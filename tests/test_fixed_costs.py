"""Fixed costs (vehicle tax, insurance, ...): when a payment falls due, and what the cost page makes of it."""

from datetime import date, timedelta

from carassistant import db, fuelstats


def add(conn, vid, title, cost, every, start, end=None, kind="tax"):
    return conn.execute(
        "INSERT INTO fixed_costs(vehicle_id, title, cost_kind, cost, every, start_date, end_date) VALUES(?,?,?,?,?,?,?)",
        (vid, title, kind, cost, every, start, end),
    ).lastrowid


def days(payments):
    return [p["date"] for p in payments]


def test_a_monthly_cost_falls_due_on_the_same_day_and_a_short_month_takes_its_last_day(conn, vehicle):
    add(conn, vehicle, "Parking", 50, "month", "2026-01-31")
    got = fuelstats.fixed_payments(conn, vehicle, date(2026, 1, 1), date(2026, 5, 31))
    assert days(got) == ["2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30", "2026-05-31"]


def test_quarterly_half_yearly_and_yearly_payments(conn, vehicle):
    add(conn, vehicle, "Insurance", 120, "quarter", "2025-11-15", kind="insurance")
    add(conn, vehicle, "Club", 30, "halfyear", "2025-12-01", kind="club")
    add(conn, vehicle, "Tax", 200, "year", "2024-03-10")
    got = fuelstats.fixed_payments(conn, vehicle, date(2026, 1, 1), date(2026, 12, 31))
    assert [(p["title"], p["date"]) for p in got] == [
        ("Insurance", "2026-02-15"),
        ("Tax", "2026-03-10"),
        ("Insurance", "2026-05-15"),
        ("Club", "2026-06-01"),
        ("Insurance", "2026-08-15"),
        ("Insurance", "2026-11-15"),
        ("Club", "2026-12-01"),
    ]  # oldest first


def test_a_payment_counts_only_inside_its_own_time(conn, vehicle):
    add(conn, vehicle, "Insurance", 100, "year", "2024-06-01", end="2025-06-01", kind="insurance")  # ended: the 2026 payment is not due
    add(conn, vehicle, "Sticker", 40, "once", "2026-02-01", end="2020-01-01", kind="toll")  # a single payment has no end
    add(conn, vehicle, "Later", 10, "month", "2026-09-01")  # starts in the future
    got = fuelstats.fixed_payments(conn, vehicle, date(2024, 1, 1), date(2026, 6, 30))
    assert [(p["title"], p["date"]) for p in got] == [("Insurance", "2024-06-01"), ("Insurance", "2025-06-01"), ("Sticker", "2026-02-01")]
    assert fuelstats.fixed_payments(conn, vehicle, date(2026, 7, 1), date(2026, 6, 1)) == []  # an upside-down window


def test_the_cost_page_counts_fixed_costs_per_period_and_never_the_future(conn, vehicle):
    add(conn, vehicle, "Parking", 50, "month", "2026-01-15")
    add(conn, vehicle, "Tax", 240, "year", "2026-03-20")
    today = date(2026, 5, 10)  # the May payment of the parking (15th) is not due yet
    rows = {r["key"]: r for r in fuelstats.costs(conn, vehicle, "month", 6, today)}
    assert [rows[k]["fixed"] for k in ("2026-01", "2026-02", "2026-03", "2026-04", "2026-05")] == [50, 50, 290, 50, 0]
    listed = fuelstats.expenses(conn, vehicle, "month", 6, "fixed", today)
    assert [e["date"] for e in listed] == ["2026-04-15", "2026-03-20", "2026-03-15", "2026-02-15", "2026-01-15"]  # newest first
    assert sum(e["cost"] for e in listed) == 440
    assert (
        sum(e["cost"] for e in fuelstats.expenses(conn, vehicle, "month", 6, "fuel", today)) == 0
    )  # another category: no fixed cost in it
    assert sum(e["cost"] for e in fuelstats.expenses(conn, vehicle, "month", 6, "", today)) == 440  # all of them


def test_the_form_checks_the_amount_and_the_dates_and_the_page_shows_the_payments(client):
    from tests.test_web import create_vehicle, slug

    vid = create_vehicle(client, "Fixed Car")
    url = f"/v/{slug(vid)}/e/fixed"
    first = (date.today() - timedelta(days=40)).isoformat()
    good = {"title": "Vehicle tax", "cost_kind": "tax", "cost": "199,50", "every": "year", "start_date": first}
    assert client.post(url, data={**good, "cost": "0"}).status_code == 400  # nothing to pay
    assert client.post(url, data={**good, "end_date": "2001-01-01"}).status_code == 400  # ends before it starts
    assert client.post(url, data={**good, "title": ""}).status_code == 400
    assert client.post(url, data=good).status_code in (200, 303)
    page = client.get(url)
    assert page.status_code == 200 and "Vehicle tax" in page.text and "199.5" in page.text
    report = client.get(f"/v/{slug(vid)}/report")
    assert "Fixed costs" in report.text and "199" in report.text
    only = client.get(f"/v/{slug(vid)}/report?c=fixed")
    assert "Vehicle tax" in only.text and "Yearly" in only.text
    assert client.get(f"/v/{slug(vid)}/report?c=nonsense").status_code == 200  # an unknown category lists everything


def test_a_single_payment_ignores_an_end_date(client):
    from tests.test_web import create_vehicle, slug

    vid = create_vehicle(client, "Once Car")
    data = {
        "title": "Toll sticker",
        "cost_kind": "toll",
        "cost": "11",
        "every": "once",
        "start_date": "2026-02-01",
        "end_date": "2026-03-01",
    }
    assert client.post(f"/v/{slug(vid)}/e/fixed", data=data).status_code in (200, 303)
    with db.tx() as conn:
        assert conn.execute("SELECT end_date FROM fixed_costs WHERE vehicle_id = ?", (vid,)).fetchone()[0] is None


def test_the_cost_page_has_three_tabs_with_symbols_and_the_fixed_costs_are_no_page_of_the_list(client):
    from tests.test_web import create_vehicle, slug

    from carassistant import db, modules

    vid = create_vehicle(client, "Tab Car")
    base = f"/v/{slug(vid)}"
    for url, current in ((f"{base}/report", "report"), (f"{base}/e/fixed", "fixed")):
        page = client.get(url).text
        tabs = page.split('<nav class="seg-tabs')[1].split("</nav>")[0]
        assert f'href="{base}/report"' in tabs and f'href="{base}/e/fixed"' in tabs and "Overview" in tabs and "Fixed costs" in tabs
        assert tabs.count("<svg") == 3 and f'href="{base}/invoices"' in tabs  # a symbol on each tab; the invoices are the third
        assert tabs.count('aria-current="page"') == 1 and (f'href="{base}/e/fixed" class="on"' in tabs) == (current == "fixed")
    assert f"{base}/e/fixed" not in client.get(f"{base}/more").text  # one entry for the costs, not two
    with db.tx() as conn:
        modules.set_vehicle_enabled(conn, vid, "report", False)
    assert client.get(f"{base}/e/fixed").status_code == 404  # they follow the switch of the cost page
