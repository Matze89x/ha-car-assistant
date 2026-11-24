"""The page *Interfaces* of a plugin or integration: every interface it offers or uses, in one place - what it says about itself (``interfaces`` and
``docs`` of its plugin.json) next to what it really did (``plugin_usage``: addresses and field names, never values). So anyone can see where
an interface is reached and which other package could use it."""

from __future__ import annotations

import re
import sqlite3

from . import addons, assets, pluginsvc, regional


def _norm(path: str, vehicle_id: int) -> str:
    """An address without the car's number, so a declared and a seen address compare equal."""
    path = path.replace("<id>", "{id}").replace("{vehicle}", "{id}")
    return re.sub(rf"/vehicles/{vehicle_id}(?=/|$)", "/vehicles/{id}", path)


def view(conn: sqlite3.Connection, vehicle_id: int, addon: dict, base_url: str) -> dict:
    """Everything for the page, as plain data: ``sends`` / ``reads`` / ``offers`` (each a list of rows), the ``settings`` and the ``docs`` text."""
    m = addon["m"]
    seen = [dict(r) for r in conn.execute(
        "SELECT method, endpoint, fields, hits, last_seen FROM plugin_usage WHERE vehicle_id = ? AND addon_id = ? ORDER BY endpoint, method",
        (vehicle_id, addon["addon_id"]),
    )]  # fmt: skip
    used = {(r["method"], _norm(r["endpoint"], vehicle_id)): r for r in seen}

    def find(direction: str, key: str):
        """The seen call for a declared interface: a plugin sends with POST and reads with GET; an offered address is called with any method."""
        methods = {"sends": ("POST", "PUT"), "reads": ("GET",)}.get(direction)
        hits = [r for (method, endpoint), r in used.items() if endpoint == key and (methods is None or method in methods)]
        return max(hits, key=lambda r: r["last_seen"]) if hits else None

    rows: dict[str, list[dict]] = {"sends": [], "reads": [], "offers": []}
    matched: set[str] = set()
    for item in m.get("interfaces", []):
        key = _norm(item["path"], vehicle_id) if item["path"] else ""
        hit = used.get(key)
        if hit:
            matched.add(key)
        rows[item["direction"]].append(
            {**item, "declared": True, "seen": regional.fdatetime(hit["last_seen"]) if hit else "", "hits": hit["hits"] if hit else 0}
        )
    service = m.get("service") or {}
    for route in service.get("routes", []):
        hit = find("offers", route["prefix"])
        if hit:
            matched.add((hit["method"], route["prefix"]))
        rows["offers"].append(
            {
                "direction": "offers",
                "name": "Service route",
                "path": (base_url.rstrip("/") if base_url else "https://<address>") + route["prefix"],
                "note": (
                    f"public, but only with the plugin's token in the header {route['token_header']}"
                    if route.get("token_header")
                    else "public: reachable without a login (for example by the car)"
                )
                if route["public"]
                else "only from Home Assistant",
                "declared": True,
                "auto": True,
                "seen": regional.fdatetime(hit["last_seen"]) if hit else "",
                "hits": hit["hits"] if hit else 0,
            }
        )
    for page in m.get("pages", []):
        rows["offers"].append(
            {
                "direction": "offers",
                "name": f"Page: {page['title']}",
                "path": f"/api/v1/vehicles/{{id}}/modules/{addon['addon_id']}/{page['id']}",
                "note": "read the entries (GET) or add / change / delete them (POST), see docs/api.md",
                "fields": [f["key"] for f in page["fields"]],
                "declared": True,
                "auto": True,
            }
        )
    for r in seen:
        key = _norm(r["endpoint"], vehicle_id)
        if (r["method"], key) in matched:
            continue
        direction = "offers" if not key.startswith("/api/") else ("reads" if r["method"] == "GET" else "sends")
        rows[direction].append(
            {
                "direction": direction,
                "name": r["method"] + " " + key,
                "path": key,
                "fields": [x for x in r["fields"].split(", ") if x],
                "note": "",
                "declared": False,
                "seen": regional.fdatetime(r["last_seen"]),
                "hits": r["hits"],
            }
        )
    for d in m.get("downloads", []):
        rows["offers"].append(
            {
                "direction": "offers",
                "name": "Download: " + d["label"],
                "path": d["path"],
                "note": d["note"],
                "declared": True,
                "auto": True,
                "download": True,
            }
        )
    if m.get("connection_file"):
        rows["offers"].append(
            {
                "direction": "offers",
                "name": "Connection file",
                "path": m["connection_file"]["name"],
                "note": "downloaded from the settings page; holds the address, the token and the settings",
                "declared": True,
                "auto": True,
            }
        )
    offered = pluginsvc.approved(addon)
    return {
        "rows": rows,
        "docs": m.get("docs", ""),
        "docs_parts": assets.docs_parts(addon, offered),
        "files": assets.listing(addon, offered),
        "files_offered": offered,
        "settings": [f for f in m.get("settings", []) if f["type"] not in addons.NO_VALUE],
        "service": bool(service),
        "downloads": m.get("downloads", []),
        "has_any": any(rows.values()),
    }
