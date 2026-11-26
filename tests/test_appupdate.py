import io
import json

from carassistant import __version__, appupdate, db


def test_nothing_is_fetched_by_default_and_the_indicator_is_calm(client):
    appupdate.forget()
    with db.tx() as conn:
        assert not appupdate.enabled(conn) and not appupdate.due(conn)
        assert appupdate.status(conn)["newer"] is False
    page = client.get("/about").text
    assert "sb-upd" not in page and 'class="dot "' in page.replace("dot  ", "dot ")


def test_a_newer_version_shows_up_in_the_side_bar_and_in_the_settings(client, monkeypatch):
    class Answer(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        appupdate.urllib.request, "urlopen", lambda *a, **k: Answer(json.dumps({"version": "99.0.0", "stage": "Beta"}).encode())
    )
    client.post("/settings/app-update", data={"check": "1"})
    with db.tx() as conn:
        assert appupdate.enabled(conn) and appupdate.due(conn)  # switched on, never looked: due
    client.post("/settings/app-update", data={"now": "1"})
    with db.tx() as conn:
        s = appupdate.status(conn)
        assert s["latest"] == "99.0.0" and s["newer"] and not appupdate.due(conn)
    appupdate.forget()
    assert "sb-upd" in client.get("/about").text and "v99.0.0" in client.get("/about").text
    assert "99.0.0" in client.get("/settings/system").text


def test_a_failed_look_keeps_the_old_value(client, monkeypatch):
    def boom(*a, **k):
        raise OSError("offline")

    monkeypatch.setattr(appupdate.urllib.request, "urlopen", boom)
    with db.tx() as conn:
        assert appupdate.check(conn) is False
        assert appupdate.status(conn)["latest"] == ""


def test_assets_get_a_fingerprint_and_are_revalidated(client):
    page = client.get("/about").text
    assert "pc-core.css?v=" in page and "?v=" + __version__ + "-" in page
    assert client.get("/static/pc-core.css").headers["cache-control"] == "no-cache"


def _installed_with_newer_offer(conn, vehicle):
    """One plugin of a car whose source offers a newer version than the installed one."""
    conn.execute("INSERT INTO sources(name, url, for_integration, for_plugin) VALUES('Test source', 'https://example.com/s', 1, 1)")
    source = conn.execute("SELECT id FROM sources WHERE url = 'https://example.com/s'").fetchone()[0]
    conn.execute("INSERT INTO source_packages(source_id, kind, pkg_id, name, version) VALUES(?, 'plugin', 'demo', 'Demo', '2')", (source,))
    manifest = json.dumps({"id": "demo", "kind": "plugin", "name": "Demo", "version": "1"})
    conn.execute(
        "INSERT INTO vehicle_addons(vehicle_id, kind, addon_id, manifest, created_at, source_id, pkg_sha) VALUES(?, 'plugin', 'demo', ?, '2026-01-01', ?, 'aaa')",
        (vehicle, manifest, source),
    )
    return conn.execute("SELECT id FROM vehicle_addons WHERE addon_id = 'demo'").fetchone()[0]


def test_the_count_names_the_packages_and_follows_an_update_at_once(client, conn, vehicle):
    appupdate.forget()
    conn.execute("UPDATE vehicles SET slug = 'demo-car' WHERE id = ?", (vehicle,))
    pk = _installed_with_newer_offer(conn, vehicle)
    conn.commit()
    note = appupdate.pending()
    assert note["plugins"] == 1 and "Demo" in note["plugin_list"] and "1 → 2" in note["plugin_list"]
    assert note["plugins_car"] == "demo-car"  # all on one car: the link goes to that car's plugin page
    # the package is updated (a new checksum, a new version): the side bar must not keep saying so for a minute
    conn.execute(
        "UPDATE vehicle_addons SET manifest = ?, pkg_sha = 'bbb' WHERE id = ?",
        (json.dumps({"id": "demo", "kind": "plugin", "name": "Demo", "version": "2"}), pk),
    )
    conn.commit()
    assert appupdate.pending()["plugins"] == 0


def test_a_package_that_is_missing_is_not_counted(client, conn, vehicle):
    appupdate.forget()
    pk = _installed_with_newer_offer(conn, vehicle)
    conn.execute("UPDATE vehicle_addons SET status = 'missing' WHERE id = ?", (pk,))
    conn.commit()
    assert appupdate.pending()["plugins"] == 0
