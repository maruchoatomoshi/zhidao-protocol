-- Зомби-протокол (V4_GAMES.md §4.12): вечерний раунд, скрещённый с Вирусом.
--
-- У игрока — сторона, код жертвы, число заражений и отметка о вакцине. Кто
-- кого заразил, не записывается. Через полчаса после конца раунда строки
-- игроков удаляются, у раунда остаются итоги (results_json). Дневной лимит
-- призов — отдельная таблица без ссылки на раунд.
CREATE TABLE v4_zombie_games (
    id INTEGER PRIMARY KEY,
    season_id INTEGER NOT NULL,
    host_account_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('lobby', 'running', 'over')),
    state_json TEXT NOT NULL CHECK (json_valid(state_json)),
    results_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(results_json)),
    purged INTEGER NOT NULL DEFAULT 0 CHECK (purged IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    ends_at TEXT,
    finished_at TEXT,
    FOREIGN KEY (season_id) REFERENCES v4_seasons(id) ON DELETE RESTRICT,
    FOREIGN KEY (host_account_id) REFERENCES v4_accounts(id) ON DELETE RESTRICT
);

CREATE INDEX v4_zombie_games_season_idx ON v4_zombie_games(season_id, status);

CREATE TABLE v4_zombie_players (
    game_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    joined_at TEXT NOT NULL,
    code TEXT NOT NULL CHECK (length(code) = 6 AND code NOT GLOB '*[^0-9]*'),
    side TEXT NOT NULL DEFAULT 'human' CHECK (side IN ('human', 'zombie')),
    starter INTEGER NOT NULL DEFAULT 0 CHECK (starter IN (0, 1)),
    turned_at TEXT,
    last_tag_at TEXT,
    tags INTEGER NOT NULL DEFAULT 0 CHECK (tags >= 0),
    vaccinated INTEGER NOT NULL DEFAULT 0 CHECK (vaccinated IN (0, 1)),
    immune_until TEXT,
    PRIMARY KEY (game_id, account_id),
    UNIQUE (game_id, code),
    FOREIGN KEY (game_id) REFERENCES v4_zombie_games(id) ON DELETE CASCADE,
    FOREIGN KEY (account_id) REFERENCES v4_accounts(id) ON DELETE RESTRICT
);

CREATE TABLE v4_zombie_prize_days (
    season_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    prize_day TEXT NOT NULL,
    PRIMARY KEY (season_id, account_id, prize_day),
    FOREIGN KEY (season_id, account_id)
        REFERENCES v4_season_memberships(season_id, account_id) ON DELETE RESTRICT
);
