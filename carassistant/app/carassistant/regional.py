"""Date and time as the people of this installation write them (Settings > System > Region).

One server-wide choice (like units and currency): how a date is written, and whether the clock has 24 hours or 12 (am / pm). "auto" follows the
language. Stored values stay ISO (dates) and 24 h (times); only what is SHOWN changes. Everything that shows a date or a time asks this module.
"""

from __future__ import annotations

import os
import re
import time
from datetime import UTC, date, datetime

from . import config, i18n

DATE_SETTING, TIME_SETTING, TZ_SETTING = "region.date", "region.time", "region.tz"
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


# ---------------------------------------------------------------------------------------------- time zone
_zones: list[str] | None = None
_applied: str | None = None  # the zone the process was set to ("" = the machine's own)


def zones() -> list[str]:
    """Every time zone name the system knows (``Europe/Berlin``, ...), sorted."""
    global _zones
    if _zones is None:
        from zoneinfo import available_timezones

        _zones = sorted(
            z
            for z in available_timezones()
            if ("/" in z and not z.startswith(("posix/", "right/", "Etc/", "SystemV/", "US/"))) or z == "UTC"
        )
    return _zones


def home_assistant_zone() -> str:
    """The time zone of Home Assistant ("" when there is no Home Assistant or it says nothing usable)."""
    from . import ha

    try:
        name = str(ha.get_config().get("time_zone") or "") if ha.available() else ""
    except Exception:
        name = ""
    return name if name in zones() else ""


def automatic_zone() -> str:
    """What "automatic" means (for the label): the time zone of Home Assistant, else the zone the machine runs in."""
    return home_assistant_zone() or os.environ.get("TZ_ORIGINAL") or os.environ.get("TZ") or time.tzname[0]


def zone_key() -> str:
    """The chosen zone (``auto`` when none was chosen)."""
    chosen = config.stored_setting(TZ_SETTING)
    return chosen if chosen in zones() else "auto"


def apply() -> str:
    """Make the whole process follow the zone (every ``datetime.now()``, ``date.today()``, ``astimezone()`` and local time of the pages, with summer
    and winter time from the time zone database). Automatic = the zone of Home Assistant; without one the machine's own zone is left alone.
    Cheap: it only acts when the zone changed."""
    global _applied
    key = zone_key()
    target = key if key != "auto" else home_assistant_zone()  # "" = leave the machine's zone as it is
    if target != _applied:
        if "TZ_ORIGINAL" not in os.environ:
            os.environ["TZ_ORIGINAL"] = os.environ.get("TZ") or ""
        if target:
            os.environ["TZ"] = target
        elif os.environ["TZ_ORIGINAL"]:
            os.environ["TZ"] = os.environ["TZ_ORIGINAL"]
        else:
            os.environ.pop("TZ", None)
        time.tzset()
        _applied = target
    return target or automatic_zone()


def clock() -> dict:
    """The current time in the zone, for the settings card: ``{"time", "date", "abbr", "offset", "summer"}``."""
    apply()
    now = datetime.now(UTC).astimezone()
    off = now.utcoffset()
    minutes = int(off.total_seconds() // 60) if off else 0
    sign = "+" if minutes >= 0 else "-"
    return {
        "iso": now.isoformat(timespec="seconds"),
        "time": ftime(now),
        "date": fdate(now),
        "abbr": now.strftime("%Z"),
        "offset": f"UTC{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}",
        "summer": bool(now.dst()),
    }


def fdatetime(value) -> str:
    """A stored UTC time (ISO text or datetime) as date and time in the system's zone and writing: ``22.11.2026 11:20``. Unreadable text as it is."""
    if not value:
        return ""
    try:
        stamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    local = stamp.astimezone()
    return f"{fdate(local)} {ftime(local)}"


def flog(value) -> str:
    """A time stamp of a log line in the system's zone: ``11:20:05`` today, ``21.11. 11:20:05`` before. Text that is no time is shown as it is."""
    if not value:
        return ""
    try:
        stamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    local = stamp.astimezone()
    clock_part = local.strftime("%H:%M:%S") if time_key() != "12" else local.strftime("%I:%M:%S %p").lstrip("0")
    if local.date() == datetime.now().astimezone().date():
        return clock_part
    fmt = date_format()
    fmt = fmt[2:].lstrip(".-/ ") if fmt.startswith("%Y") else fmt[:-2].rstrip(".-/ ") if fmt.endswith("%Y") else fmt
    return f"{local.strftime(fmt)} {clock_part}"
