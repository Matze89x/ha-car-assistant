-- when a log line was kept (lines older than the retention set under Settings -> System are removed)
ALTER TABLE vehicle_logs ADD COLUMN added TEXT;
