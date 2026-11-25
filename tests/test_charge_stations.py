"""Charging station search (electric cars): OpenStreetMap without a key, Open Charge Map with a key of the person's own - read from data, shown with
the plugs and their power, filtered by power and plug, with the sources named. Nothing is requested before a person looks for charging points."""

import json
import logging

import pytest
from tests.test_web import create_vehicle, slug

from carassistant import chargeproviders, db, stations

OSM = {
    "elements": [
        {
            "type": "node",
            "lat": 50.0152,
            "lon": 8.0201,
            "tags": {
                "amenity": "charging_station",
                "name": "Town hall",
                "operator": "City works",
                "capacity": "6",
                "socket:ccs": "2",
                "socket:ccs:output": "150 kW",
                "socket:type2": "4",
                "socket:type2:output": "22 kW",
                "fee": "yes",
                "opening_hours": "24/7",
                "addr:street": "Main street",
                "addr:housenumber": "1",
                "addr:postcode": "12345",
                "addr:city": "Town",
            },
        },
        {
            "type": "node",
            "lat": 50.03,
            "lon": 8.04,
            "tags": {
                "amenity": "charging_station",
                "brand": "Market",
                "socket:type2": "2",
                "socket:type2:output": "11",
                "fee": "no",
                "access": "customers",
            },
        },
        {
            "type": "way",
            "center": {"lat": 50.05, "lon": 8.0},
            "tags": {"amenity": "charging_station", "name": "Motorway", "socket:ccs": "8", "socket:ccs:output": "350 kW"},
        },
        {"type": "node", "lat": 50.01, "lon": 8.01, "tags": {"amenity": "charging_station", "charging_station:output": "50 kW"}},
        {"type": "node", "tags": {"amenity": "charging_station"}},  # no position: left out
    ]
}

OCM = [
    {
        "NumberOfPoints": 4,
        "UsageCost": "0.45 EUR/kWh",
        "UsageType": {"Title": "Public"},
        "StatusType": {"IsOperational": True},
        "OperatorInfo": {"Title": "Operator A"},
        "DataProvider": {"Title": "Open Data Example", "License": "CC BY 4.0"},
        "AddressInfo": {
            "Title": "Car park",
            "AddressLine1": "Road 1",
            "Postcode": "12345",
            "Town": "Town",
            "Latitude": 50.0,
            "Longitude": 8.0,
        },
        "Connections": [
            {"ConnectionType": {"Title": "CCS (Type 2)"}, "PowerKW": 150, "Quantity": 2},
            {"ConnectionType": {"Title": "Type 2 (Socket Only)"}, "PowerKW": 22, "Quantity": 2},
            {"ConnectionType": {"Title": "CHAdeMO"}, "PowerKW": 50},
        ],
    },
    {
        "StatusType": {"IsOperational": False},
        "AddressInfo": {"Title": "Broken one", "Latitude": 50.01, "Longitude": 8.01},
        "Connections": [{"ConnectionType": {"Title": "Tesla Supercharger"}, "PowerKW": 250}],
    },
    {"AddressInfo": {"Title": "far away", "Latitude": 51.5, "Longitude": 8.0}},
    {"AddressInfo": {"Title": "no position"}},
]


def test_openstreetmap_charging_points_give_plugs_power_fee_and_access():
    got = stations.normalize_overpass_charge(OSM, (50.0, 8.0))
    assert len(got) == 4  # the one without a position is dropped
    hall, market, motorway, only_output = got
    assert hall.name == "Town hall" and hall.operator == "City works" and hall.points == 6 and hall.max_kw == 150
    assert [(p["type"], p["n"], p["kw"]) for p in hall.plugs] == [("ccs", 2, 150.0), ("type2", 4, 22.0)]  # the strongest first
    assert hall.address == "Main street 1, 12345 Town" and hall.hours == "24/7" and hall.free is False
    assert market.name == "Market" and market.free is True and market.access == "customers" and market.max_kw == 11  # "11" without a unit
    assert motorway.max_kw == 350 and motorway.points is None
    assert only_output.max_kw == 50 and only_output.plugs == () and only_output.name == "?"  # the power of the whole site, no plug known


def test_the_words_of_a_service_become_a_kind_of_plug():
    kind = chargeproviders.plug_type
    assert kind("CCS (Type 2)") == "ccs" and kind("Type 2 (Socket Only)") == "type2" and kind("CHAdeMO") == "chademo"
    assert kind("Tesla Supercharger") == "nacs" and kind("NACS") == "nacs" and kind("Type 1 (J1772)") == "type1"
    assert kind("Europlug 2-Pin (CEE 7/16)") == "schuko" and kind("Something new") == "other" and kind("") == "other"
    summed = chargeproviders.sum_plugs(
        [{"type": "ccs", "kw": 50, "n": 1}, {"type": "ccs", "kw": 150, "n": 2}, {"type": "type2", "kw": 22, "n": 2}]
    )
    assert summed == [{"type": "ccs", "label": "", "n": 3, "kw": 150}, {"type": "type2", "label": "", "n": 2, "kw": 22}]


def test_the_shipped_open_charge_map_file_reads_a_real_shaped_answer_and_asks_only_for_open_data():
    d = chargeproviders.load()["ocm"]
    assert d["key"]["header"] == "X-API-Key" and d["source"] == "bundled" and "openchargemap.org" in d["attribution"]
    params, headers = chargeproviders.request_parts(d, 50.0, 8.0, 15, "my-key")
    assert (
        params["opendata"] == "true" and params["latitude"] == "50.00000" and params["distance"] == "15" and params["distanceunit"] == "KM"
    )
    assert headers == {"X-API-Key": "my-key"} and "my-key" not in json.dumps(params)  # the key travels in a header, never in the address
    got = chargeproviders.parse(d, OCM)
    assert len(got) == 3  # the one without a position is dropped
    a, broken, _far = got
    assert a["name"] == "Car park" and a["address"] == "Road 1, 12345 Town" and a["operator"] == "Operator A" and a["points"] == 4
    assert a["provider"] == "Open Data Example, CC BY 4.0" and a["fee"] == "0.45 EUR/kWh" and a["operational"] is True
    assert [(p["type"], p["n"], p["kw"]) for p in a["plugs"]] == [("ccs", 2, 150), ("chademo", 1, 50), ("type2", 2, 22)]
    assert broken["operational"] is False and broken["plugs"][0]["type"] == "nacs"


def test_a_definition_must_be_https_and_not_take_over_the_built_in_source():
    base = {"id": "xx", "url": "https://a.example.com/x", "fields": {"lat": "a", "lon": "b"}}
    assert chargeproviders.clean(base)["id"] == "xx"
    for bad in (
        {**base, "url": "http://a.example.com/x"},
        {**base, "id": "osm"},
        {**base, "id": "Bad Id"},
        {**base, "fields": {"lat": "a"}},
        "text",
    ):
        assert chargeproviders.clean(bad) is None


def test_a_file_in_the_data_folder_adds_a_source(env):
    folder = chargeproviders.user_dir()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "nordic.json").write_text(
        json.dumps(
            {
                "id": "nordic",
                "name": "Nordic register",
                "countries": ["no", "SE"],
                "url": "https://nordic.example.com/api",
                "fields": {"lat": "lat", "lon": "lon"},
            }
        ),
        encoding="utf-8",
    )
    (folder / "bad.json").write_text("{ not json", encoding="utf-8")
    sources = {s["id"]: s for s in stations.charge_sources("NO")}
    assert (
        set(sources) == {"osm", "ocm", "nordic"}
        and sources["nordic"]["countries"] == ["NO", "SE"]
        and sources["nordic"]["source"] == "added"
    )
    assert sources["ocm"]["needs_key"] and not sources["ocm"]["has_key"] and sources["osm"]["has_key"]
    assert [s["id"] for s in stations.charge_sources("NO")][:2] == ["osm", "nordic"] or stations.charge_sources("NO")[0]["id"] in (
        "osm",
        "nordic",
    )


def test_power_and_plug_filters_and_the_sort():
    pts = stations.normalize_overpass_charge(OSM, (50.0, 8.0))
    assert [s.name for s in stations.filter_charge(pts, 50)] == ["Town hall", "Motorway", "?"]  # 50 kW counts; unknown power does not
    assert [s.name for s in stations.filter_charge(pts, 100)] == ["Town hall", "Motorway"]
    assert [s.name for s in stations.filter_charge(pts, 0, "type2")] == ["Town hall", "Market"]
    assert stations.filter_charge(pts, 200, "type2") == []
    assert [s.name for s in stations.sort_charge(pts, "power")][:2] == ["Motorway", "Town hall"]
    assert stations.sort_charge(pts, "distance")[0].distance_km <= stations.sort_charge(pts, "distance")[-1].distance_km


def test_openstreetmap_is_asked_once_per_area_and_only_for_charging_points(monkeypatch):
    stations.clear_cache()
    calls = []

    class Answer:
        def raise_for_status(self):
            pass

        def json(self):
            return OSM

    def post(url, data=None, headers=None, timeout=None):
        calls.append((url, data["data"], headers))
        return Answer()

    monkeypatch.setattr(stations.requests, "post", post)
    got, used = stations.nearby_charge(50.0, 8.0, 15, "osm", "power")
    assert used == "osm" and got[0].name == "Motorway" and len(got) == 4
    stations.nearby_charge(50.0, 8.0, 15, "osm", "distance", 50, "ccs")  # the filters are applied here: no second question
    assert len(calls) == 1 and '"amenity"="charging_station"' in calls[0][1] and "fuel" not in calls[0][1]
    assert "ha-car-assistant" in calls[0][2]["User-Agent"]  # the service is told who asks (the app, nothing personal)


def test_a_source_with_a_key_needs_it_and_the_key_is_never_logged(env, monkeypatch, caplog):
    stations.clear_cache()
    d = chargeproviders.load()["ocm"]
    with pytest.raises(stations.StationsError) as exc:
        stations.fetch_charge_provider(d, 50.0, 8.0, 15)
    assert exc.value.args[0] == "err.no_charge_key"  # nothing is asked without it
    with db.tx() as conn:
        db.set_setting(conn, "int.chargekey.ocm", "super-secret-key")
    from carassistant import config

    config.forget_settings()
    seen = {}

    class Answer:
        def raise_for_status(self):
            pass

        def json(self):
            return OCM

    def request(method, url, params=None, data=None, headers=None, timeout=None):
        seen.update(method=method, url=url, params=params, headers=headers)
        return Answer()

    monkeypatch.setattr(stations.requests, "request", request)
    got = stations.fetch_charge_provider(d, 50.0, 8.0, 15)
    assert (
        seen["url"] == "https://api.openchargemap.io/v3/poi/"
        and seen["params"]["opendata"] == "true"
        and seen["headers"]["X-API-Key"] == "super-secret-key"
    )
    assert [s.name for s in got] == ["Car park", "Broken one"]  # the far one is outside the radius
    assert got[1].is_open is False and got[0].provider == "Open Data Example, CC BY 4.0" and got[0].max_kw == 150 and got[0].free is None
    stations.clear_cache()

    def boom(*a, **k):
        raise stations.requests.ConnectionError("https://x/?key=super-secret-key")

    monkeypatch.setattr(stations.requests, "request", boom)
    with caplog.at_level(logging.DEBUG), pytest.raises(stations.StationsError) as exc:
        stations.fetch_charge_provider(d, 50.0, 8.0, 15)
    assert exc.value.args[0] == "err.stations_failed" and "super-secret-key" not in caplog.text


def _ev(client):
    client.post("/vehicles", data={"name": "Stromer", "fuel_type": "electric"})
    with db.tx() as conn:
        vid = conn.execute("SELECT MAX(id) FROM vehicles").fetchone()[0]
    return vid


def test_the_charging_page_of_an_electric_car_searches_and_filters(client, monkeypatch):
    vid = _ev(client)
    base = f"/v/{slug(vid)}/e/fuel"
    asked = []

    def fake(lat, lon, radius, source, sort, min_kw=0, plug=""):
        asked.append((source, sort, min_kw, plug))
        pts = stations.normalize_overpass_charge(OSM, (lat, lon))
        return stations.sort_charge(stations.filter_charge(pts, min_kw, plug), sort), "osm"

    monkeypatch.setattr(stations, "nearby_charge", fake)
    page = client.get(base).text
    assert 'id="stations"' in page and asked == []  # nothing is looked up before a person presses search
    assert (
        "Charging station search" in page
        and "Fuel stations nearby" not in page
        and "gas-station" not in page.split('id="stations"')[1][:600]
    )
    found = client.get(f"{base}?go=1&lat=50.0&lon=8.0&sort=power&kw=50&plug=ccs").text
    assert asked == [("osm", "power", 50, "ccs")]
    assert "Town hall" in found and "Motorway" in found and "Market" not in found  # CCS only, at least 50 kW
    assert "CCS 150 kW ×2" in found and "Type 2 22 kW ×4" in found and "© OpenStreetMap contributors (ODbL)" in found
    assert "Free" not in found and "24/7" in found
    assert "kw=50" in found and "plug=ccs" in found  # the filters stay in the links
    client.get(f"{base}?go=1&lat=50.0&lon=8.0&kw=7&plug=nope")  # not offered: ignored
    assert asked[-1] == ("osm", "distance", 0, "")


def test_the_charging_sources_have_their_own_key_and_default(client):
    vid = _ev(client)
    page = client.get(f"/v/{slug(vid)}/e/fuel").text
    assert "Open Charge Map" in page and "OpenStreetMap" in page and "Tankerk" not in page  # the charging sources, not the fuel prices
    assert 'name="kind" value="charge"' in page
    r = client.post(
        "/settings/fuelkey",
        data={"id": "ocm", "kind": "charge", "api_key": "abc DEF-12 3", "back": f"/v/{slug(vid)}/e/fuel"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    from carassistant import config

    config.forget_settings()
    assert chargeproviders.key_of("ocm") == "abcDEF-123"  # cleaned, kept apart from the fuel keys
    assert not config.stored_setting("int.fuelkey.ocm")
    assert client.post("/settings/fuel-defaults", data={"kind": "charge", "source": "ocm"}).status_code in (200, 204, 303)
    config.forget_settings()
    assert stations.default_charge_source() == "ocm" and stations.preferred_source() == ""
    client.post("/settings/fuelkey", data={"id": "ocm", "kind": "charge", "remove": "1"})
    config.forget_settings()
    assert (
        chargeproviders.key_of("ocm") == "" and stations.default_charge_source() == "osm"
    )  # without its key the preferred source is not used
    assert client.post("/settings/fuelkey", data={"id": "osm", "kind": "charge", "api_key": "x"}, follow_redirects=False).status_code == 303
    assert chargeproviders.key_of("osm") == ""


def test_a_fuel_car_still_gets_the_fuel_stations(client, monkeypatch):
    vid = create_vehicle(client, "Diesel One")
    page = client.get(f"/v/{slug(vid)}/e/fuel").text
    assert "Fuel stations nearby" in page and "Charging station search" not in page


def test_the_home_price_estimates_slow_charging_without_a_bill_and_says_so(client):
    """A price per kWh at home (the settings of the charging page): a slow session without a bill is counted with it - marked ``~``; a fast one (public)
    and a session with a bill are not touched."""
    from datetime import UTC, datetime, timedelta

    from carassistant import charge_detect

    vid = _ev(client)
    with db.tx() as conn:
        conn.execute("UPDATE vehicles SET battery_kwh = 60 WHERE id = ?", (vid,))
        now = datetime.now(UTC)
        for i, kw in enumerate((11, 11, 120)):  # two slow sessions and one fast
            conn.execute(
                "INSERT INTO charge_sessions(vehicle_id, started, ended, start_pct, end_pct, max_kw) VALUES(?,?,?,?,?,?)",
                (vid, (now - timedelta(days=3 + i, hours=4)).isoformat(), (now - timedelta(days=3 + i, hours=1)).isoformat(), 20, 70, kw),
            )
        assert charge_detect.stats(conn, vid)["cost"] is None  # no price, no bill: no cost at all
    assert client.post(f"/v/{slug(vid)}/home-price", data={"price": "0,30"}, follow_redirects=False).status_code == 303
    with db.tx() as conn:
        assert charge_detect.home_price(conn, vid) == 0.3
        st = charge_detect.stats(conn, vid)
        rows = {s["max_kw"]: s for s in charge_detect.sessions(conn, vid)}
    assert st["cost_estimated"] and st["cost"] == pytest.approx(2 * 30 * 0.3)  # 50 % of 60 kWh = 30 kWh, twice, at 0.30
    assert (
        rows[11]["cost_estimated"] and rows[11]["cost"] == pytest.approx(9.0) and rows[120]["cost"] is None
    )  # the fast one is not guessed
    page = client.get(f"/v/{slug(vid)}/e/fuel").text
    assert "~18,00" in page.replace(" ", "").replace(".", ",") or "~18.00" in page or "~18" in page  # the sum is marked as an estimate
    assert "partly estimated with your home price" in page and 'name="price"' in page and "Electricity at home" in page
    for bad in ("0", "-1", "abc", "11"):
        assert client.post(f"/v/{slug(vid)}/home-price", data={"price": bad}, follow_redirects=False).status_code == 303
    with db.tx() as conn:
        assert charge_detect.home_price(conn, vid) == 0.3  # a price that makes no sense is not stored
    client.post(f"/v/{slug(vid)}/home-price", data={"price": ""})
    with db.tx() as conn:
        assert charge_detect.home_price(conn, vid) is None and charge_detect.stats(conn, vid)["cost"] is None
