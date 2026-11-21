-- Readable vehicle addresses: /v/<slug> instead of /v/<number>. The slug is filled by the app (see slugs.py).
ALTER TABLE vehicles ADD COLUMN slug TEXT;
CREATE UNIQUE INDEX idx_vehicles_slug ON vehicles(slug);
