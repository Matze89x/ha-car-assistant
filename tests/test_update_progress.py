"""The bar of the update window (carassistant/updprogress.py, docs/sources.md, "The update window"): how far an update has come is what the update says about itself -
the stage it is in and the bytes of its package that have come - and never a guess on a timer. The share of every stage is fixed, the percentage never goes back
and reaches 100 only when the update is done; the page may ask for it only if it may update.

Nothing here talks to the network: a source answers from a dict, a big file from a made-up answer."""

import io
import json
import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from tests.test_update_window import LOG, REPO, _car, _offer, _pk

from carassistant import accounts, addons, auth_web, config, db, i18n, pluginsvc, sources, updprogress, web
from carassistant import addons_web as addons_web_module


@pytest.fixture(autouse=True)
def fresh():
    updprogress._runs.clear()
    yield
    updprogress._runs.clear()


@pytest.fixture()
def fake_source(monkeypatch):
    """A source answers from this dict (path -> text); a path that is not in it is 'not found'."""
    state = {"files": dict(REPO)}

    def fake_http(url, headers, check_host, limit=0):
        for path, text in state["files"].items():
            if url.endswith("/" + path):
                return text.encode()
        raise sources.SourceError("err.src_missing")

    monkeypatch.setattr(sources, "_http", fake_http)
    return state


@pytest.fixture()
def offered(client, fake_source):
    """A car with 'Demo One' 1.9 installed from the source, which now offers 2.0 (``vid``, ``slug``, ``sid``, ``pk``)."""
    car = _car(client)
    client.post(f"/sources/{car.sid}/refresh", data={"kind": "plugin"})
    client.post(f"/v/{car.vid}/packages/{car.sid}/plugin/demo-one/install")
    _offer(client, fake_source, car.sid, "2.0", LOG)
    car.pk = _pk(car.vid)
    return car


def numbers(value, digits=0):
    return f"{value:.{digits}f}"


# ------------------------------------------------------------------ what is counted


def test_a_plain_description_is_read_and_saved_a_package_is_also_loaded_and_checked():
    assert updprogress.plan_for(False, False) == ("read", "save")
    assert updprogress.plan_for(True, False) == ("read", "download", "check", "save")
    assert updprogress.plan_for(True, True) == ("read", "download", "check", "save", "restart")


def test_every_stage_has_its_share_and_the_percentage_never_goes_back():
    plan = updprogress.plan_for(True, False)  # 10 + 55 + 15 + 10 = 90
    run = updprogress.begin(7, plan)
    assert updprogress.read(7)["pct"] == 0
    run.stage("download", 0.5)
    assert round(updprogress.read(7)["pct"], 1) == 41.7  # (10 + 27.5) / 90
    run.stage("download", 0.2)  # a lower number does not take the bar back
    assert round(updprogress.read(7)["pct"], 1) == 41.7
    run.stage("check")
    assert round(updprogress.read(7)["pct"], 1) == 72.2  # (10 + 55) / 90
    run.stage("restart")  # a stage this update does not have: nothing happens
    assert updprogress.read(7)["stage"] == "check"
    run.stage("save", 1.0)
    assert updprogress.read(7)["pct"] == 99  # all that is left is "done"
    run.finish(True)
    got = updprogress.read(7)
    assert got["pct"] == 100 and got["done"] and got["ok"] is True
    run.stage("read")  # after the end nothing moves
    assert updprogress.read(7)["pct"] == 100


def test_an_update_that_fails_stops_where_it_was_and_says_so():
    run = updprogress.begin(3, updprogress.plan_for(True, False))
    run.stage("download", 0.5, 5_000_000, 10_000_000)
    run.finish(False)
    got = updprogress.read(3)
    assert got["done"] and got["ok"] is False and round(got["pct"]) == 42 and got["got"] is None


def test_a_new_version_with_other_stages_does_not_take_the_bar_back():
    run = updprogress.begin(5, ("read", "save"))
    run.stage("save")
    assert updprogress.read(5)["pct"] == 50  # the installed version was a plain description: read, then save
    run.replan(updprogress.plan_for(True, True))  # the new one brings files and a service
    assert updprogress.read(5)["pct"] == 50  # what was shown stays
    run.stage("download", 0.1)  # counted again, this is less: the bar does not go back
    assert updprogress.read(5)["pct"] == 50
    run.stage("restart", 1.0)
    assert updprogress.read(5)["pct"] == 99


def test_what_is_long_ago_is_forgotten_and_there_are_never_many(monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(updprogress, "_now", lambda: clock["now"])
    updprogress.begin(1, ("read", "save")).finish(True)
    clock["now"] += updprogress.KEEP_SECONDS + 1
    updprogress.begin(2, ("read", "save"))  # (starting one looks after the old ones)
    assert updprogress.read(1) is None and updprogress.read(2) is not None
    for pk in range(100, 100 + updprogress.MAX_RUNS + 20):
        clock["now"] += 1
        updprogress.begin(pk, ("read", "save"))
    assert len(updprogress._runs) <= updprogress.MAX_RUNS


def test_only_the_update_that_is_tracked_is_told():
    run = updprogress.begin(1, ("read", "download", "save"))
    updprogress.report("download", 0.5, 1, 2)  # nobody asked for it in this thread: nothing happens
    assert updprogress.read(1)["stage"] == "read"
    with updprogress.tracking(run):
        updprogress.report("download", 0.5, 1, 2)
    assert updprogress.read(1)["stage"] == "download"
    updprogress.report("save")  # the tracking has ended
    assert updprogress.read(1)["stage"] == "download"


def test_a_newer_update_of_the_same_install_takes_the_place_of_an_older_one():
    old = updprogress.begin(1, ("read", "download", "save"), "first")
    new = updprogress.begin(1, ("read", "download", "save"), "second")  # somebody else presses the button
    old.stage("download", 0.9)  # the old one goes on with its work, but is not heard any more
    old.finish(True)
    assert updprogress.read(1, "first") is None
    got = updprogress.read(1, "second")
    assert got["stage"] == "read" and got["done"] is False
    new.stage("save")
    new.finish(True)
    assert updprogress.read(1, "second")["done"] is True


def test_a_window_hears_only_about_its_own_update():
    updprogress.begin(1, ("read", "save"), "abc-1").finish(True)
    assert updprogress.read(1, "abc-1")["done"] is True
    assert updprogress.read(1, "other") is None  # the finished update of a minute ago is not the one this window started
    assert updprogress.read(1, "") is None
    assert updprogress.read(1)["done"] is True  # asked without a mark, the last one answers (what a script may want)
    assert [updprogress.token_of(x) for x in ("w1k2-abc_D", "", None, "a b", "x" * 41, "<script>", "ok")] == [
        "w1k2-abc_D",
        "",
        "",
        "",
        "",
        "",
        "ok",
    ]


def test_the_answer_for_the_page_is_in_the_language_of_the_page():
    run = updprogress.begin(1, updprogress.plan_for(True, False))
    run.stage("download", 0.5, 5_250_000, 10_500_000)
    en = updprogress.describe(updprogress.read(1), i18n.translator("en"), numbers)
    assert en == {"pct": 42, "label": "Loading the package", "detail": "5.2 of 10.5 MB", "done": False, "ok": None}
    de = updprogress.describe(updprogress.read(1), i18n.translator("de"), numbers)
    assert de["label"] == "Paket wird geladen" and de["detail"] == "5.2 von 10.5 MB"
    run.stage("download", 0.5, 5_250_000, None)  # the size is not known: only what has come
    assert updprogress.describe(updprogress.read(1), i18n.translator("en"), numbers)["detail"] == "5.2 MB"
    run.finish(True)
    assert updprogress.describe(updprogress.read(1), i18n.translator("en"), numbers) == {
        "pct": 100,
        "label": "Done",
        "detail": "",
        "done": True,
        "ok": True,
    }
    assert updprogress.describe(None, i18n.translator("en"), numbers) == {"state": "none"}


# ------------------------------------------------------------------ the bytes that come


class Answer:
    """What a source answers: the body, read in the pieces the reader asks for, and its headers."""

    def __init__(self, data: bytes, length: bool = True):
        self.body = io.BytesIO(data)
        self.headers = {"Content-Length": str(len(data))} if length else {}

    def read(self, n=-1):
        return self.body.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def _answer(monkeypatch, data: bytes, length: bool = True):
    monkeypatch.setattr(
        sources.urllib.request, "build_opener", lambda *_a: SimpleNamespace(open=lambda _request, timeout=None: Answer(data, length))
    )


def test_a_big_file_says_how_many_bytes_have_come_and_is_the_same_file(monkeypatch):
    data = bytes(range(256)) * 2000  # half a megabyte: eight pieces
    _answer(monkeypatch, data)
    run = updprogress.begin(1, updprogress.plan_for(True, False))
    seen = []
    real = run.stage
    monkeypatch.setattr(
        run, "stage", lambda name, fraction=0.0, got=None, total=None: (seen.append((name, got, total)), real(name, fraction, got, total))
    )
    with updprogress.tracking(run):
        body = sources._http("https://example.com/package.zip", {}, False, limit=sources.MAX_PACKAGE_ZIP)
    assert bytes(body) == data
    assert len(seen) == 8 and seen[0] == ("download", 65536, len(data)) and seen[-1] == ("download", len(data), len(data))
    assert [s[1] for s in seen] == sorted(s[1] for s in seen)  # more and more
    assert updprogress.read(1)["stage"] == "download"


def test_a_small_file_is_read_as_before_and_says_nothing(monkeypatch):
    _answer(monkeypatch, b"x" * 1000)
    run = updprogress.begin(1, updprogress.plan_for(True, False))
    with updprogress.tracking(run):
        assert bytes(sources._http("https://example.com/plugin.json", {}, False)) == b"x" * 1000
    assert updprogress.read(1)["stage"] == "read" and updprogress.read(1)["got"] is None


def test_a_file_without_a_size_is_counted_without_a_total_and_one_that_is_too_big_is_refused(monkeypatch):
    data = b"y" * 200_000
    _answer(monkeypatch, data, length=False)
    run = updprogress.begin(1, updprogress.plan_for(True, False))
    with updprogress.tracking(run):
        sources._http("https://example.com/package.zip", {}, False, limit=sources.MAX_FILE + 1000)
    got = updprogress.read(1)
    assert (
        got["total"] is None and got["got"] == len(data) and got["pct"] == pytest.approx(11.11, abs=0.01)
    )  # the stage is not counted by the byte
    limit = sources.MAX_FILE + 10
    _answer(monkeypatch, b"z" * (limit + 5))
    with pytest.raises(sources.SourceError) as refused:
        sources._http("https://example.com/package.zip", {}, False, limit=limit)
    assert str(refused.value) == "err.src_format"


# ------------------------------------------------------------------ the update and the page


def test_the_window_has_the_bar_hidden_until_the_update_runs(client, offered):
    page = client.get(f"/v/{offered.slug}/plugins").text
    dialog = re.search(rf'<dialog id="upd-{offered.pk}".*?</dialog>', page, re.S).group(0)
    assert f'<div class="upd-prog" hidden data-progress="/v/{offered.slug}/integrations/{offered.pk}/update-progress">' in dialog
    assert 'role="progressbar"' in dialog and 'aria-valuenow="0"' in dialog and "Starting the update" in dialog


def test_an_update_from_the_window_answers_where_to_go_and_the_bar_ends_at_done(client, offered):
    url = f"/v/{offered.vid}/integrations/{offered.pk}"
    got = client.post(f"{url}/update", headers={"X-Requested-With": "fetch", "X-Update-Run": "w1-abc"}, follow_redirects=False)
    assert got.status_code == 200 and got.headers["cache-control"] == "no-store"
    body = got.json()
    assert body["ok"] is True and body["to"].endswith("m=addon.updated") and f"/{offered.slug}/" in body["to"]
    with db.tx() as conn:
        assert addons.get(conn, offered.vid, offered.pk)["m"]["version"] == "2.0"
    done = {"pct": 100, "label": "Done", "detail": "", "done": True, "ok": True}
    assert client.get(f"{url}/update-progress?run=w1-abc").json() == done  # the window that pressed the button hears it
    assert client.get(f"{url}/update-progress?run=another").json() == {"state": "none"}  # another window does not
    assert client.get(f"{url}/update-progress").json() == done


def test_a_form_without_the_window_still_redirects_as_before(client, offered):
    got = client.post(f"/v/{offered.vid}/integrations/{offered.pk}/update", follow_redirects=False)
    assert got.status_code == 303 and got.headers["location"].endswith("m=addon.updated")


def test_an_update_that_does_not_work_says_so_in_the_bar_too(client, fake_source, offered):
    del fake_source["files"]["plugins/demo-one/plugin.json"]
    with db.tx() as conn:
        conn.execute("DELETE FROM source_cache")
    got = client.post(f"/v/{offered.vid}/integrations/{offered.pk}/update", headers={"X-Requested-With": "fetch"}, follow_redirects=False)
    assert got.status_code == 200 and got.json()["ok"] is False and "m=err." in got.json()["to"]
    progress = client.get(f"/v/{offered.vid}/integrations/{offered.pk}/update-progress").json()
    assert (
        progress["done"] is True and progress["ok"] is False and progress["label"] == "The update did not finish." and progress["pct"] < 100
    )


def test_a_package_with_files_goes_through_every_stage_and_the_page_hears_it(client, fake_source, monkeypatch):
    car = _car(client)
    files = [{"name": "a.jar", "path": "assets/a.jar", "sha256": "0" * 64, "size": 3}]
    with db.tx() as conn:
        pk = addons.add(
            conn,
            car.vid,
            addons.parse_package(
                json.dumps({"id": "files-demo", "kind": "plugin", "name": "Files Demo", "version": "1", "files": files}).encode()
            ),
            car.sid,
            "0" * 64,
        )
        conn.execute(
            "INSERT INTO source_packages(source_id, kind, pkg_id, name, description, version, icon) VALUES(?,?,?,?,?,?,?)",
            (car.sid, "plugin", "files-demo", "Files Demo", "", "2", ""),
        )
    fake_source["files"]["plugins/files-demo/plugin.json"] = json.dumps(
        {"id": "files-demo", "name": "Files Demo", "version": "2", "files": files}
    )
    t = i18n.translator("en")
    heard = []

    def package(_manifest, _source_id, _kind, _pkg_id):
        """The loading of the package, as sources._http and pkginstall say it."""
        heard.append(updprogress.describe(updprogress.read(pk), t, numbers))  # the manifest has been read, the files are next
        updprogress.report("download", 0.5, 5_000_000, 10_000_000)
        heard.append(updprogress.describe(updprogress.read(pk), t, numbers))
        updprogress.report("download", 1.0, 10_000_000, 10_000_000)
        updprogress.report("check")
        heard.append(updprogress.describe(updprogress.read(pk), t, numbers))
        return "1" * 64

    monkeypatch.setattr(addons_web_module, "_fetch_service_package", package)
    monkeypatch.setattr(pluginsvc, "restart", lambda _pk: heard.append("restart"))
    monkeypatch.setattr(pluginsvc, "kick", lambda: None)
    with db.tx() as conn:
        conn.execute("DELETE FROM source_cache")
    got = client.post(f"/v/{car.vid}/integrations/{pk}/update", headers={"X-Requested-With": "fetch"}, follow_redirects=False)
    assert got.json()["ok"] is True
    assert [(h["label"], h["pct"], h["detail"]) for h in heard[:3]] == [
        ("Loading the package", 11, ""),  # (the manifest was read: 10 of 90)
        ("Loading the package", 42, "5.0 of 10.0 MB"),
        ("Checking and unpacking the files", 72, ""),
    ]
    assert heard[3:] == [
        "restart"
    ]  # (what the app has always done after loading a package; a package without a service has no such stage in the bar)
    assert client.get(f"/v/{car.vid}/integrations/{pk}/update-progress").json()["pct"] == 100


def test_the_page_asks_what_is_known_and_a_package_that_does_not_exist_is_not_found(client, offered):
    url = f"/v/{offered.vid}/integrations/{offered.pk}/update-progress"
    assert client.get(url).json() == {"state": "none"}  # no update has run
    updprogress.begin(offered.pk, updprogress.plan_for(True, False)).stage("download", 0.5, 5_000_000, 10_000_000)
    assert client.get(url).json() == {"pct": 42, "label": "Loading the package", "detail": "5.0 of 10.0 MB", "done": False, "ok": None}
    assert client.get(f"/v/{offered.vid}/integrations/9999/update-progress").status_code == 404


def test_the_bar_speaks_german_with_the_decimal_comma(client, offered, monkeypatch):
    monkeypatch.setattr(config, "language", lambda: "de")
    updprogress.begin(offered.pk, updprogress.plan_for(True, False)).stage("download", 0.5, 5_250_000, 10_500_000)
    got = client.get(f"/v/{offered.vid}/integrations/{offered.pk}/update-progress").json()
    assert got["label"] == "Paket wird geladen" and got["detail"] == "5,2 von 10,5 MB"
    page = client.get(f"/v/{offered.slug}/plugins").text
    assert "Das Update startet" in page and "Fortschritt des Updates" in page


def test_only_people_who_may_update_ask_how_far_it_is(client, offered, monkeypatch):
    with db.tx() as conn:
        admin = accounts.create_session(conn, accounts.create_user(conn, "owner", "a-long-pass-123", "Owner", True))
        guest = accounts.create_session(conn, accounts.create_user(conn, "guest", "a-long-pass-123", "Guest", False))
    monkeypatch.delenv("CARASSISTANT_DEV", raising=False)  # somebody from outside is not the Home Assistant gateway
    outside = TestClient(web.app, base_url="https://car.example.com", follow_redirects=False, headers={"Origin": "https://car.example.com"})
    url = f"/v/{offered.vid}/integrations/{offered.pk}/update-progress"
    assert outside.get(url, cookies={auth_web.COOKIE: guest}).status_code == 403
    assert outside.get(url, cookies={auth_web.COOKIE: admin}).status_code == 200
    assert outside.get(url).status_code in (303, 401, 403)


def test_the_script_of_the_window_keeps_the_page_and_only_asks_for_the_bar():
    from pathlib import Path

    js = (Path(web.__file__).parent / "static" / "app.js").read_text(encoding="utf-8")
    assert 'form.closest("dialog.upd-dlg")' in js and '"X-Requested-With": "fetch"' in js and "data-progress" in js
    assert "window.location.reload()" in js  # whatever goes wrong: the page as it is
