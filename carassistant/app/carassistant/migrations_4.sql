-- Plugin API: tokens for integrations and plugins that push vehicle data into Car Assistant.
CREATE TABLE api_tokens (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    vehicle_id INTEGER REFERENCES vehicles(id) ON DELETE CASCADE,  -- NULL = all vehicles
    created_at TEXT NOT NULL,
    last_used TEXT
);
