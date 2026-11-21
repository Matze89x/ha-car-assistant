"""Builds the package.zip of a plugin with a service from its readable folder and writes its sha256 into the index of the source.

    python tools/build_plugin_package.py <source folder> <plugin id>

The folder ``<source>/plugins/<id>/`` holds ``plugin.json`` and the service files (readable text; see docs/plugins.md). The zip is built the same
way every time (sorted files, fixed time), so the checksum only changes when a file changes. Commit the folder, the zip and the index together:
people can read every file on GitHub before they approve the plugin.
"""

import hashlib
import json
import sys
import zipfile
from pathlib import Path

READABLE = {
    ".py",
    ".sh",
    ".json",
    ".txt",
    ".md",
    ".html",
    ".css",
    ".js",
    ".svg",
    ".yaml",
    ".yml",
    ".toml",
    ".cfg",
    ".ini",
    ".csv",
    ".xml",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".ico",
    "",
}


def main(source: str, plugin_id: str) -> None:
    folder = Path(source) / "plugins" / plugin_id
    manifest_file = folder / "plugin.json"
    manifest = json.loads(manifest_file.read_text())
    assets = {}
    for item in manifest.get("files") or []:  # the downloadable files: checksum and size are taken from the real file
        path = folder / item["path"]
        if not path.is_file():
            sys.exit(f"The file {item['path']} listed under 'files' is not in the folder.")
        data = path.read_bytes()
        item["sha256"], item["size"] = hashlib.sha256(data).hexdigest(), len(data)
        assets[item["path"]] = item
    if assets:
        manifest_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    files = sorted(p for p in folder.rglob("*") if p.is_file() and p.name != "package.zip" and not p.name.startswith("."))
    bad = [str(p.relative_to(folder)) for p in files if p.suffix.lower() not in READABLE and str(p.relative_to(folder)) not in assets]
    if bad:
        sys.exit(f"Not readable text or plain images (not allowed in a package unless listed under 'files'): {', '.join(bad)}")
    target = folder / "package.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for path in files:
            info = zipfile.ZipInfo(str(path.relative_to(folder)), date_time=(2020, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            z.writestr(info, path.read_bytes(), zipfile.ZIP_DEFLATED)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    index_file = Path(source) / "plugins" / "index.json"
    index = json.loads(index_file.read_text()) if index_file.exists() else {"packages": []}
    entries = index.setdefault("packages", [])
    entry = next((e for e in entries if e.get("id") == plugin_id), None)
    if entry is None:
        entry = {
            "id": plugin_id,
            "name": manifest.get("name", plugin_id),
            "version": manifest.get("version", ""),
            "description": manifest.get("description", ""),
        }
        entries.append(entry)
    entry["sha256"] = digest
    if assets:
        entry["files"] = [
            {"name": f["name"], "sha256": f["sha256"], "size": f["size"]} for f in assets.values()
        ]  # the index names every file, too
    else:
        entry.pop("files", None)
    index_file.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n")
    print(f"{target}  sha256 {digest}" + (f"  ({len(assets)} file(s) listed in the index)" if assets else ""))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
