-- Accounts for direct (external) access: users, sessions, passkeys, recovery codes, one-time challenges.
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL,
    display_name TEXT,
    pw_salt TEXT, pw_iter INTEGER, pw_hash TEXT,
    is_admin INTEGER NOT NULL DEFAULT 0,
    handle TEXT,
    created_at TEXT NOT NULL,
    last_login TEXT
);
CREATE UNIQUE INDEX users_username_lower ON users (lower(username));
CREATE TABLE sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    auth TEXT NOT NULL DEFAULT 'password',
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX idx_sessions_user ON sessions (user_id);
CREATE TABLE passkeys (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    credential_id TEXT NOT NULL UNIQUE,
    public_key BLOB NOT NULL,
    sign_count INTEGER NOT NULL DEFAULT 0,
    label TEXT NOT NULL DEFAULT 'Passkey',
    rp_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_used TEXT
);
CREATE TABLE recovery_codes (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    code_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    used_at TEXT
);
CREATE TABLE auth_challenges (
    token TEXT PRIMARY KEY,
    challenge TEXT NOT NULL,
    purpose TEXT NOT NULL,
    user_id INTEGER,
    expires_at TEXT NOT NULL
);
