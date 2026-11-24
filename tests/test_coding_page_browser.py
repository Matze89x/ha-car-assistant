"""The Coding page (the control units of the car and their codings) on a real browser, at the width of a small phone, a phone and a tablet.

It had been checked without any data: with a unit whose byte is opened, the editor was wider than the screen (a note field cut off at the edge, the
round bit buttons running out of the box). Needs a real browser (tools/cdp.py); skipped without one."""

import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

OLD = " ".join(f"{(i * 7) % 256:02X}" for i in range(40))
NEW = OLD.replace(OLD.split()[6], "FF", 1)  # one byte changed

# The opened editor of a changed byte: what leaves its box, what is too small to type in without a phone zooming, what is not even
MEASURE = """JSON.stringify((function () {
  var u = document.querySelector('.pm-unit'); u.open = true;
  var cells = u.querySelectorAll('.pm-byte'); cells[6].click();
  var sel = u.querySelector('.pm-sel'), sr = sel.getBoundingClientRect(), out = [];
  Array.prototype.forEach.call(sel.querySelectorAll('*'), function (e) {
    var r = e.getBoundingClientRect();
    if (r.width && (r.right > sr.right + 0.5 || r.left < sr.left - 0.5)) { out.push(e.className + ' ' + Math.round(r.right - sr.right)); }
  });
  var small = [];
  Array.prototype.forEach.call(u.querySelectorAll('input[type=text], input[type=number], textarea'), function (e) {
    if (e.type !== 'hidden' && parseFloat(getComputedStyle(e).fontSize) < 16) { small.push(e.className || e.name); }
  });
  var sizes = {};
  Array.prototype.forEach.call(cells, function (c) { var r = c.getBoundingClientRect(); sizes[Math.round(r.width) + 'x' + Math.round(r.height)] = 1; });
  return {
    shown: !sel.hidden, outside: out, small: small, cellSizes: Object.keys(sizes),
    pageScrolls: document.documentElement.scrollWidth > window.innerWidth + 1,
    spin: getComputedStyle(u.querySelector('.pm-gval') || u).getPropertyValue('-moz-appearance') || ''
  };
})())"""


@pytest.fixture(scope="module")
def coding():
    from cdp import Browser, find_chrome

    from browser_app import running_app

    if find_chrome() is None:
        pytest.skip("no Chrome / Chromium installed")
    from tests.test_pagemods import PKG

    with running_app(PKG) as (base, slug, _pk):
        page = f"{base}/v/{slug}/m/coding-demo"
        with httpx.Client(follow_redirects=False, timeout=30) as c:
            for addr, name, old, new, notes in (
                ("09", "Central electronics (a name that is rather long for a small screen)", OLD, NEW, "A long note " * 12),
                ("5F", "Information electronics 1", "0A 0B 0C 0D", "0A 0B 0C 0D", ""),
            ):
                r = c.post(page + "/units", data={"addr": addr, "name": name, "old": old, "new": new, "notes": notes})
                assert r.status_code == 303, r.status_code
        with Browser() as b:
            yield b, page


@pytest.mark.parametrize("width", [320, 390, 768])
def test_the_opened_byte_editor_fits_the_screen(coding, width):
    import json

    b, page = coding
    b.open(page, width, 900, 1, settle=0.8)
    b.wait_for("document.querySelector('.pm-unit .pm-byte')", seconds=15)
    got = json.loads(b.run(MEASURE))
    time.sleep(0.2)
    assert got["shown"], got
    assert not got["outside"], got  # nothing of the editor stands out of its box
    assert not got["pageScrolls"], got  # and the page itself never scrolls sideways
    assert not got["small"], got  # a field below 16px makes iPhone Safari zoom in when it is touched
    assert len(got["cellSizes"]) == 1, got  # the bytes are one even grid: a changed byte is not bigger than the rest
