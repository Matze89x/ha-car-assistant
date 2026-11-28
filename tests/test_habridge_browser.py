"""The page of the Home Assistant plugin on a real browser, against a made-up Home Assistant (tools/fake_ha.py): the list of entities opens at a click, a click on
an entity fills the field and the line under it says what the entity delivers, the options come once an entity is chosen, a row can be added, a save sticks - and at
the width of a phone nothing runs out of the screen. Needs a real browser (tools/cdp.py); skipped without one."""

import json
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

# (a page that is not the focused window of a headless browser does not fire the focus events by itself: they are sent here)
OPEN = "(function (slot) { var i = document.querySelector('[data-hb-slot=' + slot + '] [data-hb-entity]'); i.focus(); i.dispatchEvent(new FocusEvent('focusin', {bubbles: true})); })('%s')"

STATE = """JSON.stringify((function () {
  var box = document.querySelector('[data-hb-slot="odometer_km"]'), input = box.querySelector('[data-hb-entity]');
  var line = box.querySelector('[data-hb-status]'), panel = document.querySelector('[data-hb-panel]');
  var wide = Array.prototype.filter.call(document.querySelectorAll('.hb-row, .hb-lrow, .hb-fld, .hb-panel'), function (e) {
    var r = e.getBoundingClientRect(); return r.width && (r.right > window.innerWidth + 1 || r.left < -1);
  }).length;
  return {
    value: input.value, level: line.getAttribute('data-level'), text: line.textContent.trim(),
    options: !box.querySelector('.hb-opts').hidden, panel: !panel.hidden, choices: panel.querySelectorAll('.hb-opt').length,
    first: panel.querySelector('.hb-opt') ? panel.querySelector('.hb-opt').textContent : '',
    sideScroll: document.documentElement.scrollWidth > window.innerWidth + 1, outside: wide,
    groups: document.querySelectorAll('.hb-group').length
  };
})())"""


@pytest.fixture(scope="module")
def page():
    from cdp import Browser, find_chrome
    from fake_ha import FakeHA, demo
    from tests.test_habridge import BRIDGE

    from browser_app import running_app

    if find_chrome() is None:
        pytest.skip("no Chrome / Chromium installed")
    fake = FakeHA().start()
    demo(fake)
    try:
        with running_app(BRIDGE, {"CARASSISTANT_HA_API": fake.api, "SUPERVISOR_TOKEN": fake.token}) as (base, slug, pk), Browser() as b:
            address = f"{base}/v/{slug}/integrations/{pk}/settings"
            end = time.time() + 20
            while time.time() < end and "Live connection to Home Assistant" not in httpx.get(address, timeout=20).text:
                time.sleep(0.3)  # the app builds up its live connection a moment after it starts
            yield b, address
    finally:
        fake.stop()


@pytest.mark.parametrize("width", [320, 390, 1000])
def test_the_page_fits_the_screen_and_says_the_connection_is_live(page, width):
    b, address = page
    b.open(address, width, 900, 1, settle=1.0)
    b.wait_for("document.querySelector('[data-hb-form]')", seconds=15)
    got = json.loads(b.run(STATE))
    assert got["groups"] == 9 and not got["sideScroll"] and got["outside"] == 0, got
    assert b.run("document.querySelector('.hb-live').getAttribute('data-live')") == "1"  # the live connection stands


def test_choosing_an_entity_from_the_list(page):
    b, address = page
    b.open(address, 1000, 900, 1, settle=1.0)
    b.wait_for("document.querySelector('[data-hb-form]')", seconds=15)
    b.run(OPEN % "odometer_km")
    b.wait_for("document.querySelectorAll('[data-hb-panel] .hb-opt').length > 0", seconds=10)
    got = json.loads(b.run(STATE))
    assert got["panel"] and got["choices"] > 3 and "odometer" in got["first"].lower() and got["value"] == "", got  # the likeliest first
    b.run("document.querySelector('[data-hb-panel] .hb-opt').click()")  # a click on the first
    b.wait_for("document.querySelector('[data-hb-slot=odometer_km] [data-hb-status]').getAttribute('data-level') === 'ok'", seconds=10)
    got = json.loads(b.run(STATE))
    assert got["value"] == "sensor.family_car_odometer" and not got["panel"] and got["options"], got
    assert got["text"] == "48210.5 km", got  # what Home Assistant says, converted if need be
    # the words typed are looked for in the device and the area, too
    b.run(
        "var i = document.querySelector('[data-hb-slot=charge_power_kw] [data-hb-entity]'); i.focus(); i.value = 'garage'; i.dispatchEvent(new Event('input', {bubbles: true}))"
    )
    b.wait_for("document.querySelectorAll('[data-hb-panel] .hb-opt').length === 2", seconds=10)
    assert "Wallbox" in b.run("document.querySelector('[data-hb-panel]').textContent") and "Garage" in b.run(
        "document.querySelector('[data-hb-panel]').textContent"
    )
    assert (
        b.run("document.querySelector('[data-hb-slot=charge_power_kw] [data-hb-status]').getAttribute('data-level')") == "idle"
    )  # words for the list: no error for them


def test_a_row_more_in_a_list_and_a_save_that_sticks(page):
    b, address = page
    b.open(address, 1000, 900, 1, settle=1.0)
    b.wait_for("document.querySelector('[data-hb-form]')", seconds=15)
    before = b.run("document.querySelectorAll('[data-hb-list=doors] [data-hb-lrow]').length")
    b.run("document.querySelector('[data-hb-slot=doors] [data-hb-add]').click()")
    assert b.run("document.querySelectorAll('[data-hb-list=doors] [data-hb-lrow]').length") == before + 1
    b.run(
        "var f = document.querySelector('[data-hb-form]');"
        "f.querySelector('[name=\"e.range_km\"]').value = 'sensor.family_car_range';"
        "f.querySelector('[name=\"l.doors.0.n\"]').value = 'front_left';"
        "f.querySelector('[name=\"l.doors.0.e\"]').value = 'binary_sensor.family_car_door_front_left';"
        "f.requestSubmit()"
    )
    b.wait_for("location.search.indexOf('m=saved') > -1", seconds=15)
    saved = httpx.get(address, timeout=20).text
    assert (
        'value="sensor.family_car_range"' in saved
        and 'value="binary_sensor.family_car_door_front_left"' in saved
        and 'value="front_left"' in saved
    )
    b.wait_for("document.querySelector('[data-hb-slot=range_km] [data-hb-status]').getAttribute('data-level') === 'ok'", seconds=10)
    assert b.run("document.querySelector('[data-hb-slot=range_km] [data-hb-status]').textContent.trim()") == "281 km"
