-- Tyres like the original: pressure when fully loaded, and a separate rear axle (size / name).
ALTER TABLE tire_pressure ADD COLUMN load_front_bar REAL;
ALTER TABLE tire_pressure ADD COLUMN load_rear_bar REAL;
ALTER TABLE tires ADD COLUMN rear_size TEXT;
ALTER TABLE tires ADD COLUMN rear_name TEXT;
