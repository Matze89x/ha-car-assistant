"""Logging in with an account: OAuth 2.0 for a step of the set-up flow (``type: "oauth"``, docs/plugins.md, "Logging in with an account").

The app does the dance - the request for the login (with PKCE), the exchange of the code for tokens, the renewal - so that no plugin has to: it asks the
app for the current access token (``GET /api/v1/vehicles/<id>/connection``) and uses it. Everything that leaves the app goes to the ``token_url`` the package
named: https, a public address, no redirects, a size and a time limit. The tokens are kept sealed (vault.py), never in a log, never in an answer other than
the one to the plugin they belong to. A connection belongs to one package and one step of its flow; the installs linked to it share it (one car, or several
cars of the same account)."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta

from . import addons, connectors, db, vault
from .sources import _public_host

PENDING_SECONDS = 600  # a login that was begun counts for ten minutes
SKEW = 60  # an access token that ends within a minute is renewed before it is handed out
TIMEOUT = 15
LIMIT = 65536  # the most the provider may answer
RENEW_EVERY = 30  # seconds: a plugin that insists (``renew``) renews a connection at most this often
LOGIN_ERRORS = {
    "invalid_grant",
    "invalid_token",
    "unauthorized_client",
    "access_denied",
    "invalid_client",
}  # what means "the person has to log in again"


class OAuthError(Exception):
    """A step of the login failed. ``key`` is a text of i18n.py, ``detail`` what the provider said (short, cleaned, never a token)."""

    def __init__(self, key: str, detail: str = ""):
        super().__init__(key)
        self.key, self.detail = key, detail


class LoginRequired(OAuthError):
    """The tokens are no longer good and cannot be renewed: the person has to log in again."""


class ProviderRefused(OAuthError):
    """The provider answered with an error (``error`` of RFC 6749)."""

    def __init__(self, code: str, detail: str):
        super().__init__("err.oauth_refused", detail)
        self.code = code


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _when(text: str | None) -> datetime | None:
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC) if text else None
    except ValueError:
        return None


def _plain(text) -> str:
    """What the provider said, for the person: one line, no control characters, 200 characters at most."""
    return re.sub(r"[\x00-\x1f\x7f]+", " ", str(text or "")).strip()[:200]


def _challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")


# ------------------------------------------------------------------ what the package says


def step_of(addon: dict, step_id: str) -> dict | None:
    flow = ((addon.get("m") or {}).get("setup") or {}).get("flow") or []
    return next((s for s in flow if s["id"] == step_id and s["type"] == "oauth"), None)


def steps_of(addon: dict) -> list[dict]:
    return [s for s in (((addon.get("m") or {}).get("setup") or {}).get("flow") or []) if s["type"] == "oauth"]


def provider(addon: dict, step: dict) -> dict:
    """The ``oauth`` of the step with the client id (fixed, or the setting the person filled in) and the client secret."""
    spec = step["oauth"]
    vals = addon.get("vals") or {}
    client = spec.get("client_id") or vals.get(spec.get("client_id_setting", ""), "")
    if not client:
        raise OAuthError("err.oauth_client")
    return {
        **spec,
        "client_id": client,
        "client_secret": vals.get(spec.get("client_secret_setting", ""), "") if spec.get("client_secret_setting") else "",
    }


def redirect_uri_of(spec: dict, external: str) -> str:
    """Where the provider sends the person: the fixed address of the package (``paste``: the person copies the address from the bar) or the callback of
    this app under its https address (``app``). Empty = not possible yet (no https address set)."""
    if spec["redirect"] == "paste":
        return spec["redirect_uri"]
    return f"{external.rstrip('/')}/oauth/callback" if external else ""


# ------------------------------------------------------------------ the request


def begin(conn, addon: dict, step: dict, redirect_uri: str) -> str:
    """A login begins: the state of the request and the PKCE verifier are kept for ten minutes; returns the address the person opens at the provider."""
    spec = provider(addon, step)
    conn.execute("DELETE FROM oauth_pending WHERE created < ?", (_iso(_now() - timedelta(seconds=PENDING_SECONDS)),))
    conn.execute("DELETE FROM oauth_pending WHERE addon_pk = ? AND step = ?", (addon["id"], step["id"]))
    state, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    conn.execute(
        "INSERT INTO oauth_pending(state, addon_pk, step, kind, verifier, redirect, created) VALUES(?,?,?,?,?,?,?)",
        (state, addon["id"], step["id"], "code", vault.encrypt(verifier), redirect_uri, _iso(_now())),
    )
    return _authorize_url(spec, state, verifier, redirect_uri)


def _authorize_url(spec: dict, state: str, verifier: str, redirect_uri: str) -> str:
    query = {"response_type": "code", "client_id": spec["client_id"], "redirect_uri": redirect_uri, "state": state}
    if spec["scopes"]:
        query["scope"] = " ".join(spec["scopes"])
    if spec["pkce"]:
        query.update(code_challenge=_challenge(verifier), code_challenge_method="S256")
    query.update(spec.get("extra") or {})
    return spec["authorize_url"] + ("&" if "?" in spec["authorize_url"] else "?") + urllib.parse.urlencode(query)


def pending(conn, addon_pk: int, step_id: str):
    """The login that was begun and not finished (still valid), or None."""
    row = conn.execute("SELECT * FROM oauth_pending WHERE addon_pk = ? AND step = ? AND kind = 'code'", (addon_pk, step_id)).fetchone()
    if row is None:
        return None
    return row if (_when(row["created"]) or _now()) > _now() - timedelta(seconds=PENDING_SECONDS) else None


def pending_url(conn, addon: dict, step: dict) -> str:
    """The address of a login that was begun, again (the page shows it as a link that opens in a new tab)."""
    row = pending(conn, addon["id"], step["id"])
    if row is None:
        return ""
    return _authorize_url(provider(addon, step), row["state"], vault.decrypt(row["verifier"]), row["redirect"])


def parse_pasted(text: str) -> tuple[str, str, str]:
    """``(code, state, error)`` from what the person pasted: the whole address they were sent to, only its query (``code=...&state=...``), or the bare code."""
    text = (text or "").strip()[:4000]
    if not text:
        return "", "", ""
    if "://" in text:
        parts = urllib.parse.urlsplit(text)
        query, fragment = parts.query, parts.fragment
    else:
        query, _, fragment = text.lstrip("?").partition("#")
    fields = {k: v[0] for k, v in urllib.parse.parse_qs(query or fragment).items()}  # (some providers answer in the part after the #)
    if fields.get("code") or fields.get("error"):
        return fields.get("code", ""), fields.get("state", ""), fields.get("error", "")
    if "://" in text or re.search(r"\s", text):
        return "", "", ""  # an address without a code in it
    return text, "", ""  # a bare code


def take(conn, state: str):
    """The login that was begun with this ``state`` - used once: it is gone when this returns (a wrong or old state ends nothing else)."""
    row = conn.execute("SELECT * FROM oauth_pending WHERE state = ? AND kind = 'code'", (state[:100],)).fetchone() if state else None
    if row is None:
        raise OAuthError("err.oauth_state")
    conn.execute("DELETE FROM oauth_pending WHERE state = ?", (row["state"],))
    if (_when(row["created"]) or _now()) <= _now() - timedelta(seconds=PENDING_SECONDS):
        raise OAuthError("err.oauth_state")
    return row


def addon_of(conn, addon_pk: int) -> dict | None:
    row = conn.execute("SELECT vehicle_id FROM vehicle_addons WHERE id = ?", (addon_pk,)).fetchone()
    return addons.get(conn, row["vehicle_id"], addon_pk) if row else None


def finish(state: str, code: str, expect: tuple[int, str] | None = None) -> dict:
    """The login ends: the code becomes tokens (ONE request to the token address of the package) and is saved. ``expect`` = (install, step) when the person
    pasted the address on that step's page: the state must belong to exactly that. Raises ``OAuthError``; returns the install."""
    with db.tx() as conn:
        row = take(conn, state)  # gone from now on, whatever follows
        addon = addon_of(conn, row["addon_pk"])
        step = step_of(addon, row["step"]) if addon else None
        if step is None or (expect is not None and (row["addon_pk"], row["step"]) != expect):
            raise OAuthError("err.oauth_state")
        spec = provider(addon, step)
        verifier = vault.decrypt(row["verifier"])
    tokens = exchange(spec, code, verifier, row["redirect"])
    with db.tx() as conn:
        save(conn, addon, step["id"], tokens)
        connectors.write_logs(
            conn, addon["vehicle_id"], addon["addon_id"], [(connectors._now(), "info", "app", "logged in with an account")]
        )
    return addon


# ------------------------------------------------------------------ the provider


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # the provider answers itself; it never sends the tokens' request elsewhere
        return None


def _opener():
    return urllib.request.build_opener(_NoRedirect)


def _send(url: str, body: bytes, headers: dict[str, str]) -> tuple[int, bytes]:
    """The one place a request leaves the app for a provider: ``(status, at most 64 kB of the answer)``."""
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")  # noqa: S310 - https only, checked by the caller
    try:
        with _opener().open(request, timeout=TIMEOUT) as answer:
            return answer.status, answer.read(LIMIT + 1)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(LIMIT + 1)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise OAuthError("err.oauth_net") from exc


def _post(url: str, form: dict[str, str], basic: tuple[str, str] | None = None) -> dict:
    """One request to the token address of the package: https, a public address, no redirect, 64 kB, 15 seconds. Returns the JSON object it answered."""
    host = urllib.parse.urlsplit(url).hostname or ""
    if not url.startswith("https://") or not _public_host(host):
        raise OAuthError("err.oauth_host")
    headers = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json", "User-Agent": "car-assistant"}
    if basic:
        pair = f"{urllib.parse.quote(basic[0], safe='')}:{urllib.parse.quote(basic[1], safe='')}"
        headers["Authorization"] = "Basic " + base64.b64encode(pair.encode()).decode()
    status, raw = _send(url, urllib.parse.urlencode(form).encode(), headers)
    if len(raw) > LIMIT:
        raise OAuthError("err.oauth_big")
    try:
        data = json.loads(raw or b"{}")
    except ValueError:
        data = None
    if not isinstance(data, dict):
        raise OAuthError("err.oauth_bad", _plain(status))
    if status >= 300 or data.get("error"):  # (a redirect is no answer: it is never followed)
        raise ProviderRefused(
            _plain(data.get("error")) or str(status), _plain(data.get("error_description") or data.get("error") or status)
        )
    return data


def _client_form(spec: dict, form: dict[str, str]) -> tuple[dict[str, str], tuple[str, str] | None]:
    """The client's own credentials, the way the package said they travel: in the body (``post``) or as Basic authentication (``basic``)."""
    if not spec["client_secret"]:
        return {**form, "client_id": spec["client_id"]}, None
    if spec["client_auth"] == "basic":
        return form, (spec["client_id"], spec["client_secret"])
    return {**form, "client_id": spec["client_id"], "client_secret": spec["client_secret"]}, None


def _tokens(data: dict) -> dict:
    """What a token answer is kept as: the access token (required), the refresh token, the type, the scope and when the access token ends."""
    access = data.get("access_token")
    if not (isinstance(access, str) and 0 < len(access) <= 8000):
        raise OAuthError("err.oauth_bad")
    refresh = data.get("refresh_token")
    out = {
        "access_token": access,
        "refresh_token": refresh if isinstance(refresh, str) and 0 < len(refresh) <= 8000 else "",
        "token_type": _plain(data.get("token_type") or "Bearer")[:20] or "Bearer",
        "scope": _plain(data.get("scope"))[:300],
    }
    life = data.get("expires_in")
    if isinstance(life, str) and life.isdigit():
        life = int(life)
    if isinstance(life, int | float) and not isinstance(life, bool) and 0 < life < 10 * 365 * 86400:
        out["expires_at"] = _iso(_now() + timedelta(seconds=int(life)))
    return out


def exchange(spec: dict, code: str, verifier: str, redirect_uri: str) -> dict:
    """The code for tokens at the token address of the package."""
    form = {"grant_type": "authorization_code", "code": code[:2000], "redirect_uri": redirect_uri}
    if spec["pkce"]:
        form["code_verifier"] = verifier
    body, basic = _client_form(spec, form)
    return _tokens(_post(spec["token_url"], body, basic))


# ------------------------------------------------------------------ the connection


def save(conn, addon: dict, step_id: str, tokens: dict) -> int:
    """The tokens of a login: into the connection this install is linked to (the others that share it get them, too), or a new one."""
    expires = tokens.get("expires_at")
    secret = vault.encrypt(json.dumps({k: v for k, v in tokens.items() if k != "expires_at"}))
    link = conn.execute("SELECT connection_id FROM connection_links WHERE addon_pk = ? AND step = ?", (addon["id"], step_id)).fetchone()
    if link:
        conn.execute(
            "UPDATE connections SET secret = ?, expires_at = ?, state = 'ok', error = '', updated = ? WHERE id = ?",
            (secret, expires, _iso(_now()), link["connection_id"]),
        )
        return link["connection_id"]
    cid = conn.execute(
        "INSERT INTO connections(plugin, step, secret, expires_at, state, error, updated) VALUES(?,?,?,?, 'ok', '', ?)",
        (addon["addon_id"], step_id, secret, expires, _iso(_now())),
    ).lastrowid
    conn.execute("INSERT INTO connection_links(addon_pk, step, connection_id) VALUES(?,?,?)", (addon["id"], step_id, cid))
    return cid


def status(conn, addon_pk: int, step_id: str) -> dict:
    """``{"connected": bool, "state": "ok" | "login_required", "expires_at", "error", "id"}`` of the install's connection."""
    row = conn.execute(
        "SELECT c.id, c.state, c.error, c.expires_at, c.secret FROM connection_links l JOIN connections c ON c.id = l.connection_id "
        "WHERE l.addon_pk = ? AND l.step = ?",
        (addon_pk, step_id),
    ).fetchone()
    if row is None or not row["secret"]:
        return {"connected": False, "state": "none", "expires_at": None, "error": "", "id": None}
    state = (
        row["state"] if vault.decrypt(row["secret"]) else "login_required"
    )  # tokens sealed by another system (a backup without a passphrase) are none here
    return {"connected": state == "ok", "state": state, "expires_at": row["expires_at"], "error": row["error"], "id": row["id"]}


def login_needed(conn, addon_pk: int) -> bool:
    """Does a connection of this install need the person to log in again?"""
    return bool(
        conn.execute(
            "SELECT 1 FROM connection_links l JOIN connections c ON c.id = l.connection_id WHERE l.addon_pk = ? AND c.state = 'login_required'",
            (addon_pk,),
        ).fetchone()
    )


def forget(conn, addon_pk: int, step_id: str | None = None) -> None:
    """The install lets go of its connection (all of them, or one step's); a connection nobody uses any more is deleted with its tokens."""
    if step_id is None:
        conn.execute("DELETE FROM connection_links WHERE addon_pk = ?", (addon_pk,))
    else:
        conn.execute("DELETE FROM connection_links WHERE addon_pk = ? AND step = ?", (addon_pk, step_id))
    prune(conn)


def prune(conn) -> None:
    conn.execute("DELETE FROM connections WHERE id NOT IN (SELECT connection_id FROM connection_links)")


def export(conn, addon_pk: int) -> dict[str, dict]:
    """The connections of one install for the secrets block of a backup: ``{step: {"secret": the tokens as text, "expires_at", "state"}}``."""
    out: dict[str, dict] = {}
    for row in conn.execute(
        "SELECT l.step, c.secret, c.expires_at, c.state FROM connection_links l JOIN connections c ON c.id = l.connection_id WHERE l.addon_pk = ?",
        (addon_pk,),
    ):
        if text := vault.decrypt(row["secret"]):
            out[row["step"]] = {"secret": text, "expires_at": row["expires_at"], "state": row["state"]}
    return out


def restore(conn, vehicle_id: int, addon_id: str, steps) -> None:
    """The connections of a backup into the install of a car: only for steps the package has, only tokens that look like tokens; each becomes a
    connection of its own (a sharing of the old system is not brought back)."""
    row = conn.execute("SELECT id FROM vehicle_addons WHERE vehicle_id = ? AND addon_id = ?", (vehicle_id, addon_id)).fetchone()
    addon = addons.get(conn, vehicle_id, row["id"]) if row else None
    if addon is None or not isinstance(steps, dict):
        return
    for step_id, entry in steps.items():
        if not (isinstance(entry, dict) and isinstance(entry.get("secret"), str) and step_of(addon, str(step_id))):
            continue
        try:
            tokens = json.loads(entry["secret"])
        except ValueError:
            continue
        if not (isinstance(tokens, dict) and isinstance(tokens.get("access_token"), str) and tokens["access_token"]):
            continue
        kept = {k: tokens[k] for k in ("access_token", "refresh_token", "token_type", "scope") if isinstance(tokens.get(k), str)}
        if _when(entry.get("expires_at")):
            kept["expires_at"] = entry["expires_at"]
        cid = save(conn, addon, str(step_id), kept)
        if entry.get("state") == "login_required":
            conn.execute("UPDATE connections SET state = 'login_required' WHERE id = ?", (cid,))


def _read(secret: str) -> dict:
    """The tokens of a connection; ``{}`` when they cannot be read (sealed by another system)."""
    try:
        data = json.loads(vault.decrypt(secret) or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


_locks: dict[int, threading.Lock] = {}
_renewed: dict[int, float] = {}


def _provider_of(conn, connection_id: int) -> dict | None:
    """The provider settings of a connection: read from an install linked to it (the manifest names the addresses, the settings the client)."""
    for link in conn.execute("SELECT addon_pk, step FROM connection_links WHERE connection_id = ?", (connection_id,)).fetchall():
        row = conn.execute("SELECT vehicle_id FROM vehicle_addons WHERE id = ?", (link["addon_pk"],)).fetchone()
        addon = addons.get(conn, row["vehicle_id"], link["addon_pk"]) if row else None
        step = step_of(addon, link["step"]) if addon else None
        if step:
            return provider(addon, step)
    return None


def _mark(connection_id: int, state: str, error: str) -> None:
    with db.tx() as conn:
        conn.execute(
            "UPDATE connections SET state = ?, error = ?, updated = ? WHERE id = ?", (state, error[:200], _iso(_now()), connection_id)
        )


def fresh(connection_id: int, renew: bool = False) -> dict:
    """The access token of a connection, renewed first when it ends within a minute (or when ``renew`` says the provider refused it). Raises
    ``LoginRequired`` when the person has to log in again, ``OAuthError`` when the provider could not be reached (try again later). The answer holds
    no refresh token: a plugin has no use for it."""
    lock = _locks.setdefault(connection_id, threading.Lock())  # two plugins of one account do not renew at the same moment
    with lock:
        with db.tx() as conn:
            row = conn.execute("SELECT * FROM connections WHERE id = ?", (connection_id,)).fetchone()
            spec = _provider_of(conn, connection_id) if row else None
        if row is None or spec is None or not row["secret"]:
            raise OAuthError("err.oauth_none")
        if row["state"] != "ok":
            raise LoginRequired("err.oauth_expired", row["error"])
        tokens = _read(row["secret"])
        if not tokens.get("access_token"):  # sealed by another system: nothing to use
            _mark(connection_id, "login_required", "")
            raise LoginRequired("err.oauth_expired")
        expires = _when(row["expires_at"])
        due = expires is not None and expires - _now() <= timedelta(seconds=SKEW)
        if renew and time.monotonic() - _renewed.get(connection_id, -RENEW_EVERY) < RENEW_EVERY:
            renew = False  # asked a moment ago: the answer of that time is the freshest there is
        if due or renew:
            if not tokens.get("refresh_token"):
                if expires is not None and expires <= _now():
                    _mark(connection_id, "login_required", "")
                    raise LoginRequired("err.oauth_expired")
            else:
                tokens, expires = _renew(connection_id, spec, tokens)
                _renewed[connection_id] = time.monotonic()
        return {
            "access_token": tokens["access_token"],
            "token_type": tokens.get("token_type") or "Bearer",
            "scope": tokens.get("scope", ""),
            "expires_at": _iso(expires) if expires else None,
            "expires_in": max(0, int((expires - _now()).total_seconds())) if expires else None,
        }


def _renew(connection_id: int, spec: dict, tokens: dict) -> tuple[dict, datetime | None]:
    body, basic = _client_form(spec, {"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]})
    try:
        got = _tokens(_post(spec["token_url"], body, basic))
    except ProviderRefused as exc:
        if exc.code in LOGIN_ERRORS:  # the person has to log in again: every install that shares the connection shows it
            _mark(connection_id, "login_required", exc.detail)
            raise LoginRequired("err.oauth_expired", exc.detail) from exc
        raise
    got["refresh_token"] = got["refresh_token"] or tokens["refresh_token"]  # a provider that does not rotate leaves the old one valid
    expires = _when(got.pop("expires_at", None))
    with db.tx() as conn:
        conn.execute(
            "UPDATE connections SET secret = ?, expires_at = ?, state = 'ok', error = '', updated = ? WHERE id = ?",
            (vault.encrypt(json.dumps(got)), _iso(expires) if expires else None, _iso(_now()), connection_id),
        )
    return got, expires
