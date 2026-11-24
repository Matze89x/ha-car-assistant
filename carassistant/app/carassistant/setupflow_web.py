"""The free set-up flow of a plugin (``setup.flow`` in its plugin.json, docs/plugins.md, "The set-up flow").

The three fixed steps of the older guide (check, token, files) stay for every package that has no ``flow``. A package WITH a flow decides itself which steps
there are and in which order: text, requirements, a form (user name and password are just settings), a check by the plugin's own service, the token, files,
a page of the plugin and a file the service makes (a ZIP). Everything about a step is read, never executed; the only code that runs is the plugin's own
service (approved by an administrator) when a step asks it (``check`` and ``download``) - a route that is NOT public.

The token travels from step to step inside the page only (never stored), exactly as in the older guide."""

from __future__ import annotations

import re

from fastapi import Request
from fastapi.responses import Response

from . import addons, assets, auth_web, config, connectors, db, events, i18n, pluginsvc
from .connectors_web import _may_manage
from .web import app, form_dict, go, render, vehicle_ctx, vehicle_or_404

ICONS = {
    "text": "info",
    "requirements": "lock",
    "form": "settings",
    "check": "shield",
    "token": "lock",
    "files": "download",
    "page": "puzzle",
    "download": "download",
}
FILE_TYPES = {"application/zip", "application/octet-stream", "text/plain", "text/csv", "application/json"}
NEEDS = {
    "external_https": ("guide.need_external_https", "guide.missing_external_https"),
    "vehicle_vin": ("guide.need_vehicle_vin", "guide.missing_vehicle_vin"),
}


def _guard(request: Request, vid: int):
    return None if _may_manage(request) else go(request, f"/v/{vid}/integrations", "acct.need_admin")


def steps_of(addon: dict, tr) -> list[dict]:
    """The steps in the language of the page: title (the plugin's own, else the name of the type), text as safe HTML, label of the main button."""
    lang = config.language()
    out = []
    for n, s in enumerate(addon["m"]["setup"]["flow"], 1):
        own = (s.get("l10n") or {}).get(lang) or {}
        text = own.get("text") or s.get("text") or ""
        out.append(
            {
                **s,
                "n": n,
                "title": own.get("title") or s.get("title") or tr(f"flow.type_{s['type']}"),
                "label": own.get("label") or s.get("label") or "",
                "html": addons.render_text(text) if text else "",
                "icon": ICONS[s["type"]],
            }
        )
    return out


def needs_of(addon: dict, vehicle, step: dict, tr) -> list[dict]:
    """What a ``requirements`` step waits for: the app's own checks (address, VIN) and settings that must have a value."""
    out = []
    values = {
        "external_https": (bool(config.external_url()), config.external_url() or "", "/settings/system#external"),
        "vehicle_vin": (bool(vehicle["vin"]), vehicle["vin"] or "", f"/v/{vehicle['slug']}/edit?mode=form"),
    }
    for key in step.get("requires", []):
        ok, value, link = values[key]
        out.append({"ok": ok, "label": tr(NEEDS[key][0]), "value": value, "missing": tr(NEEDS[key][1]), "link": link})
    fields = {f["key"]: f for f in addon["m"].get("settings", [])}
    for key in step.get("filled", []):
        out.append(
            {
                "ok": bool(addon["vals"].get(key)),
                "label": fields[key]["label"],
                "value": "",
                "missing": tr("flow.need_setting"),
                "link": f"/v/{vehicle['slug']}/integrations/{addon['id']}/settings",
            }
        )
    return out


def page(
    request: Request,
    vid: int,
    aid: int,
    step: int = 1,
    token: str = "",
    *,
    fresh: bool = False,
    errors: dict | None = None,
    shown: dict | None = None,
    status: int = 200,
    result: dict | None = None,
    kind: str = "",
    done: str = "",
):
    """One step of the flow as a page. ``kind`` jumps to the first step of that type (the older routes of the token and the files ask for it)."""
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        addon = addons.get(conn, vid, aid)
        if addon is None or not (addon["m"].get("setup") or {}).get("flow"):
            return go(request, f"/v/{vid}/plugins", "addon.err_id")
        ctx = vehicle_ctx(conn, vehicle, "integrations")
        known = addon.get("token_id") if addon["m"].get("connection_file") else None
        fingerprint = connectors.fingerprint(conn, known)
    tr = i18n.translator(config.language())
    steps = steps_of(addon, tr)
    if kind:
        step = next((s["n"] for s in steps if s["type"] == kind), step)
    step = max(1, min(step, len(steps)))
    for s in steps[:step]:  # a step of requirements that is not met stops everything behind it
        if s["type"] == "requirements" and not all(c["ok"] for c in needs_of(addon, vehicle, s, tr)):
            step = s["n"]
            break
    cur = steps[step - 1]
    needs = needs_of(addon, vehicle, cur, tr) if cur["type"] == "requirements" else []
    keys = set(cur.get("settings", []))
    fields = [f for f in addon["m"].get("settings", []) if f["key"] in keys] if cur["type"] in ("form", "check", "download") else []
    offered = pluginsvc.approved(addon)
    rows = {r["name"]: r for r in assets.listing(addon, offered)} if cur["type"] == "files" else {}
    return render(
        request,
        "addon_flow.html",
        status=status,
        **ctx,
        hide_hero=True,
        addon=addon,
        steps=steps,
        now=cur,  # not `cur`: the page context already has a currency of that name
        step=step,
        needs=needs,
        ready=all(c["ok"] for c in needs),
        fields=fields,
        shown=shown if shown is not None else addon["vals"],
        errors={k: tr(v) for k, v in (errors or {}).items()},
        result=result,
        token=token,
        fresh=fresh,
        done=done,
        has_token=bool(known),
        fingerprint=fingerprint,
        bundle_rows=[{**rows[n], "entries": []} for n in cur.get("bundles", []) if n in rows],
        pkg_offered=offered,
        has_file=bool(cur.get("connection_file")),
        texts={"files": ""},  # the text of a step is shown above the step's own block
        file_name=(addon["m"].get("connection_file") or {}).get("name", ""),
        last=step == len(steps),
        back_to=f"/v/{vid}/{'plugins' if addon['kind'] == 'plugin' else 'integrations'}",
    )


def _typed(addon: dict, form: dict, keys: set[str]) -> dict:
    """What was typed in a step, typed like settings.json (numbers as numbers, passwords as they are): what a check or a download sends to the service."""
    sub = addons.guide_manifest(addon, keys)
    return addons.typed_settings(sub, addons._guide_values(addon, form, keys))


def _file_name(headers: dict, addon_id: str, step_id: str, ctype: str) -> str:
    """The name the service suggested, cleaned: only the last part of a path, letters, digits and ``._-``, never a leading dot."""
    wanted = re.search(r'filename="?([^";]{1,100})"?', headers.get("content-disposition", ""))
    raw = wanted.group(1).replace("\\", "/").rsplit("/", 1)[-1] if wanted else ""
    name = re.sub(r"[^A-Za-z0-9._-]", "_", raw)[:80].lstrip("._-")
    return name or f"{addon_id}-{step_id}.{'zip' if ctype == 'application/zip' else 'bin'}"


@app.post("/v/{vid}/integrations/{aid}/guide/flow")
async def flow_post(request: Request, vid: int, aid: int):
    """Every button of the flow: *Back*, the main button of a step (next / check / finish), a new token, the file the service makes."""
    if (denied := _guard(request, vid)) is not None:
        return denied
    form = await form_dict(request)
    try:
        step = int(form.get("step", "1"))
    except ValueError:
        step = 1
    do = (form.get("do") or "next")[:12]
    carried = (form.get("token") or "").strip()[:200]
    tr = i18n.translator(config.language())
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        addon = addons.get(conn, vid, aid)
        if addon is None or not (addon["m"].get("setup") or {}).get("flow"):
            return go(request, f"/v/{vid}/plugins", "addon.err_id")
        who = auth_web._acting_user(request, conn)
    steps = steps_of(addon, tr)
    step = max(1, min(step, len(steps)))
    cur = steps[step - 1]
    user = str(who["id"]) if who else "ha"
    if do == "back":
        return page(request, vid, aid, step - 1, carried)

    if cur["type"] == "requirements" and not all(c["ok"] for c in needs_of(addon, vehicle, cur, tr)):
        return page(request, vid, aid, step, carried, status=409)

    if cur["type"] == "token" and do == "new":
        if addon["kind"] != "plugin":
            return go(request, f"/v/{vid}/plugins", "addon.err_id")
        with db.tx() as conn:
            token = addons.new_token(conn, vid, addon)
        if pluginsvc.service_of(addon):
            pluginsvc.write_token(addon, token)
            pluginsvc.restart(addon["id"])
        return page(request, vid, aid, step, token, fresh=True)

    if cur["type"] in ("form", "check", "download") and do in ("next", "check", "make"):
        keys = set(cur.get("settings", []))
        if keys:
            errors = addons.check_settings(addons.guide_manifest(addon, keys), addons.guide_form(addon, form, keys), addon["vals"])
            if errors:
                return page(
                    request, vid, aid, step, carried, errors=errors, shown=addons._guide_values(addon, form, keys) | form, status=400
                )
        answer: dict = {}
        message, headers, body = "", {}, b""
        if cur["type"] in ("check", "download"):  # the service is asked FIRST: nothing wrong is stored, and it sees what was typed
            if not addon["active"] or not pluginsvc.approved(addon):
                return page(
                    request, vid, aid, step, carried, shown=form, result={"ok": False, "message": tr("addon.button_off")}, status=409
                )
            payload = {
                "vehicle": vid,
                "step": cur["id"],
                "language": config.language(),
                "values": _typed(addon, form, keys),  # what this step asked for
                "settings": addons.typed_settings(
                    addon["m"], addons._guide_values(addon, form, keys)
                ),  # all settings, with what was just typed
            }
            if cur["type"] == "check":
                ok, message, answer = pluginsvc.ask(addon["id"], cur["action"], payload, vid, user)
            else:
                ok, message, headers, body = pluginsvc.fetch(addon["id"], cur["action"], payload, vid, user)
            if not ok:
                if message in ("not running", "no answer"):
                    message = tr("addon.button_down")
                return page(
                    request,
                    vid,
                    aid,
                    step,
                    carried,
                    shown=form,
                    result={"ok": False, "message": message or tr("addon.button_failed")},
                    status=422,
                )
        refused = ""
        with db.tx() as conn:
            if keys:
                addons.save_flow_values(conn, addons.get(conn, vid, aid), form, keys)
            changes = answer.get("settings")
            if (
                isinstance(changes, dict) and changes
            ):  # what the service learned (a token it was given, a name): only settings it may write itself
                try:
                    addons.service_set(conn, addons.get(conn, vid, aid), changes)
                except addons.SettingError as exc:
                    refused = str(exc)
        if refused:
            return page(request, vid, aid, step, carried, shown=form, result={"ok": False, "message": refused[:200]}, status=422)
        if keys and pluginsvc.service_of(addon):
            pluginsvc.restart(addon["id"])  # settings.json is written again at the start
        events.changed()
        if cur["type"] == "download":
            ctype = (headers.get("content-type") or "").split(";")[0].strip().lower()
            ctype = ctype if ctype in FILE_TYPES else "application/octet-stream"
            return Response(
                body,
                media_type=ctype,
                headers={
                    "Content-Disposition": f'attachment; filename="{_file_name(headers, addon["addon_id"], cur["id"], ctype)}"',
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                },
            )
        if cur["type"] == "check":  # on to the next step, with what the plugin said ("Logged in as ...")
            if step >= len(steps):
                return _finish(request, vid, aid, carried)
            return page(request, vid, aid, step + 1, carried, result={"ok": True, "message": message} if message else None)

    if do == "finish" or (do == "next" and step >= len(steps)):
        return _finish(request, vid, aid, carried)
    return page(request, vid, aid, step + 1, carried)


def _finish(request: Request, vid: int, aid: int, carried: str):
    """The last step: the plugin counts as set up (a plugin that has no token yet gets one here, shown once)."""
    with db.tx() as conn:
        addon = addons.get(conn, vid, aid)
        if addon is None:
            return go(request, f"/v/{vid}/plugins", "addon.err_id")
        made = addons.set_up(conn, vid, addon, {}, set())
    if made and pluginsvc.service_of(addon):
        pluginsvc.write_token(addon, made)
        pluginsvc.restart(addon["id"])
    events.changed()
    if made:
        return page(request, vid, aid, 10_000, made, fresh=True, done="token")
    return go(request, f"/v/{vid}/{'plugins' if addon['kind'] == 'plugin' else 'integrations'}", "saved")
