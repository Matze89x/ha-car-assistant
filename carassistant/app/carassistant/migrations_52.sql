-- Notifications are ONE system per person (Settings -> User): a matrix of events per car (+ the choice for new cars) and general events.
-- The per-device car lists of the Car tab are gone: a device of a person gets what the person chose.
ALTER TABLE user_notify ADD COLUMN general TEXT NOT NULL DEFAULT '[]';
DELETE FROM push_device_cars;
DELETE FROM user_notify_vehicle WHERE vehicle_id NOT IN (SELECT id FROM vehicles);
