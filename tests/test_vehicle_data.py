"""Vehicle data page: hero card, three groups, badges, new technical fields."""

from datetime import date

from tests.test_web import create_vehicle, slug

from carassistant import vin


def test_model_year_from_vin():
    today = date(2026, 11, 13)
    # position 10 is the model-year code, repeating every 30 years; the latest cycle not later than next year wins
    assert vin.model_year("ABCDEFGH1K1234567", today) == 2019  # K = 1989 / 2019
    assert vin.model_year("ABCDEFGH1T1234567", today) == 2026  # T = 1996 / 2026
    assert vin.model_year("ABCDEFGH1V1234567", today) == 2027  # V = 1997 / 2027 (next year is still allowed)
    assert vin.model_year("ABCDEFGH1W1234567", today) == 1998  # W = 1998 / 2028 (too late)
    assert vin.model_year("ABCDEFGH1A1234567", today) == 2010  # A = 1980 / 2010 / 2040
    assert vin.model_year("ABCDEFGH191234567", today) == 2009  # 9 = 2009 / 2039
    assert vin.model_year("short", today) is None and vin.model_year(None, today) is None
    assert vin.model_year("ABCDEFGH1U1234567", today) is None  # U is not a model-year code
    assert vin.model_year("ABCDEFGH1K123456I", today) is None  # I, O and Q never appear in a VIN


def test_page_has_hero_four_groups_and_footnote(client):
    vid = create_vehicle(client)
    html = client.get(f"/v/{slug(vid)}/edit").text
    assert "vd-hero" in html and "plate-chip" in html and "B-XY 1" in html
    assert (
        html.count('class="vd-group-h"') >= 3
        and html.count('class="vd-g g') == 4
        and html.count('class="vd-col"') == 2
        and "Energy" in html
    )
    assert "Papers &amp; look" in html or "Papers & look" in html
    assert 'class="bk-note"' in html


def test_year_from_vin_badge_only_when_no_year_entered(client):
    vid = create_vehicle(client)
    client.post(f"/v/{slug(vid)}/edit", data={"name": "X", "fuel_type": "petrol", "vin": "ABCDEFGH1K1234567"})
    html = client.get(f"/v/{slug(vid)}/edit").text
    assert "2019" in html and "from VIN" in html
    client.post(f"/v/{slug(vid)}/edit", data={"name": "X", "fuel_type": "petrol", "vin": "ABCDEFGH1K1234567", "year": "2020"})
    html = client.get(f"/v/{slug(vid)}/edit").text
    assert "2020" in html and "from VIN" not in html  # a year entered by hand always wins


def test_new_fields_are_saved_shown_and_validated(client):
    vid = create_vehicle(client)
    data = {
        "name": "Daily",
        "fuel_type": "diesel",
        "engine": "2.0 diesel",
        "power_kw": "110",
        "displacement_ccm": "1968",
        "drivetrain": "awd",
        "transmission": "dct",
        "body_type": "wagon",
        "engine_code": "ABCD",
        "gearbox_code": "EFG",
        "battery": "AGM 70 Ah (2024)",
        "paint_code": "X1X1",
        "hsn": "0603",
        "tsn": "ABC",
        "key_numbers": "1: 123\n2: 456",
        "build_date": "2020-05-03",
        "model_type": "T1",
    }
    r = client.post(f"/v/{slug(vid)}/edit", data=data)
    assert r.status_code == 303
    html = client.get(f"/v/{slug(vid)}/edit").text
    for needle in (
        "2.0 diesel",
        "110 kW (150 hp)",
        "All-wheel drive",
        "Dual-clutch",
        "Wagon",
        "ABCD",
        "EFG",
        "0603 / ABC",
        "03.05.2020",
    ):
        assert needle in html or needle.replace("03.05.2020", "2020-05-03") in html, needle
    form = client.get(f"/v/{slug(vid)}/edit?mode=form").text
    assert 'name="power_kw"' in form and 'value="110"' in form and "selected" in form
    bad = client.post(f"/v/{slug(vid)}/edit", data={**data, "drivetrain": "hamster"})
    assert bad.status_code == 400
    assert client.post(f"/v/{slug(vid)}/edit", data={**data, "power_kw": "abc"}).status_code == 400
    assert client.post(f"/v/{slug(vid)}/edit", data={**data, "build_date": "yesterday"}).status_code == 400


def test_typed_values_are_read_leniently():
    """A hand-typed value must not end in a 400: units, comma, spaces and the German date are understood."""
    from carassistant.web import parse_build_date, parse_displacement, parse_power_kw, parse_vehicle

    assert [parse_power_kw(v, "x") for v in ("110", "110 kW", "110kw", "150 PS", "150 hp")] == [110, 110, 110, 110, 110]
    assert [parse_displacement(v, "x") for v in ("1968", "1968 cm³", "1968 ccm", "1.968", "2.0", "1,6 l", "2 liter")] == [
        1968,
        1968,
        1968,
        1968,
        2000,
        1600,
        2000,
    ]
    assert parse_build_date("03.05.2020", "x") == parse_build_date("2020-05-03", "x") == "2020-05-03"
    assert parse_vehicle({"name": "T", "vin": "test 1234-abcd"})["vin"] == "TEST1234ABCD"


def test_nonsense_is_still_rejected_with_a_message():
    import pytest

    from carassistant.entities import FormError
    from carassistant.web import parse_build_date, parse_displacement, parse_power_kw, parse_vehicle

    for call, value in (
        (parse_power_kw, "abc"),
        (parse_power_kw, "0"),
        (parse_power_kw, "99999"),
        (parse_displacement, "x"),
        (parse_displacement, "30000"),
        (parse_build_date, "yesterday"),
    ):
        with pytest.raises(FormError):
            call(value, "x")
    with pytest.raises(FormError):
        parse_vehicle({"name": "T", "vin": "TEST$1234"})


def test_failed_creation_leaves_no_vehicle_behind(client):
    """A rejected form shows the message and must not create a vehicle (also not when the error comes after the insert)."""
    r = client.post("/vehicles", data={"name": "Broken", "fuel_type": "petrol", "odometer": "50 000"})
    assert r.status_code == 400 and "Broken" in r.text
    assert "50 000" in r.text  # what was typed stays in the form
    from carassistant import db

    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0] == 0
