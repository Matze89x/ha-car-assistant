"""Fill-ups from a CSV file of another app (Fuelio, Spritmonitor, a spreadsheet ...): read the file, guess which column means what, convert and check
every row - and only when the person has looked at the result are the rows written to the fuel log (the pages are in ``fuelimport_web.py``).

Nothing is stored before the last step. The file is read here and thrown away afterwards; only the columns the person assigned are used, and every row is
checked like a row typed into the form (a date, an amount above zero, numbers that are numbers). A row that is already in the log (the same day and the
same amount, or the same odometer) is skipped, so the same file can be imported twice without doubling anything.

Fuelio writes several tables into one file (``## Vehicle``, ``## Log`` ...): the vehicle table tells the units and the date format, the log table holds
the fill-ups. Any other file is one table with a header row; the delimiter (comma, semicolon, tab) and the encoding are found out.
"""

from __future__ import annotations

import csv
import io
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 20_000
MAX_PROBLEMS = 50
TARGETS = ("date", "amount", "odometer_km", "price_total", "price_per_unit", "full_tank", "station", "notes")
REQUIRED = ("date", "amount")
MILE_KM = 1.609344
GALLON_L = {"usgal": 3.785411784, "ukgal": 4.54609}
ORDERS = ("ymd", "dmy", "mdy")


class FileError(ValueError):
    """A file that cannot be imported: ``key`` is the i18n key of what to tell the person."""

    def __init__(self, key: str):
        super().__init__(key)
        self.key = key


@dataclass
class Table:
    columns: list[str]
    rows: list[list[str]]
    delimiter: str = ","
    section: str = ""
    meta: dict = field(
        default_factory=dict
    )  # what the file says about itself: "dist" (km / mi), "vol" (l / usgal / ukgal), "order" (ymd / dmy / mdy)


@dataclass
class Result:
    rows: list[dict] = field(default_factory=list)  # the entries to write, in the units that are stored
    duplicates: int = 0  # rows that are in the log already
    problems: list[tuple[int, str, str]] = field(default_factory=list)  # (row of the table, i18n key, the value that was not understood)
    problem_count: int = 0
    read: int = 0
    order: str = ""  # the date order that was used


# ------------------------------------------------------------------ the file


def decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")  # never fails


_SECTION = re.compile(r'^\s*"?##\s*([A-Za-z][A-Za-z ]*?)"?\s*[,;]*\s*$')


def _sections(text: str) -> list[tuple[str, list[str]]]:
    """``(name, lines)`` of every part of the file: Fuelio starts its tables with a line ``## Name``; a file without them is one part with no name."""
    out: list[tuple[str, list[str]]] = []
    name, lines = "", []
    for line in text.splitlines():
        found = _SECTION.match(line)
        if found:
            out.append((name, lines))
            name, lines = found.group(1).strip(), []
        else:
            lines.append(line)
    out.append((name, lines))
    return [(n, [x for x in ls]) for n, ls in out if any(x.strip() for x in ls)]


def _delimiter(lines: list[str]) -> str:
    sample = "\n".join(lines[:6])
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        head = next((x for x in lines if x.strip()), "")
        counts = {d: head.count(d) for d in ",;\t|"}
        best = max(counts, key=lambda d: counts[d])
        return best if counts[best] else ","


def _rows(lines: list[str], delimiter: str) -> list[list[str]]:
    try:
        parsed = list(csv.reader(io.StringIO("\n".join(lines)), delimiter=delimiter))
    except csv.Error:
        raise FileError("fuelimport.err_format") from None
    return [[cell.strip() for cell in row] for row in parsed if any(cell.strip() for cell in row)]


def _meta(sections: list[tuple[str, list[str]]]) -> dict:
    """What the vehicle table of a Fuelio file says: the units and the order of the date."""
    out: dict = {}
    for name, lines in sections:
        if name.lower() != "vehicle":
            continue
        rows = _rows(lines, ",")
        if len(rows) < 2:
            continue
        info = {k.lower(): v for k, v in zip(rows[0], rows[1], strict=False)}
        dist = info.get("distunit", "").lower()
        if dist:
            out["dist"] = "mi" if dist.startswith("mi") else "km"
        fuel = info.get("fuelunit", "").lower()
        if fuel:
            out["vol"] = "usgal" if ("us" in fuel and "gal" in fuel) else ("ukgal" if "gal" in fuel else "l")
        shape = info.get("importcsvdateformat", "")
        if shape:
            out["order"] = {"y": "ymd", "d": "dmy", "M": "mdy"}.get(shape[:1], "")
    return {k: v for k, v in out.items() if v}


def read(data: bytes) -> Table:
    """The table of fill-ups in a file. ``FileError`` (with the text to show) for a file that is empty, too big, no text or has no table."""
    if not data.strip():
        raise FileError("fuelimport.err_empty")
    if len(data) > MAX_BYTES:
        raise FileError("fuelimport.err_size")
    if b"\x00" in data[:4096]:
        raise FileError("fuelimport.err_binary")
    sections = _sections(decode(data))
    if not sections:
        raise FileError("fuelimport.err_empty")
    meta = _meta(sections)
    named = [s for s in sections if s[0].lower() == "log"]
    pool = named or [s for s in sections if s[0].lower() != "vehicle"] or sections
    name, lines = max(pool, key=lambda s: len(s[1]))
    delimiter = _delimiter(lines)
    rows = _rows(lines, delimiter)
    start = next((i for i, row in enumerate(rows) if sum(1 for c in row if c) >= 2), None)
    if start is None or len(rows) - start < 2:
        raise FileError("fuelimport.err_columns")
    header, body = rows[start], rows[start + 1 :]
    if len(body) > MAX_ROWS:
        raise FileError("fuelimport.err_rows")
    seen: dict[str, int] = {}
    columns: list[str] = []
    for n, title in enumerate(header, 1):
        title = title or f"#{n}"
        seen[title] = seen.get(title, 0) + 1
        columns.append(title if seen[title] == 1 else f"{title} ({seen[title]})")
    width = len(columns)
    return Table(columns, [(row + [""] * width)[:width] for row in body], delimiter, name, meta)


# ------------------------------------------------------------------ which column is what

_PATTERNS: dict[str, tuple[str, ...]] = {  # the name of a column, without what stands in brackets, in lower case
    "date": (r"^(date|data|datum|fecha|day|tag|date ?time|datetime|zeitpunkt|when)$", r"\b(date|datum|fecha)\b"),
    "price_per_unit": (
        r"^(volume ?price|price per (liter|litre|unit|gallon|gal)|unit ?price|liter ?preis|literpreis|preis (l|liter|pro liter|je liter)|ppl|price l)$",
        r"(volume ?price|per ?(lit|gal)|liter ?preis|unit ?price)",
    ),
    "amount": (
        r"^(fuel|liters|litres|liter|litre|gallons|gallon|gal|menge|volume|quantity|qty|amount|getankt|fuel amount|kwh)$",
        r"\b(fuel|liters|litres|gallons|menge|quantity|volume)\b",
    ),
    "odometer_km": (
        r"^(odo|odometer|odometre|kilometerstand|km ?stand|mileage|kilometres|kilometers|km|miles|mi)$",
        r"\b(odo|odometer|kilometerstand|mileage)\b",
    ),
    "price_total": (
        r"^(price|total|total price|cost|costs|betrag|gesamtpreis|gesamtbetrag|summe|kosten|sum|total cost)$",
        r"\b(price|cost|total|betrag|summe|kosten)\b",
    ),
    "full_tank": (r"^(full|full tank|vollgetankt|voll|tank full|tankfüllung|filled)$",),
    "station": (r"^(city|station|tankstelle|ort|place|gas station|petrol station|location|stadt)$",),
    "notes": (r"^(notes|note|notiz|notizen|bemerkung|comment|comments|kommentar|memo|description)$",),
}


def _plain(title: str) -> str:
    """A column name by its words: no brackets (``Price (optional)`` is ``price``), no case, no marks."""
    text = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", title.lower())
    return re.sub(r"[^a-zäöüß0-9]+", " ", text).strip()


def guess(columns: list[str]) -> dict[str, int | None]:
    """The column of every target by its name (``None`` when no column looks like it); a column is used once."""
    plain = [_plain(c) for c in columns]
    taken: set[int] = set()
    out: dict[str, int | None] = {t: None for t in TARGETS}
    for target in ("date", "price_per_unit", "amount", "odometer_km", "price_total", "full_tank", "station", "notes"):
        for pattern in _PATTERNS[target]:
            hit = next((i for i, name in enumerate(plain) if i not in taken and re.search(pattern, name)), None)
            if hit is not None:
                out[target] = hit
                taken.add(hit)
                break
    return out


def sample(table: Table, index: int | None) -> str:
    """The first value of a column that is not empty (what the person sees beside the choice of the column)."""
    if index is None or not 0 <= index < len(table.columns):
        return ""
    return next((row[index] for row in table.rows if row[index]), "")[:40]


# ------------------------------------------------------------------ the values


def to_number(text: str, whole: bool = False) -> float:
    """A number as people write it: ``1,234.56``, ``1.234,56``, ``37,17``, ``59.43 EUR``. A single separator is the decimal sign - except in a whole
    number (an odometer) where it stands before exactly three digits: ``36,633`` is 36633. ValueError for a text that is none."""
    s = re.sub(r"[^\d,.\-]", "", text.replace(" ", " "))
    if not re.search(r"\d", s):
        raise ValueError(text)
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", "") if (whole and re.search(r",\d{3}$", s)) or s.count(",") > 1 else s.replace(",", ".")
    elif s.count(".") > 1 or (whole and re.search(r"\.\d{3}$", s) and not re.search(r"\.\d{3}0+$", s)):
        s = s.replace(".", "")
    return float(s)


def to_bool(text: str) -> bool | None:
    """Yes / no as an app writes it (``1``, ``true``, ``ja``, ``full``); ``None`` when it says neither."""
    word = text.strip().lower()
    if word in ("1", "true", "yes", "y", "ja", "j", "x", "full", "voll", "wahr", "ok"):
        return True
    if word in ("0", "false", "no", "n", "nein", "partial", "teil", "falsch"):
        return False
    return None


_DATE_PARTS = re.compile(r"^(\d{1,4})[./\-](\d{1,2})[./\-](\d{1,4})$")


def _day(text: str) -> str:
    """The date part of a text: ``2024-09-16 15:39`` -> ``2024-09-16``."""
    return re.split(r"[ T]", text.strip(), maxsplit=1)[0]


def detect_order(values: list[str]) -> str | None:
    """The order of day, month and year in the dates of a column: ``ymd``, ``dmy`` or ``mdy``; ``None`` when they do not tell (01.02.2024 may be either)."""
    saw_dm = saw_md = False
    for value in values:
        parts = _DATE_PARTS.match(_day(value))
        if not parts:
            if re.fullmatch(r"\d{8}", _day(value)):
                return "ymd"
            continue
        a, b, _c = parts.groups()
        if len(a) == 4:
            return "ymd"
        if int(a) > 12:
            saw_dm = True
        if int(b) > 12:
            saw_md = True
    if saw_dm and not saw_md:
        return "dmy"
    if saw_md and not saw_dm:
        return "mdy"
    return None


def to_date(text: str, order: str) -> str:
    """A date as ISO text. ValueError for a text that is no date (or a day that lies after tomorrow, or before 1950)."""
    day = _day(text)
    if re.fullmatch(r"\d{8}", day):
        y, m, d = int(day[:4]), int(day[4:6]), int(day[6:])
    else:
        parts = _DATE_PARTS.match(day)
        if not parts:
            raise ValueError(text)
        a, b, c = (int(x) for x in parts.groups())
        if len(parts.group(1)) == 4:
            y, m, d = a, b, c
        elif order == "mdy":
            m, d, y = a, b, c
        else:
            d, m, y = a, b, c
        if y < 100:
            y += 2000
    found = date(y, m, d)
    if found < date(1950, 1, 1) or found > date.today() + timedelta(days=1):
        raise ValueError(text)
    return found.isoformat()


# ------------------------------------------------------------------ the rows


def known(conn: sqlite3.Connection, vehicle_id: int) -> tuple[set[tuple[str, float]], set[tuple[str, int]]]:
    """What the fuel log of the car holds already: ``(day, amount)`` and ``(day, odometer)`` - a row of a file that matches one of them is not imported again."""
    amounts: set[tuple[str, float]] = set()
    odometers: set[tuple[str, int]] = set()
    for row in conn.execute("SELECT date, amount, odometer_km FROM fuel WHERE vehicle_id = ?", (vehicle_id,)):
        if row["amount"]:
            amounts.add((row["date"], round(row["amount"], 1)))
        if row["odometer_km"]:
            odometers.add((row["date"], row["odometer_km"]))
    return amounts, odometers


def convert(table: Table, mapping: dict[str, int | None], options: dict, base: str, have: tuple[set, set] | None = None) -> Result:
    """Every row of the table as an entry of the fuel log, in the units that are stored (km, litres - or kWh / kg for ``base``). ``mapping`` says which
    column is what, ``options`` the units of the file (``dist``: km / mi, ``vol``: l / usgal / ukgal), the order of the date (``order``: auto / ymd / dmy /
    mdy) and ``skip`` (leave out what is in the log already). A row with a missing or unreadable date or amount is a problem, not an entry."""
    out = Result()
    col = {t: mapping.get(t) for t in TARGETS}
    order = options.get("order") or "auto"
    if order == "auto" and col["date"] is not None:
        order = detect_order([row[col["date"]] for row in table.rows[:200]]) or table.meta.get("order") or "ymd"
    elif order == "auto":
        order = "ymd"
    out.order = order
    dist = MILE_KM if options.get("dist") == "mi" else 1.0
    vol = GALLON_L.get(options.get("vol", "l"), 1.0) if base == "L" else 1.0
    amounts, odometers = have or (set(), set())

    def cell(row: list[str], target: str) -> str:
        index = col[target]
        return row[index].strip() if index is not None and index < len(row) else ""

    def problem(n: int, key: str, value: str) -> None:
        out.problem_count += 1
        if len(out.problems) < MAX_PROBLEMS:
            out.problems.append((n, key, value[:40]))

    for n, row in enumerate(table.rows, 2):  # row 1 of the table is the header
        out.read += 1
        try:
            day = to_date(cell(row, "date"), order)
        except ValueError:
            problem(n, "fuelimport.row_date", cell(row, "date"))
            continue
        try:
            amount_file = to_number(cell(row, "amount"))
            amount = amount_file * vol
            if amount <= 0:
                raise ValueError
        except ValueError:
            problem(n, "fuelimport.row_amount", cell(row, "amount"))
            continue
        entry: dict = {"date": day, "amount": round(amount, 3), "odometer_km": None, "price_total": None, "price_per_unit": None}
        if cell(row, "odometer_km"):
            try:
                km = to_number(cell(row, "odometer_km"), whole=True) * dist
                entry["odometer_km"] = round(km) if km >= 0 else None
            except ValueError:
                problem(n, "fuelimport.row_odometer", cell(row, "odometer_km"))
        if cell(row, "price_total"):
            try:
                total = to_number(cell(row, "price_total"))
                entry["price_total"] = round(total, 2) if total >= 0 else None
            except ValueError:
                problem(n, "fuelimport.row_price", cell(row, "price_total"))
        unit_file = None
        if cell(row, "price_per_unit"):
            try:
                unit_file = to_number(cell(row, "price_per_unit"))
                entry["price_per_unit"] = (
                    round(unit_file / vol, 3) if unit_file >= 0 else None
                )  # a price per gallon becomes a price per litre
            except ValueError:
                problem(n, "fuelimport.row_price", cell(row, "price_per_unit"))
        if entry["price_total"] is None and unit_file:
            entry["price_total"] = round(amount_file * unit_file, 2)  # in the units of the file, so that they cancel
        elif entry["price_per_unit"] is None and entry["price_total"]:
            entry["price_per_unit"] = round(entry["price_total"] / entry["amount"], 3)
        full = to_bool(cell(row, "full_tank")) if col["full_tank"] is not None else True
        entry["full_tank"] = 1 if full in (True, None) else 0
        entry["station"] = cell(row, "station")[:80] or None
        entry["notes"] = cell(row, "notes")[:500] or None
        if options.get("skip", True) and (
            (day, round(entry["amount"], 1)) in amounts or (entry["odometer_km"] and (day, entry["odometer_km"]) in odometers)
        ):
            out.duplicates += 1
            continue
        out.rows.append(entry)
    return out


def insert(conn: sqlite3.Connection, vehicle_id: int, rows: list[dict]) -> int:
    """Write the entries to the fuel log (one statement for all of them). Returns how many."""
    conn.executemany(
        "INSERT INTO fuel(vehicle_id, date, odometer_km, amount, price_per_unit, price_total, full_tank, station, notes, fuel_kind) "
        "VALUES(?,?,?,?,?,?,?,?,?,'main')",
        [
            (
                vehicle_id,
                r["date"],
                r["odometer_km"],
                r["amount"],
                r["price_per_unit"],
                r["price_total"],
                r["full_tank"],
                r["station"],
                r["notes"],
            )
            for r in rows
        ],
    )
    return len(rows)
