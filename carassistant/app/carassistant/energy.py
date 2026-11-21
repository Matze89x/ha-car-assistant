"""Energy view of a vehicle: "fuel" (tank, fill-ups) or "charge" (battery, charging), and when the level counts as low.

The page is for every kind of vehicle. Electric vehicles show charging wording by default, everything else fuel wording;
a vehicle can be switched to the other view (a plug-in hybrid, for example). Only the wording and the units change.
"""

from __future__ import annotations

MODES = ("fuel", "charge")
DEFAULT_WARN_PCT = 25
DEFAULT_CRIT_PCT = 10


def _get(vehicle, key):
    try:
        return vehicle[key]
    except (KeyError, IndexError):
        return None


def mode(vehicle) -> str:
    """ "fuel" or "charge" for a vehicle row (or anything that behaves like one)."""
    chosen = _get(vehicle, "energy_mode")
    if chosen in MODES:
        return chosen
    return "charge" if _get(vehicle, "fuel_type") == "electric" else "fuel"


def levels(vehicle) -> dict[str, int | None]:
    return {
        "warn_pct": _get(vehicle, "warn_pct") or DEFAULT_WARN_PCT,
        "crit_pct": _get(vehicle, "crit_pct") or DEFAULT_CRIT_PCT,
        "warn_km": _get(vehicle, "warn_range_km"),
        "crit_km": _get(vehicle, "crit_range_km"),
    }


def state(vehicle, pct: float | None, range_km: float | None) -> str:
    """ "ok", "soon" (yellow) or "overdue" (red) from the level in percent and the range, whichever is worse."""
    lv = levels(vehicle)
    worst = 0
    if pct is not None:
        worst = 2 if pct <= lv["crit_pct"] else 1 if pct <= lv["warn_pct"] else 0
    if range_km is not None:
        if lv["crit_km"] and range_km <= lv["crit_km"]:
            worst = 2
        elif lv["warn_km"] and range_km <= lv["warn_km"]:
            worst = max(worst, 1)
    return ("ok", "soon", "overdue")[worst]
