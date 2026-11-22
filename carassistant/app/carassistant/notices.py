"""The notices of a page are placed on the SERVER, in the slot under the page header (``<div class="notice-slot">`` made by ``page_head``).

Info (the introduction of the page), "saved" messages, warnings and errors are one tile with an icon. Placing them here, before the page is sent,
means nothing is moved in the browser afterwards: no flash, no jump (a script that moves them after the first paint shows both). ``notices.js``
only handles what is built later in the browser.
"""

from __future__ import annotations

import re

from . import icons

SLOT = '<div class="notice-slot" aria-live="polite"></div>'
_ICON = {"info": "information-outline", "ok": "check-circle-outline", "warn": "alert-outline", "err": "alert-circle-outline"}
_FLASH = re.compile(r'<(div|p) class="flash (err|ok|warn)"(?: role="status")?>(.*?)</\1>', re.S)
_INTRO = re.compile(
    r'\s*(?:<p class="hint(?: set-scope)?">(?P<p>.*?)</p>|<span class="hint">(?P<s>.*?)</span>|<div class="pk-bar">\s*<span class="hint">(?P<b>.*?)</span>\s*</div>)',
    re.S,
)
_SVG = re.compile(r"^\s*<svg\b.*?</svg>\s*", re.S)


def _icon(kind: str) -> str:
    path = icons.ICONS.get(_ICON[kind], "")
    return (
        f'<svg class="ico" width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="{path}"></path></svg>'
    )


def tile(kind: str, body: str) -> str:
    role = "alert" if kind in ("err", "warn") else "status"
    return f'<div class="notice {kind}" role="{role}">{_icon(kind)}<span>{body.strip()}</span></div>'


def place(html: str) -> str:
    """Move the flash messages and the introduction of a page into the slot. Pages without the slot stay as they are."""
    at = html.find(SLOT)
    main = html.rfind("<main", 0, at) if at >= 0 else -1
    if main < 0:
        return html
    messages: list[str] = []

    def take(m: re.Match) -> str:
        messages.append(tile(m.group(2), m.group(3)))
        return ""

    before = html[:main]
    between = _FLASH.sub(take, html[main:at])  # the message of the address (?m=...) sits between <main> and the slot
    rest = html[at + len(SLOT) :]
    info = ""
    intro = _INTRO.match(rest)
    if intro:
        text = intro.group("p") or intro.group("s") or intro.group("b") or ""
        info = tile("info", _SVG.sub("", text))
        rest = rest[intro.end() :]
    rest = _FLASH.sub(take, rest)  # flashes inside the page (errors of a form ...) come along, messages first, the introduction last
    return before + between + f'<div class="notice-slot" aria-live="polite">{"".join(messages)}{info}</div>' + rest
