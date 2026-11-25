import json
import re
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


def test_only_what_a_car_really_delivers_is_offered_for_notifications(client):
    from carassistant import connectors, notify

    uid = _admin(client)
    vid = create_vehicle(client, "Plain Car")
    client.post("/settings/notifications", data={"service": "mobile_app_x"})
    with db.tx() as conn:
        car = conn.execute("SELECT * FROM vehicles WHERE id = ?", (vid,)).fetchone()
        assert notify.offered_events(conn, car) == {
            "maint_due",
            "appointment",
        }  # the person's own entries only: no plugin reported anything
    page = client.get("/settings/user").text
    assert f'name="ev_{vid}" value="maint_due"' in page and f'name="ev_{vid}" value="appointment"' in page
    assert (
        f'name="ev_{vid}" value="tyre_pressure"' not in page and f'name="ev_{vid}" value="open_closure"' not in page
    )  # no tyre system, no door data
    assert "Only what this car delivers is offered" in page
    assert 'name="ev_new" value="tyre_pressure"' in page  # the choice for new cars offers everything
    with db.tx() as conn:  # a plugin reports tyre pressures and the doors
        connectors._store(conn, vid, "tyre_pressure_bar", '{"fl": 2.4, "fr": 2.4, "rl": 2.4, "rr": 2.4}')
        connectors._store(conn, vid, "doors", '{"driver": false}')
        car = conn.execute("SELECT * FROM vehicles WHERE id = ?", (vid,)).fetchone()
        assert {"tyre_pressure", "open_closure"} <= notify.offered_events(conn, car)
        assert not {"low_energy", "car_message", "refuel", "trip_end"} & notify.offered_events(conn, car)
    page = client.get("/settings/user").text
    assert f'name="ev_{vid}" value="tyre_pressure"' in page and f'name="ev_{vid}" value="open_closure"' in page
    assert f'name="ev_{vid}" value="low_energy"' not in page  # still no level reported
    # a message that is switched on for a car that never delivers it (the start value of a new car) is NOT shown: it never fires; it appears as soon as
    # a plugin or an entity delivers the value
    client.post("/settings/notifications/matrix", data={f"ev_{vid}": ["low_energy"]})
    assert f'name="ev_{vid}" value="low_energy"' not in client.get("/settings/user").text
    with db.tx() as conn:
        connectors._store(conn, vid, "fuel_level", "40")
    assert f'name="ev_{vid}" value="low_energy" checked' in client.get("/settings/user").text.replace("\n", " ").replace("  ", " ") or (
        f'name="ev_{vid}" value="low_energy"' in client.get("/settings/user").text
    )
    assert uid


def test_the_messages_have_a_tab_per_car_and_the_general_ones_a_window_of_their_own(client):
    """One tab per car (the car you work with is open first) and a last tab for the cars added later; under the open tab only that car's messages.
    The messages that belong to no car sit in a window of their own, still in the one form."""
    _admin(client)
    page = client.get("/settings/user").text
    assert (
        "nm-tabs" not in page and 'id="nm-select"' not in page
    )  # no car yet: no tab bar, the one panel for the cars to come is just shown
    assert 'data-panel="pnew"' in page and not re.search(r'data-panel="pnew"[^>]*hidden', page)

    first = create_vehicle(client, "Alpha Car")
    second = create_vehicle(client, "Beta Car")
    ids = {first: "Alpha Car", second: "Beta Car"}
    page = client.get(f"/settings/user?car={second}").text
    bar = page[page.index('class="seg-tabs nm-tabs"') : page.index("</nav>", page.index('class="seg-tabs nm-tabs"'))]
    for vid, name in ids.items():
        assert f'data-nm-tab="p{vid}"' in bar and f"<span>{name}</span>" in bar  # a tab per car, named like the car
    assert 'data-nm-tab="pnew"' in bar and "<span>More cars</span>" in bar  # and one for the cars added later
    assert bar.count('class="on"') == 1 and re.search(rf'<a [^>]*data-nm-tab="p{second}"[^>]*class="on"', bar)  # the car in use is open
    assert re.search(rf'data-panel="p{first}"[^>]*hidden', page) and not re.search(rf'data-panel="p{second}"[^>]*hidden', page)

    # the general messages: a window of their own, after the cars, in the same form (so one save covers both)
    cars_part, general_part = page.split('id="notify-general"')
    assert 'name="gen"' in general_part and 'name="gen"' not in cars_part
    assert 'name="ev_' not in general_part and f'name="ev_{second}"' in cars_part
    form = page[page.index('id="nm-form"') : page.index("</form>", page.index('id="nm-form"'))]
    assert 'id="notify-general"' in form and 'id="nm-panels"' in form


def test_two_cars_with_different_plugins_each_get_their_own_odometer_rule_and_their_own_messages(client):
    """Everything about a car is per car: a plugin on the first car (odometer, fuel level, doors) and a different one on the second (battery, tyre pressures)
    must not leak into each other - not the 'the odometer is shown, not typed' rule, not the messages a person can switch on."""
    from carassistant import connectors, summary

    _admin(client)
    old = create_vehicle(client, "Old Van")
    electric = create_vehicle(client, "Electric Compact")
    with db.tx() as conn:
        connectors.create_token(conn, "van-plugin", old)
        summary.record_odometer(conn, old, 120_500, "api:van-plugin")  # the van's plugin reports the odometer
        connectors._store(conn, old, "fuel_level", "55")
        connectors._store(conn, old, "doors", '{"driver": false}')
        connectors._store(conn, electric, "battery_pct", "80")  # the electric car's plugin: battery and tyres, no odometer
        connectors._store(conn, electric, "tyre_pressure_bar", '{"fl": 2.5, "fr": 2.5, "rl": 2.5, "rr": 2.5}')
        summary.add_odometer(conn, electric, 8_000)  # typed by a person
        assert summary.odometer_from_car(conn, old) is True and summary.odometer_from_car(conn, electric) is False
        van, ev = (conn.execute("SELECT * FROM vehicles WHERE id = ?", (v,)).fetchone() for v in (old, electric))
        van_offer, ev_offer = notify.offered_events(conn, van), notify.offered_events(conn, ev)
    assert {"low_energy", "open_closure", "refuel"} <= van_offer and "tyre_pressure" not in van_offer
    assert {"low_energy", "tyre_pressure", "refuel"} <= ev_offer and "open_closure" not in ev_offer
    # the settings page: one tab and one panel per car, each with its own switches
    page = client.get(f"/settings/user?car={electric}").text
    assert f'name="ev_{old}" value="open_closure"' in page and f'name="ev_{electric}" value="open_closure"' not in page
    assert f'name="ev_{electric}" value="tyre_pressure"' in page and f'name="ev_{old}" value="tyre_pressure"' not in page
    assert page.count('data-nm-tab="p') >= 3 and f'data-nm-tab="p{old}"' in page and f'data-nm-tab="p{electric}"' in page
    # the odometer: the van's page has nothing to type, the electric car's page has the box
    van_page = client.get(f"/v/{old}/edit").text
    ev_page = client.get(f"/v/{electric}/edit").text
    assert 'class="odo-entry"' not in van_page and 'class="odo-entry"' in ev_page
