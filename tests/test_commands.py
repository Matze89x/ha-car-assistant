"""Commands to the car (``command`` on a button of a plugin, docs/plugins.md, "Commands to the car"): a vocabulary the app knows, a question that is asked by
the server before a command that cannot be taken back lightly, a line in the log of the plugin for every command, and a limit against a storm."""

import json

import pytest
from tests.test_addons import MANIFEST
from tests.test_web import create_vehicle, slug

from carassistant import addons, addons_web, db, pluginsvc

SERVICE = {
    "entry": "service/main.py",
    "python": ">=3.9",
    "requirements": [],
    "routes": [{"prefix": "/svc/", "public": True}, {"prefix": "/priv/", "public": False}],
}
BUTTONS = [
    {"id": "lock", "label": "Lock", "action": "/priv/lock", "command": "lock"},
    {"id": "unlock", "label": "Unlock", "action": "/priv/unlock", "command": "unlock", "timeout": 500},
    {"id": "wash", "label": "Wash", "action": "/priv/wash", "command": "wash_the_car"},  # not in the vocabulary
]


def test_the_vocabulary_is_read_with_its_icons_and_limits():
    got = {b["id"]: b for b in addons.clean_buttons(BUTTONS, [], SERVICE)}
    assert got["lock"]["command"] == "lock" and got["lock"]["icon"] == "lock" and got["lock"]["timeout"] == 20
    assert got["unlock"]["icon"] == "lock-open-variant" and got["unlock"]["timeout"] == 60  # a minute at most
    assert "command" not in got["wash"] and got["wash"]["action"] == "/priv/wash"  # an unknown name is an ordinary button
    assert (
        addons.clean_buttons([{"id": "p", "label": "P", "page": "docs", "command": "lock"}], [{"id": "docs"}], SERVICE)[0].get("command")
        is None
    )  # only a service route can send one
    assert {n for n, (danger, _icon) in addons.COMMANDS.items() if danger} == {"unlock", "climate_on", "open_trunk"}


@pytest.fixture()
def car(client, monkeypatch):
    monkeypatch.setattr(pluginsvc, "approved", lambda addon: True)
    monkeypatch.setattr(pluginsvc, "ready", lambda pk: True)
    addons_web._command_times.clear()
    sent = []
    monkeypatch.setattr(
        pluginsvc, "call", lambda pk, path, payload, vehicle, user="ha", timeout=10.0: sent.append((path, payload, timeout)) or (True, "")
    )
    vid = create_vehicle(client)
    manifest = {**MANIFEST, "id": "cmd-demo", "service": SERVICE, "buttons": BUTTONS}
    with db.tx() as conn:
        source = conn.execute("SELECT id FROM sources LIMIT 1").fetchone()["id"]
        pk = addons.add(conn, vid, addons.parse_package(json.dumps(manifest).encode()), source, "0" * 64)
        conn.execute("UPDATE vehicle_addons SET active = 1 WHERE id = ?", (pk,))
    return vid, pk, sent


def _log(vid):
    with db.tx() as conn:
        return [
            (r["level"], r["message"])
            for r in conn.execute("SELECT level, message FROM vehicle_logs WHERE vehicle_id = ? ORDER BY id", (vid,))
        ]


def test_a_command_goes_to_the_service_with_its_name_and_leaves_a_line_in_the_log(client, car):
    vid, pk, sent = car
    base = f"/v/{slug(vid)}/integrations/{pk}/button"
    done = client.post(f"{base}/lock")
    assert done.status_code == 200 and "addon-status ok" in done.text
    assert sent == [("/priv/lock", {"vehicle": vid, "button": "lock", "language": "en", "command": "lock"}, 20.0)]
    level, message = _log(vid)[-1]
    assert level == "info" and message.startswith("command lock by ") and message.endswith(": sent")  # who, what, and how it went


def test_a_command_that_cannot_be_taken_back_lightly_is_asked_by_the_server(client, car):
    vid, pk, sent = car
    base = f"/v/{slug(vid)}/integrations/{pk}/button"
    ask = client.post(f"{base}/unlock")  # a press without the answer yes
    assert (
        ask.status_code == 200 and 'name="confirmed" value="1"' in ask.text and sent == [] and _log(vid) == []
    )  # nothing was sent, nothing was written
    assert client.get(f"{base}/unlock").status_code == 200 and sent == []  # the page itself can be opened any time
    done = client.post(f"{base}/unlock", data={"confirmed": "1"})
    assert done.status_code == 200 and [p["command"] for _path, p, _t in sent] == ["unlock"] and sent[0][2] == 60.0
    level, message = _log(vid)[-1]
    assert level == "warn" and message.startswith("command unlock by ")  # a dangerous one is a warning line: it stands out in the log
    assert client.get(f"{base}/lock").status_code == 404  # (a command that is no question has no page)
    tile = client.get(f"/v/{slug(vid)}/plugins").text
    assert f'href="/v/{slug(vid)}/integrations/{pk}/button/unlock"' in tile  # the tile links to the question instead of posting
    assert f'action="/v/{slug(vid)}/integrations/{pk}/button/lock"' in tile  # and posts the harmless one at once


def test_a_failure_is_written_down_and_a_storm_is_stopped(client, car, monkeypatch):
    vid, pk, sent = car
    base = f"/v/{slug(vid)}/integrations/{pk}/button"
    monkeypatch.setattr(pluginsvc, "call", lambda *a, **k: (False, "The car is asleep."))
    failed = client.post(f"{base}/lock")
    assert "The car is asleep." in failed.text
    assert _log(vid)[-1][0] == "warn" and _log(vid)[-1][1].endswith("failed - The car is asleep.")  # a failure is a warning, not news
    monkeypatch.setattr(pluginsvc, "call", lambda pk, path, payload, vehicle, user="ha", timeout=10.0: sent.append(path) or (True, ""))
    for _ in range(addons_web.COMMAND_LIMIT):  # (the failed one counted, too)
        client.post(f"{base}/lock")
    stopped = client.post(f"{base}/lock")
    assert "Too many commands" in stopped.text and len(sent) == addons_web.COMMAND_LIMIT - 1  # not sent: the car is not flooded
    assert _log(vid)[-1][0] == "warn" and "failed - " in _log(vid)[-1][1]
