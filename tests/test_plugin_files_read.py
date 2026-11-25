"""A service that READS the files of its package (``service.files: "read"``, the environment variable ``CA_FILES_DIR``) and a file that is hidden
(``files[].hidden: true``): not offered as a download, not listed on its own, but with its checksum on the approval page and readable by such a service
(docs/plugins.md, "A service that reads the files of its package")."""

import hashlib
import io
import json
import os
import re
import zipfile

import pytest
from tests.test_assets import JAR, _install, _manifest

from carassistant import addons, pluginsvc


def _service(**extra):
    return {"entry": "svc.py", **extra}


def test_the_two_keys_are_parsed_and_nothing_else_is_taken():
    assert addons.clean_service(_service(files="read"))["files"] == "read"
    assert "files" not in addons.clean_service(_service())  # without the key nothing changes
    for bad in ("write", True, False, 1, ["a.jar"], {"read": True}):
        with pytest.raises(addons.AddonError):
            addons.clean_service(_service(files=bad))
    item = _manifest()["files"][0]
    assert addons.clean_files([{**item, "hidden": True}])[0]["hidden"] is True
    assert "hidden" not in addons.clean_files([{**item, "hidden": False}])[0] and "hidden" not in addons.clean_files([item])[0]
    for bad in ("yes", 1, "true", [True]):
        with pytest.raises(addons.AddonError):
            addons.clean_files([{**item, "hidden": bad}])


def test_both_belong_to_the_approval_and_older_approvals_stay_valid():
    plain = addons.parse_package(json.dumps({**_manifest(), "service": _service()}).encode())
    reads = addons.parse_package(json.dumps({**_manifest(), "service": _service(files="read")}).encode())
    hidden_files = _manifest()
    hidden_files["files"][0]["hidden"] = True
    hidden = addons.parse_package(json.dumps({**hidden_files, "service": _service()}).encode())
    fp = addons.approval_fingerprint
    assert len({fp(plain), fp(reads), fp(hidden)}) == 3  # each one needs its own approval
    old_way = hashlib.sha256(
        json.dumps(
            {
                "service": plain.get("service"),
                "files": [(f["name"], f["sha256"], f["size"]) for f in plain["files"]],
                "bundles": [{k: v for k, v in b.items() if k not in ("version", "installed")} for b in plain["bundles"]],
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    assert fp(plain) == old_way  # a package that uses neither key: the approval given before still counts


def _stored(client, files=None):
    """A package with a service and its files in the stores of the app: (addon dict, jar bytes)."""
    manifest = {**_manifest(), "service": _service(files="read"), "bundles": []}
    if files:
        manifest["files"] = files
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as z:
        z.writestr("plugin.json", json.dumps(manifest))
        z.writestr("svc.py", "print(1)\n")
        z.writestr("assets/carassistant.jar", JAR)
    data = raw.getvalue()
    sha = hashlib.sha256(data).hexdigest()
    parsed = addons.parse_package(json.dumps(manifest).encode())
    pluginsvc.store_package("files-pkg", data, sha, "svc.py", parsed["files"], [])
    return {"addon_id": "files-pkg", "kind": "plugin", "vehicle_id": 1, "pkg_sha": sha, "m": parsed, "vals": {}, "id": 1}


def test_the_service_gets_its_files_read_only_and_only_when_it_asks(client):
    addon = _stored(client)
    view = pluginsvc.ensure_files_view(addon)
    assert view is not None and view == pluginsvc.files_view_dir("files-pkg", addon["pkg_sha"])
    assert (view / "carassistant.jar").read_bytes() == JAR  # exactly the approved bytes under their name
    assert sorted(p.name for p in view.iterdir()) == ["carassistant.jar"]
    assert oct((view / "carassistant.jar").stat().st_mode & 0o777) == oct(0o444) and oct(view.stat().st_mode & 0o777) == oct(
        0o555
    )  # no write bit
    env = pluginsvc._env(addon, view, "", 1234)
    assert env["CA_FILES_DIR"] == str(view)
    assert pluginsvc.ensure_files_view(addon) == view  # again: nothing to do

    no_ask = {**addon, "m": {**addon["m"], "service": addons.clean_service(_service())}}
    assert pluginsvc.ensure_files_view(no_ask) is None and "CA_FILES_DIR" not in pluginsvc._env(
        no_ask, view, "", 1234
    )  # without the key: not given


def test_a_file_that_does_not_match_is_not_given(client):
    addon = _stored(client)
    stored = pluginsvc.asset_dir("files-pkg", addon["pkg_sha"]) / "carassistant.jar"
    os.chmod(stored.parent, 0o755)
    os.chmod(stored, 0o644)
    stored.write_bytes(JAR[:-1] + b"X")  # the bytes of the store changed behind the app's back
    assert pluginsvc.ensure_files_view(addon) is None  # the checksum is checked again when the copy is made
    assert "CA_FILES_DIR" not in pluginsvc._env(addon, stored.parent, "", 1234)


def test_forget_removes_the_read_only_copies(client):
    addon = _stored(client)
    view = pluginsvc.ensure_files_view(addon)
    assert view is not None
    pluginsvc._unlock(view.parent)
    import shutil

    shutil.rmtree(view.parent)
    assert not view.exists()


@pytest.fixture()
def hidden_pkg(client, monkeypatch):
    manifest = _manifest()
    manifest["files"][0]["hidden"] = True
    vid, item = _install(client, monkeypatch, manifest)
    assert item is not None
    return vid, item


def test_a_hidden_file_is_not_offered_listed_or_linked_but_stays_on_the_approval_page(client, hidden_pkg):
    vid, item = hidden_pkg
    review = client.get(f"/v/{vid}/integrations/{item['id']}/service").text
    assert "carassistant.jar" in review and "for the service only" in review and "sha256" in review  # approved by name and checksum
    client.post(f"/v/{vid}/integrations/{item['id']}/service/approve")
    assert client.get("/plugins/files-pkg/files/carassistant.jar").status_code == 404  # approved, and still not handed out
    general = client.get(f"/v/{vid}/integrations/{item['id']}/settings").text
    assert "carassistant.jar" not in general and not re.search(r"/get/carassistant\.jar", general)  # not under "Files for the car"
    assert client.get(f"/v/{vid}/integrations/{item['id']}/get/carassistant.jar").status_code == 404
    info = client.get(f"/v/{vid}/integrations/{item['id']}/info?tab=interfaces").text
    assert "carassistant.jar" not in info.replace(
        "{file:carassistant.jar}", ""
    )  # nor on the info page (the placeholder in the text stays text)
    assert client.get("/plugins/files-pkg/files/install.zip").status_code == 200  # the bundle of the package is offered as before
