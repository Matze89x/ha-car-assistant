-- Fixed costs of a car (vehicle tax, insurance, parking, ...): one row per cost, paid once or again and again from a first due date.
-- The cost page counts every payment on the day it falls due (see fuelstats.fixed_payments); nothing is stored per payment.
CREATE TABLE IF NOT EXISTS fixed_costs (
    id         INTEGER PRIMARY KEY,
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    title      TEXT NOT NULL,
    cost_kind  TEXT NOT NULL DEFAULT 'tax',
    cost       REAL NOT NULL,
    every      TEXT NOT NULL DEFAULT 'year',
    start_date TEXT NOT NULL,
    end_date   TEXT,
    notes      TEXT
);
CREATE INDEX IF NOT EXISTS idx_fixed_costs_vehicle ON fixed_costs(vehicle_id, start_date);
