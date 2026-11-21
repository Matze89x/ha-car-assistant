"""Equipment of a vehicle ("Ausstattungsmerkmale"): features grouped in FIXED categories, each feature with a status and an optional code (for example a PR number).

The categories are the same for every car and always there (even when empty); they can only be put in another order. Everybody creates the features
themselves. Status: ``series`` (standard), ``option`` (special equipment), ``retrofit`` (added later), ``missing`` (not fitted). The first three count
as fitted (green / blue tick), ``missing`` carries a red cross. Inside a category the features are listed in that order.

A feature stores the category as its KEY (``exterior`` ...); older rows with a free name still show up, after the fixed categories.
"""

from __future__ import annotations

import json
import re
import sqlite3

from . import db, i18n, icons

STATUSES = ("series", "option", "retrofit", "missing")
FITTED = ("series", "option", "retrofit")
MAX_TITLE = 120
MAX_CODE = 24

# (key, icon, colour class): the twelve areas of every car, in this order; the names are translated (``eq.cat.<key>``) in every language of the app
CATEGORIES: tuple[tuple[str, str, str], ...] = (
    ("comfort", "snowflake", "c1"),
    ("seats", "seat", "c2"),
    ("controls", "car-shift-pattern", "c5"),
    ("lights", "car-light-dimmed", "c3"),
    ("packages", "puzzle", "c4"),
    ("interior", "car-door", "c7"),
    ("wheels", "tires", "c6"),
    ("tech", "airbag", "c6"),
    ("exterior", "car-side", "c1"),
    ("media", "memory", "c7"),
    ("assist", "shield-check", "c2"),
    ("roof", "window-closed-variant", "c4"),
)
KEYS = tuple(c[0] for c in CATEGORIES)
_BY_KEY = {c[0]: c for c in CATEGORIES}
ORDER_SETTING = "equipment.order"  # per vehicle: "<setting>.<vehicle id>" = JSON list of category keys


def clean_status(value: str) -> str:
    return value if value in STATUSES else "series"


def clean_text(value: str, limit: int) -> str:
    return re.sub(r"\s+", " ", value or "").strip()[:limit]


def clean_category(value: str, conn: sqlite3.Connection | None = None, vehicle_id: int | None = None) -> str:
    """A category key of the fixed set (anything unknown goes to the first area)."""
    value = (value or "").strip()
    return value if value in _BY_KEY else KEYS[0]


def display(ident: str, lang: str) -> str:
    return i18n.translator(lang)(f"eq.cat.{ident}")


def order(conn: sqlite3.Connection, vehicle_id: int) -> list[str]:
    """The twelve categories of a vehicle in their order: the saved order first, then what is missing there."""
    try:
        saved = json.loads(db.get_setting(conn, f"{ORDER_SETTING}.{vehicle_id}", "") or "[]")
    except ValueError:
        saved = []
    seq: list[str] = []
    for ident in [*(saved if isinstance(saved, list) else []), *KEYS]:
        if ident in _BY_KEY and ident not in seq:
            seq.append(ident)
    return seq


def groups(conn: sqlite3.Connection, vehicle_id: int, lang: str = "en") -> list[dict]:
    """Every category of the vehicle (also the empty ones) with its features: series, special, retrofitted, not fitted - and the count fitted/total."""
    rows: dict[str, list] = {}
    for row in conn.execute("SELECT * FROM equipment WHERE vehicle_id = ? ORDER BY sort, id", (vehicle_id,)):
        rows.setdefault(row["category"], []).append(row)
    out = []
    for ident in order(conn, vehicle_id):
        items = sorted(rows.get(ident, []), key=lambda r: STATUSES.index(r["status"]) if r["status"] in STATUSES else 0)
        out.append(
            {
                "key": ident,
                "name": display(ident, lang),
                "icon": _BY_KEY[ident][1],
                "chip": _BY_KEY[ident][2],
                "items": items,
                "groups": [
                    {"key": st, "rows": [r for r in items if r["status"] == st]} for st in STATUSES if any(r["status"] == st for r in items)
                ],
                "fitted": sum(1 for r in items if r["status"] in FITTED),
                "total": len(items),
            }
        )
    return out


def add_item(conn: sqlite3.Connection, vehicle_id: int, category: str, title: str, status: str = "series", code: str = "") -> bool:
    title = clean_text(title, MAX_TITLE)
    if not title:
        return False
    category = clean_category(category, conn, vehicle_id)
    nxt = conn.execute("SELECT COALESCE(MAX(sort), 0) + 1 FROM equipment WHERE vehicle_id = ?", (vehicle_id,)).fetchone()[0]
    conn.execute(
        "INSERT INTO equipment(vehicle_id, category, icon, title, code, status, sort) VALUES(?,?,?,?,?,?,?)",
        (vehicle_id, category, "", title, clean_text(code, MAX_CODE).upper(), clean_status(status), nxt),
    )
    return True


def save_item(conn: sqlite3.Connection, vehicle_id: int, item_id: int, form: dict[str, str]) -> None:
    """Edit ONE feature: text, code, status and its category (a different one moves it there); ``del`` removes it."""
    row = conn.execute("SELECT * FROM equipment WHERE id = ? AND vehicle_id = ?", (item_id, vehicle_id)).fetchone()
    if row is None:
        return
    if form.get("del"):
        conn.execute("DELETE FROM equipment WHERE id = ?", (item_id,))
        return
    conn.execute(
        "UPDATE equipment SET title = ?, code = ?, status = ?, category = ? WHERE id = ?",
        (
            clean_text(form.get("title", ""), MAX_TITLE) or row["title"],
            clean_text(form.get("code", ""), MAX_CODE).upper(),
            clean_status(form.get("status", "")),
            clean_category(form.get("category", row["category"]), conn, vehicle_id),
            item_id,
        ),
    )


def move_category(conn: sqlite3.Connection, vehicle_id: int, category: str, direction: str) -> None:
    """Move a category one place up or down."""
    seq = order(conn, vehicle_id)
    if category not in seq:
        return
    i = seq.index(category)
    j = i - 1 if direction == "up" else i + 1
    if not 0 <= j < len(seq):
        return
    seq[i], seq[j] = seq[j], seq[i]
    db.set_setting(conn, f"{ORDER_SETTING}.{vehicle_id}", json.dumps(seq))


_ = icons  # the icon names of CATEGORIES are checked by the tests
