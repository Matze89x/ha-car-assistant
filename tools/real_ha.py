#!/usr/bin/env python3
"""A REAL Home Assistant to test against (Home Assistant Core in a virtual environment of its own, outside the repository) - what tools/fake_ha.py cannot tell:
the real REST and WebSocket API, real helpers (``input_number``, ``input_boolean`` ...), template sensors and the way Home Assistant stamps its states.

    python tools/real_ha.py setup     once: the virtual environment, Home Assistant, a made-up configuration with helpers, a test user and a token (about 5 minutes)
    python tools/real_ha.py start     starts it on 127.0.0.1:8124 (in the background)
    python tools/real_ha.py stop
    python tools/real_ha.py status

Everything lives in ``~/.ha-test`` (configuration, token, log) and ``~/.venvs/ha-core`` (Home Assistant); ``CA_REAL_HA_HOME``, ``CA_REAL_HA_VENV`` and
``CA_REAL_HA_PORT`` change that. Home Assistant needs Python 3.14 or newer (``python3.14`` / ``python3.15`` is looked for). It is only a test system: its user and
its token are made up and good for this machine only. tests/test_real_ha.py skips itself when no such Home Assistant answers."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HOME = Path(os.environ.get("CA_REAL_HA_HOME", Path.home() / ".ha-test"))
VENV = Path(os.environ.get("CA_REAL_HA_VENV", Path.home() / ".venvs" / "ha-core"))
PORT = int(os.environ.get("CA_REAL_HA_PORT", "8124"))
CONFIG, TOKEN, PIDFILE, LOG = HOME / "config", HOME / "token", HOME / "hass.pid", HOME / "hass.log"

YAML = """# A made-up Home Assistant for testing Car Assistant against a real one (tools/real_ha.py). Nothing private in it.
homeassistant:
  name: CA Test
  latitude: 52.52
  longitude: 13.405
  elevation: 34
  unit_system: metric
  currency: EUR
  country: DE
  time_zone: Europe/Berlin

http:
  server_host: 127.0.0.1
  server_port: __PORT__

frontend:
api:
websocket_api:
logger:
  default: warning

# helpers - the kind people create under Settings -> Devices & services -> Helpers
input_number:
  car_odometer:
    name: Car odometer
    min: 0
    max: 1000000
    step: 0.1
    mode: box
    unit_of_measurement: km
    initial: 86000
  car_odometer_default_max:  # a helper made with the default maximum (100): it cannot hold an odometer
    name: Car odometer (default maximum)
    min: 0
    max: 100
    step: 1
    mode: box
    unit_of_measurement: km
    initial: 50
  car_odometer_miles:
    name: Car odometer miles
    min: 0
    max: 1000000
    step: 0.1
    mode: box
    unit_of_measurement: mi
    initial: 53000
  car_odometer_nounit:
    name: Car odometer without a unit
    min: 0
    max: 1000000
    step: 1
    mode: box
    initial: 86000
input_boolean:
  car_ignition:
    name: Car ignition
    initial: false
template:
  - sensor:
      - name: Car odometer sensor
        unique_id: car_odometer_sensor
        unit_of_measurement: km
        device_class: distance
        state_class: total_increasing
        state: "{{ states('input_number.car_odometer') | float(0) }}"
"""

# runs in the virtual environment of Home Assistant (it has aiohttp): the first user, a long-lived token, the confirmation of the http settings
ONBOARD = r"""
import asyncio, json, os, sys
import aiohttp
base, token_file, login_file = sys.argv[1:4]
async def main():
    async with aiohttp.ClientSession() as s:
        steps = await (await s.get(base + "/api/onboarding")).json()
        if next(x for x in steps if x["step"] == "user")["done"]:
            raise SystemExit("the user exists already")
        password = __import__("secrets").token_urlsafe(16)
        body = {"client_id": base + "/", "name": "CA Test", "username": "catest", "password": password, "language": "en"}
        code = (await (await s.post(base + "/api/onboarding/users", json=body)).json())["auth_code"]
        open(login_file, "w").write("user: catest\npassword: " + password + "\n")
        os.chmod(login_file, 0o600)
        tok = await (await s.post(base + "/auth/token", data={"grant_type": "authorization_code", "code": code, "client_id": base + "/"})).json()
        async with s.ws_connect(base + "/api/websocket") as ws:
            await ws.receive_json()
            await ws.send_json({"type": "auth", "access_token": tok["access_token"]})
            assert (await ws.receive_json())["type"] == "auth_ok"
            await ws.send_json({"id": 1, "type": "auth/long_lived_access_token", "client_name": "car-assistant-test", "lifespan": 3650})
            open(token_file, "w").write((await ws.receive_json())["result"])
            os.chmod(token_file, 0o600)
            await ws.send_json({"id": 2, "type": "http/config/promote"})  # the settings of the YAML are tried out until somebody confirms them
            await ws.receive_json()
        hdr = {"Authorization": "Bearer " + tok["access_token"]}
        for path, extra in (("core_config", {}), ("analytics", {}), ("integration", {"client_id": base + "/", "redirect_uri": base + "/?auth_callback=1"})):
            await s.post(base + "/api/onboarding/" + path, json=extra, headers=hdr)
asyncio.run(main())
"""


def _run(args: list[str]) -> None:
    subprocess.run(args, check=True)  # noqa: S603 - the arguments are made in this file


def url() -> str:
    return f"http://127.0.0.1:{PORT}"


def token() -> str:
    return TOKEN.read_text().strip() if TOKEN.is_file() else ""


def api(method: str, path: str, body: dict | None = None, timeout: float = 15):
    """One call of the REST API of the test Home Assistant (``GET /api/states``, ``POST /api/services/input_number/set_value`` ...)."""
    request = urllib.request.Request(  # noqa: S310 - 127.0.0.1
        url() + path,
        data=None if body is None else json.dumps(body).encode(),
        method=method,
        headers={"Authorization": f"Bearer {token()}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as answer:  # noqa: S310
        raw = answer.read()
        return json.loads(raw) if raw else None


def set_state(entity: str, state: str, **attributes):
    """Put an entity into the state machine (a tracker of a phone app, a sensor of a car integration ...)."""
    return api("POST", f"/api/states/{entity}", {"state": state, "attributes": attributes})


def call(domain: str, service: str, **data):
    return api("POST", f"/api/services/{domain}/{service}", data)


def running() -> bool:
    """Does a test Home Assistant answer (with the token of this tool)?"""
    if not token():
        return False
    try:
        return "API running" in str(api("GET", "/api/", timeout=2))
    except (OSError, ValueError):
        return False


def _python() -> str:
    for name in ("python3.15", "python3.14"):
        found = shutil.which(name)
        if found:
            return found
    if sys.version_info >= (3, 14):
        return sys.executable
    raise SystemExit("Home Assistant needs Python 3.14 or newer (python3.14 or python3.15 was not found)")


def setup() -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    HOME.chmod(0o700)
    if not (VENV / "bin" / "hass").exists():
        print("making the virtual environment and installing Home Assistant (a few minutes) ...", flush=True)
        _run([_python(), "-m", "venv", str(VENV)])
        pip = [str(VENV / "bin" / "pip"), "install", "--quiet"]
        _run([*pip, "--upgrade", "pip", "wheel"])
        _run([*pip, "homeassistant"])
    CONFIG.mkdir(parents=True, exist_ok=True)
    (CONFIG / "configuration.yaml").write_text(YAML.replace("__PORT__", str(PORT)))
    start(wait=True)
    if token() and running():
        print("the test Home Assistant is ready:", url())
        return
    _run([str(VENV / "bin" / "python"), "-c", ONBOARD, url(), str(TOKEN), str(HOME / "login.txt")])
    print("a test user and a token were made; Home Assistant answers on", url())


def answers() -> bool:
    """Does a Home Assistant answer on the port (whoever made it)?"""
    try:
        return urllib.request.urlopen(url() + "/api/onboarding", timeout=2).status == 200  # noqa: S310 - 127.0.0.1
    except (OSError, ValueError):
        return False


def start(wait: bool = True) -> None:
    if answers():
        print("it runs already:", url())
        return
    if not (VENV / "bin" / "hass").exists():
        raise SystemExit("not set up yet: python tools/real_ha.py setup")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("w") as log:
        command = [str(VENV / "bin" / "hass"), "-c", str(CONFIG)]
        proc = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)  # noqa: S603 - made in this file
    PIDFILE.write_text(str(proc.pid))
    if not wait:
        return
    end = time.time() + 240
    while time.time() < end:
        if answers():
            return
        if proc.poll() is not None:
            raise SystemExit(f"Home Assistant ended at once - see {LOG}")
        time.sleep(2)
    raise SystemExit(f"Home Assistant did not answer in four minutes - see {LOG}")


def stop() -> None:
    if not PIDFILE.is_file():
        print("no pid file - nothing to stop")
        return
    pid = int(PIDFILE.read_text())
    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(60):
            time.sleep(0.5)
            os.kill(pid, 0)  # raises when it is gone
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    PIDFILE.unlink(missing_ok=True)
    print("stopped")


def main(argv: list[str]) -> int:
    command = argv[0] if argv else "status"
    if command == "setup":
        setup()
    elif command == "start":
        start()
    elif command == "stop":
        stop()
    elif command == "status":
        print(f"{'running' if running() else 'not running'}: {url()}   (config {CONFIG})")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
