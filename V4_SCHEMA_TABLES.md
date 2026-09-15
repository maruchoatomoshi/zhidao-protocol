# ZHIDAO V4 — таблицы текущей схемы

<!-- Сгенерировано tools/schema_doc.py из migrations/v4. Не править руками:
     python tools/schema_doc.py пересобирает файл, тест сверяет его со схемой. -->

Последняя миграция: **0025**. Таблиц: **66**, явных индексов: **31**, триггеров: **7**.

Здесь только то, что SQLite сообщает о структуре: колонки, внешние ключи,
индексы, триггеры. CHECK-ограничения, комментарии и причины решений — в
самих файлах `migrations/v4/`. Модель данных и её правила — `V4_SCHEMA.md`.

## Миграции

| № | Файл | Назначение |
|---|---|---|
| 0001 | `0001_identity_seasons_groups.sql` | ZHIDAO Protocol V4 foundation. |
| 0002 | `0002_local_auth_sessions.sql` | Provider-neutral local authentication for the standalone V4 web app. |
| 0003 | `0003_architect_console.sql` | Optimistic locking for Architect edits of season configuration. |
| 0004 | `0004_max_provider_link_codes.sql` | Turns on the MAX identity provider (migration 0001 created it disabled) |
| 0005 | `0005_link_code_revocation.sql` | Fixes a defect in 0004: an operator could never issue a second pairing code |
| 0006 | `0006_cases.sql` | Independent seasonal progress; never import the frozen Beijing economy. |
| 0007 | `0007_campus_exploration.sql` | Туман кампуса: карту открывает группа, ногами. |
| 0008 | `0008_game_rooms.sql` | Комнаты вечерних игр: Шпион сейчас, Шифровальщики и Сбой системы — следом. |
| 0009 | `0009_game_rooms_any_game.sql` | Комнаты для любой игры за столом: Шифровальщики сейчас, Сбой системы следом. |
| 0010 | `0010_diary_ratings.sql` | Оценка бумажного дневника и REP. |
| 0011 | `0011_shop.sql` | Витрина дня и косметика. |
| 0012 | `0012_meetings.sql` | Пазл встреч: кусок картинки получают только от другого человека. |
| 0013 | `0013_virus.sql` | Вирус Протокола: шуточная «инфекция» (V4_GAMES.md §4.7). |
| 0014 | `0014_map_marks.sql` | Метки на карте (V4_GAMES.md §4.2): «Осторожно: геккон 壁虎» там, где стоишь. |
| 0015 | `0015_story.sql` | Скрытые файлы и сюжет по местам (V4_GAMES.md §4.4). |
| 0016 | `0016_capture.sql` | Захват кампуса (V4_GAMES.md §4.12): фракции воюют за настоящие точки кампуса. |
| 0017 | `0017_capture_duels.sql` | Дуэли Захвата кампуса (V4_GAMES.md §4.12, этап 2). |
| 0018 | `0018_capture_war.sql` | Захват кампуса, этап 3 (V4_GAMES.md §4.12): способности, лидер дня, итоги войны. |
| 0019 | `0019_royale.sql` | Протокол 60 (V4_GAMES.md §4.12): королевская битва на всю смену. |
| 0020 | `0020_smuggle.sql` | Контрабанда (V4_GAMES.md §4.12): игра за столом с игровыми юанями. |
| 0021 | `0021_agent.sql` | Тайный агент (V4_GAMES.md §4.12): игра на всю смену, без выбывания, на очки. |
| 0022 | `0022_zombie.sql` | Зомби-протокол (V4_GAMES.md §4.12): вечерний раунд, скрещённый с Вирусом. |
| 0023 | `0023_sabotage.sql` | Саботаж (V4_GAMES.md §4.12): Among Us вживую, станции — точки кампуса по GPS. |
| 0024 | `0024_royale_surprises.sql` | Протокол 60, этап 2 (V4_GAMES.md §4.12): новые сюрпризы выбывших — |
| 0025 | `0025_smuggle_market.sql` | Рынок Контрабанды, этап 2 (V4_GAMES.md §4.12): торговля на весь кампус на один день. |

## Таблицы

### Созданы в 0001 — `0001_identity_seasons_groups.sql`

#### `v4_accounts`

_создана в 0001_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `id` | INTEGER |  |  | 1 |
| `public_id` | TEXT | да |  |  |
| `display_name` | TEXT | да |  |  |
| `status` | TEXT | да | `'active'` |  |
| `locale` | TEXT | да | `'ru'` |  |
| `created_at` | TEXT | да | `strftime('%Y-%m-%dT%H:%M:%fZ', 'now')` |  |
| `updated_at` | TEXT | да | `strftime('%Y-%m-%dT%H:%M:%fZ', 'now')` |  |
| `disabled_at` | TEXT |  |  |  |

Индексы и уникальность:
- из определения таблицы: UNIQUE-ограничение — (public_id)

#### `v4_audit_log`

_создана в 0001_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `id` | INTEGER |  |  | 1 |
| `occurred_at` | TEXT | да | `strftime('%Y-%m-%dT%H:%M:%fZ', 'now')` |  |
| `actor_account_id` | INTEGER |  |  |  |
| `season_id` | INTEGER |  |  |  |
| `action` | TEXT | да |  |  |
| `entity_type` | TEXT | да |  |  |
| `entity_id` | TEXT |  |  |  |
| `request_id` | TEXT |  |  |  |
| `before_json` | TEXT |  |  |  |
| `after_json` | TEXT |  |  |  |
| `metadata_json` | TEXT |  |  |  |

Внешние ключи:
- (season_id) → `v4_seasons`(id) ON DELETE RESTRICT
- (actor_account_id) → `v4_accounts`(id) ON DELETE RESTRICT

Индексы и уникальность:
- `v4_audit_log_actor_idx`: индекс — (actor_account_id, occurred_at)
- `v4_audit_log_entity_idx`: индекс — (entity_type, entity_id, occurred_at)

Триггеры: `v4_audit_log_no_delete`, `v4_audit_log_no_update`

#### `v4_external_identities`

_создана в 0001_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `id` | INTEGER |  |  | 1 |
| `account_id` | INTEGER | да |  |  |
| `provider_code` | TEXT | да |  |  |
| `provider_subject` | TEXT | да |  |  |
| `provider_username` | TEXT |  |  |  |
| `verified_at` | TEXT |  |  |  |
| `last_seen_at` | TEXT |  |  |  |
| `created_at` | TEXT | да | `strftime('%Y-%m-%dT%H:%M:%fZ', 'now')` |  |
| `metadata_json` | TEXT |  |  |  |

Внешние ключи:
- (provider_code) → `v4_identity_providers`(code) ON DELETE RESTRICT
- (account_id) → `v4_accounts`(id) ON DELETE RESTRICT

Индексы и уникальность:
- из определения таблицы: UNIQUE-ограничение — (provider_code, provider_subject)
- из определения таблицы: UNIQUE-ограничение — (account_id, provider_code)
- `v4_external_identities_account_idx`: индекс — (account_id)

Триггеры: `v4_local_identity_provider_guard`

#### `v4_group_memberships`

_создана в 0001_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `id` | INTEGER |  |  | 1 |
| `season_id` | INTEGER | да |  |  |
| `group_id` | INTEGER | да |  |  |
| `season_membership_id` | INTEGER | да |  |  |
| `membership_role` | TEXT | да | `'member'` |  |
| `joined_at` | TEXT | да | `strftime('%Y-%m-%dT%H:%M:%fZ', 'now')` |  |
| `left_at` | TEXT |  |  |  |

Внешние ключи:
- (season_membership_id, season_id) → `v4_season_memberships`(id, season_id) ON DELETE RESTRICT
- (group_id, season_id) → `v4_groups`(id, season_id) ON DELETE RESTRICT

Индексы и уникальность:
- `v4_active_group_membership_uq`: уникальный индекс, частичный (WHERE — в миграции) — (group_id, season_membership_id)
- `v4_group_memberships_member_idx`: индекс — (season_membership_id, left_at)
- `v4_one_active_participant_group_uq`: уникальный индекс, частичный (WHERE — в миграции) — (season_id, season_membership_id)

#### `v4_groups`

_создана в 0001_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `id` | INTEGER |  |  | 1 |
| `season_id` | INTEGER | да |  |  |
| `code` | TEXT | да |  |  |
| `name` | TEXT | да |  |  |
| `status` | TEXT | да | `'active'` |  |
| `capacity` | INTEGER |  |  |  |
| `created_by_account_id` | INTEGER |  |  |  |
| `created_at` | TEXT | да | `strftime('%Y-%m-%dT%H:%M:%fZ', 'now')` |  |
| `updated_at` | TEXT | да | `strftime('%Y-%m-%dT%H:%M:%fZ', 'now')` |  |

Внешние ключи:
- (created_by_account_id) → `v4_accounts`(id) ON DELETE RESTRICT
- (season_id) → `v4_seasons`(id) ON DELETE RESTRICT

Индексы и уникальность:
- из определения таблицы: UNIQUE-ограничение — (season_id, code)
- из определения таблицы: UNIQUE-ограничение — (id, season_id)

#### `v4_identity_providers`

_создана в 0001_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `code` | TEXT |  |  | 1 |
| `display_name` | TEXT | да |  |  |
| `is_enabled` | INTEGER | да | `1` |  |
| `created_at` | TEXT | да | `strftime('%Y-%m-%dT%H:%M:%fZ', 'now')` |  |

#### `v4_role_assignments`

_создана в 0001_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `id` | INTEGER |  |  | 1 |
| `account_id` | INTEGER | да |  |  |
| `role_code` | TEXT | да |  |  |
| `season_id` | INTEGER |  |  |  |
| `granted_by_account_id` | INTEGER |  |  |  |
| `granted_at` | TEXT | да | `strftime('%Y-%m-%dT%H:%M:%fZ', 'now')` |  |
| `revoked_at` | TEXT |  |  |  |
| `reason` | TEXT |  |  |  |

Внешние ключи:
- (granted_by_account_id) → `v4_accounts`(id) ON DELETE RESTRICT
- (season_id) → `v4_seasons`(id) ON DELETE RESTRICT
- (role_code) → `v4_roles`(code) ON DELETE RESTRICT
- (account_id) → `v4_accounts`(id) ON DELETE RESTRICT

Индексы и уникальность:
- `v4_active_global_role_uq`: уникальный индекс, частичный (WHERE — в миграции) — (account_id, role_code)
- `v4_active_season_role_uq`: уникальный индекс, частичный (WHERE — в миграции) — (account_id, role_code, season_id)
- `v4_role_assignments_season_idx`: индекс — (season_id, role_code, account_id)

#### `v4_roles`

_создана в 0001_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `code` | TEXT |  |  | 1 |
| `display_name` | TEXT | да |  |  |
| `description` | TEXT | да |  |  |
| `is_system` | INTEGER | да | `1` |  |

#### `v4_schema_migrations`

_создана в 0001_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `version` | INTEGER |  |  | 1 |
| `name` | TEXT | да |  |  |
| `checksum` | TEXT | да |  |  |
| `applied_at` | TEXT | да | `strftime('%Y-%m-%dT%H:%M:%fZ', 'now')` |  |

#### `v4_season_memberships`

_создана в 0001_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `id` | INTEGER |  |  | 1 |
| `season_id` | INTEGER | да |  |  |
| `account_id` | INTEGER | да |  |  |
| `member_number` | INTEGER |  |  |  |
| `profile_name` | TEXT |  |  |  |
| `status` | TEXT | да | `'invited'` |  |
| `joined_at` | TEXT |  |  |  |
| `completed_at` | TEXT |  |  |  |
| `created_at` | TEXT | да | `strftime('%Y-%m-%dT%H:%M:%fZ', 'now')` |  |
| `metadata_json` | TEXT |  |  |  |

Внешние ключи:
- (account_id) → `v4_accounts`(id) ON DELETE RESTRICT
- (season_id) → `v4_seasons`(id) ON DELETE RESTRICT

Индексы и уникальность:
- из определения таблицы: UNIQUE-ограничение — (season_id, account_id)
- из определения таблицы: UNIQUE-ограничение — (id, season_id)
- `v4_season_member_number_uq`: уникальный индекс, частичный (WHERE — в миграции) — (season_id, member_number)
- `v4_season_memberships_account_idx`: индекс — (account_id, season_id)

#### `v4_seasons`

_создана в 0001, колонки, ключи или индексы последний раз менялись в 0003_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `id` | INTEGER |  |  | 1 |
| `code` | TEXT | да |  |  |
| `name` | TEXT | да |  |  |
| `status` | TEXT | да | `'draft'` |  |
| `starts_on` | TEXT |  |  |  |
| `ends_on` | TEXT |  |  |  |
| `timezone` | TEXT | да | `'Asia/Shanghai'` |  |
| `theme_key` | TEXT |  |  |  |
| `created_by_account_id` | INTEGER |  |  |  |
| `created_at` | TEXT | да | `strftime('%Y-%m-%dT%H:%M:%fZ', 'now')` |  |
| `updated_at` | TEXT | да | `strftime('%Y-%m-%dT%H:%M:%fZ', 'now')` |  |
| `activated_at` | TEXT |  |  |  |
| `closed_at` | TEXT |  |  |  |
| `archived_at` | TEXT |  |  |  |
| `metadata_json` | TEXT |  |  |  |
| `revision` | INTEGER | да | `1` |  |

Внешние ключи:
- (created_by_account_id) → `v4_accounts`(id) ON DELETE RESTRICT

Индексы и уникальность:
- из определения таблицы: UNIQUE-ограничение — (code)
- `v4_seasons_status_idx`: индекс — (status, updated_at)

### Созданы в 0002 — `0002_local_auth_sessions.sql`

#### `v4_idempotency_keys`

_создана в 0002_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `id` | INTEGER |  |  | 1 |
| `account_id` | INTEGER | да |  |  |
| `operation` | TEXT | да |  |  |
| `idempotency_key` | TEXT | да |  |  |
| `request_hash` | TEXT | да |  |  |
| `response_status` | INTEGER | да |  |  |
| `response_json` | TEXT | да |  |  |
| `created_at` | TEXT | да | `strftime('%Y-%m-%dT%H:%M:%fZ', 'now')` |  |
| `expires_at` | TEXT |  |  |  |

Внешние ключи:
- (account_id) → `v4_accounts`(id) ON DELETE RESTRICT

Индексы и уникальность:
- из определения таблицы: UNIQUE-ограничение — (account_id, operation, idempotency_key)
- `v4_idempotency_expiry_idx`: индекс, частичный (WHERE — в миграции) — (expires_at)

#### `v4_local_credentials`

_создана в 0002_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `identity_id` | INTEGER |  |  | 1 |
| `password_hash` | TEXT | да |  |  |
| `must_change_password` | INTEGER | да | `0` |  |
| `failed_attempts` | INTEGER | да | `0` |  |
| `locked_until` | TEXT |  |  |  |
| `password_changed_at` | TEXT | да | `strftime('%Y-%m-%dT%H:%M:%fZ', 'now')` |  |

Внешние ключи:
- (identity_id) → `v4_external_identities`(id) ON DELETE RESTRICT

Триггеры: `v4_local_credentials_identity_guard`, `v4_local_credentials_provider_guard`

#### `v4_sessions`

_создана в 0002_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `token_hash` | TEXT |  |  | 1 |
| `csrf_token_hash` | TEXT | да |  |  |
| `account_id` | INTEGER | да |  |  |
| `created_at` | TEXT | да |  |  |
| `expires_at` | TEXT | да |  |  |
| `last_seen_at` | TEXT | да |  |  |
| `revoked_at` | TEXT |  |  |  |

Внешние ключи:
- (account_id) → `v4_accounts`(id) ON DELETE RESTRICT

Индексы и уникальность:
- `v4_sessions_account_idx`: индекс — (account_id, revoked_at, expires_at)

### Созданы в 0004 — `0004_max_provider_link_codes.sql`

#### `v4_link_codes`

_создана в 0004, колонки, ключи или индексы последний раз менялись в 0005_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `id` | INTEGER |  |  | 1 |
| `account_id` | INTEGER | да |  |  |
| `provider_code` | TEXT | да |  |  |
| `code_hash` | TEXT | да |  |  |
| `created_at` | TEXT | да | `strftime('%Y-%m-%dT%H:%M:%fZ', 'now')` |  |
| `expires_at` | TEXT | да |  |  |
| `consumed_at` | TEXT |  |  |  |
| `consumed_identity_id` | INTEGER |  |  |  |
| `created_by_account_id` | INTEGER | да |  |  |
| `revoked_at` | TEXT |  |  |  |
| `revoked_by_account_id` | INTEGER |  |  |  |

Внешние ключи:
- (created_by_account_id) → `v4_accounts`(id) ON DELETE RESTRICT
- (consumed_identity_id) → `v4_external_identities`(id) ON DELETE SET NULL
- (provider_code) → `v4_identity_providers`(code) ON DELETE RESTRICT
- (account_id) → `v4_accounts`(id) ON DELETE RESTRICT
- (revoked_by_account_id) → `v4_accounts`(id) ON DELETE RESTRICT

Индексы и уникальность:
- из определения таблицы: UNIQUE-ограничение — (code_hash)
- `v4_link_codes_account_idx`: индекс — (account_id)
- `v4_link_codes_active_per_account_idx`: уникальный индекс, частичный (WHERE — в миграции) — (account_id, provider_code)

### Созданы в 0006 — `0006_cases.sql`

#### `v4_case_inventory`

_создана в 0006_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `season_id` | INTEGER | да |  | 1 |
| `account_id` | INTEGER | да |  | 2 |
| `item_code` | TEXT | да |  | 3 |
| `quantity` | INTEGER | да |  |  |
| `effect_state` | TEXT | да |  |  |

Внешние ключи:
- (season_id, account_id) → `v4_season_memberships`(season_id, account_id) ON DELETE RESTRICT

#### `v4_case_wallets`

_создана в 0006, колонки, ключи или индексы последний раз менялись в 0010_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `season_id` | INTEGER | да |  | 1 |
| `account_id` | INTEGER | да |  | 2 |
| `stars` | INTEGER | да | `0` |  |
| `scans` | INTEGER | да | `0` |  |
| `rep` | INTEGER | да | `0` |  |

Внешние ключи:
- (season_id, account_id) → `v4_season_memberships`(season_id, account_id) ON DELETE RESTRICT

#### `v4_economy_operations`

_создана в 0006, колонки, ключи или индексы последний раз менялись в 0010_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `id` | INTEGER |  |  | 1 |
| `season_id` | INTEGER | да |  |  |
| `account_id` | INTEGER | да |  |  |
| `actor_account_id` | INTEGER | да |  |  |
| `operation` | TEXT | да |  |  |
| `stars_delta` | INTEGER | да |  |  |
| `scans_delta` | INTEGER | да |  |  |
| `rep_delta` | INTEGER | да | `0` |  |
| `stars_after` | INTEGER | да |  |  |
| `scans_after` | INTEGER | да |  |  |
| `rep_after` | INTEGER | да | `0` |  |
| `details_json` | TEXT | да |  |  |
| `created_at` | TEXT | да | `strftime('%Y-%m-%dT%H:%M:%fZ', 'now')` |  |

Внешние ключи:
- (season_id, account_id) → `v4_season_memberships`(season_id, account_id) ON DELETE RESTRICT
- (actor_account_id) → `v4_accounts`(id)

Индексы и уникальность:
- `v4_economy_history_idx`: индекс — (season_id, account_id, id)

Триггеры: `v4_economy_no_delete`, `v4_economy_no_update`

### Созданы в 0007 — `0007_campus_exploration.sql`

#### `v4_campus_cells`

_создана в 0007_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `season_id` | INTEGER | да |  | 1 |
| `cell_lon` | INTEGER | да |  | 2 |
| `cell_lat` | INTEGER | да |  | 3 |
| `opened_at` | TEXT | да | `strftime('%Y-%m-%dT%H:%M:%fZ', 'now')` |  |
| `visits` | INTEGER | да | `1` |  |

Внешние ключи:
- (season_id) → `v4_seasons`(id) ON DELETE RESTRICT

Индексы и уникальность:
- `v4_campus_cells_season_idx`: индекс — (season_id, opened_at)

### Созданы в 0008 — `0008_game_rooms.sql`

#### `v4_game_room_players`

_создана в 0008_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `room_id` | INTEGER | да |  | 1 |
| `account_id` | INTEGER | да |  | 2 |
| `seat` | INTEGER | да |  |  |
| `score` | INTEGER | да | `0` |  |
| `joined_at` | TEXT | да |  |  |

Внешние ключи:
- (account_id) → `v4_accounts`(id)
- (room_id) → `v4_game_rooms`(id) ON DELETE CASCADE

Индексы и уникальность:
- `v4_game_room_players_one_room_uq`: уникальный индекс — (account_id)

#### `v4_game_rooms`

_создана в 0008_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `id` | INTEGER |  |  | 1 |
| `code` | TEXT | да |  |  |
| `game` | TEXT | да |  |  |
| `host_account_id` | INTEGER | да |  |  |
| `status` | TEXT | да |  |  |
| `settings_json` | TEXT | да |  |  |
| `state_json` | TEXT | да | `'{}'` |  |
| `revision` | INTEGER | да | `1` |  |
| `created_at` | TEXT | да |  |  |
| `last_activity_at` | TEXT | да |  |  |

Внешние ключи:
- (host_account_id) → `v4_accounts`(id)

Индексы и уникальность:
- из определения таблицы: UNIQUE-ограничение — (code)
- `v4_game_rooms_activity_idx`: индекс — (last_activity_at)

#### `v4_game_switches`

_создана в 0008_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `game` | TEXT |  |  | 1 |
| `enabled` | INTEGER | да |  |  |
| `updated_by_account_id` | INTEGER | да |  |  |
| `updated_at` | TEXT | да |  |  |

Внешние ключи:
- (updated_by_account_id) → `v4_accounts`(id)

### Созданы в 0010 — `0010_diary_ratings.sql`

#### `v4_diary_ratings`

_создана в 0010_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `season_id` | INTEGER | да |  | 1 |
| `account_id` | INTEGER | да |  | 2 |
| `entry_date` | TEXT | да |  | 3 |
| `stars` | INTEGER | да |  |  |
| `bonus` | INTEGER | да |  |  |
| `scan_granted` | INTEGER | да | `0` |  |
| `revision` | INTEGER | да | `1` |  |
| `rated_by_account_id` | INTEGER | да |  |  |
| `rated_at` | TEXT | да | `strftime('%Y-%m-%dT%H:%M:%fZ', 'now')` |  |

Внешние ключи:
- (season_id, account_id) → `v4_season_memberships`(season_id, account_id) ON DELETE RESTRICT
- (rated_by_account_id) → `v4_accounts`(id)

Индексы и уникальность:
- `v4_diary_ratings_day_idx`: индекс — (season_id, entry_date)

### Созданы в 0011 — `0011_shop.sql`

#### `v4_cosmetics_equipped`

_создана в 0011_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `season_id` | INTEGER | да |  | 1 |
| `account_id` | INTEGER | да |  | 2 |
| `slot` | TEXT | да |  | 3 |
| `item_code` | TEXT | да |  |  |

Внешние ключи:
- (season_id, account_id) → `v4_season_memberships`(season_id, account_id) ON DELETE RESTRICT

#### `v4_shop_stock`

_создана в 0011_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `season_id` | INTEGER | да |  | 1 |
| `shop_day` | TEXT | да |  | 2 |
| `item_code` | TEXT | да |  | 3 |
| `stock` | INTEGER | да |  |  |
| `sold` | INTEGER | да | `0` |  |

Внешние ключи:
- (season_id) → `v4_seasons`(id) ON DELETE RESTRICT

### Созданы в 0012 — `0012_meetings.sql`

#### `v4_meet_pairs`

_создана в 0012_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `season_id` | INTEGER | да |  | 1 |
| `meet_day` | TEXT | да |  | 2 |
| `account_low` | INTEGER | да |  | 3 |
| `account_high` | INTEGER | да |  | 4 |

Внешние ключи:
- (season_id) → `v4_seasons`(id) ON DELETE RESTRICT

#### `v4_puzzle_pieces`

_создана в 0012_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `season_id` | INTEGER | да |  | 1 |
| `account_id` | INTEGER | да |  | 2 |
| `puzzle_code` | TEXT | да |  | 3 |
| `piece` | INTEGER | да |  | 4 |
| `obtained_at` | TEXT | да | `strftime('%Y-%m-%dT%H:%M:%fZ', 'now')` |  |

Внешние ключи:
- (season_id, account_id) → `v4_season_memberships`(season_id, account_id) ON DELETE RESTRICT

### Созданы в 0013 — `0013_virus.sql`

#### `v4_virus_state`

_создана в 0013_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `season_id` | INTEGER | да |  | 1 |
| `account_id` | INTEGER | да |  | 2 |
| `infected_until` | TEXT |  |  |  |
| `firewall_until` | TEXT |  |  |  |

Внешние ключи:
- (season_id, account_id) → `v4_season_memberships`(season_id, account_id) ON DELETE RESTRICT

### Созданы в 0014 — `0014_map_marks.sql`

#### `v4_map_mark_quota`

_создана в 0014_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `season_id` | INTEGER | да |  | 1 |
| `account_id` | INTEGER | да |  | 2 |
| `mark_day` | TEXT | да |  | 3 |
| `used` | INTEGER | да |  |  |

Внешние ключи:
- (season_id, account_id) → `v4_season_memberships`(season_id, account_id) ON DELETE RESTRICT

#### `v4_map_mark_votes`

_создана в 0014_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `mark_id` | INTEGER | да |  | 1 |
| `account_id` | INTEGER | да |  | 2 |

Внешние ключи:
- (account_id) → `v4_accounts`(id) ON DELETE RESTRICT
- (mark_id) → `v4_map_marks`(id) ON DELETE CASCADE

#### `v4_map_marks`

_создана в 0014_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `id` | INTEGER |  |  | 1 |
| `season_id` | INTEGER | да |  |  |
| `cell_lon` | INTEGER | да |  |  |
| `cell_lat` | INTEGER | да |  |  |
| `template_code` | TEXT | да |  |  |
| `word_code` | TEXT | да |  |  |
| `placed_hour` | TEXT | да |  |  |
| `expires_at` | TEXT | да |  |  |
| `useful` | INTEGER | да | `0` |  |
| `hidden_at` | TEXT |  |  |  |
| `hidden_by_account_id` | INTEGER |  |  |  |

Внешние ключи:
- (hidden_by_account_id) → `v4_accounts`(id) ON DELETE RESTRICT
- (season_id) → `v4_seasons`(id) ON DELETE RESTRICT

Индексы и уникальность:
- `v4_map_marks_season_idx`: индекс — (season_id, expires_at)

### Созданы в 0015 — `0015_story.sql`

#### `v4_story_solved`

_создана в 0015_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `season_id` | INTEGER | да |  | 1 |
| `fragment_code` | TEXT | да |  | 2 |
| `solved_day` | TEXT | да |  |  |

Внешние ключи:
- (season_id) → `v4_seasons`(id) ON DELETE RESTRICT

#### `v4_story_state`

_создана в 0015_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `season_id` | INTEGER |  |  | 1 |
| `started_day` | TEXT | да |  |  |

Внешние ключи:
- (season_id) → `v4_seasons`(id) ON DELETE RESTRICT

### Созданы в 0016 — `0016_capture.sql`

#### `v4_capture_factions`

_создана в 0016_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `season_id` | INTEGER | да |  | 1 |
| `account_id` | INTEGER | да |  | 2 |
| `faction` | TEXT | да |  |  |

Внешние ключи:
- (season_id, account_id) → `v4_season_memberships`(season_id, account_id) ON DELETE RESTRICT

Индексы и уникальность:
- `v4_capture_factions_faction_idx`: индекс — (season_id, faction)

#### `v4_capture_holds`

_создана в 0016_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `id` | INTEGER |  |  | 1 |
| `season_id` | INTEGER | да |  |  |
| `point_code` | TEXT | да |  |  |
| `faction` | TEXT | да |  |  |
| `since` | TEXT | да |  |  |
| `until` | TEXT |  |  |  |

Внешние ключи:
- (season_id, point_code) → `v4_capture_points`(season_id, point_code) ON DELETE RESTRICT

Индексы и уникальность:
- `v4_capture_holds_open_idx`: индекс — (season_id, point_code, until)

#### `v4_capture_points`

_создана в 0016_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `season_id` | INTEGER | да |  | 1 |
| `point_code` | TEXT | да |  | 2 |
| `lon` | REAL | да |  |  |
| `lat` | REAL | да |  |  |
| `confirmed_at` | TEXT | да |  |  |
| `owner` | TEXT |  |  |  |
| `level` | INTEGER | да | `0` |  |
| `changed_at` | TEXT |  |  |  |

Внешние ключи:
- (season_id) → `v4_seasons`(id) ON DELETE RESTRICT

#### `v4_capture_state`

_создана в 0016, колонки, ключи или индексы последний раз менялись в 0018_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `season_id` | INTEGER |  |  | 1 |
| `enabled` | INTEGER | да | `0` |  |
| `updated_by_account_id` | INTEGER |  |  |  |
| `updated_at` | TEXT |  |  |  |
| `war` | INTEGER | да | `1` |  |
| `war_finished_at` | TEXT |  |  |  |

Внешние ключи:
- (updated_by_account_id) → `v4_accounts`(id) ON DELETE RESTRICT
- (season_id) → `v4_seasons`(id) ON DELETE RESTRICT

### Созданы в 0017 — `0017_capture_duels.sql`

#### `v4_capture_bonus`

_создана в 0017_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `season_id` | INTEGER | да |  | 1 |
| `faction` | TEXT | да |  | 2 |
| `points` | INTEGER | да | `0` |  |

Внешние ключи:
- (season_id) → `v4_seasons`(id) ON DELETE RESTRICT

#### `v4_capture_duel_quota`

_создана в 0017_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `season_id` | INTEGER | да |  | 1 |
| `account_id` | INTEGER | да |  | 2 |
| `duel_day` | TEXT | да |  | 3 |
| `used` | INTEGER | да |  |  |

Внешние ключи:
- (season_id, account_id) → `v4_season_memberships`(season_id, account_id) ON DELETE RESTRICT

#### `v4_capture_duels`

_создана в 0017_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `id` | INTEGER |  |  | 1 |
| `season_id` | INTEGER | да |  |  |
| `a_account_id` | INTEGER | да |  |  |
| `b_account_id` | INTEGER | да |  |  |
| `kind` | TEXT | да |  |  |
| `point_code` | TEXT |  |  |  |
| `state_json` | TEXT | да |  |  |
| `status` | TEXT | да | `'active'` |  |
| `created_at` | TEXT | да |  |  |
| `updated_at` | TEXT | да |  |  |
| `finished_at` | TEXT |  |  |  |

Внешние ключи:
- (b_account_id) → `v4_accounts`(id) ON DELETE RESTRICT
- (a_account_id) → `v4_accounts`(id) ON DELETE RESTRICT
- (season_id) → `v4_seasons`(id) ON DELETE RESTRICT

Индексы и уникальность:
- `v4_capture_duels_a_idx`: индекс — (a_account_id, status)
- `v4_capture_duels_b_idx`: индекс — (b_account_id, status)

### Созданы в 0018 — `0018_capture_war.sql`

#### `v4_capture_activity`

_создана в 0018_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `season_id` | INTEGER | да |  | 1 |
| `account_id` | INTEGER | да |  | 2 |
| `activity_day` | TEXT | да |  | 3 |

Внешние ключи:
- (season_id, account_id) → `v4_season_memberships`(season_id, account_id) ON DELETE RESTRICT

#### `v4_capture_daily_bonus`

_создана в 0018_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `season_id` | INTEGER | да |  | 1 |
| `faction` | TEXT | да |  | 2 |
| `bonus_day` | TEXT | да |  | 3 |
| `points` | INTEGER | да | `0` |  |

Внешние ключи:
- (season_id) → `v4_seasons`(id) ON DELETE RESTRICT

#### `v4_capture_days`

_создана в 0018_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `season_id` | INTEGER | да |  | 1 |
| `war` | INTEGER | да |  | 2 |
| `day` | TEXT | да |  | 3 |
| `winners_json` | TEXT | да |  |  |
| `rewarded` | INTEGER | да | `0` |  |
| `settled_at` | TEXT | да |  |  |

Внешние ключи:
- (season_id) → `v4_seasons`(id) ON DELETE RESTRICT

#### `v4_capture_effects`

_создана в 0018_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `id` | INTEGER |  |  | 1 |
| `season_id` | INTEGER | да |  |  |
| `faction` | TEXT | да |  |  |
| `ability` | TEXT | да |  |  |
| `target` | TEXT | да | `''` |  |
| `since` | TEXT | да |  |  |
| `until` | TEXT | да |  |  |

Внешние ключи:
- (season_id) → `v4_seasons`(id) ON DELETE RESTRICT

Индексы и уникальность:
- `v4_capture_effects_live_idx`: индекс — (season_id, until)

#### `v4_capture_point_moves`

_создана в 0018_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `season_id` | INTEGER | да |  | 1 |
| `point_code` | TEXT | да |  | 2 |
| `move_day` | TEXT | да |  | 3 |
| `moves` | INTEGER | да |  |  |

Внешние ключи:
- (season_id) → `v4_seasons`(id) ON DELETE RESTRICT

#### `v4_capture_pools`

_создана в 0018_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `id` | INTEGER |  |  | 1 |
| `season_id` | INTEGER | да |  |  |
| `faction` | TEXT | да |  |  |
| `ability` | TEXT | да |  |  |
| `target` | TEXT | да | `''` |  |
| `collected` | INTEGER | да | `0` |  |
| `created_at` | TEXT | да |  |  |

Внешние ключи:
- (season_id) → `v4_seasons`(id) ON DELETE RESTRICT

Индексы и уникальность:
- из определения таблицы: UNIQUE-ограничение — (season_id, faction, ability, target)

#### `v4_capture_wars`

_создана в 0018_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `season_id` | INTEGER | да |  | 1 |
| `number` | INTEGER | да |  | 2 |
| `finished_at` | TEXT | да |  |  |
| `winners_json` | TEXT | да |  |  |
| `scores_json` | TEXT | да |  |  |

Внешние ключи:
- (season_id) → `v4_seasons`(id) ON DELETE RESTRICT

### Созданы в 0019 — `0019_royale.sql`

#### `v4_royale_answers`

_создана в 0019_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `game_id` | INTEGER | да |  | 1 |
| `round` | INTEGER | да |  | 2 |
| `account_id` | INTEGER | да |  | 3 |
| `choice` | INTEGER | да |  |  |
| `ms` | INTEGER | да |  |  |
| `correct` | INTEGER | да |  |  |

Внешние ключи:
- (game_id) → `v4_royale_games`(id) ON DELETE CASCADE

#### `v4_royale_games`

_создана в 0019_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `id` | INTEGER |  |  | 1 |
| `season_id` | INTEGER | да |  |  |
| `host_account_id` | INTEGER | да |  |  |
| `status` | TEXT | да |  |  |
| `round` | INTEGER | да | `0` |  |
| `state_json` | TEXT | да |  |  |
| `results_json` | TEXT | да | `'[]'` |  |
| `purged` | INTEGER | да | `0` |  |
| `created_at` | TEXT | да |  |  |
| `updated_at` | TEXT | да |  |  |
| `finished_at` | TEXT |  |  |  |

Внешние ключи:
- (host_account_id) → `v4_accounts`(id) ON DELETE RESTRICT
- (season_id) → `v4_seasons`(id) ON DELETE RESTRICT

Индексы и уникальность:
- `v4_royale_games_season_idx`: индекс — (season_id, status)

#### `v4_royale_players`

_создана в 0019_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `game_id` | INTEGER | да |  | 1 |
| `account_id` | INTEGER | да |  | 2 |
| `joined_at` | TEXT | да |  |  |
| `alive` | INTEGER | да | `1` |  |
| `out_round` | INTEGER |  |  |  |
| `revived` | INTEGER | да | `0` |  |
| `total_ms` | INTEGER | да | `0` |  |

Внешние ключи:
- (account_id) → `v4_accounts`(id) ON DELETE RESTRICT
- (game_id) → `v4_royale_games`(id) ON DELETE CASCADE

#### `v4_royale_prize_days`

_создана в 0019_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `season_id` | INTEGER | да |  | 1 |
| `account_id` | INTEGER | да |  | 2 |
| `prize_day` | TEXT | да |  | 3 |

Внешние ключи:
- (season_id, account_id) → `v4_season_memberships`(season_id, account_id) ON DELETE RESTRICT

#### `v4_royale_votes`

_создана в 0019_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `game_id` | INTEGER | да |  | 1 |
| `round` | INTEGER | да |  | 2 |
| `account_id` | INTEGER | да |  | 3 |
| `surprise` | TEXT | да |  |  |

Внешние ключи:
- (game_id) → `v4_royale_games`(id) ON DELETE CASCADE

### Созданы в 0020 — `0020_smuggle.sql`

#### `v4_smuggle_prize_days`

_создана в 0020_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `season_id` | INTEGER | да |  | 1 |
| `account_id` | INTEGER | да |  | 2 |
| `prize_day` | TEXT | да |  | 3 |

Внешние ключи:
- (season_id, account_id) → `v4_season_memberships`(season_id, account_id) ON DELETE RESTRICT

### Созданы в 0021 — `0021_agent.sql`

#### `v4_agent_links`

_создана в 0021_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `season_id` | INTEGER | да |  | 1 |
| `agent_account_id` | INTEGER | да |  | 2 |
| `target_account_id` | INTEGER | да |  |  |
| `day` | TEXT | да |  |  |
| `mission` | TEXT | да |  |  |
| `asks` | INTEGER | да | `0` |  |
| `asking` | INTEGER | да | `0` |  |
| `known` | INTEGER | да | `0` |  |
| `since` | TEXT | да |  |  |

Внешние ключи:
- (season_id, target_account_id) → `v4_season_memberships`(season_id, account_id) ON DELETE RESTRICT
- (season_id, agent_account_id) → `v4_season_memberships`(season_id, account_id) ON DELETE RESTRICT

Индексы и уникальность:
- `v4_agent_links_target_idx`: индекс — (season_id, target_account_id)

#### `v4_agent_players`

_создана в 0021_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `season_id` | INTEGER | да |  | 1 |
| `account_id` | INTEGER | да |  | 2 |
| `joined_at` | TEXT | да |  |  |
| `points` | INTEGER | да | `0` |  |
| `missions` | INTEGER | да | `0` |  |
| `reveals` | INTEGER | да | `0` |  |
| `refusals` | INTEGER | да | `0` |  |
| `excluded` | INTEGER | да | `0` |  |
| `guessed_day` | TEXT |  |  |  |
| `news_json` | TEXT |  |  |  |

Внешние ключи:
- (season_id, account_id) → `v4_season_memberships`(season_id, account_id) ON DELETE RESTRICT

#### `v4_agent_shifts`

_создана в 0021_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `season_id` | INTEGER | да |  | 1 |
| `number` | INTEGER | да |  | 2 |
| `finished_at` | TEXT | да |  |  |
| `results_json` | TEXT | да |  |  |

Внешние ключи:
- (season_id) → `v4_seasons`(id) ON DELETE RESTRICT

#### `v4_agent_state`

_создана в 0021_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `season_id` | INTEGER |  |  | 1 |
| `shift` | INTEGER | да | `1` |  |
| `running` | INTEGER | да | `0` |  |
| `day` | TEXT |  |  |  |
| `updated_by_account_id` | INTEGER |  |  |  |
| `updated_at` | TEXT | да |  |  |

Внешние ключи:
- (updated_by_account_id) → `v4_accounts`(id) ON DELETE RESTRICT
- (season_id) → `v4_seasons`(id) ON DELETE RESTRICT

### Созданы в 0022 — `0022_zombie.sql`

#### `v4_zombie_games`

_создана в 0022_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `id` | INTEGER |  |  | 1 |
| `season_id` | INTEGER | да |  |  |
| `host_account_id` | INTEGER | да |  |  |
| `status` | TEXT | да |  |  |
| `state_json` | TEXT | да |  |  |
| `results_json` | TEXT | да | `'{}'` |  |
| `purged` | INTEGER | да | `0` |  |
| `created_at` | TEXT | да |  |  |
| `updated_at` | TEXT | да |  |  |
| `started_at` | TEXT |  |  |  |
| `ends_at` | TEXT |  |  |  |
| `finished_at` | TEXT |  |  |  |

Внешние ключи:
- (host_account_id) → `v4_accounts`(id) ON DELETE RESTRICT
- (season_id) → `v4_seasons`(id) ON DELETE RESTRICT

Индексы и уникальность:
- `v4_zombie_games_season_idx`: индекс — (season_id, status)

#### `v4_zombie_players`

_создана в 0022_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `game_id` | INTEGER | да |  | 1 |
| `account_id` | INTEGER | да |  | 2 |
| `joined_at` | TEXT | да |  |  |
| `code` | TEXT | да |  |  |
| `side` | TEXT | да | `'human'` |  |
| `starter` | INTEGER | да | `0` |  |
| `turned_at` | TEXT |  |  |  |
| `last_tag_at` | TEXT |  |  |  |
| `tags` | INTEGER | да | `0` |  |
| `vaccinated` | INTEGER | да | `0` |  |
| `immune_until` | TEXT |  |  |  |

Внешние ключи:
- (account_id) → `v4_accounts`(id) ON DELETE RESTRICT
- (game_id) → `v4_zombie_games`(id) ON DELETE CASCADE

Индексы и уникальность:
- из определения таблицы: UNIQUE-ограничение — (game_id, code)

#### `v4_zombie_prize_days`

_создана в 0022_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `season_id` | INTEGER | да |  | 1 |
| `account_id` | INTEGER | да |  | 2 |
| `prize_day` | TEXT | да |  | 3 |

Внешние ключи:
- (season_id, account_id) → `v4_season_memberships`(season_id, account_id) ON DELETE RESTRICT

### Созданы в 0023 — `0023_sabotage.sql`

#### `v4_sabotage_games`

_создана в 0023_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `id` | INTEGER |  |  | 1 |
| `season_id` | INTEGER | да |  |  |
| `host_account_id` | INTEGER | да |  |  |
| `status` | TEXT | да |  |  |
| `state_json` | TEXT | да |  |  |
| `results_json` | TEXT | да | `'{}'` |  |
| `purged` | INTEGER | да | `0` |  |
| `created_at` | TEXT | да |  |  |
| `updated_at` | TEXT | да |  |  |
| `started_at` | TEXT |  |  |  |
| `ends_at` | TEXT |  |  |  |
| `finished_at` | TEXT |  |  |  |

Внешние ключи:
- (host_account_id) → `v4_accounts`(id) ON DELETE RESTRICT
- (season_id) → `v4_seasons`(id) ON DELETE RESTRICT

Индексы и уникальность:
- `v4_sabotage_games_season_idx`: индекс — (season_id, status)

#### `v4_sabotage_players`

_создана в 0023_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `game_id` | INTEGER | да |  | 1 |
| `account_id` | INTEGER | да |  | 2 |
| `joined_at` | TEXT | да |  |  |
| `code` | TEXT | да |  |  |
| `role` | TEXT | да | `'crew'` |  |
| `captain` | INTEGER | да | `0` |  |
| `meetings_left` | INTEGER | да | `0` |  |
| `alive` | INTEGER | да | `1` |  |
| `ejected` | INTEGER | да | `0` |  |
| `out_at` | TEXT |  |  |  |
| `last_kill_at` | TEXT |  |  |  |
| `tasks_json` | TEXT | да | `'[]'` |  |
| `done_json` | TEXT | да | `'[]'` |  |

Внешние ключи:
- (account_id) → `v4_accounts`(id) ON DELETE RESTRICT
- (game_id) → `v4_sabotage_games`(id) ON DELETE CASCADE

Индексы и уникальность:
- из определения таблицы: UNIQUE-ограничение — (game_id, code)

#### `v4_sabotage_prize_days`

_создана в 0023_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `season_id` | INTEGER | да |  | 1 |
| `account_id` | INTEGER | да |  | 2 |
| `prize_day` | TEXT | да |  | 3 |

Внешние ключи:
- (season_id, account_id) → `v4_season_memberships`(season_id, account_id) ON DELETE RESTRICT

#### `v4_sabotage_votes`

_создана в 0023_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `game_id` | INTEGER | да |  | 1 |
| `meeting` | INTEGER | да |  | 2 |
| `account_id` | INTEGER | да |  | 3 |
| `choice` | INTEGER | да |  |  |

Внешние ключи:
- (game_id) → `v4_sabotage_games`(id) ON DELETE CASCADE

### Созданы в 0025 — `0025_smuggle_market.sql`

#### `v4_market_days`

_создана в 0025_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `season_id` | INTEGER | да |  | 1 |
| `day` | TEXT | да |  | 2 |
| `settled_at` | TEXT | да |  |  |
| `results_json` | TEXT | да |  |  |

Внешние ключи:
- (season_id) → `v4_seasons`(id) ON DELETE RESTRICT

#### `v4_market_players`

_создана в 0025_

| Колонка | Тип | NOT NULL | По умолчанию | PK |
|---|---|---|---|---|
| `season_id` | INTEGER | да |  | 1 |
| `day` | TEXT | да |  | 2 |
| `account_id` | INTEGER | да |  | 3 |
| `joined_at` | TEXT | да |  |  |
| `role` | TEXT | да | `'merchant'` |  |
| `money` | INTEGER | да |  |  |
| `goods_json` | TEXT | да |  |  |
| `code` | TEXT | да |  |  |
| `traded` | INTEGER | да | `0` |  |
| `last_inspected_at` | TEXT |  |  |  |
| `last_inspection_at` | TEXT |  |  |  |
| `news_json` | TEXT |  |  |  |

Внешние ключи:
- (season_id, account_id) → `v4_season_memberships`(season_id, account_id) ON DELETE RESTRICT

Индексы и уникальность:
- из определения таблицы: UNIQUE-ограничение — (season_id, day, code)
