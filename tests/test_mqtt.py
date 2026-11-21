import json

from carassistant import connectors, mqtt_ha


class FakeClient:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    def publish(self, topic, payload=None, retain=False):
        self.sent.append((topic, payload))

        class _R:
            def wait_for_publish(self, *_a):
                return True

        return _R()


def _publisher():
    pub = mqtt_ha.Publisher()
    pub._client = FakeClient()
    pub._connected.set()
    return pub


def _row(conn, vehicle):
    return conn.execute("SELECT * FROM vehicles WHERE id = ?", (vehicle,)).fetchone()


def test_live_sensors_appear_only_when_the_car_delivers_them(conn, vehicle):
    row = _row(conn, vehicle)
    keys = {s.key for s in mqtt_ha.wanted_sensors(row, mqtt_ha.compute_values(conn, row))}
    assert "odometer" in keys and "ignition" not in keys and "tyre_fl" not in keys and "doors" not in keys
    connectors.ingest(
        conn,
        vehicle,
        {"ignition": True, "doors": {"front_left": True, "rear_left": False}, "tyre_pressure_bar": {"fl": 2.4}, "locked": False},
        "test",
    )
    values = mqtt_ha.compute_values(conn, row)
    assert values["ignition"] == "ON" and values["doors"] == "ON" and values["tyre_fl"] == "2.40" and values["locked"] == "ON"
    keys = {s.key for s in mqtt_ha.wanted_sensors(row, values)}
    assert {"ignition", "doors", "tyre_fl", "locked"} <= keys and "tyre_rr" not in keys


def test_rare_values_are_created_switched_off_or_as_diagnostics(conn, vehicle):
    row = _row(conn, vehicle)
    speed = mqtt_ha.discovery_payload(row, mqtt_ha.BY_KEY["speed_kmh"])
    assert speed["enabled_by_default"] is False and speed["device_class"] == "speed"
    volt = mqtt_ha.discovery_payload(row, mqtt_ha.BY_KEY["battery_12v_v"])
    assert volt["entity_category"] == "diagnostic" and "enabled_by_default" not in volt
    assert mqtt_ha.discovery_payload(row, mqtt_ha.BY_KEY["tyre_fl"])["unit_of_measurement"] == "bar"
    assert mqtt_ha.discovery_payload(row, mqtt_ha.BY_KEY["odometer"])["has_entity_name"] is True


def test_the_position_becomes_a_device_tracker_with_attributes(conn, vehicle):
    row = _row(conn, vehicle)
    assert mqtt_ha.position_attributes(conn, row) is None
    connectors.ingest(conn, vehicle, {"position": {"lat": 48.5, "lon": 9.25}, "speed_kmh": 50, "heading_deg": 90}, "test")
    attrs = mqtt_ha.position_attributes(conn, row)
    assert attrs["latitude"] == 48.5 and attrs["longitude"] == 9.25 and attrs["speed"] == 50 and attrs["heading"] == 90
    payload = mqtt_ha.tracker_payload(row)
    assert payload["source_type"] == "gps" and payload["json_attributes_topic"] == f"carassistant/{vehicle}/position/attributes"
    pub = _publisher()
    pub.publish_vehicle(conn, row)
    topics = dict(pub._client.sent)
    assert json.loads(topics[f"carassistant/{vehicle}/position/attributes"])["latitude"] == 48.5
    assert f"homeassistant/device_tracker/carassistant_{vehicle}/position/config" in topics


def test_nothing_is_sent_twice_until_asked(conn, vehicle):
    row = _row(conn, vehicle)
    pub = _publisher()
    pub.publish_vehicle(conn, row)
    first = len(pub._client.sent)
    assert first > 0
    pub.publish_vehicle(conn, row)
    assert len(pub._client.sent) == first  # same values: the broker is not bothered again
    pub.resend()
    pub.publish_vehicle(conn, row)
    assert len(pub._client.sent) == 2 * first


def test_switching_off_removes_the_entities(conn, vehicle):
    pub = _publisher()
    pub.remove_all(conn)
    empties = [t for t, p in pub._client.sent if p == ""]
    assert any(t.endswith(f"carassistant_{vehicle}/odometer/config") for t in empties)
    assert any("device_tracker" in t for t in empties)


def test_the_switch_is_there_with_and_without_a_broker(client, monkeypatch):
    assert 'name="enabled"' in client.get("/settings/system").text.split('id="mqtt"')[1].split("</section>")[0]
    monkeypatch.setenv("MQTT_HOST", "core-mosquitto")
    assert 'name="enabled"' in client.get("/settings/system").text.split('id="mqtt"')[1].split("</section>")[0]
