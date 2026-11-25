"""The glass capsule belongs to the phone bar only: pc-core.css loads after app.css and must not bring it back into the sidebar."""

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "carassistant" / "app" / "carassistant" / "static"


def test_pc_core_has_no_unconditional_tabbar_glass():
    css = (STATIC / "pc-core.css").read_text(encoding="utf-8")
    for rule in re.findall(r"(?m)^\.tabbar\s*\{[^}]*\}", css):
        assert not re.search(r"background|border|box-shadow|backdrop-filter", rule), rule


def test_sidebar_resets_the_capsule_and_keeps_original_metrics():
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    side = css.split("@media (min-width: 760px)")[1].split("@media (min-width: 1280px)")[0]
    reset = re.search(r"\.tabbar\s*\{[^}]*\}", side).group(0)
    for needle in ("background: none", "border: 0", "box-shadow: none", "backdrop-filter: none", "border-radius: 0"):
        assert needle in reset, needle
    assert ".side .sb-brand .brand-mark" in side  # the logo is an inline icon tile, sized in pc-core.css like a navigation item
    narrow = side.split("@media")[0]
    assert re.search(
        r"\.side \.sb-brand \{[^}]*justify-content: center", narrow
    )  # the logo sits centred over the icons in the narrow sidebar
    assert ".side .sb-brand span { display: none; }" in narrow  # ... and the hidden name must not leave a gap next to it
    assert "--sw: 84px;" in css and "--sw: 248px;" in css


def test_favicon_ico_is_served(client):
    r = client.get("/favicon.ico")
    assert r.status_code == 200 and r.content[:4] == b"\x00\x00\x01\x00"  # ICO header
    assert 'href="/favicon.ico"' in client.get("/").text


def test_no_page_cross_fade_that_flashes(client):
    """The cross-document view transition made pages flash light between page changes; the browser holds the old page instead."""
    assert "view-transition" not in client.get("/").text and "view-transition" not in (STATIC / "app.css").read_text(encoding="utf-8")


def test_selected_more_entry_is_lighter_not_red():
    css = (STATIC / "pc-core.css").read_text(encoding="utf-8")
    assert ".mi.sel .ico" not in css  # no accent colour on the icons of the selected entry
    assert ".more-pane .mi.sel" in css


def test_page_next_to_the_more_list_fills_its_column():
    css = (STATIC / "pc-core.css").read_text(encoding="utf-8")
    assert ".vpage.with-more > main { grid-column: 2; margin: 0;" in css  # `margin: 0 auto` would shrink the grid item


def test_spacing_comes_from_fixed_tokens():
    css = (STATIC / "pc-core.css").read_text(encoding="utf-8")
    for token in ("--sp-edge", "--sp-col", "--sp-top", "--sp-head", "--sp-block", "--head-h"):
        assert f"{token}:" in css and f"var({token})" in css, token  # defined once, used by the layout


def test_round_icon_buttons_are_not_stretched_by_the_global_button_rule():
    css = (STATIC / "pc-core.css").read_text(encoding="utf-8")
    line = next(x for x in css.splitlines() if x.startswith(".icon-btn, .back-btn, .cur-switch"))  # the one circle-button rule
    assert "min-height: 0" in line and "padding: 0" in line  # the global `button` rule (44 px, 20 px padding) made it 42x44


def test_tab_bar_radius_follows_the_tokens():
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    line = next(x for x in css.splitlines() if x.startswith(".tabbar { position: fixed"))
    assert "border-radius: calc(var(--r-l) + 5px)" in line  # outer = inner radius + 5 px padding, no fixed 32 px


def test_the_back_arrow_of_a_page_deeper_than_more_stays_on_wide_screens():
    """With the More list beside the page it is the way back - except on a page deeper than More (one plugin, Sources, Add): that arrow leads to its own
    list and stays (it was hidden together with the others on a wide screen)."""
    css = (Path(__file__).resolve().parents[1] / "carassistant" / "app" / "carassistant" / "static" / "pc-core.css").read_text(
        encoding="utf-8"
    )
    assert ".vpage.with-more > main > .page-head .back-btn:not(.deep) { display: none; }" in css
    assert ".vpage.with-more > main > .page-head .back-btn.deep { display: inline-grid; }" in css
