"""One interface, one plugin (carassistant/claims.py): a field a plugin has taken for a car is filled by that plugin only - everything else is ignored for that field and says so."""

import json

from tests.test_web import create_vehicle

from carassistant import addons, claims, connectors, db, live

HDR = lambda token: {"Authorization": f"Bearer {token}"}  # noqa: E731


def _plugin(vid, addon_id, name):
    """A plugin without a service on a car, with its token; returns (install, token)."""
    manifest = {"id": addon_id, "kind": "plugin", "name": name, "version": "1", "settings": []}
    with db.tx() as conn:
        source = conn.execute("SELECT id FROM sources LIMIT 1").fetchone()["id"]
        pk = addons.add(conn, vid, addons.parse_package(json.dumps(manifest).encode()), source, None)
        conn.execute("UPDATE vehicle_addons SET active = 1 WHERE id = ?", (pk,))
        return pk, addons.new_token(conn, vid, addons.get(conn, vid, pk))


def _live(vid):
    with db.tx() as conn:
        return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM live WHERE vehicle_id = ?", (vid,))}


def test_the_earliest_claim_of_a_plugin_that_is_on_holds_the_field(client):
    vid = create_vehicle(client)
    a, _ = _plugin(vid, "plugin-a", "Plugin A")
    b, _ = _plugin(vid, "plugin-b", "Plugin B")
    with db.tx() as conn:
        claims.register(conn, vid, a, ["odometer_km", "fuel_level_pct"])
        claims.register(conn, vid, b, ["fuel_level_pct", "range_km"])
        held = claims.owners(conn, vid)
        assert held["odometer_km"] == {"pk": a, "name": "Plugin A"} and held["fuel_level_pct"]["pk"] == a  # A was first
        assert held["range_km"]["pk"] == b
        assert claims.conflicts(conn, vid, b, ["fuel_level_pct", "range_km"]) == {"fuel_level_pct": "Plugin A"}
        assert claims.conflicts(conn, vid, a, ["fuel_level_pct"]) == {}  # its own field is no conflict
        claims.register(conn, vid, a, ["odometer_km"])  # A lets go of one: B holds it now
        assert claims.owners(conn, vid)["fuel_level_pct"]["pk"] == b
        conn.execute("UPDATE vehicle_addons SET active = 0 WHERE id = ?", (a,))  # a plugin that is off holds nothing
        assert "odometer_km" not in claims.owners(conn, vid)
        conn.execute("UPDATE vehicle_addons SET active = 1 WHERE id = ?", (a,))
        assert claims.owners(conn, vid)["odometer_km"]["pk"] == a  # ... and gets it back with it
        assert claims.held_by(conn, vid, b) == ["fuel_level_pct", "range_km"]


def test_a_value_of_another_plugin_for_a_taken_field_is_ignored_and_says_so(client):
    vid = create_vehicle(client)
    a, token_a = _plugin(vid, "plugin-a", "Plugin A")
    _b, token_b = _plugin(vid, "plugin-b", "Plugin B")
    with db.tx() as conn:
        claims.register(conn, vid, a, ["fuel_level_pct", "range_km"])
    url = f"/api/v1/vehicles/{vid}/data"
    got = client.post(
        url, headers=HDR(token_b), json={"fuel_level_pct": 40, "range_km": 300, "battery_pct": 80, "measured_at": "2026-11-26T08:00:00Z"}
    )
    assert got.status_code == 200
    result = got.json()["result"]
    assert (
        result["fuel_level_pct"] == "ignored (taken by Plugin A)"
        and result["range_km"] == "ignored (taken by Plugin A)"
        and result["battery_pct"] == "stored"
    )
    assert "fuel_level" not in _live(vid) and _live(vid)["battery_pct"] == "80"  # the free field was stored, the taken ones were not
    # everything is taken: nothing is stored, the answer still says what happened, and no error
    only = client.post(url, headers=HDR(token_b), json={"fuel_level_pct": 41, "measured_at": "2026-11-26T08:01:00Z"})
    assert only.status_code == 200 and only.json()["result"] == {"fuel_level_pct": "ignored (taken by Plugin A)"}
    # the holder fills them
    mine = client.post(url, headers=HDR(token_a), json={"fuel_level_pct": 55, "range_km": 410})
    assert mine.json()["result"] == {"fuel_level_pct": "stored", "range_km": "stored"} and _live(vid)["fuel_level"] == "55"
    # a plugin that is switched off takes nothing; one that is deleted leaves nothing behind
    with db.tx() as conn:
        conn.execute("UPDATE vehicle_addons SET active = 0 WHERE id = ?", (a,))
    assert client.post(url, headers=HDR(token_b), json={"fuel_level_pct": 30}).json()["result"] == {"fuel_level_pct": "stored"}
    with db.tx() as conn:
        conn.execute("UPDATE vehicle_addons SET active = 1 WHERE id = ?", (a,))
        addons.remove(conn, addons.get(conn, vid, a))
        assert conn.execute("SELECT COUNT(*) AS n FROM field_claims").fetchone()["n"] == 0


def test_the_bindings_of_the_vehicle_form_step_back_for_a_taken_interface(client, monkeypatch):
    vid = create_vehicle(client)
    a, _ = _plugin(vid, "plugin-a", "Plugin A")
    states = {"sensor.fuel": {"state": "61", "attributes": {}}, "sensor.range": {"state": "480", "attributes": {}}}
    monkeypatch.setattr(live.ha, "get_state", lambda entity: states.get(entity))
    with db.tx() as conn:
        conn.execute("UPDATE vehicles SET bind_fuel_level = 'sensor.fuel', bind_range = 'sensor.range' WHERE id = ?", (vid,))
        claims.register(conn, vid, a, ["fuel_level_pct"])
        live.refresh_vehicle(conn, conn.execute("SELECT * FROM vehicles WHERE id = ?", (vid,)).fetchone())
    assert _live(vid) == {"range_km": "480"}  # the range still comes from the binding, the fuel level belongs to the plugin
    with db.tx() as conn:
        claims.release(conn, a)
        live.refresh_vehicle(conn, conn.execute("SELECT * FROM vehicles WHERE id = ?", (vid,)).fetchone())
    assert _live(vid)["fuel_level"] == "61"


def test_the_guard_leaves_a_delivery_alone_when_nothing_is_taken(client):
    vid = create_vehicle(client)
    a, _ = _plugin(vid, "plugin-a", "Plugin A")
    data = {"fuel_level_pct": 40, "measured_at": "2026-11-26T08:00:00Z"}
    with db.tx() as conn:
        assert claims.guard(conn, vid, data, None) == (data, {})  # no claim at all: the same dict, nothing asked
        claims.register(conn, vid, a, ["range_km"])
        assert claims.guard(conn, vid, data, None) == (data, {})
        kept, refused = claims.guard(conn, vid, {"range_km": 1, "fuel_level_pct": 2, "measured_at": "x"}, None)
        assert kept == {"fuel_level_pct": 2, "measured_at": "x"} and refused == {"range_km": "Plugin A"}
        assert claims.guard(conn, vid, {"range_km": 1, "measured_at": "x"}, None) == (
            {},
            {"range_km": "Plugin A"},
        )  # the time alone is no delivery
    assert {"fuel_level_pct", "range_km", "odometer_km"} <= connectors.KNOWN
