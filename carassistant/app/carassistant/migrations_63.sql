-- Logging in with an account (docs/plugins.md, "Logging in with an account"): the tokens a provider gave a set-up step of type ``oauth``, sealed.
-- A connection belongs to ONE package (``plugin``) and one step of its flow and is used by the installs linked to it - one, or several cars of the same
-- account. ``oauth_pending`` holds a login that has begun (the state of the request, the sealed PKCE verifier) for a few minutes.
CREATE TABLE IF NOT EXISTS connections (
  id         INTEGER PRIMARY KEY,
  plugin     TEXT NOT NULL,
  step       TEXT NOT NULL,
  secret     TEXT NOT NULL DEFAULT '',
  expires_at TEXT,
  state      TEXT NOT NULL DEFAULT 'ok',
  error      TEXT NOT NULL DEFAULT '',
  updated    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS connection_links (
  addon_pk      INTEGER NOT NULL REFERENCES vehicle_addons(id) ON DELETE CASCADE,
  step          TEXT NOT NULL,
  connection_id INTEGER NOT NULL REFERENCES connections(id) ON DELETE CASCADE,
  PRIMARY KEY (addon_pk, step)
);
CREATE INDEX IF NOT EXISTS idx_connection_links_conn ON connection_links(connection_id);

CREATE TABLE IF NOT EXISTS oauth_pending (
  state    TEXT PRIMARY KEY,
  addon_pk INTEGER NOT NULL REFERENCES vehicle_addons(id) ON DELETE CASCADE,
  step     TEXT NOT NULL,
  kind     TEXT NOT NULL DEFAULT 'code',
  verifier TEXT NOT NULL DEFAULT '',
  redirect TEXT NOT NULL DEFAULT '',
  extra    TEXT NOT NULL DEFAULT '',
  created  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_oauth_pending_addon ON oauth_pending(addon_pk, step);
