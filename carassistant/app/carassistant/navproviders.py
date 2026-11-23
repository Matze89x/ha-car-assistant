"""Where a destination is sent to navigate: the plugin of the car (when it offers ``navigate``), or a navigation service of the people's choice.

A provider is only a *link*: Car Assistant builds the address with the destination in it and the phone opens its navigation app (or the website).
Nothing is sent from this server to a provider. The choice (System -> Navigation) is one for the whole app; ``''`` means *automatic*: the plugin
of the car when it offers one, else Google Maps.
"""

from __future__ import annotations

import sqlite3
from urllib.parse import quote

from . import addons, config, db, pluginsvc

SETTING = "nav.provider"
DEFAULT = "google"
PLUGIN = "plugin:"  # the key of a plugin in the list: plugin:<package id>

# (key, name, link with {lat} {lon} {name}); a link opens the installed app of that provider or its website
PROVIDERS: tuple[tuple[str, str, str], ...] = (
    ("google", "Google Maps", "https://www.google.com/maps/dir/?api=1&destination={lat}%2C{lon}&travelmode=driving"),
    ("apple", "Apple Maps", "https://maps.apple.com/directions?destination={lat},{lon}&mode=driving"),
    ("waze", "Waze", "https://waze.com/ul?ll={lat},{lon}&navigate=yes"),
    ("bing", "Bing Maps", "https://bing.com/maps/default.aspx?rtp=~pos.{lat}_{lon}_{name}&rtop=0~1~0&mode=D"),
    ("osm", "OpenStreetMap", "https://www.openstreetmap.org/directions?engine=fossgis_osrm_car&route=%3B{lat}%2C{lon}"),
    ("mapy", "Mapy.com", "https://mapy.com/fnc/v1/route?end={lon},{lat}&routeType=car_fast&navigate=true"),
    ("here", "HERE WeGo", "https://share.here.com/l/{lat},{lon},{name}?z=16&p=yes"),
    ("yandex", "Yandex Maps", "https://yandex.com/maps/?rtext=~{lat},{lon}&rtt=auto"),
    ("yandexnavi", "Yandex Navigator", "yandexnavi://build_route_on_map?lat_to={lat}&lon_to={lon}"),
    ("magicearth", "Magic Earth", "magicearth://?drive_to&lat={lat}&lon={lon}"),
    ("sygic", "Sygic", "com.sygic.aura://coordinate|{lon}|{lat}|drive"),
    ("geo", "Android / geo link", "geo:{lat},{lon}?q={lat},{lon}({name})"),
)
BY_KEY = {k: (n, t) for k, n, t in PROVIDERS}


def url(key: str, lat: float, lon: float, name: str = "") -> str | None:
    """The link that opens that provider with the destination, or None for an unknown key."""
    if key not in BY_KEY:
        return None
    return BY_KEY[key][1].format(lat=f"{lat:.6f}", lon=f"{lon:.6f}", name=quote(name[:80] or "Destination", safe=""))


def chosen(conn: sqlite3.Connection) -> str:
    """The setting: '' (automatic) or the key of one provider."""
    value = db.get_setting(conn, SETTING, "") or ""
    return value if value in BY_KEY else ""


def set_chosen(conn: sqlite3.Connection, key: str) -> None:
    db.set_setting(conn, SETTING, key if key in BY_KEY else None)


def plugins_for(conn: sqlite3.Connection, vehicle_id: int) -> list[dict]:
    """The plugins of this car that can take a destination right now (installed, switched on, service running)."""
    out = []
    for a in addons.list_for(conn, vehicle_id):
        cap = (a["m"].get("capabilities") or {}).get("navigate")
        if cap and a["kind"] == "plugin" and pluginsvc.state(a["id"], a) == "running":
            out.append(
                {
                    "key": PLUGIN + a["addon_id"],
                    "name": cap.get("label") or a["m"].get("name") or a["addon_id"],
                    "pk": a["id"],
                    "path": cap["path"],
                }
            )
    return out


def options(conn: sqlite3.Connection, vehicle_id: int) -> tuple[list[dict], str]:
    """The list for the choice at the map - plugins of the car first, then the providers - and the key that is chosen at first."""
    plugins = plugins_for(conn, vehicle_id)
    rows = [{"key": p["key"], "name": p["name"], "plugin": True} for p in plugins]
    rows += [{"key": k, "name": n, "plugin": False} for k, n, _t in PROVIDERS]
    picked = chosen(conn)
    first = picked or (plugins[0]["key"] if plugins else DEFAULT)
    return rows, first


def send(
    conn: sqlite3.Connection, vehicle_id: int, key: str, lat: float, lon: float, name: str, address: str, user: str = "ha"
) -> tuple[bool, str]:
    """Hand a destination to a plugin of the car. ``(ok, message)``; a provider is not 'sent to' - its link is opened by the phone."""
    for p in plugins_for(conn, vehicle_id):
        if p["key"] == key:
            payload = {
                "vehicle": vehicle_id,
                "name": name[:120],
                "address": address[:240],
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "language": config.language(),
            }
            return pluginsvc.call(p["pk"], p["path"], payload, vehicle_id, user)
    return False, "unknown"
