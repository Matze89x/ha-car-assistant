"""The design of a car as plain CSS variables, for pages a package shows inside the app (``kind: frame``, docs/plugins.md).

Only custom properties (``--accent``, ``--bg``, the glass values, radii ...) and ``color-scheme`` - no layout. They are read from the same files the app
itself uses (``static/app.css``, ``static/pc-core.css`` and the theme file), so a frame always matches the chosen design, also a theme file of your own.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import themes

STATIC = Path(__file__).resolve().parent / "static"

CONTRACT_TOKENS = (  # the variables every design and every package page can rely on (docs/design-contract.md - a test keeps both in step)
    "--bg", "--card", "--card2", "--line", "--line2",
    "--text", "--muted", "--dim", "--strong",
    "--accent", "--accent-rgb", "--accent-hi", "--accent-text",
    "--ok", "--soon", "--overdue", "--ok-rgb", "--soon-rgb", "--overdue-rgb", "--ok-bg", "--soon-bg", "--overdue-bg",
    "--fg-rgb", "--glass", "--glass2", "--glass-b", "--btn-edge", "--btn-hi",
    "--r-s", "--r-m", "--r-l",
    "--sp-edge", "--sp-col", "--sp-block",
)  # fmt: skip
_cache: dict[str, str] = {}


def _rules(css: str):
    """(selector, body) of the rules at the top level of a stylesheet (nested blocks such as @media are skipped)."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    depth, start, sel = 0, 0, ""
    for i, ch in enumerate(css):
        if ch == "{":
            if depth == 0:
                sel = " ".join(css[start:i].split())
                start = i + 1
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                yield sel, css[start:i]
                start = i + 1


def _declarations(css: str, want: re.Pattern[str]) -> list[str]:
    out: list[str] = []
    for sel, body in _rules(css):
        if any(want.fullmatch(part.strip()) for part in sel.split(",")):
            out += [d.strip() for d in body.split(";") if d.strip().startswith(("--", "color-scheme"))]
    return out


def tokens(theme: str) -> str:
    """``:root { ... }`` with the tokens of the theme (``default`` = the dark base, ``auto`` = dark base and the light theme on a light device)."""
    theme = theme if theme in themes.available() or theme in themes.INTERNAL else themes.DEFAULT
    if themes.is_custom(theme):  # dark / light with a colour of your own: the base design plus the accent family of the chosen colour
        base = themes.base_of(theme)
        return tokens(base) + themes.accent_css(themes.stored_accent(), {"light": "light", "auto": "auto"}.get(base, "dark")) + "\n"
    if theme in _cache:
        return _cache[theme]
    base: list[str] = []
    for name in ("app.css", "pc-core.css"):
        base += _declarations((STATIC / name).read_text(encoding="utf-8"), re.compile(r":root"))
    lines = [":root { " + "; ".join(base) + "; }"]
    wanted = {theme} if theme != "auto" else {"light"}
    for name in wanted:
        path = STATIC / "themes" / f"{name}.css"
        if not path.is_file():
            continue
        decls = _declarations(path.read_text(encoding="utf-8"), re.compile(r':root\[data-theme="' + re.escape(name) + r'"\]'))
        if decls:
            block = ":root { " + "; ".join(decls) + "; }"
            lines.append(f"@media (prefers-color-scheme: light) {{ {block} }}" if theme == "auto" else block)
    text = "\n".join(lines) + "\n"
    _cache[theme] = text
    return text
