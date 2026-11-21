-- Notifications per car: a user chooses the events for each car on its own (no row = the events of the user's general choice)
CREATE TABLE IF NOT EXISTS user_notify_vehicle (
    user_id    INTEGER NOT NULL,
    vehicle_id INTEGER NOT NULL,
    events     TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (user_id, vehicle_id)
);
