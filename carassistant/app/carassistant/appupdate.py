"""Is there a newer Car Assistant, and are there package updates? (shown as the indicator at the foot of the side bar)

Opt-in (Settings > System > Updates): once a day - or when the person presses *Check now* - the app reads ONE small file of the public project
(``release.json`` on the main branch) and remembers its version. Nothing else is sent; no data about the installation leaves it.
Package updates (plugins, integrations) come from the sources the app already reads (``sources.auto``); this module only counts them.
"""

from __future__ import annotations

import json
import sqlite3
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

from . import __version__, addons, db, sources

SETTING = "app.update.check"
URL = "https://raw.githubusercontent.com/Matze89x/ha-car-assistant/main/release.json"
_cache: dict = {"at": 0.0, "value": None}


def enabled(conn: sqlite3.Connection) -> bool:
    return db.get_setting(conn, SETTING, "") == "1"


def check(conn: sqlite3.Connection) -> bool:
    """Read the file and remember the version; False when it could not be read (the old value stays)."""
    try:
        request = urllib.request.Request(URL, headers={"User-Agent": "car-assistant-update-check"})
        with urllib.request.urlopen(request, timeout=10) as answer:  # noqa: S310 (a fixed https address)
            data = json.loads(answer.read(200_000).decode("utf-8"))
        version = str(data.get("version", "")).strip()
        if not version or not all(p.isdigit() for p in version.split(".")):
            return False
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return False
    db.set_setting(conn, "app.update.latest", version)
    db.set_setting(conn, "app.update.stage", str(data.get("stage", ""))[:20])
    db.set_setting(conn, "app.update.checked", datetime.now(UTC).isoformat(timespec="minutes"))
    forget()
    return True


def due(conn: sqlite3.Connection, now: float | None = None) -> bool:
    """Switched on and the last look is more than a day old."""
    if not enabled(conn):
        return False
    stamp = db.get_setting(conn, "app.update.checked", "")
    try:
        last = datetime.fromisoformat(stamp).timestamp()
    except ValueError:
        return True
    return (now or time.time()) - last >= 24 * 3600


def forget() -> None:
    _cache["value"] = None


def plugin_updates(conn: sqlite3.Connection) -> int:
    rows = conn.execute("SELECT * FROM vehicle_addons").fetchall()
    offered = addons._newer_versions(conn, rows)
    return sum(1 for r in rows if sources.is_newer(offered.get(r["id"], ""), json.loads(r["manifest"]).get("version", "")))


def status(conn: sqlite3.Connection) -> dict:
    latest = db.get_setting(conn, "app.update.latest", "")
    return {
        "enabled": enabled(conn),
        "latest": latest,
        "stage": db.get_setting(conn, "app.update.stage", ""),
        "checked": db.get_setting(conn, "app.update.checked", ""),
        "newer": bool(latest) and sources.is_newer(latest, __version__),
        "plugins": plugin_updates(conn),
    }


def pending() -> dict:
    """What the side bar shows: ``{"app": newer version or "", "plugins": number}`` - remembered for a minute (every page asks)."""
    now = time.monotonic()
    if _cache["value"] is None or now - _cache["at"] > 60:
        with db.tx() as conn:
            s = status(conn)
        _cache.update(at=now, value={"app": s["latest"] if s["newer"] else "", "plugins": s["plugins"]})
    return _cache["value"]
