"""Is every page fast with the data volume the design book promises (docs/design.md, section 8: 15 cars, thousands of entries per car)?

Builds a temporary installation with 15 demo cars, adds a lot of made-up rows to each (readings, fill-ups, service, trips with points, a GPS track, signal
history, debug lines, parts, appointments ...), opens every page it can reach by its links (in-process, the way the tests do) and tells the slowest.
The made-up data is only for this measurement; nothing of it goes anywhere.

  python tools/perf_sweep.py [--cars 15] [--scale 1] [--limit 110] [--top 12] [--profile /v/demo-diesel/e/fuel]

``--scale 3`` triples every table (a heavier car than most will ever have). Exit code 1 when a page needs more than ``--limit`` milliseconds (a warm
second request). ``--profile PAGE`` prints where the time of that page goes.
"""

from __future__ import annotations

import argparse
import os
import random
import re
import sys
import tempfile
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "carassistant" / "app"))
sys.path.insert(0, str(ROOT / "tools"))

# rows per car at --scale 1
VOLUME = {
    "odometer": 6000,
    "fuel": 900,
    "service": 250,
    "trips": 2500,
    "trip_points": 40_000,
    "vehicle_track": 30_000,
    "signal_history": 30_000,
    "vehicle_logs": 8000,
    "trip_summaries": 2500,
    "parts": 400,
    "mods": 150,
    "appointments": 120,
}


def build(data: Path, cars: int, scale: float) -> list[str]:
    """Seed the demo, make it ``cars`` cars and fill every one of them. Returns the slugs."""
    os.environ.update(CARASSISTANT_DATA=str(data), CARASSISTANT_DEV="1")
    import make_screenshots as ms

    ms.seed(data, "en")
    import demo_data
    from carassistant import config, db, slugs as slugmod  # noqa: F401  (config first: it reads the environment)

    rnd = random.Random(7)
    today = date.today()
    with db.tx() as conn:
        slugs = [r["slug"] for r in conn.execute("SELECT slug FROM vehicles ORDER BY id")]
        n = 0
        while len(slugs) < cars:
            n += 1
            vid = demo_data.create(conn, electric=n % 3 == 0)
            name = f"Extra Car {n}"
            conn.execute("UPDATE vehicles SET name = ?, slug = ? WHERE id = ?", (name, slugmod.unique(conn, name, vid), vid))
            slugs = [r["slug"] for r in conn.execute("SELECT slug FROM vehicles ORDER BY id")]
        ids = [r["id"] for r in conn.execute("SELECT id FROM vehicles ORDER BY id")]
        for vid in ids:
            km = 20_000
            rows = []
            for i in range(int(VOLUME["odometer"] * scale)):
                km += rnd.randint(1, 12)
                rows.append((vid, (today - timedelta(days=3000 - i // 2)).isoformat(), km, "auto" if i % 3 else "manual"))
            conn.executemany("INSERT INTO odometer(vehicle_id, date, odometer_km, source) VALUES(?,?,?,?)", rows)
            conn.executemany(
                "INSERT INTO fuel(vehicle_id, date, odometer_km, amount, price_per_unit, price_total, full_tank, station, notes) VALUES(?,?,?,?,?,?,?,?,?)",
                [
                    (
                        vid,
                        (today - timedelta(days=3000 - i * 3)).isoformat(),
                        20_000 + i * 55,
                        40 + rnd.random() * 10,
                        1.5,
                        70.0,
                        1,
                        f"Station {i % 40}",
                        "",
                    )
                    for i in range(int(VOLUME["fuel"] * scale))
                ],
            )
            conn.executemany(
                "INSERT INTO service(vehicle_id, date, odometer_km, title, workshop, cost, notes) VALUES(?,?,?,?,?,?,?)",
                [
                    (vid, (today - timedelta(days=3000 - i * 11)).isoformat(), 20_000 + i * 400, f"Service job {i}", "Workshop", 80.0, "")
                    for i in range(int(VOLUME["service"] * scale))
                ],
            )
            trip_ids = []
            for i in range(int(VOLUME["trips"] * scale)):
                d = (today - timedelta(days=2000 - i // 2)).isoformat()
                cur = conn.execute(
                    "INSERT INTO trips(vehicle_id, date, start_time, end_time, start_km, end_km, start_place, end_place, category, source, distance_km) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (vid, d, "08:00", "08:40", 30_000 + i * 20, 30_020 + i * 20, "A street", "B street", "private", "auto", 20.0),
                )
                trip_ids.append(cur.lastrowid)
            per = max(1, int(VOLUME["trip_points"] * scale) // max(1, len(trip_ids) // 12))
            for t in trip_ids[::12]:
                conn.executemany(
                    "INSERT OR IGNORE INTO trip_points(trip_id, seq, lat, lon, ts) VALUES(?,?,?,?,?)",
                    [(t, s, 52.5 + s * 1e-4, 13.4 + s * 1e-4, None) for s in range(per)],
                )
            now = datetime.now(UTC).replace(microsecond=0)  # stored with its zone, like everything the app writes
            conn.executemany(
                "INSERT INTO vehicle_track(vehicle_id, ts, lat, lon, speed_kmh) VALUES(?,?,?,?,?)",
                [
                    (vid, (now - timedelta(seconds=10 * i)).isoformat(), 52.5 + i * 1e-5, 13.4 + i * 1e-5, 50.0)
                    for i in range(int(VOLUME["vehicle_track"] * scale))
                ],
            )
            conn.executemany(
                "INSERT INTO signal_history(vehicle_id, addon_id, direction, name, ts, value) VALUES(?,?,?,?,?,?)",
                [
                    (vid, "p-demo", "set", f"field{i % 30}", (now - timedelta(seconds=i)).isoformat(), str(i))
                    for i in range(int(VOLUME["signal_history"] * scale))
                ],
            )
            conn.executemany(
                "INSERT INTO vehicle_logs(vehicle_id, ts, level, source, message) VALUES(?,?,?,?,?)",
                [
                    (vid, (now - timedelta(seconds=i)).isoformat(), "info", "demo", f"line {i}")
                    for i in range(int(VOLUME["vehicle_logs"] * scale))
                ],
            )
            conn.executemany(
                "INSERT INTO trip_summaries(vehicle_id, ts, distance_km, consumption, avg_kmh, minutes) VALUES(?,?,?,?,?,?)",
                [(vid, (now - timedelta(hours=i)).isoformat(), 12.0, 6.0, 40.0, 20) for i in range(int(VOLUME["trip_summaries"] * scale))],
            )
            conn.executemany(
                "INSERT INTO parts(vehicle_id, date, name, part_number, manufacturer, shop, quantity, cost, installed, installed_km, notes) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                [
                    (vid, (today - timedelta(days=i)).isoformat(), f"Part {i}", f"PN{i}", "Maker", "Shop", 1, 9.9, 1, 30_000, "")
                    for i in range(int(VOLUME["parts"] * scale))
                ],
            )
            conn.executemany(
                "INSERT INTO mods(vehicle_id, date, odometer_km, title, cost, notes) VALUES(?,?,?,?,?,?)",
                [
                    (vid, (today - timedelta(days=i * 5)).isoformat(), 30_000, f"Modification {i}", 50.0, "")
                    for i in range(int(VOLUME["mods"] * scale))
                ],
            )
            conn.executemany(
                "INSERT INTO appointments(vehicle_id, kind, title, due_date, month_only, done) VALUES(?,?,?,?,?,?)",
                [
                    (vid, "inspection", f"Appointment {i}", (today + timedelta(days=i * 3 - 200)).isoformat(), 0, 1 if i % 4 else 0)
                    for i in range(int(VOLUME["appointments"] * scale))
                ],
            )
    return slugs


def crawl(client, start: list[str], limit: int = 260) -> list[tuple[float, int, str]]:
    """Every page that can be reached by a link from the start pages: ``(milliseconds of the warm request, bytes, url)``."""
    seen: set[str] = set()
    queue = list(start)
    out: list[tuple[float, int, str]] = []
    skip = (
        "logout",
        "delete",
        "export",
        "/api/",
        "/static",
        "/icon",
        "manifest",
        "download",
        "backup",
        "/docs/",
        "/media/",
        "/photo",
        "/video",
    )
    while queue and len(seen) < limit:
        url = queue.pop(0)
        if url in seen or any(s in url for s in skip):
            continue
        seen.add(url)
        client.get(url)  # cold: templates compiled, caches filled
        t = time.perf_counter()
        r = client.get(url)
        ms = (time.perf_counter() - t) * 1000
        out.append((ms, len(r.content), url))
        if "text/html" in r.headers.get("content-type", ""):
            for href in re.findall(r'href="(/[^"#]*)"', r.text):
                if href not in seen and href.startswith(("/v/", "/settings", "/vehicles", "/about")):
                    queue.append(href)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cars", type=int, default=15)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--limit", type=float, default=110.0)
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--profile", default="")
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        started = time.time()
        slugs = build(Path(tmp), args.cars, args.scale)
        size = sum(f.stat().st_size for f in Path(tmp).rglob("*.db")) / 1e6
        print(f"{len(slugs)} cars built in {time.time() - started:.0f} s, database {size:.0f} MB")
        from fastapi.testclient import TestClient

        from carassistant import web

        with TestClient(web.app) as client:
            first = slugs[0]
            results = crawl(client, [f"/v/{first}", f"/v/{first}/more", "/vehicles", "/about", "/settings/user", "/settings/system"])
            results.sort(reverse=True)
            print(f"{len(results)} pages; slowest (warm):")
            for ms, size_b, url in results[: args.top]:
                print(f"  {ms:7.0f} ms {size_b / 1024:7.0f} KB  {url}")
            print("median", round(sorted(r[0] for r in results)[len(results) // 2]), "ms")
            if args.profile:
                import cProfile
                import pstats

                pr = cProfile.Profile()
                pr.enable()
                for _ in range(3):
                    client.get(args.profile)
                pr.disable()
                pstats.Stats(pr).sort_stats("cumulative").print_stats(25)
            slow = [r for r in results if r[0] > args.limit]
            return 1 if slow else 0


if __name__ == "__main__":
    sys.exit(main())
