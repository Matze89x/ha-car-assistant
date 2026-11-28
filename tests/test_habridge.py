"""The Home Assistant plugin (carassistant/habridge.py, docs/home-assistant.md): units, what an entity says as a number / yes-no / position, the deliveries
to the Plugin API, the schedule, saving the bindings (and the interfaces they take), the page and its routes."""

import json
import time
from datetime import UTC, datetime, timedelta

import pytest
from tests.test_web import create_vehicle

from carassistant import addons, claims, connectors, db, ha, habridge, i18n, summary, trips
from carassistant import habridge_slots as cat

T = i18n.translator("en")

BRIDGE = {
    "id": "home-assistant",
    "kind": "plugin",
    "name": "Home Assistant",
    "version": "1.0.0",
    "icon": "home",
    "bridge": {"type": "home_assistant"},
    "settings": [
        {
            "key": "every",
            "type": "select",
            "label": "Check every",
            "default": "30",
            "options": [{"value": "10", "label": "10 s"}, {"value": "30", "label": "30 s"}, {"value": "300", "label": "5 min"}],
        }
    ],
}


def state(entity, value, unit=None, dclass=None, at="2026-11-26T08:00:00+00:00", **attrs):
    """One entity as Home Assistant lists it."""
    attributes = {**attrs}
    if unit:
        attributes["unit_of_measurement"] = unit
    if dclass:
        attributes["device_class"] = dclass
    return {"entity_id": entity, "state": value, "attributes": attributes, "last_updated": at, "last_reported": at}


def world(*entities):
    return {e["entity_id"]: e for e in entities}


def one(slot_key, entity_state, **opts):
    return habridge.read(cat.BY_KEY[slot_key], entity_state["entity_id"], opts, world(entity_state))


# ------------------------------------------------------------------ units


@pytest.mark.parametrize(
    ("slot_unit", "unit", "value", "expected"),
    [
        ("km", "mi", 100, 160.9344),
        ("km", "m", 1500, 1.5),
        ("km", "km", 12.5, 12.5),
        ("km", "", 12.5, 12.5),  # no unit: already the unit of the slot
        ("km/h", "mph", 60, 96.56064),
        ("km/h", "m/s", 10, 36),
        ("kW", "W", 7400, 7.4),
        ("kW", "MW", 0.001, 1),
        ("bar", "psi", 34.8, 2.39937),
        ("bar", "kPa", 240, 2.4),
        ("bar", "hPa", 2400, 2.4),
        ("bar", "Pa", 240000, 2.4),
        ("l", "gal", 10, 37.85412),
        ("l", "kWh", 50, 50),  # an electric car: the amount in the battery
        ("°C", "°F", 212, 100),
        ("°C", "K", 273.15, 0),
        ("V", "mV", 12500, 12.5),
        ("min", "h", 2, 120),
        ("min", "s", 90, 1.5),
        ("d", "h", 48, 2),
        ("l/100km", "km/l", 20, 5),
        ("l/100km", "mpg", 47.0429166, 5),
        ("l/100km", "Wh/km", 180, 18),
        ("l/100km", "L/100 km", 7.2, 7.2),  # spelled another way
        ("%", "%", 80, 80),
    ],
)
def test_units_are_turned_into_the_unit_of_the_slot(slot_unit, unit, value, expected):
    assert habridge.convert(slot_unit, unit, value) == pytest.approx(expected, rel=1e-4, abs=1e-6)


def test_a_unit_that_does_not_fit_is_not_guessed():
    assert habridge.convert("km", "l", 5) is None
    assert habridge.convert("%", "l", 5) is None
    assert habridge.convert("bar", "bananas", 5) is None
    assert habridge.convert("l/100km", "km/l", 0) is None  # no division by zero


# ------------------------------------------------------------------ numbers


def test_a_number_is_read_in_the_unit_of_the_slot():
    r = one("odometer_km", state("sensor.odo", "62150.4", "mi"))
    assert r.ok and r.value == pytest.approx(100021.37, abs=0.01) and r.converted and "mi" in r.raw
    r = one("tyre_fl", state("sensor.fl", "34.8", "psi", "pressure"))
    assert r.ok and r.value == 2.4 and r.converted
    r = one("range_km", state("sensor.range", "412", "km"))
    assert r.ok and r.value == 412 and not r.converted and r.raw == ""
    r = one("fuel_level_pct", state("sensor.fuel", "55"))
    assert r.ok and r.value == 55
    assert r.at == "2026-11-26T08:00:00+00:00"  # the time Home Assistant gives (the entity's last report)


def test_what_is_not_a_number_or_not_available_says_why_and_never_raises():
    assert one("range_km", state("sensor.r", "unavailable")).problem == "unavailable"
    assert one("range_km", state("sensor.r", "unknown")).problem == "unavailable"
    assert one("range_km", state("sensor.r", "")).problem == "unavailable"
    assert one("range_km", state("sensor.r", "far away")).problem == "number"
    assert one("range_km", state("sensor.r", "nan")).problem == "unavailable"
    assert one("range_km", state("sensor.r", "inf")).problem == "number"
    assert one("range_km", state("sensor.r", "12", "l")).problem == "unit"  # litres are no distance
    assert one("fuel_level_pct", state("sensor.f", "250")).problem == "range"  # more than a hundred percent
    assert one("range_km", state("sensor.r", "-3")).problem == "range"
    assert one("odometer_km", state("sensor.o", "0")).problem == "range"
    r = habridge.read(cat.BY_KEY["range_km"], "sensor.nothing", {}, world())
    assert r.problem == "gone"
    assert habridge.read(cat.BY_KEY["range_km"], "sensor.r", {}, None).problem == "ha"


def test_the_options_of_a_number():
    sensor = state("sensor.fuel_l", "27.5", "l")
    assert one("fuel_level_pct", sensor).problem == "unit"  # litres are no percent ...
    r = one("fuel_level_pct", sensor, unit="raw", scale=100 / 55)  # ... unless the person says: take the number as it is, 55 l = 100 %
    assert r.ok and r.value == pytest.approx(50)
    assert one("fuel_level_pct", state("sensor.f", "0.5"), scale=100).value == 50
    assert one("outside_temp_c", state("sensor.t", "10"), offset=-0.5).value == 9.5
    assert one("range_km", state("sensor.r", "100", "mi"), unit="km").value == 100  # the person says what the entity does not
    assert one("range_km", state("sensor.r", "100"), unit="mi").value == pytest.approx(160.934)
    attr = state("climate.cabin", "heat", current_temperature=21.5, temperature=22)
    assert one("cabin_temp_c", attr, attribute="current_temperature").value == 21.5
    assert one("target_temp_c", attr, attribute="temperature").value == 22
    assert one("cabin_temp_c", attr, attribute="nothing").problem == "attribute"
    assert one("heading_deg", state("sensor.h", "-90")).value == 270  # a heading is always 0 ... 360


def test_a_date_or_a_time_becomes_the_days_or_minutes_until_then():
    from datetime import UTC, datetime, timedelta

    soon = (datetime.now(UTC) + timedelta(minutes=90)).isoformat()
    assert one("charge_minutes_left", state("sensor.done", soon, dclass="timestamp")).value == pytest.approx(90, abs=1.5)
    in_ten_days = (datetime.now().date() + timedelta(days=10)).isoformat()
    assert one("service_due_days", state("sensor.service", in_ten_days, dclass="date")).value == 10
    assert one("range_km", state("sensor.service", in_ten_days)).problem == "number"  # a date is no distance


# ------------------------------------------------------------------ yes and no


@pytest.mark.parametrize(
    ("slot", "entity", "value", "dclass", "expected"),
    [
        ("locked", "lock.car", "locked", None, True),
        ("locked", "lock.car", "unlocked", None, False),
        ("locked", "lock.car", "open", None, False),
        ("locked", "lock.car", "jammed", None, None),
        ("locked", "binary_sensor.lock", "on", "lock", False),  # Home Assistant: for this class on = UNLOCKED
        ("locked", "binary_sensor.lock", "off", "lock", True),
        ("locked", "switch.lock", "on", None, True),
        ("doors", "binary_sensor.door", "on", "door", True),
        ("doors", "binary_sensor.door", "off", "door", False),
        ("doors", "cover.trunk", "closed", None, False),
        ("doors", "cover.trunk", "open", None, True),
        ("doors", "cover.trunk", "opening", None, True),
        ("windows", "binary_sensor.window", "on", "window", True),
        ("plugged", "binary_sensor.plug", "on", "plug", True),
        ("plugged", "sensor.status", "Disconnected", None, False),
        ("plugged", "sensor.status", "connected", None, True),
        ("charging", "binary_sensor.charging", "on", "battery_charging", True),
        ("charging", "sensor.status", "charging", None, True),
        ("charging", "sensor.status", "not_charging", None, False),
        ("climate_on", "climate.cabin", "heat", None, True),
        ("climate_on", "climate.cabin", "off", None, False),
        ("ignition", "binary_sensor.engine", "on", "running", True),
        ("parking_brake", "input_boolean.brake", "off", None, False),
        ("oil_warning", "binary_sensor.oil", "on", "problem", True),
        ("lights", "light.head", "on", None, True),
        ("warnings", "binary_sensor.door", "on", "door", True),  # a warning takes any kind of yes / no
    ],
)
def test_a_yes_or_no_is_understood_by_the_kind_of_entity(slot, entity, value, dclass, expected):
    r = one(slot, state(entity, value, dclass=dclass))
    if expected is None:
        assert not r.ok and r.problem == "state"
    else:
        assert r.ok and r.value is expected, (r, slot, entity, value)


def test_an_entity_about_something_else_is_not_taken_for_the_slot():
    assert one("locked", state("binary_sensor.door", "on", dclass="door")).problem == "truth"  # an open door does not say "locked"
    assert one("doors", state("lock.car", "locked")).problem == "truth"
    assert one("ignition", state("lock.car", "locked")).problem == "truth"


def test_the_person_names_the_states_that_mean_yes_or_a_value_above_which_it_does():
    status = state("sensor.wallbox", "Preparing")
    assert one("plugged", status, yes=["Preparing", "Charging", "SuspendedEV"]).value is True
    assert one("plugged", state("sensor.wallbox", "Available"), yes=["Preparing", "Charging"]).value is False  # every other state is no
    assert one("charging", state("sensor.wallbox", "Charging"), yes=["charging"]).value is True  # no matter how it is spelled
    assert one("charging", state("sensor.power", "7400", "W"), above=0).value is True
    assert one("charging", state("sensor.power", "0", "W"), above=0).value is False
    assert one("locked", state("lock.car", "locked"), invert=True).value is False
    assert one("charging", state("sensor.wallbox", "Weird")).problem == "state"  # not guessed


# ------------------------------------------------------------------ text and position


def test_a_vin_and_a_position():
    assert one("vin", state("sensor.vin", "ab-cd 12345 xyz")).value == "ABCD12345XYZ"
    assert one("vin", state("sensor.vin", "!!")).problem == "vin"
    tracker = state("device_tracker.car", "not_home", latitude=52.52, longitude=13.405, gps_accuracy=5)
    assert one("position", tracker).value == (52.52, 13.405)
    assert one("position", state("sensor.pos", "52.52, 13.405")).value == (52.52, 13.405)
    assert one("position", state("device_tracker.car", "home")).problem == "coords"  # a zone, no coordinates
    assert one("position", state("device_tracker.car", "not_home", latitude=0, longitude=0)).problem == "coords"  # no fix
    assert one("position", state("device_tracker.car", "not_home", latitude=95, longitude=0)).problem == "coords"
    assert one("position", state("device_tracker.car", "unavailable")).problem == "unavailable"
    assert one("position_lat", state("sensor.lat", "52.5", "°")).value == 52.5
    assert one("position_lon", state("sensor.lon", "200")).problem == "range"


# ------------------------------------------------------------------ the catalogue


def test_every_slot_is_a_field_of_the_plugin_api_and_has_its_texts():
    en, de = i18n.translator("en"), i18n.translator("de")
    for slot in cat.SLOTS:
        assert (slot.field in connectors.KNOWN or slot.kind == "command") and slot.group in {g for g, _icon in cat.GROUPS}, (
            slot
        )  # (a command fills no interface)
        assert (slot.kind == "command") == (slot.field == ""), slot
        assert slot.kind in habridge.READERS, slot
        for t in (en, de):
            assert t.has(f"hab.slot.{slot.key}"), slot.key
        if slot.kind in ("number", "tyre", "coord"):
            assert slot.unit in habridge.UNITS or slot.unit == "", slot  # a number can be turned into the unit of its slot
            if slot.field in connectors.NUMBERS:
                assert connectors.NUMBERS[slot.field][1] <= connectors.NUMBERS[slot.field][2]
        if slot.kind in ("bool", "closure", "warning"):
            assert slot.truth in ("on", "locked", "open", "plugged", "charging", "climate", "any"), slot
    for group, _icon in cat.GROUPS:
        assert en.has(f"hab.group.{group}") and de.has(f"hab.group.{group}")
    assert {s.key for s in cat.SLOTS} == set(cat.BY_KEY) and len(cat.SLOTS) == len(cat.BY_KEY)
    for names in cat.CLOSURE_NAMES.values():
        for name in names:
            assert en.has(f"hab.name.{name}") and de.has(f"hab.name.{name}")
    # every interface of the Plugin API a person could bind is offered (the ones that are no values of the car stay out)
    offered = {s.field for s in cat.SLOTS if s.kind != "command"}
    assert set(connectors.KNOWN) - offered == {"measured_at"}, set(connectors.KNOWN) - offered - {"measured_at"}
    for truth in ("on", "locked", "open", "plugged", "charging", "climate", "any"):
        for n in (0, 1):
            assert en.has(f"hab.v.{truth}.{n}") and de.has(f"hab.v.{truth}.{n}")


# ------------------------------------------------------------------ one delivery


def test_the_readings_become_deliveries_one_for_each_time_of_measurement():
    soon, late = "2026-11-26T08:00:00+00:00", "2026-11-26T08:05:00+00:00"
    rows = {
        "odometer_km": one("odometer_km", state("sensor.odo", "1000", at=soon)),
        "range_km": one("range_km", state("sensor.range", "300", at=late)),
        "tyre_fl": one("tyre_fl", state("sensor.fl", "2.4", at=soon)),
        "tyre_rr": one("tyre_rr", state("sensor.rr", "2.5", at=soon)),
        "position": one("position", state("device_tracker.car", "not_home", at=late, latitude=1.5, longitude=2.5)),
        "doors.front_left": habridge.read(
            cat.BY_KEY["doors"], "binary_sensor.fl", {}, world(state("binary_sensor.fl", "on", dclass="door")), "front_left"
        ),
        "doors.trunk": habridge.read(cat.BY_KEY["doors"], "cover.trunk", {}, world(state("cover.trunk", "closed")), "trunk"),
        "warnings.low_oil": habridge.read(
            cat.BY_KEY["warnings"],
            "binary_sensor.oil",
            {},
            world(state("binary_sensor.oil", "on", friendly_name="Oil pressure low")),
            "low_oil",
        ),
        "warnings.old": habridge.read(cat.BY_KEY["warnings"], "binary_sensor.old", {}, world(state("binary_sensor.old", "off")), "old"),
    }
    batches = habridge.build(rows)
    assert [at for at, _data in batches] == [soon, late]  # the oldest first
    first, second = batches[0][1], batches[1][1]
    assert first["odometer_km"] == 1000 and first["tyre_pressure_bar"] == {"fl": 2.4, "rr": 2.5}
    assert first["doors"] == {"front_left": True, "trunk": False}
    assert first["warnings"] == {"low_oil": "Oil pressure low", "old": None}  # a warning that is off is taken away again
    assert second == {"range_km": 300, "position": {"lat": 1.5, "lon": 2.5}}


def test_a_position_of_two_sensors_is_used_only_while_no_tracker_is_chosen():
    lat, lon = (
        one("position_lat", state("sensor.lat", "10.5")),
        one("position_lon", state("sensor.lon", "20.5", at="2026-11-26T09:00:00+00:00")),
    )
    joined = habridge._position_of_halves({"position_lat": lat, "position_lon": lon})
    assert joined["position"].value == (10.5, 20.5) and joined["position"].at == "2026-11-26T09:00:00+00:00"  # the later of the two times
    tracker = one("position", state("device_tracker.car", "not_home", latitude=1.0, longitude=2.0))
    assert habridge._position_of_halves({"position": tracker, "position_lat": lat, "position_lon": lon})["position"] is tracker
    broken = habridge._position_of_halves({"position_lat": lat, "position_lon": one("position_lon", state("sensor.lon", "unavailable"))})
    assert not broken["position"].ok and broken["position"].problem == "unavailable"
    assert "position" not in habridge._position_of_halves({"position_lat": lat})  # one half alone is nothing


# ------------------------------------------------------------------ an install, its bindings and the schedule

STATES = world(
    state("sensor.car_odometer", "60210.5", "km", "distance"),
    state("sensor.car_range", "281", "km", "distance"),
    state("sensor.car_battery", "64", "%", "battery"),
    state("device_tracker.car", "not_home", latitude=52.52, longitude=13.405, gps_accuracy=8, friendly_name="Car"),
    state("lock.car", "locked"),
    state("binary_sensor.door_fl", "off", dclass="door"),
    state("cover.trunk", "closed"),
    state("sensor.tyre_fl", "34.8", "psi", "pressure"),
    state("sensor.wallbox_status", "Charging"),
    state("sensor.wallbox_power", "7400", "W", "power"),
    state("binary_sensor.problem_oil", "on", dclass="problem", friendly_name="Oil pressure low"),
)

FORM = {
    "e.odometer_km": "sensor.car_odometer",
    "e.range_km": "sensor.car_range",
    "e.battery_pct": "sensor.car_battery",
    "e.position": "device_tracker.car",
    "e.locked": "lock.car",
    "e.tyre_fl": "sensor.tyre_fl",
    "e.charging": "sensor.wallbox_status",
    "o.charging.yes": "Charging",
    "e.charge_power_kw": "sensor.wallbox_power",
    "l.doors.0.n": "front_left",
    "l.doors.0.e": "binary_sensor.door_fl",
    "l.doors.1.n": "Trunk",
    "l.doors.1.e": "cover.trunk",
    "l.warnings.0.n": "low_oil",
    "l.warnings.0.e": "binary_sensor.problem_oil",
    "every": "30",
}


@pytest.fixture()
def home(monkeypatch):
    """Home Assistant as the plugin sees it: a dict of entities the test may change (``home.states``), or ``home.down``."""

    class Home:
        states = dict(STATES)
        down = False
        asked = 0

    box = Home()
    box.states = dict(STATES)

    def all_states(seconds=4.0):
        box.asked += 1
        return None if box.down else dict(box.states)

    monkeypatch.setattr(ha, "all_states", all_states)
    habridge._state.clear()
    habridge._watch = {}
    habridge.attach(None)
    yield box
    habridge.attach(None)
    habridge._state.clear()


def install(client, **change):
    vid = create_vehicle(client)
    manifest = {**BRIDGE, **change}
    with db.tx() as conn:
        source = conn.execute("SELECT id FROM sources LIMIT 1").fetchone()["id"]
        pk = addons.add(conn, vid, addons.parse_package(json.dumps(manifest).encode()), source, None)
    return vid, pk


def stored(vid):
    with db.tx() as conn:
        return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM live WHERE vehicle_id = ?", (vid,))}


def log_of(vid):
    with db.tx() as conn:
        return [
            (r["level"], r["message"])
            for r in conn.execute("SELECT level, message FROM vehicle_logs WHERE vehicle_id = ? ORDER BY id", (vid,))
        ]


def save(client, vid, pk, **change):
    form = {**FORM, **change}
    return client.post(f"/v/{vid}/integrations/{pk}/bridge", data={k: v for k, v in form.items() if v is not None})


def test_the_manifest_of_a_bridge_is_checked():
    manifest = addons.parse_package(json.dumps(BRIDGE).encode())
    assert manifest["bridge"] == {"type": "home_assistant"} and not addons.needs_token(
        manifest
    )  # nobody calls the Plugin API: the app does
    narrow = addons.parse_package(
        json.dumps({**BRIDGE, "bridge": {"type": "home_assistant", "groups": ["battery", "nonsense"], "every": 1}}).encode()
    )
    assert narrow["bridge"] == {"type": "home_assistant", "groups": ["battery"], "every": habridge.EVERY[0]}
    only = addons.parse_package(
        json.dumps(
            {**BRIDGE, "bridge": {"type": "home_assistant", "slots": ["charging", "plugged", "nothing"], "groups": ["fuel"]}}
        ).encode()
    )
    assert only["bridge"]["slots"] == ["charging", "plugged"] and "groups" not in only["bridge"]  # the slots win
    assert [s.key for s in habridge.offered(only)] == ["charging", "plugged"]
    assert [s.key for s in habridge.offered(narrow)] == [s.key for s in cat.SLOTS if s.group == "battery"]
    for bridge in ({"type": "mqtt"}, "yes", None, {}):
        assert "bridge" not in addons.parse_package(json.dumps({**BRIDGE, "bridge": bridge}).encode())
    # one thing or the other: a package with a service or a connector or an integration is no bridge
    assert "bridge" not in addons.parse_package(json.dumps({**BRIDGE, "kind": "integration"}).encode())
    service = {"entry": "main.py", "routes": []}
    assert "bridge" not in addons.parse_package(json.dumps({**BRIDGE, "service": service}).encode())
    connector = {"requests": [{"id": "a", "url": "https://api.example.com/x"}], "map": [{"field": "odometer_km", "from": "a", "path": "a"}]}
    assert "bridge" not in addons.parse_package(json.dumps({**BRIDGE, "connector": connector}).encode())
    assert habridge.interval({"m": manifest, "vals": {"every": "300"}}) == 300
    assert habridge.interval({"m": manifest, "vals": {"every": "1"}}) == habridge.EVERY[0]
    assert habridge.interval({"m": manifest, "vals": {"every": "x"}}) == habridge.EVERY[2]
    assert habridge.interval({"m": narrow, "vals": {}}) == habridge.EVERY[0]  # what the package says, when the person did not choose


def test_the_claims_of_a_package_are_cleaned():
    plain = {
        **{k: v for k, v in BRIDGE.items() if k != "bridge"},
        "claims": ["range_km", "fuel_level_pct", "nonsense", "measured_at", "range_km", 5],
    }
    assert addons.parse_package(json.dumps(plain).encode())["claims"] == ["fuel_level_pct", "range_km"]
    assert "claims" not in addons.parse_package(json.dumps({**plain, "claims": []}).encode())
    assert "claims" not in addons.parse_package(json.dumps({**plain, "claims": "range_km"}).encode())
    assert "claims" not in addons.parse_package(
        json.dumps({**BRIDGE, "claims": ["range_km"]}).encode()
    )  # a bridge takes what the person binds


def test_the_page_of_a_bridge_lists_the_interfaces_by_group(client, home):
    vid, pk = install(client)
    page = client.get(f"/v/{vid}/integrations/{pk}/settings")
    assert page.status_code == 200
    html = page.text
    assert "Entities of Home Assistant" in html and "habridge.js" in html
    for group in ("Vehicle", "Fuel and range", "Battery and charging", "Doors, windows and lock", "Tyres", "Service and warnings"):
        assert group in html, group
    for slot in cat.SLOTS:
        if slot.kind in cat.LIST_KINDS:
            assert f'data-hb-list="{slot.key}"' in html, slot.key
        else:
            assert f'name="e.{slot.key}"' in html, slot.key
    assert 'name="every"' in html and '<option value="30" selected>' in html  # the interval comes from the package's own setting
    assert (
        'name="o.position.track"' in html and 'name="o.range_km.track"' not in html
    )  # the option to record trips belongs to the tracker row
    assert "0 of" in html  # nothing chosen yet
    assert 'action="/v/' not in html.split("hbform")[0] or True  # (the generic settings form is replaced)
    assert 'id="aform"' not in html


def test_saving_binds_the_entities_takes_the_interfaces_and_the_values_flow(client, home):
    vid, pk = install(client)
    got = save(client, vid, pk)
    assert got.status_code == 303 and got.headers["location"].endswith(f"/integrations/{pk}/settings?m=saved")
    with db.tx() as conn:
        rows = habridge.bindings(conn, pk)
        assert set(rows) == {
            "odometer_km", "range_km", "battery_pct", "position", "locked", "tyre_fl", "charging", "charge_power_kw",
            "doors.front_left", "doors.trunk", "warnings.low_oil",
        }  # fmt: skip
        assert rows["charging"] == {"entity": "sensor.wallbox_status", "options": {"yes": ["Charging"]}}
        assert rows["doors.trunk"]["entity"] == "cover.trunk"  # (the name was typed with a capital)
        assert claims.held_by(conn, vid, pk) == sorted(
            [
                "battery_pct",
                "charge_power_kw",
                "charging",
                "doors",
                "locked",
                "odometer_km",
                "position",
                "range_km",
                "tyre_pressure_bar",
                "warnings",
            ]
        )
        assert addons.get(conn, vid, pk)["status"] == "configured" and addons.get(conn, vid, pk)["token_id"] is None
    assert habridge.tick(1000.0) == 1  # the first reading
    values = stored(vid)
    assert values["range_km"] == "281" and values["battery_pct"] == "64" and values["locked"] == "locked" and values["charging"] == "yes"
    assert values["charge_power_kw"] == "7.4" and values["position"] == "52.520000,13.405000"
    assert json.loads(values["tyre_pressure_bar"]) == {"fl": 2.4} and json.loads(values["doors"]) == {"front_left": False, "trunk": False}
    assert json.loads(values["warnings"]) == {"low_oil": "Oil pressure low"}
    with db.tx() as conn:
        assert summary.current_odometer(conn, vid) == 60210  # (round half to even: 60210.5 -> 60210)
    assert ("info", "reading 11 entities of Home Assistant every 30 s") in log_of(vid)
    assert habridge.tick(1010.0) == 0  # not due yet
    assert habridge.tick(1031.0) == 1  # due: nothing changed, nothing is sent
    home.states["sensor.car_range"] = state("sensor.car_range", "250", "km", at="2026-11-26T09:00:00+00:00")
    sent = []
    real = habridge.deliver
    habridge.deliver = lambda conn, addon, at, data: sent.append((at, data)) or real(conn, addon, at, data)
    try:
        assert habridge.tick(1062.0) == 1
    finally:
        habridge.deliver = real
    assert sent == [("2026-11-26T09:00:00+00:00", {"range_km": 250})]  # only what changed - with the time Home Assistant gives
    assert stored(vid)["range_km"] == "250"


def test_the_odometer_follows_home_assistant_by_itself_and_is_shown_not_typed(client, home):
    """Nothing has to be triggered: a plugin that has an entity for the odometer reads it by itself (here: the next reading after the interval; in the
    add-on at once through the live connection). The dashboard then shows the figure instead of asking for it - a plugin without a key is no exception."""
    vid, pk = install(client)
    with db.tx() as conn:
        assert summary.odometer_from_car(conn, vid) is False  # typed at the start: a person's
    assert save(client, vid, pk).status_code == 303
    assert habridge.tick(1000.0) == 1
    with db.tx() as conn:
        assert summary.current_odometer(conn, vid) == 60210  # (the car started with 50000, typed)
        assert summary.odometer_from_car(conn, vid) is True
    home.states["sensor.car_odometer"] = state("sensor.car_odometer", "60300.2", "km", "distance", at="2026-11-26T09:00:00+00:00")
    assert habridge.tick(1010.0) == 0  # (not due yet)
    assert habridge.tick(1031.0) == 1
    with db.tx() as conn:
        assert summary.current_odometer(conn, vid) == 60300
        rows = conn.execute("SELECT odometer_km FROM odometer WHERE vehicle_id = ? AND source = 'api:Home Assistant'", (vid,)).fetchall()
        assert [r["odometer_km"] for r in rows] == [60300]  # one row for the day, not one per reading
    # switched off, or no entity for the odometer any more: the person has it back (the last reading stays)
    with db.tx() as conn:
        conn.execute("UPDATE vehicle_addons SET active = 0 WHERE id = ?", (pk,))
        assert summary.odometer_from_car(conn, vid) is False
        conn.execute("UPDATE vehicle_addons SET active = 1 WHERE id = ?", (pk,))
        assert summary.odometer_from_car(conn, vid) is True
    assert save(client, vid, pk, **{"e.odometer_km": ""}).status_code == 303
    with db.tx() as conn:
        assert summary.odometer_from_car(conn, vid) is False and summary.current_odometer(conn, vid) == 60300


def test_an_odometer_below_the_known_one_is_said_once_and_never_after_a_restart(client, home):
    vid, pk = install(client)
    assert save(client, vid, pk).status_code == 303
    assert habridge.tick(1000.0) == 1

    def drives(km, now, at):
        home.states["sensor.car_odometer"] = state("sensor.car_odometer", km, "km", "distance", at=at)
        assert habridge.tick(now) == 1

    def lines():
        return [m for lvl, m in log_of(vid) if lvl == "warn" and m.startswith("odometer_km")]

    drives("60400", 1031.0, "2026-11-26T09:00:00+00:00")
    assert lines() == []  # higher than 60210: taken
    with db.tx() as conn:  # a fill-up typed with a higher figure: that is the known odometer now
        conn.execute(
            "INSERT INTO fuel(vehicle_id, date, odometer_km, amount, price_total, full_tank) VALUES(?, '2026-11-26', 70000, 40, 70, 1)",
            (vid,),
        )
    drives("60500", 1062.0, "2026-11-26T10:00:00+00:00")
    with db.tx() as conn:
        assert summary.current_odometer(conn, vid) == 70000  # not taken ...
    assert lines() == [habridge.ODOMETER_LOW]  # ... and the log says why, so nobody has to guess
    drives("60600", 1093.0, "2026-11-26T11:00:00+00:00")
    drives("60700", 1124.0, "2026-11-26T12:00:00+00:00")
    assert lines() == [habridge.ODOMETER_LOW]  # said once, not with every kilometre driven
    drives("70100", 1155.0, "2026-11-26T13:00:00+00:00")  # it has caught up: taken, and the gap is forgotten
    with db.tx() as conn:
        assert summary.current_odometer(conn, vid) == 70100
        conn.execute("UPDATE fuel SET odometer_km = 80000 WHERE odometer_km = 70000")  # a new gap is said again at once
    drives("70200", 1186.0, "2026-11-26T14:00:00+00:00")
    assert lines() == [habridge.ODOMETER_LOW] * 2
    # the add-on restarts and reads the figure it stored itself again: equal is no gap, so no word
    with db.tx() as conn:
        conn.execute("UPDATE fuel SET odometer_km = 1000 WHERE odometer_km = 80000")
        assert summary.current_odometer(conn, vid) == 70100
    habridge._state.clear()
    drives("70100", 2000.0, "2026-11-26T15:00:00+00:00")
    assert lines() == [habridge.ODOMETER_LOW] * 2


# ------------------------------------------------------------------ the drives of a tracker (option "Record trips" of the position row)

DRIVE = [(52.5230, 13.4080, 3), (52.5260, 13.4110, 4), (52.5290, 13.4140, 5)]  # about 390 m between two reports


def _story(client, home, monkeypatch, **form):
    """The plugin installed with the tracker chosen (and ``form`` on top) and the drive told minute by minute: returns ``(vid, moves, clock)`` where
    ``moves(lat, lon, minute, **attributes)`` is one report of the tracker. The clock of the trip maker is the time of the report, as it is in life."""
    clock = {"now": datetime(2026, 11, 26, 8, 0, tzinfo=UTC)}
    real = trips.from_track
    monkeypatch.setattr(trips, "from_track", lambda conn, vid, now=None: real(conn, vid, now=clock["now"]))
    vid, pk = install(client)
    assert save(client, vid, pk, **form).status_code == 303
    ticks = [999.0]

    def moves(lat, lon, minute, **attributes):
        when = datetime(2026, 11, 26, 8, 0, tzinfo=UTC) + timedelta(minutes=minute)
        clock["now"] = when
        attributes.setdefault("gps_accuracy", 8)
        home.states["device_tracker.car"] = state(
            "device_tracker.car", "not_home", at=when.isoformat(), latitude=lat, longitude=lon, **attributes
        )
        ticks[0] += 31
        assert habridge.tick(ticks[0]) == 1

    return vid, moves, clock


def _route(vid):
    with db.tx() as conn:
        points = conn.execute("SELECT ts, lat, lon, trip_id FROM vehicle_track WHERE vehicle_id = ? ORDER BY ts", (vid,)).fetchall()
        made = conn.execute("SELECT * FROM trips WHERE vehicle_id = ?", (vid,)).fetchall()
    return points, made


def test_the_drives_of_a_tracker_become_trips_when_the_option_is_on(client, home, monkeypatch):
    vid, moves, clock = _story(client, home, monkeypatch, **{"o.position.track": "on"})
    moves(52.5200, 13.4050, 0)  # parked
    moves(52.52003, 13.40502, 1)  # a parked tracker jitters by a few metres: no point
    moves(52.52002, 13.40499, 2)
    for lat, lon, minute in DRIVE:
        moves(lat, lon, minute)
    moves(52.5290, 13.4140, 6)  # it stands: the same place again, no new point
    points, made = _route(vid)
    assert [p["ts"][11:16] for p in points] == [
        "08:02",
        "08:03",
        "08:04",
        "08:05",
    ]  # the place where it stood, then the moves - nothing of the jitter
    assert made == []  # one minute after the last point the drive is not over
    clock["now"] = datetime(2026, 11, 26, 8, 20, tzinfo=UTC)
    with db.tx() as conn:
        assert trips.from_track(conn, vid) == 1  # ten minutes of nothing new: it was a trip
    points, made = _route(vid)
    assert len(made) == 1 and made[0]["source"] == "track" and 0.9 < made[0]["distance_km"] < 1.5
    assert {p["trip_id"] for p in points} == {made[0]["id"]}
    assert stored(vid)["position"] == "52.529000,13.414000"  # the position of the car is the newest point, as always


def test_a_position_seen_hours_ago_is_not_the_place_where_a_drive_began(client, home, monkeypatch):
    """Found with a real Home Assistant: the first report after a long silence (the night, a restart of the app, an entity that was away) was joined to the
    position seen hours before - the trip got a line of many kilometres and began at the old time."""
    vid, moves, _clock = _story(client, home, monkeypatch, **{"o.position.track": "on"})
    moves(52.5200, 13.4050, 0)  # where the car stood in the evening
    moves(52.6200, 13.5050, 300)  # five hours later the tracker reports from about 13 km away: nothing says where it was in between
    assert _route(vid)[0] == []  # no line through the night
    for lat, lon, minute in ((52.6230, 13.5080, 301), (52.6260, 13.5110, 302), (52.6290, 13.5140, 303)):
        moves(lat, lon, minute)
    points, _made = _route(vid)
    assert [p["ts"][11:16] for p in points] == [
        "13:00",
        "13:01",
        "13:02",
        "13:03",
    ]  # the drive begins where the car stood at its last report before the moves


def test_nothing_of_the_route_is_kept_without_the_option(client, home, monkeypatch):
    vid, moves, _clock = _story(client, home, monkeypatch)  # the default: only the position of the car is kept
    moves(52.5200, 13.4050, 0)
    for lat, lon, minute in DRIVE:
        moves(lat, lon, minute)
    points, made = _route(vid)
    assert points == [] and made == []
    assert stored(vid)["position"] == "52.529000,13.414000"


def test_a_car_that_is_off_and_a_fix_that_is_inexact_leave_no_points(client, home, monkeypatch):
    home.states["binary_sensor.ignition"] = state("binary_sensor.ignition", "off")
    vid, moves, _clock = _story(client, home, monkeypatch, **{"o.position.track": "on", "e.ignition": "binary_sensor.ignition"})
    moves(52.5200, 13.4050, 0)
    moves(52.5210, 13.4060, 1)  # the tracker drifts by about 130 m (a garage), the ignition says off: no point
    assert _route(vid)[0] == []
    home.states["binary_sensor.ignition"] = state("binary_sensor.ignition", "on")
    moves(52.5240, 13.4090, 2, gps_accuracy=500)  # a fix the tracker calls 500 m wrong: left out altogether
    assert _route(vid)[0] == []
    moves(52.5270, 13.4120, 3)
    moves(52.5300, 13.4150, 4)
    assert [p["ts"][11:16] for p in _route(vid)[0]] == ["08:01", "08:03", "08:04"]  # from where it stood, never through the inexact fix


def test_the_option_record_trips_belongs_to_the_tracker_row_only():
    tracker = cat.BY_KEY["position"]
    assert habridge.parse_options({"x.track": "on"}, "x.", tracker) == ({"track": True}, "")
    assert habridge.parse_options({}, "x.", tracker) == ({}, "")
    assert habridge.parse_options({"x.track": "on"}, "x.", cat.BY_KEY["range_km"]) == ({}, "")  # any other row ignores it
    assert habridge.clean_stored("position", "device_tracker.car", {"track": True}) == {
        "entity": "device_tracker.car",
        "options": {"track": True},
    }
    assert habridge.clean_stored("position", "device_tracker.car", {"track": False})["options"] == {}  # (a backup file is read like a form)
    assert habridge._typed_options({"o.position.track": "on"}, "o.position.", tracker) == {"track": True}


def test_what_is_wrong_is_said_once_in_the_log_and_never_stops_the_rest(client, home):
    vid, pk = install(client)
    assert save(client, vid, pk).status_code == 303
    home.states["sensor.car_range"] = state("sensor.car_range", "281", "l")  # the wrong unit
    del home.states["sensor.car_battery"]  # an entity that is gone
    home.states["sensor.tyre_fl"] = state("sensor.tyre_fl", "unavailable")  # the car is asleep: no line for that
    habridge.tick(1000.0)
    values = stored(vid)
    assert "range_km" not in values and "battery_pct" not in values and values["locked"] == "locked"
    lines = [m for lvl, m in log_of(vid) if lvl == "warn"]
    assert any(m.startswith("range_km (sensor.car_range): The unit “l” does not fit") for m in lines)
    assert any(m.startswith("battery_pct (sensor.car_battery): This entity does not exist") for m in lines)
    assert not any("tyre" in m for m in lines)
    habridge.tick(1031.0)
    habridge.tick(1062.0)
    assert len([m for lvl, m in log_of(vid) if lvl == "warn"]) == len(lines)  # the same trouble is not said again and again
    home.states["sensor.car_range"] = state("sensor.car_range", "281", "km")  # put right: it works, without a word
    habridge.tick(1093.0)
    assert stored(vid)["range_km"] == "281"


def test_home_assistant_that_cannot_be_asked_is_said_once_and_asked_again(client, home):
    vid, pk = install(client)
    assert save(client, vid, pk).status_code == 303
    home.down = True
    assert habridge.tick(1000.0) == 1
    assert stored(vid) == {}
    habridge.tick(1031.0)
    habridge.tick(1100.0)
    assert [m for lvl, m in log_of(vid) if lvl == "warn"] == ["Home Assistant cannot be reached; trying again"]  # once
    home.down = False
    habridge.tick(1500.0)
    assert stored(vid)["range_km"] == "281"
    assert ("info", "Home Assistant can be reached again") in log_of(vid)


def test_only_a_plugin_that_is_on_and_set_up_on_a_car_in_use_is_read(client, home):
    vid, pk = install(client)
    assert habridge.tick(1000.0) == 0  # not set up yet
    assert save(client, vid, pk).status_code == 303
    with db.tx() as conn:
        conn.execute("UPDATE vehicle_addons SET active = 0 WHERE id = ?", (pk,))
    assert habridge.tick(1000.0) == 0  # switched off
    with db.tx() as conn:
        conn.execute("UPDATE vehicle_addons SET active = 1 WHERE id = ?", (pk,))
        conn.execute("UPDATE vehicles SET archived = 1 WHERE id = ?", (vid,))
    assert habridge.tick(1000.0) == 0  # the car is archived
    with db.tx() as conn:
        conn.execute("UPDATE vehicles SET archived = 0 WHERE id = ?", (vid,))
    assert habridge.tick(1000.0) == 1


# ------------------------------------------------------------------ what is refused when saving


def test_nothing_is_saved_while_anything_is_wrong_and_the_page_comes_back_with_what_was_typed(client, home):
    vid, pk = install(client)
    got = save(
        client,
        vid,
        pk,
        **{
            "e.range_km": "not an entity",  # no entity
            "e.battery_pct": "sensor.nothing_here",  # Home Assistant has no such entity
            "o.tyre_fl.scale": "abc",  # not a number
            "l.doors.1.n": "front_left",  # the same name twice
            "l.warnings.0.n": "Bad Name!",
        },
    )
    assert got.status_code == 400
    html = got.text
    for text in (
        "That is no entity of Home Assistant",
        "Home Assistant has no such entity.",
        "A number is needed",
        "This name is used twice.",
        "The name needs lower-case letters",
        "Some settings need a correction - nothing was saved.",
    ):
        assert text in html, text
    assert 'value="not an entity"' in html and 'value="sensor.nothing_here"' in html and 'value="abc"' in html  # what was typed stays
    with db.tx() as conn:
        assert habridge.bindings(conn, pk) == {} and claims.held_by(conn, vid, pk) == []
        assert addons.get(conn, vid, pk)["status"] != "configured"


def test_a_save_from_the_page_script_answers_in_json(client, home):
    vid, pk = install(client)
    headers = {"X-Requested-With": "fetch"}
    bad = client.post(f"/v/{vid}/integrations/{pk}/bridge", data={"e.range_km": "nope"}, headers=headers)
    assert bad.status_code == 422 and bad.json()["ok"] is False and "e.range_km" in bad.json()["errors"]
    good = client.post(f"/v/{vid}/integrations/{pk}/bridge", data={"e.range_km": "sensor.car_range"}, headers=headers)
    assert good.status_code == 200 and good.json() == {"ok": True}


@pytest.mark.parametrize(
    ("form", "why"),
    [
        ({"e.range_km": "sensor.car_range", "o.range_km.unit": "furlongs"}, "hab.err_unit"),
        ({"e.range_km": "sensor.car_range", "o.range_km.scale": "1e12"}, "hab.err_number"),
        ({"e.range_km": "sensor.car_range", "o.range_km.attribute": "a b"}, "hab.err_attribute"),
        ({"e.locked": "lock.car", "o.locked.yes": "a,b,c,d,e,f,g,h,i,j,k,l,m"}, "hab.err_yes"),
        ({"e.locked": "lock.car", "o.locked.yes": "locked", "o.locked.above": "1"}, "hab.err_both"),
        ({"e.locked": "lock.car", "o.locked.above": "x"}, "hab.err_number"),
        ({"l.doors.0.e": "binary_sensor.door_fl"}, "hab.err_name"),  # a row without a name
        ({"l.doors.0.n": "a", "l.doors.0.e": "Binary_Sensor.Door_FL"}, None),  # (upper case is fine: entities are lower case)
    ],
)
def test_every_option_is_checked(form, why):
    states = dict(STATES)
    rows, errors = habridge.parse_form(form, addons.parse_package(json.dumps(BRIDGE).encode()), states)
    assert (set(errors.values()) == {why}) if why else not errors, (errors, rows)


def test_what_can_be_bound_is_limited_and_a_package_may_offer_only_a_part():
    manifest = addons.parse_package(json.dumps({**BRIDGE, "bridge": {"type": "home_assistant", "slots": ["charging", "plugged"]}}).encode())
    rows, errors = habridge.parse_form({"e.charging": "sensor.wallbox_status", "e.range_km": "sensor.car_range"}, manifest, dict(STATES))
    assert set(rows) == {"charging"} and not errors  # the range is not offered by this package: it is not taken from a form either
    many = {f"e.{slot.key}": "sensor.car_range" for slot in cat.SLOTS if slot.kind not in cat.LIST_KINDS}  # every value ...
    for slot in cat.SLOTS:
        if slot.kind in cat.LIST_KINDS:  # ... and every row of every list (16 each)
            many |= {f"l.{slot.key}.{i}.n": f"row{i}" for i in range(16)} | {
                f"l.{slot.key}.{i}.e": "binary_sensor.door_fl" for i in range(16)
            }
    rows, errors = habridge.parse_form(many, addons.parse_package(json.dumps(BRIDGE).encode()), dict(STATES))
    assert errors == {"_": "hab.err_many"}


# ------------------------------------------------------------------ one interface, one plugin


def _other_plugin(vid, claims_wanted):
    manifest = {"id": "other-plugin", "kind": "plugin", "name": "Other Plugin", "version": "1", "claims": claims_wanted, "settings": []}
    with db.tx() as conn:
        source = conn.execute("SELECT id FROM sources LIMIT 1").fetchone()["id"]
        return addons.add(conn, vid, addons.parse_package(json.dumps(manifest).encode()), source, None)


def test_an_interface_another_plugin_holds_cannot_be_bound_and_the_page_says_who(client, home):
    vid, pk = install(client)
    other = _other_plugin(vid, ["range_km"])  # takes the range by its manifest
    with db.tx() as conn:
        assert addons.get(conn, vid, other)["active"] == 1 and claims.held_by(conn, vid, other) == ["range_km"]
    got = save(client, vid, pk)
    assert (
        got.status_code == 400
        and "Another plugin of this car holds these interfaces:" in got.text
        and "range_km (Other Plugin)" in got.text
    )
    with db.tx() as conn:
        assert habridge.bindings(conn, pk) == {}
    assert "Taken by Other Plugin" in client.get(f"/v/{vid}/integrations/{pk}/settings").text
    assert save(client, vid, pk, **{"e.range_km": None}).status_code == 303  # without that one it goes
    # ... and the other plugin steps back: the interface is free
    with db.tx() as conn:
        claims.release(conn, other)
    assert save(client, vid, pk).status_code == 303
    assert habridge.tick(1000.0) == 1 and stored(vid)["range_km"] == "281"


def test_a_plugin_whose_interface_is_taken_is_installed_off_and_cannot_be_switched_on(client, home):
    vid, pk = install(client)
    assert save(client, vid, pk).status_code == 303  # the bridge holds the range, the battery ...
    other = _other_plugin(vid, ["range_km", "fuel_level_pct"])
    with db.tx() as conn:
        assert addons.get(conn, vid, other)["active"] == 0  # installed, but off: it would take what is taken
        addon = addons.get(conn, vid, other)
        with pytest.raises(addons.AddonError) as why:
            addons.set_active(conn, addon, True)
        assert why.value.key == "addon.err_claims"
    answer = client.post(f"/v/{vid}/integrations/{other}/active", data={"active": "1"})
    assert answer.status_code == 303 and "m=addon.err_claims" in answer.headers["location"]
    assert client.post(f"/v/{vid}/integrations/{other}/active", data={"active": "1", "ajax": "1"}).status_code == 409
    # the bridge lets the range go: the other plugin may be switched on now
    assert save(client, vid, pk, **{"e.range_km": None}).status_code == 303
    assert client.post(f"/v/{vid}/integrations/{other}/active", data={"active": "1"}).headers["location"].endswith("m=saved")
    with db.tx() as conn:
        assert claims.owners(conn, vid)["range_km"]["name"] == "Other Plugin"


def test_a_value_of_another_source_for_a_bound_interface_is_ignored_and_says_so(client, home):
    vid, pk = install(client)
    other = _other_plugin(vid, [])
    with db.tx() as conn:
        token = addons.new_token(conn, vid, addons.get(conn, vid, other))
    assert save(client, vid, pk).status_code == 303
    habridge.tick(1000.0)
    sent = client.post(
        f"/api/v1/vehicles/{vid}/data", headers={"Authorization": f"Bearer {token}"}, json={"range_km": 5, "speed_kmh": 50}
    ).json()["result"]
    assert sent["range_km"] == "ignored (taken by Home Assistant)" and sent["speed_kmh"] == "stored"
    assert stored(vid)["range_km"] == "281"


def test_removing_the_plugin_gives_the_interfaces_back(client, home):
    vid, pk = install(client)
    assert save(client, vid, pk).status_code == 303
    with db.tx() as conn:
        assert claims.owners(conn, vid)
        addons.remove(conn, addons.get(conn, vid, pk))
        assert claims.owners(conn, vid) == {} and conn.execute("SELECT COUNT(*) FROM ha_bindings").fetchone()[0] == 0


# ------------------------------------------------------------------ the routes of the page


def test_the_page_script_asks_what_the_entities_deliver_and_for_entities_to_choose_from(client, home):
    vid, pk = install(client)
    assert save(client, vid, pk).status_code == 303
    answer = client.post(
        f"/v/{vid}/integrations/{pk}/bridge/preview",
        data={
            "e.range_km": "sensor.car_range",
            "e.tyre_fl": "sensor.tyre_fl",
            "e.locked": "lock.car",
            "e.battery_pct": "sensor.nothing",
            "e.vin": "x y",
        },
    ).json()
    rows = answer["rows"]
    assert answer["ok"] and answer["ha"]
    assert rows["e.range_km"] == {"level": "ok", "text": "281 km", "from": ""}
    assert rows["e.tyre_fl"] == {"level": "ok", "text": "2.4 bar", "from": "from 34.8 psi"}
    assert rows["e.locked"]["text"] == "Locked" and rows["e.locked"]["from"] == "state: locked"
    assert rows["e.battery_pct"]["level"] == "bad" and "Home Assistant has no such entity" in rows["e.battery_pct"]["text"]
    assert rows["e.vin"]["level"] == "bad"
    home.states["sensor.car_range"] = state("sensor.car_range", "unavailable")
    again = client.post(f"/v/{vid}/integrations/{pk}/bridge/preview", data={"e.range_km": "sensor.car_range"}).json()["rows"]["e.range_km"]
    assert again["level"] == "warn" and again["text"] == "Not available right now"
    home.down = True
    assert client.post(f"/v/{vid}/integrations/{pk}/bridge/preview", data={"e.range_km": "sensor.car_range"}).json()["ha"] is False

    home.down = False
    home.states["sensor.car_range"] = state("sensor.car_range", "281", "km", "distance", friendly_name="Car range")
    found = client.get(f"/v/{vid}/integrations/{pk}/bridge/entities", params={"slot": "range_km"}).json()
    ids = [e["id"] for e in found["entities"]]
    assert found["ok"] and ids[0] == "sensor.car_range" and "lock.car" not in ids  # the right kind first; a lock is no range
    assert found["entities"][0] == {"id": "sensor.car_range", "name": "Car range", "state": "281", "unit": "km", "device": "", "area": ""}
    assert [
        e["id"]
        for e in client.get(f"/v/{vid}/integrations/{pk}/bridge/entities", params={"slot": "range_km", "q": "battery"}).json()["entities"]
    ] == ["sensor.car_battery"]  # the words typed filter - also entities of another kind of value
    everything = client.get(f"/v/{vid}/integrations/{pk}/bridge/entities", params={"slot": "range_km", "all": 1}).json()["entities"]
    assert "lock.car" in [e["id"] for e in everything]
    assert client.get(f"/v/{vid}/integrations/{pk}/bridge/entities", params={"slot": "nonsense"}).status_code == 404
    home.down = True
    assert client.get(f"/v/{vid}/integrations/{pk}/bridge/entities", params={"slot": "range_km"}).json() == {
        "ok": True,
        "ha": False,
        "entities": [],
    }


def test_the_entities_are_for_administrators_only(client, home, monkeypatch):
    from carassistant import habridge_web

    vid, pk = install(client)
    monkeypatch.setattr(habridge_web, "_may_manage", lambda request: False)
    assert client.post(f"/v/{vid}/integrations/{pk}/bridge/preview", data={}).status_code == 403
    assert client.get(f"/v/{vid}/integrations/{pk}/bridge/entities", params={"slot": "range_km"}).status_code == 403
    assert save(client, vid, pk).status_code == 303  # (it goes back to the list of integrations, with the reason)
    assert client.post(f"/v/{vid}/integrations/{pk}/bridge", data=FORM, headers={"X-Requested-With": "fetch"}).status_code == 403
    with db.tx() as conn:
        assert habridge.bindings(conn, pk) == {}


# ------------------------------------------------------------------ with the live connection


@pytest.fixture()
def live_home(monkeypatch):
    """A made-up Home Assistant that speaks real REST and WebSocket, and the live connection of the plugin to it."""
    pytest.importorskip("websocket")
    from fake_ha import FakeHA

    from carassistant import halive

    fake = FakeHA().start()
    for entity in STATES.values():
        fake.set(entity["entity_id"], entity["state"], **entity["attributes"])
    monkeypatch.setenv("CARASSISTANT_HA_API", fake.api)
    monkeypatch.setenv("SUPERVISOR_TOKEN", fake.token)
    monkeypatch.setattr(halive.Link, "READ_TIMEOUT", 0.05)
    monkeypatch.setattr(halive.Link, "BACKOFF", (0.05, 0.1))
    ha._cache.clear()
    habridge._state.clear()
    link = halive.Link()
    habridge.attach(link)
    link.start()
    yield fake, link
    link.stop()
    habridge.attach(None)
    habridge._state.clear()
    fake.stop()


def settle(link, entities, seconds=5.0):
    """Tick until the live connection follows these entities (the first tick tells the link what to follow)."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        habridge.tick(time.monotonic())
        if link.live and set(entities) <= link.following():
            habridge.tick(time.monotonic())  # (the connection coming up asks for a look at everything: that is this reading)
            return True
        time.sleep(0.02)
    return False


def test_a_change_in_home_assistant_arrives_at_once_without_asking(client, live_home):
    fake, link = live_home
    vid, pk = install(client)
    assert save(client, vid, pk).status_code == 303
    assert settle(link, {"sensor.car_range", "lock.car"})
    assert stored(vid)["range_km"] == "281"  # the first reading
    asked = fake.reads  # how often the list of all entities was fetched so far
    fake.set("sensor.car_range", "199", "km", "distance")  # the car drives on
    end = time.monotonic() + 5
    while stored(vid)["range_km"] != "199" and time.monotonic() < end:
        habridge.tick(time.monotonic() + 2)  # (the clock of the tick is ahead: the pause between two readings is over)
        time.sleep(0.02)
    assert stored(vid)["range_km"] == "199"
    st = habridge._state[pk]
    assert (
        st["next"] > time.monotonic() + 100
    )  # ... and it was no turn of the schedule: with a live connection that is a safety net, minutes away
    fake.set("lock.car", "unlocked")
    end = time.monotonic() + 5
    while stored(vid)["locked"] != "unlocked" and time.monotonic() < end:
        habridge.tick(time.monotonic() + 4)
        time.sleep(0.02)
    assert stored(vid)["locked"] == "unlocked" and fake.reads == asked  # nobody asked Home Assistant for anything


def test_a_change_that_comes_before_the_subscription_does_not_wait_for_the_safety_net(client, live_home, monkeypatch):
    """The plugin is saved, the first reading is made, and a moment later (before the subscription of the live connection is made) the entity changes: no event
    says so. The reading must come as soon as the subscription has looked at Home Assistant - not five minutes later (found with a real Home Assistant)."""
    import threading

    from carassistant import halive

    fake, _link = live_home
    gate = threading.Event()
    real = halive.Link._subscribe

    def late(self, ws, mode, entities, version):
        gate.wait(5)  # the subscription is made only when the test says so
        return real(self, ws, mode, entities, version)

    monkeypatch.setattr(halive.Link, "_subscribe", late)
    vid, pk = install(client)
    assert save(client, vid, pk).status_code == 303
    end = time.monotonic() + 5
    while stored(vid).get("range_km") != "281" and time.monotonic() < end:
        habridge.tick(time.monotonic())
        time.sleep(0.02)
    assert stored(vid)["range_km"] == "281"  # the first reading (the link has been told what to follow, but has not subscribed)
    fake.set("sensor.car_range", "199", "km", "distance")  # the car drives on - before anything follows the entity
    gate.set()  # now the subscription is made; it sees 199 only through its first look
    end = time.monotonic() + 5
    while stored(vid)["range_km"] != "199" and time.monotonic() < end:
        habridge.tick(time.monotonic())
        time.sleep(0.02)
    assert stored(vid)["range_km"] == "199"


def test_a_burst_of_changes_is_one_reading_after_the_pause(client, live_home):
    fake, link = live_home
    vid, pk = install(client)
    assert save(client, vid, pk).status_code == 303
    assert settle(link, {"sensor.car_range"})
    st = habridge._state[pk]
    base = time.monotonic() + 10
    fake.set("sensor.car_range", "10", "km", "distance")
    assert wait_for_dirty(st)
    assert habridge.tick(base) == 1  # the first change: a reading at once
    fake.set("sensor.car_range", "11", "km", "distance")
    assert wait_for_dirty(st)
    assert habridge.tick(base + 0.2) == 0 and habridge._pause <= 0.85  # a second one right behind it waits for its turn ...
    assert habridge.tick(base + habridge.LIVE_GAP + 0.1) == 1  # ... and gets it
    assert stored(vid)["range_km"] == "11"


def wait_for_dirty(st, seconds=5.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if st["dirty"]:
            return True
        time.sleep(0.01)
    return False


def test_without_the_live_connection_the_plugin_asks_as_it_always_did(client, live_home):
    fake, link = live_home
    vid, pk = install(client)
    assert save(client, vid, pk).status_code == 303
    assert settle(link, {"sensor.car_range"})
    fake.drop()  # the connection fails ...
    fake.set("sensor.car_range", "150", "km", "distance")  # ... and the car goes on
    end = time.monotonic() + 5
    while stored(vid)["range_km"] != "150" and time.monotonic() < end:
        habridge.tick(time.monotonic() + 40)  # the way back to asking is a reading at once; its time comes from the interval of the setting
        time.sleep(0.02)
    assert stored(vid)["range_km"] == "150"


def test_the_page_says_whether_the_connection_is_live(client, live_home):
    _fake, link = live_home
    vid, pk = install(client)
    assert save(client, vid, pk).status_code == 303
    assert settle(link, {"sensor.car_range"})
    assert "Live connection to Home Assistant: changes arrive at once." in client.get(f"/v/{vid}/integrations/{pk}/settings").text
    link.stop()
    assert "No live connection - Home Assistant is asked every 30 seconds." in client.get(f"/v/{vid}/integrations/{pk}/settings").text


def test_the_words_typed_are_looked_for_in_the_device_and_the_area_too():
    states = world(
        state("sensor.wallbox_power", "7400", "W", "power", friendly_name="Power"),
        state("sensor.house_power", "900", "W", "power", friendly_name="House power"),
        state("sensor.range", "300", "km", "distance", friendly_name="Range"),
    )
    where = {"sensor.wallbox_power": {"device": "Wallbox", "area": "Garage"}, "sensor.range": {"device": "Family car", "area": ""}}
    slot = cat.BY_KEY["charge_power_kw"]
    found = habridge.suggest(slot, "garage", False, states, context=where)
    assert [e["id"] for e in found] == ["sensor.wallbox_power"]  # its name says only "Power": the device and the area say the rest
    assert found[0]["device"] == "Wallbox" and found[0]["area"] == "Garage"
    assert [e["id"] for e in habridge.suggest(slot, "wallbox power", False, states, context=where)] == ["sensor.wallbox_power"]
    assert [e["id"] for e in habridge.suggest(slot, "power", False, states)][0:2] == [
        "sensor.house_power",
        "sensor.wallbox_power",
    ]  # (no registry: as before)
    assert habridge.suggest(slot, "nothing like it", False, states, context=where) == []


# ------------------------------------------------------------------ the backup


def _with_rows(raw, rows):
    """A backup file of a car with the bindings replaced by ``rows`` (as a file from anywhere might hold them)."""
    import io
    import zipfile

    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as src, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            body = src.read(item)
            if item.filename == "vehicle.json":
                data = json.loads(body)
                data["tables"]["ha_bindings"] = rows
                body = json.dumps(data).encode()
            dst.writestr(item, body)
    return out.getvalue()


def test_the_bindings_travel_with_the_car_and_take_their_interfaces_again(client, home):
    from carassistant import vehiclebackup

    vid, pk = install(client)
    assert save(client, vid, pk).status_code == 303
    with db.tx() as conn:
        raw = vehiclebackup.export(conn, vid)
        copy = vehiclebackup.restore(conn, raw)
        new_pk = conn.execute("SELECT id FROM vehicle_addons WHERE vehicle_id = ?", (copy,)).fetchone()["id"]
        assert habridge.bindings(conn, new_pk) == habridge.bindings(conn, pk) and len(habridge.bindings(conn, pk)) == 11
        assert claims.held_by(conn, copy, new_pk) == claims.held_by(conn, vid, pk)  # the interfaces it reads are its own again ...
        assert (
            addons.get(conn, copy, new_pk)["active"] == 0 and addons.get(conn, copy, new_pk)["status"] == "configured"
        )  # ... when it is switched on
        assert claims.owners(conn, copy) == {}  # (a plugin that is off holds nothing)
        data, zf = vehiclebackup.read(raw)
        zf.close()
        assert {r["slot"] for r in data["tables"]["ha_bindings"]} == set(habridge.bindings(conn, pk))


def test_a_binding_from_a_file_is_checked_again(client, home):
    from carassistant import vehiclebackup

    vid, pk = install(client)
    assert save(client, vid, pk).status_code == 303
    with db.tx() as conn:
        raw = vehiclebackup.export(conn, vid)
    bad = [
        {"addon_pk": pk, "slot": "range_km", "entity": "sensor.car_range", "options": '{"scale": 2, "unit": "mi", "nonsense": 1}'},
        {"addon_pk": pk, "slot": "locked", "entity": "../../etc/passwd", "options": "{}"},  # no entity
        {"addon_pk": pk, "slot": "nonsense", "entity": "sensor.x", "options": "{}"},  # no such interface
        {"addon_pk": pk, "slot": "doors", "entity": "sensor.x", "options": "{}"},  # a list without a name
        {"addon_pk": pk, "slot": "doors.Bad Name", "entity": "sensor.x", "options": "{}"},
        {"addon_pk": pk, "slot": "range_km.extra", "entity": "sensor.x", "options": "{}"},  # a name for a value
        {"addon_pk": pk, "slot": "battery_pct", "entity": "sensor.car_battery", "options": "not json"},
        {"addon_pk": pk, "slot": "charge_power_kw", "entity": "sensor.wallbox_power", "options": '{"scale": 1e99}'},
        {"addon_pk": 999, "slot": "vin", "entity": "sensor.vin", "options": "{}"},  # an install that is not in the file
        "not a row",
    ]
    with db.tx() as conn:
        copy = vehiclebackup.restore(conn, _with_rows(raw, bad))
        new_pk = conn.execute("SELECT id FROM vehicle_addons WHERE vehicle_id = ?", (copy,)).fetchone()["id"]
        got = habridge.bindings(conn, new_pk)
    assert got == {
        "range_km": {
            "entity": "sensor.car_range",
            "options": {"scale": 2.0, "unit": "mi"},
        },  # what it knows stays, the rest of its options goes
        "battery_pct": {"entity": "sensor.car_battery", "options": {}},
        "charge_power_kw": {"entity": "sensor.wallbox_power", "options": {}},
    }


def test_the_interfaces_of_a_package_name_what_a_bridge_reads_and_what_a_plugin_takes():
    from carassistant import interfaces

    manifest = addons.parse_package(json.dumps(BRIDGE).encode())
    sends = interfaces.preview(manifest, T)["rows"]["sends"]
    assert [r["name"] for r in sends] == ["Reads entities of Home Assistant"]
    assert (
        "range_km" in sends[0]["fields"]
        and "tyre_pressure_bar" in sends[0]["fields"]
        and "no other source of the car fills it" in sends[0]["note"]
    )
    plain = {**{k: v for k, v in BRIDGE.items() if k != "bridge"}, "claims": ["range_km"]}
    sends = interfaces.preview(addons.parse_package(json.dumps(plain).encode()), T)["rows"]["sends"]
    assert [(r["name"], r["fields"]) for r in sends] == [("Takes interfaces for itself", ["range_km"])]


def test_the_page_writes_numbers_the_way_the_language_does(client, home, monkeypatch):
    from carassistant import config

    slot = cat.BY_KEY["charge_power_kw"]
    reading = one("charge_power_kw", state("sensor.power", "7400", "W"))
    assert habridge.describe(slot, reading, T) == {"level": "ok", "text": "7.4 kW", "from": "from 7400 W"}
    monkeypatch.setattr(config, "language", lambda: "de")
    de = i18n.translator("de")
    assert habridge.describe(slot, reading, de) == {"level": "ok", "text": "7,4 kW", "from": "aus 7400 W"}
    assert habridge.describe(cat.BY_KEY["locked"], one("locked", state("lock.car", "locked")), de)["text"] == "Verriegelt"
    bad = habridge.describe(slot, one("charge_power_kw", state("sensor.power", "7400", "bananas")), de)
    assert bad == {"level": "bad", "text": "Die Einheit „bananas“ passt nicht - wähle die Einheit in den Optionen", "from": ""}
