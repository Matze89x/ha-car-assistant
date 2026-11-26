"""A made-up Home Assistant: to try the Home Assistant plugin without one, and for the tests of the live connection.

It speaks the part of Home Assistant that Car Assistant uses: the REST API (``/api/states``, ``/api/config``, ``/api/services/<domain>/<service>``) and the
WebSocket API (``/api/websocket``: login, ping, ``get_states``, ``subscribe_trigger``, ``subscribe_events``, ``unsubscribe_events`` and the registries
of areas, devices and entities) - with real WebSocket frames, so a real client library talks to it.

    python tools/fake_ha.py [port]
    CARASSISTANT_HA_API=http://127.0.0.1:<port>/api SUPERVISOR_TOKEN=test-token  <start Car Assistant>

In a test: ``fake = FakeHA().start()``, ``fake.set("sensor.range", "300", "km")`` (also pushes the change to everybody who follows it), ``fake.drop()``
cuts every connection, ``fake.refuse_auth = True`` makes it refuse the login, ``fake.silent = True`` makes it stop answering."""

from __future__ import annotations

import base64
import hashlib
import json
import socket
import struct
import sys
import threading
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _frame(opcode: int, payload: bytes) -> bytes:
    """One frame as a server sends it (not masked)."""
    head = bytes([0x80 | opcode])
    size = len(payload)
    if size < 126:
        head += bytes([size])
    elif size < 65536:
        head += bytes([126]) + struct.pack(">H", size)
    else:
        head += bytes([127]) + struct.pack(">Q", size)
    return head + payload


def _read(sock: socket.socket, count: int) -> bytes:
    data = b""
    while len(data) < count:
        chunk = sock.recv(count - len(data))
        if not chunk:
            raise ConnectionError("closed")
        data += chunk
    return data


def _read_frame(sock: socket.socket) -> tuple[int, bytes]:
    """One frame of a client (masked): ``(opcode, payload)``; a message in pieces is put together."""
    message = b""
    first_opcode = 0
    while True:
        b1, b2 = _read(sock, 2)
        fin, opcode, size = b1 & 0x80, b1 & 0x0F, b2 & 0x7F
        if size == 126:
            size = struct.unpack(">H", _read(sock, 2))[0]
        elif size == 127:
            size = struct.unpack(">Q", _read(sock, 8))[0]
        mask = _read(sock, 4) if b2 & 0x80 else b"\0\0\0\0"
        payload = bytes(c ^ mask[i % 4] for i, c in enumerate(_read(sock, size)))
        if opcode:
            first_opcode = opcode
        message += payload
        if fin:
            return first_opcode, message


class _Connection:
    """One WebSocket client."""

    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.lock = threading.Lock()
        self.subs: dict[int, dict] = {}  # id of the subscription -> {"kind": trigger | events, "entities": set | None}
        self.authed = False

    def send(self, message: dict) -> None:
        with self.lock:
            self.sock.sendall(_frame(0x1, json.dumps(message).encode()))

    def close(self) -> None:
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


class FakeHA:
    def __init__(self, token: str = "test-token", port: int = 0):
        self.token = token
        self.states: dict[str, dict] = {}
        self.areas: list[dict] = []  # [{"area_id", "name"}]
        self.devices: list[dict] = []  # [{"id", "name", "area_id", ...}]
        self.entities: list[dict] = []  # [{"entity_id", "device_id", "area_id", ...}]
        self.calls: list[tuple[str, str, dict]] = []  # the services that were called
        self.reads = 0  # how often the whole list of entities was asked for through the REST API
        self.refuse_auth = False
        self.silent = False  # a connection that stays open but does not answer any more
        self.refuse_trigger = False  # subscribe_trigger answers "not allowed" (subscribe_events still works)
        self.refuse_subscribe = False  # every kind of subscription is refused
        self.rest_down = False  # the REST API answers 503
        self._lock = threading.RLock()
        self._conns: list[_Connection] = []
        self.server = ThreadingHTTPServer(("127.0.0.1", port), self._handler())
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def api(self) -> str:
        return f"http://127.0.0.1:{self.port}/api"

    def start(self) -> FakeHA:
        self._thread.start()
        return self

    def stop(self) -> None:
        self.drop()
        self.server.shutdown()
        self.server.server_close()

    def connections(self) -> int:
        with self._lock:
            return sum(1 for c in self._conns if c.authed)

    def subscriptions(self) -> list[dict]:
        with self._lock:
            return [s for c in self._conns for s in c.subs.values()]

    # ---- the world

    def set(self, entity_id: str, state, unit: str | None = None, dclass: str | None = None, **attrs) -> dict:
        """Create or change an entity - and tell everybody who follows it."""
        with self._lock:
            before = self.states.get(entity_id)
            attributes = {k: v for k, v in attrs.items() if v is not None}
            if unit:
                attributes["unit_of_measurement"] = unit
            if dclass:
                attributes["device_class"] = dclass
            stamp = _now()
            new = {
                "entity_id": entity_id,
                "state": str(state),
                "attributes": attributes,
                "last_changed": stamp,
                "last_reported": stamp,
                "last_updated": stamp,
                "context": {"id": "x", "parent_id": None, "user_id": None},
            }
            self.states[entity_id] = new
            self._push(entity_id, before, new)
        return new

    def remove(self, entity_id: str) -> None:
        with self._lock:
            before = self.states.pop(entity_id, None)
            self._push(entity_id, before, None)

    def _push(self, entity_id: str, old: dict | None, new: dict | None) -> None:
        for conn in list(self._conns):
            for sub_id, sub in list(conn.subs.items()):
                if sub["kind"] == "trigger" and entity_id in sub["entities"]:
                    event = {"variables": {"trigger": {"platform": "state", "entity_id": entity_id, "from_state": old, "to_state": new}}}
                elif sub["kind"] == "events":
                    event = {"event_type": "state_changed", "data": {"entity_id": entity_id, "old_state": old, "new_state": new}}
                else:
                    continue
                try:
                    conn.send({"id": sub_id, "type": "event", "event": event})
                except OSError:
                    pass

    def drop(self) -> None:
        """Cut every WebSocket connection, like a network that fails."""
        with self._lock:
            conns, self._conns = self._conns, []
        for conn in conns:
            conn.close()

    # ---- the WebSocket API

    def _command(self, conn: _Connection, message: dict) -> None:
        kind, message_id = message.get("type"), message.get("id")

        def answer(result=None, success: bool = True, error: str = ""):
            body = {"id": message_id, "type": "result", "success": success, "result": result}
            if not success:
                body["error"] = {"code": "not_allowed", "message": error}
            conn.send(body)

        if kind == "ping":
            conn.send({"id": message_id, "type": "pong"})
        elif kind == "get_states":
            answer(list(self.states.values()))
        elif kind == "subscribe_trigger":
            trigger = message.get("trigger") or {}
            if self.refuse_trigger or self.refuse_subscribe:
                return answer(success=False, error="not allowed")
            ids = trigger.get("entity_id")
            conn.subs[message_id] = {"kind": "trigger", "entities": set(ids if isinstance(ids, list) else [ids]), "id": message_id}
            answer()
        elif kind == "subscribe_events":
            if self.refuse_subscribe:
                return answer(success=False, error="not allowed")
            conn.subs[message_id] = {"kind": "events", "entities": None, "id": message_id}
            answer()
        elif kind == "unsubscribe_events":
            conn.subs.pop(message.get("subscription"), None)
            answer()
        elif kind == "config/area_registry/list":
            answer(self.areas)
        elif kind == "config/device_registry/list":
            answer(self.devices)
        elif kind == "config/entity_registry/list":
            answer(self.entities)
        else:
            answer(success=False, error=f"unknown command {kind}")

    def _serve_socket(self, sock: socket.socket) -> None:
        conn = _Connection(sock)
        with self._lock:
            self._conns.append(conn)
        try:
            conn.send({"type": "auth_required", "ha_version": "2026.11.0"})
            while True:
                opcode, payload = _read_frame(sock)
                if opcode == 0x8:
                    break
                if opcode == 0x9:
                    with conn.lock:
                        sock.sendall(_frame(0xA, payload))
                    continue
                if opcode != 0x1 or self.silent:
                    continue
                message = json.loads(payload.decode())
                if not conn.authed:
                    if message.get("type") == "auth" and message.get("access_token") == self.token and not self.refuse_auth:
                        conn.authed = True
                        conn.send({"type": "auth_ok", "ha_version": "2026.11.0"})
                    else:
                        conn.send({"type": "auth_invalid", "message": "Invalid access token or password"})
                        break
                    continue
                with self._lock:
                    self._command(conn, message)
        except (OSError, ConnectionError, ValueError):
            pass
        finally:
            with self._lock:
                if conn in self._conns:
                    self._conns.remove(conn)
            conn.close()

    # ---- the REST API

    def _handler(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args):
                pass

            def _json(self, code: int, body) -> None:
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _allowed(self) -> bool:
                if fake.rest_down:
                    self._json(503, {"message": "down"})
                    return False
                if self.headers.get("Authorization") != f"Bearer {fake.token}":
                    self._json(401, {"message": "unauthorized"})
                    return False
                return True

            def do_GET(self):
                path = self.path.split("?")[0]
                if path == "/api/websocket" and self.headers.get("Upgrade", "").lower() == "websocket":
                    key = self.headers.get("Sec-WebSocket-Key", "")
                    accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()  # noqa: S324 - the handshake of the protocol
                    self.send_response(101, "Switching Protocols")
                    self.send_header("Upgrade", "websocket")
                    self.send_header("Connection", "Upgrade")
                    self.send_header("Sec-WebSocket-Accept", accept)
                    self.end_headers()
                    self.wfile.flush()
                    self.close_connection = True
                    fake._serve_socket(self.connection)
                    return
                if not self._allowed():
                    return
                if path == "/api/states":
                    fake.reads += 1
                    with fake._lock:
                        self._json(200, list(fake.states.values()))
                elif path.startswith("/api/states/"):
                    state = fake.states.get(path[len("/api/states/") :])
                    self._json(200, state) if state else self._json(404, {"message": "Entity not found."})
                elif path == "/api/config":
                    self._json(200, {"country": "DE", "currency": "EUR", "version": "2026.11.0", "latitude": 52.5, "longitude": 13.4})
                else:
                    self._json(404, {"message": "not found"})

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                parts = self.path.split("?")[0].split("/")
                if self.path.split("?")[0] == "/fake/set":  # (only here, not in Home Assistant) change an entity from outside: curl -d '{"entity_id": ..., "state": ...}'
                    attrs = body.get("attributes") or {}
                    fake.set(body["entity_id"], body.get("state", ""), body.get("unit"), body.get("device_class"), **attrs)
                    return self._json(200, {"ok": True})
                if not self._allowed():
                    return
                if len(parts) == 5 and parts[:3] == ["", "api", "services"]:
                    fake.calls.append((parts[3], parts[4], body))
                    self._json(200, [])
                else:
                    self._json(404, {"message": "not found"})

        return Handler


def demo(fake: FakeHA) -> None:
    """A car, a wallbox and some more, as a Home Assistant at home might hold them."""
    fake.areas = [{"area_id": "garage", "name": "Garage"}, {"area_id": "driveway", "name": "Driveway"}]
    fake.devices = [
        {"id": "dev_car", "name": "Family car", "name_by_user": None, "area_id": "driveway", "manufacturer": "Example", "model": "EV"},
        {"id": "dev_box", "name": "Wallbox", "name_by_user": None, "area_id": "garage", "manufacturer": "Example", "model": "Box"},
    ]
    car = {"device_id": "dev_car", "area_id": None, "platform": "example"}
    box = {"device_id": "dev_box", "area_id": None, "platform": "example"}
    fake.entities = [
        {"entity_id": e, **car}
        for e in (
            "sensor.family_car_odometer",
            "sensor.family_car_battery",
            "sensor.family_car_range",
            "device_tracker.family_car",
            "lock.family_car",
        )
    ] + [{"entity_id": e, **box} for e in ("sensor.wallbox_status", "sensor.wallbox_power", "binary_sensor.wallbox_plugged")]
    fake.set("sensor.family_car_odometer", "48210.5", "km", "distance", friendly_name="Family car odometer")
    fake.set("sensor.family_car_battery", "64", "%", "battery", friendly_name="Family car battery")
    fake.set("sensor.family_car_range", "281", "km", "distance", friendly_name="Family car range")
    fake.set("device_tracker.family_car", "not_home", latitude=52.52, longitude=13.405, gps_accuracy=8, friendly_name="Family car")
    fake.set("lock.family_car", "locked", friendly_name="Family car lock")
    fake.set("binary_sensor.family_car_door_front_left", "off", None, "door", friendly_name="Family car door front left")
    fake.set("sensor.family_car_tyre_front_left", "34.8", "psi", "pressure", friendly_name="Family car tyre front left")
    fake.set("sensor.wallbox_status", "Charging", friendly_name="Wallbox status")
    fake.set("sensor.wallbox_power", "7400", "W", "power", friendly_name="Wallbox power")
    fake.set("binary_sensor.wallbox_plugged", "on", None, "plug", friendly_name="Wallbox plugged")
    fake.set("sensor.outside_temperature", "8.5", "°C", "temperature", friendly_name="Outside temperature")
    fake.set("light.hallway", "on", friendly_name="Hallway light")


if __name__ == "__main__":
    fake = FakeHA(token="test-token", port=int(sys.argv[1]) if len(sys.argv) > 1 else 8123)
    demo(fake)
    fake.start()
    print(f"Fake Home Assistant on {fake.api}  (token: test-token)")
    print(f"  CARASSISTANT_HA_API={fake.api} SUPERVISOR_TOKEN=test-token")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        fake.stop()
