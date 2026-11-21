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
        _level(conn, vid, 95)  # +70 points
        row = conn.execute("SELECT * FROM fuel WHERE vehicle_id = ?", (vid,)).fetchone()
        assert row["amount"] is None and row["price_total"] is None and row["full_tank"] == 1 and row["notes"].startswith("auto:tank:+70%")
        _level(conn, vid, 30)
        _level(conn, vid, 98)  # a second jump hours later would be a new refuel, but not within the guard time
        assert conn.execute("SELECT COUNT(*) FROM fuel WHERE vehicle_id = ?", (vid,)).fetchone()[0] == 1
        todo = refuel_detect.todo(conn, vid)
        assert todo[0]["rise"] == 70 and todo[0]["litres"] == 35  # a rough estimate from the tank size, never stored as the amount
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
