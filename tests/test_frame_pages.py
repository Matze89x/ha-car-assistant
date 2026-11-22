import json

import pytest

from carassistant import addons, db, framehead, frametheme, navigation, pagemods, pluginsvc, proxy
from carassistant.addons import AddonError

SERVICE = {
    "entry": "app.py",
    "routes": [{"prefix": "/ext/editor/", "public": False}, {"prefix": "/ext/car/", "public": True}],
}


def _manifest(kind="plugin", **over):
    page = {"id": "editor", "kind": "frame", "title": "Editor", "route": "/ext/editor/", "icon": "settings"}
    data = {"id": "editor-pkg", "kind": kind, "name": "Editor", "version": "3", "service": SERVICE, "pages": [page], **over}
    return json.dumps(data).encode()


def test_a_frame_page_must_lie_under_a_non_public_route_of_the_own_service():
    ok = addons.parse_package(_manifest())
    page = ok["pages"][0]
    assert page["kind"] == "frame" and page["route"] == "/ext/editor/" and page["icon"] == "settings" and page["fields"] == []
    for route in ("/ext/other/", "/ext/car/", "/ext/editor/../x", "/ext//editor/", "ext/editor/", "/ext/editor/ x"):
        bad = {"id": "editor", "kind": "frame", "title": "x", "route": route}
        with pytest.raises(AddonError):
            addons.parse_package(_manifest(pages=[bad]))
    with pytest.raises(AddonError):  # a frame without a service of its own
        addons.parse_package(_manifest(service=None))


def test_the_approval_only_changes_for_packages_with_frames():
    without = {"service": {"entry": "app.py"}, "pages": []}
    assert addons.approval_fingerprint(without) == addons.approval_fingerprint({**without, "pages": [{"kind": "list", "id": "x"}]})
    with_frame = {**without, "pages": [{"kind": "frame", "id": "e", "route": "/ext/editor/"}]}
    moved = {**without, "pages": [{"kind": "frame", "id": "e", "route": "/ext/editor/two/"}]}
    assert addons.approval_fingerprint(with_frame) != addons.approval_fingerprint(without)
    assert addons.approval_fingerprint(with_frame) != addons.approval_fingerprint(moved)  # a new address needs a new approval


def _install_frame(vid, monkeypatch, running=True, kind="plugin"):
    manifest = addons.parse_package(_manifest(kind))
    with db.tx() as conn:
        conn.execute(
            "INSERT INTO vehicle_addons(vehicle_id, kind, addon_id, manifest, status, settings, active, created_at) "
            "VALUES(?, ?, 'editor-pkg', ?, 'configured', '{}', 1, '2026-01-01')",
            (vid, kind, json.dumps(manifest)),
        )
    monkeypatch.setattr(pluginsvc, "running", lambda pk: running)


def test_the_page_and_its_entry_exist_only_while_the_service_runs(client, monkeypatch):
    from tests.conftest import demo_car

    vid = demo_car(client)
    _install_frame(vid, monkeypatch, running=False)
    with db.tx() as conn:
        assert pagemods.active_modules(conn, vid) == [] and navigation.X + "editor-pkg" not in navigation.integration_pages(conn, vid)
    _install_frame_running = monkeypatch.setattr(pluginsvc, "running", lambda pk: True)
    assert _install_frame_running is None
    with db.tx() as conn:
        assert [m["addon_id"] for m in pagemods.active_modules(conn, vid)] == ["editor-pkg"]
        assert navigation.X + "editor-pkg" in navigation.integration_pages(conn, vid)
    r = client.get(f"/v/{vid}/m/editor-pkg", follow_redirects=False)  # no iframe: the page of the package IS the page
    where = r.headers["location"]
    assert r.status_code == 303 and where.startswith("/ext/editor/?lang=") and f"car={vid}" in where and "units=metric" in where
    assert "theme=default" in where and "frame-theme.css" in where and "frame-kit.css" in where and "tiles=" in where


def test_a_stopped_service_has_no_page(client, monkeypatch):
    from tests.conftest import demo_car

    vid = demo_car(client)
    _install_frame(vid, monkeypatch, running=False)
    r = client.get(f"/v/{vid}/m/editor-pkg", follow_redirects=False)
    assert r.status_code == 303 and "editor-pkg" not in client.get(f"/v/{vid}/more").text


def test_a_request_that_changes_something_needs_the_frame_header():
    headers = [(b"x-requested-with", b"frame")]
    assert proxy.frame_ok("GET", []) and proxy.frame_ok("POST", headers) and proxy.frame_ok("DELETE", [(b"x-requested-with", b"Frame")])
    assert not proxy.frame_ok("POST", []) and not proxy.frame_ok("PUT", [(b"x-requested-with", b"XMLHttpRequest")])


def test_the_service_gets_the_car_and_the_person_but_never_cookies(client):
    from tests.conftest import demo_car

    vid = demo_car(client)
    got = dict(proxy.identity([(b"cookie", b"x=y")], f"lang=de&car={vid}", "127.0.0.1"))
    assert got == {"X-CA-Vehicle": str(vid), "X-CA-User": "ha"}
    assert dict(proxy.identity([], "car=99999", "8.8.8.8")) == {}  # a car that does not exist, a stranger: nothing
    assert dict(proxy.identity([], "car=abc", "127.0.0.1")) == {"X-CA-User": "ha"}
    assert {"x-ca-vehicle", "x-ca-user"} <= proxy.DROP_REQUEST  # what a caller sends under these names is dropped


def test_the_design_goes_to_the_page_as_variables_and_a_small_kit(client):
    default = frametheme.tokens("default")
    assert "--accent" in default and "color-scheme: dark" in default and "[data-theme" not in default
    assert "color-scheme: light" in frametheme.tokens("light")
    assert "prefers-color-scheme: light" in frametheme.tokens("auto")
    assert frametheme.tokens("../../etc/passwd") == default  # an unknown name is the default
    css = client.get("/frame-theme.css?theme=light")
    assert css.status_code == 200 and css.headers["content-type"].startswith("text/css") and "color-scheme: light" in css.text
    kit = client.get("/frame-kit.css?theme=custom-light").text
    assert (
        "--accent" in kit and ".card {" in kit and "button.primary" in kit and "#" not in kit.split("*/", 1)[1].replace("#fff", "")
    )  # tokens only


def test_an_integration_may_carry_a_service_and_frame_pages(client, monkeypatch):
    from tests.conftest import demo_car

    assert addons.parse_package(_manifest("integration"))["kind"] == "integration"
    vid = demo_car(client)
    _install_frame(vid, monkeypatch, running=False, kind="integration")
    with db.tx() as conn:
        assert pagemods.active_modules(conn, vid) == []  # stopped: no page, no entry
    monkeypatch.setattr(pluginsvc, "running", lambda pk: True)
    with db.tx() as conn:
        mods = pagemods.active_modules(conn, vid)
        assert [m["addon_id"] for m in mods] == ["editor-pkg"] and mods[0]["version"] == "3"
        assert navigation.X + "editor-pkg" in navigation.integration_pages(conn, vid)
    assert client.get(f"/v/{vid}/m/editor-pkg", follow_redirects=False).status_code == 303


def test_the_service_of_an_integration_gets_no_token_and_no_api():
    manifest = addons.parse_package(_manifest("integration"))
    addon = {"addon_id": "editor-pkg", "kind": "integration", "m": manifest, "vals": {}, "vehicle_id": 1, "pkg_sha": "abc"}
    env = pluginsvc._env(addon, pluginsvc.Path("/tmp/x"), "", 4321)
    assert "CA_API_TOKEN" not in env and "CA_API_URL" not in env and env["CA_PORT"] == "4321" and env["CA_VEHICLE_ID"] == "1"
    plugin = {**addon, "kind": "plugin"}
    assert pluginsvc._env(plugin, pluginsvc.Path("/tmp/x"), "tok", 4321)["CA_API_TOKEN"] == "tok"


def test_the_head_is_put_on_a_page_of_the_package_only(client, monkeypatch):
    from tests.conftest import demo_car

    vid = demo_car(client)
    _install_frame(vid, monkeypatch)
    with db.tx() as conn:
        pk = conn.execute("SELECT id FROM vehicle_addons WHERE addon_id = 'editor-pkg'").fetchone()["id"]
        slug = conn.execute("SELECT slug FROM vehicles WHERE id = ?", (vid,)).fetchone()["slug"]
    page = b"<!doctype html><html><head><title>x</title></head><body><h1>Editor</h1></body></html>"
    html = [("Content-Type", "text/html; charset=utf-8")]
    nav = [(b"sec-fetch-dest", b"document"), (b"accept", b"text/html")]
    got = proxy._with_head(page, html, pk, "/ext/editor/", "theme=custom-light", nav).decode()
    assert (
        got.index("<head>") < got.index("frame-head.css?theme=custom-light") < got.index("<title>")
    )  # the styles of the package come later and win
    assert got.index('<body><header id="ca-head">') < got.index("<h1>")  # the head sits at the top of the body
    assert f'href="/v/{slug}/more"' in got and 'class="ca-name">Editor<' in got and 'class="ca-ver">v3<' in got and "<script" not in got
    assert proxy._with_head(page, html, pk, "/ext/editor/x", "", nav).decode().count('id="ca-head"') == 1  # below the route: still the page
    assert proxy._with_head(page, html, pk, "/ext/other/", "", nav) == page  # not a frame page: untouched
    assert proxy._with_head(page, [("Content-Type", "application/json")], pk, "/ext/editor/", "", nav) == page
    assert (
        proxy._with_head(page, html, pk, "/ext/editor/", "", [(b"sec-fetch-dest", b"iframe")]) == page
    )  # only a page of its own, nothing embedded
    assert proxy._with_head(page, html, pk, "/ext/editor/", "", [*nav, (b"x-requested-with", b"frame")]) == page  # a fetch from a script
    ingress = framehead.base_of("/api/hassio_ingress/abc_1")
    assert ingress == "/api/hassio_ingress/abc_1" and framehead.base_of("/evil") == ""


def test_the_head_has_no_head_or_body_tag_to_find_still_works():
    out = framehead.inject(b"<p>plain</p>", '<header id="ca-head"></header>', "/frame-head.css")
    assert out.startswith(b'<link rel="stylesheet"') and b'<header id="ca-head">' in out and out.endswith(b"<p>plain</p>")
    upper = framehead.inject(b"<HTML><HEAD></HEAD><BODY class=x>hi</BODY></HTML>", "<header></header>", "/c.css")
    assert upper.index(b"<link") < upper.index(b"<header>") < upper.index(b"hi")


def test_the_head_follows_the_design_and_never_touches_the_page_variables(client):
    for theme in ("default", "light", "auto"):
        css = framehead.css(theme)
        assert "#ca-head {" in css and ":root" not in css and "html {" in css and ".ca-back" in css
    assert "html { background: #0d1016" in framehead.css("default") and "html { background: #eef0f4" in framehead.css("light")
    assert "prefers-color-scheme: light" in framehead.css("auto")
    r = client.get("/frame-head.css?theme=ocean")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/css") and "#ca-head" in r.text


def test_a_page_of_a_package_gets_a_box_of_the_maximum_width_and_a_foot():
    foot = '<footer id="ca-foot"></footer>'
    out = framehead.inject(b"<html><head></head><body><h1>x</h1></body></html>", '<header id="ca-head"></header>', "/c.css", foot).decode()
    assert out.index('<header id="ca-head"></header><div id="ca-wrap"><h1>x</h1></div><footer id="ca-foot">') < out.index("</body>")
    plain = framehead.inject(b"<p>x</p>", "<header></header>", "/c.css", foot).decode()
    assert plain.endswith('</div><footer id="ca-foot"></footer>') and 'id="ca-wrap"' in plain
