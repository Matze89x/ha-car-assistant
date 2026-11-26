"""The golden backup files of tests/fixtures/backups/: every format that ever existed stays restorable (docs/backup.md, "Compatibility").

A golden file is made once, by the code of its own format, and is never edited or made again (README there). When ``FORMAT`` grows, the new file is
added first - ``test_every_format_has_its_golden_file`` fails until it is. A newer Car Assistant restores every one of them."""

import json
import re
from pathlib import Path

import pytest

from carassistant import addons, backup, backupsecrets, connectors, db, vault, vehiclebackup

FIX = Path(__file__).parent / "fixtures" / "backups"


def _numbers(pattern: str) -> list[int]:
    return sorted(int(re.search(r"format(\d+)", p.name).group(1)) for p in FIX.glob(pattern))


def _facts(n: int) -> dict:
    return json.loads((FIX / f"expected-format{n}.json").read_text(encoding="utf-8"))


def test_every_format_has_its_golden_file():
    assert _numbers("vehicle-format*.zip") == list(range(vehiclebackup.MIN_FORMAT, vehiclebackup.FORMAT + 1)), (
        "a new vehicle backup format needs its golden file first"
    )
    assert _numbers("system-format*.zip") == list(range(backup.MIN_FORMAT, backup.FORMAT + 1)), (
        "a new system backup format needs its golden file first"
    )
    assert _numbers("expected-format*.json") == _numbers("vehicle-format*.zip")


@pytest.fixture(autouse=True)
def quick_scrypt(monkeypatch):
    monkeypatch.setattr(backupsecrets, "SCRYPT_N", 2**10)  # (a golden file carries its own cost: this is only for what a test makes itself)


@pytest.mark.parametrize("n", _numbers("vehicle-format*.zip"))
def test_a_golden_vehicle_backup_of_every_format_restores(client, n):
    facts = _facts(n)
    with db.tx() as conn:
        new_id = vehiclebackup.restore(conn, (FIX / f"vehicle-format{n}.zip").read_bytes(), facts.get("passphrase", ""))
    with db.tx() as conn:
        assert conn.execute("SELECT name FROM vehicles WHERE id = ?", (new_id,)).fetchone()["name"] == facts["vehicle_name"]
        for table, count in facts["list_counts"].items():  # every list the format had comes back with all its rows
            assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE vehicle_id = ?", (new_id,)).fetchone()[0] == count, table
        points = conn.execute(
            "SELECT COUNT(*) FROM trip_points p JOIN trips t ON t.id = p.trip_id WHERE t.vehicle_id = ?", (new_id,)
        ).fetchone()[0]
        assert points == facts["trip_points"]
        assert conn.execute("SELECT COUNT(*) FROM module_rows WHERE vehicle_id = ?", (new_id,)).fetchone()[0] == facts["module_rows"]
        items = {a["addon_id"]: a for a in addons.list_for(conn, new_id)}
        assert set(items) == {"sim-plugin", "coding-demo"}
        assert items["sim-plugin"]["vals"] == facts["plugin_settings"]
        assert items["sim-plugin"]["token_id"] is not None  # the token of the plugin is back (the same hash it already holds)
        if n == 1:  # format 1 carried the kept token readable in the file
            assert connectors.remembered(conn, items["sim-plugin"]["token_id"])
        if n >= 2:  # from format 2 on the secrets travel in the block, opened by the passphrase
            assert connectors.remembered(conn, items["sim-plugin"]["token_id"]) and facts["kept_token"]
            code = json.loads(
                conn.execute(
                    "SELECT data FROM module_rows WHERE vehicle_id = ? AND addon_id = 'coding-demo' ORDER BY sort", (new_id,)
                ).fetchone()[0]
            )["code"]
            assert code == facts["access_code"]
            assert db.get_setting(conn, f"charge.home_price.{new_id}") == facts["home_price"]
            delivered = conn.execute(
                "SELECT name, settings_hash FROM addon_deliveries WHERE addon_pk = ?", (items["sim-plugin"]["id"],)
            ).fetchone()
            assert dict(delivered) == facts["delivered"]
            session = conn.execute("SELECT fuel_id FROM charge_sessions WHERE vehicle_id = ?", (new_id,)).fetchone()
            assert conn.execute(
                "SELECT 1 FROM fuel WHERE id = ? AND vehicle_id = ?", (session["fuel_id"], new_id)
            ).fetchone()  # it points at ITS refuel


@pytest.mark.parametrize("n", _numbers("system-format*.zip"))
def test_a_golden_system_backup_of_every_format_restores(client, n):
    facts = _facts(n)
    backup.restore((FIX / f"system-format{n}.zip").read_bytes(), facts.get("passphrase", ""))
    with db.tx() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == len(db.MIGRATIONS)  # an older schema is brought up to date
        cars = conn.execute("SELECT id, name FROM vehicles").fetchall()
        assert [c["name"] for c in cars] == [facts["vehicle_name"]]
        for table, count in facts["list_counts"].items():
            assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE vehicle_id = ?", (cars[0]["id"],)).fetchone()[0] == count, table
        assert conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] >= 1
        items = {a["addon_id"]: a for a in addons.list_for(conn, cars[0]["id"])}
        assert set(items) == {"sim-plugin", "coding-demo"}
        if n >= 2:  # the secrets of the block are sealed with the key of THIS system again
            assert items["sim-plugin"]["vals"]["account_pw"] == facts["plugin_settings"]["account_pw"]
            assert connectors.remembered(conn, items["sim-plugin"]["token_id"]) and facts["kept_token"]
            assert (
                vault.decrypt(conn.execute("SELECT token FROM sources WHERE url = 'https://example.com/packages'").fetchone()[0])
                == facts["source_key"]
            )
            assert vault.decrypt(db.get_setting(conn, "push.vapid_private")) == facts["push_key"]
            assert (
                json.loads(conn.execute("SELECT data FROM module_rows WHERE addon_id = 'coding-demo' ORDER BY sort").fetchone()[0])["code"]
                == facts["access_code"]
            )
