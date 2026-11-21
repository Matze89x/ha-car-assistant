-- Integrations and plugins belong to exactly one vehicle. Only the manifest is stored; no uploaded code is ever executed.
CREATE TABLE vehicle_addons (
    id          INTEGER PRIMARY KEY,
    vehicle_id  INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,                 -- plugin | integration
    addon_id    TEXT NOT NULL,                 -- id from the manifest
    manifest    TEXT NOT NULL,                 -- cleaned plugin.json
    status      TEXT NOT NULL DEFAULT 'uploaded',  -- uploaded | configured
    settings    TEXT NOT NULL DEFAULT '{}',
    token_id    INTEGER REFERENCES api_tokens(id) ON DELETE SET NULL,
    created_at  TEXT NOT NULL,
    UNIQUE (vehicle_id, addon_id)
);
