-- Plugin API: a track of positions (trips are made from it) and free "raw signals" a plugin may park for a car.
CREATE TABLE vehicle_track (
  id         INTEGER PRIMARY KEY,
  vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
  ts         TEXT NOT NULL,
  lat        REAL NOT NULL,
  lon        REAL NOT NULL,
  speed_kmh  REAL
);
CREATE INDEX idx_vehicle_track ON vehicle_track(vehicle_id, ts);
CREATE TABLE vehicle_signals (
  vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
  name       TEXT NOT NULL,
  value      TEXT NOT NULL,
  updated    TEXT NOT NULL,
  PRIMARY KEY (vehicle_id, name)
) WITHOUT ROWID;
