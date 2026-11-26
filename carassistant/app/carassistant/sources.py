"""Sources: the places packages (integrations and plugins) are offered from. One list for the whole server (server level, never per vehicle).

A source is a GitHub repository (``https://github.com/<owner>/<repo>``) or any https address that serves the same files. Fixed layout
(docs/sources.md):

    integrations/index.json      {"packages": [{"id", "name", "description", "version"}, ...]}
    integrations/<id>/plugin.json
    plugins/index.json
    plugins/<id>/plugin.json

Nothing is requested from a source on its own: only when the user presses *Update* (or adds the source, opens a package, installs or updates it).

How a file is read (``_read``): a public GitHub repository comes from raw.githubusercontent.com - that is no API request and counts against no quota (the
API allows 60 an hour for EVERYONE behind one internet address); a file is kept with the ETag the server named, so asking again costs nothing; and the
standard source needs no connection at all until the person updates it: the copy that came with this version of the app (``stdsource/``) answers.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import socket
import sqlite3
import threading
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urlsplit

from . import addons, db, icons, vault

MAX_SOURCES = 50
MAX_FILE = 200_000  # bytes per downloaded file
MAX_VEHICLE = 25_000_000  # a vehicle backup may carry photos
MAX_PACKAGES = 200  # per index
TIMEOUT = 10
KINDS = ("integration", "plugin")
FOLDER = {"integration": "integrations", "plugin": "plugins"}
DEFAULT_URL = "https://github.com/Matze89x/ha-car-assistant-sources"  # temporary factory source (docs/sources.md)
DEFAULT_NAME = "Car Assistant"
BUNDLE = Path(__file__).parent / "stdsource"  # the standard source as it was when this version was made (tools/sync_stdsource.py)
CACHE_SECONDS = (
    600  # a file read a moment ago is not asked for again; *Update list* always asks (an unchanged file is answered "not modified")
)
DEMO_IDS = ("demo-diesel", "demo-electric")  # the demo cars of the standard source: offered by "Just have a look", not in the list of cars
GITHUB = re.compile(r"^https://github\.com/([A-Za-z0-9][A-Za-z0-9-]{0,38})/([A-Za-z0-9._-]{1,100})$")


class SourceError(ValueError):
    """The address, name or request is not acceptable; the message is an i18n key."""


# ------------------------------------------------------------------ addresses


def clean_url(raw: str) -> str:
    url = (raw or "").strip()
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment or len(url) > 300:
        raise SourceError("err.src_url")
    url = url.rstrip("/")
    return url[:-4] if url.endswith(".git") else url


def _github(url: str) -> tuple[str, str] | None:
    found = GITHUB.match(url)
    return (found.group(1), found.group(2)) if found else None


# ------------------------------------------------------------------ the list


def _flag(kind: str) -> str:
    if kind not in KINDS:
        raise SourceError("err.src_missing")
    return "for_" + kind  # column name: for_integration | for_plugin


def listing(conn: sqlite3.Connection, kind: str) -> list[dict]:
    """The sources of one list (Integrations or Plugins) with what each offers and has installed - of that kind only."""
    rows = conn.execute(
        "SELECT s.id, s.name, s.url, s.is_default, s.checked_at, s.online_at, s.error, s.note, (s.token IS NOT NULL AND s.token != '') AS has_token, "
        "(SELECT COUNT(*) FROM source_packages p WHERE p.source_id = s.id AND p.kind = ?1) AS n_packages, "
        "(SELECT COUNT(*) FROM vehicle_addons a WHERE a.source_id = s.id AND a.kind = ?1) AS n_installed, "
        "s.for_integration, s.for_plugin "
        f"FROM sources s WHERE s.{_flag(kind)} = 1 ORDER BY s.is_default DESC, s.name COLLATE NOCASE, s.id",
        (kind,),
    ).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        item["bundled"] = (
            r["url"] == DEFAULT_URL and r["online_at"] is None and r["n_packages"] > 0 and BUNDLE.is_dir()
        )  # only the copy of this version is known
        try:
            item["notes"] = json.loads(r["note"] or "[]")
        except ValueError:
            item["notes"] = []
        out.append(item)
    return out


def get(conn: sqlite3.Connection, source_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()


def auto_name(url: str) -> str:
    """A readable name for a source the user did not name: owner/repository for GitHub, else the host and the last part of the path."""
    gh = _github(url)
    if gh:
        return f"{gh[0]}/{gh[1]}"[:60]
    parts = urlsplit(url)
    tail = parts.path.strip("/").split("/")[-1]
    return f"{parts.hostname}/{tail}"[:60] if tail else (parts.hostname or url)[:60]


def add(conn: sqlite3.Connection, name: str, url: str, token: str, kind: str = "plugin") -> int:
    """Add a source. One source serves Integrations and Plugins alike, so it always goes into both lists (``kind`` is only kept for callers)."""
    url = clean_url(url)
    known = conn.execute("SELECT id, for_integration, for_plugin FROM sources WHERE url = ?", (url,)).fetchone()
    if known:
        if known["for_integration"] and known["for_plugin"]:
            raise SourceError("err.src_dup")
        conn.execute("UPDATE sources SET for_integration = 1, for_plugin = 1 WHERE id = ?", (known["id"],))
        if _clean_token(token):
            conn.execute("UPDATE sources SET token = ? WHERE id = ?", (vault.encrypt(_clean_token(token)), known["id"]))
        return known["id"]
    if conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] >= MAX_SOURCES:
        raise SourceError("err.src_many")
    typed = " ".join((name or "").split())[:60]
    return conn.execute(
        "INSERT INTO sources(name, url, token, for_integration, for_plugin, name_auto) VALUES(?, ?, ?, 1, 1, ?)",
        (typed or auto_name(url), url, vault.encrypt(_clean_token(token)) or None, 0 if typed else 1),
    ).lastrowid


def _clean_token(raw: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.=-]", "", raw or "")[:255]


def set_token(conn: sqlite3.Connection, source_id: int, token: str, remove: bool = False) -> None:
    value = None if remove else (vault.encrypt(_clean_token(token)) or None)
    if value is None and not remove:
        return  # blank = keep the stored key
    conn.execute("UPDATE sources SET token = ? WHERE id = ?", (value, source_id))


def restore_default(conn: sqlite3.Connection, kind: str = "plugin") -> None:
    if conn.execute("UPDATE sources SET for_integration = 1, for_plugin = 1 WHERE url = ?", (DEFAULT_URL,)).rowcount == 0:
        conn.execute(
            "INSERT INTO sources(name, url, is_default, for_integration, for_plugin) VALUES(?, ?, 1, 1, 1)", (DEFAULT_NAME, DEFAULT_URL)
        )


def seed_defaults(conn: sqlite3.Connection) -> None:
    """The factory setting: the standard source. Used for a fresh install (migration) and after a factory reset."""
    restore_default(conn)


def seed_bundled(conn: sqlite3.Connection) -> None:
    """The standard source as it came with this version of the app (``stdsource/``) fills its list without any connection - on the first start, and again when
    a newer version of the app brought a newer copy (then what was read online before is dropped: the copy of the app is the newer one). Nothing goes online."""
    source = conn.execute("SELECT id FROM sources WHERE url = ?", (DEFAULT_URL,)).fetchone()
    if source is None or not BUNDLE.is_dir():
        return
    version_file = BUNDLE / "VERSION"
    version = version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else ""
    listed = conn.execute("SELECT 1 FROM source_packages WHERE source_id = ? LIMIT 1", (source["id"],)).fetchone()
    if db.get_setting(conn, "stdsource.seen", "") == version and listed:
        return
    conn.execute("DELETE FROM source_cache WHERE source_id = ?", (source["id"],))
    conn.execute("UPDATE sources SET online_at = NULL WHERE id = ?", (source["id"],))
    refresh(conn, source["id"], offline=True)
    db.set_setting(conn, "stdsource.seen", version)


def installed_count(conn: sqlite3.Connection, source_id: int, kind: str) -> int:
    return conn.execute("SELECT COUNT(*) FROM vehicle_addons WHERE source_id = ? AND kind = ?", (source_id, kind)).fetchone()[0]


def remove(conn: sqlite3.Connection, source_id: int, kind: str = "plugin") -> None:
    """Delete a source - not while an integration or plugin installed from it remains (it would lose its origin and its updates)."""
    if any(installed_count(conn, source_id, k) for k in KINDS):
        raise SourceError("err.src_in_use")
    conn.execute("DELETE FROM source_cache WHERE source_id = ?", (source_id,))
    conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))


# ------------------------------------------------------------------ talking to a source


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # a source answers itself; it never sends us elsewhere
        return None


def _public_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except OSError:
        return False
    return all(
        not (a := ipaddress.ip_address(i[4][0])).is_private and not a.is_loopback and not a.is_link_local and not a.is_reserved
        for i in infos
    )


class Body(bytes):
    """A file as the server sent it: its bytes, the ``etag`` it named, and ``not_modified`` when the server answered "still the same" (no bytes then)."""

    etag: str | None = None
    not_modified: bool = False


def _http(url: str, headers: dict[str, str], check_host: bool, limit: int = MAX_FILE) -> bytes:
    """GET one file. With ``If-None-Match`` among the headers a file that did not change is answered "not modified" (it costs no quota). Raises
    SourceError(i18n key); a missing file is signalled with ``err.src_missing``."""
    host = urlsplit(url).hostname or ""
    if check_host and not _public_host(host):
        raise SourceError("err.src_host")
    request = urllib.request.Request(url, headers={"User-Agent": "car-assistant", **headers})  # noqa: S310 - https only, see clean_url
    try:
        with urllib.request.build_opener(_NoRedirect).open(request, timeout=TIMEOUT) as response:
            data = Body(response.read(limit + 1))
            data.etag = response.headers.get("ETag")
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            same = Body()
            same.not_modified = True
            return same
        if exc.code == 404:
            raise SourceError("err.src_missing") from exc
        if exc.code == 429 or (exc.code == 403 and exc.headers is not None and exc.headers.get("X-RateLimit-Remaining") == "0"):
            raise SourceError("err.src_rate") from exc  # not a wrong key: GitHub allows only 60 anonymous API requests an hour per address
        raise SourceError("err.src_auth" if exc.code in (401, 403) else "err.src_net") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SourceError("err.src_net") from exc
    if len(data) > limit:
        raise SourceError("err.src_format")
    return data


def _where(source: sqlite3.Row, path: str) -> tuple[str, dict[str, str], bool]:
    """Where a file of a source is read, with which headers, and whether the host must be a public one. A public GitHub repository is read from
    raw.githubusercontent.com: no API request, no quota (the API allows 60 an hour for everyone behind one internet address - this app, other add-ons,
    the tools of the person). One with an access key goes through the API (the key lifts its limit to 5000 an hour)."""
    token = vault.decrypt(source["token"])
    gh = _github(source["url"])
    if gh and not token:
        return f"https://raw.githubusercontent.com/{gh[0]}/{gh[1]}/HEAD/{quote(path)}", {}, False
    if gh:
        headers = {"Accept": "application/vnd.github.raw+json", "X-GitHub-Api-Version": "2022-11-28", "Authorization": f"Bearer {token}"}
        return f"https://api.github.com/repos/{gh[0]}/{gh[1]}/contents/{quote(path)}", headers, False
    return f"{source['url']}/{quote(path)}", ({"Authorization": f"Bearer {token}"} if token else {}), True


def _bundled(source: sqlite3.Row, path: str) -> bytes | None:
    """A file of the standard source as it came with this version of the app (``stdsource/``), or None."""
    if source["url"] != DEFAULT_URL or ".." in path.split("/"):
        return None
    file = BUNDLE / path
    return file.read_bytes() if file.is_file() else None


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _age(stamp: str) -> float:
    try:
        return (datetime.now(UTC) - datetime.fromisoformat(stamp)).total_seconds()
    except ValueError:
        return float("inf")


_used = (
    threading.local()
)  # did this thread take a file from what was known (the limit was hit, or there is no connection) while it was reading?


def _read(
    conn: sqlite3.Connection, source: sqlite3.Row, path: str, limit: int = MAX_FILE, fresh: bool = False, offline: bool = False
) -> bytes:
    """One file of a source.

    A small file is kept with the ETag the server named: asked again, the server answers "not modified" for a file that did not change - no quota, no bytes.
    ``fresh`` (the person pressed *Update list*) always asks; otherwise a file read in the last ten minutes is not asked for again - a file the source does
    not have (an optional index) is kept as "not there" the same way. The standard source needs no connection until it was read online once: what came
    with this version of the app answers. When the limit is hit or there is no connection, what was known before answers (``_used.fallback`` says so);
    ``offline`` never asks (the copy of the app only)."""
    cacheable = limit == MAX_FILE
    row = (
        conn.execute("SELECT etag, body, checked_at FROM source_cache WHERE source_id = ? AND path = ?", (source["id"], path)).fetchone()
        if cacheable
        else None
    )
    own = _bundled(source, path) if source["online_at"] is None or offline else None
    if offline:
        if own is not None:
            return own
        raise SourceError("err.src_missing")
    if not fresh:
        if row is not None and _age(row["checked_at"]) < CACHE_SECONDS:
            if not row["body"]:
                raise SourceError("err.src_missing")  # the source did not have this file a moment ago
            return bytes(row["body"])
        if own is not None:
            return own
    url, headers, check = _where(source, path)
    if row is not None and row["etag"]:
        headers = {**headers, "If-None-Match": row["etag"]}
    try:
        data = _http(url, headers, check, **({"limit": limit} if limit != MAX_FILE else {}))
    except SourceError as exc:
        if str(exc) in ("err.src_rate", "err.src_net"):
            if row is not None and not row["body"]:
                raise SourceError("err.src_missing") from exc  # it was not there before: a limit does not make it appear
            # a limit or no connection: what was known is better than nothing
            kept = bytes(row["body"]) if row is not None else _bundled(source, path)
            if kept is not None:
                _used.fallback = True
                return kept
        elif str(exc) == "err.src_missing" and cacheable:
            _keep(conn, source, path, None, b"")  # an optional file the source does not have: not asked for again within ten minutes
        raise
    if getattr(data, "not_modified", False) and row is not None and row["body"]:
        conn.execute("UPDATE source_cache SET checked_at = ? WHERE source_id = ? AND path = ?", (_now(), source["id"], path))
        return bytes(row["body"])
    etag = getattr(data, "etag", None)
    if cacheable and etag:
        _keep(conn, source, path, etag, bytes(data))
    return bytes(data)


def _keep(conn: sqlite3.Connection, source: sqlite3.Row, path: str, etag: str | None, body: bytes) -> None:
    """Remember a file of a source with the ETag the server named (an empty body: the source does not have the file)."""
    conn.execute(
        "INSERT INTO source_cache(source_id, path, etag, body, checked_at) VALUES(?,?,?,?,?) "
        "ON CONFLICT(source_id, path) DO UPDATE SET etag = excluded.etag, body = excluded.body, checked_at = excluded.checked_at",
        (source["id"], path, etag, body, _now()),
    )


def _json(raw: bytes) -> dict:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise SourceError("err.src_format") from exc
    if not isinstance(data, dict):
        raise SourceError("err.src_format")
    return data


def _text(value: object, limit: int) -> str:
    return " ".join(value.split())[:limit] if isinstance(value, str) else ""


def _entries(data, *keys: str) -> list:
    """The list of entries of an index: {"packages": [...]} (also the kind's own key) or a bare list."""
    if isinstance(data, list):
        return data
    for key in (*keys, "packages", "items"):
        if isinstance(data.get(key), list):
            return data[key]
    return []


def _clean_entries(entries: list, kind: str) -> tuple[list[dict], list[dict]]:
    """Valid entries, and the ones that were left out with the reason (shown on the source so authors can fix them)."""
    good, skipped = [], []
    for item in entries[:MAX_PACKAGES]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            skipped.append({"kind": kind, "id": "", "why": "shape"})
        elif not addons.ID.match(item["id"]):
            skipped.append({"kind": kind, "id": item["id"][:40], "why": "id"})
        else:
            good.append(
                {
                    "id": item["id"],
                    "name": _text(item.get("name"), 80) or item["id"],
                    "description": _text(item.get("description"), 300),
                    "version": _text(item.get("version"), 20),
                    "icon": item.get("icon") if item.get("icon") in icons.ICONS else "",
                }
            )
    return good, skipped


def _load_index(conn: sqlite3.Connection, source: sqlite3.Row, path: str, fresh: bool = False, offline: bool = False):
    """The parsed index file at ``path`` or None when the source has none; SourceError when it is not usable."""
    try:
        raw = _read(conn, source, path, fresh=fresh, offline=offline)
    except SourceError as exc:
        if str(exc) == "err.src_missing":
            return None
        raise
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise SourceError("err.src_format") from exc
    if not isinstance(data, dict | list):
        raise SourceError("err.src_format")
    return data


def _index(
    conn: sqlite3.Connection, source: sqlite3.Row, kind: str, fresh: bool = False, offline: bool = False
) -> tuple[list[dict], list[dict]] | None:
    """The cleaned index of one kind (and what was left out), or None when the source has none for it."""
    data = _load_index(conn, source, f"{FOLDER[kind]}/index.json", fresh, offline)
    return None if data is None else _clean_entries(_entries(data, FOLDER[kind]), kind)


def _vehicle_index(conn: sqlite3.Connection, source: sqlite3.Row, fresh: bool = False, offline: bool = False) -> list[dict] | None:
    """Optional: vehicles/index.json lists car backups (vehicles/<id>.zip) that can be restored from this source."""
    data = _load_index(conn, source, "vehicles/index.json", fresh, offline)
    return None if data is None else _clean_entries(_entries(data, "vehicles"), "vehicle")[0]


def _root_name(conn: sqlite3.Connection, source: sqlite3.Row, fresh: bool = False, offline: bool = False) -> str:
    """Optional: a root index.json may carry {"name": "..."} - the name the source gives itself."""
    try:
        data = _load_index(conn, source, "index.json", fresh, offline)
    except SourceError:
        return ""
    return _text(data.get("name"), 60) if isinstance(data, dict) else ""


def refresh(conn: sqlite3.Connection, source_id: int, offline: bool = False) -> str | None:
    """Read both indexes of one source and replace what was known. Returns None or an i18n error key (also stored on the source). The person's *Update list*
    always asks the server (an unchanged file is answered "not modified" and costs no quota); when the limit is hit or there is no connection the list is
    made from what was known and the source says ``err.src_stale``. ``offline`` reads only the copy that came with this version (seed_bundled)."""
    source = get(conn, source_id)
    if source is None:
        return "err.src_missing"
    fresh = not offline
    _used.fallback = False
    found: dict[str, list[dict]] = {}
    notes: list[dict] = []
    error = None
    vehicles: list[dict] = []
    new_name = ""
    try:
        for kind in KINDS:
            if not source[_flag(kind)]:
                continue
            index = _index(conn, source, kind, fresh, offline)
            if index is not None:
                found[kind] = index[0]
                notes += index[1]
        vehicles = _vehicle_index(conn, source, fresh, offline) or []
        if not found and not vehicles:
            error = "err.src_empty"
        else:  # a list the source is in but has no index for: nothing offered there
            for kind in KINDS:
                if source[_flag(kind)] and kind not in found:
                    found[kind] = []
        if source["name_auto"]:
            new_name = _root_name(conn, source, fresh, offline)
    except SourceError as exc:
        error = str(exc)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    if error is None:
        conn.execute("DELETE FROM source_packages WHERE source_id = ? AND kind = 'vehicle'", (source_id,))
        conn.executemany(
            "INSERT INTO source_packages(source_id, kind, pkg_id, name, description, version, icon) VALUES(?,?,?,?,?,?,?)",
            [(source_id, "vehicle", p["id"], p["name"], p["description"], p["version"], p["icon"]) for p in vehicles],
        )
        for kind, packages in found.items():
            conn.execute("DELETE FROM source_packages WHERE source_id = ? AND kind = ?", (source_id, kind))
            conn.executemany(
                "INSERT INTO source_packages(source_id, kind, pkg_id, name, description, version, icon) VALUES(?,?,?,?,?,?,?)",
                [(source_id, kind, p["id"], p["name"], p["description"], p["version"], p["icon"]) for p in packages],
            )
        if new_name:
            conn.execute("UPDATE sources SET name = ? WHERE id = ?", (new_name, source_id))
    stale = error is None and bool(getattr(_used, "fallback", False))
    error = "err.src_stale" if stale else error
    conn.execute(
        "UPDATE sources SET checked_at = COALESCE(?, checked_at), online_at = COALESCE(?, online_at), error = ?, note = ? WHERE id = ?",
        (None if offline else now, now if error is None and not offline else None, error, json.dumps(notes) if notes else None, source_id),
    )
    return error


def updates_for(conn: sqlite3.Connection, vehicle_id: int, kind: str) -> int:
    """How many installed packages of this car have a newer version in their source (as of the last reading of the sources)."""
    return sum(1 for a in addons.list_for(conn, vehicle_id) if a["kind"] == kind and a["has_update"])


def refresh_all(conn: sqlite3.Connection, kind: str) -> int:
    """Update every source of one list; returns how many failed."""
    rows = conn.execute(f"SELECT id FROM sources WHERE {_flag(kind)} = 1").fetchall()
    return sum(1 for row in rows if refresh(conn, row["id"]))


MAX_PACKAGE_ZIP = 40_000_000  # a package with a service: its code (and perhaps its wheels)


def fetch_package(conn: sqlite3.Connection, source_id: int, kind: str, pkg_id: str, files: list[dict] | None = None) -> tuple[bytes, str]:
    """The ``package.zip`` of a package with a service and its sha256. The index of the source must name that sha256 and the file must match it,
    otherwise nothing is returned (``err.src_hash``). An index that is a few minutes old and does not fit is read once more, asked afresh."""
    source = get(conn, source_id)
    if source is None or kind not in KINDS or not addons.ID.match(pkg_id):
        raise SourceError("err.src_missing")
    for fresh in (False, True):
        data = _load_index(conn, source, f"{FOLDER[kind]}/index.json", fresh=fresh)
        entry = next((e for e in _entries(data or {}, FOLDER[kind]) if isinstance(e, dict) and e.get("id") == pkg_id), None)
        wanted = entry.get("sha256") if entry else None
        if not isinstance(wanted, str) or not re.fullmatch(r"[0-9a-f]{64}", wanted.lower()):
            raise SourceError("err.src_hash")
        listed = {
            (f.get("name"), str(f.get("sha256", "")).lower(), f.get("size")) for f in (entry.get("files") or []) if isinstance(f, dict)
        }
        if any((f["name"], f["sha256"], f["size"]) not in listed for f in files or []):
            raise SourceError("err.src_hash")  # the index must name every file with the same checksum and size
        raw = _read(conn, source, f"{FOLDER[kind]}/{pkg_id}/package.zip", MAX_PACKAGE_ZIP)
        digest = hashlib.sha256(raw).hexdigest()
        if digest == wanted.lower():
            return raw, digest
    raise SourceError("err.src_hash")


def fetch_manifest(conn: sqlite3.Connection, source_id: int, kind: str, pkg_id: str) -> dict:
    """The cleaned ``plugin.json`` of one package. The folder decides the kind; the manifest id must match the folder name."""
    source = get(conn, source_id)
    if source is None or kind not in KINDS or not addons.ID.match(pkg_id):
        raise SourceError("err.src_missing")
    try:
        manifest = addons.parse_package(_read(conn, source, f"{FOLDER[kind]}/{pkg_id}/plugin.json"))
    except addons.AddonError as exc:
        raise SourceError("err.src_format") from exc
    if manifest["id"] != pkg_id:
        raise SourceError("err.src_format")
    manifest["kind"] = kind
    return manifest


# ------------------------------------------------------------------ what a vehicle can add


DEMO_PLUGIN = "demo-connector"


def available(conn: sqlite3.Connection, kind: str, vehicle_id: int) -> list[sqlite3.Row]:
    """Packages of the known indexes; ``installed`` marks the ones this vehicle already has - whatever they came from. ``origin`` says where the
    installed one came from: ``here`` (this source), ``other`` (another source) or ``none`` (a file, or no source at all); None when it is not installed.
    A package waiting for its files after a restore (``missing``) does not count as installed."""
    return conn.execute(
        "SELECT q.*, (q.origin IS NOT NULL) AS installed FROM ("
        # three plain EXISTS tests (older SQLite versions cannot refer to the outer row inside an ORDER BY): from here, from no source, from another one
        "SELECT p.*, s.name AS source_name, CASE "
        "WHEN EXISTS (SELECT 1 FROM vehicle_addons a WHERE a.vehicle_id = ?2 AND a.addon_id = p.pkg_id AND a.kind = p.kind AND a.status != 'missing' "
        "AND a.source_id = p.source_id) THEN 'here' "
        "WHEN EXISTS (SELECT 1 FROM vehicle_addons a WHERE a.vehicle_id = ?2 AND a.addon_id = p.pkg_id AND a.kind = p.kind AND a.status != 'missing' "
        "AND a.source_id IS NULL) THEN 'none' "
        "WHEN EXISTS (SELECT 1 FROM vehicle_addons a WHERE a.vehicle_id = ?2 AND a.addon_id = p.pkg_id AND a.kind = p.kind AND a.status != 'missing') "
        "THEN 'other' END AS origin "
        "FROM source_packages p JOIN sources s ON s.id = p.source_id "
        "WHERE p.kind = ?1 AND (CASE p.kind WHEN 'plugin' THEN s.for_plugin ELSE s.for_integration END) = 1 "
        "AND NOT (s.url = ?3 AND p.kind = 'plugin' AND p.pkg_id = ?4)"  # the demo plugin only belongs to the demo cars: never offered to pick
        ") q ORDER BY q.name COLLATE NOCASE",
        (kind, vehicle_id, DEFAULT_URL, DEMO_PLUGIN),
    ).fetchall()


def package(conn: sqlite3.Connection, source_id: int, kind: str, pkg_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT p.*, s.name AS source_name FROM source_packages p JOIN sources s ON s.id = p.source_id "
        "WHERE p.source_id = ? AND p.kind = ? AND p.pkg_id = ?",
        (source_id, kind, pkg_id),
    ).fetchone()


def version_key(text: str) -> tuple:
    """'1.10.2' > '1.9' (numbers compared as numbers; anything else sorts by its text)."""
    return tuple((0, int(p)) if p.isdigit() else (1, p) for p in re.split(r"[.\-]", text or "") if p)


def is_newer(candidate: str, installed: str) -> bool:
    return bool(candidate) and version_key(candidate) > version_key(installed)


# ------------------------------------------------------------------ vehicles (car backups) offered by sources


def available_vehicles(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Cars that sources offer for restoring - without the demo cars of the standard source (they have their own 'Just have a look')."""
    return conn.execute(
        "SELECT p.*, s.name AS source_name FROM source_packages p JOIN sources s ON s.id = p.source_id "
        "WHERE p.kind = 'vehicle' AND NOT (s.url = ? AND p.pkg_id IN (?, ?)) ORDER BY p.name COLLATE NOCASE",
        (DEFAULT_URL, *DEMO_IDS),
    ).fetchall()


def demo_offered(conn: sqlite3.Connection) -> bool:
    """'Just have a look' needs the standard source: without it (deleted) there is no connection and no demo."""
    return (
        conn.execute("SELECT 1 FROM sources WHERE url = ? AND (for_integration = 1 OR for_plugin = 1)", (DEFAULT_URL,)).fetchone()
        is not None
    )


def fetch_vehicle(conn: sqlite3.Connection, source_id: int, pkg_id: str) -> bytes:
    """The backup file of one offered car (vehicles/<id>.zip)."""
    source = get(conn, source_id)
    if source is None or not addons.ID.match(pkg_id):
        raise SourceError("err.src_missing")
    return _read(conn, source, f"vehicles/{pkg_id}.zip", MAX_VEHICLE)
