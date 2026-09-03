-- Provider-neutral local authentication for the standalone V4 web app.
-- Raw passwords, session tokens, and CSRF tokens are never stored.

CREATE TABLE v4_local_credentials (
    identity_id INTEGER PRIMARY KEY,
    password_hash TEXT NOT NULL,
    must_change_password INTEGER NOT NULL DEFAULT 0
        CHECK (must_change_password IN (0, 1)),
    failed_attempts INTEGER NOT NULL DEFAULT 0 CHECK (failed_attempts >= 0),
    locked_until TEXT,
    password_changed_at TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    ),
    FOREIGN KEY (identity_id) REFERENCES v4_external_identities(id) ON DELETE RESTRICT,
    CHECK (length(password_hash) >= 64)
);

CREATE TRIGGER v4_local_credentials_provider_guard
BEFORE INSERT ON v4_local_credentials
WHEN COALESCE(
    (SELECT provider_code FROM v4_external_identities WHERE id = NEW.identity_id),
    ''
) <> 'local'
BEGIN
    SELECT RAISE(ABORT, 'credentials require a local identity');
END;

CREATE TRIGGER v4_local_credentials_identity_guard
BEFORE UPDATE OF identity_id ON v4_local_credentials
BEGIN
    SELECT RAISE(ABORT, 'credential identity cannot be changed');
END;

CREATE TRIGGER v4_local_identity_provider_guard
BEFORE UPDATE OF provider_code ON v4_external_identities
WHEN EXISTS (
    SELECT 1 FROM v4_local_credentials WHERE identity_id = OLD.id
) AND NEW.provider_code <> 'local'
BEGIN
    SELECT RAISE(ABORT, 'credential identity must remain local');
END;

CREATE TABLE v4_sessions (
    token_hash TEXT PRIMARY KEY CHECK (length(token_hash) = 64),
    csrf_token_hash TEXT NOT NULL CHECK (length(csrf_token_hash) = 64),
    account_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    revoked_at TEXT,
    FOREIGN KEY (account_id) REFERENCES v4_accounts(id) ON DELETE RESTRICT,
    CHECK (expires_at > created_at),
    CHECK (last_seen_at >= created_at),
    CHECK (revoked_at IS NULL OR revoked_at >= created_at)
);

CREATE INDEX v4_sessions_account_idx
    ON v4_sessions(account_id, revoked_at, expires_at);

CREATE TABLE v4_idempotency_keys (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL,
    operation TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL CHECK (length(request_hash) = 64),
    response_status INTEGER NOT NULL CHECK (response_status BETWEEN 200 AND 599),
    response_json TEXT NOT NULL CHECK (json_valid(response_json)),
    created_at TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    ),
    expires_at TEXT,
    FOREIGN KEY (account_id) REFERENCES v4_accounts(id) ON DELETE RESTRICT,
    UNIQUE (account_id, operation, idempotency_key),
    CHECK (length(trim(operation)) >= 1),
    CHECK (length(idempotency_key) BETWEEN 8 AND 128),
    CHECK (expires_at IS NULL OR expires_at >= created_at)
);

CREATE INDEX v4_idempotency_expiry_idx
    ON v4_idempotency_keys(expires_at)
    WHERE expires_at IS NOT NULL;
