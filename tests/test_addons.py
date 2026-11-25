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
    assert card.count('class="addon-bar fb') == 1 and "addon-menu" not in card  # one bar at the bottom, nothing hidden under "More"
    assert "Uninstall" in card and card.count("addon-bar") == 1  # uninstalling stays on the card


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
    page2 = client.get(
        f"{url}/guide?step=2"
    ).text  # none in the app yet: the existing-token box is shown (input = adopt) and nothing is stored
    assert "Keep using the existing token" in page2 and 'name="adopt_token"' in page2 and 'value="saved"' not in page2
    settings = {"server": "https://car.example.com", "interval": "60", "dns": ""}
    for bad in ("not-a-token", "ca_short"):
        assert client.post(f"{url}/guide/next", data={**settings, "adopt_token": bad}).status_code == 400
    mine = "ca_" + "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
    step3 = client.post(f"{url}/guide/next", data={**settings, "adopt_token": mine})
    assert step3.status_code == 200 and f'name="token" value="{mine}"' in step3.text
    assert client.get("/api/v1", headers={"Authorization": f"Bearer {mine}"}).status_code == 200  # it works as a token
    again = client.get(f"{url}/guide?step=2").text
    assert "This plugin has a token" in again and mine not in again and 'name="have_token"' in again  # fixed now, only its mark shows
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


def test_a_service_may_read_and_change_only_the_settings_the_package_marks_writable(client):
    vid = create_vehicle(client)
    manifest = {
        "id": "own-settings",
        "kind": "plugin",
        "name": "Own settings",
        "settings": [
            {
                "key": "mode",
                "label": "Mode",
                "type": "select",
                "options": [{"value": "eco", "label": "Eco"}, {"value": "fast", "label": "Fast"}],
                "service_writable": True,
            },
            {"key": "interval", "label": "Interval", "type": "number", "min": 5, "max": 600, "service_writable": True},
            {"key": "debug", "label": "Debug", "type": "bool", "service_writable": True},
            {"key": "secret", "label": "Secret", "type": "password", "service_writable": True},
            {"key": "owner_only", "label": "Owner only", "type": "text"},
            {"key": "status", "label": "Status", "type": "value"},
        ],
    }
    parsed = addons.parse_package(json.dumps(manifest).encode())
    assert [f["key"] for f in parsed["settings"] if f.get("service_writable")] == ["mode", "interval", "debug", "secret"]
    upload(client, vid, json.dumps(manifest).encode())
    with db.tx() as conn:
        addon = addons.list_for(conn, vid)[0]
        token = addons.new_token(conn, vid, addon)
    h = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1", headers=h).json()["features"] == [
        "measured_at",
        "plugin-settings",
        "oil-change",
        "trip-summary",
        "position-names",
        "refuel-notify",
    ]
    got = client.get(f"/api/v1/vehicles/{vid}/plugin-settings", headers=h).json()
    assert got["writable"] == ["debug", "interval", "mode", "secret", "status"] and got["settings"]["owner_only"] == ""
    put = lambda values: client.put(f"/api/v1/vehicles/{vid}/plugin-settings", headers=h, json={"values": values})  # noqa: E731
    r = put({"mode": "fast", "interval": 30, "debug": True, "secret": "s3cret", "status": "Running until 14:20"})
    assert r.status_code == 200 and r.json()["changed"] == ["debug", "interval", "mode", "secret", "status"]
    got = client.get(f"/api/v1/vehicles/{vid}/plugin-settings", headers=h).json()["settings"]
    assert got["mode"] == "fast" and got["interval"] == 30 and got["debug"] is True and got["status"] == "Running until 14:20"
    assert got["secret"] == "***"  # a password is never readable
    with db.tx() as conn:
        assert "s3cret" not in json.dumps([dict(r) for r in conn.execute("SELECT settings FROM vehicle_addons")])  # encrypted at rest
        logs = [x["message"] for x in conn.execute("SELECT message FROM vehicle_logs WHERE vehicle_id = ?", (vid,))]
    assert any("settings changed by the plugin" in m and "s3cret" not in m for m in logs)  # names in the log, never values
    refused = put({"owner_only": "x"})
    assert refused.status_code == 403 and refused.json()["error"] == "not_writable"
    bad = put({"interval": "abc"})
    assert bad.status_code == 422 and "interval" in bad.json()["fields"]
    assert put({"interval": 99999}).status_code == 200  # like the form: a number is held to its bounds
    assert client.get(f"/api/v1/vehicles/{vid}/plugin-settings", headers=h).json()["settings"]["interval"] == 600
    put({"interval": 30})
    assert put({"mode": "nonsense"}).status_code == 422
    assert (
        client.get(f"/api/v1/vehicles/{vid}/plugin-settings", headers=h).json()["settings"]["interval"] == 30
    )  # nothing stored by a wrong call
    assert put({"mode": "eco", "interval": 20}).status_code == 200
    # the list of writable keys belongs to what the administrator approves
    assert addons.approval_fingerprint({**parsed, "service": {"entry": "x"}}) != addons.approval_fingerprint(
        {
            **parsed,
            "service": {"entry": "x"},
            "settings": [dict(f, service_writable=False) if f["type"] != "value" else f for f in parsed["settings"]],
        }
    )


def test_a_guide_step_may_open_a_page_of_the_plugins_service(client):
    manifest = {
        **SETUP_MANIFEST,
        "id": "page-step",
        "service": {"entry": "app.py", "routes": [{"prefix": "/ext/setup/", "public": False}]},
        "pages": [{"id": "wizard", "kind": "frame", "title": "Wizard", "route": "/ext/setup/"}],
        "setup": {
            **SETUP_MANIFEST["setup"],
            "steps": [
                SETUP_MANIFEST["setup"]["steps"][0],
                {"id": "extra", "title": "Pick a mode", "text": "Do this **now**.", "page": "wizard"},
                {"id": "bad", "title": "unknown page is dropped", "page": "nope"},
            ],
        },
    }
    parsed = addons.parse_package(json.dumps(manifest).encode())
    steps = {s["id"]: s for s in parsed["setup"]["steps"]}
    assert steps["extra"].get("page") == "wizard" and "page" not in steps["bad"]


def test_a_package_may_name_one_of_its_frame_pages_as_its_own_settings_page(client):
    base = {
        "id": "own-page",
        "kind": "plugin",
        "name": "Own page",
        "service": {"entry": "app.py", "routes": [{"prefix": "/ext/s/", "public": False}]},
        "pages": [{"id": "cfg", "kind": "frame", "title": "Config", "route": "/ext/s/"}],
        "settings": [{"key": "mode", "label": "Mode", "type": "text"}],
    }
    assert addons.parse_package(json.dumps({**base, "settings_page": "cfg"}).encode())["settings_page"] == "cfg"
    assert "settings_page" not in addons.parse_package(json.dumps({**base, "settings_page": "nope"}).encode())  # only an own frame page
    assert "settings_page" not in addons.parse_package(json.dumps(base).encode())


def test_step_two_has_three_boxes_and_next_does_the_chosen_one(client):
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
    settings = {"server": "https://car.example.com", "interval": "60", "dns": ""}
    first = client.get(f"{url}/guide?step=2").text
    assert first.count('name="token_mode"') == 2 and 'value="new" checked' in first  # no token yet: existing + new, "new" preselected
    made = client.post(f"{url}/guide/next", data={**settings, "token_mode": "new"})
    token = re.search(r"ca_[A-Za-z0-9_-]{20,}", made.text).group(0)
    assert made.status_code == 200 and "link.cfg" in made.text
    again = client.get(f"{url}/guide?step=2").text
    assert 'value="saved" checked' in again and "<code>•••• " in again  # a kept token is offered and preselected
    saved = client.post(f"{url}/guide/next", data={**settings, "token_mode": "saved"})
    assert saved.status_code == 200 and f'name="token" value="{token}"' in saved.text
    renewed = client.post(f"{url}/guide/next", data={**settings, "token_mode": "new"})  # the old token becomes invalid
    token2 = re.search(r"ca_[A-Za-z0-9_-]{20,}", renewed.text).group(0)
    assert token2 != token and client.get("/api/v1", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert client.get("/api/v1", headers={"Authorization": f"Bearer {token2}"}).status_code == 200
    kept = client.post(f"{url}/guide/next", data={**settings, "token_mode": "existing", "have_token": token2})
    assert kept.status_code == 200 and f'name="token" value="{token2}"' in kept.text
    wrong = client.post(f"{url}/guide/next", data={**settings, "token_mode": "existing", "have_token": "ca_wrong"})
    assert wrong.status_code == 400


TABBED = {
    "id": "tabbed",
    "name": "Tabbed",
    "version": "1.0",
    "kind": "plugin",
    "settings": [
        {"key": "name", "label": "Name", "type": "text"},
        {"type": "tab", "id": "news", "label": "News", "icon": "bell-outline", "l10n": {"de": {"label": "Nachrichten"}}},
        {"key": "feed", "label": "Feed", "type": "url", "required": True},
        {"type": "section", "label": "More"},
        {"key": "count", "label": "Count", "type": "number"},
        {"type": "tab", "id": "weather", "label": "Weather", "icon": "no-such-icon"},
        {"key": "city", "label": "City", "type": "text"},
        {"type": "tab", "id": "news", "label": "Twice"},  # the same id again: dropped
    ],
}


def test_a_tab_element_splits_the_settings_and_a_package_without_tabs_is_unchanged():
    m = addons.parse_package(json.dumps(TABBED).encode())
    kinds = [(f["type"], f.get("id") or f["key"]) for f in m["settings"]]
    assert kinds.count(("tab", "news")) == 1 and ("tab", "weather") in kinds
    tabs = addons.settings_tabs(m["settings"])
    assert [g["id"] for g in tabs] == ["general", "news", "weather"]
    assert [f["key"] for f in tabs[0]["fields"]] == ["name"] and tabs[0]["implicit"]
    assert [f["key"] for f in tabs[1]["fields"] if f["type"] != "section"] == ["feed", "count"]
    assert tabs[1]["icon"] == "bell-outline" and tabs[2]["icon"] == ""  # an icon the app does not know is dropped
    assert addons.settings_tabs(addons.parse_package(json.dumps(MANIFEST).encode())["settings"]) == []  # no tab: one list as before
    only_one = {**TABBED, "settings": [{"type": "tab", "id": "a", "label": "A"}, {"key": "x", "type": "text", "label": "X"}]}
    assert addons.settings_tabs(addons.parse_package(json.dumps(only_one).encode())["settings"]) == []  # one tab = no tab bar
    first = {**TABBED, "settings": [{"type": "tab", "id": "general", "label": "Main"}, *TABBED["settings"][1:5]]}
    ids = [g["id"] for g in addons.settings_tabs(addons.parse_package(json.dumps(first).encode())["settings"])]
    assert ids == ["general", "news"]  # a first tab of its own takes the place of the implicit one
    many = {**TABBED, "settings": [{"type": "tab", "id": f"t{i}", "label": str(i)} for i in range(12)]}
    assert sum(f["type"] == "tab" for f in addons.parse_package(json.dumps(many).encode())["settings"]) == addons.MAX_TABS


def test_the_settings_page_shows_tabs_with_the_cards_in_the_first_one_and_keeps_every_value(client):
    vid = create_vehicle(client)
    upload(client, vid, json.dumps(TABBED).encode())
    with db.tx() as conn:
        aid = addons.list_for(conn, vid)[0]["id"]
    url = f"/v/{slug(vid)}/integrations/{aid}"
    page = client.get(f"{url}/settings").text
    assert "data-set-tabs" in page and page.count("data-tab-panel=") == 3
    assert re.search(r'data-tab-panel="news" hidden', page) and 'data-tab-panel="general" hidden' not in page
    assert page.count('data-tabfor="general"') >= 1 and 'name="_n' not in page  # a tab is never a form field
    # a missing required value sends you to the tab that has the error, nothing is saved
    bad = client.post(f"{url}/setup", data={"name": "x", "feed": ""})
    assert bad.status_code == 400
    assert re.search(r'data-tab-panel="general" hidden', bad.text) and 'data-tab-panel="news" hidden' not in bad.text
    assert 'class="err"' in bad.text or " err" in bad.text
    ok = client.post(f"{url}/setup", data={"name": "x", "feed": "https://example.com/rss", "count": "3", "city": "Berlin"})
    assert ok.status_code in (200, 303)
    with db.tx() as conn:
        vals = addons.list_for(conn, vid)[0]["vals"]
    assert vals["feed"] == "https://example.com/rss" and vals["city"] == "Berlin" and vals["name"] == "x"
    assert not any(k.startswith("_n") for k in vals)
    plain = upload(client, vid, json.dumps({**MANIFEST, "id": "no-tabs"}).encode())
    assert plain.status_code in (200, 303)
    with db.tx() as conn:
        other = next(a["id"] for a in addons.list_for(conn, vid) if a["addon_id"] == "no-tabs")
    assert "data-set-tabs" not in client.get(f"/v/{slug(vid)}/integrations/{other}/settings").text


def test_a_list_setting_can_be_sorted_and_the_saved_order_is_the_order_of_the_rows(client):
    manifest = {
        "id": "feeds",
        "name": "Feeds",
        "version": "1",
        "kind": "plugin",
        "settings": [{"key": "feeds", "type": "list", "label": "News feeds", "name_label": "Name", "value_label": "RSS address"}],
    }
    vid = create_vehicle(client)
    upload(client, vid, json.dumps(manifest).encode())
    with db.tx() as conn:
        aid = addons.list_for(conn, vid)[0]["id"]
    url = f"/v/{slug(vid)}/integrations/{aid}"
    client.post(
        f"{url}/setup",
        data={"feeds__0n": "A", "feeds__0v": "https://a.example/rss", "feeds__1n": "B", "feeds__1v": "https://b.example/rss"},
    )
    page = client.get(f"{url}/settings").text
    assert page.count('class="grip"') == 3  # a handle on each of the two rows and on the <template> a new row is made from
    assert "<template data-lf-row>" in page and 'name="feeds__#n"' in page
    # the page numbers the rows again after a move: the numbers (and so the saved order) follow the rows
    client.post(
        f"{url}/setup",
        data={"feeds__0n": "B", "feeds__0v": "https://b.example/rss", "feeds__1n": "A", "feeds__1v": "https://a.example/rss"},
    )
    with db.tx() as conn:
        rows = addons.service_settings(addons.get(conn, vid, aid))["feeds"]
    assert [r["name"] for r in rows] == ["B", "A"]


def test_a_list_can_offer_ready_made_rows_keep_a_minimum_and_start_with_rows(client):
    """``templates`` (a select and a button that appends the chosen row), ``min_rows`` (saving with fewer is refused) and ``default`` as rows."""
    manifest = {
        "id": "keys",
        "name": "Keys",
        "version": "1",
        "kind": "plugin",
        "settings": [
            {
                "key": "entries",
                "type": "list",
                "label": "Entries",
                "min_rows": 1,
                "default": [{"name": "Comfort", "value": "comfort"}, {"name": "Sport | Dynamic", "value": "sport"}],
                "templates": [
                    {
                        "label": "Comfort <-> Dynamic",
                        "name": "ADS Comfort Dynamic",
                        "value": "comfort_dynamic",
                        "l10n": {"de": {"label": "Komfort <-> Dynamisch"}},
                    },
                    {"label": "", "name": "Eco", "value": "eco"},
                    {"label": "no row", "name": "", "value": ""},
                ],
            }
        ],
    }
    parsed = addons.parse_package(json.dumps(manifest).encode())
    f = parsed["settings"][0]
    assert f["min_rows"] == 1 and [t["value"] for t in f["templates"]] == ["comfort_dynamic", "eco"] and f["templates"][1]["label"] == "Eco"
    assert f["default"] == "Comfort | comfort\nSport Dynamic | sport"  # the stored form of the rows; a bar inside a text is not a separator
    vid = create_vehicle(client)
    upload(client, vid, json.dumps(manifest).encode())
    with db.tx() as conn:
        aid = addons.list_for(conn, vid)[0]["id"]
    url = f"/v/{slug(vid)}/integrations/{aid}"
    page = client.get(f"{url}/settings").text
    assert (
        'data-min="1"' in page and 'class="lf-pick"' in page and 'data-value="comfort_dynamic"' in page and 'value="Comfort"' in page
    )  # the start rows
    refused = client.post(f"{url}/setup", data={})  # an empty list: nothing is saved, the page says so
    assert refused.status_code == 400 and "at least the number of rows" in refused.text
    ok = client.post(f"{url}/setup", data={"entries__0n": "Eco", "entries__0v": "eco"}, follow_redirects=False)
    assert ok.status_code in (200, 303)
    with db.tx() as conn:
        assert [r["name"] for r in addons.service_settings(addons.get(conn, vid, aid))["entries"]] == ["Eco"]


def test_a_list_row_can_have_more_cells_than_a_name_and_a_value(client, monkeypatch):
    """``columns`` (at most 3): a second line, a logo address ... Stored as ``name | value | cell | cell``, given to the service as keys of the row."""
    from carassistant import config

    manifest = {
        "id": "stations",
        "name": "Stations",
        "version": "1",
        "kind": "plugin",
        "settings": [
            {
                "key": "stations",
                "type": "list",
                "label": "Stations",
                "name_label": "Name",
                "value_label": "Stream address",
                "min_rows": 1,
                "columns": [
                    {"key": "second", "label": "Second line", "max": 10, "l10n": {"de": {"label": "Zweite Zeile"}}},
                    {"key": "logo", "label": "Logo address"},
                    {"key": "name", "label": "taken"},  # a key of the row itself
                    {"key": "logo", "label": "twice"},
                    {"key": "Bad Key", "label": "bad"},
                    {"key": "extra", "label": "Third", "max": 500},
                    {"key": "fourth", "label": "Fourth"},  # only three
                ],
                "default": [{"name": "Radio A", "value": "https://a.example/s", "second": "News", "logo": "https://a.example/l.png"}],
                "templates": [
                    {
                        "label": "Radio B",
                        "name": "Radio B",
                        "value": "https://b.example/s",
                        "second": "Pop",
                        "logo": "https://b.example/l.png",
                    }
                ],
            }
        ],
    }
    f = addons.parse_package(json.dumps(manifest).encode())["settings"][0]
    assert [c["key"] for c in f["columns"]] == ["second", "logo", "extra"] and [c["max"] for c in f["columns"]] == [10, 120, 500]
    assert (
        f["default"] == "Radio A | https://a.example/s | News | https://a.example/l.png | "
    )  # the stored form: the third cell stays empty
    assert f["templates"][0]["cells"] == ["Pop", "https://b.example/l.png", ""]
    plain = addons.parse_package(json.dumps({**manifest, "settings": [{"key": "l", "type": "list", "label": "L"}]}).encode())["settings"][0]
    assert "columns" not in plain  # a list without columns is the list it always was
    assert addons.list_rows("A | b | c") == [{"name": "A", "value": "b | c"}]  # ... and its value still takes the rest of the line
    assert addons.list_rows("A | b | c", f["columns"]) == [{"name": "A", "value": "b", "second": "c", "logo": "", "extra": ""}]
    assert addons.list_rows(" | | | x | ", f["columns"]) == [
        {"name": "", "value": "", "second": "", "logo": "x", "extra": ""}
    ]  # a cell alone makes a row
    vid = create_vehicle(client)
    upload(client, vid, json.dumps(manifest).encode())
    with db.tx() as conn:
        aid = addons.list_for(conn, vid)[0]["id"]
    url = f"/v/{slug(vid)}/integrations/{aid}"
    page = client.get(f"{url}/settings").text
    assert (
        'name="stations__0c0"' in page
        and 'name="stations__0c1"' in page
        and 'name="stations__#c2"' in page
        and 'class="lf-in lf-cols"' in page
    )
    assert (
        'value="News"' in page
        and 'value="https://a.example/l.png"' in page
        and 'data-c0="Pop"' in page
        and 'placeholder="Second line"' in page
    )
    monkeypatch.setattr(config, "language", lambda: "de")
    assert (
        'placeholder="Zweite Zeile"' in client.get(f"{url}/settings").text
        and 'placeholder="Logo address"' in client.get(f"{url}/settings").text
    )
    monkeypatch.setattr(config, "language", lambda: "en")
    data = {
        "stations__0n": "B | b",
        "stations__0v": "https://b.example/s",
        "stations__0c0": "A very long second line",
        "stations__0c1": "https://b.example/l.png",
        "stations__1c1": "only a logo",
    }
    too_long = client.post(f"{url}/setup", data=data)  # a text longer than its limit is refused with a message, never cut quietly
    assert too_long.status_code == 400 and "longer than it may be" in too_long.text and "Nothing was saved" in too_long.text
    with db.tx() as conn:
        assert addons.service_settings(addons.get(conn, vid, aid))["stations"] != addons.list_rows(
            "B b | x", f["columns"]
        )  # nothing came of it
    data["stations__0c0"] = "A long line"[:10]
    assert client.post(f"{url}/setup", data=data, follow_redirects=False).status_code in (200, 303)
    with db.tx() as conn:
        addon = addons.get(conn, vid, aid)
        rows = addons.service_settings(addon)["stations"]
    assert rows[0] == {
        "name": "B b",
        "value": "https://b.example/s",
        "second": "A long lin",
        "logo": "https://b.example/l.png",
        "extra": "",
    }
    assert rows[1] == {"name": "", "value": "", "second": "", "logo": "only a logo", "extra": ""} and len(rows) == 2
    assert client.post(f"{url}/setup", data={"stations__0c0": ""}).status_code == 400  # min_rows: an empty row is no row


def test_the_limits_of_the_cells_of_a_list_row_can_be_raised_to_500(client):
    """``columns[].max`` and ``value_max`` up to 500 (a stream address, a logo address); the name stays at 80."""
    manifest = {
        "id": "long-cells",
        "name": "Long cells",
        "version": "1",
        "kind": "plugin",
        "settings": [
            {
                "key": "stations",
                "type": "list",
                "label": "Stations",
                "value_max": 255,
                "columns": [{"key": "logo", "label": "Logo", "max": 500}, {"key": "second", "label": "Second", "max": 501}],
            },
            {"key": "feeds", "type": "list", "label": "Feeds", "value_max": 501},
        ],
    }
    stations, feeds = addons.parse_package(json.dumps(manifest).encode())["settings"]
    assert stations["value_max"] == 255 and [c["max"] for c in stations["columns"]] == [500, 120]  # beyond 500: the default
    assert "value_max" not in feeds  # beyond 500 is not read: the value of a list keeps its 200
    vid = create_vehicle(client)
    upload(client, vid, json.dumps(manifest).encode())
    with db.tx() as conn:
        aid = addons.list_for(conn, vid)[0]["id"]
    url = f"/v/{slug(vid)}/integrations/{aid}"
    assert 'maxlength="255"' in client.get(f"{url}/settings").text  # the page stops typing at the limit
    stream, logo = "https://s.example/" + "a" * 237, "https://l.example/" + "b" * 482  # 255 and 500 characters
    ok = client.post(f"{url}/setup", data={"stations__0n": "R", "stations__0v": stream, "stations__0c0": logo}, follow_redirects=False)
    assert ok.status_code in (200, 303)
    with db.tx() as conn:
        row = addons.service_settings(addons.get(conn, vid, aid))["stations"][0]
    assert row["value"] == stream and row["logo"] == logo  # whole, not cut
    for field, text in (("0v", stream + "x"), ("0c0", logo + "x"), ("0n", "n" * 81)):
        r = client.post(f"{url}/setup", data={"stations__0n": "R", "stations__0v": stream, f"stations__{field}": text})
        assert r.status_code == 400 and "longer than it may be" in r.text, field
    assert client.post(f"{url}/setup", data={"feeds__0n": "F", "feeds__0v": "x" * 201}).status_code == 400  # every list: refused, not cut


def test_the_docs_of_a_package_keep_their_paragraphs_and_come_in_the_language_of_the_page(client):
    manifest = {
        "id": "docs-demo",
        "name": "Docs",
        "version": "1",
        "kind": "plugin",
        "settings": [{"key": "a", "type": "text", "label": "A"}],
        "docs": "WHAT IT IS\nA  plugin.\n\n\nSAFETY\nNothing leaves the car.",
        "l10n": {"de": {"docs": "WAS ES IST\nEin Plugin.\n\nSICHERHEIT\nNichts verlaesst das Auto."}},
    }
    parsed = addons.parse_package(json.dumps(manifest).encode())
    assert parsed["docs"] == "WHAT IT IS\nA plugin.\n\nSAFETY\nNothing leaves the car."
    assert parsed["l10n"]["de"]["docs"].startswith("WAS ES IST\nEin Plugin.\n\nSICHERHEIT")
    vid = create_vehicle(client)
    upload(client, vid, json.dumps(manifest).encode())
    with db.tx() as conn:
        aid = addons.list_for(conn, vid)[0]["id"]
    assert (
        "WHAT IT IS\nA plugin." in client.get(f"/v/{slug(vid)}/integrations/{aid}/info").text
        or "WHAT IT IS" in client.get(f"/v/{slug(vid)}/integrations/{aid}/info").text
    )


def test_a_plugin_may_name_its_set_up_guide_and_without_a_name_nothing_changes(client):
    vid = create_vehicle(client)
    named = {
        **SETUP_MANIFEST,
        "id": "named-guide",
        "setup": {
            **SETUP_MANIFEST["setup"],
            "title": "Install & uninstall on the car",
            "l10n": {"de": {"title": "Am Auto installieren & deinstallieren"}},
        },
    }
    parsed = addons.parse_package(json.dumps(named).encode())["setup"]
    assert parsed["title"] == "Install & uninstall on the car" and parsed["l10n"]["de"]["title"].startswith("Am Auto")
    upload(client, vid, json.dumps(named).encode())
    upload(client, vid, json.dumps({**SETUP_MANIFEST, "id": "plain-guide"}).encode())
    with db.tx() as conn:
        by_id = {a["addon_id"]: a["id"] for a in addons.list_for(conn, vid)}
    tile = client.get(f"/v/{slug(vid)}/plugins").text
    assert "Install &amp; uninstall on the car" in tile  # the main button of a plugin that is not set up yet
    assert "Install &amp; uninstall on the car" in client.get(f"/v/{slug(vid)}/integrations/{by_id['named-guide']}/settings").text
    assert "Install &amp; uninstall on the car" in client.get(f"/v/{slug(vid)}/integrations/{by_id['named-guide']}/guide").text
    plain = client.get(f"/v/{slug(vid)}/integrations/{by_id['plain-guide']}/settings").text
    assert (
        "Install &amp; uninstall" not in plain and "Set up" in plain
    )  # no name: the app's own name stays (the same word as the button on the tile)


def test_a_settings_page_may_have_twelve_tabs_and_the_bar_scrolls():
    many = {**TABBED, "id": "twelve", "settings": [{"type": "tab", "id": f"t{i}", "label": f"Tab {i}"} for i in range(14)]}
    tabs = [f for f in addons.parse_package(json.dumps(many).encode())["settings"] if f["type"] == "tab"]
    assert len(tabs) == 12 == addons.MAX_TABS


def test_a_list_value_can_be_a_choice_and_an_old_value_is_kept(client):
    """``value_options`` makes the value cell of a row a choice (the stored row stays ``name | value | ...``); a stored cell that does not fit its
    column any more (an old text in a date column, a value that is no choice any more) is shown as an old value and stays stored - never emptied or
    dropped quietly on the next save - while a NEW entry that does not fit is still refused."""
    manifest = {
        "id": "choice-list",
        "name": "Choice list",
        "version": "1",
        "kind": "plugin",
        "settings": [
            {
                "key": "pairs",
                "type": "list",
                "label": "Pairs",
                "value_label": "Profile",
                "value_options": [
                    {"value": "comfort_dynamic", "label": "Comfort / Dynamic", "l10n": {"de": {"label": "Komfort / Dynamisch"}}},
                    {"value": "eco", "label": "Eco"},
                    {"value": "no,comma", "label": "dropped: a comma"},
                ],
                "columns": [
                    {"key": "since", "label": "Since", "type": "date"},
                    {"key": "mode", "label": "Mode", "type": "select", "options": [{"value": "on", "label": "On"}]},
                ],
            }
        ],
    }
    field = addons.parse_package(json.dumps(manifest).encode())["settings"][0]
    assert [o["value"] for o in field["value_options"]] == ["comfort_dynamic", "eco"]  # a value with a comma is no usable choice
    assert field["value_options"][0]["l10n"]["de"]["label"] == "Komfort / Dynamisch" and "l10n" not in field["value_options"][1]
    vid = create_vehicle(client)
    upload(client, vid, json.dumps(manifest).encode())
    with db.tx() as conn:
        aid = addons.list_for(conn, vid)[0]["id"]
    url = f"/v/{slug(vid)}/integrations/{aid}"
    page = client.get(f"{url}/settings").text
    assert '<select name="pairs__#v"' in page and "Comfort / Dynamic" in page and "old value" not in page  # the row to add is a choice

    def row() -> dict:
        with db.tx() as conn:
            return addons.service_settings(addons.get(conn, vid, aid))["pairs"][0]

    ok = client.post(
        f"{url}/setup",
        data={"pairs__0n": "ADS", "pairs__0v": "eco", "pairs__0c0": "2026-01-02", "pairs__0c1": "on"},
        follow_redirects=False,
    )
    assert ok.status_code in (200, 303) and row()["value"] == "eco" and row()["since"] == "2026-01-02"  # the service gets the value as text
    new_bad = {"pairs__0n": "ADS", "pairs__0v": "turbo", "pairs__0c0": "2026-01-02", "pairs__0c1": "on"}
    assert client.post(f"{url}/setup", data=new_bad).status_code == 400  # a new value that is no choice: refused as before

    with db.tx() as conn:  # data from before: a date in the old notation, a mode that is no choice, a value that is no choice
        conn.execute("UPDATE vehicle_addons SET settings = ? WHERE id = ?", (json.dumps({"pairs": "ADS | Off | 201701010000 | gone"}), aid))
    page = client.get(f"{url}/settings").text
    assert page.count("old value") >= 3 and "201701010000" in page and "Off" in page and "gone" in page  # shown, not empty
    assert 'class="lf-old"' in page and "lf-oldnote" in page
    same = {"pairs__0n": "ADS", "pairs__0v": "Off", "pairs__0c0": "201701010000", "pairs__0c1": "gone"}
    assert client.post(f"{url}/setup", data=same, follow_redirects=False).status_code in (200, 303)
    assert (row()["value"], row()["since"], row()["mode"]) == ("Off", "201701010000", "gone")  # saved unchanged: still there
    assert client.post(f"{url}/setup", data={**same, "pairs__0v": "Other"}).status_code == 400  # another bad value is a new one
    assert client.post(f"{url}/setup", data={**same, "pairs__0c0": "2026-02-30x"}).status_code == 400
    fixed = {**same, "pairs__0v": "eco", "pairs__0c0": "2026-03-04", "pairs__0c1": "on"}
    assert client.post(f"{url}/setup", data=fixed, follow_redirects=False).status_code in (200, 303)
    assert (row()["value"], row()["since"], row()["mode"]) == ("eco", "2026-03-04", "on")  # a new choice replaces the old value
