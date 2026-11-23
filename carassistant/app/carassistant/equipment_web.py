"""Routes of the equipment list on the vehicle passport: add, edit and delete a feature, put the categories in order."""

from __future__ import annotations

from . import db, equipment, events
from .web import Request, app, form_dict, go, vehicle_or_404


def _back(request: Request, conn, vid: int, msg: str = "saved"):
    return go(request, f"/v/{vehicle_or_404(conn, vid)['slug']}/edit#equipment", msg)


@app.post("/v/{vid}/equipment/new")
async def equipment_new(request: Request, vid: int):
    form = await form_dict(request)
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        ok = equipment.add_item(
            conn, vid, form.get("category", ""), form.get("title", ""), form.get("status", "series"), form.get("code", "")
        )
        back = _back(request, conn, vid, "saved" if ok else "err.required")
    events.changed()
    return back


@app.post("/v/{vid}/equipment/item/{item_id}")
async def equipment_item(request: Request, vid: int, item_id: int):
    form = await form_dict(request)
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        equipment.save_item(conn, vid, item_id, form)
        back = _back(request, conn, vid)
    events.changed()
    return back
