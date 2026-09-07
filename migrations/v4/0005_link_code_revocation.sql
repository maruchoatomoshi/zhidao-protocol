-- Fixes a defect in 0004: an operator could never issue a second pairing code
-- for the same participant.
--
-- 0004 guarded "at most one usable code per account and provider" with a
-- partial unique index on `WHERE consumed_at IS NULL`, and
-- auth.create_link_code retired the previous code by pushing its `expires_at`
-- into the past. But an expired code is still an unconsumed row, so it still
-- occupies the index slot: the very next INSERT died with
-- `UNIQUE constraint failed: v4_link_codes.account_id, v4_link_codes.provider_code`.
-- That hits the ordinary case, not an edge one — a code lives 30 minutes, so
-- "the child never got round to entering it, issue another" is exactly what
-- an operator does.
--
-- The index cannot simply exclude expired rows: SQLite forbids
-- non-deterministic functions such as datetime('now') in a partial index
-- predicate, so expiry is not expressible there. Instead a retired code is
-- now marked explicitly, and the invariant becomes "at most one code that is
-- neither consumed nor revoked".
--
-- Revoked rows are kept rather than deleted: "a code was issued to this
-- account and never used" is exactly the sort of thing worth being able to
-- read back when a participant says they could not get in.

ALTER TABLE v4_link_codes ADD COLUMN revoked_at TEXT;
ALTER TABLE v4_link_codes ADD COLUMN revoked_by_account_id INTEGER
    REFERENCES v4_accounts(id) ON DELETE RESTRICT;

DROP INDEX v4_link_codes_active_per_account_idx;

CREATE UNIQUE INDEX v4_link_codes_active_per_account_idx
    ON v4_link_codes(account_id, provider_code)
    WHERE consumed_at IS NULL AND revoked_at IS NULL;
