"""MCP access: Claude Code (or any MCP client) can read - and with the highest level also correct - the data of this app.

Off by default. It can be switched on (Settings -> System) only when the app is reachable over https from outside: a user exists, the external
https address is saved and the port is open. Every client needs its own access key (shown once, only a hash is stored), and every key has a
level - read or read + write - that can never go above the level of the whole server. Everything a key does is written to a short log.

The transport is MCP "Streamable HTTP" in its simplest form: ``POST /mcp`` with JSON-RPC 2.0, an answer as JSON (no event stream, no session).
The tools never show secrets (passwords, tokens, keys, the external address) and cannot change settings, users or plugins - only the records
of the cars. See docs/mcp.md.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
from collections import defaultdict, deque
from dataclasses import asdict
from datetime import UTC, datetime
from urllib.parse import urlparse

from . import STAGE, __version__, accounts, config, db, entities, events, fuelstats, ha, slugs, summary

LEVELS = ("off", "read", "write")
SETTING = "mcp.level"
PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
KEY_PREFIX = "cam_"
MAX_BODY = 256 * 1024
RATE_PER_MINUTE = 120  # calls per key
FAIL_LIMIT, FAIL_WINDOW, BLOCK_SECONDS = 10, 600, 900  # wrong keys per address, in how many seconds, and how long that address is blocked
LOG_KEEP = 500
MAX_ROWS = 100
HIDDEN_COLUMNS = {"photo"}  # never handed out

_calls: dict[int, deque] = defaultdict(deque)
_fails: dict[str, list[float]] = defaultdict(list)
_blocked: dict[str, float] = {}


class ToolError(Exception):
    """A problem the client should see as the result of a tool (not a protocol error)."""


# ------------------------------------------------------------------ switch and availability


def level(conn: sqlite3.Connection) -> str:
    raw = db.get_setting(conn, SETTING, "off")
    return raw if raw in LEVELS else "off"


def missing(conn: sqlite3.Connection) -> list[str]:
    """What is still needed before MCP can be switched on (i18n keys). Empty = it may be used."""
    out = []
    if not accounts.has_users(conn):
        out.append("mcp.need_user")
    if not config.external_url().lower().startswith("https://"):
        out.append("mcp.need_https")
    if not config.dev_mode() and ha.network_port()[1] is None:
        out.append("mcp.need_port")
    return out


def set_level(conn: sqlite3.Connection, value: str) -> None:
    """ValueError(i18n key) when the choice is not allowed (yet)."""
    if value not in LEVELS:
        raise ValueError("err.choice")
    if value != "off" and (gaps := missing(conn)):
        raise ValueError(gaps[0])
    db.set_setting(conn, SETTING, None if value == "off" else value)


PATH_KEY_SETTING = "mcp.path_key"


def path_key_allowed(conn: sqlite3.Connection) -> bool:
    """May the key sit in the address (``/mcp/<key>``)? The simplest way to connect, on by default; off = the Authorization header only."""
    return db.get_setting(conn, PATH_KEY_SETTING, "1") != "0"


def set_path_key(conn: sqlite3.Connection, allowed: bool) -> None:
    db.set_setting(conn, PATH_KEY_SETTING, None if allowed else "0")


def active_level(conn: sqlite3.Connection) -> str:
    """The level in force right now: off as soon as one of the requirements is gone (address removed, port closed)."""
    value = level(conn)
    return "off" if value == "off" or missing(conn) else value


# ------------------------------------------------------------------ keys


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def renew_key(conn: sqlite3.Connection) -> str:
    """The one access key: made when there is none, replaced when there is (every older key stops working at once). Returned once, never stored."""
    conn.execute("DELETE FROM mcp_keys")
    _calls.clear()
    token = KEY_PREFIX + secrets.token_urlsafe(32)
    conn.execute(
        "INSERT INTO mcp_keys(name, key_hash, prefix, level, created_at) VALUES(?,?,?,?,?)",
        ("Claude", _hash(token), token[: len(KEY_PREFIX) + 4], "read", _now()),
    )
    return token


def delete_keys(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM mcp_keys")
    _calls.clear()


def keys(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT id, name, prefix, level, created_at, last_used, uses FROM mcp_keys ORDER BY id").fetchall()


def verify(conn: sqlite3.Connection, token: str | None) -> sqlite3.Row | None:
    if not token or not token.startswith(KEY_PREFIX) or len(token) > 120:
        return None
    row = conn.execute("SELECT id, name, level FROM mcp_keys WHERE key_hash = ?", (_hash(token),)).fetchone()
    if row:
        conn.execute("UPDATE mcp_keys SET last_used = ?, uses = uses + 1 WHERE id = ?", (_now(), row["id"]))
    return row


def blocked(address: str) -> bool:
    until = _blocked.get(address, 0)
    if until and until > time.time():
        return True
    _blocked.pop(address, None)
    return False


def failed(address: str) -> None:
    now = time.time()
    recent = [t for t in _fails[address] if now - t < FAIL_WINDOW] + [now]
    _fails[address] = recent
    if len(recent) >= FAIL_LIMIT:
        _blocked[address] = now + BLOCK_SECONDS
        _fails[address] = []


def within_rate(key_id: int) -> bool:
    now = time.time()
    queue = _calls[key_id]
    while queue and now - queue[0] > 60:
        queue.popleft()
    if len(queue) >= RATE_PER_MINUTE:
        return False
    queue.append(now)
    return True


def audit(conn: sqlite3.Connection, key_name: str, method: str, tool: str | None, ok: bool, detail: str = "") -> None:
    conn.execute(
        "INSERT INTO mcp_log(ts, key_name, method, tool, ok, detail) VALUES(?,?,?,?,?,?)",
        (_now(), key_name, method, tool, int(ok), detail[:200]),
    )
    conn.execute("DELETE FROM mcp_log WHERE id NOT IN (SELECT id FROM mcp_log ORDER BY id DESC LIMIT ?)", (LOG_KEEP,))


def state(conn: sqlite3.Connection) -> dict:
    """Everything the settings card shows."""
    return {
        "level": level(conn),
        "path_key": path_key_allowed(conn),
        "missing": missing(conn),
        "key": (keys(conn) or [None])[0],
        "log": conn.execute("SELECT * FROM mcp_log ORDER BY id DESC LIMIT 15").fetchall(),
        "url": (config.external_url() + "/mcp") if config.external_url() else "",
    }


# ------------------------------------------------------------------ tools


def _vehicle(conn: sqlite3.Connection, ref) -> int:
    vid = slugs.id_for(conn, str(ref).strip()) if ref not in (None, "") else None
    if vid is None:
        raise ToolError("Unknown vehicle. Use an id or the name from list_vehicles (the 'slug').")
    return vid


def _clean(row) -> dict:
    return {k: v for k, v in dict(row).items() if k not in HIDDEN_COLUMNS and not isinstance(v, bytes)}


def _entity(kind: str):
    entity = entities.ENTITIES.get(kind)
    if entity is None:
        raise ToolError(f"Unknown kind '{kind}'. One of: {', '.join(entities.ENTITIES)}.")
    return entity


def _int(args: dict, name: str, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(args.get(name, default))))
    except (TypeError, ValueError):
        raise ToolError(f"'{name}' must be a whole number.") from None


def t_app_info(conn, args):
    return {
        "app": "Car Assistant",
        "version": __version__,
        "stage": STAGE,
        "schema": len(db.MIGRATIONS),
        "language": config.language(),
        "vehicles": conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0],
        "kinds": list(entities.ENTITIES),
        "units": "Values are in base units: km, litres (kWh for electric), bar, degrees Celsius, money as a plain number.",
    }


def t_list_vehicles(conn, args):
    return [
        {
            "id": r["id"],
            "slug": r["slug"],
            "name": r["name"],
            "make": r["make"],
            "model": r["model"],
            "year": r["year"],
            "fuel_type": r["fuel_type"],
            "archived": bool(r["archived"]),
            "odometer_km": summary.current_odometer(conn, r["id"]),
        }
        for r in conn.execute("SELECT * FROM vehicles ORDER BY archived, name COLLATE NOCASE")
    ]


def t_get_vehicle(conn, args):
    vid = _vehicle(conn, args.get("vehicle"))
    row = conn.execute("SELECT * FROM vehicles WHERE id = ?", (vid,)).fetchone()
    live = {
        r["key"]: {"value": r["value"], "updated": r["updated"]}
        for r in conn.execute("SELECT key, value, updated FROM live WHERE vehicle_id = ?", (vid,))
    }
    return {
        "vehicle": _clean(row),
        "odometer_km": summary.current_odometer(conn, vid),
        "live": live,
        "attention": [asdict(a) for a in summary.attention_items(conn, vid)],
        "counts": {k: entities.count(conn, e, vid) for k, e in entities.ENTITIES.items()},
    }


def t_list_entries(conn, args):
    vid = _vehicle(conn, args.get("vehicle"))
    entity = _entity(str(args.get("kind", "")))
    limit, offset = _int(args, "limit", 25, 1, MAX_ROWS), _int(args, "offset", 0, 0, 10**7)
    rows = conn.execute(
        f"SELECT * FROM {entity.table} WHERE vehicle_id = ? ORDER BY {entity.order} LIMIT ? OFFSET ?", (vid, limit, offset)
    ).fetchall()
    return {"kind": entity.key, "total": entities.count(conn, entity, vid), "offset": offset, "rows": [_clean(r) for r in rows]}


def t_get_costs(conn, args):
    vid = _vehicle(conn, args.get("vehicle"))
    group = str(args.get("group", "month"))
    if group not in fuelstats.PERIODS:
        raise ToolError(f"'group' must be one of: {', '.join(fuelstats.PERIODS)}.")
    count = _int(args, "count", fuelstats.PERIODS[group][0], 1, 120)
    return {
        "group": group,
        "count": count,
        "costs": fuelstats.costs(conn, vid, group, count),
        "overall": fuelstats.overall(conn, vid),
        "expenses": fuelstats.expenses(conn, vid, group, count, str(args.get("kind", "")))[:MAX_ROWS],
    }


def t_get_logs(conn, args):
    limit = _int(args, "limit", 30, 1, MAX_ROWS)
    if args.get("vehicle") not in (None, ""):
        rows = conn.execute(
            "SELECT ts, level, source, message FROM vehicle_logs WHERE vehicle_id = ? ORDER BY id DESC LIMIT ?",
            (_vehicle(conn, args["vehicle"]), limit),
        ).fetchall()
    else:
        rows = conn.execute("SELECT vehicle_id, ts, level, source, message FROM vehicle_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


VEHICLE_FIELDS = ("vin", "plate", "make", "model", "year", "first_reg", "hsn", "tsn", "engine", "color")


def t_data_gaps(conn, args):
    """What is still missing in the data of one vehicle - the starting point for completing it together with the user."""
    vid = _vehicle(conn, args.get("vehicle"))
    car = conn.execute("SELECT * FROM vehicles WHERE id = ?", (vid,)).fetchone()
    limit = _int(args, "limit", 20, 1, MAX_ROWS)
    fields = (*VEHICLE_FIELDS, "battery_kwh" if car["fuel_type"] == "electric" else "tank_l")
    gaps: dict = {"vehicle": [f for f in fields if car[f] in (None, "")]}

    def rows(sql: str, need: tuple[str, ...]) -> dict:
        found = conn.execute(sql, (vid,)).fetchall()
        examples = []
        for r in found[:limit]:
            keys = r.keys()
            examples.append(
                {
                    "id": r["id"],
                    "date": r["date"] if "date" in keys else None,
                    "title": r["title"] if "title" in keys else None,
                    "missing": [k for k in need if r[k] in (None, "")],
                }
            )
        return {"count": len(found), "examples": examples}

    gaps["fuel"] = rows(
        "SELECT id, date, odometer_km, amount, price_total FROM fuel WHERE vehicle_id = ? "
        "AND (odometer_km IS NULL OR amount IS NULL OR price_total IS NULL) ORDER BY date DESC",
        ("odometer_km", "amount", "price_total"),
    )
    gaps["service"] = rows(
        "SELECT id, date, title, odometer_km, cost FROM service WHERE vehicle_id = ? AND (odometer_km IS NULL OR cost IS NULL) ORDER BY date DESC",
        ("odometer_km", "cost"),
    )
    gaps["tasks"] = rows(
        "SELECT id, title, last_date, last_km FROM tasks WHERE vehicle_id = ? AND muted = 0 AND last_date IS NULL AND last_km IS NULL ORDER BY title",
        ("last_date", "last_km"),
    )
    gaps["trips"] = rows(
        "SELECT id, date, start_place, end_place FROM trips WHERE vehicle_id = ? "
        "AND (start_place IS NULL OR start_place = '' OR end_place IS NULL OR end_place = '') ORDER BY date DESC",
        ("start_place", "end_place"),
    )
    return gaps


def _form_of(entity, current: dict | None, values: dict) -> dict[str, str]:
    """The strings parse_form expects: the old record (for a change) with the new values on top."""
    form: dict[str, str] = {}
    for f in entity.fields:
        if f.name in values:
            v = values[f.name]
        elif current is not None:
            v = current.get(f.name)
            if f.kind == "month_or_date" and v and current.get("month_only"):
                v = str(v)[:7]
        else:
            continue
        form[f.name] = "" if v is None else ("1" if v is True else "" if v is False else str(v))
        if f.kind == "bool" and current is not None and f.name not in values:
            form[f.name] = "1" if current.get(f.name) else ""
    return form


def _values(args: dict) -> dict:
    values = args.get("values")
    if not isinstance(values, dict) or not values:
        raise ToolError('\'values\' must be an object with the fields to set, e.g. {"date": "2026-11-20", "title": "Oil"}.')
    return values


def _checked(entity, form):
    try:
        return entities.parse_form(entity, form)
    except entities.FormError as exc:
        raise ToolError(f"Invalid value: {' / '.join(str(a) for a in exc.args)}") from None


def t_add_entry(conn, args):
    vid = _vehicle(conn, args.get("vehicle"))
    entity = _entity(str(args.get("kind", "")))
    row_id = entities.insert(conn, entity, vid, _checked(entity, _form_of(entity, None, _values(args))))
    events.changed()
    return {"ok": True, "id": row_id}


def t_update_entry(conn, args):
    vid = _vehicle(conn, args.get("vehicle"))
    entity = _entity(str(args.get("kind", "")))
    row_id = _int(args, "id", 0, 0, 10**12)
    row = conn.execute(f"SELECT * FROM {entity.table} WHERE id = ? AND vehicle_id = ?", (row_id, vid)).fetchone()
    if row is None:
        raise ToolError("No such entry for this vehicle.")
    entities.update(conn, entity, vid, row_id, _checked(entity, _form_of(entity, dict(row), _values(args))))
    events.changed()
    return {"ok": True, "id": row_id}


def t_delete_entry(conn, args):
    vid = _vehicle(conn, args.get("vehicle"))
    entity = _entity(str(args.get("kind", "")))
    row_id = _int(args, "id", 0, 0, 10**12)
    if conn.execute(f"SELECT 1 FROM {entity.table} WHERE id = ? AND vehicle_id = ?", (row_id, vid)).fetchone() is None:
        raise ToolError("No such entry for this vehicle.")
    entities.delete(conn, entity, vid, row_id)
    events.changed()
    return {"ok": True, "id": row_id}


def _schema(props: dict, required: tuple[str, ...] = ()) -> dict:
    return {"type": "object", "properties": props, "required": list(required), "additionalProperties": False}


_VEHICLE = {"type": "string", "description": "The vehicle: its slug (name in the address) or id, from list_vehicles."}
_KIND = {"type": "string", "description": "The kind of record: service, appointments, mods, fuel, tires, tasks, trips, counters or parts."}
_VALUES = {
    "type": "object",
    "description": "Field values by name (dates as YYYY-MM-DD, numbers in base units: km, litres, bar). See list_entries for the field names.",
}

TOOLS: tuple[tuple[str, str, dict, bool, object], ...] = (
    ("app_info", "Version, stage and size of this Car Assistant, and the kinds of records.", _schema({}), False, t_app_info),
    ("list_vehicles", "All vehicles with id, slug, name, fuel type and odometer.", _schema({}), False, t_list_vehicles),
    (
        "get_vehicle",
        "One vehicle: all its data, the live values, what needs attention, and how many records of each kind it has.",
        _schema({"vehicle": _VEHICLE}, ("vehicle",)),
        False,
        t_get_vehicle,
    ),
    (
        "list_entries",
        "The records of one kind of a vehicle, newest first (paged).",
        _schema(
            {
                "vehicle": _VEHICLE,
                "kind": _KIND,
                "limit": {"type": "integer", "description": "1-100, default 25"},
                "offset": {"type": "integer"},
            },
            ("vehicle", "kind"),
        ),
        False,
        t_list_entries,
    ),
    (
        "get_costs",
        "Costs of a vehicle per day / week / month (fuel, service, modifications, parts) and the list of every priced entry in that window.",
        _schema(
            {
                "vehicle": _VEHICLE,
                "group": {"type": "string", "description": "day, week or month"},
                "count": {"type": "integer"},
                "kind": {"type": "string"},
            },
            ("vehicle",),
        ),
        False,
        t_get_costs,
    ),
    (
        "get_logs",
        "The newest log lines of the plugins (all vehicles, or one) - useful when something does not work.",
        _schema({"vehicle": _VEHICLE, "limit": {"type": "integer", "description": "1-100, default 30"}}),
        False,
        t_get_logs,
    ),
    (
        "data_gaps",
        "What is still missing for one vehicle (empty vehicle fields; refuels without odometer, amount or price; service without cost or odometer; "
        "tasks never done; trips without places). Start here to complete the data together with the user.",
        _schema({"vehicle": _VEHICLE, "limit": {"type": "integer", "description": "examples per list, 1-100, default 20"}}, ("vehicle",)),
        False,
        t_data_gaps,
    ),
    (
        "add_entry",
        "Add a record (needs write access). Required fields depend on the kind; wrong values are refused with the reason.",
        _schema({"vehicle": _VEHICLE, "kind": _KIND, "values": _VALUES}, ("vehicle", "kind", "values")),
        True,
        t_add_entry,
    ),
    (
        "update_entry",
        "Change a record: only the fields in 'values' change (needs write access).",
        _schema({"vehicle": _VEHICLE, "kind": _KIND, "id": {"type": "integer"}, "values": _VALUES}, ("vehicle", "kind", "id", "values")),
        True,
        t_update_entry,
    ),
    (
        "delete_entry",
        "Delete a record (needs write access; cannot be undone).",
        _schema({"vehicle": _VEHICLE, "kind": _KIND, "id": {"type": "integer"}}, ("vehicle", "kind", "id")),
        True,
        t_delete_entry,
    ),
)
BY_NAME = {t[0]: t for t in TOOLS}

INSTRUCTIONS = (
    "Car Assistant keeps the data of vehicles (fuel, service, appointments, parts, tyres, trips, documents). "
    "Start with list_vehicles; use the slug as 'vehicle'. To complete data call data_gaps first, ask the user for the missing values, then use "
    "update_entry / add_entry. Values are in base units (km, litres, bar). "
    "Write tools change real data: say what you will change and prefer small, checked steps."
)


# ------------------------------------------------------------------ JSON-RPC


def _result(msg_id, result) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def handle(conn: sqlite3.Connection, key, message) -> dict | None:
    """One JSON-RPC message from a client with a valid key -> the answer (None for a notification)."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
        return _error(message.get("id") if isinstance(message, dict) else None, -32600, "Invalid request")
    method, msg_id = message["method"], message.get("id")
    params = message.get("params") if isinstance(message.get("params"), dict) else {}
    if "id" not in message:  # a notification (e.g. notifications/initialized): no answer
        return None
    allowed = active_level(conn)  # one switch for everything: the level of the server
    if allowed == "off":
        return _error(msg_id, -32000, "MCP access is switched off.")
    if method == "initialize":
        asked = params.get("protocolVersion")
        audit(conn, key["name"], method, None, True)
        return _result(
            msg_id,
            {
                "protocolVersion": asked if asked in PROTOCOLS else PROTOCOLS[0],
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "car-assistant", "version": f"{__version__} {STAGE}".strip()},
                "instructions": INSTRUCTIONS,
            },
        )
    if method == "ping":
        return _result(msg_id, {})
    if method == "tools/list":
        listed = [{"name": n, "description": d, "inputSchema": s} for n, d, s, writes, _f in TOOLS if allowed == "write" or not writes]
        return _result(msg_id, {"tools": listed})
    if method == "tools/call":
        name = params.get("name")
        tool = BY_NAME.get(name) if isinstance(name, str) else None
        if tool is None:
            return _error(msg_id, -32602, f"Unknown tool '{name}'.")
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        if tool[3] and allowed != "write":
            audit(conn, key["name"], method, name, False, "write refused")
            return _result(msg_id, _text({"error": "This key (or the server) allows read access only."}, error=True))
        try:
            out = tool[4](conn, arguments)
            audit(conn, key["name"], method, name, True)
            return _result(msg_id, _text(out))
        except ToolError as exc:
            audit(conn, key["name"], method, name, False, str(exc))
            return _result(msg_id, _text({"error": str(exc)}, error=True))
    return _error(msg_id, -32601, f"Method not found: {method}")


def _text(data, error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False, default=str, indent=1)}], "isError": error}


def origin_allowed(origin: str | None) -> bool:
    """A browser page of another site must not use the endpoint (DNS rebinding): no Origin (a program) or our own external address."""
    if not origin:
        return True
    return urlparse(origin).netloc == urlparse(config.external_url()).netloc
