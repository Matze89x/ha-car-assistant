"""Reminders for every person who asked for them: through a Home Assistant ``notify.*`` service (no port set) or as web push (a port is set).
Each item is announced at most every REPEAT_DAYS days."""

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


def push_mode() -> bool:
    """With a port set people sign in and get web push; without one the Home Assistant notify service is the way."""
    return (ha.network_port() or (None, None))[1] is not None


def anyone_notified(conn: sqlite3.Connection) -> bool:
    """Did anybody set up a way to be notified? (the start page asks for it as long as nobody did)"""
    return bool(
        conn.execute("SELECT 1 FROM user_notify WHERE service != ''").fetchone() or conn.execute("SELECT 1 FROM push_devices").fetchone()
    )


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


def matrix(conn: sqlite3.Connection, user_id: int) -> dict:
    """What the person gets, for the settings page: the choice for ``default`` (new cars), every car of the installation with its events, and the
    general events. Cars come and go by themselves: a new car starts with the choice for new cars, a removed one disappears."""
    row = conn.execute("SELECT events, general FROM user_notify WHERE user_id = ?", (user_id,)).fetchone()
    default = set(_events_of(row["events"])) if row else set()
    cars = []
    for v in conn.execute("SELECT id, name FROM vehicles WHERE archived = 0 ORDER BY name COLLATE NOCASE").fetchall():
        own = conn.execute("SELECT events FROM user_notify_vehicle WHERE user_id = ? AND vehicle_id = ?", (user_id, v["id"])).fetchone()
        cars.append({"id": v["id"], "name": v["name"], "events": set(_events_of(own["events"])) if own else set(default)})
    return {"default": default, "cars": cars, "general": set(_general_of(row["general"])) if row else set()}


def save_matrix(conn: sqlite3.Connection, user_id: int, form) -> None:
    """The whole matrix from one form: ``ev_new`` (the choice for new cars), ``ev_<car id>`` per car, ``gen`` (general events)."""
    conn.execute("INSERT OR IGNORE INTO user_notify(user_id, service, events) VALUES(?, '', '[]')", (user_id,))
    default = [e for e in EVENTS if e in form.getlist("ev_new")]
    general = [e for e in GENERAL if e in form.getlist("gen")]
    conn.execute("UPDATE user_notify SET events = ?, general = ? WHERE user_id = ?", (json.dumps(default), json.dumps(general), user_id))
    for v in conn.execute("SELECT id FROM vehicles WHERE archived = 0").fetchall():
        chosen = [e for e in EVENTS if e in form.getlist(f"ev_{v['id']}")]
        conn.execute(
            "INSERT INTO user_notify_vehicle(user_id, vehicle_id, events, enabled) VALUES(?,?,?,1) "
            "ON CONFLICT(user_id, vehicle_id) DO UPDATE SET events = excluded.events, enabled = 1",
            (user_id, v["id"], json.dumps(chosen)),
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
}


def link_for(vehicle, pages: set[str]) -> str:
    """The address a notification opens: the page of that one topic, or the car when it is about several (empty without a saved address)."""
    base = (config.external_url() or "").rstrip("/")
    if not base:
        return ""
    only = next(iter(pages)) if len(pages) == 1 else ""
    return f"{base}/v/{vehicle['slug'] or vehicle['id']}{only}"


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
                pages.add("")
    if "open_closure" in events:
        opened = status.open_closures(live)
        key = f"{user_key}:open:{vid}"
        if opened and not _recently_sent(conn, key, now):
            keys.append(key)
            lines.append(t("notify.closures_open", n=len(opened)))
            pages.add("")
    if "low_energy" in events:
        capacity = vehicle["battery_kwh"] if vehicle["fuel_type"] == "electric" else vehicle["tank_l"]
        mode = energy.mode(vehicle)
        info = status.tank(live, capacity, mode)
        hero = status.hero_range(live, t, capacity, "kWh" if mode == "charge" else "L", mode)
        level = energy.state(vehicle, info["pct"] if info else None, hero["km"] if hero else None) if (info or hero) else "ok"
        key = f"{user_key}:energy:{vid}:{level}"
        if level in ("soon", "overdue") and not _recently_sent(conn, key, now):
            keys.append(key)
            parts = [f"{info['pct']} %"] if info and info["pct"] is not None else []
            if hero:
                parts.append(units.of().dist_str(hero["km"]))
            lines.append(f"{t('notify.energy_charge') if mode == 'charge' else t('notify.energy_fuel')}: {' · '.join(parts)}")
            pages.add("")
    if "tyre_pressure" in events:
        low = status.low_tyres(conn, vid, live)
        key = f"{user_key}:tyres:{vid}:{','.join(sorted(low))}"
        if low and not _recently_sent(conn, key, now):
            keys.append(key)
            lines.append(t("notify.tyres_low", n=len(low), names=", ".join(t("tp." + w) for w in sorted(low))))
            pages.add(PAGE_OF["tyre_pressure"])
    if "trip_end" in events:
        since = (now - timedelta(days=1)).date().isoformat()
        for trip in conn.execute(
            "SELECT id, distance_km, end_place FROM trips WHERE vehicle_id = ? AND date >= ? AND source != 'manual' ORDER BY id DESC LIMIT 3",
            (vid, since),
        ):
            key = f"{user_key}:trip:{vid}:{trip['id']}"
            if not _recently_sent(conn, key, now):
                keys.append(key)
                distance = trip["distance_km"]
                lines.append(t("notify.trip_end", d=units.of().dist_str(distance) if distance else "-", place=trip["end_place"] or ""))
                pages.add(PAGE_OF["trip_end"])
    if "refuel" in events:
        from . import refuel_detect

        for item in refuel_detect.todo(conn, vid):
            key = f"{user_key}:refuel:{vid}:{item['id']}"
            if not _recently_sent(conn, key, now):
                keys.append(key)
                lines.append(t("notify.refuel", pct=item["rise"] or "", litres=f" (~{item['litres']} L)" if item["litres"] else ""))
                pages.add(PAGE_OF["refuel"])
    return lines, keys, pages


_recent: dict[tuple[int, str, str], float] = {}
_run_lock = threading.Lock()  # one check at a time: a trip that ends while the regular check runs must not be announced twice
SAME_MESSAGE_SECONDS = 180


def _deliver(
    conn: sqlite3.Connection, user_id: int, service: str, title: str, message: str, url: str = "", vehicle_id: int | None = None
) -> tuple[bool, str]:
    """One message to one person: web push with a port, the Home Assistant service without. ``url`` is the page a tap opens. The same words to
    the same person within three minutes go out once."""
    now = time.monotonic()
    for k in [k for k, at in _recent.items() if now - at > SAME_MESSAGE_SECONDS]:
        _recent.pop(k, None)
    if (user_id, title, message) in _recent and not title.startswith("Car Assistant"):
        return True, ""
    _recent[(user_id, title, message)] = now
    if push_mode():
        sent = push.send(conn, user_id, title, message, url, vehicle_id)
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
                conn, row["user_id"], row["service"], vehicle["name"], "\n".join(lines), link_for(vehicle, pages), vehicle["id"]
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
                )
                if ok:
                    sent += 1
                    _remember(conn, [k for k, _n, _v in fresh], now)
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
