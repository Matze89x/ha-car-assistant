"""A practice set of made-up photos with their right answers, to practise (and measure) the reading of an odometer and a fuel receipt.

Nothing here is real: invented instrument clusters (analog with two dials, a window in the dial, a digital panel, a light one, miles) and invented
receipts (German, English, French, Polish; with a second product, with gas, a narrow till roll), each drawn with its right answer. ``degrade`` makes them
as bad as a phone can: blurred, dim, crooked, small, over-compressed. ``tools/ocr_bench.py`` reads every one of them with the real text recognition and
says how many it got right - the number to look at before and after a change of the reading.

  python tools/practice_photos.py <out_dir>      writes every photo + answers.json (to look at, or to try the app with)
"""

from __future__ import annotations

import io
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import demo_photos as dp  # noqa: E402

TODAY = date(2026, 11, 24)


@dataclass
class Case:
    name: str  # "cluster/digital-amber"
    kind: str  # "odometer" | "receipt"
    data: bytes
    truth: dict
    last: int | None = None  # the last reading the app would know (odometer)
    tags: list[str] = field(default_factory=list)


def _jpeg(img: Image.Image, quality: int = 88) -> bytes:
    out = io.BytesIO()
    img.convert("RGB").save(out, "JPEG", quality=quality)
    return out.getvalue()


def shown(km: int, style: str) -> str:
    """The odometer written the way a cluster writes it."""
    return {
        "plain": f"{km}",
        "zero": f"{km:06d}",
        "space": f"{km:,}".replace(",", " "),
        "dot": f"{km:,}".replace(",", "."),
        "comma": f"{km:,}",
    }[style]


# ------------------------------------------------------------------ instrument clusters


def _dial(d: ImageDraw.ImageDraw, cx: int, cy: int, r: int, top: int, steps: int, ink, f):
    d.ellipse((cx - r - 14, cy - r - 14, cx + r + 14, cy + r + 14), outline=ink, width=6)
    for i in range(steps):
        a = math.radians(135 + i * 270 / (steps - 1))
        d.line(
            (cx + (r - 8) * math.cos(a), cy + (r - 8) * math.sin(a), cx + (r - 44) * math.cos(a), cy + (r - 44) * math.sin(a)),
            fill=ink,
            width=5,
        )
        d.text((cx + (r - 86) * math.cos(a), cy + (r - 86) * math.sin(a)), str(round(i * top / (steps - 1))), fill=ink, font=f, anchor="mm")
    a = math.radians(135 + 0.31 * 270)
    d.line((cx, cy, cx + (r - 70) * math.cos(a), cy + (r - 70) * math.sin(a)), fill=(226, 0, 26), width=9)
    d.ellipse((cx - 22, cy - 22, cx + 22, cy + 22), fill=(60, 62, 68))


def cluster(style: str, km: int = 86_020, trip: float = 24.5, unit: str = "km", fmt: str = "plain", seed: int = 1) -> bytes:
    """One instrument cluster. ``style``: analog (two dials, the display between them), window (one big dial with a small window), digital (a panel),
    light (dark digits on a light cluster)."""
    w, h = 1600, 900
    light = style == "light"
    bg, ink, dim = ((214, 216, 218), (24, 26, 30), (90, 94, 100)) if light else ((10, 11, 14), (235, 236, 240), (150, 154, 162))
    img = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(img)
    num, label = dp.font(36), dp.font(30)
    text = f"{shown(km, fmt)} {unit}"
    trip_text = f"{trip:.1f} {unit}".replace(".", "," if fmt in ("dot", "space") else ".")
    if style in ("analog", "light"):
        _dial(d, 430, 400, 330, 260, 14, ink, num)
        _dial(d, 1170, 400, 330, 8, 9, ink, num)
        d.rounded_rectangle((520, 560, 1080, 800), radius=26, fill=(18, 20, 26) if not light else (236, 237, 238), outline=dim, width=3)
        d.text((552, 588), "TRIP A", fill=dim, font=label)
        d.text((1048, 588), trip_text, fill=ink, font=label, anchor="ra")
        d.text((800, 700), text, fill=ink, font=dp.font(92, True), anchor="mm")
    elif style == "window":
        _dial(d, 800, 430, 380, 260, 14, ink, num)
        d.rectangle((690, 560, 910, 610), fill=(0, 0, 0), outline=dim, width=2)
        d.text(
            (800, 586), f"{km:06d}", fill=(240, 240, 240), font=dp.font(40, True), anchor="mm"
        )  # a small window in the dial: the digits are small
        d.text((800, 632), unit, fill=dim, font=dp.font(26), anchor="mm")
        d.text((800, 668), trip_text, fill=dim, font=dp.font(26), anchor="mm")
    else:  # digital panel
        amber = (255, 176, 40)
        d.text((800, 270), "87", fill=ink, font=dp.font(260, True), anchor="mm")
        d.text((800, 410), "km/h", fill=dim, font=dp.font(46), anchor="mm")
        for k in range(18):  # a bar of segments
            d.rectangle((260 + k * 62, 480, 260 + k * 62 + 44, 520), fill=amber if k < 9 else (50, 52, 58))
        d.text((300, 640), "TRIP", fill=dim, font=label)
        d.text((1300, 640), trip_text, fill=amber, font=dp.font(48, True), anchor="ra")
        d.text((800, 760), text, fill=amber, font=dp.font(110, True), anchor="mm")
    return dp._photo(img, angle=1.2 + (seed % 3) * 0.4, seed=seed, blur=0.9)


def cluster_cases() -> list[Case]:
    cases = []
    spec = [
        ("analog", 86_020, "km", "plain"),
        ("analog", 123_456, "km", "zero"),
        ("analog", 9_870, "km", "plain"),
        ("analog", 86_020, "km", "space"),
        ("analog", 86_020, "km", "dot"),
        ("analog", 53_450, "mi", "comma"),
        ("window", 86_020, "km", "zero"),
        ("window", 212_345, "km", "zero"),
        ("digital", 86_020, "km", "plain"),
        ("digital", 140_300, "km", "space"),
        ("light", 86_020, "km", "plain"),
        ("light", 45_730, "km", "dot"),
    ]
    for i, (style, km, unit, fmt) in enumerate(spec):
        cases.append(
            Case(
                f"cluster/{style}-{km}-{unit}-{fmt}",
                "odometer",
                cluster(style, km, 24.5, unit, fmt, seed=i + 1),
                {"value": km},
                last=km - 640,
                tags=[style, unit],
            )
        )
    return cases


# ------------------------------------------------------------------ receipts


def receipt(
    lang: str = "de",
    product: str = "Diesel",
    amount: float = 42.70,
    price: float = 1.649,
    odometer: int | None = 86_020,
    extra: bool = False,
    narrow: bool = False,
    seed: int = 4,
) -> bytes:
    """A receipt as a till prints it. ``lang``: de, en, fr, pl. ``extra``: a coffee and water on it; ``narrow``: a thin till roll."""
    total = round(amount * price, 2)
    vat = total / 119 * 19
    d2 = lambda v: f"{v:.2f}"  # noqa: E731
    comma = lang in ("de", "fr", "pl")
    n = (lambda s: s.replace(".", ",")) if comma else (lambda s: s)
    words = {
        "de": ("Datum", "Saeule", "Menge", "Preis/l", "SUMME EUR", "MwSt 19%", "EC-Karte", "KM-Stand", "Vielen Dank fuer Ihren Besuch"),
        "en": ("Date", "Pump", "Volume", "Price/l", "TOTAL EUR", "VAT 19%", "Card", "Odometer", "Thank you for your visit"),
        "fr": ("Date", "Pompe", "Volume", "Prix/L", "TOTAL EUR", "TVA 20%", "Carte", "Kilometrage", "Merci de votre visite"),
        "pl": ("Data", "Dystrybutor", "Ilosc", "Cena/l", "RAZEM EUR", "VAT 23%", "Karta", "Przebieg", "Dziekujemy"),
    }[lang]
    head = {
        "de": ("EXAMPLE FUEL", "Musterstrasse 12", "12345 Musterstadt"),
        "en": ("EXAMPLE FUEL", "12 Sample Street", "Exampletown"),
        "fr": ("EXAMPLE CARBURANT", "12 rue Exemple", "75001 Exempleville"),
        "pl": ("EXAMPLE PALIWA", "ul. Przykladowa 12", "00-001 Przykladowo"),
    }[lang]
    size = 27 if narrow else 31
    big, text, small = dp.font(size + 9, True), dp.font(size, True), dp.font(size - 6, True)
    paper = Image.new("RGB", (480 if narrow else 640, 1150 if extra else 1020), (244, 243, 238))
    d = ImageDraw.Draw(paper)
    unit = "l"
    lines = [
        (big, head[0]),
        (text, head[1]),
        (text, head[2]),
        (small, ""),
        (text, f"{words[0]}: {TODAY.day:02d}.{TODAY.month:02d}.{TODAY.year}  17:42"),
        (text, f"{words[1]} 4"),
        (small, ""),
    ]
    if extra:
        lines += [(text, n("Kaffee 2.50")), (text, n("Wasser 1.29")), (small, "")]
    lines += [
        (text, product),
        (text, n(f"{words[2]}  {d2(amount)} {unit}")),
        (text, n(f"{words[3]}  {price:.3f} EUR/l")),
        (small, "-" * 28),
        (big, n(f"{words[4]} {d2(total)}")),
        (small, "-" * 28),
        (text, n(f"{words[5]}  {d2(vat)} EUR")),
        (text, words[6]),
    ]
    if odometer is not None:
        lines += [(small, ""), (text, f"{words[7]}: {odometer}")]
    lines += [(small, ""), (small, words[8])]
    y = 36
    for f, line in lines:
        d.text((28, y), line, fill=(28, 28, 30), font=f)
        y += f.size + 14
    img = Image.new("RGB", (paper.width + 260, paper.height + 160), (34, 36, 40))
    img.paste(paper, (130, 80))
    return dp._photo(img, angle=-2.2, seed=seed)


def receipt_cases() -> list[Case]:
    cases = []
    spec = [
        ("de", "Diesel", 42.70, 1.649, 86_020, False, False),
        ("de", "Super E10", 38.07, 1.719, None, False, False),
        ("de", "Super E10", 51.25, 1.789, 120_450, True, False),
        ("de", "V-Power Diesel", 38.07, 1.659, None, False, True),
        ("de", "Autogas", 31.40, 0.799, 86_020, False, False),
        ("en", "Diesel", 42.70, 1.649, 86_020, False, False),
        ("en", "Unleaded", 36.20, 1.559, None, True, False),
        ("fr", "Gazole", 40.15, 1.789, 86_020, False, False),
        ("pl", "ON Diesel", 45.50, 1.629, None, False, False),
    ]
    labels = {
        "Diesel": "Diesel",
        "Super E10": "Super E10",
        "V-Power Diesel": "V-Power Diesel",
        "Autogas": "Autogas",
        "Unleaded": "",
        "Gazole": "",
        "ON Diesel": "",
    }
    for i, (lang, product, amount, price, odo, extra, narrow) in enumerate(spec):
        truth = {
            "amount": amount,
            "price_per_unit": price,
            "price_total": round(amount * price, 2),
            "date": TODAY.isoformat(),
            "odometer": odo,
            "notes": labels[product] or None,
        }
        cases.append(
            Case(
                f"receipt/{lang}-{product.replace(' ', '-')}",
                "receipt",
                receipt(lang, product, amount, price, odo, extra, narrow, seed=i + 2),
                truth,
                last=(odo - 400) if odo else 86_000,
                tags=[lang],
            )
        )
    return cases


# ------------------------------------------------------------------ as bad as a phone can make them

DEGRADATIONS = ("clean", "blur", "dim", "left", "right", "small", "squeezed", "glare")


def degrade(data: bytes, kind: str) -> bytes:
    img = Image.open(io.BytesIO(data)).convert("RGB")
    if kind == "blur":
        img = img.filter(ImageFilter.GaussianBlur(2.0))
    elif kind == "dim":
        img = ImageEnhance.Brightness(img).enhance(0.5)
    elif kind in ("left", "right"):
        img = img.rotate(8 if kind == "left" else -8, expand=True, fillcolor=(30, 30, 30), resample=Image.BICUBIC)
    elif kind == "small":
        img = img.resize((max(400, img.width // 3), max(300, img.height // 3)), Image.LANCZOS)
    elif kind == "squeezed":
        return _jpeg(img, 22)
    elif kind == "glare":  # a bright reflection across a part of the picture
        glare = Image.new("RGB", img.size, (255, 255, 255))
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).ellipse(
            (int(img.width * 0.55), int(img.height * 0.05), int(img.width * 0.95), int(img.height * 0.45)), fill=110
        )
        img = Image.composite(glare, img, mask.filter(ImageFilter.GaussianBlur(60)))
    return _jpeg(img, 82)


def all_cases() -> list[Case]:
    return cluster_cases() + receipt_cases()


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "practice")
    out.mkdir(parents=True, exist_ok=True)
    answers = {}
    for case in all_cases():
        name = case.name.replace("/", "-")
        (out / f"{name}.jpg").write_bytes(case.data)
        answers[f"{name}.jpg"] = {"kind": case.kind, "right_answer": case.truth, "last_reading": case.last}
    (out / "answers.json").write_text(json.dumps(answers, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(answers)} photos and answers.json in {out}")
