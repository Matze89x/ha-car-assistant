"""Route: the files of a package. Only for signed-in people (the app's own login covers every page that is not public), only while approved."""

from __future__ import annotations

from fastapi import HTTPException
from fastapi.responses import Response

from . import addons, assets, db
from .web import app


@app.get("/plugins/{addon_id}/files/{name}")
def package_file(addon_id: str, name: str):
    if not addons.ID.match(addon_id) or not addons.FILE_NAME.fullmatch(name):
        raise HTTPException(404)
    with db.tx() as conn:
        addon = assets.instance(conn, addon_id)
    if addon is None:
        raise HTTPException(404)
    bundle = next((b for b in addon["m"].get("bundles", []) if b["name"] == name), None)
    if bundle is not None:
        data, ctype = assets.build_bundle(addon, bundle), addons.FILE_TYPES[".zip"]
    else:
        found = assets.read_file(addon, name)
        data, ctype = found if found else (None, "")
    if data is None:
        raise HTTPException(404)
    return Response(
        data,
        media_type=ctype,
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
