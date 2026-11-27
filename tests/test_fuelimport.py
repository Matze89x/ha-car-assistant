"""Fill-ups from a CSV file of another app (fuelimport.py): Fuelio's file with several tables, a plain table, other delimiters and number formats,
the guess of the columns, the units and the rows that are in the log already."""

import pytest

from carassistant import fuelimport as fi

FUELIO_HEAD = (
    '"Data","Odo (km)","Fuel (litres)","Full","Price (optional)","l/100km (optional)","latitude (optional)","longitude (optional)","City (optional)",'
    '"Notes (optional)","Missed","TankNumber","FuelType","VolumePrice","StationID (optional)","ExcludeDistance","UniqueId","TankCalc","Weather"'
)
FUELIO_ROWS = (
    '"2024-09-16 15:39","36633.0","37.17","1","59.43","5.86","0.0","0.0","","Driver A","0","1","110","1.599","0","0.0","41","0.0",""\n'
    '"2024-09-05 21:00","35999.0","38.0","1","58.0","6.51","0.0","0.0","","Driver B","0","1","110","1.526","0","0.0","40","0.0",""\n'
    '"2024-08-19 18:25","35415.0","36.25","1","55.43","","0.0","0.0","","Driver A","0","1","110","1.529","0","0.0","39","0.0",""\n'
)
FUELIO = (
    '"## Vehicle"\n"Name","Description","DistUnit","FuelUnit","ConsumptionUnit","ImportCSVDateFormat","VIN","Insurance","Plate"\n'
    '"Example Car","","km","Litre","l/100km","yyyy-MM-dd HH:mm","","",""\n'
    f'"## Log"\n{FUELIO_HEAD}\n{FUELIO_ROWS}'
    '"## CostCategories"\n"CostTypeID","Name","priority","color"\n"1","Service","1","-1"\n'
)


def _table(text: str = FUELIO) -> fi.Table:
    return fi.read(text.encode("utf-8"))


def test_a_fuelio_file_is_read_from_its_log_table():
    table = _table()
    assert table.section == "Log" and table.delimiter == ","
    assert table.columns[:5] == ["Data", "Odo (km)", "Fuel (litres)", "Full", "Price (optional)"]
    assert len(table.rows) == 3 and table.rows[0][0] == "2024-09-16 15:39"
    assert table.meta == {"dist": "km", "vol": "l", "order": "ymd"}  # from the vehicle table


def test_the_columns_of_a_fuelio_file_are_guessed_by_their_names():
    table = _table()
    got = {t: (table.columns[i] if i is not None else None) for t, i in fi.guess(table.columns).items()}
    assert got == {
        "date": "Data",
        "amount": "Fuel (litres)",
        "odometer_km": "Odo (km)",
        "price_total": "Price (optional)",
        "price_per_unit": "VolumePrice",
        "full_tank": "Full",
        "station": "City (optional)",
        "notes": "Notes (optional)",
    }


def test_the_rows_become_entries_in_the_units_that_are_stored():
    table = _table()
    mapping = fi.guess(table.columns)
    result = fi.convert(table, mapping, {"order": "auto", "dist": "km", "vol": "l"}, "L")
    assert (result.read, result.duplicates, result.problem_count) == (3, 0, 0)
    first = result.rows[0]
    assert first == {
        "date": "2024-09-16",
        "amount": 37.17,
        "odometer_km": 36633,
        "price_total": 59.43,
        "price_per_unit": 1.599,
        "full_tank": 1,
        "station": None,
        "notes": "Driver A",
    }


def test_miles_and_gallons_are_converted_to_km_and_litres():
    text = "Date;Odometer;Gallons;Price per gallon\n2024-01-05;1000;10;4.00\n"
    table = _table(text)
    result = fi.convert(table, fi.guess(table.columns), {"dist": "mi", "vol": "usgal"}, "L")
    row = result.rows[0]
    assert row["odometer_km"] == 1609 and row["amount"] == 37.854  # 10 gallons
    assert row["price_per_unit"] == pytest.approx(4.0 / 3.785411784, abs=0.001)  # a price per gallon is a price per litre
    assert row["price_total"] == 40.0  # amount x price, the units cancel


def test_other_delimiters_number_formats_and_date_orders():
    text = "Datum;Kilometerstand;Menge;Betrag\n16.09.2024;36.633;37,17;59,43 EUR\n05.09.2024;35.999;38,00;58,00 EUR\n"
    table = _table(text)
    assert table.delimiter == ";"
    result = fi.convert(table, fi.guess(table.columns), {"order": "auto"}, "L")
    assert result.order == "dmy"  # 16.09. cannot be a month
    assert [(r["date"], r["odometer_km"], r["amount"], r["price_total"]) for r in result.rows] == [
        ("2024-09-16", 36633, 37.17, 59.43),
        ("2024-09-05", 35999, 38.0, 58.0),
    ]
    assert result.rows[0]["price_per_unit"] == 1.599  # total / amount


def test_a_date_that_could_be_two_things_follows_the_choice():
    assert fi.detect_order(["01.02.2024", "03.04.2024"]) is None
    assert fi.to_date("01.02.2024", "dmy") == "2024-02-01" and fi.to_date("01.02.2024", "mdy") == "2024-01-02"
    assert fi.detect_order(["09/16/2024"]) == "mdy" and fi.detect_order(["2024/09/16"]) == "ymd"
    assert fi.to_date("20240916", "ymd") == "2024-09-16" and fi.to_date("16.9.24", "dmy") == "2024-09-16"
    for bad in ("", "tomorrow", "31.02.2024", "1900-01-01", "2999-01-01"):
        with pytest.raises(ValueError):
            fi.to_date(bad, "dmy")


def test_numbers_as_people_write_them():
    assert fi.to_number("1,234.56") == 1234.56 and fi.to_number("1.234,56") == 1234.56
    assert fi.to_number("37,17") == 37.17 and fi.to_number("59.43 EUR") == 59.43 and fi.to_number("€ 1,5") == 1.5
    assert (
        fi.to_number("36,633", whole=True) == 36633
        and fi.to_number("36.633", whole=True) == 36633
        and fi.to_number("36633.0", whole=True) == 36633
    )
    for bad in ("", "abc", "-"):
        with pytest.raises(ValueError):
            fi.to_number(bad)


def test_a_row_with_a_bad_date_or_amount_is_a_problem_the_others_are_imported():
    text = "Date,Liters\n2024-09-16,37.1\nnot a date,40\n2024-09-17,0\n2024-09-18,abc\n2024-09-19,41\n"
    table = _table(text)
    result = fi.convert(table, fi.guess(table.columns), {}, "L")
    assert [r["date"] for r in result.rows] == ["2024-09-16", "2024-09-19"]
    assert result.problem_count == 3
    assert [(n, key) for n, key, _ in result.problems] == [
        (3, "fuelimport.row_date"),
        (4, "fuelimport.row_amount"),
        (5, "fuelimport.row_amount"),
    ]


def test_a_row_that_is_in_the_log_already_is_skipped(conn, vehicle):
    conn.execute("INSERT INTO fuel(vehicle_id, date, amount, odometer_km) VALUES(?, '2024-09-16', 37.17, 36633)", (vehicle,))
    conn.execute(
        "INSERT INTO fuel(vehicle_id, date, amount, odometer_km) VALUES(?, '2024-09-05', 12.0, 35999)", (vehicle,)
    )  # same day and odometer, other amount
    table = _table()
    have = fi.known(conn, vehicle)
    result = fi.convert(table, fi.guess(table.columns), {"skip": True}, "L", have)
    assert result.duplicates == 2 and [r["date"] for r in result.rows] == ["2024-08-19"]
    again = fi.convert(table, fi.guess(table.columns), {"skip": False}, "L", have)
    assert len(again.rows) == 3  # the person may ask for everything


def test_the_rows_are_written_in_one_go(conn, vehicle):
    table = _table()
    rows = fi.convert(table, fi.guess(table.columns), {}, "L").rows
    assert fi.insert(conn, vehicle, rows) == 3
    got = conn.execute(
        "SELECT date, amount, odometer_km, price_per_unit, full_tank, notes, fuel_kind, auto_open FROM fuel ORDER BY date"
    ).fetchall()
    assert tuple(got[0]) == ("2024-08-19", 36.25, 35415, 1.529, 1, "Driver A", "main", 0)


def test_a_file_that_is_no_table_gets_a_clear_refusal():
    for data, key in (
        (b"", "fuelimport.err_empty"),
        (b"   \n  ", "fuelimport.err_empty"),
        (b"\x00\x01\x02" * 50, "fuelimport.err_binary"),
        (b"just one line", "fuelimport.err_columns"),
        (b"a,b\n", "fuelimport.err_columns"),
        (b"x" * (fi.MAX_BYTES + 1), "fuelimport.err_size"),
    ):
        with pytest.raises(fi.FileError) as caught:
            fi.read(data)
        assert caught.value.key == key, data[:20]


def test_an_old_windows_file_is_read_too():
    text = "Datum;Menge;Tankstelle\n16.09.2024;37,17;Müller Tankstelle\n"
    table = fi.read(text.encode("cp1252"))
    assert table.rows[0][2] == "Müller Tankstelle"
    assert fi.read(("﻿" + text).encode("utf-8")).columns[0] == "Datum"  # a byte order mark does not belong to the name


def test_a_text_that_would_be_a_formula_is_exported_as_text(conn, vehicle):
    """The notes of an imported file are not what the person typed: the CSV export (opened in a spreadsheet) must not run them as a formula."""
    from carassistant import fuel_export

    conn.execute(
        "INSERT INTO fuel(vehicle_id, date, amount, station, notes) VALUES(?, '2024-09-16', 30, '=cmd|calc', '@SUM(1+1)')", (vehicle,)
    )
    conn.execute(
        "INSERT INTO fuel(vehicle_id, date, amount, station, notes) VALUES(?, '2024-09-17', 30, 'Station', '-5 km from home')", (vehicle,)
    )
    rows = fuel_export.fills_in_range(conn, vehicle, "2024-01-01", "2024-12-31")
    labels = {k: k for k in fuel_export.COLUMNS}
    conv = {"dist": lambda v: v, "vol": lambda v: v, "price": lambda v: v}
    text = fuel_export.csv_bytes(rows, labels, conv).decode("utf-8-sig")
    assert "'=cmd|calc" in text and "'@SUM(1+1)" in text and "'-5 km from home" in text
    assert ";Station;" in text  # an ordinary text stays as it is
