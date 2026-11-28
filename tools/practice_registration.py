"""Made-up registration certificates (Zulassungsbescheinigung Teil I, the "Fahrzeugschein") with their right answers, to practise (and measure) the reading of
a certificate - for the tests, for the documentation and for trying the app without a real document.

NOTHING HERE IS REAL: the layout follows the harmonised form (three pages side by side: the holder and the plate on the left, the vehicle in a table of numbered
fields in the middle and on the right), but every value is invented - the holder is the stock "Mustermann", the plate, the VIN, the numbers are made up.
``photo`` makes a picture of such a certificate as bad as a phone can: crooked, with an uneven light, soft, over-compressed, lying on a dark table.

  python tools/practice_registration.py <out_dir>      writes the certificates (clean and as photos) and answers.json
  python tools/practice_registration.py --bench [n]    reads them n ways (another noise, light and blur each time) with the real text recognition (Tesseract must
                                                       be installed) and counts what was right, wrong and missing: change the reading, run this again, and the
                                                       number of WRONG fields (above all those the app calls sure) must not go up
"""

from __future__ import annotations

import io
import json
import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import demo_photos as dp  # (a font with umlauts, wherever the tool runs)

PAPER = (1720, 870)  # the paper of the folded certificate, in pixels
INK = (28, 30, 28)
SHEET = (214, 226, 214)  # the green-grey security paper


@dataclass
class Sample:
    name: str
    data: bytes  # a photo (JPEG)
    clean: bytes  # the flat picture (PNG)
    truth: dict  # what the app should offer for the pass: the form fields of the vehicle
    inspection: str  # the month of the next inspection, "2027-06"


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    return dp.font(size)


# ------------------------------------------------------------------ the three pages

# the table of the middle page: (height, [(label of the small box, value, share of the row), ...]); a value of None is an empty cell
MID_X, MID_W = 535, 570
RIGHT_X, RIGHT_W = 1125, 595


def _middle(v: dict) -> list[tuple[int, list[tuple[str, str | None, float]]]]:
    return [
        (47, [("B", v["first_reg_text"], 0.36), ("2.1", v["hsn"], 0.26), ("2.2", v["tsn_text"], 0.38)]),
        (33, [("J", v["class"], 0.6), ("4", v["code4"], 0.4)]),
        (38, [("E", v["vin"], 0.8), ("3", "X", 0.2)]),
        (32, [("D.1", v["make_text"], 1.0)]),
        (35, [("", v["type"], 1.0)]),
        (35, [("D.2", v["variant"], 1.0)]),
        (38, [("", v["version"], 1.0)]),
        (35, [("", None, 1.0)]),
        (35, [("D.3", v["trade_text"], 1.0)]),
        (37, [("2", v["short"], 1.0)]),
        (32, [("5", v["class_text"], 1.0)]),
        (31, [("", v["body_text"], 1.0)]),
        (37, [("V.9", v["emission_regs"], 1.0)]),
        (38, [("14", v["euro"], 1.0)]),
        (35, [("P.3", v["fuel_text"], 1.0)]),
        (35, [("10", "0001", 0.3), ("14.1", "35F0", 0.35), ("P.1", v["displacement_text"], 0.35)]),
        (32, [("22", "DATUM ZUR EMISSIONSKLASSE: " + v["first_reg_text"] + "*", 1.0)]),  # (a smaller type: the row is long)
    ]


def _right(v: dict) -> list[tuple[int, list[tuple[str, str | None, float]]]]:
    return [
        (47, [("L", "2", 0.18), ("9", "1", 0.18), ("P.2 P.4", v["power_text"], 0.42), ("T", v["speed"], 0.22)]),
        (33, [("18", v["length"], 0.5), ("19", v["width"], 0.5)]),
        (38, [("20", v["height"], 0.5), ("G", v["unladen"] + "--", 0.5)]),
        (32, [("12", None, 0.4), ("13", "-", 0.3), ("Q", "-", 0.3)]),
        (35, [("V.7", v["co2"], 0.3), ("F.1", v["mass"], 0.35), ("F.2", v["mass"], 0.35)]),
        (35, [("7.1", "920", 0.3), ("7.2", "790", 0.35), ("7.3", "-", 0.35)]),
        (38, [("8.1", "920", 0.3), ("8.2", "790", 0.35), ("8.3", "-", 0.35)]),
        (35, [("U.1", "85", 0.3), ("U.2", "3750", 0.35), ("U.3", "74", 0.35)]),
        (35, [("O.1", "-", 0.3), ("O.2", "-", 0.3), ("S.1", v["seats"], 0.2), ("S.2", "-", 0.2)]),
        (37, [("15.1", v["tyre"], 1.0)]),
        (32, [("15.2", v["tyre"], 1.0)]),
        (31, [("15.3", "-", 1.0)]),
        (37, [("R", v["color_text"], 0.8), ("11", "7", 0.2)]),
        (38, [("K", v["approval"], 1.0)]),
        (35, [("6", v["approval_date"], 0.5), ("17", "K", 0.2), ("16", v["code16"], 0.3)]),
        (35, [("21", None, 1.0)]),
    ]


def _table(d: ImageDraw.ImageDraw, x0: int, width: int, rows, top: int, value_font, label_font) -> int:
    """Draw ruled rows; returns the y under the last row."""
    y = top
    d.line((x0, y, x0 + width, y), fill=INK, width=2)
    for height, cells in rows:
        x = x0
        for label, value, share in cells:
            cell_w = round(width * share)
            d.line((x, y, x, y + height), fill=INK, width=2)
            box = 28 if label else 0
            if label:
                parts = label.split()
                d.rectangle((x + 3, y + 4, x + box - 2, y + height - 4), outline=INK, width=1)
                for n, part in enumerate(parts):
                    d.text((x + 6, y + 7 + n * 11), part, fill=INK, font=label_font)
            if value:
                font = _font(24) if value.startswith("DATUM") else value_font
                d.text((x + box + 12, y + (height - 30) // 2 + (3 if value.startswith("DATUM") else 0)), value, fill=INK, font=font)
            x += cell_w
        d.line((x0 + width, y, x0 + width, y + height), fill=INK, width=2)
        y += height
        d.line((x0, y, x0 + width, y), fill=INK, width=2)
    return y


def certificate(v: dict) -> Image.Image:
    """The flat certificate with the values of ``v``."""
    img = Image.new("RGB", PAPER, SHEET)
    d = ImageDraw.Draw(img)
    big, mid, small, tiny = _font(30), _font(34, True), _font(15), _font(11)
    # the left page: title, plate, holder (the stock sample holder), next inspection
    d.text((12, 28), "Zulassungsbescheinigung Teil I", fill=INK, font=mid)
    d.text((190, 66), "(Fahrzeugschein)", fill=INK, font=small)
    d.text((12, 100), "Nr.", fill=INK, font=small)
    d.text((120, 96), "XX-X-1-000/26-00000", fill=INK, font=_font(28, True))
    d.text((80, 150), "Europäische\nGemeinschaft", fill=INK, font=small)
    d.ellipse((215, 140, 290, 215), outline=INK, width=3)
    d.text((240, 160), "D", fill=INK, font=_font(36))
    d.text((305, 150), "Bundesrepublik\nDeutschland", fill=INK, font=small)
    for n in range(6):
        d.text((8, 202 + n * 24), "Certificate of registration. Part I / Certificat d'immatriculation. Partie I", fill=INK, font=tiny)
    d.text((16, 362), "A Amtliches Kennzeichen", fill=INK, font=tiny)
    d.rectangle((18, 376, 482, 424), outline=INK, width=2)
    d.text((165, 384), v["plate_text"], fill=INK, font=_font(34, True))
    d.text((18, 430), "C.1.1 Name oder Firmenname", fill=INK, font=tiny)
    d.text((46, 462), "Mustermann", fill=INK, font=big)
    d.text((18, 534), "C.1.2 Vorname(n)", fill=INK, font=tiny)
    d.text((46, 550), "Erika", fill=INK, font=big)
    d.text((18, 602), "C.1.3 Anschrift", fill=INK, font=tiny)
    d.text((46, 640), "Musterstraße 1\n12345 Musterstadt", fill=INK, font=big)
    d.text((18, 735), "X Nächste HU", fill=INK, font=tiny)
    d.text((18, 750), "(Monat und Jahr)", fill=INK, font=tiny)
    d.text((140, 726), v["inspection_text"], fill=INK, font=big)
    d.text((330, 768), "Musterstadt", fill=INK, font=big)
    d.text((370, 810), "01.01.2026", fill=INK, font=big)
    d.text(
        (18, 826), "C.4c Der Inhaber der Zulassungsbescheinigung\nwird nicht als Eigentümer des Fahrzeugs ausgewiesen.", fill=INK, font=tiny
    )
    d.line((513, 0, 513, PAPER[1]), fill=INK, width=2)
    # the middle and the right page: the table of numbered fields
    value_font, label_font = _font(30), _font(11)
    _table(d, MID_X, MID_W, _middle(v), 12, value_font, label_font)
    _table(d, RIGHT_X, RIGHT_W, _right(v), 12, value_font, label_font)
    for x in (1105, 1118):  # the fold between the middle and the right page
        d.line((x, 0, x, PAPER[1]), fill=INK, width=2)
    for y in range(660, PAPER[1], 38):  # the empty lines of the table down to the edge
        d.line((MID_X, y, MID_X + MID_W, y), fill=INK, width=2)
        d.line((RIGHT_X, y, RIGHT_X + RIGHT_W, y), fill=INK, width=2)
    return img


# ------------------------------------------------------------------ the photo


def photo(
    paper: Image.Image, seed: int = 1, angle: float = 1.5, size: tuple[int, int] = (2000, 1500), blur: float = 0.9, quality: int = 80
) -> bytes:
    """The certificate lying on a dark table, photographed with a phone: turned a little, an uneven light, soft, noisy, compressed."""
    rng = random.Random(seed)  # noqa: S311 (a fixed seed: the pictures look the same every time)
    # the security print of the paper: faint pink and green waves (the reason a plain threshold fails)
    wave = Image.new("L", paper.size, 0)
    wd = ImageDraw.Draw(wave)
    for y in range(0, paper.height, 5):
        wd.line([(x, y + 3 * math.sin(x / 23 + y / 17)) for x in range(0, paper.width, 12)], fill=28, width=1)
    paper = ImageChops.subtract(paper, Image.merge("RGB", (Image.new("L", paper.size, 0), wave, wave)))
    table = Image.new("RGB", size, (34, 32, 34))
    px, py = (size[0] - paper.width) // 2, (size[1] - paper.height) // 2
    turned = paper.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=(34, 32, 34))
    table.paste(turned, (px - (turned.width - paper.width) // 2, py - (turned.height - paper.height) // 2))
    # an uneven light: a bright patch from the window, darker in a corner
    light = Image.new("L", size, 0)
    ld = ImageDraw.Draw(light)
    cx, cy = rng.randint(size[0] // 5, size[0] // 2), rng.randint(size[1] // 5, size[1] // 2)
    for r in range(900, 0, -30):
        ld.ellipse((cx - r, cy - r, cx + r, cy + r), fill=int(70 * (1 - r / 900)))
    table = ImageChops.add(table, Image.merge("RGB", (light, light, light)))
    table = table.filter(ImageFilter.GaussianBlur(blur))
    noise = (
        Image.frombytes("L", size, rng.randbytes(size[0] * size[1])).point(lambda v: round(128 + (v - 127.5) * 0.19)).convert("RGB")
    )  # (from the seed: the same picture every time)
    table = ImageChops.add(table, ImageChops.subtract(noise, Image.new("RGB", size, (128, 128, 128))))
    out = io.BytesIO()
    table.save(out, "JPEG", quality=quality)
    return out.getvalue()


# ------------------------------------------------------------------ the made-up cars


def _values(**kw) -> dict:
    v = {
        "plate_text": "AB CD123",
        "first_reg_text": "15.03.2016",
        "hsn": "9999",
        "tsn_text": "XYZ00001 3",
        "class": "M1",
        "code4": "AA",
        "vin": "EXAMPLE1234567890",
        "make_text": "EXAMPLE",
        "type": "1A",
        "variant": "ABCDEF1",
        "version": "XYZ12ABC3D4E5F6GH7",
        "trade_text": "EXAMPLE T4 TOURER",
        "short": "EXAMPLE (H)",
        "class_text": "Fz.z.Pers.bef.b. 8 Spl.",
        "body_text": "Kombi",
        "emission_regs": "715/2007*692/2008F",
        "euro": "EURO6;F;PI/CI; M, N1 I",
        "fuel_text": "Diesel",
        "displacement_text": "1968",
        "power_text": "110/3500",
        "speed": "215",
        "length": "4400-4500",
        "width": "1800-1900",
        "height": "1400-1500",
        "unladen": "1450",
        "co2": "128",
        "mass": "2150",
        "seats": "5",
        "tyre": "215/55 R17 94V",
        "color_text": "Blau",
        "approval": "e1*2007/46*0000*00",
        "approval_date": "01.01.2016",
        "code16": "AB1234",
        "inspection_text": "06.2027",
    }
    v.update(kw)
    return v


CARS = {
    # the form fields the app should offer for the pass, the month of the next inspection
    "diesel-wagon": (
        _values(),
        {
            "plate": "AB-CD 123",
            "first_reg": "2016-03-15",
            "hsn": "9999",
            "tsn": "XYZ",
            "vin": "EXAMPLE1234567890",
            "make": "Example",
            "model": "T4 Tourer",
            "model_type": "1A",
            "body_type": "wagon",
            "fuel_type": "diesel",
            "displacement_ccm": "1968",
            "power_kw": "110",
            "seats": "5",
            "gross_weight_kg": "2150",
            "color": "Blau",
        },
        "2027-06",
    ),
    "petrol-hatchback": (
        _values(
            plate_text="XY Z 4567",
            first_reg_text="02.09.2019",
            hsn="8888",
            tsn_text="QRS00002 4",
            vin="SAMPLEV0987654321",
            make_text="SAMPLE",
            trade_text="SAMPLE SPARK",
            short="SAMPLE (H)",
            type="2B",
            variant="GHIJKL2",
            version="UVW34DEF5G6H7I8JK9",
            body_text="Schrägheck",
            fuel_text="Benzin",
            displacement_text="999",
            power_text="70/5000",
            seats="5",
            mass="1560",
            color_text="Rot",
            inspection_text="09.2026",
            tyre="185/65 R15 88T",
            co2="112",
            unladen="1050",
            approval_date="10.05.2019",
            code16="CD6543",
        ),
        {
            "plate": "XY-Z 4567",
            "first_reg": "2019-09-02",
            "hsn": "8888",
            "tsn": "QRS",
            "vin": "SAMPLEV0987654321",
            "make": "Sample",
            "model": "Spark",
            "model_type": "2B",
            "body_type": "hatchback",
            "fuel_type": "petrol",
            "displacement_ccm": "999",
            "power_kw": "70",
            "seats": "5",
            "gross_weight_kg": "1560",
            "color": "Rot",
        },
        "2026-09",
    ),
    "electric-suv": (
        _values(
            plate_text="MM EV 99E",
            first_reg_text="21.11.2023",
            hsn="7777",
            tsn_text="LMN00003 5",
            vin="VLTAGE75555666677",
            make_text="VOLTAGE",
            trade_text="VOLTAGE CROSS",
            short="VOLTAGE (H)",
            type="3C",
            variant="MNOPQR3",
            version="ABC56GHI7J8K9L0MNO",
            body_text="Geländewagen",
            fuel_text="Elektro",
            displacement_text="-",
            power_text="150/-",
            seats="5",
            mass="2500",
            color_text="Weiß",
            inspection_text="11.2026",
            tyre="235/55 R19 105V",
            co2="0",
            unladen="1900",
            approval_date="03.03.2023",
            code16="EF1122",
            euro="EURO6;F;EV; M, N1 I",
        ),
        {
            "plate": "MM-EV 99E",
            "first_reg": "2023-11-21",
            "hsn": "7777",
            "tsn": "LMN",
            "vin": "VLTAGE75555666677",
            "make": "Voltage",
            "model": "Cross",
            "model_type": "3C",
            "body_type": "suv",
            "fuel_type": "electric",
            "power_kw": "150",
            "seats": "5",
            "gross_weight_kg": "2500",
            "color": "Weiß",
        },
        "2026-11",
    ),
}


def for_docs(photo_bytes: bytes, margin: int = 36, width: int = 1500) -> bytes:
    """The photo as the documentation shows it: cut down to the paper and a margin of the table (no empty table around it), a little smaller."""
    img = Image.open(io.BytesIO(photo_bytes)).convert("RGB")
    box = (
        img.convert("L").point(lambda v: 255 if v > 150 else 0).getbbox()
    )  # the paper is far lighter than the table (even where the light falls on it)
    if box:
        img = img.crop(
            (max(0, box[0] - margin), max(0, box[1] - margin), min(img.width, box[2] + margin), min(img.height, box[3] + margin))
        )
    img = img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=80, optimize=True)
    return out.getvalue()


def samples(seed: int = 1) -> list[Sample]:
    out = []
    for n, (name, (values, truth, inspection)) in enumerate(CARS.items()):
        paper = certificate(values)
        flat = io.BytesIO()
        paper.save(flat, "PNG")
        out.append(Sample(name, photo(paper, seed + n, angle=(-1.8, 1.2, 0.0)[n % 3]), flat.getvalue(), truth, inspection))
    return out


# how bad the photos of the bench are: (angle in degrees, blur, JPEG quality, size of the picture)
CONDITIONS = ((-1.8, 0.9, 80, (2000, 1500)), (1.2, 1.4, 65, (2200, 1650)), (3.0, 1.0, 55, (2000, 1500)), (0.0, 0.7, 90, (1800, 1350)))


def bench(runs: int = 8) -> int:
    """Every made-up certificate ``runs`` times, each with another noise and one of the conditions; the real text recognition reads them. Prints how many fields
    were right, wrong (and of those, how many the app would have called sure) and missing, and which fields it was."""
    import time
    from collections import Counter

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "carassistant" / "app"))
    from carassistant import receipt, registration

    if not receipt.available():
        print("Tesseract is not installed - nothing to measure")
        return 2
    right, wrong, sure, missing = Counter(), Counter(), Counter(), Counter()
    total = photos = 0
    started = time.time()
    for _name, (values, truth, inspection) in CARS.items():
        paper = certificate(values)
        for n in range(runs):
            angle, blur, quality, size = CONDITIONS[n % len(CONDITIONS)]
            got = registration.scan(photo(paper, seed=100 + n, angle=angle, size=size, blur=blur, quality=quality))
            photos += 1
            for key, want in {**truth, "inspection": inspection}.items():
                total += 1
                value = got["inspection"] if key == "inspection" else got["fields"].get(key)
                if not value:
                    missing[key] += 1
                elif value == want:
                    right[key] += 1
                else:
                    wrong[key] += 1
                    sure[key] += key not in got["unsure"]
    print(f"{photos} photos read in {time.time() - started:.0f} s")
    print(
        f"right {sum(right.values())}/{total} ({100 * sum(right.values()) / total:.1f} %), wrong {sum(wrong.values())} (sure: {sum(sure.values())}), missing {sum(missing.values())}"
    )
    for title, counter in (("wrong", wrong), ("sure but wrong", sure), ("missing", missing)):
        if counter:
            print(f"  {title}: " + ", ".join(f"{key} {count}" for key, count in counter.most_common()))
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--bench"]:
        sys.exit(bench(int(sys.argv[2]) if len(sys.argv) > 2 else 8))
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "registration-samples")
    target.mkdir(parents=True, exist_ok=True)
    answers = {}
    for sample in samples():
        (target / f"{sample.name}.jpg").write_bytes(sample.data)
        (target / f"{sample.name}-clean.png").write_bytes(sample.clean)
        answers[sample.name] = {"fields": sample.truth, "inspection": sample.inspection}
    (target / "answers.json").write_text(json.dumps(answers, indent=2, ensure_ascii=False))
    print("wrote", len(answers), "certificates to", target)
