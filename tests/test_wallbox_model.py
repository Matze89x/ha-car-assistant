"""What the wallbox card knows (carassistant/wallbox.py): the state from the word of the wallbox or from what the car says, the power against what the wallbox may give,
the figures of the charge, the end, the curve - and nothing that is not known."""

from datetime import UTC, datetime, timedelta

import pytest
from tests.test_web import create_vehicle

from carassistant import charge_detect, connectors, db, wallbox

NOW = datetime(2026, 11, 28, 18, 0, tzinfo=UTC)


def live(at=NOW, **values):
    """The live rows of a car: ``live(charge_state="charging", charge_power_kw=7.4)`` (``None`` leaves a key out)."""
    return {key: (str(value), at) for key, value in values.items() if value is not None}


def car(client, battery_kwh=60.0, price=None):
    vid = create_vehicle(client, "Card Car")
    with db.tx() as conn:
        conn.execute("UPDATE vehicles SET fuel_type = 'electric', battery_kwh = ? WHERE id = ?", (battery_kwh, vid))
        if price is not None:
            charge_detect.set_home_price(conn, vid, price)
    return vid


def card(vid, rows, now=NOW):
    with db.tx() as conn:
        return wallbox.model(conn, vid, rows, now)


# ------------------------------------------------------------------ the state


def test_the_word_of_the_wallbox_is_the_state_and_a_fault_wins():
    assert wallbox.state_of(live(charge_state="waiting")) == ("waiting", "wallbox")
    assert wallbox.state_of(live(charge_state="charging", charge_fault="E-12 residual current")) == ("fault", "wallbox")
    assert wallbox.state_of(live(charge_state="bogus")) == (None, "")  # a word the Plugin API would never have stored


def test_a_car_that_only_says_charging_and_plugged_gets_a_state_too():
    assert wallbox.state_of(live(charging="yes", plugged="yes")) == ("charging", "car")
    assert wallbox.state_of(live(charging="no", plugged="yes")) == ("plugged", "car")
    assert wallbox.state_of(live(charging="no", plugged="no")) == ("unplugged", "car")
    assert wallbox.state_of(live(charging="no")) == (None, "")  # nothing says whether a cable is in


def test_a_card_is_drawn_for_a_wallbox_or_a_car_that_charges_and_for_nothing_else():
    assert wallbox.wanted(live(charge_state="unplugged"))
    assert wallbox.wanted(live(charge_session_kwh=3))
    assert wallbox.wanted(live(charge_total_kwh=4210.4))
    assert wallbox.wanted(live(charging="yes", plugged="yes"))
    assert not wallbox.wanted(live(charging="no", plugged="yes", battery_pct=80))  # the Home car data say that already
    assert not wallbox.wanted(live(battery_pct=80, charge_limit_pct=90))
    assert not wallbox.wanted({})


def test_nothing_to_draw_is_none(client):
    vid = car(client)
    assert card(vid, {}) is None and card(vid, live(battery_pct=70)) is None


# ------------------------------------------------------------------ a charge that runs


def test_a_charge_that_runs_says_power_limit_energy_cost_and_the_end(client):
    vid = car(client, battery_kwh=60, price=0.30)
    rows = live(
        charge_state="charging", charge_power_kw=7.4, charge_session_kwh=3.7, charge_session_minutes=30, charge_voltage_v=230, charge_current_a=10.7,
        charge_phases=3, charge_current_limit_a=16, battery_pct=50, charge_limit_pct=80, charge_mode="Solar", charge_total_kwh=4214.1, charge_temp_c=34,
    )  # fmt: skip
    m = card(vid, rows)
    assert m["state"] == "charging" and m["source"] == "wallbox" and not m["stale"]
    assert m["kw"] == 7.4 and m["phases"] == 3 and m["amps"] == 10.7 and m["volts"] == 230
    assert m["max_kw"] == pytest.approx(11.04) and m["load_pct"] == pytest.approx(7.4 / 11.04 * 100)  # 16 A on three phases
    assert m["energy_kwh"] == 3.7 and m["minutes"] == 30 and m["cost"] == 1.11 and m["price"] == 0.30
    assert m["left_min"] == round(30 / 100 * 60 / 7.4 * 60)  # 18 kWh are missing to 80 %: 146 minutes at 7.4 kW
    assert m["finish"] == (NOW + timedelta(minutes=m["left_min"])).astimezone().strftime("%H:%M")
    assert m["mode"] == "Solar" and m["total_kwh"] == 4214.1 and m["temp_c"] == 34


def test_the_power_is_worked_out_from_volts_and_amperes_when_the_wallbox_gives_none(client):
    vid = car(client)
    m = card(vid, live(charge_state="charging", charge_voltage_v=230, charge_current_a=16, charge_phases=1))
    assert m["kw"] == pytest.approx(3.68) and m["phases"] == 1
    m = card(vid, live(charge_state="charging", charge_power_kw=11.0, charge_voltage_v=230, charge_current_a=16))
    assert m["phases"] == 3  # 11 kW at 230 V and 16 A can only be three phases


def test_what_is_not_known_is_not_made_up(client):
    vid = car(client, battery_kwh=None, price=None)
    m = card(vid, live(charge_state="charging", charge_power_kw=7.4))
    assert m["soc"] is None and m["left_min"] is None and m["finish"] is None  # no battery, no target: no end
    assert m["max_kw"] is None and m["energy_kwh"] is None and m["cost"] is None and m["loss_pct"] is None and m["range_km"] is None
    assert m["load_pct"] == 100.0  # without a limit the bar is full at the power that flows


def test_a_power_that_was_reported_last_is_not_the_power_now(client):
    vid = car(client)
    m = card(vid, live(charge_state="finished", charge_power_kw=7.4, charge_session_kwh=8.2))
    assert m["state"] == "finished" and m["kw"] == 0.0 and m["energy_kwh"] == 8.2  # what was charged stays, the power does not


def test_a_charge_without_news_for_a_while_is_no_longer_live(client):
    vid = car(client)
    old = NOW - timedelta(minutes=wallbox.STALE_MINUTES + 5)
    assert card(vid, live(at=old, charge_state="charging", charge_power_kw=7.4))["stale"]
    assert not card(vid, live(at=NOW - timedelta(minutes=2), charge_state="charging", charge_power_kw=7.4))["stale"]
    assert not card(vid, live(at=old, charge_state="finished", charge_session_kwh=8.2))[
        "stale"
    ]  # a finished charge sends nothing more: that is fine


def test_the_open_session_gives_the_start_the_loss_and_the_curve(client):
    vid = car(client, battery_kwh=60, price=0.30)
    started = NOW - timedelta(minutes=75)
    with db.tx() as conn:
        sid = conn.execute(
            "INSERT INTO charge_sessions(vehicle_id, started, start_pct, end_pct, max_kw) VALUES(?, ?, 20, 20, 7.4)",
            (vid, started.isoformat(timespec="seconds")),
        ).lastrowid
        for n, kw in enumerate((1.5, 4.0, 7.2, 7.4, 7.4)):
            conn.execute(
                "INSERT INTO charge_samples(session_id, at, kw) VALUES(?,?,?)",
                (sid, (started + timedelta(minutes=n * 15)).isoformat(timespec="seconds"), kw),
            )
    m = card(
        vid,
        live(charge_state="charging", charge_power_kw=7.4, charge_session_kwh=9.0, battery_pct=40, charge_limit_pct=80, consumption=16.5),
    )
    assert m["minutes"] == 75 and m["since"] == (NOW - timedelta(minutes=75)).astimezone().strftime("%H:%M")
    assert (
        m["gained_kwh"] == pytest.approx(12.0) and m["energy_kwh"] == 9.0
    )  # 20 % of 60 kWh reached the battery but the wallbox counted less: no loss shown
    assert m["loss_pct"] is None and m["in_battery"] is None  # more in the battery than from the wall: not shown, not believed
    m = card(
        vid,
        live(charge_state="charging", charge_power_kw=7.4, charge_session_kwh=14.0, battery_pct=40, charge_limit_pct=80, consumption=16.5),
    )
    assert round(m["loss_pct"]) == 14 and m["range_km"] == pytest.approx(12.0 / 16.5 * 100)  # 14 kWh from the wall, 12 in the battery
    assert m["in_battery"] == pytest.approx(12.0)
    assert m["curve_line"].startswith("M") and m["curve_area"].endswith("Z") and m["peak_kw"] == 7.4 and m["curve_top"] == 7.4


def test_while_no_car_is_plugged_in_the_card_has_the_last_charge(client):
    vid = car(client, battery_kwh=60, price=0.30)
    with db.tx() as conn:
        conn.execute(
            "INSERT INTO charge_sessions(vehicle_id, started, ended, start_pct, end_pct, max_kw, energy_kwh) VALUES(?,?,?,30,80,7.4,31.2)",
            (vid, "2026-11-27T17:42:00+00:00", "2026-11-27T21:22:00+00:00"),
        )
    m = card(vid, live(charge_state="unplugged", charge_total_kwh=4300))
    assert m["state"] == "unplugged" and m["last"]["minutes"] == 220 and m["last"]["start_pct"] == 30 and m["last"]["end_pct"] == 80


# ------------------------------------------------------------------ the curve


def test_the_curve_is_two_paths_and_long_series_are_thinned():
    area, line = wallbox.curve([0, 5, 10, 5], 10)
    assert line.startswith("M0.0 62.0 L100.0") and area == f"{line} L300 66 L0 66Z"
    assert wallbox.curve([1], 10) == ("", "") and wallbox.curve([1, 2], 0) == ("", "")
    thin = wallbox._thin(list(range(1000)), 90)
    assert len(thin) == 90 and thin[0] == 0 and thin[-1] == 999
    assert wallbox._thin([1, 2, 3], 90) == [1, 2, 3]


def test_the_entities_that_feed_the_card_are_listed(client):
    from tests.test_habridge import install, state, world  # noqa: F401

    vid, pk = install(client)
    with db.tx() as conn:
        conn.executemany(
            "INSERT INTO ha_bindings(addon_pk, slot, entity, options) VALUES(?,?,?,'{}')",
            [
                (pk, "charge_state", "sensor.wallbox_status"),
                (pk, "charge_session_kwh", "sensor.wallbox_energy_session"),
                (pk, "battery_pct", "sensor.car_battery"),
                (pk, "range_km", "sensor.car_range"),
            ],
        )
        conn.execute("UPDATE vehicle_addons SET active = 1 WHERE id = ?", (pk,))
        from carassistant import i18n

        listed = wallbox.sources(conn, vid, i18n.translator("en"))
    assert [(r["label"], r["entity"], r["domain"]) for r in listed] == [
        ("Battery charge", "sensor.car_battery", "sensor"),
        ("State of the wallbox", "sensor.wallbox_status", "sensor"),
        ("Energy of this charge", "sensor.wallbox_energy_session", "sensor"),
    ]  # the range belongs to another card
    assert connectors.CHARGE_STATES  # (the vocabulary the card knows)
