"""A refuel the car noticed: its mark lives in columns (never in the notes), the card turns into the form to complete it - scan a photo or a file, keep
the odometer the car gave, check, save - and the reminder goes after the save, or after three trips, or after three days."""

from datetime import UTC, date, datetime, timedelta

from tests.test_web import create_vehicle, slug

from carassistant import connectors, db, refuel_detect


def _noticed(client, name="Pump Car", tank=50):
    """A car whose tank jumped from 20 to 95 %: one unfinished refuel, the car's own odometer in it."""
    vid = create_vehicle(client, name)
    with db.tx() as conn:
        conn.execute("UPDATE vehicles SET tank_l = ? WHERE id = ?", (tank, vid))
        connectors._store(conn, vid, "fuel_level", "20")
        connectors._store(conn, vid, "fuel_level", "95")
        row = conn.execute("SELECT * FROM fuel WHERE vehicle_id = ?", (vid,)).fetchone()
    return vid, row


def _trip(conn, vid, day, start):
    conn.execute("INSERT INTO trips(vehicle_id, date, start_time, end_time, distance_km) VALUES(?,?,?,?,1)", (vid, day, start, start))


def test_the_card_of_a_noticed_refuel_is_the_form_to_complete_it(client, monkeypatch):
    from carassistant import receipt

    monkeypatch.setattr(receipt, "available", lambda: True)
    vid, row = _noticed(client)
    base = f"/v/{slug(vid)}/e/fuel"
    assert (row["notes"], row["auto_kind"], row["auto_open"], row["odometer_km"]) == (
        None,
        "tank",
        1,
        50000,
    )  # nothing but the entry's own data in the notes
    page = client.get(base).text
    assert (
        f'href="/v/{vid}/e/fuel?edit={row["id"]}#fuel-{row["id"]}"' in page and f'id="fuel-{row["id"]}"' in page
    )  # the reminder leads to the card
    assert 'class="rec rcpt rec-tap" id="fuel-' in page  # still closed until it is asked for; a till receipt like the cards of Parts
    open_page = client.get(f"{base}?edit={row['id']}").text
    assert f'class="rec rcpt rec-tap editing" id="fuel-{row["id"]}"' in open_page
    card = open_page.split(f'id="fuel-{row["id"]}"')[1].split("</article>")[0]
    assert "None" not in card and 'value="50000"' in card  # an empty field is empty, and the odometer the car gave stays
    assert 'placeholder="~38"' in card  # the rough estimate from the tank size is a hint in the amount field, never a value
    assert card.count("data-scan-btn") == 2 and 'data-scan-btn="camera"' in card and 'data-scan-btn="file"' in card  # Scan, and Load file
    assert 'data-scan-file="camera"' in card and 'capture="environment"' in card and 'accept="image/*,application/pdf"' in card
    assert "data-rec-cancel" in card and f'form="del-{row["id"]}"' in card and "btn-edit" not in card  # close, delete, save: like Parts
    assert card.index("data-scan-btn") < card.index('name="date"')  # the scan row is above the fields
    assert "<details" not in card and 'class="rec-edit"' not in card  # the old fold with its own edit button is gone


def test_saving_the_card_ends_the_reminder_and_leaves_the_notes_alone(client):
    vid, row = _noticed(client)
    base = f"/v/{slug(vid)}/e/fuel"
    assert "Refuel noticed" in client.get(base).text and refuel_detect_todo(vid) == 1
    done = client.post(
        f"{base}/{row['id']}",
        data={
            "date": row["date"],
            "odometer_km": "50000",
            "amount": "42.79",
            "price_per_unit": "1.969",
            "price_total": "84.25",
            "full_tank": "1",
        },
        follow_redirects=False,
    )
    assert done.status_code == 303
    with db.tx() as conn:
        saved = conn.execute("SELECT * FROM fuel WHERE id = ?", (row["id"],)).fetchone()
    assert (saved["amount"], saved["price_total"], saved["auto_open"], saved["notes"]) == (42.79, 84.25, 0, None)
    assert refuel_detect_todo(vid) == 0 and "Refuel noticed" not in client.get(base).text


def refuel_detect_todo(vid):
    with db.tx() as conn:
        return len(refuel_detect.todo(conn, vid))


def test_saving_without_the_receipt_also_ends_the_reminder_but_the_entry_stays_open_for_later(client):
    vid, row = _noticed(client)
    client.post(f"/v/{slug(vid)}/e/fuel/{row['id']}", data={"date": row["date"], "odometer_km": "50000", "full_tank": "1"})
    assert refuel_detect_todo(vid) == 0  # the person has seen it and saved it
    page = client.get(f"/v/{slug(vid)}/e/fuel").text
    assert "Refuel noticed" in page  # the card still says what it is (no amount yet) ...
    assert "data-rec-open" in page  # ... and can be completed from its card whenever the receipt turns up


def test_the_reminder_goes_after_three_trips_or_three_days(client):
    vid, row = _noticed(client)
    at = datetime.now().strftime(refuel_detect.STAMP)
    day, now = at[:10], at[11:16]
    with db.tx() as conn:
        _trip(conn, vid, day, "00:01")  # driven BEFORE the refuel was noticed: the way to the pump
        assert refuel_detect.trips_since(conn, vid, f"{day}T{now}") == 0 or now < "00:01"
        conn.execute("UPDATE fuel SET auto_at = ? WHERE id = ?", (f"{day}T00:30", row["id"]))
        _trip(conn, vid, day, "09:00")
        _trip(conn, vid, day, "09:10")
    assert refuel_detect_todo(vid) == 1  # two trips since 00:30 are not enough
    with db.tx() as conn:
        _trip(conn, vid, day, "09:20")
    assert refuel_detect_todo(vid) == 0  # the third ends it
    other, second = _noticed(client, "Slow Car")
    old = (datetime.now() - timedelta(days=4)).strftime(refuel_detect.STAMP)
    with db.tx() as conn:
        conn.execute("UPDATE fuel SET auto_at = ? WHERE id = ?", (old, second["id"]))
    assert refuel_detect_todo(other) == 0  # four days without a receipt: it is let go
    with db.tx() as conn:
        assert (
            conn.execute("SELECT auto_open FROM fuel WHERE id = ?", (second["id"],)).fetchone()[0] == 1
        )  # nothing was changed, only not shown


def test_marks_that_older_versions_wrote_into_the_notes_move_into_the_columns(client):
    vid = create_vehicle(client, "Old Marks")
    other = create_vehicle(client, "Other Car")
    with db.tx() as conn:
        for car, notes, amount, total in (
            (vid, "auto:tank:+78%:2026-11-27T07:48", None, None),
            (vid, "auto:charge:+50%:2026-11-26T18:05", None, None),
            (vid, "auto:tank:api:2026-11-25T09:00", None, None),
            (vid, "api:my-plugin", 41.5, 70.0),
            (vid, "auto:tank:+40%:2026-11-20T10:00", 38.0, 60.0),  # completed already
            (vid, "a note of my own", None, None),
            (other, "auto:tank:+10%:2026-11-27T07:00", None, None),
        ):
            conn.execute(
                "INSERT INTO fuel(vehicle_id, date, amount, price_total, notes) VALUES(?, '2026-11-27', ?, ?, ?)",
                (car, amount, total, notes),
            )
        assert refuel_detect.migrate_marks(conn, vid) == 5  # only this car
        rows = conn.execute(
            "SELECT notes, amount, auto_kind, auto_rise, auto_at, auto_src, auto_open FROM fuel WHERE vehicle_id = ? ORDER BY id", (vid,)
        ).fetchall()
        assert [tuple(r) for r in rows] == [
            (None, None, "tank", 78.0, "2026-11-27T07:48", None, 1),
            (None, None, "charge", 50.0, "2026-11-26T18:05", None, 1),
            (None, None, "api", None, "2026-11-25T09:00", None, 1),
            (None, 41.5, "api", None, None, "my-plugin", 0),
            (None, 38.0, "tank", 40.0, "2026-11-20T10:00", None, 0),
            ("a note of my own", None, None, None, None, None, 0),
        ]
        assert refuel_detect.migrate_marks(conn, vid) == 0  # again: nothing left to move
        assert (
            conn.execute("SELECT notes FROM fuel WHERE vehicle_id = ?", (other,)).fetchone()[0].startswith("auto:")
        )  # the other car waits for its own turn
        assert refuel_detect.migrate_marks(conn) == 1


def test_a_backup_from_before_the_columns_comes_back_clean(client):
    from carassistant import vehiclebackup

    vid = create_vehicle(client, "Backup Car")
    with db.tx() as conn:
        conn.execute("INSERT INTO fuel(vehicle_id, date, notes) VALUES(?, '2026-11-27', 'auto:tank:+78%:2026-11-27T07:48')", (vid,))
        refuel_detect.migrate_marks(conn)  # (this version would have cleaned it already: put the old mark back, as an old backup holds it)
        conn.execute(
            "UPDATE fuel SET notes = 'auto:tank:+78%:2026-11-27T07:48', auto_kind = NULL, auto_rise = NULL, auto_at = NULL, auto_open = 0"
        )
        raw = vehiclebackup.export(conn, vid)
    with db.tx() as conn:
        new_vid = vehiclebackup.restore(conn, raw)
        row = conn.execute("SELECT notes, auto_kind, auto_rise, auto_open FROM fuel WHERE vehicle_id = ?", (new_vid,)).fetchone()
    assert tuple(row) == (None, "tank", 78.0, 1)


def test_an_entry_without_amount_shows_no_none_in_any_list(client):
    vid = create_vehicle(client, "Empty Fields")
    base = f"/v/{slug(vid)}"
    client.post(f"{base}/e/fuel", data={"date": "2026-11-01", "odometer_km": "51000", "full_tank": "1"})
    client.post(f"{base}/e/service", data={"date": "2026-11-02", "title": "Oil"})
    client.post(f"{base}/e/parts", data={"date": "2026-11-03", "name": "Filter"})
    for url in ("/e/fuel", "/e/service", "/e/parts"):
        page = client.get(base + url).text
        assert 'value="None"' not in page and ">None<" not in page, url


def test_edit_in_the_address_opens_that_entry_on_every_list(client):
    vid = create_vehicle(client, "Open Car")
    base = f"/v/{slug(vid)}"
    client.post(f"{base}/e/service", data={"date": "2026-11-02", "title": "Oil"})
    with db.tx() as conn:
        sid = conn.execute("SELECT id FROM service WHERE vehicle_id = ?", (vid,)).fetchone()[0]
    assert " editing" in client.get(f"{base}/e/service?edit={sid}").text and " editing" not in client.get(f"{base}/e/service").text


def test_a_file_that_is_a_pdf_can_be_scanned_too(client, monkeypatch):
    from tests.test_invoice import _pdf

    from carassistant import receipt

    vid = create_vehicle(client, "Pdf Car")
    monkeypatch.setattr(receipt, "available", lambda: True)
    lines = [
        "BFT Tankstelle Musterstadt",
        "Datum  " + date.today().strftime("%d.%m.%Y"),
        "42,79 Liter DIESEL",
        "1,969 EUR/Liter",
        "TOTAL 84,25 EUR",
    ]
    got = client.post(f"/v/{vid}/fuel/scan", content=_pdf(lines), headers={"Content-Type": "application/pdf"})
    assert got.status_code == 200, got.text
    d = got.json()
    assert (d["amount"], d["price_per_unit"], d["price_total"]) == ("42.79", "1.969", "84.25") and d["checked"] is True


def test_the_add_form_has_the_same_scan_row_and_a_bar_with_close_and_save(client, monkeypatch):
    from carassistant import receipt

    monkeypatch.setattr(receipt, "available", lambda: True)
    vid = create_vehicle(client, "Add Car")
    page = client.get(f"/v/{slug(vid)}/e/fuel").text
    panel = page.split('id="fuel-add"')[1].split("</form>")[0]
    assert (
        'data-scan-btn="camera"' in panel
        and 'data-scan-btn="file"' in panel
        and 'data-toggle-panel="#fuel-add"' in panel
        and 'class="primary"' in panel
    )
    assert datetime.now(UTC).year > 2000  # (keeps the imports honest)


def test_a_new_fill_up_starts_with_todays_date(client):
    vid = create_vehicle(client, "Today Car")
    panel = client.get(f"/v/{slug(vid)}/e/fuel").text.split('id="fuel-add"')[1].split("</form>")[0]
    assert f'name="date" value="{date.today().isoformat()}"' in panel
