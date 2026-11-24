"""Export of the fill-ups / charging sessions of one car: a period to pick (7 / 30 days, this or last month, this or last year, everything,
or your own dates) and CSV or PDF."""

from __future__ import annotations

import csv
import io
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from . import trips

RANGES = ("all", "7d", "30d", "month", "lastmonth", "year", "lastyear", "custom")
COLUMNS = ("date", "odometer", "amount", "price_unit", "price_total", "full_tank", "station", "notes")


def resolve_range(kind: str | None, start: str | None, end: str | None, today: date | None = None) -> tuple[str, str]:
    """(first day, last day) as ISO dates for a named period; ``all`` is wide open."""
    today = today or date.today()
    kind = kind if kind in RANGES else "all"
    if kind == "7d":
        return (today - timedelta(days=6)).isoformat(), today.isoformat()
    if kind == "30d":
        return (today - timedelta(days=29)).isoformat(), today.isoformat()
    if kind == "month":
        return today.replace(day=1).isoformat(), today.isoformat()
    if kind == "lastmonth":
        last = today.replace(day=1) - timedelta(days=1)
        return last.replace(day=1).isoformat(), last.isoformat()
    if kind == "year":
        return today.replace(month=1, day=1).isoformat(), today.isoformat()
    if kind == "lastyear":
        return date(today.year - 1, 1, 1).isoformat(), date(today.year - 1, 12, 31).isoformat()
    if kind == "custom":
        first, last = trips.parse_range(start, end)
        return first, last
    return "0000-01-01", "9999-12-31"


def fills_in_range(conn: sqlite3.Connection, vehicle_id: int, first: str, last: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM fuel WHERE vehicle_id = ? AND date >= ? AND date <= ? ORDER BY date ASC, COALESCE(odometer_km, 0) ASC, id ASC",
        (vehicle_id, first, last),
    ).fetchall()


def columns(fuels: dict[str, str] | None = None) -> list[str]:
    """The columns of the export; a bi-fuel car (``fuels`` names its two fuels) gets one more after the amount: which fuel it was."""
    cols = list(COLUMNS)
    if fuels:
        cols.insert(3, "fuel_kind")
    return cols


def _cells(row: sqlite3.Row, conv, fuels: dict[str, str] | None = None) -> list[str]:
    def num(value, digits=None):
        return "" if value is None else (f"{value:.{digits}f}" if digits is not None else f"{value:g}")

    second = bool(fuels) and row["fuel_kind"] == "second"  # the second fuel has its own unit (``vol2`` / ``price2``)
    vol = conv.get("vol2", conv["vol"]) if second else conv["vol"]
    price = conv.get("price2", conv["price"]) if second else conv["price"]
    cells = [
        row["date"],
        num(None if row["odometer_km"] is None else conv["dist"](row["odometer_km"])),
        num(None if row["amount"] is None else vol(row["amount"]), 2),
        num(None if row["price_per_unit"] is None else price(row["price_per_unit"]), 3),
        num(row["price_total"], 2),
        "1" if row["full_tank"] else "0",
        row["station"] or "",
        (row["notes"] or "").replace("\n", " "),
    ]
    if fuels:
        cells.insert(3, fuels["second" if second else "main"])
    return cells


def csv_bytes(rows: list[sqlite3.Row], labels: dict[str, str], conv: dict, fuels: dict[str, str] | None = None) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";")
    writer.writerow([labels[k] for k in columns(fuels)])
    for r in rows:
        writer.writerow(_cells(r, conv, fuels))
    return ("﻿" + out.getvalue()).encode("utf-8")  # a BOM: Excel reads the umlauts right


def pdf_bytes(
    vehicle: sqlite3.Row,
    rows: list[sqlite3.Row],
    first: str,
    last: str,
    labels: dict[str, str],
    conv: dict,
    fuels: dict[str, str] | None = None,
) -> bytes:
    from fpdf import FPDF

    pdf = FPDF(orientation="L", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    regular = next((p for p in trips._FONT_CANDIDATES if Path(p).exists()), None)
    if regular:
        pdf.add_font("body", "", regular)
        family = "body"

        def clean(text: str) -> str:
            return text
    else:
        family = "Helvetica"

        def clean(text: str) -> str:  # core fonts are latin-1 only
            return text.encode("latin-1", "replace").decode("latin-1")

    pdf.set_font(family, size=14)
    plate = f" ({vehicle['plate']})" if vehicle["plate"] else ""
    pdf.cell(0, 8, clean(f"{labels['title']} – {vehicle['name']}{plate}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(family, size=9)
    period = labels["all"] if first.startswith("0000") else f"{first} – {last}"
    pdf.cell(0, 5, clean(f"{labels['period']}: {period}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    widths = (24, 28, 24, 22, 28, 28, 22, 60, 41) if fuels else (24, 28, 24, 28, 28, 22, 60, 63)  # the page is 277 mm wide
    pdf.set_font(family, size=8)
    pdf.set_fill_color(230, 230, 230)
    for key, width in zip(columns(fuels), widths, strict=True):
        pdf.cell(width, 6, clean(labels[key]), border=1, fill=True)
    pdf.ln()
    total = 0.0
    for r in rows:
        cells = _cells(r, conv, fuels)
        total += r["price_total"] or 0
        for value, width in zip(cells, widths, strict=True):
            pdf.cell(width, 5.5, clean(value[: int(width / 1.9)]), border=1)
        pdf.ln()
    pdf.ln(2)
    pdf.set_font(family, size=9)
    pdf.cell(0, 5, clean(f"{labels['price_total']}: {total:.2f}"), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
