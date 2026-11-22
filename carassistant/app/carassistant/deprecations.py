"""What of the Plugin API is announced as deprecated (docs/api.md, "Stability and compatibility").

Nothing is deprecated today, so both lists are empty. The day something has to change, it is entered HERE (and in the changelog and the docs): from then
on every answer of that endpoint carries the standard HTTP headers ``Deprecation: true``, ``Sunset: <date>`` (when a date is set) and a ``Link`` to the
docs, and an answer to a request that used a deprecated field says so in ``deprecated``. A plugin author sees it in the first test run - and the
function itself keeps working until its date.

An entry: ``{"since": "0.9.0", "sunset": date(2027, 6, 1) or None, "use": "what to use instead"}``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from email.utils import format_datetime

DOCS = "https://github.com/Matze89x/ha-car-assistant/blob/main/docs/api.md#stability-and-compatibility-a-promise-to-everyone-who-writes-plugins"

# (HTTP method, address with {id} for the vehicle) -> entry
ENDPOINTS: dict[tuple[str, str], dict] = {}
# a field of the body of POST /api/v1/vehicles/<id>/data -> entry
FIELDS: dict[str, dict] = {}


def _sunset(entry: dict) -> str | None:
    day = entry.get("sunset")
    if not isinstance(day, date):
        return None
    return format_datetime(datetime(day.year, day.month, day.day, tzinfo=UTC), usegmt=True)


def headers(entries: list[dict]) -> dict[str, str]:
    """The headers for an answer that touched deprecated things (the earliest sunset date counts)."""
    if not entries:
        return {}
    out = {"Deprecation": "true", "Link": f'<{DOCS}>; rel="deprecation"'}
    days = sorted(e["sunset"] for e in entries if isinstance(e.get("sunset"), date))
    if days:
        out["Sunset"] = _sunset({"sunset": days[0]}) or ""
    return out


def for_endpoint(method: str, template: str) -> list[dict]:
    entry = ENDPOINTS.get((method.upper(), template))
    return [entry] if entry else []


def used_fields(data) -> list[dict]:
    """The deprecated fields a request body used, for the answer: ``[{"field", "since", "sunset", "use"}]``."""
    if not isinstance(data, dict):
        return []
    return [
        {
            "field": name,
            "since": e.get("since"),
            "sunset": e["sunset"].isoformat() if isinstance(e.get("sunset"), date) else None,
            "use": e.get("use"),
        }
        for name, e in FIELDS.items()
        if name in data
    ]
