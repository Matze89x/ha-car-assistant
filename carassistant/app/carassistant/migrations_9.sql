-- Debug log lines a vehicle (plugin) sends while debugging is switched on for it in the dashboard.
CREATE TABLE vehicle_logs (
    id         INTEGER PRIMARY KEY,
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    ts         TEXT NOT NULL,
    level      TEXT NOT NULL DEFAULT 'info',
    source     TEXT,
    message    TEXT NOT NULL
);
CREATE INDEX idx_vehicle_logs ON vehicle_logs(vehicle_id, id);
