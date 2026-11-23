"""*Check Home Assistant* (System -> MQTT): like the test push, but for the sensors. It looks at every step from the app to Home Assistant and
says where it stops: can the app reach Home Assistant, is a broker found and connected, did a test message put on the sensor *Last notification*
of every car arrive in Home Assistant - and which entity IDs Home Assistant gave the sensors."""

from __future__ import annotations

import time
from datetime import datetime

from . import config, db, ha, i18n, mqtt_ha

WAIT_SECONDS = 8  # how long Home Assistant gets to show the test message
last: dict | None = None  # the result of the last check (kept in memory: it only matters while somebody looks at the page)


def _step(ok: bool | None, key: str, **kw) -> dict:
    return {"ok": ok, "key": key, **kw}


def _states() -> list[dict]:
    data = ha._get("/states")
    return data if isinstance(data, list) else []


def _entities_of(states: list[dict], car: str, names: list[str]) -> dict[str, dict]:
    """Home Assistant names an entity ``<device> <entity>`` (friendly name): find ours by that. ``{sensor name: state}``"""
    wanted = {f"{car} {n}": n for n in names}
    return {wanted[s["attributes"]["friendly_name"]]: s for s in states if (s.get("attributes") or {}).get("friendly_name") in wanted}


def run(wait: int = WAIT_SECONDS) -> dict:
    """Do the check. ``{time, steps: [{ok, key, ...}], cars: [{name, entity, found, total, entities}]}``."""
    global last
    steps: list[dict] = []
    cars: list[dict] = []
    started = datetime.now()
    api = ha.available() and isinstance(ha._get("/config"), dict)
    steps.append(_step(api, "api_ok" if api else "api_no"))
    settings = config.mqtt_settings()
    pub = mqtt_ha.publisher
    if not config.mqtt_discovery_enabled():
        steps.append(_step(False, "mqtt_off"))
    elif not settings:
        steps.append(_step(False, "mqtt_nobroker"))
    elif not pub.connected:
        steps.append(_step(False, "mqtt_down", reason=pub.last_error or "other"))
    else:
        steps.append(_step(True, "mqtt_ok", host=settings["host"], port=settings["port"]))
        cars = _test_cars(steps, api, wait)
    last = {"time": started.isoformat(timespec="seconds"), "steps": steps, "cars": cars}
    return last


def _test_cars(steps: list[dict], api: bool, wait: int) -> list[dict]:
    t = i18n.translator(config.language())
    pub = mqtt_ha.publisher
    with db.tx() as conn:
        vehicles = conn.execute("SELECT * FROM vehicles WHERE archived = 0 ORDER BY name COLLATE NOCASE").fetchall()
        if not vehicles:
            steps.append(_step(None, "no_car"))
            return []
        notice_on = config.ha_notice_sensor_enabled()
        text = t("check.test_text", time=datetime.now().strftime("%H:%M:%S"))
        if notice_on:
            for v in vehicles:
                mqtt_ha.add_notice(conn, v["id"], [text], datetime.now())
        pub.resend()
        for v in vehicles:
            pub.publish_vehicle(conn, v)
        steps.append(_step(True, "sent", n=len(vehicles), notice=notice_on))
        sensors = {
            v["id"]: [s for s in mqtt_ha.wanted_sensors(v, mqtt_ha.compute_values(conn, v), modules_off(conn, v["id"]))] for v in vehicles
        }
    if not api:
        return []
    probe = mqtt_ha.display_name("Last notification")
    expected = text[: mqtt_ha.NOTICE_STATE_MAX]
    found: dict[int, dict[str, dict]] = {}
    for _ in range(max(1, wait)):
        states = _states()
        for v in vehicles:
            names = [mqtt_ha.display_name(s.name) for s in sensors[v["id"]]]
            found[v["id"]] = _entities_of(states, v["name"], names)
        if not notice_on or all(probe in found[v["id"]] and found[v["id"]][probe].get("state") == expected for v in vehicles):
            break
        time.sleep(1)
    cars = []
    for v in vehicles:
        mine = found.get(v["id"], {})
        entity = mine.get(probe, {})
        arrived = bool(entity) and (not notice_on or entity.get("state") == expected)
        cars.append(
            {
                "name": v["name"],
                "ok": arrived if notice_on else bool(mine),
                "entity": entity.get("entity_id", ""),
                "found": len(mine),
                "total": len(sensors[v["id"]]),
                "entities": sorted(s["entity_id"] for s in mine.values())[:40],
            }
        )
    return cars


def modules_off(conn, vehicle_id: int) -> set[str]:
    from . import modules

    return modules.disabled(conn, vehicle_id)
