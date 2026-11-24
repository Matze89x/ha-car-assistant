"""The tile of a plugin: Uninstall as a symbol, Logs, Settings, first-time Set up, the plugin's own free buttons, and the log page."""

import json
import re

from tests.test_addons import MANIFEST, upload
from tests.test_web import create_vehicle, slug

from carassistant import addons, connectors, db, pluginsvc

SERVICE = {
    "entry": "service/main.py",
    "python": ">=3.9",
    "requirements": [],
    "routes": [{"prefix": "/svc/", "public": True}, {"prefix": "/priv/", "public": False}],
}
PAGES = [{"id": "docs", "kind": "frame", "title": "Documentation", "route": "/priv/docs/"}]


def test_buttons_open_a_page_of_the_package_or_call_a_private_route_of_its_service():
    got = addons.clean_buttons(
        [
            {"id": "docs", "label": "Documentation", "icon": "book-open-variant", "page": "docs"},
            {
                "id": "ping",
                "label": "Wake the car",
                "icon": "not-an-icon",
                "action": "/priv/ping",
                "confirm": "Sure?",
                "l10n": {"de": {"label": "Auto wecken"}},
            },
            {"id": "open", "label": "Public", "action": "/svc/open"},  # a public route: anybody could press it
            {"id": "far", "label": "Away", "action": "/priv/../x"},
            {"id": "nopage", "label": "Missing", "page": "nothing"},
            {"id": "Bad Id", "label": "x", "page": "docs"},
            {"id": "docs", "label": "Twice", "page": "docs"},
            {"id": "nolabel", "page": "docs"},
            "nonsense",
        ],
        PAGES,
        SERVICE,
    )
    assert [b["id"] for b in got] == ["docs", "ping"]
    assert got[0]["page"] == "docs" and "action" not in got[0]
    assert got[1]["action"] == "/priv/ping" and got[1]["confirm"] == "Sure?" and got[1]["icon"] == "play-circle-outline"
    assert got[1]["l10n"] == {"de": {"label": "Auto wecken"}}
    assert addons.clean_buttons("nonsense", PAGES, SERVICE) == [] and addons.clean_buttons(None, [], None) == []


def test_three_buttons_at_most_because_the_tile_is_one_line():
    many = [{"id": f"b{i}", "label": f"B{i}", "page": "docs"} for i in range(8)]
    assert len(addons.clean_buttons(many, PAGES, SERVICE)) == addons.MAX_BUTTONS == 3


def test_the_manifest_keeps_the_buttons_and_the_language_of_the_page_picks_the_label(client):
    manifest = {
        **MANIFEST,
        "id": "btn-demo",
        "pages": PAGES,
        "service": SERVICE,
        "buttons": [{"id": "docs", "label": "Docs", "page": "docs", "l10n": {"de": {"label": "Anleitung"}}}],
    }
    parsed = addons.parse_package(json.dumps(manifest).encode())
    assert parsed["buttons"][0]["id"] == "docs"
    assert "buttons" not in addons.parse_package(json.dumps(MANIFEST).encode())  # nothing added when the package has none


def _install_with_buttons(client, buttons, pages=PAGES, service=SERVICE):
    vid = create_vehicle(client)
    manifest = {**MANIFEST, "id": "btn-demo", "pages": pages, "service": service, "buttons": buttons}
    with db.tx() as conn:
        source = conn.execute("SELECT id FROM sources LIMIT 1").fetchone()["id"]
        pk = addons.add(conn, vid, addons.parse_package(json.dumps(manifest).encode()), source, "0" * 64)
    return vid, pk


def test_the_tile_has_uninstall_as_a_symbol_then_logs_settings_and_the_free_buttons(client):
    vid, pk = _install_with_buttons(
        client, [{"id": "docs", "label": "Documentation", "page": "docs"}, {"id": "ping", "label": "Wake", "action": "/priv/ping"}]
    )
    page = client.get(f"/v/{slug(vid)}/plugins").text
    bar = page[page.index('class="addon-bar fb2"') :]
    bar = bar[: bar.index("</div>")]
    first = bar.index("<button")
    assert 'class="danger ico-only"' in bar[first : first + 80] and "Uninstall" in bar[first : first + 260]
    assert "lbl2" not in bar[first : bar.index("</button>", first)]  # no text on the first button, only the symbol
    positions = [
        bar.index(x)
        for x in (f"/integrations/{pk}/logs", f"/integrations/{pk}/settings", "/m/btn-demo/docs", f"/integrations/{pk}/button/ping")
    ]
    assert positions == sorted(positions)  # Logs, Settings, free buttons, in this order
    assert ">Logs<" in bar and ">Settings<" in bar and ">Documentation<" in bar and ">Wake<" in bar


def test_the_tile_counts_the_downloads_too_so_the_bar_never_overflows(client):
    """The widths at which the words go are chosen by how many extra buttons stand in the bar: the own buttons AND the downloads."""
    vid = create_vehicle(client)
    manifest = {
        **MANIFEST,
        "id": "dl-demo",
        "pages": PAGES,
        "service": SERVICE,
        "buttons": [{"id": "docs", "label": "Documentation", "page": "docs"}],
        "downloads": [{"label": "Car log", "path": "/svc/car.log"}, {"label": "Signal data", "path": "/svc/signals.zip"}],
    }
    with db.tx() as conn:
        source = conn.execute("SELECT id FROM sources LIMIT 1").fetchone()["id"]
        addons.add(conn, vid, addons.parse_package(json.dumps(manifest).encode()), source, "0" * 64)
    page = client.get(f"/v/{slug(vid)}/plugins").text
    assert 'class="abar-box"><div class="addon-bar fb3"' in page  # one button of its own + two downloads
    assert ">Car log<" in page and ">Signal data<" in page
    many = {**manifest, "id": "dl-many", "buttons": [], "downloads": [{"label": f"D{i}", "path": f"/svc/d{i}.zip"} for i in range(10)]}
    with db.tx() as conn:
        addons.add(conn, vid, addons.parse_package(json.dumps(many).encode()), source, "0" * 64)
    assert (
        'class="addon-bar fb9"' in client.get(f"/v/{slug(vid)}/plugins").text
    )  # nine or more: symbols only, and a second line may be taken


def test_a_plugin_without_free_buttons_has_the_same_tile_with_fb0(client):
    client.post("/vehicles", data={"name": "Plain", "fuel_type": "petrol"})
    vid = create_vehicle(client, name="Plain two")
    assert upload(client, vid, json.dumps(MANIFEST).encode()).status_code == 303
    page = client.get(f"/v/{slug(vid)}/plugins").text
    assert 'class="addon-bar fb0"' in page and "/logs" in page and "ico-only" in page


def test_the_log_page_shows_everything_or_only_the_problems_and_gives_a_text_file(client):
    vid, pk = _install_with_buttons(client, [])
    with db.tx() as conn:
        connectors.write_logs(
            conn,
            vid,
            "btn-demo",
            [
                ("2026-11-24T10:00:00+00:00", "info", "svc", "all is fine"),
                ("2026-11-24T10:01:00+00:00", "error", "svc", "the login failed"),
                ("2026-11-24T10:02:00+00:00", "warn", "svc", "slow answer"),
            ],
        )
    base = f"/v/{slug(vid)}/integrations/{pk}/logs"
    everything = client.get(base).text
    assert "all is fine" in everything and "the login failed" in everything and "slow answer" in everything
    assert "Problems · 2" in everything  # the number of warnings and errors is on the filter
    problems = client.get(base + "?level=problems").text
    assert "the login failed" in problems and "slow answer" in problems and "all is fine" not in problems
    text = client.get(base + ".txt")
    assert (
        text.status_code == 200
        and text.headers["content-type"].startswith("text/plain")
        and "attachment" in text.headers["content-disposition"]
    )
    assert "the login failed" in text.text and "all is fine" in text.text
    assert client.get(f"/v/{slug(vid)}/integrations/{pk}/info?tab=logs").status_code == 200  # the old address still works


def test_an_action_button_calls_the_private_route_and_shows_what_the_service_said(client, monkeypatch):
    vid, pk = _install_with_buttons(client, [{"id": "ping", "label": "Wake", "action": "/priv/ping"}])
    with db.tx() as conn:
        conn.execute("UPDATE vehicle_addons SET active = 1 WHERE id = ?", (pk,))
    calls = []

    def fake_call(pk_, path, payload, vehicle_id, user="ha", timeout=10.0):
        calls.append((pk_, path, payload, vehicle_id))
        return True, "The car is awake."

    monkeypatch.setattr(pluginsvc, "call", fake_call)
    monkeypatch.setattr(pluginsvc, "approved", lambda addon: True)
    r = client.post(f"/v/{slug(vid)}/integrations/{pk}/button/ping")
    assert r.status_code == 200 and 'class="addon-status ok"' in r.text and "The car is awake." in r.text
    assert calls == [(pk, "/priv/ping", {"vehicle": vid, "button": "ping", "language": "en"}, vid)]
    monkeypatch.setattr(pluginsvc, "call", lambda *a, **k: (False, "no answer"))
    assert "does not answer" in client.post(f"/v/{slug(vid)}/integrations/{pk}/button/ping").text
    assert client.post(f"/v/{slug(vid)}/integrations/{pk}/button/nothing").status_code == 404  # only buttons the package declared
    monkeypatch.setattr(pluginsvc, "approved", lambda addon: False)
    assert "approved" in client.post(f"/v/{slug(vid)}/integrations/{pk}/button/ping").text  # a plugin that is not approved is never called


def test_inside_the_plugins_area_the_side_bar_keeps_its_entry_marked_and_a_plugin_page_leads_back_to_the_list(client):
    """The side bar entry *Plugins* stays marked on every page of the area (the list, its tabs, one plugin's settings / logs), and a page of one plugin has a
    Back that leads to the list of its kind - Integrations for an integration."""
    vid, pk = _install_with_buttons(client, [])
    base = f"/v/{slug(vid)}"

    def marked(page: str, name: str) -> bool:
        """Is the side bar item (``<a class="mi ...">``) that leads to ``name`` marked?"""
        item = re.search(rf'<a class="(mi[^"]*)" href="{re.escape(base)}/{name}"', page)
        assert item, name
        return "sel" in item.group(1).split()

    for path in (
        f"{base}/plugins",
        f"{base}/plugins/add",
        f"{base}/plugins/connections",
        f"{base}/integrations/{pk}/settings",
        f"{base}/integrations/{pk}/logs",
    ):
        page = client.get(path).text
        assert marked(page, "plugins") and not marked(page, "integrations"), path  # Plugins is marked, Integrations is not
    for path in (f"{base}/integrations/{pk}/settings", f"{base}/integrations/{pk}/logs"):
        assert f'class="back-btn deep" href="{base}/plugins"' in client.get(path).text, path  # a Back to the list, also on wide screens
    manifest = {
        "id": "an-integration",
        "kind": "integration",
        "name": "Tool",
        "version": "1",
        "settings": [{"key": "a", "type": "text", "label": "A"}],
    }
    with db.tx() as conn:
        source = conn.execute("SELECT id FROM sources LIMIT 1").fetchone()["id"]
        other = addons.add(conn, vid, addons.parse_package(json.dumps(manifest).encode()), source, "0" * 64)
    page = client.get(f"{base}/integrations/{other}/settings").text
    assert marked(page, "integrations") and not marked(page, "plugins")  # an integration marks Integrations
    assert f'class="back-btn deep" href="{base}/integrations"' in page
