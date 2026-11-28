"""Car Assistant against a REAL Home Assistant (tools/real_ha.py): the odometer and the trips that come from it - the things people ask about in the forum - with real
helpers (``input_number``, ``input_boolean``), a template sensor and a state machine that stamps its states the way Home Assistant does.

Opt-in: these tests need a test Home Assistant that answers (``python tools/real_ha.py setup`` once, then ``python tools/real_ha.py start``); without one they are
skipped. They share ONE Home Assistant, so a parallel run takes turns. The app itself runs in this process (the bridge and its live connection are the real code);
what is made up is only the car."""

import fcntl
import sys
import time
import urllib.error
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from tests.test_habridge import install

from carassistant import db, ha, habridge, halive, summary, trips

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import real_ha  # noqa: E402

pytest.importorskip("websocket")
pytestmark = pytest.mark.skipif(not real_ha.running(), reason="no test Home Assistant answers (python tools/real_ha.py start)")


@pytest.fixture(autouse=True)
def one_at_a_time():
    """The tests share one Home Assistant and its helpers: the workers of a parallel run take turns."""
    real_ha.HOME.mkdir(parents=True, exist_ok=True)
    with (real_ha.HOME / "tests.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


class Car:
    """A car whose Home Assistant plugin reads the real Home Assistant; the test asks and pushes time forward with ``pump``."""

    def __init__(self, client, vid, pk):
        self.client, self.vid, self.pk = client, vid, pk

    def bind(self, every=None, **rows):
        """``slot=entity`` or ``slot=(entity, {option: value})`` - the form of the plugin; the plugin reads at once. ``every``: the interval in seconds."""
        form = {} if every is None else {"every": str(every)}
        for slot, spec in rows.items():
            entity, options = (spec, {}) if isinstance(spec, str) else spec
            form[f"e.{slot}"] = entity
            form.update({f"o.{slot}.{name}": value for name, value in options.items()})
        assert self.client.post(f"/v/{self.vid}/integrations/{self.pk}/bridge", data=form).status_code == 303

    def pump(self, check, seconds=10.0):
        """What the loop of the app does: read whatever is due, again and again, until ``check()`` holds."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            habridge.tick(time.monotonic())
            if check():
                return True
            time.sleep(0.05)
        return False

    def odometer(self):
        with db.tx() as conn:
            return summary.current_odometer(conn, self.vid)

    def typed(self, km):
        with db.tx() as conn:
            summary.add_odometer(conn, self.vid, km, summary.today().isoformat(), "typed")

    def untyped(self):
        """The figure somebody typed is taken away again (a typo found)."""
        with db.tx() as conn:
            conn.execute("DELETE FROM odometer WHERE vehicle_id = ? AND source = 'typed'", (self.vid,))

    def log(self):
        with db.tx() as conn:
            return [r["message"] for r in conn.execute("SELECT message FROM vehicle_logs WHERE vehicle_id = ? ORDER BY id", (self.vid,))]

    def trips(self):
        """``([distance of every trip], number of points of the route that are kept)``."""
        with db.tx() as conn:
            rows = conn.execute("SELECT distance_km FROM trips WHERE vehicle_id = ?", (self.vid,)).fetchall()
            points = conn.execute("SELECT COUNT(*) FROM vehicle_track WHERE vehicle_id = ?", (self.vid,)).fetchone()[0]
        return [r["distance_km"] for r in rows], points


@pytest.fixture()
def car(client, monkeypatch):
    monkeypatch.setenv("CARASSISTANT_HA_API", real_ha.url() + "/api")
    monkeypatch.setenv("SUPERVISOR_TOKEN", real_ha.token())
    ha._cache.clear()
    habridge._state.clear()
    real_ha.call("input_number", "set_value", entity_id="input_number.car_odometer", value=86000)
    real_ha.call("input_boolean", "turn_off", entity_id="input_boolean.car_ignition")
    link = halive.Link()
    habridge.attach(link)
    link.start()
    vid, pk = install(client)
    client.post(f"/v/{vid}/modules/trips", data={"enabled": "1"})
    try:
        yield Car(client, vid, pk)
    finally:
        link.stop()
        habridge.attach(None)
        habridge._state.clear()


def set_helper(entity, value):
    real_ha.call("input_number", "set_value", entity_id=f"input_number.{entity}", value=value)


# ------------------------------------------------------------------ the odometer


def test_an_odometer_helper_arrives_within_seconds_and_the_next_change_too(car):
    car.bind(odometer_km="input_number.car_odometer")
    assert car.pump(lambda: car.odometer() == 86000)
    time.sleep(1.5)  # the live subscription is up
    set_helper("car_odometer", 86010.5)
    assert car.pump(lambda: car.odometer() == 86010, 8)  # an event, not the safety net that is minutes away
    set_helper("car_odometer", 86123.4)
    assert car.pump(lambda: car.odometer() == 86123, 8)


def test_a_change_right_after_saving_is_not_lost(car):
    """Found with a real Home Assistant: a change in the first moment after saving (before the live subscription was made) was seen only by the safety net."""
    car.bind(odometer_km="input_number.car_odometer")
    assert car.pump(lambda: car.odometer() == 86000)
    set_helper("car_odometer", 86050)  # at once - nothing follows the helper yet
    assert car.pump(lambda: car.odometer() == 86050, 8)


def test_a_figure_that_was_typed_higher_holds_back_the_reading_and_the_log_says_so_once(car):
    car.typed(87000)  # a fill-up, a service ... somebody typed more than the helper says
    car.bind(odometer_km="input_number.car_odometer")
    assert car.pump(lambda: any("less than the odometer" in line for line in car.log()))
    assert car.odometer() == 87000
    set_helper("car_odometer", 86200)
    car.pump(lambda: False, 2)
    assert sum("less than the odometer" in line for line in car.log()) == 1 and car.odometer() == 87000  # said once, not at every change
    set_helper("car_odometer", 87100)
    assert car.pump(lambda: car.odometer() == 87100, 8)  # it counts again as soon as it is higher


def test_a_typo_that_is_corrected_lets_the_reading_that_was_held_back_count_again(car):
    """Found with a real Home Assistant: after the correction the odometer stayed where it was until the car drove on (a parked car's helper does not change)."""
    car.bind(odometer_km="input_number.car_odometer", every=10)
    assert car.pump(lambda: car.odometer() == 86000)
    time.sleep(1.5)
    car.typed(186000)  # one digit too many
    set_helper("car_odometer", 86010)
    car.pump(lambda: False, 2.5)
    assert car.odometer() == 186000  # held back
    car.untyped()
    assert car.pump(lambda: car.odometer() == 86010, 25)  # Home Assistant changed nothing: the figure that was held back is offered again


def test_miles_are_turned_into_kilometres_and_a_helper_without_a_unit_counts_as_kilometres(car):
    real_ha.call("input_number", "set_value", entity_id="input_number.car_odometer_miles", value=53600)
    car.bind(odometer_km="input_number.car_odometer_miles")
    assert car.pump(lambda: car.odometer() == 86261)  # 53,600 mi
    set_helper("car_odometer_nounit", 86400)
    car.bind(odometer_km="input_number.car_odometer_nounit")
    assert car.pump(lambda: car.odometer() == 86400)


def test_a_template_sensor_follows_its_helper(car):
    car.bind(odometer_km="sensor.car_odometer_sensor")
    assert car.pump(lambda: car.odometer() == 86000)
    time.sleep(1.5)
    set_helper("car_odometer", 86500)
    assert car.pump(lambda: car.odometer() == 86500, 8)


def test_unavailable_and_unknown_leave_the_last_value_where_it_was(car):
    attributes = {"unit_of_measurement": "km", "device_class": "distance", "state_class": "total_increasing"}
    real_ha.set_state("sensor.fake_car_odometer", "86600", **attributes)
    car.bind(odometer_km="sensor.fake_car_odometer")
    assert car.pump(lambda: car.odometer() == 86600)
    time.sleep(1.5)
    for state in ("unavailable", "unknown"):
        real_ha.set_state("sensor.fake_car_odometer", state, **attributes)
        car.pump(lambda: False, 1.5)
        assert car.odometer() == 86600
    real_ha.set_state("sensor.fake_car_odometer", "86650.7", **attributes)
    assert car.pump(lambda: car.odometer() == 86651, 8)


def test_a_helper_made_with_the_default_maximum_cannot_hold_an_odometer(car):
    """Not our doing, but the question comes up: ``input_number`` has a maximum (100 unless set), Home Assistant refuses a higher value."""
    with pytest.raises(urllib.error.HTTPError) as refused:
        real_ha.call("input_number", "set_value", entity_id="input_number.car_odometer_default_max", value=86020)
    assert refused.value.code == 400


# ------------------------------------------------------------------ trips from a tracker


def park(entity, lat, lon, accuracy=8):
    """The tracker stands here (before the plugin is told to read it: the first thing it sees is where the car stands)."""
    real_ha.set_state(entity, "home", latitude=lat, longitude=lon, gps_accuracy=accuracy)


def drive(car, entity, steps, dlat, dlon, accuracy=8, pause=1.05):
    """From where the tracker is now it moves ``steps`` times, once a second (the time of a reading is the second Home Assistant stamped on the state)."""
    here = real_ha.api("GET", f"/api/states/{entity}")["attributes"]
    car.pump(lambda: False, 1.0)  # (the reading of the place it stood)
    for i in range(1, steps + 1):
        real_ha.set_state(
            entity,
            "not_home",
            latitude=round(here["latitude"] + i * dlat, 6),
            longitude=round(here["longitude"] + i * dlon, 6),
            gps_accuracy=accuracy,
        )
        car.pump(lambda: False, pause)


def test_a_drive_with_a_tracker_and_the_ignition_becomes_a_trip_when_the_ignition_goes_off(car):
    park("device_tracker.ca_car", 52.5, 13.4)
    car.bind(position=("device_tracker.ca_car", {"track": "1"}), ignition="input_boolean.car_ignition")
    real_ha.call("input_boolean", "turn_on", entity_id="input_boolean.car_ignition")
    car.pump(lambda: False, 1.5)
    drive(car, "device_tracker.ca_car", 10, 0.0010, 0.0006)  # about 1.5 km
    assert car.trips()[0] == [] and car.trips()[1] >= 8  # the points are kept, the drive is not over
    real_ha.call("input_boolean", "turn_off", entity_id="input_boolean.car_ignition")
    assert car.pump(lambda: car.trips()[0], 10)
    (distance,) = car.trips()[0]
    assert 0.9 < distance < 1.6  # (10 steps of about 120 m)


def test_a_person_entity_makes_trips_like_a_tracker(car):
    park("person.ca_test", 52.8, 13.7)
    car.bind(position=("person.ca_test", {"track": "1"}), ignition="input_boolean.car_ignition")
    real_ha.call("input_boolean", "turn_on", entity_id="input_boolean.car_ignition")
    car.pump(lambda: False, 1.5)
    drive(car, "person.ca_test", 8, 0.0010, 0.0006)
    real_ha.call("input_boolean", "turn_off", entity_id="input_boolean.car_ignition")
    assert car.pump(lambda: car.trips()[0], 10)


@pytest.mark.parametrize(
    ("options", "accuracy", "dlat", "why"),
    [
        ({}, 8, 0.0010, "the option *Record trips* is off (the default)"),
        ({"track": "1"}, 150, 0.0010, "the tracker calls its fix inexact (over 100 m)"),
    ],
)
def test_no_route_is_kept_when(car, options, accuracy, dlat, why):
    park("device_tracker.ca_car", 52.6, 13.5)
    car.bind(position=("device_tracker.ca_car", options), ignition="input_boolean.car_ignition")
    real_ha.call("input_boolean", "turn_on", entity_id="input_boolean.car_ignition")
    car.pump(lambda: False, 1.5)
    drive(car, "device_tracker.ca_car", 6, dlat, 0.0006, accuracy=accuracy)
    real_ha.call("input_boolean", "turn_off", entity_id="input_boolean.car_ignition")
    car.pump(lambda: False, 2)
    assert car.trips() == ([], 0), why


def test_a_tracker_that_only_jitters_keeps_no_points_and_the_ignition_off_keeps_none_either(car):
    park("device_tracker.ca_car", 52.9, 13.8)
    car.bind(position=("device_tracker.ca_car", {"track": "1"}), ignition="input_boolean.car_ignition")
    car.pump(lambda: False, 1.5)  # the ignition is off
    drive(car, "device_tracker.ca_car", 6, 0.0010, 0.0006)  # it moves, but the ignition says the car is off: nothing is kept
    assert car.trips() == ([], 0)
    real_ha.call("input_boolean", "turn_on", entity_id="input_boolean.car_ignition")
    car.pump(lambda: False, 1.5)
    drive(car, "device_tracker.ca_car", 6, 0.0000, 0.00002)  # from where it stands now: a few metres of jitter
    assert car.trips() == ([], 0)


def has_a_recorder():
    """Does this test Home Assistant keep a history (the ``recorder:`` and ``history:`` of the configuration of tools/real_ha.py)?"""
    start = (datetime.now(UTC) - timedelta(minutes=1)).isoformat().replace("+", "%2B")
    try:
        real_ha.api("GET", f"/api/history/period/{start}?filter_entity_id=input_boolean.car_ignition")
    except urllib.error.HTTPError:
        return False
    return True


@pytest.mark.skipif(
    not real_ha.running() or not has_a_recorder(),
    reason="this test Home Assistant keeps no history (restart it: python tools/real_ha.py stop; start)",
)
def test_a_drive_the_app_did_not_see_is_read_from_the_history_of_home_assistant(car, monkeypatch):
    """The app looks away (an update, a restart): the car drives, the ignition goes on and off, and when the app looks again the tracker stands somewhere else
    and nothing was seen on the way. Home Assistant's recorder has all of it - the drive becomes a trip."""
    monkeypatch.setattr(trips, "TRIP_GAP", timedelta(seconds=6))  # (a test cannot wait ten minutes for a silence in the reports)
    park("device_tracker.ca_car", 52.45, 13.45)
    car.bind(position=("device_tracker.ca_car", {"track": "1"}), ignition="input_boolean.car_ignition")
    assert car.pump(lambda: habridge._state[car.pk].get("seen"))
    with db.tx() as conn:  # (a car whose drives were recorded before)
        conn.execute(
            "INSERT INTO vehicle_track(vehicle_id, ts, lat, lon, trip_id) VALUES(?, ?, 52.45, 13.45, 0)",
            (car.vid, "2020-01-01T00:00:00+00:00"),
        )
    # the app does not look from here on: nothing is pumped
    real_ha.call("input_boolean", "turn_on", entity_id="input_boolean.car_ignition")
    time.sleep(1.1)
    for i in range(1, 9):
        real_ha.set_state(
            "device_tracker.ca_car",
            "not_home",
            latitude=round(52.45 + i * 0.0010, 6),
            longitude=round(13.45 + i * 0.0006, 6),
            gps_accuracy=8,
        )
        time.sleep(1.05)
    real_ha.call("input_boolean", "turn_off", entity_id="input_boolean.car_ignition")
    time.sleep(6.5)  # the recorder writes to its database every five seconds
    assert car.trips() == ([], 1)  # (the point put there by hand, nothing else)
    assert car.pump(lambda: car.trips()[0], 20)
    (distance,) = car.trips()[0]
    assert 0.7 < distance < 1.3  # (8 steps of about 120 m)
    assert any(line.startswith("caught up from the history of Home Assistant") for line in car.log())
