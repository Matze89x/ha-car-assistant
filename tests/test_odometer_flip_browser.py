"""The odometer plate of the dashboard turned over: under it stands the line of the back (the note, or all readings) and - when a reading does not fit - the
warning of the front. They must never lie on top of each other (they once did: both stood exactly under the plate). On a real browser at three widths;
skipped without one."""

import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

MEASURE = """JSON.stringify((function () {
  var flip = document.querySelector('.odo-flip');
  if (!flip) { return null; }
  return Array.prototype.map.call(flip.querySelectorAll('.odo-all, .scan-note'), function (e) {
    var cs = getComputedStyle(e), r = e.getBoundingClientRect();
    var shown = cs.display !== 'none' && cs.visibility !== 'hidden' && parseFloat(cs.opacity) > 0 && r.width > 0 && r.height > 0 && !e.hidden;
    return { cls: e.className, text: e.textContent.trim().slice(0, 40), shown: shown, l: r.left, t: r.top, w: r.width, h: r.height };
  });
})())"""


@pytest.fixture(scope="module")
def dashboard():
    from cdp import Browser, find_chrome

    from browser_app import running_app

    if find_chrome() is None:
        pytest.skip("no Chrome / Chromium installed")
    with running_app(None) as (base, slug, _pk), Browser() as b:
        yield b, f"{base}/v/{slug}"


def _overlaps(lines):
    found = []
    shown = [x for x in lines if x["shown"]]
    for i, a in enumerate(shown):
        for b in shown[i + 1 :]:
            if (
                a["l"] < b["l"] + b["w"] - 1
                and b["l"] < a["l"] + a["w"] - 1
                and a["t"] < b["t"] + b["h"] - 1
                and b["t"] < a["t"] + a["h"] - 1
            ):
                found.append((a["text"], b["text"]))
    return found


@pytest.mark.parametrize("width", [320, 390, 1200])
def test_the_lines_under_the_odometer_plate_never_lie_on_top_of_each_other(dashboard, width):
    b, page = dashboard
    b.open(page, width, 1500, 1, settle=1.0)
    b.wait_for("document.querySelector('.odo-front[data-odo-open]')", seconds=15)
    closed = json.loads(b.run(MEASURE))
    odd = [x for x in closed if "odd" in x["cls"].split()]
    assert odd and odd[0]["shown"], closed  # the demo car has a reading that does not fit: the warning stands under the plate
    b.run("document.querySelector('.odo-front[data-odo-open]').click()")
    b.wait_for("document.querySelector('.odo-flip.open')", seconds=5)
    time.sleep(1.2)  # the plate turns over (.8 s)
    opened = json.loads(b.run(MEASURE))
    assert not _overlaps(opened), opened
    assert any(x["shown"] and "odo-all" in x["cls"] for x in opened), opened  # the back says something under the plate: all readings
