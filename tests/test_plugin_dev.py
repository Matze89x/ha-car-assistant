"""The development tool (tools/plugin_dev.py): a plugin made by the starter runs in a real Car Assistant, installed and approved, and what it sends is shown."""

import json
import re
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

import new_plugin  # tools/ is on the path (conftest)
import plugin_dev

TOOL = Path(__file__).resolve().parents[1] / "tools" / "plugin_dev.py"


def run_tool(*args: str, timeout: int = 180) -> subprocess.CompletedProcess:
    """The tool as a person runs it: a process of its own (it starts the app, sets the data folder and ends it again)."""
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, timeout=timeout, check=False)


def test_a_new_plugin_runs_in_a_real_app_and_what_it_sends_is_shown(tmp_path):
    assert new_plugin.main(["demo-dev", "--out", str(tmp_path)]) == 0
    done = run_tool(str(tmp_path / "plugins" / "demo-dev"), "--once", "--no-watch", "--set", "user=max", "--set", "password=pw")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "/v/dev-car/plugins" in done.stdout  # the address of the plugin in the app that runs
    assert "An administrator approved the service" in done.stdout and "Service started" in done.stdout  # approved for the author, running
    assert "POST /data -> 200" in done.stdout and "odometer_km" in done.stdout  # the delivery went through the Plugin API, with its token
    assert "pw" not in done.stdout.replace("password", "")  # a password of the settings is never printed


def test_it_ends_with_1_when_the_plugin_sends_nothing_and_with_a_reason_when_the_package_is_refused(tmp_path):
    assert new_plugin.main(["demo-quiet", "--out", str(tmp_path)]) == 0
    folder = tmp_path / "plugins" / "demo-quiet"
    (folder / "service" / "main.py").write_text("import carassistant_sdk as ca\n\nca.run(lambda: None, every=60)\n", encoding="utf-8")
    quiet = run_tool(str(folder), "--once", "--seconds", "6", "--no-watch", "--set", "user=max", "--set", "password=pw")
    assert quiet.returncode == 1 and "Service started" in quiet.stdout and "-> 200" not in quiet.stdout

    broken = tmp_path / "plugins" / "demo-broken"
    broken.mkdir()
    (broken / "plugin.json").write_text('{ "id": "demo-broken", ', encoding="utf-8")  # not even JSON
    refused = run_tool(str(broken), "--once")
    assert refused.returncode == 1 and "the package is not accepted" in refused.stdout

    assert run_tool(str(tmp_path / "plugins" / "nothing-here")).returncode == 2  # no plugin.json


def test_a_plugin_without_a_service_gets_a_token_for_its_own_script(tmp_path):
    """The third way of building a plugin: a script or a device that calls the Plugin API itself. The tool prints the address and the token."""
    assert new_plugin.main(["demo-device", "--no-service", "--out", str(tmp_path)]) == 0
    tool = subprocess.Popen(
        [sys.executable, "-u", str(TOOL), str(tmp_path / "plugins" / "demo-device"), "--once", "--no-watch"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    guard = threading.Timer(150, tool.kill)  # a test that hangs is a failed test
    guard.start()
    try:
        seen = []
        found = None
        for line in tool.stdout:
            seen.append(line)
            found = re.search(r"Plugin API\s+(http://\S+)/api/v1/vehicles/(\d+)/\.\.\.\s+token: (\S+)", line)
            if found:
                break
        assert found, "".join(seen)
        base, vehicle, token = found.groups()
        request = urllib.request.Request(  # the script of the person: one HTTP request with the token
            f"{base}/api/v1/vehicles/{vehicle}/data",
            data=json.dumps({"odometer_km": 4321}).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=20) as answer:
            assert answer.status == 200
        rest = tool.stdout.read()
        assert tool.wait(timeout=60) == 0, "".join(seen) + rest  # --once: ends when the first call was accepted
        assert "POST /data -> 200" in rest and "odometer_km" in rest
    finally:
        guard.cancel()
        tool.kill()
        tool.stdout.close()


def test_the_data_folder_of_a_run_holds_the_plugin_ready_to_use(client, tmp_path):
    """What the tool puts into the data folder: a plugin without a service has a token that works; an integration has none and shows its page."""
    source = tmp_path / "source"
    assert new_plugin.main(["demo-device", "--no-service", "--out", str(source)]) == 0
    vid, _pk, _slug, token = plugin_dev.install(source / "plugins" / "demo-device", {})
    assert token
    sent = client.post(f"/api/v1/vehicles/{vid}/data", json={"odometer_km": 77}, headers={"Authorization": f"Bearer {token}"})
    assert sent.status_code == 200
    assert new_plugin.main(["demo-notes", "--kind", "integration", "--out", str(source)]) == 0
    _vid, _pk, slug, token = plugin_dev.install(source / "integrations" / "demo-notes", {})
    assert token == ""  # an integration calls no API
    page = client.get(f"/v/{slug}/m/demo-notes")
    assert page.status_code == 200 and "Notes" in page.text
