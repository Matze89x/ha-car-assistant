"""Charging sessions noticed from the readings: when a car starts charging the app opens a session (time, battery level, odometer); the power seen
and the level at the end are kept while it runs; when charging stops, the session is closed and an unfinished fuel-log entry is added (energy and
price are missing - the energy is only estimated from the battery size, never stored as a fact). Only for cars with a battery."""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime

from . import db, refuel_detect, summary

log = logging.getLogger(__name__)
MIN_MINUTES = 3  # shorter than this is a plug contact, not a session
MAX_MINUTES = 36 * 60  # longer than this: the "stopped" message never came - not a real session, nothing is kept
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
    if minutes < MIN_MINUTES or minutes > MAX_MINUTES or rise is None or rise < MIN_PCT:
        conn.execute("DELETE FROM charge_sessions WHERE id = ?", (session["id"],))  # a plug contact: not worth keeping
        return False
    day = ended.astimezone().date().isoformat()
    km = session["odometer_km"]
    own_entry = conn.execute("SELECT 1 FROM fuel WHERE vehicle_id = ? AND date = ? AND auto_kind IS NOT NULL", (vehicle_id, day)).fetchone()
    for row in conn.execute("SELECT odometer_km FROM fuel WHERE vehicle_id = ? AND date = ?", (vehicle_id, day)):
        if (km is None or row["odometer_km"] is None or abs(row["odometer_km"] - km) <= 5) and own_entry is None:
            return False  # the person logged this charge already
    cur = conn.execute(
        "INSERT INTO fuel(vehicle_id, date, odometer_km, amount, price_total, full_tank, auto_kind, auto_rise, auto_at, auto_open) "
        "VALUES(?,?,?,?,?,?,?,?,?,1)",
        (
            vehicle_id,
            day,
            session["odometer_km"],
            None,
            None,
            1 if end_pct >= 95 else 0,
            "charge",
            round(rise),
            ended.astimezone().strftime(refuel_detect.STAMP),
        ),
    )
    conn.execute("UPDATE charge_sessions SET fuel_id = ? WHERE id = ?", (cur.lastrowid, session["id"]))
    return True


FAST_KW = 25  # a session whose strongest power was at least this is counted as fast charging (DC), the rest as slow (home, wallbox, AC)


def _rows(conn: sqlite3.Connection, vehicle_id: int, since: str | None, limit: int | None):
    sql = (
        "SELECT s.*, f.amount AS bill_kwh, f.price_total AS bill_cost FROM charge_sessions s LEFT JOIN fuel f ON f.id = s.fuel_id "
        "WHERE s.vehicle_id = ? AND s.ended IS NOT NULL"
        + (" AND s.started >= ?" if since else "")
        + " ORDER BY s.id DESC"
        + (" LIMIT ?" if limit else "")
    )
    args = [vehicle_id, *([since] if since else []), *([limit] if limit else [])]
    return conn.execute(sql, args).fetchall()


def home_price(conn: sqlite3.Connection, vehicle_id: int) -> float | None:
    """The person's price per kWh at home (Settings of the charging page): used to estimate the cost of slow charging without a bill."""
    raw = db.get_setting(conn, f"charge.home_price.{vehicle_id}", "") or ""
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if 0 < value <= 10 else None


def set_home_price(conn: sqlite3.Connection, vehicle_id: int, value: float | None) -> None:
    db.set_setting(conn, f"charge.home_price.{vehicle_id}", None if value is None else f"{value:g}")


def _one(r, battery_kwh, price=None) -> dict:
    start = _parse(r["started"]).astimezone()
    end = _parse(r["ended"]).astimezone()
    rise = (r["end_pct"] - r["start_pct"]) if r["end_pct"] is not None and r["start_pct"] is not None else None
    gained = battery_kwh * rise / 100 if battery_kwh and rise else None  # what reached the battery (an estimate)
    bill = r["bill_kwh"]  # what the bill says (the person's entry), when completed
    cost = r["bill_cost"]
    fast = bool(r["max_kw"] and r["max_kw"] >= FAST_KW)
    est_cost = (
        round(gained * price, 2) if price and gained and not bill and not fast else None
    )  # slow charging without a bill: at the home price
    loss = (1 - gained / bill) * 100 if gained and bill and bill >= gained * 0.8 else None  # the share that did not reach the battery
    return {
        "id": r["id"],
        "date": start.date().isoformat(),
        "from": start.strftime("%H:%M"),
        "to": end.strftime("%H:%M"),
        "minutes": round((end - start).total_seconds() / 60),
        "start_pct": round(r["start_pct"]) if r["start_pct"] is not None else None,
        "end_pct": round(r["end_pct"]) if r["end_pct"] is not None else None,
        "max_kw": round(r["max_kw"]) if r["max_kw"] else None,
        "fast": fast,
        "kwh": round(bill, 1) if bill else (round(gained, 1) if gained else None),
        "kwh_billed": bool(bill),
        "gained_kwh": gained,
        "cost": cost if cost else est_cost,
        "cost_estimated": bool(not cost and est_cost),
        "per_kwh": (cost / bill) if cost and bill else None,
        "loss_pct": loss,
        "fuel_id": r["fuel_id"],
    }


def sessions(conn: sqlite3.Connection, vehicle_id: int, limit: int = 10) -> list[dict]:
    """The last finished sessions for the page: when, how long, levels, strongest power, energy (from the bill when completed, else an estimate from the
    battery size), cost, price per kWh and the share lost on the way."""
    battery = conn.execute("SELECT battery_kwh FROM vehicles WHERE id = ?", (vehicle_id,)).fetchone()
    kwh = battery["battery_kwh"] if battery and battery["battery_kwh"] else None
    price = home_price(conn, vehicle_id)
    return [_one(r, kwh, price) for r in _rows(conn, vehicle_id, None, limit)]


def stats(conn: sqlite3.Connection, vehicle_id: int, days: int = 90) -> dict | None:
    """What the sessions of the last ``days`` days add up to: count, energy, cost, average price per kWh, average strongest power, fast / slow split
    and the average loss. None without a session."""
    from datetime import timedelta

    battery = conn.execute("SELECT battery_kwh FROM vehicles WHERE id = ?", (vehicle_id,)).fetchone()
    kwh = battery["battery_kwh"] if battery and battery["battery_kwh"] else None
    since = (_now() - timedelta(days=days)).isoformat(timespec="seconds")
    price = home_price(conn, vehicle_id)
    items = [_one(r, kwh, price) for r in _rows(conn, vehicle_id, since, None)]
    if not items:
        return None
    billed = [s for s in items if s["kwh_billed"]]
    priced = [s for s in items if s["cost"] and s["kwh_billed"]]
    estimated = [s for s in items if s["cost_estimated"]]
    powers = [s["max_kw"] for s in items if s["max_kw"]]
    losses = [s["loss_pct"] for s in items if s["loss_pct"] is not None]
    energy = sum(s["kwh"] for s in items if s["kwh"])
    billed_cost = sum(s["cost"] for s in priced)
    cost = billed_cost + sum(s["cost"] for s in estimated)
    return {
        "days": days,
        "n": len(items),
        "kwh": energy,
        "kwh_estimated": len(billed) < len(items),  # some energy is an estimate: the bills are not all in yet
        "cost": cost if (priced or estimated) else None,
        "cost_estimated": bool(estimated),  # some of the cost is the home price times the energy that reached the battery
        "per_kwh": billed_cost / sum(s["kwh"] for s in priced) if priced and sum(s["kwh"] for s in priced) else None,  # of the bills only
        "avg_kw": sum(powers) / len(powers) if powers else None,
        "fast": sum(1 for s in items if s["fast"]),
        "slow": sum(1 for s in items if not s["fast"]),
        "loss_pct": sum(losses) / len(losses) if losses else None,
        "minutes": sum(s["minutes"] for s in items),
    }
