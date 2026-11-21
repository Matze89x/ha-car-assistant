import io
import zipfile

from carassistant import backup, db


def create_vehicle(client, name="My Car"):
    r = client.post("/vehicles", data={"name": name, "fuel_type": "diesel", "odometer": "50000", "plate": "B-XY 1"})
    assert r.status_code == 303, r.text
    from carassistant import db

    with db.tx() as conn:  # the address is /v/<name>; the tests work with the id
        return conn.execute("SELECT MAX(id) FROM vehicles").fetchone()[0]


def slug(vid: int) -> str:
    """The readable address part of a vehicle (what the pages link to)."""
    from carassistant import db, slugs

    with db.tx() as conn:
        return slugs.slug_of(conn, vid)


def test_dashboard_empty_and_welcome(client):
    r = client.get("/")
    assert r.status_code == 200 and "Welcome to Car Assistant" in r.text
    assert client.get("/healthz").json()["status"] == "ok"


def test_ingress_prefix_is_applied_to_links_and_redirects(client):
    prefix = "/api/hassio_ingress/abc123_-X"
    r = client.get("/", headers={"X-Ingress-Path": prefix})
    assert f'href="{prefix}/vehicles/new"' in r.text and f"{prefix}/static/app.css" in r.text
    r = client.post("/vehicles", data={"name": "Car"}, headers={"X-Ingress-Path": prefix})
    assert r.headers["location"] == f"{prefix}/setup/functions"
    # a forged prefix must never be reflected
    r = client.get("/", headers={"X-Ingress-Path": '"><script>alert(1)</script>'})
    assert "<script>alert" not in r.text


def test_guard_blocks_non_ingress_clients(env, monkeypatch):
    from fastapi.testclient import TestClient

    from carassistant.web import app

    monkeypatch.delenv("CARASSISTANT_DEV")
    assert TestClient(app).get("/").status_code == 403
    assert TestClient(app, client=("172.30.32.2", 1234)).get("/").status_code == 200


def test_vehicle_lifecycle_and_validation(client):
    vid = create_vehicle(client)
    page = client.get(f"/v/{vid}")
    assert page.status_code == 200 and "50,000" in page.text and "My Car" in page.text
    bad = client.post("/vehicles", data={"name": "", "fuel_type": "petrol"})
    assert bad.status_code == 400 and "Required field missing" in bad.text
    bad = client.post("/vehicles", data={"name": "x", "vin": "!!"})
    assert bad.status_code == 400
    bad = client.post("/vehicles", data={"name": "x", "bind_odometer": "not an entity"})
    assert bad.status_code == 400
    r = client.post(f"/v/{vid}/edit", data={"name": "Renamed", "fuel_type": "petrol", "bind_odometer": "sensor.car_odo"})
    assert r.status_code == 303 and "Renamed" in client.get(f"/v/{vid}").text
    assert client.get("/v/999").status_code == 404
    assert client.post(f"/v/{vid}/archive").status_code == 303
    assert "Archived vehicles" in client.get("/").text
    assert client.post(f"/v/{vid}/delete").status_code == 303
    assert client.get(f"/v/{vid}").status_code == 404


def test_generic_entities_crud(client):
    vid = create_vehicle(client)
    for key, data in {
        "service": {"date": "2026-03-01", "title": "Oil change", "odometer_km": "51000", "cost": "120"},
        "mods": {"date": "2026-03-02", "title": "New exhaust"},
        "appointments": {"title": "TÜV", "due_date": "2027-03", "kind": "inspection"},
        "tires": {"name": "Winter set", "season": "winter"},
        "fuel": {"date": "2026-03-03", "odometer_km": "51100", "amount": "40", "price_per_unit": "1,6", "full_tank": "1"},
        "trips": {"date": "2026-03-04", "start_km": "51100", "end_km": "51140", "category": "business"},
        "tasks": {"title": "Wiper blades", "interval_months": "12"},
    }.items():
        r = client.post(f"/v/{vid}/e/{key}", data=data)
        assert r.status_code == 303, (key, r.text[:300])
        page = client.get(f"/v/{vid}/e/{key}")
        assert page.status_code == 200
    assert "Oil change" in client.get(f"/v/{vid}/e/service").text
    assert "03.2027" in client.get(f"/v/{vid}/e/appointments").text or "2027-03" in client.get(f"/v/{vid}/e/appointments").text
    assert client.get(f"/v/{vid}/e/nope").status_code == 404
    # validation error keeps the user's input and shows the message
    r = client.post(f"/v/{vid}/e/service", data={"date": "not-a-date", "title": "Keep me"})
    assert r.status_code == 400 and "Not a valid date" in r.text and "Keep me" in r.text
    # update + delete
    with db.tx() as conn:
        sid = conn.execute("SELECT id FROM service").fetchone()["id"]
    assert client.post(f"/v/{vid}/e/service/{sid}", data={"date": "2026-03-01", "title": "Edited"}).status_code == 303
    assert "Edited" in client.get(f"/v/{vid}/e/service").text
    assert client.post(f"/v/{vid}/e/service/{sid}/delete").status_code == 303
    assert "Edited" not in client.get(f"/v/{vid}/e/service").text


def test_cross_vehicle_isolation(client):
    a, b = create_vehicle(client, "A"), create_vehicle(client, "B")
    client.post(f"/v/{a}/e/service", data={"date": "2026-03-01", "title": "A only"})
    with db.tx() as conn:
        sid = conn.execute("SELECT id FROM service").fetchone()["id"]
    client.post(f"/v/{b}/e/service/{sid}/delete")  # wrong vehicle: must not delete
    assert "A only" in client.get(f"/v/{a}/e/service").text


def test_tasks_defaults_done_and_tire_mount(client):
    vid = create_vehicle(client)
    with db.tx() as conn:
        tid = conn.execute(
            "INSERT INTO tasks(vehicle_id, title, interval_km, interval_months) VALUES(?,?,?,?)", (vid, "Engine oil", 15000, 12)
        ).lastrowid
    assert client.post(f"/v/{vid}/e/tasks/{tid}/done").status_code == 303
    with db.tx() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (tid,)).fetchone()
    assert row["last_km"] == 50000 and row["last_date"]
    client.post(f"/v/{vid}/e/tires", data={"name": "S", "season": "summer"})
    client.post(f"/v/{vid}/e/tires", data={"name": "W", "season": "winter"})
    with db.tx() as conn:
        ids = [r["id"] for r in conn.execute("SELECT id FROM tires ORDER BY id")]
    client.post(f"/v/{vid}/e/tires/{ids[0]}/mount")
    client.post(f"/v/{vid}/e/tires/{ids[1]}/mount")
    with db.tx() as conn:
        mounted = [r["name"] for r in conn.execute("SELECT name FROM tires WHERE mounted = 1")]
    assert mounted == ["W"]


def test_report_page_and_trip_export(client):
    vid = create_vehicle(client)
    for date, km, amount in (("2026-01-01", 1000, 40), ("2026-02-01", 1500, 40)):
        client.post(
            f"/v/{vid}/e/fuel", data={"date": date, "odometer_km": str(km), "amount": str(amount), "price_total": "60", "full_tank": "1"}
        )
    page = client.get(f"/v/{vid}/report")
    assert page.status_code == 200 and "8.0" in page.text
    client.post(f"/v/{vid}/e/trips", data={"date": "2026-03-04", "start_km": "100", "end_km": "140", "purpose": "Meeting"})
    pdf = client.get(f"/v/{vid}/trips-export.pdf?start=2026-01-01&end=2026-12-31")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    csv = client.get(f"/v/{vid}/trips-export.csv")
    assert csv.status_code == 200 and b"Meeting" in csv.content
    assert client.get(f"/v/{vid}/trips-export.xml").status_code == 404


def test_gpx_import_and_trip_detail(client):
    vid = create_vehicle(client)
    gpx = (
        b'<gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>'
        b'<trkpt lat="52.5" lon="13.4"><time>2026-05-01T07:00:00Z</time></trkpt>'
        b'<trkpt lat="52.6" lon="13.5"><time>2026-05-01T07:30:00Z</time></trkpt></trkseg></trk></gpx>'
    )
    r = client.post(f"/v/{vid}/trips-import", files={"gpx": ("t.gpx", gpx, "application/gpx+xml")}, data={"category": "private"})
    assert r.status_code == 303 and "m=saved" in r.headers["location"]
    with db.tx() as conn:
        tid = conn.execute("SELECT id FROM trips").fetchone()["id"]
    detail = client.get(f"/v/{vid}/trips/{tid}")
    assert detail.status_code == 200 and "<svg" in detail.text
    assert b"<trkpt" in client.get(f"/v/{vid}/trips/{tid}/track.gpx").content
    bad = client.post(f"/v/{vid}/trips-import", files={"gpx": ("t.gpx", b"nope", "text/xml")})
    assert "err.gpx_invalid" in bad.headers["location"]


def test_documents_upload_download_delete(client, env):
    vid = create_vehicle(client)
    r = client.post(
        f"/v/{vid}/docs",
        files={"file": ("../../evil name.pdf", b"%PDF-1.4 test", "application/pdf")},
        data={"title": "Invoice", "category": "invoice"},
    )
    assert r.status_code == 303
    with db.tx() as conn:
        doc = conn.execute("SELECT * FROM documents").fetchone()
    assert doc["filename"] == "evil name.pdf"  # path components stripped
    got = client.get(f"/v/{vid}/docs/{doc['id']}")
    assert got.status_code == 200 and got.content.startswith(b"%PDF") and "attachment" in got.headers["content-disposition"]
    assert "Invoice" in client.get(f"/v/{vid}/docs").text
    exe = client.post(f"/v/{vid}/docs", files={"file": ("x.exe", b"MZ", "application/octet-stream")})
    assert "err.file_type" in exe.headers["location"]
    client.post(f"/v/{vid}/docs/{doc['id']}/delete")
    assert client.get(f"/v/{vid}/docs/{doc['id']}").status_code == 404


def test_vehicle_photo(client):
    vid = create_vehicle(client)
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buf, "PNG")
    png = buf.getvalue()
    r = client.post(f"/v/{vid}/edit", data={"name": "P", "fuel_type": "petrol"}, files={"photo": ("p.png", png, "image/png")})
    assert r.status_code == 303
    assert client.get(f"/v/{vid}/photo").content == png
    r = client.post(f"/v/{vid}/edit", data={"name": "P", "fuel_type": "petrol"}, files={"photo": ("p.svg", b"<svg/>", "image/svg+xml")})
    assert r.status_code == 400  # SVG would allow script injection – not allowed


def test_calendar_and_stations_and_settings_pages(client):
    vid = create_vehicle(client)
    client.post(f"/v/{vid}/e/appointments", data={"title": "HU", "due_date": "2027-05-20"})
    ics = client.get("/calendar.ics")
    assert b"BEGIN:VEVENT" in ics.content and ics.headers["content-type"].startswith("text/calendar")
    assert client.get(f"/v/{vid}/calendar.ics").status_code == 200
    assert client.get("/stations").headers["location"].endswith("/stations")  # the old address leads to the first car
    assert client.get(f"/v/{vid}/stations", follow_redirects=False).status_code == 303  # the stations are a part of the fuel page
    r = client.get(f"/v/{vid}/e/fuel?go=1&lat=95&lon=0&source=osm")
    assert r.status_code == 200 and "Invalid coordinates" in r.text
    assert client.get("/settings/design").status_code == 200
    assert client.post("/settings/notifications/test", data={"service": ""}).status_code in (303, 401)


def test_backup_roundtrip_and_malicious_archives(client, env):
    vid = create_vehicle(client, "Before")
    client.post(f"/v/{vid}/docs", files={"file": ("a.pdf", b"%PDF-data", "application/pdf")})
    data = client.get("/settings/backup.zip").content
    client.post(f"/v/{vid}/delete")
    assert client.get(f"/v/{vid}").status_code == 404
    r = client.post("/settings/restore", files={"backup": ("b.zip", data, "application/zip")}, data={"confirm": "1"})
    assert r.status_code == 303 and "restored" in r.headers["location"]
    assert "Before" in client.get(f"/v/{vid}").text
    assert (env / "files" / str(vid)).is_dir()
    assert list((env / "backups").glob("pre-restore-*.zip"))
    # rejects traversal, foreign archives and garbage; the live database must survive
    evil = io.BytesIO()
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("manifest.json", '{"app": "carassistant", "schema": 1}')
        zf.writestr("carassistant.db", b"x")
        zf.writestr("../../etc/passwd", "x")
    for payload in (evil.getvalue(), b"garbage"):
        try:
            backup.restore(payload)
        except backup.BackupError:
            pass
        else:
            raise AssertionError("malicious backup accepted")
    assert "Before" in client.get(f"/v/{vid}").text
    # restore requires explicit confirmation
    assert "err.required" in client.post("/settings/restore", files={"backup": ("b.zip", data, "application/zip")}).headers["location"]


def _direct(monkeypatch):
    from fastapi.testclient import TestClient

    from carassistant.web import app

    monkeypatch.delenv("CARASSISTANT_DEV")
    return TestClient(app, base_url="https://car.example.com", headers={"Origin": "https://car.example.com"}, follow_redirects=False)


def test_direct_access_is_locked_until_a_user_exists(env, monkeypatch):
    c = _direct(monkeypatch)
    page = c.get("/")
    assert page.status_code == 403 and "locked until a user exists" in page.text
    from carassistant import accounts, db

    with db.tx() as conn:
        accounts.create_user(conn, "owner", "a-long-password-12345", "Owner", True)
    assert c.get("/").status_code == 303  # now the login


def test_direct_post_requires_same_origin(env, monkeypatch):
    from carassistant import accounts, db

    with db.tx() as conn:
        accounts.create_user(conn, "owner", "a-long-password-12345", "Owner", True)
        session = accounts.create_session(conn, accounts.admin_id(conn))
    c = _direct(monkeypatch)
    cookies = {"ca_session": session}
    assert c.post("/settings/republish", cookies=cookies, headers={"Origin": "https://evil.example"}).status_code == 403
    assert c.post("/settings/republish", cookies=cookies).status_code in (303, 200)


def test_module_can_be_switched_off_and_on(client, conn, vehicle):
    conn.commit()
    assert client.get(f"/v/{vehicle}/e/parts").status_code == 200
    client.post("/integrations/module/parts", data={"enabled": "0"}, follow_redirects=False)
    assert client.get(f"/v/{vehicle}/e/parts").status_code == 404
    assert "/e/parts" not in client.get(f"/v/{vehicle}").text  # tab disappears
    client.post("/integrations/module/parts", data={"enabled": "1"}, follow_redirects=False)
    assert client.get(f"/v/{vehicle}/e/parts").status_code == 200


def test_core_modules_cannot_be_switched_off(client):
    assert client.post("/integrations/module/overview", data={"enabled": "0"}).status_code == 404


def test_single_vehicle_skips_list_and_switcher(client, conn, vehicle):
    conn.commit()
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith(f"/v/{vehicle}")
    assert "switcher" not in client.get(f"/v/{vehicle}").text


def test_second_vehicle_shows_switcher(client, conn, vehicle):
    conn.commit()
    client.post("/vehicles", data={"name": "Zweitwagen", "fuel_type": "petrol"}, follow_redirects=False)
    page = client.get(f"/v/{vehicle}/more").text
    assert "cur-switch" in page and "Zweitwagen" in page
    assert client.get("/", follow_redirects=False).status_code == 200


def test_tankerkoenig_key_and_language_from_ui(client, env):
    from carassistant import config

    client.post("/settings/fuelkey", data={"id": "tankerkoenig", "api_key": "abc-123"}, follow_redirects=False)
    assert config.tankerkoenig_key() == "abc-123"
    assert "abc-123" not in client.get("/settings/system").text  # secret is never echoed
    assert "settings/fuelkey" not in client.get("/settings/system").text  # the keys are set on the fuel page now
    client.post("/settings/language", data={"language": "de"}, follow_redirects=False)
    assert config.language() == "de"


def test_mqtt_default_is_broker_from_supervisor_without_password(client, monkeypatch):
    from carassistant import config

    monkeypatch.setenv("MQTT_HOST", "core-mosquitto")
    assert config.mqtt_settings()["host"] == "core-mosquitto"
    client.post("/integrations/mqtt", data={"enabled": "1", "host": "broker.lan", "port": "1884"}, follow_redirects=False)
    assert config.mqtt_settings() == {"host": "broker.lan", "port": 1884, "user": None, "password": None}


def test_first_own_broker_switches_the_sensors_on_and_the_switch_is_always_there(client):
    from carassistant import config

    assert 'name="enabled"' in client.get("/settings/system").text  # also without a broker, so nobody has to save twice
    assert not config.mqtt_discovery_enabled()
    client.post("/integrations/mqtt", data={"host": "broker.lan"}, follow_redirects=False)
    assert config.mqtt_discovery_enabled()
    client.post("/integrations/mqtt", data={"host": "broker.lan"}, follow_redirects=False)  # an explicit off stays off
    assert not config.mqtt_discovery_enabled()


def test_the_addon_option_switches_the_sensors_on_until_the_app_says_otherwise(client, monkeypatch):
    from carassistant import config

    monkeypatch.setenv("MQTT_SENSORS", "1")
    assert config.mqtt_discovery_enabled()
    client.post("/integrations/mqtt", data={}, follow_redirects=False)  # the switch in the app was saved off: that wins
    assert not config.mqtt_discovery_enabled()


def test_notifications_are_only_offered_on_an_https_page(client):
    from pathlib import Path

    js = (Path(__file__).resolve().parents[1] / "carassistant" / "app" / "carassistant" / "static" / "push.js").read_text()
    assert 'location.protocol !== "https:"' in js and "btn.hidden = true" in js  # nothing is offered on a page that is not https
    from carassistant import i18n

    assert i18n.translator("de")("push.https_only") != "push.https_only"
    assert i18n.translator("en")("push.https_only") != "push.https_only"


def test_a_manual_trip_is_checked_for_sense(client):
    url = f"/v/{create_vehicle(client)}/e/trips"
    base = {"date": "2020-01-02", "start_km": "1000", "end_km": "1100"}
    assert client.post(url, data=base, follow_redirects=False).status_code == 303
    for bad in ({"date": "2999-01-01"}, {"end_km": "9000"}, {"end_km": "900"}):
        assert client.post(url, data={**base, **bad}, follow_redirects=False).status_code == 400, bad


def test_counter_counts_from_start_to_current_odometer(client, conn, vehicle):
    from carassistant import summary

    summary.add_odometer(conn, vehicle, 12500)
    conn.commit()
    client.post(f"/v/{vehicle}/e/counters", data={"name": "Tax 2026", "kind": "tax", "start_date": "2026-01-01", "start_km": "10000"})
    page = client.get(f"/v/{vehicle}/e/trips").text  # the counters live on the trips page
    assert 'id="counters"' in page and ("2.500" in page or "2,500" in page)
    assert client.get(f"/v/{vehicle}/e/counters", follow_redirects=False).headers["location"].endswith("/e/trips#counters")


def test_parts_can_be_recorded(client, conn, vehicle):
    conn.commit()
    r = client.post(
        f"/v/{vehicle}/e/parts",
        data={"date": "2026-05-01", "name": "Brake pads", "part_number": "4G0698151", "cost": "89,90"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "4G0698151" in client.get(f"/v/{vehicle}/e/parts").text


def _png(color=(10, 200, 100), size=(300, 200)):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def test_default_icon_sizes_and_manifest(client):
    vid = create_vehicle(client, "Roadster")
    assert client.get("/icon/48.png").headers["content-type"] == "image/png"
    assert client.get("/icon/999.png").status_code == 404
    assert client.get("/v/999/icon/48.png").status_code == 404
    page = client.get(f"/v/{vid}").text
    assert f"/v/{slug(vid)}/icon/48.png" in page and f"/v/{slug(vid)}/manifest.webmanifest" in page
    manifest = client.get(f"/v/{vid}/manifest.webmanifest", headers={"X-Ingress-Path": "/api/hassio_ingress/tok"}).json()
    assert manifest["name"] == "Roadster" and manifest["display"] == "standalone"
    assert manifest["start_url"] == f"/api/hassio_ingress/tok/app/{slug(vid)}"  # the car's own start address, readable
    assert manifest["scope"] == "/api/hassio_ingress/tok/"
    assert client.get("/manifest.webmanifest").json()["name"] == "Car Assistant"


def test_only_cars_have_icons_of_their_own(client):
    """The icon of the app cannot be changed (only the colours of its frame follow the design); every car can have its own."""
    from PIL import Image

    a, b = create_vehicle(client, "A"), create_vehicle(client, "B")
    default = client.get(f"/v/{a}/icon/192.png").content
    assert client.post("/settings/icon", files={"icon": ("mine.png", _png(), "image/png")}).status_code in (404, 405)  # no app-wide upload
    client.post(f"/v/{b}/icon", files={"icon": ("b.png", _png((200, 0, 30)), "image/png")})
    own = Image.open(io.BytesIO(client.get(f"/v/{b}/icon/192.png").content))
    assert own.size == (192, 192) and own.convert("RGB").getpixel((96, 96))[0] > 150  # the car has its own ...
    assert client.get(f"/v/{a}/icon/192.png").content == default  # ... the other car and the app keep theirs
    client.post(f"/v/{b}/icon/reset")
    assert client.get(f"/v/{b}/icon/192.png").content == default


def test_icon_upload_rejects_non_images(client):
    vid = create_vehicle(client)
    r = client.post(f"/v/{vid}/icon", files={"icon": ("x.png", b"<svg onload=alert(1)>", "image/png")})
    assert "err.file_type" in r.headers["location"]
    r = client.post(f"/v/{vid}/icon", files={"icon": ("big.png", b"0" * (6 * 1024 * 1024), "image/png")})
    assert "err.file_big" in r.headers["location"]
    r = client.post(f"/v/{vid}/icon", data={})
    assert "err.required" in r.headers["location"]


def test_factory_reset_needs_confirmation_and_wipes_everything(client, env):
    vid = create_vehicle(client)
    client.post(f"/v/{vid}/e/fuel", data={"date": "2026-01-01", "odometer_km": "50100", "amount": "40", "cost": "60"})
    (env / "files" / "photos").mkdir(parents=True, exist_ok=True)
    (env / "files" / "photos" / "1.png").write_bytes(b"x")
    assert client.post("/settings/reset", data={"confirm": "no"}).headers["location"].endswith("err.reset_confirm")
    assert client.get(f"/v/{vid}").status_code == 200  # nothing deleted without the word
    assert client.post("/settings/reset", data={"confirm": "RESET"}).status_code == 303
    from carassistant import db

    with db.tx() as conn:
        assert all(
            conn.execute(f'SELECT COUNT(*) FROM "{t[0]}"').fetchone()[0]
            == (1 if t[0] == "sources" else 0)  # (the standard source is the factory setting)
            for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
        )
    assert not (env / "files" / "photos" / "1.png").exists()
    assert client.get("/").headers["location"].endswith("/setup/language")  # like new: the first start asks for the language again
    client.post("/setup/language", data={"language": "en"})
    assert "Welcome to Car Assistant" in client.get("/").text
    assert client.post("/vehicles", data={"name": "Again", "fuel_type": "petrol"}).status_code == 303  # can be set up again


def test_first_start_asks_for_the_language(env, client):
    from carassistant import db

    with db.tx() as conn:
        conn.execute("DELETE FROM settings WHERE key = 'setup.language'")
    r = client.get("/")
    assert r.status_code == 303 and r.headers["location"].endswith("/setup/language")
    page = client.get("/setup/language").text
    assert "English" in page and "Deutsch" in page
    assert client.post("/setup/language", data={"language": "de"}).headers["location"].endswith("/")
    assert "Willkommen" in client.get("/").text  # German UI after choosing German
    assert client.post("/setup/language", data={"language": "xx"}).headers["location"].endswith("err.choice")


def test_language_choice_page_is_english_without_navigation(env, client):
    from carassistant import db

    with db.tx() as conn:
        db.set_setting(conn, "language", "de")
        conn.execute("DELETE FROM settings WHERE key = 'setup.language'")
    page = client.get("/setup/language").text
    assert (
        '<html lang="en"' in page
        and "Welcome" in page
        and "data-lang-switch" in page
        and "Weiteres" not in page
        and 'id="tabbar"' not in page
    )


def test_vehicle_can_be_deleted_from_its_edit_page_not_from_a_tiny_icon(client):
    from tests.test_web import create_vehicle, slug

    vid = create_vehicle(client, "Delete Me")
    cards = client.get("/vehicles").text
    assert f'action="/v/{slug(vid)}/delete"' in cards and 'class="round-del"' in cards  # the manage list (Weiteres -> Vehicles)
    edit = client.get(f"/settings/car?car={slug(vid)}").text
    assert f'action="/v/{slug(vid)}/delete"' in edit and 'class="ghost-btn small warn"' in edit
    assert client.post(f"/v/{slug(vid)}/delete", follow_redirects=False).status_code == 303
    assert f"/v/{slug(vid)}" not in client.get("/vehicles").text


def test_deleting_a_vehicle_removes_everything_that_belongs_to_it(client):
    from carassistant import config, db

    gone = create_vehicle(client, "Gone")
    kept = create_vehicle(client, "Kept")
    client.post(f"/v/{slug(gone)}/e/fuel", data={"date": "2024-01-01", "liters": "40", "price_total": "60", "odometer_km": "1000"})
    client.post("/integrations/api/tokens", data={"vehicle_id": str(gone), "name": "t"})
    folder = config.files_dir() / str(gone)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "doc.txt").write_text("x")
    with db.tx() as conn:
        conn.execute("INSERT INTO tasks(vehicle_id, title, interval_km) VALUES(?,?,?)", (gone, "Oil", 10000))
        conn.execute("INSERT INTO tasks(vehicle_id, title, interval_km) VALUES(?,?,?)", (kept, "Oil", 10000))
        tables = [
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            if any(c["name"] == "vehicle_id" for c in conn.execute(f"PRAGMA table_info({r['name']})"))
        ]
        assert "tasks" in tables and "api_tokens" in tables
        assert conn.execute("SELECT COUNT(*) FROM tasks WHERE vehicle_id = ?", (gone,)).fetchone()[0] > 0
    assert client.post(
        f"/v/{slug(kept)}/e/fuel", data={"date": "2024-01-02", "liters": "30", "price_total": "45", "odometer_km": "2000"}
    ).status_code in (200, 303)
    assert client.post(f"/v/{slug(gone)}/delete", follow_redirects=False).status_code == 303
    with db.tx() as conn:
        for table in tables:
            assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE vehicle_id = ?", (gone,)).fetchone()[0] == 0, table
        assert conn.execute("SELECT COUNT(*) FROM vehicles WHERE id = ?", (gone,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM tasks WHERE vehicle_id = ?", (kept,)).fetchone()[0] > 0  # the other car is untouched
    assert not folder.exists()


def test_tyre_sets_view_opens_on_summer_and_edit_is_one_form(client):
    vid = create_vehicle(client, "Tyres")
    base = f"/v/{slug(vid)}/e/tires"
    page = client.get(base).text
    assert "No tyre set for this season" in page and 'class="seg-tabs tv-tabs"' in page and "ps=winter" in page  # always the three tabs
    edit = client.get(f"{base}?edit=1").text
    assert 'id="tf"' in edit and "/e/tires/save" in edit and 'data-panel="winter"' in edit and "tp-dot" not in edit
    assert "data-rec-cancel" not in edit and "Add tyre set" in edit  # a blank set per season, no extra buttons
    client.post(base, data={"name": "Winter set", "season": "winter", "size": "205/55 R16", "dot": "1523"})
    page = client.get(f"{base}?ps=winter").text
    assert 'class="card tire-card' in page and "205/55 R16" in page and "Winter set" in page
    assert "Winter set" not in client.get(base).text  # the summer tab does not show it


def test_tyre_edit_saves_everything_at_once(client):
    vid = create_vehicle(client, "Tyres")
    base = f"/v/{slug(vid)}/e/tires"
    r = client.post(
        f"{base}/save",
        data={
            "view": "winter",
            "n_summer_name": "Summer set",
            "n_winter_size": "205/55 R16",
            "p_winter_front": "2,5",
            "p_winter_rear": "2.7",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303 and "ps=winter" in r.headers["location"]
    from carassistant import db

    with db.tx() as conn:
        rows = {x["name"]: x for x in conn.execute("SELECT * FROM tires WHERE vehicle_id = ?", (vid,))}
        assert set(rows) == {"Summer set", "Winter"} and rows["Winter"]["season"] == "winter" and rows["Winter"]["size"] == "205/55 R16"
        sid, wid = rows["Summer set"]["id"], rows["Winter"]["id"]
    page = client.get(f"{base}?ps=winter").text
    assert "(2.5 bar)" in page and "(2.7 bar)" in page
    client.post(f"{base}/save", data={"mounted": str(wid), f"t{wid}_name": "Winter set", f"t{sid}_name": "Summer set", f"t{sid}_del": "1"})
    with db.tx() as conn:
        left = [(x["name"], x["mounted"]) for x in conn.execute("SELECT name, mounted FROM tires WHERE vehicle_id = ?", (vid,))]
    assert left == [("Winter set", 1)]


def test_theme_changes_only_the_colour_file(client):
    import re

    from carassistant import themes

    assert "custom-light" in themes.available() and "default" in themes.available()
    vid = create_vehicle(client, "Themed")
    page = client.get(f"/v/{slug(vid)}").text
    assert "data-theme" not in page and "/themes/" not in page  # the default needs no extra file
    assert client.post("/settings/theme", data={"theme": "custom-light"}, follow_redirects=False).status_code == 303
    page = client.get(f"/v/{slug(vid)}").text
    assert 'data-theme="light"' in page and "/static/themes/light.css" in page
    client.post("/settings/theme", data={"theme": "../../etc/passwd"})  # unknown names are refused
    assert 'data-theme="light"' not in client.get(f"/v/{slug(vid)}").text
    css = (themes.THEMES_DIR / "light.css").read_text()
    known = set(re.findall(r"--[a-z-]+(?=:)", (themes.THEMES_DIR.parent / "app.css").read_text()))
    assert set(re.findall(r"--[a-z-]+(?=:)", css)) <= known  # a theme file only sets tokens the app defines


def test_no_fixed_brand_colours_outside_the_tokens():
    """Accent and status colours exist once (the :root tokens); everything else uses var(--…) so a theme can recolour the app."""
    import re
    from pathlib import Path

    static = Path(__file__).resolve().parents[1] / "carassistant" / "app" / "carassistant" / "static"
    for name in ("app.css", "pc-core.css"):
        css = (static / name).read_text(encoding="utf-8").split("/* theme picker")[0]  # the swatch previews are fixed on purpose
        css = re.sub(r":root\s*\{[^}]*\}", "", css)  # the token definitions themselves
        for bad in ("#e2001a", "226,0,26", "226, 0, 26", "#4ade80", "74,222,128", "74, 222, 128"):
            assert bad not in css.lower(), f"{name}: {bad} - use the token (docs/design.md)"


def test_tank_battery_capacity_and_12v_battery_are_separate_fields(client):
    vid = create_vehicle(client, "Energy")
    r = client.post(
        f"/v/{slug(vid)}/edit",
        data={"name": "Energy", "fuel_type": "hybrid", "tank_l": "45", "battery_kwh": "13,5", "battery": "AGM 70 Ah"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    page = client.get(f"/v/{slug(vid)}/edit").text
    assert "Energy</div>" in page and "45 L" in page and "13.5 kWh" in page and "AGM 70 Ah" in page
    assert (
        "Tank size (L)" in client.get(f"/v/{slug(vid)}/edit?mode=form").text
        and "Battery capacity (kWh)" in client.get(f"/v/{slug(vid)}/edit?mode=form").text
    )


def test_language_page_follows_the_chosen_language(env, client):
    from carassistant import db

    with db.tx() as conn:
        conn.execute("DELETE FROM settings WHERE key = 'setup.language'")
    de = client.get("/setup/language?lang=de").text
    assert "Willkommen" in de and 'value="de" selected' in de and 'id="tabbar"' not in de
    assert "Welcome" in client.get("/setup/language?lang=nope").text  # unknown codes fall back to English


def test_first_vehicle_page_is_a_cards_form_with_the_navigation(client):
    page = client.get("/vehicles/new").text
    assert 'class="vf-hero"' in page and 'class="season-pick fuel-pick"' in page and 'class="card fgroup basics"' in page
    assert 'id="tabbar"' in page  # the navigation stays (only the guide's own /setup pages have none)
    create_vehicle(client)
    assert 'id="tabbar"' in client.get("/vehicles/new").text


def test_external_url_is_entered_in_the_system_settings_but_only_with_a_user(client, monkeypatch):
    from carassistant import accounts, config, db

    config.forget_external()
    page = client.get("/settings/system").text
    assert (
        'id="external"' in page and "/settings/external-url" not in page
    )  # the card is there, but without a user it has no form, only the notice
    assert "Create a user first" in page
    res = client.post("/settings/external-url", data={"url": "https://auto.example.com"}, follow_redirects=False)
    assert "m=err.ext_needs_user" in res.headers["location"] and config.external_url() == ""  # refused: nobody could log in
    with db.tx() as conn:
        accounts.create_user(conn, "owner", "A-very-Long-Passw0rd!x", admin=True)  # now a login exists
    assert "/settings/external-url" in client.get("/settings/system").text  # and now the field is there
    for bad in (
        "http://auto.example.com",
        "https://auto.example.com/path",
        "https://u:p@auto.example.com",
        "https://auto.example.com?x=1",
        "auto.example.com",
    ):
        r = client.post("/settings/external-url", data={"url": bad}, follow_redirects=False)
        assert "m=err.ext_url" in r.headers["location"], bad
    assert client.post("/settings/external-url", data={"url": "https://auto.example.com/"}, follow_redirects=False).status_code == 303
    assert config.external_url() == "https://auto.example.com"
    client.post("/settings/external-url", data={"url": ""})  # empty removes it
    assert config.external_url() == ""


def test_direct_access_row_tells_the_truth(client, monkeypatch):
    from carassistant import accounts, db, ha

    system = lambda: client.get("/settings/system").text  # noqa: E731
    monkeypatch.setattr(ha, "network_port", lambda: (False, None))
    assert "Unknown (Home Assistant does not answer)" in system()
    monkeypatch.setattr(ha, "network_port", lambda: (True, None))
    assert ">Off<" in system()  # no port: the status lives under System
    monkeypatch.setattr(ha, "network_port", lambda: (True, 8321))
    assert "On, locked" in system()  # a port is set: the row lives under System (one place for the address too)
    with db.tx() as conn:
        accounts.create_user(conn, "owner", "a-long-pass-123", "Owner", True)
    page = system()  # a user protects it: no password option needed; the row is short: On, then the port
    assert ">On<" in page and "Port: <code>8321</code>" in page and "protected by users" not in page


def test_tyres_target_pressures_per_season_and_actual_values(client):
    vid = create_vehicle(client)
    base = f"/v/{slug(vid)}/e/tires"
    client.post(
        base, data={"name": "Winter set", "season": "winter", "size": "225/55 R17", "rear_size": "245/45 R18", "rear_name": "Rear brand"}
    )
    page = client.get(f"{base}?ps=winter&edit=1").text
    assert "Tyre pressure" in page and "Normal use" in page and "Fully loaded" in page
    assert (
        "245/45 R18" in client.get(f"{base}?ps=winter").text and "Rear brand" in client.get(f"{base}?ps=winter").text
    )  # the rear axle of its own
    r = client.post(
        f"{base}/pressure",
        data={"season": "winter", "front": "2,6", "rear": "2.8", "load_front": "3", "load_rear": "3.2"},
        follow_redirects=False,
    )
    assert r.status_code == 303 and "ps=winter" in r.headers["location"]
    winter = client.get(f"{base}?ps=winter&edit=1").text
    assert 'value="2.6"' in winter and 'value="2.8"' in winter and 'value="3.2"' in winter
    assert "2.6 bar" in client.get(f"{base}?ps=winter").text  # the read-only view shows them as text
    assert 'name="p_summer_front" inputmode="decimal" value=""' in winter  # every season has its own values
    assert client.post(f"{base}/pressure", data={"season": "bogus"}).status_code == 400
    client.post(f"{base}/pressure", data={"season": "winter", "front": "", "rear": "", "load_front": "", "load_rear": ""})
    assert 'name="p_winter_front" inputmode="decimal" value=""' in client.get(f"{base}?ps=winter&edit=1").text  # empty removes
    from carassistant import db

    with db.tx() as c:
        c.execute(
            "INSERT INTO live(vehicle_id, key, value, updated) VALUES (?, 'tyre_pressure_bar', ?, '2026-11-16T10:00:00')",
            (vid, '{"fl": 2.3, "fr": 2.4}'),
        )
    assert "2.3 <small>bar" in client.get(f"{base}?ps=winter").text


def test_storage_only_shown_when_filled(client):
    base = f"/v/{slug(create_vehicle(client))}/e/tires"
    client.post(base, data={"name": "Summer set", "season": "summer"})
    assert "Garage" not in client.get(base).text
    client.post(base, data={"name": "Winter set", "season": "winter", "storage": "Garage"})
    assert "Garage" in client.get(f"{base}?ps=winter").text


def test_instant_navigation_script_is_served_and_loaded_on_app_pages(client):
    vid = create_vehicle(client)
    page = client.get(f"/v/{slug(vid)}").text
    assert page.index("static/embed.js") < page.index("static/softnav.js")  # the listener registry comes first
    assert client.get("/static/softnav.js").status_code == 200


def test_about_page_shows_the_large_animated_logo(client):
    page = client.get("/about").text
    assert 'class="about-logo"' in page and "/static/about-logo.svg" in page
    svg = client.get("/static/about-logo.svg").text
    assert "@keyframes" in svg and "prefers-reduced-motion" in svg and "<script" not in svg  # animation only, no code


def test_app_icons_for_every_device(client):
    from io import BytesIO

    from PIL import Image

    def image(path):
        r = client.get(path)
        assert r.status_code == 200 and r.headers["content-type"] == "image/png", path
        return Image.open(BytesIO(r.content))

    assert image("/icon/180.png").mode == "RGB"  # iPhone: full square, no transparency (iOS would paint it black)
    tab = image("/icon/32.png")
    assert tab.size == (32, 32) and tab.mode == "RGBA" and tab.getpixel((0, 0))[3] == 0  # a browser tab: the rounded tile
    mask = image("/icon/maskable-512.png")
    assert mask.size == (512, 512) and mask.getpixel((0, 0))[:3] == (
        13,
        16,
        22,
    )  # Android: the tile inside the safe zone on the page colour
    manifest = client.get("/manifest.webmanifest").json()
    assert {(i["purpose"], i["sizes"]) for i in manifest["icons"]} == {(p, s) for p in ("any", "maskable") for s in ("192x192", "512x512")}
    assert client.get("/favicon.ico").status_code == 200 and client.get("/static/favicon.svg").status_code == 200
    page = client.get("/vehicles").text
    assert 'type="image/svg+xml"' in page and "favicon.svg" in page


def test_own_icons_win_over_the_default_look(client):
    """The default icon is on every page - except where an own icon was uploaded: a car's pages use that car's icon (its own home-screen app)."""
    import io

    from PIL import Image

    from carassistant import appicon

    vid = create_vehicle(client)
    png = io.BytesIO()
    Image.new("RGBA", (64, 64), (200, 30, 30, 255)).save(png, "PNG")
    car = f"/v/{slug(vid)}"
    assert 'type="image/svg+xml"' in client.get(car).text and 'type="image/svg+xml"' in client.get("/about").text  # the default look
    appicon.save_custom(png.getvalue(), vid)  # this car gets its own icon
    page = client.get(car).text
    assert 'type="image/svg+xml"' not in page and f"{car}/icon/180.png" in page and f"{car}/icon/48.png" in page  # its pages: its own icon
    assert 'type="image/svg+xml"' in client.get("/about").text  # the rest of the app keeps the default look
    manifest = client.get(f"{car}/manifest.webmanifest").json()
    assert any("maskable" in i["src"] for i in manifest["icons"]) and all(f"/v/{slug(vid)}/icon/" in i["src"] for i in manifest["icons"])


def test_every_car_is_a_web_app_of_its_own(client):
    a, b = create_vehicle(client, "Alpha"), create_vehicle(client, "Beta")
    ma = client.get(f"/v/{slug(a)}/manifest.webmanifest").json()
    mb = client.get(f"/v/{slug(b)}/manifest.webmanifest").json()
    assert ma["start_url"] == ma["id"] == f"/app/{slug(a)}" and mb["start_url"] == f"/app/{slug(b)}"  # its own start address
    assert ma["scope"] == mb["scope"] == "/"  # the whole app: no link leaves the web app (iOS would open a little browser)
    assert ma["name"] == "Alpha" and mb["name"] == "Beta" and ma["icons"][0]["src"].startswith(f"/v/{slug(a)}/icon/")
    system = client.get("/manifest.webmanifest").json()
    assert system["scope"] == "/" and system["name"] == "Car Assistant"
    js = client.get("/static/softnav.js").text
    assert (
        "syncHead" in js and "scopeOf" not in js
    )  # in an installed web app another car is a page of its own; in a browser tab the swap takes over icon, manifest and title


def test_the_built_in_icon_address_changes_with_the_app_version(client, monkeypatch):
    import re

    from carassistant import appicon

    first = appicon.revision(None)
    monkeypatch.setattr("carassistant.__version__", "9.9.9")
    assert appicon.revision(None) != first  # a new version: new icon addresses (iOS and every cache fetch it again)
    assert re.search(r"/icon/180\.png\?v=\d+", client.get("/about").text)


def test_icon_upload_is_centred_and_cut_to_a_square(tmp_path):
    import io

    from PIL import Image

    from carassistant import appicon

    wide = Image.new("RGB", (400, 100), (255, 0, 0))
    wide.paste((0, 0, 255), (150, 0, 250, 100))  # a blue square in the middle
    buf = io.BytesIO()
    wide.save(buf, "GIF")  # not a PNG: converted
    appicon.save_custom(buf.getvalue(), 7)
    stored = Image.open(appicon.custom_path(7)).convert("RGBA")
    assert stored.size == (100, 100)  # the middle part, full square, no bars
    assert stored.getpixel((50, 50))[3] == 255 and stored.getpixel((2, 2))[3] == 255
    appicon.reset(7)


def test_equipment_has_fixed_categories_and_own_features(client):
    from carassistant import db, equipment

    vid = create_vehicle(client)
    page = client.get(f"/v/{vid}/edit").text
    assert ('id="equipment"' in page and "Exterior" in page.replace("Außen", "Exterior")) or "Außen" in page  # fixed areas are always there
    assert (
        'name="cat"' in page and "equipment/new" in page and "/equipment/starter" not in page and "eq-add" not in page
    )  # no starter, no new area
    with db.tx() as conn:
        groups = equipment.groups(conn, vid, "en")
        assert [g["key"] for g in groups] == list(equipment.KEYS) and all(g["total"] == 0 for g in groups)
    client.post(f"/v/{vid}/equipment/new", data={"category": "exterior", "title": "Roof box", "status": "retrofit", "code": "ab1"})
    client.post(
        f"/v/{vid}/equipment/new", data={"category": "nonsense", "title": "Mystery", "status": "series"}
    )  # unknown area -> the first one (comfort)
    with db.tx() as conn:
        by = {g["key"]: g for g in equipment.groups(conn, vid, "en")}
        item = by["exterior"]["items"][0]
        assert item["code"] == "AB1" and item["status"] == "retrofit" and by["comfort"]["total"] == 1 and by["exterior"]["fitted"] == 1
    client.post(
        f"/v/{vid}/equipment/item/{item['id']}", data={"title": "Roof box XL", "code": "", "status": "series", "category": "assist"}
    )
    with db.tx() as conn:
        by = {g["key"]: g for g in equipment.groups(conn, vid, "en")}
        assert by["exterior"]["total"] == 0 and by["assist"]["items"][0]["title"] == "Roof box XL"  # moved to another area
    client.post(f"/v/{vid}/equipment/item/{item['id']}", data={"del": "1"})
    with db.tx() as conn:
        assert equipment.groups(conn, vid, "en")[10]["total"] == 0
    assert "Search equipment" in client.get(f"/v/{vid}/edit").text or "Ausstattung" in client.get(f"/v/{vid}/edit").text


def test_equipment_categories_can_be_moved(client):
    from carassistant import db, equipment

    vid = create_vehicle(client)
    client.post(f"/v/{vid}/equipment/move", data={"cat": "seats", "dir": "up"})
    client.post(f"/v/{vid}/equipment/move", data={"cat": "seats", "dir": "up"})  # already first: nothing
    with db.tx() as conn:
        keys = [g["key"] for g in equipment.groups(conn, vid)]
    assert keys[:2] == ["seats", "comfort"] and keys[2:] == list(equipment.KEYS[2:])


def test_trip_card_stats_and_track_json(client):
    from carassistant import db, trips

    vid = create_vehicle(client)
    with db.tx() as conn:
        tid = conn.execute(
            "INSERT INTO trips(vehicle_id, date, start_place, end_place, category, source, distance_km) VALUES(?, '2026-11-01', 'A', 'B', 'private', 'track', 1.0)",
            (vid,),
        ).lastrowid
        for i, (lat, lon, ts) in enumerate(
            [(50.0, 8.0, "2026-11-01T10:00:00+00:00"), (50.01, 8.0, "2026-11-01T10:01:00+00:00"), (50.02, 8.0, "2026-11-01T10:02:00+00:00")]
        ):
            conn.execute("INSERT INTO trip_points(trip_id, seq, lat, lon, ts) VALUES(?,?,?,?,?)", (tid, i, lat, lon, ts))
        data = trips.stats(trips.trip_points(conn, tid))
    assert data["minutes"] == 2.0 and 60 < data["avg_kmh"] < 70 and data["max_kmh"] >= data["avg_kmh"] and len(data["points"]) == 3
    r = client.get(f"/v/{vid}/trips/{tid}/track.json")
    assert r.status_code == 200 and r.json()["points"][1][2] > 0
    page = client.get(f"/v/{vid}/e/trips").text
    assert '<details class="trip"' in page and f"trips/{tid}/track.json" in page and "static/trips.js" in page


def test_extra_work_page_cards_reset_and_templates(client):
    from carassistant import db

    vid = create_vehicle(client)
    base = f"/v/{slug(vid)}"
    page = client.get(f"{base}/e/tasks").text
    assert "Current odometer" in page and "Add ready-made jobs" in page and "Extra work" in page
    client.post(f"{base}/tasks/templates")
    with db.tx() as conn:
        n = conn.execute("SELECT COUNT(*) FROM tasks WHERE vehicle_id = ?", (vid,)).fetchone()[0]
        oil = conn.execute("SELECT id FROM tasks WHERE vehicle_id = ? AND title = 'Oil change'", (vid,)).fetchone()["id"]
    assert n >= 8
    assert "Add ready-made jobs" not in client.get(f"{base}/e/tasks").text  # all added now
    client.post(f"{base}/tasks/templates")  # twice: no duplicates
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM tasks WHERE vehicle_id = ?", (vid,)).fetchone()[0] == n
    client.post(f"{base}/e/tasks/{oil}/done", data={"km": "51000"})
    with db.tx() as conn:
        row = conn.execute("SELECT last_km, last_date FROM tasks WHERE id = ?", (oil,)).fetchone()
    assert row["last_km"] == 51000 and row["last_date"]
    page = client.get(f"{base}/e/tasks").text
    assert "za-card" in page and "every 30" in page.replace(",", "").replace(".", "")


def test_manual_import_chapters_search_read_and_epub(client):
    import io
    import zipfile

    from carassistant import db, manual

    vid = create_vehicle(client)
    base = f"/v/{slug(vid)}/manual"
    assert "Import manual" in client.get(base).text
    text = "# Driving\n## Tyres\nCheck the tyre pressure every month. See page 2.\n\n## Lights\nHigh beam on the stalk.\n# Service\n## Oil\nOil every 30000 km.\n"
    r = client.post(f"{base}/import", files={"file": ("manual.md", text.encode(), "text/markdown")}, follow_redirects=False)
    assert r.status_code == 303
    page = client.get(base).text
    assert "Driving" in page and "Tyres" in page and "Oil" in page and "p. 1" in page
    hits = client.get(f"{base}?q=tyre pressure").text
    assert "<mark>tyre pressure</mark>" in hits.replace("Tyre pressure", "tyre pressure") or "tyre pressure" in hits.lower()
    read = client.get(f"{base}/read?page=1").text
    assert "Check the tyre pressure" in read and "Page 1 of" in read
    assert "Continue reading" in client.get(base).text  # the last page read is remembered
    assert (
        client.post(f"{base}/import", files={"file": ("x.exe", b"MZ", "application/octet-stream")}, follow_redirects=False).status_code
        == 303
    )
    epub = client.get(f"{base}/export.epub")
    assert epub.status_code == 200 and zipfile.ZipFile(io.BytesIO(epub.content)).read("mimetype") == b"application/epub+zip"
    # the EPUB we wrote can be read back
    r = client.post(f"{base}/import", files={"file": ("again.epub", epub.content, "application/epub+zip")}, follow_redirects=False)
    assert r.status_code == 303
    with db.tx() as conn:
        assert manual.info(conn, vid)["source_name"] == "again.epub" and manual.info(conn, vid)["pages"] >= 1
    client.post(f"{base}/delete")
    with db.tx() as conn:
        assert manual.info(conn, vid) is None


def test_attention_vehicle_data_and_position_stay_one_full_row(client):
    from carassistant import db, widgets

    vid = create_vehicle(client)
    with db.tx() as conn:
        first = widgets.layout(conn, vid)
        widgets.save(conn, vid, [w.key for w in first], {w.key: "s" for w in first}, {w.key for w in first}, {})  # everything asked small
        sizes = {w.key: w.size for w in widgets.layout(conn, vid)}
    assert sizes["attention"] == sizes["car_data"] == sizes["location"] == "m"
    assert sizes["security"] == "s" and sizes["trips"] == "s"  # the others may be small
    page = client.get(f"/v/{slug(vid)}").text
    assert "wd-slot m locked" in page or "locked" not in page  # a locked slot is marked when the widget shows


def test_a_new_car_from_the_page_starts_with_the_recommended_functions(client):
    from carassistant import db, modules

    client.post("/vehicles", data={"name": "Plain", "fuel_type": "diesel"})  # no page: everything stays on (scripts, tests)
    client.post("/vehicles", data={"name": "From page", "fuel_type": "diesel", "recommended": "1"})
    with db.tx() as conn:
        plain, paged = (r["id"] for r in conn.execute("SELECT id FROM vehicles ORDER BY id").fetchall())
        assert modules.vehicle_off(conn, plain) == set()
        off = modules.vehicle_off(conn, paged)
    assert off == set(modules.ON_REQUEST) and not off & set(modules.RECOMMENDED)
    assert 'name="recommended"' in client.get("/vehicles/new").text


def test_setup_step_three_lists_the_recommended_first_and_the_rest_off(client):
    client.post("/vehicles", data={"name": "First", "fuel_type": "diesel", "recommended": "1"})
    page = client.get("/setup/functions").text
    assert "Recommended" not in page and "When you need it" not in page  # one list, no group headings
    assert page.index('value="service"') < page.index('value="fuel"') < page.index('value="tires"')  # the recommended ones come first
    assert 'value="service" checked' in page and 'value="fuel" checked' in page
    assert 'value="tires" checked' not in page and 'value="tires"' in page


def test_trips_are_cards_under_period_headings_with_search_and_export_periods(client):
    from datetime import date, timedelta

    vid = create_vehicle(client)
    base = f"/v/{slug(vid)}/e/trips"
    today, old = date.today(), date.today() - timedelta(days=90)
    client.post(
        base,
        data={
            "date": today.isoformat(),
            "start_place": "Home",
            "end_place": "Office",
            "start_km": "100",
            "end_km": "130",
            "category": "business",
        },
    )
    client.post(base, data={"date": old.isoformat(), "start_place": "Lake", "end_place": "Home", "category": "private"})
    page = client.get(base).text
    assert page.count('<article class="rec trip-card"') >= 2 and "Today" in page and 'class="rec-month"' in page
    assert "Home" in page and "30" in page  # the distance of the first trip
    found = client.get(f"{base}?q=Lake").text
    assert "Lake" in found and "Office" not in found.split('id="trips"')[1]  # the search works over all trips
    for rng in ("all", "7d", "30d", "year", "custom"):
        r = client.get(f"/v/{slug(vid)}/trips-export.csv?range={rng}")
        assert r.status_code == 200 and "text/csv" in r.headers["content-type"]
    week = client.get(f"/v/{slug(vid)}/trips-export.csv?range=7d").text
    assert "Home" in week and "Lake" not in week  # only the last seven days


def test_an_own_picture_gets_the_coloured_frame_in_every_size(client):
    """Your logo or photo is put into the frame of the real icon (red top left, green bottom right) - favicon, iPhone and web-app sizes alike."""
    from PIL import Image

    vid = create_vehicle(client, "Framed")
    client.post(f"/v/{vid}/icon", files={"icon": ("c.png", _png((30, 90, 200), (400, 400)), "image/png")})
    for size in (32, 192, 512):
        icon = Image.open(io.BytesIO(client.get(f"/v/{vid}/icon/{size}.png").content)).convert("RGBA")
        edge = round(size * 0.02)
        centre = icon.getpixel((size // 2, size // 2))
        assert centre[2] > 150 and centre[0] < 80  # the picture is inside ...
        assert icon.getpixel((0, 0))[3] == 0  # ... the corners of the tile are transparent ...
        left, right = icon.getpixel((edge, size // 2)), icon.getpixel((size - 1 - edge, size // 2))
        assert left[0] > left[1] and right[1] > right[0]  # ... and the edge runs from red (left) to green (right)
    phone = Image.open(io.BytesIO(client.get(f"/v/{vid}/icon/180.png").content))
    assert phone.mode == "RGB"  # iOS paints transparency black: no alpha there
    maskable = Image.open(io.BytesIO(client.get(f"/v/{vid}/icon/maskable-512.png").content))
    assert maskable.size == (512, 512)


def test_the_address_is_typed_without_the_scheme_and_always_https(client):
    from carassistant import accounts, db

    with db.tx() as conn:
        accounts.create_user(conn, "owner", "A-very-Long-Passw0rd!x", admin=True)
    client.post("/settings/external-url", data={"host": "auto.example.com"})
    from carassistant import config

    assert config.external_url() == "https://auto.example.com"
    page = client.get("/settings/system").text
    assert 'class="affix-pre"' in page and 'value="auto.example.com"' in page
    for bad in ("http://auto.example.com", "auto.example.com/path"):
        r = client.post("/settings/external-url", data={"host": bad}, follow_redirects=False)
        assert "err.ext_url" in r.headers["location"] or "error" in r.headers["location"].lower()
    assert config.external_url() == "https://auto.example.com"  # the refused ones changed nothing
    client.post("/settings/external-url", data={"host": ""})
    assert config.external_url() == ""


def test_passkeys_and_notifications_wait_for_the_saved_address(client, monkeypatch):
    from carassistant import accounts, db, ha

    monkeypatch.setattr(ha, "network_port", lambda: (True, 8321))
    with db.tx() as conn:
        accounts.create_user(conn, "owner", "A-very-Long-Passw0rd!x", admin=True)
    ha._cache.clear()
    page = client.get("/settings/user").text
    assert 'id="notifications"' not in page and 'id="pk-add"' not in page  # a port, but no address under System yet
    assert 'id="access"' not in page
    client.post("/settings/external-url", data={"host": "auto.example.com"})
    page = client.get("/settings/user").text
    assert 'id="notifications"' in page  # now they are offered


def _dummy_package(pages=4, offset=2, with_index=True, bad_image=False):
    """A package made of made-up pictures (never real manual content)."""
    import gzip
    import io
    import json
    import zipfile

    fake = b"\x00\x00\x00\x1cftypavif" + b"\x00" * 24
    chapters = [
        {"t": "Basics", "p": 3, "g": "Part One", "c": [{"t": "Lights", "p": 4}]},
        {"t": "Service", "p": 2},
    ]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("pack/meta.json", json.dumps({"title": "Example manual", "pages": pages, "offset": offset, "chapters": chapters}))
        for i in range(1, pages + 1):
            z.writestr(f"pack/p/{i:03d}.avif", b"not a picture" if bad_image and i == 2 else fake + bytes([i]))
        if with_index:
            index = [{"p": i, "t": f"Text of page {i}. See page 1 for the lamp."} for i in range(1, pages + 1)]
            z.writestr("pack/index.json.gz", gzip.compress(json.dumps(index).encode()))
    return buf.getvalue()


def test_manual_package_with_page_images(client):
    from carassistant import config, db, manual

    vid = create_vehicle(client)
    base = f"/v/{slug(vid)}/manual"
    up = {"file": ("pack.zip", _dummy_package(), "application/zip")}
    assert client.post(f"{base}/import", files=up, follow_redirects=False).status_code == 303
    with db.tx() as conn:
        meta = manual.info(conn, vid)
        assert (meta["pages"], meta["page_offset"], meta["images"], meta["title"]) == (4, 2, 4, "Example manual")
        assert [r["depth"] for r in conn.execute("SELECT depth FROM manual_chapters WHERE vehicle_id = ? ORDER BY sort", (vid,))] == [
            0,
            1,
            0,
        ]
    assert (config.files_dir() / "manual" / str(vid) / "0003.avif").is_file()
    page = client.get(base).text
    assert "Part One" in page and "Lights" in page and "mi-sub" in page and "p. 1<" in page  # printed numbers: file page 3 - offset 2
    # the page as image, with the switch; the text view links 'page 1' to the file page 1 + offset 2 = 3
    read = client.get(f"{base}/read?page=3").text
    assert f"{base}/image/3" in read and "Page image" in read and "Page 1 of 2" in read
    text = client.get(f"{base}/read?page=3&view=text").text
    assert "Text of <a" in text and f"{base}/read?page=3&amp;view=text" in text
    img = client.get(f"{base}/image/3")
    assert img.status_code == 200 and img.headers["content-type"] == "image/avif"
    assert client.get(f"{base}/image/99").status_code == 404
    assert "Text of page 2" in client.get(f"{base}?q=Text of page 2").text
    # a new import replaces; a text-only package works, and the old images are gone
    up = {"file": ("again.zip", _dummy_package(pages=3, with_index=True), "application/zip")}
    client.post(f"{base}/import", files=up, follow_redirects=False)
    assert client.get(f"{base}/image/4").status_code == 404
    client.post(f"{base}/delete")
    assert not (config.files_dir() / "manual" / str(vid)).exists()


def test_manual_package_is_checked(client):
    import io
    import zipfile

    vid = create_vehicle(client)
    base = f"/v/{slug(vid)}/manual"
    empty = io.BytesIO()
    with zipfile.ZipFile(empty, "w") as z:
        z.writestr("readme.txt", "no meta")
    for data in (_dummy_package(bad_image=True), empty.getvalue(), b"PK-not-a-zip"):
        r = client.post(f"{base}/import", files={"file": ("x.zip", data, "application/zip")}, follow_redirects=False)
        assert r.status_code == 303 and "m=" in r.headers["location"] and "m=saved" not in r.headers["location"]
    from carassistant import db, manual

    with db.tx() as conn:
        assert manual.info(conn, vid) is None


def test_manual_package_simple_form_numbered_pictures_only(client):
    import io
    import zipfile

    from carassistant import db, manual

    vid = create_vehicle(client)
    base = f"/v/{slug(vid)}/manual"
    fake = b"\x00\x00\x00\x1cftypavif" + b"\x00" * 24
    for layout in ("{:03d}.avif", "book/{:03d}.avif", "p/{:03d}.avif"):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("__MACOSX/._001.avif", b"junk")
            for i in range(1, 4):
                z.writestr(layout.format(i), fake + bytes([i]))
        r = client.post(f"{base}/import", files={"file": ("My_Manual.zip", buf.getvalue(), "application/zip")}, follow_redirects=False)
        assert "m=saved" in r.headers["location"], layout
        with db.tx() as conn:
            meta = manual.info(conn, vid)
            assert (meta["pages"], meta["images"], meta["page_offset"], meta["title"]) == (3, 3, 0, "My Manual")
        assert client.get(f"{base}/image/3").status_code == 200
        assert f"{base}/image/2" in client.get(f"{base}/read?page=2").text


def test_manual_page_references_are_tappable_on_the_image(client):
    import gzip
    import io
    import json
    import zipfile

    from carassistant import db, manual

    vid = create_vehicle(client)
    base = f"/v/{slug(vid)}/manual"
    fake = b"\x00\x00\x00\x1cftypavif" + b"\x00" * 24
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("meta.json", json.dumps({"pages": 4, "offset": 2}))
        for i in range(1, 5):
            z.writestr(f"p/{i:03d}.avif", fake + bytes([i]))
        boxes = {"x": [[1, 100, 200, 300, 230], [2, 10, 10, 50, 30], [99, 1, 1, 2, 2], [3, 500, 500, 400, 600], ["x", 1, 2, 3, 4]]}
        z.writestr("t/003.json.gz", gzip.compress(json.dumps(boxes).encode()))
        z.writestr("t/004.json.gz", b"not gzip")
    r = client.post(f"{base}/import", files={"file": ("pack.zip", buf.getvalue(), "application/zip")}, follow_redirects=False)
    assert "m=saved" in r.headers["location"]
    page = client.get(f"{base}/read?page=3").text
    # printed 1 -> file page 3, printed 2 -> file page 4; 99 is outside the book, the reversed box and the odd entry are dropped
    assert page.count('class="mn-ref"') == 2
    assert f'href="{base}/read?page=3&amp;view=image"' in page and f'href="{base}/read?page=4&amp;view=image"' in page
    assert 'x="98" y="199" width="204" height="32"' in page and 'aria-label="page 1"' in page
    assert 'class="mn-ref"' not in client.get(f"{base}/read?page=2").text
    assert 'class="mn-ref"' not in client.get(f"{base}/read?page=3&view=text").text
    with db.tx() as conn:
        assert conn.execute("SELECT refs FROM manual_pages WHERE vehicle_id = ? AND page = 4", (vid,)).fetchone()["refs"] == ""
        assert manual.info(conn, vid)["images"] == 4


def test_report_period_filter(client):
    base = f"/v/{slug(create_vehicle(client))}/report"
    page = client.get(base).text
    assert "Months" in page and "Days" in page and "Weeks" in page
    page = client.get(f"{base}?g=week&n=8").text
    assert 'class="on" aria-current="page">Weeks' in page and '<option value="8" selected>' in page
    assert client.get(f"{base}?g=bogus&n=7").status_code == 200  # unknown values fall back to the defaults


def test_navigation_editor_icon_choices_are_rendered_once(client):
    page = client.get(f"/v/{slug(create_vehicle(client))}/integrations").text
    assert page.count('id="pk-tpl"') == 1 and page.count('class="pickgrid"') >= 4  # the grids are filled by script when opened
    assert page.count('type="radio"') < 100  # not forty icons in every row


def test_passport_with_first_registration_but_no_inspection_appointment(client):
    vid = create_vehicle(client, "Estimate")
    client.post(f"/v/{slug(vid)}/edit", data={"name": "Estimate", "fuel_type": "diesel", "first_reg": "2017-08-17"})
    r = client.get(f"/v/{slug(vid)}/edit")
    assert r.status_code == 200


def test_google_search_helper_is_off_until_switched_on(client):
    vid = create_vehicle(client, "Search")
    page = client.get(f"/v/{slug(vid)}/edit?mode=form").text
    assert "lookup.js" not in page
    assert client.post("/settings/google", data={"help": "1"}).status_code == 303
    page = client.get(f"/v/{slug(vid)}/edit?mode=form").text
    assert "static/lookup.js" in page
    assert 'name="help" value="1" checked' in client.get("/settings/system").text.replace("\n", " ")


def test_document_upload_guesses_the_category_and_has_one_button(client):
    vid = create_vehicle(client)
    page = client.get(f"/v/{vid}/docs").text
    assert page.count("data-send") == 1 and "add-card" not in page  # the one button in the page header, no second one in a tile
    client.post(f"/v/{vid}/docs", files={"file": ("Versicherung 2026.pdf", b"%PDF-data", "application/pdf")})
    client.post(f"/v/{vid}/docs", files={"file": ("scan.jpg", b"\xff\xd8data", "image/jpeg")})
    with db.tx() as conn:
        cats = {r["filename"]: r["category"] for r in conn.execute("SELECT filename, category FROM documents WHERE vehicle_id = ?", (vid,))}
    assert cats == {"Versicherung 2026.pdf": "insurance", "scan.jpg": "other"}


def test_report_page_lists_the_costs_and_filters_by_category(client):
    from datetime import date

    car = slug(create_vehicle(client))
    today = date.today().isoformat()
    client.post(f"/v/{car}/e/service", data={"date": today, "title": "Brake pads", "cost": "250"})
    client.post(f"/v/{car}/e/fuel", data={"date": today, "amount": "30", "price_total": "55", "station": "Corner"})
    page = client.get(f"/v/{car}/report").text
    assert "Brake pads" in page and "Corner" in page and "305.00" in page
    listing = client.get(f"/v/{car}/report?c=service").text.split('id="rp-list"')[1].split("</section>")[0]
    assert "Brake pads" in listing and "Corner" not in listing


def test_car_web_app_shows_one_car_only_and_can_be_left(client):
    one = slug(create_vehicle(client, "First Car"))
    two = slug(create_vehicle(client, "Second Car"))
    manifest = client.get(f"/v/{one}/manifest.webmanifest").json()
    assert manifest["start_url"].endswith(f"/app/{one}") and manifest["scope"].endswith("/") and "/v/" not in manifest["scope"]
    assert 'class="cur-switch"' in client.get(f"/v/{one}").text  # normally the car can be switched
    assert 'class="ph-s" data-car' in client.get(f"/v/{one}/e/service").text  # ... and the name is shown under the title
    page = client.get(f"/app/{one}")  # the car's own address: shown there, no redirect, device remembers it
    assert page.status_code == 200 and "ca_car" in page.headers.get("set-cookie", "")
    assert 'class="cur-switch"' not in client.get(f"/v/{one}").text and f"/v/{two}" not in client.get(f"/v/{one}").text.split("<main")[1]
    assert "app-all" not in client.get(f"/v/{one}/more").text  # nothing about it at the bottom of More
    assert 'class="ph-s' not in client.get(f"/v/{one}/e/service").text  # the car's own app does not repeat the car's name under every title
    assert 'href="/app-all"' in client.get("/settings/user").text  # the way back to all cars is on the User tab
    assert "is-app" in client.get("/static/embed.js").text  # an installed web app hides the "change car" sign
    assert "--app-gap: 30px" in client.get("/static/pc-core.css").text  # ... and starts below the status bar with one adjustable distance
    root = client.get("/", follow_redirects=False)
    assert root.status_code == 303 and root.headers["location"].endswith(f"/v/{one}")
    assert client.get("/app/nonsense").status_code == 404
    left = client.get("/app-all", follow_redirects=False)
    assert left.status_code == 303 and "ca_car" in left.headers.get("set-cookie", "")
    client.cookies.clear()
    assert 'class="cur-switch"' in client.get(f"/v/{one}").text
