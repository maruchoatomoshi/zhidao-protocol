# SECURITY_HARDENING.md

Итоги аудита безопасности ZHIDAO Protocol (2026-06-10) и конкретные действия.
Проверялось вживую против локальной копии бэкенда.

## TL;DR — что сделать в проде

1. **Проверить `TELEGRAM_AUTH_REQUIRED=1`** в systemd-юните API. Это самый важный
   пункт. Без него любой может выдавать себя за любого юзера.
2. **Добавить rate-limit в nginx** (блок ниже). Защита от DDoS/флуда, который
   исторически уже дважды клал SQLite-писатель (см. CLAUDE.md, оба датакрэша).
3. **(Сделано в коде)** Проверка свежести init-data — защита от replay.

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

## Дыра №2 (важная для DDoS): нет rate-limit

В приложении нет троттлинга (проверено: 150 параллельных запросов — все 200).
Особо опасно, т.к. флуд write-запросов = тот самый каскад блокировок SQLite из
истории инцидентов. Закрываем на уровне nginx (он уже стоит ради HTTPS).

В `http {}` блок (обычно `/etc/nginx/nginx.conf`):
```nginx
limit_req_zone  $binary_remote_addr zone=zhidao_api:10m  rate=10r/s;
limit_conn_zone $binary_remote_addr zone=zhidao_conn:10m;
```

В `server {}` для `hk.marucho.icu`, внутри `location /api/`:
```nginx
location /api/ {
    limit_req  zone=zhidao_api burst=20 nodelay;
    limit_conn zhidao_conn 20;
    limit_req_status 429;
    limit_conn_status 429;

    proxy_pass https://127.0.0.1:8443;
    # ... существующие proxy_set_header ...
}
```

Применить:
```bash
nginx -t && systemctl reload nginx
```

Проверка (должны появиться 429 при флуде):
```bash
for i in $(seq 1 60); do curl -s -o /dev/null -w "%{http_code}\n" \
  https://hk.marucho.icu/api/settings & done | sort | uniq -c
```

По возможности — поставить Cloudflare перед доменом (бесплатный тариф закрывает
объёмный L3/L4 DDoS, до которого nginx уже не дотянется).

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
| DDoS / флуд | Закрывается nginx rate-limit (Дыра №2) + Cloudflare |
| Профи-хакеры | Поверхность мала: нет инъекций/секретов, серверная экономика; главный вектор — отказ в обслуживании |
