-- Trip values of the car's own on-board computer (consumption, average speed, duration), and the ones waiting for their trip.
ALTER TABLE trips ADD COLUMN consumption_l100 REAL;
ALTER TABLE trips ADD COLUMN avg_kmh REAL;
ALTER TABLE trips ADD COLUMN bc_minutes INTEGER;
CREATE TABLE trip_summaries (
    id          INTEGER PRIMARY KEY,
    vehicle_id  INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    ts          TEXT NOT NULL,
    distance_km REAL,
    consumption REAL,
    avg_kmh     REAL,
    minutes     INTEGER
);
CREATE INDEX idx_trip_summaries_vehicle ON trip_summaries(vehicle_id, ts);
