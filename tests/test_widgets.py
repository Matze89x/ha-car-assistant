"""Home widgets: one uniform grid, arranged per vehicle (order, size, visibility)."""

from pathlib import Path

from tests.test_web import create_vehicle, slug

from carassistant import db, widgets


def test_default_layout_and_edit_page(client):
    vid = create_vehicle(client)
    html = client.get(f"/v/{slug(vid)}").text
    assert (
        'class="wgrid"' in html and 'id="wd-toggle"' in html and 'id="pe"' in html
    )  # "Edit page" sits at the bottom of Home and opens the window
    assert "Car Assistant 0." not in html  # the version only sits in More
    page = client.get(f"/v/{slug(vid)}/widgets")
    assert page.status_code == 200 and page.text.count('name="k"') == len(widgets.REGISTRY)
    assert f'href="/v/{slug(vid)}/integrations"' in page.text  # the "+" leads to the integrations of this vehicle


def test_move_resize_hide_and_reset(client):
    vid = create_vehicle(client)
    base = f"/v/{slug(vid)}/widgets"
    order = [w.key for w in widgets.REGISTRY]
    moved = list(order)
    i, j = moved.index("security"), moved.index("service")
    moved[i], moved[j] = moved[j], moved[i]  # the order is the order of the rows: dragged with the handle, saved with the form
    form = {"k": moved, "size_security": "m", "on_security": "1", "on_service": "1"}
    r = client.post(base, data=form, follow_redirects=False)
    assert r.status_code == 303
    with db.tx() as conn:
        lay = widgets.layout(conn, vid)
    assert [w.key for w in lay][:3] == ["messages", "service", "security"] and lay[2].size == "m" and lay[2].on
    assert not next(w for w in lay if w.key == "appointments").on  # unchecked = hidden
    client.post(
        f"/v/{slug(vid)}/e/appointments", data={"title": "HU", "due_date": "2031-05-20", "kind": "inspection"}
    )  # widgets exist only with data
    html = client.get(f"/v/{slug(vid)}").text
    assert (
        'class="wd-slot m' in html and 'class="wd-slot s off" data-k="appointments"' in html
    )  # hidden = dimmed in the editor, gone outside it
    assert 'id="wd-toggle"' in html and 'id="wd-tpl"' in html
    client.post(base, data={"reset": "1"})
    with db.tx() as conn:
        assert [w.key for w in widgets.layout(conn, vid)] == order and [w.on for w in widgets.layout(conn, vid)] == [
            w.on for w in widgets.REGISTRY
        ]  # back to the defaults


def test_unknown_or_broken_layout_is_ignored(client):
    vid = create_vehicle(client)
    with db.tx() as conn:
        db.set_setting(conn, f"home.widgets.{vid}", '[{"k": "nope"}, 5, {"k": "fuel", "s": "xl", "on": false}]')
        lay = widgets.layout(conn, vid)
    assert lay[0].key == "fuel" and lay[0].size == "s" and not lay[0].on and len(lay) == len(widgets.REGISTRY)
    assert client.get(f"/v/{slug(vid)}").status_code == 200


def test_partial_save_keeps_the_places_of_widgets_without_data(client):
    vid = create_vehicle(client)
    with db.tx() as conn:
        widgets.save(conn, vid, ["location", "security"], {"location": "m", "security": "s"}, {"location", "security"})
        lay = widgets.layout(conn, vid)
    keys = [w.key for w in lay]
    assert keys.index("location") < keys.index("security") and len(keys) == len(widgets.REGISTRY)  # the two swapped, the rest kept
    assert next(w for w in lay if w.key == "location").size == "m"


def test_the_unit_of_a_plugin_tile_is_shown_in_the_language_of_the_app(env):
    """A plugin that writes "days" gets "Tage" in a German app; its own translation (l10n -> unit) wins; any other unit stays as written."""
    from carassistant import addons, config, db, widgets

    def tile(**kw):
        return {"id": "t", "label": "Service in", "icon": "wrench", "data": "service_due_days", **kw}

    with db.tx() as conn:
        db.set_setting(conn, "language", "de")
    config.forget_settings()
    assert widgets.tile_unit(tile(unit="days")) == "Tage" and widgets.tile_unit(tile(unit="Hours")) == "Std."
    assert widgets.tile_unit(tile(unit="days", l10n={"de": {"unit": "Tg."}})) == "Tg."  # the plugin's own word wins
    assert widgets.tile_unit(tile(unit="km")) == "km" and widgets.tile_unit(tile(unit="°C")) == "°C" and widgets.tile_unit(tile()) == ""
    with db.tx() as conn:
        db.set_setting(conn, "language", "en")
    config.forget_settings()
    assert widgets.tile_unit(tile(unit="days")) == "days"
    cleaned = addons.clean_tiles(
        [{"id": "a", "label": "A", "data": "service_due_days", "unit": "days", "l10n": {"de": {"label": "A", "unit": "Tage", "junk": "x"}}}]
    )
    assert cleaned[0]["l10n"]["de"]["unit"] == "Tage" and "junk" not in cleaned[0]["l10n"]["de"]  # the unit is kept (and only known keys)


def test_the_odometer_widget_shows_only_the_months_under_its_figure(client):
    """Under the figure: the kilometres of the last six months as bars (this month marked), the average a day, this month, the progress to the next service.
    Only worked out while the widget is switched on (it is off until somebody turns it on)."""
    from tests.conftest import demo_car
    from tests.test_web import slug

    vid = demo_car(client)
    base = f"/v/{slug(vid)}"
    assert "odo-wd-foot" not in client.get(base).text  # off by default: nothing is worked out, nothing is shown
    order = [w.key for w in widgets.REGISTRY]
    client.post(f"{base}/widgets", data={"k": order, "on_odometer": "1", "size_odometer": "s", "opt_odometer_design": "drums"})
    page = client.get(base).text
    assert (
        page.count('class="odo-wd-foot"') == 3 and page.count('class="minibars"') >= 3
    )  # all three looks (drums, tile, plate) carry the six months under the figure
    assert page.count('class="mb top"') >= 2 or 'class="mb top"' in page  # this month is the marked bar
    assert 'wd-t">Kilometerstand' not in page and 'class="wd-t">Odometer' in page  # the short title: it fits the small tile
    assert "odo-wd-stats" not in page and "a day" not in page and "this month" not in page  # only the bars: no average, no month sum
    assert all(
        "odo-next" not in chunk.split("</section>")[0] for chunk in page.split('class="odo-wd-foot"')[1:]
    )  # and no way to the next service in it


def _appointments_tile(client, slug_, days: list[tuple[str, int]]) -> str:
    """Home with the given appointments (title, days from today): just the HTML of the appointments tile."""
    from datetime import date, timedelta

    for title, n in days:
        client.post(
            f"/v/{slug_}/e/appointments",
            data={"title": title, "due_date": (date.today() + timedelta(days=n)).isoformat(), "kind": "inspection"},
        )
    page = client.get(f"/v/{slug_}").text
    start = page.index("wc-c6")
    return page[start : page.index("</a>", start)]


def test_the_appointments_tile_colours_the_number_like_the_state_and_shows_the_day(client):
    """37 days left is fine, so the number is green (it used to fall back to the red of the tile); the weekday stands before the date; the one after
    it is a small line of its own, and the number does not repeat itself as a chip."""
    from datetime import date, timedelta

    vid = create_vehicle(client)
    tile = _appointments_tile(client, slug(vid), [("First aid kit", 37), ("Inspection", 120), ("Tyres", 200)])
    assert 'class="wd-count ok"' in tile and "<b>37</b>" in tile and "days left" in tile
    assert 'class="badge' not in tile  # no second chip with the same figure
    day = date.today() + timedelta(days=37)
    assert f", {day.strftime('%d.%m.%Y')}" in tile or f", {day.strftime('%Y-%m-%d')}" in tile or f", {day.strftime('%m/%d/%Y')}" in tile
    assert day.strftime("%a") in tile  # Mon ... Sun in English
    assert 'class="wd-next"' in tile and "Inspection" in tile and "in 120 d" in tile and "+1" in tile


def test_the_appointments_tile_for_one_day_today_and_overdue(client):
    vid = create_vehicle(client)
    tile = _appointments_tile(client, slug(vid), [("Old", -3), ("Soon", 1)])
    assert 'class="wd-count overdue"' in tile and "<b>3</b>" in tile and "days overdue" in tile
    assert 'class="wd-next"' in tile and 'class="soon"' in tile  # the one after: due tomorrow, in the colour of "soon"
    vid2 = create_vehicle(client, name="Second")
    tile = _appointments_tile(client, slug(vid2), [("Tomorrow", 1)])
    assert 'class="wd-count soon"' in tile and "<b>1</b>" in tile and "day left" in tile and "days left" not in tile
    assert "wd-next" not in tile  # nothing after it: no empty line
    vid3 = create_vehicle(client, name="Third")
    tile = _appointments_tile(client, slug(vid3), [("Today", 0)])
    assert "<b>Today</b>" in tile and "due" in tile


def test_weekday_of_a_date():
    from datetime import date, datetime

    from carassistant import regional

    assert regional.weekday("2026-11-24") == 1 and regional.weekday(date(2026, 11, 22)) == 6
    assert regional.weekday(datetime(2026, 11, 23, 9, 0)) == 0 and regional.weekday(None) is None and regional.weekday("soon") is None


def test_an_overdue_tile_is_red_and_a_soon_tile_amber_like_everywhere_else():
    css = (Path(widgets.__file__).parent / "static" / "pc-core.css").read_text(encoding="utf-8")
    assert ".wd.st-warn .wd-v { color: var(--overdue); }" in css and ".wd.st-soon .wd-v { color: var(--soon); }" in css
    assert ".wd.st-warn .wd-v, .wd.st-soon .wd-v" not in css  # they once shared the amber: an overdue tile looked like a "soon" one


def test_the_odometer_is_locked_only_while_the_plugin_that_reported_it_exists(client):
    """A plugin reports the odometer: it is shown, not typed, and the dashboard has no odometer of its own. When the plugin (its key) is gone, the person
    gets the odometer back - the last reading stays - instead of a plate that can never be changed again."""
    from carassistant import connectors, summary

    vid = create_vehicle(client)
    with db.tx() as conn:
        assert summary.odometer_from_car(conn, vid) is False  # typed at the start: a person's
        token = connectors.create_token(conn, "my-plugin", vid)
        row = conn.execute("SELECT id FROM api_tokens WHERE name = 'my-plugin'").fetchone()
        summary.record_odometer(conn, vid, 51_000, "api:my-plugin")
        assert summary.odometer_from_car(conn, vid) is True
        conn.execute("UPDATE vehicles SET bind_odometer = NULL WHERE id = ?", (vid,))
        connectors.delete_token(conn, row["id"])  # the plugin is removed, its key goes with it
        assert summary.odometer_from_car(conn, vid) is False
        assert summary.current_odometer(conn, vid) == 51_000  # the reading stays
        summary.record_odometer(conn, vid, 51_200, "ha")  # a Home Assistant entity
        assert summary.odometer_from_car(conn, vid) is False  # ... but none is set for this car
        conn.execute("UPDATE vehicles SET bind_odometer = 'sensor.km' WHERE id = ?", (vid,))
        assert summary.odometer_from_car(conn, vid) is True
    assert token


def test_the_two_list_widgets_let_the_person_choose_the_columns(client):
    """Vehicle messages and Needs attention: automatic (two columns when there is room), one column, or two - chosen in the widget's settings like the look
    of the odometer."""
    from tests.conftest import demo_car

    vid = demo_car(client)
    base = f"/v/{slug(vid)}"
    for key in ("messages", "attention"):
        w = next(w for w in widgets.REGISTRY if w.key == key)
        assert w.options == (("columns", ("auto", "one", "two")),) and w.opts == {"columns": "auto"}
    page = client.get(base).text
    assert 'data-k="attention"' in page and 'data-opt-columns="auto"' in page
    order = [w.key for w in widgets.REGISTRY]
    form = {
        "k": order,
        "on_messages": "1",
        "size_messages": "m",
        "opt_messages_columns": "one",
        "on_attention": "1",
        "size_attention": "m",
        "opt_attention_columns": "two",
    }
    client.post(f"{base}/widgets", data=form)
    with db.tx() as conn:
        chosen = {w.key: w.opts["columns"] for w in widgets.layout(conn, vid) if w.key in ("messages", "attention")}
    assert chosen == {"messages": "one", "attention": "two"}
    page = client.get(base).text
    assert 'data-opt-columns="one"' in page and 'data-opt-columns="two"' in page
    client.post(f"{base}/widgets", data={**form, "opt_messages_columns": "bogus"})  # an unknown choice keeps the old one
    with db.tx() as conn:
        assert next(w for w in widgets.layout(conn, vid) if w.key == "messages").opts["columns"] == "one"
