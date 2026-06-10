# SECURITY_HARDENING.md

Итоги аудита безопасности ZHIDAO Protocol (2026-06-10) и конкретные действия.
Проверялось вживую против локальной копии бэкенда.

## TL;DR — что сделать в проде

1. **Проверить `TELEGRAM_AUTH_REQUIRED=1`** в systemd-юните API. Это самый важный
   пункт. Без него любой может выдавать себя за любого юзера.
2. **(Сделано в коде)** Rate-limit по IP внутри приложения. Защита от
   DDoS/флуда, который исторически уже дважды клал SQLite-писатель (см.
   CLAUDE.md, оба датакрэша). Задеплоить и при необходимости подправить
   `RATE_LIMIT_MAX_REQUESTS_PER_SECOND` (см. Дыра №2).
3. **(Сделано в коде, задеплоено)** Проверка свежести init-data — защита от replay.

---

## Что уже сделано правильно (не трогать)

- Аутентификация через Telegram init-data: HMAC-подпись бота, `hmac.compare_digest`.
- Экономика серверо-авторитетна: клиент не решает суммы. Админская правка очков
  ограничена ±5000 и требует причину.
- SQL весь параметризованный — инъекций нет.
- Секретов в коде нет (всё через `os.getenv`). Во фронте `ADMIN_IDS = []` —
  статус админа приходит с сервера. Подмена `isAdmin` в браузере бесполезна:
  каждое админ-действие проверяется на сервере и отдаёт 401/403.
- CORS `allow_origins=["*"]` здесь безопасен: аутентификация через кастомный
  заголовок, а не cookie — нет амбиентных учёток для CSRF. **Менять не нужно.**

---

## Дыра №1 (критическая): `TELEGRAM_AUTH_REQUIRED`

Дефолт переменной — `0`. При `0` (проверено вживую):

```
GET  /api/profile/<любой_id>       -> 200 + все очки/реп/статистика
POST /api/casino/open {telegram_id:<чужой>} -> 200, кейс открыт от чужого имени
```

То есть подмена личности на всех неадминских эндпоинтах. Админские при этом
защищены всегда (наличие заголовка `x-admin-id` само включает проверку).

**Проверка в проде:**
```bash
systemctl show zhidao_api.service -p Environment | tr ' ' '\n' \
  | grep -E "TELEGRAM_AUTH_REQUIRED|BOT_TOKEN|API_INTERNAL_TOKEN"
```
Должно быть `TELEGRAM_AUTH_REQUIRED=1`. Если нет — добавить в юнит и
`systemctl daemon-reload && systemctl restart zhidao_api.service`.

---

## Дыра №2 (важная для DDoS, ИСПРАВЛЕНО в коде): нет rate-limit

В приложении не было троттлинга (проверено: 150 параллельных запросов — все 200).
Особо опасно, т.к. флуд write-запросов = тот самый каскад блокировок SQLite из
истории инцидентов.

**Важно:** изначально планировался rate-limit на уровне nginx, но проверка
конфигурации сервера показала, что nginx **не проксирует** порт 8443 — uvicorn
сам терминирует TLS и слушает 8443 напрямую (см. systemd unit/override). Поэтому
nginx `limit_req` тут не сработает, и троттлинг сделан **внутри приложения**.

### Что добавлено

In-process sliding-window rate-limit по IP, в `zhidao_api_ready.py`:

- Новая переменная окружения: `RATE_LIMIT_MAX_REQUESTS_PER_SECOND` (дефолт `20`).
  `0` отключает лимит (escape hatch).
- Лимит — на IP-адрес, скользящее окно в 1 секунду (`collections.deque`).
- При превышении — `429 Too Many Requests`.
- Запросы с заголовком `x-internal-token` (внутренние вызовы бота через
  `API_INTERNAL_TOKEN`) лимит не учитывает.
- Фоновая задача раз в 60с чистит "остывшие" бакеты IP, чтобы память не росла
  при флуде с большого числа разных адресов.

Проверено в песочнице:
- `RATE_LIMIT_MAX_REQUESTS_PER_SECOND=1`, 20 параллельных запросов — 1×200,
  19×429.
- С `x-internal-token` — все 20×200 (байпас работает).
- После ожидания >1с — снова 200 (окно сбрасывается).
- Реальная загрузка главной страницы (≈10 параллельных запросов на старте) при
  дефолтном лимите 20/с — все 200, ни одного 429.

### Деплой бэкенда

```bash
curl -sL https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/zhidao_api_ready.py -o /root/zhidao_api.py
python3 -m py_compile /root/zhidao_api.py && systemctl restart zhidao_api.service
```

Перед деплоем сверить с тем, что реально крутится (см. предупреждение в
CLAUDE.md про расхождение репо/сервера после отладки SQLite 2026-06-09):
```bash
diff /root/zhidao_api.py <(curl -sL https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/zhidao_api_ready.py)
```

Если дефолт 20/с окажется слишком строгим или слишком мягким для реального
трафика — подправить через systemd override:
```bash
systemctl edit zhidao_api.service
# [Service]
# Environment=RATE_LIMIT_MAX_REQUESTS_PER_SECOND=30
systemctl daemon-reload && systemctl restart zhidao_api.service
```

По возможности — поставить Cloudflare перед доменом (бесплатный тариф закрывает
объёмный L3/L4 DDoS, до которого приложение уже не дотянется).

---

## Дыра №3 (средняя, ИСПРАВЛЕНО в коде): replay init-data

`verify_telegram_init_data` не проверял `auth_date` — перехваченная строка
init-data была валидна вечно. Добавлена проверка свежести.

- Новая переменная: `TELEGRAM_AUTH_MAX_AGE_SECONDS` (дефолт `86400` = 24 ч).
- `0` отключает проверку (escape hatch, если будет лочить долгие сессии).
- Логика проверена юнит-тестом: свежая подпись — принята, протухшая (25 ч) и
  подделанная — отклонены.

### Деплой бэкенда

```bash
curl -sL https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/zhidao_api_ready.py -o /root/zhidao_api.py
python3 -m py_compile /root/zhidao_api.py && systemctl restart zhidao_api.service
```

ВНИМАНИЕ: перед деплоем сверить с тем, что реально крутится (CLAUDE.md
предупреждает о расхождении репо и сервера после отладки SQLite 2026-06-09):
```bash
diff /root/zhidao_api.py <(curl -sL https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/zhidao_api_ready.py)
```

---

## Сводка по типам угроз

| Угроза | Статус |
|---|---|
| Школьники через нейронки / консоль браузера | Защищены — клиент ничего не решает |
| Айтишники (подмена запросов, replay) | Защищены при `TELEGRAM_AUTH_REQUIRED=1` + фикс replay |
| DDoS / флуд | Закрывается in-app rate-limit (Дыра №2, исправлено) + желательно Cloudflare |
| Профи-хакеры | Поверхность мала: нет инъекций/секретов, серверная экономика; главный вектор — отказ в обслуживании |
