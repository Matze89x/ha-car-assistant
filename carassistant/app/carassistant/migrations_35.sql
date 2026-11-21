-- Which interfaces a plugin really used (observed): the address, the NAMES of the fields it sent, how often, when last. No values.
CREATE TABLE plugin_usage (
  vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
  addon_id   TEXT NOT NULL,
  method     TEXT NOT NULL,
  endpoint   TEXT NOT NULL,
  fields     TEXT NOT NULL DEFAULT '',
  hits       INTEGER NOT NULL DEFAULT 0,
  last_seen  TEXT NOT NULL,
  PRIMARY KEY (vehicle_id, addon_id, method, endpoint)
) WITHOUT ROWID;
