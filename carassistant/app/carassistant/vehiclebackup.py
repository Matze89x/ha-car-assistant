"""Backup and restore of ONE vehicle (everything that belongs to that car only), separate from the backup of the whole system (backup.py).

A vehicle backup is a zip: ``vehicle.json`` (the data), ``files/`` (documents, photos, videos) and - when the person chose a passphrase -
``secrets.enc`` (tokens, passwords, access keys and codes of that car, encrypted: backupsecrets.py). It holds the vehicle, all its lists (service,
fuel, charging sessions, trips with their route, ...), its live values, its settings, its connection tokens (as the hash the server keeps, so a
plugin keeps working with the token it already has) and its integrations and plugins with their settings and where each came from (source,
version, checksum, whether it was running) - but NOT the packages themselves: a restore fetches them again from their source (restoresetup.py).
Restored as a NEW vehicle (or into the car it belongs to).

Compatibility: ``format`` is the layout. Every newer app restores every older format (``MIN_FORMAT`` .. ``FORMAT``; tests/test_backup_compat.py restores
the golden file of each one); a backup from a newer app is refused with a hint to update. The reader ignores columns it does not know and fills
missing ones with their default, so small additions never break an old backup.
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

from . import __version__, appicon, backupsecrets, config, slugs, vault

FORMAT = 2  # 2: more tables of a car, every setting of a car, where a package came from, secrets in a passphrase block
MIN_FORMAT = 1
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
    "fixed_costs",
    "parts",
    "documents",
    "vehicle_media",
    "equipment",
    "manuals",
    "manual_chapters",
    "manual_pages",
    "live",
    "charge_sessions",  # the fuel_id of a session follows the new id of its refuel (see _fill)
    "trip_summaries",
    "vehicle_events",
    "vehicle_track",
    "vehicle_signals",
    "signal_state",
    "signal_history",
    "plugin_usage",
)
SETTINGS = (
    "home.widgets",
    "nav.slots",
    "modules.off",
    "debug",
    "interval",
    "equipment.order",
    "charge.home_price",
    "manual.last",
)  # per-vehicle settings: "<prefix>.<vehicle id>"; tests/test_backup_compat.py checks that every such key of the code is here or in SETTINGS_SKIPPED
SETTINGS_SKIPPED = {
    "sim.token": "the token of the demo player: made again when it is switched on",
    "mqtt.notice": "what was last announced to Home Assistant: made again",
}

# Every table of the database is named in exactly one of these places (a test checks it, so a new table cannot be forgotten):
HANDLED = frozenset(
    {
        "vehicles",
        "api_tokens",
        "vehicle_addons",
        "module_rows",
        "settings",
        "trip_points",
        "addon_deliveries",
        "connections",
        "connection_links",
        "ha_bindings",
        "field_claims",
    }
)  # taken care of by name in export / _fill / _wipe (a connection: only its tokens in the secrets block; the claims are made again from the bindings)
SKIPPED_TABLES = {
    "vehicle_logs": "log lines of the plugins (kept for 7 days)",
    "vehicle_traffic": "the traffic view of a plugin while debug is on (kept for 7 days)",
    "oauth_pending": "a login with an account that has begun and is good for ten minutes",
}
SYSTEM_TABLES = frozenset(  # people, devices and the packages' sources: part of the backup of the whole system only
    {
        "auth_challenges", "mcp_keys", "mcp_log", "notify_energy", "notify_log", "notify_state", "passkeys", "place_names",
        "push_device_cars", "push_devices", "recovery_codes", "sessions", "source_cache", "source_packages", "sources", "user_notify",
        "user_notify_vehicle", "user_prefs", "users",
    }
)  # fmt: skip
SCALARS = (str, int, float, type(None))


class VehicleBackupError(ValueError):
    """The file is not a usable vehicle backup; the message is an i18n key."""


def _rows(conn: sqlite3.Connection, sql: str, args: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def _safe(name: str) -> bool:
    p = PurePosixPath(name)
    return (
        not p.is_absolute()
        and ".." not in p.parts
        and (name in ("vehicle.json", backupsecrets.NAME, backupsecrets.LOCAL_NAME) or p.parts[0] == "files")
    )


def export(conn: sqlite3.Connection, vid: int, with_codes: bool = False, passphrase: str | None = None, local: bool = False) -> bytes:
    """The backup of one car as a zip. Without ``passphrase`` it holds no secret (no kept token, no password, no key, no access code unless the older
    ``with_codes`` is asked for); with one, all of them travel in the block ``secrets.enc``. ``local`` is for the safety copy that stays on this system:
    the same block, sealed with this system's key instead (``secrets.sys``)."""
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

    secret: dict | None = (
        {"v": 1, "tokens": {}, "addons": {}, "source_keys": {}, "approvals": {}, "connections": {}, "modules": None}
        if (passphrase or local)
        else None
    )
    for tok in data["tokens"]:  # the hash is no secret (it opens nothing); the kept token itself goes into the secrets block only
        kept = connectors.remembered(conn, tok["id"])
        if kept and secret is not None:
            secret["tokens"][str(tok["id"])] = kept
    for a in conn.execute(
        "SELECT a.*, COALESCE(s.url, a.source_url) AS origin, s.name AS source_name FROM vehicle_addons a "
        "LEFT JOIN sources s ON s.id = a.source_id WHERE a.vehicle_id = ? ORDER BY a.id",
        (vid,),
    ):
        manifest = json.loads(a["manifest"])
        if secret is not None:
            passwords = {f["key"] for f in manifest.get("settings", []) if f.get("type") == "password"}
            kept = {k: vault.decrypt(v) for k, v in json.loads(a["settings"] or "{}").items() if k in passwords and isinstance(v, str)}
            if any(kept.values()):
                secret["addons"][a["addon_id"]] = {k: v for k, v in kept.items() if v}
            from . import addons as _addons

            fingerprint = _addons.approval_fingerprint(manifest)
            if (
                fingerprint and a["svc_ok"] == fingerprint and a["pkg_sha"]
            ):  # what an administrator approved: the same package may be approved again (restoresetup.py)
                secret["approvals"][a["addon_id"]] = {"svc_ok": fingerprint, "pkg_sha": a["pkg_sha"]}
            from . import oauth

            if logins := oauth.export(
                conn, a["id"]
            ):  # the tokens of a login with an account: the person need not log in again after a restore
                secret["connections"][a["addon_id"]] = logins
            if a["origin"] and a["source_id"]:
                key = vault.decrypt(
                    (conn.execute("SELECT token FROM sources WHERE id = ?", (a["source_id"],)).fetchone() or {"token": None})["token"]
                )
                if key:
                    secret["source_keys"][a["origin"]] = key
        data["addons"].append(
            {
                "id": a["id"],  # the number it had here: the files it handed out (addon_deliveries) point to it
                "addon_id": a["addon_id"],
                "kind": a["kind"],
                "manifest": manifest,
                "settings": {  # a password (login data of a web service, ...) travels only in the passphrase block, never in the plain file
                    k: v
                    for k, v in json.loads(a["settings"] or "{}").items()
                    if k not in {f["key"] for f in manifest.get("settings", []) if f.get("type") == "password"}
                },
                "status": a["status"],
                "active": bool(a["active"]),
                "token_id": a["token_id"],
                "source_url": a["origin"],  # (format 1 only knew this)
                "source": {"url": a["origin"], "name": a["source_name"] or ""} if a["origin"] else None,
                "version": str(manifest.get("version") or ""),
                "pkg_sha": a["pkg_sha"],
            }
        )
    data["tables"]["addon_deliveries"] = _rows(
        conn, "SELECT d.* FROM addon_deliveries d JOIN vehicle_addons a ON a.id = d.addon_pk WHERE a.vehicle_id = ?", (vid,)
    )
    data["tables"]["ha_bindings"] = (
        _rows(  # the entities of Home Assistant a plugin reads for this car (the interfaces they take follow from them)
            conn, "SELECT b.* FROM ha_bindings b JOIN vehicle_addons a ON a.id = b.addon_pk WHERE a.vehicle_id = ?", (vid,)
        )
    )
    from . import pagemods

    data["modules"] = pagemods.export(conn, vid, with_codes)  # the entries of the pages of the car's integrations
    if secret is not None:
        secret["modules"] = pagemods.export(conn, vid, True)  # the same entries WITH their access codes
    data["secrets"] = secret is not None
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("vehicle.json", json.dumps(data, ensure_ascii=False))
        if secret is not None:
            if passphrase:
                zf.writestr(backupsecrets.NAME, backupsecrets.seal(secret, passphrase))
            else:
                zf.writestr(backupsecrets.LOCAL_NAME, backupsecrets.seal_local(secret))
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
    return _upgrade(data), zf


def _upgrade(data: dict) -> dict:
    """A backup of an older format in the shape of the current one. Format 1 -> 2: an add-on says where it came from as ``source``; what the old
    format did not know (activity, checksum, more tables) stays absent and is filled with its default when it is read."""
    for entry in data.get("addons") or []:
        if isinstance(entry, dict) and not entry.get("source") and isinstance(entry.get("source_url"), str) and entry["source_url"]:
            entry["source"] = {"url": entry["source_url"], "name": ""}
    return data


def secrets_state(zf: zipfile.ZipFile) -> str:
    """What a file says about secrets: ``none`` | ``passphrase`` (a block that needs one) | ``local`` (sealed by this system's key, opens only here)."""
    names = zf.namelist()
    if backupsecrets.NAME in names:
        return "passphrase"
    return "local" if backupsecrets.LOCAL_NAME in names else "none"


def open_secrets(zf: zipfile.ZipFile, passphrase: str = "") -> dict | None:
    """The secrets of a file, or None (none in it, no passphrase given, or a local block of another system). A wrong passphrase is an error."""
    names = zf.namelist()
    if backupsecrets.LOCAL_NAME in names:
        payload = backupsecrets.unseal_local(zf.read(backupsecrets.LOCAL_NAME))
        if payload is not None:
            return payload
    if backupsecrets.NAME in names and passphrase:
        try:
            return backupsecrets.unseal(zf.read(backupsecrets.NAME), backupsecrets.clean(passphrase))
        except backupsecrets.WrongPassphrase:
            raise VehicleBackupError("err.bk_passphrase") from None
    return None


def load(raw: bytes, passphrase: str = "") -> tuple[dict, dict | None]:
    """The data and the secrets (None when there are none or no passphrase) of a backup file, as ``restore`` sees them."""
    data, zf = read(raw)
    with zf:
        return data, open_secrets(zf, passphrase)


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


def restore(conn: sqlite3.Connection, raw: bytes, passphrase: str = "") -> int:
    """Create a NEW vehicle (as a copy: a taken name gets a number, so does its address) and return its id. With the right ``passphrase`` the secrets of
    the file come back as well (tokens, passwords, keys, codes); without it they are left out."""
    data, zf = read(raw)
    with zf:
        secrets_found = open_secrets(zf, passphrase)
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
        _fill(conn, zf, data, new_id, secrets_found)
    return new_id


def _wipe(conn: sqlite3.Connection, vid: int) -> None:
    """Everything of one car except the vehicle row itself (its id and address stay)."""
    from . import manual, media

    conn.execute("DELETE FROM trip_points WHERE trip_id IN (SELECT id FROM trips WHERE vehicle_id = ?)", (vid,))
    for table in LISTS:
        conn.execute(f"DELETE FROM {table} WHERE vehicle_id = ?", (vid,))
    conn.execute("DELETE FROM api_tokens WHERE vehicle_id = ?", (vid,))
    conn.execute("DELETE FROM addon_deliveries WHERE addon_pk IN (SELECT id FROM vehicle_addons WHERE vehicle_id = ?)", (vid,))
    conn.execute("DELETE FROM ha_bindings WHERE addon_pk IN (SELECT id FROM vehicle_addons WHERE vehicle_id = ?)", (vid,))
    conn.execute("DELETE FROM field_claims WHERE vehicle_id = ?", (vid,))
    conn.execute("DELETE FROM vehicle_addons WHERE vehicle_id = ?", (vid,))
    from . import oauth

    oauth.prune(conn)  # (the links went with the installs; the tokens nobody uses any more go now)
    conn.execute("DELETE FROM module_rows WHERE vehicle_id = ?", (vid,))
    for prefix in SETTINGS:
        conn.execute("DELETE FROM settings WHERE key = ?", (f"{prefix}.{vid}",))
    shutil.rmtree(config.files_dir() / str(vid), ignore_errors=True)
    shutil.rmtree(media.folder(vid), ignore_errors=True)
    shutil.rmtree(manual.folder(vid), ignore_errors=True)
    appicon.reset(vid)


def replace(conn: sqlite3.Connection, raw: bytes, vid: int, passphrase: str = "") -> int:
    """Put the backup's data into an EXISTING car. A copy of its current state is saved first (data/backups, the last three are kept)."""
    data, zf = read(raw)
    with zf:
        secrets_found = open_secrets(zf, passphrase)
        row = conn.execute("SELECT id, slug FROM vehicles WHERE id = ?", (vid,)).fetchone()
        if row is None:
            raise VehicleBackupError("err.vb_missing")
        safety = config.data_dir() / "backups"
        safety.mkdir(exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        (safety / f"vehicle-{row['slug'] or vid}-before-restore-{stamp}.zip").write_bytes(export(conn, vid, with_codes=True, local=True))
        for old in sorted(safety.glob(f"vehicle-{row['slug'] or vid}-before-restore-*.zip"))[:-3]:
            old.unlink()
        values = _clean(data["vehicle"], _columns(conn, "vehicles"))
        for forbidden in ("slug", "media_id", "photo_id", "uid", "created_at"):
            values.pop(forbidden, None)
        if values.get("name"):
            conn.execute("UPDATE vehicles SET " + ", ".join(f"{k} = ?" for k in values) + " WHERE id = ?", [*values.values(), vid])
        _wipe(conn, vid)
        _fill(conn, zf, data, vid, secrets_found)
    return vid


def _fill(conn: sqlite3.Connection, zf: zipfile.ZipFile, data: dict, new_id: int, secret: dict | None = None) -> None:
    """The lists, files, settings, tokens, integrations and plugins of a backup into car ``new_id``. ``secret`` is what its secrets block held."""
    secret = secret or {}
    from . import addons, manual, media

    tables = data.get("tables") if isinstance(data.get("tables"), dict) else {}
    ids: dict[str, dict] = {"trips": {}, "documents": {}, "vehicle_media": {}, "fuel": {}}
    for table in LISTS:
        columns = _columns(conn, table)
        for row in (tables.get(table) or [])[:MAX_ROWS]:
            if not isinstance(row, dict):
                continue
            clean = _clean(row, columns)
            clean["vehicle_id"] = new_id
            if table == "charge_sessions":  # the refuel it was made into has a new number now (fuel comes first in LISTS)
                clean["fuel_id"] = ids["fuel"].get(row.get("fuel_id"))
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
        kept = (secret.get("tokens") or {}).get(str(tok.get("id"))) or tok.get("token")  # (format 1 carried the kept token readable)
        if isinstance(kept, str) and kept:
            from . import connectors

            connectors.remember(conn, new_token, kept)  # only kept when it really is the token of that fingerprint
    addon_ids = addons.restore_all(conn, new_id, data.get("addons") or [], token_ids, secret.get("addons"))
    from . import oauth

    for package_id, logins in (
        secret.get("connections") or {}
    ).items():  # the logins with an account of the car come back with their tokens
        oauth.restore(conn, new_id, str(package_id), logins)
    delivered = _columns(conn, "addon_deliveries")
    for row in (tables.get("addon_deliveries") or [])[:MAX_ROWS]:  # which files of a package were handed out, and when
        if isinstance(row, dict) and row.get("addon_pk") in addon_ids:
            clean = _clean(row, delivered)
            clean["addon_pk"] = addon_ids[row["addon_pk"]]
            conn.execute(
                "INSERT OR REPLACE INTO addon_deliveries(addon_pk, name, version, delivered_at, settings_hash) VALUES(?,?,?,?,?)",
                (
                    clean["addon_pk"],
                    clean.get("name") or "",
                    clean.get("version") or "",
                    clean.get("delivered_at") or "",
                    clean.get("settings_hash") or "",
                ),
            )
    from . import claims, habridge

    restored: dict[int, dict[str, dict]] = {}
    for row in (tables.get("ha_bindings") or [])[
        :MAX_ROWS
    ]:  # the entities of Home Assistant a plugin reads: each one is checked again, the file may be from anywhere
        if isinstance(row, dict) and row.get("addon_pk") in addon_ids:
            binding = habridge.clean_stored(row.get("slot"), row.get("entity"), row.get("options"))
            if binding is not None:
                restored.setdefault(addon_ids[row["addon_pk"]], {})[row["slot"]] = binding
    for pk, bound in restored.items():
        for slot, binding in bound.items():
            conn.execute(
                "INSERT OR REPLACE INTO ha_bindings(addon_pk, slot, entity, options) VALUES(?,?,?,?)",
                (pk, slot, binding["entity"], json.dumps(binding["options"], sort_keys=True)),
            )
        claims.register(
            conn, new_id, pk, habridge.fields_bound(bound)
        )  # what it reads is taken for it again (it starts off, like every restored plugin)
    from . import pagemods

    pagemods.restore(conn, new_id, secret["modules"] if isinstance(secret.get("modules"), list) else data.get("modules"))
