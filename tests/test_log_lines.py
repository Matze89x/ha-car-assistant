"""What the app says in the log of the add-on besides the line for every request (docs/logs.md): the intake of values, the lines it writes into the log of
a plugin, the life of the app - and what it keeps out."""

import io
import json
import logging

import pytest
from tests.test_web import create_vehicle

from carassistant import appupdate, backup, connectors, db, halive, vehiclebackup


def said(caplog, name):
    return [(r.levelname, r.getMessage()) for r in caplog.records if r.name == name]


def test_the_intake_of_values_says_the_fields_and_what_became_of_them_never_a_value(client, caplog):
    vid = create_vehicle(client)
    with db.tx() as conn, caplog.at_level(logging.DEBUG, logger="carassistant.connectors"):
        connectors.ingest(conn, vid, {"odometer_km": 987654, "range_km": 2371}, "My plugin")
        with pytest.raises(connectors.ApiError):
            connectors.ingest(conn, vid, {"nonsense": 1}, "My plugin")
    assert said(caplog, "carassistant.connectors") == [
        ("DEBUG", f"data from My plugin for vehicle {vid}: odometer_km: stored, range_km: stored"),
        ("DEBUG", f"data from My plugin for vehicle {vid} refused: unknown_field"),
    ]
    assert "987654" not in caplog.text and "2371" not in caplog.text
    caplog.clear()
    with db.tx() as conn, caplog.at_level(logging.INFO, logger="carassistant.connectors"):
        connectors.ingest(conn, vid, {"range_km": 2222}, "My plugin")
    assert said(caplog, "carassistant.connectors") == []  # (a line for debug only)


def test_a_line_the_app_writes_for_a_plugin_is_in_the_log_of_the_add_on_too_but_what_a_plugin_sends_is_not(client, caplog):
    vid = create_vehicle(client)
    with db.tx() as conn, caplog.at_level(logging.DEBUG, logger="carassistant.plugins"):
        connectors.app_log(conn, vid, "my-plugin", "warn", "app", "something is wrong")
        connectors.app_log(conn, vid, "my-plugin", "info", "app", "command unlock by Example User: sent", mirror="command unlock: sent")
        connectors.app_log(conn, vid, "my-plugin", "debug", "app", "a detail", mirror="")  # nothing to say there
        connectors.app_log(conn, vid, "my-plugin", "error", "app", "it broke")
    assert said(caplog, "carassistant.plugins") == [
        ("WARNING", f"[car {vid}] my-plugin: something is wrong"),
        ("INFO", f"[car {vid}] my-plugin: command unlock: sent"),  # not the person
        ("ERROR", f"[car {vid}] my-plugin: it broke"),
    ]
    with db.tx() as conn:
        kept = [r["message"] for r in conn.execute("SELECT message FROM vehicle_logs WHERE vehicle_id = ? ORDER BY id", (vid,))]
    assert kept == [
        "something is wrong",
        "command unlock by Example User: sent",
        "a detail",
        "it broke",
    ]  # the log of the plugin keeps every word
    caplog.clear()
    with db.tx() as conn, caplog.at_level(logging.DEBUG, logger="carassistant"):
        connectors.set_debug(conn, vid, True)
        caplog.clear()
        connectors.ingest_logs(conn, vid, {"lines": [{"level": "error", "message": "token=SECRET123 leaked"}]}, "a plugin")
        stored = conn.execute("SELECT message FROM vehicle_logs WHERE vehicle_id = ? ORDER BY id DESC LIMIT 1", (vid,)).fetchone()
    assert stored["message"] == "token=SECRET123 leaked"  # what a plugin sends stays in its own log ...
    assert "SECRET123" not in caplog.text and said(caplog, "carassistant.plugins") == []  # ... and never reaches the log of the add-on


def test_a_database_that_moves_on_says_so_once(env, monkeypatch, caplog):
    fresh = env / "fresh"
    fresh.mkdir()
    monkeypatch.setenv("CARASSISTANT_DATA", str(fresh))
    with caplog.at_level(logging.INFO, logger="carassistant.db"):
        db.migrate()
        db.migrate()
    assert said(caplog, "carassistant.db") == [("INFO", f"Database updated: schema 0 -> {len(db.MIGRATIONS)}")]


def test_the_live_connection_says_when_it_stands(caplog):
    link = halive.Link()
    with caplog.at_level(logging.INFO, logger="carassistant"):
        link._set_live(True)
        link._set_live(True)  # no change: nothing to say
        link._set_live(False)  # (the loss itself is a warning where it happens)
        link._set_live(True)
    assert said(caplog, "carassistant") == [("INFO", "Live connection to Home Assistant: connected")] * 2


def test_the_update_check_says_what_it_found(client, monkeypatch, caplog):
    class Answer(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        appupdate.urllib.request, "urlopen", lambda *a, **k: Answer(json.dumps({"version": "99.0.0", "stage": "Beta"}).encode())
    )
    with db.tx() as conn, caplog.at_level(logging.INFO, logger="carassistant.appupdate"):
        assert appupdate.check(conn) is True

        def boom(*a, **k):
            raise OSError("offline")

        monkeypatch.setattr(appupdate.urllib.request, "urlopen", boom)
        assert appupdate.check(conn) is False
    assert said(caplog, "carassistant.appupdate") == [
        ("INFO", "Update check: the newest version is 99.0.0"),
        ("INFO", "Update check: the file of the project could not be read (no connection or no answer)"),
    ]


def test_backups_and_restores_are_said_once_each(client, caplog):
    vid = create_vehicle(client)
    with caplog.at_level(logging.INFO):
        data = backup.create()
        with db.tx() as conn:
            vehiclebackup.export(conn, vid)
            vehiclebackup.export(conn, vid, local=True)  # a copy kept for safety is not worth a line
        backup.restore(data)
    assert said(caplog, "carassistant.backup") == [  # (the copy it keeps for itself before the restore is not a line)
        ("INFO", "System backup created"),
        ("INFO", f"System backup restored (schema {len(db.MIGRATIONS)})"),
    ]
    assert said(caplog, "carassistant.vehiclebackup") == [("INFO", f"Backup of vehicle {vid} created")]
