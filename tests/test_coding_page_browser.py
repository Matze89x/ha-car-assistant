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


STATE = """JSON.stringify((function () {
  var u = document.querySelector('.pm-unit'), sel = u.querySelector('.pm-sel'), q = function (x) { return u.querySelector(x); };
  var rs = q('.pm-reset'), hint = q('.pm-unsaved'), g = u.querySelector('input[name=bitgroups]');
  var notes = Array.prototype.filter.call(u.querySelectorAll('.pm-bnw'), function (w) { return !w.hidden; }).length;
  return { firstSelected: !!u.querySelector('.pm-byte.sel') && Array.prototype.indexOf.call(u.querySelectorAll('.pm-byte'), u.querySelector('.pm-byte.sel')), resetDisabled: rs.disabled, hintHidden: hint.hidden, groups: g.value, visibleNotes: notes };
})())"""

GROUP = """(function () {
  var s = document.querySelector('.pm-sel');
  [[1, 2], [4, 5, 6]].forEach(function (bits) {
    bits.forEach(function (n) { s.querySelector('.pm-gchip[data-bit="' + n + '"]').click(); });
    s.querySelector('.pm-gbtn').click();
  });
})()"""

LOOK = """JSON.stringify((function () {
  var u = document.querySelector('.pm-unit'), ul = u.querySelector('.pm-bitrows'), li = function (b) { return ul.querySelector('li[data-bit="' + b + '"]'); };
  var mid = function (r) { return (r.top + r.bottom) / 2; };
  var lab = li(1).querySelector('.pm-bl').getBoundingClientRect(), w = li(1).querySelector('.pm-bnw').getBoundingClientRect(), inp = li(1).querySelector('.pm-bnote').getBoundingClientRect();
  var r1 = li(1).querySelector('.pm-bd').getBoundingClientRect(), r2 = li(2).querySelector('.pm-bd').getBoundingClientRect();
  var gm = getComputedStyle(li(1).querySelector('.pm-bd')).borderBottomColor, last = getComputedStyle(li(7).querySelector('.pm-bd')).borderBottomWidth;
  var btn = Array.prototype.map.call(u.querySelectorAll('.pm-acts > *'), function (e) { var r = e.getBoundingClientRect(); return [Math.round(r.top), Math.round(r.right), Math.round(r.bottom)]; });
  var form = u.querySelector('.pm-form').getBoundingClientRect();
  return {
    labelText: li(1).querySelector('.pm-bl').textContent, labelSecondHidden: li(2).querySelector('.pm-bl').hidden, noteSecondHidden: li(2).querySelector('.pm-bnw').hidden,
    spanCoversBoth: Math.abs(lab.top - r1.top) < 2 && Math.abs(lab.bottom - r2.bottom) < 2 && Math.abs(w.top - r1.top) < 2 && Math.abs(w.bottom - r2.bottom) < 2,
    centred: Math.abs(mid(inp) - mid(lab)) < 40 && inp.height > 0, lineInsideGroup: gm, lineAfterLast: last,
    buttons: btn, oneLine: btn.length >= 2 && btn.every(function (b) { return Math.abs(b[0] - btn[0][0]) <= 2 && Math.abs(b[2] - btn[0][2]) <= 2; }),
    buttonsInside: btn.every(function (b) { return b[1] <= form.right + 1; }), factoryHeader: ul.querySelector('.pm-bh > :nth-child(2)').getBoundingClientRect().height
  };
})())"""


@pytest.mark.parametrize("width", [320, 390, 768])
def test_a_group_joins_its_rows_and_a_unit_is_saved_or_reset_by_its_buttons(coding, width):
    import json

    b, page = coding
    b.open(page, width, 900, 1, settle=0.8)
    b.wait_for("document.querySelector('.pm-unit .pm-byte')", seconds=15)
    b.run("document.querySelector('.pm-unit').open = true")
    time.sleep(0.5)
    start = json.loads(b.run(STATE))
    assert start["firstSelected"] == 0, start  # opened: byte 0 is chosen already
    assert start["resetDisabled"] and start["hintHidden"] and start["visibleNotes"] == 8, (
        start
    )  # nothing changed: nothing to take back, nothing unsaved
    b.run(GROUP)
    time.sleep(0.3)
    got = json.loads(b.run(LOOK))
    assert got["labelText"] == "Bit 1+2" and got["labelSecondHidden"] and got["noteSecondHidden"], (
        got
    )  # ONE label and ONE note over both rows
    assert got["spanCoversBoth"] and got["centred"], got  # they stand over the two rows, the note in the middle
    assert got["lineInsideGroup"] in ("rgba(0, 0, 0, 0)", "transparent"), got  # no line between the bits of a group
    assert got["lineAfterLast"] == "0px", got  # and none after the last row
    assert got["oneLine"] and got["buttonsInside"], got  # Reset and Save (and New = factory) stand in one line inside the card
    assert got["factoryHeader"] < 36, got  # the heading of the factory column is one line, not wrapped into three
    changed = json.loads(b.run(STATE))
    assert not changed["resetDisabled"] and not changed["hintHidden"] and changed["visibleNotes"] == 8 - 1 - 2, (
        changed
    )  # unsaved: the line says so, Reset works
    b.run("document.querySelector('.pm-reset').click()")
    time.sleep(0.3)
    back = json.loads(b.run(STATE))
    assert back["resetDisabled"] and back["hintHidden"] and back["visibleNotes"] == 8 and back["groups"] in ("", "{}"), (
        back
    )  # Reset: everything as it was loaded
