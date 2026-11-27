"""The import of fill-ups from a CSV file, page by page (fuelimport_web.py): the file, the columns, the check, the one that says it worked."""

import re

from carassistant import config, db

HEAD = (
    '"Data","Odo (km)","Fuel (litres)","Full","Price (optional)","l/100km (optional)","latitude (optional)","longitude (optional)","City (optional)",'
    '"Notes (optional)","Missed","TankNumber","FuelType","VolumePrice","StationID (optional)","ExcludeDistance","UniqueId","TankCalc","Weather"'
)
ROWS = (
    '"2024-09-16 15:39","36633.0","37.17","1","59.43","5.86","0.0","0.0","","Driver A","0","1","110","1.599","0","0.0","41","0.0",""\n'
    '"2024-09-05 21:00","35999.0","38.0","1","58.0","6.51","0.0","0.0","","Driver B","0","1","110","1.526","0","0.0","40","0.0",""\n'
    '"2024-08-19 18:25","35415.0","36.25","0","55.43","","0.0","0.0","","Driver A","0","1","110","1.529","0","0.0","39","0.0",""\n'
)
FUELIO = (
    '"## Vehicle"\n"Name","Description","DistUnit","FuelUnit","ConsumptionUnit","ImportCSVDateFormat"\n"Example Car","","km","Litre","l/100km","yyyy-MM-dd HH:mm"\n'
    f'"## Log"\n{HEAD}\n{ROWS}'
)


def _car(client) -> int:
    client.post("/vehicles", data={"name": "Import Car", "fuel_type": "diesel"})
    with db.tx() as conn:
        return conn.execute("SELECT id FROM vehicles ORDER BY id DESC LIMIT 1").fetchone()[0]


def _upload(client, vid: int, data: bytes = FUELIO.encode(), name: str = "fuelio.csv"):
    return client.post(f"/v/{vid}/fuel/import", files={"file": (name, data, "text/csv")})


def _token(response) -> str:
    return response.headers["location"].rstrip("/").split("/")[-1]


def _mapping(page: str) -> dict[str, str]:
    """The column that is selected for each point on the page of the columns: ``{point: name of the column}``."""
    out = {}
    for name, body in re.findall(r'<select name="col_(\w+)"[^>]*>(.*?)</select>', page, re.S):
        chosen = re.search(r'<option value="\d+"[^>]*selected[^>]*>([^<]*)</option>', body)
        out[name] = chosen.group(1) if chosen else ""
    return out


def _form(page: str, **changes) -> dict[str, str]:
    """What the browser would post from the page of the columns as it stands (the selected options), with ``changes``."""
    form = {}
    for name, body in re.findall(r'<select name="(\w+)"[^>]*>(.*?)</select>', page, re.S):
        chosen = re.search(r'<option value="([^"]*)"[^>]*selected', body)
        form[name] = chosen.group(1) if chosen else ""
    form["skip"] = "1"
    form.update(changes)
    return form


def test_the_first_page_asks_for_a_file(client):
    vid = _car(client)
    page = client.get(f"/v/{vid}/fuel/import")
    assert page.status_code == 200
    assert 'class="guide-bar"' in page.text and 'type="file"' in page.text and "Import fill-ups" in page.text
    assert client.get("/v/99999/fuel/import").status_code == 404


def test_a_fuelio_file_goes_through_all_the_pages_and_the_fill_ups_are_written(client):
    vid = _car(client)
    sent = _upload(client, vid)
    assert sent.status_code == 303
    token = _token(sent)
    columns = client.get(f"/v/{vid}/fuel/import/{token}")
    assert columns.status_code == 200 and "3 rows in the file" in columns.text
    assert _mapping(columns.text) == {
        "date": "Data",
        "amount": "Fuel (litres)",
        "odometer_km": "Odo (km)",
        "price_total": "Price (optional)",
        "price_per_unit": "VolumePrice",
        "full_tank": "Full",
        "station": "City (optional)",
        "notes": "Notes (optional)",
    }
    assert 'data-sample="e.g. 2024-09-16 15:39"' in columns.text  # the example under a choice
    saved = client.post(f"/v/{vid}/fuel/import/{token}", data=_form(columns.text))
    assert saved.status_code == 303 and saved.headers["location"].endswith(f"/{token}/check")
    check = client.get(f"/v/{vid}/fuel/import/{token}/check")
    assert "Ready to import: 3 fill-ups" in check.text and "16.09.2024" not in check.text.replace(
        "2024-09-16", ""
    )  # shown as the server writes dates
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM fuel WHERE vehicle_id = ?", (vid,)).fetchone()[0] == 0  # nothing before the last yes
    run = client.post(f"/v/{vid}/fuel/import/{token}/run")
    assert run.status_code == 303 and run.headers["location"].endswith(f"/{token}/done")
    done = client.get(f"/v/{vid}/fuel/import/{token}/done")
    assert "Import successful" in done.text and "3 fill-ups were added" in done.text
    with db.tx() as conn:
        rows = conn.execute(
            "SELECT date, odometer_km, amount, price_total, price_per_unit, full_tank, notes FROM fuel WHERE vehicle_id = ? ORDER BY date",
            (vid,),
        ).fetchall()
    assert [tuple(r) for r in rows] == [
        ("2024-08-19", 35415, 36.25, 55.43, 1.529, 0, "Driver A"),
        ("2024-09-05", 35999, 38.0, 58.0, 1.526, 1, "Driver B"),
        ("2024-09-16", 36633, 37.17, 59.43, 1.599, 1, "Driver A"),
    ]
    assert not (config.data_dir() / "import-cache" / f"{token}.csv").exists()  # the file is not kept
    assert client.post(f"/v/{vid}/fuel/import/{token}/run").status_code == 303  # a second press writes nothing more
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM fuel WHERE vehicle_id = ?", (vid,)).fetchone()[0] == 3
    assert "Driver A" in client.get(f"/v/{vid}/e/fuel").text  # they are on the fuel page


def test_the_same_file_twice_adds_nothing(client):
    vid = _car(client)
    for attempt in (1, 2):
        token = _token(_upload(client, vid))
        form = _form(client.get(f"/v/{vid}/fuel/import/{token}").text)
        client.post(f"/v/{vid}/fuel/import/{token}", data=form)
        check = client.get(f"/v/{vid}/fuel/import/{token}/check").text
        if attempt == 2:
            assert "Ready to import: 0 fill-ups - skipped: 3 that are in the log already" in check and "disabled" in check
            assert (
                client.post(f"/v/{vid}/fuel/import/{token}/run").headers["location"].endswith("/check")
            )  # nothing to write: back to the check
        else:
            client.post(f"/v/{vid}/fuel/import/{token}/run")
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM fuel WHERE vehicle_id = ?", (vid,)).fetchone()[0] == 3


def test_the_person_can_ask_for_everything_again(client):
    vid = _car(client)
    for attempt in (1, 2):
        token = _token(_upload(client, vid))
        page = client.get(f"/v/{vid}/fuel/import/{token}").text
        form = _form(page)
        if attempt == 2:
            form.pop("skip")  # the switch is off
        client.post(f"/v/{vid}/fuel/import/{token}", data=form)
        client.post(f"/v/{vid}/fuel/import/{token}/run")
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM fuel WHERE vehicle_id = ?", (vid,)).fetchone()[0] == 6


def test_the_columns_must_be_chosen_and_used_once(client):
    vid = _car(client)
    token = _token(_upload(client, vid))
    page = client.get(f"/v/{vid}/fuel/import/{token}").text
    none = client.post(f"/v/{vid}/fuel/import/{token}", data=_form(page, col_amount=""))
    assert none.status_code == 400 and "Date and Amount each need a column." in none.text
    assert _mapping(none.text)["date"] == "Data"  # what was chosen stays
    twice = client.post(f"/v/{vid}/fuel/import/{token}", data=_form(page, col_amount="0"))  # the date column once more
    assert twice.status_code == 400 and "A column can only be used for one point." in twice.text


def test_a_file_that_is_no_table_is_refused_on_the_first_page(client):
    vid = _car(client)
    for data, text in ((b"", "The file is empty."), (b"\x00\x01" * 100, "This is no CSV file"), (b"one line", "No table was found")):
        page = _upload(client, vid, data)
        assert page.status_code == 400 and text in page.text, data[:10]
    folder = config.data_dir() / "import-cache"
    assert not folder.exists() or not list(folder.glob("*.csv"))  # a refused file is not kept
    assert client.post(f"/v/{vid}/fuel/import", data={}).status_code == 400  # no file at all


def test_a_token_of_another_car_or_an_old_one_leads_nowhere(client):
    first, second = _car(client), None
    token = _token(_upload(client, first))
    client.post("/vehicles", data={"name": "Other Car", "fuel_type": "petrol"})
    with db.tx() as conn:
        second = conn.execute("SELECT id FROM vehicles ORDER BY id DESC LIMIT 1").fetchone()[0]
    assert client.get(f"/v/{second}/fuel/import/{token}").status_code == 404  # the file belongs to the first car
    gone = client.get(f"/v/{first}/fuel/import/{'x' * 20}")
    assert gone.status_code == 303 and gone.headers["location"].endswith("fuel/import?m=fi_expired")
    assert client.get(f"/v/{first}/fuel/import/short").status_code == 404  # no name a person could guess
    assert "has expired" in client.get(gone.headers["location"]).text


def test_the_texts_come_in_german_too(client):
    from carassistant import config as cfg

    vid = _car(client)
    with db.tx() as conn:
        db.set_setting(conn, "language", "de")
    cfg.forget_settings()
    token = _token(_upload(client, vid))
    page = client.get(f"/v/{vid}/fuel/import/{token}").text
    assert "Welche Spalte ist was?" in page and "Datum *" in page and "Einträge überspringen" in page
    for step in ("", "/check"):
        text = re.sub(r"<[^>]+>", " ", client.get(f"/v/{vid}/fuel/import/{token}{step}").text)
        assert not re.search(r"\b(?:fi|fuelimport)\.[a-z_0-9]+", text), step  # no untranslated key shows


def test_the_fuel_page_offers_the_import(client):
    vid = _car(client)
    page = client.get(f"/v/{vid}/e/fuel").text
    assert "Export and import" in page and "/fuel/import" in page and "Import CSV" in page
