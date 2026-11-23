"""The connection map page and its data routes - and that it stays light with many connections."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from carassistant import db, linkmap


@pytest.fixture()
def world(env):
    from carassistant import web

    client = TestClient(web.app, client=("172.30.32.2", 1), follow_redirects=False)  # inside Home Assistant: an administrator
    assert client.post("/vehicles", data={"name": "Map Car", "odometer": "100"}).status_code == 303
    linkmap._seen.clear()
    return client


def _plugin(conn, addon_id, name, icon="plug"):
    conn.execute(
        "INSERT INTO vehicle_addons(vehicle_id, kind, addon_id, manifest, status, active, created_at) VALUES(1, 'plugin', ?, ?, 'configured', 1, datetime('now'))",
        (addon_id, json.dumps({"id": addon_id, "kind": "plugin", "name": name, "icon": icon})),
    )


def _call(conn, addon, method, path, data=None):
    return linkmap.record(conn, 1, addon, method, ["", "api", "v1", "vehicles", "1", *path.split("/")], data)


def test_the_page_draws_plugins_areas_and_lines_and_escapes_what_a_plugin_calls_itself(world):
    with db.tx() as c:
        _plugin(c, "p-one", "Plugin <b>One</b>")
        _call(c, "p-one", "POST", "data", {"ignition": True, "tyre_pressure_bar": {"fl": 2.4}})
        _call(c, "p-one", "GET", "control")
    page = world.get("/v/1/plugins/connections")
    assert page.status_code == 200
    html = page.text
    assert 'id="lm"' in html and 'id="lm-wires"' in html and "linkmap.js" in html
    assert "Plugin &lt;b&gt;One&lt;/b&gt;" in html and "Plugin <b>One</b>" not in html  # a name from a plugin is never HTML
    assert "Dashboard and vehicle data" in html and "Tyres" in html and "Control and settings" in html
    assert ("data-edges" in html and '"dir":"set"' in html.replace(" ", "")) or "&#34;dir&#34;:&#34;set&#34;" in html.replace(" ", "")
    assert 'class="current' not in html  # (the tab bar marks the page: the Connections tab is on)
    assert "Connections" in html


def test_an_empty_car_says_so_instead_of_drawing_nothing(world):
    html = world.get("/v/1/plugins/connections").text
    assert "No plugin is installed yet" in html and 'id="lm-board"' not in html
    with db.tx() as c:
        _plugin(c, "p-one", "Quiet")
    html = world.get("/v/1/plugins/connections").text
    assert "No connection was seen yet" in html and 'id="lm-board"' in html


def test_the_data_routes_answer_with_signals_history_and_a_light_state(world):
    with db.tx() as c:
        _plugin(c, "p-one", "One")
        for v in (40, 41, 42):
            linkmap._seen.clear()
            _call(c, "p-one", "POST", "data", {"fuel_level_pct": v})
        _call(c, "p-one", "POST", "signals", {"signals": {"kombi.x": 1}})
    light = world.get("/v/1/plugins/connections/graph.json").json()
    assert light["plugins"][0]["id"] == "p-one" and light["plugins"][0]["state"] == "live" and light["version"]
    signals = world.get("/v/1/plugins/connections/signals.json?plugin=p-one&area=energy").json()
    assert (
        signals["raw"] is True and [s["name"] for s in signals["signals"]] == ["fuel_level_pct"] and signals["signals"][0]["value"] == "42"
    )
    only_area = world.get("/v/1/plugins/connections/signals.json?area=signals").json()["signals"]
    assert [s["name"] for s in only_area] == ["signals.kombi.x"]
    assert world.get("/v/1/plugins/connections/signals.json").status_code == 400
    hist = world.get("/v/1/plugins/connections/history.json?plugin=p-one&name=fuel_level_pct&dir=set").json()
    assert [h["value"] for h in hist["history"]] == ["42", "41", "40"] and hist["value"] == "42"  # newest first
    assert world.get("/v/1/plugins/connections/history.json?plugin=p-one&name=x&dir=sideways").status_code == 400
    assert world.get("/v/1/plugins/connections/graph.json").headers["cache-control"] == "no-store"


def test_a_hundred_connections_stay_light(world):
    """8 plugins with 100 signals each: writing, the map, the page and a list all stay quick and small."""
    with db.tx() as c:
        for i in range(8):
            _plugin(c, f"p-{i}", f"Plugin {i}")
        started = time.perf_counter()
        for i in range(8):
            for n in range(100):
                _call(c, f"p-{i}", "POST", "signals", {"signals": {f"s.n{n:03d}": n}})
        wrote = time.perf_counter() - started
    assert wrote < 6.0  # 800 signals (each a read and a write, in a slow test machine)
    with db.tx() as c:
        started = time.perf_counter()
        g = linkmap_graph = linkmap.graph(c, 1)
        built = time.perf_counter() - started
    assert built < 0.5 and len(g["edges"]) == 8 and linkmap_graph["version"]  # one line per plugin and area: 8, not 800
    started = time.perf_counter()
    page = world.get("/v/1/plugins/connections")
    assert page.status_code == 200 and time.perf_counter() - started < 3.0
    assert len(page.text) < 120_000  # the signals are not in the page
    rows = world.get("/v/1/plugins/connections/signals.json?plugin=p-3").json()["signals"]
    assert len(rows) == 100
    capped = world.get("/v/1/plugins/connections/signals.json?plugin=p-3&limit=5").json()["signals"]
    assert len(capped) == 5
    with db.tx() as c:
        assert (
            c.execute("SELECT COUNT(*) FROM signal_history").fetchone()[0] <= 800 * linkmap.HISTORY
        )  # a bounded history, never a growing log


def test_the_page_is_calm_tiles_for_the_phone_the_unconnected_areas_folded_and_the_explanations_only_in_the_detail(world):
    with db.tx() as c:
        _plugin(c, "p-one", "Plugin One", "car")
        _call(c, "p-one", "POST", "data", {"ignition": True, "tyre_pressure_bar": {"fl": 2.4}})
    html = world.get("/v/1/plugins/connections").text
    assert 'class="lm-tiles"' in html and 'class="lm-tile"' in html and 'data-area="dashboard"' in html  # the phone shows a card with tiles
    assert "lm-intro" not in html and html.count("lm-legend") == 1  # no introduction card: one line and a thin legend
    assert 'class="lm-rest"' not in html  # nothing to fold yet: the areas nobody uses are not drawn at all
    with db.tx() as c:
        c.execute(
            "INSERT INTO vehicle_addons(vehicle_id, kind, addon_id, manifest, status, active, created_at) VALUES(1, 'integration', 'quiet-int', ?, 'configured', 1, datetime('now'))",
            ('{"id": "quiet-int", "kind": "integration", "name": "Quiet", "icon": "puzzle", "version": "1"}',),
        )
    html = world.get("/v/1/plugins/connections").text
    assert 'class="lm-rest"' in html and "More areas (1)" in html  # an integration nobody talks to is folded under one line
