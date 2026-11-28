"""Thin client for the Home Assistant Core API through the Supervisor proxy (``homeassistant_api: true``)."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import UTC, datetime

try:
    import requests
except ImportError:  # tools/check_plugin.py reads packages without the rest of the app's requirements; nothing here is called then
    requests = None  # type: ignore[assignment]

from . import config

log = logging.getLogger(__name__)
TIMEOUT = 8
HISTORY_TIMEOUT = 30  # the recorder reads a database: a day of a tracker that reports every few seconds takes a while on a small machine
HISTORY_MAX_BYTES = 16 * 1024 * 1024
ENTITY_ID = re.compile(r"[a-z0-9_]+\.[a-z0-9_]+")
_cache: dict[str, tuple[float, object]] = {}


def _cached(key: str, seconds: float, fetch):
    """Ask Home Assistant / the Supervisor at most once per ``seconds`` (also after a failure). Pages ask for the currency, the port or the entity
    list on nearly every view; without this every view waited for a round trip through the Supervisor (up to ``TIMEOUT`` seconds when it is slow)."""
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and now - hit[0] < seconds:
        return hit[1]
    value = fetch()
    _cache[key] = (now, value)
    return value


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {config.supervisor_token()}", "Content-Type": "application/json"}


def available() -> bool:
    return bool(config.supervisor_token())


def _get(path: str):
    if not available():
        return None
    try:
        resp = requests.get(f"{config.ha_api_base()}{path}", headers=_headers(), timeout=TIMEOUT)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError) as exc:
        log.warning("HA API GET %s failed: %s", path, exc)
        return None


def _supervisor_port() -> tuple[bool, int | None]:
    try:
        resp = requests.get(f"{config.supervisor_api_base()}/addons/self/info", headers=_headers(), timeout=TIMEOUT)
        resp.raise_for_status()
        port = (resp.json().get("data", {}).get("network") or {}).get("8099/tcp")
    except (requests.RequestException, ValueError) as exc:
        log.warning("Supervisor info failed: %s", exc)
        return False, None
    return True, int(port) if isinstance(port, int) else None


def network_port() -> tuple[bool, int | None]:
    """(known, port): the Supervisor says which host port is mapped to the web UI (Add-on -> Configuration -> Network); port None = not mapped."""
    dev = os.environ.get("CARASSISTANT_DEV_NETWORK_PORT", "") if config.dev_mode() else ""
    if dev.isdigit():  # development only (tools/pagecheck.py): act as if the host port is mapped, so the pages that need one are drawn and can be checked without a Supervisor
        return True, int(dev)
    if not available():
        return False, None
    return _cached("port", 20, _supervisor_port)


def published_port() -> int | None:
    """Host port the user mapped for the web UI (Supervisor: Network tab), or None if switched off/unknown."""
    return network_port()[1]


def get_state(entity_id: str) -> dict | None:
    if not entity_id or "." not in entity_id:
        return None
    return _get(f"/states/{entity_id}")


def all_states(seconds: float = 4.0) -> dict[str, dict] | None:
    """Every entity of Home Assistant by its id - ONE request, kept for a few seconds so that every plugin and every page shares it. None when Home Assistant
    cannot be asked (not the add-on, or it does not answer)."""

    def fetch():
        states = _get("/states")
        return (
            {s["entity_id"]: s for s in states if isinstance(s, dict) and isinstance(s.get("entity_id"), str)}
            if isinstance(states, list)
            else None
        )

    return _cached("all_states", seconds, fetch)


def history(entity_ids: list[str], start: datetime, end: datetime) -> dict[str, list[dict]] | None:
    """What the recorder of Home Assistant kept of these entities between two moments: ``{entity id: [state, ...]}`` oldest first, every state with ALL its
    attributes (also those that changed only an attribute - a tracker that moves keeps its state ``not_home``). The first one is the state the entity had at
    ``start`` (Home Assistant gives it that time). The recorder commits every few seconds, so the newest seconds may be missing. None when it cannot be had:
    not the add-on, no recorder (404), an answer that is too large, no answer."""
    if not available() or not entity_ids or not all(ENTITY_ID.fullmatch(e) for e in entity_ids):
        return None
    try:
        resp = requests.get(
            f"{config.ha_api_base()}/history/period/{start.astimezone(UTC).isoformat()}",
            params={"filter_entity_id": ",".join(entity_ids), "end_time": end.astimezone(UTC).isoformat(), "significant_changes_only": "0"},
            headers=_headers(),
            timeout=HISTORY_TIMEOUT,
            stream=True,
        )
        if resp.status_code >= 400:
            log.debug("HA history for %s: HTTP %s", entity_ids, resp.status_code)
            return None
        parts: list[bytes] = []
        size = 0
        for chunk in resp.iter_content(65536):
            size += len(chunk)
            if size > HISTORY_MAX_BYTES:
                log.debug("HA history for %s: more than %d bytes - not taken", entity_ids, HISTORY_MAX_BYTES)
                return None
            parts.append(chunk)
        data = json.loads(b"".join(parts))
    except (requests.RequestException, ValueError) as exc:
        log.debug("HA history for %s failed: %s", entity_ids, exc)
        return None
    out: dict[str, list[dict]] = {}
    for rows in data if isinstance(data, list) else ():
        rows = [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
        if rows and isinstance(rows[0].get("entity_id"), str):
            out[rows[0]["entity_id"]] = [{**r, "entity_id": rows[0]["entity_id"]} for r in rows]
    return out


def get_config() -> dict:
    return _cached("config", 300, lambda: _get("/config") or {})  # country, currency, home location: change almost never


def list_entities(domains: tuple[str, ...] = ("sensor", "device_tracker", "number")) -> list[dict]:
    """Entities for the binding pickers (id + friendly name), sorted by id."""
    return _cached("entities" + ",".join(domains), 30, lambda: _entities(domains))


def _entities(domains: tuple[str, ...]) -> list[dict]:
    states = _get("/states") or []
    result = [
        {"id": s["entity_id"], "name": s.get("attributes", {}).get("friendly_name", "")}
        for s in states
        if s.get("entity_id", "").split(".")[0] in domains
    ]
    return sorted(result, key=lambda e: e["id"])


def call_service(domain: str, service: str, data: dict) -> tuple[bool, str]:
    if not available():
        return False, "Home Assistant API not available (no supervisor token)"
    try:
        resp = requests.post(f"{config.ha_api_base()}/services/{domain}/{service}", json=data, headers=_headers(), timeout=TIMEOUT)
        if resp.status_code >= 400:
            return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
        return True, ""
    except requests.RequestException as exc:
        return False, str(exc)


def country() -> str:
    return str(get_config().get("country") or "").upper()


def currency() -> str:
    return str(get_config().get("currency") or "")
