-- Makes detaching a MAX account possible at all.
--
-- 0004 declared consumed_identity_id as ON DELETE SET NULL and, on the same
-- table, CHECK (consumed_at IS NULL OR consumed_identity_id IS NOT NULL).
-- The two contradict each other: the foreign key promises the column may go
-- NULL when the identity is deleted, and the CHECK forbids precisely the row
-- that leaves behind. So deleting a linked identity did not merely lose
-- history — it failed outright with "CHECK constraint failed", and a MAX
-- account paired to the wrong child could be detached only by editing the
-- database by hand.
--
-- The foreign key's reading is the one that survives: a consumed code points
-- at the identity it created while that identity exists, and at nothing once
-- it is unlinked. When a code was consumed stays on the row.
--
-- Which MAX account consumed it is deliberately written into the
-- 'identity.unlinked' audit entry at the moment of unlinking, because that is
-- the moment it stops existing anywhere else: 'identity.linked' records only
-- the provider name, not the subject. Do not read that entry's absence as
-- proof no MAX was attached — read the unlink entry.
--
-- SQLite cannot drop a CHECK in place, so the table is rebuilt. Nothing
-- references v4_link_codes, so there are no incoming keys to repoint; the old
-- table's indexes go with it and are recreated below. Foreign keys are
-- switched off for the rebuild and checked after, same as every other
-- rebuild in this migration set (0026's audit found the reason: SQLite's own
-- documentation requires it for a table with incoming references, and
-- migrations.py now does this for every migration, not just this one).

CREATE TABLE v4_link_codes_rebuilt (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL,
    provider_code TEXT NOT NULL,
    code_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    ),
    expires_at TEXT NOT NULL,
    consumed_at TEXT,
    consumed_identity_id INTEGER,
    created_by_account_id INTEGER NOT NULL,
    revoked_at TEXT,
    revoked_by_account_id INTEGER,
    FOREIGN KEY (account_id) REFERENCES v4_accounts(id) ON DELETE RESTRICT,
    FOREIGN KEY (provider_code) REFERENCES v4_identity_providers(code) ON DELETE RESTRICT,
    FOREIGN KEY (consumed_identity_id) REFERENCES v4_external_identities(id) ON DELETE SET NULL,
    FOREIGN KEY (created_by_account_id) REFERENCES v4_accounts(id) ON DELETE RESTRICT,
    FOREIGN KEY (revoked_by_account_id) REFERENCES v4_accounts(id) ON DELETE RESTRICT,
    CHECK (length(code_hash) = 64)
);

INSERT INTO v4_link_codes_rebuilt(
    id, account_id, provider_code, code_hash, created_at, expires_at,
    consumed_at, consumed_identity_id, created_by_account_id,
    revoked_at, revoked_by_account_id
)
SELECT
    id, account_id, provider_code, code_hash, created_at, expires_at,
    consumed_at, consumed_identity_id, created_by_account_id,
    revoked_at, revoked_by_account_id
FROM v4_link_codes;

DROP TABLE v4_link_codes;

ALTER TABLE v4_link_codes_rebuilt RENAME TO v4_link_codes;

CREATE INDEX v4_link_codes_account_idx ON v4_link_codes(account_id);

CREATE UNIQUE INDEX v4_link_codes_active_per_account_idx
    ON v4_link_codes(account_id, provider_code)
    WHERE consumed_at IS NULL AND revoked_at IS NULL;
