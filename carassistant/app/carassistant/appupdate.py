"""Is there a newer Car Assistant, and are there package updates? (shown as the indicator at the foot of the side bar)

Opt-in (Settings > System > Updates): once a day - or when the person presses *Check now* - the app reads ONE small file of the public project
(``release.json`` on the main branch) and remembers its version. Nothing else is sent; no data about the installation leaves it.
Package updates (plugins, integrations) come from the sources the app already reads (``sources.auto``); this module only counts them.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

from . import __version__, addons, db, sources

log = logging.getLogger(__name__)

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
        log.info("Update check: the file of the project could not be read (no connection or no answer)")
        return False
    log.info("Update check: the newest version is %s", version)
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


def package_updates(conn: sqlite3.Connection) -> list[dict]:
    """Installed plugins and integrations (of every car) for which their source offers a newer version."""
    rows = conn.execute(
        "SELECT a.*, v.name AS car, v.slug AS car_slug FROM vehicle_addons a JOIN vehicles v ON v.id = a.vehicle_id "
        "WHERE a.status != 'missing' ORDER BY v.name COLLATE NOCASE, a.id"
    ).fetchall()
    offered = addons._newer_versions(conn, rows)
    out = []
    for r in rows:
        manifest = json.loads(r["manifest"])
        if sources.is_newer(offered.get(r["id"], ""), manifest.get("version", "")):
            out.append(
                {
                    "kind": r["kind"],
                    "name": manifest.get("name") or r["addon_id"],
                    "car": r["car"],
                    "car_slug": r["car_slug"],
                    "installed": manifest.get("version", ""),
                    "latest": offered[r["id"]],
                }
            )
    return out


def plugin_updates(conn: sqlite3.Connection) -> int:
    return len(package_updates(conn))


def status(conn: sqlite3.Connection) -> dict:
    latest = db.get_setting(conn, "app.update.latest", "")
    return {
        "enabled": enabled(conn),
        "latest": latest,
        "stage": db.get_setting(conn, "app.update.stage", ""),
        "checked": db.get_setting(conn, "app.update.checked", ""),
        "newer": bool(latest) and sources.is_newer(latest, __version__),
        "plugins": plugin_updates(conn),
        "packages": package_updates(conn),
    }


def _installed(conn: sqlite3.Connection) -> tuple:
    """What is installed (which package, in which version - its checksum -, from which source): when it changes, the remembered answer is stale."""
    return tuple(tuple(r) for r in conn.execute("SELECT id, pkg_sha, status, source_id FROM vehicle_addons ORDER BY id"))


def pending() -> dict:
    """What the side bar shows: ``{"app": newer version or "", "plugins": number, "plugin_list": one line per package, "plugins_car": slug}``.

    Remembered for a minute (every page asks) - and not a second longer than what is installed stays the same: installing, updating or
    removing a package shows at once. ``plugins_car`` is the car whose plugin page lists them all (empty when they are on several cars).
    """
    now = time.monotonic()
    with db.tx() as conn:
        installed = _installed(conn)
        if _cache["value"] is None or now - _cache["at"] > 60 or _cache.get("installed") != installed:
            s = status(conn)
            cars = {p["car_slug"] for p in s["packages"]}
            _cache.update(
                at=now,
                installed=installed,
                value={
                    "app": s["latest"] if s["newer"] else "",
                    "plugins": s["plugins"],
                    "plugin_list": "\n".join(f"{p['name']} · {p['car']}: {p['installed']} → {p['latest']}" for p in s["packages"]),
                    "plugins_car": next(iter(cars)) if len(cars) == 1 else "",
                },
            )
    return _cache["value"]
