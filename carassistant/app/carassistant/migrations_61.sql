-- Low tank / battery message: a threshold of one's own per person and car (NULL = the car's yellow level, 0 = not used), and what was told
ALTER TABLE user_notify ADD COLUMN energy_pct INTEGER;
ALTER TABLE user_notify ADD COLUMN energy_km INTEGER;
ALTER TABLE user_notify_vehicle ADD COLUMN energy_pct INTEGER;
ALTER TABLE user_notify_vehicle ADD COLUMN energy_km INTEGER;
-- fired = 1: the person was told that the level fell to the threshold and is not told again until it was back above it (user_id 0 = the Home Assistant sensor)
CREATE TABLE IF NOT EXISTS notify_energy (
    user_id INTEGER NOT NULL,
    vehicle_id INTEGER NOT NULL,
    fired INTEGER NOT NULL DEFAULT 0,
    at TEXT,
    PRIMARY KEY (user_id, vehicle_id)
);
