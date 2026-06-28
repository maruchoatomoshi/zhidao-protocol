# CODEX HANDOFF — ZHIDAO Protocol

Дата фиксации: 2026-06-28

Этот файл нужен, чтобы открыть проект на другом компьютере и быстро передать контекст новому Codex-чату.

## Как использовать на новом ноутбуке

1. Открой репозиторий `zhidao-protocol` в Codex.
2. Перед любыми правками попроси Codex прочитать:
   - `CODEX_HANDOFF.md`
   - `CLAUDE.md`
   - `PROJECT_STATUS_2026-06-17.md`
   - `ECONOMY_PASSPORT.md`
   - `FEATURE_FREEZE.md`
3. Первое сообщение новому Codex можно дать таким:

```text
Это проект ZHIDAO Protocol. Прочитай CODEX_HANDOFF.md, CLAUDE.md,
PROJECT_STATUS_2026-06-17.md, ECONOMY_PASSPORT.md и FEATURE_FREEZE.md.
После этого работай точечно: не делай broad rewrite, не деплой backend без сверки
с сервером, не трогай SQLite/WAL/checkpoint без причины.
```

## Что это за проект

ZHIDAO Protocol — Telegram Mini App для поездки в Пекин.

Основные части:

- frontend: GitHub Pages, `index.html`, `css/styles.css`, `js/*.js`;
- backend: FastAPI, `zhidao_api_ready.py`;
- bot: `zhidao_bot_ready.py`;
- база: SQLite на сервере;
- темы: NetWatch/Cyberpunk, Genshin, admin, architect;
- игровые системы: REP, stars/points, магазин, кейсы/молитвы, импланты, карточки, рейды, дневник, переклички, контракты, карта кампуса, live gift-code, ивенты Architect/WildAI.

## Текущее рабочее правило

Проект функционально готов к запуску. Любые изменения должны быть точечными.

Перед поездкой и во время поездки приоритет такой:

1. стабильность;
2. сохранность базы;
3. работа Telegram Mini App на телефонах;
4. только потом визуальная полировка.

Не делать большие переписывания, если нет аварии.

## Важные документы

- `CLAUDE.md` — главная operational-памятка, история аварий, правила работы.
- `PROJECT_STATUS_2026-06-17.md` — запусковая фиксация состояния проекта.
- `ECONOMY_PASSPORT.md` — экономика: `points`, `rep_score`, источники, траты, лимиты.
- `FEATURE_FREEZE.md` — план заморозки фич и порядок открытия разделов.
- `GUIDE_MIKHAIL_YURYEVICH.md` — версия руководства для Михаила Юрьевича.
- `USER_GUIDE.md` — пользовательская инструкция.
- `PROJECT_ASSESSMENT.md` — оценка проекта и рисков.

## Критические инциденты

### Великий датакрэш — 2026-05-27

Сервер/API/DB оказались почти пустыми:

- `users=0`;
- `expected_students=0`;
- `shop_items=1`;
- `achievements=0`;
- `settings=0`.

Пришлось заново восстанавливать пользователей, админов, тестеров, товары, настройки, HTTPS, список детей, VPN/Marzban-привязки.

После этого появились более строгие правила по env, backup и deployment.

### Второй датакрэш — 2026-06-09

SQLite/WAL/checkpoint-эксперименты привели к зависаниям write endpoints на десятки и сотни секунд:

- покупки;
- начисления/снятия баллов;
- магазин;
- любые операции с записью.

Опасные зоны:

- `wal_checkpoint(TRUNCATE/RESTART)` рядом с активными writers;
- startup checkpoint, который блокирует запуск uvicorn;
- случайные изменения writer path без бенчмарка.

Known-good backup на сервере:

```text
/root/zhidao_known_good/zhidao_known_good_20260609_123206.tar.gz
sha256: d842860f72718193c24151f60e6ece7f0041a7dc6c201e770e50c2b840b2c07a
```

## Backend: главное предупреждение

Backend на сервере мог отличаться от `zhidao_api_ready.py` в репозитории.

Перед любым backend deploy:

```bash
diff /root/zhidao_api.py <(curl -sL https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/zhidao_api_ready.py)
```

Если есть расхождение, сначала понять, какая версия рабочая. Не заливать GitHub-версию вслепую.

## Production env

Не хранить секреты в репозитории и не вставлять их в AI-чат.

Критичные переменные на сервере:

- `ADMIN_IDS`
- `ARCHITECT_IDS`
- `TELEGRAM_AUTH_REQUIRED=1`
- `BOT_TOKEN`
- `API_INTERNAL_TOKEN`
- `EXPECTED_STUDENTS_FILE`
- `TELEGRAM_AUTH_MAX_AGE_SECONDS`

В коде дефолты могут быть мягче, чем production. Production держится на systemd env.

## Проверка здоровья сервера

После backend-изменений или странных задержек:

```bash
journalctl -u zhidao_api.service -u zhidao_bot.service --since "10 minutes ago" --no-pager -l \
  | grep -E "ZHIDAO_DB_WRITE|ZHIDAO_SLOW_CONN|ZHIDAO_WAL|database is locked|ERROR|Traceback"

ls -lh /root/zhidao.db*
```

Здоровое состояние:

- нет `database is locked`;
- нет `Traceback`;
- нет длинных `ZHIDAO_DB_WRITE`;
- WAL не растёт неконтролируемо, ориентир — до нескольких MB.

## Минимальный backend deploy

Только после сверки серверной версии.

```bash
mkdir -p /root/zhidao_backup
cp -a /root/zhidao_api.py /root/zhidao_backup/zhidao_api_before_update_$(date +%Y%m%d_%H%M%S).py

curl -L https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/zhidao_api_ready.py \
  -o /root/zhidao_api.py

python3 -m py_compile /root/zhidao_api.py
systemctl restart zhidao_api.service
sleep 3
systemctl status zhidao_api.service --no-pager -l
```

Для бота аналогично, но не забывать `BOT_TOKEN` и `API_INTERNAL_TOKEN` в env.

## Frontend deploy

Frontend живёт через GitHub Pages/raw GitHub assets.

После frontend-правок:

```bash
node --check js/*.js
git diff --check
git status --short
```

Потом commit/push.

Если Telegram WebView показывает старое, проверить cache-bust версии в `<script src="...?...">` и обновление GitHub Pages.

## Экономика

Главная модель:

- `points` = spendable wallet, звёзды `★`;
- `rep_score` = публичная репутация `REP`;
- публичный рейтинг строится по `rep_score`, не по кошельку.

REP нельзя переводить, дарить или покупать через P2P.

Базовые правила:

- дневник даёт и `★`, и `REP`;
- штрафы за переклички снимают и `★`, и `REP`;
- магазин, контракты, подарки, кейсы, рейды не должны напрямую покупать публичный рейтинг;
- подарки и контракты мониторятся как возможный indirect value transfer;
- contract fee: 10%, минимум 2★, комиссия сгорает;
- non-admin gift limit: 5/day;
- raid: entry 50★, win reward 100★, chance 40%.

Подробности всегда сверять с `ECONOMY_PASSPORT.md` и backend-кодом.

## Feature freeze

В `js/config.js` есть фронтенд-заморозка разделов:

```js
window.APP_FEATURE_FREEZE_ENABLED = false;
window.APP_FROZEN_FEATURES = {
  casino: true,
  shop: true,
  implants: true,
  laundry: false,
  achievements: true,
  'diary-stars': true,
  rating: true,
};
```

Если поставить `APP_FEATURE_FREEZE_ENABLED = true`, обычные пользователи увидят замороженные разделы как закрытые.

Админы и Архитектор обходят feature-freeze.

Важно: это frontend-only блокировка. Для жёсткой серверной блокировки экономики использовать BlackWall или персональную NetWatch-заморозку.

## Режимы блокировки

Есть три разных механизма:

1. `APP_FEATURE_FREEZE_ENABLED` — frontend lock отдельных разделов.
2. `user_status.frozen` / `netwatch_locked_until` — персональная NetWatch-заморозка игрока.
3. `settings.blackwall` — глобальный Красный Файрвол, блокирует магазин, кейсы/молитвы и Доску поручений для обычных пользователей.

Не путать их при диагностике.

## Что нельзя делать без явного решения

- Не мигрировать на PostgreSQL.
- Не переписывать frontend на React/modules.
- Не менять SQLite WAL/checkpoint/writer path без измерений.
- Не деплоить backend с GitHub вслепую.
- Не чистить “мёртвый код” в боевой день.
- Не менять экономику на глаз.
- Не удалять старые поля вроде `points`, если они используются как compatibility layer.
- Не коммитить секреты, реальные токены, приватные списки и персональные данные.

## Перед любой правкой

Проверить:

```bash
git status --short --branch
git log --oneline -5
```

Если ветка отстаёт от `origin/main` или есть чужие незакоммиченные изменения, не делать `reset`, не делать destructive checkout. Сначала согласовать с пользователем или работать точечно, не затрагивая чужие файлы.

## Стиль правок

- Точечно.
- Без broad rewrite.
- Без переименования глобальных JS-функций, которые вызываются из inline `onclick`.
- После JS-правок запускать `node --check`.
- После Python-правок запускать `python -m py_compile`.
- После любых изменений делать `git diff --check`.

## Быстрый smoke перед запуском

Проверить с реального Telegram Mini App:

- открытие профиля;
- выбор темы;
- магазин: покупка и баланс;
- дневник ★: начисление/снятие;
- REP: ручное начисление и рейтинг;
- перекличка: запуск, ответ, кто не ответил;
- контракт: создать, принять, отменить/завершить;
- карта кампуса;
- бот `/start` и основные кнопки;
- админка: users/dossier/economy/contracts.

## Если приложение “пустое” или “без данных”

Проверять в таком порядке:

1. Telegram initData/auth.
2. `BOT_TOKEN` в API env.
3. `API_INTERNAL_TOKEN` для bot/API.
4. `/api/user/{telegram_id}`.
5. `systemctl status zhidao_api.service zhidao_bot.service`.
6. Логи `ERROR|Traceback|ZHIDAO_TELEGRAM_AUTH`.
7. Не был ли пользователь потерян из `users`.

## Если покупки/начисления снова тормозят

Не начинать с PostgreSQL.

Сначала:

1. посмотреть `journalctl` по шаблону выше;
2. проверить размер WAL;
3. проверить, не вернулся ли опасный checkpoint;
4. проверить, не держит ли бот write-lock;
5. сравнить серверный `/root/zhidao_api.py` с known-good/repo;
6. сделать backup перед любыми изменениями.

## Рабочая позиция для Codex

В этом проекте важнее сохранить работоспособность, чем сделать архитектурно красиво.

Если есть выбор:

- маленький безопасный hotfix лучше крупного рефактора;
- измерение лучше предположения;
- backup перед backend-правкой обязателен;
- серверная реальность важнее того, что “должно быть” в репозитории.
