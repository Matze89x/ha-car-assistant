"""The widget editor on Home in a real browser: a tap beside the widgets ends the editing and what was changed is saved - nothing else to press.

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

EDITING = "document.getElementById('wgrid').classList.contains('editing')"
STATE = "JSON.stringify(Array.prototype.map.call(document.querySelectorAll('.wd-slot'), function (s) { return [s.getAttribute('data-k'), s.classList.contains('off')]; }))"


def _mouse(b, kind: str, x: float, y: float) -> None:
    b.call("Input.dispatchMouseEvent", type=kind, x=x, y=y, button="left", clickCount=1)


def _tap(b, x: float, y: float) -> None:
    _mouse(b, "mousePressed", x, y)
    _mouse(b, "mouseReleased", x, y)
    time.sleep(0.25)


def test_a_tap_beside_the_widgets_saves_and_ends_the_editing():
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
        seed = "import sys; from pathlib import Path; import make_screenshots as ms; ms.seed(Path(sys.argv[1]), 'en')"
        subprocess.run([sys.executable, "-c", seed, str(data)], check=True, env=env, capture_output=True, timeout=120)
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
            url = f"{base}/v/{ms.DIESEL}"
            with Browser() as b:
                b.open(url, 1280, 1500, 1, settle=1.5)
                before = json.loads(b.run(STATE))
                key = next(k for k, off in before if not off and k not in ("messages",))
                outside = (1268.0, 700.0)  # the page behind the content, right of the widgets
                assert b.run(f"!document.elementFromPoint({outside[0]}, {outside[1]}).closest('.wd-slot, a, button, dialog')"), (
                    "the spot is not empty"
                )

                b.run("document.getElementById('wd-toggle').click()")
                assert b.run(EDITING) is True
                b.run(f"document.querySelector('.wd-slot[data-k=\"{key}\"] .wd-eye').click()")  # hide one widget (saved a moment later)

                # a tap ON a widget does not end it (and does not follow its link)
                box = json.loads(
                    b.run(
                        "(function(){var r=document.querySelector('.wd-slot[data-k=\"messages\"]').getBoundingClientRect();return JSON.stringify([r.left+r.width/2,r.top+r.height/2]);})()"
                    )
                )
                _tap(b, *box)
                assert b.run(EDITING) is True and b.run("location.pathname") == f"/v/{ms.DIESEL}"

                # pressing beside and dragging away (a scroll, a selection) is no tap
                _mouse(b, "mousePressed", *outside)
                _mouse(b, "mouseMoved", outside[0], outside[1] + 120)
                _mouse(b, "mouseReleased", outside[0], outside[1] + 120)
                time.sleep(0.2)
                assert b.run(EDITING) is True

                # a tap beside the widgets: finished, the button says so, and the change is on the server
                _tap(b, *outside)
                assert b.run(EDITING) is False
                assert b.run("document.querySelector('#wd-toggle .lbl').textContent") == "Customise dashboard"
                time.sleep(0.8)
                b.open(url, 1280, 1500, 1, settle=1.0)
                after = dict((k, off) for k, off in json.loads(b.run(STATE)))
                assert after[key] is True  # the hidden widget stayed hidden after a reload

                # Escape ends it too
                b.run("document.getElementById('wd-toggle').click()")
                assert b.run(EDITING) is True
                b.run("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))")
                assert b.run(EDITING) is False
        finally:
            server.terminate()
            server.wait(timeout=10)
