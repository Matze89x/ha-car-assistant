"""``POST /registration/scan``: a photo or a PDF of a registration certificate (the "Fahrzeugschein") in, the fields of the vehicle pass out (see
registration.py). The picture is never stored and nothing leaves this server. The route belongs to no car: the form that adds a car uses it too."""

from __future__ import annotations

import asyncio

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from . import receipt, registration
from .web import app


@app.post("/registration/scan")
async def registration_scan(request: Request):
    if not receipt.available():
        raise HTTPException(501, "text recognition is not installed")
    try:
        if int(request.headers.get("content-length") or 0) > registration.MAX_BYTES:
            raise HTTPException(413, "photo too large")
    except ValueError:
        raise HTTPException(400, "bad length") from None
    data = await request.body()
    try:
        result = await asyncio.to_thread(registration.scan_file, data)  # a photo or a PDF
    except ValueError:
        raise HTTPException(400, "not a photo") from None
    return JSONResponse(result, headers={"Cache-Control": "no-store"})
