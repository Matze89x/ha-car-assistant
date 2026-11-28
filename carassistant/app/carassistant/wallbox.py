"""The wallbox card of the Charging page and the tile of Home: what a charging point and a car that charges say, worked out into one model.

``model(conn, vehicle_id, live)`` reads what the Plugin API keeps (``charge_state``, ``charge_power_kw``, ``charge_session_kwh`` ... docs/api.md) and works out what
a card draws: the state, the ring (battery and target), the power against what the wallbox may give, the figures of the charge (energy, time, cost, the share
that did not reach the battery, the end) and the curve of the power. Nothing is invented: what cannot be worked out from what is known is ``None`` and the
template shows nothing in its place - no loss that is assumed, no sun share that nobody measured.

The model holds numbers, not words: the template says them in the language, the units and the currency of the person (``fnum``, ``units``, ``ftime``)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

from . import charge_detect, connectors
from . import habridge_slots as slots
from .status import Live

STALE_MINUTES = 20  # a charge whose power has not been reported for this long is no longer "live"
SERIES_POINTS = 90  # points of the curve that are drawn
VOLTS = 230  # what a wallbox at home gives when it does not say
WALLBOX_KEYS = (
    "charge_state",
    "charge_mode",
    "charge_fault",
    "charge_session_kwh",
    "charge_session_minutes",
    "charge_voltage_v",
    "charge_current_a",
    "charge_phases",
    "charge_current_limit_a",
    "charge_total_kwh",
    "charge_temp_c",
)
PULSE_KEYS = (
    "charge_power_kw",
    "charge_current_a",
    "charge_session_kwh",
    "charge_total_kwh",
    "battery_pct",
)  # what keeps coming while a charge runs


def _num(live: Live, key: str) -> float | None:
    raw = live.get(key, (None,))[0]
    try:
        return float(raw) if raw not in (None, "") else None
    except ValueError:
        return None


def _text(live: Live, key: str) -> str:
    return str(live.get(key, ("",))[0] or "")


def _stamp(live: Live, *keys: str) -> datetime | None:
    stamps = [live[k][1] for k in keys if k in live and live[k][1]]
    return max(stamps) if stamps else None


def state_of(live: Live) -> tuple[str | None, str]:
    """``(state, where it comes from)``: the word of the wallbox (``wallbox``), or - for a car that only says whether it charges and is plugged in - worked out
    from that (``car``). A fault the wallbox names wins. ``(None, "")`` when nothing says what is going on."""
    if _text(live, "charge_fault"):
        return "fault", "wallbox"
    word = _text(live, "charge_state")
    if word in connectors.CHARGE_STATES:
        return word, "wallbox"
    charging, plugged = live.get("charging", (None,))[0], live.get("plugged", (None,))[0]
    if charging == "yes":
        return "charging", "car"
    if plugged == "yes":
        return "plugged", "car"
    if plugged == "no":
        return "unplugged", "car"
    return None, ""


def wanted(live: Live) -> bool:
    """Is there something to draw a card for: the wallbox says something about itself, or the car charges right now."""
    if any(_text(live, k) for k in ("charge_state", "charge_mode", "charge_fault")):
        return True
    if any(_num(live, k) is not None for k in WALLBOX_KEYS if k not in ("charge_state", "charge_mode", "charge_fault")):
        return True
    return live.get("charging", (None,))[0] == "yes"


def _clock(moment: datetime) -> str:
    return moment.astimezone().strftime("%H:%M")


def curve(series: list[float], top: float, width: int = 300, height: int = 66) -> tuple[str, str]:
    """The power curve as two paths of an SVG (the area under it and its line); ``top`` is the power at the upper edge."""
    if len(series) < 2 or top <= 0:
        return "", ""
    n = len(series)
    points = [f"{i / (n - 1) * width:.1f} {height - 4 - min(max(v, 0), top) / top * (height - 12):.1f}" for i, v in enumerate(series)]
    line = "M" + " L".join(points)
    return f"{line} L{width} {height} L0 {height}Z", line


def _thin(values: list[float], size: int) -> list[float]:
    """At most ``size`` values, evenly picked, the last one always kept."""
    if len(values) <= size:
        return values
    step = (len(values) - 1) / (size - 1)
    return [values[round(i * step)] for i in range(size)]


def _series(conn: sqlite3.Connection, session_id: int | None) -> list[float]:
    if session_id is None:
        return []
    return _thin(
        [r["kw"] for r in conn.execute("SELECT kw FROM charge_samples WHERE session_id = ? ORDER BY at", (session_id,))], SERIES_POINTS
    )


def model(conn: sqlite3.Connection, vehicle_id: int, live: Live, now: datetime | None = None) -> dict | None:
    """What the wallbox card shows for a car; None when there is nothing to show (no wallbox data and the car is not charging)."""
    state, source = state_of(live)
    if state is None or not wanted(live):
        return None
    now = now or datetime.now(UTC)
    vehicle = conn.execute("SELECT battery_kwh FROM vehicles WHERE id = ?", (vehicle_id,)).fetchone()
    battery_kwh = vehicle["battery_kwh"] if vehicle and vehicle["battery_kwh"] else None
    session = charge_detect._open(conn, vehicle_id)
    last = None if session is not None else next(iter(charge_detect.sessions(conn, vehicle_id, 1)), None)

    soc, target = _num(live, "battery_pct"), _num(live, "charge_limit_pct")
    volts, amps = _num(live, "charge_voltage_v"), _num(live, "charge_current_a")
    phases = _num(live, "charge_phases")
    limit_a = _num(live, "charge_current_limit_a")
    kw = _num(live, "charge_power_kw")
    charging = state == "charging"
    if kw is None and charging and volts and amps:
        kw = volts * amps * max(1, round(phases or 1)) / 1000  # the wallbox says volts and amperes but no power
    if not charging:
        kw = 0.0  # nothing flows: a power that was reported last (and never reset) is not the power now
    if phases is None and kw and volts and amps:
        phases = min(3, max(1, round(kw * 1000 / (volts * amps))))  # worked out from what flows
    phases = int(phases) if phases else None
    max_kw = (
        limit_a * (volts or VOLTS) * phases / 1000 if limit_a and phases else None
    )  # what the wallbox may give with the limit that is set
    top = max_kw or (session["max_kw"] if session is not None and session["max_kw"] else None) or kw or None

    price = charge_detect.home_price(conn, vehicle_id)
    energy = _num(live, "charge_session_kwh")
    started = charge_detect._parse(session["started"]) if session is not None else None
    if energy is None and session is not None and session["energy_kwh"]:
        energy = session["energy_kwh"]
    minutes = _num(live, "charge_session_minutes")
    if minutes is None and started is not None:
        minutes = (now - started).total_seconds() / 60
    start_pct = session["start_pct"] if session is not None else None
    gained = (
        battery_kwh * (soc - start_pct) / 100 if battery_kwh and soc is not None and start_pct is not None and soc >= start_pct else None
    )
    loss = (
        (1 - gained / energy) * 100 if gained and energy and energy >= gained * 0.8 and gained < energy else None
    )  # (an estimate: only with the battery size)
    consumption = _num(live, "consumption")  # kWh per 100 km, from the car
    left = _num(live, "charge_minutes_left")
    if left is None and charging and kw and kw > 0.1 and battery_kwh and soc is not None and target is not None and target > soc:
        left = (target - soc) / 100 * battery_kwh / kw * 60  # what is missing to the target at the power that flows now
    left_min = round(left) if left else None
    need = (
        (target - soc) / 100 * battery_kwh if battery_kwh and soc is not None and target is not None and target > soc else None
    )  # kWh up to the target
    samples = _series(conn, session["id"] if session is not None else None)
    area, line = curve(samples, top or 0)
    pulse = _stamp(live, *PULSE_KEYS)
    stale = charging and pulse is not None and now - pulse > timedelta(minutes=STALE_MINUTES)
    return {
        "state": state,
        "source": source,  # wallbox | car
        "stale": bool(stale),
        "signal": _stamp(live, *WALLBOX_KEYS, "charging", "plugged", "charge_power_kw"),
        "soc": soc,
        "target": target,
        "kw": kw,
        "max_kw": max_kw,
        "load_pct": min(100.0, kw / top * 100) if kw and top else 0.0,
        "volts": volts,
        "amps": amps,
        "phases": phases,
        "limit_a": limit_a,
        "energy_kwh": energy,
        "minutes": round(minutes) if minutes is not None else None,
        "since": _clock(started) if started is not None else None,
        "price": price,
        "cost": round(energy * price, 2) if energy and price else None,
        "gained_kwh": gained,
        "in_battery": gained
        if gained and energy and gained <= energy
        else None,  # what reached the battery - only when it is less than what the wallbox gave
        "loss_pct": loss,
        "range_km": gained / consumption * 100 if gained and consumption else None,
        "need_kwh": need,
        "avg_kw": energy / minutes * 60 if energy and minutes else None,
        "left_min": left_min,
        "finish": _clock(now + timedelta(minutes=left_min)) if left_min else None,
        "mode": _text(live, "charge_mode"),
        "fault": _text(live, "charge_fault"),
        "temp_c": _num(live, "charge_temp_c"),
        "total_kwh": _num(live, "charge_total_kwh"),
        "curve_area": area,
        "curve_line": line,
        "curve_top": top,
        "peak_kw": max(samples) if samples else (session["max_kw"] if session is not None else None),
        "last": last,  # the last finished charge (a dict of charge_detect.sessions): what the card says while no car is plugged in
    }


def page(conn: sqlite3.Connection, vehicle_id: int, live: Live, t, states: dict[str, dict] | None = None) -> dict | None:
    """The model for a page: with the time since the last signal in words, the entities that feed it (``sources``) and - when ``states`` (what Home Assistant says
    now) are given - what the card may do (``controls``, wallbox_control.py); None when there is no card."""
    from . import wallbox_control
    from .status import ago

    found = model(conn, vehicle_id, live)
    if found is None:
        return None
    found["ago"] = ago(found["signal"], t) if found["signal"] else ""
    found["sources"] = sources(conn, vehicle_id, t)
    found["controls"] = wallbox_control.available(conn, vehicle_id, found["state"], states)
    return found


def sources(conn: sqlite3.Connection, vehicle_id: int, t) -> list[dict]:
    """The entities of Home Assistant that feed the card of this car: ``[{"label", "entity", "domain"}]``, in the order of the catalogue."""
    rows = conn.execute(
        "SELECT b.slot, b.entity FROM ha_bindings b JOIN vehicle_addons a ON a.id = b.addon_pk WHERE a.vehicle_id = ? AND a.active = 1",
        (vehicle_id,),
    ).fetchall()
    order = {s.key: n for n, s in enumerate(slots.SLOTS)}
    out = []
    for row in sorted(rows, key=lambda r: order.get(r["slot"], 999)):
        slot = slots.BY_KEY.get(row["slot"])
        if slot is None or slot.group not in ("battery", "wallbox"):
            continue
        out.append({"label": t(f"hab.slot.{slot.key}"), "entity": row["entity"], "domain": row["entity"].split(".")[0]})
    return out
