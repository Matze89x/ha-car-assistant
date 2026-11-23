"""The data the connection map loads when somebody opens it: the light state (refreshed), the signals of a plugin / an area and the history of one."""

from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from . import db, linkmap, linkmap_ui
from .connectors_web import _may_manage
from .web import app, vehicle_or_404

NO_STORE = {"Cache-Control": "no-store"}


def _short(raw: str | None) -> str:
    """One line of a raw value for the list: compact, cut."""
    if raw is None:
        return ""
    return raw if len(raw) <= 80 else raw[:79] + "…"


@app.get("/v/{vid}/plugins/connections/graph.json")
def links_graph(vid: int):
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        return JSONResponse(linkmap_ui.light(linkmap_ui.build(conn, vid)), headers=NO_STORE)


@app.get("/v/{vid}/plugins/connections/signals.json")
def links_signals(request: Request, vid: int, plugin: str = "", area: str = "", limit: int = 200):
    if not plugin and not area:
        raise HTTPException(400, "plugin or area")
    from . import config, i18n

    t = i18n.translator(config.language())
    raw_ok = _may_manage(request)
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        rows = linkmap.signals_of(conn, vid, plugin or None, area or None, limit)
        names = {p["id"]: p["name"] for p in linkmap_ui.build(conn, vid)["plugins"]}
    out = [
        {
            "plugin": r["addon_id"],
            "plugin_name": names.get(r["addon_id"], r["addon_id"]),
            "dir": r["direction"],
            "name": r["name"],
            "area": r["area"],
            "hits": r["hits"],
            "ts": r["last_ts"],
            "ago": linkmap_ui.ago(r["last_ts"], t),
            "value": _short(r["last_value"]) if raw_ok else None,
            "has_value": r["last_value"] is not None,
        }
        for r in rows
    ]
    return JSONResponse({"signals": out, "raw": raw_ok}, headers=NO_STORE)


@app.get("/v/{vid}/plugins/connections/history.json")
def links_history(request: Request, vid: int, plugin: str, name: str, dir: str = "set"):
    if dir not in ("set", "get"):
        raise HTTPException(400, "dir")
    from . import config, i18n

    t = i18n.translator(config.language())
    raw_ok = _may_manage(request)
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        state = conn.execute(
            "SELECT last_value, last_ts FROM signal_state WHERE vehicle_id = ? AND addon_id = ? AND direction = ? AND name = ?",
            (vid, plugin, dir, name),
        ).fetchone()
        history = linkmap.history_of(conn, vid, plugin, dir, name)
    body = {
        "raw": raw_ok,
        "value": state["last_value"] if state and raw_ok else None,
        "ts": state["last_ts"] if state else None,
        "history": [{"ts": h["ts"], "ago": linkmap_ui.ago(h["ts"], t), "value": h["value"] if raw_ok else None} for h in history],
    }
    return JSONResponse(body, headers=NO_STORE)
