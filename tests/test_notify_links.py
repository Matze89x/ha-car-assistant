"""A tap on a notification leads to the thing it is about: the card of a refuel to complete, one trip, the page of the topic - and a web push needs no saved
address for that (it carries the path of the app itself)."""

from datetime import UTC, datetime
from pathlib import Path

from tests.test_refuel_complete import _noticed, _trip
from tests.test_web import create_vehicle, slug

from carassistant import accounts, config, db, ha, i18n, notify, push


def _lines(conn, vid, events):
    vehicle = conn.execute("SELECT * FROM vehicles WHERE id = ?", (vid,)).fetchone()
    lines, _keys, pages = notify._lines_for(conn, vehicle, set(events), datetime.now(UTC), "u1", i18n.translator("en"))
    return vehicle, lines, pages


def test_one_refuel_to_complete_leads_to_its_card_and_several_to_the_list(client):
    vid, row = _noticed(client)
    with db.tx() as conn:
        vehicle, lines, pages = _lines(conn, vid, {"refuel"})
    assert "Tap to scan the receipt" in lines[0]
    assert notify.link_path(vehicle, pages) == f"/v/{slug(vid)}/e/fuel?edit={row['id']}#fuel-{row['id']}"
    with db.tx() as conn:
        conn.execute(
            "INSERT INTO fuel(vehicle_id, date, auto_kind, auto_rise, auto_at, auto_open) VALUES(?, ?, 'tank', 40, ?, 1)",
            (vid, row["date"], row["auto_at"]),
        )
        vehicle, lines, pages = _lines(conn, vid, {"refuel"})
    assert len(lines) == 2 and notify.link_path(vehicle, pages) == f"/v/{slug(vid)}/e/fuel"


def test_one_trip_leads_to_its_page_several_to_the_list_and_a_mixed_message_to_the_car(client):
    vid, _row = _noticed(client, "Trip Car")
    day = datetime.now().strftime("%Y-%m-%d")
    with db.tx() as conn:
        conn.execute(
            "INSERT INTO trips(vehicle_id, date, start_time, end_time, distance_km, end_place, source) VALUES(?,?,?,?,5,'Town','track')",
            (vid, day, "08:00", "08:20"),
        )
        trip_id = conn.execute("SELECT MAX(id) FROM trips").fetchone()[0]
        vehicle, _text, pages = _lines(conn, vid, {"trip_end"})
        assert notify.link_path(vehicle, pages) == f"/v/{slug(vid)}/trips/{trip_id}"
        _vehicle, _l, mixed = _lines(conn, vid, {"trip_end", "refuel"})
        assert len(mixed) == 2 and notify.link_path(vehicle, mixed) == f"/v/{slug(vid)}"  # two topics: the car
        conn.execute(
            "INSERT INTO trips(vehicle_id, date, start_time, end_time, distance_km, end_place, source) VALUES(?,?,?,?,5,'Town','track')",
            (vid, day, "09:00", "09:20"),
        )
        _vehicle, _l, several = _lines(conn, vid, {"trip_end"})
        assert notify.link_path(vehicle, several) == f"/v/{slug(vid)}/e/trips"


def test_open_doors_and_car_messages_lead_to_the_page_that_shows_them(client, monkeypatch):
    from carassistant import status

    vid = create_vehicle(client, "Door Car")
    monkeypatch.setattr(status, "open_closures", lambda live: ["front_left"])
    with db.tx() as conn:
        vehicle, lines, pages = _lines(conn, vid, {"open_closure"})
    assert lines and notify.link_path(vehicle, pages) == f"/v/{slug(vid)}/security"


def _person(conn, vid, events, service="mobile_app_phone"):
    uid = accounts.create_user(conn, "owner", "Correct-Horse-Battery-9", admin=True)
    notify.save_service(conn, uid, service)
    conn.execute("INSERT INTO user_notify_vehicle(user_id, vehicle_id, events, enabled) VALUES(?,?,?,1)", (uid, vid, events))
    return uid


def test_a_web_push_carries_the_path_even_when_no_address_is_saved(client, monkeypatch):
    vid, row = _noticed(client, "Push Car")
    sent = []
    monkeypatch.setattr(notify, "push_mode", lambda: True)
    monkeypatch.setattr(push, "devices", lambda conn, uid: [{"id": 1}])
    monkeypatch.setattr(push, "send", lambda conn, uid, title, body, url="", vehicle_id=None: sent.append((title, body, url)) or 1)
    with db.tx() as conn:
        _person(conn, vid, '["refuel"]')
        assert config.external_url() == ""  # nothing saved under Settings > System
        assert notify.check_users(conn, only={"refuel"}) == 1
    title, body, url = sent[0]
    assert title == "Push Car" and "Tap to scan the receipt" in body
    assert (
        url == f"/v/{slug(vid)}/e/fuel?edit={row['id']}#fuel-{row['id']}"
    )  # a path of the app itself: the same origin as the worker that shows it


def test_the_home_assistant_app_gets_the_full_address_of_the_card(client, monkeypatch):
    vid, row = _noticed(client, "Mobile Car")
    sent = []
    monkeypatch.setattr(ha, "call_service", lambda d, s, p: (sent.append(p) or True, ""))
    with db.tx() as conn:
        db.set_setting(conn, "ext.url", "https://car.example.com")
    config.forget_external()  # (the setting is saved: the next look finds it)
    with db.tx() as conn:
        _person(conn, vid, '["refuel"]')
        assert notify.check_users(conn, only={"refuel"}) == 1
    assert sent[0]["data"]["url"] == f"https://car.example.com/v/{slug(vid)}/e/fuel?edit={row['id']}#fuel-{row['id']}"


def test_the_service_worker_takes_the_open_window_there_or_opens_the_page():
    text = (Path(config.__file__).parent / "static" / "sw.js").read_text(encoding="utf-8")
    assert "new URL(" in text and "self.registration.scope" in text  # a path is resolved against the app's own address
    assert text.index(".navigate(") < text.index("openWindow(")  # first the open window, then (no window, or it refuses) a new one
    assert "catch" in text  # a window that refuses must not end the tap without a page
    assert _trip is not None  # (the helper of the other tests is shared)
