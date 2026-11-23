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
    """The sensors in Home Assistant (MQTT): on unless somebody switched them off in the app (Settings -> System). Without a broker nothing happens and
    the System page says so; the add-on option ``mqtt_sensors`` is kept only so that old configurations stay valid - one place decides: the app."""
    stored = stored_setting("int.mqtt.enabled")
    return stored != "0" if stored is not None else True


def ha_notice_sensor_enabled() -> bool:
    """The sensor *Last notification* of every car in Home Assistant (needs MQTT too): on unless somebody switched it off (System tab)."""
    return stored_setting("int.mqtt.notice_sensor") != "0"


HA_GROUPS = ("live", "service", "fuel", "stats", "position")  # what can be sent to Home Assistant, in a few rough groups
HA_GROUPS_OFF_BY_DEFAULT = ("stats",)  # the extra statistics are there for whoever wants them; everything older stays on


def ha_groups_off() -> set[str]:
    """The groups that are NOT sent to Home Assistant (System -> MQTT)."""
    off = set()
    for group in HA_GROUPS:
        stored = stored_setting(f"int.mqtt.group.{group}")
        on = stored == "1" if group in HA_GROUPS_OFF_BY_DEFAULT else stored != "0"
        if not on:
            off.add(group)
    return off


def tankerkoenig_key() -> str:
    """The user's own Tankerkönig key (Settings -> System). There is no built-in key and no add-on option: everyone gets their own."""
    return (stored_setting("int.tankerkoenig.api_key") or "").strip()


def _plain(secret: str | None) -> str | None:
    from . import vault

    return vault.decrypt(secret) or None


def _unset(value: str | None) -> str | None:
    """A text from the add-on configuration: an option that was left empty arrives as the WORD null (bashio), never as nothing."""
    text = (value or "").strip()
    return None if text.lower() in ("", "null", "none") else text


def clean_broker(host: str | None, port: object = None) -> dict | None:
    """What somebody typed for the broker -> ``{host, port, tls}``. Understands ``192.168.1.5``, ``192.168.1.5:1883``, ``mqtt://host:1883`` and
    ``mqtts://host`` (encrypted); a port that is not a number is the usual one (1883, or 8883 when encrypted). None without a host."""
    text = (_unset(host) or "").strip()
    scheme = ""
    if "://" in text:
        scheme, text = text.split("://", 1)
    text = text.split("/", 1)[0].strip()
    typed = None
    if text.startswith("[") and "]" in text:  # [::1]:1883
        rest = text[text.index("]") + 1 :]
        text = text[1 : text.index("]")]
        typed = rest[1:] if rest.startswith(":") else None
    elif text.count(":") == 1:
        text, typed = text.split(":", 1)
    text = text.strip()
    if not text:
        return None
    tls = scheme.lower() in ("mqtts", "ssl", "tls", "tcps", "mqtt+ssl")
    chosen = None
    for candidate in (_unset(str(port)) if port is not None else None, typed):
        try:
            number = int(str(candidate).strip())
        except (TypeError, ValueError):
            continue
        if 1 <= number <= 65535:
            chosen = number
            break
    number = chosen or (8883 if tls else 1883)
    return {"host": text, "port": number, "tls": tls or number == 8883}


def mqtt_settings() -> dict | None:
    """Broker credentials. Default: the Home Assistant broker as announced by the Supervisor (no password to enter).
    A manually entered host (Integrations page) overrides it, e.g. for an external broker."""
    manual = clean_broker(stored_setting("int.mqtt.host"), stored_setting("int.mqtt.port"))
    if manual:
        return {**manual, "user": _unset(stored_setting("int.mqtt.username")), "password": _plain(stored_setting("int.mqtt.password"))}
    given = clean_broker(os.environ.get("MQTT_HOST"), os.environ.get("MQTT_PORT"))
    if not given:
        return None
    return {**given, "user": _unset(os.environ.get("MQTT_USER")), "password": _unset(os.environ.get("MQTT_PASSWORD"))}


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
