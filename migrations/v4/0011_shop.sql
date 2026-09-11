-- Витрина дня и косметика.
--
-- Каталог (цены, товары) живёт в static/app/assets/shop/shop.json и проверяется
-- при старте. Здесь — только то, что должно пережить перезапуск сервера:
-- набор и запас витрины каждого дня и надетая косметика. Купленные предметы
-- лежат в v4_case_inventory, покупки — операции shop.buy в журнале экономики.

-- Витрина одного сезон-дня: какие товары выставлены, сколько штук, сколько
-- продано. Строки создаются при первом открытии витрины после 07:00 по поясу
-- сезона и больше не меняются, кроме счётчика продаж.
CREATE TABLE v4_shop_stock (
    season_id INTEGER NOT NULL REFERENCES v4_seasons(id) ON DELETE RESTRICT,
    shop_day TEXT NOT NULL CHECK (shop_day GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]'),
    item_code TEXT NOT NULL CHECK (length(item_code) BETWEEN 1 AND 40),
    stock INTEGER NOT NULL CHECK (stock > 0),
    sold INTEGER NOT NULL DEFAULT 0 CHECK (sold >= 0 AND sold <= stock),
    PRIMARY KEY (season_id, shop_day, item_code)
);

-- Надетая косметика: одна вещь на слот (обои, рамка, звуки).
CREATE TABLE v4_cosmetics_equipped (
    season_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    slot TEXT NOT NULL CHECK (slot IN ('wallpaper', 'frame', 'sounds')),
    item_code TEXT NOT NULL CHECK (length(item_code) BETWEEN 1 AND 40),
    PRIMARY KEY (season_id, account_id, slot),
    FOREIGN KEY (season_id, account_id)
        REFERENCES v4_season_memberships(season_id, account_id) ON DELETE RESTRICT
);
