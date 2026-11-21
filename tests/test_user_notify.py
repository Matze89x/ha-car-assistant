from datetime import UTC, datetime

from tests.test_web import create_vehicle

from carassistant import accounts, db, ha, notify


def _admin(client):
    with db.tx() as conn:
        return accounts.create_user(conn, "owner", "correct horse battery staple", admin=True)


def test_a_user_saves_their_own_service_and_events(client):
    uid = _admin(client)
    vid = create_vehicle(client, "Phone Car")
    r = client.post("/settings/notifications", data={"service": "notify.mobile_app_my_phone"})  # Settings > User: only the way to be told
    assert r.status_code == 303
    with db.tx() as conn:
        assert notify.prefs(conn, uid) == {"service": "mobile_app_my_phone", "events": [], "enabled": True}  # prefix dropped
    r = client.post(
        "/settings/notifications",
        data={"service": "notify.mobile_app_my_phone", "vehicle": str(vid), "ev": ["maint_due", "bogus", "reminder"]},  # Settings > Car
    )
    assert r.status_code == 303
    with db.tx() as conn:
        assert notify.prefs(conn, uid, vid)["events"] == ["maint_due", "reminder"]  # unknown event dropped
    assert 'value="mobile_app_my_phone"' in client.get("/settings/user").text
    assert 'value="maint_due" checked' in client.get("/settings/car").text.replace("\n", " ")  # the events are on the Car tab
    client.post("/settings/notifications", data={"service": "bad service!"})
    with db.tx() as conn:
        assert notify.prefs(conn, uid)["service"] == ""  # not a service name: nothing is stored


def test_a_car_can_be_switched_off_for_a_person_without_losing_its_events(client, monkeypatch):
    uid = _admin(client)
    vid = create_vehicle(client, "Quiet Car")
    client.post("/settings/notifications", data={"service": "mobile_app_phone", "vehicle": str(vid), "ev": ["maint_due"]})
    client.post("/settings/notifications/cars", data={})  # no car ticked: all off
    with db.tx() as conn:
        assert notify.prefs(conn, uid, vid) == {"service": "mobile_app_phone", "events": [], "enabled": False}
    assert "switched off" in client.get("/settings/car").text
    client.post("/settings/notifications/cars", data={"car": [str(vid)]})
    with db.tx() as conn:
        assert notify.prefs(conn, uid, vid)["events"] == ["maint_due"]  # the choice was kept
    user = client.get("/settings/user").text
    assert (f'name="car" value="{vid}" checked' in user.replace("\n", " ") and "Settings &gt; Car" in user) or "Settings > Car" in user


def test_only_chosen_events_go_to_the_users_service_and_only_once(client, monkeypatch):
    uid = _admin(client)
    vid = create_vehicle(client, "Notify Car")
    sent = []
    monkeypatch.setattr(ha, "call_service", lambda domain, service, payload: (sent.append((service, payload["message"])) or True, ""))
    with db.tx() as conn:
        conn.execute("DELETE FROM tasks WHERE vehicle_id = ?", (vid,))
        conn.execute("INSERT INTO tasks(vehicle_id, title, interval_months, last_date) VALUES(?, 'Oil', 12, '2020-01-01')", (vid,))
        notify.save_prefs(conn, uid, "mobile_app_phone", ["appointment"])
        assert notify.check_users(conn, datetime.now(UTC)) == 0 and sent == []  # maintenance was not asked for
        notify.save_prefs(conn, uid, "mobile_app_phone", ["maint_due"])
        assert notify.check_users(conn, datetime.now(UTC)) == 1
        assert sent[0][0] == "mobile_app_phone" and "Oil" in sent[0][1]
        assert notify.check_users(conn, datetime.now(UTC)) == 0  # told already: not again at once


def test_the_test_button_uses_the_users_service(client, monkeypatch):
    uid = _admin(client)
    sent = []
    monkeypatch.setattr(ha, "call_service", lambda domain, service, payload: (sent.append(service) or True, ""))
    with db.tx() as conn:
        notify.save_prefs(conn, uid, "mobile_app_phone", ["maint_due"])
    r = client.post("/settings/notifications/test", follow_redirects=False)
    assert r.status_code == 303 and sent == ["mobile_app_phone"]


def test_start_car_and_haptics_are_per_user(client, monkeypatch):
    from tests.test_web import create_vehicle

    from carassistant import accounts, db, userprefs

    first, second = create_vehicle(client, "First"), create_vehicle(client, "Second")
    with db.tx() as conn:
        uid = accounts.admin_id(conn) or accounts.create_user(conn, "owner", "a-long-pass-123", "Owner", True)
    assert client.get("/", follow_redirects=False).status_code == 200  # two cars: the choice
    client.post("/settings/prefs", data={"start_car": str(second)})
    with db.tx() as conn:
        assert userprefs.get(conn, uid, "start_car") == str(second)
    r = client.get("/", follow_redirects=False)
    assert (r.status_code == 303 and str(second) in r.headers["location"]) or "second" in r.headers["location"]
    client.post("/settings/prefs", data={"start_car": "999"})  # not a car: back to asking
    assert client.get("/", follow_redirects=False).status_code == 200
    from carassistant import ha

    monkeypatch.setattr(ha, "network_port", lambda: (True, 9000))  # a port is set: touch feedback is the person's own
    client.post("/settings/haptics", data={})
    with db.tx() as conn:
        assert userprefs.get(conn, uid, "haptics") == "0" and db.get_setting(conn, "ui.haptics", "1") == "1"
    assert first


def test_events_are_chosen_per_car(client, monkeypatch):
    uid = _admin(client)
    first, second = create_vehicle(client, "First"), create_vehicle(client, "Second")
    sent = []
    monkeypatch.setattr(ha, "call_service", lambda domain, service, payload: (sent.append(payload["message"]) or True, ""))
    r = client.post("/settings/notifications", data={"service": "mobile_app_phone", "vehicle": str(second), "ev": ["maint_due"]})
    assert r.status_code == 303
    with db.tx() as conn:
        assert notify.prefs(conn, uid, second)["events"] == ["maint_due"]
        assert notify.prefs(conn, uid, first)["events"] == []  # the other car keeps its own choice
        for vid in (first, second):
            conn.execute("DELETE FROM tasks WHERE vehicle_id = ?", (vid,))
            conn.execute("INSERT INTO tasks(vehicle_id, title, interval_months, last_date) VALUES(?, 'Oil', 12, '2020-01-01')", (vid,))
        assert notify.check_users(conn, datetime.now(UTC)) == 1  # only the second car was asked for
    page = client.get(f"/settings/car?car={second}").text  # the Car tab of the second car carries its own events
    assert f'name="vehicle" value="{second}"' in page and "Second" in page


def test_a_finished_trip_is_announced_at_once(client, monkeypatch):
    from carassistant import trips, worker

    uid = _admin(client)
    vid = create_vehicle(client, "Trip Car")
    sent = []
    monkeypatch.setattr(ha, "call_service", lambda domain, service, payload: (sent.append(payload["message"]) or True, ""))
    with db.tx() as conn:
        notify.save_prefs(conn, uid, "mobile_app_phone", ["trip_end"], vid)
        for i in range(8):  # a drive of a few kilometres, long ago enough to count as finished
            conn.execute(
                "INSERT INTO vehicle_track(vehicle_id, ts, lat, lon) VALUES(?, ?, ?, 8.0)",
                (vid, f"2026-11-20T10:{i:02d}:00+00:00", 50.0 + i * 0.01),
            )
        assert trips.from_track(conn, vid, datetime(2026, 11, 20, 12, 0, tzinfo=UTC)) == 1
    # the finished drive wakes the worker, which tells the user without waiting for the 6-hourly check
    worker.run_once({"poll": 1e12, "publish": 1e12, "notify": 1e12, "maintain": 1e12, "srcauto": 1e12}, 1.0)
    assert len(sent) == 1
    assert notify.take_trip_flag() is False
