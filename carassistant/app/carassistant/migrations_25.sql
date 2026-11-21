-- Notifications per user: each user chooses the Home Assistant notify service that reaches them and which events they want.
CREATE TABLE user_notify (
  user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  service TEXT NOT NULL DEFAULT '',
  events TEXT NOT NULL DEFAULT '[]'
);
