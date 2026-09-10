-- Оценка бумажного дневника и REP.
--
-- Дневник остаётся бумажным (V4_DECISIONS §1): в приложении только оценка,
-- которую ставит вожатый, — 0–3 звезды и бонус за день. Оценка приносит REP
-- и ★ по правилам `static/app/assets/diary/diary.json` и первую за день
-- попытку кейса за 3 звезды.
--
-- 1. Журнал экономики. В 0006 CHECK пускал только case.open и case.grant, и
--    любая новая операция требовала бы пересборки. Пересобираем один раз:
--    CHECK проверяет форму имени операции, список живёт в коде. Добавлены
--    rep_delta/rep_after. Все прежние строки переносятся как есть (REP у них
--    0 — до этой миграции REP не существовало), таблица остаётся только на
--    дописывание: триггеры пересоздаются.
CREATE TABLE v4_economy_operations_next (
    id INTEGER PRIMARY KEY,
    season_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    actor_account_id INTEGER NOT NULL REFERENCES v4_accounts(id),
    operation TEXT NOT NULL CHECK (
        length(operation) BETWEEN 3 AND 48
        AND operation GLOB '[a-z]*.[a-z]*'
        AND operation NOT GLOB '*[^a-z._-]*'
    ),
    stars_delta INTEGER NOT NULL,
    scans_delta INTEGER NOT NULL,
    rep_delta INTEGER NOT NULL DEFAULT 0,
    stars_after INTEGER NOT NULL CHECK (stars_after >= 0),
    scans_after INTEGER NOT NULL CHECK (scans_after BETWEEN 0 AND 7),
    rep_after INTEGER NOT NULL DEFAULT 0,
    details_json TEXT NOT NULL CHECK (json_valid(details_json)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (season_id, account_id)
        REFERENCES v4_season_memberships(season_id, account_id) ON DELETE RESTRICT
);
INSERT INTO v4_economy_operations_next(
    id, season_id, account_id, actor_account_id, operation, stars_delta, scans_delta,
    stars_after, scans_after, details_json, created_at
)
SELECT id, season_id, account_id, actor_account_id, operation, stars_delta, scans_delta,
       stars_after, scans_after, details_json, created_at
FROM v4_economy_operations;
DROP TABLE v4_economy_operations;
ALTER TABLE v4_economy_operations_next RENAME TO v4_economy_operations;
CREATE INDEX v4_economy_history_idx ON v4_economy_operations(season_id, account_id, id);
CREATE TRIGGER v4_economy_no_update BEFORE UPDATE ON v4_economy_operations
BEGIN
    SELECT RAISE(ABORT, 'v4_economy_operations is append-only');
END;
CREATE TRIGGER v4_economy_no_delete BEFORE DELETE ON v4_economy_operations
BEGIN
    SELECT RAISE(ABORT, 'v4_economy_operations is append-only');
END;

-- 2. REP живёт рядом с ★ и попытками. Отрицательным он может быть: в сезоне 1
--    штрафы за присутствие снимали REP, и запрещать это схемой рано.
ALTER TABLE v4_case_wallets ADD COLUMN rep INTEGER NOT NULL DEFAULT 0;

-- 3. Текущая оценка за день. История изменений — в журнале экономики и аудите;
--    здесь только последнее состояние и ревизия, по которой два вожатых не
--    перезапишут оценку друг друга молча. scan_granted помнит, что попытка за
--    3 звезды этого дня уже выдана: переоценка 3 → 2 → 3 не выдаёт вторую.
CREATE TABLE v4_diary_ratings (
    season_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    entry_date TEXT NOT NULL CHECK (entry_date GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]'),
    stars INTEGER NOT NULL CHECK (stars BETWEEN 0 AND 3),
    bonus INTEGER NOT NULL CHECK (bonus IN (0, 1)),
    scan_granted INTEGER NOT NULL DEFAULT 0 CHECK (scan_granted IN (0, 1)),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    rated_by_account_id INTEGER NOT NULL REFERENCES v4_accounts(id),
    rated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (season_id, account_id, entry_date),
    FOREIGN KEY (season_id, account_id)
        REFERENCES v4_season_memberships(season_id, account_id) ON DELETE RESTRICT
);
CREATE INDEX v4_diary_ratings_day_idx ON v4_diary_ratings(season_id, entry_date);
