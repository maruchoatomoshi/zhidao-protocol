-- Turns on the MAX identity provider (migration 0001 created it disabled)
-- and adds pairing codes for providers whose accounts an operator issues
-- ahead of time rather than letting a stranger self-register into the
-- roster. MAX Mini App login is the first consumer; the table is generic
-- enough for the same pattern later (see CLAUDE_HANDOFF_GAME_BLENDER §16 on
-- the game's own pairing-code idea, kept intentionally similar).

UPDATE v4_identity_providers SET is_enabled = 1 WHERE code = 'max';

CREATE TABLE v4_link_codes (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL,
    provider_code TEXT NOT NULL,
    -- SHA-256 hex of the code shown to the operator, never the code itself:
    -- same reasoning as session and CSRF tokens in v4_sessions.
    code_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    ),
    expires_at TEXT NOT NULL,
    consumed_at TEXT,
    consumed_identity_id INTEGER,
    created_by_account_id INTEGER NOT NULL,
    FOREIGN KEY (account_id) REFERENCES v4_accounts(id) ON DELETE RESTRICT,
    FOREIGN KEY (provider_code) REFERENCES v4_identity_providers(code) ON DELETE RESTRICT,
    FOREIGN KEY (consumed_identity_id) REFERENCES v4_external_identities(id) ON DELETE SET NULL,
    FOREIGN KEY (created_by_account_id) REFERENCES v4_accounts(id) ON DELETE RESTRICT,
    CHECK (length(code_hash) = 64),
    CHECK (consumed_at IS NULL OR consumed_identity_id IS NOT NULL)
);

CREATE INDEX v4_link_codes_account_idx ON v4_link_codes(account_id);

-- At most one still-usable code per account and provider. The application
-- consumes or expires the previous one before issuing a new code; this index
-- is the backstop if it ever forgets.
CREATE UNIQUE INDEX v4_link_codes_active_per_account_idx
    ON v4_link_codes(account_id, provider_code)
    WHERE consumed_at IS NULL;
