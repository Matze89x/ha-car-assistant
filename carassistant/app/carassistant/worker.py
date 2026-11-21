"""Background loop: poll bound HA entities, keep MQTT sensors current, send reminders."""

from __future__ import annotations

import logging
import threading
import time

from . import config, db, events, live, notify, simulator
from .mqtt_ha import publisher

log = logging.getLogger(__name__)

POLL_SECONDS = 300
PUBLISH_SECONDS = 3600
NOTIFY_SECONDS = 6 * 3600
MAINTENANCE_SECONDS = 24 * 3600


def maintain(conn) -> None:
    """Daily housekeeping: refresh query statistics and fold the write-ahead log back into the database file."""
    try:
        from . import connectors

        connectors.trim_all(conn)  # log lines older than the retention go
        conn.execute("PRAGMA optimize")
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception:
        log.exception("Database maintenance failed")


def run_once(state: dict[str, float], now: float) -> None:
    changed = events.dirty.is_set()
    events.dirty.clear()
    with db.tx() as conn:
        if now - state["poll"] >= POLL_SECONDS:
            state["poll"] = now
            for vehicle in conn.execute("SELECT * FROM vehicles WHERE archived = 0").fetchall():
                if any(vehicle[k] for k in ("bind_odometer", "bind_fuel_level", "bind_range", "bind_tracker")):
                    try:
                        live.refresh_vehicle(conn, vehicle)
                        changed = True  # live values (fuel level, range) are republished on every poll
                    except Exception:
                        log.exception("Polling vehicle %s failed", vehicle["id"])
        if config.mqtt_discovery_enabled() and (changed or now - state["publish"] >= PUBLISH_SECONDS):
            state["publish"] = now
            try:
                publisher.publish_all(conn)
            except Exception:
                log.exception("MQTT publish failed")
        if (
            conn.execute("SELECT 1 FROM settings WHERE key = 'sources.auto' AND value = '1'").fetchone()
            and now - state.get("srcauto", -1e9) >= MAINTENANCE_SECONDS
        ):
            state["srcauto"] = now  # opt-in (Settings -> System): read the sources once a day, so updates show up by themselves
            try:
                from . import sources

                for kind in sources.KINDS:
                    sources.refresh_all(conn, kind)
                changed = True
            except Exception:
                log.exception("Reading the sources failed")
        if now - state.setdefault("maintain", now) >= MAINTENANCE_SECONDS:
            state["maintain"] = now
            maintain(conn)
        if notify.take_trip_flag():
            try:
                notify.check_users(conn, only={"trip_end"})
            except Exception:
                log.exception("Trip notification failed")
        if now - state["notify"] >= NOTIFY_SECONDS:
            state["notify"] = now
            try:
                notify.check_all(conn)
            except Exception:
                log.exception("Reminder check failed")


def loop() -> None:
    state = {"poll": -POLL_SECONDS, "publish": -PUBLISH_SECONDS, "notify": time.monotonic() - NOTIFY_SECONDS + 60}
    while not events.stop.is_set():
        try:
            run_once(state, time.monotonic())
        except Exception:
            log.exception("Worker iteration failed")
        if events.dirty.wait(timeout=30):
            time.sleep(2)  # debounce bursts of edits


def start() -> threading.Thread:
    thread = threading.Thread(target=loop, name="worker", daemon=True)
    thread.start()
    simulator.start()  # plays the scenario of plugins from a source that are switched on; idle otherwise
    return thread
