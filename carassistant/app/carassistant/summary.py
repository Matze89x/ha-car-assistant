"""Derived values: current odometer, due dates, maintenance status, per-vehicle summary and attention list."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta

from . import modules

SOON_DAYS = 30
SOON_KM = 1000


def today() -> date:
    return date.today()


def add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year, month = d.year + month_index // 12, month_index % 12 + 1
    # clamp the day (e.g. 31 Jan + 1 month -> 28/29 Feb)
    for day in (d.day, 30, 29, 28):
        try:
            return date(year, month, day)
        except ValueError:
            continue
    raise AssertionError("unreachable")


def current_odometer(conn: sqlite3.Connection, vehicle_id: int) -> int | None:
    """Highest known odometer value across all records (odometer is the most reliable ordering key)."""
    row = conn.execute(
        """
        SELECT MAX(v) AS km FROM (
            SELECT MAX(odometer_km) AS v FROM odometer WHERE vehicle_id = :v
            UNION ALL SELECT MAX(odometer_km) FROM fuel WHERE vehicle_id = :v
            UNION ALL SELECT MAX(odometer_km) FROM service WHERE vehicle_id = :v
            UNION ALL SELECT MAX(odometer_km) FROM mods WHERE vehicle_id = :v
            UNION ALL SELECT MAX(end_km) FROM trips WHERE vehicle_id = :v
        )
        """,
        {"v": vehicle_id},
    ).fetchone()
    return int(row["km"]) if row and row["km"] is not None else None


def add_odometer(conn: sqlite3.Connection, vehicle_id: int, km: int, when: str | None = None, source: str = "manual") -> None:
    conn.execute(
        "INSERT INTO odometer(vehicle_id, date, odometer_km, source) VALUES(?, ?, ?, ?)",
        (vehicle_id, when or today().isoformat(), km, source),
    )


def record_odometer(conn: sqlite3.Connection, vehicle_id: int, km: int, source: str) -> None:
    """Automatic readings (plugin, Home Assistant): one row per day and source holding the day's highest value.

    A car that reports every few seconds therefore adds one row a day, not one per kilometre."""
    day = today().isoformat()
    row = conn.execute(
        "SELECT id FROM odometer WHERE vehicle_id = ? AND date = ? AND source = ? ORDER BY id DESC LIMIT 1", (vehicle_id, day, source)
    ).fetchone()
    if row:
        conn.execute("UPDATE odometer SET odometer_km = MAX(odometer_km, ?) WHERE id = ?", (km, row["id"]))
    else:
        add_odometer(conn, vehicle_id, km, day, source)


@dataclass
class DueInfo:
    status: str  # ok | soon | overdue | unknown
    days_left: int | None = None
    km_left: int | None = None
    due_date: date | None = None
    due_km: int | None = None


def _status(days_left: int | None, km_left: int | None) -> str:
    candidates = []
    if days_left is not None:
        candidates.append("overdue" if days_left < 0 else "soon" if days_left <= SOON_DAYS else "ok")
    if km_left is not None:
        candidates.append("overdue" if km_left < 0 else "soon" if km_left <= SOON_KM else "ok")
    if not candidates:
        return "unknown"
    for level in ("overdue", "soon", "ok"):
        if level in candidates:
            return level
    return "unknown"


def appointment_due(row: sqlite3.Row, ref: date | None = None) -> DueInfo:
    ref = ref or today()
    due = date.fromisoformat(row["due_date"])
    days = (due - ref).days
    return DueInfo(_status(days, None), days_left=days, due_date=due)


def service_index(conn: sqlite3.Connection, vehicle_id: int) -> list[tuple[str, int | None, str]]:
    """The service book of one car, newest first, with the lower-case search text of each entry (read once per page)."""
    return [
        (r["date"], r["odometer_km"], f"{r['title']} {r['notes'] or ''}".lower())
        for r in conn.execute(
            "SELECT date, odometer_km, title, notes FROM service WHERE vehicle_id = ? ORDER BY date DESC, id DESC", (vehicle_id,)
        )
    ]


def task_last(
    conn: sqlite3.Connection, vehicle_id: int, task: sqlite3.Row, index: list[tuple[str, int | None, str]] | None = None
) -> tuple[str | None, int | None]:
    """Latest completion: manual ``last_*`` fields or the newest service-book entry that matches a keyword.

    Pass ``index`` (from :func:`service_index`) when checking several tasks of one car, so the book is read once."""
    best_date, best_km = task["last_date"], task["last_km"]
    keywords = [k.strip().lower() for k in (task["keywords"] or "").split(",") if k.strip()]
    if keywords:
        for date_, km, haystack in index if index is not None else service_index(conn, vehicle_id):
            if any(k in haystack for k in keywords):
                if best_date is None or date_ >= best_date:
                    best_date, best_km = date_, km if km is not None else best_km
                break
    return best_date, best_km


def task_due(
    conn: sqlite3.Connection,
    vehicle_id: int,
    task: sqlite3.Row,
    odometer: int | None,
    ref: date | None = None,
    index: list[tuple[str, int | None, str]] | None = None,
) -> DueInfo:
    ref = ref or today()
    last_date, last_km = task_last(conn, vehicle_id, task, index)
    due_date = due_km = days_left = km_left = None
    if task["interval_months"] and last_date:
        due_date = add_months(date.fromisoformat(last_date), task["interval_months"])
        days_left = (due_date - ref).days
    if task["interval_km"] and last_km is not None:
        due_km = last_km + task["interval_km"]
        if odometer is not None:
            km_left = due_km - odometer
    return DueInfo(_status(days_left, km_left), days_left, km_left, due_date, due_km)


@dataclass
class Attention:
    kind: str  # appointment | task
    severity: str  # soon | overdue
    title: str
    days_left: int | None = None
    km_left: int | None = None
    item_id: int | None = None


def attention_items(conn: sqlite3.Connection, vehicle_id: int, ref: date | None = None) -> list[Attention]:
    ref = ref or today()
    off = modules.disabled(conn, vehicle_id)  # a function that is switched off raises no hint and costs no query
    odo = current_odometer(conn, vehicle_id)
    items: list[Attention] = []
    if "appointments" not in off:
        for row in conn.execute("SELECT * FROM appointments WHERE vehicle_id = ? AND done = 0", (vehicle_id,)):
            info = appointment_due(row, ref)
            if info.status in ("soon", "overdue"):
                items.append(Attention("appointment", info.status, row["title"], info.days_left, None, row["id"]))
    if "tasks" not in off:
        index = service_index(conn, vehicle_id)
        for row in conn.execute("SELECT * FROM tasks WHERE vehicle_id = ? AND muted = 0", (vehicle_id,)):
            info = task_due(conn, vehicle_id, row, odo, ref, index)
            if info.status in ("soon", "overdue"):
                items.append(Attention("task", info.status, row["title"], info.days_left, info.km_left, row["id"]))
    items.sort(key=lambda a: (a.severity != "overdue", a.days_left if a.days_left is not None else 10**6))
    return items


def next_inspection(conn: sqlite3.Connection, vehicle_id: int, ref: date | None = None) -> sqlite3.Row | None:
    """Next open appointment of kind ``inspection`` (TÜV / MOT / HU)."""
    if "appointments" in modules.disabled(conn, vehicle_id):
        return None
    return conn.execute(
        "SELECT * FROM appointments WHERE vehicle_id = ? AND kind = 'inspection' AND done = 0 ORDER BY due_date ASC LIMIT 1",
        (vehicle_id,),
    ).fetchone()


def inspection_estimate(first_reg: str | None, ref: date | None = None) -> date | None:
    """Next inspection derived from the first registration: the first one after 3 years, then every 2 years. A guide only -
    an appointment entered by the user always wins."""
    if not first_reg:
        return None
    try:
        start = date.fromisoformat(first_reg[:10])
    except ValueError:
        return None
    ref = ref or today()
    due = date(start.year + 3, start.month, min(start.day, 28))
    while due < ref:
        due = date(due.year + 2, due.month, due.day)
    return due


def next_service_km(conn: sqlite3.Connection, vehicle_id: int, odometer: int | None) -> dict | None:
    """The task that is due first by kilometres: ``km_left`` (negative = overdue), its ``title`` and how much of its interval is used (``pct``, 0-100)."""
    if odometer is None or "tasks" in modules.disabled(conn, vehicle_id):
        return None
    index = service_index(conn, vehicle_id)
    best = None
    for task in conn.execute("SELECT * FROM tasks WHERE vehicle_id = ? AND interval_km IS NOT NULL AND interval_km > 0", (vehicle_id,)):
        _, last_km = task_last(conn, vehicle_id, task, index)
        if last_km is None:
            continue
        left = last_km + task["interval_km"] - odometer
        if best is None or left < best["km_left"]:
            used = (odometer - last_km) / task["interval_km"]
            best = {"title": task["title"], "km_left": left, "pct": max(0, min(100, round(used * 100)))}
    return best


def vehicle_summary(conn: sqlite3.Connection, vehicle: sqlite3.Row, ref: date | None = None) -> dict:
    ref = ref or today()
    vid = vehicle["id"]
    insp = next_inspection(conn, vid)
    insp_info = appointment_due(insp, ref) if insp else None
    attention = attention_items(conn, vid, ref)
    live = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM live WHERE vehicle_id = ?", (vid,))}
    mounted = (
        None
        if "tires" in modules.disabled(conn, vid)
        else conn.execute("SELECT * FROM tires WHERE vehicle_id = ? AND mounted = 1 LIMIT 1", (vid,)).fetchone()
    )
    return {
        "vehicle": vehicle,
        "odometer": current_odometer(conn, vid),
        "inspection": insp,
        "inspection_info": insp_info,
        "attention": attention,
        "overdue": sum(1 for a in attention if a.severity == "overdue"),
        "soon": sum(1 for a in attention if a.severity == "soon"),
        "live": live,
        "tires": mounted,
        "horizon": ref + timedelta(days=SOON_DAYS),
    }
