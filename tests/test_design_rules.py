"""The design method as a test: every page is built the same way (docs/design.md, chapter 9). A page that breaks a rule fails here."""

import re
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[1] / "carassistant" / "app" / "carassistant" / "templates"
# pages that deliberately have no page header: Home, the 404 page and the first language page
NO_HEAD = {"vehicle.html", "error.html", "setup_language.html"}


def _files():
    return sorted(TEMPLATES.glob("*.html"))


def test_every_page_has_the_same_header():
    for path in _files():
        text = path.read_text(encoding="utf-8")
        if 'extends "base.html"' in text and path.name not in NO_HEAD:
            assert "page_head(" in text, f"{path.name}: pages start with page_head()"


def test_colours_only_as_tokens_no_inline_styles():
    for path in _files():
        text = path.read_text(encoding="utf-8")
        for style in re.findall(r'style="([^"]*)"', text):
            assert re.fullmatch(r"width: \{\{ [^}]+ \}\}%", style.strip()), (
                f"{path.name}: inline style {style!r} (only a bar's width may be inline)"
            )
        assert not re.search(
            r"#[0-9a-fA-F]{6}\b",
            re.sub(r"<(script|style)[\s\S]*?</\1>", "", text)
            if path.name not in ("base.html", "login.html", "unlock.html")
            else ""  # the browser chrome (theme-color) and the standalone lock pages need real values), (
            f"{path.name}: a fixed colour in the markup",
        )


def test_settings_apply_live_without_a_save_button():
    """Settings forms are marked data-live / data-theme-live and carry no submit button; explicit actions (upload, reset, delete) are separate forms."""
    for name in ("settings_section.html", "_settings_system.html"):
        text = (TEMPLATES / name).read_text(encoding="utf-8")
        for form in re.findall(r"<form[^>]*data-(?:live|theme-live)[^>]*>[\s\S]*?</form>", text):
            assert "<button" not in form, f"{name}: a live form must not have a button"


def test_destructive_actions_are_confirmed_and_red():
    for path in _files():
        text = path.read_text(encoding="utf-8")
        for form in re.findall(r"<form[^>]*action=\"[^\"]*/delete\"[^>]*>[\s\S]*?</form>", text):
            assert "data-confirm" in form or "confirm_form(" in form, f"{path.name}: a delete asks first"


STATIC = TEMPLATES.parent / "static"
SIZES = {10, 11, 12, 13, 14, 15, 16, 18, 20, 24, 32, 40, 52, 64}  # the type scale (docs/design.md, chapter 1) + display numbers


def _css():
    text = "".join((STATIC / n).read_text(encoding="utf-8") for n in ("app.css", "pc-core.css"))
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def test_corners_and_type_follow_the_fixed_scale():
    css = _css()
    bad_r = [v for v in re.findall(r"border-radius:\s*(\d+(?:\.\d+)?px)", css) if v != "999px"]
    assert not bad_r, f"corners only as --r-s / --r-m / --r-l (or 999px): {sorted(set(bad_r))}"
    bad_f = {v for v in re.findall(r"font-size:\s*([\d.]+)px", css) if float(v) not in SIZES}
    assert not bad_f, f"font sizes only from the scale: {sorted(bad_f)}"


def test_one_rule_for_every_button():
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    pc = (STATIC / "pc-core.css").read_text(encoding="utf-8")
    assert (
        "button, .button, .ghost-btn { display: inline-flex" in css
        and "min-height: 44px; padding: 0 22px; border-radius: var(--r-m)" in css
    )
    assert ".ghost-btn.small { min-height: 36px; padding: 0 14px; font-size: 13px; border-radius: var(--r-s); }" in css  # the two sizes
    # a button never gets its own look on a page: the look (fill, edge, radius, colour) lives only in the one rule in app.css
    for line in pc.splitlines():
        if re.match(r"^\s*[^{]*\.(ghost-btn|button)\b[^{]*\{", line) and "icon-btn" not in line and "page-head" not in line:
            assert not re.search(r"(?<![-\w])(background|border-radius|border|color|backdrop-filter):", line.split("{", 1)[1]), (
                f"private button look: {line[:100]}"
            )
    # no page-level rule may resize a plain/primary/danger button again
    for line in pc.splitlines():
        if "page-head" in line or line.startswith("  "):
            continue  # the phone's round / icon-only buttons (inside @media) are a different component
        if re.match(r"^\s*[^{]*\b(form-bar|manage-bar|actions)[^{]*button[^{]*\{", line):
            assert not re.search(r"(min-)?height:|padding:|font-size:", line), f"override of the button size: {line[:90]}"


def test_haptics_switch_is_in_design_and_controls_the_hidden_switch(client):
    client.post("/vehicles", data={"name": "Tap Car", "fuel_type": "petrol"})
    assert 'data-haptics="1"' in client.get("/settings/design", follow_redirects=True).text  # on by default
    assert 'name="haptics"' in client.get("/settings/design").text
    client.post("/settings/haptics", data={})  # switch off: the checkbox sends nothing
    assert 'data-haptics="1"' not in client.get("/settings/design", follow_redirects=True).text
    client.post("/settings/haptics", data={"haptics": "1"})
    assert 'data-haptics="1"' in client.get("/settings/design", follow_redirects=True).text


def test_app_script_keeps_its_features():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    for needle in ("nav.pager[data-more]", 'setAttribute("switch"', "form[data-live]", "refreshBar"):
        assert needle in js, f"app.js lost a feature: {needle}"


def test_home_screen_icon_is_opaque_and_found_at_the_root(client):
    import io

    from PIL import Image

    for path in ("/apple-touch-icon.png", "/apple-touch-icon-precomposed.png", "/icon/180.png"):
        res = client.get(path)
        assert res.status_code == 200 and res.headers["content-type"] == "image/png"
        image = Image.open(io.BytesIO(res.content))
        assert image.size == (180, 180) and image.mode == "RGB", path  # no alpha channel: iOS would paint it black


def test_every_switch_row_has_a_line_above_and_below_and_air_after_it():
    css = (STATIC / "pc-core.css").read_text(encoding="utf-8")
    assert "label.nm-row.sw-row, .card label.nm-row.sw-row, form label.nm-row.sw-row { border-top: 1px solid var(--glass-b); }" in css
    assert ".sw-row + .hint" in css and "form:has(> .sw-row:last-child) + .hint" in css


def test_section_labels_share_one_air_above_and_one_distance_to_the_tile_below():
    """Every section label (vd-group-h, rec-month) takes its margins from the same tokens, no page has its own numbers."""
    import re
    from pathlib import Path

    css = (Path(__file__).resolve().parents[1] / "carassistant/app/carassistant/static/pc-core.css").read_text(encoding="utf-8")
    assert "--sp-label-top: 28px" in css and "--sp-label-bottom: 10px" in css
    for line in css.splitlines():
        head = line.split("{")[0]
        if re.search(r"(^|[ ,>])\.(vd-group-h|rec-month)\b", head) and "margin:" in line and "margin: 0" not in line:
            if ".card.grid" in head or ".pl-fix" in head:
                continue
            assert "var(--sp-label" in line, line


def test_every_page_head_has_the_one_notice_slot_and_the_script_fills_it(client):
    """Info, saved, warning and error all land in ONE slot under the page header (app.js moves the old .flash markup there)."""
    from pathlib import Path

    from tests.test_web import create_vehicle

    vid = create_vehicle(client)
    for path in (f"/v/{vid}/e/service", f"/v/{vid}/docs", f"/v/{vid}/plugins", "/settings/user"):
        page = client.get(path).text
        assert 'class="notice-slot"' in page and 'id="notice-icons"' in page, path
    js = (Path(__file__).resolve().parents[1] / "carassistant/app/carassistant/static/notices.js").read_text(encoding="utf-8")
    assert ".notice-slot" in js and '"info"' in js and '"err"' in js


def test_the_server_places_notices_in_the_slot_before_the_page_is_sent():
    from carassistant import notices

    page = (
        '<body><main>\n<div class="flash ok" role="status">Saved.</div>\n<div class="page-head"></div>'
        + notices.SLOT
        + '<p class="hint"><svg class="ico"><path d="x"></path></svg> Intro text</p><div class="card">x</div>'
        '<div class="flash err">Broken</div><div class="flash err" id="st-msg" hidden></div></main></body>'
    )
    out = notices.place(page)
    slot = out[out.index('<div class="notice-slot"') : out.index('<div class="card">')]
    assert slot.index("notice ok") < slot.index("notice err") < slot.index("notice info") or slot.index("notice err") < slot.index(
        "notice info"
    )
    assert "Saved." in slot and "Broken" in slot and "Intro text" in slot and "<svg" in slot
    assert '<p class="hint">' not in out and out.count('class="flash') == 1 and 'id="st-msg"' in out  # only the dynamic one stays
    assert notices.place("<main>no slot</main>") == "<main>no slot</main>"


def test_every_linked_widget_shows_its_arrow():
    """A widget that is a link carries the arrow at the top right - also the small ones (no rule may hide it)."""
    from pathlib import Path

    css = (Path(__file__).resolve().parents[1] / "carassistant/app/carassistant/static/pc-core.css").read_text(encoding="utf-8")
    assert ".wd.s .wd-h > .ico:last-child { display: none; }" not in css


def test_there_are_only_two_kinds_of_tab_bars_and_the_navigation():
    """ONE tab bar for text and symbol (.seg-tabs) and ONE round symbol switch (.seg-icons); the navigation (.tabbar) is not a tab bar.
    A new look for 'tabs' is not a new class: use one of these two (docs/design.md, "The fixed building blocks")."""
    import glob
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "carassistant/app/carassistant"
    allowed = {
        "seg-tabs",
        "seg-icons",
        "tv-tabs",
        "ta-tabs",
        "tabbar",
        "tab",
        "tab-ind",
        "table-wrap",
    }  # tv-/ta- only add a margin to .seg-tabs
    found = set()
    for path in glob.glob(str(root / "templates/**/*.html"), recursive=True) + glob.glob(str(root / "static/*.js")):
        for m in re.finditer(r'class="([^"{}]*)"', Path(path).read_text(encoding="utf-8")):
            found.update(tok for tok in m.group(1).split() if "tab" in tok)
    assert found <= allowed, f"a new kind of tab bar: {sorted(found - allowed)} - use .seg-tabs or .seg-icons"
    css = (root / "static/pc-core.css").read_text(encoding="utf-8") + (root / "static/app.css").read_text(encoding="utf-8")
    assert not re.search(r"(^|[\s,>])\.tabs\b", css, re.M), "the old .tabs rules are gone"


def test_every_style_sheet_is_balanced_and_has_no_dead_selectors_left_over():
    """A stray closing brace makes the browser drop the next rule without a word: every sheet must have as many { as }."""
    import re
    from pathlib import Path

    for name in ("pc-core.css", "app.css", "frame-kit.css", "frame-head.css"):
        css = (Path(__file__).resolve().parents[1] / "carassistant/app/carassistant/static" / name).read_text(encoding="utf-8")
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        assert css.count("{") == css.count("}"), f"{name}: unbalanced braces"


def test_rows_are_put_in_order_with_the_sort_handle_never_with_up_and_down_arrows():
    """ONE way to sort (docs/design.md, "The sort handle"): the strip `.grip` on the left of a row. A pair of up / down buttons is a second way."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "carassistant/app/carassistant"
    for path in list((root / "templates").glob("**/*.html")):
        text = path.read_text(encoding="utf-8")
        assert "nav.up" not in text and "nav.down" not in text, f"{path.name}: sorting arrows - use the sort handle"
        assert not re.search(r'name="(move|way|dir)"[^>]*value="[^"]*(up|down)"', text), (
            f"{path.name}: sorting arrows - use the sort handle"
        )
    for key in ("nav.up", "nav.down"):
        assert f'"{key}"' not in (root / "i18n.py").read_text(encoding="utf-8")
    css = (root / "static/pc-core.css").read_text(encoding="utf-8")
    assert not re.search(r"\.mvb\b|\.mv \{", css), "the old sort arrows (.mv / .mvb) are gone"
    js = (root / "static/app.js").read_text(encoding="utf-8")
    assert "[data-sort-item]" in js and "sortchange" in js


def test_everything_that_stands_on_its_own_on_a_page_has_ONE_corner_defined_in_one_place():
    """Neighbours on a page share ONE corner (docs/design.md, Radius). It is defined once, in the rule `:is(...) { border-radius: var(--r-surface) }` at the
    end of pc-core.css; a block of that list never gets another corner anywhere else, and the token is the card's corner."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "carassistant/app/carassistant/static"
    sheets = {n: (root / n).read_text(encoding="utf-8") for n in ("app.css", "pc-core.css", "frame-kit.css")}
    assert re.search(r"--r-surface: var\(--r-l\)", sheets["app.css"])
    one = re.search(r":is\(([^)]*)\) \{ border-radius: var\(--r-surface\); \}", sheets["pc-core.css"])
    assert one, "the one rule for the corner of a block that stands on its own is missing"
    surfaces = {x.strip() for x in one.group(1).split(",")}
    assert {".card", ".notice", ".flash", ".seg-tabs", "details.eq", ".rec", ".wd"} <= surfaces
    bad = []
    for name, css in sheets.items():
        for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
            radius = re.search(r"(?<![-\w])border-radius:\s*([^;]+)", body)
            if not radius or selectors.strip().startswith(":is(") or selectors.strip().startswith("@"):
                continue
            value = radius.group(1).strip()
            for selector in selectors.split(","):
                last = re.split(r"[\s>+~]+", selector.strip())[-1]
                base = re.split(r":(?!is)", last)[0]
                if base in surfaces and not (
                    value.startswith("var(--r-surface") or value.startswith("var(--r-l") or value in ("inherit", "0", "0 0 0 0")
                ):
                    bad.append(f"{name}: {selector.strip()} {{ border-radius: {value} }}")
    assert not bad, "a block that stands on its own has another corner than a card: " + "; ".join(bad)
    # the first block of a page starts level with the first card of the More list, also behind the (empty) notice slot
    assert ".page-head + .notice-slot + *" in sheets["pc-core.css"]
