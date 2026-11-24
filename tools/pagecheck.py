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
    script: str, *, width: int = 1200, lang: str = "en", open_all: bool = False, height: int = 900, theme: str = "", accent: str = ""
) -> Iterator[tuple[str, object]]:
    """``(page, answer)`` for every page: ``script`` is run in the page and must return a JSON text (``JSON.stringify(...)``).
    ``theme`` / ``accent`` set the design of the whole installation (``light``, ``custom-dark`` ...), ``""`` is the classic one."""
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
        env = {**os.environ, "CARASSISTANT_DATA": str(data), "CARASSISTANT_DEV": "1", "CARASSISTANT_PORT": str(port)}
        env["PYTHONPATH"] = str(ROOT / "carassistant" / "app")
        server = subprocess.Popen([sys.executable, "-m", "carassistant"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603
        try:
            base = f"http://127.0.0.1:{port}"
            ms.wait_for(base + "/healthz")
            with Browser() as b:
                for page in dict.fromkeys(check_alignment.page_list(b, base, ms)):
                    b.open(base + page, width, height, 1, settle=0.35)
                    if open_all:
                        b.run(OPEN_ALL)
                    yield page, json.loads(b.run(script))
        finally:
            server.terminate()
            server.wait(timeout=10)
