# ZHIDAO Protocol — запусковая фиксация

Дата: 2026-06-17
Коммит: `d01875e` (`main`, синхронизирован с `origin/main`)
Статус: функционально готово к запуску, дальнейшие изменения делать как точечные hotfix.

## Проверка репозитория

Локальная ветка была fast-forward синхронизирована с `origin/main`.

Проверки, выполненные 2026-06-17:

- `python -m py_compile zhidao_api_ready.py zhidao_bot_ready.py` — успешно.
- `node --check js/*.js` — успешно.
- `git diff --check` — успешно.
- `git status --short --branch` — чисто, `main...origin/main`.

## Что добавлено к текущей версии

### 1. Дневник Архитектора

Добавлен отдельный слой прогресс-лора:

- фронт: `js/architect-diary.js`;
- backend: таблица `architect_diary_unlocks`;
- API: `GET /api/diary/architect/{telegram_id}`, `POST /api/diary/architect/unlock`;
- разблокировки привязаны к игровым действиям: экономика, магазин, стирка, контракт, рейд, событие Architect и т.п.;
- попап Архитектора показывает новые записи с изображением и typewriter-эффектом.

Назначение: давать игроку ощущение прогресса и сюжетной обратной связи без прямого влияния на экономику.

### 2. Gift-code live event

Добавлена система кодов-наград с попапом Михаила Юрьевича:

- фронт: `js/gift-code.js`;
- backend: `gift_codes`, `gift_code_redemptions`;
- API:
  - `GET /api/gift-code/active`;
  - `POST /api/gift-code/redeem`;
  - `GET /api/admin/gift-code`;
  - `POST /api/admin/gift-code`;
- пользовательский фронт опрашивает активный код примерно раз в 10 секунд;
- активное окно показа кода ограничено, код можно погасить один раз на пользователя;
- админка умеет создавать код, награду, лимит использований, заметку и время показа.

Назначение: управляемые живые раздачи наград во время поездки.

### 3. Инструкция внутри приложения

Добавлен интерактивный гайд с Юлией:

- фронт: `js/instruction.js`;
- режимы: текстовая инструкция и пошаговый tour;
- tour подсвечивает реальные разделы приложения и ведёт пользователя по интерфейсу;
- добавлены изображения Юлии для разных состояний.

Назначение: снизить нагрузку на админов при первом запуске у детей.

### 4. Wild AI Breach

Система Wild AI Breach выросла в отдельный режим/ивент:

- фронт: `js/wild-ai-breach.js`, расширения в `js/architect-event.js`;
- backend: отдельные настройки `wildai_event`, `wildai_breach`;
- API:
  - `POST /api/admin/wildai-breach`;
  - `POST /api/admin/wildai-event`;
  - `POST /api/events/wildai/create`;
- добавлены отдельные лобби, фазы, медиа, музыка, поражение/победа;
- Architect Protocol и Wild AI Breach разведены по event slots, чтобы не блокировать друг друга одним active-event lock;
- есть UI-хаос: баннер, подмена/перемешивание подписей, визуальная деградация интерфейса.

Назначение: аварийно-сюжетный режим поверх BlackWall/ивентов.

### 5. Карта кампуса

Карта кампуса теперь полноценный раздел:

- фронт: `js/campus-map.js`;
- backend: `GET /api/campus-map`, `POST /api/admin/campus-map`;
- фильтры по категориям: учёба, еда, жильё, спорт, важное, сбор;
- поиск, избранное, точки, подписи, попап по месту;
- режим редактирования для Архитектора;
- поддержка тем и отдельных map assets.

Важно: правки точек через редактор должны попадать в backend, иначе они останутся локальными/кэшированными.

### 6. Контракты

Доска поручений стала ближе к боевой версии:

- вкладки: открытые, мои, спорные;
- фильтры по категориям;
- анонимное публичное создание при сохранении полной видимости для админов;
- состояния: `open`, `accepted`, `submitted`, `completed`, `cancelled`, `disputed`, `expired`;
- авто-истечение открытых контрактов;
- авто-подтверждение submitted-контрактов после таймера;
- админский мониторинг контрактов, подарков, подозрительных пар и пересечений gift/contract.

Назначение: P2P-экономика без публичного раскрытия кошельков и без возможности незаметно отмывать ценность.

### 7. Переклички, стирка, вода

Переклички:

- типы: `morning`, `evening`, `manual`;
- ручные сессии генерируются отдельно и могут запускаться много раз;
- бот отправляет кнопки, API хранит статусы, админы видят обзор;
- штрафы проходят через защитные механики: иммунитет, броня, карточные пассивки.

Стирка/вода:

- расписания вынесены в `laundry_schedule`, `water_schedule`;
- бронирования в `laundry_bookings`, `water_bookings`;
- есть capacity, отмена пользователем и админская отмена;
- пользователь может менять слот, старая бронь удаляется.

### 8. Экономика, пассивки и мониторинг

Сохраняется разделение:

- `points` = `★`, расходуемая валюта;
- `rep_score` = REP, публичная репутация;
- рейтинг строится по REP, не по кошельку.

Усилены:

- `economy_log`;
- админский economy report;
- подарки с дневным лимитом;
- мониторинг gift pairs и contract/gift overlap;
- карточные и имплантные пассивки;
- Qilin с diminishing returns;
- Panda cashback без арбитража;
- Zhongli/Fox/Sea/Star/Pyro/Fairy/Literature/Forest/Moon пассивки.

Бот теперь использует `API_INTERNAL_TOKEN` для денежных операций через `/api/internal/points/add`, но всё ещё читает базу напрямую для справочных задач. Это нормальное промежуточное состояние.

## Стабильность и backend

Текущая схема backend:

- FastAPI + SQLite WAL;
- `get_conn()` использует thread-local persistent connection;
- `db_write()` сериализует записи через `DB_WRITE_LOCK`;
- запись выполняется в single-worker `DB_WRITE_EXECUTOR`;
- `wal_autocheckpoint=0`, checkpoint только PASSIVE и вне активного write-lock;
- ошибки пишутся и в stdout/journald, и в `ZHIDAO_API_ERROR_LOG`.

Это фактическая рабочая архитектура на 2026-06-17. Не менять её без замеров.

Критическое правило: перед деплоем backend с GitHub сравнить серверный `/root/zhidao_api.py` с `zhidao_api_ready.py`. После Второго датакрэша сервер мог жить на known-good версии, и слепой deploy может откатить рабочие SQLite-фиксы.

## Безопасность

Сделано:

- HMAC-проверка Telegram initData;
- freshness check через `TELEGRAM_AUTH_MAX_AGE_SECONDS`;
- `API_INTERNAL_TOKEN` для внутренних вызовов бота;
- in-process rate limit;
- `RATE_LIMIT_MAX_REQUESTS_PER_SECOND` для пользователя/идентичности;
- `RATE_LIMIT_MAX_REQUESTS_PER_IP` для общей нагрузки с одного IP/NAT;
- админские действия проверяются на backend.

Критический env на сервере:

- `TELEGRAM_AUTH_REQUIRED=1`;
- `BOT_TOKEN`;
- `API_INTERNAL_TOKEN`;
- `ADMIN_IDS`;
- `ARCHITECT_IDS`;
- `EXPECTED_STUDENTS_FILE`.

Важно: в коде дефолт `TELEGRAM_AUTH_REQUIRED` остаётся `0`, поэтому production держится именно на systemd env.

## Конфигурация frontend на 2026-06-17

В `js/config.js`:

- `APP_LAUNCH_LOCK_ENABLED = false`;
- `ARCHITECT_EVENT_ENABLED = false`;
- `APP_FEATURE_FREEZE_ENABLED = false`;
- список frozen features оставлен в коде, но глобально выключен.

Это означает: приложение сейчас открыто как рабочая версия без launch-lock и без feature-freeze. Если перед Пекином нужно закрыть части интерфейса, включать осознанно.

## Оценка готовности

Оценка: приложение готово к запуску при условии аккуратного operational режима.

Сильные стороны:

- функционально покрыты все основные сценарии поездки;
- есть админские инструменты для денег, REP, перекличек, контрактов, стирки/воды, gift-code, ивентов;
- экономика серверо-авторитетна;
- есть security hardening и rate limit;
- появилось достаточно документации для восстановления контекста;
- UI стал намного понятнее за счёт инструкции и сюжетных попапов.

Главные риски:

- монолитный backend и крупные JS-файлы всё ещё требуют осторожных точечных правок;
- нет полноценных автотестов бизнес-логики, только syntax/CI checks;
- SQLite подходит для группы ~85 человек, но WAL/checkpoint трогать нельзя без причины;
- production env важнее дефолтов в коде;
- GitHub Pages/Telegram WebView могут держать старый кэш, поэтому cache-bust версии важны;
- репозиторий и серверный backend нужно сравнивать перед каждым backend deploy.

## Рабочий режим в Пекине

Во время поездки любые изменения делать по схеме:

1. Сначала определить: frontend-only или backend/API.
2. Для frontend: правка, `node --check`, `git diff --check`, commit/push.
3. Для backend: сначала `diff /root/zhidao_api.py` против `main/zhidao_api_ready.py`, затем backup, `py_compile`, restart, smoke.
4. После любой денежной/перекличечной правки проверить логи:

```bash
journalctl -u zhidao_api.service -u zhidao_bot.service --since "10 minutes ago" --no-pager -l \
  | grep -E "ZHIDAO_DB_WRITE|ZHIDAO_SLOW_CONN|ZHIDAO_WAL|database is locked|ERROR|Traceback"

ls -lh /root/zhidao.db*
```

Healthy state: нет ошибок/lock, WAL не разрастается неконтролируемо.

## Что не делать во время поездки

- Не мигрировать на PostgreSQL без реальной аварии.
- Не переписывать frontend на модули/React.
- Не менять экономику “на глаз” без пересчёта.
- Не трогать WAL/checkpoint/SQLite writer path без измерений.
- Не деплоить backend с GitHub вслепую.
- Не чистить “мёртвый код” в боевой день, если он не ломает работу.

## Минимальный ежедневный check

- API и бот active.
- Нет `database is locked`, `Traceback`, `ZHIDAO_SLOW_CONN`.
- Gift-code/ивенты выключены или включены осознанно.
- `TELEGRAM_AUTH_REQUIRED=1`.
- Создан свежий backup базы.
- Один ручной smoke с телефона: профиль, магазин, перекличка, контракт, админка.
