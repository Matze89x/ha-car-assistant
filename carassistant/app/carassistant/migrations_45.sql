-- The VIN is typed in by a person; a plugin only compares. This remembers that the car reported exactly this VIN.
ALTER TABLE vehicles ADD COLUMN vin_verified INTEGER NOT NULL DEFAULT 0;
