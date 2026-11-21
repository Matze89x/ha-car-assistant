"""Integrations: data sources and services that can be switched on/off and configured in the UI.

Settings are stored in the ``settings`` table as ``int.<key>.<field>``; they override the app options (which stay
as defaults). Vehicle connections for specific brands will be added as integrations later (see docs/integrations.md).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from . import config, db


@dataclass(frozen=True)
class Opt:
    name: str
    label: str  # i18n key
    kind: str = "text"  # text | password | bool
    help: str = ""  # i18n key


@dataclass(frozen=True)
class Integration:
    key: str
    category: str  # data | system
    options: tuple[Opt, ...] = ()
    link: str = ""
    toggle: bool = True  # can be disabled


INTEGRATIONS: tuple[Integration, ...] = (
    Integration("homeassistant", "system", (), toggle=False),
    Integration(
        "mqtt",
        "system",
        (
            Opt("host", "int.mqtt_host", "text", "int.mqtt.help"),
            Opt("port", "int.mqtt_port", "text"),
            Opt("username", "int.mqtt_user", "text"),
            Opt("password", "int.mqtt_password", "password"),
        ),
    ),
)
BY_KEY = {i.key: i for i in INTEGRATIONS}


def get(key: str, name: str) -> str | None:
    """Stored value or None. Reads straight from the database (also usable outside a request)."""
    return config.stored_setting(f"int.{key}.{name}")


def is_enabled(key: str) -> bool:
    return config.stored_setting(f"int.{key}.enabled") != "0"


def save(conn: sqlite3.Connection, key: str, form: dict[str, str]) -> None:
    integration = BY_KEY[key]
    if integration.toggle:
        db.set_setting(conn, f"int.{key}.enabled", "1" if form.get("enabled") else "0")
    if form.get("toggle_only"):
        return  # only the switch was moved: the other settings stay as they are
    for opt in integration.options:
        raw = (form.get(opt.name) or "").strip()[:200]
        if opt.kind == "password" and not raw and not form.get(f"{opt.name}__clear"):
            continue  # blank password field = keep the stored secret
        if opt.kind == "password" and raw:
            from . import vault

            raw = vault.encrypt(raw) or ""  # secrets are kept encrypted
        db.set_setting(conn, f"int.{key}.{opt.name}", raw or None)
