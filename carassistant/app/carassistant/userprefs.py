"""Preferences of one signed-in user (user-bound level). A missing value means "like the server"."""

from __future__ import annotations

import sqlite3

KEYS = ("start_car", "haptics", "design", "page_size", "manual_view")


def get(conn: sqlite3.Connection, user_id: int | None, key: str) -> str | None:
    if user_id is None or key not in KEYS:
        return None
    row = conn.execute("SELECT value FROM user_prefs WHERE user_id = ? AND key = ?", (user_id, key)).fetchone()
    return row["value"] if row else None


def put(conn: sqlite3.Connection, user_id: int, key: str, value: str | None) -> None:
    if key not in KEYS:
        raise ValueError(key)
    if value in (None, ""):
        conn.execute("DELETE FROM user_prefs WHERE user_id = ? AND key = ?", (user_id, key))
    else:
        conn.execute(
            "INSERT INTO user_prefs(user_id, key, value) VALUES(?,?,?) ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value",
            (user_id, key, value),
        )


def start_vehicle(conn: sqlite3.Connection, user_id: int | None) -> int | None:
    """The car this user wants to land on, if it still exists and is not archived."""
    raw = get(conn, user_id, "start_car")
    if not raw or not raw.isdigit():
        return None
    row = conn.execute("SELECT id FROM vehicles WHERE id = ? AND archived = 0", (int(raw),)).fetchone()
    return row["id"] if row else None
