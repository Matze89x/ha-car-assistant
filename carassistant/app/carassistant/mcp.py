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
import re
import secrets
import sqlite3
import time
from collections import defaultdict, deque
from dataclasses import asdict
from datetime import UTC, date, datetime
from urllib.parse import urlparse

from . import STAGE, __version__, accounts, addons, config, db, entities, events, fuelstats, ha, pagemods, slugs, summary, units

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


def t_list_plugins(conn, args):
    """Plugins and integrations of one vehicle (or all): what is installed, switched on, set up - never tokens or secret settings."""
    ids = (
        [_vehicle(conn, args["vehicle"])]
        if args.get("vehicle") not in (None, "")
        else [r["id"] for r in conn.execute("SELECT id FROM vehicles")]
    )
    out = []
    for vid in ids:
        for a in addons.list_for(conn, vid):
            m = a["m"]
            secret = {f["key"] for f in m.get("settings", []) if f.get("type") == "password"}
            out.append(
                {
                    "vehicle_id": vid,
                    "kind": a["kind"],
                    "id": a["addon_id"],
                    "name": m.get("name"),
                    "version": m.get("version"),
                    "description": m.get("description"),
                    "active": bool(a["active"]),
                    "status": a["status"],
                    "source": a.get("source_name"),
                    "update_available": a.get("has_update", False),
                    "debug": bool(a.get("debug")),
                    "settings": {k: ("***" if k in secret else v) for k, v in a["vals"].items()},
                }
            )
    return out


def t_list_documents(conn, args):
    """The documents of a vehicle (title, category, file name, size) - the files themselves are not handed out."""
    vid = _vehicle(conn, args.get("vehicle"))
    rows = conn.execute(
        "SELECT id, category, title, filename, mime, size, created_at FROM documents WHERE vehicle_id = ? ORDER BY id DESC LIMIT ?",
        (vid, _int(args, "limit", 50, 1, MAX_ROWS)),
    ).fetchall()
    return [dict(r) for r in rows]


def t_get_charging(conn, args):
    """Charging sessions noticed for an electric / plug-in car (newest first)."""
    vid = _vehicle(conn, args.get("vehicle"))
    rows = conn.execute(
        "SELECT started, ended, start_pct, end_pct, max_kw, odometer_km FROM charge_sessions WHERE vehicle_id = ? ORDER BY started DESC LIMIT ?",
        (vid, _int(args, "limit", 25, 1, MAX_ROWS)),
    ).fetchall()
    return [dict(r) for r in rows]


def t_get_tyres(conn, args):
    """Recommended tyre pressures per season and the tyre sets of a vehicle."""
    vid = _vehicle(conn, args.get("vehicle"))
    pressure = conn.execute("SELECT season, front_bar, rear_bar FROM tire_pressure WHERE vehicle_id = ?", (vid,)).fetchall()
    sets = conn.execute("SELECT * FROM tires WHERE vehicle_id = ? ORDER BY id DESC", (vid,)).fetchall()
    return {"pressure_bar": [dict(r) for r in pressure], "sets": [_clean(r) for r in sets]}


def t_get_settings(conn, args):
    """The server-wide choices (language, units, currency) - nothing secret."""
    return {
        "language": config.language(),
        "units": units.default_system(),
        "currency": units.default_currency(),
        "vehicles": conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0],
        "plugins": conn.execute("SELECT COUNT(*) FROM vehicle_addons WHERE kind = 'plugin'").fetchone()[0],
        "integrations": conn.execute("SELECT COUNT(*) FROM vehicle_addons WHERE kind = 'integration'").fetchone()[0],
    }


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


def t_update_vehicle(conn, args):
    """Fill in or correct the master data of a vehicle (only the fields of data_gaps: vin, plate, make, model, year, ...)."""
    vid = _vehicle(conn, args.get("vehicle"))
    values = _values(args)
    unknown = sorted(set(values) - set(VEHICLE_FIELDS))
    if unknown:
        raise ToolError(f"Not allowed here: {', '.join(unknown)}. Allowed: {', '.join(VEHICLE_FIELDS)}.")
    if not values:
        raise ToolError("Give at least one field in 'values'.")
    clean: dict[str, object] = {}
    for key, raw in values.items():
        text = "" if raw is None else str(raw).strip()
        if key == "year":
            if text and not (text.isdigit() and 1885 <= int(text) <= 2100):
                raise ToolError("'year' must be a four-digit year.")
            clean[key] = int(text) if text else None
        else:
            clean[key] = text[:120] or None
    conn.execute(f"UPDATE vehicles SET {', '.join(f'{k} = ?' for k in clean)} WHERE id = ?", (*clean.values(), vid))
    events.changed()
    return {"ok": True, "updated": sorted(clean)}


def t_update_document(conn, args):
    """Title, category, document date, validity and note of a stored document (the file itself is never touched)."""
    vid = _vehicle(conn, args.get("vehicle"))
    doc_id = _int(args, "id", 0, 0, 10**12)
    row = conn.execute("SELECT * FROM documents WHERE id = ? AND vehicle_id = ?", (doc_id, vid)).fetchone()
    if row is None:
        raise ToolError("No such document for this vehicle.")
    values = _values(args)
    allowed = ("title", "category", "doc_date", "valid_until", "notes")
    unknown = sorted(set(values) - set(allowed))
    if unknown:
        raise ToolError(f"Not allowed here: {', '.join(unknown)}. Allowed: {', '.join(allowed)}.")
    categories = ("manual", "invoice", "insurance", "registration", "inspection", "other")
    if "category" in values and values["category"] not in categories:
        raise ToolError(f"'category' must be one of: {', '.join(categories)}.")
    for key in ("doc_date", "valid_until"):
        if values.get(key):
            try:
                values[key] = date.fromisoformat(str(values[key])[:10]).isoformat()
            except ValueError:
                raise ToolError(f"'{key}' must be a date like 2026-12-31.") from None
    new = {
        k: (str(values[k]).strip()[:2000] or None) if k in values and values[k] is not None else (values.get(k) if k in values else row[k])
        for k in allowed
    }
    new["title"] = new["title"] or row["filename"]
    conn.execute(
        "UPDATE documents SET title = ?, category = ?, doc_date = ?, valid_until = ?, notes = ? WHERE id = ?",
        (new["title"], new["category"] or row["category"], new["doc_date"], new["valid_until"], new["notes"], doc_id),
    )
    return {"ok": True, "id": doc_id}


def t_set_tyre_pressure(conn, args):
    """The recommended pressure (bar) of a season, front and rear axle."""
    vid = _vehicle(conn, args.get("vehicle"))
    season = str(args.get("season", ""))
    if season not in ("summer", "winter", "allseason"):
        raise ToolError("'season' must be summer, winter or allseason.")
    bars = []
    for key in ("front_bar", "rear_bar"):
        try:
            bar = float(args[key])
        except (KeyError, TypeError, ValueError):
            raise ToolError(f"'{key}' must be a number in bar.") from None
        if not 0.5 <= bar <= 6.0:
            raise ToolError(f"'{key}' looks wrong (0.5 - 6.0 bar expected).")
        bars.append(round(bar, 2))
    conn.execute(
        "INSERT INTO tire_pressure(vehicle_id, season, front_bar, rear_bar) VALUES(?,?,?,?) "
        "ON CONFLICT(vehicle_id, season) DO UPDATE SET front_bar = excluded.front_bar, rear_bar = excluded.rear_bar",
        (vid, season, *bars),
    )
    events.changed()
    return {"ok": True, "season": season, "front_bar": bars[0], "rear_bar": bars[1]}


def t_delete_entry(conn, args):
    vid = _vehicle(conn, args.get("vehicle"))
    entity = _entity(str(args.get("kind", "")))
    row_id = _int(args, "id", 0, 0, 10**12)
    if conn.execute(f"SELECT 1 FROM {entity.table} WHERE id = ? AND vehicle_id = ?", (row_id, vid)).fetchone() is None:
        raise ToolError("No such entry for this vehicle.")
    entities.delete(conn, entity, vid, row_id)
    events.changed()
    return {"ok": True, "id": row_id}


# ------------------------------------------------------------------ pages of integrations (for example Coding)


def _module_pages(conn, vid: int) -> list[tuple[dict, dict]]:
    """``(module, page)`` of every page with entries that an integration of the car describes (a frame page has no entries)."""
    out = []
    for m in pagemods.active_modules(conn, vid):
        mod = pagemods.module(conn, vid, m["addon_id"])
        for page in (mod or {}).get("pages", []):
            if page.get("kind") != "frame" and page.get("fields"):
                out.append((mod, page))
    return out


def _page(conn, vid: int, args: dict) -> tuple[dict, dict]:
    mod = pagemods.module(conn, vid, str(args.get("integration") or "").strip())
    page = pagemods.page_of(mod, str(args.get("page") or "").strip() or None) if mod else None
    if mod is None or page is None or page.get("kind") == "frame" or not page.get("fields"):
        raise ToolError(
            "Unknown or stopped integration, or a page without entries. Use the 'integration' and 'page' names from list_pages."
        )
    return mod, page


def _has_bits(page: dict) -> bool:
    return any(f["type"] == "hex" and f.get("compare") for f in page["fields"])


def _page_row(page: dict, row: dict) -> dict:
    """An entry as a client sees it: the values (no access codes), and for a coding its notes and groups of bits."""
    hidden = pagemods.secret_keys(page)
    data = row["data"]
    out = {"id": row["id"], "values": {k: v for k, v in data.items() if not k.startswith("_") and k not in hidden}}
    if _has_bits(page):
        out["bit_notes"] = pagemods._bit_notes(data.get("_bits", ""))
        out["bit_groups"] = pagemods._bit_groups(data.get("_groups", ""))
    return out


def t_list_pages(conn, args):
    vid = _vehicle(conn, args.get("vehicle"))
    out: dict[str, dict] = {}
    for mod, page in _module_pages(conn, vid):
        entry = out.setdefault(mod["addon_id"], {"integration": mod["addon_id"], "name": mod["name"], "pages": []})
        fields = [
            {
                k: v
                for k, v in {
                    "key": f["key"],
                    "label": f["label"],
                    "type": f["type"],
                    "required": f.get("required") or None,
                    "once": f.get("once") or None,
                    "compare": f.get("compare"),
                    "options": [o["value"] for o in f.get("options", [])] or None,
                    "access_code": True if f["type"] == "secret" else None,
                }.items()
                if v is not None
            }
            for f in page["fields"]
        ]
        count = conn.execute(
            "SELECT COUNT(*) FROM module_rows WHERE vehicle_id = ? AND addon_id = ? AND page = ?", (vid, mod["addon_id"], page["id"])
        ).fetchone()[0]
        entry["pages"].append(
            {"page": page["id"], "title": page.get("title") or page["id"], "entries": count, "has_bits": _has_bits(page), "fields": fields}
        )
    return list(out.values())


def t_list_page_entries(conn, args):
    vid = _vehicle(conn, args.get("vehicle"))
    mod, page = _page(conn, vid, args)
    limit, offset = _int(args, "limit", 25, 1, MAX_ROWS), _int(args, "offset", 0, 0, 10**7)
    rows = pagemods.rows(conn, vid, mod["addon_id"], page["id"])
    return {
        "integration": mod["addon_id"],
        "page": page["id"],
        "total": len(rows),
        "offset": offset,
        "rows": [_page_row(page, r) for r in rows[offset : offset + limit]],
    }


def _check_values(page: dict, values) -> dict:
    if values is None:
        return {}
    if not isinstance(values, dict):
        raise ToolError("'values' must be an object with the fields to set (field key: value, see list_pages).")
    hidden = pagemods.secret_keys(page)
    known = {f["key"] for f in page["fields"]}
    bad = sorted(k for k in values if k in hidden)
    if bad:
        raise ToolError(f"Not allowed here: {', '.join(bad)} (an access code - only the person types it in).")
    unknown = sorted(k for k in values if k not in known)
    if unknown:
        raise ToolError(f"Unknown field: {', '.join(unknown)}. Fields: {', '.join(sorted(known - hidden))}.")
    return values


def _bit_forms(page: dict, old_data: dict | None, args: dict) -> dict[str, str]:
    """The form texts ``bitnotes`` / ``bitgroups`` after merging the notes and groups of the call into the stored ones (notes: one note per bit, an empty text
    deletes it; groups: the list given for a byte replaces that byte's groups, an empty list removes them)."""
    notes_in, groups_in = args.get("bit_notes"), args.get("bit_groups")
    if notes_in is None and groups_in is None:
        return {}
    if not _has_bits(page):
        raise ToolError("This page has no coding field, so there are no bits to describe.")
    hexes = [f["key"] for f in page["fields"] if f["type"] == "hex"]
    old = old_data or {}
    form: dict[str, str] = {}
    if notes_in is not None:
        if not isinstance(notes_in, dict):
            raise ToolError('\'bit_notes\' must look like {"<hex field>": {"12.5": "text"}}.')
        merged = pagemods._bit_notes(old.get("_bits", ""))
        for field, per in notes_in.items():
            if field not in hexes or not isinstance(per, dict):
                raise ToolError(f"'{field}' is not a hex field of this page. One of: {', '.join(hexes)}.")
            mine = dict(merged.get(field, {}))
            for where, text in per.items():
                if not re.fullmatch(r"\d{1,4}\.[0-7]", str(where)) or int(str(where).split(".")[0]) >= 1100:
                    raise ToolError(
                        f"Bit '{where}': write <byte>.<bit> - the byte counted from 0 along the hex value, the bit 0-7 (0 = the lowest), e.g. 12.5."
                    )
                text = " ".join(str(text or "").split())[:200]
                if text:
                    mine[str(where)] = text
                else:
                    mine.pop(str(where), None)
            merged[field] = mine
        form["bitnotes"] = json.dumps(merged)
    if groups_in is not None:
        if not isinstance(groups_in, dict):
            raise ToolError('\'bit_groups\' must look like {"<hex field>": {"12": [{"m": 12, "l": "name"}]}}.')
        merged_g = pagemods._bit_groups(old.get("_groups", ""))
        for field, per_byte in groups_in.items():
            if field not in hexes or not isinstance(per_byte, dict):
                raise ToolError(f"'{field}' is not a hex field of this page. One of: {', '.join(hexes)}.")
            mine_g = dict(merged_g.get(field, {}))
            for byte, groups in per_byte.items():
                if not (str(byte).isdigit() and int(byte) < 1100 and isinstance(groups, list) and len(groups) <= 8):
                    raise ToolError(f'Byte \'{byte}\': a number counted from 0, with a list of at most 8 groups {{"m": mask, "l": name}}.')
                used = 0
                for g in groups:
                    mask = g.get("m") if isinstance(g, dict) else None
                    if not (
                        isinstance(mask, int)
                        and not isinstance(mask, bool)
                        and 1 <= mask <= 255
                        and bin(mask).count("1") >= 2
                        and not mask & used
                    ):
                        raise ToolError(
                            f"Byte {byte}: a group's mask 'm' is the bits of one byte as a number (1-255, at least two bits, e.g. bits 2 and 3 = 12); groups must not overlap."
                        )
                    used |= mask
                if groups:
                    mine_g[str(byte)] = groups
                else:
                    mine_g.pop(str(byte), None)
            merged_g[field] = mine_g
        form["bitgroups"] = json.dumps(merged_g)
    return form


def _parsed(page: dict, form: dict, old: dict | None, keep_once: bool = True) -> dict:
    try:
        return pagemods.parse(page, form, old, keep_once=keep_once)
    except pagemods.PageError as exc:
        raise ToolError(f"Invalid value: {' / '.join(str(a) for a in exc.args)}") from None


def t_add_page_entry(conn, args):
    vid = _vehicle(conn, args.get("vehicle"))
    mod, page = _page(conn, vid, args)
    values = _check_values(page, args.get("values"))
    if not values:
        raise ToolError("'values' must be an object with the fields of the entry (see list_pages).")
    form = {**pagemods.form_from(page, None, values), **_bit_forms(page, None, args)}
    try:
        row_id = pagemods.add(conn, vid, mod["addon_id"], page, _parsed(page, form, None))
    except pagemods.PageError as exc:
        raise ToolError(f"Invalid value: {' / '.join(str(a) for a in exc.args)}") from None
    events.changed()
    return {"ok": True, "id": row_id}


def t_update_page_entry(conn, args):
    vid = _vehicle(conn, args.get("vehicle"))
    mod, page = _page(conn, vid, args)
    row_id = _int(args, "id", 0, 0, 10**12)
    old = pagemods.get(conn, vid, mod["addon_id"], row_id)
    if old is None or old["page"] != page["id"]:
        raise ToolError("No such entry on this page.")
    values = _check_values(page, args.get("values"))
    bits = _bit_forms(page, old["data"], args)
    if not values and not bits:
        raise ToolError("Nothing to change: give 'values', 'bit_notes' or 'bit_groups'.")
    form = {**pagemods.form_from(page, old["data"], values), **bits}
    pagemods.update(conn, row_id, _parsed(page, form, old["data"]))
    events.changed()
    return {"ok": True, "id": row_id}


def t_delete_page_entry(conn, args):
    vid = _vehicle(conn, args.get("vehicle"))
    mod, page = _page(conn, vid, args)
    row_id = _int(args, "id", 0, 0, 10**12)
    old = pagemods.get(conn, vid, mod["addon_id"], row_id)
    if old is None or old["page"] != page["id"]:
        raise ToolError("No such entry on this page.")
    pagemods.delete(conn, row_id)
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

_INTEGRATION = {"type": "string", "description": "The integration: its id from list_pages."}
_PAGE = {"type": "string", "description": "The page: its id from list_pages."}
_PAGE_VALUES = {"type": "object", "description": "Field values by field key (see list_pages); hex fields as hex text, dates as YYYY-MM-DD."}
_BIT_NOTES = {
    "type": "object",
    "description": 'Notes of bits: {"<hex field key>": {"<byte>.<bit>": "text"}}, byte counted from 0, bit 0-7 (0 = lowest), an empty text deletes the note.',
}
_BIT_GROUPS = {
    "type": "object",
    "description": 'Groups of bits of one byte: {"<hex field key>": {"<byte>": [{"m": 12, "l": "name"}]}}; m = the bits as a number (1-255, at least two, no overlap).',
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
        "list_plugins",
        "Plugins and integrations of one vehicle (or of all): name, version, switched on or off, set up or not, source, settings (secrets hidden).",
        _schema({"vehicle": _VEHICLE}),
        False,
        t_list_plugins,
    ),
    (
        "list_documents",
        "The documents stored for a vehicle (title, category, file name, size) - not the files themselves.",
        _schema({"vehicle": _VEHICLE, "limit": {"type": "integer", "description": "1-100, default 50"}}, ("vehicle",)),
        False,
        t_list_documents,
    ),
    (
        "list_pages",
        "The pages that integrations of a vehicle keep (for example Coding: one entry per control unit): per integration its pages with the fields "
        "(key, label, type) and how many entries each has. Start here, then use list_page_entries.",
        _schema({"vehicle": _VEHICLE}, ("vehicle",)),
        False,
        t_list_pages,
    ),
    (
        "list_page_entries",
        "The entries of one page of an integration (paged). Access codes are never shown. A coding page also gives per entry its bit_notes "
        '({field: {"<byte>.<bit>": "note"}}) and bit_groups ({field: {"<byte>": [{"m": mask, "l": name}]}}); the byte is counted from 0 along the hex '
        "value, the bit 0-7 with 0 the lowest, a group's mask is its bits as one number (bits 2 and 3 = 12).",
        _schema(
            {
                "vehicle": _VEHICLE,
                "integration": _INTEGRATION,
                "page": _PAGE,
                "limit": {"type": "integer", "description": "1-100, default 25"},
                "offset": {"type": "integer"},
            },
            ("vehicle", "integration", "page"),
        ),
        False,
        t_list_page_entries,
    ),
    (
        "get_charging",
        "Charging sessions of an electric or plug-in car: when, battery level from and to, strongest charging power.",
        _schema({"vehicle": _VEHICLE, "limit": {"type": "integer", "description": "1-100, default 25"}}, ("vehicle",)),
        False,
        t_get_charging,
    ),
    (
        "get_tyres",
        "The recommended tyre pressures per season and the tyre sets of a vehicle.",
        _schema({"vehicle": _VEHICLE}, ("vehicle",)),
        False,
        t_get_tyres,
    ),
    (
        "get_settings",
        "The server-wide choices: language, unit system, currency, and how many vehicles, plugins and integrations exist.",
        _schema({}),
        False,
        t_get_settings,
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
        "update_vehicle",
        "Fill in or correct the master data of a vehicle: vin, plate, make, model, year, first_reg, hsn, tsn, engine, color (needs write access). Use it after data_gaps.",
        _schema({"vehicle": _VEHICLE, "values": _VALUES}, ("vehicle", "values")),
        True,
        t_update_vehicle,
    ),
    (
        "update_document",
        "Change title, category (manual, invoice, insurance, registration, inspection, other), doc_date, valid_until or notes of a stored document (needs write access; the file is not touched).",
        _schema({"vehicle": _VEHICLE, "id": {"type": "integer"}, "values": _VALUES}, ("vehicle", "id", "values")),
        True,
        t_update_document,
    ),
    (
        "set_tyre_pressure",
        "Set the recommended tyre pressure in bar for a season (summer, winter, allseason), front and rear axle (needs write access).",
        _schema(
            {
                "vehicle": _VEHICLE,
                "season": {"type": "string", "description": "summer, winter or allseason"},
                "front_bar": {"type": "number"},
                "rear_bar": {"type": "number"},
            },
            ("vehicle", "season", "front_bar", "rear_bar"),
        ),
        True,
        t_set_tyre_pressure,
    ),
    (
        "add_page_entry",
        "Add an entry to a page of an integration (needs write access), for example a control unit on the Coding page. 'values' by field key; for a coding "
        "page 'bit_notes' and 'bit_groups' describe its bits (same shape as list_page_entries gives).",
        _schema(
            {
                "vehicle": _VEHICLE,
                "integration": _INTEGRATION,
                "page": _PAGE,
                "values": _PAGE_VALUES,
                "bit_notes": _BIT_NOTES,
                "bit_groups": _BIT_GROUPS,
            },
            ("vehicle", "integration", "page", "values"),
        ),
        True,
        t_add_page_entry,
    ),
    (
        "update_page_entry",
        "Change an entry of a page (needs write access): only the given 'values' change. The ORIGINAL value of a field that is written once is kept once it has one. "
        "'bit_notes' adds or changes one note per bit (an empty text deletes it); 'bit_groups' replaces the groups of each byte you list (an empty list removes them). "
        "Describe the bits of a coding this way: fill the notes bit by bit and group bits that belong together under a name.",
        _schema(
            {
                "vehicle": _VEHICLE,
                "integration": _INTEGRATION,
                "page": _PAGE,
                "id": {"type": "integer"},
                "values": _PAGE_VALUES,
                "bit_notes": _BIT_NOTES,
                "bit_groups": _BIT_GROUPS,
            },
            ("vehicle", "integration", "page", "id"),
        ),
        True,
        t_update_page_entry,
    ),
    (
        "delete_page_entry",
        "Delete an entry of a page of an integration (needs write access; cannot be undone).",
        _schema(
            {"vehicle": _VEHICLE, "integration": _INTEGRATION, "page": _PAGE, "id": {"type": "integer"}},
            ("vehicle", "integration", "page", "id"),
        ),
        True,
        t_delete_page_entry,
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
    "Integrations keep pages too (for example Coding, one entry per control unit): list_pages, list_page_entries, then update_page_entry to fill in the notes and groups of bits. "
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
