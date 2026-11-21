"""Model year from a VIN (ISO 3779, position 10). Brand-neutral and best effort.

Most manufacturers follow the model-year code; where a VIN does not, the page shows the value with the badge
"from VIN" so it is clear where it comes from, and a year entered by hand always wins.
"""

from __future__ import annotations

import re
from datetime import date

# 30 codes, repeating every 30 years: A=1980/2010/2040 ... Y=2000/2030, 1=2001/2031 ... 9=2009/2039 (I, O, Q, U, Z, 0 are not used)
_CODES = "ABCDEFGHJKLMNPRSTVWXY123456789"
_VIN = re.compile(r"[A-HJ-NPR-Z0-9]{17}")
_ANY = re.compile(r"[A-Z0-9]{5,20}")


def clean(raw) -> str | None:
    """A VIN as typed or sent: spaces and hyphens dropped, upper case; None when empty. ValueError when it is not letters and digits (5-20)."""
    text = re.sub(r"[\s-]", "", raw if isinstance(raw, str) else "").upper()
    if not text:
        return None
    if not _ANY.fullmatch(text):
        raise ValueError("vin")
    return text


def model_year(vin: str | None, today: date | None = None) -> int | None:
    """The model year coded in position 10, resolved to the latest cycle that is not later than next year."""
    vin = (vin or "").strip().upper()
    if not _VIN.fullmatch(vin):
        return None
    index = _CODES.find(vin[9])
    if index < 0:
        return None
    limit = (today or date.today()).year + 1
    candidates = [y for y in (1980 + index, 2010 + index, 2040 + index) if y <= limit]
    return max(candidates) if candidates else None
