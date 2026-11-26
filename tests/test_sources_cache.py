"""Reading a source without running into the limit of GitHub (docs/sources.md): raw files instead of the API, files kept with their ETag, what was known when
the limit is hit, and the standard source that comes with the app."""

import json
import shutil
from pathlib import Path

import pytest

from carassistant import db, sources

HERE = Path(__file__).resolve().parents[1]
REAL_BUNDLE = HERE / "carassistant" / "app" / "carassistant" / "stdsource"
URL = "https://github.com/example/pkgs"


def _body(data: bytes, etag: str | None = None, same: bool = False) -> sources.Body:
    body = sources.Body(b"" if same else data)
    body.etag, body.not_modified = etag, same
    return body


class Net:
    """A fake network: the files of one server by path, with ETags; every request is noted."""

    def __init__(self):
        self.files: dict[str, bytes] = {}
        self.fail: str | None = None
        self.seen: list[tuple[str, dict]] = []

    def __call__(self, url, headers, check_host, limit=0):
        self.seen.append((url, dict(headers)))
        if self.fail:
            raise sources.SourceError(self.fail)
        for path, data in self.files.items():
            if url.endswith("/" + path):
                etag = '"' + str(hash(data) % 10**8) + '"'
                if headers.get("If-None-Match") == etag:
                    return _body(b"", etag, same=True)
                return _body(data, etag)
        raise sources.SourceError("err.src_missing")

    def requests(self, needle: str = "") -> int:
        return sum(1 for url, _ in self.seen if needle in url)


@pytest.fixture()
def net(monkeypatch):
    fake = Net()
    fake.files = {
        "plugins/index.json": json.dumps({"packages": [{"id": "demo-one", "name": "Demo One", "version": "1"}]}).encode(),
        "plugins/demo-one/plugin.json": json.dumps({"id": "demo-one", "kind": "plugin", "name": "Demo One", "version": "1"}).encode(),
    }
    monkeypatch.setattr(sources, "_http", fake)
    return fake


def _source(client, url=URL, token=""):
    with db.tx() as conn:
        return sources.add(conn, "Example", url, token)


def _row(sid):
    with db.tx() as conn:
        return conn.execute("SELECT * FROM sources WHERE id = ?", (sid,)).fetchone()


def test_a_public_github_source_is_read_from_raw_and_one_with_a_key_through_the_api(client):
    public = _row(_source(client))
    url, headers, check = sources._where(public, "plugins/index.json")
    assert (
        url == "https://raw.githubusercontent.com/example/pkgs/HEAD/plugins/index.json"
        and "Authorization" not in headers
        and check is False
    )
    keyed = _row(_source(client, "https://github.com/example/private", "secret-key"))
    url, headers, _ = sources._where(keyed, "plugins/index.json")
    assert (
        url == "https://api.github.com/repos/example/private/contents/plugins/index.json"
        and headers["Authorization"] == "Bearer secret-key"
    )
    other = _row(_source(client, "https://packages.example.org/stuff"))
    url, headers, check = sources._where(other, "plugins/index.json")
    assert url == "https://packages.example.org/stuff/plugins/index.json" and check is True


def test_a_file_is_kept_with_its_etag_and_asked_again_with_it(client, net):
    sid = _source(client)
    with db.tx() as conn:
        assert sources.refresh(conn, sid) is None
    first = net.requests()
    assert first >= 2 and all("If-None-Match" not in h for _, h in net.seen)
    with db.tx() as conn:
        kept = {r["path"]: bool(r["body"]) for r in conn.execute("SELECT path, body FROM source_cache WHERE source_id = ?", (sid,))}
        assert (
            kept["plugins/index.json"] is True and kept["integrations/index.json"] is False
        )  # a file is kept; one the source lacks is kept as "not there"
    net.seen.clear()
    with db.tx() as conn:
        assert sources.refresh(conn, sid) is None  # the person pressed Update list again: the server is asked ...
        assert [r["pkg_id"] for r in conn.execute("SELECT pkg_id FROM source_packages WHERE source_id = ?", (sid,))] == ["demo-one"]
    asked = [h for url, h in net.seen if url.endswith("plugins/index.json")]
    assert len(asked) == 1 and "If-None-Match" in asked[0]  # ... with the ETag it knows: the server answers "not modified"


def test_a_file_read_a_moment_ago_is_not_asked_for_again(client, net):
    sid = _source(client)
    with db.tx() as conn:
        sources.refresh(conn, sid)
        net.seen.clear()
        manifest = sources.fetch_manifest(conn, sid, "plugin", "demo-one")
        again = sources.fetch_manifest(conn, sid, "plugin", "demo-one")
    assert manifest["id"] == again["id"] == "demo-one" and net.requests("plugin.json") == 1  # read once, then kept for ten minutes


def test_the_limit_does_not_empty_the_list(client, net):
    sid = _source(client)
    with db.tx() as conn:
        assert sources.refresh(conn, sid) is None
    before = _row(sid)["online_at"]
    net.fail = "err.src_rate"
    with db.tx() as conn:
        assert sources.refresh(conn, sid) == "err.src_stale"  # said, not hidden ...
        assert [r["pkg_id"] for r in conn.execute("SELECT pkg_id FROM source_packages WHERE source_id = ?", (sid,))] == [
            "demo-one"
        ]  # ... and the list stays
    assert _row(sid)["error"] == "err.src_stale" and _row(sid)["online_at"] == before
    net.fail = "err.src_net"  # no connection: the same
    with db.tx() as conn:
        assert sources.refresh(conn, sid) == "err.src_stale"
    net.fail = None
    with db.tx() as conn:
        assert sources.refresh(conn, sid) is None  # the limit is back: all is well again
    assert _row(sid)["error"] is None and _row(sid)["online_at"]


def test_a_source_without_anything_known_still_says_the_limit(client, net):
    sid = _source(client)
    net.fail = "err.src_rate"
    with db.tx() as conn:
        assert sources.refresh(conn, sid) == "err.src_rate"  # nothing known to fall back on: the plain message
        assert conn.execute("SELECT COUNT(*) FROM source_packages WHERE source_id = ?", (sid,)).fetchone()[0] == 0


def test_a_package_is_read_again_afresh_when_the_kept_index_does_not_fit(client, net):
    import hashlib

    from tests.test_assets import make_zip

    sid = _source(client)
    manifest = {"id": "demo-one", "kind": "plugin", "name": "Demo One", "version": "1", "service": {"entry": "svc.py"}}
    old, _ = make_zip({"plugin.json": json.dumps(manifest), "svc.py": "print(1)\n"})
    new, _ = make_zip({"plugin.json": json.dumps(manifest), "svc.py": "print(2)\n"})
    net.files["plugins/index.json"] = json.dumps(
        {"packages": [{"id": "demo-one", "name": "Demo One", "version": "1", "sha256": hashlib.sha256(old).hexdigest()}]}
    ).encode()
    net.files["plugins/demo-one/package.zip"] = new  # the author published the new zip and index a minute ago
    with db.tx() as conn:
        sources.refresh(conn, sid)
        net.files["plugins/index.json"] = json.dumps(
            {"packages": [{"id": "demo-one", "name": "Demo One", "version": "1", "sha256": hashlib.sha256(new).hexdigest()}]}
        ).encode()
        raw, sha = sources.fetch_package(conn, sid, "plugin", "demo-one")  # the kept index names the old zip: asked afresh, it fits
    assert raw == new and sha == hashlib.sha256(new).hexdigest()


def test_removing_a_source_removes_what_was_kept_of_it(client, net):
    sid = _source(client)
    with db.tx() as conn:
        sources.refresh(conn, sid)
        sources.remove(conn, sid)
        assert conn.execute("SELECT COUNT(*) FROM source_cache WHERE source_id = ?", (sid,)).fetchone()[0] == 0


# ------------------------------------------------------------------ the standard source comes with the app


@pytest.fixture()
def bundled(client, monkeypatch, net):
    monkeypatch.setattr(sources, "BUNDLE", REAL_BUNDLE)
    net.files = {}  # a connection that has nothing: every request would be a failure
    net.fail = "err.src_net"
    return net


def _default():
    with db.tx() as conn:
        return conn.execute("SELECT id FROM sources WHERE url = ?", (sources.DEFAULT_URL,)).fetchone()["id"]


def test_the_copy_in_the_app_is_a_valid_source():
    import sys

    sys.path.insert(0, str(HERE / "tools"))
    import check_source

    assert check_source.main([str(REAL_BUNDLE)]) == 0
    assert (REAL_BUNDLE / "VERSION").read_text().strip()
    assert not any(p.name.lower().startswith(("readme", "license")) for p in REAL_BUNDLE.rglob("*"))  # what the app reads, nothing else


def test_the_standard_source_works_without_any_connection(client, bundled):
    with db.tx() as conn:
        sources.seed_bundled(conn)
        offered = {
            (r["kind"], r["pkg_id"]) for r in conn.execute("SELECT kind, pkg_id FROM source_packages WHERE source_id = ?", (_default(),))
        }
        assert {("integration", "coding"), ("plugin", "demo-connector"), ("vehicle", "demo-diesel")} <= offered
        manifest = sources.fetch_manifest(conn, _default(), "integration", "coding")  # a package page, an install
        assert manifest["id"] == "coding" and manifest["pages"]
        assert sources.fetch_vehicle(conn, _default(), "demo-electric")[:2] == b"PK"  # the demo car
        shown = {r["id"]: r for r in sources.listing(conn, "integration")}[_default()]
        assert shown["bundled"] is True and shown["checked_at"] is None and shown["n_packages"] >= 2
    assert bundled.seen == []  # not one request


def test_the_standard_source_is_read_online_when_the_person_updates_it_and_falls_back_when_that_fails(client, bundled):
    with db.tx() as conn:
        sources.seed_bundled(conn)
    with db.tx() as conn:  # the limit is hit while the person presses Update list: the copy of the app answers, and it is said
        assert sources.refresh(conn, _default()) == "err.src_stale"
        assert conn.execute("SELECT COUNT(*) FROM source_packages WHERE source_id = ?", (_default(),)).fetchone()[0] >= 5
    assert _row(_default())["online_at"] is None  # still only the copy of the app is known
    bundled.fail = None
    bundled.files = {  # now the net answers, and the author has published a new package
        "plugins/index.json": json.dumps({"packages": [{"id": "brand-new", "name": "Brand new", "version": "3"}]}).encode(),
        "plugins/brand-new/plugin.json": json.dumps({"id": "brand-new", "kind": "plugin", "name": "Brand new", "version": "3"}).encode(),
    }
    with db.tx() as conn:
        assert sources.refresh(conn, _default()) is None
        assert ("plugin", "brand-new") in {
            (r["kind"], r["pkg_id"]) for r in conn.execute("SELECT kind, pkg_id FROM source_packages WHERE source_id = ?", (_default(),))
        }
        assert (
            sources.fetch_manifest(conn, _default(), "plugin", "brand-new")["version"] == "3"
        )  # read online: the copy of the app does not have it
    assert _row(_default())["online_at"] and not sources.listing(db.connect(), "plugin")[0]["bundled"]


def test_a_newer_copy_with_a_new_version_of_the_app_replaces_what_was_read_online(client, bundled, monkeypatch, tmp_path):
    with db.tx() as conn:
        sources.seed_bundled(conn)
    bundled.fail = None
    bundled.files = {
        "plugins/index.json": json.dumps({"packages": [{"id": "online-only", "name": "Online only", "version": "1"}]}).encode()
    }
    with db.tx() as conn:
        sources.refresh(conn, _default())
        conn.execute("UPDATE sources SET online_at = checked_at WHERE id = ?", (_default(),))
    newer = tmp_path / "newer-stdsource"
    shutil.copytree(REAL_BUNDLE, newer)
    (newer / "VERSION").write_text("brand-new-version\n")
    monkeypatch.setattr(sources, "BUNDLE", newer)
    with db.tx() as conn:
        sources.seed_bundled(conn)  # the app was updated: its copy is the newer one now
        ids = {
            r["pkg_id"] for r in conn.execute("SELECT pkg_id FROM source_packages WHERE source_id = ? AND kind = 'plugin'", (_default(),))
        }
        assert (
            ids == {"demo-connector"}
            and conn.execute("SELECT COUNT(*) FROM source_cache WHERE source_id = ?", (_default(),)).fetchone()[0] == 0
        )
    assert _row(_default())["online_at"] is None
    with db.tx() as conn:
        before = conn.execute("SELECT checked_at FROM sources WHERE id = ?", (_default(),)).fetchone()[0]
        sources.seed_bundled(conn)  # the same version again: nothing to do
        assert conn.execute("SELECT checked_at FROM sources WHERE id = ?", (_default(),)).fetchone()[0] == before
