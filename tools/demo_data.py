"""Made-up demo data for the sources repository (used by make_demo_vehicles.py; the app itself has no demo code any more).

A demo vehicle: a made-up car with two years of believable data, so every page can be tried with real-looking content.

Everything is invented and neutral (no brand, no real place of a person). Dates are relative to today, so the demo always looks current.
"""

from __future__ import annotations

import json
import random
import sqlite3
from datetime import UTC, date, datetime, timedelta

from carassistant import slugs, summary

DEMO_NAME = "Demo Car"
DEMO_CONNECTOR = "Demo connector"
START_KM = 61_200
KM_PER_DAY = 34.0
DAYS = 730

# (place, lat, lon) - generic, spread around one neutral region
PLACES = (
    ("Home", 52.5200, 13.4050),
    ("Office", 52.5008, 13.4380),
    ("Supermarket", 52.5120, 13.3890),
    ("Lake", 52.4350, 13.6430),
    ("Airport", 52.3667, 13.5033),
    ("Garden centre", 52.5560, 13.3250),
    ("Sports club", 52.4870, 13.3540),
)
CHARGERS = ("Home wallbox", "City charger", "Motorway fast charger", "Supermarket charger")
STATIONS = ("Example Fuel", "City Station", "Motorway Services", "Corner Pump")
EV_SKIP = ("Engine oil & filter", "Spark plugs", "Gearbox oil", "Timing belt")  # service items an electric car does not have


DEMO_TASKS = (
    ("Engine oil & filter", 15000, 12, "oil,öl,ölwechsel"),
    ("Brake fluid", None, 24, "brake fluid,bremsflüssigkeit"),
    ("Coolant", None, 60, "coolant,kühlmittel,kühlflüssigkeit"),
    ("Cabin air filter", 20000, 12, "cabin filter,innenraumfilter,pollenfilter"),
    ("Air filter", 30000, 24, "air filter,luftfilter"),
    ("Spark plugs", 60000, 48, "spark plug,zündkerze"),
    ("Gearbox oil", 60000, 60, "gearbox oil,getriebeöl,dsg"),
    ("Timing belt", 120000, 60, "timing belt,zahnriemen"),
    ("Battery check", None, 24, "battery,batterie"),
    ("Brake pads / discs", 40000, None, "brake pad,bremsbelag,bremsbeläge,bremsscheibe"),
)


def _d(days_ago: int) -> date:
    return summary.today() - timedelta(days=days_ago)


def _km_at(day: date) -> int:
    return round(START_KM + KM_PER_DAY * (DAYS - (summary.today() - day).days))


def _store(conn: sqlite3.Connection, vid: int, key: str, value: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO live(vehicle_id, key, value, updated) VALUES(?,?,?,?)",
        (vid, key, value, (datetime.now(UTC) - timedelta(minutes=12)).isoformat(timespec="seconds")),
    )


def create(conn: sqlite3.Connection, electric: bool = False) -> int:
    """Insert the demo vehicle with data in every module and return its id."""
    rnd = random.Random(7)  # noqa: S311 (fixed seed: the demo looks the same every time, not a secret)
    today = summary.today()
    km_now = _km_at(today)

    vid = conn.execute(
        "INSERT INTO vehicles (name, make, model, variant, year, plate, vin, fuel_type, tank_l, color, notes, build_date, model_type, "
        "engine, power_kw, displacement_ccm, drivetrain, transmission, body_type, engine_code, gearbox_code, battery, paint_code, "
        "hsn, tsn, key_numbers) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            DEMO_NAME,
            "Example",
            "Tourer",
            "2.0 Diesel Comfort",
            today.year - 7,
            "AB-CD 123",
            "EXAMPL3DEMO000001",
            "diesel",
            55.0,
            "Grey metallic",
            "Demo vehicle with made-up data. Delete it any time.\nWiper blades 650/475 mm, H7 low beam, cabin filter F-1234",
            f"{today.year - 7}-03-14",
            "T5",
            "2.0 TDI",
            110,
            1968,
            "fwd",
            "dct",
            "wagon",
            "EX20D",
            "DCT7",
            "AGM 70 Ah, fitted 2 years ago",
            "GM7",
            "0000",
            "ABC",
            "2 keys, 1 spare in the drawer",
        ),
    ).lastrowid
    name = "Demo EV" if electric else DEMO_NAME
    if electric:
        conn.execute(
            "UPDATE vehicles SET name = ?, model = ?, variant = ?, plate = ?, vin = ?, fuel_type = 'electric', tank_l = NULL, battery_kwh = 64, "
            "engine = ?, power_kw = 150, displacement_ccm = NULL, engine_code = NULL, gearbox_code = NULL, drivetrain = 'rwd', "
            "transmission = 'automatic', body_type = 'hatchback', battery = ? WHERE id = ?",
            (
                name,
                "Voltra",
                "64 kWh Long Range",
                "EF-GH 456",
                "EXAMPL3DEMO000002",
                "Electric motor 150 kW",
                "AGM 60 Ah (06/2022)",
                vid,
            ),
        )
    conn.execute("UPDATE vehicles SET slug = ? WHERE id = ?", (slugs.unique(conn, name, vid), vid))

    # odometer history: roughly monthly readings
    for days_ago in range(DAYS, 0, -30):
        summary.add_odometer(conn, vid, _km_at(_d(days_ago)), _d(days_ago).isoformat())
    summary.add_odometer(conn, vid, km_now)

    # fuel: a full tank about every 800 km
    day = _d(DAYS - 3)
    while day < today - timedelta(days=2):
        litres = round(rnd.uniform(24, 46), 1) if electric else round(rnd.uniform(38, 50), 1)
        price = round(rnd.uniform(0.28, 0.55), 3) if electric else round(rnd.uniform(1.52, 1.78), 3)
        conn.execute(
            "INSERT INTO fuel(vehicle_id, date, odometer_km, amount, price_per_unit, price_total, full_tank, station) VALUES(?,?,?,?,?,?,?,?)",
            (vid, day.isoformat(), _km_at(day), litres, price, round(litres * price, 2), 1, rnd.choice(CHARGERS if electric else STATIONS)),
        )
        day += timedelta(days=round(800 / KM_PER_DAY * rnd.uniform(0.85, 1.15)))

    # service history
    for days_ago, title, shop, cost, notes in (
        (610, "Oil & filter service", "Example Garage", 189.90, "Oil 5W-30 and oil filter"),
        (420, "Inspection", "Example Garage", 349.00, "Brake system checked"),
        (300, "Brake pads front", "City Workshop", 276.50, "Pads and discs"),
        (200, "Tyre change", "City Workshop", 49.90, "Winter to summer"),
        (95, "Oil & filter service", "Example Garage", 205.40, "Cabin filter included"),
        (30, "Battery check", "City Workshop", 0.0, "All values fine"),
        (700, "First inspection", "Example Garage", 289.00, "Oil, filters, brake check"),
        (520, "Wiper blades", "Parts shop", 24.90, "Front pair"),
        (360, "Air conditioning service", "City Workshop", 95.00, "Refilled and cleaned"),
        (150, "Headlight bulb", "Example Garage", 38.50, "Left low beam"),
        (60, "Tyre pressure check", "City Workshop", 0.0, "Adjusted to the recommended values"),
    ):
        d = _d(days_ago)
        conn.execute(
            "INSERT INTO service(vehicle_id, date, odometer_km, title, workshop, cost, notes) VALUES(?,?,?,?,?,?,?)",
            (vid, d.isoformat(), _km_at(d), title, shop, cost or None, notes),
        )

    # appointments: one overdue, one soon, one later, one done
    for kind, title, due, month_only, done in (
        ("other", "Tyre swap", today - timedelta(days=5), 0, 0),
        ("inspection", "Roadworthiness test", today + timedelta(days=19), 1, 0),
        ("service", "Annual service", today + timedelta(days=75), 0, 0),
        ("insurance", "Insurance renewal", today + timedelta(days=130), 0, 0),
        ("other", "Car wash and interior cleaning", today + timedelta(days=8), 0, 0),
        ("service", "Winter tyre swap", today + timedelta(days=190), 1, 0),
        ("insurance", "Insurance renewal (last year)", today - timedelta(days=235), 0, 1),
        ("inspection", "Emissions test", today - timedelta(days=200), 1, 1),
    ):
        conn.execute(
            "INSERT INTO appointments(vehicle_id, kind, title, due_date, month_only, done) VALUES(?,?,?,?,?,?)",
            (vid, kind, title, due.isoformat(), month_only, done),
        )

    # recurring tasks with different states (ok / soon / overdue)
    for title, km, months, keywords in DEMO_TASKS:
        conn.execute(
            "INSERT INTO tasks(vehicle_id, title, interval_km, interval_months, keywords) VALUES(?,?,?,?,?)",
            (vid, title, km, months, keywords),
        )
    states = {
        "Engine oil & filter": (95, 8),  # ok
        "Brake fluid": (780, 780),  # overdue by date
        "Coolant": (1800, 1800),  # due within a month (60 months)
        "Cabin air filter": (95, 95),
        "Air filter": (705, 705),  # due soon (24 months)
        "Spark plugs": None,
        "Gearbox oil": (900, 900),
        "Timing belt": None,
        "Battery check": (30, 30),
        "Brake pads / discs": (300, 300),
    }
    for title, state in states.items():
        if state is None or (electric and title in EV_SKIP):
            conn.execute("UPDATE tasks SET muted = 1 WHERE vehicle_id = ? AND title = ?", (vid, title))  # not applicable to this drivetrain
            continue
        d = _d(state[0])
        conn.execute(
            "UPDATE tasks SET last_date = ?, last_km = ? WHERE vehicle_id = ? AND title = ?",
            (d.isoformat(), _km_at(d), vid, title),
        )

    # modifications and parts
    for days_ago, title, cost, notes in (
        (500, "Roof rails", 240.0, "Fitted by me"),
        (260, "Dash camera", 119.0, "Hard-wired, SD card 64 GB"),
        (400, "Floor mats", 79.0, "All-weather, set of four"),
        (140, "Phone holder", 29.9, "Vent clip"),
        (45, "Tow bar", 690.0, "Detachable, fitted by the garage"),
    ):
        d = _d(days_ago)
        conn.execute(
            "INSERT INTO mods(vehicle_id, date, odometer_km, title, cost, notes) VALUES(?,?,?,?,?,?)",
            (vid, d.isoformat(), _km_at(d), title, cost, notes),
        )
    for days_ago, name, pn, maker, shop, qty, cost, installed in (
        (300, "Brake pads front", "BP-1042", "Example Parts", "Parts shop", 1, 74.90, 1),
        (95, "Oil filter", "OF-220", "Example Parts", "Parts shop", 2, 18.40, 1),
        (20, "Wiper blades", "WB-650", "Example Parts", "Online", 1, 24.90, 0),
        (150, "Headlight bulb H7", "HB-H7", "Example Parts", "Parts shop", 2, 16.80, 1),
        (520, "Cabin filter", "CF-1234", "Example Parts", "Online", 1, 21.50, 1),
        (360, "Air conditioning cleaner", "AC-77", "Example Parts", "Online", 1, 12.90, 1),
        (60, "Key fob battery", "KB-2032", "Example Parts", "Pharmacy", 2, 5.40, 1),
        (10, "Valve caps (set)", "VC-04", "Example Parts", "Online", 1, 6.20, 0),
    ):
        d = _d(days_ago)
        conn.execute(
            "INSERT INTO parts(vehicle_id, date, name, part_number, manufacturer, shop, quantity, cost, installed, installed_km) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (vid, d.isoformat(), name, pn, maker, shop, qty, cost, installed, _km_at(d) if installed else None),
        )

    # tyre sets
    summer, winter = _d(200), _d(200 + 180)
    conn.execute(
        "INSERT INTO tires(vehicle_id, name, season, size, dot, storage, mounted, mounted_date, mounted_km) VALUES(?,?,?,?,?,?,?,?,?)",
        (vid, "Summer set", "summer", "225/45 R17", "2423", "Garage shelf", 1, summer.isoformat(), _km_at(summer)),
    )
    conn.execute(
        "INSERT INTO tires(vehicle_id, name, season, size, dot, storage, mounted, mounted_date, mounted_km) VALUES(?,?,?,?,?,?,?,?,?)",
        (vid, "Winter set", "winter", "205/55 R16", "3921", "Cellar", 0, winter.isoformat(), _km_at(winter)),
    )
    conn.execute(
        "INSERT INTO tires(vehicle_id, name, season, size, dot, storage, mounted) VALUES(?,?,?,?,?,?,?)",
        (vid, "All-season set", "allseason", "225/45 R17", "1224", "Garage", 0),
    )  # every season that shows pressures has a set with a name

    # counters (tax year and a business-trip counter)
    year_start = date(today.year, 1, 1)
    conn.execute(
        "INSERT INTO counters(vehicle_id, name, kind, start_date, start_km) VALUES(?,?,?,?,?)",
        (vid, f"Tax {today.year}", "tax", year_start.isoformat(), _km_at(year_start)),
    )
    conn.execute(
        "INSERT INTO counters(vehicle_id, name, kind, start_date, start_km, end_date, end_km) VALUES(?,?,?,?,?,?,?)",
        (vid, "Summer holiday", "private", _d(150).isoformat(), _km_at(_d(150)), _d(136).isoformat(), _km_at(_d(136))),
    )

    # trips: the last weeks, three of them with a recorded track
    categories = ("commute", "commute", "private", "business", "private")
    day = today
    for n in range(14):
        a, b = rnd.sample(PLACES, 2)
        start_km = _km_at(day) - 40
        dist = round(rnd.uniform(6, 48), 1)
        category = categories[n % len(categories)]
        trip_id = conn.execute(
            "INSERT INTO trips(vehicle_id, date, start_time, end_time, start_km, end_km, start_place, end_place, category, purpose, "
            "source, distance_km) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                vid,
                day.isoformat(),
                "07:45",
                "08:30",
                start_km,
                round(start_km + dist),
                a[0],
                b[0],
                category,
                "Client visit" if category == "business" else None,
                "gps" if n < 3 else "manual",
                dist,
            ),
        ).lastrowid
        if n < 3:
            for seq in range(12):
                f = seq / 11
                conn.execute(
                    "INSERT INTO trip_points(trip_id, seq, lat, lon, ts) VALUES(?,?,?,?,?)",
                    (trip_id, seq, a[1] + (b[1] - a[1]) * f + 0.004 * (f * (1 - f)), a[2] + (b[2] - a[2]) * f, None),
                )
        day -= timedelta(days=rnd.choice((1, 2, 3, 4)))

    # live values, as a connector would deliver them. The two demo cars are set up so that every kind of message has something to say
    # (low tank / battery, a tyre too soft, a door or the boot open, a car warning, a service coming up, a trip that just ended).
    _store(conn, vid, "fuel_level", "16" if electric else "12")
    _store(conn, vid, "range_km", "103" if electric else "85")
    _store(conn, vid, "fuel_amount", "10.2" if electric else "6.6")
    if electric:
        _store(conn, vid, "battery_pct", "16")
        _store(conn, vid, "plugged", "no")
        _store(conn, vid, "charging", "no")
        _store(conn, vid, "charge_power_kw", "0")
        _store(conn, vid, "charge_limit_pct", "80")
        _store(conn, vid, "target_temp_c", "21")
        _store(conn, vid, "climate_on", "no")
    else:
        _store(conn, vid, "adblue_level_pct", "38")
        _store(conn, vid, "adblue_range_km", "2400")
        _store(conn, vid, "oil_level_pct", "70")
        _store(conn, vid, "oil_temp_c", "21")
        _store(conn, vid, "coolant_temp_c", "22")
        _store(conn, vid, "oil_warning", "no")
    _store(conn, vid, "position", "52.512000,13.389000")
    _store(conn, vid, "heading_deg", "135")
    _store(conn, vid, "speed_kmh", "0")
    _store(conn, vid, "speed_limit_kmh", "50")
    _store(conn, vid, "outside_temp_c", "7.5")
    _store(conn, vid, "cabin_temp_c", "14")
    _store(conn, vid, "battery_12v_v", "12.6")
    _store(conn, vid, "consumption", "16.8" if electric else "5.4")
    _store(conn, vid, "parking_brake", "yes")
    _store(conn, vid, "service_due_days", "25" if electric else "12")
    if not electric:
        _store(conn, vid, "service_due_km", "850")
    _store(conn, vid, "locked", "locked")
    _store(conn, vid, "ignition", "off")
    _store(conn, vid, "lights", json.dumps({"low_beam": False, "high_beam": False, "hazard": False, "parking": False}))
    _store(
        conn,
        vid,
        "doors",
        json.dumps(
            {
                "front_left": False,
                "front_right": False,
                "rear_left": False,
                "rear_right": electric,
                "trunk": not electric,
            }
        ),
    )
    _store(conn, vid, "windows", json.dumps({"front_left": False, "front_right": False, "rear_left": False, "rear_right": not electric}))
    _store(conn, vid, "warnings", json.dumps({"software": "Software update available"} if electric else {"washer": "Washer fluid low"}))
    # one tyre clearly too soft (more than 0.3 bar under the recommendation): the tyre message fires
    _store(
        conn,
        vid,
        "tyre_pressure_bar",
        json.dumps({"fl": 2.4, "fr": 2.0, "rl": 2.6, "rr": 2.5} if electric else {"fl": 2.4, "fr": 2.4, "rl": 2.1, "rr": 2.5}),
    )
    # the rest of the vehicle data, so no field of the demo is empty
    conn.execute(
        "UPDATE vehicles SET first_reg = ?, seats = 5, gross_weight_kg = ?, oil_spec = ?, oil_l = ? WHERE id = ?",
        (
            "2022-06-15" if electric else "2021-03-10",
            2150 if electric else 1950,
            None if electric else "5W-30 (ACEA C3)",
            None if electric else 4.3,
            vid,
        ),
    )
    for season, front, rear in (("summer", 2.4, 2.6), ("winter", 2.6, 2.8), ("allseason", 2.5, 2.7)):
        conn.execute("INSERT INTO tire_pressure(vehicle_id, season, front_bar, rear_bar) VALUES (?,?,?,?)", (vid, season, front, rear))
    conn.execute(
        "UPDATE tire_pressure SET load_front_bar = ROUND(front_bar + 0.3, 1), load_rear_bar = ROUND(rear_bar + 0.4, 1) WHERE vehicle_id = ?",
        (vid,),
    )
    conn.execute(
        "UPDATE tires SET rear_size = '255/40 R18 99Y', rear_name = 'Rear axle: wider tyre' WHERE vehicle_id = ? AND season = 'summer'",
        (vid,),
    )
    _equipment(conn, vid, electric)
    _icon(vid)
    return vid


def _icon(vid: int) -> None:
    """The demo car's own icon (home screen, More): its picture on a dark tile. Only demo cars get one."""
    import io
    from pathlib import Path

    from PIL import Image

    from carassistant import appicon

    car = Image.open(
        Path(__file__).resolve().parent.parent / "carassistant" / "app" / "carassistant" / "static" / "car-default.webp"
    ).convert("RGBA")
    side = 1024  # the largest an icon can be (the app keeps at most 1024 px); the picture goes in at its own pixel size, never scaled up
    tile = Image.new("RGBA", (side, side), (13, 16, 22, 255))
    if car.width > side:
        car = car.resize((side, round(car.height * side / car.width)), Image.LANCZOS)
    tile.alpha_composite(car, ((side - car.width) // 2, (side - car.height) // 2))
    buf = io.BytesIO()
    tile.convert("RGB").save(buf, "PNG")
    appicon.save_custom(buf.getvalue(), vid)


# (area key, [(title, status, code, note)]): made-up equipment in every area and with every status - standard, special, retrofitted, not fitted
EQUIPMENT = {
    "comfort": [
        ("Automatic climate control", "series", "9AQ", ""),
        ("Keyless entry", "option", "GZ2", "Also starts the engine without a key"),
        ("Auxiliary heater", "retrofit", "", "Fitted by a workshop in 2024"),
        ("Electric tailgate", "missing", "4E7", ""),
        ("Cruise control", "series", "8T1", ""),
    ],
    "seats": [
        ("Cloth seats", "series", "N4X", ""),
        ("Heated front seats", "option", "4A3", ""),
        ("Seat covers", "retrofit", "", "Waterproof, for the dog"),
        ("Electric seat adjustment", "missing", "3L4", ""),
    ],
    "controls": [
        ("Multifunction steering wheel", "series", "2ZB", ""),
        ("Paddle shifters", "option", "GH1", ""),
        ("Gear knob in leather", "retrofit", "", ""),
        ("Heated steering wheel", "missing", "1ZW", ""),
    ],
    "lights": [
        ("Halogen headlights", "series", "8G1", ""),
        ("LED rear lights", "option", "8SL", ""),
        ("Ambient lighting", "retrofit", "QQ2", "Added with a kit, 3 colours"),
        ("Matrix headlights", "missing", "PXC", ""),
    ],
    "packages": [
        ("Comfort line", "series", "WCL", ""),
        ("Sport package", "option", "WSP", ""),
        ("Winter package", "retrofit", "", "Heated mirrors and nozzles, fitted later"),
        ("Black edition", "missing", "WBE", ""),
    ],
    "interior": [
        ("Floor mats", "series", "0TD", ""),
        ("Piano-black inlays", "option", "5TG", ""),
        ("Boot liner", "retrofit", "", "Custom fit"),
        ("Aluminium inlays", "missing", "5MH", ""),
    ],
    "wheels": [
        ("16-inch steel wheels", "series", "C16", ""),
        ("17-inch alloy wheels", "option", "CJ2", "Second set on steel wheels for winter"),
        ("Wheel spacers", "retrofit", "", ""),
        ("Space-saver spare wheel", "missing", "1G9", ""),
    ],
    "tech": [
        ("Electronic stability control", "series", "1AS", ""),
        ("Start-stop system", "option", "7L6", ""),
        ("Dashcam", "retrofit", "", "Wired to the fuse box"),
        ("Rain and light sensor", "missing", "4L6", ""),
    ],
    "exterior": [
        ("Body-coloured bumpers", "series", "", ""),
        ("Roof rails", "option", "3S1", ""),
        ("Tow bar", "retrofit", "1D7", "Detachable, fitted in 2023"),
        ("Panoramic roof", "missing", "3FU", ""),
    ],
    "media": [
        ("Radio with 6 speakers", "series", "7UH", ""),
        ("Navigation", "option", "PNQ", ""),
        ("Smartphone wireless charging", "retrofit", "", ""),
        ("Premium sound system", "missing", "9VS", ""),
    ],
    "assist": [
        ("Front assist (emergency braking)", "series", "6K2", ""),
        ("Lane assist", "option", "7Y1", ""),
        ("Reversing camera", "retrofit", "KA2", "Plug-in kit"),
        ("Blind spot warning", "missing", "7Y4", ""),
    ],
    "roof": [
        ("Tinted rear windows", "series", "4KF", ""),
        ("Acoustic windscreen", "option", "VW1", ""),
        ("Sun blinds", "retrofit", "", "Rear side windows"),
        ("Sunroof", "missing", "3FE", ""),
    ],
}


def _equipment(conn: sqlite3.Connection, vid: int, electric: bool) -> None:
    n = 0
    for key, items in EQUIPMENT.items():
        for title, status, code, note in items:
            if electric and title in ("Auxiliary heater", "Start-stop system"):
                title = "Heat pump" if title == "Auxiliary heater" else "One-pedal driving"
            n += 1
            conn.execute(
                "INSERT INTO equipment(vehicle_id, category, icon, title, code, status, note, sort) VALUES(?,?,?,?,?,?,?,?)",
                (vid, key, "", title, code, status, note, n),
            )
