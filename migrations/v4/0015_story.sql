-- Скрытые файлы и сюжет по местам (V4_GAMES.md §4.4).
--
-- Прогресс общий на сезон: разгадывают все вместе, поэтому кто решил — не
-- хранится. День старта нужен, чтобы выпускать по фрагменту в сезон-день,
-- даже если у сезона не заполнена дата начала.
CREATE TABLE v4_story_state (
    season_id INTEGER PRIMARY KEY,
    started_day TEXT NOT NULL CHECK (started_day GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    FOREIGN KEY (season_id) REFERENCES v4_seasons(id) ON DELETE RESTRICT
);

CREATE TABLE v4_story_solved (
    season_id INTEGER NOT NULL,
    fragment_code TEXT NOT NULL CHECK (length(fragment_code) BETWEEN 1 AND 40),
    solved_day TEXT NOT NULL,
    PRIMARY KEY (season_id, fragment_code),
    FOREIGN KEY (season_id) REFERENCES v4_seasons(id) ON DELETE RESTRICT
);
