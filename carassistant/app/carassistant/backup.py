"""Backup & restore of the whole database plus uploaded files as a single zip.

Home Assistant also includes ``/data`` in its own backups (the app uses ``backup: cold`` so SQLite is consistent);
this export is for moving data between installations or keeping an off-site copy.

The secrets of the database (kept tokens, passwords of plugins, access keys of sources, access codes, the push key) are sealed with the key of THIS system
(vault.py), which is not in a backup. With a passphrase they leave the copy of the database and travel in one block of their own, ``secrets.enc``
(backupsecrets.py): a restore on another system then brings them back. Without a passphrase the file holds no secret that anyone could read.
Compatibility: every newer app restores every older format (``MIN_FORMAT`` .. ``FORMAT``, tests/test_backup_compat.py); an older database is
brought up to date by the migrations.
"""

from __future__ import annotations

import io
import json
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from . import __version__, backupsecrets, config, db

MAX_RESTORE_BYTES = 500 * 1024 * 1024
FORMAT = (
    2  # layout of this backup (2: the secrets in a block with a passphrase). Every newer app restores every older format (docs/backup.md).
)
MIN_FORMAT = 1


class BackupError(ValueError):
    pass


def secrets_state(data: bytes) -> str:
    """``passphrase`` when the file holds a secrets block (its passphrase is needed to bring the secrets back), else ``none``."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            return "passphrase" if backupsecrets.NAME in zf.namelist() else "none"
    except zipfile.BadZipFile:
        return "none"


def create(passphrase: str | None = None) -> bytes:
    """The backup as a zip. With a ``passphrase`` (at least ``backupsecrets.MIN_LENGTH`` characters) the secrets travel in the block ``secrets.enc``."""
    if passphrase and len(backupsecrets.clean(passphrase)) < backupsecrets.MIN_LENGTH:
        raise BackupError("err.bk_short")
    buffer = io.BytesIO()
    block = None
    with tempfile.TemporaryDirectory() as tmp:
        snapshot = Path(tmp) / "carassistant.db"
        src = db.connect()
        try:
            dst = sqlite3.connect(snapshot)
            try:
                src.backup(dst)
                dst.execute("DELETE FROM source_cache")  # (what was read from the sources is read again when needed)
                if passphrase:
                    dst.row_factory = sqlite3.Row
                    block = backupsecrets.seal(_take_secrets(dst), passphrase)
                    dst.row_factory = None
                    dst.commit()
                    dst.execute("VACUUM")  # the old values would still lie in the freed pages of the file
                dst.commit()
            finally:
                dst.close()
        finally:
            src.close()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "manifest.json",
                json.dumps(
                    {"app": "carassistant", "kind": "system", "format": FORMAT, "version": __version__, "schema": len(db.MIGRATIONS),
                     "created": datetime.now(UTC).isoformat(timespec="seconds"), "secrets": block is not None}
                ),
            )  # fmt: skip
            if block is not None:
                zf.writestr(backupsecrets.NAME, block)
            zf.write(snapshot, "carassistant.db")
            for path in sorted(config.files_dir().rglob("*")):
                if path.is_file() and "icons/cache" not in path.as_posix():
                    zf.write(path, f"files/{path.relative_to(config.files_dir()).as_posix()}")
    return buffer.getvalue()


def _safe_member(name: str) -> bool:
    p = PurePosixPath(name)
    return (
        not p.is_absolute()
        and ".." not in p.parts
        and (name in ("manifest.json", "carassistant.db", backupsecrets.NAME) or p.parts[0] == "files")
    )


def _take_secrets(dst: sqlite3.Connection) -> dict:
    """Every secret out of the COPY of the database (it comes back readable here, the copy is left without it): what travels in the secrets block.
    Locations: the kept tokens, the access keys of sources, the passwords in the settings of plugins, sealed settings (the push key), and the access codes
    of the pages of integrations (they are plain in the database)."""
    from . import pagemods, vault

    out: dict = {"v": 1, "api_tokens": {}, "sources": {}, "addon_settings": {}, "settings": {}, "module_rows": {}}
    for row in dst.execute("SELECT id, token_enc FROM api_tokens WHERE token_enc IS NOT NULL").fetchall():
        if text := vault.decrypt(row["token_enc"]):
            out["api_tokens"][str(row["id"])] = text
    dst.execute("UPDATE api_tokens SET token_enc = NULL")
    for row in dst.execute("SELECT id, token FROM sources WHERE token IS NOT NULL").fetchall():
        if text := vault.decrypt(row["token"]):
            out["sources"][str(row["id"])] = text
    dst.execute("UPDATE sources SET token = NULL")
    for row in dst.execute("SELECT id, settings FROM vehicle_addons").fetchall():
        values = json.loads(row["settings"] or "{}")
        sealed = {k: vault.decrypt(v) for k, v in values.items() if isinstance(v, str) and v.startswith(vault.PREFIX)}
        if sealed:
            out["addon_settings"][str(row["id"])] = {k: v for k, v in sealed.items() if v}
            dst.execute(
                "UPDATE vehicle_addons SET settings = ? WHERE id = ?",
                (json.dumps({k: v for k, v in values.items() if k not in sealed}), row["id"]),
            )
    for row in dst.execute("SELECT key, value FROM settings WHERE value LIKE ?", (vault.PREFIX + "%",)).fetchall():
        if text := vault.decrypt(row["value"]):
            out["settings"][row["key"]] = text
        dst.execute("DELETE FROM settings WHERE key = ?", (row["key"],))
    for car in dst.execute("SELECT id FROM vehicles").fetchall():
        secret_fields = pagemods._secrets_of(dst, car["id"])
        for row in dst.execute("SELECT id, addon_id, page, data FROM module_rows WHERE vehicle_id = ?", (car["id"],)).fetchall():
            keys = secret_fields.get((row["addon_id"], row["page"]))
            data = json.loads(row["data"] or "{}") if keys else {}
            moved = {k: data.pop(k) for k in list(data) if k in (keys or ()) and data.get(k)}
            if moved:
                out["module_rows"][str(row["id"])] = moved
                dst.execute("UPDATE module_rows SET data = ? WHERE id = ?", (json.dumps(data), row["id"]))
    return out


def _give_back(conn: sqlite3.Connection, held: dict) -> None:
    """The secrets of a block into the restored database, sealed with the key of THIS system. The numbers are those of the backup: the database came back as it was."""
    from . import connectors, vault

    for key, token in (held.get("api_tokens") or {}).items():
        if str(key).isdigit() and isinstance(token, str):
            connectors.remember(conn, int(key), token)  # only kept when it really is the token of that fingerprint
    for key, text in (held.get("sources") or {}).items():
        if str(key).isdigit() and isinstance(text, str) and text:
            conn.execute("UPDATE sources SET token = ? WHERE id = ?", (vault.encrypt(text), int(key)))
    for key, items in (held.get("addon_settings") or {}).items():
        row = conn.execute("SELECT settings FROM vehicle_addons WHERE id = ?", (int(key),)).fetchone() if str(key).isdigit() else None
        if row and isinstance(items, dict):
            values = json.loads(row["settings"] or "{}")
            values.update({k: vault.encrypt(v) for k, v in items.items() if isinstance(v, str) and v})
            conn.execute("UPDATE vehicle_addons SET settings = ? WHERE id = ?", (json.dumps(values), int(key)))
    for key, text in (held.get("settings") or {}).items():
        if isinstance(key, str) and isinstance(text, str) and text:
            db.set_setting(conn, key, vault.encrypt(text))
    for key, items in (held.get("module_rows") or {}).items():
        row = conn.execute("SELECT data FROM module_rows WHERE id = ?", (int(key),)).fetchone() if str(key).isdigit() else None
        if row and isinstance(items, dict):
            data = json.loads(row["data"] or "{}")
            data.update({str(k)[:31]: str(v)[:20000] for k, v in items.items() if isinstance(v, str | int | float)})
            conn.execute("UPDATE module_rows SET data = ? WHERE id = ?", (json.dumps(data), int(key)))


def restore(data: bytes, passphrase: str = "") -> None:
    """Replace the current database and files. A safety copy of the current state is stored first. With the right ``passphrase`` the secrets of the
    file come back as well; a wrong one stops everything before anything is touched."""
    if len(data) > MAX_RESTORE_BYTES:
        raise BackupError("err.backup_big")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise BackupError("err.backup_invalid") from None
    with zf:
        names = zf.namelist()
        if "manifest.json" not in names or "carassistant.db" not in names or not all(_safe_member(n) for n in names):
            raise BackupError("err.backup_invalid")
        try:
            manifest = json.loads(zf.read("manifest.json"))
        except ValueError:
            raise BackupError("err.backup_invalid") from None
        if manifest.get("kind", "system") != "system":
            raise BackupError("err.backup_kind")  # a vehicle backup belongs on the Add vehicle page
        if (
            manifest.get("app") != "carassistant"
            or int(manifest.get("format", 1)) > FORMAT
            or int(manifest.get("schema", 0)) > len(db.MIGRATIONS)
        ):
            raise BackupError("err.backup_version")
        held = None
        if backupsecrets.NAME in names and passphrase:
            try:
                held = backupsecrets.unseal(zf.read(backupsecrets.NAME), backupsecrets.clean(passphrase))
            except backupsecrets.WrongPassphrase:
                raise BackupError("err.bk_passphrase") from None
        with tempfile.TemporaryDirectory() as tmp:
            tmp_db = Path(tmp) / "carassistant.db"
            tmp_db.write_bytes(zf.read("carassistant.db"))
            check = sqlite3.connect(tmp_db)
            try:
                if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise BackupError("err.backup_invalid")
            except sqlite3.DatabaseError:
                raise BackupError("err.backup_invalid") from None
            finally:
                check.close()

            safety_dir = config.data_dir() / "backups"
            safety_dir.mkdir(exist_ok=True)
            stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
            (safety_dir / f"pre-restore-{stamp}.zip").write_bytes(create())
            for old in sorted(safety_dir.glob("pre-restore-*.zip"))[:-3]:
                old.unlink()

            target = config.db_path()
            for suffix in ("-wal", "-shm"):
                Path(str(target) + suffix).unlink(missing_ok=True)
            shutil.copyfile(tmp_db, target)
            files = config.files_dir()
            shutil.rmtree(files, ignore_errors=True)
            files.mkdir(parents=True, exist_ok=True)
            for name in names:
                if name.startswith("files/") and not name.endswith("/"):
                    dest = files / PurePosixPath(name).relative_to("files")
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(zf.read(name))
    db.migrate()
    from . import connectors

    with db.tx() as conn:
        if held:
            _give_back(conn, held)
        connectors.reseal(conn)  # (a kept token that came in readable, format 1, is sealed with this system's key)
