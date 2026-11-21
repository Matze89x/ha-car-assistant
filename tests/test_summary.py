from datetime import date

from carassistant import summary


def test_add_months_clamps_day():
    assert summary.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert summary.add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert summary.add_months(date(2026, 11, 15), 3) == date(2027, 2, 15)


def test_current_odometer_is_max_over_all_sources(conn, vehicle):
    assert summary.current_odometer(conn, vehicle) is None
    summary.add_odometer(conn, vehicle, 1000)
    conn.execute("INSERT INTO fuel(vehicle_id, date, odometer_km) VALUES(?, '2026-01-01', 1500)", (vehicle,))
    conn.execute("INSERT INTO service(vehicle_id, date, odometer_km, title) VALUES(?, '2026-01-01', 1200, 'x')", (vehicle,))
    assert summary.current_odometer(conn, vehicle) == 1500


def test_appointment_status(conn, vehicle):
    conn.execute("INSERT INTO appointments(vehicle_id, title, due_date) VALUES(?, 'HU', '2026-06-30')", (vehicle,))
    row = conn.execute("SELECT * FROM appointments").fetchone()
    assert summary.appointment_due(row, date(2026, 1, 1)).status == "ok"
    assert summary.appointment_due(row, date(2026, 6, 10)).status == "soon"
    info = summary.appointment_due(row, date(2026, 7, 5))
    assert info.status == "overdue" and info.days_left == -5


def test_task_detects_last_done_from_service_book(conn, vehicle):
    summary.add_odometer(conn, vehicle, 30000)
    conn.execute(
        "INSERT INTO tasks(vehicle_id, title, interval_km, interval_months, keywords) VALUES(?, 'Oil', 15000, 12, 'oil,öl')", (vehicle,)
    )
    conn.execute("INSERT INTO service(vehicle_id, date, odometer_km, title) VALUES(?, '2026-01-10', 20000, 'Ölwechsel')", (vehicle,))
    task = conn.execute("SELECT * FROM tasks").fetchone()
    info = summary.task_due(conn, vehicle, task, 30000, date(2026, 6, 1))
    assert info.due_km == 35000 and info.km_left == 5000 and info.due_date == date(2027, 1, 10)
    assert info.status == "ok"
    info = summary.task_due(conn, vehicle, task, 34500, date(2026, 6, 1))
    assert info.status == "soon"
    info = summary.task_due(conn, vehicle, task, 36000, date(2026, 6, 1))
    assert info.status == "overdue"


def test_task_without_history_is_unknown_and_not_flagged(conn, vehicle):
    conn.executemany(
        "INSERT INTO tasks(vehicle_id, title, interval_km, interval_months, keywords) VALUES(?,?,?,?,?)",
        [
            (vehicle, "Engine oil & filter", 15000, 12, "oil"),
            (vehicle, "Brake fluid", None, 24, "brake fluid"),
            (vehicle, "Coolant", None, 60, "coolant"),
            (vehicle, "Air filter", 30000, 24, "air filter"),
            (vehicle, "Battery check", None, 24, "battery"),
        ],
    )
    assert summary.attention_items(conn, vehicle) == []


def test_attention_sorted_overdue_first(conn, vehicle):
    conn.execute(
        "INSERT INTO appointments(vehicle_id, title, due_date) VALUES(?, 'soon', ?)",
        (vehicle, date.today().replace(year=date.today().year + 5).isoformat()),
    )
    conn.execute("INSERT INTO appointments(vehicle_id, title, due_date) VALUES(?, 'late', '2000-01-01')", (vehicle,))
    items = summary.attention_items(conn, vehicle)
    assert [i.title for i in items] == ["late"]
    assert items[0].severity == "overdue"
