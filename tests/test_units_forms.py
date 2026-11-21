"""Units: entered and shown in the units of Settings -> Region, stored in km / litres / price per litre."""

from carassistant import db, units


def _car(client, name="Unit Car", fuel="petrol"):
    client.post("/vehicles", data={"name": name, "fuel_type": fuel})
    with db.tx() as conn:
        return conn.execute("SELECT id, slug FROM vehicles WHERE name = ?", (name,)).fetchone()


def _us(client):
    client.post("/settings/units", data={"units": "us", "currency": "USD"})


def test_units_convert_back_and_forth():
    us = units.Units("us", "USD")
    assert round(us.from_d(100), 3) == 160.934 and round(us.d(160.934), 1) == 100.0
    assert round(us.from_v(10), 3) == 37.854 and round(us.v(37.854), 2) == 10.0
    assert round(us.from_price_vol(4.0), 4) == round(4.0 * units.L_TO_US_GAL, 4) and round(us.price_vol(us.from_price_vol(4.0)), 4) == 4.0
    assert us.from_v(10, "kWh") == 10 and us.from_price_vol(0.3, "kWh") == 0.3  # only litres change
    assert us.dist_str(1609.344).startswith("1,000 mi")


def test_a_fill_up_typed_in_miles_and_gallons_is_stored_in_km_and_litres(client):
    car = _car(client)
    _us(client)
    client.post(
        f"/v/{car['slug']}/e/fuel",
        data={
            "date": "2026-01-01",
            "odometer_km": "10000",
            "amount": "10",
            "price_per_unit": "4.00",
            "price_total": "40",
            "full_tank": "1",
        },
    )
    with db.tx() as conn:
        row = conn.execute("SELECT * FROM fuel WHERE vehicle_id = ?", (car["id"],)).fetchone()
    assert (
        row["odometer_km"] == 16093
        and round(row["amount"], 3) == 37.854
        and round(row["price_per_unit"], 4) == round(4.0 * units.L_TO_US_GAL, 4)
    )
    page = client.get(f"/v/{car['slug']}/e/fuel").text
    assert "10,000 mi" in page and "Amount (gal)" in page and "$/gal" in page  # shown in miles and gallons
    assert 'value="10000"' in page and 'value="10.0"' in page  # editing shows what was typed
    with db.tx() as conn:
        rid = conn.execute("SELECT id FROM fuel WHERE vehicle_id = ?", (car["id"],)).fetchone()["id"]
    client.post(
        f"/v/{car['slug']}/e/fuel/{rid}",
        data={
            "date": "2026-01-01",
            "odometer_km": "10000",
            "amount": "10.0",
            "price_per_unit": "4.0",
            "price_total": "40",
            "full_tank": "1",
        },
    )
    with db.tx() as conn:
        again = conn.execute("SELECT * FROM fuel WHERE id = ?", (rid,)).fetchone()
    assert again["odometer_km"] == row["odometer_km"] and abs(again["amount"] - row["amount"]) < 0.01


def test_metric_stays_exactly_as_typed(client):
    car = _car(client, "Metric Car")
    client.post(
        f"/v/{car['slug']}/e/fuel",
        data={"date": "2026-01-01", "odometer_km": "10000", "amount": "40.5", "price_per_unit": "1.789", "full_tank": "1"},
    )
    with db.tx() as conn:
        row = conn.execute("SELECT * FROM fuel WHERE vehicle_id = ?", (car["id"],)).fetchone()
    assert row["odometer_km"] == 10000 and row["amount"] == 40.5 and row["price_per_unit"] == 1.789


def test_an_electric_car_keeps_kwh_but_distances_follow_the_choice(client):
    car = _car(client, "Volt Car", "electric")
    _us(client)
    client.post(
        f"/v/{car['slug']}/e/fuel",
        data={"date": "2026-01-01", "odometer_km": "1000", "amount": "30", "price_per_unit": "0.30", "full_tank": "1"},
    )
    with db.tx() as conn:
        row = conn.execute("SELECT * FROM fuel WHERE vehicle_id = ?", (car["id"],)).fetchone()
    assert row["amount"] == 30 and row["price_per_unit"] == 0.30 and row["odometer_km"] == 1609  # kWh and money stay, miles become km


def test_report_vehicle_form_and_due_texts_use_the_chosen_units(client):
    car = _car(client)
    for day, odo, amount in (("2026-01-01", 1000, 40), ("2026-02-01", 1500, 30), ("2026-03-01", 2000, 30)):
        client.post(f"/v/{car['slug']}/e/fuel", data={"date": day, "odometer_km": str(odo), "amount": str(amount), "full_tank": "1"})
    metric = client.get(f"/v/{car['slug']}/report").text
    assert "L/100 km" in metric
    _us(client)
    us = client.get(f"/v/{car['slug']}/report").text
    assert "mpg" in us and "L/100 km" not in us and "mi" in us
    assert "(mi)" in client.get("/vehicles/new").text or "Odometer (mi)" in client.get("/vehicles/new").text  # the form asks in miles
    client.post(f"/v/{car['slug']}/e/tasks", data={"title": "Oil", "interval_km": "10000", "last_km": "1000"})
    page = client.get(f"/v/{car['slug']}/e/tasks").text
    assert "Interval (mi)" in page


def test_what_the_car_reports_is_shown_in_the_chosen_units(client):
    from carassistant import connectors

    car = _car(client, "Live Car")
    with db.tx() as conn:
        token = connectors.create_token(conn, "Plugin", car["id"])
    h = {"Authorization": f"Bearer {token}"}
    body = {
        "speed_kmh": 100,
        "outside_temp_c": 20,
        "consumption_l_100km": 7.0,
        "tyre_pressure_bar": {"fl": 2.4, "fr": 2.4, "rl": 2.4, "rr": 2.4},
    }
    assert client.post(f"/api/v1/vehicles/{car['id']}/data", json=body, headers=h).status_code == 200
    metric = client.get(f"/v/{car['slug']}").text
    assert "100 km/h" in metric and "20 °C" in metric and "bar" in metric
    _us(client)
    us = client.get(f"/v/{car['slug']}").text
    assert "62 mph" in us and "68 °F" in us and "psi" in us and "mpg" in us and "100 km/h" not in us
