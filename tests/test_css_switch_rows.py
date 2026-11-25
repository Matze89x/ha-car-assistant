"""Switch rows (.sw-row) sit exactly in the middle of their own divided row: no generic rule may give them an outer gap."""

import re
from pathlib import Path

CSS = (Path(__file__).resolve().parents[1] / "carassistant" / "app" / "carassistant" / "static" / "pc-core.css").read_text()


def test_no_stacked_label_rule_adds_a_gap_around_switch_rows():
    """``label + label { margin-top }`` rules are for stacked inputs; they must say ``:not(.sw-row)`` on both labels (a gap above only the second
    and later switch rows made their text look pushed down)."""
    for match in re.finditer(r"([^{}]*label[^{}]*\+\s*label[^{}]*)\{([^}]*)\}", CSS):
        selector, body = match.group(1), match.group(2)
        if "var(--sp-field)" in body and ".nm-row.sw-row" in selector:
            continue  # the ONE deliberate gap: a switch row right under a field keeps the air of the design, so its line does not touch the field
        if "margin-top" in body or re.search(r"margin\s*:", body):
            assert selector.count(":not(.sw-row)") >= 2, selector.strip()


def test_a_switch_row_has_a_fixed_minimum_height_and_centres_its_content():
    assert (
        "form label.nm-row.sw-row { align-items: center; min-height: 52px;" in CSS.replace("\n", " ")
        or ".nm-row, .card label.nm-row.sw-row, form label.nm-row.sw-row { align-items: center; min-height: 52px;" in CSS
    )
