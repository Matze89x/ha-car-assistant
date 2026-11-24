"""A heading that stands on its own on a page is a section label of the design book (11 px, upper case, dim, left aligned, the spacing of
``.vd-group-h``) - on every page, with no label of a page's own (the About page once centred them).

It needs a real browser: tools/check_headings.py opens every page of the More list in a headless Chrome on a temporary demo installation. The test is
skipped where no Chrome / Chromium is installed (``CHROME`` can name one)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))


def test_every_free_standing_heading_is_a_section_label_of_the_design_book():
    from cdp import find_chrome

    if find_chrome() is None:
        pytest.skip("no Chrome / Chromium installed")
    import check_headings

    problems = check_headings.run(width=1200)
    assert not problems, "\n".join(problems)
