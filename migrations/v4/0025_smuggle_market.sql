-- Рынок Контрабанды, этап 2 (V4_GAMES.md §4.12): торговля на весь кампус на один день.
--
-- Строка торговца живёт один сезон-день: юани, товары, код сумки, роль
-- (торговец или патрульный NetWatch) и «торговал ли сегодня». Кто с кем
-- торговал и кого проверял, не записывается. При подведении итогов дня строки
-- удаляются — юани и товары сгорают, у дня остаётся таблица мест.
CREATE TABLE v4_market_players (
    season_id INTEGER NOT NULL,
    day TEXT NOT NULL CHECK (day GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]'),
    account_id INTEGER NOT NULL,
    joined_at TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'merchant' CHECK (role IN ('merchant', 'patrol')),
    money INTEGER NOT NULL CHECK (money >= 0),
    goods_json TEXT NOT NULL CHECK (json_valid(goods_json)),
    code TEXT NOT NULL CHECK (length(code) = 6 AND code NOT GLOB '*[^0-9]*'),
    traded INTEGER NOT NULL DEFAULT 0 CHECK (traded IN (0, 1)),
    last_inspected_at TEXT,
    last_inspection_at TEXT,
    news_json TEXT CHECK (news_json IS NULL OR json_valid(news_json)),
    PRIMARY KEY (season_id, day, account_id),
    UNIQUE (season_id, day, code),
    FOREIGN KEY (season_id, account_id)
        REFERENCES v4_season_memberships(season_id, account_id) ON DELETE RESTRICT
);

CREATE TABLE v4_market_days (
    season_id INTEGER NOT NULL,
    day TEXT NOT NULL,
    settled_at TEXT NOT NULL,
    results_json TEXT NOT NULL CHECK (json_valid(results_json)),
    PRIMARY KEY (season_id, day),
    FOREIGN KEY (season_id) REFERENCES v4_seasons(id) ON DELETE RESTRICT
);
