"""Reading a fuel receipt: the parser on the text Tesseract finds (no photo needed)."""

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
