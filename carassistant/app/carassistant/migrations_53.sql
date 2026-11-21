-- Charging sessions of electric / plug-in cars, noticed from the readings of a plugin or entity: when, from which to which battery level, how strong,
-- and the unfinished fuel-log entry (energy and price from the bill) that belongs to it.
CREATE TABLE IF NOT EXISTS charge_sessions (
    id          INTEGER PRIMARY KEY,
    vehicle_id  INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    started     TEXT NOT NULL,
    ended       TEXT,
    start_pct   REAL,
    end_pct     REAL,
    max_kw      REAL,
    odometer_km INTEGER,
    fuel_id     INTEGER
);
CREATE INDEX IF NOT EXISTS idx_charge_vehicle ON charge_sessions(vehicle_id, started);
