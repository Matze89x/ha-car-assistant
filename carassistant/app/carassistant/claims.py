"""One interface, one plugin: the fields of the Plugin API a plugin has taken (claimed) for itself on a car.

Nothing is taken by itself - a plugin that sends a field is simply one of the sources, and the newer measurement wins (connectors.py). A person (or a package,
by ``claims`` in its plugin.json) may TAKE a field for one plugin on one car: while that plugin is on, every other source of that car - another plugin, a
connector, the older bindings of the vehicle form - is ignored for that field, and says so in its answer (``ignored (taken by <plugin>)``). So two sources
never fight over one value, and what a car shows always has exactly one origin.

The earliest claim of a plugin that is ON holds the field; a plugin that is off holds nothing (its claims wait, and come back with it). The claims of a plugin
go with the plugin (``ON DELETE CASCADE``)."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def pk_of(conn: sqlite3.Connection, vehicle_id: int, addon_id: str | None) -> int | None:
    """The install (its number) of a package on a car - or None."""
    if not addon_id:
        return None
    row = conn.execute("SELECT id FROM vehicle_addons WHERE vehicle_id = ? AND addon_id = ?", (vehicle_id, addon_id)).fetchone()
    return row["id"] if row else None


def owners(conn: sqlite3.Connection, vehicle_id: int) -> dict[str, dict]:
    """Who holds which field on this car: ``{field: {"pk": install, "name": name of the plugin}}`` - the earliest claim of a plugin that is on."""
    held: dict[str, dict] = {}
    for row in conn.execute(
        "SELECT c.field, c.addon_pk, a.manifest FROM field_claims c JOIN vehicle_addons a ON a.id = c.addon_pk "
        "WHERE c.vehicle_id = ? AND a.active = 1 ORDER BY c.created, c.addon_pk",
        (vehicle_id,),
    ):
        if row["field"] not in held:
            try:
                name = json.loads(row["manifest"]).get("name") or ""
            except ValueError:
                name = ""
            held[row["field"]] = {"pk": row["addon_pk"], "name": name or "?"}
    return held


def conflicts(conn: sqlite3.Connection, vehicle_id: int, addon_pk: int, fields) -> dict[str, str]:
    """The fields among ``fields`` that another plugin (one that is on) holds: ``{field: name of that plugin}``."""
    held = owners(conn, vehicle_id)
    return {f: held[f]["name"] for f in fields if f in held and held[f]["pk"] != addon_pk}


def register(conn: sqlite3.Connection, vehicle_id: int, addon_pk: int, fields) -> None:
    """This plugin holds exactly ``fields`` on this car from now on (a field it held before keeps its place in the order)."""
    wanted = set(fields)
    have = {
        r["field"] for r in conn.execute("SELECT field FROM field_claims WHERE vehicle_id = ? AND addon_pk = ?", (vehicle_id, addon_pk))
    }
    for field in have - wanted:
        conn.execute("DELETE FROM field_claims WHERE vehicle_id = ? AND addon_pk = ? AND field = ?", (vehicle_id, addon_pk, field))
    for field in sorted(wanted - have):
        conn.execute(
            "INSERT INTO field_claims(vehicle_id, field, addon_pk, created) VALUES(?,?,?,?)", (vehicle_id, field, addon_pk, _now())
        )


def release(conn: sqlite3.Connection, addon_pk: int) -> None:
    conn.execute("DELETE FROM field_claims WHERE addon_pk = ?", (addon_pk,))


def held_by(conn: sqlite3.Connection, vehicle_id: int, addon_pk: int) -> list[str]:
    return sorted(
        r["field"] for r in conn.execute("SELECT field FROM field_claims WHERE vehicle_id = ? AND addon_pk = ?", (vehicle_id, addon_pk))
    )


def guard(conn: sqlite3.Connection, vehicle_id: int, data: dict, caller_pk: int | None) -> tuple[dict, dict[str, str]]:
    """What of a delivery may be stored: ``(the fields that are free or held by the sender, {field: name of the holder} for the ones that are not)``.
    ``measured_at`` goes along only while at least one field does."""
    if not conn.execute("SELECT 1 FROM field_claims WHERE vehicle_id = ? LIMIT 1", (vehicle_id,)).fetchone():
        return data, {}
    held = owners(conn, vehicle_id)
    refused = {f: held[f]["name"] for f in data if f in held and held[f]["pk"] != caller_pk and f != "measured_at"}
    if not refused:
        return data, {}
    kept = {f: v for f, v in data.items() if f not in refused}
    if not (set(kept) - {"measured_at"}):
        kept = {}
    return kept, refused
