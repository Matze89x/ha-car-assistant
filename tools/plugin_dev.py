#!/usr/bin/env python3
"""Runs a REAL Car Assistant on your computer with your plugin already installed, approved and running - one command, nothing to set up.

    python tools/plugin_dev.py <folder of the plugin> [--set key=value ...] [--port 8123] [--once | --seconds N] [--keep] [--no-watch]

What it does: a temporary data folder, a car "Dev car", your plugin installed from the folder (packed like a source would pack it, the service approved for
you - this is YOUR computer and YOUR code), the app started on a free port - then it shows the log lines of the plugin as they come, every call it makes to the Plugin API and what the car shows.
Open the address it prints: the tile of the plugin, its settings, the steps of its set-up and its pages are the real ones. Change a file of the plugin and it
is packed and started again. Ctrl-C ends it (the temporary folder is deleted; ``--keep`` keeps it).

``--set key=value`` fills a setting and finishes the set-up for you; without it the plugin waits for you to run its set-up in the browser, like a person would.
``--once`` runs until the plugin has sent something to the car and ends: exit code 0 then, 1 when nothing came within ``--seconds`` (60 by default) -
the quickest check that your service starts, logs in and delivers. ``--seconds N`` alone runs N seconds and ends the same way (0 = it sent something).

Needs the requirements of the app (``pip install -r carassistant/requirements.txt``): it starts the app of this repository."""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "carassistant" / "app"
SKIP = {"__pycache__", "tests", ".git", ".venv", "node_modules"}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def snapshot(folder: Path) -> dict:
    """What is in the folder, for noticing a change."""
    return {p: p.stat().st_mtime_ns for p in sorted(folder.rglob("*")) if p.is_file() and not (SKIP & set(p.relative_to(folder).parts))}


def pack(folder: Path, manifest: dict) -> tuple[bytes, str]:
    """The folder as a package.zip: the readable files, and the declared ``files`` (checked binaries) - like tools/build_plugin_package.py."""
    from carassistant import pluginsvc

    wanted = {f["path"] for f in manifest.get("files") or []}
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for path in snapshot(folder):
            rel = path.relative_to(folder).as_posix()
            if path.name != "package.zip" and (path.suffix.lower() in pluginsvc.READABLE or rel in wanted):
                z.write(path, rel)
    raw = out.getvalue()
    return raw, hashlib.sha256(raw).hexdigest()


def load(folder: Path) -> dict:
    from carassistant import addons

    return addons.parse_package((folder / "plugin.json").read_bytes())


def install(folder: Path, values: dict) -> tuple[int, int, str, str]:
    """The car and the plugin in the data folder of this run. Returns (vehicle id, add-on number, slug, token): the token only for a plugin without a
    service - it calls the Plugin API itself; the service of a plugin gets its token from the app."""
    from carassistant import addons, connectors, db, pluginsvc, slugs, sources

    manifest = load(folder)
    raw, sha = pack(folder, manifest)
    with db.tx() as conn:
        conn.execute("DELETE FROM vehicle_addons")
        vid = conn.execute("SELECT id FROM vehicles WHERE name = 'Dev car'").fetchone()
        vid = vid["id"] if vid else conn.execute("INSERT INTO vehicles(name, fuel_type) VALUES('Dev car', 'petrol')").lastrowid
        conn.execute("UPDATE vehicles SET slug = ? WHERE id = ?", (slugs.unique(conn, "Dev car", vid), vid))
        db.set_setting(conn, "setup.language", "1")
        found = conn.execute("SELECT id FROM sources WHERE url = 'https://example.invalid/dev'").fetchone()
        sid = (
            found["id"] if found else sources.add(conn, "Your folder", "https://example.invalid/dev", "")
        )  # nothing is ever fetched from it
        service = manifest.get("service") or {}
        if addons.needs_package(manifest):
            pluginsvc.store_package(manifest["id"], raw, sha, service.get("entry"), manifest.get("files"), manifest.get("bundles"))
        pk = addons.add(conn, vid, manifest, sid, sha if addons.needs_package(manifest) else None)
        if values:
            addons.set_up(conn, vid, addons.get(conn, vid, pk), values)
        if addons.needs_package(manifest):
            pluginsvc.approve(conn, addons.get(conn, vid, pk))
        addons.set_active(conn, addons.get(conn, vid, pk), True)
        connectors.set_plugin_debug(
            conn, vid, manifest["id"], True, 1
        )  # the output of the service is kept for the log page (and shown here)
        slug = conn.execute("SELECT slug FROM vehicles WHERE id = ?", (vid,)).fetchone()["slug"]
        token = ""
        if manifest["kind"] == "plugin" and not manifest.get("service") and addons.needs_token(manifest):
            token = addons.new_token(conn, vid, addons.get(conn, vid, pk))
    return vid, pk, slug, token


def start_app(port: int, data: Path) -> subprocess.Popen:
    env = {**os.environ, "PYTHONPATH": str(APP), "CARASSISTANT_DATA": str(data), "CARASSISTANT_DEV": "1", "CARASSISTANT_PORT": str(port)}
    proc = subprocess.Popen([sys.executable, "-m", "carassistant"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    end = time.time() + 60
    while time.time() < end:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=2):
                return proc
        except OSError:
            time.sleep(0.4)
    proc.terminate()
    raise SystemExit("the app did not start")


def stop_app(proc: subprocess.Popen) -> None:
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()


class Follower:
    """Prints the log lines of the plugin, every call it makes to the Plugin API and the values the car shows, as they arrive."""

    def __init__(self, vid: int):
        self.vid, self.last_log, self.last_call, self.delivered, self.seen = vid, 0, 0, 0, {}

    def step(self) -> int:
        """Print what is new; returns how many calls of the plugin the app has accepted so far."""
        from carassistant import db

        with db.tx() as conn:
            for r in conn.execute(
                "SELECT id, ts, level, message FROM vehicle_logs WHERE vehicle_id = ? AND id > ? ORDER BY id", (self.vid, self.last_log)
            ):
                self.last_log = r["id"]
                print(f"  log  {r['ts'][11:19]} {r['level']:5s} {r['message']}")
            for r in conn.execute(
                "SELECT id, ts, method, path, status, detail FROM vehicle_traffic WHERE vehicle_id = ? AND kind = 'api' AND id > ? ORDER BY id",
                (self.vid, self.last_call),
            ):
                self.last_call = r["id"]
                self.delivered += r["status"] < 400
                path = r["path"].split("/vehicles/", 1)[-1].split("/", 1)[-1]  # "/data", "/track", ...
                print(f"  api  {r['ts'][11:19]} {r['method']} /{path} -> {r['status']}  {r['detail'][:80]}")
            live = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM live WHERE vehicle_id = ?", (self.vid,))}
        for key, value in live.items():
            if self.seen.get(key) != value:
                self.seen[key] = value
                print(f"  car  {key} = {value}")
        return self.delivered


def show_where(manifest: dict, port: int, slug: str, vid: int, token: str) -> None:
    """The addresses of the app that runs, and - for a plugin without a service - how a script or a device talks to it."""
    base = f"http://127.0.0.1:{port}"
    if manifest["kind"] == "integration":
        print(f"  the integration  {base}/v/{slug}/integrations")
        if manifest.get("pages"):
            print(f"  its page         {base}/v/{slug}/m/{manifest['id']}")
    else:
        print(f"  the plugin       {base}/v/{slug}/plugins")
    print(f"  the car          {base}/v/{slug}")
    if token:
        print(f"  Plugin API       {base}/api/v1/vehicles/{vid}/...   token: {token}")
        print(f"                   try: curl -H 'Authorization: Bearer {token}' -H 'Content-Type: application/json' \\")
        print(f"                             -d '{{\"odometer_km\": 1000}}' {base}/api/v1/vehicles/{vid}/data")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Run a real Car Assistant with your plugin (see the top of this file).")
    parser.add_argument("folder")
    parser.add_argument("--set", action="append", default=[], metavar="key=value")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--seconds", type=float, default=0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--no-watch", dest="watch", action="store_false")
    args = parser.parse_args(argv)
    if args.once and not args.seconds:
        args.seconds = 60
    folder = Path(args.folder).resolve()
    if not (folder / "plugin.json").is_file():
        print(f"{folder}/plugin.json is missing")
        return 2
    values = dict(item.split("=", 1) for item in args.set if "=" in item)

    tmp = tempfile.TemporaryDirectory(prefix="ca-plugin-dev-")
    data = Path(tmp.name)
    os.environ.update({"CARASSISTANT_DATA": str(data), "CARASSISTANT_DEV": "1"})
    sys.path.insert(0, str(APP))
    from carassistant import db

    db.migrate()
    try:
        manifest = load(folder)
        if args.once and manifest["kind"] == "integration":
            print("An integration sends nothing by itself: leave out --once and open its page.")
            return 2
        vid, _pk, slug, token = install(folder, values)
    except Exception as exc:  # the package is refused: say why, the way the app would
        print(f"the package is not accepted: {exc}")
        return 1
    port = args.port or free_port()
    proc = start_app(port, data)
    print(f"Car Assistant {'with your plugin ' if values else ''}is running - open it:")
    show_where(manifest, port, slug, vid, token)
    print(
        "\nLog lines of the plugin, its calls to the Plugin API and what the car shows follow. Change a file and the plugin starts again. Ctrl-C ends this.\n"
    )
    follower = Follower(vid)
    seen, started = snapshot(folder), time.time()
    got = 0
    try:
        while True:
            time.sleep(1)
            got = max(got, follower.step())
            if args.once and got:
                break
            if args.seconds and time.time() - started >= args.seconds:
                break
            if args.watch and snapshot(folder) != seen:
                seen = snapshot(folder)
                print("\n-- a file changed: packing and starting again --")
                stop_app(proc)
                try:
                    manifest = load(folder)
                    vid, _pk, slug, new_token = install(folder, values)
                    if new_token:
                        print(f"  (a new token: {new_token})")
                except Exception as exc:
                    print(f"the package is not accepted: {exc}")
                proc = start_app(port, data)
    except KeyboardInterrupt:
        print()
    finally:
        stop_app(proc)
        if args.keep:
            print(f"kept: {data}")
            tmp._finalizer.detach()
        else:
            tmp.cleanup()
    if args.seconds and manifest["kind"] == "integration":
        return 0  # nothing to wait for: it was only shown
    if args.seconds:
        print(f"\n{got} call(s) of the plugin were accepted." if got else f"\nNothing arrived from the plugin in {args.seconds:g} seconds.")
        return 0 if got else 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
