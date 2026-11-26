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
from urllib.parse import urlsplit

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
    "section", "info", "value", "tab",
)  # fmt: skip
NO_VALUE = ("section", "info", "tab")  # headings, texts and tabs: nothing to store
CHOICE = ("select", "radio", "multiselect")
MAX_OPTIONS = 30
MAX_PACKAGE = 100_000
MAX_MANIFEST = 60_000
MAX_FIELDS = 40
MAX_TABS = 12  # tabs of a settings page; they do not count as fields


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
SERVICE_TOKEN_HEADER = re.compile(r"[A-Za-z][A-Za-z0-9-]{1,39}")
SERVICE_TOKEN_HEADER_DENIED = {
    "host",
    "cookie",
    "authorization",
    "proxy-authorization",
    "connection",
    "keep-alive",
    "te",
    "trailer",
    "upgrade",
    "origin",
    "referer",
    "user-agent",
    "accept",
    "x-requested-with",
}  # headers the proxy, the browser or the network own: a service cannot use them as its key
SERVICE_TOKEN_HEADER_DENIED_START = ("x-ca-", "content-", "transfer-", "sec-", "proxy-", "x-forwarded-", "x-ingress", "x-hass", "cf-")
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
        route = {"prefix": prefix, "public": r.get("public") is True}
        header = r.get("token_header")
        if (
            header is not None
        ):  # present but not usable = the package is refused: a hardening that is silently dropped would leave the route open
            if (
                not route["public"]
                or not isinstance(header, str)
                or not SERVICE_TOKEN_HEADER.fullmatch(header)
                or header.lower() in SERVICE_TOKEN_HEADER_DENIED
                or header.lower().startswith(SERVICE_TOKEN_HEADER_DENIED_START)
            ):
                raise AddonError("addon.err_service")
            route["token_header"] = header
        routes.append(route)
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
    token = raw.get("token")
    if token is not None and not isinstance(token, bool):  # ``false`` = a service without a token; anything but a yes/no is refused
        raise AddonError("addon.err_service")
    files = raw.get("files")
    if files is not None and files != "read":  # ``"read"``: the service may READ the files of the package; nothing else exists
        raise AddonError("addon.err_service")
    return {
        "entry": entry,
        **({"token": False} if token is False else {}),
        **({"files": "read"} if files == "read" else {}),
        **({"python": python.replace(" ", "")} if python else {}),
        "requirements": [r.replace(" ", "") for r in reqs],
        "routes": routes,
        "env": env,
        **({"connects": [h.lower() for h in connects_in]} if connects_in else {}),
    }


DOWNLOAD_PATH = re.compile(r"/[A-Za-z0-9_./~%+-]{1,150}")


def clean_downloads(raw, service: dict | None, setting_types: dict[str, str] | None = None) -> list[dict]:
    """Files a plugin's service offers for download: ``[{"label", "path", "note", "place", "when"}]``. The path must lie under one of the service's
    routes (the app shows a button; the file itself comes from the service). ``place`` is ``tile`` (default) or ``settings`` (the tab *General* of the
    settings page); ``when`` says when the button shows (``clean_when``). Anything else is dropped."""
    prefixes = [r["prefix"] for r in (service or {}).get("routes", [])]
    out: list[dict] = []
    for item in (raw if isinstance(raw, list) else [])[:10]:
        path = item.get("path") if isinstance(item, dict) else None
        if not isinstance(path, str) or not DOWNLOAD_PATH.fullmatch(path) or ".." in path or not any(path.startswith(p) for p in prefixes):
            continue
        when = clean_when(item.get("when"), setting_types or {})
        if when is None:  # a condition that cannot be read: the button stays away rather than show when it should not
            continue
        out.append(
            {
                "label": _text(item, "label", 60) or path.rsplit("/", 1)[-1],
                "path": path,
                "note": _text(item, "note", 200),
                **({"place": "settings"} if item.get("place") == "settings" else {}),
                **({"when": when} if when else {}),
                **(
                    {"l10n": texts} if (texts := _l10n(item.get("l10n"), {"label": 60, "note": 200})) else {}
                ),  # label / note in other languages
            }
        )
    return out


# ---- conditions (``when``): when a button or a download shows, and when the set-up counts as done (docs/plugins.md, "Conditions")
WHEN_TESTS = 5  # at most this many tests in one ``when`` (all must hold)


def clean_when(raw, setting_types: dict[str, str], allow_setup: bool = True) -> list[dict] | None:
    """The ``when`` of a button, a download or the ``done_when`` of the set-up: ONE test or a list of up to 5 (all must hold). A test is
    ``{"setup": "done" | "open"}``, ``{"token": true | false}``, ``{"key": "<setting>", "equals": value}`` or ``{"key": "<setting>", "set": true | false}``.
    No ``when`` gives ``[]``; a ``when`` that cannot be read gives ``None`` - the caller then drops the thing it belongs to (a condition that is
    silently ignored would show what the plugin meant to hide)."""
    if raw is None:
        return []
    tests_in = raw if isinstance(raw, list) else [raw]
    if not tests_in or len(tests_in) > WHEN_TESTS:
        return None
    out: list[dict] = []
    for t in tests_in:
        if not isinstance(t, dict):
            return None
        if "setup" in t:
            if not allow_setup or t["setup"] not in ("done", "open"):
                return None
            out.append({"setup": t["setup"]})
        elif "token" in t:
            if not isinstance(t["token"], bool):
                return None
            out.append({"token": t["token"]})
        elif "downloaded" in t:  # true / false = any file of the package, or the name of one bundle or file
            what = t["downloaded"]
            if not isinstance(what, bool) and not (isinstance(what, str) and FILE_NAME.fullmatch(what)):
                return None
            out.append({"downloaded": what})
        elif isinstance(t.get("key"), str) and t["key"] in setting_types and setting_types[t["key"]] not in NO_VALUE:
            if isinstance(t.get("equals"), str | int | bool):
                value = t["equals"]
                out.append({"key": t["key"], "equals": ("1" if value else "0") if isinstance(value, bool) else str(value)[:40]})
            elif isinstance(t.get("set"), bool):
                out.append({"key": t["key"], "set": t["set"]})
            else:
                return None
        else:
            return None
    return out


def when_holds(
    tests: list[dict], *, setup_done: bool, has_token: bool, values: dict, types: dict[str, str], delivered: frozenset[str] = frozenset()
) -> bool:
    """Do all tests of a ``when`` hold right now? ``values`` are the stored settings (a switch is ``1`` / ``0``, a password never counts as set
    here because it is not in ``values`` readable)."""
    for t in tests:
        if "setup" in t:
            ok = setup_done == (t["setup"] == "done")
        elif "token" in t:
            ok = has_token == t["token"]
        elif "downloaded" in t:
            what = t["downloaded"]
            ok = (what in delivered) if isinstance(what, str) else (bool(delivered) == what)
        else:
            have = values.get(t["key"], "")
            if "equals" in t:
                ok = str(have) == t["equals"]
            else:
                filled = have not in ("", None) and not (types.get(t["key"]) == "bool" and str(have) == "0")
                ok = filled == t["set"]
        if not ok:
            return False
    return True


def version_state(have: str, offered: str) -> str:
    """What a file the plugin offers (``offered``) means for what lies on the car (``have``): ``update`` (the offer is newer), ``current``,
    or ``newer`` (the car has a newer one); ``""`` when the plugin did not say what is on the car."""
    from .sources import version_key

    if not have or not offered:
        return ""

    def plain(text: str) -> str:  # "v8", "V8", "Build 7" and "8" are versions by their numbers; so are "V1.21" and "1.21"
        text = text.strip().lower()
        return re.sub(r"^[^\d]*(?=\d)", "", text)

    a, b = version_key(plain(have)), version_key(plain(offered))
    return "current" if a == b else "update" if b > a else "newer"


CAPABILITY_PATH = re.compile(r"/[A-Za-z0-9_./~%+-]{1,150}")


def clean_capabilities(raw, service: dict | None) -> dict:
    """What a plugin offers the APP besides the data it sends (docs/plugins.md, "Capabilities"): so far ``navigate`` - the plugin can take a
    destination and pass it on to its car. The ``path`` is a route of the plugin's own service that is NOT public; anything else is dropped."""
    out: dict = {}
    nav = raw.get("navigate") if isinstance(raw, dict) else None
    path = nav.get("path") if isinstance(nav, dict) else None
    prefixes = [r["prefix"] for r in (service or {}).get("routes", []) if not r.get("public")]
    if isinstance(path, str) and CAPABILITY_PATH.fullmatch(path) and ".." not in path and any(path.startswith(p) for p in prefixes):
        out["navigate"] = {"path": path, "label": _text(nav, "label", 40)}
    return out


# ---- files a package brings for download ("assets"): checked binaries the app hands out itself, never runs (docs/plugins.md)
FILE_EXTENSIONS = (".jar", ".zip", ".bin", ".json", ".txt", ".md", ".pdf")  # a fixed list - nothing that could be run
FILE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")
FILE_VERSION = re.compile(
    r"[0-9A-Za-z](?:[0-9A-Za-z._+ -]{0,18}[0-9A-Za-z])?"
)  # the version of a file the plugin offers (shown, compared with what is on the car); "Build 7" is fine


def _file_version(item: dict) -> dict:
    """``version`` (what the plugin offers) and ``installed`` (the key of a setting in which the plugin reports what lies on the car) of a file or a
    bundle; whatever is unusable is left out - they are only shown, never needed. ``installed`` is checked against the settings later."""
    out = {}
    if isinstance(item.get("version"), str) and FILE_VERSION.fullmatch(item["version"]):
        out["version"] = item["version"]
    if isinstance(item.get("installed"), str) and KEY.match(item["installed"]):
        out["installed"] = item["installed"]
    return out


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
        hidden = item.get("hidden")
        if hidden is not None and not isinstance(hidden, bool):  # a yes / no; anything else refuses the package
            raise AddonError("addon.err_files")
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
                **({"hidden": True} if hidden else {}),  # not offered as a download; only a service that reads the files sees it
                **_file_version(item),
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
        out.append(
            {
                "name": name,
                "label": _text(item, "label", 80) or name,
                "note": _text(item, "note", 300),
                "entries": entries,
                **_file_version(item),
                **extra,
            }
        )
    return out


def _installed_keys(items: list[dict], writable: set[str]) -> list[dict]:
    """``installed`` must name a setting the plugin can write itself (a ``value`` field or ``service_writable``); otherwise nothing could ever fill it."""
    return [{k: v for k, v in it.items() if k != "installed" or v in writable} for it in items]


def needs_package(manifest: dict) -> bool:
    """A package with a service, files or bundles comes as a ``package.zip`` of a source (its sha256 is checked); a plain description does not."""
    return bool(manifest.get("service") or manifest.get("files") or manifest.get("bundles"))


def approval_fingerprint(manifest: dict) -> str:
    """What an administrator approves: the description of the service and the list of files and bundles (names, checksums, sizes). A new
    version that changes any of it needs a new approval."""
    import hashlib

    thing = {
        "service": manifest.get("service"),
        "files": [
            (f["name"], f["sha256"], f["size"], *((True,) if f.get("hidden") else ())) for f in manifest.get("files", [])
        ],  # a hidden file is part of what is approved (only then: approvals given before stay valid)
        "bundles": [
            {k: v for k, v in b.items() if k not in ("version", "installed")} for b in manifest.get("bundles", [])
        ],  # the version a bundle is shown with is no part of what is approved
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


MAX_BUTTONS = 3  # what fits in the ONE line of the tile on the smallest phone (docs/plugins.md, Buttons)
MAX_SETTINGS_BUTTONS = 6  # buttons that live in the tab *General* of the settings page instead (``place: "settings"``)
BUTTON_ID = re.compile(r"[a-z][a-z0-9_-]{0,30}")


def clean_buttons(
    raw, pages: list[dict], service: dict | None, setting_types: dict[str, str] | None = None, flow_ids: list[str] | None = None
) -> list[dict]:
    """Free buttons of a plugin (docs/plugins.md, "Buttons"): ``{"id", "label", "icon", "page": "<id of a page of the package>"}`` opens a page of the
    plugin, ``{"id", "label", "icon", "action": "/route"}`` makes the app call a route of the plugin's own service (NOT public) and show the answer.
    ``place`` is ``tile`` (default, at most 3: the ONE line of the tile) or ``settings`` (at most 6, in the tab *General*: logout, change the login,
    delete data ...); ``when`` says when the button shows (``clean_when``). Anything that does not fit is dropped."""
    from . import icons

    out: list[dict] = []
    page_ids = {p["id"] for p in pages if isinstance(p, dict) and p.get("id")}
    prefixes = [r["prefix"] for r in (service or {}).get("routes", []) if not r.get("public")]
    for item in raw[: MAX_BUTTONS + MAX_SETTINGS_BUTTONS] if isinstance(raw, list) else []:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("id"), str)
            or not BUTTON_ID.fullmatch(item["id"])
            or any(b["id"] == item["id"] for b in out)
        ):
            continue
        label = _text(item, "label", 40)
        if not label:
            continue
        place = "settings" if item.get("place") == "settings" else "tile"
        if sum(1 for b in out if b.get("place", "tile") == place) >= (MAX_SETTINGS_BUTTONS if place == "settings" else MAX_BUTTONS):
            continue
        when = clean_when(item.get("when"), setting_types or {})
        if when is None:  # a condition that cannot be read: the button stays away rather than show when it should not
            continue
        btn = {"id": item["id"], "label": label, "icon": item.get("icon") if item.get("icon") in icons.ICONS else "play-circle-outline"}
        if item.get("page") in page_ids:
            btn["page"] = item["page"]
        elif item.get("step") in (flow_ids or []):  # opens a step of the set-up flow again (change the login, ...)
            btn["step"] = item["step"]
        else:
            path = item.get("action")
            if not (
                isinstance(path, str) and CAPABILITY_PATH.fullmatch(path) and ".." not in path and any(path.startswith(p) for p in prefixes)
            ):
                continue
            btn["action"] = path
            if _text(item, "confirm", 160):
                btn["confirm"] = _text(item, "confirm", 160)
        if place == "settings":
            btn["place"] = "settings"
        if when:
            btn["when"] = when
        if _l10n(item.get("l10n"), {"label": 40, "confirm": 160}):
            btn["l10n"] = _l10n(item.get("l10n"), {"label": 40, "confirm": 160})
        out.append(btn)
    return out


def _docs_text(value) -> str:
    """A longer text with its paragraphs: every line is tidied (blanks collapsed), at most one empty line in a row, at most 3000 characters."""
    if not isinstance(value, str):
        return ""
    lines, blank = [], False
    for raw in value.replace("\r\n", "\n").split("\n"):
        line = " ".join(raw.split())
        if not line:
            if lines and not blank:
                lines.append("")
            blank = True
            continue
        lines.append(line)
        blank = False
    return "\n".join(lines).strip()[:3000]


def _package_l10n(raw) -> dict[str, dict[str, str]]:
    """The translations of the package itself: name, description and - with its line breaks - docs."""
    out = _l10n(raw, {"name": 80, "description": 300})
    for lang, texts in list((raw if isinstance(raw, dict) else {}).items())[:12]:
        if isinstance(lang, str) and LANG.match(lang) and isinstance(texts, dict) and _docs_text(texts.get("docs")):
            out.setdefault(lang, {})["docs"] = _docs_text(texts.get("docs"))
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
        if _l10n(item.get("l10n"), {"label": 40, "unit": 16}):
            tile["l10n"] = _l10n(item.get("l10n"), {"label": 40, "unit": 16})
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


FLOW_TYPES = ("text", "requirements", "form", "check", "token", "files", "page", "download", "oauth")
MAX_FLOW = 12
INPUT_TYPES = ("text", "password", "number", "email", "url")  # what a ``check`` step may ask for once (``inputs``)
MAX_INPUTS = 6


OAUTH_SCOPE = re.compile(r"[\x21\x23-\x5b\x5d-\x7e]{1,100}")  # what RFC 6749 allows in one scope word
OAUTH_RESERVED = {"response_type", "client_id", "redirect_uri", "state", "scope", "code_challenge", "code_challenge_method"}
OAUTH_REDIRECTS = ("paste", "app")
OAUTH_LOCAL = re.compile(r"https?://(localhost|127\.0\.0\.1)(:\d{1,5})?(/[^\s\"'<>\\]*)?")


def _oauth_url(value) -> str | None:
    """An address of a provider: https, a host NAME (not an IP number, not ``localhost``), no log-in inside it, at most 300 characters."""
    if not isinstance(value, str) or len(value) > 300 or not value.startswith("https://") or any(c in value for c in " \"'<>\\\n\r\t"):
        return None
    parts = urlsplit(value)
    host = parts.hostname or ""
    if parts.username or parts.password or parts.fragment or not re.fullmatch(r"[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+", host):
        return None
    return None if re.fullmatch(r"[0-9.]+", host) else value


def clean_oauth(raw, types: dict[str, str]) -> tuple[dict | None, str]:
    """The ``oauth`` of a step of type ``oauth`` (docs/plugins.md, "Logging in with an account"): ``(cleaned, "")`` or ``(None, why)`` - the reason is for the
    checker of the package. ``types`` = the settings of the package and their types: the client id / secret may come from a setting the person fills in."""
    if not isinstance(raw, dict):
        return None, "'oauth' must be an object"
    out: dict = {}
    for key in ("authorize_url", "token_url"):
        if not (url := _oauth_url(raw.get(key))):
            return None, f"'{key}' must be an https address with a host name (no IP number, no log-in inside, at most 300 characters)"
        out[key] = url
    client, setting = raw.get("client_id"), raw.get("client_id_setting")
    if isinstance(client, str) and re.fullmatch(r"[\x21-\x7e]{1,200}", client):
        out["client_id"] = client
    elif isinstance(setting, str) and types.get(setting) in ("text", "password"):
        out["client_id_setting"] = setting
    else:
        return None, "give 'client_id' or the key of a text setting in 'client_id_setting'"
    if (secret := raw.get("client_secret_setting")) is not None:
        if not (isinstance(secret, str) and types.get(secret) == "password"):
            return None, "'client_secret_setting' must be the key of a password setting"
        out["client_secret_setting"] = secret
    scopes = raw.get("scopes")
    out["scopes"] = [w for w in scopes[:20] if isinstance(w, str) and OAUTH_SCOPE.fullmatch(w)] if isinstance(scopes, list) else []
    out["pkce"] = raw.get("pkce") is not False  # on unless the package says no
    out["client_auth"] = "basic" if raw.get("client_auth") == "basic" else "post"
    out["redirect"] = raw.get("redirect") if raw.get("redirect") in OAUTH_REDIRECTS else "paste"
    if out["redirect"] == "paste":
        uri = raw.get("redirect_uri")
        if not (isinstance(uri, str) and (_oauth_url(uri) or OAUTH_LOCAL.fullmatch(uri))) or len(uri) > 300:
            return None, "'redirect_uri' (the address the provider sends the person to) must be an https address or one on localhost"
        out["redirect_uri"] = uri
    extra = raw.get("extra") if isinstance(raw.get("extra"), dict) else {}
    out["extra"] = {
        k: v
        for k, v in list(extra.items())[:5]
        if isinstance(k, str) and re.fullmatch(r"[a-z_]{1,30}", k) and k not in OAUTH_RESERVED and isinstance(v, str) and 0 < len(v) <= 200
    }
    return out, ""


def clean_inputs(raw, taken: set[str] | frozenset[str] = frozenset()) -> list[dict]:
    """The one-time inputs of a ``check`` step (``inputs``, docs/plugins.md): fields the person fills in for THIS check only - a code from an SMS, an
    e-mail or an app. They travel to the service with the check and are never stored: not as a setting, not in ``settings.json``, not in a backup.
    ``ask: true`` keeps a field off the page until the service asks for it (``{"ok": false, "ask": ["code"], "message": "..."}``). Types: text,
    password, number, email, url; the key of an input is never the key of a setting; at most 6."""
    items = [r for r in (raw if isinstance(raw, list) else [])[:MAX_INPUTS] if isinstance(r, dict)]
    asked: dict = {}
    for r in items:
        asked.setdefault(r.get("key"), r.get("ask") is True)  # the first of two with the same key is the one that stays
    out: list[dict] = []
    for field in clean_setting_fields(items):
        if field["type"] not in INPUT_TYPES or field["key"] in taken or any(x["key"] == field["key"] for x in out):
            continue
        for key in ("service_writable", "advanced", "show_if", "default"):
            field.pop(key, None)  # an input is empty every time and always belongs to its step
        if asked.get(field["key"]):
            field["ask"] = True
        out.append(field)
    return out


def input_fields(step: dict, asked: set[str] | frozenset[str] = frozenset()) -> list[dict]:
    """The one-time inputs of a ``check`` step that are on the page now: those that always show and those the service has asked for."""
    return [f for f in step.get("inputs", []) if not f.get("ask") or f["key"] in asked]


def clean_flow(
    raw,
    bundles: list[dict],
    has_file: bool,
    setting_keys: frozenset[str] | set[str],
    frame_ids: frozenset[str] | set[str],
    service: dict | None,
    setting_types: dict[str, str] | None = None,
) -> list[dict]:
    """The free set-up flow (``setup.flow``): up to 12 steps, each of ONE type (docs/plugins.md, "The set-up flow"): ``text``, ``requirements``
    (``requires`` the app can check, ``filled`` settings that must have a value), ``form`` (``settings`` to fill in), ``check`` (the service checks what
    was typed: ``action``, and may ask for one-time ``inputs``), ``token``, ``files`` (``bundles``, the connection file), ``page`` (a frame page of the plugin) and ``download`` (the service
    makes a file: ``action``). A step that does not fit its type is dropped."""
    out: list[dict] = []
    names = {b["name"] for b in bundles}
    prefixes = [r["prefix"] for r in (service or {}).get("routes", []) if not r.get("public")]
    for st in raw[:MAX_FLOW] if isinstance(raw, list) else []:
        if (
            not isinstance(st, dict)
            or not isinstance(st.get("id"), str)
            or not STEP_ID.fullmatch(st["id"])
            or st.get("type") not in FLOW_TYPES
            or any(x["id"] == st["id"] for x in out)
        ):
            continue
        kind = st["type"]
        step = {"id": st["id"], "type": kind, "title": _text(st, "title", 80), "text": _long(st.get("text"), 3000)}
        if kind in ("form", "check", "download") and isinstance(st.get("settings"), list):
            step["settings"] = [k for k in dict.fromkeys(st["settings"]) if isinstance(k, str) and k in setting_keys][:60]
        if kind in ("check", "download"):
            path = st.get("action")
            if not (
                isinstance(path, str) and CAPABILITY_PATH.fullmatch(path) and ".." not in path and any(path.startswith(p) for p in prefixes)
            ):
                continue  # the service's own route, never a public one
            step["action"] = path
            if _text(st, "label", 40):
                step["label"] = _text(st, "label", 40)
            if kind == "check" and (inputs := clean_inputs(st.get("inputs"), setting_keys)):
                step["inputs"] = inputs
        if kind == "form" and not step.get("settings"):
            continue
        if kind == "oauth":  # logging in with an account: the app does the dance and keeps the tokens (oauth.py)
            spec, _why = clean_oauth(st.get("oauth"), setting_types or {k: "text" for k in setting_keys})
            if spec is None:
                continue
            step["oauth"] = spec
            if _text(st, "label", 40):
                step["label"] = _text(st, "label", 40)
        if kind == "requirements":
            wanted = st.get("requires") if isinstance(st.get("requires"), list) else []
            step["requires"] = [r for r in SETUP_REQUIRES if r in wanted]
            step["filled"] = [
                k
                for k in dict.fromkeys(st.get("filled") if isinstance(st.get("filled"), list) else [])
                if isinstance(k, str) and k in setting_keys
            ][:30]
            if not step["requires"] and not step["filled"]:
                continue
        if kind == "page":
            if not (isinstance(st.get("page"), str) and st["page"] in frame_ids):
                continue
            step["page"] = st["page"]
        if kind == "files":
            step["bundles"] = [
                n for n in (st.get("bundles") if isinstance(st.get("bundles"), list) else []) if isinstance(n, str) and n in names
            ][:8]
            step["connection_file"] = st.get("connection_file") is True and has_file
        own = _l10n(st.get("l10n"), {"title": 80, "text": 3000, "label": 40})
        if own:
            step["l10n"] = own
        out.append(step)
    return out


def clean_setup(
    raw,
    bundles: list[dict],
    has_file: bool,
    setting_keys: frozenset[str] | set[str] = frozenset(),
    frame_ids: frozenset[str] | set[str] = frozenset(),
    service: dict | None = None,
    setting_types: dict[str, str] | None = None,
) -> dict | None:
    """The ``setup`` of a manifest: a guide in steps (docs/plugins.md). ``requires`` lists what must be there first (an https address under System,
    a VIN in the vehicle data); a step may offer the token, the connection file and ``bundles`` of the package, and brings its own text.
    ``done_when`` (a ``when``, see ``clean_when``) says what else must hold for the set-up to count as done - for example a token and a login that
    worked; ``settings_after`` hides the *Settings* button of the tile until the set-up is done (only with a ``flow``)."""
    if not isinstance(raw, dict):
        return None
    flow = clean_flow(raw.get("flow"), bundles, has_file, setting_keys, frame_ids, service, setting_types)
    if not flow and not isinstance(raw.get("steps"), list):
        return None
    wanted = raw.get("requires") if isinstance(raw.get("requires"), list) else []
    names = {b["name"] for b in bundles}
    steps: list[dict] = []
    for st in (raw["steps"] if isinstance(raw.get("steps"), list) else [])[:8]:
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
    if not steps and not flow:
        return None
    guide = {"requires": [r for r in SETUP_REQUIRES if r in wanted], "steps": steps}
    if flow:  # the free flow takes the place of the three fixed steps
        guide["flow"] = flow
    if _text(raw, "title", 60):  # the name of the guide (its button and heading); without it the app's own name is used
        guide["title"] = _text(raw, "title", 60)
    if _l10n(raw.get("l10n"), {"title": 60}):
        guide["l10n"] = _l10n(raw.get("l10n"), {"title": 60})
    done = clean_when(raw.get("done_when"), setting_types or {k: "text" for k in setting_keys}, allow_setup=False)
    if done:  # a condition that cannot be read is ignored here: the set-up then counts as done at the end of the guide, as before
        guide["done_when"] = done
    if flow and raw.get("settings_after") is True:
        guide["settings_after"] = True
    if (
        raw.get("token") is False
    ):  # no token part in the guide (a plugin without a service that never reports); ignored when a service needs one
        guide["token"] = False
    return guide


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


def _options(f: dict, key: str = "options", l10n: bool = False) -> list[dict]:
    """The choices of a setting (``options``), or of the value cell of a ``list`` (``value_options``, with the label per language if ``l10n``)."""
    out = []
    for o in (f.get(key) if isinstance(f.get(key), list) else [])[:MAX_OPTIONS]:
        if not (isinstance(o, dict) and _text(o, "value", 40) and "," not in _text(o, "value", 40)):
            continue
        item = {"value": _text(o, "value", 40), "label": _text(o, "label", 60) or _text(o, "value", 40)}
        if l10n and _l10n(o.get("l10n"), {"label": 60}):
            item["l10n"] = _l10n(o.get("l10n"), {"label": 60})
        out.append(item)
    return out


def clean_setting_fields(raw) -> list[dict]:
    """The ``settings`` of a manifest: what the plugin asks for, as the settings page draws it. Unknown types become text; a choice without
    options becomes text; ``section``, ``info`` and ``tab`` are headings, texts and page tabs without a value."""
    from . import icons

    fields: list[dict] = []
    tabs = 0
    for i, f in enumerate((raw if isinstance(raw, list) else [])[: MAX_FIELDS + MAX_TABS]):
        if not isinstance(f, dict):
            continue
        kind = f.get("type") if f.get("type") in FIELD_TYPES else "text"
        if kind == "tab":
            tab_id = f.get("id") if isinstance(f.get("id"), str) and KEY.match(f["id"]) else f"tab{i}"
            if tabs >= MAX_TABS or any(x.get("id") == tab_id for x in fields):
                continue
            tabs += 1
            tab = {"key": f"_n{i}", "type": "tab", "id": tab_id, "label": _text(f, "label", 40) or tab_id, "help": ""}
            if f.get("icon") in icons.ICONS:
                tab["icon"] = f["icon"]
            if _l10n(f.get("l10n"), {"label": 40}):
                tab["l10n"] = _l10n(f.get("l10n"), {"label": 40})
            fields.append(tab)
            continue
        if sum(x["type"] != "tab" for x in fields) >= MAX_FIELDS:
            continue
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
        if kind == "value":  # a value shown for information: how its text is written and which texts get a coloured dot
            if f.get("format") in VALUE_FORMATS:
                field["format"] = f["format"]
            if states := _value_states(f.get("state")):
                field["state"] = states
        if f.get("advanced") is True and kind not in NO_VALUE:
            field["advanced"] = True  # the set-up guide shows it folded under "Advanced settings"
        if kind == "bool" and isinstance(f.get("default"), bool):
            field["default"] = "1" if f["default"] else "0"  # a switch may start as true / false (stored like every switch: 1 / 0)
        elif _text(f, "default", 200) and kind not in NO_VALUE:
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
            columns = _list_columns(f.get("columns"))  # more cells in a row (a second line, a logo address): the row stays one line of text
            if columns:
                field["columns"] = columns
            if value_options := _options(f, "value_options", l10n=True):  # the value cell is a choice (the stored row stays "name | value")
                field["value_options"] = value_options
            vmax = f.get("value_max")  # how long the value of a row may be (a stream address is long)
            if isinstance(vmax, int) and not isinstance(vmax, bool) and 1 <= vmax <= LIST_CELL_MAX:
                field["value_max"] = vmax
            if isinstance(f.get("min_rows"), int) and not isinstance(f.get("min_rows"), bool) and 1 <= f["min_rows"] <= LIST_ROWS:
                field["min_rows"] = f["min_rows"]  # saving with fewer rows is refused
            tpls = _list_templates(f.get("templates"), columns, field.get("value_max", 200))
            if tpls:
                field["templates"] = tpls  # a select of ready-made rows and a button that appends the chosen one
            if isinstance(f.get("default"), list):  # the rows a new installation starts with: [{"name", "value"}], at most 30
                rows = _list_default(f["default"], columns, field.get("value_max", 200))
                if rows:
                    field["default"] = rows
                else:
                    field.pop("default", None)
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
        cond = clean_show_if(f.get("show_if"))  # only shown while other settings have these values (see clean_show_if)
        if cond:
            field["show_if"] = cond
        fields.append(field)
    return fields


SHOW_OPS = ("equals", "not", "in", "not_in", "has")  # what one condition can say about a setting
SHOW_MAX_PARTS, SHOW_MAX_DEPTH, SHOW_MAX_VALUES = 8, 3, 12


def _show_text(value) -> str | None:
    """A value a condition compares with, as the text the form has: a switch is ``"1"`` or ``"0"``."""
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)[:40] if isinstance(value, str | int) else None


def clean_show_if(cond, depth: int = 0, parts: list | None = None):
    """The condition of a setting (``show_if``), cleaned - or None: a condition that cannot be used is dropped, the setting is then simply always shown.

    One test of one setting: ``{"key": "mode", "equals": "custom"}`` (a switch: ``"equals": true``), or ``"not"``, ``"in": [...]`` (one of these values),
    ``"not_in": [...]``, ``"has": "x"`` (a ``multiselect`` with this box ticked). Tests are put together with ``{"any": [...]}`` (one of them) and
    ``{"all": [...]}`` (every one); a plain list means ``all``. Up to 8 tests, 3 levels deep. Only ``equals`` is the old form and stays as it was."""
    parts = [0] if parts is None else parts
    if isinstance(cond, list):
        cond = {"all": cond}
    if not isinstance(cond, dict) or depth > SHOW_MAX_DEPTH:
        return None
    for word in ("all", "any"):
        if word in cond:
            items = cond[word]
            if not isinstance(items, list) or not 1 <= len(items) <= SHOW_MAX_PARTS:
                return None
            cleaned = [clean_show_if(c, depth + 1, parts) for c in items]
            return {word: cleaned} if all(cleaned) else None
    key = cond.get("key")
    op = next((o for o in SHOW_OPS if o in cond), None)
    if not isinstance(key, str) or not KEY.match(key) or op is None:
        return None
    parts[0] += 1
    if parts[0] > SHOW_MAX_PARTS:
        return None
    if op in ("in", "not_in"):
        raw = cond[op]
        values = [_show_text(v) for v in raw] if isinstance(raw, list) and 1 <= len(raw) <= SHOW_MAX_VALUES else []
        return {"key": key, op: values} if values and None not in values else None
    value = _show_text(cond[op])
    return {"key": key, op: value} if value is not None else None


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
    types = {f["key"]: f["type"] for f in fields if "key" in f}
    writable = {k for k, t in types.items() if t == "value"} | {f["key"] for f in fields if f.get("service_writable")}
    files, bundles = _installed_keys(files, writable), _installed_keys(bundles, writable)
    downloads = clean_downloads(data.get("downloads"), service, types)
    capabilities = clean_capabilities(data.get("capabilities"), service)
    setup = clean_setup(
        data.get("setup"),
        bundles,
        bool(conn_file),
        {f["key"] for f in fields},
        {p["id"] for p in pages if p.get("kind") == "frame"},
        service,
        types,
    )
    buttons = clean_buttons(data.get("buttons"), pages, service, types, [st["id"] for st in (setup or {}).get("flow", [])])
    if service and service.get("token") is False:
        _check_tokenless(service, conn_file, bundles, tiles, fields, setup)
    docs = _docs_text(data.get("docs"))  # a longer description for the Interfaces page (paragraphs and line breaks stay)
    icon = data.get("icon") if data.get("icon") in icons.ICONS else ""  # one of the app's icons (docs/icons.md); shown on the plugin's tile
    return {
        **({"icon": icon} if icon else ({"icon": "puzzle"} if pages else {})),
        **({"service": service} if service else {}),
        **({"interfaces": interfaces} if interfaces or data.get("interfaces") == [] else {}),
        **({"tiles": tiles} if tiles else {}),
        **({"downloads": downloads} if downloads else {}),
        **({"capabilities": capabilities} if capabilities else {}),
        **({"buttons": buttons} if buttons else {}),
        **({"files": files} if files else {}),
        **({"bundles": bundles} if bundles else {}),
        **({"setup": setup} if setup else {}),
        **({"docs": docs} if docs else {}),
        **({"reminders": reminders} if reminders else {}),
        **({"pages": pages, "nav": data.get("nav") is not False} if pages else {}),
        **({"l10n": _package_l10n(data.get("l10n"))} if data.get("l10n") else {}),
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


def restore_all(conn: sqlite3.Connection, vehicle_id: int, entries: list, token_ids: dict, passwords: dict | None = None) -> dict[int, int]:
    """Integrations and plugins from a vehicle backup: settings and token come back, the package itself is not part of a backup.
    Everything starts OFF. When the same package is already installed on this system it is used at once (still off, to be switched on on purpose);
    otherwise the entry waits as 'missing' until the package is installed from a source (restoresetup.py does that when the person asked for it).
    ``passwords`` ({package id: {setting: password}}) is what the secrets block of the backup held; they are stored sealed (vault.py).
    Returns {the number an entry had in the backup: its number here}."""
    numbers: dict[int, int] = {}
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
            "SELECT manifest, source_id, pkg_sha FROM vehicle_addons WHERE addon_id = ? AND kind = ? AND status != 'missing' AND vehicle_id != ? ORDER BY id LIMIT 1",
            (entry["addon_id"], kind, vehicle_id),
        ).fetchone()
        status = "missing"
        source_id = pkg_sha = None
        if have:
            manifest, source_id, pkg_sha = json.loads(have["manifest"]), have["source_id"], have["pkg_sha"]
            status = "configured" if values else "uploaded"
        returned = (passwords or {}).get(entry["addon_id"])
        if isinstance(returned, dict):  # the passwords of the backup, for the fields the package declares as passwords
            secret_keys = {f["key"] for f in manifest.get("settings", []) if f.get("type") == "password"}
            values.update({k: str(v)[:1000] for k, v in returned.items() if k in secret_keys and isinstance(v, str) and v})
            if status != "missing":
                status = "configured" if values else status
        source = entry.get("source") if isinstance(entry.get("source"), dict) else {}
        url = source.get("url") if isinstance(source.get("url"), str) else entry.get("source_url")
        url = url if isinstance(url, str) else None
        conn.execute(
            "INSERT OR IGNORE INTO vehicle_addons(vehicle_id, kind, addon_id, manifest, status, settings, token_id, created_at, source_id, active, source_url, pkg_sha) "
            "VALUES(?,?,?,?,?,?,?,?,?,0,?,?)",
            (
                vehicle_id,
                kind,
                entry["addon_id"],
                json.dumps(manifest),
                status,
                json.dumps(_sealed(manifest, values)),
                token_ids.get(entry.get("token_id")),
                datetime.now(UTC).isoformat(timespec="seconds"),
                source_id,
                url,
                pkg_sha,
            ),
        )
        row = conn.execute(
            "SELECT id FROM vehicle_addons WHERE vehicle_id = ? AND addon_id = ?", (vehicle_id, entry["addon_id"])
        ).fetchone()
        if row and isinstance(entry.get("id"), int):
            numbers[entry["id"]] = row["id"]
    return numbers


def _newer_versions(conn: sqlite3.Connection, rows: list[sqlite3.Row]) -> dict[int, str]:
    """For installed packages that came from a source: the version that source offers now (by addon row id)."""
    out: dict[int, str] = {}
    for r in rows:
        if r["source_id"] is None:  # installed without a source (a file, an older built-in offer): a source that offers it can update it
            offer = unlinked_offer(conn, r) if r["status"] != "missing" else None
            if offer:
                out[r["id"]] = offer["version"]
            continue
        found = conn.execute(
            "SELECT version FROM source_packages WHERE source_id = ? AND kind = ? AND pkg_id = ?",
            (r["source_id"], r["kind"], r["addon_id"]),
        ).fetchone()
        if found:
            out[r["id"]] = found["version"]
    return out


def unlinked_offer(conn: sqlite3.Connection, r) -> sqlite3.Row | None:
    """For a package installed WITHOUT a source (a file, an older built-in offer): the newest version that any source of its list offers
    (``source_id``, ``version``, ``name`` of the source), or None. An update takes the package from there - and links it to that source."""
    from .sources import version_key

    flag = "for_plugin" if r["kind"] == "plugin" else "for_integration"
    found = conn.execute(
        f"SELECT p.source_id, p.version, s.name FROM source_packages p JOIN sources s ON s.id = p.source_id "
        f"WHERE p.kind = ? AND p.pkg_id = ? AND s.{flag} = 1 AND p.version != ''",
        (r["kind"], r["addon_id"]),
    ).fetchall()
    return max(found, key=lambda o: version_key(o["version"]), default=None)


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


def _ui_state(row, manifest: dict, vals: dict, delivered: frozenset[str] = frozenset()) -> dict:
    """What the page needs to judge a ``when``: is the set-up done (finished, and every ``done_when`` holds), is there a token, the stored values.
    ``setup_open`` is true while a plugin WITH a ``setup`` still has to be set up (its main button says so)."""
    setup = manifest.get("setup") or {}
    types = {f["key"]: f["type"] for f in manifest.get("settings", []) if "key" in f}
    has_token = row["token_id"] is not None
    done = row["status"] == "configured" and when_holds(
        setup.get("done_when", []), setup_done=True, has_token=has_token, values=vals, types=types, delivered=delivered
    )
    return {
        "setup_done": done,
        "has_token": has_token,
        "values": vals,
        "types": types,
        "delivered": delivered,
        "setup_open": bool(setup) and not done,
        "settings_after": bool(setup.get("settings_after")),
    }


def list_for(conn: sqlite3.Connection, vehicle_id: int) -> list[dict]:
    from .sources import is_newer

    rows = conn.execute("SELECT * FROM vehicle_addons WHERE vehicle_id = ? ORDER BY id", (vehicle_id,)).fetchall()
    latest = _newer_versions(conn, rows)
    names = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM sources")}
    out = []
    from . import config

    lang = config.language()
    handed: dict[int, frozenset[str]] = {}  # which files of a package the app handed out for this car, per plugin
    for d in conn.execute(
        "SELECT addon_pk, name FROM addon_deliveries WHERE addon_pk IN (SELECT id FROM vehicle_addons WHERE vehicle_id = ?)", (vehicle_id,)
    ):
        handed[d["addon_pk"]] = handed.get(d["addon_pk"], frozenset()) | {d["name"]}
    login_needed = {  # the installs whose login with an account has expired: the tile says "log in again"
        x["addon_pk"]
        for x in conn.execute(
            "SELECT l.addon_pk FROM connection_links l JOIN connections c ON c.id = l.connection_id WHERE c.state = 'login_required' "
            "AND l.addon_pk IN (SELECT id FROM vehicle_addons WHERE vehicle_id = ?)",
            (vehicle_id,),
        )
    }
    for r in rows:
        manifest = json.loads(r["manifest"])
        texts = (manifest.get("l10n") or {}).get(lang) or {}
        manifest = {
            **manifest,
            **{k: texts[k] for k in ("name", "description", "docs") if k in texts},
        }  # the package's own translation, when it has one
        manifest["settings"] = [
            {**f, **{k: v for k, v in ((f.get("l10n") or {}).get(lang) or {}).items() if k in ("label", "help")}}
            for f in manifest.get("settings", [])
        ]
        if manifest.get("buttons"):  # the labels of the free buttons in the language of the page
            manifest["buttons"] = [
                {**b, **{k: v for k, v in ((b.get("l10n") or {}).get(lang) or {}).items() if k in ("label", "confirm")}}
                for b in manifest["buttons"]
            ]
        for f in manifest["settings"]:
            if f.get("templates"):  # the ready-made rows of a list in the language of the page
                f["templates"] = [{**t, "label": ((t.get("l10n") or {}).get(lang) or {}).get("label", t["label"])} for t in f["templates"]]
            if f.get("value_options"):  # the choices of the value cell
                f["value_options"] = [
                    {**o, "label": ((o.get("l10n") or {}).get(lang) or {}).get("label", o["label"])} for o in f["value_options"]
                ]
            if f.get("columns"):  # the names of the extra cells, too
                f["columns"] = [{**c, "label": ((c.get("l10n") or {}).get(lang) or {}).get("label", c["label"])} for c in f["columns"]]
        if manifest.get("setup") and manifest["setup"].get("title"):
            manifest["setup"] = {
                **manifest["setup"],
                "title": ((manifest["setup"].get("l10n") or {}).get(lang) or {}).get("title") or manifest["setup"]["title"],
            }
        offered = latest.get(r["id"], "")
        offer = (
            unlinked_offer(conn, r) if offered and r["source_id"] is None else None
        )  # where an update of a package without a source comes from
        need = _need(conn, r) if r["status"] == "missing" else None
        defaults = {f["key"]: f["default"] for f in manifest.get("settings", []) if "default" in f}
        secret = {f["key"] for f in manifest.get("settings", []) if f.get("type") == "password"}
        stored = {
            k: (vault.decrypt(v) if k in secret else v) for k, v in json.loads(r["settings"] or "{}").items()
        }  # passwords are encrypted at rest
        vals = {**defaults, **stored}
        state = _ui_state(r, manifest, vals, handed.get(r["id"], frozenset()))
        judge = {k: state[k] for k in ("setup_done", "has_token", "values", "types", "delivered")}
        flow_ids = [st["id"] for st in (manifest.get("setup") or {}).get("flow", [])]
        manifest["buttons"] = [
            {
                **b,
                "shown": when_holds(b.get("when", []), **judge),
                **({"step_n": flow_ids.index(b["step"]) + 1} if b.get("step") in flow_ids else {}),
            }
            for b in manifest.get("buttons", [])
        ]  # which of them show right now (their ``when``), and the number of the flow step a button opens
        manifest["downloads"] = [
            {
                **d,
                **{k: v for k, v in ((d.get("l10n") or {}).get(lang) or {}).items() if k in ("label", "note")},
                "shown": when_holds(d.get("when", []), **judge),
            }
            for d in manifest.get("downloads", [])
        ]  # the label and note in the language of the page, when the package brings them
        out.append(
            {
                **dict(r),
                "m": manifest,
                "vals": vals,
                "setup_open": state["setup_open"],
                "settings_shown": not (state["settings_after"] and state["setup_open"]),
                "has_token": state["has_token"],
                "needs_token": needs_token(manifest),
                "latest": offered,
                "has_update": is_newer(offered, manifest.get("version", "")),
                "source_name": names.get(r["source_id"]),
                "offer_source": offer["name"] if offer else None,
                "can_link": bool(offer)
                and r["status"] != "missing"
                and not is_newer(offered, manifest.get("version", ""))
                and not is_newer(
                    manifest.get("version", ""), offered
                ),  # the same version stands in a source: it can be linked without an update
                "login_needed": r["id"] in login_needed,
                "login_step": next(
                    (n for n, st in enumerate((manifest.get("setup") or {}).get("flow", []), 1) if st["type"] == "oauth"), 0
                ),
                "debug": connectors.plugin_debug(conn, vehicle_id, r["addon_id"]),
                "debug_state": connectors.plugin_debug_state(conn, vehicle_id, r["addon_id"]),
                "missing": r["status"] == "missing",
                "need": need,
            }
        )
    return out


def get(conn: sqlite3.Connection, vehicle_id: int, addon_pk: int) -> dict | None:
    return next((a for a in list_for(conn, vehicle_id) if a["id"] == addon_pk), None)


LIST_ROWS = 30


def _row_text(value, limit: int) -> str:
    return " ".join(str(value or "").replace("|", " ").split())[:limit]


LIST_COLUMNS = 3  # extra cells next to the name and the value
LIST_CELL_MAX = 500  # the longest a cell (or the value) of a row may be set to; a text longer than its limit is refused, never cut quietly
LIST_COLUMN_KEY = re.compile(r"[a-z][a-z0-9_]{0,19}")
LIST_COLUMN_RESERVED = {"name", "value", "label", "l10n"}


LIST_COLUMN_TYPES = ("text", "number", "date", "select")
VALUE_FORMATS = (
    "datetime",
    "date",
)  # a ``value`` holding a time (ISO text, UTC when it has no zone) is shown in the system's zone and writing
VALUE_LEVELS = ("ok", "warn", "bad")  # the coloured dot in front of a ``value``: green, amber, red


def _value_states(raw) -> dict:
    """``{"ok": ["connected"], "warn": ["waiting"], "bad": ["error"]}``: which texts of a ``value`` get which dot (up to 8 texts for each level)."""
    out: dict[str, list[str]] = {}
    if isinstance(raw, dict):
        for level in VALUE_LEVELS:
            texts = [_show_text(v) for v in raw.get(level, [])[:8]] if isinstance(raw.get(level), list) else []
            texts = [t for t in texts if t]
            if texts:
                out[level] = texts
    return out


def _list_columns(raw) -> list[dict]:
    """The extra cells of a ``list`` row: ``[{"key", "label", "max", "type", "options", "l10n": {"de": {"label"}}}]``, at most 3; a column that is not
    usable (no key, a key twice or taken, no list) is left out. ``type`` is ``text`` (the default), ``number``, ``date`` (``YYYY-MM-DD``) or
    ``select`` (with ``options``, like a choice setting)."""
    out: list[dict] = []
    for c in raw[:10] if isinstance(raw, list) else []:
        if len(out) == LIST_COLUMNS:
            break
        key = c.get("key") if isinstance(c, dict) else None
        if (
            not isinstance(key, str)
            or not LIST_COLUMN_KEY.fullmatch(key)
            or key in LIST_COLUMN_RESERVED
            or any(o["key"] == key for o in out)
        ):
            continue
        limit = c.get("max")
        col = {
            "key": key,
            "label": _text(c, "label", 40) or key,
            "max": limit if isinstance(limit, int) and not isinstance(limit, bool) and 1 <= limit <= LIST_CELL_MAX else 120,
        }
        kind = c.get("type") if c.get("type") in LIST_COLUMN_TYPES else "text"  # a cell that is a number, a date or one of a few choices
        if kind == "select":
            options = _options(c)
            if options:
                col["options"] = options
            else:
                kind = "text"  # a choice without options is a text
        if kind != "text":
            col["type"] = kind
        if _l10n(c.get("l10n"), {"label": 40}):
            col["l10n"] = _l10n(c.get("l10n"), {"label": 40})
        out.append(col)
    return out


def _cells(row: dict, columns: list[dict] | tuple = (), value_max: int = 200) -> list[str]:
    """The cells of a row given as a dict in the order of the line: name, value, then the extra columns (each cut to its length)."""
    return [
        _row_text(row.get("name"), 80),
        _row_text(row.get("value"), value_max),
        *[_row_text(row.get(c["key"]), c["max"]) for c in columns],
    ]


def _list_default(rows: list, columns: list[dict] | tuple = (), value_max: int = 200) -> str:
    """``[{"name", "value", <column>...}, ...]`` as the stored lines ``name | value | ...`` (at most 30; an empty row is dropped)."""
    lines = []
    for r in rows[:LIST_ROWS]:
        cells = _cells(r, columns, value_max) if isinstance(r, dict) else []
        if any(cells):
            lines.append(" | ".join(cells))
    return "\n".join(lines)


def _list_templates(raw, columns: list[dict] | tuple = (), value_max: int = 200) -> list[dict]:
    """The ready-made rows of a ``list``: ``[{"label", "name", "value", <column>..., "l10n": {"de": {"label"}}}]``, at most 30.
    ``cells`` holds the extra cells in the order of the columns."""
    out = []
    for t in raw[:LIST_ROWS] if isinstance(raw, list) else []:
        if not isinstance(t, dict) or not any(_cells(t, columns, value_max)):
            continue
        item = {
            "label": _text(t, "label", 60) or _row_text(t.get("name"), 80),
            "name": _row_text(t.get("name"), 80),
            "value": _row_text(t.get("value"), value_max),
        }
        if columns:
            item["cells"] = _cells(t, columns, value_max)[2:]
        if _l10n(t.get("l10n"), {"label": 60}):
            item["l10n"] = _l10n(t.get("l10n"), {"label": 60})
        out.append(item)
    return out


def split_line(line: str, columns: list[dict] | tuple = ()) -> list[str]:
    """One stored line ``name | value | <column>...`` as its cells (always 2 + the number of columns; the value takes the rest of a line
    when the list has no columns)."""
    parts = [c.strip() for c in line.split("|", 1 + len(columns))]
    return parts + [""] * (2 + len(columns) - len(parts))


def list_rows(value: str, columns: list[dict] | tuple = ()) -> list[dict]:
    """The rows of a ``list`` setting (stored as lines ``name | value | ...``) as ``[{"name", "value", <column>...}]``."""
    rows = []
    for line in (value or "").splitlines():
        cells = split_line(line, columns)
        if any(cells):
            rows.append({"name": cells[0], "value": cells[1], **{c["key"]: cells[2 + n] for n, c in enumerate(columns)}})
    return rows[:LIST_ROWS]


def typed_rows(rows: list[dict], columns: list[dict] | tuple = ()) -> list[dict]:
    """What a service gets of the rows: the cells of a ``number`` column as numbers (empty: ``null``), everything else as text."""
    numbers = [c["key"] for c in columns if c.get("type") == "number"]
    if not numbers:
        return rows
    out = []
    for row in rows:
        row = dict(row)
        for k in numbers:
            try:
                n = float(str(row.get(k, "")).replace(",", "."))
                row[k] = int(n) if n == int(n) else n
            except (ValueError, OverflowError):
                row[k] = None
        out.append(row)
    return out


def _form_cells(key: str, form: dict, i: int, columns: list[dict] | tuple) -> list[str]:
    """The cells of row ``i`` as typed (tidied, not cut): fields ``<key>__<i>n``, ``__<i>v`` and ``__<i>c<j>``."""
    suffixes = ["n", "v", *[f"c{j}" for j in range(len(columns))]]
    return [" ".join(str(form.get(f"{key}__{i}{sfx}") or "").replace("|", " ").split()) for sfx in suffixes]


def _list_from_form(key: str, form: dict, columns: list[dict] | tuple = (), value_max: int = 200) -> str:
    """The rows of the page as the stored lines ``name | value | ...`` (a row of empty cells is dropped)."""
    limits = [80, value_max, *[c["max"] for c in columns]]
    lines = []
    for i in range(LIST_ROWS):
        cells = [cell[:limit] for cell, limit in zip(_form_cells(key, form, i, columns), limits, strict=True)]
        for j, c in enumerate(columns):
            if c.get("type") == "number" and _cell_fits(cells[2 + j], c):
                cells[2 + j] = cells[2 + j].strip().replace(",", ".")  # 3,5 is stored as 3.5
        if any(cells):
            lines.append(" | ".join(cells))
    return "\n".join(lines)


def list_too_long(key: str, form: dict, columns: list[dict] | tuple = (), value_max: int = 200) -> bool:
    """Is a cell of the list longer than its limit? The page stops typing at the limit; this catches a request that did not come from the page.
    Such a list is refused with a message - an address cut in the middle would lead nowhere."""
    limits = [80, value_max, *[c["max"] for c in columns]]
    return any(len(cell) > limit for i in range(LIST_ROWS) for cell, limit in zip(_form_cells(key, form, i, columns), limits, strict=True))


def _cell_fits(cell: str, column: dict) -> bool:
    """Does a filled cell fit the type of its column (``number``, ``date``, ``select``)? An empty cell always does."""
    cell = cell.strip()
    kind = column.get("type", "text")
    if not cell or kind == "text":
        return True
    if kind == "number":
        try:
            float(cell.replace(",", "."))
        except ValueError:
            return False
        return True
    if kind == "date":
        return bool(DATE.fullmatch(cell))
    return cell in {o["value"] for o in column.get("options", [])}


cell_fits = _cell_fits  # the page asks the same question for a cell it is about to draw


def list_cells_fit(key: str, form: dict, columns: list[dict] | tuple = (), value_options: list[dict] | tuple = (), old: str = "") -> bool:
    """Do all cells of the list fit their columns (and the choices of the value cell)? The page offers the right input for each type; this catches a
    request that did not come from it. A cell that does not fit but is **stored already** (an old value) is let through: it is kept, never refused and
    never dropped quietly - the person chooses a new one when it suits."""
    typed = [(2 + j, c) for j, c in enumerate(columns) if c.get("type")]
    if value_options:
        typed.append((1, {"type": "select", "options": list(value_options)}))
    if not typed:
        return True
    stored = [split_line(line, columns) for line in (old or "").splitlines()]
    kept = {pos: {cells[pos].strip() for cells in stored} for pos, _ in typed}
    return all(
        _cell_fits(cells[pos], c) or cells[pos].strip() in kept[pos]
        for i in range(LIST_ROWS)
        for cells in [_form_cells(key, form, i, columns)]
        for pos, c in typed
    )


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
        if (
            kind == "list"
            and f.get("min_rows")
            and _is_shown(f, manifest, form)
            and len(list_rows(_list_from_form(key, form, f.get("columns", ()), f.get("value_max", 200)))) < f["min_rows"]
        ):
            errors[key] = "err.min_rows"
        if kind == "list" and _is_shown(f, manifest, form) and list_too_long(key, form, f.get("columns", ()), f.get("value_max", 200)):
            errors[key] = "err.cell_long"
        elif (
            kind == "list"
            and _is_shown(f, manifest, form)
            and not list_cells_fit(key, form, f.get("columns", ()), f.get("value_options", ()), old.get(key) or "")
        ):
            errors[key] = "err.cell_type"
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


def show_if_holds(cond: dict, settings: dict, form: dict) -> bool:
    """Does a cleaned condition (``clean_show_if``) hold for this form? ``settings`` = the package's settings by key. A test of a setting that does not
    exist holds (the setting is then shown - a typo must never hide something)."""
    if "all" in cond:
        return all(show_if_holds(c, settings, form) for c in cond["all"])
    if "any" in cond:
        return any(show_if_holds(c, settings, form) for c in cond["any"])
    other = settings.get(cond["key"])
    if other is None:
        return True
    if other["type"] == "bool":
        picked = ["1" if form.get(other["key"]) else "0"]
    elif other["type"] == "multiselect":
        picked = _picked(other["key"], other, form)
    else:
        picked = [str(form.get(other["key"]) or "").strip()]
    current = ",".join(picked)  # the whole value (for a multiselect: the ticked boxes, joined)
    if "equals" in cond:
        return current == cond["equals"]
    if "not" in cond:
        return current != cond["not"]
    if "in" in cond:
        return any(p in cond["in"] for p in picked)
    if "not_in" in cond:
        return not any(p in cond["not_in"] for p in picked)
    return cond["has"] in picked


def _is_shown(f: dict, manifest: dict, form: dict) -> bool:
    cond = f.get("show_if")
    return not cond or show_if_holds(cond, {x["key"]: x for x in manifest["settings"]}, form)


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
            values[key] = _list_from_form(key, form, f.get("columns", ()), f.get("value_max", 200))
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
            out[key] = typed_rows(list_rows(raw, f.get("columns", ())), f.get("columns", ()))
        else:
            out[key] = raw
    return out


def _sealed(manifest: dict, values: dict) -> dict:
    """The settings as they are stored: the passwords encrypted (vault.py)."""
    secret = {f["key"] for f in manifest.get("settings", []) if f.get("type") == "password"}
    return {k: (vault.encrypt(v) if k in secret else v) for k, v in values.items()}


def settings_tabs(fields: list[dict], bad: set[str] | frozenset[str] = frozenset()) -> list[dict]:
    """The settings split into the tabs the package asked for (``{"type": "tab", "id", "label", "icon"}``): every setting belongs to the tab before it;
    what comes before the first tab forms the tab "General" (``implicit``). A package without two or more tabs gets ``[]``: its page stays one list.
    ``bad`` = keys with an error: their tab is marked (``err``) and shown first."""
    groups: list[dict] = []
    lead: list[dict] = []
    for f in fields:
        if f["type"] == "tab":
            groups.append({"id": f["id"], "label": f["label"], "icon": f.get("icon", ""), "fields": [], "implicit": False})
        elif groups:
            groups[-1]["fields"].append(f)
        else:
            lead.append(f)
    if not groups:
        return []
    if lead:
        ids = {g["id"] for g in groups}
        groups.insert(
            0, {"id": "general" if "general" not in ids else "_general", "label": "", "icon": "", "fields": lead, "implicit": True}
        )
    if len(groups) < 2:
        return []
    groups[0]["label"] = (
        ""  # the first tab is always the app's own *General* (login, token, files, uninstall belong there), whatever it was called
    )
    for g in groups:
        g["err"] = any(f["key"] in bad for f in g["fields"])
    return groups


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


def _check_tokenless(
    service: dict, conn_file: dict | None, bundles: list[dict], tiles: list[dict], fields: list[dict], setup: dict | None = None
) -> None:
    """``service.token: false`` (a plugin with a service that has NO token and no Plugin API): refuse what only works with a token - a connection file with
    ``{token}``, a bundle that carries it, a public route that checks it (``token_header``), tiles (the plugin fills them through the API), settings the
    service writes itself (``value`` fields, ``service_writable``) and a guide step that shows the token. A promise the package cannot keep is refused when it is read, never dropped quietly."""
    if (
        (conn_file and "{token}" in conn_file["template"])
        or any(b.get("connection_file_to") for b in bundles)
        or any(r.get("token_header") for r in service.get("routes", []))
        or tiles
        or any(f.get("type") == "value" or f.get("service_writable") for f in fields)
        or any(st.get("type") == "token" for st in (setup or {}).get("flow", []))  # a guide that asks for the token
    ):
        raise AddonError("addon.err_service_token")


def needs_token(manifest: dict) -> bool:
    """Does the plugin use a token at all? A plugin with a service does (the service reports with it) unless it says ``service.token: false``. Without a service it does not when its
    connection file has no ``{token}`` (a file with only settings, nothing secret) or when it says so (``setup.token: false``): then the guide leaves the
    token part out, no token is made and the page shows no token card."""
    if manifest.get("service"):
        return manifest["service"].get("token") is not False  # ``service.token: false``: a service without a token (docs/plugins.md)
    if (manifest.get("setup") or {}).get("token") is False:
        return False
    cfile = manifest.get("connection_file")
    return not cfile or "{token}" in cfile["template"]


def file_has_secret(manifest: dict) -> bool:
    """Does the connection file carry the token (``{token}`` in its template)? Then it is only handed out with the token."""
    cfile = manifest.get("connection_file")
    return bool(cfile) and "{token}" in cfile["template"]


def settings_hash(manifest: dict, values: dict) -> str:
    """A short fingerprint of the settings a package is built from (everything a person typed; what the service reports is left out): it tells whether
    the settings changed since a package was handed out."""
    import hashlib

    types = {f["key"]: f["type"] for f in manifest.get("settings", []) if "key" in f}
    kept = {k: v for k, v in sorted(values.items()) if types.get(k, "text") != "value"}
    return hashlib.sha256(json.dumps(kept, sort_keys=True).encode()).hexdigest()[:16]


def token_by_guide(manifest: dict) -> bool:
    """A plugin with a set-up guide AND a connection file gets its token ONLY by the choice in step 2 (new / existing / kept): nothing makes one before
    (not the installation, not the start of its service, not saving the settings)."""
    return bool(manifest.get("setup") and manifest.get("connection_file")) and needs_token(manifest)


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
        and needs_token(addon["m"])
        and (not addon["m"].get("service") or addon["m"].get("connection_file"))
    ):
        token = connectors.create_token(conn, f"{addon['m']['name']}", vehicle_id)
        token_id = conn.execute("SELECT id FROM api_tokens ORDER BY id DESC LIMIT 1").fetchone()["id"]
        connectors.remember(conn, token_id, token)  # every plugin token: an administrator can read it again on the tab *General*
    conn.execute(
        "UPDATE vehicle_addons SET status = 'configured', settings = ?, token_id = ? WHERE id = ?",
        (json.dumps(_sealed(addon["m"], _guide_values(addon, form, only))), token_id, addon["id"]),
    )
    return token


def save_flow_values(conn: sqlite3.Connection, addon: dict, form: dict, keys: set[str]) -> None:
    """A step of the set-up flow saves the settings it showed (and only those); the plugin is NOT marked as configured by it - the last step does that."""
    new = _guide_values(addon, form, keys)
    conn.execute("UPDATE vehicle_addons SET settings = ? WHERE id = ?", (json.dumps(_sealed(addon["m"], new)), addon["id"]))


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
    connectors.remember(conn, token_id, token)
    return token


def update_manifest(
    conn: sqlite3.Connection, addon: dict, manifest: dict, pkg_sha: str | None = None, source_id: int | None = None
) -> None:
    """A newer version from the source: replace the description, keep the settings, the token and the state. When the service description
    changed, the approval no longer matches (service_fingerprint) and the service waits for a new one. A package that had NO source is linked
    to ``source_id`` (the source the update came from), so its next updates come from there."""
    if needs_package(manifest) and not pkg_sha:
        raise AddonError("addon.err_service_upload")
    conn.execute(
        "UPDATE vehicle_addons SET manifest = ?, pkg_sha = COALESCE(?, pkg_sha), source_id = COALESCE(source_id, ?) WHERE id = ?",
        (json.dumps(manifest), pkg_sha, source_id, addon["id"]),
    )
    if (
        addon["kind"] == "plugin" and addon.get("token_id") and not needs_token(manifest)
    ):  # the new version has no token: the old one is revoked
        connectors.delete_token(conn, addon["token_id"])
        conn.execute("UPDATE vehicle_addons SET token_id = NULL WHERE id = ?", (addon["id"],))


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
    conn.execute("DELETE FROM addon_deliveries WHERE addon_pk = ?", (addon["id"],))
    conn.execute("DELETE FROM vehicle_addons WHERE id = ?", (addon["id"],))
    from . import oauth

    oauth.prune(conn)  # the tokens of a login nobody uses any more go with the install
    if addon["kind"] == "integration":
        from . import navigation

        navigation.forget(conn, addon["vehicle_id"], navigation.X + addon["addon_id"])
