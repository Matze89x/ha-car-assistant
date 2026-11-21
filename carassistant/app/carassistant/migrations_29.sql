-- Plugin API: a list of events a plugin reports (traffic signs read, town borders crossed, anything with a time and a place).
CREATE TABLE vehicle_events (
  id         INTEGER PRIMARY KEY,
  vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
  ts         TEXT NOT NULL,
  type       TEXT NOT NULL,
  text       TEXT NOT NULL DEFAULT '',
  value      REAL,
  lat        REAL,
  lon        REAL
);
CREATE INDEX idx_vehicle_events ON vehicle_events(vehicle_id, type, ts);
