"""A charge at a wallbox that counts its energy is booked with the exact kWh - and with the home price its cost - instead of an unfinished entry that waits for a
bill (carassistant/charge_detect.py). The power of the charge is kept as a curve, a point a minute."""

from datetime import UTC, datetime, timedelta

import pytest
from tests.test_web import create_vehicle

from carassistant import charge_detect, connectors, db


def _car(client, battery_kwh=60.0, price=None, fuel_type="electric"):
    vid = create_vehicle(client, "Wallbox Car")
    with db.tx() as conn:
        conn.execute("UPDATE vehicles SET fuel_type = ?, battery_kwh = ? WHERE id = ?", (fuel_type, battery_kwh, vid))
        if price is not None:
            charge_detect.set_home_price(conn, vid, price)
    return vid


def _old(conn, vid, minutes=45):
    """The charge began a while ago (a charge of a few seconds is a plug contact)."""
    conn.execute(
        "UPDATE charge_sessions SET started = ? WHERE vehicle_id = ? AND ended IS NULL",
        ((datetime.now(UTC) - timedelta(minutes=minutes)).isoformat(timespec="seconds"), vid),
    )


def _entry(conn, vid):
    return conn.execute("SELECT * FROM fuel WHERE vehicle_id = ?", (vid,)).fetchall()


def test_the_energy_the_wallbox_counted_is_booked_with_the_cost_at_the_home_price(client):
    vid = _car(client, price=0.30)
    with db.tx() as conn:
        connectors._store(conn, vid, "charging", "yes")
        connectors._store(conn, vid, "charge_power_kw", "7.4")
        connectors._store(conn, vid, "charge_session_kwh", "3.7")
        connectors._store(conn, vid, "charge_session_kwh", "7.4")
        _old(conn, vid)
        connectors._store(
            conn, vid, "charge_session_kwh", "0"
        )  # some wallboxes count from 0 again when the car is unplugged: the most it said counts
        connectors._store(conn, vid, "charging", "no")
        (row,) = _entry(conn, vid)
        assert (row["amount"], row["price_total"], row["price_per_unit"], row["auto_kind"], row["auto_open"]) == (
            7.4,
            2.22,
            0.3,
            "charge",
            0,
        )
        done = charge_detect.sessions(conn, vid)[0]
        assert done["kwh"] == 7.4 and done["kwh_billed"] and done["cost"] == 2.22 and not done["cost_estimated"]  # a fact, not an estimate
        assert conn.execute("SELECT energy_kwh FROM charge_sessions WHERE vehicle_id = ?", (vid,)).fetchone()[0] == 7.4


def test_without_a_home_price_the_energy_is_booked_and_only_the_price_is_left_to_add(client):
    vid = _car(client)
    with db.tx() as conn:
        connectors._store(conn, vid, "charging", "yes")
        connectors._store(conn, vid, "charge_session_kwh", "11.5")
        _old(conn, vid)
        connectors._store(conn, vid, "charging", "no")
        (row,) = _entry(conn, vid)
        assert row["amount"] == 11.5 and row["price_total"] is None and row["auto_open"] == 1  # the entry still asks for the bill


def test_the_difference_of_the_counter_is_the_energy_when_the_wallbox_counts_only_over_its_life(client):
    vid = _car(client, price=0.25)
    with db.tx() as conn:
        connectors._store(conn, vid, "charge_total_kwh", "4210.4")
        connectors._store(conn, vid, "charging", "yes")
        connectors._store(conn, vid, "charge_total_kwh", "4214.1")
        connectors._store(conn, vid, "charge_total_kwh", "4217.8")
        _old(conn, vid)
        connectors._store(conn, vid, "charging", "no")
        (row,) = _entry(conn, vid)
        assert row["amount"] == 7.4 and row["price_total"] == 1.85


def test_a_charge_needs_no_battery_data_when_the_wallbox_knows_the_energy(client):
    vid = _car(client, price=0.30)
    with db.tx() as conn:
        connectors._store(conn, vid, "charging", "yes")
        connectors._store(conn, vid, "charge_session_kwh", "6")
        _old(conn, vid)
        connectors._store(conn, vid, "charging", "no")
        (row,) = _entry(conn, vid)
        assert row["amount"] == 6 and row["auto_rise"] is None and row["full_tank"] == 0


def test_a_plug_contact_is_still_not_a_session_and_nothing_counted_is_nothing(client):
    vid = _car(client)
    with db.tx() as conn:
        connectors._store(conn, vid, "charging", "yes")
        connectors._store(conn, vid, "charge_session_kwh", "0.05")  # less than the wallbox needs to say for it to count
        _old(conn, vid)
        connectors._store(conn, vid, "charging", "no")
        assert _entry(conn, vid) == [] and conn.execute("SELECT COUNT(*) FROM charge_sessions").fetchone()[0] == 0


def test_a_car_without_a_wallbox_counter_is_booked_as_before(client):
    vid = _car(client)
    with db.tx() as conn:
        connectors._store(conn, vid, "battery_pct", "30")
        connectors._store(conn, vid, "charging", "yes")
        connectors._store(conn, vid, "battery_pct", "80")
        _old(conn, vid)
        connectors._store(conn, vid, "charging", "no")
        (row,) = _entry(conn, vid)
        assert row["amount"] is None and row["auto_open"] == 1 and row["auto_rise"] == 50  # an estimate only: the bill completes it


def test_the_loss_between_the_wallbox_and_the_battery_is_worked_out_from_the_exact_energy(client):
    vid = _car(client, battery_kwh=60)
    with db.tx() as conn:
        connectors._store(conn, vid, "battery_pct", "20")
        connectors._store(conn, vid, "charging", "yes")
        connectors._store(conn, vid, "charge_session_kwh", "34")
        connectors._store(
            conn, vid, "battery_pct", "80"
        )  # 36 kWh reached the battery, the wallbox says 34: that is no loss (an estimate off by a little)
        _old(conn, vid)
        connectors._store(conn, vid, "charging", "no")
        assert charge_detect.sessions(conn, vid)[0]["loss_pct"] is None
    vid = _car(client, battery_kwh=60)
    with db.tx() as conn:
        connectors._store(conn, vid, "battery_pct", "20")
        connectors._store(conn, vid, "charging", "yes")
        connectors._store(conn, vid, "charge_session_kwh", "40")
        connectors._store(conn, vid, "battery_pct", "80")
        _old(conn, vid)
        connectors._store(conn, vid, "charging", "no")
        done = charge_detect.sessions(conn, vid)[0]
        assert done["gained_kwh"] == 36 and round(done["loss_pct"]) == 10  # 40 kWh from the wall, 36 in the battery


def test_the_power_curve_has_a_point_about_every_minute_and_goes_with_its_charge(client, monkeypatch):
    vid = _car(client)
    clock = {"now": datetime.now(UTC)}
    monkeypatch.setattr(charge_detect, "_now", lambda: clock["now"])
    with db.tx() as conn:
        connectors._store(conn, vid, "charging", "yes")
        for second, kw in ((0, 1.2), (10, 3.0), (30, 5.5), (60, 7.2), (75, 7.3), (125, 7.4)):
            clock["now"] = clock["now"] + timedelta(seconds=second - (clock.get("last") or 0))
            clock["last"] = second
            connectors._store(conn, vid, "charge_power_kw", str(kw))
        points = [(r["kw"]) for r in conn.execute("SELECT kw FROM charge_samples ORDER BY at")]
        assert points == [1.2, 7.2, 7.4]  # one every 50 seconds at the most, however often the power is reported
        session = conn.execute("SELECT id FROM charge_sessions").fetchone()["id"]
        conn.execute("DELETE FROM charge_sessions WHERE id = ?", (session,))
        assert conn.execute("SELECT COUNT(*) FROM charge_samples").fetchone()[0] == 0  # the curve goes with its charge


def test_the_curves_of_charges_that_are_two_weeks_old_are_dropped(client, monkeypatch):
    vid = _car(client)
    with db.tx() as conn:
        old = conn.execute(
            "INSERT INTO charge_sessions(vehicle_id, started, ended, energy_kwh) VALUES(?, '2026-01-01T08:00:00+00:00', '2026-01-01T09:00:00+00:00', 5)",
            (vid,),
        ).lastrowid
        conn.execute("INSERT INTO charge_samples(session_id, at, kw) VALUES(?, '2026-01-01T08:30:00+00:00', 7)", (old,))
        connectors._store(conn, vid, "charging", "yes")
        connectors._store(conn, vid, "charge_session_kwh", "4")
        _old(conn, vid)
        connectors._store(conn, vid, "charging", "no")
        assert conn.execute("SELECT COUNT(*) FROM charge_samples WHERE session_id = ?", (old,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM charge_sessions WHERE id = ?", (old,)).fetchone()[0] == 1  # the charge itself stays


@pytest.mark.parametrize("fuel_type", ["petrol", "diesel"])
def test_a_car_with_a_tank_notices_no_charge(client, fuel_type):
    vid = _car(client, fuel_type=fuel_type)
    with db.tx() as conn:
        connectors._store(conn, vid, "charging", "yes")
        connectors._store(conn, vid, "charge_session_kwh", "6")
        connectors._store(conn, vid, "charging", "no")
        assert _entry(conn, vid) == []


def test_the_curve_goes_on_while_the_power_stays_the_same_because_the_energy_keeps_coming(client, monkeypatch):
    """A wallbox reports 7.4 kW once and then nothing, but the energy of the charge grows: that is the pulse of the curve."""
    vid = _car(client)
    clock = {"now": datetime.now(UTC)}
    monkeypatch.setattr(charge_detect, "_now", lambda: clock["now"])
    with db.tx() as conn:
        connectors._store(conn, vid, "charge_power_kw", "7.4")  # the power arrives before the word "charging"
        connectors._store(conn, vid, "charging", "yes")
        for n in range(1, 5):
            clock["now"] += timedelta(seconds=60)
            connectors._store(conn, vid, "charge_session_kwh", str(round(n * 0.123, 3)))
        points = [r["kw"] for r in conn.execute("SELECT kw FROM charge_samples ORDER BY at")]
        assert points == [7.4] * 5  # the first one at the start, then one a minute
        clock["now"] += timedelta(seconds=60)
        connectors._store(conn, vid, "charge_power_kw", "0")
        clock["now"] += timedelta(seconds=60)
        connectors._store(conn, vid, "charge_session_kwh", "0.7")
        assert [r["kw"] for r in conn.execute("SELECT kw FROM charge_samples ORDER BY at")][-1] == 0.0
