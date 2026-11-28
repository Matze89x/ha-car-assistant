"""The update window in a real browser (tools/cdp.py; skipped without Chrome): the line *Update available* and the *Update* button open it, the changelog
of the package arrives only when it opens, what a source writes into it never runs, a failure shows a sentence and can be tried again, and the window fits
a phone - the two buttons on one line, the text of the changelog scrolling inside the window."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

PKG = {
    "id": "weather-tile",
    "kind": "plugin",
    "name": "Weather Tile",
    "version": "1.0.0",
    "description": "A small weather tile for the dashboard.",
    "author": "Example",
    "settings": [],
}
LOG = (
    "# Changelog\n\n## 1.2.0 - 2026-11-27\n### Added\n- A forecast for the next **three days** on the tile\n"
    '- <img src=x onerror="window.__pwned=1"> and <script>window.__pwned=2</script>\n'
    "- See [the page](javascript:window.__pwned=3)\n\n## 1.1.0 - 2026-10-30\n- Wind speed on the tile\n"
    + "".join(f"- A change number {n} with a few more words so that the list is long\n" for n in range(30))
    + "\n## 1.0.0 - 2026-09-14\n- First version\n"
)
OFFER = {
    "kind": "plugin",
    "id": "weather-tile",
    "name": "Weather Tile",
    "version": "1.2.0",
    "files": {"plugins/weather-tile/CHANGELOG.md": LOG},
}

STATE = """JSON.stringify((function () {
  var d = document.querySelector('dialog.upd-dlg'), log = d.querySelector('.upd-log');
  return {open: d.open, state: log.getAttribute('data-state'), text: log.textContent, tiles: Array.prototype.map.call(d.querySelectorAll('.upd-vers .tg'), function (t) { return t.querySelector('i').textContent + ' ' + t.querySelector('b').textContent; }),
          bad: log.querySelectorAll('script, img, a, iframe, [onerror]').length, pwned: window.__pwned || 0};
})())"""
MEASURE = """JSON.stringify((function () {
  var d = document.querySelector('dialog.upd-dlg'), r = d.getBoundingClientRect(), x = d.querySelector('.vsw-x').getBoundingClientRect(), h = d.querySelector('h2').getBoundingClientRect();
  var bar = Array.prototype.map.call(d.querySelectorAll('.form-bar button'), function (b) { var q = b.getBoundingClientRect(); return {top: Math.round(q.top), left: q.left, right: q.right, text: b.textContent.trim()}; });
  var log = d.querySelector('.upd-log');
  return {w: innerWidth, left: r.left, right: r.right, width: r.width, hscroll: document.documentElement.scrollWidth > innerWidth + 1, dlgScrolls: d.scrollHeight > d.clientHeight + 1,
          titleClear: h.right <= x.left + 1, bar: bar, logScrolls: log.scrollHeight > log.clientHeight + 1,
          inside: bar.every(function (q) { return q.left >= r.left - 0.5 && q.right <= r.right + 0.5; })};
})())"""


@pytest.fixture(scope="module")
def app():
    from cdp import Browser, find_chrome

    from browser_app import running_app

    if find_chrome() is None:
        pytest.skip("no Chrome / Chromium installed")
    with running_app(PKG, offer=OFFER) as (base, slug, _pk), Browser() as b:
        yield b, f"{base}/v/{slug}/plugins"


def _open(b, url, width=1000, height=900):
    b.open(url, width, height, 1, settle=0.6)


def _click(b, selector):
    b.run(f"document.querySelector({json.dumps(selector)}).click()")


def _state(b):
    return json.loads(b.run(STATE))


def test_the_line_opens_the_window_and_the_changelog_arrives_only_then(app):
    b, url = app
    _open(b, url)
    before = _state(b)
    assert not before["open"] and before["state"] is None and "Loading the changelog" in before["text"]  # nothing was read yet
    _click(b, "button.addon-status.upd")
    b.wait_for("document.querySelector('dialog.upd-dlg .upd-log[data-state=done]')")
    got = _state(b)
    assert got["open"] and got["tiles"] == ["Installed v1.0.0", "Available v1.2.0"]
    assert "three days" in got["text"] and "Wind speed on the tile" in got["text"] and "1.2.0" in got["text"]
    assert "First version" not in got["text"]  # that is the version that is installed: not news
    _click(b, "dialog.upd-dlg .form-bar [data-close]")  # Cancel
    assert not _state(b)["open"]


def test_the_update_button_opens_the_same_window_and_the_changelog_is_not_read_twice(app):
    b, url = app
    _open(b, url)
    _click(b, ".addon-bar button.primary[data-open]")
    b.wait_for("document.querySelector('dialog.upd-dlg .upd-log[data-state=done]')")
    assert _state(b)["open"]
    b.run("document.querySelector('dialog.upd-dlg .upd-log').setAttribute('data-changelog', '/nope')")  # a second reading would fail now
    _click(b, "dialog.upd-dlg [data-close]")
    _click(b, "button.addon-status.upd")
    assert _state(b)["state"] == "done" and "three days" in _state(b)["text"]


def test_what_a_source_writes_into_a_changelog_never_runs(app):
    b, url = app
    _open(b, url)
    _click(b, "button.addon-status.upd")
    b.wait_for("document.querySelector('dialog.upd-dlg .upd-log[data-state=done]')")
    got = _state(b)
    assert got["bad"] == 0 and got["pwned"] == 0  # no script, no picture, no link, no handler: it is text
    assert "<script>window.__pwned=2</script>" in got["text"] and "the page" in got["text"]


def test_a_failure_shows_a_sentence_and_the_next_opening_tries_again(app):
    b, url = app
    _open(b, url)
    good = b.run("document.querySelector('dialog.upd-dlg .upd-log').getAttribute('data-changelog')")
    b.run("document.querySelector('dialog.upd-dlg .upd-log').setAttribute('data-changelog', '/nope')")
    _click(b, "button.addon-status.upd")
    b.wait_for("document.querySelector('dialog.upd-dlg .upd-log').textContent.indexOf('could not be loaded') >= 0")
    failed = _state(b)
    assert failed["state"] is None and "You can still update" in failed["text"]  # nothing is marked as read
    _click(b, "dialog.upd-dlg [data-close]")
    b.run(f"document.querySelector('dialog.upd-dlg .upd-log').setAttribute('data-changelog', {json.dumps(good)})")
    _click(b, "button.addon-status.upd")
    b.wait_for("document.querySelector('dialog.upd-dlg .upd-log[data-state=done]')")
    assert "three days" in _state(b)["text"]


@pytest.mark.parametrize("width", [320, 360, 390, 1000])
def test_the_window_fits_the_screen_and_its_two_buttons_stay_on_one_line(app, width):
    b, url = app
    _open(b, url, width, 740)
    _click(b, "button.addon-status.upd")
    b.wait_for("document.querySelector('dialog.upd-dlg .upd-log[data-state=done]')")
    m = json.loads(b.run(MEASURE))
    assert m["left"] >= 0 and m["right"] <= m["w"] and not m["hscroll"], m  # nothing sticks out sideways
    assert m["inside"] and m["titleClear"], m  # the buttons lie inside the window, the title does not run under the X
    assert not m["dlgScrolls"] and m["logScrolls"], m  # the long text scrolls INSIDE the window; the window itself stays put
    assert [q["text"] for q in m["bar"]] == ["Cancel", "Update now"]
    if width > 340:
        assert len({q["top"] for q in m["bar"]}) == 1, m  # one line
    if width >= 1000:
        assert m["width"] <= 560, m  # a popup, not a page


def _language(b, url, code):
    """The language of the whole installation (the page asks for the German changelog and has German words, which are the longest)."""
    _open(b, url)
    b.run(
        "fetch('/settings/language', {method: 'POST', body: new URLSearchParams({language: "
        + json.dumps(code)
        + "}), credentials: 'same-origin', redirect: 'manual'}).then(function () { return true; })"
    )


@pytest.mark.parametrize("width", [320, 360, 390])
def test_in_german_the_window_fits_a_phone_too(app, width):
    b, url = app
    _language(b, url, "de")
    try:
        _open(b, url, width, 740)
        _click(b, "button.addon-status.upd")
        b.wait_for("document.querySelector('dialog.upd-dlg .upd-log[data-state=done]')")
        m = json.loads(b.run(MEASURE))
        assert m["left"] >= 0 and m["right"] <= m["w"] and not m["hscroll"], m
        assert m["inside"] and m["titleClear"], m  # the longest German label ("Jetzt aktualisieren") still lies inside the window
        assert [q["text"] for q in m["bar"]] == ["Abbrechen", "Jetzt aktualisieren"]
        if width > 340:
            assert len({q["top"] for q in m["bar"]}) == 1, m  # one line, in German too
        assert "Neuigkeiten" in b.run("document.querySelector('dialog.upd-dlg .sub-h').textContent")
    finally:
        _language(b, url, "en")
