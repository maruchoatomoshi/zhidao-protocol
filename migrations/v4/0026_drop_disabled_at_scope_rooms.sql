-- Two small schema defects, found while auditing the games work: a dead
-- column and a table that was never scoped to a season.
--
-- v4_accounts.disabled_at has existed since 0001. Nothing in this
-- repository ever writes it or reads it -- there is no account-disable
-- feature anywhere, not even in the admin console. Rather than build a
-- feature around a column nobody asked for, drop it.
--
-- v4_game_rooms had no season_id. An account can hold more than one season
-- membership, and room games (Spy, Ciphers, System Outage, Contraband) had
-- no way to record which season a room belonged to. 0009 already
-- established that room tables rebuild without carrying data forward --
-- rooms are temporary, and any open room closes at deploy time. Same here.
-- DROP COLUMN alone is refused: the table-level CHECK
-- "status = 'disabled' OR disabled_at IS NULL" (0001) references the
-- column, and SQLite won't drop a column a CHECK constraint depends on.
-- Rebuild instead, same as 0009 rebuilt the rooms tables. 'disabled' stays
-- a legal status value -- only the unused timestamp goes.
CREATE TABLE v4_accounts_next (
    id INTEGER PRIMARY KEY,
    public_id TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('pending', 'active', 'disabled')),
    locale TEXT NOT NULL DEFAULT 'ru',
    created_at TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    ),
    updated_at TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    ),
    CHECK (length(trim(public_id)) >= 8),
    CHECK (length(trim(display_name)) >= 1)
);
INSERT INTO v4_accounts_next(id, public_id, display_name, status, locale, created_at, updated_at)
    SELECT id, public_id, display_name, status, locale, created_at, updated_at FROM v4_accounts;
DROP TABLE v4_accounts;
ALTER TABLE v4_accounts_next RENAME TO v4_accounts;

DROP TABLE v4_game_room_players;
DROP TABLE v4_game_rooms;

CREATE TABLE v4_game_rooms (
    id INTEGER PRIMARY KEY,
    season_id INTEGER NOT NULL REFERENCES v4_seasons(id),
    code TEXT NOT NULL UNIQUE CHECK (length(code) = 4 AND code NOT GLOB '*[^0-9]*'),
    game TEXT NOT NULL CHECK (length(game) BETWEEN 2 AND 24 AND game NOT GLOB '*[^a-z]*'),
    host_account_id INTEGER NOT NULL REFERENCES v4_accounts(id),
    status TEXT NOT NULL CHECK (status IN ('lobby', 'playing')),
    settings_json TEXT NOT NULL CHECK (json_valid(settings_json)),
    state_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(state_json)),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    created_at TEXT NOT NULL,
    last_activity_at TEXT NOT NULL
);
CREATE INDEX v4_game_rooms_activity_idx ON v4_game_rooms(last_activity_at);
CREATE INDEX v4_game_rooms_season_idx ON v4_game_rooms(season_id);

CREATE TABLE v4_game_room_players (
    room_id INTEGER NOT NULL REFERENCES v4_game_rooms(id) ON DELETE CASCADE,
    account_id INTEGER NOT NULL REFERENCES v4_accounts(id),
    seat INTEGER NOT NULL CHECK (seat > 0),
    score INTEGER NOT NULL DEFAULT 0 CHECK (score >= 0),
    joined_at TEXT NOT NULL,
    PRIMARY KEY (room_id, account_id)
);
CREATE UNIQUE INDEX v4_game_room_players_one_room_uq ON v4_game_room_players(account_id);
