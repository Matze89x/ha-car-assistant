"""The roll-in of the odometer starts from "invisible"; a safety net switches the animation off after a moment, so that the figures (and their frames) are
there even when an animation never ran (a home-screen web app that starts in the background: an empty gap under the range text on an iPhone).
Needs a real browser (tools/cdp.py); skipped without one."""

import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

STATE = """JSON.stringify((function () {
  var cells = Array.prototype.filter.call(document.querySelectorAll('.odo-drum i'), function (e) { return e.getClientRects().length > 0; });
  return {
    settled: document.documentElement.classList.contains('odo-settled'),
    cells: cells.length,
    visible: cells.every(function (e) { var s = getComputedStyle(e); return s.opacity === '1' && s.animationName === 'none'; })
  };
})())"""


def test_the_odometer_is_there_even_without_its_animation():
    from cdp import Browser, find_chrome

    from browser_app import running_app

    if find_chrome() is None:
        pytest.skip("no Chrome / Chromium installed")
    with running_app(None) as (base, slug, _pk), Browser() as b:
        b.open(f"{base}/v/{slug}", 390, 900, 1, settle=0.5)
        b.wait_for("document.querySelector('.hero-meta, .vehicle-hero')", seconds=15)
        time.sleep(3.2)  # the safety net runs after about 2.6 seconds
        got = json.loads(b.run(STATE))
        assert got["settled"] and got["cells"] > 0, got  # the plate is on the page
        assert got["visible"], got  # every figure that is on the page: fully visible, without an animation
