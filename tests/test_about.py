from carassistant import about
from conftest import demo_car


def test_about_page_lists_vehicles_and_plugins(client):
    demo_car(client)
    page = client.get("/about")
    assert page.status_code == 200
    assert "Demo connector" in page.text
    assert "Matze89x" in page.text
    assert "about-stat" in page.text


def test_about_in_more_list(client):
    assert "/about" in client.get("/more").text


def test_human_size(monkeypatch):
    from carassistant import config

    monkeypatch.setattr(config, "language", lambda: "en")
    assert about.human(512) == "512 B"
    assert about.human(2048) == "2.0 KB"


def test_long_lists_are_paged(client, env):
    from carassistant import db, lists

    demo_car(client)
    with db.tx() as conn:
        vid = conn.execute("SELECT id FROM vehicles ORDER BY id LIMIT 1").fetchone()[0]
        for i in range(lists.size() * 2 + 5):
            conn.execute("INSERT INTO parts(vehicle_id, name, date) VALUES(?, ?, '2020-01-01')", (vid, f"Part {i}"))
    first = client.get(f"/v/{vid}/e/parts")
    second = client.get(f"/v/{vid}/e/parts?page=2")
    huge = client.get(f"/v/{vid}/e/parts?page=999")
    assert first.status_code == second.status_code == huge.status_code == 200
    assert "page=2" in first.text and "pager" in first.text
    assert first.text.count('<article class="rec') <= lists.size()
    assert huge.text.count('<article class="rec') > 0  # out-of-range page falls back to the last one
    assert 'data-more="' in first.text and "data-more=" not in huge.text  # scroll loading: next batch address, none on the last page


def test_route_svg_thins_huge_tracks_quickly():
    import time

    from carassistant import charts

    points = [(50 + i * 1e-5, 8 + i * 1e-5) for i in range(60000)]
    start = time.perf_counter()
    svg = charts.route_svg(points)
    assert time.perf_counter() - start < 1.0
    assert svg.count("L") <= charts.MAX_ROUTE_POINTS + 2
    assert 'class="end"' in svg


def test_about_and_charging_wording_in_german(client, env):
    from carassistant import db

    demo_car(client, electric=True)
    with db.tx() as conn:
        db.set_setting(conn, "language", "de")
    page = client.get("/about").text
    assert "Über" in page and "Installiert je Fahrzeug" in page and "Kaffee spendieren" in page
    assert "about." not in page  # no untranslated key shows


def test_documents_are_paged_too(client):
    from carassistant import db, lists

    demo_car(client)
    with db.tx() as conn:
        vid = conn.execute("SELECT id FROM vehicles ORDER BY id LIMIT 1").fetchone()[0]
        for i in range(lists.size() + 3):
            conn.execute(
                "INSERT INTO documents(vehicle_id, title, category, filename, mime, size, created_at) VALUES(?, ?, 'other', 'f.pdf', 'application/pdf', 10, '2024-01-01')",
                (vid, f"Doc {i}"),
            )
    page = client.get(f"/v/{vid}/docs").text
    assert page.count('class="rec doc-rec"') == lists.size() and 'data-into="#doclist"' in page


def test_sizes_use_the_decimal_comma_in_german(monkeypatch):
    from carassistant import about, config

    monkeypatch.setattr(config, "language", lambda: "de")
    assert about.human(2048) == "2,0 KB" and about.human(512) == "512 B"
    monkeypatch.setattr(config, "language", lambda: "en")
    assert about.human(2048) == "2.0 KB"
