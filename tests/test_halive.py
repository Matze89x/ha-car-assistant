"""The live connection to Home Assistant (carassistant/halive.py), against a made-up Home Assistant (tools/fake_ha.py) that speaks real WebSocket frames to the
real client library: the login, the entities it follows, the changes that arrive, a connection that is lost (or silent, or refused) and built up again."""

import time

import pytest
from fake_ha import FakeHA

from carassistant import ha, halive

pytest.importorskip("websocket")


def wait_for(condition, seconds=5.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture()
def fake():
    server = FakeHA().start()
    server.set("sensor.range", "300", "km")
    server.set("sensor.odo", "1000", "km")
    server.set("sensor.other", "1")
    yield server
    server.stop()


@pytest.fixture()
def quick(monkeypatch):
    """The waits of the link are seconds; for a test they are a few hundredths."""
    monkeypatch.setattr(halive.Link, "READ_TIMEOUT", 0.05)
    monkeypatch.setattr(halive.Link, "PING_EVERY", 0.2)
    monkeypatch.setattr(halive.Link, "DEAD_AFTER", 1.0)
    monkeypatch.setattr(halive.Link, "BACKOFF", (0.05, 0.1))
    monkeypatch.setattr(halive.Link, "REFUSED_WAIT", 0.3)
    monkeypatch.setattr(halive.Link, "CONNECT_TIMEOUT", 2.0)


def link_to(fake, **kw):
    heard: list[str] = []
    changes: list[bool] = []
    link = halive.Link(
        address=f"ws://127.0.0.1:{fake.port}/api/websocket",
        token=lambda: fake.token,
        snapshot=lambda: dict(fake.states),
        on_change=heard.append,
        on_state=changes.append,
        **kw,
    )
    link.heard, link.changes = heard, changes
    return link


def test_the_address_of_the_websocket_follows_the_address_of_the_rest_api(monkeypatch):
    for api, expected in (
        ("http://supervisor/core/api", "ws://supervisor/core/websocket"),  # the Supervisor, as in the add-on
        ("http://homeassistant.local:8123/api", "ws://homeassistant.local:8123/api/websocket"),
        ("https://ha.example.com/api/", "wss://ha.example.com/api/websocket"),
    ):
        monkeypatch.setenv("CARASSISTANT_HA_API", api)
        assert halive.url() == expected


def test_it_logs_in_follows_the_entities_and_takes_every_change(fake, quick):
    link = link_to(fake)
    link.follow({"sensor.range", "sensor.odo"})
    link.start()
    try:
        assert wait_for(lambda: link.live) and link.changes == [True] and link.mode == "trigger"
        states = link.states()
        assert set(states) == {"sensor.range", "sensor.odo"}  # exactly what is followed (not sensor.other)
        assert states["sensor.range"]["state"] == "300"
        fake.set("sensor.range", "250", "km")
        assert wait_for(lambda: link.states()["sensor.range"]["state"] == "250")
        assert link.heard == ["sensor.range"]
        fake.set("sensor.other", "2")  # not followed: not even sent
        fake.set("sensor.odo", "1001", "km")
        assert wait_for(lambda: link.states()["sensor.odo"]["state"] == "1001")
        assert link.heard == ["sensor.range", "sensor.odo"]
        assert fake.connections() == 1 and fake.subscriptions()[0]["entities"] == {"sensor.range", "sensor.odo"}
    finally:
        link.stop()
    assert link.changes[-1] is False and link.states() is None  # a stopped link says it has nothing


def test_what_is_followed_can_change_while_it_runs(fake, quick):
    link = link_to(fake)
    link.follow({"sensor.range"})
    link.start()
    try:
        assert wait_for(lambda: link.live)
        link.follow({"sensor.range", "sensor.odo"})  # a plugin bound one more entity
        assert wait_for(lambda: "sensor.odo" in (link.states() or {}))
        assert len(fake.subscriptions()) == 1 and fake.subscriptions()[0]["entities"] == {"sensor.range", "sensor.odo"}  # the old one ended
        link.follow({"sensor.odo"})
        assert wait_for(lambda: set(link.states() or {}) == {"sensor.odo"})
        fake.set("sensor.range", "1", "km")
        fake.set("sensor.odo", "2", "km")
        assert wait_for(lambda: link.states()["sensor.odo"]["state"] == "2")
        assert "sensor.range" not in link.states()
        link.follow(set())  # nothing to follow: the connection stays, and says nothing
        assert wait_for(lambda: link.states() == {} and not fake.subscriptions())
        assert link.live
    finally:
        link.stop()


def test_an_entity_that_is_removed_leaves_the_memory(fake, quick):
    link = link_to(fake)
    link.follow({"sensor.range"})
    link.start()
    try:
        assert wait_for(lambda: link.live)
        fake.remove("sensor.range")
        assert wait_for(lambda: "sensor.range" not in link.states())
        assert link.heard == ["sensor.range"]
        fake.set("sensor.range", "5", "km")  # and when it comes back it is there again
        assert wait_for(lambda: "sensor.range" in link.states())
    finally:
        link.stop()


def test_a_lost_connection_is_built_up_again_and_what_happened_meanwhile_is_found(fake, quick):
    link = link_to(fake)
    link.follow({"sensor.range"})
    link.start()
    try:
        assert wait_for(lambda: link.live)
        fake.drop()  # the network fails
        assert wait_for(lambda: link.changes[-1:] == [False])
        assert link.states() is None  # no live states while there is no connection: whoever reads asks Home Assistant itself
        fake.set("sensor.range", "42", "km")  # something happens while nobody listens
        assert wait_for(lambda: link.live and link.connects == 2, 5)
        assert link.states()["sensor.range"]["state"] == "42"  # the look at Home Assistant after the new login found it
        assert link.changes == [True, False, True]
        fake.set("sensor.range", "43", "km")
        assert wait_for(lambda: link.states()["sensor.range"]["state"] == "43")  # and it goes on
    finally:
        link.stop()


def test_a_connection_that_stays_open_but_is_silent_is_given_up(fake, quick):
    link = link_to(fake)
    link.follow({"sensor.range"})
    link.start()
    try:
        assert wait_for(lambda: link.live)
        fake.silent = True  # still connected, no answer to anything
        assert wait_for(lambda: link.changes[-1:] == [False], 6)
        fake.silent = False
        assert wait_for(lambda: link.live and link.connects >= 2, 6)
    finally:
        link.stop()


def test_a_refused_token_is_tried_again_only_now_and_then(fake, quick):
    fake.refuse_auth = True
    link = link_to(fake)
    link.follow({"sensor.range"})
    link.start()
    try:
        assert wait_for(lambda: "refused" in link.last_error)
        assert not link.live and link.connects == 0
        fake.refuse_auth = False  # the token is right again
        assert wait_for(lambda: link.live, 5)
    finally:
        link.stop()


def test_when_the_first_kind_of_subscription_is_refused_the_second_one_does_the_same(fake, quick):
    fake.refuse_trigger = True
    link = link_to(fake)
    link.follow({"sensor.range"})
    link.start()
    try:
        assert wait_for(lambda: link.live) and link.mode == "events"
        fake.set("sensor.other", "3")  # (everything is sent now, the link filters)
        fake.set("sensor.range", "11", "km")
        assert wait_for(lambda: link.states()["sensor.range"]["state"] == "11")
        assert "sensor.other" not in link.states() and link.heard == ["sensor.range"]
    finally:
        link.stop()


def test_a_refused_subscription_of_every_kind_ends_the_connection_and_it_tries_again(fake, quick):
    fake.refuse_subscribe = True
    link = link_to(fake)
    link.follow({"sensor.range"})
    link.start()
    try:
        assert wait_for(lambda: link.connects >= 2)  # no live states, and no standing still
        assert not link.live
        fake.refuse_subscribe = False
        assert wait_for(lambda: link.live)
    finally:
        link.stop()


def test_a_look_at_home_assistant_is_merged_by_time(fake, quick):
    link = link_to(fake)
    link.follow({"sensor.range"})
    link.start()
    try:
        assert wait_for(lambda: link.live)
        fake.set("sensor.range", "20", "km")
        assert wait_for(lambda: link.states()["sensor.range"]["state"] == "20")
        old = dict(link.states()["sensor.range"], state="19", last_updated="2000-01-01T00:00:00+00:00")
        link.merge({"sensor.range": old, "sensor.other": {"entity_id": "sensor.other", "state": "9"}})
        assert link.states()["sensor.range"]["state"] == "20"  # an older look does not undo a newer change
        assert "sensor.other" not in link.states()  # and only what is followed is kept
        newer = dict(link.states()["sensor.range"], state="21", last_updated="2099-01-01T00:00:00+00:00")
        link.merge({"sensor.range": newer})
        assert link.states()["sensor.range"]["state"] == "21"
    finally:
        link.stop()


def test_the_states_come_through_the_rest_api_of_the_add_on(fake, quick, monkeypatch):
    """The whole way as the add-on goes it: address and token from the environment, the first look through the REST API."""
    monkeypatch.setenv("CARASSISTANT_HA_API", fake.api)
    monkeypatch.setenv("SUPERVISOR_TOKEN", fake.token)
    ha._cache.clear()
    assert halive.available() and halive.url() == f"ws://127.0.0.1:{fake.port}/api/websocket"
    link = halive.Link()
    link.follow({"sensor.range"})
    link.start()
    try:
        assert wait_for(lambda: link.live)
        assert link.states()["sensor.range"]["attributes"]["unit_of_measurement"] == "km"
        fake.set("sensor.range", "77", "km")
        assert wait_for(lambda: link.states()["sensor.range"]["state"] == "77")
    finally:
        link.stop()


def test_without_the_rest_api_there_is_no_live_connection_to_trust(fake, quick):
    """A connection whose first look fails is no connection: the states it would offer are not complete."""
    fake.rest_down = True
    link = halive.Link(address=f"ws://127.0.0.1:{fake.port}/api/websocket", token=lambda: fake.token, snapshot=lambda: None)
    link.follow({"sensor.range"})
    link.start()
    try:
        assert wait_for(lambda: link.connects >= 2) and not link.live
    finally:
        link.stop()


def test_the_device_and_the_area_of_an_entity_are_read_from_the_registries(fake):
    fake.areas = [{"area_id": "garage", "name": "Garage"}, {"area_id": "yard", "name": "Yard"}]
    fake.devices = [
        {"id": "d1", "name": "Wallbox", "name_by_user": None, "area_id": "garage"},
        {"id": "d2", "name": "Gateway 7", "name_by_user": "Car gateway", "area_id": None},
    ]
    fake.entities = [
        {"entity_id": "sensor.range", "device_id": "d1", "area_id": None},  # the area of its device
        {"entity_id": "sensor.odo", "device_id": "d1", "area_id": "yard"},  # an area of its own wins
        {"entity_id": "sensor.other", "device_id": "d2", "area_id": None},  # the name the person gave wins; no area at all
        {"entity_id": "sensor.alone", "device_id": None, "area_id": None},  # nothing to say
    ]
    address, token = f"ws://127.0.0.1:{fake.port}/api/websocket", lambda: fake.token
    ha._cache.clear()
    got = halive.registry(address, token)
    assert got == {
        "sensor.range": {"device": "Wallbox", "area": "Garage"},
        "sensor.odo": {"device": "Wallbox", "area": "Yard"},
        "sensor.other": {"device": "Car gateway", "area": ""},
    }
    fake.drop()
    assert halive.registry(address, token) == got  # kept for a minute: no new connection
    ha._cache.clear()
    fake.refuse_auth = True
    assert halive.registry(address, token) is None  # Home Assistant does not tell: the list is without it, nothing else is lost
