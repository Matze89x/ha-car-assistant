"""Reminders of integrations: "do something again after N kilometres" or "after N refuels" - optional, off until the integration runs.

The rule comes from the integration's manifest (``reminders``), the numbers from its settings. The app counts: kilometres from the odometer,
refuels from the fuel entries. "Done" starts the count again. Nothing of a package is executed.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from . import summary

STATE_PAGE = "_state"


def _state_row(conn: sqlite3.Connection, vehicle_id: int, addon_id: str) -> tuple[int | None, dict]:
    r = conn.execute(
        "SELECT id, data FROM module_rows WHERE vehicle_id = ? AND addon_id = ? AND page = ?", (vehicle_id, addon_id, STATE_PAGE)
    ).fetchone()
    if not r:
        return None, {}
    try:
        return r["id"], json.loads(r["data"] or "{}")
    except ValueError:
        return r["id"], {}


def _save_state(conn: sqlite3.Connection, vehicle_id: int, addon_id: str, row_id: int | None, state: dict) -> int:
    if row_id is None:
        return conn.execute(
            "INSERT INTO module_rows(vehicle_id, addon_id, page, sort, data, created_at) VALUES(?,?,?,?,?,?)",
            (vehicle_id, addon_id, STATE_PAGE, 0, json.dumps(state), datetime.now(UTC).isoformat(timespec="seconds")),
        ).lastrowid
    conn.execute("UPDATE module_rows SET data = ? WHERE id = ?", (json.dumps(state), row_id))
    return row_id


def _baseline(conn: sqlite3.Connection, vehicle_id: int) -> dict:
    return {
        "km": summary.current_odometer(conn, vehicle_id) or 0,
        "fuel_id": conn.execute("SELECT COALESCE(MAX(id), 0) FROM fuel WHERE vehicle_id = ?", (vehicle_id,)).fetchone()[0],
    }


def _number(value, default: float) -> float:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default


def running(conn: sqlite3.Connection, vehicle_id: int) -> list[dict]:
    """Reminder rules of the running integrations of this vehicle, each with its settings (defaults filled in) and the translations."""
    from . import addons, config

    lang = config.language()
    out = []
    for a in addons.list_for(conn, vehicle_id):
        if a["kind"] != "integration" or not a["active"] or a["missing"]:
            continue
        for rule in a["m"].get("reminders", []):
            texts = (rule.get("l10n") or {}).get(lang) or {}
            out.append(
                {
                    **rule,
                    **{k: v for k, v in texts.items() if k in ("title", "text_due")},
                    "lang": lang,
                    "addon_id": a["addon_id"],
                    "vals": a["vals"],
                    "name": a["m"]["name"],
                }
            )
    return out


def status(conn: sqlite3.Connection, vehicle_id: int) -> list[dict]:
    """Where each reminder stands: ``{key, title, icon, due, mode, left, every, text_due}``; ``left`` is in kilometres or refuels (negative = past due)."""
    rules = running(conn, vehicle_id)
    if not rules:
        return []
    odometer = summary.current_odometer(conn, vehicle_id)
    out = []
    states: dict[str, tuple[int | None, dict]] = {}
    for rule in rules:
        addon_id = rule["addon_id"]
        if addon_id not in states:
            states[addon_id] = _state_row(conn, vehicle_id, addon_id)
        row_id, state = states[addon_id]
        mine = state.get(rule["id"])
        if not isinstance(mine, dict):  # first look: the count starts now
            mine = state[rule["id"]] = _baseline(conn, vehicle_id)
            states[addon_id] = (_save_state(conn, vehicle_id, addon_id, row_id, state), state)
        vals = rule["vals"]
        if rule.get("plan"):
            out.append(_plan_status(conn, vehicle_id, rule, states, odometer))
            continue
        mode = vals.get(rule["mode_setting"]) if rule["mode_setting"] else ("km" if rule["km_setting"] else "refuels")
        if mode not in ("km", "refuels"):
            mode = "km" if rule["km_setting"] else "refuels"
        if mode == "km" and rule["km_setting"]:
            every = max(1.0, _number(vals.get(rule["km_setting"]), 1000.0))
            left = every - (odometer - mine["km"]) if odometer is not None else None
        elif rule["refuels_setting"]:
            every = max(1.0, _number(vals.get(rule["refuels_setting"]), 2.0))
            n = conn.execute("SELECT COUNT(*) FROM fuel WHERE vehicle_id = ? AND id > ?", (vehicle_id, mine["fuel_id"])).fetchone()[0]
            left, mode = every - n, "refuels"
        else:
            continue
        out.append(
            {
                "key": f"{addon_id}-{rule['id']}",
                "addon_id": addon_id,
                "id": rule["id"],
                "title": rule["title"],
                "icon": rule["icon"],
                "text_due": rule["text_due"],
                "mode": mode,
                "every": every,
                "left": left,
                "due": left is not None and left <= 0,
            }
        )
    return out


def done(conn: sqlite3.Connection, vehicle_id: int, addon_id: str, rule_id: str) -> bool:
    """The reminder was acted on: the count starts again from today's odometer and the latest refuel."""
    if not any(r["addon_id"] == addon_id and r["id"] == rule_id for r in running(conn, vehicle_id)):
        return False
    if _rule(conn, vehicle_id, addon_id, rule_id) is not None:  # a plan: "done" says the latest dose was really added
        row_id, state = _state_row(conn, vehicle_id, addon_id)
        hist = (state.get(rule_id) or {}).get("hist") or []
        if hist and hist[0].get("dose"):
            hist[0]["filled"] = True
            _save_state(conn, vehicle_id, addon_id, row_id, state)
        return True
    row_id, state = _state_row(conn, vehicle_id, addon_id)
    state[rule_id] = _baseline(conn, vehicle_id)
    _save_state(conn, vehicle_id, addon_id, row_id, state)
    return True


# ------------------------------------------------------------------ plans: a rotation with one step per refuel

MAX_HIST = 40


def _step_text(rule: dict, i: int) -> tuple[str, str, bool]:
    """(label, amount, is_dose) of step ``i``: a fixed label, or the name (and amount) the person typed in the settings."""
    step = rule["plan"][i % len(rule["plan"])]
    texts = (step.get("l10n") or {}).get(rule.get("lang", "")) or {}
    vals = rule["vals"]
    if step["setting"]:
        name = str(vals.get(step["setting"], "") or "").strip()
        amount = str(vals.get(step["amount_setting"], "") or "").strip() if step["amount_setting"] else ""
        return (name or texts.get("label") or step["label"] or "–"), amount, True
    return texts.get("label") or step["label"], "", False


def _is_on(rule: dict) -> bool:
    key = rule.get("active_setting")
    if not key:
        return True
    return str(rule["vals"].get(key, "1")).lower() not in ("0", "false", "", "off", "no")


def _sync_plan(conn: sqlite3.Connection, vehicle_id: int, rule: dict, mine: dict) -> bool:
    """Every refuel since the last look takes one step of the plan: it lands in the history and the plan moves on. Returns True when changed."""
    changed = False
    mine.setdefault("step", 0)
    mine.setdefault("hist", [])
    for fuel in conn.execute("SELECT id, date FROM fuel WHERE vehicle_id = ? AND id > ? ORDER BY id", (vehicle_id, mine["fuel_id"])):
        label, amount, dose = _step_text(rule, mine["step"])
        mine["hist"].insert(0, {"date": fuel["date"], "label": label, "amount": amount, "dose": dose, "filled": None})
        mine["step"] = (mine["step"] + 1) % len(rule["plan"])
        mine["fuel_id"] = fuel["id"]
        changed = True
    del mine["hist"][MAX_HIST:]
    return changed


def _plan_status(conn: sqlite3.Connection, vehicle_id: int, rule: dict, states: dict, odometer) -> dict:
    addon_id = rule["addon_id"]
    row_id, state = states[addon_id]
    mine = state[rule["id"]]
    if _sync_plan(conn, vehicle_id, rule, mine):
        states[addon_id] = (_save_state(conn, vehicle_id, addon_id, row_id, state), state)
    label, amount, dose = _step_text(rule, mine["step"])
    due = dose and _is_on(rule)
    limit = _number(rule["vals"].get(rule["range_setting"]), 0.0) if rule.get("range_setting") else 0.0
    if due and limit:
        live = conn.execute("SELECT value FROM live WHERE vehicle_id = ? AND key = 'range_km'", (vehicle_id,)).fetchone()
        try:
            due = float(str(live["value"]).split()[0]) < limit if live else True  # without a range reading the reminder is not held back
        except (ValueError, IndexError):
            due = True
    return {
        "key": f"{addon_id}-{rule['id']}",
        "addon_id": addon_id,
        "id": rule["id"],
        "title": f"{label} ({amount})" if amount else label,
        "icon": rule["icon"],
        "text_due": rule["text_due"],
        "mode": "plan",
        "every": len(rule["plan"]),
        "left": None,
        "due": bool(due),
        "plan": {
            "steps": [
                {"label": _step_text(rule, i)[0], "amount": _step_text(rule, i)[1], "dose": _step_text(rule, i)[2]}
                for i in range(len(rule["plan"]))
            ],
            "current": mine["step"],
            "hist": mine["hist"],
            "on": _is_on(rule),
            "kind_title": rule["title"],
        },
    }


def _rule(conn: sqlite3.Connection, vehicle_id: int, addon_id: str, rule_id: str) -> dict | None:
    return next((r for r in running(conn, vehicle_id) if r["addon_id"] == addon_id and r["id"] == rule_id and r.get("plan")), None)


def plan_set(
    conn: sqlite3.Connection, vehicle_id: int, addon_id: str, rule_id: str, step: int | None = None, advance: bool = False
) -> bool:
    """Correct the plan by hand: choose the step that comes at the next refuel, or move one step on (a refuel the app did not see)."""
    rule = _rule(conn, vehicle_id, addon_id, rule_id)
    if rule is None:
        return False
    row_id, state = _state_row(conn, vehicle_id, addon_id)
    mine = state.get(rule_id) if isinstance(state.get(rule_id), dict) else _baseline(conn, vehicle_id)
    mine.setdefault("step", 0)
    mine.setdefault("hist", [])
    if advance:
        label, amount, dose = _step_text(rule, mine["step"])
        mine["hist"].insert(
            0, {"date": datetime.now(UTC).date().isoformat(), "label": label, "amount": amount, "dose": dose, "filled": None}
        )
        del mine["hist"][MAX_HIST:]
        mine["step"] = (mine["step"] + 1) % len(rule["plan"])
    elif step is not None and 0 <= step < len(rule["plan"]):
        mine["step"] = step
    state[rule_id] = mine
    _save_state(conn, vehicle_id, addon_id, row_id, state)
    return True


def plan_filled(conn: sqlite3.Connection, vehicle_id: int, addon_id: str, rule_id: str, index: int, filled: bool) -> bool:
    """Mark an entry of the history as 'added' or 'not added'."""
    if _rule(conn, vehicle_id, addon_id, rule_id) is None:
        return False
    row_id, state = _state_row(conn, vehicle_id, addon_id)
    mine = state.get(rule_id)
    if not isinstance(mine, dict) or not 0 <= index < len(mine.get("hist", [])):
        return False
    mine["hist"][index]["filled"] = bool(filled)
    _save_state(conn, vehicle_id, addon_id, row_id, state)
    return True
