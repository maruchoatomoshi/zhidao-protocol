-- Захват кампуса, этап 3 (V4_GAMES.md §4.12): способности, лидер дня, итоги войны.
--
-- Способности покупаются складчиной фракции: копилка знает фракцию и сумму,
-- а кто сколько внёс — только журнал экономики, как у любой траты. Действующие
-- эффекты, счётчик ходов у точки и дневной бонус — без людей. Активность «кто
-- в этот день сделал ход» нужна, чтобы наградить лидера дня только играющих,
-- и удаляется при подведении дня.
ALTER TABLE v4_capture_state ADD COLUMN war INTEGER NOT NULL DEFAULT 1;
ALTER TABLE v4_capture_state ADD COLUMN war_finished_at TEXT;

-- AUTOINCREMENT: номер копилки не переиспользуется — по нему возвращаются взносы.
CREATE TABLE v4_capture_pools (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id INTEGER NOT NULL,
    faction TEXT NOT NULL CHECK (length(faction) BETWEEN 1 AND 20),
    ability TEXT NOT NULL CHECK (ability IN ('shield', 'fog', 'double', 'scout')),
    target TEXT NOT NULL DEFAULT '' CHECK (length(target) <= 40),
    collected INTEGER NOT NULL DEFAULT 0 CHECK (collected >= 0),
    created_at TEXT NOT NULL,
    UNIQUE (season_id, faction, ability, target),
    FOREIGN KEY (season_id) REFERENCES v4_seasons(id) ON DELETE RESTRICT
);

CREATE TABLE v4_capture_effects (
    id INTEGER PRIMARY KEY,
    season_id INTEGER NOT NULL,
    faction TEXT NOT NULL CHECK (length(faction) BETWEEN 1 AND 20),
    ability TEXT NOT NULL CHECK (ability IN ('shield', 'fog', 'double', 'scout')),
    target TEXT NOT NULL DEFAULT '' CHECK (length(target) <= 40),
    since TEXT NOT NULL,
    until TEXT NOT NULL,
    FOREIGN KEY (season_id) REFERENCES v4_seasons(id) ON DELETE RESTRICT
);

CREATE INDEX v4_capture_effects_live_idx ON v4_capture_effects(season_id, until);

CREATE TABLE v4_capture_point_moves (
    season_id INTEGER NOT NULL,
    point_code TEXT NOT NULL CHECK (length(point_code) BETWEEN 1 AND 40),
    move_day TEXT NOT NULL,
    moves INTEGER NOT NULL CHECK (moves >= 1),
    PRIMARY KEY (season_id, point_code, move_day),
    FOREIGN KEY (season_id) REFERENCES v4_seasons(id) ON DELETE RESTRICT
);

CREATE TABLE v4_capture_activity (
    season_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    activity_day TEXT NOT NULL,
    PRIMARY KEY (season_id, account_id, activity_day),
    FOREIGN KEY (season_id, account_id)
        REFERENCES v4_season_memberships(season_id, account_id) ON DELETE RESTRICT
);

CREATE TABLE v4_capture_daily_bonus (
    season_id INTEGER NOT NULL,
    faction TEXT NOT NULL CHECK (length(faction) BETWEEN 1 AND 20),
    bonus_day TEXT NOT NULL,
    points INTEGER NOT NULL DEFAULT 0 CHECK (points >= 0),
    PRIMARY KEY (season_id, faction, bonus_day),
    FOREIGN KEY (season_id) REFERENCES v4_seasons(id) ON DELETE RESTRICT
);

CREATE TABLE v4_capture_days (
    season_id INTEGER NOT NULL,
    war INTEGER NOT NULL,
    day TEXT NOT NULL,
    winners_json TEXT NOT NULL CHECK (json_valid(winners_json)),
    rewarded INTEGER NOT NULL DEFAULT 0 CHECK (rewarded >= 0),
    settled_at TEXT NOT NULL,
    PRIMARY KEY (season_id, war, day),
    FOREIGN KEY (season_id) REFERENCES v4_seasons(id) ON DELETE RESTRICT
);

CREATE TABLE v4_capture_wars (
    season_id INTEGER NOT NULL,
    number INTEGER NOT NULL CHECK (number >= 1),
    finished_at TEXT NOT NULL,
    winners_json TEXT NOT NULL CHECK (json_valid(winners_json)),
    scores_json TEXT NOT NULL CHECK (json_valid(scores_json)),
    PRIMARY KEY (season_id, number),
    FOREIGN KEY (season_id) REFERENCES v4_seasons(id) ON DELETE RESTRICT
);
