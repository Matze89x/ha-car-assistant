-- Units and currency per vehicle (empty = follow the default of Settings -> Region).
ALTER TABLE vehicles ADD COLUMN units TEXT;      -- metric | us | uk
ALTER TABLE vehicles ADD COLUMN currency TEXT;   -- ISO code, e.g. EUR
