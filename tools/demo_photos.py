"""Made-up photos for the documentation and the tests of the text recognition: a fuel receipt and the instrument cluster of a car.

Everything is invented (no brand, no real station, no real car). The pictures are drawn with Pillow, a little rotated, blurred and noisy so that
they are no cleaner than a phone photo; ``make_screenshots.py`` shows them next to the form they fill in, the tests read them with the real
Tesseract when it is installed.

  python tools/demo_photos.py <out_dir>        writes receipt.jpg and cluster.jpg
"""

from __future__ import annotations

import io
import math
import random
import sys
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

_MONO = (
    "/System/Library/Fonts/Menlo.ttc",
    "/System/Library/Fonts/Monaco.ttf",
    "/usr/share/fonts/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
)
_SANS = (
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)


def font(size: int, mono: bool = False) -> ImageFont.ImageFont:
    for path in _MONO if mono else _SANS:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default(size)


def _photo(img: Image.Image, angle: float, seed: int, blur: float = 0.8, noise: int = 7) -> bytes:
    """What a phone makes of a picture: a little turned, a little soft, a little noise, saved as JPEG."""
    rnd = random.Random(seed)  # noqa: S311 (a fixed seed: the pictures look the same every time)
    img = img.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=(34, 36, 40))
    img = img.filter(ImageFilter.GaussianBlur(blur))
    px = img.load()
    for _ in range(img.width * img.height // 9):
        x, y = rnd.randrange(img.width), rnd.randrange(img.height)
        r, g, b = px[x, y][:3]
        d = rnd.randint(-noise, noise)
        px[x, y] = (max(0, min(255, r + d)), max(0, min(255, g + d)), max(0, min(255, b + d)))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=86)
    return out.getvalue()


def receipt_photo(today: date | None = None, odometer: int | None = 86_020, lang: str = "de") -> bytes:
    """A fuel receipt as a till prints it: station, date, product, litres, price per litre, total - and, as many stations print it when it
    was typed at the pump, the odometer."""
    today = today or date.today()
    w, h = 900, 1180
    img = Image.new("RGB", (w, h), (34, 36, 40))  # the table
    paper = Image.new("RGB", (640, 1020), (244, 243, 238))
    d = ImageDraw.Draw(paper)
    big, text, small = font(40, True), font(31, True), font(25, True)
    amount, price = 42.70, 1.649
    total = round(amount * price, 2)
    vat = total / 119 * 19
    if lang == "de":
        lines = [
            (big, "EXAMPLE FUEL"),
            (text, "Musterstrasse 12"),
            (text, "12345 Musterstadt"),
            (small, ""),
            (text, f"Datum: {today.day:02d}.{today.month:02d}.{today.year}  17:42"),
            (text, "Saeule 4"),
            (small, ""),
            (text, "Diesel"),
            (text, f"Menge      {amount:.2f} l".replace(".", ",")),
            (text, f"Preis/l    {price:.3f} EUR/l".replace(".", ",")),
            (small, "-" * 28),
            (big, f"SUMME EUR {total:.2f}".replace(".", ",")),
            (small, "-" * 28),
            (text, f"MwSt 19%   {vat:.2f} EUR".replace(".", ",")),
            (text, "EC-Karte"),
        ]
        if odometer is not None:
            lines += [(small, ""), (text, f"KM-Stand: {odometer}")]
        lines += [(small, ""), (small, "Vielen Dank fuer Ihren Besuch")]
    else:
        lines = [
            (big, "EXAMPLE FUEL"),
            (text, "12 Sample Street"),
            (text, "Exampletown"),
            (small, ""),
            (text, f"Date: {today.day:02d}.{today.month:02d}.{today.year}  17:42"),
            (text, "Pump 4"),
            (small, ""),
            (text, "Diesel"),
            (text, f"Volume     {amount:.2f} l"),
            (text, f"Price/l    {price:.3f} EUR/l"),
            (small, "-" * 28),
            (big, f"TOTAL EUR {total:.2f}"),
            (small, "-" * 28),
            (text, f"VAT 19%    {vat:.2f} EUR"),
            (text, "Card"),
        ]
        if odometer is not None:
            lines += [(small, ""), (text, f"Odometer: {odometer}")]
        lines += [(small, ""), (small, "Thank you for your visit")]
    y = 36
    for f, line in lines:
        d.text((28, y), line, fill=(28, 28, 30), font=f)
        y += f.size + 14
    img.paste(paper, (130, 80))
    return _photo(img, angle=-2.2, seed=4)


def cluster_photo(odometer: int = 86_020, trip: float = 24.5) -> bytes:
    """The instrument cluster of a car, seen from the driver's seat: a round speedometer, a round rev counter and, in the lower middle, the
    little display with the odometer and - smaller, above it - the trip counter."""
    w, h = 1600, 900
    img = Image.new("RGB", (w, h), (10, 11, 14))
    d = ImageDraw.Draw(img)
    num, label, digits = font(36), font(30), font(92, True)
    for cx, top, top_label in ((430, 0, 260), (1170, 0, 8)):
        cy, r = 400, 330
        d.ellipse((cx - r - 14, cy - r - 14, cx + r + 14, cy + r + 14), outline=(60, 64, 72), width=6)
        steps = 14 if top_label == 260 else 9  # 0, 20 ... 260 km/h and 0 ... 8 x1000/min
        for i in range(steps):
            a = math.radians(135 + i * 270 / (steps - 1))
            x1, y1 = cx + (r - 8) * math.cos(a), cy + (r - 8) * math.sin(a)
            x2, y2 = cx + (r - 44) * math.cos(a), cy + (r - 44) * math.sin(a)
            d.line((x1, y1, x2, y2), fill=(235, 236, 240), width=5)
            value = str(i * 20) if top_label == 260 else str(i)
            tx, ty = cx + (r - 86) * math.cos(a), cy + (r - 86) * math.sin(a)
            d.text((tx, ty), value, fill=(235, 236, 240), font=num, anchor="mm")
        a = math.radians(135 + 0.31 * 270)  # the needle
        d.line((cx, cy, cx + (r - 70) * math.cos(a), cy + (r - 70) * math.sin(a)), fill=(226, 0, 26), width=9)
        d.ellipse((cx - 22, cy - 22, cx + 22, cy + 22), fill=(40, 42, 48))
    d.text((430, 520), "km/h", fill=(150, 154, 162), font=label, anchor="mm")
    d.text((1170, 520), "x1000/min", fill=(150, 154, 162), font=label, anchor="mm")
    # the display between the dials: trip counter on top, odometer below
    d.rounded_rectangle((520, 560, 1080, 800), radius=26, fill=(18, 20, 26), outline=(70, 74, 84), width=3)
    d.text((552, 588), "TRIP A", fill=(140, 144, 152), font=label)
    d.text((1048, 588), f"{trip:.1f} km", fill=(235, 236, 240), font=label, anchor="ra")
    d.text((800, 700), f"{odometer} km", fill=(246, 247, 250), font=digits, anchor="mm")
    return _photo(img, angle=1.4, seed=9, blur=1.0)


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    (out / "receipt.jpg").write_bytes(receipt_photo())
    (out / "cluster.jpg").write_bytes(cluster_photo())
    print("written to", out)
