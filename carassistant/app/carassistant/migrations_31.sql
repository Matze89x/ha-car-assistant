-- Logs belong to a plugin (addon_id), so they can be limited per plugin and deleted with it.
ALTER TABLE vehicle_logs ADD COLUMN addon_id TEXT;
CREATE INDEX idx_vehicle_logs_addon ON vehicle_logs(vehicle_id, addon_id, id);
