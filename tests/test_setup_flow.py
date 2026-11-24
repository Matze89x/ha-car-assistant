"""The free set-up flow (``setup.flow``): steps of different types in the order the plugin wants, a check by the plugin's own service, a file the service makes."""

import json

from tests.test_web import create_vehicle, slug

from carassistant import addons, db, pluginsvc

SERVICE = {
    "entry": "service/main.py",
    "python": ">=3.9",
    "requirements": [],
    "routes": [{"prefix": "/svc/", "public": True}, {"prefix": "/priv/", "public": False}],
}
PAGES = [{"id": "docs", "kind": "frame", "title": "Documentation", "route": "/priv/docs/"}]
SETTINGS = [
    {"key": "user", "label": "User name", "type": "text"},
    {"key": "password", "label": "Password", "type": "password"},
    {"key": "status", "label": "Status", "type": "value"},
]
FLOW = [
    {"id": "intro", "type": "text", "title": "Welcome", "text": "Log in with your **account**."},
    {"id": "login", "type": "check", "action": "/priv/login", "settings": ["user", "password"], "label": "Check the login"},
    {"id": "needs", "type": "requirements", "filled": ["user"]},
    {"id": "pack", "type": "download", "action": "/priv/zip", "label": "Create the ZIP"},
    {"id": "docs", "type": "page", "page": "docs"},
]


def manifest(flow=None, **extra):
    base = {
        "id": "flow-demo",
        "kind": "plugin",
        "name": "Flow demo",
        "version": "1",
        "settings": SETTINGS,
        "service": SERVICE,
        "pages": PAGES,
        "setup": {"title": "Connect the account", "flow": flow if flow is not None else FLOW},
    }
    return {**base, **extra}


def test_flow_steps_are_typed_and_a_step_that_does_not_fit_its_type_is_dropped():
    keys = {"user", "password", "status"}
    got = addons.clean_flow(
        [
            {"id": "a", "type": "text", "text": "Hello"},
            {"id": "b", "type": "form", "settings": ["user", "nothing"]},
            {"id": "c", "type": "form"},  # a form without a field
            {"id": "d", "type": "check", "action": "/priv/x"},
            {"id": "e", "type": "check", "action": "/svc/x"},  # a public route
            {"id": "f", "type": "download", "action": "/priv/../x"},
            {"id": "g", "type": "page", "page": "docs"},
            {"id": "h", "type": "page", "page": "nothing"},
            {"id": "i", "type": "requirements", "requires": ["external_https", "bogus"], "filled": ["user", "zzz"]},
            {"id": "j", "type": "requirements"},  # waits for nothing
            {"id": "k", "type": "magic"},
            {"id": "a", "type": "text"},  # twice
            {"id": "Bad Id", "type": "text"},
            "nonsense",
        ],
        [],
        False,
        keys,
        {"docs"},
        SERVICE,
    )
    assert [s["id"] for s in got] == ["a", "b", "d", "g", "i"]
    assert got[1]["settings"] == ["user"] and got[2]["action"] == "/priv/x" and got[3]["page"] == "docs"
    assert got[4]["requires"] == ["external_https"] and got[4]["filled"] == ["user"]
    assert (
        addons.clean_flow("nonsense", [], False, keys, set(), None) == []
        and len(addons.clean_flow([{"id": f"s{i}", "type": "text"} for i in range(30)], [], False, keys, set(), None)) == addons.MAX_FLOW
    )


def test_a_setup_may_have_only_a_flow_or_the_old_steps_or_both():
    only_flow = addons.parse_package(json.dumps(manifest()).encode())["setup"]
    assert [s["id"] for s in only_flow["flow"]] == ["intro", "login", "needs", "pack", "docs"] and only_flow["steps"] == []
    old = addons.parse_package(json.dumps({**manifest(), "setup": {"steps": [{"id": "token", "token": True}]}}).encode())["setup"]
    assert "flow" not in old and old["steps"][0]["id"] == "token"  # the three fixed steps stay for a package without a flow
    nothing = addons.parse_package(json.dumps({**manifest(), "setup": {"flow": [{"id": "x", "type": "magic"}]}}).encode())
    assert "setup" not in nothing


def _install(client, **extra):
    vid = create_vehicle(client)
    with db.tx() as conn:
        source = conn.execute("SELECT id FROM sources LIMIT 1").fetchone()["id"]
        pk = addons.add(conn, vid, addons.parse_package(json.dumps(manifest(**extra)).encode()), source, "0" * 64)
        conn.execute("UPDATE vehicle_addons SET active = 1 WHERE id = ?", (pk,))
    return vid, pk


def _stored(pk):
    with db.tx() as conn:
        row = conn.execute("SELECT status, settings FROM vehicle_addons WHERE id = ?", (pk,)).fetchone()
    return row["status"], json.loads(row["settings"] or "{}")


def test_the_flow_goes_through_its_steps_and_a_wrong_login_stores_nothing(client, monkeypatch):
    vid, pk = _install(client)
    monkeypatch.setattr(pluginsvc, "approved", lambda addon: True)
    monkeypatch.setattr(pluginsvc, "ready", lambda pk_: True)
    monkeypatch.setattr(pluginsvc, "restart", lambda pk_: None)
    base = f"/v/{slug(vid)}/integrations/{pk}/guide"
    first = client.get(base).text
    assert "Welcome" in first and "<b>account</b>" in first and "Connect the account" in first and "Set-up" not in first.split("<h2>")[0]
    assert client.get(base + "?step=2").text.count('name="password"') == 1  # the second step shows the fields of the check
    asked = []

    def ask(pk_, path, payload, vehicle_id, user="ha", timeout=10.0):
        asked.append((path, payload))
        return False, "Wrong password.", {}

    monkeypatch.setattr(pluginsvc, "ask", ask)
    bad = client.post(base + "/flow", data={"step": "2", "do": "check", "user": "max", "password": "nope"})
    assert bad.status_code == 422 and "Wrong password." in bad.text and 'class="addon-status err"' in bad.text
    assert 'value="max"' in bad.text  # what was typed stays in the field
    assert _stored(pk) == ("uploaded", {})  # nothing wrong was stored
    assert asked[0][0] == "/priv/login" and asked[0][1]["values"] == {"user": "max", "password": "nope"} and asked[0][1]["step"] == "login"

    def ask_ok(pk_, path, payload, vehicle_id, user="ha", timeout=10.0):
        return True, "Logged in as Max.", {"ok": True, "settings": {"status": "Connected"}}

    monkeypatch.setattr(pluginsvc, "ask", ask_ok)
    good = client.post(base + "/flow", data={"step": "2", "do": "check", "user": "max", "password": "right"})
    assert (
        good.status_code == 200 and "Logged in as Max." in good.text and 'class="addon-status ok"' in good.text
    )  # on to the next step with the plugin's words
    status, values = _stored(pk)
    assert status == "uploaded" and values["user"] == "max" and values["status"] == "Connected"  # the service wrote its own `value` setting
    assert "right" not in json.dumps(values)  # the password is sealed at rest


def test_a_step_of_requirements_stops_everything_behind_it_until_it_is_met(client, monkeypatch):
    vid, pk = _install(client)
    monkeypatch.setattr(pluginsvc, "approved", lambda addon: True)
    monkeypatch.setattr(pluginsvc, "ready", lambda pk_: True)
    base = f"/v/{slug(vid)}/integrations/{pk}/guide"
    page = client.get(base + "?step=4").text  # the step asked for is behind the requirements: the page stops at the requirements
    assert "Not filled in yet." in page and "User name" in page and '<button class="primary" disabled' in page
    assert client.post(base + "/flow", data={"step": "3", "do": "next"}).status_code == 409


def test_a_service_can_make_the_file_of_a_step_and_the_name_is_made_safe(client, monkeypatch):
    vid, pk = _install(client)
    monkeypatch.setattr(pluginsvc, "approved", lambda addon: True)
    monkeypatch.setattr(pluginsvc, "ready", lambda pk_: True)
    monkeypatch.setattr(pluginsvc, "restart", lambda pk_: None)
    with db.tx() as conn:
        conn.execute("UPDATE vehicle_addons SET settings = ? WHERE id = ?", (json.dumps({"user": "max"}), pk))
    base = f"/v/{slug(vid)}/integrations/{pk}/guide/flow"
    seen = []

    def fetch(pk_, path, payload, vehicle_id, user="ha", timeout=30.0):
        seen.append((path, payload["step"], user))
        return (
            True,
            "",
            {"content-type": "application/zip; charset=x", "content-disposition": 'attachment; filename="../my pack?.zip"'},
            b"PK\x03\x04zip",
        )

    monkeypatch.setattr(pluginsvc, "fetch", fetch)
    r = client.post(base, data={"step": "4", "do": "make"})
    assert r.status_code == 200 and r.content == b"PK\x03\x04zip" and r.headers["content-type"] == "application/zip"
    assert r.headers["content-disposition"] == 'attachment; filename="my_pack_.zip"' and r.headers["x-content-type-options"] == "nosniff"
    assert seen == [("/priv/zip", "pack", "ha")] or seen[0][:2] == ("/priv/zip", "pack")
    monkeypatch.setattr(pluginsvc, "fetch", lambda *a, **k: (True, "", {"content-type": "text/html"}, b"<script>"))
    assert (
        client.post(base, data={"step": "4", "do": "make"}).headers["content-type"] == "application/octet-stream"
    )  # never served as a page
    monkeypatch.setattr(pluginsvc, "fetch", lambda *a, **k: (False, "no answer", {}, b""))
    assert "does not answer" in client.post(base, data={"step": "4", "do": "make"}).text
    monkeypatch.setattr(pluginsvc, "approved", lambda addon: False)
    assert "approved" in client.post(base, data={"step": "4", "do": "make"}).text  # a service that is not approved is never asked


def test_the_last_step_marks_the_plugin_as_set_up(client, monkeypatch):
    vid, pk = _install(client)
    monkeypatch.setattr(pluginsvc, "approved", lambda addon: True)
    monkeypatch.setattr(pluginsvc, "ready", lambda pk_: True)
    monkeypatch.setattr(pluginsvc, "restart", lambda pk_: None)
    monkeypatch.setattr(pluginsvc, "write_token", lambda addon, token: None)
    r = client.post(f"/v/{slug(vid)}/integrations/{pk}/guide/flow", data={"step": "5", "do": "finish"})
    assert r.status_code in (200, 303)
    assert _stored(pk)[0] == "configured"
    tile = client.get(f"/v/{slug(vid)}/plugins").text
    assert "/guide" not in tile.split('class="addon-bar')[1].split("</div>")[0]  # no "Set up" button any more


def test_every_plugin_that_is_not_set_up_yet_has_a_set_up_button_on_its_tile(client):
    from tests.test_addons import MANIFEST, upload

    vid = create_vehicle(client)
    assert upload(client, vid, json.dumps(MANIFEST).encode()).status_code == 303  # a plugin without a guide
    with db.tx() as conn:
        pk = addons.list_for(conn, vid)[0]["id"]
    tile = client.get(f"/v/{slug(vid)}/plugins").text
    bar = tile.split('class="addon-bar')[1].split("</div>")[0]
    assert (
        f"/integrations/{pk}/settings" in bar and ">Set up<" in bar and "primary" in bar
    )  # it leads to the page that sets it up and makes its token
    client.post(f"/v/{slug(vid)}/integrations/{pk}/setup", data={"note": "x", "secret": "y"})
    bar = client.get(f"/v/{slug(vid)}/plugins").text.split('class="addon-bar')[1].split("</div>")[0]
    assert ">Set up<" not in bar  # done


def test_the_plugin_checker_names_buttons_and_steps_the_app_would_drop(tmp_path):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    import check_plugin

    bad = manifest(flow=[{"id": "ok", "type": "text"}, {"id": "gone", "type": "check", "action": "/svc/public"}])
    bad["buttons"] = [{"id": "docs", "label": "Docs", "page": "docs"}, {"id": "lost", "label": "Lost", "action": "/svc/public"}]
    folder = tmp_path / "flow-demo"
    folder.mkdir()
    (folder / "plugin.json").write_text(json.dumps(bad))
    _errors, notes = check_plugin.check(folder / "plugin.json")
    text = "\n".join(notes)
    assert "Buttons dropped: lost" in text and "Set-up steps dropped: gone" in text
    good = manifest()
    good["buttons"] = [{"id": "docs", "label": "Docs", "page": "docs"}]
    (folder / "plugin.json").write_text(json.dumps(good))
    assert not [n for n in check_plugin.check(folder / "plugin.json")[1] if "dropped" in n]


REAL_SERVICE = """
import io, json, os, zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer


class H(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        data = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/priv/login":
            v = data.get("values", {})
            ok = v.get("user") == "max" and v.get("password") == "right"
            out = json.dumps({"ok": True, "message": "Logged in as Max.", "settings": {"status": "Connected"}} if ok else {"ok": False, "message": "Wrong password."}).encode()
            self.send_response(200 if ok else 401)
            self.send_header("Content-Type", "application/json")
        else:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                z.writestr("who.txt", str(data["settings"].get("user")) + "|" + str(data["settings"].get("status")) + "|" + self.headers.get("X-CA-Vehicle", ""))
            out = buf.getvalue()
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", 'attachment; filename="install.zip"')
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


HTTPServer(("127.0.0.1", int(os.environ["CA_PORT"])), H).serve_forever()
"""


def test_a_real_service_checks_the_login_and_makes_the_zip_after_its_own_restart(client, monkeypatch):
    import io
    import zipfile

    from tests import test_pluginsvc as ps

    vid, pk = ps._install(client, {"service/main.py": REAL_SERVICE}, manifest(id="flow-real"))
    restart = pluginsvc.restart

    def restart_and_start(pk_):  # in the app a thread brings the service back; here the test does it
        restart(pk_)
        pluginsvc.tick()

    monkeypatch.setattr(pluginsvc, "restart", restart_and_start)
    base = f"/v/{vid}/integrations/{pk}/guide/flow"
    try:
        with db.tx() as conn:
            conn.execute("UPDATE vehicle_addons SET active = 1 WHERE id = ?", (pk,))
            assert pluginsvc.approve(conn, addons.get(conn, vid, pk)) is None
        pluginsvc._installing.add(pk)
        pluginsvc._install(pk)
        pluginsvc.tick()
        assert ps._wait(lambda: pluginsvc.running(pk))
        bad = client.post(base, data={"step": "2", "do": "check", "user": "max", "password": "nope"})
        assert bad.status_code == 422 and "Wrong password." in bad.text and _stored(pk)[1] == {}  # the real answer, nothing stored
        good = client.post(base, data={"step": "2", "do": "check", "user": "max", "password": "right"})
        assert good.status_code == 200 and "Logged in as Max." in good.text
        assert _stored(pk)[1]["status"] == "Connected"  # the service wrote its own value
        # the save restarted the service; the next step waits for it and then the service builds the file from what it was sent
        made = client.post(base, data={"step": "4", "do": "make"})
        assert made.status_code == 200 and made.headers["content-type"] == "application/zip"
        assert 'filename="install.zip"' in made.headers["content-disposition"]
        with zipfile.ZipFile(io.BytesIO(made.content)) as z:
            assert z.read("who.txt").decode() == f"max|Connected|{vid}"
    finally:
        pluginsvc.stop_all()
        pluginsvc._stop.clear()
