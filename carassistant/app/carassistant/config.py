"""Runtime configuration. Everything comes from environment variables set by run.sh (app options)."""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path


def data_dir() -> Path:
    path = Path(os.environ.get("CARASSISTANT_DATA", "./data")).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def files_dir() -> Path:
    path = data_dir() / "files"
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "carassistant.db"


_settings: tuple[float, dict[str, str]] | None = None
SETTINGS_SECONDS = 2.0


def forget_settings() -> None:
    """Drop the remembered settings (called after every write, so the next read sees it)."""
    global _settings
    _settings = None


def stored_setting(key: str) -> str | None:
    """Value saved through the UI (settings table) or None. Never raises - before the first migration there is no table.
    The whole (small) table is read at once and remembered for a moment: pages ask for the language, units and modules dozens of times and
    every question used to open its own database connection."""
    global _settings
    now = time.monotonic()
    if _settings is None or now - _settings[0] > SETTINGS_SECONDS:
        path = db_path()
        if not path.exists():
            return None
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
            try:
                rows = {k: v for k, v in conn.execute("SELECT key, value FROM settings") if v not in (None, "")}
            finally:
                conn.close()
        except sqlite3.Error:
            return None
        _settings = (now, rows)
    return _settings[1].get(key)


def language() -> str:
    from . import i18n

    lang = (stored_setting("language") or "en").lower()
    return lang if lang in i18n.CATALOGS else "en"


def log_level() -> str:
    return os.environ.get("CARASSISTANT_LOG_LEVEL", "info").upper()


def mqtt_discovery_enabled() -> bool:
    if stored_setting("int.mqtt.enabled") is not None:
        return stored_setting("int.mqtt.enabled") == "1"
    return os.environ.get("MQTT_SENSORS") == "1"  # off until it is switched on - here or in the add-on configuration


def tankerkoenig_key() -> str:
    """The user's own Tankerkönig key (Settings -> System). There is no built-in key and no add-on option: everyone gets their own."""
    return (stored_setting("int.tankerkoenig.api_key") or "").strip()


def _plain(secret: str | None) -> str | None:
    from . import vault

    return vault.decrypt(secret) or None


def mqtt_settings() -> dict | None:
    """Broker credentials. Default: the Home Assistant broker as announced by the Supervisor (no password to enter).
    A manually entered host (Integrations page) overrides it, e.g. for an external broker."""
    manual = (stored_setting("int.mqtt.host") or "").strip()
    if manual:
        try:
            port = int(stored_setting("int.mqtt.port") or 1883)
        except ValueError:
            port = 1883
        return {
            "host": manual,
            "port": port,
            "user": stored_setting("int.mqtt.username"),
            "password": _plain(stored_setting("int.mqtt.password")),
        }
    host = os.environ.get("MQTT_HOST", "").strip()
    if not host:
        return None
    return {
        "host": host,
        "port": int(os.environ.get("MQTT_PORT", "1883") or 1883),
        "user": os.environ.get("MQTT_USER") or None,
        "password": os.environ.get("MQTT_PASSWORD") or None,
    }


def supervisor_token() -> str:
    return os.environ.get("SUPERVISOR_TOKEN", "")


def ha_api_base() -> str:
    return os.environ.get("CARASSISTANT_HA_API", "http://supervisor/core/api")


def port() -> int:
    return int(os.environ.get("CARASSISTANT_PORT", "8099"))


def dev_mode() -> bool:
    """Dev mode disables the ingress-only source IP check (local testing)."""
    return os.environ.get("CARASSISTANT_DEV", "") == "1"


_ext_cache: tuple[float, str] | None = None


def _stored_external() -> str:
    global _ext_cache
    now = time.monotonic()
    if _ext_cache is None or now - _ext_cache[0] > 5:  # read the database at most every 5 seconds (this runs on every request)
        value = (stored_setting("ext.url") or "").strip().rstrip("/")
        _ext_cache = (now, value if value.startswith(("http://", "https://")) else "")
    return _ext_cache[1]


def forget_external() -> None:
    global _ext_cache
    _ext_cache = None


def clean_external_url(raw: str) -> str:
    """The address typed in Settings -> System: https, a host (and port), no path, no login, no parameters. '' removes it."""
    from urllib.parse import urlsplit

    text = (raw or "").strip().rstrip("/")
    if not text:
        return ""
    parts = urlsplit(text)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
        or len(text) > 200
    ):
        raise ValueError("err.ext_url")
    return f"https://{parts.netloc}"


def external_url() -> str:
    """Optional public URL under which the UI is reachable (e.g. via a reverse proxy), entered in Settings -> System."""
    return _stored_external()


def supervisor_api_base() -> str:
    return os.environ.get("CARASSISTANT_SUPERVISOR_API", "http://supervisor")
