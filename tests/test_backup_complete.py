"""A backup of a car leaves nothing of that car behind - and a new table or setting cannot be forgotten (docs/backup.md).

Every table of the database is named in exactly one place of ``vehiclebackup`` (backed up, handled by name, deliberately skipped, or part of the
system backup only), and every setting that the code keeps per car is part of the backup or named as skipped."""

import json
import re
from pathlib import Path

from tests.test_vehicle_backup import _car, _restore

from carassistant import addons, db, vehiclebackup

APP = Path(vehiclebackup.__file__).parent


def test_every_table_is_named_exactly_once(client):
    groups = {
        "backed up (LISTS)": set(vehiclebackup.LISTS),
        "handled by name": set(vehiclebackup.HANDLED),
        "skipped on purpose": set(vehiclebackup.SKIPPED_TABLES),
        "system backup only": set(vehiclebackup.SYSTEM_TABLES),
    }
    names = [t for group in groups.values() for t in group]
    assert len(names) == len(set(names)), "a table is named in two places: " + ", ".join(sorted({t for t in names if names.count(t) > 1}))
    with db.tx() as conn:
        tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")}
    assert tables - set(names) == set(), (
        "a table of the database is not named in vehiclebackup.py (back it up, or say why not): " + ", ".join(sorted(tables - set(names)))
    )
    assert set(names) - tables == set(), "vehiclebackup.py names a table that does not exist: " + ", ".join(sorted(set(names) - tables))


def test_every_setting_of_a_car_is_backed_up_or_named():
    found: set[str] = set()
    for path in APP.glob("*.py"):
        found |= set(re.findall(r'f"([a-z0-9_.]+)\.\{(?:vehicle_id|vid)\}"', path.read_text(encoding="utf-8")))
    known = set(vehiclebackup.SETTINGS) | set(vehiclebackup.SETTINGS_SKIPPED)
    assert found - known == set(), (
        "a setting kept per car is not in vehiclebackup.SETTINGS (back it up) or SETTINGS_SKIPPED (say why not): "
        + ", ".join(sorted(found - known))
    )


def test_what_a_car_has_comes_back_with_it(client):
    car = _car(client)
    vid = car["id"]
    with db.tx() as conn:
        fuel = conn.execute(
            "INSERT INTO fuel(vehicle_id, date, odometer_km, amount, price_per_unit, price_total, full_tank) VALUES(?, '2026-02-01', 1200, 40, 0.3, 12, 1)",
            (vid,),
        ).lastrowid
        conn.execute(
            "INSERT INTO charge_sessions(vehicle_id, started, ended, start_pct, end_pct, max_kw, odometer_km, fuel_id) "
            "VALUES(?, '2026-02-01T08:00:00', '2026-02-01T09:00:00', 20, 80, 11, 1200, ?)",
            (vid, fuel),
        )
        conn.execute("INSERT INTO charge_sessions(vehicle_id, started, start_pct) VALUES(?, '2026-02-02T08:00:00', 30)", (vid,))
        conn.execute(
            "INSERT INTO trip_summaries(vehicle_id, ts, distance_km, consumption, avg_kmh, minutes) VALUES(?, '2026-02-03T10:00:00', 12.5, 6.1, 40, 19)",
            (vid,),
        )
        conn.execute(
            "INSERT INTO vehicle_events(vehicle_id, ts, type, text, value, lat, lon) VALUES(?, '2026-02-03T10:00:00', 'door', 'Boot opened', 1, 50.1, 8.2)",
            (vid,),
        )
        conn.execute(
            "INSERT INTO vehicle_track(vehicle_id, ts, lat, lon, speed_kmh) VALUES(?, '2026-02-03T10:00:00', 50.1, 8.2, 31)", (vid,)
        )
        conn.execute(
            "INSERT INTO vehicle_signals(vehicle_id, name, value, updated) VALUES(?, 'cabin.temp', '21.5', '2026-02-03T10:00:00')", (vid,)
        )
        conn.execute(
            "INSERT INTO signal_state(vehicle_id, addon_id, direction, name, area, hits, last_ts, last_value) VALUES(?, 'sim-plugin', 'set', 'odometer_km', 'dashboard', 3, '2026-02-03T10:00:00', '1200')",
            (vid,),
        )
        conn.execute(
            "INSERT INTO signal_history(vehicle_id, addon_id, direction, name, ts, value) VALUES(?, 'sim-plugin', 'set', 'odometer_km', '2026-02-03T10:00:00', '1200')",
            (vid,),
        )
        conn.execute(
            "INSERT INTO plugin_usage(vehicle_id, addon_id, method, endpoint, fields, hits, last_seen) VALUES(?, 'sim-plugin', 'POST', '/api/v1/data', 'odometer_km', 4, '2026-02-03T10:00:00')",
            (vid,),
        )
        db.set_setting(conn, f"charge.home_price.{vid}", "0.31")
        db.set_setting(conn, f"manual.last.{vid}", "7")
        manifest = addons.parse_package(json.dumps({"id": "sim-plugin", "kind": "plugin", "name": "Sim", "version": "1"}).encode())
        pk = addons.add(conn, vid, manifest)
        conn.execute(
            "INSERT INTO addon_deliveries(addon_pk, name, version, delivered_at, settings_hash) VALUES(?, 'link.cfg', '1', '2026-02-03T10:00:00', 'abc')",
            (pk,),
        )
        data = vehiclebackup.export(conn, vid)
    assert _restore(client, data).status_code == 303
    with db.tx() as conn:
        new = conn.execute("SELECT id FROM vehicles WHERE id != ?", (vid,)).fetchone()["id"]
        for table, wanted in (
            ("charge_sessions", 2), ("trip_summaries", 1), ("vehicle_events", 1), ("vehicle_track", 1), ("vehicle_signals", 1),
            ("signal_state", 1), ("signal_history", 1), ("plugin_usage", 1),
        ):  # fmt: skip
            assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE vehicle_id = ?", (new,)).fetchone()[0] == wanted, table
        session = conn.execute("SELECT fuel_id FROM charge_sessions WHERE vehicle_id = ? AND ended IS NOT NULL", (new,)).fetchone()
        refuel = conn.execute("SELECT id FROM fuel WHERE vehicle_id = ?", (new,)).fetchone()
        assert (
            refuel["id"] != fuel and session["fuel_id"] == refuel["id"]
        )  # the session still points at ITS refuel, not at the one of the original car
        assert (
            conn.execute("SELECT fuel_id FROM charge_sessions WHERE vehicle_id = ? AND ended IS NULL", (new,)).fetchone()["fuel_id"] is None
        )
        assert db.get_setting(conn, f"charge.home_price.{new}") == "0.31" and db.get_setting(conn, f"manual.last.{new}") == "7"
        item = addons.list_for(conn, new)[0]
        delivered = conn.execute("SELECT name, settings_hash FROM addon_deliveries WHERE addon_pk = ?", (item["id"],)).fetchone()
        assert (
            delivered["name"] == "link.cfg" and delivered["settings_hash"] == "abc"
        )  # what was handed out follows the new number of its add-on
