"""Vehicle state shown on Home: ignition, doors and windows (hero badges) and the position card.

Integrations and plugins push these values through the Plugin API (``docs/api.md``); they land in the ``live``
table. Nothing is shown until data exists. Live keys read here:

- ``ignition``  – ``"on"`` or ``"off"``
- ``doors`` / ``windows`` – JSON object ``{"front_left": true, ...}``, ``true`` = open
- ``position``  – ``"lat,lon"``
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import quote

from . import db, regional, units

Translator = Callable[..., str]
Live = dict[str, tuple[str | None, datetime | None]]

MAP_SETTING = "map.tiles"  # "1" = load the map tiles from OpenStreetMap; anything else (the default) = nothing is loaded


def _parse(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        stamp = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)


def rows(conn: sqlite3.Connection, vehicle_id: int) -> Live:
    """The live values of a vehicle with the time each one arrived."""
    return {
        r["key"]: (r["value"], _parse(r["updated"]))
        for r in conn.execute("SELECT key, value, updated FROM live WHERE vehicle_id = ?", (vehicle_id,))
    }


def map_tiles_enabled(conn: sqlite3.Connection) -> bool:
    return db.get_setting(conn, MAP_SETTING, "0") == "1"


def ignition(live: Live) -> bool | None:
    value = live.get("ignition", (None, None))[0]
    return True if value == "on" else False if value == "off" else None


def parse_flags(raw: str | None) -> dict[str, bool]:
    try:
        data = json.loads(raw or "")
    except ValueError:
        return {}
    return {str(k): v for k, v in data.items() if isinstance(v, bool)} if isinstance(data, dict) else {}


def parse_warnings(raw: str | None) -> dict[str, str]:
    try:
        data = json.loads(raw or "")
    except ValueError:
        return {}
    return {str(k): v for k, v in data.items() if isinstance(v, str) and v} if isinstance(data, dict) else {}


def parse_numbers(raw: str | None) -> dict[str, float]:
    try:
        data = json.loads(raw or "")
    except ValueError:
        return {}
    return (
        {str(k): float(v) for k, v in data.items() if isinstance(v, int | float) and not isinstance(v, bool)}
        if isinstance(data, dict)
        else {}
    )


def warnings(live: Live) -> list[tuple[str, str]]:
    """The messages the car reported, as (code, text), sorted by code."""
    return sorted(parse_warnings(live.get("warnings", (None, None))[0]).items())


def closures(live: Live) -> dict[str, dict[str, bool]] | None:
    """Doors and windows as ``{"doors": {name: open}, "windows": {name: open}}`` or None while nothing is known."""
    doors = parse_flags(live.get("doors", (None, None))[0])
    windows = parse_flags(live.get("windows", (None, None))[0])
    return {"doors": doors, "windows": windows} if doors or windows else None


def closure_label(group: str, name: str, t: Translator) -> str:
    """'Front left door'; an unknown name is shown as written, only prettified."""
    key = f"{'door' if group == 'doors' else 'window'}.{name}"
    text = t(key)
    return name.replace("_", " ").capitalize() if text == key else text


def _badge(title: str, value: str, tone: str, icon: str) -> dict:
    return {"title": title, "value": value, "tone": tone, "icon": icon}


def _num(live: Live, key: str) -> float | None:
    try:
        return float(live[key][0])
    except (KeyError, TypeError, ValueError):
        return None


def tank(live: Live, capacity: float | None = None, mode: str = "fuel") -> dict | None:
    """How full the tank (or battery) is: ``pct`` and ``amount`` (litres / kWh left), from whatever the plugin delivered - the level in per cent
    (``fuel_level_pct``, for a charging vehicle also ``battery_pct``), the amount itself (``fuel_amount``), or one of them with the size of the tank.
    None when nothing is known."""
    pct = _num(live, "fuel_level")
    if pct is None and mode == "charge":
        pct = _num(live, "battery_pct")
    amount = _num(live, "fuel_amount")
    if pct is None and amount is not None and capacity:
        pct = amount / capacity * 100
    if pct is not None:
        pct = max(0, min(100, round(pct)))
    if amount is None and capacity and pct is not None:
        amount = capacity * pct / 100
    if pct is None and amount is None:
        return None
    return {"pct": pct, "amount": round(amount, 1) if amount is not None else None}


def hero_range(live: Live, t: Translator, capacity: float | None = None, unit: str = "L", mode: str = "fuel") -> dict | None:
    """The big figure under the car: the range the car reports, the tank level, the amount left (litres or kWh) and when the value arrived -
    None when the car sends no range, then the page shows the odometer instead."""
    km = _num(live, "range_km")
    if km is None:
        return None
    info = tank(live, capacity, mode) or {"pct": None, "amount": None}
    return {"km": round(km), "pct": info["pct"], "liters": info["amount"], "unit": unit, "when": live["range_km"][1]}


def freshness(live: Live, t: Translator) -> str:
    """When the car last reported anything ("5 min ago"); empty when nothing came in yet."""
    stamps = [stamp for _, stamp in live.values() if stamp]
    return ago(max(stamps), t) if stamps else ""


def last_signal(live: Live):
    """The moment the car last reported anything (a datetime) or None."""
    stamps = [stamp for _, stamp in live.values() if stamp]
    return max(stamps) if stamps else None


def hero_badges(live: Live, t: Translator) -> dict[str, list[dict]]:
    """Two plaques at the car picture: ignition on the left, doors & windows on the right. Only with real data."""
    left: list[dict] = []
    right: list[dict] = []
    ign = ignition(live)
    if ign is not None:
        left.append(_badge(t("hb.ignition"), t("hb.on") if ign else t("hb.off"), "ok" if ign else "off", "power"))
    known = closures(live)
    if known:
        doors, windows = known["doors"], known["windows"]
        title = t("hb.doors_windows") if doors and windows else t("hb.doors") if doors else t("hb.windows")
        opened = [(group, name) for group in ("doors", "windows") for name, is_open in known[group].items() if is_open]
        if len(opened) == 1:
            right.append(_badge(title, t("hb.one_open", name=closure_label(*opened[0], t)), "warn", "car-door"))
        elif opened:
            right.append(_badge(title, t("hb.n_open", n=len(opened)), "warn", "car-door"))
        else:
            right.append(_badge(title, t("hb.closed"), "ok", "car-door"))
    return {"left": left, "right": right}


def ago(stamp: datetime | None, t: Translator, now: datetime | None = None) -> str:
    if stamp is None:
        return ""
    seconds = max(0, int(((now or datetime.now(UTC)) - stamp).total_seconds()))
    if seconds < 60:
        return t("ago.now")
    if seconds < 3600:
        return t("ago.min", n=seconds // 60)
    if seconds < 86400:
        return t("ago.hours", n=seconds // 3600)
    return t("ago.days", n=seconds // 86400)


def _coords(raw: str | None) -> tuple[float, float] | None:
    try:
        lat_text, lon_text = (raw or "").split(",")
        lat, lon = float(lat_text), float(lon_text)
    except ValueError:
        return None
    return (lat, lon) if -90 <= lat <= 90 and -180 <= lon <= 180 else None


def location(live: Live, t: Translator, now: datetime | None = None) -> dict | None:
    """The position card: title, chips (parked since, last signal) and navigation links. None without a position."""
    raw, updated = live.get("position", (None, None))
    point = _coords(raw)
    if point is None:
        return None
    lat, lon = point
    parked = ignition(live) is False
    chips: list[dict] = []
    if parked:
        since = live["ignition"][1]
        chips.append({"text": t("loc.parked_since", time=regional.ftime(since.astimezone())) if since else t("loc.parked"), "tone": "ok"})
    if updated:
        chips.append({"text": t("loc.last_signal", ago=ago(updated, t, now)), "tone": ""})
    target = f"{lat:.6f},{lon:.6f}"
    return {
        "lat": f"{lat:.6f}",
        "lon": f"{lon:.6f}",
        "coords": f"{lat:.5f}, {lon:.5f}",
        "title": t("loc.here") if parked else t("loc.last_known"),
        "chips": chips,
        "links": [
            {"key": "waze", "name": "Waze", "url": f"https://waze.com/ul?ll={quote(target, safe=',')}&navigate=yes"},
            {
                "key": "google",
                "name": "Google Maps",
                "url": f"https://www.google.com/maps/dir/?api=1&destination={quote(target, safe=',')}",
            },
            {"key": "apple", "name": "Apple Maps", "url": f"https://maps.apple.com/?daddr={quote(target, safe=',')}"},
        ],
    }


DOOR_ORDER = ("front_left", "front_right", "rear_left", "rear_right", "trunk", "hood")
WINDOW_ORDER = ("front_left", "front_right", "rear_left", "rear_right", "sunroof")


def lock(live: Live) -> bool | None:
    """True = locked, False = unlocked, None = unknown."""
    value = live.get("locked", (None, None))[0]
    return True if value == "locked" else False if value == "unlocked" else None


def open_closures(live: Live) -> list[tuple[str, str]]:
    """Every door and window that is open, as (group, name)."""
    known = closures(live) or {"doors": {}, "windows": {}}
    return [(group, name) for group in ("doors", "windows") for name, is_open in known[group].items() if is_open]


def _ordered(items: dict[str, bool], order: tuple[str, ...]) -> list[tuple[str, bool]]:
    return [(n, items[n]) for n in order if n in items] + sorted((n, o) for n, o in items.items() if n not in order)


def security_view(live: Live, t: Translator, now: datetime | None = None) -> dict | None:
    """Everything the Security page shows about doors, windows and the lock. None while the car reported none of it."""
    known = closures(live)
    locked = lock(live)
    if known is None and locked is None:
        return None
    view: dict = {"lock": None, "headline": None, "tone": "off", "subline": "", "doors": [], "windows": []}
    if locked is not None:
        stamp = live["locked"][1]
        view["lock"] = {
            "text": t("sec.locked") if locked else t("sec.unlocked"),
            "tone": "ok" if locked else "warn",
            "ago": t("sec.updated", ago=ago(stamp, t, now)) if stamp else "",
        }
    if known is not None:
        doors, windows = known["doors"], known["windows"]
        opened = open_closures(live)
        if not opened:
            view["headline"], view["tone"] = t("sec.all_closed"), "ok"
        elif len(opened) == 1:
            view["headline"], view["tone"] = t("hb.one_open", name=closure_label(*opened[0], t)), "warn"
        else:
            view["headline"], view["tone"] = t("hb.n_open", n=len(opened)), "warn"
        title = t("hb.doors_windows") if doors and windows else t("hb.doors") if doors else t("hb.windows")
        stamps = [live[k][1] for k in ("doors", "windows") if k in live and live[k][1]]
        view["subline"] = f"{title} · {t('sec.updated', ago=ago(max(stamps), t, now))}" if stamps else title
        view["doors"] = [{"label": closure_label("doors", n, t), "open": o} for n, o in _ordered(doors, DOOR_ORDER)]
        view["windows"] = [{"label": closure_label("windows", n, t), "open": o} for n, o in _ordered(windows, WINDOW_ORDER)]
    return view


LIGHT_NAMES = ("low_beam", "high_beam", "hazard", "parking")


def car_data(live: Live, t: Translator, base: str = "L") -> list[dict]:
    """The extra values a plugin may send (temperatures, speed, battery, charging, tyre pressures) as small label/value pairs."""

    def num(key: str) -> float | None:
        try:
            return float(live[key][0]) if key in live and live[key][0] not in (None, "") else None
        except ValueError:
            return None

    shown = units.of()  # speed, temperatures, consumption and pressure in the units of Settings -> Region
    deg = shown.temp_unit

    def temp(value: float) -> str:
        return f"{round(shown.t(value), 1):g} {deg}"

    out: list[dict] = []
    if (v := num("speed_kmh")) is not None and v > 0:
        out.append({"icon": "speedometer", "label": t("cd.speed"), "value": f"{round(shown.d(v)):g} {shown.speed_unit}"})
    if (v := num("outside_temp_c")) is not None:
        out.append({"icon": "weather-cloudy", "label": t("cd.outside"), "value": temp(v)})
    if (v := num("coolant_temp_c")) is not None:
        out.append({"icon": "engine-outline", "label": t("cd.coolant"), "value": temp(v)})
    if (v := num("oil_temp_c")) is not None:
        out.append({"icon": "oil", "label": t("cd.oil"), "value": temp(v)})
    if (v := num("consumption")) is not None:
        out.append(
            {"icon": "gas-station", "label": t("cd.consumption"), "value": f"{round(shown.c(v, base), 1):g} {shown.consumption_unit(base)}"}
        )
    cabin, target, climate = num("cabin_temp_c"), num("target_temp_c"), live.get("climate_on", (None,))[0]
    if cabin is not None or climate in ("yes", "no"):
        text = temp(cabin) if cabin is not None else ""
        if climate == "yes":
            text = (text + " · " if text else "") + t("cd.climate_on") + (f" → {temp(target)}" if target is not None else "")
        out.append({"icon": "snowflake", "label": t("cd.cabin"), "value": text or t("cd.climate_off")})
    if (v := num("battery_12v_v")) is not None:
        out.append({"icon": "battery", "label": t("cd.battery12"), "value": f"{v:g} V"})
    if (v := num("battery_pct")) is not None:
        out.append({"icon": "lightning-bolt", "label": t("cd.battery_hv"), "value": f"{v:g} %"})
    charging, plugged = live.get("charging", (None,))[0], live.get("plugged", (None,))[0]
    if charging in ("yes", "no") or plugged in ("yes", "no"):
        power, limit, mins = num("charge_power_kw"), num("charge_limit_pct"), num("charge_minutes_left")
        if charging == "yes":
            text = t("cd.charging_on") + (f" · {power:g} kW" if power else "") + (f" · {mins:g} min" if mins else "")
        else:
            text = t("cd.plugged") if plugged == "yes" else t("cd.charging_off")
        if limit is not None:
            text += f" · {t('cd.limit')} {limit:g} %"
        out.append({"icon": "plug", "label": t("cd.charging"), "value": text})
    tyres = parse_numbers(live["tyre_pressure_bar"][0]) if "tyre_pressure_bar" in live else {}
    if tyres:
        order = ("fl", "fr", "rl", "rr")
        out.append(
            {
                "icon": "car-tire-alert",
                "label": t("cd.tyres"),
                "value": " · ".join(f"{round(units.of().p(tyres[w]), 1):g}" for w in order if w in tyres) + f" {units.of().press_unit}",
            }
        )
    lights = [name for name, on in parse_flags(live["lights"][0] if "lights" in live else None).items() if on]
    if lights:
        out.append(
            {
                "icon": "car-light-dimmed",
                "label": t("cd.lights"),
                "value": ", ".join(t("cd.light." + n) if n in LIGHT_NAMES else n for n in lights),
            }
        )
    if live.get("parking_brake", (None,))[0] == "yes":
        out.append({"icon": "car-brake-parking", "label": t("cd.parking_brake"), "value": t("cd.on")})
    if (v := num("speed_limit_kmh")) is not None and v > 0:
        out.append({"icon": "speedometer", "label": t("cd.speed_limit"), "value": f"{round(shown.d(v)):g} {shown.speed_unit}"})
    level, ad_range = num("adblue_level_pct"), num("adblue_range_km")
    if level is not None or ad_range is not None:
        text = " · ".join(
            b for b in (f"{level:g} %" if level is not None else "", units.of().dist_str(ad_range) if ad_range is not None else "") if b
        )
        out.append({"icon": "water-percent", "label": t("cd.adblue"), "value": text})
    oil_level, oil_warn = num("oil_level_pct"), live.get("oil_warning", (None,))[0]
    if oil_level is not None or oil_warn == "yes":
        text = f"{oil_level:g} %" if oil_level is not None else ""
        if oil_warn == "yes":
            text = (text + " · " if text else "") + t("cd.oil_warning")
        out.append({"icon": "oil-level", "label": t("cd.oil_level"), "value": text})
    days, km = num("service_due_days"), num("service_due_km")
    if days is not None or km is not None:
        bits = []
        if days is not None:
            bits.append(t("cd.in_days", n=int(days)) if days >= 0 else t("cd.overdue_days", n=int(-days)))
        if km is not None:
            bits.append(t("cd.in_km", n=units.of().dist_str(km)) if km >= 0 else t("cd.overdue_km", n=units.of().dist_str(-km)))
        out.append({"icon": "wrench", "label": t("cd.service"), "value": " · ".join(bits)})
    return out


def car_messages(live: Live, t: Translator) -> list[dict]:
    """What the car itself says needs attention: its messages (warnings) and a service that is due soon or overdue."""
    out = [{"code": code, "text": text, "severity": "overdue"} for code, text in warnings(live)]

    def num(key: str) -> float | None:
        try:
            return float(live[key][0]) if key in live and live[key][0] not in (None, "") else None
        except ValueError:
            return None

    days, km = num("service_due_days"), num("service_due_km")
    parts, severity = [], None
    if days is not None and days <= 30:
        parts.append(t("cd.in_days", n=int(days)) if days >= 0 else t("cd.overdue_days", n=int(-days)))
        severity = "overdue" if days < 0 else "soon"
    if km is not None and km <= 1000:
        parts.append(t("cd.in_km", n=units.of().dist_str(km)) if km >= 0 else t("cd.overdue_km", n=units.of().dist_str(-km)))
        severity = "overdue" if km < 0 or severity == "overdue" else "soon"
    if parts:
        out.append({"code": "service", "text": t("vm.service") + ": " + " · ".join(parts), "severity": severity})
    return out


def low_tyres(conn, vehicle_id: int, live: Live, margin: float = 0.3) -> set[str]:
    """Wheels (fl, fr, rl, rr) whose last reported pressure is more than ``margin`` bar under the recommended one of the season on the car."""
    actual = parse_numbers(live["tyre_pressure_bar"][0]) if "tyre_pressure_bar" in live else {}
    if not actual:
        return set()
    row = conn.execute("SELECT season FROM tires WHERE vehicle_id = ? AND mounted = 1", (vehicle_id,)).fetchone()
    goal = conn.execute(
        "SELECT front_bar, rear_bar FROM tire_pressure WHERE vehicle_id = ? AND season = ?",
        (vehicle_id, row["season"] if row else "summer"),
    ).fetchone()
    if goal is None:
        return set()
    wanted = {"fl": goal["front_bar"], "fr": goal["front_bar"], "rl": goal["rear_bar"], "rr": goal["rear_bar"]}
    return {w for w, bar in actual.items() if wanted.get(w) is not None and bar < wanted[w] - margin}
