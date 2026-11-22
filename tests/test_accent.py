"""Dark / light with a colour of your own: one colour becomes the whole accent family, the page and the frames follow it."""

import re

from carassistant import frametheme, themes


def _tokens(css: str) -> dict[str, str]:
    return dict(re.findall(r"(--[a-z-]+):([^;}]+)", css))


def test_one_colour_becomes_the_accent_family():
    css = themes.accent_css("#e2001a", "dark")
    tok = _tokens(css)
    assert tok["--accent"] == "#e2001a" and tok["--accent-rgb"].strip() == "226, 0, 26"  # the classic red stays itself
    for key in ("--accent-hi", "--accent-top", "--accent-bot", "--accent-top-h", "--accent-bot-h", "--accent-text"):
        assert key in tok
    assert css.startswith(":root:root:root{")  # beats the theme files whatever the order


def test_the_text_on_a_button_stays_readable():
    assert _tokens(themes.accent_css("#2f8cff", "dark"))["--accent-text"] == "#ffffff"
    assert _tokens(themes.accent_css("#f5b301", "dark"))["--accent-text"] == "#10131a"  # white on yellow would not be readable


def test_extreme_colours_are_kept_in_a_readable_range():
    for color in ("#ffffff", "#000000"):
        for scheme in ("dark", "light"):
            accent = _tokens(themes.accent_css(color, scheme))["--accent"]
            assert accent not in ("#ffffff", "#000000")


def test_only_real_colour_values_are_taken():
    assert themes.clean_accent("A855F7") == "#a855f7"
    assert themes.clean_accent("#12") is None and themes.clean_accent("red") is None and themes.clean_accent(None) is None


def test_the_designs_with_your_colour_use_the_dark_and_the_light_base():
    assert themes.attr("custom-dark") is None and themes.attr("custom-light") == "light"
    assert themes.meta("custom-light")[0] == "light" and themes.meta("custom-dark")[0] == "dark"
    assert {"custom-dark", "custom-light"} <= set(themes.available())


def test_the_page_follows_the_chosen_colour(client):
    assert client.post("/settings/accent", data={"accent": "#a855f7", "ajax": "1"}).status_code == 204
    client.post("/settings/theme", data={"theme": "custom-dark"})
    page = client.get("/settings/design").text
    assert 'id="accent-custom">:root:root:root{--accent:' in page and "data-theme=" not in page.split("<head>")[0]
    assert 'id="accent-pick"' in page and "hidden" not in re.search(r'<div[^>]*id="accent-pick"[^>]*>', page).group(0)
    client.post("/settings/theme", data={"theme": "custom-light"})
    light = client.get("/settings/design").text
    assert 'data-theme="light"' in light and "/static/themes/light.css" in light
    client.post("/settings/theme", data={"theme": "default"})
    other = client.get("/settings/design").text
    assert 'id="accent-custom"></style>' in other  # no colour of your own: the tag stays empty


def test_a_wrong_colour_is_refused_and_the_preview_is_plain_css(client):
    assert client.post("/settings/accent", data={"accent": "banana"}).status_code == 400
    r = client.get("/settings/accent-preview", params={"c": "#14b8a6", "s": "light"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/css") and "--accent:" in r.text
    assert client.get("/settings/accent-preview", params={"c": "nope"}).status_code == 400


def test_frames_get_the_colour_too(client):
    client.post("/settings/accent", data={"accent": "#14b8a6", "ajax": "1"})
    css = frametheme.tokens("custom-dark")
    assert "--bg:" in css and ":root:root:root{--accent:" in css
    assert frametheme.tokens("custom-light").count("color-scheme") >= 1


def test_the_old_designs_move_to_the_nearest_one_with_their_colour(env):
    from carassistant import db
    from carassistant.db import SCHEMA_DIR

    sql = (SCHEMA_DIR / "migrations_42.sql").read_text(encoding="utf-8")
    with db.tx() as conn:
        conn.execute("DELETE FROM settings WHERE key IN ('ui.theme', 'ui.accent')")
        conn.execute("INSERT INTO settings(key, value) VALUES('ui.theme', 'sunset')")
        conn.execute("INSERT INTO vehicles(name, slug, fuel_type, theme) VALUES('A', 'a', 'petrol', 'frost')")
        conn.execute("INSERT INTO vehicles(name, slug, fuel_type, theme) VALUES('B', 'b', 'petrol', 'auto')")
        conn.executescript(sql)
        assert db.get_setting(conn, "ui.theme", "") == "custom-dark" and db.get_setting(conn, "ui.accent", "") == "#ff7a1a"
        got = {r["slug"]: r["theme"] for r in conn.execute("SELECT slug, theme FROM vehicles WHERE slug IN ('a', 'b')")}
        assert got == {"a": "custom-light", "b": "custom-auto"}


def test_the_first_start_page_asks_for_language_and_design(client):
    page = client.get("/setup/language").text
    assert 'id="lang-sel"' in page and 'name="theme"' in page and 'id="accent-pick"' in page
    assert page.count('name="theme"') == 4  # Classic red, Light, Dark, Auto
    assert 'form="lang-form"' in page  # Continue belongs to the language form, which sits above the design


def test_the_frame_of_the_icon_follows_the_design(client):
    import io

    from PIL import Image

    from carassistant import appicon

    def edge(size=192):
        icon = Image.open(io.BytesIO(client.get(f"/icon/{size}.png").content)).convert("RGB")
        return icon.getpixel((size // 2, 4))  # the top edge of the frame

    classic = edge()
    assert classic[0] > classic[1]  # red-ish at the top: the classic frame
    client.post("/settings/theme", data={"theme": "custom-dark"})
    client.post("/settings/accent", data={"accent": "#2f8cff", "ajax": "1"})
    blue = edge()
    assert blue[2] > blue[0]  # the frame wears the colour of the design - the car inside is still the app icon
    assert appicon.themed(None)
    client.post("/settings/theme", data={"theme": "default"})  # Classic red again: the original icon, as drawn
    assert edge() == classic and not appicon.themed(None)


def test_any_colour_stays_visible_and_readable_on_its_design():
    """A pale colour on the light design (or a dark one on the dark design) is deepened / lightened until it can be seen (3 : 1) and read as text (4.5 : 1)."""
    import re

    from carassistant import themes

    for colour in ("#00ffab", "#ffff00", "#ff0000", "#3ddc84", "#ffffff", "#000000", "#2f8cff", "#a855f7"):
        for scheme in ("light", "dark"):
            css = themes.accent_css(colour, scheme)
            main = re.search(r"--accent:(#[0-9a-f]{6})", css).group(1)
            ink = re.search(r"--accent-ink:(#[0-9a-f]{6})", css).group(1)
            surface = themes.SURFACE[scheme]
            assert themes.contrast(main, surface) >= 2.9, (colour, scheme, main)
            assert themes.contrast(ink, surface) >= 4.4, (colour, scheme, ink)
