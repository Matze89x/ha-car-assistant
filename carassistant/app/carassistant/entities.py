"""Declarative definitions of the simple per-vehicle record types (service book, appointments, fuel, ...).

One ``Entity`` describes a table, its form fields and optional hooks. The generic routes/templates in ``web.py``
render lists and forms from these definitions, so adding a record type needs no new route or template.
"""

from __future__ import annotations

import calendar
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from . import lists, regional


class FormError(ValueError):
    """Invalid user input. ``args[0]`` is an i18n key, ``args[1]`` (optional) the field label key."""


@dataclass(frozen=True)
class Field:
    name: str
    kind: str  # text | textarea | date | time | month_or_date | int | float | bool | choice
    label: str  # i18n key
    required: bool = False
    choices: tuple[str, ...] = ()  # i18n keys are "<name>.<choice>"
    default: object = None
    show: bool = True  # shown as a column in the list view
    step: str = "any"
    dim: str = ""  # dist | vol | price_vol: stored in km / litres / price per litre, shown and entered in the units of Settings -> Region


@dataclass(frozen=True)
class Entity:
    key: str
    table: str
    title: str  # i18n key
    fields: tuple[Field, ...]
    order: str = "date DESC, id DESC"
    prepare: Callable[[dict], dict] | None = None
    row_actions: tuple[str, ...] = ()  # names of extra per-row POST actions handled in web.py
    empty_hint: str = ""
    list_extra: tuple[str, ...] = ()  # derived columns shown in the list but not editable


# ---------------------------------------------------------------- parsing helpers


def parse_float(raw: str, label: str) -> float:
    try:
        return float(raw.strip().replace(",", "."))
    except ValueError:
        raise FormError("err.number", label) from None


def parse_date(raw: str, label: str) -> str:
    try:
        return date.fromisoformat(raw.strip()).isoformat()
    except ValueError:
        raise FormError("err.date", label) from None


def parse_time(raw: str, label: str) -> str:
    try:
        hh, mm = raw.strip().split(":")[:2]
        if not (0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
            raise ValueError
        return f"{int(hh):02d}:{int(mm):02d}"
    except ValueError:
        raise FormError("err.time", label) from None


def parse_month_or_date(raw: str, label: str) -> tuple[str, bool]:
    """``YYYY-MM`` -> last day of that month (month_only=True); ``YYYY-MM-DD`` -> as is."""
    raw = regional.to_iso(raw)
    if len(raw) == 7:
        try:
            year, month = int(raw[:4]), int(raw[5:7])
            return date(year, month, calendar.monthrange(year, month)[1]).isoformat(), True
        except (ValueError, calendar.IllegalMonthError):
            raise FormError("err.date", label) from None
    return parse_date(raw, label), False


def _to_base(f: Field, number: float, units, base: str) -> float:
    """What was typed (in the units shown) -> the base units that are stored."""
    if units is None or not f.dim:
        return number
    if f.dim == "dist":
        return units.from_d(number)
    if f.dim == "vol":
        return units.from_v(number, base)
    return units.from_price_vol(number, base)


def parse_form(entity: Entity, form: dict[str, str], units=None, base: str = "L") -> dict:
    """Validate and convert posted form values (typed in the units shown: ``units``). Unknown keys are ignored."""
    values: dict = {}
    for f in entity.fields:
        raw = (form.get(f.name) or "").strip()
        if f.kind == "bool":
            values[f.name] = 1 if form.get(f.name) in ("1", "on", "true") else 0
            continue
        if raw == "":
            if f.required:
                raise FormError("err.required", f.label)
            values[f.name] = f.default if f.kind == "choice" else None
            continue
        if f.kind in ("text", "textarea"):
            values[f.name] = raw
        elif f.kind == "date":
            values[f.name] = parse_date(raw, f.label)
        elif f.kind == "time":
            values[f.name] = parse_time(raw, f.label)
        elif f.kind == "month_or_date":
            values[f.name], values["month_only"] = parse_month_or_date(raw, f.label)
        elif f.kind == "int":
            number = parse_float(raw, f.label)
            if number < 0:
                raise FormError("err.negative", f.label)
            values[f.name] = round(_to_base(f, number, units, base))
        elif f.kind == "float":
            number = parse_float(raw, f.label)
            if number < 0:
                raise FormError("err.negative", f.label)
            values[f.name] = round(_to_base(f, number, units, base), 6)
        elif f.kind == "choice":
            if raw not in f.choices:
                raise FormError("err.choice", f.label)
            values[f.name] = raw
    if entity.prepare:
        values = entity.prepare(values)
    return values


# ---------------------------------------------------------------- hooks


def _fuel_prepare(values: dict) -> dict:
    """Derive the missing one of price per unit / total price."""
    amount, unit, total = values.get("amount"), values.get("price_per_unit"), values.get("price_total")
    if amount and unit and not total:
        values["price_total"] = round(amount * unit, 2)
    elif amount and total and not unit:
        values["price_per_unit"] = round(total / amount, 3)
    return values


def _appointment_prepare(values: dict) -> dict:
    values.setdefault("month_only", 0)
    values["month_only"] = 1 if values["month_only"] else 0
    return values


MAX_TRIP_KM = 3000


def _trip_prepare(values: dict) -> dict:
    start, end = values.get("start_km"), values.get("end_km")
    if start is not None and end is not None:
        if end < start:
            raise FormError("err.km_order", "f.end_km")
        if end - start > MAX_TRIP_KM:
            raise FormError("err.trip_far", "f.end_km")  # one trip of more than that is a typo (a missing digit, a swapped field)
        values["distance_km"] = float(end - start)
    else:
        values["distance_km"] = None
    day = values.get("date")
    if day and str(day) > date.today().isoformat():
        raise FormError("err.trip_future", "f.date")  # a trip that has not happened yet
    a, z = values.get("start_time"), values.get("end_time")
    if a and z and z < a and day and str(day) == date.today().isoformat():
        raise FormError("err.time_order", "f.end_time")
    return values


def _counter_prepare(values: dict) -> dict:
    start, end = values.get("start_km"), values.get("end_km")
    if start is None:
        raise FormError("err.required", "f.start_km")
    if end is not None and end < start:
        raise FormError("err.km_order", "f.end_km")
    if values.get("end_date") and values.get("start_date") and values["end_date"] < values["start_date"]:
        raise FormError("err.date_order", "f.end_date")
    return values


COUNTER_KINDS = ("tax", "business", "private", "other")
SEASONS = ("summer", "winter", "allseason")
TRIP_CATEGORIES = ("private", "business", "commute")
KINDS = ("inspection", "service", "insurance", "tax", "other")
FUEL_TYPES = ("petrol", "diesel", "lpg", "cng", "hybrid", "electric")
SECOND_FUELS = ("lpg", "cng")  # a bi-fuel car (petrol or diesel plus gas) has one of these as its second fuel
DRIVETRAINS = ("fwd", "rwd", "awd")
TRANSMISSIONS = ("manual", "automatic", "dct", "cvt")
BODY_TYPES = ("sedan", "wagon", "hatchback", "suv", "coupe", "convertible", "van", "pickup")

SERVICE = Entity(
    key="service",
    table="service",
    title="service.title",
    fields=(
        Field("date", "date", "f.date", required=True),
        Field("odometer_km", "int", "f.odometer", dim="dist", step="1"),
        Field("title", "text", "f.work", required=True),
        Field("workshop", "text", "f.workshop"),
        Field("cost", "float", "f.cost"),
        Field("notes", "textarea", "f.notes", show=False),
    ),
    empty_hint="service.empty",
)

APPOINTMENTS = Entity(
    key="appointments",
    table="appointments",
    title="appointments.title",
    fields=(
        Field("kind", "choice", "f.kind", choices=KINDS, default="inspection"),
        Field("title", "text", "f.title", required=True),
        Field("due_date", "month_or_date", "f.due", required=True),
        Field("notes", "textarea", "f.notes", show=False),
        Field("done", "bool", "f.done"),
    ),
    order="done ASC, due_date ASC",
    prepare=_appointment_prepare,
    empty_hint="appointments.empty",
)

MODS = Entity(
    key="mods",
    table="mods",
    title="mods.title",
    fields=(
        Field("date", "date", "f.date", required=True),
        Field("odometer_km", "int", "f.odometer", dim="dist", step="1"),
        Field("title", "text", "f.work", required=True),
        Field("cost", "float", "f.cost"),
        Field("notes", "textarea", "f.notes", show=False),
    ),
    empty_hint="mods.empty",
)

FUEL = Entity(
    key="fuel",
    table="fuel",
    title="fuel.title",
    fields=(
        Field("date", "date", "f.date", required=True),
        Field("odometer_km", "int", "f.odometer", dim="dist", step="1"),
        Field("amount", "float", "f.amount", dim="vol"),
        Field("price_per_unit", "float", "f.price_unit", step="0.001", dim="price_vol"),
        Field("price_total", "float", "f.price_total", step="0.01"),
        Field("full_tank", "bool", "f.full_tank", default=1),
        Field("fuel_kind", "choice", "f.fuel_kind", choices=("main", "second"), default="main", show=False),
        Field("station", "text", "f.station", show=False),
        Field("notes", "textarea", "f.notes", show=False),
    ),
    order="date DESC, COALESCE(odometer_km, 0) DESC, id DESC",
    prepare=_fuel_prepare,
    empty_hint="fuel.empty",
)

TIRES = Entity(
    key="tires",
    table="tires",
    title="tires.title",
    fields=(
        Field("name", "text", "f.name", required=True),
        Field("season", "choice", "f.season", choices=SEASONS, default="summer"),
        Field("size", "text", "f.size"),
        Field("storage", "text", "f.storage"),
        Field("rear_size", "text", "f.rear_size", show=False),
        Field("notes", "textarea", "f.notes", show=False),
    ),
    order="mounted DESC, id ASC",
    row_actions=("mount",),
    empty_hint="tires.empty",
)

TASKS = Entity(
    key="tasks",
    table="tasks",
    title="tasks.title",
    fields=(
        Field("title", "text", "f.title", required=True),
        Field("interval_km", "int", "f.interval_km", dim="dist", step="1"),
        Field("interval_months", "int", "f.interval_months", step="1"),
        Field("keywords", "text", "f.keywords", show=False),
        Field("last_date", "date", "f.last_date"),
        Field("last_km", "int", "f.last_km", dim="dist", step="1"),
        Field("muted", "bool", "f.muted", show=False),
        Field("notes", "textarea", "f.notes", show=False),
    ),
    order="title COLLATE NOCASE",
    row_actions=("done",),
    empty_hint="tasks.empty",
)

TRIPS = Entity(
    key="trips",
    table="trips",
    title="trips.title",
    fields=(
        Field("date", "date", "f.date", required=True),
        Field("start_time", "time", "f.start_time", show=False),
        Field("end_time", "time", "f.end_time", show=False),
        Field("start_km", "int", "f.start_km", dim="dist", step="1"),
        Field("end_km", "int", "f.end_km", dim="dist", step="1"),
        Field("start_place", "text", "f.start_place"),
        Field("end_place", "text", "f.end_place"),
        Field("category", "choice", "f.category", choices=TRIP_CATEGORIES, default="private"),
        Field("purpose", "text", "f.purpose"),
    ),
    prepare=_trip_prepare,
    list_extra=("distance_km",),
    empty_hint="trips.empty",
)

COUNTERS = Entity(
    key="counters",
    table="counters",
    title="counters.title",
    fields=(
        Field("name", "text", "f.name", required=True),
        Field("kind", "choice", "f.kind", choices=COUNTER_KINDS, default="tax"),
        Field("start_date", "date", "f.start_date", required=True),
        Field("start_km", "int", "f.start_km", dim="dist", required=True, step="1"),
        Field("end_date", "date", "f.end_date"),
        Field("end_km", "int", "f.end_km", dim="dist", step="1"),
        Field("notes", "textarea", "f.notes", show=False),
    ),
    order="start_date DESC, id DESC",
    prepare=_counter_prepare,
    list_extra=("driven_km",),
    empty_hint="counters.empty",
)

PARTS = Entity(
    key="parts",
    table="parts",
    title="parts.title",
    fields=(
        Field("date", "date", "f.purchase_date", required=True),
        Field("name", "text", "f.part", required=True),
        Field("part_number", "text", "f.part_number"),
        Field("manufacturer", "text", "f.manufacturer", show=False),
        Field("shop", "text", "f.shop"),
        Field("quantity", "float", "f.quantity", show=False),
        Field("cost", "float", "f.cost"),
        Field("installed", "bool", "f.installed"),
        Field("installed_km", "int", "f.installed_km", dim="dist", step="1", show=False),
        Field("notes", "textarea", "f.notes", show=False),
    ),
    empty_hint="parts.empty",
)

ENTITIES: dict[str, Entity] = {e.key: e for e in (SERVICE, APPOINTMENTS, MODS, FUEL, TIRES, TASKS, TRIPS, COUNTERS, PARTS)}


def insert(conn: sqlite3.Connection, entity: Entity, vehicle_id: int, values: dict) -> int:
    cols = ["vehicle_id", *values.keys()]
    sql = f"INSERT INTO {entity.table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})"
    return conn.execute(sql, [vehicle_id, *values.values()]).lastrowid


def update(conn: sqlite3.Connection, entity: Entity, vehicle_id: int, row_id: int, values: dict) -> None:
    sets = ", ".join(f"{k} = ?" for k in values)
    conn.execute(
        f"UPDATE {entity.table} SET {sets} WHERE id = ? AND vehicle_id = ?",
        [*values.values(), row_id, vehicle_id],
    )


def delete(conn: sqlite3.Connection, entity: Entity, vehicle_id: int, row_id: int) -> None:
    conn.execute(f"DELETE FROM {entity.table} WHERE id = ? AND vehicle_id = ?", (row_id, vehicle_id))


def count(conn: sqlite3.Connection, entity: Entity, vehicle_id: int) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {entity.table} WHERE vehicle_id = ?", (vehicle_id,)).fetchone()[0]


def rows(conn: sqlite3.Connection, entity: Entity, vehicle_id: int, page: int = 1, edit_id: int | None = None) -> list[sqlite3.Row]:
    """One page of records, in the entity's order. A record being edited is always included, even from another page."""
    found = conn.execute(
        f"SELECT * FROM {entity.table} WHERE vehicle_id = ? ORDER BY {entity.order} LIMIT ? OFFSET ?",
        (vehicle_id, lists.size(), (max(page, 1) - 1) * lists.size()),
    ).fetchall()
    if edit_id is not None and all(r["id"] != edit_id for r in found):
        extra = conn.execute(f"SELECT * FROM {entity.table} WHERE vehicle_id = ? AND id = ?", (vehicle_id, edit_id)).fetchone()
        if extra is not None:
            found.insert(0, extra)
    return found


def previous_date(conn: sqlite3.Connection, entity: Entity, vehicle_id: int, page: int, date_key: str) -> str | None:
    """The date of the record just before the batch of ``page`` (so a group continuing over the border gets no second heading)."""
    if page <= 1:
        return None
    row = conn.execute(
        f"SELECT {date_key} FROM {entity.table} WHERE vehicle_id = ? ORDER BY {entity.order} LIMIT 1 OFFSET ?",
        (vehicle_id, (page - 1) * lists.size() - 1),
    ).fetchone()
    return row[0] if row else None


__all__ = ["ENTITIES", "Entity", "Field", "FormError", "parse_form"]


def group_by_month(rows, date_key: str, lang: str, sum_keys: tuple[str, ...] = ()) -> list[dict]:
    """Rows (newest first) grouped by month: ``{key, title, rows, sums}``."""
    from .trips import MONTHS

    names = MONTHS.get(lang, MONTHS["en"])
    groups: dict[str, dict] = {}
    for row in rows:
        key = (row[date_key] or "")[:7] or "0000-00"
        month = int(key[5:7] or 0)
        group = groups.setdefault(
            key,
            {
                "key": key,
                "title": f"{names[month - 1]} {key[:4]}" if 1 <= month <= 12 else key,
                "rows": [],
                "sums": dict.fromkeys(sum_keys, 0.0),
            },
        )
        group["rows"].append(row)
        for k in sum_keys:
            group["sums"][k] += row[k] or 0
    return list(groups.values())


# the icon of an extra-work card follows what the job is about (words in English and German; anything else gets the wrench)
TASK_ICONS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("brake", "brems"), "car-brake-parking"),
    (("oil", "öl"), "oil"),
    (("battery", "batterie", "akku"), "battery"),
    (("tyre", "tire", "reifen"), "tires"),
    (("filter",), "engine-outline"),
    (("coolant", "kühl", "antifreeze", "frost"), "water-percent"),
    (("spark", "glow", "zünd", "glüh", "bulb", "lamp", "light", "licht", "birne"), "lightning-bolt"),
    (("gearbox", "getriebe", "dsg", "atf", "clutch", "kupplung"), "car-shift-pattern"),
    (("belt", "riemen"), "timer-outline"),
    (("fuel", "diesel", "kraftstoff", "tank"), "gas-station"),
    (("cabin", "pollen", "innenraum", "klima", "air con"), "snowflake"),
    (("wash", "wasch", "clean", "reinig", "polish", "wax"), "water-percent"),
    (("inspection", "tüv", "hu ", "service"), "wrench"),
)


def task_icon(title: str, keywords: str = "") -> str:
    text = f"{title} {keywords}".lower()
    for words, icon in TASK_ICONS:
        if any(w in text for w in words):
            return icon
    return "wrench"
