-- Settings: Benutzer / Auto / System. A car can have its own colour for the designs "with your own colour" (like the system one),
-- and a person can switch the notifications of a whole car off (the events themselves are chosen per car).
ALTER TABLE vehicles ADD COLUMN accent TEXT;
ALTER TABLE user_notify_vehicle ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1;
