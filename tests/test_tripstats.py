"""Trip analysis: totals, kinds, length classes, weekday x time of day, and the driving style from recorded drives."""

from datetime import date

from carassistant import tripstats


def _trip(conn, vid, day, start, end, km, category="private", source="manual"):
    return conn.execute(
        "INSERT INTO trips(vehicle_id, date, start_time, end_time, category, source, distance_km) VALUES(?,?,?,?,?,?,?)",
        (vid, day, start, end, category, source, km),
    ).lastrowid


def test_totals_kinds_lengths_and_the_heat_map(conn, vehicle):
    today = date(2026, 11, 20)  # a Friday
    _trip(conn, vehicle, "2026-11-20", "07:30", "08:00", 20, "commute")  # Friday morning, 40 km/h
    _trip(conn, vehicle, "2026-11-19", "17:45", "18:15", 20, "commute")  # Thursday afternoon
    _trip(conn, vehicle, "2026-11-15", "10:00", "12:00", 150, "private")  # Sunday morning, the longest
    _trip(conn, vehicle, "2026-11-10", None, None, 3, "business")  # no start time
    _trip(conn, vehicle, "2026-05-01", "09:00", "09:30", 30, "private")  # outside the 30 days
    a = tripstats.analyse(conn, vehicle, "30", lambda km: km, today)
    assert a["n"] == 4 and round(a["km"]) == 193 and round(a["avg_km"], 1) == 48.2
    assert a["longest"]["km"] == 150 and a["minutes"] == 30 + 30 + 120
    assert [c["key"] for c in a["cats"]] == ["private", "commute", "business"] and a["cats"][0]["n"] == 1
    assert a["buckets"] == [1, 0, 2, 0, 0, 1, 0]  # 3 km; two of 20 km (10-25); 150 km (100-200)
    assert a["heat"][4][1] == 1 and a["heat"][3][2] == 1 and a["heat"][6][1] == 1  # Fri morning, Thu afternoon, Sun morning
    assert a["untimed"] == 1 and a["heat_max"] == 1
    assert tripstats.analyse(conn, vehicle, "all", lambda km: km, today)["n"] == 5  # everything
    assert (
        tripstats.analyse(conn, vehicle, "nonsense", lambda km: km, today)["n"] == 4
    )  # an unknown choice falls back to the default (90 days)


def test_the_length_classes_follow_the_units_shown(conn, vehicle):
    _trip(conn, vehicle, "2026-11-20", "08:00", "08:20", 12)  # 12 km = 7.5 miles
    metric = tripstats.analyse(conn, vehicle, "all", lambda km: km)
    miles = tripstats.analyse(conn, vehicle, "all", lambda km: km * 0.621371)
    assert metric["buckets"].index(1) == 2 and miles["buckets"].index(1) == 1  # 10-25 km, but 5-10 mi
    assert tripstats.length_labels() == ["<5", "5-10", "10-25", "25-50", "50-100", "100-200", ">200"]


def test_the_driving_style_comes_from_recorded_drives_with_times(conn, vehicle):
    tid = _trip(conn, vehicle, "2026-11-20", "07:00", "07:10", None, source="gps")
    # a straight drive north at 54 km/h that ends with a hard stop; 15 m per second
    from datetime import UTC, datetime, timedelta

    t0 = datetime(2026, 11, 20, 7, 0, tzinfo=UTC)
    lat = 50.0
    speeds = [0.00013] * 40 + [0.00013, 0.00004, 0.0] + [0.0] * 5  # degrees of latitude per second (about 14.5 m/s, then braking)
    for seq, step in enumerate([0.0, *speeds]):
        lat += step
        conn.execute(
            "INSERT INTO trip_points(trip_id, seq, lat, lon, ts) VALUES(?,?,?,?,?)",
            (tid, seq, lat, 8.0, (t0 + timedelta(seconds=seq)).isoformat()),
        )
    style = tripstats.driving_style(conn, [tid])
    assert style and style["trips"] == 1 and style["km"] > 0.4 and style["top_kmh"] > 40
    assert style["idle_pct"] is not None and 0 <= style["idle_pct"] <= 100
    assert tripstats.driving_style(conn, []) is None
    manual = _trip(conn, vehicle, "2026-11-19", "07:00", "07:10", 5, source="manual")
    assert tripstats.driving_style(conn, [manual]) is None  # no points: nothing to say


def test_the_trips_page_shows_the_analysis_and_the_period_choice(client):
    from tests.test_web import create_vehicle, slug

    from carassistant import db

    vid = create_vehicle(client, "Analysis Car")
    with db.tx() as conn:
        _trip(conn, vid, date.today().isoformat(), "07:30", "08:00", 20, "commute")
    page = client.get(f"/v/{slug(vid)}/e/trips").text
    assert 'id="analysis"' in page and ("Trip analysis" in page or "Fahrten-Auswertung" in page)
    assert "?ap=30#analysis" in page and "?ap=all#analysis" in page and 'class="ta-heat"' in page and "ta-bars" in page
    assert 'aria-current="page"' in client.get(f"/v/{slug(vid)}/e/trips?ap=365").text
    assert "ap=365" in client.get(f"/v/{slug(vid)}/e/trips?ap=365").text.split('class="seg-tabs ta-tabs"')[1].split("</nav>")[0]
    assert client.get(f"/v/{slug(vid)}/e/trips?ap=nonsense").status_code == 200
