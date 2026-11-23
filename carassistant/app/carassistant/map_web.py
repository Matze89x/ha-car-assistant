"""The page *Map* (``/v/<id>/map``): the car and - when the person allows it in the browser - their own position on a full-area map, a search
for a destination and the way to send it on: to the plugin of the car (when it offers ``navigate``) or to a navigation service. See navproviders.py."""

from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from . import auth_web, config, db, i18n, navproviders, places, status
from .web import app, render, vehicle_ctx, vehicle_or_404

SEARCH = {
    "google": "https://www.google.com/maps/search/?api=1&query={q}",
    "apple": "https://maps.apple.com/?q={q}",
    "waze": "https://waze.com/ul?q={q}&navigate=yes",
    "bing": "https://www.bing.com/maps?q={q}",
    "osm": "https://www.openstreetmap.org/search?query={q}",
}


def _providers(conn, vid: int) -> tuple[list[dict], str]:
    rows, first = navproviders.options(conn, vid)
    out = []
    for r in rows:
        if r["plugin"]:
            out.append({"key": r["key"], "name": r["name"], "plugin": True})
        else:
            out.append(
                {
                    "key": r["key"],
                    "name": r["name"],
                    "plugin": False,
                    "url": navproviders.BY_KEY[r["key"]][1],
                    "search": SEARCH.get(r["key"], ""),
                }
            )
    return out, first


@app.get("/v/{vid}/map")
def map_page(request: Request, vid: int):
    t = i18n.translator(config.language())
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        live = status.rows(conn, vid)
        place = status.location(live, t)
        tiles_on = status.map_tiles_enabled(conn)
        providers, first = _providers(conn, vid)
        ctx = vehicle_ctx(conn, vehicle, "map")
    return render(
        request, "map_page.html", **ctx, place=place, map_tiles=tiles_on, providers=providers, provider_first=first, map_page=True
    )


@app.get("/v/{vid}/map/car.json")
def map_car(vid: int):
    """The position of the car now (the map asks every 20 seconds while it is open)."""
    t = i18n.translator(config.language())
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        place = status.location(status.rows(conn, vid), t)
    if place is None:
        return JSONResponse({"lat": None}, headers={"Cache-Control": "no-store"})
    return JSONResponse(
        {"lat": float(place["lat"]), "lon": float(place["lon"]), "title": place["title"]}, headers={"Cache-Control": "no-store"}
    )


@app.get("/v/{vid}/map/search")
def map_search(vid: int, q: str = "", bbox: str = ""):
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        if not status.map_tiles_enabled(conn):
            raise HTTPException(404)
    area = None
    try:
        parts = [float(x) for x in bbox.split(",")]
        if len(parts) == 4 and -90 <= parts[0] <= parts[2] <= 90 and -180 <= parts[1] <= parts[3] <= 180:
            area = (parts[0], parts[1], parts[2], parts[3])
    except ValueError:
        area = None
    results = places.search(q, config.language(), area)
    if results is None:
        raise HTTPException(502, "search service did not answer")
    return JSONResponse({"results": results}, headers={"Cache-Control": "no-store"})


@app.post("/v/{vid}/map/send")
async def map_send(request: Request, vid: int):
    """A destination to the plugin of the car. Body: ``{key, lat, lon, name, address}``; answer ``{ok, message}``."""
    try:
        body = await request.json()
        lat, lon = float(body["lat"]), float(body["lon"])
        key = str(body["key"])
    except (ValueError, KeyError, TypeError):
        raise HTTPException(400, "bad request") from None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or not key.startswith(navproviders.PLUGIN):
        raise HTTPException(400, "bad request")
    with db.tx() as conn:
        vehicle_or_404(conn, vid)
        who = auth_web._acting_user(request, conn)
        ok, message = navproviders.send(
            conn, vid, key, lat, lon, str(body.get("name") or ""), str(body.get("address") or ""), str(who["id"]) if who else "ha"
        )
    return JSONResponse({"ok": ok, "message": message}, headers={"Cache-Control": "no-store"})
