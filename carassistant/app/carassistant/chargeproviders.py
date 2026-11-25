"""Charging-point providers described as data: the open interface for charging points of any country.

The same idea as the fuel price providers (``fuelproviders.py``): a provider is ONE JSON file - never code - that says where an open HTTP/JSON
service is, how to ask it for the charging points around a point and which field of the answer is what. The app ships one (Open Charge Map,
``chargeproviders/ocm.json``, it needs a key of the person's own); more can be added by putting a file into ``<data>/chargeproviders/`` (see
docs/charge-providers.md). Only ``https`` addresses are used, nothing from a file is executed, and nothing is requested unless a person looks for
charging points. OpenStreetMap is built in (``stations.py``) and needs no key.

``{"id": "x", "name": "...", "countries": ["NO"], "license": "...", "attribution": "...", "url": "https://.../poi",
"params": {"lat": "{lat}", "lon": "{lon}", "km": "{radius_km}"}, "key": {"header": "X-API-Key", "url": "https://where-to-get-one"},
"items": "results", "fields": {"lat": "pos.lat", "lon": "pos.lon", "name": "{name}", "address": "{street}, {zip} {town}", "operator": "operator.title",
"points": "numberOfPoints", "fee": "usageCost", "hours": "openingHours", "provider": "{dataProvider.title}", "operational": "status.isOperational"},
"connections": {"path": "connections", "type": "type.title", "kw": "powerKW", "count": "quantity"}}``
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from urllib.parse import urlsplit

from . import config
from .fuelproviders import ID, PLACEHOLDER, fill, get_path, number

log = logging.getLogger(__name__)

BUNDLED = Path(__file__).parent / "chargeproviders"
RESERVED = {"osm"}
MAX_FILE = 20000
FIELD_KEYS = ("lat", "lon", "name", "address", "operator", "points", "fee", "hours", "access", "provider", "operational")
PLUG_TYPES = ("ccs", "type2", "chademo", "nacs", "type1", "schuko", "other")


def user_dir() -> Path:
    return config.data_dir() / "chargeproviders"


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
    if not _text(fields.get("lat"), 80) or not _text(fields.get("lon"), 80):
        return None
    key = raw.get("key") if isinstance(raw.get("key"), dict) else None
    if key is not None and not (_text(key.get("param"), 40) or _text(key.get("header"), 40)):
        return None
    conns = raw.get("connections") if isinstance(raw.get("connections"), dict) else {}
    countries = [
        c.upper()
        for c in (raw.get("countries") if isinstance(raw.get("countries"), list) else [])
        if isinstance(c, str) and re.fullmatch(r"[A-Za-z]{2}", c)
    ]
    max_radius = raw.get("max_radius_km", 25)
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
        "fields": {k: _text(fields.get(k), 200) for k in FIELD_KEYS if fields.get(k)},
        "connections": {k: _text(conns.get(k), 120) for k in ("path", "type", "kw", "count") if conns.get(k)} if conns.get("path") else {},
        "max_radius_km": min(max(float(max_radius), 1.0), 100.0)
        if isinstance(max_radius, int | float) and not isinstance(max_radius, bool)
        else 25.0,
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
                log.warning("Charging provider file %s is not usable and is ignored", path.name)
                continue
            d["source"] = label
            found[d["id"]] = d
    return found


def key_of(provider_id: str) -> str:
    return (config.stored_setting(f"int.chargekey.{provider_id}") or "").strip()


def request_parts(defn: dict, lat: float, lon: float, radius_km: float, key: str) -> tuple[dict, dict]:
    """(query parameters, headers) of the question: placeholders filled, the key put where the definition wants it."""
    known = {"lat": f"{lat:.5f}", "lon": f"{lon:.5f}", "radius_km": f"{radius_km:g}", "radius_m": str(int(radius_km * 1000)), "key": key}
    sub = lambda s: PLACEHOLDER.sub(lambda m: known.get(m.group(1), ""), s)  # noqa: E731
    params = {k: sub(v) for k, v in defn["params"].items()}
    headers = {k: sub(v) for k, v in defn["headers"].items()}
    if defn["key"]:
        if defn["key"]["param"]:
            params[defn["key"]["param"]] = key
        if defn["key"]["header"]:
            headers[defn["key"]["header"]] = key
    return params, headers


def plug_type(label: str) -> str:
    """The kind of plug from the words a service uses for it (``CCS (Type 2)``, ``Type 2 (Socket Only)``, ``CHAdeMO`` ...): one of PLUG_TYPES."""
    t = (label or "").lower()
    if "ccs" in t or "combo" in t:
        return "ccs"
    if "chademo" in t:
        return "chademo"
    if "nacs" in t or "tesla" in t or "supercharger" in t:
        return "nacs"
    if "type 2" in t or "type2" in t or "mennekes" in t or "iec 62196-2" in t:
        return "type2"
    if "type 1" in t or "type1" in t or "j1772" in t:
        return "type1"
    if "schuko" in t or "cee 7" in t or "europlug" in t or "household" in t:
        return "schuko"
    return "other"


def sum_plugs(plugs: list[dict]) -> list[dict]:
    """One entry per kind of plug: how many points, the strongest power, a label. Sorted by power (strongest first), then by name."""
    by: dict[str, dict] = {}
    for p in plugs:
        e = by.setdefault(p["type"], {"type": p["type"], "label": p.get("label") or "", "n": 0, "kw": None})
        e["n"] += max(int(p.get("n") or 1), 1)
        if p.get("kw") and (e["kw"] is None or p["kw"] > e["kw"]):
            e["kw"] = p["kw"]
        if not e["label"] and p.get("label"):
            e["label"] = p["label"]
    return sorted(by.values(), key=lambda e: (-(e["kw"] or 0), e["type"]))


def parse(defn: dict, payload) -> list[dict]:
    """The charging points of an answer, as plain dicts (see ``stations.Station``): name, address, lat, lon, operator, points, plugs, fee, hours,
    access, provider, operational."""
    items = get_path(payload, defn["items"]) if defn["items"] else payload
    f = defn["fields"]
    out = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        lat, lon = number(get_path(it, f["lat"])), number(get_path(it, f["lon"]))
        if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        plugs = []
        spec = defn["connections"]
        raw = get_path(it, spec["path"]) if spec else None
        for c in raw if isinstance(raw, list) else []:
            if not isinstance(c, dict):
                continue
            label = fill(spec.get("type", ""), c) if spec.get("type") else ""
            kw = number(get_path(c, spec["kw"])) if spec.get("kw") else None
            n = number(get_path(c, spec["count"])) if spec.get("count") else None
            plugs.append({"type": plug_type(label), "label": label, "kw": kw if kw and kw > 0 else None, "n": int(n) if n and n > 0 else 1})
        points = number(get_path(it, f["points"])) if f.get("points") else None
        operational = get_path(it, f["operational"]) if f.get("operational") else None
        out.append(
            {
                "name": fill(f.get("name", ""), it) if f.get("name") else "",
                "address": fill(f.get("address", ""), it) if f.get("address") else "",
                "operator": fill(f.get("operator", ""), it) if f.get("operator") else "",
                "lat": lat,
                "lon": lon,
                "points": int(points) if points and points > 0 else None,
                "plugs": sum_plugs(plugs),
                "fee": fill(f.get("fee", ""), it)[:200] if f.get("fee") else "",
                "hours": fill(f.get("hours", ""), it)[:120] if f.get("hours") else "",
                "access": fill(f.get("access", ""), it)[:60] if f.get("access") else "",
                "provider": fill(f.get("provider", ""), it)[:120] if f.get("provider") else "",
                "operational": operational if isinstance(operational, bool) else None,
            }
        )
    return out
