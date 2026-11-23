"""The connection map: what a plugin sends and reads is noted per signal (last value, time, a history of ten), mapped to the area it lands in, and
the map stays light with many signals."""

import json

import pytest
from fastapi.testclient import TestClient

from carassistant import db, linkmap


@pytest.fixture()
def car(env):
    with db.tx() as c:
        vid = c.execute("INSERT INTO vehicles(name, fuel_type) VALUES('Map Car', 'petrol')").lastrowid
        c.execute(
            "INSERT INTO vehicle_addons(vehicle_id, kind, addon_id, manifest, status, active, created_at) VALUES(?, 'plugin', 'p-one', ?, 'configured', 1, datetime('now'))",
            (vid, json.dumps({"id": "p-one", "kind": "plugin", "name": "Plugin One", "icon": "plug"})),
        )
    linkmap._seen.clear()
    return vid


def _call(conn, vid, method, path, data=None, addon="p-one"):
    parts = ["", "api", "v1", "vehicles", str(vid), *path.strip("/").split("/")]
    return linkmap.record(conn, vid, addon, method, parts, data)


def test_a_post_of_data_becomes_one_signal_per_field_with_its_area(car):
    with db.tx() as c:
        n = _call(
            c,
            car,
            "POST",
            "data",
            {
                "ignition": True,
                "position": {"lat": 1.5, "lon": 2.5},
                "tyre_pressure_bar": {"fl": 2.4},
                "doors": {"front_left": True},
                "fuel_level_pct": 55,
                "measured_at": "x",
            },
        )
        assert n == 5  # measured_at is no signal
        rows = {r["name"]: r for r in linkmap.signals_of(c, car, "p-one")}
    assert (
        rows["ignition"]["area"] == "dashboard" and rows["position"]["area"] == "location" and rows["tyre_pressure_bar"]["area"] == "tires"
    )
    assert rows["doors"]["area"] == "security" and rows["fuel_level_pct"]["area"] == "energy"
    assert json.loads(rows["position"]["last_value"]) == {"lat": 1.5, "lon": 2.5} and rows["ignition"]["direction"] == "set"


def test_the_other_calls_land_where_they_belong(car):
    with db.tx() as c:
        _call(c, car, "POST", "track", {"points": [{"lat": 1, "lon": 2}, {"lat": 3, "lon": 4}]})
        _call(c, car, "POST", "refuel", {"amount": 40})
        _call(c, car, "POST", "logs", {"lines": ["a", "b"]})
        _call(c, car, "POST", "signals", {"signals": {"kombi.odo_km": 52340}})
        _call(c, car, "POST", "modules/coding-demo/units", {"rows": [{"values": {}}], "delete": []})
        _call(c, car, "GET", "control")
        _call(c, car, "GET", "plugin-settings")
        rows = {(r["direction"], r["name"]): r for r in linkmap.signals_of(c, car, "p-one")}
    assert rows[("set", "track")]["area"] == "trips" and json.loads(rows[("set", "track")]["last_value"])["points"] == 2
    assert rows[("set", "refuel")]["area"] == "energy" and rows[("set", "logs")]["area"] == "logs"
    assert rows[("set", "signals.kombi.odo_km")]["area"] == "signals" and rows[("set", "units")]["area"] == "int:coding-demo"
    assert rows[("get", "control")]["area"] == "control" and rows[("get", "plugin-settings")]["last_value"] is None  # a read has no value


def test_a_value_is_noted_when_it_changes_and_the_history_keeps_ten(car):
    with db.tx() as c:
        for i in range(14):
            linkmap._seen.clear()  # (as if the throttle had expired)
            _call(c, car, "POST", "data", {"fuel_level_pct": 40 + i})
        history = linkmap.history_of(c, car, "p-one", "set", "fuel_level_pct")
        state = linkmap.signals_of(c, car, "p-one")[0]
    assert (
        len(history) == linkmap.HISTORY and json.loads(history[0]["value"]) == 53 and json.loads(history[-1]["value"]) == 44
    )  # newest first
    assert state["hits"] == 14 and json.loads(state["last_value"]) == 53


def test_the_same_value_within_thirty_seconds_writes_nothing(car):
    with db.tx() as c:
        assert _call(c, car, "POST", "data", {"fuel_level_pct": 50}) == 1
        assert _call(c, car, "POST", "data", {"fuel_level_pct": 50}) == 0  # unchanged, a moment later
        assert _call(c, car, "POST", "data", {"fuel_level_pct": 51}) == 1  # changed: noted at once
        assert len(linkmap.history_of(c, car, "p-one", "set", "fuel_level_pct")) == 2


def test_a_plugin_cannot_fill_the_database_and_a_value_is_cut(car, monkeypatch):
    monkeypatch.setattr(linkmap, "MAX_SIGNALS", 5)
    with db.tx() as c:
        for i in range(12):
            _call(c, car, "POST", "signals", {"signals": {f"s.n{i}": i}})
        assert len(linkmap.signals_of(c, car, "p-one")) == 5
        _call(c, car, "POST", "data", {"warnings": {"x": "y" * 5000}})
    big = linkmap._raw({"a": "y" * 5000})
    assert len(big) <= linkmap.MAX_VALUE


def test_without_a_plugin_nothing_is_noted_and_forgetting_removes_everything(car):
    with db.tx() as c:
        assert _call(c, car, "POST", "data", {"ignition": True}, addon=None) == 0
        _call(c, car, "POST", "data", {"ignition": True})
        linkmap.forget(c, car, "p-one")
        assert linkmap.signals_of(c, car) == [] and linkmap.history_of(c, car, "p-one", "set", "ignition") == []


def test_the_graph_is_one_line_per_plugin_and_area_not_per_signal(car):
    with db.tx() as c:
        c.execute(
            "INSERT INTO vehicle_addons(vehicle_id, kind, addon_id, manifest, status, active, created_at) VALUES(?, 'integration', 'coding-demo', ?, 'configured', 1, datetime('now'))",
            (car, json.dumps({"id": "coding-demo", "kind": "integration", "name": "Coding", "icon": "memory"})),
        )
        _call(c, car, "POST", "data", {f"k{i}": i for i in range(30)} | {"ignition": True, "tyre_pressure_bar": {"fl": 2.2}})
        _call(c, car, "GET", "data")
        _call(c, car, "POST", "modules/coding-demo/units", {"rows": []})
        g = linkmap.graph(c, car)
        assert g["version"] == linkmap.graph(c, car)["version"]  # the same map, the same marker
    assert [p["id"] for p in g["plugins"]] == ["p-one"] and g["plugins"][0]["tint"] == 1 and g["plugins"][0]["sets"] >= 32
    pairs = {(e["plugin"], e["area"], e["dir"]) for e in g["edges"]}
    assert ("p-one", "dashboard", "set") in pairs and ("p-one", "dashboard", "get") in pairs and ("p-one", "tires", "set") in pairs
    assert ("p-one", "int:coding-demo", "set") in pairs and len(g["edges"]) <= 6  # 32 signals, a handful of lines
    keys = [a["key"] for a in g["areas"]]
    assert (
        "dashboard" in keys and "tires" in keys and "int:coding-demo" in keys and "security" not in keys
    )  # only areas with traffic are drawn


def test_the_middleware_notes_a_real_call_of_a_plugin_by_its_token(env):
    import re

    from carassistant import web

    client = TestClient(web.app, client=("172.30.32.2", 1), follow_redirects=False)
    assert client.post("/vehicles", data={"name": "Token Car", "odometer": "100"}).status_code == 303
    page = client.post("/integrations/api/tokens", data={"name": "p-one", "vehicle_id": "1"})
    secret = re.search(r"ca_[A-Za-z0-9_-]{20,}", page.text).group(0)
    with db.tx() as c:
        token_id = c.execute("SELECT id FROM api_tokens ORDER BY id DESC LIMIT 1").fetchone()["id"]
        c.execute(
            "INSERT INTO vehicle_addons(vehicle_id, kind, addon_id, manifest, status, active, token_id, created_at) VALUES(1, 'plugin', 'p-one', ?, 'configured', 1, ?, datetime('now'))",
            (json.dumps({"id": "p-one", "kind": "plugin", "name": "P"}), token_id),
        )
    linkmap._seen.clear()
    r = client.post("/api/v1/vehicles/1/data", json={"ignition": True, "fuel_level_pct": 60}, headers={"Authorization": f"Bearer {secret}"})
    assert r.status_code == 200, r.text
    assert client.get("/api/v1/vehicles/1/control", headers={"Authorization": f"Bearer {secret}"}).status_code == 200
    with db.tx() as c:
        names = {(s["direction"], s["name"]) for s in linkmap.signals_of(c, 1, "p-one")}
    assert {("set", "ignition"), ("set", "fuel_level_pct"), ("get", "control")} <= names
    assert client.post(
        "/api/v1/vehicles/1/data", json={"nonsense_field": 1}, headers={"Authorization": f"Bearer {secret}"}
    ).status_code in (200, 422)
