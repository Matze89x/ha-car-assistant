"""A text for a spreadsheet. One place for what every CSV export does with the text it writes: a text that starts with ``=``, ``+``, ``-``, ``@`` or a tab or
a line break is read by Excel and other spreadsheets as a FORMULA (``=HYPERLINK(...)``, ``+cmd|...``), and the text of an imported file or of a plugin is not one
the person typed - so a quote in front makes it a text."""

from __future__ import annotations

DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def safe(value: str | None) -> str:
    """``value`` as a cell of a CSV file that no spreadsheet will run (``None`` is an empty cell)."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in DANGEROUS else text
