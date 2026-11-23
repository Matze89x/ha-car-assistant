"""An own (external) MQTT broker: typed addresses, add-on options left empty, the reason shown when it is not reached."""

import socket

import pytest

from carassistant import config, mqtt_ha


@pytest.mark.parametrize(
    ("host", "port", "expected"),
    [
        ("192.168.1.5", None, ("192.168.1.5", 1883, False)),
        ("  192.168.1.5  ", "1884", ("192.168.1.5", 1884, False)),
        ("192.168.1.5:1885", None, ("192.168.1.5", 1885, False)),
        ("mqtt://nuc.local:1883", "", ("nuc.local", 1883, False)),
        ("mqtt://nuc.local/", None, ("nuc.local", 1883, False)),
        ("mqtts://broker.example.com", None, ("broker.example.com", 8883, True)),
        ("broker.example.com", "8883", ("broker.example.com", 8883, True)),
        ("[::1]:1884", None, ("::1", 1884, False)),
        ("192.168.1.5", "null", ("192.168.1.5", 1883, False)),  # an add-on option left empty arrives as the word null
        ("192.168.1.5", "70000", ("192.168.1.5", 1883, False)),
        ("192.168.1.5", "abc", ("192.168.1.5", 1883, False)),
    ],
)
def test_the_address_is_understood_however_it_was_typed(host, port, expected):
    got = config.clean_broker(host, port)
    assert (got["host"], got["port"], got["tls"]) == expected


@pytest.mark.parametrize("host", [None, "", "   ", "null", "None", "mqtt://", "://"])
def test_no_host_is_no_broker(host):
    assert config.clean_broker(host, "1883") is None


def test_addon_options_left_empty_are_no_login_and_no_crash(env, monkeypatch):
    monkeypatch.setenv("MQTT_HOST", "192.168.1.5")
    monkeypatch.setenv("MQTT_PORT", "null")
    monkeypatch.setenv("MQTT_USER", "null")
    monkeypatch.setenv("MQTT_PASSWORD", "null")
    assert config.mqtt_settings() == {"host": "192.168.1.5", "port": 1883, "tls": False, "user": None, "password": None}
    monkeypatch.setenv("MQTT_USER", "house")
    monkeypatch.setenv("MQTT_PASSWORD", "secret")
    got = config.mqtt_settings()
    assert got["user"] == "house" and got["password"] == "secret"


def test_the_system_page_still_opens_with_such_options_and_shows_the_reason(env, monkeypatch):
    from fastapi.testclient import TestClient

    from carassistant import db, web

    monkeypatch.setenv("MQTT_HOST", "192.168.1.5")
    monkeypatch.setenv("MQTT_PORT", "null")
    monkeypatch.setenv("MQTT_SENSORS", "1")
    with db.tx() as conn:
        db.set_setting(conn, "setup.language", "1")
    client = TestClient(web.app, base_url="http://testserver", headers={"Origin": "http://testserver"})
    assert client.get("/settings/system").status_code == 200
    monkeypatch.setattr(mqtt_ha.publisher, "last_error", "dns")
    page = client.get("/settings/system")
    assert "Use the IP address of the broker" in page.text and "mqtt://192.168.1.5:1883" in page.text
    monkeypatch.setattr(mqtt_ha.publisher, "last_error", "")
    assert "Use the IP address of the broker" not in client.get("/settings/system").text


@pytest.mark.parametrize(
    ("raised", "kind"),
    [
        (socket.gaierror(), "dns"),
        (ConnectionRefusedError(), "refused"),
        (TimeoutError(), "timeout"),
        (OSError(65, "No route to host"), "unreach"),
    ],
)
def test_the_reason_a_broker_is_not_reached(monkeypatch, raised, kind):
    def fail(*a, **kw):
        raise raised

    monkeypatch.setattr(mqtt_ha.socket, "create_connection", fail)
    assert mqtt_ha.diagnose("192.168.1.5", 1883) == kind


def test_a_port_that_answers_but_is_no_broker_is_said_so(monkeypatch):
    class Open:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(mqtt_ha.socket, "create_connection", lambda *a, **kw: Open())
    assert mqtt_ha.diagnose("192.168.1.5", 1883) == "protocol"


def test_every_reason_has_a_text_in_both_languages():
    from carassistant import i18n
    from carassistant.web import MQTT_ERRORS

    for key in MQTT_ERRORS.values():
        assert i18n.CATALOGS["en"][key] and i18n.CATALOGS["de"][key] != i18n.CATALOGS["en"][key]


def test_each_installation_has_one_stable_client_id(env):
    first = mqtt_ha.Publisher._client_id()
    assert first.startswith("carassistant-") and len(first) > len("carassistant-")
    assert mqtt_ha.Publisher._client_id() == first  # the same one after a restart: nothing is re-created
