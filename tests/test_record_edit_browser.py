"""Opening a record card or the add form must not throw the keyboard or the system's date sheet over the form (a phone), and with a mouse the cursor
goes to a text field - never into the date field.

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

COARSE = (
    "window.matchMedia = function (q) { return {matches: /pointer:\\s*coarse/.test(q), media: q, addEventListener: function () {}, "
    "removeEventListener: function () {}, addListener: function () {}, removeListener: function () {}}; };"
)
FOCUS = (
    "JSON.stringify({tag: document.activeElement.tagName, type: document.activeElement.type || '', "
    "in_card: !!document.activeElement.closest('[data-rec-edit].editing'), in_add: !!document.activeElement.closest('#addcard')})"
)


def test_a_tap_on_a_card_does_not_open_the_date_sheet_on_a_phone():
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
            url = f"{base}/v/{ms.DIESEL}/e/service"
            with Browser() as b:
                tap_card = "document.querySelector('[data-rec-edit] .rec-title').click()"
                tap_add = "document.querySelector('[data-add-toggle]').click()"

                # a phone (coarse pointer): the card opens, nothing takes the cursor
                b.open(url, 390, 900, 1, settle=1.0)
                b.drain()  # from here on everything the page reports is looked at
                assert b.run("matchMedia('(pointer: coarse)').matches") is False  # the test must see the real thing first
                b.run(COARSE)
                b.run(tap_card)
                time.sleep(0.2)
                got = json.loads(b.run(FOCUS))
                assert b.run("!!document.querySelector('[data-rec-edit].editing')") is True  # it did open ...
                assert got["in_card"] is False and got["type"] != "date"  # ... and the date field has no focus
                b.run(tap_add)
                time.sleep(0.2)
                got = json.loads(b.run(FOCUS))
                assert b.run("document.getElementById('addcard').open") is True and got["in_add"] is False

                # a mouse: the cursor goes to a text field of the card - not to the date
                b.open(url, 1200, 900, 1, settle=1.0)
                b.run(tap_card)
                time.sleep(0.2)
                got = json.loads(b.run(FOCUS))
                assert got["in_card"] is True and got["tag"] in ("INPUT", "TEXTAREA") and got["type"] not in ("date", "month", "time")
                b.open(url, 1200, 900, 1, settle=1.0)
                b.run(tap_add)
                time.sleep(0.2)
                got = json.loads(b.run(FOCUS))
                assert got["in_add"] is True and got["type"] not in ("date", "month", "time")
                reported = [e for e in b.drain() if e["kind"] in ("exception", "console", "csp")]
                assert not reported, reported  # no script error, no blocked script
        finally:
            server.terminate()
            server.wait(timeout=10)
