"""Home widgets: a fixed set of uniform tiles in one grid, arranged per vehicle.

Each widget is a template in `templates/widgets/<key>.html`; the template decides itself whether there is anything to show
(a widget without data renders nothing). A widget is "s" (one of two grid columns) or "m" (the full row). Widgets that
integrations and plugins bring along will be registered here later.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
from dataclasses import dataclass, replace

from . import db


@dataclass(frozen=True)
class Widget:
    key: str
    size: str  # "s" | "m"
    icon: str
    chip: str
    title: str  # translation key
    module: str | None = None  # the module that has to be enabled for the widget to show
    on: bool = True
    options: tuple[tuple[str, tuple[str, ...]], ...] = ()  # settings of the widget: (key, choices), the first choice is the default
    values: tuple[tuple[str, str], ...] = ()  # what the user chose (saved per car)
    label: str = ""  # a title that is not a translation key (a widget of an integration)
    template: str = ""  # the widget template when it is not widgets/<key>.html
    ref: str = ""  # what the template shows (a reminder of an integration)
    fixed: bool = False  # always the full row: it cannot be made small

    @property
    def opts(self) -> dict[str, str]:
        """Every option with its current value (the default when nothing was chosen)."""
        chosen = dict(self.values)
        return {key: chosen.get(key, choices[0]) for key, choices in self.options}

    @property
    def design(self) -> str:
        return self.opts.get("design", "")

    @property
    def options_json(self) -> str:
        """For the page: [{"key", "choices", "value"}] (the editor builds its settings window from it)."""
        return json.dumps([{"key": k, "choices": list(c), "value": self.opts[k]} for k, c in self.options])


REGISTRY: tuple[Widget, ...] = (
    Widget("messages", "m", "alert", "c6", "vm.title", options=(("columns", ("auto", "one", "two")),)),
    Widget("security", "s", "security", "c2", "tab.security", "security"),
    Widget("service", "s", "wrench", "c4", "nav.service", "service"),
    Widget("appointments", "s", "calendar", "c6", "tab.appointments", "appointments"),
    Widget(
        "odometer", "m", "counter", "c3", "f.odometer", on=False, options=(("design", ("tile", "drums", "plate")),)
    ),  # the plate under the car is the odometer; the widget is an extra look. The first look is the standard: the plain figure ("tile", shown as *Text*)
    Widget("trips", "s", "route", "c7", "tile.last_trip", "trips"),
    Widget("fuel", "s", "fuel", "c1", "nav.fuel", "fuel"),
    Widget("fuel_avg", "s", "chart", "c5", "tile.avg", "fuel"),
    Widget("attention", "m", "alert", "c6", "overview.attention", fixed=True, options=(("columns", ("auto", "one", "two")),)),
    Widget("car_data", "m", "gauge", "c5", "cd.title", fixed=True),
    Widget("location", "m", "map-marker-radius", "c7", "loc.title", fixed=True),
)
BY_KEY = {w.key: w for w in REGISTRY}


def dynamic(conn: sqlite3.Connection, vehicle_id: int) -> list[Widget]:
    """Widgets that running integrations bring along: one tile per reminder rule."""
    from . import reminders

    return [
        Widget(
            f"x-{r['addon_id']}-{r['id']}",
            "s",
            r["icon"],
            "c4",
            "",
            label=r["title"],
            template="x_reminder",
            ref=f"{r['addon_id']}-{r['id']}",
        )
        for r in reminders.running(conn, vehicle_id)
    ]


def tiles(conn: sqlite3.Connection, vehicle_id: int) -> list[Widget]:
    """The value tiles of running plugins and integrations (``tiles`` of their plugin.json): shown only while there is a value."""
    from . import addons, config

    lang = config.language()
    out = []
    for a in addons.list_for(conn, vehicle_id):
        if a["missing"] or not a["active"]:
            continue
        for t in a["m"].get("tiles", []):
            label = ((t.get("l10n") or {}).get(lang) or {}).get("label") or t["label"]
            out.append(
                Widget(
                    f"x-tile-{a['addon_id']}-{t['id']}",
                    "s",
                    t["icon"],
                    "c5",
                    "",
                    label=label,
                    template="x_tile",
                    ref=f"{a['addon_id']}-{t['id']}",
                )
            )
    return out


def tile_unit(tile: dict) -> str:
    """The unit of a value tile in the language of the app: the plugin's own translation (``l10n`` -> ``unit``) first, else a word the app knows
    (days, hours, minutes ... in every language the app has), else the unit as it was written."""
    from . import config, i18n

    lang = config.language()
    unit = tile.get("unit", "")
    own = ((tile.get("l10n") or {}).get(lang) or {}).get("unit")
    if own:
        return own
    key = f"unit.{unit.strip().lower()}"
    word = i18n.translator(lang)(key)
    return unit if word == key else word


def tile_values(conn: sqlite3.Connection, vehicle_id: int) -> dict[str, dict]:
    """The current value of every value tile of the car: ``{"<addon>-<id>": {"text", "updated"}}``."""
    from . import addons, connectors

    signals = {
        r["name"]: (r["value"], r["updated"])
        for r in conn.execute("SELECT name, value, updated FROM vehicle_signals WHERE vehicle_id = ?", (vehicle_id,))
    }
    live = {
        r["key"]: (r["value"], r["updated"])
        for r in conn.execute("SELECT key, value, updated FROM live WHERE vehicle_id = ?", (vehicle_id,))
    }
    out = {}
    for a in addons.list_for(conn, vehicle_id):
        for t in a["m"].get("tiles", []):
            found = signals.get(t["signal"]) if "signal" in t else live.get(connectors.NUMBERS[t["data"]][0])
            if not found or found[0] in (None, ""):
                continue
            text = found[0]
            if "decimals" in t:
                with contextlib.suppress(ValueError):  # not a number: shown as it is
                    text = f"{float(text):.{t['decimals']}f}"
            out[f"{a['addon_id']}-{t['id']}"] = {"text": text[:40], "unit": tile_unit(t), "updated": found[1]}
    return out


def registry(conn: sqlite3.Connection, vehicle_id: int) -> tuple[Widget, ...]:
    return (*REGISTRY, *dynamic(conn, vehicle_id), *tiles(conn, vehicle_id))


def _setting(vehicle_id: int) -> str:
    return f"home.widgets.{vehicle_id}"


def layout(conn: sqlite3.Connection, vehicle_id: int) -> list[Widget]:
    """All widgets of a vehicle's Home in display order, with the saved size and visibility; new registry widgets come last."""
    try:
        saved = json.loads(db.get_setting(conn, _setting(vehicle_id), "[]") or "[]")
    except ValueError:
        saved = []
    reg = registry(conn, vehicle_id)
    by_key = {w.key: w for w in reg}
    out: list[Widget] = []
    seen: set[str] = set()
    for item in saved if isinstance(saved, list) else []:
        if not isinstance(item, dict) or item.get("k") not in by_key or item["k"] in seen:
            continue
        base = by_key[item["k"]]
        seen.add(base.key)
        saved_opts = item.get("o") if isinstance(item.get("o"), dict) else {}
        if "d" in item:  # older saves kept the look as "d"
            saved_opts = {"design": item["d"], **saved_opts}
        values = tuple((k, saved_opts[k]) for k, choices in base.options if saved_opts.get(k) in choices)
        size = item.get("s") if item.get("s") in ("s", "m") and (not base.options or "o" in item or "d" in item) else base.size
        if base.fixed:
            size = "m"
        out.append(replace(base, size=size, on=bool(item.get("on", True)), values=values))
    reported = None
    for w in reg:
        if w.key in seen:
            continue
        if w.key == "odometer":  # a plugin reports the odometer: it is not on the dashboard any more, so the widget is how it is shown
            from . import summary

            reported = summary.odometer_from_car(conn, vehicle_id) if reported is None else reported
            w = replace(w, on=reported)
        out.append(w)
    return out


def _chosen(base: Widget, asked: dict[str, str], old: Widget) -> dict[str, str]:
    """Only values the widget offers; anything else keeps the old choice."""
    return {key: asked.get(key) if asked.get(key) in choices else old.opts[key] for key, choices in base.options}


def save(
    conn: sqlite3.Connection,
    vehicle_id: int,
    order: list[str],
    sizes: dict[str, str],
    shown: set[str],
    options: dict[str, dict[str, str]] | None = None,
) -> None:
    """Store the arrangement. `order` may contain only some widgets (the page shows only those with data): the others keep
    their saved size and visibility and their place among the remaining slots."""
    current = layout(conn, vehicle_id)
    by_key = {w.key: w for w in current}
    full = [w.key for w in current]
    submitted = [k for k in dict.fromkeys(order) if k in by_key]
    slots = [i for i, k in enumerate(full) if k in submitted]
    for i, k in zip(slots, submitted, strict=False):
        full[i] = k
    old = {w.key: w for w in current}
    items = []
    for k in full:
        if k in submitted:
            size = sizes.get(k) if sizes.get(k) in ("s", "m") else old[k].size
            size = "m" if by_key[k].fixed else size
            item = {"k": k, "s": size, "on": k in shown}
            if by_key[k].options:
                item["o"] = _chosen(by_key[k], (options or {}).get(k, {}), old[k])
            items.append(item)
        else:
            kept = {"k": k, "s": old[k].size, "on": old[k].on}
            if old[k].options:
                kept["o"] = old[k].opts
            items.append(kept)
    db.set_setting(conn, _setting(vehicle_id), json.dumps(items))


def reset(conn: sqlite3.Connection, vehicle_id: int) -> None:
    db.set_setting(conn, _setting(vehicle_id), None)
