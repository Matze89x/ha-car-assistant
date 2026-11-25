from carassistant import connectors, db, energy


def _make(client, name, fuel, **extra):
    client.post("/vehicles", data={"name": name, "fuel_type": fuel, **extra})
    with db.tx() as conn:
        return conn.execute("SELECT id FROM vehicles WHERE name = ?", (name,)).fetchone()["id"]


def test_mode_is_per_vehicle_and_automatic_by_default():
    assert energy.mode({"fuel_type": "electric", "energy_mode": None}) == "charge"
    assert energy.mode({"fuel_type": "diesel", "energy_mode": None}) == "fuel"
    assert energy.mode({"fuel_type": "hybrid", "energy_mode": "charge"}) == "charge"
    assert energy.mode({"fuel_type": "electric", "energy_mode": "fuel"}) == "fuel"


def test_state_uses_percent_and_range_whichever_is_worse():
    car = {"warn_pct": None, "crit_pct": None, "warn_range_km": 120, "crit_range_km": 50}
    assert energy.state(car, 60, 400) == "ok"
    assert energy.state(car, 24, 400) == "soon"  # default 25 %
    assert energy.state(car, 9, 400) == "overdue"  # default 10 %
    assert energy.state(car, 60, 100) == "soon"  # range below the yellow level
    assert energy.state(car, 60, 40) == "overdue"
    assert energy.state({"warn_pct": 40, "crit_pct": 20}, 35, None) == "soon"


def test_each_vehicle_has_its_own_wording_and_levels(client):
    diesel = _make(client, "Diesel", "diesel")
    ev = _make(client, "Stromer", "electric")
    hybrid = _make(client, "Hybrid", "hybrid", energy_mode="charge", warn_pct="40", crit_pct="15")
    assert "<span>Charging</span>" not in client.get(f"/v/{diesel}/e/fuel").text
    assert "<span>Fuel</span>" in client.get(f"/v/{diesel}/e/fuel").text
    assert "<span>Charging</span>" in client.get(f"/v/{ev}/e/fuel").text and "Energy (kWh)" in client.get(f"/v/{ev}/e/fuel").text
    assert "<span>Charging</span>" in client.get(f"/v/{hybrid}/e/fuel").text  # switched by hand
    page = client.get(f"/v/{hybrid}/edit?mode=form").text
    assert 'name="energy_mode" value="charge" checked' in page and 'name="warn_pct"' in page and 'value="40"' in page


def test_the_range_bar_turns_yellow_then_red(client):
    vid = _make(client, "Low", "petrol", warn_pct="30", crit_pct="12")
    with db.tx() as conn:
        token = connectors.create_token(conn, "Plugin", vid)
    h = {"Authorization": f"Bearer {token}"}

    def state(level):
        client.post(f"/api/v1/vehicles/{vid}/data", json={"fuel_level_pct": level, "range_km": level * 5}, headers=h)
        page = client.get(f"/v/{vid}").text
        return next(s for s in ("st-ok", "st-soon", "st-overdue") if f"range-block {s}" in page)

    assert state(60) == "st-ok" and state(25) == "st-soon" and state(10) == "st-overdue"


def test_level_inputs_are_validated(client):
    r = client.post("/vehicles", data={"name": "Bad", "fuel_type": "petrol", "warn_pct": "abc"})
    assert r.status_code == 400
    assert client.post("/vehicles", data={"name": "Bad2", "fuel_type": "petrol", "energy_mode": "steam"}).status_code == 400


def test_charging_view_uses_the_plug_icon(client):
    ev = _make(client, "Plug", "electric")
    diesel = _make(client, "Pump", "diesel")
    assert "M16,7V3H14V7H10V3H8V7H8C7,7" in client.get(f"/v/{ev}/e/fuel").text  # plug path
    assert "M16,7V3H14V7H10V3H8V7H8C7,7" not in client.get(f"/v/{diesel}/e/fuel").text


def test_logo_is_an_inline_icon_and_leads_home_or_to_the_list(client):
    import re

    one = _make(client, "Solo", "diesel")
    page = client.get(f"/v/{one}").text
    assert 'class="brand-mark"' in page and "/static/logo-car.svg" in page  # the car as a vector graphic
    assert re.search(
        r'<a class="sb-brand" href="/"', page
    )  # the logo always goes to "/" (the start page: dashboard of one car, else the choice)
    _make(client, "Zwei", "petrol")
    assert re.search(r'<a class="sb-brand" href="/"', client.get(f"/v/{one}").text)
    assert re.search(r'<a class="sb-brand" href="/"', client.get("/about").text)


def test_fuel_page_holds_the_station_search_and_the_history(client):
    client.post("/vehicles", data={"name": "Diesel One", "fuel_type": "diesel"})
    client.post("/vehicles", data={"name": "Volt One", "fuel_type": "electric"})
    page = client.get("/v/diesel-one/e/fuel").text
    assert 'id="stations"' in page and page.index('id="stations"') < page.index('id="fuel"')  # the stations come first, the history below
    assert 'id="fuel-add"' in page and "static/stations.js" in page
    ev = client.get("/v/volt-one/e/fuel").text  # an electric car has no FUEL stations - it searches charging points in the same place
    assert 'id="stations"' in ev and "Charging points nearby" in ev and "Fuel stations nearby" not in ev
    assert (
        client.get("/v/diesel-one/stations?go=1", follow_redirects=False).headers["location"].endswith("/e/fuel?go=1#stations")
    )  # the old page
