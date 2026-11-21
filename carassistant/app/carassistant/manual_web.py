"""Routes of the manual ("Handbuch"): overview with chapters and search, reading page by page, import, export, delete."""

from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, Response

from . import config, db, events, i18n, manual, userprefs
from .web import app, go, render, vehicle_ctx, vehicle_or_404


@app.get("/v/{vid}/manual")
def manual_page(request: Request, vid: int):
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        meta = manual.info(conn, vid)
        q = request.query_params.get("q", "")[:80]
        last = manual.last_read(conn, vid) if meta else None
        return render(
            request,
            "manual.html",
            **vehicle_ctx(conn, vehicle, "manual"),
            meta=meta,
            chapter_groups=manual.groups(conn, vid) if meta else [],
            q=q,
            hits=manual.search(conn, vid, q) if meta and q else [],
            last=last,
            last_chapter=manual.chapter_of(conn, vid, last) if last else "",
            off=meta["page_offset"] if meta else 0,
            pg=(lambda n, o=meta["page_offset"]: manual.shown(n, o)) if meta else None,
        )


@app.get("/v/{vid}/manual/read")
def manual_read(request: Request, vid: int):
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        meta = manual.info(conn, vid)
        if meta is None:
            raise HTTPException(404)
        raw = request.query_params.get("page", "1")
        page = min(max(int(raw) if raw.isdigit() else 1, 1), meta["pages"])
        row = manual.get_page(conn, vid, page)
        manual.remember(conn, vid, page)
        q = request.query_params.get("q", "")[:80]
        base = f"{request.state.base}/v/{vehicle['slug']}"
        t = i18n.translator(config.language())
        view = request.query_params.get("view", "")
        me = request.state.user["id"] if request.state.user else None
        if view in ("image", "text") and me is not None:
            userprefs.put(conn, me, "manual_view", view)
        view = view if view in ("image", "text") else (userprefs.get(conn, me, "manual_view") or "image")
        has_image = bool(meta["images"]) and manual.image_path(vid, page) is not None
        view = "image" if has_image and view == "image" else "text"
        offset = meta["page_offset"]
        body = (
            manual.mark(row["text"], q)
            if q
            else manual.linkify(row["text"], base, t("manual.page_word"), offset, meta["pages"], "text" if view == "text" else "")
        )
        return render(
            request,
            "manual_read.html",
            **vehicle_ctx(conn, vehicle, "manual"),
            meta=meta,
            page=page,
            body=body,
            chapter=manual.chapter_of(conn, vid, page),
            q=q,
            view=view,
            has_image=has_image,
            shown=manual.shown(page, offset),
            refs=manual.ref_boxes(row["refs"], offset, meta["pages"]) if view == "image" else [],
        )


@app.get("/v/{vid}/manual/image/{page}")
def manual_image(vid: int, page: int):
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
    path = manual.image_path(vid, page)
    if path is None:
        raise HTTPException(404)
    return FileResponse(path, media_type=manual.IMAGE_MIME[path.suffix[1:]], headers={"Cache-Control": "private, max-age=3600"})


@app.post("/v/{vid}/manual/import")
async def manual_import(request: Request, vid: int):
    form = await request.form()
    upload = form.get("file")
    if upload is None or not getattr(upload, "filename", ""):
        return go(request, f"/v/{vid}/manual", "err.required")
    if upload.filename.lower().endswith(".zip"):  # a ready-made package: read from the temporary file, not into memory
        try:
            with db.tx() as conn:
                vehicle_or_404(conn, vid)
                manual.import_package(conn, vid, upload.filename, upload.file)
        except manual.ManualError as exc:
            return go(request, f"/v/{vid}/manual", exc.args[0])
        events.changed()
        return go(request, f"/v/{vid}/manual", "saved")
    data = await upload.read(manual.MAX_BYTES + 1)
    try:
        with db.tx() as conn:
            vehicle_or_404(conn, vid)
            manual.import_file(conn, vid, upload.filename, data)
    except manual.ManualError as exc:
        return go(request, f"/v/{vid}/manual", exc.args[0])
    events.changed()
    return go(request, f"/v/{vid}/manual", "saved")


@app.post("/v/{vid}/manual/delete")
async def manual_delete(request: Request, vid: int):
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        manual.delete(conn, vid)
    events.changed()
    return go(request, f"/v/{vid}/manual", "saved")


@app.get("/v/{vid}/manual/export.epub")
def manual_export(vid: int):
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        if manual.info(conn, vid) is None:
            raise HTTPException(404)
        data = manual.epub_bytes(conn, vid)
    return Response(data, media_type="application/epub+zip", headers={"Content-Disposition": f'attachment; filename="manual-{vid}.epub"'})
