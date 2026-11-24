"""A short walk through the pages of the app in a real browser: no server error, no script error, no failed request, no broken rule of the Content
Security Policy. ``python tools/smoke_crawl.py`` walks through all of them (a few minutes). Skipped where no Chrome / Chromium is installed."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))


def test_the_first_pages_load_without_a_single_error():
    from cdp import find_chrome

    if find_chrome() is None:
        pytest.skip("no Chrome / Chromium installed")
    import smoke_crawl

    problems, looked_at = smoke_crawl.run(limit=24)
    assert looked_at >= 20
    assert not problems, "\n".join(dict.fromkeys(problems))
