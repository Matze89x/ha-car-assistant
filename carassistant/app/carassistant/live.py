"""Pull values from bound Home Assistant entities (odometer, fuel level, range, position) into the database."""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime

from . import ha, summary

log = logging.getLogger(__name__)
MILES_TO_KM = 1.609344


def _number(state: dict | None) -> float | None:
    if not state:
        return None
    try:
        value = float(state.get("state"))
    except (TypeError, ValueError):
        return None
    unit = (state.get("attributes") or {}).get("unit_of_measurement", "")
    return value * MILES_TO_KM if unit in ("mi", "miles") else value


def _store(conn: sqlite3.Connection, vehicle_id: int, key: str, value: str | None) -> None:
    if value is None:
        return
    conn.execute(
        "INSERT INTO live(vehicle_id, key, value, updated) VALUES(?,?,?,?) "
        "ON CONFLICT(vehicle_id, key) DO UPDATE SET value = excluded.value, updated = excluded.updated",
        (vehicle_id, key, value, datetime.now(UTC).isoformat(timespec="seconds")),
    )


def refresh_vehicle(conn: sqlite3.Connection, vehicle: sqlite3.Row) -> bool:
    """Returns True when new data (e.g. a higher odometer) was stored."""
    changed = False
    vid = vehicle["id"]
    if vehicle["bind_odometer"]:
        km = _number(ha.get_state(vehicle["bind_odometer"]))
        if km is not None and km > 0:
            km_int = round(km)
            known = summary.current_odometer(conn, vid)
            if known is None or km_int > known:
                summary.record_odometer(conn, vid, km_int, "ha")
                changed = True
    for bind, key in (("bind_fuel_level", "fuel_level"), ("bind_range", "range_km")):
        if vehicle[bind]:
            value = _number(ha.get_state(vehicle[bind]))
            if value is not None:
                _store(conn, vid, key, f"{value:.0f}")
    if vehicle["bind_tracker"]:
        state = ha.get_state(vehicle["bind_tracker"])
        attrs = (state or {}).get("attributes") or {}
        if "latitude" in attrs and "longitude" in attrs:
            _store(conn, vid, "position", f"{float(attrs['latitude']):.6f},{float(attrs['longitude']):.6f}")
    return changed
