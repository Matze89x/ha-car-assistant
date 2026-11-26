-- Sources: the files read from a source are kept with the ETag the server named, so asking again costs nothing (a file that did not change is answered
-- "not modified") and a hit limit or a lost connection does not empty the list; online_at = when a source was last read from the net (NULL: only the copy that
-- came with this version of the app is known, see stdsource/)
CREATE TABLE IF NOT EXISTS source_cache (
    source_id  INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    path       TEXT NOT NULL,
    etag       TEXT,
    body       BLOB NOT NULL,
    checked_at TEXT NOT NULL,
    PRIMARY KEY (source_id, path)
) WITHOUT ROWID;
ALTER TABLE sources ADD COLUMN online_at TEXT;
