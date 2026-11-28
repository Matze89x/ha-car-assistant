"""Controlling a wallbox through Home Assistant (docs/home-assistant.md, "Controlling the wallbox"): pause and resume, start, acknowledge a fault, the current
limit and the mode - by a person pressing a button on the wallbox card, never by the app on its own.

The administrator chose the entities when binding the Home Assistant plugin: *Charging allowed* (a switch), *Start*, *Stop* and *Acknowledge the fault* (buttons or
scripts), and the entities of *Current limit that is set* and *Mode* when they can be set (number, input_number, select, input_select). A command goes only to one
of THOSE entities, of THIS car, with a service from the fixed table below and a value that was checked against what the entity says it takes. A request names
neither an entity nor a service: it says ``pause``, ``limit`` or ``mode`` and a number or a word. Every command leaves a line in the log of the plugin, and a car
takes only a few a minute."""

from __future__ import annotations

import sqlite3
import time

from . import connectors, ha

MAX_PER_MINUTE = 12  # commands to one car
ACTIONS = ("pause", "resume", "start", "stop", "ack", "limit", "mode")
SLOTS = {"allow": "wb_allow", "start": "wb_start", "stop": "wb_stop", "ack": "wb_ack"}  # the entities a command goes to, by what they do
SERVICE = {  # domain -> {what to do: service}: the only calls this module ever makes
    "switch": {"on": "turn_on", "off": "turn_off"},
    "input_boolean": {"on": "turn_on", "off": "turn_off"},
    "button": {"press": "press"},
    "input_button": {"press": "press"},
    "script": {"press": "turn_on"},
}
SETTABLE = {"number": "set_value", "input_number": "set_value", "select": "select_option", "input_select": "select_option"}
_recent: dict[int, list[float]] = {}


class ControlError(ValueError):
    """A command that was not sent; the message is an i18n key."""


def _bindings(conn: sqlite3.Connection, vehicle_id: int) -> dict[str, tuple[str, int, str]]:
    """``{slot: (entity, install, addon id)}`` of the active Home Assistant plugins of this car (the first install that binds a slot wins)."""
    rows = conn.execute(
        "SELECT b.slot, b.entity, a.id AS pk, a.addon_id FROM ha_bindings b JOIN vehicle_addons a ON a.id = b.addon_pk "
        "WHERE a.vehicle_id = ? AND a.active = 1 ORDER BY a.id",
        (vehicle_id,),
    ).fetchall()
    out: dict[str, tuple[str, int, str]] = {}
    for r in rows:
        out.setdefault(r["slot"], (r["entity"], r["pk"], r["addon_id"]))
    return out


def _on(state: dict | None) -> bool | None:
    word = str((state or {}).get("state") or "").lower()
    return True if word == "on" else False if word == "off" else None


def _number(value) -> float | None:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def available(conn: sqlite3.Connection, vehicle_id: int, state: str | None, states: dict[str, dict] | None) -> dict:
    """What the card may offer right now: ``{"main": {"action", "primary"}, "limit": {...}, "mode": {...}}`` - only what the entities of this car can do. Nothing
    when Home Assistant cannot be reached (``states`` is None): a button that cannot work is not shown."""
    if not states:
        return {}
    bound = _bindings(conn, vehicle_id)
    out: dict = {}
    allow = bound.get("wb_allow")
    allowed = _on(states.get(allow[0])) if allow else None
    can_stop = "wb_stop" in bound or (allow is not None and SERVICE.get(allow[0].split(".")[0]))
    if state == "fault" and "wb_ack" in bound:
        out["main"] = {"action": "ack", "primary": True}
    elif state == "charging" and can_stop:
        out["main"] = {"action": "pause", "primary": False}
    elif state in ("waiting", "plugged") and allowed is False:
        out["main"] = {"action": "resume", "primary": True}
    elif state in ("waiting", "plugged") and ("wb_start" in bound or (allow is not None and allowed is not True)):
        out["main"] = {"action": "start", "primary": True}
    limit = bound.get("charge_current_limit_a")
    if limit and limit[0].split(".")[0] in SETTABLE and limit[0] in states:
        entity = states[limit[0]]
        attrs = entity.get("attributes") or {}
        if limit[0].startswith(("select.", "input_select.")):
            options = [str(o) for o in (attrs.get("options") or []) if _number(o) is not None]
            if len(options) >= 2:
                out["limit"] = {"entity": limit[0], "value": _number(entity.get("state")), "options": [_number(o) for o in options]}
        else:
            low, high = _number(attrs.get("min")), _number(attrs.get("max"))
            if low is not None and high is not None and high > low:
                out["limit"] = {
                    "entity": limit[0],
                    "value": _number(entity.get("state")),
                    "min": low,
                    "max": high,
                    "step": _number(attrs.get("step")) or 1.0,
                }
    mode = bound.get("charge_mode")
    if mode and mode[0].split(".")[0] in ("select", "input_select") and mode[0] in states:
        entity = states[mode[0]]
        options = [str(o) for o in ((entity.get("attributes") or {}).get("options") or [])][:12]
        if len(options) >= 2:
            out["mode"] = {"entity": mode[0], "value": str(entity.get("state")), "options": options}
    return out


def _step(offer: dict, direction: int) -> float | None:
    """The next value of the limit up or down (``direction`` 1 or -1) among what the entity accepts; None when it is already at the end."""
    now = offer["value"]
    if "options" in offer:
        ordered = sorted(offer["options"])
        later = [o for o in ordered if (o > now if direction > 0 else o < now)] if now is not None else ordered
        return (later[0] if direction > 0 else later[-1]) if later else None
    step = offer["step"]
    target = (now if now is not None else offer["min"]) + direction * step
    target = min(offer["max"], max(offer["min"], target))
    return None if now is not None and target == now else target


def _simple(action: str, bound: dict, states: dict[str, dict]) -> tuple[tuple[str, str, str, dict], tuple[str, int, str]]:
    """The call for pause / stop / resume / start / acknowledge: the first entity of this car that can do it, with the service its kind of entity has."""
    order = {
        "pause": ("wb_stop", "wb_allow"),
        "stop": ("wb_stop", "wb_allow"),
        "resume": ("wb_allow", "wb_start"),
        "start": ("wb_start", "wb_allow"),
        "ack": ("wb_ack",),
    }[action]
    on = action in ("resume", "start")
    for key in order:
        entry = bound.get(key)
        if entry is None or entry[0] not in states:
            continue
        domain = entry[0].split(".")[0]
        services = SERVICE.get(domain)
        if not services or (action == "ack" and "press" not in services):  # an acknowledgement is a press, never a switch
            continue
        return (domain, services.get("press") or services["on" if on else "off"], entry[0], {}), entry
    raise ControlError("wb.cmd.err_none")


def wanted(conn: sqlite3.Connection, vehicle_id: int) -> bool:
    """Has this car an entity the card can send something to (so that Home Assistant is asked what they say)."""
    bound = _bindings(conn, vehicle_id)
    if any(key in bound for key in SLOTS.values()):
        return True
    return any(key in bound and bound[key][0].split(".")[0] in SETTABLE for key in ("charge_current_limit_a", "charge_mode"))


def do(conn: sqlite3.Connection, vehicle_id: int, action: str, form: dict, states: dict[str, dict] | None, now: float | None = None) -> str:
    """Send one command. Returns the i18n key of the message for the person (``wb.cmd.ok``, or ``wb.cmd.err_ha`` when Home Assistant did not take it); raises
    ``ControlError`` (its message is a key) when nothing was sent because the request did not fit what this car can do."""
    if action not in ACTIONS:
        raise ControlError("wb.cmd.err_what")
    if not states:
        raise ControlError("wb.cmd.err_ha")
    moment = time.monotonic() if now is None else now
    recent = [t for t in _recent.get(vehicle_id, []) if moment - t < 60]
    if len(recent) >= MAX_PER_MINUTE:
        raise ControlError("wb.cmd.err_often")
    bound = _bindings(conn, vehicle_id)
    if action in ("pause", "stop", "resume", "start", "ack"):
        sent, who = _simple(action, bound, states)
    elif action == "limit":
        offer = available(conn, vehicle_id, None, states).get("limit")
        if offer is None:
            raise ControlError("wb.cmd.err_none")
        entity = offer["entity"]
        who = bound["charge_current_limit_a"]
        asked = _number(form.get("value")) if form.get("value") not in (None, "") else None
        if asked is None:
            delta = _number(form.get("delta"))
            if delta not in (-1.0, 1.0):
                raise ControlError("wb.cmd.err_value")
            asked = _step(offer, int(delta))
            if asked is None:
                raise ControlError("wb.cmd.err_end")
        if "options" in offer:
            if asked not in offer["options"]:
                raise ControlError("wb.cmd.err_value")
            option = next(str(o) for o in ((states[entity].get("attributes") or {}).get("options") or []) if _number(o) == asked)
            sent = (entity.split(".")[0], "select_option", entity, {"option": option})
        else:
            if not offer["min"] <= asked <= offer["max"]:
                raise ControlError("wb.cmd.err_value")
            sent = (entity.split(".")[0], "set_value", entity, {"value": asked})
    else:  # mode
        offer = available(conn, vehicle_id, None, states).get("mode")
        if offer is None:
            raise ControlError("wb.cmd.err_none")
        option = str(form.get("option") or "")
        if option not in offer["options"]:
            raise ControlError("wb.cmd.err_value")
        who = bound["charge_mode"]
        sent = (offer["entity"].split(".")[0], "select_option", offer["entity"], {"option": option})
    domain, service, entity, extra = sent
    _recent[vehicle_id] = [*recent, moment]  # a command that fails counts, too: a broken Home Assistant is not asked over and over
    done, why = ha.call_service(domain, service, {"entity_id": entity, **extra})
    text = f"command {action}: {domain}.{service} {entity}" + (f" {extra}" if extra else "")
    if not done:
        connectors.app_log(conn, vehicle_id, who[2], "warn", "wallbox", f"{text} - Home Assistant did not take it: {why[:200]}")
        return "wb.cmd.err_ha"
    connectors.app_log(conn, vehicle_id, who[2], "info", "wallbox", text)
    return "wb.cmd.ok"
