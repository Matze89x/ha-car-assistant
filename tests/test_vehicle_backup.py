import io
import json
import re
import zipfile

import pytest

from carassistant import addons, backup, config, connectors, db, sources, vehiclebackup


@pytest.fixture(autouse=True)
def fake_source(monkeypatch):
    state = {
        "files": {
            "plugins/index.json": json.dumps({"packages": [{"id": "sim-plugin", "name": "Sim", "version": "1"}]}),
            "plugins/sim-plugin/plugin.json": json.dumps(
                {"id": "sim-plugin", "name": "Sim", "version": "1", "settings": [{"key": "mode", "label": "Mode"}]}
            ),
        }
    }

    def fake_http(url, headers, check_host, limit=0):
        for path, text in state["files"].items():
            if url.endswith("/" + path):
                return text.encode()
        raise sources.SourceError("err.src_missing")

    monkeypatch.setattr(sources, "_http", fake_http)
    return state


def _car(client, name="Backup Car"):
    client.post("/vehicles", data={"name": name, "fuel_type": "petrol", "plate": "AB-CD 123"})
    with db.tx() as conn:
        return conn.execute("SELECT id, slug FROM vehicles WHERE name = ?", (name,)).fetchone()


def _fill(vid):
    """Rows in several lists, a trip with its route, a document with its file, per-vehicle settings, a plugin with its token."""
    with db.tx() as conn:
        conn.execute("INSERT INTO service(vehicle_id, date, title, odometer_km, cost) VALUES(?, '2026-01-02', 'Oil', 1000, 99.5)", (vid,))
        conn.execute(
            "INSERT INTO fuel(vehicle_id, date, odometer_km, amount, price_per_unit, price_total, full_tank) VALUES(?, '2026-02-01', 1200, 40, 1.8, 72, 1)",
            (vid,),
        )
        trip = conn.execute(
            "INSERT INTO trips(vehicle_id, date, start_place, end_place) VALUES(?, '2026-03-01', 'A', 'B')", (vid,)
        ).lastrowid
        for seq in range(3):
            conn.execute(
                "INSERT INTO trip_points(trip_id, seq, lat, lon, ts) VALUES(?,?,?,?,?)", (trip, seq, 50.0 + seq, 8.0, "2026-03-01T10:00:00")
            )
        doc = conn.execute(
            "INSERT INTO documents(vehicle_id, category, title, filename, mime, size) VALUES(?, 'other', 'Manual', 'manual.txt', 'text/plain', 5)",
            (vid,),
        ).lastrowid
        folder = config.files_dir() / str(vid)
        folder.mkdir(exist_ok=True)
        (folder / f"{doc}.txt").write_bytes(b"hello")
        conn.execute("INSERT INTO settings(key, value) VALUES(?, ?)", (f"modules.off.{vid}", '["tires"]'))
        manifest = addons.parse_package(
            json.dumps(
                {"id": "sim-plugin", "kind": "plugin", "name": "Sim", "version": "1", "settings": [{"key": "mode", "label": "Mode"}]}
            ).encode()
        )
        addons.add(conn, vid, manifest)
        addon = addons.list_for(conn, vid)[0]
        token = addons.set_up(conn, vid, addon, {"mode": "eco"})
        return token


def _restore(client, data, mode="copy"):
    """Upload a backup; when the car is already here the page asks - answer with ``mode`` (replace | copy | cancel)."""
    res = client.post("/vehicles/restore", files={"backup": ("car.zip", data, "application/zip")}, follow_redirects=False)
    if res.status_code == 200 and "/vehicles/restore/confirm" in res.text:
        token = re.search(r'name="token" value="([^"]+)"', res.text).group(1)
        res = client.post("/vehicles/restore/confirm", data={"token": token, "mode": mode}, follow_redirects=False)
    return res


def test_vehicle_roundtrip_keeps_everything_of_that_car(client):
    car = _car(client)
    token = _fill(car["id"])
    with db.tx() as conn:
        data = vehiclebackup.export(conn, car["id"])
    res = _restore(client, data)
    assert res.status_code == 303
    with db.tx() as conn:
        new = conn.execute("SELECT * FROM vehicles WHERE id != ?", (car["id"],)).fetchone()
        assert new["name"] == "Backup Car 2" and new["slug"] != car["slug"] and new["plate"] == "AB-CD 123"
        nid = new["id"]
        assert conn.execute("SELECT title, cost FROM service WHERE vehicle_id = ?", (nid,)).fetchone()["cost"] == 99.5
        trip = conn.execute("SELECT id FROM trips WHERE vehicle_id = ?", (nid,)).fetchone()["id"]
        assert conn.execute("SELECT COUNT(*) FROM trip_points WHERE trip_id = ?", (trip,)).fetchone()[0] == 3
        doc = conn.execute("SELECT id FROM documents WHERE vehicle_id = ?", (nid,)).fetchone()["id"]
        assert conn.execute("SELECT value FROM settings WHERE key = ?", (f"modules.off.{nid}",)).fetchone()["value"] == '["tires"]'
        # the plugin: its settings are back, it is OFF, and the package is asked for; the original car is untouched
        item = addons.list_for(conn, nid)[0]
        assert item["missing"] is False and item["active"] == 0 and item["vals"] == {"mode": "eco"}
        assert conn.execute("SELECT COUNT(*) FROM service WHERE vehicle_id = ?", (car["id"],)).fetchone()[0] == 1
    assert (config.files_dir() / str(nid) / f"{doc}.txt").read_bytes() == b"hello"
    assert token  # the token of the original stays valid for the original (same hash exists once)


def test_token_comes_back_for_the_copy_only_when_the_system_does_not_know_it(client):
    car = _car(client)
    token = _fill(car["id"])
    with db.tx() as conn:
        data = vehiclebackup.export(conn, car["id"])
        conn.execute("DELETE FROM vehicles WHERE id = ?", (car["id"],))  # the car is gone, e.g. a fresh system
    _restore(client, data)
    with db.tx() as conn:
        nid = conn.execute("SELECT id FROM vehicles").fetchone()["id"]
        item = addons.list_for(conn, nid)[0]
        assert item["token_id"] is not None  # the plugin's token is back (the same one it already holds)
        conn.execute("UPDATE vehicle_addons SET active = 1 WHERE id = ?", (item["id"],))
        assert connectors.verify(conn, token)["vehicle_id"] == nid
    _restore(client, data)  # a second copy next to it: the token belongs to the first one
    with db.tx() as conn:
        second = conn.execute("SELECT id FROM vehicles WHERE id != ?", (nid,)).fetchone()["id"]
        assert addons.list_for(conn, second)[0]["token_id"] is None


def test_missing_package_is_asked_for_with_the_right_hint(client, fake_source):
    car = _car(client)
    _fill(car["id"])
    with db.tx() as conn:
        data = vehiclebackup.export(conn, car["id"])
        conn.execute("DELETE FROM vehicle_addons WHERE vehicle_id = ?", (car["id"],))  # nothing installed on this system
        conn.execute("UPDATE vehicle_addons SET source_url = NULL")
    data = _with_source(data, "https://github.com/example/pkgs")
    _restore(client, data)
    with db.tx() as conn:
        new = conn.execute("SELECT id, slug FROM vehicles WHERE id != ?", (car["id"],)).fetchone()
    page = client.get(f"/v/{new['slug']}/plugins").text
    assert "braucht das Paket" in page or "needs the package" in page
    assert "https://github.com/example/pkgs" in page  # the source is missing: say which one to add first
    # the source is added and updated: the package can be installed and arrives switched OFF with the saved settings
    client.post("/sources", data={"kind": "plugin", "url": "https://github.com/example/pkgs"})
    page = client.get(f"/v/{new['slug']}/plugins").text
    assert "/packages/" in page and "/install" in page
    with db.tx() as conn:
        sid = conn.execute("SELECT id FROM sources WHERE url = 'https://github.com/example/pkgs'").fetchone()["id"]
    client.post(f"/v/{new['id']}/packages/{sid}/plugin/sim-plugin/install")
    with db.tx() as conn:
        item = addons.list_for(conn, new["id"])[0]
    assert item["status"] == "configured" and item["active"] == 0 and item["vals"] == {"mode": "eco"} and item["source_id"] == sid


def _with_source(data, url):
    """A copy of the backup in which the plugin remembers where it came from."""
    zin = zipfile.ZipFile(io.BytesIO(data))
    doc = json.loads(zin.read("vehicle.json"))
    for entry in doc["addons"]:
        entry["source_url"] = url
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zout:
        zout.writestr("vehicle.json", json.dumps(doc))
    return out.getvalue()


def test_old_and_unknown_things_do_not_break_a_restore(client):
    car = _car(client)
    with db.tx() as conn:
        data = vehiclebackup.export(conn, car["id"])
    doc = json.loads(zipfile.ZipFile(io.BytesIO(data)).read("vehicle.json"))
    doc["vehicle"]["a_column_from_the_future"] = "x"
    doc["tables"]["a_table_from_the_future"] = [{"x": 1}]
    del doc["vehicle"]["plate"]  # a column the old backup did not have yet
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("vehicle.json", json.dumps(doc))
    assert _restore(client, out.getvalue()).status_code == 303
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0] == 2


def test_wrong_files_are_refused(client):
    car = _car(client)
    with db.tx() as conn:
        data = vehiclebackup.export(conn, car["id"])
    doc = json.loads(zipfile.ZipFile(io.BytesIO(data)).read("vehicle.json"))
    cases = {}
    for label, change in (("newer", {"format": vehiclebackup.FORMAT + 1}), ("system", {"kind": "system"})):
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as z:
            z.writestr("vehicle.json", json.dumps({**doc, **change}))
        cases[label] = out.getvalue()
    slip = io.BytesIO()
    with zipfile.ZipFile(slip, "w") as z:
        z.writestr("vehicle.json", json.dumps(doc))
        z.writestr("files/../../evil.txt", "x")
    for raw in (*cases.values(), slip.getvalue(), b"not a zip"):
        res = _restore(client, raw)
        assert res.status_code == 303 and "m=err.vb_" in res.headers["location"]
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0] == 1
    # and the two backups cannot be mixed up
    system = zipfile.ZipFile(io.BytesIO(backup.create())).read("manifest.json")
    assert json.loads(system)["kind"] == "system" and json.loads(system)["format"] == backup.FORMAT


def test_backup_download_and_cards(client):
    car = _car(client)
    res = client.get(f"/v/{car['slug']}/backup.zip")
    assert res.status_code == 200 and res.headers["content-type"] == "application/zip"
    assert zipfile.ZipFile(io.BytesIO(res.content)).namelist()[0] == "vehicle.json"
    assert "backup.zip" in client.get(f"/settings/car?car={car['slug']}").text
    assert "/vehicles/restore" in client.get("/vehicles/new").text


def test_start_list_is_a_plain_choice_and_manage_lives_under_vehicles(client):
    car = _car(client)
    _car2 = client.post("/vehicles", data={"name": "Second Car", "fuel_type": "petrol"})
    plain = client.get("/").text  # two cars: the list to choose from
    assert "Second Car" in plain and "/vehicles/new" not in plain and "/vehicles/restore" not in plain and "round-del" not in plain
    assert f"/v/{car['slug']}/backup.zip" not in plain
    manage = client.get("/vehicles").text  # Weiteres -> Vehicles: everything
    assert "/vehicles/new" in manage and "/vehicles/restore" in manage and f"/v/{car['slug']}/backup.zip" in manage


def test_a_car_that_is_already_here_is_asked_about(client):
    car = _car(client)
    _fill(car["id"])
    with db.tx() as conn:
        data = vehiclebackup.export(conn, car["id"])
    # what the user did to the car after the backup
    with db.tx() as conn:
        conn.execute(
            "INSERT INTO service(vehicle_id, date, title, odometer_km, cost) VALUES(?, '2026-05-05', 'Later', 5000, 10)", (car["id"],)
        )
        conn.execute("UPDATE vehicles SET plate = 'ZZ-99' WHERE id = ?", (car["id"],))
    page = client.post("/vehicles/restore", files={"backup": ("car.zip", data, "application/zip")})
    assert page.status_code == 200 and "Backup Car" in page.text and "vehicles/restore/confirm" in page.text  # asks, restores nothing yet
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0] == 1

    # replace: the same car (id and address stay) is back at the state of the backup, a safety copy was saved
    res = _restore(client, data, "replace")
    assert res.status_code == 303 and res.headers["location"].split("?")[0].split("/v/")[1].startswith(car["slug"])
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0] == 1
        row = conn.execute("SELECT id, plate FROM vehicles").fetchone()
        assert row["id"] == car["id"] and row["plate"] == "AB-CD 123"
        assert [r["title"] for r in conn.execute("SELECT title FROM service WHERE vehicle_id = ?", (car["id"],))] == ["Oil"]
        assert conn.execute("SELECT COUNT(*) FROM trip_points").fetchone()[0] == 3
    assert list((config.data_dir() / "backups").glob("vehicle-*-before-restore-*.zip"))

    # copy: a second car, its name and its address carry a number
    _restore(client, data, "copy")
    with db.tx() as conn:
        cars = conn.execute("SELECT name, slug FROM vehicles ORDER BY id").fetchall()
    assert [(c["name"], c["slug"]) for c in cars] == [("Backup Car", car["slug"]), ("Backup Car 2", car["slug"] + "-2")]

    # cancel: nothing happens and the file kept for the question is gone
    kept = len(list((config.data_dir() / "tmp").glob("restore-*.zip")))  # (the first question above was never answered)
    _restore(client, data, "cancel")
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0] == 2
    assert len(list((config.data_dir() / "tmp").glob("restore-*.zip"))) == kept
    assert (
        "m=err.vb_expired"
        in client.post("/vehicles/restore/confirm", data={"token": "x" * 22, "mode": "replace"}, follow_redirects=False).headers["location"]
    )


def test_the_same_car_is_found_by_identity_even_when_renamed(client):
    car = _car(client)
    with db.tx() as conn:
        data = vehiclebackup.export(conn, car["id"])  # gives the car its identity
        conn.execute("UPDATE vehicles SET name = 'Renamed' WHERE id = ?", (car["id"],))
    page = client.post("/vehicles/restore", files={"backup": ("car.zip", data, "application/zip")})
    assert page.status_code == 200 and "Renamed" in page.text
    # a car this system has never seen goes in at once
    with db.tx() as conn:
        conn.execute("DELETE FROM vehicles")
    assert (
        client.post("/vehicles/restore", files={"backup": ("car.zip", data, "application/zip")}, follow_redirects=False).status_code == 303
    )


def test_what_the_user_saved_in_a_plugin_comes_back_with_the_car(client):
    """Everything saved in the plugin's settings window (a note, a choice, a number) is part of the car's backup - not the package itself."""
    car = _car(client)
    manifest = addons.parse_package(
        json.dumps(
            {
                "id": "note-plugin", "kind": "plugin", "name": "Notes", "version": "1",
                "settings": [{"key": "note", "label": "Note", "type": "textarea"}, {"key": "mode", "label": "Mode", "type": "select", "options": [{"value": "a", "label": "A"}]}],
            }
        ).encode()
    )  # fmt: skip
    with db.tx() as conn:
        addons.add(conn, car["id"], manifest)
        row = addons.list_for(conn, car["id"])[0]
    note = "A longer note. " * 30
    client.post(f"/v/{car['slug']}/integrations/{row['id']}/setup", data={"note": note, "mode": "a"})
    with db.tx() as conn:
        data = vehiclebackup.export(conn, car["id"])
        conn.execute("DELETE FROM vehicles WHERE id = ?", (car["id"],))
    _restore(client, data)
    with db.tx() as conn:
        new = conn.execute("SELECT id FROM vehicles").fetchone()["id"]
        item = addons.list_for(conn, new)[0]
    assert (
        item["vals"] == {"note": note.strip()[:1000], "mode": "a"} and item["missing"]
    )  # the values are back, the package itself is asked for


def test_the_example_vehicle_file_can_be_restored(client, tmp_path, monkeypatch):
    import runpy

    from carassistant import db, vehiclebackup

    monkeypatch.chdir(tmp_path)
    runpy.run_path(str(__import__("pathlib").Path(__file__).parent.parent / "docs/examples/make_vehicle_file.py"))
    with db.tx() as conn:
        vid = vehiclebackup.restore(conn, (tmp_path / "example-vehicle.zip").read_bytes())
        car = conn.execute("SELECT name, tank_l FROM vehicles WHERE id = ?", (vid,)).fetchone()
        assert car["name"] == "Example" and car["tank_l"] == 55
        assert conn.execute("SELECT COUNT(*) FROM fuel WHERE vehicle_id = ? AND amount = 41.2", (vid,)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM trips WHERE vehicle_id = ? AND source = 'import'", (vid,)).fetchone()[0] == 1


def test_manual_images_travel_with_the_car_backup(client):
    from carassistant import manual
    from test_web import _dummy_package

    car = _car(client, "Manual Car")
    with db.tx() as conn:
        manual.import_package(conn, car["id"], "pack.zip", io.BytesIO(_dummy_package()))
    raw = client.get(f"/v/{car['slug']}/backup.zip").content if False else None
    with db.tx() as conn:
        raw = vehiclebackup.export(conn, car["id"])
    names = zipfile.ZipFile(io.BytesIO(raw)).namelist()
    assert "files/manual/0001.avif" in names and "files/manual/0004.avif" in names
    with db.tx() as conn:
        new_id = vehiclebackup.restore(conn, raw)
        meta = manual.info(conn, new_id)
        assert (meta["page_offset"], meta["images"], meta["pages"]) == (2, 4, 4)
        assert manual.image_path(new_id, 3).is_file()
        assert [r["depth"] for r in conn.execute("SELECT depth FROM manual_chapters WHERE vehicle_id = ? ORDER BY sort", (new_id,))] == [
            0,
            1,
            0,
        ]
        vehiclebackup.replace(conn, raw, car["id"])  # replace: the images are put back, not lost
        assert manual.image_path(car["id"], 2).is_file()
    # the whole system backup carries them as ordinary files
    assert f"files/manual/{car['id']}/0001.avif" in zipfile.ZipFile(io.BytesIO(backup.create())).namelist()
