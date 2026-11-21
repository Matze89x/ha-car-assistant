-- Place names looked up for coordinates (only while the map info is switched on): kept, so a spot is asked for once.
CREATE TABLE IF NOT EXISTS place_names (
    key        TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
