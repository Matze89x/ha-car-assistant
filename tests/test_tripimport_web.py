"""The import of trips from a CSV file, page by page (tripimport_web.py): the file, the columns, the check, the one that says it worked."""

from tests.test_fuelimport_web import FUELIO, _car, _form, _mapping, _token

from carassistant import db

TRIPS = (
    "Datum;Startzeit;Endzeit;Von;Nach;Start-km;End-km;Strecke;Kategorie;Zweck\n"
    "2026-11-20;08:05;08:40;Berlin;Potsdam;12000;12035;35,2;Geschäftlich;Kunde\n"
    "2026-11-21;17:10;;Potsdam;Berlin;12035;12071;;Privat;\n"
    "2026-11-22;07:30;08:00;Berlin;Büro;12071;12090;;Arbeitsweg;\n"
)


def _upload(client, vid: int, data: bytes = TRIPS.encode(), name: str = "trips.csv"):
    return client.post(f"/v/{vid}/trips-csv", files={"file": (name, data, "text/csv")})


def _count(vid: int) -> int:
    with db.tx() as conn:
        return conn.execute("SELECT COUNT(*) FROM trips WHERE vehicle_id = ?", (vid,)).fetchone()[0]


def test_the_trips_page_offers_the_import_and_the_first_page_asks_for_a_file(client):
    vid = _car(client)
    page = client.get(f"/v/{vid}/trips-csv")
    assert page.status_code == 200
    assert 'class="guide-bar"' in page.text and 'type="file"' in page.text and "Import trips" in page.text
    assert client.get("/v/99999/trips-csv").status_code == 404
    with db.tx() as conn:
        slug = conn.execute("SELECT slug FROM vehicles WHERE id = ?", (vid,)).fetchone()[0]
    assert f'href="/v/{slug}/trips-csv"' in client.get(f"/v/{vid}/e/trips").text  # the way in: Export / import of the trips page


def test_a_file_goes_through_all_the_pages_and_the_trips_are_written(client):
    vid = _car(client)
    sent = _upload(client, vid)
    assert sent.status_code == 303
    token = _token(sent)
    columns = client.get(f"/v/{vid}/trips-csv/{token}")
    assert columns.status_code == 200 and "3 rows in the file" in columns.text
    assert _mapping(columns.text) == {
        "date": "Datum", "start_time": "Startzeit", "end_time": "Endzeit", "start_km": "Start-km", "end_km": "End-km", "distance_km": "Strecke",
        "start_place": "Von", "end_place": "Nach", "category": "Kategorie", "purpose": "Zweck",
    }  # fmt: skip
    posted = client.post(f"/v/{vid}/trips-csv/{token}", data=_form(columns.text))
    assert posted.status_code == 303 and posted.headers["location"].endswith(f"/trips-csv/{token}/check")
    check = client.get(f"/v/{vid}/trips-csv/{token}/check")
    assert check.status_code == 200 and "Ready to import: 3 trips" in check.text and "Potsdam" in check.text
    assert _count(vid) == 0  # nothing is written before the last yes
    done = client.post(f"/v/{vid}/trips-csv/{token}/run")
    assert done.status_code == 303 and done.headers["location"].endswith(f"/trips-csv/{token}/done")
    page = client.get(f"/v/{vid}/trips-csv/{token}/done")
    assert page.status_code == 200 and "3 trips were added" in page.text
    with db.tx() as conn:
        rows = conn.execute(
            "SELECT date, start_time, distance_km, category, source FROM trips WHERE vehicle_id = ? ORDER BY date", (vid,)
        ).fetchall()
    assert [tuple(r) for r in rows] == [
        ("2026-11-20", "08:05", 35.2, "business", "csv"),
        ("2026-11-21", "17:10", 36.0, "private", "csv"),
        ("2026-11-22", "07:30", 19.0, "commute", "csv"),
    ]
    assert not list((client_data_dir() / "import-cache").glob(f"{token}.csv"))  # the file is not kept
    assert client.post(f"/v/{vid}/trips-csv/{token}/run").status_code == 303 and _count(vid) == 3  # a second press writes nothing more


def client_data_dir():
    from carassistant import config

    return config.data_dir()


def test_the_same_file_a_second_time_adds_nothing(client):
    vid = _car(client)
    for expected in (3, 3):
        token = _token(_upload(client, vid))
        columns = client.get(f"/v/{vid}/trips-csv/{token}")
        client.post(f"/v/{vid}/trips-csv/{token}", data=_form(columns.text))
        check = client.get(f"/v/{vid}/trips-csv/{token}/check")
        if expected == 3 and _count(vid) == 0:
            assert "Ready to import: 3 trips" in check.text
            client.post(f"/v/{vid}/trips-csv/{token}/run")
        else:
            assert "Ready to import: 0 trips" in check.text and "skipped: 3" in check.text
    assert _count(vid) == 3


def test_a_missing_distance_column_is_said_on_the_page_of_the_columns(client):
    vid = _car(client)
    token = _token(_upload(client, vid))
    columns = client.get(f"/v/{vid}/trips-csv/{token}")
    form = _form(columns.text, col_distance_km="", col_start_km="", col_end_km="")
    bad = client.post(f"/v/{vid}/trips-csv/{token}", data=form)
    assert bad.status_code == 400 and "needs a column" in bad.text
    twice = client.post(f"/v/{vid}/trips-csv/{token}", data=_form(columns.text, col_purpose="0"))  # the date column once more
    assert twice.status_code == 400 and "only be used for one point" in twice.text
    assert _count(vid) == 0


def test_a_column_number_that_is_no_number_is_taken_for_no_column(client):
    vid = _car(client)
    token = _token(_upload(client, vid))
    columns = client.get(f"/v/{vid}/trips-csv/{token}")
    for odd in ("²", "①", "x", "-1", "99"):  # "²" is a digit for str.isdigit() but not for int(): it must not end in an error page
        bad = client.post(f"/v/{vid}/trips-csv/{token}", data=_form(columns.text, col_date=odd))
        assert bad.status_code == 400 and "needs a column" in bad.text, odd
    assert _count(vid) == 0


def test_a_file_that_is_no_table_is_refused_on_the_first_page(client):
    vid = _car(client)
    bad = _upload(client, vid, b"just one line", "x.csv")
    assert bad.status_code == 400 and "No table was found" in bad.text
    empty = client.post(f"/v/{vid}/trips-csv", files={})
    assert empty.status_code == 400


def test_a_file_of_the_fill_ups_does_not_open_here_and_a_file_of_the_trips_does_not_open_there(client):
    vid = _car(client)
    fuel_token = _token(client.post(f"/v/{vid}/fuel/import", files={"file": ("f.csv", FUELIO.encode(), "text/csv")}))
    assert client.get(f"/v/{vid}/trips-csv/{fuel_token}").status_code == 303  # not its pages: back to the start
    trips_token = _token(_upload(client, vid))
    assert client.get(f"/v/{vid}/fuel/import/{trips_token}").status_code == 303


def test_the_file_of_one_car_is_not_for_another_and_a_made_up_name_is_nothing(client):
    one, two = _car(client), _car(client)
    token = _token(_upload(client, one))
    assert client.get(f"/v/{two}/trips-csv/{token}").status_code == 404
    assert client.get(f"/v/{one}/trips-csv/{'a' * 22}").status_code == 303  # unknown: back to the start with a note
    assert client.get(f"/v/{one}/trips-csv/not-a-token").status_code == 404
