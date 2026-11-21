import json

import pytest

from carassistant import config, db, fuelproviders, stations

FR = {
    "results": [
        {
            "adresse": "2 RUE X",
            "cp": "75010",
            "ville": "Paris",
            "geom": {"lat": 48.879, "lon": 2.37},
            "gazole_prix": 2.162,
            "e10_prix": 1.941,
            "sp95_prix": None,
        },
        {"adresse": "far away", "cp": "1", "ville": "Y", "geom": {"lat": 49.9, "lon": 2.37}, "gazole_prix": 1.0},
        {"adresse": "broken", "geom": {}},
    ]
}


def test_the_shipped_french_provider_reads_a_real_shaped_answer():
    d = fuelproviders.load()["fr"]
    got = fuelproviders.parse(d, FR)
    assert len(got) == 2  # the one without coordinates is dropped
    assert got[0]["name"] == "2 RUE X" and got[0]["address"] == "75010 Paris" and got[0]["prices"] == {"e10": 1.941, "diesel": 2.162}
    params, headers = fuelproviders.request_parts(d, 48.8566, 2.3522, 5, "")
    assert params["where"] == "within_distance(geom, geom'POINT(2.35220 48.85660)', 5km)" and headers == {}


def test_a_definition_must_be_https_and_not_take_over_a_built_in_id():
    base = {"id": "xx", "url": "https://a.example.com/x", "fields": {"lat": "a", "lon": "b"}}
    assert fuelproviders.clean(base)["id"] == "xx"
    for bad in (
        {**base, "url": "http://a.example.com/x"},
        {**base, "id": "osm"},
        {**base, "id": "Bad Id"},
        {**base, "fields": {"lat": "a"}},
        "text",
    ):
        assert fuelproviders.clean(bad) is None


def test_a_file_in_the_data_folder_adds_a_provider_and_a_key_is_needed_when_asked(env, monkeypatch):
    folder = fuelproviders.user_dir()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "xx.json").write_text(
        json.dumps(
            {
                "id": "xx",
                "name": "Example land",
                "countries": ["xx", "ZZ"],
                "url": "https://prices.example.com/api",
                "key": {"header": "X-Key", "url": "https://prices.example.com/key"},
                "params": {"lat": "{lat}", "lon": "{lon}", "r": "{radius_m}"},
                "items": "stations",
                "fields": {"lat": "latitude", "lon": "longitude", "name": "brand"},
                "prices": {"diesel": "price.diesel"},
            }
        )
    )
    (folder / "broken.json").write_text("{not json")
    assert "xx" in fuelproviders.load() and "broken" not in fuelproviders.load()
    assert next(s["id"] for s in stations.sources("ZZ")) == "xx"  # the provider of the country first
    with pytest.raises(stations.StationsError):  # no key yet: nothing is asked
        stations.nearby(10.0, 20.0, 5, "diesel", "xx", "price")
    with db.tx() as conn:
        db.set_setting(conn, "int.fuelkey.xx", "k3y")
    config.forget_settings()
    seen = {}

    class Answer:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "stations": [
                    {"latitude": 10.01, "longitude": 20.0, "brand": "Near", "price": {"diesel": 1.5}},
                    {"latitude": 11, "longitude": 20, "brand": "Far", "price": {"diesel": 1}},
                ]
            }

    def fake(method, url, params=None, data=None, headers=None, timeout=None):
        seen.update(method=method, url=url, params=params, headers=headers)
        return Answer()

    monkeypatch.setattr(stations.requests, "request", fake)
    found, used = stations.nearby(10.0, 20.0, 5, "diesel", "xx", "price")
    assert used == "xx" and [s.name for s in found] == ["Near"] and found[0].price == 1.5  # the far one is outside the radius
    assert seen["headers"]["X-Key"] == "k3y" and seen["params"]["r"] and seen["url"].startswith("https://")


def test_a_service_asked_for_one_fuel_at_a_time_gets_the_code_and_the_price_of_that_fuel(env, monkeypatch):
    d = fuelproviders.load()["at"]
    params, _ = fuelproviders.request_parts(d, 48.2, 16.4, 25, "", "diesel")
    assert params["fuelType"] == "DIE" and fuelproviders.request_parts(d, 48.2, 16.4, 25, "", "e5")[0]["fuelType"] == "SUP"
    answer = [
        {
            "name": "A",
            "open": True,
            "location": {"latitude": 48.2, "longitude": 16.4, "address": "Weg 1", "postalCode": "1010", "city": "Wien"},
            "prices": [{"fuelType": "DIE", "amount": 1.979}],
        }
    ]
    got = fuelproviders.parse(d, answer, "diesel")
    assert got[0]["prices"] == {"diesel": 1.979} and got[0]["address"] == "Weg 1, 1010 Wien" and got[0]["is_open"] is True
    assert stations.fetch_provider(d, 48.2, 16.4, 5, "lpg") == []  # a fuel the service does not have
