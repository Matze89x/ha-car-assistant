"""Odd input to every route of the app (forms and query strings): a clean answer - a page, a redirect or a refusal - and never a server error.

Every POST route gets forms with wrong types, huge numbers, impossible dates and markup; every GET route gets strange query strings. The input is
made from a fixed seed. Routes that sign out, delete everything, restore a backup, install or update are left out (they would end the walk)."""

import random
import re
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

ODD = [
    "",
    " ",
    "0",
    "-1",
    "1e9",
    "99999999999999999999",
    "abc",
    "x" * 2500,
    "<b>x</b>",
    "'; --",
    "2026-13-45",
    "2026-02-30",
    "NaN",
    "\u0000",
    "\U0001f697",
    "1,5",
    "1.5.5",
    "../..",
    "%s%s",
    "-9999",
]
FORM_KEYS = ["name", "title", "date", "odometer", "odometer_km", "amount", "price_per_unit", "price_total", "station", "notes", "category", "due_date", "interval_km",
             "interval_months", "cost", "km", "start_km", "end_km", "plate", "vin", "fuel_type", "fuel2_type", "year", "size", "season", "id", "view", "back", "q", "go", "lat",
             "lon", "fuel_kind", "full_tank", "confirm", "mode", "key", "value", "kind"]  # fmt: skip
QUERY_KEYS = ["page", "limit", "offset", "g", "n", "c", "ap", "ps", "view", "q", "sort", "go", "lat", "lon", "fuel", "radius", "source", "open", "edit", "m", "tab", "car", "range",
              "start", "end", "season", "fs", "kind", "id", "plugin", "area", "name", "dir", "odo"]  # fmt: skip
SKIP_POST = re.compile(
    r"logout|reset|restore|uninstall|factory|backup|archive|signout|/setup|passkey|webauthn|login|users/|account|mcp|token|update|install|sources|upload|import|restart|/delete",
    re.I,
)
SKIP_GET = re.compile(r"logout|signout|download|export|backup|\.zip|/static|/media|stream|/events|/login|/setup|/auth", re.I)


@pytest.fixture()
def world(env):
    import demo_data

    from carassistant import db, web

    with db.tx() as conn:
        demo_data.create(conn)
    return TestClient(web.app, client=("172.30.32.2", 1), follow_redirects=False, raise_server_exceptions=False)


def _routes(method: str, skip):
    from carassistant import web

    return [r.path for r in web.app.routes if method in getattr(r, "methods", ()) and getattr(r, "path", "") and not skip.search(r.path)]


def _fill(path: str) -> str:
    return re.sub(r"\{[^}:]*(:[^}]*)?\}", "1", path)


def test_no_route_answers_odd_forms_with_a_server_error(world):
    rnd = random.Random(7)
    bad = []
    for path in _routes("POST", SKIP_POST):
        for _ in range(3):
            data = {rnd.choice(FORM_KEYS): rnd.choice(ODD) for _ in range(rnd.randint(0, 6))}
            r = world.post(_fill(path), data=data, headers={"Origin": "http://testserver"})
            if r.status_code >= 500:
                bad.append(f"POST {path} {str(data)[:100]} -> {r.status_code}")
    assert not bad, "\n".join(bad[:12])


def test_no_route_answers_odd_query_strings_with_a_server_error(world):
    rnd = random.Random(11)
    bad = []
    for path in _routes("GET", SKIP_GET):
        for _ in range(3):
            query = "&".join(f"{rnd.choice(QUERY_KEYS)}={quote(rnd.choice(ODD))}" for _ in range(rnd.randint(0, 4)))
            r = world.get(_fill(path) + ("?" + query if query else ""))
            if r.status_code >= 500:
                bad.append(f"GET {path}?{query[:100]} -> {r.status_code}")
    assert not bad, "\n".join(bad[:12])


def test_a_json_body_that_is_no_object_is_refused_not_a_crash(world):
    for path in ("/push/status", "/push/unsubscribe", "/push/subscribe"):
        for content in (b"", b"[]", b'"x"', b"{", b"\xff\xfe", b"null", b"123"):
            r = world.post(path, content=content, headers={"Content-Type": "application/json", "Origin": "http://testserver"})
            assert r.status_code < 500, (path, content, r.status_code)
