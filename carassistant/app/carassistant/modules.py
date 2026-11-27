"""UI modules: every feature block of the front end can be switched on or off (like integrations in Home Assistant).

Core modules (overview, vehicle settings) are always on. The disabled set is stored in the ``settings`` table;
the data of a disabled module is kept and reappears when the module is enabled again.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from . import db

SETTING = "modules.disabled"


@dataclass(frozen=True)
class Module:
    key: str
    scope: str  # "vehicle" (tab inside a vehicle) | "global" (entry in the top navigation)
    path: str  # URL suffix below /v/<id> (vehicle) or absolute path (global)
    core: bool = False


MODULES: tuple[Module, ...] = (
    Module("overview", "vehicle", "", core=True),
    Module("service", "vehicle", "/e/service"),
    Module("appointments", "vehicle", "/e/appointments"),
    Module("tasks", "vehicle", "/e/tasks"),
    Module("tires", "vehicle", "/e/tires"),
    Module("mods", "vehicle", "/e/mods"),
    Module("parts", "vehicle", "/e/parts"),
    Module("fuel", "vehicle", "/e/fuel"),
    Module("counters", "vehicle", "/e/counters"),
    Module("trips", "vehicle", "/e/trips"),
    Module("security", "vehicle", "/security"),
    Module("report", "vehicle", "/report"),
    Module("docs", "vehicle", "/docs"),
    Module("manual", "vehicle", "/manual"),
    Module("edit", "vehicle", "/edit", core=True),
    Module("stations", "vehicle", "/stations"),
    Module("map", "vehicle", "/map"),
)
BY_KEY = {m.key: m for m in MODULES}


@dataclass(frozen=True)
class Page:
    key: str  # what a page of a bundle is called: the key of its function, or of a page of its own (fixed, invoices)
    module: str  # the function whose switch it follows
    path: str  # below /v/<id>
    icon: str


# Pages that belong together are ONE entry of the More list with a tab for each page (docs/design.md, 4b: the tab bar). A bundle needs two of its pages
# switched on; with one the page stands alone. The first page of a bundle is where its entry leads.
BUNDLES: tuple[tuple[str, tuple[Page, ...]], ...] = (
    (
        "costs",
        (
            Page("report", "report", "/report", "chart"),
            Page("fixed", "report", "/e/fixed", "calendar-clock"),
            Page("invoices", "report", "/invoices", "file-document-outline"),
        ),
    ),
    (
        "service",
        (
            Page("service", "service", "/e/service", "wrench"),
            Page("tasks", "tasks", "/e/tasks", "tasks"),
            Page("parts", "parts", "/e/parts", "parts"),
            Page("mods", "mods", "/e/mods", "mods"),
        ),
    ),
    ("papers", (Page("docs", "docs", "/docs", "docs"), Page("manual", "manual", "/manual", "book-open-page"))),
)
BUNDLE_OF = {page.key: name for name, pages in BUNDLES for page in pages}
BUNDLE_TITLE = {"costs": "mod.report.name", "service": "bundle.service", "papers": "bundle.papers"}  # the name of an entry of More


def bundle_pages(conn: sqlite3.Connection, vehicle_id: int | None, name: str) -> list[Page]:
    """The pages of a bundle that are switched on for this car (their function is not hidden)."""
    off = disabled(conn, vehicle_id)
    return [page for bundle, pages in BUNDLES if bundle == name for page in pages if page.module not in off]


# What most people need from day one (switched on for a new car, in this order) and what is added when needed (switched off at first).
RECOMMENDED = ("service", "appointments", "fuel", "docs", "security", "report")
ON_REQUEST = ("tasks", "tires", "mods", "parts", "counters", "trips", "manual", "stations", "map")


def apply_recommended(conn: sqlite3.Connection, vehicle_id: int) -> None:
    """A new car starts with the recommended functions; the others are one switch away (More -> Integrations)."""
    db.set_setting(conn, f"modules.off.{vehicle_id}", ",".join(sorted(ON_REQUEST)))


# URL -> module key, enforced centrally in the web middleware.
_ROUTES: tuple[tuple[re.Pattern[str], str | None], ...] = (
    (re.compile(r"^/v/\d+/e/fixed"), "report"),  # the fixed costs are a tab of the cost page: they follow its switch
    (re.compile(r"^/v/\d+/invoices"), "report"),  # so are the invoices
    (re.compile(r"^/v/\d+/e/([a-z_]+)"), None),  # entity key == module key
    (re.compile(r"^/v/\d+/(report)"), None),
    (re.compile(r"^/v/\d+/trips"), "trips"),
    (re.compile(r"^/v/\d+/(docs)"), None),
    (re.compile(r"^/v/\d+/(manual)"), None),
    (re.compile(r"^/v/\d+/(security)"), None),
    (re.compile(r"^/v/\d+/(stations)"), None),
    (re.compile(r"^/v/\d+/(map)(?:/|$)"), None),
    (re.compile(r"^(?:/v/\d+)?/calendar\.ics"), "appointments"),
)


def module_for_path(path: str) -> str | None:
    for pattern, fixed in _ROUTES:
        match = pattern.match(path)
        if match:
            return fixed or match.group(1)
    return None


def vehicle_off(conn: sqlite3.Connection, vehicle_id: int | None) -> set[str]:
    """Functions hidden for ONE vehicle (each car can hide what it does not use)."""
    if not vehicle_id:
        return set()
    raw = db.get_setting(conn, f"modules.off.{vehicle_id}", "") or ""
    return {k for k in raw.split(",") if k in BY_KEY and not BY_KEY[k].core}


def disabled(conn: sqlite3.Connection, vehicle_id: int | None = None) -> set[str]:
    """Switched off everywhere (system level) plus, with a vehicle, what that vehicle hides."""
    raw = db.get_setting(conn, SETTING, "") or ""
    return {k for k in raw.split(",") if k in BY_KEY and not BY_KEY[k].core} | vehicle_off(conn, vehicle_id)


def is_enabled(conn: sqlite3.Connection, key: str, vehicle_id: int | None = None) -> bool:
    return key not in disabled(conn, vehicle_id)


def set_enabled(conn: sqlite3.Connection, key: str, enabled: bool) -> None:
    module = BY_KEY.get(key)
    if module is None or module.core:
        raise KeyError(key)
    off = disabled(conn)
    off.discard(key) if enabled else off.add(key)
    db.set_setting(conn, SETTING, ",".join(sorted(off)))


def set_vehicle_enabled(conn: sqlite3.Connection, vehicle_id: int, key: str, enabled: bool) -> None:
    module = BY_KEY.get(key)
    if module is None or module.core or module.scope != "vehicle":
        raise KeyError(key)
    off = vehicle_off(conn, vehicle_id)
    off.discard(key) if enabled else off.add(key)
    db.set_setting(conn, f"modules.off.{vehicle_id}", ",".join(sorted(off)))


def vehicle_tabs(conn: sqlite3.Connection, vehicle_id: int | None = None) -> list[Module]:
    off = disabled(conn, vehicle_id)
    return [m for m in MODULES if m.scope == "vehicle" and m.key not in off]


def global_nav(conn: sqlite3.Connection) -> list[Module]:
    off = disabled(conn)
    return [m for m in MODULES if m.scope == "global" and m.key not in off]
