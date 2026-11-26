"""The pages of the backups with a passphrase: download (a form, never an address), restore with the passphrase, without it, with a wrong one."""

import io
import re
import zipfile

import pytest
from tests.test_backup_secrets import PASSPHRASE, _car_with_secrets

from carassistant import addons, backup, backupsecrets, connectors, db, vehiclebackup


@pytest.fixture(autouse=True)
def quick_scrypt(monkeypatch):
    monkeypatch.setattr(backupsecrets, "SCRYPT_N", 2**10)


def _zip_names(content: bytes) -> set[str]:
    return set(zipfile.ZipFile(io.BytesIO(content)).namelist())


def test_a_car_backup_is_a_form_and_the_passphrase_is_never_part_of_an_address(client):
    car, token = _car_with_secrets(client)
    plain = client.get(f"/v/{car['id']}/backup.zip")
    assert plain.status_code == 200 and "secrets.enc" not in _zip_names(plain.content) and token.encode() not in plain.content
    page = client.get(f"/settings/car?car={car['slug']}").text
    assert f'method="post" action="/v/{car["slug"]}/backup.zip"' in page and 'name="passphrase"' in page
    assert "backup.zip?codes=1" not in page  # the separate download of the codes is gone: they travel in the encrypted block
    secure = client.post(f"/v/{car['id']}/backup.zip", data={"passphrase": PASSPHRASE})
    assert secure.status_code == 200 and "secrets.enc" in _zip_names(secure.content) and secure.headers["cache-control"] == "no-store"
    assert "with-secrets" in secure.headers["content-disposition"]
    short = client.post(f"/v/{car['id']}/backup.zip", data={"passphrase": "short"})
    assert short.status_code == 303 and "err.bk_short" in short.headers["location"]
    empty = client.post(f"/v/{car['id']}/backup.zip", data={"passphrase": ""})
    assert empty.status_code == 200 and "secrets.enc" not in _zip_names(empty.content)


def _upload(client, raw, **form):
    return client.post("/vehicles/restore", files={"backup": ("car.zip", raw, "application/zip")}, data=form, follow_redirects=False)


def test_restoring_a_car_with_secrets_asks_for_the_passphrase(client):
    car, token = _car_with_secrets(client)
    raw = client.post(f"/v/{car['id']}/backup.zip", data={"passphrase": PASSPHRASE}).content
    with db.tx() as conn:
        conn.execute("DELETE FROM vehicles WHERE id = ?", (car["id"],))  # a system that does not know the car

    wrong = _upload(client, raw, passphrase="not the passphrase")  # a wrong passphrase is told at once
    assert wrong.status_code == 303 and "err.bk_passphrase" in wrong.headers["location"]
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0] == 0

    asked = _upload(client, raw)  # none: the page asks, the file waits
    assert asked.status_code == 200 and 'name="passphrase"' in asked.text and 'name="no_secrets"' in asked.text
    pending = re.search(r'name="token" value="([^"]+)"', asked.text).group(1)
    miss = client.post("/vehicles/restore/confirm", data={"token": pending, "mode": "new"})
    assert miss.status_code == 303 and "restore/ask" in miss.headers["location"] and "err.bk_need_passphrase" in miss.headers["location"]
    again = client.get(re.search(r"(/vehicles/restore/ask\?token=[^&]+)", miss.headers["location"]).group(1))
    assert again.status_code == 200 and 'name="passphrase"' in again.text
    bad = client.post("/vehicles/restore/confirm", data={"token": pending, "mode": "new", "passphrase": "nope nope nope"})
    assert bad.status_code == 303 and "err.bk_passphrase" in bad.headers["location"]
    done = client.post("/vehicles/restore/confirm", data={"token": pending, "mode": "new", "passphrase": PASSPHRASE})
    assert done.status_code == 303
    with db.tx() as conn:
        new = conn.execute("SELECT id FROM vehicles").fetchone()["id"]
        item = next(a for a in addons.list_for(conn, new) if a["addon_id"] == "sim-plugin")
        assert item["vals"]["account_pw"] == "pw-of-the-account" and connectors.remembered(conn, item["token_id"]) == token
    assert (
        client.post("/vehicles/restore/confirm", data={"token": pending, "mode": "new", "passphrase": PASSPHRASE}).status_code == 303
    )  # (gone: expired)


def test_a_car_with_secrets_can_be_restored_without_them(client):
    car, _ = _car_with_secrets(client)
    raw = client.post(f"/v/{car['id']}/backup.zip", data={"passphrase": PASSPHRASE}).content
    with db.tx() as conn:
        conn.execute("DELETE FROM vehicles WHERE id = ?", (car["id"],))
    asked = _upload(client, raw)
    pending = re.search(r'name="token" value="([^"]+)"', asked.text).group(1)
    done = client.post("/vehicles/restore/confirm", data={"token": pending, "mode": "new", "no_secrets": "1"})
    assert done.status_code == 303
    with db.tx() as conn:
        new = conn.execute("SELECT id FROM vehicles").fetchone()["id"]
        item = next(a for a in addons.list_for(conn, new) if a["addon_id"] == "sim-plugin")
        assert item["vals"] == {"mode": "eco"} and not connectors.remembered(conn, item["token_id"])


def test_a_car_that_is_already_here_and_has_secrets_asks_once_for_both(client):
    car, _token = _car_with_secrets(client)
    raw = client.post(f"/v/{car['id']}/backup.zip", data={"passphrase": PASSPHRASE}).content
    asked = _upload(client, raw, passphrase=PASSPHRASE)  # the passphrase is known, the car is here: replace or copy?
    assert asked.status_code == 200 and "mode" in asked.text and 'name="no_secrets"' not in asked.text
    pending = re.search(r'name="token" value="([^"]+)"', asked.text).group(1)
    assert client.post("/vehicles/restore/confirm", data={"token": pending, "mode": "copy", "passphrase": PASSPHRASE}).status_code == 303
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0] == 2


def test_the_backup_of_the_system_is_a_form_too(client):
    car, token = _car_with_secrets(client)
    page = client.get("/settings/system").text
    assert 'method="post" action="/settings/backup.zip"' in page and 'name="passphrase"' in page and 'name="no_secrets"' in page
    assert client.get("/settings/backup.zip").status_code == 200  # the plain link still works
    short = client.post("/settings/backup.zip", data={"passphrase": "short"})
    assert short.status_code == 303 and "err.bk_short" in short.headers["location"]
    secure = client.post("/settings/backup.zip", data={"passphrase": PASSPHRASE})
    assert secure.status_code == 200 and "secrets.enc" in _zip_names(secure.content) and token.encode() not in secure.content
    raw = secure.content

    def restore(**form):
        return client.post("/settings/restore", files={"backup": ("b.zip", raw, "application/zip")}, data={"confirm": "1", **form})

    miss = restore()  # no passphrase and no decision: nothing is replaced
    assert miss.status_code == 303 and "err.bk_need_passphrase" in miss.headers["location"]
    wrong = restore(passphrase="this is not it")
    assert wrong.status_code == 303 and "err.bk_passphrase" in wrong.headers["location"]
    assert backup.secrets_state(raw) == "passphrase"
    assert restore(passphrase=PASSPHRASE).status_code == 303
    with db.tx() as conn:
        item = next(a for a in addons.list_for(conn, car["id"]) if a["addon_id"] == "sim-plugin")
        assert item["vals"]["account_pw"] == "pw-of-the-account"
    assert restore(no_secrets="1").status_code == 303  # the person chose to leave them out
    assert vehiclebackup.FORMAT == backup.FORMAT == 2
