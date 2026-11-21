-- a car always keeps a chosen photo; a chosen video is optional and plays on top of it
ALTER TABLE vehicles ADD COLUMN photo_id INTEGER;
ALTER TABLE vehicles ADD COLUMN video_id INTEGER;
UPDATE vehicles SET
  photo_id = COALESCE(
    (SELECT m.id FROM vehicle_media m WHERE m.id = vehicles.media_id AND m.kind = 'photo'),
    (SELECT m.id FROM vehicle_media m WHERE m.vehicle_id = vehicles.id AND m.kind = 'photo' ORDER BY m.id DESC LIMIT 1)),
  video_id = (SELECT m.id FROM vehicle_media m WHERE m.id = vehicles.media_id AND m.kind = 'video');
