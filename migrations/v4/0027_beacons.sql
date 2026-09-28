-- Метки на кампусе (V4_GAMES.md §3.7): QR-табличка у каждой точки Захвата.
--
-- Решение пользователя 2026-09-28: у точки висит табличка с QR, и засчитывается
-- только скан настоящей таблички рядом с ней — QR плюс GPS. Фото метки,
-- пересланное в общежитие, не сработает: там не тот GPS.
--
-- token — случайная строка с таблички. Перевыпуск меняет её, и старая
-- табличка перестаёт действовать. installed_* — где вожатый её повесил:
-- установка и есть подтверждение точки (v4_capture_points), координата — его
-- телефона у таблички, а не с карты. far_* — сколько раз настоящую метку
-- сканировали далеко от места: табличку перевесили или сфотографировали.
-- Кто сканировал, не хранится — только место и счётчик.
CREATE TABLE v4_beacons (
    season_id INTEGER NOT NULL,
    point_code TEXT NOT NULL CHECK (length(point_code) BETWEEN 1 AND 40),
    token TEXT NOT NULL CHECK (length(token) = 10),
    issued_at TEXT NOT NULL,
    installed_at TEXT,
    installed_lon REAL,
    installed_lat REAL,
    far_scans INTEGER NOT NULL DEFAULT 0 CHECK (far_scans >= 0),
    far_last_at TEXT,
    PRIMARY KEY (season_id, point_code),
    UNIQUE (season_id, token),
    FOREIGN KEY (season_id) REFERENCES v4_seasons(id) ON DELETE RESTRICT
);
