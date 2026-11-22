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
