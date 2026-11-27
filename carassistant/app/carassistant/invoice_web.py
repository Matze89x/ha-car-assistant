"""The invoices tab of the cost page: upload or photograph an invoice, see what was read from it, book it as a cost (see invoice.py and invoice_book.py).

An invoice is a document of the category ``invoice``: the file lives where the other documents live and shows up on the Documents page as well. What
the reading found is kept next to it; booking opens the ordinary form of a service, parts, modification, fixed cost or refuel entry, filled in
(``web.entity_page``), and the save of that form links the entry to the invoice.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse

from . import config, db, i18n, invoice, invoice_book, lists, receipt
from .web import DOC_EXT, MAX_DOC, _doc_path, app, clean_filename, go, render, vehicle_ctx, vehicle_or_404

ALLOWED = (".pdf", *invoice.IMAGE_EXT, ".txt")  # what can be an invoice: a PDF, a photo or scan, a text
MAX_FILES = 10  # one upload
READ_BUDGET = 60  # seconds of reading in one upload; what is left over is read when its page is opened


def _store_reading(conn, vid: int, doc_id: int, result: dict) -> None:
    """What the reading found, kept with the document: the total, the date, the sender as the title (while the title is still the file name)."""
    doc = invoice_book.document(conn, vid, doc_id)
    if doc is None:
        return
    title = doc["title"]
    if result.get("vendor") and title == doc["filename"]:
        title = " ".join(x for x in (result["vendor"], result.get("number")) if x)[:120]
    conn.execute(
        "UPDATE documents SET extract = ?, amount = ?, doc_date = COALESCE(doc_date, ?), title = ? WHERE id = ?",
        (json.dumps(result, ensure_ascii=False), result.get("amount"), result.get("date"), title, doc_id),
    )


async def _read(vid: int, doc_id: int) -> dict | None:
    """Read the file of an invoice (in a thread: text recognition takes seconds) and keep what was found."""
    with db.tx() as conn:
        doc = invoice_book.document(conn, vid, doc_id)
        if doc is None:
            return None
        path, filename = _doc_path(vid, doc), doc["filename"]
    data = path.read_bytes() if path.is_file() else b""
    result = await asyncio.to_thread(invoice.read, data, filename) if data else {**invoice.parse(""), "how": ""}
    with db.tx() as conn:
        _store_reading(conn, vid, doc_id, result)
    return result


def _ctx(conn, vehicle) -> dict:
    from .nav_web import section_tabs

    tabs = section_tabs(conn, vehicle["id"], "invoices", i18n.translator(config.language()))
    return {**vehicle_ctx(conn, vehicle, "report"), "section_tabs": tabs, "ocr": receipt.available()}


@app.get("/v/{vid}/invoices")
def invoices_page(request: Request, vid: int):
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        total = conn.execute("SELECT COUNT(*) FROM documents WHERE vehicle_id = ? AND category = 'invoice'", (vid,)).fetchone()[0]
        pages = max(1, -(-total // lists.size()))
        asked = request.query_params.get("page", "1")
        page = min(max(int(asked) if asked.isdigit() else 1, 1), pages)
        docs = conn.execute(
            "SELECT * FROM documents WHERE vehicle_id = ? AND category = 'invoice' "
            "ORDER BY (booked_table IS NOT NULL), COALESCE(doc_date, substr(created_at, 1, 10)) DESC, id DESC LIMIT ? OFFSET ?",
            (vid, lists.size(), (page - 1) * lists.size()),
        ).fetchall()
        return render(
            request,
            "invoices.html",
            **_ctx(conn, vehicle),
            docs=docs,
            extracts={d["id"]: invoice_book.extract_of(d) for d in docs},
            booked=invoice_book.booked(conn, vid, docs),
            sums=invoice_book.sums(conn, vid),
            pager={"page": page, "pages": pages, "total": total, "size": lists.size()},
        )


@app.post("/v/{vid}/invoices")
async def invoices_upload(request: Request, vid: int):
    form = await request.form()
    uploads = [u for u in form.getlist("file") if getattr(u, "filename", "")][:MAX_FILES]
    if not uploads:
        return go(request, f"/v/{vid}/invoices", "err.required")
    deadline = time.monotonic() + READ_BUDGET
    last, made, again, refused = None, 0, 0, 0
    for upload in uploads:
        filename = clean_filename(upload.filename)
        ext = Path(filename).suffix.lower()
        data = await upload.read(MAX_DOC + 1)
        if ext not in ALLOWED or len(data) > MAX_DOC or not data:
            refused += 1
            continue
        sha = hashlib.sha256(data).hexdigest()
        with db.tx() as conn:
            vehicle_or_404(conn, vid)
            same = conn.execute(
                "SELECT id FROM documents WHERE vehicle_id = ? AND category = 'invoice' AND sha256 = ?", (vid, sha)
            ).fetchone()
            if same:  # the same file again: nothing is stored twice
                last, again = same["id"], again + 1
                continue
            doc_id = conn.execute(
                "INSERT INTO documents(vehicle_id, category, title, filename, mime, size, sha256) VALUES(?,?,?,?,?,?,?)",
                (vid, "invoice", filename, filename, DOC_EXT.get(ext), len(data), sha),
            ).lastrowid
            folder = config.files_dir() / str(vid)
            folder.mkdir(exist_ok=True)
            (folder / f"{doc_id}{ext}").write_bytes(data)
        last, made = doc_id, made + 1
        if time.monotonic() < deadline:
            result = await asyncio.to_thread(invoice.read, data, filename)
            with db.tx() as conn:
                _store_reading(conn, vid, doc_id, result)
    if not made and not again:
        return go(request, f"/v/{vid}/invoices", "err.file_type")
    if len(uploads) == 1 and last:
        return go(request, f"/v/{vid}/invoices/{last}", "inv_again" if again else None)
    return go(request, f"/v/{vid}/invoices", "inv_many" if not refused else "inv_some")


@app.get("/v/{vid}/invoices/{doc_id}")
async def invoice_page(request: Request, vid: int, doc_id: int):
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        doc = invoice_book.document(conn, vid, doc_id)
        if doc is None:
            raise HTTPException(404)
        unread = doc["extract"] is None
    if unread:  # uploaded on the Documents page, or the reading did not fit into the time of the upload
        await _read(vid, doc_id)
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        doc = invoice_book.document(conn, vid, doc_id)
        extract = invoice_book.extract_of(doc)
        kinds = invoice_book.kinds_open(conn, vid)
        return render(
            request,
            "invoice.html",
            **_ctx(conn, vehicle),
            doc=doc,
            ex=extract,
            kinds=kinds,
            suggested=extract.get("kind") if extract.get("kind") in kinds else None,
            booked=invoice_book.booked(conn, vid, [doc]).get(doc_id),
            is_image=Path(doc["filename"]).suffix.lower() in invoice.IMAGE_EXT,
            has_file=_doc_path(vid, doc).is_file(),
        )


@app.get("/v/{vid}/invoices/{doc_id}/file")
def invoice_file(vid: int, doc_id: int):
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        doc = invoice_book.document(conn, vid, doc_id)
    if doc is None or not _doc_path(vid, doc).is_file():
        raise HTTPException(404)
    path = _doc_path(vid, doc)
    return FileResponse(  # shown in the page or the browser; the type comes from the ending we checked, never from the file
        path,
        media_type=DOC_EXT.get(path.suffix.lower(), "application/octet-stream"),
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(doc['filename'])}", "X-Content-Type-Options": "nosniff"},
    )


@app.post("/v/{vid}/invoices/{doc_id}/read")
async def invoice_read(request: Request, vid: int, doc_id: int):
    if await _read(vid, doc_id) is None:
        raise HTTPException(404)
    return go(request, f"/v/{vid}/invoices/{doc_id}", "inv_read")


@app.post("/v/{vid}/invoices/{doc_id}/unlink")
def invoice_unlink(request: Request, vid: int, doc_id: int):
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        if invoice_book.document(conn, vid, doc_id) is None:
            raise HTTPException(404)
        invoice_book.unlink(conn, vid, doc_id)
    return go(request, f"/v/{vid}/invoices/{doc_id}", "saved")


@app.post("/v/{vid}/invoices/{doc_id}/delete")
def invoice_delete(request: Request, vid: int, doc_id: int):
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        doc = invoice_book.document(conn, vid, doc_id)
        if doc is None:
            raise HTTPException(404)
        _doc_path(vid, doc).unlink(missing_ok=True)  # the cost entry it was booked as stays: only the invoice goes
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    return go(request, f"/v/{vid}/invoices", "deleted")
