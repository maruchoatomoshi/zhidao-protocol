-- Саботаж (V4_GAMES.md §4.12): Among Us вживую, станции — точки кампуса по GPS.
--
-- У игрока — роль, отметка капитана, жив ли он, код, задания и сделанные
-- задания. Кто кого вывел, не записывается. Голоса живут только до конца
-- собрания: после подсчёта удаляются, в истории игры остаётся только исход.
-- Через полчаса после конца игры строки игроков удаляются, остаются итоги.
CREATE TABLE v4_sabotage_games (
    id INTEGER PRIMARY KEY,
    season_id INTEGER NOT NULL,
    host_account_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('lobby', 'running', 'meeting', 'over')),
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

CREATE INDEX v4_sabotage_games_season_idx ON v4_sabotage_games(season_id, status);

CREATE TABLE v4_sabotage_players (
    game_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    joined_at TEXT NOT NULL,
    code TEXT NOT NULL CHECK (length(code) = 6 AND code NOT GLOB '*[^0-9]*'),
    role TEXT NOT NULL DEFAULT 'crew' CHECK (role IN ('crew', 'saboteur')),
    captain INTEGER NOT NULL DEFAULT 0 CHECK (captain IN (0, 1)),
    meetings_left INTEGER NOT NULL DEFAULT 0 CHECK (meetings_left >= 0),
    alive INTEGER NOT NULL DEFAULT 1 CHECK (alive IN (0, 1)),
    ejected INTEGER NOT NULL DEFAULT 0 CHECK (ejected IN (0, 1)),
    out_at TEXT,
    last_kill_at TEXT,
    tasks_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(tasks_json)),
    done_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(done_json)),
    PRIMARY KEY (game_id, account_id),
    UNIQUE (game_id, code),
    FOREIGN KEY (game_id) REFERENCES v4_sabotage_games(id) ON DELETE CASCADE,
    FOREIGN KEY (account_id) REFERENCES v4_accounts(id) ON DELETE RESTRICT
);

CREATE TABLE v4_sabotage_votes (
    game_id INTEGER NOT NULL,
    meeting INTEGER NOT NULL CHECK (meeting >= 1),
    account_id INTEGER NOT NULL,
    choice INTEGER NOT NULL CHECK (choice >= 0),
    PRIMARY KEY (game_id, meeting, account_id),
    FOREIGN KEY (game_id) REFERENCES v4_sabotage_games(id) ON DELETE CASCADE
);

CREATE TABLE v4_sabotage_prize_days (
    season_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    prize_day TEXT NOT NULL,
    PRIMARY KEY (season_id, account_id, prize_day),
    FOREIGN KEY (season_id, account_id)
        REFERENCES v4_season_memberships(season_id, account_id) ON DELETE RESTRICT
);
