-- A refuel or charge that the app or a plugin noticed (the tank / battery level, the Plugin API) used to be marked in the NOTES of the entry
-- ("auto:tank:+78%:2026-11-27T07:48"): the person saw that text in their own notes field. The mark has columns of its own now; the notes stay theirs.
ALTER TABLE fuel ADD COLUMN auto_kind TEXT;                        -- tank | charge | api: how the entry came to be without the person; empty = typed in
ALTER TABLE fuel ADD COLUMN auto_rise REAL;                        -- by how many percentage points the tank / battery rose
ALTER TABLE fuel ADD COLUMN auto_at TEXT;                          -- when it was noticed (local time, YYYY-MM-DDTHH:MM)
ALTER TABLE fuel ADD COLUMN auto_src TEXT;                         -- the plugin that reported it
ALTER TABLE fuel ADD COLUMN auto_open INTEGER NOT NULL DEFAULT 0;  -- 1 = the receipt is still to be added: the page reminds until it is saved (or three trips / three days pass)
