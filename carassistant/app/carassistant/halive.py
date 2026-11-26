"""A live connection to Home Assistant: its WebSocket API tells the app the moment an entity changes - nothing has to ask again and again.

The Supervisor offers the same door as for the REST API (``ws://supervisor/core/websocket``, the token of the add-on). The link logs in, follows exactly the
entities the plugins read (``subscribe_trigger`` on those entities only; ``subscribe_events`` for ``state_changed`` is the second way, should the first be
refused) and keeps the newest state of each in a small memory. Whoever reads (habridge.py) takes the states from there; ``on_change`` says which entity changed.

What keeps it dependable: the connection is watched (a ping every 25 s, silence for 70 s ends it), a lost connection is built up again with growing waits
(1 ... 60 s) and everything is looked at afresh then - the entities are read once through the REST API and merged by time, so a change missed meanwhile is
found; while there is no connection ``states()`` says so (None) and the readers fall back to asking, as they always did. A refused token is retried only
now and then. Nothing here stops anything else: without the library, outside the add-on or against a Home Assistant that does not answer, the plugins
simply check every few seconds."""

from __future__ import annotations

import contextlib
import json
import logging
import random
import threading
import time
import urllib.parse
from datetime import datetime

try:
    import websocket  # the package websocket-client
except ImportError:  # the checks of packages and the other parts run without it; the plugins then ask Home Assistant every few seconds
    websocket = None

from . import config, ha

log = logging.getLogger("carassistant")


class _Refused(Exception):
    """Home Assistant did not accept the token."""


def available() -> bool:
    """Can there be a live connection at all: the library is there and this is the add-on (a token of the Supervisor)."""
    return websocket is not None and ha.available()


def url() -> str:
    """The address of the WebSocket API that belongs to the REST address (Supervisor: ``.../core/api`` -> ``.../core/websocket``; Home Assistant itself:
    ``.../api`` -> ``.../api/websocket``)."""
    base = config.ha_api_base().rstrip("/")
    ws = base.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
    return ws[: -len("/api")] + "/websocket" if base.endswith("/core/api") else ws + "/websocket"


def _stamp(state: dict) -> datetime | None:
    try:
        return datetime.fromisoformat(str(state.get("last_updated") or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def _newer(new: dict, old: dict | None) -> bool:
    """Is ``new`` at least as new as ``old``? (What cannot be compared counts as newer: Home Assistant is the one who knows.)"""
    if old is None:
        return True
    a, b = _stamp(new), _stamp(old)
    return a is None or b is None or a >= b


class Link:
    """The connection. ``follow()`` says which entities matter, ``states()`` gives their newest states (None while there is no live connection)."""

    PING_EVERY = 25.0  # seconds without a message: ask Home Assistant if it is still there
    DEAD_AFTER = 70.0  # seconds without ANY message: the connection is dead
    READ_TIMEOUT = 1.0  # how long one read waits (the loop also looks at what is followed, the stop and the heartbeat)
    CONNECT_TIMEOUT = 10.0
    BACKOFF = (1.0, 2.0, 5.0, 10.0, 30.0, 60.0)  # waits between two attempts (+/- a fifth)
    REFUSED_WAIT = 600.0  # a refused token is tried again only now and then
    STABLE_AFTER = 60.0  # a connection that held this long starts the waits afresh

    def __init__(self, address: str | None = None, token=None, snapshot=None, on_change=None, on_state=None):
        self._url = address
        self._token = token or config.supervisor_token
        self._snapshot = snapshot or (lambda: ha.all_states(0))
        self.on_change = on_change  # called with the id of an entity that changed (in the thread of the link: keep it short)
        self.on_state = on_state  # called with True / False when the live connection comes up / goes down
        self._lock = threading.Lock()
        self._follow: frozenset[str] = frozenset()
        self._version = 0
        self._cache: dict[str, dict] = {}
        self._active: frozenset[str] = frozenset()
        self._live = False
        self._ws = None
        self._ids = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.mode = ""  # trigger | events: how the entities are followed right now
        self.events = 0  # changes received (for the log / the tests)
        self.connects = 0
        self.last_error = ""

    # ---- what the readers use

    def follow(self, entities) -> None:
        """These entities are the ones that matter now (the others are not even asked about)."""
        wanted = frozenset(entities)
        with self._lock:
            if wanted != self._follow:
                self._follow = wanted
                self._version += 1
                self._cache = {
                    entity: state for entity, state in self._cache.items() if entity in wanted
                }  # what nobody reads any more goes

    @property
    def live(self) -> bool:
        return self._live

    def following(self) -> frozenset[str]:
        """The entities whose changes are certain to arrive now (the subscription that runs, and was looked at once): what was only just asked for is not in it."""
        return self._active if self._live else frozenset()

    def states(self) -> dict[str, dict] | None:
        """The newest state of every followed entity there is - or None while there is no live connection."""
        with self._lock:
            return dict(self._cache) if self._live else None

    def merge(self, states: dict[str, dict] | None) -> None:
        """A look at Home Assistant through the REST API (the readers do that now and then): what is newer than what the link holds is taken over."""
        if not states:
            return
        with self._lock:
            for entity in self._follow:
                state = states.get(entity)
                if state is not None and _newer(state, self._cache.get(entity)):
                    self._cache[entity] = state

    # ---- life of the thread

    def start(self) -> threading.Thread | None:
        if not available() and self._url is None:
            return None
        self._thread = threading.Thread(target=self._run, name="halive", daemon=True)
        self._thread.start()
        return self._thread

    def stop(self) -> None:
        self._stop.set()
        ws = self._ws
        if ws is not None:
            with contextlib.suppress(Exception):
                ws.close()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _set_live(self, value: bool) -> None:
        if self._live == value:
            return
        self._live = value
        if not value:
            self._active = frozenset()
            with self._lock:
                self._cache.clear()  # what it held is old now
        if self.on_state:
            with contextlib.suppress(Exception):
                self.on_state(value)

    def _run(self) -> None:
        failures = 0
        while not self._stop.is_set():
            started = time.monotonic()
            wait: float | None = None
            try:
                self._session()
            except _Refused as exc:
                self.last_error = f"Home Assistant refused the login ({exc})"
                log.warning("Live connection to Home Assistant: %s - trying again in %d minutes", self.last_error, self.REFUSED_WAIT // 60)
                wait = self.REFUSED_WAIT
            except Exception as exc:
                text = f"{type(exc).__name__}: {exc}"[:200]
                if failures == 0 or text != self.last_error:  # said once for the same trouble, not at every try
                    log.warning("Live connection to Home Assistant lost (%s) - building it up again", text)
                self.last_error = text
            finally:
                self._set_live(False)
                self._ws = None
            if self._stop.is_set():
                return
            held = time.monotonic() - started
            failures = 0 if held >= self.STABLE_AFTER else failures + 1
            if wait is None:
                wait = self.BACKOFF[min(failures, len(self.BACKOFF)) - 1] if failures else self.BACKOFF[0]
                wait *= random.uniform(0.8, 1.2)  # noqa: S311 - a pause between two tries, nothing secret
            self._stop.wait(wait)

    # ---- one connection

    def _next_id(self) -> int:
        self._ids += 1
        return self._ids

    def _send(self, ws, **message) -> int:
        message_id = self._next_id()
        ws.send(json.dumps({"id": message_id, **message}))
        return message_id

    def _recv(self, ws, wait: float):
        """One message as a dict, or None when nothing came within ``wait`` seconds."""
        ws.settimeout(wait)
        try:
            raw = ws.recv()
        except websocket.WebSocketTimeoutException:
            return None
        if not raw:
            raise ConnectionError("the connection was closed")
        try:
            message = json.loads(raw)
        except ValueError:
            return {}
        return message if isinstance(message, dict) else {}

    def _session(self) -> None:
        address = self._url or url()
        host = urllib.parse.urlsplit(address).hostname or ""
        ws = websocket.create_connection(
            address, timeout=self.CONNECT_TIMEOUT, http_no_proxy=[host]
        )  # (never through a proxy: it is Home Assistant)
        self._ws = ws
        try:
            hello = self._recv(ws, self.CONNECT_TIMEOUT)
            if not hello or hello.get("type") != "auth_required":
                raise ConnectionError("Home Assistant did not ask for a login")
            ws.send(json.dumps({"type": "auth", "access_token": self._token()}))
            answer = self._recv(ws, self.CONNECT_TIMEOUT) or {}
            if answer.get("type") == "auth_invalid":
                raise _Refused(str(answer.get("message") or "invalid token")[:80])
            if answer.get("type") != "auth_ok":
                raise ConnectionError("Home Assistant did not accept the login")
            self.connects += 1
            self._follow_changes(ws)
        finally:
            with contextlib.suppress(Exception):
                ws.close()

    def _follow_changes(self, ws) -> None:
        """The loop of a connection: keep what is followed in step, take the changes, watch the connection."""
        sub: dict | None = None  # the subscription that runs: {"id", "mode", "version", "entities"}
        asked: dict | None = None  # the subscription that was asked for and has not been answered yet
        mode = "trigger"
        last_rx = last_ping = time.monotonic()
        while not self._stop.is_set():
            with self._lock:
                wanted, version = self._follow, self._version
            start = sub is None and bool(wanted)  # something to follow and nothing runs yet
            changed = sub is not None and sub["version"] != version  # or what is followed is another set now
            if asked is None and (start or changed):
                if sub is not None:  # what is followed changed: the old subscription ends, a new one starts
                    with contextlib.suppress(Exception):
                        self._send(ws, type="unsubscribe_events", subscription=sub["id"])
                    sub = None
                if wanted:
                    asked = self._subscribe(ws, mode, wanted, version)
            if not wanted and sub is None and asked is None:
                self._set_live(True)  # nothing to follow: connected, and nothing to say
            message = self._recv(ws, self.READ_TIMEOUT)
            now = time.monotonic()
            if message is not None:
                last_rx = now
                kind = message.get("type")
                if kind == "result" and asked is not None and message.get("id") == asked["id"]:
                    if message.get("success"):
                        sub, asked = asked, None
                        self.mode = sub["mode"]
                        self._seed(sub["entities"])
                        self._active = sub["entities"]
                        self._set_live(True)
                    elif mode == "trigger":  # the first way is refused: the second one does the same, with more traffic
                        log.info("Live connection to Home Assistant: subscribe_trigger refused, following state_changed instead")
                        mode = "events"
                        asked = self._subscribe(ws, mode, asked["entities"], asked["version"])
                    else:
                        raise ConnectionError("Home Assistant refused to report changes")
                elif kind == "event" and sub is not None and message.get("id") == sub["id"]:
                    self._take(message, sub)
            if now - last_rx > self.DEAD_AFTER:
                raise ConnectionError("Home Assistant does not answer any more")
            if now - last_ping > self.PING_EVERY:
                last_ping = now
                self._send(ws, type="ping")

    def _subscribe(self, ws, mode: str, entities: frozenset[str], version: int) -> dict:
        if mode == "trigger":
            message_id = self._send(ws, type="subscribe_trigger", trigger={"platform": "state", "entity_id": sorted(entities)})
        else:
            message_id = self._send(ws, type="subscribe_events", event_type="state_changed")
        return {"id": message_id, "mode": mode, "version": version, "entities": entities}

    def _seed(self, entities: frozenset[str]) -> None:
        """Right after (re)subscribing: look at every followed entity once (REST), so nothing that happened meanwhile is missed."""
        states = self._snapshot()
        if states is None:
            raise ConnectionError("the states of Home Assistant could not be read")
        with self._lock:
            for gone in set(self._cache) - set(entities):
                del self._cache[gone]
        self.merge(states)

    def _take(self, message: dict, sub: dict) -> None:
        event = message.get("event") or {}
        try:
            if sub["mode"] == "trigger":
                trigger = (event.get("variables") or {}).get("trigger") or {}
                entity, state = trigger.get("entity_id"), trigger.get("to_state")
            else:
                data = event.get("data") or {}
                entity, state = data.get("entity_id"), data.get("new_state")
        except AttributeError:
            return
        if not isinstance(entity, str) or entity not in sub["entities"] or not (state is None or isinstance(state, dict)):
            return
        with self._lock:
            if state is None:  # the entity was removed
                self._cache.pop(entity, None)
            elif _newer(state, self._cache.get(entity)):
                self._cache[entity] = state
            else:
                return
        self.events += 1
        if self.on_change:
            with contextlib.suppress(Exception):
                self.on_change(entity)


# ------------------------------------------------------------------ the devices and areas of the entities (for the list to choose from)


def _fetch_registry(address: str | None, token) -> dict[str, dict] | None:
    host = urllib.parse.urlsplit(address or url()).hostname or ""
    ws = websocket.create_connection(address or url(), timeout=10, http_no_proxy=[host])
    try:
        ws.settimeout(10)
        if json.loads(ws.recv()).get("type") != "auth_required":
            return None
        ws.send(json.dumps({"type": "auth", "access_token": token()}))
        if json.loads(ws.recv()).get("type") != "auth_ok":
            return None
        commands = {1: "config/entity_registry/list", 2: "config/device_registry/list", 3: "config/area_registry/list"}
        for message_id, kind in commands.items():
            ws.send(json.dumps({"id": message_id, "type": kind}))
        results: dict[int, list] = {}
        deadline = time.monotonic() + 10
        while len(results) < len(commands) and time.monotonic() < deadline:
            message = json.loads(ws.recv())
            if message.get("type") == "result" and message.get("id") in commands:
                if not message.get("success"):
                    return None
                results[message["id"]] = message.get("result") or []
    finally:
        with contextlib.suppress(Exception):
            ws.close()
    if len(results) < len(commands):
        return None
    areas = {a.get("area_id"): str(a.get("name") or "") for a in results[3] if isinstance(a, dict)}
    devices = {d.get("id"): d for d in results[2] if isinstance(d, dict)}
    out: dict[str, dict] = {}
    for entry in results[1]:
        if not isinstance(entry, dict) or not isinstance(entry.get("entity_id"), str):
            continue
        device = devices.get(entry.get("device_id")) or {}
        area = areas.get(entry.get("area_id") or device.get("area_id"), "")
        name = str(device.get("name_by_user") or device.get("name") or "")
        if name or area:
            out[entry["entity_id"]] = {"device": name, "area": area}
    return out


def registry(address: str | None = None, token=None) -> dict[str, dict] | None:
    """Which device and which area an entity belongs to: ``{entity id: {"device": name, "area": name}}`` - what the list of entities shows beside each one
    and what the words typed are looked for in, as in Home Assistant itself. One short connection of its own, kept for a minute; None when Home
    Assistant does not tell (the list is then without it)."""
    if websocket is None or (address is None and not ha.available()):
        return None

    def fetch():
        try:
            return _fetch_registry(address, token or config.supervisor_token)
        except Exception as exc:
            log.info("The devices and areas of Home Assistant could not be read (%s: %s)", type(exc).__name__, exc)
            return None

    return ha._cached("registry" + (address or ""), 60, fetch)
