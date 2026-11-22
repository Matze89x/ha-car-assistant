"""Backup and restore of ONE vehicle (everything that belongs to that car only), separate from the backup of the whole system (backup.py).

A vehicle backup is a zip: ``vehicle.json`` (the data) and ``files/`` (documents, photos, videos). It holds the vehicle, all its lists (service, fuel,
trips with their route, ...), its live values, its settings (navigation, widgets, hidden functions), its connection tokens (as the hash the server
keeps, so a plugin keeps working with the token it already has, plus the kept token itself: the file is as private as the tokens) and its integrations and plugins with their settings - but NOT the packages
themselves. Restored as a NEW vehicle; integrations and plugins come back switched OFF (activate them on purpose) and, when their package is not
installed, as "needs the package" (see addons.py).

Compatibility: ``format`` is the layout. From version 1.0 on every newer app restores every older format; a backup from a newer app is refused.
The reader ignores columns it does not know and fills missing ones with their default, so small additions never break an old backup.
"""

from __future__ import annotations

import io
import json
import secrets
import shutil
import sqlite3
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from . import __version__, appicon, config, slugs

FORMAT = 1
MAX_BYTES = 500 * 1024 * 1024
MAX_ROWS = 500_000

# tables that hold one vehicle's rows (vehicle_id column); id columns are re-created on restore
LISTS = (
    "odometer",
    "service",
    "appointments",
    "mods",
    "tires",
    "tire_pressure",
    "tasks",
    "fuel",
    "trips",
    "counters",
    "parts",
    "documents",
    "vehicle_media",
    "equipment",
    "manuals",
    "manual_chapters",
    "manual_pages",
    "live",
)
SETTINGS = (
    "home.widgets",
    "nav.slots",
    "modules.off",
    "debug",
    "interval",
    "equipment.order",
)  # per-vehicle settings: "<prefix>.<vehicle id>"
SCALARS = (str, int, float, type(None))


class VehicleBackupError(ValueError):
    """The file is not a usable vehicle backup; the message is an i18n key."""


def _rows(conn: sqlite3.Connection, sql: str, args: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def _safe(name: str) -> bool:
    p = PurePosixPath(name)
    return not p.is_absolute() and ".." not in p.parts and (name == "vehicle.json" or p.parts[0] == "files")


def export(conn: sqlite3.Connection, vid: int, with_codes: bool = False) -> bytes:
    from . import manual, media

    vehicle = conn.execute("SELECT * FROM vehicles WHERE id = ?", (vid,)).fetchone()
    if vehicle is None:
        raise VehicleBackupError("err.vb_missing")
    if not vehicle["uid"]:  # a car gets its identity the first time it is backed up
        conn.execute("UPDATE vehicles SET uid = ? WHERE id = ?", (secrets.token_hex(8), vid))
        vehicle = conn.execute("SELECT * FROM vehicles WHERE id = ?", (vid,)).fetchone()
    data: dict = {
        "app": "carassistant",
        "kind": "vehicle",
        "format": FORMAT,
        "version": __version__,
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "vehicle": {k: v for k, v in dict(vehicle).items() if k not in ("id", "slug")},
        "tables": {},
        "settings": {},
        "tokens": [],
        "addons": [],
    }
    for table in LISTS:
        data["tables"][table] = _rows(conn, f"SELECT * FROM {table} WHERE vehicle_id = ?", (vid,))
    data["tables"]["trip_points"] = _rows(
        conn, "SELECT p.* FROM trip_points p JOIN trips t ON t.id = p.trip_id WHERE t.vehicle_id = ? ORDER BY p.trip_id, p.seq", (vid,)
    )
    for prefix in SETTINGS:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (f"{prefix}.{vid}",)).fetchone()
        if row:
            data["settings"][prefix] = row["value"]
    data["tokens"] = _rows(conn, "SELECT id, name, token_hash, created_at FROM api_tokens WHERE vehicle_id = ?", (vid,))
    from . import connectors

    for tok in data[
        "tokens"
    ]:  # the kept token goes in readable (the key of this system is not in the file): the file is as private as the tokens
        kept = connectors.remembered(conn, tok["id"])
        if kept:
            tok["token"] = kept
    for a in conn.execute(
        "SELECT a.*, COALESCE(s.url, a.source_url) AS origin FROM vehicle_addons a LEFT JOIN sources s ON s.id = a.source_id WHERE a.vehicle_id = ? ORDER BY a.id",
        (vid,),
    ):
        data["addons"].append(
            {
                "addon_id": a["addon_id"],
                "kind": a["kind"],
                "manifest": json.loads(a["manifest"]),
                "settings": {  # a password (login data of a web service, ...) is never part of a backup file: it is entered again after a restore
                    k: v
                    for k, v in json.loads(a["settings"] or "{}").items()
                    if k not in {f["key"] for f in json.loads(a["manifest"]).get("settings", []) if f.get("type") == "password"}
                },
                "status": a["status"],
                "token_id": a["token_id"],
                "source_url": a["origin"],
            }
        )
    from . import pagemods

    data["modules"] = pagemods.export(conn, vid, with_codes)  # the entries of the pages of the car's integrations
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("vehicle.json", json.dumps(data, ensure_ascii=False))
        for doc in data["tables"]["documents"]:
            path = config.files_dir() / str(vid) / f"{doc['id']}{Path(doc['filename']).suffix.lower()}"
            if path.is_file():
                zf.write(path, f"files/documents/{path.name}")
        for item in data["tables"]["vehicle_media"]:
            path = media.folder(vid) / Path(item["file"]).name
            if path.is_file():
                zf.write(path, f"files/media/{path.name}")
            still = media.poster_of(vid, item)
            if still.is_file():
                zf.write(still, f"files/media/{still.name}")
        if data["tables"]["manuals"] and manual.folder(vid).is_dir():  # page images of the manual (already compressed: stored as they are)
            for path in sorted(manual.folder(vid).iterdir()):
                if path.is_file():
                    zf.write(path, f"files/manual/{path.name}", compress_type=zipfile.ZIP_STORED)
        if appicon.custom_path(vid).is_file():  # the car's own app icon
            zf.write(appicon.custom_path(vid), "files/icon.png")
    return buffer.getvalue()


def _clean(row: dict, columns: set[str]) -> dict:
    """Only columns this app knows, only plain values."""
    return {k: v for k, v in row.items() if k in columns and k != "id" and isinstance(v, SCALARS)}


def _insert(conn: sqlite3.Connection, table: str, values: dict) -> int:
    cols = list(values)
    return conn.execute(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})", list(values.values())).lastrowid


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def read(raw: bytes) -> tuple[dict, zipfile.ZipFile]:
    if len(raw) > MAX_BYTES:
        raise VehicleBackupError("err.backup_big")
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
        names = zf.namelist()
        if "vehicle.json" not in names or not all(_safe(n) for n in names):
            raise VehicleBackupError("err.vb_invalid")
        data = json.loads(zf.read("vehicle.json"))
    except (zipfile.BadZipFile, ValueError, KeyError):
        raise VehicleBackupError("err.vb_invalid") from None
    if not isinstance(data, dict) or data.get("app") != "carassistant" or not isinstance(data.get("vehicle"), dict):
        raise VehicleBackupError("err.vb_invalid")
    if data.get("kind") != "vehicle":
        raise VehicleBackupError("err.vb_kind")  # the backup of the whole system belongs under Settings -> System
    if int(data.get("format", 1)) > FORMAT:
        raise VehicleBackupError("err.vb_newer")  # made by a newer app: update this one first
    return data, zf


def find_existing(conn: sqlite3.Connection, data: dict) -> sqlite3.Row | None:
    """The car on this system that the backup belongs to: the same identity, or else the same name."""
    uid = data["vehicle"].get("uid")
    if isinstance(uid, str) and uid:
        found = conn.execute("SELECT * FROM vehicles WHERE uid = ?", (uid,)).fetchone()
        if found:
            return found
    name = str(data["vehicle"].get("name") or "").strip().lower()
    return conn.execute("SELECT * FROM vehicles WHERE lower(name) = ?", (name,)).fetchone() if name else None


def summary(data: dict) -> dict:
    """What a backup holds, for the question 'replace or copy?'."""
    tables = data.get("tables") if isinstance(data.get("tables"), dict) else {}
    return {
        "name": str(data["vehicle"].get("name") or ""),
        "created": str(data.get("created") or "")[:10],
        "version": str(data.get("version") or ""),
        "counts": {k: len(v) for k, v in tables.items() if isinstance(v, list) and v and k not in ("trip_points", "live")},
    }


def restore(conn: sqlite3.Connection, raw: bytes) -> int:
    """Create a NEW vehicle (as a copy: a taken name gets a number, so does its address) and return its id."""
    data, zf = read(raw)
    with zf:
        vcols = _columns(conn, "vehicles")
        values = _clean(data["vehicle"], vcols)
        for forbidden in ("slug", "media_id", "photo_id", "uid"):
            values.pop(forbidden, None)
        name = str(values.get("name") or "").strip()[:80]
        if not name:
            raise VehicleBackupError("err.vb_invalid")
        taken = {r["name"].lower() for r in conn.execute("SELECT name FROM vehicles")}
        base, n = name, 2
        while name.lower() in taken:
            name, n = f"{base} {n}", n + 1
        values["name"] = name
        values["uid"] = secrets.token_hex(8)  # a copy is a new car
        values.setdefault("created_at", datetime.now(UTC).isoformat(timespec="seconds"))
        new_id = _insert(conn, "vehicles", values)
        conn.execute("UPDATE vehicles SET slug = ? WHERE id = ?", (slugs.unique(conn, name, new_id), new_id))
        _fill(conn, zf, data, new_id)
    return new_id


def _wipe(conn: sqlite3.Connection, vid: int) -> None:
    """Everything of one car except the vehicle row itself (its id and address stay)."""
    from . import manual, media

    conn.execute("DELETE FROM trip_points WHERE trip_id IN (SELECT id FROM trips WHERE vehicle_id = ?)", (vid,))
    for table in LISTS:
        conn.execute(f"DELETE FROM {table} WHERE vehicle_id = ?", (vid,))
    conn.execute("DELETE FROM api_tokens WHERE vehicle_id = ?", (vid,))
    conn.execute("DELETE FROM vehicle_addons WHERE vehicle_id = ?", (vid,))
    conn.execute("DELETE FROM module_rows WHERE vehicle_id = ?", (vid,))
    for prefix in SETTINGS:
        conn.execute("DELETE FROM settings WHERE key = ?", (f"{prefix}.{vid}",))
    shutil.rmtree(config.files_dir() / str(vid), ignore_errors=True)
    shutil.rmtree(media.folder(vid), ignore_errors=True)
    shutil.rmtree(manual.folder(vid), ignore_errors=True)
    appicon.reset(vid)


def replace(conn: sqlite3.Connection, raw: bytes, vid: int) -> int:
    """Put the backup's data into an EXISTING car. A copy of its current state is saved first (data/backups, the last three are kept)."""
    data, zf = read(raw)
    with zf:
        row = conn.execute("SELECT id, slug FROM vehicles WHERE id = ?", (vid,)).fetchone()
        if row is None:
            raise VehicleBackupError("err.vb_missing")
        safety = config.data_dir() / "backups"
        safety.mkdir(exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        (safety / f"vehicle-{row['slug'] or vid}-before-restore-{stamp}.zip").write_bytes(export(conn, vid, with_codes=True))
        for old in sorted(safety.glob(f"vehicle-{row['slug'] or vid}-before-restore-*.zip"))[:-3]:
            old.unlink()
        values = _clean(data["vehicle"], _columns(conn, "vehicles"))
        for forbidden in ("slug", "media_id", "photo_id", "uid", "created_at"):
            values.pop(forbidden, None)
        if values.get("name"):
            conn.execute("UPDATE vehicles SET " + ", ".join(f"{k} = ?" for k in values) + " WHERE id = ?", [*values.values(), vid])
        _wipe(conn, vid)
        _fill(conn, zf, data, vid)
    return vid


def _fill(conn: sqlite3.Connection, zf: zipfile.ZipFile, data: dict, new_id: int) -> None:
    """The lists, files, settings, tokens, integrations and plugins of a backup into car ``new_id``."""
    from . import addons, manual, media

    tables = data.get("tables") if isinstance(data.get("tables"), dict) else {}
    ids: dict[str, dict] = {"trips": {}, "documents": {}, "vehicle_media": {}}
    for table in LISTS:
        columns = _columns(conn, table)
        for row in (tables.get(table) or [])[:MAX_ROWS]:
            if not isinstance(row, dict):
                continue
            clean = _clean(row, columns)
            clean["vehicle_id"] = new_id
            if table == "live":
                conn.execute("INSERT OR REPLACE INTO live (vehicle_id, key, value, updated) VALUES (?,?,?,?)",
                             (new_id, clean.get("key"), clean.get("value"), clean.get("updated") or ""))  # fmt: skip
                continue
            new_row = _insert(conn, table, clean)
            if table in ids and isinstance(row.get("id"), int):
                ids[table][row["id"]] = new_row
    point_cols = _columns(conn, "trip_points")
    for row in (tables.get("trip_points") or [])[:MAX_ROWS]:
        if isinstance(row, dict) and row.get("trip_id") in ids["trips"]:
            clean = _clean(row, point_cols)
            clean["trip_id"] = ids["trips"][row["trip_id"]]
            _insert(conn, "trip_points", clean)

    # files: documents are stored by their new id, media by their (unchanged) file name
    for old_id, new_doc in ids["documents"].items():
        doc = next((d for d in tables.get("documents", []) if d.get("id") == old_id), None)
        ext = Path(str(doc.get("filename") or "")).suffix.lower() if doc else ""
        src = f"files/documents/{old_id}{ext}"
        if src in zf.namelist():
            folder = config.files_dir() / str(new_id)
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{new_doc}{ext}").write_bytes(zf.read(src))
    for item in tables.get("vehicle_media", []):
        src = f"files/media/{Path(str(item.get('file') or '')).name}"
        if src in zf.namelist():
            (media.folder(new_id) / Path(src).name).write_bytes(zf.read(src))
            still = f"{src}.poster.jpg"
            if still in zf.namelist():
                (media.folder(new_id) / Path(still).name).write_bytes(zf.read(still))
    pages = {Path(n).name for n in zf.namelist() if n.startswith("files/manual/")}
    if tables.get("manuals") and pages:  # the images of the manual; only plain page numbers with a known picture ending
        target = manual.folder(new_id)
        target.mkdir(parents=True, exist_ok=True)
        for name in pages:
            stem, _, ext = name.partition(".")
            if stem.isdigit() and ext in manual.IMAGE_EXT:
                (target / name).write_bytes(zf.read(f"files/manual/{name}"))
    if "files/icon.png" in zf.namelist():
        appicon.custom_path(new_id).write_bytes(zf.read("files/icon.png"))
        appicon.clear_cache()
    # the choices of the car (Dashboard picture, list photo) follow the new media ids
    old = data["vehicle"]
    conn.execute(
        "UPDATE vehicles SET media_id = ?, photo_id = ? WHERE id = ?",
        (ids["vehicle_media"].get(old.get("media_id")), ids["vehicle_media"].get(old.get("photo_id")), new_id),
    )

    for prefix, value in (data.get("settings") or {}).items():
        if prefix in SETTINGS and isinstance(value, str):
            conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)", (f"{prefix}.{new_id}", value))

    # connection tokens: the same hash again, so the plugin keeps working with the token it has - unless this system already knows it
    token_ids: dict[int, int | None] = {}
    for tok in data.get("tokens") or []:
        if not isinstance(tok, dict) or not isinstance(tok.get("token_hash"), str):
            continue
        if conn.execute("SELECT 1 FROM api_tokens WHERE token_hash = ?", (tok["token_hash"],)).fetchone():
            token_ids[tok.get("id")] = None
            continue
        new_token = conn.execute(
            "INSERT INTO api_tokens(name, token_hash, vehicle_id, created_at) VALUES(?,?,?,?)",
            (str(tok.get("name") or "")[:40], tok["token_hash"], new_id, str(tok.get("created_at") or "")),
        ).lastrowid
        token_ids[tok.get("id")] = new_token
        if isinstance(tok.get("token"), str):
            from . import connectors

            connectors.remember(conn, new_token, tok["token"])  # only kept when it really is the token of that fingerprint
    addons.restore_all(conn, new_id, data.get("addons") or [], token_ids)
    from . import pagemods

    pagemods.restore(conn, new_id, data.get("modules"))
