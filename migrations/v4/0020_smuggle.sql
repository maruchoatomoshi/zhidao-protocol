-- Контрабанда (V4_GAMES.md §4.12): игра за столом с игровыми юанями.
--
-- Юани живут только в состоянии комнаты и сгорают с ней. Настоящие ★ получает
-- только победитель партии от четырёх игроков — не чаще раза в сезон-день.
-- Лимит — отдельная таблица без ссылки на комнату и соперников.
CREATE TABLE v4_smuggle_prize_days (
    season_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    prize_day TEXT NOT NULL,
    PRIMARY KEY (season_id, account_id, prize_day),
    FOREIGN KEY (season_id, account_id)
        REFERENCES v4_season_memberships(season_id, account_id) ON DELETE RESTRICT
);
