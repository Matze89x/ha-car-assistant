-- A push device can be switched on for several cars (Settings -> Car): the cars of a device. No row = the device gets every car (older devices).
CREATE TABLE IF NOT EXISTS push_device_cars (
    device_id  INTEGER NOT NULL REFERENCES push_devices(id) ON DELETE CASCADE,
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    PRIMARY KEY (device_id, vehicle_id)
);
INSERT OR IGNORE INTO push_device_cars(device_id, vehicle_id) SELECT id, vehicle_id FROM push_devices WHERE vehicle_id IS NOT NULL;
