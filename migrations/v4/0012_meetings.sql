-- Пазл встреч: кусок картинки получают только от другого человека.
--
-- Рукопожатие двух телефонов — код из шести цифр на 60 секунд — живёт в
-- памяти сервера: это секунды, и перезапуск просто отменяет незавершённый код.
-- В базе — только то, что должно остаться.

-- Собранные куски. Кто дал кусок, не хранится: пазлу это не нужно.
CREATE TABLE v4_puzzle_pieces (
    season_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    puzzle_code TEXT NOT NULL CHECK (length(puzzle_code) BETWEEN 1 AND 40),
    piece INTEGER NOT NULL CHECK (piece BETWEEN 0 AND 63),
    obtained_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (season_id, account_id, puzzle_code, piece),
    FOREIGN KEY (season_id, account_id)
        REFERENCES v4_season_memberships(season_id, account_id) ON DELETE RESTRICT
);

-- Кто с кем встретился сегодня — ради правила «одна пара — один кусок в
-- день». Строки прошлых дней удаляются при каждой новой встрече и при
-- открытии пазла: история знакомств после дня не хранится.
CREATE TABLE v4_meet_pairs (
    season_id INTEGER NOT NULL REFERENCES v4_seasons(id) ON DELETE RESTRICT,
    meet_day TEXT NOT NULL CHECK (meet_day GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]'),
    account_low INTEGER NOT NULL,
    account_high INTEGER NOT NULL CHECK (account_low < account_high),
    PRIMARY KEY (season_id, meet_day, account_low, account_high)
);
