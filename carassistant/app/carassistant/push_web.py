"""Routes for web push: the service worker, the server key, adding and removing a device. See push.py."""

from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from . import auth_web, config, db, i18n, push
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


@app.post("/push/subscribe")
async def push_subscribe(request: Request):
    t = i18n.translator(config.language())
    try:
        body = await request.json()
        with db.tx() as conn:
            me = _me(request, conn)
            if me is None:
                return JSONResponse({"ok": False, "error": t("push.need_port")}, status_code=400)
            push.add_device(conn, me["id"], body.get("sub") or {}, str(body.get("label") or ""))
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": t("push.too_many") if str(exc) == "limit" else t("push.bad")}, status_code=400)
    return JSONResponse({"ok": True})


@app.post("/push/status")
async def push_status(request: Request):
    """Is this device (its subscription) registered for the signed-in person? The notification card asks it to show the right button."""
    body = await request.json()
    with db.tx() as conn:
        me = _me(request, conn)
        on = bool(
            me is not None
            and conn.execute(
                "SELECT 1 FROM push_devices WHERE user_id = ? AND endpoint = ?", (me["id"], str(body.get("endpoint") or ""))
            ).fetchone()
        )
    return JSONResponse({"ok": True, "on": on})


@app.post("/push/unsubscribe")
async def push_unsubscribe(request: Request):
    """Switch this device off completely."""
    body = await request.json()
    with db.tx() as conn:
        me = _me(request, conn)
        if me is not None:
            push.remove_device(conn, me["id"], endpoint=str(body.get("endpoint") or ""))
    return JSONResponse({"ok": True, "remaining": 0})


@app.post("/settings/push/{device_id}/delete")
def push_delete(request: Request, device_id: int):
    with db.tx() as conn:
        me = auth_web._acting_user(request, conn)
        if me is not None:
            push.remove_device(conn, me["id"], device_id=device_id)
    return go(request, "/settings/user#notifications", "saved")
