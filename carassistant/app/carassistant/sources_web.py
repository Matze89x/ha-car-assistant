"""Routes: the package sources. The list is server-wide; Integrations and Plugins each have their own (a source can be in both)."""

from __future__ import annotations

from fastapi import Request

from . import db, sources
from .connectors_web import _may_manage
from .web import app, form_dict, go, render, vehicle_ctx


def _kind(form: dict) -> str:
    return form.get("kind") if form.get("kind") in sources.KINDS else "plugin"


async def _form(request: Request) -> tuple[dict, str, str | None]:
    form = await form_dict(request)
    vid = form.get("vid") if str(form.get("vid", "")).isdigit() else None
    return form, _kind(form), vid


def _reply(request: Request, kind: str, vid: str | None, msg: str | None = None, back: str = ""):
    """Back to the tab the user pressed the button on (Manage, Add or Sources of Integrations / Plugins in the vehicle page), else the plain page."""
    tab = {"manage": "", "add": "/add"}.get(back, "/sources")
    return go(request, f"/v/{vid}/{kind}s{tab}" if vid else f"/sources?kind={kind}", msg)


@app.get("/sources")
def sources_page(request: Request):
    """Without a vehicle there is no tab bar: the plain list of one kind (?kind=plugin|integration)."""
    asked = request.query_params.get("kind")
    kind = asked if asked in sources.KINDS else "plugin"
    with db.tx() as conn:
        rows = sources.listing(conn, kind)
        first = conn.execute("SELECT id FROM vehicles WHERE archived = 0 ORDER BY name COLLATE NOCASE LIMIT 1").fetchone()
    if first:
        return go(request, f"/v/{first['id']}/{kind}s/sources")
    return render(request, "sources.html", rows=rows, kind=kind, vid=None, has_default=any(r["is_default"] for r in rows))


@app.get("/v/{vid}/{kindw}/sources/{source_id}/key")
def source_key_page(request: Request, vid: int, kindw: str, source_id: int):
    """The access key of a source as a page of its own (it used to be a pop-up); Back is the Sources tab."""
    if kindw not in ("plugins", "integrations"):
        return go(request, "/sources")
    with db.tx() as conn:
        source = sources.get(conn, source_id)
        vehicle = conn.execute("SELECT * FROM vehicles WHERE id = ?", (vid,)).fetchone()
        if source is None or vehicle is None:
            return go(request, f"/v/{vid}/{kindw}/sources", "err.src_missing")
        ctx = vehicle_ctx(conn, vehicle, "integrations")
    return render(
        request,
        "source_key.html",
        **ctx,
        hide_hero=True,
        source=source,
        kind=kindw[:-1],
        has_token=bool(source["token"]),
        back_to=f"/v/{vid}/{kindw}/sources",
    )


@app.post("/sources")
async def sources_add(request: Request):
    form, kind, vid = await _form(request)
    if not _may_manage(request):
        return _reply(request, kind, vid, "acct.need_admin")
    try:
        with db.tx() as conn:
            new_id = sources.add(conn, form.get("name", ""), form.get("url", ""), form.get("token", ""), kind)
        with db.tx() as conn:
            error = sources.refresh(conn, new_id)  # a new source is read once so its packages show up right away
    except sources.SourceError as exc:
        return _reply(request, kind, vid, str(exc))
    return _reply(request, kind, vid, error or "src_added")


@app.post("/sources/refresh")
async def sources_refresh_all(request: Request):
    form, kind, vid = await _form(request)
    back = form.get("back", "")
    if not _may_manage(request):
        return _reply(request, kind, vid, "acct.need_admin", back)
    with db.tx() as conn:
        failed = sources.refresh_all(conn, kind)
    if failed:
        return _reply(request, kind, vid, "err.src_some", back)
    if back == "manage" and vid:  # "Check for updates": say what was found
        with db.tx() as conn:
            found = sources.updates_for(conn, int(vid), kind)
        return _reply(request, kind, vid, "src_updates_found" if found else "src_up_to_date", back)
    return _reply(request, kind, vid, "src_refreshed", back)


@app.post("/sources/restore-default")
async def sources_restore_default(request: Request):
    _, kind, vid = await _form(request)
    if not _may_manage(request):
        return _reply(request, kind, vid, "acct.need_admin")
    with db.tx() as conn:
        sources.restore_default(conn, kind)
    return _reply(request, kind, vid, "src_added")


@app.post("/sources/{source_id}/refresh")
async def sources_refresh(request: Request, source_id: int):
    _, kind, vid = await _form(request)
    if not _may_manage(request):
        return _reply(request, kind, vid, "acct.need_admin")
    with db.tx() as conn:
        error = sources.refresh(conn, source_id)
    return _reply(request, kind, vid, error or "src_refreshed")


@app.post("/sources/{source_id}/token")
async def sources_token(request: Request, source_id: int):
    form, kind, vid = await _form(request)
    if not _may_manage(request):
        return _reply(request, kind, vid, "acct.need_admin")
    with db.tx() as conn:
        sources.set_token(conn, source_id, form.get("token", ""), remove=bool(form.get("remove")))
    return _reply(request, kind, vid, "saved")


@app.post("/sources/{source_id}/delete")
async def sources_delete(request: Request, source_id: int):
    _, kind, vid = await _form(request)
    if not _may_manage(request):
        return _reply(request, kind, vid, "acct.need_admin")
    try:
        with db.tx() as conn:
            sources.remove(conn, source_id, kind)
    except sources.SourceError as exc:
        return _reply(request, kind, vid, str(exc))
    return _reply(request, kind, vid, "src_removed")
