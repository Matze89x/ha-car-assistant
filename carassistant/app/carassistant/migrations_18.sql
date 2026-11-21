-- more vehicle data: first registration (derives the next inspection), engine oil, seats, permitted gross weight
ALTER TABLE vehicles ADD COLUMN first_reg TEXT;
ALTER TABLE vehicles ADD COLUMN oil_spec TEXT;
ALTER TABLE vehicles ADD COLUMN oil_l REAL;
ALTER TABLE vehicles ADD COLUMN seats INTEGER;
ALTER TABLE vehicles ADD COLUMN gross_weight_kg INTEGER;
