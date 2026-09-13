-- Тайный агент (V4_GAMES.md §4.12): игра на всю смену, без выбывания, на очки.
--
-- Круг «агент → цель» живёт один сезон-день: в 07:00 его строки удаляются и
-- собираются заново, вчерашний круг не хранится. У агента в строке — миссия
-- дня, сколько раз он спрашивал цель и ждёт ли ответа; кто кого поймал раньше,
-- не записывается. У игрока — только очки, счётчики и отказы для вожатого.
-- Конец смены удаляет круг и игроков; остаётся таблица мест смены.
CREATE TABLE v4_agent_state (
    season_id INTEGER PRIMARY KEY,
    shift INTEGER NOT NULL DEFAULT 1 CHECK (shift >= 1),
    running INTEGER NOT NULL DEFAULT 0 CHECK (running IN (0, 1)),
    day TEXT CHECK (day IS NULL OR day GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]'),
    updated_by_account_id INTEGER,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (season_id) REFERENCES v4_seasons(id) ON DELETE RESTRICT,
    FOREIGN KEY (updated_by_account_id) REFERENCES v4_accounts(id) ON DELETE RESTRICT
);

CREATE TABLE v4_agent_players (
    season_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    joined_at TEXT NOT NULL,
    points INTEGER NOT NULL DEFAULT 0 CHECK (points >= 0),
    missions INTEGER NOT NULL DEFAULT 0 CHECK (missions >= 0),
    reveals INTEGER NOT NULL DEFAULT 0 CHECK (reveals >= 0),
    refusals INTEGER NOT NULL DEFAULT 0 CHECK (refusals >= 0),
    excluded INTEGER NOT NULL DEFAULT 0 CHECK (excluded IN (0, 1)),
    guessed_day TEXT,
    news_json TEXT CHECK (news_json IS NULL OR json_valid(news_json)),
    PRIMARY KEY (season_id, account_id),
    FOREIGN KEY (season_id, account_id)
        REFERENCES v4_season_memberships(season_id, account_id) ON DELETE RESTRICT
);

CREATE TABLE v4_agent_links (
    season_id INTEGER NOT NULL,
    agent_account_id INTEGER NOT NULL,
    target_account_id INTEGER NOT NULL CHECK (target_account_id <> agent_account_id),
    day TEXT NOT NULL CHECK (day GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]'),
    mission TEXT NOT NULL CHECK (length(mission) BETWEEN 1 AND 40),
    asks INTEGER NOT NULL DEFAULT 0 CHECK (asks >= 0),
    asking INTEGER NOT NULL DEFAULT 0 CHECK (asking IN (0, 1)),
    known INTEGER NOT NULL DEFAULT 0 CHECK (known IN (0, 1)),
    since TEXT NOT NULL,
    PRIMARY KEY (season_id, agent_account_id),
    FOREIGN KEY (season_id, agent_account_id)
        REFERENCES v4_season_memberships(season_id, account_id) ON DELETE RESTRICT,
    FOREIGN KEY (season_id, target_account_id)
        REFERENCES v4_season_memberships(season_id, account_id) ON DELETE RESTRICT
);

CREATE INDEX v4_agent_links_target_idx ON v4_agent_links(season_id, target_account_id);

CREATE TABLE v4_agent_shifts (
    season_id INTEGER NOT NULL,
    number INTEGER NOT NULL CHECK (number >= 1),
    finished_at TEXT NOT NULL,
    results_json TEXT NOT NULL CHECK (json_valid(results_json)),
    PRIMARY KEY (season_id, number),
    FOREIGN KEY (season_id) REFERENCES v4_seasons(id) ON DELETE RESTRICT
);
