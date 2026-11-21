"""FastAPI web UI (server-rendered, served through Home Assistant Ingress)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import sqlite3
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote, urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.gzip import GZipMiddleware

from . import (
    __version__,
    access,
    accounts,
    appicon,
    backup,
    calendar_ics,
    charts,
    config,
    connectors,
    db,
    energy,
    entities,
    equipment,
    events,
    fuelstats,
    ha,
    i18n,
    integrations,
    lists,
    live,
    mcp,
    media,
    modules,
    navigation,
    notify,
    plugins,
    push,
    slugs,
    sources,
    stations,
    status,
    summary,
    themes,
    trips,
    tripstats,
    units,
    userprefs,
)
from . import fuel_export as fuel_export_mod
from . import (
    icons as icon_set,
)
from . import (
    status as vehicle_status,
)
from . import (
    vin as vin_info,
)
from . import widgets as home_widgets
from .entities import ENTITIES, FormError
from .mqtt_ha import publisher

log = logging.getLogger(__name__)

HERE = Path(__file__).parent
ALLOWED_CLIENTS = {"172.30.32.2", "127.0.0.1", "::1"}  # Supervisor ingress gateway + localhost
INGRESS_PATH = re.compile(r"^/api/hassio_ingress/[A-Za-z0-9_\-]+$")
ENTITY_ID = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")

PHOTO_EXT = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
DOC_EXT = {
    **PHOTO_EXT,
    ".pdf": "application/pdf",
    ".gif": "image/gif",
    ".txt": "text/plain",
    ".csv": "text/csv",
}
MAX_PHOTO = 5 * 1024 * 1024
MAX_DOC = 25 * 1024 * 1024
DOC_CATEGORIES = ("manual", "invoice", "insurance", "registration", "inspection", "other")

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, title="Car Assistant", version=__version__)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=5)  # pages and styles shrink to about a fifth
templates = Jinja2Templates(directory=HERE / "templates")


# ------------------------------------------------------------------ middleware


def _same_origin(request: Request) -> bool:
    """CSRF protection for direct access: state-changing requests must come from our own origin."""
    origin = request.headers.get("Origin") or request.headers.get("Referer")
    if not origin:
        return False
    host = urlparse(origin).netloc
    allowed = {request.headers.get("Host", ""), request.headers.get("X-Forwarded-Host", "").split(",")[0].strip()}
    if config.external_url():
        allowed.add(urlparse(config.external_url()).netloc)
    return host in allowed


async def _api_guard(request: Request, call_next):
    """Plugin API: a valid token is the only credential (no session, no ingress); everything else is refused."""
    auth = request.headers.get("Authorization", "")
    token = auth[7:].strip() if auth[:7].lower() == "bearer " else None
    with db.tx() as conn:
        row = connectors.verify(conn, token)
    if row is None:
        await asyncio.sleep(0.5)  # slow down token guessing
        return JSONResponse(
            {"error": "unauthorized", "message": "Missing or invalid token (Authorization: Bearer ca_...)."}, status_code=401
        )
    request.state.api_token = row
    request.state.base = ""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers["Cache-Control"] = "no-store"
    return response


@app.middleware("http")
async def timing(request: Request, call_next):
    """``Server-Timing: app;dur=..`` on every answer: the browser's network tab shows how long this app needed, so a slow page can be told
    apart from a slow way to it (Home Assistant's ingress adds its own time on top)."""
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["Server-Timing"] = f"app;dur={(time.perf_counter() - started) * 1000:.1f}"
    return response


@app.middleware("http")
async def guard(request: Request, call_next):
    client = request.client.host if request.client else ""
    path = request.url.path
    if path == "/healthz":  # Supervisor watchdog; reveals nothing
        return await call_next(request)
    if path == "/mcp" or path.startswith("/mcp/"):  # the endpoint checks its own access key (no session, no ingress) - see mcp_web.py
        return await call_next(request)
    if path.startswith("/api/v1"):
        return await _api_guard(request, call_next)
    request.state.user = None
    request.state.external = not config.dev_mode() and client not in ALLOWED_CLIENTS
    if request.state.external:
        # Direct access (published port / reverse proxy). The Home Assistant panel (ingress) never gets here.
        if (refused := access.refuse(request)) is not None:  # not allowed from here (add-on option "access"), or no user yet
            return refused
        with db.tx() as conn:
            have_users = accounts.has_users(conn)
            user = accounts.session_user(conn, request.cookies.get(auth_web.COOKIE)) if have_users else None
        safe_method = request.method in ("GET", "HEAD", "OPTIONS")
        if have_users:
            request.state.user = user
            if user is not None and not auth_web.is_public(path):
                token = request.cookies.get(auth_web.COOKIE)
                if accounts.is_locked(user):  # a device with a passcode that was idle: only the unlock page (and sign-out) work
                    if path not in ("/unlock", "/logout"):
                        if request.method in ("GET", "HEAD"):
                            target = path + (f"?{request.url.query}" if request.url.query else "")
                            return RedirectResponse(f"/unlock?next={quote(target)}", status_code=303)
                        return Response("Locked.", status_code=401)
                elif user["has_pin"]:
                    with db.tx() as conn:
                        accounts.mark_active(conn, token, user)
            if user is None and not auth_web.is_public(path):
                if request.method in ("GET", "HEAD"):
                    target = path + (f"?{request.url.query}" if request.url.query else "")
                    return RedirectResponse(f"/login?next={quote(target)}", status_code=303)
                return Response("Authentication required.", status_code=401)
            if user is not None and not user["is_admin"] and auth_web.admin_only(path):
                return Response("Only an administrator may do this.", status_code=403)
            if not safe_method and not _same_origin(request):
                return Response("Forbidden – cross-site request.", status_code=403)
        elif not (request.method in ("GET", "HEAD") and access.is_icon(path)):  # no user yet: only the icons of the locked page are served
            return Response("Forbidden - direct access is locked.", status_code=403)
    base = request.headers.get("X-Ingress-Path", "")
    request.state.base = base if INGRESS_PATH.match(base) else ""
    shown = re.match(r"^/v/([^/]+)(/.*)?$", request.url.path)
    if shown and not shown.group(1).isdigit():  # /v/<name>/... works like /v/<id>/... (numeric addresses keep working, too)
        with db.tx() as conn:
            vid = slugs.id_for(conn, shown.group(1))
        if vid is None:
            return render(request, "error.html", status=404, nf_path=request.url.path[:120])
        if vid is not None:
            rewritten = f"/v/{vid}{shown.group(2) or ''}"
            request.scope["path"], request.scope["raw_path"] = rewritten, rewritten.encode()
    module_key = modules.module_for_path(request.scope["path"])  # the numeric form: /v/<name>/... was rewritten above
    if module_key:
        owner = re.match(r"^/v/(\d+)/", request.scope["path"])
        with db.tx() as conn:
            off = modules.is_enabled(conn, module_key, int(owner.group(1)) if owner else None) is False
        if off:
            return render(request, "error.html", status=404, module_off=module_key)
    if not request.scope["path"].startswith("/static"):
        with db.tx() as conn:
            lists.use(
                conn, request.state.user["id"] if request.state.user else None
            )  # how many cards a list loads at a time (the person's choice)
    response = await call_next(request)
    last = shown and not shown.group(1).isdigit() and request.method == "GET" and response.status_code < 400
    if last and request.cookies.get(LAST_CAR) != shown.group(1):  # the car chosen last: the Car tab of the settings is about this one
        response.set_cookie(LAST_CAR, shown.group(1), max_age=365 * 86400, httponly=True, samesite="lax", path="/")
    if request.url.path.startswith("/static/") and request.query_params.get("v"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"  # the address carries the app version
    elif request.url.path.startswith("/static/fonts/"):
        response.headers["Cache-Control"] = "public, max-age=2592000"
    elif request.url.path.startswith(("/static/", "/icon/")) or request.url.path.endswith(".webmanifest"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.middleware("http")  # registered last = outermost: every answer carries these, also the early refusals (401, 403, login redirect)
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault(  # nothing is loaded from other hosts: map tiles come through this app (tiles.py)
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data:; media-src 'self' blob:; style-src 'self' 'unsafe-inline'; frame-ancestors 'self'; form-action 'self'",
    )
    return response


# ------------------------------------------------------------------ helpers


def _place_with_names(conn, place: dict | None) -> dict | None:
    """The position card with the place and street of the spot, when the map info is on and they are known (else asked in the background)."""
    from . import places

    if place and (status.map_tiles_enabled(conn) or not places.custom_service()):  # the offline list needs no map info
        lat, lon = float(place["lat"]), float(place["lon"])
        known = places.here_cached(conn, lat, lon)
        if known:
            place["town"], place["street"] = known
        else:
            places.kick_here(lat, lon)
    return place


def _period_label(key: str, group: str) -> str:
    """Short label of a period under a chart: ``18.11.`` / ``KW47`` / ``11/26``."""
    if group == "day":
        return f"{key[8:10]}.{key[5:7]}."
    if group == "week":
        return f"KW{int(key[6:])}"
    return f"{key[5:7]}/{key[2:4]}"


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def fdate(value: str | None) -> str:
    if not value:
        return ""
    try:
        d = date.fromisoformat(value[:10])
    except ValueError:
        return value
    return d.strftime(i18n.LANGUAGES[config.language()]["date"])


def fshort(value) -> str:
    """Date and time without the year ("13.11. 16:04"), in the local time zone and the date order of the language."""
    if not value:
        return ""
    fmt = i18n.LANGUAGES[config.language()]["date"]
    fmt = fmt[2:].lstrip(".-/ ") if fmt.startswith("%Y") else fmt[:-2] if fmt.endswith("%Y") else fmt
    return value.astimezone().strftime(f"{fmt} %H:%M")


def fnum(value, digits: int = 0) -> str:
    if value is None or value == "":
        return ""
    try:
        text = f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return str(value)
    if config.language() == "de":
        text = text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return text


def _nav_section(path: str) -> str:
    for key in ("integrations", "settings", "stations"):
        if path.startswith("/" + key):
            return key
    return "home"


_SWITCH_SAME_PAGE = ("/more", "/security", "/docs", "/integrations", "/edit")


def _switch_suffix(path: str, on_more: bool) -> str:
    """Where "change vehicle" leads: staying in More means staying on the same page of the other car (or its More list)."""
    if not on_more:
        return ""
    parts = path.rstrip("/").split("/")  # ['', 'v', '<id>', ...]
    rest = "/" + "/".join(parts[3:]) if len(parts) > 3 and parts[1] == "v" else ""
    if rest in _SWITCH_SAME_PAGE or (rest.startswith("/e/") and rest.count("/") == 2):
        return rest
    return "/more"


LAST_CAR = "ca_last"  # the car whose pages were opened last (a slug); the settings of "Car" are about this car
APP_COOKIE = "ca_car"  # set by /app/<car>: this device (the home-screen web app of one car) shows that car only


def _app_car(request: Request, conn) -> sqlite3.Row | None:
    """The car this device was set up for through /app/<car> (None = normal: all cars)."""
    token = request.cookies.get(APP_COOKIE, "")
    if not token or len(token) > 80:
        return None
    return conn.execute("SELECT id, name, slug FROM vehicles WHERE slug = ? AND archived = 0", (token,)).fetchone()


BACK_RULES = (
    (r"(/v/[^/]+)/integrations/\d+/(?:service|setup|token)", r"\1/plugins"),
    (r"(/v/[^/]+)/debug", r"\1/plugins"),
    (r"(/v/[^/]+)/trips/\d+", r"\1/e/trips"),
    (r"(/v/[^/]+)/report", r"\1/e/fuel"),
    (r"(/v/[^/]+)/media", r"\1/edit"),
    (r"(/v/[^/]+)/widgets", r"\1"),
    (r"(/v/[^/]+)/packages/\d+/(plugin|integration)/[^/]+", r"\1/\2s/add"),
    (r"(/v/[^/]+)/(plugin|integration)s/sources", r"\1/\2s/add"),
)


def render(request: Request, name: str, status: int = 200, **ctx):
    page_lang = ctx.pop("force_lang", None) or config.language()  # the first-start language choice is always English
    t = i18n.translator(page_lang)
    with db.tx() as conn:
        ctx["global_nav"] = modules.global_nav(conn)
        ctx["theme"] = themes.current(conn)
        ctx["ext_set"] = bool(config.external_url())
        ctx["google_help"] = db.get_setting(conn, "google.help", "0") == "1"
        ctx.setdefault("external_url", config.external_url())
        ctx["port_on"] = (
            ha.network_port()[1] is not None
        )  # a port is set: people sign in, and design and touch feedback are theirs; otherwise the system's
        me_id = (auth_web._acting_user(request, conn) or {"id": None})["id"] if ctx["port_on"] else None
        theirs = userprefs.get(conn, me_id, "design")
        if theirs and theirs in themes.available():
            ctx["theme"] = theirs  # a person's own design (only with a port) ...
        own, own_accent = None, None
        shown_car = ctx.get("v")
        if shown_car is not None and "theme" in shown_car.keys():  # noqa: SIM118 (a Row: "in" would look at the values)
            own = shown_car["theme"]
            own_accent = shown_car["accent"] if "accent" in shown_car.keys() else None  # noqa: SIM118
        if (
            own is None and ctx.get("nav_vid") and not ctx.get("system_design")
        ):  # pages of a car that show no vehicle row (More, security ...) follow its design as well
            row = conn.execute("SELECT theme, accent FROM vehicles WHERE id = ?", (ctx["nav_vid"],)).fetchone()
            own, own_accent = (row["theme"], row["accent"]) if row else (None, None)
        own_set = bool(own) and own in themes.available()
        if own_set:  # ... and a car with its own design shows that one on its pages
            ctx["theme"] = own
        ctx["theme_scheme"], ctx["theme_bg"] = themes.meta(ctx["theme"])
        ctx["theme_attr"] = themes.attr(ctx["theme"])  # data-theme of the page; the designs with your own colour use the dark / light base
        ctx["theme_file"] = themes.base_of(ctx["theme"]) if themes.base_of(ctx["theme"]) != themes.DEFAULT else None
        ctx["accent_css"] = (
            themes.accent_css(
                (themes.clean_accent(own_accent) if own_set else None)  # the car's own colour, else the one of the system
                or themes.clean_accent(db.get_setting(conn, themes.ACCENT_SETTING, ""))
                or themes.DEFAULT_ACCENT,
                ctx["theme_scheme"],
            )
            if themes.is_custom(ctx["theme"])
            else ""
        )
        ctx["page_sizes"], ctx["page_size"] = lists.SIZES, lists.current_choice(conn, me_id)  # how many cards a list loads at a time
        mine = userprefs.get(conn, me_id, "haptics")  # the person's own choice wins
        ctx["haptics"] = (
            mine if mine is not None else db.get_setting(conn, "ui.haptics", "1")
        ) == "1"  # a soft tap when the bottom bar is used (iPhone)
        active = conn.execute(
            "SELECT id, name, slug, plate, photo FROM vehicles WHERE archived = 0 ORDER BY name COLLATE NOCASE"
        ).fetchall()
        app_car = _app_car(request, conn)
        vehicle = ctx.get("v")
        nav_vid = vehicle["id"] if vehicle else ctx.get("nav_vid", active[0]["id"] if active else None)
        if not vehicle and "nav_vid" not in ctx and request.url.path.rstrip("/") == "":
            nav_vid = None  # the start page where a car is chosen: no car is preselected, neither in the bar nor in the side bar
        named = conn.execute("SELECT name FROM vehicles WHERE id = ?", (nav_vid,)).fetchone() if nav_vid else None
        ctx["nav_vname"] = named["name"] if named else ""  # the car the navigation belongs to (also on pages without a car in the address)
        ctx["live_poll"] = f"/v/{vehicle['id']}/live-state" if vehicle and connectors.has_live_source(conn, vehicle["id"]) else None
        mode_row = conn.execute("SELECT fuel_type, energy_mode FROM vehicles WHERE id = ?", (nav_vid,)).fetchone() if nav_vid else None
        ctx["energy_mode"] = energy.mode(mode_row) if mode_row else "fuel"
        if ctx["energy_mode"] == "charge":  # same pages, charging wording
            t = i18n.translator(page_lang, charge=True)
        ctx["tabs"] = modules.vehicle_tabs(conn, nav_vid)
        from .nav_web import section_tabs

        ctx["section_tabs"] = ctx.get("section_tabs") or (section_tabs(conn, vehicle["id"], ctx.get("tab"), t) if vehicle else None)
        # the start page "/" is Home (also without a vehicle); every other page without a vehicle belongs to More
        current = (ctx.get("tab") or "more") if vehicle else ("overview" if request.url.path.rstrip("/") == "" else "more")
        ctx["nav_items"] = navigation.bar(conn, nav_vid, current)
        if ctx["energy_mode"] == "charge":  # the plug instead of the fuel pump
            for item in ctx["nav_items"]:
                if item["key"] == "fuel":
                    item["icon"] = "plug"
        more_href = f"/v/{nav_vid}/more" if nav_vid else "/more"
        ctx["setup_flow"] = request.url.path.startswith("/setup") or (
            request.url.path.rstrip("/") == "/vehicles/new" and not active
        )  # first-start pages: no navigation at all
        ctx["hide_nav"] = request.url.path.startswith(
            "/setup"
        )  # only the guide's own pages have no navigation; the first "Add vehicle" keeps it
        on_more = any(i["key"] == "more" and i["on"] for i in ctx["nav_items"]) and not ctx["hide_nav"]
        ctx["back_href"] = slugs.pretty(conn, more_href) if on_more and request.url.path.rstrip("/") not in ("/more", more_href) else None
        # a page that leads somewhere has a FIXED Back: from the page itself (back_to) or from BACK_RULES - never an address from the link (Home Assistant answers 400)
        if ctx.get("back_to"):
            ctx["back_href"] = slugs.pretty(conn, ctx["back_to"])
        else:
            for pattern, target in BACK_RULES:
                hit = re.fullmatch(pattern, request.url.path.rstrip("/"))
                if hit:
                    ctx["back_href"] = slugs.pretty(conn, hit.expand(target))
                    break
        ctx["back_deep"] = bool(ctx.get("back_href")) and ctx["back_href"] != slugs.pretty(
            conn, more_href
        )  # deeper than More: Back stays visible on wide screens
        ctx["nav_choices"] = navigation.choices()
        if on_more:  # wide screens: "More" is a second navigation next to the page
            from .nav_web import more_groups

            ctx["more_pane"] = more_groups(conn, nav_vid, t)
            ctx["more_cur"] = slugs.pretty(conn, request.url.path)
    ctx["app_car"] = app_car
    ctx["switch_vehicles"] = active if len(active) > 1 and not app_car else []  # a car's own web app shows that car only
    ctx["switch_suffix"] = _switch_suffix(request.url.path, on_more)
    ctx.update(
        nav=_nav_section(request.url.path),
        icons=icon_set.ICONS,
        module_icon={**icon_set.MODULE_ICON, "fuel": "plug"} if ctx.get("energy_mode") == "charge" else icon_set.MODULE_ICON,
        integration_icon=icon_set.INTEGRATION_ICON,
        base=request.state.base,
        units=units.of(ctx.get("v")),
        uof=units.of,
        _=t,
        lang=page_lang,
        languages=i18n.LANGUAGES,
        text_dir=i18n.LANGUAGES.get(page_lang, {}).get("dir", "ltr"),
        version=__version__,
        fdate=fdate,
        fshort=fshort,
        fnum=fnum,
        msg=request.query_params.get("m"),
        icon_base=f"{request.state.base}/v/{ctx['v']['slug'] or ctx['v']['id']}/icon" if ctx.get("v") else f"{request.state.base}/icon",
        manifest_url=f"{request.state.base}/v/{ctx['v']['slug'] or ctx['v']['id']}/manifest.webmanifest"
        if ctx.get("v")
        else f"{request.state.base}/manifest.webmanifest",
        icon_rev=appicon.revision(ctx["v"]["id"] if ctx.get("v") else None),
        logo_custom=appicon.has_custom(ctx["v"]["id"] if ctx.get("v") else None)
        or appicon.themed(ctx["v"]["id"] if ctx.get("v") else None),
        icon_rev_of=appicon.revision,
        has_icon=appicon.has_custom,
    )
    return templates.TemplateResponse(request, name, ctx, status_code=status)


def go(request: Request, path: str, msg: str | None = None) -> RedirectResponse:
    with db.tx() as conn:
        path = slugs.pretty(conn, path)  # /v/3/... -> /v/my-car/...
    path, hash_, anchor = path.partition("#")  # the message belongs before the anchor, or it would become part of it
    if msg:
        path += ("&" if "?" in path else "?") + "m=" + quote(msg)
    return RedirectResponse(f"{request.state.base}{path}{hash_}{anchor}", status_code=303)


def vehicle_or_404(conn: sqlite3.Connection, vid: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM vehicles WHERE id = ?", (vid,)).fetchone()
    if row is None:
        raise HTTPException(404)
    return row


async def form_dict(request: Request) -> dict[str, str]:
    form = await request.form()
    return {k: v for k, v in form.items() if isinstance(v, str)}


def vehicle_ctx(conn: sqlite3.Connection, vehicle: sqlite3.Row, tab: str) -> dict:
    return {"v": vehicle, "tab": tab, "odometer": summary.current_odometer(conn, vehicle["id"])}


def unit_for(fuel_type: str) -> str:
    return {"electric": "kWh", "cng": "kg"}.get(fuel_type, "L")


def clean_filename(name: str) -> str:
    name = Path(name or "file").name
    return re.sub(r"[^\w.\- ]", "_", name)[:120] or "file"


# ------------------------------------------------------------------ dashboard & vehicles


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/")
def index(request: Request):
    with db.tx() as conn:
        if db.get_setting(conn, "setup.language") != "1":  # first start: ask for the language first
            return RedirectResponse(f"{request.state.base}/setup/language", status_code=303)
        me = auth_web._acting_user(request, conn)
        mine = _app_car(request, conn)
        if mine:  # the web app of one car: never a car list
            return RedirectResponse(f"{request.state.base}/v/{mine['slug']}", status_code=303)
        wanted = userprefs.start_vehicle(conn, me["id"] if me else None)
        if wanted is not None:  # this user chose a car to start with
            return RedirectResponse(f"{request.state.base}{slugs.pretty(conn, '/v/' + str(wanted))}", status_code=303)
        only = conn.execute("SELECT id FROM vehicles WHERE archived = 0").fetchall()
        if len(only) == 1:  # one vehicle: no vehicle list, go straight to it
            return RedirectResponse(f"{request.state.base}{slugs.pretty(conn, '/v/' + str(only[0]['id']))}", status_code=303)
    return vehicle_list(request, manage=False)  # two or more cars: just choose one


@app.get("/vehicles")
def vehicle_list(request: Request, manage: bool = True):  # Weiteres -> Vehicles: add, restore, save, delete
    with db.tx() as conn:
        vehicles = conn.execute("SELECT * FROM vehicles ORDER BY archived, name COLLATE NOCASE").fetchall()
        cards = [summary.vehicle_summary(conn, v) for v in vehicles]
        for card in cards:
            card["has_tasks"] = (
                conn.execute("SELECT 1 FROM tasks WHERE vehicle_id = ? LIMIT 1", (card["vehicle"]["id"],)).fetchone() is not None
            )
    return render(
        request,
        "index.html",
        active=[c for c in cards if not c["vehicle"]["archived"]],
        archived=[c for c in cards if c["vehicle"]["archived"]],
        manage=manage or not any(not c["vehicle"]["archived"] for c in cards),  # no active car left: the full page again (add, reactivate)
    )


def _trip_duration(trip) -> str:
    """'1 h 05 min' / '42 min' from the start and end time of a trip, or '' when they are not both known."""
    if not trip or not trip["start_time"] or not trip["end_time"]:
        return ""
    try:
        start = int(trip["start_time"][:2]) * 60 + int(trip["start_time"][3:5])
        end = int(trip["end_time"][:2]) * 60 + int(trip["end_time"][3:5])
    except ValueError:
        return ""
    minutes = (end - start) % (24 * 60)
    return f"{minutes // 60} h {minutes % 60:02d} min" if minutes >= 60 else f"{minutes} min"


_NUMBER = re.compile(r"\s*(\d+(?:[.,]\d+)?)\s*([a-zA-Z\u00b3]*)\s*")
_HORSEPOWER = {"ps", "hp", "cv", "pk"}


def _number_with_unit(raw: str, units: set[str], label: str) -> tuple[float, str]:
    match = _NUMBER.fullmatch(raw)
    if not match or match.group(2).lower() not in units:
        raise FormError("err.number", label)
    return float(match.group(1).replace(",", ".")), match.group(2).lower()


def parse_power_kw(raw: str, label: str) -> int:
    """'110', '110 kW' or '150 PS' -> kW."""
    value, unit = _number_with_unit(raw, {"", "kw"} | _HORSEPOWER, label)
    kw = round(value / 1.35962) if unit in _HORSEPOWER else round(value)
    if not 0 < kw <= 2000:
        raise FormError("err.number", label)
    return kw


def parse_displacement(raw: str, label: str) -> int:
    """'1968', '1968 cm\u00b3', '1.968', '2.0' or '1,6 l' -> cm\u00b3 (a value up to 20 without a unit is read as litres)."""
    value, unit = _number_with_unit(raw, {"", "ccm", "cc", "cm3", "cm\u00b3", "l", "liter", "litre"}, label)
    ccm = round(value * 1000) if unit in {"l", "liter", "litre"} or (unit == "" and value <= 20) else round(value)
    if not 0 < ccm <= 20000:
        raise FormError("err.number", label)
    return ccm


def parse_build_date(raw: str, label: str) -> str:
    """ISO (what the date field sends) or 03.05.2020."""
    match = re.fullmatch(r"\s*(\d{1,2})\.(\d{1,2})\.(\d{4})\s*", raw)
    if match:
        raw = f"{match[3]}-{int(match[2]):02d}-{int(match[1]):02d}"
    return entities.parse_date(raw, label)


def parse_vehicle(form: dict[str, str]) -> dict:
    name = form.get("name", "").strip()
    if not name:
        raise FormError("err.required", "f.name")
    values: dict = {"name": name[:80]}
    for key in ("make", "model", "variant", "plate", "color", "notes"):
        text = (form.get(key) or "").strip()[:500]
        values[key] = None if text in ("", "-", "–", "—") else text  # a lone dash means "empty"
    try:
        values["vin"] = vin_info.clean(form.get("vin"))  # pasted with spaces or hyphens
    except ValueError:
        raise FormError("err.vin", "f.vin") from None
    year = (form.get("year") or "").strip()
    if year:
        if not year.isdigit() or not 1886 <= int(year) <= date.today().year + 1:
            raise FormError("err.year", "f.year")
        values["year"] = int(year)
    else:
        values["year"] = None
    fuel_type = form.get("fuel_type") or "petrol"
    if fuel_type not in entities.FUEL_TYPES:
        raise FormError("err.choice", "f.fuel_type")
    values["fuel_type"] = fuel_type
    tank = (form.get("tank_l") or "").strip()
    values["tank_l"] = entities.parse_float(tank, "f.tank") if tank else None
    kwh = (form.get("battery_kwh") or "").strip()
    values["battery_kwh"] = entities.parse_float(kwh, "f.battery_kwh") if kwh else None
    for key in ("model_type", "engine", "engine_code", "gearbox_code", "battery", "paint_code", "hsn", "tsn"):
        values[key] = (form.get(key) or "").strip()[:200] or None
    values["key_numbers"] = (form.get("key_numbers") or "").strip()[:2000] or None
    if "theme" in form:  # only the creation form and the Car tab send it: the passport form leaves the design alone
        chosen_theme = (form.get("theme") or "").strip()
        values["theme"] = chosen_theme if chosen_theme in themes.available() else None  # empty = like the system
    power = (form.get("power_kw") or "").strip()
    values["power_kw"] = parse_power_kw(power, "f.power_kw") if power else None
    displacement = (form.get("displacement_ccm") or "").strip()
    values["displacement_ccm"] = parse_displacement(displacement, "f.displacement") if displacement else None
    for key, options, label in (
        ("drivetrain", entities.DRIVETRAINS, "f.drivetrain"),
        ("transmission", entities.TRANSMISSIONS, "f.transmission"),
        ("body_type", entities.BODY_TYPES, "f.body_type"),
    ):
        choice = (form.get(key) or "").strip()
        if choice and choice not in options:
            raise FormError("err.choice", label)
        values[key] = choice or None
    build_date = (form.get("build_date") or "").strip()
    values["build_date"] = parse_build_date(build_date, "f.build_date") if build_date else None
    first_reg = (form.get("first_reg") or "").strip()
    values["first_reg"] = parse_build_date(first_reg, "f.first_reg") if first_reg else None
    values["oil_spec"] = (form.get("oil_spec") or "").strip()[:200] or None
    oil = (form.get("oil_l") or "").strip()
    values["oil_l"] = entities.parse_float(oil, "f.oil_l") if oil else None
    for key, low, high in (("seats", 1, 99), ("gross_weight_kg", 100, 99999)):
        raw = (form.get(key) or "").strip()
        if raw:
            if not raw.isdigit() or not low <= int(raw) <= high:
                raise FormError("err.number", "f." + key)
            values[key] = int(raw)
        else:
            values[key] = None
    chosen = (form.get("energy_mode") or "").strip()
    if chosen and chosen not in energy.MODES:
        raise FormError("err.choice", "f.energy_mode")
    values["energy_mode"] = chosen or None
    for key, label, high in (
        ("warn_pct", "f.warn_pct", 100),
        ("crit_pct", "f.crit_pct", 100),
        ("warn_range_km", "f.warn_range_km", 3000),
        ("crit_range_km", "f.crit_range_km", 3000),
    ):
        raw = (form.get(key) or "").strip()
        if raw and not raw.isdigit():
            raise FormError("err.number", label)
        number = int(raw) if raw else None
        if number is not None and key.endswith("_km"):
            number = round(units.of().from_d(number))  # typed in the units shown, stored in km
        if number is not None and not 0 < number <= high:
            raise FormError("err.number", label)
        values[key] = number
    values.update(parse_bindings(form))
    return values


BIND_KEYS = ("bind_odometer", "bind_fuel_level", "bind_range", "bind_tracker")


def parse_bindings(form: dict) -> dict:
    """The Home Assistant entities of a car (only the keys that were sent: the passport form does not send them)."""
    values: dict = {}
    for key in BIND_KEYS:
        if key not in form:
            continue
        raw = (form.get(key) or "").strip().lower()
        if raw and not ENTITY_ID.match(raw):
            raise FormError("err.entity", "f." + key)
        values[key] = raw or None
    return values


async def save_photo(conn: sqlite3.Connection, vid: int, upload) -> None:
    """The photo field of the vehicle form: goes into the vehicle's photo/video library (see media.py)."""
    if upload is None or not getattr(upload, "filename", ""):
        return
    try:
        await media.store(conn, vid, upload)
    except media.MediaError as exc:
        raise FormError(exc.args[0], "f.photo") from exc


def _shown_vehicle(vehicle: sqlite3.Row) -> dict:
    """The vehicle as the form shows it: distances in the units chosen in Settings -> Region."""
    values = dict(vehicle)
    for key in ("warn_range_km", "crit_range_km"):
        if values.get(key) is not None:
            values[key] = round(units.of().d(values[key]))
    return values


def _source_vehicles() -> tuple[list, bool]:
    with db.tx() as conn:
        return sources.available_vehicles(conn), sources.demo_offered(conn)


def vehicle_form_page(request: Request, vehicle: sqlite3.Row | None, form: dict | None = None, error=None, status: int = 200):
    odometer = None
    if vehicle is not None:
        with db.tx() as conn:
            odometer = summary.current_odometer(conn, vehicle["id"])
    return render(
        request,
        "vehicle_form.html",
        status=status,
        vehicle=vehicle,
        form=form or (_shown_vehicle(vehicle) if vehicle else {"fuel_type": "petrol"}),
        error=error,
        fuel_types=entities.FUEL_TYPES,
        drivetrains=entities.DRIVETRAINS,
        transmissions=entities.TRANSMISSIONS,
        body_types=entities.BODY_TYPES,
        tab="edit" if vehicle else None,
        v=vehicle,
        odometer=odometer,
        open_group=re.sub(r"[^a-z]", "", request.query_params.get("open", ""))[:12],
        source_vehicles=_source_vehicles()[0],
        demo_offered=_source_vehicles()[1],
    )


@app.get("/vehicles/new")
def vehicle_new(request: Request):
    return vehicle_form_page(request, None)


@app.post("/vehicles")
async def vehicle_create(request: Request):
    raw = await request.form()
    form = {k: v for k, v in raw.items() if isinstance(v, str)}
    try:
        values = parse_vehicle(form)
        with db.tx() as conn:
            cols = list(values)
            vid = conn.execute(
                f"INSERT INTO vehicles ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                list(values.values()),
            ).lastrowid
            conn.execute("UPDATE vehicles SET slug = ? WHERE id = ?", (slugs.unique(conn, values["name"], vid), vid))
            if form.get("recommended") == "1":  # the creation page asks for the recommended set of functions
                modules.apply_recommended(conn, vid)
            await save_photo(conn, vid, raw.get("photo"))
            km = (form.get("odometer") or "").strip()
            if km:
                summary.add_odometer(conn, vid, round(units.of().from_d(entities.parse_float(km, "f.odometer"))))
    except FormError as exc:
        return vehicle_form_page(request, None, form, exc.args, 400)
    events.changed()
    return after_vehicle_created(request, vid)


def after_vehicle_created(request: Request, vid: int):
    with db.tx() as conn:
        first_run = (
            auth_web.setup_pending(conn)
            and not accounts.has_users(conn)
            and conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0] == 1
        )
    if first_run:  # first car created: ask how the UI will be used (only in Home Assistant, or also from outside with a login)
        return go(request, "/setup/functions")  # step 3 of the guide; then the access step; after setup "/" leads to the only vehicle
    return go(request, f"/v/{vid}", "saved")


@app.get("/v/{vid}/live-state")
def live_state(request: Request, vid: int):
    """A short fingerprint of the live values; the page of a demo car polls it and reloads when it changes."""
    import hashlib

    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        rows = conn.execute("SELECT key, value FROM live WHERE vehicle_id = ? ORDER BY key", (vid,)).fetchall()
        odo = summary.current_odometer(conn, vid)
    raw = repr([(r["key"], r["value"]) for r in rows]) + str(odo)
    return JSONResponse({"v": hashlib.sha1(raw.encode()).hexdigest()[:12]})  # noqa: S324 (a change marker, not security)


def _week_km(conn: sqlite3.Connection, vid: int) -> tuple[list[tuple[str, float]], float]:
    """Kilometres of the trips of the last seven days (oldest first, with the short weekday) and their sum, for the trips widget."""
    today = date.today()
    days = [today - timedelta(days=n) for n in range(6, -1, -1)]
    per_day = {d.isoformat(): 0.0 for d in days}
    for r in conn.execute(
        "SELECT date, distance_km, start_km, end_km FROM trips WHERE vehicle_id = ? AND date >= ?", (vid, days[0].isoformat())
    ):
        km = r["distance_km"] if r["distance_km"] else ((r["end_km"] or 0) - (r["start_km"] or 0))
        if r["date"][:10] in per_day and km and km > 0:
            per_day[r["date"][:10]] += float(km)
    rows = [(d.strftime("%a"), per_day[d.isoformat()]) for d in days]
    return rows, sum(per_day.values())


@app.get("/v/{vid}")
def vehicle_overview(request: Request, vid: int):
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        s = summary.vehicle_summary(conn, vehicle)
        hero_media = media.active(conn, vid)
        recent_service = conn.execute("SELECT * FROM service WHERE vehicle_id = ? ORDER BY date DESC, id DESC LIMIT 5", (vid,)).fetchall()
        stats = fuelstats.overall(conn, vid)
        upcoming = conn.execute("SELECT * FROM appointments WHERE vehicle_id = ? AND done = 0 ORDER BY due_date LIMIT 5", (vid,)).fetchall()
        upcoming_info = {r["id"]: summary.appointment_due(r) for r in upcoming}
        last_trip = conn.execute(
            "SELECT date, distance_km, start_km, end_km, start_time, end_time FROM trips WHERE vehicle_id = ? ORDER BY date DESC, id DESC LIMIT 1",
            (vid,),
        ).fetchone()
        last_fuel = conn.execute(
            "SELECT date, amount, odometer_km, price_total FROM fuel WHERE vehicle_id = ? ORDER BY date DESC, id DESC LIMIT 1", (vid,)
        ).fetchone()
        has_tasks = conn.execute("SELECT 1 FROM tasks WHERE vehicle_id = ? LIMIT 1", (vid,)).fetchone() is not None
        odo_next = summary.next_service_km(conn, vid, s["odometer"])
        from . import reminders as _rem

        reminders = _rem.status(conn, vid)
        trip_time = _trip_duration(last_trip)
        spark_cons = charts.spark_svg([v for _d, v in fuelstats.consumption_series(conn, vid)][-10:])
        spark_price = charts.spark_svg([v for _d, v in fuelstats.price_series(conn, vid)][-10:])
        week_rows, week_km = _week_km(conn, vid)
        week_bars = charts.mini_bars_svg([(label, units.of().d(km)) for label, km in week_rows])
        cons_delta = (stats["last_per_100"] - stats["avg_per_100"]) if stats.get("last_per_100") and stats.get("avg_per_100") else None
        live_rows = vehicle_status.rows(conn, vid)
        t = i18n.translator(config.language(), charge=energy.mode(vehicle) == "charge")
        hero = vehicle_status.hero_range(
            live_rows,
            t,
            vehicle["battery_kwh"] if vehicle["fuel_type"] == "electric" else vehicle["tank_l"],
            unit_for(vehicle["fuel_type"]),
            energy.mode(vehicle),
        )
        tank_info = vehicle_status.tank(
            live_rows, vehicle["battery_kwh"] if vehicle["fuel_type"] == "electric" else vehicle["tank_l"], energy.mode(vehicle)
        )
        if not hero and (est := fuelstats.estimate_range(conn, vehicle)):
            hero = {"km": est["km"], "pct": None, "liters": None, "unit": unit_for(vehicle["fuel_type"]), "when": None, "estimated": True}
        if hero:
            hero["state"] = energy.state(vehicle, hero["pct"], hero["km"])
        return render(
            request,
            "vehicle.html",
            odo_next=odo_next,
            reminders=reminders,
            tile_values=home_widgets.tile_values(conn, vid),
            trip_time=trip_time,
            spark_cons=spark_cons,
            spark_price=spark_price,
            week_bars=week_bars,
            week_km=week_km,
            cons_delta=cons_delta,
            hero_badges=vehicle_status.hero_badges(live_rows, t),
            widgets=home_widgets.layout(conn, vid),
            hero_range=hero,
            tank_info=tank_info,
            tank_unit=unit_for(vehicle["fuel_type"]),
            hero_media=hero_media,
            **{f"media_{k}": val for k, val in media.panel(conn, vid).items()},
            fresh_ago=vehicle_status.freshness(live_rows, t),
            closure_open=len(vehicle_status.open_closures(live_rows)) + len(vehicle_status.car_messages(live_rows, t)),
            car_warnings=vehicle_status.car_messages(live_rows, t),
            car_data=vehicle_status.car_data(live_rows, t, unit_for(vehicle["fuel_type"])),
            place=_place_with_names(conn, vehicle_status.location(live_rows, t)),
            map_tiles=vehicle_status.map_tiles_enabled(conn),
            last_trip=last_trip,
            last_fuel=last_fuel,
            has_tasks=has_tasks,
            **vehicle_ctx(conn, vehicle, "overview"),
            s=s,
            recent_service=recent_service,
            stats=stats,
            upcoming=upcoming,
            upcoming_info=upcoming_info,
            unit=unit_for(vehicle["fuel_type"]),
        )


@app.post("/v/{vid}/odometer")
async def odometer_add(request: Request, vid: int):
    form = await form_dict(request)
    try:
        km = int(entities.parse_float(form.get("odometer_km", ""), "f.odometer"))
        when = entities.parse_date(form["date"], "f.date") if form.get("date") else None
    except FormError as exc:
        return go(request, f"/v/{vid}", exc.args[0])
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        summary.add_odometer(conn, vid, km, when)
    events.changed()
    return go(request, f"/v/{vid}", "saved")


@app.get("/v/{vid}/edit")
def vehicle_edit(request: Request, vid: int):
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        if request.query_params.get("mode") == "form":
            return vehicle_form_page(request, vehicle)
        row = conn.execute("SELECT source FROM odometer WHERE vehicle_id = ? ORDER BY date DESC, id DESC LIMIT 1", (vid,)).fetchone()
        return render(
            request,
            "vehicle_data.html",
            v=vehicle,
            tab="edit",
            hide_hero=True,  # the page has its own hero card
            odometer=summary.current_odometer(conn, vid),
            odo_from_car=bool(row and row["source"] != "manual"),
            vin_year=None if vehicle["year"] else vin_info.model_year(vehicle["vin"]),
            insp_estimate=None if summary.next_inspection(conn, vid) else _iso(summary.inspection_estimate(vehicle["first_reg"])),
            equip=equipment.groups(conn, vid, config.language()),
            equip_status=equipment.STATUSES,
            picker_icons=icon_set.PICKER_ICONS,
        )


@app.post("/v/{vid}/edit")
async def vehicle_update(request: Request, vid: int):
    raw = await request.form()
    form = {k: v for k, v in raw.items() if isinstance(v, str)}
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        try:
            values = parse_vehicle(form)
            values["vin_verified"] = (
                vehicle["vin_verified"] if values["vin"] == vehicle["vin"] else 0
            )  # another VIN: the car has not confirmed it yet
            sets = ", ".join(f"{k} = ?" for k in values)
            conn.execute(f"UPDATE vehicles SET {sets} WHERE id = ?", [*values.values(), vid])
            new_slug = slugs.unique(conn, values["name"], vid)
            conn.execute("UPDATE vehicles SET slug = ? WHERE id = ?", (new_slug, vid))
            await save_photo(conn, vid, raw.get("photo"))
        except FormError as exc:
            return vehicle_form_page(request, vehicle, form, exc.args, 400)
    events.changed()
    return go(
        request, f"/v/{new_slug}/edit", "saved"
    )  # every Save of the form saves everything that changed - and the page falls back to the passport


def _car_tab(vehicle, anchor: str = "") -> str:
    return f"/settings/car?car={vehicle['slug'] or vehicle['id']}{'#' + anchor if anchor else ''}"


@app.post("/v/{vid}/theme")
async def vehicle_theme(request: Request, vid: int):
    """The design of ONE car (empty = like the system); chosen on the Car tab of the settings."""
    form = await form_dict(request)
    choice = form.get("theme", "")
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        conn.execute("UPDATE vehicles SET theme = ? WHERE id = ?", (choice if choice in themes.available() else None, vid))
    return go(request, _car_tab(vehicle, "theme"), "saved")


@app.post("/v/{vid}/accent")
async def vehicle_accent(request: Request, vid: int):
    """The colour of the car's design "with your own colour" (applies at once, no Save - like the one of the system)."""
    form = await form_dict(request)
    color = themes.clean_accent(form.get("accent"))
    if color is None:
        raise HTTPException(400)
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        conn.execute("UPDATE vehicles SET accent = ? WHERE id = ?", (color, vid))
    if form.get("ajax"):
        return Response(status_code=204)
    return go(request, _car_tab(vehicle, "theme"), "saved")


@app.post("/v/{vid}/bindings")
async def vehicle_bindings(request: Request, vid: int):
    """The Home Assistant entities of ONE car (Car tab): only these four values are touched."""
    form = await form_dict(request)
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        try:
            values = parse_bindings({key: form.get(key, "") for key in BIND_KEYS})
        except FormError as exc:
            return go(request, _car_tab(vehicle, "ha"), exc.args[0])
        sets = ", ".join(f"{k} = ?" for k in values)
        conn.execute(f"UPDATE vehicles SET {sets} WHERE id = ?", [*values.values(), vid])
    events.changed()
    return go(request, _car_tab(vehicle, "ha"), "saved")


@app.post("/v/{vid}/archive")
def vehicle_archive(request: Request, vid: int):
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        conn.execute("UPDATE vehicles SET archived = ? WHERE id = ?", (0 if vehicle["archived"] else 1, vid))
    events.changed()
    return go(request, "/", "saved")


@app.post("/v/{vid}/delete")
def vehicle_delete(request: Request, vid: int):
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        conn.execute("DELETE FROM vehicles WHERE id = ?", (vid,))
        conn.execute(
            "DELETE FROM user_notify_vehicle WHERE vehicle_id = ?", (vid,)
        )  # the car disappears from everybody's notification matrix
    import shutil

    shutil.rmtree(config.files_dir() / str(vid), ignore_errors=True)
    shutil.rmtree(config.files_dir() / "media" / str(vid), ignore_errors=True)
    for photo in (config.files_dir() / "photos").glob(f"{vid}.*"):
        photo.unlink(missing_ok=True)
    appicon.reset(vid)
    publisher.remove_vehicle(vid)
    return go(request, "/", "deleted")


@app.get("/v/{vid}/photo")
def vehicle_photo(vid: int):
    """The still picture of a car (lists, switcher, fallback while a video loads)."""
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        row = media.photo_row(conn, vid)
    if row is None:
        raise HTTPException(404)
    path = media.path_of(vid, row)
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type=row["mime"], headers={"Cache-Control": "private, max-age=3600"})


# ------------------------------------------------------------------ icons and web-app manifest


def _icon_response(vid: int | None, size: int, kind: str = "any") -> FileResponse:
    try:
        path = appicon.variant(vid, size, kind)
    except KeyError:
        raise HTTPException(404) from None
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})


@app.get("/favicon.ico")
def favicon_ico():
    return Response(appicon.favicon_ico(), media_type="image/x-icon", headers={"Cache-Control": "no-cache"})


@app.get("/icon/maskable-{size}.png")
def app_icon_maskable(size: int):
    return _icon_response(None, size, "maskable")


@app.get("/icon/{size}.png")
def app_icon(size: int):
    return _icon_response(None, size)


@app.get("/apple-touch-icon.png")
@app.get("/apple-touch-icon-precomposed.png")
def apple_touch_icon_root():
    """iOS asks for these two addresses on its own (home screen, some in-app browsers) when it finds no link."""
    return _icon_response(None, 180)


@app.get("/v/{vid}/icon/maskable-{size}.png")
def vehicle_icon_maskable(vid: int, size: int):
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
    return _icon_response(vid, size, "maskable")


@app.get("/v/{vid}/icon/{size}.png")
def vehicle_icon(vid: int, size: int):
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
    return _icon_response(vid, size)


def _manifest(request: Request, vid: int | None, name: str) -> JSONResponse:
    """The system and every car are web apps of their own: own name, icon and colours. A car starts at /app/<car> (that shows only this car)."""
    base = request.state.base
    with db.tx() as conn:
        row = conn.execute("SELECT slug, theme FROM vehicles WHERE id = ?", (vid,)).fetchone() if vid is not None else None
        chosen = (row["theme"] if row and row["theme"] in themes.available() else None) or themes.current(conn)
        label = (row["slug"] if row and row["slug"] else vid) if vid is not None else ""
    prefix = f"{base}/v/{label}" if vid is not None else f"{base}"
    rev = appicon.revision(vid)
    background = themes.meta(chosen)[1]
    return JSONResponse(
        {
            "id": f"{base}/app/{label}" if vid is not None else f"{base}/",
            "name": name,
            "short_name": name[:14],  # "Car Assistant" has 13 letters: nothing may be cut off
            "start_url": f"{base}/app/{label}" if vid is not None else f"{prefix}/",
            "scope": f"{base}/",  # the whole app: a link to More or the settings must not open the phone's little in-app browser
            "display": "standalone",
            "background_color": background,
            "theme_color": background,
            "icons": [
                {
                    "src": f"{prefix}/icon/{'maskable-' if purpose == 'maskable' else ''}{size}.png?v={rev}",
                    "sizes": f"{size}x{size}",
                    "type": "image/png",
                    "purpose": purpose,
                }
                for purpose in ("any", "maskable")
                for size in (192, 512)
            ],
        },
        media_type="application/manifest+json",
    )


@app.get("/manifest.webmanifest")
def app_manifest(request: Request):
    return _manifest(request, None, "Car Assistant")


@app.get("/v/{vid}/manifest.webmanifest")
def vehicle_manifest(request: Request, vid: int):
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
    return _manifest(request, vid, vehicle["name"])


@app.get("/app/{token}")
def car_app(request: Request, token: str):
    """The start address of one car's web app: remembers on this device that only this car is shown, then opens the car."""
    with db.tx() as conn:
        vid = slugs.id_for(conn, token)
        row = conn.execute("SELECT slug, archived FROM vehicles WHERE id = ?", (vid,)).fetchone() if vid else None
    if not row or row["archived"] or not row["slug"]:
        raise HTTPException(404)
    response = vehicle_overview(request, vid)  # no redirect: the address stays /app/<car>, so "Add to Home Screen" keeps exactly this one
    response.set_cookie(
        APP_COOKIE, row["slug"], max_age=365 * 86400, httponly=True, samesite="lax", secure=request.url.scheme == "https", path="/"
    )
    return response


@app.get("/app-all")
def car_app_all(request: Request):
    """Back to all cars on this device."""
    response = RedirectResponse(f"{request.state.base}/", status_code=303)
    response.delete_cookie(APP_COOKIE, path="/")
    return response


async def _store_icon(request: Request, vid: int) -> RedirectResponse:
    form = await request.form()
    upload = form.get("icon")
    back = str(form.get("back", ""))
    back = (
        back if re.fullmatch(r"/[A-Za-z0-9_./\-?=&#]*", back) and not back.startswith("//") else "/settings/system"
    )  # only a page of this app
    if upload is None or not getattr(upload, "filename", ""):
        return go(request, back, "err.required")
    try:
        appicon.save_custom(await upload.read(appicon.MAX_BYTES + 1), vid)
    except appicon.IconError as exc:
        return go(request, back, exc.args[0])
    return go(request, back, "icon_saved")


@app.post("/v/{vid}/icon")
async def vehicle_icon_upload(request: Request, vid: int):
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
    return await _store_icon(request, vid)


@app.post("/v/{vid}/icon/reset")
async def vehicle_icon_reset(request: Request, vid: int):
    form = await request.form()
    back = str(form.get("back", ""))
    back = back if re.fullmatch(r"/[A-Za-z0-9_./\-?=&#]*", back) and not back.startswith("//") else "/settings/system"
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
    appicon.reset(vid)
    return go(request, back, "icon_reset")


# ------------------------------------------------------------------ generic record lists


def entity_context(
    conn: sqlite3.Connection, vehicle: sqlite3.Row, entity: entities.Entity, page: int = 1, edit_id: int | None = None
) -> dict:
    total = entities.count(conn, entity, vehicle["id"])
    pages = max(1, -(-total // lists.size()))
    page = min(max(page, 1), pages)
    rows = entities.rows(conn, entity, vehicle["id"], page, edit_id)
    odo = summary.current_odometer(conn, vehicle["id"])
    extras: dict[int, dict] = {}
    if entity.key == "appointments":
        for r in rows:
            extras[r["id"]] = {"due": summary.appointment_due(r) if not r["done"] else None}
    elif entity.key == "tasks":
        book = summary.service_index(conn, vehicle["id"])
        for r in rows:
            last_date, last_km = summary.task_last(conn, vehicle["id"], r, book)
            extras[r["id"]] = {"due": summary.task_due(conn, vehicle["id"], r, odo, index=book), "last_date": last_date, "last_km": last_km}
    elif entity.key == "trips":
        for r in rows:
            extras[r["id"]] = {"distance": trips.trip_distance(r)}
    elif entity.key == "counters":
        for r in rows:
            end = r["end_km"] if r["end_km"] is not None else odo
            extras[r["id"]] = {"distance": (end - r["start_km"]) if end is not None else None}
    group_field = {"service": "date", "parts": "date"}.get(entity.key)  # lists with a date get a heading per period (Today, Yesterday, ...)
    items = (
        lists.with_headings(rows, group_field, entities.previous_date(conn, entity, vehicle["id"], page, group_field), config.language())
        if group_field
        else [(None, r) for r in rows]
    )
    return {
        "entity": entity,
        "rows": rows,
        "items": items,
        "extras": extras,
        "unit": unit_for(vehicle["fuel_type"]),
        "pager": {"page": page, "pages": pages, "total": total, "size": lists.size()},
    }


def entity_page(request: Request, vid: int, key: str, form: dict | None = None, error=None, edit_id: int | None = None, status: int = 200):
    entity = ENTITIES.get(key)
    if entity is None:
        raise HTTPException(404)
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        page = request.query_params.get("page", "1")
        ctx = entity_context(conn, vehicle, entity, int(page) if page.isdigit() else 1, edit_id)
        ctx.update(vehicle_ctx(conn, vehicle, key))
        extra: dict = {}
        if key == "tires":
            tp_edit = bool(request.query_params.get("edit")) or bool(form) or edit_id is not None
            extra["tp"] = tire_pressure_context(conn, vid, request.query_params.get("ps"), ctx["rows"], tp_edit)
            extra["tp_edit"] = tp_edit
        if key == "trips":
            start, end = trips.parse_range(request.query_params.get("from"), request.query_params.get("to"))
            extra.update(range_from=start, range_to=end)
            odo = summary.current_odometer(conn, vid)
            counters = [
                dict(r) for r in conn.execute("SELECT * FROM counters WHERE vehicle_id = ? ORDER BY start_date DESC, id DESC", (vid,))
            ]
            for c in counters:
                end_km = c["end_km"] if c["end_km"] is not None else odo
                c["driven"] = (end_km - c["start_km"]) if end_km is not None else None
            got = paged_list(conn, vid, request, "trips", ("start_place", "end_place", "purpose", "date"), "date DESC, id DESC")
            ctx["pager"] = got["pager"]
            recent = trips.trips_in_range(conn, vid, (date.today() - timedelta(days=29)).isoformat(), date.today().isoformat())
            kpis = {"n": len(recent), "km": sum(trips.trip_distance(r) or 0 for r in recent), "minutes": 0}
            for r in recent:
                a, b = (r["start_time"] or ""), (r["end_time"] or "")
                if ":" in a and ":" in b:
                    gap = int(b[:2]) * 60 + int(b[3:5]) - (int(a[:2]) * 60 + int(a[3:5]))
                    kpis["minutes"] += gap if gap > 0 else 0
            extra["kpis"] = kpis
            period = request.query_params.get("ap", "")
            period = period if period in tripstats.PERIODS else tripstats.DEFAULT_PERIOD
            extra.update(
                ta=tripstats.analyse(conn, vid, period, units.of(vehicle).d),
                ta_period=period,
                ta_periods=tuple(tripstats.PERIODS),
                ta_labels=tripstats.length_labels(),
            )
            ctx["extras"] = {r["id"]: {"distance": trips.trip_distance(r)} for r in got["rows"]}
            extra.update(
                trip_items=got["items"],
                total_rows=got["total"],
                q=got["q"],
                counters=counters,
                counter_entity=ENTITIES["counters"],
                counter_kinds=entities.COUNTER_KINDS,
                trip_categories=entities.TRIP_CATEGORIES,
                map_tiles=vehicle_status.map_tiles_enabled(conn),
                has_points={
                    r[0]
                    for r in conn.execute(
                        "SELECT DISTINCT trip_id FROM trip_points WHERE trip_id IN (SELECT id FROM trips WHERE vehicle_id = ?)", (vid,)
                    )
                },
            )
            return render(request, "trips_page.html", status=status, form=form or {}, error=error, edit_id=edit_id, **ctx, **extra)
        if key == "tasks":
            odo = summary.current_odometer(conn, vid)
            book = summary.service_index(conn, vid)
            cards = []
            for r in conn.execute("SELECT * FROM tasks WHERE vehicle_id = ? ORDER BY title COLLATE NOCASE", (vid,)):
                last_date, last_km = summary.task_last(conn, vid, r, book)
                due = summary.task_due(conn, vid, r, odo, index=book)
                parts = []
                if r["interval_km"] and last_km is not None and odo is not None:
                    parts.append((odo - last_km) / r["interval_km"])
                if r["interval_months"] and last_date:
                    parts.append((date.today() - date.fromisoformat(last_date)).days / (r["interval_months"] * 30.44))
                cards.append(
                    {
                        "row": r,
                        "due": due,
                        "last_date": last_date,
                        "last_km": last_km,
                        "pct": round(min(max(max(parts), 0), 1) * 100) if parts else None,
                    }
                )
            odo_row = conn.execute(
                "SELECT date, source FROM odometer WHERE vehicle_id = ? ORDER BY date DESC, id DESC LIMIT 1", (vid,)
            ).fetchone()
            return render(
                request,
                "tasks_page.html",
                status=status,
                form=form or {},
                error=error,
                edit_id=edit_id,
                **ctx,
                cards=cards,
                odo_row=odo_row,
                n_ok=sum(1 for c in cards if c["due"].status in ("ok", "unknown")),
                n_open=sum(1 for c in cards if c["due"].status in ("soon", "overdue")),
                templates_left=[
                    t
                    for t in entities.TASK_TEMPLATES
                    if not conn.execute("SELECT 1 FROM tasks WHERE vehicle_id = ? AND title = ?", (vid, t[0])).fetchone()
                ],
            )
        if key == "mods":
            all_rows = conn.execute("SELECT * FROM mods WHERE vehicle_id = ? ORDER BY date DESC, id DESC LIMIT 2000", (vid,)).fetchall()
            return render(
                request,
                "mods_page.html",
                status=status,
                form=form or {},
                error=error,
                edit_id=edit_id,
                **ctx,
                rows_all=all_rows,
                today=date.today().isoformat(),
            )
        if key == "fuel":
            if vehicle["fuel_type"] != "electric":
                extra["stn"] = station_context(request, vehicle)  # the fuel stations are part of this page now
                extra["fs_pref"] = stations.preferred_source()
            from . import reminders as _rem

            extra["reminders"] = _rem.status(conn, vid)
            ctx.update(fuel_list_context(conn, vid, request))  # replaces the generic list's rows and pager
            return render(request, "fuel_page.html", status=status, form=form or {}, error=error, edit_id=edit_id, **ctx, **extra)
        return render(request, "entity.html", status=status, form=form or {}, error=error, edit_id=edit_id, **ctx, **extra)


def paged_list(conn: sqlite3.Connection, vid: int, request: Request, table: str, search: tuple[str, ...], order: str) -> dict:
    """One batch of records of a car (the batch size is the person's choice): rows, a heading wherever the period changes, the searched text and the
    pager. ``table``, ``search`` and ``order`` are fixed text of the callers, never input."""
    q = (request.query_params.get("q") or "").strip()[:60]
    where, args = "vehicle_id = ?", [vid]
    if q:
        where += " AND (" + " OR ".join(f"COALESCE({c}, '') LIKE ?" for c in search) + ")"
        args += [f"%{q}%"] * len(search)
    total = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", args).fetchone()[0]
    size = lists.size()
    pages = max(1, -(-total // size))
    asked = request.query_params.get("page", "1")
    page = min(max(int(asked) if asked.isdigit() else 1, 1), pages)
    rows = conn.execute(
        f"SELECT * FROM {table} WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?", [*args, size, (page - 1) * size]
    ).fetchall()
    previous = None
    if page > 1:
        row = conn.execute(
            f"SELECT date FROM {table} WHERE {where} ORDER BY {order} LIMIT 1 OFFSET ?", [*args, (page - 1) * size - 1]
        ).fetchone()
        previous = row["date"] if row else None
    return {
        "items": lists.with_headings(rows, "date", previous, config.language()),
        "rows": rows,
        "total": total,
        "q": q,
        "pager": {"page": page, "pages": pages, "total": total, "size": size},
    }


def fuel_list_context(conn: sqlite3.Connection, vid: int, request: Request) -> dict:
    got = paged_list(conn, vid, request, "fuel", ("station", "notes", "date"), "date DESC, COALESCE(odometer_km, 0) DESC, id DESC")
    from . import charge_detect, refuel_detect

    return {
        "charge_sessions": charge_detect.sessions(conn, vid),
        "charge_stats": charge_detect.stats(conn, vid),
        "fuel_items": got["items"],
        "total_rows": got["total"],
        "q": got["q"],
        "pager": got["pager"],
        "refuel_todo": refuel_detect.todo(conn, vid),
    }


def tire_pressure_context(conn: sqlite3.Connection, vid: int, chosen: str | None, rows, edit: bool = False) -> dict:
    """Recommended pressures per season (tabs) and the last pressures a plugin reported (None = no plugin offers them)."""
    shown = units.of()
    saved = {r["season"]: r for r in conn.execute("SELECT * FROM tire_pressure WHERE vehicle_id = ?", (vid,))}
    seasons = ("summer", "winter", "allseason")
    has_pressure = {s: any(saved[s][k] is not None for k in ("front_bar", "rear_bar", "load_front_bar", "load_rear_bar")) for s in saved}
    present = [s for s in seasons if has_pressure.get(s) or any(r["season"] == s for r in rows)]
    mounted_season = next((r["season"] for r in rows if r["mounted"]), None)
    if chosen not in seasons:
        chosen = "summer"  # the page always opens on the summer tab

    def show(bar):
        return None if bar is None else f"{round(shown.p(bar), 1):g}"

    row = saved.get(chosen)
    every = {
        sn: {
            "front": show(saved[sn]["front_bar"]) if sn in saved else None,
            "rear": show(saved[sn]["rear_bar"]) if sn in saved else None,
            "load_front": show(saved[sn]["load_front_bar"]) if sn in saved else None,
            "load_rear": show(saved[sn]["load_rear_bar"]) if sn in saved else None,
        }
        for sn in seasons
    }
    live = conn.execute("SELECT value, updated FROM live WHERE vehicle_id = ? AND key = 'tyre_pressure_bar'", (vid,)).fetchone()
    actual = status.parse_numbers(live["value"]) if live else {}
    return {
        "seasons": seasons,
        "present": present,
        "season": chosen,
        "mounted_season": mounted_season,
        "every": every,
        "set": has_pressure,
        "front": show(row["front_bar"]) if row else None,
        "rear": show(row["rear_bar"]) if row else None,
        "load_front": show(row["load_front_bar"]) if row else None,
        "load_rear": show(row["load_rear_bar"]) if row else None,
        "actual": {w: show(actual[w]) if w in actual else None for w in ("fl", "fr", "rl", "rr")},
        "actual_when": live["updated"] if live and actual else None,
        "unit": shown.press_unit,
    }


@app.get("/v/{vid}/e/{key}")
def entity_list(request: Request, vid: int, key: str):
    if key == "counters":  # the km counters live on the trips page now
        with db.tx() as conn:
            slug = vehicle_or_404(conn, vid)["slug"]
        return RedirectResponse(f"{request.state.base}/v/{slug}/e/trips#counters", status_code=303)
    if key == "trips":
        with db.tx() as conn:
            trips.from_track(conn, vid)  # a drive that has ended since the last visit becomes a trip now
        from . import places

        places.kick()
    return entity_page(request, vid, key)


def _save_pressure(conn: sqlite3.Connection, vid: int, season: str, texts: dict) -> None:
    """Recommended pressures of one season (front / rear axle, normal and fully loaded), typed in the shown unit, stored in bar. Empty = removed."""
    shown = units.of()
    values = []
    for name in ("front", "rear", "load_front", "load_rear"):
        try:
            number = float((texts.get(name) or "").replace(",", "."))
        except ValueError:
            number = None
        bar = shown.from_p(number) if number is not None else None
        values.append(round(bar, 2) if bar is not None and 0.5 <= bar <= 8 else None)
    if not any(v is not None for v in values):
        conn.execute("DELETE FROM tire_pressure WHERE vehicle_id = ? AND season = ?", (vid, season))
    else:
        conn.execute(
            "INSERT INTO tire_pressure(vehicle_id, season, front_bar, rear_bar, load_front_bar, load_rear_bar) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(vehicle_id, season) DO UPDATE SET front_bar = excluded.front_bar, rear_bar = excluded.rear_bar, "
            "load_front_bar = excluded.load_front_bar, load_rear_bar = excluded.load_rear_bar",
            (vid, season, *values),
        )


def _mount_tire(conn: sqlite3.Connection, vid: int, row_id: int) -> None:
    odo = summary.current_odometer(conn, vid)
    conn.execute("UPDATE tires SET mounted = 0 WHERE vehicle_id = ?", (vid,))
    conn.execute(
        "UPDATE tires SET mounted = 1, mounted_date = ?, mounted_km = ? WHERE id = ? AND vehicle_id = ?",
        (date.today().isoformat(), odo, row_id, vid),
    )


@app.post("/v/{vid}/e/tires/pressure")
async def tire_pressure_save(request: Request, vid: int):
    form = await form_dict(request)
    season = form.get("season", "")
    if season not in ("summer", "winter", "allseason"):
        raise HTTPException(400)
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        _save_pressure(conn, vid, season, form)
    return go(request, f"/v/{vid}/e/tires?ps={season}", "saved")


_TIRE_FIELDS = ("name", "size", "rear_size", "storage", "notes")


@app.post("/v/{vid}/e/tires/save")
async def tire_save_all(request: Request, vid: int):
    """The one Save of the tyre edit page: the pressures and the sets of all three seasons, which set is mounted, sets to remove."""
    form = await form_dict(request)
    shown = form.get("view", "")
    shown = shown if shown in ("summer", "winter", "allseason") else "summer"
    try:
        with db.tx() as conn:
            vehicle_or_404(conn, vid)
            for season in ("summer", "winter", "allseason"):
                _save_pressure(
                    conn, vid, season, {n: form.get(f"p_{season}_{n}", "") for n in ("front", "rear", "load_front", "load_rear")}
                )
                fresh = {n: form.get(f"n_{season}_{n}", "") for n in _TIRE_FIELDS}
                if any(v.strip() for v in fresh.values()):
                    fresh["name"] = fresh["name"].strip() or i18n.translator(config.language())(f"season.{season}")
                    entities.insert(conn, ENTITIES["tires"], vid, entities.parse_form(ENTITIES["tires"], {**fresh, "season": season}))
            for row in conn.execute("SELECT id, season FROM tires WHERE vehicle_id = ?", (vid,)).fetchall():
                key = f"t{row['id']}_"
                if form.get(key + "del") == "1":
                    entities.delete(conn, ENTITIES["tires"], vid, row["id"])
                elif key + "name" in form:
                    given = {**{n: form.get(key + n, "") for n in _TIRE_FIELDS}, "season": row["season"]}
                    entities.update(conn, ENTITIES["tires"], vid, row["id"], entities.parse_form(ENTITIES["tires"], given))
            chosen = form.get("mounted", "")
            if chosen.isdigit():
                current = conn.execute("SELECT id FROM tires WHERE vehicle_id = ? AND mounted = 1", (vid,)).fetchone()
                if conn.execute("SELECT 1 FROM tires WHERE id = ? AND vehicle_id = ?", (int(chosen), vid)).fetchone() and (
                    current is None or current["id"] != int(chosen)
                ):
                    _mount_tire(conn, vid, int(chosen))
    except FormError as exc:
        return entity_page(request, vid, "tires", form, exc.args, status=400)
    events.changed()
    return go(request, f"/v/{vid}/e/tires?ps={shown}", "saved")


@app.post("/v/{vid}/e/{key}")
async def entity_add(request: Request, vid: int, key: str):
    entity = ENTITIES.get(key)
    if entity is None:
        raise HTTPException(404)
    form = await form_dict(request)
    try:
        with db.tx() as conn:
            vehicle = vehicle_or_404(conn, vid)
            values = entities.parse_form(entity, form, units.of(vehicle), unit_for(vehicle["fuel_type"]))  # typed in the units shown
            entities.insert(conn, entity, vid, values)
    except FormError as exc:
        return entity_page(request, vid, "trips" if key == "counters" else key, form, exc.args, status=400)
    events.changed()
    return go(request, f"/v/{vid}/e/{'trips#counters' if key == 'counters' else key}", "saved")


@app.post("/v/{vid}/e/{key}/{row_id}")
async def entity_update(request: Request, vid: int, key: str, row_id: int):
    entity = ENTITIES.get(key)
    if entity is None:
        raise HTTPException(404)
    form = await form_dict(request)
    try:
        with db.tx() as conn:
            vehicle = vehicle_or_404(conn, vid)
            values = entities.parse_form(entity, form, units.of(vehicle), unit_for(vehicle["fuel_type"]))
            entities.update(conn, entity, vid, row_id, values)
    except FormError as exc:
        return entity_page(request, vid, "trips" if key == "counters" else key, form, exc.args, edit_id=row_id, status=400)
    events.changed()
    return go(request, f"/v/{vid}/e/{'trips#counters' if key == 'counters' else key}", "saved")


@app.post("/v/{vid}/e/{key}/{row_id}/delete")
def entity_delete(request: Request, vid: int, key: str, row_id: int):
    entity = ENTITIES.get(key)
    if entity is None:
        raise HTTPException(404)
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        entities.delete(conn, entity, vid, row_id)
    events.changed()
    return go(request, f"/v/{vid}/e/{'trips#counters' if key == 'counters' else key}", "deleted")


@app.post("/v/{vid}/e/tasks/{row_id}/done")
async def task_done(request: Request, vid: int, row_id: int):
    """Reset a job: today's date and the odometer (or the km typed in the shown unit) become its last completion."""
    form = await form_dict(request)
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        odo = summary.current_odometer(conn, vid)
        typed = None
        try:
            typed = round(units.of(vehicle).from_d(float(str(form.get("km", "")).replace(",", "."))))
        except (ValueError, TypeError):
            typed = None
        conn.execute(
            "UPDATE tasks SET last_date = ?, last_km = COALESCE(?, ?, last_km) WHERE id = ? AND vehicle_id = ?",
            (date.today().isoformat(), typed, odo, row_id, vid),
        )
    events.changed()
    return go(request, f"/v/{vid}/e/tasks", "saved")


@app.post("/v/{vid}/tasks/templates")
def task_templates(request: Request, vid: int):
    """Add the ready-made jobs this car does not have yet (generic guideline values)."""
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        for title, _note, km, months, keywords, _icon in entities.TASK_TEMPLATES:
            if not conn.execute("SELECT 1 FROM tasks WHERE vehicle_id = ? AND title = ?", (vid, title)).fetchone():
                conn.execute(
                    "INSERT INTO tasks(vehicle_id, title, interval_km, interval_months, keywords) VALUES(?,?,?,?,?)",
                    (vid, title, km, months, keywords),
                )
    events.changed()
    return go(request, f"/v/{vid}/e/tasks", "saved")


@app.post("/v/{vid}/e/tires/{row_id}/mount")
def tire_mount(request: Request, vid: int, row_id: int):
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        _mount_tire(conn, vid, row_id)
    events.changed()
    return go(request, f"/v/{vid}/e/tires?edit=1", "saved")


# ------------------------------------------------------------------ fuel report


@app.get("/v/{vid}/report")
def fuel_report(request: Request, vid: int):
    t_ = i18n.translator(config.language())
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        unit = unit_for(vehicle["fuel_type"])
        shown = units.of(vehicle)
        series = [(label, shown.c(value, unit)) for label, value in fuelstats.consumption_series(conn, vid)]
        group = request.query_params.get("g", "month")
        group = group if group in fuelstats.PERIODS else "month"
        count = request.query_params.get("n", "")
        count = int(count) if count.isdigit() and int(count) in fuelstats.PERIODS[group] else fuelstats.PERIODS[group][0]
        names = [t_("report.c_fuel"), t_("report.c_service"), t_("report.c_mods"), t_("report.c_parts")]
        cost_rows = fuelstats.costs(conn, vid, group, count)
        cost_totals = [sum(r[k] for r in cost_rows) for k in ("fuel", "service", "mods", "parts")]
        cost_chart = charts.bars_svg(
            [(_period_label(r["key"], group), [r["fuel"], r["service"], r["mods"], r["parts"]]) for r in cost_rows],
            unit=f" {units.of().cur}",
            names=names,
        )
        km_rows = fuelstats.kilometres(conn, vid, group, count)
        km_chart = charts.bars_svg([(_period_label(k, group), [shown.d(v) if v else 0]) for k, v in km_rows], unit=f" {shown.dist_unit}")
        km_total = sum(v for _k, v in km_rows if v)
        kinds = ("fuel", "service", "mods", "parts")
        kind = request.query_params.get("c", "")
        kind = kind if kind in kinds else ""
        spent_all = sum(cost_totals)
        shares = [
            {"kind": k, "name": names[i], "sum": cost_totals[i], "pct": cost_totals[i] / spent_all * 100}
            for i, k in enumerate(kinds)
            if cost_totals[i] > 0 and spent_all > 0
        ]
        listing = fuelstats.expenses(conn, vid, group, count, kind)
        exp_months: list[dict] = []
        for e in listing:
            if not exp_months or exp_months[-1]["key"] != e["date"][:7]:
                exp_months.append({"key": e["date"][:7], "sum": 0.0, "rows": []})
            exp_months[-1]["sum"] += e["cost"]
            exp_months[-1]["rows"].append(e)
        km_shown = shown.d(km_total) if km_total else 0
        top = max(listing, key=lambda e: e["cost"]) if listing else None
        window = fuelstats.period_start(group, count, date.today()).isoformat()
        series = [(label, value) for label, value in series if label[:10] >= window]
        months = [
            {"month": m.month, "km": shown.d(m.km), "per_100": shown.c(m.per_100, unit) if m.per_100 else None, "spent": m.spent}
            for m in fuelstats.periods(conn, vid, group, count)
        ]
        stats = {
            k: (shown.c(v, unit) if k in ("avg_per_100", "last_per_100") and v else v) for k, v in fuelstats.overall(conn, vid).items()
        }
        return render(
            request,
            "report.html",
            **vehicle_ctx(conn, vehicle, "report"),
            months=months,
            group=group,
            count=count,
            counts=fuelstats.PERIODS[group],
            period_groups=tuple(fuelstats.PERIODS),
            stats=stats,
            chart=charts.line_svg(series[-40:], unit=f" {shown.consumption_unit(unit)}", trend=5),
            price_chart=charts.line_svg(fuelstats.price_series(conn, vid, window)[-60:], unit=f" {units.of().cur}", trend=5),
            cost_chart=cost_chart,
            cost_names=names,
            cost_totals=cost_totals,
            spent_all=spent_all,
            per_period=spent_all / count if spent_all else 0,
            per_km100=spent_all / km_shown * 100 if km_shown and spent_all else None,
            shares=shares,
            kind=kind,
            kinds=kinds,
            exp_months=exp_months,
            exp_count=len(listing),
            exp_sum=sum(e["cost"] for e in listing),
            top=top,
            km_chart=km_chart,
            km_total=shown.d(km_total),
            unit=unit,
        )


# ------------------------------------------------------------------ trips


@app.get("/v/{vid}/trips/{trip_id}")
def trip_detail(request: Request, vid: int, trip_id: int):
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        trip = conn.execute("SELECT * FROM trips WHERE id = ? AND vehicle_id = ?", (trip_id, vid)).fetchone()
        if trip is None:
            raise HTTPException(404)
        points = trips.trip_points(conn, trip_id)
        return render(
            request,
            "trip.html",
            **vehicle_ctx(conn, vehicle, "trips"),
            trip=trip,
            distance=trips.trip_distance(trip),
            route=charts.route_svg([(p["lat"], p["lon"]) for p in points]),
            point_count=len(points),
        )


@app.get("/v/{vid}/trips/{trip_id}/track.json")
def trip_track_json(vid: int, trip_id: int):
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        if conn.execute("SELECT 1 FROM trips WHERE id = ? AND vehicle_id = ?", (trip_id, vid)).fetchone() is None:
            raise HTTPException(404)
        trip = conn.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
        data = trips.stats(trips.trip_points(conn, trip_id))
        km = trips.trip_distance(trip) or data["km"]
        shown, base = units.of(), unit_for(vehicle_or_404(conn, vid)["fuel_type"])
        overall = fuelstats.overall(conn, vid)
        est: dict = {}
        if km and overall["avg_per_100"]:  # an estimate: the average consumption of the car x the driven km (x the average price)
            litres = km * overall["avg_per_100"] / 100
            est = {
                "per100": f"{shown.c(overall['avg_per_100'], base):.1f}".replace(".", ","),
                "per100_unit": shown.consumption_unit(base),
                "amount": f"{shown.v(litres, base):.1f}".replace(".", ","),
                "amount_unit": shown.vol_unit(base),
                "cost": f"{km * overall['cost_per_100'] / 100:.2f}".replace(".", ",") if overall["cost_per_100"] else None,
                "cur": shown.cur,
            }
        data["estimate"] = est
    return JSONResponse(data, headers={"Cache-Control": "no-cache"})


@app.get("/v/{vid}/trips/{trip_id}/track.gpx")
def trip_gpx(vid: int, trip_id: int):
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        trip = conn.execute("SELECT * FROM trips WHERE id = ? AND vehicle_id = ?", (trip_id, vid)).fetchone()
        if trip is None:
            raise HTTPException(404)
        data = trips.gpx_bytes(trip, trips.trip_points(conn, trip_id))
    return Response(data, media_type="application/gpx+xml", headers={"Content-Disposition": f'attachment; filename="trip-{trip_id}.gpx"'})


@app.post("/v/{vid}/trips-import")
async def trips_import(request: Request, vid: int):
    form = await request.form()
    upload = form.get("gpx")
    if upload is None or not getattr(upload, "filename", ""):
        return go(request, f"/v/{vid}/e/trips", "err.required")
    category = form.get("category") if form.get("category") in entities.TRIP_CATEGORIES else "private"
    try:
        data = await upload.read(trips.MAX_GPX_BYTES + 1)
        with db.tx() as conn:
            vehicle_or_404(conn, vid)
            trips.import_gpx(conn, vid, data, category)
    except trips.GpxError as exc:
        return go(request, f"/v/{vid}/e/trips", exc.args[0])
    events.changed()
    return go(request, f"/v/{vid}/e/trips", "saved")


def _trip_labels() -> dict[str, str]:
    t = i18n.translator(config.language())
    keys = {
        "title": "trips.logbook", "period": "exp.period", "total": "exp.total", "disclaimer": "exp.disclaimer",
        "date": "f.date", "start": "f.start_time", "end": "f.end_time", "from": "f.start_place", "to": "f.end_place",
        "start_km": "f.start_km", "end_km": "f.end_km", "distance": "f.distance", "category": "f.category", "purpose": "f.purpose",
    }  # fmt: skip
    labels = {k: t(v) for k, v in keys.items()}
    for cat in entities.TRIP_CATEGORIES:
        labels["cat." + cat] = t("category." + cat)
    return labels


@app.get("/v/{vid}/trips-export.{fmt}")
def trips_export(vid: int, fmt: str, start: str | None = None, end: str | None = None, range: str | None = None):
    if fmt not in ("csv", "pdf"):
        raise HTTPException(404)
    start, end = fuel_export_mod.resolve_range(range, start, end) if range else trips.parse_range(start, end)
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        rows = trips.trips_in_range(conn, vid, start, end)
        if start.startswith("0000"):  # everything: the period shown is the one of the drives
            dates = [r["date"] for r in rows if r["date"]]
            start, end = (min(dates), max(dates)) if dates else (date.today().isoformat(),) * 2
        if fmt == "csv":
            data, media = trips.csv_bytes(rows, _trip_labels()), "text/csv; charset=utf-8"
        else:
            data, media = trips.pdf_bytes(vehicle, rows, start, end, _trip_labels()), "application/pdf"
    return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="logbook-{start}-{end}.{fmt}"'})


@app.get("/v/{vid}/fuel-export.{fmt}")
def fuel_export(vid: int, fmt: str, range: str | None = None, start: str | None = None, end: str | None = None):
    if fmt not in ("csv", "pdf"):
        raise HTTPException(404)
    first, last = fuel_export_mod.resolve_range(range, start, end)
    t = i18n.translator(config.language())
    shown = units.of()
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        unit = unit_for(vehicle["fuel_type"])
        rows = fuel_export_mod.fills_in_range(conn, vid, first, last)
        conv = {"dist": shown.d, "vol": lambda x: shown.v(x, unit), "price": lambda x: shown.price_vol(x, unit)}
        labels = {k: t(v) for k, v in {
            "date": "f.date", "odometer": "f.odometer", "amount": "f.amount", "price_unit": "f.price_unit", "price_total": "f.price_total",
            "full_tank": "f.full_tank", "station": "f.station", "notes": "f.notes", "title": "fuel.title", "period": "exp.period", "all": "fx.r_all",
        }.items()}  # fmt: skip
        if fmt == "csv":
            data, media = fuel_export_mod.csv_bytes(rows, labels, conv), "text/csv; charset=utf-8"
        else:
            data, media = fuel_export_mod.pdf_bytes(vehicle, rows, first, last, labels, conv), "application/pdf"
    name = "all" if first.startswith("0000") else f"{first}-{last}"
    return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="fuel-{name}.{fmt}"'})


# ------------------------------------------------------------------ documents


@app.get("/v/{vid}/docs")
def docs_page(request: Request, vid: int, error: str | None = None):
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        total = conn.execute("SELECT COUNT(*) FROM documents WHERE vehicle_id = ?", (vid,)).fetchone()[0]
        pages = max(1, -(-total // lists.size()))
        asked = request.query_params.get("page", "1")
        page = min(max(int(asked) if asked.isdigit() else 1, 1), pages)
        docs = conn.execute(
            "SELECT * FROM documents WHERE vehicle_id = ? ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
            (vid, lists.size(), (page - 1) * lists.size()),
        ).fetchall()
        pager = {"page": page, "pages": pages, "total": total, "size": lists.size()}
        return render(request, "docs.html", **vehicle_ctx(conn, vehicle, "docs"), docs=docs, categories=DOC_CATEGORIES, pager=pager)


_DOC_WORDS = (
    ("registration", ("fahrzeugschein", "zulassung", "registration", "schein", "brief")),
    ("insurance", ("versicherung", "insurance", "police", "sf-klasse")),
    ("inspection", ("tüv", "tuv", "hu_", "hu-", "au_", "prüf", "pruef", "inspection", "dekra", "gutachten")),
    ("manual", ("handbuch", "anleitung", "betriebsanleitung", "manual", "bedienung")),
    ("invoice", ("rechnung", "invoice", "beleg", "quittung", "receipt", "kaufvertrag")),
)


def guess_doc_category(filename: str) -> str:
    """A first guess from the file name (the upload button asks for nothing else); everything unknown is 'other'."""
    low = filename.lower()
    return next((cat for cat, words in _DOC_WORDS if any(w in low for w in words)), "other")


@app.post("/v/{vid}/docs")
async def docs_upload(request: Request, vid: int):
    form = await request.form()
    upload = form.get("file")
    if upload is None or not getattr(upload, "filename", ""):
        return go(request, f"/v/{vid}/docs", "err.required")
    filename = clean_filename(upload.filename)
    ext = Path(filename).suffix.lower()
    if ext not in DOC_EXT:
        return go(request, f"/v/{vid}/docs", "err.file_type")
    data = await upload.read(MAX_DOC + 1)
    if len(data) > MAX_DOC:
        return go(request, f"/v/{vid}/docs", "err.file_big")
    category = form.get("category") if form.get("category") in DOC_CATEGORIES else guess_doc_category(filename)
    title = (form.get("title") or "").strip()[:120] or filename
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        doc_id = conn.execute(
            "INSERT INTO documents(vehicle_id, category, title, filename, mime, size) VALUES(?,?,?,?,?,?)",
            (vid, category, title, filename, DOC_EXT[ext], len(data)),
        ).lastrowid
        folder = config.files_dir() / str(vid)
        folder.mkdir(exist_ok=True)
        (folder / f"{doc_id}{ext}").write_bytes(data)
    return go(request, f"/v/{vid}/docs", "saved")


def _doc_path(vid: int, doc: sqlite3.Row) -> Path:
    return config.files_dir() / str(vid) / f"{doc['id']}{Path(doc['filename']).suffix.lower()}"


@app.get("/v/{vid}/docs/{doc_id}")
def docs_download(vid: int, doc_id: int):
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        doc = conn.execute("SELECT * FROM documents WHERE id = ? AND vehicle_id = ?", (doc_id, vid)).fetchone()
    if doc is None or not _doc_path(vid, doc).is_file():
        raise HTTPException(404)
    return FileResponse(
        _doc_path(vid, doc),
        media_type=doc["mime"] or "application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(doc['filename'])}"},
    )


@app.post("/v/{vid}/docs/{doc_id}/delete")
def docs_delete(request: Request, vid: int, doc_id: int):
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        doc = conn.execute("SELECT * FROM documents WHERE id = ? AND vehicle_id = ?", (doc_id, vid)).fetchone()
        if doc:
            _doc_path(vid, doc).unlink(missing_ok=True)
            conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    return go(request, f"/v/{vid}/docs", "deleted")


# ------------------------------------------------------------------ calendar


@app.get("/calendar.ics")
def calendar_all():
    with db.tx() as conn:
        data = calendar_ics.build(conn)
    return Response(
        data, media_type="text/calendar; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="car-assistant.ics"'}
    )


@app.get("/v/{vid}/calendar.ics")
def calendar_vehicle(vid: int):
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        data = calendar_ics.build(conn, vid)
    return Response(
        data, media_type="text/calendar; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="vehicle-{vid}.ics"'}
    )


# ------------------------------------------------------------------ stations


@app.get("/stations")
def stations_legacy(request: Request):
    """Stations belong to ONE vehicle: the old address leads to the first car."""
    with db.tx() as conn:
        row = conn.execute("SELECT id FROM vehicles WHERE archived = 0 ORDER BY name COLLATE NOCASE LIMIT 1").fetchone()
        target = f"/v/{slugs.slug_of(conn, row['id'])}/stations" if row else "/vehicles"
    return RedirectResponse(f"{request.state.base}{target}", status_code=303)


def station_context(request: Request, vehicle: sqlite3.Row) -> dict:
    """What the station search needs for THIS vehicle: its last known position (or the phone's, the browser asks for it) and the result when
    the user pressed search. Nothing is requested online until then."""
    q = request.query_params
    with db.tx() as conn:
        pos = conn.execute("SELECT value FROM live WHERE vehicle_id = ? AND key = 'position'", (vehicle["id"],)).fetchone()
    car_pos: tuple[float, float] | None = None
    if pos and pos["value"]:
        try:
            lat, lon = pos["value"].split(",")
            car_pos = (float(lat), float(lon))
        except ValueError:
            car_pos = None
    origin = car_pos
    where = "car"
    error = None
    try:
        if q.get("lat") and q.get("lon"):
            origin, where = (entities.parse_float(q["lat"], "f.lat"), entities.parse_float(q["lon"], "f.lon")), "me"
    except FormError:
        error = "err.number"
    searched = bool(q.get("go"))
    electric = vehicle["fuel_type"] == "electric"
    fuel = q.get("fuel") if q.get("fuel") in stations.FUELS else ("diesel" if vehicle["fuel_type"] == "diesel" else "e5")
    sort = q.get("sort") if q.get("sort") in ("price", "distance") else "price"
    shown_units = units.of(vehicle)
    try:
        chosen = stations.default_radius()
        radius = float(
            q.get("radius", shown_units.d(chosen) if chosen else ("5" if not shown_units.imperial else "3"))
        )  # in the distance unit shown
    except ValueError:
        radius = 5.0
    radius_km = shown_units.from_d(radius)
    country = ha.country() if ha.available() else ""
    source_list = stations.sources(country)
    source = q.get("source")
    if source not in {s["id"] for s in source_list}:
        source = stations.default_source(country)
    results: list[stations.Station] = []
    if searched and not electric and origin is not None and error is None:
        try:
            results, source = stations.nearby(origin[0], origin[1], radius_km, fuel, source, sort)
        except stations.StationsError as exc:
            error = exc.args[0]
    return {
        "car_pos": car_pos, "origin": origin, "where": where, "results": results, "error": error, "electric": electric, "fuel": fuel,
        "sort": sort, "radius": radius, "source": source, "searched": searched, "has_key": next((s["has_key"] for s in source_list if s["id"] == source), False),
        "sources": source_list, "info": next((s for s in source_list if s["id"] == source), source_list[0]),
    }  # fmt: skip


@app.get("/v/{vid}/stations")
def stations_page(request: Request, vid: int):
    """The fuel stations are a part of the fuel page now (same query string)."""
    with db.tx() as conn:
        slug = vehicle_or_404(conn, vid)["slug"]
    query = request.url.query
    return RedirectResponse(f"{request.state.base}/v/{slug}/e/fuel{'?' + query if query else ''}#stations", status_code=303)


# ------------------------------------------------------------------ integrations & modules


@app.get("/integrations")
def integrations_page(request: Request):
    with db.tx() as conn:
        off = modules.disabled(conn)
        api_tokens = connectors.list_tokens(conn)
        all_vehicles = conn.execute(
            "SELECT id, name, slug, plate, photo FROM vehicles WHERE archived = 0 ORDER BY name COLLATE NOCASE"
        ).fetchall()
    secret_set = {
        i.key: {o.name: bool(integrations.get(i.key, o.name)) for o in i.options if o.kind == "password"} for i in integrations.INTEGRATIONS
    }
    plain = {
        i.key: {o.name: (integrations.get(i.key, o.name) or "") for o in i.options if o.kind != "password"}
        for i in integrations.INTEGRATIONS
    }
    int_enabled = {i.key: integrations.is_enabled(i.key) for i in integrations.INTEGRATIONS}
    int_enabled["mqtt"] = config.mqtt_discovery_enabled()
    return render(
        request,
        "integrations.html",
        all_modules=modules.MODULES,
        off=off,
        catalog=integrations.INTEGRATIONS,
        int_enabled=int_enabled,
        secret_set=secret_set,
        plain=plain,
        found_plugins=plugins.discover(),
        api_tokens=api_tokens,
        all_vehicles=all_vehicles,
        tab=None,
        v=None,
    )  # fmt: skip


@app.post("/integrations/module/{key}")
async def integrations_module(request: Request, key: str):
    form = await form_dict(request)
    enabled = form.get("enabled") == "1"
    try:
        with db.tx() as conn:
            modules.set_enabled(conn, key, enabled)
    except KeyError:
        raise HTTPException(404) from None
    return go(request, "/integrations", "module_on" if enabled else "module_off")


@app.post("/integrations/{key}")
async def integrations_save(request: Request, key: str):
    if key not in integrations.BY_KEY:
        raise HTTPException(404)
    form = await form_dict(request)
    was_on = key == "mqtt" and config.mqtt_discovery_enabled()
    if key == "mqtt" and (form.get("host") or "").strip() and config.stored_setting("int.mqtt.enabled") is None:
        form["enabled"] = "1"  # the first own broker that is entered switches the sensors on - no second visit needed
    with db.tx() as conn:
        if was_on and not form.get("enabled"):
            publisher.remove_all(conn)  # switched off: the cars' entities leave Home Assistant again
        integrations.save(conn, key, form)
    if key == "mqtt":
        publisher.stop()  # reconnect with the new settings (manual broker or the Home Assistant default)
        publisher.start()
        events.changed()
    return go(request, "/settings/system#mqtt" if form.get("back") == "system" else "/integrations", "int_saved")


# ------------------------------------------------------------------ settings, backup


SETTINGS_SECTIONS = ("car", "user", "system")  # the tabs, in this order: the car, the person, the whole app
OLD_SECTIONS = ("design", "region")  # the former tabs now live on the System tab; their addresses still work


@app.get("/settings")
def settings_page(request: Request):
    return RedirectResponse(f"{request.state.base}/settings/car", status_code=303)


def _settings_tabs(current: str) -> list[dict]:
    t = i18n.translator(config.language())
    titles = {"user": t("set.user"), "car": t("set.car"), "system": t("set.system")}
    return [{"key": k, "href": f"/settings/{k}", "title": titles[k], "on": k == current} for k in SETTINGS_SECTIONS]


def _settings_section(request: Request, section: str):
    with db.tx() as conn:
        account = auth_web.account_context(request, conn)
        map_tiles = vehicle_status.map_tiles_enabled(conn)
        from . import about as about_info

        info = about_info.collect(conn)
        server = {
            "version": __version__,
            "python": info["python"],
            "db": info["db"],
            "files": info["files"],
            "vehicles": len(info["vehicles"]),
            "entries": info["entries"],
        }
        has_users = accounts.has_users(conn)
        design_ctx = _design_context(conn)
        sources_auto = db.get_setting(conn, "sources.auto", "") == "1"
        log_keep = connectors.log_keep(conn)
        log_days = connectors.log_days(conn)
        log_total = conn.execute("SELECT COUNT(*) FROM vehicle_logs").fetchone()[0]
        me = account.get("acct_me")
        cars = conn.execute("SELECT * FROM vehicles WHERE archived = 0 ORDER BY name COLLATE NOCASE").fetchall()
        car = _current_car(request, cars)
        notify_prefs = notify.prefs(conn, me["id"]) if me else {"service": "", "events": [], "enabled": True}
        notify_matrix = notify.matrix(conn, me["id"]) if me and section == "user" else None
        car_ctx = _car_context(conn, car) if section == "car" and car is not None else {}
        system_theme = themes.current(conn)
        start_car = userprefs.get(conn, me["id"], "start_car") if me else None
        my_design = userprefs.get(conn, me["id"], "design") if me else None
        push_dev = push.devices(conn, me["id"]) if me else []
        mcp_state = mcp.state(conn) if section == "system" else None
        log_rows = conn.execute("SELECT * FROM notify_log ORDER BY id DESC LIMIT 5").fetchall()
        vehicle_rows = conn.execute(
            "SELECT id, name, slug, plate, archived FROM vehicles ORDER BY archived, name COLLATE NOCASE"
        ).fetchall()
    return render(
        request,
        "settings_section.html",
        unit_systems=units.SYSTEMS,
        currencies=units.CURRENCIES,
        default_units=units.default_system(),
        default_currency=units.default_currency(),
        section=section,
        mqtt_host=integrations.get("mqtt", "host") or "",
        mqtt_port=integrations.get("mqtt", "port") or "",
        mqtt_user=integrations.get("mqtt", "username") or "",
        mqtt_pw_set=bool(integrations.get("mqtt", "password")),
        mqtt_auto=bool(config.os.environ.get("MQTT_HOST")),
        mqtt_enabled=config.mqtt_discovery_enabled(),
        mqtt_available=config.mqtt_settings() is not None,
        mqtt_connected=publisher.connected,
        ha_available=ha.available(),
        has_key=bool(config.tankerkoenig_key()),
        external_url=config.external_url(),
        has_users=has_users,
        direct_state=_direct_state(has_users),
        published_port=ha.published_port(),
        log_rows=log_rows,
        vehicle_rows=vehicle_rows,
        map_tiles=map_tiles,
        geocoder_url=config.stored_setting("map.geocoder_url") or "",
        server=server,
        lock_after=auth_web.lock_after(),
        lock_minutes=auth_web.lock_seconds() // 60,
        acct_blocked=auth_web.blocked(),
        **design_ctx,
        my_design=my_design,
        picker_icons=icon_set.PICKER_ICONS,
        section_tabs=_settings_tabs(section),
        tab=None,
        v=car if section == "car" else None,
        nav_vid=car["id"] if car else None,
        system_design=section != "car",  # only the Car tab shows the design of the car; the others show the system's own
        switch_to="/settings/car?car=" if section == "car" else "",
        car=car,
        system_theme=system_theme,
        **car_ctx,
        **account,
        notify_prefs=notify_prefs,
        mcp_state=mcp_state,
        notify_matrix=notify_matrix,
        start_car=start_car,
        sources_auto=sources_auto,
        log_keep=log_keep,
        log_days=log_days,
        log_days_choices=connectors.LOG_DAYS_CHOICES,
        log_choices=connectors.LOG_KEEP_CHOICES,
        log_total=log_total,
        notify_events=notify.EVENTS,
        notify_general=notify.GENERAL,
        push_devices=push_dev,
    )


def _current_car(request: Request, cars) -> sqlite3.Row | None:
    """The car the Car tab is about: the web app's own car, else the one asked for (?car=), else the one opened last, else the first."""
    if not cars:
        return None
    by = {c["slug"]: c for c in cars} | {str(c["id"]): c for c in cars}
    for token in (request.cookies.get(APP_COOKIE), request.query_params.get("car"), request.cookies.get(LAST_CAR)):
        if token and token in by:
            return by[token]
    return cars[0]


def _car_context(conn, car) -> dict:
    """Everything the Car tab shows besides the car itself: photos / videos, Home Assistant entities, backup, its design."""
    from . import pagemods

    panel = {f"media_{k}": val for k, val in media.panel(conn, car["id"]).items()}
    return {
        **panel,
        "has_codes": pagemods.has_secrets(conn, car["id"]),
        "ha_entities": ha.list_entities() if ha.available() else [],
        "car_accent": themes.clean_accent(car["accent"])
        or themes.clean_accent(db.get_setting(conn, themes.ACCENT_SETTING, ""))
        or themes.DEFAULT_ACCENT,
    }


def _design_context(conn) -> dict:
    """What the design picker needs (Settings -> Design and the first start)."""
    names = themes.available()
    return {
        "theme_list": names,
        "theme_meta": {name: themes.meta(name) for name in names},
        "theme_attr_of": {name: themes.attr(name) for name in names},
        "theme_file_of": {name: (themes.base_of(name) if themes.base_of(name) != themes.DEFAULT else None) for name in names},
        "custom_themes": themes.CUSTOM,
        "accent": themes.clean_accent(db.get_setting(conn, themes.ACCENT_SETTING, "")) or themes.DEFAULT_ACCENT,
        "accent_presets": themes.PRESETS,
    }


def _register_settings_sections() -> None:
    for name in SETTINGS_SECTIONS:

        def page(request: Request, _name: str = name):  # the annotation matters: FastAPI hands over the request
            return _settings_section(request, _name)

        app.add_api_route(f"/settings/{name}", page, methods=["GET"], include_in_schema=False)


_register_settings_sections()


def _old_section(request: Request, _name: str = "system"):
    """Design and Region were tabs of their own; now they are cards of System (the old addresses keep working)."""
    return _settings_section(request, "system")


for _old in OLD_SECTIONS:
    app.add_api_route(f"/settings/{_old}", _old_section, methods=["GET"], include_in_schema=False)


@app.post("/settings/language")
async def settings_language(request: Request):
    form = await form_dict(request)
    lang = form.get("language", "")
    if lang not in i18n.CATALOGS:
        return go(request, "/settings/system#region", "err.choice")
    with db.tx() as conn:
        db.set_setting(conn, "language", lang)
        db.set_setting(conn, "setup.language", "1")
    return go(request, "/settings/system#region", "saved")


@app.post("/settings/units")
async def settings_units(request: Request):
    form = await form_dict(request)
    with db.tx() as conn:
        system, currency = form.get("units", ""), form.get("currency", "")
        db.set_setting(conn, "region.units", system if system in units.SYSTEMS and system != units.DEFAULT_SYSTEM else None)
        db.set_setting(conn, "region.currency", currency if currency in units.CURRENCY else None)
    return go(request, "/settings/system#units", "saved")


@app.post("/settings/theme")
async def settings_theme(request: Request):
    form = await form_dict(request)
    choice = form.get("theme", "")
    with db.tx() as conn:
        db.set_setting(conn, themes.SETTING, choice if choice in themes.available() and choice != themes.DEFAULT else None)
    return go(request, "/settings/system#theme", "saved")


@app.post("/settings/accent")
async def settings_accent(request: Request):
    """The colour of the designs "dark / light with your own colour" (one colour for the whole server; applies at once, no Save)."""
    form = await form_dict(request)
    color = themes.clean_accent(form.get("accent"))
    if color is None:
        raise HTTPException(400)
    with db.tx() as conn:
        db.set_setting(conn, themes.ACCENT_SETTING, color)
    if form.get("ajax"):
        return Response(status_code=204)
    return go(request, "/settings/system#theme", "saved")


@app.get("/settings/accent-preview")
def settings_accent_preview(c: str = "", s: str = "dark"):
    """The accent family of a colour as CSS, so the colour wheel can show it live before it is saved (the maths stays in one place)."""
    color = themes.clean_accent(c)
    if color is None:
        raise HTTPException(400)
    return Response(
        themes.accent_css(color, s if s in ("light", "auto") else "dark"), media_type="text/css", headers={"Cache-Control": "no-store"}
    )


@app.post("/settings/page-size")
async def settings_page_size(request: Request):
    form = await form_dict(request)
    size = lists.clean(form.get("size"))
    if size is None:
        raise HTTPException(400)
    with db.tx() as conn:
        me = auth_web._acting_user(request, conn)
        if me is not None:  # signed in: the person's own choice
            userprefs.put(conn, me["id"], "page_size", str(size))
        else:  # no sign-in (Home Assistant only): one setting for the system
            db.set_setting(conn, lists.SETTING, str(size))
    if form.get("ajax"):
        return Response(status_code=204)
    return go(request, "/settings/user#lists", "saved")


@app.post("/settings/haptics")
async def settings_haptics(request: Request):
    form = await form_dict(request)
    with db.tx() as conn:
        me = auth_web._acting_user(request, conn)
        if me is not None and ha.network_port()[1] is not None:  # a port is set: everybody changes only their own choice
            userprefs.put(conn, me["id"], "haptics", "1" if form.get("haptics") else "0")
        else:  # no port: one setting for the system
            db.set_setting(conn, "ui.haptics", "1" if form.get("haptics") else "0")
    return go(request, "/settings/user#prefs" if form.get("from") == "user" else "/settings/system#haptics", "saved")


def _direct_state(has_users: bool) -> str:
    """What "direct access" is right now: off (no port mapped), accounts (reachable, protected), locked (port, but nobody can sign in), unknown."""
    known, port = ha.network_port()
    if not known:
        return "unknown"
    if port is None:
        return "off"
    if has_users:
        return "accounts"
    return "locked"


@app.post("/settings/sources-auto")
async def settings_sources_auto(request: Request):
    """Opt-in: the app reads the package sources once a day (the only time it goes online by itself for packages)."""
    form = await form_dict(request)
    with db.tx() as conn:
        db.set_setting(conn, "sources.auto", "1" if form.get("auto") else None)
    if form.get("ajax"):
        return Response(status_code=204)
    return go(request, "/settings/system#updates", "saved")


@app.post("/settings/logs")
async def settings_logs(request: Request):
    """How many log lines each plugin may keep (the oldest go first), or delete all plugin logs."""
    form = await form_dict(request)
    with db.tx() as conn:
        if form.get("clear"):
            conn.execute("DELETE FROM vehicle_logs")
        else:
            with contextlib.suppress(ValueError):  # not a number: unchanged
                if form.get("lines"):
                    connectors.set_log_keep(conn, int(form["lines"]))
                if form.get("days"):
                    connectors.set_log_days(conn, int(form["days"]))
    if form.get("ajax"):
        return Response(status_code=204)
    return go(request, "/settings/system#logs", "saved")


@app.post("/settings/prefs")
async def settings_prefs(request: Request):
    """The signed-in user's own preferences (start car)."""
    form = await form_dict(request)
    with db.tx() as conn:
        me = auth_web._acting_user(request, conn)
        if me is None:
            return go(request, "/settings/user", "acct.need_admin")
        choice = str(form.get("start_car") or "")
        valid = {str(r["id"]) for r in conn.execute("SELECT id FROM vehicles WHERE archived = 0")}
        userprefs.put(conn, me["id"], "start_car", choice if choice in valid else None)
        if (
            ha.network_port()[1] is not None and "design" in form
        ):  # design and touch feedback are personal only when people sign in over a port
            design = str(form.get("design") or "")
            userprefs.put(conn, me["id"], "design", design if design in themes.available() else None)
            userprefs.put(conn, me["id"], "haptics", "1" if form.get("haptics") else "0")
    if form.get("ajax"):
        return Response(status_code=204)
    return go(request, "/settings/user#prefs", "saved")


@app.post("/settings/external-url")
async def settings_external_url(request: Request):
    """The address from which the app is reached from outside. Only once a user exists: without a login everyone on the internet could read the cars."""
    form = await form_dict(request)
    raw = form.get("host") if "host" in form else form.get("url", "")
    raw = (raw or "").strip()
    if "host" in form and raw and not raw.lower().startswith("http://"):  # https:// is fixed in front of the field
        raw = "https://" + raw.removeprefix("https://").removeprefix("HTTPS://")
    try:
        value = config.clean_external_url(raw)
    except ValueError as exc:
        return go(request, "/settings/system#external", str(exc))
    with db.tx() as conn:
        if value and not accounts.has_users(conn):
            return go(request, "/settings/system#external", "err.ext_needs_user")
        db.set_setting(conn, "ext.url", value or None)
    config.forget_external()
    return go(request, "/settings/system#external", "saved")


@app.post("/settings/map")
async def settings_map(request: Request):
    form = await form_dict(request)
    with db.tx() as conn:
        db.set_setting(conn, vehicle_status.MAP_SETTING, "1" if form.get("tiles") else "0")
    if form.get("tiles"):
        from . import places

        places.kick()  # trips with coordinates get their place names
    return go(request, "/settings/system#online", "saved")


@app.post("/settings/geocoder")
async def settings_geocoder(request: Request):
    """The address used for place names (a Nominatim-compatible server); empty = the public OpenStreetMap service. https only."""
    from . import places

    form = await form_dict(request)
    try:
        value = places.clean_source(form.get("url") or "")
    except ValueError as exc:
        return go(request, "/settings/system#online", str(exc))
    with db.tx() as conn:
        db.set_setting(conn, "map.geocoder_url", value or None)
    config.forget_settings()
    return go(request, "/settings/system#online", "saved")


@app.post("/settings/google")
async def settings_google(request: Request):
    """Offer a magnifier next to the passport fields that opens a Google search (nothing is sent by the app; the link is only opened by a click)."""
    form = await form_dict(request)
    with db.tx() as conn:
        db.set_setting(conn, "google.help", "1" if form.get("help") else "0")
    return go(request, "/settings/system#online", "saved")


def _fuel_back(raw: str) -> str:
    """Where a fuel setting returns to: the fuel page of a car (its settings panel), else the System page."""
    return raw + "?fs=1#fuel-settings" if re.fullmatch(r"/v/[a-z0-9-]{1,60}/e/fuel", raw or "") else "/settings/system"


@app.post("/settings/fuelkey")
async def settings_fuelkey(request: Request):
    """The own key for a fuel price source that needs one (empty + remove = delete it). Nothing is requested from a service without its key."""
    from . import fuelproviders

    form = await form_dict(request)
    pid = (form.get("id") or "")[:24]
    back = _fuel_back(form.get("back") or "")
    if pid == "tankerkoenig":
        name, rule = "int.tankerkoenig.api_key", r"[^A-Za-z0-9-]"
    else:
        defn = fuelproviders.load().get(pid)
        if defn is None or not defn["key"]:
            return go(request, back, "err.number")
        name, rule = f"int.fuelkey.{pid}", r"[^A-Za-z0-9._~+/=-]"
    key = re.sub(rule, "", (form.get("api_key") or ""))[:200]
    with db.tx() as conn:
        if key:
            db.set_setting(conn, name, key)
        elif form.get("remove"):
            db.set_setting(conn, name, None)
    config.forget_settings()
    return go(request, back, "saved")


@app.post("/settings/fuel-defaults")
async def settings_fuel_defaults(request: Request):
    """What the fuel page starts with: the preferred source and the search radius (in the distance unit shown)."""
    form = await form_dict(request)
    wanted = (form.get("source") or "")[:24]
    known = {s["id"] for s in stations.sources()}
    try:
        radius = units.of().from_d(float((form.get("radius") or "").replace(",", ".")))
    except ValueError:
        radius = None
    with db.tx() as conn:
        db.set_setting(conn, "fuel.source", wanted if wanted in known else None)
        db.set_setting(conn, "fuel.radius", f"{min(max(radius, 1.0), stations.MAX_RADIUS_KM):.1f}" if radius else None)
    config.forget_settings()
    if form.get("ajax"):
        return Response(status_code=204)
    return go(request, _fuel_back(form.get("back") or ""), "saved")


@app.post("/settings/notifications")
async def settings_notifications(request: Request):
    """The signed-in person's way to be told (the Home Assistant notify service)."""
    form = await request.form()
    with db.tx() as conn:
        me = auth_web._acting_user(request, conn)
        if me is None:
            return go(request, "/settings/user", "acct.need_admin")
        notify.save_service(conn, me["id"], str(form.get("service") or ""))
    if form.get("ajax"):
        return Response(status_code=204)
    return go(request, "/settings/user#notifications", "saved")


@app.post("/settings/notifications/matrix")
async def settings_notifications_matrix(request: Request):
    """The whole notification matrix of the signed-in person: events per car, the choice for new cars, the general events."""
    form = await request.form()
    with db.tx() as conn:
        me = auth_web._acting_user(request, conn)
        if me is None:
            return go(request, "/settings/user", "acct.need_admin")
        notify.save_matrix(conn, me["id"], form)
    if form.get("ajax"):
        return Response(status_code=204)
    return go(request, "/settings/user#notify-matrix", "saved")


@app.post("/settings/notifications/test")
async def settings_notifications_test(request: Request):
    """A test message to the person's own devices."""
    t = i18n.translator(config.language())
    back = "/settings/user#notifications"
    with db.tx() as conn:
        me = auth_web._acting_user(request, conn)
        if me is None:
            return go(request, back, "err.required")
        service = notify.prefs(conn, me["id"])["service"]
        if (not notify.push_mode() and not service) or (notify.push_mode() and not push.devices(conn, me["id"])):
            return go(request, back, "err.required")
        ok, _error = notify._deliver(conn, me["id"], service, "Car Assistant", t("notify.test"), "")
    return go(request, back, "notify_ok" if ok else "notify_fail")


@app.post("/settings/republish")
def settings_republish(request: Request):
    publisher.resend()
    events.changed()
    return go(request, "/settings/system", "saved")


@app.post("/settings/refresh-live")
def settings_refresh_live(request: Request):
    with db.tx() as conn:
        for vehicle in conn.execute("SELECT * FROM vehicles WHERE archived = 0").fetchall():
            live.refresh_vehicle(conn, vehicle)
    events.changed()
    return go(request, "/settings/system", "saved")


@app.get("/settings/backup.zip")
def settings_backup():
    data = backup.create()
    name = f"car-assistant-backup-{date.today().isoformat()}.zip"
    return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.post("/settings/restore")
async def settings_restore(request: Request):
    form = await request.form()
    upload = form.get("backup")
    if upload is None or not getattr(upload, "filename", "") or form.get("confirm") != "1":
        return go(request, "/settings/system", "err.required")
    try:
        backup.restore(await upload.read(backup.MAX_RESTORE_BYTES + 1))
    except backup.BackupError as exc:
        return go(request, "/settings/system", exc.args[0])
    events.changed()
    return go(request, "/", "restored")


@app.exception_handler(404)
async def not_found(request: Request, exc):
    return (
        render(request, "error.html", status=404, nf_path=request.url.path[:120])
        if hasattr(request.state, "base")
        else Response("Not found", status_code=404)
    )


from . import (  # noqa: E402,F401
    addons_web,
    assets_web,
    auth_web,
    connectors_web,
    demo_web,
    equipment_web,
    manual_web,
    mcp_web,
    media_web,
    nav_web,
    pagemods_web,
    push_web,
    sources_web,
    tiles_web,
    vehiclebackup_web,
    widgets_web,
)  # register the login, account, plugin API, navigation and page-module routes
