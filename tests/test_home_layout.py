from pathlib import Path

from tests.test_web import create_vehicle
from tests.test_web import slug as slug_of

from carassistant import db


def test_empty_home_offers_first_steps_and_a_lone_tile_fills_its_row(client):
    vid = create_vehicle(client, "Empty Car")
    slug = slug_of(vid)
    with db.tx() as conn:
        conn.execute("DELETE FROM tasks WHERE vehicle_id = ?", (vid,))
        conn.execute("DELETE FROM service WHERE vehicle_id = ?", (vid,))
    page = client.get(f"/v/{slug}").text
    assert "wd-start" in page and f"/v/{slug}/e/fuel" in page  # nothing to show yet: first steps instead of a hole
    client.post(f"/v/{slug}/e/fuel", data={"date": "2026-11-01", "amount": "40", "price_total": "60", "odometer_km": "42000"})
    page = client.get(f"/v/{slug}").text
    assert "wd-start" not in page and 'wd-slot s fill" data-k="fuel"' in page  # a single small tile spans the row


def test_boxes_reach_into_a_photo_but_the_photo_never_covers_the_name():
    from pathlib import Path

    css = (Path(__file__).parents[1] / "carassistant/app/carassistant/static/pc-core.css").read_text()
    # the boxes keep reaching into the picture (the rule of the glass boxes) ...
    assert ".hero-pic { margin-block: calc(-1 * (12px + var(--inset))); }" in css
    assert ".hero-row { padding-inline: var(--inset); }" in css
    # ... but only where a row exists: without one the photo must not creep over the name or the model line
    assert ":not(.has-top) .hero-pic { margin-top: 0; }" in css and ":not(.has-bottom) .hero-pic { margin-bottom: 0; }" in css
    assert ".hero-car-wrap:not(.glow):not(.has-video) + .odo-card { margin-top: 0; }" in css


def test_change_car_button_sits_next_to_the_car_name_with_two_cars(client):
    first = create_vehicle(client, "First")
    page = client.get(f"/v/{slug_of(first)}/e/fuel").text
    assert 'class="ph-s"' in page and "cur-switch" not in page.split('class="ph-s"')[1].split("</div>")[0]  # one car: no button
    create_vehicle(client, "Second")
    assert "cur-switch" in client.get(f"/v/{slug_of(first)}/e/fuel").text.split('class="ph-s"')[1].split("</div>")[0]


def test_hero_edit_button_is_not_centred_with_a_transform():
    from pathlib import Path

    css = (Path(__file__).parents[1] / "carassistant/app/carassistant/static/pc-core.css").read_text()
    rule = next(line for line in css.splitlines() if line.startswith(".hero-edit {"))
    assert "translate" not in rule  # button:active sets transform: scale(), which would drop the centring and make it jump


def test_next_service_by_km_picks_the_task_due_first(client):
    from carassistant import summary

    vid = create_vehicle(client, "Km Car")
    with db.tx() as conn:
        conn.execute("DELETE FROM tasks WHERE vehicle_id = ?", (vid,))
        conn.execute("DELETE FROM service WHERE vehicle_id = ?", (vid,))
        conn.execute("INSERT INTO tasks(vehicle_id, title, interval_km, last_km) VALUES(?, 'Far', 30000, 1000)", (vid,))
        conn.execute("INSERT INTO tasks(vehicle_id, title, interval_km, last_km) VALUES(?, 'Soon', 10000, 5000)", (vid,))
        nxt = summary.next_service_km(conn, vid, 9000)
        assert nxt == {"title": "Soon", "km_left": 6000, "pct": 40}
        over = summary.next_service_km(conn, vid, 16000)
        assert over["km_left"] == -1000 and over["pct"] == 100  # overdue: the bar is full
        assert summary.next_service_km(conn, vid, None) is None


def test_odometer_drums_follow_the_server_units(client):
    vid = create_vehicle(client, "Mile Car")  # the test car starts at 50,000 km
    client.post("/settings/units", data={"units": "us", "currency": "USD"})
    page = client.get(f"/v/{slug_of(vid)}").text
    assert 'aria-label="31,069 mi"' in page and ">mi</span>" in page  # 50,000 km shown as miles: digits and unit


def test_odometer_widget_look_is_saved_per_car(client):
    from carassistant import widgets

    vid = create_vehicle(client, "Look Car")
    with db.tx() as conn:
        assert {w.key: w.design for w in widgets.layout(conn, vid)}["odometer"] == "drums"  # default look
    client.post(
        f"/v/{vid}/widgets",
        data={"ajax": "1", "k": ["odometer", "fuel"], "size_odometer": "s", "on_odometer": "1", "opt_odometer_design": "tile"},
    )
    with db.tx() as conn:
        odo = next(w for w in widgets.layout(conn, vid) if w.key == "odometer")
    assert odo.design == "tile" and odo.size == "s"
    client.post(f"/v/{vid}/widgets", data={"ajax": "1", "k": ["odometer"], "opt_odometer_design": "nonsense", "on_odometer": "1"})
    with db.tx() as conn:
        assert next(w for w in widgets.layout(conn, vid) if w.key == "odometer").design == "tile"  # an unknown look changes nothing


def test_trip_duration_and_widget_extra_lines():
    from carassistant import web

    row = lambda a, b: {"start_time": a, "end_time": b}  # noqa: E731
    assert web._trip_duration(row("08:10", "08:52")) == "42 min"
    assert web._trip_duration(row("23:30", "00:45")) == "1 h 15 min"  # past midnight
    assert web._trip_duration(row("", "09:00")) == "" and web._trip_duration(None) == ""


def test_the_start_page_with_several_cars_preselects_no_car(client):
    create_vehicle(client, "Car One")
    create_vehicle(client, "Car Two")
    page = client.get("/").text
    assert (
        'class="sb-car"' not in page and "Drive · Log · Go" in page
    )  # the side bar names no car (name and slogan then sit centred next to the logo)
    assert 'id="tabbar"' not in page and "/e/fuel" not in page.split("<main", 1)[0]  # choosing a car: no navigation at all, only the logo


def test_a_car_can_have_its_own_design(client):
    vid = create_vehicle(client, "Design Car")
    slug = slug_of(vid)
    system = client.get(f"/v/{slug}").text
    assert 'data-theme="light"' not in system
    client.post(f"/v/{slug}/theme", data={"theme": "custom-light"})  # chosen on the Car tab of the settings
    assert 'data-theme="light"' in client.get(f"/v/{slug}").text  # on the car's pages
    assert 'data-theme="light"' in client.get(f"/v/{slug}/more").text  # also on its More page
    assert 'data-theme="light"' not in client.get("/about").text  # elsewhere the system design
    form = client.get(f"/settings/car?car={slug}").text
    assert 'action="/v/' + slug + '/theme"' in form and 'value="custom-light"' in form and "checked" in form
    assert 'name="theme"' not in client.get(f"/v/{slug}/edit?mode=form").text  # the passport no longer carries the design
    assert 'data-theme="light"' not in client.get("/settings/user").text  # the other tabs show the system's own design
    client.post(f"/v/{slug}/theme", data={"theme": ""})
    assert 'data-theme="light"' not in client.get(f"/v/{slug}").text  # back to the system


def test_hidden_widgets_are_not_displayed_outside_edit_mode():
    css = (Path(__file__).parent.parent / "carassistant/app/carassistant/static/pc-core.css").read_text()
    assert ".wgrid:not(.editing) .wd-slot.off { display: none; }" in css
