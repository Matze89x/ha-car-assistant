"""Import trips from a CSV file: the pages are the file, the columns, the check - and the one that says it worked (see tripimport.py for what is done with
the file). It is the road of the fill-ups (fuelimport_web.py): the file waits in the same folder between the pages (a name nobody can guess, two hours,
only for the car it was chosen for) and is deleted when the rows are written; nothing reaches the trip log before the person presses *Import* on the
last page.

The address is ``/v/<car>/trips-csv`` and not ``/v/<car>/trips/import``: the second would be taken for the number of a trip (``/v/<car>/trips/<id>``).
"""

from __future__ import annotations

import secrets

from fastapi import Request
from fastapi.responses import RedirectResponse

from . import db, events, fuelimport, tripimport, units
from .fuelimport_web import PREVIEW, _folder, _load, _purge, _save
from .web import app, clean_filename, form_dict, go, render, vehicle_ctx, vehicle_or_404

KIND = "trips"  # what the state of a chosen file says it is for: a file of the fill-ups does not open here


def _expired(request: Request, vid: int) -> RedirectResponse:
    return go(request, f"/v/{vid}/trips-csv", "ti_expired")


def _defaults(vehicle) -> dict:
    """The unit and the date order a file most likely has: the units of this server."""
    return {"order": "auto", "dist": "mi" if units.of(vehicle).imperial else "km", "skip": True}


def _result(conn, vehicle, table: fuelimport.Table, state: dict) -> fuelimport.Result:
    options = state.get("options") or {}
    mapping = {t: state.get("mapping", {}).get(t) for t in tripimport.TARGETS}
    have = tripimport.known(conn, vehicle["id"]) if options.get("skip", True) else None
    return tripimport.convert(table, mapping, options, have)


def _page(request: Request, conn, vehicle, step: int, status: int = 200, **ctx):
    return render(
        request,
        "trip_import.html",
        status=status,
        **vehicle_ctx(conn, vehicle, "trips"),
        step=step,
        furl=f"{request.state.base}/v/{vehicle['slug'] or vehicle['id']}/trips-csv",
        **ctx,
    )


def _columns_page(
    request: Request, conn, vehicle, token: str, table, state: dict, mapping: dict, options: dict, error: str = "", status: int = 200
):
    samples = [fuelimport.sample(table, i) for i in range(len(table.columns))]
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
        filename=state.get("name", ""),
        error=error,
    )


@app.get("/v/{vid}/trips-csv")
def trip_import_start(request: Request, vid: int):
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        return _page(request, conn, vehicle, 1, error="")


@app.post("/v/{vid}/trips-csv")
async def trip_import_upload(request: Request, vid: int):
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
    _save(token, {"vid": vid, "kind": KIND, "name": clean_filename(upload.filename)})
    return go(request, f"/v/{vid}/trips-csv/{token}")


@app.get("/v/{vid}/trips-csv/{token}")
def trip_import_columns(request: Request, vid: int, token: str):
    loaded = _load(vid, token, KIND)
    if loaded is None or loaded[1] is None:
        return _expired(request, vid)
    state, table = loaded
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        mapping = (
            {t: state["mapping"].get(t) for t in tripimport.TARGETS}
            if state.get("mapping")
            else tripimport.guess(table.columns, table.rows)
        )
        return _columns_page(request, conn, vehicle, token, table, state, mapping, state.get("options") or _defaults(vehicle))


@app.post("/v/{vid}/trips-csv/{token}")
async def trip_import_columns_save(request: Request, vid: int, token: str):
    loaded = _load(vid, token, KIND)
    if loaded is None or loaded[1] is None:
        return _expired(request, vid)
    state, table = loaded
    form = await form_dict(request)
    mapping: dict[str, int | None] = {}
    for target in tripimport.TARGETS:
        raw = form.get(f"col_{target}", "")
        mapping[target] = (
            int(raw) if raw.isascii() and raw.isdigit() and int(raw) < len(table.columns) else None
        )  # isascii: "²" is a digit for isdigit(), not for int()
    options = {
        "order": form.get("order") if form.get("order") in ("auto", *fuelimport.ORDERS) else "auto",
        "dist": "mi" if form.get("dist") == "mi" else "km",
        "skip": form.get("skip") in ("1", "on", "true"),
    }
    used = [i for i in mapping.values() if i is not None]
    error = tripimport.missing(mapping)
    if not error and len(used) != len(set(used)):
        error = "fuelimport.err_twice"
    if error:
        with db.tx() as conn:
            vehicle = vehicle_or_404(conn, vid)
            return _columns_page(request, conn, vehicle, token, table, state, mapping, options, error=error, status=400)
    _save(token, {**state, "mapping": mapping, "options": options})
    return go(request, f"/v/{vid}/trips-csv/{token}/check")


@app.get("/v/{vid}/trips-csv/{token}/check")
def trip_import_check(request: Request, vid: int, token: str):
    loaded = _load(vid, token, KIND)
    if loaded is None:
        return _expired(request, vid)
    state, table = loaded
    if state.get("done"):
        return go(request, f"/v/{vid}/trips-csv/{token}/done")
    if table is None:
        return _expired(request, vid)
    if not state.get("mapping"):
        return go(request, f"/v/{vid}/trips-csv/{token}")
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
            preview=sorted(result.rows, key=lambda r: (r["date"], r["start_time"] or ""), reverse=True)[:PREVIEW],
            filename=state.get("name", ""),
        )


@app.post("/v/{vid}/trips-csv/{token}/run")
def trip_import_run(request: Request, vid: int, token: str):
    loaded = _load(vid, token, KIND)
    if loaded is None:
        return _expired(request, vid)
    state, table = loaded
    if state.get("done") or table is None or not state.get("mapping"):
        return go(request, f"/v/{vid}/trips-csv/{token}/{'done' if state.get('done') else 'check'}")
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        result = _result(conn, vehicle, table, state)
        if not result.rows:
            return go(request, f"/v/{vid}/trips-csv/{token}/check")
        written = tripimport.insert(conn, vid, result.rows)
    _save(token, {**state, "done": {"imported": written, "duplicates": result.duplicates, "problems": result.problem_count}})
    (_folder() / f"{token}.csv").unlink(missing_ok=True)  # the file is not kept
    events.changed()
    return go(request, f"/v/{vid}/trips-csv/{token}/done")


@app.get("/v/{vid}/trips-csv/{token}/done")
def trip_import_done(request: Request, vid: int, token: str):
    loaded = _load(vid, token, KIND)
    if loaded is None or not loaded[0].get("done"):
        return _expired(request, vid)
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        return _page(request, conn, vehicle, 4, done=loaded[0]["done"])
