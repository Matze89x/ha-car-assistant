"""Routes: backup of one vehicle and restoring it (the whole system has its own backup under Settings -> System).

A backup of a car that is already here is not restored blindly: the user chooses to replace its data or to add a copy (name and address get a number).
A backup that holds secrets (tokens, passwords, keys, access codes: backupsecrets.py) is opened with its passphrase - typed in the form, never part of an
address - or restored without them.
"""

from __future__ import annotations

import re
import secrets
import time
from datetime import date
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import Response

from . import backupsecrets, config, db, sources, vehiclebackup
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


def _file(data: bytes, name: str) -> Response:
    return Response(
        data,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}", "Cache-Control": "no-store"},
    )


@app.get("/v/{vid}/backup.zip")
def vehicle_backup_download(request: Request, vid: int):
    """The plain backup of a car: no secret in it. (``?codes=1``, from before the passphrase, adds the access codes in plain text.)"""
    if not _may_manage(request):
        return go(request, f"/v/{vid}/edit", "acct.need_admin")
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        codes = request.query_params.get("codes") == "1"
        data = vehiclebackup.export(conn, vid, with_codes=codes)
        name = f"car-{vehicle['slug'] or vid}-{date.today().isoformat()}{'-with-codes' if codes else ''}.zip"
    return _file(data, name)


@app.post("/v/{vid}/backup.zip")
async def vehicle_backup_download_secure(request: Request, vid: int):
    """The backup of a car; with a passphrase typed in the form its secrets come along, encrypted (a passphrase never belongs into an address)."""
    if not _may_manage(request):
        return go(request, f"/v/{vid}/edit", "acct.need_admin")
    passphrase = (await form_dict(request)).get("passphrase", "")
    try:
        with db.tx() as conn:
            vehicle = vehicle_or_404(conn, vid)
            data = vehiclebackup.export(conn, vid, passphrase=passphrase or None)
            name = f"car-{vehicle['slug'] or vid}-{date.today().isoformat()}{'-with-secrets' if passphrase else ''}.zip"
    except backupsecrets.PassphraseTooShort:
        return go(request, f"/settings/car?car={vid}#vbackup", "err.bk_short")
    return _file(data, name)


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


def _question(request: Request, token: str, existing, data: dict, passphrase: str = "", locked: bool = False, status: int = 200):
    """The page that asks before a restore: replace or copy (the car is already here), and the passphrase (the backup holds secrets)."""
    return render(
        request,
        "restore_confirm.html",
        status=status,
        token=token,
        existing=existing,
        backup=vehiclebackup.summary(data),
        passphrase=passphrase,
        locked=locked,
        nav="vehicles",
    )


def handle_backup(request: Request, raw: bytes, back: str, passphrase: str = ""):
    """A backup file (uploaded or fetched from a source): restore it, or ask first when the car is already here or the secrets need their passphrase."""
    try:
        data, zf = vehiclebackup.read(raw)
        locked = vehiclebackup.secrets_state(zf) == "passphrase" and not passphrase
        if passphrase and vehiclebackup.secrets_state(zf) == "passphrase":
            vehiclebackup.open_secrets(zf, passphrase)  # a wrong passphrase is told now, not after a question
        zf.close()
        new_id = None
        with db.tx() as conn:
            existing = vehiclebackup.find_existing(conn, data)
            if existing is None and not locked:  # a car this system does not know: simply restore it
                new_id = vehiclebackup.restore(conn, raw, passphrase)
            else:
                existing = dict(existing) if existing else None
    except vehiclebackup.VehicleBackupError as exc:
        return go(request, back, str(exc))
    if new_id is not None:
        return _opened(request, new_id)  # (after the commit)
    # the car is already here, or the secrets are locked: keep the file for a moment and ask what to do
    token = secrets.token_urlsafe(16)
    (_pending_dir() / f"restore-{token}.zip").write_bytes(raw)
    return _question(request, token, existing, data, passphrase, locked)


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
    passphrase = form.get("passphrase")
    return handle_backup(request, await upload.read(vehiclebackup.MAX_BYTES + 1), back, passphrase if isinstance(passphrase, str) else "")


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


def _pending(token: str):
    path = _pending_dir() / f"restore-{token}.zip" if TOKEN.match(token) else None
    return path if path is not None and path.is_file() else None


@app.get("/vehicles/restore/ask")
def vehicle_restore_ask(request: Request):
    """The question again - after a passphrase that did not fit, or one that was missing (the file waits for a day)."""
    if not _may_manage(request):
        return go(request, "/vehicles", "acct.need_admin")
    token = request.query_params.get("token", "")
    path = _pending(token)
    if path is None:
        return go(request, "/vehicles", "err.vb_expired")
    try:
        data, zf = vehiclebackup.read(path.read_bytes())
        locked = vehiclebackup.secrets_state(zf) == "passphrase"
        zf.close()
        with db.tx() as conn:
            existing = vehiclebackup.find_existing(conn, data)
            existing = dict(existing) if existing else None
    except vehiclebackup.VehicleBackupError as exc:
        return go(request, "/vehicles", str(exc))
    return _question(request, token, existing, data, "", locked)


@app.post("/vehicles/restore/confirm")
async def vehicle_restore_confirm(request: Request):
    if not _may_manage(request):
        return go(request, "/vehicles", "acct.need_admin")
    form = await form_dict(request)
    token = form.get("token", "")
    path = _pending(token)
    if path is None:
        return go(request, "/vehicles", "err.vb_expired")
    mode = form.get("mode")
    if mode not in ("replace", "copy", "new"):
        path.unlink(missing_ok=True)
        return go(request, "/vehicles", "vb_cancelled")
    passphrase = "" if form.get("no_secrets") == "1" else form.get("passphrase", "")
    try:
        raw = path.read_bytes()
        with db.tx() as conn:
            data, zf = vehiclebackup.read(raw)
            locked = vehiclebackup.secrets_state(zf) == "passphrase" and not passphrase and form.get("no_secrets") != "1"
            zf.close()
            if locked:
                raise vehiclebackup.VehicleBackupError("err.bk_need_passphrase")
            target = vehiclebackup.find_existing(conn, data)
            new_id = (
                vehiclebackup.replace(conn, raw, target["id"], passphrase)
                if mode == "replace" and target
                else vehiclebackup.restore(conn, raw, passphrase)
            )
    except vehiclebackup.VehicleBackupError as exc:
        if str(exc) in ("err.bk_passphrase", "err.bk_need_passphrase"):  # the file waits: ask again, with the reason
            return go(request, f"/vehicles/restore/ask?token={token}", str(exc))
        path.unlink(missing_ok=True)
        return go(request, "/vehicles", str(exc))
    path.unlink(missing_ok=True)
    return _opened(request, new_id, created=not (mode == "replace" and target))
