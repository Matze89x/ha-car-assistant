"""A refuel noticed from the tank level: when the level of a car rises by a lot between two readings, the app adds an unfinished entry to the fuel log
(date, mileage, what the tank jumped by) and tells the person - they only have to complete amount and price from the receipt.

Only for cars with a tank (not electric). Nothing is invented: the amount stays empty (the page shows a rough estimate from the tank size next to it).
An entry the person made for that day and mileage, or a detection a few hours ago, is never doubled.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime, timedelta

from . import summary

log = logging.getLogger(__name__)
JUMP_PCT = 15.0  # percentage points of the tank between two readings that count as a refuel
GUARD_HOURS = 3  # one detection per drive to the pump
MARK = "auto:tank"


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def level_changed(conn: sqlite3.Connection, vehicle_id: int, old, new) -> bool:
    """Called with the old and the new tank level (percent) just before / after it is stored. True when an unfinished fuel entry was added."""
    before, after = _num(old), _num(new)
    if before is None or after is None or after - before < JUMP_PCT:
        return False
    vehicle = conn.execute("SELECT fuel_type FROM vehicles WHERE id = ?", (vehicle_id,)).fetchone()
    if vehicle is None or vehicle["fuel_type"] == "electric":
        return False
    now = datetime.now(UTC).astimezone()
    recent = (now - timedelta(hours=GUARD_HOURS)).date().isoformat()
    for row in conn.execute(
        "SELECT id, notes FROM fuel WHERE vehicle_id = ? AND date >= ? AND notes LIKE ?", (vehicle_id, recent, MARK + "%")
    ):
        stamp = _stamp(row["notes"])
        if stamp is None or now - stamp < timedelta(hours=GUARD_HOURS):
            return False
    km = summary.current_odometer(conn, vehicle_id)
    day = now.date().isoformat()
    for row in conn.execute("SELECT odometer_km FROM fuel WHERE vehicle_id = ? AND date = ?", (vehicle_id, day)):
        if km is None or row["odometer_km"] is None or abs(row["odometer_km"] - km) <= 5:
            return False  # the person has logged this refuel already
    rise = round(after - before)
    conn.execute(
        "INSERT INTO fuel(vehicle_id, date, odometer_km, amount, price_total, full_tank, notes) VALUES(?,?,?,?,?,?,?)",
        (vehicle_id, day, km, None, None, 1 if after >= 95 else 0, f"{MARK}:+{rise}%:{now.strftime('%Y-%m-%dT%H:%M')}"),
    )
    return True


def _stamp(notes: str | None) -> datetime | None:
    try:
        return datetime.strptime((notes or "").rsplit(":", 2)[-2] + ":" + (notes or "").rsplit(":", 1)[-1], "%Y-%m-%dT%H:%M").astimezone()
    except (ValueError, IndexError):
        return None


def rise_of(notes: str | None) -> int | None:
    """The tank rise (percentage points) a detected entry carries, else None."""
    parts = (notes or "").split(":")
    if len(parts) >= 3 and parts[0] == "auto" and parts[1] in ("tank", "charge") and parts[2].startswith("+") and parts[2].endswith("%"):
        try:
            return int(parts[2][1:-1])
        except ValueError:
            return None
    return None


def todo(conn: sqlite3.Connection, vehicle_id: int, limit: int = 3) -> list[dict]:
    """Detected refuels / charges that still lack amount or price: ``{"id", "date", "odometer_km", "rise", "litres", "unit", "charge"}``
    (``litres`` = a rough estimate from the tank / battery size, in ``unit``)."""
    v = conn.execute("SELECT tank_l, battery_kwh FROM vehicles WHERE id = ?", (vehicle_id,)).fetchone()
    out = []
    for r in conn.execute(
        "SELECT id, date, odometer_km, notes FROM fuel WHERE vehicle_id = ? AND notes LIKE 'auto:%' AND (amount IS NULL OR price_total IS NULL) "
        "ORDER BY date DESC, id DESC LIMIT ?",
        (vehicle_id, limit),
    ):
        rise = rise_of(r["notes"])
        charge = (r["notes"] or "").startswith("auto:charge")
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
    return out
