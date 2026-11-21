-- Manual: page images (ready-made package), page offset (printed page + offset = page of the file) and chapter depth.
ALTER TABLE manuals ADD COLUMN page_offset INTEGER NOT NULL DEFAULT 0;
ALTER TABLE manuals ADD COLUMN images INTEGER NOT NULL DEFAULT 0;
ALTER TABLE manual_chapters ADD COLUMN depth INTEGER NOT NULL DEFAULT 0;
