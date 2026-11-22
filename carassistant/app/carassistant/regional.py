"""Date and time as the people of this installation write them (Settings > System > Region).

One server-wide choice (like units and currency): how a date is written, and whether the clock has 24 hours or 12 (am / pm). "auto" follows the
language. Stored values stay ISO (dates) and 24 h (times); only what is SHOWN changes. Everything that shows a date or a time asks this module.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from . import config, i18n

DATE_SETTING, TIME_SETTING = "region.date", "region.time"
DATES = {  # key -> (strftime format, example)
    "dmy_dot": "%d.%m.%Y",
    "dmy_slash": "%d/%m/%Y",
    "mdy_slash": "%m/%d/%Y",
    "ymd_dash": "%Y-%m-%d",
}
TIMES = ("24", "12")


def date_format() -> str:
    key = config.stored_setting(DATE_SETTING)
    return DATES.get(key or "") or i18n.LANGUAGES[config.language()]["date"]


def date_key() -> str:
    key = config.stored_setting(DATE_SETTING)
    return key if key in DATES else "auto"


def time_key() -> str:
    key = config.stored_setting(TIME_SETTING)
    return key if key in TIMES else "auto"


def time_format() -> str:
    return "%I:%M %p" if time_key() == "12" else "%H:%M"


def fdate(value) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        value = value.date()
    if not isinstance(value, date):
        try:
            value = date.fromisoformat(str(value)[:10])
        except ValueError:
            return str(value)
    return value.strftime(date_format())


def ftime(value) -> str:
    """A time of day: a datetime, or "HH:MM" / "HH:MM:SS" text. Unreadable text is shown as it is."""
    if not value:
        return ""
    if not isinstance(value, datetime):
        try:
            value = datetime.strptime(str(value)[:5], "%H:%M")
        except ValueError:
            return str(value)
    text = value.strftime(time_format())
    return text.lstrip("0") if time_key() == "12" else text


def fshort(value) -> str:
    """Date and time without the year ("13.11. 16:04"), in the local time zone and the date order of the setting."""
    if not value:
        return ""
    fmt = date_format()
    fmt = fmt[2:].lstrip(".-/ ") if fmt.startswith("%Y") else fmt[:-2].rstrip(".-/ ") if fmt.endswith("%Y") else fmt
    local = value.astimezone()
    return f"{local.strftime(fmt)} {ftime(local)}"


def fmonth(value: str) -> str:
    """``YYYY-MM`` written like the date setting writes a month (12.2026, 12/2026, 2026-12)."""
    try:
        year, month = int(value[:4]), int(value[5:7])
    except ValueError:
        return value
    fmt = date_format()
    if fmt.startswith("%Y"):
        return f"{year:04d}-{month:02d}"
    sep = "/" if "/" in fmt else "."
    return f"{month:02d}{sep}{year:04d}"


def field_value(value: str | None) -> str:
    """What a date field of a form shows: a day or a month ("YYYY-MM"), in the written form of the setting."""
    if not value:
        return ""
    return fmonth(value) if len(value) == 7 else fdate(value)


def placeholder() -> str:
    return date(2026, 12, 31).strftime(date_format())


def to_iso(raw: str) -> str:
    """Typed in any usual way (31.12.2026, 12/31/2026, 12.2026, 2026-12) -> ISO (``YYYY-MM-DD`` or ``YYYY-MM``). Unknown text is returned unchanged."""
    text = raw.strip()
    if re.fullmatch(r"\d{4}-\d{1,2}(-\d{1,2})?", text):
        return "-".join(p.zfill(2) if i else p for i, p in enumerate(text.split("-")))
    m = re.fullmatch(r"(\d{1,2})[./](\d{4})", text)
    if m:
        return f"{m[2]}-{int(m[1]):02d}"
    m = re.fullmatch(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", text)
    if m:
        a, b, year = int(m[1]), int(m[2]), m[3]
        fmt = date_format()
        month_first = fmt.index("%m") < fmt.index("%d")
        day, month = (b, a) if month_first else (a, b)
        return f"{year}-{month:02d}-{day:02d}"
    return text
