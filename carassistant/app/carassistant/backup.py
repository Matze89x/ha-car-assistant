"""Backup & restore of the whole database plus uploaded files as a single zip.

Home Assistant also includes ``/data`` in its own backups (the app uses ``backup: cold`` so SQLite is consistent);
this export is for moving data between installations or keeping an off-site copy.
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

from . import __version__, config, db

MAX_RESTORE_BYTES = 500 * 1024 * 1024
FORMAT = 1  # layout of this backup. From version 1.0 on every newer app restores every older format (see docs/backup.md).


class BackupError(ValueError):
    pass


def create() -> bytes:
    buffer = io.BytesIO()
    with tempfile.TemporaryDirectory() as tmp:
        snapshot = Path(tmp) / "carassistant.db"
        src = db.connect()
        try:
            dst = sqlite3.connect(snapshot)
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "manifest.json",
                json.dumps(
                    {"app": "carassistant", "kind": "system", "format": FORMAT, "version": __version__, "schema": len(db.MIGRATIONS),
                     "created": datetime.now(UTC).isoformat(timespec="seconds")}
                ),
            )  # fmt: skip
            zf.write(snapshot, "carassistant.db")
            for path in sorted(config.files_dir().rglob("*")):
                if path.is_file() and "icons/cache" not in path.as_posix():
                    zf.write(path, f"files/{path.relative_to(config.files_dir()).as_posix()}")
    return buffer.getvalue()


def _safe_member(name: str) -> bool:
    p = PurePosixPath(name)
    return not p.is_absolute() and ".." not in p.parts and (name in ("manifest.json", "carassistant.db") or p.parts[0] == "files")


def restore(data: bytes) -> None:
    """Replace the current database and files. A safety copy of the current state is stored first."""
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
