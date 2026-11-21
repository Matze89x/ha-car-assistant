"""Map tiles through Car Assistant itself.

The browser asks this app for ``/tiles/<z>/<x>/<y>.png``; the app fetches the tile from OpenStreetMap once, with a User-Agent that names
the project (the OSM tile usage policy requires an identifying User-Agent or Referer - a browser inside the Home Assistant app often
sends neither), and keeps it on disk for a week. Consequences: OpenStreetMap never sees the phone or the Home Assistant address, at most
two requests run at once, and a map seen before also works without internet. Only used while the map is switched on (Settings -> Map).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path

import requests

from . import __version__, config

log = logging.getLogger(__name__)

SOURCE = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
USER_AGENT = f"CarAssistant/{__version__} (+https://github.com/Matze89x/ha-car-assistant)"
MAX_AGE = 7 * 24 * 3600  # the policy asks for at least a week
MAX_CACHE = 200 * 1024 * 1024
MAX_TILE = 512 * 1024
TIMEOUT = 8
_slots = threading.Semaphore(2)  # the policy allows two connections at most
_writes = 0
_lock = threading.Lock()


def valid(z: int, x: int, y: int) -> bool:
    return 0 <= z <= 19 and 0 <= x < (1 << z) and 0 <= y < (1 << z)


def path_of(z: int, x: int, y: int) -> Path:
    return config.data_dir() / "cache" / "tiles" / str(z) / str(x) / f"{y}.png"


def _fetch(z: int, x: int, y: int) -> bytes | None:
    with _slots:
        try:
            r = requests.get(SOURCE.format(z=z, x=x, y=y), headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        except requests.RequestException:
            return None
    if r.status_code != 200 or not r.content or len(r.content) > MAX_TILE or r.headers.get("content-type", "").split(";")[0] != "image/png":
        log.warning("Map tile %s/%s/%s: OpenStreetMap answered %s", z, x, y, r.status_code)
        return None
    return r.content


def _prune() -> None:
    """Keep the cache below its limit: remove the least recently written tiles first."""
    root = config.data_dir() / "cache" / "tiles"
    files = [(p.stat().st_mtime, p.stat().st_size, p) for p in root.rglob("*.png")]
    total = sum(f[1] for f in files)
    if total <= MAX_CACHE:
        return
    for _mtime, size, p in sorted(files):
        p.unlink(missing_ok=True)
        total -= size
        if total <= MAX_CACHE * 0.8:
            break


def get(z: int, x: int, y: int) -> bytes | None:
    """The tile from the cache, or fetched and stored; a stale copy is used when OpenStreetMap cannot be reached."""
    global _writes
    path = path_of(z, x, y)
    stale = None
    try:
        age = time.time() - path.stat().st_mtime
        data = path.read_bytes()
        if age < MAX_AGE:
            return data
        stale = data
    except OSError:
        pass
    fresh = _fetch(z, x, y)
    if fresh is None:
        return stale
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_bytes(fresh)
    tmp.replace(path)
    with _lock:
        _writes += 1
        due = _writes % 200 == 0
    if due:
        _prune()
    return fresh
