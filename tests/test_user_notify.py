import json
from datetime import UTC, datetime, timedelta

from tests.test_web import create_vehicle

from carassistant import accounts, db, ha, notify


class Form:
    """What the settings form sends: named lists."""

    def __init__(self, **lists):
        self.lists = lists

    def getlist(self, key):
        return self.lists.get(key, [])


def _admin(client):
    with db.tx() as conn:
        return accounts.create_user(conn, "owner", "correct horse battery staple", admin=True)


def _set(conn, uid, service, events, vid=None):
    """Service and events like the settings page stores them (events for one car, or the choice for new cars)."""
    notify.save_service(conn, uid, service)
    if vid is None:
        conn.execute("UPDATE user_notify SET events = ? WHERE user_id = ?", (json.dumps(events), uid))
    else:
        conn.execute(
            "INSERT INTO user_notify_vehicle(user_id, vehicle_id, events) VALUES(?,?,?) ON CONFLICT(user_id, vehicle_id) DO UPDATE SET events = excluded.events",
            (uid, vid, json.dumps(events)),
        )


def test_notifications_are_one_matrix_under_user_and_nothing_under_car(client):
    uid = _admin(client)
    vid = create_vehicle(client, "Phone Car")
    r = client.post("/settings/notifications", data={"service": "notify.mobile_app_my_phone"})  # only the way to be told
    assert r.status_code == 303
    with db.tx() as conn:
        assert notify.prefs(conn, uid) == {"service": "mobile_app_my_phone", "events": [], "enabled": True}  # prefix dropped
    r = client.post(
        "/settings/notifications/matrix",
        data={f"ev_{vid}": ["maint_due", "bogus", "reminder"], "ev_new": ["trip_end"], "gen": ["addon_update", "x"]},
    )
    assert r.status_code == 303
    with db.tx() as conn:
        assert notify.prefs(conn, uid, vid)["events"] == ["maint_due", "reminder"]  # unknown event dropped
        m = notify.matrix(conn, uid)
        assert m["default"] == {"trip_end"} and m["general"] == {"addon_update"} and m["cars"][0]["events"] == {"maint_due", "reminder"}
    user = client.get("/settings/user").text.replace("\n", " ")
    assert 'value="mobile_app_my_phone"' in user and f'name="ev_{vid}" value="maint_due"' in user and 'name="ev_new"' in user
    car = client.get("/settings/car").text
    assert 'id="notifications"' not in car and "ev_new" not in car and "push-on" not in car  # nothing about notifications under Car
    assert 'id="notifications"' not in client.get("/settings/system").text
    client.post("/settings/notifications", data={"service": "bad service!"})
    with db.tx() as conn:
        assert notify.prefs(conn, uid)["service"] == ""  # not a service name: nothing is stored


def test_cars_come_and_go_in_the_matrix_by_themselves(client):
    uid = _admin(client)
    first = create_vehicle(client, "First")
    client.post("/settings/notifications/matrix", data={"ev_new": ["maint_due"], f"ev_{first}": ["reminder"]})
    second = create_vehicle(client, "Second")  # added later: starts with the choice for new cars
    with db.tx() as conn:
        m = {c["id"]: c["events"] for c in notify.matrix(conn, uid)["cars"]}
        assert m[first] == {"reminder"} and m[second] == {"maint_due"}
    client.post(f"/v/{second}/delete")
    with db.tx() as conn:
        assert [c["id"] for c in notify.matrix(conn, uid)["cars"]] == [first]  # a removed car disappears
        assert conn.execute("SELECT COUNT(*) FROM user_notify_vehicle WHERE vehicle_id = ?", (second,)).fetchone()[0] == 0


def test_only_chosen_events_go_to_the_users_service_and_only_once(client, monkeypatch):
    uid = _admin(client)
    vid = create_vehicle(client, "Notify Car")
    sent = []
    monkeypatch.setattr(ha, "call_service", lambda domain, service, payload: (sent.append((service, payload["message"])) or True, ""))
    with db.tx() as conn:
        conn.execute("DELETE FROM tasks WHERE vehicle_id = ?", (vid,))
        conn.execute("INSERT INTO tasks(vehicle_id, title, interval_months, last_date) VALUES(?, 'Oil', 12, '2020-01-01')", (vid,))
        _set(conn, uid, "mobile_app_phone", ["appointment"], vid)
        assert notify.check_users(conn, datetime.now(UTC)) == 0 and sent == []  # maintenance was not asked for
        _set(conn, uid, "mobile_app_phone", ["maint_due"], vid)
        assert notify.check_users(conn, datetime.now(UTC)) == 1
        assert sent[0][0] == "mobile_app_phone" and "Oil" in sent[0][1]
        assert notify.check_users(conn, datetime.now(UTC)) == 0  # told already: not again at once


def test_the_same_words_to_the_same_person_go_out_once(client, monkeypatch):
    uid = _admin(client)
    sent = []
    monkeypatch.setattr(ha, "call_service", lambda domain, service, payload: (sent.append(payload["message"]) or True, ""))
    with db.tx() as conn:
        notify.save_service(conn, uid, "mobile_app_phone")
        notify._recent.clear()
        assert notify._deliver(conn, uid, "mobile_app_phone", "Car", "Trip finished")[0]
        assert notify._deliver(conn, uid, "mobile_app_phone", "Car", "Trip finished")[
            0
        ]  # a second identical call (two workers, two triggers)
    assert sent == ["Trip finished"]


def test_the_test_button_uses_the_users_service(client, monkeypatch):
    uid = _admin(client)
    sent = []
    monkeypatch.setattr(ha, "call_service", lambda domain, service, payload: (sent.append(service) or True, ""))
    with db.tx() as conn:
        _set(conn, uid, "mobile_app_phone", ["maint_due"])
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
    client.post("/settings/notifications", data={"service": "mobile_app_phone"})
    r = client.post("/settings/notifications/matrix", data={f"ev_{second}": ["maint_due"]})
    assert r.status_code == 303
    with db.tx() as conn:
        assert notify.prefs(conn, uid, second)["events"] == ["maint_due"]
        assert notify.prefs(conn, uid, first)["events"] == []  # the other car keeps its own choice
        for vid in (first, second):
            conn.execute("DELETE FROM tasks WHERE vehicle_id = ?", (vid,))
            conn.execute("INSERT INTO tasks(vehicle_id, title, interval_months, last_date) VALUES(?, 'Oil', 12, '2020-01-01')", (vid,))
        assert notify.check_users(conn, datetime.now(UTC)) == 1  # only the second car was asked for
    page = client.get("/settings/user").text
    assert f'name="ev_{second}"' in page and "Second" in page and "First" in page  # every car in the one matrix


def test_a_finished_trip_is_announced_at_once(client, monkeypatch):
    from carassistant import trips, worker

    DAY = (datetime.now(UTC) - timedelta(hours=20)).date().isoformat()  # a drive from yesterday evening or earlier today: always "recent"

    uid = _admin(client)
    vid = create_vehicle(client, "Trip Car")
    sent = []
    monkeypatch.setattr(ha, "call_service", lambda domain, service, payload: (sent.append(payload["message"]) or True, ""))
    with db.tx() as conn:
        _set(conn, uid, "mobile_app_phone", ["trip_end"], vid)
        for i in range(8):  # a drive of a few kilometres, long ago enough to count as finished
            conn.execute(
                "INSERT INTO vehicle_track(vehicle_id, ts, lat, lon) VALUES(?, ?, ?, 8.0)",
                (vid, f"{DAY}T10:{i:02d}:00+00:00", 50.0 + i * 0.01),
            )
        assert trips.from_track(conn, vid, datetime.fromisoformat(f"{DAY}T12:00:00+00:00")) == 1
    # the finished drive wakes the worker, which tells the user without waiting for the 6-hourly check
    worker.run_once({"poll": 1e12, "publish": 1e12, "notify": 1e12, "maintain": 1e12, "srcauto": 1e12}, 1.0)
    assert len(sent) == 1
    assert notify.take_trip_flag() is False


def test_a_message_never_shows_raw_coordinates_as_a_place():
    from carassistant import notify

    assert notify._readable_place("49.33276, 7.09618") == "" and notify._readable_place("-12.5,130.1") == ""
    assert notify._readable_place("Neunkirchen") == "Neunkirchen" and notify._readable_place(None) == ""
