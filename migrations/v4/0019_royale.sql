-- Протокол 60 (V4_GAMES.md §4.12): королевская битва на всю смену.
--
-- Состав игры, ответы и голоса нужны только пока идёт игра и полчаса после,
-- чтобы все увидели итоги; потом строки игроков, ответов и голосов удаляются,
-- а у игры остаётся только таблица мест (results_json) — как рейтинг.
-- Дневной лимит призов — отдельная таблица без ссылки на игру.
CREATE TABLE v4_royale_games (
    id INTEGER PRIMARY KEY,
    season_id INTEGER NOT NULL,
    host_account_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('lobby', 'question', 'reveal', 'over')),
    round INTEGER NOT NULL DEFAULT 0 CHECK (round >= 0),
    state_json TEXT NOT NULL CHECK (json_valid(state_json)),
    results_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(results_json)),
    purged INTEGER NOT NULL DEFAULT 0 CHECK (purged IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT,
    FOREIGN KEY (season_id) REFERENCES v4_seasons(id) ON DELETE RESTRICT,
    FOREIGN KEY (host_account_id) REFERENCES v4_accounts(id) ON DELETE RESTRICT
);

CREATE INDEX v4_royale_games_season_idx ON v4_royale_games(season_id, status);

CREATE TABLE v4_royale_players (
    game_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    joined_at TEXT NOT NULL,
    alive INTEGER NOT NULL DEFAULT 1 CHECK (alive IN (0, 1)),
    out_round INTEGER,
    revived INTEGER NOT NULL DEFAULT 0 CHECK (revived IN (0, 1)),
    total_ms INTEGER NOT NULL DEFAULT 0 CHECK (total_ms >= 0),
    PRIMARY KEY (game_id, account_id),
    FOREIGN KEY (game_id) REFERENCES v4_royale_games(id) ON DELETE CASCADE,
    FOREIGN KEY (account_id) REFERENCES v4_accounts(id) ON DELETE RESTRICT
);

CREATE TABLE v4_royale_answers (
    game_id INTEGER NOT NULL,
    round INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    choice INTEGER NOT NULL,
    ms INTEGER NOT NULL CHECK (ms >= 0),
    correct INTEGER NOT NULL CHECK (correct IN (0, 1)),
    PRIMARY KEY (game_id, round, account_id),
    FOREIGN KEY (game_id) REFERENCES v4_royale_games(id) ON DELETE CASCADE
);

CREATE TABLE v4_royale_votes (
    game_id INTEGER NOT NULL,
    round INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    surprise TEXT NOT NULL CHECK (surprise IN ('fast', 'hanzi', 'more')),
    PRIMARY KEY (game_id, round, account_id),
    FOREIGN KEY (game_id) REFERENCES v4_royale_games(id) ON DELETE CASCADE
);

CREATE TABLE v4_royale_prize_days (
    season_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    prize_day TEXT NOT NULL,
    PRIMARY KEY (season_id, account_id, prize_day),
    FOREIGN KEY (season_id, account_id)
        REFERENCES v4_season_memberships(season_id, account_id) ON DELETE RESTRICT
);
