"""Routes: the pages of installed integrations (page modules). Everything is per vehicle; a stopped integration has no page."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import RedirectResponse, Response

from . import addons, auth_web, config, db, events, framehead, frametheme, navigation, pagemods
from .web import app, form_dict, go, render, vehicle_ctx, vehicle_or_404


def _view(page: dict, rows: list[dict], reveal: int | None = None) -> list[dict]:
    """What the template shows per entry: the title, the second line, the other values and the byte comparisons."""
    out = []
    fields = page["fields"]
    hidden = pagemods.secret_keys(page)
    title_keys = [f["key"] for f in fields if f["role"] == "title"] or [fields[0]["key"]]
    sub_keys = [f["key"] for f in fields if f["role"] == "subtitle"]
    for r in rows:
        d = r["data"]
        facts, diffs = [], []
        for f in fields:
            value = d.get(f["key"], "")
            if f["key"] in title_keys or f["key"] in sub_keys:
                continue
            if f["type"] == "hex" and f.get("compare"):
                diffs.append(
                    {
                        "key": f["key"],
                        "old_line": " ".join(
                            c["old"]
                            for c in pagemods.byte_diff(d.get(f["compare"], ""), value or d.get(f["compare"], ""))["cells"]
                            if c["old"]
                        ),
                        "label": f["label"],
                        "old_label": next(x["label"] for x in fields if x["key"] == f["compare"]),
                        "diff": pagemods.byte_diff(
                            d.get(f["compare"], ""), value or d.get(f["compare"], "")
                        ),  # nothing changed yet: now = original
                    }
                )
                continue
            if f["type"] == "hex" and any(x.get("compare") == f["key"] for x in fields):
                continue  # shown inside the comparison of the other field
            if value not in ("", "0") or f["type"] != "bool":
                if f["type"] == "bool":
                    value = "✓"
                if value and f["type"] == "secret":  # the code itself is in the page only after "Show" for this entry
                    facts.append(
                        {"key": f["key"], "label": f["label"], "value": value if reveal == r["id"] else "••••••", "kind": "secret"}
                    )
                elif value:
                    facts.append({"key": f["key"], "label": f["label"], "value": value, "kind": f["type"]})
        out.append(
            {
                "id": r["id"],
                "q": " ".join(str(v) for k, v in d.items() if isinstance(v, str) and k not in hidden).lower()[:3000],
                "changed": sum(len(x["diff"]["changed"]) for x in diffs),
                "data": d,
                "badge": d.get(title_keys[0], "") if len(title_keys) > 1 else "",  # a short code in front (an address, a number)
                "title": " · ".join(d.get(k, "") for k in (title_keys[1:] if len(title_keys) > 1 else title_keys) if d.get(k)) or "–",
                "subtitle": " · ".join(d.get(k, "") for k in sub_keys if d.get(k)),
                "facts": facts,
                "diffs": diffs,
                "bits_json": d.get("_bits", ""),
                "groups_json": d.get("_groups", ""),
            }
        )
    return out


def _frame_address(request: Request, conn, vehicle, page: dict) -> str:
    """The address of a frame page with what the page may use: language, car, units, design and the ready-made addresses of the design (variables, kit),
    of the head and of the map tiles."""
    from urllib.parse import quote

    from . import ha, themes, units, userprefs

    base = request.state.base
    theme = themes.current(conn)
    me = auth_web._acting_user(request, conn) if ha.network_port()[1] is not None else None
    mine = userprefs.get(conn, me["id"] if me else None, "design")
    if mine and mine in themes.available():
        theme = mine
    if vehicle["theme"] and vehicle["theme"] in themes.available():
        theme = vehicle["theme"]
    sep = "&" if "?" in page["route"] else "?"
    css = quote(f"{base}/frame-theme.css?theme={theme}", safe="")
    kit = quote(f"{base}/frame-kit.css?theme={theme}", safe="")
    tiles = quote(f"{base}/tiles", safe="")
    return f"{base}{page['route']}{sep}lang={config.language()}&car={vehicle['id']}&units={units.of().system}&theme={theme}&css={css}&kit={kit}&tiles={tiles}"


def _context(conn, vehicle, mod: dict, page: dict, reveal: int | None = None):
    base = f"/v/{vehicle['slug']}/m/{mod['addon_id']}"
    tabs = (
        [{"href": f"{base}/{p['id']}", "title": p["title"], "on": p["id"] == page["id"]} for p in mod["pages"]]
        if len(mod["pages"]) > 1
        else None
    )
    return {
        **vehicle_ctx(conn, vehicle, navigation.X + mod["addon_id"]),
        "hide_hero": True,
        "mod": mod,
        "page": page,
        "base_url": base + "/" + page["id"],
        "section_tabs": tabs,
        "reveal": reveal,
        "view": _view(page, pagemods.rows(conn, vehicle["id"], mod["addon_id"], page["id"], page.get("order")), reveal),
    }


def _show(request: Request, vid: int, addon_id: str, page_id: str | None, form=None, error=None, edit_id=None, status=200):
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        mod = pagemods.module(conn, vid, addon_id)
        page = pagemods.page_of(mod, page_id) if mod else None
        if mod is None or page is None:
            return go(request, f"/v/{vid}/integrations", "addon.err_id")
        if (
            page.get("kind") == "frame"
        ):  # the page of the package IS the page: opened as a whole window with the head of Car Assistant on it
            return RedirectResponse(_frame_address(request, conn, vehicle, page), status_code=303)
        if page.get("kind") == "plan":
            from . import reminders

            rs = next((r for r in reminders.status(conn, vid) if r["addon_id"] == addon_id and r["id"] == page["reminder"]), None)
            addon = next((a for a in addons.list_for(conn, vid) if a["addon_id"] == addon_id), None)
            return render(
                request,
                "plan_page.html",
                **vehicle_ctx(conn, vehicle, navigation.X + addon_id),
                hide_hero=True,
                mod=mod,
                page=page,
                rs=rs,
                addon=addon,
                base_url=f"/v/{vehicle['slug']}/m/{addon_id}/{page['id']}",
            )
        raw = request.query_params.get("reveal", "")
        ctx = _context(conn, vehicle, mod, page, int(raw) if raw.isdigit() else None)
    response = render(request, "module_page.html", status=status, form=form or {}, error=error, edit_id=edit_id, **ctx)
    if ctx["reveal"] is not None:
        response.headers["Cache-Control"] = "no-store"  # a page that shows an access code is never kept
    return response


@app.get("/v/{vid}/m/{addon_id}")
def module_home(request: Request, vid: int, addon_id: str):
    return _show(request, vid, addon_id, None)


@app.get("/v/{vid}/m/{addon_id}/{page_id}")
def module_page(request: Request, vid: int, addon_id: str, page_id: str):
    return _show(request, vid, addon_id, page_id)


async def _save(request: Request, vid: int, addon_id: str, page_id: str, row_id: int | None):
    form = await form_dict(request)
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        mod = pagemods.module(conn, vid, addon_id)
        page = pagemods.page_of(mod, page_id) if mod else None
        if mod is None or page is None:
            return go(request, f"/v/{vid}/integrations", "addon.err_id")
        old = None
        if row_id is not None:
            old = pagemods.get(conn, vid, addon_id, row_id)
            if old is None or old["page"] != page_id:
                return go(request, f"/v/{vid}/m/{addon_id}/{page_id}")
        try:
            if old and form.get("same_as_old"):  # "new = old": a compared field goes back to its original value
                for f in page["fields"]:
                    if f.get("compare"):
                        form[f["key"]] = old["data"].get(f["compare"], "")
            data = pagemods.parse(page, form, old["data"] if old else None, keep_once=False)  # a person may change the original too
            if old:
                pagemods.update(conn, row_id, data)
            else:
                pagemods.add(conn, vid, addon_id, page, data)
        except pagemods.PageError as exc:
            error = exc.args
        else:
            error = None
    if error:
        return _show(request, vid, addon_id, page_id, form=form, error=error, edit_id=row_id, status=400)
    events.changed()
    return go(request, f"/v/{vid}/m/{addon_id}/{page_id}", "saved")


@app.post("/v/{vid}/m/{addon_id}/{page_id}")
async def module_add(request: Request, vid: int, addon_id: str, page_id: str):
    return await _save(request, vid, addon_id, page_id, None)


@app.post("/v/{vid}/m/{addon_id}/{page_id}/{row_id}")
async def module_edit(request: Request, vid: int, addon_id: str, page_id: str, row_id: int):
    return await _save(request, vid, addon_id, page_id, row_id)


@app.post("/v/{vid}/m/{addon_id}/{page_id}/{row_id}/delete")
def module_delete(request: Request, vid: int, addon_id: str, page_id: str, row_id: int):
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        if pagemods.module(conn, vid, addon_id) and (row := pagemods.get(conn, vid, addon_id, row_id)) and row["page"] == page_id:
            pagemods.delete(conn, row_id)
    events.changed()
    return go(request, f"/v/{vid}/m/{addon_id}/{page_id}", "deleted")


@app.post("/v/{vid}/reminders/{addon_id}/{rule_id}/done")
async def reminder_done(request: Request, vid: int, addon_id: str, rule_id: str):
    from . import reminders

    form = await form_dict(request)
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        reminders.done(conn, vid, addon_id, rule_id)
    events.changed()
    return go(request, f"/v/{vehicle['slug']}/e/fuel" if form.get("back") == "fuel" else f"/v/{vehicle['slug']}", "saved")


@app.post("/v/{vid}/m/{addon_id}/{page_id}/{row_id}/move")
async def module_move(request: Request, vid: int, addon_id: str, page_id: str, row_id: int):
    form = await form_dict(request)
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        if pagemods.module(conn, vid, addon_id):
            pagemods.move(conn, vid, addon_id, page_id, row_id, "up" if form.get("way") == "up" else "down")
    events.changed()
    return go(request, f"/v/{vid}/m/{addon_id}/{page_id}")


@app.post("/v/{vid}/reminders/{addon_id}/{rule_id}/plan")
async def reminder_plan(request: Request, vid: int, addon_id: str, rule_id: str):
    """Correct a plan: ``step`` = the step for the next refuel, ``advance`` = one refuel on, ``mark`` + ``filled`` = an entry of the history."""
    from . import reminders

    form = await form_dict(request)
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        if form.get("advance"):
            reminders.plan_set(conn, vid, addon_id, rule_id, advance=True)
        elif form.get("step", "").isdigit():
            reminders.plan_set(conn, vid, addon_id, rule_id, step=int(form["step"]))
        elif form.get("mark", "").isdigit():
            reminders.plan_filled(conn, vid, addon_id, rule_id, int(form["mark"]), form.get("filled") == "1")
        back = f"/v/{vehicle['slug']}/m/{addon_id}"
    events.changed()
    return go(request, back, "saved")


@app.get("/frame-theme.css")
def frame_theme(theme: str = "default"):
    """The design as CSS variables for a page a package shows inside the app (only for signed-in people, like every page)."""
    return Response(frametheme.tokens(theme), media_type="text/css", headers={"Cache-Control": "no-cache"})


@app.get("/frame-head.css")
def frame_head(theme: str = "default"):
    """The style sheet of the head Car Assistant puts above a page of a package."""
    return Response(framehead.css(theme), media_type="text/css", headers={"Cache-Control": "no-cache"})


@app.get("/frame-kit.css")
def frame_kit(theme: str = "default"):
    """The design variables plus the kit (cards, buttons, fields, chips) a package page can link to look like the app."""
    kit = (frametheme.STATIC / "frame-kit.css").read_text(encoding="utf-8")
    return Response(frametheme.tokens(theme) + kit, media_type="text/css", headers={"Cache-Control": "no-cache"})
