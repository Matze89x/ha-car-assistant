-- A source gets a clean name (taken from the repository or its root index.json unless the user typed one) and keeps the notes of its last check.
ALTER TABLE sources ADD COLUMN name_auto INTEGER NOT NULL DEFAULT 0;
ALTER TABLE sources ADD COLUMN note TEXT;
