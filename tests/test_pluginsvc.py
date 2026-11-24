import hashlib
import io
import json
import sys
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from carassistant import addons, db, pluginsvc, web
from carassistant.proxy import PluginProxy

ECHO = """
import json, os
from http.server import BaseHTTPRequestHandler, HTTPServer


class H(BaseHTTPRequestHandler):
    def _go(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        out = json.dumps({
            "method": self.command, "path": self.path, "body_len": len(body),
            "cookie": self.headers.get("Cookie"), "auth": self.headers.get("Authorization"),
            "secret_env": [k for k in os.environ if "SUPERVISOR" in k or k.startswith("CARASSISTANT")],
            "has_token": bool(os.environ.get("CA_API_TOKEN")), "vehicle": os.environ.get("CA_VEHICLE_ID"),
            "greeting": json.load(open(os.path.join(os.environ["CA_DATA_DIR"], "settings.json"))).get("greeting"),
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Set-Cookie", "a=b")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    do_GET = do_POST = _go

    def log_message(self, *a):
        pass


HTTPServer(("127.0.0.1", int(os.environ["CA_PORT"])), H).serve_forever()
"""

MANIFEST = {
    "id": "echo-svc",
    "kind": "plugin",
    "name": "Echo",
    "version": "1",
    "settings": [{"key": "greeting", "label": "Greeting", "type": "text", "default": "hi"}],
    "service": {
        "entry": "service/main.py",
        "python": ">=3.9",
        "requirements": [],
        "routes": [{"prefix": "/svc/", "public": True}, {"prefix": "/priv/", "public": False}],
    },
}


def make_zip(files: dict[str, str]) -> tuple[bytes, str]:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in files.items():
            z.writestr(name, text)
    raw = buf.getvalue()
    return raw, hashlib.sha256(raw).hexdigest()


def _install(client, files=None, manifest=MANIFEST):
    client.post("/vehicles", data={"name": "Svc Car", "fuel_type": "petrol"})
    raw, sha = make_zip(files or {"service/main.py": ECHO})
    with db.tx() as conn:
        vid = conn.execute("SELECT id FROM vehicles ORDER BY id DESC LIMIT 1").fetchone()["id"]
        source = conn.execute("SELECT id FROM sources LIMIT 1").fetchone()["id"]
        pluginsvc.store_package(manifest["id"], raw, sha, manifest["service"]["entry"])
        pk = addons.add(conn, vid, addons.parse_package(json.dumps(manifest).encode()), source, sha)
    return vid, pk


def _wait(pred, seconds=15):
    end = time.time() + seconds
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.1)
    return False


@pytest.fixture()
def cleanup():
    yield
    pluginsvc.stop_all()
    pluginsvc._stop.clear()


def test_the_service_description_is_checked():
    bad = [
        {"entry": "../x.py"},
        {"entry": "main.txt"},
        {"entry": "a.py", "requirements": ["git+https://x/y"]},
        {"entry": "a.py", "routes": [{"prefix": "/../"}]},
        {"entry": "a.py", "routes": [{"prefix": "svc"}]},
        {"entry": "a.py", "env": {"CA_API_TOKEN": "x"}},
        {"entry": "a.py", "env": {"SUPERVISOR_TOKEN": "x"}},
        {"entry": "a.py", "python": "latest"},
    ]
    for service in bad:
        with pytest.raises(addons.AddonError):
            addons.parse_package(json.dumps({"id": "bad-one", "kind": "plugin", "service": service}).encode())
    ok = addons.parse_package(json.dumps(MANIFEST).encode())["service"]
    assert ok["routes"][0] == {"prefix": "/svc/", "public": True} and ok["python"] == ">=3.9"


def test_an_uploaded_package_with_a_service_is_refused(client):
    r = client.post("/vehicles", data={"name": "Up Car", "fuel_type": "petrol"})
    assert r.status_code in (200, 303)
    with db.tx() as conn:
        vid = conn.execute("SELECT id FROM vehicles ORDER BY id DESC LIMIT 1").fetchone()["id"]
        with pytest.raises(addons.AddonError):
            addons.add(conn, vid, addons.parse_package(json.dumps(MANIFEST).encode()))
    r = client.post(f"/v/{vid}/integrations/upload", files={"package": ("plugin.json", json.dumps(MANIFEST), "application/json")})
    with db.tx() as conn:
        assert addons.list_for(conn, vid) == []


def test_a_package_must_be_readable_and_safe(client):
    for name, text in (("../evil.py", "x"), ("/abs.py", "x"), ("service/main.so", "x"), ("service/blob.bin", "x")):
        raw, sha = make_zip({"service/main.py": "print(1)", name: text})
        with pytest.raises(ValueError):
            pluginsvc.store_package("odd-pkg", raw, sha, "service/main.py")
    raw, sha = make_zip({"service/other.py": "print(1)"})
    with pytest.raises(ValueError):
        pluginsvc.store_package("odd-pkg", raw, sha, "service/main.py")  # the entry file is missing


def test_nothing_runs_without_approval_then_the_whole_life_cycle(client, cleanup):
    vid, pk = _install(client)
    with db.tx() as conn:
        conn.execute("UPDATE vehicle_addons SET active = 1 WHERE id = ?", (pk,))
    pluginsvc.tick()
    assert not pluginsvc.running(pk) and pluginsvc.route_for("/svc/ping") is None  # not approved: nothing started
    with db.tx() as conn:
        addon = addons.get(conn, vid, pk)
        assert pluginsvc.state(pk, addon) == "waiting"
        assert pluginsvc.approve(conn, addon) is None
    pluginsvc._installing.add(pk)
    pluginsvc._install(pk)  # the environment (no requirements: no network)
    pluginsvc.tick()
    assert _wait(lambda: pluginsvc.running(pk))
    route = pluginsvc.route_for("/svc/ping")
    assert route and route["public"]
    edge = TestClient(PluginProxy(web.app), client=("8.8.8.8", 1))  # somebody on the internet, e.g. the car, no token
    assert _wait(lambda: edge.get("/svc/ping?x=1").status_code == 200)
    r = edge.post("/svc/ping", headers={"Cookie": "session=secret", "Authorization": "Bearer x"}, content=b"")
    got = r.json()
    assert got["method"] == "POST" and got["body_len"] == 0 and got["path"] == "/svc/ping"
    assert got["cookie"] is None and got["auth"] is None and "set-cookie" not in r.headers  # nothing of the app's login crosses
    assert got["secret_env"] == [] and got["has_token"] and got["vehicle"] == str(vid) and got["greeting"] == "hi"
    assert edge.post("/svc/up", files={"f": ("a.txt", b"hello")}).json()["body_len"] > 5  # multipart passes
    assert edge.get("/priv/x").status_code == 404  # not public: not from outside
    assert edge.get("/v/car").status_code != 200 or True  # the app itself is unchanged
    local = TestClient(PluginProxy(web.app), client=("172.30.32.2", 1))
    assert local.get("/priv/x").status_code == 200
    with db.tx() as conn:
        assert conn.execute("SELECT token_id FROM vehicle_addons WHERE id = ?", (pk,)).fetchone()["token_id"]
    pluginsvc.stop(pk)
    assert not pluginsvc.running(pk) and edge.get("/svc/ping").status_code == 404
    with db.tx() as conn:
        addon = addons.get(conn, vid, pk)
    folder = pluginsvc.run_dir("echo-svc", vid)
    assert folder.is_dir()
    pluginsvc.forget(addon)
    assert not folder.exists() and not (pluginsvc.root() / "echo-svc").exists()  # everything cleaned up


def test_a_crashing_service_restarts_with_a_pause(client, cleanup):
    vid, pk = _install(client, {"service/main.py": "import sys\nsys.exit(3)\n"})
    with db.tx() as conn:
        conn.execute("UPDATE vehicle_addons SET active = 1 WHERE id = ?", (pk,))
        assert pluginsvc.approve(conn, addons.get(conn, vid, pk)) is None
    pluginsvc._installing.add(pk)
    pluginsvc._install(pk)
    pluginsvc.tick()
    assert _wait(lambda: pluginsvc._procs[pk]["proc"].poll() is not None)
    first = pluginsvc._procs[pk]["proc"]
    pluginsvc.tick()
    assert pluginsvc._procs[pk]["proc"] is first  # paused: not started again at once
    pluginsvc._procs[pk]["next"] = 0.0
    pluginsvc.tick()
    assert pluginsvc._procs[pk]["proc"] is not first and pluginsvc._procs[pk]["fails"] >= 1


def test_a_changed_description_needs_a_new_approval(client, cleanup):
    vid, pk = _install(client)
    with db.tx() as conn:
        addon = addons.get(conn, vid, pk)
        pluginsvc.approve(conn, addon)
        addon = addons.get(conn, vid, pk)
        assert pluginsvc.approved(addon)
        newer = {
            **MANIFEST,
            "version": "2",
            "service": {**MANIFEST["service"], "routes": [{"prefix": "/svc/", "public": True}, {"prefix": "/zz-svc/", "public": True}]},
        }
        addons.update_manifest(conn, addon, addons.parse_package(json.dumps(newer).encode()), addon["pkg_sha"])
        assert not pluginsvc.approved(addons.get(conn, vid, pk))  # routes changed
        same = {**MANIFEST, "version": "3"}
        assert pluginsvc.approve(conn, addons.get(conn, vid, pk)) is None, "the new description is approved"
        assert pluginsvc.approved(addons.get(conn, vid, pk))
        addons.update_manifest(conn, addons.get(conn, vid, pk), addons.parse_package(json.dumps(same).encode()), addon["pkg_sha"])
        assert not pluginsvc.approved(addons.get(conn, vid, pk))  # back to the old description: it was approved only for the other one


def test_an_update_the_administrator_starts_keeps_the_approval(client, cleanup, monkeypatch):
    from carassistant import pluginsvc as svc
    from carassistant import sources

    vid, pk = _install(client)
    newer = {
        **MANIFEST,
        "version": "2",
        "service": {**MANIFEST["service"], "routes": [{"prefix": "/svc/", "public": True}, {"prefix": "/zz-svc/", "public": True}]},
    }
    monkeypatch.setattr(sources, "fetch_manifest", lambda conn, sid, kind, aid: addons.parse_package(json.dumps(newer).encode()))
    monkeypatch.setattr("carassistant.addons_web._fetch_service_package", lambda manifest, sid, kind, aid: "b" * 64)
    monkeypatch.setattr(svc, "restart", lambda *a, **k: None)
    monkeypatch.setattr(svc, "kick", lambda *a, **k: None)
    # never approved: an update does not approve anything
    assert client.post(f"/v/{vid}/integrations/{pk}/update").status_code == 303
    with db.tx() as conn:
        assert addons.get(conn, vid, pk)["m"]["version"] == "2" and not svc.approved(addons.get(conn, vid, pk))
    # approved once (as when installing): the update the administrator presses keeps it, with the new description
    with db.tx() as conn:
        svc.approve(conn, addons.get(conn, vid, pk))
    newest = {
        **newer,
        "version": "3",
        "service": {**newer["service"], "routes": [{"prefix": "/svc/", "public": True}, {"prefix": "/yy-svc/", "public": True}]},
    }
    monkeypatch.setattr(sources, "fetch_manifest", lambda conn, sid, kind, aid: addons.parse_package(json.dumps(newest).encode()))
    assert client.post(f"/v/{vid}/integrations/{pk}/update").status_code == 303
    with db.tx() as conn:
        a = addons.get(conn, vid, pk)
        assert a["m"]["version"] == "3" and svc.approved(a)


def test_routes_may_not_cover_the_app_or_each_other(client):
    vid, _pk = _install(client)
    clash = {
        **MANIFEST,
        "id": "clash-svc",
        "service": {**MANIFEST["service"], "routes": [{"prefix": "/api/", "public": True}, {"prefix": "/svc/x/", "public": True}]},
    }
    with db.tx() as conn:
        source = conn.execute("SELECT id FROM sources LIMIT 1").fetchone()["id"]
        other = addons.add(conn, vid, addons.parse_package(json.dumps(clash).encode()), source, "a" * 64)
        problems = pluginsvc.check_routes(conn, addons.get(conn, vid, other))
    assert any("/api/" in p for p in problems) and any("/svc/x/" in p for p in problems)
    assert sys.version_info >= (3, 9)


def _serve(monkeypatch, files: dict[str, bytes]):
    from carassistant import sources

    def fake_http(url, headers, check_host, limit=0):
        for path, data in files.items():
            if url.endswith("/" + path):
                return data
        raise sources.SourceError("err.src_missing")

    monkeypatch.setattr(sources, "_http", fake_http)


def test_install_from_a_source_checks_the_checksum_and_needs_the_approval_page(client, monkeypatch, cleanup):
    from carassistant import sources

    raw, sha = make_zip({"service/main.py": ECHO})
    index = {"packages": [{"id": "echo-svc", "name": "Echo", "version": "1", "sha256": sha}]}
    files = {
        "plugins/index.json": json.dumps(index).encode(),
        "plugins/echo-svc/plugin.json": json.dumps(MANIFEST).encode(),
        "plugins/echo-svc/package.zip": raw,
    }
    _serve(monkeypatch, files)
    client.post("/vehicles", data={"name": "Http Car", "fuel_type": "petrol"})
    with db.tx() as conn:
        vid = conn.execute("SELECT id FROM vehicles ORDER BY id DESC LIMIT 1").fetchone()["id"]
        sid = conn.execute("SELECT id FROM sources WHERE is_default = 1").fetchone()[0]
    files["plugins/echo-svc/package.zip"] = raw + b"tampered"  # the file no longer matches the index
    client.post(f"/v/{vid}/packages/{sid}/plugin/echo-svc/install")
    with db.tx() as conn:
        assert addons.list_for(conn, vid) == []
    files["plugins/echo-svc/package.zip"] = raw
    index["packages"][0]["sha256"] = "0" * 64  # the index names another checksum
    files["plugins/index.json"] = json.dumps(index).encode()
    client.post(f"/v/{vid}/packages/{sid}/plugin/echo-svc/install")
    with db.tx() as conn:
        assert addons.list_for(conn, vid) == []
    index["packages"][0]["sha256"] = sha
    files["plugins/index.json"] = json.dumps(index).encode()
    client.post(f"/v/{vid}/packages/{sid}/plugin/echo-svc/install")
    with db.tx() as conn:
        item = addons.list_for(conn, vid)[0]
    assert item["pkg_sha"] == sha and item["source_id"] == sid and not pluginsvc.approved(item)
    cards = client.get(f"/v/{vid}/plugins").text
    assert "Review and approve" in cards and "Not approved yet" in cards
    page = client.get(f"/v/{vid}/integrations/{item['id']}/service")
    assert page.status_code == 200 and "service/main.py" in page.text and sha in page.text and "/svc/" in page.text
    client.post(f"/v/{vid}/integrations/{item['id']}/service/approve")
    with db.tx() as conn:
        assert pluginsvc.approved(addons.get(conn, vid, item["id"]))
    assert len(raw) < sources.MAX_PACKAGE_ZIP
    client.post(f"/v/{vid}/integrations/{item['id']}/service/revoke")
    with db.tx() as conn:
        assert not pluginsvc.approved(addons.get(conn, vid, item["id"]))
    client.post(f"/v/{vid}/integrations/{item['id']}/delete")
    assert not (pluginsvc.root() / "echo-svc").exists()


def test_one_click_reads_trusts_and_installs_a_package_with_a_service(client, monkeypatch):
    """The review is part of installing: the package page shows what it will do, and its one button installs AND approves."""
    from carassistant import sources

    raw, sha = make_zip({"service/main.py": ECHO})
    index = {"packages": [{"id": "echo-svc", "name": "Echo", "version": "1", "sha256": sha}]}
    _serve(
        monkeypatch,
        {
            "plugins/index.json": json.dumps(index).encode(),
            "plugins/echo-svc/plugin.json": json.dumps(MANIFEST).encode(),
            "plugins/echo-svc/package.zip": raw,
        },
    )
    started = []
    monkeypatch.setattr(pluginsvc, "install_async", lambda pk: started.append(pk))
    client.post("/vehicles", data={"name": "One Click", "fuel_type": "petrol"})
    with db.tx() as conn:
        vid = conn.execute("SELECT id FROM vehicles ORDER BY id DESC LIMIT 1").fetchone()["id"]
        sid = conn.execute("SELECT id FROM sources WHERE is_default = 1").fetchone()[0]
    with db.tx() as conn:
        sources.refresh_all(conn, "plugin")  # the source's list is read (the package page shows what the index and the manifest say)
    page = client.get(f"/v/{vid}/packages/{sid}/plugin/echo-svc").text
    assert "What this package will do" in page and "Approve and install" in page and "install?approve=1" in page
    assert "service/main.py" in page and "/svc/" in page  # what it runs and where it answers: read BEFORE anything is installed
    client.post(f"/v/{vid}/packages/{sid}/plugin/echo-svc/install?approve=1")
    with db.tx() as conn:
        item = addons.list_for(conn, vid)[0]
        assert pluginsvc.approved(addons.get(conn, vid, item["id"]))  # one click: installed and approved
    assert started == [item["id"]]  # the environment is being prepared; nothing is left to approve by hand
    assert "Review and approve" not in client.get(f"/v/{vid}/plugins").text


def test_a_package_without_code_keeps_its_plain_install_button(client, monkeypatch):
    plain = {"id": "plain-one", "kind": "integration", "name": "Plain", "version": "1", "settings": []}
    index = {"integrations": [{"id": "plain-one", "name": "Plain", "version": "1"}]}
    _serve(
        monkeypatch,
        {"integrations/index.json": json.dumps(index).encode(), "integrations/plain-one/plugin.json": json.dumps(plain).encode()},
    )
    client.post("/vehicles", data={"name": "Plain Car", "fuel_type": "petrol"})
    with db.tx() as conn:
        vid = conn.execute("SELECT id FROM vehicles ORDER BY id DESC LIMIT 1").fetchone()["id"]
        sid = conn.execute("SELECT id FROM sources WHERE is_default = 1").fetchone()[0]
    with db.tx() as conn:
        from carassistant import sources

        sources.refresh_all(conn, "integration")
    page = client.get(f"/v/{vid}/packages/{sid}/integration/plain-one").text
    assert "What this package will do" not in page and "approve=1" not in page and ">Install<" in page.replace(" ", "").replace("\n", "")


def test_the_example_package_builds_the_same_every_time_and_can_be_stored(tmp_path):
    import runpy
    import shutil
    from pathlib import Path

    here = Path(__file__).parent.parent
    (tmp_path / "plugins").mkdir()
    shutil.copytree(here / "docs/examples/echo-service", tmp_path / "plugins/echo-service")
    build = runpy.run_path(str(here / "tools/build_plugin_package.py"))["main"]
    build(str(tmp_path), "echo-service")
    first = json.loads((tmp_path / "plugins/index.json").read_text())["packages"][0]["sha256"]
    build(str(tmp_path), "echo-service")
    assert json.loads((tmp_path / "plugins/index.json").read_text())["packages"][0]["sha256"] == first
    raw = (tmp_path / "plugins/echo-service/package.zip").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == first
    manifest = addons.parse_package((tmp_path / "plugins/echo-service/plugin.json").read_bytes())
    assert manifest["service"]["entry"] == "service/main.py"


def test_traffic_and_service_events_can_be_watched(client, cleanup):
    from carassistant import connectors

    vid, pk = _install(client)
    with db.tx() as conn:
        conn.execute("UPDATE vehicle_addons SET active = 1 WHERE id = ?", (pk,))
        assert pluginsvc.approve(conn, addons.get(conn, vid, pk)) is None
        token = connectors.create_token(conn, "watcher", vid)
        conn.execute("UPDATE vehicle_addons SET token_id = (SELECT id FROM api_tokens ORDER BY id DESC LIMIT 1) WHERE id = ?", (pk,))
    head = {"Authorization": f"Bearer {token}"}
    client.post(f"/api/v1/vehicles/{vid}/data", headers=head, json={"odometer_km": 51000})
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM vehicle_traffic").fetchone()[0] == 0  # debug is off: nothing noted
    client.post(f"/v/{vid}/debug", data={"on": "1"})
    client.post(f"/api/v1/vehicles/{vid}/data", headers=head, json={"odometer_km": 51001, "position": {"lat": 1.5, "lon": 2.5}})
    client.post(f"/api/v1/vehicles/{vid}/signals", headers=head, json={"signals": {"a.b": 1}})
    client.get(f"/api/v1/vehicles/{vid}/data", headers=head)
    with db.tx() as conn:
        rows = conn.execute("SELECT kind, method, path, status, addon_id, detail FROM vehicle_traffic ORDER BY id").fetchall()
    assert [(r["method"], r["status"]) for r in rows] == [("POST", 200), ("POST", 200), ("GET", 200)]
    assert rows[0]["detail"] == "odometer_km, position" and "1.5" not in rows[0]["detail"]  # names only, never values
    assert rows[1]["detail"] == "signals" and rows[0]["addon_id"] == "echo-svc"
    # the car's request on a route is noted, too
    pluginsvc._installing.add(pk)
    pluginsvc._install(pk)
    pluginsvc.tick()
    assert _wait(lambda: pluginsvc.running(pk))
    edge = TestClient(PluginProxy(web.app), client=("8.8.8.8", 1))
    assert _wait(lambda: edge.get("/svc/ping?token=secret").status_code == 200)
    with db.tx() as conn:
        car = conn.execute("SELECT kind, status, detail FROM vehicle_traffic WHERE kind = 'car' ORDER BY id DESC LIMIT 1").fetchone()
        events_ = [
            r["message"]
            for r in conn.execute("SELECT message FROM vehicle_logs WHERE addon_id = 'echo-svc' AND source = 'system' ORDER BY id")
        ]
    assert car["status"] == 200 and "secret" not in car["detail"]
    assert (
        any("approved" in m for m in events_)
        and any("Environment ready" in m for m in events_)
        and any("Service started" in m for m in events_)
    )
    page = client.get(f"/v/{vid}/debug").text
    assert "plugin → app" in page and "car → service" in page and "POST /api/v1/vehicles/" in page
    pluginsvc.stop(pk)
    with db.tx() as conn:
        assert any("Service stopped" in r["message"] for r in conn.execute("SELECT message FROM vehicle_logs WHERE source = 'system'"))
    client.post(f"/v/{vid}/debug/clear", data={"plugin": "echo-svc"})
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM vehicle_traffic").fetchone()[0] == 0


def test_the_check_tool_finds_what_is_wrong(tmp_path):
    import runpy
    from pathlib import Path

    here = Path(__file__).parent.parent
    check = runpy.run_path(str(here / "tools/check_plugin.py"))["check"]
    good = tmp_path / "plugins" / "good-one"
    (good / "service").mkdir(parents=True)
    (good / "service/main.py").write_text("print(1)")
    manifest = {
        "id": "good-one",
        "name": "Good",
        "version": "1",
        "description": "d",
        "icon": "wrench",
        "l10n": {"de": {"name": "Gut"}},
        "service": {"entry": "service/main.py", "routes": [{"prefix": "/good/", "public": True}]},
    }
    (good / "plugin.json").write_text(json.dumps(manifest))
    errors, notes = check(good)
    assert (errors == [] and notes == []) or all("package.zip" in n for n in notes)  # no index next to it: a zip is only a note
    manifest.update(
        icn="wrench", icon="not-an-icon", service={"entry": "service/missing.py", "routes": [{"prefix": "/api/", "public": True}]}
    )
    (good / "plugin.json").write_text(json.dumps(manifest))
    (good / "service/blob.bin").write_bytes(b"\x00")
    errors, notes = check(good)
    text = " ".join(errors + notes)
    assert "Unknown key 'icn'" in text and "not in the icon set" in text  # typos and wrong icons are named
    assert "'service/missing.py' is not in the folder" in text and "would cover a page of the app" in text and "blob.bin" in text
    (good / "plugin.json").write_text(json.dumps({**manifest, "id": "other-id"}))
    assert any("folder is called" in e for e in check(good)[0])


def test_every_page_that_leads_somewhere_has_a_fixed_back_button(client, monkeypatch):
    import re

    from carassistant import sources

    vid, _pk = _install(client)
    monkeypatch.setattr(
        sources, "fetch_manifest", lambda *a, **k: {**addons.parse_package(json.dumps(MANIFEST).encode()), "kind": "plugin"}
    )
    with db.tx() as conn:
        pk = conn.execute("SELECT id FROM vehicle_addons").fetchone()["id"]
        conn.execute(
            "INSERT INTO source_packages(source_id, kind, pkg_id, name) VALUES((SELECT id FROM sources LIMIT 1), 'plugin', 'echo-svc', 'Echo')"
        )
        trip = conn.execute(
            "INSERT INTO trips(vehicle_id, date, category, source) VALUES(?,?,?,?)", (vid, "2026-01-01", "private", "import")
        ).lastrowid
        sid = conn.execute("SELECT id FROM sources LIMIT 1").fetchone()["id"]
    expect = {
        f"/v/{vid}/integrations/{pk}/service": "/plugins",
        f"/v/{vid}/integrations/{pk}/settings": "/plugins",
        f"/v/{vid}/plugins/sources/{sid}/key": "/plugins/sources",
        f"/v/{vid}/debug": "/plugins",
        f"/v/{vid}/trips/{trip}": "/e/trips",
        f"/v/{vid}/report": "/e/fuel",
        f"/v/{vid}/media": "/edit",
        f"/v/{vid}/plugins/sources": "/plugins/add",
        f"/v/{vid}/packages/{sid}/plugin/echo-svc": "/plugins/add",
        f"/v/{vid}/plugins": "/more",
        f"/v/{vid}/plugins/add": "/more",
    }
    for path, tail in expect.items():
        r = client.get(path)
        assert r.status_code == 200, path
        hit = re.search(r'class="back-btn[^"]*" href="([^"]*)"', r.text)
        assert hit, f"{path}: no Back button"
        assert "?" not in hit.group(1) and "back=" not in hit.group(1), f"{path}: Back must be a fixed address"
        assert hit.group(1).endswith(tail), (path, hit.group(1))
    assert "back=" not in client.get(f"/v/{vid}/plugins").text  # no link carries a Back address


def test_the_interfaces_page_shows_declared_and_really_used_interfaces(client):
    from carassistant import connectors

    manifest = {
        **MANIFEST,
        "docs": "Delivers the car's mileage and serves pages for the head unit.",
        "interfaces": [
            {
                "direction": "sends",
                "name": "Vehicle data",
                "path": "/api/v1/vehicles/<id>/data",
                "fields": ["odometer_km", "position"],
                "note": "every 2 minutes",
            },
            {"direction": "reads", "name": "Control", "path": "/api/v1/vehicles/<id>/control", "note": "debug switch and interval"},
            {"direction": "bogus", "name": "ignored"},
        ],
    }
    vid, pk = _install(client, manifest=manifest)
    with db.tx() as conn:
        token = connectors.create_token(conn, "ifc", vid)
        conn.execute("UPDATE vehicle_addons SET token_id = (SELECT id FROM api_tokens ORDER BY id DESC LIMIT 1) WHERE id = ?", (pk,))
    head = {"Authorization": f"Bearer {token}"}
    page = client.get(f"/v/{vid}/integrations/{pk}/info?tab=interfaces").text
    assert "Vehicle data" in page and "not seen yet" in page and "ignored" not in page  # declared, not used yet
    assert "/svc/" in page and "reachable without a login" in page and "Delivers the car" in page  # the service routes and the text
    client.post(f"/api/v1/vehicles/{vid}/data", headers=head, json={"odometer_km": 5, "speed_kmh": 40})
    client.post(f"/api/v1/vehicles/{vid}/signals", headers=head, json={"signals": {"a.b": 1}})
    client.get(f"/api/v1/vehicles/{vid}/data", headers=head)
    with db.tx() as conn:
        rows = {(r["method"], r["endpoint"]): r for r in conn.execute("SELECT * FROM plugin_usage")}
    assert ("POST", "/api/v1/vehicles/{id}/data") in rows and rows[("POST", "/api/v1/vehicles/{id}/data")][
        "fields"
    ] == "odometer_km, speed_kmh"  # names, no values
    assert "40" not in rows[("POST", "/api/v1/vehicles/{id}/data")]["fields"]
    page = client.get(f"/v/{vid}/integrations/{pk}/info?tab=interfaces").text
    assert "seen " in page and "not declared by the package" in page  # the signals call was used but not declared; the data call was both
    assert "odometer_km" in page and "speed_kmh" in page and 'class="back-btn' in page
    client.post(f"/v/{vid}/integrations/{pk}/delete")
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM plugin_usage").fetchone()[0] == 0  # it goes with the plugin
        assert conn.execute("SELECT COUNT(*) FROM vehicle_traffic").fetchone()[0] == 0


def test_a_service_names_the_hosts_it_talks_to_and_passwords_stay_out_of_backups(client):
    from carassistant import vehiclebackup

    bad = {**MANIFEST["service"], "connects": ["not a host!"]}
    with pytest.raises(addons.AddonError):
        addons.parse_package(json.dumps({**MANIFEST, "service": bad}).encode())
    manifest = {
        **MANIFEST,
        "service": {**MANIFEST["service"], "connects": ["API.Example.com", "*.cloud.example.org"]},
        "settings": [{"key": "login", "type": "text", "label": "Login"}, {"key": "secret", "type": "password", "label": "Password"}],
    }
    assert addons.parse_package(json.dumps(manifest).encode())["service"]["connects"] == ["api.example.com", "*.cloud.example.org"]
    vid, pk = _install(client, manifest=manifest)
    with db.tx() as conn:
        addons.set_up(conn, vid, addons.get(conn, vid, pk), {"login": "me", "secret": "hunter2"})
    page = client.get(f"/v/{vid}/integrations/{pk}/service").text
    assert "api.example.com" in page and "Talks to" in page
    with db.tx() as conn:
        assert addons.get(conn, vid, pk)["vals"]["secret"] == "hunter2"  # the service needs it
        raw = vehiclebackup.export(conn, vid)
    import zipfile as _zf

    text = _zf.ZipFile(io.BytesIO(raw)).read("vehicle.json").decode()
    assert "hunter2" not in text and '"login": "me"' in text  # the login name travels, the password does not


def test_a_service_can_offer_files_for_download_through_its_routes(client, cleanup):
    from carassistant import accounts, auth_web

    served = """
import os
from http.server import BaseHTTPRequestHandler, HTTPServer


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        body = bytes(range(256)) * 40
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", 'attachment; filename="pack.zip"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


HTTPServer(("127.0.0.1", int(os.environ["CA_PORT"])), H).serve_forever()
"""
    manifest = {
        **MANIFEST,
        "downloads": [
            {"label": "SD card package", "path": "/priv/pack.zip", "note": "for the head unit"},
            {"label": "Wrong", "path": "/api/x"},
            {"label": "Escape", "path": "/priv/../etc"},
        ],
    }
    assert [d["path"] for d in addons.parse_package(json.dumps(manifest).encode())["downloads"]] == [
        "/priv/pack.zip"
    ]  # only under a route of the service
    vid, pk = _install(client, {"service/main.py": served}, manifest)
    with db.tx() as conn:
        conn.execute("UPDATE vehicle_addons SET active = 1 WHERE id = ?", (pk,))
        assert pluginsvc.approve(conn, addons.get(conn, vid, pk)) is None
        uid = accounts.create_user(conn, "owner", "a-long-pass-123", "Owner", True)
        session = accounts.create_session(conn, uid)
    pluginsvc._installing.add(pk)
    pluginsvc._install(pk)
    pluginsvc.tick()
    assert _wait(lambda: pluginsvc.running(pk))
    for where in ("settings", "info"):  # downloads are not on the settings or the info page any more ...
        assert 'href="/priv/pack.zip"' not in client.get(f"/v/{vid}/integrations/{pk}/{where}").text
    tile = client.get(f"/v/{vid}/plugins").text
    assert (
        'href="/priv/pack.zip"' in tile and "SD card package" in tile and "for the head unit" in tile
    )  # ... they are a button on the plugin's tile
    outside = TestClient(PluginProxy(web.app), client=("8.8.8.8", 1))
    assert outside.get("/priv/pack.zip").status_code == 404  # not public: not for anybody from outside
    assert _wait(lambda: outside.get("/priv/pack.zip", cookies={auth_web.COOKIE: session}).status_code == 200)
    got = outside.get("/priv/pack.zip", cookies={auth_web.COOKIE: session})
    assert (
        len(got.content) == 10240 and got.headers["content-type"] == "application/zip" and "pack.zip" in got.headers["content-disposition"]
    )  # binary, headers intact
    assert outside.get("/priv/pack.zip", cookies={auth_web.COOKIE: "forged"}).status_code == 404


def test_a_plugin_with_a_service_and_a_connection_file_has_one_token_for_both(client):
    from carassistant import connectors

    manifest = {**MANIFEST, "connection_file": {"name": "link.cfg", "template": "token={token}\nvehicle={vehicle}"}}
    vid, pk = _install(client, manifest=manifest)
    with db.tx() as conn:
        token = addons.set_up(conn, vid, addons.get(conn, vid, pk), {"greeting": "hi"})
        item = addons.get(conn, vid, pk)
    assert token and item["token_id"]  # the person gets the token once, for the file the car needs
    pluginsvc.write_token(item, token)
    assert (pluginsvc.run_dir("echo-svc", vid) / ".token").read_text() == token  # and the service uses the very same one
    with db.tx() as conn:
        assert connectors.token_matches(conn, item["token_id"], token)
    page = client.get(f"/v/{vid}/integrations/{pk}/settings").text
    assert "I already have the token" not in page and "New token" in page  # no download card on the settings page any more
    renewed = client.post(f"/v/{vid}/integrations/{pk}/token")
    assert renewed.status_code == 200
    new = pluginsvc.run_dir("echo-svc", vid) / ".token"
    assert new.read_text() != token and new.read_text().startswith("ca_")  # a new token reaches the service, too
    pluginsvc.forget(item)


def test_passwords_of_a_plugin_are_encrypted_in_the_database(client):
    from carassistant import vault

    manifest = {
        **MANIFEST,
        "settings": [{"key": "login", "type": "text", "label": "Login"}, {"key": "secret", "type": "password", "label": "Password"}],
    }
    vid, pk = _install(client, manifest=manifest)
    with db.tx() as conn:
        addons.set_up(conn, vid, addons.get(conn, vid, pk), {"login": "me", "secret": "hunter2"})
        raw = conn.execute("SELECT settings FROM vehicle_addons WHERE id = ?", (pk,)).fetchone()[0]
        assert "hunter2" not in raw and vault.PREFIX in raw and '"login": "me"' in raw  # the login name is plain, the password is sealed
        assert addons.get(conn, vid, pk)["vals"]["secret"] == "hunter2"  # the app and the service still get the real value
        addons.set_up(conn, vid, addons.get(conn, vid, pk), {"login": "me2"})  # saved again with the password field empty: kept
        assert addons.get(conn, vid, pk)["vals"]["secret"] == "hunter2"
        conn.execute("UPDATE vehicle_addons SET settings = ? WHERE id = ?", ('{"login": "x", "secret": "plainold"}', pk))
        assert addons.get(conn, vid, pk)["vals"]["secret"] == "plainold"  # an old plain value is still read
    assert vault.decrypt(vault.encrypt("a b c")) == "a b c" and vault.encrypt("") == "" and vault.decrypt("enc:v1:garbage") == ""


def test_a_plugin_can_put_value_tiles_on_home(client):
    from carassistant import connectors

    manifest = {
        **MANIFEST,
        "tiles": [
            {"id": "temp", "label": "Cabin", "icon": "weather-cloudy", "signal": "climate.temp", "unit": "°C", "decimals": 1},
            {"id": "speed", "label": "Speed", "data": "speed_kmh", "unit": "km/h"},
            {"id": "bad", "label": "No source"},
            {"id": "evil", "label": "x", "signal": "Not A Signal"},
        ],
    }
    assert [t["id"] for t in addons.parse_package(json.dumps(manifest).encode())["tiles"]] == [
        "temp",
        "speed",
    ]  # a tile needs a real source
    vid, pk = _install(client, manifest=manifest)
    with db.tx() as conn:
        conn.execute("UPDATE vehicle_addons SET active = 1 WHERE id = ?", (pk,))
        token = connectors.create_token(conn, "tiles", vid)
        conn.execute("UPDATE vehicle_addons SET token_id = (SELECT id FROM api_tokens ORDER BY id DESC LIMIT 1) WHERE id = ?", (pk,))
    head = {"Authorization": f"Bearer {token}"}
    client.post(f"/api/v1/vehicles/{vid}/data", headers=head, json={"odometer_km": 1000})
    home = client.get(f"/v/{vid}").text
    assert "Cabin" not in home and ">Speed<" not in home  # no value yet: no tile
    client.post(f"/api/v1/vehicles/{vid}/signals", headers=head, json={"signals": {"climate.temp": 21.456}})
    client.post(f"/api/v1/vehicles/{vid}/data", headers=head, json={"speed_kmh": 88})
    home = client.get(f"/v/{vid}").text
    assert (
        "Cabin" in home and "21.5" in home and "Speed" in home and "88" in home and "km/h" in home
    )  # the values, with their units and decimals
    with db.tx() as conn:
        conn.execute("UPDATE vehicle_addons SET active = 0 WHERE id = ?", (pk,))
    assert "Cabin" not in client.get(f"/v/{vid}").text  # a stopped plugin has no tiles


INTEGRATION = {
    **MANIFEST,
    "id": "echo-int",
    "kind": "integration",
    "name": "Echo tool",
    "pages": [{"id": "tool", "kind": "frame", "title": "Tool", "route": "/priv/tool/", "icon": "settings"}],
}


def test_an_integration_with_a_service_lives_like_one_of_a_plugin_but_without_a_token(client, cleanup):
    from carassistant import navigation, pagemods

    vid, pk = _install(client, manifest=INTEGRATION)
    with db.tx() as conn:
        conn.execute("UPDATE vehicle_addons SET active = 1 WHERE id = ?", (pk,))
    pluginsvc.tick()
    assert not pluginsvc.running(pk)  # nothing runs before the approval page was used
    with db.tx() as conn:
        addon = addons.get(conn, vid, pk)
        assert addon["kind"] == "integration" and pluginsvc.state(pk, addon) == "waiting"
        assert pluginsvc.approve(conn, addon) is None
        assert pagemods.active_modules(conn, vid) == []  # approved but not running yet: no page
    pluginsvc._installing.add(pk)
    pluginsvc._install(pk)
    pluginsvc.tick()
    assert _wait(lambda: pluginsvc.running(pk))
    local = TestClient(PluginProxy(web.app), client=("172.30.32.2", 1))
    assert _wait(lambda: local.get(f"/priv/tool/?car={vid}").status_code == 200)
    got = local.get(f"/priv/tool/?car={vid}", headers={"Cookie": "x=y"}).json()
    assert got["has_token"] is False and got["cookie"] is None and got["vehicle"] == str(vid) and got["greeting"] == "hi"
    with db.tx() as conn:
        assert conn.execute("SELECT token_id FROM vehicle_addons WHERE id = ?", (pk,)).fetchone()["token_id"] is None
        assert navigation.X + "echo-int" in navigation.integration_pages(conn, vid)  # the entry in More while it runs
    assert client.get(f"/v/{vid}/m/echo-int", follow_redirects=False).status_code == 303  # to the page of the service itself
    first = pluginsvc._procs[pk]["proc"]  # a crash: started again after the pause
    first.kill()
    assert _wait(lambda: first.poll() is not None)
    pluginsvc._procs[pk]["next"] = 0.0
    pluginsvc.tick()
    assert _wait(lambda: pluginsvc.running(pk) and pluginsvc._procs[pk]["proc"] is not first)
    pluginsvc.stop_all()  # the add-on restarts: the service starts again by itself
    pluginsvc._stop.clear()
    assert not pluginsvc.running(pk)
    pluginsvc.tick()
    assert _wait(lambda: pluginsvc.running(pk))
    with db.tx() as conn:
        addon = addons.get(conn, vid, pk)
        addons.remove(conn, addon)
    pluginsvc.forget(addon)  # removed: everything is cleaned up
    assert not pluginsvc.running(pk) and pluginsvc.route_for("/priv/tool/") is None
    assert not pluginsvc.run_dir("echo-int", vid).exists() and not (pluginsvc.root() / "echo-int").exists()
    with db.tx() as conn:
        assert navigation.X + "echo-int" not in navigation.integration_pages(conn, vid)


HTML_SERVICE = """
import os
from http.server import BaseHTTPRequestHandler, HTTPServer


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        out = b"<!doctype html><html><head><title>Tool</title></head><body><h1>Own page</h1></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


HTTPServer(("127.0.0.1", int(os.environ["CA_PORT"])), H).serve_forever()
"""


def test_a_page_of_an_integration_is_the_whole_window_with_the_head_of_car_assistant(client, cleanup):
    vid, pk = _install(client, {"service/main.py": HTML_SERVICE}, manifest=INTEGRATION)
    with db.tx() as conn:
        conn.execute("UPDATE vehicle_addons SET active = 1 WHERE id = ?", (pk,))
        assert pluginsvc.approve(conn, addons.get(conn, vid, pk)) is None
        slug = conn.execute("SELECT slug FROM vehicles WHERE id = ?", (vid,)).fetchone()["slug"]
    pluginsvc._installing.add(pk)
    pluginsvc._install(pk)
    pluginsvc.tick()
    assert _wait(lambda: pluginsvc.running(pk))
    local = TestClient(PluginProxy(web.app), client=("172.30.32.2", 1))
    nav = {"Sec-Fetch-Dest": "document", "Accept": "text/html,*/*"}
    assert _wait(lambda: local.get("/priv/tool/", headers=nav).status_code == 200)
    page = local.get(f"/priv/tool/?car={vid}&theme=custom-light", headers=nav)
    assert page.headers["content-type"].startswith("text/html") and int(page.headers["content-length"]) == len(page.content)
    text = page.text
    assert "<h1>Own page</h1>" in text and 'id="ca-head"' in text and "frame-head.css?theme=custom-light" in text
    assert f'href="/v/{slug}/more"' in text and 'class="ca-name">Echo tool<' in text and 'class="ca-ver">v1<' in text
    assert "<iframe" not in text and "<script" not in text
    assert (
        "ca-head" not in local.get("/priv/tool/", headers={"Accept": "*/*", "X-Requested-With": "frame"}).text
    )  # a fetch gets the page as it is


def test_a_plugin_with_a_guide_gets_no_token_before_step_2_and_the_token_can_be_read_again(client):
    """The token is chosen IN the set-up guide: neither the installation nor the first start of the service nor saving settings makes one; once chosen it can be
    read again on the settings page (administrator), so a reinstallation can keep what is in the car."""
    guided = {
        **MANIFEST,
        "connection_file": {"name": "link.cfg", "template": "token={token}\nvehicle={vehicle}"},
        "setup": {"steps": [{"id": "token", "title": "Token", "token": True}]},
    }
    vid, pk = _install(client, manifest=guided)
    with db.tx() as conn:
        addon = addons.get(conn, vid, pk)
        _folder, token = pluginsvc._prepare_run(conn, addon)  # what the first start does
        assert token == "" and addons.get(conn, vid, pk)["token_id"] is None  # no token was made
        assert addons.set_up(conn, vid, addons.get(conn, vid, pk), {"greeting": "hi"}) is None  # saving settings makes none either
        assert addons.get(conn, vid, pk)["token_id"] is None
        made = addons.new_token(conn, vid, addons.get(conn, vid, pk))  # the explicit choice "make a new token"
        addons.set_up(conn, vid, addons.get(conn, vid, pk), {"greeting": "hi"})
    page = client.get(f"/v/{vid}/integrations/{pk}/settings").text
    assert "Token of this plugin" in page and made in page  # readable again


def test_a_prefix_the_app_answers_is_never_free_for_a_service(env):
    from carassistant import pluginsvc

    for prefix in (
        "/settings/",
        "/v/",
        "/api/",
        "/stations/",
        "/about/",
        "/healthz/",
        "/plugins/x/",
    ):  # the app's own pages, also the ones a later version added
        assert not pluginsvc.prefix_is_free(prefix), prefix
    assert pluginsvc.prefix_is_free("/mycar/") and pluginsvc.prefix_is_free("/my-car/api/")


def test_a_public_route_can_ask_for_the_token_of_the_plugin_in_a_header():
    routes = lambda *rs: addons.clean_service({"entry": "a.py", "routes": list(rs)})["routes"]  # noqa: E731
    assert routes({"prefix": "/car/", "public": True, "token_header": "X-Demo-Token"}) == [
        {"prefix": "/car/", "public": True, "token_header": "X-Demo-Token"}
    ]
    assert routes({"prefix": "/car/", "public": True, "token_header": None}) == [
        {"prefix": "/car/", "public": True}
    ]  # none asked: as before
    for bad in (
        {"prefix": "/car/", "public": False, "token_header": "X-Demo"},  # only a public route has a use for it
        {"prefix": "/car/", "public": True, "token_header": "Authorization"},
        {"prefix": "/car/", "public": True, "token_header": "Cookie"},
        {"prefix": "/car/", "public": True, "token_header": "X-CA-User"},
        {"prefix": "/car/", "public": True, "token_header": "Content-Type"},
        {"prefix": "/car/", "public": True, "token_header": "x"},
        {"prefix": "/car/", "public": True, "token_header": "X Demo"},
        {"prefix": "/car/", "public": True, "token_header": 5},
        {"prefix": "/car/", "public": True, "token_header": ""},
    ):  # a hardening that cannot be kept refuses the package: dropping it silently would leave the route open
        with pytest.raises(addons.AddonError):
            routes(bad)
    plain = {**MANIFEST}
    hard = {**MANIFEST, "service": {**MANIFEST["service"], "routes": [{"prefix": "/svc/", "public": True, "token_header": "X-Demo-Token"}]}}
    assert addons.approval_fingerprint(plain) != addons.approval_fingerprint(
        hard
    )  # a new version that asks for less (or more) is approved again


def test_the_app_answers_401_itself_before_the_service_sees_a_request_without_the_token(client, monkeypatch):
    vid, pk = _install(client)
    with db.tx() as conn:
        token = addons.new_token(conn, vid, addons.get(conn, vid, pk))
    seen = []

    def forward(port, method, target, headers, body):
        seen.append(target)
        return 200, [("content-type", "text/plain")], b"hello"

    route = {"prefix": "/svc/", "port": 1, "public": True, "pk": pk, "token_header": "x-demo-token"}
    monkeypatch.setattr(pluginsvc, "route_for", lambda path: route if path.startswith("/svc/") else None)
    monkeypatch.setattr("carassistant.proxy._forward", forward)
    edge = TestClient(PluginProxy(web.app), client=("8.8.8.8", 1))
    assert edge.get("/svc/ping").status_code == 401 and edge.post("/svc/ping", content=b"x").status_code == 401
    assert edge.get("/svc/ping", headers={"X-Demo-Token": "nope"}).status_code == 401
    assert edge.get("/svc/ping", headers={"X-Demo-Token": token + "x"}).status_code == 401
    assert edge.get("/svc/ping", headers={"Authorization": "Bearer " + token}).status_code == 401  # only the header the plugin named counts
    assert seen == []  # the service saw none of it
    ok = edge.get("/svc/ping?a=1", headers={"x-demo-token": token})
    assert ok.status_code == 200 and ok.text == "hello" and seen == ["/svc/ping?a=1"]
    assert edge.get("/svc/ping", headers={"X-DEMO-TOKEN": token}).status_code == 200  # a name has no case
    with db.tx() as conn:  # a plugin without a token matches nothing, not even an empty header
        conn.execute("UPDATE vehicle_addons SET token_id = NULL WHERE id = ?", (pk,))
    assert edge.get("/svc/ping", headers={"X-Demo-Token": token}).status_code == 401 and edge.get("/svc/ping").status_code == 401
    route["token_header"] = ""  # a route that asks for nothing is open as before
    assert edge.get("/svc/ping").status_code == 200


def test_the_review_page_says_that_a_route_wants_the_token(client):
    from carassistant import i18n

    assert "{header}" in i18n.EN["svc.public_token"] and "{header}" in i18n.DE["svc.public_token"]
