"""Place names for the start and the end of a trip.

A trip made from the positions of a plugin starts out with coordinates ("52.50000, 13.40000"). While **map info** is switched on (Settings ->
System -> Map info) the app asks OpenStreetMap (Nominatim) once for the street and place of such a spot and writes that into the trip. Only
the coordinates of the start and the end of a trip are sent, never anything else; OpenStreetMap sees the server's IP address, not the phone or
the Home Assistant address. Every answer is kept (``place_names``), a spot is never asked for twice. A name you typed yourself is never touched.
Nothing happens while the map info is off: the coordinates stay.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from datetime import UTC, datetime

import requests

from . import config, db, status
from .tiles import USER_AGENT

log = logging.getLogger(__name__)

SOURCE = "https://nominatim.openstreetmap.org/reverse"
COORD = re.compile(r"^(-?\d{1,3}\.\d+), (-?\d{1,3}\.\d+)$")  # how a trip writes a spot it has no name for
TIMEOUT = 8
PER_RUN = 100  # lookups in one background run (the usage policy allows one request a second); the next visit continues
GAP = 1.1
MAX_CACHE = 5000
_running = threading.Lock()


def _key(lat: float, lon: float, lang: str) -> str:
    return f"{lang}|{lat:.4f},{lon:.4f}"  # about 11 m: the same door, the same name


def short(data: dict) -> str:
    """Only the place of an answer of Nominatim: ``Berlin`` (no street, no house number): a trip goes from place to place."""
    addr = data.get("address") if isinstance(data.get("address"), dict) else {}
    city = next(
        (
            addr[k]
            for k in ("city", "town", "village", "hamlet", "suburb", "municipality", "county")
            if isinstance(addr.get(k), str) and addr[k]
        ),
        "",
    )
    if not city:
        name = data.get("name") if isinstance(data.get("name"), str) else ""
        shown = data.get("display_name") if isinstance(data.get("display_name"), str) else ""
        parts = [p.strip() for p in shown.split(",") if p.strip()]
        city = name or (parts[-3] if len(parts) >= 3 else parts[0] if parts else "")
    return city[:120]


def _tidy_old() -> None:
    """Names kept earlier as ``Street, Place`` become just the place (also in the trips they were written into)."""
    with db.tx() as conn:
        for r in conn.execute("SELECT key, name FROM place_names WHERE name LIKE '%, %'").fetchall():
            new = r["name"].rsplit(", ", 1)[1]
            conn.execute("UPDATE trips SET start_place = ? WHERE start_place = ?", (new, r["name"]))
            conn.execute("UPDATE trips SET end_place = ? WHERE end_place = ?", (new, r["name"]))
            conn.execute("UPDATE place_names SET name = ? WHERE key = ?", (new, r["key"]))


def lookup(lat: float, lon: float, lang: str) -> str | None:
    """One question to OpenStreetMap; None when it cannot answer (nothing is stored then, the next run tries again)."""
    try:
        r = requests.get(
            SOURCE,
            params={"format": "jsonv2", "lat": f"{lat:.6f}", "lon": f"{lon:.6f}", "zoom": 16, "addressdetails": 1, "accept-language": lang},
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )
        data = r.json() if r.status_code == 200 else None
    except (requests.RequestException, ValueError):
        return None
    return short(data) or None if isinstance(data, dict) else None


def _from_cache(conn, lat: float, lon: float, lang: str) -> str | None:
    row = conn.execute("SELECT name FROM place_names WHERE key = ?", (_key(lat, lon, lang),)).fetchone()
    return row["name"] if row else None


def fill_missing() -> int:
    """Give trips with coordinates a place name (when the map info is on). Returns how many spots got a name. Safe to call any time."""
    if not _running.acquire(blocking=False):
        return 0
    done = 0
    try:
        with db.tx() as conn:
            if not status.map_tiles_enabled(conn):
                return 0
        _tidy_old()
        with db.tx() as conn:
            todo = []
            for t in conn.execute("SELECT id, start_place, end_place FROM trips ORDER BY id DESC LIMIT 1500").fetchall():
                for col in ("start_place", "end_place"):
                    m = COORD.match(t[col] or "")
                    if m:
                        todo.append((t["id"], col, float(m.group(1)), float(m.group(2))))
        lang = config.language()
        asked = 0
        for tid, col, lat, lon in todo:
            if asked >= PER_RUN:
                break
            with db.tx() as conn:
                name = _from_cache(conn, lat, lon, lang)
            if name is None:
                if asked:
                    time.sleep(GAP)
                asked += 1
                name = lookup(lat, lon, lang)
                if not name:
                    continue
                with db.tx() as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO place_names(key, name, created_at) VALUES(?,?,?)",
                        (_key(lat, lon, lang), name, datetime.now(UTC).isoformat(timespec="seconds")),
                    )
                    conn.execute(
                        "DELETE FROM place_names WHERE key NOT IN (SELECT key FROM place_names ORDER BY created_at DESC LIMIT ?)",
                        (MAX_CACHE,),
                    )
            with db.tx() as conn:  # only while it still is the coordinates: a name typed by hand stays
                cur = conn.execute(f"UPDATE trips SET {col} = ? WHERE id = ? AND {col} = ?", (name, tid, f"{lat:.5f}, {lon:.5f}"))
                done += cur.rowcount
    except Exception:  # a failing lookup must never break the page or the plugin
        log.exception("Place names could not be filled")
    finally:
        _running.release()
    return done


def kick() -> None:
    """Fill in the background (cheap when nothing is to do or the map info is off)."""
    threading.Thread(target=lambda: (time.sleep(1.0), fill_missing()), name="place-names", daemon=True).start()


# ---- the spot where the car stands now: place and, small below, the street (kept like the trip places, asked for once per spot)
_here_running = threading.Lock()


def street(data: dict) -> str:
    """``Hauptstraße 12`` of an answer of Nominatim (street and house number, whatever exists)."""
    addr = data.get("address") if isinstance(data.get("address"), dict) else {}
    road = next((addr[k] for k in ("road", "pedestrian", "footway", "path", "cycleway") if isinstance(addr.get(k), str) and addr[k]), "")
    number = addr.get("house_number") if isinstance(addr.get("house_number"), str) else ""
    return f"{road} {number}".strip()[:120] if road else ""


def here_cached(conn, lat: float, lon: float) -> tuple[str, str] | None:
    """(place, street) of a spot when it was looked up before."""
    row = conn.execute("SELECT name FROM place_names WHERE key = ?", ("here:" + _key(lat, lon, config.language()),)).fetchone()
    if not row:
        return None
    town, _sep, road = row["name"].partition("\t")
    return town, road


def _here_lookup(lat: float, lon: float, lang: str) -> tuple[str, str] | None:
    try:
        r = requests.get(
            SOURCE,
            params={"format": "jsonv2", "lat": f"{lat:.6f}", "lon": f"{lon:.6f}", "zoom": 18, "addressdetails": 1, "accept-language": lang},
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )
        data = r.json() if r.status_code == 200 else None
    except (requests.RequestException, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    town = short(data)
    return (town, street(data)) if town else None


def kick_here(lat: float, lon: float) -> None:
    """Look up the spot of the car in the background (only with the map info on); the next view shows it."""

    def work():
        if not _here_running.acquire(blocking=False):
            return
        try:
            lang = config.language()
            with db.tx() as conn:
                if not status.map_tiles_enabled(conn) or here_cached(conn, lat, lon):
                    return
            found = _here_lookup(lat, lon, lang)
            if found:
                with db.tx() as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO place_names(key, name, created_at) VALUES(?,?,?)",
                        ("here:" + _key(lat, lon, lang), f"{found[0]}\t{found[1]}", datetime.now(UTC).isoformat(timespec="seconds")),
                    )
        except Exception:
            log.exception("The place of the car could not be looked up")
        finally:
            _here_running.release()

    threading.Thread(target=work, name="place-here", daemon=True).start()
