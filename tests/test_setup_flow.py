"""The free set-up flow (``setup.flow``): steps of different types in the order the plugin wants, a check by the plugin's own service, a file the service makes."""

import json
import re

from tests.test_web import create_vehicle, slug

from carassistant import addons, db, pluginsvc, setupflow_web

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
    assert "Welcome" in first and "<b>account</b>" in first and "Connect the account" in first and "Set up" not in first.split("<h2>")[0]
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


def test_one_time_inputs_of_a_check_are_cleaned():
    flow = addons.clean_flow(
        [
            {
                "id": "login",
                "type": "check",
                "action": "/priv/login",
                "settings": ["user"],
                "inputs": [
                    {
                        "key": "code",
                        "label": "Code",
                        "type": "text",
                        "ask": True,
                        "default": "123",
                        "show_if": {"key": "user", "equals": "x"},
                        "service_writable": True,
                    },
                    {"key": "pin", "label": "PIN", "type": "password", "ask": "yes"},  # ``ask`` is a yes / no, not a word
                    {"key": "user", "label": "Taken", "type": "text"},  # the key of a setting
                    {"key": "notes", "label": "Notes", "type": "textarea"},  # a type a one-time input cannot have
                    {"key": "code", "label": "Twice", "type": "text"},
                    "nonsense",
                ],
            },
            {"id": "t", "type": "text", "inputs": [{"key": "x", "label": "X", "type": "text"}]},
        ],
        [],
        False,
        {"user", "password"},
        set(),
        SERVICE,
    )
    assert [f["key"] for f in flow[0]["inputs"]] == ["code", "pin"]
    code, pin = flow[0]["inputs"]
    assert code["ask"] is True and not {"default", "show_if", "service_writable"} & set(code)  # empty every time, always on its own step
    assert "ask" not in pin
    assert "inputs" not in flow[1]  # only a check step has them
    assert [f["key"] for f in addons.input_fields(flow[0])] == ["pin"] and [f["key"] for f in addons.input_fields(flow[0], {"code"})] == [
        "code",
        "pin",
    ]


ASK_FLOW = [
    {
        "id": "login",
        "type": "check",
        "action": "/priv/login",
        "settings": ["user", "password"],
        "label": "Log in",
        "inputs": [
            {"key": "code", "label": "Code from the SMS", "type": "text", "ask": True, "required": True},
            {"key": "pin", "label": "PIN", "type": "password"},
        ],
    },
    {"id": "done", "type": "text", "title": "Done", "text": "You are logged in."},
]


def test_a_service_can_ask_for_a_code_and_what_is_typed_for_it_is_never_stored(client, monkeypatch):
    vid, pk = _install(client, flow=ASK_FLOW)
    monkeypatch.setattr(pluginsvc, "approved", lambda addon: True)
    monkeypatch.setattr(pluginsvc, "ready", lambda pk_: True)
    monkeypatch.setattr(pluginsvc, "restart", lambda pk_: None)
    base = f"/v/{slug(vid)}/integrations/{pk}/guide"
    page = client.get(base).text
    assert 'name="pin"' in page and 'name="code"' not in page  # a field marked ``ask`` is not there before the service asks
    sent = []
    answers = iter(
        [
            (False, "A code was sent by SMS.", {"ok": False, "ask": ["code", "user", "nothing"], "message": "A code was sent by SMS."}),
            (False, "Wrong code.", {"ok": False, "message": "Wrong code."}),
            (True, "Logged in as Max.", {"ok": True}),
        ]
    )

    def ask(pk_, path, payload, vehicle_id, user="ha", timeout=10.0):
        sent.append(payload)
        return next(answers, (False, "Wrong code.", {"ok": False}))

    monkeypatch.setattr(pluginsvc, "ask", ask)

    first = client.post(base + "/flow", data={"step": "1", "do": "check", "user": "max", "password": "s3cret", "pin": "4711"})
    assert first.status_code == 200 and "A code was sent by SMS." in first.text  # a question, not an error
    assert 'class="addon-status err"' not in first.text
    assert 'name="code"' in first.text and 'name="asked" value="code"' in first.text  # only what the step declared with ``ask``
    assert sent[0]["values"] == {"user": "max", "password": "s3cret", "pin": "4711"}  # the first call knew nothing of a code
    assert _stored(pk) == ("uploaded", {})  # nothing is stored before the check passes
    carry = re.search(r'name="carry" value="([^"]+)"', first.text).group(1)

    wrong = client.post(
        base + "/flow",
        data={"step": "1", "do": "check", "user": "max", "password": "", "pin": "4711", "code": "000000", "asked": "code", "carry": carry},
    )
    assert wrong.status_code == 422 and "Wrong code." in wrong.text and 'name="code"' in wrong.text  # the field stays for another try
    assert (
        sent[1]["values"]["password"] == "s3cret" and sent[1]["values"]["code"] == "000000"
    )  # the password came from memory, not from the person
    carry = re.search(r'name="carry" value="([^"]+)"', wrong.text).group(1)

    right = client.post(
        base + "/flow",
        data={"step": "1", "do": "check", "user": "max", "password": "", "pin": "4711", "code": "123456", "asked": "code", "carry": carry},
    )
    assert right.status_code == 200 and "You are logged in." in right.text and "Logged in as Max." in right.text
    assert sent[2]["values"] == {"user": "max", "password": "s3cret", "pin": "4711", "code": "123456"}
    assert "code" not in sent[2]["settings"] and "pin" not in sent[2]["settings"]  # the settings the service reads are the settings
    _status, values = _stored(pk)
    assert values["user"] == "max" and not {"code", "pin"} & set(values)
    with db.tx() as conn:
        dump = " ".join(
            str(tuple(r)) for table in ("vehicle_addons", "vehicle_logs", "vehicle_traffic") for r in conn.execute(f"SELECT * FROM {table}")
        )
    assert not {"123456", "000000", "4711", "s3cret"} & set(dump.replace("'", " ").replace(",", " ").split())  # never written anywhere
    assert carry not in setupflow_web._carry  # the memory of the password is gone after the pass
    # a code typed after the memory ran out cannot bring the password back
    late = client.post(
        base + "/flow", data={"step": "1", "do": "check", "user": "max", "password": "", "code": "1", "asked": "code", "carry": carry}
    )
    assert late.status_code in (200, 422) and "s3cret" not in late.text


def test_the_check_tool_names_a_one_time_input_that_was_dropped(tmp_path):
    import check_plugin

    folder = tmp_path / "plugins" / "flow-demo"
    (folder / "service").mkdir(parents=True)
    (folder / "service" / "main.py").write_text("print(1)", encoding="utf-8")
    flow = [
        {
            "id": "login",
            "type": "check",
            "action": "/priv/login",
            "settings": ["user"],
            "inputs": [{"key": "code", "label": "Code", "type": "text", "ask": True}, {"key": "user", "label": "Taken", "type": "text"}],
        },
        {"id": "info", "type": "text", "inputs": [{"key": "x", "label": "X", "type": "text"}]},
    ]
    (folder / "plugin.json").write_text(json.dumps(manifest(flow=flow, description="d", icon="wrench")), encoding="utf-8")
    errors, notes = check_plugin.check(folder)
    text = " ".join(notes)
    assert "the one-time input(s) user were dropped" in text and "Step 'info': 'inputs' belong to a step of type check" in text
    assert "code" not in text.split("were dropped")[0]  # the good input is not named
    assert not [e for e in errors if "inputs" in e]
