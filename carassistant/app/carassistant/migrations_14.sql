-- Passcode (app lock) of a login: a short code that unlocks a signed-in device again after it was idle.
ALTER TABLE users ADD COLUMN pin_salt TEXT;
ALTER TABLE users ADD COLUMN pin_iter INTEGER;
ALTER TABLE users ADD COLUMN pin_hash TEXT;
ALTER TABLE users ADD COLUMN lock_minutes INTEGER NOT NULL DEFAULT 15;   -- 0 = never lock
ALTER TABLE sessions ADD COLUMN unlocked_at TEXT;
