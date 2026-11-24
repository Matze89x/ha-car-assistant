from carassistant import fuelstats


def add(conn, vid, date, km, amount, total=None, full=1):
    conn.execute(
        "INSERT INTO fuel(vehicle_id, date, odometer_km, amount, price_total, full_tank) VALUES(?,?,?,?,?,?)",
        (vid, date, km, amount, total, full),
    )


def test_full_to_full_interval_includes_partial_fills(conn, vehicle):
    add(conn, vehicle, "2026-01-01", 1000, 40, 60)  # start point (amount not counted)
    add(conn, vehicle, "2026-01-10", 1300, 10, 15, full=0)  # partial
    add(conn, vehicle, "2026-01-20", 1500, 30, 45)  # full: 40 l over 500 km
    ivs = fuelstats.intervals(conn, vehicle)
    assert len(ivs) == 1
    assert ivs[0].km == 500 and ivs[0].amount == 40 and round(ivs[0].per_100, 2) == 8.0
    assert ivs[0].cost == 60 and round(ivs[0].cost_per_100, 2) == 12.0


def test_missing_amount_skips_interval_but_keeps_chain(conn, vehicle):
    add(conn, vehicle, "2026-01-01", 1000, 40)
    add(conn, vehicle, "2026-01-10", 1300, None, full=0)
    add(conn, vehicle, "2026-01-20", 1500, 30)  # interval invalid (partial amount unknown)
    add(conn, vehicle, "2026-02-01", 2000, 40)  # valid: 500 km, 40 l
    ivs = fuelstats.intervals(conn, vehicle)
    assert [(i.km, i.amount) for i in ivs] == [(500, 40.0)]


def test_cost_requires_all_prices_and_odometer_is_the_key(conn, vehicle):
    add(conn, vehicle, "2026-03-01", 2000, 40, 60)
    add(conn, vehicle, "2026-01-01", 1000, 40, 60)  # entered out of order, odometer decides
    add(conn, vehicle, "2026-02-01", 1500, 40, None)
    ivs = fuelstats.intervals(conn, vehicle)
    assert [i.km for i in ivs] == [500, 500]
    assert ivs[0].cost is None  # the 1500 km fill has no price
    assert ivs[1].cost == 60  # but the next interval only contains the priced 2000 km fill


def test_monthly_and_overall(conn, vehicle):
    add(conn, vehicle, "2026-01-01", 1000, 40, 60)
    add(conn, vehicle, "2026-01-25", 1500, 40, 60)
    add(conn, vehicle, "2026-02-10", 2100, 48, 72)
    months = fuelstats.monthly(conn, vehicle)
    assert [m.month for m in months] == ["2026-02", "2026-01"]
    assert months[1].per_100 == 8.0 and months[0].per_100 == 8.0
    assert months[1].spent == 120
    total = fuelstats.overall(conn, vehicle)
    assert total["intervals"] == 2 and round(total["avg_per_100"], 2) == 8.0
    assert fuelstats.month_spent(conn, vehicle, "2026-02") == 72


def _car(conn, vid, tank=50, fuel="petrol"):
    conn.execute("UPDATE vehicles SET tank_l = ?, fuel_type = ? WHERE id = ?", (tank, fuel, vid))
    return conn.execute("SELECT * FROM vehicles WHERE id = ?", (vid,)).fetchone()


def test_estimated_range_from_refuelling(conn, vehicle):
    add(conn, vehicle, "2026-01-01", 1000, 40)
    add(conn, vehicle, "2026-01-20", 1500, 40)  # 8 l/100 km
    conn.execute("INSERT INTO odometer(vehicle_id, date, odometer_km) VALUES(?, '2026-01-25', 1700)", (vehicle,))
    est = fuelstats.estimate_range(conn, _car(conn, vehicle))
    assert est["since"] == 200 and round(est["per100"], 1) == 8.0
    assert est["km"] == 425  # 50 l / 8 * 100 - 200


def test_estimated_range_needs_data(conn, vehicle):
    car = _car(conn, vehicle)
    assert fuelstats.estimate_range(conn, car) is None  # nothing yet
    add(conn, vehicle, "2026-01-01", 1000, 40)
    assert fuelstats.estimate_range(conn, car) is None  # only one full tank, no interval
    add(conn, vehicle, "2026-01-20", 1500, 40)
    assert fuelstats.estimate_range(conn, _car(conn, vehicle, tank=None)) is None  # no tank size
    assert fuelstats.estimate_range(conn, _car(conn, vehicle, fuel="electric")) is None


def test_periods_group_and_limit(conn, vehicle):
    from datetime import date

    add(conn, vehicle, "2026-09-01", 1000, 40, 60)
    add(conn, vehicle, "2026-10-05", 1500, 40, 60)
    add(conn, vehicle, "2026-11-10", 2000, 40, 60)
    add(conn, vehicle, "2026-11-18", 2400, 32, 48)
    today = date(2026, 11, 20)
    months = fuelstats.periods(conn, vehicle, "month", 2, today)
    assert [m.month for m in months] == ["2026-11", "2026-10"]  # September is outside the two months
    assert months[0].km == 900 and round(months[0].spent) == 108
    days = fuelstats.periods(conn, vehicle, "day", 30, today)
    assert [m.month for m in days] == ["2026-11-18", "2026-11-10"]  # 30 days back reaches 2026-10-22
    weeks = fuelstats.periods(conn, vehicle, "week", 4, today)
    assert [m.month for m in weeks] == ["2026-W47", "2026-W46"]


def test_costs_and_kilometres_per_period(conn, vehicle):
    from datetime import date

    add(conn, vehicle, "2026-10-05", 1000, 40, 60)
    add(conn, vehicle, "2026-11-10", 1500, 40, 70)
    conn.execute("INSERT INTO service(vehicle_id, date, title, cost) VALUES(?, '2026-11-12', 'Oil', 200)", (vehicle,))
    today = date(2026, 11, 20)
    rows = fuelstats.costs(conn, vehicle, "month", 3, today)
    assert [r["key"] for r in rows] == ["2026-09", "2026-10", "2026-11"]
    assert rows[2]["fuel"] == 70 and rows[2]["service"] == 200 and rows[0]["fuel"] == 0
    km = dict(fuelstats.kilometres(conn, vehicle, "month", 3, today))
    assert km["2026-11"] == 500 and km["2026-09"] is None


def test_widget_sparkline_and_mini_bars():
    from carassistant import charts

    assert charts.spark_svg([1.0]) == "" and charts.spark_svg([]) == ""
    svg = charts.spark_svg([6.1, 5.8, 6.4, 5.9])
    assert svg.startswith("<svg") and 'class="sp-line"' in svg and 'class="sp-dot"' in svg and "<circle" not in svg
    assert charts.mini_bars_svg([("Mon", 0.0), ("Tue", 0.0)]) == ""
    bars = charts.mini_bars_svg([("Mon", 10.0), ("Tue", 0.0), ("Wed", 5.0)])
    assert bars.count("<rect") == 3 and bars.count('class="mb top"') == 1 and 'class="mb none"' in bars
    assert "viewBox" not in bars and 'rx="3"' in bars  # laid out in percent: never stretched


def test_expense_list_has_every_priced_entry_newest_first_and_filters_by_kind(conn, vehicle):
    from datetime import date

    add(conn, vehicle, "2026-11-02", 1000, 40, 60)
    add(conn, vehicle, "2026-11-10", 1400, 30, None)  # no price: not an expense
    conn.execute(
        "INSERT INTO service(vehicle_id, date, title, workshop, cost) VALUES(?,?,?,?,?)", (vehicle, "2026-11-15", "Oil", "Garage", 120)
    )
    conn.execute("INSERT INTO mods(vehicle_id, date, title, cost) VALUES(?,?,?,?)", (vehicle, "2026-10-20", "Wheels", 900))
    conn.execute(
        "INSERT INTO parts(vehicle_id, date, name, cost) VALUES(?,?,?,?)", (vehicle, "2025-01-01", "Old part", 5)
    )  # outside the window
    today = date(2026, 11, 20)
    rows = fuelstats.expenses(conn, vehicle, "month", 3, today=today)
    assert [(r["kind"], r["cost"]) for r in rows] == [("service", 120.0), ("fuel", 60.0), ("mods", 900.0)]
    assert [r["kind"] for r in fuelstats.expenses(conn, vehicle, "month", 3, "mods", today=today)] == ["mods"]
    assert len(fuelstats.expenses(conn, vehicle, "month", 3, "nonsense", today=today)) == 3


def test_a_bi_fuel_car_has_a_consumption_per_fuel_and_the_first_fuel_is_unchanged(client):
    from tests.test_web import create_vehicle, slug

    from carassistant import db, fuelstats

    vid = create_vehicle(client)
    client.post(f"/v/{slug(vid)}/edit", data={"name": "Gas car", "fuel_type": "petrol", "fuel2_type": "lpg"})
    with db.tx() as conn:
        assert conn.execute("SELECT fuel2_type FROM vehicles WHERE id = ?", (vid,)).fetchone()[0] == "lpg"
        rows = [  # petrol: 0 -> 500 km uses 40 L; LPG: 100 -> 400 km uses 30 L
            ("2026-01-01", 1000, 40.0, "main", 1),
            ("2026-01-10", 1100, 20.0, "second", 1),
            ("2026-01-20", 1400, 30.0, "second", 1),
            ("2026-02-01", 1500, 40.0, "main", 1),
        ]
        for day, km, amount, kind, full in rows:
            conn.execute(
                "INSERT INTO fuel(vehicle_id, date, odometer_km, amount, price_per_unit, price_total, full_tank, fuel_kind) VALUES (?, ?, ?, ?, 1.0, ?, ?, ?)",
                (vid, day, km, amount, amount, full, kind),
            )
        main = fuelstats.overall(conn, vid)
        second = fuelstats.overall(conn, vid, "second")
    assert main["intervals"] == 1 and round(main["avg_per_100"], 1) == 8.0  # 40 L over 500 km - the gas fill-ups are not in it
    assert second["intervals"] == 1 and round(second["avg_per_100"], 1) == 10.0 and second["fills"] == 2  # 30 L over 300 km
    page = client.get(f"/v/{slug(vid)}/e/fuel").text
    assert 'name="fuel_kind"' in page and "LPG" in page and "fuel-second" in page
    # a car with one fuel has none of this
    plain = create_vehicle(client)
    assert 'name="fuel_kind"' not in client.get(f"/v/{slug(plain)}/e/fuel").text


def test_a_bi_fuel_car_tells_the_fuels_apart_in_the_export_and_in_home_assistant(client):
    from tests.test_web import create_vehicle

    from carassistant import db, mqtt_ha

    vid = create_vehicle(client)
    client.post(f"/v/{vid}/edit", data={"name": "Gas car", "fuel_type": "petrol", "fuel2_type": "lpg"})
    with db.tx() as conn:
        for day, km, amount, kind in (
            ("2026-01-01", 1000, 40.0, "main"),
            ("2026-01-10", 1100, 20.0, "second"),
            ("2026-01-20", 1400, 30.0, "second"),
            ("2026-02-01", 1500, 40.0, "main"),
            ("2026-02-05", 1600, 25.0, "second"),  # the newest fill-up is gas: it is not "the last fill-up" of the first fuel
        ):
            conn.execute(
                "INSERT INTO fuel(vehicle_id, date, odometer_km, amount, price_per_unit, price_total, full_tank, fuel_kind) VALUES (?, ?, ?, ?, 1.0, ?, 1, ?)",
                (vid, day, km, amount, amount, kind),
            )
        row = conn.execute("SELECT * FROM vehicles WHERE id = ?", (vid,)).fetchone()
        values = mqtt_ha.compute_values(conn, row)
        wanted = {s.key for s in mqtt_ha.wanted_sensors(row, values)}
    assert values["avg_consumption"] == "8.0" and values["avg_consumption_second"] == "11.0"  # 40 L / 500 km; gas 55 L / 500 km
    assert values["last_fill_amount"] == "40.00" and values["last_fill_date"] == "2026-02-01"  # the first fuel's own last fill-up
    assert "avg_consumption_second" in wanted  # the "more statistics" group (cost per 100 km ...) is off by default, like the first fuel's
    assert (
        values["cost_per_100km_second"] == "11.00" and values["fuel_spent_total_second"] == "75.00"
    )  # 1.0 per litre: 11 L per 100 km; 20 + 30 + 25 L
    lines = client.get(f"/v/{vid}/fuel-export.csv").content.decode("utf-8-sig").splitlines()
    head = lines[0].split(";")
    assert len(head) == 9 and head[3] == "Fuel"  # the added column, after the amount
    assert [r.split(";")[3] for r in lines[1:]] == ["Petrol", "LPG", "LPG", "Petrol", "LPG"]
    # a car with one fuel keeps the old columns
    plain = create_vehicle(client)
    assert len(client.get(f"/v/{plain}/fuel-export.csv").content.decode("utf-8-sig").splitlines()[0].split(";")) == 8
