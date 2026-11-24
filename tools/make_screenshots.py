#!/usr/bin/env python3
"""Make every picture of docs/screenshots/<lang>/ again, from the made-up demo cars, with a headless Chrome.

  python tools/make_screenshots.py [--only name,name] [--langs en,de] [--out docs/screenshots]

Needs Google Chrome (or set CHROME=/path/to/chrome). Runs the app itself on a free port with an empty temporary data folder, fills it with the two
demo cars of tools/demo_data.py and takes the pictures; nothing of a real installation is read. Desktop pictures are 1200 px wide, phone pictures
500 px wide at double density (Chrome never makes a window narrower than 500 px; the pages use their phone layout up to 520 px).
"""

from __future__ import annotations

import argparse
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "carassistant" / "app"))
sys.path.insert(0, str(ROOT / "tools"))

CHROME = os.environ.get("CHROME") or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DIESEL, EV = "demo-diesel", "demo-electric"
COMPACT = "demo-compact"  # a plain car with no data from the car: its dashboard shows the odometer plate you can turn over and type on
SCENES = ("odometer-photo", "fuel-scan", "connections-map")  # pictures that need a tap and a photo first (tools/cdp.py)

# name, path, width, height (desktop pictures; the height cuts the page where it is still worth looking at)
DESKTOP = (
    ("dashboard", f"/v/{DIESEL}", 1200, 1250),
    ("dashboard-map", f"/v/{DIESEL}", 1200, 2100),
    ("dashboard-ev", f"/v/{EV}", 1200, 1250),
    ("fuel", f"/v/{DIESEL}/e/fuel", 1200, 1300),
    ("trips", f"/v/{DIESEL}/e/trips?ap=all", 1200, 2300),
    (
        "trip-map",
        f"/v/{DIESEL}/e/trips?ap=all&open=1",
        1200,
        3600,
        (1590, 2740),
    ),  # the first trip of the demo car is open: its route on the map, coloured by speed
    ("service", f"/v/{DIESEL}/e/service", 1200, 1300),
    ("tires", f"/v/{DIESEL}/e/tires", 1200, 1300),
    ("mods", f"/v/{DIESEL}/e/mods", 1200, 1100),
    (
        "notice",
        f"/v/{DIESEL}/docs?m=err.required",
        1200,
        800,
    ),  # the one notice tile under the page header: an error message (red) above the page introduction
    ("tasks", f"/v/{DIESEL}/e/tasks", 1200, 1300),
    ("appointments", f"/v/{DIESEL}/e/appointments", 1200, 1000),
    ("parts", f"/v/{DIESEL}/e/parts", 1200, 1000),
    ("report", f"/v/{DIESEL}/report?g=month&n=12", 1200, 2000),
    ("documents", f"/v/{DIESEL}/docs", 1200, 900),
    ("security", f"/v/{DIESEL}/security", 1200, 1200),
    ("passport", f"/v/{DIESEL}/edit", 1200, 1700),
    ("more", f"/v/{DIESEL}/more", 1200, 900),
    ("plugins", f"/v/{DIESEL}/plugins", 1200, 900),
    ("about", "/about", 1200, 1200),
    ("settings-user", "/settings/user", 1200, 1700),
    ("settings-car", f"/settings/car?car={DIESEL}", 1200, 2300),
    ("settings-system", "/settings/system", 1200, 3300),
)
MOBILE = (
    ("mobile-dashboard", f"/v/{DIESEL}", 500, 844),
    ("mobile-fuel", f"/v/{DIESEL}/e/fuel", 500, 844),
    ("mobile-trips", f"/v/{DIESEL}/e/trips?ap=all", 500, 1500),
    ("mobile-trip-map", f"/v/{DIESEL}/e/trips?ap=all&open=1", 500, 3000, (1700, 2700)),
    ("mobile-tires", f"/v/{DIESEL}/e/tires", 500, 1100),
    ("mobile-report", f"/v/{DIESEL}/report?g=month&n=12", 500, 1500),
    ("mobile-more", f"/v/{DIESEL}/more", 500, 844),
    ("mobile-settings-car", f"/settings/car?car={DIESEL}", 500, 1500),
)
# the same dashboard in every design: (picture, theme of the car, its colour)
DESIGNS = (
    ("design-classic", "", None),
    ("design-light", "custom-light", "#2f8cff"),
    ("design-dark", "custom-dark", "#3ddc84"),
    ("design-auto", "custom-auto", "#a855f7"),
)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _demo_plugins(conn, vid: int) -> None:
    """Two installed plugins, so that the checks and the pictures measure the TILE of a plugin: one with a service and three free buttons (the widest
    bar there is: Uninstall, Logs, Settings, three own buttons and the main button), one plain plugin that still has to be set up."""
    import json

    from carassistant import addons

    source = conn.execute("SELECT id FROM sources ORDER BY id LIMIT 1").fetchone()[0]
    gateway = {
        "id": "demo-gateway",
        "kind": "plugin",
        "name": "Demo gateway",
        "version": "1.0",
        "author": "Example",
        "icon": "plug",
        "description": "A made-up plugin with a service, three buttons of its own and a log - it only exists to show the tile of a plugin.",
        "settings": [
            {"key": "host", "label": "Address", "type": "text"},
            {
                "key": "stations",
                "label": "Stations",
                "type": "list",
                "name_label": "Name",
                "value_label": "Stream address",
                "columns": [{"key": "second", "label": "Second line"}, {"key": "logo", "label": "Logo address"}],
                "default": [
                    {"name": "Radio A", "value": "https://a.example/stream", "second": "News", "logo": "https://a.example/logo.png"}
                ],
            },
        ],
        "service": {
            "entry": "service/main.py",
            "python": ">=3.9",
            "requirements": [],
            "routes": [{"prefix": "/demo/", "public": False}],
        },
        "pages": [{"id": "docs", "kind": "frame", "title": "Documentation", "icon": "file-document-outline", "route": "/demo/docs/"}],
        "buttons": [
            {"id": "docs", "label": "Documentation", "icon": "file-document-outline", "page": "docs"},
            {"id": "wake", "label": "Wake the car", "icon": "power", "action": "/demo/wake"},
            {"id": "sync", "label": "Sync now", "icon": "refresh", "action": "/demo/sync", "confirm": "Fetch everything again?"},
        ],
        "downloads": [{"label": "Car log", "path": "/demo/car.log"}, {"label": "Signal data", "path": "/demo/signals.zip"}],
    }
    addons.add(conn, vid, addons.parse_package(json.dumps(gateway).encode()), source, "0" * 64)
    cloud = {
        "id": "demo-cloud",
        "kind": "plugin",
        "name": "Demo cloud",
        "version": "1.0",
        "author": "Example",
        "icon": "cloud",
        "description": "A made-up plugin that logs in to an account; it still has to be set up.",
        "settings": [{"key": "user", "label": "User name", "type": "text"}, {"key": "password", "label": "Password", "type": "password"}],
        "setup": {
            "title": "Connect the account",
            "flow": [
                {
                    "id": "intro",
                    "type": "text",
                    "title": "Welcome",
                    "text": "Log in with the account you use in the car app.\n\n- Your details stay on this server.\n- Nothing is sent anywhere else.",
                },
                {"id": "login", "type": "form", "title": "Your account", "settings": ["user", "password"]},
                {"id": "needs", "type": "requirements", "requires": ["external_https"], "filled": ["user"]},
                {"id": "token", "type": "token", "text": "The token lets the plugin talk to Car Assistant."},
            ],
        },
    }
    addons.add(conn, vid, addons.parse_package(json.dumps(cloud).encode()))


def seed(data: Path, lang: str) -> None:
    """The demo cars, a user and an MCP key (so the settings pages show their full cards), in the language of the pictures."""
    os.environ["CARASSISTANT_DATA"] = str(data)
    os.environ["CARASSISTANT_DEV"] = "1"
    import demo_data

    from carassistant import accounts, config, db, mcp, slugs

    config.forget_external()  # a second language in the same process must not inherit the first one's address (the password rules are strict with one)
    config.forget_settings()
    db.migrate()
    with db.tx() as conn:
        db.set_setting(conn, "setup.language", "1")
        db.set_setting(conn, "language", lang)
        for electric, name in ((False, "Demo Diesel"), (True, "Demo Electric")):
            vid = demo_data.create(conn, electric=electric)
            conn.execute("UPDATE vehicles SET name = ?, slug = ? WHERE id = ?", (name, slugs.unique(conn, name, vid), vid))
            for title, category in (
                ("Quick guide (example)", "manual"),
                ("Service plan (example)", "inspection"),
                ("Insurance policy (example)", "insurance"),
            ):
                doc = conn.execute(
                    "INSERT INTO documents(vehicle_id, category, title, filename, mime, size) VALUES(?,?,?,?,?,?)",
                    (vid, category, title, "example.txt", "text/plain", 120),
                ).lastrowid
                folder = config.files_dir() / str(vid)  # a real (tiny) file: the page offers *Open* only for a file that is there
                folder.mkdir(parents=True, exist_ok=True)
                (folder / f"{doc}.txt").write_text("Example document.\n" * 6, encoding="utf-8")
        vid = conn.execute(
            "INSERT INTO vehicles (name, make, model, fuel_type, plate) VALUES ('Demo Compact', 'Example', 'Compact', 'diesel', 'EF-GH 456')"
        ).lastrowid
        conn.execute("UPDATE vehicles SET slug = ? WHERE id = ?", (slugs.unique(conn, "Demo Compact", vid), vid))
        today = date.today()
        for days, km in ((70, 84_200), (35, 84_900), (3, 85_640)):  # the last reading is a little below what the photo of the cluster shows
            conn.execute(
                "INSERT INTO odometer(vehicle_id, date, odometer_km, source) VALUES (?, ?, ?, 'manual')",
                (vid, (today - timedelta(days=days)).isoformat(), km),
            )
        for days, km, litres in ((36, 84_250, 41.2), (12, 85_150, 39.8)):
            conn.execute(
                "INSERT INTO fuel(vehicle_id, date, odometer_km, amount, price_per_unit, price_total, full_tank, station) VALUES (?, ?, ?, ?, 1.659, ?, 1, 'Example Fuel')",
                (vid, (today - timedelta(days=days)).isoformat(), km, litres, round(litres * 1.659, 2)),
            )
        accounts.create_user(conn, "demo", "correct horse battery staple", admin=True)
        _demo_plugins(conn, conn.execute("SELECT id FROM vehicles WHERE name = 'Demo Diesel'").fetchone()[0])
        db.set_setting(conn, "ext.url", "https://car.example.com")
        db.set_setting(conn, "map.tiles", "1")  # the maps of the trips and the position show real map tiles in the pictures
    config.forget_external()
    config.forget_settings()
    with db.tx() as conn:
        mcp.set_level(conn, "read")
        mcp.renew_key(conn)


def wait_for(url: str, seconds: float = 40) -> None:
    end = time.time() + seconds
    while time.time() < end:
        try:
            urllib.request.urlopen(url, timeout=2).read()
            return
        except Exception:
            time.sleep(0.5)
    raise SystemExit(f"the app did not start: {url}")


def shot(base: str, path: str, out: Path, width: int, height: int, scale: int, crop: tuple[int, int] | None = None) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        CHROME,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--no-first-run",
        f"--force-device-scale-factor={scale}",
        f"--window-size={width},{height}",
        "--virtual-time-budget=6000",
        f"--screenshot={out}",
        base + path,
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=90)
    if (
        crop
    ):  # a tall picture of which only a band is worth showing (the open trip with its map); needs Pillow, else the whole picture stays
        try:
            from PIL import Image

            with Image.open(out) as im:
                im.crop((0, crop[0] * scale, im.width, min(im.height, crop[1] * scale))).save(out)
        except ImportError:
            pass


def compose(photo: bytes, screen: Path, out: Path, photo_height: int | None = 760) -> None:
    """The photo on the left, an arrow, the picture of the app on the right: what the person holds up and what the app makes of it."""
    import io

    from PIL import Image, ImageDraw

    left = Image.open(io.BytesIO(photo)).convert("RGB")
    right = Image.open(screen).convert("RGB")
    photo_height = photo_height or right.height  # None: the photo is as tall as the picture of the app
    left = left.resize((round(left.width * photo_height / left.height), photo_height), Image.LANCZOS)
    if right.height > photo_height:  # the picture of the app is never taller than the photo
        right = right.crop((0, 0, right.width, photo_height))
    gap = 110
    height = max(left.height, right.height) + 60
    sheet = Image.new("RGB", (left.width + gap + right.width + 80, height), (13, 16, 22))
    sheet.paste(left, (30, (height - left.height) // 2))
    sheet.paste(right, (30 + left.width + gap, (height - right.height) // 2))
    d = ImageDraw.Draw(sheet)
    x0, x1, y = 30 + left.width + 24, 30 + left.width + gap - 24, height // 2
    d.line((x0, y, x1, y), fill=(226, 0, 26), width=8)
    d.polygon([(x1 + 12, y), (x1 - 14, y - 22), (x1 - 14, y + 22)], fill=(226, 0, 26))
    if sheet.width > 1800:  # the pictures of the documentation are not wider than they are shown
        sheet = sheet.resize((1800, round(sheet.height * 1800 / sheet.width)), Image.LANCZOS)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, optimize=True)


def connect_demo_plugins() -> None:
    """Two made-up plugins that have talked to the Plugin API (in this process: the data folder of ``seed``), so that the connection map has lines."""
    import json

    from carassistant import db, linkmap

    with db.tx() as conn:
        vid = conn.execute("SELECT id FROM vehicles WHERE slug = ?", (DIESEL,)).fetchone()[0]
        for addon_id, name, icon in (("demo-connector", "Demo connector", "plug"), ("cloud-account", "Cloud account", "cloud")):
            conn.execute(
                "INSERT INTO vehicle_addons(vehicle_id, kind, addon_id, manifest, status, settings, created_at, active) VALUES(?, 'plugin', ?, ?, 'configured', '{}', '2026-01-01', 1)",
                (vid, addon_id, json.dumps({"id": addon_id, "kind": "plugin", "name": name, "version": "1", "icon": icon})),
            )
        pre = ["", "api", "v1", "vehicles", str(vid)]

        def call(addon: str, method: str, what: str, body=None) -> None:
            linkmap.record(conn, vid, addon, method, pre + [what], body)

        for km, ign, fuel in ((86020, "on", 42), (86031, "off", 41), (86044, "off", 40)):
            linkmap._seen.clear()
            call(
                "demo-connector",
                "POST",
                "data",
                {"odometer_km": km, "ignition": ign, "fuel_level_pct": fuel, "range_km": 520 - (42 - fuel) * 12},
            )
        linkmap._seen.clear()
        call(
            "demo-connector",
            "POST",
            "data",
            {
                "position": {"lat": 52.52, "lon": 13.405},
                "speed_kmh": 0,
                "doors": {"fl": "closed", "fr": "closed"},
                "tyre_pressure_bar": {"fl": 2.4, "fr": 2.4, "rl": 2.5, "rr": 2.5},
            },
        )
        call("demo-connector", "GET", "control")
        call("demo-connector", "POST", "logs", {"lines": ["connected", "reading"]})
        call("cloud-account", "POST", "data", {"battery_12v_v": 12.6, "outside_temp_c": 7.5, "service_due_km": 4200})
        call("cloud-account", "GET", "data")
        call("cloud-account", "POST", "track", {"points": [{"lat": 52.5, "lon": 13.4}]})
        call("cloud-account", "POST", "refuel", {"amount": 41.2, "price_per_unit": 1.659})
        conn.execute(
            "UPDATE signal_state SET last_ts = ? WHERE addon_id = 'cloud-account' AND name = 'service_due_km'",
            ((date.today() - timedelta(days=3)).isoformat() + "T10:00:00+00:00",),
        )


def scenes(base: str, out_root: Path, lang: str, only: set[str]) -> None:
    """The pictures that show a tap and a photo: the odometer plate turned over with a photo of the cluster read, the fill-up form with a receipt read."""
    from cdp import Browser, upload_script

    import demo_photos

    note = "(function(){var n=document.querySelector('%s');return !!n && !n.hidden && !n.classList.contains('busy');})()"
    with Browser() as b, tempfile.TemporaryDirectory() as tmp:
        if not only or "odometer-photo" in only:
            b.open(f"{base}/v/{COMPACT}", 520, 900, 2)
            b.run("document.querySelector('.odo-front').click()")  # a tap on the odometer turns it over to the entry
            time.sleep(1.2)
            photo = demo_photos.cluster_photo(odometer=86_020, trip=24.5)
            b.run(upload_script(".odo-flip [data-scan-file]", photo, "cluster.jpg", "image/jpeg"))
            b.wait_for(note % ".odo-flip [data-scan-note]")
            time.sleep(1.0)
            x, y, w, h = b.run(
                "(function(){var f=document.querySelector('.odo-flip').getBoundingClientRect(),n=document.querySelector('.odo-flip [data-scan-note]').getBoundingClientRect();"
                "return [f.left+scrollX,f.top+scrollY,f.width,Math.max(f.bottom,n.bottom)-f.top];})()"
            )
            screen = Path(tmp) / "odo.png"
            b.shot(screen, clip=(max(0, x - 18), max(0, y - 6), min(520, w + 36), h + 10), scale=2)
            compose(photo, screen, out_root / lang / "odometer-photo.png")
            print(lang, "odometer-photo", flush=True)
        if not only or "connections-map" in only:
            connect_demo_plugins()
            b.open(f"{base}/v/{DIESEL}/plugins/connections", 1800, 1500, 1, settle=1.0)  # a wide window: the whole map fits and reads well
            b.wait_for("document.getElementById('lmz').classList.contains('ready')")
            time.sleep(0.4)
            b.run(
                "document.querySelector('.lmz-ch[data-id=\"odometer_km\"]').dispatchEvent(new MouseEvent('click',{bubbles:true}))"
            )  # a click opens everything about it below
            b.wait_for("document.querySelectorAll('.lmz-sig').length > 0")
            time.sleep(0.8)
            x, y, w, h = b.run(
                "(function(){var r=document.getElementById('lmz').getBoundingClientRect();return [r.left+scrollX,r.top+scrollY,r.width,r.height];})()"
            )
            screen = Path(tmp) / "map.png"
            b.shot(screen, clip=(x - 8, y - 8, w + 16, h + 16), scale=1)
            out = out_root / lang / "connections-map.png"
            out.parent.mkdir(parents=True, exist_ok=True)
            screen.replace(out)
            print(lang, "connections-map", flush=True)
        if not only or "fuel-scan" in only:
            b.open(f"{base}/v/{COMPACT}/e/fuel#fuel-add", 520, 1000, 2, settle=3.5)  # the link opens the form of a new fill-up
            photo = demo_photos.receipt_photo(lang=lang, odometer=86_020)
            b.run(upload_script("#fuel-add [data-scan-file]", photo, "receipt.jpg", "image/jpeg"))
            b.wait_for(note % "#fuel-add [data-scan-note]")
            time.sleep(0.8)
            x, y, w, h = b.run(
                "(function(){var r=document.getElementById('fuel-add').getBoundingClientRect();return [r.left+scrollX,r.top+scrollY,r.width,r.height];})()"
            )
            screen = Path(tmp) / "fuel.png"
            b.shot(screen, clip=(max(0, x - 10), max(0, y - 10), min(520, w + 20), h + 20), scale=2)
            compose(photo, screen, out_root / lang / "fuel-scan.png", photo_height=None)
            print(lang, "fuel-scan", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--langs", default="en,de")
    ap.add_argument("--out", default=str(ROOT / "docs" / "screenshots"))
    args = ap.parse_args()
    only = {n for n in args.only.split(",") if n}
    out_root = Path(args.out)
    for lang in args.langs.split(","):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            seed(data, lang)
            port = free_port()
            env = {**os.environ, "CARASSISTANT_DATA": str(data), "CARASSISTANT_DEV": "1", "CARASSISTANT_PORT": str(port)}
            env["PYTHONPATH"] = str(ROOT / "carassistant" / "app")
            server = subprocess.Popen([sys.executable, "-m", "carassistant"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                base = f"http://127.0.0.1:{port}"
                wait_for(base + "/healthz")
                for name, path, w, h, *crop in DESKTOP:
                    if not only or name in only:
                        shot(base, path, out_root / lang / f"{name}.png", w, h, 1, *crop)
                        print(lang, name, flush=True)
                for name, path, w, h, *crop in MOBILE:
                    if not only or name in only:
                        shot(base, path, out_root / lang / f"{name}.png", w, h, 2, *crop)
                        print(lang, name, flush=True)
                if not only or only & set(SCENES):
                    scenes(base, out_root, lang, only)
                db = sqlite3.connect(data / "carassistant.db")
                for name, theme, accent in DESIGNS:
                    if only and name not in only:
                        continue
                    db.execute("UPDATE vehicles SET theme = ?, accent = ? WHERE slug = ?", (theme or None, accent, DIESEL))
                    db.commit()
                    shot(base, f"/v/{DIESEL}", out_root / lang / f"{name}.png", 1200, 1250, 1)
                    print(lang, name, flush=True)
                db.execute("UPDATE vehicles SET theme = NULL, accent = NULL WHERE slug = ?", (DIESEL,))
                db.commit()
                db.close()
            finally:
                server.terminate()
                server.wait(timeout=10)


if __name__ == "__main__":
    main()
