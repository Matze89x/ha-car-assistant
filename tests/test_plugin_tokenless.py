"""A plugin that never reports needs no token (its guide leaves the token part out), a package with a connection file is offered on the tab General,
the app notes what it handed out ("last downloaded", "settings changed since"), the test ``downloaded``, a button that opens a step of the
set-up flow, and the honest install page (docs/plugins.md)."""

import json
import re

from tests.test_assets import _install, _manifest
from tests.test_plugin_conditions import FULL
from tests.test_web import create_vehicle, slug

from carassistant import addons, connectors, db, i18n, interfaces


def _tokenless(template="cfg=2\nmode={mode}\n", **extra):
    return {
        **_manifest(),
        "id": "files-pkg",
        "settings": [{"key": "mode", "type": "text", "label": "Mode"}],
        "connection_file": {"name": "x.cfg", "template": template},
        "bundles": [
            {
                "name": "install.zip",
                "label": "Install",
                "version": "3",
                "connection_file_to": "mod/x/x.cfg",
                "entries": [{"from": "scripts/custom.sh", "to": "mod/custom.sh"}],
            }
        ],
        "setup": {"title": "Set up", "steps": [{"id": "files", "bundles": ["install.zip"]}], "done_when": [{"downloaded": True}]},
        **extra,
    }


def test_who_needs_a_token():
    need = addons.needs_token
    assert need({"service": {"entry": "a.py"}, "connection_file": {"template": "x=1\n"}})  # a service always reports
    assert need({}) and need({"connection_file": {"template": "token={token}\n"}})
    assert not need({"connection_file": {"template": "cfg=2\n"}})  # a file with only settings
    assert not need({"setup": {"token": False}})  # or when it says so
    assert need({"service": {"entry": "a.py"}, "setup": {"token": False}})  # ... but not with a service
    assert addons.file_has_secret({"connection_file": {"template": "t={token}"}}) and not addons.file_has_secret(
        {"connection_file": {"template": "a"}}
    )


def test_downloaded_is_a_test_and_a_leading_word_does_not_matter_in_a_version():
    types = {}
    assert addons.clean_when({"downloaded": True}, types) == [{"downloaded": True}]
    assert addons.clean_when({"downloaded": "install.zip"}, types) == [{"downloaded": "install.zip"}]
    assert addons.clean_when({"downloaded": 3}, types) is None and addons.clean_when({"downloaded": "../x"}, types) is None

    def holds(tests, delivered):
        return addons.when_holds(tests, setup_done=False, has_token=False, values={}, types={}, delivered=frozenset(delivered))

    assert holds([{"downloaded": True}], {"a.zip"}) and not holds([{"downloaded": True}], set())
    assert (
        holds([{"downloaded": False}], set())
        and holds([{"downloaded": "a.zip"}], {"a.zip"})
        and not holds([{"downloaded": "b.zip"}], {"a.zip"})
    )
    assert (
        addons.version_state("7", "Build 7") == "current" and addons.version_state("Build 6", "Build 7") == "update"
    )  # "Build 7" has a space
    assert addons.version_state("V1.23", "1.23") == "current" and addons.version_state("v8", "8") == "current"
    parsed = addons.parse_package(json.dumps({**_manifest(), "bundles": [{**_manifest()["bundles"][0], "version": "Build 7"}]}).encode())
    assert parsed["bundles"][0]["version"] == "Build 7"


def test_the_guide_of_a_plugin_without_a_token_has_only_the_settings_and_gives_the_package_straight_away(client, monkeypatch):
    vid, item = _install(client, monkeypatch, _tokenless())
    assert item is not None and not addons.needs_token(item["m"])
    base = f"/v/{vid}/integrations/{item['id']}"
    client.post(f"{base}/service/approve")
    step2 = client.get(f"{base}/guide?step=2").text
    assert 'name="token_mode"' not in step2 and "Settings" in step2  # no boxes for a token
    client.post(f"{base}/guide/next", data={"mode": "eco"})
    with db.tx() as conn:
        item = addons.get(conn, vid, item["id"])
    assert item["status"] == "configured" and item["token_id"] is None  # set up, and no token was made
    assert item["setup_open"]  # done_when asks for a package that was handed out: not yet
    plugins = client.get(f"/v/{vid}/plugins").text
    assert "Set up" in plugins
    step3 = client.get(f"{base}/guide?step=3").text
    assert 'action="' in step3 and "/guide/bundle" in step3 and 'name="token"' not in step3  # no token to type or carry
    made = client.post(f"{base}/guide/bundle", data={"name": "install.zip"})
    assert made.status_code == 200 and made.headers["content-type"] == "application/zip"
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(made.content)) as z:
        assert z.read("mod/x/x.cfg").decode() == "cfg=2\nmode=eco\n"
    with db.tx() as conn:
        assert addons.get(conn, vid, item["id"])["setup_open"] is False  # handed out once: the set-up button is gone
    assert "Set up" not in client.get(f"/v/{vid}/plugins").text.split('class="abar-box"')[1].split("</div></div>")[0]
    general = client.get(f"{base}/settings").text
    assert "Last downloaded" in general and "Connection token" not in general  # no token card for a plugin without a token
    assert "Settings changed since" not in general
    with db.tx() as conn:  # the person changes a setting after that package was made
        conn.execute("UPDATE vehicle_addons SET settings = ? WHERE id = ?", (json.dumps({"mode": "sport"}), item["id"]))
    assert "Settings changed since - download again" in client.get(f"{base}/settings").text
    again = client.get(f"{base}/get/install.zip")  # the tab General hands it out, too, and notes it
    assert again.status_code == 200
    with zipfile.ZipFile(io.BytesIO(again.content)) as z:
        assert z.read("mod/x/x.cfg").decode() == "cfg=2\nmode=sport\n"
    assert "Settings changed since" not in client.get(f"{base}/settings").text


def test_a_package_that_carries_the_token_comes_from_general_only_when_the_app_keeps_the_token(client, monkeypatch):
    vid, item = _install(client, monkeypatch, _tokenless("token={token}\nmode={mode}\n"))
    base = f"/v/{vid}/integrations/{item['id']}"
    client.post(f"{base}/service/approve")
    with db.tx() as conn:
        conn.execute("UPDATE vehicle_addons SET status = 'configured' WHERE id = ?", (item["id"],))
    general = client.get(f"{base}/settings").text
    assert (
        f"{base.split('/integrations')[0]}" and "/get/install.zip" not in general and "set-up guide" in general
    )  # no kept token: the guide builds it
    assert client.get(f"{base}/get/install.zip", follow_redirects=False).status_code == 303  # sent to the guide
    with db.tx() as conn:
        token = connectors.create_token(conn, "t", vid)
        token_id = conn.execute("SELECT id FROM api_tokens ORDER BY id DESC").fetchone()["id"]
        conn.execute("UPDATE vehicle_addons SET token_id = ? WHERE id = ?", (token_id, item["id"]))
        assert connectors.remember(conn, token_id, token)
    assert "/get/install.zip" in client.get(f"{base}/settings").text
    got = client.get(f"{base}/get/install.zip")
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(got.content)) as z:
        assert z.read("mod/x/x.cfg").decode().startswith(f"token={token}\n")


def test_a_button_can_open_a_step_of_the_set_up_flow_again(client, monkeypatch):
    from carassistant import pluginsvc

    monkeypatch.setattr(pluginsvc, "approved", lambda addon: True)
    manifest = {
        **FULL,
        "id": "step-demo",
        "buttons": [
            *FULL["buttons"],
            {"id": "login", "label": "Change the login", "step": "hello", "place": "settings"},
            {"id": "ghost", "label": "Nowhere", "step": "no-such-step", "place": "settings"},
        ],
    }
    parsed = addons.parse_package(json.dumps(manifest).encode())
    assert [b["step"] for b in parsed["buttons"] if b.get("step")] == ["hello"]  # an unknown step is dropped, with its button
    vid = create_vehicle(client)
    with db.tx() as conn:
        source = conn.execute("SELECT id FROM sources LIMIT 1").fetchone()["id"]
        pk = addons.add(conn, vid, parsed, source, "0" * 64)
        conn.execute("UPDATE vehicle_addons SET active = 1 WHERE id = ?", (pk,))
    page = client.get(f"/v/{slug(vid)}/integrations/{pk}/settings").text
    assert re.search(rf'href="[^"]*/integrations/{pk}/guide\?step=1"[^>]*title="Change the login"', page)


def test_the_install_page_can_say_that_a_package_sends_nothing_and_needs_no_token():
    t = i18n.translator("en")
    quiet = addons.parse_package(json.dumps({**_tokenless(), "interfaces": []}).encode())
    assert quiet["interfaces"] == []  # an explicit empty list is kept: the package says "nothing"
    seen = interfaces.preview({**quiet, "kind": "plugin"}, t)
    assert seen["declared_none"] and seen["no_token"]
    assert not [r for r in seen["rows"]["brings"] if r["name"] == t("pkg.row_token")]  # no "token for the Plugin API" row
    bundle = next(r for r in seen["rows"]["brings"] if r["path"] == "install.zip")
    assert "1 files and a connection file made for you" in bundle["note"]
    silent = addons.parse_package(json.dumps(_tokenless()).encode())
    assert (
        "interfaces" not in silent and not interfaces.preview({**silent, "kind": "plugin"}, t)["declared_none"]
    )  # saying nothing is not saying "nothing"
