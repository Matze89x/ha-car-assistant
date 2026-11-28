"""The buttons of the wallbox card (carassistant/wallbox_control.py, wallbox_web.py): pause and resume, start, acknowledge a fault, the current limit, the mode -
through the services of Home Assistant, played against the made-up Home Assistant with its made-up wallbox (real HTTP, real client).

What is checked is as much what is NOT done: a command goes only to an entity the administrator bound for this car, with a service of a fixed table and a value that
fits; a request never names an entity or a service."""

import json

import pytest
from fake_ha import FakeHA, Wallbox
from fastapi.testclient import TestClient
from tests.test_habridge import install
from tests.test_web import create_vehicle

from carassistant import accounts, auth_web, db, ha, habridge, wallbox_control, web

BASE = {
    "e.charge_state": "sensor.wallbox_status",
    "e.charge_power_kw": "sensor.wallbox_power",
    "e.charge_current_limit_a": "number.wallbox_max_current",
    "e.charge_mode": "input_select.wallbox_mode",
    "e.charge_session_kwh": "sensor.wallbox_energy_session",
}
CONTROLS = {
    "e.wb_allow": "switch.wallbox_charging_allowed",
    "e.wb_start": "button.wallbox_start",
    "e.wb_stop": "button.wallbox_stop",
    "e.wb_ack": "button.wallbox_acknowledge",
}


@pytest.fixture()
def home(monkeypatch):
    """A made-up Home Assistant with a wallbox; the app talks to it for real (``ha.call_service`` and ``ha.all_states`` over HTTP)."""
    fake = FakeHA().start()
    box = Wallbox(fake)
    monkeypatch.setenv("CARASSISTANT_HA_API", fake.api)
    monkeypatch.setenv("SUPERVISOR_TOKEN", fake.token)
    ha._cache.clear()
    wallbox_control._recent.clear()
    habridge._state.clear()
    habridge._watch = {}
    habridge.attach(None)

    class Home:
        pass

    result = Home()
    result.fake, result.box = fake, box
    yield result
    habridge.attach(None)
    habridge._state.clear()
    fake.stop()


def car(client, home, **form):
    """A car with the Home Assistant plugin bound to the wallbox (``form`` adds or changes rows); returns ``(vid, slug, pk)``."""
    vid, pk = install(client)
    with db.tx() as conn:
        conn.execute("UPDATE vehicles SET fuel_type = 'electric', battery_kwh = 60 WHERE id = ?", (vid,))
        slug = conn.execute("SELECT slug FROM vehicles WHERE id = ?", (vid,)).fetchone()["slug"]
        conn.execute("UPDATE vehicle_addons SET active = 1 WHERE id = ?", (pk,))
    data = {**BASE, **CONTROLS, **form}
    got = client.post(f"/v/{vid}/integrations/{pk}/bridge", data={k: v for k, v in data.items() if v is not None})
    assert got.status_code == 303, got.text[:300]
    return vid, slug, pk


def tick(home, now):
    """The plugin reads the wallbox once (what is on the page comes from there)."""
    ha._cache.clear()
    assert habridge.tick(now) >= 1


def press(client, vid, action, **form):
    return client.post(f"/v/{vid}/wallbox/{action}", data=form)


def message(response) -> str:
    return response.headers["location"].split("m=")[-1].split("#")[0]


def card(client, slug) -> str:
    import re

    html = client.get(f"/v/{slug}/e/fuel").text
    found = re.search(r'<section class="card wb".*?</section>', html, re.S)
    return found.group(0) if found else ""


def log_of(vid):
    with db.tx() as conn:
        return [
            (r["level"], r["message"])
            for r in conn.execute("SELECT level, message FROM vehicle_logs WHERE vehicle_id = ? ORDER BY id", (vid,))
        ]


# ------------------------------------------------------------------ what the card offers


def test_the_buttons_follow_the_state_and_what_the_entities_can_do(client, home):
    _vid, slug, _pk = car(client, home)
    box = home.box
    box.plug_in()
    box.wait()
    tick(home, 1000.0)
    html = card(client, slug)
    assert "Charge now" in html and f'action="/v/{slug}/wallbox/start"' in html  # waiting: start
    assert "Max current" in html and 'name="delta"' in html and "16 A" in html  # the limit that is set, with its two buttons
    assert 'id="wb-mode"' in html and "Solar" in html and "Fast" in html  # the mode: the options of the helper
    box.charge(7.4, 5)
    tick(home, 1100.0)
    html = card(client, slug)
    assert "Pause" in html and "Charge now" not in html and 'wallbox/pause"' in html
    box.fault()
    tick(home, 1200.0)
    assert "Acknowledge the fault" in card(client, slug)
    box.unplug()
    tick(home, 1300.0)
    html = card(client, slug)
    assert (
        "wb-ctl" in html and 'wallbox/pause"' not in html and "Charge now" not in html and "Acknowledge the fault" not in html
    )  # no car: no main button, the limit stays


def test_nothing_is_offered_that_no_entity_can_do(client, home):
    _vid, slug, _pk = car(
        client,
        home,
        **{
            "e.wb_allow": None,
            "e.wb_start": None,
            "e.wb_stop": None,
            "e.wb_ack": None,
            "e.charge_current_limit_a": None,
            "e.charge_mode": None,
        },
    )
    home.box.plug_in()
    home.box.charge(7.4, 5)
    tick(home, 1000.0)
    html = card(client, slug)
    assert "wb-ctl" not in html and "<form" not in html  # a card that only shows
    _vid2, slug2, _pk2 = car(
        client, home, **{"e.wb_stop": None, "e.wb_ack": None, "e.charge_mode": None, "e.charge_current_limit_a": "sensor.wallbox_power"}
    )
    tick(home, 1100.0)
    assert "wb-step" not in card(client, slug2)  # a sensor cannot be set: no stepper


def test_without_home_assistant_no_button_is_shown_that_could_not_work(client, home):
    _vid, slug, _pk = car(client, home)
    home.box.plug_in()
    home.box.charge(7.4, 5)
    tick(home, 1000.0)
    assert "wb-ctl" in card(client, slug)
    home.fake.rest_down = True
    ha._cache.clear()
    html = card(client, slug)
    assert html and "wb-ctl" not in html  # the card is there (the values are known), the buttons are not


# ------------------------------------------------------------------ what a press does


def test_pause_and_resume_switch_the_allowed_entity_and_the_wallbox_follows(client, home):
    vid, slug, _pk = car(client, home, **{"e.wb_stop": None})
    box = home.box
    box.plug_in()
    box.charge(7.4, 5)
    tick(home, 1000.0)
    got = press(client, vid, "pause")
    assert got.status_code == 303 and message(got) == "wb.cmd.ok"
    assert home.fake.calls[-1] == ("switch", "turn_off", {"entity_id": "switch.wallbox_charging_allowed"})
    tick(home, 1050.0)
    assert "Resume" in card(client, slug) and 'data-st="waiting"' in card(client, slug)  # the wallbox held back: the card says so
    got = press(client, vid, "resume")
    assert message(got) == "wb.cmd.ok" and home.fake.calls[-1] == ("switch", "turn_on", {"entity_id": "switch.wallbox_charging_allowed"})
    tick(home, 1100.0)
    assert 'data-st="charging"' in card(client, slug)
    assert any(
        "command pause: switch.turn_off switch.wallbox_charging_allowed" in text for _level, text in log_of(vid)
    )  # every command leaves a line


def test_start_stop_and_acknowledge_press_their_buttons(client, home):
    vid, slug, _pk = car(client, home)
    box = home.box
    box.plug_in()
    box.wait()
    tick(home, 1000.0)
    press(client, vid, "start")
    assert home.fake.calls[-1] == ("button", "press", {"entity_id": "button.wallbox_start"})
    tick(home, 1050.0)
    assert 'data-st="charging"' in card(client, slug)
    press(client, vid, "pause")
    assert home.fake.calls[-1] == ("button", "press", {"entity_id": "button.wallbox_stop"})  # a button of its own wins over the switch
    box.fault()
    tick(home, 1100.0)
    press(client, vid, "ack")
    assert home.fake.calls[-1] == ("button", "press", {"entity_id": "button.wallbox_acknowledge"})
    tick(home, 1150.0)
    assert 'data-st="plugged"' in card(client, slug) and "E-12" not in card(client, slug)


def test_a_script_and_a_switch_do_what_their_kind_does(client, home):
    home.fake.set("script.start_charging", "off", friendly_name="Start charging")
    home.fake.set("switch.start_plug", "off", friendly_name="Start plug")
    vid, _slug, _pk = car(client, home, **{"e.wb_start": "script.start_charging", "e.wb_stop": "switch.start_plug", "e.wb_allow": None})
    home.box.plug_in()
    home.box.wait()
    tick(home, 1000.0)
    press(client, vid, "start")
    assert home.fake.calls[-1] == ("script", "turn_on", {"entity_id": "script.start_charging"})  # a script runs
    press(client, vid, "pause")
    assert home.fake.calls[-1] == ("switch", "turn_off", {"entity_id": "switch.start_plug"})  # a switch for stopping is turned off


def test_the_limit_goes_up_and_down_by_its_step_within_what_the_entity_takes(client, home):
    vid, slug, _pk = car(client, home)
    home.box.plug_in()
    tick(home, 1000.0)
    assert message(press(client, vid, "limit", delta="-1")) == "wb.cmd.ok"
    assert home.fake.calls[-1] == ("number", "set_value", {"entity_id": "number.wallbox_max_current", "value": 15.0})
    tick(home, 1050.0)
    assert "15 A" in card(client, slug)
    assert message(press(client, vid, "limit", value="6")) == "wb.cmd.ok" and home.fake.calls[-1][2]["value"] == 6.0
    tick(home, 1100.0)
    assert message(press(client, vid, "limit", delta="-1")) == "wb.cmd.err_end"  # already at the lowest: nothing is sent
    n = len(home.fake.calls)
    for bad in ({"value": "99"}, {"value": "5"}, {"value": "abc"}, {"delta": "3"}, {"delta": "x"}, {}):
        assert message(press(client, vid, "limit", **bad)) == "wb.cmd.err_value", bad
    assert len(home.fake.calls) == n  # not one of them reached Home Assistant


def test_the_limit_of_a_choice_takes_one_of_its_options(client, home):
    home.fake.set("select.wallbox_current", "10", friendly_name="Current", options=["6", "10", "13", "16"])
    vid, _slug, _pk = car(client, home, **{"e.charge_current_limit_a": "select.wallbox_current"})
    home.box.plug_in()
    tick(home, 1000.0)
    assert message(press(client, vid, "limit", delta="1")) == "wb.cmd.ok"
    assert home.fake.calls[-1] == ("select", "select_option", {"entity_id": "select.wallbox_current", "option": "13"})
    assert message(press(client, vid, "limit", value="11")) == "wb.cmd.err_value"  # 11 is no option


def test_the_mode_takes_one_of_the_options_of_the_helper_and_nothing_else(client, home):
    vid, slug, _pk = car(client, home)
    home.box.plug_in()
    tick(home, 1000.0)
    assert message(press(client, vid, "mode", option="Fast")) == "wb.cmd.ok"
    assert home.fake.calls[-1] == ("input_select", "select_option", {"entity_id": "input_select.wallbox_mode", "option": "Fast"})
    tick(home, 1050.0)
    assert "Mode: Fast" in card(client, slug)
    n = len(home.fake.calls)
    assert (
        message(press(client, vid, "mode", option="Turbo")) == "wb.cmd.err_value"
        and message(press(client, vid, "mode")) == "wb.cmd.err_value"
    )
    assert len(home.fake.calls) == n


# ------------------------------------------------------------------ what is never done


def test_a_request_cannot_name_an_entity_or_a_service(client, home):
    vid, _slug, _pk = car(client, home)
    home.box.plug_in()
    tick(home, 1000.0)
    n = len(home.fake.calls)
    for action in ("lock", "unlock", "turn_off", "../start", "start/../../x", "", "LIMIT"):
        got = client.post(f"/v/{vid}/wallbox/{action}", data={"entity_id": "lock.front_door", "service": "unlock", "domain": "lock"})
        assert got.status_code in (303, 404, 405), (action, got.status_code)
        if got.status_code == 303:
            assert message(got) == "wb.cmd.err_what", action
    press(client, vid, "mode", option="Fast", entity_id="lock.front_door")  # a field that names an entity is simply not read
    assert [c for c in home.fake.calls[n:] if c[2].get("entity_id") != "input_select.wallbox_mode"] == []


def test_a_car_without_bound_entities_sends_nothing(client, home):
    vid = create_vehicle(client, "Plain Car")
    n = len(home.fake.calls)
    for action in ("pause", "resume", "start", "stop", "ack", "limit", "mode"):
        assert message(press(client, vid, action, delta="1", option="Fast")) == "wb.cmd.err_none", action
    assert len(home.fake.calls) == n


def test_an_entity_that_is_not_there_any_more_is_not_called(client, home):
    vid, _slug, _pk = car(client, home)
    home.box.plug_in()
    home.box.wait()
    tick(home, 1000.0)
    home.fake.remove("switch.wallbox_charging_allowed")
    home.fake.remove("button.wallbox_start")
    ha._cache.clear()
    n = len(home.fake.calls)
    assert message(press(client, vid, "start")) == "wb.cmd.err_none" and len(home.fake.calls) == n


def test_home_assistant_that_refuses_or_cannot_be_reached_is_said_and_logged_not_hidden(client, home):
    vid, _slug, _pk = car(client, home)
    home.box.plug_in()
    home.box.wait()
    tick(home, 1000.0)
    home.fake.refuse_services = True
    assert message(press(client, vid, "start")) == "wb.cmd.err_ha"
    assert any(level == "warn" and "Home Assistant did not take it" in text for level, text in log_of(vid))
    home.fake.rest_down = True
    ha._cache.clear()
    assert message(press(client, vid, "start")) == "wb.cmd.err_ha"  # no states to judge with: asked for, answered, said


def test_a_car_takes_only_a_few_commands_a_minute(client, home, monkeypatch):
    vid, _slug, _pk = car(client, home)
    home.box.plug_in()
    tick(home, 1000.0)
    results = [message(press(client, vid, "limit", value="10")) for _ in range(wallbox_control.MAX_PER_MINUTE + 3)]
    assert results[: wallbox_control.MAX_PER_MINUTE] == ["wb.cmd.ok"] * wallbox_control.MAX_PER_MINUTE
    assert results[wallbox_control.MAX_PER_MINUTE :] == ["wb.cmd.err_often"] * 3
    assert len([c for c in home.fake.calls if c[0] == "number"]) == wallbox_control.MAX_PER_MINUTE  # the rest never left the app
    other = create_vehicle(client, "Other Car")
    assert (
        message(press(client, other, "limit", value="10")) == "wb.cmd.err_none"
    )  # (another car is judged by its own entities, and has none)


def test_only_administrators_press_the_buttons(client, home, monkeypatch):
    vid, _slug, _pk = car(client, home)
    home.box.plug_in()
    home.box.wait()
    tick(home, 1000.0)
    with db.tx() as conn:
        admin = accounts.create_session(conn, accounts.create_user(conn, "owner", "a-long-pass-123", "Owner", True))
        guest = accounts.create_session(conn, accounts.create_user(conn, "guest", "a-long-pass-123", "Guest", False))
    monkeypatch.delenv("CARASSISTANT_DEV", raising=False)
    outside = TestClient(web.app, base_url="https://car.example.com", follow_redirects=False, headers={"Origin": "https://car.example.com"})
    n = len(home.fake.calls)
    refused = outside.post(f"/v/{vid}/wallbox/start", cookies={auth_web.COOKIE: guest})
    assert refused.status_code == 303 and "acct.need_admin" in refused.headers["location"] and len(home.fake.calls) == n
    anon = outside.post(f"/v/{vid}/wallbox/start")
    assert anon.status_code in (303, 401, 403) and len(home.fake.calls) == n
    allowed = outside.post(f"/v/{vid}/wallbox/start", cookies={auth_web.COOKIE: admin})
    assert allowed.status_code == 303 and "wb.cmd.ok" in allowed.headers["location"] and home.fake.calls[-1][1] == "press"


def test_the_command_rows_of_the_plugin_page_say_whether_the_entity_is_there_and_fits(client, home):
    vid, _slug, pk = car(client, home, **{"e.wb_ack": "sensor.wallbox_power"})
    page = client.get(f"/v/{vid}/integrations/{pk}/settings").text
    assert 'data-hb-slot="wb_allow"' in page and "Charging allowed (switch)" in page and "Acknowledge a fault (button)" in page
    states = json.loads(json.dumps(home.fake.states))
    ok = habridge.read(habridge.cat.BY_KEY["wb_allow"], "switch.wallbox_charging_allowed", {}, states)
    assert ok.ok and ok.value is None  # it reads nothing: it is there
    wrong = habridge.read(habridge.cat.BY_KEY["wb_ack"], "sensor.wallbox_power", {}, states)
    assert not wrong.ok and wrong.problem == "domain" and wrong.detail == "sensor"
    assert habridge.fields_bound({"wb_allow": {}}) == set()  # a command takes no interface of the car


def test_a_command_row_delivers_nothing_to_the_plugin_api(client, home):
    vid, _slug, _pk = car(client, home)
    home.box.plug_in()
    tick(home, 1000.0)
    with db.tx() as conn:
        values = {r["key"] for r in conn.execute("SELECT key FROM live WHERE vehicle_id = ?", (vid,))}
        held = {r["field"] for r in conn.execute("SELECT field FROM field_claims WHERE vehicle_id = ?", (vid,))}
    assert not any(key.startswith("wb_") for key in values) and "" not in held and not any(field.startswith("wb_") for field in held)
