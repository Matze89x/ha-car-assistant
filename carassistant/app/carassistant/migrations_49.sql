-- MCP access (Settings -> System): access keys (only a hash is stored) and a short log of what a key did
CREATE TABLE IF NOT EXISTS mcp_keys (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    key_hash   TEXT NOT NULL UNIQUE,
    prefix     TEXT NOT NULL,
    level      TEXT NOT NULL DEFAULT 'read',
    created_at TEXT NOT NULL,
    last_used  TEXT,
    uses       INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS mcp_log (
    id       INTEGER PRIMARY KEY,
    ts       TEXT NOT NULL,
    key_name TEXT,
    method   TEXT NOT NULL,
    tool     TEXT,
    ok       INTEGER NOT NULL DEFAULT 1,
    detail   TEXT
);
