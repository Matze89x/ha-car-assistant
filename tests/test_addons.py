"""Integrations and plugins belong to one vehicle: upload (manifest only), set up, settings, remove."""

import io
import json
import re
import zipfile

import pytest
from tests.test_web import create_vehicle, slug

from carassistant import addons, db

MANIFEST = {
    "id": "demo-plugin",
    "name": "Demo",
    "version": "1.0",
    "kind": "plugin",
    "settings": [{"key": "note", "label": "Note", "type": "text"}, {"key": "secret", "label": "Secret", "type": "password"}],
}


def upload(client, vid, data: bytes, name="plugin.json"):
    return client.post(f"/v/{slug(vid)}/integrations/upload", files={"package": (name, data, "application/octet-stream")})


def test_manifest_json_and_zip_are_cleaned():
    m = addons.parse_package(json.dumps({**MANIFEST, "homepage": "http://x", "evil": "<script>"}).encode())
    assert m["id"] == "demo-plugin" and m["homepage"] == "" and "evil" not in m and len(m["settings"]) == 2
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("plugin.json", json.dumps(MANIFEST))
        z.writestr("code.py", "import os")  # never read, never executed
    assert addons.parse_package(buf.getvalue())["name"] == "Demo"


@pytest.mark.parametrize("raw", [b"", b"not json", b"[]", json.dumps({"id": "A!"}).encode(), b"PK\x03\x04broken", b"x" * 200_000])
def test_bad_packages_are_rejected(raw):
    with pytest.raises(addons.AddonError):
        addons.parse_package(raw)


def test_upload_setup_settings_token_and_delete(client):
    vid = create_vehicle(client)
    assert client.get(f"/v/{slug(vid)}/plugins").status_code == 200
    assert upload(client, vid, json.dumps(MANIFEST).encode()).status_code == 303
    assert upload(client, vid, json.dumps(MANIFEST).encode()).headers["location"].endswith("addon.err_exists")  # once per car
    page = client.get(f"/v/{slug(vid)}/plugins").text
    assert "Demo" in page and "Settings" in page  # the card has a Settings button; the settings are a page of their own
    with db.tx() as conn:
        first = addons.list_for(conn, vid)[0]["id"]
    sp = client.get(f"/v/{slug(vid)}/integrations/{first}/settings")
    assert sp.status_code == 200 and "Set up" in sp.text and 'class="back-btn' in sp.text and f"/v/{slug(vid)}/plugins" in sp.text
    with db.tx() as conn:
        aid = addons.list_for(conn, vid)[0]["id"]
    r = client.post(f"/v/{slug(vid)}/integrations/{aid}/setup", data={"note": "hello", "secret": "s3"})
    token = re.search(r"ca_[A-Za-z0-9_-]{20,}", r.text).group(0)  # plugin: token shown once
    with db.tx() as conn:
        a = addons.list_for(conn, vid)[0]
        assert a["status"] == "configured" and a["vals"] == {"note": "hello", "secret": "s3"} and a["token_id"]
    assert (
        token not in client.get(f"/v/{slug(vid)}/plugins").text and "s3" not in client.get(f"/v/{slug(vid)}/plugins").text
    )  # secrets are never shown again
    client.post(f"/v/{slug(vid)}/integrations/{aid}/setup", data={"note": "changed", "secret": ""})  # blank password keeps the secret
    with db.tx() as conn:
        assert addons.list_for(conn, vid)[0]["vals"] == {"note": "changed", "secret": "s3"}
    assert client.post(f"/v/{slug(vid)}/integrations/{aid}/token").status_code == 200
    client.post(f"/v/{slug(vid)}/integrations/{aid}/delete")
    with db.tx() as conn:
        assert (
            addons.list_for(conn, vid) == [] and conn.execute("SELECT COUNT(*) FROM api_tokens").fetchone()[0] == 0
        )  # the token is revoked


def test_addons_are_per_vehicle_and_offered_optionally(client):
    first, second = create_vehicle(client, "A"), create_vehicle(client, "B")
    upload(client, first, json.dumps(MANIFEST).encode())
    with db.tx() as conn:
        assert len(addons.list_for(conn, first)) == 1 and addons.list_for(conn, second) == []
    assert "Webradio" not in client.get(f"/v/{slug(second)}/integrations/add").text  # nothing is built in any more, nothing added by itself
    assert f"/v/{slug(first)}/integrations" in client.get(f"/v/{slug(first)}/more").text
    with db.tx() as conn:
        conn.execute("DELETE FROM vehicles WHERE id = ?", (first,))
        assert conn.execute("SELECT COUNT(*) FROM vehicle_addons WHERE vehicle_id = ?", (first,)).fetchone()[0] == 0


def test_token_without_vehicle_is_refused(client):
    assert client.post("/integrations/api/tokens", data={"name": "x", "vehicle_id": ""}).headers["location"].endswith("err.choice")


def test_settings_window_has_all_field_types_and_keeps_values_only_after_save(client):
    from carassistant import addons, db

    manifest = {
        "id": "rich-plugin",
        "kind": "plugin",
        "name": "Rich",
        "settings": [
            {
                "key": "mode",
                "label": "Mode",
                "type": "select",
                "options": [{"value": "eco", "label": "Economy"}, {"value": "fast", "label": "Fast"}],
                "help": "How it runs",
            },
            {"key": "limit", "label": "Limit", "type": "number", "min": 1, "max": 10, "step": 1},
            {"key": "note", "label": "Note", "type": "textarea"},
            {"key": "empty_select", "label": "Broken", "type": "select"},
        ],
    }
    clean = addons.parse_package(json.dumps(manifest).encode())
    assert [f["type"] for f in clean["settings"]] == ["select", "number", "textarea", "text"]  # a select without options becomes text
    assert clean["settings"][0]["options"][1] == {"value": "fast", "label": "Fast"} and clean["settings"][1]["max"] == 10.0
    assert addons.clean_settings(clean, {"mode": "fast", "limit": "99", "note": "hi"}, {}) == {
        "mode": "fast",
        "limit": "10.0",
        "note": "hi",
        "empty_select": "",
    }
    assert (
        addons.clean_settings(clean, {"mode": "evil", "limit": "abc"}, {"mode": "eco"})["mode"] == "eco"
    )  # unknown choice keeps the old value

    client.post("/vehicles", data={"name": "Rich Car", "fuel_type": "petrol"})
    with db.tx() as conn:
        vid = conn.execute("SELECT id FROM vehicles").fetchone()["id"]
        addons.add(conn, vid, clean)
        row = addons.list_for(conn, vid)[0]
    card = client.get("/v/rich-car/plugins").text
    assert (
        f'href="/v/rich-car/integrations/{row["id"]}/settings"' in card or f"/integrations/{row['id']}/settings" in card
    )  # a link to the page
    assert "aset-dlg" not in card  # no pop-up window of its own: the settings are a page
    page = client.get(f"/v/rich-car/integrations/{row['id']}/settings").text
    assert "How it runs" in page and "<select" in page and 'type="number"' in page and "<textarea" in page
    assert card.count('class="addon-bar"') == 1 and "addon-menu" not in card  # a bar of three buttons with words, the rest under "More"
    assert (
        "icon-lbl" not in card and 'title="' not in card.split('class="addon-bar"')[1].split("</section>")[0]
    )  # no icon-only buttons, no hover tips


FILE_MANIFEST = {
    "id": "file-plugin",
    "kind": "plugin",
    "name": "File plugin",
    "settings": [
        {"key": "server", "label": "Address", "type": "text"},
        {"key": "interval", "label": "Interval", "type": "number"},
        {"key": "dns", "label": "DNS", "type": "text"},
    ],
    "connection_file": {
        "name": "link.cfg",
        "template": "server={server}\nvehicle={vehicle}\ntoken={token}\ninterval={interval}\ndns={dns}\n",
    },
}


def test_connection_file_manifest_is_cleaned():
    assert addons.parse_package(json.dumps(FILE_MANIFEST).encode())["connection_file"]["name"] == "link.cfg"
    for bad in (
        {"name": "../x", "template": "a"},
        {"name": "a.cfg", "template": ""},
        {"name": "a.cfg", "template": "x" * 3000},
        "text",
        {"name": 3},
    ):
        assert "connection_file" not in addons.parse_package(json.dumps({**FILE_MANIFEST, "connection_file": bad}).encode())


def test_connection_file_text_skips_empty_lines_and_cannot_add_lines():
    m = addons.parse_package(json.dumps(FILE_MANIFEST).encode())
    text = addons.connection_file_text(
        m, {"server": "https://car.example.com\nevil=1", "interval": "120", "dns": ""}, token="ca_abc", vehicle=7, url=""
    )
    assert text == "server=https://car.example.com evil=1\nvehicle=7\ntoken=ca_abc\ninterval=120\n"  # no dns= line, no extra line


def test_connection_file_download_after_setup(client):
    vid = create_vehicle(client)
    upload(client, vid, json.dumps(FILE_MANIFEST).encode())
    with db.tx() as conn:
        aid = addons.list_for(conn, vid)[0]["id"]
    r = client.post(f"/v/{slug(vid)}/integrations/{aid}/setup", data={"server": "https://car.example.com", "interval": "60", "dns": ""})
    token = re.search(r"ca_[A-Za-z0-9_-]{20,}", r.text).group(0)
    assert "Download link.cfg" in r.text
    f = client.post(f"/v/{slug(vid)}/integrations/{aid}/connection-file", data={"token": token})
    assert f.status_code == 200 and 'filename="link.cfg"' in f.headers["content-disposition"] and f.headers["cache-control"] == "no-store"
    assert f.text == f"server=https://car.example.com\nvehicle={vid}\ntoken={token}\ninterval=60\n"
    assert client.post(f"/v/{slug(vid)}/integrations/{aid}/connection-file", data={"token": ""}).status_code in (
        302,
        303,
    )  # no token, no file
    with db.tx() as conn:  # the token itself is never stored in the clear
        assert token not in json.dumps([dict(r) for r in conn.execute("SELECT * FROM vehicle_addons")])


def test_long_default_of_a_setting_is_kept():
    long_default = ",".join(f"service_{i}" for i in range(15))  # about 150 characters
    m = addons.parse_package(json.dumps({"id": "x-y", "settings": [{"key": "list", "label": "L", "default": long_default}]}).encode())
    assert m["settings"][0]["default"] == long_default


RICH = {
    "id": "rich-types",
    "kind": "plugin",
    "name": "Rich types",
    "settings": [
        {"key": "intro", "type": "section", "label": "Connection", "help": "How the device is reached"},
        {
            "key": "mode",
            "type": "radio",
            "label": "Mode",
            "options": [{"value": "a", "label": "A"}, {"value": "custom", "label": "Custom"}],
            "default": "a",
        },
        {"key": "custom_url", "type": "url", "label": "Address", "required": True, "show_if": {"key": "mode", "equals": "custom"}},
        {
            "key": "features",
            "type": "multiselect",
            "label": "Features",
            "options": [{"value": "news", "label": "News"}, {"value": "weather", "label": "Weather"}],
        },
        {"key": "volume", "type": "slider", "label": "Volume", "min": 0, "max": 10, "step": 1, "unit": "%"},
        {"key": "mail", "type": "email", "label": "Mail"},
        {"key": "wake", "type": "time", "label": "Wake"},
        {"key": "since", "type": "date", "label": "Since"},
        {"key": "tint", "type": "color", "label": "Tint"},
        {"key": "on", "type": "bool", "label": "On"},
        {"key": "hint", "type": "info", "label": "Note", "help": "Only shown text"},
    ],
}


def test_many_kinds_of_settings_are_stored_checked_and_handed_over_typed(client):
    vid = create_vehicle(client)
    assert upload(client, vid, json.dumps(RICH).encode()).status_code == 303
    with db.tx() as conn:
        item = addons.list_for(conn, vid)[0]
    kinds = [f["type"] for f in item["m"]["settings"]]
    assert kinds == ["section", "radio", "url", "multiselect", "slider", "email", "time", "date", "color", "bool", "info"]
    assert item["m"]["settings"][0]["key"] == "intro" and item["m"]["settings"][-1]["key"] == "hint"
    page = client.get(f"/v/{slug(vid)}/integrations/{item['id']}/settings").text
    for needle in (
        'type="radio"',
        'type="range"',
        'type="color"',
        'type="email"',
        'type="time"',
        'type="date"',
        'name="features__news"',
        "set-sec",
        "set-info",
        'data-showif-eq="custom"',
    ):
        assert needle in page, needle
    base = {
        "mode": "a",
        "features__news": "1",
        "volume": "55",
        "mail": "a@example.com",
        "wake": "07:30",
        "since": "2026-11-16",
        "tint": "#E2001A",
        "on": "1",
    }
    bad = client.post(f"/v/{slug(vid)}/integrations/{item['id']}/setup", data={**base, "mode": "custom", "mail": "nope", "wake": "25:99"})
    assert (
        bad.status_code == 400 and "valid e-mail" in bad.text and "Not a valid time" in bad.text and "Required field missing" in bad.text
    )  # nothing saved
    with db.tx() as conn:
        assert addons.list_for(conn, vid)[0]["status"] != "configured"
    ok = client.post(f"/v/{slug(vid)}/integrations/{item['id']}/setup", data=base)
    assert ok.status_code in (200, 303)
    with db.tx() as conn:
        item = addons.list_for(conn, vid)[0]
    assert (
        item["vals"]["features"] == "news"
        and item["vals"]["volume"] == "10.0"
        and item["vals"]["tint"] == "#e2001a"
        and item["vals"]["on"] == "1"
    )  # clamped, lower-case
    assert "custom_url" not in item["vals"] or item["vals"]["custom_url"] == ""  # a hidden (not applicable) field is not demanded
    typed = addons.typed_settings(item["m"], item["vals"])
    assert typed["on"] is True and typed["volume"] == 10 and typed["features"] == ["news"] and "intro" not in typed and "hint" not in typed


def test_an_existing_token_gets_the_connection_file_again_without_a_new_token(client):
    from carassistant import connectors

    vid = create_vehicle(client)
    manifest = {**FILE_MANIFEST, "id": "token-plugin"}
    upload(client, vid, json.dumps(manifest).encode())
    with db.tx() as conn:
        item = addons.list_for(conn, vid)[0]
        token = addons.set_up(conn, vid, addons.get(conn, vid, item["id"]), {"server": "https://car.example.com", "interval": "60"})
        before = conn.execute("SELECT COUNT(*), MAX(token_hash) FROM api_tokens").fetchone()
    url = f"/v/{slug(vid)}/integrations/{item['id']}/token/verify"
    page = client.get(f"/v/{slug(vid)}/integrations/{item['id']}/settings").text
    assert "I already have the token" in page and "New token" in page  # both ways side by side
    bad = client.post(url, data={"token": "ca_not-the-token"})
    assert bad.status_code == 400 and "not the token of this plugin" in bad.text and token not in bad.text
    assert client.post(url, data={"token": ""}).status_code == 400
    good = client.post(url, data={"token": token})
    assert (
        good.status_code == 200 and "attachment" in good.headers["content-disposition"] and token in good.text
    )  # in the file, nowhere else
    assert "no-store" in good.headers["cache-control"]
    with db.tx() as conn:
        after = conn.execute("SELECT COUNT(*), MAX(token_hash) FROM api_tokens").fetchone()
        assert connectors.token_matches(conn, item["token_id"] or conn.execute("SELECT id FROM api_tokens").fetchone()["id"], token)
    assert tuple(before) == tuple(after)  # no new token, the old one is still the one
    for _ in range(5):  # guessing is limited: five wrong tries in 15 minutes, then it stops - even for the right token
        client.post(url, data={"token": "ca_wrong"})
    assert client.post(url, data={"token": token}).status_code == 429


SETUP_MANIFEST = {
    **FILE_MANIFEST,
    "id": "guided",
    "connection_file": {"name": "link.cfg", "template": "url={url}\nvin={vin}\ntoken={token}\n"},
    "setup": {
        "requires": ["external_https", "vehicle_vin", "nonsense"],
        "steps": [
            {
                "id": "files",
                "title": "Token and file",
                "text": "1. Do **this**\n2. See [the docs](https://example.com/docs)\n\n<script>x</script>",
                "token": True,
                "connection_file": True,
                "l10n": {"de": {"title": "Token und Datei", "text": "Mach **das**"}},
            },
            {"id": "files", "title": "double id is dropped"},
            {"id": "BAD ID", "title": "bad id is dropped"},
        ],
    },
}


def test_setup_of_a_manifest_is_cleaned_and_its_text_is_safe():
    m = addons.parse_package(json.dumps(SETUP_MANIFEST).encode())
    assert m["setup"]["requires"] == ["external_https", "vehicle_vin"]  # only known requirements
    assert [s["id"] for s in m["setup"]["steps"]] == ["files"] and m["setup"]["steps"][0]["connection_file"] is True
    html = str(addons.render_text(m["setup"]["steps"][0]["text"]))
    assert "<ol><li>Do <b>this</b></li><li>See <a href=" in html and 'rel="noopener noreferrer"' in html
    assert "<script>" not in html and "&lt;script&gt;" in html  # everything else is escaped
    assert "<a " not in str(addons.render_text("[x](javascript:alert(1))")) and "<a " not in str(
        addons.render_text("[x](http://plain.example)")
    )
    assert "setup" not in addons.parse_package(json.dumps({**FILE_MANIFEST, "setup": {"steps": "no"}}).encode())


def test_the_connection_file_gets_the_vin_of_the_vehicle():
    m = addons.parse_package(json.dumps(SETUP_MANIFEST).encode())
    text = addons.connection_file_text(m, {}, token="ca_abc", vehicle=1, url="https://car.example.com", vin="WV1ZZZ2KZZZ012345")
    assert text == "url=https://car.example.com\nvin=WV1ZZZ2KZZZ012345\ntoken=ca_abc\n"
    assert "vin=" not in addons.connection_file_text(m, {}, token="ca_abc", vehicle=1, url="https://car.example.com")  # no VIN yet: no line


def test_the_guide_goes_in_three_fixed_steps_and_carries_the_token_without_keeping_it(client):
    vid = create_vehicle(client)
    manifest = {**SETUP_MANIFEST, "settings": [{**f, "advanced": True} if f["key"] == "dns" else f for f in SETUP_MANIFEST["settings"]]}
    upload(client, vid, json.dumps(manifest).encode())
    with db.tx() as conn:
        aid = addons.list_for(conn, vid)[0]["id"]
    url = f"/v/{slug(vid)}/integrations/{aid}"
    # step 1: the check; Next stays shut until the address and the VIN are there (also when step 2 is asked for directly)
    page = client.get(f"{url}/guide?step=2").text
    assert "Not saved yet" in page and "Not typed in yet" in page and "disabled>Next" in page and "guide/next" not in page
    client.post(f"/v/{vid}/edit", data={"name": "My Car", "vin": "WV1ZZZ2KZZZ012345", "fuel_type": "diesel"})
    from carassistant import config

    with db.tx() as conn:
        db.set_setting(conn, "ext.url", "https://car.example.com")
    config.forget_external()
    page = client.get(f"{url}/guide").text
    assert "WV1ZZZ2KZZZ012345" in page and "car.example.com" in page and f"{url}/guide?step=2" in page
    # step 2: no token yet - make one (shown once), the settings with the advanced one folded
    page = client.get(f"{url}/guide?step=2").text
    assert "Make a new token" in page and "guide-adv" in page and "Advanced settings" in page
    made = client.post(f"{url}/guide/token")
    token = re.search(r"ca_[A-Za-z0-9_-]{20,}", made.text).group(0)
    assert f'name="token" value="{token}"' in made.text  # carried to the next step inside the page
    settings = {"server": "https://car.example.com", "interval": "60", "dns": "", "token": token}
    wrong = client.post(f"{url}/guide/next", data={**settings, "interval": "abc"})
    assert wrong.status_code == 400  # nothing saved, the page comes back
    step3 = client.post(f"{url}/guide/next", data=settings)
    assert (
        step3.status_code == 200 and "link.cfg" in step3.text and f'name="token" value="{token}"' in step3.text and "Finish" in step3.text
    )
    f = client.post(f"{url}/guide/file", data={"token": token})
    assert f.text == f"url=https://car.example.com\nvin=WV1ZZZ2KZZZ012345\ntoken={token}\n"
    assert client.post(f"{url}/guide/file", data={"token": "ca_wrong"}).status_code == 400  # compared with the stored fingerprint
    with db.tx() as conn:  # the token itself is stored nowhere
        assert token not in json.dumps([dict(r) for r in conn.execute("SELECT * FROM vehicle_addons")])
    # again: step 2 knows the token (only its mark), a typed token carries on, a wrong one does not
    again = client.get(f"{url}/guide?step=2").text
    assert "This plugin has a token" in again and token not in again and "Keep using the existing token" in again
    assert client.post(f"{url}/guide/next", data={**settings, "token": "", "have_token": "ca_wrong"}).status_code == 400
    ok = client.post(f"{url}/guide/next", data={**settings, "token": "", "have_token": token})
    assert ok.status_code == 200 and f'name="token" value="{token}"' in ok.text
    # step 3 without a carried token asks for it once more
    bare = client.get(f"{url}/guide?step=3").text
    assert 'type="password"' in bare and "Type it once more" in bare


def test_the_guide_takes_over_a_token_the_device_already_has_and_then_keeps_it_fixed(client):
    vid = create_vehicle(client)
    upload(client, vid, json.dumps(SETUP_MANIFEST).encode())
    with db.tx() as conn:
        aid = addons.list_for(conn, vid)[0]["id"]
    client.post(f"/v/{vid}/edit", data={"name": "My Car", "vin": "WV1ZZZ2KZZZ012345", "fuel_type": "diesel"})
    with db.tx() as conn:
        db.set_setting(conn, "ext.url", "https://car.example.com")
    from carassistant import config

    config.forget_external()
    url = f"/v/{slug(vid)}/integrations/{aid}"
    assert "Use an existing token" in client.get(f"{url}/guide?step=2").text  # none in the app yet
    settings = {"server": "https://car.example.com", "interval": "60", "dns": ""}
    for bad in ("not-a-token", "ca_short"):
        assert client.post(f"{url}/guide/next", data={**settings, "adopt_token": bad}).status_code == 400
    mine = "ca_" + "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
    step3 = client.post(f"{url}/guide/next", data={**settings, "adopt_token": mine})
    assert step3.status_code == 200 and f'name="token" value="{mine}"' in step3.text
    assert client.get("/api/v1", headers={"Authorization": f"Bearer {mine}"}).status_code == 200  # it works as a token
    again = client.get(f"{url}/guide?step=2").text
    assert (
        "This plugin has a token" in again and mine not in again and "Use an existing token" not in again
    )  # fixed now, only its mark shows
    with db.tx() as conn:
        assert mine not in json.dumps([dict(r) for r in conn.execute("SELECT * FROM api_tokens")])  # only the fingerprint is stored
        before = conn.execute("SELECT COUNT(*) FROM api_tokens").fetchone()[0]
    assert (
        client.post(f"{url}/guide/next", data={**settings, "adopt_token": "ca_" + "ZyXwVuTsRqPoNmLkJiHgFeDcBa9876543210"}).status_code
        == 200
    )
    with db.tx() as conn:  # a second typed token is not taken while one exists
        assert conn.execute("SELECT COUNT(*) FROM api_tokens").fetchone()[0] == before


def test_the_set_up_guide_is_the_first_card_on_the_settings_page(client):
    vid = create_vehicle(client)
    upload(client, vid, json.dumps(SETUP_MANIFEST).encode())
    with db.tx() as conn:
        aid = addons.list_for(conn, vid)[0]["id"]
    page = client.get(f"/v/{slug(vid)}/integrations/{aid}/settings").text
    assert page.index(f"/integrations/{aid}/guide") < page.index('id="aform"')  # above the settings fields


def test_a_plugin_with_a_guide_offers_set_up_on_its_tile_until_it_is_set_up(client):
    vid = create_vehicle(client)
    upload(client, vid, json.dumps(SETUP_MANIFEST).encode())
    with db.tx() as conn:
        aid = addons.list_for(conn, vid)[0]["id"]
    tile = client.get(f"/v/{slug(vid)}/plugins").text
    assert (
        f'href="/v/{slug(vid)}/integrations/{aid}/guide"' in tile.replace("//v/", "/v/") or f"/integrations/{aid}/guide" in tile
    )  # not set up: the main action
    client.post(f"/v/{slug(vid)}/integrations/{aid}/setup", data={"server": "https://car.example.com", "interval": "60", "dns": ""})
    assert f"/integrations/{aid}/guide" not in client.get(f"/v/{slug(vid)}/plugins").text  # set up: the tile has its other actions again


def test_a_package_may_list_the_settings_the_guide_shows_and_the_others_keep_their_value(client):
    from carassistant import config

    vid = create_vehicle(client)
    steps = [
        {**SETUP_MANIFEST["setup"]["steps"][0], "settings": ["server", "nonsense", "server"]}
    ]  # listed: only "server"; unknown keys are dropped
    manifest = {
        **SETUP_MANIFEST,
        "id": "listed",
        "settings": [*SETUP_MANIFEST["settings"], {"key": "debug", "label": "Debug", "type": "bool", "default": "1"}],
        "setup": {**SETUP_MANIFEST["setup"], "steps": steps},
    }
    parsed = addons.parse_package(json.dumps(manifest).encode())
    assert parsed["setup"]["steps"][0]["settings"] == ["server"]
    upload(client, vid, json.dumps(manifest).encode())
    with db.tx() as conn:
        aid = addons.list_for(conn, vid)[0]["id"]
    url = f"/v/{slug(vid)}/integrations/{aid}"
    client.post(f"/v/{vid}/edit", data={"name": "My Car", "vin": "WV1ZZZ2KZZZ012345", "fuel_type": "diesel"})
    with db.tx() as conn:
        db.set_setting(conn, "ext.url", "https://car.example.com")
    config.forget_external()
    page = client.get(f"{url}/guide?step=2").text
    assert 'name="server"' in page and 'name="interval"' not in page and 'name="dns"' not in page and 'name="debug"' not in page
    token = re.search(r"ca_[A-Za-z0-9_-]{20,}", client.post(f"{url}/guide/token").text).group(0)
    step3 = client.post(f"{url}/guide/next", data={"server": "https://car.example.com", "token": token})
    assert step3.status_code == 200
    with db.tx() as conn:
        vals = addons.list_for(conn, vid)[0]["vals"]
    assert vals["server"] == "https://car.example.com" and vals["debug"] == "1"  # a switch that was not in the page is NOT switched off
    # a package that lists nothing keeps the old behaviour: every setting is in the guide
    plain = {**SETUP_MANIFEST, "id": "plain-all"}
    assert "settings" not in addons.parse_package(json.dumps(plain).encode())["setup"]["steps"][0]
