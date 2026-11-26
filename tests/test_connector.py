"""Connectors without code (``connector`` in a plugin.json, carassistant/connector.py): the manifest check, the paths and the map, a whole run against a made-up
service, the schedule (and the slowing down of a connector that fails), and the limits that keep it safe."""

import json

import pytest
from tests.test_web import create_vehicle

from carassistant import addons, connector, connectors, db, i18n, interfaces, oauth

TYPES = {"token": "password", "user": "text", "pass": "password", "car": "text", "region": "select"}
SPEC = {
    "every": 300,
    "requests": [
        {
            "id": "car",
            "url": "https://api.example.com/v1/cars/{setting.car}/status?lang=en",
            "headers": {"X-Region": "{setting.region}"},
            "auth": "bearer:token",
        }
    ],
    "map": [
        {"field": "odometer_km", "from": "car", "path": "data.odometer.km"},
        {"field": "fuel_level_pct", "from": "car", "path": "data.fuel.ratio", "scale": 100},
        {"field": "charging", "from": "car", "path": "data.charge.state", "values": {"CHARGING": True, "IDLE": False}},
        {"field": "position", "from": "car", "lat": "data.pos.lat", "lon": "data.pos.lon"},
    ],
}


def test_the_manifest_of_a_connector_is_checked():
    good, why = addons.clean_connector(SPEC, TYPES)
    assert why == "" and good["every"] == 300 and good["requests"][0]["auth"] == "bearer:token" and len(good["map"]) == 4
    assert good["map"][1]["scale"] == 100 and good["map"][2]["values"] == {"CHARGING": True, "IDLE": False}

    def bad(**change):
        spec = json.loads(json.dumps(SPEC))
        for key, value in change.items():
            if key == "url":
                spec["requests"][0]["url"] = value
            elif key == "auth":
                spec["requests"][0]["auth"] = value
            elif key == "headers":
                spec["requests"][0]["headers"] = value
            else:
                spec[key] = value
        return addons.clean_connector(spec, TYPES)[0]

    for change in (
        {"url": "http://api.example.com/x"},  # not https
        {"url": "https://{setting.car}.example.com/x"},  # the host is never filled in from a setting
        {"url": "https://127.0.0.1/x"},
        {"url": "https://api.example.com/{setting.nothing}"},  # a setting that does not exist
        {"url": "https://api.example.com/{setting.token}"},  # a password never goes into an address
        {"url": "https://api.example.com/{other}"},
        {"url": "https://user:pw@api.example.com/x"},
        {"headers": {"Authorization": "x"}},  # the app sets that itself, by ``auth``
        {"headers": {"Host": "evil.example.com"}},
        {"headers": {"X-A": "{setting.nothing}"}},
        {"auth": "bearer:nothing"},
        {"auth": "basic:user:car"},  # the second must be a password setting
        {"auth": "header:Host:token"},
        {"auth": "magic"},
        {"requests": []},
        {"map": []},
        {"map": [{"field": "not_a_field", "from": "car", "path": "a.b"}]},
        {"map": [{"field": "odometer_km", "from": "nothing", "path": "a.b"}]},
        {"map": [{"field": "odometer_km", "from": "car", "path": "a b"}]},
        {"map": [{"field": "position", "from": "car", "path": "a.b"}]},  # a position needs lat and lon
    ):
        assert bad(**change) is None, change
    assert (
        addons.clean_connector({**SPEC, "every": 5}, TYPES)[0]["every"] == 60
        and addons.clean_connector({**SPEC, "every": 10**9}, TYPES)[0]["every"] == 86400
    )
    assert addons.clean_connector({k: v for k, v in SPEC.items() if k != "every"}, TYPES)[0]["every"] == 300
    twice = {**SPEC, "requests": [*SPEC["requests"], SPEC["requests"][0]]}
    assert addons.clean_connector(twice, TYPES)[0] is None  # the same id twice


def _package(**extra):
    return {
        "id": "conn-demo",
        "kind": "plugin",
        "name": "Connector demo",
        "version": "1",
        "settings": [
            {"key": "token", "type": "password", "label": "Token"},
            {"key": "user", "type": "text", "label": "User"},
            {"key": "pass", "type": "password", "label": "Password"},
            {"key": "car", "type": "text", "label": "Car"},
            {"key": "region", "type": "select", "label": "Region", "options": [{"value": "eu", "label": "EU"}], "default": "eu"},
        ],
        "connector": SPEC,
        **extra,
    }


def test_a_package_keeps_its_connector_only_without_a_service_and_needs_no_token():
    kept = addons.parse_package(json.dumps(_package()).encode())
    assert (
        kept["connector"]["requests"][0]["id"] == "car" and addons.needs_token(kept) is False
    )  # nobody calls the Plugin API: the app delivers
    service = {"entry": "service/main.py", "python": ">=3.9", "requirements": [], "routes": [{"prefix": "/svc/", "public": False}]}
    assert "connector" not in addons.parse_package(json.dumps(_package(service=service)).encode())  # a service is a program of its own
    assert "connector" not in addons.parse_package(json.dumps(_package(kind="integration")).encode())
    assert "connector" not in addons.parse_package(
        json.dumps(_package(connector={"requests": []})).encode()
    )  # unusable: dropped, the package stays
    rows = interfaces.preview(kept, i18n.translator("en"))["rows"]["sends"]
    row = next(r for r in rows if "Reads api.example.com every 5 min" in r["name"])
    assert row["fields"] == ["charging", "fuel_level_pct", "odometer_km", "position"] and "nothing of the package is run" in row["note"]


def test_a_path_walks_through_the_answer():
    doc = {"data": {"items": [{"v": 1}, {"v": [7, 8]}], "x-y": {"a_b": 3}}, "list": [[1, 2]]}
    assert (
        connector.walk(doc, "data.items[1].v[0]") == 7
        and connector.walk(doc, "data.x-y.a_b") == 3
        and connector.walk(doc, "list[0][1]") == 2
    )
    for path in ("data.nothing", "data.items[5]", "data.items.v", "list.x", "data.items[0].v.deeper"):
        with pytest.raises(KeyError):
            connector.walk(doc, path)


def test_the_map_picks_values_and_skips_only_what_does_not_fit():
    spec, _ = addons.clean_connector(
        {
            **SPEC,
            "map": [
                *SPEC["map"],
                {"field": "locked", "from": "car", "path": "data.locked"},
                {"field": "ignition", "from": "car", "path": "data.ign"},
                {"field": "vin", "from": "car", "path": "data.vin"},
                {"field": "range_km", "from": "car", "path": "data.nothing"},
                {"field": "battery_pct", "from": "car", "path": "data.bat", "offset": 1},
                {"field": "measured_at", "from": "car", "path": "data.at"},
            ],
        },
        TYPES,
    )
    answer = {
        "data": {
            "odometer": {"km": "12345.5"},
            "fuel": {"ratio": 0.5},
            "charge": {"state": "CHARGING"},
            "pos": {"lat": 52.5, "lon": 13.4},
            "locked": "yes",
            "ign": "maybe",  # not a yes / no: skipped
            "vin": "WAUZZZ1234567890",
            "bat": "40",
            "at": "2026-11-20T08:15:00Z",
        }
    }
    data, skipped = connector.build(spec, {"car": answer})
    assert data == {
        "odometer_km": 12345.5,
        "fuel_level_pct": 50.0,
        "charging": True,
        "position": {"lat": 52.5, "lon": 13.4},
        "locked": True,
        "vin": "WAUZZZ1234567890",
        "battery_pct": 41.0,
        "measured_at": "2026-11-20T08:15:00Z",
    }
    assert sorted(s.split(":")[0] for s in skipped) == ["ignition", "range_km"]  # only those two were left out, and the notes say why


class Service:
    """A made-up web service: answers what a test lets it, and notes every request."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.answer = (
            200,
            json.dumps(
                {
                    "data": {
                        "odometer": {"km": 60000},
                        "fuel": {"ratio": 0.5},
                        "charge": {"state": "IDLE"},
                        "pos": {"lat": 52.5, "lon": 13.4},
                    }
                }
            ).encode(),
        )

    def get(self, url, headers):
        self.calls.append((url, headers))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


@pytest.fixture()
def service(monkeypatch):
    fake = Service()
    monkeypatch.setattr(connector, "_send_get", fake.get)
    monkeypatch.setattr(connector, "_public_host", lambda host: True)
    connector._state.clear()
    return fake


def _install(client, spec=None, settings=None, active=True, status="configured", package=None):
    vid = create_vehicle(client)
    manifest = _package(**({"connector": spec} if spec else {}), **(package or {}))
    with db.tx() as conn:
        source = conn.execute("SELECT id FROM sources LIMIT 1").fetchone()["id"]
        m = addons.parse_package(json.dumps(manifest).encode())
        pk = addons.add(conn, vid, m, source, None)
        values = {"token": "tok-123", "car": "my car/1", "region": "eu", **(settings or {})}
        conn.execute(
            "UPDATE vehicle_addons SET active = ?, status = ?, settings = ? WHERE id = ?",
            (1 if active else 0, status, json.dumps(addons._sealed(m, values)), pk),
        )
    return vid, pk


def _live(vid):
    with db.tx() as conn:
        return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM live WHERE vehicle_id = ?", (vid,))}


def _log(vid):
    with db.tx() as conn:
        return [
            (r["level"], r["source"], r["message"])
            for r in conn.execute("SELECT level, source, message FROM vehicle_logs WHERE vehicle_id = ? ORDER BY id", (vid,))
        ]


def test_a_run_fetches_the_address_with_the_settings_and_stores_what_the_map_finds(client, service):
    vid, _pk = _install(client)
    assert connector.tick(now=1000.0) == 1
    url, headers = service.calls[0]
    assert url == "https://api.example.com/v1/cars/my%20car%2F1/status?lang=en"  # a setting fills the path - quoted, it cannot add a slash
    assert headers["Authorization"] == "Bearer tok-123" and headers["X-Region"] == "eu" and headers["Accept"] == "application/json"
    live = _live(vid)
    assert live["fuel_level"] == "50" and live["position"] == "52.500000,13.400000" and live["charging"] == "no"
    with db.tx() as conn:
        last = conn.execute("SELECT odometer_km, source FROM odometer WHERE vehicle_id = ? ORDER BY id DESC", (vid,)).fetchone()
        assert (last["odometer_km"], last["source"]) == (60000, "api:Connector demo")  # entered like the reading of any plugin
        used = conn.execute("SELECT fields FROM plugin_usage WHERE vehicle_id = ? AND addon_id = 'conn-demo'", (vid,)).fetchone()
    assert "odometer_km" in used["fields"]  # it shows on the connection map like any plugin that sends
    assert connector.tick(now=1100.0) == 0  # not due yet: every 300 seconds
    assert connector.tick(now=1301.0) == 1 and len(service.calls) == 2
    assert _log(vid) == []  # a quiet success writes nothing (debug is off)


def test_a_failing_connector_says_why_slows_down_and_says_when_it_works_again(client, service):
    vid, pk = _install(client)
    service.answer = (500, b"oops")
    assert connector.tick(now=0.0) == 1
    assert _log(vid)[-1][0] == "warn" and "the service answered 500" in _log(vid)[-1][2] and "next in 300 s" in _log(vid)[-1][2]
    assert connector.tick(now=299.0) == 0 and connector.tick(now=301.0) == 1  # the second failure waits twice as long
    assert "next in 600 s" in _log(vid)[-1][2]
    service.answer = (200, b"not json")
    assert connector.tick(now=902.0) == 1 and "the answer is not JSON" in _log(vid)[-1][2]
    service.answer = (200, json.dumps({"data": {}}).encode())
    connector.tick(now=3000.0)
    assert "nothing in the answer matched the map" in _log(vid)[-1][2]
    service.answer = connector.ConnectorError("the service could not be reached")
    connector.tick(now=10000.0)
    assert _log(vid)[-1][0] == "error" and "could not be reached" in _log(vid)[-1][2]  # five in a row: an error, not a warning
    assert "next in 3600 s" in _log(vid)[-1][2] or "next in 4800 s" not in _log(vid)[-1][2]
    service.answer = (200, json.dumps({"data": {"odometer": {"km": 13000}}}).encode())
    connector.tick(now=100000.0)
    assert _log(vid)[-1][0] == "info" and _log(vid)[-1][2].startswith("works again")
    assert connector._state[pk]["fails"] == 0


def test_a_connector_runs_only_for_a_plugin_that_is_on_and_set_up(client, service):
    _install(client, active=False)
    assert connector.tick(now=0.0) == 0  # switched off
    _install(client, status="uploaded")
    assert connector.tick(now=0.0) == 0  # not set up yet
    assert service.calls == []
    _vid, pk = _install(client)
    assert connector.tick(now=0.0) == 1
    with db.tx() as conn:
        conn.execute("UPDATE vehicle_addons SET active = 0 WHERE id = ?", (pk,))
    connector.tick(now=1000.0)
    assert pk not in connector._state  # off: its schedule is forgotten, it starts afresh when it comes back


def test_what_the_settings_do_not_hold_stops_a_run_before_anything_is_sent(client, service):
    vid, _pk = _install(client, settings={"token": "", "car": "c1"})
    connector.tick(now=0.0)
    assert service.calls == [] and "the setting token is empty" in _log(vid)[-1][2]
    vid2, _ = _install(client, settings={"car": ""})
    connector.tick(now=0.0)
    assert service.calls == [] and "the setting car is empty" in _log(vid2)[-1][2]


def test_the_limits_that_keep_a_connector_safe(client, service, monkeypatch):
    vid, _pk = _install(client)
    monkeypatch.setattr(connector, "_public_host", lambda host: False)  # an address that points into the local network
    connector.tick(now=0.0)
    assert service.calls == [] and "the address is not allowed" in _log(vid)[-1][2]
    monkeypatch.setattr(connector, "_public_host", lambda host: True)
    service.answer = (200, b"x" * (connector.LIMIT + 1))
    connector.tick(now=100000.0)
    assert "the answer is too big" in _log(vid)[-1][2]
    service.answer = (302, b"")  # a redirect is no answer
    connector.tick(now=200000.0)
    assert "the service answered 302" in _log(vid)[-1][2]
    with pytest.raises(connector.ConnectorError):
        connector.fetch("http://api.example.com/x", {})  # not https


def test_the_login_of_the_person_is_the_credential_of_a_connector(client, service, monkeypatch):
    spec = {**SPEC, "requests": [{**SPEC["requests"][0], "auth": "oauth"}]}
    oauth_step = {
        "id": "connect",
        "type": "oauth",
        "oauth": {
            "authorize_url": "https://login.example.com/a",
            "token_url": "https://login.example.com/t",
            "client_id": "cid",
            "redirect": "paste",
            "redirect_uri": "https://localhost/callback",
        },
    }
    vid, pk = _install(client, spec, package={"setup": {"flow": [oauth_step]}})
    connector.tick(now=0.0)
    assert service.calls == [] and "nobody has logged in yet" in _log(vid)[-1][2]  # no login: nothing is sent, the person is told
    with db.tx() as conn:
        addon = addons.get(conn, vid, pk)
        oauth.save(conn, addon, "connect", {"access_token": "AT-1", "refresh_token": "RT-1", "token_type": "Bearer"})
    connector.tick(now=100000.0)
    assert service.calls[0][1]["Authorization"] == "Bearer AT-1"
    with db.tx() as conn:
        conn.execute("UPDATE connections SET state = 'login_required'")
    connector.tick(now=200000.0)
    assert len(service.calls) == 1 and "the login has expired - log in again" in _log(vid)[-1][2]


def test_basic_and_header_credentials_and_the_vin_of_the_car(client, service):
    spec = {
        **SPEC,
        "requests": [
            {
                "id": "car",
                "url": "https://api.example.com/{vin}/s",
                "headers": {"X-Key": "{setting.token}"},
                "auth": "basic:user:pass",
            },
        ],
    }
    vid, pk = _install(client, spec, settings={"user": "max", "pass": "secret"})
    connector.tick(now=0.0)
    assert "the VIN of the car is empty" in _log(vid)[-1][2]  # a VIN that is not set cannot fill a place
    with db.tx() as conn:
        conn.execute("UPDATE vehicles SET vin = 'WAUZZZ1234567890' WHERE id = ?", (vid,))
    connector.tick(now=100000.0)
    url, headers = service.calls[0]
    assert url == "https://api.example.com/WAUZZZ1234567890/s" and headers["X-Key"] == "tok-123"
    assert headers["Authorization"] == "Basic bWF4OnNlY3JldA=="
    for call in service.calls:
        assert "secret" not in call[0]  # a password is never part of an address
    del pk


def test_the_values_of_a_connector_are_judged_like_those_of_the_plugin_api(client, service):
    vid, _pk = _install(client)
    service.answer = (
        200,
        json.dumps({"data": {"fuel": {"ratio": 7.5}, "odometer": {"km": 100}}}).encode(),
    )  # 750 percent: the intake refuses it
    connector.tick(now=0.0)
    assert "the values were refused" in _log(vid)[-1][2] and _live(vid).get("fuel_level") is None
    assert connectors.NUMBERS["fuel_level_pct"][0] == "fuel_level"


def test_the_request_really_leaves_as_a_get_over_https_and_a_redirect_is_not_followed(tmp_path, monkeypatch):
    """The one place that fetches for a connector, against a real local https server (a certificate made for the test)."""
    import http.server
    import urllib.request

    from tests.tls_helper import https_server

    seen: list[tuple] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append((self.path, dict(self.headers)))
            if self.path == "/elsewhere":
                self.send_response(302)
                self.send_header("Location", "/car")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            payload = b'{"data": {"odometer": {"km": 1}}}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *a):
            pass

    monkeypatch.setattr(connector, "_public_host", lambda host: True)
    with https_server(tmp_path, Handler) as (base, trust):
        monkeypatch.setattr(
            oauth, "_opener", lambda: urllib.request.build_opener(oauth._NoRedirect, urllib.request.HTTPSHandler(context=trust))
        )
        assert connector.fetch(f"{base}/car?x=1", {"X-Key": "k"}) == {"data": {"odometer": {"km": 1}}}
        path, headers = seen[0]
        assert (
            path == "/car?x=1"
            and headers["X-Key"] == "k"
            and headers["Accept"] == "application/json"
            and headers["User-Agent"] == "car-assistant"
        )
        with pytest.raises(connector.ConnectorError) as redirect:
            connector.fetch(f"{base}/elsewhere", {})
        assert "answered 302" in str(redirect.value) and [p for p, _h in seen] == ["/car?x=1", "/elsewhere"]  # not followed
    with pytest.raises(connector.ConnectorError) as down:
        connector.fetch(f"{base}/car", {})
    assert "could not be reached" in str(down.value)
