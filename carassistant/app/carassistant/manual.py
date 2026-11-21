"""The manual ("Handbuch") of a vehicle: import a PDF (with a text layer), an EPUB, a text / Markdown file or a ready-made package (a zip with
page images), read it page by page with chapters, search it and export it as EPUB. Text and chapters are kept in the database, page images as
files in the data folder of the car; nothing from the file is executed.

Package (zip, optionally inside one folder): ``meta.json`` (title, pages, offset = printed page + offset is the page of the file, chapters as a
tree of ``{t, p, c: [...], g: part}``), ``p/NNN.avif|jpg|png|webp`` (page images) and optionally ``index.json.gz`` (a list of ``{p, t}``: the text
of each page, for the search) and optionally ``t/NNN.json.gz`` (per page ``{"x": [[printed page, x0, y0, x1, y1], ...]}``: boxes of page
references such as "page 137" on the image, in thousandths of the page width and height, which the reader makes tappable)."""

from __future__ import annotations

import gzip
import html
import io
import json
import re
import shutil
import sqlite3
import zipfile
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import ClassVar

from defusedxml import ElementTree as ET  # an EPUB is untrusted input: no entity tricks

from . import config, db

MAX_BYTES = 60 * 1024 * 1024
MAX_PAGES = 3000
CHUNK = 2400  # characters of a "page" for files that have no pages of their own (EPUB, text)
MAX_PACKAGE = 400 * 1024 * 1024  # uncompressed size of a package
MAX_IMAGE = 8 * 1024 * 1024
MAX_INDEX = 60 * 1024 * 1024
MAX_REFS = 2 * 1024 * 1024
IMAGE_EXT = ("avif", "jpg", "png", "webp")
IMAGE_MIME = {"avif": "image/avif", "jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
LAST = "manual.last"  # per vehicle: "<setting>.<vehicle id>" = the page read last


class ManualError(ValueError):
    """The file cannot be used; the message is an i18n key."""


class _Text(HTMLParser):
    BLOCK: ClassVar[set[str]] = {
        "p",
        "div",
        "br",
        "li",
        "tr",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "section",
        "article",
        "ul",
        "ol",
        "table",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0
        self.heading = ""
        self._in_h = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self.skip += 1
        if tag in self.BLOCK:
            self.parts.append("\n")
        if tag in ("h1", "h2", "h3") and not self.heading:
            self._in_h = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head"):
            self.skip = max(0, self.skip - 1)
        if tag in self.BLOCK:
            self.parts.append("\n")
        if tag in ("h1", "h2", "h3"):
            self._in_h = False

    def handle_data(self, data):
        if self.skip:
            return
        self.parts.append(data)
        if self._in_h and not self.heading:
            self.heading = data.strip()


def html_to_text(raw: str) -> tuple[str, str]:
    parser = _Text()
    parser.feed(raw)
    text = re.sub(r"[ \t\r\f\v]+", " ", "".join(parser.parts))
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return text, parser.heading


def paginate(text: str, size: int = CHUNK) -> list[str]:
    """Cut a long text into pages on paragraph borders."""
    pages: list[str] = []
    current = ""
    for para in re.split(r"\n\s*\n", text):
        if current and len(current) + len(para) > size:
            pages.append(current.strip())
            current = ""
        while len(para) > size * 2:  # a huge paragraph
            pages.append(para[:size].strip())
            para = para[size:]
        current += para + "\n\n"
    if current.strip():
        pages.append(current.strip())
    return pages or [""]


def parse_pdf(data: bytes) -> tuple[list[str], list[tuple[str, str, int]]]:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        count = len(reader.pages)
    except Exception as exc:
        raise ManualError("manual.err_file") from exc
    if count > MAX_PAGES:
        raise ManualError("manual.err_big")
    pages = []
    for page in reader.pages:
        try:
            pages.append((page.extract_text() or "").strip())
        except Exception:
            pages.append("")
    if not any(pages):
        raise ManualError("manual.err_scan")  # a scan without a text layer
    chapters: list[tuple[str, str, int]] = []

    def walk(items, group: str, depth: int) -> None:
        prev_title = ""
        for it in items:
            if isinstance(it, list):
                walk(it, prev_title if depth == 0 else group, depth + 1)
                continue
            try:
                number = reader.get_destination_page_number(it) + 1
            except Exception:  # noqa: S112 (a bookmark without a target is skipped)
                continue
            prev_title = str(getattr(it, "title", "") or "").strip()
            has_children = False
            if depth == 0:
                # a top-level entry with children becomes the group, one without is a chapter of its own
                idx = items.index(it)
                has_children = idx + 1 < len(items) and isinstance(items[idx + 1], list)
            if prev_title and not has_children:
                chapters.append((group, prev_title, number))

    try:
        walk(reader.outline, "", 0)
    except Exception:
        chapters = []
    return pages, chapters


def parse_epub(data: bytes) -> tuple[list[str], list[tuple[str, str, int]]]:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        container = ET.fromstring(z.read("META-INF/container.xml"))
        rootfile = next(e for e in container.iter() if e.tag.endswith("rootfile")).attrib["full-path"]
        opf = ET.fromstring(z.read(rootfile))
    except Exception as exc:
        raise ManualError("manual.err_file") from exc
    base = rootfile.rsplit("/", 1)[0] + "/" if "/" in rootfile else ""
    manifest = {e.attrib["id"]: e.attrib["href"] for e in opf.iter() if e.tag.endswith("}item") or e.tag == "item"}
    spine = [e.attrib["idref"] for e in opf.iter() if e.tag.endswith("itemref")]
    pages: list[str] = []
    chapters: list[tuple[str, str, int]] = []
    for ref in spine:
        href = manifest.get(ref)
        if not href:
            continue
        try:
            raw = z.read((base + href.split("#")[0]).lstrip("/")).decode("utf-8", "replace")
        except KeyError:
            continue
        text, heading = html_to_text(raw)
        if not text:
            continue
        chapters.append(("", heading or href.rsplit("/", 1)[-1].rsplit(".", 1)[0], len(pages) + 1))
        pages.extend(paginate(text))
        if len(pages) > MAX_PAGES:
            raise ManualError("manual.err_big")
    if not pages:
        raise ManualError("manual.err_file")
    return pages, chapters


def parse_text(data: bytes) -> tuple[list[str], list[tuple[str, str, int]]]:
    text = data.decode("utf-8", "replace")
    chapters: list[tuple[str, str, int]] = []
    pages: list[str] = []
    group = ""
    buf: list[str] = []

    def flush(title: str) -> None:
        body = "\n".join(buf).strip()
        if body and title:
            chapters.append((group, title, len(pages) + 1))
        if body:
            pages.extend(paginate(body))
        buf.clear()

    title = ""
    for line in text.splitlines():
        m = re.match(r"^(#{1,2})\s+(.*)$", line)
        if m:
            flush(title)
            if len(m.group(1)) == 1:
                group, title = m.group(2).strip(), m.group(2).strip()
            else:
                title = m.group(2).strip()
        else:
            buf.append(line)
    flush(title or "Text")
    if not pages:
        raise ManualError("manual.err_file")
    if len(pages) > MAX_PAGES:
        raise ManualError("manual.err_big")
    return pages, chapters


def folder(vehicle_id: int) -> Path:
    """Where the page images of a car are kept (it may not exist)."""
    return config.files_dir() / "manual" / str(int(vehicle_id))


def image_path(vehicle_id: int, page: int) -> Path | None:
    for ext in IMAGE_EXT:
        path = folder(vehicle_id) / f"{int(page):04d}.{ext}"
        if path.is_file():
            return path
    return None


def sniff_image(head: bytes) -> str | None:
    """Extension of a page image, recognised from its first bytes."""
    if head[4:8] == b"ftyp" and head[8:12] in (b"avif", b"avis"):
        return "avif"
    if head[:3] == b"\xff\xd8\xff":
        return "jpg"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def ref_boxes(raw: str, offset: int, pages: int) -> list[dict]:
    """The tappable page references of a page as percent boxes; the target is the PRINTED number plus the offset."""
    try:
        items = json.loads(raw) if raw else []
    except ValueError:
        return []
    out = []
    for item in items if isinstance(items, list) else []:
        if not (isinstance(item, list) and len(item) == 5):
            continue
        n, x0, y0, x1, y1 = item
        target = n + offset
        if 1 <= target <= pages:
            out.append(
                {
                    "printed": n,
                    "page": target,
                    "x": max(0, x0 - 2),  # a little room around the words (thousandths of the page)
                    "y": max(0, y0 - 1),
                    "w": x1 - x0 + 4,
                    "h": y1 - y0 + 2,
                }
            )
    return out


def shown(page: int, offset: int) -> int:
    """The number printed on a page (the page of the file minus the offset); pages before the first printed one show the file's number."""
    return page - offset if page - offset >= 1 else page


def _walk_chapters(nodes, depth: int, group: str, out: list[tuple[str, str, int, int]], pages: int) -> None:
    for node in nodes if isinstance(nodes, list) else []:
        if not isinstance(node, dict) or not isinstance(node.get("t"), str) or not isinstance(node.get("p"), int):
            continue
        grp = node["g"] if depth == 0 and isinstance(node.get("g"), str) else group
        out.append((grp, node["t"].strip(), max(1, min(node["p"], pages)), min(depth, 3)))
        _walk_chapters(node.get("c"), depth + 1, grp, out, pages)
        if len(out) > 5000:
            return


def parse_package(zf: zipfile.ZipFile) -> dict:
    """Read and check a package. Nothing is written; returns title, offset, texts, chapters and the page images (page -> (ext, member name))."""
    infos = [i for i in zf.infolist() if not i.is_dir()]
    metas = sorted((i.filename for i in infos if i.filename.rsplit("/", 1)[-1] == "meta.json" and i.filename.count("/") <= 1), key=len)
    if sum(i.file_size for i in infos) > MAX_PACKAGE:
        raise ManualError("manual.err_big")
    meta: dict = {}
    if metas:
        prefix = metas[0][: -len("meta.json")]
        try:
            meta = json.loads(zf.read(metas[0]))
        except ValueError:
            raise ManualError("manual.err_package") from None
        if not isinstance(meta, dict):
            raise ManualError("manual.err_package")
    else:  # the simple form: only numbered pictures (001.avif ...), at the top or in one folder, optionally inside p/
        simple = re.compile(r"^((?:[^/]+/)?)(?:p/)?\d{1,5}\.(?:avif|jpe?g|png|webp)$", re.I)
        found = sorted(m.group(1) for i in infos if (m := simple.match(i.filename)) and not i.filename.startswith("__MACOSX/"))
        if not found:
            raise ManualError("manual.err_package")
        prefix = found[0]
    images: dict[int, tuple[str, str]] = {}
    pattern = re.compile(r"^(?:p/)?(\d{1,5})\.(avif|jpe?g|png|webp)$", re.I)
    for info in infos:
        name = info.filename
        if not name.startswith(prefix) or ".." in name.split("/") or name.startswith("/"):
            continue
        m = pattern.match(name[len(prefix) :])
        if not m:
            continue
        if info.file_size > MAX_IMAGE:
            raise ManualError("manual.err_image")
        with zf.open(info) as fh:
            ext = sniff_image(fh.read(16))
        if ext is None:
            raise ManualError("manual.err_image")
        images[int(m.group(1))] = (ext, name)
    texts: dict[int, str] = {}
    index = prefix + "index.json.gz"
    if index in zf.namelist():
        try:
            with zf.open(index) as raw, gzip.GzipFile(fileobj=raw) as gz:
                body = gz.read(MAX_INDEX + 1)
            if len(body) > MAX_INDEX:
                raise ManualError("manual.err_big")
            entries = json.loads(body)
        except (OSError, EOFError, ValueError):
            raise ManualError("manual.err_package") from None
        for e in entries if isinstance(entries, list) else []:
            if isinstance(e, dict) and isinstance(e.get("p"), int) and isinstance(e.get("t"), str):
                texts[e["p"]] = e["t"]
    refs: dict[int, str] = {}
    for info in infos:
        m = re.match(r"^t/(\d{1,5})\.json\.gz$", info.filename[len(prefix) :]) if info.filename.startswith(prefix) else None
        if not m or ".." in info.filename.split("/"):
            continue
        try:
            with zf.open(info) as raw, gzip.GzipFile(fileobj=raw) as gz:
                body = gz.read(MAX_REFS + 1)
            data = json.loads(body) if len(body) <= MAX_REFS else {}
        except (OSError, EOFError, ValueError):
            continue  # a broken optional file only costs the tappable references of that page
        boxes = []
        for x in (data.get("x") if isinstance(data, dict) else None) or []:
            if isinstance(x, list) and len(x) == 5 and all(isinstance(v, int | float) and not isinstance(v, bool) for v in x):
                a, x0, y0, x1, y1 = (int(v) for v in x)
                if 1 <= a <= 9999 and 0 <= x0 < x1 <= 1000 and 0 <= y0 < y1 <= 1000:
                    boxes.append([a, x0, y0, x1, y1])
        if boxes:
            refs[int(m.group(1))] = json.dumps(boxes[:300], separators=(",", ":"))
    declared = meta.get("pages") if isinstance(meta.get("pages"), int) else 0
    pages = declared or max([*images, *texts, 0])
    if pages < 1 or not (images or any(texts.values())):
        raise ManualError("manual.err_package")
    if pages > MAX_PAGES:
        raise ManualError("manual.err_big")
    offset = meta.get("offset") if isinstance(meta.get("offset"), int) else 0
    chapters: list[tuple[str, str, int, int]] = []
    _walk_chapters(meta.get("chapters"), 0, "", chapters, pages)
    title = meta.get("title") if isinstance(meta.get("title"), str) else ""
    return {
        "title": title.strip()[:120],
        "offset": max(0, min(offset, pages - 1)),
        "pages": pages,
        "texts": texts,
        "refs": refs,
        "chapters": chapters,
        "images": {p: v for p, v in images.items() if 1 <= p <= pages},
    }


def import_package(conn: sqlite3.Connection, vehicle_id: int, name: str, fileobj) -> int:
    """Import a ready-made package (zip) with page images, replacing the manual of the car."""
    try:
        zf = zipfile.ZipFile(fileobj)
    except zipfile.BadZipFile:
        raise ManualError("manual.err_file") from None
    with zf:
        pkg = parse_package(zf)
        tmp = folder(vehicle_id).with_name(f"{int(vehicle_id)}.new")
        shutil.rmtree(tmp, ignore_errors=True)
        try:
            if pkg["images"]:
                tmp.mkdir(parents=True)
            for page, (ext, member) in pkg["images"].items():
                with zf.open(member) as src, open(tmp / f"{page:04d}.{ext}", "wb") as dst:
                    shutil.copyfileobj(src, dst)
            delete(conn, vehicle_id)
            if pkg["images"]:
                tmp.replace(folder(vehicle_id))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    title = pkg["title"] or re.sub(r"[_]+", " ", name.rsplit(".", 1)[0]).strip()[:120]
    conn.execute(
        "INSERT INTO manuals(vehicle_id, title, source_name, pages, imported_at, page_offset, images) VALUES(?,?,?,?,?,?,?)",
        (vehicle_id, title, name[:200], pkg["pages"], datetime.now(UTC).isoformat(timespec="seconds"), pkg["offset"], len(pkg["images"])),
    )
    conn.executemany(
        "INSERT INTO manual_pages(vehicle_id, page, text, refs) VALUES(?,?,?,?)",
        [(vehicle_id, i, pkg["texts"].get(i, "")[:20000], pkg["refs"].get(i, "")) for i in range(1, pkg["pages"] + 1)],
    )
    chapters = pkg["chapters"] or [("", title, 1, 0)]
    conn.executemany(
        "INSERT INTO manual_chapters(vehicle_id, grp, title, page, sort, depth) VALUES(?,?,?,?,?,?)",
        [(vehicle_id, g[:120], t[:160], p, i, d) for i, (g, t, p, d) in enumerate(chapters)],
    )
    return pkg["pages"]


def import_file(conn: sqlite3.Connection, vehicle_id: int, name: str, data: bytes) -> int:
    if len(data) > MAX_BYTES:
        raise ManualError("err.file_big")
    lower = name.lower()
    if data[:4] == b"%PDF":
        pages, chapters = parse_pdf(data)
    elif data[:2] == b"PK" and lower.endswith(".epub"):
        pages, chapters = parse_epub(data)
    elif lower.endswith((".txt", ".md", ".markdown")):
        pages, chapters = parse_text(data)
    else:
        raise ManualError("err.file_type")
    if not chapters:
        chapters = [("", name.rsplit(".", 1)[0], 1)]
    delete(conn, vehicle_id)
    title = re.sub(r"[_]+", " ", name.rsplit(".", 1)[0]).strip()[:120]
    conn.execute(
        "INSERT INTO manuals(vehicle_id, title, source_name, pages, imported_at) VALUES(?,?,?,?,?)",
        (vehicle_id, title, name[:200], len(pages), datetime.now(UTC).isoformat(timespec="seconds")),
    )
    conn.executemany(
        "INSERT INTO manual_pages(vehicle_id, page, text) VALUES(?,?,?)", [(vehicle_id, i + 1, t[:20000]) for i, t in enumerate(pages)]
    )
    conn.executemany(
        "INSERT INTO manual_chapters(vehicle_id, grp, title, page, sort) VALUES(?,?,?,?,?)",
        [(vehicle_id, g[:120], t[:160], max(1, min(p, len(pages))), i) for i, (g, t, p) in enumerate(chapters)],
    )
    return len(pages)


def delete(conn: sqlite3.Connection, vehicle_id: int) -> None:
    for table in ("manual_pages", "manual_chapters", "manuals"):
        conn.execute(f"DELETE FROM {table} WHERE vehicle_id = ?", (vehicle_id,))
    shutil.rmtree(folder(vehicle_id), ignore_errors=True)
    db.set_setting(conn, f"{LAST}.{vehicle_id}", None)


def info(conn: sqlite3.Connection, vehicle_id: int):
    return conn.execute("SELECT * FROM manuals WHERE vehicle_id = ?", (vehicle_id,)).fetchone()


def groups(conn: sqlite3.Connection, vehicle_id: int) -> list[dict]:
    out: dict[str, list] = {}
    for row in conn.execute("SELECT * FROM manual_chapters WHERE vehicle_id = ? ORDER BY sort", (vehicle_id,)):
        out.setdefault(row["grp"], []).append(row)
    return [{"title": g, "chapters": rows} for g, rows in out.items()]


def chapter_of(conn: sqlite3.Connection, vehicle_id: int, page: int) -> str:
    row = conn.execute(
        "SELECT title FROM manual_chapters WHERE vehicle_id = ? AND page <= ? ORDER BY page DESC, sort DESC LIMIT 1", (vehicle_id, page)
    ).fetchone()
    return row["title"] if row else ""


def get_page(conn: sqlite3.Connection, vehicle_id: int, page: int):
    return conn.execute("SELECT * FROM manual_pages WHERE vehicle_id = ? AND page = ?", (vehicle_id, page)).fetchone()


def last_read(conn: sqlite3.Connection, vehicle_id: int) -> int | None:
    raw = db.get_setting(conn, f"{LAST}.{vehicle_id}", "")
    return int(raw) if raw and raw.isdigit() else None


def remember(conn: sqlite3.Connection, vehicle_id: int, page: int) -> None:
    db.set_setting(conn, f"{LAST}.{vehicle_id}", str(page))


def search(conn: sqlite3.Connection, vehicle_id: int, query: str, limit: int = 60) -> list[dict]:
    q = query.strip()
    if len(q) < 2:
        return []
    like = "%" + q.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_") + "%"
    out = []
    for row in conn.execute(
        "SELECT page, text FROM manual_pages WHERE vehicle_id = ? AND text LIKE ? ESCAPE '\\' ORDER BY page LIMIT ?",
        (vehicle_id, like, limit),
    ):
        text = row["text"]
        at = text.lower().find(q.lower())
        start = max(0, at - 60)
        out.append(
            {
                "page": row["page"],
                "chapter": chapter_of(conn, vehicle_id, row["page"]),
                "before": text[start:at].replace("\n", " "),
                "hit": text[at : at + len(q)],
                "after": text[at + len(q) : at + len(q) + 90].replace("\n", " "),
            }
        )
    return out


def linkify(text: str, base: str, word: str, offset: int = 0, pages: int = 9999, view: str = "") -> str:
    """HTML of a page: escaped, 'page 137' references become links (word = the translated word for page). A reference names the PRINTED page,
    so the offset is added to find the page of the file."""
    safe = html.escape(text)
    pattern = re.compile(rf"(?i)\b({re.escape(word)}|page|seite)\s+(\d{{1,4}})\b")
    extra = f"&amp;view={view}" if view else ""
    return pattern.sub(lambda m: f'<a href="{base}/manual/read?page={min(int(m.group(2)) + offset, pages)}{extra}">{m.group(0)}</a>', safe)


def mark(text: str, query: str) -> str:
    safe = html.escape(text)
    if len(query.strip()) < 2:
        return safe
    return re.sub(f"(?i)({re.escape(html.escape(query.strip()))})", r"<mark>\1</mark>", safe)


def epub_bytes(conn: sqlite3.Connection, vehicle_id: int) -> bytes:
    """The manual as an EPUB (one file, one chapter per entry of the table of contents)."""
    meta = info(conn, vehicle_id)
    chapters = list(conn.execute("SELECT * FROM manual_chapters WHERE vehicle_id = ? ORDER BY page, sort", (vehicle_id,)))
    total = meta["pages"]
    if not chapters:
        chapters = [{"title": meta["title"] or "Manual", "page": 1}]
    buf = io.BytesIO()
    esc = html.escape
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
        )
        items, spine, nav = [], [], []
        for i, ch in enumerate(chapters):
            end = chapters[i + 1]["page"] - 1 if i + 1 < len(chapters) else total
            pages = [
                r["text"]
                for r in conn.execute(
                    "SELECT text FROM manual_pages WHERE vehicle_id = ? AND page BETWEEN ? AND ? ORDER BY page",
                    (vehicle_id, ch["page"], max(end, ch["page"])),
                )
            ]
            body = "".join(f"<p>{esc(p).replace(chr(10), '<br/>')}</p>" for p in pages)
            z.writestr(
                f"OEBPS/c{i}.xhtml",
                f'<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>{esc(ch["title"])}</title></head><body><h1>{esc(ch["title"])}</h1>{body}</body></html>',
            )
            items.append(f'<item id="c{i}" href="c{i}.xhtml" media-type="application/xhtml+xml"/>')
            spine.append(f'<itemref idref="c{i}"/>')
            nav.append(f'<li><a href="c{i}.xhtml">{esc(ch["title"])}</a></li>')
        z.writestr(
            "OEBPS/nav.xhtml",
            f'<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Contents</title></head>'
            f'<body><nav epub:type="toc"><ol>{"".join(nav)}</ol></nav></body></html>',
        )
        z.writestr(
            "OEBPS/content.opf",
            f'<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">'
            f'<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">manual-{vehicle_id}</dc:identifier><dc:title>{esc(meta["title"] or "Manual")}</dc:title><dc:language>und</dc:language></metadata>'
            f'<manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>{"".join(items)}</manifest><spine>{"".join(spine)}</spine></package>',
        )
    return buf.getvalue()


_ = json
