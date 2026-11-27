"""Invoices and the cost entries: what the form of a new entry is filled with when an invoice is booked, and the link between the two.

An invoice is a document of the category ``invoice`` (documents.py of the pages: ``web.py``) that has been read (``invoice.py``). Booking it means
opening the ordinary form of a service, parts, modification, fixed cost or refuel entry, filled in from what the reading found; the person checks it
and saves, and the entry then points back at the invoice (``documents.booked_table`` / ``booked_id``). Nothing is booked without that save.
"""

from __future__ import annotations

import json
import sqlite3

from . import invoice, odometer_scan, units

TABLE_OF = {"service": "service", "mods": "mods", "parts": "parts", "fixed": "fixed_costs", "fuel": "fuel"}  # entity key -> table
KEY_OF = {table: key for key, table in TABLE_OF.items()}
_LEAD = {  # the columns that say when and what an entry is, to show a booked invoice's entry
    "service": ("date", "title"),
    "mods": ("date", "title"),
    "parts": ("date", "name"),
    "fixed_costs": ("start_date", "title"),
    "fuel": ("date", "station"),
}


def document(conn: sqlite3.Connection, vid: int, doc_id: int) -> sqlite3.Row | None:
    """An invoice of this car (None for another car's, or for a document of another category)."""
    return conn.execute("SELECT * FROM documents WHERE id = ? AND vehicle_id = ? AND category = 'invoice'", (doc_id, vid)).fetchone()


def extract_of(doc: sqlite3.Row) -> dict:
    try:
        got = json.loads(doc["extract"] or "{}")
    except ValueError:
        return {}
    return got if isinstance(got, dict) else {}


def link(conn: sqlite3.Connection, vid: int, doc_id: int, table: str, row_id: int) -> bool:
    """The invoice was booked as the entry ``row_id`` of ``table``. False when it is no invoice of this car."""
    if table not in KEY_OF or document(conn, vid, doc_id) is None:
        return False
    conn.execute("UPDATE documents SET booked_table = ?, booked_id = ? WHERE id = ?", (table, row_id, doc_id))
    return True


def unlink(conn: sqlite3.Connection, vid: int, doc_id: int) -> None:
    conn.execute("UPDATE documents SET booked_table = NULL, booked_id = NULL WHERE id = ? AND vehicle_id = ?", (doc_id, vid))


def booked(conn: sqlite3.Connection, vid: int, docs) -> dict[int, dict]:
    """For the invoices among ``docs`` that are booked and whose entry still exists: ``{doc id: {key, row, day, title}}``."""
    out: dict[int, dict] = {}
    for d in docs:
        table = d["booked_table"]
        if table not in _LEAD or d["booked_id"] is None:
            continue
        day, name = _LEAD[table]
        row = conn.execute(
            f"SELECT {day} AS day, {name} AS name FROM {table} WHERE id = ? AND vehicle_id = ?", (d["booked_id"], vid)
        ).fetchone()
        if row is not None:
            out[d["id"]] = {"key": KEY_OF[table], "row": d["booked_id"], "day": row["day"], "title": row["name"] or ""}
    return out


def invoices_of(conn: sqlite3.Connection, vid: int, table: str, ids: list[int]) -> dict[int, int]:
    """The invoice of each of these entries (``{entry id: document id}``): for the paperclip in a list."""
    if not ids or table not in KEY_OF:
        return {}
    marks = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT booked_id, id FROM documents WHERE vehicle_id = ? AND booked_table = ? AND booked_id IN ({marks}) ORDER BY id",
        (vid, table, *ids),
    ).fetchall()
    return {r["booked_id"]: r["id"] for r in rows}


def sums(conn: sqlite3.Connection, vid: int) -> dict:
    """How many invoices wait to be booked and what they come to (an entry that was deleted does not count as booked)."""
    docs = conn.execute(
        "SELECT id, amount, booked_table, booked_id FROM documents WHERE vehicle_id = ? AND category = 'invoice'", (vid,)
    ).fetchall()
    done = booked(conn, vid, docs)
    open_ = [d for d in docs if d["id"] not in done]
    return {"total": len(docs), "open": len(open_), "open_amount": round(sum(d["amount"] or 0 for d in open_), 2)}


def prefill(key: str, extract: dict, doc: sqlite3.Row, u: units.Units, base: str, last_km: int | None, t) -> dict[str, str]:
    """The fields of a new entry of kind ``key`` as text for the form (typed in the units shown), from what the reading found. Fields nothing was found
    for are left out: an empty form field says nothing is claimed."""
    form: dict[str, str] = {}
    day = extract.get("date") or doc["doc_date"]
    if day:
        form["date" if key != "fixed" else "start_date"] = day
    km = extract.get("odometer")
    if key in ("service", "mods", "fuel") and km and odometer_scan.plausible(km, last_km):
        form["odometer_km"] = str(round(u.d(km)))
    vendor = extract.get("vendor") or ""
    amount = extract.get("amount") if extract.get("amount") is not None else doc["amount"]
    cost = f"{amount:.2f}" if amount else ""
    work = t(f"inv.w.{extract['work']}") if extract.get("work") else ""
    note = t("inv.note", n=extract["number"]) if extract.get("number") else ""
    if key == "service":
        form.update(title=work or vendor, workshop=vendor, cost=cost)
    elif key == "mods":
        form.update(title=work or vendor, cost=cost)
    elif key == "parts":
        form.update(name=work or vendor, shop=vendor, cost=cost)
    elif key == "fixed":
        kind = extract.get("fixed_kind") if extract.get("fixed_kind") in ("tax", "insurance", "parking", "toll", "club") else "other"
        form.update(
            title=" ".join(x for x in (t(f"cost_kind.{kind}"), vendor) if x),
            cost_kind=kind,
            cost=cost,
            every=extract.get("every") or "once",
        )
    elif key == "fuel":
        pump = extract.get("fuel") or {}
        if pump.get("amount") is not None:
            form["amount"] = f"{u.v(pump['amount'], base):.2f}"
        if pump.get("price_per_unit") is not None:
            form["price_per_unit"] = f"{u.price_vol(pump['price_per_unit'], base):.3f}"
        total = pump.get("price_total") if pump.get("price_total") is not None else amount
        if total:
            form["price_total"] = f"{total:.2f}"
        form["station"] = pump.get("station") or vendor
        form["notes"] = pump.get("notes") or ""
    if note and key != "fuel":
        form["notes"] = note
    elif note:
        form["notes"] = " · ".join(x for x in (form.get("notes"), note) if x)
    return {k: v for k, v in form.items() if v}


def kinds_open(conn: sqlite3.Connection, vid: int) -> list[str]:
    """The kinds an invoice can be booked as on this car: the entries whose function is not switched off."""
    from . import modules

    off = modules.disabled(conn, vid)
    return [k for k in invoice.KINDS if (k if k != "fixed" else "report") not in off]
