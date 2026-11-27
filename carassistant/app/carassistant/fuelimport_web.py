"""Import fill-ups from a CSV file (Fuelio and others): the pages are the file, the columns, the check - and the one that says it worked (see
fuelimport.py for what is done with the file).

The file waits in a folder of its own between the pages (a name nobody can guess, two hours, only for the car it was chosen for) and is deleted
when the rows are written. Nothing reaches the fuel log before the person presses *Import* on the last page.
"""

from __future__ import annotations

import json
import re
import secrets
import time
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

from . import config, db, events, fuelimport, units
from .web import app, clean_filename, form_dict, go, render, unit_for, vehicle_ctx, vehicle_or_404

KEEP = 2 * 3600  # seconds a chosen file waits for the person
TOKEN = re.compile(r"^[A-Za-z0-9_-]{16,40}$")
PREVIEW = 8  # rows shown on the page that asks for the last yes


def _folder() -> Path:
    path = config.data_dir() / "import-cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _purge() -> None:
    """Chosen files that nobody finished are not kept."""
    now = time.time()
    for entry in _folder().iterdir():
        try:
            if now - entry.stat().st_mtime > KEEP:
                entry.unlink()
        except OSError:
            continue


def _load(vid: int, token: str, kind: str = "fuel") -> tuple[dict, fuelimport.Table | None] | None:
    """``(state, table)`` of a chosen file; ``table`` is None once the import is done (the file is gone then). ``None`` when the token is unknown,
    too old, a file of the other import (``kind``: the fill-ups or the trips share the folder) or belongs to another car."""
    if not TOKEN.match(token):
        raise HTTPException(404)
    try:
        state = json.loads((_folder() / f"{token}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if state.get("vid") != vid:
        raise HTTPException(404)
    if state.get("kind", "fuel") != kind:
        return None
    try:
        table = fuelimport.read((_folder() / f"{token}.csv").read_bytes())
    except (OSError, fuelimport.FileError):
        table = None
    return state, table


def _save(token: str, state: dict) -> None:
    (_folder() / f"{token}.json").write_text(json.dumps(state), encoding="utf-8")


def _expired(request: Request, vid: int) -> RedirectResponse:
    return go(request, f"/v/{vid}/fuel/import", "fi_expired")


def _defaults(table: fuelimport.Table, vehicle) -> dict:
    """The units and the date order a file most likely has: what a Fuelio file says about itself, else the units of this server."""
    u = units.of(vehicle)
    return {
        "order": "auto",
        "dist": table.meta.get("dist") or ("mi" if u.imperial else "km"),
        "vol": table.meta.get("vol") or {"us": "usgal", "uk": "ukgal"}.get(u.system, "l"),
        "skip": True,
    }


def _result(conn, vehicle, table: fuelimport.Table, state: dict) -> fuelimport.Result:
    options = state.get("options") or {}
    mapping = {t: state.get("mapping", {}).get(t) for t in fuelimport.TARGETS}
    have = fuelimport.known(conn, vehicle["id"]) if options.get("skip", True) else None
    return fuelimport.convert(table, mapping, options, unit_for(vehicle["fuel_type"]), have)


def _page(request: Request, conn, vehicle, step: int, status: int = 200, **ctx):
    return render(
        request,
        "fuel_import.html",
        status=status,
        **vehicle_ctx(conn, vehicle, "fuel"),
        step=step,
        furl=f"{request.state.base}/v/{vehicle['slug'] or vehicle['id']}/fuel/import",
        base_unit=unit_for(vehicle["fuel_type"]),
        **ctx,
    )


def _columns_page(
    request: Request, conn, vehicle, token: str, table, state: dict, mapping: dict, options: dict, error: str = "", status: int = 200
):
    samples = [fuelimport.sample(table, i) for i in range(len(table.columns))]
    found = fuelimport.detect_order([row[mapping["date"]] for row in table.rows[:200]]) if mapping.get("date") is not None else None
    return _page(
        request,
        conn,
        vehicle,
        2,
        status=status,
        token=token,
        table=table,
        samples=samples,
        mapping=mapping,
        options=options,
        detected=found or table.meta.get("order") or "ymd",
        filename=state.get("name", ""),
        error=error,
    )


@app.get("/v/{vid}/fuel/import")
def import_start(request: Request, vid: int):
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        return _page(request, conn, vehicle, 1, error="")


@app.post("/v/{vid}/fuel/import")
async def import_upload(request: Request, vid: int):
    form = await request.form()
    upload = form.get("file")
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
    if upload is None or not getattr(upload, "filename", ""):
        with db.tx() as conn:
            return _page(request, conn, vehicle, 1, status=400, error="err.required")
    data = await upload.read(fuelimport.MAX_BYTES + 1)
    try:
        fuelimport.read(data)  # is it a table at all? (the pages read it again: the file is the one thing that is kept)
    except fuelimport.FileError as exc:
        with db.tx() as conn:
            return _page(request, conn, vehicle, 1, status=400, error=exc.key)
    _purge()
    token = secrets.token_urlsafe(16)
    (_folder() / f"{token}.csv").write_bytes(data)
    _save(token, {"vid": vid, "name": clean_filename(upload.filename)})
    return go(request, f"/v/{vid}/fuel/import/{token}")


@app.get("/v/{vid}/fuel/import/{token}")
def import_columns(request: Request, vid: int, token: str):
    loaded = _load(vid, token)
    if loaded is None or loaded[1] is None:
        return _expired(request, vid)
    state, table = loaded
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        mapping = {t: state["mapping"].get(t) for t in fuelimport.TARGETS} if state.get("mapping") else fuelimport.guess(table.columns)
        return _columns_page(request, conn, vehicle, token, table, state, mapping, state.get("options") or _defaults(table, vehicle))


@app.post("/v/{vid}/fuel/import/{token}")
async def import_columns_save(request: Request, vid: int, token: str):
    loaded = _load(vid, token)
    if loaded is None or loaded[1] is None:
        return _expired(request, vid)
    state, table = loaded
    form = await form_dict(request)
    mapping: dict[str, int | None] = {}
    for target in fuelimport.TARGETS:
        raw = form.get(f"col_{target}", "")
        mapping[target] = int(raw) if raw.isdigit() and int(raw) < len(table.columns) else None
    options = {
        "order": form.get("order") if form.get("order") in ("auto", *fuelimport.ORDERS) else "auto",
        "dist": "mi" if form.get("dist") == "mi" else "km",
        "vol": form.get("vol") if form.get("vol") in ("l", "usgal", "ukgal") else "l",
        "skip": form.get("skip") in ("1", "on", "true"),
    }
    used = [i for i in mapping.values() if i is not None]
    error = ""
    if any(mapping[t] is None for t in fuelimport.REQUIRED):
        error = "fuelimport.err_required"
    elif len(used) != len(set(used)):
        error = "fuelimport.err_twice"
    if error:
        with db.tx() as conn:
            vehicle = vehicle_or_404(conn, vid)
            return _columns_page(request, conn, vehicle, token, table, state, mapping, options, error=error, status=400)
    _save(token, {**state, "mapping": mapping, "options": options})
    return go(request, f"/v/{vid}/fuel/import/{token}/check")


@app.get("/v/{vid}/fuel/import/{token}/check")
def import_check(request: Request, vid: int, token: str):
    loaded = _load(vid, token)
    if loaded is None:
        return _expired(request, vid)
    state, table = loaded
    if state.get("done"):
        return go(request, f"/v/{vid}/fuel/import/{token}/done")
    if table is None:
        return _expired(request, vid)
    if not state.get("mapping"):
        return go(request, f"/v/{vid}/fuel/import/{token}")
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        result = _result(conn, vehicle, table, state)
        return _page(
            request,
            conn,
            vehicle,
            3,
            token=token,
            result=result,
            preview=sorted(result.rows, key=lambda r: r["date"], reverse=True)[:PREVIEW],
            filename=state.get("name", ""),
        )


@app.post("/v/{vid}/fuel/import/{token}/run")
def import_run(request: Request, vid: int, token: str):
    loaded = _load(vid, token)
    if loaded is None:
        return _expired(request, vid)
    state, table = loaded
    if state.get("done") or table is None or not state.get("mapping"):
        return go(request, f"/v/{vid}/fuel/import/{token}/{'done' if state.get('done') else 'check'}")
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        result = _result(conn, vehicle, table, state)
        if not result.rows:
            return go(request, f"/v/{vid}/fuel/import/{token}/check")
        written = fuelimport.insert(conn, vid, result.rows)
    _save(token, {**state, "done": {"imported": written, "duplicates": result.duplicates, "problems": result.problem_count}})
    (_folder() / f"{token}.csv").unlink(missing_ok=True)  # the file is not kept
    events.changed()
    return go(request, f"/v/{vid}/fuel/import/{token}/done")


@app.get("/v/{vid}/fuel/import/{token}/done")
def import_done(request: Request, vid: int, token: str):
    loaded = _load(vid, token)
    if loaded is None or not loaded[0].get("done"):
        return _expired(request, vid)
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        return _page(request, conn, vehicle, 4, done=loaded[0]["done"])
