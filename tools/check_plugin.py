"""Checks a package the way Car Assistant will read it - and tells you what is wrong in plain words.

    python tools/check_plugin.py <folder | plugin.json | package.zip>

For a folder (plugins/<id>/ of a source) it also checks the service files, the icon, the checksum of package.zip against the index and
typos in the names of the fields (a misspelt key is silently ignored by the app, this tool shows it). Exit code 1 when something is wrong.
"""

import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "carassistant" / "app"))

from carassistant import addons, i18n, icons

KNOWN = {
    "id", "kind", "name", "version", "description", "author", "homepage", "icon", "nav", "settings", "pages", "reminders", "tiles", "interfaces", "docs", "downloads",
    "l10n", "connection_file", "simulation", "service", "setup", "bundles", "files", "capabilities", "settings_page", "buttons",
}  # fmt: skip
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


def load(target: Path) -> tuple[bytes, Path | None]:
    if target.is_dir():
        return (target / "plugin.json").read_bytes(), target
    return target.read_bytes(), None


def check(target: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    notes: list[str] = []
    try:
        raw, folder = load(target)
    except OSError as exc:
        return [f"Cannot read {target}: {exc}"], []
    text = raw
    if raw[:2] == b"PK":
        with zipfile.ZipFile(target) as z:
            text = z.read("plugin.json")
    try:
        data = json.loads(text)
    except ValueError as exc:
        return [f"plugin.json is not valid JSON: {exc}"], []
    for key in sorted(set(data) - KNOWN):
        notes.append(f"Unknown key '{key}' in plugin.json - ignored by the app (a typo?). Known keys: {', '.join(sorted(KNOWN))}")

    # texts the app cuts without a word (addons._text): say so here
    def long_texts(node, where: str) -> None:
        """Warn about a label / help that is longer than the app keeps (also inside l10n)."""
        if isinstance(node, dict):
            for key, limit in (("label", 60), ("help", 300)):
                value = node.get(key)
                if isinstance(value, str) and len(" ".join(value.split())) > limit:
                    notes.append(
                        f"{where}: '{key}' has {len(' '.join(value.split()))} characters - the app keeps {limit} and cuts the rest ({value[:30]}...)"
                    )
            if node.get("type") == "tab" and isinstance(node.get("label"), str) and len(node["label"]) > 40:
                notes.append(f"{where}: the label of a tab is cut at 40 characters")
            for k, v in node.items():
                long_texts(v, f"{where}.{k}" if k != "settings" else where)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                long_texts(v, where)

    long_texts({k: data[k] for k in ("settings", "pages", "l10n") if k in data}, "plugin.json")
    try:
        manifest = addons.parse_package(raw)
    except addons.AddonError as exc:
        errors.append(i18n.EN.get(f"{exc}", str(exc)))
        return errors, notes
    if folder is not None and folder.name != manifest["id"]:
        errors.append(f"The folder is called '{folder.name}' but the id is '{manifest['id']}': in a source they must be the same.")
    if not data.get("description"):
        notes.append("No description: the tile shows nothing under the name.")
    if not data.get("version"):
        notes.append("No version: updates cannot be offered.")
    if data.get("icon") and data["icon"] not in icons.ICONS:
        notes.append(f"Icon '{data['icon']}' is not in the icon set (docs/icons.md) - the default icon is shown.")
    if not data.get("icon"):
        notes.append("No icon: the default (plug / puzzle piece) is shown. Pick one from docs/icons.md.")
    if not manifest.get("l10n"):
        notes.append("No translations (l10n): the texts are shown as written in every language.")
    keys = [f["key"] for f in manifest.get("settings", [])]
    for key in {k for k in keys if keys.count(k) > 1}:
        errors.append(f"Setting key '{key}' is used twice.")
    for field in data.get("settings", []) if isinstance(data.get("settings"), list) else []:
        if isinstance(field, dict) and field.get("type") not in (None, *addons.FIELD_TYPES):
            notes.append(
                f"Setting '{field.get('key')}': the type '{field.get('type')}' is unknown (becomes text). Types: {', '.join(addons.FIELD_TYPES)}"
            )
    for field in manifest.get("settings", []):
        cond = field.get("show_if")
        if cond and cond["key"] not in keys:
            errors.append(f"Setting '{field['key']}': show_if refers to '{cond['key']}', which is not a setting.")
    for field in data.get("settings", []) if isinstance(data.get("settings"), list) else []:
        if (
            isinstance(field, dict)
            and field.get("type") in addons.CHOICE
            and field.get("key")
            and not any(f["key"] == field["key"] and f["type"] in addons.CHOICE for f in manifest.get("settings", []))
        ):
            notes.append(
                f"Setting '{field['key']}': a choice needs 'options' (each with a 'value' without a comma) - it became a text field."
            )
    asked = data.get("downloads") if isinstance(data.get("downloads"), list) else []
    if len(asked) != len(manifest.get("downloads", [])):
        notes.append(
            "Some 'downloads' were dropped: a path must start with one of the service routes (service.routes[].prefix) and use plain characters."
        )
    asked_buttons = data.get("buttons") if isinstance(data.get("buttons"), list) else []
    kept_buttons = {b["id"] for b in manifest.get("buttons", [])}
    lost = [
        str(b.get("id") if isinstance(b, dict) else b)[:30]
        for b in asked_buttons
        if not isinstance(b, dict) or b.get("id") not in kept_buttons
    ]
    if lost or len(asked_buttons) > addons.MAX_BUTTONS:
        notes.append(
            f"Buttons dropped: {', '.join(lost) or 'the ones after the third'} - a button needs a unique id (a-z0-9_-), a label and EITHER a 'page' "
            f"(the id of one of your frame pages) OR an 'action' (a route under a NON-public service route prefix); at most {addons.MAX_BUTTONS}."
        )
    setup = data.get("setup") if isinstance(data.get("setup"), dict) else {}
    asked_flow = setup.get("flow") if isinstance(setup.get("flow"), list) else []
    kept_flow = {st["id"] for st in (manifest.get("setup") or {}).get("flow", [])}
    lost = [
        str(st.get("id") if isinstance(st, dict) else st)[:30]
        for st in asked_flow
        if not isinstance(st, dict) or st.get("id") not in kept_flow
    ]
    if lost or len(asked_flow) > addons.MAX_FLOW:
        notes.append(
            f"Set-up steps dropped: {', '.join(lost) or 'the ones after the twelfth'} - a step needs a unique id (a-z0-9_), a 'type' ({', '.join(addons.FLOW_TYPES)}) "
            "and what its type needs: form = 'settings'; check / download = an 'action' under a NON-public route prefix; page = the id of a frame page; "
            "requirements = 'requires' or 'filled'."
        )
    if folder is not None and (manifest.get("files") or manifest.get("bundles")):
        index_entry = None
        index = folder.parent / "index.json"
        if index.is_file():
            index_entry = next((e for e in json.loads(index.read_text()).get("packages", []) if e.get("id") == manifest["id"]), None)
        for f in manifest.get("files", []):
            path = folder / f["path"]
            if not path.is_file():
                errors.append(f"File '{f['path']}' is listed under 'files' but is not in the folder.")
                continue
            blob = path.read_bytes()
            if len(blob) != f["size"] or hashlib.sha256(blob).hexdigest() != f["sha256"]:
                errors.append(
                    f"File '{f['name']}': size or sha256 in plugin.json does not match the file - run tools/build_plugin_package.py."
                )
            if index_entry is not None and not any(
                x.get("name") == f["name"] and x.get("sha256") == f["sha256"] and x.get("size") == f["size"]
                for x in index_entry.get("files") or []
            ):
                errors.append(
                    f"File '{f['name']}' is not in plugins/index.json with this sha256 and size - run tools/build_plugin_package.py."
                )
        known = {f["path"] for f in manifest.get("files", [])}
        for b in manifest.get("bundles", []):
            for e in b["entries"]:
                if e["from"] not in known and not (folder / e["from"]).is_file():
                    errors.append(f"Bundle '{b['name']}': '{e['from']}' is not a file of the package.")
        names = {f["name"] for f in manifest.get("files", [])} | {b["name"] for b in manifest.get("bundles", [])}
        for ref in re.findall(r"\{file:([^}]+)\}", data.get("docs", "") if isinstance(data.get("docs"), str) else ""):
            if ref not in names:
                errors.append(f"docs refers to {{file:{ref}}}, which is neither a file nor a bundle.")
    service = manifest.get("service")
    if service:
        if folder is None:
            notes.append("A service can only be checked in a folder (plugins/<id>/).")
        else:
            if not (folder / service["entry"]).is_file():
                errors.append(f"The service entry '{service['entry']}' is not in the folder.")
            for p in sorted(folder.rglob("*")):
                if (
                    p.is_file()
                    and p.name != "package.zip"
                    and p.suffix.lower() not in READABLE
                    and str(p.relative_to(folder)) not in {f["path"] for f in manifest.get("files", [])}
                ):
                    errors.append(f"{p.relative_to(folder)}: only text files and plain images are allowed in a package (no binaries).")
            for route in service["routes"]:
                if route["prefix"].split("/")[1] in {
                    "api",
                    "v",
                    "static",
                    "integrations",
                    "settings",
                    "account",
                    "sources",
                    "setup",
                    "vehicles",
                    "auth",
                    "media",
                    "healthz",
                }:
                    errors.append(f"Route {route['prefix']} would cover a page of the app.")
            zip_file = folder / "package.zip"
            index = folder.parent / "index.json"
            if not zip_file.is_file():
                (errors if index.is_file() else notes).append("package.zip is missing - run tools/build_plugin_package.py.")
            elif index.is_file():
                entry = next((e for e in json.loads(index.read_text()).get("packages", []) if e.get("id") == manifest["id"]), None)
                if entry is None or entry.get("sha256") != hashlib.sha256(zip_file.read_bytes()).hexdigest():
                    errors.append("The sha256 in index.json does not match package.zip - run tools/build_plugin_package.py again.")
    return errors, notes


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    errors, notes = check(Path(sys.argv[1]))
    for n in notes:
        print(f"note:  {n}")
    for e in errors:
        print(f"ERROR: {e}")
    print("OK - the package can be read." if not errors else f"{len(errors)} problem(s).")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
