-- Photos and videos of a vehicle: a small library per car (newest 5 of each kind are kept), one of them shown on Home.
CREATE TABLE vehicle_media (
    id         INTEGER PRIMARY KEY,
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    kind       TEXT NOT NULL,              -- photo | video
    file       TEXT NOT NULL,              -- name inside <files>/media/<vehicle id>/
    mime       TEXT NOT NULL,
    size       INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_vehicle_media ON vehicle_media(vehicle_id, kind, id);
ALTER TABLE vehicles ADD COLUMN media_id INTEGER;      -- the one shown on Home (photo or video); empty = the default picture
ALTER TABLE vehicles ADD COLUMN media_kind TEXT;       -- how a video's background blends in: adapt (default) | black | alpha
