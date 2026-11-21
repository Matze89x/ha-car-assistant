-- Sources become real: an optional read key, the state of the last check and the package index of each source.
-- Installed packages remember where they came from (a source with installed packages cannot be removed) and can be switched off.
ALTER TABLE sources ADD COLUMN token TEXT;
ALTER TABLE sources ADD COLUMN is_default INTEGER NOT NULL DEFAULT 0;
ALTER TABLE sources ADD COLUMN for_integration INTEGER NOT NULL DEFAULT 1;  -- the source is in the Integrations list
ALTER TABLE sources ADD COLUMN for_plugin INTEGER NOT NULL DEFAULT 1;       -- the source is in the Plugins list
ALTER TABLE sources ADD COLUMN checked_at TEXT;
ALTER TABLE sources ADD COLUMN error TEXT;

CREATE TABLE IF NOT EXISTS source_packages (
    source_id   INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,                  -- plugin | integration
    pkg_id      TEXT NOT NULL,                  -- id = folder name
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    version     TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (source_id, kind, pkg_id)
);

ALTER TABLE vehicle_addons ADD COLUMN source_id INTEGER;
ALTER TABLE vehicle_addons ADD COLUMN source_url TEXT;  -- where a package came from (kept by a vehicle backup; status 'missing' = restored, package not installed)
ALTER TABLE vehicles ADD COLUMN uid TEXT;  -- stable identity of a car, carried by its backup (made when first needed)
ALTER TABLE vehicle_addons ADD COLUMN active INTEGER NOT NULL DEFAULT 1;
CREATE INDEX IF NOT EXISTS idx_vehicle_addons_source ON vehicle_addons(source_id);

-- factory setting: the first source is the project's package repository (ha-car-assistant-sources) (temporary, see docs/sources.md)
INSERT OR IGNORE INTO sources(name, url, is_default) VALUES('Car Assistant', 'https://github.com/Matze89x/ha-car-assistant-sources', 1);
