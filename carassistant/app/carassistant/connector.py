"""Connectors without code (``connector`` in a plugin.json, docs/plugins.md, "Connectors without code").

A plugin without a service may describe where its values come from: addresses to fetch (GET, https, JSON back) and a ``map`` from places in the answers to the
fields of the Plugin API. The APP does the fetching - every ``every`` seconds, for every car where the plugin is on and set up - and hands what the map found
to the same intake as ``POST /api/v1/vehicles/<id>/data`` (``connectors.ingest``). Nothing of the package is executed: it is a description of addresses and
paths. What keeps it safe: only GET; https only; the host is written out in the address (a setting can fill the path and the query, never the host); a public
address only (checked when it is used); no redirect is followed; 256 kB and 15 seconds at most; the credentials go only into the headers of THIS request; a
failing connector slows down (up to an hour) and says why in the log of the plugin."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import urllib.parse

from . import addons, connectors, db, events, linkmap, oauth
from .sources import _public_host

log = logging.getLogger("carassistant")

LIMIT = 256 * 1024
TIMEOUT = 15
MAX_BACKOFF = 3600
TRUE_WORDS, FALSE_WORDS = {"true", "yes", "on", "1", "y"}, {"false", "no", "off", "0", "n"}


class ConnectorError(Exception):
    """A run failed; the text is for the log of the plugin (never a secret)."""


# ------------------------------------------------------------------ reading an answer


def walk(data, path: str):
    """The value at ``data.items[0].value``. Raises ``KeyError`` when the place is not there."""
    current = data
    for token in re.findall(r"\[\d+\]|[A-Za-z0-9_-]+", path):
        if token.startswith("["):
            index = int(token[1:-1])
            if not isinstance(current, list) or index >= len(current):
                raise KeyError(path)
            current = current[index]
        else:
            if not isinstance(current, dict) or token not in current:
                raise KeyError(path)
            current = current[token]
    return current


def _number(value, entry: dict) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise ValueError("not a number")
    return float(value) * entry.get("scale", 1) + entry.get("offset", 0)


def _flag(value, entry: dict) -> bool:
    mapped = entry.get("values") or {}
    if str(value) in mapped and isinstance(mapped[str(value)], bool):
        return mapped[str(value)]
    if isinstance(value, bool):
        return value
    word = str(value).strip().lower()
    if word in TRUE_WORDS:
        return True
    if word in FALSE_WORDS:
        return False
    raise ValueError("not a yes / no")


def build(spec: dict, answers: dict[str, object]) -> tuple[dict, list[str]]:
    """What the ``map`` finds in the answers: ``(data for the Plugin API intake, notes about what was skipped and why)``. A place that is missing or a
    value that does not fit skips that field only."""
    data: dict = {}
    skipped: list[str] = []
    for entry in spec["map"]:
        field, source = entry["field"], answers[entry["from"]]
        try:
            if field == "position":
                data[field] = {"lat": _number(walk(source, entry["lat"]), {}), "lon": _number(walk(source, entry["lon"]), {})}
            else:
                raw = walk(source, entry["path"])
                if field in connectors.BOOLS or field in ("locked", "ignition"):
                    data[field] = _flag(raw, entry)
                elif field in ("vin", "measured_at"):
                    if isinstance(raw, bool) or not isinstance(raw, str | int | float):
                        raise ValueError("not text")
                    data[field] = raw
                else:
                    data[field] = _number(raw, entry)
        except KeyError:
            skipped.append(f"{field}: nothing at that place of the answer")
        except (ValueError, OverflowError):
            skipped.append(f"{field}: the value does not fit")
    return data, skipped


# ------------------------------------------------------------------ talking to the address


def _fill(text: str, addon: dict, vin: str, quote: bool) -> str:
    """The places ``{vin}`` and ``{setting.key}`` of an address (quoted) or a header (as they are). An empty setting stops the run: no half address."""

    def one(found):
        name = found.group(1)
        value = vin if name == "vin" else str(addon["vals"].get(name[8:], ""))
        if not value:
            raise ConnectorError(f"{'the VIN of the car' if name == 'vin' else 'the setting ' + name[8:]} is empty")
        return urllib.parse.quote(value, safe="") if quote else value

    return addons.CONNECTOR_PLACEHOLDER.sub(one, text)


def _auth(auth: str, addon: dict) -> dict[str, str]:
    kind, *args = auth.split(":")
    vals = addon["vals"]
    if kind == "bearer":
        if not vals.get(args[0]):
            raise ConnectorError(f"the setting {args[0]} is empty")
        return {"Authorization": f"Bearer {vals[args[0]]}"}
    if kind == "basic":
        if not (vals.get(args[0]) and vals.get(args[1])):
            raise ConnectorError(f"the settings {args[0]} and {args[1]} must be filled in")
        import base64

        return {"Authorization": "Basic " + base64.b64encode(f"{vals[args[0]]}:{vals[args[1]]}".encode()).decode()}
    if kind == "header":
        if not vals.get(args[1]):
            raise ConnectorError(f"the setting {args[1]} is empty")
        return {args[0]: vals[args[1]]}
    if kind == "oauth":
        steps = oauth.steps_of(addon)
        if not steps:
            raise ConnectorError("the package says auth oauth but has no login step")
        with db.tx() as conn:
            link = oauth.status(conn, addon["id"], steps[0]["id"])
        if link["id"] is None:
            raise ConnectorError("nobody has logged in yet")
        try:
            got = oauth.fresh(link["id"])
        except oauth.LoginRequired as exc:
            raise ConnectorError("the login has expired - log in again") from exc
        except oauth.OAuthError as exc:
            raise ConnectorError("the provider of the login could not be reached") from exc
        return {"Authorization": f"{got['token_type']} {got['access_token']}"}
    return {}


def _send_get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
    """The one place a connector request leaves the app: ``(status, at most 256 kB of the answer)``."""
    import urllib.error
    import urllib.request

    request = urllib.request.Request(url, headers=headers, method="GET")  # noqa: S310 - https only, checked by the caller
    try:
        with oauth._opener().open(request, timeout=TIMEOUT) as answer:
            return answer.status, answer.read(LIMIT + 1)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(LIMIT + 1)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise ConnectorError("the service could not be reached") from exc


def fetch(url: str, headers: dict[str, str]):
    """GET one address and read its JSON: https, a public host, no redirect, 256 kB, 15 seconds."""
    host = urllib.parse.urlsplit(url).hostname or ""
    if not url.startswith("https://") or not _public_host(host):
        raise ConnectorError("the address is not allowed (https and a public host are needed)")
    status, raw = _send_get(url, {"Accept": "application/json", "User-Agent": "car-assistant", **headers})
    if len(raw) > LIMIT:
        raise ConnectorError("the answer is too big")
    if status >= 300:  # (a redirect is no answer either: it is never followed)
        raise ConnectorError(f"the service answered {status}")
    try:
        return json.loads(raw or b"null")
    except ValueError as exc:
        raise ConnectorError("the answer is not JSON") from exc


# ------------------------------------------------------------------ one run, and the schedule


def run(addon: dict) -> str:
    """One run of the connector of an install: fetch, map, store. Returns a sentence about what was stored; raises ``ConnectorError``."""
    spec = addon["m"]["connector"]
    with db.tx() as conn:
        vin = (conn.execute("SELECT vin FROM vehicles WHERE id = ?", (addon["vehicle_id"],)).fetchone() or {"vin": ""})["vin"] or ""
    answers: dict[str, object] = {}
    started = time.monotonic()
    for request in spec["requests"]:
        headers = {name: _fill(value, addon, vin, False) for name, value in request["headers"].items()}
        headers.update(_auth(request["auth"], addon))
        answers[request["id"]] = fetch(_fill(request["url"], addon, vin, True), headers)
    data, skipped = build(spec, answers)
    if not data:
        raise ConnectorError("nothing in the answer matched the map" + (f" ({'; '.join(skipped[:3])})" if skipped else ""))
    name = addon["m"].get("name") or addon["addon_id"]
    with db.tx() as conn:
        try:
            result = connectors.ingest(conn, addon["vehicle_id"], data, name, caller=addon["id"])
        except connectors.ApiError as exc:
            raise ConnectorError(f"the values were refused: {exc.message[:150]}") from exc
        fields = sorted(k for k in data if k != "measured_at")
        connectors.note_usage(conn, addon["vehicle_id"], addon["addon_id"], "POST", "/api/v1/vehicles/{id}/data", ", ".join(fields))
        linkmap.record(
            conn, addon["vehicle_id"], addon["addon_id"], "POST", ["", "api", "v1", "vehicles", str(addon["vehicle_id"]), "data"], data
        )
        if connectors.debug_enabled(conn, addon["vehicle_id"], addon["addon_id"]):
            connectors.record_traffic(
                conn, addon["vehicle_id"], addon["addon_id"], "api", "POST", f"/api/v1/vehicles/{addon['vehicle_id']}/data", 200, len(json.dumps(data)),
                round((time.monotonic() - started) * 1000), ", ".join(fields),
            )  # fmt: skip
    events.changed()
    note = f"{sum(1 for v in result.values() if v.startswith('stored'))} value(s) stored"
    return note + (f"; skipped: {'; '.join(skipped[:3])}" if skipped else "")


_state: dict[int, dict] = {}  # install -> {"next": when it is due (monotonic), "fails": failures in a row}


def _line(conn, addon: dict, level: str, text: str) -> None:
    connectors.app_log(conn, addon["vehicle_id"], addon["addon_id"], level, "connector", text[:300])  # (also in the log of the add-on)


def tick(now: float | None = None) -> int:
    """Runs every connector that is due (a plugin without a service that has a ``connector``, is on and is set up, on a car that is not archived).
    Returns how many ran. Called every few seconds by ``loop``; tests call it with a clock of their own."""
    now = time.monotonic() if now is None else now
    ran = 0
    with db.tx() as conn:
        rows = conn.execute(
            "SELECT a.id, a.vehicle_id FROM vehicle_addons a JOIN vehicles v ON v.id = a.vehicle_id "
            "WHERE a.active = 1 AND a.status = 'configured' AND a.kind = 'plugin' AND a.manifest LIKE '%\"connector\"%' AND v.archived = 0"
        ).fetchall()
    live = {r["id"] for r in rows}
    for gone in set(_state) - live:  # switched off or removed: it starts afresh when it comes back
        _state.pop(gone, None)
    for row in rows:
        with db.tx() as conn:
            addon = addons.get(conn, row["vehicle_id"], row["id"])
        if addon is None or not addon["m"].get("connector"):
            continue
        state = _state.setdefault(row["id"], {"next": 0.0, "fails": 0})
        if now < state["next"]:
            continue
        ran += 1
        every = addon["m"]["connector"]["every"]
        try:
            note = run(addon)
        except ConnectorError as exc:
            state["fails"] += 1
            state["next"] = now + min(MAX_BACKOFF, every * 2 ** min(state["fails"] - 1, 6))
            with db.tx() as conn:
                _line(
                    conn,
                    addon,
                    "error" if state["fails"] >= 5 else "warn",
                    f"{exc} (try {state['fails']}, next in {int(state['next'] - now)} s)",
                )
        except Exception:
            log.exception("connector of %s failed", addon["addon_id"])
            state["fails"] += 1
            state["next"] = now + min(MAX_BACKOFF, every * 2 ** min(state["fails"] - 1, 6))
            with db.tx() as conn:
                _line(conn, addon, "error", "the connector failed unexpectedly (see the log of the add-on)")
        else:
            with db.tx() as conn:
                if state["fails"]:
                    _line(conn, addon, "info", f"works again: {note}")
                elif connectors.debug_enabled(conn, addon["vehicle_id"], addon["addon_id"]):
                    _line(conn, addon, "debug", note)
            state["fails"], state["next"] = 0, now + every
    return ran


def loop() -> None:
    while not events.stop.is_set():
        try:
            tick()
        except Exception:
            log.exception("connectors: a round failed")
        events.stop.wait(15)


def start() -> threading.Thread:
    thread = threading.Thread(target=loop, name="connectors", daemon=True)
    thread.start()
    return thread
