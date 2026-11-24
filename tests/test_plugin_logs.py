"""Every plugin has ITS OWN log: lines, watched calls and what it used belong to one plugin of one car, are cut down per plugin and go with it - and only it."""

import json

from tests.test_addons import MANIFEST
from tests.test_web import create_vehicle, slug

from carassistant import addons, connectors, db


def _two_plugins(client):
    vid = create_vehicle(client)
    ids = {}
    with db.tx() as conn:
        for pid, name in (("plugin-a", "Plugin A"), ("plugin-b", "Plugin B")):
            ids[pid] = addons.add(conn, vid, addons.parse_package(json.dumps({**MANIFEST, "id": pid, "name": name}).encode()))
    return vid, ids


def _count(conn, table, vid, pid):
    return conn.execute(f"SELECT COUNT(*) FROM {table} WHERE vehicle_id = ? AND addon_id = ?", (vid, pid)).fetchone()[0]


def test_a_chatty_plugin_cannot_push_the_lines_or_the_calls_of_another_out(client):
    vid, _ids = _two_plugins(client)
    with db.tx() as conn:
        keep = min(connectors.LOG_KEEP_CHOICES)
        connectors.set_log_keep(conn, keep)
        connectors.write_logs(conn, vid, "plugin-b", [("2026-11-24T10:00:00+00:00", "info", "b", "quiet one")])
        connectors.record_traffic(conn, vid, "plugin-b", "api", "GET", "/api/v1/x", 200, 10, 5, "once")
        for i in range(keep * 3):  # A says a lot, more than the limit
            connectors.write_logs(conn, vid, "plugin-a", [("2026-11-24T10:01:00+00:00", "info", "a", f"line {i}")])
            connectors.record_traffic(conn, vid, "plugin-a", "api", "POST", "/api/v1/data", 200, 10, 5, f"call {i}")
        assert _count(conn, "vehicle_logs", vid, "plugin-a") == keep  # cut down per plugin ...
        assert _count(conn, "vehicle_traffic", vid, "plugin-a") == keep
        assert _count(conn, "vehicle_logs", vid, "plugin-b") == 1  # ... and the other plugin keeps everything it has
        assert _count(conn, "vehicle_traffic", vid, "plugin-b") == 1


def test_the_log_page_of_a_plugin_shows_only_its_own_lines(client):
    vid, ids = _two_plugins(client)
    with db.tx() as conn:
        connectors.write_logs(conn, vid, "plugin-a", [("2026-11-24T10:00:00+00:00", "info", "a", "only for a")])
        connectors.write_logs(conn, vid, "plugin-b", [("2026-11-24T10:00:00+00:00", "error", "b", "only for b")])
    a = client.get(f"/v/{slug(vid)}/integrations/{ids['plugin-a']}/logs").text
    b = client.get(f"/v/{slug(vid)}/integrations/{ids['plugin-b']}/logs").text
    assert "only for a" in a and "only for b" not in a
    assert "only for b" in b and "only for a" not in b
    assert "only for a" not in client.get(f"/v/{slug(vid)}/integrations/{ids['plugin-b']}/logs.txt").text


def test_uninstalling_a_plugin_takes_its_own_log_with_it_and_nothing_of_the_others(client):
    vid, ids = _two_plugins(client)
    with db.tx() as conn:
        for pid in ("plugin-a", "plugin-b"):
            connectors.write_logs(conn, vid, pid, [("2026-11-24T10:00:00+00:00", "warn", pid, "a line of " + pid)])
            connectors.record_traffic(conn, vid, pid, "api", "GET", "/api/v1/x", 200, 10, 5, pid)
            connectors.note_usage(conn, vid, pid, "GET", "/api/v1/vehicles/1/control", "debug")
            connectors.set_plugin_debug(conn, vid, pid, True)
    assert client.post(f"/v/{slug(vid)}/integrations/{ids['plugin-a']}/delete").status_code == 303
    with db.tx() as conn:
        for table in ("vehicle_logs", "vehicle_traffic", "plugin_usage"):
            assert _count(conn, table, vid, "plugin-a") == 0, table  # all of A is gone ...
            assert _count(conn, table, vid, "plugin-b") == 1, table  # ... all of B is still there
        assert connectors.plugin_debug(conn, vid, "plugin-a") is False and connectors.plugin_debug(conn, vid, "plugin-b") is True
    assert "a line of plugin-b" in client.get(f"/v/{slug(vid)}/integrations/{ids['plugin-b']}/logs").text
