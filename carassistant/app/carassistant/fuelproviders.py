"""Fuel price providers described as data: the open interface for fuel prices of any country.

A provider is one JSON file (never code) that says where an open HTTP/JSON service is, how to ask it for the stations around a point and which
field of the answer is what. The app ships a few (``fuelproviders/*.json``); more can be added by putting a file into ``<data>/fuelproviders/``
(see docs/fuel-providers.md). Only ``https`` addresses are used, nothing from a file is executed, and nothing is requested unless a person looks
for stations.

``{"id": "fr", "name": "France", "countries": ["FR"], "license": "...", "attribution": "...", "url": "https://.../records",
"params": {"where": "within_distance(geom, geom'POINT({lon} {lat})', {radius_km}km)", "limit": "100"},
"items": "results", "fields": {"lat": "geom.lat", "lon": "geom.lon", "name": "{adresse}", "address": "{adresse}, {cp} {ville}"},
"prices": {"e5": "sp95_prix", "e10": "e10_prix", "diesel": "gazole_prix"}}``

``params`` and ``headers`` values may use ``{lat} {lon} {radius_km} {radius_m} {key} {fuel}``. For a service that is asked for one fuel at a time give
``"fuel_codes": {"e5": "SUP", "diesel": "DIE"}`` (the value of ``{fuel}``) and ``"price"`` (the field of the price in the answer). With ``"key": {"param": "apikey", "url": "https://..."}``
(or ``"header"``) the person needs a key of their own (System -> Fuel prices); without a key nothing is asked.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from urllib.parse import urlsplit

from . import config

log = logging.getLogger(__name__)

BUNDLED = Path(__file__).parent / "fuelproviders"
ID = re.compile(r"^[a-z][a-z0-9_-]{1,23}$")
FUEL_KEYS = ("e5", "e10", "diesel")
RESERVED = {"tankerkoenig", "osm"}
PLACEHOLDER = re.compile(r"\{([A-Za-z0-9_.]+)\}")
MAX_FILE = 20000


def user_dir() -> Path:
    return config.data_dir() / "fuelproviders"


def _text(value, limit: int) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def clean(raw) -> dict | None:
    """A definition checked and cut to what is used; None when it is not usable."""
    if not isinstance(raw, dict) or not isinstance(raw.get("id"), str) or not ID.match(raw["id"]) or raw["id"] in RESERVED:
        return None
    url = _text(raw.get("url"), 400)
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        return None
    fields = raw.get("fields") if isinstance(raw.get("fields"), dict) else {}
    prices = raw.get("prices") if isinstance(raw.get("prices"), dict) else {}
    if not _text(fields.get("lat"), 80) or not _text(fields.get("lon"), 80):
        return None
    key = raw.get("key") if isinstance(raw.get("key"), dict) else None
    if key is not None and not (_text(key.get("param"), 40) or _text(key.get("header"), 40)):
        return None
    countries = [
        c.upper()
        for c in (raw.get("countries") if isinstance(raw.get("countries"), list) else [])
        if isinstance(c, str) and re.fullmatch(r"[A-Za-z]{2}", c)
    ]
    return {
        "id": raw["id"],
        "name": _text(raw.get("name"), 80) or raw["id"],
        "countries": countries[:60],
        "license": _text(raw.get("license"), 80),
        "attribution": _text(raw.get("attribution"), 300),
        "url": url,
        "method": "POST" if str(raw.get("method", "")).upper() == "POST" else "GET",
        "params": {str(k)[:40]: _text(v, 300) for k, v in list((raw.get("params") or {}).items())[:12]}
        if isinstance(raw.get("params"), dict)
        else {},
        "headers": {str(k)[:40]: _text(v, 200) for k, v in list((raw.get("headers") or {}).items())[:6]}
        if isinstance(raw.get("headers"), dict)
        else {},
        "key": (
            {"param": _text(key.get("param"), 40), "header": _text(key.get("header"), 40), "url": _text(key.get("url"), 300)}
            if key is not None
            else None
        ),
        "items": _text(raw.get("items"), 80),
        "fields": {k: _text(fields.get(k), 200) for k in ("lat", "lon", "name", "brand", "address", "open") if fields.get(k)},
        "prices": {k: _text(prices[k], 80) for k in FUEL_KEYS if isinstance(prices.get(k), str) and prices[k]},
        "fuel_codes": {k: _text(raw["fuel_codes"].get(k), 20) for k in FUEL_KEYS if _text(raw["fuel_codes"].get(k), 20)}
        if isinstance(raw.get("fuel_codes"), dict)
        else {},
        "price": _text(raw.get("price"), 80),
        "max_radius_km": min(max(float(raw.get("max_radius_km") or 25), 1.0), 100.0)
        if isinstance(raw.get("max_radius_km", 25), int | float)
        else 25.0,
        "price_scale": float(raw["price_scale"]) if isinstance(raw.get("price_scale"), int | float) and raw["price_scale"] > 0 else 1.0,
        "source": "",
    }


def load() -> dict[str, dict]:
    """Every usable definition: the shipped ones, then the ones in the data folder (they win when an id is the same)."""
    found: dict[str, dict] = {}
    for where, label in ((BUNDLED, "bundled"), (user_dir(), "added")):
        if not where.is_dir():
            continue
        for path in sorted(where.glob("*.json")):
            try:
                if path.stat().st_size > MAX_FILE:
                    raise ValueError("too big")
                d = clean(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                d = None
            if d is None:
                log.warning("Fuel provider file %s is not usable and is ignored", path.name)
                continue
            d["source"] = label
            found[d["id"]] = d
    return found


def get_path(obj, path: str):
    """``a.b.c`` into nested dicts (and list positions); None when something is missing."""
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return None
        if cur is None:
            return None
    return cur


def fill(template: str, item: dict) -> str:
    """``{adresse}, {cp} {ville}`` with the values of one item; a part without a value is left out. A template without braces is a field name."""
    if "{" not in template:
        v = get_path(item, template)
        return str(v).strip() if v is not None and not isinstance(v, dict | list) else ""
    out = PLACEHOLDER.sub(
        lambda m: str(v) if (v := get_path(item, m.group(1))) is not None and not isinstance(v, dict | list) else "", template
    )
    return re.sub(r"\s+", " ", re.sub(r"(^[,\s]+|[,\s]+$)", "", re.sub(r"\s*,\s*(,\s*)+", ", ", out))).strip()


def number(value) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "."))
        except ValueError:
            return None
    return None


def request_parts(defn: dict, lat: float, lon: float, radius_km: float, key: str, fuel: str = "") -> tuple[dict, dict]:
    """(query parameters, headers) of the question: placeholders filled, the key put where the definition wants it."""
    known = {
        "lat": f"{lat:.5f}",
        "lon": f"{lon:.5f}",
        "radius_km": f"{radius_km:g}",
        "radius_m": str(int(radius_km * 1000)),
        "key": key,
        "fuel": defn["fuel_codes"].get(fuel, ""),
    }
    sub = lambda s: PLACEHOLDER.sub(lambda m: known.get(m.group(1), ""), s)  # noqa: E731
    params = {k: sub(v) for k, v in defn["params"].items()}
    headers = {k: sub(v) for k, v in defn["headers"].items()}
    if defn["key"]:
        if defn["key"]["param"]:
            params[defn["key"]["param"]] = key
        if defn["key"]["header"]:
            headers[defn["key"]["header"]] = key
    return params, headers


def parse(defn: dict, payload, fuel: str = "") -> list[dict]:
    """The stations of an answer, as plain dicts: name, brand, address, lat, lon, prices {fuel: number}, is_open."""
    items = get_path(payload, defn["items"]) if defn["items"] else payload
    out = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        lat, lon = number(get_path(it, defn["fields"]["lat"])), number(get_path(it, defn["fields"]["lon"]))
        if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        prices = {f: p * defn["price_scale"] for f, path in defn["prices"].items() if (p := number(get_path(it, path))) and p > 0}
        if (
            defn["price"] and fuel and (p := number(get_path(it, defn["price"]))) and p > 0
        ):  # one price per answer: the fuel that was asked for
            prices[fuel] = p * defn["price_scale"]
        opened = get_path(it, defn["fields"]["open"]) if defn["fields"].get("open") else None
        out.append(
            {
                "name": fill(defn["fields"].get("name", ""), it) if defn["fields"].get("name") else "",
                "brand": fill(defn["fields"].get("brand", ""), it) if defn["fields"].get("brand") else "",
                "address": fill(defn["fields"].get("address", ""), it) if defn["fields"].get("address") else "",
                "lat": lat,
                "lon": lon,
                "prices": prices,
                "is_open": opened if isinstance(opened, bool) else None,
            }
        )
    return out


def key_of(provider_id: str) -> str:
    return (config.stored_setting(f"int.fuelkey.{provider_id}") or "").strip()
