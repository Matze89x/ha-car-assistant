"""The data of a wallbox (Phase 1): the optional fields of the Plugin API, the interfaces of the Home Assistant plugin for them (a state word, the energy of
the charge, volts, amperes, the counter, a mode, a fault), the words of the wallboxes people have, and a simulated wallbox with every kind of entity
(tools/fake_ha.py) that plays its story through the real plugin: plug in, wait, charge, finish, unplug, a fault.

Nothing here talks to a real Home Assistant: the entities are those of the made-up one."""

import json

import pytest
from fake_ha import FakeHA, Wallbox
from tests.test_habridge import install, state, stored, world
from tests.test_web import create_vehicle

from carassistant import claims, connectors, db, ha, habridge, i18n
from carassistant import habridge_slots as cat

T = i18n.translator("en")
MAKE = {
    "e.charge_state": "sensor.wallbox_status",
    "e.charge_power_kw": "sensor.wallbox_power",
    "e.charge_session_kwh": "sensor.wallbox_energy_session",
    "e.charge_session_minutes": "sensor.wallbox_session_duration",
    "e.charge_voltage_v": "sensor.wallbox_voltage",
    "e.charge_current_a": "sensor.wallbox_current",
    "e.charge_phases": "select.wallbox_phases",
    "e.charge_current_limit_a": "number.wallbox_max_current",
    "e.charge_total_kwh": "sensor.wallbox_energy_total",
    "e.charge_temp_c": "sensor.wallbox_temperature",
    "e.charge_mode": "input_select.wallbox_mode",
    "e.charge_fault": "sensor.wallbox_fault",
}


@pytest.fixture()
def box(monkeypatch):
    """A made-up Home Assistant with a wallbox; ``box.states`` is what the plugin reads (``box.sync()`` after each step of the story)."""
    fake = FakeHA().start()
    wallbox = Wallbox(fake)

    class Box:
        wb = wallbox
        states: dict = {}

        def sync(self):
            self.states = json.loads(json.dumps(fake.states))

    result = Box()
    result.sync()
    monkeypatch.setattr(ha, "all_states", lambda seconds=4.0: dict(result.states))
    habridge._state.clear()
    habridge._watch = {}
    habridge.attach(None)
    yield result
    habridge.attach(None)
    habridge._state.clear()
    fake.stop()


def _bound(client, form=None):
    """A car with the Home Assistant plugin, the wallbox entities bound (``form`` changes the form)."""
    vid, pk = install(client)
    data = {**MAKE, **(form or {})}
    got = client.post(f"/v/{vid}/integrations/{pk}/bridge", data={k: v for k, v in data.items() if v is not None})
    assert got.status_code == 303 and "m=saved" in got.headers["location"], got.text[:300]
    return vid, pk


# ------------------------------------------------------------------ the Plugin API


def test_the_api_takes_the_wallbox_fields_and_keeps_them(client):
    vid = create_vehicle(client)
    body = {
        "charge_state": "charging", "charge_mode": "Solar", "charge_fault": "", "charge_session_kwh": 3.7, "charge_session_minutes": 30,
        "charge_voltage_v": 231.5, "charge_current_a": 10.7, "charge_phases": 3, "charge_current_limit_a": 16, "charge_total_kwh": 4214.1,
        "charge_temp_c": 34.3,
    }  # fmt: skip
    with db.tx() as conn:
        done = connectors.ingest(conn, vid, body, "test")
        assert set(done) == set(body) and set(done.values()) == {"stored"}
        data = connectors.snapshot(conn, vid)["data"]
    assert data["charge_state"] == "charging" and data["charge_mode"] == "Solar" and data["charge_session_kwh"] == 3.7
    assert "charge_fault" not in data  # nothing wrong: an empty text is stored, and not shown as a fault
    assert {"charge_state", "charge_mode", "charge_fault", "charge_total_kwh"} <= connectors.KNOWN


@pytest.mark.parametrize(
    "body",
    [
        {"charge_state": "bogus"},  # only the six words
        {"charge_state": 3},
        {"charge_mode": "x" * 41},
        {"charge_fault": "y" * 121},
        {"charge_mode": ["Solar"]},
        {"charge_session_kwh": -1},
        {"charge_voltage_v": 5000},
        {"charge_phases": 4},
        {"charge_current_a": "ten"},
        {"charge_temp_c": True},
    ],
)
def test_the_api_refuses_what_does_not_fit_a_wallbox(client, body):
    vid = create_vehicle(client)
    with db.tx() as conn, pytest.raises(connectors.ApiError) as err:
        connectors.ingest(conn, vid, body, "test")
    assert err.value.status == 422


def test_a_fault_is_taken_away_by_an_empty_text_and_texts_are_cleaned(client):
    vid = create_vehicle(client)
    with db.tx() as conn:
        connectors.ingest(conn, vid, {"charge_fault": "  E-12\tresidual\n current \x07 "}, "test")
        assert connectors.snapshot(conn, vid)["data"]["charge_fault"] == "E-12 residual current"
        connectors.ingest(conn, vid, {"charge_fault": ""}, "test")
        assert "charge_fault" not in connectors.snapshot(conn, vid)["data"]


# ------------------------------------------------------------------ the words of the wallboxes


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        # OCPP
        ("Available", "unplugged"), ("Preparing", "plugged"), ("Charging", "charging"), ("SuspendedEV", "waiting"), ("SuspendedEVSE", "waiting"),
        ("Finishing", "finished"), ("Faulted", "fault"),
        # go-e
        ("Idle", "unplugged"), ("WaitCar", "waiting"), ("Complete", "finished"), ("Error", "fault"),
        # Easee
        ("disconnected", "unplugged"), ("awaiting_start", "waiting"), ("ready_to_charge", "plugged"), ("completed", "finished"),
        # IEC 61851 and plain words
        ("A", "unplugged"), ("B", "plugged"), ("C", "charging"), ("E", "fault"), ("Not connected", "unplugged"), ("Paused", "waiting"),
        ("Charge-Complete", "finished"), ("plugged in", "plugged"),
        # German
        ("lädt", "charging"), ("Bereit", "plugged"), ("Fehler", "fault"),
    ],
)  # fmt: skip
def test_the_words_of_the_usual_wallboxes_are_understood(word, expected):
    reading = habridge.read(cat.BY_KEY["charge_state"], "sensor.s", {}, world(state("sensor.s", word)))
    assert reading.ok and reading.value == expected and reading.raw == word


def test_the_persons_own_words_come_first_and_an_unknown_word_says_so():
    slot = cat.BY_KEY["charge_state"]
    mine = {"words": {"charging": ["Zapfen", "Stromfluss"], "waiting": ["Charging"]}}  # even a usual word may be given another meaning
    assert habridge.read(slot, "sensor.s", mine, world(state("sensor.s", "zapfen"))).value == "charging"
    assert habridge.read(slot, "sensor.s", mine, world(state("sensor.s", "Charging"))).value == "waiting"
    bad = habridge.read(slot, "sensor.s", {}, world(state("sensor.s", "Zapfen")))
    assert not bad.ok and bad.problem == "words" and bad.detail == "Zapfen"
    assert "name it in the options" in habridge.describe(slot, bad, T)["text"]
    gone = habridge.read(slot, "sensor.s", {}, world(state("sensor.s", "unavailable")))
    assert not gone.ok and gone.problem == "unavailable"  # a wallbox that sleeps is no error


def test_a_helper_holds_the_word_just_as_well_as_a_sensor():
    for entity in ("input_select.mode", "select.mode", "input_text.mode", "text.mode"):
        assert habridge.read(cat.BY_KEY["charge_state"], entity, {}, world(state(entity, "Charging"))).value == "charging"
    reading = habridge.read(
        cat.BY_KEY["charge_mode"], "input_select.m", {}, world(state("input_select.m", "Solar", options=["Solar", "Fast"]))
    )
    assert reading.ok and reading.value == "Solar"


def test_a_fault_is_a_text_or_a_yes_no_and_nothing_wrong_is_an_empty_text():
    slot = cat.BY_KEY["charge_fault"]

    def text(value):
        return habridge.read(slot, "sensor.f", {}, world(state("sensor.f", value)))

    def flag(value, **opts):
        entity = state("binary_sensor.p", value, None, "problem", friendly_name="Wallbox problem")
        return habridge.read(slot, "binary_sensor.p", opts, world(entity))

    assert text("none").value == "" and text("No error").value == "" and text("OK").value == "" and text("0").value == ""
    assert text("E-12 residual current").value == "E-12 residual current"
    assert flag("on").value == "Wallbox problem" and flag("off").value == ""  # the name of the entity is what is wrong
    assert flag("on", invert=True).value == "" and flag("off", invert=True).value == "Wallbox problem"
    assert habridge.describe(slot, text("none"), T)["text"] == "No fault"
    assert habridge.describe(slot, text("E-12"), T)["text"] == "E-12"


# ------------------------------------------------------------------ the numbers of a wallbox


@pytest.mark.parametrize(
    ("slot", "unit", "value", "expected"),
    [
        ("charge_session_kwh", "Wh", 3700, 3.7), ("charge_session_kwh", "kWh", 3.7, 3.7), ("charge_total_kwh", "MWh", 4.2, 4200),
        ("charge_current_a", "mA", 10700, 10.7), ("charge_voltage_v", "V", 231, 231), ("charge_session_minutes", "h", 1.5, 90),
        ("charge_temp_c", "°F", 95, 35), ("charge_current_limit_a", "A", 16, 16),
    ],
)  # fmt: skip
def test_the_units_of_a_wallbox_are_turned_into_the_unit_of_the_slot(slot, unit, value, expected):
    reading = habridge.read(cat.BY_KEY[slot], "sensor.x", {}, world(state("sensor.x", str(value), unit)))
    assert reading.ok and reading.value == pytest.approx(expected, abs=0.01), reading
    wrong = habridge.read(cat.BY_KEY[slot], "sensor.x", {}, world(state("sensor.x", "5", "bananas")))
    assert not wrong.ok and wrong.problem == "unit"


def test_a_choice_and_a_helper_number_are_numbers_too():
    limit, phases = cat.BY_KEY["charge_current_limit_a"], cat.BY_KEY["charge_phases"]
    assert habridge.read(limit, "select.l", {}, world(state("select.l", "10", options=["6", "10", "16"]))).value == 10
    assert habridge.read(limit, "input_number.l", {}, world(state("input_number.l", "13.5", "A"))).value == 13.5
    assert habridge.read(limit, "number.l", {}, world(state("number.l", "16", "A"))).value == 16
    assert habridge.read(phases, "select.p", {}, world(state("select.p", "3"))).value == 3
    too_much = habridge.read(phases, "select.p", {}, world(state("select.p", "7")))
    assert not too_much.ok and too_much.problem == "range"  # the Plugin API would refuse it, so the row says so


# ------------------------------------------------------------------ one word makes charging and plugged


def _fresh(*pairs):
    return {key: habridge.Reading(ok=True, value=value, raw="x", at="2026-11-28T10:00:00+00:00") for key, value in pairs}


def test_a_state_word_also_says_whether_the_car_charges_and_is_plugged_in():
    seen = lambda word, bound=("charge_state",): habridge._charge_of_state(_fresh(("charge_state", word)), {k: {} for k in bound})  # noqa: E731
    assert (seen("charging")["charging"].value, seen("charging")["plugged"].value) == (True, True)
    assert (seen("waiting")["charging"].value, seen("waiting")["plugged"].value) == (False, True)
    assert (seen("finished")["charging"].value, seen("finished")["plugged"].value) == (False, True)
    assert (seen("unplugged")["charging"].value, seen("unplugged")["plugged"].value) == (False, False)
    assert seen("fault")["charging"].value is False and "plugged" not in seen("fault")  # a fault says nothing about the cable
    assert "charging" not in seen("charging", ("charge_state", "charging"))  # the person bound these themselves: their entity speaks
    assert "plugged" not in seen("charging", ("charge_state", "plugged"))
    assert habridge.fields_bound({"charge_state": {}}) == {
        "charge_state",
        "charging",
        "plugged",
    }  # ... and the plugin takes both interfaces
    assert habridge._charge_of_state({"charge_power_kw": habridge.Reading(ok=True, value=1.0)}, {}) == {
        "charge_power_kw": habridge.Reading(ok=True, value=1.0)
    }


# ------------------------------------------------------------------ the whole story through the real plugin


def test_a_wallbox_with_every_kind_of_entity_plays_its_story_through_the_plugin(client, box):
    vid, pk = _bound(client)
    wb = box.wb
    with db.tx() as conn:
        assert {"charge_state", "charging", "plugged", "charge_session_kwh", "charge_total_kwh"} <= set(claims.held_by(conn, vid, pk))

    def step(play, now):
        play()
        box.sync()
        assert habridge.tick(now) == 1
        return stored(vid)

    got = step(wb.unplug, 1000.0)
    assert got["charge_state"] == "unplugged" and got["plugged"] == "no" and got["charging"] == "no"
    assert got["charge_mode"] == "Solar" and got["charge_phases"] == "3" and got["charge_current_limit_a"] == "16"
    assert got["charge_voltage_v"] == "0" and got["charge_total_kwh"] == "4210.4"
    got = step(wb.plug_in, 1040.0)
    assert got["charge_state"] == "plugged" and got["plugged"] == "yes" and got["charging"] == "no" and got["charge_voltage_v"] == "230"
    got = step(wb.wait, 1080.0)
    assert got["charge_state"] == "waiting" and got["plugged"] == "yes" and got["charging"] == "no"
    got = step(lambda: wb.charge(7.4, 30), 1120.0)
    assert got["charge_state"] == "charging" and got["charging"] == "yes" and got["plugged"] == "yes"
    assert got["charge_power_kw"] == "7.4" and got["charge_session_kwh"] == "3.7" and got["charge_session_minutes"] == "30"
    assert got["charge_current_a"] == "10.7" and got["charge_total_kwh"] == "4214.1" and got["charge_temp_c"] == "34.4"
    got = step(lambda: wb.charge(7.4, 30), 1160.0)
    assert got["charge_session_kwh"] == "7.4" and got["charge_total_kwh"] == "4217.8"  # the counter and the session grow together
    got = step(wb.finish, 1200.0)
    assert got["charge_state"] == "finished" and got["charging"] == "no" and got["plugged"] == "yes" and got["charge_power_kw"] == "0"
    assert got["charge_session_kwh"] == "7.4"  # what was charged stays until the next car
    got = step(wb.fault, 1240.0)
    assert (
        got["charge_state"] == "fault" and got["charge_fault"] == "E-12 residual current" and got["plugged"] == "yes"
    )  # (the cable: as it was)
    got = step(wb.unplug, 1280.0)
    assert (
        got["charge_state"] == "unplugged" and got["plugged"] == "no" and got["charge_fault"] == ""
    )  # the fault is gone with the entity's "none"


def test_a_sleeping_wallbox_keeps_the_last_values_and_the_problem_is_said_once(client, box):
    vid, _pk = _bound(client)
    box.wb.plug_in()
    box.wb.charge(7.4, 12)
    box.sync()
    habridge.tick(1000.0)
    assert stored(vid)["charge_state"] == "charging"
    for entity in ("sensor.wallbox_status", "sensor.wallbox_power", "sensor.wallbox_energy_session"):
        box.states[entity]["state"] = "unavailable"
    habridge.tick(1031.0)
    got = stored(vid)
    assert got["charge_state"] == "charging" and got["charge_session_kwh"] == "1.48"  # no value now: the last one stays
    box.states["sensor.wallbox_status"]["state"] = "Zapfen"  # a word nobody knows: said in the log, once, in plain words
    habridge.tick(1062.0)
    habridge.tick(1093.0)
    with db.tx() as conn:
        lines = [r["message"] for r in conn.execute("SELECT message FROM vehicle_logs WHERE vehicle_id = ? ORDER BY id", (vid,))]
    said = [line for line in lines if "charge_state" in line and "Zapfen" in line]
    assert len(said) == 1 and "name it in the options" in said[0]


def test_the_persons_own_state_and_charging_rows_win_over_the_derived_ones(client, box):
    vid, _pk = _bound(client, {"e.charging": "binary_sensor.wallbox_charging", "e.plugged": "binary_sensor.wallbox_cable"})
    box.wb.plug_in()
    box.wb.wait()
    box.sync()
    habridge.tick(1000.0)
    got = stored(vid)
    assert got["charge_state"] == "waiting" and got["charging"] == "no" and got["plugged"] == "yes"  # from their own binary sensors
    box.wb.charge(7.4, 6)
    box.sync()
    habridge.tick(1031.0)
    assert stored(vid)["charging"] == "yes"


# ------------------------------------------------------------------ the page


def test_the_page_offers_the_wallbox_group_with_every_row_and_takes_the_words(client, box):
    vid, pk = install(client)
    page = client.get(f"/v/{vid}/integrations/{pk}/settings").text
    assert (
        'id="hb-wallbox"' in page
        and "State of the wallbox" in page
        and "Energy of this charge" in page
        and "Counter of the wallbox" in page
    )
    for key in (k.removeprefix("e.") for k in MAKE):
        assert f'data-hb-slot="{key}"' in page, key
    assert "Words for: Charging" in page and "Words for: No car" in page  # the words of THIS wallbox, under the options of the state row
    got = client.post(
        f"/v/{vid}/integrations/{pk}/bridge",
        data={
            "e.charge_state": "sensor.wallbox_status",
            "o.charge_state.w_charging": "Zapfen, Stromfluss",
            "o.charge_state.w_fault": "Kaputt",
        },
    )
    assert got.status_code == 303
    with db.tx() as conn:
        assert habridge.bindings(conn, pk)["charge_state"]["options"] == {
            "words": {"charging": ["Zapfen", "Stromfluss"], "fault": ["Kaputt"]}
        }
    again = client.get(f"/v/{vid}/integrations/{pk}/settings").text
    assert 'value="Zapfen, Stromfluss"' in again and 'value="Kaputt"' in again
    too_many = client.post(
        f"/v/{vid}/integrations/{pk}/bridge",
        data={"e.charge_state": "sensor.wallbox_status", "o.charge_state.w_charging": ", ".join(f"w{n}" for n in range(13))},
    )
    assert too_many.status_code == 400 and "At most 12 words for a state" in too_many.text  # nothing is saved, the page says why


def test_the_words_survive_a_backup_and_a_file_that_is_not_ours_is_cleaned():
    kept = habridge.clean_stored("charge_state", "sensor.s", {"words": {"charging": ["Zapfen"], "nonsense": ["x"], "fault": "no list"}})
    assert kept == {"entity": "sensor.s", "options": {"words": {"charging": ["Zapfen"]}}}
    assert habridge.clean_stored("charge_state", "sensor.s", json.dumps({"words": {"waiting": ["a", "b"]}}))["options"] == {
        "words": {"waiting": ["a", "b"]}
    }
    assert (
        habridge.clean_stored("charge_state", "sensor.s", {"words": {"charging": ["x" * 41]}})["options"] == {}
    )  # too long: the options are dropped, not the row


def test_the_entities_that_fit_are_offered_first_for_each_interface(box):
    states = box.states

    def offered(key, query=""):
        return [e["id"] for e in habridge.suggest(cat.BY_KEY[key], query, False, states)]

    word = offered("charge_state")
    assert {"sensor.wallbox_status", "input_select.wallbox_mode", "select.wallbox_phases"} <= set(
        word
    )  # sensors and helpers that hold a word
    assert "binary_sensor.wallbox_cable" not in word and "switch.wallbox_charging_allowed" not in word
    assert (
        offered("charge_session_kwh")[0] == "sensor.wallbox_energy_session"
        or "sensor.wallbox_energy_session" in offered("charge_session_kwh")[:2]
    )  # device class energy
    assert {"number.wallbox_max_current", "select.wallbox_phases", "input_number.wallbox_home_price"} <= set(
        offered("charge_current_limit_a")
    )
    assert "sensor.wallbox_fault" in offered("charge_fault") and "binary_sensor.wallbox_problem" in offered("charge_fault")
    assert offered("charge_voltage_v")[0] == "sensor.wallbox_voltage"
    assert "sensor.wallbox_status" in offered("charge_mode", "wallbox")
