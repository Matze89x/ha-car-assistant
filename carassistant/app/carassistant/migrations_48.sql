-- A device that turned notifications on inside one car's web app gets that car's messages only (NULL = all cars)
ALTER TABLE push_devices ADD COLUMN vehicle_id INTEGER REFERENCES vehicles(id) ON DELETE CASCADE;
