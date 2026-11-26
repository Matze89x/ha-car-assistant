"""Routes of the Home Assistant plugin (habridge.py): save the bindings, say what an entity would deliver while the person types, find entities to
choose from. The page itself is the settings page of the plugin (addons_web.py ``_settings_page``). Everything here is for administrators: the
entities of Home Assistant are the system's, not the car's."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from . import addons, config, db, events, ha, habridge, halive, i18n
from . import habridge_slots as cat
from .connectors_web import _may_manage
from .web import app, form_dict, go, vehicle_or_404


def _bridge(vid: int, aid: int) -> dict | None:
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        addon = addons.get(conn, vid, aid)
    return addon if addon is not None and addon["m"].get("bridge") else None


def _refused(request: Request) -> JSONResponse | None:
    return None if _may_manage(request) else JSONResponse({"ok": False, "error": "admin"}, status_code=403)


@app.post("/v/{vid}/integrations/{aid}/bridge")
async def bridge_save(request: Request, vid: int, aid: int):
    """Save the entities the page chose. Nothing is saved while anything is wrong; a plugin that holds an interface the choice needs is named."""
    ajax = request.headers.get("x-requested-with") == "fetch"
    if not _may_manage(request):
        return (
            JSONResponse({"ok": False, "error": "admin"}, status_code=403)
            if ajax
            else go(request, f"/v/{vid}/integrations", "acct.need_admin")
        )
    addon = _bridge(vid, aid)
    if addon is None:
        return go(request, f"/v/{vid}/plugins", "addon.err_id")
    form = await form_dict(request)
    states = ha.all_states()
    with db.tx() as conn:
        errors, taken = habridge.save(conn, addon, form, states)
    t = i18n.translator(config.language())
    if errors or taken:
        said = {field: t(why) for field, why in errors.items()}
        if ajax:
            return JSONResponse({"ok": False, "errors": said, "taken": taken}, status_code=422)
        typed = habridge.typed_rows(form, addon["m"])
        slots = frozenset(field.split(".")[1] if field.startswith("l.") else field.split(".")[-1] for field in errors if field != "_")
        from . import addons_web  # (loaded by now; importing it at the top would be a circle: addons_web -> web -> this module)

        return addons_web._settings_page(
            request, vid, addon, addon["vals"], {}, 400, hb_typed=typed, hb_errors=said, hb_taken=taken, hb_slots=slots
        )
    habridge.request_run(addon["id"])  # read at once, send everything
    events.changed()
    if ajax:
        return JSONResponse({"ok": True})
    return go(request, f"/v/{vid}/integrations/{aid}/settings", "saved")


@app.post("/v/{vid}/integrations/{aid}/bridge/preview")
async def bridge_preview(request: Request, vid: int, aid: int):
    """What each entity on the page would deliver right now - the answer for the status lines (while typing, and every few seconds)."""
    if (denied := _refused(request)) is not None:
        return denied
    addon = _bridge(vid, aid)
    if addon is None:
        return JSONResponse({"ok": False, "error": "gone"}, status_code=404)
    form = await form_dict(request)
    states = ha.all_states()
    t = i18n.translator(config.language())
    rows = habridge.preview(form, addon["m"], states, t)
    with db.tx() as conn:
        held = habridge.claims.owners(conn, addon["vehicle_id"])
    return JSONResponse(
        {"ok": True, "ha": states is not None, "rows": rows, "taken": {f: h["name"] for f, h in held.items() if h["pk"] != addon["id"]}}
    )


@app.get("/v/{vid}/integrations/{aid}/bridge/entities")
def bridge_entities(request: Request, vid: int, aid: int, slot: str = "", q: str = "", all: int = 0):
    """The entities of Home Assistant to choose from for one interface: the likeliest first (the right kind, a fitting class or unit, the words typed)."""
    if (denied := _refused(request)) is not None:
        return denied
    addon = _bridge(vid, aid)
    found = cat.BY_KEY.get(slot)
    if addon is None or found is None:
        return JSONResponse({"ok": False, "error": "gone"}, status_code=404)
    states = ha.all_states()
    if states is None:
        return JSONResponse({"ok": True, "ha": False, "entities": []})
    return JSONResponse({"ok": True, "ha": True, "entities": habridge.suggest(found, q[:80], bool(all), states, context=halive.registry())})
