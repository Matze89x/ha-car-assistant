import hashlib
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient
from tests.test_pluginsvc import _serve, make_zip

from carassistant import addons, db, pluginsvc, web

JAR = bytes(range(256)) * 20  # some bytes that are no text
SCRIPT = "#!/bin/sh\necho custom\n"


def _manifest(sha=None, size=None, **extra):
    return {
        "id": "files-pkg",
        "kind": "plugin",
        "name": "Files",
        "version": "1",
        "docs": "Get {file:carassistant.jar} and the pack {file:install.zip}.",
        "files": [
            {
                "name": "carassistant.jar",
                "path": "assets/carassistant.jar",
                "label": "Program for the car",
                "note": "put it on the card",
                "sha256": sha or hashlib.sha256(JAR).hexdigest(),
                "size": size or len(JAR),
            }
        ],
        "bundles": [
            {
                "name": "install.zip",
                "label": "SD card package",
                "entries": [
                    {"from": "scripts/custom.sh", "to": "mod/custom.sh"},
                    {"from": "assets/carassistant.jar", "to": "mod/carassistant/carassistant.jar"},
                ],
            }
        ],
        **extra,
    }


def _install(client, monkeypatch, manifest=None, jar=JAR, index_files="auto"):
    manifest = manifest or _manifest()
    raw, sha = make_zip({"plugin.json": json.dumps(manifest), "scripts/custom.sh": SCRIPT})
    buf = io.BytesIO(raw)
    with zipfile.ZipFile(buf, "a") as z:
        z.writestr("assets/carassistant.jar", jar)
    raw = buf.getvalue()
    sha = hashlib.sha256(raw).hexdigest()
    listed = (
        [{"name": f["name"], "sha256": f["sha256"], "size": f["size"]} for f in manifest["files"]] if index_files == "auto" else index_files
    )
    index = {"packages": [{"id": "files-pkg", "name": "Files", "version": "1", "sha256": sha, "files": listed}]}
    _serve(
        monkeypatch,
        {
            "plugins/index.json": json.dumps(index).encode(),
            "plugins/files-pkg/plugin.json": json.dumps(manifest).encode(),
            "plugins/files-pkg/package.zip": raw,
        },
    )
    client.post("/vehicles", data={"name": "Asset Car", "fuel_type": "petrol"})
    with db.tx() as conn:
        vid = conn.execute("SELECT id FROM vehicles ORDER BY id DESC LIMIT 1").fetchone()["id"]
        sid = conn.execute("SELECT id FROM sources WHERE is_default = 1").fetchone()[0]
    client.post(f"/v/{vid}/packages/{sid}/plugin/files-pkg/install")
    with db.tx() as conn:
        found = [a for a in addons.list_for(conn, vid) if a["addon_id"] == "files-pkg"]
    return vid, (found[0] if found else None)


@pytest.fixture()
def installed(client, monkeypatch):
    vid, item = _install(client, monkeypatch)
    assert item is not None
    return vid, item


def test_forbidden_endings_and_sizes_are_refused():
    for bad_name in ("run.exe", "lib.so", "setup.sh", "tool.bat", "noext"):
        manifest = _manifest()
        manifest["files"][0].update(name=bad_name, path=f"assets/{bad_name}")
        with pytest.raises(addons.AddonError):
            addons.parse_package(json.dumps(manifest).encode())
    for patch in ({"size": 8_000_001}, {"sha256": "nothex"}, {"path": "../x.jar"}, {"path": "/abs.jar"}, {"path": "assets/other.zip"}):
        manifest = _manifest()
        manifest["files"][0].update(patch)
        with pytest.raises(addons.AddonError):
            addons.parse_package(json.dumps(manifest).encode())
    big = _manifest()
    big["files"] = [{**big["files"][0], "name": f"f{i}.bin", "path": f"assets/f{i}.bin", "size": 7_000_000} for i in range(3)]
    with pytest.raises(addons.AddonError):  # 21 MB together
        addons.parse_package(json.dumps(big).encode())
    many = _manifest()
    many["files"] = [{**many["files"][0], "name": f"f{i}.bin", "path": f"assets/f{i}.bin"} for i in range(11)]
    with pytest.raises(addons.AddonError):
        addons.parse_package(json.dumps(many).encode())
    with pytest.raises(addons.AddonError):  # a bundle that reaches outside the package
        addons.parse_package(
            json.dumps({**_manifest(), "bundles": [{"name": "x.zip", "entries": [{"from": "../etc/passwd", "to": "a"}]}]}).encode()
        )


def test_a_wrong_checksum_installs_nothing(client, monkeypatch):
    _vid, item = _install(client, monkeypatch, _manifest(sha="0" * 64))  # the manifest says one thing, the zip holds another
    assert item is None and not (pluginsvc.files_root() / "files-pkg").exists()
    _vid, item = _install(client, monkeypatch, _manifest(size=len(JAR) + 1))
    assert item is None
    _vid, item = _install(client, monkeypatch, index_files=[])  # the index does not name the file
    assert item is None and not (pluginsvc.files_root() / "files-pkg").exists()


def test_files_wait_for_approval_then_download_with_the_right_headers(client, installed):
    vid, item = installed
    assert client.get("/plugins/files-pkg/files/carassistant.jar").status_code == 404  # not approved: nothing is handed out
    cards = client.get(f"/v/{vid}/plugins").text
    assert "waiting for approval" in cards and "Review and approve" in cards
    page = client.get(f"/v/{vid}/integrations/{item['id']}/service").text
    assert "carassistant.jar" in page and "sha256" in page and "never runs them" in page and "install.zip" in page
    assert "/plugins/files-pkg/files/carassistant.jar" not in client.get(f"/v/{vid}/integrations/{item['id']}/info").text  # no link before
    client.post(f"/v/{vid}/integrations/{item['id']}/service/approve")
    got = client.get("/plugins/files-pkg/files/carassistant.jar")
    assert got.status_code == 200 and got.content == JAR
    assert got.headers["content-type"] == "application/java-archive" and "attachment" in got.headers["content-disposition"]
    assert "no-store" in got.headers["cache-control"]
    assert client.get("/plugins/files-pkg/files/other.jar").status_code == 404
    page = client.get(f"/v/{vid}/integrations/{item['id']}/info").text
    assert 'href="/plugins/files-pkg/files/carassistant.jar"' in page and "SD card package" in page  # buttons on the Interfaces page
    assert page.count('href="/plugins/files-pkg/files/install.zip"') >= 2  # one in the text ({file:...}), one on the button
    assert "Program for the car" in page and "put it on the card" in page
    stored = pluginsvc.asset_dir("files-pkg", item["pkg_sha"]) / "carassistant.jar"
    assert oct(stored.stat().st_mode & 0o777) == oct(0o444)  # read-only, never executable


def test_only_signed_in_people_get_the_files(client, installed, monkeypatch):
    from carassistant import accounts, auth_web

    vid, item = installed
    client.post(f"/v/{vid}/integrations/{item['id']}/service/approve")
    with db.tx() as conn:
        uid = accounts.create_user(conn, "owner", "a-long-pass-123", "Owner", True)
        session = accounts.create_session(conn, uid)
    monkeypatch.delenv("CARASSISTANT_DEV", raising=False)  # as on a real system: somebody from outside is not the Home Assistant gateway
    outside = TestClient(web.app, base_url="https://car.example.com", follow_redirects=False, headers={"Origin": "https://car.example.com"})
    assert outside.get("/plugins/files-pkg/files/carassistant.jar").status_code in (303, 401, 403)
    assert outside.get("/plugins/files-pkg/files/carassistant.jar", cookies={auth_web.COOKIE: "forged"}).status_code in (303, 401, 403)
    assert outside.get("/plugins/files-pkg/files/carassistant.jar", cookies={auth_web.COOKIE: session}).content == JAR


def test_the_download_works_without_a_running_service(client, monkeypatch):
    manifest = _manifest(service={"entry": "service/main.py", "routes": [{"prefix": "/fp/", "public": False}]})
    raw, _ = make_zip({"plugin.json": json.dumps(manifest), "scripts/custom.sh": SCRIPT, "service/main.py": "print(1)"})
    buf = io.BytesIO(raw)
    with zipfile.ZipFile(buf, "a") as z:
        z.writestr("assets/carassistant.jar", JAR)
    raw = buf.getvalue()
    index = {
        "packages": [
            {
                "id": "files-pkg",
                "name": "Files",
                "sha256": hashlib.sha256(raw).hexdigest(),
                "files": [{"name": "carassistant.jar", "sha256": hashlib.sha256(JAR).hexdigest(), "size": len(JAR)}],
            }
        ]
    }
    _serve(
        monkeypatch,
        {
            "plugins/index.json": json.dumps(index).encode(),
            "plugins/files-pkg/plugin.json": json.dumps(manifest).encode(),
            "plugins/files-pkg/package.zip": raw,
        },
    )
    client.post("/vehicles", data={"name": "Svc Asset Car", "fuel_type": "petrol"})
    with db.tx() as conn:
        vid = conn.execute("SELECT id FROM vehicles ORDER BY id DESC LIMIT 1").fetchone()["id"]
        sid = conn.execute("SELECT id FROM sources WHERE is_default = 1").fetchone()[0]
    client.post(f"/v/{vid}/packages/{sid}/plugin/files-pkg/install")
    with db.tx() as conn:
        item = addons.list_for(conn, vid)[0]
    client.post(f"/v/{vid}/integrations/{item['id']}/service/approve")
    for _ in range(100):  # the environment of the approved service installs in the background: let it finish
        if item["id"] not in pluginsvc._installing:
            break
        __import__("time").sleep(0.1)
    pluginsvc.stop_all()  # the service is not running (and never was)
    assert not pluginsvc.running(item["id"]) and client.get("/plugins/files-pkg/files/carassistant.jar").content == JAR
    asset_folder = pluginsvc.files_root() / "files-pkg"
    assert not str(pluginsvc.pkg_dir("files-pkg", item["pkg_sha"])).startswith(str(asset_folder))  # apart from the code of the service
    assert not (pluginsvc.pkg_dir("files-pkg", item["pkg_sha"]) / "assets").exists()  # the code folder does not hold the binaries
    pluginsvc._stop.clear()


def test_a_bundle_holds_exactly_its_entries_and_is_the_same_every_time(client, installed):
    vid, item = installed
    client.post(f"/v/{vid}/integrations/{item['id']}/service/approve")
    one = client.get("/plugins/files-pkg/files/install.zip")
    two = client.get("/plugins/files-pkg/files/install.zip")
    assert (
        one.status_code == 200 and one.content == two.content and one.headers["content-type"] == "application/zip"
    )  # same bytes, same checksum
    with zipfile.ZipFile(io.BytesIO(one.content)) as z:
        assert z.namelist() == ["mod/custom.sh", "mod/carassistant/carassistant.jar"]  # the given order and paths
        assert z.read("mod/custom.sh").decode() == SCRIPT and z.read("mod/carassistant/carassistant.jar") == JAR
        assert {i.date_time for i in z.infolist()} == {(2020, 1, 1, 0, 0, 0)}
        assert all((i.external_attr >> 16) & 0o111 == 0 for i in z.infolist())  # nothing marked as runnable
    assert b"token" not in one.content  # the connection file (token) is not part of it


def test_changed_files_need_a_new_approval_and_removal_cleans_up(client, installed):
    vid, item = installed
    client.post(f"/v/{vid}/integrations/{item['id']}/service/approve")
    with db.tx() as conn:
        addon = addons.get(conn, vid, item["id"])
        assert pluginsvc.approved(addon)
        newer = _manifest(sha=hashlib.sha256(b"other").hexdigest(), size=5)
        addons.update_manifest(conn, addon, addons.parse_package(json.dumps(newer).encode()), addon["pkg_sha"])
        assert not pluginsvc.approved(addons.get(conn, vid, item["id"]))  # other files: ask again
    assert client.get("/plugins/files-pkg/files/carassistant.jar").status_code == 404
    folder = pluginsvc.files_root() / "files-pkg"
    assert folder.exists()
    client.post(f"/v/{vid}/integrations/{item['id']}/delete")
    assert not folder.exists() and not (pluginsvc.root() / "files-pkg").exists()  # the files are gone with the plugin


def test_the_tools_build_the_index_with_the_files_and_the_checker_finds_a_mismatch(tmp_path):
    import runpy
    from pathlib import Path

    here = Path(__file__).parent.parent
    folder = tmp_path / "plugins" / "files-pkg"
    (folder / "assets").mkdir(parents=True)
    (folder / "scripts").mkdir()
    (folder / "assets/carassistant.jar").write_bytes(JAR)
    (folder / "scripts/custom.sh").write_text(SCRIPT)
    manifest = _manifest(sha="0" * 64, size=1)
    (folder / "plugin.json").write_text(json.dumps(manifest))
    runpy.run_path(str(here / "tools/build_plugin_package.py"))["main"](str(tmp_path), "files-pkg")
    built = json.loads((folder / "plugin.json").read_text())
    assert built["files"][0]["sha256"] == hashlib.sha256(JAR).hexdigest() and built["files"][0]["size"] == len(
        JAR
    )  # taken from the real file
    entry = json.loads((tmp_path / "plugins/index.json").read_text())["packages"][0]
    assert entry["files"] == [{"name": "carassistant.jar", "sha256": hashlib.sha256(JAR).hexdigest(), "size": len(JAR)}]
    check = runpy.run_path(str(here / "tools/check_plugin.py"))["check"]
    assert check(folder)[0] == []
    (folder / "assets/carassistant.jar").write_bytes(JAR + b"x")  # changed after the build
    errors = " ".join(check(folder)[0])
    assert "does not match the file" in errors and "not in plugins/index.json" not in errors.replace("does not match", "")
    (folder / "plugin.json").write_text(json.dumps({**built, "docs": "See {file:nothing.zip}"}))
    assert any("nothing.zip" in e for e in check(folder)[0])


def test_a_bundle_with_the_connection_file_is_made_only_in_the_guide_with_the_token(client, monkeypatch):
    from carassistant import addons_web

    manifest = _manifest(connection_file={"name": "my.cfg", "template": "token={token}\n"})
    for b in manifest["bundles"]:
        b["connection_file_to"] = "mod/carassistant/my.cfg"
    manifest["bundles"].append(
        {
            "name": "remove.zip",
            "label": "Remove",
            "entries": [{"from": "scripts/custom.sh", "to": "mod/custom.sh"}],
            "connection_file_to": "mod/my.cfg",
        }
    )
    manifest["setup"] = {"steps": [{"id": "files", "bundles": ["install.zip", "remove.zip"]}]}
    vid, item = _install(client, monkeypatch, manifest)
    assert item is not None
    client.post(f"/v/{vid}/integrations/{item['id']}/service/approve")
    assert client.get("/plugins/files-pkg/files/install.zip").status_code == 404  # never a plain download: it would be without the token
    assert client.get("/plugins/files-pkg/files/remove.zip").status_code == 404
    wrong = client.post(f"/v/{vid}/integrations/{item['id']}/guide/bundle", data={"name": "install.zip", "token": "ca_nope"})
    assert wrong.status_code in (400, 429) and wrong.content[:2] != b"PK"
    monkeypatch.setattr(addons_web, "_guide_token_ok", lambda *a: "")
    for name, path in (("install.zip", "mod/carassistant/my.cfg"), ("remove.zip", "mod/my.cfg")):
        r = client.post(f"/v/{vid}/integrations/{item['id']}/guide/bundle", data={"name": name, "token": "ca_secret"})
        assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            assert z.read(path).decode() == "token=ca_secret\n"
    other = client.post(
        f"/v/{vid}/integrations/{item['id']}/guide/bundle", data={"name": "nothing.zip", "token": "x"}, follow_redirects=False
    )
    assert other.headers.get("content-type") != "application/zip"
    with pytest.raises(addons.AddonError):  # the connection file may not overwrite an entry
        addons.clean_bundles([{"name": "a.zip", "entries": [{"from": "x.sh", "to": "m/x"}], "connection_file_to": "m/x"}], [])
