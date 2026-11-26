"""Pages of the main navigation: "More" (grouped menu), "Security" and the navigation settings."""

from __future__ import annotations

import sqlite3

from fastapi import Request
from fastapi.responses import RedirectResponse

from . import accounts, appicon, auth_web, config, db, events, i18n, icons, modules, navigation, slugs, sources, status, summary
from .connectors_web import _may_manage
from .web import app, form_dict, go, render, vehicle_or_404

# tint of the icon chip per entry
CHIP = {
    "edit": "c1",
    "docs": "c6",
    "manual": "c6",
    "tires": "c2",
    "counters": "c3",
    "fixed": "c4",
    "appointments": "c6",
    "service": "c4",
    "tasks": "c3",
    "parts": "c2",
    "mods": "c3",
    "trips": "c1",
    "fuel": "c6",
    "report": "c7",
    "security": "c2",
    "stations": "c1",
    "map": "c7",
    "integrations": "c4",
    "vehicles": "c2",
    "account": "c5",
    "settings": "c5",
    "about": "c7",
}
TABLE = {
    "service": "service",
    "tasks": "tasks",
    "tires": "tires",
    "mods": "mods",
    "parts": "parts",
    "docs": "documents",
    "counters": "counters",
    "fixed": "fixed_costs",
    "trips": "trips",
    "fuel": "fuel",
}


def _hint(conn: sqlite3.Connection, vid: int, key: str, t) -> str:
    if key == "appointments":
        row = conn.execute(
            "SELECT due_date FROM appointments WHERE vehicle_id = ? AND done = 0 ORDER BY due_date LIMIT 1", (vid,)
        ).fetchone()
        return row["due_date"][:7] if row else ""
    if key in TABLE:
        n = conn.execute(f"SELECT COUNT(*) AS n FROM {TABLE[key]} WHERE vehicle_id = ?", (vid,)).fetchone()["n"]
        return t("more.entries", n=n) if n else ""
    return ""


def section_pages(conn: sqlite3.Connection, vid: int | None, section: modules.Section) -> list[str]:
    """The pages of an umbrella page that are available for this vehicle, in their order."""
    off = modules.disabled(conn, vid)
    return [k for k in section.modules if k not in off]


def section_tabs(conn: sqlite3.Connection, vid: int | None, current: str | None, t) -> list[dict] | None:
    """No umbrella tab bars any more: every page of a car is reached from the bar or from More, one by one."""
    return None


def more_groups(conn: sqlite3.Connection, vid: int | None, t) -> list[dict]:
    off = modules.disabled(conn, vid)
    base = f"/v/{slugs.slug_of(conn, vid) or vid}" if vid else ""
    groups: list[dict] = []
    if vid:  # everything in this group belongs to the CURRENT vehicle only; the bar's pages are not repeated here
        # the order of the editor (Integrations -> Management) decides: the first four are the bar, the rest follows here in the same order
        rest = [key for key, _icon in navigation.order(conn, vid)[navigation.MAX_SLOTS :]]
        from . import pagemods

        mods = {
            navigation.X + m["addon_id"]: m for m in (pagemods.localize(m, config.language()) for m in pagemods.active_modules(conn, vid))
        }
        in_bar = {key for key, _ic in navigation.slots(conn, vid)}
        items = []
        # fixed pages AND the pages of running integrations in ONE list, in the order of the editor
        for key in [*rest, *(k for k in mods if k not in rest and k not in in_bar)]:
            if key in mods:
                mod = mods[key]
                items.append(
                    {
                        "href": f"{base}/m/{mod['addon_id']}",
                        "paths": [f"{base}/m/{mod['addon_id']}"],
                        "icon": mod["icon"],
                        "chip": CHIP["integrations"],
                        "title": mod["name"],
                        "hint": "",
                    }
                )
                continue
            if key not in modules.BY_KEY or (key != "edit" and key in off):
                continue
            items.append(
                {
                    "href": base + modules.BY_KEY[key].path,
                    "paths": [base + modules.BY_KEY[key].path],
                    "icon": icons.MODULE_ICON.get(key, icons.DEFAULT_ICON),
                    "chip": CHIP.get(key, "c1"),
                    "title": t(f"mod.{key}.name"),
                    "hint": _hint(conn, vid, key, t) if key in TABLE or key == "appointments" else "",
                }
            )
        for key, ic, title in (
            ("integrations", "puzzle", "addon.integrations"),
            ("plugins", "plug", "addon.plugins"),
        ):  # the extensions of THIS vehicle (and where to see what they do: logs, traffic)
            items.append(
                {
                    "href": f"{base}/{key}",
                    "paths": [f"{base}/{key}", f"{base}/{key}/add", f"{base}/{key}/sources"],
                    "icon": ic,
                    "chip": CHIP["integrations"],
                    "title": t(title),
                    "hint": "",
                }
            )
        row = conn.execute("SELECT name, plate FROM vehicles WHERE id = ?", (vid,)).fetchone()
        count = conn.execute("SELECT COUNT(*) FROM vehicles WHERE archived = 0").fetchone()[0]
        groups.append(
            {
                "title": t("more.g_current"),
                "items": items,
                "current": {
                    "name": row["name"],
                    "plate": row["plate"],
                    "can_switch": count > 1,
                    "href": base + modules.BY_KEY["edit"].path,  # the first entry of the car IS its passport: one fixed two-line card
                    "title": t("mod.edit.name"),
                    "icon": icons.MODULE_ICON.get("edit", icons.DEFAULT_ICON),
                    "chip": CHIP["edit"],
                    "icon_url": f"{base}/icon/128.png?v={appicon.revision(vid)}",
                    "icon_up": f"{base}/icon",
                    "icon_custom": appicon.has_custom(vid),
                    "back": f"{base}/more",
                    "sel": True,
                },
            }
        )
    groups.append(  # what belongs to the server (and the login): no connection to one vehicle
        {
            "title": t("more.g_general"),
            "items": [
                {
                    "href": "/settings/car",
                    "paths": ["/settings", *(f"/settings/{k}" for k in ("car", "user", "design", "region", "system")), "/account"],
                    "icon": "settings",
                    "chip": CHIP["settings"],
                    "title": t("nav.settings"),
                    "hint": "",
                },
                {"href": "/vehicles", "icon": "garage", "chip": CHIP["vehicles"], "title": t("nav.vehicles"), "hint": ""},
                {"href": "/about", "icon": "info", "chip": CHIP["about"], "title": t("about.title"), "hint": ""},
            ],
        }
    )
    return groups


def _current_vid(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT id FROM vehicles WHERE archived = 0 ORDER BY name COLLATE NOCASE LIMIT 1").fetchone()
    return row["id"] if row else None


@app.get("/more")
def more_global(request: Request):
    with db.tx() as conn:
        vid = _current_vid(conn)
        return _more(request, conn, vid)


@app.get("/v/{vid}/more")
def more_vehicle(request: Request, vid: int):
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        return _more(request, conn, vid)


def _more(request: Request, conn: sqlite3.Connection, vid: int | None):
    t = i18n.translator(config.language())
    return render(request, "more.html", groups=more_groups(conn, vid, t), nav_vid=vid, tab=None, v=None, nav="more")


@app.get("/v/{vid}/security")
def security_page(request: Request, vid: int):
    from .web import vehicle_ctx

    t = i18n.translator(config.language())
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        s = summary.vehicle_summary(conn, vehicle)
        live = status.rows(conn, vid)
        view = status.security_view(live, t)
        car_msgs = status.car_messages(live, t)
        open_total = len(s["attention"]) + len(status.open_closures(live)) + len(car_msgs)
        return render(
            request, "security.html", **vehicle_ctx(conn, vehicle, "security"), s=s, view=view, open_total=open_total, car_msgs=car_msgs
        )


# ------------------------------------------------------------------ account & login (its own page, not part of the settings)


@app.get("/account")
def account_page(request: Request):
    return RedirectResponse(f"{request.state.base}/settings/user", status_code=303)


@app.get("/about")
def about_page(request: Request):
    from . import about

    with db.tx() as conn:
        info = about.collect(conn)
    return render(request, "about.html", tab=None, v=None, about=info)


# ------------------------------------------------------------------ first start: language


def _first_vehicle(conn: sqlite3.Connection):
    return conn.execute("SELECT * FROM vehicles WHERE archived = 0 ORDER BY id LIMIT 1").fetchone()


@app.get("/setup/functions")
def setup_functions_page(request: Request):
    """Step 3 of the first-start guide: which fixed integrations does this first car need? Everything is on; switch off what is not needed."""
    with db.tx() as conn:
        vehicle = _first_vehicle(conn)
        if vehicle is None:
            return RedirectResponse(f"{request.state.base}/vehicles/new", status_code=303)
        off = modules.vehicle_off(conn, vehicle["id"])
        by_key = {m.key: m for m in modules.MODULES if m.scope == "vehicle" and not m.core}
        order = modules.RECOMMENDED + modules.ON_REQUEST  # the ones most people need first, the rest below (switched off for a new car)
        rows = [(by_key[k], k not in off) for k in order if k in by_key] + [
            (m, m.key not in off) for k, m in by_key.items() if k not in order
        ]
    return render(request, "setup_functions.html", rows=rows, chips=CHIP, vehicle=vehicle, tab=None, v=None)


@app.post("/setup/functions")
async def setup_functions_submit(request: Request):
    form = await request.form()
    keep = set(form.getlist("on"))
    with db.tx() as conn:
        vehicle = _first_vehicle(conn)
        if vehicle is None:
            return go(request, "/vehicles/new")
        for m in modules.MODULES:
            if m.scope == "vehicle" and not m.core:
                modules.set_vehicle_enabled(conn, vehicle["id"], m.key, m.key in keep)
        pending = auth_web.setup_pending(conn) and not accounts.has_users(conn)
    events.changed()
    return go(request, "/setup/access" if pending else "/")


@app.get("/setup/language")
def language_page(request: Request):
    from .web import _design_context

    chosen = request.query_params.get("lang", "")
    with db.tx() as conn:
        design = _design_context(conn)
    return render(request, "setup_language.html", tab=None, v=None, force_lang=chosen if chosen in i18n.CATALOGS else "en", **design)


@app.post("/setup/language")
async def language_choose(request: Request):
    form = await form_dict(request)
    lang = form.get("language", "")
    if lang not in i18n.CATALOGS:
        return go(request, "/setup/language", "err.choice")
    with db.tx() as conn:
        db.set_setting(conn, "language", lang)
        db.set_setting(conn, "setup.language", "1")
    return RedirectResponse(f"{request.state.base}/", status_code=303)


# ------------------------------------------------------------------ settings: factory reset


@app.post("/settings/reset")
async def factory_reset(request: Request):
    """Delete ALL data (vehicles, entries, accounts, tokens, settings) and uploaded files; the app starts like new."""
    if not _may_manage(request):
        return go(request, "/settings/system", "acct.need_admin")
    form = await form_dict(request)
    if form.get("confirm", "").strip() != "RESET":
        return go(request, "/settings/system", "err.reset_confirm")
    import shutil

    with db.tx() as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'").fetchall():
            conn.execute(f'DELETE FROM "{name}"')
        sources.seed_defaults(conn)  # like a fresh install: the standard source is always there first
        sources.seed_bundled(conn)  # ... with the packages that came with this version
    folder = config.files_dir()
    for child in folder.iterdir() if folder.is_dir() else []:
        shutil.rmtree(child, ignore_errors=True) if child.is_dir() else child.unlink(missing_ok=True)
    events.changed()
    return RedirectResponse(f"{request.state.base}/", status_code=303)


# ------------------------------------------------------------------ settings: navigation
