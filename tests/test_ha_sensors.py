"""What goes to Home Assistant: the app's own records as sensors, the rough groups, the rebuild (also when a car is renamed), the German names and
the *Check Home Assistant* button."""

import json
from datetime import date, timedelta

import pytest
from tests.test_mqtt import _publisher, _row
from tests.test_web import create_vehicle

from carassistant import config, db, hacheck, mqtt_ha, summary

REF = date(2026, 11, 23)


def _records(conn, vid):
    summary.add_odometer(conn, vid, 51000)
    conn.execute(
        "INSERT INTO fuel(vehicle_id, date, odometer_km, amount, price_per_unit, price_total, full_tank) VALUES(?, '2026-10-01', 50000, 40, 1.8, 72, 1)",
        (vid,),
    )
    conn.execute(
        "INSERT INTO fuel(vehicle_id, date, odometer_km, amount, price_per_unit, price_total, full_tank) VALUES(?, '2026-11-10', 50700, 45.5, 1.7, 77.35, 1)",
        (vid,),
    )
    conn.execute("INSERT INTO tasks(vehicle_id, title, interval_months, last_date) VALUES(?, 'Oil', 12, '2026-01-10')", (vid,))
    conn.execute(
        "INSERT INTO appointments(vehicle_id, kind, title, due_date, done) VALUES(?, 'other', 'Brakes', ?, 0)",
        (vid, (REF + timedelta(days=9)).isoformat()),
    )
    conn.execute(
        "INSERT INTO trips(vehicle_id, date, start_place, end_place, distance_km, source) VALUES(?, '2026-11-20', 'Home', 'Office', 23.4, 'manual')",
        (vid,),
    )
    conn.execute("INSERT INTO tires(vehicle_id, name, season, size, mounted) VALUES(?, 'Winter', 'winter', '205/55 R16', 1)", (vid,))


def _stats_on(conn=None):
    if conn is not None:
        conn.commit()  # the setting is written by its own connection
    with db.tx() as c:
        db.set_setting(c, "int.mqtt.group.stats", "1")
    config.forget_settings()


def test_the_apps_own_records_become_sensors_and_nothing_is_empty(conn, vehicle):
    _records(conn, vehicle)
    row = _row(conn, vehicle)
    values = mqtt_ha.compute_values(conn, row, REF)
    assert values["last_fill_date"] == "2026-11-10" and values["last_fill_amount"] == "45.50" and values["last_fill_price"] == "1.700"
    assert values["next_appointment_days"] == "9" and values["last_trip_km"] == "23.4" and values["tires_mounted"] == "Winter 205/55 R16"
    assert values["fuel_spent_total"] == "149.35" and values["next_task_days"] is not None
    keys = {s.key for s in mqtt_ha.wanted_sensors(row, values)}
    assert {"odometer", "next_task_days", "next_appointment_days", "tires_mounted", "avg_consumption"} <= keys  # the everyday groups are on
    assert not {"last_fill_date", "costs_year", "last_trip_km"} & keys  # the extra statistics wait until somebody wants them
    _stats_on(conn)
    keys = {s.key for s in mqtt_ha.wanted_sensors(row, values)}
    assert {"last_fill_date", "last_fill_amount", "costs_year", "last_trip_km", "fuel_spent_total"} <= keys


def test_a_sensor_without_a_value_is_never_created(conn, vehicle):
    _stats_on(conn)
    row = _row(conn, vehicle)
    keys = {s.key for s in mqtt_ha.wanted_sensors(row, mqtt_ha.compute_values(conn, row, REF))}
    assert keys <= {"attention", "attention_count", "last_notification"}  # a car with no records: no empty entity


def test_the_attributes_say_more_than_the_number(conn, vehicle):
    _records(conn, vehicle)
    row = _row(conn, vehicle)
    task = mqtt_ha.sensor_attributes(conn, row, "next_task_days")
    assert task["task"] == "Oil" and task["due_date"].startswith("2027-01")
    appointment = mqtt_ha.sensor_attributes(conn, row, "next_appointment_days")
    assert appointment["title"] == "Brakes" and appointment["kind"] == "other"
    trip = mqtt_ha.sensor_attributes(conn, row, "last_trip_km")
    assert trip["from"] == "Home" and trip["to"] == "Office"


def test_the_units_follow_the_car_and_the_currency(conn, vehicle):
    row = _row(conn, vehicle)
    assert mqtt_ha.discovery_payload(row, mqtt_ha.BY_KEY["fuel_spent_total"])["unit_of_measurement"] == "EUR"
    assert mqtt_ha.discovery_payload(row, mqtt_ha.BY_KEY["last_fill_amount"])["unit_of_measurement"] == "L"
    assert mqtt_ha.discovery_payload(row, mqtt_ha.BY_KEY["last_fill_price"])["unit_of_measurement"] == "EUR/L"
    assert mqtt_ha.discovery_payload(row, mqtt_ha.BY_KEY["cost_per_100km"])["unit_of_measurement"] == "EUR/100 km"


def test_the_groups_default_to_what_was_there_before_and_can_be_switched(client):
    assert config.ha_groups_off() == {"stats"}
    r = client.post("/settings/mqtt-groups", data={"g_live": "1"}, headers={"Origin": "http://testserver"})
    assert r.status_code == 303
    assert config.ha_groups_off() == {"service", "fuel", "stats", "position"}
    client.post("/settings/mqtt-groups", data={f"g_{g}": "1" for g in config.HA_GROUPS}, headers={"Origin": "http://testserver"})
    assert config.ha_groups_off() == set()


def test_a_group_that_is_off_takes_its_sensors_and_the_position_away(conn, vehicle):
    from carassistant import connectors

    connectors.ingest(conn, vehicle, {"position": {"lat": 48.5, "lon": 9.25}, "ignition": True}, "test")
    row = _row(conn, vehicle)
    pub = _publisher()
    pub.publish_vehicle(conn, row)
    sent = dict(pub._client.sent)
    assert (
        sent[f"homeassistant/device_tracker/carassistant_{vehicle}/position/config"]
        and sent[f"homeassistant/binary_sensor/carassistant_{vehicle}/ignition/config"]
    )
    conn.commit()
    with db.tx() as c:
        db.set_setting(c, "int.mqtt.group.position", "0")
        db.set_setting(c, "int.mqtt.group.live", "0")
    config.forget_settings()
    pub._client.sent.clear()
    pub.publish_vehicle(conn, row)
    sent = dict(pub._client.sent)
    assert sent[f"homeassistant/device_tracker/carassistant_{vehicle}/position/config"] == ""
    assert sent[f"homeassistant/binary_sensor/carassistant_{vehicle}/ignition/config"] == ""


def test_a_rebuild_takes_the_entities_out_waits_and_puts_them_back(conn, vehicle):
    row = _row(conn, vehicle)
    pub = _publisher()
    pub.publish_vehicle(conn, row)
    pub._client.sent.clear()
    assert pub.rebuild([vehicle], wait=60) is True
    gone = {t: p for t, p in pub._client.sent}
    assert gone[f"homeassistant/sensor/carassistant_{vehicle}/odometer/config"] == "" or any(
        t.endswith("/config") and p == "" for t, p in gone.items()
    )
    assert all(p == "" for t, p in pub._client.sent if t.endswith("/config"))
    pub._client.sent.clear()
    pub.publish_vehicle(conn, row)
    assert pub._client.sent == []  # while Home Assistant forgets them nothing is sent
    pub._after_rebuild()
    pub.publish_vehicle(conn, row)
    assert any(t.endswith("/config") and p for t, p in pub._client.sent)  # and then they come back, with the names as they are now


def test_a_rebuild_needs_a_connected_broker():
    pub = mqtt_ha.Publisher()
    assert pub.rebuild([1]) is False


def test_the_rebuild_button_and_a_rename(client, monkeypatch):
    from carassistant import web

    vid = create_vehicle(client, "Demo Diesel")
    calls = []
    monkeypatch.setattr(web.publisher, "rebuild", lambda ids, **kw: calls.append(list(ids)) or True)
    r = client.post("/settings/mqtt-rebuild", headers={"Origin": "http://testserver"})
    assert r.status_code == 303 and "mqtt_rebuilt" in r.headers["location"] and calls == [[vid]]
    client.post(f"/v/{vid}/edit", data={"name": "Demo Diesel", "fuel_type": "diesel"}, headers={"Origin": "http://testserver"})
    assert calls == [[vid]]  # the same name: nothing is rebuilt
    client.post(f"/v/{vid}/edit", data={"name": "Family Car", "fuel_type": "diesel"}, headers={"Origin": "http://testserver"})
    assert calls[-1] == [vid] and len(calls) == 2  # a new name: this car's entities are made anew, so the IDs follow the name
    monkeypatch.setattr(web.publisher, "rebuild", lambda ids, **kw: False)
    r = client.post("/settings/mqtt-rebuild", headers={"Origin": "http://testserver"})
    assert "err.mqtt_not_connected" in r.headers["location"]


def test_every_sensor_has_a_german_name_and_the_names_are_unique():
    english = [s.name for s in mqtt_ha.SENSORS]
    assert len(set(english)) == len(english)  # two sensors with one name would get IDs with _2
    german = [mqtt_ha.NAMES_DE.get(n) for n in english]
    assert None not in german and len(set(german)) == len(german), [n for n in english if n not in mqtt_ha.NAMES_DE]


def test_the_german_names_go_to_home_assistant_when_the_language_is_german(conn, vehicle):
    conn.commit()
    with db.tx() as c:
        db.set_setting(c, "language", "de")
    config.forget_settings()
    row = _row(conn, vehicle)
    assert mqtt_ha.discovery_payload(row, mqtt_ha.BY_KEY["odometer"])["name"] == "Kilometerstand"
    assert mqtt_ha.discovery_payload(row, mqtt_ha.BY_KEY["last_notification"])["name"] == "Letzte Benachrichtigung"


# ------------------------------------------------------------------ Check Home Assistant


@pytest.fixture()
def ha_world(env, monkeypatch):
    """A car, a connected (fake) broker and a fake Home Assistant that shows what was published."""
    monkeypatch.setenv("MQTT_HOST", "broker.lan")
    monkeypatch.setenv("MQTT_SENSORS", "1")
    pub = _publisher()
    monkeypatch.setattr(mqtt_ha, "publisher", pub)
    monkeypatch.setattr(hacheck.mqtt_ha, "publisher", pub)
    monkeypatch.setattr(hacheck.time, "sleep", lambda s: None)
    monkeypatch.setattr(hacheck.ha, "available", lambda: True)
    monkeypatch.setattr(hacheck.ha, "_get", lambda path: {"version": "x"} if path == "/config" else [])
    with db.tx() as c:
        vid = c.execute("INSERT INTO vehicles(name, fuel_type) VALUES('Plain Car', 'petrol')").lastrowid
        summary.add_odometer(c, vid, 1000)
    return pub, vid


def _ha_shows(monkeypatch, vid, name="Plain Car", arrived=True):
    def states():
        if not arrived:
            return []
        with db.tx() as c:
            rec = mqtt_ha.notice_record(c, vid)
        return [
            {
                "entity_id": "sensor.plain_car_last_notification",
                "state": rec["text"],
                "attributes": {"friendly_name": f"{name} Last notification"},
            },
            {"entity_id": "sensor.plain_car_odometer", "state": "1000", "attributes": {"friendly_name": f"{name} Odometer"}},
        ]

    monkeypatch.setattr(hacheck, "_states", states)


def test_the_check_follows_a_message_all_the_way_to_home_assistant(ha_world, monkeypatch):
    pub, vid = ha_world
    _ha_shows(monkeypatch, vid)
    result = hacheck.run(wait=1)
    assert [s["key"] for s in result["steps"]] == ["api_ok", "mqtt_ok", "sent"] and all(s["ok"] for s in result["steps"])
    car = result["cars"][0]
    assert (
        car["ok"]
        and car["entity"] == "sensor.plain_car_last_notification"
        and car["found"] == 2
        and car["total"] == 4
        and "sensor.plain_car_odometer" in car["entities"]
    )
    assert any(t.endswith("/last_notification/state") for t, _p in pub._client.sent)


def test_the_check_says_when_nothing_arrived(ha_world, monkeypatch):
    _pub, vid = ha_world
    _ha_shows(monkeypatch, vid, arrived=False)
    car = hacheck.run(wait=1)["cars"][0]
    assert car["ok"] is False and car["found"] == 0


def test_the_check_says_where_it_stops(env, monkeypatch):
    monkeypatch.setattr(hacheck.ha, "available", lambda: False)
    steps = hacheck.run(wait=1)["steps"]
    assert steps[0] == {"ok": False, "key": "api_no"} and steps[1]["key"] == "mqtt_off"
    monkeypatch.setenv("MQTT_SENSORS", "1")
    assert hacheck.run(wait=1)["steps"][1]["key"] == "mqtt_nobroker"
    monkeypatch.setenv("MQTT_HOST", "broker.lan")
    pub = mqtt_ha.Publisher()
    pub.last_error = "auth"
    monkeypatch.setattr(hacheck.mqtt_ha, "publisher", pub)
    down = hacheck.run(wait=1)["steps"][1]
    assert down["key"] == "mqtt_down" and down["reason"] == "auth"


def test_the_system_page_shows_the_switches_and_the_result(ha_world, monkeypatch, client):
    _pub, vid = ha_world
    with db.tx() as c:
        db.set_setting(c, "setup.language", "1")
    _ha_shows(monkeypatch, vid)
    r = client.post("/settings/mqtt-check", headers={"Origin": "http://testserver"})
    assert r.status_code == 303
    page = client.get("/settings/system").text
    assert 'id="mqtt-groups"' in page and "sensor.plain_car_last_notification" in page and "2 of 4 sensors found" in page
    assert json.loads(json.dumps(hacheck.last))["steps"][0]["key"] == "api_ok"
