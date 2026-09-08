-- Independent seasonal progress; never import the frozen Beijing economy.
CREATE TABLE v4_case_wallets (
    season_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    stars INTEGER NOT NULL DEFAULT 0 CHECK (stars >= 0),
    scans INTEGER NOT NULL DEFAULT 0 CHECK (scans BETWEEN 0 AND 7),
    PRIMARY KEY (season_id, account_id),
    FOREIGN KEY (season_id, account_id)
        REFERENCES v4_season_memberships(season_id, account_id) ON DELETE RESTRICT
);

CREATE TABLE v4_case_inventory (
    season_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    item_code TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    effect_state TEXT NOT NULL CHECK (effect_state IN ('active', 'pending')),
    PRIMARY KEY (season_id, account_id, item_code),
    FOREIGN KEY (season_id, account_id)
        REFERENCES v4_season_memberships(season_id, account_id) ON DELETE RESTRICT
);

-- Immutable operation ledger stores the actual delta, including capped grants.
CREATE TABLE v4_economy_operations (
    id INTEGER PRIMARY KEY,
    season_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    actor_account_id INTEGER NOT NULL REFERENCES v4_accounts(id),
    operation TEXT NOT NULL CHECK (operation IN ('case.open', 'case.grant')),
    stars_delta INTEGER NOT NULL,
    scans_delta INTEGER NOT NULL,
    stars_after INTEGER NOT NULL CHECK (stars_after >= 0),
    scans_after INTEGER NOT NULL CHECK (scans_after BETWEEN 0 AND 7),
    details_json TEXT NOT NULL CHECK (json_valid(details_json)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (season_id, account_id)
        REFERENCES v4_season_memberships(season_id, account_id) ON DELETE RESTRICT
);
CREATE INDEX v4_economy_history_idx ON v4_economy_operations(season_id, account_id, id);
CREATE TRIGGER v4_economy_no_update BEFORE UPDATE ON v4_economy_operations
BEGIN
    SELECT RAISE(ABORT, 'v4_economy_operations is append-only');
END;
CREATE TRIGGER v4_economy_no_delete BEFORE DELETE ON v4_economy_operations
BEGIN
    SELECT RAISE(ABORT, 'v4_economy_operations is append-only');
END;
