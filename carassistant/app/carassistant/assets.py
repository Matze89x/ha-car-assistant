"""The files of a package (``files`` and ``bundles`` of its plugin.json): checked downloads the app hands out itself.

They lie read-only in their own folder (apart from the code of any service, which cannot reach it), are never opened beyond reading their bytes and
never run. A file is only handed out while an administrator approved exactly what the package says (see pluginsvc.approved). A bundle is a zip the
app builds on request from files of the package - always the same bytes for the same package (fixed order, fixed times).
"""

from __future__ import annotations

import hashlib
import io
import re
import sqlite3
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from . import addons, config, connectors, pluginsvc, regional

_bundle_cache: dict[tuple[str, str, str], dict] = {}
PLACEHOLDER = re.compile(r"\{file:([A-Za-z0-9][A-Za-z0-9._-]{0,79})\}")


def instance(conn: sqlite3.Connection, addon_id: str) -> dict | None:
    """An installed copy of this package whose files are approved (the files are the same on every car)."""
    for row in conn.execute(
        "SELECT vehicle_id, id FROM vehicle_addons WHERE addon_id = ? AND status != 'missing' ORDER BY id", (addon_id,)
    ):
        addon = addons.get(conn, row["vehicle_id"], row["id"])
        if addon and (addon["m"].get("files") or addon["m"].get("bundles")) and pluginsvc.approved(addon) and addon.get("pkg_sha"):
            return addon
    return None


def _source(addon: dict, path: str) -> Path | None:
    """The file of the package a bundle entry (or a download) points to: one of the ``files`` or a text file of the package."""
    by_path = {f["path"]: f for f in addon["m"].get("files", [])}
    if path in by_path:
        base = pluginsvc.asset_dir(addon["addon_id"], addon["pkg_sha"])
        target = base / by_path[path]["name"]
    else:
        base = pluginsvc.pkg_dir(addon["addon_id"], addon["pkg_sha"])
        target = base / path
    try:
        resolved = target.resolve()
        return resolved if resolved.is_relative_to(base.resolve()) and resolved.is_file() else None
    except OSError:
        return None


def read_file(addon: dict, name: str) -> tuple[bytes, str] | None:
    """(bytes, content type) of a file, checked against its checksum once more; None when it is not there or does not match."""
    meta = next((f for f in addon["m"].get("files", []) if f["name"] == name), None)
    if meta is None:
        return None
    path = pluginsvc.asset_dir(addon["addon_id"], addon["pkg_sha"]) / name
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) != meta["size"] or hashlib.sha256(data).hexdigest() != meta["sha256"]:
        return None
    return data, addons.FILE_TYPES["." + name.rsplit(".", 1)[-1].lower()]


def build_bundle(addon: dict, bundle: dict, connection_file: str | None = None) -> bytes | None:
    """The zip of a bundle: the entries in the given order, with the given paths, fixed times and permissions, so the same package always gives the
    same bytes. None when a source is missing or the result would be too big. A bundle with ``connection_file_to`` is only built with the text of the
    connection file (it holds the token, made for one download and never stored); without it there is no zip."""
    to = bundle.get("connection_file_to")
    if to and connection_file is None:
        return None
    out = io.BytesIO()
    total = 0
    with zipfile.ZipFile(out, "w") as zf:
        for entry in bundle["entries"]:
            source = _source(addon, entry["from"])
            if source is None:
                return None
            data = source.read_bytes()
            total += len(data)
            if total > addons.MAX_FILES_TOTAL:
                return None
            info = zipfile.ZipInfo(entry["to"], date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            info.create_system = 3
            zf.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)
        if to:
            info = zipfile.ZipInfo(to, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            info.create_system = 3
            zf.writestr(info, connection_file.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)
    return out.getvalue()


def bundle_info(addon: dict, bundle: dict) -> dict:
    """Size and short checksum of a bundle (built once per package version and remembered)."""
    key = (addon["addon_id"], addon.get("pkg_sha") or "", bundle["name"])
    if key not in _bundle_cache:
        data = build_bundle(addon, bundle)
        _bundle_cache[key] = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()} if data is not None else {}
    return _bundle_cache[key]


def listing(addon: dict, offered: bool) -> list[dict]:
    """The files and bundles of a package for the pages: name, label, note, size, checksum, and (when approved) the address to fetch them."""
    rows = []
    vals = addon.get("vals") or {}

    def versions(item: dict) -> dict:
        """What the plugin says it offers (``version``) and what it reported to lie on the car (the setting named in ``installed``)."""
        have = str(vals.get(item.get("installed", ""), "") or "")
        return {"version": item.get("version", ""), "have": have, "state": addons.version_state(have, item.get("version", ""))}

    for f in addon["m"].get("files", []):
        rows.append(
            {
                "name": f["name"],
                "label": f["label"],
                "note": f["note"],
                "size": f["size"],
                "sha256": f["sha256"],
                "kind": "file",
                "href": f"/plugins/{addon['addon_id']}/files/{f['name']}" if offered else "",
                **versions(f),
            }
        )
    lang = config.language()
    for b in addon["m"].get("bundles", []):
        own = (b.get("l10n") or {}).get(lang) or {}
        b = {**b, "label": own.get("label") or b["label"], "note": own.get("note") or b["note"]}
        with_token = bool(b.get("connection_file_to"))
        info = bundle_info(addon, b) if offered and not with_token else {}
        rows.append(
            {
                "name": b["name"],
                "label": b["label"],
                "note": b["note"],
                "size": info.get("size", 0),
                "sha256": info.get("sha256", ""),
                "kind": "bundle",
                "entries": [f"{e['from']} -> {e['to']}" for e in b["entries"]]
                + ([f"(connection file) -> {b['connection_file_to']}"] if with_token else []),
                "with_token": with_token,  # handed out only by the set-up guide, with the token of that run
                "href": f"/plugins/{addon['addon_id']}/files/{b['name']}" if offered and not with_token else "",
                **versions(b),
            }
        )
    return rows


def docs_parts(addon: dict, offered: bool) -> list[dict]:
    """The ``docs`` text with ``{file:name}`` turned into links: a list of ``{"text"}`` and ``{"file": {...}}`` pieces for the page."""
    text = addon["m"].get("docs", "")
    by_name = {r["name"]: r for r in listing(addon, offered)}
    parts, last = [], 0
    for m in PLACEHOLDER.finditer(text):
        if m.start() > last:
            parts.append({"text": text[last : m.start()]})
        parts.append({"file": by_name[m.group(1)]} if m.group(1) in by_name else {"text": m.group(0)})
        last = m.end()
    if last < len(text):
        parts.append({"text": text[last:]})
    return parts or ([{"text": text}] if text else [])


def record_delivery(conn: sqlite3.Connection, addon: dict, name: str) -> None:
    """Note that this file of the package was handed out for this car: when, which version it had and which settings it was built from."""
    item = next((x for x in [*addon["m"].get("files", []), *addon["m"].get("bundles", [])] if x["name"] == name), {})
    conn.execute(
        "INSERT INTO addon_deliveries(addon_pk, name, version, delivered_at, settings_hash) VALUES(?,?,?,?,?) "
        "ON CONFLICT(addon_pk, name) DO UPDATE SET version = excluded.version, delivered_at = excluded.delivered_at, "
        "settings_hash = excluded.settings_hash",
        (
            addon["id"],
            name,
            item.get("version", ""),
            datetime.now(UTC).isoformat(timespec="seconds"),
            addons.settings_hash(addon["m"], addon["vals"]),
        ),
    )


def general_rows(conn: sqlite3.Connection, addon: dict, slug: str, offered: bool) -> list[dict]:
    """The files and bundles for the tab *General*: every row downloads through the car's own address (so the app notes it), and says what was last
    handed out (``last_version``, ``last_at``) and whether the settings changed since (``stale``: only for a package that carries the connection file).
    A package with a connection file that holds the token is built here only when the app keeps the token; otherwise the set-up guide does it."""
    seen = {
        r["name"]: r
        for r in conn.execute("SELECT name, version, delivered_at, settings_hash FROM addon_deliveries WHERE addon_pk = ?", (addon["id"],))
    }
    now = addons.settings_hash(addon["m"], addon["vals"])
    can_token = not addons.file_has_secret(addon["m"]) or bool(connectors.remembered(conn, addon.get("token_id")))
    out = []
    for row in listing(addon, offered):
        row = {**row, "entries": []}  # the list of entries belongs on the Info page
        row["href"] = (
            f"/v/{slug}/integrations/{addon['id']}/get/{row['name']}" if offered and (not row.get("with_token") or can_token) else ""
        )
        row["guide_only"] = bool(row.get("with_token")) and not row["href"]
        last = seen.get(row["name"])
        if last:
            row["last_version"] = last["version"]
            row["last_at"] = regional.fdatetime(last["delivered_at"])
            row["stale"] = bool(row.get("with_token")) and last["settings_hash"] != now
            if not row.get("state") and last["version"] and row.get("version"):
                row["state"] = addons.version_state(
                    last["version"], row["version"]
                )  # no word from the car: compare with what was last handed out
        out.append(row)
    return out
