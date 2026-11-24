"""What a connector can send through the interface and how the car shows it (the contract every plugin relies on)."""


def test_vehicle_messages_through_the_interface_and_home_widget(client):
    import re

    client.post("/vehicles", data={"name": "Msg", "fuel_type": "petrol"})
    from carassistant import connectors, db

    with db.tx() as conn:
        vid = conn.execute("SELECT id FROM vehicles WHERE name = 'Msg'").fetchone()["id"]
        token = connectors.create_token(conn, "Plugin", vid)
    h = {"Authorization": f"Bearer {token}"}
    ok = client.post(f"/api/v1/vehicles/{vid}/data", json={"warnings": {"tyre_pressure": "Tyre pressure low"}}, headers=h)
    assert ok.status_code == 200
    assert "Tyre pressure low" in client.get(f"/v/{vid}").text
    snap = client.get(f"/api/v1/vehicles/{vid}/data", headers=h).json()
    assert snap["data"]["warnings"] == {"tyre_pressure": "Tyre pressure low"}
    assert client.post(f"/api/v1/vehicles/{vid}/data", json={"warnings": {"tyre_pressure": None}}, headers=h).status_code == 200
    assert "Tyre pressure low" not in client.get(f"/v/{vid}").text
    assert client.post(f"/api/v1/vehicles/{vid}/data", json={"warnings": {"Bad Code": "x"}}, headers=h).status_code == 422
    assert re.search(r"data-live-poll", client.get(f"/v/{vid}").text)  # a vehicle with a connector gets live updates


def test_more_read_fields_and_the_debug_channel(client):
    from carassistant import connectors, db

    client.post("/vehicles", data={"name": "Dbg", "fuel_type": "electric"})
    with db.tx() as conn:
        vid = conn.execute("SELECT id FROM vehicles WHERE name = 'Dbg'").fetchone()["id"]
        token = connectors.create_token(conn, "Plugin", vid)
    h = {"Authorization": f"Bearer {token}"}
    body = {
        "speed_kmh": 72,
        "outside_temp_c": 4.5,
        "battery_12v_v": 12.7,
        "battery_pct": 63,
        "charging": True,
        "charge_power_kw": 11,
        "tyre_pressure_bar": {"fl": 2.4, "fr": 2.5, "rl": 2.3, "rr": 2.3},
    }
    r = client.post(f"/api/v1/vehicles/{vid}/data", json=body, headers=h)
    assert r.status_code == 200 and r.json()["control"] == {"debug": False, "interval_s": 120}
    snap = client.get(f"/api/v1/vehicles/{vid}/data", headers=h).json()["data"]
    assert snap["battery_pct"] == 63 and snap["charging"] is True and snap["tyre_pressure_bar"]["fl"] == 2.4
    home = client.get(f"/v/{vid}").text
    assert "72 km/h" in home and "4.5" in home and "Charging" in home and "2.4 · 2.5 · 2.3 · 2.3 bar" in home
    bad = client.post(f"/api/v1/vehicles/{vid}/data", json={"tyre_pressure_bar": {"xx": 2}}, headers=h)
    assert bad.status_code == 422
    # debug: refused while off, accepted while on, switched in the dashboard
    off = client.post(f"/api/v1/vehicles/{vid}/logs", json={"lines": ["hello"]}, headers=h)
    assert off.status_code == 409 and off.json()["error"] == "debug_off"
    client.post(f"/v/{vid}/debug", data={"on": "1"})
    assert client.get(f"/api/v1/vehicles/{vid}/control", headers=h).json()["control"] == {"debug": True, "interval_s": 120}
    assert client.post(f"/api/v1/vehicles/{vid}/data", json={}, headers=h).json()["control"] == {"debug": True, "interval_s": 120}
    ok = client.post(f"/api/v1/vehicles/{vid}/logs", json={"lines": ["hello", {"level": "warn", "message": "careful"}]}, headers=h)
    assert ok.status_code == 200 and ok.json()["stored"] == 2
    page = client.get(f"/v/{vid}/debug").text
    assert "hello" in page and "careful" in page
    assert client.post(f"/api/v1/vehicles/{vid}/logs", json={"lines": [{"message": "x", "level": "loud"}]}, headers=h).status_code == 422
    client.post(f"/v/{vid}/debug/clear")
    assert "careful" not in client.get(f"/v/{vid}/debug").text
    client.post(f"/v/{vid}/debug", data={"on": "0"})
    assert client.post(f"/api/v1/vehicles/{vid}/logs", json={"lines": ["late"]}, headers=h).status_code == 409


def test_the_typical_vehicle_signals(client):
    from carassistant import connectors, db

    client.post("/vehicles", data={"name": "Sig", "fuel_type": "petrol"})
    with db.tx() as conn:
        vid = conn.execute("SELECT id FROM vehicles WHERE name = 'Sig'").fetchone()["id"]
        token = connectors.create_token(conn, "Plugin", vid)
    h = {"Authorization": f"Bearer {token}"}
    body = {
        "coolant_temp_c": 90,
        "oil_temp_c": 95,
        "cabin_temp_c": 21,
        "target_temp_c": 22,
        "climate_on": True,
        "heading_deg": 270,
        "consumption_l_100km": 6.1,
        "service_due_days": 40,
        "service_due_km": -200,
        "plugged": False,
        "parking_brake": True,
        "lights": {"low_beam": True, "hazard": False},
    }
    assert client.post(f"/api/v1/vehicles/{vid}/data", json=body, headers=h).status_code == 200
    data = client.get(f"/api/v1/vehicles/{vid}/data", headers=h).json()["data"]
    assert data["climate_on"] is True and data["lights"] == {"low_beam": True, "hazard": False} and data["service_due_km"] == -200
    home = client.get(f"/v/{vid}").text
    for needle in ("90 °C", "Climate on", "Low beam", "in 40 d", "200 km overdue", "Parking brake"):
        assert needle in home, needle
    assert client.post(f"/api/v1/vehicles/{vid}/data", json={"climate_on": "yes"}, headers=h).status_code == 422
    assert client.post(f"/api/v1/vehicles/{vid}/data", json={"coolant_temp_c": 999}, headers=h).status_code == 422


def test_car_messages_and_service_count_as_open_points(client):
    from carassistant import connectors, db

    client.post("/vehicles", data={"name": "Cnt", "fuel_type": "petrol"})
    with db.tx() as conn:
        vid = conn.execute("SELECT id FROM vehicles WHERE name = 'Cnt'").fetchone()["id"]
        token = connectors.create_token(conn, "Plugin", vid)
    h = {"Authorization": f"Bearer {token}"}
    client.post(f"/api/v1/vehicles/{vid}/data", json={"service_due_days": 10, "warnings": {"washer_fluid": "Washer fluid low"}}, headers=h)
    home = client.get(f"/v/{vid}").text
    assert "2 open" in home and "Service due: in 10 d" in home
    sec = client.get(f"/v/{vid}/security").text
    assert "Vehicle messages" in sec and "Washer fluid low" in sec
    assert 'data-alert="1"' in home  # the dot on the Security tab
    client.post(f"/api/v1/vehicles/{vid}/data", json={"service_due_days": 200, "warnings": {"washer_fluid": None}}, headers=h)
    assert "Service due" not in client.get(f"/v/{vid}").text


def test_logs_belong_to_their_plugin_are_limited_by_the_setting_and_go_with_it(client):
    import json as _json

    from carassistant import addons, connectors, db

    client.post("/vehicles", data={"name": "Log Car", "fuel_type": "petrol"})
    with db.tx() as conn:
        vid = conn.execute("SELECT id FROM vehicles ORDER BY id DESC LIMIT 1").fetchone()["id"]
    tokens = {}
    for name in ("alpha", "beta"):
        manifest = addons.parse_package(_json.dumps({"id": f"{name}-plug", "kind": "plugin", "name": name.title()}).encode())
        with db.tx() as conn:
            pk = addons.add(conn, vid, manifest)
            addon = addons.get(conn, vid, pk)
            tokens[name] = addons.set_up(conn, vid, addon, {})
    client.post(f"/v/{vid}/debug", data={"on": "1"})
    for name, token in tokens.items():
        lines = [{"message": f"{name} {i}"} for i in range(30)]
        assert (
            client.post(f"/api/v1/vehicles/{vid}/logs", json={"lines": lines}, headers={"Authorization": f"Bearer {token}"}).status_code
            == 200
        )
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM vehicle_logs WHERE addon_id = 'alpha-plug'").fetchone()[0] == 30
        connectors.set_log_keep(conn, 200)
    with db.tx() as conn:
        connectors.set_log_keep(conn, 7)  # not an offered value: ignored
        assert connectors.log_keep(conn) == 200
    page = client.get(f"/v/{vid}/debug?plugin=alpha-plug", follow_redirects=True).text  # leads to the log page of that plugin
    assert "alpha 29" in page and "beta 29" not in page
    assert "Alpha" in client.get(f"/v/{vid}/debug").text  # the filter lists the plugin by its name
    client.post(f"/v/{vid}/debug/clear", data={"plugin": "beta-plug"})
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM vehicle_logs WHERE addon_id = 'beta-plug'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM vehicle_logs WHERE addon_id = 'alpha-plug'").fetchone()[0] == 30
        addon = next(a for a in addons.list_for(conn, vid) if a["addon_id"] == "alpha-plug")
    client.post(f"/v/{vid}/integrations/{addon['id']}/delete")  # removing the plugin removes its lines
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM vehicle_logs WHERE vehicle_id = ?", (vid,)).fetchone()[0] == 0


def test_every_plugin_keeps_its_own_number_of_lines(client):
    from carassistant import connectors, db

    client.post("/vehicles", data={"name": "Cap Car", "fuel_type": "petrol"})
    with db.tx() as conn:
        vid = conn.execute("SELECT id FROM vehicles ORDER BY id DESC LIMIT 1").fetchone()["id"]
        db.set_setting(conn, "logs.max_lines", "200")
        for who in ("one", "two"):
            connectors.write_logs(conn, vid, who, [("2026-11-15T08:00:00", "info", who, f"line {i}") for i in range(250)])
        assert conn.execute("SELECT COUNT(*) FROM vehicle_logs WHERE addon_id = 'one'").fetchone()[0] == 200
        assert (
            conn.execute("SELECT COUNT(*) FROM vehicle_logs WHERE addon_id = 'two'").fetchone()[0] == 200
        )  # one noisy plugin does not push out another
        assert (
            conn.execute("SELECT MIN(message) FROM vehicle_logs WHERE addon_id = 'one'").fetchone()[0] == "line 100"
        )  # the oldest went first
    with db.tx() as conn:
        connectors.set_log_keep(conn, 500)  # offered value: more room
        assert connectors.log_keep(conn) == 500
    assert (
        client.get("/settings/system").status_code == 200 and 'id="logs"' not in client.get("/settings/system").text
    )  # no plugin logs under System any more
    assert client.post("/settings/logs", data={"days": "1"}).status_code in (404, 405)


def test_debug_button_of_one_plugin_and_retention_by_days(client):
    import json as _json
    from datetime import UTC, datetime, timedelta

    from carassistant import addons, connectors, db

    client.post("/vehicles", data={"name": "Dbg Car", "fuel_type": "petrol"})
    with db.tx() as conn:
        vid = conn.execute("SELECT id FROM vehicles ORDER BY id DESC LIMIT 1").fetchone()["id"]
    tokens, pks = {}, {}
    for name in ("alpha", "beta"):
        manifest = addons.parse_package(_json.dumps({"id": f"{name}-plug", "kind": "plugin", "name": name.title()}).encode())
        with db.tx() as conn:
            pks[name] = addons.add(conn, vid, manifest)
            tokens[name] = addons.set_up(conn, vid, addons.get(conn, vid, pks[name]), {})
    head = {n: {"Authorization": f"Bearer {t}"} for n, t in tokens.items()}
    line = {"lines": [{"message": "hello"}]}
    assert client.post(f"/api/v1/vehicles/{vid}/logs", json=line, headers=head["alpha"]).status_code == 409  # debug is off everywhere
    client.post(f"/v/{vid}/integrations/{pks['alpha']}/debug", data={"on": "1"})  # the button of alpha only
    assert client.get(f"/api/v1/vehicles/{vid}/control", headers=head["alpha"]).json()["control"]["debug"] is True
    assert client.get(f"/api/v1/vehicles/{vid}/control", headers=head["beta"]).json()["control"]["debug"] is False
    assert client.post(f"/api/v1/vehicles/{vid}/logs", json=line, headers=head["alpha"]).status_code == 200
    assert client.post(f"/api/v1/vehicles/{vid}/logs", json=line, headers=head["beta"]).status_code == 409
    client.post(f"/api/v1/vehicles/{vid}/data", json={"odometer_km": 5}, headers=head["alpha"])
    client.post(f"/api/v1/vehicles/{vid}/data", json={"odometer_km": 6}, headers=head["beta"])
    with db.tx() as conn:
        seen = {r["addon_id"] for r in conn.execute("SELECT addon_id FROM vehicle_traffic")}
    assert seen == {"alpha-plug"}  # only the plugin with its button on is watched
    info = client.get(f"/v/{vid}/integrations/{pks['alpha']}/info?tab=logs").text  # the log page says so and points to the settings
    assert "Debug is on" in info and f"/integrations/{pks['alpha']}/settings" in info
    page = client.get(
        f"/v/{vid}/integrations/{pks['alpha']}/settings"
    ).text  # the switch sits in the settings of every plugin, with its time
    assert 'name="on"' in page and "Switches off by itself on" in page and '<option value="1" selected>' in page
    assert f"/integrations/{pks['alpha']}/info" in client.get(f"/v/{vid}/plugins").text  # the tile points to it under More
    assert client.get(f"/v/{vid}/addons/{pks['alpha']}/log").status_code == 303  # the old address leads there
    client.post(f"/v/{vid}/integrations/{pks['alpha']}/debug", data={"on": "0"})
    assert client.get(f"/api/v1/vehicles/{vid}/control", headers=head["alpha"]).json()["control"]["debug"] is False
    # retention: lines older than the chosen days go, newer stay
    old = (datetime.now(UTC) - timedelta(days=3)).isoformat(timespec="seconds")
    with db.tx() as conn:
        conn.execute("UPDATE vehicle_logs SET added = ? WHERE addon_id = 'alpha-plug'", (old,))
        assert connectors.log_days(conn) == 7
    with db.tx() as conn:
        connectors.set_log_days(conn, 1)
        assert connectors.log_days(conn) == 1
        assert (
            conn.execute("SELECT COUNT(*) FROM vehicle_logs WHERE addon_id = 'alpha-plug'").fetchone()[0] == 0
        )  # three days old, kept for one
    with db.tx() as conn:
        connectors.set_log_days(conn, 9)  # not offered: unchanged
        assert connectors.log_days(conn) == 1
