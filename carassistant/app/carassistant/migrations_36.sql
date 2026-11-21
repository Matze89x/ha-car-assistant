-- Recommended (target) tyre pressures per vehicle and season (bar, front / rear axle)
CREATE TABLE tire_pressure (
  id         INTEGER PRIMARY KEY,
  vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
  season     TEXT NOT NULL,
  front_bar  REAL,
  rear_bar   REAL,
  UNIQUE (vehicle_id, season)
);
