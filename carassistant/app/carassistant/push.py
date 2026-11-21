"""Web push: notifications on a phone or computer that works like an app (home-screen web app), straight from this app to the device.

Only offered while a port is set (people then sign in over https). The content is encrypted end to end (RFC 8291) and only passes the push service of the
browser maker as an envelope. The server key (VAPID) is made on the first use and kept encrypted next to the other secrets; nothing here is personal.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import sqlite3
from datetime import UTC, datetime

from . import config, db, vault

log = logging.getLogger(__name__)
SUBJECT = "https://github.com"  # push services want a contact address of the sender; the library accepts only a host here (no path), so not the project page
MAX_DEVICES = 10  # per person
_ENDPOINT = re.compile(r"^https://[A-Za-z0-9.\-]+(:\d+)?/[\x21-\x7e]{8,1000}$")


def _vapid(conn: sqlite3.Connection):
    """(py_vapid object, public key base64url): made on first use, the private key is stored encrypted."""
    from cryptography.hazmat.primitives import serialization
    from py_vapid import Vapid

    pem = vault.decrypt(db.get_setting(conn, "push.vapid_private"))
    if pem:
        key = Vapid.from_pem(pem.encode())
    else:
        key = Vapid()
        key.generate_keys()
        db.set_setting(conn, "push.vapid_private", vault.encrypt(key.private_pem().decode()))
    raw = key.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return key, base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def public_key(conn: sqlite3.Connection) -> str:
    return _vapid(conn)[1]


def add_device(conn: sqlite3.Connection, user_id: int, sub: dict, label: str = "") -> int:
    """Remember a device of this person (it gets what the person chose in the notification matrix). ValueError for anything that is not a real subscription."""
    endpoint = str((sub or {}).get("endpoint") or "")
    keys = (sub or {}).get("keys") or {}
    p256dh, auth = str(keys.get("p256dh") or ""), str(keys.get("auth") or "")
    if (
        not _ENDPOINT.match(endpoint)
        or not re.fullmatch(r"[A-Za-z0-9_\-=]{20,200}", p256dh)
        or not re.fullmatch(r"[A-Za-z0-9_\-=]{8,64}", auth)
    ):
        raise ValueError("subscription")
    mine = conn.execute("SELECT COUNT(*) FROM push_devices WHERE user_id = ? AND endpoint <> ?", (user_id, endpoint)).fetchone()[0]
    if mine >= MAX_DEVICES:
        raise ValueError("limit")
    conn.execute(
        "INSERT INTO push_devices(user_id, endpoint, p256dh, auth, label, created_at) VALUES(?,?,?,?,?,?) "
        "ON CONFLICT(endpoint) DO UPDATE SET user_id = excluded.user_id, p256dh = excluded.p256dh, auth = excluded.auth, label = excluded.label, fails = 0",
        (user_id, endpoint, p256dh, auth, (label or "").strip()[:40], datetime.now(UTC).isoformat(timespec="seconds")),
    )
    return conn.execute("SELECT id FROM push_devices WHERE endpoint = ?", (endpoint,)).fetchone()["id"]


def remove_device(conn: sqlite3.Connection, user_id: int, device_id: int | None = None, endpoint: str = "") -> None:
    if device_id is not None:
        conn.execute("DELETE FROM push_devices WHERE id = ? AND user_id = ?", (device_id, user_id))
    elif endpoint:
        conn.execute("DELETE FROM push_devices WHERE endpoint = ? AND user_id = ?", (endpoint, user_id))


def devices(conn: sqlite3.Connection, user_id: int) -> list[dict]:
    """The devices of a person: ``id``, ``endpoint``, ``label``, ``created_at``."""
    return [
        dict(d) for d in conn.execute("SELECT id, endpoint, label, created_at FROM push_devices WHERE user_id = ? ORDER BY id", (user_id,))
    ]


def send(conn: sqlite3.Connection, user_id: int, title: str, body: str, url: str = "", vehicle_id: int | None = None) -> int:
    """Send to every device of the person (what is sent was chosen in the notification matrix; ``vehicle_id`` is only kept for the callers).
    Returns how many accepted it. A device the push service no longer knows is forgotten."""
    from pywebpush import WebPushException, webpush

    rows = conn.execute("SELECT id, endpoint, p256dh, auth FROM push_devices WHERE user_id = ?", (user_id,)).fetchall()
    if not rows:
        return 0
    key = _vapid(conn)[0]
    tag = hashlib.sha256(f"{title}|{body}".encode()).hexdigest()[:16]  # the same words replace each other on a device instead of piling up
    payload = json.dumps({"title": title[:120], "body": body[:600], "url": url or config.external_url() or "/", "tag": tag})
    sent = 0
    for row in rows:
        try:
            webpush(
                subscription_info={"endpoint": row["endpoint"], "keys": {"p256dh": row["p256dh"], "auth": row["auth"]}},
                data=payload,
                vapid_private_key=key,
                vapid_claims={"sub": SUBJECT},
                ttl=86400,
                timeout=10,
            )
            sent += 1
        except WebPushException as exc:
            code = getattr(getattr(exc, "response", None), "status_code", None)
            if code in (404, 410):  # the device removed its subscription
                conn.execute("DELETE FROM push_devices WHERE id = ?", (row["id"],))
            else:
                conn.execute("UPDATE push_devices SET fails = fails + 1 WHERE id = ?", (row["id"],))
                log.warning("Web push failed (%s): %s", code, exc)
        except Exception as exc:  # network problems must never stop the reminders
            log.warning("Web push failed: %s", exc)
    return sent
