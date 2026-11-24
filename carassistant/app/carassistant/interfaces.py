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


def preview(m: dict, t) -> dict:
    """What a package says it will do, read from its description alone (nothing of it runs): shown BEFORE it is installed. Four groups of rows
    (``name``, ``path``, ``fields``, ``note``): ``sends`` (to the app), ``reads`` (from the app), ``offers`` (addresses, pages, actions its service
    answers) and ``brings`` (files, the token, settings it may change itself). ``t`` is the translator of the page."""
    rows: dict[str, list[dict]] = {"sends": [], "reads": [], "offers": [], "brings": []}

    def add(group: str, name: str, path: str = "", fields=None, note: str = "") -> None:
        rows[group].append({"name": name, "path": path, "fields": list(fields or []), "note": note})

    for item in m.get("interfaces", []):  # what the package says about itself
        add(item["direction"], item["name"], item.get("path", ""), item.get("fields"), item.get("note", ""))
    shown = [x["data"] for x in m.get("tiles", []) if x.get("data")]
    if shown:
        add("sends", t("pkg.row_tiles"), "", shown, t("pkg.note_tiles"))
    service = m.get("service") or {}
    for route in service.get("routes", []):
        if route.get("token_header"):
            note = t("svc.public_token", header=route["token_header"])
        else:
            note = t("svc.public") if route.get("public") else t("svc.local")
        add("offers", t("pkg.row_route"), route["prefix"], None, note)
    for page in m.get("pages", []):
        if page.get("kind") == "frame":
            add("offers", t("pkg.row_page", title=page["title"]), page["route"], None, t("pkg.note_frame"))
        else:
            add("offers", t("pkg.row_page", title=page["title"]), "", [f["key"] for f in page.get("fields", [])])
    nav = (m.get("capabilities") or {}).get("navigate")
    if nav:
        add("offers", t("pkg.row_navigate"), nav["path"], None, t("pkg.note_navigate"))
    for button in m.get("buttons", []):
        if button.get("action"):
            add("offers", t("pkg.row_action", label=button["label"]), button["action"], None, t("pkg.note_action"))
    for step in (m.get("setup") or {}).get("flow", []):
        if step["type"] == "check":
            add("offers", t("pkg.row_check", title=step.get("title") or step["id"]), step.get("action", ""), None, t("pkg.note_check"))
        elif step["type"] == "download":
            add("offers", t("pkg.row_make", title=step.get("title") or step["id"]), step.get("action", ""), None, t("pkg.note_make"))
    for d in m.get("downloads", []):
        add("brings", t("pkg.row_download", label=d["label"]), d["path"], None, d.get("note", ""))
    for f in m.get("files", []):
        add(
            "brings",
            t("pkg.row_file", label=f["label"]),
            f["name"],
            None,
            " · ".join(x for x in (f.get("version", ""), f.get("note", "")) if x),
        )
    for b in m.get("bundles", []):
        add(
            "brings",
            t("pkg.row_bundle", label=b["label"]),
            b["name"],
            None,
            " · ".join(
                x
                for x in (
                    b.get("version", ""),
                    b.get("note", ""),
                    t("pkg.note_bundle_cfg" if b.get("connection_file_to") else "pkg.note_bundle", n=len(b.get("entries", []))),
                )
                if x
            ),
        )
    if m.get("connection_file"):
        add("brings", t("pkg.row_connfile"), m["connection_file"]["name"], None, t("pkg.note_connfile"))
    writes = [f["key"] for f in m.get("settings", []) if f.get("service_writable") or f.get("type") == "value"]
    if writes:
        add("brings", t("pkg.row_writes"), "", writes)
    is_plugin = m.get("kind", "plugin") == "plugin"
    if is_plugin and addons.needs_token(m):
        add("brings", t("pkg.row_token"), "", None, t("pkg.note_token"))
    return {
        "rows": rows,
        "has_any": any(rows.values()),
        # the package says so itself: an empty list of interfaces = it sends nothing and reads nothing
        "declared_none": m.get("interfaces") == [] and not (rows["sends"] or rows["reads"] or rows["offers"]),
        "no_token": is_plugin and not addons.needs_token(m),
    }


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
