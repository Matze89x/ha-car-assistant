"""The starter of packages (tools/new_plugin.py): everything it makes is a package the app accepts, and the plugin it makes with a service works."""

import json
import py_compile
import runpy
import sys
from pathlib import Path

import check_plugin  # tools/ is on the path (conftest)
import new_plugin
import pytest

from carassistant import addons

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "docs" / "examples" / "sdk" / "carassistant_sdk.py"


@pytest.mark.parametrize(
    ("args", "where", "service"),
    [
        (["demo-one"], "plugins/demo-one", True),
        (["demo-two", "--login", "none"], "plugins/demo-two", True),
        (["demo-oauth", "--login", "oauth"], "plugins/demo-oauth", True),
        (["demo-three", "--no-service"], "plugins/demo-three", False),
        (["demo-conn", "--connector"], "plugins/demo-conn", False),
        (["demo-four", "--kind", "integration"], "integrations/demo-four", False),
    ],
)
def test_every_kind_it_makes_is_a_package_the_app_and_the_checker_accept(tmp_path, args, where, service):
    assert new_plugin.main([*args, "--out", str(tmp_path)]) == 0
    folder = tmp_path / where
    manifest = addons.parse_package((folder / "plugin.json").read_bytes())  # what the app does when it reads the package
    assert manifest["id"] == args[0] and bool(manifest.get("service")) is service
    errors, _notes = check_plugin.check(folder)
    assert [
        e for e in errors if "package.zip" not in e
    ] == []  # (the zip of a service is built later; the list of the source already names it)
    assert (folder / "README.md").is_file()
    if args[-1] == "--connector":  # the description came through the check of the app: one request, a map, no program
        assert manifest["connector"]["requests"][0]["auth"] == "bearer:token" and addons.needs_token(manifest) is False
    if args[-1] == "oauth":  # the step of the login came through the check of the app
        assert [st["id"] for st in manifest["setup"]["flow"]] == ["app", "connect", "done"] and manifest["setup"]["flow"][1][
            "type"
        ] == "oauth"
    if service:
        py_compile.compile(str(folder / "service" / "main.py"), doraise=True)
        assert (folder / "service" / "carassistant_sdk.py").read_bytes() == SDK.read_bytes()  # the helper library goes along, unchanged
    else:
        assert not (folder / "service").exists()


def test_it_never_overwrites_and_refuses_an_id_that_cannot_be_one(tmp_path, capsys):
    assert new_plugin.main(["demo-one", "--out", str(tmp_path)]) == 0
    manifest = tmp_path / "plugins" / "demo-one" / "plugin.json"
    manifest.write_text('{"mine": true}\n', encoding="utf-8")  # the author has changed it
    assert new_plugin.main(["demo-one", "--out", str(tmp_path)]) == 1
    assert manifest.read_text(encoding="utf-8") == '{"mine": true}\n'
    assert "exists already" in capsys.readouterr().out
    for bad in ("Demo One", "x", "../up", "a" * 60):
        assert new_plugin.main([bad, "--out", str(tmp_path)]) == 2
    assert sorted(p.name for p in (tmp_path / "plugins").iterdir()) == ["demo-one", "index.json"]  # nothing else was made


@pytest.fixture()
def made(tmp_path, monkeypatch):
    """The plugin with a service and a login, made by the starter, loaded the way the add-on starts it - with ``run`` replaced by a note of what it was given."""
    assert new_plugin.main(["demo-login", "--out", str(tmp_path)]) == 0
    service = tmp_path / "plugins" / "demo-login" / "service"
    data = tmp_path / "data"
    data.mkdir()
    for key, value in {
        "CA_DATA_DIR": str(data),
        "CA_API_URL": "http://127.0.0.1:1",
        "CA_API_TOKEN": "t",
        "CA_VEHICLE_ID": "3",
        "CA_PORT": "0",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.syspath_prepend(str(service))
    sys.modules.pop("carassistant_sdk", None)
    import carassistant_sdk as ca

    runs = []
    monkeypatch.setattr(ca, "run", lambda poll=None, every=None: runs.append((poll, every)))
    ca._routes.clear()
    ca._settings_seen.update(stamp=None, data={})
    loaded = runpy.run_path(str(service / "main.py"), run_name="plugin_main")
    yield ca, loaded, runs, data
    sys.modules.pop("carassistant_sdk", None)


def test_the_plugin_it_makes_checks_the_login_the_way_the_set_up_flow_asks(made):
    ca, loaded, _runs, _data = made
    assert [(m, p) for m, p, _f in ca._routes] == [("POST", "/demo-login/check")]  # the route the manifest names as the action of the step

    def ask(values):
        body = json.dumps({"vehicle": 3, "step": "login", "values": values}).encode()
        return loaded["check"](ca.Request("POST", "/demo-login/check", {}, {}, body))

    refused = ask({"user": "max"})  # no password yet
    assert refused["ok"] is False and "password" in refused["message"] and "settings" not in refused
    fine = ask({"user": "max", "password": "pw"})
    assert (
        fine["ok"] is True and "max" in fine["message"] and fine["settings"] == {"status": "connected"}
    )  # status: a key the service may write itself
    assert "pw" not in json.dumps(fine)  # the answer never repeats the password


def test_the_plugin_it_makes_sends_what_it_knows_to_the_car_and_keeps_polling(made, monkeypatch):
    ca, loaded, runs, data = made
    assert len(runs) == 1 and runs[0][0] is loaded["poll"] and runs[0][1] == 60  # the main loop was started with the poll and a pause
    sent = []
    monkeypatch.setattr(ca.Api, "send", lambda self, data=None, **fields: sent.append(data))
    (data / "settings.json").write_text(json.dumps({"user": "max", "password": "pw"}), encoding="utf-8")
    loaded["poll"]()
    assert sent == [{"odometer_km": 12345}]  # a made-up value, so that the author sees something arrive


def test_the_list_of_the_source_gets_its_line_and_a_whole_source_passes_the_check(tmp_path):
    """From nothing to a source the app can read: three packages, the zip of the one with a service, the list - and the check of the whole source is clean."""
    import build_plugin_package
    import check_source

    source = tmp_path / "source"
    for args in (["alpha"], ["beta", "--no-service"], ["gamma", "--kind", "integration"]):
        assert new_plugin.main([*args, "--out", str(source)]) == 0
    plugins = json.loads((source / "plugins" / "index.json").read_text(encoding="utf-8"))["packages"]
    assert [e["id"] for e in plugins] == ["alpha", "beta"] and "sha256" not in plugins[0]  # the checksum comes with the zip
    assert [e["id"] for e in json.loads((source / "integrations" / "index.json").read_text(encoding="utf-8"))["packages"]] == ["gamma"]
    errors, _hints, _count = check_source.check_source(source)
    assert any("alpha" in e for e in errors)  # a service plugin is not ready before its zip is built
    build_plugin_package.main(str(source), "alpha")
    errors, _hints, count = check_source.check_source(source)
    assert errors == [] and count == 3
    again = json.loads((source / "plugins" / "index.json").read_text(encoding="utf-8"))["packages"]
    assert len(again) == 2 and again[0]["sha256"]  # the build tool filled the line that was there, and made no second one


def test_a_list_that_is_there_is_extended_never_replaced_and_a_broken_one_is_left_alone(tmp_path, capsys):
    (tmp_path / "plugins").mkdir()
    (tmp_path / "plugins" / "index.json").write_text(json.dumps([{"id": "mine", "version": "7"}]), encoding="utf-8")  # a bare list
    assert new_plugin.main(["demo-one", "--out", str(tmp_path)]) == 0
    assert json.loads((tmp_path / "plugins" / "index.json").read_text(encoding="utf-8")) == [
        {"id": "mine", "version": "7"},
        {
            "id": "demo-one",
            "name": "Demo one",
            "version": "1",
            "description": "One sentence for the tile: what it does.",
            "icon": "wrench",
        },
    ]
    (tmp_path / "integrations").mkdir()
    (tmp_path / "integrations" / "index.json").write_text("{ broken", encoding="utf-8")
    assert new_plugin.main(["demo-two", "--kind", "integration", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "integrations" / "index.json").read_text(encoding="utf-8") == "{ broken"  # not touched
    assert "not valid JSON" in capsys.readouterr().out


def test_the_plugin_it_makes_for_a_login_with_an_account_waits_for_the_login_and_then_sends(tmp_path, monkeypatch):
    assert new_plugin.main(["demo-account", "--login", "oauth", "--out", str(tmp_path)]) == 0
    service = tmp_path / "plugins" / "demo-account" / "service"
    for key, value in {
        "CA_DATA_DIR": str(tmp_path / "data"),
        "CA_API_URL": "http://127.0.0.1:1",
        "CA_API_TOKEN": "t",
        "CA_VEHICLE_ID": "3",
        "CA_PORT": "0",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.syspath_prepend(str(service))
    sys.modules.pop("carassistant_sdk", None)
    try:
        import carassistant_sdk as ca

        monkeypatch.setattr(ca, "run", lambda poll=None, every=None: None)
        loaded = runpy.run_path(str(service / "main.py"), run_name="plugin_main")
        sent, logged = [], []
        monkeypatch.setattr(ca.Api, "send", lambda self, data=None, **fields: sent.append(data))
        monkeypatch.setattr(ca, "log", lambda message, level="info": logged.append((level, message)))
        for error in (
            "not_connected",
            "login_required",
        ):  # nobody has logged in yet / the login has expired: wait, do not crash, do not send
            monkeypatch.setattr(
                ca.Api, "connection", lambda self, step=None, renew=False, error=error: (_ for _ in ()).throw(ca.ApiError(404, error, ""))
            )
            loaded["poll"]()
        assert sent == [] and [m for _l, m in logged] == ["waiting for the login of the person"] * 2
        monkeypatch.setattr(ca.Api, "connection", lambda self, step=None, renew=False: {"access_token": "AT", "token_type": "Bearer"})
        loaded["poll"]()  # logged in: it asks with the token of the person (made-up value here) and sends
        assert sent == [{"odometer_km": 12345}]
        monkeypatch.setattr(
            ca.Api, "connection", lambda self, step=None, renew=False: (_ for _ in ()).throw(ca.ApiError(502, "provider_unreachable", ""))
        )
        with pytest.raises(ca.ApiError):  # any other trouble is the main loop's business: it notes it and tries again later
            loaded["poll"]()
    finally:
        sys.modules.pop("carassistant_sdk", None)
