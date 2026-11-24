"""The tab bars of the Plugins and Integrations pages (Manage, Connections, Add, Sources) fit a phone: at 560 px and below only the open tab names
itself, the others are their symbol - nothing is cut off and nothing needs a swipe. Needs a real browser (tools/cdp.py); skipped without one."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

PAGES = (
    "plugins",
    "plugins/connections",
    "plugins/add",
    "plugins/sources",
    "integrations",
    "integrations/add",
    "integrations/sources",
)
MEASURE = """JSON.stringify((function () {
  var bar = document.querySelector('.seg-tabs'); if (!bar) { return {none: true}; }
  var r = bar.getBoundingClientRect(), tabs = Array.prototype.slice.call(bar.querySelectorAll('a'));
  return {
    cls: bar.className, n: tabs.length, scrolls: bar.scrollWidth > bar.clientWidth + 1,
    outside: tabs.filter(function (a) { return a.getBoundingClientRect().right > r.right + 0.5; }).length,
    named: tabs.filter(function (a) { var s = a.querySelector('span'); return s && s.getBoundingClientRect().width > 4; }).length,
    titles: tabs.every(function (a) { return !!a.title; })
  };
})())"""


@pytest.fixture(scope="module")
def app():
    from cdp import Browser, find_chrome

    from browser_app import running_app

    if find_chrome() is None:
        pytest.skip("no Chrome / Chromium installed")
    with running_app() as (base, slug, _pk), Browser() as b:
        yield b, f"{base}/v/{slug}"


@pytest.mark.parametrize("width", [320, 390, 560])
def test_the_tab_bars_fit_a_phone_and_only_the_open_tab_names_itself(app, width):
    b, car = app
    for page in PAGES:
        b.open(f"{car}/{page}", width, 800, 1, settle=0.5)
        got = json.loads(b.run(MEASURE))
        assert not got.get("none"), page
        assert "fold" in got["cls"], (page, got)
        assert not got["scrolls"] and got["outside"] == 0, (page, width, got)  # nothing is cut off, nothing to swipe
        assert got["named"] == 1, (page, got)  # only the open tab shows its word
        assert got["titles"], (page, got)  # the others keep their name as the tip


def test_on_a_wide_screen_every_tab_names_itself(app):
    b, car = app
    b.open(f"{car}/plugins", 900, 800, 1, settle=0.5)
    got = json.loads(b.run(MEASURE))
    assert got["named"] == got["n"] == 4, got
