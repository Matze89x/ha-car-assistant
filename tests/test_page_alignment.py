"""The first block of every page starts level with the first card of the More list (and the title with the word More, the same gap everywhere).

It needs a real browser: tools/check_alignment.py opens every page of the More list in a headless Chrome on a temporary demo installation. The test
is skipped where no Chrome / Chromium is installed (``CHROME`` can name one)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))


def test_every_page_starts_level_with_the_more_list():
    from cdp import find_chrome

    if find_chrome() is None:
        pytest.skip("no Chrome / Chromium installed")
    import check_alignment

    problems = check_alignment.run(widths=(1200,))
    assert not problems, "\n".join(problems)
