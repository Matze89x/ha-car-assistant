"""The connection map: which plugin is connected where, and what flows through it.

Every call a plugin makes to the Plugin API is noted *per signal* (a field of the data, or an interface): the direction (``set`` = the plugin sends,
``get`` = the plugin reads), where it lands in the app (an *area*: dashboard, position, security ... or an installed integration), the last raw value
with its time and a small history of the last few different values. The page *Plugins -> Connections* draws all of it as one map.

It is built to stay light: a call is written to the database only when its value changed (or after 30 seconds), a signal keeps at most ``HISTORY``
values, a plugin may have at most ``MAX_SIGNALS`` signals per car and a value is cut at ``MAX_VALUE`` characters. The map itself is made of one
line per plugin and area (not per signal); the signals are only loaded when somebody opens one.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from datetime import UTC, datetime

HISTORY = 10  # values kept per signal (later a setting)
MAX_SIGNALS = 400  # signals per plugin and car
MAX_VALUE = 2000  # characters of a raw value that are kept
MAX_PER_CALL = 60  # signals noted from one call
SAME_SECONDS = 30  # the same value is written again at most this often
LIVE_SECONDS = 120  # "just now": a connection seen within this time is drawn live
RECENT_SECONDS = 86400  # a connection seen within a day is drawn as active, older ones as idle

# where a field of ``POST /data`` lands (anything else lands on the dashboard)
AREA_OF_KEY = {
    "position": "location", "speed_kmh": "location", "heading_deg": "location",
    "doors": "security", "windows": "security", "locked": "security", "warnings": "security",
    "tyre_pressure_bar": "tires",
    "fuel_level_pct": "energy", "fuel_amount": "energy", "range_km": "energy", "consumption_l_100km": "energy", "charging": "energy",
    "plugged": "energy", "battery_pct": "energy", "charge_power_kw": "energy", "charge_limit_pct": "energy", "charge_minutes_left": "energy",
    "charge_state": "energy", "charge_session_kwh": "energy", "charge_session_minutes": "energy", "charge_voltage_v": "energy",
    "charge_current_a": "energy", "charge_phases": "energy", "charge_current_limit_a": "energy", "charge_total_kwh": "energy",
    "charge_temp_c": "energy", "charge_mode": "energy", "charge_fault": "energy",
    "service_due_days": "service", "service_due_km": "service", "oil_change_due_days": "service", "oil_change_due_km": "service",
    "oil_level_pct": "service", "oil_warning": "service", "adblue_level_pct": "service", "adblue_range_km": "service",
}  # fmt: skip

# the fixed areas: key, icon, colour chip (the same tints as the module chips)
AREAS: tuple[tuple[str, str, str], ...] = (
    ("dashboard", "speedometer", "c3"),
    ("location", "map-marker-radius", "c7"),
    ("security", "security", "c2"),
    ("tires", "tires", "c2"),
    ("energy", "fuel", "c6"),
    ("trips", "route", "c1"),
    ("service", "wrench", "c4"),
    ("signals", "bug", "c5"),
    ("logs", "docs", "c5"),
    ("control", "settings", "c5"),
)
AREA_KEYS = {a[0] for a in AREAS}

_seen: dict[tuple, tuple[float, str]] = {}
_lock = threading.Lock()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _raw(value) -> str | None:
    if value is None:
        return None
    try:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        text = str(value)
    return text if len(text) <= MAX_VALUE else text[: MAX_VALUE - 1] + "…"


# ------------------------------------------------------------------ what a call says


def entries(method: str, parts: list[str], data) -> list[tuple[str, str, str, object]]:
    """The signals of one API call as ``(direction, name, area, value)``. ``parts`` is the path split at ``/``
    (``['', 'api', 'v1', 'vehicles', '3', 'data', ...]``). A read has no value."""
    what = parts[5] if len(parts) > 5 else ""
    rest = parts[6:]
    get = method == "GET"
    direction = "get" if get else "set"
    body = data if isinstance(data, dict) else {}
    if what == "data":
        if get:
            return [("get", "data", "dashboard", None)]
        return [("set", k, AREA_OF_KEY.get(k, "dashboard"), v) for k, v in body.items() if k != "measured_at"]
    if what == "signals":
        if get:
            return [("get", "signals", "signals", None)]
        found = body.get("signals")
        return [("set", f"signals.{k}", "signals", v) for k, v in (found.items() if isinstance(found, dict) else [])]
    if what == "track":
        points = body.get("points") if isinstance(body.get("points"), list) else []
        return [(direction, "track", "trips", None if get else {"points": len(points), "last": points[-1] if points else None})]
    if what == "trip-summary":
        return [(direction, "trip-summary", "trips", None if get else body)]
    if what == "refuel":
        return [("set", "refuel", "energy", body)]
    if what == "events":
        events = body.get("events") if isinstance(body.get("events"), list) else []
        return [(direction, "events", "dashboard", None if get else {"events": len(events), "last": events[-1] if events else None})]
    if what == "logs":
        lines = body.get("lines") if isinstance(body.get("lines"), list) else []
        return [("set", "logs", "logs", {"lines": len(lines), "last": lines[-1] if lines else None})]
    if what == "plugin-settings":
        return [(direction, "plugin-settings", "control", None if get else body)]
    if what == "control":
        return [("get", "control", "control", None)]
    if what == "modules" and len(rest) >= 2:
        value = None if get else {"rows": len(body.get("rows") or []), "delete": len(body.get("delete") or [])}
        return [(direction, rest[1], f"int:{rest[0]}", value)]
    if what == "":  # /api/v1/vehicles
        return [("get", "vehicles", "control", None)]
    return []


# ------------------------------------------------------------------ writing


def record(conn: sqlite3.Connection, vehicle_id: int, addon_id: str | None, method: str, parts: list[str], data) -> int:
    """Note what one successful call of a plugin said. Returns the number of signals written (0 for a call that changed nothing)."""
    if not addon_id:
        return 0
    written = 0
    for direction, name, area, value in entries(method, parts, data)[:MAX_PER_CALL]:
        name = str(name)[:80]
        raw = _raw(value)
        sig = hashlib.blake2s(f"{area}|{raw}".encode(), digest_size=8).hexdigest()
        key = (vehicle_id, addon_id, direction, name)
        now = time.monotonic()
        with _lock:
            seen = _seen.get(key)
            if seen and seen[1] == sig and now - seen[0] < SAME_SECONDS:
                continue  # the same value a moment ago: nothing new to say
            _seen[key] = (now, sig)
        old = conn.execute(
            "SELECT last_value FROM signal_state WHERE vehicle_id = ? AND addon_id = ? AND direction = ? AND name = ?",
            (vehicle_id, addon_id, direction, name),
        ).fetchone()
        if (
            old is None
            and conn.execute("SELECT COUNT(*) FROM signal_state WHERE vehicle_id = ? AND addon_id = ?", (vehicle_id, addon_id)).fetchone()[
                0
            ]
            >= MAX_SIGNALS
        ):
            continue  # a plugin cannot fill the database with names
        stamp = _now()
        conn.execute(
            "INSERT INTO signal_state(vehicle_id, addon_id, direction, name, area, hits, last_ts, last_value) VALUES(?,?,?,?,?,1,?,?) "
            "ON CONFLICT(vehicle_id, addon_id, direction, name) DO UPDATE SET area = excluded.area, hits = hits + 1, "
            "last_ts = excluded.last_ts, last_value = excluded.last_value",
            (vehicle_id, addon_id, direction, name, area, stamp, raw),
        )
        if old is None or old["last_value"] != raw or direction == "get":
            conn.execute(
                "INSERT INTO signal_history(vehicle_id, addon_id, direction, name, ts, value) VALUES(?,?,?,?,?,?)",
                (vehicle_id, addon_id, direction, name, stamp, raw),
            )
            conn.execute(
                "DELETE FROM signal_history WHERE vehicle_id = ? AND addon_id = ? AND direction = ? AND name = ? AND id NOT IN "
                "(SELECT id FROM signal_history WHERE vehicle_id = ? AND addon_id = ? AND direction = ? AND name = ? ORDER BY id DESC LIMIT ?)",
                (vehicle_id, addon_id, direction, name, vehicle_id, addon_id, direction, name, HISTORY),
            )
        written += 1
    return written


def forget(conn: sqlite3.Connection, vehicle_id: int, addon_id: str) -> None:
    """A plugin that is removed takes its signals with it."""
    for table in ("signal_state", "signal_history"):
        conn.execute(f"DELETE FROM {table} WHERE vehicle_id = ? AND addon_id = ?", (vehicle_id, addon_id))
    with _lock:
        for key in [k for k in _seen if k[0] == vehicle_id and k[1] == addon_id]:
            _seen.pop(key, None)


# ------------------------------------------------------------------ reading


def _age(stamp: str | None) -> float | None:
    if not stamp:
        return None
    try:
        return (datetime.now(UTC) - datetime.fromisoformat(stamp)).total_seconds()
    except ValueError:
        return None


def activity(stamp: str | None) -> str:
    """How a connection is drawn: ``live`` (just now), ``recent`` (within a day), ``idle`` (older) or ``none`` (never seen)."""
    age = _age(stamp)
    if age is None:
        return "none"
    return "live" if age <= LIVE_SECONDS else "recent" if age <= RECENT_SECONDS else "idle"


def color_of(addon_ids: list[str]) -> dict[str, int]:
    """Every plugin gets one of seven tints, always the same one (by its place in the sorted list of the car's plugins)."""
    return {a: i % 7 + 1 for i, a in enumerate(sorted(addon_ids))}


def graph(conn: sqlite3.Connection, vehicle_id: int) -> dict:
    """The whole map of one car as plain data: ``plugins``, ``areas`` and ``edges`` (one per plugin, area and direction). Cheap on purpose: two
    queries over the aggregated state, never the signals themselves."""
    plugins = []
    integrations: dict[str, dict] = {}
    for r in conn.execute(
        "SELECT id, addon_id, kind, active, status, manifest FROM vehicle_addons WHERE vehicle_id = ? ORDER BY id", (vehicle_id,)
    ):
        try:
            m = json.loads(r["manifest"])
        except ValueError:
            continue
        item = {
            "id": r["addon_id"],
            "pk": r["id"],
            "name": m.get("name") or r["addon_id"],
            "icon": m.get("icon") or ("plug" if r["kind"] == "plugin" else "puzzle"),
            "version": m.get("version") or "",
            "active": bool(r["active"]) and r["status"] != "missing",
            "missing": r["status"] == "missing",
        }
        if r["kind"] == "plugin":
            plugins.append(item)
        else:
            integrations[r["addon_id"]] = item
    tint = color_of([p["id"] for p in plugins])
    for p in plugins:
        p["tint"] = tint[p["id"]]
    rows = conn.execute(
        "SELECT addon_id, direction, area, COUNT(*) AS n, SUM(hits) AS hits, MAX(last_ts) AS last_ts FROM signal_state WHERE vehicle_id = ? "
        "GROUP BY addon_id, direction, area",
        (vehicle_id,),
    ).fetchall()
    known = {p["id"] for p in plugins}
    edges = []
    area_last: dict[str, str] = {}
    stat = {p["id"]: {"set": 0, "get": 0, "last": None} for p in plugins}
    for r in rows:
        if r["addon_id"] not in known:
            continue  # a plugin that is gone (its rows are cleaned up with it)
        edges.append(
            {
                "plugin": r["addon_id"],
                "area": r["area"],
                "dir": r["direction"],
                "n": r["n"],
                "hits": r["hits"],
                "last": r["last_ts"],
                "state": activity(r["last_ts"]),
            }
        )
        s = stat[r["addon_id"]]
        s[r["direction"]] += r["n"]
        if r["last_ts"] and (s["last"] is None or r["last_ts"] > s["last"]):
            s["last"] = r["last_ts"]
        if r["last_ts"] and r["last_ts"] > area_last.get(r["area"], ""):
            area_last[r["area"]] = r["last_ts"]
    for p in plugins:
        p.update(sets=stat[p["id"]]["set"], gets=stat[p["id"]]["get"], last=stat[p["id"]]["last"], state=activity(stat[p["id"]]["last"]))
    used = {e["area"] for e in edges}
    areas = [
        {"key": k, "icon": ic, "chip": chip, "last": area_last.get(k), "state": activity(area_last.get(k)), "used": k in used}
        for k, ic, chip in AREAS
    ]
    for a in sorted(used | {f"int:{i}" for i in integrations}):
        if a.startswith("int:"):
            iid = a[4:]
            meta = integrations.get(iid) or {"name": iid, "icon": "puzzle"}
            areas.append(
                {
                    "key": a, "icon": meta["icon"], "chip": "c4", "name": meta["name"], "integration": True, "last": area_last.get(a),
                    "state": activity(area_last.get(a)), "used": a in used,
                }
            )  # fmt: skip
    # the areas nobody uses are not drawn (only the ones with traffic and every installed integration)
    areas = [a for a in areas if a["used"] or a.get("integration")]
    body = {"plugins": plugins, "areas": areas, "edges": edges}
    body["version"] = hashlib.sha1(
        json.dumps(
            {
                "p": [(p["id"], p["active"]) for p in plugins],
                "a": [a["key"] for a in areas],
                "e": [(e["plugin"], e["area"], e["dir"]) for e in edges],
            }
        ).encode(),
        usedforsecurity=False,
    ).hexdigest()[:12]
    return body


def signals_of(
    conn: sqlite3.Connection, vehicle_id: int, addon_id: str | None = None, area: str | None = None, limit: int = 200
) -> list[dict]:
    """The signals of one plugin and/or one area, newest first (at most ``limit``)."""
    sql = "SELECT addon_id, direction, name, area, hits, last_ts, last_value FROM signal_state WHERE vehicle_id = ?"
    args: list = [vehicle_id]
    if addon_id:
        sql += " AND addon_id = ?"
        args.append(addon_id)
    if area:
        sql += " AND area = ?"
        args.append(area)
    sql += " ORDER BY last_ts DESC, name LIMIT ?"
    args.append(max(1, min(limit, 500)))
    return [dict(r) for r in conn.execute(sql, args)]


def history_of(conn: sqlite3.Connection, vehicle_id: int, addon_id: str, direction: str, name: str) -> list[dict]:
    """The last values of one signal with their times, newest first."""
    return [
        dict(r)
        for r in conn.execute(
            "SELECT ts, value FROM signal_history WHERE vehicle_id = ? AND addon_id = ? AND direction = ? AND name = ? ORDER BY id DESC LIMIT ?",
            (vehicle_id, addon_id, direction, name, HISTORY),
        )
    ]
