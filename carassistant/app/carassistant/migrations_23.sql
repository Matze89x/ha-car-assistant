-- Page modules: an integration may describe pages (lists of entries with fields). The entries are stored per vehicle and per integration.
CREATE TABLE module_rows (
  id INTEGER PRIMARY KEY,
  vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
  addon_id TEXT NOT NULL,
  page TEXT NOT NULL,
  sort INTEGER NOT NULL DEFAULT 0,
  data TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE INDEX idx_module_rows ON module_rows(vehicle_id, addon_id, page, sort);
