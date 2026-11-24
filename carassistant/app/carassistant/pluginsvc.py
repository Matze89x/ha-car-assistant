"""Plugins with their own service: a process inside this add-on, started and watched by the app (docs/plugins.md, "Plugins with a service").

This is the one place where code from a package runs. It is held to strict rules:
- only a package that came from a **source** (checked against the sha256 of the source's index) can have a service, never an uploaded file;
- nothing runs before an **administrator approved** the description of the service (entry, Python version, requirements, routes, environment);
  a new version that changes that description needs a new approval;
- the service is its **own process**, in its **own virtual environment**, as its **own unprivileged user** (when the add-on runs as root), with
  limits for memory, files and processes, and with an environment that holds only what is listed in docs/plugins.md - never the Supervisor
  token, never the database;
- it talks to the app through the normal Plugin API with a token of its own, and the car (or anyone) reaches it only through the public
  routes it declared (``proxy.py``).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import venv
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from . import addons, config, connectors, db, events

log = logging.getLogger("carassistant.pluginsvc")

UID_BASE = 30000  # a service of vehicle_addons row N runs as user 30000+N (no entry in /etc/passwd needed)
MEM_MB = 768
READABLE = {
    ".py",
    ".sh",  # text only: it can be put into a bundle, the app never runs it
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
MAX_FILES = 2000
MAX_UNPACKED = 120_000_000
INSTALL_TIMEOUT = 900
BACKOFF = (5, 10, 30, 60, 120)  # seconds before the next restart after a crash
RESERVED = {
    "",
    "static",
    "healthz",
    "api",
    "v",
    "integrations",
    "settings",
    "account",
    "sources",
    "setup",
    "vehicles",
    "auth",
    "media",
    "plugins",
}

_lock = threading.RLock()
_procs: dict[int, dict] = {}  # addon row id -> {"proc", "port", "started", "fails", "next", "stop"}
_installing: set[int] = set()
_tail: dict[int, list[str]] = {}  # the last output lines of each service, in memory only (shown after a crash while debug is on)
_routes: dict[str, dict] = {}
_wake = threading.Event()
_stop = threading.Event()
_thread: threading.Thread | None = None


# ------------------------------------------------------------------ paths and files


def root() -> Path:
    return config.data_dir() / "plugins"


def pkg_dir(addon_id: str, sha: str) -> Path:
    return root() / addon_id / "pkg" / sha[:16]


def venv_dir(addon_id: str) -> Path:
    return root() / addon_id / "venv"


def run_dir(addon_id: str, vehicle_id: int) -> Path:
    return root() / addon_id / str(vehicle_id)


def _is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


def _uid(pk: int) -> int:
    return UID_BASE + pk


def harden() -> None:
    """When the add-on runs as root: the data folder can be passed through but not read by the unprivileged users of the services, the database
    and everything else of the app stays closed to them."""
    if not _is_root():
        return
    with contextlib.suppress(OSError):
        os.chmod(config.data_dir(), 0o711)  # noqa: S103 - others may pass through, not read: the services must reach their own folder
        for path in config.data_dir().iterdir():  # everything of the app (database, documents, photos, backups) is closed to the services
            if path.name != "plugins" and not path.is_symlink():
                os.chmod(path, 0o700 if path.is_dir() else 0o600)
        root().mkdir(parents=True, exist_ok=True)
        os.chmod(root(), 0o711)  # noqa: S103


def files_root() -> Path:
    """Where the downloadable files of packages lie - apart from the code of the services, closed to them (see harden)."""
    return config.data_dir() / "plugin-files"


def asset_dir(addon_id: str, sha: str) -> Path:
    return files_root() / addon_id / sha[:16]


def store_package(
    addon_id: str, raw: bytes, sha: str, entry: str | None = None, files: list[dict] | None = None, bundles: list[dict] | None = None
) -> None:
    """Unpack the package zip (already checked against its sha256) next to the others. Nothing is run and nothing is opened beyond reading the bytes.
    Text files go to the code folder; the ``files`` (checked binaries) go to their own read-only folder, only when every checksum and size matches.
    Raises ValueError on anything odd - then nothing at all is kept."""
    files, bundles = files or [], bundles or []
    dest, assets = pkg_dir(addon_id, sha), asset_dir(addon_id, sha)
    if (not entry or (dest / entry).is_file()) and dest.is_dir() and all((assets / f["name"]).is_file() for f in files):
        return
    asset_paths = {f["path"]: f for f in files}
    tmp, tmp_assets = dest.with_name(dest.name + ".tmp"), assets.with_name(assets.name + ".tmp")
    for folder in (tmp, tmp_assets):
        shutil.rmtree(folder, ignore_errors=True)
    tmp.mkdir(parents=True)
    try:
        with zipfile.ZipFile(__import__("io").BytesIO(raw)) as z:
            infos = z.infolist()
            if len(infos) > MAX_FILES or sum(i.file_size for i in infos) > MAX_UNPACKED:
                raise ValueError("size")
            names = {i.filename for i in infos if not i.is_dir()}
            for info in infos:
                name = info.filename
                parts = Path(name).parts
                if name.startswith(("/", "\\")) or ".." in parts or ":" in name or (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("path")
                if not info.is_dir() and name not in asset_paths and Path(name).suffix.lower() not in READABLE:
                    raise ValueError("unreadable")  # only text files and plain images - except the declared files below
            for f in files:  # every file must be there and match its checksum and size, before anything is unpacked
                if f["path"] not in names:
                    raise ValueError("asset missing")
                data = z.read(f["path"])
                if len(data) != f["size"] or hashlib.sha256(data).hexdigest() != f["sha256"]:
                    raise ValueError("asset checksum")
            for bundle in bundles:
                for e in bundle["entries"]:
                    if e["from"] not in names:
                        raise ValueError("bundle source")
            for info in infos:
                if info.filename in asset_paths:
                    continue
                target = tmp / info.filename
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(z.read(info))
            if files:
                tmp_assets.mkdir(parents=True)
                for f in files:
                    (tmp_assets / f["name"]).write_bytes(z.read(f["path"]))
        if entry and not (tmp / entry).is_file():
            raise ValueError("entry")
        shutil.rmtree(dest, ignore_errors=True)
        tmp.replace(dest)
        _readable(dest)
        if files:
            shutil.rmtree(assets, ignore_errors=True)
            assets.parent.mkdir(parents=True, exist_ok=True)
            tmp_assets.replace(assets)
            for p in assets.iterdir():
                os.chmod(p, 0o444)  # read-only, never executable
            os.chmod(assets, 0o555)  # noqa: S103 - read and enter, nobody writes
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError("zip") from exc
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(tmp_assets, ignore_errors=True)


def _readable(path: Path) -> None:
    """Code and environments belong to root but may be read and run by the services."""
    with contextlib.suppress(OSError):
        for p in [path, *path.rglob("*")]:
            if not p.is_symlink():
                os.chmod(p, (p.stat().st_mode | 0o444 | (0o111 if p.is_dir() else 0)) & ~0o022)


# ------------------------------------------------------------------ approval and installation


def service_of(addon: dict) -> dict | None:
    return (addon.get("m") or {}).get("service")


def approved(addon: dict) -> bool:
    """The administrator approved exactly what the package now says (its service, its files, its bundles)."""
    fingerprint = addons.approval_fingerprint(addon.get("m") or {})
    return bool(fingerprint) and addon.get("svc_ok") == fingerprint


def check_routes(conn, addon: dict) -> list[str]:
    """Reasons the routes of this service may not be used (empty = fine): a prefix that would cover a page of the app, or one another service has."""
    from . import web

    taken_by_app = {r.path.split("/")[1] for r in web.app.routes if getattr(r, "path", "").startswith("/") and len(r.path.split("/")) > 1}
    problems: list[str] = []
    mine = (service_of(addon) or {}).get("routes", [])
    others = []
    for row in conn.execute("SELECT id, manifest FROM vehicle_addons WHERE id != ? AND status != 'missing'", (addon["id"],)):
        others += [r["prefix"] for r in (json.loads(row["manifest"]).get("service") or {}).get("routes", [])]
    for route in mine:
        prefix = route["prefix"]
        first = prefix.split("/")[1]
        if first in RESERVED or first in taken_by_app:
            problems.append(f"{prefix} (app)")
        elif any(prefix.startswith(o) or o.startswith(prefix) for o in others):
            problems.append(f"{prefix} (taken)")
    return problems


def approve(conn, addon: dict) -> str | None:
    """An administrator confirmed the description. Returns an i18n key when it cannot be approved."""
    if not addons.needs_package(addon.get("m") or {}) or addon.get("source_id") is None or not addon.get("pkg_sha"):
        return "svc.err_nosource"
    if service_of(addon) and check_routes(conn, addon):
        return "svc.err_routes"
    conn.execute(
        "UPDATE vehicle_addons SET svc_ok = ?, svc_error = NULL WHERE id = ?", (addons.approval_fingerprint(addon["m"]), addon["id"])
    )
    _event(addon, "info", "An administrator approved the service", conn)
    return None


def revoke(conn, addon: dict) -> None:
    conn.execute("UPDATE vehicle_addons SET svc_ok = NULL WHERE id = ?", (addon["id"],))
    _event(addon, "info", "The approval was taken back - the service is stopped", conn)
    stop(addon["id"])


def _event(addon: dict | sqlite3.Row, level: str, text: str, conn=None) -> None:
    """A line in the plugin's log about what the add-on does with its service (install, start, crash, restart, stop). Written whether or not debug is on:
    these lines say where something goes wrong and hold nothing about the car."""
    row = [(datetime.now(UTC).isoformat(timespec="seconds"), level, "system", text[:500])]
    try:
        if conn is not None:
            connectors.write_logs(conn, addon["vehicle_id"], addon["addon_id"], row)
        else:
            with db.tx() as own:
                connectors.write_logs(own, addon["vehicle_id"], addon["addon_id"], row)
    except Exception:
        log.debug("could not write a service event", exc_info=True)


def _python_ok(service: dict) -> bool:
    wanted = service.get("python")
    if not wanted:
        return True
    major, minor = (int(x) for x in wanted[2:].split("."))
    return sys.version_info[:2] >= (major, minor)


def _install(pk: int) -> None:
    """Make the virtual environment and install the requirements from PyPI (only ready wheels - nothing is built on the way)."""
    error = None
    addon_id = None
    try:
        with db.tx() as conn:
            row = conn.execute("SELECT vehicle_id FROM vehicle_addons WHERE id = ?", (pk,)).fetchone()
            addon = addons.get(conn, row["vehicle_id"], pk) if row else None
        if addon is None or not approved(addon):
            return
        addon_id = addon["addon_id"]
        service = service_of(addon)
        _event(addon, "info", f"Preparing the environment ({len(service['requirements'])} Python package(s) to install)")
        if not _python_ok(service):
            error = "svc.err_python"
            _event(
                addon,
                "error",
                f"This add-on has Python {sys.version_info.major}.{sys.version_info.minor}, the package needs {service.get('python')}",
            )
        else:
            env = venv_dir(addon_id)
            marker = env / f".reqs-{addons.service_fingerprint({'r': service['requirements']})[:16]}"
            if not marker.exists():
                shutil.rmtree(env, ignore_errors=True)
                venv.EnvBuilder(with_pip=bool(service["requirements"]), symlinks=True, clear=True).create(env)
                if service["requirements"]:
                    cmd = [
                        str(env / "bin" / "python"),
                        "-m",
                        "pip",
                        "install",
                        "--only-binary=:all:",
                        "--no-input",
                        "--disable-pip-version-check",
                    ]
                    cmd += service["requirements"]
                    done = subprocess.run(cmd, capture_output=True, text=True, timeout=INSTALL_TIMEOUT, check=False)  # noqa: S603
                    if done.returncode != 0:
                        log.warning("requirements of %s failed: %s", addon_id, done.stderr[-500:])
                        error = "svc.err_install"
                        _event(addon, "error", "pip failed: " + " ".join(done.stderr.split())[-400:])
                if not error:
                    marker.write_text("ok")
                    _readable(env)
                    _event(addon, "info", "Environment ready")
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        log.exception("installing the environment of plugin %s failed", pk)
        error = "svc.err_install"
        if addon is not None:
            _event(addon, "error", f"Installing the environment failed: {type(exc).__name__}: {str(exc)[:200]}")
    finally:
        with _lock:
            _installing.discard(pk)
        with db.tx() as conn:
            conn.execute("UPDATE vehicle_addons SET svc_error = ? WHERE id = ?", (error, pk))
        events.changed()
        _wake.set()


def install_async(pk: int) -> None:
    with _lock:
        if pk in _installing:
            return
        _installing.add(pk)
    threading.Thread(target=_install, args=(pk,), daemon=True, name=f"svc-install-{pk}").start()


# ------------------------------------------------------------------ processes


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _own(path: Path, pk: int) -> None:
    if _is_root():
        with contextlib.suppress(OSError):
            os.chown(path, _uid(pk), _uid(pk))


def write_token(addon: dict, token: str) -> None:
    """The token the person was given (shown once, for the connection file) is also the one the service uses: a copy goes into the service's own
    folder, readable by the service only. Used when a plugin with a service AND a connection file is set up or gets a new token."""
    folder = run_dir(addon["addon_id"], addon["vehicle_id"])
    folder.mkdir(parents=True, exist_ok=True)
    os.chmod(folder, 0o700)
    _own(folder, addon["id"])
    file = folder / ".token"
    file.write_text(token)
    os.chmod(file, 0o600)
    _own(file, addon["id"])


def _prepare_run(conn, addon: dict) -> tuple[Path, str]:
    """The data folder of this car's service with its token and settings file. Returns (folder, token)."""
    folder = run_dir(addon["addon_id"], addon["vehicle_id"])
    folder.mkdir(parents=True, exist_ok=True)
    os.chmod(folder, 0o700)
    _own(folder, addon["id"])
    token_file = folder / ".token"
    token = token_file.read_text().strip() if token_file.is_file() else ""
    if addon["kind"] == "integration":  # an integration has no token and cannot call the Plugin API: just its own data folder
        token = ""
    elif (not token or not addon.get("token_id")) and not addons.token_by_guide(addon["m"]):  # with a guide the token is chosen in step 2
        if addon.get("token_id"):
            connectors.delete_token(conn, addon["token_id"])
        token = connectors.create_token(conn, addon["m"]["name"], addon["vehicle_id"])
        conn.execute(
            "UPDATE vehicle_addons SET token_id = (SELECT id FROM api_tokens ORDER BY id DESC LIMIT 1) WHERE id = ?", (addon["id"],)
        )
        token_file.write_text(token)
        os.chmod(token_file, 0o600)
        _own(token_file, addon["id"])
    settings_file = folder / "settings.json"
    settings_file_values = addons.typed_settings(addon["m"], addon["vals"])
    vin_row = conn.execute("SELECT vin FROM vehicles WHERE id = ?", (addon["vehicle_id"],)).fetchone()
    settings_file_values["external_url"] = config.external_url() or ""  # what the app knows, so the service never asks for it again
    settings_file_values["vehicle_vin"] = vin_row["vin"] if vin_row and vin_row["vin"] else ""
    settings_file.write_text(json.dumps(settings_file_values, ensure_ascii=False))
    os.chmod(settings_file, 0o600)
    _own(settings_file, addon["id"])
    return folder, token


def _limits() -> None:  # runs in the child before the service starts
    import resource

    limit = MEM_MB * 1024 * 1024
    wanted = [(resource.RLIMIT_AS, limit), (resource.RLIMIT_NOFILE, 256)]
    if _is_root():
        wanted.append((resource.RLIMIT_NPROC, 64))
    for which, value in wanted:
        with contextlib.suppress(
            ValueError, OSError
        ):  # a system that does not know this limit (macOS for the address space): the others still apply
            resource.setrlimit(which, (value, value))
    os.umask(0o077)


def _env(addon: dict, folder: Path, token: str, port: int) -> dict[str, str]:
    service = service_of(addon)
    py = venv_dir(addon["addon_id"])
    env = {
        "PATH": f"{py / 'bin'}:/usr/local/bin:/usr/bin:/bin",
        "HOME": str(folder),
        "LANG": "C.UTF-8",
        "PYTHONUNBUFFERED": "1",
        "PYTHONPATH": str(pkg_dir(addon["addon_id"], addon["pkg_sha"])),
        **({"CA_API_URL": f"http://127.0.0.1:{config.port()}", "CA_API_TOKEN": token} if addon["kind"] != "integration" else {}),
        "CA_VEHICLE_ID": str(addon["vehicle_id"]),
        "CA_DATA_DIR": str(folder),
        "CA_PORT": str(port),
    }
    for name, template in service.get("env", {}).items():
        env[name] = re.sub(r"\{([a-z][a-z0-9_]*)\}", lambda m: str(addon["vals"].get(m.group(1), "")), template)
    return env


def _log_reader(pk: int, proc: subprocess.Popen, addon_id: str, vehicle_id: int) -> None:
    """The output of the service: kept only while debug is on for the car (same rule as the log lines of any plugin)."""
    assert proc.stdout is not None
    on, checked = False, 0.0
    for raw in proc.stdout:
        _tail.setdefault(pk, []).append(raw.decode("utf-8", "replace").rstrip()[:200])
        del _tail[pk][:-8]
        now = time.monotonic()
        if now - checked > 5:
            with contextlib.suppress(Exception), db.tx() as conn:
                on = connectors.debug_enabled(conn, vehicle_id, addon_id)
            checked = now
        if not on:
            continue
        line = raw.decode("utf-8", "replace").rstrip()[:500]
        if not line:
            continue
        with contextlib.suppress(Exception), db.tx() as conn:
            connectors.write_logs(
                conn, vehicle_id, addon_id, [(datetime.now(UTC).isoformat(timespec="seconds"), "info", f"service:{addon_id}"[:40], line)]
            )


def _start(conn, addon: dict) -> None:
    pk = addon["id"]
    service = service_of(addon)
    entry = pkg_dir(addon["addon_id"], addon["pkg_sha"]) / service["entry"]
    python = venv_dir(addon["addon_id"]) / "bin" / "python"
    if not entry.is_file() or not python.is_file():
        raise FileNotFoundError("environment")
    folder, token = _prepare_run(conn, addon)
    port = _free_port()
    kwargs: dict = {}
    if _is_root():
        kwargs = {"user": _uid(pk), "group": _uid(pk), "extra_groups": []}
    proc = subprocess.Popen(  # noqa: S603 - our own interpreter and the approved entry file
        [str(python), "-u", str(entry)],
        cwd=folder,
        env=_env(addon, folder, token, port),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        preexec_fn=_limits,
        start_new_session=True,
        **kwargs,
    )
    old = _procs.get(pk, {})
    _procs[pk] = {"proc": proc, "port": port, "started": time.monotonic(), "fails": old.get("fails", 0), "next": 0.0}
    threading.Thread(target=_log_reader, args=(pk, proc, addon["addon_id"], addon["vehicle_id"]), daemon=True, name=f"svc-log-{pk}").start()
    conn.execute(
        "UPDATE vehicle_addons SET svc_started = ?, svc_error = NULL WHERE id = ?", (datetime.now(UTC).isoformat(timespec="seconds"), pk)
    )
    log.info("service of plugin %s (car %s) started on port %s", addon["addon_id"], addon["vehicle_id"], port)
    _event(addon, "info", f"Service started (process {proc.pid}, port {port}, restarts so far {_procs[pk]['fails']})", conn)


def stop(pk: int, wait: float = 5.0) -> None:
    with _lock:
        info = _procs.pop(pk, None)
        _rebuild_routes()
    if info is None:
        return
    with contextlib.suppress(Exception), db.tx() as conn:
        row = conn.execute("SELECT vehicle_id, addon_id FROM vehicle_addons WHERE id = ?", (pk,)).fetchone()
        if row:
            _event(row, "info", "Service stopped", conn)
    proc: subprocess.Popen = info["proc"]
    if proc.poll() is None:
        with contextlib.suppress(OSError, ProcessLookupError):
            os.killpg(proc.pid, 15)
        try:
            proc.wait(wait)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(OSError, ProcessLookupError):
                os.killpg(proc.pid, 9)
            proc.wait(2)


def restart(pk: int) -> None:
    """After the settings changed: the service starts again with the new settings.json."""
    stop(pk)
    with _lock:
        _procs.pop(pk, None)
    _wake.set()


def running(pk: int) -> bool:
    with _lock:
        info = _procs.get(pk)
        return bool(info and info["proc"].poll() is None)


def call(pk: int, path: str, payload: dict, vehicle_id: int, user: str = "ha", timeout: float = 10.0) -> tuple[bool, str]:
    """The APP asks a running service for something it offers (a capability, for example ``navigate``): ``POST <path>`` with a JSON body.
    ``(True, message)`` when the service answers 2xx, else ``(False, reason)``. The service gets the same two identity headers as for a page."""
    with _lock:
        info = _procs.get(pk)
        port = info["port"] if info and info["proc"].poll() is None else None
    if not port:
        return False, "not running"
    body = json.dumps(payload).encode()
    import http.client

    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request(
            "POST",
            path,
            body,
            {"Content-Type": "application/json", "X-CA-Vehicle": str(vehicle_id), "X-CA-User": user, "Content-Length": str(len(body))},
        )
        response = conn.getresponse()
        raw = response.read(8192)
    except (OSError, http.client.HTTPException):
        return False, "no answer"
    finally:
        conn.close()
    try:
        data = json.loads(raw.decode("utf-8", "replace") or "{}")
    except ValueError:
        data = {}
    text = str(data.get("message") or data.get("error") or "")[:200] if isinstance(data, dict) else ""
    return (200 <= response.status < 300 and (not isinstance(data, dict) or data.get("ok") is not False)), text


def state(pk: int, addon: dict) -> str:
    """installing | stopped | waiting (not approved) | running | restarting | error"""
    if not service_of(addon):
        return ""
    if not approved(addon):
        return "waiting"
    with _lock:
        if pk in _installing:
            return "installing"
    if running(pk):
        return "running"
    if addon.get("svc_error"):
        return "error"
    if addon.get("active"):
        return "restarting" if _procs.get(pk) else "starting"
    return "stopped"


def _rebuild_routes() -> None:
    _routes.clear()
    with db.tx() as conn:
        rows = {r["id"]: r["manifest"] for r in conn.execute("SELECT id, manifest FROM vehicle_addons WHERE manifest LIKE '%\"service\"%'")}
    for pk, info in _procs.items():
        if info["proc"].poll() is None and pk in rows:
            for route in (json.loads(rows[pk]).get("service") or {}).get("routes", []):
                _routes[route["prefix"]] = {"port": info["port"], "public": route["public"], "pk": pk}


def note_car_request(pk: int, method: str, path: str, status: int, nbytes: int, started: float, detail: str, query: str = "") -> None:
    """A request from outside on a route of a service, for the traffic view - only while debug is on for the car."""
    try:
        with db.tx() as conn:
            row = conn.execute("SELECT vehicle_id, addon_id FROM vehicle_addons WHERE id = ?", (pk,)).fetchone()
            if row and status < 400:
                prefix = (route_for(path) or {}).get("prefix") or path
                connectors.note_usage(
                    conn, row["vehicle_id"], row["addon_id"], method, prefix, ""
                )  # the page *Interfaces*: which route is called
            if row and connectors.debug_enabled(conn, row["vehicle_id"], row["addon_id"]):
                connectors.record_traffic(
                    conn,
                    row["vehicle_id"],
                    row["addon_id"],
                    "car",
                    method,
                    path,
                    status,
                    nbytes,
                    round((time.monotonic() - started) * 1000),
                    detail or (f"query: {len(query)} characters" if query else ""),
                )
    except Exception:
        log.debug("could not note a request", exc_info=True)


def route_for(path: str) -> dict | None:
    with _lock:
        best = max((p for p in _routes if path.startswith(p)), key=len, default=None)
        return {"prefix": best, **_routes[best]} if best else None


def tick() -> None:
    """One round of supervision: start what should run, stop what should not, restart crashed services with a growing pause."""
    now = time.monotonic()
    with db.tx() as conn:
        rows = conn.execute(
            "SELECT id, vehicle_id FROM vehicle_addons WHERE kind IN ('plugin', 'integration') AND status != 'missing' AND manifest LIKE '%\"service\"%'"
        ).fetchall()
        want: dict[int, dict] = {}
        for r in rows:
            addon = addons.get(conn, r["vehicle_id"], r["id"])
            if addon and service_of(addon) and addon["active"] and approved(addon) and addon.get("pkg_sha") and not addon.get("svc_error"):
                if addons.token_by_guide(addon["m"]) and addon["status"] != "configured":
                    continue  # a plugin with a connection file runs only after step 2 of its guide: the token is chosen THERE, never made before
                want[addon["id"]] = addon
        with _lock:
            for pk in [p for p in _procs if p not in want]:
                _stop_unlocked(pk)
                row = conn.execute("SELECT vehicle_id, addon_id FROM vehicle_addons WHERE id = ?", (pk,)).fetchone()
                if row:
                    _event(row, "info", "Service stopped (switched off, approval taken back or package changed)", conn)
            for pk, addon in want.items():
                if pk in _installing:
                    continue
                info = _procs.get(pk)
                if info and info["proc"].poll() is None:
                    if now - info["started"] > 60:
                        info["fails"] = 0  # stable for a minute: the crash counter starts again
                    continue
                if info and now < info["next"]:
                    continue
                if info:  # crashed: pause longer each time
                    info["fails"] += 1
                    code = info["proc"].returncode
                    log.warning("service of plugin %s exited (%s)", addon["addon_id"], code)
                    wait = BACKOFF[min(info["fails"] - 1, len(BACKOFF) - 1)]
                    last = (
                        " | ".join(_tail.get(pk, [])[-4:])
                        if connectors.debug_enabled(conn, addon["vehicle_id"], addon["addon_id"])
                        else "turn debug on to see its last output"
                    )
                    _event(
                        addon,
                        "error",
                        f"Service stopped by itself (exit code {code}); start number {info['fails'] + 1} after a pause of {wait} s. {last}",
                        conn,
                    )
                if not (venv_dir(addon["addon_id"]) / "bin" / "python").is_file() or not _env_ready(addon):
                    install_async(pk)
                    continue
                try:
                    fails = info["fails"] if info else 0
                    _start(conn, addon)
                    _procs[pk]["fails"] = fails
                    _procs[pk]["next"] = now + BACKOFF[min(fails, len(BACKOFF) - 1)]
                except (OSError, FileNotFoundError, ValueError) as exc:
                    log.warning("could not start the service of plugin %s: %s", addon["addon_id"], exc)
                    _event(addon, "error", f"The service could not be started: {type(exc).__name__}: {str(exc)[:200]}", conn)
                    conn.execute("UPDATE vehicle_addons SET svc_error = 'svc.err_start' WHERE id = ?", (pk,))
            _rebuild_routes()


def _env_ready(addon: dict) -> bool:
    service = service_of(addon)
    marker = venv_dir(addon["addon_id"]) / f".reqs-{addons.service_fingerprint({'r': service['requirements']})[:16]}"
    return marker.exists()


def _stop_unlocked(pk: int) -> None:
    info = _procs.pop(pk, None)
    if info and info["proc"].poll() is None:
        with contextlib.suppress(OSError, ProcessLookupError):
            os.killpg(info["proc"].pid, 15)
        with contextlib.suppress(subprocess.TimeoutExpired):
            info["proc"].wait(5)
        if info["proc"].poll() is None:
            with contextlib.suppress(OSError, ProcessLookupError):
                os.killpg(info["proc"].pid, 9)


def forget(addon: dict) -> None:
    """The plugin is removed: stop the service, delete its data of this car and, when no other car uses the package, its code and environment."""
    stop(addon["id"])
    shutil.rmtree(run_dir(addon["addon_id"], addon["vehicle_id"]), ignore_errors=True)
    with db.tx() as conn:
        others = conn.execute("SELECT 1 FROM vehicle_addons WHERE addon_id = ? AND id != ?", (addon["addon_id"], addon["id"])).fetchone()
    if not others:
        shutil.rmtree(root() / addon["addon_id"], ignore_errors=True)
        folder = files_root() / addon["addon_id"]
        for p in [folder, *folder.rglob("*")]:  # the files are read-only: make them removable first
            with contextlib.suppress(OSError):
                os.chmod(p, 0o755 if p.is_dir() else 0o644)
        shutil.rmtree(folder, ignore_errors=True)
    _wake.set()


# ------------------------------------------------------------------ the supervisor thread


def _loop() -> None:
    harden()
    while not _stop.is_set():
        try:
            tick()
        except Exception:
            log.exception("plugin service supervision failed")
        _wake.wait(2.0)
        _wake.clear()


def start_supervisor() -> None:
    global _thread
    if _thread is None or not _thread.is_alive():
        _stop.clear()
        _thread = threading.Thread(target=_loop, daemon=True, name="plugin-services")
        _thread.start()


def stop_all() -> None:
    _stop.set()
    _wake.set()
    with _lock:
        for pk in list(_procs):
            _stop_unlocked(pk)
        _rebuild_routes()


def kick() -> None:
    _wake.set()
