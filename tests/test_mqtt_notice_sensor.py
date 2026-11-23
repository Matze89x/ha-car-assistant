"""The sensor *Last notification* of every car in Home Assistant: fed by what the app announces, whether or not anybody set up notifications."""

import json
from datetime import UTC, datetime, timedelta

from tests.test_mqtt import _publisher, _row

from carassistant import config, db, mqtt_ha, notify

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)


def _overdue_task(conn, vehicle):
    conn.execute("INSERT INTO tasks(vehicle_id, title, interval_months, last_date) VALUES(?, 'Oil', 12, '2020-01-01')", (vehicle,))


def _on(monkeypatch, pub=None):
    pub = pub or _publisher()
    monkeypatch.setenv("MQTT_SENSORS", "1")
    monkeypatch.setattr(mqtt_ha, "publisher", pub)
    return pub


def test_the_sensor_exists_but_stays_unknown_until_something_was_announced(conn, vehicle, monkeypatch):
    pub = _on(monkeypatch)
    row = _row(conn, vehicle)
    assert "last_notification" in {s.key for s in mqtt_ha.wanted_sensors(row, mqtt_ha.compute_values(conn, row))}
    pub.publish_vehicle(conn, row)
    topics = [t for t, _p in pub._client.sent]
    assert any(t.endswith("/last_notification/config") for t in topics)  # the entity is there for automations to be built on
    assert not any(t.endswith("/last_notification/state") for t in topics)  # but has no value yet


def test_an_announcement_without_any_user_reaches_the_sensor_once(conn, vehicle, monkeypatch):
    pub = _on(monkeypatch)
    _overdue_task(conn, vehicle)
    assert notify.check_users(conn, NOW) == 1  # nobody set up a way to be notified: Home Assistant still gets it
    sent = dict(pub._client.sent)
    state = sent[mqtt_ha.state_topic(vehicle, "last_notification")]
    attrs = json.loads(sent[mqtt_ha.sensor_attributes_topic(vehicle, "last_notification")])
    assert "Oil" in state and attrs["count"] == 1 and attrs["lines"] and attrs["time"].startswith("2026-11-23")
    assert notify.check_users(conn, NOW + timedelta(hours=6)) == 0  # told already: not again
    assert json.loads(db.get_setting(conn, f"mqtt.notice.{vehicle}"))["n"] == 1


def test_a_new_announcement_keeps_the_earlier_ones_as_history(conn, vehicle):
    for i in range(12):
        record = mqtt_ha.add_notice(conn, vehicle, [f"Message {i}"], NOW + timedelta(hours=i))
    assert record["n"] == 12 and record["text"] == "Message 11"
    assert len(record["history"]) == mqtt_ha.NOTICE_HISTORY - 1 and record["history"][0]["text"] == "Message 10"
    attrs = mqtt_ha.notice_attributes(record)
    assert attrs["message"] == "Message 11" and attrs["count"] == 12


def test_a_long_text_fits_a_home_assistant_state(conn, vehicle):
    record = mqtt_ha.add_notice(conn, vehicle, ["x" * 200, "y" * 200], NOW)
    assert len(record["text"]) <= 250 and len(mqtt_ha.notice_attributes(record)["message"]) == 401  # the full text stays in the attribute


def test_while_the_broker_is_not_reached_nothing_is_used_up(conn, vehicle, monkeypatch):
    pub = _publisher()
    pub._connected.clear()
    _on(monkeypatch, pub)
    _overdue_task(conn, vehicle)
    assert notify.check_users(conn, NOW) == 0 and mqtt_ha.notice_record(conn, vehicle) is None
    pub._connected.set()
    assert notify.check_users(conn, NOW) == 1  # it was waiting


def test_switched_off_there_is_no_entity_and_no_message(conn, vehicle, monkeypatch):
    pub = _on(monkeypatch)
    conn.commit()  # the setting is read by its own connection
    with db.tx() as other:
        db.set_setting(other, "int.mqtt.notice_sensor", "0")
    config.forget_settings()
    row = _row(conn, vehicle)
    assert "last_notification" not in {s.key for s in mqtt_ha.wanted_sensors(row, mqtt_ha.compute_values(conn, row))}
    _overdue_task(conn, vehicle)
    assert notify.check_users(conn, NOW) == 0 and not pub._client.sent


def test_the_discovery_names_the_attributes_topic():
    class Row(dict):
        pass

    row = Row(id=7, name="Car", make=None, model=None, variant=None, fuel_type="petrol")
    payload = mqtt_ha.discovery_payload(row, mqtt_ha.BY_KEY["last_notification"])
    assert payload["json_attributes_topic"] == "carassistant/7/last_notification/attributes" and payload["icon"] == "mdi:bell-outline"
    assert "json_attributes_topic" not in mqtt_ha.discovery_payload(row, mqtt_ha.BY_KEY["odometer"])


def test_the_switch_on_the_system_page_defaults_to_on_and_can_be_turned_off(client):
    from carassistant import db as _db

    with _db.tx() as c:
        _db.set_setting(c, "setup.language", "1")
    assert config.ha_notice_sensor_enabled() is True
    assert 'id="mqtt-notices"' in client.get("/settings/system").text
    client.post("/settings/mqtt-notices", data={}, headers={"Origin": "http://testserver"})
    assert config.ha_notice_sensor_enabled() is False
    client.post("/settings/mqtt-notices", data={"enabled": "1"}, headers={"Origin": "http://testserver"})
    assert config.ha_notice_sensor_enabled() is True
