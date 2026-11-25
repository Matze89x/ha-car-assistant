import json

import pytest

from carassistant import addons, connectors, db, sources

REPO = {
    "integrations/index.json": json.dumps({"packages": []}),
    "plugins/index.json": json.dumps({"packages": [{"id": "demo-one", "name": "Demo One", "description": "First", "version": "1.9"}]}),
    "plugins/demo-one/plugin.json": json.dumps(
        {"id": "demo-one", "name": "Demo One", "version": "1.9", "description": "First", "settings": []}
    ),
}


@pytest.fixture(autouse=True)
def fake_source(monkeypatch):
    """No test talks to the network: a source answers from this dict (path -> text); a missing path is 'not found'."""
    state = {"files": dict(REPO), "seen": []}

    def fake_http(url, headers, check_host, limit=0):
        state["seen"].append((url, headers))
        for path, text in state["files"].items():
            if url.endswith("/" + path.replace(" ", "%20")):
                return text.encode()
        raise sources.SourceError("err.src_missing")

    monkeypatch.setattr(sources, "_http", fake_http)
    return state


def _car(client):
    client.post("/vehicles", data={"name": "Src Car", "fuel_type": "petrol"})
    with db.tx() as conn:
        row = conn.execute("SELECT id, slug FROM vehicles ORDER BY id DESC LIMIT 1").fetchone()
    return row["id"], row["slug"]


def _default_id():
    with db.tx() as conn:
        return conn.execute("SELECT id FROM sources WHERE is_default = 1").fetchone()[0]


def test_first_source_is_the_projects_package_repository(client):
    with db.tx() as conn:
        for kind in sources.KINDS:  # in both lists
            assert [(r["url"], r["is_default"]) for r in sources.listing(conn, kind)] == [(sources.DEFAULT_URL, 1)]


def test_one_source_serves_both_kinds_and_shows_in_both_tabs(client):
    _, slug = _car(client)
    client.post("/sources", data={"kind": "plugin", "url": "https://example.com/pkgs", "name": "Examples"})
    plugins = client.get(f"/v/{slug}/plugins/sources").text
    integrations = client.get(f"/v/{slug}/integrations/sources").text
    assert "Examples" in plugins and "Examples" in integrations  # the same source in both tabs
    assert 'class="seg-tabs' in plugins and 'class="seg-tabs' in integrations
    client.post("/sources", data={"kind": "integration", "url": "https://example.com/pkgs"})  # twice: refused
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 2
        sid = conn.execute("SELECT id FROM sources WHERE url = 'https://example.com/pkgs'").fetchone()[0]
    client.post(f"/sources/{sid}/delete", data={"kind": "integration"})  # deleting removes it everywhere
    with db.tx() as conn:
        assert sources.get(conn, sid) is None


def test_source_address_is_checked(client):
    for bad in ("http://example.com/x", "ftp://example.com", "https://user:pw@example.com/x", "https://example.com/x?a=1", "not a url", ""):
        client.post("/sources", data={"kind": "plugin", "url": bad})
    client.post("/sources", data={"kind": "plugin", "url": "https://example.com/a"})
    client.post("/sources", data={"kind": "plugin", "url": "https://example.com/a/"})  # same address again
    with db.tx() as conn:
        urls = [r["url"] for r in conn.execute("SELECT url FROM sources ORDER BY id")]
    assert urls == [sources.DEFAULT_URL, "https://example.com/a"]


def test_update_reads_both_indexes_and_lists_the_packages(client, fake_source):
    sid = _default_id()
    client.post(f"/sources/{sid}/refresh", data={"kind": "plugin"})
    with db.tx() as conn:
        row = conn.execute("SELECT checked_at, error FROM sources WHERE id = ?", (sid,)).fetchone()
        n = conn.execute("SELECT kind, pkg_id, version FROM source_packages").fetchall()
    assert row["error"] is None and row["checked_at"]
    assert [tuple(r) for r in n] == [("plugin", "demo-one", "1.9")]
    assert any("api.github.com/repos/Matze89x/ha-car-assistant-sources/contents/plugins/index.json" in u for u, _ in fake_source["seen"])
    _, slug = _car(client)
    add_page = client.get(f"/v/{slug}/plugins/add").text
    assert "Demo One" in add_page and "/packages/" in add_page
    assert "Demo One" not in client.get(f"/v/{slug}/integrations/add").text  # integrations and plugins stay apart


def test_wrong_layout_is_reported(client, fake_source):
    sid = _default_id()
    fake_source["files"].clear()
    client.post(f"/sources/{sid}/refresh", data={"kind": "plugin"})
    with db.tx() as conn:
        assert conn.execute("SELECT error FROM sources WHERE id = ?", (sid,)).fetchone()[0] == "err.src_empty"
    fake_source["files"]["plugins/index.json"] = "not json"
    client.post(f"/sources/{sid}/refresh", data={"kind": "plugin"})
    with db.tx() as conn:
        assert conn.execute("SELECT error FROM sources WHERE id = ?", (sid,)).fetchone()[0] == "err.src_format"


def test_install_manage_update_deactivate_uninstall(client, fake_source):
    sid = _default_id()
    vid, slug = _car(client)
    client.post(f"/sources/{sid}/refresh", data={"kind": "plugin"})
    detail = client.get(f"/v/{slug}/packages/{sid}/plugin/demo-one")
    assert detail.status_code == 200 and "Demo One" in detail.text
    client.post(f"/v/{vid}/packages/{sid}/plugin/demo-one/install")
    with db.tx() as conn:
        item = addons.list_for(conn, vid)[0]
    assert item["addon_id"] == "demo-one" and item["kind"] == "plugin" and item["source_id"] == sid and not item["has_update"]
    assert "Demo One" in client.get(f"/v/{slug}/plugins").text  # installed ones live under Manage
    add_again = client.get(f"/v/{slug}/plugins/add").text  # still listed on Add, but marked and not linked
    assert "Demo One" in add_again and "/packages/" not in add_again

    # a source with an installed package cannot be deleted
    client.post(f"/sources/{sid}/delete", data={"kind": "plugin"})
    with db.tx() as conn:
        assert sources.get(conn, sid) is not None

    # the source offers 2.0: an update shows up and is applied, settings and token stay
    fake_source["files"]["plugins/index.json"] = json.dumps({"packages": [{"id": "demo-one", "name": "Demo One", "version": "2.0"}]})
    fake_source["files"]["plugins/demo-one/plugin.json"] = json.dumps({"id": "demo-one", "name": "Demo One", "version": "2.0"})
    client.post(f"/sources/{sid}/refresh", data={"kind": "plugin"})
    with db.tx() as conn:
        item = addons.list_for(conn, vid)[0]
    assert item["has_update"] and item["latest"] == "2.0"
    client.post(f"/v/{vid}/integrations/{item['id']}/update")
    with db.tx() as conn:
        item = addons.list_for(conn, vid)[0]
    assert item["m"]["version"] == "2.0" and not item["has_update"]

    # switched off: its connection token is refused until it is switched on again
    client.post(f"/v/{vid}/integrations/{item['id']}/setup", data={})
    with db.tx() as conn:
        item = addons.list_for(conn, vid)[0]
        token = connectors.create_token(conn, "x", vid)
        conn.execute(
            "UPDATE vehicle_addons SET token_id = (SELECT id FROM api_tokens ORDER BY id DESC LIMIT 1) WHERE id = ?", (item["id"],)
        )
        assert connectors.verify(conn, token) is not None
    client.post(f"/v/{vid}/integrations/{item['id']}/active", data={})
    with db.tx() as conn:
        assert connectors.verify(conn, token) is None
    client.post(f"/v/{vid}/integrations/{item['id']}/active", data={"active": "1"})
    with db.tx() as conn:
        assert connectors.verify(conn, token) is not None

    # uninstalled: the source can go, and the standard one comes back on request
    client.post(f"/v/{vid}/integrations/{item['id']}/delete")
    client.post(f"/sources/{sid}/delete", data={"kind": "plugin"})
    with db.tx() as conn:
        assert sources.listing(conn, "plugin") == [] and sources.get(conn, sid) is None  # gone from both lists
    client.post("/sources/restore-default", data={"kind": "plugin"})
    with db.tx() as conn:
        assert [r["url"] for r in sources.listing(conn, "plugin")] == [sources.DEFAULT_URL]


def test_access_key_is_sent_but_never_shown(client, fake_source):
    sid = _default_id()
    client.post(f"/sources/{sid}/token", data={"kind": "plugin", "token": "github_pat_SECRET123"})
    client.post(f"/sources/{sid}/refresh", data={"kind": "plugin"})
    assert any(h.get("Authorization") == "Bearer github_pat_SECRET123" for _, h in fake_source["seen"])
    assert "SECRET123" not in client.get("/sources").text
    client.post(f"/sources/{sid}/token", data={"kind": "plugin", "token": ""})  # blank keeps the key
    with db.tx() as conn:
        from carassistant import vault

        assert vault.decrypt(sources.get(conn, sid)["token"]) == "github_pat_SECRET123"  # stored sealed, readable by the app
    client.post(f"/sources/{sid}/token", data={"kind": "plugin", "remove": "1"})
    with db.tx() as conn:
        assert sources.get(conn, sid)["token"] is None


def test_manifest_must_match_its_folder(client, fake_source):
    sid = _default_id()
    client.post(f"/sources/{sid}/refresh", data={"kind": "plugin"})
    fake_source["files"]["plugins/demo-one/plugin.json"] = json.dumps({"id": "other", "name": "X"})
    vid, _ = _car(client)
    client.post(f"/v/{vid}/packages/{sid}/plugin/demo-one/install")
    with db.tx() as conn:
        assert addons.list_for(conn, vid) == []


def test_versions_are_compared_as_numbers():
    assert (
        sources.is_newer("1.10", "1.9")
        and not sources.is_newer("1.9", "1.10")
        and not sources.is_newer("", "1")
        and sources.is_newer("2", "")
    )


def test_private_network_addresses_are_refused():  # no database needed
    assert not sources._public_host("127.0.0.1") and not sources._public_host("localhost")


def test_card_without_a_source_shows_no_update_note(client, fake_source):
    """`a.update` would be the dict method in the template: the flag has its own name."""
    vid, slug = _car(client)
    with db.tx() as conn:
        addons.add(
            conn, vid, addons.parse_package(json.dumps({"id": "manual-one", "kind": "plugin", "name": "Manual", "version": "1"}).encode())
        )
    page = client.get(f"/v/{slug}/plugins").text
    assert "Manual" in page and "upd-note" not in page


def test_back_returns_to_the_page_the_user_came_from(client):
    _, slug = _car(client)
    add = client.get(f"/v/{slug}/plugins/add").text
    assert (
        f'/v/{slug}/plugins/sources"' in add and "?back=" not in add
    )  # no address inside the link (it once gave a 400 behind Home Assistant)
    page = client.get(f"/v/{slug}/plugins/sources").text
    assert f'class="back-btn deep" href="/v/{slug}/plugins/add"' in page  # Back is worked out from the page itself
    page = client.get(f"/v/{slug}/plugins/sources?back=/v/{slug}/plugins/add").text
    assert f'class="back-btn deep" href="/v/{slug}/plugins/add"' in page
    for bad in ("//evil.example", "https://evil.example", "/v/x/../../y", "/a b"):
        assert f'href="{bad}"' not in client.get(f"/v/{slug}/plugins/sources", params={"back": bad}).text


def test_factory_reset_brings_the_standard_source_back_and_it_can_be_removed_again(client):
    sid = _default_id()
    client.post(f"/sources/{sid}/delete", data={"kind": "plugin"})
    client.post(f"/sources/{sid}/delete", data={"kind": "integration"})
    with db.tx() as conn:
        assert sources.listing(conn, "plugin") == []
    res = client.post("/settings/reset", data={"confirm": "RESET"}, follow_redirects=False)
    assert res.status_code == 303
    with db.tx() as conn:  # like a fresh install: in both lists, marked as the standard
        for kind in sources.KINDS:
            assert [(r["url"], r["is_default"]) for r in sources.listing(conn, kind)] == [(sources.DEFAULT_URL, 1)]
    new_id = _default_id()
    client.post(f"/sources/{new_id}/delete", data={"kind": "plugin"})  # nothing is installed from it: it can go
    client.post(f"/sources/{new_id}/delete", data={"kind": "integration"})
    with db.tx() as conn:
        assert sources.get(conn, new_id) is None


def test_auto_name_and_lenient_index(client, fake_source):
    assert sources.auto_name("https://github.com/Owner/Repo-X") == "Owner/Repo-X"
    assert sources.auto_name("https://example.org/a/b/cars") == "example.org/cars"
    fake_source["files"]["plugins/index.json"] = json.dumps([{"id": "demo-one", "name": "Demo One"}, {"id": "Bad Id"}, {"name": "no id"}])
    fake_source["files"]["index.json"] = json.dumps({"name": "Fine Source"})
    with db.tx() as conn:
        sid = sources.add(conn, "", "https://example.org/x/cars", "", "plugin")
    with db.tx() as conn:
        assert sources.refresh(conn, sid) is None
    with db.tx() as conn:
        row = sources.listing(conn, "plugin")
    mine = next(r for r in row if r["id"] == sid)
    assert mine["name"] == "Fine Source" and mine["n_packages"] == 1
    assert {n["why"] for n in mine["notes"]} == {"id", "shape"}


def test_a_package_installed_from_a_file_is_taken_over_by_its_source(client, fake_source):
    sid = _default_id()
    vid, slug = _car(client)
    client.post(
        f"/v/{vid}/integrations/upload",
        files={"package": ("plugin.json", json.dumps({"id": "demo-one", "kind": "plugin", "name": "Old"}), "application/json")},
    )
    client.post(f"/sources/{sid}/refresh", data={"kind": "plugin"})
    add_page = client.get(f"/v/{slug}/plugins/add").text
    assert (
        "/packages/" not in add_page and "Installed · no source" in add_page
    )  # it IS installed, only not from this source: no second install
    client.post(f"/v/{vid}/packages/{sid}/plugin/demo-one/install")
    with db.tx() as conn:
        item = addons.list_for(conn, vid)[0]
    assert item["source_id"] == sid and item["m"]["name"] == "Demo One"  # now it has its source and updates come from there


def _file_package(client, vid, pkg_id="demo-one", version="1.0"):
    client.post(
        f"/v/{vid}/integrations/upload",
        files={
            "package": ("plugin.json", json.dumps({"id": pkg_id, "kind": "plugin", "name": "Mine", "version": version}), "application/json")
        },
    )


def test_a_package_without_a_source_gets_the_update_of_a_source_that_offers_a_newer_one(client, fake_source):
    sid = _default_id()
    vid, slug = _car(client)
    _file_package(client, vid, version="1.0")  # installed from a file: no source
    client.post(f"/sources/{sid}/refresh", data={"kind": "plugin"})  # the source offers 1.9
    with db.tx() as conn:
        item = addons.list_for(conn, vid)[0]
    assert item["source_id"] is None and item["has_update"] and item["latest"] == "1.9" and item["offer_source"]
    page = client.get(f"/v/{slug}/plugins").text
    assert "no source" in page and "Update available: v1.9 from" in page
    client.post(f"/v/{vid}/integrations/{item['id']}/update")
    with db.tx() as conn:
        item = addons.list_for(conn, vid)[0]
    assert (
        item["source_id"] == sid and item["m"]["version"] == "1.9" and not item["has_update"]
    )  # taken over: its next updates come from there


def test_a_package_without_a_source_that_is_newer_than_the_source_is_left_alone(client, fake_source):
    sid = _default_id()
    vid, slug = _car(client)
    _file_package(client, vid, version="5")  # the source only has 1.9
    client.post(f"/sources/{sid}/refresh", data={"kind": "plugin"})
    with db.tx() as conn:
        item = addons.list_for(conn, vid)[0]
    assert item["source_id"] is None and not item["has_update"]
    client.post(f"/v/{vid}/integrations/{item['id']}/update")  # nothing newer on offer: refused, nothing changes
    with db.tx() as conn:
        item = addons.list_for(conn, vid)[0]
    assert item["source_id"] is None and item["m"]["version"] == "5"
    add_page = client.get(f"/v/{slug}/plugins/add").text
    assert "Installed · no source" in add_page and "/packages/" not in add_page  # not shown as "not installed"


def test_the_two_update_buttons_and_the_icon_of_the_index(client, fake_source):
    import json as _json

    vid, slug = _car(client)
    sid = _default_id()
    fake_source["files"]["plugins/index.json"] = _json.dumps(
        {
            "packages": [
                {"id": "demo-one", "name": "Demo One", "version": "2", "icon": "wrench"},
                {"id": "demo-two", "name": "Two", "icon": "no-such-icon"},
            ]
        }
    )
    r = client.post("/sources/refresh", data={"kind": "plugin", "vid": str(vid), "back": "add"})
    assert r.headers["location"].endswith("/plugins/add?m=src_refreshed")  # "Update list" stays on Add
    page = client.get(f"/v/{slug}/plugins/add").text
    assert "Demo One" in page and "Update list" in page and "pk-tile" in page
    with db.tx() as conn:
        icons_ = {r["pkg_id"]: r["icon"] for r in conn.execute("SELECT pkg_id, icon FROM source_packages WHERE kind = 'plugin'")}
    assert icons_["demo-one"] == "wrench" and icons_["demo-two"] == ""  # only a name of the icon set counts
    client.post(f"/v/{vid}/packages/{sid}/plugin/demo-one/install")
    fake_source["files"]["plugins/index.json"] = _json.dumps({"packages": [{"id": "demo-one", "name": "Demo One", "version": "3"}]})
    r = client.post("/sources/refresh", data={"kind": "plugin", "vid": str(vid), "back": "manage"})
    assert r.headers["location"].endswith("/plugins?m=src_updates_found")  # "Check for updates" says what it found
    manage = client.get(f"/v/{slug}/plugins").text
    assert ("Check for updates" in manage and "Update to v3" in manage) or "v3" in manage
    fake_source["files"]["plugins/demo-one/plugin.json"] = _json.dumps(
        {"id": "demo-one", "name": "Demo One", "version": "3", "settings": []}
    )
    client.post(f"/v/{vid}/integrations/{_pk(vid)}/update")
    r = client.post("/sources/refresh", data={"kind": "plugin", "vid": str(vid), "back": "manage"})
    assert r.headers["location"].endswith("m=src_up_to_date")
    assert "Update list" not in client.get(f"/v/{slug}/plugins/sources").text  # the Sources tab has no update button any more


def _pk(vid):
    with db.tx() as conn:
        return conn.execute("SELECT id FROM vehicle_addons WHERE vehicle_id = ?", (vid,)).fetchone()["id"]


def test_the_daily_check_is_opt_in(client):
    client.post("/settings/sources-auto", data={"auto": "1"})
    with db.tx() as conn:
        assert db.get_setting(conn, "sources.auto") == "1"
    assert "Check the sources once a day" in client.get("/settings/system").text
    client.post("/settings/sources-auto", data={})
    with db.tx() as conn:
        assert db.get_setting(conn, "sources.auto") is None


def test_the_access_key_of_a_source_is_stored_encrypted_and_still_used(client, fake_source):
    from carassistant import vault

    sid = _default_id()
    client.post(f"/sources/{sid}/token", data={"kind": "plugin", "token": "github_pat_SECRET123"})
    with db.tx() as conn:
        stored = conn.execute("SELECT token FROM sources WHERE id = ?", (sid,)).fetchone()[0]
        assert stored.startswith(vault.PREFIX) and "SECRET123" not in stored  # what lies in the database
        sources.refresh(conn, sid)
    assert any(
        h.get("Authorization") == "Bearer github_pat_SECRET123" for _, h in fake_source["seen"]
    )  # the source still gets the real key


def test_the_demo_plugin_is_never_offered_to_pick(conn, vehicle):
    sid = conn.execute("SELECT id FROM sources WHERE url = ?", (sources.DEFAULT_URL,)).fetchone()["id"]
    conn.executemany(
        "INSERT INTO source_packages(source_id, kind, pkg_id, name, description, version, icon) VALUES(?,?,?,?,?,?,?)",
        [(sid, "plugin", "demo-connector", "Demo connector", "", "2", ""), (sid, "plugin", "example-plugin", "Example", "", "2", "")],
    )
    assert [r["pkg_id"] for r in sources.available(conn, "plugin", vehicle)] == [
        "example-plugin"
    ]  # the demo cars still fetch the demo plugin
    assert sources.package(conn, sid, "plugin", "demo-connector") is not None


def test_github_rate_limit_is_not_reported_as_a_wrong_key(monkeypatch, client):
    import io
    import urllib.error

    import pytest

    from carassistant import sources

    class Opener:
        def open(self, request, timeout=None):
            raise urllib.error.HTTPError(request.full_url, 403, "rate limited", {"X-RateLimit-Remaining": "0"}, io.BytesIO(b""))

    monkeypatch.undo()  # the fixture of this file replaces _http by a fake: the real one is needed here
    monkeypatch.setattr(sources.urllib.request, "build_opener", lambda *a: Opener())
    with pytest.raises(sources.SourceError) as err:
        sources._http("https://api.github.com/repos/x/y/contents/index.json", {}, False)
    assert err.value.args[0] == "err.src_rate"
