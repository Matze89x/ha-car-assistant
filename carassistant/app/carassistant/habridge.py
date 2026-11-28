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
from datetime import UTC, date, datetime, timedelta

from . import addons, claims, config, connectors, db, events, ha, halive, i18n, linkmap, modules, summary, trips
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
TRACK_STEP_M = (
    40  # a point of the route is kept only when the car moved this far from the last one: a parked tracker jitters by a few metres
)
TRACK_ACCURACY_M = 100  # a fix the tracker itself calls less exact than this (``gps_accuracy``, metres) is left out
DRIVING_MS = 4.0  # metres per second between two reports (about 15 km/h): faster than somebody walks - below it nothing is said about a car that "moves"
MAX_SPEED_MS = 150.0  # faster than this between two reports (540 km/h) is no drive: the tracker jumped (a bad fix, another device of a person) - the route is broken there


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
    "A": {"a": (1, 0), "ma": (0.001, 0)},
    "kWh": {"kwh": (1, 0), "wh": (0.001, 0), "mwh": (1000, 0)},
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
    "A": ("A", "mA"),
    "kWh": ("kWh", "Wh", "MWh"),
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


# what the word of a wallbox says (the six states of ``charge_state``): the words of the integrations people use - OCPP (Available, Preparing, Charging,
# SuspendedEV, SuspendedEVSE, Finishing, Faulted), go-e (Idle, Charging, WaitCar, Complete, Error), Easee (disconnected, awaiting_start, charging,
# completed, error), the states A to F of IEC 61851 (A no car, B plugged in, C charging, E / F fault) and plain words, a few of them German.
# Compared in lower case with blanks, dashes and dots turned into _. What is not here is named by the person (the options of the row).
STATE_WORDS: dict[str, tuple[str, ...]] = {
    "unplugged": (
        *(
            "unplugged",
            "not_plugged",
            "disconnected",
            "not_connected",
            "cable_disconnected",
            "no_vehicle",
            "no_car",
            "vehicle_not_connected",
        ),
        *("available", "idle", "free", "standby", "a", "a1", "a2", "state_a", "getrennt", "nicht_verbunden", "kein_auto", "frei"),
    ),
    "plugged": (
        *("plugged", "plugged_in", "connected", "cable_connected", "vehicle_connected", "car_connected", "vehicle_detected", "preparing"),
        *("ready", "ready_to_charge", "b", "b1", "b2", "state_b", "angesteckt", "verbunden", "bereit"),
    ),
    "waiting": (
        *("waiting", "waiting_for_car", "waiting_for_car_demand", "wait_car", "waitcar", "waiting_for_vehicle", "awaiting_start"),
        *("awaiting_authorization", "waiting_for_authorization", "authorization_required", "authorizing", "waiting_for_next_schedule"),
        *("scheduled", "delayed", "paused", "pause", "suspended", "suspended_ev", "suspendedev", "suspended_evse", "suspendedevse"),
        *("charging_paused", "pending", "waiting_for_sun", "waiting_for_surplus", "locked", "stopped", "blocked", "wartet", "pausiert"),
    ),
    "charging": (
        *("charging", "charge", "in_charge", "charging_active", "c", "c1", "c2", "d", "state_c", "state_d", "fast_charging", "ev_charging"),
        *("supplying_energy", "l\u00e4dt", "laden", "ladevorgang"),
    ),
    "finished": (
        *("finished", "finishing", "complete", "completed", "charge_complete", "charging_complete", "charged", "fully_charged", "full"),
        *("done", "charging_finished", "end_of_charge", "fertig", "abgeschlossen", "voll"),
    ),
    "fault": (
        *("fault", "faulted", "error", "failure", "failed", "alarm", "e", "f", "state_e", "state_f", "emergency", "malfunction", "problem"),
        *("fehler", "st\u00f6rung"),
    ),
}
STATE_OF_WORD = {word: state for state, words in STATE_WORDS.items() for word in words}
# a text that says "nothing is wrong"
NO_FAULT = {
    "none",
    "no_error",
    "no_errors",
    "no_fault",
    "no_faults",
    "ok",
    "normal",
    "off",
    "false",
    "no",
    "0",
    "clear",
    "idle",
    "ready",
    "kein_fehler",
}
# a wallbox that says what it does also says whether the car is plugged in (a fault says nothing about the cable)
PLUGGED_BY_STATE = {"unplugged": False, "plugged": True, "waiting": True, "charging": True, "finished": True}


def _word(text: object) -> str:
    return re.sub(r"[\s\-./:]+", "_", str(text).strip().lower()).strip("_")


def read_state(slot: cat.Slot, state: dict, opts: dict) -> Reading:
    """The word of a wallbox as one of the six states (``connectors.CHARGE_STATES``): the person's own words first, then the usual ones."""
    value, _unit = _source(state, opts)
    text = str(value).strip()
    key = _word(text)
    for name, words in (opts.get("words") or {}).items():
        if key in {_word(w) for w in words}:
            return Reading(ok=True, value=name, raw=text[:40])
    found = STATE_OF_WORD.get(key)
    if found is None:
        raise _Problem("words", text[:30])
    return Reading(ok=True, value=found, raw=text[:40])


def read_label(slot: cat.Slot, state: dict, opts: dict) -> Reading:
    """A short word as it is: the mode a wallbox is in."""
    value, _unit = _source(state, opts)
    text = " ".join(str(value).split())[:40]
    if not text:
        raise _Problem("unavailable")
    return Reading(ok=True, value=text, raw=text)


def read_fault(slot: cat.Slot, state: dict, opts: dict) -> Reading:
    """What is wrong with the wallbox: a text sensor (its words, or ``none``) or a yes / no of the class *problem* (the name of the entity then). The value is
    the text - empty while nothing is wrong, which is a reading, too: it takes the old fault away. (``none`` and an empty state say that nothing is wrong;
    only ``unavailable`` and ``unknown`` say that nothing is known.)"""
    attrs = state.get("attributes") or {}
    if opts.get("attribute"):
        if opts["attribute"] not in attrs:
            raise _Problem("attribute", opts["attribute"])
        value = attrs[opts["attribute"]]
    else:
        value = state.get("state")
    text = " ".join(str(value if value is not None else "").split())
    key = _word(text)
    if key in ("unavailable", "unknown", "nan", "null"):
        raise _Problem("unavailable")
    limit = connectors.TEXTS["charge_fault"][1]
    if str(state.get("entity_id") or "").split(".")[0] in ("binary_sensor", "switch", "input_boolean") or key in ("on", "true", "yes"):
        on = key in ("on", "true", "yes", "1", "problem", "detected")
        if opts.get("invert"):
            on = not on
        name = " ".join(str(attrs.get("friendly_name") or "").split())
        return Reading(ok=True, value=(name or "Fault")[:limit] if on else "", raw=text[:40])
    return Reading(ok=True, value="" if key in NO_FAULT or not key else text[:limit], raw=text[:40])


def read_command(slot: cat.Slot, state: dict, opts: dict) -> Reading:
    """A row for a command reads nothing: it says that the entity is there and what it says now (the card shows the buttons only for entities that can do it)."""
    domain = str(state.get("entity_id") or "").split(".")[0]
    if domain not in slot.domains:
        raise _Problem("domain", domain)
    return Reading(ok=True, value=None, raw=str(state.get("state"))[:40])


READERS = {
    "command": read_command,
    "state": read_state,
    "label": read_label,
    "fault": read_fault,
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
    """The interfaces (fields of the Plugin API) these bindings fill. A wallbox state also makes *Charging* and *Plugged in* (unless they have rows of their own)."""
    fields = {slot.field for key in bound if (slot := split(key)[0]) is not None and slot.field}  # (a command fills no interface)
    if "charge_state" in bound:
        fields |= {"charging", "plugged"}
    return fields


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
        if v is not False and k != "words"
    }
    if isinstance(raw.get("words"), dict):
        for name, words in raw["words"].items():
            if name in connectors.CHARGE_STATES and isinstance(words, list):
                form[f"x.w_{name}"] = ", ".join(str(w) for w in words)
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


def _charge_of_state(readings: dict[str, Reading], bound: dict[str, dict]) -> dict[str, Reading]:
    """A wallbox that says one word for what it does (*State of the wallbox*) also tells whether the car is charging and whether it is plugged in - for
    the interfaces the person did not bind to an entity of their own."""
    state = readings.get("charge_state")
    if state is None or not state.ok:
        return readings
    out = dict(readings)
    if "charging" not in bound:
        out["charging"] = Reading(ok=True, value=state.value == "charging", raw=state.raw, at=state.at)
    if "plugged" not in bound and state.value in PLUGGED_BY_STATE:
        out["plugged"] = Reading(ok=True, value=PLUGGED_BY_STATE[state.value], raw=state.raw, at=state.at)
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
    return {"next": 0.0, "sent": {}, "said": {}, "fails": 0, "ha_down": False, "started": False, "dirty": False, "gap": 0.0, "retry": None}


def _line(conn, addon: dict, level: str, text: str) -> None:
    connectors.app_log(conn, addon["vehicle_id"], addon["addon_id"], level, SOURCE, text[:300])  # (also in the log of the add-on)


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


def _moment(text) -> datetime | None:
    try:
        when = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=UTC)


def _accuracy_of(state: dict | None):
    """What the tracker says about how exact its fix is, metres (``gps_accuracy``; ``location_accuracy`` is what the developer documentation calls it)."""
    attrs = (state or {}).get("attributes") or {}
    return attrs.get("gps_accuracy", attrs.get("location_accuracy"))


TRIP_NOTES = {  # what is noticed about a tracker that makes no drives: (how many times in a row before it is said, the sentence - ``{}`` is filled in)
    "parked": (
        3,
        "position ({position}): the car moves, but the ignition entity ({ignition}) says off - no drive is recorded while it does. It should be on while the "
        "car runs; if it is not the right entity, choose another one or clear the row.",
    ),
    "inexact": (
        5,
        "position ({position}): the tracker calls its fixes inexact (more than {metres} m) - they are left out, so no drive is recorded from them.",
    ),
    "rare": (
        3,
        "position ({position}): the car is somewhere else every time, but the tracker reports less often than every {minutes} min while it moves - no drive can "
        "be recorded from that. Trips need a report at least every few minutes (every 1-2 minutes is good).",
    ),
}  # fmt: skip


def _track_step(st: dict, lat: float, lon: float, when: datetime, accuracy, parked: bool) -> tuple[list[dict], dict | None, str]:
    """The rules of a drive for ONE report of the tracker - the same for a report that has just come and for one read from the history of Home Assistant
    afterwards: ``(the points to keep, the place the route has reached, what was noticed)``. ``st`` remembers the last report (``seen``) and the last point
    kept (``track``). Noticed: ``""``, ``parked`` (the car moved while the ignition entity says off), ``inexact`` (a fix the tracker calls less exact than
    ``TRACK_ACCURACY_M``), ``rare`` (the car is elsewhere, but the report before is longer ago than ``TRIP_GAP``: nothing says how it got there) or ``jump``
    (faster than ``MAX_SPEED_MS``: a bad fix, or another device - no line is drawn to such a place)."""
    seen, last = st.get("seen"), st.get("track")
    metres, speed = 0.0, 0.0  # from the last report: how far, how fast (metres per second)
    if seen is not None and when > seen["at"]:
        metres = trips.haversine_km(seen["lat"], seen["lon"], lat, lon) * 1000
        speed = metres / max(1.0, (when - seen["at"]).total_seconds())
    driving = (
        metres >= TRACK_STEP_M and speed >= DRIVING_MS
    )  # (does it look as if the car drives: far enough, and faster than somebody walks)
    if isinstance(accuracy, int | float) and not isinstance(accuracy, bool) and accuracy > TRACK_ACCURACY_M:
        return [], None, "inexact" if driving else ""
    st["seen"] = {"lat": lat, "lon": lon, "at": when}
    if seen is None or when <= seen["at"]:
        return [], None, ""  # the first report since the start (nothing to compare with), or an old one
    if when - seen["at"] > trips.TRIP_GAP:
        # the report before is long ago: that place is no start of a drive (a line of many km through the night)
        return [], None, "rare" if driving else ""
    if speed > MAX_SPEED_MS:
        st["track"] = None  # the report is where it is from now on, but no line leads there: the next points begin a drive of their own
        return [], None, "jump"
    if parked:
        return [], None, "parked" if driving else ""
    if last is not None and when <= last["at"]:
        return [], None, ""
    new_drive = last is None or when - last["at"] > trips.TRIP_GAP
    origin = seen if new_drive else last
    if trips.haversine_km(origin["lat"], origin["lon"], lat, lon) * 1000 < TRACK_STEP_M:
        return [], None, ""
    points = [{"ts": when.isoformat(timespec="seconds"), "lat": lat, "lon": lon}]
    if new_drive:
        points.insert(0, {"ts": seen["at"].isoformat(timespec="seconds"), "lat": seen["lat"], "lon": seen["lon"]})
    return points, {"lat": lat, "lon": lon, "at": when}, ""


def _trip_notes(conn, addon: dict, st: dict, bound: dict, note: str, kept: bool, now: float) -> None:
    """A tracker that moves but makes no drives: after the same thing several times in a row the log of the plugin says what the reason may be."""
    counts = st.setdefault("notes", {})
    if kept:
        counts.clear()
        for key in TRIP_NOTES:
            st["said"].pop(f"trip.{key}", None)  # all is well again: a later problem is said again at once
        return
    if note not in TRIP_NOTES:
        return
    counts[note] = counts.get(note, 0) + 1
    if counts[note] >= TRIP_NOTES[note][0]:
        words = {
            "position": (bound.get("position") or {}).get("entity", "?"),
            "ignition": (bound.get("ignition") or {}).get("entity", "?"),
            "metres": TRACK_ACCURACY_M,
            "minutes": int(trips.TRIP_GAP.total_seconds() // 60),
        }
        _say(conn, addon, st, f"trip.{note}", "warn", TRIP_NOTES[note][1].format(**words), now)


def _record_track(
    conn, addon: dict, st: dict, readings: dict[str, Reading], states: dict[str, dict] | None, bound: dict, now: float | None = None
) -> int:
    """The option *Record trips* of the position row: every move of the tracker becomes a point of the route (``connectors.ingest_track``, the same
    place a plugin's track goes), and ``trips.from_track`` makes a trip of a drive that is over. Returns how many points were kept.

    A tracker in a parked car jitters by a few metres, and one of those points every few minutes would keep a drive "running" for ever: a point is
    kept only when the car is at least ``TRACK_STEP_M`` from the last one. A drive starts at the place the car STOOD (the last position seen before it
    moved), not at the first reading after it set off. While an ignition entity is chosen and says off nothing is kept, and a fix the tracker calls
    inexact is ignored. How fine the route is depends on how often the tracker reports - a car that reports every ten minutes makes no trips.
    What was missed while the app could not look is fetched from the history of Home Assistant first (``_catch_up``)."""
    reading = readings.get("position")
    if reading is None or not reading.ok:
        return 0
    lat, lon = reading.value
    when = _moment(reading.at) if reading.at else datetime.now(UTC)
    if when is None:
        return 0
    entity = (bound.get("position") or {}).get("entity", "")
    ignition = readings.get("ignition")
    parked = ignition is not None and ignition.ok and not ignition.value
    points, track, note = _track_step(st, lat, lon, when, _accuracy_of((states or {}).get(entity)), parked)
    _trip_notes(conn, addon, st, bound, note, bool(points), time.monotonic() if now is None else now)
    if not points:
        return 0
    try:
        connectors.ingest_track(conn, addon["vehicle_id"], {"points": points})
    except connectors.ApiError as exc:
        log.debug("track of %s for vehicle %s refused: %s", addon["addon_id"], addon["vehicle_id"], exc.code)
        return 0
    st["track"] = track
    connectors.note_usage(conn, addon["vehicle_id"], addon["addon_id"], "POST", "/api/v1/vehicles/{id}/track", "points")
    log.debug("track of %s for vehicle %s: %d point(s)", addon["addon_id"], addon["vehicle_id"], len(points))
    return len(points)


# ---- drives that were missed: read from the history Home Assistant keeps

CATCHUP_MAX = timedelta(hours=48)  # how far back the history is looked at
CATCHUP_CHUNK = timedelta(
    hours=12
)  # and asked for in pieces of this size (a tracker that reports every few seconds is a lot for a small machine)
CATCHUP_BUDGET = 25.0  # seconds one reading may spend on it; what is left is taken up at the next one
CATCHUP_PAUSE = 60.0  # seconds between two tries
CATCHUP_PATIENCE = 600.0  # a history that is not there (yet - Home Assistant has just started) is asked for again for this long


def _last_known_position(vehicle_id: int) -> datetime | None:
    """When the car's position was last stored, for a car whose drives were recorded before - binding a tracker for the first time must not bring in
    what happened before it."""
    with db.tx() as conn:
        if conn.execute("SELECT 1 FROM vehicle_track WHERE vehicle_id = ? LIMIT 1", (vehicle_id,)).fetchone() is None:
            return None
        row = conn.execute("SELECT updated FROM live WHERE vehicle_id = ? AND key = 'position'", (vehicle_id,)).fetchone()
    return _moment(row["updated"]) if row and row["updated"] else None


def _replay(st: dict, bound: dict, history: dict[str, list[dict]], ignition_on: bool | None) -> tuple[list[dict], bool | None]:
    """The points of the drives in a piece of history: every report of the tracker goes through the rules of a live one (``_track_step``), with the
    ignition as it was at that moment. Returns ``(points, the ignition at the end)``."""
    position, ignition = bound["position"], bound.get("ignition")
    slot_position, slot_ignition = cat.BY_KEY["position"], cat.BY_KEY["ignition"]
    events: list[tuple[datetime, int, dict]] = []
    for row in history.get(position["entity"], ()):
        found = read(slot_position, position["entity"], position["options"], {position["entity"]: row})
        if found.ok and (when := _moment(found.at)) is not None:
            events.append((when, 1, {"lat": found.value[0], "lon": found.value[1], "accuracy": _accuracy_of(row)}))
    for row in history.get(ignition["entity"], ()) if ignition else ():
        found = read(slot_ignition, ignition["entity"], ignition["options"], {ignition["entity"]: row})
        if found.ok and (when := _moment(found.at)) is not None:
            events.append((when, 0, {"on": bool(found.value)}))
    events.sort(key=lambda event: (event[0], event[1]))  # (an ignition that turns on in the same second as a report counts for it)
    points: list[dict] = []
    for when, kind, data in events:
        if kind == 0:
            ignition_on = data["on"]
            continue
        kept, track, _note = _track_step(st, data["lat"], data["lon"], when, data["accuracy"], ignition_on is False)
        if kept:
            points.extend(kept)
            st["track"] = track
    return points, ignition_on


def _catch_up(addon: dict, st: dict, bound: dict, readings: dict[str, Reading], now: float) -> None:
    """Drives that were missed - the app was off or being updated, Home Assistant could not be reached for a while, the live connection was away - are
    read from the history Home Assistant keeps (the recorder) and put through the same rules as a report that comes live. It is tried when the tracker's
    report is more than ``TRIP_GAP`` later than the last one the app saw (after a start: than the car's position the app stored), and only for a car
    that records drives. Points that are there already are not stored again. A history that cannot be had (Home Assistant has just started, no recorder)
    is asked for again for a few minutes; what cannot be had at all is lost, as it was before."""
    position = bound.get("position")
    reading = readings.get("position")
    if not position or not position["options"].get("track") or reading is None or not reading.ok or not reading.at:
        return
    newest = _moment(reading.at)
    again = st.get("catchup_again")
    if newest is None or now - (st.get("catchup") or -1e9) < CATCHUP_PAUSE or (again is not None and now > again["until"]):
        if again is not None and now > again["until"]:
            st["catchup_again"] = None  # (no more patience)
        return
    seen = st.get("seen")
    since = again["since"] if again is not None else (seen["at"] if seen is not None else _last_known_position(addon["vehicle_id"]))
    if since is None or newest - since <= trips.TRIP_GAP:
        return
    st["catchup"] = now
    entities = [position["entity"], *([bound["ignition"]["entity"]] if bound.get("ignition") else [])]
    begin, end = max(since, newest - CATCHUP_MAX), datetime.now(UTC)
    deadline = time.monotonic() + CATCHUP_BUDGET
    points: list[dict] = []
    ignition_on: bool | None = None
    reached, failed = begin, False
    while reached < end and time.monotonic() < deadline:
        upto = min(reached + CATCHUP_CHUNK, end)
        got = ha.history(entities, reached, upto)
        if got is None:
            failed = True
            break
        kept, ignition_on = _replay(st, bound, got, ignition_on)
        points += kept
        reached = upto
    unfinished = reached < end
    st["catchup_again"] = (
        {"since": reached, "until": (again["until"] if again else now + CATCHUP_PATIENCE)} if (failed or unfinished) else None
    )
    if not points:
        log.debug("catching up %s: nothing found in the history since %s", addon["addon_id"], begin.isoformat(timespec="seconds"))
        return
    vid = addon["vehicle_id"]
    with db.tx() as conn:
        have = {
            r["ts"]
            for r in conn.execute(
                "SELECT ts FROM vehicle_track WHERE vehicle_id = ? AND ts >= ?", (vid, begin.isoformat(timespec="seconds"))
            )
        }
        new = [p for p in points if connectors._iso(p["ts"]) not in have]  # (the form the points are stored in)
        before = conn.execute("SELECT COUNT(*) FROM trips WHERE vehicle_id = ?", (vid,)).fetchone()[0]
        for i in range(0, len(new), connectors.MAX_TRACK_POINTS):
            try:
                connectors.ingest_track(conn, vid, {"points": new[i : i + connectors.MAX_TRACK_POINTS]})
            except connectors.ApiError as exc:
                log.debug("catching up %s: %s", addon["addon_id"], exc.code)
                break
        made = conn.execute("SELECT COUNT(*) FROM trips WHERE vehicle_id = ?", (vid,)).fetchone()[0] - before
        if new:
            hours = max(1, round((end - begin).total_seconds() / 3600))
            _line(
                conn,
                addon,
                "info",
                f"caught up from the history of Home Assistant (the last {hours} h): {len(new)} position(s) of drives, {made} trip(s) made",
            )


def run(addon: dict, states: dict[str, dict] | None, st: dict, now: float | None = None) -> str:
    """One reading of an install: read the entities, send what is new. Returns a sentence about it (for the log in debug mode)."""
    now = time.monotonic() if now is None else now
    with db.tx() as conn:
        bound = bindings(conn, addon["id"])
    readings: dict[str, Reading] = {}
    for key, binding in bound.items():
        slot, name = split(key)
        if slot is not None and slot.kind != "command":  # a command row is only looked at by the page; no value of it goes anywhere
            readings[key] = read(slot, binding["entity"], binding["options"], states, name)
    effective = _charge_of_state(_position_of_halves(readings), bound)
    # (before anything is stored: it asks Home Assistant, which may take a while - no database is held meanwhile)
    _catch_up(addon, st, bound, effective, now)
    fresh = {k: r for k, r in effective.items() if r.ok and st["sent"].get(k) != (r.value, r.at)}
    st["retry"] = None
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
        landed: set[str] = set()  # the fields the intake took (the position of a tracker may be refused: another plugin holds it)
        for at, data in batches:
            done, refused = deliver(conn, addon, at, data)
            fields |= set(data)
            landed |= {field for field, text in done.items() if text.startswith("stored")}
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
                        retry.add(
                            field
                        )  # not "sent": somebody may correct the higher figure (a typo) - then Home Assistant's counts at the next reading
                        _say(conn, addon, st, "odometer.low", "warn", ODOMETER_LOW, now)
                    else:
                        st["said"].pop("odometer.low", None)  # it counts again: a later gap is said again at once
            stored += sum(1 for text in done.values() if text.startswith("stored"))
        if (
            retry
        ):  # something was held back (refused, taken by another plugin, lower than the known odometer): it may be let through at any moment
            st["retry"] = now + interval(
                addon
            )  # (a typo corrected, a claim given up) - offered again at the pace of the setting, with a live connection too
        for key, reading in fresh.items():
            slot = split(key)[0]
            if slot is not None and slot.field not in retry:
                st["sent"][key] = (reading.value, reading.at)
        if "position" in landed and (bound.get("position") or {}).get("options", {}).get("track"):
            _record_track(conn, addon, st, effective, states, bound, now)
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
        again = (
            st["retry"] is not None and now >= st["retry"]
        )  # (what was held back is offered again - from what the live connection knows, nobody asks)
        event = (bool(st["dirty"]) or again) and follows is not None and entities.get(row["id"], set()) <= known
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
    elif slot.kind == "command":
        text = t("hab.cmd_ready")
        origin = t("hab.state", raw=reading.raw) if reading.raw else ""
    elif slot.kind == "state":
        text = t(f"hab.cs.{reading.value}")
        origin = t("hab.state", raw=reading.raw) if reading.raw else ""
    elif slot.kind == "fault":
        text = str(reading.value) or t("hab.nofault")
        origin = t("hab.state", raw=reading.raw) if reading.raw and reading.value else ""
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
    if slot.kind == "command":
        return opts, ""  # nothing to set: the entity is the whole of it
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
    if slot.kind == "fault" and str(form.get(prefix + "invert") or "") in ("1", "on", "true"):
        opts["invert"] = True  # for a yes / no whose "on" means that everything is fine
    if slot.kind == "state":
        words: dict[str, list[str]] = {}
        for name in connectors.CHARGE_STATES:  # the words of this wallbox for each state; the usual ones are understood without them
            listed = [w.strip() for w in re.split(r"[,;\n]", str(form.get(prefix + "w_" + name) or "")) if w.strip()]
            if len(listed) > MAX_YES or any(len(w) > 40 for w in listed):
                return {}, "hab.err_words"
            if listed:
                words[name] = listed
        if words:
            opts["words"] = words
    if slot.key == "position" and str(form.get(prefix + "track") or "") in ("1", "on", "true"):
        opts["track"] = True  # the drives of this tracker become trips (see _record_track)
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


# What an entity says about itself decides which interface it fits (Home Assistant's own words: an odometer is a ``distance`` that only grows, a
# ``total_increasing``; a range goes up and down, a ``measurement``): points for the slot, and against it. The names are what people call such things.
STATE_CLASS_HINT = {
    ("odometer_km", "total_increasing"): 3,
    ("odometer_km", "total"): 2,
    ("odometer_km", "measurement"): -2,
    ("range_km", "total_increasing"): -3,
    ("range_km", "total"): -2,
    ("range_km", "measurement"): 1,
}
NAME_HINT = {  # slot: (words that point to it, words that speak against it)
    "odometer_km": (
        ("odometer", "mileage", "kilometerstand", "laufleistung", "gesamtstrecke"),
        ("trip", "service", "range", "remaining", "reichweite", "until", "inspection", "last", "average", "avg", "fahrt"),
    ),
    "range_km": (("range", "reichweite", "remaining"), ("trip", "odometer", "mileage", "service", "adblue", "kilometerstand")),
}
TRACKER_SOURCES = {
    "gps": 1,
    "router": -3,
    "bluetooth": -3,
    "bluetooth_le": -3,
}  # a tracker that knows where it is, or only that it is connected


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
        score += STATE_CLASS_HINT.get((slot.key, str(attrs.get("state_class") or "")), 0)
        if slot.key in NAME_HINT:
            pointing, against = NAME_HINT[slot.key]
            score += (2 if any(w in haystack for w in pointing) else 0) - (3 if any(w in haystack for w in against) else 0)
        if slot.key == "position" and domain == "device_tracker":
            score += TRACKER_SOURCES.get(str(attrs.get("source_type") or "").lower(), 0)
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
    if str(form.get(prefix + "track") or "") in ("1", "on", "true"):
        opts["track"] = True
    words = {n: v for n in connectors.CHARGE_STATES if (v := str(form.get(prefix + "w_" + n) or "").strip())}
    if words:
        opts["words"] = words
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
                "command": slot.kind == "command",
                "state": slot.kind == "state",
                "states": connectors.CHARGE_STATES if slot.kind == "state" else (),
                "fault": slot.kind == "fault",
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
                if slot.key == "position" and binding and typed is None:
                    entry["row"]["trip"] = trip_status(conn, addon, bound, states, t)
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


def trip_status(conn, addon: dict, bound: dict, states: dict[str, dict] | None, t) -> dict | None:
    """The line under the tracker row: are the drives of this car being recorded, and if not, what is in the way (the questions people ask: the page of the
    trips is off, the ignition entity says off while the car moves, the tracker reports too rarely). None while the option *Record trips* is off."""
    position = bound.get("position")
    if not position or not position["options"].get("track"):
        return None
    if not modules.is_enabled(conn, "trips", addon["vehicle_id"]):
        return {"level": "warn", "text": t("hab.trip.module_off")}
    st = _state.get(addon["id"]) or {}
    notes = st.get("notes") or {}
    words = {
        "ignition": (bound.get("ignition") or {}).get("entity", ""),
        "metres": TRACK_ACCURACY_M,
        "minutes": int(trips.TRIP_GAP.total_seconds() // 60),
    }
    for key, (count, _sentence) in TRIP_NOTES.items():
        if notes.get(key, 0) >= count:
            return {"level": "warn", "text": t(f"hab.trip.{key}", **words)}
    seen = st.get("seen")
    if seen is None:
        return {"level": "idle", "text": t("hab.trip.wait")}
    ignition = bound.get("ignition")
    if ignition and (now := read(cat.BY_KEY["ignition"], ignition["entity"], ignition["options"], states)).ok and not now.value:
        return {"level": "idle", "text": t("hab.trip.parked_now", ignition=words["ignition"])}
    from . import linkmap_ui  # (a page helper; not needed anywhere else here)

    since = (datetime.now(UTC) - timedelta(hours=24)).isoformat(timespec="seconds")
    points = conn.execute("SELECT COUNT(*) FROM vehicle_track WHERE vehicle_id = ? AND ts >= ?", (addon["vehicle_id"], since)).fetchone()[0]
    made = conn.execute("SELECT COUNT(*) FROM trips WHERE vehicle_id = ? AND source = 'track'", (addon["vehicle_id"],)).fetchone()[0]
    return {
        "level": "ok",
        "text": t("hab.trip.ok", ago=linkmap_ui.ago(seen["at"].isoformat(timespec="seconds"), t), points=points, trips=made),
    }


def _empty_row() -> dict:
    return {
        "entity": "",
        "name": "",
        "opts": {},
        "words": {},
        "yes": "",
        "friendly": "",
        "status": {"level": "idle", "text": "", "from": ""},
    }


def _row(slot: cat.Slot, name: str, binding: dict | None, states: dict[str, dict] | None, t, live: bool = True) -> dict:
    opts = binding["options"] if binding else {}
    entity = binding["entity"] if binding else ""
    state = (states or {}).get(entity) or {}
    yes = opts.get("yes", "")
    words = opts.get("words") if isinstance(opts.get("words"), dict) else {}
    return {
        "entity": entity,
        "name": name,
        "opts": opts,
        "words": {n: (", ".join(w) if isinstance(w, list) else str(w)) for n, w in words.items()},
        "yes": ", ".join(yes) if isinstance(yes, list) else str(yes),
        "friendly": str((state.get("attributes") or {}).get("friendly_name") or ""),
        "status": describe(slot, read(slot, entity, opts, states, name), t) if entity and live else _empty_row()["status"],
    }
