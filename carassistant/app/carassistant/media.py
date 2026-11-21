"""Photos and videos of a vehicle: a small library per car (at most KEEP files, photos and videos together).

Files live in ``<files>/media/<vehicle id>/``. The type is recognised from the first bytes (never from the name or the browser's
claim). Per car the newest ``KEEP`` files stay; the next upload removes the oldest one together with its file.
"""

from __future__ import annotations

import secrets
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from . import config

KEEP = 10
MAX_PHOTO = 10 * 1024 * 1024  # what is stored
MAX_PHOTO_UPLOAD = 40 * 1024 * 1024  # what may be uploaded: a big photo is shrunk, not refused
SHRINK_FROM = 2 * 1024 * 1024  # photos from this size on are shrunk (not PNG, never videos)
MAX_VIDEO = 40 * 1024 * 1024
MAX_SIDE = 1920  # longest side of a stored JPEG / WebP photo; PNG (cut-outs with transparency) is never touched
KINDS = ("adapt", "black", "alpha")  # how a video's own background blends into the page
CHUNK = 1024 * 1024
PHOTO_EXT = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


class MediaError(ValueError):
    """``args[0]`` is an i18n key."""


MAX_POSTER = 400_000  # bytes; the browser makes it small (640 px wide)


def sniff(head: bytes) -> tuple[str, str, str] | None:
    """``(kind, extension, mime)`` from the first bytes, or None for anything that is not png/jpg/webp/mp4/mov/webm."""
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "photo", "png", "image/png"
    if head[:3] == b"\xff\xd8\xff":
        return "photo", "jpg", "image/jpeg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "photo", "webp", "image/webp"
    if len(head) >= 12 and head[4:8] == b"ftyp":
        return ("video", "mov", "video/quicktime") if head[8:12] == b"qt  " else ("video", "mp4", "video/mp4")
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "video", "webm", "video/webm"
    return None


def folder(vid: int) -> Path:
    path = config.files_dir() / "media" / str(int(vid))
    path.mkdir(parents=True, exist_ok=True)
    return path


def path_of(vid: int, row: sqlite3.Row) -> Path:
    return folder(vid) / Path(row["file"]).name


def poster_of(vid: int, row: sqlite3.Row) -> Path:
    """The still picture of a video (taken by the browser when it was uploaded); it may not exist."""
    return folder(vid) / (Path(row["file"]).name + ".poster.jpg")


def store_poster(vid: int, mid: int, data: bytes, conn: sqlite3.Connection) -> bool:
    """Keep the preview picture of a video. Only a real, small JPEG is accepted; anything else is ignored."""
    row = conn.execute("SELECT * FROM vehicle_media WHERE id = ? AND vehicle_id = ? AND kind = 'video'", (mid, vid)).fetchone()
    if row is None or not data.startswith(b"\xff\xd8\xff") or len(data) > MAX_POSTER:
        return False
    poster_of(vid, row).write_bytes(data)
    return True


def items(conn: sqlite3.Connection, vid: int) -> list[dict]:
    """Newest first, each with ``home`` (shown on the Dashboard) and ``pick`` (the photo for lists and the car choice)."""
    chosen = conn.execute("SELECT media_id, photo_id FROM vehicles WHERE id = ?", (vid,)).fetchone()
    home, pick = (chosen["media_id"], chosen["photo_id"]) if chosen else (None, None)
    return [
        {**dict(r), "home": r["id"] == home, "pick": r["id"] == pick, "poster": r["kind"] == "video" and poster_of(vid, r).is_file()}
        for r in conn.execute("SELECT * FROM vehicle_media WHERE vehicle_id = ? ORDER BY id DESC", (vid,))
    ]


def panel(conn: sqlite3.Connection, vid: int) -> dict:
    """Everything the photo/video panel needs (the library page, the Home editor and the vehicle form share it)."""
    library = items(conn, vid)
    row = conn.execute("SELECT media_kind FROM vehicles WHERE id = ?", (vid,)).fetchone()
    return {
        "library": library,  # photos and videos together: what the Dashboard shows
        "photos": [m for m in library if m["kind"] == "photo"],  # photos only: lists, the car choice and so on
        "videos": [m for m in library if m["kind"] == "video"],
        "keep": KEEP,
        "kinds": KINDS,
        "kind": (row["media_kind"] if row else None) or "adapt",
    }


def active(conn: sqlite3.Connection, vid: int) -> sqlite3.Row | None:
    return conn.execute("SELECT m.* FROM vehicle_media m JOIN vehicles v ON v.media_id = m.id WHERE v.id = ?", (vid,)).fetchone()


def photo_row(conn: sqlite3.Connection, vid: int) -> sqlite3.Row | None:
    """The still picture for lists and as the video's stand-in: the chosen photo, else the newest one."""
    return conn.execute(
        "SELECT m.* FROM vehicle_media m WHERE m.vehicle_id = ? AND m.kind = 'photo' "
        "ORDER BY (m.id = (SELECT photo_id FROM vehicles WHERE id = ?)) DESC, m.id DESC LIMIT 1",
        (vid, vid),
    ).fetchone()


def _sync_photo_flag(conn: sqlite3.Connection, vid: int) -> None:
    """Keep both choices valid: the photo for lists (always a photo while one exists) and what Home shows (a photo or a video;
    a video may be there without any photo - lists and the car choice then show the standard car)."""
    photo = photo_row(conn, vid)
    home = conn.execute("SELECT m.id FROM vehicle_media m JOIN vehicles v ON v.media_id = m.id WHERE v.id = ?", (vid,)).fetchone()
    home_id = (
        home["id"] if home else (photo["id"] if photo else None)
    )  # a video may stand alone: lists and the car choice then show the standard car
    conn.execute(
        "UPDATE vehicles SET photo = ?, photo_id = ?, media_id = ? WHERE id = ?",
        (photo["file"] if photo else None, photo["id"] if photo else None, home_id, vid),
    )


def _remove(conn: sqlite3.Connection, vid: int, row: sqlite3.Row) -> None:
    path_of(vid, row).unlink(missing_ok=True)
    poster_of(vid, row).unlink(missing_ok=True)
    conn.execute("DELETE FROM vehicle_media WHERE id = ?", (row["id"],))


def _trim(conn: sqlite3.Connection, vid: int, kind: str = "") -> None:
    """At most ``KEEP`` files per car, photos and videos together: the oldest falls out. The last photo never does (a video
    always needs one), the oldest of the others goes instead."""
    rows = conn.execute("SELECT * FROM vehicle_media WHERE vehicle_id = ? ORDER BY id DESC", (vid,)).fetchall()
    keep, drop = rows[:KEEP], rows[KEEP:]
    if drop and not any(r["kind"] == "photo" for r in keep):
        saved = next(r for r in drop if r["kind"] == "photo") if any(r["kind"] == "photo" for r in drop) else None
        if saved is not None:
            drop = [keep[-1], *[r for r in drop if r["id"] != saved["id"]]]
    for row in drop:
        _remove(conn, vid, row)


def _check_photo(path: Path) -> None:
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(path) as image:
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise MediaError("err.file_type") from exc


def _shrink(path: Path, ext: str) -> int:
    """Photos from ``SHRINK_FROM`` (2 MB) on: turn upright (camera orientation), scale down to ``MAX_SIDE`` and drop the metadata (GPS position,
    camera); the quality is lowered step by step until the result fits ``MAX_PHOTO``. Smaller photos, every PNG (cut-outs with transparency)
    and all videos are kept exactly as they were uploaded. Returns the final size in bytes."""
    from PIL import Image, ImageOps

    original = path.stat().st_size
    if ext == "png" or original < SHRINK_FROM:
        return original
    with Image.open(path) as image:
        if ext == "jpg":
            image.draft("RGB", (MAX_SIDE * 2, MAX_SIDE * 2))  # the decoder reads a smaller version: little memory even for a 100 MP photo
        upright = ImageOps.exif_transpose(image)
        upright.load()
        if max(upright.size) > MAX_SIDE:
            upright.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
        if ext == "jpg":
            upright = upright.convert("RGB")
        out = path.with_suffix(".shrunk")
        for quality in (88, 80, 70, 60, 50):
            upright.save(out, "JPEG" if ext == "jpg" else "WEBP", quality=quality, **({"optimize": True} if ext == "jpg" else {}))
            if out.stat().st_size <= MAX_PHOTO:
                break
    if out.stat().st_size > MAX_PHOTO:
        out.unlink(missing_ok=True)
        raise MediaError("err.file_big")
    out.replace(path)
    return path.stat().st_size


async def store(conn: sqlite3.Connection, vid: int, upload, select: bool = True) -> int:
    """Check and keep an uploaded photo or video; returns its id. Raises MediaError."""
    target = folder(vid)
    tmp = target / f".upload-{secrets.token_hex(6)}.tmp"
    total, found = 0, None
    try:
        with tmp.open("wb") as fh:
            while True:
                chunk = await upload.read(CHUNK)
                if not chunk:
                    break
                if found is None:
                    found = sniff(chunk[:16])
                    if found is None:
                        raise MediaError("err.file_type")
                total += len(chunk)
                if total > (
                    MAX_PHOTO_UPLOAD if found[0] == "photo" and found[1] != "png" else MAX_PHOTO if found[1] == "png" else MAX_VIDEO
                ):
                    raise MediaError("err.file_big")
                fh.write(chunk)
        if found is None or total < 16:
            raise MediaError("err.file_type")
        kind, ext, mime = found
        if kind == "photo":
            _check_photo(tmp)
            total = _shrink(tmp, ext)
        name = f"{secrets.token_hex(8)}.{ext}"
        tmp.replace(target / name)
    finally:
        tmp.unlink(missing_ok=True)
    mid = conn.execute(
        "INSERT INTO vehicle_media(vehicle_id, kind, file, mime, size, created_at) VALUES(?,?,?,?,?,?)",
        (vid, kind, name, mime, total, datetime.now(UTC).isoformat(timespec="seconds")),
    ).lastrowid
    _trim(conn, vid, kind)
    if select:
        conn.execute("UPDATE vehicles SET media_id = ? WHERE id = ?", (mid, vid))
        if kind == "photo":
            conn.execute("UPDATE vehicles SET photo_id = ? WHERE id = ?", (mid, vid))
    _sync_photo_flag(conn, vid)
    return mid


def use(conn: sqlite3.Connection, vid: int, mid: int, target: str = "home") -> bool:
    """``home``: what the Dashboard shows (photo or video). ``photo``: the photo for lists and the car choice (photos only)."""
    row = conn.execute("SELECT * FROM vehicle_media WHERE id = ? AND vehicle_id = ?", (mid, vid)).fetchone()
    if row is None:
        return False
    if target == "photo":
        if row["kind"] != "photo":
            return False
        conn.execute("UPDATE vehicles SET photo_id = ? WHERE id = ?", (mid, vid))
    else:
        conn.execute("UPDATE vehicles SET media_id = ? WHERE id = ?", (mid, vid))
    _sync_photo_flag(conn, vid)
    return True


def delete(conn: sqlite3.Connection, vid: int, mid: int) -> bool:
    row = conn.execute("SELECT * FROM vehicle_media WHERE id = ? AND vehicle_id = ?", (mid, vid)).fetchone()
    if row is None:
        return False
    _remove(conn, vid, row)
    _sync_photo_flag(conn, vid)  # the newest remaining photo takes over; without any photo a chosen video is dropped too
    return True


def set_kind(conn: sqlite3.Connection, vid: int, kind: str) -> None:
    conn.execute("UPDATE vehicles SET media_kind = ? WHERE id = ?", (kind if kind in KINDS else None, vid))


def import_legacy(conn: sqlite3.Connection) -> None:
    """Photos uploaded before the library existed (``<files>/photos/<id>.<ext>``) become library items."""
    old = config.files_dir() / "photos"
    if not old.is_dir():
        return
    for path in sorted(old.iterdir()):
        stem = path.stem
        if not (path.is_file() and stem.isdigit() and path.suffix.lower() in PHOTO_EXT):
            continue
        vid = int(stem)
        if not conn.execute("SELECT 1 FROM vehicles WHERE id = ?", (vid,)).fetchone():
            continue
        if conn.execute("SELECT 1 FROM vehicle_media WHERE vehicle_id = ?", (vid,)).fetchone():
            continue
        found = sniff(path.read_bytes()[:16])
        if found is None or found[0] != "photo":
            continue
        name = f"{secrets.token_hex(8)}.{found[1]}"
        (folder(vid) / name).write_bytes(path.read_bytes())
        mid = conn.execute(
            "INSERT INTO vehicle_media(vehicle_id, kind, file, mime, size, created_at) VALUES(?,?,?,?,?,?)",
            (vid, "photo", name, found[2], path.stat().st_size, datetime.now(UTC).isoformat(timespec="seconds")),
        ).lastrowid
        conn.execute("UPDATE vehicles SET photo_id = ?, media_id = ?, photo = ? WHERE id = ?", (mid, mid, name, vid))
        path.unlink(missing_ok=True)
