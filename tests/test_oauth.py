"""Logging in with an account (``type: "oauth"`` step, carassistant/oauth.py): the manifest check, the whole login against a made-up provider, the way back,
the renewal and what a plugin gets through the Plugin API - and what must never happen (a foreign or old state, a private address, a token in a log)."""

import html
import json
import re
import urllib.parse

import pytest
from tests.test_web import create_vehicle, slug

from carassistant import addons, config, db, oauth, vault

SPEC = {
    "authorize_url": "https://login.example.com/oauth/authorize",
    "token_url": "https://login.example.com/oauth/token",
    "scopes": ["offline_access", "read"],
    "client_id_setting": "client_id",
    "client_secret_setting": "client_secret",
    "redirect": "paste",
    "redirect_uri": "https://localhost/callback",
}
TYPES = {"client_id": "text", "client_secret": "password"}


def manifest(spec=None, **extra):
    base = {
        "id": "oauth-demo",
        "kind": "plugin",
        "name": "OAuth demo",
        "version": "1",
        "settings": [
            {"key": "client_id", "type": "text", "label": "Client ID"},
            {"key": "client_secret", "type": "password", "label": "Client secret"},
        ],
        "setup": {
            "flow": [
                {"id": "connect", "type": "oauth", "title": "Log in", "oauth": spec or SPEC},
                {"id": "done", "type": "text", "title": "Done", "text": "Ready."},
            ]
        },
    }
    return {**base, **extra}


def test_the_manifest_of_an_oauth_step_is_checked():
    good, why = addons.clean_oauth(SPEC, TYPES)
    assert why == "" and good["pkce"] is True and good["client_auth"] == "post" and good["scopes"] == ["offline_access", "read"]
    assert good["client_id_setting"] == "client_id" and good["client_secret_setting"] == "client_secret" and good["redirect"] == "paste"

    def bad(**change):
        spec = {**SPEC, **change}
        return addons.clean_oauth({k: v for k, v in spec.items() if v is not None}, TYPES)

    for change in (
        {"authorize_url": "http://login.example.com/authorize"},  # not https
        {"token_url": "https://127.0.0.1/token"},  # an IP number
        {"token_url": "https://localhost/token"},  # no dot: not a name on the internet
        {"authorize_url": "https://user:pw@login.example.com/a"},  # a log-in inside the address
        {"token_url": "https://login.example.com/t token"},  # a space
        {"authorize_url": None},
        {"client_id_setting": None},  # no client at all
        {"client_id_setting": "nothing"},
        {"client_secret_setting": "client_id"},  # not a password setting
        {"redirect_uri": None},  # ``paste`` needs the address the provider sends the person to
        {"redirect_uri": "http://example.com/cb"},  # http only for localhost
    ):
        assert bad(**change)[0] is None, change
    assert addons.clean_oauth("nonsense", TYPES)[0] is None
    fixed, _ = addons.clean_oauth(
        {**SPEC, "client_id": "abc", "client_id_setting": None, "redirect": "app", "redirect_uri": None, "client_auth": "basic"}, TYPES
    )
    assert (
        fixed["client_id"] == "abc" and "client_id_setting" not in fixed and fixed["redirect"] == "app" and fixed["client_auth"] == "basic"
    )
    cleaned, _ = addons.clean_oauth(
        {
            **SPEC,
            "scopes": ["ok", "a b", 'x"y', "z" * 200, 5],
            "pkce": False,
            "extra": {"audience": "car", "state": "x", "Bad": "y", "prompt": ""},
        },
        TYPES,
    )
    assert (
        cleaned["scopes"] == ["ok"] and cleaned["pkce"] is False and cleaned["extra"] == {"audience": "car"}
    )  # what the request carries itself cannot be overridden
    # a package whose oauth step is unusable loses that step and nothing else
    got = addons.parse_package(json.dumps(manifest({**SPEC, "token_url": "http://x.example.com/t"})).encode())
    assert [s["id"] for s in got["setup"]["flow"]] == ["done"]


def test_a_pasted_address_is_read_the_ways_people_paste_it():
    read = oauth.parse_pasted
    assert read("https://localhost/callback?code=abc&state=xyz") == ("abc", "xyz", "")
    assert read("code=abc&state=xyz") == ("abc", "xyz", "")
    assert read("?code=abc&state=xyz") == ("abc", "xyz", "")
    assert read("https://localhost/callback#code=abc&state=xyz") == ("abc", "xyz", "")  # some providers answer after the #
    assert read("https://localhost/callback?error=access_denied&state=xyz") == ("", "xyz", "access_denied")
    assert read("abc123") == ("abc123", "", "")  # a bare code
    assert read("https://localhost/callback") == ("", "", "")  # an address without a code is no code
    assert read("   ") == ("", "", "") and read("two words") == ("", "", "")


class Provider:
    """A made-up provider: answers the token requests of the app and notes them."""

    def __init__(self):
        self.calls: list[dict] = []
        self.count = 0
        self.reply = None  # a function (form) -> (status, body) that takes over
        self.route = None  # a function (url, form) -> (status, body) or None, asked first

    def send(self, url, body, headers):
        form = {k: v[0] for k, v in urllib.parse.parse_qs(body.decode()).items()}
        self.calls.append({"url": url, "form": form, "headers": headers})
        if self.route and (got := self.route(url, form)):
            return got
        if self.reply:
            return self.reply(form)
        self.count += 1
        if form["grant_type"] == "authorization_code":
            return 200, json.dumps(
                {"access_token": f"AT{self.count}", "refresh_token": f"RT{self.count}", "expires_in": 3600, "scope": "read"}
            ).encode()
        return 200, json.dumps({"access_token": f"AT{self.count}", "expires_in": 3600}).encode()  # a renewal that keeps the refresh token


@pytest.fixture()
def provider(monkeypatch):
    fake = Provider()
    monkeypatch.setattr(oauth, "_send", fake.send)
    monkeypatch.setattr(oauth, "_public_host", lambda host: True)
    oauth._renewed.clear()
    return fake


def _install(client, spec=None):
    vid = create_vehicle(client)
    with db.tx() as conn:
        source = conn.execute("SELECT id FROM sources LIMIT 1").fetchone()["id"]
        m = addons.parse_package(json.dumps(manifest(spec)).encode())
        pk = addons.add(conn, vid, m, source, None)
        conn.execute(
            "UPDATE vehicle_addons SET active = 1, settings = ? WHERE id = ?",
            (json.dumps(addons._sealed(m, {"client_id": "cid-1", "client_secret": "shh-secret"})), pk),
        )
        token = addons.new_token(conn, vid, addons.get(conn, vid, pk))
    return vid, pk, token


def _link(client, vid, pk):
    """The address of the login the page offers (it opens in a new tab), as a dict of its query."""
    page = client.get(f"/v/{slug(vid)}/integrations/{pk}/guide").text
    found = re.search(r'href="(https://login\.example\.com/oauth/authorize\?[^"]+)"', page)
    assert found, page
    return {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(html.unescape(found.group(1))).query).items()}, page


def _api(client, vid, token, **query):
    return client.get(f"/api/v1/vehicles/{vid}/connection", params=query, headers={"Authorization": f"Bearer {token}"})


def test_a_login_by_pasted_address_end_to_end_and_the_plugin_gets_the_token(client, provider):
    vid, pk, token = _install(client)
    base = f"/v/{slug(vid)}/integrations/{pk}/guide"
    page = client.get(base).text
    assert "Not logged in yet." in page and "login.example.com" in page and 'name="do" value="start"' in page
    assert _api(client, vid, token).status_code == 404 and _api(client, vid, token).json()["error"] == "not_connected"

    started = client.post(base + "/flow", data={"step": "1", "do": "start"})
    assert started.status_code == 303 and started.headers["location"].endswith(
        "guide?step=1"
    )  # back to the page, which now shows the address
    query, page = _link(client, vid, pk)
    assert query["response_type"] == "code" and query["client_id"] == "cid-1" and query["redirect_uri"] == "https://localhost/callback"
    assert query["scope"] == "offline_access read" and query["code_challenge_method"] == "S256" and len(query["state"]) >= 24
    assert 'target="_blank"' in page and 'name="pasted"' in page  # a login page cannot live in the frame of the app: a new tab
    assert "shh-secret" not in page  # the client secret is never on a page

    wrong = client.post(
        base + "/flow", data={"step": "1", "do": "paste", "pasted": "https://localhost/callback?code=abc&state=not-the-state"}
    )
    assert (
        wrong.status_code == 422 and "not valid any more" in wrong.text and provider.calls == []
    )  # nothing is asked of the provider for a foreign state
    assert _link(client, vid, pk)[0] == query  # and the login that was begun is still there
    done = client.post(
        base + "/flow", data={"step": "1", "do": "paste", "pasted": f"https://localhost/callback?code=the-code&state={query['state']}"}
    )
    assert done.status_code == 200 and "Connected." in done.text
    call = provider.calls[0]
    assert call["url"] == "https://login.example.com/oauth/token"
    assert (
        call["form"]["grant_type"] == "authorization_code"
        and call["form"]["code"] == "the-code"
        and call["form"]["redirect_uri"] == "https://localhost/callback"
    )
    assert call["form"]["client_id"] == "cid-1" and call["form"]["client_secret"] == "shh-secret"
    assert (
        oauth._challenge(call["form"]["code_verifier"]) == query["code_challenge"]
    )  # PKCE: the verifier belongs to the challenge of the request

    with db.tx() as conn:
        row = conn.execute("SELECT * FROM connections").fetchone()
        assert (
            row["plugin"] == "oauth-demo" and row["state"] == "ok" and "AT1" not in row["secret"] and "RT1" not in row["secret"]
        )  # sealed at rest
        assert conn.execute("SELECT COUNT(*) AS n FROM oauth_pending").fetchone()["n"] == 0
        logs = " ".join(r["message"] for r in conn.execute("SELECT message FROM vehicle_logs"))
    assert "AT1" not in logs and "RT1" not in logs and "the-code" not in logs

    got = _api(client, vid, token)
    assert got.status_code == 200 and got.headers["cache-control"] == "no-store"
    body = got.json()
    assert (
        body["access_token"] == "AT1" and body["token_type"] == "Bearer" and body["scope"] == "read" and 3500 < body["expires_in"] <= 3600
    )
    assert "refresh_token" not in body  # a plugin has no use for it
    assert len(provider.calls) == 1  # still valid: no request to the provider
    assert client.post(base + "/flow", data={"step": "1", "do": "next"}).status_code == 200  # on to the next step now

    # it ends: the app renews with the refresh token, keeps the one it has when the provider sends none
    with db.tx() as conn:
        conn.execute("UPDATE connections SET expires_at = '2000-01-01T00:00:00Z'")
    again = _api(client, vid, token).json()
    assert again["access_token"] == "AT2" and provider.calls[1]["form"] == {
        "grant_type": "refresh_token",
        "refresh_token": "RT1",
        "client_id": "cid-1",
        "client_secret": "shh-secret",
    }
    assert _api(client, vid, token).json()["access_token"] == "AT2" and len(provider.calls) == 2
    # the provider refused the token the plugin had: it says so (renew) and gets a new one - but not more often than every half minute
    oauth._renewed.clear()  # (the renewal a moment ago counts as the freshest there is)
    assert (
        _api(client, vid, token, renew=1).json()["access_token"] == "AT3"
        and _api(client, vid, token, renew=1).json()["access_token"] == "AT3"
    )
    assert len(provider.calls) == 3

    # the refresh token is no good any more: the person has to log in again - the page, the tile and the Plugin API say so
    provider.reply = lambda form: (400, json.dumps({"error": "invalid_grant", "error_description": "Token revoked"}).encode())
    with db.tx() as conn:
        conn.execute("UPDATE connections SET expires_at = '2000-01-01T00:00:00Z'")
    refused = _api(client, vid, token)
    assert refused.status_code == 409 and refused.json()["error"] == "login_required"
    assert "log in again" in client.get(base).text and 'name="do" value="start"' in client.get(base).text
    assert client.post(base + "/flow", data={"step": "1", "do": "next"}).status_code == 409  # no way past a login that has expired

    # logging in again puts the new tokens into the same connection; disconnecting removes it with its tokens
    provider.reply = None
    client.post(base + "/flow", data={"step": "1", "do": "start"})
    query, _ = _link(client, vid, pk)
    client.post(base + "/flow", data={"step": "1", "do": "paste", "pasted": f"code=second&state={query['state']}"})
    assert _api(client, vid, token).json()["access_token"].startswith("AT")
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM connections").fetchone()["n"] == 1
    client.post(base + "/flow", data={"step": "1", "do": "forget"})
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM connections").fetchone()["n"] == 0
    assert _api(client, vid, token).status_code == 404


def test_the_way_back_of_a_login_under_the_https_address_of_the_app(client, provider, monkeypatch):
    monkeypatch.setattr(config, "external_url", lambda: "https://car.example.com")
    spec = {k: v for k, v in SPEC.items() if k != "redirect_uri"} | {"redirect": "app"}
    vid, pk, token = _install(client, spec)
    base = f"/v/{slug(vid)}/integrations/{pk}/guide"
    assert "https://car.example.com/oauth/callback" in client.get(base).text  # what to register at the provider
    client.post(base + "/flow", data={"step": "1", "do": "start"})
    query, page = _link(client, vid, pk)
    assert (
        query["redirect_uri"] == "https://car.example.com/oauth/callback" and 'data-autoreload="4"' in page and 'name="pasted"' not in page
    )

    # the browser comes back - nobody is signed in at that moment, and the page must still not tell more than it has to
    back = client.get("/oauth/callback", params={"code": "c1", "state": query["state"]})
    assert back.status_code == 200 and "Logged in." in back.text and "AT1" not in back.text and "c1" not in back.text
    assert provider.calls[0]["form"]["redirect_uri"] == "https://car.example.com/oauth/callback"
    assert _api(client, vid, token).json()["access_token"] == "AT1"
    assert client.get(base).text.count("Connected.") >= 1
    # used once: the same address again, a made-up one and one without anything find nothing
    for params in ({"code": "c1", "state": query["state"]}, {"code": "c", "state": "made-up"}, {"code": "c"}, {}):
        assert client.get("/oauth/callback", params=params).status_code == 400
    assert len(provider.calls) == 1

    # the person said no at the provider: the login ends, a line in the log of the plugin says why
    client.post(base + "/flow", data={"step": "1", "do": "start"})
    query, _ = _link(client, vid, pk)
    denied = client.get("/oauth/callback", params={"error": "access_denied", "error_description": "No thanks", "state": query["state"]})
    assert denied.status_code == 400 and "No thanks" not in denied.text
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM oauth_pending").fetchone()["n"] == 0
        assert any("No thanks" in r["message"] for r in conn.execute("SELECT message FROM vehicle_logs WHERE level = 'warn'"))
    # without the https address of the app there is no way back to register
    monkeypatch.setattr(config, "external_url", lambda: "")
    assert client.post(base + "/flow", data={"step": "1", "do": "start"}).status_code == 409


def test_a_login_of_one_step_cannot_be_finished_on_another(client, provider):
    vid, pk, _ = _install(client)
    base = f"/v/{slug(vid)}/integrations/{pk}/guide"
    client.post(base + "/flow", data={"step": "1", "do": "start"})
    query, _ = _link(client, vid, pk)
    with db.tx() as conn:
        source = conn.execute("SELECT id FROM sources LIMIT 1").fetchone()["id"]
        other = addons.add(conn, vid, addons.parse_package(json.dumps(manifest(id="oauth-other")).encode()), source, None)
        conn.execute("UPDATE vehicle_addons SET active = 1 WHERE id = ?", (other,))
    # the state of the first install pasted on the page of the second one
    stolen = client.post(
        f"/v/{slug(vid)}/integrations/{other}/guide/flow", data={"step": "1", "do": "paste", "pasted": f"code=x&state={query['state']}"}
    )
    assert stolen.status_code == 422 and provider.calls == []
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM connections").fetchone()["n"] == 0


def test_a_request_to_a_provider_goes_only_to_a_public_https_address(monkeypatch):
    called = []
    monkeypatch.setattr(oauth, "_send", lambda *a: called.append(a) or (200, b"{}"))
    for url in ("http://login.example.com/token", "https://127.0.0.1/token", "https://localhost/token", "https://192.168.1.5/token"):
        with pytest.raises(oauth.OAuthError) as error:
            oauth._post(url, {"a": "b"})
        assert error.value.key == "err.oauth_host", url
    assert called == []  # not even tried


def test_what_a_provider_answers_is_read_with_care(monkeypatch):
    monkeypatch.setattr(oauth, "_public_host", lambda host: True)
    url = "https://login.example.com/token"

    def answer(status, body):
        monkeypatch.setattr(oauth, "_send", lambda *a: (status, body))
        return lambda: oauth._post(url, {})

    assert answer(200, b'{"access_token": "x"}')() == {"access_token": "x"}
    for status, body, key in (
        (200, b"not json", "err.oauth_bad"),
        (200, b"[1, 2]", "err.oauth_bad"),
        (200, b"x" * (oauth.LIMIT + 1), "err.oauth_big"),
        (400, b'{"error": "invalid_grant", "error_description": "Gone\\nfor good"}', "err.oauth_refused"),
        (200, b'{"error": "server_error"}', "err.oauth_refused"),
    ):
        with pytest.raises(oauth.OAuthError) as error:
            answer(status, body)()
        assert error.value.key == key, body[:30]
    with pytest.raises(oauth.ProviderRefused) as refused:
        answer(400, b'{"error": "invalid_grant", "error_description": "Gone\\nfor good"}')()
    assert refused.value.code == "invalid_grant" and "\n" not in refused.value.detail  # one line, cleaned
    # a token answer without an access token is no login
    with pytest.raises(oauth.OAuthError):
        oauth._tokens({"refresh_token": "r"})
    kept = oauth._tokens({"access_token": "a", "refresh_token": "r", "expires_in": "3600", "token_type": "bearer"})
    assert kept["expires_at"] and kept["token_type"] == "bearer" and "expires_in" not in kept
    assert "expires_at" not in oauth._tokens({"access_token": "a"})  # no end named: it counts as good until the provider refuses it


def test_the_request_leaves_with_basic_authentication_when_the_package_says_so(client, provider):
    spec = {**SPEC, "client_auth": "basic"}
    vid, pk, _ = _install(client, spec)
    base = f"/v/{slug(vid)}/integrations/{pk}/guide"
    client.post(base + "/flow", data={"step": "1", "do": "start"})
    query, _ = _link(client, vid, pk)
    client.post(base + "/flow", data={"step": "1", "do": "paste", "pasted": f"code=c&state={query['state']}"})
    call = provider.calls[0]
    assert call["headers"]["Authorization"].startswith("Basic ") and "client_secret" not in call["form"] and "client_id" not in call["form"]


def test_installs_that_share_a_connection_renew_it_once_for_all(client, provider):
    """Two cars of one account: the second install is linked to the connection of the first - one set of tokens, renewed once."""
    vid, pk, _token = _install(client)
    base = f"/v/{slug(vid)}/integrations/{pk}/guide"
    client.post(base + "/flow", data={"step": "1", "do": "start"})
    query, _ = _link(client, vid, pk)
    client.post(base + "/flow", data={"step": "1", "do": "paste", "pasted": f"code=c&state={query['state']}"})
    second = create_vehicle(client, "Second Car")
    with db.tx() as conn:
        cid = conn.execute("SELECT id FROM connections").fetchone()["id"]
        source = conn.execute("SELECT id FROM sources LIMIT 1").fetchone()["id"]
        other = addons.add(conn, second, addons.parse_package(json.dumps(manifest()).encode()), source, None)
        conn.execute(
            "UPDATE vehicle_addons SET active = 1, settings = ? WHERE id = ?",
            (json.dumps(addons._sealed(manifest(), {"client_id": "cid-1", "client_secret": "shh-secret"})), other),
        )
        conn.execute("INSERT INTO connection_links(addon_pk, step, connection_id) VALUES(?, 'connect', ?)", (other, cid))
        conn.execute("UPDATE connections SET expires_at = '2000-01-01T00:00:00Z'")
        assert oauth.status(conn, other, "connect")["connected"] and not oauth.login_needed(conn, other)
    assert oauth.fresh(cid)["access_token"] == "AT2" and oauth.fresh(cid)["access_token"] == "AT2"  # one renewal for both
    assert len(provider.calls) == 2
    # a login that has expired shows at BOTH installs
    provider.reply = lambda form: (400, json.dumps({"error": "invalid_grant"}).encode())
    with db.tx() as conn:
        conn.execute("UPDATE connections SET expires_at = '2000-01-01T00:00:00Z'")
    with pytest.raises(oauth.LoginRequired):
        oauth.fresh(cid)
    with db.tx() as conn:
        assert oauth.login_needed(conn, pk) and oauth.login_needed(conn, other)
    # when one install lets go, the other keeps the connection; when the last lets go, the tokens are deleted
    with db.tx() as conn:
        oauth.forget(conn, pk)
        assert conn.execute("SELECT COUNT(*) AS n FROM connections").fetchone()["n"] == 1
        oauth.forget(conn, other)
        assert conn.execute("SELECT COUNT(*) AS n FROM connections").fetchone()["n"] == 0


def _connected(client, provider):
    """A car with the plugin logged in (tokens AT1 / RT1); returns (vehicle id, install, plugin token)."""
    vid, pk, token = _install(client)
    base = f"/v/{slug(vid)}/integrations/{pk}/guide"
    client.post(base + "/flow", data={"step": "1", "do": "start"})
    query, _ = _link(client, vid, pk)
    client.post(base + "/flow", data={"step": "1", "do": "paste", "pasted": f"code=c&state={query['state']}"})
    return vid, pk, token


def test_the_tokens_of_a_login_travel_in_the_backup_of_a_car_only_with_a_passphrase(client, provider):
    import io
    import zipfile

    from carassistant import vehiclebackup

    vid, _pk, _token = _connected(client, provider)
    phrase = "a long enough passphrase"
    with db.tx() as conn:
        plain = vehiclebackup.export(conn, vid)
        sealed = vehiclebackup.export(conn, vid, passphrase=phrase)
    for raw in (plain, sealed):
        for name in zipfile.ZipFile(io.BytesIO(raw)).namelist():
            if name != "secrets.enc":
                assert b"AT1" not in zipfile.ZipFile(io.BytesIO(raw)).read(name) and b"RT1" not in zipfile.ZipFile(io.BytesIO(raw)).read(
                    name
                )
    assert b"AT1" not in sealed  # even the block is not readable
    with db.tx() as conn:
        copy = vehiclebackup.restore(conn, plain)  # no tokens in it: the plugin is there and waits for the login
    with db.tx() as conn:
        addon = addons.list_for(conn, copy)[0]
        assert addon["m"]["id"] == "oauth-demo" and not oauth.status(conn, addon["id"], "connect")["connected"]
    with db.tx() as conn:
        again = vehiclebackup.restore(conn, sealed, phrase)  # with the passphrase the login comes back as it was
    with db.tx() as conn:
        back = addons.list_for(conn, again)[0]
        status = oauth.status(conn, back["id"], "connect")
        assert status["connected"] and status["state"] == "ok"
        assert conn.execute("SELECT COUNT(*) AS n FROM connections").fetchone()["n"] == 2  # the old car's and the copy's: not shared
    assert oauth.fresh(status["id"])["access_token"] == "AT1"


def test_the_tokens_of_a_login_travel_in_the_backup_of_the_system_only_with_a_passphrase(client, provider):
    import io
    import sqlite3
    import tempfile
    import zipfile
    from pathlib import Path

    from carassistant import backup

    vid, _pk, token = _connected(client, provider)
    sealed = backup.create(passphrase="a long enough passphrase")
    plain = backup.create()
    with tempfile.TemporaryDirectory() as tmp:
        zipfile.ZipFile(io.BytesIO(sealed)).extract("carassistant.db", tmp)
        copy = sqlite3.connect(Path(tmp) / "carassistant.db")
        assert copy.execute("SELECT secret, state FROM connections").fetchone() == ("", "login_required")  # the copy holds no token
        copy.close()
    assert b"AT1" not in sealed
    backup.restore(sealed, "a long enough passphrase")
    assert _api(client, vid, token).json()["access_token"] == "AT1"  # the login came back as it was
    with db.tx() as conn:
        conn.execute(
            "UPDATE connections SET secret = ?", (vault.PREFIX + "bm90LXRoaXMta2V5",)
        )  # sealed by a key that is not here (a backup without a passphrase, restored elsewhere)
    assert _api(client, vid, token).status_code == 409 and _api(client, vid, token).json()["error"] == "login_required"
    assert "The login has expired" in client.get(f"/v/{slug(vid)}/plugins").text  # and the tile of the plugin says so
    del plain


def test_the_page_of_a_package_names_both_hosts_of_a_login_before_it_is_installed():
    from carassistant import i18n, interfaces

    m = addons.parse_package(json.dumps(manifest({**SPEC, "token_url": "https://tokens.example.org/exchange"})).encode())
    rows = interfaces.preview(m, i18n.translator("en"))["rows"]["brings"]
    login = next(r for r in rows if "Log in with an account" in r["name"])
    assert "login.example.com" in login["name"] and "tokens.example.org" in login["note"]


def test_the_checker_says_why_a_login_step_was_dropped(tmp_path):
    import check_plugin

    folder = tmp_path / "plugins" / "oauth-demo"
    folder.mkdir(parents=True)
    bad = manifest({**SPEC, "token_url": "http://login.example.com/token"}, description="d", icon="wrench")
    (folder / "plugin.json").write_text(json.dumps(bad), encoding="utf-8")
    _errors, notes = check_plugin.check(folder)
    assert any("Step 'connect' (type oauth) was dropped: 'token_url' must be an https address" in n for n in notes), notes
    (folder / "plugin.json").write_text(json.dumps(manifest(description="d", icon="wrench")), encoding="utf-8")
    assert not any("oauth" in n and "dropped" in n for n in check_plugin.check(folder)[1])


def test_the_request_really_leaves_as_a_form_post_over_https_and_a_redirect_is_not_followed(tmp_path, monkeypatch):
    """The one place that talks to a provider, against a real local https server (a certificate made for the test)."""
    import base64
    import http.server
    import urllib.request

    from tests.tls_helper import https_server

    seen: list[tuple] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            seen.append((self.path, dict(self.headers), body))
            if self.path == "/elsewhere":
                self.send_response(302)
                self.send_header("Location", f"https://127.0.0.1:{self.server.server_address[1]}/token")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            payload = b'{"access_token": "T", "expires_in": 60}' if self.path == "/token" else b'{"error": "invalid_grant"}'
            self.send_response(200 if self.path == "/token" else 400)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *a):
            pass

    monkeypatch.setattr(oauth, "_public_host", lambda host: True)
    with https_server(tmp_path, Handler) as (base, trust):
        monkeypatch.setattr(
            oauth, "_opener", lambda: urllib.request.build_opener(oauth._NoRedirect, urllib.request.HTTPSHandler(context=trust))
        )
        assert oauth._post(f"{base}/token", {"grant_type": "authorization_code", "code": "a b&c"}, ("id", "se cret")) == {
            "access_token": "T",
            "expires_in": 60,
        }
        path, headers, body = seen[0]
        assert (
            path == "/token"
            and headers["Content-Type"] == "application/x-www-form-urlencoded"
            and body == b"grant_type=authorization_code&code=a+b%26c"
        )
        assert (
            headers["Authorization"] == "Basic " + base64.b64encode(b"id:se%20cret").decode()
        )  # (both parts are form-encoded first, RFC 6749)
        with pytest.raises(oauth.ProviderRefused):
            oauth._post(f"{base}/refused", {})  # an error answer is read, not hidden
        with pytest.raises(oauth.OAuthError):
            oauth._post(f"{base}/elsewhere", {})  # a redirect is no answer ...
        assert [p for p, _h, _b in seen] == ["/token", "/refused", "/elsewhere"]  # ... and was not followed
    with pytest.raises(oauth.OAuthError) as down:
        oauth._post(f"{base}/token", {})  # nobody is listening any more
    assert down.value.key == "err.oauth_net"


def _install_on(vid, client_id="cid-1"):
    """The same package on another car (with the app registered at the provider under ``client_id``); returns (install, plugin token)."""
    with db.tx() as conn:
        source = conn.execute("SELECT id FROM sources LIMIT 1").fetchone()["id"]
        m = addons.parse_package(json.dumps(manifest()).encode())
        pk = addons.add(conn, vid, m, source, None)
        conn.execute(
            "UPDATE vehicle_addons SET active = 1, settings = ? WHERE id = ?",
            (json.dumps(addons._sealed(m, {"client_id": client_id, "client_secret": "shh-secret"})), pk),
        )
        return pk, addons.new_token(conn, vid, addons.get(conn, vid, pk))


def test_a_second_car_can_use_the_login_of_the_first_and_only_of_the_same_app(client, provider):
    vid, pk, token = _connected(client, provider)
    with db.tx() as conn:
        cid = conn.execute("SELECT id FROM connections").fetchone()["id"]
    second = create_vehicle(client, "Second Car")
    other, other_token = _install_on(second)
    base = f"/v/{slug(second)}/integrations/{other}/guide"
    page = client.get(base).text
    assert "Use the login of My Car" in page and f'name="use" value="{cid}"' in page  # the login of the first car is offered
    assert _api(client, second, other_token).status_code == 404  # but not used before the person says so
    taken = client.post(base + "/flow", data={"step": "1", "use": str(cid)})
    assert taken.status_code == 303
    page = client.get(base).text
    assert "Connected." in page and "The same login is used by: My Car." in page and "Stop using the shared login" in page
    assert _api(client, second, other_token).json()["access_token"] == "AT1" and _api(client, vid, token).json()["access_token"] == "AT1"
    assert len(provider.calls) == 1  # no second login at the provider
    assert "The same login is used by: Second Car." in client.get(f"/v/{slug(vid)}/integrations/{pk}/guide").text
    # a car whose app is registered under another client id gets no offer, and cannot take the login by a forged number
    third = create_vehicle(client, "Third Car")
    stranger, _t = _install_on(third, client_id="cid-other")
    base3 = f"/v/{slug(third)}/integrations/{stranger}/guide"
    assert 'name="use"' not in client.get(base3).text
    assert client.post(base3 + "/flow", data={"step": "1", "use": str(cid)}).status_code == 422
    # the second car stops sharing: it has no login any more, the first keeps its own
    client.post(base + "/flow", data={"step": "1", "do": "forget"})
    assert _api(client, second, other_token).status_code == 404 and _api(client, vid, token).json()["access_token"] == "AT1"
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM connections").fetchone()["n"] == 1


DEVICE_SPEC = {
    "grant": "device",
    "device_url": "https://login.example.com/oauth/device",
    "token_url": "https://login.example.com/oauth/token",
    "scopes": ["read"],
    "client_id_setting": "client_id",
}


def _due():
    """The provider's pause is over (the page would have waited for it)."""
    with db.tx() as conn:
        row = conn.execute("SELECT state, extra FROM oauth_pending").fetchone()
        extra = json.loads(vault.decrypt(row["extra"]))
        extra["next"] = "2000-01-01T00:00:00Z"
        conn.execute("UPDATE oauth_pending SET extra = ? WHERE state = ?", (vault.encrypt(json.dumps(extra)), row["state"]))


def test_a_login_by_code_typed_at_the_provider(client, provider):
    spec, why = addons.clean_oauth(DEVICE_SPEC, TYPES)
    assert why == "" and spec["grant"] == "device" and "authorize_url" not in spec and "redirect" not in spec  # no way back to arrange
    assert addons.clean_oauth({**DEVICE_SPEC, "device_url": "http://login.example.com/d"}, TYPES)[0] is None
    assert addons.clean_oauth({k: v for k, v in DEVICE_SPEC.items() if k != "device_url"}, TYPES)[0] is None

    answers = iter(["authorization_pending", "slow_down", "ok"])

    def route(url, form):
        if url.endswith("/device"):
            return 200, json.dumps(
                {
                    "device_code": "DC1",
                    "user_code": "WDJB-MJHT",
                    "verification_uri": "https://login.example.com/activate",
                    "interval": 5,
                    "expires_in": 600,
                }
            ).encode()
        if form.get("grant_type") == oauth.DEVICE_GRANT:
            step = next(answers)
            if step == "ok":
                return 200, json.dumps({"access_token": "DT1", "refresh_token": "DR1", "expires_in": 3600}).encode()
            return 400, json.dumps({"error": step}).encode()
        return None

    provider.route = route
    vid, pk, token = _install(client, DEVICE_SPEC)
    base = f"/v/{slug(vid)}/integrations/{pk}/guide"
    page = client.get(base).text
    assert (
        "Not logged in yet." in page and "login.example.com" in page and "redirect address of your app" not in page
    )  # nothing to register: no way back
    started = client.post(base + "/flow", data={"step": "1", "do": "start"})
    assert started.status_code == 303
    assert provider.calls[0]["url"].endswith("/device") and provider.calls[0]["form"] == {"scope": "read", "client_id": "cid-1"}
    page = client.get(base).text  # the page shows the code and the address; it did not ask yet - the provider's pause is not over
    assert (
        "WDJB-MJHT" in page
        and 'href="https://login.example.com/activate"' in page
        and "data-autoreload" in page
        and len(provider.calls) == 1
    )
    _due()
    client.get(base)  # pending: asked once, will ask again later
    assert len(provider.calls) == 2 and provider.calls[1]["form"] == {
        "grant_type": oauth.DEVICE_GRANT,
        "device_code": "DC1",
        "client_id": "cid-1",
    }
    client.get(base)
    assert len(provider.calls) == 2  # the pause is not over: the page does not ask again, however often it is loaded
    _due()
    client.get(base)  # slow down: the pause grows by five seconds
    with db.tx() as conn:
        extra = json.loads(vault.decrypt(conn.execute("SELECT extra FROM oauth_pending").fetchone()["extra"]))
    assert len(provider.calls) == 3 and extra["interval"] == 10
    _due()
    page = client.get(base).text  # the code was typed: the tokens are saved and the page says so
    assert "Connected." in page and "WDJB-MJHT" not in page
    assert _api(client, vid, token).json()["access_token"] == "DT1"
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM oauth_pending").fetchone()["n"] == 0


def test_a_login_by_code_ends_when_the_person_says_no_or_the_code_runs_out(client, provider):
    def route(url, form):
        if url.endswith("/device"):
            return 200, json.dumps(
                {"device_code": "DC", "user_code": "ABCD", "verification_uri": "https://login.example.com/activate"}
            ).encode()
        return 400, json.dumps({"error": reply[0], "error_description": "The person said no"}).encode()

    reply = ["access_denied"]
    provider.route = route
    vid, pk, token = _install(client, DEVICE_SPEC)
    base = f"/v/{slug(vid)}/integrations/{pk}/guide"
    client.post(base + "/flow", data={"step": "1", "do": "start"})
    _due()
    page = client.get(base).text
    assert "refused the login" in page and "The person said no" in page and "ABCD" not in page  # over: the page offers a new start
    assert 'name="do" value="start"' in page and _api(client, vid, token).status_code == 404
    client.post(base + "/flow", data={"step": "1", "do": "start"})
    reply[0] = "expired_token"
    _due()
    assert "not valid any more" in client.get(base).text
    # a code that ran out by the clock is gone, too
    client.post(base + "/flow", data={"step": "1", "do": "start"})
    with db.tx() as conn:
        row = conn.execute("SELECT state, extra FROM oauth_pending").fetchone()
        extra = json.loads(vault.decrypt(row["extra"]))
        extra["expires_at"] = "2000-01-01T00:00:00Z"
        conn.execute("UPDATE oauth_pending SET extra = ? WHERE state = ?", (vault.encrypt(json.dumps(extra)), row["state"]))
    assert "ABCD" not in client.get(base).text


def test_what_the_provider_sends_for_a_login_by_code_is_checked(client, provider):
    vid, pk, _token = _install(client, DEVICE_SPEC)
    base = f"/v/{slug(vid)}/integrations/{pk}/guide"
    for bad in (
        {"device_code": "DC", "user_code": "ABCD", "verification_uri": "javascript:alert(1)"},  # it is shown as a link: only plain https
        {"device_code": "DC", "user_code": "ABCD", "verification_uri": "http://login.example.com/a"},
        {"device_code": "DC", "user_code": "x" * 100, "verification_uri": "https://login.example.com/a"},
        {"user_code": "ABCD", "verification_uri": "https://login.example.com/a"},
    ):
        provider.route = lambda url, form, bad=bad: (200, json.dumps(bad).encode()) if url.endswith("/device") else None
        refused = client.post(base + "/flow", data={"step": "1", "do": "start"})
        assert refused.status_code == 422 and "could not be read" in refused.text, bad
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM oauth_pending").fetchone()["n"] == 0
