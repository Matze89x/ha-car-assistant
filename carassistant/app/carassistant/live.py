"""Pull values from bound Home Assistant entities (odometer, fuel level, range, position) into the database."""

from __future__ import annotations

import logging
import sqlite3

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


def _store(conn: sqlite3.Connection, vehicle_id: int, key: str, value: str | None, at: str | None = None) -> None:
    if value is None:
        return
    from . import connectors

    connectors._store(conn, vehicle_id, key, value, at)


def _reported(state: dict | None) -> str | None:
    """When Home Assistant says the entity last reported / changed - not when we looked."""
    from . import connectors

    return connectors.moment((state or {}).get("last_reported") or (state or {}).get("last_updated"))


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
            state = ha.get_state(vehicle[bind])
            value = _number(state)
            if value is not None:
                _store(conn, vid, key, f"{value:.0f}", _reported(state))
    if vehicle["bind_tracker"]:
        state = ha.get_state(vehicle["bind_tracker"])
        attrs = (state or {}).get("attributes") or {}
        if "latitude" in attrs and "longitude" in attrs:
            _store(conn, vid, "position", f"{float(attrs['latitude']):.6f},{float(attrs['longitude']):.6f}", _reported(state))
    return changed
