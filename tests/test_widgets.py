"""Home widgets: one uniform grid, arranged per vehicle (order, size, visibility)."""

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
        assert [w.key for w in widgets.layout(conn, vid)] == order and all(w.on for w in widgets.layout(conn, vid))


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
