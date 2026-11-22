"""Colour themes: a theme is one CSS file in `static/themes/` that only overrides the colour tokens (see docs/design.md).

The layout and all functions stay the same; the colours of the whole app follow the tokens. "default" needs no file.
"""

from __future__ import annotations

import colorsys
import re
from pathlib import Path

from . import db

THEMES_DIR = Path(__file__).parent / "static" / "themes"
SETTING = "ui.theme"
DEFAULT = "default"
_NAME = re.compile(r"^[a-z][a-z0-9-]{1,30}$")


CUSTOM = ("custom-light", "custom-dark", "custom-auto")  # light / dark / light-dark with a colour of your own (one colour for the server)
INTERNAL = frozenset({"light", "auto"})  # the files the light and the day / night designs are built on - not offered on their own
ACCENT_SETTING = "ui.accent"
DEFAULT_ACCENT = "#2f8cff"
PRESETS = ("#e2001a", "#ff6a00", "#f5b301", "#3ddc84", "#14b8a6", "#2f8cff", "#6366f1", "#a855f7", "#ec4899", "#94a3b8")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def available() -> list[str]:
    own = sorted(p.stem for p in THEMES_DIR.glob("*.css") if _NAME.match(p.stem) and p.stem not in INTERNAL)  # a theme file of your own
    return [DEFAULT, *CUSTOM, *own]


def is_custom(name: str | None) -> bool:
    return name in CUSTOM


def base_of(name: str) -> str:
    """The theme whose files a design uses: dark with your own colour is the dark base, light with your own colour the light theme."""
    return {"custom-dark": DEFAULT, "custom-light": "light", "custom-auto": "auto"}.get(name, name)


def attr(name: str) -> str | None:
    """The value of ``data-theme`` on the page (the dark base has none)."""
    base = base_of(name)
    return None if base == DEFAULT else base


def clean_accent(value: str | None) -> str | None:
    value = (value or "").strip()
    if value and not value.startswith("#"):
        value = "#" + value
    return value.lower() if _HEX.match(value) else None


def stored_accent() -> str:
    with db.tx() as conn:
        return clean_accent(db.get_setting(conn, ACCENT_SETTING, "")) or DEFAULT_ACCENT


def frame_colours(accent: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """The two colours of the icon frame for a design colour: the colour itself and its partner on the colour wheel (like red and green of the
    classic frame)."""
    color = clean_accent(accent) or DEFAULT_ACCENT
    r, g, b = (int(color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    h, _, s = colorsys.rgb_to_hls(r, g, b)
    s = max(s, 0.55)

    def rgb(hue: float, light: float) -> tuple[int, int, int]:
        red, green, blue = colorsys.hls_to_rgb(hue % 1.0, light, s)
        return round(red * 255), round(green * 255), round(blue * 255)

    return rgb(h, 0.47), rgb(h + 0.38, 0.58)


def _luminance(r: float, g: float, b: float) -> float:
    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


# the surfaces a design colour has to be readable on (a card of the light design / of the dark one)
SURFACE = {"light": "#f4f5f7", "dark": "#181c24"}


def contrast(a: str, b: str) -> float:
    """WCAG contrast ratio of two ``#rrggbb`` colours (1 = none, 21 = black on white)."""
    la, lb = (_luminance(*(int(c[i : i + 2], 16) / 255 for i in (1, 3, 5))) for c in (a, b))
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def readable_lightness(h: float, s: float, light: float, scheme: str, ratio: float) -> float:
    """The lightness nearest to ``light`` at which this colour reaches ``ratio`` on the surface of the scheme: darker on the light design,
    lighter on the dark one. A pale green on white becomes a deeper green, a dark blue on dark a lighter blue - the hue stays."""
    surface = SURFACE["light" if scheme == "light" else "dark"]
    step = -0.01 if scheme == "light" else 0.01
    while 0.04 < light < 0.96 and contrast(_hex(h, s, light), surface) < ratio:
        light += step
    return light


def _hex(h: float, s: float, light: float) -> str:
    r, g, b = colorsys.hls_to_rgb(h, min(max(light, 0.0), 1.0), s)
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


def accent_css(color: str, scheme: str) -> str:
    """One colour -> the whole accent family of a design (button gradient, hover, light text colour, the text colour on a button).

    The lightness is kept in a range that stays readable on the background of the scheme; green / amber / red of the states are not touched.
    """
    color = clean_accent(color) or DEFAULT_ACCENT
    red, green, blue = (int(color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    if scheme == "auto":  # follows the device: the dark family, and the light one while the device is light
        return accent_css(color, "dark") + "@media (prefers-color-scheme: light){" + accent_css(color, "light") + "}"
    h, light, s = colorsys.rgb_to_hls(red, green, blue)
    if scheme == "light":
        base = min(max(light, 0.34), 0.50)
        hi = base - 0.07
    else:
        base = min(max(light, 0.42), 0.58)
        hi = min(base + 0.26, 0.82)
    base = readable_lightness(h, s, base, scheme, 3.0)  # whatever the colour: fills and lines of it are always visible (3 : 1)
    ink = _hex(h, s, readable_lightness(h, s, base, scheme, 4.5))  # ... and as text always readable (4.5 : 1)
    top, bot, top_h, bot_h = base + 0.10, base - 0.03, base + 0.14, base
    main = _hex(h, s, base)
    mr, mg, mb = (int(main[i : i + 2], 16) for i in (1, 3, 5))
    # text on a button: white, unless the button is so light that white would be hard to read
    lum = _luminance(*(int(_hex(h, s, base + 0.035)[i : i + 2], 16) / 255 for i in (1, 3, 5)))
    text = "#ffffff" if 1.05 / (lum + 0.05) >= 2.8 else "#10131a"
    return (
        ":root:root:root{"
        f"--accent:{main};--accent-rgb:{mr}, {mg}, {mb};--accent-hi:{_hex(h, s, hi)};"
        f"--accent-top:{_hex(h, s, top)};--accent-bot:{_hex(h, s, bot)};--accent-top-h:{_hex(h, s, top_h)};--accent-bot-h:{_hex(h, s, bot_h)};"
        f"--accent-text:{text};--accent-ink:{ink}"
        "}"
    )


def current(conn) -> str:
    chosen = db.get_setting(conn, SETTING, DEFAULT) or DEFAULT
    return chosen if chosen in available() else DEFAULT


_BG = re.compile(r"--bg:\s*(#[0-9a-fA-F]{6})")
DARK_META = ("dark", "#0d1016")


def meta(name: str) -> tuple[str, str]:
    """(color scheme, background colour) of a theme, read from its file; used for the browser's own colours."""
    name = base_of(name)
    path = THEMES_DIR / f"{name}.css"
    if name == DEFAULT or not _NAME.match(name) or not path.is_file():
        return DARK_META
    text = path.read_text(encoding="utf-8")
    found = _BG.search(text)
    if text.startswith("/* scheme: auto */"):
        return ("auto", DARK_META[1])  # dark unless the device asks for light
    return ("light" if text.startswith("/* scheme: light */") else "dark", found.group(1) if found else DARK_META[1])
