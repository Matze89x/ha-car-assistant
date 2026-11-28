"""The wallbox card of the Charging page and its tile on Home: what a person sees for each state of the wallbox, in both languages, and nothing for a car
without a wallbox (carassistant/wallbox.py, templates/_wallbox_card.html, templates/widgets/wallbox.html)."""

import re

import pytest
from tests.test_web import create_vehicle

from carassistant import config, connectors, db


def electric(client, name="Card Car", **change):
    vid = create_vehicle(client, name)
    with db.tx() as conn:
        conn.execute("UPDATE vehicles SET fuel_type = ?, battery_kwh = 60 WHERE id = ?", (change.get("fuel_type", "electric"), vid))
        slug = conn.execute("SELECT slug FROM vehicles WHERE id = ?", (vid,)).fetchone()["slug"]
    return vid, slug


def say(vid, **data):
    with db.tx() as conn:
        connectors.ingest(conn, vid, data, "test")


def page(client, slug):
    return client.get(f"/v/{slug}/e/fuel").text


def card(html):
    found = re.search(r'<section class="card wb".*?</section>', html, re.S)
    return found.group(0) if found else ""


CHARGING = {
    "charge_state": "charging", "charging": True, "plugged": True, "charge_power_kw": 7.4, "charge_session_kwh": 3.7, "charge_session_minutes": 30,
    "charge_voltage_v": 230, "charge_current_a": 10.7, "charge_phases": 3, "charge_current_limit_a": 16, "battery_pct": 50, "charge_limit_pct": 80,
    "charge_mode": "Solar", "charge_total_kwh": 4214.1,
}  # fmt: skip


def test_a_car_that_charges_at_a_wallbox_gets_the_card_with_the_live_figures(client):
    vid, slug = electric(client)
    say(vid, **CHARGING)
    html = card(page(client, slug))
    assert 'data-st="charging"' in html and 'id="wb"' in html
    assert 'stroke-dasharray="50.0 100"' in html and "rotate(288.0 116 116)" in html  # 50 % of the ring, the target mark at 80 %
    assert "<b>7.4</b><span>kW</span>" in html and "of max. 11.0 kW" in html
    assert "3 × 10.7 A" in html and "230 V" in html and "3 phases" in html
    assert "Mode: Solar" in html and "Charging" in html and "Target 80 %" in html and "left" in html
    for fact in ("Charged", "3.7 kWh", "Duration", "30 min", "Done at", "Max current", "16 A", "Counter", "4,214.1 kWh"):
        assert fact in html, fact


def test_the_card_speaks_german_with_the_decimal_comma(client, monkeypatch):
    vid, slug = electric(client)
    say(vid, **CHARGING)
    monkeypatch.setattr(config, "language", lambda: "de")
    html = card(page(client, slug))
    assert "Lädt" in html and "Modus: Solar" in html and "Ziel 80 %" in html and "von max. 11,0 kW" in html and "<b>7,4</b>" in html
    assert "Geladen" in html and "Dauer" in html and "Max. Strom" in html and "3 Phasen" in html


def test_a_car_without_wallbox_data_that_does_not_charge_has_no_card(client):
    vid, slug = electric(client)
    assert card(page(client, slug)) == ""
    say(vid, battery_pct=70, charge_limit_pct=80, charging=False, plugged=True)
    assert card(page(client, slug)) == ""  # the Home car data say that already


def test_a_car_that_only_says_it_charges_gets_a_card_too(client):
    vid, slug = electric(client)
    say(vid, charging=True, plugged=True, charge_power_kw=11, battery_pct=40)
    html = card(page(client, slug))
    assert 'data-st="charging"' in html and "<b>11.0</b>" in html


def test_a_car_with_a_tank_never_gets_a_card(client):
    vid, slug = electric(client, "Tank Car", fuel_type="petrol")
    say(vid, **CHARGING)
    assert card(page(client, slug)) == ""


@pytest.mark.parametrize(
    ("data", "state", "words"),
    [
        ({"charge_state": "waiting", "plugged": True, "battery_pct": 31, "charge_limit_pct": 80, "charge_mode": "Solar"}, "waiting", ("Waiting to charge", "mode Solar", "To the target", "29.4 kWh")),
        ({"charge_state": "plugged", "plugged": True}, "plugged", ("Plugged in", "Charging has not started yet.")),
        ({"charge_state": "fault", "charge_fault": "E-12 residual current", "battery_pct": 47, "charge_session_kwh": 6.1}, "fault", ("E-12 residual current", "Charging was stopped", "6.1 kWh")),
        ({"charge_state": "finished", "battery_pct": 80, "charge_limit_pct": 80, "charge_session_kwh": 28.4, "charge_session_minutes": 208}, "finished", ("Charge finished", "Target reached", "28.4 kWh", "3 h 28 min")),
        ({"charge_state": "unplugged", "charge_total_kwh": 4300.5}, "unplugged", ("No car plugged in", "Ready for a car", "Counter", "4,300.5 kWh")),
    ],
)  # fmt: skip
def test_every_state_says_what_is_going_on_and_what_is_known(client, data, state, words):
    vid, slug = electric(client)
    say(vid, **data)
    html = card(page(client, slug))
    assert f'data-st="{state}"' in html
    for word in words:
        assert word in html, (state, word)


def test_nothing_is_made_up_when_a_figure_is_not_known(client):
    vid, slug = electric(client)
    say(vid, charge_state="charging", charge_power_kw=7.4)  # no battery, no energy, no price
    html = card(page(client, slug))
    for word in ("Charged", "Cost", "Loss", "Range added", "Done at", "Target"):
        assert word not in html, word


def test_the_last_charge_is_told_while_no_car_is_plugged_in(client):
    vid, slug = electric(client)
    with db.tx() as conn:
        conn.execute(
            "INSERT INTO charge_sessions(vehicle_id, started, ended, start_pct, end_pct, max_kw, energy_kwh) VALUES(?,?,?,30,80,7.4,31.2)",
            (vid, "2026-11-27T17:42:00+00:00", "2026-11-27T21:22:00+00:00"),
        )
    say(vid, charge_state="unplugged")
    html = card(page(client, slug))
    assert "Last charge" in html and "31.2" in html and "3 h 40 min" in html


def test_what_a_wallbox_says_is_text_and_never_markup(client):
    vid, slug = electric(client)
    say(vid, charge_state="fault", charge_fault="<script>alert(1)</script> & <b>x</b>", charge_mode="<img src=x onerror=alert(1)>")
    html = card(page(client, slug))
    assert "<script>alert" not in html and "<img src=x" not in html and "<b>x</b>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html and "&lt;img src=x" in html


def test_the_entities_behind_the_values_can_be_looked_at(client):
    import json

    from tests.test_habridge import BRIDGE

    from carassistant import addons

    vid, slug = electric(client)
    say(vid, **CHARGING)
    with db.tx() as conn:
        source = conn.execute("SELECT id FROM sources LIMIT 1").fetchone()["id"]
        pk = addons.add(conn, vid, addons.parse_package(json.dumps(BRIDGE).encode()), source, None)
        conn.execute("UPDATE vehicle_addons SET active = 1 WHERE id = ?", (pk,))
        conn.executemany(
            "INSERT INTO ha_bindings(addon_pk, slot, entity, options) VALUES(?,?,?,'{}')",
            [(pk, "charge_state", "sensor.wallbox_status"), (pk, "charge_session_kwh", "sensor.wallbox_energy_session")],
        )
    html = card(page(client, slug))
    assert "Where the values come from · 2 entities" in html and "sensor.wallbox_status" in html and "State of the wallbox" in html


def test_the_tile_on_home_shows_the_power_while_charging_and_nothing_without_a_wallbox(client):
    vid, slug = electric(client)
    assert "wb-tile" not in client.get(f"/v/{slug}").text
    say(vid, **CHARGING)
    home = client.get(f"/v/{slug}").text
    assert "7.4 <small>kW</small>" in home and "50 % → 80 %" in home and "Done at" in home
    say(vid, charge_state="fault", charge_fault="E-12", charging=False)
    assert "E-12" in client.get(f"/v/{slug}").text


def test_the_tile_is_a_widget_the_person_can_hide_like_any_other(client):
    from carassistant import widgets

    assert "wallbox" in {w.key for w in widgets.REGISTRY}
    vid, slug = electric(client)
    say(vid, **CHARGING)
    with db.tx() as conn:
        layout = widgets.layout(conn, vid)
    assert any(w.key == "wallbox" and w.on for w in layout)
    edit = client.get(f"/v/{slug}").text
    assert 'data-w="wallbox"' in edit or "wallbox" in edit


def test_the_page_reads_only_the_card_again_when_the_values_change():
    from pathlib import Path

    from carassistant import web

    js = (Path(web.__file__).parent / "static" / "livepoll.js").read_text(encoding="utf-8")
    assert r"(\/security|\/e\/fuel)?" in js  # the Charging page is read again ...
    assert 'getElementById("wb")' in js and "never what somebody is typing" in js  # ... but only the card
