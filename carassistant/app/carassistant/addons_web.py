"""Routes: integrations and plugins of one vehicle (upload, set up, settings, remove)."""

from __future__ import annotations

import contextlib
import time

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from . import (
    addons,
    assets,
    auth_web,
    changelog,
    config,
    connectors,
    db,
    events,
    ha,
    habridge,
    i18n,
    interfaces,
    linkmap_ui,
    linkmap_zoom,
    modules,
    navigation,
    pkginstall,
    pluginsvc,
    regional,
    restoresetup,
    sources,
)
from . import icons as icon_set
from . import nav_web as nav_chips
from .connectors_web import _may_manage
from .web import app, form_dict, go, render, templates, vehicle_ctx, vehicle_or_404

MAX_UPLOAD = addons.MAX_PACKAGE + 1


def _tabs(base: str, current: str, keys: tuple[tuple[str, str, str], ...]) -> list[dict]:
    t = i18n.translator(config.language())
    # the Sources tab is the same page for every vehicle: one server-wide list (path None -> /sources); ``fold``: on a phone only the open tab
    # names itself, the others are their symbol (the bars of the Plugins and Integrations pages are too long for a phone otherwise)
    return [
        {
            "key": k,
            "href": "/sources" if path is None else f"{base}{path}",
            "title": t(title),
            "on": k == current,
            "icon": TAB_ICON.get(k),
            "fold": True,
        }
        for k, path, title in keys
    ]


TAB_ICON = {
    "navigation": "cog",
    "manage": "cog",
    "links": "sitemap",
    "add": "plus",
    "sources": "database",
}  # the symbol in front of each tab
INT_TABS = (("navigation", "", "int.tab_nav"), ("add", "/add", "int.tab_add"), ("sources", "/sources", "int.tab_sources"))
PLUG_TABS = (
    ("manage", "", "plug.tab_manage"),
    ("links", "/connections", "plug.tab_links"),
    ("add", "/add", "int.tab_add"),
    ("sources", "/sources", "int.tab_sources"),
)


def _functions(conn, vid: int):
    """The fixed integrations in the same order as the navigation editor (what is switched off follows at the end)."""
    rank = {key: i for i, (key, _icon) in enumerate(navigation.order(conn, vid))}
    mods = [m for m in modules.MODULES if m.scope == "vehicle" and not m.core and m.key not in ("counters", "stations")]
    mods.sort(key=lambda m: rank.get(m.key, len(rank)))
    return [(m, m.key not in modules.vehicle_off(conn, vid), m.key in modules.disabled(conn)) for m in mods]


def _source_ctx(conn, kind: str, vid: int) -> dict:
    rows = sources.listing(conn, kind)
    return {"rows": rows, "kind": kind, "vid": vid, "has_default": any(r["is_default"] for r in rows)}


def _sort_installed(items: list[dict], key: str) -> list[dict]:
    """The installed packages: by name (default), the newest installed first, or those that need something (update, set-up) first."""
    if key == "recent":
        return sorted(items, key=lambda a: a["created_at"] or "", reverse=True)
    if key == "status":
        return sorted(items, key=lambda a: (not a["missing"], not a["has_update"], (a["m"].get("name") or "").lower()))
    return sorted(items, key=lambda a: (a["m"].get("name") or "").lower())


def _sort_available(rows, key: str) -> list:
    """The packages of the sources: by name (default), by source, or the ones not yet installed first."""
    if key == "source":
        return sorted(rows, key=lambda p: ((p["source_name"] or "").lower(), (p["name"] or "").lower()))
    if key == "new":
        return sorted(rows, key=lambda p: (bool(p["installed"]), (p["name"] or "").lower()))
    return sorted(rows, key=lambda p: (p["name"] or "").lower())


def _sort_ctx(request: Request, tab_manage: bool) -> dict:
    asked = request.query_params.get("sort", "")
    choices = ("name", "recent", "status") if tab_manage else ("name", "source", "new")
    return {"sort": asked if asked in choices else "name", "sort_choices": choices}


def _integrations_page(request: Request, vid: int, tab: str):
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        sortc = _sort_ctx(request, tab == "navigation")
        items = _sort_installed(_with_service([a for a in addons.list_for(conn, vid) if a["kind"] == "integration"]), sortc["sort"])
        return render(
            request,
            "vehicle_integrations.html",
            **sortc,
            **vehicle_ctx(conn, vehicle, "integrations"),
            hide_hero=True,
            itab=tab,
            section_tabs=_tabs(f"/v/{vehicle['slug']}/integrations", tab, INT_TABS),
            items=items,
            chips=nav_chips.CHIP,
            nav_order=navigation.order(conn, vid),
            nav_extra=navigation.integration_pages(conn, vid),
            nav_aid={navigation.X + a["addon_id"]: a["id"] for a in items},  # the switch of an integration page in the order
            picker_icons=icon_set.PICKER_ICONS,
            functions=_functions(conn, vid),
            available=_sort_available(sources.available(conn, "integration", vid), sortc["sort"]),
            last_read=conn.execute("SELECT MAX(checked_at) FROM sources").fetchone()[0],
            **_source_ctx(conn, "integration", vehicle["id"]),
            have_packages=bool(conn.execute("SELECT 1 FROM source_packages LIMIT 1").fetchone()),
        )


def _hold_service_buttons(a: dict) -> None:
    """A service that nobody approved does not run: what needs it (a button that calls it, a page it serves, its own downloads) is not offered yet -
    the way to the approval (the card's main button) stays. Buttons that open a step of the set-up or a page of the app itself stay."""
    frames = {p["id"] for p in a["m"].get("pages", []) if p.get("kind") == "frame"}
    a["m"] = {
        **a["m"],
        "buttons": [{**b, "shown": False} if (b.get("action") or b.get("page") in frames) else b for b in a["m"].get("buttons", [])],
        "downloads": [{**d, "shown": False} for d in a["m"].get("downloads", [])],
    }


def _with_service(items: list[dict]) -> list[dict]:
    """Plugins with a service get ``svc``: what the card shows (state, approval, routes)."""
    for a in items:
        service = pluginsvc.service_of(a)
        a["svc"] = (
            {
                "state": pluginsvc.state(a["id"], a),
                "approved": pluginsvc.approved(a),
                "routes": service["routes"],
                "started": regional.fdatetime(a.get("svc_started")),
                "error": a.get("svc_error") or "",
            }
            if service
            else None
        )
        if service and not a["svc"]["approved"]:
            _hold_service_buttons(a)
        has_files = bool(
            a["m"].get("files") or a["m"].get("bundles")
        )  # downloads the package brings: shown for approval, handed out once approved
        a["pkgfiles"] = (
            {"approved": pluginsvc.approved(a), "n": len(a["m"].get("files", [])) + len(a["m"].get("bundles", []))} if has_files else None
        )
    return items


def _plugins_page(request: Request, vid: int, tab: str):
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        if tab == "links":  # the connection map: its own, light data (no package lists, no sources)
            return render(
                request,
                "vehicle_plugins.html",
                **vehicle_ctx(conn, vehicle, "plugins"),
                hide_hero=True,
                ptab=tab,
                section_tabs=_tabs(f"/v/{vehicle['slug']}/plugins", tab, PLUG_TABS),
                lm=linkmap_ui.build(conn, vid),
                lmz=linkmap_zoom.model(conn, vid),
                can_raw=_may_manage(request),
            )
        sortc = _sort_ctx(request, tab == "manage")
        items = _sort_installed(_with_service([a for a in addons.list_for(conn, vid) if a["kind"] == "plugin"]), sortc["sort"])
        return render(
            request,
            "vehicle_plugins.html",
            **sortc,
            **vehicle_ctx(conn, vehicle, "plugins"),
            hide_hero=True,
            ptab=tab,
            section_tabs=_tabs(f"/v/{vehicle['slug']}/plugins", tab, PLUG_TABS),
            items=items,
            chips=nav_chips.CHIP,
            available=_sort_available(sources.available(conn, "plugin", vid), sortc["sort"]),
            last_read=conn.execute("SELECT MAX(checked_at) FROM sources").fetchone()[0],
            **_source_ctx(conn, "plugin", vehicle["id"]),
            have_packages=bool(conn.execute("SELECT 1 FROM source_packages LIMIT 1").fetchone()),
        )


@app.get("/v/{vid}/integrations")
def integrations_navigation(request: Request, vid: int):
    return _integrations_page(request, vid, "navigation")


@app.get("/v/{vid}/integrations/add")
def integrations_add(request: Request, vid: int):
    return _integrations_page(request, vid, "add")


@app.get("/v/{vid}/integrations/sources")
def integrations_sources(request: Request, vid: int):
    return _integrations_page(request, vid, "sources")


@app.get("/v/{vid}/plugins")
def plugins_manage(request: Request, vid: int):
    return _plugins_page(request, vid, "manage")


@app.get("/v/{vid}/plugins/connections")
def plugins_connections(request: Request, vid: int):
    return _plugins_page(request, vid, "links")


@app.get("/v/{vid}/plugins/add")
def plugins_add(request: Request, vid: int):
    return _plugins_page(request, vid, "add")


@app.get("/v/{vid}/plugins/sources")
def plugins_sources(request: Request, vid: int):
    return _plugins_page(request, vid, "sources")


def _manage(kind: str, vid: int) -> str:
    """The Manage page of a kind: installed packages live there."""
    return f"/v/{vid}/plugins" if kind == "plugin" else f"/v/{vid}/integrations"


def _where(kind: str, vid: int) -> str:
    """Where a change of an integration / a plugin is shown afterwards."""
    return _manage(kind, vid)


@app.post("/v/{vid}/integrations/{addon_pk}/bar")
async def addon_bar(request: Request, vid: int, addon_pk: int):
    """An integration's page into the navigation bar of this car, or back to More."""
    form = await form_dict(request)
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        addon = addons.get(conn, vid, addon_pk)
        if addon and addon["active"]:
            navigation.put_in_bar(conn, vid, navigation.X + addon["addon_id"], form.get("way") == "in")
    events.changed()
    return go(request, f"/v/{vid}/integrations", "saved")


@app.post("/v/{vid}/navigation")
async def vehicle_navigation(request: Request, vid: int):
    """The bar of ONE vehicle: which pages sit in it (the first four), in which order, with which icon."""
    raw = await request.form()
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        if raw.get("reset"):
            navigation.reset(conn, vid)
        else:
            pairs = list(zip(raw.getlist("m"), raw.getlist("i"), strict=False))
            navigation.save_order(conn, [(str(k), str(i)) for k, i in pairs], vid)
    events.changed()
    if raw.get("ajax"):
        return Response(status_code=204)  # live save from the editor: the page stays where it is
    return go(request, f"/v/{vid}/integrations", "saved")


def _guard(request: Request, vid: int):
    return None if _may_manage(request) else go(request, f"/v/{vid}/integrations", "acct.need_admin")


@app.post("/v/{vid}/integrations/upload")
async def addons_upload(request: Request, vid: int):
    if (denied := _guard(request, vid)) is not None:
        return denied
    form = await request.form()
    upload = form.get("package")
    if upload is None or not getattr(upload, "filename", ""):
        return go(request, f"/v/{vid}/integrations", "addon.err_manifest")
    raw = await upload.read(MAX_UPLOAD)
    try:
        manifest = addons.parse_package(raw)
        with db.tx() as conn:
            vehicle_or_404(conn, vid)
            addons.add(conn, vid, manifest)
    except addons.AddonError as exc:
        return go(request, f"/v/{vid}/integrations/add", exc.key)
    events.changed()
    return go(request, _where(manifest["kind"], vid), "addon.uploaded")


@app.get("/v/{vid}/packages/{source_id}/{kind}/{pkg_id}")
def package_page(request: Request, vid: int, source_id: int, kind: str, pkg_id: str):
    """One package of a source: what the index says, plus the manifest read from the source right now (author, settings)."""
    if kind not in sources.KINDS:
        return go(request, f"/v/{vid}/integrations/add", "addon.err_id")
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        entry = sources.package(conn, source_id, kind, pkg_id)
        if entry is None:
            return go(request, f"/v/{vehicle['slug']}/{kind}s/add", "addon.err_id")
        installed = any(a["addon_id"] == pkg_id for a in addons.list_for(conn, vid))
        manifest, problem = None, None
        try:
            manifest = sources.fetch_manifest(conn, source_id, kind, pkg_id)
        except sources.SourceError as exc:
            problem = str(exc)
        needs_review = bool(manifest) and addons.needs_package(
            manifest
        )  # a service, files or a page of its own: read what it does, then one click
        return render(
            request,
            "package.html",
            **vehicle_ctx(conn, vehicle, f"{kind}s"),
            hide_hero=True,
            entry=entry,
            manifest=manifest,
            problem=problem,
            installed=installed,
            kind=kind,
            needs_review=needs_review,
            does=interfaces.preview({**manifest, "kind": kind}, i18n.translator(config.language())) if manifest else None,
            service=(manifest or {}).get("service"),
            may=_may_manage(request),
        )


def _fetch_service_package(manifest: dict, source_id: int, kind: str, pkg_id: str) -> str | None:
    """A package with a service, files or bundles: fetch its zip from the source, check it and unpack it (nothing runs). Returns the sha256 (pkginstall.py)."""
    return pkginstall.fetch_files(manifest, source_id, kind, pkg_id)


@app.post("/v/{vid}/packages/{source_id}/{kind}/{pkg_id}/install")
def package_install(request: Request, vid: int, source_id: int, kind: str, pkg_id: str):
    if (denied := _guard(request, vid)) is not None:
        return denied
    back = f"/v/{vid}/{kind}s/add"
    try:
        with db.tx() as conn:
            vehicle_or_404(conn, vid)
            manifest = sources.fetch_manifest(conn, source_id, kind, pkg_id)
        sha = _fetch_service_package(manifest, source_id, kind, pkg_id)
        with db.tx() as conn:
            waiting = conn.execute(
                "SELECT 1 FROM vehicle_addons WHERE vehicle_id = ? AND addon_id = ? AND status = 'missing'", (vid, pkg_id)
            ).fetchone()
            aid = addons.add(conn, vid, manifest, source_id, sha)
    except sources.SourceError as exc:
        return go(request, back, str(exc))
    except addons.AddonError as exc:
        return go(request, back, exc.key)
    if request.query_params.get("approve") == "1" and addons.needs_package(manifest):
        # the review page was the approval: one click reads, trusts and installs (an administrator only - _guard above)
        with db.tx() as conn:
            addon = addons.get(conn, vid, aid)
            key = pluginsvc.approve(conn, addon)
        events.changed()
        if key:  # for example a route that is already taken: the installed package waits for a look on its own review page
            return go(request, f"/v/{vid}/integrations/{aid}/service", key)
        if pluginsvc.service_of(addon):
            pluginsvc.install_async(aid)
        return go(request, _manage(kind, vid), "svc.approved" if pluginsvc.service_of(addon) else "fil.approved")
    events.changed()
    return go(request, _manage(kind, vid), "addon.installed_off" if waiting else "addon.installed")


@app.post("/v/{vid}/integrations/{aid}/update")
def addons_update(request: Request, vid: int, aid: int):
    if (denied := _guard(request, vid)) is not None:
        return denied
    with db.tx() as conn:
        addon = addons.get(conn, vid, aid)
        if addon is None:
            return go(request, f"/v/{vid}/integrations", "addon.err_id")
        source_id = addon["source_id"]
        if source_id is None:  # installed without a source: a source that offers a NEWER version takes it over
            offer = addons.unlinked_offer(conn, addon)
            if offer is None or not sources.is_newer(offer["version"], addon["m"].get("version", "")):
                return go(request, f"/v/{vid}/integrations", "addon.err_id")
            source_id = offer["source_id"]
    try:
        with db.tx() as conn:
            manifest = sources.fetch_manifest(conn, source_id, addon["kind"], addon["addon_id"])
        sha = _fetch_service_package(manifest, source_id, addon["kind"], addon["addon_id"])
        with db.tx() as conn:
            was_approved = pluginsvc.approved(addon)
            addons.update_manifest(conn, addon, manifest, sha, source_id)
            if (
                sha and was_approved
            ):  # the administrator allowed this package when installing it and now pressed Update: the allowance carries over
                pluginsvc.approve(conn, addons.get(conn, vid, aid))
        if sha:
            pluginsvc.restart(addon["id"])  # the new code runs only when the package is approved (pluginsvc.approved)
            pluginsvc.kick()
    except sources.SourceError as exc:
        return go(request, _manage(addon["kind"], vid), str(exc))
    events.changed()
    return go(request, _manage(addon["kind"], vid), "addon.updated")


@app.get("/v/{vid}/integrations/{aid}/changelog")
def addons_changelog(request: Request, vid: int, aid: int):
    """The news of an update, for the window that opens on *Update available*: the changelog of the package, read from its source now (and kept for ten
    minutes, like every file of a source). Only for a package that HAS an update and only for people who may update it. The answer is a piece of a page
    (``_update_log.html``) with every text escaped - never a whole page, never anything of the source as markup."""
    if not _may_manage(request):
        return Response(status_code=403)
    text = None
    state = "error"
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        addon = addons.get(conn, vid, aid)
        if addon is None or addon["missing"] or not addon["has_update"]:
            raise HTTPException(404)
        source_id = addon["source_id"]
        if source_id is None:  # installed without a source: the update comes from the source that offers a newer version
            offer = addons.unlinked_offer(conn, addon)
            source_id = offer["source_id"] if offer else None
        try:
            text = sources.fetch_changelog(conn, source_id, addon["kind"], addon["addon_id"], config.language()) if source_id else None
            state = "ok" if text and text.strip() else "none"
        except sources.SourceError:  # no connection and nothing kept, or the file is too big to be a changelog
            state = "error"
    log: dict = {}
    if state == "ok":
        log = changelog.parse(text, addon["m"].get("version", ""))
        if log["empty"]:
            state = "nothing" if log["structured"] else "none"  # sections per version, but none of them is newer than the installed version
    page = templates.get_template("_update_log.html").render(
        state=state, log=log, _=i18n.translator(config.language()), icons=icon_set.ICONS
    )
    return HTMLResponse(page, headers={"Cache-Control": "no-store"})


@app.post("/v/{vid}/integrations/{aid}/link")
def addons_link(request: Request, vid: int, aid: int):
    """A package installed without a source, and a source offers exactly its version: link it (its next updates come from there). Nothing else changes."""
    if (denied := _guard(request, vid)) is not None:
        return denied
    with db.tx() as conn:
        addon = addons.get(conn, vid, aid)
        if addon is None:
            return go(request, f"/v/{vid}/integrations", "addon.err_id")
        offer = addons.unlinked_offer(conn, addon) if addon["source_id"] is None and addon["status"] != "missing" else None
        have = addon["m"].get("version", "")
        if offer is None or sources.is_newer(offer["version"], have) or sources.is_newer(have, offer["version"]):
            return go(request, _manage(addon["kind"], vid), "addon.err_id")
        conn.execute("UPDATE vehicle_addons SET source_id = ? WHERE id = ? AND source_id IS NULL", (offer["source_id"], addon["id"]))
    events.changed()
    return go(request, _manage(addon["kind"], vid), "addon.linked")


@app.post("/v/{vid}/integrations/{aid}/active")
async def addons_active(request: Request, vid: int, aid: int):
    if (denied := _guard(request, vid)) is not None:
        return denied
    form = await form_dict(request)
    with db.tx() as conn:
        addon = addons.get(conn, vid, aid)
        if addon is None:
            return go(request, f"/v/{vid}/integrations", "addon.err_id")
        try:
            addons.set_active(
                conn, addon, form.get("active", form.get("enabled")) == "1"
            )  # Start / Stop buttons say "active", the switch in the list "enabled"
        except addons.AddonError as exc:  # it takes an interface another plugin of this car holds
            if form.get("ajax"):
                return Response(status_code=409)
            return go(request, _manage(addon["kind"], vid), exc.key)
    pluginsvc.kick()
    events.changed()
    if form.get("ajax"):
        return Response(status_code=204)
    return go(request, _manage(addon["kind"], vid), "saved")


def _token_page(request: Request, token: str, name: str, vid: int, addon: dict | None = None):
    return render(
        request,
        "api_token.html",
        token=token,
        conn_name=name,
        conn_file=((addon or {}).get("m") or {}).get("connection_file"),
        addon_pk=(addon or {}).get("id"),
        nav="integrations",
        base_url=config.external_url() or "",
        back=f"/v/{vid}/plugins",
        vid=vid,
    )


def _settings_page(
    request: Request,
    vid: int,
    addon: dict,
    shown: dict,
    errors: dict,
    status: int = 200,
    hb_typed: dict | None = None,
    hb_errors: dict | None = None,
    hb_taken: dict | None = None,
    hb_slots: frozenset = frozenset(),
):
    manage = _may_manage(request)
    states = ha.all_states() if addon["m"].get("bridge") and manage else None  # (a call to Home Assistant: before the database is opened)
    if pluginsvc.service_of(addon) and not pluginsvc.approved(addon):
        _hold_service_buttons(addon)  # the actions on the tab General need the service, too
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        ctx = vehicle_ctx(conn, vehicle, "integrations")
        in_bar = ("x-" + addon["addon_id"]) in [k for k, _i in navigation.order(conn, vid)[:4]]
        # the token of a configured plugin can be read again (administrator only): for a new installation that must keep what is in the car
        kept = connectors.remembered(conn, addon.get("token_id")) if addon["status"] == "configured" and _may_manage(request) else ""
        fingerprint = (
            connectors.fingerprint(conn, addon.get("token_id")) if addon.get("token_id") and addon["status"] == "configured" else ""
        )
        car_files = (
            assets.general_rows(conn, addon, vehicle["slug"], pluginsvc.approved(addon))
            if addon["m"].get("files") or addon["m"].get("bundles")
            else []
        )
    t = i18n.translator(config.language())
    set_tabs = addons.settings_tabs(addon["m"]["settings"], frozenset(errors))
    hb = None
    if addon["m"].get("bridge") and manage:
        with db.tx() as conn:
            hb = habridge.page_model(conn, addon, states, t, hb_typed, hb_slots)
    return render(
        request,
        "addon_settings.html",
        hb=hb,
        hb_manage=manage,
        hb_errors=hb_errors or {},
        hb_taken=hb_taken or {},
        set_tabs=set_tabs,
        debug_days=connectors.DEBUG_DAYS,
        debug_default=connectors.DEBUG_DEFAULT_DAYS,
        car_files=car_files,
        set_tab_on=next((g["id"] for g in set_tabs if g["err"]), set_tabs[0]["id"] if set_tabs else ""),
        kept_token=kept,
        token_fp=fingerprint,
        status=status,
        **ctx,
        hide_hero=True,
        addon=addon,
        shown=shown,
        errors={k: t(v) for k, v in errors.items()},
        back_to=_manage(addon["kind"], vid),  # Back is the Manage page, always (never an address taken from the link)
        in_bar=in_bar,
    )


def _vin(vid: int) -> str:
    with db.tx() as conn:
        row = conn.execute("SELECT vin FROM vehicles WHERE id = ?", (vid,)).fetchone()
    return (row["vin"] if row and row["vin"] else "") or ""


def _guide_page(
    request: Request,
    vid: int,
    aid: int,
    step: int = 1,
    token: str = "",
    fresh: bool = False,
    errors: dict | None = None,
    shown: dict | None = None,
    status: int = 200,
    notice: str = "",
):
    """The set-up guide in three fixed steps: 1 check (address, VIN), 2 token and settings, 3 files and instructions.
    The token travels from step to step inside the page only (never stored): it is shown once when new, or typed again and compared with the fingerprint.
    A package with a free ``setup.flow`` is handled by ``setupflow_web`` instead (the older routes of the token and the files land there, too)."""
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        addon = addons.get(conn, vid, aid)
        if addon is None or not addon["m"].get("setup"):
            return go(request, f"/v/{vid}/plugins", "addon.err_id")
        if addon["m"]["setup"].get("flow"):
            from . import setupflow_web

            return setupflow_web.page(
                request,
                vid,
                aid,
                step,
                token,
                fresh=fresh,
                errors=errors,
                shown=shown,
                status=status,
                kind={2: "token", 3: "files"}.get(step, "") if errors or token else "",
            )
        ctx = vehicle_ctx(conn, vehicle, "integrations")
        vin = vehicle["vin"] or ""
        # a token the service made by itself when it first started (the plugin was never set up) is nobody's token yet: the guide offers no
        # "existing token" for it - step 2 starts as if there were none
        known = addon.get("token_id") if addon["status"] == "configured" else None
        fingerprint = connectors.fingerprint(conn, known)
        saved_token = bool(connectors.remembered(conn, known)) and _may_manage(request)
    lang = config.language()
    setup = addon["m"]["setup"]
    tr = i18n.translator(lang)
    own = {s["id"]: ((s.get("l10n") or {}).get(lang) or {}) for s in setup["steps"]}
    by_id = {s["id"]: s for s in setup["steps"]}

    def text_of(sid: str) -> str:
        s = by_id.get(sid)
        return str(addons.render_text(own.get(sid, {}).get("text", s["text"]))) if s and (own.get(sid, {}).get("text") or s["text"]) else ""

    need = {
        "external_https": {"ok": bool(config.external_url()), "value": config.external_url() or "", "link": "/settings/system#external"},
        "vehicle_vin": {"ok": bool(vin), "value": vin, "link": f"/v/{vehicle['slug']}/edit?mode=form"},
    }
    names = {
        "external_https": ("guide.need_external_https", "guide.missing_external_https"),
        "vehicle_vin": ("guide.need_vehicle_vin", "guide.missing_vehicle_vin"),
    }
    checks = [{**need[key], "label": tr(names[key][0]), "missing": tr(names[key][1])} for key in setup["requires"]]
    ready = all(c["ok"] for c in checks)
    extra = [
        s for s in setup["steps"] if s.get("page") and s["id"] not in ("check", "token", "files")
    ]  # steps of the plugin: a page of its service
    extra_steps = [
        {
            "id": s["id"],
            "page": s["page"],
            "title": (own.get(s["id"], {}).get("title") or s.get("title") or s["id"]),
            "text": text_of(s["id"]),
        }
        for s in extra
    ]
    step = min(step, 3 + len(extra_steps))
    if not ready:
        step = 1
    offered = pluginsvc.approved(addon)
    rows = {r["name"]: r for r in assets.listing(addon, offered)}
    files_step = by_id.get("files") or {}
    bundle_rows = [
        {**rows[n], "entries": []} for n in files_step.get("bundles", []) if n in rows
    ]  # the technical list of entries belongs on the info page
    only = addons.guide_keys(addon)
    fields = [f for f in addon["m"].get("settings", []) if only is None or f["key"] in only]  # a package may list the settings per step
    values = shown if shown is not None else addon["vals"]
    return render(
        request,
        "addon_guide.html",
        status=status,
        **ctx,
        hide_hero=True,
        addon=addon,
        step=step,
        checks=checks,
        ready=ready,
        token=token,
        fresh=fresh,
        has_token=bool(known),
        fingerprint=fingerprint,
        saved_token=saved_token,
        main_fields=[f for f in fields if not f.get("advanced")],
        adv_fields=[f for f in fields if f.get("advanced")],
        shown=values,
        errors={k: tr(v) for k, v in (errors or {}).items()},
        notice=notice,
        extra_steps=extra_steps,
        texts={"check": text_of("check"), "token": text_of("token"), "files": text_of("files")},
        bundle_rows=bundle_rows,
        pkg_offered=offered,
        has_file=bool(addon["m"].get("connection_file")),
        file_name=(addon["m"].get("connection_file") or {}).get("name", ""),
        tokenless=not addons.needs_token(addon["m"]),
        token_free=not addons.file_has_secret(addon["m"]),
        back_to=_manage(addon["kind"], vid),
    )


@app.get("/v/{vid}/integrations/{aid}/guide")
def addon_guide(request: Request, vid: int, aid: int):
    """The set-up guide of a plugin (its manifest's ``setup``), always from step 1 or the one asked for with ``?step=``."""
    try:
        step = min(12, max(1, int(request.query_params.get("step", "1"))))
    except ValueError:
        step = 1
    return _guide_page(request, vid, aid, step)


@app.post("/v/{vid}/integrations/{aid}/guide/token")
async def addon_guide_token(request: Request, vid: int, aid: int):
    """A new token inside step 2: shown once, and carried to step 3 for the connection file."""
    if (denied := _guard(request, vid)) is not None:
        return denied
    with db.tx() as conn:
        addon = addons.get(conn, vid, aid)
        if addon is None or addon["kind"] != "plugin" or not addon["m"].get("setup") or addon["m"]["setup"].get("flow"):
            return go(request, f"/v/{vid}/plugins", "addon.err_id")
        token = addons.new_token(conn, vid, addon)
    if pluginsvc.service_of(addon):
        pluginsvc.write_token(addon, token)
        pluginsvc.restart(addon["id"])
    return _guide_page(request, vid, aid, 2, token, fresh=True)


_token_tries: dict[int, list[float]] = {}  # plugin row id -> times of wrong guesses (the last 15 minutes)
TOKEN_TRIES = 5
TOKEN_WINDOW = 15 * 60


def _guide_token_ok(conn, aid: int, addon: dict, candidate: str) -> str:
    """'' when the typed token is the plugin's token, else the error key. Wrong guesses are limited: five in 15 minutes per plugin."""
    import time

    now = time.monotonic()
    tries = [x for x in _token_tries.get(aid, []) if now - x < TOKEN_WINDOW]
    if len(tries) >= TOKEN_TRIES:
        _token_tries[aid] = tries
        return "err.token_rate"
    if not candidate or not connectors.token_matches(conn, addon["token_id"], candidate):
        _token_tries[aid] = [*tries, now]
        return "err.token_mismatch"
    _token_tries.pop(aid, None)
    return ""


@app.post("/v/{vid}/integrations/{aid}/guide/next")
async def addon_guide_next(request: Request, vid: int, aid: int):
    """'Next' in step 2: the settings are saved (nothing is saved when one is wrong), a token typed for re-use is compared with its fingerprint,
    and step 3 follows with the token carried along."""
    if (denied := _guard(request, vid)) is not None:
        return denied
    form = await form_dict(request)
    carried = (form.get("token") or "").strip()[:200]
    have = (form.get("have_token") or "").strip()[:200]
    adopt = (form.get("adopt_token") or "").strip()[:200]
    mode = (form.get("token_mode") or "").strip()  # the three boxes of step 2: saved | existing | new (empty = older form)
    with db.tx() as conn:
        _a = addons.get(conn, vid, aid)
    if _a is not None and not addons.needs_token(
        _a["m"]
    ):  # a plugin that never reports has no token to choose: only the settings are saved
        carried = have = adopt = mode = ""
    use_saved = bool(form.get("use_saved")) or mode == "saved"
    if mode in ("saved", "new"):
        have = adopt = ""
    elif mode == "existing":
        use_saved = False
    with db.tx() as conn:
        addon = addons.get(conn, vid, aid)
        if addon is None or addon["kind"] != "plugin" or not addon["m"].get("setup") or addon["m"]["setup"].get("flow"):
            return go(request, f"/v/{vid}/plugins", "addon.err_id")
        keys = addons.guide_keys(addon)  # None = the package lists no settings per step: the guide shows (and saves) all of them
        errors = addons.check_settings(addons.guide_manifest(addon, keys), addons.guide_form(addon, form, keys), addon["vals"])
        if errors:
            return _guide_page(
                request,
                vid,
                aid,
                2,
                carried,
                errors=errors,
                shown=addons._guide_values(addon, form, keys) | {k: form.get(k, "") for k in errors},
                status=400,
            )
        if (
            adopt and addon.get("token_id") and addon["status"] != "configured"
        ):  # the service's own start-up token: nobody has it, it makes way
            connectors.delete_token(conn, addon["token_id"])
            conn.execute("UPDATE vehicle_addons SET token_id = NULL WHERE id = ?", (addon["id"],))
            addon = addons.get(conn, vid, aid)
        if adopt and not addon.get("token_id"):  # a token that is already on the device: stored as a fingerprint, fixed from now on
            try:
                connectors.adopt_token(conn, addon["m"]["name"], vid, adopt)
            except connectors.ApiError as exc:
                return _guide_page(
                    request,
                    vid,
                    aid,
                    2,
                    carried,
                    errors={"__token": f"err.{exc.code}"},
                    shown=addons._guide_values(addon, form, keys),
                    status=400,
                )
            conn.execute(
                "UPDATE vehicle_addons SET token_id = (SELECT id FROM api_tokens ORDER BY id DESC LIMIT 1) WHERE id = ?", (addon["id"],)
            )
            addon = addons.get(conn, vid, aid)
            carried = adopt
            if addon["m"].get("connection_file"):
                connectors.remember(conn, addon["token_id"], adopt)
            if pluginsvc.service_of(addon):
                pluginsvc.write_token(addon, adopt)
        if use_saved and not have:  # "use the kept token": an administrator only (this route is guarded), only while the option is on
            have = connectors.remembered(conn, addon.get("token_id"))
        if have:
            bad = _guide_token_ok(conn, aid, addon, have)
            if bad:
                return _guide_page(request, vid, aid, 2, carried, errors={"__token": bad}, status=429 if bad == "err.token_rate" else 400)
            carried = have
            if addon["m"].get("connection_file"):
                connectors.remember(
                    conn, addon.get("token_id"), have
                )  # a token that was typed (and fits) is kept from now on, when allowed
        renewed = ""
        if mode == "new":  # "Make a new token": the old one becomes invalid, the new one is shown once and carried to step 3
            renewed = addons.new_token(conn, vid, addon)
            addon = addons.get(conn, vid, aid)
        made = (
            addons.set_up(conn, vid, addon, form, keys) or renewed
        )  # saves the settings; a plugin without a token gets one here (shown once)
    if made and pluginsvc.service_of(addon):
        pluginsvc.write_token(addon, made)
    if pluginsvc.service_of(addon):
        pluginsvc.restart(addon["id"])  # settings.json is written again at the start
    events.changed()
    return _guide_page(request, vid, aid, 3, made or carried, fresh=bool(made))


@app.post("/v/{vid}/integrations/{aid}/guide/file")
async def addon_guide_file(request: Request, vid: int, aid: int):
    """The connection file in step 3: the token is compared with the stored fingerprint, then it goes into the file; nothing is stored."""
    if (denied := _guard(request, vid)) is not None:
        return denied
    form = await form_dict(request)
    candidate = (form.get("token") or "").strip()[:200]
    with db.tx() as conn:
        addon = addons.get(conn, vid, aid)
        if addon is None or addon["kind"] != "plugin" or not addon["m"].get("connection_file"):
            return go(request, f"/v/{vid}/plugins", "addon.err_id")
        secret = addons.file_has_secret(addon["m"])
        bad = _guide_token_ok(conn, aid, addon, candidate) if secret else ""
        if bad:
            return _guide_page(request, vid, aid, 3, "", errors={"__token": bad}, status=429 if bad == "err.token_rate" else 400)
        text = addons.connection_file_text(
            addon["m"], addon["vals"], token=candidate if secret else "", vehicle=vid, url=config.external_url() or "", vin=_vin(vid)
        )
        name = addon["m"]["connection_file"]["name"]
    return Response(
        text,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"},
    )


@app.post("/v/{vid}/integrations/{aid}/guide/bundle")
async def addon_guide_bundle(request: Request, vid: int, aid: int):
    """A zip of the package that carries the connection file (``connection_file_to`` of the bundle): built now, with the token of this run (compared
    with the stored fingerprint first); nothing of it is stored. Administrator only, only while the package is approved."""
    if (denied := _guard(request, vid)) is not None:
        return denied
    form = await form_dict(request)
    candidate = (form.get("token") or "").strip()[:200]
    name = (form.get("name") or "")[:60]
    with db.tx() as conn:
        addon = addons.get(conn, vid, aid)
        bundle = next(
            (b for b in (addon["m"].get("bundles", []) if addon else []) if b["name"] == name and b.get("connection_file_to")), None
        )
        if (
            addon is None
            or addon["kind"] != "plugin"
            or not addon["m"].get("connection_file")
            or bundle is None
            or not pluginsvc.approved(addon)
        ):
            return go(request, f"/v/{vid}/plugins", "addon.err_id")
        secret = addons.file_has_secret(addon["m"])
        bad = _guide_token_ok(conn, aid, addon, candidate) if secret else ""
        if bad:
            return _guide_page(request, vid, aid, 3, "", errors={"__token": bad}, status=429 if bad == "err.token_rate" else 400)
        text = addons.connection_file_text(
            addon["m"], addon["vals"], token=candidate if secret else "", vehicle=vid, url=config.external_url() or "", vin=_vin(vid)
        )
        data = assets.build_bundle(addon, bundle, text)
        if data is not None:
            assets.record_delivery(conn, addon, name)
    if data is None:
        return go(request, f"/v/{vid}/plugins", "addon.err_id")
    return Response(
        data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@app.get("/v/{vid}/integrations/{aid}/get/{name}")
def addon_get_file(request: Request, vid: int, aid: int, name: str):
    """A file or a package of the plugin from the tab *General*: handed out through this car's own address, so the app notes what was handed out and
    when (``addon_deliveries``). A package that carries the token is built with the kept token; when the app keeps none, the set-up guide does it.
    Administrator only, only while the package is approved."""
    if (denied := _guard(request, vid)) is not None:
        return denied
    if not addons.FILE_NAME.fullmatch(name):
        raise HTTPException(404)
    with db.tx() as conn:
        addon = addons.get(conn, vid, aid)
        if addon is None or not pluginsvc.approved(addon):
            return go(request, f"/v/{vid}/plugins", "addon.err_id")
        bundle = next((b for b in addon["m"].get("bundles", []) if b["name"] == name), None)
        secret = addons.file_has_secret(addon["m"])
        if bundle is not None and bundle.get("connection_file_to"):
            token = connectors.remembered(conn, addon.get("token_id")) if secret else ""
            if secret and not token:
                return go(request, f"/v/{vid}/integrations/{aid}/guide?step=3", "addon.get_via_guide")
            text = addons.connection_file_text(
                addon["m"], addon["vals"], token=token, vehicle=vid, url=config.external_url() or "", vin=_vin(vid)
            )
            data, ctype = assets.build_bundle(addon, bundle, text), addons.FILE_TYPES[".zip"]
        elif bundle is not None:
            data, ctype = assets.build_bundle(addon, bundle), addons.FILE_TYPES[".zip"]
        else:
            found = assets.read_file(addon, name)
            data, ctype = found if found else (None, "")
        if data is None:
            raise HTTPException(404)
        assets.record_delivery(conn, addon, name)
    return Response(
        data,
        media_type=ctype,
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@app.get("/v/{vid}/integrations/{aid}/info")
def addon_info(request: Request, vid: int, aid: int):
    """Everything about ONE plugin / integration on one page: overview, what it offers and uses (interfaces, files), its log with the debug switch."""
    return _info_page(request, vid, aid, request.query_params.get("tab", "overview"))


@app.get("/v/{vid}/integrations/{aid}/logs")
def addon_logs(request: Request, vid: int, aid: int):
    """The log page of a plugin (button *Logs* on its tile): what it and its service noted, newest first - all of it, or only warnings and errors."""
    return _info_page(request, vid, aid, "logs")


@app.get("/v/{vid}/integrations/{aid}/logs.txt")
def addon_logs_text(request: Request, vid: int, aid: int):
    """The same log as a plain text file (to read offline or to send along with a bug report); only people who may manage packages."""
    if (denied := _guard(request, vid)) is not None:
        return denied
    with db.tx() as conn:
        addon = addons.get(conn, vid, aid)
        if addon is None:
            return go(request, f"/v/{vid}/plugins", "addon.err_id")
        rows = conn.execute(
            "SELECT ts, level, source, message FROM vehicle_logs WHERE vehicle_id = ? AND addon_id = ? ORDER BY id DESC LIMIT 1000",
            (vid, addon["addon_id"]),
        ).fetchall()
    text = "\n".join(f"{regional.flog(r['ts'])}  {r['level']:<5}  {r['source'] or ''}  {r['message']}" for r in rows) + "\n"
    name = f"{addon['addon_id']}-log.txt"
    return Response(
        text,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


def _info_page(request: Request, vid: int, aid: int, info_tab: str):
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        addon = addons.get(conn, vid, aid)
        if addon is None:
            return go(request, f"/v/{vid}/plugins", "addon.err_id")
        ctx = vehicle_ctx(conn, vehicle, "integrations")
        data = interfaces.view(conn, vid, addon, config.external_url() or "")
        pid = addon["addon_id"]
        level = "problems" if request.query_params.get("level") == "problems" else "all"
        lines = conn.execute(
            "SELECT ts, level, source, message FROM vehicle_logs WHERE vehicle_id = ? AND addon_id = ?"
            + (" AND level IN ('warn', 'error')" if level == "problems" else "")
            + " ORDER BY id DESC LIMIT 300",
            (vid, pid),
        ).fetchall()
        problems = conn.execute(
            "SELECT COUNT(*) FROM vehicle_logs WHERE vehicle_id = ? AND addon_id = ? AND level IN ('warn', 'error')", (vid, pid)
        ).fetchone()[0]
        traffic = conn.execute(
            "SELECT ts, kind, method, path, status, bytes, ms, detail FROM vehicle_traffic WHERE vehicle_id = ? AND addon_id = ? ORDER BY id DESC LIMIT 150",
            (vid, pid),
        ).fetchall()
        keep, debug_on = connectors.log_keep(conn), connectors.plugin_debug(conn, vid, pid)
        with_svc = _with_service([dict(addon)])[0]
    t_ = i18n.translator(config.language())
    states = {
        "waiting": "svc.state_waiting",
        "installing": "svc.state_installing",
        "running": "svc.state_running",
        "starting": "svc.state_starting",
        "restarting": "svc.state_restarting",
        "stopped": "svc.state_stopped",
        "error": "svc.state_error",
    }
    svc = with_svc.get("svc")
    if info_tab not in ("overview", "interfaces", "logs"):
        info_tab = "overview"
    info_base = f"/v/{ctx['v']['slug']}/integrations/{aid}/info"
    info_tabs = [
        {
            "key": k,
            "href": info_base if k == "overview" else (f"{info_base[: -len('info')]}logs" if k == "logs" else f"{info_base}?tab={k}"),
            "title": t_(title),
            "on": k == info_tab,
            "icon": ic,
        }
        for k, title, ic in (
            ("overview", "info.overview", "info"),
            ("interfaces", "ifc.title", "swap-vertical"),
            ("logs", "addon.logs", "list"),
        )
    ]
    return render(
        request,
        "addon_info.html",
        **ctx,
        section_tabs=info_tabs,
        info_tab=info_tab,
        hide_hero=True,
        addon=addon,
        data=data,
        vid=vid,
        lines=lines,
        log_level=level,
        log_problems=problems,
        log_url=f"{info_base.rsplit('/', 1)[0]}/logs",
        traffic=traffic,
        keep=keep,
        debug_on=debug_on,
        svc=svc,
        svc_state=t_(states.get(svc["state"], "svc.state_stopped")) if svc else "",
        back_to=_manage(addon["kind"], vid),
    )


@app.get("/v/{vid}/integrations/{aid}/interfaces")
def addon_interfaces(request: Request, vid: int, aid: int):
    """The old address: interfaces now sit on the Info page."""
    return RedirectResponse(f"{request.state.base}/v/{vid}/integrations/{aid}/info?tab=interfaces", status_code=303)


@app.get("/v/{vid}/integrations/{aid}/settings")
def addon_settings(request: Request, vid: int, aid: int):
    """The settings of a package as a page of its own (it used to be a pop-up)."""
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        addon = addons.get(conn, vid, aid)
    if addon is None:
        return go(request, f"/v/{vid}/plugins", "addon.err_id")
    return _settings_page(request, vid, addon, addon["vals"], {})


@app.post("/v/{vid}/integrations/{aid}/setup")
async def addons_setup(request: Request, vid: int, aid: int):
    if (denied := _guard(request, vid)) is not None:
        return denied
    form = await form_dict(request)
    with db.tx() as conn:
        addon = addons.get(conn, vid, aid)
        if addon is None:
            return go(request, f"/v/{vid}/integrations", "addon.err_id")
        errors = addons.check_settings(addon["m"], form, addon["vals"])
        if errors:  # nothing is saved: the page comes back with what was typed and what is wrong
            return _settings_page(
                request,
                vid,
                addon,
                addons.clean_settings(addon["m"], form, addon["vals"]) | {k: form.get(k, "") for k in errors},
                errors,
                400,
            )
        token = addons.set_up(conn, vid, addon, form)
    if pluginsvc.service_of(addon):
        if token:
            pluginsvc.write_token(addon, token)  # the same token for the car's file and for the service
        pluginsvc.restart(addon["id"])  # settings.json is written again at the start
    events.changed()
    if token:
        return _token_page(request, token, addon["m"]["name"], vid, addon)
    return go(request, _where(addon["kind"], vid), "saved")


@app.post("/v/{vid}/integrations/{aid}/token")
async def addons_token(request: Request, vid: int, aid: int):
    if (denied := _guard(request, vid)) is not None:
        return denied
    with db.tx() as conn:
        addon = addons.get(conn, vid, aid)
        if addon is None or addon["kind"] != "plugin":
            return go(request, f"/v/{vid}/integrations", "addon.err_id")
        token = addons.new_token(conn, vid, addon)
    if pluginsvc.service_of(addon):
        pluginsvc.write_token(addon, token)
        pluginsvc.restart(addon["id"])  # the service starts again with the new token
    return _token_page(request, token, addon["m"]["name"], vid, addon)


@app.post("/v/{vid}/integrations/{aid}/connection-file")
async def addons_connection_file(request: Request, vid: int, aid: int):
    """The file a plugin needs (its manifest's ``connection_file``), filled with the token that was just shown and the plugin's settings.
    The token comes from the page that showed it (it is stored only as a fingerprint); nothing is stored here."""
    if (denied := _guard(request, vid)) is not None:
        return denied
    form = await form_dict(request)
    token = (form.get("token") or "").strip()[:200]
    with db.tx() as conn:
        addon = addons.get(conn, vid, aid)
    if addon is None or addon["kind"] != "plugin" or not addon["m"].get("connection_file") or not token:
        return go(request, f"/v/{vid}/integrations", "addon.err_id")
    text = addons.connection_file_text(addon["m"], addon["vals"], token=token, vehicle=vid, url=config.external_url() or "", vin=_vin(vid))
    name = addon["m"]["connection_file"]["name"]
    return Response(
        text,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"},
    )


COMMAND_LIMIT, COMMAND_WINDOW = 6, 60.0  # commands per car per minute: a button pressed in a loop does not become a storm towards the car
_command_times: dict[int, list[float]] = {}


def _command_page(request: Request, vid: int, aid: int, bid: str):
    """The question before a command that cannot be taken back lightly (unlock, open the trunk, ...): enforced HERE, not by a dialog of the browser -
    the command runs only from the form of this page (``confirmed``)."""
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        addon = addons.get(conn, vid, aid)
        button = next((b for b in addon["m"].get("buttons", []) if b["id"] == bid and b.get("dangerous")), None) if addon else None
        if button is None:
            raise HTTPException(404)
        ctx = vehicle_ctx(conn, vehicle, "integrations")
    return render(request, "addon_command.html", **ctx, hide_hero=True, addon=addon, button=button, back_to=_manage(addon["kind"], vid))


@app.get("/v/{vid}/integrations/{aid}/button/{bid}")
def addon_command_ask(request: Request, vid: int, aid: int, bid: str):
    if (denied := _guard(request, vid)) is not None:
        return denied
    return _command_page(request, vid, aid, bid)


@app.post("/v/{vid}/integrations/{aid}/button/{bid}")
async def addon_button(request: Request, vid: int, aid: int, bid: str):
    """A free button of a plugin (``buttons`` in its plugin.json) that triggers an action: the app calls the route of the plugin's own service - it is
    never public - and shows what the service answers (done, or the reason it did not work). Only for a running plugin and only for people who may manage."""
    if (denied := _guard(request, vid)) is not None:
        return denied
    form = await form_dict(request)
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        addon = addons.get(conn, vid, aid)
        if addon is None:
            return go(request, f"/v/{vid}/plugins", "addon.err_id")
        button = next((b for b in addon["m"].get("buttons", []) if b["id"] == bid and b.get("action")), None)
        if button is None:
            raise HTTPException(404)
        hidden = not button.get("shown", True)  # its ``when`` does not hold right now: it is not on the page, so it is not run either
        ctx = vehicle_ctx(conn, vehicle, "integrations")
        who = auth_web._acting_user(request, conn)
    command = button.get("command")
    if command and button.get("dangerous") and form.get("confirmed") != "1" and not hidden:
        return _command_page(request, vid, aid, bid)  # nothing is sent before the person has said yes on that page
    limited = False
    if command:
        now = time.monotonic()
        recent = [t for t in _command_times.get(vid, []) if now - t < COMMAND_WINDOW]
        limited = len(recent) >= COMMAND_LIMIT
        _command_times[vid] = recent if limited else [*recent, now]
    if hidden:
        ok, message = False, "addon.button_when"
    elif limited:
        ok, message = False, "addon.button_rate"
    elif not addon["active"] or not pluginsvc.approved(addon):
        ok, message = False, "addon.button_off"
    else:
        payload = {"vehicle": vid, "button": bid, "language": config.language()}
        if command:
            payload["command"] = command
        ok, message = pluginsvc.call(
            addon["id"], button["action"], payload, vid, str(who["id"]) if who else "ha", timeout=float(button.get("timeout", 10.0))
        )
        if not ok and message in ("not running", "no answer"):
            message = "addon.button_down"
    if command and not hidden:  # the trail: who sent which command to the car, and what came of it (in the log of the plugin)
        by = (who["username"] if who else None) or "Home Assistant"
        outcome = "sent" if ok else f"failed - {(message or '')[:120]}"
        with db.tx() as conn:
            connectors.app_log(
                conn,
                vid,
                addon["addon_id"],
                "warn" if button.get("dangerous") or not ok else "info",
                "app",
                f"command {command} by {by}: {outcome}",
                mirror=f"command {command}: {'sent' if ok else 'failed'}",  # (neither the person nor the text the service answered)
            )
    return render(
        request,
        "addon_button.html",
        **ctx,
        hide_hero=True,
        addon=addon,
        button=button,
        ok=ok,
        message=message,
        back_to=_manage(addon["kind"], vid),
    )


@app.post("/v/{vid}/integrations/{aid}/delete")
async def addons_delete(request: Request, vid: int, aid: int):
    if (denied := _guard(request, vid)) is not None:
        return denied
    with db.tx() as conn:
        addon = addons.get(conn, vid, aid)
        kind = addon["kind"] if addon else "integration"
        if addon:
            addons.remove(conn, addon)
    if addon and addons.needs_package(addon["m"]):
        pluginsvc.forget(addon)  # stops the service and deletes its data, environment, files and (when no other car uses it) its code
    events.changed()
    return go(request, _where(kind, vid), "addon.removed")


@app.get("/v/{vid}/integrations/{aid}/service")
def service_page(request: Request, vid: int, aid: int):
    """The page where an administrator reads what a package will do (its service) or hand out (its files) and approves it - or takes the approval back."""
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        addon = addons.get(conn, vid, aid)
        if not addon or not addons.needs_package(addon["m"]):
            return go(request, f"/v/{vid}/plugins", "addon.err_id")
        service = pluginsvc.service_of(addon)
        addon = _with_service([addon])[0]
        code = []
        if service and addon.get("pkg_sha"):
            base = pluginsvc.pkg_dir(addon["addon_id"], addon["pkg_sha"])
            code = sorted(str(p.relative_to(base)) for p in base.rglob("*") if p.is_file())[:200]
        return render(
            request,
            "service_approve.html",
            **vehicle_ctx(conn, vehicle, "integrations"),
            hide_hero=True,
            addon=addon,
            service=service,
            files=code,
            pkg_files=assets.listing(addon, False, with_hidden=True),
            approved=pluginsvc.approved(addon),
            problems=pluginsvc.check_routes(conn, addon) if service else [],
            files_gone=restoresetup.files_missing(addon),
            may=_may_manage(request),
        )


@app.post("/v/{vid}/integrations/{aid}/debug")
async def addon_debug(request: Request, vid: int, aid: int):
    """The debug button of one plugin (works for a stopped one, too): more is noted for it until it is switched off again."""
    if (denied := _guard(request, vid)) is not None:
        return denied
    form = await form_dict(request)
    with db.tx() as conn:
        addon = addons.get(conn, vid, aid)
        if addon is None:
            return go(request, f"/v/{vid}/plugins", "addon.err_id")
        days = int(form["days"]) if (form.get("days") or "").isdigit() else connectors.DEBUG_DEFAULT_DAYS
        connectors.set_plugin_debug(conn, vid, addon["addon_id"], form.get("on") == "1", days)
        where = _where(addon["kind"], vid)
    if form.get("ajax"):
        return Response(status_code=204)
    return go(request, where, "saved")


@app.post("/v/{vid}/integrations/{aid}/service/approve")
def service_approve(request: Request, vid: int, aid: int):
    if (denied := _guard(request, vid)) is not None:
        return denied
    with db.tx() as conn:
        addon = addons.get(conn, vid, aid)
        if addon is None:
            return go(request, f"/v/{vid}/plugins", "addon.err_id")
        key = pluginsvc.approve(conn, addon)
    if key:
        return go(request, f"/v/{vid}/integrations/{aid}/service", key)
    if pluginsvc.service_of(addon):
        pluginsvc.install_async(aid)
    events.changed()
    return go(request, _where(addon["kind"], vid), "svc.approved" if pluginsvc.service_of(addon) else "fil.approved")


@app.post("/v/{vid}/integrations/{aid}/refetch")
def service_refetch(request: Request, vid: int, aid: int):
    """The files of an installed package are gone (a restore on another system): fetch them again from its source - exactly the package that was installed."""
    if (denied := _guard(request, vid)) is not None:
        return denied
    with db.tx() as conn:
        addon = addons.get(conn, vid, aid)
    if addon is None:
        return go(request, f"/v/{vid}/plugins", "addon.err_id")
    key = restoresetup.refetch(vid, aid)
    if key is None:
        with db.tx() as conn:
            conn.execute("UPDATE vehicle_addons SET svc_error = NULL WHERE id = ?", (aid,))
        if addon["active"] and pluginsvc.service_of(addon) and pluginsvc.approved(addon):
            pluginsvc.install_async(aid)
        events.changed()
        return go(request, _where(addon["kind"], vid), "svc.refetched")
    return go(request, f"/v/{vid}/integrations/{aid}/service", key)


@app.post("/v/{vid}/integrations/{aid}/service/revoke")
def service_revoke(request: Request, vid: int, aid: int):
    if (denied := _guard(request, vid)) is not None:
        return denied
    with db.tx() as conn:
        addon = addons.get(conn, vid, aid)
        if addon is None:
            return go(request, f"/v/{vid}/plugins", "addon.err_id")
        pluginsvc.revoke(conn, addon)
    events.changed()
    return go(request, _where(addon["kind"], vid), "saved")


_ = i18n


@app.post("/v/{vid}/modules/{key}")
async def vehicle_module(request: Request, vid: int, key: str):
    """Show or hide one built-in function for this vehicle only."""
    form = await form_dict(request)
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        try:
            modules.set_vehicle_enabled(conn, vid, key, form.get("enabled") == "1")
        except KeyError:
            return go(request, f"/v/{vehicle['slug']}/integrations", "err.choice")
        slug = vehicle["slug"]
    events.changed()
    if form.get("ajax"):
        return Response(status_code=204)
    return go(request, f"/v/{slug}/integrations", "saved")


# ------------------------------------------------------------------ debug: the one switch towards the vehicle + its log lines


@app.post("/v/{vid}/interval")
async def interval_set(request: Request, vid: int):
    if (denied := _guard(request, vid)) is not None:
        return denied
    form = await form_dict(request)
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        with contextlib.suppress(ValueError):  # not a number: unchanged
            connectors.set_interval(conn, vid, int(form.get("interval") or 0))
    if form.get("ajax"):
        return Response(status_code=204)
    return go(request, f"/v/{vid}/debug", "saved")


@app.get("/v/{vid}/debug")
def debug_page(request: Request, vid: int):
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        plugin = request.query_params.get("plugin", "")
        pk = next((a["id"] for a in addons.list_for(conn, vid) if a["addon_id"] == plugin), None) if plugin else None
        if pk:  # the log of one plugin has its own page
            return RedirectResponse(f"{request.state.base}/v/{vehicle['slug']}/integrations/{pk}/info?tab=logs", status_code=303)
        lines = conn.execute(
            "SELECT ts, level, source, message FROM vehicle_logs WHERE vehicle_id = ?"
            + (" AND addon_id = ?" if plugin else "")
            + " ORDER BY id DESC LIMIT 300",
            (vid, plugin) if plugin else (vid,),
        ).fetchall()
        traffic = conn.execute(
            "SELECT ts, kind, method, path, status, bytes, ms, detail, addon_id FROM vehicle_traffic WHERE vehicle_id = ?"
            + (" AND addon_id = ?" if plugin else "")
            + " ORDER BY id DESC LIMIT 150",
            (vid, plugin) if plugin else (vid,),
        ).fetchall()
        log_plugins = [  # every plugin of the car, so Logs of a plugin without lines still shows whose page it is
            {"id": a["addon_id"], "name": a["m"].get("name") or a["addon_id"]} for a in addons.list_for(conn, vid) if not a["missing"]
        ]
        return render(
            request,
            "debug.html",
            **vehicle_ctx(conn, vehicle, "integrations"),
            hide_hero=True,
            debug_on=connectors.debug_enabled(conn, vid),
            lines=lines,
            keep=connectors.log_keep(conn),
            log_plugins=log_plugins,
            traffic=traffic,
            plugin=plugin,
            signals=connectors.read_signals(conn, vid),
            intervals=connectors.INTERVALS,
            interval=connectors.interval_s(conn, vid),
            event_count=conn.execute("SELECT COUNT(*) FROM vehicle_events WHERE vehicle_id = ?", (vid,)).fetchone()[0],
            track_points=conn.execute("SELECT COUNT(*) FROM vehicle_track WHERE vehicle_id = ?", (vid,)).fetchone()[0],
        )


@app.get("/v/{vid}/addons/{aid}/log")
def addon_log_page(request: Request, vid: int, aid: int):
    """The old address: the log now sits on the Info page."""
    return RedirectResponse(f"{request.state.base}/v/{vid}/integrations/{aid}/info?tab=logs", status_code=303)


@app.post("/v/{vid}/debug")
async def debug_switch(request: Request, vid: int):
    if (denied := _guard(request, vid)) is not None:
        return denied
    form = await form_dict(request)
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        connectors.set_debug(conn, vid, form.get("on") == "1")
    events.changed()
    return go(request, f"/v/{vid}/debug", "saved")


@app.post("/v/{vid}/debug/clear")
async def debug_clear(request: Request, vid: int):
    if (denied := _guard(request, vid)) is not None:
        return denied
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        form = await form_dict(request)
        plugin = form.get("plugin") or ""
        for table in ("vehicle_logs", "vehicle_traffic"):  # the lines and the watched calls
            conn.execute(
                f"DELETE FROM {table} WHERE vehicle_id = ?" + (" AND addon_id = ?" if plugin else ""),
                (vid, plugin) if plugin else (vid,),
            )
    return go(request, f"/v/{vid}/debug" + (f"?plugin={plugin}" if plugin else ""), "deleted")
