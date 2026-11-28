"""The scan card of the vehicle pass in a real browser: a made-up certificate (tools/practice_registration.py) fills the EMPTY fields of a new car and marks them,
a car that already has its values keeps every one of them (what differs is only named, and one button takes it over), a picture of something else changes
nothing. Needs Chrome and Tesseract: skipped without them."""

import io
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

FIELDS = [
    "plate", "make", "model", "model_type", "first_reg", "hsn", "tsn", "vin",
    "power_kw", "displacement_ccm", "seats", "gross_weight_kg", "color", "body_type",
]  # fmt: skip
READ = """JSON.stringify((function () {
  var f = document.getElementById('vform'), o = {values: {}, marked: [], yellow: []};
  __FIELDS__.forEach(function (n) { o.values[n] = f.elements[n] ? String(f.elements[n].value) : null; });
  o.values.fuel_type = f.elements['fuel_type'].value; o.values.fuel2_type = f.elements['fuel2_type'].value;
  o.values.name = f.elements['name'].value; o.values.year = f.elements['year'].value;
  Array.prototype.forEach.call(document.querySelectorAll('.scan-hit'), function (e) { o.marked.push(e.name || e.className); if (e.classList.contains('scan-unsure')) o.yellow.push(e.name || e.className); });
  var n = document.querySelector('[data-reg-note]'); o.note = n.hidden ? '' : n.textContent; o.tone = n.className;
  var a = document.querySelector('[data-reg-apply]'); o.apply = !a.hidden;
  var i = document.querySelector('[data-reg-insp]'); o.insp = i.hidden ? null : {text: i.querySelector('.nm-t').textContent.trim(), value: i.querySelector('input').value, on: i.querySelector('input').checked};
  var opened = Array.prototype.map.call(document.querySelectorAll('details.fgroup[open]'), function (d) { return d.querySelector('.fg-t').textContent.trim(); });
  o.opened = opened;
  return o;
})())""".replace("__FIELDS__", json.dumps(FIELDS))
SETTLED = (
    "document.querySelector('[data-reg-note]') && !document.querySelector('[data-reg-note]').hidden"
    " && !document.querySelector('[data-reg-note]').classList.contains('busy')"
)


@pytest.fixture(scope="module")
def card():
    from cdp import Browser, find_chrome

    from browser_app import running_app
    from carassistant import receipt

    if find_chrome() is None:
        pytest.skip("no Chrome / Chromium installed")
    if not receipt.available():
        pytest.skip("Tesseract is not installed")
    import practice_registration as pr

    sample = {s.name: s for s in pr.samples()}["diesel-wagon"]
    with running_app(None) as (base, slug, _pk), Browser() as b:
        yield b, base, slug, sample


def _scan(b, data, name="certificate.jpg", mime="image/jpeg"):
    from cdp import upload_script

    b.run(upload_script('[data-reg-file="file"]', data, name, mime))
    b.wait_for(SETTLED, seconds=150)
    return json.loads(b.run(READ))


def test_a_new_car_is_filled_in_marked_and_nothing_else_is_touched(card):
    b, base, _slug, sample = card
    b.open(f"{base}/vehicles/new", 390, 1500, 1, settle=1.0)
    b.wait_for("document.querySelector('[data-regscan]')", seconds=15)
    got = _scan(b, sample.data)
    for name, want in sample.truth.items():
        if name in ("fuel_type", "seats"):
            continue
        assert got["values"][name] == want, name
    assert got["values"]["seats"] in (
        "",
        sample.truth["seats"],
    )  # (the lone digit of the seats is the weakest field: empty is allowed, wrong is not)
    assert (
        got["values"]["fuel_type"] == "diesel" and got["values"]["fuel2_type"] == ""
    )  # the preset petrol of a new car counts as empty until somebody chooses
    assert got["values"]["name"] == "" and got["values"]["year"] == ""  # nothing the certificate does not say
    assert len(got["marked"]) >= len(sample.truth) - 2  # every filled field (and the fuel tile) carries the mark
    assert "Identification" in got["opened"] and "Technical" in got["opened"]  # the groups with filled fields are open
    assert got["insp"] is not None and "06/2027" in got["insp"]["text"] and got["insp"]["value"] == "2027-06"
    assert got["tone"].split()[-1] in ("ok", "warn") and "Filled in from the certificate" in got["note"]
    assert not got["apply"]
    # the person changes a field: its mark goes
    b.run(
        "(function(){var e=document.getElementById('vform').elements['make'];e.value='Other';e.dispatchEvent(new Event('input',{bubbles:true}));})()"
    )
    assert "make" not in json.loads(b.run(READ))["marked"]


def test_a_car_with_values_keeps_every_one_and_the_certificate_only_names_what_differs(card):
    b, base, slug, sample = card
    b.open(f"{base}/v/{slug}/edit?mode=form", 390, 1500, 1, settle=1.0)
    b.wait_for("document.querySelector('[data-regscan]')", seconds=15)
    before = json.loads(b.run(READ))["values"]
    got = _scan(b, sample.data)
    assert got["values"] == before  # not one value was replaced
    assert got["marked"] == [] and got["apply"]
    assert "something else" in got["note"] and "not changed" in got["note"]
    assert got["insp"] is None  # the demo car has an inspection appointment already: it stays, nothing is offered
    # one button takes the values of the certificate over
    b.run("document.querySelector('[data-reg-apply]').click()")
    after = json.loads(b.run(READ))
    assert after["values"]["vin"] == sample.truth["vin"] and after["values"]["model"] == sample.truth["model"]
    assert "vin" in after["marked"] and not after["apply"] and "taken over" in after["note"]


def test_a_picture_of_something_else_changes_nothing(card):
    from PIL import Image, ImageDraw

    b, base, _slug, _sample = card
    b.open(f"{base}/vehicles/new", 390, 1500, 1, settle=1.0)
    b.wait_for("document.querySelector('[data-regscan]')", seconds=15)
    img = Image.new("RGB", (1600, 900), (225, 225, 225))
    ImageDraw.Draw(img).text((200, 400), "A letter from the garage, no certificate", fill=(20, 20, 20))
    out = io.BytesIO()
    img.save(out, "JPEG")
    got = _scan(b, out.getvalue())
    assert got["marked"] == [] and "Nothing could be read" in got["note"] and "warn" in got["tone"]
    assert got["values"]["plate"] == "" and got["insp"] is None


@pytest.mark.parametrize("width", [320, 390, 1200])
def test_the_card_fits_the_screen_at_every_width(card, width):
    b, base, slug, sample = card
    b.open(f"{base}/v/{slug}/edit?mode=form", width, 1500, 1, settle=1.0)
    b.wait_for("document.querySelector('[data-regscan]')", seconds=15)
    _scan(b, sample.data)  # the longest note and the button of the differing values are on show
    box = json.loads(
        b.run(
            """JSON.stringify((function () {
  var c = document.querySelector('.vf-scan').getBoundingClientRect(), out = {card: [c.left, c.right], over: document.documentElement.scrollWidth - innerWidth, outside: []};
  Array.prototype.forEach.call(document.querySelectorAll('.vf-scan *'), function (e) {
    var r = e.getBoundingClientRect();
    if (r.width && !e.hidden && (r.left < c.left - 1 || r.right > c.right + 1)) out.outside.push(e.className || e.tagName);
  });
  return out;
})())"""
        )
    )
    assert box["over"] <= 0, box  # no sideways scrolling
    assert box["outside"] == [], box  # nothing sticks out of the card
