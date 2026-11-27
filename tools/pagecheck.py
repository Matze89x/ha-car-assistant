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

# what is folded away until somebody taps it: the add form, the edit form of a card, extra-work edit boxes
OPEN_ALL = (
    "document.querySelectorAll('details').forEach(function (d) { d.open = true; });"
    "document.querySelectorAll('[data-rec-edit]').forEach(function (c) { c.classList.add('editing'); });"
    "document.querySelectorAll('.za-edit[hidden]').forEach(function (e) { e.hidden = false; });"
)


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
