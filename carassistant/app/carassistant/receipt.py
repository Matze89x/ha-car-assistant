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

FIELDS = (
    "date",
    "amount",
    "price_per_unit",
    "price_total",
    "station",
    "notes",
    "odometer",
)  # what a receipt can fill in, in the order of the form
# the odometer, when the station printed it (typed at the pump, fleet and company cards): "KM-Stand: 86020", "Kilometerstand 86.020", "Odometer 86020"
ODOMETER_LABEL = re.compile(
    r"\b(?:km[\s.\-]*sta[a-z]{1,2}|kilometer[\s.\-]*sta[a-z]{1,2}|tachostand|odometer|mileage|fzg\.?[\s\-]*km|kilom[eé]trage|compteur|przebieg|chilometraggio|kilometraje|od[oó]metro)\b[\s.:=]*(\d{1,3}(?:[ .,'’]\d{3})+|\d{3,7})(?!\d)",
    re.I,
)

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
    ("Super E10", r"super\s*e\s*1\s*[0oO@°]|\be\s*1\s*[0oO@°]\b|sans\s*plomb\s*98?\s*e10"),
    ("Super E5", r"super\s*e\s*5|\be5\b"),
    ("Super Plus", r"super\s*plus"),
    ("V-Power Diesel", r"v-?power\s*diesel|ultimate\s*diesel|diesel\s*ultimate"),
    ("V-Power", r"v-?power|ultimate\s*(?:95|100)|ultimate"),
    ("Premium Diesel", r"premium\s*diesel|diesel\s*premium|excellium|aral\s*ultimate"),
    ("Diesel", r"diesel|\bdsl\b|gazole|gasoil|gas[oó]leo|olej\s*nap[eę]dowy"),
    ("Super", r"\bsuper\b|benzin|unleaded|sans\s*plomb|gasolina|benzyna|\bsp\s*9[58]\b|\b95\b"),
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


def skew(data: bytes) -> float:
    """How far a photo is turned: the angle (degrees, -14 ... 14) at which the lines of text are most clearly separate - the rows of a straight line of
    digits differ most from each other (the variance of the row means of the black-and-white middle of the photo). 0 when turning does not help clearly."""
    from PIL import Image, ImageOps, ImageStat

    img = Image.open(io.BytesIO(data)).convert("L")
    img.thumbnail((520, 520))
    w, h = img.size
    img = ImageOps.autocontrast(
        img.crop((int(w * 0.15), int(h * 0.25), int(w * 0.85), int(h * 0.95))), cutoff=2
    )  # the middle and lower part: digits, not dials or edges
    mean = ImageStat.Stat(img).mean[0]
    img = img.point(lambda v: 255 if v > mean else 0)
    fill = round(ImageStat.Stat(img).mean[0])

    def score(angle: float) -> float:
        turned = img.rotate(angle, resample=Image.BILINEAR, fillcolor=fill)
        return ImageStat.Stat(turned.resize((1, turned.height), Image.BOX)).var[0]

    base = score(0)
    best, best_score = 0.0, base
    for angle in range(-14, 15, 2):
        if angle and (s := score(angle)) > best_score:
            best, best_score = float(angle), s
    for angle in (best - 1, best + 1):
        if best and (s := score(angle)) > best_score:
            best, best_score = angle, s
    return best if abs(best) >= 2 and best_score > base * 1.15 else 0.0


def deskew(data: bytes) -> bytes:
    """The photo turned back straight (when it is clearly crooked), else as it is."""
    angle = skew(data)
    if not angle:
        return data
    from PIL import Image, ImageStat

    img = Image.open(io.BytesIO(data)).convert("L")
    out = io.BytesIO()
    img.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=round(ImageStat.Stat(img).mean[0])).save(out, "PNG")
    return out.getvalue()


def lower(data: bytes, fraction: float = 0.5) -> bytes:
    """The lower part of a cleaned photo: the odometer of a car sits in the lower half of the cluster, away from the dial numbers."""
    from PIL import Image

    img = Image.open(io.BytesIO(data))
    top = min(max(int(img.height * (1 - fraction)), 0), img.height - 1)
    out = io.BytesIO()
    img.crop((0, top, img.width, img.height)).save(out, "PNG")
    return out.getvalue()


def inverted(data: bytes) -> bytes:
    """The same cleaned photo with light and dark swapped (a cluster shows light digits on dark: the recognition prefers dark on light)."""
    from PIL import Image, ImageOps

    img = ImageOps.invert(Image.open(io.BytesIO(data)).convert("L"))
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


def variant(data: bytes, kind: str) -> bytes:
    """Another view of a cleaned photo for a second try: ``sharp`` (a soft photo: bigger and sharper), ``bin`` (faded thermal paper: black and white),
    ``left`` / ``right`` (a receipt held a little crooked: turned back by 5 and 10 degrees)."""
    from PIL import Image, ImageFilter, ImageOps

    img = Image.open(io.BytesIO(data)).convert("L")
    if kind == "sharp":
        img = img.resize((round(img.width * 1.5), round(img.height * 1.5)), Image.LANCZOS).filter(
            ImageFilter.UnsharpMask(radius=3, percent=220, threshold=2)
        )
    elif kind == "bin":
        img = ImageOps.autocontrast(img, cutoff=8).point(lambda v: 255 if v > 150 else 0)
    elif kind.startswith(("left", "right")):
        angle = {"left": 5, "right": -5, "left2": 10, "right2": -10}[kind]
        img = img.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=255)
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


def read_text(data: bytes, psm: int = 6, digits: bool = False) -> str:
    """The text Tesseract finds in a cleaned photo ('' when it fails or takes too long); ``digits`` lets it answer with digits only."""
    with tempfile.TemporaryDirectory(prefix="ca-receipt-") as tmp:
        path = os.path.join(tmp, "r.png")
        with open(path, "wb") as fh:
            fh.write(data)
        env = {**os.environ, "OMP_THREAD_LIMIT": "1"}
        try:
            run = subprocess.run(  # noqa: S603 (a fixed program, a file of our own and fixed options)
                [
                    _binary() or "tesseract",
                    path,
                    "stdout",
                    "-l",
                    "+".join(languages()),
                    "--psm",
                    str(psm),
                    *(["-c", "tessedit_char_whitelist=0123456789"] if digits else []),
                ],
                capture_output=True,
                text=True,
                timeout=TIMEOUT,
                env=env,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return ""
    return run.stdout if run.returncode == 0 else ""


def _score(result: dict) -> int:
    """How much a reading is worth: the fields found, a lot more when amount x price = total holds, less for a value that was calculated."""
    return len(result["found"]) + (8 if result["checked"] else 0) - 2 * len(result["derived"])


def _good(result: dict) -> bool:
    return result["checked"] and not result["derived"] and len(result["found"]) >= 5 and bool(result["date"])


def scan(data: bytes, today: date | None = None) -> dict:
    """A photo -> the fields of a refuel. ValueError for a file that is no photo; an empty result (``found == []``) when nothing could be read.

    One reading first. When it is not complete and does not add up (amount x price = total), more tries follow with another page layout, a sharper
    and bigger copy, black and white (faded thermal paper) and the photo turned back a little (a crooked receipt); the best reading wins and
    what only another try found (date, product, odometer) is added."""
    if len(data) > MAX_BYTES:
        raise ValueError("too large")
    cleaned = deskew(clean(data))
    seen: dict[int, int] = {}  # odometer readings found and how many readings found each

    def note(result: dict) -> dict:
        if result["odometer"]:
            seen[result["odometer"]] = seen.get(result["odometer"], 0) + 1
        return result

    with _one_at_a_time:
        best = note(parse(read_text(cleaned, 6), today))
        if not _good(best):
            tries = ((None, 4), ("sharp", 6), ("bin", 6), ("left", 6), ("right", 6), ("left2", 6), ("right2", 6))
            for kind, psm in tries:
                other = note(parse(read_text(cleaned if kind is None else variant(cleaned, kind), psm), today))
                better, worse = (other, best) if _score(other) > _score(best) else (best, other)
                for key in ("date", "notes"):  # what only the other reading found is kept
                    if not better[key] and worse[key]:
                        better[key] = worse[key]
                best = better
                if _good(best):
                    break
        # one digit wrong in a kilometre figure would go unnoticed (a 0 read as a 9): a figure that was found is read once more in other views, and the
        # digits are voted on position by position; a figure that does not come out the same in at least two readings is not offered
        if seen:
            for kind, psm in ((None, 4), ("sharp", 6), ("bin", 6), ("left", 6), ("right", 6)):
                if max(seen.values()) >= 3 or sum(seen.values()) >= 4:
                    break
                note(parse(read_text(cleaned if kind is None else variant(cleaned, kind), psm), today))
    best["odometer"] = _vote_odometer(seen)
    best["found"] = [k for k in FIELDS if best.get(k)]
    return best


def _vote_odometer(seen: dict[int, int]) -> int | None:
    """The odometer the readings agree on: the figure found most often, with every digit decided by the vote of the figures of the same length that differ from it in at most
    one place. A figure found only once is not trusted (None)."""
    if not seen:
        return None
    top = max(seen.items(), key=lambda kv: (kv[1], len(str(kv[0])), kv[0]))[0]
    group = {
        n: c for n, c in seen.items() if len(str(n)) == len(str(top)) and sum(a != b for a, b in zip(str(n), str(top), strict=True)) <= 1
    }
    digits = []
    for pos in range(len(str(top))):
        votes: dict[str, int] = {}
        for n, c in group.items():
            votes[str(n)[pos]] = votes.get(str(n)[pos], 0) + c
        digits.append(max(votes.items(), key=lambda kv: (kv[1], kv[0] == str(top)[pos]))[0])
    value = int("".join(digits))
    return value if sum(group.values()) >= 2 else None


# ------------------------------------------------------------------ the text of a receipt


def _num(token: str) -> float:
    return float(token.replace(",", "."))


def _numbers(line: str) -> list[tuple[float, int]]:
    """Every decimal number of a line with the number of its decimals (1,789 has three, 81,12 two)."""
    return [(_num(f"{a}.{b}"), len(b)) for a, b in NUMBER.findall(line)]


def _clean_text(text: str) -> list[str]:
    fixed = []
    for raw in text.replace("\r", "").split("\n"):
        line = re.sub(r"[‐‑–—−]", "-", raw.strip())  # an en or em dash is a hyphen (EC—Karte, V—Power)
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


def _odometer(lines: list[str]) -> int | None:
    """The odometer reading the station printed (only a labelled number: a receipt is full of other numbers), in kilometres."""
    for line in lines:
        m = ODOMETER_LABEL.search(re.sub(r"(?<=\d)[Oo](?=\d)", "0", line))
        if m:
            value = int(re.sub(r"\D", "", m.group(1)))
            if 100 <= value <= 9_999_999:
                return value
    return None


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
    product, for example *Super E10*), ``odometer`` (kilometres, only when the station printed it) and ``found`` - the names of the fields that were found (``derived`` says which of them were calculated from the other two, not read)."""
    today = today or date.today()
    lines = _clean_text(text)
    out: dict = {
        "date": None,
        "amount": None,
        "price_per_unit": None,
        "price_total": None,
        "station": "",
        "notes": "",
        "odometer": None,
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
    out["odometer"] = _odometer(lines)
    out["found"] = [k for k in FIELDS if out[k]]
    return out
