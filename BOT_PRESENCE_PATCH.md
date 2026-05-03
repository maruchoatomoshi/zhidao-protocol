# ZHIDAO Bot Presence Patch

Этот патч переводит бота со старой локальной логики `checkin_responses` на новый Presence API.

Важно: не коммить живой `BOT_TOKEN` в GitHub. На сервере можно оставить текущий токен в `/root/zhidao_bot.py`, но в публичный репозиторий его лучше не переносить.

## 1. Константы после `reminders_enabled = False`

```python
API_URL = "https://127.0.0.1:8443"
PRESENCE_ADMIN_ID = ADMIN_IDS[0]
PRESENCE_PENALTY_POINTS = 50
PRESENCE_RETRY_STATUSES = {"pending", "leave_rejected"}
PRESENCE_SAFE_STATUSES = {"confirmed", "free_time", "admin_approved", "skipped", "penalized"}
```

Проверь список админов в боте. В присланном коде нет `463135292`, хотя в API он есть:

```python
ADMIN_IDS = [389741116, 244487659, 1190015933, 491711713, 463135292, 8222459731]
```

## 2. API helpers после `is_admin`

```python
async def api_request(method, path, json_data=None, params=None, admin=False):
    headers = {}
    if admin:
        headers["x-admin-id"] = str(PRESENCE_ADMIN_ID)

    async with aiohttp.ClientSession() as session:
        async with session.request(
            method,
            f"{API_URL}{path}",
            json=json_data,
            params=params,
            headers=headers,
            ssl=False,
        ) as r:
            try:
                data = await r.json()
            except Exception:
                data = {"detail": await r.text()}

            if r.status >= 400:
                raise RuntimeError(data.get("detail") or f"API error {r.status}")
            return data


async def presence_start(check_type, note=""):
    return await api_request(
        "POST",
        "/api/presence/start",
        {"check_type": check_type, "note": note},
        admin=True,
    )


async def presence_attempt(check_type, telegram_id):
    return await api_request(
        "POST",
        "/api/presence/attempt",
        {"check_type": check_type, "telegram_id": telegram_id},
        admin=True,
    )


async def presence_confirm(telegram_id, check_type, action, note=""):
    return await api_request(
        "POST",
        "/api/presence/confirm",
        {
            "telegram_id": telegram_id,
            "check_type": check_type,
            "action": action,
            "note": note,
        },
    )


async def presence_overview(check_type):
    return await api_request(
        "GET",
        "/api/presence/admin/overview",
        params={"check_type": check_type},
        admin=True,
    )


async def presence_escalate(check_type):
    return await api_request(
        "POST",
        "/api/presence/admin/escalate",
        {"check_type": check_type},
        admin=True,
    )


async def presence_penalize(check_type, penalty_points=PRESENCE_PENALTY_POINTS):
    return await api_request(
        "POST",
        "/api/presence/admin/penalize",
        {"check_type": check_type, "penalty_points": penalty_points},
        admin=True,
    )


async def presence_approve(telegram_id, check_type, admin_id, reason="admin_approved"):
    return await api_request(
        "POST",
        "/api/presence/admin/approve",
        {
            "telegram_id": telegram_id,
            "check_type": check_type,
            "admin_id": admin_id,
            "reason": reason,
        },
        admin=True,
    )


async def presence_reject(telegram_id, check_type, admin_id, reason="leave rejected"):
    return await api_request(
        "POST",
        "/api/presence/admin/reject",
        {
            "telegram_id": telegram_id,
            "check_type": check_type,
            "admin_id": admin_id,
            "reason": reason,
        },
        admin=True,
    )
```

## 3. Клавиатуры вместо старого `get_checkin_keyboard`

```python
def get_presence_keyboard(check_type):
    if check_type == "morning":
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Я проснулся", callback_data="presence:morning:confirm"),
            InlineKeyboardButton(text="🙋 Нужна помощь", callback_data="presence:morning:request_leave"),
        ]])

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я в комнате", callback_data="presence:evening:confirm")],
        [
            InlineKeyboardButton(text="🕐 Свободное время", callback_data="presence:evening:free_time"),
            InlineKeyboardButton(text="🙋 Нужен отгул", callback_data="presence:evening:request_leave"),
        ],
    ])


def get_checkin_keyboard():
    return get_presence_keyboard("evening")


def get_presence_admin_keyboard(check_type, telegram_id):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="✅ Разрешить",
            callback_data=f"presence_admin:approve:{check_type}:{telegram_id}",
        ),
        InlineKeyboardButton(
            text="❌ Отклонить",
            callback_data=f"presence_admin:reject:{check_type}:{telegram_id}",
        ),
    ]])
```

## 4. Новая рассылка вместо старых `send_checkin`, `check_missing`, `check_wakeup_missing`

```python
async def notify_admins(text, reply_markup=None):
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, reply_markup=reply_markup)
        except Exception:
            pass


def get_presence_message(check_type, attempt_no=1):
    if check_type == "morning":
        return (
            "🌅 Утренняя отметка\n\n"
            f"Попытка {attempt_no}/3. Нажми кнопку, чтобы подтвердить подъём."
        )

    return (
        "🌙 Вечерняя отметка\n\n"
        f"Попытка {attempt_no}/3. 21:00 — нужно быть в комнате.\n"
        "Если у тебя разрешение от админа или активное «Свободное время», выбери нужную кнопку."
    )


async def send_presence_attempt(check_type, attempt_no=1, create_check=False):
    if not reminders_enabled:
        return

    if create_check:
        await presence_start(check_type, f"bot attempt {attempt_no}")

    overview = await presence_overview(check_type)
    sent = 0

    for check in overview.get("checks", []):
        tg_id = check.get("telegram_id")
        status = check.get("status")
        if not tg_id or tg_id in ADMIN_IDS or status not in PRESENCE_RETRY_STATUSES:
            continue

        try:
            await bot.send_message(
                tg_id,
                get_presence_message(check_type, attempt_no),
                reply_markup=get_presence_keyboard(check_type),
            )
            sent += 1

            attempt = await presence_attempt(check_type, tg_id)
            if attempt.get("needs_admin_alert"):
                name = check.get("full_name") or str(tg_id)
                await notify_admins(f"⚠️ {name}: 3 попытки без подтверждения ({check_type}). Нужно проверить.")
        except Exception:
            pass

    await notify_admins(f"📡 Presence {check_type}: попытка {attempt_no}/3 отправлена ({sent} чел.)")


async def send_checkin():
    await send_presence_attempt("evening", attempt_no=1, create_check=True)


async def check_missing():
    await escalate_presence("evening")


async def check_wakeup_missing():
    await escalate_presence("morning")


async def send_morning_presence():
    await send_presence_attempt("morning", attempt_no=1, create_check=True)


async def retry_evening_presence(attempt_no):
    await send_presence_attempt("evening", attempt_no=attempt_no, create_check=False)


async def retry_morning_presence(attempt_no):
    await send_presence_attempt("morning", attempt_no=attempt_no, create_check=False)


async def escalate_presence(check_type):
    if not reminders_enabled:
        return

    data = await presence_escalate(check_type)
    rows = data.get("needs_attention", [])
    if not rows:
        await notify_admins(f"✅ Presence {check_type}: все в порядке, тревог нет.")
        return

    text = f"🚨 Presence {check_type}: нужно проверить вручную\n\n"
    for row in rows:
        text += f"• {row.get('full_name') or row.get('telegram_id')} — {row.get('attempts_sent', 0)} попытки\n"
    await notify_admins(text)


async def penalize_presence(check_type):
    if not reminders_enabled:
        return

    data = await presence_penalize(check_type, PRESENCE_PENALTY_POINTS)
    penalized = data.get("penalized", [])
    if not penalized:
        await notify_admins(f"✅ Presence {check_type}: штрафовать некого.")
        return

    text = f"⚠️ Presence {check_type}: применён штраф -{PRESENCE_PENALTY_POINTS}★\n\n"
    for row in penalized:
        tg_id = row.get("telegram_id")
        name = row.get("full_name") or str(tg_id)
        text += f"• {name}\n"
        try:
            await bot.send_message(
                tg_id,
                f"⚠️ Отметка {check_type} не подтверждена.\n"
                f"Списано -{PRESENCE_PENALTY_POINTS}★."
            )
        except Exception:
            pass
    await notify_admins(text)
```

## 5. Callback handlers

```python
@dp.callback_query(lambda c: c.data and c.data.startswith("presence:"))
async def presence_child_callback(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Некорректная кнопка", show_alert=True)
        return

    _, check_type, action = parts
    user_id = callback.from_user.id

    try:
        if action == "confirm":
            await presence_confirm(user_id, check_type, "confirm")
            text = "✅ Отметка принята. Спасибо!"
        elif action == "free_time":
            await presence_confirm(user_id, check_type, "free_time")
            text = "🕐 Активное «Свободное время» принято. Админы увидят статус."
        elif action == "request_leave":
            await presence_confirm(user_id, check_type, "request_leave", "Запрос через Telegram bot")
            text = "🙋 Запрос отправлен админам. Дождись подтверждения."
            name = callback.from_user.full_name or callback.from_user.first_name or str(user_id)
            await notify_admins(
                f"🙋 Запрос отгула ({check_type})\n\n{name} / `{user_id}` просит разрешение.",
                reply_markup=get_presence_admin_keyboard(check_type, user_id),
            )
        else:
            await callback.answer("Неизвестное действие", show_alert=True)
            return

        await callback.message.edit_text(text)
        await callback.answer()
    except Exception as e:
        await callback.answer(str(e), show_alert=True)


@dp.callback_query(lambda c: c.data and c.data.startswith("presence_admin:"))
async def presence_admin_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет прав администратора", show_alert=True)
        return

    parts = callback.data.split(":")
    if len(parts) != 4:
        await callback.answer("Некорректная кнопка", show_alert=True)
        return

    _, action, check_type, tg_id_raw = parts
    tg_id = int(tg_id_raw)

    try:
        if action == "approve":
            await presence_approve(tg_id, check_type, callback.from_user.id, "admin_approved from bot")
            await callback.message.edit_text(f"✅ Разрешение выдано: {tg_id} ({check_type})")
            try:
                await bot.send_message(tg_id, "✅ Админ разрешил отгул. Статус отмечен.")
            except Exception:
                pass
        elif action == "reject":
            await presence_reject(tg_id, check_type, callback.from_user.id, "rejected from bot")
            await callback.message.edit_text(f"❌ Отгул отклонён: {tg_id} ({check_type})")
            try:
                await bot.send_message(
                    tg_id,
                    "❌ Отгул отклонён. Нужно подтвердить отметку.",
                    reply_markup=get_presence_keyboard(check_type),
                )
            except Exception:
                pass
        else:
            await callback.answer("Неизвестное действие", show_alert=True)
            return

        await callback.answer()
    except Exception as e:
        await callback.answer(str(e), show_alert=True)
```

## 6. Команды

В `/admin` добавь:

```python
"/подъем — запустить утреннюю отметку вручную\n"
"/presence morning|evening — статус отметки\n"
```

Добавь новые команды:

```python
@dp.message(Command("подъем"))
async def manual_morning_presence(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора.")
        return
    await message.answer("✅ Запускаю утреннюю отметку...")
    await send_morning_presence()


@dp.message(Command("presence"))
async def presence_status_cmd(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора.")
        return

    args = message.text.split()
    check_type = args[1] if len(args) > 1 else "evening"
    if check_type not in ("morning", "evening"):
        await message.answer("Использование: /presence morning или /presence evening")
        return

    data = await presence_overview(check_type)
    counts = data.get("counts", {})
    text = f"📊 Presence {check_type}\n\n"
    for key, value in counts.items():
        text += f"• {key}: {value}\n"
    await message.answer(text)
```

Команду `/проснулся` замени на:

```python
@dp.message(Command("проснулся"))
async def woke_up(message: types.Message):
    try:
        await presence_confirm(message.from_user.id, "morning", "confirm")
        await message.answer("✅ Подъём подтверждён. Доброе утро!")
        await notify_admins(f"✅ {message.from_user.first_name} подтвердил подъём.")
    except Exception as e:
        await message.answer(f"❌ Не удалось подтвердить подъём: {e}")
```

## 7. Scheduler в `main()`

Замени старые задачи:

```python
scheduler.add_job(send_checkin, CronTrigger(hour=21, minute=0, timezone=BEIJING_TZ))
scheduler.add_job(send_goodnight, CronTrigger(hour=22, minute=0, timezone=BEIJING_TZ))
scheduler.add_job(check_wakeup_missing, CronTrigger(hour=8, minute=0, timezone=BEIJING_TZ))
```

на:

```python
scheduler.add_job(send_checkin, CronTrigger(hour=21, minute=0, timezone=BEIJING_TZ))
scheduler.add_job(retry_evening_presence, CronTrigger(hour=21, minute=15, timezone=BEIJING_TZ), args=[2])
scheduler.add_job(retry_evening_presence, CronTrigger(hour=21, minute=30, timezone=BEIJING_TZ), args=[3])
scheduler.add_job(check_missing, CronTrigger(hour=21, minute=45, timezone=BEIJING_TZ))
scheduler.add_job(send_goodnight, CronTrigger(hour=22, minute=0, timezone=BEIJING_TZ))
scheduler.add_job(penalize_presence, CronTrigger(hour=22, minute=10, timezone=BEIJING_TZ), args=["evening"])

scheduler.add_job(send_morning_presence, CronTrigger(hour=7, minute=30, timezone=BEIJING_TZ))
scheduler.add_job(retry_morning_presence, CronTrigger(hour=7, minute=40, timezone=BEIJING_TZ), args=[2])
scheduler.add_job(retry_morning_presence, CronTrigger(hour=7, minute=50, timezone=BEIJING_TZ), args=[3])
scheduler.add_job(check_wakeup_missing, CronTrigger(hour=8, minute=0, timezone=BEIJING_TZ))
scheduler.add_job(penalize_presence, CronTrigger(hour=8, minute=15, timezone=BEIJING_TZ), args=["morning"])
```

Остальные ежедневные пассивки (`netwatch_morning`, `caishen_morning`, `qilin_morning`) оставь как есть.

## 8. Проверка на сервере

```bash
python3 -m py_compile /root/zhidao_bot.py
systemctl restart zhidao_bot.service
systemctl status zhidao_bot.service --no-pager
journalctl -u zhidao_bot.service -n 80 --no-pager
```

Ручной тест в Telegram:

```text
/напоминания вкл
/перекличка
/presence evening
/подъем
/presence morning
```
