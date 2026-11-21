import pytest

from carassistant import trips

GPX = b"""<?xml version="1.0"?>
<gpx version="1.1" creator="t" xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>
<trkpt lat="52.5200" lon="13.4050"><time>2026-05-01T07:00:00Z</time></trkpt>
<trkpt lat="52.5300" lon="13.4050"><time>2026-05-01T07:10:00Z</time></trkpt>
<trkpt lat="52.5400" lon="13.4050"><time>2026-05-01T07:20:00Z</time></trkpt>
</trkseg></trk></gpx>"""


def test_haversine_known_distance():
    assert abs(trips.haversine_km(52.52, 13.405, 52.53, 13.405) - 1.112) < 0.01


def test_parse_and_import_gpx(conn, vehicle):
    trip_id = trips.import_gpx(conn, vehicle, GPX, "business")
    trip = conn.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
    assert trip["source"] == "gpx" and trip["category"] == "business"
    assert abs(trip["distance_km"] - 2.22) < 0.05
    assert trip["date"] == "2026-05-01" and trip["start_time"] == "07:00"
    assert len(trips.trip_points(conn, trip_id)) == 3
    out = trips.gpx_bytes(trip, trips.trip_points(conn, trip_id))
    assert b"<trkpt" in out and trips.parse_gpx(out)[0][0] == pytest.approx(52.52)


@pytest.mark.parametrize(
    "payload",
    [
        b"not xml",
        b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><gpx><trk/></gpx>',
        b'<gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg><trkpt lat="1" lon="1"/></trkseg></trk></gpx>',
        b'<gpx><trk><trkseg><trkpt lat="99" lon="1"/><trkpt lat="98" lon="1"/></trkseg></trk></gpx>',
    ],
)
def test_bad_gpx_rejected(payload):
    with pytest.raises(trips.GpxError):
        trips.parse_gpx(payload)


def test_exports(conn, vehicle):
    conn.execute(
        "INSERT INTO trips(vehicle_id, date, start_place, end_place, start_km, end_km, distance_km, category, purpose) "
        "VALUES(?, '2026-03-03', 'Home', 'Office; Müller', 100, 142, 42, 'business', 'Client, A')",
        (vehicle,),
    )
    vrow = conn.execute("SELECT * FROM vehicles").fetchone()
    rows = trips.trips_in_range(conn, vehicle, "2026-01-01", "2026-12-31")
    labels = {
        k: k
        for k in (
            "date",
            "start",
            "end",
            "from",
            "to",
            "start_km",
            "end_km",
            "distance",
            "category",
            "purpose",
            "title",
            "period",
            "total",
            "disclaimer",
            "cat.business",
            "cat.private",
            "cat.commute",
        )
    }
    csv_data = trips.csv_bytes(rows, labels).decode("utf-8-sig")
    assert "42,0" in csv_data and "Office; Müller" in csv_data
    pdf = trips.pdf_bytes(vrow, rows, "2026-01-01", "2026-12-31", labels)
    assert pdf.startswith(b"%PDF") and len(pdf) > 800
    assert trips.totals(rows) == {"business": 42.0, "total": 42.0}


def test_parse_range_defaults_and_swaps():
    s, e = trips.parse_range("2026-05-01", "2026-01-01")
    assert (s, e) == ("2026-01-01", "2026-05-01")
    s, e = trips.parse_range("garbage", None)
    assert s.endswith("-01-01") and e.endswith("-12-31")


def test_the_trip_card_has_a_legend_a_square_map_and_driving_style_in_one_column_on_wide_screens():
    from pathlib import Path

    app = Path(__file__).resolve().parents[1] / "carassistant" / "app" / "carassistant"
    page = (app / "templates" / "trips_page.html").read_text()
    assert (
        'class="tp-legend"' in page and "data-legend=" in page and "data-hard=" in page and "data-note=" in page
    )  # the colours are explained, the texts are there
    css = (app / "static" / "pc-core.css").read_text()
    assert "aspect-ratio: 1 / 1" in css.split(".tp-map {")[1].split("}")[0]  # as wide as high
    assert "min-width: 700px) { .tp-tiles { grid-template-columns: minmax(0, 1fr); } }" in css  # one column from a tablet on
    js = (app / "static" / "trips.js").read_text()
    assert "pos-map" in js and "data-map" in js and "fitBounds" in js  # light / dark like the location map, the route in the middle
