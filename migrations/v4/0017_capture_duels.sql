-- Дуэли Захвата кампуса (V4_GAMES.md §4.12, этап 2).
--
-- Дуэль знает двоих — без этого нельзя сыграть. Поэтому строка живёт только
-- пока идёт дуэль и несколько минут после (показать итог), а затем удаляется.
-- Дневной лимит считает отдельная таблица без ссылки на соперника. Бонус
-- дуэлей копится фракции, а не человеку.
CREATE TABLE v4_capture_duels (
    id INTEGER PRIMARY KEY,
    season_id INTEGER NOT NULL,
    a_account_id INTEGER NOT NULL,
    b_account_id INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('quiz', 'reaction', 'tactics')),
    point_code TEXT CHECK (point_code IS NULL OR length(point_code) BETWEEN 1 AND 40),
    state_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'done', 'cancelled')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT,
    FOREIGN KEY (season_id) REFERENCES v4_seasons(id) ON DELETE RESTRICT,
    FOREIGN KEY (a_account_id) REFERENCES v4_accounts(id) ON DELETE RESTRICT,
    FOREIGN KEY (b_account_id) REFERENCES v4_accounts(id) ON DELETE RESTRICT,
    CHECK (a_account_id <> b_account_id)
);

CREATE INDEX v4_capture_duels_a_idx ON v4_capture_duels(a_account_id, status);
CREATE INDEX v4_capture_duels_b_idx ON v4_capture_duels(b_account_id, status);

CREATE TABLE v4_capture_duel_quota (
    season_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    duel_day TEXT NOT NULL,
    used INTEGER NOT NULL CHECK (used BETWEEN 1 AND 50),
    PRIMARY KEY (season_id, account_id, duel_day),
    FOREIGN KEY (season_id, account_id)
        REFERENCES v4_season_memberships(season_id, account_id) ON DELETE RESTRICT
);

CREATE TABLE v4_capture_bonus (
    season_id INTEGER NOT NULL,
    faction TEXT NOT NULL CHECK (length(faction) BETWEEN 1 AND 20),
    points INTEGER NOT NULL DEFAULT 0 CHECK (points >= 0),
    PRIMARY KEY (season_id, faction),
    FOREIGN KEY (season_id) REFERENCES v4_seasons(id) ON DELETE RESTRICT
);
