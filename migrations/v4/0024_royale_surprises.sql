-- Протокол 60, этап 2 (V4_GAMES.md §4.12): новые сюрпризы выбывших —
-- «зеркальный иероглиф» и «варианты бегают».
--
-- 0019 перечисляла сюрпризы в CHECK, а SQLite не меняет CHECK на месте, поэтому
-- таблица голосов пересобирается. Голоса живут секунды (разбор раунда), но
-- переносим их, чтобы выкатка посреди игры не стёрла чей-то выбор.
CREATE TABLE v4_royale_votes_next (
    game_id INTEGER NOT NULL,
    round INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    surprise TEXT NOT NULL CHECK (surprise IN ('fast', 'hanzi', 'more', 'mirror', 'shuffle')),
    PRIMARY KEY (game_id, round, account_id),
    FOREIGN KEY (game_id) REFERENCES v4_royale_games(id) ON DELETE CASCADE
);
INSERT INTO v4_royale_votes_next(game_id, round, account_id, surprise)
    SELECT game_id, round, account_id, surprise FROM v4_royale_votes;
DROP TABLE v4_royale_votes;
ALTER TABLE v4_royale_votes_next RENAME TO v4_royale_votes;
