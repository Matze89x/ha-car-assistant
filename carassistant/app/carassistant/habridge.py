"""The Home Assistant plugin: values of entities of Home Assistant become values of a car (docs/home-assistant.md).

A plugin whose ``plugin.json`` has ``bridge`` offers, on its settings page, every interface of the Plugin API (habridge_slots.py) as a place to bind an
ENTITY of Home Assistant - for each car on its own. The package never names an entity and never sees the Home Assistant token: the administrator chooses
the entities, the APP reads them (one request for all of them, ``ha.all_states``) every few seconds and hands what it found to the same intake as
``POST /api/v1/vehicles/<id>/data`` (``connectors.ingest``), as that plugin. What it does on the way:

* a unit is converted (miles, psi, Fahrenheit, watts, minutes ...) into the one the Plugin API stores;
* a yes / no is read from what the entity says (a lock, a door sensor, a cover, a climate entity, a status text of a wallbox) - the entity says what its
  "on" means, the slot says what it needs; the person can turn it round or name the states that mean yes;
* what is sent carries the time Home Assistant gives (``measured_at``), so the NEWER measurement of several sources wins;
* only what changed is sent, an entity that is unavailable is skipped, a failing value never blocks the others;
* the interfaces a plugin binds are *taken* for it (claims.py): no other source of that car fills them at the same time.

Nothing here runs code of the package: ``bridge`` only chooses which of the slots are offered."""

from __future__ import annotations

import json
import logging
import math
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime

from . import addons, claims, config, connectors, db, events, ha, halive, i18n, linkmap, summary
from . import habridge_slots as cat
from . import vin as vin_info

log = logging.getLogger("carassistant")

ENTITY = re.compile(r"[a-z][a-z0-9_]{0,40}\.[a-z0-9_]{1,100}")  # <domain>.<object id> as Home Assistant writes it
ATTRIBUTE = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}")
GONE = {"unavailable", "unknown", "none", "null", "nan", ""}  # states that carry no value
EVERY = (10, 3600, 30)  # seconds between two readings: least, most, default
MAX_BACKOFF = 600  # when Home Assistant cannot be asked, or a round fails: the longest wait before the next try
MAX_YES = 12  # states a person may name as "yes"
SCALE_LIMIT = 1e9
SOURCE = "bridge"  # what the log lines of the plugin call their source
ODOMETER_LOW = (
    "odometer_km: Home Assistant reports less than the odometer Car Assistant already knows (the highest of all readings and entries - a fill-up, "
    "a service, a trip). The odometer only grows, so this reading was not taken; it counts again as soon as it is higher."
)  # (no figures: the same words are said once, not with every kilometre driven)


# ------------------------------------------------------------------ units
# the unit of a slot -> {unit of the entity (lower case, no spaces): (factor, offset)}: value in the slot's unit = value * factor + offset;
# ("inv", k) = k / value (a consumption written the other way round: km per litre, miles per gallon)
UNITS: dict[str, dict[str, tuple]] = {
    "km": {"km": (1, 0), "m": (0.001, 0), "cm": (1e-5, 0), "mi": (1.609344, 0), "mile": (1.609344, 0), "miles": (1.609344, 0)}
    | {"ft": (0.0003048, 0), "yd": (0.0009144, 0)},
    "km/h": {"km/h": (1, 0), "kmh": (1, 0), "kph": (1, 0), "mph": (1.609344, 0), "m/s": (3.6, 0), "kn": (1.852, 0), "kt": (1.852, 0)}
    | {"ft/s": (1.09728, 0)},
    "kW": {"kw": (1, 0), "w": (0.001, 0), "mw": (1000, 0), "hp": (0.7457, 0)},
    "bar": {"bar": (1, 0), "mbar": (0.001, 0), "hpa": (0.001, 0), "kpa": (0.01, 0), "pa": (1e-5, 0), "cbar": (0.01, 0)}
    | {"psi": (0.0689475729, 0), "inhg": (0.0338638866, 0), "mmhg": (0.00133322368, 0)},
    # litres in the tank - or kWh in the battery of an electric car (the Plugin API keeps that amount in the same field)
    "l": {"l": (1, 0), "ml": (0.001, 0), "m³": (1000, 0), "m3": (1000, 0), "gal": (3.785411784, 0), "kwh": (1, 0), "wh": (0.001, 0)}
    | {"mwh": (1000, 0)},
    "°C": {"°c": (1, 0), "°f": (5 / 9, -160 / 9), "k": (1, -273.15)},
    "V": {"v": (1, 0), "mv": (0.001, 0), "kv": (1000, 0)},
    "min": {"min": (1, 0), "s": (1 / 60, 0), "ms": (1 / 60000, 0), "h": (60, 0), "d": (1440, 0)},
    "d": {"d": (1, 0), "h": (1 / 24, 0), "min": (1 / 1440, 0), "s": (1 / 86400, 0)},
    "%": {"%": (1, 0)},
    "°": {"°": (1, 0), "deg": (1, 0), "rad": (57.29577951308232, 0)},
    "l/100km": {"l/100km": (1, 0), "kwh/100km": (1, 0), "wh/km": (0.1, 0), "kwh/km": (100, 0), "l/km": (100, 0)}
    | {"km/l": ("inv", 100), "km/kwh": ("inv", 100), "mi/kwh": ("inv", 160.9344)}
    | {"mpg": ("inv", 235.214583), "mpg(us)": ("inv", 235.214583), "mpg(uk)": ("inv", 282.480936), "mpg(imp)": ("inv", 282.480936)},
}
# the units the options of a slot offer (the rest of the table is understood when an entity brings it)
UNIT_CHOICES: dict[str, tuple[str, ...]] = {
    "km": ("km", "mi", "m"),
    "km/h": ("km/h", "mph", "m/s"),
    "kW": ("kW", "W", "MW"),
    "bar": ("bar", "kPa", "psi", "hPa", "mbar"),
    "l": ("l", "ml", "gal", "kWh", "Wh"),
    "°C": ("°C", "°F", "K"),
    "V": ("V", "mV"),
    "min": ("min", "s", "h", "d"),
    "d": ("d", "h", "min"),
    "l/100km": ("l/100km", "kWh/100km", "Wh/km", "km/l", "mpg", "mi/kWh"),
}
MAX_UNIT_TEXT = 16


def _norm(unit: str) -> str:
    return re.sub(r"\s+", "", str(unit or "")).lower()


def convert(slot_unit: str, from_unit: str, value: float) -> float | None:
    """``value`` given in ``from_unit`` as a number of ``slot_unit`` - or None when that unit cannot be turned into it. No unit = already that unit."""
    unit = _norm(from_unit)
    if unit in ("", _norm(slot_unit)):
        return value
    rule = UNITS.get(slot_unit, {}).get(unit)
    if rule is None:
        return None
    if rule[0] == "inv":
        return rule[1] / value if value else None
    return value * rule[0] + rule[1]


# ------------------------------------------------------------------ what an entity says


class _Problem(Exception):
    """Nothing could be read: ``problem`` is a short word (the page and the log say it in their own words), ``detail`` what to show with it."""

    def __init__(self, problem: str, detail: str = ""):
        super().__init__(problem)
        self.problem, self.detail = problem, detail


@dataclass
class Reading:
    ok: bool = False
    value: object = None  # a number (in the unit of the slot), True / False, a text, or (lat, lon)
    raw: str = ""  # the state as Home Assistant gave it (with its unit): what the page shows beside a converted value
    at: str | None = None  # when Home Assistant says the entity reported (UTC, ISO)
    problem: str = ""  # why there is no value: ha | gone | unavailable | attribute | number | unit | range | state | truth | coords | vin
    detail: str = ""
    converted: bool = False  # the number was changed on the way (unit, scale, offset)
    text: str = ""  # a warning: the words it shows


def _source(state: dict, opts: dict) -> tuple[object, str]:
    """``(the value, its unit)`` a slot reads: the state of the entity - or the attribute the person named. Raises ``_Problem`` when there is none."""
    attrs = state.get("attributes") or {}
    attribute = opts.get("attribute")
    if attribute:
        if attribute not in attrs:
            raise _Problem("attribute", attribute)
        value, unit = attrs[attribute], ""
    else:
        value, unit = state.get("state"), str(attrs.get("unit_of_measurement") or "")
    if value is None or str(value).strip().lower() in GONE:
        raise _Problem("unavailable")
    return value, unit


def _number_of(value) -> float:
    if isinstance(value, bool):
        raise _Problem("number", "yes / no")
    if isinstance(value, int | float):
        number = float(value)
    else:
        text = str(value).strip()
        if text.count(",") == 1 and "." not in text:
            text = text.replace(",", ".")
        try:
            number = float(text)
        except ValueError:
            raise _Problem("number", text[:30]) from None
    if not math.isfinite(number):
        raise _Problem("number", str(value)[:30])
    return number


def _until(text: str, unit: str) -> float | None:
    """A date or a time of an entity (device class date / timestamp) as days or minutes from now: for 'minutes left' and 'days until the service'."""
    if unit not in ("min", "d") or not re.match(r"\d{4}-\d{2}-\d{2}", text.strip()):
        return None
    text = text.strip().replace("Z", "+00:00")
    try:
        if len(text) == 10:  # a date
            target = date.fromisoformat(text)
            if unit == "d":
                return float((target - date.today()).days)
            return (datetime.combine(target, datetime.min.time()) - datetime.now()).total_seconds() / 60
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    now = datetime.now(moment.tzinfo)
    if unit == "d":
        return float((moment.date() - now.date()).days)
    return (moment - now).total_seconds() / 60


def _limits(slot: cat.Slot) -> tuple[float, float]:
    if slot.kind == "tyre":
        return 0.0, 8.0
    if slot.key == "position_lat":
        return -90.0, 90.0
    if slot.key == "position_lon":
        return -180.0, 180.0
    if slot.field == "odometer_km":
        return 1.0, float(connectors.MAX_ODOMETER_KM)
    _live, low, high = connectors.NUMBERS[slot.field]
    return float(low), float(high)


def read_number(slot: cat.Slot, state: dict, opts: dict) -> Reading:
    value, entity_unit = _source(state, opts)
    chosen = str(opts.get("unit") or "auto")
    number = _until(str(value), slot.unit)
    if number is None:
        number = _number_of(value)
        if chosen == "raw":
            converted = False
        else:
            from_unit = entity_unit if chosen == "auto" else chosen
            turned = convert(slot.unit, from_unit, number)
            if turned is None:
                raise _Problem("unit", from_unit)
            converted = _norm(from_unit) not in ("", _norm(slot.unit))
            number = turned
    else:
        converted = True
    scale, offset = opts.get("scale"), opts.get("offset")
    if scale is not None or offset is not None:
        number = number * (1 if scale is None else scale) + (offset or 0)
        converted = True
    if slot.field == "heading_deg":
        number %= 360
    low, high = _limits(slot)
    if not low <= number <= high:
        raise _Problem("range", f"{number:g} ({low:g} … {high:g})")
    number = round(number, 2 if slot.kind == "tyre" else 6 if slot.kind == "coord" else 3)
    raw = f"{value} {entity_unit}".strip() if converted else ""
    return Reading(ok=True, value=number, raw=raw, converted=converted)


# what a word of a state says: (what it is about, yes / no); None as the subject = a plain on / off
WORDS: dict[str, tuple[str | None, bool]] = {
    **{
        w: (None, True)
        for w in ("on", "true", "yes", "1", "active", "enabled", "engaged", "running", "applied", "set", "detected", "problem")
    },
    **{w: (None, False) for w in ("off", "false", "no", "0", "inactive", "disabled", "released", "clear", "ok")},
    **{w: ("locked", True) for w in ("locked", "secured", "locking")},
    **{w: ("locked", False) for w in ("unlocked", "unsecured", "unlocking", "jammed_open")},
    **{w: ("open", True) for w in ("open", "opened", "opening", "tilted", "ajar", "vent")},
    **{w: ("open", False) for w in ("closed", "shut", "closing_done")},
    **{w: ("plugged", True) for w in ("plugged", "plugged_in", "connected", "cable_connected", "preparing")},
    **{w: ("plugged", False) for w in ("unplugged", "not_plugged", "disconnected", "not_connected", "cable_disconnected")},
    **{w: ("charging", True) for w in ("charging",)},
    **{w: ("charging", False) for w in ("not_charging", "charge_complete", "charged", "complete", "completed", "finished", "stopped")},
    **{w: ("climate", True) for w in ("heat", "cool", "heating", "cooling", "heat_cool", "auto", "ventilating", "defrost", "fan_only")},
}
# what a device class of a binary sensor is about (the others are a plain on / off)
CLASS_TRUTH = {
    "door": "open",
    "window": "open",
    "garage_door": "open",
    "opening": "open",
    "plug": "plugged",
    "battery_charging": "charging",
}


def _meaning(domain: str, dclass: str, key: str) -> tuple[str | None, bool | None]:
    """What the state ``key`` of an entity says: ``(what it is about, yes / no)``; no = None when the state is no word that is known."""
    if domain == "lock":
        if key in ("locked", "locking"):
            return "locked", True
        return "locked", False if key in ("unlocked", "unlocking", "open", "opening") else None
    if domain == "cover":
        if key == "closed":
            return "open", False
        return "open", True if key in ("open", "opening", "closing", "stopped") else None
    if domain == "climate":
        return "climate", key != "off"
    if domain == "binary_sensor" and key in ("on", "off"):
        if dclass == "lock":  # Home Assistant: for this class ``on`` means UNLOCKED
            return "locked", key == "off"
        return CLASS_TRUTH.get(dclass), key == "on"
    return WORDS.get(key, (None, None))


def read_flag(slot: cat.Slot, state: dict, opts: dict) -> Reading:
    value, _unit = _source(state, opts)
    text = str(value).strip()
    key = re.sub(r"[\s-]+", "_", text.lower())
    if opts.get("yes"):  # the person named the states that mean yes: every other state is no
        flag = key in {re.sub(r"[\s-]+", "_", w.lower()) for w in opts["yes"]}
    elif opts.get("above") is not None:  # a number as a yes / no: a charging power above 0 means charging
        flag = _number_of(value) > opts["above"]
    else:
        domain = str(state.get("entity_id") or "").split(".")[0]
        subject, flag = _meaning(domain, str((state.get("attributes") or {}).get("device_class") or ""), key)
        if flag is None:
            raise _Problem("state", text[:30])
        if subject is not None and slot.truth not in ("any", subject):
            raise _Problem("truth", subject)
    if opts.get("invert"):
        flag = not flag
    return Reading(ok=True, value=flag, raw=text[:40])


def read_text(slot: cat.Slot, state: dict, opts: dict) -> Reading:
    value, _unit = _source(state, opts)
    try:
        text = vin_info.clean(str(value))
    except ValueError:
        text = None
    if not text:
        raise _Problem("vin", str(value)[:20])
    return Reading(ok=True, value=text, raw=text)


def read_position(slot: cat.Slot, state: dict, opts: dict) -> Reading:
    attrs = state.get("attributes") or {}
    lat, lon = attrs.get("latitude"), attrs.get("longitude")
    if lat is None or lon is None:
        found = re.fullmatch(
            r"\s*(-?\d{1,3}(?:\.\d+)?)\s*[,; ]\s*(-?\d{1,3}(?:\.\d+)?)\s*", str(state.get("state"))
        )  # a sensor "52.5, 13.4"
        if not found:
            raise _Problem("unavailable" if str(state.get("state")).strip().lower() in GONE else "coords")
        lat, lon = found.group(1), found.group(2)
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        raise _Problem("coords") from None
    if not (math.isfinite(lat) and math.isfinite(lon)) or not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
        raise _Problem("coords")  # (0, 0) is what a tracker without a fix reports
    return Reading(ok=True, value=(round(lat, 6), round(lon, 6)), raw=f"{lat:.5f}, {lon:.5f}")


READERS = {
    "number": read_number,
    "tyre": read_number,
    "coord": read_number,
    "bool": read_flag,
    "closure": read_flag,
    "warning": read_flag,
    "text": read_text,
    "position": read_position,
}


def read(slot: cat.Slot, entity: str, opts: dict, states: dict[str, dict] | None, name: str = "") -> Reading:
    """What one entity says for one slot. Never raises: a reading that is not usable says why (``problem``)."""
    if states is None:
        return Reading(problem="ha")
    state = states.get(entity)
    if state is None:
        return Reading(problem="gone")
    at = connectors.moment(state.get("last_reported") or state.get("last_updated"))
    try:
        reading = READERS[slot.kind](slot, state, opts)
    except _Problem as exc:
        return Reading(problem=exc.problem, detail=exc.detail, at=at)
    reading.at = at
    if slot.kind == "warning":
        friendly = str((state.get("attributes") or {}).get("friendly_name") or "")
        reading.text = " ".join((opts.get("text") or friendly or name.replace("_", " ")).split())[: connectors.MAX_WARNING_TEXT]
    return reading


# ------------------------------------------------------------------ the bindings of an install


def split(row_key: str) -> tuple[cat.Slot | None, str]:
    """``"doors.front_left"`` -> (the slot ``doors``, ``"front_left"``); ``"odometer_km"`` -> (the slot, "")."""
    key, _dot, name = row_key.partition(".")
    return cat.BY_KEY.get(key), name


def offered(manifest: dict) -> list[cat.Slot]:
    """The slots a package offers: its ``bridge.slots`` when it names some, else the slots of its ``bridge.groups``, else all."""
    spec = manifest.get("bridge") or {}
    if spec.get("slots"):
        return [s for s in cat.SLOTS if s.key in spec["slots"]]
    if spec.get("groups"):
        return [s for s in cat.SLOTS if s.group in spec["groups"]]
    return list(cat.SLOTS)


def bindings(conn, addon_pk: int) -> dict[str, dict]:
    """``{row key: {"entity": ..., "options": {...}}}`` of an install (a row of a list is ``doors.front_left``)."""
    out: dict[str, dict] = {}
    for row in conn.execute("SELECT slot, entity, options FROM ha_bindings WHERE addon_pk = ? ORDER BY rowid", (addon_pk,)):
        try:
            options = json.loads(row["options"] or "{}")
        except ValueError:
            options = {}
        out[row["slot"]] = {"entity": row["entity"], "options": options if isinstance(options, dict) else {}}
    return out


def fields_bound(bound: dict[str, dict]) -> set[str]:
    """The interfaces (fields of the Plugin API) these bindings fill."""
    return {slot.field for key in bound if (slot := split(key)[0]) is not None}


def clean_stored(slot_key, entity, options) -> dict | None:
    """A binding as a backup file holds it, checked again (the file may be from anywhere): ``{"entity", "options"}`` or None when it is not usable."""
    if not isinstance(slot_key, str) or not isinstance(entity, str) or not ENTITY.fullmatch(entity):
        return None
    slot, name = split(slot_key)
    if slot is None or (slot.kind in cat.LIST_KINDS) != bool(name) or (name and not connectors.CLOSURE_NAME.fullmatch(name)):
        return None
    try:
        raw = json.loads(options) if isinstance(options, str) else options
    except ValueError:
        raw = {}
    raw = raw if isinstance(raw, dict) else {}
    form = {
        f"x.{k}": (", ".join(map(str, v)) if isinstance(v, list) else ("1" if v is True else str(v)))
        for k, v in raw.items()
        if v is not False
    }
    cleaned, why = parse_options(form, "x.", slot)
    return {"entity": entity, "options": {} if why else cleaned}


def interval(addon: dict) -> int:
    """Seconds between two readings: the setting ``every`` of the install, else what the package says, else 30."""
    spec = (addon["m"].get("bridge") or {}).get("every", EVERY[2])
    value = (addon.get("vals") or {}).get("every")
    try:
        seconds = int(value) if value not in (None, "") else int(spec)
    except (TypeError, ValueError):
        seconds = EVERY[2]
    return min(EVERY[1], max(EVERY[0], seconds))


# ------------------------------------------------------------------ from readings to one delivery


def _position_of_halves(readings: dict[str, Reading]) -> dict[str, Reading]:
    """Two sensors of their own (latitude, longitude) make the position - but only while no tracker is chosen."""
    out = {k: r for k, r in readings.items() if k not in ("position_lat", "position_lon")}
    if "position" in readings:
        return out
    lat, lon = readings.get("position_lat"), readings.get("position_lon")
    if lat is None or lon is None:
        return out
    if lat.ok and lon.ok:
        times = [t for t in (lat.at, lon.at) if t]
        out["position"] = Reading(
            ok=True, value=(lat.value, lon.value), raw=f"{lat.value:.5f}, {lon.value:.5f}", at=max(times) if times else None
        )
    else:
        out["position"] = lat if not lat.ok else lon  # what is wrong with one half is what the page shows
    return out


def build(readings: dict[str, Reading]) -> list[tuple[str | None, dict]]:
    """The deliveries for the Plugin API, one for each time of measurement, the oldest first (a newer value of a key makes an older one of the same key
    obsolete: ``connectors._store`` keeps the newer one). ``readings`` = the rows that are to be sent."""
    groups: dict[str | None, dict] = {}
    for key, reading in readings.items():
        slot, name = split(key)
        if slot is None or not reading.ok:
            continue
        data = groups.setdefault(reading.at, {})
        if slot.kind == "position":
            data["position"] = {"lat": reading.value[0], "lon": reading.value[1]}
        elif slot.kind == "tyre":
            data.setdefault("tyre_pressure_bar", {})[cat.TYRE_WHEEL[slot.key]] = reading.value
        elif slot.kind == "closure":
            data.setdefault(slot.field, {})[name] = bool(reading.value)
        elif slot.kind == "warning":
            data.setdefault("warnings", {})[name] = reading.text if reading.value else None  # null removes the code again
        else:
            data[slot.field] = reading.value
    return [(at, groups[at]) for at in sorted(groups, key=lambda a: a or "9999")]


def deliver(conn, addon: dict, at: str | None, data: dict) -> tuple[dict[str, str], dict[str, str]]:
    """One delivery to the intake of the Plugin API, as this plugin: ``(what became of each field, what was refused and why)``. When the intake refuses
    the whole delivery because of one value, the others are tried one by one - one bad value never keeps the rest from the car."""
    name = addon["m"].get("name") or addon["addon_id"]
    stamp = {"measured_at": at} if at else {}
    try:
        return connectors.ingest(conn, addon["vehicle_id"], {**data, **stamp}, name, caller=addon["id"]), {}
    except connectors.ApiError as exc:
        if len(data) <= 1:
            return {}, {next(iter(data), "?"): exc.message}
    done: dict[str, str] = {}
    refused: dict[str, str] = {}
    for field, value in data.items():
        try:
            done.update(connectors.ingest(conn, addon["vehicle_id"], {field: value, **stamp}, name, caller=addon["id"]))
        except connectors.ApiError as exc:
            refused[field] = exc.message
    return done, refused


# ------------------------------------------------------------------ one reading of an install, and the schedule

_state: dict[
    int, dict
] = {}  # install -> what the loop remembers: next (when due, monotonic), sent (row -> (value, time)), said (what was logged), fails
_wake = threading.Event()  # a save asks for a reading at once
LOG_AGAIN = 3600  # a problem that stays is said again after this many seconds


def _fresh_state() -> dict:
    return {"next": 0.0, "sent": {}, "said": {}, "fails": 0, "ha_down": False, "started": False, "dirty": False, "gap": 0.0}


def _line(conn, addon: dict, level: str, text: str) -> None:
    connectors.write_logs(conn, addon["vehicle_id"], addon["addon_id"], [(connectors._now(), level, SOURCE, text[:300])])


def _say(conn, addon: dict, st: dict, key: str, level: str, text: str, now: float) -> None:
    """A line in the log of the plugin - once for the same thing (again only when the text changes or after an hour)."""
    before = st["said"].get(key)
    if before and before[0] == text and now - before[1] < LOG_AGAIN:
        return
    st["said"][key] = (text, now)
    _line(conn, addon, level, text)


def _detail(problem: str, detail: str, t) -> str:
    return t(f"hab.subject.{detail}") if problem == "truth" else detail


def _problem_words(problem: str, detail: str) -> str:
    t = i18n.translator("en")
    return t(f"hab.p.{problem}", detail=_detail(problem, detail, t))


def _report(conn, addon: dict, st: dict, bound: dict, readings: dict[str, Reading], now: float) -> None:
    """What is wrong with the entities goes into the log of the plugin: a typing error, a unit that does not fit - not a car that is asleep."""
    for key, reading in readings.items():
        if reading.ok or reading.problem in ("unavailable", "ha"):
            st["said"].pop(key, None)
            continue
        entity = (bound.get(key) or {}).get("entity", "?")
        _say(conn, addon, st, key, "warn", f"{key} ({entity}): {_problem_words(reading.problem, reading.detail)}", now)


def run(addon: dict, states: dict[str, dict] | None, st: dict, now: float | None = None) -> str:
    """One reading of an install: read the entities, send what is new. Returns a sentence about it (for the log in debug mode)."""
    now = time.monotonic() if now is None else now
    with db.tx() as conn:
        bound = bindings(conn, addon["id"])
    readings: dict[str, Reading] = {}
    for key, binding in bound.items():
        slot, name = split(key)
        if slot is not None:
            readings[key] = read(slot, binding["entity"], binding["options"], states, name)
    effective = _position_of_halves(readings)
    fresh = {k: r for k, r in effective.items() if r.ok and st["sent"].get(k) != (r.value, r.at)}
    started = time.monotonic()
    stored = 0
    notes: list[str] = []
    with db.tx() as conn:
        _report(conn, addon, st, bound, effective, now)
        if not st["started"] and bound:
            st["started"] = True
            _line(conn, addon, "info", f"reading {len(bound)} entities of Home Assistant every {interval(addon)} s")
        if not fresh:
            return "nothing new"
        batches = build(fresh)
        fields: set[str] = set()
        retry: set[str] = set()
        for at, data in batches:
            done, refused = deliver(conn, addon, at, data)
            fields |= set(data)
            for field, text in refused.items():
                retry.add(field)
                _say(conn, addon, st, f"refused.{field}", "warn", f"{field}: the Plugin API refused the value: {text[:150]}", now)
            for field, text in done.items():
                if text.startswith("ignored (taken"):
                    retry.add(field)
                    _say(conn, addon, st, f"taken.{field}", "warn", f"{field}: {text}", now)
                elif field == "odometer_km":
                    known = summary.current_odometer(conn, addon["vehicle_id"])
                    # lower than known: said (once). Equal is the plugin's own reading again after a restart: no word.
                    if text.startswith("ignored") and known is not None and round(data["odometer_km"]) < known:
                        _say(conn, addon, st, "odometer.low", "warn", ODOMETER_LOW, now)
                    else:
                        st["said"].pop("odometer.low", None)  # it counts again: a later gap is said again at once
            stored += sum(1 for text in done.values() if text.startswith("stored"))
        for key, reading in fresh.items():
            slot = split(key)[0]
            if slot is not None and slot.field not in retry:
                st["sent"][key] = (reading.value, reading.at)
        names = sorted(fields)
        connectors.note_usage(conn, addon["vehicle_id"], addon["addon_id"], "POST", "/api/v1/vehicles/{id}/data", ", ".join(names))
        merged: dict = {}
        for _at, data in batches:
            merged.update(data)
        linkmap.record(
            conn, addon["vehicle_id"], addon["addon_id"], "POST", ["", "api", "v1", "vehicles", str(addon["vehicle_id"]), "data"], merged
        )
        if connectors.debug_enabled(conn, addon["vehicle_id"], addon["addon_id"]):
            connectors.record_traffic(
                conn, addon["vehicle_id"], addon["addon_id"], "api", "POST", f"/api/v1/vehicles/{addon['vehicle_id']}/data", 200,
                len(json.dumps(merged)), round((time.monotonic() - started) * 1000), ", ".join(names),
            )  # fmt: skip
    if stored:
        events.changed()
    notes.append(f"{stored} value(s) stored")
    return "; ".join(notes)


def request_run(addon_pk: int) -> None:
    """A page saved the bindings: read again at once, and send everything (not only what changed)."""
    st = _state.get(addon_pk)
    if st is not None:
        st["next"] = 0.0
        st["sent"] = {}
        st["dirty"] = False
    _wake.set()


# ---- the live connection (halive.py): a change of an entity makes a reading at once; asking now and then stays as the safety net

LIVE_GAP = 1.0  # a change makes a reading at once; the next one for the same install waits this long (a burst of changes is one reading)
LIVE_CATCHUP = 300  # with a live connection Home Assistant is looked at through the REST API only this often (or as often as the setting says, if longer)
_link: halive.Link | None = None
_watch: dict[str, set[int]] = {}  # entity -> the installs that read it (made by tick)
_pause = 3.0  # how long the loop may sleep: tick shortens it when a change waits for its turn


def attach(link: halive.Link | None) -> None:
    """Use this live connection (the add-on does that at the start; the tests with a made-up Home Assistant do it themselves)."""
    global _link
    _link = link
    if link is not None:
        link.on_change, link.on_state = _on_change, _on_state


def live() -> bool:
    return _link is not None and _link.live


def _on_change(entity: str) -> None:
    """An entity of Home Assistant changed (called in the thread of the live connection)."""
    for pk in _watch.get(entity, ()):
        st = _state.get(pk)
        if st is not None:
            st["dirty"] = True
    _wake.set()


def _on_state(up: bool) -> None:
    """The live connection came up or went down: look at Home Assistant afresh now (the first in the way of a safety net, the second as the way back to asking)."""
    for st in list(_state.values()):
        st["next"] = 0.0
    _wake.set()


def tick(now: float | None = None) -> int:
    """Reads every install that is due (a plugin with ``bridge`` that is on and set up, on a car that is not archived): on its turn (the interval of the
    setting; with a live connection only as a safety net) or because an entity it reads has changed. Returns how many ran. Home Assistant is asked ONCE for
    all of them. Called every few seconds and at every change by ``loop``; tests call it with a clock of their own."""
    global _watch, _pause
    now = time.monotonic() if now is None else now
    entities: dict[int, set[str]] = {}
    watch: dict[str, set[int]] = {}
    with db.tx() as conn:
        rows = conn.execute(
            "SELECT a.id, a.vehicle_id FROM vehicle_addons a JOIN vehicles v ON v.id = a.vehicle_id "
            "WHERE a.active = 1 AND a.status = 'configured' AND a.kind = 'plugin' AND a.manifest LIKE '%\"bridge\"%' AND v.archived = 0"
        ).fetchall()
        marks = ",".join("?" * len(rows))  # only what the installs that are read bind: nothing else of Home Assistant is followed
        for row in (
            conn.execute(f"SELECT addon_pk, entity FROM ha_bindings WHERE addon_pk IN ({marks})", [r["id"] for r in rows]) if rows else ()
        ):
            entities.setdefault(row["addon_pk"], set()).add(row["entity"])
            watch.setdefault(row["entity"], set()).add(row["addon_pk"])
    _watch = watch
    for gone in set(_state) - {r["id"] for r in rows}:  # switched off or removed: it starts afresh when it comes back
        _state.pop(gone, None)
    link = _link
    if link is not None:
        link.follow(watch)  # exactly the entities that are read, nothing else of Home Assistant
    follows = link.states() if link is not None else None  # None: no live connection, asking is the way
    known = link.following() if link is not None else frozenset()
    due: list[tuple[dict, bool]] = []
    _pause = 3.0
    for row in rows:
        st = _state.setdefault(row["id"], _fresh_state())
        scheduled = now >= st["next"]
        event = bool(st["dirty"]) and follows is not None and entities.get(row["id"], set()) <= known
        if event and now < st["gap"]:
            _pause = min(_pause, max(0.05, st["gap"] - now))  # the next change waits for its turn: come back then
            event = False
        if scheduled or event:
            due.append((row, scheduled))
    if not due:
        return 0
    dump = ha.all_states() if any(scheduled for _row, scheduled in due) else None
    if dump is not None and follows is not None and link is not None:
        link.merge(dump)  # what Home Assistant says now is taken over where it is newer ...
        dump = {**dump, **(link.states() or {})}  # ... and what the live connection knows is newer than a look that is a few seconds old
    ran = 0
    for row, scheduled in due:
        with db.tx() as conn:
            addon = addons.get(conn, row["vehicle_id"], row["id"])
        if addon is None or not addon["m"].get("bridge"):
            continue
        st = _state[row["id"]]
        every = interval(addon)
        states = (dump if dump is not None else follows) if scheduled else follows
        ran += 1
        if states is None:  # Home Assistant cannot be asked: say so once, try again soon (a restart of Home Assistant takes a minute)
            st["fails"] += 1
            st["next"] = now + min(300, every * 2 ** min(st["fails"] - 1, 4))
            if not st["ha_down"]:
                st["ha_down"] = True
                with db.tx() as conn:
                    _line(conn, addon, "warn", "Home Assistant cannot be reached; trying again")
            continue
        st["dirty"], st["gap"] = False, now + LIVE_GAP  # (a change during the reading marks it again)
        try:
            note = run(addon, states, st, now)
        except Exception:
            log.exception("home assistant plugin %s failed", addon["addon_id"])
            st["fails"] += 1
            st["next"] = now + min(MAX_BACKOFF, every * 2 ** min(st["fails"] - 1, 4))
            with db.tx() as conn:
                _say(conn, addon, st, "crash", "error", "reading Home Assistant failed unexpectedly (see the log of the add-on)", now)
            continue
        with db.tx() as conn:
            if st["ha_down"]:
                st["ha_down"] = False
                _line(conn, addon, "info", "Home Assistant can be reached again")
            elif connectors.debug_enabled(conn, addon["vehicle_id"], addon["addon_id"]):
                _line(conn, addon, "debug", f"{'checked' if scheduled else 'a change arrived'}: {note}")
        st["fails"] = 0
        if scheduled:
            st["next"] = now + (max(every, LIVE_CATCHUP) if follows is not None else every)
    return ran


def loop() -> None:
    while not events.stop.is_set():
        try:
            tick()
        except Exception:
            log.exception("home assistant plugins: a round failed")
        if _wake.wait(max(0.05, _pause)):
            _wake.clear()


def start() -> threading.Thread:
    if os.environ.get("CARASSISTANT_HA_LIVE", "1") != "0" and halive.available():
        link = halive.Link()
        attach(link)
        link.start()
    thread = threading.Thread(target=loop, name="habridge", daemon=True)
    thread.start()
    return thread


# ------------------------------------------------------------------ what the page says


def _fmt(value: float) -> str:
    """A number as the page shows it: no zeros at the end, a decimal comma in German."""
    text = f"{int(value)}" if float(value).is_integer() else f"{value:.3f}".rstrip("0").rstrip(".")
    return text.replace(".", ",") if config.language() == "de" else text


def describe(slot: cat.Slot, reading: Reading | None, t) -> dict:
    """What the page says about one row: ``{"level": ok | warn | bad | idle, "text": the value or what is wrong, "from": where it came from}``."""
    if reading is None:
        return {"level": "idle", "text": "", "from": ""}
    if not reading.ok:
        level = "warn" if reading.problem in ("unavailable", "ha") else "bad"
        return {"level": level, "text": t(f"hab.p.{reading.problem}", detail=_detail(reading.problem, reading.detail, t)), "from": ""}
    if slot.kind in ("number", "tyre", "coord"):
        text = f"{_fmt(reading.value)} {slot.unit}".strip()
        origin = t("hab.from", raw=reading.raw) if reading.converted and reading.raw else ""
    elif slot.kind in ("bool", "closure", "warning"):
        text = t(f"hab.v.{slot.truth or 'on'}.{1 if reading.value else 0}")
        origin = t("hab.state", raw=reading.raw) if reading.raw else ""
    else:
        text, origin = str(reading.raw), ""
    return {"level": "ok", "text": text, "from": origin}


def _row_name(raw) -> str:
    return re.sub(r"[\s-]+", "_", str(raw or "").strip().lower())


def _number_option(raw) -> float:
    number = float(str(raw).strip().replace(",", "."))
    if not math.isfinite(number) or abs(number) >= SCALE_LIMIT:
        raise ValueError("limit")
    return number


def parse_options(form: dict, prefix: str, slot: cat.Slot) -> tuple[dict, str]:
    """The options of one row as the page sent them: ``(cleaned, "")`` or ``({}, i18n key of what is wrong)``."""
    opts: dict = {}
    attribute = str(form.get(prefix + "attribute") or "").strip()
    if attribute:
        if not ATTRIBUTE.fullmatch(attribute):
            return {}, "hab.err_attribute"
        opts["attribute"] = attribute
    if slot.kind in ("number", "tyre", "coord"):
        unit = str(form.get(prefix + "unit") or "auto").strip()
        if unit not in ("auto", "raw", *UNIT_CHOICES.get(slot.unit, ())):
            return {}, "hab.err_unit"
        if unit != "auto":
            opts["unit"] = unit
        for name in ("scale", "offset"):
            raw = str(form.get(prefix + name) or "").strip()
            if raw:
                try:
                    opts[name] = _number_option(raw)
                except ValueError:
                    return {}, "hab.err_number"
    if slot.kind in ("bool", "closure", "warning"):
        if str(form.get(prefix + "invert") or "") in ("1", "on", "true"):
            opts["invert"] = True
        words = [w.strip() for w in re.split(r"[,;\n]", str(form.get(prefix + "yes") or "")) if w.strip()]
        if len(words) > MAX_YES or any(len(w) > 40 for w in words):
            return {}, "hab.err_yes"
        above = str(form.get(prefix + "above") or "").strip()
        if words and above:
            return {}, "hab.err_both"
        if words:
            opts["yes"] = words
        if above:
            try:
                opts["above"] = _number_option(above)
            except ValueError:
                return {}, "hab.err_number"
    if slot.kind == "warning":
        text = " ".join(str(form.get(prefix + "text") or "").split())[: connectors.MAX_WARNING_TEXT]
        if text:
            opts["text"] = text
    return opts, ""


MAX_BOUND = 80  # rows an install may bind in all


def parse_form(form: dict, manifest: dict, states: dict[str, dict] | None) -> tuple[dict[str, dict], dict[str, str]]:
    """The bindings a page of the plugin sent: ``({row key: {"entity", "options", "field"}}, {name of the entity field: i18n key of what is wrong})``.
    Field names: ``e.<slot>`` (and ``o.<slot>.<option>``) for a value, ``l.<slot>.<n>.e`` / ``.n`` / ``.<option>`` for the n-th row of a list."""
    rows: dict[str, dict] = {}
    errors: dict[str, str] = {}
    for slot in offered(manifest):
        if slot.kind in cat.LIST_KINDS:
            names: set[str] = set()
            candidates = [(f"l.{slot.key}.{i}.", _row_name(form.get(f"l.{slot.key}.{i}.n"))) for i in range(cat.MAX_ROWS)]
        else:
            candidates = [(f"o.{slot.key}.", "")]
        for prefix, name in candidates:
            field = prefix + "e" if slot.kind in cat.LIST_KINDS else f"e.{slot.key}"
            entity = str(form.get(field) or "").strip().lower()
            if not entity:
                continue
            key = f"{slot.key}.{name}" if slot.kind in cat.LIST_KINDS else slot.key
            if slot.kind in cat.LIST_KINDS:
                if not connectors.CLOSURE_NAME.fullmatch(name):
                    errors[field] = "hab.err_name"
                    continue
                if name in names:
                    errors[field] = "hab.err_dupe"
                    continue
                names.add(name)
            if not ENTITY.fullmatch(entity):
                errors[field] = "hab.err_entity"
                continue
            if states is not None and entity not in states:
                errors[field] = "hab.err_missing"
                continue
            opts, why = parse_options(form, prefix, slot)
            if why:
                errors[field] = why
                continue
            rows[key] = {"entity": entity, "options": opts, "field": field}
    if len(rows) > MAX_BOUND:
        errors["_"] = "hab.err_many"
    return rows, errors


def preview(form: dict, manifest: dict, states: dict[str, dict] | None, t) -> dict[str, dict]:
    """What each entity the person typed would say, before anything is saved: ``{name of the entity field: describe(...)}``."""
    rows, errors = parse_form(form, manifest, states)
    out = {field: {"level": "bad", "text": t(why), "from": ""} for field, why in errors.items() if field != "_"}
    for key, row in rows.items():
        slot, name = split(key)
        if slot is not None:
            out[row["field"]] = describe(slot, read(slot, row["entity"], row["options"], states, name), t)
    return out


def save(conn, addon: dict, form: dict, states: dict[str, dict] | None) -> tuple[dict[str, str], dict[str, str]]:
    """Save what the page sent: the bindings, the interfaces they take (claims.py), the interval. ``(errors, taken)``: errors by the name of the field,
    ``taken`` = interfaces another plugin of this car holds ({field: its name}); when either is not empty nothing is saved."""
    rows, errors = parse_form(form, addon["m"], states)
    if errors:
        return errors, {}
    taken = claims.conflicts(conn, addon["vehicle_id"], addon["id"], fields_bound({k: {} for k in rows}))
    if taken:
        return {}, taken
    every = form.get("every")
    if every is not None and any(f["key"] == "every" for f in addon["m"].get("settings", [])):
        sub = addons.guide_manifest(addon, {"every"})
        bad = addons.check_settings(sub, addons.guide_form(addon, {"every": str(every)}, {"every"}), addon["vals"])
        if bad:
            return {"every": bad["every"]}, {}
        addons.save_flow_values(conn, addon, {"every": str(every)}, {"every"})
    conn.execute("DELETE FROM ha_bindings WHERE addon_pk = ?", (addon["id"],))
    for key, row in rows.items():
        conn.execute(
            "INSERT INTO ha_bindings(addon_pk, slot, entity, options) VALUES(?,?,?,?)",
            (addon["id"], key, row["entity"], json.dumps(row["options"], sort_keys=True)),
        )
    claims.register(conn, addon["vehicle_id"], addon["id"], fields_bound(rows))
    fresh = addons.get(conn, addon["vehicle_id"], addon["id"]) or addon
    addons.set_up(conn, addon["vehicle_id"], fresh, {}, set())  # an install with bindings is set up
    return {}, {}


# ------------------------------------------------------------------ the entities to choose from


def suggest(
    slot: cat.Slot, query: str, show_all: bool, states: dict[str, dict], limit: int = 40, context: dict[str, dict] | None = None
) -> list[dict]:
    """Entities of Home Assistant for one slot, the likeliest first: the right kind of entity, a device class or a unit that fits, the words typed
    (looked for in the name, the id, the device and the area - ``context`` = ``halive.registry()``)."""
    words = [w for w in re.split(r"\s+", query.strip().lower()) if w]
    out: list[tuple[int, str, dict]] = []
    for entity_id, state in states.items():
        domain = entity_id.split(".")[0]
        attrs = state.get("attributes") or {}
        name = str(attrs.get("friendly_name") or "")
        if not show_all and domain not in slot.domains:
            continue
        where = (context or {}).get(entity_id) or {}
        haystack = f"{entity_id} {name} {where.get('device', '')} {where.get('area', '')}".lower()
        if any(w not in haystack for w in words):
            continue
        score = 0
        score += 2 if str(attrs.get("device_class") or "") in slot.classes else 0
        unit = str(attrs.get("unit_of_measurement") or "")
        score += 2 if unit and _norm(unit) in UNITS.get(slot.unit, {}) and slot.unit not in ("%", "°") else 0
        score += 3 if slot.kind == "position" and "latitude" in attrs and "longitude" in attrs else 0
        score += 1 if domain in slot.domains else 0
        score += sum(1 for part in slot.key.split("_") if len(part) > 2 and part in haystack)
        shown = {
            "id": entity_id,
            "name": name,
            "state": str(state.get("state"))[:40],
            "unit": unit[:16],
            "device": where.get("device", "")[:60],
            "area": where.get("area", "")[:60],
        }
        out.append((-score, entity_id, shown))
    out.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in out[:limit]]


# ------------------------------------------------------------------ the page


def _typed_options(form: dict, prefix: str, slot: cat.Slot) -> dict:
    """The options of a row as they were typed (nothing checked): what the page shows again when a save was refused."""
    opts: dict = {}
    for name in ("attribute", "unit", "scale", "offset", "above", "text", "yes"):
        value = str(form.get(prefix + name) or "").strip()
        if value and not (name == "unit" and value == "auto"):
            opts[name] = value
    if str(form.get(prefix + "invert") or "") in ("1", "on", "true"):
        opts["invert"] = True
    return opts


def typed_rows(form: dict, manifest: dict) -> dict[str, dict]:
    """The rows of a form as they were typed, not checked (``parse_form`` says what is wrong): ``{row key: {"entity", "options", "name"}}``."""
    rows: dict[str, dict] = {}
    for slot in offered(manifest):
        if slot.kind in cat.LIST_KINDS:
            for i in range(cat.MAX_ROWS):
                prefix = f"l.{slot.key}.{i}."
                entity, name = str(form.get(prefix + "e") or "").strip(), _row_name(form.get(prefix + "n"))
                if entity or name:
                    rows[f"{slot.key}.{name or '~' + str(i)}"] = {
                        "entity": entity,
                        "options": _typed_options(form, prefix, slot),
                        "name": name,
                    }
        elif (entity := str(form.get(f"e.{slot.key}") or "").strip()) or form.get(f"o.{slot.key}.attribute"):
            rows[slot.key] = {"entity": entity, "options": _typed_options(form, f"o.{slot.key}.", slot), "name": ""}
    return rows


def page_model(
    conn, addon: dict, states: dict[str, dict] | None, t, typed: dict[str, dict] | None = None, err_slots: frozenset[str] = frozenset()
) -> dict:
    """Everything the settings page of a package with ``bridge`` draws: the groups with their slots, what is bound, what each entity says right now,
    which interfaces another plugin holds. ``typed`` = rows as typed after a refused save (shown instead of the saved ones, without a reading)."""
    held = claims.owners(conn, addon["vehicle_id"])
    bound = typed if typed is not None else bindings(conn, addon["id"])
    shown = offered(addon["m"])
    groups = []
    for group in cat.groups({s.group for s in shown}):
        slots = []
        for slot in group["slots"]:
            if slot not in shown:
                continue
            owner = held.get(slot.field)
            entry = {
                "key": slot.key,
                "kind": slot.kind,
                "unit": slot.unit,
                "label": t(f"hab.slot.{slot.key}"),
                "help": t(f"hab.help.{slot.key}") if t.has(f"hab.help.{slot.key}") else "",
                "units": UNIT_CHOICES.get(slot.unit, ()),
                "taken": owner["name"] if owner and owner["pk"] != addon["id"] else "",
                "flag": slot.kind in ("bool", "closure", "warning"),
                "number": slot.kind in ("number", "tyre", "coord"),
                "list": slot.kind in cat.LIST_KINDS,
                "names": cat.CLOSURE_NAMES.get(slot.key, ()),
                "count": 0,
            }
            if slot.kind in cat.LIST_KINDS:
                rows = []
                for key, binding in bound.items():
                    found, name = split(key)
                    if found is slot:
                        rows.append(_row(slot, name if typed is None else binding.get("name", ""), binding, states, t, typed is None))
                entry["rows"] = rows
                entry["spare"] = min(2, cat.MAX_ROWS - len(rows))
                entry["count"] = sum(1 for r in rows if r["entity"])
            else:
                binding = bound.get(slot.key)
                entry["row"] = _row(slot, "", binding, states, t, typed is None) if binding else _empty_row()
                entry["count"] = 1 if binding and binding["entity"] else 0
            slots.append(entry)
        count = sum(s["count"] for s in slots)
        groups.append(
            {
                "id": group["id"],
                "icon": group["icon"],
                "name": t(f"hab.group.{group['id']}"),
                "slots": slots,
                "bound": count,
                "total": len(slots),
                "err": any(s["key"] in err_slots for s in slots),
            }
        )
    anything = any(g["bound"] for g in groups)
    for n, g in enumerate(groups):
        g["open"] = bool(g["bound"] or g["err"] or (n == 0 and not anything))
    every = next((f for f in addon["m"].get("settings", []) if f["key"] == "every"), None)
    return {
        "groups": groups,
        "ha": states is not None,
        "every": every,
        "every_now": str((addon.get("vals") or {}).get("every") or (every or {}).get("default") or ""),
        "bound": sum(g["bound"] for g in groups),
        "live": live(),
        "seconds": interval(addon),
    }


def _empty_row() -> dict:
    return {"entity": "", "name": "", "opts": {}, "yes": "", "friendly": "", "status": {"level": "idle", "text": "", "from": ""}}


def _row(slot: cat.Slot, name: str, binding: dict | None, states: dict[str, dict] | None, t, live: bool = True) -> dict:
    opts = binding["options"] if binding else {}
    entity = binding["entity"] if binding else ""
    state = (states or {}).get(entity) or {}
    yes = opts.get("yes", "")
    return {
        "entity": entity,
        "name": name,
        "opts": opts,
        "yes": ", ".join(yes) if isinstance(yes, list) else str(yes),
        "friendly": str((state.get("attributes") or {}).get("friendly_name") or ""),
        "status": describe(slot, read(slot, entity, opts, states, name), t) if entity and live else _empty_row()["status"],
    }
