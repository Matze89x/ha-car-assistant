from carassistant import themes


def test_light_themes_exist_and_declare_their_scheme(client):
    assert list(themes.available()[:4]) == ["default", "custom-light", "custom-dark", "custom-auto"]  # the designs, in this order
    assert not {"ocean", "sunset", "frost", "light", "auto"} & set(themes.available())  # the base files are not offered on their own
    assert themes.meta("light")[0] == "light" and themes.meta("light")[1] == "#eef0f4"
    assert themes.meta("custom-dark")[0] == "dark" and themes.meta("default") == ("dark", "#0d1016")
    client.post("/vehicles", data={"name": "A", "fuel_type": "petrol"})
    client.post("/settings/theme", data={"theme": "custom-light"})
    page = client.get("/settings/design").text
    assert 'data-theme="light"' in page and 'content="light"' in page and "#eef0f4" in page


def test_no_hard_coded_white_overlays_left(env):
    from pathlib import Path

    import carassistant

    for name in ("app.css", "pc-core.css"):
        css = (Path(carassistant.__file__).parent / "static" / name).read_text()
        bad = [ln for ln in css.splitlines() if "rgba(255,255,255" in ln.replace(" ", "") and "primary" not in ln and "--fg-rgb:" not in ln]
        assert not bad, bad[:2]


def test_auto_theme_follows_the_device(client):
    from pathlib import Path

    import carassistant

    assert themes.meta("auto")[0] == "auto"
    assert (Path(carassistant.__file__).parent / "static" / "themes" / "auto.css").read_text().startswith("/* scheme: auto */")
    client.post("/vehicles", data={"name": "A", "fuel_type": "petrol"})
    client.post("/settings/theme", data={"theme": "custom-auto"})
    page = client.get("/settings/design").text
    assert 'data-theme="auto"' in page and 'content="light dark"' in page and "prefers-color-scheme: light" in page
    assert "themes/light.css" in page and 'media="(prefers-color-scheme: light)"' in page and "/static/embed.js" in page


def test_page_changes_use_a_view_transition(env):
    from pathlib import Path

    import carassistant

    css = (Path(carassistant.__file__).parent / "static" / "pc-core.css").read_text()
    assert "@view-transition { navigation: auto; }" in css
