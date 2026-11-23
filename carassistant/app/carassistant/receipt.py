"""Read a fuel receipt from a photo: text recognition on this server (Tesseract), then a parser that picks the refuel out of the text.

Nothing leaves the server: the photo is cleaned up, read and thrown away (it is never stored), and no online service is asked. The result only
*fills in* the form of a new refuel; the person looks at it and saves. When Tesseract is not installed the feature is simply not offered.

``parse`` works on plain text, so it can be tested without a photo. It looks for the amount, the price per litre and the total, and checks
that ``amount x price = total`` (to the cent): with that check a misread digit is found and a missing value is calculated.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import tempfile
import threading
from datetime import date, timedelta
from itertools import product

MAX_BYTES = 12 * 1024 * 1024
MAX_PIXELS = 40_000_000
TIMEOUT = 45
_one_at_a_time = threading.Semaphore(1)  # a small device reads one photo at a time
_langs: list[str] | None = None

NUMBER = re.compile(r"(?<![\d.,])(\d{1,4})[.,](\d{1,3})(?![\d])")
LITRE_LABEL = re.compile(r"\b(menge|liter|litre|volumen|volume|quantity|qty|zapfmenge|getankt|kraftstoffmenge|kwh)\b", re.I)
PRICE_LABEL = re.compile(r"(preis|price|literpreis|prix|/\s*l\b|/\s*ltr|/\s*liter|je\s*liter|pro\s*liter|eur\s*/|€\s*/)", re.I)
TOTAL_LABEL = re.compile(
    r"\b(summe|gesamt|gesamtbetrag|betrag|endbetrag|zahlbetrag|zu\s+zahlen|total|brutto|amount|sum|bar|ec|karte|visa|mastercard)\b", re.I
)
SKIP_LINE = re.compile(r"\b(mwst|ust|steuer|netto|tax|vat|tel|fax|kundenkarte|punkte|bonus|iban|bic|kennzeichen)\b", re.I)

BRANDS = (
    ("Aral", r"aral"),
    ("Shell", r"shell"),
    ("Esso", r"esso"),
    ("JET", r"jet\s*tankstelle|\bjet\b"),
    ("TotalEnergies", r"total\s*energies|\btotal\s+(?:tank|station|service|access|marketing)"),
    ("HEM", r"\bhem\b"),
    ("OMV", r"\bomv\b"),
    ("Avia", r"\bavia\b"),
    ("BP", r"\bbp\b"),
    ("star", r"\bstar\s+tankstelle|\bstar\b"),
    ("Eni", r"\beni\b|agip"),
    ("Orlen", r"orlen"),
    ("Tamoil", r"tamoil"),
    ("Hoyer", r"hoyer"),
    ("Sprint", r"\bsprint\b"),
    ("bft", r"\bbft\b"),
    ("Q1", r"\bq1\b"),
    ("Westfalen", r"westfalen"),
    ("Allguth", r"allguth"),
    ("Classic", r"\bclassic\s+tank"),
    ("Raiffeisen", r"raiffeisen"),
    ("Roth", r"\broth\b"),
    ("Markant", r"markant"),
    ("Supol", r"supol"),
    ("Turmöl", r"turm\s*[oö]l"),
    ("Genol", r"genol"),
    ("Avanti", r"avanti"),
    ("Migrol", r"migrol"),
    ("Agrola", r"agrola"),
    ("Coop", r"coop\s*pronto"),
    ("Repsol", r"repsol"),
    ("Cepsa", r"cepsa"),
    ("Galp", r"\bgalp\b"),
    ("Circle K", r"circle\s*k"),
    ("Statoil", r"statoil"),
    ("Gulf", r"\bgulf\b"),
    ("Texaco", r"texaco"),
    ("Lukoil", r"lukoil"),
    ("MOL", r"\bmol\b"),
)
PRODUCTS = (
    ("Super E10", r"super\s*e\s*10|e10"),
    ("Super E5", r"super\s*e\s*5|\be5\b"),
    ("Super Plus", r"super\s*plus"),
    ("V-Power Diesel", r"v-?power\s*diesel|ultimate\s*diesel|diesel\s*ultimate"),
    ("V-Power", r"v-?power|ultimate\s*(?:95|100)|ultimate"),
    ("Premium Diesel", r"premium\s*diesel|diesel\s*premium|excellium|aral\s*ultimate"),
    ("Diesel", r"diesel|\bdsl\b"),
    ("Super", r"\bsuper\b|benzin|unleaded|\bsp\s*95\b|\b95\b"),
    ("Autogas", r"autogas|\blpg\b"),
    ("Erdgas", r"erdgas|\bcng\b"),
    ("Strom", r"\bkwh\b|ladevorgang|charging"),
)
NOT_A_NAME = re.compile(
    r"^(kassenbon|beleg|rechnung|quittung|tankbeleg|tank\s*quittung|kundenbeleg|kundenquittung|tax\s+invoice|receipt|invoice|danke|vielen dank)\b",
    re.I,
)


# ------------------------------------------------------------------ the text of a photo


def _binary() -> str | None:
    """The full path of Tesseract (a fixed program of this server, never anything that came with a request)."""
    return shutil.which("tesseract")


def available() -> bool:
    return _binary() is not None


def languages() -> list[str]:
    """German and English when installed (one of them otherwise): the recognition is much better with the right language data."""
    global _langs
    if _langs is None:
        try:
            out = subprocess.run([_binary() or "tesseract", "--list-langs"], capture_output=True, text=True, timeout=10, check=False).stdout  # noqa: S603
        except (OSError, subprocess.SubprocessError):
            out = ""
        have = {line.strip() for line in out.splitlines()[1:] if line.strip()}
        _langs = [x for x in ("deu", "eng") if x in have] or ([next(iter(sorted(have)))] if have else ["eng"])
    return _langs


def clean(data: bytes) -> bytes:
    """Upright, grey, with the contrast stretched and the size brought to what the recognition likes. ValueError for anything that is no photo."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError) as exc:
        raise ValueError("not an image") from exc
    img = ImageOps.exif_transpose(img).convert("L")
    img = ImageOps.autocontrast(img, cutoff=2)
    width = max(img.size)
    if width > 2600 or width < 1400:
        factor = 2000 / width
        img = img.resize((max(1, round(img.width * factor)), max(1, round(img.height * factor))), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


def read_text(data: bytes, psm: int = 6) -> str:
    """The text Tesseract finds in a cleaned photo ('' when it fails or takes too long)."""
    with tempfile.TemporaryDirectory(prefix="ca-receipt-") as tmp:
        path = os.path.join(tmp, "r.png")
        with open(path, "wb") as fh:
            fh.write(data)
        env = {**os.environ, "OMP_THREAD_LIMIT": "1"}
        try:
            run = subprocess.run(  # noqa: S603 (a fixed program, a file of our own and fixed options)
                [_binary() or "tesseract", path, "stdout", "-l", "+".join(languages()), "--psm", str(psm)],
                capture_output=True,
                text=True,
                timeout=TIMEOUT,
                env=env,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return ""
    return run.stdout if run.returncode == 0 else ""


def scan(data: bytes, today: date | None = None) -> dict:
    """A photo -> the fields of a refuel. ValueError for a file that is no photo; an empty result (``found == []``) when nothing could be read."""
    if len(data) > MAX_BYTES:
        raise ValueError("too large")
    cleaned = clean(data)
    with _one_at_a_time:
        best = parse(read_text(cleaned, 6), today)
        if len(best["found"]) < 3:  # a second reading with another page layout: keep the better one
            other = parse(read_text(cleaned, 4), today)
            if len(other["found"]) > len(best["found"]):
                best = other
    return best


# ------------------------------------------------------------------ the text of a receipt


def _num(token: str) -> float:
    return float(token.replace(",", "."))


def _numbers(line: str) -> list[tuple[float, int]]:
    """Every decimal number of a line with the number of its decimals (1,789 has three, 81,12 two)."""
    return [(_num(f"{a}.{b}"), len(b)) for a, b in NUMBER.findall(line)]


def _clean_text(text: str) -> list[str]:
    fixed = []
    for raw in text.replace("\r", "").split("\n"):
        line = raw.strip()
        if not line:
            continue
        # frequent misreadings inside a number: a letter O for a zero, l / I for a one, a space or a dot as the decimal comma
        line = re.sub(r"(?<=\d)[Oo](?=\d)|(?<=\d)[Oo](?=[.,]\d)|(?<=[.,])[Oo](?=\d)", "0", line)
        line = re.sub(r"(?<=\d)[lI](?=[.,]\d)|(?<=[.,]\d)[lI](?=\d)", "1", line)
        line = re.sub(r"(\d)\s+[,.]\s*(\d)", r"\1,\2", line)
        fixed.append(line)
    return fixed


def _dates(lines: list[str], today: date) -> str | None:
    found: list[tuple[int, date]] = []
    for line in lines:
        for m in re.finditer(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)|(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](\d{4}|\d{2})(?!\d)", line):
            try:
                if m.group(1):
                    d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                else:
                    year = int(m.group(6))
                    d = date(year + 2000 if year < 100 else year, int(m.group(5)), int(m.group(4)))
            except ValueError:
                continue
            if date(2000, 1, 1) <= d <= today + timedelta(days=1):
                found.append((0 if re.search(r"datum|date|am\b", line, re.I) else 1, d))
    return min(found, key=lambda x: x[0])[1].isoformat() if found else None


def _station(lines: list[str]) -> str:
    head = "\n".join(lines[:14])
    whole = "\n".join(lines)
    name = ""
    for brand, pattern in BRANDS:
        if re.search(pattern, head, re.I):
            name = brand
            break
    if not name:
        for brand, pattern in BRANDS[:12]:  # the well-known ones also when the name sits lower on the receipt
            if re.search(pattern, whole, re.I):
                name = brand
                break
    town = ""
    for line in lines[:18]:
        m = re.search(r"(?<!\d)\d{5}\s+([A-ZÄÖÜ][A-Za-zÄÖÜäöüß.\- ]{2,28})", line)
        if m:
            town = m.group(1).strip(" .-")
            break
    if name and town and town.lower() not in name.lower():
        return f"{name} {town}"[:80]
    if name:
        return name
    for line in lines[:6]:
        letters = re.sub(r"[^A-Za-zÄÖÜäöüß ]", "", line).strip()
        if len(letters) >= 4 and not NOT_A_NAME.match(letters) and len(letters.split()) <= 5 and not re.search(r"\d{4,}", line):
            return letters[:60]
    return ""


def _product(lines: list[str]) -> str:
    text = "\n".join(lines)
    for label, pattern in PRODUCTS:
        if re.search(pattern, text, re.I):
            return label
    return ""


def _candidates(lines: list[str]) -> tuple[list, list, list]:
    """Plausible amounts, prices per unit and totals: ``(value, weight)`` - the weight is higher when the line says what the number is."""
    amounts: dict[float, int] = {}
    prices: dict[float, int] = {}
    totals: dict[float, int] = {}
    for line in lines:
        if SKIP_LINE.search(line) and not LITRE_LABEL.search(line):
            continue
        has_litre = bool(LITRE_LABEL.search(line)) or bool(re.search(r"\d\s*(l|ltr|liter|kwh)\b", line, re.I))
        has_price = bool(PRICE_LABEL.search(line))
        has_total = bool(TOTAL_LABEL.search(line)) or bool(re.search(r"(eur|€)", line, re.I))
        for value, decimals in _numbers(line):
            if 2 <= decimals <= 3 and 2.0 <= value <= 160 and (decimals == 2 or has_litre):
                amounts[value] = max(amounts.get(value, 0), 3 if has_litre else 1)
            if 0.6 <= value <= 3.6 and (decimals == 3 or (decimals == 2 and has_price)):
                prices[value] = max(prices.get(value, 0), 3 if has_price else 1)
            if decimals == 2 and 3.0 <= value <= 500:
                totals[value] = max(
                    totals.get(value, 0),
                    3 if re.search(r"(summe|gesamt|betrag|total|zu\s+zahlen|brutto)", line, re.I) else (2 if has_total else 1),
                )
    order = lambda d: sorted(d.items(), key=lambda kv: -kv[1])[:24]  # noqa: E731
    return order(amounts), order(prices), order(totals)


def _best_triple(amounts: list, prices: list, totals: list):
    """The amount, price and total that fit together (amount x price = total, to a cent or two); the labelled ones win."""
    best, best_score = None, 0.0
    for (a, wa), (p, wp), (t, wt) in product(amounts, prices, totals):
        err = abs(a * p - t)
        if err <= 0.03 or err <= t * 0.0012:
            score = 10 + wa + wp + wt - err * 20
            if score > best_score:
                best, best_score = (a, p, t), score
    return best


def _one_digit_apart(a: str, b: str) -> bool:
    return len(a) == len(b) and sum(x != y for x, y in zip(a, b, strict=True)) == 1


def parse(text: str, today: date | None = None) -> dict:
    """The refuel in the text of a receipt: ``date``, ``amount``, ``price_per_unit``, ``price_total`` (numbers), ``station``, ``notes`` (the
    product, for example *Super E10*) and ``found`` - the names of the fields that were found (``derived`` says which of them were calculated from the other two, not read)."""
    today = today or date.today()
    lines = _clean_text(text)
    out: dict = {
        "date": None,
        "amount": None,
        "price_per_unit": None,
        "price_total": None,
        "station": "",
        "notes": "",
        "found": [],
        "checked": False,
        "derived": [],
    }
    if not lines:
        return out
    amounts, prices, totals = _candidates(lines)
    triple = _best_triple(amounts, prices, totals)
    if triple:
        out["amount"], out["price_per_unit"], out["price_total"] = triple
        out["checked"] = True
    else:
        top = lambda c, w: next((v for v, weight in c if weight >= w), None)  # noqa: E731
        a, p, t = top(amounts, 3), top(prices, 3), top(totals, 2)
        if a and p and not t:
            t = round(a * p, 2)
            out["derived"] = ["price_total"]
        elif a and t and not p and a > 0:
            p = round(t / a, 3)
            out["derived"] = ["price_per_unit"]
        elif p and t and not a:
            a = round(t / p, 2)
            out["derived"] = ["amount"]
        if a and p and t and not out["derived"]:
            calc = round(t / p, 2)
            if _one_digit_apart(f"{a:.2f}", f"{calc:.2f}"):  # the amount was misread by one digit: price and total agree with each other
                a, out["derived"] = calc, ["amount"]
        out["amount"], out["price_per_unit"], out["price_total"] = a, p, t
    out["date"] = _dates(lines, today)
    out["station"] = _station(lines)
    out["notes"] = _product(lines)
    out["found"] = [k for k in ("date", "amount", "price_per_unit", "price_total", "station", "notes") if out[k]]
    return out
