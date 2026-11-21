"""Routes: backup of one vehicle and restoring it (the whole system has its own backup under Settings -> System).

A backup of a car that is already here is not restored blindly: the user chooses to replace its data or to add a copy (name and address get a number).
"""

from __future__ import annotations

import re
import secrets
import time
from datetime import date
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import Response

from . import config, db, sources, vehiclebackup
from .connectors_web import _may_manage
from .web import after_vehicle_created, app, form_dict, go, render, vehicle_or_404

PENDING_HOURS = 24
TOKEN = re.compile(r"^[A-Za-z0-9_-]{16,40}$")


def _pending_dir():
    path = config.data_dir() / "tmp"
    path.mkdir(exist_ok=True)
    for old in path.glob("restore-*.zip"):
        if time.time() - old.stat().st_mtime > PENDING_HOURS * 3600:
            old.unlink(missing_ok=True)
    return path


@app.get("/v/{vid}/backup.zip")
def vehicle_backup_download(request: Request, vid: int):
    if not _may_manage(request):
        return go(request, f"/v/{vid}/edit", "acct.need_admin")
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        codes = request.query_params.get("codes") == "1"  # with the access codes: a separate, deliberate download
        data = vehiclebackup.export(conn, vid, with_codes=codes)
        name = f"car-{vehicle['slug'] or vid}-{date.today().isoformat()}{'-with-codes' if codes else ''}.zip"
    return Response(data, media_type="application/zip", headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


def _opened(request: Request, new_id: int, created: bool = True):
    with db.tx() as conn:
        row = conn.execute(
            "SELECT slug, (SELECT COUNT(*) FROM vehicle_addons WHERE vehicle_id = vehicles.id AND status = 'missing') AS need FROM vehicles WHERE id = ?",
            (new_id,),
        ).fetchone()
        first_car = conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0] == 1
    if created and first_car:  # the very first car of a fresh system: the first-start guide goes on like after creating one
        return after_vehicle_created(request, new_id)
    # a restored car that needs packages opens where they are asked for
    return go(request, f"/v/{row['slug']}/plugins" if row["need"] else f"/v/{row['slug']}", "vb_restored")


def handle_backup(request: Request, raw: bytes, back: str):
    """A backup file (uploaded or fetched from a source): restore it, or ask first when the car is already here."""
    try:
        data, zf = vehiclebackup.read(raw)
        zf.close()
        new_id = None
        with db.tx() as conn:
            existing = vehiclebackup.find_existing(conn, data)
            if existing is None:  # a car this system does not know: simply restore it
                new_id = vehiclebackup.restore(conn, raw)
            else:
                existing = dict(existing)
    except vehiclebackup.VehicleBackupError as exc:
        return go(request, back, str(exc))
    if new_id is not None:
        return _opened(request, new_id)  # (after the commit)
    # the car is already here: keep the file for a moment and ask what to do
    token = secrets.token_urlsafe(16)
    (_pending_dir() / f"restore-{token}.zip").write_bytes(raw)
    return render(request, "restore_confirm.html", token=token, existing=existing, backup=vehiclebackup.summary(data), nav="vehicles")


@app.post("/vehicles/restore")
async def vehicle_restore(request: Request):
    if not _may_manage(request):
        return go(request, "/vehicles", "acct.need_admin")
    form = await request.form()
    back = (
        "/vehicles/new" if "/vehicles/new" in (request.headers.get("referer") or "") else "/vehicles"
    )  # an error returns to the page it came from
    upload = form.get("backup")
    if upload is None or not getattr(upload, "filename", ""):
        return go(request, back, "err.required")
    return handle_backup(request, await upload.read(vehiclebackup.MAX_BYTES + 1), back)


@app.post("/vehicles/from-source/{source_id}/{pkg_id}")
def vehicle_from_source(request: Request, source_id: int, pkg_id: str):
    """A car offered by a source (vehicles/<id>.zip): fetched now - the user pressed the button - and restored like an uploaded backup."""
    if not _may_manage(request):
        return go(request, "/vehicles/new", "acct.need_admin")
    try:
        with db.tx() as conn:
            raw = sources.fetch_vehicle(conn, source_id, pkg_id)
    except sources.SourceError as exc:
        return go(request, "/vehicles/new", str(exc))
    return handle_backup(request, raw, "/vehicles/new")


@app.post("/vehicles/restore/confirm")
async def vehicle_restore_confirm(request: Request):
    if not _may_manage(request):
        return go(request, "/vehicles", "acct.need_admin")
    form = await form_dict(request)
    token = form.get("token", "")
    path = _pending_dir() / f"restore-{token}.zip" if TOKEN.match(token) else None
    if path is None or not path.is_file():
        return go(request, "/vehicles", "err.vb_expired")
    mode = form.get("mode")
    try:
        if mode in ("replace", "copy"):
            raw = path.read_bytes()
            with db.tx() as conn:
                data, zf = vehiclebackup.read(raw)
                zf.close()
                target = vehiclebackup.find_existing(conn, data)
                new_id = (
                    vehiclebackup.replace(conn, raw, target["id"]) if mode == "replace" and target else vehiclebackup.restore(conn, raw)
                )
            return _opened(request, new_id, created=not (mode == "replace" and target))
        return go(request, "/vehicles", "vb_cancelled")
    except vehiclebackup.VehicleBackupError as exc:
        return go(request, "/vehicles", str(exc))
    finally:
        path.unlink(missing_ok=True)
