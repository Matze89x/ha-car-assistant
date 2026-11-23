-- The connection map: what every plugin sends to / reads from the Plugin API, per signal: the last value with its time and a small history.
CREATE TABLE signal_state (
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    addon_id   TEXT NOT NULL,
    direction  TEXT NOT NULL,          -- 'set' (the plugin sends) | 'get' (the plugin reads)
    name       TEXT NOT NULL,          -- a field of the data, or the name of the interface
    area       TEXT NOT NULL,          -- where it lands in the app (dashboard, location, security ... or int:<integration>)
    hits       INTEGER NOT NULL DEFAULT 0,
    last_ts    TEXT NOT NULL,
    last_value TEXT,                   -- the raw value as JSON (cut), NULL for a read
    PRIMARY KEY (vehicle_id, addon_id, direction, name)
) WITHOUT ROWID;
CREATE INDEX idx_signal_state_area ON signal_state(vehicle_id, area);

CREATE TABLE signal_history (
    id         INTEGER PRIMARY KEY,
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    addon_id   TEXT NOT NULL,
    direction  TEXT NOT NULL,
    name       TEXT NOT NULL,
    ts         TEXT NOT NULL,
    value      TEXT
);
CREATE INDEX idx_signal_history ON signal_history(vehicle_id, addon_id, direction, name, id);
