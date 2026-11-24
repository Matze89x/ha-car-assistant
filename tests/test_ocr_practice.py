"""The reading of the practice set (tools/practice_photos.py: made-up clusters and receipts with their right answers) with the real text recognition.

It guards the reading against getting worse: the clean photos must be read right in nearly all cases. ``python tools/ocr_bench.py`` measures the same
for crooked, dim, soft and small photos too. Skipped where Tesseract is not installed."""

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from carassistant import odometer_scan, receipt


@pytest.mark.skipif(not receipt.available(), reason="Tesseract is not installed")
def test_the_clean_practice_photos_are_read_right():
    import practice_photos as pp

    cluster_ok = [odometer_scan.read(c.data, c.last)["value"] == c.truth["value"] for c in pp.cluster_cases()]
    assert sum(cluster_ok) >= len(cluster_ok) - 1, cluster_ok  # every cluster but (at most) one of the twelve
    good = 0
    cases = pp.receipt_cases()
    for case in cases:
        got = receipt.scan(case.data, date(2026, 11, 24))
        wrong = [k for k in ("amount", "price_per_unit", "price_total") if got[k] is None or abs(got[k] - case.truth[k]) > 0.005]
        assert not wrong, (case.name, wrong)  # what is paid and what is bought is never wrong on a clean receipt
        assert got["date"] == case.truth["date"], case.name
        odo = got["odometer"]  # a digit can be misread: the figure is shown for checking, so a few misses are allowed
        good += odo == case.truth["odometer"] or case.truth["odometer"] is None
    assert good >= len(cases) - 3
