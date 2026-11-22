"""Routes of the Plugin API (``/api/v1``) and the token management on the Integrations page."""

from __future__ import annotations

import json
import time
import zlib

from fastapi import Request
from fastapi.responses import JSONResponse

from . import __version__, auth_web, config, connectors, db, deprecations, events, summary
from .web import app, form_dict, go, render

MAX_BODY = 20_000
MAX_LOG_BODY = 60_000
MAX_BIG_BODY = 400_000  # tracks, signals, page entries (after unpacking)


class _TooLarge(Exception):
    pass


async def _body(request: Request, limit: int) -> bytes:
    """The request body; ``Content-Encoding: gzip`` is unpacked (the limit counts the unpacked size, so a small file cannot blow up)."""
    raw = await request.body()
    if request.headers.get("content-encoding", "").lower() == "gzip":
        unpacker = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            raw = unpacker.decompress(raw, limit + 1)
        except zlib.error as exc:
            raise ValueError("bad gzip") from exc
        if unpacker.unconsumed_tail:
            raise _TooLarge
    if len(raw) > limit:
        raise _TooLarge
    return raw


def _describe(data) -> str:
    """What a delivery contained, for the traffic view: the names of the fields and how many items - never a value."""
    if not isinstance(data, dict):
        return ""
    parts = []
    for key, value in list(data.items())[:12]:
        parts.append(f"{key}[{len(value)}]" if isinstance(value, list) else key)
    return ", ".join(parts)


@app.middleware("http")
async def watch_connector_traffic(request: Request, call_next):
    """While debug is on for a car, note every call of a plugin to its Plugin API (address, status, size, time, field names)."""
    path = request.url.path
    if not path.startswith("/api/v1/vehicles/"):
        return await call_next(request)
    started = time.monotonic()
    response = await call_next(request)
    try:
        vehicle_id = int(path.split("/")[4])
        token = getattr(request.state, "api_token", None)
        detail = getattr(request.state, "traffic_detail", "")
        with db.tx() as conn:
            addon_id = connectors.addon_for_token(conn, token["id"]) if token else None
            if response.status_code < 400:  # the page *Interfaces* of the plugin shows what it really used (names only)
                parts = path.split("/")
                connectors.note_usage(conn, vehicle_id, addon_id, request.method, "/".join(["", *parts[1:4], "{id}", *parts[5:]]), detail)
            if connectors.debug_enabled(conn, vehicle_id, addon_id):
                connectors.record_traffic(
                    conn,
                    vehicle_id,
                    addon_id,
                    "api",
                    request.method,
                    path,
                    response.status_code,
                    int(request.headers.get("content-length") or 0),
                    round((time.monotonic() - started) * 1000),
                    detail,
                )
    except (ValueError, IndexError, KeyError):
        pass
    parts = path.split("/")
    for name, value in deprecations.headers(
        deprecations.for_endpoint(request.method, "/".join(["", *parts[1:4], "{id}", *parts[5:]]))
    ).items():
        response.headers[name] = value  # an announced change: the plugin author sees it in the first test run
    return response


async def _json(request: Request, limit: int):
    """(data, None) or (None, error response)."""
    try:
        raw = await _body(request, limit)
    except _TooLarge:
        return None, _err("too_large", "Body too large.", 413)
    except ValueError:
        return None, _err("invalid_gzip", "The body is not valid gzip.", 400)
    try:
        data = json.loads(raw or b"{}")
    except ValueError:
        return None, _err("invalid_json", "The body is not valid JSON.", 400)
    request.state.traffic_detail = _describe(data)
    return data, None


def _err(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": code, "message": message}, status_code=status)


def _allowed(request: Request, vehicle_id: int) -> bool:
    scope = request.state.api_token["vehicle_id"]
    return scope is None or scope == vehicle_id


@app.get("/api/v1")
def api_root(request: Request):
    return {
        "name": "Car Assistant",
        "version": __version__,
        "api": 1,
        "connector": request.state.api_token["name"],
        "fields": sorted(connectors.KNOWN),
        "features": ["measured_at", "plugin-settings"],  # what a plugin can check before it uses it
    }


@app.get("/api/v1/vehicles")
def api_vehicles(request: Request):
    with db.tx() as conn:
        rows = conn.execute("SELECT id, name, plate FROM vehicles WHERE archived = 0 ORDER BY id").fetchall()
        out = [
            {"id": r["id"], "name": r["name"], "plate": r["plate"], "odometer_km": summary.current_odometer(conn, r["id"])}
            for r in rows
            if _allowed(request, r["id"])
        ]
    return out


@app.get("/api/v1/vehicles/{vehicle_id}/modules/{addon_id}/{page_id}")
def api_module_rows(request: Request, vehicle_id: int, addon_id: str, page_id: str):
    """The entries of a page of an installed integration of this car (e.g. the stations of the web radio), in their order, as plain values."""
    if not _allowed(request, vehicle_id):
        return _err("forbidden", "This token is not allowed for this vehicle.", 403)
    from . import pagemods

    with db.tx() as conn:
        found = pagemods.module(conn, vehicle_id, addon_id)
        page = pagemods.page_of(found, page_id) if found else None
        if page is None:
            return _err("not_found", "No such page (is the integration installed and running?).", 404)
        hidden = pagemods.secret_keys(page)  # access codes never leave through the interface
        keys = [f["key"] for f in page["fields"] if f["key"] not in hidden]
        return {
            "page": page["id"],
            "rows": [
                {"id": r["id"], **{k: r["data"].get(k, "") for k in keys}}
                for r in pagemods.rows(conn, vehicle_id, addon_id, page_id, page.get("order"))
            ],
        }


_setting_calls: dict[int, list[float]] = {}
SETTING_CALLS_PER_MINUTE = 30


@app.get("/api/v1/vehicles/{vehicle_id}/plugin-settings")
def api_plugin_settings(request: Request, vehicle_id: int):
    """The plugin's own settings for this car, as its service reads them: typed values, passwords never (``***`` when set), and which keys it may change."""
    from . import addons

    if not _allowed(request, vehicle_id):
        return _err("forbidden", "This token is not allowed for this vehicle.", 403)
    with db.tx() as conn:
        addon = next((a for a in addons.list_for(conn, vehicle_id) if a["token_id"] == request.state.api_token["id"]), None)
        if addon is None:
            return _err("no_plugin", "This token does not belong to a plugin of this vehicle.", 404)
        return {"ok": True, "settings": addons.service_settings(addon), "writable": sorted(addons.writable_keys(addon))}


@app.put("/api/v1/vehicles/{vehicle_id}/plugin-settings")
async def api_plugin_settings_put(request: Request, vehicle_id: int):
    """The service changes some of ITS OWN settings: ``{"values": {"key": value}}``. Only keys the package marks ``service_writable`` (the administrator
    approved that list) and ``value`` fields; checked like the form; at most 30 calls a minute; the change is noted in the log (names, never values)."""
    from . import addons

    if not _allowed(request, vehicle_id):
        return _err("forbidden", "This token is not allowed for this vehicle.", 403)
    data, failed = await _json(request, MAX_BODY)
    if failed:
        return failed
    token_id = request.state.api_token["id"]
    now = time.monotonic()
    recent = [t for t in _setting_calls.get(token_id, []) if now - t < 60]
    if len(recent) >= SETTING_CALLS_PER_MINUTE:
        _setting_calls[token_id] = recent
        return _err("rate_limited", "Too many calls; at most 30 a minute.", 429)
    _setting_calls[token_id] = [*recent, now]
    with db.tx() as conn:
        addon = next((a for a in addons.list_for(conn, vehicle_id) if a["token_id"] == token_id), None)
        if addon is None:
            return _err("no_plugin", "This token does not belong to a plugin of this vehicle.", 404)
        if not isinstance(data, dict) or not isinstance(data.get("values"), dict):
            return _err("invalid_body", 'The body must be an object like {"values": {"key": value}}.', 422)
        try:
            keys = addons.service_set(conn, addon, data["values"])
        except addons.SettingError as exc:
            status = 403 if exc.code == "not_writable" else 422
            body = {"error": exc.code, "message": str(exc)}
            if exc.fields:
                body["fields"] = exc.fields
            return JSONResponse(body, status_code=status)
        connectors.write_logs(
            conn, vehicle_id, addon["addon_id"], [(connectors._now(), "info", "app", f"settings changed by the plugin: {', '.join(keys)}")]
        )
    events.changed()
    return {"ok": True, "changed": keys}


@app.post("/api/v1/vehicles/{vehicle_id}/data")
async def api_data(request: Request, vehicle_id: int):
    if not _allowed(request, vehicle_id):
        return _err("forbidden", "This token is not allowed for this vehicle.", 403)
    data, failed = await _json(request, MAX_BODY)
    if failed:
        return failed
    with db.tx() as conn:
        if conn.execute("SELECT 1 FROM vehicles WHERE id = ? AND archived = 0", (vehicle_id,)).fetchone() is None:
            return _err("not_found", "Vehicle not found.", 404)
        try:
            result = connectors.ingest(conn, vehicle_id, data, request.state.api_token["name"])
        except connectors.ApiError as exc:
            return _err(exc.code, exc.message, exc.status)
        control = connectors.control(conn, vehicle_id, connectors.addon_for_token(conn, request.state.api_token["id"]))
    events.changed()
    body = {"ok": True, "result": result, "control": control}  # the answer tells the plugin what the dashboard asks of it
    old = deprecations.used_fields(data)
    if old:  # fields announced as deprecated: named in the answer and in the headers, they still work
        body["deprecated"] = old
        return JSONResponse(body, headers=deprecations.headers(list(deprecations.FIELDS[o["field"]] for o in old)))
    return body


@app.get("/api/v1/vehicles/{vehicle_id}/control")
def api_control(request: Request, vehicle_id: int):
    """What the dashboard asks this vehicle to do (first switch: ``debug``). Read-only for the plugin."""
    if not _allowed(request, vehicle_id):
        return _err("forbidden", "This token is not allowed for this vehicle.", 403)
    with db.tx() as conn:
        if conn.execute("SELECT 1 FROM vehicles WHERE id = ? AND archived = 0", (vehicle_id,)).fetchone() is None:
            return _err("not_found", "Vehicle not found.", 404)
        return {
            "ok": True,
            "control": connectors.control(conn, vehicle_id, connectors.addon_for_token(conn, request.state.api_token["id"])),
        }


@app.post("/api/v1/vehicles/{vehicle_id}/logs")
async def api_logs(request: Request, vehicle_id: int):
    """Debug lines from the vehicle. Only accepted while debug is switched on for it (409 ``debug_off`` otherwise)."""
    if not _allowed(request, vehicle_id):
        return _err("forbidden", "This token is not allowed for this vehicle.", 403)
    data, failed = await _json(request, MAX_LOG_BODY)
    if failed:
        return failed
    with db.tx() as conn:
        if conn.execute("SELECT 1 FROM vehicles WHERE id = ? AND archived = 0", (vehicle_id,)).fetchone() is None:
            return _err("not_found", "Vehicle not found.", 404)
        try:
            stored = connectors.ingest_logs(conn, vehicle_id, data, request.state.api_token["name"], request.state.api_token["id"])
        except connectors.ApiError as exc:
            return _err(exc.code, exc.message, exc.status)
    return {"ok": True, "stored": stored}


@app.get("/api/v1/vehicles/{vehicle_id}/data")
def api_data_read(request: Request, vehicle_id: int):
    """What Car Assistant currently knows (for testing a connector); same shape as the POST body plus ``updated``."""
    if not _allowed(request, vehicle_id):
        return _err("forbidden", "This token is not allowed for this vehicle.", 403)
    with db.tx() as conn:
        if conn.execute("SELECT 1 FROM vehicles WHERE id = ? AND archived = 0", (vehicle_id,)).fetchone() is None:
            return _err("not_found", "Vehicle not found.", 404)
        return {"ok": True, **connectors.snapshot(conn, vehicle_id)}


def _vehicle_gate(request: Request, vehicle_id: int, conn):
    """An error response when this token may not use the vehicle or it does not exist, else None."""
    if not _allowed(request, vehicle_id):
        return _err("forbidden", "This token is not allowed for this vehicle.", 403)
    if conn.execute("SELECT 1 FROM vehicles WHERE id = ? AND archived = 0", (vehicle_id,)).fetchone() is None:
        return _err("not_found", "Vehicle not found.", 404)
    return None


@app.post("/api/v1/vehicles/{vehicle_id}/track")
async def api_track(request: Request, vehicle_id: int):
    """Positions of a drive (batches of up to 500 points, gzip allowed)."""
    data, failed = await _json(request, MAX_BIG_BODY)
    if failed:
        return failed
    with db.tx() as conn:
        if (gate := _vehicle_gate(request, vehicle_id, conn)) is not None:
            return gate
        try:
            stored = connectors.ingest_track(conn, vehicle_id, data)
        except connectors.ApiError as exc:
            return _err(exc.code, exc.message, exc.status)
        control = connectors.control(conn, vehicle_id, connectors.addon_for_token(conn, request.state.api_token["id"]))
    events.changed()
    return {"ok": True, "stored": stored, "control": control}


@app.get("/api/v1/vehicles/{vehicle_id}/track")
def api_track_read(request: Request, vehicle_id: int, since: str | None = None, limit: int = 200):
    with db.tx() as conn:
        if (gate := _vehicle_gate(request, vehicle_id, conn)) is not None:
            return gate
        try:
            return {"ok": True, "points": connectors.read_track(conn, vehicle_id, since, limit)}
        except connectors.ApiError as exc:
            return _err(exc.code, exc.message, exc.status)


@app.post("/api/v1/vehicles/{vehicle_id}/events")
async def api_events(request: Request, vehicle_id: int):
    """Events with a time and maybe a place (traffic signs read, town borders crossed, ...); the newest 2000 per car are kept."""
    data, failed = await _json(request, MAX_BIG_BODY)
    if failed:
        return failed
    with db.tx() as conn:
        if (gate := _vehicle_gate(request, vehicle_id, conn)) is not None:
            return gate
        try:
            stored = connectors.ingest_events(conn, vehicle_id, data)
        except connectors.ApiError as exc:
            return _err(exc.code, exc.message, exc.status)
        control = connectors.control(conn, vehicle_id, connectors.addon_for_token(conn, request.state.api_token["id"]))
    return {"ok": True, "stored": stored, "control": control}


@app.get("/api/v1/vehicles/{vehicle_id}/events")
def api_events_read(request: Request, vehicle_id: int, since: str | None = None, type: str | None = None, limit: int = 200):
    with db.tx() as conn:
        if (gate := _vehicle_gate(request, vehicle_id, conn)) is not None:
            return gate
        try:
            return {"ok": True, "events": connectors.read_events(conn, vehicle_id, since, type, limit)}
        except connectors.ApiError as exc:
            return _err(exc.code, exc.message, exc.status)


@app.post("/api/v1/vehicles/{vehicle_id}/trip-summary")
async def api_trip_summary(request: Request, vehicle_id: int):
    """The values of the car's own trip computer for the drive that just ended (consumption, average speed, duration)."""
    data, failed = await _json(request, MAX_BODY)
    if failed:
        return failed
    with db.tx() as conn:
        if (gate := _vehicle_gate(request, vehicle_id, conn)) is not None:
            return gate
        try:
            result = connectors.ingest_trip_summary(conn, vehicle_id, data)
        except connectors.ApiError as exc:
            return _err(exc.code, exc.message, exc.status)
        control = connectors.control(conn, vehicle_id, connectors.addon_for_token(conn, request.state.api_token["id"]))
    events.changed()
    return {"ok": True, "result": result, "control": control}


@app.post("/api/v1/vehicles/{vehicle_id}/refuel")
async def api_refuel(request: Request, vehicle_id: int):
    """A refuel the car noticed. Added to the fuel log, marked with the plugin; duplicates for the same day and mileage are ignored."""
    data, failed = await _json(request, MAX_BODY)
    if failed:
        return failed
    with db.tx() as conn:
        if (gate := _vehicle_gate(request, vehicle_id, conn)) is not None:
            return gate
        try:
            result = connectors.ingest_refuel(conn, vehicle_id, data, request.state.api_token["name"])
        except connectors.ApiError as exc:
            return _err(exc.code, exc.message, exc.status)
        control = connectors.control(conn, vehicle_id, connectors.addon_for_token(conn, request.state.api_token["id"]))
    events.changed()
    return {"ok": True, "result": result, "control": control}


@app.post("/api/v1/vehicles/{vehicle_id}/signals")
async def api_signals(request: Request, vehicle_id: int):
    """Free, car-specific values the app only keeps (and shows on the Debug page)."""
    data, failed = await _json(request, MAX_BIG_BODY)
    if failed:
        return failed
    with db.tx() as conn:
        if (gate := _vehicle_gate(request, vehicle_id, conn)) is not None:
            return gate
        try:
            stored = connectors.ingest_signals(conn, vehicle_id, data)
        except connectors.ApiError as exc:
            return _err(exc.code, exc.message, exc.status)
        control = connectors.control(conn, vehicle_id, connectors.addon_for_token(conn, request.state.api_token["id"]))
    return {"ok": True, "stored": stored, "control": control}


@app.get("/api/v1/vehicles/{vehicle_id}/signals")
def api_signals_read(request: Request, vehicle_id: int):
    with db.tx() as conn:
        if (gate := _vehicle_gate(request, vehicle_id, conn)) is not None:
            return gate
        return {"ok": True, "signals": connectors.read_signals(conn, vehicle_id)}


@app.post("/api/v1/vehicles/{vehicle_id}/modules/{addon_id}/{page_id}")
async def api_module_write(request: Request, vehicle_id: int, addon_id: str, page_id: str):
    """Add, change or delete entries of a page of an installed, running integration (for example the control units of *Coding*).
    Body: ``{"rows": [{"id": 5, "values": {...}} | {"values": {...}}], "delete": [ids]}``. An entry with an ``id`` is changed (fields marked
    *once* keep their first value), one without is added."""
    data, failed = await _json(request, MAX_BIG_BODY)
    if failed:
        return failed
    from . import pagemods

    with db.tx() as conn:
        if (gate := _vehicle_gate(request, vehicle_id, conn)) is not None:
            return gate
        found = pagemods.module(conn, vehicle_id, addon_id)
        page = pagemods.page_of(found, page_id) if found else None
        if page is None:
            return _err("not_found", "No such page (is the integration installed and running?).", 404)
        try:
            result = pagemods.api_write(conn, vehicle_id, addon_id, page, data)
        except pagemods.PageError as exc:
            return _err("invalid_value", f"{exc.args[0]}: {exc.args[1]}" if len(exc.args) > 1 else str(exc.args[0]), 422)
    events.changed()
    return {"ok": True, **result}


# ------------------------------------------------------------------ token management (Integrations page)


def _may_manage(request: Request) -> bool:
    user = getattr(request.state, "user", None)
    return not getattr(request.state, "external", False) or bool(user and user["is_admin"])


@app.post("/integrations/api/tokens")
async def api_token_create(request: Request):
    if not _may_manage(request):
        return go(request, "/integrations", "acct.need_admin")
    form = await form_dict(request)
    vid = form.get("vehicle_id") or ""
    if not vid.isdigit():
        return go(request, "/integrations", "err.choice")
    try:
        with db.tx() as conn:
            token = connectors.create_token(conn, form.get("name", ""), int(vid))
    except connectors.ApiError:
        return go(request, "/integrations", "err.name_required")
    return render(
        request,
        "api_token.html",
        token=token,
        conn_name=form.get("name", "").strip()[:40],
        nav="integrations",
        base_url=config.external_url() or "",
    )


@app.post("/integrations/api/tokens/{token_id}/delete")
async def api_token_delete(request: Request, token_id: int):
    if not _may_manage(request):
        return go(request, "/integrations", "acct.need_admin")
    with db.tx() as conn:
        connectors.delete_token(conn, token_id)
    return go(request, "/integrations", "token_deleted")


_ = auth_web  # keep the import: the account routes must be registered before these
