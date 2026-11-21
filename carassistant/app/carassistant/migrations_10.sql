-- Energy view and warning levels per vehicle.
ALTER TABLE vehicles ADD COLUMN energy_mode TEXT;      -- fuel | charge (empty = automatic: electric -> charge, otherwise fuel)
ALTER TABLE vehicles ADD COLUMN warn_pct INTEGER;      -- level (%) at or below which the bar turns yellow (empty = 25)
ALTER TABLE vehicles ADD COLUMN crit_pct INTEGER;      -- ... red (empty = 10)
ALTER TABLE vehicles ADD COLUMN warn_range_km INTEGER; -- range (km) at or below which it turns yellow (empty = not used)
ALTER TABLE vehicles ADD COLUMN crit_range_km INTEGER; -- ... red
