"""SQLite access. One short-lived connection per unit of work; WAL mode; schema versioned via PRAGMA user_version."""

from __future__ import annotations

import contextlib
import sqlite3
from collections.abc import Iterator
from pathlib import Path

from . import config

SCHEMA_DIR = Path(__file__).parent

# Each entry upgrades the database by one version. Never edit an entry that has shipped – append a new one.
MIGRATIONS: list[str] = [
    (SCHEMA_DIR / "schema.sql").read_text(encoding="utf-8"),
    (SCHEMA_DIR / "migrations_2.sql").read_text(encoding="utf-8"),  # km counters, parts
    (SCHEMA_DIR / "migrations_3.sql").read_text(encoding="utf-8"),  # accounts, sessions, passkeys
    (SCHEMA_DIR / "migrations_4.sql").read_text(encoding="utf-8"),  # plugin API tokens
    (SCHEMA_DIR / "migrations_5.sql").read_text(encoding="utf-8"),  # vehicle data: technical details and papers
    (SCHEMA_DIR / "migrations_6.sql").read_text(encoding="utf-8"),  # integrations and plugins per vehicle
    (SCHEMA_DIR / "migrations_7.sql").read_text(encoding="utf-8"),  # readable vehicle addresses (slug)
    (SCHEMA_DIR / "migrations_8.sql").read_text(encoding="utf-8"),  # battery capacity (kWh)
    (SCHEMA_DIR / "migrations_9.sql").read_text(encoding="utf-8"),  # debug log lines sent by a vehicle
    (SCHEMA_DIR / "migrations_10.sql").read_text(encoding="utf-8"),  # energy view and warning levels
    (SCHEMA_DIR / "migrations_11.sql").read_text(encoding="utf-8"),  # indexes for per-vehicle reads and cascades
    (SCHEMA_DIR / "migrations_12.sql").read_text(encoding="utf-8"),  # photo and video library per vehicle
    (SCHEMA_DIR / "migrations_13.sql").read_text(
        encoding="utf-8"
    ),  # vehicles.units / vehicles.currency: unused (units are a server setting)
    (SCHEMA_DIR / "migrations_14.sql").read_text(encoding="utf-8"),  # passcode (app lock) per login
    (SCHEMA_DIR / "migrations_15.sql").read_text(encoding="utf-8"),  # chosen photo + optional chosen video per vehicle
    (SCHEMA_DIR / "migrations_16.sql").read_text(encoding="utf-8"),  # one Notes field (parts_note merged into notes)
    (SCHEMA_DIR / "migrations_17.sql").read_text(encoding="utf-8"),  # video_id dropped (Home = media_id, lists = photo_id)
    (SCHEMA_DIR / "migrations_18.sql").read_text(encoding="utf-8"),  # first registration, engine oil, seats, gross weight
    (SCHEMA_DIR / "migrations_19.sql").read_text(encoding="utf-8"),  # sources: one server-wide list of package sources
    (SCHEMA_DIR / "migrations_20.sql").read_text(
        encoding="utf-8"
    ),  # sources: key, check state, package index; installed packages know their source
    (SCHEMA_DIR / "migrations_21.sql").read_text(encoding="utf-8"),  # sources: clean automatic name, notes of the last check
    (SCHEMA_DIR / "migrations_22.sql").read_text(encoding="utf-8"),  # sources: one source serves Integrations and Plugins alike
    (SCHEMA_DIR / "migrations_23.sql").read_text(encoding="utf-8"),  # page modules: entries of an integration's pages
    (SCHEMA_DIR / "migrations_24.sql").read_text(encoding="utf-8"),  # vehicles.theme: an own design per car
    (SCHEMA_DIR / "migrations_25.sql").read_text(encoding="utf-8"),  # user_notify: notifications per user
    (SCHEMA_DIR / "migrations_26.sql").read_text(encoding="utf-8"),  # vehicle_track, vehicle_signals: Plugin API
    (SCHEMA_DIR / "migrations_27.sql").read_text(encoding="utf-8"),  # user_prefs: preferences per user
    (SCHEMA_DIR / "migrations_28.sql").read_text(encoding="utf-8"),  # vehicle_track.trip_id: trips made from the track
    (SCHEMA_DIR / "migrations_29.sql").read_text(encoding="utf-8"),  # vehicle_events: events reported by a plugin
    (SCHEMA_DIR / "migrations_30.sql").read_text(encoding="utf-8"),  # plugins with their own service
    (SCHEMA_DIR / "migrations_31.sql").read_text(encoding="utf-8"),  # vehicle_logs.addon_id: logs per plugin
    (SCHEMA_DIR / "migrations_32.sql").read_text(encoding="utf-8"),  # vehicle_traffic: calls to watch while debugging
    (SCHEMA_DIR / "migrations_33.sql").read_text(encoding="utf-8"),  # source_packages.icon
    (SCHEMA_DIR / "migrations_34.sql").read_text(encoding="utf-8"),  # vehicle_logs.added: retention by days
    (SCHEMA_DIR / "migrations_35.sql").read_text(encoding="utf-8"),  # plugin_usage: interfaces really used by a plugin
    (SCHEMA_DIR / "migrations_36.sql").read_text(encoding="utf-8"),  # tire_pressure: recommended pressures per season
    (SCHEMA_DIR / "migrations_37.sql").read_text(encoding="utf-8"),  # push_devices: web push per user
    (SCHEMA_DIR / "migrations_38.sql").read_text(encoding="utf-8"),  # equipment: features of a vehicle by category
    (SCHEMA_DIR / "migrations_39.sql").read_text(encoding="utf-8"),  # equipment: categories are fixed keys
    (SCHEMA_DIR / "migrations_40.sql").read_text(encoding="utf-8"),  # tyres: loaded pressure, rear axle
    (SCHEMA_DIR / "migrations_41.sql").read_text(encoding="utf-8"),  # manual: pages and chapters per vehicle
    (SCHEMA_DIR / "migrations_42.sql").read_text(encoding="utf-8"),  # designs: the old ones move to dark / light / day-night + colour
    (SCHEMA_DIR / "migrations_43.sql").read_text(encoding="utf-8"),  # manual: page images, page offset, chapter depth
    (SCHEMA_DIR / "migrations_44.sql").read_text(encoding="utf-8"),  # manual: tappable page references on the image
    (SCHEMA_DIR / "migrations_45.sql").read_text(encoding="utf-8"),  # the car confirmed the VIN that was typed in
    (SCHEMA_DIR / "migrations_46.sql").read_text(encoding="utf-8"),  # place names of trips (map info)
    (SCHEMA_DIR / "migrations_47.sql").read_text(encoding="utf-8"),  # notifications per car
    (SCHEMA_DIR / "migrations_48.sql").read_text(encoding="utf-8"),  # a push device can belong to one car's web app
    (SCHEMA_DIR / "migrations_49.sql").read_text(encoding="utf-8"),  # MCP access: keys and log
    (SCHEMA_DIR / "migrations_50.sql").read_text(encoding="utf-8"),  # own accent colour per car, notifications of a car on / off per person
    (SCHEMA_DIR / "migrations_51.sql").read_text(encoding="utf-8"),  # push devices per car (several cars per device)
    (SCHEMA_DIR / "migrations_52.sql").read_text(encoding="utf-8"),  # notifications: one system per person (matrix of cars and events)
    (SCHEMA_DIR / "migrations_53.sql").read_text(encoding="utf-8"),  # charging sessions noticed from the readings
    (SCHEMA_DIR / "migrations_54.sql").read_text(encoding="utf-8"),  # tyre sets: DOT and rear name move into the notes
    (SCHEMA_DIR / "migrations_55.sql").read_text(encoding="utf-8"),  # documents: note, document date, valid until
    (SCHEMA_DIR / "migrations_56.sql").read_text(encoding="utf-8"),  # plugin tokens: optional encrypted copy
    (SCHEMA_DIR / "migrations_57.sql").read_text(encoding="utf-8"),  # trip values of the car's on-board computer
]


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")  # safe with WAL: no fsync per commit, a crash can only lose the last commit
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA cache_size = -16000")  # 16 MB page cache per connection
    conn.execute("PRAGMA temp_store = MEMORY")
    return conn


@contextlib.contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
        config.forget_settings()  # something may have been written
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate() -> int:
    conn = connect()
    try:
        conn.execute("PRAGMA journal_mode = WAL")  # stays in the file: set once here, not on every connection
        current = conn.execute("PRAGMA user_version").fetchone()[0]
        for version, script in enumerate(MIGRATIONS, start=1):
            if version <= current:
                continue
            conn.executescript(script)
            conn.execute(f"PRAGMA user_version = {version}")
            conn.commit()
        from . import slugs

        slugs.backfill(conn)
        from . import media

        media.import_legacy(conn)
        conn.commit()
        return len(MIGRATIONS)
    finally:
        conn.close()


def get_setting(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row and row["value"] not in (None, "") else default


def set_setting(conn: sqlite3.Connection, key: str, value: str | None) -> None:
    config.forget_settings()
    if value in (None, ""):
        conn.execute("DELETE FROM settings WHERE key = ?", (key,))
    else:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
