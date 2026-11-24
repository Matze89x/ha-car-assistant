"""Conditions (``when``) for buttons and downloads, ``setup.done_when`` / ``settings_after``, the place of buttons (tile or tab *General*),
the fixed first tab, and the versions of the files a plugin offers (docs/plugins.md, "Conditions" and "The tab General")."""

import json
import re

from tests.test_addons import MANIFEST, upload
from tests.test_plugin_buttons import PAGES, SERVICE
from tests.test_web import create_vehicle, slug

from carassistant import addons, connectors, db

TYPES = {"account": "value", "mode": "text", "flag": "bool", "head": "section"}


def test_a_when_is_one_test_or_a_list_and_what_cannot_be_read_gives_none():
    ok = addons.clean_when
    assert ok(None, TYPES) == []  # no condition
    assert ok({"setup": "done"}, TYPES) == [{"setup": "done"}]
    assert ok([{"token": True}, {"key": "account", "set": True}], TYPES) == [{"token": True}, {"key": "account", "set": True}]
    assert ok({"key": "mode", "equals": "eco"}, TYPES) == [{"key": "mode", "equals": "eco"}]
    assert ok({"key": "flag", "equals": True}, TYPES) == [{"key": "flag", "equals": "1"}]  # a switch is 1 / 0, like show_if
    for bad in (
        [],  # nothing to test
        {"setup": "maybe"},
        {"token": "yes"},
        {"key": "nope", "set": True},  # no such setting
        {"key": "head", "set": True},  # a heading holds no value
        {"key": "mode"},  # neither equals nor set
        "done",
        [{"token": True}] * 6,  # more than five tests
    ):
        assert ok(bad, TYPES) is None, bad
    assert ok({"setup": "done"}, TYPES, allow_setup=False) is None  # done_when cannot depend on itself


def test_when_holds_judges_setup_token_and_stored_values():
    def holds(tests, **kw):
        base = {"setup_done": False, "has_token": False, "values": {}, "types": TYPES}
        return addons.when_holds(tests, **{**base, **kw})

    assert holds([])  # no test = always
    assert holds([{"setup": "open"}]) and not holds([{"setup": "done"}])
    assert holds([{"setup": "done"}], setup_done=True)
    assert holds([{"token": True}], has_token=True) and not holds([{"token": True}])
    assert holds([{"key": "account", "set": True}], values={"account": "max"}) and not holds([{"key": "account", "set": True}])
    assert holds([{"key": "account", "set": False}])
    assert holds([{"key": "mode", "equals": "eco"}], values={"mode": "eco"}) and not holds(
        [{"key": "mode", "equals": "eco"}], values={"mode": "x"}
    )
    assert not holds([{"key": "flag", "set": True}], values={"flag": "0"})  # a switch that is off is not "set"
    assert holds([{"key": "flag", "set": True}], values={"flag": "1"})
    assert not holds([{"token": True}, {"setup": "done"}], has_token=True)  # all of them must hold


def test_buttons_have_a_place_and_a_when_and_an_unreadable_when_drops_the_button():
    got = addons.clean_buttons(
        [
            {"id": "a", "label": "A", "page": "docs"},
            {"id": "out", "label": "Log out", "action": "/priv/out", "place": "settings", "when": {"key": "account", "set": True}},
            {"id": "bad", "label": "Bad", "action": "/priv/bad", "place": "settings", "when": {"key": "nope", "set": True}},
        ],
        PAGES,
        SERVICE,
        TYPES,
    )
    assert [b["id"] for b in got] == ["a", "out"]  # the one with a condition that cannot be read stays away
    assert "place" not in got[0] and got[1]["place"] == "settings" and got[1]["when"] == [{"key": "account", "set": True}]
    tile = [{"id": f"t{i}", "label": "T", "page": "docs"} for i in range(5)]
    aside = [{"id": f"s{i}", "label": "S", "page": "docs", "place": "settings"} for i in range(9)]
    got = addons.clean_buttons(tile[:4] + aside, PAGES, SERVICE, TYPES)
    assert sum(b.get("place") != "settings" for b in got) == addons.MAX_BUTTONS == 3
    assert sum(b.get("place") == "settings" for b in got) <= addons.MAX_SETTINGS_BUTTONS == 6


def test_downloads_take_place_and_when_too():
    got = addons.clean_downloads(
        [
            {"label": "Log", "path": "/priv/car.log"},
            {"label": "Export", "path": "/priv/export.zip", "place": "settings", "when": {"setup": "done"}},
            {"label": "Bad", "path": "/priv/bad.zip", "when": {"token": 1}},
        ],
        SERVICE,
        TYPES,
    )
    assert [d["label"] for d in got] == ["Log", "Export"]
    assert got[1]["place"] == "settings" and got[1]["when"] == [{"setup": "done"}] and "place" not in got[0]


def _setup(**extra):
    return {
        "title": "Log in",
        "l10n": {"de": {"title": "Anmelden"}},
        "flow": [{"id": "hello", "type": "text", "title": "Hello", "text": "Welcome."}],
        **extra,
    }


def test_done_when_and_settings_after_come_from_the_setup_and_a_bad_condition_is_ignored():
    types = {"account": "value"}
    got = addons.clean_setup(
        _setup(done_when=[{"token": True}, {"key": "account", "set": True}], settings_after=True),
        [],
        False,
        {"account"},
        set(),
        None,
        types,
    )
    assert got["done_when"] == [{"token": True}, {"key": "account", "set": True}] and got["settings_after"] is True
    bad = addons.clean_setup(_setup(done_when={"setup": "done"}), [], False, {"account"}, set(), None, types)
    assert "done_when" not in bad  # the set-up then counts as done at the end of the guide, as before
    steps = {"steps": [{"id": "token", "token": True}], "settings_after": True}
    legacy = addons.clean_setup(steps, [], False, set(), set(), None, {})
    assert "settings_after" not in legacy  # only a flow can be finished before the settings are needed


def test_the_version_of_a_file_is_shown_and_installed_must_name_a_setting_the_plugin_can_write():
    manifest = {
        **MANIFEST,
        "id": "ver-demo",
        "settings": [{"key": "car", "type": "value", "label": "On the car"}, {"key": "plain", "type": "text", "label": "Plain"}],
        "bundles": [
            {
                "name": "install.zip",
                "label": "Install",
                "version": "1.4",
                "installed": "car",
                "entries": [{"from": "a.txt", "to": "b.txt"}],
            },
            {
                "name": "other.zip",
                "label": "Other",
                "version": "no good!",
                "installed": "plain",
                "entries": [{"from": "a.txt", "to": "c.txt"}],
            },
        ],
    }
    got = addons.parse_package(json.dumps(manifest).encode())["bundles"]
    assert got[0]["version"] == "1.4" and got[0]["installed"] == "car"
    assert (
        "version" not in got[1] and "installed" not in got[1]
    )  # a version with odd characters and a setting nobody can write: both dropped
    # what is approved does not change with the shown version
    other = json.loads(json.dumps(manifest))
    other["bundles"][0]["version"] = "1.5"
    changed = addons.parse_package(json.dumps(other).encode())
    assert addons.approval_fingerprint(addons.parse_package(json.dumps(manifest).encode())) == addons.approval_fingerprint(changed)


def test_the_first_tab_is_always_the_apps_general_whatever_the_package_called_it():
    fields = addons.clean_setting_fields(
        [
            {"type": "tab", "id": "conn", "label": "Connection", "icon": "plug"},
            {"key": "host", "type": "text", "label": "Host"},
            {"type": "tab", "id": "more", "label": "More"},
            {"key": "mode", "type": "text", "label": "Mode"},
        ]
    )
    tabs = addons.settings_tabs(fields)
    assert [t["id"] for t in tabs] == ["conn", "more"]  # the id stays, so a link to it keeps working ...
    assert (
        tabs[0]["label"] == "" and tabs[0]["icon"] == "plug" and tabs[1]["label"] == "More"
    )  # ... the page writes General (empty = the app's word)


def test_the_car_version_is_compared_with_the_offered_one():
    assert addons.version_state("1.2", "1.4") == "update"
    assert addons.version_state("1.4", "1.4") == "current"
    assert addons.version_state("1.10", "1.9") == "newer"  # numbers are compared as numbers
    assert addons.version_state("", "1.4") == "" and addons.version_state("1.2", "") == ""  # nothing known = nothing said


FULL = {
    **MANIFEST,
    "id": "cond-demo",
    "pages": PAGES,
    "service": SERVICE,
    "settings": [
        {"key": "account", "type": "value", "label": "Account"},
        {"key": "car", "type": "value", "label": "Version on the car"},
        {"type": "tab", "id": "conn", "label": "Connection"},
        {"key": "host", "type": "text", "label": "Host"},
        {"type": "tab", "id": "more", "label": "More"},
        {"key": "mode", "type": "text", "label": "Mode"},
    ],
    "setup": _setup(done_when=[{"token": True}, {"key": "account", "set": True}], settings_after=True),
    "buttons": [
        {"id": "wake", "label": "Wake the car", "action": "/priv/wake"},
        {"id": "docs", "label": "Documentation", "page": "docs", "when": {"setup": "done"}},
        {
            "id": "out",
            "label": "Log out",
            "action": "/priv/out",
            "place": "settings",
            "when": {"key": "account", "set": True},
            "confirm": "Sure?",
        },
        {"id": "again", "label": "Log in again", "page": "docs", "place": "settings", "when": {"key": "account", "set": False}},
    ],
    "downloads": [
        {"label": "Car log", "path": "/priv/car.log"},
        {"label": "Full export", "path": "/priv/export.zip", "place": "settings"},
    ],
    "bundles": [
        {
            "name": "install.zip",
            "label": "Update for the car",
            "version": "1.4",
            "installed": "car",
            "entries": [{"from": "a.txt", "to": "b.txt"}],
        },
    ],
}


def _install(client, monkeypatch):
    from carassistant import pluginsvc

    monkeypatch.setattr(pluginsvc, "approved", lambda addon: True)  # otherwise the main button asks for the approval first
    vid = create_vehicle(client)
    with db.tx() as conn:
        source = conn.execute("SELECT id FROM sources LIMIT 1").fetchone()["id"]
        pk = addons.add(conn, vid, addons.parse_package(json.dumps(FULL).encode()), source, "0" * 64)
        conn.execute("UPDATE vehicle_addons SET active = 1 WHERE id = ?", (pk,))
    return vid, pk


def _tile(client, vid):
    page = client.get(f"/v/{slug(vid)}/plugins").text
    start = page.index('class="abar-box"')
    return page[start : page.index("</div></div>", start)]


def test_the_tile_shows_setup_until_the_conditions_hold_and_settings_only_after(client, monkeypatch):
    vid, pk = _install(client, monkeypatch)
    tile = _tile(client, vid)
    assert "Log in" in tile and f"/integrations/{pk}/guide" in tile  # the plugin's own name for the set-up is the main button
    assert f"/integrations/{pk}/settings" not in tile  # settings_after: not before the set-up is done
    assert "Wake the car" in tile and "Documentation" not in tile  # `when: setup done` is not true yet
    with db.tx() as conn:  # the guide ended (configured) and a token exists, but nobody is logged in yet
        token = connectors.create_token(conn, "t", vid)
        assert token
        token_id = conn.execute("SELECT id FROM api_tokens ORDER BY id DESC").fetchone()["id"]
        conn.execute("UPDATE vehicle_addons SET status = 'configured', token_id = ? WHERE id = ?", (token_id, pk))
    tile = _tile(client, vid)
    assert f"/integrations/{pk}/guide" in tile and f"/integrations/{pk}/settings" not in tile  # done_when asks for the account, too
    with db.tx() as conn:
        conn.execute("UPDATE vehicle_addons SET settings = ? WHERE id = ?", (json.dumps({"account": "max"}), pk))
    tile = _tile(client, vid)
    assert f"/integrations/{pk}/guide" not in tile and "Log in" not in tile  # the main button is gone
    assert f"/integrations/{pk}/settings" in tile and "Documentation" in tile
    with db.tx() as conn:  # the login fails later: the button comes back
        conn.execute("UPDATE vehicle_addons SET settings = '{}' WHERE id = ?", (pk,))
    assert f"/integrations/{pk}/guide" in _tile(client, vid)


def test_the_settings_page_has_the_fixed_first_tab_actions_files_and_versions(client, monkeypatch):
    vid, pk = _install(client, monkeypatch)
    with db.tx() as conn:
        conn.execute("UPDATE vehicle_addons SET settings = ? WHERE id = ?", (json.dumps({"account": "max", "car": "1.2"}), pk))
    page = client.get(f"/v/{slug(vid)}/integrations/{pk}/settings").text
    start = page.index("data-set-tabs")
    nav = page[start : page.index("</nav>", start)]
    assert nav.index(">General<") < nav.index(">Connection<") < nav.index(">More<")  # settings before the first tab are the app's General
    assert "Log out" in page and "Log in again" not in page  # the account is set: only what fits
    assert 'data-confirm="Sure?"' in page and f"/integrations/{pk}/button/out" in page
    assert "Update for the car" in page and "Update ready" in page  # the car has 1.2, 1.4 is offered
    assert "Ready <b>1.4</b>" in page and "On the car <b>1.2</b>" in page
    assert "Full export" in page and "Car log" not in page.split("Files for the car")[1].split("</section>")[0]  # only its own place
    with db.tx() as conn:
        conn.execute("UPDATE vehicle_addons SET settings = ? WHERE id = ?", (json.dumps({"car": "1.4"}), pk))
    page = client.get(f"/v/{slug(vid)}/integrations/{pk}/settings").text
    assert "Up to date" in page and "Log in again" in page and "Log out" not in page
    assert "Log in again" in page  # `set: false` shows the opposite button


def test_an_action_that_is_hidden_right_now_is_not_run_either(client, monkeypatch):
    from carassistant import pluginsvc

    vid, pk = _install(client, monkeypatch)
    calls = []
    monkeypatch.setattr(pluginsvc, "call", lambda *a, **k: calls.append(a) or (True, "done"))
    page = client.post(f"/v/{slug(vid)}/integrations/{pk}/button/out").text  # nobody is logged in: "Log out" is not on any page
    assert "not available right now" in page and not calls
    with db.tx() as conn:
        conn.execute("UPDATE vehicle_addons SET settings = ? WHERE id = ?", (json.dumps({"account": "max"}), pk))
    assert "done" in client.post(f"/v/{slug(vid)}/integrations/{pk}/button/out").text and len(calls) == 1


def test_every_plugin_token_can_be_read_again_by_an_administrator_on_the_settings_page(client):
    """Not only a plugin with a connection file: the token of any plugin is kept (encrypted) and shown on the tab General."""
    vid = create_vehicle(client)
    upload(client, vid, json.dumps(MANIFEST).encode())
    with db.tx() as conn:
        pk = addons.list_for(conn, vid)[0]["id"]
    made = client.post(f"/v/{slug(vid)}/integrations/{pk}/setup", data={"note": "x"})
    token = re.search(r"ca_[A-Za-z0-9_-]{20,}", made.text).group(0)
    page = client.get(f"/v/{slug(vid)}/integrations/{pk}/settings").text
    assert f'value="{token}"' in page
