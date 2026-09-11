-- Вирус Протокола: шуточная «инфекция» (V4_GAMES.md §4.7).
--
-- Хранится ровно то, что решено: заражён ли человек и до какого времени, и
-- включён ли у него фаервол. Кто кого заразил, не хранится ни здесь, ни где-то
-- ещё: цепочка заражений была бы графом знакомств. Покупки антивируса и
-- фаервола — обычные операции журнала экономики.
CREATE TABLE v4_virus_state (
    season_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    infected_until TEXT,
    firewall_until TEXT,
    PRIMARY KEY (season_id, account_id),
    FOREIGN KEY (season_id, account_id)
        REFERENCES v4_season_memberships(season_id, account_id) ON DELETE RESTRICT
);
