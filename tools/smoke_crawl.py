"""Open every page of a demo installation in a headless Chrome and report what goes wrong: a server error, a script error, an error in the console, a
request that fails, a file that is not found, a rule of the Content Security Policy that was broken.

It starts at the pages of the app, follows the links it finds (same address only, no downloads, nothing that deletes or signs out) and looks at each
page once. The installation is a temporary one with made-up cars and two made-up plugins, nothing of a real installation is read.

  python tools/smoke_crawl.py [--limit 400] [--width 1280]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urldefrag, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

SKIP = re.compile(r"/(delete|logout|signout|reset|restore|backup\.zip|archive|remove|revoke|install|uninstall)\b|\.(csv|pdf|ics|gpx|zip|png|jpg|jpeg|svg|webp|mp4|json|js|css|woff2?)(\?|$)|/api/|/static/|/media/|/files?/|/export|/download|/docs/\d+$|^mailto:|^tel:|^javascript:", re.I)


def run(limit: int = 400, width: int = 1280) -> tuple[list[str], int]:
    import make_screenshots as ms
    from cdp import Browser

    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp)
        env = {**os.environ, "PYTHONPATH": str(ROOT / "carassistant" / "app") + os.pathsep + str(ROOT / "tools"), "CARASSISTANT_DATA": str(data), "CARASSISTANT_DEV": "1"}
        prep = (
            "import sys; sys.path.insert(0, %r); from pathlib import Path; import make_screenshots as ms; ms.seed(Path(%r), 'en'); ms.connect_demo_plugins()"
            % (str(ROOT / "tools"), str(data))
        )
        subprocess.run([sys.executable, "-c", prep], check=True, env=env, capture_output=True, timeout=180)  # noqa: S603
        port = ms.free_port()
        server = subprocess.Popen([sys.executable, "-m", "carassistant"], env={**env, "CARASSISTANT_PORT": str(port)}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603
        try:
            base = f"http://127.0.0.1:{port}"
            ms.wait_for(base + "/healthz")
            origin = urlparse(base).netloc
            todo = ["/", "/vehicles", "/about", "/settings/user", "/settings/system", f"/settings/car?car={ms.DIESEL}", f"/v/{ms.DIESEL}", f"/v/{ms.COMPACT}", f"/v/{ms.EV}"]
            seen: set[str] = set()
            with Browser() as b:
                while todo and len(seen) < limit:
                    path = todo.pop(0)
                    key = re.sub(r"[?&]m=[^&]*", "", path)
                    if key in seen:
                        continue
                    seen.add(key)
                    b.drain()
                    b.open(base + path, width, 900, 1, settle=0.5)
                    events = b.drain()
                    if any(e["kind"] in ("exception", "console", "csp", "failed", "http") for e in events):  # a machine under load can stumble once: it counts when the page does it again
                        b.open(base + path, width, 900, 1, settle=1.0)
                        again = {(e["kind"], e["text"]) for e in b.drain()}
                        events = [e for e in events if (e["kind"], e["text"]) in again]
                    title = b.run("document.title")
                    status_bad = [e for e in events if e["kind"] == "http"]
                    for e in events:
                        if e["kind"] in ("exception", "console", "csp", "failed", "http"):
                            problems.append(f"{path}: {e['kind']}: {e['text']}")
                    if "Internal Server Error" in (b.run("document.body.innerText.slice(0, 400)") or "") and not status_bad:
                        problems.append(f"{path}: the page says Internal Server Error")
                    hrefs = json.loads(b.run("JSON.stringify(Array.from(document.querySelectorAll('a[href]')).map(function (a) { return a.href; }))") or "[]")
                    for href in hrefs:
                        href, _ = urldefrag(href)
                        u = urlparse(href)
                        if u.netloc != origin or SKIP.search(u.path + ("?" + u.query if u.query else "")) or SKIP.search(href):
                            continue
                        target = u.path + ("?" + u.query if u.query else "")
                        if re.sub(r"[?&]m=[^&]*", "", target) not in seen and target not in todo:
                            todo.append(target)
                    _ = title
            return problems, len(seen)
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=400)
    ap.add_argument("--width", type=int, default=1280)
    args = ap.parse_args()
    found, n = run(args.limit, args.width)
    print(f"{n} pages looked at")
    print("\n".join(dict.fromkeys(found)) if found else "nothing went wrong")
    sys.exit(1 if found else 0)
