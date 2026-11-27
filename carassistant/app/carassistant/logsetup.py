"""The log of the add-on in Home Assistant (*Settings -> Apps -> Car Assistant -> Log*): its format, its levels, the filter against repeats and the line
for every request (docs/logs.md).

There are two logs and they say different things. THIS one is the app itself: how it starts, what it cannot reach, what went wrong - and, one level
lower, what it does (a request, a delivery of values, the lines the app wrote into the log of a plugin). The *Logs* page of a plugin inside the app holds
what ONE plugin does for ONE car; it is kept per car and per plugin and has a switch of its own.

What is never written here, at any level: an access token, a value of the car (position, odometer ...), a query string or a body, the free text a plugin
sends (it may hold anything, and this log is what people copy into a forum), the name of a person."""

from __future__ import annotations

import logging
import threading
import time

FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LEVELS = {"debug": logging.DEBUG, "info": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR}
REPEAT_WINDOW = 300.0  # seconds: the same warning or error is written once in this time
REPEAT_KEYS = 500  # how many different messages the filter keeps in mind


def level_name(text: str) -> str:
    """The level of the option ``log_level`` (in any case); anything that is not one of the four reads as ``info``."""
    name = str(text or "").strip().lower()
    return name if name in LEVELS else "info"


def uvicorn_level(text: str) -> str:
    """The level uvicorn is told. Its own ``debug`` lines are traces of the connection, not what a person looks for in this log (the request lines of
    :class:`RequestLog` are): it never goes lower than ``info``."""
    name = level_name(text)
    return "info" if name == "debug" else name


class RepeatFilter(logging.Filter):
    """The same warning or error again within a few minutes is not written again; the next one after that time says how many were left out. So a
    Home Assistant that cannot be reached fills the log with one line, not with one for every try. Lines below warning are never touched: a request
    line or a note about the start is one thing that happened, however often it happens."""

    def __init__(self, window: float = REPEAT_WINDOW, clock=time.monotonic):
        super().__init__()
        self.window = window
        self._clock = clock
        self._seen: dict[
            tuple[str, int, str], list[float]
        ] = {}  # (logger, level, text) -> [when it was written, how many were left out since]
        self._lock = threading.Lock()

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno < logging.WARNING:
            return True
        try:
            text = record.getMessage()
        except Exception:  # a call with the wrong arguments is the caller's mistake, not a reason to lose the line (the handler reports it)
            return True
        key = (record.name, record.levelno, text)
        now = self._clock()
        with self._lock:
            entry = self._seen.get(key)
            if entry is not None and now - entry[0] < self.window:
                entry[1] += 1
                return False
            left_out, since = (int(entry[1]), entry[0]) if entry else (0, now)
            self._seen[key] = [now, 0]
            if len(self._seen) > REPEAT_KEYS:
                self._forget(now)
        if left_out:
            record.msg = f"{text} (repeated {left_out}x in the last {max(1, round((now - since) / 60))} min)"
            record.args = ()
        return True

    def _forget(self, now: float) -> None:
        for key in [k for k, (when, _n) in self._seen.items() if now - when >= self.window]:
            del self._seen[key]
        if len(self._seen) > REPEAT_KEYS:  # a flood of different texts: better to repeat now and then than to grow
            self._seen.clear()


def setup(text: str) -> int:
    """Set the log up for the whole process (it takes the place of ``logging.basicConfig``); returns the level as a number.

    Our own loggers (``carassistant`` and everything below it) follow the option. The libraries we use are heard only from warning on, whatever the
    option says: at ``debug`` an image library or an upload parser would otherwise write a line for every chunk it touches."""
    number = LEVELS[level_name(text)]
    root = logging.getLogger()
    for old in [h for h in root.handlers if getattr(h, "_carassistant", False)]:  # (set up twice in one process: one handler only)
        root.removeHandler(old)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(FORMAT, DATE_FORMAT))
    handler.addFilter(RepeatFilter())
    handler._carassistant = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(max(number, logging.WARNING))
    logging.getLogger("carassistant").setLevel(number)
    return number


class RequestLog:
    """One line per request - at the level ``debug`` only; otherwise the request passes by without a trace of it: ``GET /v/{vid}/fuel -> 200 (31 ms)``.

    The line names the ROUTE the request matched (its pattern, with the braces), never the address that was asked for: addresses carry numbers of
    cars and, in places, a token (``/v/{vid}/fuel/import/{token}``), and nothing of the query, the headers or the body is ever looked at. The checks of the
    watchdog and the files of the app's own styles and scripts are left out (they would be most of the log). A request a plugin's service answered is
    named by the number of the plugin (``carassistant_label`` in the scope, set by the proxy), not by what it asked for."""

    def __init__(self, app, logger: logging.Logger | None = None):
        self.app = app
        self.log = logger or logging.getLogger("carassistant.http")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not self.log.isEnabledFor(logging.DEBUG):
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        if path == "/healthz" or path.startswith("/static/"):
            return await self.app(scope, receive, send)
        started = time.perf_counter()
        status = 0

        async def watch(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, watch)
        except Exception:
            status = status or 500  # (the server answers 500 when nothing was sent yet)
            raise
        finally:
            self.log.debug(
                "%s %s -> %s (%d ms)", scope.get("method", "?"), label(scope), status or "-", (time.perf_counter() - started) * 1000
            )


def label(scope) -> str:
    """What a request is called in the log: the plugin it was handed to, or the pattern of the route it matched (``(no page)`` when none did)."""
    named = scope.get("carassistant_label")
    if isinstance(named, str) and named:
        return named
    pattern = getattr(scope.get("route"), "path", None)
    return pattern if isinstance(pattern, str) and pattern else "(no page)"
