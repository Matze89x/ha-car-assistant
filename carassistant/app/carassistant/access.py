"""Direct access (the published port / a reverse proxy) - as opposed to the Home Assistant panel (ingress), which is always allowed.

There is nothing to choose: the port is off by default (Home Assistant: Network). Once someone sets it, the app is reachable directly, and a user
(name + password or passkey) must exist and sign in. Without any user the direct address only shows a page that says so.
The public routes of a plugin's service are not covered (they are public on purpose: a device calls them).
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse

from . import accounts, config, db, i18n

_PAGE_CSS = """
*{box-sizing:border-box}html,body{height:100%}
body{margin:0;display:grid;place-items:center;padding:24px;color:#f2f3f5;background:#0d1016;
 font-family:"Space Grotesk",ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
 background-image:radial-gradient(60% 55% at 8% 0%,rgba(226,0,26,.32),transparent 70%),radial-gradient(55% 50% at 100% 100%,rgba(74,222,128,.16),transparent 70%)}
body::after{content:"";position:fixed;left:0;right:0;bottom:0;height:5px;background:linear-gradient(90deg,#e2001a,#4ade80)}
.card{width:min(100%,460px);text-align:center;padding:30px 26px 26px;border-radius:28px;border:1px solid rgba(255,255,255,.1);
 background:linear-gradient(180deg,rgba(255,255,255,.07),rgba(255,255,255,.025));box-shadow:0 20px 60px rgba(0,0,0,.45),0 0 70px rgba(226,0,26,.12);backdrop-filter:blur(14px)}
.logo{width:150px;height:150px;margin:0 auto 8px}.logo svg{width:100%;height:100%;display:block;filter:drop-shadow(0 0 24px rgba(226,0,26,.3))}
h1{margin:6px 0 2px;font-size:30px;letter-spacing:.01em}h1 span{color:#e2001a}
.slogan{margin:0 0 18px;font-size:12px;letter-spacing:.2em;text-transform:uppercase;color:#4ade80}
.badge{display:inline-flex;align-items:center;gap:8px;padding:7px 14px;border-radius:999px;font-size:13px;font-weight:600;color:#f2f3f5;
 background:linear-gradient(90deg,rgba(226,0,26,.25),rgba(74,222,128,.2));border:1px solid rgba(255,255,255,.16)}
.badge svg{width:16px;height:16px;fill:currentColor}
p{margin:16px 0 0;line-height:1.55;font-size:16px}.how{margin-top:12px;font-size:14px;opacity:.65}
"""
_LOCK = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 17a2 2 0 1 0 0-4 2 2 0 0 0 0 4m6-9a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V10a2 2 0 0 1 2-2h1V6a5 5 0 0 1 10 0v2zm-6-5a3 3 0 0 0-3 3v2h6V6a3 3 0 0 0-3-3"/></svg>'
_logo_cache: str | None = None


def _logo() -> str:
    """The animated logo as inline markup: this page is shown before anyone is signed in, so no file of the app may be needed."""
    global _logo_cache
    if _logo_cache is None:
        path = Path(__file__).parent / "static" / "about-logo.svg"
        _logo_cache = path.read_text(encoding="utf-8") if path.exists() else ""
    return _logo_cache


def _page(status: int, key: str) -> HTMLResponse:
    t = i18n.translator(config.language())
    lang = config.language()
    body = (
        f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
        f'<meta name="color-scheme" content="dark"><title>Car Assistant</title>'
        '<link rel="icon" type="image/svg+xml" href="/static/favicon.svg"><link rel="icon" href="/favicon.ico" sizes="any">'
        '<link rel="apple-touch-icon" sizes="180x180" href="/icon/180.png">'
        f"<style>{_PAGE_CSS}</style></head><body>"
        f'<main class="card"><div class="logo">{_logo()}</div><h1>Car <span>Assistant</span></h1><div class="slogan">Drive · Log · Go</div>'
        f'<div class="badge">{_LOCK}<span>{escape(t("access.badge"))}</span></div>'
        f'<p>{escape(t(key))}</p><p class="how">{escape(t("access.how"))}</p></main></body></html>'
    )
    return HTMLResponse(body, status_code=status)


ICON_PATHS = {"/favicon.ico", "/apple-touch-icon.png", "/apple-touch-icon-precomposed.png", "/static/favicon.svg"}


def is_icon(path: str) -> bool:
    return path in ICON_PATHS or (path.startswith("/icon/") and path.endswith(".png"))


def refuse(request: Request) -> HTMLResponse | None:
    """The answer to a direct connection that must not get in (None = go on to the sign-in). The Home Assistant panel never comes here.
    The icons stay reachable: a phone asks for them even while the page only says "locked" (they show nothing about the cars)."""
    if request.method in ("GET", "HEAD") and is_icon(request.url.path):
        return None
    with db.tx() as conn:
        if not accounts.has_users(conn):
            return _page(403, "access.locked")
    return None
