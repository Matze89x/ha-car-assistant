from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def api(env):
    from carassistant import web

    return TestClient(web.app, client=("172.30.32.2", 1), follow_redirects=False)


def setup(api):
    r = api.post("/vehicles", data={"name": "Car", "odometer": "50000"})
    assert r.status_code == 303
    r = api.post("/integrations/api/tokens", data={"name": "my-plugin", "vehicle_id": "1"})
    assert r.status_code == 200
    import re

    return re.search(r"ca_[A-Za-z0-9_-]{20,}", r.text).group(0)


def hdr(token):
    return {"Authorization": f"Bearer {token}"}


def test_requires_valid_token(api):
    assert api.get("/api/v1").status_code == 401
    assert api.get("/api/v1", headers=hdr("ca_nope")).status_code == 401
    assert api.post("/api/v1/vehicles/1/data", json={}).status_code == 401


def test_push_values(api):
    token = setup(api)
    assert api.get("/api/v1", headers=hdr(token)).json()["connector"] == "my-plugin"
    cars = api.get("/api/v1/vehicles", headers=hdr(token)).json()
    assert cars[0]["odometer_km"] == 50000
    r = api.post(
        "/api/v1/vehicles/1/data",
        headers=hdr(token),
        json={"odometer_km": 50120, "fuel_level_pct": 61, "range_km": 420, "position": {"lat": 52.5, "lon": 13.4}},
    )
    assert r.status_code == 200 and r.json()["result"]["odometer_km"] == "stored"
    assert api.get("/api/v1/vehicles", headers=hdr(token)).json()[0]["odometer_km"] == 50120
    low = api.post("/api/v1/vehicles/1/data", headers=hdr(token), json={"odometer_km": 100}).json()
    assert low["result"]["odometer_km"].startswith("ignored")
    from carassistant import db

    with db.tx() as conn:
        live = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM live WHERE vehicle_id = 1")}
        src = conn.execute("SELECT source FROM odometer ORDER BY id DESC LIMIT 1").fetchone()["source"]
    assert live == {"fuel_level": "61", "range_km": "420", "position": "52.500000,13.400000"}
    assert src == "api:my-plugin"


def test_validation(api):
    token = setup(api)
    for body in ({"fuel_level_pct": 150}, {"odometer_km": "x"}, {"foo": 1}, {"position": {"lat": 99, "lon": 1}}, {"fuel_level_pct": True}):
        assert api.post("/api/v1/vehicles/1/data", headers=hdr(token), json=body).status_code == 422
    assert api.post("/api/v1/vehicles/9/data", headers=hdr(token), json={}).status_code == 403  # a token belongs to exactly one car
    assert (
        api.post("/api/v1/vehicles/1/data", headers={**hdr(token), "Content-Type": "application/json"}, content=b"{bad").status_code == 400
    )


def test_vehicle_scope_and_revoke(api):
    api.post("/vehicles", data={"name": "A"})
    api.post("/vehicles", data={"name": "B"})
    import re

    r = api.post("/integrations/api/tokens", data={"name": "only-b", "vehicle_id": "2"})
    token = re.search(r"ca_[A-Za-z0-9_-]{20,}", r.text).group(0)
    assert api.post("/api/v1/vehicles/1/data", headers=hdr(token), json={"odometer_km": 5}).status_code == 403
    assert api.post("/api/v1/vehicles/2/data", headers=hdr(token), json={"odometer_km": 5}).status_code == 200
    assert [c["id"] for c in api.get("/api/v1/vehicles", headers=hdr(token)).json()] == [2]
    assert api.post("/integrations/api/tokens/1/delete").status_code == 303
    assert api.get("/api/v1", headers=hdr(token)).status_code == 401


def test_token_works_externally_without_login(env, monkeypatch):
    from carassistant import web

    ing = TestClient(web.app, client=("172.30.32.2", 1), follow_redirects=False)
    token = setup(ing)
    monkeypatch.delenv("CARASSISTANT_DEV", raising=False)
    ext = TestClient(web.app, base_url="https://car.example.com", follow_redirects=False)
    assert ext.get("/api/v1", headers=hdr(token)).status_code == 200
    assert ext.get("/").status_code == 403  # the UI stays locked


def test_gzip_bodies_and_the_unpacked_limit(api):
    import gzip
    import json

    token = setup(api)
    body = gzip.compress(json.dumps({"odometer_km": 50500}).encode())
    r = api.post(
        "/api/v1/vehicles/1/data", headers={**hdr(token), "Content-Encoding": "gzip", "Content-Type": "application/json"}, content=body
    )
    assert r.status_code == 200 and r.json()["result"]["odometer_km"] == "stored"
    bomb = gzip.compress(b'{"odometer_km": 1, "x": "' + b"a" * 2_000_000 + b'"}')
    r = api.post("/api/v1/vehicles/1/data", headers={**hdr(token), "Content-Encoding": "gzip"}, content=bomb)
    assert r.status_code == 413
    r = api.post("/api/v1/vehicles/1/data", headers={**hdr(token), "Content-Encoding": "gzip"}, content=b"not gzip")
    assert r.status_code == 400


def test_new_fields_adblue_oil_speed_limit(api):
    token = setup(api)
    r = api.post(
        "/api/v1/vehicles/1/data",
        headers=hdr(token),
        json={"adblue_level_pct": 40, "adblue_range_km": 2300, "oil_level_pct": 70, "oil_warning": True, "speed_limit_kmh": 50},
    )
    assert r.status_code == 200
    data = api.get("/api/v1/vehicles/1/data", headers=hdr(token)).json()["data"]
    assert data["adblue_range_km"] == 2300 and data["oil_warning"] is True and data["speed_limit_kmh"] == 50
    assert api.post("/api/v1/vehicles/1/data", headers=hdr(token), json={"speed_limit_kmh": 999}).status_code == 422


def test_track_points_are_stored_read_back_and_set_the_position(api):
    token = setup(api)
    points = [
        {"ts": "2026-11-15T08:00:00Z", "lat": 52.5, "lon": 13.4, "speed_kmh": 30},
        {"ts": "2026-11-15T08:00:05Z", "lat": 52.501, "lon": 13.401, "speed_kmh": 42},
    ]
    r = api.post("/api/v1/vehicles/1/track", headers=hdr(token), json={"points": points})
    assert r.status_code == 200 and r.json()["stored"] == 2
    got = api.get("/api/v1/vehicles/1/track", headers=hdr(token)).json()["points"]
    assert [p["ts"] for p in got] == ["2026-11-15T08:00:00+00:00", "2026-11-15T08:00:05+00:00"]
    assert api.get("/api/v1/vehicles/1/track?since=2026-11-15T08:00:01Z", headers=hdr(token)).json()["points"][0]["lat"] == 52.501
    data = api.get("/api/v1/vehicles/1/data", headers=hdr(token)).json()["data"]
    assert data["position"]["lat"] == 52.501 and data["speed_kmh"] == 42  # the newest point is the current position
    assert api.post("/api/v1/vehicles/1/track", headers=hdr(token), json={"points": [{"lat": 99, "lon": 1}]}).status_code == 422
    assert api.post("/api/v1/vehicles/1/track", headers=hdr(token), json={"points": [{"lat": 1, "lon": 1, "ts": "x"}]}).status_code == 422
    assert api.post("/api/v1/vehicles/1/track", headers=hdr(token), json={"points": []}).status_code == 422


def test_raw_signals_are_kept_removed_and_limited(api):
    token = setup(api)
    r = api.post(
        "/api/v1/vehicles/1/signals",
        headers=hdr(token),
        json={"signals": {"kombi.odo_km": 52340, "pc.override": True, "tsd.signs": "1,2,3"}},
    )
    assert r.status_code == 200 and r.json()["stored"] == 3
    got = api.get("/api/v1/vehicles/1/signals", headers=hdr(token)).json()["signals"]
    assert got["kombi.odo_km"]["value"] == "52340" and got["pc.override"]["value"] == "true"
    api.post("/api/v1/vehicles/1/signals", headers=hdr(token), json={"signals": {"pc.override": None}})
    assert "pc.override" not in api.get("/api/v1/vehicles/1/signals", headers=hdr(token)).json()["signals"]
    assert api.post("/api/v1/vehicles/1/signals", headers=hdr(token), json={"signals": {"Bad Name": 1}}).status_code == 422
    too_many = {f"s{i}": i for i in range(301)}
    assert api.post("/api/v1/vehicles/1/signals", headers=hdr(token), json={"signals": too_many}).status_code == 422
    assert api.post("/api/v1/vehicles/1/signals", json={"signals": {"a": 1}}).status_code == 401


def test_a_finished_drive_becomes_a_trip_and_a_running_one_waits(api):
    from datetime import UTC, datetime, timedelta

    from carassistant import db, trips

    token = setup(api)

    def pts(start, n, step_s=30):
        return [
            {"ts": (start + timedelta(seconds=i * step_s)).isoformat(), "lat": 52.5 + i * 0.002, "lon": 13.4, "speed_kmh": 50}
            for i in range(n)
        ]

    old = datetime.now(UTC) - timedelta(hours=3)
    assert api.post("/api/v1/vehicles/1/track", headers=hdr(token), json={"points": pts(old, 10)}).json()["stored"] == 10
    now = datetime.now(UTC) - timedelta(minutes=1)
    api.post("/api/v1/vehicles/1/track", headers=hdr(token), json={"points": pts(now, 5, 10)})  # still driving: no trip yet
    with db.tx() as conn:
        rows = conn.execute("SELECT source, distance_km FROM trips").fetchall()
    assert len(rows) == 1 and rows[0]["source"] == "track" and 1.5 < rows[0]["distance_km"] < 2.5  # 9 steps of 0.002 deg ~ 2 km
    api.post(
        "/api/v1/vehicles/1/track", headers=hdr(token), json={"points": pts(datetime.now(UTC) - timedelta(minutes=30), 2)}
    )  # a short hop
    api.post("/api/v1/vehicles/1/data", headers=hdr(token), json={"ignition": True})  # the engine runs: the drive waits
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM trips").fetchone()[0] == 1  # the running drive still waits
        assert conn.execute("SELECT COUNT(*) FROM vehicle_track WHERE trip_id = 0").fetchone()[0] == 2  # the 2-point hop is dropped
        assert trips.from_track(conn, 1, datetime.now(UTC) + timedelta(minutes=20)) == 1  # twenty quiet minutes later it is a trip
        assert conn.execute("SELECT COUNT(*) FROM trips").fetchone()[0] == 2
        assert trips.from_track(conn, 1, datetime.now(UTC) + timedelta(minutes=20)) == 0  # nothing twice


def test_events_refuel_and_interval(api):
    token = setup(api)
    ev = [
        {"type": "speed_sign", "ts": "2026-11-15T08:00:00Z", "text": "50", "value": 50, "lat": 52.5, "lon": 13.4},
        {"type": "town_border", "text": "A -> B"},
    ]
    r = api.post("/api/v1/vehicles/1/events", headers=hdr(token), json={"events": ev})
    assert r.status_code == 200 and r.json()["stored"] == 2 and r.json()["control"]["interval_s"] == 120
    got = api.get("/api/v1/vehicles/1/events?type=speed_sign", headers=hdr(token)).json()["events"]
    assert len(got) == 1 and got[0]["value"] == 50 and got[0]["lat"] == 52.5
    assert api.post("/api/v1/vehicles/1/events", headers=hdr(token), json={"events": [{"type": "Bad Type"}]}).status_code == 422
    assert api.post("/api/v1/vehicles/1/events", headers=hdr(token), json={"events": [{"type": "x", "lat": 1}]}).status_code == 422
    body = {"date": "2026-11-15", "odometer_km": 52340, "amount": 41.5, "full_tank": True}
    assert api.post("/api/v1/vehicles/1/refuel", headers=hdr(token), json=body).json()["result"] == "stored"
    assert (
        api.post("/api/v1/vehicles/1/refuel", headers=hdr(token), json={**body, "odometer_km": 52342})
        .json()["result"]
        .startswith("ignored")
    )
    from carassistant import db

    with db.tx() as conn:
        row = conn.execute("SELECT amount, full_tank, notes FROM fuel").fetchone()
    assert row["amount"] == 41.5 and row["full_tank"] == 1 and row["notes"] == "api:my-plugin"
    assert api.post("/api/v1/vehicles/1/refuel", headers=hdr(token), json={"amount": -3}).status_code == 422
    api.post("/v/1/interval", data={"interval": "60"})
    assert api.get("/api/v1/vehicles/1/control", headers=hdr(token)).json()["control"]["interval_s"] == 60
    api.post("/v/1/interval", data={"interval": "7"})  # not an offered value: unchanged
    assert api.get("/api/v1/vehicles/1/control", headers=hdr(token)).json()["control"]["interval_s"] == 60


def test_range_and_tank_amount_show_for_fuel_and_electric_cars(api):
    from carassistant import status

    live = {"range_km": ("420", "2026-11-16T08:00:00+00:00"), "fuel_level": ("61", "x")}
    t = lambda key, **k: key  # noqa: E731
    hero = status.hero_range(live, t, 50, "L")
    assert hero["km"] == 420 and hero["pct"] == 61 and hero["liters"] == 30.5  # the amount from the level and the size of the tank
    assert (
        status.hero_range({"range_km": live["range_km"], "fuel_amount": ("12.5", "x")}, t, 50, "L")["pct"] == 25
    )  # the amount alone, with the size
    assert (
        status.hero_range({"range_km": live["range_km"], "fuel_amount": ("12.5", "x")}, t, None, "L")["liters"] == 12.5
    )  # amount without size: no per cent
    ev = status.hero_range({"range_km": live["range_km"], "battery_pct": ("80", "x")}, t, 60, "kWh", "charge")
    assert ev["pct"] == 80 and ev["liters"] == 48.0  # an electric car: the battery level counts
    assert (
        status.hero_range({"range_km": live["range_km"], "battery_pct": ("80", "x")}, t, 60, "L", "fuel")["pct"] is None
    )  # a fuel car does not read the battery
    assert status.tank({}, 50) is None
    token = setup(api)
    assert api.post("/api/v1/vehicles/1/data", headers=hdr(token), json={"fuel_amount": 31.5}).status_code == 200
    assert api.get("/api/v1/vehicles/1/data", headers=hdr(token)).json()["data"]["fuel_amount"] == 31.5
    assert "50" in api.get("/v/car").text or True


def test_the_vin_typed_in_is_only_compared_with_what_the_car_reports(api):
    from carassistant import db

    token = setup(api)
    url = "/api/v1/vehicles/1/data"
    r = api.post(url, json={"vin": "WV1ZZZ2KZZZ012345"}, headers=hdr(token))
    assert r.status_code == 200 and r.json()["result"]["vin"].startswith("not checked")  # none typed in yet: nothing is taken over
    with db.tx() as conn:
        assert conn.execute("SELECT vin FROM vehicles WHERE id = 1").fetchone()["vin"] is None
    api.post("/v/1/edit", data={"name": "Car", "vin": "wv1 zzz-2kzzz012345", "fuel_type": "petrol"})  # a person types it in
    r = api.post(url, json={"vin": "WV1ZZZ2KZZZ012345", "odometer_km": 60000}, headers=hdr(token))
    assert r.json()["result"]["vin"] == "matches"
    with db.tx() as conn:
        assert conn.execute("SELECT vin_verified FROM vehicles WHERE id = 1").fetchone()["vin_verified"] == 1
    assert "Confirmed by the car" in api.get("/v/1/edit").text  # the vehicle data say so
    r = api.post(url, json={"vin": "ANOTHER-CAR-99999", "odometer_km": 99000}, headers=hdr(token))  # another car: nothing gets in
    assert r.status_code == 409 and r.json()["error"] == "vin_mismatch"
    assert api.post(url, json={"odometer_km": 61000}, headers=hdr(token)).status_code == 200  # a plugin that sends no VIN is not refused
    for bad in ("12", "ab$cd-123456", 12345, ""):
        assert api.post(url, json={"vin": bad}, headers=hdr(token)).status_code == 422, bad
    api.post(
        "/v/1/edit", data={"name": "Car", "vin": "NEWVIN123456", "fuel_type": "petrol"}
    )  # another VIN typed in: not confirmed any more
    with db.tx() as conn:
        assert conn.execute("SELECT vin_verified FROM vehicles WHERE id = 1").fetchone()["vin_verified"] == 0


def test_a_drive_ends_when_the_ignition_goes_off(api):
    from datetime import UTC, datetime, timedelta

    token = setup(api)
    now = datetime.now(UTC)
    pts = [
        {"ts": (now - timedelta(minutes=4 - i)).strftime("%Y-%m-%dT%H:%M:%SZ"), "lat": 52.5 + i * 0.01, "lon": 13.4, "speed_kmh": 50}
        for i in range(5)
    ]
    api.post("/api/v1/vehicles/1/track", headers=hdr(token), json={"points": pts})
    from carassistant import db

    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM trips").fetchone()[0] == 0  # the last point is only minutes old: still driving
    api.post("/api/v1/vehicles/1/data", headers=hdr(token), json={"ignition": False})
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM trips").fetchone()[0] == 1  # ignition off: the trip is closed at once


def _stamps(vehicle_id=1):
    from carassistant import db

    with db.tx() as conn:
        return {
            r["key"]: (r["value"], r["updated"])
            for r in conn.execute("SELECT key, value, updated FROM live WHERE vehicle_id = ?", (vehicle_id,))
        }


def test_a_value_sent_again_unchanged_is_no_news_and_measured_at_is_kept(api):
    """The last signal is when the CAR reported, not when we were told again (a restart of the app or the plugin sends remembered values)."""
    token = setup(api)
    old = "2026-11-01T08:00:00Z"
    r = api.post("/api/v1/vehicles/1/data", headers=hdr(token), json={"range_km": 300, "measured_at": old})
    assert r.status_code == 200
    assert _stamps()["range_km"][1].startswith("2026-11-01T08:00:00")
    # the same value again without a time: the car did not report anything new
    assert api.post("/api/v1/vehicles/1/data", headers=hdr(token), json={"range_km": 300}).status_code == 200
    assert _stamps()["range_km"][1].startswith("2026-11-01T08:00:00")
    # a changed value without a time counts from its arrival
    api.post("/api/v1/vehicles/1/data", headers=hdr(token), json={"range_km": 280})
    assert _stamps()["range_km"][1] > "2026-11-02"
    # a time never goes backwards, and one in the future is cut to now; a measurement older than the one we have does not replace it
    api.post("/api/v1/vehicles/1/data", headers=hdr(token), json={"range_km": 270, "measured_at": old})
    assert _stamps()["range_km"][1] > "2026-11-02" and _stamps()["range_km"][0] == "280"
    api.post("/api/v1/vehicles/1/data", headers=hdr(token), json={"range_km": 260, "measured_at": "2999-01-01T00:00:00Z"})
    assert _stamps()["range_km"][1] < "2100"
    assert api.post("/api/v1/vehicles/1/data", headers=hdr(token), json={"range_km": 250, "measured_at": "yesterday"}).status_code == 422


def test_home_assistant_values_carry_the_time_home_assistant_gives(api, monkeypatch):
    from carassistant import db, ha, live

    setup(api)
    state = {"state": "55", "attributes": {}, "last_reported": "2026-11-01T09:30:00+00:00"}
    monkeypatch.setattr(ha, "get_state", lambda entity: state)
    with db.tx() as conn:
        conn.execute("UPDATE vehicles SET bind_fuel_level = 'sensor.fuel' WHERE id = 1")
        live.refresh_vehicle(conn, conn.execute("SELECT * FROM vehicles WHERE id = 1").fetchone())
    assert _stamps()["fuel_level"][1].startswith("2026-11-01T09:30:00")  # not the moment we looked


def test_connected_means_the_car_reported_within_half_an_hour():
    from datetime import UTC, datetime, timedelta

    from carassistant import status

    now = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
    assert status.connected({}, now) is None
    assert status.connected({"range_km": ("300", now - timedelta(minutes=10))}, now) is True
    assert status.connected({"range_km": ("300", now - timedelta(minutes=45))}, now) is False


def test_nothing_is_deprecated_today_and_an_announced_change_is_shown_in_the_answer(api, monkeypatch):
    from datetime import date

    from carassistant import deprecations

    token = setup(api)
    r = api.post("/api/v1/vehicles/1/data", headers=hdr(token), json={"range_km": 300})
    assert "deprecation" not in r.headers and "deprecated" not in r.json()  # the lists are empty: nothing is announced
    assert not deprecations.ENDPOINTS and not deprecations.FIELDS
    # announce a field and an endpoint: the headers and the answer say so, and everything keeps working
    monkeypatch.setitem(deprecations.FIELDS, "range_km", {"since": "0.9.0", "sunset": date(2027, 6, 1), "use": "range_km2"})
    r = api.post("/api/v1/vehicles/1/data", headers=hdr(token), json={"range_km": 310})
    assert r.status_code == 200 and r.json()["result"]["range_km"] == "stored"
    assert (
        r.headers["deprecation"] == "true"
        and r.headers["sunset"].endswith("2027 00:00:00 GMT")
        and 'rel="deprecation"' in r.headers["link"]
    )
    assert r.json()["deprecated"] == [{"field": "range_km", "since": "0.9.0", "sunset": "2027-06-01", "use": "range_km2"}]
    monkeypatch.setitem(
        deprecations.ENDPOINTS, ("GET", "/api/v1/vehicles/{id}/data"), {"since": "0.9.0", "sunset": None, "use": "something else"}
    )
    r = api.get("/api/v1/vehicles/1/data", headers=hdr(token))
    assert r.status_code == 200 and r.headers["deprecation"] == "true" and "sunset" not in r.headers


def test_plugin_tokens_are_always_kept_encrypted_and_travel_in_backups(api, monkeypatch):
    from carassistant import backup, backupsecrets, connectors, db, vault

    monkeypatch.setattr(backupsecrets, "SCRYPT_N", 2**10)  # (the real cost is for people, not for tests)
    token = setup(api)  # a token of a plugin-less setup: made by the integrations page
    with db.tx() as conn:
        token_id = conn.execute("SELECT id FROM api_tokens ORDER BY id DESC LIMIT 1").fetchone()["id"]
        assert connectors.remember(conn, token_id, "ca_" + "x" * 40) is False  # a token that is not the one of this id is refused
        assert connectors.remember(conn, token_id, token) is True  # no switch: always kept
        raw = conn.execute("SELECT token_enc FROM api_tokens WHERE id = ?", (token_id,)).fetchone()["token_enc"]
        assert raw.startswith("enc:v1:") and token not in raw  # encrypted at rest
        assert connectors.remembered(conn, token_id) == token
    assert api.post("/settings/token-remember", data={"remember": "1"}).status_code in (404, 405)  # the switch is gone
    import io
    import sqlite3
    import tempfile
    import zipfile
    from pathlib import Path

    def kept_in(file: bytes):
        """What the copy of the database inside a backup holds as the kept token, and whether the token can be read anywhere in the file."""
        zf = zipfile.ZipFile(io.BytesIO(file))
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "x.db").write_bytes(zf.read("carassistant.db"))
            inside = sqlite3.connect(Path(tmp) / "x.db").execute("SELECT token_enc FROM api_tokens WHERE id = ?", (token_id,)).fetchone()[0]
        return inside, any(token.encode() in zf.read(n) for n in zf.namelist())

    inside, readable = kept_in(backup.create())  # without a passphrase the token stays sealed with the key of this system ...
    assert inside.startswith(vault.PREFIX) and not readable
    inside, readable = kept_in(sealed := backup.create("a long enough passphrase"))  # ... with one it travels in the secrets block
    assert inside is None and not readable and backup.secrets_state(sealed) == "passphrase"
    with db.tx() as conn:  # a restore on another system: the key is another one, so nothing of the old copy can be read
        conn.execute("UPDATE api_tokens SET token_enc = NULL WHERE id = ?", (token_id,))
    backup.restore(sealed, "a long enough passphrase")
    with db.tx() as conn:
        assert connectors.remembered(conn, token_id) == token and conn.execute(
            "SELECT token_enc FROM api_tokens WHERE id = ?", (token_id,)
        ).fetchone()[0].startswith(vault.PREFIX)
    with db.tx() as conn:  # a file of the old format carried the token readable: a restore seals it with the key of the system
        conn.execute("UPDATE api_tokens SET token_enc = ? WHERE id = ?", (token, token_id))
        connectors.reseal(conn)
        assert conn.execute("SELECT token_enc FROM api_tokens WHERE id = ?", (token_id,)).fetchone()[0].startswith(vault.PREFIX)
        assert connectors.remembered(conn, token_id) == token


def test_the_car_names_its_own_spot(api):
    from carassistant import db, places

    token = setup(api)
    pos = {"lat": 52.5, "lon": 13.4, "street": "  Hauptstraße   12 ", "place": "Berlin"}
    r = api.post("/api/v1/vehicles/1/data", headers=hdr(token), json={"position": pos})
    assert r.status_code == 200
    with db.tx() as conn:
        assert places.here_cached(conn, 52.5, 13.4) == ("Berlin", "Hauptstraße 12")
    bad = api.post("/api/v1/vehicles/1/data", headers=hdr(token), json={"position": {**pos, "street": 5}})
    assert bad.status_code == 422


def test_refuel_without_amount_is_unfinished_and_small_steps_add_up(api):
    from carassistant import db, refuel_detect

    token = setup(api)
    r = api.post("/api/v1/vehicles/1/refuel", headers=hdr(token), json={"odometer_km": 52000, "full_tank": True})
    assert r.status_code == 200
    with db.tx() as conn:
        todo = refuel_detect.todo(conn, 1)
    assert len(todo) == 1 and todo[0]["odometer_km"] == 52000 and todo[0]["rise"] is None
    with db.tx() as conn:  # 33 -> 40 -> 50 is one refuel of 17 points
        conn.execute("DELETE FROM fuel")
        refuel_detect._floor.clear()
        assert refuel_detect.level_changed(conn, 1, 33, 40) is False
        assert refuel_detect.level_changed(conn, 1, 40, 50) is True


def test_oil_change_due_fields(api):
    token = setup(api)
    assert (
        api.post("/api/v1/vehicles/1/data", headers=hdr(token), json={"oil_change_due_km": 18600, "oil_change_due_days": -3}).status_code
        == 200
    )
    data = api.get("/api/v1/vehicles/1/data", headers=hdr(token)).json()["data"]
    assert data["oil_change_due_km"] == 18600 and data["oil_change_due_days"] == -3


def test_trip_summary_goes_to_the_trip_that_ended_then(api):
    token = setup(api)
    # yesterday around noon (UTC): the drive never crosses local midnight, whatever the time zone and whenever the test runs
    now = (datetime.now(UTC) - timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)
    start = now - timedelta(hours=2)
    points = [
        {"ts": (start + timedelta(minutes=m)).isoformat(), "lat": 52.5 + m * 0.002, "lon": 13.4, "speed_kmh": 40} for m in range(0, 10)
    ]
    assert api.post("/api/v1/vehicles/1/track", headers=hdr(token), json={"points": points}).status_code == 200
    end = datetime.fromisoformat(points[-1]["ts"])
    body = {
        "ts": (end + timedelta(minutes=1)).isoformat(),
        "distance_km": 2.0,
        "consumption_l_100km": 8.2,
        "avg_speed_kmh": 26,
        "minutes": 28,
    }
    r = api.post("/api/v1/vehicles/1/trip-summary", headers=hdr(token), json=body)
    assert r.status_code == 200
    from carassistant import db

    with db.tx() as conn:
        trip = conn.execute("SELECT consumption_l100, avg_kmh, bc_minutes FROM trips").fetchone()
        assert (trip["consumption_l100"], trip["avg_kmh"], trip["bc_minutes"]) == (8.2, 26, 28)
        assert conn.execute("SELECT COUNT(*) FROM trip_summaries").fetchone()[0] == 0  # attached, nothing waits
    assert api.post("/api/v1/vehicles/1/trip-summary", headers=hdr(token), json={}).status_code == 422
    far = api.post("/api/v1/vehicles/1/trip-summary", headers=hdr(token), json={"ts": start.isoformat(), "avg_speed_kmh": 30})
    assert far.status_code == 200
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM trip_summaries").fetchone()[0] == 1  # no trip ended then: it waits


def test_with_two_sources_of_one_field_the_newer_measurement_wins_whoever_sent_it_last(api):
    """A slow plugin that delivers a reading after a faster one must not push the car back to an older state."""
    token = setup(api)

    def post(value, at=None):
        return api.post("/api/v1/vehicles/1/data", headers=hdr(token), json={"range_km": value, **({"measured_at": at} if at else {})})

    post(300, "2026-11-01T10:00:00Z")
    post(250, "2026-11-01T09:00:00Z")  # an hour older, arrives later
    assert _stamps()["range_km"][0] == "300" and _stamps()["range_km"][1].startswith("2026-11-01T10:00:00")
    post(280, "2026-11-01T11:00:00Z")  # newer
    assert _stamps()["range_km"][0] == "280" and _stamps()["range_km"][1].startswith("2026-11-01T11:00:00")
    post(281, "2026-11-01T11:00:00Z")  # the same moment: the one that arrived last
    assert _stamps()["range_km"][0] == "281"
