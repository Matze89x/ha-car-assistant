"""Odd, wrong and hostile input to the Plugin API: the answer is a clean refusal (4xx) or a result, never a server error and never a crash.

A plugin is code of somebody else: whatever it sends - the wrong type, a huge number, a nested list, text where a number belongs, a missing body -
must not bring a page down. The inputs are made from a fixed seed, so the same run is repeated every time."""

import json
import random

import pytest
from fastapi.testclient import TestClient
from tests.test_connectors import hdr, setup


@pytest.fixture()
def api(env):
    from carassistant import web

    return TestClient(web.app, client=("172.30.32.2", 1), follow_redirects=False, raise_server_exceptions=False)


ODD = [
    None, True, False, 0, -1, 1, 3.14, -0.0, 10**30, -(10**30), float("1e308"), "", " ", "x" * 5000, "\u0000", "🚗", "<script>alert(1)</script>",
    "'; DROP TABLE vehicles; --", "../../etc/passwd", "NaN", "Infinity", [], [None], [[[[1]]]], {}, {"a": {"b": {"c": [1, 2, {"d": None}]}}}, [{"lat": 1}], {"lat": "x", "lon": []},
]  # fmt: skip

FIELDS = ["odometer_km", "vin", "position", "ignition", "doors", "windows", "lights", "locked", "warnings", "tyre_pressure_bar", "fuel_level_pct", "range_km", "speed_kmh",
          "battery_pct", "charging", "plugged", "service_due_days", "measured_at", "nope", "__proto__", "a.b", ""]  # fmt: skip


def _body(rnd: random.Random):
    kind = rnd.random()
    if kind < 0.1:
        return rnd.choice(ODD)
    return {rnd.choice(FIELDS): rnd.choice(ODD) for _ in range(rnd.randint(0, 5))}


def test_the_plugin_api_never_answers_with_a_server_error(api):
    token = setup(api)
    rnd = random.Random(20261124)
    posts = ["data", "track", "events", "trip-summary", "refuel", "signals", "logs", "plugin-settings"]
    gets = ["", "data", "track", "events", "signals", "control", "plugin-settings", "modules/none/page"]
    bad: list[str] = []
    for _ in range(260):
        what = rnd.choice(posts)
        body = _body(rnd)
        if what == "track" and isinstance(body, dict) and rnd.random() < 0.5:
            body = {"points": [rnd.choice(ODD) for _ in range(rnd.randint(0, 4))]}
        if what == "logs" and isinstance(body, dict) and rnd.random() < 0.5:
            body = {"lines": [rnd.choice(ODD) for _ in range(rnd.randint(0, 4))]}
        if what == "signals" and isinstance(body, dict) and rnd.random() < 0.5:
            body = {"signals": body}
        try:
            raw = json.dumps(body, allow_nan=True)
        except (TypeError, ValueError):
            continue
        r = api.post(
            f"/api/v1/vehicles/1/{what}",
            headers={**hdr(token), "Content-Type": "application/json"},
            content=raw.encode("utf-8", "surrogatepass"),
        )
        if r.status_code >= 500:
            bad.append(f"POST {what} {raw[:120]} -> {r.status_code}")
    for what in gets:
        for _ in range(3):
            r = api.get(f"/api/v1/vehicles/1/{what}".rstrip("/") if what else "/api/v1/vehicles", headers=hdr(token))
            if r.status_code >= 500:
                bad.append(f"GET {what} -> {r.status_code}")
    for path in (
        "/api/v1/vehicles/999999/data",
        "/api/v1/vehicles/abc/data",
        "/api/v1/vehicles/-1/track",
        "/api/v1/vehicles/1/data%00",
        "/api/v1/vehicles/1//data",
    ):
        for method in ("get", "post"):
            r = api.get(path, headers=hdr(token)) if method == "get" else api.post(path, headers=hdr(token), json={})
            if r.status_code >= 500:
                bad.append(f"{method.upper()} {path} -> {r.status_code}")
    for content in (b"", b"not json", b"{", b"\xff\xfe\x00", b"[" * 5000, b'{"a":' * 500):
        for what in ("data", "track", "events", "signals"):
            r = api.post(f"/api/v1/vehicles/1/{what}", headers={**hdr(token), "Content-Type": "application/json"}, content=content)
            if r.status_code >= 500:
                bad.append(f"POST {what} raw {content[:20]!r} -> {r.status_code}")
    assert not bad, "\n".join(bad[:15])
    page = api.get("/v/1/plugins/connections")  # whatever came in, the pages that show it still work
    assert page.status_code == 200
    assert api.get("/v/1/plugins/connections/zoom.json").status_code == 200
