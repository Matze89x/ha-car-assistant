"""Fuel stations and charging points nearby.

* Germany: Tankerkönig (prices from the Markttransparenzstelle für Kraftstoffe, licence CC BY 4.0 – attribution is shown
  in the UI). Needs a free personal API key.
* Everywhere else (or without a key): OpenStreetMap via Overpass – stations only, no prices (no open price source).

Charging points (electric cars): OpenStreetMap via Overpass (no key; the plugs and their power as far as the map has them) or a provider file
(``chargeproviders.py``, Open Charge Map is shipped and needs a key of the person's own). Neither knows whether a point is free right now.

Rate limits: one real request per ~5 minutes per area (cached, location rounded to ~1 km).
"""

from __future__ import annotations

import logging
import math
import re
import threading
import time
from dataclasses import dataclass
from typing import Any

import requests

from . import chargeproviders, config, fuelproviders

log = logging.getLogger(__name__)

TANKERKOENIG_URL = "https://creativecommons.tankerkoenig.de/json/list.php"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "ha-car-assistant/2.0 (+https://github.com/Matze89x/ha-car-assistant)"
CACHE_SECONDS = 300
MAX_RADIUS_KM = 25
FUELS = ("e5", "e10", "diesel")


class StationsError(RuntimeError):
    """``args[0]`` is an i18n key."""


@dataclass
class Station:
    name: str
    brand: str
    address: str
    lat: float
    lon: float
    distance_km: float
    price: float | None = None
    is_open: bool | None = None
    # charging points only (empty for a fuel station)
    operator: str = ""
    points: int | None = None  # how many cars can charge at once, when the source knows
    max_kw: float | None = None
    plugs: tuple = ()  # ({"type", "label", "n", "kw"}, ...): one per kind of plug, the strongest first
    fee: str = ""  # what the source says about the cost (free text)
    free: bool | None = None  # no fee for sure / a fee for sure / unknown
    access: str = ""  # restrictions (customers only, private ...)
    hours: str = ""
    provider: str = ""  # the data provider that must be named (Open Charge Map hands out data of many)


_cache: dict[tuple, tuple[float, Any]] = {}
_lock = threading.Lock()


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(a))


def clean_params(lat: float, lon: float, radius: float) -> tuple[float, float, float]:
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise StationsError("err.coordinates")
    return lat, lon, min(max(float(radius), 1.0), MAX_RADIUS_KM)


def normalize_tankerkoenig(payload: dict, fuel: str, origin: tuple[float, float]) -> list[Station]:
    result = []
    for s in payload.get("stations", []):
        try:
            lat, lon = float(s["lat"]), float(s["lng"])
        except (KeyError, TypeError, ValueError):
            continue
        price = s.get(fuel)
        address = " ".join(str(x) for x in (s.get("street"), s.get("houseNumber")) if x)
        town = " ".join(str(x) for x in (s.get("postCode"), s.get("place")) if x)
        result.append(
            Station(
                name=str(s.get("name") or s.get("brand") or "?"),
                brand=str(s.get("brand") or ""),
                address=", ".join(x for x in (address, town) if x),
                lat=lat,
                lon=lon,
                distance_km=float(s["dist"]) if s.get("dist") is not None else haversine_km(*origin, lat, lon),
                price=float(price) if isinstance(price, int | float) else None,
                is_open=s.get("isOpen"),
            )
        )
    return result


def normalize_overpass(payload: dict, origin: tuple[float, float]) -> list[Station]:
    result = []
    for el in payload.get("elements", []):
        tags = el.get("tags") or {}
        lat = el.get("lat", (el.get("center") or {}).get("lat"))
        lon = el.get("lon", (el.get("center") or {}).get("lon"))
        if lat is None or lon is None:
            continue
        street = " ".join(x for x in (tags.get("addr:street"), tags.get("addr:housenumber")) if x)
        town = " ".join(x for x in (tags.get("addr:postcode"), tags.get("addr:city")) if x)
        result.append(
            Station(
                name=tags.get("name") or tags.get("brand") or tags.get("operator") or "?",
                brand=tags.get("brand") or "",
                address=", ".join(x for x in (street, town) if x),
                lat=float(lat),
                lon=float(lon),
                distance_km=haversine_km(*origin, float(lat), float(lon)),
            )
        )
    return result


def sort_stations(stations: list[Station], by: str) -> list[Station]:
    if by == "price":
        return sorted(stations, key=lambda s: (s.price is None, s.price if s.price is not None else 0, s.distance_km))
    return sorted(stations, key=lambda s: s.distance_km)


def _cached(key: tuple):
    with _lock:
        hit = _cache.get(key)
        if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
            return hit[1]
    return None


def _store(key: tuple, value: Any) -> Any:
    with _lock:
        _cache[key] = (time.monotonic(), value)
        if len(_cache) > 50:
            for old in sorted(_cache, key=lambda k: _cache[k][0])[:25]:
                _cache.pop(old, None)
    return value


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def fetch_tankerkoenig(lat: float, lon: float, radius: float, fuel: str) -> list[Station]:
    key = config.tankerkoenig_key()
    if not key:
        raise StationsError("err.no_key")
    lat, lon, radius = clean_params(lat, lon, radius)
    # One call returns every fuel type for the full radius (type=all); fuel/radius filtering happens locally.
    cache_key = ("tk", round(lat, 2), round(lon, 2))
    payload = _cached(cache_key)
    if payload is None:
        try:
            resp = requests.get(
                TANKERKOENIG_URL,
                params={"lat": f"{lat:.5f}", "lng": f"{lon:.5f}", "rad": MAX_RADIUS_KM, "type": "all", "apikey": key},
                headers={"User-Agent": USER_AGENT},
                timeout=15,
            )
            resp.raise_for_status()
            payload = resp.json()
        except (requests.RequestException, ValueError) as exc:
            log.warning("Tankerkönig request failed: %s", type(exc).__name__)  # never log the URL (contains the key)
            raise StationsError("err.stations_failed") from None
        if not payload.get("ok"):
            raise StationsError("err.stations_failed")
        _store(cache_key, payload)
    stations = normalize_tankerkoenig(payload, fuel, (lat, lon))
    return [s for s in stations if s.distance_km <= radius]


def fetch_osm(lat: float, lon: float, radius: float) -> list[Station]:
    lat, lon, radius = clean_params(lat, lon, radius)
    cache_key = ("osm", round(lat, 2), round(lon, 2), int(radius))
    hit = _cached(cache_key)
    if hit is not None:
        return hit
    query = (
        f'[out:json][timeout:20];(node["amenity"="fuel"](around:{int(radius * 1000)},{lat:.5f},{lon:.5f});'
        f'way["amenity"="fuel"](around:{int(radius * 1000)},{lat:.5f},{lon:.5f}););out center tags 60;'
    )
    try:
        resp = requests.post(OVERPASS_URL, data={"data": query}, headers={"User-Agent": USER_AGENT}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        log.warning("Overpass request failed: %s", type(exc).__name__)
        raise StationsError("err.stations_failed") from None
    return _store(cache_key, normalize_overpass(data, (lat, lon)))


def fetch_provider(defn: dict, lat: float, lon: float, radius: float, fuel: str) -> list[Station]:
    """Stations from a provider described as data (fuelproviders.py): one cached request per area, filtering by radius and fuel here."""
    lat, lon, radius = clean_params(lat, lon, radius)
    radius = min(radius, defn["max_radius_km"])
    key = fuelproviders.key_of(defn["id"]) if defn["key"] else ""
    if defn["key"] and not key:
        raise StationsError("err.no_key")
    cache_key = ("fp", defn["id"], round(lat, 2), round(lon, 2), int(radius), fuel if defn["fuel_codes"] else "")
    if defn["fuel_codes"] and fuel not in defn["fuel_codes"]:
        return []  # this service has no such fuel
    items = _cached(cache_key)
    if items is None:
        params, headers = fuelproviders.request_parts(
            defn, lat, lon, defn["max_radius_km"] if "{radius" not in "".join(defn["params"].values()) else radius, key, fuel
        )
        try:
            resp = requests.request(defn["method"], defn["url"], params=params if defn["method"] == "GET" else None,
                                    data=params if defn["method"] == "POST" else None, headers={"User-Agent": USER_AGENT, **headers}, timeout=20)  # fmt: skip
            resp.raise_for_status()
            items = fuelproviders.parse(defn, resp.json(), fuel)
        except (requests.RequestException, ValueError) as exc:
            log.warning("Fuel provider %s failed: %s", defn["id"], type(exc).__name__)  # never log the URL (it may hold a key)
            raise StationsError("err.stations_failed") from None
        _store(cache_key, items)
    out = []
    for s in items:
        d = haversine_km(lat, lon, s["lat"], s["lon"])
        if d > radius:
            continue
        out.append(
            Station(
                name=s["name"] or s["brand"] or s["address"] or "?",
                brand=s["brand"],
                address=s["address"],
                lat=s["lat"],
                lon=s["lon"],
                distance_km=d,
                price=s["prices"].get(fuel),
                is_open=s["is_open"],
            )
        )
    return out


def sources(country: str = "") -> list[dict]:
    """The places stations can come from, for the pages: ``{"id", "name", "prices", "needs_key", "has_key", "attribution", "countries"}``. The ones
    for the country of the installation come first."""
    out = [
        {"id": "tankerkoenig", "name": "Tankerk\u00f6nig (DE)", "prices": True, "needs_key": True, "has_key": bool(config.tankerkoenig_key()), "attribution": "", "countries": ["DE"], "key_url": "https://creativecommons.tankerkoenig.de", "license": "CC BY 4.0", "source": "built in"},
        {"id": "osm", "name": "OpenStreetMap", "prices": False, "needs_key": False, "has_key": True, "attribution": "", "countries": [], "key_url": "", "license": "ODbL", "source": "built in"},
    ]  # fmt: skip
    for d in fuelproviders.load().values():
        out.append(
            {"id": d["id"], "name": d["name"], "prices": bool(d["prices"]), "needs_key": bool(d["key"]), "has_key": bool(d["key"] and fuelproviders.key_of(d["id"])) or not d["key"],
             "attribution": d["attribution"], "countries": d["countries"], "key_url": (d["key"] or {}).get("url", ""), "source": d["source"], "license": d["license"]}
        )  # fmt: skip
    return sorted(out, key=lambda s: (bool(country) and country.upper() not in s["countries"], s["id"] == "osm", s["name"]))


def preferred_source() -> str:
    """The source the person chose to start with on the fuel page ('' = automatic)."""
    return (config.stored_setting("fuel.source") or "").strip()


def default_source(country: str = "") -> str:
    """The source used when none is chosen: the one the person prefers (if it can be used), else the first that fits the country and has its key,
    else OpenStreetMap."""
    wanted = preferred_source()
    if wanted:
        for s in sources(country):
            if s["id"] == wanted and s["has_key"]:
                return wanted
    for s in sources(country):
        if (
            s["id"] != "osm"
            and s["has_key"]
            and (country.upper() in s["countries"] or (not country and s["id"] == "tankerkoenig" and s["has_key"]))
        ):
            return s["id"]
    return "osm"


def nearby(lat: float, lon: float, radius: float, fuel: str, source: str, sort: str) -> tuple[list[Station], str]:
    """``source``: ``tankerkoenig`` | ``osm`` | the id of a provider (fuelproviders.py). Returns (stations, source_used)."""
    if fuel not in FUELS:
        fuel = "e5"
    if source == "tankerkoenig":
        return sort_stations(fetch_tankerkoenig(lat, lon, radius, fuel), sort), "tankerkoenig"
    defn = fuelproviders.load().get(source)
    if defn is not None:
        found = fetch_provider(defn, lat, lon, radius, fuel)
        return sort_stations(found, sort if defn["prices"] else "distance"), source
    return sort_stations(fetch_osm(lat, lon, radius), "distance"), "osm"


# ------------------------------------------------------------------ charging points

PLUG_TAGS = (  # (the part after ``socket:`` in OpenStreetMap, the kind of plug)
    ("type2", "type2"), ("type2_combo", "ccs"), ("ccs", "ccs"), ("type1_combo", "ccs"), ("chademo", "chademo"),
    ("tesla_supercharger", "nacs"), ("nacs", "nacs"), ("tesla_ccs", "ccs"), ("type1", "type1"), ("schuko", "schuko"),
)  # fmt: skip
POWER = re.compile(r"(\d+(?:[.,]\d+)?)")


def _power(text) -> float | None:
    """The strongest number in ``22 kW`` / ``11;22`` / ``22000 W`` as kilowatts."""
    if not isinstance(text, str):
        return None
    values = [float(m.replace(",", ".")) for m in POWER.findall(text)]
    if not values:
        return None
    top = max(values)
    if "w" in text.lower() and "kw" not in text.lower() and top >= 1000:
        top /= 1000.0
    return top if 0 < top <= 1500 else None


def normalize_overpass_charge(payload: dict, origin: tuple[float, float]) -> list[Station]:
    """Charging points from OpenStreetMap (``amenity=charging_station``): the plugs come from ``socket:*`` and their power from ``socket:*:output``."""
    result = []
    for el in payload.get("elements", []):
        tags = el.get("tags") or {}
        lat = el.get("lat", (el.get("center") or {}).get("lat"))
        lon = el.get("lon", (el.get("center") or {}).get("lon"))
        if lat is None or lon is None:
            continue
        plugs = []
        for tag, kind in PLUG_TAGS:
            count = tags.get(f"socket:{tag}")
            if count is None:
                continue
            n = int(count) if str(count).isdigit() else (1 if str(count).lower() in ("yes", "1") else 0)
            if n <= 0:
                continue
            plugs.append({"type": kind, "label": "", "n": n, "kw": _power(tags.get(f"socket:{tag}:output"))})
        powers = [p["kw"] for p in plugs if p["kw"]]
        max_kw = max(powers) if powers else None
        if max_kw is None:
            max_kw = _power(tags.get("charging_station:output") or tags.get("charge_point:output"))
        capacity = tags.get("capacity")
        street = " ".join(x for x in (tags.get("addr:street"), tags.get("addr:housenumber")) if x)
        town = " ".join(x for x in (tags.get("addr:postcode"), tags.get("addr:city")) if x)
        fee = str(tags.get("fee") or "").lower()
        result.append(
            Station(
                name=tags.get("name") or tags.get("brand") or tags.get("operator") or "?",
                brand=tags.get("brand") or "",
                address=", ".join(x for x in (street, town) if x),
                lat=float(lat),
                lon=float(lon),
                distance_km=haversine_km(*origin, float(lat), float(lon)),
                operator=str(tags.get("operator") or "")[:80],
                points=int(capacity) if str(capacity or "").isdigit() and int(capacity) > 0 else None,
                max_kw=max_kw,
                plugs=tuple(chargeproviders.sum_plugs(plugs)),
                free=True if fee == "no" else (False if fee == "yes" else None),
                access=str(tags.get("access") or "")[:40],
                hours=str(tags.get("opening_hours") or "")[:120],
            )
        )
    return result


def fetch_osm_charge(lat: float, lon: float, radius: float) -> list[Station]:
    lat, lon, radius = clean_params(lat, lon, radius)
    cache_key = ("osmc", round(lat, 2), round(lon, 2), int(radius))
    hit = _cached(cache_key)
    if hit is not None:
        return hit
    around = f"(around:{int(radius * 1000)},{lat:.5f},{lon:.5f})"
    query = f'[out:json][timeout:25];(node["amenity"="charging_station"]{around};way["amenity"="charging_station"]{around};);out center tags 150;'
    try:
        resp = requests.post(OVERPASS_URL, data={"data": query}, headers={"User-Agent": USER_AGENT}, timeout=35)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        log.warning("Overpass request failed: %s", type(exc).__name__)
        raise StationsError("err.stations_failed") from None
    return _store(cache_key, normalize_overpass_charge(data, (lat, lon)))


def fetch_charge_provider(defn: dict, lat: float, lon: float, radius: float) -> list[Station]:
    """Charging points from a provider described as data (chargeproviders.py): one cached request per area, the radius is filtered here again."""
    lat, lon, radius = clean_params(lat, lon, radius)
    radius = min(radius, defn["max_radius_km"])
    key = chargeproviders.key_of(defn["id"]) if defn["key"] else ""
    if defn["key"] and not key:
        raise StationsError("err.no_charge_key")
    cache_key = ("cp", defn["id"], round(lat, 2), round(lon, 2), int(radius))
    items = _cached(cache_key)
    if items is None:
        params, headers = chargeproviders.request_parts(defn, lat, lon, radius, key)
        try:
            resp = requests.request(defn["method"], defn["url"], params=params if defn["method"] == "GET" else None,
                                    data=params if defn["method"] == "POST" else None, headers={"User-Agent": USER_AGENT, **headers}, timeout=25)  # fmt: skip
            resp.raise_for_status()
            items = chargeproviders.parse(defn, resp.json())
        except (requests.RequestException, ValueError) as exc:
            log.warning(
                "Charging provider %s failed: %s", defn["id"], type(exc).__name__
            )  # never log the URL or the headers (they may hold a key)
            raise StationsError("err.stations_failed") from None
        _store(cache_key, items)
    out = []
    for s in items:
        d = haversine_km(lat, lon, s["lat"], s["lon"])
        if d > radius:
            continue
        max_kw = max([p["kw"] for p in s["plugs"] if p["kw"]], default=None)
        fee = s["fee"]
        out.append(
            Station(
                name=s["name"] or s["operator"] or s["address"] or "?",
                brand="",
                address=s["address"],
                lat=s["lat"],
                lon=s["lon"],
                distance_km=d,
                is_open=s["operational"],
                operator=s["operator"],
                points=s["points"],
                max_kw=max_kw,
                plugs=tuple(s["plugs"]),
                fee=fee,
                free=True if re.fullmatch(r"(?i)\s*(free|kostenlos|gratis)\b.*", fee or "") else None,
                access=s["access"],
                hours=s["hours"],
                provider=s["provider"],
            )
        )
    return out


def filter_charge(stations: list[Station], min_kw: float = 0, plug: str = "") -> list[Station]:
    """Only the points that have at least ``min_kw`` (a point whose power is not known does not count) and, when asked, a plug of that kind."""
    out = []
    for s in stations:
        if min_kw and (s.max_kw is None or s.max_kw < min_kw):
            continue
        if plug and not any(p["type"] == plug for p in s.plugs):
            continue
        out.append(s)
    return out


def sort_charge(stations: list[Station], by: str) -> list[Station]:
    if by == "power":
        return sorted(stations, key=lambda s: (s.max_kw is None, -(s.max_kw or 0), s.distance_km))
    return sorted(stations, key=lambda s: s.distance_km)


def charge_sources(country: str = "") -> list[dict]:
    """Where charging points can come from, for the pages: the same shape as ``sources()``. The ones for the country of the installation come first,
    OpenStreetMap (no key) is the fallback."""
    out = [
        {"id": "osm", "name": "OpenStreetMap", "prices": False, "needs_key": False, "has_key": True, "attribution": "", "countries": [], "key_url": "", "license": "ODbL", "source": "built in"},
    ]  # fmt: skip
    for d in chargeproviders.load().values():
        out.append(
            {"id": d["id"], "name": d["name"], "prices": False, "needs_key": bool(d["key"]), "has_key": bool(d["key"] and chargeproviders.key_of(d["id"])) or not d["key"],
             "attribution": d["attribution"], "countries": d["countries"], "key_url": (d["key"] or {}).get("url", ""), "source": d["source"], "license": d["license"]}
        )  # fmt: skip
    return sorted(
        out, key=lambda s: (bool(country) and country.upper() not in s["countries"] and s["id"] != "osm", s["id"] != "osm", s["name"])
    )


def preferred_charge_source() -> str:
    return (config.stored_setting("charge.source") or "").strip()


def default_charge_source(country: str = "") -> str:
    """The source used when none is chosen: the one the person prefers (when it can be used), else OpenStreetMap - it needs nothing."""
    wanted = preferred_charge_source()
    if wanted:
        for s in charge_sources(country):
            if s["id"] == wanted and s["has_key"]:
                return wanted
    return "osm"


def nearby_charge(
    lat: float, lon: float, radius: float, source: str, sort: str, min_kw: float = 0, plug: str = ""
) -> tuple[list[Station], str]:
    """``source``: ``osm`` | the id of a provider (chargeproviders.py). Returns (charging points, source_used)."""
    defn = chargeproviders.load().get(source)
    if defn is not None:
        found, used = fetch_charge_provider(defn, lat, lon, radius), source
    else:
        found, used = fetch_osm_charge(lat, lon, radius), "osm"
    return sort_charge(filter_charge(found, min_kw, plug), sort), used
