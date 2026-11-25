"""The low tank / battery message: told ONCE when the level falls to the person's threshold - right when the reading arrives - and told again only after the
level was back above it by a margin (no hopping up and down); thresholds of one's own per person and car."""

from datetime import UTC, datetime, timedelta

from tests.test_user_notify import _admin
from tests.test_web import create_vehicle

from carassistant import accounts, connectors, db, ha, notify

NOW = datetime(2026, 11, 24, 12, tzinfo=UTC)


class _Post(dict):
    """A form as the settings page posts it: single values and lists."""

    def getlist(self, key):
        value = self.get(key, [])
        return value if isinstance(value, list) else ([value] if value else [])


def test_the_rules_in_a_table():
    d = notify.energy_decision
    assert d(30, None, 25, None, False) == "" and d(25, None, 25, None, False) == "fire"  # at the threshold and below
    assert d(24, None, 25, None, True) == ""  # told already: no repeat, however long it stays low
    assert (
        d(27, None, 25, None, True) == "" and d(29, None, 25, None, True) == ""
    )  # between the threshold and the margin: nothing, nothing forgotten
    assert d(30, None, 25, None, True) == "rearm"  # back above it by the margin (5 points): the next fall is told again
    assert d(24, None, 25, None, False) == "fire"  # ... and told again
    # a range as threshold (a fifth, at least 10 km, as margin)
    assert d(None, 90, None, 100, False) == "fire" and d(None, 110, None, 100, True) == "" and d(None, 120, None, 100, True) == "rearm"
    assert (
        d(None, 140, None, 40, True) == "rearm" and d(None, 45, None, 40, True) == "" and d(None, 50, None, 40, True) == "rearm"
    )  # at least 10 km
    # both: either one tells, both have to be back up
    assert d(60, 90, 25, 100, False) == "fire" and d(60, 90, 25, 100, True) == "" and d(60, 130, 25, 100, True) == "rearm"
    # what is not known is not judged; nothing used = nothing happens
    assert d(None, None, 25, 100, False) == "" and d(None, None, 25, 100, True) == ""
    assert d(10, 10, None, None, False) == "" and d(10, 10, 0, 0, False) == ""
    assert d(None, 130, 25, 100, True) == "rearm"  # only the range is known and high: that is enough to rearm


def _arrange(client, monkeypatch, *, events=("low_energy",), name="Fuel Car"):
    """A signed-in person who wants the message for one car, told through a Home Assistant service; the messages sent are collected."""
    uid = _admin(client)
    vid = create_vehicle(client, name)
    sent = []
    monkeypatch.setattr(ha, "network_port", lambda: (True, None))
    monkeypatch.setattr(notify.ha, "call_service", lambda d, s, data: sent.append(data["message"]) or (True, ""))
    with db.tx() as conn:
        notify.save_service(conn, uid, "mobile_app_x")
        conn.execute("UPDATE vehicles SET fuel_type = 'petrol', tank_l = 50 WHERE id = ?", (vid,))
        notify.save_matrix(conn, uid, _Post({f"ev_{vid}": list(events)}))
    return uid, vid, sent


def _reading(vid, pct, km=None, at=None):
    with db.tx() as conn:
        connectors._store(conn, vid, "fuel_level", str(pct), at)
        if km is not None:
            connectors._store(conn, vid, "range_km", str(km), at)


def test_one_message_when_it_falls_and_the_next_only_after_it_was_back_above(client, monkeypatch):
    uid, vid, sent = _arrange(client, monkeypatch)
    notify.take_energy_vehicles()  # (earlier tests may have left cars waiting)
    _reading(vid, 40, 380)
    with db.tx() as conn:
        assert notify.check_energy(conn, {vid}, NOW) == 0  # well above the threshold (the car's yellow level, 25 %)
    _reading(vid, 25, 230)
    assert vid in notify.take_energy_vehicles()  # a reading about the tank: the worker is asked at once
    with db.tx() as conn:
        assert notify.check_energy(conn, {vid}, NOW) == 1
    assert sent == ["Tank is getting low: 25 % · 230 km"] and "Fuel Car" not in sent[0]
    for pct in (24, 20, 25, 18):  # it stays low, wobbles, falls further: never again
        _reading(vid, pct, pct * 9)
        with db.tx() as conn:
            assert notify.check_energy(conn, {vid}, NOW + timedelta(hours=20)) == 0
    for pct in (26, 28, 29, 27):  # hops up a little (a sloshing tank, a sensor): still the same fall
        _reading(vid, pct)
        with db.tx() as conn:
            assert notify.check_energy(conn, {vid}, NOW + timedelta(days=1)) == 0
        with db.tx() as conn:
            assert conn.execute("SELECT fired FROM notify_energy WHERE user_id = ?", (uid,)).fetchone()["fired"] == 1
    _reading(vid, 80)  # refuelled: above the threshold by the margin
    with db.tx() as conn:
        assert notify.check_energy(conn, {vid}, NOW + timedelta(days=2)) == 0  # silently armed again
        assert conn.execute("SELECT fired FROM notify_energy WHERE user_id = ?", (uid,)).fetchone()["fired"] == 0
    _reading(vid, 24, 220)  # and a new fall is told
    with db.tx() as conn:
        assert notify.check_energy(conn, {vid}, NOW + timedelta(days=5)) == 1
    assert len(sent) == 2


def test_the_regular_check_is_only_a_safety_net_and_repeats_nothing(client, monkeypatch):
    _uid, vid, sent = _arrange(client, monkeypatch)
    _reading(vid, 20, 200)
    with db.tx() as conn:
        assert notify.check_all(conn, NOW) == 1  # a reading that arrived while the app was off: told once
        for hours in (6, 12, 24 * 3, 24 * 4):  # the old way told it again every three days
            assert notify.check_all(conn, NOW + timedelta(hours=hours)) == 0
    assert len(sent) == 1


def test_a_person_without_the_event_or_a_reading_gets_nothing(client, monkeypatch):
    _uid, vid, _sent = _arrange(client, monkeypatch, events=("trip_end",))
    _reading(vid, 5, 50)
    with db.tx() as conn:
        assert notify.check_energy(conn, {vid}, NOW) == 0  # did not ask for it
    other = create_vehicle(client, "Other")
    with db.tx() as conn:
        notify.save_matrix(conn, _uid, _Post({f"ev_{other}": ["low_energy"]}))
        assert notify.check_energy(conn, {other}, NOW) == 0  # the car has not reported a level yet


def test_everybody_has_a_threshold_of_their_own_per_car(client, monkeypatch):
    uid, vid, sent = _arrange(client, monkeypatch)
    with db.tx() as conn:
        second = accounts.create_user(conn, "partner", "another long passphrase here", admin=False)
        notify.save_service(conn, second, "mobile_app_y")
        notify.save_matrix(conn, uid, _Post({f"ev_{vid}": ["low_energy"], f"ep_{vid}": "15"}))
        notify.save_matrix(conn, second, _Post({f"ev_{vid}": ["low_energy"], f"ep_{vid}": "35"}))
    _reading(vid, 30, 300)  # below the partner's 35 %, above the owner's 15 %
    with db.tx() as conn:
        assert notify.check_energy(conn, {vid}, NOW) == 1
    assert sent == ["Tank is getting low: 30 % · 300 km"]  # one message: for the partner
    _reading(vid, 14, 140)
    with db.tx() as conn:
        assert notify.check_energy(conn, {vid}, NOW) == 1  # now the owner, too (the partner was told already)
    assert len(sent) == 2


def test_without_a_choice_the_yellow_level_of_the_car_is_the_threshold(client, monkeypatch):
    uid, vid, _sent = _arrange(client, monkeypatch)
    with db.tx() as conn:
        conn.execute("UPDATE vehicles SET warn_pct = 40 WHERE id = ?", (vid,))
        assert notify.energy_thresholds(conn, uid, conn.execute("SELECT * FROM vehicles WHERE id = ?", (vid,)).fetchone()) == (40, None)
        conn.execute(
            "UPDATE user_notify_vehicle SET energy_pct = 0, energy_km = 80 WHERE user_id = ?", (uid,)
        )  # 0 = per cent not used, a range instead
        assert notify.energy_thresholds(conn, uid, conn.execute("SELECT * FROM vehicles WHERE id = ?", (vid,)).fetchone()) == (None, 80)


def test_a_message_of_the_old_kind_counts_as_told_so_an_update_does_not_say_it_again(client, monkeypatch):
    uid, vid, _sent = _arrange(client, monkeypatch)
    with db.tx() as conn:
        conn.execute("INSERT INTO notify_state(key, last_sent) VALUES(?, ?)", (f"u{uid}:energy:{vid}:soon", NOW.isoformat()))
    _reading(vid, 22, 200)
    with db.tx() as conn:
        assert notify.check_energy(conn, {vid}, NOW + timedelta(days=9)) == 0  # told in the old way: not again after the update
        _reading(vid, 70)
        notify.check_energy(conn, {vid}, NOW + timedelta(days=9))
    _reading(vid, 20)
    with db.tx() as conn:
        assert notify.check_energy(conn, {vid}, NOW + timedelta(days=10)) == 1  # a new fall after a refuel is told


def test_an_electric_car_is_told_about_its_battery(client, monkeypatch):
    _uid, vid, sent = _arrange(client, monkeypatch, name="Electric Car")
    with db.tx() as conn:
        conn.execute("UPDATE vehicles SET fuel_type = 'electric', battery_kwh = 60 WHERE id = ?", (vid,))
        connectors._store(conn, vid, "battery_pct", "18")
        assert notify.check_energy(conn, {vid}, NOW) == 1
    assert sent == ["Battery is getting low: 18 %"]


def test_the_settings_keep_one_way_to_be_told_and_show_it_under_the_switch(client):
    uid = _admin(client)
    vid = create_vehicle(client, "Phone Car")

    def stored():
        with db.tx() as conn:
            row = conn.execute(
                "SELECT energy_pct, energy_km FROM user_notify_vehicle WHERE user_id = ? AND vehicle_id = ?", (uid, vid)
            ).fetchone()
        return row["energy_pct"], row["energy_km"]

    # a level: the range is stored as "not used" (0) - one way or the other, never both
    r = client.post(
        "/settings/notifications/matrix",
        data={
            f"ev_{vid}": ["low_energy"],
            f"em_{vid}": "pct",
            f"ep_{vid}": "18",
            f"ek_{vid}": "120",
            "em_new": "km",
            "ep_new": "22",
            "ek_new": "150",
        },
    )
    assert r.status_code == 303 and stored() == (18, 0)
    with db.tx() as conn:
        m = notify.matrix(conn, uid)
        car = m["cars"][0]
        assert (car["mode"], car["energy_pct"], car["energy_km"]) == ("pct", 18, None)
        assert (m["energy_mode"], m["energy_pct"], m["energy_km"]) == ("km", None, 150)  # the choice for new cars: a range
    page = client.get("/settings/user").text
    assert f'name="em_{vid}" value="pct" checked' in page.replace("\n", " ") or f'name="em_{vid}" value="pct"  checked' in page.replace(
        "\n", " "
    )
    assert f'name="ep_{vid}"' in page and f'name="ek_{vid}"' in page and 'name="em_new"' in page
    assert (
        page.index("Only what this car delivers is offered")
        < page.index(f'name="ev_{vid}" value="low_energy"')
        < page.index(f'name="em_{vid}"')
    )  # the explanation stands at the top of the car's window, its choice right under its switch
    # a range
    client.post(
        "/settings/notifications/matrix", data={f"ev_{vid}": ["low_energy"], f"em_{vid}": "km", f"ep_{vid}": "18", f"ek_{vid}": "120"}
    )
    assert stored() == (0, 120)
    with db.tx() as conn:
        assert notify.matrix(conn, uid)["cars"][0]["mode"] == "km"
    # a range chosen but left empty falls back to the level (the car's yellow level when that is empty, too)
    client.post("/settings/notifications/matrix", data={f"ev_{vid}": ["low_energy"], f"em_{vid}": "km", f"ep_{vid}": "", f"ek_{vid}": ""})
    assert stored() == (None, 0)
    client.post("/settings/notifications/matrix", data={f"ev_{vid}": ["low_energy"]})  # a form without the fields leaves them alone
    assert stored() == (None, 0)
    client.post("/settings/notifications/matrix", data={f"ev_{vid}": ["low_energy"], f"em_{vid}": "pct", f"ep_{vid}": "500"})
    assert stored() == (99, 0)  # held to what makes sense
    client.post("/settings/notifications/matrix", data={f"ev_{vid}": ["low_energy"], f"em_{vid}": "km", f"ek_{vid}": "99999"})
    assert stored() == (0, 3000)
