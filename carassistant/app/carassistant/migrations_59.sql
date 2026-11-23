-- Bi-fuel cars (petrol and LPG / CNG): the second fuel of a car and the fuel of each fill-up (NULL / 'main' = the first one, 'second' = the second).
ALTER TABLE vehicles ADD COLUMN fuel2_type TEXT;
ALTER TABLE fuel ADD COLUMN fuel_kind TEXT;
