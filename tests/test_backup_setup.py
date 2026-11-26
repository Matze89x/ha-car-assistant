"""A restored car sets itself up from its sources (docs/backup.md, restoresetup.py): sources are added, packages installed, what ran runs again, and a service is
approved again only when it is byte for byte the package that was approved before - which the backup says inside its passphrase block."""

import json
import re
from types import SimpleNamespace

import pytest
from tests.test_pluginsvc import ECHO, MANIFEST, _serve, make_zip

from carassistant import addons, backupsecrets, connectors, db, pluginsvc, restoresetup, sources, vault, vehiclebackup

PASSPHRASE = "correct horse battery"
SOURCE = "https://example.com/pkgs"
SVC = {**MANIFEST, "settings": [*MANIFEST["settings"], {"key": "account_pw", "label": "Password", "type": "password"}]}
NOTES = {
    "id": "note-pad",
    "kind": "integration",
    "name": "Note pad",
    "version": "1",
    "pages": [
        {
            "id": "notes",
            "title": "Notes",
            "item": "Note",
            "fields": [{"key": "text", "label": "Text", "type": "text", "required": True, "role": "title"}],
        }
    ],
}


@pytest.fixture(autouse=True)
def quick_scrypt(monkeypatch):
    monkeypatch.setattr(backupsecrets, "SCRYPT_N", 2**10)


@pytest.fixture()
def started(monkeypatch):
    """The environment of the services is not built in these tests: what would be started is only noted."""
    calls: list[int] = []
    monkeypatch.setattr(pluginsvc, "install_async", lambda pk: calls.append(pk))
    monkeypatch.setattr(pluginsvc, "kick", lambda: None)
    return calls


def _files(extra_code: str = ""):
    raw, sha = make_zip({"service/main.py": ECHO + extra_code})
    return {
        "plugins/index.json": json.dumps({"packages": [{"id": "echo-svc", "name": "Echo", "version": "1", "sha256": sha}]}).encode(),
        "plugins/echo-svc/plugin.json": json.dumps(SVC).encode(),
        "plugins/echo-svc/package.zip": raw,
        "integrations/index.json": json.dumps({"packages": [{"id": "note-pad", "name": "Note pad", "version": "1"}]}).encode(),
        "integrations/note-pad/plugin.json": json.dumps(NOTES).encode(),
    }, sha


def _car_with_packages(client, monkeypatch, started):
    """A car with a service plugin (approved, running, a password) and an integration, installed from a source of its own with a key; a backup with a
    passphrase and a plain one. Then the car, its packages and the source are gone: a fresh system."""
    files, sha = _files()
    _serve(monkeypatch, files)
    client.post("/vehicles", data={"name": "Other Car", "fuel_type": "petrol"})  # (the restored car is not the first car of a fresh system)
    client.post("/vehicles", data={"name": "Setup Car", "fuel_type": "petrol"})
    with db.tx() as conn:
        vid = conn.execute("SELECT id FROM vehicles ORDER BY id DESC LIMIT 1").fetchone()["id"]
        sid = sources.add(conn, "Example", SOURCE, "key-of-example")
        sources.refresh(conn, sid)
    client.post(f"/v/{vid}/packages/{sid}/plugin/echo-svc/install?approve=1")
    client.post(f"/v/{vid}/packages/{sid}/integration/note-pad/install")
    with db.tx() as conn:
        item = next(a for a in addons.list_for(conn, vid) if a["addon_id"] == "echo-svc")
        addons.set_up(conn, vid, item, {"greeting": "hello", "account_pw": "pw-1"})
        token = addons.new_token(conn, vid, addons.get(conn, vid, item["id"]))  # (the kept token travels in the passphrase block)
        addons.set_active(conn, addons.get(conn, vid, item["id"]), True)
        addons.set_active(conn, next(a for a in addons.list_for(conn, vid) if a["addon_id"] == "note-pad"), True)
        assert pluginsvc.approved(addons.get(conn, vid, item["id"]))
        built = SimpleNamespace(
            secure=vehiclebackup.export(conn, vid, passphrase=PASSPHRASE),
            plain=vehiclebackup.export(conn, vid),
            files=files,
            sha=sha,
            token=token,
        )
        for a in addons.list_for(conn, vid):
            addons.remove(conn, a)
        conn.execute("DELETE FROM vehicles WHERE id = ?", (vid,))
        conn.execute("DELETE FROM sources WHERE id = ?", (sid,))
    started.clear()
    return built


def _restore(client, raw, setup=True, passphrase=PASSPHRASE):
    asked = client.post(
        "/vehicles/restore", files={"backup": ("car.zip", raw, "application/zip")}, data={"passphrase": passphrase} if passphrase else {}
    )
    assert asked.status_code == 200, asked.text[:300]
    pending = re.search(r'name="token" value="([^"]+)"', asked.text).group(1)
    form = {"token": pending, "mode": "new", **({"passphrase": passphrase} if passphrase else {}), **({"setup": "1"} if setup else {})}
    return asked, client.post("/vehicles/restore/confirm", data=form)


def _items(name="Setup Car"):
    with db.tx() as conn:
        vid = conn.execute("SELECT id FROM vehicles WHERE name = ?", (name,)).fetchone()["id"]
        return vid, {a["addon_id"]: a for a in addons.list_for(conn, vid)}


def test_the_question_page_lists_what_would_be_fetched(client, monkeypatch, started):
    built = _car_with_packages(client, monkeypatch, started)
    asked, _ = _restore(client, built.secure)
    assert "Echo" in asked.text and "Note pad" in asked.text and SOURCE in asked.text and 'name="setup"' in asked.text
    assert "new source" in asked.text and "runs its own code" in asked.text and "· approved before" in asked.text
    assert "Fetch and set up the packages" in asked.text


def test_restore_and_set_up_installs_everything_as_it_was(client, monkeypatch, started):
    built = _car_with_packages(client, monkeypatch, started)
    _, done = _restore(client, built.secure)
    assert (
        done.status_code == 303
        and "vb_setup_done" in done.headers["location"]
        and done.headers["location"].split("?")[0].endswith("/plugins")
    )
    _, items = _items()
    echo, notes = items["echo-svc"], items["note-pad"]
    assert not echo["missing"] and not notes["missing"] and echo["source_id"] and notes["source_id"] == echo["source_id"]
    assert echo["vals"] == {"greeting": "hello", "account_pw": "pw-1"}  # the settings and the password
    assert echo["active"] == 1 and notes["active"] == 1  # switched on, as they were
    assert pluginsvc.approved(echo) and echo["pkg_sha"] == built.sha  # the same package: approved again, and started
    assert started == [echo["id"]]
    with db.tx() as conn:
        source = conn.execute("SELECT url, token FROM sources WHERE url = ?", (SOURCE,)).fetchone()
        assert source and vault.decrypt(source["token"]) == "key-of-example"  # the source came back with its key
        assert connectors.remembered(conn, echo["token_id"]) == built.token  # and the token of the plugin


def test_a_package_that_changed_since_is_installed_but_not_approved(client, monkeypatch, started):
    built = _car_with_packages(client, monkeypatch, started)
    newer, _ = _files("\n# a new version of the code\n")
    _serve(monkeypatch, newer)
    _, done = _restore(client, built.secure)
    assert done.status_code == 303
    _, items = _items()
    echo = items["echo-svc"]
    assert (
        not echo["missing"] and echo["pkg_sha"] != built.sha and not pluginsvc.approved(echo) and started == []
    )  # it waits for the person, as always


def test_without_the_passphrase_nothing_is_approved(client, monkeypatch, started):
    built = _car_with_packages(client, monkeypatch, started)
    asked, _ = _restore(client, built.plain, passphrase="")
    assert "· approved before" not in asked.text  # (the hint above the list says the word, the list does not)
    _, items = _items()
    echo = items["echo-svc"]
    assert not echo["missing"] and not pluginsvc.approved(echo) and started == []
    assert echo["vals"].get("greeting") == "hello" and "account_pw" not in echo["vals"]


def test_restore_data_only_keeps_the_old_way(client, monkeypatch, started):
    built = _car_with_packages(client, monkeypatch, started)
    _, done = _restore(client, built.secure, setup=False)
    assert done.status_code == 303 and "vb_restored" in done.headers["location"]
    _, items = _items()
    assert items["echo-svc"]["missing"] and items["note-pad"]["missing"] and items["echo-svc"]["active"] == 0


def test_a_source_that_does_not_answer_leaves_the_package_waiting_and_says_so(client, monkeypatch, started):
    built = _car_with_packages(client, monkeypatch, started)

    def down(url, headers, check_host, limit=0):
        raise sources.SourceError("err.src_net")

    monkeypatch.setattr(sources, "_http", down)
    _, done = _restore(client, built.secure)
    assert done.status_code == 303 and "vb_setup_partly" in done.headers["location"]
    _, items = _items()
    assert (
        items["echo-svc"]["missing"] and items["echo-svc"]["vals"].get("greeting") == "hello"
    )  # nothing is lost: the settings wait for the package


def test_a_package_that_is_already_installed_comes_with_its_checksum(client, monkeypatch, started):
    built = _car_with_packages(client, monkeypatch, started)
    _restore(client, built.secure)  # the first restore installs the packages on this system
    asked = client.post("/vehicles/restore", files={"backup": ("car.zip", built.plain, "application/zip")})
    pending = re.search(r'name="token" value="([^"]+)"', asked.text)
    assert pending  # the car is already here: replace or copy
    client.post("/vehicles/restore/confirm", data={"token": pending.group(1), "mode": "copy"})
    with db.tx() as conn:
        copy = conn.execute("SELECT id FROM vehicles WHERE name = 'Setup Car 2'").fetchone()["id"]
        row = next(a for a in addons.list_for(conn, copy) if a["addon_id"] == "echo-svc")
    assert not row["missing"] and row["pkg_sha"] == built.sha  # the files of the package that is already here come with the copy


def test_the_plan_names_only_what_is_missing_and_has_a_source(client, monkeypatch, started):
    built = _car_with_packages(client, monkeypatch, started)
    data, held = vehiclebackup.load(built.secure, PASSPHRASE)
    with db.tx() as conn:
        found = {p["addon_id"]: p for p in restoresetup.plan(conn, data, held)}
        assert set(found) == {"echo-svc", "note-pad"} and found["echo-svc"]["runs_code"] and found["echo-svc"]["approved_before"]
        assert not found["note-pad"]["runs_code"] and not found["note-pad"]["approved_before"] and found["echo-svc"]["new_source"]
        for entry in data["addons"]:
            entry["source"], entry["source_url"] = None, None
        assert restoresetup.plan(conn, data, held) == []  # a package without a source cannot be fetched: nothing to ask about


# ------------------------------------------------------------------ the files of installed packages after a restore of the whole system


def _install_service(client, monkeypatch, started):
    files, sha = _files()
    _serve(monkeypatch, files)
    client.post("/vehicles", data={"name": "Repair Car", "fuel_type": "petrol"})
    with db.tx() as conn:
        vid = conn.execute("SELECT id FROM vehicles ORDER BY id DESC LIMIT 1").fetchone()["id"]
        sid = conn.execute("SELECT id FROM sources WHERE is_default = 1").fetchone()[0]
        sources.refresh(conn, sid)
    client.post(f"/v/{vid}/packages/{sid}/plugin/echo-svc/install?approve=1")
    with db.tx() as conn:
        item = next(a for a in addons.list_for(conn, vid) if a["addon_id"] == "echo-svc")
        addons.set_active(conn, item, True)
    started.clear()
    return vid, item["id"], sha


def _lose_the_files(sha):
    import shutil

    shutil.rmtree(
        pluginsvc.pkg_dir("echo-svc", sha), ignore_errors=True
    )  # a restore of the whole system on another system: the database is there, the folders are not


def test_the_files_of_installed_packages_are_fetched_again_after_a_system_restore(client, monkeypatch, started):
    vid, pk, sha = _install_service(client, monkeypatch, started)
    with db.tx() as conn:
        assert not restoresetup.files_missing(addons.get(conn, vid, pk))
    _lose_the_files(sha)
    with db.tx() as conn:
        assert restoresetup.files_missing(addons.get(conn, vid, pk))
    assert restoresetup.repair_all() == [{"addon_id": "echo-svc", "ok": True, "why": ""}]
    with db.tx() as conn:
        addon = addons.get(conn, vid, pk)
        assert (
            not restoresetup.files_missing(addon) and pluginsvc.approved(addon) and addon["svc_error"] is None
        )  # still approved: the same package
    assert started == [pk]  # and its environment is made again
    assert restoresetup.repair_all() == []  # nothing to do the second time


def test_a_package_that_changed_at_its_source_is_not_put_in_place_by_a_repair(client, monkeypatch, started):
    vid, pk, sha = _install_service(client, monkeypatch, started)
    _lose_the_files(sha)
    newer, _ = _files("\n# changed at the source\n")
    _serve(monkeypatch, newer)
    assert restoresetup.repair_all() == [{"addon_id": "echo-svc", "ok": False, "why": "svc.err_changed"}]
    with db.tx() as conn:
        addon = addons.get(conn, vid, pk)
        assert restoresetup.files_missing(addon) and addon["svc_error"] == "svc.err_files" and addon["pkg_sha"] == sha
    assert started == []


def test_the_approval_page_offers_to_fetch_the_files_again(client, monkeypatch, started):
    vid, pk, sha = _install_service(client, monkeypatch, started)
    assert "Fetch the files again" not in client.get(f"/v/{vid}/integrations/{pk}/service").text
    _lose_the_files(sha)
    page = client.get(f"/v/{vid}/integrations/{pk}/service").text
    assert "Fetch the files again" in page and f"/integrations/{pk}/refetch" in page
    done = client.post(f"/v/{vid}/integrations/{pk}/refetch")
    assert done.status_code == 303 and "svc.refetched" in done.headers["location"] and started == [pk]
    assert "Fetch the files again" not in client.get(f"/v/{vid}/integrations/{pk}/service").text
    _lose_the_files(sha)
    _serve(monkeypatch, {})  # the source is not reachable: the reason is told on the page
    again = client.post(f"/v/{vid}/integrations/{pk}/refetch")
    assert again.status_code == 303 and "err.src" in again.headers["location"]
