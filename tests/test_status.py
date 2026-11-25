"""Hero plaques (ignition, doors & windows) and the position card: only with data, map switchable."""

import json
import re
from datetime import UTC, datetime, timedelta

from tests.test_connectors import api, hdr, setup  # noqa: F401  (fixtures and helpers of the API tests)
from tests.test_web import create_vehicle, slug

from carassistant import db, i18n, status

T = i18n.translator("en")
NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


def live(**values):
    """Live rows as status.rows() returns them: key -> (value, arrived)."""
    return {k: (v, NOW - timedelta(minutes=5)) for k, v in values.items()}


def seed(vid: int, **values):
    with db.tx() as conn:
        for key, value in values.items():
            conn.execute(
                "INSERT INTO live(vehicle_id, key, value, updated) VALUES(?,?,?,?) ON CONFLICT(vehicle_id, key) DO UPDATE SET value = excluded.value, updated = excluded.updated",
                (vid, key, value, datetime.now(UTC).isoformat(timespec="seconds")),
            )


def test_ignition_and_closures_parse():
    assert status.ignition(live(ignition="on")) is True
    assert status.ignition(live(ignition="off")) is False
    assert status.ignition(live(ignition="maybe")) is None and status.ignition({}) is None
    doors = json.dumps({"front_left": True, "rear_left": False, "bogus": "yes"})
    assert status.closures(live(doors=doors)) == {
        "doors": {"front_left": True, "rear_left": False},
        "windows": {},
    }  # non-booleans are dropped
    assert status.closures(live(doors="not json")) is None and status.closures({}) is None


def test_hero_badges_only_with_data():
    assert status.hero_badges({}, T) == {"left": [], "right": []}
    badges = status.hero_badges(live(ignition="on"), T)
    assert badges["left"][0]["value"] == "on" and badges["left"][0]["tone"] == "ok" and badges["right"] == []
    assert status.hero_badges(live(ignition="off"), T)["left"][0]["tone"] == "off"


def test_door_and_window_badge_states():
    closed = json.dumps({"front_left": False, "front_right": False})
    right = status.hero_badges(live(doors=closed), T)["right"][0]
    assert (right["title"], right["value"], right["tone"]) == ("Doors", "closed", "ok")
    one = status.hero_badges(live(doors=json.dumps({"front_right": True, "trunk": False}), windows=closed), T)["right"][0]
    assert (one["title"], one["value"], one["tone"]) == ("Doors & windows", "Front right door open", "warn")
    many = status.hero_badges(live(doors=json.dumps({"front_left": True}), windows=json.dumps({"sunroof": True})), T)["right"][0]
    assert many["value"] == "2 open" and many["tone"] == "warn"
    only_windows = status.hero_badges(live(windows=json.dumps({"sunroof": True})), T)["right"][0]
    assert only_windows["title"] == "Windows" and only_windows["value"] == "Sunroof open"
    unknown = status.hero_badges(live(doors=json.dumps({"side_flap": True})), T)["right"][0]
    assert unknown["value"] == "Side flap open"  # an unknown name is shown as written


def test_ago_wording():
    just, five, three_h, two_d = (
        NOW - timedelta(seconds=10),
        NOW - timedelta(minutes=5),
        NOW - timedelta(hours=3),
        NOW - timedelta(days=2),
    )
    assert [status.ago(s, T, NOW) for s in (just, five, three_h, two_d)] == ["just now", "5 minutes ago", "3 hours ago", "2 days ago"]
    assert status.ago(None, T, NOW) == ""


def test_the_time_since_is_written_out_with_one_and_many_forms():
    from datetime import timedelta

    from carassistant import i18n

    de = i18n.translator("de")
    one = [status.ago(NOW - d, de, NOW) for d in (timedelta(minutes=1), timedelta(hours=1), timedelta(days=1))]
    many = [status.ago(NOW - d, de, NOW) for d in (timedelta(minutes=5), timedelta(hours=3), timedelta(days=5))]
    assert one == ["vor 1 Minute", "vor 1 Stunde", "vor einem Tag"]
    assert many == ["vor 5 Minuten", "vor 3 Stunden", "vor 5 Tagen"]
    from datetime import UTC, datetime

    live = {"speed": ("0", datetime.now(UTC) - timedelta(days=1, minutes=5))}
    assert status.freshness(live, de) == "Vor einem Tag"  # on its own at the car: a capital letter
    assert status.freshness({}, de) == ""
    # a language file that only knows the short forms keeps them
    short = lambda key, **kw: {"ago.hours": "{n} h"}.get(key, key).format(**kw)  # noqa: E731
    short.has = lambda key: key == "ago.hours"  # type: ignore[attr-defined]
    assert status.ago(NOW - timedelta(hours=3), short, NOW) == "3 h"


def test_location_needs_a_valid_position():
    assert status.location({}, T) is None
    for bad in ("nonsense", "91.0,10.0", "10.0,181.0", "1,2,3", "a,b"):
        assert status.location(live(position=bad), T) is None, bad


def test_location_card_parked_and_links():
    card = status.location(live(position="52.516275,13.377704", ignition="off"), T, NOW)
    assert card["title"].startswith("Your car has been parked here since ") and card["coords"] == "52.51628, 13.37770"
    assert [c["text"] for c in card["chips"]][1] == "Last signal 5 minutes ago"
    assert card["chips"][0]["text"].startswith("Parked since ") and card["chips"][0]["tone"] == "ok"
    urls = {link["key"]: link["url"] for link in card["links"]}
    assert urls["waze"] == "https://waze.com/ul?ll=52.516275,13.377704&navigate=yes"
    assert urls["google"].endswith("destination=52.516275,13.377704") and "daddr=52.516275,13.377704" in urls["apple"]
    moving = status.location(live(position="52.5,13.4", ignition="on"), T, NOW)
    assert moving["title"] == "Your car is driving here" and len(moving["chips"]) == 1
    assert status.location(live(position="52.5,13.4"), T, NOW)["title"] == "Last known position"  # no ignition reading


def test_api_accepts_ignition(api):  # noqa: F811
    token = setup(api)
    r = api.post("/api/v1/vehicles/1/data", headers=hdr(token), json={"ignition": True})
    assert r.status_code == 200 and r.json()["result"]["ignition"] == "stored"
    with db.tx() as conn:
        assert status.ignition(status.rows(conn, 1)) is True
    api.post("/api/v1/vehicles/1/data", headers=hdr(token), json={"ignition": False})
    with db.tx() as conn:
        assert status.ignition(status.rows(conn, 1)) is False
    for bad in ("on", 1, "true"):
        r = api.post("/api/v1/vehicles/1/data", headers=hdr(token), json={"ignition": bad})
        assert r.status_code == 422, bad


def test_home_shows_nothing_without_data(client):
    vid = create_vehicle(client)
    html = client.get(f"/v/{slug(vid)}").text
    assert "hb-item" not in html and 'id="location"' not in html and "leaflet" not in html
    assert "has-hb" not in html


def test_home_with_data_shows_plaques_and_location(client):
    vid = create_vehicle(client)
    seed(vid, ignition="off", position="52.516275,13.377704", doors=json.dumps({"front_left": True}))
    html = client.get(f"/v/{slug(vid)}").text
    assert html.count("hb-item") >= 2 and "hero-row-top" in html and "Zündung" not in html  # English UI
    assert 'id="location"' in html and "52.51628, 13.37770" in html
    assert 'rel="noopener noreferrer"' in html and "waze.com/ul?ll=52.516275,13.377704" in html
    assert "<script>" not in html  # the CSP forbids inline scripts


def test_map_is_off_by_default_and_loads_nothing(client):
    """Nothing may go online unless the user switches the map on: no map element, no Leaflet, no tile host in the CSP."""
    vid = create_vehicle(client)
    seed(vid, position="52.5,13.4")
    response = client.get(f"/v/{slug(vid)}")
    html = response.text
    assert 'id="posmap"' not in html and "leaflet" not in html and "map.js" not in html
    assert "loads nothing from the internet" in html and "waze.com" in html  # coordinates and links still work
    csp = response.headers["content-security-policy"]
    assert "openstreetmap" not in csp and "img-src 'self' data:;" in csp
    settings = client.get("/settings/system").text
    assert "checked" not in re.search(r'<input type="checkbox" name="tiles"[^>]*>', settings).group(0)


def test_map_can_be_switched_on_and_off_again(client):
    vid = create_vehicle(client)
    seed(vid, position="52.516275,13.377704")
    assert client.post("/settings/map", data={"tiles": "1"}).status_code == 303
    response = client.get(f"/v/{slug(vid)}")
    html = response.text
    assert 'id="posmap"' in html and 'data-lat="52.516275"' in html
    assert "/static/vendor/leaflet/leaflet.min.js" in html and "/static/map.js" in html
    assert 'data-tiles="/tiles"' in html
    assert "openstreetmap" not in response.headers["content-security-policy"]  # the browser never talks to OpenStreetMap itself
    assert "script-src" not in response.headers["content-security-policy"]
    assert "checked" in re.search(r'<input type="checkbox" name="tiles"[^>]*>', client.get("/settings/system").text).group(0)
    assert client.post("/settings/map", data={}).status_code == 303  # an unchecked box sends nothing
    again = client.get(f"/v/{slug(vid)}")
    assert 'id="posmap"' not in again.text and "openstreetmap" not in again.headers["content-security-policy"]


def test_static_assets_are_served(client):
    for path in ("/static/vendor/leaflet/leaflet.min.js", "/static/vendor/leaflet/leaflet.min.css", "/static/map.js"):
        assert client.get(path).status_code == 200, path


def test_api_doors_windows_locked_merge_and_read_back(api):  # noqa: F811
    token = setup(api)
    url = "/api/v1/vehicles/1/data"
    r = api.post(
        url, headers=hdr(token), json={"doors": {"front_left": False, "trunk": True}, "windows": {"sunroof": False}, "locked": True}
    )
    assert r.status_code == 200 and r.json()["result"] == {"doors": "stored", "windows": "stored", "locked": "stored"}
    api.post(url, headers=hdr(token), json={"doors": {"front_left": True, "trunk": None}})  # only these names change; null removes
    data = api.get(url, headers=hdr(token)).json()
    assert (
        data["data"]["doors"] == {"front_left": True} and data["data"]["windows"] == {"sunroof": False} and data["data"]["locked"] is True
    )
    assert set(data["updated"]) >= {"doors", "windows", "locked"}
    for bad in (
        {"doors": []},
        {"doors": {"Front": True}},
        {"doors": {"a": "open"}},
        {"locked": "yes"},
        {"doors": {f"d{i}": True for i in range(17)}},
    ):
        assert api.post(url, headers=hdr(token), json=bad).status_code == 422, bad
    assert "doors" in api.get("/api/v1", headers=hdr(token)).json()["fields"]


def test_security_page_lists_doors_and_counts_them(client):
    vid = create_vehicle(client)
    assert "closure-grid" not in client.get(f"/v/{slug(vid)}/security").text  # nothing without data
    seed(vid, doors=json.dumps({"front_left": True, "trunk": False}), locked="unlocked")
    page = client.get(f"/v/{slug(vid)}/security").text
    assert "Front left door open" in page and "Unlocked" in page and "1 open" in page and "closure-grid" in page
    assert "/security" in re.search(r'href="([^"]+/security)" class="tab[^"]*" data-alert="1"', client.get(f"/v/{slug(vid)}").text).group(0)


def test_home_shows_range_if_the_car_reports_it_else_the_odometer(client):
    from tests.test_web import create_vehicle, slug

    from carassistant import db

    vid = create_vehicle(client, "Rangey")  # odometer 50000, no live data
    page = client.get(f"/v/{slug(vid)}").text
    assert (
        'class="odo-card"' in page and "odo-drum" in page and 'aria-label="50,000 km"' in page
    )  # no range: the odometer is the big figure ...
    assert 'data-k="odometer"' in page and re.search(
        r'class="wd-slot [a-z]+ off" data-k="odometer"', page
    )  # the odometer widget is an extra look: off until it is switched on
    with db.tx() as conn:
        now = "2030-01-01T00:00:00+00:00"
        conn.execute("INSERT INTO live(vehicle_id, key, value, updated) VALUES(?, 'range_km', '540', ?)", (vid, now))
        conn.execute("INSERT INTO live(vehicle_id, key, value, updated) VALUES(?, 'fuel_level', '62', ?)", (vid, now))
    page = client.get(f"/v/{slug(vid)}").text
    assert 'class="range-km">540<' in page and "62 %" in page  # the range is the big figure with the tank level
    assert 'class="odo-card"' in page and "odo-drum" in page  # the plate stays under the car, below the range
