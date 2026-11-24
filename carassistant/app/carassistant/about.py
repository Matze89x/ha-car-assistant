"""Data for the About page: versions, storage, what is installed per vehicle, who made what."""

from __future__ import annotations

import platform
import sqlite3
from importlib import metadata
from pathlib import Path

from . import STAGE, __version__, addons, config, integrations, regional

AUTHOR = "Matze89x"
AUTHOR_URL = "https://github.com/Matze89x"
PROJECT_URL = "https://github.com/Matze89x/ha-car-assistant"
SUPPORT_URL = "https://ko-fi.com/matze89x"  # a coffee; shown only on this page

# every table holding entries of a car (counted for the "entries" figure)
ENTRY_TABLES = ("fuel", "service", "tasks", "tires", "mods", "parts", "documents", "counters", "trips", "appointments", "odometer")
LIBRARIES = (
    "fastapi",
    "jinja2",
    "uvicorn",
    "pillow",
    "webauthn",
    "cryptography",
    "pywebpush",
    "requests",
    "fpdf2",
    "paho-mqtt",
    "pypdf",
    "defusedxml",
    "python-multipart",
)
CREDITS = (
    ("Material Design Icons", "Pictogrammers", "Apache-2.0"),
    ("Space Grotesk · Space Mono", "Florian Karsten · Colophon", "OFL-1.1"),
    ("Leaflet", "Vladimir Agafonkin", "BSD-2-Clause"),
    ("OpenStreetMap", "OpenStreetMap contributors", "ODbL"),
    ("GeoNames (place names)", "GeoNames contributors", "CC BY 4.0"),
)


def _size(path: Path) -> int:
    try:
        if path.is_file():
            return path.stat().st_size
        return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
    except OSError:
        return 0


def human(num: int) -> str:
    """A size as people read it (``472.0 KB``, in German ``472,0 KB``)."""
    value = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            text = f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
            return text.replace(".", ",") if config.language() == "de" else text
        value /= 1024
    return ""


def _versions() -> list[dict]:
    out = []
    for name in LIBRARIES:
        try:
            out.append({"name": name, "version": metadata.version(name)})
        except metadata.PackageNotFoundError:
            continue
    return out


def _counts(conn: sqlite3.Connection) -> dict[int, int]:
    """Entries per vehicle: one grouped query per table instead of one per car and table."""
    total: dict[int, int] = {}
    for table in ENTRY_TABLES:
        try:
            for r in conn.execute(f"SELECT vehicle_id, COUNT(*) AS n FROM {table} GROUP BY vehicle_id"):
                total[r["vehicle_id"]] = total.get(r["vehicle_id"], 0) + r["n"]
        except sqlite3.Error:
            continue
    return total


def _vehicle(conn: sqlite3.Connection, row: sqlite3.Row, counts: dict[int, int]) -> dict:
    items = []
    for a in addons.list_for(conn, row["id"]):
        used = None
        if a["token_id"]:
            token = conn.execute("SELECT last_used FROM api_tokens WHERE id = ?", (a["token_id"],)).fetchone()
            used = token["last_used"] if token else None
        m = a["m"]
        items.append(
            {
                "kind": a["kind"],
                "name": m.get("name") or a["addon_id"],
                "version": m.get("version") or "",
                "author": m.get("author") or "",
                "homepage": m.get("homepage") or "",
                "configured": a["status"] == "configured",
                "last_used": regional.fdatetime(used),
            }
        )
    return {
        "name": row["name"],
        "slug": row["slug"] or row["id"],
        "entries": counts.get(row["id"], 0),
        "items": items,
    }


def _global() -> list[dict]:
    out = []
    for i in integrations.INTEGRATIONS:
        out.append({"key": i.key, "on": integrations.is_enabled(i.key), "link": i.link, "category": i.category})
    return out


def collect(conn: sqlite3.Connection) -> dict:
    db = config.db_path()
    counts = _counts(conn)
    vehicles = [_vehicle(conn, r, counts) for r in conn.execute("SELECT id, name, slug FROM vehicles WHERE archived = 0 ORDER BY id")]
    db_bytes = _size(db) + _size(db.with_name(db.name + "-wal"))
    files_bytes = _size(config.files_dir())
    try:
        migrations = conn.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.Error:
        migrations = 0
    return {
        "version": __version__,
        "stage": STAGE,
        "vehicles": vehicles,
        "plugins": sum(1 for v in vehicles for i in v["items"] if i["kind"] == "plugin"),
        "addons": sum(len(v["items"]) for v in vehicles),
        "entries": sum(v["entries"] for v in vehicles),
        "db": human(db_bytes),
        "files": human(files_bytes),
        "schema": migrations,
        "python": platform.python_version(),
        "libraries": _versions(),
        "global": _global(),
        "credits": CREDITS,
        "author": AUTHOR,
        "author_url": AUTHOR_URL,
        "project_url": PROJECT_URL,
        "support_url": SUPPORT_URL,
    }
