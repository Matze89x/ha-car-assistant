"""Reading a fuel receipt: the parser on the text Tesseract finds (no photo needed)."""

import re
from datetime import date

from carassistant import receipt

TODAY = date(2026, 11, 23)

ARAL = """
ARAL Tankstelle
Musterstrasse 12
12345 Musterstadt
Tel. 01234 56789

Datum: 21.11.2026   Uhrzeit 17:42
Zapfsaeule 4
Super E10      45,32 l
Preis/l        1,789 EUR/l
Gesamtbetrag   81,08 EUR
MwSt 19%       12,95 EUR
Vielen Dank fuer Ihren Besuch
"""

SHELL_MISREAD = """
Shell
Kassenbon
Datum 03.11.26
V-Power Diesel
Menge  38,O7 L
EUR/L 1,659
Summe EUR 63,19
EC-Karte 63,19
"""


def test_a_typical_receipt_is_read_completely():
    r = receipt.parse(ARAL, TODAY)
    assert r["amount"] == 45.32
    assert r["price_per_unit"] == 1.789
    assert r["price_total"] == 81.08
    assert r["date"] == "2026-11-21"
    assert r["station"] == "Aral Musterstadt"
    assert r["notes"] == "Super E10"
    assert r["checked"] is True
    assert set(r["found"]) == {"date", "amount", "price_per_unit", "price_total", "station", "notes"}


def test_a_letter_o_inside_a_number_is_read_as_zero_and_the_product_is_named():
    r = receipt.parse(SHELL_MISREAD, TODAY)
    assert r["amount"] == 38.07
    assert r["price_per_unit"] == 1.659
    assert r["price_total"] == 63.19
    assert r["date"] == "2026-11-03"
    assert r["station"] == "Shell"
    assert r["notes"] == "V-Power Diesel"


def test_a_missing_total_is_calculated_and_a_missing_amount_too():
    text = "Aral\nSuper E10\nMenge 40,00 l\nPreis 1,800 EUR/l\n"
    r = receipt.parse(text, TODAY)
    assert (r["amount"], r["price_per_unit"], r["price_total"]) == (40.0, 1.8, 72.0)
    text = "Jet\nDiesel\nPreis 1,700 EUR/l\nSumme EUR 51,00\n"
    r = receipt.parse(text, TODAY)
    assert r["price_total"] == 51.0 and r["amount"] == 30.0


def test_a_date_in_the_future_or_a_phone_number_is_no_refuel_date():
    r = receipt.parse("Aral\nTel 01.02.2040\nDatum 05.11.2026\n", TODAY)
    assert r["date"] == "2026-11-05"
    r = receipt.parse("Aral\nDatum 2026-10-30\n", TODAY)
    assert r["date"] == "2026-10-30"


def test_an_unknown_station_takes_its_name_from_the_head_and_text_without_a_refuel_gives_nothing():
    r = receipt.parse("Muster Autohof GmbH\nDiesel\nMenge 50,00 l\n1,600 EUR/l\nGesamt 80,00\n", TODAY)
    assert r["station"] == "Muster Autohof GmbH"
    assert r["price_total"] == 80.0
    empty = receipt.parse("", TODAY)
    assert empty["found"] == [] and empty["amount"] is None
    noise = receipt.parse("Brot 2,49\nMilch 1,19\nSumme 3,68\n", TODAY)
    assert noise["amount"] is None and noise["price_per_unit"] is None


def test_the_check_amount_times_price_equals_total_picks_the_matching_numbers():
    text = "Esso\nMenge 12,00 l\nMenge 30,00 l\nPreis/l 1,500 EUR/l\nGesamt 45,00\nBar 50,00\n"
    r = receipt.parse(text, TODAY)
    assert (r["amount"], r["price_total"]) == (30.0, 45.0)


def test_something_that_is_no_photo_is_refused():
    import pytest

    with pytest.raises(ValueError):
        receipt.clean(b"this is not an image")
    with pytest.raises(ValueError):
        receipt.scan(b"x" * (receipt.MAX_BYTES + 1))


def test_an_unreadable_value_is_calculated_and_said_so():
    r = receipt.parse("Aral\nSuper E10\nMenge A532 l\nPreis/l 1,789 EUR/l\nGesamtbetrag 81,08 EUR\n", TODAY)
    assert r["amount"] == 45.32 and r["derived"] == ["amount"]
    r = receipt.parse(ARAL, TODAY)
    assert r["derived"] == []


def test_the_scan_route_fills_in_the_units_shown(env, monkeypatch):
    from fastapi.testclient import TestClient

    from carassistant import db, receipt_web, web
    from carassistant import receipt as rc

    with db.tx() as conn:
        conn.execute("INSERT INTO vehicles (name, slug, fuel_type) VALUES ('Test', 'test', 'petrol')")
        vid = conn.execute("SELECT id FROM vehicles").fetchone()["id"]
    monkeypatch.setattr(rc, "available", lambda: True)
    monkeypatch.setattr(rc, "scan", lambda data, today=None: rc.parse(ARAL, TODAY))
    client = TestClient(web.app, base_url="http://testserver", headers={"Origin": "http://testserver"})
    r = client.post(f"/v/{vid}/fuel/scan", content=b"\xff\xd8\xff", headers={"Content-Type": "image/jpeg"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert (d["amount"], d["price_per_unit"], d["price_total"], d["station"]) == ("45.32", "1.789", "81.08", "Aral Musterstadt")
    assert receipt_web.shown(rc.parse("", TODAY), __import__("carassistant.units", fromlist=["x"]).of(None), "L")["amount"] == ""
    monkeypatch.setattr(rc, "available", lambda: False)
    assert client.post(f"/v/{vid}/fuel/scan", content=b"x").status_code == 501


def test_one_misread_digit_of_the_amount_is_corrected_from_price_and_total():
    r = receipt.parse("Shell\nV-Power Diesel\nMenge 32,18 L\nPreis/Liter 1,659 EUR\nBetrag EUR 86,57\n", TODAY)
    assert r["amount"] == 52.18 and r["derived"] == ["amount"] and r["price_total"] == 86.57
    far = receipt.parse("Shell\nMenge 10,00 L\nPreis/Liter 1,659 EUR\nBetrag EUR 86,57\n", TODAY)
    assert far["amount"] == 10.0 and far["derived"] == []  # not one digit: nothing is guessed


def test_the_word_total_before_an_amount_is_no_station():
    r = receipt.parse("BP Service Station\n12 High Street\nVolume 41.20 L\nPrice 1.589 /L\nTotal 65.47 EUR\n", TODAY)
    assert r["station"] == "BP" and r["price_total"] == 65.47
    assert receipt.parse("TotalEnergies Access\nDiesel\n", TODAY)["station"].startswith("TotalEnergies")


# ------------------------------------------------------------------ the odometer


def test_numbers_of_an_odometer_photo_are_found_split_groups_joined_and_noise_dropped():
    from carassistant import odometer_scan as o

    assert o.numbers("052340\n12") == [52340]  # leading zeros, a trip counter that is too short
    assert 52340 in o.numbers("52 340 km")  # a thousands split is read as one number
    assert o.numbers("1234567890") == []  # more than seven digits is no odometer
    assert o.numbers("12") == [] and o.numbers("") == []


def test_the_most_plausible_number_wins_and_an_odd_one_is_flagged():
    from carassistant import odometer_scan as o

    assert o.plausible(52500, 52340) and not o.plausible(1200, 52340) and not o.plausible(900_000, 52340)  # below the last: a trip counter
    assert o.plausible(52340, None) and not o.plausible(12, None)
    assert o.pick([1234, 52340, 52340, 1234], 52000) == (52340, True)  # the plausible one, not the trip counter seen as often
    assert o.pick([1234], 52000) == (1234, False)  # only something odd: it is offered, flagged
    assert o.pick([], 52000) == (None, False)
    assert o.pick([5000, 51000], None) == (51000, True)  # no last reading: the longer number


def test_the_odometer_scan_route_answers_in_the_unit_shown_and_the_quick_save_stores_kilometres(env, monkeypatch):
    from fastapi.testclient import TestClient

    from carassistant import db, odometer_scan, summary, web
    from carassistant import receipt as rc

    with db.tx() as conn:
        conn.execute("INSERT INTO vehicles (name, slug, fuel_type) VALUES ('Test', 'test', 'petrol')")
        vid = conn.execute("SELECT id FROM vehicles").fetchone()["id"]
        summary.add_odometer(conn, vid, 52000)
    monkeypatch.setattr(rc, "available", lambda: True)
    seen = {}

    def fake(data, last=None):
        seen["last"] = last
        return {"value": 52340, "plausible": True}

    monkeypatch.setattr(odometer_scan, "read", fake)
    client = TestClient(web.app, base_url="http://testserver", headers={"Origin": "http://testserver"})
    r = client.post(f"/v/{vid}/odometer/scan", content=b"\xff\xd8\xff", headers={"Content-Type": "image/jpeg"})
    assert r.status_code == 200 and r.json() == {"odometer": "52340", "plausible": True, "last": 52000} and seen["last"] == 52000
    monkeypatch.setattr(odometer_scan, "read", lambda data, last=None: {"value": None, "plausible": False})
    assert client.post(f"/v/{vid}/odometer/scan", content=b"x").json()["odometer"] == ""
    monkeypatch.setattr(rc, "available", lambda: False)
    assert client.post(f"/v/{vid}/odometer/scan", content=b"x").status_code == 501
    # the quick save: the number as shown (here kilometres), spaces allowed, nonsense refused
    assert client.post(f"/v/{vid}/odometer/quick", data={"odometer": "52 340"}, follow_redirects=False).status_code == 303
    with db.tx() as conn:
        assert summary.current_odometer(conn, vid) == 52340
    client.post(f"/v/{vid}/odometer/quick", data={"odometer": "abc"})
    with db.tx() as conn:
        assert summary.current_odometer(conn, vid) == 52340  # nothing changed


def test_the_dashboard_has_the_quick_entry_and_only_offers_the_photo_when_text_recognition_is_there(client, monkeypatch):
    from tests.test_web import create_vehicle, slug

    from carassistant import db, summary
    from carassistant import receipt as rc

    vid = create_vehicle(client)
    with db.tx() as conn:
        summary.add_odometer(conn, vid, 52000)
    monkeypatch.setattr(rc, "available", lambda: True)
    page = client.get(f"/v/{slug(vid)}").text
    assert (
        'class="odo-entry"' in page
        and f"/v/{slug(vid)}/odometer/scan" in page
        and "receipt.js" in page
        and page.count("data-scan-btn") == 1  # one photo button: the phone offers camera or library
    )
    monkeypatch.setattr(rc, "available", lambda: False)
    page = client.get(f"/v/{slug(vid)}").text
    assert 'class="odo-entry"' in page and "data-scan-btn" not in page  # typing always works


# ------------------------------------------------------------------ an odometer that runs backwards


def test_outliers_are_the_readings_that_break_the_rising_order_and_of_two_that_contradict_the_higher_is_odd():
    from carassistant.summary import outliers

    assert outliers([4300, 4100]) == {0}  # two that contradict each other: the higher is the odd one (it would stay the highest for good)
    assert outliers([52000, 520000, 52500, 53000]) == {1}  # a typo that is too high: only the typo
    assert outliers([52000, 5200, 52500]) == {1}  # a typo that is too low
    assert outliers([1, 2, 2, 3]) == set() and outliers([]) == set() and outliers([7]) == set()


def test_a_lower_or_far_higher_number_asks_first_and_is_saved_only_when_confirmed(client):
    from tests.test_web import create_vehicle, slug

    from carassistant import db, summary

    vid = create_vehicle(client)
    with db.tx() as conn:
        conn.execute("DELETE FROM odometer WHERE vehicle_id = ?", (vid,))  # the car starts without a reading
        summary.add_odometer(conn, vid, 4300)
    url = f"/v/{slug(vid)}/odometer/quick"
    page = client.post(url, data={"odometer": "4100"})  # lower than the last reading
    assert page.status_code == 200 and 'name="confirm"' in page.text and 'value="4100"' in page.text  # the question, not the saving
    with db.tx() as conn:
        assert (
            summary.current_odometer(conn, vid) == 4300 and conn.execute("SELECT COUNT(*) FROM odometer").fetchone()[0] == 1
        )  # nothing saved yet
    far = client.post(url, data={"odometer": "430000"})
    assert far.status_code == 200 and 'name="confirm"' in far.text
    assert client.post(url, data={"odometer": "4500"}, follow_redirects=False).status_code == 303  # a normal step: saved at once
    ok = client.post(url, data={"odometer": "4100", "confirm": "1"}, follow_redirects=False)  # confirmed: saved
    assert ok.status_code == 303
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM odometer").fetchone()[0] == 3


def test_the_odometer_list_marks_what_does_not_fit_and_a_plain_reading_can_be_deleted(client):
    from tests.test_web import create_vehicle, slug

    from carassistant import db, summary

    vid = create_vehicle(client)
    with db.tx() as conn:
        conn.execute("DELETE FROM odometer WHERE vehicle_id = ?", (vid,))
        for day, km in (("2026-01-01", 52000), ("2026-02-01", 520000), ("2026-03-01", 52500)):
            conn.execute("INSERT INTO odometer(vehicle_id, date, odometer_km, source) VALUES (?, ?, ?, 'manual')", (vid, day, km))
        rows = summary.odometer_readings(conn, vid)
        assert [r["km"] for r in rows] == [52500, 520000, 52000] and [r["odd"] for r in rows] == [
            "",
            "higher",
            "",
        ]  # newest first, only the typo marked
        bad = next(r for r in rows if r["odd"])
    old = client.get(
        f"/v/{slug(vid)}/odometer", follow_redirects=False
    )  # no page of its own any more: the old address lands in the passport
    assert old.status_code == 303 and old.headers["location"].endswith(f"/v/{slug(vid)}/edit#odo-readings")
    page = client.get(f"/v/{slug(vid)}/edit").text
    assert 'id="odo-readings"' in page and 'class="odo-hrow odd"' in page and page.count("odo-hrow") == 3 and "notice warn" in page
    assert "odo-all odd" in client.get(f"/v/{slug(vid)}").text  # the dashboard points at it
    assert client.post(f"/v/{slug(vid)}/odometer/{bad['id']}/delete", follow_redirects=False).status_code == 303
    with db.tx() as conn:
        assert [r["odd"] for r in summary.odometer_readings(conn, vid)] == ["", ""]


def test_a_long_odometer_list_shows_the_newest_rows_and_every_odd_one_with_a_link_to_all(client):
    from datetime import date, timedelta

    from tests.test_web import create_vehicle, slug

    from carassistant import db, summary

    vid = create_vehicle(client)
    first = date(2024, 1, 1)
    with db.tx() as conn:
        conn.execute("DELETE FROM odometer WHERE vehicle_id = ?", (vid,))
        for i in range(300):
            km = 90_000 if i == 2 else 10_000 + i * 20  # an old typo far above its neighbours
            conn.execute(
                "INSERT INTO odometer(vehicle_id, date, odometer_km, source) VALUES (?, ?, ?, 'auto')",
                (vid, (first + timedelta(days=i)).isoformat(), km),
            )
        rows = summary.odometer_readings(conn, vid)
        shown = summary.trim_readings(rows)
    assert len(rows) == 300 and len(shown) == 121 and shown[-1]["km"] == 90_000 and shown[-1]["odd"]  # the newest 120 and the old typo
    page = client.get(f"/v/{slug(vid)}/edit").text
    assert page.count("odo-hrow") == 121 and "edit?odo=all#odo-readings" in page and 'class="eq-n">300<' in page
    assert (
        client.get(f"/v/{slug(vid)}/edit?odo=all").text.count("odo-hrow") == 300
        and "edit?odo=all#odo-readings" not in client.get(f"/v/{slug(vid)}/edit?odo=all").text
    )


def test_the_vehicle_passport_has_the_odometer_entry_when_no_plugin_reports_it(client):
    from tests.test_web import create_vehicle, slug

    from carassistant import db

    vid = create_vehicle(client)
    page = client.get(f"/v/{slug(vid)}/edit").text
    assert (
        'class="vd-odo"' in page and "data-odo-open" in page and f"/v/{slug(vid)}/odometer/quick" in page
    )  # typed by hand: the entry sits under the hero card
    with db.tx() as conn:
        conn.execute("UPDATE odometer SET source = 'plugin-x' WHERE vehicle_id = ?", (vid,))
    assert 'class="vd-odo"' not in client.get(f"/v/{slug(vid)}/edit").text  # the car reports it: nothing to type


def test_the_odometer_on_the_dashboard_is_a_flip_card_that_shows_the_last_reading_in_the_box(client):
    from tests.test_web import create_vehicle, slug

    from carassistant import db

    vid = create_vehicle(client)
    with db.tx() as conn:
        conn.execute("DELETE FROM odometer WHERE vehicle_id = ?", (vid,))
        conn.execute("INSERT INTO odometer(vehicle_id, date, odometer_km, source) VALUES (?, '2026-01-01', 12345, 'manual')", (vid,))
    page = client.get(f"/v/{slug(vid)}").text
    assert (
        'class="odo-face odo-front" data-odo-open role="button"' in page and 'class="odo-pencil"' not in page
    )  # the figure is the button, no icon
    assert (
        'class="odo-flip"' in page and 'class="odo-face odo-front"' in page and 'class="odo-face odo-back"' in page
    )  # figure in front, box behind
    assert "odo-flip open" not in page and 'class="odo-close"' not in page  # shown from the front; a tap outside turns it back
    assert 'placeholder="12345"' in page  # the last reading is the hint in the box - not text to delete
    assert (
        'name="odometer" inputmode="numeric" pattern="[0-9 .,]*" maxlength="9" autocomplete="off" value' not in page
    )  # and nothing is typed for you


def test_the_plate_is_fixed_while_a_plugin_reports_the_odometer_and_the_hidden_side_is_inert(client):
    from tests.test_web import create_vehicle, slug

    from carassistant import db

    vid = create_vehicle(client)
    with db.tx() as conn:
        conn.execute("DELETE FROM odometer WHERE vehicle_id = ?", (vid,))
        conn.execute("INSERT INTO odometer(vehicle_id, date, odometer_km, source) VALUES (?, '2026-01-01', 12345, 'manual')", (vid,))
    page = client.get(f"/v/{slug(vid)}").text
    assert (
        'class="odo-face odo-back" inert' in page and 'class="odo-flip"' in page and page.count("odo-flip odo-static") == 1
    )  # typed by hand: it turns over, the back is not reachable by Tab (the one plate that is static is the look of the odometer widget)
    with db.tx() as conn:
        conn.execute("INSERT INTO odometer(vehicle_id, date, odometer_km, source) VALUES (?, '2026-01-02', 12400, 'plugin')", (vid,))
    page = client.get(f"/v/{slug(vid)}").text
    assert (
        page.count("odo-flip odo-static") == 1  # only the plate look of the odometer widget
        and 'class="odo-flip"' not in page
        and "odo-face odo-back" not in page
        and "data-odo-open" not in page
        and 'class="odo-card"' not in page  # reported by the car: nothing to type, so nothing under the car ...
        and re.search(
            r'class="wd-slot [a-z]+" data-k="odometer"', page
        )  # ... the odometer widget shows it, and it is on by default for such a car
    )


# ------------------------------------------------------------------ the lower half of a cluster, the odometer on a receipt, real photos


def test_a_number_before_its_unit_is_the_odometer_and_a_trip_counter_or_a_speed_is_not():
    from carassistant import odometer_scan as o

    assert o.labelled("TRIP A 24.5 km\n86020 km") == [86020]  # the trip counter has a decimal
    assert o.labelled("86.020 km  53 450 mi") == [86020, 53450]  # thousands groups are joined
    assert o.labelled("86O20 km") == [86020]  # a letter O inside the number
    assert o.labelled("260 km/h  12 km") == []  # a speed is no odometer, 12 is no number of an odometer


def test_the_lower_half_of_a_photo_is_read_first_and_the_dial_numbers_above_do_not_win(monkeypatch):
    import io

    from PIL import Image

    from carassistant import odometer_scan as o
    from carassistant import receipt as rc

    img = Image.new("L", (600, 600), 30)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    png = buf.getvalue()
    monkeypatch.setattr(rc, "clean", lambda data: png)

    def fake(image, psm=6, digits=False):  # the lower half is 300 px high, the whole photo 600
        height = Image.open(io.BytesIO(image)).height
        if height <= 300:
            return "86020\n245" if digits else "TRIP A 24.5 km\n86020 km"
        return "20 40 60 80 100 120 140 160 180 173195 86020" if digits else "km/h 260 220"  # the dial numbers run together

    monkeypatch.setattr(rc, "read_text", fake)
    assert o.read(png, 85500) == {"value": 86020, "plausible": True}
    assert o.read(png, None) == {"value": 86020, "plausible": True}
    low = o.read(png, 86500)  # below the last reading: the number on the display is shown, flagged - not a made-up "plausible" one
    assert low == {"value": 86020, "plausible": False}


def test_a_receipt_that_prints_the_odometer_gives_it_and_one_without_does_not():
    text = ARAL + "\nKM-Stand: 86.020\n"
    r = receipt.parse(text, TODAY)
    assert r["odometer"] == 86020 and "odometer" in r["found"]
    assert receipt.parse(ARAL, TODAY)["odometer"] is None
    assert receipt.parse("Aral\nSuper E10\nMenge 40,00 l\nPreis 1,800 EUR/l\nKilometerstand 123456\n", TODAY)["odometer"] == 123456
    assert (
        receipt.parse("Aral\nSuper E10\nMenge 40,00 l\nPreis 1,800 EUR/l\nKunden-Nr 7777777\n", TODAY)["odometer"] is None
    )  # only a labelled number


def test_the_odometer_of_a_receipt_is_offered_only_when_it_fits_the_last_reading():
    from carassistant import receipt_web, units

    shown = receipt_web.shown(receipt.parse(ARAL + "\nKM-Stand: 86020\n", TODAY), units.of(None), "L", 85500)
    assert shown["odometer_km"] == "86020" and "odometer" in shown["found"]
    low = receipt_web.shown(receipt.parse(ARAL + "\nKM-Stand: 86020\n", TODAY), units.of(None), "L", 90000)  # below the last reading
    assert "odometer_km" not in low and "odometer" not in low["found"]
    assert receipt_web.shown(receipt.parse(ARAL + "\nKM-Stand: 86020\n", TODAY), units.of(None), "L", None)["odometer_km"] == "86020"


def test_the_start_list_opens_the_odometer_plate_and_the_fill_up_form(client):
    from tests.test_web import create_vehicle, slug

    vid = create_vehicle(client)
    from carassistant import db

    with db.tx() as conn:  # a car with nothing on it shows the start list
        for table in ("odometer", "fuel", "service", "trips", "mods", "parts", "tasks", "appointments"):
            conn.execute(f"DELETE FROM {table} WHERE vehicle_id = ?", (vid,))
    page = client.get(f"/v/{slug(vid)}").text
    assert "wd-start" in page
    assert f"/v/{slug(vid)}#odometer" in page and f"/v/{slug(vid)}/e/fuel#fuel-add" in page


def test_photos_are_read_by_the_real_text_recognition_when_it_is_installed():
    import pytest

    if not receipt.available():
        pytest.skip("Tesseract is not installed")
    import demo_photos

    from carassistant import odometer_scan as o

    cluster = demo_photos.cluster_photo(odometer=86_020, trip=24.5)
    assert o.read(cluster, 85_500) == {"value": 86020, "plausible": True}
    assert o.read(cluster, None)["value"] == 86020  # the dial numbers (0 ... 260) and the trip counter are not it
    r = receipt.scan(demo_photos.receipt_photo(odometer=86_020))
    assert (r["amount"], r["price_per_unit"], r["price_total"], r["notes"], r["odometer"]) == (42.7, 1.649, 70.41, "Diesel", 86020)
    assert r["checked"] and r["station"].lower().startswith("example")
