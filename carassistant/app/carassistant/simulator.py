"""The scenario player: lets a plugin that comes from a SOURCE play a made-up drive, as if a real car were connected.

A package never runs code. A plugin may carry a ``simulation`` scenario in its plugin.json (places, drive cycle, rates, faults); this generic player
plays it - and sends every report through the SAME HTTP interface a real connector uses (``POST /api/v1/vehicles/<id>/data`` with the plugin's
bearer token), so the token check, the validation, the debug lines and the display are tested exactly like with a real car.

Rules (docs/plugins.md):
- Only a plugin installed from a source (``source_id`` set) is played; an uploaded package never is.
- It runs while the plugin is switched ON (*Start / Stop* on the plugin card). Switched off = the car is parked for good: nothing is sent.
- Every 5 seconds (``interval_s``) one report: parked, get in, start, drive (position moves, odometer and level change), stop, get out; sometimes a
  fault that goes away again; an electric car plugs in when its battery is low.
"""

from __future__ import annotations

import json
import logging
import random
import sqlite3
import threading
import urllib.request

from . import addons, config, connectors, db, events, summary, trips

log = logging.getLogger(__name__)

DEFAULT_CYCLE = (("parked", 3), ("enter", 1), ("start", 1), ("drive", 8), ("stop", 1), ("leave", 1))
PHASES = {p for p, _ in DEFAULT_CYCLE}
CLOSURES = {
    "doors": ["front_right", "rear_left", "rear_right", "trunk"],
    "windows": ["front_left", "front_right", "rear_left", "rear_right"],
}
_state: dict[int, dict] = {}


def _num(value, low: float, high: float, default: float) -> float:
    try:
        return min(high, max(low, float(value)))
    except (TypeError, ValueError):
        return default


def clean_scenario(raw) -> dict | None:
    """The cleaned ``simulation`` part of a plugin.json, or None. Everything is bounded; unknown keys are dropped."""
    if not isinstance(raw, dict):
        return None
    places = []
    for p in (raw.get("places") if isinstance(raw.get("places"), list) else [])[:12]:
        if isinstance(p, dict) and isinstance(p.get("name"), str):
            lat, lon = _num(p.get("lat"), -90, 90, 999), _num(p.get("lon"), -180, 180, 999)
            if lat != 999 and lon != 999:
                places.append({"name": p["name"][:40], "lat": lat, "lon": lon})
    if len(places) < 2:
        return None  # a drive needs a start and a destination
    cycle = [
        [c[0], int(_num(c[1], 1, 60, 1))]
        for c in (raw.get("cycle") if isinstance(raw.get("cycle"), list) else [])[:12]
        if isinstance(c, list | tuple) and len(c) == 2 and c[0] in PHASES
    ] or [list(c) for c in DEFAULT_CYCLE]
    fuel = raw.get("fuel") if isinstance(raw.get("fuel"), dict) else {}
    ev = raw.get("electric") if isinstance(raw.get("electric"), dict) else {}
    warnings = [
        {"code": w["code"][:40], "text": w["text"][:120]}
        for w in (raw.get("warnings") if isinstance(raw.get("warnings"), list) else [])[:12]
        if isinstance(w, dict) and isinstance(w.get("code"), str) and isinstance(w.get("text"), str)
    ]
    return {
        "interval_s": int(_num(raw.get("interval_s"), 1, 60, 5)),
        "timelapse": _num(raw.get("timelapse"), 1, 100, 12),  # a drive covers this many times the route length in odometer and level
        "places": places,
        "cycle": cycle,
        "fuel": {"pct_per_km": _num(fuel.get("pct_per_km"), 0.01, 2, 0.1), "km_per_pct": _num(fuel.get("km_per_pct"), 1, 50, 10)},
        "electric": {
            "pct_per_km": _num(ev.get("pct_per_km"), 0.01, 2, 0.27),
            "km_per_pct": _num(ev.get("km_per_pct"), 1, 20, 5.2),
            "charge_below_pct": _num(ev.get("charge_below_pct"), 5, 90, 40),
            "charge_step_pct": _num(ev.get("charge_step_pct"), 1, 30, 9),
            "charge_limit_pct": _num(ev.get("charge_limit_pct"), 50, 100, 80),
            "charge_kw": _num(ev.get("charge_kw"), 1, 350, 11),
        },
        "warnings": warnings,
    }


def _live(conn: sqlite3.Connection, vid: int, key: str) -> str | None:
    row = conn.execute("SELECT value FROM live WHERE vehicle_id = ? AND key = ?", (vid, key)).fetchone()
    return row["value"] if row else None


def step(conn: sqlite3.Connection, vid: int, scn: dict, rnd: random.Random | None = None) -> tuple[str, dict]:
    """Advance one car by one step; returns (phase, the report a connector would send). Reads the car's current values, writes nothing."""
    rnd = rnd or random.Random()  # noqa: S311 (made-up data, not a secret)
    st = _state.setdefault(vid, {"i": 0, "n": 0})
    cycle = scn["cycle"]
    st["i"] %= len(cycle)
    phase, length = cycle[st["i"]]
    n = st["n"]
    places = [(p["name"], p["lat"], p["lon"]) for p in scn["places"]]
    ev = (conn.execute("SELECT fuel_type FROM vehicles WHERE id = ?", (vid,)).fetchone() or {"fuel_type": ""})["fuel_type"] == "electric"
    rates = scn["electric"] if ev else scn["fuel"]
    per_km, per_pct = rates["pct_per_km"], rates["km_per_pct"]
    level = float(_live(conn, vid, "fuel_level") or 60)
    pos = (_live(conn, vid, "position") or f"{places[0][1]},{places[0][2]}").split(",")
    lat, lon = float(pos[0]), float(pos[1])
    km = summary.current_odometer(conn, vid) or 0
    data: dict = {}
    if phase == "parked" and ev and (st.get("charging") or (n == 0 and level < scn["electric"]["charge_below_pct"])):
        st["charging"] = True  # plugged, charging, power, minutes left, unplugged
        new = min(scn["electric"]["charge_limit_pct"], level + scn["electric"]["charge_step_pct"])
        done = n >= length - 1
        data.update(
            plugged=not done,
            charging=not done,
            charge_power_kw=0 if done else scn["electric"]["charge_kw"],
            charge_limit_pct=scn["electric"]["charge_limit_pct"],
            charge_minutes_left=0 if done else (length - 1 - n) * 20,
            fuel_level_pct=new,
            battery_pct=new,
            range_km=new * per_pct,
        )
        if done:
            st["charging"] = False
    elif phase == "parked":
        opened = st.setdefault("open", {})
        if opened:  # whatever was opened gets closed again
            kind, name = opened.popitem()[0]
            data[kind] = {name: False}
        elif n < 2:  # someone opens a door or a window
            kind = rnd.choice(["doors", "windows"])
            name = rnd.choice(CLOSURES[kind])
            opened[(kind, name)] = True
            data[kind] = {name: True}
    elif phase == "enter":
        data.update(locked=False, doors={"front_left": True})
    elif phase == "start":
        a = min(places, key=lambda p: trips.haversine_km(lat, lon, p[1], p[2]))
        b = rnd.choice([p for p in places if p[0] != a[0]])
        st["route"] = {"a": a, "b": b, "odo": float(km)}
        data.update(doors={"front_left": False}, ignition=True, battery_12v_v=13.9)
        data.update(lights={"low_beam": True}, climate_on=True, target_temp_c=21, cabin_temp_c=14)
        data["tyre_pressure_bar"] = {w: round(rnd.uniform(2.3, 2.6), 1) for w in ("fl", "fr", "rl", "rr")}
    elif phase == "drive":
        r = st.get("route")
        if r is None:  # the server restarted mid-drive: park and start again
            st["i"], st["n"] = 0, 0
            return "parked", {}
        f = (n + 1) / length
        la = r["a"][1] + (r["b"][1] - r["a"][1]) * f + 0.004 * f * (1 - f)
        lo = r["a"][2] + (r["b"][2] - r["a"][2]) * f
        moved = trips.haversine_km(lat, lon, la, lo) * scn["timelapse"]
        r["odo"] += moved
        level = max(1.0, level - moved * per_km)
        data.update(position={"lat": la, "lon": lo}, odometer_km=round(r["odo"]), fuel_level_pct=level, range_km=level * per_pct)
        if ev:
            data["battery_pct"] = level
        data.update(speed_kmh=round(rnd.uniform(35, 115)), outside_temp_c=round(8 + rnd.uniform(-0.6, 0.6), 1))
        data.update(
            coolant_temp_c=min(92, 55 + n * 6),
            oil_temp_c=min(98, 50 + n * 6),
            cabin_temp_c=min(21, 14 + n),
            consumption_l_100km=round(rnd.uniform(14.5, 19.5), 1) if ev else round(rnd.uniform(5.2, 6.8), 1),
        )
    elif phase == "stop":
        data.update(ignition=False, doors={"front_left": True}, speed_kmh=0, battery_12v_v=12.6, climate_on=False, parking_brake=True)
        data["lights"] = {"low_beam": False}
        st.pop("route", None)
        if level < 15 and not ev:  # "refuelled": the car simply reports a full tank again
            data["fuel_level_pct"], data["range_km"] = 90, 90 * per_pct
    elif phase == "leave":
        data.update(doors={"front_left": False}, locked=True, parking_brake=True)
    if phase == "drive" and n == 2 and not st.get("warn") and scn["warnings"]:  # the car reports a fault
        w = rnd.choice(scn["warnings"])
        st["warn"] = w["code"]
        data["warnings"] = {w["code"]: w["text"]}
    elif phase == "leave" and st.get("warn"):  # ... and it goes away again
        data["warnings"] = {st.pop("warn"): None}
    st["n"] += 1
    if st["n"] >= length:
        st["i"], st["n"] = (st["i"] + 1) % len(cycle), 0
    return phase, data


# ------------------------------------------------------------------ who is played, and how the reports are sent


def playing(conn: sqlite3.Connection) -> list[tuple[int, dict, dict]]:
    """(vehicle id, the plugin's row, its scenario) for every plugin that may be played: from a source, switched on, with a scenario."""
    out = []
    for r in conn.execute(
        "SELECT a.vehicle_id, a.id, a.manifest FROM vehicle_addons a JOIN vehicles v ON v.id = a.vehicle_id "
        "WHERE a.kind = 'plugin' AND a.active = 1 AND a.source_id IS NOT NULL AND a.status != 'missing' AND v.archived = 0"
    ):
        scn = clean_scenario(json.loads(r["manifest"]).get("simulation"))
        if scn:
            out.append((r["vehicle_id"], dict(r), scn))
    return out


def is_playable(addon: dict) -> bool:
    """Would this installed plugin be played when switched on? (shown on its card)"""
    return addon.get("source_id") is not None and clean_scenario(addon["m"].get("simulation")) is not None


def _token(conn: sqlite3.Connection, vid: int, addon_row: dict) -> str:
    """The plugin's own bearer token. The server keeps only its fingerprint, so the player remembers the one it created."""
    saved = db.get_setting(conn, f"sim.token.{vid}", "") or ""
    token_row = conn.execute(
        "SELECT token_hash FROM api_tokens WHERE id = (SELECT token_id FROM vehicle_addons WHERE id = ?)", (addon_row["id"],)
    ).fetchone()
    if saved and token_row and connectors._hash(saved) == token_row["token_hash"]:
        return saved
    addon = addons.get(conn, vid, addon_row["id"])
    raw = addons.new_token(conn, vid, addon)
    db.set_setting(conn, f"sim.token.{vid}", raw)
    conn.execute("UPDATE vehicle_addons SET status = 'configured' WHERE id = ?", (addon_row["id"],))
    return raw


def _post(vid: int, token: str, data: dict, path: str = "data") -> dict | None:
    """Send one report exactly like a real plugin: POST /api/v1/vehicles/<id>/data with the bearer token."""
    req = urllib.request.Request(
        f"http://127.0.0.1:{config.port()}/api/v1/vehicles/{vid}/{path}",
        data=json.dumps(data).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310 (fixed local http address)
            return json.loads(resp.read() or b"{}") if resp.status == 200 else None
    except Exception:
        return None


def _debug_lines(data: dict) -> list[dict]:
    lines = [{"level": "debug", "message": f"report sent: {', '.join(sorted(data))}"}]
    if "speed_kmh" in data:
        lines.append({"level": "info", "message": f"driving, {data['speed_kmh']} km/h"})
    if "warnings" in data:
        lines.append({"level": "warn", "message": f"vehicle message changed: {data['warnings']}"})
    if "tyre_pressure_bar" in data:
        lines.append({"level": "info", "message": "tyre pressures read from the sensors"})
    return lines


def loop() -> None:
    due: dict[int, float] = {}
    clock = 0.0
    while not events.stop.wait(1.0):
        clock += 1.0
        try:
            work: list[tuple[int, str, dict]] = []
            with db.tx() as conn:
                alive = set()
                for vid, row, scn in playing(conn):
                    alive.add(vid)
                    if clock < due.get(vid, 0.0):
                        continue
                    due[vid] = clock + scn["interval_s"]
                    _, data = step(conn, vid, scn)
                    if data:
                        work.append((vid, _token(conn, vid, row), data))
                for gone in set(_state) - alive:  # switched off: the car is parked, its drive is forgotten
                    _state.pop(gone, None)
                    due.pop(gone, None)
            for vid, token, data in work:  # after the commit: the server writes with its own connection
                answer = _post(vid, token, data)
                if answer is None:
                    log.warning("Scenario report for vehicle %s was not accepted", vid)
                elif (answer.get("control") or {}).get("debug"):
                    _post(vid, token, {"lines": _debug_lines(data)}, "logs")
        except Exception:  # keep the player running whatever one step does
            log.exception("Scenario step failed")


def start() -> threading.Thread:
    thread = threading.Thread(target=loop, name="scenario-player", daemon=True)
    thread.start()
    return thread
