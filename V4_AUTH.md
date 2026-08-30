# ZHIDAO V4 — локальный вход и серверные роли

V4 API не требует Telegram. Внутренний аккаунт связывается с identity provider
`local`; Telegram и будущий MAX остаются дополнительными способами входа.

## Защитные свойства

- пароли хешируются `scrypt` с индивидуальной случайной солью;
- пять неверных паролей блокируют credential на 15 минут;
- login дополнительно ограничен по IP, по умолчанию 120 попыток в минуту;
- в SQLite сохраняются только SHA-256-хеши session/CSRF-токенов;
- session cookie — `HttpOnly`, `Secure` по умолчанию и `SameSite=Lax`;
- изменения требуют совпадающих CSRF cookie и `X-CSRF-Token`;
- роли загружаются из БД на каждом запросе, поэтому отзыв действует сразу;
- создание сезона разрешено только глобальному `system_admin`;
- `X-Idempotency-Key` исключает двойное создание при повторной отправке;
- входы, выходы, ошибки входа и создание сезона попадают в append-only AuditLog.

## 1. Первичный bootstrap

Команда интерактивно спрашивает пароль и не принимает его аргументом командной
строки. По умолчанию атомарно создаются первый `system_admin` и черновик
`hainan-v4`.

```powershell
New-Item -ItemType Directory -Force .codex-tmp\v4-local | Out-Null
.\.venv-travel\Scripts\python.exe -m zhidao_v4.bootstrap `
  --db .codex-tmp\v4-local\zhidao.db `
  --username architect `
  --display-name "Architect"
```

Повторный bootstrap запрещён, если глобальный системный администратор уже
существует.

## 2. Локальный запуск API

```powershell
$env:ZHIDAO_V4_DB_PATH = (Join-Path (Get-Location) '.codex-tmp\v4-local\zhidao.db')
$env:ZHIDAO_V4_COOKIE_SECURE = '0'
.\.venv-travel\Scripts\python.exe -m uvicorn zhidao_v4.api:create_app `
  --factory --host 127.0.0.1 --port 8770
```

`ZHIDAO_V4_COOKIE_SECURE=0` допустим только для локального HTTP. На тестовом и
production-сервере cookie обязана оставаться `Secure`.

Проверка: `http://127.0.0.1:8770/api/v4/health`.

## 3. Контракт входа

```text
POST /api/v4/auth/login
GET  /api/v4/auth/me
POST /api/v4/auth/logout
GET  /api/v4/seasons
POST /api/v4/seasons
```

Для мутаций клиент передаёт session cookie, CSRF cookie,
`X-CSRF-Token` и уникальный `X-Idempotency-Key`. Пароль и токены не должны
попадать в URL, логи или localStorage.

Сейчас bootstrap создаёт только системного администратора. Массовая выдача
детских аккаунтов будет отдельным операторским сценарием после решения о
первичных логинах и восстановлении доступа.
