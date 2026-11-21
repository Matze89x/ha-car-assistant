import pytest
from fastapi.testclient import TestClient

PW = "correct horse battery"


@pytest.fixture(autouse=True)
def _reset_locks():
    from carassistant import auth_web

    auth_web._failures.clear()
    auth_web._name_failures.clear()


@pytest.fixture()
def ext(env, monkeypatch):
    """Direct (non-ingress) access: dev mode off."""
    monkeypatch.delenv("CARASSISTANT_DEV", raising=False)
    from carassistant import web

    return TestClient(web.app, base_url="https://car.example.com", follow_redirects=False, headers={"Origin": "https://car.example.com"})


@pytest.fixture()
def ing(env, monkeypatch):
    monkeypatch.delenv("CARASSISTANT_DEV", raising=False)
    from carassistant import web

    return TestClient(web.app, client=("172.30.32.2", 5000), follow_redirects=False)


def make_admin(ing, name="admin"):
    r = ing.post("/account/create", data={"username": name, "password": PW, "password2": PW})
    assert r.status_code == 303


def test_external_locked_without_account(ext):
    r = ext.get("/")
    assert r.status_code == 403
    assert ext.get("/healthz").status_code in (200, 403)


def test_ingress_never_needs_login(ing):
    assert ing.get("/").status_code == 200
    make_admin(ing)
    assert ing.get("/").status_code == 200
    assert ing.get("/login").status_code == 303


def test_external_requires_login_then_works(ing, ext):
    make_admin(ing)
    r = ext.get("/")
    assert r.status_code == 303 and r.headers["location"].startswith("/login")
    assert ext.get("/login").status_code == 200
    bad = ext.post("/login", data={"username": "admin", "password": "nope-nope-nope", "next": "/"})
    assert bad.status_code == 401
    ok = ext.post("/login", data={"username": "admin", "password": PW, "next": "/"})
    assert ok.status_code == 303 and "ca_session" in ext.cookies
    assert ext.get("/").status_code == 200
    ext.post("/logout")
    assert ext.get("/").status_code == 303


def test_open_redirect_blocked(ing, ext):
    make_admin(ing)
    r = ext.post("/login", data={"username": "admin", "password": PW, "next": "https://evil.example/x"})
    assert r.status_code == 303 and not r.headers["location"].startswith("http")


def test_lockout_after_failures(ing, ext):
    make_admin(ing)
    for _ in range(5):
        ext.post("/login", data={"username": "admin", "password": "wrong-wrong-wrong"})
    r = ext.post("/login", data={"username": "admin", "password": PW})
    assert r.status_code == 429


def test_setup_wizard_after_first_car(ing):
    r = ing.post("/vehicles", data={"name": "Car"})
    assert r.headers["location"] == "/setup/functions"  # step 3: which fixed integrations does the car need
    page = ing.get("/setup/functions").text
    assert "Step 3 of 4" in page and 'action="/setup/functions"' in page and "Integrations" in page
    r = ing.post("/setup/functions", data={"on": ["service", "fuel"]})  # everything else is switched off for this car
    assert r.headers["location"] == "/setup/access"
    from carassistant import db, modules

    with db.tx() as conn:
        off = modules.vehicle_off(conn, 1)
    assert "trips" in off and "service" not in off and "fuel" not in off
    assert ing.get(r.headers["location"]).status_code == 200
    r2 = ing.post("/setup/access", data={"choice": "local", "next": "/v/1"})
    assert r2.status_code == 303 and r2.headers["location"].startswith("/v/")


def test_setup_wizard_creates_account(ing, ext):
    ing.post("/vehicles", data={"name": "Car"})
    r = ing.post("/setup/access", data={"choice": "external", "username": "owner", "password": PW, "password2": PW, "next": "/"})
    assert r.status_code == 303
    assert ext.get("/").status_code == 303


def test_password_rules_and_a_forgotten_password_is_reset_in_the_panel(ing, ext):
    r = ing.post("/account/create", data={"username": "admin", "password": "short", "password2": "short"})
    assert r.status_code == 303
    assert ing.get("/settings/design").status_code == 200
    make_admin(ing)
    assert ing.post("/account/recovery").status_code in (404, 405)  # no recovery codes any more
    assert ext.post("/login/recover", data={"username": "admin", "code": "X", "new": PW, "new2": PW}).status_code in (401, 404, 405)
    new = "another long password"  # forgotten: Home Assistant already signed the person in, the panel sets a new one
    assert ing.post("/account/password", data={"new": new, "new2": new}).status_code == 303
    assert ext.post("/login", data={"username": "admin", "password": new}).status_code == 303
    page = TestClient(ext.app, base_url="https://car.example.com", follow_redirects=False).get("/login").text
    assert "recovery" not in page.lower() and "Home Assistant" in page  # the login names where to reset it


def test_external_post_needs_same_origin(ing, ext):
    make_admin(ing)
    ext.post("/login", data={"username": "admin", "password": PW})
    r = ext.post("/settings/language", data={"language": "de"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_passkey_options_external_only(ing, ext):
    make_admin(ing)
    assert ext.post("/login/passkey/options").status_code == 200
    ext.post("/login", data={"username": "admin", "password": PW})
    j = ext.post("/account/passkey/options").json()
    assert j["ok"] and j["options"]["challenge"]
    assert not ing.post("/account/passkey/options").json()["ok"]


# ------------------------------------------------------------------ strict rules, passcode, blocks (user level)
STRONG = "Correct-Horse-9-Battery"


def test_strict_password_rules_apply_when_the_app_is_reachable_from_outside(env, monkeypatch):
    from carassistant import accounts, config, db

    config.forget_external()
    accounts.check_new_password("correct horse battery")  # long enough: fine while only Home Assistant opens it
    with db.tx() as conn:
        db.set_setting(conn, "ext.url", "https://car.example.com")
    config.forget_external()
    assert accounts.strict()
    for weak, key in (
        ("shortpass1!", "acct.pw_short"),
        ("alllowercaseletters", "acct.pw_classes"),
        ("Password-12345", "acct.pw_common"),
        ("aaaaAAAA1111!!!!", "acct.pw_common"),
    ):
        with pytest.raises(accounts.AccountError) as exc:
            accounts.check_new_password(weak, "admin")
        assert exc.value.key == key, weak
    with pytest.raises(accounts.AccountError):
        accounts.check_new_password("My-Admin-Pass-77!", "admin")  # contains the user name
    accounts.check_new_password(STRONG, "admin")


def test_name_lock_holds_even_from_other_addresses_and_can_be_released(ing, ext):
    from carassistant import auth_web

    make_admin(ing)
    for _ in range(auth_web.lock_after()):
        ext.post("/login", data={"username": "admin", "password": "wrong-wrong-wrong"})
    auth_web._failures.clear()  # a different address: the NAME is still locked
    assert ext.post("/login", data={"username": "admin", "password": PW}).status_code == 429
    assert any(b["kind"] == "name" and b["key"] == "admin" for b in auth_web.blocked())
    assert "admin" in ing.get("/settings/user").text  # the administrator sees what is blocked ...
    ing.post("/settings/unblock", data={"kind": "name", "key": "admin"})  # ... and releases it
    assert ext.post("/login", data={"username": "admin", "password": PW}).status_code == 303


def test_lock_settings_are_server_settings(ing):
    from carassistant import auth_web

    make_admin(ing)
    assert (auth_web.lock_after(), auth_web.lock_seconds()) == (5, 900)
    ing.post("/settings/security", data={"lock_after": "3", "lock_minutes": "60"})
    assert (auth_web.lock_after(), auth_web.lock_seconds()) == (3, 3600)


def test_passcode_rules():
    from carassistant import accounts

    for bad in ("12345", "111111", "123456", "654321", "121212", "12ab56", "1234567890123"):
        with pytest.raises(accounts.AccountError):
            accounts.check_passcode(bad)
    accounts.check_passcode("493817")


def test_passcode_locks_an_idle_device_and_unlocks_it(ing, ext):
    from carassistant import accounts, db

    make_admin(ing)
    assert ext.post("/login", data={"username": "admin", "password": PW}).status_code == 303
    r = ext.post("/account/passcode", data={"code": "493817", "code2": "493817", "minutes": "5", "current": PW})
    assert "pin_set" in r.headers["location"]
    assert ext.get("/").status_code == 200  # just used: still open
    with db.tx() as conn:  # the device was idle for longer than the chosen time
        conn.execute("UPDATE sessions SET unlocked_at = '2000-01-01T00:00:00+00:00'")
    locked = ext.get("/")
    assert locked.status_code == 303 and locked.headers["location"].startswith("/unlock")
    assert ext.post("/vehicles", data={"name": "x"}).status_code == 401  # nothing else works while locked
    wrong = ext.post("/unlock", data={"code": "000000", "next": "/"})
    assert wrong.status_code == 401
    assert ext.post("/unlock", data={"code": "493817", "next": "/"}).status_code == 303
    assert ext.get("/").status_code == 200
    ext.post("/account/lock")
    assert ext.get("/").status_code == 303  # locked by hand
    for _ in range(5):  # five wrong codes: signed out completely
        ext.post("/unlock", data={"code": "000000", "next": "/"})
    assert ext.get("/").headers["location"].startswith("/login")
    with db.tx() as conn:
        assert accounts.has_passcode(conn, 1)


def test_sign_out_everywhere_else(ing, ext):
    make_admin(ing)
    ext.post("/login", data={"username": "admin", "password": PW})
    other = TestClient(ext.app, base_url="https://car.example.com", follow_redirects=False, headers={"Origin": "https://car.example.com"})
    other.post("/login", data={"username": "admin", "password": PW})
    assert other.get("/").status_code == 200
    ext.post("/account/signout-all")
    assert ext.get("/").status_code == 200 and other.get("/").status_code == 303


# ------------------------------------------------------------------ a software passkey: the whole round trip (register, sign in, wrong signature, lock)
def _b64(raw: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


class SoftKey:
    """A made-up authenticator (like the one in a phone): an own key pair, signs what the browser would hand it."""

    def __init__(self, rp_id="car.example.com", origin="https://car.example.com"):
        from cryptography.hazmat.primitives.asymmetric import ec

        self.rp_id, self.origin, self.count = rp_id, origin, 0
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.cred_id = b"credential-" + bytes(range(16))

    def _client(self, kind, challenge):
        import json

        return json.dumps({"type": kind, "challenge": challenge, "origin": self.origin}).encode()

    def register(self, challenge):
        import hashlib
        import struct

        import cbor2

        nums = self.key.public_key().public_numbers()
        cose = cbor2.dumps({1: 2, 3: -7, -1: 1, -2: nums.x.to_bytes(32, "big"), -3: nums.y.to_bytes(32, "big")})
        auth = hashlib.sha256(self.rp_id.encode()).digest() + bytes([0x45]) + struct.pack(">I", 0)
        auth += bytes(16) + struct.pack(">H", len(self.cred_id)) + self.cred_id + cose
        att = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth})
        return {
            "id": _b64(self.cred_id),
            "rawId": _b64(self.cred_id),
            "type": "public-key",
            "response": {"clientDataJSON": _b64(self._client("webauthn.create", challenge)), "attestationObject": _b64(att)},
        }

    def sign_in(self, challenge, bad=False):
        import hashlib
        import struct

        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec

        self.count += 1
        client = self._client("webauthn.get", challenge)
        auth = hashlib.sha256(self.rp_id.encode()).digest() + bytes([0x05]) + struct.pack(">I", self.count)
        sig = self.key.sign(auth + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256()))
        if bad:
            sig = sig[:-1] + bytes([sig[-1] ^ 0xFF])
        return {
            "id": _b64(self.cred_id),
            "rawId": _b64(self.cred_id),
            "type": "public-key",
            "response": {"clientDataJSON": _b64(client), "authenticatorData": _b64(auth), "signature": _b64(sig), "userHandle": ""},
        }


def test_passkey_round_trip_with_a_software_authenticator(ing, ext):
    make_admin(ing)
    ext.post("/login", data={"username": "admin", "password": PW})
    device = SoftKey()
    begin = ext.post("/account/passkey/options").json()
    assert ext.post(
        "/account/passkey/register",
        json={"token": begin["token"], "credential": device.register(begin["options"]["challenge"]), "label": "Phone"},
    ).json() == {"ok": True}
    ext.post("/logout")
    fresh = TestClient(ext.app, base_url="https://car.example.com", follow_redirects=False, headers={"Origin": "https://car.example.com"})
    # signing in with the registered key works and gives a session
    opts = fresh.post("/login/passkey/options").json()
    ok = fresh.post(
        "/login/passkey/verify", json={"token": opts["token"], "credential": device.sign_in(opts["options"]["challenge"]), "next": "/"}
    )
    assert ok.status_code == 200 and ok.json()["ok"] is True and fresh.get("/").status_code != 303
    # a replayed token and a wrong signature are refused
    assert (
        fresh.post(
            "/login/passkey/verify", json={"token": opts["token"], "credential": device.sign_in(opts["options"]["challenge"]), "next": "/"}
        ).status_code
        == 401
    )
    other = TestClient(ext.app, base_url="https://car.example.com", follow_redirects=False, headers={"Origin": "https://car.example.com"})
    opts = other.post("/login/passkey/options").json()
    assert (
        other.post(
            "/login/passkey/verify", json={"token": opts["token"], "credential": device.sign_in(opts["options"]["challenge"], bad=True)}
        ).status_code
        == 401
    )
    # from the wrong address (another origin) a key does not work either
    evil = SoftKey(origin="https://evil.example")
    evil.key, evil.cred_id = device.key, device.cred_id
    opts = other.post("/login/passkey/options").json()
    assert other.post(
        "/login/passkey/verify", json={"token": opts["token"], "credential": evil.sign_in(opts["options"]["challenge"])}
    ).status_code in (400, 401)


def test_wrong_passkeys_lock_the_address_and_tell_the_real_minutes(ing, ext):
    from carassistant import auth_web, db

    make_admin(ing)
    with db.tx() as conn:
        db.set_setting(conn, "security.lock_minutes", "30")
    for _ in range(auth_web.lock_after()):
        opts = ext.post("/login/passkey/options").json()
        ext.post("/login/passkey/verify", json={"token": opts["token"], "credential": {"id": "nope", "response": {}}})
    r = ext.post("/login/passkey/options")
    assert r.status_code == 429 and "30" in r.json()["error"]  # the minutes of the setting, not a fixed number


def test_account_status_depends_on_the_port(ing, monkeypatch):
    from carassistant import ha

    monkeypatch.setattr(ha, "network_port", lambda: (True, None))  # no port: only the Home Assistant panel
    page = ing.get("/settings/user").text
    assert "needs none" in page and "direct access from outside is locked" not in page
    make_admin(ing)
    page = ing.get("/settings/user").text
    assert (
        "Home Assistant only" in page and "Login active" not in page and "Forgot a password?" in page
    )  # no port: the panel resets a password
    ha._cache.clear()
    monkeypatch.setattr(ha, "network_port", lambda: (True, 9000))  # a port is set: direct access exists, its status lives on this page
    page = ing.get("/settings/user").text
    assert "Login active" in page and 'id="access"' not in page and "Forgot a password?" not in page
    ha._cache.clear()
    monkeypatch.setattr(ha, "network_port", lambda: (True, None))
    assert 'id="access"' not in ing.get("/settings/user").text


def test_a_user_who_is_not_an_administrator_cannot_touch_the_system(ing, ext):
    """The backup holds every user, token and car; a restore replaces it all. Only an administrator may read or change system settings."""
    make_admin(ing)
    ing.post("/account/users/add", data={"username": "guest", "password": PW})
    ext.post("/login", data={"username": "guest", "password": PW, "next": "/"})
    assert ext.get("/").status_code == 200  # signed in as a normal user
    for path in ("/settings/backup.zip",):
        assert ext.get(path).status_code == 403
    for path, data in (
        ("/settings/restore", {"confirm": "1"}),
        ("/settings/reset", {"confirm": "RESET"}),
        ("/settings/theme", {"theme": "custom-dark"}),
        ("/settings/accent", {"accent": "#ff0000"}),
        ("/settings/units", {"units": "us"}),
        ("/settings/language", {"language": "de"}),
        ("/settings/map", {"enabled": "1"}),
        ("/settings/external-url", {"url": "https://x.example.com"}),
    ):
        assert ext.post(path, data=data).status_code == 403, path
    assert ext.get("/settings/design").status_code == 200  # reading the page is fine
    ext.post("/logout")
    ext.post("/login", data={"username": "admin", "password": PW, "next": "/"})
    assert ext.get("/settings/backup.zip").status_code == 200  # the administrator can


def test_even_the_refusals_carry_the_security_headers(client):
    for r in (client.get("/api/v1"), client.get("/definitely-not-a-page")):
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["referrer-policy"] == "same-origin"
        assert "default-src 'self'" in r.headers["content-security-policy"]


def test_a_device_can_be_registered_for_web_push_over_the_port(ing, ext, monkeypatch):
    """The whole way a phone takes: server key, then the device (an Apple-style subscription), then the card shows it."""
    from carassistant import ha

    monkeypatch.setattr(ha, "network_port", lambda: (True, 8321))
    make_admin(ing)
    assert ext.post("/login", data={"username": "admin", "password": PW, "next": "/"}).status_code == 303
    assert ext.post("/settings/external-url", data={"host": "car.example.com"}).status_code == 303
    r = ext.get("/push/key")
    assert r.status_code == 200 and r.json()["ok"] and len(r.json()["key"]) >= 80
    sub = {
        "endpoint": "https://web.push.apple.com/QMyTokenForTheTestDeviceOnly0123456789abcdefghijklmnopqrstuvwxyz",
        "keys": {
            "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM",
            "auth": "tBHItJI5svbpez7KI4CCXg",
        },
    }
    from tests.test_web import create_vehicle, slug

    one, two = create_vehicle(ing, "Push One"), create_vehicle(ing, "Push Two")
    r = ext.post("/push/subscribe", json={"sub": sub, "label": "Pocket", "vehicle": one})  # switched on for ONE car, on its Car tab
    assert r.status_code == 200 and r.json()["ok"], r.text
    user = ext.get("/settings/user").text
    assert "Pocket" in user and "Push One" in user and 'id="push-on"' not in user  # the person's overview; switching on happens per car
    car_tab = ext.get(f"/settings/car?car={slug(one)}").text
    assert 'id="push-on"' in car_tab and f'data-car="{one}"' in car_tab and "Pocket" in car_tab
    assert (
        "Pocket" not in ext.get(f"/settings/car?car={slug(two)}").text.split('id="push-box"')[1].split("</div>")[0]
    )  # not for the other car
    ask = {"endpoint": sub["endpoint"], "vehicle": one}
    assert ext.post("/push/status", json=ask).json()["on"] is True
    assert ext.post("/push/status", json={**ask, "vehicle": two}).json()["on"] is False
    assert ext.post("/push/subscribe", json={"sub": sub, "label": "Pocket", "vehicle": two}).json()[
        "ok"
    ]  # the same device for a second car
    assert ext.post("/push/status", json={**ask, "vehicle": two}).json()["on"] is True
    assert ext.post("/push/unsubscribe", json={**ask}).json()["remaining"] == 1  # off for one car: still serves the other
    assert ext.post("/push/unsubscribe", json={**ask, "vehicle": two}).json()["remaining"] == 0  # no car left: the device is gone
    assert "Pocket" not in ext.get("/settings/user").text
