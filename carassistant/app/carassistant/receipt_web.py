"""``POST /v/<id>/fuel/scan``: a photo of a fuel receipt in, the fields of a refuel out (see receipt.py). The photo is never stored."""

from __future__ import annotations

import asyncio
import re

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from . import db, odometer_scan, receipt, summary, units
from .web import app, unit_for, vehicle_or_404


def shown(result: dict, u: units.Units, base: str) -> dict:
    """The numbers of a receipt (litres, price per litre) in the units this app shows, as text for the form fields."""
    out = {
        "found": result["found"],
        "checked": result["checked"],
        "derived": result["derived"],
        "station": result["station"],
        "notes": result["notes"],
        "date": result["date"],
    }
    amount = u.v(result["amount"], base) if result["amount"] is not None else None
    price = u.price_vol(result["price_per_unit"], base) if result["price_per_unit"] is not None else None
    out["amount"] = f"{amount:.2f}" if amount is not None else ""
    out["price_per_unit"] = f"{price:.3f}" if price is not None else ""
    out["price_total"] = f"{result['price_total']:.2f}" if result["price_total"] is not None else ""
    return out


@app.post("/v/{vid}/fuel/scan")
async def fuel_scan(request: Request, vid: int):
    if not receipt.available():
        raise HTTPException(501, "text recognition is not installed")
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        base = unit_for(vehicle["fuel_type"])
    try:
        if int(request.headers.get("content-length") or 0) > receipt.MAX_BYTES:
            raise HTTPException(413, "photo too large")
    except ValueError:
        raise HTTPException(400, "bad length") from None
    data = await request.body()
    try:
        result = await asyncio.to_thread(receipt.scan, data)
    except ValueError:
        raise HTTPException(400, "not a photo") from None
    out = shown(result, units.of(vehicle), base)
    if vehicle["fuel2_type"] == "lpg" and re.search(r"autogas|\blpg\b", result["notes"] or "", re.I):
        out["fuel_kind"] = "second"  # the receipt says gas and the car has gas as its second fuel: the fill-up is one of that
    return JSONResponse(out, headers={"Cache-Control": "no-store"})


@app.post("/v/{vid}/odometer/scan")
async def odometer_scan_route(request: Request, vid: int):
    """A photo of the odometer in, the number on it out (in the unit the car is shown in). The photo is never stored."""
    if not receipt.available():
        raise HTTPException(501, "text recognition is not installed")
    with db.tx() as conn:
        vehicle = vehicle_or_404(conn, vid)
        last_km = summary.current_odometer(conn, vid)
    u = units.of(vehicle)
    last = round(u.d(last_km)) if last_km is not None else None
    try:
        if int(request.headers.get("content-length") or 0) > receipt.MAX_BYTES:
            raise HTTPException(413, "photo too large")
    except ValueError:
        raise HTTPException(400, "bad length") from None
    data = await request.body()
    try:
        result = await asyncio.to_thread(odometer_scan.read, data, last)
    except ValueError:
        raise HTTPException(400, "not a photo") from None
    return JSONResponse(
        {"odometer": str(result["value"]) if result["value"] is not None else "", "plausible": result["plausible"], "last": last},
        headers={"Cache-Control": "no-store"},
    )
