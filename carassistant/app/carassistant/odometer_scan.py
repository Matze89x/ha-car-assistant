"""A photo of the odometer -> the number on it (the text recognition of receipt.py, answering with digits only).

The result is a guess the person checks before saving: a dashboard shows light digits on dark glass, often next to a trip counter. So the photo is
read light-on-dark and dark-on-light in several page layouts, the numbers found are compared with the last reading of the car, and the one that is
plausible and found by most layouts wins. Nothing here is stored."""

from __future__ import annotations

import re
import time
from collections import Counter

from . import receipt

MAX_DIGITS = 7  # 9,999,999: more is no odometer
MIN_VALUE = 100  # a smaller number is a trip counter or noise
BUDGET = 9.0  # seconds of text recognition for one photo, at most
MAX_JUMP = 100_000  # since the last reading a car does not drive more than this


def numbers(text: str) -> list[int]:
    """Every number of 3 to 7 digits in the text; two neighbouring groups of ONE line with a thousands split ("52 340") are read as one number as well
    (the numbers of two lines - a dial and a trip counter - are never joined)."""
    found: list[int] = []
    for line in text.splitlines():
        tokens = [x for x in re.findall(r"\d+", line) if x]
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


# a number with a unit behind it ("86020 km", "86.020 km", "53 450 mi") is the odometer; "24.5 km" has a decimal and is a trip counter
LABELLED = re.compile(r"(?<![\d.,])(\d{1,3}(?:[ .,'’]\d{3})+|\d{3,7})(?![\d])\s*(?:km|mi|kilometer)\b(?!\s*/)", re.I)  # not "km/h"
LOWER = 0.5  # the odometer sits in the lower half of a cluster; the dial numbers (0 ... 260) are above it


def labelled(text: str) -> list[int]:
    """The numbers of a text that stand right before ``km`` / ``mi`` and have no decimals (thousands groups are joined): the odometer, not a trip counter."""
    text = re.sub(r"(?<=\d)[Oo](?=\d)|(?<=\d)[Oo](?=\s*km)", "0", text)  # a letter O inside a number
    found = []
    for m in LABELLED.finditer(text):
        value = int(re.sub(r"\D", "", m.group(1)))
        if MIN_VALUE <= value < 10**MAX_DIGITS:
            found.append(value)
    return found


def consensus(top: int, votes: Counter, last: int | None) -> int:
    """The figure with every digit decided by the vote of the readings: a single misread digit (an 8 read as a 3, a 0 as a 9) is outvoted by the
    others. Only figures of the same length that differ from the best one in at most two places vote."""
    text = str(top)
    group = {n: v for n, v in votes.items() if len(str(n)) == len(text) and sum(a != b for a, b in zip(str(n), text, strict=True)) <= 2}
    if len(group) < 2:
        return top
    digits = []
    for pos in range(len(text)):
        tally: Counter = Counter()
        for n, v in group.items():
            tally[str(n)[pos]] += v
        digits.append(max(tally.items(), key=lambda kv: (kv[1], kv[0] == text[pos]))[0])
    value = int("".join(digits))
    return value if plausible(value, last) or not plausible(top, last) else top


def read(data: bytes, last: int | None = None) -> dict:
    """A photo -> ``{"value": int | None, "plausible": bool}``. ValueError for a file that is no photo.

    The lower half is read first (the odometer is there, away from the dial numbers), with the unit as a clue: a number before "km" counts more. Then
    the whole photo (somebody may have photographed only the little display). Every reading is one vote per number; four readings that agree on a plausible
    number end the search. When they do not agree - a crooked, dim or soft photo - more views follow (sharper, black and white, turned back a little)
    and in the end every digit is decided by the vote of the readings, so that one misread digit does not win."""
    if len(data) > receipt.MAX_BYTES:
        raise ValueError("too large")
    cleaned = receipt.deskew(receipt.clean(data))
    votes: Counter = Counter()  # number -> weighted votes
    readings: Counter = Counter()  # number -> how many different readings found it
    tagged: set[int] = set()  # numbers that stood right before their unit

    def add(numbers_found, weight: int) -> None:
        for n in set(numbers_found):
            votes[n] += weight
            readings[n] += 1

    def best() -> tuple[int | None, bool]:
        # a number with its unit beats every other (even one below the last reading: it is shown, flagged) - but not a small one: next to a reading
        # of 86 020 a number like 240 is a trip counter, whatever the last reading says
        units = [n for n in tagged if last is None or n >= last * 0.5]
        everything = units or list(votes)
        pool = [n for n in everything if plausible(n, last)] or everything
        if not pool:
            return None, False
        value = max(pool, key=lambda n: (votes[n], len(str(n)), n))
        return value, plausible(value, last)

    def sure() -> bool:
        value, ok = best()
        return value is not None and ok and readings[value] >= 4

    deadline = time.monotonic() + BUDGET

    def look(image: bytes, weight: int, text_too: bool) -> bool:
        if time.monotonic() > deadline:  # enough tries: what is known is what is offered
            return True
        if text_too:  # the unit as a clue, read as text (not only digits)
            found = labelled(receipt.read_text(image, 6))
            tagged.update(found)
            add(found, 4)
        for psm in (6, 11, 7):  # page layouts: several lines first (a trip counter confuses the single-line reading)
            add(numbers(receipt.read_text(image, psm, digits=True)), weight)
            if sure():
                return True
        return False

    with receipt._one_at_a_time:
        low = receipt.lower(cleaned, LOWER)
        done = False
        for part, weight in ((low, 2), (cleaned, 1)):
            for image in (part, receipt.inverted(part)):
                if look(image, weight, weight == 2):
                    done = True
                    break
            if done:
                break
        if not done:  # not sure: a tighter strip (a small window in a dial) and other views of the lower half and of the whole photo
            strip = receipt.lower(cleaned, 0.4)
            for kind in ("plain", "sharp", "bin"):
                for part, weight in ((strip, 2), (low, 2), (cleaned, 1)) if kind == "plain" else ((low, 2), (cleaned, 1)):
                    view = part if kind == "plain" else receipt.variant(part, kind)
                    if look(view, weight, weight == 2) or look(receipt.inverted(view), weight, False):
                        done = True
                        break
                if done:
                    break
    value, ok = best()
    if value is not None:
        value = consensus(value, votes, last)
        ok = plausible(value, last)
    return {"value": value, "plausible": ok}
