"""Routes: arrange the Home widgets of one vehicle (order, size, visibility)."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from . import db, events, widgets
from .web import app, go, render, vehicle_ctx, vehicle_or_404


@app.get("/v/{vid}/widgets")
def widgets_page(request: Request, vid: int):
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        return render(
            request, "widgets_edit.html", **vehicle_ctx(conn, vehicle, "overview"), hide_hero=True, items=widgets.layout(conn, vid)
        )


@app.post("/v/{vid}/widgets")
async def widgets_save(request: Request, vid: int):
    form = await request.form()
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        slug = vehicle["slug"]
        if form.get("reset"):
            widgets.reset(conn, vid)
            target = "widgets"
        else:
            order = [k for k in form.getlist("k") if isinstance(k, str)]
            move = str(form.get("move") or "")  # "<key>:up" / "<key>:down" (a click on an arrow saves and stays on the page)
            if ":" in move:
                key, way = move.split(":", 1)
                if key in order:
                    i = order.index(key)
                    j = i - 1 if way == "up" else i + 1
                    if 0 <= j < len(order):
                        order[i], order[j] = order[j], order[i]
            sizes = {k: str(form.get(f"size_{k}") or "") for k in order}
            by_key = {w.key: w for w in widgets.registry(conn, vid)}
            options = {k: {key: str(form.get(f"opt_{k}_{key}") or "") for key, _choices in by_key[k].options} for k in order if k in by_key}
            widgets.save(conn, vid, order, sizes, {k for k in order if form.get(f"on_{k}")}, options)
            target = "widgets" if move else ""
    events.changed()
    if form.get("ajax"):  # the live editing on Home saves in the background
        return JSONResponse({"ok": True})
    return go(request, f"/v/{slug}/{target}".rstrip("/"), "saved")
