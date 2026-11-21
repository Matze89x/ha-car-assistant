"""``/tiles/<z>/<x>/<y>.png`` - map tiles for the location map (see tiles.py)."""

from __future__ import annotations

from fastapi import HTTPException
from fastapi.responses import Response

from . import db, tiles
from . import status as vehicle_status
from .web import app


@app.get("/tiles/{z}/{x}/{y}.png")
def map_tile(z: int, x: int, y: int):
    with db.tx() as conn:
        if not vehicle_status.map_tiles_enabled(conn):
            raise HTTPException(404)
    if not tiles.valid(z, x, y):
        raise HTTPException(404)
    data = tiles.get(z, x, y)
    if data is None:
        raise HTTPException(502)
    return Response(data, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})
