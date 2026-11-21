"""Charging sessions noticed from the readings: when a car starts charging the app opens a session (time, battery level, odometer); the power seen
and the level at the end are kept while it runs; when charging stops, the session is closed and an unfinished fuel-log entry is added (energy and
price are missing - the energy is only estimated from the battery size, never stored as a fact). Only for cars with a battery."""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime

from . import refuel_detect, summary

log = logging.getLogger(__name__)
MIN_MINUTES = 3  # shorter than this is a plug contact, not a session
MIN_PCT = 2.0  # less than this is not worth an entry


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _now() -> datetime:
    return datetime.now(UTC)


def _parse(stamp: str) -> datetime:
    value = datetime.fromisoformat(stamp)
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _open(conn: sqlite3.Connection, vehicle_id: int):
    return conn.execute(
        "SELECT * FROM charge_sessions WHERE vehicle_id = ? AND ended IS NULL ORDER BY id DESC LIMIT 1", (vehicle_id,)
    ).fetchone()


def _level(conn: sqlite3.Connection, vehicle_id: int) -> float | None:
    row = conn.execute("SELECT value FROM live WHERE vehicle_id = ? AND key = 'battery_pct'", (vehicle_id,)).fetchone()
    return _num(row["value"]) if row else None


def seen(conn: sqlite3.Connection, vehicle_id: int, key: str, before, after) -> bool:
    """A charging-related reading changed. True when a session was finished and an entry added (the person should be told)."""
    vehicle = conn.execute("SELECT fuel_type, battery_kwh FROM vehicles WHERE id = ?", (vehicle_id,)).fetchone()
    if vehicle is None or vehicle["fuel_type"] not in ("electric", "hybrid"):
        return False
    session = _open(conn, vehicle_id)
    if key == "charging":
        if str(after) == "yes" and session is None:
            conn.execute(
                "INSERT INTO charge_sessions(vehicle_id, started, start_pct, end_pct, odometer_km) VALUES(?,?,?,?,?)",
                (
                    vehicle_id,
                    _now().isoformat(timespec="seconds"),
                    _level(conn, vehicle_id),
                    _level(conn, vehicle_id),
                    summary.current_odometer(conn, vehicle_id),
                ),
            )
        elif str(after) == "no" and session is not None:
            return _close(conn, vehicle_id, session, vehicle["battery_kwh"])
        return False
    if session is None:
        return False
    if key == "battery_pct" and _num(after) is not None:
        conn.execute("UPDATE charge_sessions SET end_pct = ? WHERE id = ?", (_num(after), session["id"]))
    elif key == "charge_power_kw":
        kw = _num(after)
        if kw is not None and kw > (session["max_kw"] or 0):
            conn.execute("UPDATE charge_sessions SET max_kw = ? WHERE id = ?", (kw, session["id"]))
    return False


def _close(conn: sqlite3.Connection, vehicle_id: int, session, battery_kwh) -> bool:
    ended = _now()
    end_pct = _level(conn, vehicle_id)
    if end_pct is None:
        end_pct = session["end_pct"]
    minutes = (ended - _parse(session["started"])).total_seconds() / 60
    start_pct = session["start_pct"]
    rise = (end_pct - start_pct) if end_pct is not None and start_pct is not None else None
    conn.execute(
        "UPDATE charge_sessions SET ended = ?, end_pct = ? WHERE id = ?", (ended.isoformat(timespec="seconds"), end_pct, session["id"])
    )
    if minutes < MIN_MINUTES or rise is None or rise < MIN_PCT:
        conn.execute("DELETE FROM charge_sessions WHERE id = ?", (session["id"],))  # a plug contact: not worth keeping
        return False
    day = ended.astimezone().date().isoformat()
    km = session["odometer_km"]
    own_entry = conn.execute("SELECT 1 FROM fuel WHERE vehicle_id = ? AND date = ? AND notes LIKE 'auto:%'", (vehicle_id, day)).fetchone()
    for row in conn.execute("SELECT odometer_km FROM fuel WHERE vehicle_id = ? AND date = ?", (vehicle_id, day)):
        if (km is None or row["odometer_km"] is None or abs(row["odometer_km"] - km) <= 5) and own_entry is None:
            return False  # the person logged this charge already
    cur = conn.execute(
        "INSERT INTO fuel(vehicle_id, date, odometer_km, amount, price_total, full_tank, notes) VALUES(?,?,?,?,?,?,?)",
        (
            vehicle_id,
            day,
            session["odometer_km"],
            None,
            None,
            1 if end_pct >= 95 else 0,
            f"auto:charge:+{round(rise)}%:{ended.astimezone().strftime('%Y-%m-%dT%H:%M')}",
        ),
    )
    conn.execute("UPDATE charge_sessions SET fuel_id = ? WHERE id = ?", (cur.lastrowid, session["id"]))
    return True


def sessions(conn: sqlite3.Connection, vehicle_id: int, limit: int = 10) -> list[dict]:
    """The last finished sessions for the page: when, how long, from which to which level, the strongest power and a rough energy estimate."""
    battery = conn.execute("SELECT battery_kwh FROM vehicles WHERE id = ?", (vehicle_id,)).fetchone()
    kwh = battery["battery_kwh"] if battery and battery["battery_kwh"] else None
    out = []
    for r in conn.execute(
        "SELECT * FROM charge_sessions WHERE vehicle_id = ? AND ended IS NOT NULL ORDER BY id DESC LIMIT ?", (vehicle_id, limit)
    ):
        start = _parse(r["started"]).astimezone()
        end = _parse(r["ended"]).astimezone()
        rise = (r["end_pct"] - r["start_pct"]) if r["end_pct"] is not None and r["start_pct"] is not None else None
        out.append(
            {
                "id": r["id"],
                "date": start.date().isoformat(),
                "from": start.strftime("%H:%M"),
                "to": end.strftime("%H:%M"),
                "minutes": round((end - start).total_seconds() / 60),
                "start_pct": round(r["start_pct"]) if r["start_pct"] is not None else None,
                "end_pct": round(r["end_pct"]) if r["end_pct"] is not None else None,
                "max_kw": round(r["max_kw"]) if r["max_kw"] else None,
                "kwh": round(kwh * rise / 100, 1) if kwh and rise else None,
                "fuel_id": r["fuel_id"],
            }
        )
    return out


# the unfinished-entry helpers of refuel_detect also serve charging entries (notes ``auto:charge:+N%:...``)
rise_of = refuel_detect.rise_of
