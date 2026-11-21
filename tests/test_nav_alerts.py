"""Alert dots on the tabs: a page with an open point (overdue / due soon) gets a dot, Home never does."""

import re

from tests.test_web import create_vehicle, slug

from carassistant import db, navigation


def alert_tabs(html: str) -> set[str]:
    bar = html.split('id="tabbar"')[1].split("</nav>")[0]
    return set(re.findall(r'href="([^"]+)" class="tab[^"]*" data-alert="1"', bar))


def add_appointment(vid: int, due: str = "2000-01-01", kind: str = "inspection") -> None:
    with db.tx() as conn:
        conn.execute("INSERT INTO appointments(vehicle_id, title, due_date, kind) VALUES(?, 'HU', ?, ?)", (vid, due, kind))


def add_overdue_task(vid: int) -> None:
    with db.tx() as conn:
        conn.execute("DELETE FROM tasks WHERE vehicle_id = ?", (vid,))
        conn.execute("INSERT INTO tasks(vehicle_id, title, interval_months, last_date) VALUES(?, 'Oil', 12, '2000-01-01')", (vid,))


def test_no_dots_without_open_points(client):
    vid = create_vehicle(client)
    html = client.get(f"/v/{slug(vid)}").text
    assert alert_tabs(html) == set()
    assert 'data-alert="1"' not in html


def test_open_appointment_marks_security_but_not_home_or_service(client):
    vid = create_vehicle(client)
    add_appointment(vid)
    for path in (f"/v/{slug(vid)}", f"/v/{slug(vid)}/e/fuel", f"/v/{slug(vid)}/more"):  # the dot is on every page of the vehicle
        assert alert_tabs(client.get(path).text) == {f"/v/{slug(vid)}/security"}, path


def test_due_maintenance_marks_security_and_service(client):
    vid = create_vehicle(client)
    add_overdue_task(vid)
    assert alert_tabs(client.get(f"/v/{slug(vid)}").text) == {f"/v/{slug(vid)}/security", f"/v/{slug(vid)}/e/service"}


def test_more_gets_the_dot_when_the_page_sits_in_more(client):
    vid = create_vehicle(client)
    add_appointment(vid)
    order = ["service", "trips", "fuel", "tires", "security"]  # security is pushed out of the bar
    assert client.post(f"/v/{slug(vid)}/navigation", data={"m": order, "i": [""] * len(order)}).status_code == 303
    assert alert_tabs(client.get(f"/v/{slug(vid)}").text) == {f"/v/{slug(vid)}/more"}
    client.post(f"/v/{slug(vid)}/navigation", data={"reset": "1"})
    assert alert_tabs(client.get(f"/v/{slug(vid)}").text) == {f"/v/{slug(vid)}/security"}


def test_disabled_module_raises_no_dot(client):
    vid = create_vehicle(client)
    add_appointment(vid)
    client.post("/integrations/module/security", data={"enabled": "0"})
    assert alert_tabs(client.get(f"/v/{slug(vid)}").text) == {
        f"/v/{slug(vid)}/e/appointments"
    }  # the next page that carries the point takes over
    client.post("/integrations/module/appointments", data={"enabled": "0"})
    assert alert_tabs(client.get(f"/v/{slug(vid)}").text) == set()  # nothing left that could show it


def test_alerts_function(client):
    vid = create_vehicle(client)
    add_appointment(vid, kind="service")
    with db.tx() as conn:
        assert navigation.alerts(conn, vid) == {"security", "appointments"}
        assert navigation.alerts(conn, None) == set()


def test_dot_is_announced_to_screen_readers(client):
    vid = create_vehicle(client)
    add_appointment(vid)
    html = client.get(f"/v/{slug(vid)}").text
    assert "needs attention" in html.split('id="tabbar"')[1].split("</nav>")[0]
