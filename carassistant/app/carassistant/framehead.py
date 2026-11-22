"""The head of Car Assistant on a page a package shows as a page of its own (``kind: "frame"``, docs/plugins.md).

The service's page is the whole window - no iframe, no app navigation. The proxy puts a small head on it: a back button (to *More* of the car),
the name of the package and, at the right, its version. The head is plain HTML and a style sheet (``/frame-head.css``), no script; its variables are
scoped to the head, so they never touch the page of the package.
"""

from __future__ import annotations

import html
import json
import re
import sqlite3

from . import __version__, config, frametheme, i18n, icons

INGRESS = re.compile(r"^/api/hassio_ingress/[A-Za-z0-9_\-]+$")
_HEAD = re.compile(rb"<head[^>]*>", re.I)
_BODY = re.compile(rb"<body[^>]*>", re.I)


def context(conn: sqlite3.Connection, pk: int, path: str) -> dict | None:
    """What the head shows for the package ``pk`` at ``path``: only for a path that lies under the route of one of its frame pages."""
    row = conn.execute("SELECT vehicle_id, manifest FROM vehicle_addons WHERE id = ?", (pk,)).fetchone()
    if row is None:
        return None
    try:
        manifest = json.loads(row["manifest"])
    except ValueError:
        return None
    page = next((p for p in manifest.get("pages", []) if p.get("kind") == "frame" and path.startswith(p["route"])), None)
    car = conn.execute("SELECT slug FROM vehicles WHERE id = ?", (row["vehicle_id"],)).fetchone()
    if page is None or car is None:
        return None
    lang = config.language()
    texts = (manifest.get("l10n") or {}).get(lang) or {}
    return {
        "name": texts.get("name") or manifest.get("name") or "",
        "version": manifest.get("version") or "",
        "slug": car["slug"],
        "lang": lang,
    }


def markup(ctx: dict, base: str) -> str:
    back = i18n.translator(ctx["lang"])("nav.more")
    chevron = f'<svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="{icons.ICONS["chevron-left"]}"></path></svg>'
    version = f'<span class="ca-ver">v{html.escape(ctx["version"])}</span>' if ctx["version"] else ""
    return (
        f'<header id="ca-head"><a class="ca-back" href="{html.escape(base)}/v/{html.escape(ctx["slug"])}/more" aria-label="{html.escape(back)}">{chevron}</a>'
        f'<span class="ca-name">{html.escape(ctx["name"])}</span>{version}</header>'
    )


def footer(ctx: dict, base: str) -> str:
    """The foot of the page: Back to More on the left, the name and version of Car Assistant on the right. Plain HTML, no script."""
    t = i18n.translator(ctx["lang"])
    chevron = f'<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="{icons.ICONS["chevron-left"]}"></path></svg>'
    return (
        f'<footer id="ca-foot"><a class="ca-fback" href="{html.escape(base)}/v/{html.escape(ctx["slug"])}/more">{chevron}<span>{html.escape(t("btn.back"))}</span></a>'
        f'<span class="ca-fname"><b>Car Assistant</b> · Drive · Log · Go</span><span class="ca-ver">v{html.escape(__version__)}</span></footer>'
    )


_BODY_END = re.compile(rb"</body\s*>", re.I)


def inject(page: bytes, head_html: str, css_href: str, foot_html: str = "") -> bytes:
    """The style sheet right after ``<head>`` (so the package's own styles win), the head right after ``<body>``. With a foot, the page itself
    sits in a box of the maximum width of Car Assistant and the foot closes the page."""
    link = f'<link rel="stylesheet" href="{html.escape(css_href)}">'.encode()
    head = head_html.encode() + (b'<div id="ca-wrap">' if foot_html else b"")
    tail = (b"</div>" + foot_html.encode()) if foot_html else b""
    ends = list(_BODY_END.finditer(page))
    if tail:
        page = page[: ends[-1].start()] + tail + page[ends[-1].start() :] if ends else page + tail
    if _HEAD.search(page):
        page = _HEAD.sub(lambda m: m.group(0) + link, page, count=1)
    else:
        head = link + head
    if _BODY.search(page):
        return _BODY.sub(lambda m: m.group(0) + head, page, count=1)
    return head + page


def base_of(ingress_header: str | None) -> str:
    return ingress_header if ingress_header and INGRESS.match(ingress_header) else ""


def css(theme: str) -> str:
    """The style sheet of the head: the design variables of the theme (scoped to ``#ca-head``), the page background and the head's own rules."""
    tokens = frametheme.tokens(theme)
    scoped = tokens.replace(":root", "#ca-head")
    backgrounds = re.findall(r"--bg:\s*(#[0-9a-fA-F]{3,6})", tokens)
    page = ""
    if backgrounds:
        auto = "prefers-color-scheme: light" in tokens  # dark unless the device asks for light
        page = f"html {{ background: {backgrounds[0] if auto else backgrounds[-1]}; }}\n"
        if auto and len(backgrounds) > 1:
            page += f"@media (prefers-color-scheme: light) {{ html {{ background: {backgrounds[-1]}; }} }}\n"
    return scoped + page + (frametheme.STATIC / "frame-head.css").read_text(encoding="utf-8")
