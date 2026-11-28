"""The import of trips from a CSV file (tripimport.py): which column is what, the values, the checks of a trip, what is skipped - and that the export of this
app, in either language, comes back as it went out."""

import io
from datetime import date, timedelta

from tests.test_web import create_vehicle

from carassistant import db, entities, fuelimport, i18n, tripimport, trips

DE = (
    "Datum;Startzeit;Endzeit;Von;Nach;Start-km;End-km;Strecke;Kategorie;Zweck\n"
    "2026-11-20;08:05;08:40;Berlin;Potsdam;12000;12035;35,2;Geschäftlich;Kunde\n"
    "2026-11-21;17:10;;Potsdam;Berlin;12035;12071;;Privat;\n"
    "2026-11-22;07:30;08:00;Berlin;Büro;12071;12090;;Arbeitsweg;\n"
)
OPTIONS = {"order": "auto", "dist": "km", "skip": True}


def table(text: str) -> fuelimport.Table:
    return fuelimport.read(text.encode("utf-8-sig"))


def run(text: str, options=None, have=None, mapping=None):
    t = table(text)
    return tripimport.convert(t, mapping or tripimport.guess(t.columns, t.rows), options or OPTIONS, have)


def test_the_columns_of_the_export_of_this_app_are_found_in_both_languages():
    german = table(DE)
    assert tripimport.guess(german.columns, german.rows) == {
        "date": 0, "start_time": 1, "end_time": 2, "start_place": 3, "end_place": 4,
        "start_km": 5, "end_km": 6, "distance_km": 7, "category": 8, "purpose": 9,
    }  # fmt: skip
    english = table(
        "Date;Start time;End time;From;To;Start odometer;End odometer;Distance;Category;Purpose\n2026-11-20;08:05;08:40;Berlin;Potsdam;12000;12035;35,2;Business;Client\n"
    )
    found = tripimport.guess(english.columns, english.rows)
    assert found["date"] == 0 and found["start_time"] == 1 and found["end_km"] == 6 and found["distance_km"] == 7 and found["category"] == 8
    assert tripimport.missing(found) == ""


def test_a_column_called_start_is_a_time_or_a_place_by_what_it_holds():
    times = table("Date,Start,End,Distance\n2026-11-20,08:05,08:40,12.5\n")
    assert tripimport.guess(times.columns, times.rows)["start_time"] == 1 and tripimport.guess(times.columns, times.rows)["end_time"] == 2
    places = table("Date,Start,End,Distance\n2026-11-20,Berlin,Potsdam,12.5\n")
    found = tripimport.guess(places.columns, places.rows)
    assert found["start_place"] == 1 and found["end_place"] == 2 and found["start_time"] is None and found["end_time"] is None


def test_a_file_needs_a_date_and_a_distance_or_both_odometer_readings():
    assert tripimport.missing({"date": 0, "distance_km": 1}) == ""
    assert tripimport.missing({"date": 0, "start_km": 1, "end_km": 2}) == ""
    assert tripimport.missing({"date": 0, "start_km": 1}) == "tripimport.err_required"
    assert tripimport.missing({"distance_km": 1}) == "tripimport.err_required"


def test_the_values_of_a_row_become_a_trip():
    done = run(DE)
    assert (done.read, len(done.rows), done.problem_count, done.duplicates) == (3, 3, 0, 0)
    first, second, third = done.rows
    assert first == {
        "date": "2026-11-20", "start_time": "08:05", "end_time": "08:40", "start_km": 12000, "end_km": 12035, "distance_km": 35.2,
        "start_place": "Berlin", "end_place": "Potsdam", "category": "business", "purpose": "Kunde",
    }  # fmt: skip
    assert (
        second["distance_km"] == 36.0 and second["end_time"] is None and second["category"] == "private"
    )  # no distance: the odometer readings make it
    assert third["category"] == "commute" and third["distance_km"] == 19.0


def test_miles_are_converted_and_the_time_may_stand_in_the_date_column():
    done = run("Date,Miles,From\n2026-11-20 08:05,10,Home\n", {"order": "auto", "dist": "mi", "skip": True})
    assert done.rows[0]["distance_km"] == 16.09 and done.rows[0]["start_time"] == "08:05" and done.rows[0]["date"] == "2026-11-20"


def test_times_of_day_in_the_forms_people_write_them():
    assert [tripimport.clock(t) for t in ("8:05", "08.05", "08:05:33", "8:05 pm", "12:10 am", "2026-11-20 17:45", "25:00", "later")] == [
        "08:05", "08:05", "08:05", "20:05", "00:10", "17:45", None, None,
    ]  # fmt: skip


def test_the_words_for_the_category_in_any_language():
    assert [tripimport.category_of(w) for w in ("Private", "privat", "Business", "Geschäftlich", "dienstlich", "Commute", "Arbeitsweg", "Geschäftlicher Arbeitsweg", "", "x")] == [
        "private", "private", "business", "business", "business", "commute", "commute", "commute", "private", "private",
    ]  # fmt: skip
    assert [tripimport.category_of(w) for w in ("P", "B", "W")] == ["private", "business", "commute"]


def test_what_is_wrong_with_a_row_is_said_and_never_written():
    today = date.today()
    future = (today + timedelta(days=3)).isoformat()
    text = (
        "Date;Start time;Start odometer;End odometer;Distance\n"
        f"{future};08:00;1;2;5\n"  # a trip that has not happened yet
        "not a date;08:00;1;2;5\n"
        "2026-11-20;99:99;100;110;\n"  # a time that is none: left empty, the odometer makes the distance
        "2026-11-20;08:00;200;190;\n"  # the end is below the start: the odometer is left empty, and nothing is left to make a distance
        "2026-11-20;08:00;300;350;40\n"  # the distance of the file wins over the difference
        "2026-11-20;08:00;;;99999\n"  # more than one trip can be
        "2026-11-20;08:00;;;\n"  # no distance at all
    )
    done = run(text)
    keys = [p[1] for p in done.problems]
    assert keys == [
        "tripimport.row_date", "tripimport.row_date", "tripimport.row_time", "tripimport.row_order", "tripimport.row_distance",
        "tripimport.row_far", "tripimport.row_distance",
    ]  # fmt: skip
    assert [(r["start_km"], r["distance_km"], r["start_time"]) for r in done.rows] == [(100, 10.0, None), (300, 40.0, "08:00")]


def test_a_trip_that_is_in_the_log_already_is_skipped(client):
    vid = create_vehicle(client)
    with db.tx() as conn:
        conn.execute(
            "INSERT INTO trips(vehicle_id, date, start_time, start_km, end_km, distance_km, category, source) VALUES(?, '2026-11-20', '08:05', 12000, 12035, 35.0, 'private', 'manual')",
            (vid,),
        )
        have = tripimport.known(conn, vid)
    done = run(DE, have=have)
    assert done.duplicates == 1 and len(done.rows) == 2  # the same odometer readings on the same day
    assert len(run(DE, {**OPTIONS, "skip": False}, have=have).rows) == 3  # (unless the person wants them twice)


def test_the_export_of_this_app_can_be_imported_again_in_either_language(client):
    """What goes out comes back: the same trips, none doubled - for the labels and the categories of both languages."""
    vid = create_vehicle(client)
    for lang in ("en", "de"):
        t = i18n.translator(lang)
        labels = {
            "date": t("f.date"), "start": t("f.start_time"), "end": t("f.end_time"), "from": t("f.start_place"), "to": t("f.end_place"),
            "start_km": t("f.start_km"), "end_km": t("f.end_km"), "distance": t("f.distance"), "category": t("f.category"), "purpose": t("f.purpose"),
        }  # fmt: skip
        for cat in entities.TRIP_CATEGORIES:
            labels["cat." + cat] = t("category." + cat)
        with db.tx() as conn:
            conn.execute("DELETE FROM trips WHERE vehicle_id = ?", (vid,))
            conn.executemany(
                "INSERT INTO trips(vehicle_id, date, start_time, end_time, start_km, end_km, start_place, end_place, category, purpose, source, distance_km) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,'manual',?)",
                [
                    (
                        vid,
                        "2026-11-20",
                        "08:05",
                        "08:40",
                        12000,
                        12035,
                        "Berlin",
                        "Potsdam",
                        "business",
                        "Client; with a semicolon? no",
                        35.0,
                    ),
                    (vid, "2026-11-21", None, None, None, None, "Home", "Work", "commute", None, 12.5),
                ],
            )
            out = trips.csv_bytes(trips.trips_in_range(conn, vid, "2026-01-01", "2026-12-31"), labels)
            before = [
                tuple(r)
                for r in conn.execute(
                    "SELECT date, start_time, end_time, start_km, end_km, start_place, end_place, category, purpose, distance_km FROM trips ORDER BY date"
                )
            ]
            conn.execute("DELETE FROM trips WHERE vehicle_id = ?", (vid,))
        t_in = fuelimport.read(out)
        mapping = tripimport.guess(t_in.columns, t_in.rows)
        assert tripimport.missing(mapping) == "", lang
        done = tripimport.convert(t_in, mapping, OPTIONS)
        assert done.problem_count == 0 and len(done.rows) == 2, (lang, done.problems)
        with db.tx() as conn:
            assert tripimport.insert(conn, vid, done.rows) == 2
            after = [
                tuple(r)
                for r in conn.execute(
                    "SELECT date, start_time, end_time, start_km, end_km, start_place, end_place, category, purpose, distance_km FROM trips ORDER BY date"
                )
            ]
            sources = {r[0] for r in conn.execute("SELECT source FROM trips WHERE vehicle_id = ?", (vid,))}
        assert after == before, lang
        assert sources == {"csv"}
    assert io.BytesIO(out).read(3) == b"\xef\xbb\xbf"  # (the export carries the mark Excel wants, and the reader takes it off)


def test_a_text_for_a_spreadsheet_is_never_a_formula():
    from carassistant import csvtext

    assert [csvtext.safe(v) for v in (None, "", "Berlin", "=1+1", "+1", "-2", "@SUM(A1)", "\tx", "\rx", "a=b")] == [
        "", "", "Berlin", "'=1+1", "'+1", "'-2", "'@SUM(A1)", "'\tx", "'\rx", "a=b",
    ]  # fmt: skip


def test_the_export_of_trips_never_writes_a_formula(client):
    """The places and the purpose of a trip can come from a file of another app (the import above) or from a plugin: whatever they say, a spreadsheet must
    not run it when the exported file is opened."""
    import csv

    vid = create_vehicle(client)
    labels = {k: k for k in ("date", "start", "end", "from", "to", "start_km", "end_km", "distance", "category", "purpose")}
    labels.update({"cat." + c: c for c in entities.TRIP_CATEGORIES})
    with db.tx() as conn:
        conn.executemany(
            "INSERT INTO trips(vehicle_id, date, start_place, end_place, category, purpose, source, distance_km) VALUES(?,?,?,?, 'private', ?, 'csv', 5)",
            [
                (vid, "2026-11-20", '=HYPERLINK("http://example.com","x")', "+1+1", "@SUM(A1)"),
                (vid, "2026-11-21", "-2+3", "Berlin", "Client; visit"),
            ],
        )
        text = trips.csv_bytes(trips.trips_in_range(conn, vid, "2026-01-01", "2026-12-31"), labels).decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text), delimiter=";"))
    assert len(rows) == 3 and all(len(r) == 10 for r in rows)
    for row in rows[1:]:
        assert not any(cell[:1] in ("=", "+", "-", "@") for cell in row if cell), row
    assert rows[1][3] == '\'=HYPERLINK("http://example.com","x")' and rows[1][4] == "'+1+1" and rows[1][9] == "'@SUM(A1)"
    assert (
        rows[2][3] == "'-2+3" and rows[2][4] == "Berlin" and rows[2][9] == "Client; visit"
    )  # (a text that is no formula is left as it is)
