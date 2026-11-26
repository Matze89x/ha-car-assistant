"""The free set-up flow of a plugin (``setup.flow`` in its plugin.json, docs/plugins.md, "The set-up flow").

The three fixed steps of the older guide (check, token, files) stay for every package that has no ``flow``. A package WITH a flow decides itself which steps
there are and in which order: text, requirements, a form (user name and password are just settings), a check by the plugin's own service, the token, files,
a page of the plugin and a file the service makes (a ZIP). Everything about a step is read, never executed; the only code that runs is the plugin's own
service (approved by an administrator) when a step asks it (``check`` and ``download``) - a route that is NOT public.

The token travels from step to step inside the page only (never stored), exactly as in the older guide."""

from __future__ import annotations

import asyncio
import re
import secrets
import time
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import Response

from . import addons, assets, auth_web, config, connectors, db, events, i18n, oauth, pluginsvc
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
    "oauth": "key-variant",
}
FILE_TYPES = {"application/zip", "application/octet-stream", "text/plain", "text/csv", "application/json"}
NEEDS = {
    "external_https": ("guide.need_external_https", "guide.missing_external_https"),
    "vehicle_vin": ("guide.need_vehicle_vin", "guide.missing_vehicle_vin"),
}


CARRY_SECONDS = 600
_carry: dict[str, tuple[float, int, str, dict[str, str]]] = {}  # token -> (until, add-on, step, {password setting: what was typed})


def _keep(aid: int, step_id: str, passwords: dict[str, str]) -> str:
    """The passwords typed in a step, kept IN MEMORY for a few minutes while the service asks for one more thing (a code): the person types the code and
    not the password again. Nothing of it is ever written down; the page carries only the random token of this memory."""
    now = time.monotonic()
    for token in [t for t, held in _carry.items() if held[0] < now]:
        _carry.pop(token, None)
    if len(_carry) > 100:  # a flood guard: the oldest go first
        for token in sorted(_carry, key=lambda t: _carry[t][0])[:50]:
            _carry.pop(token, None)
    token = secrets.token_urlsafe(18)
    _carry[token] = (now + CARRY_SECONDS, aid, step_id, {k: v for k, v in passwords.items() if v})
    return token


def _carried(token: str, aid: int, step_id: str) -> dict[str, str]:
    held = _carry.get((token or "")[:40])
    return dict(held[3]) if held and held[0] >= time.monotonic() and held[1] == aid and held[2] == step_id else {}


def _asked_for(answer: dict, ask_keys: set[str]) -> set[str]:
    """The one-time inputs the service asks for in its answer (``{"ask": ["code"]}``): only those the step declared with ``ask: true``."""
    wanted = answer.get("ask")
    return {k for k in wanted if isinstance(k, str) and k in ask_keys} if isinstance(wanted, list) else set()


async def _service_ready(addon: dict, seconds: float = 15.0) -> bool:
    """A service that was restarted a moment ago (new settings, a new token) needs a little time: the flow waits for it - 15 seconds at most - before it asks."""
    end = time.monotonic() + seconds
    while not pluginsvc.ready(addon["id"]):
        if time.monotonic() >= end:
            return False
        await asyncio.sleep(0.25)
    return True


def _say(exc: oauth.OAuthError, tr) -> str:
    """What went wrong with a login, for the person: our words, then what the provider said (short, cleaned)."""
    return tr(exc.key) + (f" ({exc.detail})" if exc.detail else "")


def _login_context(addon: dict, step: dict) -> dict:
    """What the page of a step of type ``oauth`` shows: connected or not, the login that was begun (its address opens in a new tab), where the provider
    sends the person back to, and the two hosts the app talks to - the one the person logs in at and the one the tokens are exchanged with."""
    spec = step["oauth"]
    uri = oauth.redirect_uri_of(spec, config.external_url() or "")
    with db.tx() as conn:
        link = oauth.status(conn, addon["id"], step["id"])
        begun = oauth.pending(conn, addon["id"], step["id"]) is not None
        try:
            oauth.provider(addon, step)
            client_ok = True
            url = oauth.pending_url(conn, addon, step) if begun else ""
        except oauth.OAuthError:
            client_ok, url = False, ""
    return {
        **link,
        "begun": begun and bool(url),
        "url": url,
        "mode": spec["redirect"],
        "redirect_uri": uri,
        "need_external": spec["redirect"] == "app" and not uri,
        "client_ok": client_ok,
        "host": urlsplit(spec["authorize_url"]).hostname or "",
        "token_host": urlsplit(spec["token_url"]).hostname or "",
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
    asked: set[str] | frozenset[str] = frozenset(),
    carry: str = "",
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
    if cur["type"] == "check":
        fields = [
            *fields,
            *addons.input_fields(cur, asked),
        ]  # the one-time inputs: always the ones without ``ask``, the others once asked for
    offered = pluginsvc.approved(addon)
    login = _login_context(addon, cur) if cur["type"] == "oauth" else None
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
        login=login,
        asked=",".join(sorted(asked)),
        carry=carry,
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
        token_free=not addons.file_has_secret(addon["m"]),
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


def _typed_inputs(inputs: list[dict], form: dict) -> dict:
    """What was typed in the one-time inputs of a check, typed like settings: sent to the service with the check, never stored."""
    if not inputs:
        return {}
    sub = {"settings": inputs}
    return addons.typed_settings(sub, addons.clean_settings(sub, form, {}))


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

    if cur["type"] == "oauth" and do in ("start", "paste", "forget", "next", "finish"):
        return await _oauth_post(request, vid, aid, step, cur, addon, do, form, carried, steps, tr)

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
        ask_keys = {f["key"] for f in cur.get("inputs", []) if f.get("ask")}
        asked = {k for k in (form.get("asked") or "").split(",") if k in ask_keys}
        inputs = addons.input_fields(cur, asked) if cur["type"] == "check" else []
        passwords = {f["key"] for f in addon["m"].get("settings", []) if f["key"] in keys and f["type"] == "password"}
        for key, value in _carried(form.get("carry", ""), aid, cur["id"]).items():  # typed before the service asked for a code
            if key in passwords and not form.get(key):
                form[key] = value

        def again(**more):  # the same step once more, with the one-time inputs the service has asked for (and the passwords kept in memory)
            token = _keep(aid, cur["id"], {k: form.get(k, "") for k in passwords}) if (asked or more.get("asked")) else ""
            return page(request, vid, aid, step, carried, shown=form, carry=token, **{"asked": asked, **more})

        if keys or inputs:
            errors = (
                addons.check_settings(addons.guide_manifest(addon, keys), addons.guide_form(addon, form, keys), addon["vals"])
                if keys
                else {}
            )
            if inputs:
                errors |= addons.check_settings({"settings": inputs}, form, {})
            if errors:
                return page(
                    request,
                    vid,
                    aid,
                    step,
                    carried,
                    errors=errors,
                    shown=addons._guide_values(addon, form, keys) | form,
                    asked=asked,
                    carry=form.get("carry", ""),
                    status=400,
                )
        answer: dict = {}
        message, headers, body = "", {}, b""
        if cur["type"] in ("check", "download"):  # the service is asked FIRST: nothing wrong is stored, and it sees what was typed
            if not addon["active"] or not pluginsvc.approved(addon):
                return page(
                    request, vid, aid, step, carried, shown=form, result={"ok": False, "message": tr("addon.button_off")}, status=409
                )
            if not await _service_ready(addon):
                return page(
                    request, vid, aid, step, carried, shown=form, result={"ok": False, "message": tr("addon.button_down")}, status=422
                )
            payload = {
                "vehicle": vid,
                "step": cur["id"],
                "language": config.language(),
                "values": {**_typed(addon, form, keys), **_typed_inputs(inputs, form)},  # what this step asked for
                "settings": addons.typed_settings(
                    addon["m"], addons._guide_values(addon, form, keys)
                ),  # all settings, with what was just typed
            }
            if cur["type"] == "check":
                ok, message, answer = pluginsvc.ask(addon["id"], cur["action"], payload, vid, user)
                if wanted := _asked_for(answer, ask_keys):  # not a failure: the service needs one more thing to finish the login
                    return again(asked=asked | wanted, result={"ok": None, "ask": True, "message": message or tr("flow.ask_more")})
            else:
                ok, message, headers, body = pluginsvc.fetch(addon["id"], cur["action"], payload, vid, user)
            if not ok:
                if message in ("not running", "no answer"):
                    message = tr("addon.button_down")
                return again(result={"ok": False, "message": message or tr("addon.button_failed")}, status=422)
        _carry.pop((form.get("carry") or "")[:40], None)  # the check passed: the passwords kept for a follow-up question are forgotten
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


async def _oauth_post(request, vid: int, aid: int, step: int, cur: dict, addon: dict, do: str, form: dict, carried: str, steps: list, tr):
    """The buttons of a step of type ``oauth``: *Log in* (the login begins, the page shows its address), *Finish* with the address the person pasted,
    *Disconnect*, and *Next* - which waits until there is a connection."""
    back = f"/v/{vid}/integrations/{aid}/guide?step={step}"
    if do == "start":
        uri = oauth.redirect_uri_of(cur["oauth"], config.external_url() or "")
        if not uri:
            return page(request, vid, aid, step, carried, result={"ok": False, "message": tr("oauth.need_external")}, status=409)
        try:
            with db.tx() as conn:
                oauth.begin(conn, addon, cur, uri)
        except oauth.OAuthError as exc:
            return page(request, vid, aid, step, carried, result={"ok": False, "message": _say(exc, tr)}, status=422)
        return go(
            request, back
        )  # the page shows the address of the login; it opens in a new tab (a login page cannot live inside this frame)
    if do == "forget":
        with db.tx() as conn:
            oauth.forget(conn, aid, cur["id"])
        events.changed()
        return go(request, back)
    if do == "paste":
        code, state, error = oauth.parse_pasted(form.get("pasted", ""))
        if error:
            with db.tx() as conn:
                conn.execute("DELETE FROM oauth_pending WHERE addon_pk = ? AND step = ?", (aid, cur["id"]))
            return page(
                request,
                vid,
                aid,
                step,
                carried,
                result={"ok": False, "message": f"{tr('err.oauth_refused')} ({oauth._plain(error)})"},
                status=422,
            )
        if not code:
            return page(request, vid, aid, step, carried, result={"ok": False, "message": tr("oauth.paste_none")}, status=422)
        if not state:  # a bare code: it belongs to the login that was begun on this step
            with db.tx() as conn:
                begun = oauth.pending(conn, aid, cur["id"])
            state = begun["state"] if begun else ""
        try:
            await asyncio.to_thread(oauth.finish, state, code, (aid, cur["id"]))
        except oauth.OAuthError as exc:
            return page(request, vid, aid, step, carried, result={"ok": False, "message": _say(exc, tr)}, status=422)
        events.changed()
        return page(request, vid, aid, step, carried, result={"ok": True, "message": tr("oauth.connected")})
    with db.tx() as conn:  # next / finish: only with a connection
        connected = oauth.status(conn, aid, cur["id"])["connected"]
    if not connected:
        return page(request, vid, aid, step, carried, result={"ok": False, "message": tr("oauth.need_login")}, status=409)
    if do == "finish" or step >= len(steps):
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
