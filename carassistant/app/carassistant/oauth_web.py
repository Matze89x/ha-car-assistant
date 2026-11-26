"""The way back of a login (``redirect: "app"`` of a step of type ``oauth``, docs/plugins.md): the provider sends the person's browser to ``/oauth/callback``
under the https address of the app, with the ``code`` and the ``state`` of the request. The page is public - the browser may not be signed in to the app at
that address - and is safe because everything hangs on the ``state``: random, kept for ten minutes, usable once, bound to one install and step. It
says only that it worked or that it did not; the reasons go into the log of the plugin (never a token)."""

from __future__ import annotations

import logging

from fastapi import Request

from . import __version__, config, connectors, db, events, i18n, oauth
from . import icons as icon_set
from .web import app, templates

log = logging.getLogger("carassistant")


def _page(request: Request, ok: bool, text: str, status: int = 200):
    tr = i18n.translator(config.language())
    return templates.TemplateResponse(
        request,
        "oauth_done.html",
        {
            "_": tr,
            "icons": icon_set.ICONS,
            "version": __version__,
            "lang": config.language(),
            "base": request.state.base,
            "icon_base": f"{request.state.base}/icon",
            "icon_rev": 0,
            "manifest_url": f"{request.state.base}/manifest.webmanifest",
            "ok": ok,
            "text": text,
        },
        status_code=status,
    )


@app.get("/oauth/callback")
def oauth_callback(request: Request, state: str = "", code: str = "", error: str = "", error_description: str = ""):
    tr = i18n.translator(config.language())
    addon = None
    try:
        if error:  # the person said no at the provider, or the provider could not log them in
            with db.tx() as conn:
                row = conn.execute("SELECT addon_pk FROM oauth_pending WHERE state = ?", (state[:100],)).fetchone()
                conn.execute("DELETE FROM oauth_pending WHERE state = ?", (state[:100],))
                addon = oauth.addon_of(conn, row["addon_pk"]) if row else None
            raise oauth.OAuthError("err.oauth_refused", oauth._plain(error_description or error))
        if not code:
            raise oauth.OAuthError("err.oauth_state")
        addon = oauth.finish(state, code)
    except oauth.OAuthError as exc:
        if addon:
            with db.tx() as conn:
                connectors.write_logs(
                    conn,
                    addon["vehicle_id"],
                    addon["addon_id"],
                    [(connectors._now(), "warn", "app", f"login failed: {tr(exc.key)} {exc.detail}".strip())],
                )
        return _page(request, False, tr("oauth.callback_failed"), 400)
    except Exception:
        log.exception("login with an account failed")
        return _page(request, False, tr("oauth.callback_failed"), 500)
    events.changed()
    return _page(request, True, tr("oauth.callback_ok"))
