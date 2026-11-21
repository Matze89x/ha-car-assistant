-- Web push: the devices (browsers / home-screen apps) of a signed-in user that want notifications
CREATE TABLE push_devices (
  id         INTEGER PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  endpoint   TEXT NOT NULL UNIQUE,
  p256dh     TEXT NOT NULL,
  auth       TEXT NOT NULL,
  label      TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  fails      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_push_devices_user ON push_devices(user_id);
