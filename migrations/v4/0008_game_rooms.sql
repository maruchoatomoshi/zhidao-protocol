-- Комнаты вечерних игр: Шпион сейчас, Шифровальщики и Сбой системы — следом.
--
-- Состояние партии живёт в базе, а не в памяти процесса: перезапуск сервера
-- посреди вечера не должен убивать идущую игру (V4_GAMES.md §2). Присутствие
-- («кто сейчас смотрит на экран») наоборот держится в памяти — это частые
-- отметки, и писать их в SQLite на каждый опрос незачем.
--
-- Тайны партии (кто шпион, какое место) лежат в state_json и наружу не уходят:
-- сервер отдаёт каждому игроку только его собственный вид.
--
-- Комнаты временные. Простоявшая без действий комната удаляется целиком
-- вместе с составом — кто с кем играл, после вечера не хранится.
CREATE TABLE v4_game_rooms (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE CHECK (length(code) = 4 AND code NOT GLOB '*[^0-9]*'),
    game TEXT NOT NULL CHECK (game IN ('spy')),
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
-- Человек сидит не больше чем в одной комнате: вход в новую выводит из старой.
CREATE UNIQUE INDEX v4_game_room_players_one_room_uq ON v4_game_room_players(account_id);

-- Выключатель игры. Сломалась посреди поездки — гасим её, а не приложение.
-- Нет строки — игра включена.
CREATE TABLE v4_game_switches (
    game TEXT PRIMARY KEY CHECK (game IN ('spy')),
    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
    updated_by_account_id INTEGER NOT NULL REFERENCES v4_accounts(id),
    updated_at TEXT NOT NULL
);
