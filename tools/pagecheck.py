"""One place that opens every page of the app in a headless Chrome and hands a script's answer back - the base of the browser checks
(``check_alignment.py``, ``check_headings.py``, ``check_ui.py``).

A temporary demo installation (``make_screenshots.seed``) is started on a free port; the pages are those of ``check_alignment.page_list`` (every page of
the More list of a car with much data and one with little, settings, plugins ...). ``OPEN_ALL`` opens what is folded or hidden (cards, edit forms)
so that the controls inside are measured, too.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

# what is folded away until somebody taps it: the add form, the edit form of a card, extra-work edit boxes, the panel of a new entry
OPEN_ALL = (
    "document.querySelectorAll('details').forEach(function (d) { d.open = true; });"
    "document.querySelectorAll('[data-rec-edit]').forEach(function (c) { c.classList.add('editing'); });"
    "document.querySelectorAll('.za-edit[hidden]').forEach(function (e) { e.hidden = false; });"
    "document.querySelectorAll('.tp-add[hidden], .tp-add .tp-form[hidden]').forEach(function (e) { e.hidden = false; });"  # the form of a new entry
)


FUELIO_DEMO = (
    '"Data","Odo (km)","Fuel (litres)","Full","Price (optional)","l/100km (optional)","latitude (optional)","longitude (optional)","City (optional)",'
    '"Notes (optional)","Missed","TankNumber","FuelType","VolumePrice"\n'
    '"2024-09-16 15:39","36633.0","37.17","1","59.43","5.86","0.0","0.0","","Example","0","1","110","1.599"\n'
    '"2024-09-05 21:00","35999.0","38.0","1","58.0","6.51","0.0","0.0","","Example","0","1","110","1.526"\n'
)


TRIPS_DEMO = (
    "Date;Start time;End time;From;To;Start odometer;End odometer;Distance;Category;Purpose\n"
    "2024-09-16;08:05;08:40;Example town;Other town;12000;12035;35,2;Business;Client\n"
    "2024-09-17;17:10;17:45;Other town;Example town;12035;12071;;Private;\n"
)


def _import_flow(base: str, car: str, path: str, text: str, filename: str, mapping: dict, options: dict) -> list[str]:
    """The pages of an import from a CSV file: the file, the columns of a file that was chosen, the check. The file is uploaded the way a browser does
    it; nothing is written (the last page is only asked for)."""
    import urllib.parse
    import urllib.request
    import uuid

    boundary = uuid.uuid4().hex
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: text/csv\r\n\r\n{text}\r\n--{boundary}--\r\n'
    ).encode()
    request = urllib.request.Request(
        f"{base}/v/{car}/{path}", data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=20) as answer:  # noqa: S310 - the app on this machine
        columns = urllib.parse.urlparse(answer.geturl()).path
    form = urllib.parse.urlencode({**mapping, **options}).encode()
    with urllib.request.urlopen(urllib.request.Request(f"{base}{columns}", data=form, method="POST"), timeout=20):  # noqa: S310
        pass
    return [f"/v/{car}/{path}", columns, f"{columns}/check"]


def import_pages(base: str, car: str) -> list[str]:
    """The pages of the import of fill-ups (fuelimport_web.py)."""
    mapping = {
        "col_date": 0,
        "col_amount": 2,
        "col_odometer_km": 1,
        "col_price_total": 4,
        "col_price_per_unit": 13,
        "col_full_tank": 3,
        "col_notes": 9,
    }
    return _import_flow(
        base, car, "fuel/import", FUELIO_DEMO, "fuelio.csv", mapping, {"order": "auto", "dist": "km", "vol": "l", "skip": "1"}
    )


def trip_import_pages(base: str, car: str) -> list[str]:
    """The pages of the import of trips (tripimport_web.py)."""
    mapping = {
        "col_date": 0,
        "col_start_time": 1,
        "col_end_time": 2,
        "col_start_place": 3,
        "col_end_place": 4,
        "col_start_km": 5,
        "col_end_km": 6,
        "col_distance_km": 7,
        "col_category": 8,
        "col_purpose": 9,
    }
    return _import_flow(base, car, "trips-csv", TRIPS_DEMO, "trips.csv", mapping, {"order": "auto", "dist": "km", "skip": "1"})


def sweep(
    script: str,
    *,
    width: int = 1200,
    lang: str = "en",
    open_all: bool = False,
    height: int = 900,
    theme: str = "",
    accent: str = "",
    home: bool = False,
) -> Iterator[tuple[str, object]]:
    """``(page, answer)`` for every page: ``script`` is run in the page and must return a JSON text (``JSON.stringify(...)``).
    ``theme`` / ``accent`` set the design of the whole installation (``light``, ``custom-dark`` ...), ``""`` is the classic one;
    ``home`` adds the dashboards of the two demo cars (they are not in the More list)."""
    import check_alignment
    import make_screenshots as ms
    from cdp import Browser

    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp)
        check_alignment._seed(data, lang)
        if theme:
            import sqlite3

            db = sqlite3.connect(data / "carassistant.db")
            db.execute("INSERT OR REPLACE INTO settings(key, value) VALUES('ui.theme', ?)", (theme,))
            if accent:
                db.execute("INSERT OR REPLACE INTO settings(key, value) VALUES('ui.accent', ?)", (accent,))
            db.commit()
            db.close()
        port = ms.free_port()
        env = {
            **os.environ,
            "CARASSISTANT_DATA": str(data),
            "CARASSISTANT_DEV": "1",
            "CARASSISTANT_PORT": str(port),
            "CARASSISTANT_DEV_NETWORK_PORT": "8321",
        }  # a host port is "mapped": the pages that need one are checked too
        env["PYTHONPATH"] = str(ROOT / "carassistant" / "app")
        server = subprocess.Popen([sys.executable, "-m", "carassistant"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603
        try:
            base = f"http://127.0.0.1:{port}"
            ms.wait_for(base + "/healthz")
            with Browser() as b:
                pages = (
                    check_alignment.page_list(b, base, ms)
                    + [
                        f"/v/{ms.EV}/e/fuel"
                    ]  # the charging page of an electric car (a main tab, not a page of the More list): charging points, filters, the cog
                    + [
                        f"/v/{ms.DIESEL}/e/trips",
                        f"/v/{ms.DIESEL}/e/fuel",
                        f"/v/{ms.DIESEL}/invoices",
                        f"/v/{ms.DIESEL}/invoices/{ms.INVOICE_OPEN}",
                        f"/v/{ms.DIESEL}/invoices/{ms.INVOICE_BOOKED}",
                        f"/v/{ms.DIESEL}/e/service?invoice={ms.INVOICE_OPEN}",
                        *import_pages(base, ms.DIESEL),
                        *trip_import_pages(base, ms.DIESEL),
                    ]  # the main tabs of a car: trips (a card per trip) and the fill-ups; the invoices (list, one open, one booked) and an entry being booked
                    + ([f"/v/{ms.DIESEL}", f"/v/{ms.COMPACT}"] if home else [])
                )
                if os.environ.get("CA_CHECK_BLOCK_FONTS"):  # to see what a machine without the web fonts would see
                    b.call("Network.setBlockedURLs", urls=["*.woff2"])
                for page in dict.fromkeys(pages):
                    b.open(base + page, width, height, 1, settle=0.35)
                    # the measuring waits for the REAL font: with the stand-in font (font-display: swap) every word is a different width. fonts.ready alone is not
                    # enough - it is done at once when the page has not asked for a font yet (a slow machine) - so the faces are asked for by name first.
                    b.run(
                        "Promise.all(['400 15px \"Space Grotesk\"', '600 15px \"Space Grotesk\"', '700 15px \"Space Grotesk\"', '400 12px \"Space Mono\"', '700 12px \"Space Mono\"']"
                        ".map(function (f) { return document.fonts.load(f).catch(function () { return null; }); })).then(function () { return document.fonts.ready; }).then(function () { return true; })"
                    )
                    if open_all:
                        b.run(OPEN_ALL)
                    yield page, json.loads(b.run(script))
        finally:
            server.terminate()
            server.wait(timeout=10)
