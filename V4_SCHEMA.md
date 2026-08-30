# ZHIDAO V4 — фундамент схемы данных

V4-миграции создают новый namespace таблиц `v4_*` рядом с Legacy Travel. Они
не переименовывают, не удаляют и не заполняют старые таблицы.

## Состав

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

V4-миграции пока не запускаются автоматически при импорте Legacy API. Это
намеренная граница до появления первых V4-сервисов и тестового сервера.
