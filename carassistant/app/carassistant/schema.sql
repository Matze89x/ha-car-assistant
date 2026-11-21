-- Car Assistant schema (migration 1)
CREATE TABLE settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE vehicles (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    make          TEXT,
    model         TEXT,
    variant       TEXT,
    year          INTEGER,
    plate         TEXT,
    vin           TEXT,
    fuel_type     TEXT NOT NULL DEFAULT 'petrol',
    tank_l        REAL,
    color         TEXT,
    notes         TEXT,
    photo         TEXT,
    bind_odometer   TEXT,
    bind_fuel_level TEXT,
    bind_range      TEXT,
    bind_tracker    TEXT,
    archived      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE odometer (
    id         INTEGER PRIMARY KEY,
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    date       TEXT NOT NULL,
    odometer_km INTEGER NOT NULL,
    source     TEXT NOT NULL DEFAULT 'manual'
);
CREATE INDEX idx_odometer_vehicle ON odometer(vehicle_id, odometer_km);

CREATE TABLE service (
    id          INTEGER PRIMARY KEY,
    vehicle_id  INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    date        TEXT NOT NULL,
    odometer_km INTEGER,
    title       TEXT NOT NULL,
    workshop    TEXT,
    cost        REAL,
    notes       TEXT
);
CREATE INDEX idx_service_vehicle ON service(vehicle_id, date);

CREATE TABLE appointments (
    id         INTEGER PRIMARY KEY,
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    kind       TEXT NOT NULL DEFAULT 'inspection',
    title      TEXT NOT NULL,
    due_date   TEXT NOT NULL,
    month_only INTEGER NOT NULL DEFAULT 0,
    notes      TEXT,
    done       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_appointments_vehicle ON appointments(vehicle_id, due_date);

CREATE TABLE mods (
    id          INTEGER PRIMARY KEY,
    vehicle_id  INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    date        TEXT NOT NULL,
    odometer_km INTEGER,
    title       TEXT NOT NULL,
    cost        REAL,
    notes       TEXT
);

CREATE TABLE tires (
    id           INTEGER PRIMARY KEY,
    vehicle_id   INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    season       TEXT NOT NULL DEFAULT 'summer',
    size         TEXT,
    dot          TEXT,
    storage      TEXT,
    mounted      INTEGER NOT NULL DEFAULT 0,
    mounted_date TEXT,
    mounted_km   INTEGER,
    notes        TEXT
);

CREATE TABLE tasks (
    id              INTEGER PRIMARY KEY,
    vehicle_id      INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    interval_km     INTEGER,
    interval_months INTEGER,
    keywords        TEXT,
    last_date       TEXT,
    last_km         INTEGER,
    muted           INTEGER NOT NULL DEFAULT 0,
    notes           TEXT
);

CREATE TABLE fuel (
    id          INTEGER PRIMARY KEY,
    vehicle_id  INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    date        TEXT NOT NULL,
    odometer_km INTEGER,
    amount      REAL,
    price_per_unit REAL,
    price_total REAL,
    full_tank   INTEGER NOT NULL DEFAULT 1,
    station     TEXT,
    notes       TEXT
);
CREATE INDEX idx_fuel_vehicle ON fuel(vehicle_id, odometer_km);

CREATE TABLE trips (
    id          INTEGER PRIMARY KEY,
    vehicle_id  INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    date        TEXT NOT NULL,
    start_time  TEXT,
    end_time    TEXT,
    start_km    INTEGER,
    end_km      INTEGER,
    start_place TEXT,
    end_place   TEXT,
    category    TEXT NOT NULL DEFAULT 'private',
    purpose     TEXT,
    source      TEXT NOT NULL DEFAULT 'manual',
    distance_km REAL
);
CREATE INDEX idx_trips_vehicle ON trips(vehicle_id, date);

CREATE TABLE trip_points (
    trip_id INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    seq     INTEGER NOT NULL,
    lat     REAL NOT NULL,
    lon     REAL NOT NULL,
    ts      TEXT,
    PRIMARY KEY (trip_id, seq)
);

CREATE TABLE documents (
    id         INTEGER PRIMARY KEY,
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    category   TEXT NOT NULL DEFAULT 'other',
    title      TEXT NOT NULL,
    filename   TEXT NOT NULL,
    mime       TEXT,
    size       INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE live (
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    key        TEXT NOT NULL,
    value      TEXT,
    updated    TEXT,
    PRIMARY KEY (vehicle_id, key)
);

CREATE TABLE notify_state (
    key       TEXT PRIMARY KEY,
    last_sent TEXT NOT NULL
);

CREATE TABLE notify_log (
    id      INTEGER PRIMARY KEY,
    ts      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    title   TEXT,
    message TEXT,
    ok      INTEGER NOT NULL DEFAULT 0,
    error   TEXT
);
