"""The one way every list of cards works: a batch of N cards (10 / 25 / 50, the person's choice), the next batch loads while scrolling,
and a heading wherever the period changes (Today, Yesterday, This week, Last week, then the month)."""

from __future__ import annotations

import sqlite3
from contextvars import ContextVar
from datetime import date, timedelta

from . import db, userprefs

SIZES = (10, 25, 50)
DEFAULT = 10
SETTING = "ui.page_size"
_size: ContextVar[int] = ContextVar("list_page_size", default=DEFAULT)


def clean(raw: object) -> int | None:
    try:
        value = int(str(raw))
    except ValueError:
        return None
    return value if value in SIZES else None


def current_choice(conn: sqlite3.Connection, user_id: int | None) -> int:
    """The person's own choice if signed in and set, else the server's, else 10."""
    mine = clean(userprefs.get(conn, user_id, "page_size") or "")
    return mine or clean(db.get_setting(conn, SETTING, str(DEFAULT))) or DEFAULT


def use(conn: sqlite3.Connection, user_id: int | None) -> None:
    """Called once per request: the size every list of this request works with."""
    _size.set(current_choice(conn, user_id))


def size() -> int:
    return _size.get()


def period(day: str | None, today: date, lang: str) -> tuple[str, str]:
    """(key, title) of the heading a date belongs under."""
    try:
        d = date.fromisoformat((day or "")[:10])
    except ValueError:
        return "none", "–"
    from . import trips
    from .i18n import translator

    t = translator(lang)
    delta = (today - d).days
    if delta == 0:
        return "today", t("per.today")
    if delta == 1:
        return "yesterday", t("per.yesterday")
    monday = today - timedelta(days=today.weekday())
    if monday <= d <= today:
        return "week", t("per.week")
    if monday - timedelta(days=7) <= d < monday:
        return "lastweek", t("per.lastweek")
    names = trips.MONTHS.get(lang, trips.MONTHS["en"])
    return d.strftime("%Y-%m"), f"{names[d.month - 1]} {d.year}"


def with_headings(
    rows, date_key: str, previous: str | None, lang: str, today: date | None = None, mode: str = "period"
) -> list[tuple[dict | None, object]]:
    """Rows (already in order) as (heading or None, row): a heading wherever the group changes. ``previous`` is the date of the row
    just before this batch, so a group that goes on over a batch border gets no second heading."""
    from . import trips

    today = today or date.today()

    def group(day: str | None) -> tuple[str, str]:
        if mode == "month":
            try:
                d = date.fromisoformat((day or "")[:10])
            except ValueError:
                return "none", "–"
            names = trips.MONTHS.get(lang, trips.MONTHS["en"])
            return d.strftime("%Y-%m"), f"{names[d.month - 1]} {d.year}"
        return period(day, today, lang)

    last = group(previous)[0] if previous else None
    out: list[tuple[dict | None, object]] = []
    for row in rows:
        key, title = group(row[date_key])
        out.append(({"key": key, "title": title} if key != last else None, row))
        last = key
    return out
