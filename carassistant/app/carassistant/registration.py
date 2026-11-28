"""Read a German registration certificate (Zulassungsbescheinigung Teil I, the "Fahrzeugschein") from a photo or a scan: text recognition on this server
(Tesseract), then a parser that picks the fields of the vehicle pass out of the text.

Nothing leaves the server: the picture is cleaned up, read and thrown away (it is never stored), and no online service is asked. The result only *fills in* the
form of the vehicle pass - what is already written there is never replaced (the page decides that); the person looks at it and saves. The holder (fields
C.1.1 to C.1.3: name and address) is not wanted and not kept: only the plate and the month of the next inspection are taken from the left page.

The certificate is a table of numbered fields (the same on every certificate of the EU): A plate, B first registration, 2.1 / 2.2 HSN and TSN, E VIN, D.1 make,
D.2 type, D.3 trade name, 5 class and body, P.1 displacement, P.2 power, P.3 fuel, S.1 seats, F.1 permitted mass, R colour, X next inspection. It is folded in
three pages that lie side by side, the vehicle's table on the middle and the right one. A photo of it is hard for a text reader (a table with ruling lines the text is
often printed onto, security print, a light that is not even), so the picture is prepared page by page: the paper cut out and straightened, the uneven light
taken out, the ruling lines removed, each page enlarged and read on its own - several times, with another size and another page layout each - and what the
readings agree on counts.

``parse`` works on plain lines of text, so it can be tested without a picture.
"""

from __future__ import annotations

import difflib
import io
import itertools
import os
import re
import subprocess
import tempfile
import time
from datetime import date

from . import receipt

MAX_BYTES = receipt.MAX_BYTES
BORDER = 10  # pixels of white around a page that is read: Tesseract does not like text at the very edge
PAPER_WIDTH = 1720  # the paper is brought to this width: the letters then have the size the recognition likes
BUDGET = 150.0  # seconds for all the readings of one certificate; what has been read by then is what counts
VARIANTS = (
    (1.6, 11, 1.0),
    (2.2, 11, 1.0),
    (3.0, 11, 0.8),
    (2.2, 12, 1.0),
    (1.6, 6, 1.0),
    (3.0, 12, 0.8),
    (1.6, 11, 1.3),
)  # (enlargement, page layout of Tesseract, strength of the ink threshold): the readings differ, what several of them agree on counts
ENOUGH = 12  # fields: from here on (and after three readings) a certificate is read well enough
TEXT_FIELDS = ("make", "model", "model_type", "color")  # words: a reading that lost a letter still counts for the others
TWICE = (
    "seats",
)  # a lone digit next to a small box is more often the code of a box than the seats: read once among three or more readings, it is not offered

FIELDS = (
    "plate",
    "make",
    "model",
    "model_type",
    "first_reg",
    "hsn",
    "tsn",
    "vin",
    "body_type",
    "fuel_type",
    "fuel2_type",
    "power_kw",
    "displacement_ccm",
    "seats",
    "gross_weight_kg",
    "color",
)  # what a certificate fills in, in the order of the form

# ------------------------------------------------------------------ the picture


def _open(data: bytes):
    from PIL import Image, ImageOps, UnidentifiedImageError

    Image.MAX_IMAGE_PIXELS = receipt.MAX_PIXELS
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError) as exc:
        raise ValueError("not an image") from exc
    return ImageOps.exif_transpose(img).convert("L")


def _otsu(img) -> int:
    """The grey level that best divides a picture in a dark and a light part (the table and the paper)."""
    hist = img.histogram()
    total = sum(hist)
    weighted = sum(i * n for i, n in enumerate(hist))
    best, best_t, below, below_sum = -1.0, 128, 0, 0
    for t in range(256):
        below += hist[t]
        below_sum += t * hist[t]
        if below == 0 or below == total:
            continue
        mean_below, mean_above = below_sum / below, (weighted - below_sum) / (total - below)
        between = below * (total - below) * (mean_below - mean_above) ** 2
        if between > best:
            best, best_t = between, t
    return best_t


def _span(values: bytes, fraction: float) -> tuple[int, int]:
    peak = max(values) or 1
    marks = [i for i, v in enumerate(values) if v >= peak * fraction]
    return (marks[0], marks[-1]) if marks else (0, len(values) - 1)


def paper(img):
    """The certificate cut out of the photo (the paper is much lighter than the table), straightened, its longer side brought to ``PAPER_WIDTH``. A flat scan
    stays as it is."""
    from PIL import Image

    small = img.copy()
    small.thumbnail((400, 400))
    cut_at = _otsu(small)
    bright = small.point(lambda v: 255 if v > cut_at else 0)
    w, h = small.size
    x0, x1 = _span(bright.resize((w, 1), Image.BOX).tobytes(), 0.4)
    y0, y1 = _span(bright.resize((1, h), Image.BOX).tobytes(), 0.4)
    k = img.width / w
    box = (round(x0 * k), round(y0 * k), round((x1 + 1) * k), round((y1 + 1) * k))
    if (box[2] - box[0]) < img.width * 0.35 or (box[3] - box[1]) < img.height * 0.2:
        box = (0, 0, img.width, img.height)  # no paper found: take the whole picture
    cut = img.crop(box)
    k = PAPER_WIDTH / max(cut.size)  # the longer side: a certificate on its side is as long as one that lies right
    cut = cut.resize((max(1, round(cut.width * k)), max(1, round(cut.height * k))), Image.LANCZOS)
    buf = io.BytesIO()
    cut.save(buf, "PNG")
    angle = receipt.skew(buf.getvalue())  # the lines of the table give a clear answer
    if angle:
        from PIL import ImageStat

        cut = cut.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=round(ImageStat.Stat(cut).mean[0]))
    return cut


def ink(img, strength: float = 1.0):
    """The writing as black on white with the uneven light taken out (the paper is compared with its surroundings), and the strength of the ink it needs."""
    from PIL import ImageChops, ImageFilter, ImageOps

    flat = ImageChops.subtract(
        img.filter(ImageFilter.GaussianBlur(round(img.width * 0.0145))), img
    )  # where the paper is darker than around it
    hist = flat.histogram()
    seen, p99 = 0, 255
    for level in range(255, -1, -1):
        seen += hist[level]
        if seen >= img.width * img.height * 0.01:
            p99 = level
            break
    threshold = min(45, max(12, round(p99 * 0.2 * strength)))
    return ImageOps.invert(flat.point(lambda v: 255 if v > threshold else 0))


def _dark(binary, axis: int) -> list[float]:
    """The share of ink in every column (axis 0) or row (axis 1) of a black-and-white picture."""
    from PIL import Image

    size = (binary.width, 1) if axis == 0 else (1, binary.height)
    return [1 - v / 255 for v in binary.resize(size, Image.BOX).tobytes()]


def _runs(flags: list[bool]) -> list[tuple[int, int]]:
    out, start = [], None
    for i, flag in enumerate([*flags, False]):
        if flag and start is None:
            start = i
        if not flag and start is not None:
            out.append((start, i))
            start = None
    return out


def pages(binary) -> dict[str, tuple[int, int]]:
    """Where the three pages of the folded certificate are: the folds are tall dark lines at about a third and two thirds of the width. When they are not found
    the usual places are taken."""
    w = binary.width
    marks = [(a + b) / 2 for a, b in _runs([f >= 0.5 for f in _dark(binary, 0)]) if b - a <= 40]

    def near(lo: float, hi: float, usual: float) -> int:
        inside = [m for m in marks if lo * w <= m <= hi * w]
        return round(min(inside, key=lambda m: abs(m - usual * w))) if inside else round(usual * w)

    first, second = near(0.22, 0.38, 0.30), near(0.55, 0.74, 0.645)
    return {"left": (0, first - 6), "mid": (first + 6, second - 6), "right": (second + 6, w)}


def level(page):
    """The page turned a little so that its ruling lines run exactly across: the perspective of a photo makes every page of the certificate lean by its own
    angle, and a line that is not level cannot be taken out. The right angle is the one at which the rows of ink are the most uneven (lines and text rows
    on one side, white gaps on the other)."""
    from PIL import Image

    small = page.resize((max(1, page.width // 2), max(1, page.height // 2)), Image.BOX)

    def score(angle: float) -> float:
        return sum(share * share for share in _dark(small.rotate(angle, resample=Image.BILINEAR, fillcolor=255), 1))

    best = max((a / 2 for a in range(-8, 9)), key=score)  # -4 to 4 degrees, every half degree
    best = max((best + a / 10 for a in range(-4, 5)), key=score)  # then every tenth around it
    return page if abs(best) < 0.15 else page.rotate(best, resample=Image.BICUBIC, fillcolor=255)


def clean_page(page, hfrac: float = 0.5, vfrac: float = 0.55):
    """A page without its ruling lines (rows and columns that are almost all ink) and without the specks of the paper."""
    from PIL import ImageFilter

    out = page.copy()
    px = out.load()
    w, h = out.size
    for y, share in enumerate(_dark(page, 1)):
        if share >= hfrac:
            for row in range(max(0, y - 1), min(h, y + 2)):
                for x in range(w):
                    px[x, row] = 255
    for x, share in enumerate(_dark(page, 0)):
        if share >= vfrac:
            for col in range(max(0, x - 1), min(w, x + 2)):
                for y in range(h):
                    px[col, y] = 255
    return out.filter(ImageFilter.MedianFilter(3))


# ------------------------------------------------------------------ the text of the pages


def _words(img, scale: float, psm: int) -> list[dict]:
    """The words Tesseract finds, with their boxes (in the pixels of ``img``). [] on any failure - it never raises."""
    from PIL import Image, ImageOps

    big = ImageOps.expand(img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS), border=BORDER, fill=255)
    with tempfile.TemporaryDirectory(prefix="ca-registration-") as tmp:
        path = os.path.join(tmp, "p.png")
        big.save(path)
        try:
            run = subprocess.run(  # noqa: S603 (a fixed program, a file of our own and fixed options)
                [receipt._binary() or "tesseract", path, "stdout", "-l", "+".join(receipt.languages()), "--psm", str(psm), "tsv"],
                capture_output=True,
                text=True,
                timeout=receipt.TIMEOUT,
                env={**os.environ, "OMP_THREAD_LIMIT": "1"},
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return []
    if run.returncode != 0:
        return []
    words = []
    for line in run.stdout.splitlines()[1:]:
        cols = line.split("\t")
        if len(cols) == 12 and cols[11].strip():
            try:
                words.append(
                    {
                        "x": (int(cols[6]) - BORDER) / scale,
                        "y": (int(cols[7]) - BORDER) / scale,
                        "w": int(cols[8]) / scale,
                        "h": int(cols[9]) / scale,
                        "t": cols[11].strip(),
                    }
                )
            except ValueError:
                continue
    return words


def rows(words: list[dict]) -> list[str]:
    """The words put into rows by their height on the page, each row left to right; words far apart (the cells of the table) are divided by ' | '."""
    words = [w for w in words if w["h"] > 6]
    if not words:
        return []
    heights = sorted(w["h"] for w in words)
    unit = heights[len(heights) // 2]
    lines: list[list[dict]] = []
    for word in sorted(words, key=lambda w: w["y"] + w["h"] / 2):
        centre = word["y"] + word["h"] / 2
        if lines and abs(lines[-1][0] - centre) < unit * 0.6:
            lines[-1][1].append(word)
            lines[-1][0] = (lines[-1][0] + centre) / 2
        else:
            lines.append([centre, [word]])
    out = []
    for _centre, items in lines:
        items.sort(key=lambda w: w["x"])
        text = items[0]["t"]
        for before, word in itertools.pairwise(items):
            text += (" | " if word["x"] - (before["x"] + before["w"]) > unit * 2.2 else " ") + word["t"]
        out.append(text)
    return out


# ------------------------------------------------------------------ the parser

COLOURS = {
    "grau": "Grau", "silber": "Silber", "schwarz": "Schwarz", "weiss": "Weiß", "weiß": "Weiß", "weib": "Weiß", "wei8": "Weiß", "weis": "Weiß", "blau": "Blau", "rot": "Rot", "gruen": "Grün", "grün": "Grün",
    "gelb": "Gelb", "braun": "Braun", "beige": "Beige", "orange": "Orange", "violett": "Violett", "gold": "Gold", "bronze": "Bronze", "rosa": "Rosa",
    "tuerkis": "Türkis", "türkis": "Türkis", "lila": "Lila",
}  # fmt: skip
BODIES = {
    "limousine": "sedan", "stufenheck": "sedan", "kombi": "wagon", "kombilimousine": "wagon", "schrägheck": "hatchback", "schraegheck": "hatchback",
    "fließheck": "hatchback", "fliessheck": "hatchback", "steilheck": "hatchback", "coupé": "coupe", "coupe": "coupe", "cabriolet": "convertible",
    "cabrio": "convertible", "roadster": "convertible", "geländewagen": "suv", "gelaendewagen": "suv", "suv": "suv", "kastenwagen": "van", "kleinbus": "van",
    "van": "van", "grossraumlimousine": "van", "großraumlimousine": "van", "pritsche": "pickup", "pickup": "pickup",
}  # fmt: skip
FUELS = {
    "benzin": "petrol", "super": "petrol", "diesel": "diesel", "elektro": "electric", "strom": "electric", "erdgas": "cng", "cng": "cng", "flüssiggas": "lpg",
    "fluessiggas": "lpg", "autogas": "lpg", "lpg": "lpg", "hybrid": "hybrid",
}  # fmt: skip
DASH = str.maketrans({"–": "-", "—": "-", "_": "-"})
BOXES = "[](){}|!'\"`´‘’“”,;:_<>«»"  # what the small boxes of the field codes leave glued to a value
EDGES = BOXES + "*~°•·^\\"  # ... and to a word
LABELS = re.compile(r"k[eo]nn?z|amtliches", re.I)
DATE = r"(?:[0-3]?\d)\s?[.,:]\s?(?:[01]?\d)\s?[.,:]\s?(?:19|20)\d\d"
DOTTED = re.compile(r"^(?:[A-Z]{1,2}\.\d(?:\.\d)?|\d{1,2}\.\d)$")  # the code of a field written out: D.1, P.3, 2.1
TYRE = re.compile(r"(?<!\d)\d{3}\s?/\s?\d{2}(?!\d)")  # 185/65 (R15 88T): the size of the tyre, however badly the rest was read
RANGE = re.compile(r"\d{3,4}\s?[-–—]+\s?\d{0,4}")  # 4400-4500, 1315--: the measures of the page, no weights to take


def _tokens(line: str) -> list[str]:
    return [t for t in re.split(r"[\s|]+", line) if t]


def _words_of(line: str) -> list[str]:
    """The words of a row without what the small code boxes leave behind: a bracket glued to a word, the code itself (D.1, P.3), a few small letters that
    are the code of the box read as text, a single capital letter at the start (E, J, X: also a code)."""
    out: list[str] = []
    tokens = _tokens(line)
    for n, raw in enumerate(tokens):
        word = raw.strip(EDGES)
        if not re.search(r"[A-Za-zÄÖÜäöüß0-9]", word) or DOTTED.match(word):
            continue
        letters = re.sub(r"[^A-Za-zÄÖÜäöüß]", "", word)
        if len(word) <= 3 and letters and not letters.isupper():
            continue  # aa, Aa, Aaa
        if n == 0 and len(word) == 1 and len(tokens) > 1:
            continue
        out.append(word)
    return out


def _same(a: str, b: str, cutoff: float = 0.8) -> bool:
    return difflib.SequenceMatcher(None, a.upper(), b.upper()).ratio() >= cutoff


def _close(token: str, table: dict[str, str], cutoff: float = 0.8) -> str | None:
    word = re.sub(r"[^a-zäöüß]", "", token.lower())
    if len(word) < 3:
        return None
    hit = difflib.get_close_matches(word, list(table), n=1, cutoff=cutoff)
    return table[hit[0]] if hit else None


def _digits(text: str) -> str:
    """Letters that a text reader takes for digits in a place where only digits are: O, I, l, S, B, Z."""
    return text.translate(str.maketrans("OoQDIl|SBZ", "0000111582"))


def _date(text: str) -> date | None:
    for found in re.finditer(
        r"(?<![\d.])([0-3OoIl]?[0-9OoIlSB])\s?[.,:]\s?([01OoIl]?[0-9OoIlSB])\s?[.,:]\s?((?:19|20)[0-9OoIlSB]{2})(?!\d)", text
    ):
        try:
            return date(int(_digits(found[3])), int(_digits(found[2])), int(_digits(found[1])))
        except ValueError:
            continue
    return None


def _title(word: str) -> str:
    if len(word) <= 3 or any(c.isdigit() for c in word):
        return word.upper()
    return "-".join(part.capitalize() for part in word.split("-"))


def _plate(lines: list[str]) -> str | None:
    """The plate: the line below 'Amtliches Kennzeichen' (a district of one to three letters, one or two letters, the digits, E or H for an electric or historic car)."""
    start = next((i for i, line in enumerate(lines) if LABELS.search(line)), -1)
    for line in lines[start + 1 : start + 4] if start >= 0 else lines:
        text = re.sub(r"[\[\]|_{}()!]", " ", line).upper().strip()
        if "/" in text or len(text) > 14:
            continue  # the number of the document has slashes
        found = re.fullmatch(r"([A-ZÄÖÜ]{1,3})[\s.\-:]+([A-Z]{1,2})[\s.\-:]*(\d{1,4})\s?([EH])?", text)
        if found:
            return f"{found[1]}-{found[2]} {found[3]}{found[4] or ''}"
    return None


def _vin(lines: list[str]) -> tuple[str | None, int, int]:
    """A VIN: 17 letters and digits (never I, O, Q); the ones with a serial of digits at the end are the likelier. -> (VIN, how well it looks like one, line).
    A small l or o in the text of capitals is a 1 or a 0 that was misread; the code E of the box may be glued to the front of it."""
    best: tuple[int, str, int] | None = None
    for at, line in enumerate(lines):
        tokens = re.findall(r"[A-Za-z0-9]+", line.translate(str.maketrans("lo", "10")).upper())
        pieces = [
            *tokens,
            *(a + b for a, b in itertools.pairwise(tokens)),
            *(a + b + c for a, b, c in zip(tokens, tokens[1:], tokens[2:], strict=False)),
        ]
        for piece in pieces:
            for text in (piece, piece[1:] if piece[:1] == "E" else ""):
                text = text.translate(str.maketrans("OIQ", "010"))
                if len(text) != 17 or not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", text):
                    continue
                score = (
                    1 + (2 if text[-6:].isdigit() else 0) + (1 if piece == text else 0) + (1 if sum(c.isalpha() for c in text) >= 4 else 0)
                )
                if best is None or score > best[0]:
                    best = (score, text, at)
    return (best[1], best[0], best[2]) if best else (None, 0, -1)


LOOKALIKES = str.maketrans(
    {"¥": "Y", "€": "E", "£": "E", "§": "S", "©": "C", "®": "R", "¢": "C"}
)  # a symbol that stands for a letter in a word of capitals
EMISSION = re.compile(r"MISSION|EMISS")  # the row "22 DATUM ZUR EMISSIONSKLASSE: 15.03.2016" (however badly it was read)


def _year_of_cars(when: date | None) -> bool:
    return when is not None and 1950 <= when.year <= date.today().year + 1


def _rest_of_a_date(words: list[str], n: int) -> bool:
    """The year of a date whose dots were lost (21 11 2023): a day and a month stand in front of it, so it is no HSN."""
    return bool(re.fullmatch(r"(?:19|20)\d\d", words[n])) and n >= 2 and all(re.fullmatch(r"\d{1,2}", w) for w in words[n - 2 : n])


def _first_row(lines: list[str], vin_at: int) -> dict[str, str]:
    """B first registration, 2.1 the HSN (four digits) and 2.2 the TSN (three letters or digits, a letter among them) stand in the first row of the page. A row
    whose date was not read still counts when both of the others were."""
    for line in lines[: vin_at if vin_at > 0 else 4][:4]:
        if EMISSION.search(line.upper()):
            continue
        when = _date(line)
        words = _words_of(re.sub(DATE, " ", line))
        hsn = next((w for n, w in enumerate(words) if re.fullmatch(r"\d{4}", w) and not _rest_of_a_date(words, n)), None)
        tsn = next((w for w in words if re.fullmatch(r"(?=[A-Z0-9]{0,2}[A-Z])[A-Z0-9]{3,}", w)), None)
        if not _year_of_cars(when) and not (hsn and tsn):
            continue
        out = {"first_reg": when.isoformat()} if _year_of_cars(when) else {}
        if hsn:
            out["hsn"] = hsn
        if tsn:
            out["tsn"] = tsn[:3]
        return out
    return {}


def _emission_date(lines: list[str]) -> str | None:
    """The date of the emission class: on most certificates the day of the first registration again - a second reading of the same date."""
    for line in lines:
        when = _date(line)
        if EMISSION.search(line.upper()) and _year_of_cars(when):
            return when.isoformat()
    return None


def _starts_with(words: list[str], make: str) -> int | None:
    """Where the make (one word or more) stands among the first words of a row: its place, or None."""
    n = len(make.split())
    return next((i for i in range(min(3, len(words))) if _same(" ".join(words[i : i + n]), make)), None)


def _make_and_model(lines: list[str], vin_at: int) -> dict[str, str]:
    """D.1 make (the first line of capital letters under the VIN), D.2 type (a short code under it), D.3 trade name (the line above the short name of the
    maker, which ends in '(H)'). The make comes back in the trade name and in the short name: that is how it is told from the codes around it."""
    out: dict[str, str] = {}
    start = vin_at + 1
    candidates: list[tuple[int, str]] = []
    for at in range(start, min(len(lines), start + 4)):
        words = _words_of(lines[at])
        capitals = [w for w in words if re.fullmatch(r"[A-ZÄÖÜ][A-ZÄÖÜ\-]{1,19}", w)]
        if capitals:  # the row holds nothing but capital words (a make of two words: LAND ROVER), or the first one is the make
            candidates.append((at, " ".join(capitals[:3]) if len(capitals) == len(words) else capitals[0]))
    make_at, make = -1, ""
    for at, word in candidates:
        if any(_starts_with(_words_of(later), word) is not None for later in lines[at + 1 : at + 9]):
            make_at, make = at, word
            break
    if not make and candidates and len(candidates[0][1]) >= 3:
        make_at, make = candidates[0]
    if not make:
        return out
    out["make"] = " ".join(_title(w) for w in make.split())
    short_at = next(
        (
            i
            for i in range(make_at + 1, min(len(lines), make_at + 10))
            if re.search(r"\(\s?[A-Za-z]{0,2}\s?\)\s*$|\b[A-Za-z]{1,2}\)\s*$", lines[i])
        ),
        -1,
    )
    type_at = make_at
    for at in range(make_at + 1, min(len(lines), short_at if short_at > 0 else make_at + 4)):
        words = _words_of(lines[at])
        if len(words) == 1 and re.fullmatch(r"[A-Z0-9/\-]{2,5}", words[0]) and not _same(words[0], make, 0.9):
            out["model_type"] = words[0]  # the first short code under the make
            type_at = at
            break
    trade = ""
    if short_at > 0:
        for at in range(short_at - 1, type_at, -1):  # the trade name stands under the type, the variant and the version
            words = _words_of(lines[at])
            if not words:
                continue
            single = len(words) == 1
            if single and (len(words[0]) >= 9 or (len(words[0]) >= 6 and re.search(r"\d", words[0]) and re.search(r"[A-Z]", words[0]))):
                continue  # the version and the variant are long codes, no names
            trade = " ".join(words)
            break
    if trade:
        words = trade.split()
        hit = _starts_with(words, make)
        if hit is not None:
            words = words[hit + len(make.split()) :]  # the make (and the code of the box in front of it) is not part of the model
        if words:
            out["model"] = " ".join(_title(w) for w in words)
    return out


def _engine(lines: list[str]) -> dict[str, str]:
    """P.3 fuel (a word close enough to a fuel; two words of the list are a bi-fuel or a hybrid car), P.1 displacement (the last number of the row below)."""
    out: dict[str, str] = {}
    fuels: set[str] = set()
    fuel_at = -1
    for i, line in enumerate(lines):
        for token in re.split(r"[\s|/;,+]+", line):
            kind = _close(token, FUELS, 0.78) if 4 <= len(token) <= 12 else None
            if kind:
                fuels.add(kind)
                fuel_at = i if fuel_at < 0 else fuel_at
    if fuels:
        petrol_or_diesel = [k for k in ("petrol", "diesel") if k in fuels]
        if "hybrid" in fuels or ("electric" in fuels and petrol_or_diesel):
            out["fuel_type"] = "hybrid"
        elif petrol_or_diesel:
            out["fuel_type"] = petrol_or_diesel[0]
            gas = [k for k in ("lpg", "cng") if k in fuels]
            if gas:
                out["fuel2_type"] = gas[0]
        else:
            out["fuel_type"] = sorted(fuels)[0]
    if fuel_at >= 0 and out.get("fuel_type") != "electric":
        for line in lines[fuel_at + 1 : fuel_at + 3]:
            words = [w.strip(EDGES) for w in _tokens(line.translate(DASH))]
            numbers = [t for t in words if re.fullmatch(r"\d{3,5}", t)]
            if (
                words and words[-1] != "-" and len(numbers) >= 2 and 400 <= int(numbers[-1]) <= 12000
            ):  # a dash in the last cell: no displacement
                out["displacement_ccm"] = str(int(numbers[-1]))
                break
    return out


def _body(lines: list[str]) -> str | None:
    """The word of the body (Kombi, Schrägheck, ...) under the class of the vehicle."""
    for line in lines:
        for token in re.split(r"[\s|]+", line):
            kind = _close(token, BODIES, 0.84) if len(token) >= 3 else None
            if kind:
                return kind
    return None


def _power(lines: list[str]) -> str | None:
    """P.2 power over the revolutions (110/3500): in the first rows of the right page. The numbers of the regulations on the middle page (715/2007*692/2008)
    are no power."""
    for line in lines[:6]:
        found = re.search(r"(?<![\d/*°.])(\d{2,3})\s?/\s?(\d{3,5}|[-–—]+)(?![\d/*°A-Za-z.])", line.translate(DASH))
        if found and 20 <= int(found[1]) <= 1000 and (found[2].startswith("-") or 800 <= int(found[2]) <= 20000):
            return str(int(found[1]))
    return None


def _mass(lines: list[str]) -> str | None:
    """F.1 and F.2, the permitted mass, are in one row: twice the same number (or nearly), after the CO2 value. When only one of them was read, it is the last
    number of the row and the first number (the CO2 value) is small."""
    for line in lines:
        if RANGE.search(line.translate(DASH)):
            continue  # the measures above them: 4400-4500, 1315--
        numbers = [int(t) for t in (w.strip(EDGES) for w in _tokens(line)) if re.fullmatch(r"\d{3,5}", t)]
        if len(numbers) >= 2 and 500 <= numbers[-2] <= 99999 and abs(numbers[-1] - numbers[-2]) <= max(numbers[-2], numbers[-1]) * 0.1:
            return str(numbers[-2])
        if len(numbers) >= 2 and numbers[0] < 500 <= numbers[-1] <= 99999:
            return str(numbers[-1])
    return None


def _seats(lines: list[str], tyre_at: int) -> str | None:
    """S.1 the seats: a single digit of its own in the row above the tyres (O.1, O.2, S.1, S.2: the others are dashes). Without tyres: in a row of dashes."""
    dashes = [line for line in lines if sum(1 for t in _tokens(line.translate(DASH)) if t.strip(BOXES) == "-") >= 2]
    for line in [lines[tyre_at - 1]] if tyre_at > 0 else dashes:
        kept = [
            t.strip(BOXES) for t in _tokens(line.translate(DASH)) if not re.fullmatch(r"[\[{(]\w{1,2}[\]})]", t)
        ]  # a whole box in brackets is a code
        digits = [t for t in kept if re.fullmatch(r"[1-9]", t)]
        if len(digits) == 1 and not any(re.fullmatch(r"\d{2,}", t) for t in kept):
            return digits[0]
    return None


def _colour(lines: list[str]) -> str | None:
    for line in lines:
        kind = next((c for c in (_close(t, COLOURS, 0.8) for t in re.split(r"[\s|/]+", line) if 3 <= len(t) <= 12) if c), None)
        if kind:
            return kind
    return None


def _right_page(lines: list[str]) -> dict[str, str]:
    """The third page: P.2 power, F.1 / F.2 the permitted mass, S.1 the seats and R the colour."""
    tyre_at = next((i for i, line in enumerate(lines) if TYRE.search(line)), -1)
    found = {
        "power_kw": _power(lines),
        "gross_weight_kg": _mass(lines[: tyre_at if tyre_at > 0 else len(lines)]),
        "seats": _seats(lines, tyre_at),
        "color": _colour(lines),
    }
    return {key: value for key, value in found.items() if value}


def _inspection(lines: list[str]) -> str:
    """X next inspection: month and year (09.2026), not the date of issue (which has a day in front)."""
    for line in lines:
        found = re.search(r"(?<![\d.])(0?[1-9]|1[0-2])\s?[.,]\s?(20\d{2})(?![\d.])", line)
        if found:
            return f"{found[2]}-{int(found[1]):02d}"
    return ""


def parse(pages_: dict[str, list[str]]) -> dict:
    """The lines of the pages (``left``, ``mid``, ``right``; or ``all`` when the pages could not be told apart) -> what the certificate says:
    ``{"fields": {...}, "inspection": "2027-06" or ""}``. Only what is clearly there is in it."""
    pages_ = {name: [line.translate(LOOKALIKES) for line in lines] for name, lines in pages_.items()}
    left, mid, right = pages_.get("left", []), pages_.get("mid", []), pages_.get("right", [])
    if "all" in pages_:
        left = mid = right = pages_["all"]
    mid = mid or [*left, *right]
    out: dict[str, str] = {}
    if plate := _plate(left or mid):
        out["plate"] = plate
    vin, vin_score, vin_at = _vin(mid)
    if vin:
        out["vin"] = vin
    out.update(_first_row(mid, vin_at))
    if vin_at >= 0:
        out.update(_make_and_model(mid, vin_at))
    out.update(_engine(mid))
    if body := _body(mid):
        out["body_type"] = body
    out.update(_right_page(right))
    alt = {"first_reg": when} if (when := _emission_date(mid)) else {}
    return {"fields": out, "inspection": _inspection(left), "vin_score": vin_score, "alt": alt}


def _vote(values: list[str], weights: list[float]) -> str:
    """The value most of the readings agree on. Words that are alike (one lost letter) belong together; of such a group the value met most often wins, and
    of two equally often met the longer one (a letter lost is the usual mistake)."""
    groups: list[list[int]] = []
    for n, value in enumerate(values):
        for group in groups:
            if _same(value, values[group[0]], 0.75):
                group.append(n)
                break
        else:
            groups.append([n])
    best = max(groups, key=lambda g: (sum(weights[n] for n in g), -g[0]))
    counted: dict[str, float] = {}
    for n in best:
        counted[values[n]] = counted.get(values[n], 0) + weights[n]
    return max(counted, key=lambda v: (counted[v], len(v)))


def merge(readings: list[dict]) -> dict:
    """Several readings of the same certificate -> one: for every field the value most of them agree on (the first one when they do not agree). A VIN counts by
    how well it looks like one. A field that only ONE reading found is ``unsure`` (a single digit misread would not be noticed): the page marks it differently.
    The date of the emission class is a second reading of the first registration (it counts for the vote, and for the agreement when the date itself was read)."""
    out: dict[str, str] = {}
    unsure: list[str] = []
    for field in FIELDS:
        evidence: list[tuple[str, float, bool]] = []  # (value, weight, read from the field itself)
        for n, reading in enumerate(readings):
            if value := reading["fields"].get(field):
                evidence.append((value, 1 + (reading.get("vin_score", 0) * 0.1 if field == "vin" else 0) - n * 0.001, True))
            if alt := reading.get("alt", {}).get(field):
                evidence.append((alt, 0.6 - n * 0.001, False))
        if not evidence:
            continue
        values, weights = [e[0] for e in evidence], [e[1] for e in evidence]
        if field in TEXT_FIELDS:
            winner = _vote(values, weights)
        else:
            votes: dict[str, float] = {}
            for value, weight in zip(values, weights, strict=True):
                votes[value] = votes.get(value, 0) + weight
            winner = max(votes, key=votes.get)
        agreeing = [e for e in evidence if e[0] == winner or (field in TEXT_FIELDS and _same(e[0], winner, 0.75))]
        own = sum(1 for e in agreeing if e[2])
        once = own + (len(agreeing) - own if own else 0) < 2 and len(readings) >= 2
        if once and field in TWICE and len(readings) >= 3:
            continue  # (not even as a guess)
        out[field] = winner
        if once:
            unsure.append(field)
    months: dict[str, int] = {}
    for reading in readings:
        if reading["inspection"]:
            months[reading["inspection"]] = months.get(reading["inspection"], 0) + 1
    month = max(months, key=months.get) if months else ""
    if month and months[month] < 2 and len(readings) >= 2:
        unsure.append("inspection")
    return {"fields": out, "inspection": month, "unsure": unsure}


# ------------------------------------------------------------------ the whole certificate


def read_once(page, variant: tuple[float, int, float]) -> dict:
    """ONE reading of the page as it lies: the three pages cut apart, each read (``variant``), the rows parsed."""
    scale, psm, strength = variant
    binary = ink(page, strength)
    texts = {
        name: rows(_words(clean_page(level(binary.crop((x0, 0, x1, binary.height)))), scale, psm))
        for name, (x0, x1) in pages(binary).items()
    }
    return parse(texts)


WEIGHT = {
    "plate": 2,
    "first_reg": 2,
    "fuel_type": 2,
    "body_type": 2,
    "power_kw": 1.5,
    "color": 1.5,
    "displacement_ccm": 1,
    "gross_weight_kg": 1,
    "make": 1,
    "vin": 1,
    "hsn": 1,
    "tsn": 1,
    "seats": 0.5,
    "model": 0.5,
    "model_type": 0.5,
}  # fmt: skip  - how much a field says that a page was read the right way up: a fuel, a body or a date is a word or a number that gibberish rarely makes
SURE_ENOUGH = 8  # a reading with this much is the right way up; below it the other ways of turning the page are tried too


def _score(reading: dict) -> float:
    return sum(WEIGHT.get(k, 0) for k in reading["fields"])


def upright(page, variant: tuple[float, int, float]) -> tuple:
    """The page turned the way it is read, and its first reading. A certificate is wider than high: one that is higher than wide lies on its side (a scan, a
    photo without a note of the camera's position), so both ways of turning it are tried; one that is wide but gives little may be upside down. The way that
    gives the better reading stays (upside down, the text recognition makes gibberish - with an odd word or a long string among it, so the fields are weighed:
    see ``WEIGHT``)."""
    wide = page.width >= page.height * 0.9
    best, reading = None, None
    for candidate in [page] if wide else [page.rotate(90, expand=True), page.rotate(270, expand=True)]:
        got = read_once(candidate, variant)
        if reading is None or _score(got) > _score(reading):
            best, reading = candidate, got
    if wide and _score(reading) < SURE_ENOUGH:
        flipped = page.rotate(180, expand=True)
        got = read_once(flipped, variant)
        if _score(got) > _score(reading):
            best, reading = flipped, got
    return best, reading


def scan(data: bytes) -> dict:
    """A photo or a scan of a certificate -> ``{"fields": {...}, "found": [...], "unsure": [...], "inspection": "", "readings": n}``: what the certificate says,
    in the order of the form; ``unsure`` names the fields that only one reading found. ValueError for a file that is no picture; an empty result when nothing
    could be read."""
    if len(data) > MAX_BYTES:
        raise ValueError("too large")
    page = paper(_open(data))
    started = time.monotonic()
    with receipt._one_at_a_time:
        page, first = upright(page, VARIANTS[0])
        readings = [first]
        for variant in VARIANTS[1:]:
            merged = merge(readings)
            enough = len(readings) >= 3 and len(merged["fields"]) >= ENOUGH and len(merged["unsure"]) <= 2
            nothing = len(readings) >= 2 and not merged["fields"]  # no certificate in the picture: no reason to try the other ways
            if enough or nothing or time.monotonic() - started > BUDGET:
                break
            readings.append(read_once(page, variant))
    merged = merge(readings)
    merged["found"] = [k for k in FIELDS if k in merged["fields"]]
    merged["readings"] = len(readings)
    return merged


def scan_pdf(data: bytes) -> dict:
    """A certificate as a PDF (a scan): the picture on its first pages. An empty result when there is none."""
    from . import invoice

    best = {"fields": {}, "found": [], "unsure": [], "inspection": "", "readings": 0}
    try:
        pictures = invoice.pdf_pictures(data, pages=2, limit=2)
    except Exception:
        pictures = []
    for picture in pictures:
        try:
            got = scan(picture)
        except ValueError:
            continue
        if len(got["found"]) > len(best["found"]):
            best = got
    return best


def scan_file(data: bytes) -> dict:
    """A photo or a PDF. ValueError for a file that is neither."""
    if data[:5] == b"%PDF-":
        if len(data) > MAX_BYTES:
            raise ValueError("too large")
        return scan_pdf(data)
    return scan(data)
