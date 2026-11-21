CREATE TABLE counters (
    id         INTEGER PRIMARY KEY,
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    kind       TEXT NOT NULL DEFAULT 'tax',
    start_date TEXT NOT NULL,
    start_km   INTEGER NOT NULL,
    end_date   TEXT,
    end_km     INTEGER,
    notes      TEXT
);
CREATE INDEX idx_counters_vehicle ON counters(vehicle_id, start_date);

CREATE TABLE parts (
    id           INTEGER PRIMARY KEY,
    vehicle_id   INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    date         TEXT NOT NULL,
    name         TEXT NOT NULL,
    part_number  TEXT,
    manufacturer TEXT,
    shop         TEXT,
    quantity     REAL,
    cost         REAL,
    installed    INTEGER NOT NULL DEFAULT 0,
    installed_km INTEGER,
    notes        TEXT
);
CREATE INDEX idx_parts_vehicle ON parts(vehicle_id, date);
