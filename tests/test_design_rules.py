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
        "nm-tabs",
        "tabbar",
        "tab",
        "tab-ind",
        "table-wrap",
    }  # tv- / ta- / nm- only add a margin (or a name length) to .seg-tabs
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


def test_the_messages_of_a_page_without_a_header_float_as_a_toast_and_do_not_stick_to_the_page():
    """Home has no header and so no notice slot: its messages are a toast (notices.js), solid under the tint, and are hidden until the script has moved them."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "carassistant/app/carassistant/static"
    js = (root / "notices.js").read_text(encoding="utf-8")
    css = (root / "pc-core.css").read_text(encoding="utf-8")
    assert "toast-host" in js and "toast" in js and "if (!slot)" in js
    assert ".toast-host" in css and "position: fixed" in css.split(".toast-host {", 1)[1].split("}", 1)[0]
    assert "main:not(:has(> .notice-slot)) > .flash:not([id])" in css  # no flash of the old place before the toast appears


def test_the_rows_of_a_widget_never_end_in_a_line():
    """A list inside a widget draws the line ABOVE a row (the first row's line is pulled out of the grid and clipped), so that the last row of any number
    of columns ends without one. A line under every row would draw one under the last row, and no CSS can tell the last row of a grid of unknown width."""
    css = _css()
    grid = re.search(r"\.cd-grid \{([^}]*)\}", css).group(1)
    item = re.search(r"\.cd-item \{([^}]*)\}", css).group(1)
    assert "overflow: hidden" in grid
    assert "margin-top: -1px" in item and "border-top: 1px solid" in item and "border-bottom" not in item
    assert "border-bottom" not in re.search(r"\.wd-li \{([^}]*)\}", css).group(
        1
    )  # the other list of the widgets: the line sits above, the first row has none


def test_a_switch_always_sits_at_the_right_end_of_its_row_no_style_moves_it():
    """docs/design.md, "Switch": like the settings of an iPhone, the switch is always the last thing at the RIGHT end of its row - on every page, in
    every theme, also for the switches of a plugin (the app draws them). No rule of a style sheet may reorder, reverse or float a switch row;
    ``tools/check_ui.py`` measures the same on every page in a real browser."""
    static = TEMPLATES.parent / "static"
    for sheet in sorted(static.glob("*.css")):
        css = re.sub(r"/\*.*?\*/", "", sheet.read_text(encoding="utf-8"), flags=re.S)
        for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
            if re.search(r"\.switch\b|\.sw-row\b|\.nm-row\b|\.addon-sw\b", selector):
                assert not re.search(r"row-reverse|\border\s*:|float\s*:", body), f"{sheet.name}: {selector.strip()} moves a switch"
    macros = (TEMPLATES / "_macros.html").read_text(encoding="utf-8")
    row = macros[macros.index("macro switch_row") : macros.index("endmacro", macros.index("macro switch_row"))]
    assert row.index('class="nm-t"') < row.index('class="nm-state"') < row.index('class="switch"')  # text, Yes / No, then the switch


def test_sub_windows_are_one_component_with_fixed_measures():
    """A card with several areas is built from sub-windows (docs/design.md, 4c): ONE definition, its spacing only from the tokens, and none of the
    private looks that came before (a heading with a divider line, ``nm-block``, ``acct-sub`` ...)."""
    static = TEMPLATES.parent / "static"
    css = (static / "pc-core.css").read_text(encoding="utf-8")
    root = css[css.index(":root {") : css.index("}", css.index(":root {"))]
    for token in ("--sp-sub:", "--sp-sub-pad-y:", "--sp-sub-pad-x:", "--sp-sub-label:"):
        assert token in root, f"{token} is a fixed measure of the design (the :root block of pc-core.css)"
    rule = re.search(r"\n\.sub-card \{([^}]*)\}", css)
    assert rule, "the one definition of .sub-card"
    body = rule.group(1)
    assert "margin-top: var(--sp-sub)" in body and "padding: var(--sp-sub-pad-y) var(--sp-sub-pad-x)" in body, (
        ".sub-card is spaced by the tokens only"
    )
    label = re.search(r"\n\.sub-h \{([^}]*)\}", css)
    assert label and "var(--sp-sub-label)" in label.group(1), ".sub-h sits --sp-sub-label above the content"
    assert len(re.findall(r"\n\.sub-card \{", css)) == 1 and len(re.findall(r"\n\.sub-h \{", css)) == 1, "one definition each"
    for old in ("nm-block", "acct-sub", "mcp-sec", "mcp-h"):
        assert old not in css, f"{old}: the private look of a sub-area is gone, use .sub-card / .sub-h"
    assert "ar-pill" not in css, "a button in a window is the standard small button, not a private pill"
    for path in _files():
        text = path.read_text(encoding="utf-8")
        for old in ("nm-block", "acct-sub", "ar-pill"):
            assert old not in text, f"{path.name}: {old} - use .sub-card / .sub-h and the standard buttons"
        for tag in re.findall(r'<[^>]*class="[^"]*\bsub-card\b[^"]*"[^>]*>', text):
            assert "style=" not in tag, f"{path.name}: a sub-window takes its spacing from the tokens, not from a style"
        for heading in re.findall(r'<h3 class="sub-h"[^>]*>', text):
            assert "style=" not in heading


def test_a_switch_row_under_a_field_keeps_the_air_of_the_design():
    """A line never touches a field (docs/design.md, 4c): the switch row that begins with its own line stands ``--sp-field`` below a select or an input."""
    css = (TEMPLATES.parent / "static" / "pc-core.css").read_text(encoding="utf-8")
    root = css[css.index(":root {") : css.index("}", css.index(":root {"))]
    assert "--sp-field: 14px" in root
    rule = re.search(r"\nlabel:not\(\.check\):not\(\.sw-row\) \+ label\.nm-row\.sw-row[^{]*\{([^}]*)\}", css)
    assert rule and "margin-top: var(--sp-field)" in rule.group(1), "a switch row under a field is spaced by the token"


def test_the_phone_cards_of_the_connection_map_are_standard_cards_with_flat_rows():
    """The phone view of the connection map (docs/design.md, 4c: no box in a box): each plugin is a real ``.card`` and what it talks to are flat rows with a
    line between them - no framed tiles, no private card look, no dashed "more" tile (it is a standard small button)."""
    page = (TEMPLATES / "_linkmap.html").read_text(encoding="utf-8")
    assert 'class="lm-card card"' in page and "lm-tile-more" not in page
    assert re.search(r'class="small" data-more-tiles', page)
    css = (TEMPLATES.parent / "static" / "pc-core.css").read_text(encoding="utf-8")
    tile = re.search(r"\n\.lm-tile \{([^}]*)\}", css)
    assert tile and "border: 0" in tile.group(1) and "background: none" in tile.group(1), "a row of the list is flat, not a framed tile"
    assert re.search(r"\n\.lm-tiles li \+ li \{[^}]*border-top: 1px solid var\(--glass-b\)", css), "a line between the rows"
    assert "lm-tile-more" not in css
    sel = re.search(r"\n\.lm-tile\.sel \{([^}]*)\}", css)
    assert sel and "var(--glass-b)" in sel.group(1) and "accent" not in sel.group(1), (
        "the open row is marked in the colour of the lines, not red"
    )
    assert "border-radius: 0" in tile.group(1), "and square"


def test_the_lines_of_a_window_run_through_its_whole_width():
    """Lines run from edge to edge of their window (docs/design.md, 4c): the window gives its padding as ``--bleed`` and the rows that carry a line reach out by
    exactly that much and pad their content back in. ``tools/check_ui.py`` measures every line of every page; this guards the rule itself."""
    css = (TEMPLATES.parent / "static" / "pc-core.css").read_text(encoding="utf-8")
    root = css[css.index(":root {") : css.index("}", css.index(":root {"))]
    assert "--sp-card: 18px" in root
    assert re.search(r"\n\.card, dialog\.addon-dlg \.addon-dlg-body \{ --bleed: var\(--sp-card\); \}", css)
    assert "--bleed: var(--sp-sub-pad-x)" in re.search(r"\n\.sub-card \{([^}]*)\}", css).group(1)
    block = css[css.index("LINES RUN THROUGH THE WHOLE WINDOW") :]
    assert "margin-inline: calc(-1 * var(--bleed)); padding-inline: var(--bleed);" in block
    app = (TEMPLATES.parent / "static" / "app.css").read_text(encoding="utf-8")
    assert re.search(r"\n\.card \{[^}]*padding: var\(--sp-card, 18px\)", app), "the card's padding is the token the lines reach out by"


def test_every_explanation_begins_with_the_info_symbol():
    """An explanation (``<p class="hint">``) always begins with the info symbol (docs/design.md, 4c). Where it stands - at the top of its window - is measured in a
    real browser by ``tools/check_ui.py``; this guards the symbol in every template."""
    pattern = re.compile(r'<p class="hint[^"]*"([^>]*)>(.{0,40})', re.S)
    for path in _files():
        text = path.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            attrs, start = match.group(1), match.group(2)
            if "id=" in attrs or "hidden" in attrs or start.lstrip().startswith("</p"):
                continue  # filled by a script / empty
            assert start.startswith("{{ icon('info', 14) }}"), f"{path.name}: an explanation without the info symbol: {start[:36]!r}"


def test_a_fixed_status_in_a_dashboard_tile_never_breaks_inside_a_word():
    """ "All good" is a short fixed text in a half-width tile: it wraps at the gap ("Alles in / Ordnung"), never at a syllable ("Ord-/nung"). Only a long
    title (an appointment, a task) keeps the syllable breaks."""
    css = (TEMPLATES.parent / "static" / "pc-core.css").read_text(encoding="utf-8")
    rule = re.search(r"\n\.wd-v\.wd-fixed \{([^}]*)\}", css)
    assert rule and "hyphens: manual" in rule.group(1) and "overflow-wrap: normal" in rule.group(1)
    security = (TEMPLATES / "widgets" / "security.html").read_text(encoding="utf-8")
    service = (TEMPLATES / "widgets" / "service.html").read_text(encoding="utf-8")
    assert 'class="wd-v wd-fixed"' in security and "wd-fixed" in service
    assert 'class="wd-v">{% if s.attention %}{{ s.attention[0].title }}' not in service, (
        "a long title keeps its syllable breaks, a fixed status does not"
    )


def test_every_sub_window_label_has_its_symbol_in_the_main_colour():
    """The label of a sub-window always carries a symbol (docs/design.md, 4c): it comes from the ONE macro ``sub_h`` - never a hand-written ``<h3 class="sub-h">`` -
    with an icon that exists, and the symbol takes the main colour from the one rule in pc-core.css."""
    from carassistant.icons import ICONS

    macros = (TEMPLATES / "_macros.html").read_text(encoding="utf-8")
    assert macros.count("macro sub_h(") == 1 and "icon(ic, 16)" in macros
    css = (TEMPLATES.parent / "static" / "pc-core.css").read_text(encoding="utf-8")
    assert re.search(r"\n\.sub-h \.ico \{[^}]*color: var\(--accent\)", css), "the symbol of a label is the main colour"
    for path in _files():
        if path.name == "_macros.html":
            continue
        text = path.read_text(encoding="utf-8")
        assert '<h3 class="sub-h"' not in text, f"{path.name}: use the macro sub_h(icon, text), it adds the symbol"
        for name in re.findall(r"sub_h\('([a-z0-9-]+)'", text):
            assert name in ICONS, f"{path.name}: sub_h uses an icon that does not exist: {name}"


def test_an_empty_sub_window_shows_the_compact_empty_state_and_a_create_button():
    """Nothing there yet (docs/design.md, 4c): the symbol in front of one centred sentence, never a dash; the button that creates the first one is called
    *Create*, has the plus, and keeps its word on a narrow screen."""
    css = (TEMPLATES.parent / "static" / "pc-core.css").read_text(encoding="utf-8")
    assert (
        len(
            re.findall(
                r"\n\.sub-card \.empty-state, \.lm-detail \.empty-state, \.lmz-detail \.empty-state, \.push-box \.empty-state, \.sys-state\.empty-state \{",
                css,
            )
        )
        == 1
    ), "one compact definition for a sub-window and the detail of the connection map"
    assert ".ar-edit:not(.ar-new) > button > span" in css, "a create button keeps its word where the edit buttons keep only the pencil"
    account = (TEMPLATES / "_account.html").read_text(encoding="utf-8")
    assert account.count('class="empty-state"') == 2 and "account.passkeys_none" in account and "account.passcode_none" in account
    assert '<span class="muted">–</span>' not in account, "no dash for an empty window"
    assert account.count("_('btn.create')") == 2, "the passkey and the passcode button say Create"


def test_a_field_with_a_function_carries_it_inside_and_names_it():
    """A function of a field (open, copy, change, scan) sits IN the field as an icon action (docs/design.md, 4b) - one definition, no pair of a field and a
    button next to it (``cp-row`` is gone), and an icon action always has a name for a screen reader and as the tip."""
    css = (TEMPLATES.parent / "static" / "pc-core.css").read_text(encoding="utf-8")
    assert len(re.findall(r"\n\.fld \{", css)) == 1 and len(re.findall(r"\n\.fld-act \{", css)) == 1, "one definition each"
    assert "cp-row" not in css
    hover = re.search(r"\n\.fld-act:hover, \.fld-act:focus-visible \{([^}]*)\}", css)
    assert hover and "border-color: var(--glass-b)" in hover.group(1), (
        "hovering an action in a field lightens its surface only, the line stays as it was (button:hover would lighten it)"
    )
    assert re.search(r"\n\.fld-act:active \{[^}]*transform: none", css), "no press-shrink inside a field"
    for path in _files():
        text = path.read_text(encoding="utf-8")
        assert "cp-row" not in text, f"{path.name}: cp-row - the function sits in the field (.fld / .fld-act)"
        for tag in re.findall(r"<(?:button|a)\b[^>]*\bclass=\"[^\"]*\bfld-act\b[^\"]*\"[^>]*>", text):
            assert "aria-label=" in tag and "title=" in tag, (
                f"{path.name}: an icon action in a field needs aria-label and title: {tag[:80]}"
            )
