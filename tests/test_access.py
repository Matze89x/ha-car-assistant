import pytest
from fastapi.testclient import TestClient

from carassistant import accounts, db

PW = "a-long-password-12345"


def _client(host, headers=None):
    from carassistant import web

    return TestClient(
        web.app,
        client=(host, 5000),
        base_url="https://car.example.com",
        follow_redirects=False,
        headers={"Origin": "https://car.example.com", **(headers or {})},
    )


@pytest.fixture()
def direct(env, monkeypatch):
    monkeypatch.delenv("CARASSISTANT_DEV", raising=False)  # as on a real system
    return monkeypatch


def _user():
    with db.tx() as conn:
        accounts.create_user(conn, "owner", PW, "Owner", True)


def test_a_user_is_needed_for_direct_access(direct):
    page = _client("8.8.8.8").get("/")
    assert page.status_code == 403 and "locked until a user exists" in page.text  # no user: locked, with a friendly page
    _user()
    assert _client("8.8.8.8").get("/").status_code == 303  # a user exists: the login
    assert _client("192.168.1.20").get("/").status_code == 303
    assert _client("172.30.32.2").get("/").status_code != 403  # the Home Assistant panel (ingress) is never refused


def test_the_locked_page_is_a_designed_standalone_page(direct):
    page = _client("8.8.8.8").get("/")
    assert page.status_code == 403
    assert (
        "Locked until a user exists" in page.text and "<svg" in page.text and "linear-gradient" in page.text
    )  # logo and colours are inline
    assert "/static/" not in page.text.replace(
        "/static/favicon.svg", ""
    )  # no style or script of the app is needed to show it (only the icon)


def test_icons_are_reachable_when_nobody_is_signed_in_and_when_no_user_exists(direct):
    paths = (
        "/favicon.ico",
        "/apple-touch-icon.png",
        "/apple-touch-icon-precomposed.png",
        "/icon/180.png",
        "/icon/48.png",
        "/static/favicon.svg",
    )
    # no user yet: the page only says "locked", but the phone must still get its icons
    page = _client("8.8.8.8").get("/")
    assert (
        page.status_code == 403 and 'rel="apple-touch-icon"' in page.text and "favicon.svg" in page.text and "{_PAGE_CSS}" not in page.text
    )
    for path in paths:
        assert _client("8.8.8.8").get(path).status_code == 200, path
    assert _client("8.8.8.8").get("/v/1").status_code == 403  # everything else stays locked
    _user()  # a user exists but nobody is signed in: the icons are still served (not a redirect to the login)
    for path in paths:
        assert _client("8.8.8.8").get(path).status_code == 200, path
    # every page a visitor can see names its icons: the login, and an error page
    for url in ("/login", "/no-such-page"):
        html = _client("8.8.8.8").get(url).text
        assert 'rel="apple-touch-icon"' in html or url == "/no-such-page", url


def test_every_page_of_the_app_names_its_icons(client):
    for url in ("/vehicles", "/about", "/no-such-page"):
        html = client.get(url).text
        assert 'rel="apple-touch-icon"' in html and 'rel="icon"' in html, url
