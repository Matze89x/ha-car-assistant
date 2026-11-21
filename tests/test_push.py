"""Web push: what leaves the server when a notification is sent (to a local test server instead of a phone maker's push service)."""

import base64
import http.server
import os
import threading

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def test_a_notification_leaves_the_server_with_a_valid_sender_claim(env):
    from carassistant import accounts, db, push

    seen = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("content-length", 0)))
            seen.update({k.lower(): v for k, v in self.headers.items()})
            self.send_response(201)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        device = (
            ec.generate_private_key(ec.SECP256R1())
            .public_key()
            .public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        )
        with db.tx() as conn:
            accounts.create_user(conn, "owner", "A-very-Long-Passw0rd!x", admin=True)
            uid = conn.execute("SELECT id FROM users").fetchone()["id"]
            conn.execute(
                "INSERT INTO push_devices(user_id, endpoint, p256dh, auth, label, created_at) VALUES(?,?,?,?,?,?)",
                (uid, f"http://127.0.0.1:{server.server_port}/push/test", _b64(device), _b64(os.urandom(16)), "test", "now"),
            )
            assert push.send(conn, uid, "Title", "Text") == 1  # accepted by the push service
    finally:
        server.shutdown()
    assert seen["authorization"].lower().startswith("vapid") and seen["content-encoding"] == "aes128gcm" and seen["ttl"] == "86400"


def test_a_device_of_one_cars_web_app_only_gets_that_cars_messages(conn, monkeypatch):
    import pywebpush

    from carassistant import accounts, push

    uid = accounts.create_user(conn, "owner", "A-very-Long-Passw0rd!x", admin=True)
    one = conn.execute("INSERT INTO vehicles(name, slug) VALUES('One', 'one')").lastrowid
    two = conn.execute("INSERT INTO vehicles(name, slug) VALUES('Two', 'two')").lastrowid
    for name, car in (("everything", None), ("app-one", one), ("app-two", two)):
        did = conn.execute(
            "INSERT INTO push_devices(user_id, endpoint, p256dh, auth, label, created_at) VALUES(?,?,?,?,?,?)",
            (uid, f"https://push.example.com/{name}-0001", "x" * 20, "y" * 10, name, "now"),
        ).lastrowid
        if car:
            conn.execute("INSERT INTO push_device_cars(device_id, vehicle_id) VALUES(?,?)", (did, car))
    both = conn.execute("SELECT id FROM push_devices WHERE label = 'app-two'").fetchone()["id"]
    conn.execute("INSERT INTO push_device_cars(device_id, vehicle_id) VALUES(?,?)", (both, one))  # one device can serve several cars
    reached = []
    monkeypatch.setattr(pywebpush, "webpush", lambda subscription_info, **kw: reached.append(subscription_info["endpoint"].split("/")[-1]))
    push.send(conn, uid, "T", "B", "", one)
    assert sorted(reached) == ["app-one-0001", "app-two-0001", "everything-0001"]  # app-two serves both cars; nobody else is left out
    reached.clear()
    push.send(conn, uid, "T", "B", "", two)
    assert sorted(reached) == ["app-two-0001", "everything-0001"]  # car one's own device is left alone
    reached.clear()
    push.send(conn, uid, "T", "B")  # no car (the test message): every device
    assert len(reached) == 3
