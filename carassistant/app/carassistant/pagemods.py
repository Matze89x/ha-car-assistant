"""Page modules: the pages an integration describes (lists of entries with typed fields), drawn and stored by the app.

Nothing of a package runs. The manifest says which pages and fields exist; the entries live in ``module_rows`` per vehicle and per
integration, are part of the vehicle backup, and a plugin of the same car can read them through the Plugin API.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import UTC, date, datetime

MAX_ROWS = 500
HEX = re.compile(r"^[0-9A-F]*$")


class PageError(ValueError):
    """``args[0]`` is an i18n key, ``args[1]`` the label of the field."""


def active_modules(conn: sqlite3.Connection, vehicle_id: int) -> list[dict]:
    """Installed, running integrations of a vehicle that describe pages: ``{addon_id, name, icon, nav, pages}``."""
    out = []
    from . import pluginsvc

    for r in conn.execute(
        "SELECT id, addon_id, manifest FROM vehicle_addons WHERE vehicle_id = ? AND kind = 'integration' AND active = 1 AND status != 'missing' ORDER BY id",
        (vehicle_id,),
    ):
        try:
            m = json.loads(r["manifest"])
        except ValueError:
            continue
        if m.get("service") and not pluginsvc.running(r["id"]):  # the frame pages of an integration with a service exist only while it runs
            m["pages"] = [p for p in m.get("pages", []) if p.get("kind") != "frame"]
        if m.get("pages"):
            out.append(
                {
                    "addon_id": r["addon_id"],
                    "name": m.get("name") or r["addon_id"],
                    "icon": m.get("icon") or "puzzle",
                    "nav": m.get("nav", True),
                    "pages": m["pages"],
                    "version": m.get("version") or "",
                }
            )
    out.extend(_frame_modules(conn, vehicle_id))
    return out


def _frame_modules(conn: sqlite3.Connection, vehicle_id: int) -> list[dict]:
    """Packages with a service that show pages of it inside the app (kind ``frame``): only while the service RUNS - stopped, the page and its
    entry in More are gone."""
    from . import pluginsvc

    out = []
    for r in conn.execute(
        "SELECT id, addon_id, manifest FROM vehicle_addons WHERE vehicle_id = ? AND kind = 'plugin' AND active = 1 AND status != 'missing' "
        "AND manifest LIKE '%\"frame\"%' ORDER BY id",
        (vehicle_id,),
    ):
        try:
            m = json.loads(r["manifest"])
        except ValueError:
            continue
        pages = [p for p in m.get("pages", []) if p.get("kind") == "frame"]
        if pages and pluginsvc.running(r["id"]):
            out.append(
                {
                    "addon_id": r["addon_id"],
                    "name": m.get("name") or r["addon_id"],
                    "icon": pages[0].get("icon") or m.get("icon") or "puzzle",
                    "nav": m.get("nav", True),
                    "pages": pages,
                    "version": m.get("version") or "",
                    "frame": True,
                }
            )
    return out


def module(conn: sqlite3.Connection, vehicle_id: int, addon_id: str) -> dict | None:
    from . import config

    found = next((m for m in active_modules(conn, vehicle_id) if m["addon_id"] == addon_id), None)
    return localize(found, config.language()) if found else None


def localize(mod: dict, lang: str) -> dict:
    """The module with the names, titles and labels in the language (a missing translation keeps the original text)."""

    def pick(item: dict, *keys: str) -> dict:
        texts = (item.get("l10n") or {}).get(lang) or (item.get("l10n") or {}).get(lang.split("-")[0]) or {}
        return {k: texts[k] for k in keys if k in texts}

    out = {**mod, **pick(mod, "name")}
    out["pages"] = [
        {**p, **pick(p, "title", "item", "empty"), "fields": [{**f, **pick(f, "label", "help")} for f in p["fields"]]} for p in mod["pages"]
    ]
    return out


def page_of(mod: dict, page_id: str | None) -> dict | None:
    pages = mod["pages"]
    return next((p for p in pages if p["id"] == page_id), None) if page_id else pages[0]


def secret_keys(page: dict) -> set[str]:
    """The fields of a page that hold an access code: hidden until shown, never sent to a plugin, left out of the plain vehicle backup."""
    return {f["key"] for f in page.get("fields", []) if f["type"] == "secret"}


def rows(conn: sqlite3.Connection, vehicle_id: int, addon_id: str, page_id: str, order: dict | None = None) -> list[dict]:
    out = []
    for r in conn.execute(
        "SELECT id, sort, data FROM module_rows WHERE vehicle_id = ? AND addon_id = ? AND page = ? ORDER BY sort, id",
        (vehicle_id, addon_id, page_id),
    ):
        try:
            data = json.loads(r["data"])
        except ValueError:
            data = {}
        out.append({"id": r["id"], "data": data})
    if order:  # sorted by a field of the page (stable: the manual order decides between equal values)
        out.sort(key=lambda r: str(r["data"].get(order["by"], "")), reverse=order["dir"] == "desc")
    return out


MAX_BIT_NOTES = 2000
MAX_BIT_JSON = 15000


def _bit_notes(raw) -> dict:
    """``{"<hex field>": {"<byte>.<bit>": "text"}}``: a note for a bit; only valid places, short single-line texts."""
    try:
        data = json.loads(raw) if isinstance(raw, str) and raw.strip() else {}
    except ValueError:
        return {}
    out: dict = {}
    count = 0
    for field, notes in data.items() if isinstance(data, dict) else []:
        if not isinstance(field, str) or not isinstance(notes, dict):
            continue
        clean = {}
        for where, text in notes.items():
            m = re.fullmatch(r"(\d{1,4})\.([0-7])", where) if isinstance(where, str) else None
            text = " ".join(text.split())[:200] if isinstance(text, str) else ""
            if m and int(m.group(1)) < 1100 and text and count < MAX_BIT_NOTES:
                clean[where] = text
                count += 1
        if clean:
            out[field[:31]] = clean
    return out


def _bit_groups(raw) -> dict:
    """``{"<hex field>": {"<byte>": [{"m": mask, "l": "name"}]}}``: bits of one byte under one name; a group has at least two bits and none overlap."""
    try:
        data = json.loads(raw) if isinstance(raw, str) and raw.strip() else {}
    except ValueError:
        return {}
    out: dict = {}
    for field, per_byte in data.items() if isinstance(data, dict) else []:
        if not isinstance(field, str) or not isinstance(per_byte, dict):
            continue
        clean: dict = {}
        for byte, groups in per_byte.items():
            if not (isinstance(byte, str) and byte.isdigit() and int(byte) < 1100 and isinstance(groups, list)):
                continue
            used, kept = 0, []
            for g in groups[:8]:
                mask = g.get("m") if isinstance(g, dict) else None
                if (
                    isinstance(mask, int)
                    and not isinstance(mask, bool)
                    and 1 <= mask <= 255
                    and bin(mask).count("1") >= 2
                    and not mask & used
                ):
                    used |= mask
                    kept.append({"m": mask, "l": " ".join(str(g.get("l") or "").split())[:200]})
            if kept:
                clean[byte] = kept
        if clean:
            out[field[:31]] = clean
    return out


def bit_data(form: dict, old: dict | None) -> dict:
    """The notes and groups of bits of an entry (``_bits``, ``_groups``) as stored: JSON texts. Without them in the form, the old ones stay."""
    out = {}
    for ui, key, clean in (("bitnotes", "_bits", _bit_notes), ("bitgroups", "_groups", _bit_groups)):
        raw = form[ui] if ui in form else (old or {}).get(key, "")
        value = clean(raw)
        text = json.dumps(value, separators=(",", ":"), ensure_ascii=False) if value else ""
        if len(text) > MAX_BIT_JSON:
            raise PageError("err.limit", "bits")
        if text:
            out[key] = text
    return out


def parse(page: dict, form: dict[str, str], old: dict | None = None, keep_once: bool = True) -> dict:
    """The values of one entry from a form. Sent by a plugin, a ``once`` field that already has a value keeps it (a person may always change it). Raises PageError(key, label)."""
    data: dict = {}
    for f in page["fields"]:
        key, kind = f["key"], f["type"]
        raw = (form.get(key) or "").strip()
        if keep_once and old is not None and f["once"] and old.get(key) not in (None, "", "0"):
            data[key] = old[key]  # fixed once written
            continue
        if kind == "bool":
            data[key] = "1" if form.get(key) else "0"
            continue
        if kind == "secret" and old is not None:  # an empty field keeps the saved code; it is removed on purpose only
            if form.get(key + "__clear"):
                data[key] = ""
                continue
            if not raw:
                data[key] = str(old.get(key) or "")
                continue
        if not raw:
            if f["required"]:
                raise PageError("err.required", f["label"])
            data[key] = ""
            continue
        if kind == "textarea":
            data[key] = raw[:20000]
        elif kind == "number":
            try:
                data[key] = str(float(raw.replace(",", ".")))
            except ValueError as exc:
                raise PageError("err.number", f["label"]) from exc
        elif kind == "date":
            try:
                data[key] = date.fromisoformat(raw).isoformat()
            except ValueError as exc:
                raise PageError("err.date", f["label"]) from exc
        elif kind == "secret":
            data[key] = raw[:200]
        elif kind == "url":
            if not re.fullmatch(r"https?://[^\s<>\"']{3,480}", raw):
                raise PageError("err.url", f["label"])
            data[key] = raw
        elif kind == "hex":
            hexed = re.sub(r"[\s:-]", "", raw).upper()
            if not HEX.match(hexed) or len(hexed) % 2 or len(hexed) > 2200:
                raise PageError("err.hex", f["label"])
            data[key] = hexed
        elif kind == "select":
            if raw not in {o["value"] for o in f.get("options", [])}:
                raise PageError("err.choice", f["label"])
            data[key] = raw
        else:
            data[key] = raw[:500]
    if any(f["type"] == "hex" and f.get("compare") for f in page["fields"]):
        data.update(bit_data(form, old))  # notes and groups of the bits of a coding
    return data


def add(conn: sqlite3.Connection, vehicle_id: int, addon_id: str, page: dict, data: dict) -> int:
    if (
        conn.execute(
            "SELECT COUNT(*) FROM module_rows WHERE vehicle_id = ? AND addon_id = ? AND page = ?", (vehicle_id, addon_id, page["id"])
        ).fetchone()[0]
        >= MAX_ROWS
    ):
        raise PageError("err.limit", "")
    last = conn.execute(
        "SELECT COALESCE(MAX(sort), 0) FROM module_rows WHERE vehicle_id = ? AND addon_id = ? AND page = ?",
        (vehicle_id, addon_id, page["id"]),
    ).fetchone()[0]
    return conn.execute(
        "INSERT INTO module_rows(vehicle_id, addon_id, page, sort, data, created_at) VALUES(?,?,?,?,?,?)",
        (vehicle_id, addon_id, page["id"], last + 1, json.dumps(data), datetime.now(UTC).isoformat(timespec="seconds")),
    ).lastrowid


MAX_API_ROWS = 500  # entries per request


def api_write(conn: sqlite3.Connection, vehicle_id: int, addon_id: str, page: dict, body) -> dict:
    """Entries sent by a plugin: ``{"rows": [{"id"?, "values": {...}}], "delete": [ids]}``. Everything is validated like a form; the
    request is all or nothing (the caller's transaction rolls back on an error)."""
    if not isinstance(body, dict):
        raise PageError("err.required", "body")
    rows_in, gone = body.get("rows") or [], body.get("delete") or []
    if not isinstance(rows_in, list) or not isinstance(gone, list) or len(rows_in) + len(gone) > MAX_API_ROWS:
        raise PageError("err.limit", "rows")
    added, changed = [], 0
    for item in rows_in:
        values = item.get("values") if isinstance(item, dict) else None
        if not isinstance(values, dict):
            raise PageError("err.required", "values")
        hidden = secret_keys(page)
        form = {
            k: ("1" if v is True else "" if v is False or v is None else str(v))
            for k, v in values.items()
            if isinstance(k, str) and k not in hidden
        }
        if item.get("id") is not None:
            old = get(conn, vehicle_id, addon_id, item["id"]) if isinstance(item["id"], int) else None
            if old is None or old["page"] != page["id"]:
                raise PageError("err.required", f"id {item['id']}")
            update(conn, old["id"], parse(page, {**{k: str(v) for k, v in old["data"].items()}, **form}, old["data"]))
            changed += 1
        else:
            added.append(add(conn, vehicle_id, addon_id, page, parse(page, form)))
    removed = 0
    for rid in gone:
        row = get(conn, vehicle_id, addon_id, rid) if isinstance(rid, int) else None
        if row is not None and row["page"] == page["id"]:
            delete(conn, row["id"])
            removed += 1
    return {"added": added, "changed": changed, "deleted": removed}


def get(conn: sqlite3.Connection, vehicle_id: int, addon_id: str, row_id: int) -> dict | None:
    r = conn.execute(
        "SELECT id, page, data FROM module_rows WHERE id = ? AND vehicle_id = ? AND addon_id = ?", (row_id, vehicle_id, addon_id)
    ).fetchone()
    return {"id": r["id"], "page": r["page"], "data": json.loads(r["data"] or "{}")} if r else None


def update(conn: sqlite3.Connection, row_id: int, data: dict) -> None:
    conn.execute("UPDATE module_rows SET data = ? WHERE id = ?", (json.dumps(data), row_id))


def delete(conn: sqlite3.Connection, row_id: int) -> None:
    conn.execute("DELETE FROM module_rows WHERE id = ?", (row_id,))


def move(conn: sqlite3.Connection, vehicle_id: int, addon_id: str, page_id: str, row_id: int, way: str) -> None:
    """One step up or down in the page's order (the order is rewritten as 1, 2, 3, ...)."""
    ids = [
        r["id"]
        for r in conn.execute(
            "SELECT id FROM module_rows WHERE vehicle_id = ? AND addon_id = ? AND page = ? ORDER BY sort, id",
            (vehicle_id, addon_id, page_id),
        )
    ]
    if row_id not in ids:
        return
    i = ids.index(row_id)
    j = i - 1 if way == "up" else i + 1
    if 0 <= j < len(ids):
        ids[i], ids[j] = ids[j], ids[i]
    for n, rid in enumerate(ids, 1):
        conn.execute("UPDATE module_rows SET sort = ? WHERE id = ?", (n, rid))


def byte_diff(old: str, new: str) -> dict:
    """Two hex strings byte by byte: the cells (index, old, new, changed) and the list of changed bytes."""
    a = [old[i : i + 2] for i in range(0, len(old or ""), 2)]
    b = [new[i : i + 2] for i in range(0, len(new or ""), 2)]
    size = max(len(a), len(b))
    cells = [
        {
            "i": i,
            "old": a[i] if i < len(a) else "",
            "new": b[i] if i < len(b) else "",
            "changed": (a[i] if i < len(a) else "") != (b[i] if i < len(b) else ""),
        }
        for i in range(size)
    ]
    return {
        "cells": cells,
        "changed": [c for c in cells if c["changed"]],
        "len_old": len(a),
        "len_new": len(b),
        "len_differs": len(a) != len(b),
    }


def _secrets_of(conn: sqlite3.Connection, vehicle_id: int) -> dict[tuple[str, str], set[str]]:
    """(integration, page) -> its access-code fields, from the manifests of the car's integrations."""
    found: dict[tuple[str, str], set[str]] = {}
    for r in conn.execute("SELECT addon_id, manifest FROM vehicle_addons WHERE vehicle_id = ? AND kind = 'integration'", (vehicle_id,)):
        try:
            pages = json.loads(r["manifest"]).get("pages", [])
        except ValueError:
            continue
        for p in pages if isinstance(pages, list) else []:
            if isinstance(p, dict) and isinstance(p.get("fields"), list):
                keys = {
                    f["key"] for f in p["fields"] if isinstance(f, dict) and f.get("type") == "secret" and isinstance(f.get("key"), str)
                }
                if keys:
                    found[(r["addon_id"], str(p.get("id")))] = keys
    return found


def has_secrets(conn: sqlite3.Connection, vehicle_id: int) -> bool:
    """Does this car hold any saved access code (then the vehicle backup is offered with and without them)?"""
    secret = _secrets_of(conn, vehicle_id)
    return any(
        any(data.get(k) for k in secret.get((r["addon_id"], r["page"]), ()))
        for r in conn.execute("SELECT addon_id, page, data FROM module_rows WHERE vehicle_id = ?", (vehicle_id,))
        if (r["addon_id"], r["page"]) in secret
        for data in [json.loads(r["data"] or "{}")]
    )


def export(conn: sqlite3.Connection, vehicle_id: int, secrets: bool = False) -> list[dict]:
    """For the vehicle backup. Access codes are left out unless ``secrets`` is set (the person asked for a file WITH codes)."""
    secret = {} if secrets else _secrets_of(conn, vehicle_id)
    out = []
    for r in conn.execute(
        "SELECT addon_id, page, sort, data FROM module_rows WHERE vehicle_id = ? ORDER BY addon_id, page, sort, id", (vehicle_id,)
    ):
        drop = secret.get((r["addon_id"], r["page"]), ())
        data = {k: v for k, v in json.loads(r["data"] or "{}").items() if k not in drop}
        out.append({"addon_id": r["addon_id"], "page": r["page"], "sort": r["sort"], "data": data})
    return out


def restore(conn: sqlite3.Connection, vehicle_id: int, entries) -> None:
    for e in (entries if isinstance(entries, list) else [])[: MAX_ROWS * 6]:
        if (
            not isinstance(e, dict)
            or not isinstance(e.get("addon_id"), str)
            or not isinstance(e.get("page"), str)
            or not isinstance(e.get("data"), dict)
        ):
            continue
        data = {str(k)[:31]: str(v)[:20000] for k, v in e["data"].items() if isinstance(v, str | int | float)}
        conn.execute(
            "INSERT INTO module_rows(vehicle_id, addon_id, page, sort, data, created_at) VALUES(?,?,?,?,?,?)",
            (
                vehicle_id,
                e["addon_id"][:41],
                e["page"][:31],
                int(e.get("sort") or 0),
                json.dumps(data),
                datetime.now(UTC).isoformat(timespec="seconds"),
            ),
        )
