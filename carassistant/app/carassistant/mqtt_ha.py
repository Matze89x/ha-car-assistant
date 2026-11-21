"""Publish one Home Assistant device per vehicle through MQTT discovery."""

from __future__ import annotations

import contextlib
import json
import logging
import sqlite3
import threading
from dataclasses import dataclass
from datetime import date

import paho.mqtt.client as mqtt

from . import __version__, config, connectors, events, fuelstats, modules, status, summary

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


def _s(key, name, **kw) -> SensorDef:
    return SensorDef(key, name, **kw)


def _b(key, name, device_class=None, **kw) -> SensorDef:
    return SensorDef(key, name, component="binary_sensor", device_class=device_class, **kw)


TYRES = (("fl", "front left"), ("fr", "front right"), ("rl", "rear left"), ("rr", "rear right"))

# One curated list. The first block exists for every car; the rest ("live") appears by itself as soon as a plugin or a bound
# Home Assistant entity delivers that value. Less useful values are created switched off (enabled=False) or as diagnostics.
SENSORS: tuple[SensorDef, ...] = (
    _s("odometer", "Odometer", unit="km", device_class="distance", state_class="total_increasing", icon="mdi:counter", precision=0),
    _s("inspection_days", "Days until inspection", unit="d", state_class="measurement", icon="mdi:calendar-clock"),
    _s("inspection_date", "Next inspection", device_class="date", icon="mdi:calendar-check"),
    _s("attention_count", "Items needing attention", state_class="measurement", icon="mdi:alert-circle-outline"),
    _b("attention", "Attention", "problem"),
    _s("avg_consumption", "Average consumption", state_class="measurement", icon="mdi:gas-station", precision=1),
    _s("fuel_spent_month", "Fuel cost this month", state_class="measurement", icon="mdi:cash", precision=2),
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
    _s("service_due_days", "Service in", unit="d", state_class="measurement", icon="mdi:wrench-clock", live=True),
    _s("service_due_km", "Service in", unit="km", device_class="distance", state_class="measurement", icon="mdi:wrench", live=True, precision=0),
    _s("warnings", "Warnings", state_class="measurement", icon="mdi:alert-outline", live=True),
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
    "Service in": "Service in", "Warnings": "Warnungen", "Position": "Position",
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
        "fuel_spent_month": fmt(fuelstats.month_spent(conn, vehicle["id"], ref.strftime("%Y-%m")), 2),
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
    values["speed_kmh"] = live.get("speed_kmh")
    values["warnings"] = str(len(status.parse_warnings(live["warnings"]))) if live.get("warnings") else None
    tyres = status.parse_numbers(live.get("tyre_pressure_bar"))
    for k, _label in TYRES:
        values[f"tyre_{k}"] = None if k not in tyres else f"{tyres[k]:.2f}"
    return values


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


def _device(vehicle: sqlite3.Row) -> dict:
    return {
        "identifiers": [f"carassistant_{vehicle['id']}"],
        "name": vehicle["name"],
        "manufacturer": vehicle["make"] or "Car Assistant",
        "model": " ".join(x for x in (vehicle["model"], vehicle["variant"]) if x) or None,
        "sw_version": __version__,
    }


def discovery_topic(vehicle_id: int, sensor: SensorDef) -> str:
    return f"{DISCOVERY_PREFIX}/{sensor.component}/carassistant_{vehicle_id}/{sensor.key}/config"


def tracker_topic(vehicle_id: int) -> str:
    return f"{DISCOVERY_PREFIX}/device_tracker/carassistant_{vehicle_id}/{TRACKER_KEY}/config"


def state_topic(vehicle_id: int, key: str) -> str:
    return f"{STATE_PREFIX}/{vehicle_id}/{key}/state"


def attributes_topic(vehicle_id: int) -> str:
    return f"{STATE_PREFIX}/{vehicle_id}/{TRACKER_KEY}/attributes"


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
    if sensor.key == "avg_consumption":
        unit = consumption_unit(vehicle["fuel_type"])
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
    return payload


def tracker_payload(vehicle: sqlite3.Row) -> dict:
    """The car on the Home Assistant map: a device tracker whose position is read from one JSON attributes topic."""
    return {
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


# sensors that belong to a function: when the function is switched off for the car, they are not created (or are taken away again)
BELONGS_TO = {
    "inspection_days": "appointments",
    "inspection_date": "appointments",
    "avg_consumption": "fuel",
    "fuel_spent_month": "fuel",
}


def wanted_sensors(
    vehicle: sqlite3.Row, values: dict[str, str | None] | None = None, off: frozenset[str] | set[str] = frozenset()
) -> tuple[SensorDef, ...]:
    """Fuel level / range exist when an entity is bound or a value arrived; every other live sensor only once it has a value."""
    out = []
    for s in SENSORS:
        if BELONGS_TO.get(s.key) in off:
            continue
        if s.key in ("attention", "attention_count") and {"appointments", "tasks"} <= set(off):
            continue
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


class Publisher:
    def __init__(self) -> None:
        self._client: mqtt.Client | None = None
        self._connected = threading.Event()
        self._lock = threading.Lock()
        self._sent: dict[str, str] = {}  # topic -> last payload sent (cleared on every (re)connect)

    def start(self) -> bool:
        settings = config.mqtt_settings()
        if not config.mqtt_discovery_enabled() or not settings:
            log.info("MQTT discovery disabled or no broker available")
            return False
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="carassistant")
        if settings["user"]:
            client.username_pw_set(settings["user"], settings["password"])
        client.will_set(AVAILABILITY_TOPIC, "offline", retain=True)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.reconnect_delay_set(min_delay=2, max_delay=60)
        client.connect_async(settings["host"], settings["port"], keepalive=60)
        client.loop_start()
        self._client = client
        return True

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
            client.publish(AVAILABILITY_TOPIC, "online", retain=True)
            self._sent.clear()
            self._connected.set()
            events.changed()  # (re)publish everything after (re)connect
        else:
            log.warning("MQTT connect failed: %s", reason_code)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None) -> None:
        self._connected.clear()
        log.warning("MQTT disconnected: %s", reason_code)

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

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
        if not self._client or not self.connected:
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
                self._send(state_topic(vehicle["id"], sensor.key), "None" if value is None else value)
            if attrs:
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
