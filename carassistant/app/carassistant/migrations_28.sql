-- a track point that already belongs to a trip made from the track (0 = too short to be a trip)
ALTER TABLE vehicle_track ADD COLUMN trip_id INTEGER;
