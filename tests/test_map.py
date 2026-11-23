"""The Map page, its search, the navigation choice and the plugin capability ``navigate``."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def car(env):
    from carassistant import db, web

    with db.tx() as conn:
        conn.execute("INSERT INTO vehicles (name, slug, fuel_type) VALUES ('Test', 'test', 'petrol')")
        vid = conn.execute("SELECT id FROM vehicles").fetchone()["id"]
    client = TestClient(web.app, base_url="http://testserver", headers={"Origin": "http://testserver"})
    return client, vid


def _map_on():
    from carassistant import db
    from carassistant import status as vs

    with db.tx() as conn:
        db.set_setting(conn, vs.MAP_SETTING, "1")


def test_the_page_asks_to_switch_the_map_on_and_then_shows_the_stage(car):
    client, vid = car
    page = client.get(f"/v/{vid}/map")
    assert page.status_code == 200 and "mapstage" not in page.text and "/settings/system#online" in page.text
    _map_on()
    page = client.get(f"/v/{vid}/map")
    assert 'id="mapstage"' in page.text and "map_full.js" in page.text and 'data-first="google"' in page.text
    assert "Google Maps" in page.text and "HERE WeGo" in page.text


def test_search_only_with_the_map_on_and_it_asks_the_service_politely(car, monkeypatch):
    from carassistant import places

    client, vid = car
    assert client.get(f"/v/{vid}/map/search?q=berlin").status_code == 404
    _map_on()
    seen = {}

    class Reply:
        status_code = 200

        def json(self):
            return [{"lat": "52.52", "lon": "13.40", "name": "Berlin", "display_name": "Berlin, Deutschland"}, {"lat": "x", "lon": "1"}]

    def fake_get(url, params=None, headers=None, timeout=None):
        seen.update(url=url, params=params, ua=headers["User-Agent"])
        return Reply()

    monkeypatch.setattr(places.requests, "get", fake_get)
    monkeypatch.setattr(places, "GAP", 0)
    places._search_cache.clear()
    r = client.get(f"/v/{vid}/map/search?q=berlin&bbox=52,13,53,14")
    assert r.status_code == 200
    assert r.json()["results"] == [{"name": "Berlin", "address": "Berlin, Deutschland", "lat": 52.52, "lon": 13.4}]
    assert seen["url"].endswith("/search") and seen["params"]["viewbox"] == "13.00000,53.00000,14.00000,52.00000"
    assert seen["ua"].startswith("CarAssistant/")
    assert client.get(f"/v/{vid}/map/search?q=be").json()["results"] == []  # too short: nothing is asked
    seen.clear()
    client.get(f"/v/{vid}/map/search?q=berlin&bbox=52,13,53,14")
    assert not seen  # the same search again comes from the memory


def test_the_search_address_follows_the_set_service():
    from carassistant import places

    assert places.search_url() == "https://nominatim.openstreetmap.org/search"


def test_the_navigation_choice_and_the_order_of_the_list(car, monkeypatch):
    from carassistant import db, navproviders

    client, vid = car
    with db.tx() as conn:
        rows, first = navproviders.options(conn, vid)
    assert first == "google" and rows[0]["name"] == "Google Maps" and not any(r["plugin"] for r in rows)
    fake = [{"key": "plugin:demo", "name": "Demo car", "pk": 1, "path": "/x/navigate"}]
    monkeypatch.setattr(navproviders, "plugins_for", lambda conn, v: fake)
    with db.tx() as conn:
        rows, first = navproviders.options(conn, vid)
    assert rows[0] == {"key": "plugin:demo", "name": "Demo car", "plugin": True} and first == "plugin:demo"  # the plugin comes first
    assert client.post("/settings/navigation", data={"provider": "waze"}).status_code in (200, 303)
    with db.tx() as conn:
        assert navproviders.chosen(conn) == "waze"
        rows, first = navproviders.options(conn, vid)
    assert first == "waze" and rows[0]["plugin"]  # an explicit choice wins, the plugin stays in the list
    client.post("/settings/navigation", data={"provider": "nonsense"})
    with db.tx() as conn:
        assert navproviders.chosen(conn) == ""


def test_links_hold_the_destination():
    from carassistant import navproviders

    assert navproviders.url("google", 52.5, 13.4).endswith("destination=52.500000%2C13.400000&travelmode=driving")
    assert navproviders.url("waze", 1, 2, "Home").startswith("https://waze.com/ul?ll=1.000000,2.000000")
    assert navproviders.url("sygic", 48.1, 11.5) == "com.sygic.aura://coordinate|11.500000|48.100000|drive"
    assert navproviders.url("nope", 1, 2) is None


def test_sending_a_destination_to_the_plugin_of_the_car(car, monkeypatch):
    from carassistant import navproviders, pluginsvc

    client, vid = car
    fake = [{"key": "plugin:demo", "name": "Demo car", "pk": 7, "path": "/demo/navigate"}]
    monkeypatch.setattr(navproviders, "plugins_for", lambda conn, v: fake)
    got = {}

    def fake_call(pk, path, payload, vehicle_id, user="ha", timeout=10.0):
        got.update(pk=pk, path=path, payload=payload, vehicle=vehicle_id)
        return True, "On its way."

    monkeypatch.setattr(pluginsvc, "call", fake_call)
    body = {"key": "plugin:demo", "lat": 52.5, "lon": 13.4, "name": "Home", "address": "Somewhere 1"}
    r = client.post(f"/v/{vid}/map/send", json=body)
    assert r.json() == {"ok": True, "message": "On its way."}
    assert got["pk"] == 7 and got["path"] == "/demo/navigate" and got["payload"]["lat"] == 52.5 and got["payload"]["vehicle"] == vid
    assert client.post(f"/v/{vid}/map/send", json={**body, "key": "google"}).status_code == 400  # a provider is no plugin
    assert client.post(f"/v/{vid}/map/send", json={**body, "lat": 99}).status_code == 400
    assert client.post(f"/v/{vid}/map/send", json={**body, "key": "plugin:other"}).json()["ok"] is False


def test_the_capability_navigate_must_point_into_a_private_route():
    from carassistant import addons

    service = {"routes": [{"prefix": "/demo/", "public": False}, {"prefix": "/open/", "public": True}]}
    assert addons.clean_capabilities({"navigate": {"path": "/demo/navigate", "label": "To the car"}}, service) == {
        "navigate": {"path": "/demo/navigate", "label": "To the car"}
    }
    assert addons.clean_capabilities({"navigate": {"path": "/open/navigate"}}, service) == {}  # public: anybody could call it
    assert addons.clean_capabilities({"navigate": {"path": "/demo/../x"}}, service) == {}
    assert addons.clean_capabilities({"navigate": {"path": "/other/x"}}, service) == {}
    assert addons.clean_capabilities("nonsense", service) == {} and addons.clean_capabilities(None, None) == {}
