"""Reminders for every person who asked for them: through a Home Assistant ``notify.*`` service (no port set) or as web push (a port is set).
Each item is announced at most every REPEAT_DAYS days. The low tank / battery message is different: it is told ONCE when the level falls to the
person's threshold - right when the new reading arrives - and again only after the level was back above it by a margin (see ``energy_decision``)."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import time
from datetime import UTC, datetime, timedelta

from . import config, energy, events, ha, i18n, push, status, summary, units

log = logging.getLogger(__name__)
REPEAT_DAYS = 3


def describe(item: summary.Attention, lang: str) -> str:
    t = i18n.translator(lang)
    parts = []
    if item.days_left is not None:
        parts.append(t("notify.overdue_days", n=-item.days_left) if item.days_left < 0 else t("notify.in_days", n=item.days_left))
    if item.km_left is not None:
        parts.append(
            t("notify.overdue_km", n=units.of().dist_str(-item.km_left))
            if item.km_left < 0
            else t("notify.in_km", n=units.of().dist_str(item.km_left))
        )
    return f"{item.title}: {', '.join(parts)}" if parts else item.title


def _recently_sent(conn: sqlite3.Connection, key: str, now: datetime) -> bool:
    row = conn.execute("SELECT last_sent FROM notify_state WHERE key = ?", (key,)).fetchone()
    if not row:
        return False
    try:
        return now - datetime.fromisoformat(row["last_sent"]) < timedelta(days=REPEAT_DAYS)
    except ValueError:
        return False


EVENTS = (
    "maint_due",
    "appointment",
    "reminder",
    "car_message",
    "open_closure",
    "low_energy",
    "tyre_pressure",
    "trip_end",
    "refuel",
)  # what a user can ask to be told about, for every car on its own
GENERAL = ("addon_update",)  # ... and what is not about one car


def _readable_place(place: str | None) -> str:
    """A place for a message: a name, never a raw pair of coordinates (a place the offline list could not name is left out)."""
    text = (place or "").strip()
    return "" if re.fullmatch(r"-?\d+(\.\d+)?\s*[,;]\s*-?\d+(\.\d+)?", text) else text


def push_mode() -> bool:
    """With a port set people sign in and get web push; without one the Home Assistant notify service is the way."""
    return (ha.network_port() or (None, None))[1] is not None


def clean_service(raw: str) -> str:
    """A Home Assistant notify service name: ``mobile_app_phone`` (a leading ``notify.`` is dropped)."""
    name = (raw or "").strip().removeprefix("notify.")
    return name if re.fullmatch(r"[a-z0-9_]{1,80}", name) else ""


def _events_of(raw: str | None) -> list[str]:
    try:
        return [e for e in json.loads(raw or "[]") if e in EVENTS]
    except ValueError:
        return []


def _general_of(raw: str | None) -> list[str]:
    try:
        return [e for e in json.loads(raw or "[]") if e in GENERAL]
    except ValueError:
        return []


def prefs(conn: sqlite3.Connection, user_id: int, vehicle_id: int | None = None) -> dict:
    """The person's service and the events wanted - for one car when given (its own row, else the choice for new cars)."""
    row = conn.execute("SELECT service, events FROM user_notify WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        return {"service": "", "events": [], "enabled": True}
    events = _events_of(row["events"])
    if vehicle_id is not None:
        own = conn.execute("SELECT events FROM user_notify_vehicle WHERE user_id = ? AND vehicle_id = ?", (user_id, vehicle_id)).fetchone()
        if own:
            events = _events_of(own["events"])
    return {"service": row["service"], "events": events, "enabled": True}


def offered_events(conn: sqlite3.Connection, vehicle) -> set[str]:
    """What THIS car can really tell: judged by what its plugins and entities delivered (the live values, the track) - a car that never reported tyre
    pressures is not offered the tyre message, one without door data not the open-door message. What the person enters themselves (maintenance,
    appointments) is always offered; reminders only while an integration with reminders runs. The choice for new cars offers everything."""
    from . import reminders

    vid = vehicle["id"]
    live = status.rows(conn, vid)

    def has(*keys: str) -> bool:
        return any(k in live for k in keys)

    out = {"maint_due", "appointment"}
    if has("warnings"):
        out.add("car_message")
    if has("doors", "windows"):
        out.add("open_closure")
    if has("fuel_level", "battery_pct", "fuel_amount", "range_km"):
        out.add("low_energy")
    if has("tyre_pressure_bar"):
        out.add("tyre_pressure")
    if has("fuel_level", "battery_pct", "charging"):
        out.add("refuel")  # a fill-up or a charge is noticed from the level
    if (
        has("position")
        or conn.execute("SELECT 1 FROM trips WHERE vehicle_id = ? AND source != 'manual' LIMIT 1", (vid,)).fetchone()
        or conn.execute("SELECT 1 FROM vehicle_track WHERE vehicle_id = ? LIMIT 1", (vid,)).fetchone()
    ):
        out.add("trip_end")
    if reminders.running(conn, vid):
        out.add("reminder")
    return out


def matrix(conn: sqlite3.Connection, user_id: int) -> dict:
    """What the person gets, for the settings page: the choice for ``default`` (new cars), every car of the installation with its events and its
    low tank / battery threshold, and the general events. Cars come and go by themselves: a new car starts with the choice for new cars, a removed
    one disappears. Distances are given in the units of the system."""
    row = conn.execute("SELECT events, general, energy_pct, energy_km FROM user_notify WHERE user_id = ?", (user_id,)).fetchone()
    default = set(_events_of(row["events"])) if row else set()

    def shown(km):
        return None if km is None else round(units.of().d(km))

    default_choice = _energy_choice(row["energy_pct"] if row else None, row["energy_km"] if row else None, shown)
    cars = []
    for v in conn.execute("SELECT * FROM vehicles WHERE archived = 0 ORDER BY name COLLATE NOCASE").fetchall():
        own = conn.execute(
            "SELECT events, energy_pct, energy_km FROM user_notify_vehicle WHERE user_id = ? AND vehicle_id = ?", (user_id, v["id"])
        ).fetchone()
        base = own if own else row
        lv = energy.levels(v)
        cars.append(
            {
                "id": v["id"],
                "name": v["name"],
                "events": set(_events_of(own["events"])) if own else set(default),
                "offered": offered_events(conn, v),
                **_energy_choice(base["energy_pct"] if base else None, base["energy_km"] if base else None, shown),
                "pct_ph": lv["warn_pct"],  # what an empty field means: the yellow level of the car
                "km_ph": shown(lv["warn_km"]) or "",
            }
        )
    return {
        "default": default,
        "cars": cars,
        "general": set(_general_of(row["general"])) if row else set(),
        "energy_mode": default_choice["mode"],
        "energy_pct": default_choice["energy_pct"],
        "energy_km": default_choice["energy_km"],
        "pct_ph": energy.DEFAULT_WARN_PCT,
    }


def _energy_choice(pct, km, shown) -> dict:
    """What the matrix shows for a threshold: ONE way to be told - ``mode`` ``pct`` (the level) or ``km`` (the range) - and its value. 0 stands for
    a way that is not used; a person who once had both (an earlier version) sees the level."""
    if not pct and km:
        return {"mode": "km", "energy_pct": None, "energy_km": shown(km)}
    return {"mode": "pct", "energy_pct": pct or None, "energy_km": None}


def _threshold(raw, high: int, base_from=None) -> int | None:
    """A threshold typed into the matrix: empty or not a number = follow the car's own yellow level (NULL); 0 = not used; the rest is held to ``high``."""
    raw = (raw or "").strip()
    if not raw.isdigit():
        return None
    number = int(raw)
    if base_from is not None:
        number = round(base_from(number))
    return min(number, high)


def _energy_form(form, key: str) -> tuple[int | None, int | None]:
    """The threshold of the form for one car (or ``new``): ``em_<key>`` says which way is used - ``pct`` (the level, ``ep_<key>``) or ``km`` (the range,
    ``ek_<key>``) - and the way that is not chosen is stored as 0 (not used). An empty level follows the yellow level of the car; a range chosen but
    left empty falls back to that, too."""
    pct = _threshold(form.get(f"ep_{key}"), 99)
    km = _threshold(form.get(f"ek_{key}"), 3000, units.of().from_d)
    if form.get(f"em_{key}") == "km" and km:
        return 0, km
    return pct, 0


def save_matrix(conn: sqlite3.Connection, user_id: int, form) -> None:
    """The whole matrix from one form: ``ev_new`` (the choice for new cars), ``ev_<car id>`` per car, ``gen`` (general events), and the low tank /
    battery threshold per car (``em_`` / ``ep_`` / ``ek_<car id>``, ``new`` for new cars; see ``_energy_form``) - only when the form carries them."""
    conn.execute("INSERT OR IGNORE INTO user_notify(user_id, service, events) VALUES(?, '', '[]')", (user_id,))
    default = [e for e in EVENTS if e in form.getlist("ev_new")]
    general = [e for e in GENERAL if e in form.getlist("gen")]
    conn.execute("UPDATE user_notify SET events = ?, general = ? WHERE user_id = ?", (json.dumps(default), json.dumps(general), user_id))
    if "em_new" in form or "ep_new" in form or "ek_new" in form:
        conn.execute("UPDATE user_notify SET energy_pct = ?, energy_km = ? WHERE user_id = ?", (*_energy_form(form, "new"), user_id))
    for v in conn.execute("SELECT id FROM vehicles WHERE archived = 0").fetchall():
        chosen = [e for e in EVENTS if e in form.getlist(f"ev_{v['id']}")]
        conn.execute(
            "INSERT INTO user_notify_vehicle(user_id, vehicle_id, events, enabled) VALUES(?,?,?,1) "
            "ON CONFLICT(user_id, vehicle_id) DO UPDATE SET events = excluded.events, enabled = 1",
            (user_id, v["id"], json.dumps(chosen)),
        )
        if any(f"{k}_{v['id']}" in form for k in ("em", "ep", "ek")):
            conn.execute(
                "UPDATE user_notify_vehicle SET energy_pct = ?, energy_km = ? WHERE user_id = ? AND vehicle_id = ?",
                (*_energy_form(form, str(v["id"])), user_id, v["id"]),
            )


def save_service(conn: sqlite3.Connection, user_id: int, service: str) -> None:
    """Only the way to be told (the Home Assistant notify service); the events chosen stay as they are."""
    conn.execute(
        "INSERT INTO user_notify(user_id, service, events) VALUES(?,?,'[]') ON CONFLICT(user_id) DO UPDATE SET service = excluded.service",
        (user_id, clean_service(service)),
    )


def send(conn: sqlite3.Connection, title: str, message: str, service: str, url: str = "") -> tuple[bool, str]:
    if not service:
        return False, "no notify service configured"
    payload: dict = {"title": title, "message": message}
    target = url or config.external_url()
    if target:
        payload["data"] = {"url": target, "clickAction": target}
    ok, error = ha.call_service("notify", service, payload)
    conn.execute("INSERT INTO notify_log(title, message, ok, error) VALUES(?,?,?,?)", (title, message, int(ok), error or None))
    conn.execute("DELETE FROM notify_log WHERE id NOT IN (SELECT id FROM notify_log ORDER BY id DESC LIMIT 100)")
    return ok, error


# where a message leads when it is about just one thing (below /v/<car>); everything else opens the car's overview
PAGE_OF = {
    "maint_due": "/e/tasks",
    "appointment": "/e/appointments",
    "tyre_pressure": "/e/tires",
    "trip_end": "/e/trips",
    "refuel": "/e/fuel",
    "car_message": "/security",
    "open_closure": "/security",
}


def link_path(vehicle, pages: set[str]) -> str:
    """The path a notification opens, below the app's own address: the page of that one topic (a refuel to complete leads right to its card, a trip
    to its page), or the car's overview when the message is about several. A web push uses this path as it is - it is always the app's own address,
    whatever address was saved - so a tap never lands on a page that is not there."""
    only = next(iter(pages)) if len(pages) == 1 else ""
    return f"/v/{vehicle['slug'] or vehicle['id']}{only}"


def link_for(vehicle, pages: set[str]) -> str:
    """The same as a full address with the saved external address in front (the Home Assistant app needs one); empty without a saved address."""
    base = (config.external_url() or "").rstrip("/")
    return f"{base}{link_path(vehicle, pages)}" if base else ""


def _lines_for(
    conn: sqlite3.Connection, vehicle, events: set[str], now: datetime, user_key: str, t
) -> tuple[list[str], list[str], set[str]]:
    """The lines one user gets for one vehicle (only what they asked for and was not told in the last days), the keys to remember
    and the pages the lines are about."""
    from . import reminders

    lines, keys, pages = [], [], set()
    lang = config.language()
    vid = vehicle["id"]
    for item in summary.attention_items(conn, vid):
        event = "appointment" if item.kind == "appointment" else "maint_due"
        key = f"{user_key}:{item.kind}:{vid}:{item.item_id}:{item.severity}"
        if event in events and not _recently_sent(conn, key, now):
            keys.append(key)
            lines.append(describe(item, lang))
            pages.add(PAGE_OF[event])
    if "reminder" in events:
        for r in reminders.status(conn, vid):
            key = f"{user_key}:rem:{vid}:{r['key']}"
            if r["due"] and not _recently_sent(conn, key, now):
                keys.append(key)
                lines.append(f"{r['title']}: {r['text_due'] or t('rem.due')}")
                pages.add("")
    live = status.rows(conn, vid)
    if "car_message" in events:
        for m in status.car_messages(live, t):
            key = f"{user_key}:car:{vid}:{m['code'] if 'code' in m else m['text']}"
            if not _recently_sent(conn, key, now):
                keys.append(key)
                lines.append(m["text"])
                pages.add(PAGE_OF["car_message"])
    if "open_closure" in events:
        opened = status.open_closures(live)
        key = f"{user_key}:open:{vid}"
        if opened and not _recently_sent(conn, key, now):
            keys.append(key)
            lines.append(t("notify.closures_open", n=len(opened)))
            pages.add(PAGE_OF["open_closure"])
    if "tyre_pressure" in events:
        low = status.low_tyres(conn, vid, live)
        key = f"{user_key}:tyres:{vid}:{','.join(sorted(low))}"
        if low and not _recently_sent(conn, key, now):
            keys.append(key)
            lines.append(t("notify.tyres_low", n=len(low), names=", ".join(t("tp." + w) for w in sorted(low))))
            pages.add(PAGE_OF["tyre_pressure"])
    if "trip_end" in events:
        trip_ids: list[int] = []
        since = (now - timedelta(days=1)).date().isoformat()
        for trip in conn.execute(
            "SELECT id, distance_km, end_place FROM trips WHERE vehicle_id = ? AND date >= ? AND source != 'manual' ORDER BY id DESC LIMIT 3",
            (vid, since),
        ):
            key = f"{user_key}:trip:{vid}:{trip['id']}"
            if not _recently_sent(conn, key, now):
                keys.append(key)
                trip_ids.append(trip["id"])
                distance = trip["distance_km"]
                lines.append(
                    t("notify.trip_end", d=units.of().dist_str(distance) if distance else "-", place=_readable_place(trip["end_place"]))
                )
        if trip_ids:  # one trip: its own page; several: the list
            pages.add(f"/trips/{trip_ids[0]}" if len(trip_ids) == 1 else PAGE_OF["trip_end"])
    if "refuel" in events:
        from . import refuel_detect

        fresh: list[int] = []
        for item in refuel_detect.todo(conn, vid):
            key = f"{user_key}:refuel:{vid}:{item['id']}"
            if not _recently_sent(conn, key, now):
                keys.append(key)
                fresh.append(item["id"])
                lines.append(
                    t(
                        "notify.charge" if item["charge"] else ("notify.refuel" if item["rise"] else "notify.refuel_plain"),
                        pct=item["rise"] or "",
                        litres=f" (~{item['litres']} {item['unit']})" if item["litres"] else "",
                    )
                )
        if fresh:  # one refuel to complete: the tap opens its card (with the scan buttons); several: the list
            pages.add(f"{PAGE_OF['refuel']}?edit={fresh[0]}#fuel-{fresh[0]}" if len(fresh) == 1 else PAGE_OF["refuel"])
    return lines, keys, pages


# ---- low tank / battery: told once, right with the reading, again only after the level was back above the threshold by a margin
ENERGY_MARGIN_PCT = (
    5  # percentage points above the threshold the level must reach before the next fall is told again (no hopping up and down)
)
ENERGY_MARGIN_RANGE = 0.2  # ... and a fifth of the threshold for a range (at least ENERGY_MARGIN_RANGE_MIN km)
ENERGY_MARGIN_RANGE_MIN = 10
_energy_pending: set[int] = set()
_energy_lock = threading.Lock()


def energy_margin(thr_pct: int | None, thr_km: int | None) -> tuple[int, int]:
    """How far above the threshold the level must be again: (percentage points, km)."""
    return ENERGY_MARGIN_PCT, max(ENERGY_MARGIN_RANGE_MIN, round((thr_km or 0) * ENERGY_MARGIN_RANGE))


def energy_decision(pct, km, thr_pct: int | None, thr_km: int | None, fired: bool) -> str:
    """What a new reading means for one person: ``"fire"`` (the level fell to the threshold and nobody was told yet), ``"rearm"`` (it is back above the
    threshold by the margin: the next fall is told again) or ``""`` (nothing). Either threshold may be missing (not used); a reading that is
    missing is ignored. A level between the threshold and the margin keeps whatever was told: it neither tells nor forgets."""
    low = bool((thr_pct and pct is not None and pct <= thr_pct) or (thr_km and km is not None and km <= thr_km))
    if not fired:
        return "fire" if low else ""
    margin_pct, margin_km = energy_margin(thr_pct, thr_km)
    used = bool((thr_pct and pct is not None) or (thr_km and km is not None))
    high_pct = not (thr_pct and pct is not None) or pct >= thr_pct + margin_pct
    high_km = not (thr_km and km is not None) or km >= thr_km + margin_km
    return "rearm" if used and high_pct and high_km else ""


def energy_thresholds(conn: sqlite3.Connection, user_id: int, vehicle) -> tuple[int | None, int | None]:
    """The threshold of one person for one car: (per cent, range in km). Their own value, else the car's yellow level; 0 = not used."""
    row = conn.execute(
        "SELECT energy_pct, energy_km FROM user_notify_vehicle WHERE user_id = ? AND vehicle_id = ?", (user_id, vehicle["id"])
    ).fetchone()
    if row is None:  # a car that came later: the choice for new cars
        row = conn.execute("SELECT energy_pct, energy_km FROM user_notify WHERE user_id = ?", (user_id,)).fetchone()
    lv = energy.levels(vehicle)
    pct = row["energy_pct"] if row and row["energy_pct"] is not None else lv["warn_pct"]
    km = row["energy_km"] if row and row["energy_km"] is not None else lv["warn_km"]
    return (pct or None, km or None)


def _energy_reading(conn: sqlite3.Connection, vehicle) -> tuple[int | None, float | None] | None:
    """The level the car reported last: (per cent, range in km); None when it reported neither."""
    live = status.rows(conn, vehicle["id"])
    capacity = vehicle["battery_kwh"] if vehicle["fuel_type"] == "electric" else vehicle["tank_l"]
    info = status.tank(live, capacity, energy.mode(vehicle))
    km = status._num(live, "range_km")
    pct = info["pct"] if info else None
    return None if pct is None and km is None else (pct, km)


def _energy_fired(conn: sqlite3.Connection, user_id: int, vehicle_id: int) -> bool:
    """Was this person told about the current fall? Without a record of the new kind, the old way counts: a message of the last days means yes."""
    row = conn.execute("SELECT fired FROM notify_energy WHERE user_id = ? AND vehicle_id = ?", (user_id, vehicle_id)).fetchone()
    if row is not None:
        return bool(row["fired"])
    who = "ha" if user_id == 0 else f"u{user_id}"
    return conn.execute("SELECT 1 FROM notify_state WHERE key LIKE ? LIMIT 1", (f"{who}:energy:{vehicle_id}:%",)).fetchone() is not None


def _set_energy_fired(conn: sqlite3.Connection, user_id: int, vehicle_id: int, fired: bool, now: datetime) -> None:
    conn.execute(
        "INSERT INTO notify_energy(user_id, vehicle_id, fired, at) VALUES(?,?,?,?) "
        "ON CONFLICT(user_id, vehicle_id) DO UPDATE SET fired = excluded.fired, at = excluded.at",
        (user_id, vehicle_id, int(fired), now.isoformat()),
    )


def _energy_text(vehicle, pct, km, t) -> str:
    parts = [f"{pct} %"] if pct is not None else []
    if km is not None:
        parts.append(units.of().dist_str(km))
    return f"{t('notify.energy_charge') if energy.mode(vehicle) == 'charge' else t('notify.energy_fuel')}: {' · '.join(parts)}"


def energy_changed(vehicle_id: int) -> None:
    """A reading that tells the level changed: let the worker look at once whether somebody has to be told (not at the next regular check)."""
    with _energy_lock:
        _energy_pending.add(vehicle_id)
    events.changed()


def take_energy_vehicles() -> set[int]:
    with _energy_lock:
        got = set(_energy_pending)
        _energy_pending.clear()
    return got


def check_energy(conn: sqlite3.Connection, vehicle_ids: set[int] | None = None, now: datetime | None = None) -> int:
    """Tell everybody who asked for the low tank / battery message whose level just fell to their threshold. ``vehicle_ids`` = the cars with a new
    reading (None = all, the safety net of the regular check). Returns the number of messages."""
    with _run_lock:
        return _check_energy(conn, vehicle_ids, now)


def _check_energy(conn: sqlite3.Connection, vehicle_ids: set[int] | None, now: datetime | None) -> int:
    from . import mqtt_ha

    now = now or datetime.now(UTC)
    t = i18n.translator(config.language())
    by_push = push_mode()
    sent = 0
    for vehicle in conn.execute("SELECT * FROM vehicles WHERE archived = 0").fetchall():
        if vehicle_ids is not None and vehicle["id"] not in vehicle_ids:
            continue
        reading = _energy_reading(conn, vehicle)
        if reading is None:
            continue
        pct, km = reading
        for row in conn.execute("SELECT user_id, service FROM user_notify").fetchall():
            uid = row["user_id"]
            if (not by_push and not row["service"]) or (by_push and not push.devices(conn, uid)):
                continue
            if "low_energy" not in prefs(conn, uid, vehicle["id"])["events"]:
                continue
            thr_pct, thr_km = energy_thresholds(conn, uid, vehicle)
            what = energy_decision(pct, km, thr_pct, thr_km, _energy_fired(conn, uid, vehicle["id"]))
            if what == "rearm":
                _set_energy_fired(conn, uid, vehicle["id"], False, now)
            elif what == "fire":
                ok, error = _deliver(
                    conn,
                    uid,
                    row["service"],
                    vehicle["name"],
                    _energy_text(vehicle, pct, km, t),
                    link_for(
                        vehicle, {PAGE_OF["refuel"]}
                    ),  # a low tank or battery: the page where it is filled up (stations, charging points)
                    vehicle["id"],
                    link_path(vehicle, {PAGE_OF["refuel"]}),
                )
                if ok:
                    sent += 1
                    _set_energy_fired(conn, uid, vehicle["id"], True, now)
                else:
                    log.warning("Notification for user %s failed: %s", uid, error)
        if (
            config.ha_notice_sensor_enabled() and config.mqtt_discovery_enabled() and mqtt_ha.publisher.connected
        ):  # the sensor *Last notification*
            thr = energy_thresholds_default(vehicle)
            what = energy_decision(pct, km, *thr, _energy_fired(conn, 0, vehicle["id"]))
            if what == "rearm":
                _set_energy_fired(conn, 0, vehicle["id"], False, now)
            elif what == "fire":
                mqtt_ha.add_notice(conn, vehicle["id"], [_energy_text(vehicle, pct, km, t)], now)
                _set_energy_fired(conn, 0, vehicle["id"], True, now)
                mqtt_ha.publisher.publish_vehicle(conn, vehicle)
                sent += 1
    return sent


def energy_thresholds_default(vehicle) -> tuple[int | None, int | None]:
    """The threshold nobody chose: the yellow level of the car."""
    lv = energy.levels(vehicle)
    return (lv["warn_pct"] or None, lv["warn_km"] or None)


_recent: dict[tuple[int, str, str], float] = {}
_run_lock = threading.Lock()  # one check at a time: a trip that ends while the regular check runs must not be announced twice
SAME_MESSAGE_SECONDS = 180


def _deliver(
    conn: sqlite3.Connection,
    user_id: int,
    service: str,
    title: str,
    message: str,
    url: str = "",
    vehicle_id: int | None = None,
    path: str = "",
) -> tuple[bool, str]:
    """One message to one person: web push with a port, the Home Assistant service without. ``url`` is the full address a tap opens (the Home Assistant
    app needs one); ``path`` the same page as a path of the app itself - a web push takes that, so it needs no saved address. The same words to the same
    person within three minutes go out once."""
    now = time.monotonic()
    for k in [k for k, at in _recent.items() if now - at > SAME_MESSAGE_SECONDS]:
        _recent.pop(k, None)
    if (user_id, title, message) in _recent and not title.startswith("Car Assistant"):
        return True, ""
    _recent[(user_id, title, message)] = now
    if push_mode():
        sent = push.send(conn, user_id, title, message, path or url, vehicle_id)
        conn.execute(
            "INSERT INTO notify_log(title, message, ok, error) VALUES(?,?,?,?)",
            (title, message, int(bool(sent)), None if sent else "no device"),
        )
        return bool(sent), "" if sent else "no device"
    return send(conn, title, message, service, url)


_trip_flag = threading.Event()


def trip_ended() -> None:
    """A drive became a trip: let the worker tell the people who want to know right away (not only at the next 6-hourly check)."""
    _trip_flag.set()
    events.changed()


def event_now() -> None:
    """Something happened that a person wants to hear about at once (a refuel was noticed): wake the worker like a finished trip does."""
    trip_ended()


def take_trip_flag() -> bool:
    was = _trip_flag.is_set()
    _trip_flag.clear()
    return was


def _addon_updates(conn: sqlite3.Connection) -> list[tuple[str, str, str]]:
    """Installed plugins / integrations whose source offers a newer version: (key, name, version)."""
    from . import addons
    from .sources import is_newer

    rows = conn.execute("SELECT * FROM vehicle_addons WHERE status != 'missing'").fetchall()
    latest = addons._newer_versions(conn, rows)
    out = []
    for r in rows:
        try:
            manifest = json.loads(r["manifest"])
        except (ValueError, TypeError):
            continue
        offered = latest.get(r["id"], "")
        if offered and is_newer(offered, manifest.get("version", "")):
            out.append((f"upd:{r['addon_id']}:{offered}", manifest.get("name") or r["addon_id"], offered))
    return out


def check_users(conn: sqlite3.Connection, now: datetime | None = None, only: set[str] | None = None) -> int:
    """Everyone who set up a way to be told gets what they chose in the matrix (per car) and the general events. Returns the number sent."""
    with _run_lock:
        return _check_users(conn, now, only)


def _check_users(conn: sqlite3.Connection, now: datetime | None, only: set[str] | None) -> int:
    now = now or datetime.now(UTC)
    t = i18n.translator(config.language())
    sent = 0
    by_push = push_mode()
    updates = _addon_updates(conn) if only is None else []
    for row in conn.execute("SELECT user_id, service, events, general FROM user_notify").fetchall():
        if (not by_push and not row["service"]) or (by_push and not push.devices(conn, row["user_id"])):
            continue
        for vehicle in conn.execute("SELECT * FROM vehicles WHERE archived = 0").fetchall():
            wanted = set(prefs(conn, row["user_id"], vehicle["id"])["events"])
            if only is not None:
                wanted &= only
            if not wanted:
                continue
            lines, keys, pages = _lines_for(conn, vehicle, wanted, now, f"u{row['user_id']}", t)
            if not lines:
                continue
            ok, error = _deliver(
                conn,
                row["user_id"],
                row["service"],
                vehicle["name"],
                "\n".join(lines),
                link_for(vehicle, pages),
                vehicle["id"],
                link_path(vehicle, pages),
            )
            if ok:
                sent += 1
                _remember(conn, keys, now)
            else:
                log.warning("Notification for user %s failed: %s", row["user_id"], error)
        if "addon_update" in _general_of(row["general"]) and updates:
            user_key = f"u{row['user_id']}"
            fresh = [(f"{user_key}:{k}", n, v) for k, n, v in updates if not _recently_sent(conn, f"{user_key}:{k}", now)]
            if fresh:
                ok, error = _deliver(
                    conn,
                    row["user_id"],
                    row["service"],
                    "Car Assistant",
                    "\n".join(t("notify.addon_update", name=n, version=v) for _k, n, v in fresh),
                    config.external_url() or "",
                    None,
                    "/",
                )
                if ok:
                    sent += 1
                    _remember(conn, [k for k, _n, _v in fresh], now)
    sent += _feed_home_assistant(conn, now, t, only)
    if only is None:
        sent += _check_energy(conn, None, now)  # the safety net: a reading that arrived while the app was off; told once, never repeated
    return sent


def _feed_home_assistant(conn: sqlite3.Connection, now: datetime, t, only: set[str] | None) -> int:
    """Home Assistant is one more recipient that needs no person to sign up: whatever the app announces for a car - every kind of message - is put
    on the car's sensor *Last notification* (MQTT), so an automation there can pass it on. Nothing is remembered while MQTT is not connected: the
    messages wait and are put on the sensor at the next check."""
    from . import mqtt_ha

    if not config.ha_notice_sensor_enabled() or not config.mqtt_discovery_enabled() or not mqtt_ha.publisher.connected:
        return 0
    wanted = set(EVENTS) if only is None else set(EVENTS) & only
    sent = 0
    for vehicle in conn.execute("SELECT * FROM vehicles WHERE archived = 0").fetchall():
        lines, keys, _pages = _lines_for(conn, vehicle, wanted, now, "ha", t)
        if not lines:
            continue
        mqtt_ha.add_notice(conn, vehicle["id"], lines, now)
        _remember(conn, keys, now)
        mqtt_ha.publisher.publish_vehicle(conn, vehicle)
        sent += 1
    return sent


def _remember(conn: sqlite3.Connection, keys: list[str], now: datetime) -> None:
    for key in keys:
        conn.execute(
            "INSERT INTO notify_state(key, last_sent) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET last_sent = excluded.last_sent",
            (key, now.isoformat()),
        )


def check_all(conn: sqlite3.Connection, now: datetime | None = None) -> int:
    """Send what is due to everybody who asked for it. Returns the number sent."""
    return check_users(conn, now)
