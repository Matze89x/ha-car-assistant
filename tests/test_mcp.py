"""MCP access: off by default, only with https + port + a user, own keys with levels, no way in through the panel, a log of every call."""

import re

import pytest
from fastapi.testclient import TestClient

PW = "correct horse battery"


@pytest.fixture()
def ing(env, monkeypatch):
    """The Home Assistant panel (ingress): no login, used here to set things up."""
    monkeypatch.delenv("CARASSISTANT_DEV", raising=False)
    from carassistant import web

    return TestClient(web.app, client=("172.30.32.2", 5000), follow_redirects=False)


def make_admin(ing):
    assert ing.post("/account/create", data={"username": "admin", "password": PW, "password2": PW}).status_code == 303


@pytest.fixture()
def program(env, monkeypatch):
    """A program (not a browser) calling the endpoint from outside."""
    monkeypatch.delenv("CARASSISTANT_DEV", raising=False)
    from carassistant import web

    return TestClient(web.app, base_url="https://car.example.com", client=("203.0.113.7", 5000), follow_redirects=False)


def _ready(ing, monkeypatch, level="write"):
    from carassistant import ha, mcp

    mcp._calls.clear()
    mcp._fails.clear()
    mcp._blocked.clear()
    make_admin(ing)
    monkeypatch.setattr(ha, "network_port", lambda: (True, 8321))
    assert ing.post("/settings/external-url", data={"host": "car.example.com"}).status_code == 303
    assert ing.post("/settings/mcp/level", data={"level": level, "path_key": "1"}).status_code == 303


def _key(ing, *_ignored):
    """The one access key (made, or renewed when there is one)."""
    r = ing.post("/settings/mcp/key")
    assert r.status_code == 200
    return re.search(r"cam_[A-Za-z0-9_\-]+", r.text).group(0)


def rpc(program, key, method, params=None, msg_id=1, **kw):
    body = {"jsonrpc": "2.0", "method": method}
    if msg_id is not None:
        body["id"] = msg_id
    if params is not None:
        body["params"] = params
    return program.post("/mcp", json=body, headers={"Authorization": f"Bearer {key}"}, **kw)


def call(program, key, name, **arguments):
    answer = rpc(program, key, "tools/call", {"name": name, "arguments": arguments}).json()["result"]
    import json

    return answer["isError"], json.loads(answer["content"][0]["text"])


def test_it_is_off_and_invisible_by_default(program):
    assert program.post("/mcp", json={}).status_code == 404
    assert program.get("/mcp").status_code == 404


def test_it_cannot_be_switched_on_without_https_a_port_and_a_user(ing, monkeypatch):
    from carassistant import db, ha, mcp

    r = ing.post("/settings/mcp/level", data={"level": "read", "path_key": "1"})
    assert (r.status_code == 303 and "mcp.need_user" in r.headers["location"]) or "m=" in r.headers["location"]
    make_admin(ing)
    with db.tx() as conn:
        assert mcp.level(conn) == "off" and mcp.missing(conn) == ["mcp.need_https", "mcp.need_port"]
    ing.post("/settings/external-url", data={"host": "car.example.com"})
    ing.post("/settings/mcp/level", data={"level": "read", "path_key": "1"})
    with db.tx() as conn:
        assert mcp.level(conn) == "off"  # still no port
    monkeypatch.setattr(ha, "network_port", lambda: (True, 8321))
    ing.post("/settings/mcp/level", data={"level": "read", "path_key": "1"})
    with db.tx() as conn:
        assert mcp.level(conn) == "read"


def test_the_whole_conversation_of_a_client(ing, program, monkeypatch):
    _ready(ing, monkeypatch, "write")
    key = _key(ing)
    hello = rpc(
        program, key, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}
    ).json()
    assert hello["result"]["protocolVersion"] == "2025-06-18" and "tools" in hello["result"]["capabilities"]
    assert rpc(program, key, "notifications/initialized", msg_id=None).status_code == 202  # a notification: no answer
    assert rpc(program, key, "ping").json()["result"] == {}
    names = {t["name"] for t in rpc(program, key, "tools/list").json()["result"]["tools"]}
    assert {
        "app_info",
        "list_vehicles",
        "get_vehicle",
        "list_entries",
        "get_costs",
        "get_logs",
        "add_entry",
        "update_entry",
        "delete_entry",
        "list_plugins",
        "list_documents",
        "get_charging",
        "get_tyres",
        "get_settings",
    } <= names
    for tool in ("list_plugins", "get_settings"):
        error, data = call(program, key, tool)
        assert not error and data is not None
    assert rpc(program, key, "nonsense").json()["error"]["code"] == -32601
    error, info = call(program, key, "app_info")
    assert not error and info["app"] == "Car Assistant" and "stage" in info
    batch = program.post(
        "/mcp",
        json=[{"jsonrpc": "2.0", "id": 1, "method": "ping"}, {"jsonrpc": "2.0", "id": 2, "method": "ping"}],
        headers={"Authorization": f"Bearer {key}"},
    )
    assert [a["id"] for a in batch.json()] == [1, 2]


def test_a_key_needs_to_be_right_and_wrong_ones_get_blocked(ing, program, monkeypatch):
    from carassistant import mcp

    _ready(ing, monkeypatch, "read")
    assert program.post("/mcp", json={}).status_code == 401
    assert rpc(program, "cam_wrong", "ping").status_code == 401
    monkeypatch.setattr(mcp, "FAIL_LIMIT", 3)
    monkeypatch.setattr("asyncio.sleep", lambda _s: _noop())
    for _ in range(3):
        rpc(program, "cam_wrong", "ping")
    assert rpc(program, "cam_wrong", "ping").status_code == 429  # the address is blocked for a while


async def _noop():
    return None


def test_the_key_is_stored_only_as_a_hash_and_listed_without_it(ing, monkeypatch):
    from carassistant import db

    _ready(ing, monkeypatch, "read")
    key = _key(ing)
    with db.tx() as conn:
        row = conn.execute("SELECT * FROM mcp_keys").fetchone()
        assert key not in " ".join(str(v) for v in tuple(row)) and row["prefix"] == key[:8]
    page = ing.get("/settings/system").text
    assert key not in page and key[:8] in page  # only the start of the key is shown
    assert (
        'action="/settings/mcp/level" class="acct-form">' in page and "data-live" not in page.split('id="mcp"')[1].split("</form>")[0]
    )  # the level has its own Save


def test_one_switch_decides_read_or_write_for_the_key(ing, program, monkeypatch):
    from carassistant import db

    _ready(ing, monkeypatch, "read")
    with db.tx() as conn:
        vid = conn.execute("INSERT INTO vehicles(name, slug, fuel_type) VALUES('Test Car', 'test-car', 'petrol')").lastrowid
    key = _key(ing)
    read_tools = {t["name"] for t in rpc(program, key, "tools/list").json()["result"]["tools"]}
    assert "add_entry" not in read_tools and "list_entries" in read_tools
    error, answer = call(program, key, "add_entry", vehicle="test-car", kind="service", values={"date": "2026-11-20", "title": "Oil"})
    assert error and "read access" in answer["error"]
    assert (
        ing.post("/settings/mcp/level", data={"level": "write", "path_key": "1"}).status_code == 303
    )  # the same key, now with write access
    assert "add_entry" in {t["name"] for t in rpc(program, key, "tools/list").json()["result"]["tools"]}
    error, answer = call(
        program, key, "add_entry", vehicle="test-car", kind="service", values={"date": "2026-11-20", "title": "Oil", "cost": 120}
    )
    assert not error and answer["ok"]
    _error, listed = call(program, key, "list_entries", vehicle="test-car", kind="service")
    assert listed["total"] == 1 and listed["rows"][0]["title"] == "Oil" and listed["rows"][0]["cost"] == 120
    entry = listed["rows"][0]["id"]
    error, _ = call(program, key, "update_entry", vehicle="test-car", kind="service", id=entry, values={"cost": 99.5})
    row = call(program, key, "list_entries", vehicle="test-car", kind="service")[1]["rows"][0]
    assert not error and row["cost"] == 99.5 and row["title"] == "Oil"  # untouched fields stay
    error, answer = call(program, key, "add_entry", vehicle="test-car", kind="service", values={"title": "No date"})
    assert error and "Invalid value" in answer["error"]
    assert call(program, key, "delete_entry", vehicle="test-car", kind="service", id=entry)[1]["ok"]
    assert call(program, key, "list_entries", vehicle="test-car", kind="service")[1]["total"] == 0
    assert call(program, key, "get_vehicle", vehicle=str(vid))[1]["vehicle"]["name"] == "Test Car"
    assert (
        ing.post("/settings/mcp/level", data={"level": "read", "path_key": "1"}).status_code == 303
    )  # switched back: writing is refused again
    error, _ = call(program, key, "add_entry", vehicle="test-car", kind="service", values={"date": "2026-11-20", "title": "x"})
    assert error


def test_renewing_replaces_the_key_and_deleting_removes_it(ing, program, monkeypatch):
    from carassistant import db

    _ready(ing, monkeypatch, "read")
    old = _key(ing)
    assert rpc(program, old, "ping").status_code == 200
    new = _key(ing)  # renewed: the old key is gone at once
    assert new != old and rpc(program, old, "ping").status_code == 401 and rpc(program, new, "ping").status_code == 200
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM mcp_keys").fetchone()[0] == 1
    page = ing.get("/settings/system").text.split('id="mcp"')[1]
    assert 'action="/settings/mcp/key"' in page and "data-confirm" in page and new[:8] in page
    assert ing.post("/settings/mcp/key/delete").status_code == 303 and rpc(program, new, "ping").status_code == 401


def test_it_is_not_reachable_through_the_panel_a_foreign_site_or_when_the_requirements_go(ing, program, monkeypatch):
    from carassistant import ha

    _ready(ing, monkeypatch, "read")
    key = _key(ing, "read")
    assert rpc(program, key, "ping").status_code == 200
    assert (
        program.post("/mcp", json={}, headers={"Authorization": f"Bearer {key}", "X-Ingress-Path": "/api/hassio_ingress/x"}).status_code
        == 404
    )
    assert (
        program.post("/mcp", json={}, headers={"Authorization": f"Bearer {key}", "Origin": "https://evil.example.org"}).status_code == 403
    )
    monkeypatch.setattr(ha, "network_port", lambda: (True, None))  # the port is closed again
    assert rpc(program, key, "ping").status_code == 404


def test_every_call_is_logged_and_the_rate_is_limited(ing, program, monkeypatch):
    from carassistant import db, mcp

    _ready(ing, monkeypatch, "read")
    key = _key(ing)
    call(program, key, "app_info")
    call(program, key, "get_vehicle", vehicle="nope")
    with db.tx() as conn:
        rows = conn.execute("SELECT key_name, tool, ok FROM mcp_log ORDER BY id").fetchall()
    assert [(r["key_name"], r["tool"], r["ok"]) for r in rows] == [("Claude", "app_info", 1), ("Claude", "get_vehicle", 0)]
    monkeypatch.setattr(mcp, "RATE_PER_MINUTE", 2)
    mcp._calls.clear()
    assert rpc(program, key, "ping").status_code == 200 and rpc(program, key, "ping").status_code == 200
    assert rpc(program, key, "ping").status_code == 429


def test_data_gaps_show_what_is_missing_and_the_oauth_lookup_gets_a_plain_404(ing, program, monkeypatch):
    from carassistant import db

    _ready(ing, monkeypatch, "read")
    key = _key(ing, "read")
    with db.tx() as conn:
        vid = conn.execute("INSERT INTO vehicles(name, slug, fuel_type, vin) VALUES('Gap Car', 'gap-car', 'petrol', 'WXYZ')").lastrowid
        conn.execute("INSERT INTO fuel(vehicle_id, date, amount) VALUES(?, '2026-11-01', 40)", (vid,))  # no odometer, no price
        conn.execute(
            "INSERT INTO service(vehicle_id, date, title, cost, odometer_km) VALUES(?, '2026-10-01', 'Oil', 100, 5000)", (vid,)
        )  # complete
        conn.execute("INSERT INTO tasks(vehicle_id, title, interval_months) VALUES(?, 'Brake fluid', 24)", (vid,))
    error, gaps = call(program, key, "data_gaps", vehicle="gap-car")
    assert not error and "vin" not in gaps["vehicle"] and "first_reg" in gaps["vehicle"] and "tank_l" in gaps["vehicle"]
    assert gaps["fuel"]["count"] == 1 and gaps["fuel"]["examples"][0]["missing"] == ["odometer_km", "price_total"]
    assert gaps["service"]["count"] == 0 and gaps["tasks"]["examples"][0]["title"] == "Brake fluid"
    well = program.get("/.well-known/oauth-authorization-server")
    assert well.status_code == 404 and well.json() == {"error": "not_found"}  # not a redirect to the sign-in page


def test_the_key_page_lists_every_value_to_paste_and_the_key_can_also_sit_in_the_address(ing, program, monkeypatch):
    _ready(ing, monkeypatch, "read")
    r = ing.post("/settings/mcp/key")
    key = re.search(r"cam_[A-Za-z0-9_\-]+", r.text).group(0)
    assert r.text.count('data-copy="') >= 6 and f'data-copy="Bearer {key}"' in r.text and 'data-copy="Authorization"' in r.text
    assert f'data-copy="https://car.example.com/mcp/{key}"' in r.text and "claude mcp add" in r.text
    ping = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
    assert program.post(f"/mcp/{key}", json=ping).json()["result"] == {}  # for a connector dialog without a header field
    assert program.post("/mcp/cam_wrong", json=ping).status_code == 401


def test_values_to_copy_are_read_only_fields_with_a_copy_button_and_the_web_app_link_uses_the_own_address(ing, monkeypatch):
    _ready(ing, monkeypatch, "read")
    page = ing.post("/settings/mcp/key").text
    assert page.count("<input readonly data-select") >= 5 and "data-copy=" in page  # fields, not text that cannot be taken
    from tests.test_web import create_vehicle, slug

    car = slug(create_vehicle(ing, "Copy Car"))
    user = ing.get("/settings/user", headers={"X-Ingress-Path": "/api/hassio_ingress/tok"}).text
    assert f'value="https://car.example.com/app/{car}"' in user  # the own address - never the Home Assistant panel path
    assert "hassio_ingress" not in user.split('id="webapp"')[1].split("</section>")[0].split("<input readonly")[1].split(">")[0]


def test_the_key_in_the_address_can_be_switched_off_and_is_never_in_our_own_log(ing, program, monkeypatch):
    _ready(ing, monkeypatch, "read")
    key = _key(ing)
    ping = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
    assert program.post(f"/mcp/{key}", json=ping).status_code == 200  # on by default: the simplest way
    off = ing.post("/settings/mcp/level", data={"level": "read"})  # saving without the box switches it off
    assert off.status_code == 303
    assert program.post(f"/mcp/{key}", json=ping).status_code == 404  # this address does not exist any more ...
    assert rpc(program, key, "ping").status_code == 200  # ... the header still works
    page = ing.post("/settings/mcp/key").text
    assert "/mcp/cam_" not in page and 'data-copy="Authorization"' in page  # the key page shows the header way only
    ing.post("/settings/mcp/level", data={"level": "read", "path_key": "1"})
    from pathlib import Path

    from carassistant import __main__ as entry

    assert "access_log=False" in Path(entry.__file__).read_text()  # the server writes no access log: the key never shows in our own log
