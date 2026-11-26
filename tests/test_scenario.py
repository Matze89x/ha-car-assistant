"""The scenario player and the 'just have a look' flow: a demo car from the standard source, run by a plugin through the normal interface."""

import io
import json
import random
import zipfile

import pytest

from carassistant import addons, connectors, db, simulator, sources, vehiclebackup
from conftest import demo_car

SCENARIO = {
    "interval_s": 5,
    "timelapse": 12,
    "places": [
        {"name": "A", "lat": 52.52, "lon": 13.405},
        {"name": "B", "lat": 52.5, "lon": 13.438},
        {"name": "C", "lat": 52.43, "lon": 13.64},
    ],
    "cycle": [["parked", 3], ["enter", 1], ["start", 1], ["drive", 8], ["stop", 1], ["leave", 1]],
    "fuel": {"pct_per_km": 0.1, "km_per_pct": 10},
    "electric": {
        "pct_per_km": 0.27,
        "km_per_pct": 5.2,
        "charge_below_pct": 40,
        "charge_step_pct": 9,
        "charge_limit_pct": 80,
        "charge_kw": 11,
    },
    "warnings": [{"code": "washer_fluid", "text": "Washer fluid low"}],
}
PLUGIN = {"id": "demo-connector", "kind": "plugin", "name": "Demo connector", "version": "1", "settings": [], "simulation": SCENARIO}


def _demo_zip(client, electric=False):
    """A demo car backup as the standard source offers it: the plugin is asked for (status missing), not part of the file."""
    vid = demo_car(client, electric)
    with db.tx() as conn:
        raw = vehiclebackup.export(conn, vid)
        conn.execute("DELETE FROM vehicles WHERE id = ?", (vid,))
    doc = json.loads(zipfile.ZipFile(io.BytesIO(raw)).read("vehicle.json"))
    doc["vehicle"]["name"] = "Demo Electric" if electric else "Demo Diesel"
    for entry in doc["addons"]:
        entry["source_url"] = sources.DEFAULT_URL
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("vehicle.json", json.dumps(doc))
    return out.getvalue()


@pytest.fixture()
def standard_source(client, monkeypatch):
    files = {
        "vehicles/index.json": json.dumps(
            {"vehicles": [{"id": "demo-diesel", "name": "Demo Diesel"}, {"id": "demo-electric", "name": "Demo Electric"}]}
        ).encode(),
        "vehicles/demo-diesel.zip": _demo_zip(client, False),
        "vehicles/demo-electric.zip": _demo_zip(client, True),
        "plugins/index.json": json.dumps({"packages": [{"id": "demo-connector", "name": "Demo connector", "version": "1"}]}).encode(),
        "plugins/demo-connector/plugin.json": json.dumps(PLUGIN).encode(),
    }

    def fake_http(url, headers, check_host, limit=0):
        for path, body in files.items():
            if url.endswith("/" + path):
                return body
        raise sources.SourceError("err.src_missing")

    monkeypatch.setattr(sources, "_http", fake_http)
    return files


def test_scenario_is_cleaned_and_bounded():
    assert (
        simulator.clean_scenario(None) is None and simulator.clean_scenario({"places": [{"name": "x", "lat": 1, "lon": 1}]}) is None
    )  # needs 2 places
    scn = simulator.clean_scenario({**SCENARIO, "interval_s": 9999, "timelapse": -5, "evil": "x", "cycle": [["fly", 3], ["drive", 2]]})
    assert scn["interval_s"] == 60 and scn["timelapse"] == 1 and "evil" not in scn and scn["cycle"] == [["drive", 2]]
    assert addons.parse_package(json.dumps(PLUGIN).encode())["simulation"]["interval_s"] == 5  # a manifest carries its scenario


def test_a_full_cycle_goes_through_the_normal_interface(client):
    vid = demo_car(client)
    with db.tx() as conn:
        token = connectors.create_token(conn, "Demo connector", vid)
    h = {"Authorization": f"Bearer {token}"}
    scn = simulator.clean_scenario(SCENARIO)
    km0 = None
    rnd = random.Random(1)
    phases = []
    for _ in range(sum(n for _, n in scn["cycle"])):
        with db.tx() as conn:
            if km0 is None:
                km0 = conn.execute("SELECT value FROM live WHERE vehicle_id = ? AND key = 'fuel_level'", (vid,)).fetchone()["value"]
            phase, data = simulator.step(conn, vid, scn, rnd)
        phases.append(phase)
        if data:  # exactly what a plugin does: POST with its token
            assert client.post(f"/api/v1/vehicles/{vid}/data", json=data, headers=h).status_code == 200, (phase, data)
    assert list(dict.fromkeys(phases)) == [p for p, _ in scn["cycle"]]
    with db.tx() as conn:
        live = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM live WHERE vehicle_id = ?", (vid,))}
    assert live["locked"] == "locked" and live["ignition"] == "off"
    assert client.get(f"/v/{vid}").text.count("data-live-poll") == 1  # a car with a connector refreshes itself


def test_an_electric_car_plugs_in_when_its_battery_is_low(client):
    vid = demo_car(client, electric=True)
    with db.tx() as conn:
        token = connectors.create_token(conn, "Demo connector", vid)
        conn.execute("UPDATE live SET value = '30' WHERE vehicle_id = ? AND key = 'fuel_level'", (vid,))
    h = {"Authorization": f"Bearer {token}"}
    scn = simulator.clean_scenario(SCENARIO)
    for _ in range(3):
        with db.tx() as conn:
            _, data = simulator.step(conn, vid, scn, random.Random(3))
        client.post(f"/api/v1/vehicles/{vid}/data", json=data, headers=h)
    with db.tx() as conn:
        seen = {
            k: conn.execute("SELECT value FROM live WHERE vehicle_id = ? AND key = ?", (vid, k)).fetchone()["value"]
            for k in ("plugged", "battery_pct")
        }
    assert seen["plugged"] == "no" and float(seen["battery_pct"]) > 30  # charged, then unplugged again
    assert "<span>Charging</span>" in client.get(f"/v/{vid}/e/fuel").text


def test_just_have_a_look_asks_first_then_loads_car_and_plugin_from_the_standard_source(client, standard_source):
    assert "/vehicles/demo" in client.get("/vehicles/new").text
    ask = client.post("/vehicles/demo", data={"kind": "combustion"})
    assert ask.status_code == 200 and "/vehicles/demo/load" in ask.text and "GitHub" in ask.text  # nothing went online yet
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0] == 0
    res = client.post("/vehicles/demo/load", data={"kind": "combustion"}, follow_redirects=False)
    assert res.status_code == 303 and "/v/demo-diesel" in res.headers["location"]
    with db.tx() as conn:
        vid = conn.execute("SELECT id FROM vehicles").fetchone()["id"]
        item = addons.list_for(conn, vid)[0]
        # the plugin came from the source, is switched on, and may be played - an uploaded copy of it never would be
        assert item["addon_id"] == "demo-connector" and item["source_id"] and item["active"] == 1 and simulator.is_playable(item)
        assert [p[0] for p in simulator.playing(conn)] == [vid]
        conn.execute("UPDATE vehicle_addons SET source_id = NULL WHERE id = ?", (item["id"],))
        assert simulator.playing(conn) == []  # not from a source: not played
        conn.execute("UPDATE vehicle_addons SET source_id = ? WHERE id = ?", (item["source_id"], item["id"]))


def test_start_stop_on_the_plugin_card_parks_the_car(client, standard_source):
    client.post("/vehicles/demo/load", data={"kind": "electric"})
    with db.tx() as conn:
        vid = conn.execute("SELECT id FROM vehicles").fetchone()["id"]
        row = addons.list_for(conn, vid)[0]
        scn = simulator.clean_scenario(row["m"]["simulation"])
        token = simulator._token(conn, vid, simulator.playing(conn)[0][1])  # the player's own token for this plugin
    h = {"Authorization": f"Bearer {token}"}
    with db.tx() as conn:
        _, data = simulator.step(conn, vid, scn)
    assert client.post(f"/api/v1/vehicles/{vid}/data", json=data or {"speed_kmh": 0}, headers=h).status_code == 200
    page = client.get(f"/v/{vid}/plugins").text
    assert (
        "Running" in page and f'/integrations/{row["id"]}/active" checked' in page
    )  # it runs: the state says so and the switch (on) stops it
    client.post(f"/v/{vid}/integrations/{row['id']}/active", data={})  # Stop
    with db.tx() as conn:
        assert simulator.playing(conn) == []
    assert client.post(f"/api/v1/vehicles/{vid}/data", json={"speed_kmh": 5}, headers=h).status_code == 401  # a stopped plugin is refused
    page = client.get(f"/v/{vid}/plugins").text
    assert (
        "Stopped" in page and f'/integrations/{row["id"]}/active" checked' not in page
    )  # stopped: the car stands still, the switch (off) starts it again
    client.post(f"/v/{vid}/integrations/{row['id']}/active", data={"active": "1"})  # Start
    assert client.post(f"/api/v1/vehicles/{vid}/data", json={"speed_kmh": 5}, headers=h).status_code == 200


def test_just_have_a_look_is_the_only_entry_for_the_demo_cars_and_needs_the_standard_source(client, standard_source):
    client.post("/sources/1/refresh", data={"kind": "plugin"})
    page = client.get("/vehicles/new").text
    assert "/vehicles/demo" in page and "/vehicles/from-source/" not in page  # one entry, not a second list with the same cars
    assert "Demo Electric" not in page
    # the standard source is removed: there is no connection, so the entry goes away and nothing is loaded
    for kind in ("plugin", "integration"):
        client.post("/sources/1/delete", data={"kind": kind})
    assert "/vehicles/demo" not in client.get("/vehicles/new").text
    assert "m=err.demo_missing" in client.post("/vehicles/demo/load", data={"kind": "electric"}, follow_redirects=False).headers["location"]
    with db.tx() as conn:
        assert (
            conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0] == 0
            and conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 0
        )


def test_a_car_offered_by_another_source_can_be_restored_from_the_add_page(client, standard_source):
    client.post("/sources", data={"kind": "plugin", "url": "https://github.com/example/own", "name": "Own"})
    page = client.get("/vehicles/new").text
    own = [p for p in ("Demo Electric", "Demo Diesel") if p in page]
    assert own and "/vehicles/from-source/" in page  # a car of another source is listed (the standard source's demo cars are not)
    with db.tx() as conn:
        sid = conn.execute("SELECT id FROM sources WHERE url = 'https://github.com/example/own'").fetchone()["id"]
    import re

    asked = client.post(f"/vehicles/from-source/{sid}/demo-electric", follow_redirects=False)
    assert (
        asked.status_code == 200 and "Fetch and set up the packages" in asked.text
    )  # the car had a plugin that is not installed here: asked
    token = re.search(r'name="token" value="([^"]+)"', asked.text).group(1)
    res = client.post(
        "/vehicles/restore/confirm", data={"token": token, "mode": "new"}, follow_redirects=False
    )  # (without the switch: data only)
    assert res.status_code == 303  # (the very first car of a fresh system goes on with the first-start guide)
    # the plugin is asked for (not installed by this way): off until the user installs and starts it
    with db.tx() as conn:
        vid = conn.execute("SELECT id FROM vehicles").fetchone()["id"]
        item = addons.list_for(conn, vid)[0]
    assert item["missing"] and item["active"] == 0


def test_the_backup_of_a_car_has_all_of_its_own_settings(client):
    from carassistant import appicon

    vid = demo_car(client)
    with db.tx() as conn:
        for key, value in (
            (f"home.widgets.{vid}", '["a"]'),
            (f"nav.slots.{vid}", "service,fuel"),
            (f"modules.off.{vid}", "tires"),
            (f"debug.{vid}", "1"),
        ):
            db.set_setting(conn, key, value)
    appicon.custom_path(vid).write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 20)
    with db.tx() as conn:
        raw = vehiclebackup.export(conn, vid)
        conn.execute("DELETE FROM vehicles WHERE id = ?", (vid,))
        appicon.custom_path(vid).unlink()
    with db.tx() as conn:
        new = vehiclebackup.restore(conn, raw)
        for prefix, value in (("home.widgets", '["a"]'), ("nav.slots", "service,fuel"), ("modules.off", "tires"), ("debug", "1")):
            assert db.get_setting(conn, f"{prefix}.{new}") == value, prefix
    assert appicon.custom_path(new).is_file()


def test_demo_cars_always_have_every_function_on(client):
    from carassistant import modules

    for electric in (False, True):
        vid = demo_car(client, electric=electric)
        with db.tx() as conn:
            assert modules.vehicle_off(conn, vid) == set()  # the recommended set is only for a car made on the page
