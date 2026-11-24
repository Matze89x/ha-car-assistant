"""The design contract (docs/design-contract.md): every design keeps the variables, readable contrast, and the docs list them."""

import re
from pathlib import Path

import pytest

from carassistant import frametheme, themes

DOCS = Path(__file__).resolve().parents[1] / "docs"


@pytest.fixture(autouse=True)
def _own_data(env):
    """The colours read the stored accent: every test gets its own empty database (a clean checkout has none lying around, like the CI)."""


def _tokens(theme: str) -> dict[str, str]:
    css = frametheme.tokens(theme)
    if theme == "auto":
        css = css.split("@media")[0]  # the dark half; the light half is the theme "light"
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"(--[\w-]+):\s*([^;}]+)", css)}


def _luminance(colour: str) -> float:
    h = colour.lstrip("#")
    h = "".join(c * 2 for c in h) if len(h) == 3 else h
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))

    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _is_hex(value: str | None) -> bool:
    return bool(re.fullmatch(r"#[0-9a-fA-F]{3}|#[0-9a-fA-F]{6}", value or ""))


@pytest.mark.parametrize("theme", themes.available())
def test_every_design_has_the_variables_of_the_contract(theme):
    missing = [t for t in frametheme.CONTRACT_TOKENS if t not in _tokens(theme)]
    assert not missing, f"{theme}: {missing}"


# (text, on, minimum contrast): readable text 4.5, secondary 3, status and accent colours as text or icon on a card 3
CHECKS = (
    ("--text", "--bg", 4.5),
    ("--text", "--card", 4.5),
    ("--muted", "--card", 4.5),
    ("--dim", "--card", 3.0),
    ("--dim", "--bg", 3.0),  # the section labels stand on the page, not on a card
    ("--accent-text", "--accent", 3.0),
    ("--accent", "--card", 3.0),
    ("--ok", "--card", 3.0),
    ("--soon", "--card", 3.0),
    ("--overdue", "--card", 3.0),
)


@pytest.mark.parametrize("theme", themes.available())
def test_every_design_is_readable(theme):
    tokens = _tokens(theme)
    for fg, bg, minimum in CHECKS:
        a, b = tokens.get(fg), tokens.get(bg)
        assert _is_hex(a) and _is_hex(b), f"{theme}: {fg} / {bg} must be plain hex colours ({a}, {b})"
        assert contrast(a, b) >= minimum, f"{theme}: {fg} on {bg} is {contrast(a, b):.1f}:1, needs {minimum}:1"


def test_light_designs_say_so():
    for theme in ("light", "custom-light"):
        assert "color-scheme: light" in frametheme.tokens(theme)
    assert "color-scheme: dark" in frametheme.tokens("default")


@pytest.mark.parametrize("doc", ["design-contract.md", "design-contract.de.md"])
def test_the_docs_list_every_variable_of_the_contract(doc):
    text = (DOCS / doc).read_text(encoding="utf-8")
    missing = [t for t in frametheme.CONTRACT_TOKENS if f"`{t}`" not in text]
    assert not missing, f"{doc}: {missing}"


def test_the_two_docs_are_linked_to_each_other():
    assert "design-contract.de.md" in (DOCS / "design-contract.md").read_text(encoding="utf-8")
    assert "design-contract.md" in (DOCS / "design-contract.de.md").read_text(encoding="utf-8")
