from carassistant import db, summary
from conftest import demo_car


def test_demo_data_fills_every_area(client):
    """The made-up car that the demo backups are made from has data in every module and every page opens."""
    page = client.get("/vehicles/new").text
    assert "/vehicles/demo" in page  # "just have a look" asks first, then loads from the standard source
    vid = demo_car(client)
    with db.tx() as conn:
        for table in ("odometer", "service", "appointments", "mods", "parts", "tires", "tasks", "fuel", "trips", "counters", "live"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE vehicle_id = ?", (vid,)).fetchone()[0] > 0, table
        assert conn.execute("SELECT COUNT(*) FROM trip_points").fetchone()[0] > 0
        from carassistant import appicon, equipment

        assert appicon.has_custom(vid)  # a demo car has its own icon

        groups = equipment.groups(conn, vid)  # equipment in every area, with every status, codes and notes
        assert len(groups) == 12 and all(g["total"] >= 4 for g in groups)
        assert {r["status"] for g in groups for r in g["items"]} == set(equipment.STATUSES)
        assert all({r["status"] for r in g["items"]} == set(equipment.STATUSES) for g in groups)
        assert conn.execute("SELECT COUNT(*) FROM equipment WHERE vehicle_id = ? AND code != ''", (vid,)).fetchone()[0] > 20
        assert conn.execute("SELECT COUNT(*) FROM equipment WHERE vehicle_id = ? AND note != ''", (vid,)).fetchone()[0] > 5
        assert summary.current_odometer(conn, vid) > 80000
    for path in (
        "",
        "/e/service",
        "/e/fuel",
        "/e/trips",
        "/e/appointments",
        "/e/tasks",
        "/e/parts",
        "/e/mods",
        "/e/tires",
        "/edit",
        "/report",
        "/trips/1",
        "/widgets",
        "/security",
    ):
        assert client.get(f"/v/{vid}{path}").status_code == 200, path


def test_demo_css_variable_safe_area_is_embedded_aware(env):
    from pathlib import Path

    import carassistant

    css = (Path(carassistant.__file__).parent / "static" / "app.css").read_text()
    assert "html.embedded { --safe-top: 0px" in css and "env(safe-area-inset-top)" in css
