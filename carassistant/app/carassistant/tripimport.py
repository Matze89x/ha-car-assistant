"""Trips from a CSV file (a logbook app, a spreadsheet, the export of this app): read the file, guess which column means what, convert and check every
row - and only when the person has looked at the result are the rows written to the trip log (the pages are in ``tripimport_web.py``).

It is the same road as the import of fill-ups (``fuelimport.py`` reads the file and knows dates and numbers): nothing is stored before the last step, the
file is thrown away afterwards, and a row that is in the trip log already (the same day, start time and distance - or the same two odometer readings) is
skipped, so the same file can be imported twice without doubling anything.

A trip needs a date and a distance; the distance may be the odometer at the start and at the end. Times, places, the category (private / business /
commute, in either language) and the purpose are optional. A trip is checked like one typed into the form: it is not in the future, the end odometer is
not below the start, and one trip is not longer than ``entities.MAX_TRIP_KM`` (a missing digit, a swapped column).
"""

from __future__ import annotations

import re
import sqlite3
from datetime import date

from . import entities, trips
from .fuelimport import MAX_PROBLEMS, MILE_KM, FileError, Result, Table, detect_order, read, sample, to_date, to_number  # noqa: F401 (web module)

TARGETS = ("date", "start_time", "end_time", "start_km", "end_km", "distance_km", "start_place", "end_place", "category", "purpose")
REQUIRED = ("date",)
MAX_TEXT = 120

_PATTERNS: dict[
    str, tuple[str, ...]
] = {  # the name of a column, without what stands in brackets, in lower case (the export of this app is covered)
    "date": (r"^(date|datum|day|tag|fecha|start date|startdatum|date ?time|datetime|zeitpunkt|when)$", r"\b(date|datum)\b"),
    "start_time": (
        r"^(start time|startzeit|start|begin|beginn|departure|abfahrt|abfahrtszeit|time|uhrzeit|zeit|von zeit|time from)$",
        r"\b(start|beginn|abfahrt)\w* ?(time|zeit|uhrzeit)\b",
    ),
    "end_time": (
        r"^(end time|endzeit|end|ende|arrival|ankunft|ankunftszeit|bis zeit|time to)$",
        r"\b(end|ende|ankunft)\w* ?(time|zeit|uhrzeit)\b",
    ),
    "start_km": (
        r"^(start odometer|start km|startkilometerstand|start mileage|start odo|odometer start|km start|km anfang|anfangs km|anfangskilometerstand|kilometerstand start|kilometerstand anfang)$",
        r"\b(start|anfang)\w*\b.*\b(km|odo|odometer|kilometerstand|mileage)\b",
    ),
    "end_km": (
        r"^(end odometer|end km|endkilometerstand|end mileage|end odo|odometer end|km end|km ende|end km stand|kilometerstand ende|kilometerstand end|endstand)$",
        r"\b(end|ende)\w*\b.*\b(km|odo|odometer|kilometerstand|mileage)\b",
    ),
    "distance_km": (
        r"^(distance|strecke|distanz|entfernung|km|kilometer|kilometers|kilometres|miles|mi|length|laenge|länge|fahrstrecke|trip distance|trip km|gefahrene km|gefahren)$",
        r"\b(distance|strecke|distanz|entfernung|fahrstrecke)\b",
    ),
    "category": (
        r"^(category|kategorie|type|art|fahrtart|fahrttyp|trip type|typ|business private)$",
        r"\b(category|kategorie|fahrtart|fahrttyp)\b",
    ),
    "start_place": (
        r"^(from|von|start place|startort|start address|startadresse|origin|abfahrtsort|start location|from place|start point|startpunkt)$",
        r"\b(from|origin|startort|startadresse|startpunkt)\b",
    ),
    "end_place": (
        r"^(to|nach|ziel|end place|zielort|destination|end address|zieladresse|end location|to place|end point|zielpunkt|arrival place)$",
        r"\b(destination|zielort|zieladresse|zielpunkt)\b",
    ),
    "purpose": (
        r"^(purpose|zweck|fahrtzweck|reason|grund|reisezweck|anlass|notes|note|notiz|notizen|bemerkung|comment|comments|kommentar|description|beschreibung)$",
        r"\b(purpose|zweck|reason|grund|anlass)\b",
    ),
}


def _plain(title: str) -> str:
    """A column name by its words: no brackets, no case, no marks (``Distance (km)`` is ``distance``, ``Start-km`` is ``start km``)."""
    text = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", title.lower())
    return re.sub(r"[^a-zäöüß0-9]+", " ", text).strip()


_CLOCK = re.compile(r"^(\d{1,2})\s*[:.h]\s*(\d{2})(?:\s*[:.]\s*\d{2})?\s*([ap]\.?m\.?)?$", re.IGNORECASE)


def clock(text: str) -> str | None:
    """A time of day as ``HH:MM`` (``8:05``, ``08.05``, ``08:05:33``, ``8:05 pm``, or the time part of ``2024-09-16 08:05``); None when it is none."""
    word = re.split(r"[T ]", text.strip(), maxsplit=1)[-1] if re.match(r"^\d{4}-\d\d-\d\d[T ]", text.strip()) else text.strip()
    found = _CLOCK.match(word)
    if not found:
        return None
    hour, minute = int(found.group(1)), int(found.group(2))
    suffix = (found.group(3) or "").lower().replace(".", "")
    if suffix == "pm" and hour < 12:
        hour += 12
    elif suffix == "am" and hour == 12:
        hour = 0
    return f"{hour:02d}:{minute:02d}" if hour < 24 and minute < 60 else None


def guess(columns: list[str], rows: list[list[str]] | None = None) -> dict[str, int | None]:
    """The column of every target by its name (``None`` when no column looks like it); a column is used once. A column called just *Start* or *End* may
    hold a time or a place: the first values decide (``rows`` of the table)."""
    plain = [_plain(c) for c in columns]
    taken: set[int] = set()
    out: dict[str, int | None] = {t: None for t in TARGETS}

    def looks_like_time(index: int) -> bool:
        values = [r[index] for r in (rows or [])[:20] if index < len(r) and r[index].strip()]
        return bool(values) and all(clock(v) is not None for v in values)

    for target in (
        "date",
        "start_km",
        "end_km",
        "start_time",
        "end_time",
        "distance_km",
        "category",
        "start_place",
        "end_place",
        "purpose",
    ):
        for pattern in _PATTERNS[target]:
            hit = next((i for i, name in enumerate(plain) if i not in taken and re.search(pattern, name)), None)
            if (
                hit is not None
                and target in ("start_time", "end_time")
                and rows
                and plain[hit] in ("start", "end", "begin", "ende")
                and not looks_like_time(hit)
            ):
                continue  # a column "Start" full of towns is a place
            if hit is not None:
                out[target] = hit
                taken.add(hit)
                break
    # a column "Start" / "End" that held places (and was not taken as a time) names the places
    for target, words in (("start_place", ("start", "begin", "beginn")), ("end_place", ("end", "ende"))):
        if out[target] is None:
            hit = next((i for i, name in enumerate(plain) if i not in taken and name in words), None)
            if hit is not None:
                out[target] = hit
                taken.add(hit)
    return out


def missing(mapping: dict[str, int | None]) -> str:
    """The i18n key of what is missing in the choice of the columns - or ``""``: the date, and a distance (or both odometer readings)."""
    if any(mapping.get(t) is None for t in REQUIRED):
        return "tripimport.err_required"
    if mapping.get("distance_km") is None and (mapping.get("start_km") is None or mapping.get("end_km") is None):
        return "tripimport.err_required"
    return ""


_CATEGORY_WORDS = {
    "business": ("business", "geschäft", "geschaeft", "dienst", "beruf", "work", "firma", "company"),
    "commute": ("commut", "arbeitsweg", "pendel", "wohnung", "weg zur arbeit"),
    "private": ("private", "privat", "personal", "persönlich", "personlich", "privé", "prive"),
}
_CATEGORY_LETTERS = {"p": "private", "b": "business", "g": "business", "d": "business", "w": "commute", "c": "commute", "a": "commute"}


def category_of(text: str) -> str:
    """The category of a trip by the word in the file (any language that is common; ``private`` when it says nothing the app knows)."""
    word = text.strip().lower()
    if word in _CATEGORY_LETTERS:
        return _CATEGORY_LETTERS[word]
    for category in ("commute", "business", "private"):  # (a *Geschäftlicher Arbeitsweg* is a commute: the narrower word first)
        if any(part in word for part in _CATEGORY_WORDS[category]):
            return category
    return "private"


def known(conn: sqlite3.Connection, vehicle_id: int) -> tuple[set[tuple[str, str, float]], set[tuple[str, int, int]]]:
    """What the trip log holds already: ``(day, start time, distance)`` and ``(day, start odometer, end odometer)`` - a row of a file that matches one of
    them is not imported again."""
    by_time: set[tuple[str, str, float]] = set()
    by_km: set[tuple[str, int, int]] = set()
    for row in conn.execute("SELECT date, start_time, start_km, end_km, distance_km FROM trips WHERE vehicle_id = ?", (vehicle_id,)):
        distance = trips.trip_distance(row)
        if distance is not None:
            by_time.add((row["date"], row["start_time"] or "", round(distance, 1)))
        if row["start_km"] is not None and row["end_km"] is not None:
            by_km.add((row["date"], row["start_km"], row["end_km"]))
    return by_time, by_km


def convert(table: Table, mapping: dict[str, int | None], options: dict, have: tuple[set, set] | None = None) -> Result:
    """Every row of the table as a trip of the trip log, in the units that are stored (km). ``mapping`` says which column is what, ``options`` the unit of
    the file (``dist``: km / mi), the order of the date (``order``: auto / ymd / dmy / mdy) and ``skip`` (leave out what is in the log already). A row
    with a missing or unreadable date, or without any distance, is a problem, not a trip."""
    out = Result()
    col = {t: mapping.get(t) for t in TARGETS}
    order = options.get("order") or "auto"
    if order == "auto" and col["date"] is not None:
        order = detect_order([row[col["date"]] for row in table.rows[:200]]) or table.meta.get("order") or "ymd"
    elif order == "auto":
        order = "ymd"
    out.order = order
    dist = MILE_KM if options.get("dist") == "mi" else 1.0
    by_time, by_km = have or (set(), set())
    today = date.today().isoformat()

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
            if day > today:
                raise ValueError(day)
        except ValueError:
            problem(n, "tripimport.row_date", cell(row, "date"))
            continue
        times: dict[str, str | None] = {}
        for target in ("start_time", "end_time"):
            text = cell(row, target)
            times[target] = clock(text) if text else None
            if text and times[target] is None:
                problem(n, "tripimport.row_time", text)
        if col["start_time"] is None:  # a date with its time of day in one column ("2024-09-16 08:05")
            times["start_time"] = clock(cell(row, "date")) if re.search(r"\d[ T]\d", cell(row, "date")) else None
        start = end = None
        for target in ("start_km", "end_km"):
            text = cell(row, target)
            if not text:
                continue
            try:
                value = round(to_number(text, whole=True) * dist)
                if value < 0:
                    raise ValueError(text)
            except ValueError:
                problem(n, "tripimport.row_km", text)
                continue
            start, end = (value, end) if target == "start_km" else (start, value)
        if start is not None and end is not None and end < start:
            problem(n, "tripimport.row_order", cell(row, "end_km"))
            start = end = None
        distance = None
        if cell(row, "distance_km"):
            try:
                distance = round(to_number(cell(row, "distance_km")) * dist, 2)
            except ValueError:
                distance = None  # (said once below, when the odometer readings cannot make up for it)
        if (distance is None or distance <= 0) and start is not None and end is not None and end > start:
            distance = float(end - start)
        if distance is None or distance <= 0:
            problem(n, "tripimport.row_distance", cell(row, "distance_km"))
            continue
        if distance > entities.MAX_TRIP_KM:
            problem(n, "tripimport.row_far", cell(row, "distance_km") or cell(row, "end_km"))
            continue
        entry = {
            "date": day,
            "start_time": times["start_time"],
            "end_time": times["end_time"],
            "start_km": start,
            "end_km": end,
            "distance_km": distance,
            "start_place": cell(row, "start_place")[:MAX_TEXT] or None,
            "end_place": cell(row, "end_place")[:MAX_TEXT] or None,
            "category": category_of(cell(row, "category")) if col["category"] is not None else "private",
            "purpose": cell(row, "purpose")[:MAX_TEXT] or None,
        }
        if options.get("skip", True) and (
            (day, entry["start_time"] or "", round(distance, 1)) in by_time
            or (start is not None and end is not None and (day, start, end) in by_km)
        ):
            out.duplicates += 1
            continue
        out.rows.append(entry)
    return out


def insert(conn: sqlite3.Connection, vehicle_id: int, rows: list[dict]) -> int:
    """Write the trips to the trip log (one statement for all of them). Returns how many."""
    conn.executemany(
        "INSERT INTO trips(vehicle_id, date, start_time, end_time, start_km, end_km, start_place, end_place, category, purpose, source, distance_km) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,'csv',?)",
        [
            (
                vehicle_id,
                r["date"],
                r["start_time"],
                r["end_time"],
                r["start_km"],
                r["end_km"],
                r["start_place"],
                r["end_place"],
                r["category"],
                r["purpose"],
                r["distance_km"],
            )
            for r in rows
        ],
    )
    return len(rows)
