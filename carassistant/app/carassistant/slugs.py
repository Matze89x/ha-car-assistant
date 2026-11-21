"""Readable vehicle addresses: "My Golf" -> /v/my-golf. Old numeric addresses (/v/1) keep working and redirect."""

from __future__ import annotations

import re
import sqlite3
import unicodedata

_MAP = str.maketrans(
    {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
        "Ä": "ae",
        "Ö": "oe",
        "Ü": "ue",
        "æ": "ae",
        "Æ": "ae",
        "ø": "o",
        "Ø": "o",
        "å": "a",
        "Å": "a",
        "ł": "l",
        "Ł": "l",
        "đ": "d",
        "Đ": "d",
    }
)
_NUMERIC_PATH = re.compile(r"^/v/(\d+)(?=/|$|\?)")


def make_slug(name: str) -> str:
    """Lower case, umlauts and accents resolved, everything else a single hyphen; never empty, never only digits."""
    text = unicodedata.normalize("NFKD", (name or "").translate(_MAP))
    text = "".join(c for c in text if not unicodedata.combining(c))
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40].strip("-")
    if not slug:
        return "car"
    return f"car-{slug}" if slug.isdigit() else slug


def unique(conn: sqlite3.Connection, name: str, exclude_id: int | None = None) -> str:
    base = make_slug(name)
    candidate, n = base, 2
    while conn.execute("SELECT 1 FROM vehicles WHERE slug = ? AND id IS NOT ?", (candidate, exclude_id)).fetchone():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def backfill(conn: sqlite3.Connection) -> None:
    for row in conn.execute("SELECT id, name FROM vehicles WHERE slug IS NULL OR slug = ''").fetchall():
        conn.execute("UPDATE vehicles SET slug = ? WHERE id = ?", (unique(conn, row["name"], row["id"]), row["id"]))


def id_for(conn: sqlite3.Connection, token: str) -> int | None:
    """Vehicle id for a slug or a number from the address."""
    if token.isdigit():
        row = conn.execute("SELECT id FROM vehicles WHERE id = ?", (int(token),)).fetchone()
    else:
        row = conn.execute("SELECT id FROM vehicles WHERE slug = ?", (token,)).fetchone()
    return row["id"] if row else None


def slug_of(conn: sqlite3.Connection, vehicle_id: int) -> str | None:
    row = conn.execute("SELECT slug FROM vehicles WHERE id = ?", (vehicle_id,)).fetchone()
    return (row["slug"] or None) if row else None


def pretty(conn: sqlite3.Connection, path: str) -> str:
    """Replace a numeric vehicle in a path (/v/3/e/fuel) by its slug; anything else stays as it is."""
    match = _NUMERIC_PATH.match(path)
    if not match:
        return path
    slug = slug_of(conn, int(match.group(1)))
    return f"/v/{slug}{path[match.end() :]}" if slug else path
