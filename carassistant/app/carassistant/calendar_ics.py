"""iCalendar export of open appointments (subscribe/import in any calendar app)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r", "").replace("\n", "\\n")


def _fold(line: str) -> str:
    """RFC 5545: lines are folded at 75 octets (never inside a UTF-8 sequence)."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    chunks, current = [], b""
    limit = 75
    for ch in line:
        encoded = ch.encode("utf-8")
        if len(current) + len(encoded) > limit:
            chunks.append(current)
            current, limit = b"", 74  # continuation lines start with a space
        current += encoded
    chunks.append(current)
    return "\r\n ".join(c.decode("utf-8") for c in chunks)


def build(conn: sqlite3.Connection, vehicle_id: int | None = None) -> bytes:
    sql = (
        "SELECT a.*, v.name AS vehicle_name FROM appointments a JOIN vehicles v ON v.id = a.vehicle_id WHERE a.done = 0 AND v.archived = 0"
    )
    params: tuple = ()
    if vehicle_id is not None:
        sql += " AND a.vehicle_id = ?"
        params = (vehicle_id,)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Car Assistant//EN", "CALSCALE:GREGORIAN"]
    for row in conn.execute(sql + " ORDER BY a.due_date", params):
        due = date.fromisoformat(row["due_date"])
        lines += [
            "BEGIN:VEVENT",
            f"UID:appointment-{row['id']}@carassistant",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{due.strftime('%Y%m%d')}",
            f"SUMMARY:{_escape(row['vehicle_name'] + ': ' + row['title'])}",
        ]
        if row["notes"]:
            lines.append(f"DESCRIPTION:{_escape(row['notes'])}")
        lines += [
            "BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:Reminder", "TRIGGER:-P14D", "END:VALARM", "END:VEVENT",
        ]  # fmt: skip
    lines.append("END:VCALENDAR")
    return ("\r\n".join(_fold(line) for line in lines) + "\r\n").encode("utf-8")
