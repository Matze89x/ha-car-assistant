"""Routes of the MCP access: the endpoint ``POST /mcp`` and the settings (level, keys). See mcp.py and docs/mcp.md."""

from __future__ import annotations

import asyncio
import json

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from . import config, db, mcp
from .web import app, form_dict, go, render

SAFE = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"}


def _json(body, status: int = 200, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(body, status_code=status, headers={**SAFE, **(headers or {})})


def _gone() -> Response:
    """Switched off or not possible: the endpoint does not exist (nothing is revealed, not even that MCP is there)."""
    return Response("Not found.", status_code=404, headers=SAFE)


@app.get("/.well-known/{rest:path}")
def well_known(rest: str):
    """An MCP client first looks for an OAuth server here; this app uses a fixed access key, so the honest answer is a plain 404 (not the sign-in page)."""
    return JSONResponse({"error": "not_found"}, status_code=404, headers=SAFE)


@app.get("/mcp")
def mcp_get():
    with db.tx() as conn:
        if mcp.active_level(conn) == "off":
            return _gone()
    return Response("This endpoint only takes POST requests (MCP over HTTP).", status_code=405, headers={**SAFE, "Allow": "POST"})


@app.post("/mcp")
async def mcp_endpoint(request: Request):
    return await _serve(request, None)


@app.post("/mcp/{key}")
async def mcp_endpoint_with_key(request: Request, key: str):
    """The same endpoint with the key in the address - only for connector dialogs that have no field for a header (the key then shows in the logs
    of proxies on the way, so the key page names this as the second choice)."""
    with db.tx() as conn:
        if not mcp.path_key_allowed(conn):  # switched off: the key may only come in the header - this address does not exist
            return _gone()
    return await _serve(request, key)


async def _serve(request: Request, path_key: str | None):
    address = request.client.host if request.client else ""
    with db.tx() as conn:
        if mcp.active_level(conn) == "off" or request.headers.get("X-Ingress-Path"):  # the Home Assistant panel is never a way in
            return _gone()
    if mcp.blocked(address):
        return _json({"error": "too_many_attempts"}, 429, {"Retry-After": str(mcp.BLOCK_SECONDS)})
    if not mcp.origin_allowed(request.headers.get("Origin")):
        return _json({"error": "forbidden_origin"}, 403)
    auth = request.headers.get("Authorization", "")
    token = auth[7:].strip() if auth[:7].lower() == "bearer " else path_key
    with db.tx() as conn:
        key = mcp.verify(conn, token)
    if key is None:
        mcp.failed(address)
        await asyncio.sleep(0.5)  # slow down guessing
        return _json(
            {"error": "unauthorized", "message": "Missing or invalid access key (Authorization: Bearer cam_...)."},
            401,
            {"WWW-Authenticate": "Bearer"},
        )
    if not mcp.within_rate(key["id"]):
        return _json({"error": "rate_limited"}, 429, {"Retry-After": "30"})
    raw = await request.body()
    if len(raw) > mcp.MAX_BODY:
        return _json({"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Request too large"}}, 413)
    try:
        message = json.loads(raw)
    except ValueError:
        return _json({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}, 400)
    with db.tx() as conn:
        if isinstance(message, list):  # a batch
            answers = [a for a in (mcp.handle(conn, key, m) for m in message[:20]) if a is not None]
            return _json(answers) if answers else Response(status_code=202, headers=SAFE)
        answer = mcp.handle(conn, key, message)
    return _json(answer) if answer is not None else Response(status_code=202, headers=SAFE)


# ------------------------------------------------------------------ settings (administrators only, see auth_web.admin_only)


@app.post("/settings/mcp/level")
async def mcp_level(request: Request):
    form = await form_dict(request)
    try:
        with db.tx() as conn:
            mcp.set_level(conn, str(form.get("level", "off")))
            mcp.set_path_key(conn, bool(form.get("path_key")))
    except ValueError as exc:
        return go(request, "/settings/system#mcp", str(exc))
    return go(request, "/settings/system#mcp", "saved")


@app.post("/settings/mcp/key")
async def mcp_key_make(request: Request):
    """Make the access key - or renew it when there is one (the old one stops working)."""
    try:
        with db.tx() as conn:
            if mcp.level(conn) == "off" or mcp.missing(conn):
                raise ValueError("mcp.need_on")
            token = mcp.renew_key(conn)
    except ValueError as exc:
        return go(request, "/settings/system#mcp", str(exc))
    with db.tx() as conn:
        path_key = mcp.path_key_allowed(conn)
    return render(request, "mcp_key.html", token=token, url=config.external_url() + "/mcp", path_key=path_key, tab=None, v=None)


@app.post("/settings/mcp/key/delete")
def mcp_key_delete(request: Request):
    with db.tx() as conn:
        mcp.delete_keys(conn)
    return go(request, "/settings/system#mcp", "deleted")
