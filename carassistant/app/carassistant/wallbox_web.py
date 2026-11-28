"""The buttons of the wallbox card (wallbox_control.py): pause, resume, start, acknowledge a fault, the current limit, the mode. A person presses one; the
request says what to do and with which value - never which entity or which service. Only for people who may manage the app (the entities of Home Assistant
are the system's, not the car's)."""

from __future__ import annotations

from fastapi import Request

from . import db, ha, wallbox_control
from .connectors_web import _may_manage
from .web import app, form_dict, go, vehicle_or_404


@app.post("/v/{vid}/wallbox/{action}")
async def wallbox_command(request: Request, vid: int, action: str):
    back = f"/v/{vid}/e/fuel#wb"
    if not _may_manage(request):
        return go(request, back, "acct.need_admin")
    form = await form_dict(request)
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        try:
            message = wallbox_control.do(conn, vid, action, form, ha.all_states())
        except wallbox_control.ControlError as exc:
            message = str(exc)
    return go(request, back, message)
