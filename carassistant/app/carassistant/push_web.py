"""Routes for web push: the service worker, the server key, adding and removing a device. See push.py."""

from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from . import auth_web, config, db, i18n, push, web
from .web import app, go

SW = Path(__file__).parent / "static" / "sw.js"


@app.get("/sw.js")
def service_worker():
    """The service worker has to sit at the root of the site to reach every page; it holds no secrets."""
    return Response(
        SW.read_text(encoding="utf-8"), media_type="text/javascript", headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"}
    )


def _me(request: Request, conn):
    """The signed-in person - only over the port (https); the Home Assistant panel cannot receive web push."""
    if not auth_web._is_external(request):
        return None
    return auth_web._acting_user(request, conn)


@app.get("/push/key")
def push_key(request: Request):
    with db.tx() as conn:
        if _me(request, conn) is None:
            return JSONResponse({"ok": False, "error": i18n.translator(config.language())("push.need_port")}, status_code=400)
        return JSONResponse({"ok": True, "key": push.public_key(conn)})


def _car_of(conn, request: Request, raw) -> int | None:
    """The car a device is switched on for: the one the Car tab names, else the one of this car's own web app."""
    if str(raw or "").isdigit():
        row = conn.execute("SELECT id FROM vehicles WHERE id = ? AND archived = 0", (int(raw),)).fetchone()
        if row:
            return row["id"]
    mine = web._app_car(request, conn)
    return mine["id"] if mine else None


@app.post("/push/subscribe")
async def push_subscribe(request: Request):
    t = i18n.translator(config.language())
    try:
        body = await request.json()
        with db.tx() as conn:
            me = _me(request, conn)
            if me is None:
                return JSONResponse({"ok": False, "error": t("push.need_port")}, status_code=400)
            push.add_device(
                conn, me["id"], body.get("sub") or {}, str(body.get("label") or ""), _car_of(conn, request, body.get("vehicle"))
            )
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": t("push.too_many") if str(exc) == "limit" else t("push.bad")}, status_code=400)
    return JSONResponse({"ok": True})


@app.post("/push/status")
async def push_status(request: Request):
    """Is this device (its subscription) switched on for this car? The Car tab asks it to show the right button."""
    body = await request.json()
    with db.tx() as conn:
        me = _me(request, conn)
        car = _car_of(conn, request, body.get("vehicle"))
        on = bool(me is not None and car and push.covers(conn, me["id"], str(body.get("endpoint") or ""), car))
    return JSONResponse({"ok": True, "on": on})


@app.post("/push/unsubscribe")
async def push_unsubscribe(request: Request):
    """Switch a device off: for one car (``vehicle``) - it is removed when no car is left - or completely."""
    body = await request.json()
    left = 0
    with db.tx() as conn:
        me = _me(request, conn)
        if me is not None:
            endpoint = str(body.get("endpoint") or "")
            car = _car_of(conn, request, body.get("vehicle")) if body.get("vehicle") else None
            if car:
                left = push.drop_car(conn, me["id"], endpoint, car)
            else:
                push.remove_device(conn, me["id"], endpoint=endpoint)
    return JSONResponse({"ok": True, "remaining": left})


@app.post("/settings/push/{device_id}/delete")
def push_delete(request: Request, device_id: int):
    with db.tx() as conn:
        me = auth_web._acting_user(request, conn)
        if me is not None:
            push.remove_device(conn, me["id"], device_id=device_id)
    return go(request, "/settings/user#notifications", "saved")
