"""Hands requests for the routes of a plugin service to that service (``pluginsvc.py``), before the app sees them.

A route is public when the plugin declared it so: the car calls it with no login and no token (the original services of a car send none), so only
the prefixes a service registered are reachable, never a page of the app. Requests are passed on unchanged - method, query, headers, body (also
a body without a length, also ``multipart/*``), status and content type - except for what must not cross: cookies, authorization, hop-by-hop
headers. Size and time are limited.
"""

from __future__ import annotations

import asyncio
import http.client
import time
from http.cookies import SimpleCookie

from . import accounts, db, framehead, pluginsvc, themes
from .auth_web import COOKIE

MAX_BODY = 8_000_000
MAX_ANSWER = 16_000_000
TIMEOUT = 30
LOCAL_CLIENTS = {
    "172.30.32.2",
    "127.0.0.1",
    "::1",
}  # the Supervisor gateway (ingress) and this machine: where non-public routes may come from
DROP_REQUEST = {
    "host",
    "cookie",
    "authorization",
    "connection",
    "keep-alive",
    "proxy-authorization",
    "te",
    "trailer",
    "upgrade",
    "transfer-encoding",
    "x-ca-vehicle",  # set by this proxy only (below) - never taken from a caller
    "x-ca-user",
}
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
DROP_ANSWER = {
    "connection",
    "keep-alive",
    "transfer-encoding",
    "set-cookie",
    "content-length",
    "upgrade",
    "proxy-authenticate",
    "te",
    "trailer",
}


def _forward(port: int, method: str, target: str, headers: list[tuple[str, str]], body: bytes) -> tuple[int, list[tuple[str, str]], bytes]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=TIMEOUT)
    try:
        conn.putrequest(method, target, skip_host=True, skip_accept_encoding=True)
        conn.putheader("Host", f"127.0.0.1:{port}")
        for name, value in headers:
            if name.lower() not in DROP_REQUEST and name.lower() != "content-length":
                conn.putheader(name, value)
        conn.putheader("Content-Length", str(len(body)))
        conn.endheaders(body)
        response = conn.getresponse()
        data = response.read(MAX_ANSWER + 1)
        if len(data) > MAX_ANSWER:
            return 502, [("content-type", "text/plain")], b"answer too large"
        return response.status, [(k, v) for k, v in response.getheaders() if k.lower() not in DROP_ANSWER], data
    finally:
        conn.close()


def _session_user(headers: list[tuple[bytes, bytes]]):
    """The person signed in to the app (its session cookie), or None."""
    raw = next((v.decode("latin-1") for k, v in headers if k == b"cookie"), "")
    if not raw:
        return None
    jar = SimpleCookie()
    try:
        jar.load(raw)
    except Exception:
        return None
    morsel = jar.get(COOKIE)
    if morsel is None:
        return None
    with db.tx() as conn:
        return accounts.session_user(conn, morsel.value)


def _signed_in(headers: list[tuple[bytes, bytes]]) -> bool:
    """A person signed in to the app - they may use the non-public routes of a service from outside, too."""
    return _session_user(headers) is not None


def frame_ok(method: str, headers: list[tuple[bytes, bytes]]) -> bool:
    """A request that changes something and comes from a page of a package needs ``X-Requested-With: frame`` - a foreign site can not add that header
    to a request of your browser (cross-site protection)."""
    if method.upper() not in UNSAFE:
        return True
    return next((v.decode("latin-1").strip().lower() for k, v in headers if k == b"x-requested-with"), "") == "frame"


def identity(headers: list[tuple[bytes, bytes]], query: str, client: str) -> list[tuple[str, str]]:
    """The two headers a service gets for a non-public route: ``X-CA-Vehicle`` (the car of the page, from ``?car=``, only if it exists) and
    ``X-CA-User`` (the id of the signed-in person - no name - or ``ha`` inside Home Assistant). Never cookies."""
    out: list[tuple[str, str]] = []
    car = next((v for k, v in (p.partition("=")[::2] for p in query.split("&")) if k == "car"), "")
    with db.tx() as conn:
        if car.isdigit() and len(car) < 10 and conn.execute("SELECT 1 FROM vehicles WHERE id = ?", (int(car),)).fetchone():
            out.append(("X-CA-Vehicle", car))
    user = _session_user(headers)
    if user is not None:
        out.append(("X-CA-User", str(user["id"])))
    elif client in LOCAL_CLIENTS:
        out.append(("X-CA-User", "ha"))
    return out


class PluginProxy:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        route = pluginsvc.route_for(scope.get("path", ""))
        if route is None:
            return await self.app(scope, receive, send)
        client = (scope.get("client") or ("", 0))[0]
        if not route["public"] and client not in LOCAL_CLIENTS and not await asyncio.to_thread(_signed_in, scope.get("headers", [])):
            return await _reply(send, 404, b"not found")  # from outside only for a signed-in person
        if not route["public"] and not frame_ok(scope["method"], scope.get("headers", [])):
            return await _reply(send, 403, b"missing header X-Requested-With: frame")
        body = b""
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return None
            body += message.get("body", b"")
            if len(body) > MAX_BODY:
                return await _reply(send, 413, b"too large")
            if not message.get("more_body"):
                break
        query = scope.get("query_string", b"").decode("latin-1")
        target = scope["raw_path"].decode("latin-1") if scope.get("raw_path") else scope["path"]
        if query:
            target += "?" + query
        headers = [(k.decode("latin-1"), v.decode("latin-1")) for k, v in scope.get("headers", [])]
        if not route["public"]:
            headers += await asyncio.to_thread(identity, scope.get("headers", []), query, client)
        started = time.monotonic()
        try:
            status, out_headers, data = await asyncio.to_thread(_forward, route["port"], scope["method"], target, headers, body)
        except (OSError, http.client.HTTPException, TimeoutError):
            await asyncio.to_thread(
                pluginsvc.note_car_request,
                route["pk"],
                scope["method"],
                scope["path"],
                502,
                len(body),
                started,
                "the service does not answer",
                query,
            )
            return await _reply(send, 502, b"the service does not answer")
        await asyncio.to_thread(
            pluginsvc.note_car_request, route["pk"], scope["method"], scope["path"], status, len(body), started, "", query
        )
        if not route["public"] and status == 200 and scope["method"] == "GET":
            data = await asyncio.to_thread(_with_head, data, out_headers, route["pk"], scope["path"], query, scope.get("headers", []))
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in out_headers]
                + [(b"content-length", str(len(data)).encode())],
            }
        )
        await send({"type": "http.response.body", "body": data})
        return None


def _with_head(
    data: bytes, out_headers: list[tuple[str, str]], pk: int, path: str, query: str, headers: list[tuple[bytes, bytes]]
) -> bytes:
    """A page of a package that is opened as a page of its own (a navigation, not a fetch from a script) gets the head of Car Assistant."""
    if "text/html" not in next((v for k, v in out_headers if k.lower() == "content-type"), "").lower():
        return data
    asked = {k.decode(): v.decode("latin-1").lower() for k, v in headers if k in (b"sec-fetch-dest", b"accept", b"x-requested-with")}
    if (
        asked.get("sec-fetch-dest") not in (None, "document")
        or "x-requested-with" in asked
        or "text/html" not in asked.get("accept", "text/html")
    ):
        return data
    with db.tx() as conn:
        ctx = framehead.context(conn, pk, path)
    if ctx is None:
        return data
    theme = next((v for k, v in (p.partition("=")[::2] for p in query.split("&")) if k == "theme"), "")
    theme = theme if theme in themes.available() else themes.DEFAULT
    base = framehead.base_of(next((v.decode("latin-1") for k, v in headers if k == b"x-ingress-path"), None))
    return framehead.inject(data, framehead.markup(ctx, base), f"{base}/frame-head.css?theme={theme}", framehead.footer(ctx, base))


async def _reply(send, status: int, text: bytes) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"text/plain"), (b"content-length", str(len(text)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": text})
