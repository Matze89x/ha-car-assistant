"""Trip analysis: what the trips of a car say in total - how many and how long, which kinds, when you drive, and how (driving style).

Everything is computed from the trips of one car in one query each (no query per trip): the trips of the chosen period, and in one go the
recorded points of the drives that have time stamps, which is where the driving style comes from (see ``trips.stats``).
"""

from __future__ import annotations

import itertools
import sqlite3
from collections import defaultdict
from collections.abc import Callable
from datetime import date, timedelta

from . import trips

PERIODS = {"30": 30, "90": 90, "365": 365, "all": None}  # the choices: days (None = everything)
DEFAULT_PERIOD = "90"
LENGTH_EDGES = (5, 10, 25, 50, 100, 200)  # in the units shown (km or miles)
BLOCKS = ((0, 6), (6, 12), (12, 18), (18, 24))  # night, morning, afternoon, evening (start hour)
MAX_STYLE_TRIPS = 150  # the drives read for the driving style (the newest ones)


def _minutes(start: str | None, end: str | None) -> int:
    a, b = start or "", end or ""
    if ":" in a and ":" in b:
        gap = int(b[:2]) * 60 + int(b[3:5]) - (int(a[:2]) * 60 + int(a[3:5]))
        return gap if gap > 0 else 0
    return 0


def _hour(start: str | None) -> int | None:
    if start and ":" in start and start[:2].isdigit():
        h = int(start[:2])
        return h if 0 <= h < 24 else None
    return None


def length_labels() -> list[str]:
    """The names of the length classes (the unit is written next to the chart): <5, 5-10 ... >200."""
    edges = LENGTH_EDGES
    return [f"<{edges[0]}", *[f"{a}-{b}" for a, b in itertools.pairwise(edges)], f">{edges[-1]}"]


def length_bucket(shown_km: float) -> int:
    """Index of the length class a trip of this length (in the units shown) falls into."""
    for i, edge in enumerate(LENGTH_EDGES):
        if shown_km < edge:
            return i
    return len(LENGTH_EDGES)


def analyse(conn: sqlite3.Connection, vehicle_id: int, period: str, shown: Callable[[float], float], today: date | None = None) -> dict:
    """The analysis of the trips in ``period`` (a key of PERIODS). ``shown`` turns kilometres into the units shown."""
    today = today or date.today()
    days = PERIODS.get(period, PERIODS[DEFAULT_PERIOD])
    since = (today - timedelta(days=days - 1)).isoformat() if days else "0000-00-00"
    rows = conn.execute(
        "SELECT * FROM trips WHERE vehicle_id = ? AND date >= ? ORDER BY date DESC, id DESC", (vehicle_id, since)
    ).fetchall()

    km_total = 0.0
    minutes_total = 0
    timed_km = 0.0  # kilometres of the trips that have both times: the base of the average speed
    longest: dict | None = None
    cats: dict[str, dict] = {}
    buckets = [0] * (len(LENGTH_EDGES) + 1)
    heat = [[0] * len(BLOCKS) for _ in range(7)]
    untimed = 0
    for r in rows:
        km = trips.trip_distance(r) or 0.0
        km_total += km
        cat = cats.setdefault(r["category"], {"n": 0, "km": 0.0})
        cat["n"] += 1
        cat["km"] += km
        if longest is None or km > longest["km"]:
            longest = {"km": km, "date": r["date"], "from": r["start_place"], "to": r["end_place"]}
        if km:
            buckets[length_bucket(shown(km))] += 1
        gap = _minutes(r["start_time"], r["end_time"])
        if gap:
            minutes_total += gap
            timed_km += km
        hour = _hour(r["start_time"])
        try:
            weekday = date.fromisoformat((r["date"] or "")[:10]).weekday()
        except ValueError:
            weekday = None
        if hour is None or weekday is None:
            untimed += 1
        else:
            heat[weekday][next(i for i, (a, b) in enumerate(BLOCKS) if a <= hour < b)] += 1

    n = len(rows)
    return {
        "n": n,
        "km": km_total,
        "avg_km": km_total / n if n else None,
        "longest": longest if longest and longest["km"] else None,
        "minutes": minutes_total,
        "avg_kmh": timed_km / (minutes_total / 60) if minutes_total else None,
        "cats": [
            {"key": k, **v, "pct": v["km"] / km_total * 100 if km_total else 0} for k, v in sorted(cats.items(), key=lambda i: -i[1]["km"])
        ],
        "buckets": buckets,
        "heat": heat,
        "heat_max": max((c for row in heat for c in row), default=0),
        "untimed": untimed,
        "style": driving_style(conn, [r["id"] for r in rows if r["source"] != "manual"][:MAX_STYLE_TRIPS]),
    }


def driving_style(conn: sqlite3.Connection, trip_ids: list[int]) -> dict | None:
    """Driving style over many drives: hard brakings per 100 km, average speed while moving, the share of standing, top speed.
    Only drives with time stamps count (None when there is none)."""
    if not trip_ids:
        return None
    marks = ",".join("?" for _ in trip_ids)
    by_trip: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for p in conn.execute(f"SELECT trip_id, lat, lon, ts FROM trip_points WHERE trip_id IN ({marks}) ORDER BY trip_id, seq", trip_ids):
        by_trip[p["trip_id"]].append(p)
    used = 0
    km = hard = 0.0
    moving_s = speed_weight = idle_weight = minutes_sum = top = 0.0
    for points in by_trip.values():
        s = trips.stats(points)
        if not s["minutes"] or not s["km"]:
            continue
        used += 1
        km += s["km"]
        hard += s["hard_brakes"] or 0
        if s["moving_min"]:
            moving_s += s["moving_min"] * 60
            speed_weight += (s["moving_kmh"] or 0) * s["moving_min"] * 60
        if s["idle_pct"] is not None:
            idle_weight += s["idle_pct"] * s["minutes"]
        minutes_sum += s["minutes"]
        top = max(top, s["max_kmh"] or 0)
    if not used or not km:
        return None
    return {
        "trips": used,
        "km": km,
        "hard_per_100": hard / km * 100,
        "moving_kmh": speed_weight / moving_s if moving_s else None,
        "idle_pct": round(idle_weight / minutes_sum) if minutes_sum else None,
        "top_kmh": top or None,
    }
