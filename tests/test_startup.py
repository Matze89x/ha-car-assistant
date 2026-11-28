"""Start-up checks: the add-on start script and the real server start (what the unit tests do not cover)."""

import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

SHIM = r"""
# stand-in for bashio: options come from OPT_<name>; only the ones set in the environment have a value
bashio::config() { local v="OPT_$1"; printf '%s' "${!v-}"; }
bashio::config.has_value() { local v="OPT_$1"; [ -n "${!v-}" ]; }
bashio::jq() { printf 'from-jq'; }
curl() { if [ -n "${FAKE_MQTT-}" ]; then printf '%s' "$FAKE_MQTT"; else return 22; fi; }  # the Supervisor answers for the service of a broker - or there is none
bashio::log.info() { echo "INFO $*"; }
"""


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash needed")
@pytest.mark.parametrize(
    "options",
    [
        {},
        {"OPT_language": "en"},
        {"OPT_language": "de", "OPT_external_url": "https://car.example.com"},
        {"OPT_mqtt_sensors": "true", "OPT_mqtt_host": "broker.lan", "OPT_mqtt_port": "1883"},
    ],
)
def test_run_sh_starts_with_any_combination_of_optional_options(options, tmp_path):
    """The Supervisor runs run.sh with unset-variable errors on: optional options that are not set must not break it."""
    result = _run_sh(tmp_path, options)
    assert result.returncode == 0 and "RUN_SH_OK" in result.stdout, result.stderr + result.stdout


def _run_sh(tmp_path, options):
    """run.sh without its last two lines (the app itself), with the stand-in for bashio, then what it exported is printed."""
    lines = (ROOT / "carassistant" / "run.sh").read_text().splitlines()[1:]
    body = "\n".join(line for line in lines if not line.startswith(("cd /app", "exec ")))
    script = tmp_path / "run_test.sh"
    script.write_text(SHIM + "set -eu\n" + body + '\necho "RUN_SH_OK MQTT_HOST=${MQTT_HOST:-none}"\n')
    env = {"PATH": os.environ["PATH"], "OPT_log_level": "info", **options}
    return subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True, timeout=30)


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash needed")
def test_run_sh_asks_for_the_mqtt_service_quietly(tmp_path):
    """No broker is no error: nothing may be written to the log about it (bashio::services.available logged an ERROR line at every start). A broker
    that is there is used."""
    without = _run_sh(tmp_path, {})
    assert without.returncode == 0 and "MQTT_HOST=none" in without.stdout and "ERROR" not in without.stdout + without.stderr
    with_broker = _run_sh(tmp_path, {"FAKE_MQTT": '{"result": "ok", "data": {"host": "broker"}}'})
    assert with_broker.returncode == 0 and "MQTT_HOST=from-jq" in with_broker.stdout


def test_server_really_starts_and_migrates_a_fresh_data_folder(tmp_path):
    """`python -m carassistant` with a fresh data folder: migrations run, the server answers /healthz and the first page."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {
        **os.environ,
        "CARASSISTANT_DATA": str(tmp_path),
        "CARASSISTANT_PORT": str(port),
        "PYTHONPATH": str(ROOT / "carassistant" / "app"),
    }
    for var in ("SUPERVISOR_TOKEN", "MQTT_HOST"):
        env.pop(var, None)
    proc = subprocess.Popen([sys.executable, "-m", "carassistant"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        deadline, body = time.time() + 30, None
        while time.time() < deadline and body is None:
            if proc.poll() is not None:
                pytest.fail("server exited: " + (proc.stdout.read() if proc.stdout else ""))
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=2) as r:
                    body = r.read()
            except OSError:
                time.sleep(0.3)
        assert body is not None, "no answer from /healthz"
        opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler())
        with opener.open(f"http://127.0.0.1:{port}/", timeout=5) as page:
            assert page.status == 200 and re.search(r"English|Deutsch", page.read().decode())  # first start: the language question
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
