import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "carassistant" / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))  # demo_data: the made-up car of the sources repository


@pytest.fixture()
def env(tmp_path, monkeypatch):
    from carassistant import config, ha

    config.forget_external()
    config.forget_settings()  # the remembered external address belongs to one test
    ha._cache.clear()  # the answers of Home Assistant are remembered for a short time
    monkeypatch.setenv("CARASSISTANT_DATA", str(tmp_path))
    monkeypatch.setenv("CARASSISTANT_DEV", "1")
    for var in ("CARASSISTANT_TANKERKOENIG_KEY", "MQTT_HOST", "SUPERVISOR_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    from carassistant import addons_web, db

    addons_web._token_tries.clear()  # the memory of wrong token guesses belongs to one test
    from carassistant import notify

    notify._recent.clear()  # so does the memory of messages just sent
    from carassistant import refuel_detect

    refuel_detect._floor.clear()  # and the tank levels of a rise in progress
    db.migrate()
    with db.tx() as conn:
        db.set_setting(conn, "setup.language", "1")  # tests start after the first-start language choice
    return tmp_path


@pytest.fixture()
def conn(env):
    from carassistant import db

    with db.tx() as c:
        yield c


@pytest.fixture()
def vehicle(conn):
    vid = conn.execute("INSERT INTO vehicles(name, fuel_type) VALUES('Test Car', 'petrol')").lastrowid
    return vid


@pytest.fixture()
def client(env):
    from fastapi.testclient import TestClient

    from carassistant.web import app

    return TestClient(app, follow_redirects=False)


def demo_car(client=None, electric: bool = False) -> int:
    """A filled-in made-up car (tools/demo_data.py) with an installed 'Demo connector' plugin row; returns its id."""
    import json

    import demo_data

    from carassistant import db

    with db.tx() as conn:
        vid = demo_data.create(conn, electric=electric)
        manifest = {
            "id": "demo-connector",
            "kind": "plugin",
            "name": "Demo connector",
            "version": "1",
            "description": "",
            "author": "",
            "homepage": "",
            "settings": [],
        }
        conn.execute(
            "INSERT INTO vehicle_addons(vehicle_id, kind, addon_id, manifest, status, settings, created_at) VALUES(?, 'plugin', 'demo-connector', ?, 'configured', '{}', '2026-01-01')",
            (vid, json.dumps(manifest)),
        )
    return vid


def pytest_terminal_summary(terminalreporter):
    """On GitHub the log of a failed run cannot be read without signing in, but *annotations* can (the public check-runs API shows them): every failed
    test becomes one ``::error`` line, so a red run says which test failed and why - ``curl .../check-runs/<id>/annotations``."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    for report in terminalreporter.stats.get("failed", [])[:10]:
        text = (getattr(report, "longreprtext", "") or "")[-1800:]
        text = text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        title = report.nodeid.replace("::", " > ").replace(",", "%2C").replace(":", "%3A")  # a property of the command: no ":" and no ","
        terminalreporter.write_line(f"::error title=FAILED {title}::{text}")
