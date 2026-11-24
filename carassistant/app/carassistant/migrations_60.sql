-- the files of a package that the app handed out for a car: when, which version, and the settings it was built from
CREATE TABLE IF NOT EXISTS addon_deliveries (
    addon_pk INTEGER NOT NULL,
    name TEXT NOT NULL,
    version TEXT NOT NULL DEFAULT '',
    delivered_at TEXT NOT NULL,
    settings_hash TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (addon_pk, name)
);
