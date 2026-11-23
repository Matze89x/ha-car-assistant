from datetime import UTC, datetime, timedelta

from carassistant import calendar_ics, mqtt_ha, notify, stations, summary


def test_mqtt_values_and_payloads(conn, vehicle, monkeypatch):
    conn.execute("UPDATE vehicles SET make='Acme', model='Roadster', fuel_type='diesel', bind_range='sensor.r' WHERE id=?", (vehicle,))
    summary.add_odometer(conn, vehicle, 12345)
    conn.execute("INSERT INTO appointments(vehicle_id, title, due_date, kind) VALUES(?, 'HU', '2000-01-01', 'inspection')", (vehicle,))
    row = conn.execute("SELECT * FROM vehicles").fetchone()
    values = mqtt_ha.compute_values(conn, row)
    assert values["odometer"] == "12345" and values["attention"] == "ON" and values["attention_count"] == "1"
    assert values["inspection_date"] == "2000-01-01" and values["fuel_level"] is None
    keys = {s.key for s in mqtt_ha.wanted_sensors(row)}
    assert "range_km" in keys and "fuel_level" not in keys
    sensor = next(s for s in mqtt_ha.SENSORS if s.key == "avg_consumption")
    payload = mqtt_ha.discovery_payload(row, sensor)
    assert payload["unit_of_measurement"] == "L/100km" and payload["device"]["manufacturer"] == "Acme"
    assert payload["unique_id"] == f"carassistant_{vehicle}_avg_consumption"
    assert mqtt_ha.discovery_topic(vehicle, sensor).startswith("homeassistant/sensor/carassistant_")


def test_notify_sends_once_per_repeat_window(conn, vehicle, monkeypatch):
    from carassistant import accounts, ha

    uid = accounts.create_user(conn, "owner", "correct horse battery staple", admin=True)
    notify.save_service(conn, uid, "mobile_app_x")
    conn.execute("UPDATE user_notify SET events = ? WHERE user_id = ?", ('["appointment"]', uid))
    conn.commit()
    calls = []
    monkeypatch.setattr(ha, "network_port", lambda: (True, None))  # no port: Home Assistant service
    monkeypatch.setattr(notify.ha, "call_service", lambda d, s, data: calls.append((d, s, data)) or (True, ""))
    conn.execute("INSERT INTO appointments(vehicle_id, title, due_date) VALUES(?, 'HU', '2000-01-01')", (vehicle,))
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert notify.check_all(conn, now) == 1
    assert calls[0][:2] == ("notify", "mobile_app_x") and "HU" in calls[0][2]["message"]
    assert notify.check_all(conn, now + timedelta(days=1)) == 0
    assert notify.check_all(conn, now + timedelta(days=4)) == 1


def test_a_notification_opens_the_page_of_its_topic_in_that_car(conn, vehicle, monkeypatch):
    from carassistant import accounts, config, ha

    uid = accounts.create_user(conn, "owner", "correct horse battery staple", admin=True)
    notify.save_service(conn, uid, "mobile_app_x")
    conn.execute("UPDATE user_notify SET events = ? WHERE user_id = ?", ('["appointment", "tyre_pressure"]', uid))
    conn.commit()
    calls = []
    monkeypatch.setattr(ha, "network_port", lambda: (True, None))
    monkeypatch.setattr(config, "external_url", lambda: "https://car.example.com/")
    monkeypatch.setattr(notify.ha, "call_service", lambda d, s, data: calls.append(data) or (True, ""))
    conn.execute("INSERT INTO appointments(vehicle_id, title, due_date) VALUES(?, 'HU', '2000-01-01')", (vehicle,))
    conn.execute("UPDATE vehicles SET slug = 'my-car' WHERE id = ?", (vehicle,))
    slug = "my-car"
    assert notify.check_all(conn, datetime(2026, 1, 1, tzinfo=UTC)) == 1
    assert calls[0]["data"]["url"] == f"https://car.example.com/v/{slug}/e/appointments"  # one topic: straight to its page
    row = conn.execute("SELECT * FROM vehicles WHERE id = ?", (vehicle,)).fetchone()
    assert notify.link_for(row, {"/e/tires", "/e/trips"}) == f"https://car.example.com/v/{slug}"  # several topics: the car
    monkeypatch.setattr(config, "external_url", lambda: "")
    assert notify.link_for(row, {"/e/tires"}) == ""  # no saved address: nothing to link to


def test_notify_disabled_without_service(conn, vehicle):
    conn.execute("INSERT INTO appointments(vehicle_id, title, due_date) VALUES(?, 'HU', '2000-01-01')", (vehicle,))
    assert notify.check_all(conn) == 0


def test_ics_escaping_and_folding(conn, vehicle):
    conn.execute(
        "INSERT INTO appointments(vehicle_id, title, due_date, notes) VALUES(?, ?, '2027-03-31', 'a,b;c')", (vehicle, "HU " + "ä" * 60)
    )
    text = calendar_ics.build(conn).decode("utf-8")
    assert text.startswith("BEGIN:VCALENDAR") and "DTSTART;VALUE=DATE:20270331" in text
    assert "a\\,b\\;c" in text
    assert all(len(line.encode("utf-8")) <= 75 for line in text.split("\r\n"))


SAMPLE_TK = {
    "ok": True,
    "stations": [
        {
            "name": "A",
            "brand": "Aral",
            "street": "Main",
            "houseNumber": "1",
            "postCode": 10115,
            "place": "Berlin",
            "lat": 52.5,
            "lng": 13.4,
            "dist": 2.0,
            "e5": 1.80,
            "isOpen": True,
        },
        {"name": "B", "brand": "Shell", "lat": 52.51, "lng": 13.41, "dist": 1.0, "e5": 1.70, "isOpen": False},
        {"name": "C", "brand": "X", "lat": 52.52, "lng": 13.42, "dist": 0.5, "e5": None, "isOpen": True},
    ],
}


def test_station_sorting_and_normalisation():
    stations_list = stations.normalize_tankerkoenig(SAMPLE_TK, "e5", (52.5, 13.4))
    assert [s.name for s in stations.sort_stations(stations_list, "price")] == ["B", "A", "C"]
    assert [s.name for s in stations.sort_stations(stations_list, "distance")] == ["C", "B", "A"]
    assert stations_list[0].address == "Main 1, 10115 Berlin"


def test_overpass_normalisation_and_param_validation():
    data = {
        "elements": [
            {"lat": 52.5, "lon": 13.4, "tags": {"name": "N", "addr:street": "S"}},
            {"center": {"lat": 52.6, "lon": 13.5}, "tags": {"brand": "B"}},
            {"tags": {}},
        ]
    }
    result = stations.normalize_overpass(data, (52.5, 13.4))
    assert [s.name for s in result] == ["N", "B"]
    import pytest

    with pytest.raises(stations.StationsError):
        stations.clean_params(95, 0, 5)
    assert stations.clean_params(1, 1, 999)[2] == stations.MAX_RADIUS_KM


def test_tankerkoenig_requires_key(env):
    import pytest

    with pytest.raises(stations.StationsError, match=r"err\.no_key"):
        stations.fetch_tankerkoenig(52.5, 13.4, 5, "e5")


def test_published_port_from_supervisor(monkeypatch):
    from carassistant import ha

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": {"network": {"8099/tcp": 8321}}}

    monkeypatch.setenv("SUPERVISOR_TOKEN", "t")
    monkeypatch.setattr(ha.requests, "get", lambda *a, **k: Resp())
    assert ha.published_port() == 8321


def test_a_function_that_is_switched_off_raises_nothing(conn, vehicle):
    from carassistant import modules

    conn.execute("INSERT INTO appointments(vehicle_id, title, due_date, kind) VALUES(?, 'HU', '2000-01-01', 'inspection')", (vehicle,))
    summary.add_odometer(conn, vehicle, 1000)
    row = conn.execute("SELECT * FROM vehicles").fetchone()
    assert summary.attention_items(conn, vehicle) and summary.next_inspection(conn, vehicle)

    def keys():
        return {s.key for s in mqtt_ha.wanted_sensors(row, mqtt_ha.compute_values(conn, row), modules.disabled(conn, vehicle))}

    assert "inspection_days" in keys()
    modules.set_vehicle_enabled(conn, vehicle, "appointments", False)
    assert summary.attention_items(conn, vehicle) == [] and summary.next_inspection(conn, vehicle) is None
    assert summary.vehicle_summary(conn, row)["inspection"] is None
    assert "inspection_days" not in keys() and "inspection_date" not in keys() and "odometer" in keys()


def test_the_mqtt_switch_alone_keeps_the_own_broker(client):
    from carassistant import config, db

    client.post("/integrations/mqtt", data={"host": "192.168.1.5", "port": "1883", "username": "u", "enabled": "1", "back": "system"})
    client.post("/integrations/mqtt", data={"toggle_only": "1", "back": "system"})  # the switch moved to "no": nothing else is touched
    config.forget_settings()
    with db.tx() as conn:
        assert db.get_setting(conn, "int.mqtt.enabled") == "0" and db.get_setting(conn, "int.mqtt.host") == "192.168.1.5"
        assert db.get_setting(conn, "int.mqtt.username") == "u"
