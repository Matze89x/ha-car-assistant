"""carassistant_sdk - everything a Car Assistant plugin service needs, in ONE file (Python 3.9+, standard library only).

Copy this file next to your service's ``main.py`` (``tools/new_plugin.py`` does it for you). The add-on starts your service with these environment
variables (docs/plugins.md, "What the service gets"): ``CA_PORT``, ``CA_API_URL``, ``CA_API_TOKEN``, ``CA_VEHICLE_ID``, ``CA_DATA_DIR``.

    import carassistant_sdk as ca

    api = ca.Api()                                          # the Plugin API of Car Assistant (docs/api.md)

    def poll():                                             # called again and again: every `every` seconds
        cfg = ca.settings()                                 # what the person typed on the settings page
        data = ca.Http().get("https://api.example.com/car", headers={"Authorization": "Bearer " + cfg["token"]}).json()
        api.send(odometer_km=data["km"], fuel_level_pct=data["fuel"])

    @ca.route("POST", "/priv/check")                        # a step "Check the login" of the set-up flow (a route under a non-public prefix)
    def check(request):
        return {"ok": True, "message": "Logged in."}        # or {"ok": False, "message": "Wrong password."}

    ca.run(poll, every=60)

The answers of a check route: ``ca.passed("Logged in.")``, ``ca.failed("Wrong password.")`` and ``ca.ask("code", message="A code was sent by SMS.")`` (the step comes
back with a one-time input for the code).

Only what is described in docs/plugins.md and docs/api.md is used here - nothing in this file is magic, and the Plugin API stays the one door to the app.
"""

from __future__ import annotations

import contextlib
import gzip
import http.cookiejar
import http.server
import json
import os
import signal
import socketserver
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

__version__ = "1"

# ------------------------------------------------------------------ the environment of the service


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def data_dir() -> Path:
    """The only folder the service may write to (``CA_DATA_DIR``)."""
    return Path(_env("CA_DATA_DIR", "."))


def files_dir() -> Path | None:
    """The read-only folder with the files of the package, when the package asks for it (``"service": {"files": "read"}``)."""
    value = _env("CA_FILES_DIR")
    return Path(value) if value else None


_settings_seen: dict = {"stamp": None, "data": {}}


def settings() -> dict:
    """What the person set on the settings page of the plugin (``settings.json``), as typed values; also ``external_url`` and ``vehicle_vin``. A change of the
    settings restarts the service, so reading this again and again is cheap (the file is read again only when it changed)."""
    path = data_dir() / "settings.json"
    try:
        stamp = path.stat().st_mtime_ns
    except OSError:
        return {}
    if _settings_seen["stamp"] != stamp:
        try:
            _settings_seen["data"] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _settings_seen["data"] = {}
        _settings_seen["stamp"] = stamp
    return dict(_settings_seen["data"])


class State:
    """A small JSON file in the data folder: what the service has to remember - a session, a refresh token, the ids it has seen. Written as a whole and
    atomically, so a crash never leaves half a file."""

    def __init__(self, name: str = "state.json"):
        self.path = data_dir() / name
        self._lock = threading.Lock()
        self._data: dict | None = None

    def _load(self) -> dict:
        if self._data is None:
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._data = {}
        return self._data

    def get(self, key: str, default=None):
        with self._lock:
            return self._load().get(key, default)

    def set(self, key: str, value) -> None:
        self.update(**{key: value})

    def update(self, **values) -> None:
        """Set several keys at once (a value ``None`` removes its key)."""
        with self._lock:
            data = self._load()
            for key, value in values.items():
                if value is None:
                    data.pop(key, None)
                else:
                    data[key] = value
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            os.chmod(tmp, 0o600)
            tmp.replace(self.path)

    def all(self) -> dict:
        with self._lock:
            return dict(self._load())


def log(message: str, level: str = "info") -> None:
    """A line of output. The add-on keeps it for the plugin's log page while debug is on (and says nothing about the car in it): never print a password or a token."""
    print(f"[{level}] {message}", flush=True)


# ------------------------------------------------------------------ talking to web services


class HttpError(Exception):
    """A web service answered with an error status (after the retries)."""

    def __init__(self, status: int, body: bytes, url: str):
        super().__init__(f"{status} from {url}")
        self.status, self.body, self.url = status, body, url

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", "replace")


class Response:
    """An answer of a web service: ``status``, ``headers`` (lower-case names), ``body`` (bytes), ``text`` and ``json()``."""

    def __init__(self, status: int, headers: dict, body: bytes, url: str):
        self.status, self.headers, self.body, self.url = status, headers, body, url

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", "replace")

    def json(self):
        return json.loads(self.body or b"null")

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Http:
    """A small client for web services: JSON in and out, cookies kept (for a login with a session), timeouts, and a retry for what is only temporary
    (no connection, a 5xx answer). Status codes outside 2xx raise ``HttpError``; ``follow=False`` shows redirects instead of following them."""

    def __init__(self, headers: dict | None = None, timeout: float = 20.0, retries: int = 2, cookies: bool = True):
        self.headers = {"User-Agent": "carassistant-plugin", **(headers or {})}
        self.timeout, self.retries = timeout, retries
        self.jar = http.cookiejar.CookieJar() if cookies else None
        self._follow = self._build(True)
        self._stay = self._build(False)

    def _build(self, follow: bool):
        handlers: list = [] if follow else [_NoRedirect()]
        if self.jar is not None:
            handlers.append(urllib.request.HTTPCookieProcessor(self.jar))
        return urllib.request.build_opener(*handlers)

    def request(self, method: str, url: str, *, params=None, json=None, data=None, headers=None, timeout=None, follow=True) -> Response:
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
        head = {**self.headers, **(headers or {})}
        body = None
        if json is not None:
            body, head["Content-Type"] = globals()["json"].dumps(json).encode(), "application/json"
        elif isinstance(data, dict):
            body, head["Content-Type"] = urllib.parse.urlencode(data, doseq=True).encode(), "application/x-www-form-urlencoded"
        elif data is not None:
            body = bytes(data)
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            request = urllib.request.Request(url, data=body, headers=head, method=method.upper())  # noqa: S310 - an address the plugin chose
            try:
                with (self._follow if follow else self._stay).open(request, timeout=timeout or self.timeout) as answer:
                    return Response(answer.status, {k.lower(): v for k, v in answer.headers.items()}, answer.read(), answer.url)
            except urllib.error.HTTPError as exc:
                answer_body = exc.read()
                if exc.code < 500:
                    if not follow and 300 <= exc.code < 400:
                        return Response(exc.code, {k.lower(): v for k, v in exc.headers.items()}, answer_body, url)
                    raise HttpError(exc.code, answer_body, url) from exc
                last = HttpError(exc.code, answer_body, url)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last = exc
            if attempt < self.retries:
                time.sleep(0.5 * 2**attempt)
        if isinstance(last, HttpError):
            raise last
        raise HttpError(0, str(last).encode(), url) from last

    def get(self, url: str, **kw) -> Response:
        return self.request("GET", url, **kw)

    def post(self, url: str, **kw) -> Response:
        return self.request("POST", url, **kw)

    def put(self, url: str, **kw) -> Response:
        return self.request("PUT", url, **kw)

    def delete(self, url: str, **kw) -> Response:
        return self.request("DELETE", url, **kw)


# ------------------------------------------------------------------ the Plugin API of Car Assistant


class ApiError(Exception):
    """The Plugin API refused a request: ``status``, ``error`` (the code of docs/api.md, for example ``invalid_value``) and ``message``; status 0 =
    the app could not be reached."""

    def __init__(self, status: int, error: str, message: str):
        super().__init__(f"{status} {error}: {message}")
        self.status, self.error, self.message = status, error, message


class Api:
    """The Plugin API (docs/api.md) with the token and the car of this service. Every method returns the answer as a dict and raises ``ApiError``."""

    def __init__(self, url: str | None = None, token: str | None = None, vehicle: str | None = None, timeout: float = 15.0):
        self.url = (url or _env("CA_API_URL")).rstrip("/")
        self.token = token or _env("CA_API_TOKEN")
        self.vehicle = vehicle or _env("CA_VEHICLE_ID")
        self.timeout = timeout
        self._control: dict = {}

    def _call(self, method: str, path: str, body=None) -> dict:
        raw = None if body is None else json.dumps(body).encode()
        head = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json", "User-Agent": "carassistant-plugin"}
        if raw is not None and len(raw) > 2000:
            raw, head["Content-Encoding"] = gzip.compress(raw), "gzip"
        request = urllib.request.Request(f"{self.url}/api/v1/vehicles/{self.vehicle}{path}", data=raw, headers=head, method=method)  # noqa: S310 - the add-on's own address
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as answer:  # noqa: S310 - the add-on's own address
                result = json.loads(answer.read() or b"{}")
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read() or b"{}")
            except ValueError:
                detail = {}
            raise ApiError(exc.code, str(detail.get("error") or "error"), str(detail.get("message") or exc.reason)) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ApiError(0, "unreachable", str(exc)) from exc
        if isinstance(result, dict) and isinstance(result.get("control"), dict):
            self._control = result["control"]
        return result

    # what the car reports
    def send(self, data: dict | None = None, /, **fields) -> dict:
        """The values you know (docs/api.md, "Send data"): ``api.send(odometer_km=52340, doors={"trunk": True})``. Send on change, not every second."""
        return self._call("POST", "/data", {**(data or {}), **fields})

    def track(self, points: list[dict]) -> dict:
        """Positions of a drive: ``[{"ts": "2026-11-15T08:00:00Z", "lat": 52.5, "lon": 13.4, "speed_kmh": 30}, ...]`` (up to 500 per call)."""
        return self._call("POST", "/track", {"points": list(points)})

    def events(self, events: list[dict]) -> dict:
        """Things with a time and maybe a place: ``[{"type": "speed_sign", "text": "50", "value": 50}]``."""
        return self._call("POST", "/events", {"events": list(events)})

    def signals(self, values: dict | None = None, /, **more) -> dict:
        """Raw values that have no standard field: ``api.signals({"kombi.odo_km": 52340})`` (a value ``None`` removes it)."""
        return self._call("POST", "/signals", {"signals": {**(values or {}), **more}})

    def refuel(self, **fields) -> dict:
        """The car noticed that its tank or battery jumped: ``api.refuel(amount=41.5, odometer_km=52340, full_tank=True)``."""
        return self._call("POST", "/refuel", fields)

    def trip_summary(self, **fields) -> dict:
        return self._call("POST", "/trip-summary", fields)

    def module_rows(self, integration: str, page: str, rows: list[dict], delete: list[int] | None = None) -> dict:
        """Entries of an integration page (for example control units): ``rows=[{"values": {...}}, {"id": 5, "values": {...}}]``."""
        return self._call("POST", f"/modules/{integration}/{page}", {"rows": rows, **({"delete": delete} if delete else {})})

    # what the person set for the plugin
    def control(self) -> dict:
        """The switches of the dashboard: ``{"debug": False, "interval_s": 120}``."""
        self._control = self._call("GET", "/control").get("control") or {}
        return dict(self._control)

    def interval(self, default: int = 120) -> int:
        """How often the person would like the plugin to report (a request, not an order); known from the last answer."""
        return int(self._control.get("interval_s") or default)

    def debug(self) -> bool:
        return bool(self._control.get("debug"))

    def log(self, level: str, message: str) -> None:
        """A line for the plugin's log page - sent only while debug is on (the app refuses it otherwise)."""
        if self.debug():
            with contextlib.suppress(ApiError):
                self._call("POST", "/logs", {"lines": [{"level": level, "message": message[:500]}]})

    def plugin_settings(self) -> dict:
        return self._call("GET", "/plugin-settings").get("settings") or {}

    def set_plugin_settings(self, **values) -> dict:
        """Change the settings the service may write itself (``service_writable`` and ``value`` fields): a status, a name, a token it was given."""
        return self._call("PUT", "/plugin-settings", {"values": values})


# ------------------------------------------------------------------ the routes of the service


class Request:
    """What a route gets: ``method``, ``path``, ``query`` (first value of each name), ``headers`` (lower-case), ``body``; ``json()``; ``vehicle`` and ``user``
    are the identity headers the app adds (``X-CA-Vehicle``, ``X-CA-User``)."""

    def __init__(self, method: str, path: str, query: dict, headers: dict, body: bytes):
        self.method, self.path, self.query, self.headers, self.body = method, path, query, headers, body
        self.vehicle, self.user = headers.get("x-ca-vehicle", ""), headers.get("x-ca-user", "")

    def json(self):
        return json.loads(self.body or b"null")

    @property
    def values(self) -> dict:
        """The ``values`` of a request of the set-up flow (``check`` / ``download`` steps): what the person typed in that step."""
        body = self.json()
        return (body or {}).get("values") or {} if isinstance(body, dict) else {}


class Reply:
    """A full answer: ``Reply(200, body, "image/png", {"Content-Disposition": "attachment; filename=x.zip"})``."""

    def __init__(
        self, status: int = 200, body: bytes | str = b"", content_type: str = "application/octet-stream", headers: dict | None = None
    ):
        self.status, self.content_type, self.headers = status, content_type, headers or {}
        self.body = body.encode() if isinstance(body, str) else body


# ------------------------------------------------------------------ the answers of a check route (the set-up flow)


def passed(message: str = "", **settings) -> dict:
    """The answer of a ``check`` route when the login worked: ``return ca.passed("Logged in as Max.", status="connected")``. ``message`` is shown on the next
    step; the keyword arguments are settings the service may write itself (``value`` fields and ``service_writable``, docs/plugins.md)."""
    answer: dict = {"ok": True}
    if message:
        answer["message"] = message
    if settings:
        answer["settings"] = settings
    return answer


def failed(message: str) -> dict:
    """The answer when it did not work: the person stays on the step and reads ``message``. Never put a password or a token into it."""
    return {"ok": False, "message": message}


def ask(*keys: str, message: str = "") -> dict:
    """The answer when one more thing is needed to log in: the step comes back with these one-time ``inputs`` (the ones marked ``"ask": true``), and
    ``message`` says why: ``return ca.ask("code", message="A code was sent by SMS.")``. The next call of the route carries the code in ``request.values``."""
    return {"ok": False, "ask": list(keys), "message": message}


_routes: list[tuple[str, str, object]] = []


def route(method: str, path: str):
    """Register a function for ``method`` and ``path`` (a path that ends with ``/`` answers everything below it). The function gets a ``Request`` and
    returns a dict / list (JSON), ``(status, dict)``, a ``Reply``, a ``str`` (HTML if it starts with ``<``) or bytes."""

    def register(function):
        _routes.append((method.upper(), path, function))
        return function

    return register


def _answer(result) -> Reply:
    if isinstance(result, Reply):
        return result
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], int):
        reply = _answer(result[1])
        reply.status = result[0]
        return reply
    if isinstance(result, bytes):
        return Reply(200, result)
    if isinstance(result, str):
        return Reply(200, result, "text/html; charset=utf-8" if result.lstrip().startswith("<") else "text/plain; charset=utf-8")
    return Reply(200, json.dumps(result if result is not None else {"ok": True}), "application/json")


def _find(method: str, path: str):
    best = None
    for m, prefix, function in _routes:
        if (
            m == method
            and (path == prefix or (prefix.endswith("/") and path.startswith(prefix)))
            and (best is None or len(prefix) > len(best[0]))
        ):
            best = (prefix, function)
    return best[1] if best else None


class _Handler(http.server.BaseHTTPRequestHandler):
    def _go(self):
        parts = urllib.parse.urlsplit(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        request = Request(
            self.command,
            parts.path,
            {k: v[0] for k, v in urllib.parse.parse_qs(parts.query).items()},
            {k.lower(): v for k, v in self.headers.items()},
            body,
        )
        function = _find(self.command, parts.path)
        try:
            reply = (
                _answer(function(request))
                if function
                else Reply(404, json.dumps({"ok": False, "message": "not found"}), "application/json")
            )
        except Exception as exc:
            log("route " + parts.path + " failed: " + "".join(traceback.format_exception_only(type(exc), exc)).strip(), "error")
            traceback.print_exc()
            reply = Reply(500, json.dumps({"ok": False, "message": "The service had a problem (see its log)."}), "application/json")
        self.send_response(reply.status)
        self.send_header("Content-Type", reply.content_type)
        self.send_header("Content-Length", str(len(reply.body)))
        for key, value in reply.headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(reply.body)

    do_GET = do_POST = do_PUT = do_DELETE = _go

    def log_message(self, *args):  # the add-on notes requests itself
        pass


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def serve(port: int | None = None) -> http.server.HTTPServer:
    """Answer the registered routes on ``127.0.0.1:<port>`` (the add-on hands them on, see ``routes`` in ``plugin.json``) in a thread of its own."""
    server = _Server(("127.0.0.1", port or int(_env("CA_PORT", "0"))), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True, name="routes").start()
    return server


# ------------------------------------------------------------------ the main loop

BACKOFF = (5, 15, 60, 300)  # seconds to wait after a poll failed once, twice, ...
stop = threading.Event()  # set when the add-on asks the service to end


def run(poll=None, every=None) -> None:
    """Start the routes (when there are any) and call ``poll()`` again and again: every ``every`` seconds (a number, or a function that returns one -
    ``api.interval`` is a good one), 120 by default. A poll that raises is noted with its traceback and tried again after a growing pause, so one bad answer of a web service
    never ends the service. Returns when the add-on stops the service."""
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(ValueError, OSError):  # (only the main thread may set it)
            signal.signal(sig, lambda *_: stop.set())
    if _routes and _env("CA_PORT"):
        serve()
    failures = 0
    while not stop.is_set():
        started = time.monotonic()
        if poll is not None:
            try:
                poll()
                failures = 0
            except Exception:
                failures += 1
                log("poll failed (" + str(failures) + "): " + traceback.format_exc().strip().splitlines()[-1], "error")
                traceback.print_exc()
        wait = every() if callable(every) else (every or 120)
        if failures:
            wait = max(wait, BACKOFF[min(failures, len(BACKOFF)) - 1])
        stop.wait(max(1.0, float(wait) - (time.monotonic() - started)))


if __name__ == "__main__":
    print(__doc__)
    sys.exit(0)
