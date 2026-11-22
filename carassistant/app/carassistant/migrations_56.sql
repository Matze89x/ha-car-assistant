-- Plugin tokens: an optional, encrypted copy (only when the administrator switched "Remember plugin tokens" on), so the set-up guide can offer the token again.
-- Never part of a car backup (those carry only the fingerprint); the key of the encryption is not part of any backup file.
ALTER TABLE api_tokens ADD COLUMN token_enc TEXT;
