-- The Home Assistant plugin (docs/home-assistant.md) and the rule "one interface, one plugin":
-- ha_bindings = which entity of Home Assistant feeds which interface of a car (per install of the plugin);
-- field_claims = which interfaces (fields of the Plugin API) a plugin has taken for itself on a car - while it is on, no other source may fill them.
CREATE TABLE IF NOT EXISTS ha_bindings (
  addon_pk INTEGER NOT NULL REFERENCES vehicle_addons(id) ON DELETE CASCADE,
  slot     TEXT NOT NULL,
  entity   TEXT NOT NULL,
  options  TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (addon_pk, slot)
);

CREATE TABLE IF NOT EXISTS field_claims (
  vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
  field      TEXT NOT NULL,
  addon_pk   INTEGER NOT NULL REFERENCES vehicle_addons(id) ON DELETE CASCADE,
  created    TEXT NOT NULL,
  PRIMARY KEY (vehicle_id, field, addon_pk)
);
CREATE INDEX IF NOT EXISTS idx_field_claims_addon ON field_claims(addon_pk);
