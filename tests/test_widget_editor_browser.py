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


# a spot of the page that is neither a widget nor anything that can be pressed (the margin beside the widgets, empty room in a column ...), found
# by looking: the layout is not the same on every machine (fonts, scrollbars)
EMPTY_SPOT = """(function () {
  var keep = '.wd-slot, a.wd-addtile, #wd-toggle, dialog, a, button, input, select, textarea, label, summary, [role=button]';
  for (var y = 300; y < 900; y += 60) {
    for (var x = document.documentElement.clientWidth - 6; x > 20; x -= 6) {
      var e = document.elementFromPoint(x, y);
      if (e && e.closest && !e.closest(keep) && !e.closest('[data-rec-edit]')) { return JSON.stringify([x, y]); }
    }
  }
  return 'null';
})()"""


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
                b.run("document.getElementById('wd-toggle').click()")
                assert b.run(EDITING) is True
                b.run(f"document.querySelector('.wd-slot[data-k=\"{key}\"] .wd-eye').click()")  # hide one widget (saved a moment later)
                spot = json.loads(b.run(EMPTY_SPOT))
                assert spot is not None, "no empty spot beside the widgets"
                outside = (float(spot[0]), float(spot[1]))

                # a tap ON a widget does not end it (and does not follow its link)
                box = json.loads(
                    b.run(
                        "(function(){var r=document.querySelector('.wd-slot[data-k=\"messages\"]').getBoundingClientRect();return JSON.stringify([r.left+r.width/2,r.top+r.height/2]);})()"
                    )
                )
                _tap(b, *box)
                time.sleep(0.4)
                assert b.run(EDITING) is True and b.run("location.pathname") == f"/v/{ms.DIESEL}"

                # pressing beside and dragging away (a scroll, a selection) is no tap
                _mouse(b, "mousePressed", *outside)
                _mouse(b, "mouseMoved", outside[0], outside[1] + 120)
                _mouse(b, "mouseReleased", outside[0], outside[1] + 120)
                time.sleep(0.4)
                assert b.run(EDITING) is True

                # a tap beside the widgets: finished, the button says so, and the change is on the server
                _tap(b, *outside)
                b.wait_for(f"!{EDITING}")
                assert b.run("document.querySelector('#wd-toggle .lbl').textContent") == "Customise dashboard"
                hidden = False
                for _ in range(12):  # the save is a request of its own: look again until it has arrived
                    time.sleep(0.5)
                    b.open(url, 1280, 1500, 1, settle=0.5)
                    hidden = dict(json.loads(b.run(STATE)))[key]
                    if hidden:
                        break
                assert hidden is True  # the hidden widget stayed hidden after a reload

                # Escape ends it too
                b.run("document.getElementById('wd-toggle').click()")
                assert b.run(EDITING) is True
                b.run("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))")
                b.wait_for(f"!{EDITING}")
        finally:
            server.terminate()
            server.wait(timeout=10)
