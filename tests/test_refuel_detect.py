from datetime import UTC, datetime

from tests.test_web import create_vehicle

from carassistant import connectors, db, notify, refuel_detect


def _level(conn, vid, value):
    connectors._store(conn, vid, "fuel_level", str(value))


def test_a_big_rise_of_the_tank_level_adds_an_unfinished_fuel_entry_once(client):
    vid = create_vehicle(client, "Pump Car")
    with db.tx() as conn:
        conn.execute("UPDATE vehicles SET tank_l = 50 WHERE id = ?", (vid,))
        _level(conn, vid, 20)
        _level(conn, vid, 25)  # a small change is no refuel
        assert conn.execute("SELECT COUNT(*) FROM fuel WHERE vehicle_id = ?", (vid,)).fetchone()[0] == 0
        _level(conn, vid, 95)  # +75 points from the lowest level of the rise (20)
        row = conn.execute("SELECT * FROM fuel WHERE vehicle_id = ?", (vid,)).fetchone()
        assert row["amount"] is None and row["price_total"] is None and row["full_tank"] == 1 and row["notes"].startswith("auto:tank:+75%")
        _level(conn, vid, 30)
        _level(conn, vid, 98)  # a second jump hours later would be a new refuel, but not within the guard time
        assert conn.execute("SELECT COUNT(*) FROM fuel WHERE vehicle_id = ?", (vid,)).fetchone()[0] == 1
        todo = refuel_detect.todo(conn, vid)
        assert todo[0]["rise"] == 75 and todo[0]["litres"] == 38  # a rough estimate from the tank size, never stored as the amount
    page = client.get(f"/v/{vid}/e/fuel").text
    assert "Refuel noticed" in page or "Tanken erkannt" in page


def test_electric_cars_and_logged_refuels_are_left_alone(client):
    ev = create_vehicle(client, "Volt")
    car = create_vehicle(client, "Own Entry Car")
    with db.tx() as conn:
        conn.execute("UPDATE vehicles SET fuel_type = 'electric' WHERE id = ?", (ev,))
        _level(conn, ev, 10)
        _level(conn, ev, 90)  # a battery filling up is charging, not a refuel
        assert conn.execute("SELECT COUNT(*) FROM fuel WHERE vehicle_id = ?", (ev,)).fetchone()[0] == 0
        _level(conn, car, 10)
        conn.execute("INSERT INTO fuel(vehicle_id, date, amount) VALUES(?,?,40)", (car, datetime.now(UTC).astimezone().date().isoformat()))
        _level(conn, car, 90)  # the person already logged today's refuel
        assert conn.execute("SELECT COUNT(*) FROM fuel WHERE vehicle_id = ?", (car,)).fetchone()[0] == 1


def test_the_refuel_is_announced_to_those_who_asked(client, monkeypatch):
    from carassistant import accounts, ha

    vid = create_vehicle(client, "Tell Car")
    sent = []
    monkeypatch.setattr(ha, "call_service", lambda d, s, p: (sent.append(p["message"]) or True, ""))
    with db.tx() as conn:
        uid = accounts.create_user(conn, "owner", "correct horse battery staple", admin=True)
        notify.save_service(conn, uid, "mobile_app_phone")
        conn.execute("INSERT INTO user_notify_vehicle(user_id, vehicle_id, events, enabled) VALUES(?,?,?,1)", (uid, vid, '["refuel"]'))
        _level(conn, vid, 15)
        _level(conn, vid, 90)
        assert notify.check_users(conn, only={"refuel"}) == 1
        assert "75" in sent[0] and notify.check_users(conn, only={"refuel"}) == 0  # once


def test_a_charging_session_is_noticed_and_leaves_an_unfinished_entry(client):
    from carassistant import charge_detect

    vid = create_vehicle(client, "Volt")
    with db.tx() as conn:
        conn.execute("UPDATE vehicles SET fuel_type = 'electric', battery_kwh = 60 WHERE id = ?", (vid,))
        connectors._store(conn, vid, "battery_pct", "30")
        connectors._store(conn, vid, "charging", "yes")  # plugged in and charging
        connectors._store(conn, vid, "charge_power_kw", "11")
        connectors._store(conn, vid, "battery_pct", "80")
        from datetime import timedelta

        started = (datetime.now(UTC) - timedelta(minutes=50)).isoformat(timespec="seconds")
        conn.execute("UPDATE charge_sessions SET started = ? WHERE vehicle_id = ?", (started, vid))
        connectors._store(conn, vid, "charging", "no")
        row = conn.execute("SELECT * FROM fuel WHERE vehicle_id = ?", (vid,)).fetchone()
        assert row["amount"] is None and row["notes"].startswith("auto:charge:+50%")
        done = charge_detect.sessions(conn, vid)[0]
        assert done["start_pct"] == 30 and done["end_pct"] == 80 and done["max_kw"] == 11 and done["kwh"] == 30.0 and done["minutes"] >= 49
        todo = refuel_detect.todo(conn, vid)[0]
        assert todo["charge"] and todo["unit"] == "kWh" and todo["litres"] == 30
    page = client.get(f"/v/{vid}/e/fuel").text
    assert "Charging noticed" in page or "Laden erkannt" in page


def test_a_plug_contact_is_not_a_session(client):
    vid = create_vehicle(client, "Brief")
    with db.tx() as conn:
        conn.execute("UPDATE vehicles SET fuel_type = 'electric' WHERE id = ?", (vid,))
        connectors._store(conn, vid, "battery_pct", "50")
        connectors._store(conn, vid, "charging", "yes")
        connectors._store(conn, vid, "charging", "no")  # a few seconds, no change
        assert conn.execute("SELECT COUNT(*) FROM charge_sessions WHERE vehicle_id = ?", (vid,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM fuel WHERE vehicle_id = ?", (vid,)).fetchone()[0] == 0


def test_completed_sessions_give_cost_price_loss_and_a_summary(client):
    from datetime import timedelta

    from carassistant import charge_detect

    vid = create_vehicle(client, "Stats Car")
    with db.tx() as conn:
        conn.execute("UPDATE vehicles SET fuel_type = 'electric', battery_kwh = 60 WHERE id = ?", (vid,))
        for start, end, kw in ((20, 80, 11), (40, 90, 120)):
            connectors._store(conn, vid, "battery_pct", str(start))
            connectors._store(conn, vid, "charging", "yes")
            connectors._store(conn, vid, "charge_power_kw", str(kw))
            connectors._store(conn, vid, "battery_pct", str(end))
            conn.execute(
                "UPDATE charge_sessions SET started = ? WHERE ended IS NULL",
                ((datetime.now(UTC) - timedelta(minutes=40)).isoformat(timespec="seconds"),),
            )
            connectors._store(conn, vid, "charging", "no")
            conn.execute("UPDATE fuel SET date = date WHERE 0")
        assert charge_detect.stats(conn, vid)["kwh_estimated"] is True  # nothing billed yet: estimates only
        first = conn.execute("SELECT id FROM fuel WHERE vehicle_id = ? ORDER BY id LIMIT 1", (vid,)).fetchone()["id"]
        conn.execute(
            "UPDATE fuel SET amount = 40, price_total = 12 WHERE id = ?", (first,)
        )  # the person completed the first one from the bill
        s = charge_detect.sessions(conn, vid)[-1]
        assert s["kwh_billed"] and s["kwh"] == 40 and s["cost"] == 12 and round(s["per_kwh"], 2) == 0.3
        assert s["gained_kwh"] == 36 and round(s["loss_pct"]) == 10  # 60 kWh x 60 % reached the battery, 40 kWh were billed
        total = charge_detect.stats(conn, vid)
        assert total["n"] == 2 and total["fast"] == 1 and total["slow"] == 1 and total["cost"] == 12 and total["avg_kw"] == 65.5
    page = client.get(f"/v/{vid}/e/fuel").text
    assert "Charging loss" in page or "Ladeverlust" in page


def test_the_length_of_a_charging_session_is_written_in_the_language_of_the_page(client):
    """The sessions list had a German "Min." built into the template: an English page said "40 Min."."""
    from datetime import timedelta

    vid = create_vehicle(client, "Words")
    with db.tx() as conn:
        conn.execute("UPDATE vehicles SET fuel_type = 'electric', battery_kwh = 60 WHERE id = ?", (vid,))
        connectors._store(conn, vid, "battery_pct", "30")
        connectors._store(conn, vid, "charging", "yes")
        connectors._store(conn, vid, "battery_pct", "80")
        conn.execute(
            "UPDATE charge_sessions SET started = ? WHERE ended IS NULL",
            ((datetime.now(UTC) - timedelta(minutes=40)).isoformat(timespec="seconds"),),
        )
        connectors._store(conn, vid, "charging", "no")
    client.post("/settings/language", data={"language": "en"})
    page = client.get(f"/v/{vid}/e/fuel").text
    assert " minutes)" in page and "Min.)" not in page
    client.post("/settings/language", data={"language": "de"})
    assert " Min.)" in client.get(f"/v/{vid}/e/fuel").text
