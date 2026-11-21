-- Equipment list of a vehicle ("Ausstattungsmerkmale"): one row per feature, grouped by category.
-- status: series (standard), option (special equipment), retrofit (added later), missing (not fitted)
CREATE TABLE equipment (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
  category   TEXT NOT NULL,
  icon       TEXT NOT NULL DEFAULT '',
  title      TEXT NOT NULL,
  code       TEXT NOT NULL DEFAULT '',
  status     TEXT NOT NULL DEFAULT 'series',
  note       TEXT NOT NULL DEFAULT '',
  sort       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_equipment_vehicle ON equipment(vehicle_id, category);
