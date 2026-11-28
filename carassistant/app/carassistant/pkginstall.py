"""Installing a package from a source, outside any web request: the files of a package with a service, files or bundles (docs/plugins.md).

The Install and Update buttons (addons_web) and the set-up of a restored car (restoresetup) both need it."""

from __future__ import annotations

from . import addons, db, pluginsvc, sources, updprogress


def fetch_files(manifest: dict, source_id: int, kind: str, pkg_id: str) -> str | None:
    """A package with a service, files or bundles: fetch its zip from the source (the index names the sha256, and every file with its checksum), check it
    and unpack it - nothing runs. Returns the sha256; None for a plain description."""
    if not addons.needs_package(manifest):
        return None
    with db.tx() as conn:
        raw, sha = sources.fetch_package(conn, source_id, kind, pkg_id, manifest.get("files"))
    updprogress.report("check")  # (the bar of an update: what has come is checked and unpacked now)
    try:
        pluginsvc.store_package(
            pkg_id, raw, sha, (manifest.get("service") or {}).get("entry"), manifest.get("files"), manifest.get("bundles")
        )
    except ValueError as exc:
        raise sources.SourceError("err.src_package") from exc
    return sha
