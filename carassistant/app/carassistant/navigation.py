"""Main navigation: Home (fixed), up to four freely chosen entries, "More" (fixed). Every entry has an icon.

The order of all pages is stored in the settings table as JSON (``nav.slots``): ``[{"m": "service", "i": "wrench"}, ...]``.
The first four go into the bar, everything after that is listed in More.
"""

from __future__ import annotations

import json
import sqlite3

from . import db, icons, modules, slugs, status, summary

SETTING = "nav.slots"
MAX_SLOTS = 4
SHORT = {"service": "nav.service", "fuel": "nav.fuel", "trips": "nav.trips"}  # short names for the bar
MAIN_PAGES = ("security", "service", "trips", "fuel")  # the pages of the default bar; when moved out they head the More page
DEFAULT_SLOTS: list[tuple[str, str]] = [
    ("security", "shield-check"),
    ("service", "wrench"),
    ("trips", "map-marker-path"),
    ("fuel", "gas-station"),
]


def choices() -> list[modules.Module]:
    """Modules that can be placed in the bar: vehicle pages except Home and the vehicle form."""
    return [m for m in modules.MODULES if m.scope == "vehicle" and m.key not in ("overview", "edit", "counters", "stations")]


X = "x-"  # the key of an integration's page in the navigation: x-<integration id>


def integration_pages(conn: sqlite3.Connection, vehicle_id: int | None) -> dict[str, dict]:
    """Pages of the running integrations of this vehicle that may sit in the bar: ``{key: {name, path, icon}}``."""
    if not vehicle_id:
        return {}
    from . import config, pagemods

    out = {}
    for m in pagemods.active_modules(conn, vehicle_id):
        if m["nav"]:
            out[X + m["addon_id"]] = {
                "name": pagemods.localize(m, config.language())["name"],
                "path": f"/m/{m['addon_id']}",
                "icon": m["icon"],
            }
    return out


def default_icon(key: str) -> str:
    return icons.MODULE_ICON.get(key, icons.DEFAULT_ICON)


def _key(vehicle_id: int | None) -> str:
    """The navigation belongs to a VEHICLE (each car shows the pages it uses); ``nav.slots`` without an id is only the old shared default."""
    return f"{SETTING}.{int(vehicle_id)}" if vehicle_id else SETTING


def order(conn: sqlite3.Connection, vehicle_id: int | None = None) -> list[tuple[str, str]]:
    """All pages that can sit in the bar, in the vehicle's order with their icons. The first four are the bar, the rest lives in More."""
    raw = (db.get_setting(conn, _key(vehicle_id), "") if vehicle_id else "") or db.get_setting(conn, SETTING, "") or ""
    try:
        data = json.loads(raw) if raw else None
    except ValueError:
        data = None
    pairs = [(str(d.get("m")), str(d.get("i"))) for d in data if isinstance(d, dict)] if isinstance(data, list) else list(DEFAULT_SLOTS)
    more = integration_pages(conn, vehicle_id)
    allowed = [m.key for m in choices()] + list(more)
    off = modules.disabled(conn, vehicle_id)
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for key, icon in pairs + [(k, "") for k in allowed]:
        if key in allowed and key not in off and key not in seen:
            seen.add(key)
            out.append((key, icon if icon in icons.ICONS else (more[key]["icon"] if key in more else default_icon(key))))
    return out


def slots(conn: sqlite3.Connection, vehicle_id: int | None = None) -> list[tuple[str, str]]:
    """The pages in the bar (the first four of the order)."""
    return order(conn, vehicle_id)[:MAX_SLOTS]


def save_order(conn: sqlite3.Connection, pairs: list[tuple[str, str]], vehicle_id: int | None = None) -> None:
    more = integration_pages(conn, vehicle_id)
    allowed = {m.key for m in choices()} | set(more)
    clean: list[dict[str, str]] = []
    for key, icon in pairs:
        if key in allowed and key not in {c["m"] for c in clean}:
            clean.append({"m": key, "i": icon if icon in icons.ICONS else (more[key]["icon"] if key in more else default_icon(key))})
    db.set_setting(conn, _key(vehicle_id), json.dumps(clean))


def forget(conn: sqlite3.Connection, vehicle_id: int | None, key: str) -> None:
    """A page that is switched off or removed leaves the saved order; if it comes back it joins at the end and the others keep their places."""
    k = _key(vehicle_id)
    try:
        data = json.loads(db.get_setting(conn, k, "") or "[]")
    except ValueError:
        return
    if isinstance(data, list):
        kept = [d for d in data if not (isinstance(d, dict) and d.get("m") == key)]
        if len(kept) != len(data):
            db.set_setting(conn, k, json.dumps(kept))


def put_in_bar(conn: sqlite3.Connection, vehicle_id: int, key: str, into: bool) -> None:
    """Move a page into the bar (the last of its four places) or out of it (to the top of More); the others keep their order."""
    pairs = [p for p in order(conn, vehicle_id) if p[0] != key]
    icon = next((i for k, i in order(conn, vehicle_id) if k == key), "")
    pairs.insert(MAX_SLOTS - 1 if into else MAX_SLOTS, (key, icon))
    save_order(conn, pairs, vehicle_id)


def reset(conn: sqlite3.Connection, vehicle_id: int | None = None) -> None:
    db.set_setting(conn, _key(vehicle_id), None)


def open_points(conn: sqlite3.Connection, vehicle_id: int | None) -> list[set[str]]:
    """Every open point (overdue or due soon) of a vehicle with the pages that show a dot for it.

    Security collects every open point, Service and Maintenance the due maintenance tasks, Appointments the due appointments.
    Disabled modules never raise a dot; a point whose pages are all disabled is dropped.
    """
    if not vehicle_id:
        return []
    off = modules.disabled(conn, vehicle_id)
    points: list[set[str]] = []
    live = status.rows(conn, vehicle_id)
    if (status.open_closures(live) or status.car_messages(live, lambda key, **kw: key)) and "security" not in off:
        points.append({"security"})
    for item in summary.attention_items(conn, vehicle_id):
        pages = {"security", *(("service", "tasks") if item.kind == "task" else ("appointments",))} - off
        if pages:
            points.append(pages)
    return points


def alerts(conn: sqlite3.Connection, vehicle_id: int | None) -> set[str]:
    """Pages of a vehicle that carry an open point: they get a dot on their tab. Home never has one."""
    return set().union(*open_points(conn, vehicle_id))


def bar(conn: sqlite3.Connection, vehicle_id: int | None, active: str) -> list[dict]:
    """Items of the bar. ``active`` is a module key, ``overview`` (Home) or ``more``.

    Every item carries ``alert``: the tab shows a dot. More shows one only when an open point is not already shown
    by a tab in the bar, i.e. every page that carries it sits in More.
    """
    base = f"/v/{slugs.slug_of(conn, vehicle_id) or vehicle_id}" if vehicle_id else ""
    points = open_points(conn, vehicle_id)
    flagged = set().union(*points)
    more_pages = integration_pages(conn, vehicle_id)
    items = [
        {"key": "overview", "href": base or "/", "icon": "speedometer", "label": "nav.home", "on": active == "overview", "alert": False}
    ]
    if vehicle_id:
        for key, icon in slots(conn, vehicle_id):
            page = more_pages.get(key)
            path = page["path"] if page else modules.BY_KEY[key].path
            items.append(
                {
                    "key": key,
                    "href": f"{base}{path}",
                    "icon": icon,
                    "label": "nav.more" if page else SHORT.get(key, f"tab.{key}"),
                    "text": page["name"] if page else "",  # an integration's page has its own name instead of a translation key
                    "on": active == key,
                    "alert": key in flagged,
                }
            )
    bar_keys = {i["key"] for i in items}
    items.append(
        {
            "key": "more",
            "href": f"{base}/more" if vehicle_id else "/more",
            "icon": "more",
            "label": "nav.more",
            "on": active not in bar_keys,
            "alert": any(not (pages & bar_keys) for pages in points),
        }
    )
    return items
