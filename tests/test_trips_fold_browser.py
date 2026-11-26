"""The trips page on a real browser: the analysis and the km counters are folded windows; the plus in the header of the counters opens the window and its form, an
address ending in #analysis opens the analysis. Needs a real browser (tools/cdp.py); skipped without one."""

import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

STATE = """JSON.stringify((function () {
  var a = document.getElementById('analysis'), c = document.getElementById('counters'), plus = c.querySelector('summary [data-toggle-panel]');
  var panel = document.getElementById('counter-add'), sum = c.querySelector('summary').getBoundingClientRect(), pb = plus.getBoundingClientRect();
  return {
    analysisOpen: a.open, countersOpen: c.open, panelHidden: panel.hidden,
    plusInHeader: pb.top >= sum.top - 1 && pb.bottom <= sum.bottom + 1 && pb.right <= sum.right + 1 && pb.left > sum.left + sum.width / 2,
    analysisBody: a.querySelector('.ta-tabs').getBoundingClientRect().height,
    noSideScroll: document.documentElement.scrollWidth <= window.innerWidth + 1,
    start: panel.querySelector('[name=start_date]').value
  };
})())"""


@pytest.fixture(scope="module")
def trips():
    from cdp import Browser, find_chrome

    from browser_app import running_app

    if find_chrome() is None:
        pytest.skip("no Chrome / Chromium installed")
    with running_app(None) as (base, slug, _pk), Browser() as b:
        yield b, f"{base}/v/{slug}/e/trips"


@pytest.mark.parametrize("width", [320, 390, 768])
def test_the_windows_are_folded_and_the_plus_opens_the_counters(trips, width):
    b, page = trips
    b.open(page, width, 900, 1, settle=1.0)
    b.wait_for("document.getElementById('counters')", seconds=15)
    got = json.loads(b.run(STATE))
    assert not got["analysisOpen"] and not got["countersOpen"] and got["panelHidden"], got  # the page opens on the trips
    assert got["plusInHeader"] and got["noSideScroll"], got  # the plus at the right of the header, nothing runs out of the screen
    b.run("document.querySelector('#counters summary [data-toggle-panel]').click()")
    time.sleep(0.4)
    got = json.loads(b.run(STATE))
    assert got["countersOpen"] and not got["panelHidden"] and got["start"], (
        got
    )  # the plus opened the window AND its form (a start date is there)
    b.run("document.querySelector('#analysis > summary').click()")
    time.sleep(0.3)
    got = json.loads(b.run(STATE))
    assert got["analysisOpen"] and got["analysisBody"] > 0, got  # a tap on the header opens the analysis


def test_an_address_with_the_id_of_a_folded_window_opens_it(trips):
    b, page = trips
    b.open(page + "#analysis", 390, 900, 1, settle=1.0)
    b.wait_for("document.getElementById('analysis')", seconds=15)
    time.sleep(0.3)
    assert json.loads(b.run(STATE))["analysisOpen"]  # the link of a period (…?ap=30#analysis) and the page after a counter was saved
    b.open(page + "#counters", 390, 900, 1, settle=1.0)
    b.wait_for("document.getElementById('counters')", seconds=15)
    time.sleep(0.3)
    assert json.loads(b.run(STATE))["countersOpen"]
