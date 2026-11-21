"""'Just have a look': a demo car from the standard source, run through a plugin like a real connected car.

Pressing the button asks once (it goes online), then: read the standard source, fetch the demo car's backup, restore it, install the demo plugin from
the source, switch it on - the scenario player (simulator.py) then reports to the car every 5 seconds through the normal interface.
Switch the plugin off (*Start / Stop* on its card) and the car stands still.
"""

from __future__ import annotations

from fastapi import Request

from . import addons, db, events, sources, vehiclebackup
from .connectors_web import _may_manage
from .web import app, form_dict, go, render

DEMOS = {"combustion": "demo-diesel", "electric": "demo-electric"}


@app.post("/vehicles/demo")
async def vehicle_demo(request: Request):
    """Ask first: this reads the standard source on GitHub (nothing goes online without the user's yes)."""
    form = await form_dict(request)
    kind = form.get("kind") if form.get("kind") in DEMOS else "combustion"
    with db.tx() as conn:
        if not sources.demo_offered(conn):
            return go(request, "/vehicles/new", "err.demo_missing")
    return render(request, "demo_consent.html", kind=kind, nav="vehicles")


@app.post("/vehicles/demo/load")
async def vehicle_demo_load(request: Request):
    if not _may_manage(request):
        return go(request, "/vehicles/new", "acct.need_admin")
    form = await form_dict(request)
    kind = form.get("kind") if form.get("kind") in DEMOS else "combustion"
    pkg = DEMOS[kind]
    with db.tx() as conn:
        if not sources.demo_offered(conn):  # the standard source was removed: no connection, no demo
            return go(request, "/vehicles/new", "err.demo_missing")
        sid = conn.execute("SELECT id FROM sources WHERE url = ?", (sources.DEFAULT_URL,)).fetchone()["id"]
    try:
        with db.tx() as conn:
            error = sources.refresh(conn, sid)
        if error:
            return go(request, "/vehicles/new", error)
        with db.tx() as conn:
            if sources.package(conn, sid, "vehicle", pkg) is None:
                return go(request, "/vehicles/new", "err.demo_missing")
            raw = sources.fetch_vehicle(conn, sid, pkg)
        # the car (an existing one with this identity is simply opened), then its plugin from the source, switched on
        with db.tx() as conn:
            data, zf = vehiclebackup.read(raw)
            zf.close()
            existing = vehiclebackup.find_existing(conn, data)
            vid = existing["id"] if existing else vehiclebackup.restore(conn, raw)
            waiting = [a for a in addons.list_for(conn, vid) if a["missing"] and a["need"]["state"] == "offer"]
        for a in waiting:
            with db.tx() as conn:
                manifest = sources.fetch_manifest(conn, a["need"]["source_id"], a["kind"], a["addon_id"])
            with db.tx() as conn:
                row_id = addons.add(conn, vid, manifest, a["need"]["source_id"])
                addons.set_active(conn, addons.get(conn, vid, row_id), True)  # the demo is meant to run: no extra step here
    except (sources.SourceError, vehiclebackup.VehicleBackupError, addons.AddonError) as exc:
        return go(request, "/vehicles/new", getattr(exc, "key", None) or str(exc))
    events.changed()
    with db.tx() as conn:
        slug = conn.execute("SELECT slug FROM vehicles WHERE id = ?", (vid,)).fetchone()["slug"]
    return go(request, f"/v/{slug}", "demo_ready")
