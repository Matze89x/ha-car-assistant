"""Fuel statistics. The odometer is the key; nothing is ever estimated.

Consumption is computed from *full-tank intervals*: from one full fill-up to the next, all amounts in between (including
partial fills) are added up and divided by the distance. Intervals with a missing amount or odometer are skipped.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass
class Interval:
    end_date: str
    km: int
    amount: float
    cost: float | None  # None unless every fill in the interval has a price

    @property
    def per_100(self) -> float:
        return self.amount / self.km * 100

    @property
    def cost_per_100(self) -> float | None:
        return None if self.cost is None else self.cost / self.km * 100


def intervals(conn: sqlite3.Connection, vehicle_id: int) -> list[Interval]:
    rows = conn.execute(
        "SELECT * FROM fuel WHERE vehicle_id = ? AND odometer_km IS NOT NULL ORDER BY odometer_km ASC, date ASC, id ASC",
        (vehicle_id,),
    ).fetchall()
    result: list[Interval] = []
    prev_full = None
    amount_sum = 0.0
    cost_sum = 0.0
    amount_ok = cost_ok = True
    for row in rows:
        if prev_full is not None:
            if row["amount"] is None:
                amount_ok = False
            else:
                amount_sum += row["amount"]
            if row["price_total"] is None:
                cost_ok = False
            else:
                cost_sum += row["price_total"]
        if row["full_tank"]:
            if prev_full is not None and amount_ok and amount_sum > 0:
                km = row["odometer_km"] - prev_full["odometer_km"]
                if km > 0:
                    result.append(Interval(row["date"], km, amount_sum, cost_sum if cost_ok else None))
            prev_full, amount_sum, cost_sum, amount_ok, cost_ok = row, 0.0, 0.0, True, True
    return result


@dataclass
class Month:
    month: str
    km: int = 0
    amount: float = 0.0
    cost: float = 0.0
    cost_km: int = 0
    spent: float = 0.0  # actual money spent on fuel that month (all fills with a price)
    intervals: list[Interval] = field(default_factory=list)

    @property
    def per_100(self) -> float | None:
        return self.amount / self.km * 100 if self.km else None

    @property
    def cost_per_100(self) -> float | None:
        return self.cost / self.cost_km * 100 if self.cost_km else None


def monthly(conn: sqlite3.Connection, vehicle_id: int) -> list[Month]:
    months: dict[str, Month] = {}
    for iv in intervals(conn, vehicle_id):
        m = months.setdefault(iv.end_date[:7], Month(iv.end_date[:7]))
        m.km += iv.km
        m.amount += iv.amount
        m.intervals.append(iv)
        if iv.cost is not None:
            m.cost += iv.cost
            m.cost_km += iv.km
    for row in conn.execute(
        "SELECT substr(date, 1, 7) AS m, SUM(price_total) AS s FROM fuel WHERE vehicle_id = ? AND price_total IS NOT NULL GROUP BY m",
        (vehicle_id,),
    ):
        months.setdefault(row["m"], Month(row["m"])).spent = row["s"]
    return sorted(months.values(), key=lambda m: m.month, reverse=True)


# the period filter of the report: how many periods can be chosen per grouping (the first one is the default)
PERIODS = {"day": (30, 60, 90, 180, 365), "week": (4, 8, 12, 26, 52), "month": (6, 12, 24, 36, 60)}


def period_key(day: date, group: str) -> str:
    if group == "day":
        return day.isoformat()
    if group == "week":
        year, week, _ = day.isocalendar()
        return f"{year}-W{week:02d}"
    return day.isoformat()[:7]


def period_start(group: str, count: int, today: date) -> date:
    """First day of the window that shows `count` periods ending with the current one."""
    if group == "day":
        return today - timedelta(days=count - 1)
    if group == "week":
        return today - timedelta(weeks=count - 1)
    total = today.year * 12 + today.month - 1 - (count - 1)
    return date(total // 12, total % 12 + 1, 1)


def periods(conn: sqlite3.Connection, vehicle_id: int, group: str, count: int, today: date | None = None) -> list[Month]:
    """Consumption and money per day / week / month, newest first, only the last `count` periods."""
    today = today or date.today()
    first = period_key(period_start(group, count, today), group)
    found: dict[str, Month] = {}
    for iv in intervals(conn, vehicle_id):
        key = period_key(date.fromisoformat(iv.end_date[:10]), group)
        if key < first:
            continue
        m = found.setdefault(key, Month(key))
        m.km += iv.km
        m.amount += iv.amount
        m.intervals.append(iv)
        if iv.cost is not None:
            m.cost += iv.cost
            m.cost_km += iv.km
    for row in conn.execute("SELECT date, price_total FROM fuel WHERE vehicle_id = ? AND price_total IS NOT NULL", (vehicle_id,)):
        key = period_key(date.fromisoformat(row["date"][:10]), group)
        if key >= first:
            found.setdefault(key, Month(key)).spent += row["price_total"]
    return sorted(found.values(), key=lambda m: m.month, reverse=True)


def overall(conn: sqlite3.Connection, vehicle_id: int) -> dict:
    ivs = intervals(conn, vehicle_id)
    km = sum(i.km for i in ivs)
    amount = sum(i.amount for i in ivs)
    priced = [i for i in ivs if i.cost is not None]
    price_km = sum(i.km for i in priced)
    totals = conn.execute(
        "SELECT COUNT(*) AS n, SUM(amount) AS amount, SUM(price_total) AS spent FROM fuel WHERE vehicle_id = ?", (vehicle_id,)
    ).fetchone()
    return {
        "fills": totals["n"],
        "total_amount": totals["amount"],
        "total_spent": totals["spent"],
        "intervals": len(ivs),
        "avg_per_100": amount / km * 100 if km else None,
        "last_per_100": ivs[-1].per_100 if ivs else None,
        "cost_per_100": sum(i.cost for i in priced) / price_km * 100 if price_km else None,
    }


def consumption_series(conn: sqlite3.Connection, vehicle_id: int) -> list[tuple[str, float]]:
    return [(i.end_date, i.per_100) for i in intervals(conn, vehicle_id)]


def month_spent(conn: sqlite3.Connection, vehicle_id: int, month: str) -> float:
    row = conn.execute(
        "SELECT SUM(price_total) AS s FROM fuel WHERE vehicle_id = ? AND substr(date, 1, 7) = ?", (vehicle_id, month)
    ).fetchone()
    return float(row["s"] or 0)


def estimate_range(conn: sqlite3.Connection, vehicle) -> dict | None:
    """Rough remaining range from the refuelling history (only when the car reports none).

    Base is the last full-tank refuel, the consumption is the average of the last five
    full-to-full intervals. Without a tank size, two full tanks or a full tank as base
    nothing is returned - no invented number.
    """
    if vehicle["fuel_type"] == "electric" or not vehicle["tank_l"]:
        return None
    ivs = intervals(conn, vehicle["id"])[-5:]
    km_sum = sum(i.km for i in ivs)
    if not ivs or km_sum <= 0:
        return None
    per100 = sum(i.amount for i in ivs) / km_sum * 100
    if per100 <= 0:
        return None
    row = conn.execute(
        "SELECT odometer_km FROM fuel WHERE vehicle_id = ? AND full_tank = 1 AND odometer_km IS NOT NULL ORDER BY odometer_km DESC LIMIT 1",
        (vehicle["id"],),
    ).fetchone()
    if row is None:
        return None
    from . import summary

    now = summary.current_odometer(conn, vehicle["id"])
    since = max(0, (now or row["odometer_km"]) - row["odometer_km"])
    km = max(0, round(vehicle["tank_l"] / per100 * 100 - since))
    return {"km": km, "per100": per100, "since": since}


def windows(group: str, count: int, today: date | None = None) -> list[tuple[str, date, date]]:
    """The last `count` periods (oldest first) as (key, first day, last day) - empty periods included, so a chart has no holes."""
    today = today or date.today()
    out: list[tuple[str, date, date]] = []
    if group == "day":
        for i in range(count - 1, -1, -1):
            d = today - timedelta(days=i)
            out.append((period_key(d, group), d, d))
    elif group == "week":
        monday = today - timedelta(days=today.weekday())
        for i in range(count - 1, -1, -1):
            start = monday - timedelta(weeks=i)
            out.append((period_key(start, group), start, start + timedelta(days=6)))
    else:
        total = today.year * 12 + today.month - 1
        for i in range(count - 1, -1, -1):
            y, m = divmod(total - i, 12)
            start = date(y, m + 1, 1)
            nxt = date(y + (m + 1) // 12, (m + 1) % 12 + 1, 1)
            out.append((period_key(start, group), start, nxt - timedelta(days=1)))
    return out


COST_PARTS = (
    ("fuel", "SELECT date, price_total AS c FROM fuel WHERE vehicle_id = ? AND price_total IS NOT NULL"),
    ("service", "SELECT date, cost AS c FROM service WHERE vehicle_id = ? AND cost IS NOT NULL"),
    ("mods", "SELECT date, cost AS c FROM mods WHERE vehicle_id = ? AND cost IS NOT NULL"),
    ("parts", "SELECT date, cost AS c FROM parts WHERE vehicle_id = ? AND cost IS NOT NULL"),
)


def costs(conn: sqlite3.Connection, vehicle_id: int, group: str, count: int, today: date | None = None) -> list[dict]:
    """Money per period split into fuel, service, modifications and parts (oldest first)."""
    wins = windows(group, count, today)
    rows = {key: {"key": key, "fuel": 0.0, "service": 0.0, "mods": 0.0, "parts": 0.0} for key, _a, _b in wins}
    for name, sql in COST_PARTS:
        for r in conn.execute(sql, (vehicle_id,)):
            try:
                key = period_key(date.fromisoformat(r["date"][:10]), group)
            except ValueError:
                continue
            if key in rows:
                rows[key][name] += r["c"]
    return [rows[key] for key, _a, _b in wins]


EXPENSE_SQL = (
    (
        "fuel",
        "SELECT id, date, station AS title, amount AS qty, price_total AS c, odometer_km AS km FROM fuel WHERE vehicle_id = ? AND price_total IS NOT NULL",
    ),
    (
        "service",
        "SELECT id, date, title, workshop AS sub, cost AS c, odometer_km AS km FROM service WHERE vehicle_id = ? AND cost IS NOT NULL",
    ),
    ("mods", "SELECT id, date, title, cost AS c, odometer_km AS km FROM mods WHERE vehicle_id = ? AND cost IS NOT NULL"),
    (
        "parts",
        "SELECT id, date, name AS title, shop AS sub, quantity AS qty, cost AS c FROM parts WHERE vehicle_id = ? AND cost IS NOT NULL",
    ),
)


def expenses(conn: sqlite3.Connection, vehicle_id: int, group: str, count: int, kind: str = "", today: date | None = None) -> list[dict]:
    """Every entry with a price inside the shown window, newest first: ``kind`` (fuel / service / mods / parts), date, title, money, km.

    ``kind`` limits the list to one category; an unknown or empty value lists all of them.
    """
    wins = windows(group, count, today)
    first, last = wins[0][1].isoformat(), wins[-1][2].isoformat()
    out: list[dict] = []
    for name, sql in EXPENSE_SQL:
        if kind in {n for n, _ in EXPENSE_SQL} and kind != name:
            continue
        for r in conn.execute(sql, (vehicle_id,)):
            row = dict(r)
            day = (row["date"] or "")[:10]
            if not first <= day <= last:
                continue
            out.append(
                {
                    "kind": name,
                    "id": row["id"],
                    "date": day,
                    "title": row.get("title") or "",
                    "sub": row.get("sub") or "",
                    "qty": row.get("qty"),
                    "cost": float(row["c"]),
                    "km": row.get("km"),
                }
            )
    out.sort(key=lambda e: (e["date"], e["id"]), reverse=True)
    return out


def kilometres(
    conn: sqlite3.Connection, vehicle_id: int, group: str, count: int, today: date | None = None
) -> list[tuple[str, float | None]]:
    """Kilometres driven per period (oldest first), from the highest odometer value known up to the end of each period; None = not known."""
    points: list[tuple[str, int]] = []
    for sql in (
        "SELECT date, odometer_km AS k FROM odometer WHERE vehicle_id = ?",
        "SELECT date, odometer_km AS k FROM fuel WHERE vehicle_id = ? AND odometer_km IS NOT NULL",
        "SELECT date, odometer_km AS k FROM service WHERE vehicle_id = ? AND odometer_km IS NOT NULL",
        "SELECT date, end_km AS k FROM trips WHERE vehicle_id = ? AND end_km IS NOT NULL",
    ):
        points += [(r["date"][:10], r["k"]) for r in conn.execute(sql, (vehicle_id,)) if r["date"] and r["k"] is not None]
    points.sort()

    def odo_until(day: date) -> int | None:
        best = None
        for when, km in points:
            if when > day.isoformat():
                break
            best = km if best is None else max(best, km)
        return best

    wins = windows(group, count, today)
    prev = odo_until(wins[0][1] - timedelta(days=1)) if wins else None
    out: list[tuple[str, float | None]] = []
    for key, _a, end in wins:
        now = odo_until(end)
        out.append((key, float(now - prev) if now is not None and prev is not None and now >= prev else None))
        if now is not None:
            prev = now
    return out


def price_series(conn: sqlite3.Connection, vehicle_id: int, since: str = "") -> list[tuple[str, float]]:
    """Price per litre / kWh of every refuel with a price (oldest first)."""
    out = []
    for r in conn.execute(
        "SELECT date, price_per_unit AS p, price_total AS t, amount AS a FROM fuel WHERE vehicle_id = ? ORDER BY date, odometer_km",
        (vehicle_id,),
    ):
        price = r["p"] if r["p"] else (r["t"] / r["a"] if r["t"] and r["a"] else None)
        if price and r["date"][:10] >= since:
            out.append((r["date"][:10], float(price)))
    return out
