"""Set up the integrations and plugins of a restored car from their sources (docs/backup.md).

A vehicle backup holds no package, but it remembers where each one came from (the address of its source) and whether it ran; inside the block of the
passphrase it also holds the access keys of private sources and which services an administrator had approved (the fingerprint of what was approved and the
checksum of that package). When the person chose *Restore and set up* on the question page of a restore - that click is the consent - ``run``

- adds the sources that are missing (with their key from the block) and reads their lists,
- installs every package that is not installed yet from its source; a package with a service or files only when the checksum of what the source offers now
  fits what its index says (as always),
- switches on what was running,
- approves a service or its files ONLY when the package of the source is byte for byte the one that was approved before (same checksum, same description)
  AND that approval came out of the block of the passphrase - a file without it cannot approve anything,
- and leaves every other package installed, waiting for the person's approval on its own page, as always.

A source that does not answer, a package it no longer offers, an address that is not acceptable: that package stays "needs the package" with its settings and
token, and the result says so. ``plan`` is the same list before anything happens, for the question page.
"""

from __future__ import annotations

import json

from . import addons, db, pkginstall, pluginsvc, sources

MAX_ENTRIES = 50


def entries_of(data: dict) -> list[dict]:
    """The add-ons of a backup that can be worked with: a valid id and kind."""
    out = []
    for entry in (data.get("addons") or [])[:MAX_ENTRIES]:
        if isinstance(entry, dict) and isinstance(entry.get("addon_id"), str) and addons.ID.match(entry["addon_id"]):
            out.append({**entry, "kind": entry.get("kind") if entry.get("kind") in addons.KINDS else "plugin"})
    return out


def _url_of(entry: dict) -> str:
    source = entry.get("source") if isinstance(entry.get("source"), dict) else {}
    url = source.get("url") or entry.get("source_url") or ""
    try:
        return sources.clean_url(url) if isinstance(url, str) and url else ""
    except sources.SourceError:
        return ""


def _attested(entry: dict, approvals: dict) -> bool:
    return isinstance(approvals.get(entry["addon_id"]), dict)


def plan(conn, data: dict, secret: dict | None = None) -> list[dict]:
    """What a restore with *set up* would fetch: the add-ons that are not installed on this system yet and name a source. Nothing goes online here."""
    approvals = (secret or {}).get("approvals") or {}
    out = []
    for entry in entries_of(data):
        url = _url_of(entry)
        installed = conn.execute(
            "SELECT 1 FROM vehicle_addons WHERE addon_id = ? AND kind = ? AND status != 'missing' LIMIT 1",
            (entry["addon_id"], entry["kind"]),
        ).fetchone()
        if installed or not url:
            continue
        try:
            manifest = addons.parse_package(json.dumps(entry.get("manifest") or {"id": entry["addon_id"]}).encode())
        except addons.AddonError:
            continue
        out.append(
            {
                "addon_id": entry["addon_id"],
                "kind": entry["kind"],
                "name": manifest.get("name") or entry["addon_id"],
                "version": str(entry.get("version") or manifest.get("version") or ""),
                "url": url,
                "new_source": conn.execute("SELECT 1 FROM sources WHERE url = ?", (url,)).fetchone() is None,
                "runs_code": bool(manifest.get("service")),
                "hands_out": bool(manifest.get("files") or manifest.get("bundles")),
                "approved_before": _attested(entry, approvals)
                and bool(manifest.get("service") or manifest.get("files") or manifest.get("bundles")),
            }
        )
    return out


def _source(url: str, name: str, keys: dict) -> int:
    with db.tx() as conn:
        found = conn.execute("SELECT id FROM sources WHERE url = ?", (url,)).fetchone()
        if found:
            conn.execute("UPDATE sources SET for_integration = 1, for_plugin = 1 WHERE id = ?", (found["id"],))
            return found["id"]
        return sources.add(conn, name or "", url, keys.get(url, ""))


def _install(vehicle_id: int, entry: dict, keys: dict, refreshed: set) -> int:
    url = _url_of(entry)
    if not url:
        raise sources.SourceError("err.src_missing")
    source = entry.get("source") if isinstance(entry.get("source"), dict) else {}
    sid = _source(url, str(source.get("name") or ""), keys)
    if sid not in refreshed:
        with db.tx() as conn:
            error = sources.refresh(conn, sid)
        if error and error != "err.src_stale":
            raise sources.SourceError(error)
        refreshed.add(sid)
    with db.tx() as conn:
        if sources.package(conn, sid, entry["kind"], entry["addon_id"]) is None:
            raise sources.SourceError("err.src_missing")
        manifest = sources.fetch_manifest(conn, sid, entry["kind"], entry["addon_id"])
    sha = pkginstall.fetch_files(manifest, sid, entry["kind"], entry["addon_id"])
    with db.tx() as conn:
        return addons.add(conn, vehicle_id, manifest, sid, sha)


def _finish(vehicle_id: int, pk: int, entry: dict, approvals: dict) -> None:
    """What the package was before: running (and approved, when the block says the same package was approved)."""
    to_start = False
    with db.tx() as conn:
        addon = addons.get(conn, vehicle_id, pk)
        if addon is None:
            return
        if entry.get("active"):
            addons.set_active(conn, addon, True)
        said = approvals.get(entry["addon_id"])
        if (
            isinstance(said, dict)
            and addons.needs_package(addon["m"])
            and addon.get("pkg_sha")
            and addon["pkg_sha"] == said.get("pkg_sha")
            and addons.approval_fingerprint(addon["m"]) == said.get("svc_ok")
        ):
            to_start = pluginsvc.approve(conn, addon) is None and bool(pluginsvc.service_of(addon))
    if to_start:
        pluginsvc.install_async(pk)


def run(vehicle_id: int, data: dict, secret: dict | None = None) -> list[dict]:
    """Set up the add-ons of a restored car (see the top). Returns one result per add-on: ``{"addon_id", "ok", "why"}``."""
    keys = (secret or {}).get("source_keys") or {}
    approvals = (secret or {}).get("approvals") or {}
    refreshed: set[int] = set()
    results = []
    for entry in entries_of(data):
        with db.tx() as conn:
            row = conn.execute(
                "SELECT id, status FROM vehicle_addons WHERE vehicle_id = ? AND addon_id = ?", (vehicle_id, entry["addon_id"])
            ).fetchone()
        if row is None:
            continue
        try:
            pk = _install(vehicle_id, entry, keys, refreshed) if row["status"] == "missing" else row["id"]
            _finish(vehicle_id, pk, entry, approvals)
            results.append({"addon_id": entry["addon_id"], "ok": True, "why": ""})
        except (sources.SourceError, addons.AddonError) as exc:
            results.append({"addon_id": entry["addon_id"], "ok": False, "why": getattr(exc, "key", None) or str(exc)})
    pluginsvc.kick()
    return results


# ---------------------------------------------------------------- the files of packages that are installed but whose files are gone


def files_missing(addon: dict) -> bool:
    """A package that is installed (it has its checksum) but whose files are not on this system: after a restore of the whole system on another one, or a lost
    folder. The description is in the database, the files (the code of a service, the files it hands out) lie in folders of the data."""
    manifest = addon.get("m") or {}
    sha = addon.get("pkg_sha")
    if not sha or addon.get("status") == "missing" or not addons.needs_package(manifest):
        return False
    code = pluginsvc.pkg_dir(addon["addon_id"], sha)
    entry = (manifest.get("service") or {}).get("entry")
    if not code.is_dir() or (entry and not (code / entry).is_file()):
        return True
    assets = pluginsvc.asset_dir(addon["addon_id"], sha)
    return any(not (assets / f["name"]).is_file() for f in manifest.get("files") or [])


def refetch(vehicle_id: int, pk: int) -> str | None:
    """Fetch the files of one installed package again from its source. They must be exactly the files that were installed (the checksum of the package): a
    package that changed at its source is NOT put in place - that is an update the person presses. Returns None or an i18n key."""
    with db.tx() as conn:
        addon = addons.get(conn, vehicle_id, pk)
    if addon is None or addon.get("source_id") is None or not addon.get("pkg_sha"):
        return "svc.err_nosource"
    try:
        with db.tx() as conn:
            raw, sha = sources.fetch_package(conn, addon["source_id"], addon["kind"], addon["addon_id"], addon["m"].get("files"))
        if sha != addon["pkg_sha"]:
            return "svc.err_changed"
        service = addon["m"].get("service") or {}
        pluginsvc.store_package(addon["addon_id"], raw, sha, service.get("entry"), addon["m"].get("files"), addon["m"].get("bundles"))
    except sources.SourceError as exc:
        return str(exc)
    except ValueError:
        return "err.src_package"
    return None


def repair_all() -> list[dict]:
    """After a restore of the whole system: every installed package whose files are gone is fetched again from its source (one try each), and a service
    that is approved and switched on gets its environment made again. What cannot be fetched is marked on its card (``svc_error``)."""
    with db.tx() as conn:
        rows = [
            (r["vehicle_id"], r["id"])
            for r in conn.execute("SELECT vehicle_id, id FROM vehicle_addons WHERE pkg_sha IS NOT NULL AND status != 'missing'")
        ]
    results = []
    for vehicle_id, pk in rows:
        with db.tx() as conn:
            addon = addons.get(conn, vehicle_id, pk)
        if addon is None or not files_missing(addon):
            continue
        key = refetch(vehicle_id, pk)
        with db.tx() as conn:
            conn.execute("UPDATE vehicle_addons SET svc_error = ? WHERE id = ?", (None if key is None else "svc.err_files", pk))
        if key is None and addon["active"] and pluginsvc.service_of(addon) and pluginsvc.approved(addon):
            pluginsvc.install_async(pk)
        results.append({"addon_id": addon["addon_id"], "ok": key is None, "why": key or ""})
    if results:
        pluginsvc.kick()
    return results
