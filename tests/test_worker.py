"""The background loop keeps going when one of its jobs fails: a broken MQTT broker must not stop the reminders, and the other way round."""

from carassistant import config, notify, worker
from carassistant.mqtt_ha import publisher


def test_one_failing_job_does_not_stop_the_others(env, monkeypatch):
    calls = []

    def broken(conn):
        raise RuntimeError("broker is gone")

    monkeypatch.setattr(config, "mqtt_discovery_enabled", lambda: True)
    monkeypatch.setattr(publisher, "publish_all", broken)
    monkeypatch.setattr(notify, "check_all", lambda conn: calls.append("notify"))
    state = {"poll": 0.0, "publish": -worker.PUBLISH_SECONDS, "notify": -worker.NOTIFY_SECONDS}
    worker.run_once(state, 1.0)
    assert calls == ["notify"]  # the publish failed, the reminder check still ran


def test_a_failing_reminder_check_does_not_break_the_loop(env, monkeypatch):
    def broken(conn):
        raise RuntimeError("notify service is gone")

    monkeypatch.setattr(config, "mqtt_discovery_enabled", lambda: False)
    monkeypatch.setattr(notify, "check_all", broken)
    state = {"poll": 0.0, "publish": 0.0, "notify": -worker.NOTIFY_SECONDS}
    worker.run_once(state, 1.0)  # must not raise
