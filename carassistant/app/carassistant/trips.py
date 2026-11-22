"""Trip log: GPX import, distance maths, CSV / PDF / GPX export.

The PDF is an *overview of recorded data*, not a tax-authority-approved logbook (those have strict formal rules).
"""

from __future__ import annotations

import csv
import io
import math
import sqlite3
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from pathlib import Path

from defusedxml import ElementTree as ET  # a GPX file is untrusted input: no entity tricks
from defusedxml.common import DefusedXmlException

MAX_GPX_BYTES = 10 * 1024 * 1024


class GpxError(ValueError):
    pass


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dlmb = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def track_distance_km(points: list[tuple[float, float, str | None]]) -> float:
    return sum(haversine_km(a[0], a[1], b[0], b[1]) for a, b in pairwise(points))


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_gpx(data: bytes) -> list[tuple[float, float, str | None]]:
    """Return ``(lat, lon, iso_time_or_None)`` for the first track (or route) of a GPX file."""
    if len(data) > MAX_GPX_BYTES:
        raise GpxError("err.gpx_big")
    head = data[:4096].lower()
    if b"<!doctype" in head or b"<!entity" in data.lower():
        raise GpxError("err.gpx_invalid")
    try:
        root = ET.fromstring(data)
    except (ET.ParseError, DefusedXmlException):
        raise GpxError("err.gpx_invalid") from None
    points: list[tuple[float, float, str | None]] = []
    for elem in root.iter():
        if _localname(elem.tag) not in ("trkpt", "rtept"):
            continue
        try:
            lat, lon = float(elem.attrib["lat"]), float(elem.attrib["lon"])
        except (KeyError, ValueError):
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        ts = None
        for child in elem:
            if _localname(child.tag) == "time" and child.text:
                ts = child.text.strip()
        points.append((lat, lon, ts))
    if len(points) < 2:
        raise GpxError("err.gpx_empty")
    return points


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _place(lat: float, lon: float) -> str:
    return f"{lat:.5f}, {lon:.5f}"


def import_gpx(conn: sqlite3.Connection, vehicle_id: int, data: bytes, category: str = "private") -> int:
    points = parse_gpx(data)
    first, last = _parse_ts(points[0][2]), _parse_ts(points[-1][2])
    day = (first or datetime.now(UTC)).date().isoformat()
    distance = round(track_distance_km(points), 2)
    trip_id = conn.execute(
        """INSERT INTO trips(vehicle_id, date, start_time, end_time, start_place, end_place, category, source, distance_km)
           VALUES(?,?,?,?,?,?,?, 'gpx', ?)""",
        (
            vehicle_id,
            day,
            first.strftime("%H:%M") if first else None,
            last.strftime("%H:%M") if last else None,
            _place(points[0][0], points[0][1]),
            _place(points[-1][0], points[-1][1]),
            category,
            distance,
        ),
    ).lastrowid
    # keep the stored track reasonably small: at most ~2000 points, always including the last one
    step = max(1, len(points) // 2000)
    sampled = points[::step]
    if sampled[-1] != points[-1]:
        sampled.append(points[-1])
    conn.executemany(
        "INSERT INTO trip_points(trip_id, seq, lat, lon, ts) VALUES(?,?,?,?,?)",
        [(trip_id, i, p[0], p[1], p[2]) for i, p in enumerate(sampled)],
    )
    return trip_id


TRIP_GAP = timedelta(minutes=10)  # no point for this long = the drive is over
TRIP_MIN_KM = 0.3
TRIP_MIN_POINTS = 3


def from_track(conn: sqlite3.Connection, vehicle_id: int, now: datetime | None = None) -> int:
    """Turn the positions a plugin delivered (``vehicle_track``) into trips of the log book. A drive is a run of points with no gap
    over ten minutes; it becomes a trip once nothing new has come for that long. Runs that are too short are dropped. Returns the number of
    trips made. Safe to call as often as you like."""
    now = now or datetime.now(UTC)
    rows = conn.execute(
        "SELECT id, ts, lat, lon FROM vehicle_track WHERE vehicle_id = ? AND trip_id IS NULL ORDER BY ts, id", (vehicle_id,)
    ).fetchall()
    ign = conn.execute("SELECT value, updated FROM live WHERE vehicle_id = ? AND key = 'ignition'", (vehicle_id,)).fetchone()
    runs: list[list[sqlite3.Row]] = []
    for row in rows:
        when = datetime.fromisoformat(row["ts"])
        if runs and when - datetime.fromisoformat(runs[-1][-1]["ts"]) <= TRIP_GAP:
            runs[-1].append(row)
        else:
            runs.append([row])
    made = 0
    for run in runs:
        last_ts = run[-1]["ts"]
        parked = bool(
            ign and ign["value"] == "off" and (_parse_ts(ign["updated"]) or now) >= datetime.fromisoformat(last_ts)
        )  # the ignition went off after the last point: the drive is over now
        if now - datetime.fromisoformat(last_ts) <= TRIP_GAP and not parked:
            continue  # still driving (or just stopped): wait
        points = [(r["lat"], r["lon"], r["ts"]) for r in run]
        distance = round(track_distance_km(points), 2)
        ids = [(r["id"],) for r in run]
        if len(run) < TRIP_MIN_POINTS or distance < TRIP_MIN_KM:
            conn.executemany("UPDATE vehicle_track SET trip_id = 0 WHERE id = ?", ids)
            continue
        first, last = datetime.fromisoformat(points[0][2]).astimezone(), datetime.fromisoformat(points[-1][2]).astimezone()
        trip_id = conn.execute(
            """INSERT INTO trips(vehicle_id, date, start_time, end_time, start_place, end_place, category, source, distance_km)
               VALUES(?,?,?,?,?,?, 'private', 'track', ?)""",
            (
                vehicle_id,
                first.date().isoformat(),
                first.strftime("%H:%M"),
                last.strftime("%H:%M"),
                _place(points[0][0], points[0][1]),
                _place(points[-1][0], points[-1][1]),
                distance,
            ),
        ).lastrowid
        step = max(1, len(points) // 2000)
        sampled = points[::step]
        if sampled[-1] != points[-1]:
            sampled.append(points[-1])
        conn.executemany(
            "INSERT INTO trip_points(trip_id, seq, lat, lon, ts) VALUES(?,?,?,?,?)",
            [(trip_id, i, p[0], p[1], p[2]) for i, p in enumerate(sampled)],
        )
        conn.executemany(f"UPDATE vehicle_track SET trip_id = {int(trip_id)} WHERE id = ?", ids)
        made += 1
    attach_summaries(conn, vehicle_id, now)
    if made:
        from . import places

        places.kick()  # place names instead of coordinates, when the map info is on
        from . import notify

        notify.trip_ended()  # "trip finished" goes out now, not at the next 6-hourly check
    return made


def trip_points(conn: sqlite3.Connection, trip_id: int) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM trip_points WHERE trip_id = ? ORDER BY seq", (trip_id,)).fetchall()


def trip_distance(row: sqlite3.Row) -> float | None:
    if row["distance_km"] is not None:
        return float(row["distance_km"])
    if row["start_km"] is not None and row["end_km"] is not None:
        return float(row["end_km"] - row["start_km"])
    return None


def parse_range(start: str | None, end: str | None) -> tuple[str, str]:
    """Defaults to the current year; swaps reversed bounds."""
    year = date.today().year
    try:
        s = date.fromisoformat(start).isoformat() if start else f"{year}-01-01"
        e = date.fromisoformat(end).isoformat() if end else f"{year}-12-31"
    except ValueError:
        s, e = f"{year}-01-01", f"{year}-12-31"
    return (s, e) if s <= e else (e, s)


def trips_in_range(conn: sqlite3.Connection, vehicle_id: int, start: str, end: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM trips WHERE vehicle_id = ? AND date BETWEEN ? AND ? ORDER BY date ASC, COALESCE(start_time, ''), id",
        (vehicle_id, start, end),
    ).fetchall()


def totals(rows: list[sqlite3.Row]) -> dict[str, float]:
    result: dict[str, float] = {}
    for row in rows:
        d = trip_distance(row)
        if d:
            result[row["category"]] = result.get(row["category"], 0.0) + d
    result["total"] = sum(v for k, v in result.items() if k != "total")
    return result


def csv_bytes(rows: list[sqlite3.Row], labels: dict[str, str]) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";")
    writer.writerow([labels[k] for k in ("date", "start", "end", "from", "to", "start_km", "end_km", "distance", "category", "purpose")])
    for r in rows:
        d = trip_distance(r)
        writer.writerow(
            [
                r["date"],
                r["start_time"] or "",
                r["end_time"] or "",
                r["start_place"] or "",
                r["end_place"] or "",
                r["start_km"] if r["start_km"] is not None else "",
                r["end_km"] if r["end_km"] is not None else "",
                f"{d:.1f}".replace(".", ",") if d is not None else "",
                labels.get("cat." + r["category"], r["category"]),
                r["purpose"] or "",
            ]
        )
    return b"\xef\xbb\xbf" + out.getvalue().encode("utf-8")  # BOM so Excel detects UTF-8


_FONT_CANDIDATES = (
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


def pdf_bytes(vehicle: sqlite3.Row, rows: list[sqlite3.Row], start: str, end: str, labels: dict[str, str]) -> bytes:
    from fpdf import FPDF

    pdf = FPDF(orientation="L", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    regular = next((p for p in _FONT_CANDIDATES if Path(p).exists()), None)
    if regular:
        pdf.add_font("body", "", regular)
        family = "body"

        def clean(text: str) -> str:
            return text
    else:
        family = "Helvetica"

        def clean(text: str) -> str:  # core fonts are latin-1 only
            return text.encode("latin-1", "replace").decode("latin-1")

    pdf.set_font(family, size=14)
    plate = f" ({vehicle['plate']})" if vehicle["plate"] else ""
    pdf.cell(0, 8, clean(f"{labels['title']} – {vehicle['name']}{plate}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(family, size=9)
    pdf.cell(0, 5, clean(f"{labels['period']}: {start} – {end}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    columns = [
        ("date", 22), ("start", 14), ("end", 14), ("from", 52), ("to", 52),
        ("start_km", 20), ("end_km", 20), ("distance", 18), ("category", 24), ("purpose", 41),
    ]  # fmt: skip
    pdf.set_font(family, size=8)
    pdf.set_fill_color(230, 230, 230)
    for key, width in columns:
        pdf.cell(width, 6, clean(labels[key]), border=1, fill=True)
    pdf.ln()
    for r in rows:
        d = trip_distance(r)
        cells = [
            r["date"], r["start_time"] or "", r["end_time"] or "", r["start_place"] or "", r["end_place"] or "",
            "" if r["start_km"] is None else str(r["start_km"]), "" if r["end_km"] is None else str(r["end_km"]),
            "" if d is None else f"{d:.1f}", labels.get("cat." + r["category"], r["category"]), r["purpose"] or "",
        ]  # fmt: skip
        for (_, width), text in zip(columns, cells, strict=True):
            limit = max(4, int(width / 1.8))
            pdf.cell(width, 5.5, clean(text if len(text) <= limit else text[: limit - 1] + "…"), border=1)
        pdf.ln()
    pdf.ln(3)
    sums = totals(rows)
    pdf.set_font(family, size=9)
    parts = [f"{labels['cat.' + k]}: {v:.1f} km" for k, v in sums.items() if k != "total"]
    pdf.cell(0, 5, clean(f"{labels['total']}: {sums['total']:.1f} km   ({', '.join(parts)})"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font(family, size=7)
    pdf.multi_cell(0, 4, clean(labels["disclaimer"]))
    return bytes(pdf.output())


def gpx_bytes(trip: sqlite3.Row, points: list[sqlite3.Row]) -> bytes:
    from xml.sax.saxutils import escape

    name = escape(f"{trip['date']} {trip['start_place'] or ''} → {trip['end_place'] or ''}".strip())
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="Car Assistant" xmlns="http://www.topografix.com/GPX/1/1">',
        f"<trk><name>{name}</name><trkseg>",
    ]
    for p in points:
        t = f"<time>{escape(p['ts'])}</time>" if p["ts"] else ""
        lines.append(f'<trkpt lat="{p["lat"]:.6f}" lon="{p["lon"]:.6f}">{t}</trkpt>')
    lines.append("</trkseg></trk></gpx>")
    return "\n".join(lines).encode("utf-8")


MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
    "de": ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"],
}


def by_month(conn: sqlite3.Connection, vehicle_id: int, lang: str, limit: int = 2000) -> list[dict]:
    """All trips of a vehicle grouped by month (newest first): ``{key, title, rows, km}``."""
    names = MONTHS.get(lang, MONTHS["en"])
    groups: dict[str, dict] = {}
    for row in conn.execute("SELECT * FROM trips WHERE vehicle_id = ? ORDER BY date DESC, id DESC LIMIT ?", (vehicle_id, limit)):
        key = (row["date"] or "")[:7] or "0000-00"
        month = int(key[5:7] or 0)
        title = f"{names[month - 1]} {key[:4]}" if 1 <= month <= 12 else key
        group = groups.setdefault(key, {"key": key, "title": title, "rows": [], "km": 0.0})
        group["rows"].append(row)
        group["km"] += trip_distance(row) or 0.0
    return list(groups.values())


HARD_BRAKE_MS2 = 3.0  # a deceleration from here on counts as a hard braking
IDLE_KMH = 3.0


def stats(points: list[sqlite3.Row]) -> dict:
    """What a recorded drive tells (needs the time stamps for the speeds): duration, average / top speed, the driving style
    (strongest acceleration and braking in m/s², hard brakings, average speed while moving, standing share) and the points with their speed."""
    pts: list[tuple[float, float, datetime | None]] = []
    for p in points:
        pts.append((p["lat"], p["lon"], _parse_ts(p["ts"]) if "ts" in p.keys() else None))  # noqa: SIM118 (a Row)
    out_points: list[list[float]] = []
    top = km = 0.0
    speeds: list[tuple[float, float]] = []  # (km/h, seconds of the leg)
    acc = dec = 0.0
    hard = 0
    prev_speed: float | None = None
    for i, (lat, lon, when) in enumerate(pts):
        speed = 0.0
        if i:
            plat, plon, pwhen = pts[i - 1]
            leg = haversine_km(plat, plon, lat, lon)
            km += leg
            if when and pwhen and when > pwhen:
                dt = (when - pwhen).total_seconds()
                speed = leg / dt * 3600
                if speed < 250:
                    top = max(top, speed)
                    speeds.append((speed, dt))
                    if prev_speed is not None:
                        a = (speed - prev_speed) / 3.6 / dt  # m/s²
                        acc, dec = max(acc, a), min(dec, a)
                        hard += 1 if a <= -HARD_BRAKE_MS2 else 0
                    prev_speed = speed
        out_points.append([round(lat, 6), round(lon, 6), round(speed, 1)])
    first, last = (pts[0][2], pts[-1][2]) if pts else (None, None)
    duration = (last - first).total_seconds() / 60 if first and last and last > first else None
    moving = [(v, dt) for v, dt in speeds if v >= IDLE_KMH]
    total_s = sum(dt for _, dt in speeds)
    moving_s = sum(dt for _, dt in moving)
    return {
        "points": out_points,
        "km": round(km, 2),
        "minutes": round(duration, 1) if duration else None,
        "avg_kmh": round(km / (duration / 60), 1) if duration else None,
        "max_kmh": round(top, 1) if top else None,
        "moving_kmh": round(sum(v * dt for v, dt in moving) / moving_s, 1) if moving_s else None,
        "idle_pct": round((1 - moving_s / total_s) * 100) if total_s else None,
        "moving_min": round(moving_s / 60) if moving_s else None,
        "acc": round(acc, 1) if speeds else None,
        "dec": round(dec, 1) if speeds else None,
        "hard_brakes": hard if speeds else None,
        "n": len(pts),
        "start": first.astimezone().strftime("%H:%M") if first else None,
        "end": last.astimezone().strftime("%H:%M") if last else None,
    }


SUMMARY_MATCH = timedelta(minutes=20)  # an on-board trip belongs to the trip that ended this close to it
SUMMARY_KEEP = timedelta(days=3)  # one that finds no trip in this time is dropped


def attach_summaries(conn: sqlite3.Connection, vehicle_id: int, now: datetime | None = None) -> int:
    """Give the values of the car's own trip computer (consumption, average speed, duration; sent with ``trip_summary``) to the trip that
    ended at that time. Safe to call as often as you like; returns how many were attached."""
    now = now or datetime.now(UTC)
    waiting = conn.execute("SELECT * FROM trip_summaries WHERE vehicle_id = ? ORDER BY ts", (vehicle_id,)).fetchall()
    if not waiting:
        return 0
    candidates = []
    for r in conn.execute(
        "SELECT id, date, end_time FROM trips WHERE vehicle_id = ? AND end_time IS NOT NULL AND consumption_l100 IS NULL AND avg_kmh IS NULL "
        "AND bc_minutes IS NULL ORDER BY date DESC, id DESC LIMIT 200",
        (vehicle_id,),
    ):
        try:
            candidates.append((r["id"], datetime.fromisoformat(f"{r['date']}T{r['end_time']}").astimezone()))
        except ValueError:
            continue
    done = 0
    for item in waiting:
        when = datetime.fromisoformat(item["ts"]).astimezone()
        best = min(((abs(end - when), tid) for tid, end in candidates), default=None)
        if best and best[0] <= SUMMARY_MATCH:
            conn.execute(
                "UPDATE trips SET consumption_l100 = ?, avg_kmh = ?, bc_minutes = ? WHERE id = ?",
                (item["consumption"], item["avg_kmh"], item["minutes"], best[1]),
            )
            candidates = [c for c in candidates if c[0] != best[1]]
            conn.execute("DELETE FROM trip_summaries WHERE id = ?", (item["id"],))
            done += 1
        elif now - when > SUMMARY_KEEP:
            conn.execute("DELETE FROM trip_summaries WHERE id = ?", (item["id"],))
    return done
