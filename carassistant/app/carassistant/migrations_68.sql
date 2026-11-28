-- The data of a wallbox: what the wallbox counted for a charge (the exact energy, instead of an estimate from the battery size), the counter of the
-- wallbox when the charge began, and the power of the charge - a point about every minute while it runs - for the curve of the wallbox card.
ALTER TABLE charge_sessions ADD COLUMN energy_kwh REAL;      -- kWh the wallbox counted for this charge (the most it said while the charge ran); empty = not known
ALTER TABLE charge_sessions ADD COLUMN counter_start REAL;   -- the counter of the wallbox over its whole life (kWh) when the charge began
CREATE TABLE IF NOT EXISTS charge_samples (
    session_id INTEGER NOT NULL REFERENCES charge_sessions(id) ON DELETE CASCADE,
    at         TEXT NOT NULL,
    kw         REAL NOT NULL,
    PRIMARY KEY (session_id, at)
);
