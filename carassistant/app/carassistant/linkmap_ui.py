"""The words and the order of the connection map page (names, explanations, "how long ago"), built on the plain data of linkmap.py."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from . import config, i18n, linkmap

# which switch of the sensors in Home Assistant (System -> MQTT) an area belongs to; an area that is not here does not go to Home Assistant
HA_GROUP = {
    "dashboard": "live", "security": "live", "tires": "live", "energy": "live", "service": "live", "location": "position", "trips": "stats",
}  # fmt: skip


def ago(stamp: str | None, t) -> str:
    """ "just now", "5 min ago" ... in the language of the app; ``never`` for no time at all."""
    age = linkmap._age(stamp)
    if age is None:
        return t("lm.never")
    seconds = max(0, int(age))
    if seconds < 90:
        return t("lm.now")
    if seconds < 3600:
        return t("lm.min", n=seconds // 60)
    if seconds < 86400:
        return t("lm.hours", n=seconds // 3600)
    return t("lm.days", n=seconds // 86400)


def _ha_goes(key: str) -> bool:
    group = HA_GROUP.get(key)
    return bool(group) and config.mqtt_discovery_enabled() and group not in config.ha_groups_off()


def build(conn: sqlite3.Connection, vehicle_id: int) -> dict:
    """The map of one car with every text in place. Pure data (the page and the JSON endpoint both use it)."""
    t = i18n.translator(config.language())
    g = linkmap.graph(conn, vehicle_id)
    counts: dict[str, int] = {}
    for e in g["edges"]:
        counts[e["area"]] = counts.get(e["area"], 0) + e["n"]
    for p in g["plugins"]:
        if not p["active"]:
            p["meta"] = t("lm.stopped")
        elif p["last"]:
            p["meta"] = t("lm.meta", sets=p["sets"], gets=p["gets"], ago=ago(p["last"], t))
        else:
            p["meta"] = t("lm.meta_none")
    for a in g["areas"]:
        key = a["key"]
        a["name"] = a.get("name") or t(f"lm.area_{key}")
        a["explain"] = t("lm.ex_int") if a.get("integration") else t(f"lm.ex_{key}")
        a["ha"] = _ha_goes(key)
        a["meta"] = t("lm.area_meta", n=counts.get(key, 0), ago=ago(a["last"], t)) if counts.get(key) else t("lm.meta_none")
        a["linked"] = bool(counts.get(key))  # something is connected: it is drawn in full, the others fold away
    mine: dict[str, list[dict]] = {}
    for e in g["edges"]:  # the chips of a plugin (the phone shows these instead of lines)
        mine.setdefault(e["plugin"], []).append(e)
    by_key = {a["key"]: a for a in g["areas"]}
    for p in g["plugins"]:
        seen: dict[str, dict] = {}
        for e in mine.get(p["id"], []):
            area = by_key.get(e["area"]) or {}
            item = seen.setdefault(
                e["area"],
                {
                    "area": e["area"],
                    "name": area.get("name", e["area"]),
                    "icon": area.get("icon", "puzzle"),
                    "chip": area.get("chip", "c4"),
                    "n_set": 0,
                    "n_get": 0,
                    "state": e["state"],
                    "last": e["last"],
                },
            )
            item["n_" + e["dir"]] += e["n"]
            if e["last"] and (not item["last"] or e["last"] > item["last"]):
                item["last"] = e["last"]
                item["state"] = e["state"]
        for item in seen.values():
            item["ago"] = ago(item["last"], t)
        # the tiles of a plugin (the phone shows these instead of lines): the busiest first
        p["links"] = sorted(seen.values(), key=lambda x: (-(x["n_set"] + x["n_get"]), x["name"].lower()))
    g["generated"] = datetime.now(UTC).isoformat(timespec="seconds")
    return g


def light(g: dict) -> dict:
    """What the page refreshes every few seconds: only texts and states (the structure is the ``version``)."""
    return {
        "version": g["version"],
        "plugins": [{"id": p["id"], "meta": p["meta"], "state": p["state"]} for p in g["plugins"]],
        "areas": [{"key": a["key"], "meta": a["meta"], "state": a["state"]} for a in g["areas"]],
        "edges": [{"plugin": e["plugin"], "area": e["area"], "dir": e["dir"], "state": e["state"]} for e in g["edges"]],
    }
