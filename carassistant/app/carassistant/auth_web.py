"""Login, first-run access choice and account management (routes). See accounts.py for the logic.

Rule: the Home Assistant panel (Ingress) never needs a login. Direct access (published port, reverse proxy)
is blocked until an account exists and always requires a login afterwards.
"""

from __future__ import annotations

import sqlite3
import time
from urllib.parse import urlparse

from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from . import __version__, accounts, config, db, i18n
from . import icons as icon_set
from .web import app, go, render, templates

COOKIE = "ca_session"
SETUP_KEY = "setup.access_done"
PUBLIC_PATHS = {
    "/favicon.ico",
    "/apple-touch-icon.png",  # iOS asks for these two on its own (home screen) - also while nobody is signed in
    "/apple-touch-icon-precomposed.png",
    "/healthz",
    "/login",
    "/login/passkey/options",
    "/login/passkey/verify",
    "/manifest.webmanifest",
    "/sw.js",  # the service worker of web push: the browser fetches it without a session
}
PUBLIC_PREFIXES = ("/static/", "/icon/", "/.well-known/")  # the last one answers a plain 404 (MCP clients look for an OAuth server there)
LOCK_AFTER, LOCK_SECONDS = 5, 15 * 60  # defaults; the server settings (Settings -> System) override them
_failures: dict[str, list[float]] = {}  # failed logins per address
_name_failures: dict[str, list[float]] = {}  # ... and per user name, so many addresses cannot guess one account


def lock_after() -> int:
    value = config.stored_setting("security.lock_after") or ""
    return int(value) if value.isdigit() and 2 <= int(value) <= 20 else LOCK_AFTER


def lock_seconds() -> int:
    value = config.stored_setting("security.lock_minutes") or ""
    return int(value) * 60 if value.isdigit() and 1 <= int(value) <= 1440 else LOCK_SECONDS


# ------------------------------------------------------------------ helpers used by the guard


# Settings of the whole system: only an administrator may read or change them from outside (a signed-in user keeps their own preferences,
# notifications and list size). The backup holds everything - users, tokens, all cars - and a restore replaces it.
ADMIN_ONLY = frozenset(
    {
        "/settings/backup.zip",
        "/settings/restore",
        "/settings/reset",
        "/settings/external-url",
        "/settings/map",
        "/settings/tankerkoenig",
        "/settings/logs",
        "/settings/sources-auto",
        "/settings/refresh-live",
        "/settings/republish",
        "/settings/units",
        "/settings/language",
        "/settings/theme",
        "/settings/accent",
    }
)


def admin_only(path: str) -> bool:
    return path.rstrip("/") in ADMIN_ONLY or path.startswith("/settings/mcp/")  # MCP: the level and the access keys


def is_public(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _left(table: dict[str, list[float]], key: str) -> int:
    """Seconds left of the lock of one address / name, 0 if it is not locked."""
    now = time.time()
    window = lock_seconds()
    hits = [t for t in table.get(key, []) if now - t < window]
    table[key] = hits
    if len(hits) >= lock_after():
        return int(window - (now - hits[-1])) if now - hits[-1] < window else 0
    return 0


def _locked(ip: str, name: str = "") -> int:
    """Seconds left of the lock, 0 if neither the address nor the user name is locked."""
    return max(_left(_failures, ip), _left(_name_failures, name.strip().lower()) if name else 0)


def _fail(ip: str, name: str = "") -> None:
    _failures.setdefault(ip, []).append(time.time())
    if name.strip():
        _name_failures.setdefault(name.strip().lower(), []).append(time.time())


def _ok(ip: str, name: str = "") -> None:
    _failures.pop(ip, None)
    _name_failures.pop(name.strip().lower(), None)


def blocked() -> list[dict]:
    """Everything that is locked right now (addresses and user names) with the minutes left - the administrator can release them."""
    out = []
    for kind, table in (("ip", _failures), ("name", _name_failures)):
        for key in list(table):
            left = _left(table, key)
            if left:
                out.append({"kind": kind, "key": key, "minutes": left // 60 + 1})
    return out


def release(kind: str = "", key: str = "") -> None:
    """Release one lock, or every lock (no arguments)."""
    for k, table in (("ip", _failures), ("name", _name_failures)):
        if not kind:
            table.clear()
        elif kind == k:
            table.pop(key, None)


def _safe_next(value: str | None) -> str:
    value = (value or "/").strip()
    if not value.startswith("/") or value.startswith("//") or "\\" in value or "\n" in value or "\r" in value:
        return "/"
    return value


def _secure(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("X-Forwarded-Proto", "").split(",")[0].strip() == "https"


def _set_cookie(response, request: Request, token: str):
    response.set_cookie(
        COOKIE, token, max_age=accounts.SESSION_DAYS * 86400, httponly=True, samesite="lax", secure=_secure(request), path="/"
    )
    return response


def _is_external(request: Request) -> bool:
    return bool(getattr(request.state, "external", False))


def _acting_user(request: Request, conn: sqlite3.Connection):
    """Signed-in user on direct access; in the Home Assistant panel the administrator (Home Assistant already authenticated the person)."""
    user = getattr(request.state, "user", None)
    if user is not None:
        return user
    if _is_external(request):
        return None
    admin = accounts.admin_id(conn)
    return accounts.get_user(conn, admin) if admin else None


def _rp(request: Request) -> tuple[str, str]:
    """(rp_id, origin) of the address the browser uses; the configured external URL wins."""
    if config.external_url():
        parsed = urlparse(config.external_url())
        return parsed.hostname or "", f"{parsed.scheme}://{parsed.netloc}"
    host = (request.headers.get("X-Forwarded-Host") or request.headers.get("Host") or "").split(",")[0].strip().lower()
    return host.split(":")[0], f"{'https' if _secure(request) else 'http'}://{host}"


def _translate(key: str) -> str:
    return i18n.translator(config.language())(key)


def _login_page(request: Request, status: int = 200, **ctx):
    t = i18n.translator(config.language())
    return templates.TemplateResponse(
        request,
        "login.html",
        dict(
            ctx,
            _=t,
            icons=icon_set.ICONS,
            version=__version__,
            lang=config.language(),
            base=request.state.base,
            icon_base=f"{request.state.base}/icon",
            icon_rev=0,
            manifest_url=f"{request.state.base}/manifest.webmanifest",
            next=ctx.get("next", "/"),
        ),
        status_code=status,
    )


# ------------------------------------------------------------------ login / logout


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/"):
    if not _is_external(request):
        return RedirectResponse(f"{request.state.base}/", status_code=303)
    if getattr(request.state, "user", None) is not None:
        return RedirectResponse(_safe_next(next), status_code=303)
    return _login_page(request, next=_safe_next(next))


@app.post("/login")
async def login_submit(request: Request):
    form = await request.form()
    nxt = _safe_next(str(form.get("next") or "/"))
    ip = _client_ip(request)
    t = i18n.translator(config.language())
    name = str(form.get("username") or "")
    left = _locked(ip, name)
    if left:
        return _login_page(request, 429, error=t("acct.locked").replace("{min}", str(left // 60 + 1)), next=nxt)
    with db.tx() as conn:
        user = accounts.authenticate(conn, str(form.get("username") or ""), str(form.get("password") or ""))
        if user is None:
            _fail(ip, name)
            return _login_page(request, 401, error=t("acct.login_bad"), next=nxt)
        token = accounts.create_session(conn, user["id"], "password")
    _ok(ip, name)
    return _set_cookie(RedirectResponse(nxt, status_code=303), request, token)


@app.post("/logout")
def logout(request: Request):
    with db.tx() as conn:
        accounts.delete_session(conn, request.cookies.get(COOKIE))
    response = RedirectResponse(
        f"{request.state.base}/login" if _is_external(request) else f"{request.state.base}/settings", status_code=303
    )
    response.delete_cookie(COOKIE, path="/")
    return response


@app.post("/login/passkey/options")
def login_passkey_options(request: Request):
    if not _is_external(request):
        return JSONResponse({"ok": False, "error": _translate("acct.passkey_external")}, status_code=400)
    if left := _locked(_client_ip(request)):
        return JSONResponse({"ok": False, "error": _translate("acct.locked").replace("{min}", str(left // 60 + 1))}, status_code=429)
    rp_id, _origin = _rp(request)
    with db.tx() as conn:
        return JSONResponse(dict(accounts.passkey_login_begin(conn, rp_id), ok=True))


@app.post("/login/passkey/verify")
async def login_passkey_verify(request: Request):
    ip = _client_ip(request)
    if left := _locked(ip):
        return JSONResponse({"ok": False, "error": _translate("acct.locked").replace("{min}", str(left // 60 + 1))}, status_code=429)
    try:
        body = await request.json()
        rp_id, origin = _rp(request)

        def work():
            with db.tx() as conn:
                user = accounts.passkey_login_finish(conn, str(body.get("token") or ""), body.get("credential") or {}, rp_id, origin)
                return accounts.create_session(conn, user["id"], "passkey")

        token = await run_in_threadpool(work)
    except accounts.AccountError as exc:
        _fail(ip)
        return JSONResponse({"ok": False, "error": _translate(exc.key)}, status_code=401)
    except (ValueError, TypeError, AttributeError):
        _fail(ip)
        return JSONResponse({"ok": False, "error": _translate("acct.passkey_login_failed")}, status_code=400)
    _ok(ip)
    return _set_cookie(JSONResponse({"ok": True, "next": _safe_next(str(body.get("next") or "/"))}), request, token)


# ------------------------------------------------------------------ first-run: access choice


def setup_pending(conn: sqlite3.Connection) -> bool:
    return db.get_setting(conn, SETUP_KEY) != "1"


@app.get("/setup/access", response_class=HTMLResponse)
def setup_access_page(request: Request, next: str = "/"):
    with db.tx() as conn:
        if accounts.has_users(conn):
            return RedirectResponse(f"{request.state.base}{_safe_next(next)}", status_code=303)
    return render(request, "setup_access.html", next=_safe_next(next), tab=None, v=None, error=request.query_params.get("e"))


@app.post("/setup/access")
async def setup_access_submit(request: Request):
    form = await request.form()
    nxt = _safe_next(str(form.get("next") or "/"))
    choice = str(form.get("choice") or "local")
    with db.tx() as conn:
        if choice == "external" and not accounts.has_users(conn):
            if str(form.get("password") or "") != str(form.get("password2") or ""):
                return go(request, f"/setup/access?next={nxt}", "acct.pw_mismatch")
            try:
                accounts.create_user(conn, str(form.get("username") or ""), str(form.get("password") or ""), admin=True)
            except accounts.AccountError as exc:
                return go(request, f"/setup/access?next={nxt}", exc.key)
        db.set_setting(conn, SETUP_KEY, "1")
    return go(request, nxt, "acct_created" if choice == "external" else "setup_done")


# ------------------------------------------------------------------ account management (Settings)


def _port_state() -> str:
    """ "on" (a port is set: direct access exists), "off" (no port: only the Home Assistant panel) or "unknown" (Home Assistant does not answer)."""
    from . import ha

    known, port = ha.network_port()
    return "unknown" if not known else "off" if port is None else "on"


def account_context(request: Request, conn: sqlite3.Connection) -> dict:
    me = _acting_user(request, conn)
    external = _is_external(request)
    return {
        "acct_has_users": accounts.has_users(conn),
        "acct_me": me,
        "acct_is_admin": bool(me and me["is_admin"]),
        "acct_users": accounts.list_users(conn) if me and me["is_admin"] else [],
        "acct_passkeys": accounts.passkey_list(conn, me["id"]) if me else [],
        "acct_external": external,
        "acct_port": _port_state(),
        "acct_signed_in": getattr(request.state, "user", None) is not None,
        "acct_strict": accounts.strict(),
        "acct_has_pin": bool(me and accounts.has_passcode(conn, me["id"])),
        "acct_lock_choices": accounts.LOCK_CHOICES,
        "acct_lock_minutes": (me and conn.execute("SELECT lock_minutes FROM users WHERE id = ?", (me["id"],)).fetchone()["lock_minutes"])
        or 15,
    }


def _admin_ok(request: Request) -> bool:
    user = getattr(request.state, "user", None)
    return not _is_external(request) or bool(user and user["is_admin"])


@app.post("/settings/security")
async def settings_security(request: Request):
    """Server setting: how many wrong logins lock an address / a name, and for how long."""
    if not _admin_ok(request):
        return go(request, "/settings/system", "acct.need_admin")
    form = await request.form()
    after, minutes = str(form.get("lock_after") or ""), str(form.get("lock_minutes") or "")
    with db.tx() as conn:
        db.set_setting(conn, "security.lock_after", after if after.isdigit() and 2 <= int(after) <= 20 else None)
        db.set_setting(conn, "security.lock_minutes", minutes if minutes.isdigit() and 1 <= int(minutes) <= 1440 else None)
    return go(request, "/settings/system", "saved")


@app.post("/settings/unblock")
async def settings_unblock(request: Request):
    """Release a locked address / user name (or all of them)."""
    if not _admin_ok(request):
        return go(request, "/settings/user", "acct.need_admin")
    form = await request.form()
    release(str(form.get("kind") or ""), str(form.get("key") or ""))
    return go(request, "/settings/user#blocked", "unblocked")


_pin_fail: dict[str, int] = {}


@app.get("/unlock", response_class=HTMLResponse)
def unlock_page(request: Request, next: str = "/"):
    user = getattr(request.state, "user", None)
    if user is None or not accounts.is_locked(user):
        return RedirectResponse(f"{request.state.base}{_safe_next(next)}", status_code=303)
    return _unlock_page(request, name=user["username"], next=_safe_next(next))


def _unlock_page(request: Request, status: int = 200, **ctx):
    t = i18n.translator(config.language())
    return templates.TemplateResponse(
        request,
        "unlock.html",
        dict(
            ctx,
            _=t,
            icons=icon_set.ICONS,
            version=__version__,
            lang=config.language(),
            base=request.state.base,
            icon_base=f"{request.state.base}/icon",
            icon_rev=0,
            manifest_url=f"{request.state.base}/manifest.webmanifest",
        ),
        status_code=status,
    )


@app.post("/unlock")
async def unlock_submit(request: Request):
    """The passcode opens a locked device again. Five wrong codes sign the device out (a full login is needed)."""
    user = getattr(request.state, "user", None)
    if user is None:
        return RedirectResponse(f"{request.state.base}/login", status_code=303)
    form = await request.form()
    nxt = _safe_next(str(form.get("next") or "/"))
    token = request.cookies.get(COOKIE) or ""
    key = token[:16]
    t = i18n.translator(config.language())
    with db.tx() as conn:
        if accounts.verify_passcode(conn, user["id"], str(form.get("code") or "")):
            accounts.mark_active(conn, token)
            _pin_fail.pop(key, None)
            return RedirectResponse(f"{request.state.base}{nxt}", status_code=303)
        _pin_fail[key] = _pin_fail.get(key, 0) + 1
        if _pin_fail[key] >= 5:
            accounts.delete_session(conn, token)
            _pin_fail.pop(key, None)
            response = RedirectResponse(f"{request.state.base}/login", status_code=303)
            response.delete_cookie(COOKIE, path="/")
            return response
    return _unlock_page(request, 401, name=user["username"], next=nxt, error=t("acct.pin_wrong"))


@app.post("/account/passcode")
async def account_passcode(request: Request):
    form = await request.form()
    try:
        with db.tx() as conn:
            me = _acting_user(request, conn)
            if me is None or getattr(request.state, "user", None) is None:
                raise accounts.AccountError("acct.pin_session")
            if str(form.get("code") or "") != str(form.get("code2") or ""):
                raise accounts.AccountError("acct.pw_mismatch")
            if not accounts._own_password_ok(conn, me["id"], str(form.get("current") or "")):
                raise accounts.AccountError("acct.pw_wrong")
            minutes = str(form.get("minutes") or "15")
            accounts.set_passcode(conn, me["id"], str(form.get("code") or ""), int(minutes) if minutes.isdigit() else 15)
            accounts.mark_active(conn, request.cookies.get(COOKIE))
    except accounts.AccountError as exc:
        return _back(request, exc.key, "#passcode")
    return _back(request, "pin_set", "#passcode")


@app.post("/account/passcode/remove")
def account_passcode_remove(request: Request):
    with db.tx() as conn:
        me = _acting_user(request, conn)
        if me is not None:
            accounts.clear_passcode(conn, me["id"])
    return _back(request, "pin_removed", "#passcode")


@app.post("/account/lock")
def account_lock(request: Request):
    """Lock this device right now (it asks for the passcode at the next step)."""
    with db.tx() as conn:
        accounts.lock_session(conn, request.cookies.get(COOKIE))
    return RedirectResponse(f"{request.state.base}/unlock", status_code=303)


@app.post("/account/signout-all")
def account_signout_all(request: Request):
    with db.tx() as conn:
        me = _acting_user(request, conn)
        if me is not None:
            accounts.delete_user_sessions(conn, me["id"], request.cookies.get(COOKIE))
    return _back(request, "signed_out_all", "#account")


def _back(request: Request, msg: str, anchor: str = "") -> RedirectResponse:
    return go(request, "/settings/user" + anchor, msg)


def _need_admin(request: Request, conn: sqlite3.Connection):
    me = _acting_user(request, conn)
    if me is None or not me["is_admin"]:
        raise accounts.AccountError("acct.need_admin")
    return me


@app.post("/account/create")
async def account_create(request: Request):
    """First account (administrator) from the Home Assistant panel; afterwards direct access works with a login."""
    form = await request.form()
    if str(form.get("password") or "") != str(form.get("password2") or ""):
        return _back(request, "acct.pw_mismatch", "#account")
    try:
        with db.tx() as conn:
            if accounts.has_users(conn):
                raise accounts.AccountError("acct.need_admin")
            accounts.create_user(conn, str(form.get("username") or ""), str(form.get("password") or ""), admin=True)
            db.set_setting(conn, SETUP_KEY, "1")
    except accounts.AccountError as exc:
        return _back(request, exc.key, "#account")
    return _back(request, "acct_created", "#account")


@app.post("/account/password")
async def account_password(request: Request):
    form = await request.form()
    if str(form.get("new") or "") != str(form.get("new2") or ""):
        return _back(request, "acct.pw_mismatch", "#account")
    try:
        with db.tx() as conn:
            me = _acting_user(request, conn)
            if me is None:
                raise accounts.AccountError("acct.no_user")
            token = request.cookies.get(COOKIE)
            trusted = (not _is_external(request)) or accounts.strong_session(conn, token)
            accounts.change_password(conn, me["id"], str(form.get("current") or ""), str(form.get("new") or ""), token, trusted=trusted)
    except accounts.AccountError as exc:
        return _back(request, exc.key, "#account")
    return _back(request, "pw_changed", "#account")


@app.post("/account/username")
async def account_username(request: Request):
    form = await request.form()
    try:
        with db.tx() as conn:
            me = _acting_user(request, conn)
            if me is None:
                raise accounts.AccountError("acct.no_user")
            accounts.change_username(
                conn, me["id"], str(form.get("current") or ""), str(form.get("new") or ""), trusted=not _is_external(request)
            )
    except accounts.AccountError as exc:
        return _back(request, exc.key, "#account")
    return _back(request, "name_changed", "#account")


@app.post("/account/users/add")
async def account_user_add(request: Request):
    form = await request.form()
    try:
        with db.tx() as conn:
            _need_admin(request, conn)
            accounts.create_user(
                conn, str(form.get("username") or ""), str(form.get("password") or ""), str(form.get("display_name") or "")
            )
    except accounts.AccountError as exc:
        return _back(request, exc.key, "#account")
    return _back(request, "user_added", "#account")


@app.post("/account/users/{uid}/delete")
def account_user_delete(request: Request, uid: int):
    try:
        with db.tx() as conn:
            me = _need_admin(request, conn)
            accounts.delete_user(conn, uid, me["id"])
    except accounts.AccountError as exc:
        return _back(request, exc.key, "#account")
    return _back(request, "user_deleted", "#account")


@app.post("/account/users/{uid}/password")
async def account_user_password(request: Request, uid: int):
    form = await request.form()
    try:
        with db.tx() as conn:
            _need_admin(request, conn)
            accounts.admin_set_password(conn, uid, str(form.get("new") or ""))
    except accounts.AccountError as exc:
        return _back(request, exc.key, "#account")
    return _back(request, "pw_changed", "#account")


@app.post("/account/users/{uid}/passkeys/clear")
def account_user_passkeys_clear(request: Request, uid: int):
    try:
        with db.tx() as conn:
            _need_admin(request, conn)
            accounts.passkeys_clear(conn, uid)
    except accounts.AccountError as exc:
        return _back(request, exc.key, "#account")
    return _back(request, "passkey_removed", "#account")


@app.post("/account/passkey/options")
def account_passkey_options(request: Request):
    if not _is_external(request) and not config.dev_mode():
        return JSONResponse({"ok": False, "error": _translate("acct.passkey_external")}, status_code=400)
    rp_id, _origin = _rp(request)
    with db.tx() as conn:
        me = _acting_user(request, conn)
        if me is None:
            return JSONResponse({"ok": False, "error": _translate("acct.no_user")}, status_code=400)
        return JSONResponse(dict(accounts.passkey_register_begin(conn, me["id"], rp_id), ok=True))


@app.post("/account/passkey/register")
async def account_passkey_register(request: Request):
    if not _is_external(request) and not config.dev_mode():
        return JSONResponse({"ok": False, "error": _translate("acct.passkey_external")}, status_code=400)
    try:
        body = await request.json()
        rp_id, origin = _rp(request)

        def work():
            with db.tx() as conn:
                me = _acting_user(request, conn)
                if me is None:
                    raise accounts.AccountError("acct.no_user")
                return accounts.passkey_register_finish(
                    conn, me["id"], str(body.get("token") or ""), body.get("credential") or {}, rp_id, origin, str(body.get("label") or "")
                )

        await run_in_threadpool(work)
    except accounts.AccountError as exc:
        return JSONResponse({"ok": False, "error": _translate(exc.key)}, status_code=400)
    except (ValueError, TypeError, AttributeError):
        return JSONResponse({"ok": False, "error": _translate("acct.passkey_failed")}, status_code=400)
    return JSONResponse({"ok": True})


@app.post("/account/passkey/{pk_id}/delete")
def account_passkey_delete(request: Request, pk_id: int):
    with db.tx() as conn:
        me = _acting_user(request, conn)
        if me is not None:
            accounts.passkey_delete(conn, me["id"], pk_id)
    return _back(request, "passkey_removed", "#account")
