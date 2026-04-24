# ZHIDAO Protocol: Raid Upgrade Patch

Этот патч рассчитан на ваш текущий `zhidao_api.py` и приводит рейд к правилам, которые вы утвердили:

- вход в рейд: `50★`
- шанс успеха: `40%`
- награда при успехе: `150★ каждому`
- минимум бойцов: `3`
- базовый лимит: `3 рейда в день`
- товар в магазине: `+1 попытка рейда сегодня` за `80★`
- админы: могут рейдить соло и без лимита, награду получают, но в обычный рейтинг не попадают

## 1. Добавьте константы рядом с `ADMIN_IDS`

```python
RAID_ENTRY_COST = 50
RAID_SUCCESS_REWARD = 150
RAID_SUCCESS_CHANCE = 0.4
RAID_DAILY_LIMIT = 3
RAID_MIN_PLAYERS = 3
SHOP_EXTRA_RAID_CODE = "extra_raid_attempt"
SHOP_EXTRA_RAID_PRICE = 80
```

## 2. Обновите `init_db()` и добавьте миграцию

В `user_status` нужен новый столбец `extra_raids`.

Замените создание `user_status` на это:

```python
c.execute('''CREATE TABLE IF NOT EXISTS user_status
             (telegram_id INTEGER PRIMARY KEY,
              frozen INTEGER DEFAULT 0,
              immunity INTEGER DEFAULT 0,
              immunity_reason TEXT DEFAULT NULL,
              extra_cases INTEGER DEFAULT 0,
              extra_raids INTEGER DEFAULT 0,
              double_win INTEGER DEFAULT 0,
              title_date TEXT DEFAULT NULL)''')
```

Сразу после `init_db()` добавьте:

```python
def migrate_db():
    conn = sqlite3.connect('/root/zhidao.db')
    c = conn.cursor()

    c.execute("PRAGMA table_info(user_status)")
    columns = {row[1] for row in c.fetchall()}
    if "extra_raids" not in columns:
        c.execute("ALTER TABLE user_status ADD COLUMN extra_raids INTEGER DEFAULT 0")

    conn.commit()
    conn.close()

migrate_db()
```

## 3. Добавьте сид магазина для `+1 рейд-попытки`

Один раз выполните в БД:

```sql
INSERT OR REPLACE INTO shop_items
  (code, name, description, icon, price, daily_limit, category, active)
VALUES
  ('extra_raid_attempt', 'Доп. рейд-попытка', '+1 рейд сегодня', '⚔️', 80, -1, 'privilege', 1);
```

Если захотите потом зажать экономику, меняйте `daily_limit` с `-1` на конкретное число.

## 4. Обновите `/api/points/{telegram_id}`

Замените этот кусок:

```python
c.execute("SELECT double_win, extra_cases, immunity FROM user_status WHERE telegram_id=?", (telegram_id,))
status = c.fetchone()
```

на:

```python
c.execute("SELECT double_win, extra_cases, immunity, extra_raids FROM user_status WHERE telegram_id=?", (telegram_id,))
status = c.fetchone()
```

И верните ещё одно поле:

```python
return {
    "points": result[0] or 0,
    "full_name": result[1],
    "double_win": status[0] if status else 0,
    "extra_cases": status[1] if status else 0,
    "immunity": status[2] if status else 0,
    "extra_raids": status[3] if status else 0
}
```

## 5. Обновите покупку в магазине

В `buy_item()` добавьте ещё одну ветку рядом с `extra_case`:

```python
elif item_code == SHOP_EXTRA_RAID_CODE:
    c.execute("""INSERT INTO user_status (telegram_id, extra_raids) VALUES (?,1)
                 ON CONFLICT(telegram_id) DO UPDATE SET extra_raids=extra_raids+1""", (telegram_id,))
```

## 6. Полностью замените `/api/raid/status`

```python
@app.get("/api/raid/status")
async def get_raid_status(telegram_id: int = 0):
    today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
    conn = sqlite3.connect('/root/zhidao.db')
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS raids
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  date TEXT, status TEXT DEFAULT 'open',
                  result TEXT DEFAULT NULL,
                  created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS raid_participants
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  raid_id INTEGER, telegram_id INTEGER,
                  UNIQUE(raid_id, telegram_id))''')
    conn.commit()

    c.execute("SELECT COUNT(*) FROM raids WHERE date=? AND status='finished'", (today,))
    finished_today = c.fetchone()[0]

    extra_raids = 0
    if telegram_id and telegram_id not in ADMIN_IDS:
        c.execute("SELECT extra_raids FROM user_status WHERE telegram_id=?", (telegram_id,))
        row = c.fetchone()
        extra_raids = row[0] if row else 0

    if telegram_id in ADMIN_IDS:
        remaining_today = 999
    else:
        remaining_today = max(0, RAID_DAILY_LIMIT - finished_today) + extra_raids

    c.execute("SELECT id, status, result FROM raids WHERE date=? ORDER BY id DESC LIMIT 1", (today,))
    raid = c.fetchone()
    if not raid:
        conn.close()
        return {
            "raid": None,
            "participants": [],
            "count": 0,
            "finished_today": finished_today,
            "remaining_today": remaining_today,
            "limit_today": RAID_DAILY_LIMIT,
            "required_players": RAID_MIN_PLAYERS
        }

    raid_id, status, result = raid
    c.execute("""SELECT u.full_name, rp.telegram_id FROM raid_participants rp
                 JOIN users u ON rp.telegram_id = u.telegram_id
                 WHERE rp.raid_id=?""", (raid_id,))
    participants = c.fetchall()
    conn.close()

    return {
        "raid": {"id": raid_id, "status": status, "result": result, "date": today},
        "participants": [{"name": p[0] or "Аноним", "telegram_id": p[1]} for p in participants],
        "count": len(participants),
        "finished_today": finished_today,
        "remaining_today": remaining_today,
        "limit_today": RAID_DAILY_LIMIT,
        "required_players": RAID_MIN_PLAYERS
    }
```

## 7. Полностью замените `/api/raid/join`

```python
@app.post("/api/raid/join")
async def join_raid(data: dict):
    telegram_id = data.get("telegram_id")
    if not telegram_id:
        raise HTTPException(status_code=400, detail="No telegram_id")

    today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
    now_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')

    conn = sqlite3.connect('/root/zhidao.db', isolation_level='EXCLUSIVE')
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS raids
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  date TEXT, status TEXT DEFAULT 'open',
                  result TEXT DEFAULT NULL,
                  created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS raid_participants
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  raid_id INTEGER, telegram_id INTEGER,
                  UNIQUE(raid_id, telegram_id))''')

    c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
    user = c.fetchone()
    if not user or (user[0] or 0) < RAID_ENTRY_COST:
        conn.close()
        raise HTTPException(status_code=400, detail="Not enough points")

    c.execute("SELECT COUNT(*) FROM raids WHERE date=? AND status='finished'", (today,))
    finished_count = c.fetchone()[0]

    c.execute("SELECT extra_raids FROM user_status WHERE telegram_id=?", (telegram_id,))
    status_row = c.fetchone()
    extra_raids = status_row[0] if status_row else 0

    consumed_extra_attempt = False
    if telegram_id not in ADMIN_IDS and finished_count >= RAID_DAILY_LIMIT:
        if extra_raids <= 0:
            conn.close()
            raise HTTPException(status_code=400, detail="Daily raid limit reached")
        c.execute("""INSERT INTO user_status (telegram_id, extra_raids) VALUES (?,0)
                     ON CONFLICT(telegram_id) DO UPDATE SET extra_raids=extra_raids-1""", (telegram_id,))
        consumed_extra_attempt = True

    c.execute("""SELECT r.id FROM raids r
                 WHERE r.date=? AND r.status='open'
                 AND r.id NOT IN (SELECT raid_id FROM raid_participants WHERE telegram_id=?)
                 LIMIT 1""", (today, telegram_id))
    raid = c.fetchone()

    if not raid:
        c.execute("INSERT INTO raids (date, created_at) VALUES (?,?)", (today, now_str))
        raid_id = c.lastrowid
    else:
        raid_id = raid[0]

    try:
        c.execute("INSERT INTO raid_participants (raid_id, telegram_id) VALUES (?,?)",
                  (raid_id, telegram_id))
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=409, detail="Already joined")

    c.execute("UPDATE users SET points = points - ? WHERE telegram_id=?", (RAID_ENTRY_COST, telegram_id))

    c.execute("SELECT COUNT(*) FROM raid_participants WHERE raid_id=?", (raid_id,))
    count = c.fetchone()[0]

    launched = False
    result = None

    if count >= RAID_MIN_PLAYERS or (telegram_id in ADMIN_IDS and count >= 1):
        launched = True
        result = 'success' if random.random() < RAID_SUCCESS_CHANCE else 'defended'

        c.execute("UPDATE raids SET status='finished', result=? WHERE id=?", (result, raid_id))
        c.execute("SELECT telegram_id FROM raid_participants WHERE raid_id=?", (raid_id,))
        all_participants = [r[0] for r in c.fetchall()]

        if result == 'success':
            for tid in all_participants:
                c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?",
                          (RAID_SUCCESS_REWARD, tid))

    conn.commit()

    c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
    new_points = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM raids WHERE date=? AND status='finished'", (today,))
    finished_today = c.fetchone()[0]

    if telegram_id in ADMIN_IDS:
        remaining = 999
    else:
        c.execute("SELECT extra_raids FROM user_status WHERE telegram_id=?", (telegram_id,))
        extra_row_after = c.fetchone()
        extra_after = extra_row_after[0] if extra_row_after else 0
        remaining = max(0, RAID_DAILY_LIMIT - finished_today) + extra_after

    conn.close()

    return {
        "joined": True,
        "count": count,
        "launched": launched,
        "result": result,
        "participants_count": count,
        "new_points": new_points,
        "remaining_today": remaining,
        "limit_today": RAID_DAILY_LIMIT,
        "required_players": RAID_MIN_PLAYERS,
        "consumed_extra_attempt": consumed_extra_attempt,
        "points_change": (
            RAID_SUCCESS_REWARD - RAID_ENTRY_COST
            if (launched and result == "success")
            else -RAID_ENTRY_COST
            if launched
            else -RAID_ENTRY_COST
        ),
        "message": (
            f"🏆 РЕЙД УСПЕШЕН! +{RAID_SUCCESS_REWARD}★ каждому!"
            if (launched and result == "success") else
            "🛡 АЛЬФАБОСС ЗАЩИТИЛСЯ! Ставки сгорели."
            if (launched and result == "defended") else
            f"⚔️ Ты в отряде! Бойцов: {count}/{RAID_MIN_PLAYERS}"
        )
    }
```

## 8. Что уже подготовлено на фронте

В локальном HTML я уже подготовил поддержку:

- корректного отображения лимита `3/день`
- чтения персонального `remaining_today`
- магазина для `extra_raid_attempt`
- иконок-заглушек под будущие рейдовые товары:
  - `raid_insurance`
  - `raid_beacon`
  - `raid_overclock`

## 9. Что я бы добавил следующим этапом

Не обязательно сейчас, но это логичное развитие:

- `raid_beacon`
  Приватный отряд по коду, чтобы друзья шли вместе.
- `raid_insurance`
  Возврат `25★` при поражении.
- `raid_overclock`
  Бафф отряду, например `+10%` к шансу успеха.

Для этого лучше завести в `raids` поля:

```sql
ALTER TABLE raids ADD COLUMN squad_code TEXT DEFAULT NULL;
ALTER TABLE raids ADD COLUMN is_private INTEGER DEFAULT 0;
ALTER TABLE raids ADD COLUMN success_bonus REAL DEFAULT 0;
```

Но это уже второй этап, после стабилизации текущего патча.
