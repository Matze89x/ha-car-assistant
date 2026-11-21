"""Photos and videos of one vehicle: upload, choose what Home shows, delete, how a video's background blends in."""

from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse

from . import db, media
from .web import app, form_dict, go, render, vehicle_ctx, vehicle_or_404


@app.get("/v/{vid}/media")
def media_page(request: Request, vid: int):
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        return render(request, "media.html", **vehicle_ctx(conn, vehicle, "edit"), hide_hero=True, **media.panel(conn, vid))


def _back(request: Request, vid: int, form, msg: str):
    """Back to where the form was: the Home editor (reopens its window) or the library page."""
    where = {"home": f"/v/{vid}?edit=1", "car": f"/settings/car?car={vid}#media"}.get(form.get("back"), f"/v/{vid}/media")
    return go(request, where, msg)


@app.post("/v/{vid}/media")
async def media_upload(request: Request, vid: int):
    raw = await request.form()
    upload = raw.get("file")
    if upload is None or not getattr(upload, "filename", ""):
        return _back(request, vid, raw, "err.file_type")
    try:
        with db.tx() as conn:
            vehicle_or_404(conn, vid)
            mid = await media.store(conn, vid, upload)
            still = raw.get("poster")
            if still is not None and getattr(still, "filename", ""):
                media.store_poster(vid, mid, await still.read(media.MAX_POSTER + 1), conn)
    except media.MediaError as exc:
        return _back(request, vid, raw, exc.args[0])
    return _back(request, vid, raw, "saved")


@app.post("/v/{vid}/media/kind")
async def media_kind(request: Request, vid: int):
    form = await form_dict(request)
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        media.set_kind(conn, vid, form.get("kind", ""))
    return _back(request, vid, form, "saved")


@app.post("/v/{vid}/media/choose")
async def media_choose(request: Request, vid: int):
    """Save both choices at once: what the Dashboard shows (photo or video) and the photo used for lists and the car choice."""
    form = await form_dict(request)
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        for target, key in (("photo", "photo"), ("home", "home")):
            raw = form.get(key, "")
            if raw.isdigit():
                media.use(conn, vid, int(raw), target)
    return _back(request, vid, form, "saved")


@app.post("/v/{vid}/media/{mid}/use")
async def media_use(request: Request, vid: int, mid: int):
    form = await form_dict(request)
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        if not media.use(conn, vid, mid, form.get("for", "home")):
            raise HTTPException(404)
    return _back(request, vid, form, "saved")


@app.post("/v/{vid}/media/{mid}/delete")
async def media_delete(request: Request, vid: int, mid: int):
    form = await form_dict(request)
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        if not media.delete(conn, vid, mid):
            raise HTTPException(404)
    return _back(request, vid, form, "deleted")


@app.get("/v/{vid}/media/{mid}/file")
def media_file(vid: int, mid: int):
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        row = conn.execute("SELECT * FROM vehicle_media WHERE id = ? AND vehicle_id = ?", (mid, vid)).fetchone()
    if row is None:
        raise HTTPException(404)
    path = media.path_of(vid, row)
    if not path.is_file():
        raise HTTPException(404)
    # the address holds the item's id and the file never changes, so it may be kept; videos are served in ranges (iPhone needs them)
    return FileResponse(path, media_type=row["mime"], headers={"Cache-Control": "private, max-age=31536000, immutable"})


@app.get("/v/{vid}/media/{mid}/poster")
def media_poster(vid: int, mid: int):
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        row = conn.execute("SELECT * FROM vehicle_media WHERE id = ? AND vehicle_id = ? AND kind = 'video'", (mid, vid)).fetchone()
    if row is None or not media.poster_of(vid, row).is_file():
        raise HTTPException(404)
    return FileResponse(
        media.poster_of(vid, row), media_type="image/jpeg", headers={"Cache-Control": "private, max-age=31536000, immutable"}
    )
