-- Метки на карте (V4_GAMES.md §4.2): «Осторожно: геккон 壁虎» там, где стоишь.
--
-- Главное обещание — автора нет. В v4_map_marks нет account_id, а время
-- появления округлено до часа. Дневной лимит считает v4_map_mark_quota:
-- «человек — день — сколько», без ссылки на метку. Кто отметил «полезно»,
-- хранится, чтобы нельзя было голосовать дважды, и удаляется вместе с меткой.
CREATE TABLE v4_map_marks (
    id INTEGER PRIMARY KEY,
    season_id INTEGER NOT NULL,
    cell_lon INTEGER NOT NULL,
    cell_lat INTEGER NOT NULL,
    template_code TEXT NOT NULL CHECK (length(template_code) BETWEEN 1 AND 40),
    word_code TEXT NOT NULL CHECK (length(word_code) BETWEEN 1 AND 40),
    placed_hour TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    useful INTEGER NOT NULL DEFAULT 0 CHECK (useful >= 0),
    hidden_at TEXT,
    hidden_by_account_id INTEGER,
    FOREIGN KEY (season_id) REFERENCES v4_seasons(id) ON DELETE RESTRICT,
    FOREIGN KEY (hidden_by_account_id) REFERENCES v4_accounts(id) ON DELETE RESTRICT
);

CREATE INDEX v4_map_marks_season_idx ON v4_map_marks(season_id, expires_at);

CREATE TABLE v4_map_mark_votes (
    mark_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    PRIMARY KEY (mark_id, account_id),
    FOREIGN KEY (mark_id) REFERENCES v4_map_marks(id) ON DELETE CASCADE,
    FOREIGN KEY (account_id) REFERENCES v4_accounts(id) ON DELETE RESTRICT
);

CREATE TABLE v4_map_mark_quota (
    season_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    mark_day TEXT NOT NULL,
    used INTEGER NOT NULL CHECK (used BETWEEN 1 AND 10),
    PRIMARY KEY (season_id, account_id, mark_day),
    FOREIGN KEY (season_id, account_id)
        REFERENCES v4_season_memberships(season_id, account_id) ON DELETE RESTRICT
);
