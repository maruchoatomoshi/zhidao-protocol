-- Optimistic locking for Architect edits of season configuration.

ALTER TABLE v4_seasons
    ADD COLUMN revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1);

CREATE INDEX v4_seasons_status_idx
    ON v4_seasons(status, updated_at);
