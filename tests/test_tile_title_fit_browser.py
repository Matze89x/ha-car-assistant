"""A long title in a half-width tile of the dashboard (an appointment): the type gets smaller until its longest word fits, so no word is torn
apart ("Verbandskas-ten"). On a real browser at the width of a small phone and a phone; skipped without one."""

import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

TITLE = "Verbandskasten prüfen"

MEASURE = """JSON.stringify((function () {
  var out = [];
  Array.prototype.forEach.call(document.querySelectorAll('.wd-v:not(.wd-fixed)'), function (e) {
    if (e.textContent.indexOf('Verbandskasten') < 0) { return; }
    var size = parseFloat(getComputedStyle(e).fontSize);
    e.style.setProperty('hyphens', 'none'); e.style.setProperty('overflow-wrap', 'normal');
    out.push({ size: size, wordFits: e.scrollWidth <= e.clientWidth + 1, width: e.clientWidth });
    e.style.removeProperty('hyphens'); e.style.removeProperty('overflow-wrap');
  });
  return out;
})())"""


@pytest.fixture(scope="module")
def tile():
    from cdp import Browser, find_chrome

    from browser_app import running_app

    if find_chrome() is None:
        pytest.skip("no Chrome / Chromium installed")
    with running_app(None) as (base, slug, _pk):
        with httpx.Client(follow_redirects=False, timeout=30) as c:
            # an overdue date: this appointment is the first one, so it is the one the tile shows
            r = c.post(f"{base}/v/{slug}/e/appointments", data={"title": TITLE, "due_date": "2020-01-01", "kind": "inspection"})
            assert r.status_code == 303, r.status_code
        with Browser() as b:
            yield b, f"{base}/v/{slug}"


@pytest.mark.parametrize("width", [320, 390])
def test_a_long_word_in_a_half_width_tile_is_not_torn_apart(tile, width):
    import json

    b, page = tile
    b.open(page, width, 1500, 1, settle=1.0)
    b.wait_for("document.querySelector('.wd-v')", seconds=15)
    time.sleep(0.4)
    got = json.loads(b.run(MEASURE))
    assert got, "the appointment tile was not found"
    assert all(g["size"] >= 15 for g in got), got  # the type never shrinks below a readable size
    # the longest word is whole in its line - on the very smallest phone only when 15px is enough, otherwise it ends up at that size and breaks at a syllable
    assert all(g["wordFits"] or g["size"] == 15 for g in got), got
    if width >= 390:
        assert all(g["wordFits"] for g in got), got
