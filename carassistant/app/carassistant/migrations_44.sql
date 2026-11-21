-- Manual: tappable page references on the page image (permille boxes, JSON list of [printed page, x0, y0, x1, y1]).
ALTER TABLE manual_pages ADD COLUMN refs TEXT NOT NULL DEFAULT '';
