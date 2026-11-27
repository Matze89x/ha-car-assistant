import pytest

from carassistant import entities
from carassistant.entities import FormError, parse_form


def test_service_requires_title_and_valid_date():
    with pytest.raises(FormError):
        parse_form(entities.SERVICE, {"date": "2026-01-01"})
    with pytest.raises(FormError):
        parse_form(entities.SERVICE, {"date": "31.02.2026", "title": "x"})
    values = parse_form(entities.SERVICE, {"date": "2026-02-01", "title": "Oil", "odometer_km": "12 000".replace(" ", ""), "cost": "89,90"})
    assert values["odometer_km"] == 12000 and values["cost"] == 89.9


def test_month_only_appointment_uses_last_day_of_month():
    values = parse_form(entities.APPOINTMENTS, {"title": "TÜV", "due_date": "2027-02"})
    assert values["due_date"] == "2027-02-28" and values["month_only"] == 1
    values = parse_form(entities.APPOINTMENTS, {"title": "TÜV", "due_date": "2028-02"})
    assert values["due_date"] == "2028-02-29"
    values = parse_form(entities.APPOINTMENTS, {"title": "x", "due_date": "2027-05-04"})
    assert values["month_only"] == 0
    with pytest.raises(FormError):
        parse_form(entities.APPOINTMENTS, {"title": "x", "due_date": "2027-13"})


def test_fuel_derives_missing_price():
    v = parse_form(entities.FUEL, {"date": "2026-01-01", "amount": "40", "price_per_unit": "1,50"})
    assert v["price_total"] == 60.0
    v = parse_form(entities.FUEL, {"date": "2026-01-01", "amount": "40", "price_total": "60"})
    assert v["price_per_unit"] == 1.5


def test_negative_and_choice_validation():
    with pytest.raises(FormError):
        parse_form(entities.FUEL, {"date": "2026-01-01", "amount": "-4"})
    with pytest.raises(FormError):
        parse_form(entities.TIRES, {"name": "x", "season": "monsoon"})
    assert parse_form(entities.TIRES, {"name": "x"})["season"] == "summer"


def test_trip_distance_and_order():
    v = parse_form(entities.TRIPS, {"date": "2026-01-01", "start_km": "100", "end_km": "131"})
    assert v["distance_km"] == 31.0
    with pytest.raises(FormError):
        parse_form(entities.TRIPS, {"date": "2026-01-01", "start_km": "200", "end_km": "100"})


def test_bool_checkbox():
    assert parse_form(entities.FUEL, {"date": "2026-01-01", "full_tank": "1"})["full_tank"] == 1
    assert parse_form(entities.FUEL, {"date": "2026-01-01"})["full_tank"] == 0


def test_the_label_of_a_money_field_names_the_currency_like_the_other_units(client):
    """The total price of a fill-up, the cost of a service, a part and a fixed cost say what they are counted in: (€) - or the currency of the server."""
    from carassistant import db

    vid = client.post("/vehicles", data={"name": "Money Car", "fuel_type": "diesel"}, follow_redirects=False)
    with db.tx() as conn:
        vid = conn.execute("SELECT id FROM vehicles ORDER BY id DESC LIMIT 1").fetchone()[0]
    page = client.get(f"/v/{vid}/e/fuel").text
    assert "Total price (€)" in page and "Amount (L)" in page and "Price per unit (€/L)" in page
    assert "Cost (€)" in client.get(f"/v/{vid}/e/service").text
    assert "Cost (€)" in client.get(f"/v/{vid}/e/parts").text
    client.post("/settings/units", data={"units": "us", "currency": "USD"})
    assert "Total price ($)" in client.get(f"/v/{vid}/e/fuel").text
