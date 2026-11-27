"""The log of the add-on in Home Assistant (carassistant/logsetup.py, docs/logs.md): the format and the levels, the filter against repeats and the one
line for every request - and what it never says."""

import asyncio
import logging
import re
import threading

import pytest
from fastapi.testclient import TestClient
from tests.test_web import create_vehicle

from carassistant import asgi, logsetup, pluginsvc, proxy
from carassistant.proxy import PluginProxy


@pytest.fixture()
def tidy_logging():
    """``setup`` changes the logging of the whole process: what was there comes back after the test."""
    root, ours = logging.getLogger(), logging.getLogger("carassistant")
    saved = (list(root.handlers), root.level, ours.level)
    yield
    root.handlers[:] = saved[0]
    root.setLevel(saved[1])
    ours.setLevel(saved[2])


def record(text, level=logging.WARNING, name="carassistant.ha", args=()):
    return logging.LogRecord(name, level, __file__, 1, text, args, None)


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


def request_lines(caplog):
    """The request lines of a test, with the times blanked out."""
    return [re.sub(r"\(\d+ ms\)", "(N ms)", r.getMessage()) for r in caplog.records if r.name == "carassistant.http"]


# ------------------------------------------------------------------ the levels and the format


def test_the_level_of_the_option_is_read_in_any_case_and_uvicorn_never_goes_below_info():
    assert [logsetup.level_name(x) for x in ("DEBUG", "warning", " Error ", "", None, "loud")] == [
        "debug",
        "warning",
        "error",
        "info",
        "info",
        "info",
    ]
    assert [logsetup.uvicorn_level(x) for x in ("DEBUG", "info", "WARNING", "error")] == ["info", "info", "warning", "error"]


@pytest.mark.parametrize(("option", "ours", "root"), [("debug", 10, 30), ("info", 20, 30), ("warning", 30, 30), ("error", 40, 40)])
def test_setup_gives_our_loggers_the_level_and_the_libraries_a_warning_at_most(tidy_logging, option, ours, root):
    assert logsetup.setup(option) == ours
    assert logging.getLogger("carassistant").level == ours and logging.getLogger().level == root
    assert logging.getLogger("carassistant.habridge").getEffectiveLevel() == ours  # every module of the app sits below it
    assert (
        logging.getLogger("PIL.PngImagePlugin").getEffectiveLevel() == root
    )  # an image library is never louder than a warning, whatever the option


def test_setup_twice_leaves_one_handler_with_the_format_and_the_filter(tidy_logging):
    logsetup.setup("info")
    logsetup.setup("debug")
    mine = [h for h in logging.getLogger().handlers if getattr(h, "_carassistant", False)]
    assert len(mine) == 1 and any(isinstance(f, logsetup.RepeatFilter) for f in mine[0].filters)
    line = mine[0].format(logging.LogRecord("carassistant.worker", logging.INFO, __file__, 1, "Background jobs started", (), None))
    assert re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d INFO    carassistant\.worker: Background jobs started", line)


# ------------------------------------------------------------------ the filter against repeats


def test_the_same_warning_is_written_once_and_the_next_one_says_how_many_were_left_out():
    clock = Clock()
    repeat = logsetup.RepeatFilter(window=300, clock=clock)
    assert repeat.filter(record("HA API GET /states failed: timeout")) is True
    for clock.now in (10, 100, 299):
        assert repeat.filter(record("HA API GET /states failed: timeout")) is False
    clock.now = 400
    again = record("HA API GET /states failed: timeout")
    assert repeat.filter(again) is True
    assert again.getMessage() == "HA API GET /states failed: timeout (repeated 3x in the last 7 min)"
    clock.now = 410
    assert repeat.filter(record("HA API GET /states failed: timeout")) is False  # a new quiet time began with that line
    clock.now = 800
    third = record("HA API GET /states failed: timeout")
    assert repeat.filter(third) is True and third.getMessage().endswith("(repeated 1x in the last 7 min)")


def test_other_words_loggers_and_levels_are_not_held_back_and_nothing_below_a_warning_ever_is():
    repeat = logsetup.RepeatFilter(clock=Clock())
    assert repeat.filter(record("one thing")) and repeat.filter(record("another thing"))
    assert repeat.filter(record("one thing", name="carassistant.mqtt_ha"))  # the same words from another logger
    assert repeat.filter(record("one thing", level=logging.ERROR))  # ... or at another level
    for level in (logging.DEBUG, logging.INFO):
        assert all(repeat.filter(record("a line of the log", level=level)) for _ in range(5))  # what happened, however often it happens
    assert repeat.filter(record("MQTT disconnected: %s", args=("rc 7",)))
    assert not repeat.filter(record("MQTT disconnected: %s", args=("rc 7",)))
    assert repeat.filter(record("MQTT disconnected: %s", args=("rc 5",)))  # the words differ: another trouble


def test_the_filter_stays_small_and_a_broken_call_is_not_its_business():
    repeat = logsetup.RepeatFilter(clock=Clock())
    for n in range(logsetup.REPEAT_KEYS * 2):
        assert repeat.filter(record(f"trouble number {n}"))
    assert len(repeat._seen) <= logsetup.REPEAT_KEYS
    assert repeat.filter(record("%s and %s", args=("one",))) is True  # (the handler reports the call that does not fit, as it always did)


def test_many_threads_saying_the_same_thing_write_it_once():
    repeat = logsetup.RepeatFilter(clock=Clock())
    allowed: list[bool] = []

    def say():
        for _ in range(200):
            allowed.append(repeat.filter(record("the same trouble")))

    threads = [threading.Thread(target=say) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert allowed.count(True) == 1 and allowed.count(False) == 1599


# ------------------------------------------------------------------ the line for every request (debug only)


@pytest.fixture()
def wrapped(client):
    """The real app behind the request line."""
    from carassistant.web import app

    return TestClient(logsetup.RequestLog(app), follow_redirects=False)


def test_a_request_is_one_line_with_the_pattern_of_its_route_and_nothing_of_its_address(client, wrapped, caplog):
    vid = create_vehicle(client)
    with caplog.at_level(logging.DEBUG, logger="carassistant.http"):
        assert wrapped.get(f"/v/{vid}/fuel/import?secret=QUERYVALUE").status_code == 200
        assert wrapped.get(f"/v/{vid}/fuel/import/abcdefghijklmnopqrst").status_code == 303  # (a token in the address: a file that is gone)
        assert wrapped.get("/no/such/page").status_code == 404
    got = request_lines(caplog)
    assert got == [
        "GET /v/{vid}/fuel/import -> 200 (N ms)",
        "GET /v/{vid}/fuel/import/{token} -> 303 (N ms)",
        "GET (no page) -> 404 (N ms)",
    ]
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "QUERYVALUE" not in text and "abcdefghijklmnopqrst" not in text and "no/such" not in text


def test_the_watchdog_and_the_files_of_the_app_leave_no_line_and_a_quiet_level_none_at_all(client, wrapped, caplog):
    create_vehicle(client)
    with caplog.at_level(logging.DEBUG, logger="carassistant.http"):
        assert wrapped.get("/healthz").status_code == 200
        assert wrapped.get("/static/app.css?v=1").status_code == 200
    assert request_lines(caplog) == []
    with caplog.at_level(logging.INFO, logger="carassistant.http"):
        assert wrapped.get("/about").status_code == 200
    assert request_lines(caplog) == []


def run_asgi(app, scope):
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        pass

    asyncio.run(app(scope, receive, send))


def test_a_request_a_service_answered_is_named_by_the_plugin_and_a_failure_counts_as_500(caplog):
    async def answers(scope, receive, send):
        scope["carassistant_label"] = "plugin service 7"
        await send({"type": "http.response.start", "status": 502, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def breaks(scope, receive, send):
        raise RuntimeError("boom")

    scope = {"type": "http", "method": "POST", "path": "/svc/a-secret/x", "query_string": b"k=v"}
    with caplog.at_level(logging.DEBUG, logger="carassistant.http"):
        run_asgi(logsetup.RequestLog(answers), dict(scope))
        with pytest.raises(RuntimeError):
            run_asgi(logsetup.RequestLog(breaks), {**scope, "route": type("Route", (), {"path": "/v/{vid}"})()})
        run_asgi(logsetup.RequestLog(answers), {"type": "lifespan"})  # not a request: passes by
    assert request_lines(caplog) == ["POST plugin service 7 -> 502 (N ms)", "POST /v/{vid} -> 500 (N ms)"]
    assert "a-secret" not in " ".join(r.getMessage() for r in caplog.records)


def test_a_request_handed_to_a_plugin_service_is_named_by_the_plugin_not_by_its_address(client, monkeypatch, caplog):
    route = {"prefix": "/svc/", "port": 1, "public": True, "pk": 9, "token_header": ""}
    monkeypatch.setattr(pluginsvc, "route_for", lambda path: route if path.startswith("/svc/") else None)
    monkeypatch.setattr(proxy, "_forward", lambda port, method, target, headers, body: (200, [("content-type", "text/plain")], b"hello"))
    monkeypatch.setattr(pluginsvc, "note_car_request", lambda *a, **k: None)
    from carassistant.web import app

    edge = TestClient(logsetup.RequestLog(PluginProxy(app)), client=("8.8.8.8", 1))
    with caplog.at_level(logging.DEBUG, logger="carassistant.http"):
        assert edge.get("/svc/ping?token=SECRETVALUE").text == "hello"
    assert request_lines(caplog) == ["GET plugin service 9 -> 200 (N ms)"]
    assert "SECRETVALUE" not in caplog.text and "/svc/ping" not in caplog.text


def test_the_server_puts_the_request_line_around_the_plugin_proxy():
    assert isinstance(asgi.app, logsetup.RequestLog) and isinstance(asgi.app.app, proxy.PluginProxy)
