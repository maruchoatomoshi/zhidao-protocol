-- Захват кампуса (V4_GAMES.md §4.12): фракции воюют за настоящие точки кампуса.
--
-- Точки, уровни и отрезки удержания принадлежат фракции, а не человеку: кто
-- именно захватил или пробил точку, не пишется нигде. Человеку нужна только
-- его фракция на сезон — это единственная таблица с account_id.
CREATE TABLE v4_capture_state (
    season_id INTEGER PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
    updated_by_account_id INTEGER,
    updated_at TEXT,
    FOREIGN KEY (season_id) REFERENCES v4_seasons(id) ON DELETE RESTRICT,
    FOREIGN KEY (updated_by_account_id) REFERENCES v4_accounts(id) ON DELETE RESTRICT
);

CREATE TABLE v4_capture_factions (
    season_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    faction TEXT NOT NULL CHECK (length(faction) BETWEEN 1 AND 20),
    PRIMARY KEY (season_id, account_id),
    FOREIGN KEY (season_id, account_id)
        REFERENCES v4_season_memberships(season_id, account_id) ON DELETE RESTRICT
);

CREATE INDEX v4_capture_factions_faction_idx ON v4_capture_factions(season_id, faction);

-- Координата точки — та, что вожатый подтвердил, стоя на месте.
CREATE TABLE v4_capture_points (
    season_id INTEGER NOT NULL,
    point_code TEXT NOT NULL CHECK (length(point_code) BETWEEN 1 AND 40),
    lon REAL NOT NULL,
    lat REAL NOT NULL,
    confirmed_at TEXT NOT NULL,
    owner TEXT CHECK (owner IS NULL OR length(owner) BETWEEN 1 AND 20),
    level INTEGER NOT NULL DEFAULT 0 CHECK (level BETWEEN 0 AND 9),
    changed_at TEXT,
    PRIMARY KEY (season_id, point_code),
    FOREIGN KEY (season_id) REFERENCES v4_seasons(id) ON DELETE RESTRICT,
    CHECK ((owner IS NULL) = (level = 0))
);

-- Отрезки удержания: из них считаются очки в дневные окна.
CREATE TABLE v4_capture_holds (
    id INTEGER PRIMARY KEY,
    season_id INTEGER NOT NULL,
    point_code TEXT NOT NULL,
    faction TEXT NOT NULL CHECK (length(faction) BETWEEN 1 AND 20),
    since TEXT NOT NULL,
    until TEXT,
    FOREIGN KEY (season_id, point_code) REFERENCES v4_capture_points(season_id, point_code) ON DELETE RESTRICT
);

CREATE INDEX v4_capture_holds_open_idx ON v4_capture_holds(season_id, point_code, until);
