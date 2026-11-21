-- Manual ("Handbuch") of a vehicle: imported from a PDF / EPUB / text file, kept as text pages with chapters.
CREATE TABLE manuals (
  vehicle_id  INTEGER PRIMARY KEY REFERENCES vehicles(id) ON DELETE CASCADE,
  title       TEXT NOT NULL DEFAULT '',
  source_name TEXT NOT NULL DEFAULT '',
  pages       INTEGER NOT NULL DEFAULT 0,
  imported_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE manual_chapters (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
  grp        TEXT NOT NULL DEFAULT '',
  title      TEXT NOT NULL,
  page       INTEGER NOT NULL DEFAULT 1,
  sort       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_manual_chapters_vehicle ON manual_chapters(vehicle_id, sort);
CREATE TABLE manual_pages (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
  page       INTEGER NOT NULL,
  text       TEXT NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX idx_manual_pages_vehicle ON manual_pages(vehicle_id, page);
