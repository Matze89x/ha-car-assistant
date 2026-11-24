"""The zoomable map in a real browser: it draws every channel, the mouse wheel zooms, a click opens the details with the raw value and the history.

Skipped where no Chrome / Chromium is installed (see tools/cdp.py)."""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

POPULATE = r"""
import json, sys
sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[2])
from pathlib import Path
import make_screenshots as ms
ms.seed(Path(sys.argv[3]), "en")
from carassistant import db, linkmap
with db.tx() as conn:
    vid = conn.execute("SELECT id FROM vehicles WHERE slug = ?", (ms.DIESEL,)).fetchone()[0]
    conn.execute("INSERT INTO vehicle_addons(vehicle_id,kind,addon_id,manifest,status,settings,created_at,active) VALUES(?,'plugin','p-one',?,'configured','{}','2026-01-01',1)",
                 (vid, json.dumps({"id": "p-one", "kind": "plugin", "name": "Plugin One", "version": "1", "icon": "plug"})))
    pre = ["", "api", "v1", "vehicles", str(vid)]
    for km in (86020, 86031, 86044):
        linkmap._seen.clear()
        linkmap.record(conn, vid, "p-one", "POST", pre + ["data"], {"odometer_km": km, "ignition": "on"})
"""


def test_the_map_draws_zooms_and_opens_the_details_in_a_browser():
    from cdp import Browser, find_chrome

    if find_chrome() is None:
        pytest.skip("no Chrome / Chromium installed")
    import make_screenshots as ms

    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp)
        env = {
            **os.environ,
            "PYTHONPATH": str(ROOT / "carassistant" / "app") + os.pathsep + str(ROOT / "tools"),
            "CARASSISTANT_DATA": str(data),
            "CARASSISTANT_DEV": "1",
        }
        subprocess.run(
            [sys.executable, "-c", POPULATE, str(ROOT / "tools"), str(ROOT / "carassistant" / "app"), str(data)],
            check=True,
            env=env,
            capture_output=True,
            timeout=120,
        )
        port = ms.free_port()
        server = subprocess.Popen(
            [sys.executable, "-m", "carassistant"],
            env={**env, "CARASSISTANT_PORT": str(port)},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            base = f"http://127.0.0.1:{port}"
            ms.wait_for(base + "/healthz")
            with Browser() as b:
                b.open(f"{base}/v/{ms.DIESEL}/plugins/connections", 1280, 900, 1, settle=1.0)
                b.wait_for("document.getElementById('lmz').classList.contains('ready')")
                drawn = json.loads(
                    b.run(
                        "JSON.stringify({rows: document.querySelectorAll('.lmz-ch').length, open: document.querySelectorAll('.lmz-ch.open').length, live: document.querySelectorAll('.lmz-ch.live').length, plugins: document.querySelectorAll('.lmz-plugin').length, wires: document.querySelectorAll('.lmz-w').length})"
                    )
                )
                assert (
                    drawn["rows"] >= 50
                    and drawn["live"] == 2
                    and drawn["open"] == drawn["rows"] - 2
                    and drawn["plugins"] == 3  # Plugin One and the two plugins the demo data always carries (they have not talked yet)
                    and drawn["wires"] == 2
                )
                before = b.run("document.querySelector('.lmz-world').getAttribute('transform')")
                b.run(
                    "(function(){var s=document.querySelector('.lmz-stage'),r=s.getBoundingClientRect();s.dispatchEvent(new WheelEvent('wheel',{deltaY:-600,clientX:r.left+200,clientY:r.top+200,bubbles:true,cancelable:true}));})()"
                )
                time.sleep(0.2)
                assert b.run("document.querySelector('.lmz-world').getAttribute('transform')") != before  # the wheel zoomed
                b.run("document.querySelector('.lmz-ch[data-id=\"odometer_km\"]').dispatchEvent(new MouseEvent('click',{bubbles:true}))")
                b.wait_for("document.querySelectorAll('.lmz-sig').length > 0")
                shown = json.loads(
                    b.run(
                        "JSON.stringify({title: document.getElementById('lmz-dtitle').textContent, raw: document.querySelector('.lmz-sig pre').textContent, history: document.querySelectorAll('.lmz-sig .lm-hist li').length, conn: document.querySelectorAll('#lmz-conn li').length})"
                    )
                )
                assert shown == {"title": "Odometer", "raw": "86044", "history": 3, "conn": 1}
                b.run(
                    "document.querySelector('.lmz-ch[data-id=\"vin\"]').dispatchEvent(new MouseEvent('click',{bubbles:true}))"
                )  # an open channel explains itself
                b.wait_for("document.getElementById('lmz-dtitle').textContent === 'Vehicle identification number'")
                assert "OPEN" in b.run("document.getElementById('lmz-dextra').textContent")
        finally:
            server.terminate()
            server.wait(timeout=10)
