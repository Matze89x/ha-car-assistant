"""The data of the zoomable connection map: EVERY channel of the Plugin API - also the ones nobody uses yet - and what flows through the others.

The older map drew plugins, one hub and the places where the information lands. This one adds the middle: the *channels* (each field a plugin may
send, each interface it may call). A channel nobody uses is **open** (drawn hollow: it could be connected); a channel a plugin uses shows who, in which
direction, how often and how long ago. The channels sit in groups, one group per place where they land (an area of the app or an integration).

Everything is built from the aggregated state that linkmap.py keeps (one query, never the signals themselves); the signals, their raw values and
their small history are only loaded when somebody opens a channel, a plugin or a group (``detail``).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime

from . import config, connectors, i18n, icons, linkmap, linkmap_ui, regional

# every data field a plugin may send (POST /data): English, German, unit
FIELDS: dict[str, tuple[str, str, str]] = {
    "odometer_km": ("Odometer", "Kilometerstand", "km"),
    "vin": ("Vehicle identification number", "Fahrzeug-Identnummer", ""),
    "position": ("Position", "Position", "lat, lon"),
    "ignition": ("Ignition", "Zündung", ""),
    "doors": ("Doors", "Türen", ""),
    "windows": ("Windows", "Fenster", ""),
    "lights": ("Lights", "Licht", ""),
    "locked": ("Locking", "Verriegelung", ""),
    "warnings": ("Warnings", "Warnmeldungen", ""),
    "tyre_pressure_bar": ("Tyre pressure", "Reifendruck", "bar"),
    "charging": ("Charging", "Lädt", ""),
    "plugged": ("Plugged in", "Angesteckt", ""),
    "climate_on": ("Climate on", "Klimatisierung an", ""),
    "parking_brake": ("Parking brake", "Handbremse", ""),
    "oil_warning": ("Oil warning", "Ölwarnung", ""),
    "fuel_level_pct": ("Fuel level", "Tankfüllung", "%"),
    "fuel_amount": ("Fuel amount", "Kraftstoffmenge", "L"),
    "range_km": ("Range", "Reichweite", "km"),
    "speed_kmh": ("Speed", "Geschwindigkeit", "km/h"),
    "speed_limit_kmh": ("Speed limit", "Tempolimit", "km/h"),
    "heading_deg": ("Heading", "Fahrtrichtung", "°"),
    "outside_temp_c": ("Outside temperature", "Außentemperatur", "°C"),
    "cabin_temp_c": ("Cabin temperature", "Innentemperatur", "°C"),
    "target_temp_c": ("Target temperature", "Solltemperatur", "°C"),
    "coolant_temp_c": ("Coolant temperature", "Kühlmitteltemperatur", "°C"),
    "oil_temp_c": ("Oil temperature", "Öltemperatur", "°C"),
    "battery_12v_v": ("12 V battery", "12-V-Batterie", "V"),
    "battery_pct": ("Battery", "Batterie", "%"),
    "charge_power_kw": ("Charging power", "Ladeleistung", "kW"),
    "charge_limit_pct": ("Charge limit", "Ladegrenze", "%"),
    "charge_minutes_left": ("Charging time left", "Restladezeit", "min"),
    "charge_state": ("Wallbox state", "Zustand der Wallbox", ""),
    "charge_session_kwh": ("Energy of this charge", "Energie dieser Ladung", "kWh"),
    "charge_session_minutes": ("Duration of this charge", "Dauer dieser Ladung", "min"),
    "charge_voltage_v": ("Charging voltage", "Ladespannung", "V"),
    "charge_current_a": ("Charging current", "Ladestrom", "A"),
    "charge_phases": ("Charging phases", "Ladephasen", ""),
    "charge_current_limit_a": ("Current limit", "Strombegrenzung", "A"),
    "charge_total_kwh": ("Wallbox counter", "Zähler der Wallbox", "kWh"),
    "charge_temp_c": ("Wallbox temperature", "Temperatur der Wallbox", "°C"),
    "charge_mode": ("Charging mode", "Lademodus", ""),
    "charge_fault": ("Wallbox fault", "Störung der Wallbox", ""),
    "consumption_l_100km": ("Consumption", "Verbrauch", "L/100 km"),
    "service_due_days": ("Service due in", "Service fällig in", "days"),
    "service_due_km": ("Service due in", "Service fällig in", "km"),
    "oil_change_due_days": ("Oil change due in", "Ölwechsel fällig in", "days"),
    "oil_change_due_km": ("Oil change due in", "Ölwechsel fällig in", "km"),
    "oil_level_pct": ("Oil level", "Ölstand", "%"),
    "adblue_level_pct": ("AdBlue level", "AdBlue-Stand", "%"),
    "adblue_range_km": ("AdBlue range", "AdBlue-Reichweite", "km"),
}

# the interfaces: key -> (area, directions, English label, German label, English explanation, German explanation)
INTERFACES: dict[str, tuple[str, tuple[str, ...], str, str, str, str]] = {
    "data": (
        "dashboard", ("get",), "Read the data", "Daten lesen",
        "GET /data: the plugin reads what the app knows about the car (the same values the dashboard shows).",
        "GET /data: Das Plugin liest, was die App über das Auto weiß (dieselben Werte wie im Dashboard).",
    ),
    "events": (
        "dashboard", ("set", "get"), "Events", "Ereignisse",
        "POST /events: messages of the car (an alarm, a charging end ...) that the app turns into notifications; GET /events reads what is there.",
        "POST /events: Meldungen des Autos (ein Alarm, Ladeende ...), die die App zu Benachrichtigungen macht; GET /events liest, was da ist.",
    ),
    "track": (
        "trips", ("set", "get"), "Track", "Fahrspur",
        "POST /track: positions with time while the car drives - the app makes a trip of them (distance, duration, speed, route); GET /track reads them back.",
        "POST /track: Positionen mit Zeit während der Fahrt - die App macht daraus eine Fahrt (Strecke, Dauer, Tempo, Route); GET /track liest sie zurück.",
    ),
    "trip-summary": (
        "trips", ("set",), "Trip summary", "Fahrt-Zusammenfassung",
        "POST /trip-summary: what the trip computer of the car says about a finished trip (consumption, average speed, duration); it is attached to the trip that ended then.",
        "POST /trip-summary: was der Bordcomputer über eine beendete Fahrt sagt (Verbrauch, Durchschnittstempo, Dauer); sie wird an die Fahrt gehängt, die damals endete.",
    ),
    "refuel": (
        "energy", ("set",), "Refuel", "Tankung",
        "POST /refuel: a fill-up the plugin saw (amount, price, place); it becomes an entry of the fuel log - without an amount an unfinished entry.",
        "POST /refuel: eine Tankung, die das Plugin gesehen hat (Menge, Preis, Ort); sie wird ein Eintrag im Tanklog - ohne Menge ein unfertiger Eintrag.",
    ),
    "signals": (
        "signals", ("get",), "Read free signals", "Freie Signale lesen",
        "GET /signals: the plugin reads the free values it stored before.",
        "GET /signals: Das Plugin liest die freien Werte, die es vorher abgelegt hat.",
    ),
    "signals.*": (
        "signals", ("set",), "Free signals", "Freie Signale",
        "POST /signals: values only this car has (any name): the app keeps them and shows them on the Debug page.",
        "POST /signals: Werte, die nur dieses Auto hat (beliebiger Name): Die App behält sie und zeigt sie auf der Debug-Seite.",
    ),
    "logs": (
        "logs", ("set",), "Log lines", "Log-Zeilen",
        "POST /logs: the log of the plugin, shown on its Info page (tab Log).",
        "POST /logs: das Protokoll des Plugins, gezeigt auf seiner Info-Seite (Reiter Log).",
    ),
    "plugin-settings": (
        "control", ("set", "get"), "Settings of the plugin", "Einstellungen des Plugins",
        "GET / PUT /plugin-settings: the plugin reads its settings and may change the ones marked as writable.",
        "GET / PUT /plugin-settings: Das Plugin liest seine Einstellungen und darf die als schreibbar markierten ändern.",
    ),
    "control": (
        "control", ("get",), "What the app asks", "Was die App verlangt",
        "GET /control: what the app asks of the plugin (the debug switch, how long to wait between reports).",
        "GET /control: Was die App vom Plugin verlangt (der Debug-Schalter, wie lange es zwischen Meldungen warten soll).",
    ),
    "vehicles": (
        "control", ("get",), "List of vehicles", "Liste der Fahrzeuge",
        "GET /vehicles: the cars this plugin may use.",
        "GET /vehicles: die Autos, die dieses Plugin nutzen darf.",
    ),
}  # fmt: skip

AREA_ORDER = [a[0] for a in linkmap.AREAS]


def _pick(pair: tuple[str, str]) -> str:
    return pair[1] if config.language() == "de" else pair[0]


def channel_of(area: str, name: str) -> str:
    """The channel a recorded signal belongs to (the key of the catalogue): a field, an interface, the free signals or a page of an integration."""
    if area.startswith("int:"):
        return f"{area}/{name}"
    if name.startswith("signals."):
        return "signals.*"
    return name


def _channel(key: str, area: str, kind: str, label: str, dirs: tuple[str, ...], explain: str, unit: str = "", bounds: str = "") -> dict:
    return {
        "key": key, "area": area, "kind": kind, "label": label, "dirs": list(dirs), "explain": explain, "unit": unit, "range": bounds,
        "users": [], "state": "open", "last": None, "hits": 0,
    }  # fmt: skip


def catalogue(conn: sqlite3.Connection, vehicle_id: int) -> list[dict]:
    """Every channel of the Plugin API for this car: the data fields, the interfaces and the pages of the installed integrations."""
    t = i18n.translator(config.language())
    out: list[dict] = []
    for key in sorted(connectors.KNOWN - {"measured_at"}, key=lambda k: (AREA_ORDER.index(linkmap.AREA_OF_KEY.get(k, "dashboard")), k)):
        area = linkmap.AREA_OF_KEY.get(key, "dashboard")
        label_pair = FIELDS.get(key) or (key, key, "")
        unit = label_pair[2]
        bounds = ""
        if key in connectors.NUMBERS:
            _live, lo, hi = connectors.NUMBERS[key]
            bounds = f"{lo} … {hi}"
        elif key in connectors.BOOLS:
            bounds = "yes / no"
        label = _pick(label_pair[:2])
        explain = t(
            "lmz.field",
            label=label,
            unit=(f" ({unit})" if unit else ""),
            area=t(f"lm.area_{area}"),
            range=(t("lmz.range", range=bounds) if bounds else ""),
        )
        out.append(_channel(key, area, "field", label, ("set",), explain, unit, bounds))
    for key, (area, dirs, en, de, ex_en, ex_de) in INTERFACES.items():
        out.append(_channel(key, area, "interface", _pick((en, de)), dirs, _pick((ex_en, ex_de))))
    for r in conn.execute("SELECT addon_id, manifest FROM vehicle_addons WHERE vehicle_id = ? AND kind = 'integration'", (vehicle_id,)):
        try:
            manifest = json.loads(r["manifest"])
        except ValueError:
            continue
        for page in manifest.get("pages") or []:
            if not isinstance(page, dict) or not page.get("id") or page.get("kind") == "frame":
                continue
            title = page.get("title")
            title = (
                (title.get(config.language()) or title.get("en") or next(iter(title.values()), ""))
                if isinstance(title, dict)
                else (title or page["id"])
            )
            out.append(
                _channel(f"int:{r['addon_id']}/{page['id']}", f"int:{r['addon_id']}", "page", str(title), ("set", "get"), t("lm.ex_int"))
            )
    return out


def model(conn: sqlite3.Connection, vehicle_id: int) -> dict:
    """The whole zoomable map of one car: ``plugins``, ``groups`` (the places, each with its channels) and ``edges`` (plugin - channel)."""
    t = i18n.translator(config.language())
    base = linkmap_ui.build(conn, vehicle_id)
    channels = catalogue(conn, vehicle_id)
    by_key = {c["key"]: c for c in channels}
    known = {p["id"] for p in base["plugins"]}
    edges: dict[tuple[str, str, str], dict] = {}
    for r in conn.execute(
        "SELECT addon_id, direction, name, area, SUM(hits) AS hits, MAX(last_ts) AS last_ts, COUNT(*) AS n FROM signal_state WHERE vehicle_id = ? "
        "GROUP BY addon_id, direction, name, area",
        (vehicle_id,),
    ):
        if r["addon_id"] not in known:
            continue
        key = channel_of(r["area"], r["name"])
        ch = by_key.get(key)
        if ch is None:  # a name the catalogue does not know (a newer API): drawn in the group of its area
            ch = by_key[key] = _channel(
                key,
                r["area"],
                "extra",
                r["name"],
                (r["direction"],),
                t(f"lm.ex_{r['area']}") if not r["area"].startswith("int:") else t("lm.ex_int"),
            )
            channels.append(ch)
        if r["direction"] not in ch["dirs"]:
            ch["dirs"].append(r["direction"])
        edge = edges.setdefault(
            (r["addon_id"], key, r["direction"]),
            {"plugin": r["addon_id"], "channel": key, "dir": r["direction"], "hits": 0, "last": None, "n": 0},
        )
        edge["hits"] += r["hits"] or 0
        edge["n"] += r["n"]
        if r["last_ts"] and (not edge["last"] or r["last_ts"] > edge["last"]):
            edge["last"] = r["last_ts"]
    names = {p["id"]: p["name"] for p in base["plugins"]}
    for edge in edges.values():
        edge["state"] = linkmap.activity(edge["last"])
        edge["ago"] = linkmap_ui.ago(edge["last"], t)
        ch = by_key[edge["channel"]]
        ch["users"].append(
            {
                "plugin": edge["plugin"],
                "name": names.get(edge["plugin"], edge["plugin"]),
                "dir": edge["dir"],
                "state": edge["state"],
                "ago": edge["ago"],
                "hits": edge["hits"],
            }
        )
        ch["hits"] += edge["hits"]
        if edge["last"] and (not ch["last"] or edge["last"] > ch["last"]):
            ch["last"] = edge["last"]
    for ch in channels:
        ch["state"] = linkmap.activity(ch["last"]) if ch["users"] else "open"
        ch["ago"] = linkmap_ui.ago(ch["last"], t) if ch["last"] else ""
        ch["users"].sort(key=lambda u: (u["name"].lower(), u["dir"]))
    groups = []
    areas = {a["key"]: a for a in base["areas"]}
    integration_names = {a["key"]: a["name"] for a in base["areas"] if a.get("integration")}
    keys = [k for k in AREA_ORDER if any(c["area"] == k for c in channels)]
    keys += sorted({c["area"] for c in channels if c["area"].startswith("int:")} | set(integration_names))
    meta = {k: (ic, chip) for k, ic, chip in linkmap.AREAS}
    for key in keys:
        mine = [c for c in channels if c["area"] == key]
        used = [c for c in mine if c["users"]]
        info = areas.get(key) or {}
        integration = key.startswith("int:")
        last = max((c["last"] for c in used if c["last"]), default=None)
        groups.append(
            {
                "area": key,
                "name": info.get("name") or integration_names.get(key) or t(f"lm.area_{key}"),
                "icon": info.get("icon") or meta.get(key, ("puzzle", "c4"))[0],
                "chip": info.get("chip") or meta.get(key, ("puzzle", "c4"))[1],
                "integration": integration,
                "explain": t("lm.ex_int") if integration else t(f"lm.ex_{key}"),
                "ha": bool(info.get("ha")) if info else linkmap_ui._ha_goes(key),
                "state": linkmap.activity(last) if used else "open",
                "n_open": len(mine) - len(used),
                "n_used": len(used),
                "channels": mine,
            }
        )
    body = {
        "plugins": base["plugins"],
        "groups": groups,
        "edges": sorted(edges.values(), key=lambda e: (e["plugin"], e["channel"], e["dir"])),
        "n_open": sum(g["n_open"] for g in groups),
        "n_used": sum(g["n_used"] for g in groups),
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    names_used = {p["icon"] for p in body["plugins"]} | {g["icon"] for g in groups} | {"swap"}
    body["icons"] = {n: icons.ICONS.get(n) or icons.ICONS["puzzle"] for n in names_used}  # the paths the map draws (24 x 24)
    body["version"] = hashlib.sha1(
        json.dumps(
            {
                "p": [(p["id"], p["active"]) for p in body["plugins"]],
                "c": [(c["key"], tuple(c["dirs"])) for g in groups for c in g["channels"]],
                "e": [(e["plugin"], e["channel"], e["dir"]) for e in body["edges"]],
            }
        ).encode(),
        usedforsecurity=False,
    ).hexdigest()[:12]
    return body


def light(body: dict) -> dict:
    """What the page refreshes every few seconds: states and times only (a changed ``version`` reloads the page)."""
    return {
        "version": body["version"],
        "plugins": [{"id": p["id"], "meta": p["meta"], "state": p["state"]} for p in body["plugins"]],
        "channels": [
            {"key": c["key"], "state": c["state"], "ago": c["ago"], "hits": c["hits"]} for g in body["groups"] for c in g["channels"]
        ],
        "edges": [{"plugin": e["plugin"], "channel": e["channel"], "dir": e["dir"], "state": e["state"]} for e in body["edges"]],
    }


def _matches(channel_key: str, area: str, name: str) -> bool:
    return channel_of(area, name) == channel_key


def detail(conn: sqlite3.Connection, vehicle_id: int, kind: str, ident: str, sub: str, raw_ok: bool) -> dict:
    """Everything about one selection - a channel, a plugin, a group (area / integration) or the line of one plugin and channel: the connections, the
    signals with their last value, the raw value (for those who may see it) and the small history with dates."""
    t = i18n.translator(config.language())
    body = model(conn, vehicle_id)
    names = {p["id"]: p["name"] for p in body["plugins"]}
    by_key = {c["key"]: c for g in body["groups"] for c in g["channels"]}
    group_of = {c["key"]: g for g in body["groups"] for c in g["channels"]}
    rows = [
        dict(r)
        for r in conn.execute(
            "SELECT addon_id, direction, name, area, hits, last_ts, last_value FROM signal_state WHERE vehicle_id = ? ORDER BY last_ts DESC, name",
            (vehicle_id,),
        )
        if r["addon_id"] in names
    ]

    def wanted(r: dict) -> bool:
        key = channel_of(r["area"], r["name"])
        if kind == "channel":
            return key == ident and (not sub or r["addon_id"] == sub)
        if kind == "plugin":
            return r["addon_id"] == ident and (not sub or key == sub)
        if kind == "group":
            return r["area"] == ident
        return False

    picked = [r for r in rows if wanted(r)]
    title, explain, extra = "", "", []
    if kind == "channel" and ident in by_key:
        ch = by_key[ident]
        title, explain = ch["label"], ch["explain"]
        g = group_of[ident]
        extra = [t("lmz.lands_in", area=g["name"])] + ([t("lm.ha_yes")] if g["ha"] else [])
        extra.append(t("lmz.dirs_" + "_".join(sorted(ch["dirs"]))))
        if not ch["users"]:
            extra.append(t("lmz.open_text"))
    elif kind == "plugin" and ident in names:
        plugin = next(p for p in body["plugins"] if p["id"] == ident)
        title, explain = plugin["name"], t("lmz.plugin_text", meta=plugin["meta"])
        if sub and sub in by_key:
            title = f"{plugin['name']} - {by_key[sub]['label']}"
            explain = by_key[sub]["explain"]
    elif kind == "group":
        g = next((g for g in body["groups"] if g["area"] == ident), None)
        if g:
            title, explain = g["name"], g["explain"]
            extra = [t("lmz.group_counts", used=g["n_used"], open=g["n_open"])] + ([t("lm.ha_yes")] if g["ha"] else [])
    connections = [
        {
            "plugin": e["plugin"], "plugin_name": names.get(e["plugin"], e["plugin"]), "channel": e["channel"], "channel_label": by_key[e["channel"]]["label"],
            "dir": e["dir"], "hits": e["hits"], "state": e["state"], "ago": e["ago"], "when": regional.fdatetime(e["last"]) if e["last"] else "",
        }
        for e in body["edges"]
        if (kind == "channel" and e["channel"] == ident) or (kind == "plugin" and e["plugin"] == ident) or (kind == "group" and by_key[e["channel"]]["area"] == ident)
    ]  # fmt: skip
    signals = []
    for r in picked[:60]:
        history = [
            {"ts": h["ts"], "when": regional.fdatetime(h["ts"]), "ago": linkmap_ui.ago(h["ts"], t), "value": h["value"] if raw_ok else None}
            for h in linkmap.history_of(conn, vehicle_id, r["addon_id"], r["direction"], r["name"])
        ]
        signals.append(
            {
                "plugin": r["addon_id"], "plugin_name": names.get(r["addon_id"], r["addon_id"]), "dir": r["direction"], "name": r["name"], "area": r["area"],
                "channel": channel_of(r["area"], r["name"]), "hits": r["hits"], "ts": r["last_ts"], "when": regional.fdatetime(r["last_ts"]) if r["last_ts"] else "",
                "ago": linkmap_ui.ago(r["last_ts"], t), "has_value": r["last_value"] is not None,
                "value": r["last_value"] if raw_ok else None, "history": history,
            }
        )  # fmt: skip
    return {
        "kind": kind, "id": ident, "title": title, "explain": explain, "extra": extra, "connections": connections, "signals": signals,
        "more": max(0, len(picked) - 60), "raw": raw_ok,
    }  # fmt: skip
