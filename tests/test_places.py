"""Place names of trips (map info): only while the switch is on, kept once asked, never over a name typed by hand."""

from tests.test_web import create_vehicle

from carassistant import db, places, status


class _Answer:
    def __init__(self, data, code=200):
        self._data, self.status_code = data, code

    def json(self):
        return self._data


def _trip(vid, start, end):
    with db.tx() as conn:
        return conn.execute(
            "INSERT INTO trips(vehicle_id, date, start_place, end_place, category, source, distance_km) VALUES(?,?,?,?, 'private', 'track', 5)",
            (vid, "2026-11-15", start, end),
        ).lastrowid


def _places(tid):
    with db.tx() as conn:
        row = conn.execute("SELECT start_place, end_place FROM trips WHERE id = ?", (tid,)).fetchone()
    return row["start_place"], row["end_place"]


def test_a_short_name_is_only_the_place():
    assert places.short({"address": {"road": "Hauptstrasse", "house_number": "5", "city": "Berlin"}}) == "Berlin"
    assert places.short({"address": {"footway": "Weg", "village": "Dorf"}}) == "Dorf"
    assert places.short({"name": "Bahnhof", "address": {}}) == "Bahnhof"
    assert places.short({"display_name": "A, B, C"}) == "A"
    assert places.short({}) == ""


def _own_server(url="https://geo.example.com/reverse"):
    from carassistant import config

    with db.tx() as conn:
        db.set_setting(conn, "map.geocoder_url", url)
    config.forget_settings()


def test_by_default_the_names_come_from_the_offline_list_and_nobody_is_asked(client, monkeypatch):
    vid = create_vehicle(client)

    def boom(*a, **k):
        raise AssertionError("the internet must not be asked")

    monkeypatch.setattr(places.requests, "get", boom)
    tid = _trip(vid, "52.50000, 13.40000", "-33.87000, 151.21000")  # Berlin and Sydney: worldwide, without the map info
    assert places.fill_missing() == 2
    assert _places(tid) == ("Berlin", "Sydney")
    assert places.fill_missing() == 0


def test_a_spot_far_from_every_city_keeps_its_coordinates(client):
    vid = create_vehicle(client)
    tid = _trip(vid, "0.00000, -30.00000", "52.50000, 13.40000")  # open ocean
    places.fill_missing()
    assert _places(tid) == ("0.00000, -30.00000", "Berlin")


def test_the_nearest_big_city_wins_over_a_district():
    from carassistant import citydb

    assert citydb.nearest(52.52, 13.405) == "Berlin" and citydb.nearest(35.68, 139.69) == "Tokyo"
    assert citydb.nearest(48.14, 11.58) == "Munich" and citydb.nearest(48.14, 11.58, "de") == "München"  # German names for a German app
    assert citydb.nearest(48.208, 16.373, "de") == "Wien" and citydb.nearest(41.9, 12.5, "de") == "Rom"
    assert citydb.nearest(95.0, 0.0) is None


def test_with_an_own_server_set_nothing_is_asked_while_the_map_info_is_off(client, monkeypatch):
    vid = create_vehicle(client)
    _own_server()
    tid = _trip(vid, "52.50000, 13.40000", "52.51000, 13.41000")

    def boom(*a, **k):
        raise AssertionError("the internet must not be asked")

    monkeypatch.setattr(places.requests, "get", boom)
    assert places.fill_missing() == 0
    assert _places(tid) == ("52.50000, 13.40000", "52.51000, 13.41000")  # the coordinates stay


def test_with_an_own_server_and_the_map_info_on_the_coordinates_become_names_once(client, monkeypatch):
    vid = create_vehicle(client)
    _own_server()
    with db.tx() as conn:
        db.set_setting(conn, status.MAP_SETTING, "1")
    asked = []

    def fake(url, params=None, headers=None, timeout=None):
        asked.append((params["lat"], params["lon"], headers["User-Agent"]))
        return _Answer({"address": {"road": f"Road {len(asked)}", "city": f"Town {len(asked)}"}})

    monkeypatch.setattr(places.requests, "get", fake)
    monkeypatch.setattr(places.time, "sleep", lambda s: None)
    mine = _trip(vid, "52.50000, 13.40000", "52.51000, 13.41000")
    typed = _trip(vid, "Home", "52.50000, 13.40000")  # a name by hand next to a spot already known
    assert places.fill_missing() == 3
    assert _places(mine) == ("Town 1", "Town 2")
    assert _places(typed) == ("Home", "Town 1")  # the typed name stays, the known spot comes from the kept answer
    assert len(asked) == 2 and asked[0][2].startswith("CarAssistant/")  # the same spot was asked for only once; the app names itself
    assert places.fill_missing() == 0 and len(asked) == 2  # nothing left to ask


def test_an_answer_that_fails_leaves_the_coordinates(client, monkeypatch):
    vid = create_vehicle(client)
    _own_server()
    with db.tx() as conn:
        db.set_setting(conn, status.MAP_SETTING, "1")
    monkeypatch.setattr(places.requests, "get", lambda *a, **k: _Answer({}, 500))
    monkeypatch.setattr(places.time, "sleep", lambda s: None)
    tid = _trip(vid, "52.50000, 13.40000", "52.51000, 13.41000")
    assert places.fill_missing() == 0
    assert _places(tid) == ("52.50000, 13.40000", "52.51000, 13.41000")


def test_names_kept_earlier_with_a_street_become_the_place(client, monkeypatch):
    vid = create_vehicle(client)
    _own_server()
    with db.tx() as conn:
        db.set_setting(conn, status.MAP_SETTING, "1")
        conn.execute("INSERT INTO place_names(key, name, created_at) VALUES('en|52.5000,13.4000', 'Main Street, Berlin', 'now')")
    tid = _trip(vid, "Main Street, Berlin", "Main Street, Berlin")
    monkeypatch.setattr(places.requests, "get", lambda *a, **k: _Answer({}, 500))
    places.fill_missing()
    assert _places(tid) == ("Berlin", "Berlin")


def test_the_spot_of_the_car_gets_place_and_street(conn):
    from carassistant import places

    data = {"address": {"road": "Hauptstraße", "house_number": "12", "town": "Beispielstadt"}}
    assert places.street(data) == "Hauptstraße 12" and places.short(data) == "Beispielstadt"
    assert places.here_cached(conn, 50.1, 8.6) is None
    conn.execute(
        "INSERT INTO place_names(key, name, created_at) VALUES(?,?, '2026-11-20T10:00:00')",
        ("here:" + places._key(50.1, 8.6, "en"), "Beispielstadt\tHauptstraße 12"),
    )
    assert places.here_cached(conn, 50.1, 8.6) == ("Beispielstadt", "Hauptstraße 12")


def test_the_address_for_place_names_can_be_changed_and_must_be_https(env):
    from carassistant import db, places

    assert places.source_url() == places.SOURCE
    assert places.clean_source("") == "" and places.clean_source(" https://geo.example.com/reverse ") == "https://geo.example.com/reverse"
    for bad in ("http://geo.example.com/reverse", "https://", "ftp://x.example.com", "https://user:pw@geo.example.com/"):
        with __import__("pytest").raises(ValueError):
            places.clean_source(bad)
    with db.tx() as conn:
        db.set_setting(conn, "map.geocoder_url", "https://geo.example.com/reverse")
    from carassistant import config

    config.forget_settings()
    assert places.source_url() == "https://geo.example.com/reverse"
