# ZHIDAO V4 — фундамент схемы данных

V4-миграции создают новый namespace таблиц `v4_*` рядом с Legacy Travel. Они
не переименовывают, не удаляют и не заполняют старые таблицы.

## Состав

Дополнение 2026-09-08: миграция **0006** добавляет сезонные `v4_case_wallets`,
`v4_case_inventory` и неизменяемый `v4_economy_operations`. Составные внешние
ключи связывают прогресс с `(season_id, account_id)` участия, не с MAX ID.
Правила, REST-контракт и проверка — `V4_CASES.md`. MAX уже реализован через
миграции 0004–0005; упоминания «будущего MAX» ниже относятся к исходному плану.

```text
Account ──< ExternalIdentity >── IdentityProvider
   │
   ├──< RoleAssignment >── Role
   │          └── Season (необязательный scope)
   │
   └──< SeasonMembership >── Season ──< Group
                    └──────────────< GroupMembership

AuditLog ── actor Account / Season / произвольная сущность

LocalIdentity ── Credential
Account ──< Session
Account ──< IdempotencyKey
```

- `v4_accounts` — стабильная внутренняя личность, не зависящая от мессенджера;
- `v4_external_identities` — `local`, Telegram и будущий MAX;
- `v4_roles` и `v4_role_assignments` — глобальные и сезонные назначения ролей;
- `v4_seasons` и `v4_season_memberships` — участие аккаунта в конкретной
  поездке;
- `v4_groups` и `v4_group_memberships` — отряды внутри сезона;
- `v4_audit_log` — неизменяемый журнал административных действий;
- `v4_local_credentials` — только scrypt-хеши паролей и состояние блокировки;
- `v4_sessions` — SHA-256-хеши сессионных и CSRF-токенов;
- `v4_idempotency_keys` — защита критических POST-запросов от повтора;
- `v4_seasons.revision` — optimistic locking для формы Архитектора;
- `v4_schema_migrations` — версии и SHA-256 исходных SQL-файлов.

Активный участник может состоять только в одном отряде сезона. Оператор может
быть привязан к нескольким отрядам. Одна внешняя учётная запись не может быть
связана с двумя аккаунтами ZHIDAO.

Каждое runtime-подключение к SQLite обязано выполнять
`PRAGMA foreign_keys=ON`; helper `zhidao_v4.db.connect_database` делает это
автоматически.

## Локальное применение

```powershell
.\.venv-travel\Scripts\python.exe -m zhidao_v4.migrations `
  --db .codex-tmp\v4-local\zhidao.db
```

Повторный запуск безопасен и не применяет уже зарегистрированные миграции.
Если содержимое применённого SQL-файла изменилось, запуск останавливается из-за
несовпадения checksum. Исправления схемы нужно добавлять новым последовательным
файлом, а не редактировать уже применённую миграцию.

V4-миграции не запускаются автоматически при импорте Legacy API. Собственный
V4 API применяет их при создании приложения; это не затрагивает запуск
пекинского backend.
