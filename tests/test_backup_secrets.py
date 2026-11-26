"""Secrets in a backup (docs/backup.md): without a passphrase a backup holds none; with one they travel in one encrypted block and come back."""

import io
import json
import zipfile

import pytest
from tests.test_vehicle_backup import _car

from carassistant import addons, backupsecrets, connectors, db, sources, vault, vehiclebackup

PASSPHRASE = "correct horse battery"
PLUGIN = {
    "id": "sim-plugin",
    "kind": "plugin",
    "name": "Sim plugin",
    "version": "1",
    "settings": [{"key": "mode", "label": "Mode", "type": "text"}, {"key": "account_pw", "label": "Password", "type": "password"}],
}
INTEGRATION = {
    "id": "coding-demo",
    "kind": "integration",
    "name": "Coding demo",
    "version": "1",
    "pages": [
        {
            "id": "units",
            "title": "Units",
            "item": "Unit",
            "fields": [
                {"key": "addr", "label": "Address", "type": "hex", "required": True, "role": "title"},
                {"key": "code", "label": "Access code", "type": "secret"},
            ],
        }
    ],
}


@pytest.fixture(autouse=True)
def quick_scrypt(monkeypatch):
    monkeypatch.setattr(backupsecrets, "SCRYPT_N", 2**10)  # the real cost is for people, not for tests


def _car_with_secrets(client):
    car = _car(client)
    vid = car["id"]
    with db.tx() as conn:
        addons.add(conn, vid, addons.parse_package(json.dumps(PLUGIN).encode()))
        item = next(a for a in addons.list_for(conn, vid) if a["addon_id"] == "sim-plugin")
        token = addons.set_up(conn, vid, item, {"mode": "eco", "account_pw": "pw-of-the-account"})
        sid = sources.add(conn, "Example", "https://example.com/pkgs", "key-of-the-source")
        conn.execute("UPDATE vehicle_addons SET source_id = ? WHERE vehicle_id = ? AND addon_id = 'sim-plugin'", (sid, vid))
        addons.add(conn, vid, addons.parse_package(json.dumps(INTEGRATION).encode()))
        conn.execute(
            "INSERT INTO module_rows(vehicle_id, addon_id, page, sort, data, created_at) VALUES(?, 'coding-demo', 'units', 0, ?, '2026-01-01T00:00:00')",
            (vid, json.dumps({"addr": "01", "code": "12345"})),
        )
    return car, token


def _everything(raw: bytes) -> bytes:
    """All bytes of a backup file, unpacked: what somebody who finds the file can read."""
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        return b"\n".join(zf.read(n) for n in zf.namelist() if not n.startswith("files/"))


def test_a_block_opens_with_its_passphrase_only():
    block = backupsecrets.seal({"v": 1, "tokens": {"1": "abc"}}, PASSPHRASE)
    assert b"abc" not in block
    assert backupsecrets.unseal(block, PASSPHRASE) == {"v": 1, "tokens": {"1": "abc"}}
    for wrong in ("", "wrong passphrase", PASSPHRASE + " "):
        with pytest.raises(backupsecrets.WrongPassphrase):
            backupsecrets.unseal(block, wrong)
    head = json.loads(block)
    head["data"] = head["data"][:-4] + "AAAA"  # a changed block is recognised, not read as rubbish
    with pytest.raises(backupsecrets.WrongPassphrase):
        backupsecrets.unseal(json.dumps(head).encode(), PASSPHRASE)
    with pytest.raises(backupsecrets.PassphraseTooShort):
        backupsecrets.seal({}, "short")
    greedy = {**json.loads(block), "n": 2**30}  # a file cannot make this system run out of memory
    with pytest.raises(backupsecrets.WrongPassphrase):
        backupsecrets.unseal(json.dumps(greedy).encode(), PASSPHRASE)


def test_a_backup_without_a_passphrase_holds_no_secret(client):
    car, token = _car_with_secrets(client)
    with db.tx() as conn:
        raw = vehiclebackup.export(conn, car["id"])
    text = _everything(raw)
    for secret in (token, "pw-of-the-account", "key-of-the-source", "12345"):
        assert secret.encode() not in text, secret
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        assert vehiclebackup.secrets_state(zf) == "none"
    assert json.loads(zipfile.ZipFile(io.BytesIO(raw)).read("vehicle.json"))["secrets"] is False


def test_with_a_passphrase_the_secrets_travel_encrypted_and_come_back(client):
    car, token = _car_with_secrets(client)
    with db.tx() as conn:
        raw = vehiclebackup.export(conn, car["id"], passphrase=PASSPHRASE)
        conn.execute("DELETE FROM vehicles WHERE id = ?", (car["id"],))  # a fresh system: the car and its token are gone
    text = _everything(raw)
    for secret in (token, "pw-of-the-account", "key-of-the-source", "12345"):
        assert secret.encode() not in text, secret  # not readable in the file
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        assert vehiclebackup.secrets_state(zf) == "passphrase"
        held = vehiclebackup.open_secrets(zf, PASSPHRASE)
    assert held["source_keys"] == {"https://example.com/pkgs": "key-of-the-source"} and held["addons"] == {
        "sim-plugin": {"account_pw": "pw-of-the-account"}
    }

    with pytest.raises(vehiclebackup.VehicleBackupError) as wrong, db.tx() as conn:
        vehiclebackup.restore(conn, raw, "not the passphrase")
    assert str(wrong.value) == "err.bk_passphrase"
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0] == 0  # a wrong passphrase creates nothing

    with db.tx() as conn:
        new = vehiclebackup.restore(conn, raw, PASSPHRASE)
    with db.tx() as conn:
        item = next(a for a in addons.list_for(conn, new) if a["addon_id"] == "sim-plugin")
        assert item["vals"] == {"mode": "eco", "account_pw": "pw-of-the-account"}  # the password is back ...
        assert (
            vault.PREFIX
            in json.loads(conn.execute("SELECT settings FROM vehicle_addons WHERE id = ?", (item["id"],)).fetchone()[0])["account_pw"]
        )  # ... and sealed
        assert connectors.remembered(conn, item["token_id"]) == token  # the kept token is back: the guide can offer it again
        assert json.loads(conn.execute("SELECT data FROM module_rows WHERE vehicle_id = ?", (new,)).fetchone()[0])["code"] == "12345"


def test_without_the_passphrase_the_rest_of_the_car_still_comes_back(client):
    car, _token = _car_with_secrets(client)
    with db.tx() as conn:
        raw = vehiclebackup.export(conn, car["id"], passphrase=PASSPHRASE)
        conn.execute("DELETE FROM vehicles WHERE id = ?", (car["id"],))
    with db.tx() as conn:
        new = vehiclebackup.restore(conn, raw)  # no passphrase: the person chose to leave the secrets out
    with db.tx() as conn:
        item = next(a for a in addons.list_for(conn, new) if a["addon_id"] == "sim-plugin")
        assert item["vals"] == {"mode": "eco"} and item["token_id"] is not None  # settings and the token's hash are there
        assert not connectors.remembered(conn, item["token_id"])
        assert "code" not in json.loads(
            conn.execute("SELECT data FROM module_rows WHERE vehicle_id = ?", (new,)).fetchone()[0]
        )  # the entry, without its code


def test_the_safety_copy_before_a_replace_brings_the_secrets_back_on_this_system(client, tmp_path):
    car, _token = _car_with_secrets(client)
    with db.tx() as conn:
        plain = vehiclebackup.export(conn, car["id"])  # a backup without secrets, to replace the car with
        vehiclebackup.replace(conn, plain, car["id"])  # the car now has none of its secrets ...
        item = next(a for a in addons.list_for(conn, car["id"]) if a["addon_id"] == "sim-plugin")
        assert "account_pw" not in item["vals"]
    copies = sorted((tmp_path / "backups").glob("vehicle-*-before-restore-*.zip"))
    assert len(copies) == 1
    raw = copies[0].read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        assert vehiclebackup.secrets_state(zf) == "local"
    assert b"pw-of-the-account" not in _everything(raw)  # sealed with the key of this system, not readable in the file
    with db.tx() as conn:
        vehiclebackup.replace(conn, raw, car["id"])  # ... and undoing the replace needs no passphrase
        item = next(a for a in addons.list_for(conn, car["id"]) if a["addon_id"] == "sim-plugin")
        assert item["vals"]["account_pw"] == "pw-of-the-account"


def test_a_local_block_of_another_system_is_ignored(client):
    car, _ = _car_with_secrets(client)
    with db.tx() as conn:
        raw = vehiclebackup.export(conn, car["id"], local=True)
    foreign = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as zin, zipfile.ZipFile(foreign, "w") as zout:
        for name in zin.namelist():
            zout.writestr(name, b"enc:v1:not-from-this-system" if name == backupsecrets.LOCAL_NAME else zin.read(name))
    with zipfile.ZipFile(io.BytesIO(foreign.getvalue())) as zf:
        assert vehiclebackup.open_secrets(zf) is None  # no key of ours: nothing is taken from it


def test_the_kept_token_of_an_old_file_is_still_taken(client):
    """Format 1 carried the kept token readable in vehicle.json: a restore of such a file keeps honouring it."""
    car, token = _car_with_secrets(client)
    with db.tx() as conn:
        raw = vehiclebackup.export(conn, car["id"])
        conn.execute("DELETE FROM vehicles WHERE id = ?", (car["id"],))
    doc = json.loads(zipfile.ZipFile(io.BytesIO(raw)).read("vehicle.json"))
    doc["tokens"][0]["token"] = token
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("vehicle.json", json.dumps(doc))
    with db.tx() as conn:
        new = vehiclebackup.restore(conn, out.getvalue())
    with db.tx() as conn:
        item = next(a for a in addons.list_for(conn, new) if a["addon_id"] == "sim-plugin")
        assert connectors.remembered(conn, item["token_id"]) == token


# ------------------------------------------------------------------ the backup of the whole system


def _database_of(raw: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        return zf.read("carassistant.db")


def test_the_system_backup_holds_every_secret_in_its_block_and_brings_them_back_on_another_system(client, tmp_path):
    from carassistant import backup, config

    _car, token = _car_with_secrets(client)
    with db.tx() as conn:
        db.set_setting(conn, "push.vapid_private", vault.encrypt("-----PRIVATE KEY OF THE PUSH-----"))
    plain = backup.create()  # no passphrase: nothing a finder could read - the secrets stay sealed with this system's key
    for secret in (token, "pw-of-the-account", "key-of-the-source", "PRIVATE KEY OF THE PUSH"):
        assert secret.encode() not in _database_of(plain)
    assert backup.secrets_state(plain) == "none" and b"enc:v1:" in _database_of(plain)

    raw = backup.create(PASSPHRASE)
    held = _database_of(raw)
    assert backup.secrets_state(raw) == "passphrase"
    assert b"enc:v1:" not in held, "a sealed value of this system is useless elsewhere and must not stay in the copy"
    for secret in (token, "pw-of-the-account", "key-of-the-source", "PRIVATE KEY OF THE PUSH", "12345"):
        assert secret.encode() not in held and secret.encode() not in _everything(raw), secret

    with pytest.raises(backup.BackupError) as short:
        backup.create("short")
    assert short.value.args[0] == "err.bk_short"
    with pytest.raises(backup.BackupError) as wrong:
        backup.restore(raw, "this is not it")
    assert wrong.value.args[0] == "err.bk_passphrase"
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0] == 1  # nothing was touched

    # another system: another key
    (config.data_dir() / "secret.key").unlink()
    vault._fernet = vault._path = None
    backup.restore(raw, PASSPHRASE)
    with db.tx() as conn:
        vid = conn.execute("SELECT id FROM vehicles").fetchone()["id"]
        item = next(a for a in addons.list_for(conn, vid) if a["addon_id"] == "sim-plugin")
        assert item["vals"]["account_pw"] == "pw-of-the-account"
        assert connectors.remembered(conn, item["token_id"]) == token
        assert (
            vault.decrypt(conn.execute("SELECT token FROM sources WHERE url = 'https://example.com/pkgs'").fetchone()[0])
            == "key-of-the-source"
        )
        assert vault.decrypt(db.get_setting(conn, "push.vapid_private")) == "-----PRIVATE KEY OF THE PUSH-----"
        assert json.loads(conn.execute("SELECT data FROM module_rows WHERE vehicle_id = ?", (vid,)).fetchone()[0])["code"] == "12345"

    # the same file without its passphrase: the data comes back, the secrets are left out
    (config.data_dir() / "secret.key").unlink()
    vault._fernet = vault._path = None
    backup.restore(raw)
    with db.tx() as conn:
        vid = conn.execute("SELECT id FROM vehicles").fetchone()["id"]
        item = next(a for a in addons.list_for(conn, vid) if a["addon_id"] == "sim-plugin")
        assert item["vals"] == {"mode": "eco"} and not connectors.remembered(conn, item["token_id"])
        assert json.loads(conn.execute("SELECT data FROM module_rows WHERE vehicle_id = ?", (vid,)).fetchone()[0]).get("code") in (None, "")


def test_the_backup_of_the_system_can_be_restored_on_the_same_system_without_a_passphrase(client):
    from carassistant import backup

    car, token = _car_with_secrets(client)
    raw = backup.create()
    backup.restore(raw)  # the safety copy before a restore is of this kind: sealed with the key that is still here
    with db.tx() as conn:
        item = next(a for a in addons.list_for(conn, car["id"]) if a["addon_id"] == "sim-plugin")
        assert item["vals"]["account_pw"] == "pw-of-the-account" and connectors.remembered(conn, item["token_id"]) == token
