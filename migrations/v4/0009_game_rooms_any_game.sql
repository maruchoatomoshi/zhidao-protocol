-- Комнаты для любой игры за столом: Шифровальщики сейчас, Сбой системы следом.
--
-- 0008 перечисляла игры в CHECK (game IN ('spy')). Это была ошибка: SQLite не
-- умеет менять CHECK на месте, и каждая новая игра требовала бы пересборки
-- таблиц. Теперь база проверяет только форму кода игры, а список игр живёт в
-- коде (zhidao_v4/rooms.py, GAMES) — там, где живут их правила.
--
-- Комнаты временные (полчаса без действий — и их нет), поэтому таблицы
-- комнат пересобираются без переноса: в момент выкатки открытые комнаты
-- закрываются. Выключатели игр — решение организаторов, их переносим.
DROP TABLE v4_game_room_players;
DROP TABLE v4_game_rooms;

CREATE TABLE v4_game_rooms (
    id INTEGER PRIMARY KEY,
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

CREATE TABLE v4_game_room_players (
    room_id INTEGER NOT NULL REFERENCES v4_game_rooms(id) ON DELETE CASCADE,
    account_id INTEGER NOT NULL REFERENCES v4_accounts(id),
    seat INTEGER NOT NULL CHECK (seat > 0),
    score INTEGER NOT NULL DEFAULT 0 CHECK (score >= 0),
    joined_at TEXT NOT NULL,
    PRIMARY KEY (room_id, account_id)
);
CREATE UNIQUE INDEX v4_game_room_players_one_room_uq ON v4_game_room_players(account_id);

CREATE TABLE v4_game_switches_next (
    game TEXT PRIMARY KEY CHECK (length(game) BETWEEN 2 AND 24 AND game NOT GLOB '*[^a-z]*'),
    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
    updated_by_account_id INTEGER NOT NULL REFERENCES v4_accounts(id),
    updated_at TEXT NOT NULL
);
INSERT INTO v4_game_switches_next(game, enabled, updated_by_account_id, updated_at)
    SELECT game, enabled, updated_by_account_id, updated_at FROM v4_game_switches;
DROP TABLE v4_game_switches;
ALTER TABLE v4_game_switches_next RENAME TO v4_game_switches;
