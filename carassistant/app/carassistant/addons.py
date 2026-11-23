"""Integrations and plugins of ONE vehicle: upload a package, set it up, change its settings, remove it.

A package is a ``plugin.json`` (or a zip holding it). Only this manifest is read and stored – nothing from a package is ever
executed. A plugin talks to Car Assistant from outside (in the car, on a Pi, ...) with the token created when it is set up.
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import sqlite3
import zipfile
from datetime import UTC, datetime

from . import connectors, vault

ID = re.compile(r"^[a-z0-9][a-z0-9_-]{1,40}$")
KEY = re.compile(r"^[a-z][a-z0-9_]{0,30}$")
KINDS = ("plugin", "integration")
PAGE_FIELD_TYPES = (
    "text",
    "textarea",
    "number",
    "bool",
    "select",
    "url",
    "hex",
    "date",
    "secret",
)  # what an integration page may hold per entry
MAX_PAGES = 6
MAX_PAGE_FIELDS = 20
FIELD_TYPES = (  # what a plugin may ask the user for in its settings page (docs/plugins.md)
    "text", "password", "textarea", "number", "slider", "bool", "select", "radio", "multiselect", "list", "url", "email", "time", "date", "color",
    "section", "info", "value",
)  # fmt: skip
NO_VALUE = ("section", "info")  # headings and texts: nothing to store
CHOICE = ("select", "radio", "multiselect")
MAX_OPTIONS = 30
MAX_PACKAGE = 100_000
MAX_MANIFEST = 60_000
MAX_FIELDS = 40


# optional integrations offered for every vehicle (nothing is added unless the user picks it)
# ---- the optional "service" of a plugin: its own process in this add-on (see pluginsvc.py and docs/plugins.md)
SERVICE_ENTRY = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./-]{0,100}\.py")
SERVICE_PYTHON = re.compile(r">=3\.\d{1,2}")
SERVICE_REQ = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,60}(\[[A-Za-z0-9_,-]{1,40}\])?"
    r"((==|>=|<=|~=|!=|<|>)[A-Za-z0-9.*+_-]{1,30}(,(==|>=|<=|~=|!=|<|>)[A-Za-z0-9.*+_-]{1,30})*)?"
)
SERVICE_PREFIX = re.compile(r"/[A-Za-z0-9_.-]{1,30}(/[A-Za-z0-9_.-]{1,30}){0,3}/")
SERVICE_HOST = re.compile(r"(\*\.)?[a-z0-9]([a-z0-9-]{0,60}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,60}[a-z0-9])?){1,6}")
SERVICE_ENV = re.compile(r"[A-Z][A-Z0-9_]{0,39}")
SERVICE_ENV_DENIED = ("PATH", "HOME", "USER", "SHELL", "LANG", "TZ", "SUPERVISOR_TOKEN", "HASSIO_TOKEN")
SERVICE_ENV_DENIED_START = ("CA_", "LD_", "PYTHON", "DYLD_", "CARASSISTANT_", "MQTT_")


def clean_service(raw: object) -> dict | None:
    """The ``service`` object of a manifest, cleaned. Raises AddonError when it is there but not usable (the package is refused)."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise AddonError("addon.err_service")
    entry = raw.get("entry")
    if not isinstance(entry, str) or not SERVICE_ENTRY.fullmatch(entry) or ".." in entry or "//" in entry:
        raise AddonError("addon.err_service")
    python = raw.get("python")
    if python is not None and not (isinstance(python, str) and SERVICE_PYTHON.fullmatch(python.replace(" ", ""))):
        raise AddonError("addon.err_service")
    reqs = raw.get("requirements") or []
    if (
        not isinstance(reqs, list)
        or len(reqs) > 30
        or not all(isinstance(r, str) and SERVICE_REQ.fullmatch(r.replace(" ", "")) for r in reqs)
    ):
        raise AddonError("addon.err_service")
    routes_in = raw.get("routes") or []
    if not isinstance(routes_in, list) or len(routes_in) > 10:
        raise AddonError("addon.err_service")
    routes = []
    for r in routes_in:
        prefix = r.get("prefix") if isinstance(r, dict) else None
        if not isinstance(prefix, str) or not SERVICE_PREFIX.fullmatch(prefix) or ".." in prefix:
            raise AddonError("addon.err_service")
        routes.append({"prefix": prefix, "public": r.get("public") is True})
    connects_in = (
        raw.get("connects") or []
    )  # the hosts the service says it talks to (shown for the approval; the app does not block others)
    if (
        not isinstance(connects_in, list)
        or len(connects_in) > 10
        or not all(isinstance(h, str) and SERVICE_HOST.fullmatch(h.lower()) for h in connects_in)
    ):
        raise AddonError("addon.err_service")
    env_in = raw.get("env") or {}
    if not isinstance(env_in, dict) or len(env_in) > 20:
        raise AddonError("addon.err_service")
    env = {}
    for name, value in env_in.items():
        if (
            not isinstance(name, str)
            or not SERVICE_ENV.fullmatch(name)
            or name in SERVICE_ENV_DENIED
            or name.startswith(SERVICE_ENV_DENIED_START)
            or not isinstance(value, str)
        ):
            raise AddonError("addon.err_service")
        env[name] = value[:200]
    return {
        "entry": entry,
        **({"python": python.replace(" ", "")} if python else {}),
        "requirements": [r.replace(" ", "") for r in reqs],
        "routes": routes,
        "env": env,
        **({"connects": [h.lower() for h in connects_in]} if connects_in else {}),
    }


DOWNLOAD_PATH = re.compile(r"/[A-Za-z0-9_./~%+-]{1,150}")


def clean_downloads(raw, service: dict | None) -> list[dict]:
    """Files a plugin's service offers for download: ``[{"label", "path", "note"}]``. The path must lie under one of the service's routes
    (the app shows a button; the file itself comes from the service). Anything else is dropped."""
    prefixes = [r["prefix"] for r in (service or {}).get("routes", [])]
    out: list[dict] = []
    for item in (raw if isinstance(raw, list) else [])[:10]:
        path = item.get("path") if isinstance(item, dict) else None
        if not isinstance(path, str) or not DOWNLOAD_PATH.fullmatch(path) or ".." in path or not any(path.startswith(p) for p in prefixes):
            continue
        out.append({"label": _text(item, "label", 60) or path.rsplit("/", 1)[-1], "path": path, "note": _text(item, "note", 200)})
    return out


# ---- files a package brings for download ("assets"): checked binaries the app hands out itself, never runs (docs/plugins.md)
FILE_EXTENSIONS = (".jar", ".zip", ".bin", ".json", ".txt", ".md", ".pdf")  # a fixed list - nothing that could be run
FILE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")
PKG_PATH = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./-]{0,158}")
MAX_FILES_N = 10
MAX_FILE_BYTES = 8_000_000
MAX_FILES_TOTAL = 20_000_000
MAX_BUNDLES = 5
MAX_BUNDLE_ENTRIES = 40
FILE_TYPES = {
    ".jar": "application/java-archive",
    ".zip": "application/zip",
    ".bin": "application/octet-stream",
    ".json": "application/json",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".pdf": "application/pdf",
}


def _safe_path(value: object) -> str | None:
    if not isinstance(value, str) or not PKG_PATH.fullmatch(value) or ".." in value.split("/") or value.startswith("/") or "//" in value:
        return None
    return value


def clean_files(raw) -> list[dict]:
    """The ``files`` of a manifest: ``[{"name", "path", "label", "note", "sha256", "size"}]``. Checksum and size are required; a file with a
    forbidden ending, a wrong shape or too big is a reason to refuse the whole package (a package must not half-arrive)."""
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > MAX_FILES_N:
        raise AddonError("addon.err_files")
    out: list[dict] = []
    total = 0
    for item in raw:
        if not isinstance(item, dict):
            raise AddonError("addon.err_files")
        name, path = item.get("name"), _safe_path(item.get("path"))
        sha, size = item.get("sha256"), item.get("size")
        ext = ("." + name.rsplit(".", 1)[-1].lower()) if isinstance(name, str) and "." in name else ""
        if (
            not isinstance(name, str)
            or not FILE_NAME.fullmatch(name)
            or ext not in FILE_EXTENSIONS
            or path is None
            or not path.lower().endswith(ext)
            or not isinstance(sha, str)
            or not re.fullmatch(r"[0-9a-f]{64}", sha.lower())
            or isinstance(size, bool)
            or not isinstance(size, int)
            or not 1 <= size <= MAX_FILE_BYTES
            or any(f["name"] == name or f["path"] == path for f in out)
        ):
            raise AddonError("addon.err_files")
        total += size
        out.append(
            {
                "name": name,
                "path": path,
                "label": _text(item, "label", 80) or name,
                "note": _text(item, "note", 300),
                "sha256": sha.lower(),
                "size": size,
            }
        )
    if total > MAX_FILES_TOTAL:
        raise AddonError("addon.err_files")
    return out


def clean_bundles(raw, files: list[dict]) -> list[dict]:
    """The ``bundles`` of a manifest: zip files the app builds on request from files of the package (its text files and its ``files``)."""
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > MAX_BUNDLES:
        raise AddonError("addon.err_files")
    out: list[dict] = []
    for item in raw:
        name = item.get("name") if isinstance(item, dict) else None
        entries_in = item.get("entries") if isinstance(item, dict) else None
        if (
            not isinstance(name, str)
            or not FILE_NAME.fullmatch(name)
            or not name.lower().endswith(".zip")
            or any(b["name"] == name for b in out)
            or any(f["name"] == name for f in files)
            or not isinstance(entries_in, list)
            or not 1 <= len(entries_in) <= MAX_BUNDLE_ENTRIES
        ):
            raise AddonError("addon.err_files")
        entries = []
        for e in entries_in:
            src, dst = _safe_path(e.get("from")) if isinstance(e, dict) else None, _safe_path(e.get("to")) if isinstance(e, dict) else None
            if src is None or dst is None or any(x["to"] == dst for x in entries):
                raise AddonError("addon.err_files")
            entries.append({"from": src, "to": dst})
        extra = {}
        if (
            isinstance(item, dict) and item.get("connection_file_to") is not None
        ):  # the connection file (with the token) goes into the zip at this path
            to = _safe_path(item.get("connection_file_to"))
            if to is None or any(x["to"] == to for x in entries):
                raise AddonError("addon.err_files")
            extra["connection_file_to"] = to
        if _l10n(item.get("l10n"), {"label": 80, "note": 300}):  # the texts in other languages, like the settings have
            extra["l10n"] = _l10n(item.get("l10n"), {"label": 80, "note": 300})
        out.append({"name": name, "label": _text(item, "label", 80) or name, "note": _text(item, "note", 300), "entries": entries, **extra})
    return out


def needs_package(manifest: dict) -> bool:
    """A package with a service, files or bundles comes as a ``package.zip`` of a source (its sha256 is checked); a plain description does not."""
    return bool(manifest.get("service") or manifest.get("files") or manifest.get("bundles"))


def approval_fingerprint(manifest: dict) -> str:
    """What an administrator approves: the description of the service and the list of files and bundles (names, checksums, sizes). A new
    version that changes any of it needs a new approval."""
    import hashlib

    thing = {
        "service": manifest.get("service"),
        "files": [(f["name"], f["sha256"], f["size"]) for f in manifest.get("files", [])],
        "bundles": manifest.get("bundles", []),
    }
    writable = sorted(f["key"] for f in manifest.get("settings", []) if f.get("service_writable") or f.get("type") == "value")
    if writable:  # only then: approvals given before the service could change settings stay valid
        thing["writable"] = writable
    frames = [(p["id"], p["route"]) for p in manifest.get("pages", []) if p.get("kind") == "frame"]
    if frames:  # only then: approvals given before frames existed stay valid
        thing["frames"] = frames
    return (
        hashlib.sha256(json.dumps(thing, sort_keys=True).encode()).hexdigest()
        if (thing["service"] or thing["files"] or thing["bundles"])
        else ""
    )


def service_fingerprint(service: dict | None) -> str:
    """What an administrator approves: the entry, the Python version, the requirements, the routes and the environment of the service."""
    import hashlib

    return hashlib.sha256(json.dumps(service, sort_keys=True).encode()).hexdigest() if service else ""


class AddonError(ValueError):
    def __init__(self, key: str):
        super().__init__(key)
        self.key = key


def _text(data: dict, key: str, limit: int) -> str:
    value = data.get(key)
    return " ".join(value.split())[:limit] if isinstance(value, str) else ""


LANG = re.compile(r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$")


def _l10n(raw, limits: dict[str, int]) -> dict[str, dict[str, str]]:
    """Translations of the texts of a package: ``{"de": {"label": "Adresse"}}`` - only the listed keys, only short texts."""
    out: dict[str, dict[str, str]] = {}
    for lang, texts in list((raw if isinstance(raw, dict) else {}).items())[:12]:
        if isinstance(lang, str) and LANG.match(lang) and isinstance(texts, dict):
            clean = {k: _text(texts, k, n) for k, n in limits.items() if _text(texts, k, n)}
            if clean:
                out[lang] = clean
    return out


FRAME_ROUTE = re.compile(r"/[A-Za-z0-9_./~%+-]{1,150}")


def _frame_page(page: dict, service: dict | None) -> dict:
    """A page that shows a page of the package's own service inside the app: ``route`` must lie under a NON-public route prefix of that
    service (docs/plugins.md). Anything else is an error: the package is refused when it is read."""
    route = page.get("route")
    prefixes = [r["prefix"] for r in (service or {}).get("routes", []) if not r.get("public")]
    if (
        not isinstance(route, str)
        or not FRAME_ROUTE.fullmatch(route)
        or ".." in route
        or "//" in route
        or not any(route.startswith(p) for p in prefixes)
    ):
        raise AddonError("addon.err_frame")
    from . import icons

    return {
        "id": page["id"],
        "kind": "frame",
        "title": _text(page, "title", 60) or page["id"],
        "route": route,
        "icon": page.get("icon") if page.get("icon") in icons.ICONS else "",
        "l10n": _l10n(page.get("l10n"), {"title": 60}),
        "fields": [],
    }


def clean_pages(raw, service: dict | None = None) -> list[dict]:
    """The pages a package describes: lists of entries with typed fields, plans, or - for a package with a service - frames (a page of that service
    shown inside the app). Only descriptions - the app draws and stores them."""
    pages: list[dict] = []
    for page in (raw if isinstance(raw, list) else [])[:MAX_PAGES]:
        if not isinstance(page, dict) or not isinstance(page.get("id"), str) or not KEY.match(page["id"]):
            continue
        if page.get("kind") == "frame":
            pages.append(_frame_page(page, service))
            continue
        fields: list[dict] = []
        for f in (page.get("fields") if isinstance(page.get("fields"), list) else [])[:MAX_PAGE_FIELDS]:
            if (
                not isinstance(f, dict)
                or not isinstance(f.get("key"), str)
                or not KEY.match(f["key"])
                or any(x["key"] == f["key"] for x in fields)
            ):
                continue
            field = {
                "key": f["key"],
                "label": _text(f, "label", 60) or f["key"],
                "type": f.get("type") if f.get("type") in PAGE_FIELD_TYPES else "text",
                "help": _text(f, "help", 200),
                "required": bool(f.get("required")),
                "once": bool(f.get("once")),  # written once, then fixed (e.g. an original value)
                "role": f.get("role") if f.get("role") in ("title", "subtitle") else "",
                "l10n": _l10n(f.get("l10n"), {"label": 60, "help": 200}),
            }
            if field["type"] == "select":
                opts = [
                    {"value": _text(o, "value", 40), "label": _text(o, "label", 60) or _text(o, "value", 40)}
                    for o in (f.get("options") if isinstance(f.get("options"), list) else [])[:MAX_OPTIONS]
                    if isinstance(o, dict) and _text(o, "value", 40)
                ]
                if opts:
                    field["options"] = opts
                else:
                    field["type"] = "text"
            if field["type"] == "hex" and isinstance(f.get("compare"), str) and KEY.match(f["compare"]):
                field["compare"] = f["compare"]  # shown byte by byte against that other hex field, differences marked
            fields.append(field)
        hexes = {x["key"] for x in fields if x["type"] == "hex"}
        for field in fields:
            if field.get("compare") not in hexes:
                field.pop("compare", None)
        if (
            page.get("kind") == "plan" and isinstance(page.get("reminder"), str) and KEY.match(page["reminder"])
        ):  # the page of a reminder with a plan
            pages.append(
                {
                    "id": page["id"],
                    "kind": "plan",
                    "reminder": page["reminder"],
                    "title": _text(page, "title", 60) or page["id"],
                    "item": "",
                    "empty": "",
                    "sortable": False,
                    "search": False,
                    "l10n": _l10n(page.get("l10n"), {"title": 60}),
                    "fields": [],
                }
            )
        elif fields:
            pages.append(
                {
                    "id": page["id"],
                    "title": _text(page, "title", 60) or page["id"],
                    "item": _text(page, "item", 60),
                    "empty": _text(page, "empty", 160),
                    "sortable": bool(page.get("sortable")),
                    "order": _order(page.get("order"), fields),
                    "search": bool(page.get("search")),  # a search box above the list
                    "l10n": _l10n(page.get("l10n"), {"title": 60, "item": 60, "empty": 160}),
                    "fields": fields,
                }
            )
    return pages


def _order(raw, fields: list[dict]) -> dict | None:
    """``{"by": <key of a field>, "dir": "asc" | "desc"}``: the entries of a page are listed sorted by that field (a date sorts right as written)."""
    if isinstance(raw, dict) and isinstance(raw.get("by"), str) and any(f["key"] == raw["by"] and f["type"] != "secret" for f in fields):
        return {"by": raw["by"], "dir": "asc" if raw.get("dir") == "asc" else "desc"}
    return None


MAX_INTERFACES = 40
DIRECTIONS = ("sends", "reads", "offers")  # to the app | from the app | an address or page the plugin itself offers


def clean_interfaces(raw) -> list[dict]:
    """What a plugin says about the interfaces it uses or offers (shown on its page *Interfaces*): ``direction`` (sends / reads / offers), a short
    ``name``, the ``path`` (an address of the Plugin API, of its service or of a page), the ``fields`` it touches and a ``note``."""
    out: list[dict] = []
    for item in (raw if isinstance(raw, list) else [])[:MAX_INTERFACES]:
        if not isinstance(item, dict) or item.get("direction") not in DIRECTIONS or not _text(item, "name", 80):
            continue
        entry = {
            "direction": item["direction"],
            "name": _text(item, "name", 80),
            "path": _text(item, "path", 200),
            "note": _text(item, "note", 300),
        }
        fields = item.get("fields")
        if isinstance(fields, list):
            entry["fields"] = [_text({"f": x}, "f", 60) for x in fields[:40] if isinstance(x, str) and _text({"f": x}, "f", 60)]
        out.append(entry)
    return out


MAX_TILES = 8
SIGNAL_NAME = re.compile(r"[a-z][a-z0-9_.]{0,63}")


def clean_tiles(raw) -> list[dict]:
    """Value tiles a plugin or integration puts on Home while it runs: ``[{"id", "label", "icon", "signal" | "data", "unit", "decimals"}]``. The
    value comes from a raw signal the plugin delivered (``signal``) or from a standard value (``data``, a number field of the Plugin API)."""
    from . import icons

    out: list[dict] = []
    for item in (raw if isinstance(raw, list) else [])[:MAX_TILES]:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("id"), str)
            or not KEY.match(item["id"])
            or any(t["id"] == item["id"] for t in out)
        ):
            continue
        signal, data = item.get("signal"), item.get("data")
        if isinstance(signal, str) and SIGNAL_NAME.fullmatch(signal):
            source = {"signal": signal}
        elif isinstance(data, str) and data in connectors.NUMBERS:
            source = {"data": data}
        else:
            continue
        tile = {
            "id": item["id"],
            "label": _text(item, "label", 40) or item["id"],
            "icon": item.get("icon") if item.get("icon") in icons.ICONS else "gauge",
            **source,
        }
        if _text(item, "unit", 16):
            tile["unit"] = _text(item, "unit", 16)
        if isinstance(item.get("decimals"), int) and 0 <= item["decimals"] <= 3:
            tile["decimals"] = item["decimals"]
        if _l10n(item.get("l10n"), {"label": 40}):
            tile["l10n"] = _l10n(item.get("l10n"), {"label": 40})
        out.append(tile)
    return out


def clean_reminders(raw) -> list[dict]:
    """Reminder rules of an integration: due after a number of kilometres or of refuels (the numbers come from the integration's settings)."""
    from . import icons

    out: list[dict] = []
    for r in (raw if isinstance(raw, list) else [])[:4]:
        if not isinstance(r, dict) or not isinstance(r.get("id"), str) or not KEY.match(r["id"]) or any(x["id"] == r["id"] for x in out):
            continue
        rule = {
            "id": r["id"],
            "title": _text(r, "title", 60) or r["id"],
            "text_due": _text(r, "text_due", 200),
            "icon": r.get("icon") if r.get("icon") in icons.ICONS else "bell-outline",
            "mode_setting": r["mode_setting"] if isinstance(r.get("mode_setting"), str) and KEY.match(r["mode_setting"]) else "",
            "km_setting": r["km_setting"] if isinstance(r.get("km_setting"), str) and KEY.match(r["km_setting"]) else "",
            "refuels_setting": r["refuels_setting"]
            if isinstance(r.get("refuels_setting"), str) and KEY.match(r["refuels_setting"])
            else "",
            "l10n": _l10n(r.get("l10n"), {"title": 60, "text_due": 200}),
            "range_setting": r["range_setting"] if isinstance(r.get("range_setting"), str) and KEY.match(r["range_setting"]) else "",
            "active_setting": r["active_setting"] if isinstance(r.get("active_setting"), str) and KEY.match(r["active_setting"]) else "",
            "plan": [],
        }
        for st in (r.get("plan") if isinstance(r.get("plan"), list) else [])[
            :8
        ]:  # a rotation: what happens at each refuel, round and round
            if isinstance(st, dict):
                rule["plan"].append(
                    {
                        "label": _text(st, "label", 60),
                        "setting": st["setting"] if isinstance(st.get("setting"), str) and KEY.match(st["setting"]) else "",
                        "amount_setting": st["amount_setting"]
                        if isinstance(st.get("amount_setting"), str) and KEY.match(st["amount_setting"])
                        else "",
                        "l10n": _l10n(st.get("l10n"), {"label": 60}),
                    }
                )
        rule["plan"] = [st for st in rule["plan"] if st["label"] or st["setting"]]
        if rule["km_setting"] or rule["refuels_setting"] or len(rule["plan"]) >= 2:
            out.append(rule)
    return out


FILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")
PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]{0,31})\}")
MAX_TEMPLATE = 2000


def clean_connection_file(raw) -> dict | None:
    """``{"name": "x.cfg", "template": "server={server}\\ntoken={token}\\n"}`` - a text file the plugin needs next to itself.

    Only text with ``{placeholders}`` is stored; nothing is executed. See docs/plugins.md."""
    if not isinstance(raw, dict) or not isinstance(raw.get("name"), str) or not FILE_NAME.match(raw["name"]):
        return None
    template = raw.get("template")
    if not isinstance(template, str) or not template.strip() or len(template) > MAX_TEMPLATE:
        return None
    return {"name": raw["name"], "template": template.replace("\r", "")}


def connection_file_text(manifest: dict, values: dict, *, token: str, vehicle: int, url: str, vin: str = "") -> str:
    """Fill the template of ``connection_file``: ``{token}``, ``{vehicle}`` (the id used in ``/api/v1/vehicles/<id>``), ``{url}`` (the external
    address, when one is set) and every setting of the plugin by its key. A line with an empty value is left out, so an unset optional
    setting never writes ``key=`` into the file. Values lose line breaks (one value can never add a line)."""
    known = {k: re.sub(r"^(-?\d+)\.0$", r"\1", str(v)) for k, v in values.items()}  # a number field stores 60.0: the file gets 60
    known.update({"token": token, "vehicle": str(vehicle), "url": url})
    if vin:
        known["vin"] = vin  # the VIN typed into the vehicle data wins over a setting of the same name
    out = []
    for line in manifest["connection_file"]["template"].split("\n"):
        names = PLACEHOLDER.findall(line)
        if names and any(not known.get(n, "").strip() for n in names):
            continue
        out.append(PLACEHOLDER.sub(lambda m: re.sub(r"[\r\n]+", " ", known.get(m.group(1), "")).strip(), line))
    return "\n".join(out).strip("\n") + "\n"


SETUP_REQUIRES = ("external_https", "vehicle_vin")
STEP_ID = re.compile(r"[a-z][a-z0-9_]{0,23}")


def _long(value, limit: int) -> str:
    """A text with its line breaks (a paragraph of instructions), cut to ``limit``."""
    if not isinstance(value, str):
        return ""
    return re.sub(r"\n{3,}", "\n\n", value.replace("\r", "")).strip()[:limit]


def clean_setup(
    raw,
    bundles: list[dict],
    has_file: bool,
    setting_keys: frozenset[str] | set[str] = frozenset(),
    frame_ids: frozenset[str] | set[str] = frozenset(),
) -> dict | None:
    """The ``setup`` of a manifest: a guide in steps (docs/plugins.md). ``requires`` lists what must be there first (an https address under System,
    a VIN in the vehicle data); a step may offer the token, the connection file and ``bundles`` of the package, and brings its own text."""
    if not isinstance(raw, dict) or not isinstance(raw.get("steps"), list):
        return None
    wanted = raw.get("requires") if isinstance(raw.get("requires"), list) else []
    names = {b["name"] for b in bundles}
    steps: list[dict] = []
    for st in raw["steps"][:8]:
        if (
            not isinstance(st, dict)
            or not isinstance(st.get("id"), str)
            or not STEP_ID.fullmatch(st["id"])
            or any(x["id"] == st["id"] for x in steps)
        ):
            continue
        step = {
            "id": st["id"],
            "title": _text(st, "title", 80),
            "text": _long(st.get("text"), 3000),
            "token": st.get("token") is True,
            "connection_file": st.get("connection_file") is True and has_file,
            "bundles": [n for n in (st.get("bundles") if isinstance(st.get("bundles"), list) else []) if isinstance(n, str) and n in names][
                :8
            ],
        }
        if (
            isinstance(st.get("page"), str) and st["page"] in frame_ids
        ):  # a page (kind frame) of the plugin's own service, opened from this step
            step["page"] = st["page"]
        if isinstance(st.get("settings"), list):  # the settings this step shows (opt-in: without it the guide shows all of them, as before)
            step["settings"] = [k for k in dict.fromkeys(st["settings"]) if isinstance(k, str) and k in setting_keys][:60]
        l10n = {}
        for lang, texts in list((st.get("l10n") if isinstance(st.get("l10n"), dict) else {}).items())[:12]:
            if isinstance(lang, str) and LANG.match(lang) and isinstance(texts, dict):
                one = {"title": _text(texts, "title", 80), "text": _long(texts.get("text"), 3000)}
                one = {k: v for k, v in one.items() if v}
                if one:
                    l10n[lang] = one
        if l10n:
            step["l10n"] = l10n
        steps.append(step)
    if not steps:
        return None
    return {"requires": [r for r in SETUP_REQUIRES if r in wanted], "steps": steps}


def render_text(text: str):
    """The text of a guide step as safe HTML: paragraphs, ``- `` / ``1. `` lists, ``**bold**`` and ``[label](https://...)`` links. Everything else is escaped."""
    from markupsafe import Markup, escape

    def inline(line: str) -> str:
        out = str(escape(line))
        out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
        return re.sub(
            r"\[([^\]]{1,100})\]\((https://[^\s)]{1,300})\)", r'<a href="\2" target="_blank" rel="noopener noreferrer">\1</a>', out
        )

    html, block, kind = [], [], ""

    def flush():
        nonlocal block, kind
        if block:
            if kind in ("ul", "ol"):
                html.append(f"<{kind}>" + "".join(f"<li>{inline(x)}</li>" for x in block) + f"</{kind}>")
            else:
                html.append("<p>" + "<br>".join(inline(x) for x in block) + "</p>")
        block, kind = [], ""

    for line in (text or "").split("\n"):
        stripped = line.strip()
        m_ul, m_ol = re.match(r"^[-*] +(.*)$", stripped), re.match(r"^\d+[.)] +(.*)$", stripped)
        want = "ul" if m_ul else "ol" if m_ol else "p"
        if not stripped:
            flush()
            continue
        if want != kind:
            flush()
            kind = want
        block.append((m_ul or m_ol).group(1) if (m_ul or m_ol) else stripped)
    flush()
    return Markup("".join(html))  # noqa: S704  every piece went through escape() first


def _options(f: dict) -> list[dict]:
    return [
        {"value": _text(o, "value", 40), "label": _text(o, "label", 60) or _text(o, "value", 40)}
        for o in (f.get("options") if isinstance(f.get("options"), list) else [])[:MAX_OPTIONS]
        if isinstance(o, dict) and _text(o, "value", 40) and "," not in _text(o, "value", 40)
    ]


def clean_setting_fields(raw) -> list[dict]:
    """The ``settings`` of a manifest: what the plugin asks for, as the settings page draws it. Unknown types become text; a choice without
    options becomes text; ``section`` and ``info`` are headings and texts without a value."""
    fields: list[dict] = []
    for i, f in enumerate((raw if isinstance(raw, list) else [])[:MAX_FIELDS]):
        if not isinstance(f, dict):
            continue
        kind = f.get("type") if f.get("type") in FIELD_TYPES else "text"
        key = f.get("key") if isinstance(f.get("key"), str) and KEY.match(f["key"]) else (f"_n{i}" if kind in NO_VALUE else None)
        if key is None or any(x["key"] == key for x in fields):
            continue
        field = {
            "key": key,
            "label": _text(f, "label", 60) or (key if kind not in NO_VALUE else ""),
            "type": kind,
            "help": _text(f, "help", 300),
        }
        if f.get("service_writable") is True and kind not in (*NO_VALUE, "list", "multiselect", "value"):
            field["service_writable"] = True  # the plugin's service may change this setting itself (the administrator approves the list)
        if f.get("advanced") is True and kind not in NO_VALUE:
            field["advanced"] = True  # the set-up guide shows it folded under "Advanced settings"
        if _text(f, "default", 200) and kind not in NO_VALUE:
            field["default"] = _text(f, "default", 200)  # what the setting is until the user changes it
        if _l10n(f.get("l10n"), {"label": 60, "help": 300}):
            field["l10n"] = _l10n(f.get("l10n"), {"label": 60, "help": 300})
        if kind in CHOICE:  # [{"value": "eco", "label": "Economy"}, ...]
            opts = _options(f)
            if not opts:
                field["type"] = kind = "text"
            else:
                field["options"] = opts
        if kind == "list":  # rows of a name and a value (for example stations and their addresses), at most 30
            field["name_label"] = _text(f, "name_label", 40) or "Name"
            field["value_label"] = _text(f, "value_label", 40) or "Address"
        if kind in ("number", "slider"):  # optional bounds: min, max, step
            for bound in ("min", "max", "step"):
                with contextlib.suppress(KeyError, TypeError, ValueError):
                    field[bound] = float(f[bound])
            if kind == "slider":
                field.setdefault("min", 0.0)
                field.setdefault("max", 100.0)
        if kind == "textarea":
            field["rows"] = min(12, max(2, int(f["rows"]))) if isinstance(f.get("rows"), int) else 4
        if f.get("required") is True and kind not in (*NO_VALUE, "bool", "list", "multiselect"):
            field["required"] = True
        for name, width in (("placeholder", 80), ("unit", 16)):
            if _text(f, name, width) and kind in ("text", "password", "textarea", "number", "slider", "url", "email", "select"):
                field[name] = _text(f, name, width)
        cond = f.get(
            "show_if"
        )  # only shown while another setting has this value: {"key": "mode", "equals": "custom"} (a switch: "equals": "1")
        if (
            isinstance(cond, dict)
            and isinstance(cond.get("key"), str)
            and KEY.match(cond["key"])
            and isinstance(cond.get("equals"), str | int | bool)
        ):
            equals = cond["equals"]
            field["show_if"] = {"key": cond["key"], "equals": ("1" if equals else "0") if isinstance(equals, bool) else str(equals)[:40]}
        fields.append(field)
    return fields


def parse_package(raw: bytes) -> dict:
    """Read and clean the manifest from a ``plugin.json`` or a zip. Raises AddonError(i18n key)."""
    if not raw or len(raw) > MAX_PACKAGE:
        raise AddonError("addon.err_size")
    if raw[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                info = next((i for i in z.infolist() if i.filename in ("plugin.json", "./plugin.json")), None)
                if info is None or info.file_size > MAX_MANIFEST:
                    raise AddonError("addon.err_manifest")
                raw = z.read(info)
        except zipfile.BadZipFile as exc:
            raise AddonError("addon.err_manifest") from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise AddonError("addon.err_manifest") from exc
    if not isinstance(data, dict) or not isinstance(data.get("id"), str) or not ID.match(data["id"]):
        raise AddonError("addon.err_id")
    homepage = _text(data, "homepage", 200)
    fields = clean_setting_fields(data.get("settings"))
    from .simulator import clean_scenario

    scenario = clean_scenario(data.get("simulation"))
    conn_file = clean_connection_file(data.get("connection_file"))
    from . import icons

    service = clean_service(data.get("service"))
    pages = clean_pages(data.get("pages"), service)
    reminders = clean_reminders(data.get("reminders"))
    interfaces = clean_interfaces(data.get("interfaces"))
    tiles = clean_tiles(data.get("tiles"))
    files = clean_files(data.get("files"))
    bundles = clean_bundles(data.get("bundles"), files)
    downloads = clean_downloads(data.get("downloads"), service)
    setup = clean_setup(
        data.get("setup"), bundles, bool(conn_file), {f["key"] for f in fields}, {p["id"] for p in pages if p.get("kind") == "frame"}
    )
    docs = (
        " ".join(str(data["docs"]).split())[:3000] if isinstance(data.get("docs"), str) else ""
    )  # a longer description for the Interfaces page
    icon = data.get("icon") if data.get("icon") in icons.ICONS else ""  # one of the app's icons (docs/icons.md); shown on the plugin's tile
    return {
        **({"icon": icon} if icon else ({"icon": "puzzle"} if pages else {})),
        **({"service": service} if service else {}),
        **({"interfaces": interfaces} if interfaces else {}),
        **({"tiles": tiles} if tiles else {}),
        **({"downloads": downloads} if downloads else {}),
        **({"files": files} if files else {}),
        **({"bundles": bundles} if bundles else {}),
        **({"setup": setup} if setup else {}),
        **({"docs": docs} if docs else {}),
        **({"reminders": reminders} if reminders else {}),
        **({"pages": pages, "nav": data.get("nav") is not False} if pages else {}),
        **({"l10n": _l10n(data.get("l10n"), {"name": 80, "description": 300})} if data.get("l10n") else {}),
        **(
            {"settings_page": data["settings_page"]}
            if isinstance(data.get("settings_page"), str) and data["settings_page"] in {p["id"] for p in pages if p.get("kind") == "frame"}
            else {}
        ),  # the plugin's own settings page (a frame); the field list stays as the fallback
        **({"connection_file": conn_file} if conn_file else {}),  # a file the plugin needs, offered for download with the token
        **({"simulation": scenario} if scenario else {}),  # a made-up drive the app may play for a plugin from a source (simulator.py)
        "id": data["id"],
        "kind": data.get("kind") if data.get("kind") in KINDS else "plugin",
        "name": _text(data, "name", 80) or data["id"],
        "version": _text(data, "version", 20),
        "description": _text(data, "description", 300),
        "author": _text(data, "author", 80),
        "homepage": homepage if homepage.startswith("https://") else "",
        "settings": fields,
    }


def add(conn: sqlite3.Connection, vehicle_id: int, manifest: dict, source_id: int | None = None, pkg_sha: str | None = None) -> int:
    if needs_package(manifest) and (source_id is None or not pkg_sha):
        raise AddonError("addon.err_service_upload")  # a package with a service only ever comes from a source, checked by its sha256
    existing = conn.execute(
        "SELECT id, status, settings, source_id FROM vehicle_addons WHERE vehicle_id = ? AND addon_id = ?", (vehicle_id, manifest["id"])
    ).fetchone()
    if existing and existing["status"] == "missing":
        # a restored entry waits for its package: the package arrives, the settings and the token of the backup stay; it stays OFF on purpose
        state = "configured" if json.loads(existing["settings"] or "{}") else "uploaded"
        conn.execute(
            "UPDATE vehicle_addons SET manifest = ?, status = ?, source_id = ?, active = 0, pkg_sha = ? WHERE id = ?",
            (json.dumps(manifest), state, source_id, pkg_sha, existing["id"]),
        )
        return existing["id"]
    if existing and source_id is not None and existing["source_id"] is None:
        # the same package, installed from a file or an older built-in offer, now comes from a source: it is taken over (settings, state and entries stay)
        conn.execute(
            "UPDATE vehicle_addons SET manifest = ?, source_id = ?, kind = ?, pkg_sha = ? WHERE id = ?",
            (json.dumps(manifest), source_id, manifest["kind"], pkg_sha, existing["id"]),
        )
        return existing["id"]
    if existing:
        raise AddonError("addon.err_exists")
    return conn.execute(
        "INSERT INTO vehicle_addons(vehicle_id, kind, addon_id, manifest, created_at, source_id, pkg_sha) VALUES(?,?,?,?,?,?,?)",
        (
            vehicle_id,
            manifest["kind"],
            manifest["id"],
            json.dumps(manifest),
            datetime.now(UTC).isoformat(timespec="seconds"),
            source_id,
            pkg_sha,
        ),
    ).lastrowid


def restore_all(conn: sqlite3.Connection, vehicle_id: int, entries: list, token_ids: dict) -> None:
    """Integrations and plugins from a vehicle backup: settings and token come back, the package itself is not part of a backup.
    Everything starts OFF. When the same package is already installed on this system it is used at once (still off, to be switched on on purpose);
    otherwise the entry waits as 'missing' until the package is installed from a source."""
    for entry in entries[:50]:
        if not isinstance(entry, dict) or not isinstance(entry.get("addon_id"), str) or not ID.match(entry["addon_id"]):
            continue
        kind = entry.get("kind") if entry.get("kind") in KINDS else "plugin"
        try:
            manifest = parse_package(json.dumps(entry.get("manifest") or {"id": entry["addon_id"]}).encode())
        except AddonError:
            continue
        manifest["kind"], manifest["id"] = kind, entry["addon_id"]
        values = {
            k: str(v)[:1000]
            for k, v in (entry.get("settings") or {}).items()
            if isinstance(k, str) and KEY.match(k) and isinstance(v, str | int | float)
        }
        have = conn.execute(
            "SELECT manifest, source_id FROM vehicle_addons WHERE addon_id = ? AND kind = ? AND status != 'missing' AND vehicle_id != ? ORDER BY id LIMIT 1",
            (entry["addon_id"], kind, vehicle_id),
        ).fetchone()
        status = "missing"
        source_id = None
        if have:
            manifest, source_id = json.loads(have["manifest"]), have["source_id"]
            status = "configured" if values else "uploaded"
        url = entry.get("source_url") if isinstance(entry.get("source_url"), str) else None
        conn.execute(
            "INSERT OR IGNORE INTO vehicle_addons(vehicle_id, kind, addon_id, manifest, status, settings, token_id, created_at, source_id, active, source_url) "
            "VALUES(?,?,?,?,?,?,?,?,?,0,?)",
            (
                vehicle_id,
                kind,
                entry["addon_id"],
                json.dumps(manifest),
                status,
                json.dumps(values),
                token_ids.get(entry.get("token_id")),
                datetime.now(UTC).isoformat(timespec="seconds"),
                source_id,
                url,
            ),
        )


def _newer_versions(conn: sqlite3.Connection, rows: list[sqlite3.Row]) -> dict[int, str]:
    """For installed packages that came from a source: the version that source offers now (by addon row id)."""
    out: dict[int, str] = {}
    for r in rows:
        if r["source_id"] is None:
            continue
        found = conn.execute(
            "SELECT version FROM source_packages WHERE source_id = ? AND kind = ? AND pkg_id = ?",
            (r["source_id"], r["kind"], r["addon_id"]),
        ).fetchone()
        if found:
            out[r["id"]] = found["version"]
    return out


def _need(conn: sqlite3.Connection, r: sqlite3.Row) -> dict:
    """What a restored entry still needs: install it from a source that offers it, or say which source has to be added first."""
    flag = "for_plugin" if r["kind"] == "plugin" else "for_integration"
    offer = conn.execute(
        f"SELECT p.source_id, s.name FROM source_packages p JOIN sources s ON s.id = p.source_id WHERE p.kind = ? AND p.pkg_id = ? AND s.{flag} = 1 "
        "ORDER BY (s.url = ?) DESC LIMIT 1",
        (r["kind"], r["addon_id"], r["source_url"] or ""),
    ).fetchone()
    if offer:
        return {"state": "offer", "source_id": offer["source_id"], "source": offer["name"]}
    url = r["source_url"]
    if url and conn.execute(f"SELECT 1 FROM sources WHERE url = ? AND {flag} = 1", (url,)).fetchone():
        return {"state": "update_sources", "url": url}  # the source is known, its list may be old
    return {"state": "add_source" if url else "upload", "url": url}


def list_for(conn: sqlite3.Connection, vehicle_id: int) -> list[dict]:
    from .sources import is_newer

    rows = conn.execute("SELECT * FROM vehicle_addons WHERE vehicle_id = ? ORDER BY id", (vehicle_id,)).fetchall()
    latest = _newer_versions(conn, rows)
    names = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM sources")}
    out = []
    from . import config

    lang = config.language()
    for r in rows:
        manifest = json.loads(r["manifest"])
        texts = (manifest.get("l10n") or {}).get(lang) or {}
        manifest = {
            **manifest,
            **{k: texts[k] for k in ("name", "description") if k in texts},
        }  # the package's own translation, when it has one
        manifest["settings"] = [
            {**f, **{k: v for k, v in ((f.get("l10n") or {}).get(lang) or {}).items() if k in ("label", "help")}}
            for f in manifest.get("settings", [])
        ]
        offered = latest.get(r["id"], "")
        need = _need(conn, r) if r["status"] == "missing" else None
        defaults = {f["key"]: f["default"] for f in manifest.get("settings", []) if "default" in f}
        secret = {f["key"] for f in manifest.get("settings", []) if f.get("type") == "password"}
        stored = {
            k: (vault.decrypt(v) if k in secret else v) for k, v in json.loads(r["settings"] or "{}").items()
        }  # passwords are encrypted at rest
        out.append(
            {
                **dict(r),
                "m": manifest,
                "vals": {**defaults, **stored},
                "latest": offered,
                "has_update": is_newer(offered, manifest.get("version", "")),
                "source_name": names.get(r["source_id"]),
                "debug": connectors.plugin_debug(conn, vehicle_id, r["addon_id"]),
                "missing": r["status"] == "missing",
                "need": need,
            }
        )
    return out


def get(conn: sqlite3.Connection, vehicle_id: int, addon_pk: int) -> dict | None:
    return next((a for a in list_for(conn, vehicle_id) if a["id"] == addon_pk), None)


LIST_ROWS = 30


def list_rows(value: str) -> list[dict]:
    """The rows of a ``list`` setting (stored as lines ``name | value``) as ``[{"name", "value"}]``."""
    rows = []
    for line in (value or "").splitlines():
        name, _sep, rest = line.partition("|")
        if name.strip() or rest.strip():
            rows.append({"name": name.strip(), "value": rest.strip()})
    return rows[:LIST_ROWS]


def _list_from_form(key: str, form: dict) -> str:
    lines = []
    for i in range(LIST_ROWS):
        name = " ".join(str(form.get(f"{key}__{i}n") or "").replace("|", " ").split())[:80]
        value = " ".join(str(form.get(f"{key}__{i}v") or "").replace("|", " ").split())[:200]
        if name or value:
            lines.append(f"{name} | {value}")
    return "\n".join(lines)


HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")
TIME = re.compile(r"([01]\d|2[0-3]):[0-5]\d")
DATE = re.compile(r"\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])")
EMAIL = re.compile(r"[^@\s]{1,64}@[^@\s]{1,200}\.[^@\s]{2,24}")
URL = re.compile(r"https?://[^\s<>\"']{3,300}")


def _picked(key: str, field: dict, form: dict) -> list[str]:
    """The ticked boxes of a ``multiselect`` (they are named ``<key>__<value>``), in the order of the options."""
    return [o["value"] for o in field.get("options", []) if form.get(f"{key}__{o['value']}")]


def _number(raw: str, f: dict) -> str | None:
    try:
        number = float(raw.replace(",", "."))
    except ValueError:
        return None
    low, high = f.get("min"), f.get("max")
    return str(min(high if high is not None else number, max(low if low is not None else number, number)))


def check_settings(manifest: dict, form: dict, old: dict) -> dict[str, str]:
    """What is wrong with the entered settings: ``{key: i18n error key}`` (empty = fine). Nothing is saved while this is not empty."""
    errors: dict[str, str] = {}
    for f in manifest["settings"]:
        key, kind = f["key"], f["type"]
        if kind in NO_VALUE or kind in ("bool", "list", "value"):
            continue
        shown = _is_shown(f, manifest, form)
        if not shown:
            continue
        if kind == "multiselect":
            continue
        raw = str(form.get(key) or "").strip()
        if not raw:
            if f.get("required") and not (kind == "password" and old.get(key)):
                errors[key] = "err.required"
            continue
        if kind in ("number", "slider") and _number(raw, f) is None:
            errors[key] = "err.number"
        elif kind == "url" and not URL.fullmatch(raw):
            errors[key] = "err.url"
        elif kind == "email" and not EMAIL.fullmatch(raw):
            errors[key] = "err.email"
        elif kind == "time" and not TIME.fullmatch(raw):
            errors[key] = "err.time"
        elif kind == "date" and not DATE.fullmatch(raw):
            errors[key] = "err.date"
        elif kind == "color" and not HEX_COLOR.fullmatch(raw):
            errors[key] = "err.color"
        elif kind in ("select", "radio") and raw not in {o["value"] for o in f.get("options", [])}:
            errors[key] = "err.choice"
    return errors


def _is_shown(f: dict, manifest: dict, form: dict) -> bool:
    cond = f.get("show_if")
    if not cond:
        return True
    other = next((x for x in manifest["settings"] if x["key"] == cond["key"]), None)
    if other is None:
        return True
    if other["type"] == "bool":
        current = "1" if form.get(other["key"]) else "0"
    elif other["type"] == "multiselect":
        current = ",".join(_picked(other["key"], other, form))
    else:
        current = str(form.get(other["key"]) or "").strip()
    return current == cond["equals"]


def clean_settings(manifest: dict, form: dict, old: dict) -> dict:
    values = {}
    for f in manifest["settings"]:
        key, kind = f["key"], f["type"]
        if kind in NO_VALUE:
            continue
        raw = (form.get(key) or "").strip()[: 200 if kind != "textarea" else 1000]
        if kind == "value":
            values[key] = old.get(key, "")  # a value shown for information: only the service sets it
        elif kind == "list":
            values[key] = _list_from_form(key, form)
        elif kind == "bool":
            values[key] = "1" if form.get(key) else "0"
        elif kind == "multiselect":
            values[key] = ",".join(_picked(key, f, form))
        elif kind == "password" and not raw:
            values[key] = old.get(key, "")  # blank = keep the stored secret
        elif kind in ("select", "radio"):
            values[key] = raw if raw in {o["value"] for o in f.get("options", [])} else old.get(key, "")
        elif kind in ("number", "slider"):
            values[key] = (_number(raw, f) or old.get(key, "")) if raw else ""
        elif kind == "url":
            values[key] = raw if URL.fullmatch(raw) else ("" if not raw else old.get(key, ""))
        elif kind == "email":
            values[key] = raw if EMAIL.fullmatch(raw) else ("" if not raw else old.get(key, ""))
        elif kind == "time":
            values[key] = raw if TIME.fullmatch(raw) else ("" if not raw else old.get(key, ""))
        elif kind == "date":
            values[key] = raw if DATE.fullmatch(raw) else ("" if not raw else old.get(key, ""))
        elif kind == "color":
            values[key] = raw.lower() if HEX_COLOR.fullmatch(raw) else ("" if not raw else old.get(key, ""))
        else:
            values[key] = raw
    return values


def typed_settings(manifest: dict, values: dict) -> dict:
    """The settings as a service gets them (settings.json): numbers as numbers, switches as true / false, a multiselect and a list as lists."""
    out: dict = {}
    for f in manifest.get("settings", []):
        key, kind, raw = f["key"], f["type"], values.get(f["key"], "")
        if kind in NO_VALUE:
            continue
        if kind == "bool":
            out[key] = raw == "1"
        elif kind in ("number", "slider"):
            try:
                number = float(raw)
                out[key] = int(number) if number == int(number) else number
            except ValueError:
                out[key] = None
        elif kind == "multiselect":
            out[key] = [x for x in raw.split(",") if x]
        elif kind == "list":
            out[key] = list_rows(raw)
        else:
            out[key] = raw
    return out


def _sealed(manifest: dict, values: dict) -> dict:
    """The settings as they are stored: the passwords encrypted (vault.py)."""
    secret = {f["key"] for f in manifest.get("settings", []) if f.get("type") == "password"}
    return {k: (vault.encrypt(v) if k in secret else v) for k, v in values.items()}


def guide_keys(addon: dict) -> set[str] | None:
    """The settings the set-up guide shows, when the package lists them per step (``setup.steps[].settings``); None = it lists none: the guide shows all."""
    steps = ((addon.get("m") or {}).get("setup") or {}).get("steps") or []
    listed = [s["settings"] for s in steps if s.get("settings") is not None]
    return {k for keys in listed for k in keys} if listed else None


def guide_manifest(addon: dict, keys: set[str] | None) -> dict:
    """The manifest as the guide sees it: only the listed settings (all when ``keys`` is None)."""
    m = addon["m"]
    return m if keys is None else {**m, "settings": [f for f in m.get("settings", []) if f["key"] in keys]}


def guide_form(addon: dict, form: dict, keys: set[str] | None) -> dict:
    """The form as it is judged by ``show_if``: what was typed for the listed settings, the stored value for the others (they are not in the page)."""
    if keys is None:
        return form
    merged = dict(form)
    for f in addon["m"].get("settings", []):
        if f["key"] in keys or f["type"] in NO_VALUE:
            continue
        stored = addon["vals"].get(f["key"], "")
        if f["type"] == "bool":
            if stored == "1":
                merged[f["key"]] = "1"
        elif stored not in ("", None):
            merged[f["key"]] = stored
    return merged


def token_by_guide(manifest: dict) -> bool:
    """A plugin with a set-up guide AND a connection file gets its token ONLY by the choice in step 2 (new / existing / kept): nothing makes one before
    (not the installation, not the start of its service, not saving the settings)."""
    return bool(manifest.get("setup") and manifest.get("connection_file"))


def set_up(conn: sqlite3.Connection, vehicle_id: int, addon: dict, form: dict, only: set[str] | None = None) -> str | None:
    """Mark as configured, save settings; a plugin gets its connection token (returned once)."""
    token = None
    token_id = addon["token_id"]
    # a plugin without service and without connection file gets its token here; a plugin with a connection file gets one ONLY by the explicit choice in
    # step 2 of the guide (new_token / adopt), never by saving settings; a service without connection file makes its own (pluginsvc.py)
    if (
        addon["kind"] == "plugin"
        and token_id is None
        and not token_by_guide(addon["m"])
        and (not addon["m"].get("service") or addon["m"].get("connection_file"))
    ):
        token = connectors.create_token(conn, f"{addon['m']['name']}", vehicle_id)
        token_id = conn.execute("SELECT id FROM api_tokens ORDER BY id DESC LIMIT 1").fetchone()["id"]
        if addon["m"].get("connection_file"):
            connectors.remember(conn, token_id, token)
    conn.execute(
        "UPDATE vehicle_addons SET status = 'configured', settings = ?, token_id = ? WHERE id = ?",
        (json.dumps(_sealed(addon["m"], _guide_values(addon, form, only))), token_id, addon["id"]),
    )
    return token


def writable_keys(addon: dict) -> set[str]:
    """The settings the plugin's service may change itself: the ones marked ``service_writable`` and every ``value``."""
    return {f["key"] for f in addon["m"].get("settings", []) if f.get("service_writable") or f["type"] == "value"}


def service_settings(addon: dict) -> dict:
    """The settings as the service reads them over the API: typed, passwords never (``"***"`` when set, "" when not)."""
    out = typed_settings(addon["m"], addon["vals"])
    for f in addon["m"].get("settings", []):
        if f["type"] == "password" and f["key"] in out:
            out[f["key"]] = "***" if addon["vals"].get(f["key"]) else ""
    return out


class SettingError(ValueError):
    def __init__(self, code: str, message: str, fields: dict[str, str] | None = None):
        super().__init__(message)
        self.code, self.fields = code, fields or {}


def service_set(conn: sqlite3.Connection, addon: dict, changes: dict) -> list[str]:
    """The service changes some of its own settings: only writable keys, checked like the form, nothing is stored when one is wrong. Returns the keys."""
    if not isinstance(changes, dict) or not changes:
        raise SettingError("invalid_body", "'values' must be an object with the settings to change.")
    allowed = writable_keys(addon)
    refused = sorted(k for k in changes if k not in allowed)
    if refused:
        raise SettingError(
            "not_writable", f"The service may not change: {', '.join(refused)}. Allowed: {', '.join(sorted(allowed)) or 'nothing'}."
        )
    fields = {f["key"]: f for f in addon["m"]["settings"]}
    form: dict[str, str] = {}
    for key, value in changes.items():
        kind = fields[key]["type"]
        if kind == "bool":
            if value in (True, 1, "1", "true", "yes", "on"):
                form[key] = "1"
        elif value is None:
            form[key] = ""
        elif isinstance(value, bool) or not isinstance(value, str | int | float):
            raise SettingError("invalid_value", f"'{key}' must be a text or a number.", {key: "err.choice"})
        else:
            form[key] = str(value)
    only = set(changes)
    sub = guide_manifest(addon, only)
    errors = check_settings(sub, guide_form(addon, form, only), addon["vals"])
    if errors:
        raise SettingError("invalid_value", "One or more values are not valid.", errors)
    new = {**addon["vals"], **clean_settings(sub, form, addon["vals"])}
    for key in changes:
        if fields[key]["type"] == "value":
            new[key] = form.get(key, "")[:200]  # the service sets what it shows
    conn.execute("UPDATE vehicle_addons SET settings = ? WHERE id = ?", (json.dumps(_sealed(addon["m"], new)), addon["id"]))
    return sorted(changes)


def _guide_values(addon: dict, form: dict, only: set[str] | None) -> dict:
    """The values to store after the guide: all settings as typed, or - when the guide shows only some - those, the others keep their value."""
    if only is None:
        return clean_settings(addon["m"], form, addon["vals"])
    return {**addon["vals"], **clean_settings(guide_manifest(addon, only), form, addon["vals"])}


def new_token(conn: sqlite3.Connection, vehicle_id: int, addon: dict) -> str:
    if addon["token_id"]:
        connectors.delete_token(conn, addon["token_id"])
    token = connectors.create_token(conn, addon["m"]["name"], vehicle_id)
    token_id = conn.execute("SELECT id FROM api_tokens ORDER BY id DESC LIMIT 1").fetchone()["id"]
    conn.execute("UPDATE vehicle_addons SET token_id = ? WHERE id = ?", (token_id, addon["id"]))
    if addon["m"].get("connection_file"):
        connectors.remember(conn, token_id, token)
    return token


def update_manifest(conn: sqlite3.Connection, addon: dict, manifest: dict, pkg_sha: str | None = None) -> None:
    """A newer version from the source: replace the description, keep the settings, the token and the state. When the service description
    changed, the approval no longer matches (service_fingerprint) and the service waits for a new one."""
    if needs_package(manifest) and not pkg_sha:
        raise AddonError("addon.err_service_upload")
    conn.execute(
        "UPDATE vehicle_addons SET manifest = ?, pkg_sha = COALESCE(?, pkg_sha) WHERE id = ?", (json.dumps(manifest), pkg_sha, addon["id"])
    )


def set_active(conn: sqlite3.Connection, addon: dict, on: bool) -> None:
    conn.execute("UPDATE vehicle_addons SET active = ? WHERE id = ?", (1 if on else 0, addon["id"]))
    if not on and addon["kind"] == "integration":
        from . import navigation

        navigation.forget(conn, addon["vehicle_id"], navigation.X + addon["addon_id"])  # its place in the order goes; it rejoins at the end


def remove(conn: sqlite3.Connection, addon: dict) -> None:
    connectors.delete_logs(conn, addon["vehicle_id"], addon["addon_id"], addon["m"].get("name", ""))  # its log lines go with it
    connectors.set_plugin_debug(conn, addon["vehicle_id"], addon["addon_id"], False)
    if addon["token_id"]:
        connectors.delete_token(conn, addon["token_id"])
    conn.execute("DELETE FROM vehicle_addons WHERE id = ?", (addon["id"],))
    if addon["kind"] == "integration":
        from . import navigation

        navigation.forget(conn, addon["vehicle_id"], navigation.X + addon["addon_id"])
