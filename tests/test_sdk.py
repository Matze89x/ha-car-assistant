"""The helper library of plugin authors (docs/examples/sdk/carassistant_sdk.py): one file, standard library only - what it promises, tested against small servers."""

import gzip
import http.server
import importlib.util
import json
import threading
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
SDK = HERE / "docs" / "examples" / "sdk" / "carassistant_sdk.py"


@pytest.fixture()
def ca(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("carassistant_sdk_under_test", SDK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("CA_DATA_DIR", str(tmp_path))
    module._settings_seen.update(stamp=None, data={})
    module._routes.clear()
    return module


class Server:
    """A web server in a thread: answers what ``script`` says and notes every request."""

    def __init__(self, script):
        self.requests: list[dict] = []
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def _go(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                if self.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                outer.requests.append({"method": self.command, "path": self.path, "headers": dict(self.headers), "body": body})
                status, headers, payload = script(len(outer.requests), self)
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            do_GET = do_POST = do_PUT = _go

            def log_message(self, *a):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@pytest.fixture()
def server():
    made = []

    def make(script):
        made.append(Server(script))
        return made[-1]

    yield make
    for s in made:
        s.close()


def _json(payload: dict, status: int = 200):
    return status, {"Content-Type": "application/json"}, json.dumps(payload).encode()


def test_settings_are_read_when_they_change(ca, tmp_path):
    assert ca.settings() == {}
    (tmp_path / "settings.json").write_text(json.dumps({"user": "max", "interval": 30}))
    assert ca.settings() == {"user": "max", "interval": 30}
    (tmp_path / "settings.json").write_text(json.dumps({"user": "eva"}))
    import os

    os.utime(tmp_path / "settings.json", ns=(10**18, 10**18))  # (a second write within the same moment)
    assert ca.settings() == {"user": "eva"}


def test_state_is_kept_in_a_file_and_survives_a_new_start(ca, tmp_path):
    state = ca.State()
    state.set("token", "abc")
    state.update(seen=[1, 2], token=None)
    assert state.get("seen") == [1, 2] and state.get("token") is None and state.get("nothing", 7) == 7
    again = ca.State()
    assert again.all() == {"seen": [1, 2]}
    assert oct((tmp_path / "state.json").stat().st_mode & 0o777) == oct(0o600)  # not for others on the machine


def test_the_http_client_sends_json_keeps_cookies_and_raises_for_errors(ca, server):
    def script(n, handler):
        if handler.path.startswith("/login"):
            return 200, {"Set-Cookie": "session=s1; Path=/", "Content-Type": "application/json"}, b'{"ok": true}'
        if handler.path.startswith("/car"):
            return _json({"cookie": handler.headers.get("Cookie"), "x": handler.headers.get("X-Test")})
        return 404, {}, b"no"

    web = server(script)
    http = ca.Http(headers={"X-Test": "1"})
    assert http.post(web.url + "/login", json={"user": "max"}).json() == {"ok": True}
    assert json.loads(web.requests[0]["body"]) == {"user": "max"} and web.requests[0]["headers"]["Content-Type"] == "application/json"
    car = http.get(web.url + "/car", params={"a": "1"}).json()
    assert car == {"cookie": "session=s1", "x": "1"} and web.requests[1]["path"] == "/car?a=1"  # the session cookie came along
    with pytest.raises(ca.HttpError) as error:
        http.get(web.url + "/missing")
    assert error.value.status == 404 and error.value.text == "no"
    assert http.post(web.url + "/car", data={"k": "v w"}).ok and web.requests[-1]["body"] == b"k=v+w"


def test_a_temporary_problem_is_tried_again_but_a_refusal_is_not(ca, server, monkeypatch):
    monkeypatch.setattr(ca.time, "sleep", lambda s: None)

    def script(n, handler):
        if handler.path == "/flaky":
            return (503, {}, b"later") if n < 3 else _json({"n": n})
        return 401, {}, b"no"

    web = server(script)
    http = ca.Http(retries=2)
    assert http.get(web.url + "/flaky").json() == {"n": 3}  # two 503, then the answer
    before = len(web.requests)
    with pytest.raises(ca.HttpError):
        http.get(web.url + "/private")
    assert len(web.requests) == before + 1  # a 401 is no temporary problem: one request only


def test_redirects_can_be_looked_at_instead_of_followed(ca, server):
    web = server(lambda n, h: (302, {"Location": "/elsewhere?code=abc"}, b"") if h.path == "/start" else _json({"at": h.path}))
    http = ca.Http()
    seen = http.get(web.url + "/start", follow=False)
    assert seen.status == 302 and seen.headers["location"] == "/elsewhere?code=abc"
    assert http.get(web.url + "/start").json() == {"at": "/elsewhere?code=abc"}


def test_the_api_client_speaks_the_plugin_api(ca, server):
    def script(n, handler):
        if handler.path.endswith("/control"):
            return _json({"ok": True, "control": {"debug": True, "interval_s": 60}})
        if handler.path.endswith("/refuel"):
            return _json({"error": "invalid_value", "message": "amount must be a number"}, 422)
        return _json({"ok": True, "result": {}, "control": {"debug": False, "interval_s": 300}})

    app = server(script)
    api = ca.Api(url=app.url, token="ca_token", vehicle="7")
    api.send({"odometer_km": 1}, fuel_level_pct=50)
    first = app.requests[0]
    assert (
        first["method"] == "POST" and first["path"] == "/api/v1/vehicles/7/data" and first["headers"]["Authorization"] == "Bearer ca_token"
    )
    assert (
        json.loads(first["body"]) == {"odometer_km": 1, "fuel_level_pct": 50} and api.interval() == 300 and api.debug() is False
    )  # from the answer
    api.track([{"lat": 1, "lon": 2}])
    api.events([{"type": "x"}])
    api.signals({"a.b": 1}, c=2)
    api.module_rows("coding", "units", [{"values": {"addr": "01"}}], delete=[3])
    assert [r["path"].rsplit("/", 1)[-1] for r in app.requests[1:]] == ["track", "events", "signals", "units"]
    assert json.loads(app.requests[3]["body"]) == {"signals": {"a.b": 1, "c": 2}}
    assert api.control() == {"debug": True, "interval_s": 60} and api.interval() == 60
    api.log("info", "a line")  # debug is on: sent
    assert app.requests[-1]["path"].endswith("/logs") and json.loads(app.requests[-1]["body"]) == {
        "lines": [{"level": "info", "message": "a line"}]
    }
    with pytest.raises(ca.ApiError) as error:
        api.refuel(amount="a lot")
    assert (error.value.status, error.value.error, error.value.message) == (422, "invalid_value", "amount must be a number")


def test_a_big_delivery_goes_gzipped_and_a_lost_connection_is_an_error_not_a_crash(ca, server):
    app = server(lambda n, h: _json({"ok": True}))
    api = ca.Api(url=app.url, token="t", vehicle="1")
    api.signals({f"n.{i}": "x" * 40 for i in range(200)})
    assert app.requests[0]["headers"].get("Content-Encoding") == "gzip" and len(json.loads(app.requests[0]["body"])["signals"]) == 200
    gone = ca.Api(url="http://127.0.0.1:1", token="t", vehicle="1", timeout=1)
    with pytest.raises(ca.ApiError) as error:
        gone.send(odometer_km=1)
    assert error.value.status == 0 and error.value.error == "unreachable"
    api.log("info", "debug is unknown here: nothing is sent")
    assert len(app.requests) == 1


def test_routes_answer_json_text_files_and_errors(ca):
    @ca.route("POST", "/svc/check")
    def check(request):
        return {"ok": True, "got": request.values, "who": request.user, "car": request.vehicle}

    @ca.route("GET", "/svc/files/")
    def files(request):
        return ca.Reply(200, b"PK", "application/zip", {"Content-Disposition": "attachment; filename=x.zip"})

    @ca.route("GET", "/svc/page")
    def page(request):
        return "<html><body>hello</body></html>"

    @ca.route("GET", "/svc/teapot")
    def teapot(request):
        return 418, {"ok": False, "message": "no coffee"}

    @ca.route("GET", "/svc/broken")
    def broken(request):
        raise RuntimeError("password was swordfish")

    server = ca.serve(0)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        http = ca.Http(retries=0)
        answer = http.post(base + "/svc/check", json={"values": {"user": "max"}}, headers={"X-CA-User": "ha", "X-CA-Vehicle": "3"}).json()
        assert answer == {"ok": True, "got": {"user": "max"}, "who": "ha", "car": "3"}
        zipped = http.get(base + "/svc/files/pack.zip")
        assert (
            zipped.body == b"PK"
            and zipped.headers["content-type"] == "application/zip"
            and "attachment" in zipped.headers["content-disposition"]
        )
        assert http.get(base + "/svc/page").text.startswith("<html>") and http.get(base + "/svc/page").headers["content-type"].startswith(
            "text/html"
        )
        with pytest.raises(ca.HttpError) as teapot:
            http.get(base + "/svc/teapot")
        assert teapot.value.status == 418
        with pytest.raises(ca.HttpError) as missing:
            http.get(base + "/svc/nothing")
        assert missing.value.status == 404
        with pytest.raises(ca.HttpError) as broken:
            http.get(base + "/svc/broken")
        assert broken.value.status == 500 and "swordfish" not in broken.value.text  # the person sees a plain sentence, not the inside
    finally:
        server.shutdown()


def test_run_keeps_polling_after_a_failure_and_stops_when_asked(ca, monkeypatch):
    calls = []
    monkeypatch.setattr(ca, "BACKOFF", (1, 1))
    ca.stop.clear()

    def poll():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("the web service had a hiccup")
        if len(calls) >= 3:
            ca.stop.set()

    waits = []
    real_wait = ca.stop.wait
    monkeypatch.setattr(ca.stop, "wait", lambda t: waits.append(t) or real_wait(0))
    ca.run(poll, every=5)
    assert len(calls) == 3 and waits[0] >= 4  # a failure did not end the service; the pause is the normal one (less the time the poll took)
    ca.stop.clear()


def test_the_answers_of_a_check_route_have_the_shape_the_set_up_flow_reads(ca):
    assert ca.passed() == {"ok": True}
    assert ca.passed("Logged in as Max.", status="connected") == {
        "ok": True,
        "message": "Logged in as Max.",
        "settings": {"status": "connected"},
    }
    assert ca.failed("Wrong password.") == {"ok": False, "message": "Wrong password."}
    assert ca.ask("code", message="A code was sent by SMS.") == {"ok": False, "ask": ["code"], "message": "A code was sent by SMS."}


def test_the_login_of_the_person_comes_as_a_header_and_a_refusal_as_an_error(ca, server):
    def script(n, handler):
        if "step=other" in handler.path:
            return _json({"error": "login_required", "message": "The person has to log in again."}, 409)
        return _json({"ok": True, "access_token": "AT9", "token_type": "Bearer", "scope": "read", "expires_at": None, "expires_in": 3000})

    app = server(script)
    api = ca.Api(url=app.url, token="t", vehicle="4")
    assert api.connection()["access_token"] == "AT9" and app.requests[-1]["path"] == "/api/v1/vehicles/4/connection"
    assert api.bearer(renew=True) == {"Authorization": "Bearer AT9"} and app.requests[-1]["path"].endswith("/connection?renew=1")
    with pytest.raises(ca.ApiError) as error:
        api.connection("other")
    assert (
        error.value.status == 409 and error.value.error == "login_required" and app.requests[-1]["path"].endswith("/connection?step=other")
    )
