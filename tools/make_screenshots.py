#!/usr/bin/env python3
"""Make every picture of docs/screenshots/<lang>/ again, from the made-up demo cars, with a headless Chrome.

  python tools/make_screenshots.py [--only name,name] [--langs en,de] [--out docs/screenshots]

Needs Google Chrome (or set CHROME=/path/to/chrome). Runs the app itself on a free port with an empty temporary data folder, fills it with the two
demo cars of tools/demo_data.py and takes the pictures; nothing of a real installation is read. Desktop pictures are 1200 px wide, phone pictures
390 px wide at double density.
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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "carassistant" / "app"))
sys.path.insert(0, str(ROOT / "tools"))

CHROME = os.environ.get("CHROME") or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DIESEL, EV = "demo-diesel", "demo-electric"

# name, path, width, height (desktop pictures; the height cuts the page where it is still worth looking at)
DESKTOP = (
    ("dashboard", f"/v/{DIESEL}", 1200, 1250),
    ("dashboard-ev", f"/v/{EV}", 1200, 1250),
    ("fuel", f"/v/{DIESEL}/e/fuel", 1200, 1300),
    ("trips", f"/v/{DIESEL}/e/trips?ap=all", 1200, 2300),
    ("service", f"/v/{DIESEL}/e/service", 1200, 1300),
    ("tires", f"/v/{DIESEL}/e/tires", 1200, 1300),
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
    ("mobile-dashboard", f"/v/{DIESEL}", 390, 844),
    ("mobile-fuel", f"/v/{DIESEL}/e/fuel", 390, 844),
    ("mobile-trips", f"/v/{DIESEL}/e/trips?ap=all", 390, 1500),
    ("mobile-report", f"/v/{DIESEL}/report?g=month&n=12", 390, 1500),
    ("mobile-more", f"/v/{DIESEL}/more", 390, 844),
    ("mobile-settings-car", f"/settings/car?car={DIESEL}", 390, 1500),
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


def seed(data: Path, lang: str) -> None:
    """The demo cars, a user and an MCP key (so the settings pages show their full cards), in the language of the pictures."""
    os.environ["CARASSISTANT_DATA"] = str(data)
    os.environ["CARASSISTANT_DEV"] = "1"
    import demo_data

    from carassistant import accounts, config, db, mcp, slugs

    db.migrate()
    with db.tx() as conn:
        db.set_setting(conn, "setup.language", "1")
        db.set_setting(conn, "language", lang)
        for electric, name in ((False, "Demo Diesel"), (True, "Demo Electric")):
            vid = demo_data.create(conn, electric=electric)
            conn.execute("UPDATE vehicles SET name = ?, slug = ? WHERE id = ?", (name, slugs.unique(conn, name, vid), vid))
            for title, category in (("Quick guide (example)", "manual"), ("Service plan (example)", "inspection"), ("Insurance policy (example)", "insurance")):
                conn.execute(
                    "INSERT INTO documents(vehicle_id, category, title, filename, mime, size) VALUES(?,?,?,?,?,?)",
                    (vid, category, title, "example.txt", "text/plain", 120),
                )
        accounts.create_user(conn, "demo", "correct horse battery staple", admin=True)
        db.set_setting(conn, "ext.url", "https://car.example.com")
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


def shot(base: str, path: str, out: Path, width: int, height: int, scale: int) -> None:
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
                for name, path, w, h in DESKTOP:
                    if not only or name in only:
                        shot(base, path, out_root / lang / f"{name}.png", w, h, 1)
                        print(lang, name, flush=True)
                for name, path, w, h in MOBILE:
                    if not only or name in only:
                        shot(base, path, out_root / lang / f"{name}.png", w, h, 2)
                        print(lang, name, flush=True)
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
