-- Debug: who talked to the app (plugins, the car through a service) and how it went. Only written while debug is on for the car; no bodies, no values.
CREATE TABLE vehicle_traffic (
  id         INTEGER PRIMARY KEY,
  vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
  addon_id   TEXT,
  ts         TEXT NOT NULL,
  kind       TEXT NOT NULL,      -- api = a plugin called the Plugin API | car = a request on a route of a plugin service
  method     TEXT NOT NULL,
  path       TEXT NOT NULL,
  status     INTEGER NOT NULL,
  bytes      INTEGER NOT NULL DEFAULT 0,
  ms         INTEGER NOT NULL DEFAULT 0,
  detail     TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_vehicle_traffic ON vehicle_traffic(vehicle_id, id);
