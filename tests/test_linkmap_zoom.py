"""The zoomable connection map: every channel of the Plugin API is on it (also the open ones), what flows through the others, and the details."""

import html as htmllib
import json

import pytest
from fastapi.testclient import TestClient

from carassistant import connectors, db, linkmap, linkmap_zoom


@pytest.fixture()
def world(env):
    from carassistant import web

    client = TestClient(web.app, client=("172.30.32.2", 1), follow_redirects=False)  # inside Home Assistant: an administrator
    assert client.post("/vehicles", data={"name": "Zoom Car", "odometer": "100"}).status_code == 303
    linkmap._seen.clear()
    return client


def _plugin(conn, addon_id, name):
    conn.execute(
        "INSERT INTO vehicle_addons(vehicle_id, kind, addon_id, manifest, status, active, created_at) VALUES(1, 'plugin', ?, ?, 'configured', 1, datetime('now'))",
        (addon_id, json.dumps({"id": addon_id, "kind": "plugin", "name": name, "icon": "plug"})),
    )


def _call(conn, addon, method, path, data=None):
    return linkmap.record(conn, 1, addon, method, ["", "api", "v1", "vehicles", "1", *path.split("/")], data)


def test_every_field_and_every_interface_of_the_plugin_api_is_a_channel_also_when_nobody_uses_it(world):
    with db.tx() as conn:
        body = linkmap_zoom.model(conn, 1)
    keys = {c["key"] for g in body["groups"] for c in g["channels"]}
    assert (connectors.KNOWN - {"measured_at"}) <= keys  # every data field a plugin may send
    assert set(linkmap_zoom.INTERFACES) <= keys
    assert body["n_used"] == 0 and body["n_open"] == len(keys)  # nothing is connected: everything is open
    assert all(c["state"] == "open" and not c["users"] for g in body["groups"] for c in g["channels"])
    assert all(c["label"] and c["explain"] for g in body["groups"] for c in g["channels"])


def test_the_catalogue_knows_every_interface_the_app_notes_and_names_every_field():
    """A new endpoint or field must not be forgotten on the map: what linkmap.entries() records has a channel, and every field has its label."""
    for what in ("data", "signals", "track", "trip-summary", "refuel", "events", "logs", "plugin-settings", "control"):
        parts = ["", "api", "v1", "vehicles", "1", what]
        for method in ("GET", "POST"):
            for _direction, name, area, _value in linkmap.entries(method, parts, {"signals": {"x": 1}}):
                assert linkmap_zoom.channel_of(area, name) in linkmap_zoom.INTERFACES, (what, method, name)
    assert [k for k in connectors.KNOWN - {"measured_at"} if k not in linkmap_zoom.FIELDS] == []


def test_a_channel_in_use_shows_who_uses_it_how_and_when_and_the_others_stay_open(world):
    with db.tx() as conn:
        _plugin(conn, "p-one", "Plugin One")
        _plugin(conn, "p-two", "Plugin Two")
        _call(conn, "p-one", "POST", "data", {"odometer_km": 86020, "doors": {"fl": "open"}})
        _call(conn, "p-one", "GET", "control")
        _call(conn, "p-two", "POST", "data", {"odometer_km": 86100})
        _call(conn, "p-two", "POST", "signals", {"signals": {"a": 1, "b": 2}})
        body = linkmap_zoom.model(conn, 1)
    by_key = {c["key"]: c for g in body["groups"] for c in g["channels"]}
    odo = by_key["odometer_km"]
    assert odo["state"] == "live" and sorted(u["plugin"] for u in odo["users"]) == ["p-one", "p-two"] and odo["hits"] == 2
    assert by_key["control"]["users"][0]["dir"] == "get"
    assert by_key["signals.*"]["users"][0]["plugin"] == "p-two"  # the free signals are one channel
    assert by_key["vin"]["state"] == "open"  # nobody sends the VIN
    assert {(e["plugin"], e["channel"], e["dir"]) for e in body["edges"]} >= {
        ("p-one", "odometer_km", "set"),
        ("p-two", "odometer_km", "set"),
        ("p-one", "control", "get"),
    }
    assert body["n_used"] == 4 and body["n_open"] == len(by_key) - 4  # odometer, doors, control, the free signals
    assert linkmap_zoom.light(body)["version"] == body["version"] and body["icons"]


def test_the_details_show_connections_data_raw_values_and_a_history_with_dates_to_those_who_may_see_them(world):
    with db.tx() as conn:
        _plugin(conn, "p-one", "Plugin One")
        for km in (86020, 86031, 86044):
            linkmap._seen.clear()
            _call(conn, "p-one", "POST", "data", {"odometer_km": km})
    d = world.get("/v/1/plugins/connections/detail.json?kind=channel&id=odometer_km").json()
    assert d["title"] == "Odometer" and "SENDS" in " ".join(d["extra"]) and d["raw"] is True
    assert d["connections"][0]["plugin_name"] == "Plugin One" and d["connections"][0]["when"]
    sig = d["signals"][0]
    assert (
        sig["value"] == "86044"
        and [h["value"] for h in sig["history"]] == ["86044", "86031", "86020"]
        and all(h["when"] for h in sig["history"])
    )
    plugin = world.get("/v/1/plugins/connections/detail.json?kind=plugin&id=p-one").json()
    assert plugin["title"] == "Plugin One" and plugin["signals"]
    group = world.get("/v/1/plugins/connections/detail.json?kind=group&id=dashboard").json()
    assert group["title"] and group["connections"] and "open" in " ".join(group["extra"])
    open_one = world.get("/v/1/plugins/connections/detail.json?kind=channel&id=vin").json()
    assert open_one["signals"] == [] and "OPEN" in " ".join(open_one["extra"])
    assert world.get("/v/1/plugins/connections/detail.json?kind=nonsense&id=x").status_code == 400


def test_the_page_carries_the_zoom_map_with_every_channel_and_phones_keep_the_cards(world):
    with db.tx() as conn:
        _plugin(conn, "p-one", "Plugin <b>One</b>")
        _call(conn, "p-one", "POST", "data", {"ignition": True})
    page = world.get("/v/1/plugins/connections").text
    assert 'id="lmz"' in page and "linkmap_zoom.js" in page and 'id="lm"' in page  # the zoomable map and the cards of the phone
    raw = page.split("data-model='", 1)[1].split("' data-base", 1)[0]
    model = json.loads(htmllib.unescape(raw))
    assert sum(len(g["channels"]) for g in model["groups"]) >= 50 and model["n_used"] == 1
    assert (
        "Plugin <b>One</b>" not in page and "Plugin &lt;b&gt;One&lt;/b&gt;" not in raw.replace("\\u003c", "&lt;")
    ) or "\\u003cb\\u003e" in raw  # never as markup
    assert world.get("/static/linkmap_zoom.js").status_code == 200
    assert world.get("/v/1/plugins/connections/zoom.json").json()["version"] == model["version"]


def test_the_pages_of_an_integration_are_channels_in_a_group_of_their_own(world):
    with db.tx() as conn:
        _plugin(conn, "p-one", "Plugin One")
        conn.execute(
            "INSERT INTO vehicle_addons(vehicle_id, kind, addon_id, manifest, status, active, created_at) VALUES(1, 'integration', 'my-int', ?, 'configured', 1, datetime('now'))",
            (
                json.dumps(
                    {
                        "id": "my-int",
                        "kind": "integration",
                        "name": "My Integration",
                        "pages": [{"id": "entries", "title": "Entries", "fields": []}, {"id": "other", "title": "Other", "fields": []}],
                    }
                ),
            ),
        )
        _call(conn, "p-one", "POST", "modules/my-int/entries", {"rows": [{"a": 1}]})
        body = linkmap_zoom.model(conn, 1)
    group = next(g for g in body["groups"] if g["area"] == "int:my-int")
    assert group["name"] == "My Integration" and group["integration"] is True
    by_key = {c["key"]: c for c in group["channels"]}
    assert (
        by_key["int:my-int/entries"]["state"] == "live" and by_key["int:my-int/other"]["state"] == "open"
    )  # one page is used, the other is open
    d = world.get("/v/1/plugins/connections/detail.json?kind=group&id=int:my-int").json()
    assert d["title"] == "My Integration" and d["connections"][0]["channel_label"] == "Entries" and d["signals"][0]["name"] == "entries"
