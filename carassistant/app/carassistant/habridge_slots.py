"""The interfaces of the Plugin API as slots for entities of Home Assistant - what the Home Assistant plugin (docs/home-assistant.md) offers to bind.

A slot is one interface of a car: a number (with the unit it is stored in), a yes / no, a text, the position, the pressure of a tyre, the state of a door or
window, a warning. For each the catalogue knows which kinds of Home Assistant entities fit (``domains``), which device classes and units point to it (``classes``,
used to suggest entities first) and what a "yes" means (``truth``: for a lock "locked", for a door "open", for the cable "plugged in"). The page of the plugin is
drawn from this list and the reading of the entities is done by it (habridge.py)."""

from __future__ import annotations

from dataclasses import dataclass

from . import connectors


@dataclass(frozen=True)
class Slot:
    key: str  # what the form and the bindings call it: the field of the Plugin API, or "tyre_fl", "position", ...
    field: str  # the field of the Plugin API it fills
    group: str
    kind: str  # number | bool | text | position | coord | tyre | closure | warning
    unit: str = ""  # the unit a number is stored in (km, %, kW, bar, °C, ...)
    domains: tuple[str, ...] = ()  # the kinds of entities of Home Assistant that fit
    classes: tuple[str, ...] = ()  # device classes (and units) that point to this slot: those entities are suggested first
    truth: str = (
        ""  # bool / closure / warning: what "yes" means: on, locked, open, plugged, charging, climate (any: every kind of entity fits)
    )


GROUPS = (
    ("vehicle", "car-side"),
    ("fuel", "gas-station"),
    ("battery", "battery"),
    ("access", "lock"),
    ("position", "map-marker-radius"),
    ("tyres", "car-tire-alert"),
    ("climate", "snowflake"),
    ("service", "wrench"),
)

NUM = ("sensor", "number", "input_number")
FLAG = ("binary_sensor", "switch", "input_boolean", "sensor")

SLOTS: tuple[Slot, ...] = (
    # --- the car itself
    Slot("odometer_km", "odometer_km", "vehicle", "number", "km", NUM, ("distance", "odometer", "mileage")),
    Slot("speed_kmh", "speed_kmh", "vehicle", "number", "km/h", NUM, ("speed",)),
    Slot("heading_deg", "heading_deg", "vehicle", "number", "°", NUM, ("heading", "bearing")),
    Slot("speed_limit_kmh", "speed_limit_kmh", "vehicle", "number", "km/h", NUM, ("speed_limit",)),
    Slot("ignition", "ignition", "vehicle", "bool", "", FLAG, ("running", "power", "ignition"), "on"),
    Slot("vin", "vin", "vehicle", "text", "", ("sensor", "input_text", "text"), ("vin",)),
    # --- fuel and range
    Slot("fuel_level_pct", "fuel_level_pct", "fuel", "number", "%", NUM, ("fuel", "tank")),
    Slot("fuel_amount", "fuel_amount", "fuel", "number", "l", NUM, ("volume", "volume_storage", "fuel")),
    Slot("range_km", "range_km", "fuel", "number", "km", NUM, ("distance", "range")),
    Slot("consumption_l_100km", "consumption_l_100km", "fuel", "number", "l/100km", NUM, ("consumption",)),
    Slot("adblue_level_pct", "adblue_level_pct", "fuel", "number", "%", NUM, ("adblue",)),
    Slot("adblue_range_km", "adblue_range_km", "fuel", "number", "km", NUM, ("adblue",)),
    # --- battery and charging (an electric car, a hybrid, a wallbox)
    Slot("battery_pct", "battery_pct", "battery", "number", "%", NUM, ("battery", "state_of_charge", "soc")),
    Slot("charge_power_kw", "charge_power_kw", "battery", "number", "kW", NUM, ("power", "charging_power")),
    Slot("charge_limit_pct", "charge_limit_pct", "battery", "number", "%", NUM, ("charge_limit", "target")),
    Slot("charge_minutes_left", "charge_minutes_left", "battery", "number", "min", NUM, ("duration", "time_remaining")),
    Slot("charging", "charging", "battery", "bool", "", FLAG, ("battery_charging", "charging"), "charging"),
    Slot("plugged", "plugged", "battery", "bool", "", FLAG, ("plug", "connectivity", "cable"), "plugged"),
    Slot("battery_12v_v", "battery_12v_v", "battery", "number", "V", NUM, ("voltage",)),
    # --- doors, windows, lock
    Slot("locked", "locked", "access", "bool", "", ("lock", *FLAG), ("lock",), "locked"),
    Slot("parking_brake", "parking_brake", "access", "bool", "", FLAG, ("parking_brake",), "on"),
    Slot("doors", "doors", "access", "closure", "", ("binary_sensor", "cover", "sensor"), ("door", "opening", "garage_door"), "open"),
    Slot("windows", "windows", "access", "closure", "", ("binary_sensor", "cover", "sensor"), ("window", "opening"), "open"),
    Slot("lights", "lights", "access", "closure", "", ("binary_sensor", "light", "switch"), ("light",), "on"),
    # --- position
    Slot("position", "position", "position", "position", "", ("device_tracker", "person", "geo_location", "sensor"), ("location", "gps")),
    # ... or the two halves of it as sensors of their own (used only while no tracker is chosen)
    Slot("position_lat", "position", "position", "coord", "°", NUM, ("latitude",)),
    Slot("position_lon", "position", "position", "coord", "°", NUM, ("longitude",)),
    # --- tyres (pressure in bar)
    Slot("tyre_fl", "tyre_pressure_bar", "tyres", "tyre", "bar", NUM, ("pressure", "tire", "tyre")),
    Slot("tyre_fr", "tyre_pressure_bar", "tyres", "tyre", "bar", NUM, ("pressure", "tire", "tyre")),
    Slot("tyre_rl", "tyre_pressure_bar", "tyres", "tyre", "bar", NUM, ("pressure", "tire", "tyre")),
    Slot("tyre_rr", "tyre_pressure_bar", "tyres", "tyre", "bar", NUM, ("pressure", "tire", "tyre")),
    # --- temperatures and climate
    Slot("outside_temp_c", "outside_temp_c", "climate", "number", "°C", (*NUM, "climate", "weather"), ("temperature",)),
    Slot("cabin_temp_c", "cabin_temp_c", "climate", "number", "°C", (*NUM, "climate"), ("temperature",)),
    Slot("target_temp_c", "target_temp_c", "climate", "number", "°C", (*NUM, "climate"), ("temperature",)),
    Slot("coolant_temp_c", "coolant_temp_c", "climate", "number", "°C", NUM, ("temperature",)),
    Slot("oil_temp_c", "oil_temp_c", "climate", "number", "°C", NUM, ("temperature",)),
    Slot("climate_on", "climate_on", "climate", "bool", "", ("climate", *FLAG), ("climate",), "climate"),
    # --- service and warnings
    Slot("service_due_days", "service_due_days", "service", "number", "d", NUM, ("duration", "service")),
    Slot("service_due_km", "service_due_km", "service", "number", "km", NUM, ("distance", "service")),
    Slot("oil_change_due_days", "oil_change_due_days", "service", "number", "d", NUM, ("duration", "oil")),
    Slot("oil_change_due_km", "oil_change_due_km", "service", "number", "km", NUM, ("distance", "oil")),
    Slot("oil_level_pct", "oil_level_pct", "service", "number", "%", NUM, ("oil",)),
    Slot("oil_warning", "oil_warning", "service", "bool", "", FLAG, ("problem", "oil"), "on"),
    Slot("warnings", "warnings", "service", "warning", "", ("binary_sensor",), ("problem", "safety", "tamper"), "any"),
)

BY_KEY = {s.key: s for s in SLOTS}
TYRE_WHEEL = {"tyre_fl": "fl", "tyre_fr": "fr", "tyre_rl": "rl", "tyre_rr": "rr"}
LIST_KINDS = (
    "closure",
    "warning",
)  # a slot of these kinds is a list of named rows (front_left, trunk, tyre_pressure ...), each bound to an entity
MAX_ROWS = connectors.MAX_CLOSURES  # rows of one door / window / light / warning list
# names offered for the rows of a list (the person may type others: lower-case letters, digits and _)
CLOSURE_NAMES = {
    "doors": ("front_left", "front_right", "rear_left", "rear_right", "trunk", "hood"),
    "windows": ("front_left", "front_right", "rear_left", "rear_right", "roof"),
    "lights": ("head", "tail", "hazard", "fog"),
}


def groups(keys=None) -> list[dict]:
    """The groups in order, each with its slots - only the groups named in ``keys`` when given (a package may offer a part of the catalogue)."""
    out = []
    for group_id, icon in GROUPS:
        if keys is not None and group_id not in keys:
            continue
        out.append({"id": group_id, "icon": icon, "slots": [s for s in SLOTS if s.group == group_id]})
    return [g for g in out if g["slots"]]
