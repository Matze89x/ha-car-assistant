"""The standing rules of the design on every page: a button never wraps its label, a row of buttons stays on one line and is one height, one main
action per card, the buttons of a form bar sit bottom right, everything you tap is at least 30 px, every button has a name and every field a label.

It needs a real browser: tools/check_ui.py opens every page (with the folded forms opened) in a headless Chrome on a temporary demo installation -
German at phone width (the longest words, the least room) and English wide. Skipped where no Chrome / Chromium is installed."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))


@pytest.mark.parametrize(("width", "lang"), [(360, "de"), (1200, "en")])
def test_every_page_keeps_the_design_rules(width, lang):
    from cdp import find_chrome

    if find_chrome() is None:
        pytest.skip("no Chrome / Chromium installed")
    import check_ui

    problems = check_ui.run(width=width, lang=lang)
    assert not problems, "\n".join(problems)
