"""Accounts for direct (external) access: users, sessions and passkeys (WebAuthn). A forgotten password is set again in Home Assistant (the panel needs no sign-in).

* The Home Assistant panel (Ingress) never needs a login – Home Assistant already authenticated the person.
* Direct access (published port / reverse proxy) is blocked until an account exists and then always requires a login.
* Passwords: PBKDF2-HMAC-SHA256 with a random salt (600,000 rounds), never stored in plain text.
* Sessions: random token in an HttpOnly cookie; only its SHA-256 hash is stored.
* Passkeys: WebAuthn (verified by the ``webauthn`` library); the password stays as fallback.
* Recovery: 8 one-time codes per user (stored as SHA-256 only), shown once.
Emergency (locked out): stop the app, delete the rows of table ``users`` from the database, start again – external access is blocked until a new account is created in Home Assistant.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import itertools
import json
import re
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta

from . import config

PBKDF2_ITER = 600_000
SESSION_DAYS = 400
USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,31}$")
PW_MIN, PW_MAX = 10, 128
CHALLENGE_TTL_S = 300
RP_NAME = "Car Assistant"


class AccountError(ValueError):
    """User-facing error; ``args[0]`` is an i18n key, ``args[1]`` optional format parameters."""

    def __init__(self, key: str, **params):
        super().__init__(key, params)
        self.key = key
        self.params = params


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------ password hashing
def _hash(password: str, salt: bytes | None = None, iterations: int = PBKDF2_ITER) -> tuple[str, int, str]:
    salt = salt or secrets.token_bytes(16)
    return salt.hex(), iterations, hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations).hex()


def _verify(password: str, salt_hex: str, iterations: int, hash_hex: str) -> bool:
    try:
        calc = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)).hex()
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(calc, hash_hex or "")


_DUMMY: tuple[str, int, str] | None = None


def _dummy_check(password: str) -> None:
    """An unknown user costs as much time as a known one (no hint whether a name exists)."""
    global _DUMMY
    if _DUMMY is None:
        _DUMMY = _hash("no-such-user", bytes(16))
    _verify(password, *_DUMMY)


STRICT_MIN = 12
COMMON = (
    "password",
    "passwort",
    "qwertz",
    "qwerty",
    "123456",
    "12345678",
    "letmein",
    "iloveyou",
    "admin",
    "welcome",
    "willkommen",
    "carassistant",
    "homeassistant",
    "abcdef",
    "111111",
    "000000",
    "changeme",
    "geheim",
)


def strict() -> bool:
    """Strict rules apply as soon as the app can be reached from outside (a public address or a direct-access password is set)."""
    return bool(config.external_url())


def check_new_password(password: str, username: str = "") -> None:
    if len(password) < PW_MIN:
        raise AccountError("acct.pw_short", n=PW_MIN)
    if len(password) > PW_MAX:
        raise AccountError("acct.pw_long", n=PW_MAX)
    if password.strip() != password:
        raise AccountError("acct.pw_space")
    if not strict():
        return
    if len(password) < STRICT_MIN:
        raise AccountError("acct.pw_short", n=STRICT_MIN)
    kinds = sum(
        (
            any(c.islower() for c in password),
            any(c.isupper() for c in password),
            any(c.isdigit() for c in password),
            any(not c.isalnum() for c in password),
        )
    )
    if kinds < 3:
        raise AccountError("acct.pw_classes")
    low = password.lower()
    name = (username or "").strip().lower()
    if len(set(low)) <= 4 or any(w in low for w in COMMON) or (len(name) >= 3 and name in low):
        raise AccountError("acct.pw_common")


# ------------------------------------------------------------------ passcode (app lock)
PIN_MIN, PIN_MAX = 6, 12
LOCK_CHOICES = (1, 5, 15, 60)


def check_passcode(code: str) -> None:
    if not code.isdigit() or not (PIN_MIN <= len(code) <= PIN_MAX):
        raise AccountError("acct.pin_bad", n=PIN_MIN, m=PIN_MAX)
    digits = [int(c) for c in code]
    steps = {b - a for a, b in itertools.pairwise(digits)}
    half = len(code) // 2
    if len(set(code)) == 1 or steps <= {1} or steps <= {-1} or (len(code) % 2 == 0 and code[:half] == code[half:]) or len(set(code)) <= 2:
        raise AccountError("acct.pin_weak")


def set_passcode(conn: sqlite3.Connection, uid: int, code: str, minutes: int = 15) -> None:
    check_passcode(code)
    salt, iters, digest = _hash(code)
    conn.execute(
        "UPDATE users SET pin_salt = ?, pin_iter = ?, pin_hash = ?, lock_minutes = ? WHERE id = ?",
        (salt, iters, digest, minutes if minutes in LOCK_CHOICES else 15, int(uid)),
    )


def clear_passcode(conn: sqlite3.Connection, uid: int) -> None:
    conn.execute("UPDATE users SET pin_salt = NULL, pin_iter = NULL, pin_hash = NULL WHERE id = ?", (int(uid),))


def has_passcode(conn: sqlite3.Connection, uid: int) -> bool:
    row = conn.execute("SELECT pin_hash FROM users WHERE id = ?", (int(uid),)).fetchone()
    return bool(row and row["pin_hash"])


def verify_passcode(conn: sqlite3.Connection, uid: int, code: str) -> bool:
    row = conn.execute("SELECT pin_salt, pin_iter, pin_hash FROM users WHERE id = ?", (int(uid),)).fetchone()
    if not row or not row["pin_hash"]:
        _dummy_check(code or "")
        return False
    return _verify(code or "", row["pin_salt"], row["pin_iter"], row["pin_hash"])


def check_username(name: str) -> str:
    name = (name or "").strip()
    if not USERNAME_RE.match(name):
        raise AccountError("acct.name_bad")
    return name


# ------------------------------------------------------------------ users
def has_users(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None


def admin_id(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT id FROM users WHERE is_admin = 1 ORDER BY id LIMIT 1").fetchone()
    return row["id"] if row else None


def get_user(conn: sqlite3.Connection, uid: int):
    return conn.execute(
        "SELECT id, username, display_name, is_admin, created_at, last_login FROM users WHERE id = ?", (int(uid),)
    ).fetchone()


def list_users(conn: sqlite3.Connection):
    return conn.execute(
        """SELECT u.id, u.username, u.display_name, u.is_admin, u.created_at, u.last_login,
                  (SELECT count(*) FROM passkeys p WHERE p.user_id = u.id) AS passkeys
           FROM users u ORDER BY u.id"""
    ).fetchall()


def create_user(conn: sqlite3.Connection, username: str, password: str, display_name: str = "", admin: bool = False) -> int:
    username = check_username(username)
    check_new_password(password, username)
    if conn.execute("SELECT 1 FROM users WHERE lower(username) = lower(?)", (username,)).fetchone():
        raise AccountError("acct.name_taken")
    if admin and admin_id(conn) is not None:
        admin = False
    salt, iters, digest = _hash(password)
    cur = conn.execute(
        "INSERT INTO users (username, display_name, pw_salt, pw_iter, pw_hash, is_admin, handle, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (username, (display_name or "").strip()[:40] or None, salt, iters, digest, 1 if admin else 0, secrets.token_hex(32), _iso(_now())),
    )
    return int(cur.lastrowid)


def authenticate(conn: sqlite3.Connection, username: str, password: str):
    row = conn.execute(
        "SELECT id, username, display_name, is_admin, pw_salt, pw_iter, pw_hash FROM users WHERE lower(username) = lower(?)",
        ((username or "").strip(),),
    ).fetchone()
    if row is None or not row["pw_hash"]:
        _dummy_check(password or "")
        return None
    if not _verify(password or "", row["pw_salt"], row["pw_iter"], row["pw_hash"]):
        return None
    return row


def delete_user(conn: sqlite3.Connection, uid: int, acting_uid: int | None) -> None:
    user = get_user(conn, uid)
    if user is None:
        raise AccountError("acct.no_user")
    if acting_uid is not None and int(uid) == int(acting_uid):
        raise AccountError("acct.no_self_delete")
    if user["is_admin"]:
        raise AccountError("acct.no_admin_delete")
    conn.execute("DELETE FROM users WHERE id = ?", (int(uid),))  # sessions, passkeys, codes cascade


def _own_password_ok(conn: sqlite3.Connection, uid: int, current: str) -> bool:
    row = conn.execute("SELECT pw_salt, pw_iter, pw_hash FROM users WHERE id = ?", (int(uid),)).fetchone()
    return bool(row and row["pw_hash"] and _verify(current or "", row["pw_salt"], row["pw_iter"], row["pw_hash"]))


def change_password(
    conn: sqlite3.Connection, uid: int, current: str, new: str, keep_token: str | None = None, *, trusted: bool = False
) -> None:
    """Change the own password. ``trusted``: the request comes from the Home Assistant panel (already authenticated) or a fresh passkey session."""
    # a trusted request need not give the old password - but one that IS given (the popup always asks) must be the right one
    if (not trusted or current) and not _own_password_ok(conn, uid, current):
        raise AccountError("acct.pw_wrong")
    check_new_password(new, (get_user(conn, uid) or {"username": ""})["username"])
    salt, iters, digest = _hash(new)
    conn.execute("UPDATE users SET pw_salt = ?, pw_iter = ?, pw_hash = ? WHERE id = ?", (salt, iters, digest, int(uid)))
    delete_user_sessions(conn, uid, keep_token)


def admin_set_password(conn: sqlite3.Connection, uid: int, new: str) -> None:
    user = get_user(conn, uid)
    if user is None:
        raise AccountError("acct.no_user")
    check_new_password(new, user["username"])
    salt, iters, digest = _hash(new)
    conn.execute("UPDATE users SET pw_salt = ?, pw_iter = ?, pw_hash = ? WHERE id = ?", (salt, iters, digest, int(uid)))
    delete_user_sessions(conn, uid)


def change_username(conn: sqlite3.Connection, uid: int, current: str, new: str, *, trusted: bool = False) -> str:
    if not (trusted or _own_password_ok(conn, uid, current)):
        raise AccountError("acct.pw_wrong")
    new = check_username(new)
    if conn.execute("SELECT 1 FROM users WHERE lower(username) = lower(?) AND id <> ?", (new, int(uid))).fetchone():
        raise AccountError("acct.name_taken")
    conn.execute("UPDATE users SET username = ? WHERE id = ?", (new, int(uid)))
    return new


# ------------------------------------------------------------------ sessions
def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(conn: sqlite3.Connection, user_id: int, auth: str = "password") -> str:
    token = secrets.token_hex(32)
    now = _now()
    conn.execute("DELETE FROM sessions WHERE expires_at < ?", (_iso(now),))
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id, auth, created_at, expires_at, unlocked_at) VALUES (?, ?, ?, ?, ?, ?)",
        (_token_hash(token), int(user_id), auth, _iso(now), _iso(now + timedelta(days=SESSION_DAYS)), _iso(now)),
    )
    conn.execute("UPDATE users SET last_login = ? WHERE id = ?", (_iso(now), int(user_id)))
    return token


def session_user(conn: sqlite3.Connection, token: str | None):
    if not token:
        return None
    return conn.execute(
        "SELECT u.id, u.username, u.display_name, u.is_admin, u.pin_hash IS NOT NULL AS has_pin, u.lock_minutes, s.unlocked_at "
        "FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ? AND s.expires_at > ?",
        (_token_hash(token), _iso(_now())),
    ).fetchone()


def strong_session(conn: sqlite3.Connection, token: str | None) -> bool:
    """Session started by passkey within the last 24 hours: the old password is not needed to change it."""
    if not token:
        return False
    row = conn.execute(
        "SELECT 1 FROM sessions WHERE token_hash = ? AND auth = 'passkey' AND created_at > ? AND expires_at > ?",
        (_token_hash(token), _iso(_now() - timedelta(days=1)), _iso(_now())),
    ).fetchone()
    return row is not None


def is_locked(user) -> bool:
    """A signed-in device with a passcode is locked after it was idle for the chosen time (0 = never) - or when it was locked by hand."""
    if user is None or not user["has_pin"] or not user["lock_minutes"]:
        return False
    if not user["unlocked_at"]:
        return True
    try:
        last = datetime.fromisoformat(user["unlocked_at"])
    except ValueError:
        return True
    return _now() - last > timedelta(minutes=int(user["lock_minutes"]))


def mark_active(conn: sqlite3.Connection, token: str | None, user=None) -> None:
    """Slide the idle timer (at most once a minute) so the lock only comes after real idleness."""
    if not token:
        return
    if user is not None and user["unlocked_at"]:
        try:
            if _now() - datetime.fromisoformat(user["unlocked_at"]) < timedelta(seconds=60):
                return
        except ValueError:
            pass
    conn.execute("UPDATE sessions SET unlocked_at = ? WHERE token_hash = ?", (_iso(_now()), _token_hash(token)))


def lock_session(conn: sqlite3.Connection, token: str | None) -> None:
    if token:
        conn.execute("UPDATE sessions SET unlocked_at = NULL WHERE token_hash = ?", (_token_hash(token),))


def delete_session(conn: sqlite3.Connection, token: str | None) -> None:
    if token:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))


def delete_user_sessions(conn: sqlite3.Connection, uid: int, keep_token: str | None = None) -> None:
    if keep_token:
        conn.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash <> ?", (int(uid), _token_hash(keep_token)))
    else:
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (int(uid),))


# ------------------------------------------------------------------ passkeys (WebAuthn)
def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64u(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _store_challenge(conn: sqlite3.Connection, challenge: bytes, purpose: str, uid: int | None) -> str:
    conn.execute("DELETE FROM auth_challenges WHERE expires_at < ?", (_iso(_now()),))
    token = secrets.token_urlsafe(24)
    conn.execute(
        "INSERT INTO auth_challenges (token, challenge, purpose, user_id, expires_at) VALUES (?, ?, ?, ?, ?)",
        (token, _b64u(challenge), purpose, uid, _iso(_now() + timedelta(seconds=CHALLENGE_TTL_S))),
    )
    return token


def _take_challenge(conn: sqlite3.Connection, token: str, purpose: str, uid: int | None = None) -> bytes:
    row = conn.execute(
        "SELECT challenge, user_id FROM auth_challenges WHERE token = ? AND purpose = ? AND expires_at > ?",
        (token or "", purpose, _iso(_now())),
    ).fetchone()
    conn.execute("DELETE FROM auth_challenges WHERE token = ?", (token or "",))  # one use only
    if row is None or (uid is not None and row["user_id"] != int(uid)):
        raise AccountError("acct.expired")
    return _unb64u(row["challenge"])


def passkey_list(conn: sqlite3.Connection, uid: int):
    return conn.execute("SELECT id, label, created_at, last_used FROM passkeys WHERE user_id = ? ORDER BY id", (int(uid),)).fetchall()


def passkey_delete(conn: sqlite3.Connection, uid: int, pk_id: int) -> None:
    conn.execute("DELETE FROM passkeys WHERE id = ? AND user_id = ?", (int(pk_id), int(uid)))


def passkeys_clear(conn: sqlite3.Connection, uid: int) -> None:
    if get_user(conn, uid) is None:
        raise AccountError("acct.no_user")
    conn.execute("DELETE FROM passkeys WHERE user_id = ?", (int(uid),))


def _handle(conn: sqlite3.Connection, uid: int) -> bytes:
    row = conn.execute("SELECT handle FROM users WHERE id = ?", (int(uid),)).fetchone()
    handle = row["handle"] if row else None
    if not handle:
        handle = secrets.token_hex(32)
        conn.execute("UPDATE users SET handle = ? WHERE id = ?", (handle, int(uid)))
    return bytes.fromhex(handle)


def passkey_register_begin(conn: sqlite3.Connection, uid: int, rp_id: str) -> dict:
    from webauthn import generate_registration_options, options_to_json
    from webauthn.helpers import base64url_to_bytes
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria,
        PublicKeyCredentialDescriptor,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )

    user = get_user(conn, uid)
    if user is None:
        raise AccountError("acct.no_user")
    exclude = [
        PublicKeyCredentialDescriptor(id=base64url_to_bytes(r["credential_id"]))
        for r in conn.execute("SELECT credential_id FROM passkeys WHERE user_id = ?", (int(uid),))
    ]
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=RP_NAME,
        user_id=_handle(conn, uid),
        user_name=user["username"],
        user_display_name=user["display_name"] or user["username"],
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED, user_verification=UserVerificationRequirement.PREFERRED
        ),
        exclude_credentials=exclude,
    )
    return {"token": _store_challenge(conn, options.challenge, "register", uid), "options": json.loads(options_to_json(options))}


def passkey_register_finish(
    conn: sqlite3.Connection, uid: int, token: str, credential: dict, rp_id: str, origin: str, label: str = ""
) -> int:
    from webauthn import verify_registration_response
    from webauthn.helpers import bytes_to_base64url

    challenge = _take_challenge(conn, token, "register", uid)
    try:
        verified = verify_registration_response(
            credential=credential, expected_challenge=challenge, expected_rp_id=rp_id, expected_origin=origin
        )
    except Exception as exc:
        raise AccountError("acct.passkey_failed") from exc
    cid = bytes_to_base64url(verified.credential_id)
    if conn.execute("SELECT 1 FROM passkeys WHERE credential_id = ?", (cid,)).fetchone():
        raise AccountError("acct.passkey_exists")
    cur = conn.execute(
        "INSERT INTO passkeys (user_id, credential_id, public_key, sign_count, label, rp_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            int(uid),
            cid,
            bytes(verified.credential_public_key),
            int(verified.sign_count or 0),
            (label or "Passkey").strip()[:40] or "Passkey",
            rp_id,
            _iso(_now()),
        ),
    )
    return int(cur.lastrowid)


def passkey_login_begin(conn: sqlite3.Connection, rp_id: str) -> dict:
    from webauthn import generate_authentication_options, options_to_json
    from webauthn.helpers.structs import UserVerificationRequirement

    options = generate_authentication_options(rp_id=rp_id, user_verification=UserVerificationRequirement.PREFERRED)
    return {"token": _store_challenge(conn, options.challenge, "login", None), "options": json.loads(options_to_json(options))}


def passkey_login_finish(conn: sqlite3.Connection, token: str, credential: dict, rp_id: str, origin: str):
    from webauthn import verify_authentication_response

    challenge = _take_challenge(conn, token, "login", None)
    cid = str((credential or {}).get("id") or "")
    row = conn.execute("SELECT id, user_id, public_key, sign_count, rp_id FROM passkeys WHERE credential_id = ?", (cid,)).fetchone()
    if row is None or row["rp_id"] != rp_id:
        raise AccountError("acct.passkey_unknown")
    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=bytes(row["public_key"]),
            credential_current_sign_count=int(row["sign_count"] or 0),
        )
    except Exception as exc:
        raise AccountError("acct.passkey_login_failed") from exc
    conn.execute(
        "UPDATE passkeys SET sign_count = ?, last_used = ? WHERE id = ?", (int(verified.new_sign_count or 0), _iso(_now()), row["id"])
    )
    user = get_user(conn, row["user_id"])
    if user is None:
        raise AccountError("acct.no_user")
    return user
