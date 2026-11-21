-- Indexes for every table that is read or deleted per vehicle (lists, cascades on delete, many cars / many rows).
CREATE INDEX IF NOT EXISTS idx_tasks_vehicle ON tasks(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_tires_vehicle ON tires(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_mods_vehicle ON mods(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_documents_vehicle ON documents(vehicle_id, created_at);
CREATE INDEX IF NOT EXISTS idx_api_tokens_vehicle ON api_tokens(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_vehicle_addons_vehicle ON vehicle_addons(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_odometer_date ON odometer(vehicle_id, date);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
ANALYZE;
