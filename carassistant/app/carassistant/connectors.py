"""Plugin API: the simple way for integrations and plugins (written by anyone) to dock on.

A connector is any program that can send an HTTP request – an add-on, a script on a Raspberry Pi in the car, a Home Assistant
automation, a cloud bridge. It authenticates with a token (created under *Integrations → Connections*) and pushes values with
``POST /api/v1/vehicles/<id>/data``. Car Assistant stores them exactly like its own readings. No third-party code runs inside Car Assistant.
See docs/api.md.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
import sqlite3
from datetime import UTC, datetime

from . import db, status, summary
from . import vin as vin_info

log = logging.getLogger(__name__)

PREFIX = "ca_"
MAX_ODOMETER_KM = 2_000_000
CLOSURE_NAME = re.compile(r"[a-z][a-z0-9_]{0,31}")
MAX_CLOSURES = 16  # per object (doors / windows)


class ApiError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def create_token(conn: sqlite3.Connection, name: str, vehicle_id: int | None) -> str:
    name = " ".join((name or "").split())[:40]
    if not name:
        raise ApiError("name_required", "A name is required.")
    token = PREFIX + secrets.token_urlsafe(32)
    conn.execute(
        "INSERT INTO api_tokens(name, token_hash, vehicle_id, created_at) VALUES(?,?,?,?)", (name, _hash(token), vehicle_id, _now())
    )
    return token


TOKEN_FORMAT = re.compile(PREFIX + r"[A-Za-z0-9_-]{30,80}")


def adopt_token(conn: sqlite3.Connection, name: str, vehicle_id: int | None, token: str) -> None:
    """Take over a token that already exists on a device (its file was made earlier): the app stores only its fingerprint, as for a new one.
    It must have the shape of the app's tokens and may not be used anywhere else. ApiError ``token_format`` / ``token_taken``."""
    if not TOKEN_FORMAT.fullmatch(token or ""):
        raise ApiError("token_format", "That is not a token of Car Assistant.")
    if conn.execute("SELECT 1 FROM api_tokens WHERE token_hash = ?", (_hash(token),)).fetchone():
        raise ApiError("token_taken", "This token is already in use.")
    name = " ".join((name or "").split())[:40] or "plugin"
    conn.execute(
        "INSERT INTO api_tokens(name, token_hash, vehicle_id, created_at) VALUES(?,?,?,?)", (name, _hash(token), vehicle_id, _now())
    )


def fingerprint(conn: sqlite3.Connection, token_id: int | None) -> str:
    """A short mark of a stored token (the start of its fingerprint) to tell tokens apart; the token itself is never known here."""
    row = conn.execute("SELECT token_hash FROM api_tokens WHERE id = ?", (token_id,)).fetchone() if token_id else None
    return row["token_hash"][:8] if row else ""


def token_matches(conn: sqlite3.Connection, token_id: int | None, candidate: str) -> bool:
    """Is ``candidate`` the token with this id? Compared by fingerprint (the token itself is never stored), in constant time."""
    import hmac

    row = conn.execute("SELECT token_hash FROM api_tokens WHERE id = ?", (token_id,)).fetchone() if token_id else None
    return bool(row) and bool(candidate) and hmac.compare_digest(row["token_hash"], _hash(candidate))


def remember(conn: sqlite3.Connection, token_id: int | None, token: str | None) -> bool:
    """Keep an ENCRYPTED copy of a plugin's token (always on; only a token that really is the one of ``token_id``). The copy lets the set-up
    guide offer the token again and goes into the backups; it is never part of a log or a page except that guide for an administrator."""
    if not token_id or not token or not token_matches(conn, token_id, token):
        return False
    from . import vault

    conn.execute("UPDATE api_tokens SET token_enc = ? WHERE id = ?", (vault.encrypt(token), token_id))
    return True


def remembered(conn: sqlite3.Connection, token_id: int | None) -> str:
    """The kept token of ``token_id`` ('' when none, or when the copy does not fit the token any more)."""
    if not token_id:
        return ""
    row = conn.execute("SELECT token_enc FROM api_tokens WHERE id = ?", (token_id,)).fetchone()
    if not row or not row["token_enc"]:
        return ""
    from . import vault

    try:
        token = vault.decrypt(row["token_enc"]) or ""
    except Exception:
        return ""
    return token if token_matches(conn, token_id, token) else ""


def reseal(conn: sqlite3.Connection) -> None:
    """After a restore: a kept token that came in readable (backups carry them so they work on another system) is encrypted with this system's key."""
    from . import vault

    for row in conn.execute(
        "SELECT id, token_enc FROM api_tokens WHERE token_enc IS NOT NULL AND token_enc NOT LIKE ?", (vault.PREFIX + "%",)
    ).fetchall():
        conn.execute("UPDATE api_tokens SET token_enc = ? WHERE id = ?", (vault.encrypt(row["token_enc"]), row["id"]))


def has_live_source(conn: sqlite3.Connection, vehicle_id: int) -> bool:
    """True when this vehicle gets (or can get) live values: it already has some, or a connector token."""
    return (
        conn.execute("SELECT 1 FROM live WHERE vehicle_id = ? LIMIT 1", (vehicle_id,)).fetchone() is not None
        or conn.execute("SELECT 1 FROM api_tokens WHERE vehicle_id = ? LIMIT 1", (vehicle_id,)).fetchone() is not None
    )


def list_tokens(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT t.id, t.name, t.vehicle_id, t.created_at, t.last_used, v.name AS vehicle_name "
        "FROM api_tokens t LEFT JOIN vehicles v ON v.id = t.vehicle_id ORDER BY t.id"
    ).fetchall()


def delete_token(conn: sqlite3.Connection, token_id: int) -> None:
    conn.execute("DELETE FROM api_tokens WHERE id = ?", (token_id,))


def verify(conn: sqlite3.Connection, token: str | None) -> sqlite3.Row | None:
    if not token or not token.startswith(PREFIX) or len(token) > 100:
        return None
    row = conn.execute(
        "SELECT t.id, t.name, t.vehicle_id FROM api_tokens t WHERE t.token_hash = ? "
        "AND NOT EXISTS (SELECT 1 FROM vehicle_addons a WHERE a.token_id = t.id AND a.active = 0)",  # a switched-off plugin is refused
        (_hash(token),),
    ).fetchone()
    if row:
        conn.execute("UPDATE api_tokens SET last_used = ? WHERE id = ?", (_now(), row["id"]))
    return row


def _num(data: dict, key: str, low: float, high: float) -> float | None:
    if key not in data or data[key] is None:
        return None
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
        raise ApiError("invalid_value", f"'{key}' must be a number between {low:g} and {high:g}.", 422)
    return float(value)


ENERGY_KEYS = ("fuel_level", "battery_pct", "fuel_amount", "range_km")  # readings that tell how full the tank or battery is
WATCHED = ("fuel_level", "charging", "battery_pct", "charge_power_kw")  # readings whose change can mean a refuel or a charging session


def moment(value) -> str | None:
    """A point in time given as an ISO text (``2026-11-20T08:15:00Z``, with or without a zone: UTC then), a datetime or seconds since 1970 ->
    the stored form (UTC, whole seconds). Nothing in the future; None when it cannot be read or is empty."""
    if value in (None, ""):
        return None
    try:
        if isinstance(value, datetime):
            stamp = value
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            stamp = datetime.fromtimestamp(float(value), UTC)
        else:
            stamp = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except (ValueError, OverflowError, OSError):
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return min(stamp.astimezone(UTC), datetime.now(UTC)).isoformat(timespec="seconds")


def _store(conn: sqlite3.Connection, vehicle_id: int, key: str, value: str, at: str | None = None) -> None:
    """Keep one live value. The time kept with it is WHEN THE CAR REPORTED it: ``at`` when the sender knows it (``measured_at``, or the time Home
    Assistant gives), otherwise the arrival - but a value that is exactly the one already stored is no news (a plugin that sends its remembered
    values again after a restart of the app does not make the car look as if it had just reported), and a time never goes backwards."""
    row = conn.execute("SELECT value, updated FROM live WHERE vehicle_id = ? AND key = ?", (vehicle_id, key)).fetchone()
    before = row["value"] if row else None
    if at is not None and row and row["updated"] and at < row["updated"]:
        return  # a measurement older than the one we have (a slow plugin, a second source of the same field): the newer value stays
    if row and row["value"] == value and at is None:
        stamp = row["updated"]
    else:
        stamp = at or _now()
        if row and row["updated"] and stamp < row["updated"]:
            stamp = row["updated"]
    conn.execute(
        "INSERT INTO live(vehicle_id, key, value, updated) VALUES(?,?,?,?) "
        "ON CONFLICT(vehicle_id, key) DO UPDATE SET value = excluded.value, updated = excluded.updated",
        (vehicle_id, key, value, stamp),
    )
    if key in WATCHED:
        _watch(conn, vehicle_id, key, before, value)
    if key in ENERGY_KEYS and value != before:
        from . import notify

        notify.energy_changed(vehicle_id)  # the low tank / battery message does not wait for the regular check


def _watch(conn: sqlite3.Connection, vehicle_id: int, key: str, before, after) -> None:
    """A watched reading was stored: a tank that jumped is a refuel, a battery that starts / stops charging is a charging session. The person is
    told at once when something was noticed. Noticing must never break storing the reading."""
    from . import charge_detect, notify, refuel_detect

    try:
        if key == "fuel_level":
            noticed = before is not None and refuel_detect.level_changed(conn, vehicle_id, before, after)
        else:
            noticed = charge_detect.seen(conn, vehicle_id, key, before, after)
        if noticed:
            notify.event_now()
    except Exception:
        log.exception("Refuel / charging detection failed")


# plain numbers: api key -> (live key, low, high)
NUMBERS = {
    "fuel_level_pct": ("fuel_level", 0, 100),
    "range_km": ("range_km", 0, 3000),
    "speed_kmh": ("speed_kmh", 0, 450),
    "outside_temp_c": ("outside_temp_c", -60, 70),
    "battery_12v_v": ("battery_12v_v", 0, 30),
    "battery_pct": ("battery_pct", 0, 100),  # high-voltage battery of an electric / hybrid vehicle
    "charge_power_kw": ("charge_power_kw", 0, 1000),
    "charge_limit_pct": ("charge_limit_pct", 0, 100),
    "charge_minutes_left": ("charge_minutes_left", 0, 5000),
    "coolant_temp_c": ("coolant_temp_c", -40, 200),
    "oil_temp_c": ("oil_temp_c", -40, 200),
    "cabin_temp_c": ("cabin_temp_c", -40, 80),
    "target_temp_c": ("target_temp_c", 5, 40),
    "heading_deg": ("heading_deg", 0, 360),
    "consumption_l_100km": ("consumption", 0, 100),  # l/100 km, or kWh/100 km for an electric car
    "service_due_days": ("service_due_days", -3650, 3650),  # reported by the car; negative = overdue
    "service_due_km": ("service_due_km", -100000, 100000),
    "oil_change_due_days": ("oil_change_due_days", -3650, 3650),  # reported by the car; negative = overdue
    "oil_change_due_km": ("oil_change_due_km", -100000, 100000),
    "fuel_amount": (
        "fuel_amount",
        0,
        1000,
    ),  # litres in the tank (kWh in the battery of an electric car): when the car reports the amount itself
    "adblue_level_pct": ("adblue_level_pct", 0, 100),  # exhaust fluid of a diesel
    "adblue_range_km": ("adblue_range_km", 0, 50000),
    "oil_level_pct": ("oil_level_pct", 0, 100),
    "speed_limit_kmh": ("speed_limit_kmh", 0, 250),  # the limit the car currently reads from signs / navigation
}
BOOLS = ("charging", "plugged", "climate_on", "parking_brake", "oil_warning")  # stored as yes / no
TYRES = ("fl", "fr", "rl", "rr")  # front left, front right, rear left, rear right
KNOWN = {
    "measured_at",
    "odometer_km",
    "vin",
    "position",
    "ignition",
    "doors",
    "windows",
    "lights",
    "locked",
    "warnings",
    "tyre_pressure_bar",
    *BOOLS,
    *NUMBERS,
}
LOG_LEVELS = ("debug", "info", "warn", "error")
MAX_LOG_LINES = 50  # per request
MAX_LOG_KEEP = 1000  # the default: lines kept per plugin (a system setting, see log_keep)
LOG_KEEP_CHOICES = (200, 500, 1000, 2000, 5000, 20000)
LOG_DAYS_CHOICES = (1, 7, 30)
DEFAULT_LOG_DAYS = 7
MAX_WARNINGS = 16
MAX_WARNING_TEXT = 120


def _merged_closures(conn: sqlite3.Connection, vehicle_id: int, data: dict, key: str) -> dict[str, bool] | None:
    """Validate ``{"name": true|false|null}`` and merge it into the stored state. Only the names sent change; null removes a name."""
    update = data.get(key)
    if update is None:
        return None
    if not isinstance(update, dict):
        raise ApiError("invalid_value", f"'{key}' must be an object like {{\"front_left\": true}} (true = open, false = closed).", 422)
    for name, state in update.items():
        if not CLOSURE_NAME.fullmatch(name):
            raise ApiError(
                "invalid_value",
                f"'{key}': the name '{name}' must be lower-case letters, digits and _ (up to 32, starting with a letter).",
                422,
            )
        if state is not None and not isinstance(state, bool):
            raise ApiError("invalid_value", f"'{key}.{name}' must be true (open), false (closed) or null (remove).", 422)
    row = conn.execute("SELECT value FROM live WHERE vehicle_id = ? AND key = ?", (vehicle_id, key)).fetchone()
    merged = status.parse_flags(row["value"] if row else None)
    for name, state in update.items():
        if state is None:
            merged.pop(name, None)
        else:
            merged[name] = state
    if len(merged) > MAX_CLOSURES:
        raise ApiError("invalid_value", f"'{key}' may hold at most {MAX_CLOSURES} names.", 422)
    return merged


def _merged_warnings(conn: sqlite3.Connection, vehicle_id: int, data: dict) -> dict[str, str] | None:
    """Validate ``{"code": "text"|null}`` and merge it into the stored messages. Only the codes sent change; null removes a code."""
    update = data.get("warnings")
    if update is None:
        return None
    if not isinstance(update, dict):
        raise ApiError(
            "invalid_value", '\'warnings\' must be an object like {"tyre_pressure": "Tyre pressure low"} (null removes a code).', 422
        )
    for code, text in update.items():
        if not CLOSURE_NAME.fullmatch(code):
            raise ApiError(
                "invalid_value",
                f"'warnings': the code '{code}' must be lower-case letters, digits and _ (up to 32, starting with a letter).",
                422,
            )
        if text is not None and not (isinstance(text, str) and text.strip()):
            raise ApiError("invalid_value", f"'warnings.{code}' must be a text or null (remove).", 422)
    row = conn.execute("SELECT value FROM live WHERE vehicle_id = ? AND key = 'warnings'", (vehicle_id,)).fetchone()
    merged = status.parse_warnings(row["value"] if row else None)
    for code, text in update.items():
        if text is None:
            merged.pop(code, None)
        else:
            merged[code] = " ".join(text.split())[:MAX_WARNING_TEXT]
    if len(merged) > MAX_WARNINGS:
        raise ApiError("invalid_value", f"'warnings' may hold at most {MAX_WARNINGS} codes.", 422)
    return merged


def _merged_tyres(conn: sqlite3.Connection, vehicle_id: int, data: dict) -> dict[str, float] | None:
    """Validate ``{"fl": 2.4, "fr": 2.4, "rl": null, ...}`` (bar) and merge it into the stored pressures; null removes a wheel."""
    update = data.get("tyre_pressure_bar")
    if update is None:
        return None
    if not isinstance(update, dict) or set(update) - set(TYRES):
        raise ApiError("invalid_value", "'tyre_pressure_bar' must be an object with the keys fl, fr, rl, rr (bar, or null).", 422)
    for wheel, value in update.items():
        if value is not None and (isinstance(value, bool) or not isinstance(value, int | float) or not 0 <= value <= 8):
            raise ApiError("invalid_value", f"'tyre_pressure_bar.{wheel}' must be a number from 0 to 8 (bar) or null.", 422)
    row = conn.execute("SELECT value FROM live WHERE vehicle_id = ? AND key = 'tyre_pressure_bar'", (vehicle_id,)).fetchone()
    merged = status.parse_numbers(row["value"] if row else None)
    for wheel, value in update.items():
        if value is None:
            merged.pop(wheel, None)
        else:
            merged[wheel] = round(float(value), 2)
    return merged


# ---- the one way towards the vehicle: switches the dashboard sets and the vehicle reads (first one: debug)


DEBUG_DAYS = (1, 3, 7)  # how long the log switch of a plugin stays on
DEBUG_DEFAULT_DAYS = 1


def plugin_debug_state(conn: sqlite3.Connection, vehicle_id: int, addon_id: str | None) -> tuple[int, datetime] | None:
    """The log switch of ONE plugin: ``(days, until)`` while it is on, ``None`` when it is off or its time has run out. It is stored as
    ``<days>|<until>``; the older form ``1`` (no end) counts as off - nothing stays on for ever."""
    if not addon_id:
        return None
    raw = db.get_setting(conn, f"debug.{vehicle_id}.{addon_id}", "")
    days, _sep, until = raw.partition("|")
    try:
        end = datetime.fromisoformat(until)
    except ValueError:
        return None
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    return (int(days), end) if days.isdigit() and end > datetime.now(UTC) else None


def plugin_debug(conn: sqlite3.Connection, vehicle_id: int, addon_id: str | None) -> bool:
    """Is the log switch of this plugin on - and has its time not run out yet?"""
    return plugin_debug_state(conn, vehicle_id, addon_id) is not None


def set_plugin_debug(conn: sqlite3.Connection, vehicle_id: int, addon_id: str, on: bool, days: int = DEBUG_DEFAULT_DAYS) -> None:
    """Switch the log of one plugin on for ``days`` days from NOW (1, 3 or 7; changing the time starts it again) or off."""
    from datetime import timedelta

    days = days if days in DEBUG_DAYS else DEBUG_DEFAULT_DAYS
    until = (datetime.now(UTC) + timedelta(days=days)).isoformat(timespec="seconds")
    db.set_setting(conn, f"debug.{vehicle_id}.{addon_id}", f"{days}|{until}" if on else None)


def expire_debug(conn: sqlite3.Connection) -> None:
    """Forget the log switches whose time has run out (they are off already; this only tidies the settings)."""
    for row in conn.execute("SELECT key, value FROM settings WHERE key LIKE 'debug.%.%'").fetchall():
        vehicle_id, _dot, addon_id = row["key"].removeprefix("debug.").partition(".")
        if vehicle_id.isdigit() and addon_id and plugin_debug_state(conn, int(vehicle_id), addon_id) is None:
            db.set_setting(conn, row["key"], None)


def debug_enabled(conn: sqlite3.Connection, vehicle_id: int, addon_id: str | None = None) -> bool:
    """Debug is on for the whole car (page *Debug & log*) or for this one plugin (its own button)."""
    return db.get_setting(conn, f"debug.{vehicle_id}", "") == "1" or plugin_debug(conn, vehicle_id, addon_id)


def set_debug(conn: sqlite3.Connection, vehicle_id: int, on: bool) -> None:
    db.set_setting(conn, f"debug.{vehicle_id}", "1" if on else None)


INTERVALS = (30, 60, 120, 180, 300)  # seconds the plugin is asked to wait between reports
DEFAULT_INTERVAL = 120


def interval_s(conn: sqlite3.Connection, vehicle_id: int) -> int:
    raw = db.get_setting(conn, f"interval.{vehicle_id}", "")
    return int(raw) if raw.isdigit() and int(raw) in INTERVALS else DEFAULT_INTERVAL


def set_interval(conn: sqlite3.Connection, vehicle_id: int, seconds: int) -> None:
    if seconds in INTERVALS:  # anything else is ignored
        db.set_setting(conn, f"interval.{vehicle_id}", str(seconds) if seconds != DEFAULT_INTERVAL else None)


def control(conn: sqlite3.Connection, vehicle_id: int, addon_id: str | None = None) -> dict:
    """What the dashboard asks the vehicle (plugin) to do. The plugin reads it; it never writes it. ``debug`` is on when it is on for the car
    or for the plugin that asks."""
    return {"debug": debug_enabled(conn, vehicle_id, addon_id), "interval_s": interval_s(conn, vehicle_id)}


def ingest_logs(conn: sqlite3.Connection, vehicle_id: int, data: dict, source: str, token_id: int | None = None) -> int:
    """Store debug lines sent by the vehicle. Refused while debug is off for this vehicle (nothing is kept)."""
    if not debug_enabled(conn, vehicle_id, addon_for_token(conn, token_id)):
        raise ApiError("debug_off", "Debug is off for this vehicle. Do not send log lines; read /control to see the switch.", 409)
    lines = data.get("lines") if isinstance(data, dict) else None
    if not isinstance(lines, list) or not 0 < len(lines) <= MAX_LOG_LINES:
        raise ApiError("invalid_value", f"'lines' must be a list of 1 to {MAX_LOG_LINES} items.", 422)
    rows = []
    for item in lines:
        if isinstance(item, str):
            item = {"message": item}
        if not isinstance(item, dict) or not isinstance(item.get("message"), str) or not item["message"].strip():
            raise ApiError("invalid_value", "Every line needs a 'message' text (optional: 'level', 'ts').", 422)
        level = item.get("level", "info")
        if level not in LOG_LEVELS:
            raise ApiError("invalid_value", f"'level' must be one of {', '.join(LOG_LEVELS)}.", 422)
        ts = item.get("ts")
        ts = ts[:32] if isinstance(ts, str) and ts else _now()
        rows.append((ts, level, source[:40], item["message"][:500]))
    write_logs(conn, vehicle_id, addon_for_token(conn, token_id), rows)
    return len(rows)


MAX_EVENTS = 200  # per request
MAX_EVENTS_KEEP = 2000  # per vehicle
EVENT_TYPE = re.compile(r"[a-z][a-z0-9_.]{0,39}")
MAX_TRACK_POINTS = 500  # per request
MAX_TRACK_KEEP = 50_000  # per vehicle
SIGNAL_NAME = re.compile(r"[a-z][a-z0-9_.]{0,63}")
MAX_SIGNALS = 300  # per vehicle
MAX_SIGNAL_TEXT = 2000


def _iso(ts: object) -> str:
    """A point's time as UTC ISO text; anything unreadable raises."""
    if not isinstance(ts, str):
        raise ValueError
    when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return (when if when.tzinfo else when.replace(tzinfo=UTC)).astimezone(UTC).isoformat(timespec="seconds")


def ingest_track(conn: sqlite3.Connection, vehicle_id: int, data: dict) -> int:
    """Store positions of a drive: ``{"points": [{"ts", "lat", "lon", "speed_kmh"}]}`` (``ts`` optional = now). The newest point also
    becomes the car's current position and speed."""
    points = data.get("points") if isinstance(data, dict) else None
    if not isinstance(points, list) or not 0 < len(points) <= MAX_TRACK_POINTS:
        raise ApiError("invalid_value", f"'points' must be a list of 1 to {MAX_TRACK_POINTS} items.", 422)
    rows = []
    for item in points:
        if not isinstance(item, dict):
            raise ApiError("invalid_value", "Every point is an object with lat and lon.", 422)
        lat, lon, speed = _num(item, "lat", -90, 90), _num(item, "lon", -180, 180), _num(item, "speed_kmh", 0, 450)
        if lat is None or lon is None:
            raise ApiError("invalid_value", "Every point needs lat and lon.", 422)
        try:
            ts = _iso(item["ts"]) if item.get("ts") is not None else _now()
        except ValueError as exc:
            raise ApiError("invalid_value", "'ts' must be an ISO time like 2026-11-15T08:30:00Z.", 422) from exc
        rows.append((vehicle_id, ts, round(lat, 6), round(lon, 6), speed))
    conn.executemany("INSERT INTO vehicle_track(vehicle_id, ts, lat, lon, speed_kmh) VALUES(?,?,?,?,?)", rows)
    conn.execute(
        "DELETE FROM vehicle_track WHERE vehicle_id = ? AND id NOT IN (SELECT id FROM vehicle_track WHERE vehicle_id = ? ORDER BY id DESC LIMIT ?)",
        (vehicle_id, vehicle_id, MAX_TRACK_KEEP),
    )
    newest = max(rows, key=lambda r: r[1])
    at = (
        newest[1] if any(isinstance(i, dict) and i.get("ts") is not None for i in points) else None
    )  # the point's own time, when it has one
    _store(conn, vehicle_id, "position", f"{newest[2]:.6f},{newest[3]:.6f}", at)
    if newest[4] is not None:
        _store(conn, vehicle_id, "speed_kmh", f"{newest[4]:g}", at)
    from . import trips

    trips.from_track(conn, vehicle_id)  # drives that have ended become trips of the log book
    return len(rows)


def read_track(conn: sqlite3.Connection, vehicle_id: int, since: str | None, limit: int) -> list[dict]:
    args: list = [vehicle_id]
    where = ""
    if since:
        try:
            args.append(_iso(since))
        except ValueError as exc:
            raise ApiError("invalid_value", "'since' must be an ISO time.", 422) from exc
        where = " AND ts > ?"
    args.append(max(1, min(limit, 1000)))
    rows = conn.execute(
        f"SELECT ts, lat, lon, speed_kmh FROM vehicle_track WHERE vehicle_id = ?{where} ORDER BY ts, id LIMIT ?",
        args,
    ).fetchall()
    return [{"ts": r["ts"], "lat": r["lat"], "lon": r["lon"], "speed_kmh": r["speed_kmh"]} for r in rows]


def ingest_events(conn: sqlite3.Connection, vehicle_id: int, data: dict) -> int:
    """Events with a time (and maybe a place): ``{"events": [{"type": "speed_sign", "ts", "text", "value", "lat", "lon"}]}``."""
    events = data.get("events") if isinstance(data, dict) else None
    if not isinstance(events, list) or not 0 < len(events) <= MAX_EVENTS:
        raise ApiError("invalid_value", f"'events' must be a list of 1 to {MAX_EVENTS} items.", 422)
    rows = []
    for item in events:
        if not isinstance(item, dict) or not isinstance(item.get("type"), str) or not EVENT_TYPE.fullmatch(item["type"]):
            raise ApiError("invalid_value", "Every event needs a 'type' (lower-case letters, digits, _ and ., up to 40).", 422)
        text = item.get("text", "")
        if not isinstance(text, str):
            raise ApiError("invalid_value", "'text' must be a text.", 422)
        value = _num(item, "value", -1e9, 1e9)
        lat, lon = _num(item, "lat", -90, 90), _num(item, "lon", -180, 180)
        if (lat is None) != (lon is None):
            raise ApiError("invalid_value", "An event place needs lat and lon together.", 422)
        try:
            ts = _iso(item["ts"]) if item.get("ts") is not None else _now()
        except ValueError as exc:
            raise ApiError("invalid_value", "'ts' must be an ISO time like 2026-11-15T08:30:00Z.", 422) from exc
        rows.append((vehicle_id, ts, item["type"], " ".join(text.split())[:200], value, lat, lon))
    conn.executemany("INSERT INTO vehicle_events(vehicle_id, ts, type, text, value, lat, lon) VALUES(?,?,?,?,?,?,?)", rows)
    conn.execute(
        "DELETE FROM vehicle_events WHERE vehicle_id = ? AND id NOT IN (SELECT id FROM vehicle_events WHERE vehicle_id = ? ORDER BY id DESC LIMIT ?)",
        (vehicle_id, vehicle_id, MAX_EVENTS_KEEP),
    )
    return len(rows)


def read_events(conn: sqlite3.Connection, vehicle_id: int, since: str | None, kind: str | None, limit: int) -> list[dict]:
    where, args = "", [vehicle_id]
    if since:
        try:
            args.append(_iso(since))
        except ValueError as exc:
            raise ApiError("invalid_value", "'since' must be an ISO time.", 422) from exc
        where += " AND ts > ?"
    if kind:
        where += " AND type = ?"
        args.append(kind)
    args.append(max(1, min(limit, 1000)))
    rows = conn.execute(
        f"SELECT ts, type, text, value, lat, lon FROM vehicle_events WHERE vehicle_id = ?{where} ORDER BY ts, id LIMIT ?", args
    ).fetchall()
    return [dict(r) for r in rows]


def ingest_trip_summary(conn: sqlite3.Connection, vehicle_id: int, data: dict) -> str:
    """The values of the car's own trip computer for a drive that just ended: ``{"ts", "distance_km", "consumption_l_100km", "avg_speed_kmh",
    "minutes"}`` (all optional but at least one value). They are given to the trip that ended at ``ts`` (now when missing); when that trip is
    not made yet they wait for it."""
    if not isinstance(data, dict):
        raise ApiError("invalid_body", "The body must be a JSON object.", 422)
    try:
        ts = _iso(data["ts"]) if data.get("ts") is not None else _now()
    except ValueError as exc:
        raise ApiError("invalid_value", "'ts' must be an ISO time like 2026-11-15T08:30:00Z.", 422) from exc
    km = _num(data, "distance_km", 0, 5000)
    cons = _num(data, "consumption_l_100km", 0, 100)
    speed = _num(data, "avg_speed_kmh", 0, 400)
    minutes = _num(data, "minutes", 0, 100000)
    if km is None and cons is None and speed is None and minutes is None:
        raise ApiError("invalid_value", "Send at least one of distance_km, consumption_l_100km, avg_speed_kmh, minutes.", 422)
    conn.execute(
        "INSERT INTO trip_summaries(vehicle_id, ts, distance_km, consumption, avg_kmh, minutes) VALUES(?,?,?,?,?,?)",
        (vehicle_id, ts, km, cons, speed, round(minutes) if minutes is not None else None),
    )
    from . import trips

    trips.from_track(conn, vehicle_id)  # a drive that has ended becomes its trip first, then the values are attached
    trips.attach_summaries(conn, vehicle_id)
    return "stored"


def ingest_refuel(conn: sqlite3.Connection, vehicle_id: int, data: dict, source: str) -> str:
    """A refuel the car noticed (the tank jumped): ``{"date", "odometer_km", "amount", "price_total", "full_tank"}``, all optional. Becomes an
    entry of the fuel log marked with the plugin; an entry already there for that day and mileage is left alone."""
    if not isinstance(data, dict):
        raise ApiError("invalid_body", "The body must be a JSON object.", 422)
    day = data.get("date") or datetime.now(UTC).astimezone().date().isoformat()
    try:
        day = datetime.fromisoformat(str(day)).date().isoformat()
    except ValueError as exc:
        raise ApiError("invalid_value", "'date' must be like 2026-11-15.", 422) from exc
    km = _num(data, "odometer_km", 1, MAX_ODOMETER_KM)
    amount, total = _num(data, "amount", 0.1, 1000), _num(data, "price_total", 0, 100000)
    full = data.get("full_tank", False)
    if not isinstance(full, bool):
        raise ApiError("invalid_value", "'full_tank' must be true or false.", 422)
    km = round(km) if km is not None else None
    same = conn.execute("SELECT odometer_km FROM fuel WHERE vehicle_id = ? AND date = ?", (vehicle_id, day)).fetchall()
    if any(km is None or r["odometer_km"] is None or abs(r["odometer_km"] - km) <= 5 for r in same):
        return "ignored (an entry for this day and mileage exists)"
    unfinished = amount is None  # the car noticed it but knows no amount: the person completes it, like a refuel noticed by the app
    conn.execute(  # the mark of a reported refuel is in its own columns (the notes are the person's)
        "INSERT INTO fuel(vehicle_id, date, odometer_km, amount, price_total, full_tank, auto_kind, auto_src, auto_at, auto_open) "
        "VALUES(?,?,?,?,?,?,'api',?,?,?)",
        (
            vehicle_id,
            day,
            km,
            amount,
            total,
            1 if full else 0,
            source[:60] or None,
            datetime.now(UTC).astimezone().strftime("%Y-%m-%dT%H:%M"),
            1 if unfinished else 0,
        ),
    )
    if unfinished:
        try:
            from . import notify

            notify.event_now()
        except Exception:
            log.exception("The refuel could not be announced")
    return "stored"


def ingest_signals(conn: sqlite3.Connection, vehicle_id: int, data: dict) -> int:
    """Park free, car-specific values: ``{"signals": {"name": value | null}}``. Names are lower-case with ``_`` and ``.``; ``null`` removes one.
    The app only keeps and shows them (Debug page, read back); it does not interpret them."""
    signals = data.get("signals") if isinstance(data, dict) else None
    if not isinstance(signals, dict) or not signals:
        raise ApiError("invalid_value", "'signals' must be an object like {\"kombi.odo_km\": 52340}.", 422)
    clean: dict[str, str | None] = {}
    for name, value in signals.items():
        if not SIGNAL_NAME.fullmatch(name):
            raise ApiError(
                "invalid_value", f"The name '{name}' must be lower-case letters, digits, _ and . (up to 64, starting with a letter).", 422
            )
        if value is None:
            clean[name] = None
        elif isinstance(value, bool | int | float | str):
            clean[name] = str(value).lower() if isinstance(value, bool) else str(value)[:MAX_SIGNAL_TEXT]
        else:
            raise ApiError("invalid_value", f"'{name}' must be a text, number, true/false or null.", 422)
    have = {r["name"] for r in conn.execute("SELECT name FROM vehicle_signals WHERE vehicle_id = ?", (vehicle_id,))}
    final = (have | {n for n, v in clean.items() if v is not None}) - {n for n, v in clean.items() if v is None}
    if len(final) > MAX_SIGNALS:
        raise ApiError("invalid_value", f"At most {MAX_SIGNALS} signals per vehicle.", 422)
    now = _now()
    for name, value in clean.items():
        if value is None:
            conn.execute("DELETE FROM vehicle_signals WHERE vehicle_id = ? AND name = ?", (vehicle_id, name))
        else:
            conn.execute(
                "INSERT INTO vehicle_signals(vehicle_id, name, value, updated) VALUES(?,?,?,?) "
                "ON CONFLICT(vehicle_id, name) DO UPDATE SET value = excluded.value, updated = excluded.updated",
                (vehicle_id, name, value, now),
            )
    return len(clean)


def read_signals(conn: sqlite3.Connection, vehicle_id: int) -> dict[str, dict]:
    return {
        r["name"]: {"value": r["value"], "updated": r["updated"]}
        for r in conn.execute("SELECT name, value, updated FROM vehicle_signals WHERE vehicle_id = ? ORDER BY name", (vehicle_id,))
    }


def log_keep(conn: sqlite3.Connection) -> int:
    """How many log lines are kept per plugin (Settings -> System); the oldest go first."""
    raw = db.get_setting(conn, "logs.max_lines", "")
    return int(raw) if raw.isdigit() and int(raw) in LOG_KEEP_CHOICES else MAX_LOG_KEEP


def set_log_keep(conn: sqlite3.Connection, lines: int) -> None:
    if lines in LOG_KEEP_CHOICES:
        db.set_setting(conn, "logs.max_lines", str(lines) if lines != MAX_LOG_KEEP else None)
        trim_all(conn)


def log_days(conn: sqlite3.Connection) -> int:
    """How long log lines are kept (Settings -> System): 1, 7 or 30 days."""
    raw = db.get_setting(conn, "logs.days", "")
    return int(raw) if raw.isdigit() and int(raw) in LOG_DAYS_CHOICES else DEFAULT_LOG_DAYS


def set_log_days(conn: sqlite3.Connection, days: int) -> None:
    if days in LOG_DAYS_CHOICES:
        db.set_setting(conn, "logs.days", str(days) if days != DEFAULT_LOG_DAYS else None)
        trim_all(conn)


def _cutoff(conn: sqlite3.Connection) -> str:
    from datetime import timedelta

    return (datetime.now(UTC) - timedelta(days=log_days(conn))).isoformat(timespec="seconds")


def addon_for_token(conn: sqlite3.Connection, token_id: int | None) -> str | None:
    row = conn.execute("SELECT addon_id FROM vehicle_addons WHERE token_id = ?", (token_id,)).fetchone() if token_id else None
    return row["addon_id"] if row else None


def write_logs(conn: sqlite3.Connection, vehicle_id: int, addon_id: str | None, rows: list[tuple]) -> None:
    """Keep log lines (``ts, level, source, message``) of one plugin of one car and cut that plugin's lines down to the limit."""
    added = _now()
    conn.executemany(
        "INSERT INTO vehicle_logs(vehicle_id, addon_id, ts, level, source, message, added) VALUES(?,?,?,?,?,?,?)",
        [(vehicle_id, addon_id, *row, added) for row in rows],
    )
    trim_logs(conn, vehicle_id, addon_id)


def trim_logs(conn: sqlite3.Connection, vehicle_id: int, addon_id: str | None) -> None:
    conn.execute(
        "DELETE FROM vehicle_logs WHERE vehicle_id = ? AND addon_id IS ? AND added IS NOT NULL AND added < ?",
        (vehicle_id, addon_id, _cutoff(conn)),
    )
    conn.execute("DELETE FROM vehicle_traffic WHERE vehicle_id = ? AND addon_id IS ? AND ts < ?", (vehicle_id, addon_id, _cutoff(conn)))
    conn.execute(
        "DELETE FROM vehicle_logs WHERE vehicle_id = ? AND addon_id IS ? AND id NOT IN "
        "(SELECT id FROM vehicle_logs WHERE vehicle_id = ? AND addon_id IS ? ORDER BY id DESC LIMIT ?)",
        (vehicle_id, addon_id, vehicle_id, addon_id, log_keep(conn)),
    )


def trim_all(conn: sqlite3.Connection) -> None:
    for r in conn.execute("SELECT DISTINCT vehicle_id, addon_id FROM vehicle_logs").fetchall():
        trim_logs(conn, r["vehicle_id"], r["addon_id"])


def record_traffic(
    conn: sqlite3.Connection,
    vehicle_id: int,
    addon_id: str | None,
    kind: str,
    method: str,
    path: str,
    status: int,
    nbytes: int,
    ms: int,
    detail: str,
) -> None:
    """One call to watch (debug only: the caller checks the switch). Only the shape is kept - addresses, sizes, times, the names of the fields -
    never the values. The newest lines up to the log limit stay - PER PLUGIN: a plugin that calls a lot never pushes out the lines of another."""
    conn.execute(
        "INSERT INTO vehicle_traffic(vehicle_id, addon_id, ts, kind, method, path, status, bytes, ms, detail) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (vehicle_id, addon_id, _now(), kind, method[:8], path[:200], status, max(0, nbytes), max(0, ms), detail[:200]),
    )
    conn.execute(
        "DELETE FROM vehicle_traffic WHERE vehicle_id = ? AND addon_id IS ? AND id NOT IN "
        "(SELECT id FROM vehicle_traffic WHERE vehicle_id = ? AND addon_id IS ? ORDER BY id DESC LIMIT ?)",
        (vehicle_id, addon_id, vehicle_id, addon_id, log_keep(conn)),
    )


def note_usage(conn: sqlite3.Connection, vehicle_id: int, addon_id: str | None, method: str, endpoint: str, fields: str) -> None:
    """Remember that this plugin used this interface: address, the NAMES of the fields, how often, when last. Never a value. Always on (it only
    holds what the plugin's own page *Interfaces* shows), unlike the traffic view, which needs debug."""
    if not addon_id:
        return
    old = conn.execute(
        "SELECT fields FROM plugin_usage WHERE vehicle_id = ? AND addon_id = ? AND method = ? AND endpoint = ?",
        (vehicle_id, addon_id, method, endpoint),
    ).fetchone()
    names = list(
        dict.fromkeys([*(old["fields"].split(", ") if old and old["fields"] else []), *[x.split("[")[0] for x in fields.split(", ") if x]])
    )
    conn.execute(
        "INSERT INTO plugin_usage(vehicle_id, addon_id, method, endpoint, fields, hits, last_seen) VALUES(?,?,?,?,?,1,?) "
        "ON CONFLICT(vehicle_id, addon_id, method, endpoint) DO UPDATE SET fields = excluded.fields, hits = hits + 1, last_seen = excluded.last_seen",
        (vehicle_id, addon_id, method, endpoint[:200], ", ".join(names)[:400], _now()),
    )


def delete_logs(conn: sqlite3.Connection, vehicle_id: int, addon_id: str, name: str = "") -> None:
    """All log lines of a plugin (also older ones written before logs were tied to a plugin, found by its name)."""
    conn.execute(
        "DELETE FROM vehicle_logs WHERE vehicle_id = ? AND (addon_id = ? OR (addon_id IS NULL AND source = ?))",
        (vehicle_id, addon_id, name[:40]),
    )
    for table in ("vehicle_traffic", "plugin_usage"):  # what was watched and what it used goes with it
        conn.execute(f"DELETE FROM {table} WHERE vehicle_id = ? AND addon_id = ?", (vehicle_id, addon_id))
    from . import linkmap

    linkmap.forget(conn, vehicle_id, addon_id)  # and what the connection map showed of it


def snapshot(conn: sqlite3.Connection, vehicle_id: int) -> dict:
    """What Car Assistant currently knows, in the shape of the POST body, plus when each value arrived (``updated``)."""
    rows = {
        r["key"]: (r["value"], r["updated"])
        for r in conn.execute("SELECT key, value, updated FROM live WHERE vehicle_id = ?", (vehicle_id,))
    }
    data: dict = {}
    updated: dict[str, str] = {}
    last = conn.execute(
        "SELECT odometer_km, date, source FROM odometer WHERE vehicle_id = ? ORDER BY odometer_km DESC, id DESC LIMIT 1", (vehicle_id,)
    ).fetchone()
    if last:
        data["odometer_km"] = last["odometer_km"]
    for api_key, (live_key, _lo, _hi) in NUMBERS.items():
        if live_key in rows and rows[live_key][0] is not None:
            data[api_key], updated[api_key] = float(rows[live_key][0]), rows[live_key][1]
    for key in BOOLS:
        if rows.get(key, (None,))[0] in ("yes", "no"):
            data[key], updated[key] = rows[key][0] == "yes", rows[key][1]
    tyres = status.parse_numbers(rows["tyre_pressure_bar"][0]) if "tyre_pressure_bar" in rows else {}
    if tyres:
        data["tyre_pressure_bar"], updated["tyre_pressure_bar"] = tyres, rows["tyre_pressure_bar"][1]
    if "position" in rows and rows["position"][0]:
        lat, lon = rows["position"][0].split(",")
        data["position"], updated["position"] = {"lat": float(lat), "lon": float(lon)}, rows["position"][1]
    if rows.get("ignition", (None,))[0] in ("on", "off"):
        data["ignition"], updated["ignition"] = rows["ignition"][0] == "on", rows["ignition"][1]
    if rows.get("locked", (None,))[0] in ("locked", "unlocked"):
        data["locked"], updated["locked"] = rows["locked"][0] == "locked", rows["locked"][1]
    for key in ("doors", "windows", "lights"):
        flags = status.parse_flags(rows[key][0]) if key in rows else {}
        if flags:
            data[key], updated[key] = flags, rows[key][1]
    warnings = status.parse_warnings(rows["warnings"][0]) if "warnings" in rows else {}
    if warnings:
        data["warnings"], updated["warnings"] = warnings, rows["warnings"][1]
    return {"data": data, "updated": updated}


def ingest(conn: sqlite3.Connection, vehicle_id: int, data: dict, source: str, caller: int | None = None) -> dict[str, str]:
    """Validate and store pushed values. Returns what happened per key (stored / ignored). ``caller`` = the install (its number) that sends: a field
    that ANOTHER plugin has taken for this car (claims.py) is not stored and answered ``ignored (taken by <plugin>)``."""
    if not isinstance(data, dict):
        raise ApiError("invalid_body", "The body must be a JSON object.", 422)
    unknown = sorted(set(data) - KNOWN)
    if unknown:
        raise ApiError("unknown_field", f"Unknown field(s): {', '.join(unknown)}. Allowed: {', '.join(sorted(KNOWN))}.", 422)
    from . import claims

    data, taken = claims.guard(conn, vehicle_id, data, caller)
    if taken:
        result = _ingest(conn, vehicle_id, data, source) if data else {}
        return {**result, **{field: f"ignored (taken by {who})" for field, who in taken.items()}}
    return _ingest(conn, vehicle_id, data, source)


def _ingest(conn: sqlite3.Connection, vehicle_id: int, data: dict, source: str) -> dict[str, str]:
    at = None
    if data.get("measured_at") not in (None, ""):
        at = moment(data["measured_at"])
        if at is None:
            raise ApiError("invalid_value", "'measured_at' must be a time like 2026-11-20T08:15:00Z (or seconds since 1970).", 422)
    result: dict[str, str] = {}
    vin = None
    if "vin" in data:
        try:
            vin = vin_info.clean(data["vin"]) if isinstance(data["vin"], str) else None
        except ValueError:
            vin = None
        if vin is None:
            raise ApiError("invalid_value", "'vin' must be text with letters and digits only (5-20 characters).", 422)
    km = _num(data, "odometer_km", 1, MAX_ODOMETER_KM)
    numbers = {key: _num(data, key, lo, hi) for key, (_live, lo, hi) in NUMBERS.items()}
    bools = {key: data.get(key) for key in BOOLS}
    for key, value in bools.items():
        if value is not None and not isinstance(value, bool):
            raise ApiError("invalid_value", f"'{key}' must be true or false.", 422)
    tyres = _merged_tyres(conn, vehicle_id, data)
    ign = data.get("ignition")
    if ign is not None and not isinstance(ign, bool):
        raise ApiError("invalid_value", "'ignition' must be true or false.", 422)
    locked = data.get("locked")
    if locked is not None and not isinstance(locked, bool):
        raise ApiError("invalid_value", "'locked' must be true (locked) or false (unlocked).", 422)
    doors = _merged_closures(conn, vehicle_id, data, "doors")
    windows = _merged_closures(conn, vehicle_id, data, "windows")
    lights = _merged_closures(conn, vehicle_id, data, "lights")
    warnings = _merged_warnings(conn, vehicle_id, data)
    pos = data.get("position")
    lat = lon = None
    if pos is not None:
        if not isinstance(pos, dict):
            raise ApiError("invalid_value", '\'position\' must be an object {"lat": .., "lon": ..}.', 422)
        lat, lon = _num(pos, "lat", -90, 90), _num(pos, "lon", -180, 180)
        if lat is None or lon is None:
            raise ApiError("invalid_value", "'position' needs lat and lon.", 422)
        names = {}
        for field in ("street", "place"):  # optional: the car names the spot itself (street with number / town)
            text = pos.get(field)
            if text is not None and not isinstance(text, str):
                raise ApiError("invalid_value", f"'position.{field}' must be text.", 422)
            names[field] = " ".join((text or "").split())[:120]
    if vin is not None:  # the VIN is typed in by a person; the car only has to match it (like a key)
        row = conn.execute("SELECT vin FROM vehicles WHERE id = ?", (vehicle_id,)).fetchone()
        if not row["vin"]:
            result["vin"] = "not checked (no VIN is set in the vehicle data - type it in there to switch the check on)"
        elif row["vin"] == vin:
            conn.execute("UPDATE vehicles SET vin_verified = 1 WHERE id = ?", (vehicle_id,))
            result["vin"] = "matches"
        else:
            raise ApiError("vin_mismatch", "The VIN does not match the one of this vehicle; nothing was stored.", 409)
    if km is not None:
        known = summary.current_odometer(conn, vehicle_id)
        if known is None or round(km) > known:
            summary.record_odometer(conn, vehicle_id, round(km), f"api:{source}"[:60])
            result["odometer_km"] = "stored"
        else:
            result["odometer_km"] = "ignored (not higher than the known reading)"
    for key, value in numbers.items():
        if value is not None:
            _store(conn, vehicle_id, NUMBERS[key][0], f"{value:.0f}" if key in ("fuel_level_pct", "range_km") else f"{value:g}", at)
            result[key] = "stored"
    for key, value in bools.items():
        if value is not None:
            _store(conn, vehicle_id, key, "yes" if value else "no", at)
            result[key] = "stored"
    if tyres is not None:
        _store(conn, vehicle_id, "tyre_pressure_bar", json.dumps(tyres, sort_keys=True), at)
        result["tyre_pressure_bar"] = "stored"
    if lat is not None:
        _store(conn, vehicle_id, "position", f"{lat:.6f},{lon:.6f}", at)
        result["position"] = "stored"
        if names["street"] or names["place"]:
            from . import places

            places.set_given(conn, lat, lon, names["place"], names["street"])
            result["position_names"] = "stored"
    if ign is not None:
        _store(conn, vehicle_id, "ignition", "on" if ign else "off", at)
        result["ignition"] = "stored"
    if locked is not None:
        _store(conn, vehicle_id, "locked", "locked" if locked else "unlocked", at)
        result["locked"] = "stored"
    for key, merged in (("doors", doors), ("windows", windows), ("lights", lights)):
        if merged is not None:
            _store(conn, vehicle_id, key, json.dumps(merged, sort_keys=True), at)
            result[key] = "stored"
    if warnings is not None:
        _store(conn, vehicle_id, "warnings", json.dumps(warnings, sort_keys=True), at)
        result["warnings"] = "stored"
    from . import trips

    trips.from_track(conn, vehicle_id)  # also closes a drive when the plugin only reports now and then
    return result
