import asyncio
import re
import sqlite3
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram import F
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

BOT_TOKEN = "PASTE_BOT_TOKEN_HERE"
MARZBAN_URL = "http://127.0.0.1:8000"
MARZBAN_USER = "marucho"
MARZBAN_PASS = "PASTE_MARZBAN_PASSWORD_HERE"
ADMIN_IDS = [389741116, 244487659, 1190015933, 491711713, 463135292, 8222459731]
WEATHER_API_KEY = "PASTE_WEATHER_API_KEY_HERE"
BEIJING_CITY_ID = "1816670"
MINI_APP_URL = "https://maruchoatomoshi.github.io/zhidao-protocol"
BEIJING_TZ = pytz.timezone("Asia/Shanghai")

API_URL = "https://127.0.0.1:8443"
PRESENCE_ADMIN_ID = ADMIN_IDS[0]
PRESENCE_PENALTY_POINTS = 50
PRESENCE_RETRY_STATUSES = {"pending", "leave_rejected"}
PRESENCE_STATUS_LABELS = {
    "pending": "Ожидают ответа",
    "confirmed": "Подтвердили",
    "free_time": "Свободное время",
    "leave_requested": "Запросили отгул",
    "admin_approved": "Разрешено админом",
    "leave_rejected": "Отгул отклонён",
    "needs_attention": "Нужно проверить",
    "penalized": "Оштрафованы",
    "skipped": "Пропущены",
}
PRESENCE_STATUS_ORDER = [
    "pending",
    "confirmed",
    "free_time",
    "leave_requested",
    "admin_approved",
    "leave_rejected",
    "needs_attention",
    "penalized",
    "skipped",
]
PRESENCE_TYPE_LABELS = {
    "morning": "утренняя отметка",
    "evening": "вечерняя отметка",
}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler(timezone=BEIJING_TZ)

reminders_enabled = False
pending_codes = {}


class Form(StatesGroup):
    waiting_name = State()


def init_db():
    conn = sqlite3.connect("/root/zhidao.db")
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS users
                 (code TEXT PRIMARY KEY,
                  marzban_username TEXT,
                  telegram_id INTEGER,
                  full_name TEXT,
                  points INTEGER DEFAULT 0)"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS dragon_actions
                 (telegram_id INTEGER PRIMARY KEY,
                  last_rob TEXT DEFAULT NULL,
                  last_transfer TEXT DEFAULT NULL)"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS expected_students
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  full_name TEXT NOT NULL,
                  normalized_name TEXT UNIQUE NOT NULL,
                  group_label TEXT DEFAULT '',
                  room_number TEXT DEFAULT NULL,
                  telegram_id INTEGER DEFAULT NULL,
                  status TEXT DEFAULT 'pending',
                  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                  updated_at TEXT DEFAULT CURRENT_TIMESTAMP)"""
    )
    conn.commit()
    conn.close()


def get_marzban_user(code):
    conn = sqlite3.connect("/root/zhidao.db")
    c = conn.cursor()
    c.execute("SELECT marzban_username FROM users WHERE code=?", (code,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None


def add_user(code, marzban_username):
    conn = sqlite3.connect("/root/zhidao.db")
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO users (code, marzban_username) VALUES (?,?)",
        (code, marzban_username),
    )
    conn.commit()
    conn.close()


def save_telegram_id(code, telegram_id, full_name):
    conn = sqlite3.connect("/root/zhidao.db")
    c = conn.cursor()
    c.execute(
        "UPDATE users SET telegram_id=?, full_name=? WHERE code=?",
        (telegram_id, full_name, code),
    )
    conn.commit()
    conn.close()


def normalize_registration_name(value):
    text = str(value or "").replace("\t", " ").replace("Ё", "Е").replace("ё", "е")
    return re.sub(r"\s+", " ", text.strip()).lower()


def is_cyrillic_full_name(value):
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return bool(re.fullmatch(r"[А-Яа-яЁё][А-Яа-яЁё'\-]+ [А-Яа-яЁё][А-Яа-яЁё'\-]+(?: [А-Яа-яЁё][А-Яа-яЁё'\-]+)?", text))


def validate_expected_student_name(full_name, telegram_id):
    if telegram_id in ADMIN_IDS or full_name == "舒珩 佟佳":
        return True, full_name, ""

    if not is_cyrillic_full_name(full_name):
        return False, full_name, "ФИО нужно ввести кириллицей: Фамилия Имя."

    normalized = normalize_registration_name(full_name)
    conn = sqlite3.connect("/root/zhidao.db")
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='expected_students'")
    if not c.fetchone():
        conn.close()
        return True, full_name, ""

    c.execute("SELECT COUNT(*) FROM expected_students")
    if (c.fetchone()[0] or 0) == 0:
        conn.close()
        return True, full_name, ""

    c.execute(
        "SELECT full_name, telegram_id FROM expected_students WHERE normalized_name=?",
        (normalized,),
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return False, full_name, "ФИО не найдено в списке участников. Проверь написание или обратись к администратору."

    canonical_name, linked_telegram_id = row
    if linked_telegram_id and int(linked_telegram_id) != int(telegram_id):
        return False, canonical_name, "Это ФИО уже привязано к другому Telegram аккаунту. Обратись к администратору."

    return True, canonical_name, ""


def link_expected_student(full_name, telegram_id):
    normalized = normalize_registration_name(full_name)
    conn = sqlite3.connect("/root/zhidao.db")
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='expected_students'")
    if not c.fetchone():
        conn.close()
        return
    c.execute(
        """UPDATE expected_students
           SET telegram_id=?, status='registered', updated_at=CURRENT_TIMESTAMP
           WHERE normalized_name=?""",
        (telegram_id, normalized),
    )
    conn.commit()
    conn.close()


def get_all_users():
    conn = sqlite3.connect("/root/zhidao.db")
    c = conn.cursor()
    c.execute("SELECT telegram_id, full_name FROM users WHERE telegram_id IS NOT NULL")
    result = c.fetchall()
    conn.close()
    return result


def get_all_telegram_ids():
    return [row[0] for row in get_all_users()]


def is_admin(user_id):
    return user_id in ADMIN_IDS


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


async def presence_cancel(check_type, admin_id, reason="manual cancel from bot"):
    return await api_request(
        "POST",
        "/api/presence/admin/cancel",
        {
            "check_type": check_type,
            "admin_id": admin_id,
            "reason": reason,
        },
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


def has_dragon(telegram_id):
    conn = sqlite3.connect("/root/zhidao.db")
    c = conn.cursor()
    c.execute(
        "SELECT id FROM user_implants WHERE telegram_id=? AND implant_id='implant_red_dragon' AND durability > 0",
        (telegram_id,),
    )
    result = c.fetchone()
    conn.close()
    return bool(result)


def change_points(telegram_id, delta):
    conn = sqlite3.connect("/root/zhidao.db")
    c = conn.cursor()
    c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (delta, telegram_id))
    conn.commit()
    conn.close()


def get_points(telegram_id):
    conn = sqlite3.connect("/root/zhidao.db")
    c = conn.cursor()
    c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else 0


def get_leaderboard():
    conn = sqlite3.connect("/root/zhidao.db")
    c = conn.cursor()
    placeholders = ",".join("?" for _ in ADMIN_IDS)
    c.execute(
        f"""SELECT full_name, points FROM users
            WHERE telegram_id IS NOT NULL AND telegram_id NOT IN ({placeholders})
            ORDER BY points DESC LIMIT 10""",
        ADMIN_IDS,
    )
    result = c.fetchall()
    conn.close()
    return result


def find_user_by_name(query):
    conn = sqlite3.connect("/root/zhidao.db")
    c = conn.cursor()
    c.execute(
        "SELECT telegram_id, full_name, points FROM users WHERE full_name LIKE ?",
        (f"%{query}%",),
    )
    result = c.fetchone()
    conn.close()
    return result


async def get_token():
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{MARZBAN_URL}/api/admin/token",
            data={"username": MARZBAN_USER, "password": MARZBAN_PASS},
        ) as r:
            data = await r.json()
            return data.get("access_token")


async def get_user_link(marzban_username):
    token = await get_token()
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{MARZBAN_URL}/api/user/{marzban_username}",
            headers={"Authorization": f"Bearer {token}"},
        ) as r:
            data = await r.json()
            links = data.get("links", [])
            return links[0] if links else None


def get_mini_app_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Открыть ZHIDAO Protocol",
                    web_app=WebAppInfo(url=MINI_APP_URL),
                )
            ]
        ]
    )


def get_presence_keyboard(check_type):
    if check_type == "morning":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Я проснулся", callback_data="presence:morning:confirm"),
                    InlineKeyboardButton(text="🙋 Нужна помощь", callback_data="presence:morning:request_leave"),
                ]
            ]
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Я в комнате", callback_data="presence:evening:confirm")],
            [
                InlineKeyboardButton(text="🕐 Свободное время", callback_data="presence:evening:free_time"),
                InlineKeyboardButton(text="🙋 Нужен отгул", callback_data="presence:evening:request_leave"),
            ],
        ]
    )


def get_checkin_keyboard():
    return get_presence_keyboard("evening")


def get_presence_admin_keyboard(check_type, telegram_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Разрешить",
                    callback_data=f"presence_admin:approve:{check_type}:{telegram_id}",
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"presence_admin:reject:{check_type}:{telegram_id}",
                ),
            ]
        ]
    )


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
                f"⚠️ Отметка {check_type} не подтверждена.\nСписано -{PRESENCE_PENALTY_POINTS}★.",
            )
        except Exception:
            pass
    await notify_admins(text)


async def send_goodnight():
    if not reminders_enabled:
        return
    ids = get_all_telegram_ids()
    for tg_id in ids:
        try:
            await bot.send_message(
                tg_id,
                "🌙 Отбой!\n\n"
                "Спокойной ночи! Завтра занятия — не проспи! ⏰\n"
                "Телефоны на зарядку 📱",
            )
        except Exception:
            pass


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
                f"🙋 Запрос отгула ({check_type})\n\n{name} / {user_id} просит разрешение.",
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


@dp.message(lambda m: m.location is not None)
async def handle_location(message: types.Message):
    lat = message.location.latitude
    lon = message.location.longitude
    name = message.from_user.first_name
    await message.answer("✅ Геолокация получена.", reply_markup=ReplyKeyboardRemove())
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, f"📍 {name} отправил геолокацию:")
            await bot.send_location(admin_id, latitude=lat, longitude=lon)
        except Exception:
            pass


@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    args = message.text.split()
    if len(args) > 1:
        code = args[1]
        marzban_user = get_marzban_user(code)
        if marzban_user:
            pending_codes[message.from_user.id] = code
            await state.set_state(Form.waiting_name)
            await message.answer(
                "👋 Добро пожаловать в ZHIDAO Protocol!\n\n"
                "Пожалуйста, введите ваше имя и фамилию:\n"
                "_(например: Иван Иванов)_",
                parse_mode="Markdown",
            )
        else:
            await message.answer("❌ Неверный код. Обратитесь к администратору: @christianpastor")
    else:
        await message.answer(
            "👋 Добро пожаловать в ZHIDAO Protocol!\n\n"
            "Введите ваш код активации:\n/start ВАШ_КОД",
            reply_markup=get_mini_app_keyboard(),
        )


@dp.message(Form.waiting_name)
async def process_name(message: types.Message, state: FSMContext):
    full_name = message.text.strip()
    user_id = message.from_user.id
    code = pending_codes.get(user_id)
    if not code:
        await message.answer("❌ Ошибка. Попробуйте снова через /start КОД")
        await state.clear()
        return
    is_valid_name, canonical_name, validation_error = validate_expected_student_name(full_name, user_id)
    if not is_valid_name:
        await message.answer(
            "❌ Не удалось подтвердить ФИО.\n\n"
            f"{validation_error}\n\n"
            "Введи имя ещё раз в формате: Фамилия Имя"
        )
        return
    full_name = canonical_name
    save_telegram_id(code, user_id, full_name)
    link_expected_student(full_name, user_id)
    del pending_codes[user_id]
    await state.clear()
    marzban_user = get_marzban_user(code)
    link = await get_user_link(marzban_user)
    if link:
        await message.answer(
            f"✅ Отлично, {full_name}!\n\n"
            f"Ваш конфиг для ZHIDAO Protocol:\n\n"
            f"`{link}`\n\n"
            f"📖 Скопируйте ссылку и добавьте в Happ",
            parse_mode="Markdown",
            reply_markup=get_mini_app_keyboard(),
        )
    else:
        await message.answer("❌ Ошибка получения конфига. Обратитесь к администратору: @christianpastor")


@dp.message(Command("help", "помощь"))
async def help_cmd(message: types.Message):
    await message.answer(
        "📖 Инструкция по установке:\n\n"
        "1️⃣ Скачайте Happ\n"
        "2️⃣ Напишите /start ВАШ_КОД\n"
        "3️⃣ Скопируйте конфиг от бота и добавьте в Happ\n"
        "4️⃣ Откройте Mini App кнопкой ниже",
        reply_markup=get_mini_app_keyboard(),
    )


@dp.message(Command("myid", "мойid"))
async def myid(message: types.Message):
    await message.answer(f"Ваш Telegram ID: `{message.from_user.id}`", parse_mode="Markdown")


@dp.message(Command("weather", "погода"))
async def weather(message: types.Message):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://api.openweathermap.org/data/2.5/weather",
                params={
                    "id": BEIJING_CITY_ID,
                    "appid": WEATHER_API_KEY,
                    "units": "metric",
                    "lang": "ru",
                },
            ) as r:
                data = await r.json()
                temp = round(data["main"]["temp"])
                feels = round(data["main"]["feels_like"])
                desc = data["weather"][0]["description"].capitalize()
                humidity = data["main"]["humidity"]
                wind = data["wind"]["speed"]
                await message.answer(
                    f"🌤 Погода в Пекине:\n\n"
                    f"🌡 Температура: {temp}°C (ощущается как {feels}°C)\n"
                    f"☁️ {desc}\n"
                    f"💧 Влажность: {humidity}%\n"
                    f"💨 Ветер: {wind} м/с"
                )
    except Exception:
        await message.answer("❌ Не удалось получить погоду. Попробуйте позже.")


@dp.message(F.voice)
async def debug_voice(message: types.Message):
    await message.answer(f"VOICE file_id:\n{message.voice.file_id}")


@dp.message(F.audio)
async def debug_audio(message: types.Message):
    await message.answer(f"AUDIO file_id:\n{message.audio.file_id}")


@dp.message(F.document)
async def debug_document(message: types.Message):
    await message.answer(f"DOCUMENT file_id:\n{message.document.file_id}")


@dp.message(Command("баллы", "points"))
async def my_points(message: types.Message):
    points = get_points(message.from_user.id)
    lb = get_leaderboard()
    rank = next((i + 1 for i, (name, p) in enumerate(lb) if p == points), "—")
    await message.answer(
        f"⭐ Ваши баллы: *{points}*\n🏆 Место в рейтинге: {rank}",
        parse_mode="Markdown",
    )


@dp.message(Command("рейтинг", "leaderboard"))
async def leaderboard(message: types.Message):
    lb = get_leaderboard()
    if not lb:
        await message.answer("Рейтинг пока пуст.")
        return
    medals = ["🥇", "🥈", "🥉"]
    text = "🏆 Рейтинг группы:\n\n"
    for i, (name, points) in enumerate(lb):
        medal = medals[i] if i < 3 else f"{i + 1}."
        text += f"{medal} {name or 'Аноним'} — {points} баллов\n"
    await message.answer(text)


@dp.message(Command("напоминания"))
async def toggle_reminders(message: types.Message):
    global reminders_enabled
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора.")
        return
    args = message.text.split()
    if len(args) < 2 or args[1] not in ["вкл", "выкл"]:
        status = "✅ включены" if reminders_enabled else "❌ выключены"
        await message.answer(
            f"Напоминания сейчас: {status}\n\n"
            "Использование:\n"
            "/напоминания вкл — включить\n"
            "/напоминания выкл — выключить"
        )
        return
    reminders_enabled = args[1] == "вкл"
    if reminders_enabled:
        await message.answer(
            "✅ Напоминания включены!\n\n"
            "• 07:30/07:40/07:50 — подъём\n"
            "• 21:00/21:15/21:30 — вечерняя отметка\n"
            "• 22:00 — отбой"
        )
    else:
        await message.answer("❌ Напоминания выключены.")


@dp.message(Command("admin"))
async def admin_help(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора.")
        return
    status = "✅ вкл" if reminders_enabled else "❌ выкл"
    await message.answer(
        "👑 Команды администратора:\n\n"
        "/adduser КОД USERNAME — добавить пользователя\n"
        "/listusers — список пользователей\n"
        "/broadcast ТЕКСТ — рассылка всем\n"
        "/разбудить ИМЯ — будильник\n"
        "/перекличка — запустить вечернюю отметку\n"
        "/подъем — запустить утреннюю отметку\n"
        "/presence morning|evening — статус отметки\n"
        "/отмена morning|evening — отменить случайную отметку\n"
        "/award ИМЯ БАЛЛЫ ПРИЧИНА — начислить баллы\n"
        "/penalize ИМЯ БАЛЛЫ ПРИЧИНА — снять баллы\n"
        "/зп СУММА — воскресная зарплата\n"
        f"/напоминания вкл|выкл — сейчас {status}\n"
        "/admin — это меню"
    )


@dp.message(Command("adduser", "добавить"))
async def add_user_cmd(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора.")
        return
    args = message.text.split()
    if len(args) != 3:
        await message.answer("Использование: /adduser КОД MARZBAN_USERNAME")
        return
    add_user(args[1], args[2])
    await message.answer(f"✅ Добавлен: код {args[1]} → {args[2]}")


@dp.message(Command("listusers", "список"))
async def list_users(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора.")
        return
    conn = sqlite3.connect("/root/zhidao.db")
    c = conn.cursor()
    c.execute("SELECT code, marzban_username, telegram_id, full_name, points FROM users")
    users = c.fetchall()
    conn.close()
    if not users:
        await message.answer("Список пользователей пуст.")
        return
    text = "👥 Пользователи:\n\n"
    for code, username, tg_id, full_name, points in users:
        tg = str(tg_id) if tg_id else "не активирован"
        name = full_name if full_name else "имя не указано"
        pts = points if points else 0
        text += f"• {name} | {pts}⭐ | TG: {tg}\n"
    await message.answer(text)


@dp.message(Command("broadcast", "рассылка"))
async def broadcast(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора.")
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /broadcast ТЕКСТ")
        return
    sent = 0
    for tg_id in get_all_telegram_ids():
        try:
            await bot.send_message(tg_id, f"📢 Объявление:\n\n{args[1]}")
            sent += 1
        except Exception:
            pass
    await message.answer(f"✅ Отправлено {sent} пользователям.")


@dp.message(Command("перекличка"))
async def manual_checkin(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора.")
        return
    await message.answer("✅ Запускаю вечернюю отметку...")
    await send_checkin()


@dp.message(Command("подъем"))
async def manual_morning_presence(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора.")
        return
    await message.answer("✅ Запускаю утреннюю отметку...")
    await send_morning_presence()


@dp.message(Command("отмена", "presence_cancel"))
async def presence_cancel_cmd(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора.")
        return

    args = message.text.split(maxsplit=2)
    check_type = args[1] if len(args) > 1 else "evening"
    reason = args[2] if len(args) > 2 else "Отменено администратором"

    if check_type not in ("morning", "evening"):
        await message.answer("Использование: /отмена morning или /отмена evening")
        return

    try:
        data = await presence_cancel(check_type, message.from_user.id, reason)
        cancelled = data.get("cancelled", 0)
        label = PRESENCE_TYPE_LABELS.get(check_type, check_type)
        await message.answer(f"✅ {label.capitalize()} отменена.\nСтатусов сброшено: {cancelled}")
    except Exception as e:
        await message.answer(f"❌ Не удалось отменить отметку: {e}")


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
    label = PRESENCE_TYPE_LABELS.get(check_type, check_type)
    text = f"📊 {label.capitalize()}\n\n"
    for key in PRESENCE_STATUS_ORDER:
        text += f"• {PRESENCE_STATUS_LABELS.get(key, key)}: {counts.get(key, 0)}\n"
    await message.answer(text)


@dp.message(Command("award"))
async def award_points(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора.")
        return
    args = message.text.split(maxsplit=3)
    if len(args) < 4:
        await message.answer("Использование: /award ИМЯ БАЛЛЫ ПРИЧИНА")
        return
    name_query, points_str, reason = args[1], args[2], args[3]
    try:
        points = int(points_str)
    except Exception:
        await message.answer("❌ Баллы должны быть числом")
        return
    user = find_user_by_name(name_query)
    if not user:
        await message.answer(f"❌ Пользователь '{name_query}' не найден")
        return
    tg_id, full_name, current_points = user
    dragon_bonus = ""
    if has_dragon(tg_id):
        points = int(points * 1.2)
        dragon_bonus = " (+20% 🐉)"
    change_points(tg_id, points)
    new_points = current_points + points
    await message.answer(f"✅ {full_name}: +{points} баллов{dragon_bonus} ({reason})\nИтого: {new_points} баллов")
    try:
        await bot.send_message(tg_id, f"⭐ Вам начислено +{points} баллов!{dragon_bonus}\nПричина: {reason}\nВсего баллов: {new_points}")
    except Exception:
        pass


@dp.message(Command("penalize"))
async def penalize_points(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора.")
        return
    args = message.text.split(maxsplit=3)
    if len(args) < 4:
        await message.answer("Использование: /penalize ИМЯ БАЛЛЫ ПРИЧИНА")
        return
    name_query, points_str, reason = args[1], args[2], args[3]
    try:
        points = int(points_str)
    except Exception:
        await message.answer("❌ Баллы должны быть числом")
        return
    user = find_user_by_name(name_query)
    if not user:
        await message.answer(f"❌ Пользователь '{name_query}' не найден")
        return
    tg_id, full_name, current_points = user
    conn = sqlite3.connect("/root/zhidao.db")
    c = conn.cursor()
    c.execute("SELECT immunity FROM user_status WHERE telegram_id=?", (tg_id,))
    status = c.fetchone()
    has_immunity = status and status[0] == 1
    if has_immunity:
        c.execute(
            """INSERT INTO user_status (telegram_id, immunity) VALUES (?,0)
               ON CONFLICT(telegram_id) DO UPDATE SET immunity=0""",
            (tg_id,),
        )
        conn.commit()
        conn.close()
        await message.answer(f"🛡 {full_name} использовал иммунитет! Штраф -{points}★ отменён.")
        return
    conn.close()
    change_points(tg_id, -points)
    new_points = current_points - points
    await message.answer(f"⚠️ {full_name}: -{points}★ ({reason})\nИтого: {new_points}★")
    try:
        await bot.send_message(tg_id, f"⚠️ У вас снято -{points}★\nПричина: {reason}\nВсего баллов: {new_points}")
    except Exception:
        pass


@dp.message(Command("зп"))
async def salary(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Нет прав.")
        return
    args = message.text.split()
    amount = int(args[1]) if len(args) > 1 else 100
    users = get_all_users()
    conn = sqlite3.connect("/root/zhidao.db")
    c = conn.cursor()
    sent = 0
    for tg_id, full_name in users:
        if tg_id in ADMIN_IDS:
            continue
        c.execute(
            "SELECT id FROM user_implants WHERE telegram_id=? AND implant_id='implant_red_dragon' AND durability > 0",
            (tg_id,),
        )
        dragon = c.fetchone()
        final = amount * 2 if dragon else amount
        c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (final, tg_id))
        try:
            bonus_text = " (x2 🐉 Красный Дракон!)" if dragon else ""
            await bot.send_message(tg_id, f"💰 Воскресная зарплата: +{final}★{bonus_text}")
            sent += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    await message.answer(f"✅ Зарплата выдана {sent} игрокам.")


@dp.message(Command("разбудить"))
async def wake_up(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора.")
        return
    args = message.text.split(maxsplit=1)
    if len(args) != 2:
        await message.answer("Использование: /разбудить ИМЯ")
        return
    user = find_user_by_name(args[1].strip())
    if not user or not user[0]:
        await message.answer(f"❌ Пользователь '{args[1]}' не найден.")
        return
    target_id, full_name, _ = user
    try:
        for _ in range(3):
            await bot.send_message(
                target_id,
                "⏰⏰⏰ ПОДЪЁМ! ⏰⏰⏰\n\n"
                "Доброе утро! Не проспи завтрак! 🍳\n"
                "Нажми /проснулся чтобы подтвердить подъём",
            )
            await asyncio.sleep(1)
        await message.answer(f"✅ Будильник отправлен: {full_name}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@dp.message(Command("проснулся"))
async def woke_up(message: types.Message):
    try:
        await presence_confirm(message.from_user.id, "morning", "confirm")
        await message.answer("✅ Подъём подтверждён. Доброе утро!")
        await notify_admins(f"✅ {message.from_user.first_name} подтвердил подъём.")
    except Exception as e:
        await message.answer(f"❌ Не удалось подтвердить подъём: {e}")


@dp.message(Command("подарить"))
async def gift_item_cmd(message: types.Message):
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer("Использование: /подарить ИМЯ ID_ПРЕДМЕТА")
        return
    try:
        purchase_id = int(args[2])
    except Exception:
        await message.answer("❌ Неверный ID предмета — должно быть число")
        return
    recipient = find_user_by_name(args[1])
    if not recipient:
        await message.answer(f"❌ Пользователь '{args[1]}' не найден")
        return
    to_id, to_name, _ = recipient
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://hk.marucho.icu:8443/api/shop/gift",
            json={"purchase_id": purchase_id, "from_id": message.from_user.id, "to_id": to_id},
            ssl=False,
        ) as r:
            if r.status == 200:
                await message.answer(f"✅ Подарок отправлен {to_name}!\nНалог: -20★")
                try:
                    await bot.send_message(to_id, f"🎁 {message.from_user.first_name} подарил тебе предмет!")
                except Exception:
                    pass
            else:
                await message.answer("❌ Ошибка. Предмет не найден или уже использован.")


@dp.message(Command("вопрос"))
async def anonymous_question(message: types.Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /вопрос ТЕКСТ")
        return
    await message.answer("✅ Вопрос отправлен анонимно!")
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, f"🤫 Анонимный вопрос:\n\n{args[1]}")
        except Exception:
            pass


@dp.message(Command("netwatch_strike"))
async def netwatch_strike_cmd(message: types.Message):
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer("Использование: /netwatch_strike ИМЯ БАЛЛЫ")
        return
    try:
        points = int(args[2])
    except Exception:
        await message.answer("❌ Баллы должны быть числом")
        return
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://hk.marucho.icu:8443/api/netwatch/strike",
            json={"telegram_id": message.from_user.id, "target_name": args[1], "points": points},
            ssl=False,
        ) as r:
            if r.status == 200:
                data = await r.json()
                await message.answer(f"⚡ Скрипт запущен!\nЦель: {data['target']} (-{points}★)\nПобочный урон: {data['collateral']} игрока (-15★)")
            elif r.status == 403:
                await message.answer("❌ У тебя нет импланта Сетевой Дозор")
            elif r.status == 429:
                data = await r.json()
                await message.answer(f"⏳ Перезарядка: {data['detail']}")
            else:
                await message.answer("❌ Ошибка. Цель не найдена?")


@dp.message(Command("netwatch_blackwall"))
async def netwatch_blackwall_cmd(message: types.Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /netwatch_blackwall ИМЯ")
        return
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://hk.marucho.icu:8443/api/netwatch/blackwall",
            json={"telegram_id": message.from_user.id, "target_name": args[1]},
            ssl=False,
        ) as r:
            if r.status == 200:
                data = await r.json()
                await message.answer(f"🔴 Blackwall активирован!\nЦель: {data['target']}\nМагазин заблокирован на 24 часа")
            elif r.status == 403:
                await message.answer("❌ У тебя нет импланта Сетевой Дозор")
            elif r.status == 429:
                data = await r.json()
                await message.answer(f"⏳ Перезарядка: {data['detail']}")
            else:
                await message.answer("❌ Ошибка. Цель не найдена?")


async def netwatch_morning():
    conn = sqlite3.connect("/root/zhidao.db")
    c = conn.cursor()
    c.execute("SELECT DISTINCT telegram_id FROM user_implants WHERE implant_id='implant_netwatch' AND durability > 0")
    owners = c.fetchall()
    for (tg_id,) in owners:
        c.execute("UPDATE users SET points = points + 25 WHERE telegram_id=?", (tg_id,))
        try:
            await bot.send_message(tg_id, "🔴 +25★ // восполнение памяти NetWatch")
        except Exception:
            pass
    conn.commit()
    conn.close()


async def caishen_morning():
    conn = sqlite3.connect("/root/zhidao.db")
    c = conn.cursor()
    c.execute("SELECT DISTINCT telegram_id FROM user_implants WHERE implant_id='implant_caishen' AND durability > 0")
    owners = c.fetchall()
    for (tg_id,) in owners:
        c.execute("UPDATE users SET points = points + 15 WHERE telegram_id=?", (tg_id,))
        try:
            await bot.send_message(tg_id, "💰 +15★ // пассивный доход Цайшэня 财神")
        except Exception:
            pass
    conn.commit()
    conn.close()


async def qilin_morning():
    conn = sqlite3.connect("/root/zhidao.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(DISTINCT telegram_id) FROM user_implants WHERE implant_id='implant_qilin' AND durability > 0")
    total_owners = c.fetchone()[0]
    bonus = total_owners * 10
    c.execute("SELECT DISTINCT telegram_id FROM user_implants WHERE implant_id='implant_qilin' AND durability > 0")
    owners = c.fetchall()
    for (tg_id,) in owners:
        c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (bonus, tg_id))
        try:
            await bot.send_message(tg_id, f"🐉 +{bonus}★ // Цилинь麒麟 ({total_owners} владельцев × 10★)")
        except Exception:
            pass
    conn.commit()
    conn.close()


async def main():
    init_db()
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

    scheduler.add_job(netwatch_morning, CronTrigger(hour=8, minute=1, timezone=BEIJING_TZ))
    scheduler.add_job(caishen_morning, CronTrigger(hour=8, minute=2, timezone=BEIJING_TZ))
    scheduler.add_job(qilin_morning, CronTrigger(hour=8, minute=3, timezone=BEIJING_TZ))
    scheduler.start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
