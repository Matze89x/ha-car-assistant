"""A refuel noticed from the tank level: when the level of a car rises by a lot between two readings, the app adds an unfinished entry to the fuel log
(date, mileage, what the tank jumped by) and tells the person - they only have to complete amount and price from the receipt.

Only for cars with a tank (not electric). Nothing is invented: the amount stays empty (the page shows a rough estimate from the tank size next to it).
An entry the person made for that day and mileage, or a detection a few hours ago, is never doubled.

How the entry came to be is kept in its own columns (``auto_kind``, ``auto_rise``, ``auto_at``, ``auto_src``, ``auto_open``), never in the notes: the notes
are the person's. The reminder (``todo``) stays while the receipt is missing and the person has not saved the entry; it goes away by itself when three
trips have been driven since (or three days have passed) - the entry stays and can be completed from its card at any time.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import UTC, datetime, timedelta

from . import summary

log = logging.getLogger(__name__)
STEP_MINUTES = 10  # a tank that fills in several small steps counts as one refuel when the steps follow each other within this time
_floor: dict[int, tuple[float, datetime]] = {}  # per vehicle: the lowest level of the current rise and when it last changed
JUMP_PCT = 15.0  # percentage points of the tank between two readings that count as a refuel
GUARD_HOURS = 3  # one detection per drive to the pump
LAPSE_TRIPS = 3  # the reminder goes away by itself after this many trips since the refuel was noticed ...
LAPSE_DAYS = 3  # ... or this many days
STAMP = "%Y-%m-%dT%H:%M"  # how ``auto_at`` is written (local time)


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _stamp(text: str | None) -> datetime | None:
    """``auto_at`` as a moment (local time)."""
    try:
        return datetime.strptime(text or "", STAMP).astimezone()
    except ValueError:
        return None


def level_changed(conn: sqlite3.Connection, vehicle_id: int, old, new) -> bool:
    """Called with the old and the new tank level (percent) just before / after it is stored. True when an unfinished fuel entry was added."""
    before, after = _num(old), _num(new)
    if before is None or after is None:
        return False
    stamp = datetime.now(UTC)
    low, seen = _floor.get(vehicle_id, (before, stamp))
    if stamp - seen > timedelta(minutes=STEP_MINUTES):
        low = before  # an old rise is forgotten
    low = min(low, before, after)
    _floor[vehicle_id] = (low, stamp)
    before = low  # the rise over several readings close together (33 -> 40 -> 50 counts as 17)
    if after - before < JUMP_PCT:
        return False
    _floor[vehicle_id] = (after, stamp)
    vehicle = conn.execute("SELECT fuel_type FROM vehicles WHERE id = ?", (vehicle_id,)).fetchone()
    if vehicle is None or vehicle["fuel_type"] == "electric":
        return False
    now = datetime.now(UTC).astimezone()
    recent = (now - timedelta(hours=GUARD_HOURS)).date().isoformat()
    for row in conn.execute("SELECT auto_at FROM fuel WHERE vehicle_id = ? AND auto_kind = 'tank' AND date >= ?", (vehicle_id, recent)):
        noticed = _stamp(row["auto_at"])
        if noticed is None or now - noticed < timedelta(hours=GUARD_HOURS):
            return False
    km = summary.current_odometer(conn, vehicle_id)
    day = now.date().isoformat()
    for row in conn.execute("SELECT odometer_km FROM fuel WHERE vehicle_id = ? AND date = ?", (vehicle_id, day)):
        if km is None or row["odometer_km"] is None or abs(row["odometer_km"] - km) <= 5:
            return False  # the person has logged this refuel already
    conn.execute(
        "INSERT INTO fuel(vehicle_id, date, odometer_km, amount, price_total, full_tank, auto_kind, auto_rise, auto_at, auto_open) "
        "VALUES(?,?,?,?,?,?,?,?,?,1)",
        (vehicle_id, day, km, None, None, 1 if after >= 95 else 0, "tank", round(after - before), now.strftime(STAMP)),
    )
    return True


# ------------------------------------------------------------------ the reminder


def trips_since(conn: sqlite3.Connection, vehicle_id: int, at: str | None) -> int:
    """How many trips began after the moment ``at`` (``auto_at``): a trip without a start time counts only on a later day."""
    if not at or len(at) < 16:
        return 0
    day, clock = at[:10], at[11:16]
    return conn.execute(
        "SELECT COUNT(*) FROM trips WHERE vehicle_id = ? AND (date > ? OR (date = ? AND start_time IS NOT NULL AND start_time > ?))",
        (vehicle_id, day, day, clock),
    ).fetchone()[0]


def lapsed(conn: sqlite3.Connection, vehicle_id: int, at: str | None) -> bool:
    """The reminder has done its job: three trips have been driven since the refuel was noticed, or three days have passed."""
    when = _stamp(at)
    if when is None:
        return False
    if datetime.now().astimezone() - when > timedelta(days=LAPSE_DAYS):
        return True
    return trips_since(conn, vehicle_id, at) >= LAPSE_TRIPS


def todo(conn: sqlite3.Connection, vehicle_id: int, limit: int = 3) -> list[dict]:
    """Detected refuels / charges that still wait for their receipt (the person has not saved them, an amount or the price is missing, and the reminder
    has not lapsed): ``{"id", "date", "odometer_km", "rise", "litres", "unit", "charge"}`` (``litres`` = a rough estimate from the tank / battery size, in
    ``unit``)."""
    v = conn.execute("SELECT tank_l, battery_kwh FROM vehicles WHERE id = ?", (vehicle_id,)).fetchone()
    out: list[dict] = []
    for r in conn.execute(
        "SELECT id, date, odometer_km, auto_kind, auto_rise, auto_at FROM fuel WHERE vehicle_id = ? AND auto_open = 1 "
        "AND (amount IS NULL OR price_total IS NULL) ORDER BY date DESC, id DESC LIMIT 20",
        (vehicle_id,),
    ):
        if lapsed(conn, vehicle_id, r["auto_at"]):
            continue
        rise = round(r["auto_rise"]) if r["auto_rise"] else None
        charge = r["auto_kind"] == "charge"
        size = (v["battery_kwh"] if charge else v["tank_l"]) if v else None
        out.append(
            {
                "id": r["id"],
                "date": r["date"],
                "odometer_km": r["odometer_km"],
                "rise": rise,
                "litres": round(size * rise / 100) if size and rise else None,
                "unit": "kWh" if charge else "L",
                "charge": charge,
            }
        )
        if len(out) >= limit:
            break
    return out


# ------------------------------------------------------------------ entries from before the columns existed

_OLD_MARK = re.compile(r"^auto:(tank|charge)(?::(?:\+(\d+)%|api))?(?::(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}))?$")


def migrate_marks(conn: sqlite3.Connection, vehicle_id: int | None = None) -> int:
    """Entries that still carry their mark in the notes (``auto:tank:+78%:2026-11-27T07:48``, ``api:<plugin>``) - from before the columns existed, or
    from an older backup - get the mark in the columns and clean notes. Idempotent. Returns how many were moved."""
    where, args = "(notes LIKE 'auto:%' OR notes LIKE 'api:%')", []
    if vehicle_id is not None:
        where, args = where + " AND vehicle_id = ?", [vehicle_id]
    moved = 0
    for row in conn.execute(f"SELECT id, notes, amount, price_total FROM fuel WHERE {where}", args).fetchall():
        notes = (row["notes"] or "").strip()
        if notes.startswith("api:"):
            conn.execute("UPDATE fuel SET auto_kind = 'api', auto_src = ?, notes = NULL WHERE id = ?", (notes[4:60] or None, row["id"]))
        else:
            found = _OLD_MARK.match(notes)
            parts = notes.split(":")
            kind = parts[1] if len(parts) > 1 and parts[1] in ("tank", "charge") else "tank"
            if len(parts) > 2 and parts[2] == "api":  # a refuel a plugin reported without an amount
                kind = "api"
            rise = int(found.group(2)) if found and found.group(2) else None
            at = found.group(3) if found else None
            waiting = 1 if row["amount"] is None or row["price_total"] is None else 0
            conn.execute(
                "UPDATE fuel SET auto_kind = ?, auto_rise = ?, auto_at = ?, auto_open = ?, notes = NULL WHERE id = ?",
                (kind, rise, at, waiting, row["id"]),
            )
        moved += 1
    return moved
