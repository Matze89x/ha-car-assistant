"""A photo of the odometer -> the number on it (the text recognition of receipt.py, answering with digits only).

The result is a guess the person checks before saving: a dashboard shows light digits on dark glass, often next to a trip counter. So the photo is
read light-on-dark and dark-on-light in several page layouts, the numbers found are compared with the last reading of the car, and the one that is
plausible and found by most layouts wins. Nothing here is stored."""

from __future__ import annotations

import re
from collections import Counter

from . import receipt

MAX_DIGITS = 7  # 9,999,999: more is no odometer
MIN_VALUE = 100  # a smaller number is a trip counter or noise
MAX_JUMP = 100_000  # since the last reading a car does not drive more than this


def numbers(text: str) -> list[int]:
    """Every number of 3 to 7 digits in the text; two neighbouring groups with a thousands split ("52 340") are read as one number as well."""
    tokens = [t for t in re.findall(r"\d+", text) if t]
    found: list[int] = []
    for i, tok in enumerate(tokens):
        if 3 <= len(tok) <= MAX_DIGITS:
            found.append(int(tok))
        if i + 1 < len(tokens) and 1 <= len(tok) <= 3 and len(tokens[i + 1]) == 3 and len(tok) + 3 <= MAX_DIGITS:
            found.append(int(tok + tokens[i + 1]))
    return [n for n in found if n >= MIN_VALUE]


def plausible(value: int, last: int | None) -> bool:
    """Not below the last reading and not impossibly far above it (without a last reading: any number that can be an odometer)."""
    if last is None:
        return MIN_VALUE <= value <= 10**MAX_DIGITS - 1
    return last <= value <= last + MAX_JUMP


def pick(found: list[int], last: int | None) -> tuple[int | None, bool]:
    """The best number and whether it is plausible: the plausible ones first, then the most votes, then the longer, then the larger."""
    if not found:
        return None, False
    ok = [n for n in found if plausible(n, last)]
    pool = ok or found
    best = max(Counter(pool).items(), key=lambda kv: (kv[1], len(str(kv[0])), kv[0]))[0]
    return best, bool(ok)


def read(data: bytes, last: int | None = None) -> dict:
    """A photo -> ``{"value": int | None, "plausible": bool}``. ValueError for a file that is no photo."""
    if len(data) > receipt.MAX_BYTES:
        raise ValueError("too large")
    cleaned = receipt.clean(data)
    variants = [cleaned, receipt.inverted(cleaned)]
    found: list[int] = []
    with receipt._one_at_a_time:
        for psm in (6, 11, 7):  # page layouts: several lines first (a trip counter confuses the single-line reading)
            seen: set[int] = set()
            for image in variants:
                seen.update(numbers(receipt.read_text(image, psm, digits=True)))
            found += sorted(seen)  # one vote per page layout: the same wrong reading of both copies is still one vote
            value, ok = pick(found, last)
            if value is not None and ok and found.count(value) >= 2:  # two layouts agree on a plausible number: good enough
                return {"value": value, "plausible": True}
    value, ok = pick(found, last)
    return {"value": value, "plausible": ok}
