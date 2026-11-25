"""Thin client for the Home Assistant Core API through the Supervisor proxy (``homeassistant_api: true``)."""

from __future__ import annotations

import logging
import os
import time

try:
    import requests
except ImportError:  # tools/check_plugin.py reads packages without the rest of the app's requirements; nothing here is called then
    requests = None  # type: ignore[assignment]

from . import config

log = logging.getLogger(__name__)
TIMEOUT = 8
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
