"""Publish one Home Assistant device per vehicle through MQTT discovery."""

from __future__ import annotations

import contextlib
import json
import logging
import secrets
import socket
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime

import paho.mqtt.client as mqtt

from . import __version__, config, connectors, db, events, fuelstats, modules, status, summary, units

log = logging.getLogger(__name__)

DISCOVERY_PREFIX = "homeassistant"
STATE_PREFIX = "carassistant"
AVAILABILITY_TOPIC = f"{STATE_PREFIX}/status"


@dataclass(frozen=True)
class SensorDef:
    key: str
    name: str
    component: str = "sensor"
    unit: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    icon: str | None = None
    category: str | None = None  # "diagnostic": listed under Diagnostics in Home Assistant
    enabled: bool = True  # False: the entity exists but is switched off in Home Assistant until the owner enables it
    precision: int | None = None
    live: bool = False  # only created once the car (a plugin) has delivered a value; never an empty "unknown" entity
    attributes: bool = False  # the sensor also publishes a JSON object of attributes (``json_attributes_topic``)


def _s(key, name, **kw) -> SensorDef:
    return SensorDef(key, name, **kw)


def _b(key, name, device_class=None, **kw) -> SensorDef:
    return SensorDef(key, name, component="binary_sensor", device_class=device_class, **kw)


TYRES = (("fl", "front left"), ("fr", "front right"), ("rl", "rear left"), ("rr", "rear right"))

# One curated list. The first block exists for every car; the rest ("live") appears by itself as soon as a plugin or a bound
# Home Assistant entity delivers that value. Less useful values are created switched off (enabled=False) or as diagnostics.
SENSORS: tuple[SensorDef, ...] = (
    _s("odometer", "Odometer", unit="km", device_class="distance", state_class="total_increasing", icon="mdi:counter", precision=0, live=True),
    _s("inspection_days", "Days until inspection", unit="d", state_class="measurement", icon="mdi:calendar-clock", live=True),
    _s("inspection_date", "Next inspection", device_class="date", icon="mdi:calendar-check", live=True),
    _s("attention_count", "Items needing attention", state_class="measurement", icon="mdi:alert-circle-outline"),
    _b("attention", "Attention", "problem"),
    _s("avg_consumption", "Average consumption", state_class="measurement", icon="mdi:gas-station", precision=1, live=True),
    _s("fuel_spent_month", "Fuel cost this month", state_class="measurement", icon="mdi:cash", precision=2, live=True),
    _s("fuel_level", "Fuel level", unit="%", state_class="measurement", icon="mdi:gauge", precision=0),
    _s("range_km", "Range", unit="km", device_class="distance", state_class="measurement", icon="mdi:map-marker-distance", precision=0),
    _s("battery_pct", "Battery", unit="%", device_class="battery", state_class="measurement", live=True),
    _b("charging", "Charging", "battery_charging", live=True),
    _b("plugged", "Plugged in", "plug", live=True),
    _s("charge_power_kw", "Charging power", unit="kW", device_class="power", state_class="measurement", live=True, precision=1),
    _s("charge_limit_pct", "Charge limit", unit="%", state_class="measurement", icon="mdi:battery-charging-80", live=True, category="diagnostic"),
    _s("charge_minutes_left", "Charging time left", unit="min", device_class="duration", state_class="measurement", live=True),
    _b("ignition", "Ignition", "power", live=True),
    _b("locked", "Unlocked", "lock", live=True),
    _b("doors", "Doors", "door", live=True),
    _b("windows", "Windows", "window", live=True),
    _b("parking_brake", "Parking brake", icon="mdi:car-brake-parking", live=True),
    _b("climate_on", "Climate", "running", icon="mdi:air-conditioner", live=True),
    _s("speed_kmh", "Speed", unit="km/h", device_class="speed", state_class="measurement", live=True, enabled=False, precision=0),
    _s("outside_temp_c", "Outside temperature", unit="°C", device_class="temperature", state_class="measurement", live=True, precision=1),
    _s("cabin_temp_c", "Cabin temperature", unit="°C", device_class="temperature", state_class="measurement", live=True, precision=1),
    _s("battery_12v_v", "12 V battery", unit="V", device_class="voltage", state_class="measurement", live=True, category="diagnostic", precision=1),
    _s("coolant_temp_c", "Coolant temperature", unit="°C", device_class="temperature", state_class="measurement", live=True, category="diagnostic", enabled=False),
    _s("oil_temp_c", "Oil temperature", unit="°C", device_class="temperature", state_class="measurement", live=True, category="diagnostic", enabled=False),
    _s("oil_level_pct", "Oil level", unit="%", state_class="measurement", icon="mdi:oil-level", live=True, category="diagnostic"),
    _b("oil_warning", "Oil warning", "problem", live=True),
    _s("adblue_level_pct", "AdBlue level", unit="%", state_class="measurement", icon="mdi:water-percent", live=True),
    _s("adblue_range_km", "AdBlue range", unit="km", device_class="distance", state_class="measurement", icon="mdi:water-percent", live=True, precision=0),
    _s("service_due_days", "Days until service", unit="d", state_class="measurement", icon="mdi:wrench-clock", live=True),
    _s("oil_change_due_days", "Days until oil change", unit="d", state_class="measurement", icon="mdi:oil", live=True),
    _s("oil_change_due_km", "Distance to oil change", unit="km", device_class="distance", state_class="measurement", icon="mdi:oil", live=True, precision=0),
    _s("service_due_km", "Distance to service", unit="km", device_class="distance", state_class="measurement", icon="mdi:wrench", live=True, precision=0),
    _s("warnings", "Warnings", state_class="measurement", icon="mdi:alert-outline", live=True),
    SensorDef("last_notification", "Last notification", icon="mdi:bell-outline", attributes=True),
    # computed by the app from its own records (the fuel log, tasks, appointments, trips, tyres): they exist as soon as there is something to show
    _s("last_fill_date", "Last fill-up", device_class="date", icon="mdi:gas-station", live=True),
    _s("last_fill_amount", "Last fill-up amount", state_class="measurement", icon="mdi:gas-station", live=True, precision=1),
    _s("last_fill_price", "Last price per unit", state_class="measurement", icon="mdi:cash", live=True, precision=3),
    _s("last_consumption", "Last consumption", state_class="measurement", icon="mdi:gauge", live=True, precision=1),
    _s("cost_per_100km", "Cost per 100 km", state_class="measurement", icon="mdi:cash-multiple", live=True, precision=2),
    _s("fuel_spent_total", "Fuel cost total", state_class="total", icon="mdi:cash", live=True, precision=2),
    _s("costs_year", "Costs this year", state_class="total", icon="mdi:cash-register", live=True, precision=2),
    _s("km_month", "Distance this month", unit="km", device_class="distance", state_class="measurement", icon="mdi:map-marker-distance", live=True, precision=0),
    _s("km_year", "Distance this year", unit="km", device_class="distance", state_class="measurement", icon="mdi:map-marker-distance", live=True, precision=0),
    _s("next_task_days", "Days until next task", unit="d", state_class="measurement", icon="mdi:wrench-clock", live=True, attributes=True),
    _s("next_task_km", "Distance to next task", unit="km", device_class="distance", state_class="measurement", icon="mdi:wrench", live=True, precision=0, attributes=True),
    _s("next_appointment_days", "Days until next appointment", unit="d", state_class="measurement", icon="mdi:calendar-clock", live=True, attributes=True),
    _s("last_trip_km", "Last trip distance", unit="km", device_class="distance", state_class="measurement", icon="mdi:map-marker-path", live=True, precision=1, attributes=True),
    _s("tires_mounted", "Mounted tyres", icon="mdi:tire", live=True),
    *(
        _s(f"tyre_{k}", f"Tyre pressure {label}", unit="bar", device_class="pressure", state_class="measurement", live=True, precision=1)
        for k, label in TYRES
    ),
)  # fmt: skip
BY_KEY = {s.key: s for s in SENSORS}
TRACKER_KEY = "position"  # the device tracker (the car on the Home Assistant map) - not a sensor, so not in SENSORS

NAMES_DE = {
    "Odometer": "Kilometerstand", "Days until inspection": "Tage bis zur HU", "Next inspection": "Nächste HU",
    "Items needing attention": "Offene Punkte", "Attention": "Aufmerksamkeit", "Average consumption": "Ø Verbrauch",
    "Fuel cost this month": "Tankkosten diesen Monat", "Fuel level": "Tankfüllung", "Range": "Reichweite",
    "Battery": "Batterie", "Charging": "Lädt", "Plugged in": "Angesteckt", "Charging power": "Ladeleistung",
    "Charge limit": "Ladegrenze", "Charging time left": "Restladezeit", "Ignition": "Zündung", "Unlocked": "Entriegelt",
    "Doors": "Türen", "Windows": "Fenster", "Parking brake": "Handbremse", "Climate": "Klimatisierung",
    "Speed": "Geschwindigkeit", "Outside temperature": "Außentemperatur", "Cabin temperature": "Innentemperatur",
    "12 V battery": "12-V-Batterie", "Coolant temperature": "Kühlmitteltemperatur", "Oil temperature": "Öltemperatur",
    "Oil level": "Ölstand", "Oil warning": "Ölwarnung", "AdBlue level": "AdBlue-Stand", "AdBlue range": "AdBlue-Reichweite",
    "Last fill-up": "Letzte Tankung", "Last fill-up amount": "Menge der letzten Tankung", "Last price per unit": "Letzter Preis je Einheit",
    "Last consumption": "Letzter Verbrauch", "Cost per 100 km": "Kosten je 100 km", "Fuel cost total": "Tankkosten gesamt",
    "Costs this year": "Kosten dieses Jahr", "Distance this month": "Strecke diesen Monat", "Distance this year": "Strecke dieses Jahr",
    "Days until next task": "Tage bis zur nächsten Aufgabe", "Distance to next task": "Strecke bis zur nächsten Aufgabe",
    "Days until next appointment": "Tage bis zum nächsten Termin",     "Last trip distance": "Strecke der letzten Fahrt", "Mounted tyres": "Montierte Reifen",
    "Days until service": "Tage bis zum Service", "Distance to service": "Strecke bis zum Service",
    "Days until oil change": "Tage bis zum Ölwechsel", "Distance to oil change": "Strecke bis zum Ölwechsel", "Warnings": "Warnungen", "Position": "Position", "Last notification": "Letzte Benachrichtigung",
    "Tyre pressure front left": "Reifendruck vorne links", "Tyre pressure front right": "Reifendruck vorne rechts",
    "Tyre pressure rear left": "Reifendruck hinten links", "Tyre pressure rear right": "Reifendruck hinten rechts",
}  # fmt: skip


def display_name(name: str) -> str:
    return NAMES_DE.get(name, name) if config.language() == "de" else name


def consumption_unit(fuel_type: str) -> str:
    return {"electric": "kWh/100km", "cng": "kg/100km"}.get(fuel_type, "L/100km")


def _any_open(raw: str | None) -> str | None:
    flags = status.parse_flags(raw)
    return None if not flags else ("ON" if any(flags.values()) else "OFF")


def compute_values(conn: sqlite3.Connection, vehicle: sqlite3.Row, ref: date | None = None) -> dict[str, str | None]:
    ref = ref or date.today()
    s = summary.vehicle_summary(conn, vehicle, ref)
    stats = fuelstats.overall(conn, vehicle["id"])
    info = s["inspection_info"]
    live = s["live"]

    def fmt(value: float | None, digits: int = 1) -> str | None:
        return None if value is None else f"{value:.{digits}f}"

    def yes_no(key: str, on: str = "yes") -> str | None:
        return None if live.get(key) not in ("yes", "no") else ("ON" if live[key] == on else "OFF")

    values: dict[str, str | None] = {
        "odometer": None if s["odometer"] is None else str(s["odometer"]),
        "inspection_days": None if info is None else str(info.days_left),
        "inspection_date": None if info is None else info.due_date.isoformat(),
        "attention_count": str(len(s["attention"])),
        "attention": "ON" if s["overdue"] else "OFF",
        "avg_consumption": fmt(stats["avg_per_100"]),
        "fuel_spent_month": fmt(fuelstats.month_spent(conn, vehicle["id"], ref.strftime("%Y-%m")), 2) if stats["fills"] else None,
        "fuel_level": live.get("fuel_level"),
        "range_km": live.get("range_km"),
        "ignition": None if live.get("ignition") not in ("on", "off") else ("ON" if live["ignition"] == "on" else "OFF"),
        "locked": None if live.get("locked") not in ("locked", "unlocked") else ("ON" if live["locked"] == "unlocked" else "OFF"),
        "doors": _any_open(live.get("doors")),
        "windows": _any_open(live.get("windows")),
    }
    for key in connectors.BOOLS:
        values[key] = yes_no(key)
    for _api, (live_key, _lo, _hi) in connectors.NUMBERS.items():
        if live_key in BY_KEY and live_key not in values:
            values[live_key] = live.get(live_key)
    notice = notice_record(conn, vehicle["id"])
    values["last_notification"] = notice["text"] if notice else None
    values.update(_computed_values(conn, vehicle, s, stats, ref))
    values["speed_kmh"] = live.get("speed_kmh")
    values["warnings"] = str(len(status.parse_warnings(live["warnings"]))) if live.get("warnings") else None
    tyres = status.parse_numbers(live.get("tyre_pressure_bar"))
    for k, _label in TYRES:
        values[f"tyre_{k}"] = None if k not in tyres else f"{tyres[k]:.2f}"
    return values


REBUILD_WAIT = 6.0  # seconds Home Assistant gets to forget the removed entities before they come back
NOTICE_HISTORY = 10
NOTICE_STATE_MAX = 250  # a Home Assistant state is at most 255 characters


def notice_record(conn: sqlite3.Connection, vehicle_id: int) -> dict | None:
    """The notifications of a car as the Home Assistant sensor shows them: ``{n, time, text, lines, history}`` (None before the first one)."""
    raw = db.get_setting(conn, f"mqtt.notice.{vehicle_id}", "") or ""
    try:
        data = json.loads(raw) if raw else None
    except ValueError:
        return None
    return data if isinstance(data, dict) and data.get("text") else None


def add_notice(conn: sqlite3.Connection, vehicle_id: int, lines: list[str], now: datetime) -> dict:
    """Remember what the car's notification sensor says now (kept, so it is still there after a restart) and keep the last few as history."""
    old = notice_record(conn, vehicle_id) or {"n": 0, "history": []}
    text = " · ".join(lines)
    record = {
        "n": int(old.get("n") or 0) + 1,
        "time": now.isoformat(timespec="seconds"),
        "text": text[:NOTICE_STATE_MAX],
        "lines": lines[:20],
        "history": ([{"time": old["time"], "text": old["text"]}] if old.get("time") else []) + list(old.get("history") or []),
    }
    record["history"] = record["history"][: NOTICE_HISTORY - 1]
    db.set_setting(conn, f"mqtt.notice.{vehicle_id}", json.dumps(record, ensure_ascii=False))
    return record


def sensor_attributes(conn: sqlite3.Connection, vehicle: sqlite3.Row, key: str) -> dict | None:
    """The attributes a sensor carries besides its value (None: nothing to publish, the sensor stays without a value)."""
    ref = date.today()
    vid = vehicle["id"]
    if key == "last_notification":
        record = notice_record(conn, vid)
        return notice_attributes(record) if record else None
    if key in ("next_task_days", "next_task_km"):
        task = next_task(conn, vid, summary.current_odometer(conn, vid), ref)
        if not task:
            return None
        info = task["info"]
        return {
            "task": task["title"],
            "due_date": info.due_date.isoformat() if info.due_date else None,
            "due_km": info.due_km,
            "status": info.status,
        }
    if key == "next_appointment_days":
        appointment = next_appointment(conn, vid, ref)
        if not appointment:
            return None
        info = appointment["info"]
        return {"title": appointment["title"], "kind": appointment["kind"], "date": info.due_date.isoformat(), "status": info.status}
    if key == "last_trip_km":
        trip = conn.execute(
            "SELECT date, start_time, end_time, start_place, end_place, avg_kmh, consumption_l100 FROM trips WHERE vehicle_id = ? AND distance_km IS NOT NULL ORDER BY date DESC, id DESC LIMIT 1",
            (vid,),
        ).fetchone()
        if not trip:
            return None
        names = {
            "date": "date",
            "start_time": "start",
            "end_time": "end",
            "start_place": "from",
            "end_place": "to",
            "avg_kmh": "average_speed_kmh",
            "consumption_l100": "consumption",
        }
        return {names[k]: trip[k] for k in names if trip[k] not in (None, "")}
    return None


def notice_attributes(record: dict) -> dict:
    return {
        "message": "\n".join(record["lines"]),
        "lines": record["lines"],
        "time": record["time"],
        "count": record["n"],
        "history": record["history"],
    }


def _computed_values(conn: sqlite3.Connection, vehicle: sqlite3.Row, s: dict, stats: dict, ref: date) -> dict[str, str | None]:
    """What the app works out from its own records (not from the car): the last fill-up, the costs, the next task and appointment, the last trip, the
    mounted tyres. A value is None when there is nothing to say - the sensor is then not created."""
    vid = vehicle["id"]
    off = modules.disabled(conn, vid)
    out: dict[str, str | None] = {}

    def num(value, digits: int = 1) -> str | None:
        return None if value is None else f"{value:.{digits}f}"

    if "fuel" not in off:
        last = conn.execute(
            "SELECT date, amount, price_per_unit FROM fuel WHERE vehicle_id = ? AND amount IS NOT NULL ORDER BY date DESC, COALESCE(odometer_km, 0) DESC, id DESC LIMIT 1",
            (vid,),
        ).fetchone()
        out["last_fill_date"] = last["date"][:10] if last else None
        out["last_fill_amount"] = num(last["amount"], 2) if last else None
        out["last_fill_price"] = num(last["price_per_unit"], 3) if last and last["price_per_unit"] else None
        out["last_consumption"] = num(stats["last_per_100"])
        out["cost_per_100km"] = num(stats["cost_per_100"], 2)
        out["fuel_spent_total"] = num(stats["total_spent"], 2) if stats["total_spent"] else None
    if "report" not in off:
        months = fuelstats.costs(conn, vid, "month", ref.month, ref)
        total = sum(m["fuel"] + m["service"] + m["mods"] + m["parts"] for m in months)
        out["costs_year"] = num(total, 2) if total else None
    if "trips" not in off:
        month = fuelstats.kilometres(conn, vid, "month", 1, ref)
        year = [k for _p, k in fuelstats.kilometres(conn, vid, "month", ref.month, ref) if k is not None]
        out["km_month"] = None if not month or month[0][1] is None else f"{month[0][1]:.0f}"
        out["km_year"] = f"{sum(year):.0f}" if year else None
        trip = conn.execute(
            "SELECT distance_km FROM trips WHERE vehicle_id = ? AND distance_km IS NOT NULL ORDER BY date DESC, id DESC LIMIT 1", (vid,)
        ).fetchone()
        out["last_trip_km"] = num(trip["distance_km"]) if trip else None
    task = next_task(conn, vid, s["odometer"], ref) if "tasks" not in off else None
    out["next_task_days"] = None if not task or task["info"].days_left is None else str(task["info"].days_left)
    out["next_task_km"] = None if not task or task["info"].km_left is None else str(task["info"].km_left)
    appointment = next_appointment(conn, vid, ref) if "appointments" not in off else None
    out["next_appointment_days"] = None if not appointment else str(appointment["info"].days_left)
    mounted = s.get("tires")
    out["tires_mounted"] = " ".join(x for x in (mounted["name"], mounted["size"]) if x)[:120] or None if mounted else None
    return out


def next_task(conn: sqlite3.Connection, vehicle_id: int, odometer: int | None, ref: date) -> dict | None:
    """The task that comes due first (by date, else by distance), also when it is not due soon: ``{title, info}``."""
    index = summary.service_index(conn, vehicle_id)
    best = None
    for task in conn.execute("SELECT * FROM tasks WHERE vehicle_id = ? AND muted = 0", (vehicle_id,)):
        info = summary.task_due(conn, vehicle_id, task, odometer, ref, index)
        if info.days_left is None and info.km_left is None:
            continue
        rank = info.days_left if info.days_left is not None else 10**6 + (info.km_left or 0) // 20
        if best is None or rank < best[0]:
            best = (rank, {"title": task["title"], "info": info})
    return best[1] if best else None


def next_appointment(conn: sqlite3.Connection, vehicle_id: int, ref: date) -> dict | None:
    row = conn.execute(
        "SELECT * FROM appointments WHERE vehicle_id = ? AND done = 0 AND due_date IS NOT NULL ORDER BY due_date LIMIT 1", (vehicle_id,)
    ).fetchone()
    if row is None:
        return None
    try:
        return {"title": row["title"], "kind": row["kind"], "info": summary.appointment_due(row, ref)}
    except ValueError:
        return None


def position_attributes(conn: sqlite3.Connection, vehicle: sqlite3.Row) -> dict | None:
    """What the device tracker publishes: latitude / longitude plus speed, heading and the time of the fix."""
    row = conn.execute("SELECT value, updated FROM live WHERE vehicle_id = ? AND key = 'position'", (vehicle["id"],)).fetchone()
    if not row or not row["value"]:
        return None
    try:
        lat, lon = (float(x) for x in row["value"].split(","))
    except ValueError:
        return None
    attrs: dict = {"latitude": lat, "longitude": lon, "gps_accuracy": 10, "last_update": row["updated"]}
    for key, name in (("speed_kmh", "speed"), ("heading_deg", "heading")):
        r = conn.execute("SELECT value FROM live WHERE vehicle_id = ? AND key = ?", (vehicle["id"], key)).fetchone()
        if r and r["value"] not in (None, ""):
            attrs[name] = float(r["value"])
    return attrs


def _without_none(value):
    """Home Assistant checks every discovery message and refuses the WHOLE message for a ``null`` where it expects a text (a car without a model
    gave ``"model": null``: the broker got everything, Home Assistant created nothing). So a missing value is simply left out."""
    if isinstance(value, dict):
        return {k: _without_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_without_none(v) for v in value if v is not None]
    return value


def _device(vehicle: sqlite3.Row) -> dict:
    return _without_none(
        {
            "identifiers": [f"carassistant_{vehicle['id']}"],
            "name": vehicle["name"],
            "manufacturer": vehicle["make"] or "Car Assistant",
            "model": " ".join(x for x in (vehicle["model"], vehicle["variant"]) if x) or None,
            "sw_version": __version__,
        }
    )


def discovery_topic(vehicle_id: int, sensor: SensorDef) -> str:
    return f"{DISCOVERY_PREFIX}/{sensor.component}/carassistant_{vehicle_id}/{sensor.key}/config"


def tracker_topic(vehicle_id: int) -> str:
    return f"{DISCOVERY_PREFIX}/device_tracker/carassistant_{vehicle_id}/{TRACKER_KEY}/config"


def state_topic(vehicle_id: int, key: str) -> str:
    return f"{STATE_PREFIX}/{vehicle_id}/{key}/state"


def attributes_topic(vehicle_id: int) -> str:
    return f"{STATE_PREFIX}/{vehicle_id}/{TRACKER_KEY}/attributes"


def sensor_attributes_topic(vehicle_id: int, key: str) -> str:
    return f"{STATE_PREFIX}/{vehicle_id}/{key}/attributes"


def _origin() -> dict:
    return {"name": "Car Assistant", "sw_version": __version__, "url": "https://github.com/Matze89x/ha-car-assistant"}


def discovery_payload(vehicle: sqlite3.Row, sensor: SensorDef) -> dict:
    payload: dict = {
        "name": display_name(sensor.name),
        "unique_id": f"carassistant_{vehicle['id']}_{sensor.key}",
        "has_entity_name": True,
        "state_topic": state_topic(vehicle["id"], sensor.key),
        "availability_topic": AVAILABILITY_TOPIC,
        "device": _device(vehicle),
        "origin": _origin(),
    }
    unit = sensor.unit
    if sensor.key in ("avg_consumption", "last_consumption"):
        unit = consumption_unit(vehicle["fuel_type"])
    elif sensor.key in ("fuel_spent_month", "fuel_spent_total", "costs_year"):
        unit = units.default_currency()
    elif sensor.key == "last_fill_amount":
        unit = {"electric": "kWh", "cng": "kg"}.get(vehicle["fuel_type"], "L")
    elif sensor.key == "last_fill_price":
        unit = f"{units.default_currency()}/{ {'electric': 'kWh', 'cng': 'kg'}.get(vehicle['fuel_type'], 'L') }"
    elif sensor.key == "cost_per_100km":
        unit = f"{units.default_currency()}/100 km"
    if unit == "d" and config.language() == "de":
        unit = "Tage"  # Home Assistant would show its own English "days" for "d"
    if unit:
        payload["unit_of_measurement"] = unit
    for key, value in (
        ("device_class", sensor.device_class),
        ("state_class", sensor.state_class),
        ("icon", sensor.icon),
        ("entity_category", sensor.category),
    ):
        if value:
            payload[key] = value
    if sensor.precision is not None and sensor.component == "sensor":
        payload["suggested_display_precision"] = sensor.precision
    if not sensor.enabled:
        payload["enabled_by_default"] = False
    if sensor.component == "binary_sensor":
        payload.update(payload_on="ON", payload_off="OFF")
    if sensor.attributes:
        payload["json_attributes_topic"] = sensor_attributes_topic(vehicle["id"], sensor.key)
    return _without_none(payload)


def tracker_payload(vehicle: sqlite3.Row) -> dict:
    """The car on the Home Assistant map: a device tracker whose position is read from one JSON attributes topic."""
    return _without_none(
        {
            "name": display_name("Position"),
            "unique_id": f"carassistant_{vehicle['id']}_position_tracker",
            "has_entity_name": True,
            "json_attributes_topic": attributes_topic(vehicle["id"]),
            "availability_topic": AVAILABILITY_TOPIC,
            "source_type": "gps",
            "icon": "mdi:car",
            "device": _device(vehicle),
            "origin": _origin(),
        }
    )


# the rough groups under System -> MQTT; a sensor that is in no group (the odometer, the notification sensor) is always sent
GROUP_OF = {
    **dict.fromkeys(
        (
            "inspection_days",
            "inspection_date",
            "attention",
            "attention_count",
            "next_task_days",
            "next_task_km",
            "next_appointment_days",
            "tires_mounted",
        ),
        "service",
    ),
    **dict.fromkeys(("avg_consumption", "fuel_spent_month"), "fuel"),
    **dict.fromkeys(
        (
            "last_fill_date",
            "last_fill_amount",
            "last_fill_price",
            "last_consumption",
            "cost_per_100km",
            "fuel_spent_total",
            "costs_year",
            "km_month",
            "km_year",
            "last_trip_km",
        ),
        "stats",
    ),
}


def group_of(sensor: SensorDef) -> str | None:
    """The group a sensor is switched with: what the car (a plugin) delivers is ``live``; the app's own records are ``service``, ``fuel`` or ``stats``."""
    if sensor.key in ("odometer", "last_notification"):
        return None
    return GROUP_OF.get(sensor.key) or ("live" if sensor.key in ("fuel_level", "range_km") or sensor.live else None)


# sensors that belong to a function: when the function is switched off for the car, they are not created (or are taken away again)
BELONGS_TO = {
    "inspection_days": "appointments",
    "inspection_date": "appointments",
    "avg_consumption": "fuel",
    "fuel_spent_month": "fuel",
    "last_fill_date": "fuel",
    "last_fill_amount": "fuel",
    "last_fill_price": "fuel",
    "last_consumption": "fuel",
    "cost_per_100km": "fuel",
    "fuel_spent_total": "fuel",
    "costs_year": "report",
    "km_month": "trips",
    "km_year": "trips",
    "last_trip_km": "trips",
    "next_task_days": "tasks",
    "next_task_km": "tasks",
    "next_appointment_days": "appointments",
    "tires_mounted": "tires",
}


def wanted_sensors(
    vehicle: sqlite3.Row, values: dict[str, str | None] | None = None, off: frozenset[str] | set[str] = frozenset()
) -> tuple[SensorDef, ...]:
    """Fuel level / range exist when an entity is bound or a value arrived; every other live sensor only once it has a value."""
    out = []
    groups_off = config.ha_groups_off()
    for s in SENSORS:
        if BELONGS_TO.get(s.key) in off or group_of(s) in groups_off:
            continue
        if s.key in ("attention", "attention_count") and {"appointments", "tasks"} <= set(off):
            continue
        if s.key == "last_notification" and not config.ha_notice_sensor_enabled():
            continue  # switched off (System tab): no entity in Home Assistant
        if s.key == "fuel_level":
            ok = bool(vehicle["bind_fuel_level"]) or bool(values and values.get(s.key) is not None)
        elif s.key == "range_km":
            ok = bool(vehicle["bind_range"]) or bool(values and values.get(s.key) is not None)
        elif s.live:
            ok = bool(values and values.get(s.key) is not None)
        else:
            ok = True
        if ok:
            out.append(s)
    return tuple(out)


def diagnose(host: str, port: int) -> str:
    """Why a broker is not reached, as a short key (see ``mqtt.err_*`` texts): the plain TCP connection tells the cause."""
    try:
        with socket.create_connection((host, port), timeout=4):
            return "protocol"  # the port answers, but the MQTT talk (or its encryption) failed: not a broker, or the wrong port
    except socket.gaierror:
        return "dns"
    except ConnectionRefusedError:
        return "refused"
    except TimeoutError:
        return "timeout"
    except OSError:
        return "unreach"


class Publisher:
    def __init__(self) -> None:
        self._client: mqtt.Client | None = None
        self._connected = threading.Event()
        self._lock = threading.Lock()
        self._sent: dict[str, str] = {}  # topic -> last payload sent (cleared on every (re)connect)
        self.last_error = ""  # why the broker is not reached: auth | refused | dns | timeout | unreach | protocol | other
        self._target: tuple[str, int] | None = None
        self._last_probe = 0.0
        self._paused_until = 0.0  # while entities are taken out of Home Assistant and put back, nothing is published (see rebuild)

    def start(self) -> bool:
        self.last_error = ""
        settings = config.mqtt_settings()
        if not config.mqtt_discovery_enabled() or not settings:
            log.info("MQTT discovery disabled or no broker available")
            return False
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self._client_id())
        if settings["user"]:
            client.username_pw_set(settings["user"], settings["password"])
        if settings.get("tls"):
            client.tls_set()  # encrypted: the certificate must come from an authority the system knows
        client.will_set(AVAILABILITY_TOPIC, "offline", retain=True)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_connect_fail = self._on_connect_fail
        client.reconnect_delay_set(min_delay=2, max_delay=60)
        self._target = (settings["host"], settings["port"])
        try:
            client.connect_async(settings["host"], settings["port"], keepalive=60)
            client.loop_start()
        except (OSError, ValueError) as exc:  # a broken setting must never stop the app
            log.warning("MQTT: cannot start (%s)", exc)
            self.last_error = "other"
            return False
        self._client = client
        timer = threading.Timer(8.0, self._still_waiting, args=(client,))  # a broker that never answers: say why after a few seconds
        timer.daemon = True
        timer.start()
        return True

    def _still_waiting(self, client) -> None:
        if self._client is client and not self.connected and not self.last_error:
            self._last_probe = time.monotonic()
            self._probe()

    @staticmethod
    def _client_id() -> str:
        """One id per installation: two apps (for example the released and the Developer add-on) on the same broker must not throw each other out."""
        with db.tx() as conn:
            known = db.get_setting(conn, "mqtt.client_id")
            if not known:
                known = "carassistant-" + secrets.token_hex(4)
                db.set_setting(conn, "mqtt.client_id", known)
        return known

    def _on_connect_fail(self, client, userdata) -> None:
        """The TCP connection could not be made (or the answer was no MQTT): find out why, once in a while, and keep the reason for the page."""
        now = time.monotonic()
        if now - self._last_probe < 30 or not self._target:
            return
        self._last_probe = now
        threading.Thread(target=self._probe, name="mqtt-probe", daemon=True).start()

    def _probe(self) -> None:
        self.last_error = diagnose(*self._target)
        log.warning("MQTT: %s:%s - %s", self._target[0], self._target[1], self.last_error)

    def stop(self) -> None:
        if self._client:
            with contextlib.suppress(RuntimeError, ValueError):
                self._client.publish(AVAILABILITY_TOPIC, "offline", retain=True).wait_for_publish(2)
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None

    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        if reason_code == 0 or getattr(reason_code, "is_failure", False) is False:
            log.info("MQTT connected")
            self.last_error = ""
            client.publish(AVAILABILITY_TOPIC, "online", retain=True)
            self._sent.clear()
            self._connected.set()
            events.changed()  # (re)publish everything after (re)connect
        else:
            log.warning("MQTT connect failed: %s", reason_code)
            self.last_error = "auth" if "authorized" in str(reason_code).lower() or "password" in str(reason_code).lower() else "other"

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None) -> None:
        self._connected.clear()
        log.warning("MQTT disconnected: %s", reason_code)

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    def _force(self, topic: str, payload: str) -> None:
        """Publish now, even when the same payload was sent before (and forget it, so the next round may send the topic again)."""
        if self._client:
            self._client.publish(topic, payload, retain=True)
        self._sent.pop(topic, None)

    def rebuild(self, vehicle_ids: list[int], wait: float = REBUILD_WAIT) -> bool:
        """Take the entities of these cars out of Home Assistant and put them back after a few seconds. Home Assistant gives an entity its ID (for
        example ``sensor.my_car_odometer``) ONCE, when it first creates it - from the name of the car and the sensor, in the language of that
        moment - and never changes it. Only an entity that was really removed gets a new ID, from the names as they are now. The history of the
        old entities is gone. False when no broker is connected."""
        if not self._client or not self.connected or not vehicle_ids:
            return False
        with self._lock:
            for vid in vehicle_ids:
                for sensor in SENSORS:
                    self._force(discovery_topic(vid, sensor), "")
                self._force(tracker_topic(vid), "")
            self._paused_until = time.monotonic() + wait
        timer = threading.Timer(wait, self._after_rebuild)
        timer.daemon = True
        timer.start()
        return True

    def _after_rebuild(self) -> None:
        self._paused_until = 0.0
        self._sent.clear()
        events.changed()  # everything is published again, with the names as they are now

    def resend(self) -> None:
        """Forget what was sent, so the next round publishes everything again (the *Send sensors again* button)."""
        self._sent.clear()

    def _send(self, topic: str, payload: str) -> None:
        """Retained publish, only when it differs from what the broker already holds (nothing is repeated every minute)."""
        if self._sent.get(topic) == payload or not self._client:
            return
        self._client.publish(topic, payload, retain=True)
        self._sent[topic] = payload

    def publish_vehicle(self, conn: sqlite3.Connection, vehicle: sqlite3.Row) -> None:
        if not self._client or not self.connected or time.monotonic() < self._paused_until:
            return
        values = compute_values(conn, vehicle)
        attrs = position_attributes(conn, vehicle)
        with self._lock:
            wanted = wanted_sensors(vehicle, values, modules.disabled(conn, vehicle["id"]))
            for sensor in SENSORS:
                topic = discovery_topic(vehicle["id"], sensor)
                if sensor not in wanted:
                    self._send(topic, "")  # remove a stale entity
                    continue
                self._send(topic, json.dumps(discovery_payload(vehicle, sensor), sort_keys=True))
                value = values.get(sensor.key)
                if sensor.attributes:
                    extra = sensor_attributes(conn, vehicle, sensor.key)
                    if extra is None and sensor.key == "last_notification":
                        continue  # nothing was announced yet: the entity exists and is still "unknown"
                    self._send(
                        sensor_attributes_topic(vehicle["id"], sensor.key),
                        json.dumps(_without_none(extra or {}), sort_keys=True, ensure_ascii=False),
                    )
                self._send(state_topic(vehicle["id"], sensor.key), "None" if value is None else value)
            if attrs and "position" not in config.ha_groups_off():
                self._send(tracker_topic(vehicle["id"]), json.dumps(tracker_payload(vehicle), sort_keys=True))
                self._send(attributes_topic(vehicle["id"]), json.dumps(attrs, sort_keys=True))
            else:
                self._send(tracker_topic(vehicle["id"]), "")

    def remove_vehicle(self, vehicle_id: int) -> None:
        if not self._client or not self.connected:
            return
        with self._lock:
            for sensor in SENSORS:
                self._send(discovery_topic(vehicle_id, sensor), "")
            self._send(tracker_topic(vehicle_id), "")

    def remove_all(self, conn: sqlite3.Connection) -> None:
        """Switching the sensors off takes every entity of every car out of Home Assistant again."""
        for vehicle in conn.execute("SELECT id FROM vehicles"):
            self.remove_vehicle(vehicle["id"])
        if self._client and self.connected:  # no broker reachable: nothing to take away, and saving the settings must not fail
            try:
                self._client.publish(AVAILABILITY_TOPIC, "offline", retain=True).wait_for_publish(2)
            except (RuntimeError, ValueError, OSError):
                log.warning("MQTT: could not tell the broker that the sensors went offline")

    def publish_all(self, conn: sqlite3.Connection) -> None:
        for vehicle in conn.execute("SELECT * FROM vehicles"):
            if vehicle["archived"]:
                self.remove_vehicle(vehicle["id"])
            else:
                self.publish_vehicle(conn, vehicle)


publisher = Publisher()
