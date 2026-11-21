-- Preferences per user (user-bound level): start car, touch feedback. Server settings stay the default.
CREATE TABLE user_prefs (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  key     TEXT NOT NULL,
  value   TEXT NOT NULL,
  PRIMARY KEY (user_id, key)
) WITHOUT ROWID;
