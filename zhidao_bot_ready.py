import asyncio
import os
import re
import sqlite3
import aiohttp
from datetime import datetime
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
from apscheduler.triggers.interval import IntervalTrigger
import pytz

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
MARZBAN_URL = os.getenv("MARZBAN_URL", "http://127.0.0.1:8000")
MARZBAN_USER = os.getenv("MARZBAN_USER", "")
MARZBAN_PASS = os.getenv("MARZBAN_PASS", "")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "")
BEIJING_CITY_ID = "1816670"
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://example.com/zhidao-protocol")
BEIJING_TZ = pytz.timezone("Asia/Shanghai")

API_URL = os.getenv("API_URL", "https://127.0.0.1:8443")
API_INTERNAL_TOKEN = os.getenv("API_INTERNAL_TOKEN", "").strip()
DB_PATH = os.getenv("ZHIDAO_DB_PATH", "/root/zhidao.db")
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
    "manual": "ручная перекличка",
}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler(timezone=BEIJING_TZ)

reminders_enabled = False


def parse_int_list_env(name: str) -> list[int]:
    raw = os.getenv(name, "")
    result = []
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            result.append(int(part))
        except ValueError:
            continue
    return result


ADMIN_IDS = parse_int_list_env("ADMIN_IDS") or [-1]
COHORT_BEIJING = "beijing"
COHORT_MJU = "mju"
COHORT_CODES = (COHORT_BEIJING, COHORT_MJU)
MJU_ADMIN_IDS = frozenset(parse_int_list_env("MJU_ADMIN_IDS") or [244487659])
MJU_MEMBER_IDS = frozenset({
    5024821858, 5243992893, 5043234233, 5270862724, 1049679249,
    7366133308, 5973073048, 1324443747, 2055808907, 1295956600,
    244487659, 5983453551, 5306057873, 1541846222, 5220506877,
    5455635461, 5112589598, 5245376585, 5718009801, 5581257126,
    6480285200, 1192650264,
})
GLOBAL_ADMIN_IDS = frozenset(set(ADMIN_IDS) - set(MJU_ADMIN_IDS))
COHORT_ALIASES = {
    "мю": COHORT_MJU, "mju": COHORT_MJU,
    "пекин": COHORT_BEIJING, "beijing": COHORT_BEIJING,
}
FLATLINED_IDS = set(
    parse_int_list_env("FLATLINED_IDS")
    or [6157647579, 8579518402, 8580665130]
)
ARCHITECT_IDS = parse_int_list_env("ARCHITECT_IDS")
BUG_REPORT_RECIPIENT_IDS = parse_int_list_env("BUG_REPORT_RECIPIENT_IDS") or ARCHITECT_IDS or [ADMIN_IDS[0]]
REGISTRATION_BYPASS_IDS = set(parse_int_list_env("REGISTRATION_BYPASS_IDS"))
PRESENCE_ADMIN_ID = ADMIN_IDS[0]
ADMIN_CONTACT_USERNAME = os.getenv("ADMIN_CONTACT_USERNAME", "admin")
pending_codes = {}


def db_connect():
    # Match the API's connection settings. Without these PRAGMAs the bot ran at
    # synchronous=FULL, fsyncing on every commit; on this high-latency storage
    # that holds SQLite's single write lock for 100ms+ per commit and starves
    # the API's writes (observed as 15-27s stalls / black screen). NORMAL + WAL
    # means commits no longer fsync, so the bot releases the write lock fast.
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA wal_autocheckpoint=0")  # bot must not auto-checkpoint; the API owns WAL maintenance (hard rule, 2026-06-09)
    return conn


class Form(StatesGroup):
    waiting_name = State()
    waiting_bug_report = State()
    waiting_anon_reply = State()


def init_db():
    conn = db_connect()
    conn.execute("PRAGMA journal_mode=WAL")
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS users
                 (code TEXT PRIMARY KEY,
                  marzban_username TEXT,
                  telegram_id INTEGER,
                  full_name TEXT,
                  points INTEGER DEFAULT 0)"""
    )
    c.execute("PRAGMA table_info(users)")
    user_columns = {row[1] for row in c.fetchall()}
    if "cohort_code" not in user_columns:
        c.execute("ALTER TABLE users ADD COLUMN cohort_code TEXT NOT NULL DEFAULT 'beijing'")
    c.execute("UPDATE users SET cohort_code='beijing'")
    c.executemany(
        "UPDATE users SET cohort_code='mju' WHERE telegram_id=?",
        [(telegram_id,) for telegram_id in MJU_MEMBER_IDS],
    )
    c.execute("PRAGMA table_info(expected_students)")
    expected_columns = {row[1] for row in c.fetchall()}
    if expected_columns and "cohort_code" not in expected_columns:
        c.execute(
            "ALTER TABLE expected_students "
            "ADD COLUMN cohort_code TEXT NOT NULL DEFAULT 'beijing'"
        )
    if expected_columns:
        placeholders = ",".join("?" * len(MJU_MEMBER_IDS))
        c.execute(
            f"UPDATE expected_students SET cohort_code='mju' "
            f"WHERE telegram_id IN ({placeholders})",
            tuple(sorted(MJU_MEMBER_IDS)),
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
                  cohort_code TEXT NOT NULL DEFAULT 'beijing',
                  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                  updated_at TEXT DEFAULT CURRENT_TIMESTAMP)"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS bug_reports
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  telegram_id INTEGER NOT NULL,
                  full_name TEXT DEFAULT '',
                  username TEXT DEFAULT '',
                  text TEXT NOT NULL,
                  status TEXT DEFAULT 'open',
                  created_at TEXT NOT NULL)"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS anon_questions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  telegram_id INTEGER NOT NULL,
                  full_name TEXT DEFAULT '',
                  username TEXT DEFAULT '',
                  text TEXT NOT NULL,
                  created_at TEXT NOT NULL)"""
    )
    c.execute("PRAGMA table_info(anon_questions)")
    anon_q_columns = {row[1] for row in c.fetchall()}
    if 'status' not in anon_q_columns:
        c.execute("ALTER TABLE anon_questions ADD COLUMN status TEXT DEFAULT 'open'")
    if 'answered_by_name' not in anon_q_columns:
        c.execute("ALTER TABLE anon_questions ADD COLUMN answered_by_name TEXT DEFAULT NULL")
    if 'answered_at' not in anon_q_columns:
        c.execute("ALTER TABLE anon_questions ADD COLUMN answered_at TEXT DEFAULT NULL")
    conn.commit()
    conn.close()


def get_marzban_user(code):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT marzban_username FROM users WHERE code=?", (code,))
    result = c.fetchone()
    conn.close()
    if not result:
        return None
    return result[0] or ""


def code_exists(code):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT 1 FROM users WHERE code=?", (code,))
    result = c.fetchone()
    conn.close()
    return bool(result)


def add_user(code, marzban_username, cohort_code=COHORT_BEIJING):
    conn = db_connect()
    c = conn.cursor()
    cohort_code = normalize_cohort_code(cohort_code)
    c.execute(
        """INSERT INTO users (code, marzban_username, cohort_code)
           VALUES (?,?,?)
           ON CONFLICT(code) DO UPDATE SET
             marzban_username=excluded.marzban_username,
             cohort_code=CASE
               WHEN users.telegram_id IS NULL THEN excluded.cohort_code
               ELSE users.cohort_code
             END""",
        (code, marzban_username or None, cohort_code),
    )
    conn.commit()
    conn.close()


def get_code_cohort(code):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT cohort_code FROM users WHERE code=?", (code,))
    row = c.fetchone()
    conn.close()
    return normalize_cohort_code(row[0] if row else COHORT_BEIJING)


def save_telegram_id(code, telegram_id, full_name):
    conn = db_connect()
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


def validate_expected_student_name(full_name, telegram_id, cohort_code=COHORT_BEIJING):
    if telegram_id in ADMIN_IDS or telegram_id in REGISTRATION_BYPASS_IDS:
        return True, full_name, ""

    if not is_cyrillic_full_name(full_name):
        return False, full_name, "ФИО нужно ввести кириллицей: Фамилия Имя."

    normalized = normalize_registration_name(full_name)
    conn = db_connect()
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
        "SELECT full_name, telegram_id FROM expected_students "
        "WHERE normalized_name=? AND cohort_code=?",
        (normalized, normalize_cohort_code(cohort_code)),
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return False, full_name, "ФИО не найдено в списке участников. Проверь написание или обратись к администратору."

    canonical_name, linked_telegram_id = row
    if linked_telegram_id and int(linked_telegram_id) != int(telegram_id):
        return False, canonical_name, "Это ФИО уже привязано к другому Telegram аккаунту. Обратись к администратору."

    return True, canonical_name, ""


def link_expected_student(full_name, telegram_id, cohort_code=COHORT_BEIJING):
    normalized = normalize_registration_name(full_name)
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='expected_students'")
    if not c.fetchone():
        conn.close()
        return
    c.execute(
        """UPDATE expected_students
           SET telegram_id=?, status='registered', updated_at=CURRENT_TIMESTAMP
           WHERE normalized_name=? AND cohort_code=?""",
        (telegram_id, normalized, normalize_cohort_code(cohort_code)),
    )
    conn.commit()
    conn.close()


def normalize_cohort_code(value):
    return COHORT_MJU if str(value or "").strip().lower() == COHORT_MJU else COHORT_BEIJING


def get_user_cohort(telegram_id):
    if telegram_id in MJU_MEMBER_IDS or telegram_id in MJU_ADMIN_IDS:
        return COHORT_MJU
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT cohort_code FROM users WHERE telegram_id=?", (telegram_id,))
    row = c.fetchone()
    conn.close()
    return normalize_cohort_code(row[0] if row else COHORT_BEIJING)


def admins_for_cohort(cohort_code):
    cohort_code = normalize_cohort_code(cohort_code)
    result = set(GLOBAL_ADMIN_IDS)
    if cohort_code == COHORT_MJU:
        result.update(MJU_ADMIN_IDS)
    return sorted(result)


def parse_admin_cohort(admin_id, tokens, default=COHORT_BEIJING):
    tokens = list(tokens)
    if admin_id in MJU_ADMIN_IDS:
        if tokens and tokens[0].strip().lower() in COHORT_ALIASES:
            tokens.pop(0)
        return COHORT_MJU, tokens
    if tokens and tokens[0].strip().lower() in COHORT_ALIASES:
        return COHORT_ALIASES[tokens.pop(0).strip().lower()], tokens
    return normalize_cohort_code(default), tokens


def get_all_users(cohort_code=COHORT_BEIJING):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        "SELECT telegram_id, full_name FROM users "
        "WHERE telegram_id IS NOT NULL AND cohort_code=?",
        (normalize_cohort_code(cohort_code),),
    )
    result = c.fetchall()
    conn.close()
    return result


def get_all_telegram_ids(cohort_code=COHORT_BEIJING):
    return [row[0] for row in get_all_users(cohort_code)]


def get_setting(key, default=None):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default


def set_setting(key, value):
    conn = db_connect()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def is_admin(user_id):
    return user_id in ADMIN_IDS


def internal_api_headers(extra=None):
    headers = dict(extra or {})
    if API_INTERNAL_TOKEN:
        headers["x-internal-token"] = API_INTERNAL_TOKEN
    return headers


async def api_request(
    method,
    path,
    json_data=None,
    params=None,
    admin=False,
    admin_id=None,
    cohort_code=None,
):
    headers = {}
    if API_INTERNAL_TOKEN:
        headers["x-internal-token"] = API_INTERNAL_TOKEN
    if admin:
        headers["x-admin-id"] = str(admin_id or PRESENCE_ADMIN_ID)
    if cohort_code:
        headers["x-cohort-code"] = normalize_cohort_code(cohort_code)

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
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


async def presence_start(check_type, note="", cohort_code=COHORT_BEIJING, admin_id=PRESENCE_ADMIN_ID):
    return await api_request(
        "POST",
        "/api/presence/start",
        {"check_type": check_type, "note": note},
        admin=True,
        admin_id=admin_id,
        cohort_code=cohort_code,
    )


async def presence_attempt(check_type, telegram_id, cohort_code, admin_id=PRESENCE_ADMIN_ID):
    return await api_request(
        "POST",
        "/api/presence/attempt",
        {"check_type": check_type, "telegram_id": telegram_id},
        admin=True,
        admin_id=admin_id,
        cohort_code=cohort_code,
    )


async def presence_confirm(telegram_id, check_type, action, note="", check_date=None):
    return await api_request(
        "POST",
        "/api/presence/confirm",
        {
            "telegram_id": telegram_id,
            "check_type": check_type,
            "check_date": check_date,
            "action": action,
            "note": note,
        },
    )


async def presence_overview(check_type, cohort_code, admin_id=PRESENCE_ADMIN_ID):
    return await api_request(
        "GET",
        "/api/presence/admin/overview",
        params={"check_type": check_type},
        admin=True,
        admin_id=admin_id,
        cohort_code=cohort_code,
    )


async def presence_escalate(check_type, cohort_code, admin_id=PRESENCE_ADMIN_ID):
    return await api_request(
        "POST",
        "/api/presence/admin/escalate",
        {"check_type": check_type},
        admin=True,
        admin_id=admin_id,
        cohort_code=cohort_code,
    )


async def presence_penalize(
    check_type,
    cohort_code,
    penalty_points=PRESENCE_PENALTY_POINTS,
    admin_id=PRESENCE_ADMIN_ID,
):
    return await api_request(
        "POST",
        "/api/presence/admin/penalize",
        {"check_type": check_type, "penalty_points": penalty_points},
        admin=True,
        admin_id=admin_id,
        cohort_code=cohort_code,
    )


async def presence_cancel(check_type, admin_id, cohort_code, reason="manual cancel from bot"):
    return await api_request(
        "POST",
        "/api/presence/admin/cancel",
        {
            "check_type": check_type,
            "admin_id": admin_id,
            "reason": reason,
        },
        admin=True,
        admin_id=admin_id,
        cohort_code=cohort_code,
    )


async def presence_approve(telegram_id, check_type, admin_id, reason="admin_approved", check_date=None):
    cohort_code = get_user_cohort(telegram_id)
    return await api_request(
        "POST",
        "/api/presence/admin/approve",
        {
            "telegram_id": telegram_id,
            "check_type": check_type,
            "check_date": check_date,
            "admin_id": admin_id,
            "reason": reason,
        },
        admin=True,
        admin_id=admin_id,
        cohort_code=cohort_code,
    )


async def presence_reject(telegram_id, check_type, admin_id, reason="leave rejected", check_date=None):
    cohort_code = get_user_cohort(telegram_id)
    return await api_request(
        "POST",
        "/api/presence/admin/reject",
        {
            "telegram_id": telegram_id,
            "check_type": check_type,
            "check_date": check_date,
            "admin_id": admin_id,
            "reason": reason,
        },
        admin=True,
        admin_id=admin_id,
        cohort_code=cohort_code,
    )

def has_dragon(telegram_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        '''SELECT ui.id FROM user_implants ui
           LEFT JOIN user_status us ON us.telegram_id = ui.telegram_id
           WHERE ui.telegram_id=? AND ui.implant_id='implant_red_dragon' AND ui.durability > 0
             AND (COALESCE(us.theme_path, 'cyberpunk') != 'genshin' OR ui.telegram_id IN ({placeholders}))'''.format(
            placeholders=",".join("?" for _ in ADMIN_IDS) or "NULL"
        ),
        [telegram_id] + list(ADMIN_IDS),
    )
    result = c.fetchone()
    conn.close()
    return bool(result)


async def change_points(telegram_id, delta, operation='bot_manual', note=None):
    result = await api_request(
        "POST",
        "/api/internal/points/add",
        {
            "telegram_id": telegram_id,
            "delta": delta,
            "operation": operation,
            "note": note,
        },
    )
    return result["new_points"]


def get_points(telegram_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else 0


def get_leaderboard(cohort_code):
    conn = db_connect()
    c = conn.cursor()
    excluded_ids = sorted(set(ADMIN_IDS) | FLATLINED_IDS)
    placeholders = ",".join("?" for _ in excluded_ids)
    c.execute(
        f"""SELECT full_name, points FROM users
            WHERE telegram_id IS NOT NULL AND telegram_id NOT IN ({placeholders})
              AND cohort_code=?
            ORDER BY points DESC LIMIT 10""",
        excluded_ids + [normalize_cohort_code(cohort_code)],
    )
    result = c.fetchall()
    conn.close()
    return result


def find_user_by_name(query, cohort_code):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        "SELECT telegram_id, full_name, points FROM users WHERE full_name LIKE ? AND cohort_code=?",
        (f"%{query}%", normalize_cohort_code(cohort_code)),
    )
    result = c.fetchone()
    conn.close()
    return result


async def get_token():
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(
                f"{MARZBAN_URL}/api/admin/token",
                data={"username": MARZBAN_USER, "password": MARZBAN_PASS},
            ) as r:
                data = await r.json()
                return data.get("access_token")
    except Exception as exc:
        print("ZHIDAO_MARZBAN_TOKEN_ERROR %r" % (exc,), flush=True)
        return None


async def get_user_link(marzban_username):
    token = await get_token()
    if not token:
        return None
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(
                f"{MARZBAN_URL}/api/user/{marzban_username}",
                headers={"Authorization": f"Bearer {token}"},
            ) as r:
                data = await r.json()
                links = data.get("links") or []
                if links:
                    return links[0]
                subscription_url = data.get("subscription_url") or data.get("subscriptionUrl")
                return str(subscription_url).strip() if subscription_url else None
    except Exception as exc:
        print("ZHIDAO_MARZBAN_LINK_ERROR %r" % (exc,), flush=True)
        return None


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


def get_main_reply_keyboard(user_id: int | None = None):
    is_admin_user = bool(user_id and is_admin(user_id))
    keyboard = [
        [KeyboardButton(text="/баллы"), KeyboardButton(text="/вопрос")],
        [KeyboardButton(text="/bug"), KeyboardButton(text="/help")],
    ]
    if is_admin_user:
        keyboard.append([KeyboardButton(text="/напоминания"), KeyboardButton(text="/admin"), KeyboardButton(text="/bugs")])
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выберите команду или напишите сообщение",
    )


def get_presence_keyboard(check_type, check_date=None):
    if check_type == "morning":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Я проснулся", callback_data="presence:morning:confirm"),
                ]
            ]
        )
    if check_type == "manual":
        session = check_date or ""
        suffix = f":{session}" if session else ""
        return InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="✅ Я на месте", callback_data=f"presence:manual{suffix}:confirm"),
            ]]
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Я в комнате", callback_data="presence:evening:confirm")],
            [
                InlineKeyboardButton(text="🕐 Свободное время", callback_data="presence:evening:free_time"),
            ],
        ]
    )


def get_checkin_keyboard():
    return get_presence_keyboard("evening")


def get_presence_admin_keyboard(check_type, telegram_id, check_date=None):
    date_suffix = f":{check_date}" if check_date else ""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Разрешить",
                    callback_data=f"presence_admin:approve:{check_type}:{telegram_id}{date_suffix}",
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"presence_admin:reject:{check_type}:{telegram_id}{date_suffix}",
                ),
            ]
        ]
    )


async def notify_admins(text, reply_markup=None, cohort_code=COHORT_BEIJING):
    for admin_id in admins_for_cohort(cohort_code):
        try:
            await bot.send_message(admin_id, text, reply_markup=reply_markup)
        except Exception:
            pass


async def notify_bug_recipients(text):
    for admin_id in BUG_REPORT_RECIPIENT_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            pass


def save_bug_report(message: types.Message, text: str) -> int:
    full_name_parts = [
        message.from_user.first_name or "",
        message.from_user.last_name or "",
    ]
    fallback_name = " ".join(part for part in full_name_parts if part).strip()
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        "SELECT full_name FROM users WHERE telegram_id=?",
        (message.from_user.id,),
    )
    row = c.fetchone()
    full_name = (row[0] if row and row[0] else fallback_name) or str(message.from_user.id)
    username = message.from_user.username or ""
    now_str = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")
    c.execute(
        """INSERT INTO bug_reports
           (telegram_id, full_name, username, text, status, created_at)
           VALUES (?, ?, ?, ?, 'open', ?)""",
        (message.from_user.id, full_name, username, text.strip(), now_str),
    )
    report_id = c.lastrowid
    conn.commit()
    conn.close()
    return int(report_id)


def save_anon_question(message: types.Message, text: str) -> int:
    full_name = message.from_user.full_name or str(message.from_user.id)
    username = message.from_user.username or ""
    now_str = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """INSERT INTO anon_questions
           (telegram_id, full_name, username, text, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (message.from_user.id, full_name, username, text.strip(), now_str),
    )
    question_id = c.lastrowid
    conn.commit()
    conn.close()
    return int(question_id)


def get_anon_question(question_id: int):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        "SELECT telegram_id, full_name, status, answered_by_name FROM anon_questions WHERE id=?",
        (question_id,),
    )
    row = c.fetchone()
    conn.close()
    return row


def mark_anon_question_answered(question_id: int, admin_name: str):
    now_str = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        "UPDATE anon_questions SET status='answered', answered_by_name=?, answered_at=? WHERE id=?",
        (admin_name, now_str, question_id),
    )
    conn.commit()
    conn.close()


def get_recent_bug_reports(cohort_code, limit: int = 10):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """SELECT br.id, br.telegram_id, br.full_name, br.username, br.text, br.status, br.created_at
           FROM bug_reports br
           JOIN users u ON u.telegram_id=br.telegram_id
           WHERE u.cohort_code=?
           ORDER BY br.id DESC
           LIMIT ?""",
        (normalize_cohort_code(cohort_code), limit),
    )
    rows = c.fetchall()
    conn.close()
    return rows


async def submit_bug_report(message: types.Message, text: str):
    report_text = text.strip()
    if len(report_text) < 5:
        await message.answer(
            "Опиши проблему чуть подробнее: что нажал, что ожидал увидеть и что произошло."
        )
        return
    if len(report_text) > 2000:
        report_text = report_text[:2000] + "\n\n[обрезано ботом: сообщение было длиннее 2000 символов]"

    report_id = save_bug_report(message, report_text)
    username = f"@{message.from_user.username}" if message.from_user.username else "без username"
    await notify_bug_recipients(
        "🐞 BUG REPORT #{report_id}\n"
        "От: {name}\n"
        "TG: {tg_id} ({username})\n\n"
        "{text}".format(
            report_id=report_id,
            name=message.from_user.full_name,
            tg_id=message.from_user.id,
            username=username,
            text=report_text,
        )
    )
    await message.answer(
        f"✅ Баг-репорт #{report_id} отправлен.\n"
        "Если можешь, пришли скриншот или напиши, на каком экране это произошло.",
        reply_markup=get_main_reply_keyboard(message.from_user.id),
    )


def get_presence_message(check_type, attempt_no=1):
    if check_type == "morning":
        return (
            "🌅 Утренняя отметка\n\n"
            f"Попытка {attempt_no}/3. Нажми кнопку, чтобы подтвердить подъём."
        )
    if check_type == "manual":
        return (
            "📡 Ручная перекличка\n\n"
            f"Попытка {attempt_no}/3. Подтверди, что ты на месте.\n"
            "Если у тебя есть разрешение от админа, запроси отгул."
        )

    return (
        "🌙 Вечерняя отметка\n\n"
        f"Попытка {attempt_no}/3. 20:00 — нужно быть в комнате.\n"
        "Если у тебя разрешение от админа или активное «Свободное время», выбери нужную кнопку."
    )


async def send_presence_attempt(
    check_type,
    attempt_no=1,
    create_check=False,
    cohort_code=COHORT_BEIJING,
    admin_id=PRESENCE_ADMIN_ID,
):
    if not reminders_enabled:
        return

    cohort_code = normalize_cohort_code(cohort_code)
    if create_check:
        await presence_start(check_type, f"bot attempt {attempt_no}", cohort_code, admin_id)

    overview = await presence_overview(check_type, cohort_code, admin_id)
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
                reply_markup=get_presence_keyboard(check_type, overview.get("check_date")),
            )
            sent += 1
            attempt = await presence_attempt(check_type, tg_id, cohort_code, admin_id)
            if attempt.get("needs_admin_alert"):
                name = check.get("full_name") or str(tg_id)
                await notify_admins(
                    f"⚠️ {name}: 3 попытки без подтверждения ({check_type}). Нужно проверить.",
                    cohort_code=cohort_code,
                )
        except Exception:
            pass

    await notify_admins(
        f"📡 Presence {check_type}: попытка {attempt_no}/3 отправлена ({sent} чел.)",
        cohort_code=cohort_code,
    )


async def send_checkin():
    for cohort_code in COHORT_CODES:
        await send_presence_attempt("evening", attempt_no=1, create_check=True, cohort_code=cohort_code)


async def check_missing():
    for cohort_code in COHORT_CODES:
        await escalate_presence("evening", cohort_code)


async def check_wakeup_missing():
    for cohort_code in COHORT_CODES:
        await escalate_presence("morning", cohort_code)


async def send_morning_presence():
    for cohort_code in COHORT_CODES:
        await send_presence_attempt("morning", attempt_no=1, create_check=True, cohort_code=cohort_code)


async def retry_evening_presence(attempt_no):
    for cohort_code in COHORT_CODES:
        await send_presence_attempt("evening", attempt_no=attempt_no, create_check=False, cohort_code=cohort_code)


async def retry_morning_presence(attempt_no):
    for cohort_code in COHORT_CODES:
        await send_presence_attempt("morning", attempt_no=attempt_no, create_check=False, cohort_code=cohort_code)


async def escalate_presence(check_type, cohort_code, admin_id=PRESENCE_ADMIN_ID):
    if not reminders_enabled:
        return

    data = await presence_escalate(check_type, cohort_code, admin_id)
    rows = data.get("needs_attention", [])
    if not rows:
        await notify_admins(
            f"✅ Presence {check_type}: все в порядке, тревог нет.",
            cohort_code=cohort_code,
        )
        return

    text = f"🚨 Presence {check_type}: нужно проверить вручную\n\n"
    for row in rows:
        text += f"• {row.get('full_name') or row.get('telegram_id')} — {row.get('attempts_sent', 0)} попытки\n"
    await notify_admins(text, cohort_code=cohort_code)


async def penalize_presence(
    check_type,
    cohort_code=None,
    admin_id=PRESENCE_ADMIN_ID,
):
    if not reminders_enabled:
        return
    if cohort_code is None:
        for current_cohort in COHORT_CODES:
            await penalize_presence(check_type, current_cohort, admin_id)
        return

    data = await presence_penalize(
        check_type,
        cohort_code,
        PRESENCE_PENALTY_POINTS,
        admin_id,
    )
    penalized = data.get("penalized", [])
    if not penalized:
        await notify_admins(
            f"✅ Presence {check_type}: штрафовать некого.",
            cohort_code=cohort_code,
        )
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
    await notify_admins(text, cohort_code=cohort_code)


async def send_goodnight():
    if not reminders_enabled:
        return
    for cohort_code in COHORT_CODES:
        for tg_id in get_all_telegram_ids(cohort_code):
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
    if len(parts) not in (3, 4):
        await callback.answer("Некорректная кнопка", show_alert=True)
        return

    if len(parts) == 4:
        _, check_type, check_date, action = parts
    else:
        _, check_type, action = parts
        check_date = None
    user_id = callback.from_user.id

    try:
        if action == "confirm":
            await presence_confirm(user_id, check_type, "confirm", check_date=check_date)
            text = "✅ Отметка принята. Спасибо!"
        elif action == "free_time":
            await presence_confirm(user_id, check_type, "free_time", check_date=check_date)
            text = "🕐 Активное «Свободное время» принято. Админы увидят статус."
        elif action == "request_leave":
            await presence_confirm(user_id, check_type, "request_leave", "Запрос через Telegram bot", check_date=check_date)
            text = "🙋 Запрос отправлен админам. Дождись подтверждения."
            name = callback.from_user.full_name or callback.from_user.first_name or str(user_id)
            await notify_admins(
                f"🙋 Запрос отгула ({check_type})\n\n{name} / {user_id} просит разрешение.",
                reply_markup=get_presence_admin_keyboard(check_type, user_id, check_date),
                cohort_code=get_user_cohort(user_id),
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
    if len(parts) not in (4, 5):
        await callback.answer("Некорректная кнопка", show_alert=True)
        return

    if len(parts) == 5:
        _, action, check_type, tg_id_raw, check_date = parts
    else:
        _, action, check_type, tg_id_raw = parts
        check_date = None
    tg_id = int(tg_id_raw)

    try:
        if action == "approve":
            await presence_approve(tg_id, check_type, callback.from_user.id, "admin_approved from bot", check_date)
            await callback.message.edit_text(f"✅ Разрешение выдано: {tg_id} ({check_type})")
            try:
                await bot.send_message(tg_id, "✅ Админ разрешил отгул. Статус отмечен.")
            except Exception:
                pass
        elif action == "reject":
            await presence_reject(tg_id, check_type, callback.from_user.id, "rejected from bot", check_date)
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
        if code_exists(code):
            pending_codes[message.from_user.id] = code
            await state.set_state(Form.waiting_name)
            await message.answer(
                "👋 Добро пожаловать в ZHIDAO Protocol!\n\n"
                "Пожалуйста, введите ваше имя и фамилию:\n"
                "_(например: Иван Иванов)_",
                parse_mode="Markdown",
            )
        else:
            await message.answer(
                f"❌ Неверный код. Обратитесь к администратору: @{ADMIN_CONTACT_USERNAME}",
                reply_markup=get_main_reply_keyboard(message.from_user.id),
            )
    else:
        await message.answer(
            "👋 Добро пожаловать в ZHIDAO Protocol!\n\n"
            "Введите ваш код активации:\n/start ВАШ_КОД",
            reply_markup=get_main_reply_keyboard(message.from_user.id),
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
    cohort_code = get_code_cohort(code)
    is_valid_name, canonical_name, validation_error = validate_expected_student_name(
        full_name, user_id, cohort_code
    )
    if not is_valid_name:
        await message.answer(
            "❌ Не удалось подтвердить ФИО.\n\n"
            f"{validation_error}\n\n"
            "Введи имя ещё раз в формате: Фамилия Имя"
        )
        return
    full_name = canonical_name
    save_telegram_id(code, user_id, full_name)
    link_expected_student(full_name, user_id, cohort_code)
    del pending_codes[user_id]
    await state.clear()
    marzban_user = get_marzban_user(code)
    link = await get_user_link(marzban_user) if marzban_user else None
    if marzban_user and link:
        await message.answer(
            f"✅ Отлично, {full_name}!\n\n"
            f"Ваш конфиг для ZHIDAO Protocol:\n\n"
            f"`{link}`\n\n"
            f"📖 Скопируйте ссылку и добавьте в Happ",
            parse_mode="Markdown",
            reply_markup=get_main_reply_keyboard(user_id),
        )
    elif not marzban_user:
        await message.answer(
            f"✅ Отлично, {full_name}!\n\n"
            "Профиль ZHIDAO Protocol активирован.\n"
            "VPN-конфиг к этому аккаунту пока не привязан, но Mini App уже доступен.",
            reply_markup=get_main_reply_keyboard(user_id),
        )
    else:
        await message.answer(
            f"❌ Ошибка получения конфига. Обратитесь к администратору: @{ADMIN_CONTACT_USERNAME}",
            reply_markup=get_main_reply_keyboard(user_id),
        )


@dp.message(Command("help", "помощь"))
async def help_cmd(message: types.Message):
    await message.answer(
        "📖 Инструкция по установке:\n\n"
        "1️⃣ Скачайте Happ\n"
        "2️⃣ Напишите /start ВАШ_КОД\n"
        "3️⃣ Скопируйте конфиг от бота и добавьте в Happ\n"
        "4️⃣ Откройте Mini App кнопкой ниже\n\n"
        "Если нашли ошибку: /bug описание проблемы",
        reply_markup=get_main_reply_keyboard(message.from_user.id),
    )


@dp.message(Command("myid", "мойid"))
async def myid(message: types.Message):
    await message.answer(
        f"Ваш Telegram ID: `{message.from_user.id}`",
        parse_mode="Markdown",
        reply_markup=get_main_reply_keyboard(message.from_user.id),
    )


@dp.message(Command("bug", "ошибка", "баг"))
async def bug_report_cmd(message: types.Message, state: FSMContext):
    args = message.text.split(maxsplit=1)
    if len(args) > 1 and args[1].strip():
        await submit_bug_report(message, args[1])
        return
    await state.set_state(Form.waiting_bug_report)
    await message.answer(
        "🐞 Опиши проблему одним сообщением.\n\n"
        "Лучший формат:\n"
        "1. Где был баг: экран / кнопка\n"
        "2. Что нажал\n"
        "3. Что ожидал\n"
        "4. Что произошло вместо этого\n\n"
        "Можно также написать сразу: /bug текст проблемы",
        reply_markup=get_main_reply_keyboard(message.from_user.id),
    )


@dp.message(Form.waiting_bug_report)
async def process_bug_report(message: types.Message, state: FSMContext):
    await submit_bug_report(message, message.text or "")
    await state.clear()


@dp.message(Command("bugs", "buglist", "bugslist", "reports", "баги", "ошибки"))
async def bug_reports_list(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора.")
        return

    cohort_code, _ = parse_admin_cohort(message.from_user.id, message.text.split()[1:])
    reports = get_recent_bug_reports(cohort_code, 10)
    if not reports:
        await message.answer(
            "Баг-репортов пока нет.",
            reply_markup=get_main_reply_keyboard(message.from_user.id),
        )
        return

    lines = ["🐞 Последние баг-репорты:"]
    for report_id, tg_id, full_name, username, text, status, created_at in reports:
        clean_text = re.sub(r"\s+", " ", text).strip()
        if len(clean_text) > 180:
            clean_text = clean_text[:180] + "..."
        username_text = f"@{username}" if username else "без username"
        lines.append(
            f"\n#{report_id} · {status} · {created_at}\n"
            f"{full_name} | TG {tg_id} | {username_text}\n"
            f"{clean_text}"
        )
    await message.answer("\n".join(lines), reply_markup=get_main_reply_keyboard(message.from_user.id))


@dp.message(Command("weather", "погода"))
async def weather(message: types.Message):
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
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
    lb = get_leaderboard(get_user_cohort(message.from_user.id))
    rank = next((i + 1 for i, (name, p) in enumerate(lb) if p == points), "—")
    await message.answer(
        f"⭐ Ваши баллы: *{points}*\n🏆 Место в рейтинге: {rank}",
        parse_mode="Markdown",
    )


@dp.message(Command("рейтинг", "leaderboard"))
async def leaderboard(message: types.Message):
    lb = get_leaderboard(get_user_cohort(message.from_user.id))
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
            "• 07:00/07:10/07:30 — подъём\n"
            "• 20:00/20:15/20:50 — вечерняя отметка\n"
            "• 21:20 — отбой"
        )
    else:
        await message.answer("❌ Напоминания выключены.")


@dp.message(Command("admin"))
async def admin_help(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer(
            "❌ У вас нет прав администратора.",
            reply_markup=get_main_reply_keyboard(message.from_user.id),
        )
        return
    status = "✅ вкл" if reminders_enabled else "❌ выкл"
    scope_hint = "МЮ (фиксированный контур)" if message.from_user.id in MJU_ADMIN_IDS else "аргумент [мю|пекин], по умолчанию Пекин"
    await message.answer(
        "👑 Команды администратора:\n\n"
        f"Контуры: {scope_hint}\n"
        "/adduser [мю|пекин] КОД [USERNAME] — добавить пользователя\n"
        "/listusers [мю|пекин] — список пользователей\n"
        "/broadcast [мю|пекин] ТЕКСТ — рассылка\n"
        "/bugs [мю|пекин] — последние баг-репорты\n"
        "/разбудить [мю|пекин] ИМЯ — будильник\n"
        "/перекличка [мю|пекин] — вечерняя отметка\n"
        "/подъем [мю|пекин] — утренняя отметка\n"
        "/presence [мю|пекин] morning|evening — статус\n"
        "/отмена [мю|пекин] morning|evening — отменить отметку\n"
        "/award [мю|пекин] ИМЯ БАЛЛЫ ПРИЧИНА — начислить\n"
        "/penalize [мю|пекин] ИМЯ БАЛЛЫ ПРИЧИНА — снять\n"
        "/зп [мю|пекин] СУММА — зарплата\n"
        f"/напоминания вкл|выкл — сейчас {status}\n"
        "/admin — это меню",
        reply_markup=get_main_reply_keyboard(message.from_user.id),
    )

@dp.message(Command("adduser", "добавить"))
async def add_user_cmd(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора.")
        return
    raw_args = message.text.split()[1:]
    cohort_code, args = parse_admin_cohort(message.from_user.id, raw_args)
    if len(args) not in (1, 2):
        await message.answer(
            "Использование:\n"
            "/adduser [мю|пекин] КОД — student-only без VPN\n"
            "/adduser [мю|пекин] КОД MARZBAN_USERNAME — с VPN"
        )
        return
    marzban_username = args[1] if len(args) == 2 else None
    add_user(args[0], marzban_username, cohort_code)
    suffix = f" → {marzban_username}" if marzban_username else " → student-only"
    await message.answer(
        f"✅ Добавлен в {cohort_code.upper()}: код {args[0]}{suffix}"
    )

@dp.message(Command("listusers", "список"))
async def list_users(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора.")
        return
    cohort_code, _ = parse_admin_cohort(message.from_user.id, message.text.split()[1:])
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        "SELECT code, marzban_username, telegram_id, full_name, points "
        "FROM users WHERE cohort_code=?",
        (cohort_code,),
    )
    users = c.fetchall()
    conn.close()
    if not users:
        await message.answer("Список пользователей пуст.")
        return
    lines = []
    for code, username, tg_id, full_name, points in users:
        tg = str(tg_id) if tg_id else "не активирован"
        name = full_name if full_name else "имя не указано"
        pts = points if points else 0
        lines.append(f"• {name} | {pts}⭐ | TG: {tg}")

    # Telegram caps messages at 4096 chars — with 100+ users a single message
    # would silently fail to send, so chunk into multiple messages instead.
    header = f"👥 Пользователи {cohort_code.upper()} ({len(users)}):\n\n"
    chunk = header
    for line in lines:
        if len(chunk) + len(line) + 1 > 3500:
            await message.answer(chunk)
            chunk = ""
        chunk += line + "\n"
    if chunk.strip():
        await message.answer(chunk)


async def check_wildai_breach_broadcast():
    for cohort_code in COHORT_CODES:
        prefix = f"{cohort_code}:"
        if get_setting(prefix + "breach_broadcast_pending") != "1":
            continue
        glitch = get_setting(prefix + "breach_broadcast_phrase_glitch", "")
        translation = get_setting(prefix + "breach_broadcast_phrase_translation", "")
        text = (
            "⚠️ SYSTEM ERROR // RED FIREWALL: ОФФЛАЙН\n\n"
            "Операция по вытеснению Дикого ИИ провалена. Файрвол пал — система захвачена на 3 дня.\n\n"
            f"{glitch}\n— \"{translation}\""
        )
        for tg_id in get_all_telegram_ids(cohort_code):
            try:
                await bot.send_message(tg_id, text)
            except Exception:
                pass
            await asyncio.sleep(0.05)
        set_setting(prefix + "breach_broadcast_pending", "0")


@dp.message(Command("broadcast", "рассылка"))
async def broadcast(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора.")
        return
    raw = message.text.split(maxsplit=1)
    if len(raw) < 2:
        await message.answer("Использование: /broadcast [мю|пекин] ТЕКСТ")
        return
    parts = raw[1].split(maxsplit=1)
    cohort_code, parts = parse_admin_cohort(message.from_user.id, parts)
    if not parts:
        await message.answer("Укажи текст рассылки")
        return
    text = " ".join(parts)
    sent = 0
    for tg_id in get_all_telegram_ids(cohort_code):
        try:
            await bot.send_message(tg_id, f"📢 Объявление:\n\n{text}")
            sent += 1
        except Exception:
            pass
    await message.answer(f"✅ {cohort_code.upper()}: отправлено {sent} пользователям.")


@dp.message(Command("перекличка"))
async def manual_checkin(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора.")
        return
    cohort_code, _ = parse_admin_cohort(message.from_user.id, message.text.split()[1:])
    await message.answer(f"✅ Запускаю вечернюю отметку: {cohort_code.upper()}...")
    await send_presence_attempt(
        "evening",
        attempt_no=1,
        create_check=True,
        cohort_code=cohort_code,
        admin_id=message.from_user.id,
    )


@dp.message(Command("подъем"))
async def manual_morning_presence(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора.")
        return
    cohort_code, _ = parse_admin_cohort(message.from_user.id, message.text.split()[1:])
    await message.answer(f"✅ Запускаю утреннюю отметку: {cohort_code.upper()}...")
    await send_presence_attempt(
        "morning",
        attempt_no=1,
        create_check=True,
        cohort_code=cohort_code,
        admin_id=message.from_user.id,
    )


@dp.message(Command("отмена", "presence_cancel"))
async def presence_cancel_cmd(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора.")
        return

    cohort_code, args = parse_admin_cohort(
        message.from_user.id,
        message.text.split()[1:],
    )
    check_type = args.pop(0) if args else "evening"
    reason = " ".join(args) if args else "Отменено администратором"

    if check_type not in ("morning", "evening"):
        await message.answer("Использование: /отмена morning или /отмена evening")
        return

    try:
        data = await presence_cancel(check_type, message.from_user.id, cohort_code, reason)
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
    cohort_code, args = parse_admin_cohort(message.from_user.id, message.text.split()[1:])
    check_type = args[0] if args else "evening"
    if check_type not in ("morning", "evening"):
        await message.answer("Использование: /presence morning или /presence evening")
        return
    data = await presence_overview(check_type, cohort_code, message.from_user.id)
    counts = data.get("counts", {})
    label = PRESENCE_TYPE_LABELS.get(check_type, check_type)
    text = f"📊 {label.capitalize()} · {cohort_code.upper()}\n\n"
    for key in PRESENCE_STATUS_ORDER:
        text += f"• {PRESENCE_STATUS_LABELS.get(key, key)}: {counts.get(key, 0)}\n"
    await message.answer(text)


@dp.message(Command("award"))
async def award_points(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора.")
        return
    cohort_code, args = parse_admin_cohort(
        message.from_user.id,
        message.text.split(maxsplit=4)[1:],
    )
    if len(args) < 3:
        await message.answer("Использование: /award [мю|пекин] ИМЯ БАЛЛЫ ПРИЧИНА")
        return
    name_query, points_str = args[0], args[1]
    reason = " ".join(args[2:])

    try:
        points = int(points_str)
    except Exception:
        await message.answer("❌ Баллы должны быть числом")
        return
    user = find_user_by_name(name_query, cohort_code)
    if not user:
        await message.answer(f"❌ Пользователь '{name_query}' не найден")
        return
    tg_id, full_name, current_points = user
    dragon_bonus = ""
    if has_dragon(tg_id):
        points = int(points * 1.2)
        dragon_bonus = " (+20% 🐉)"
    new_points = await change_points(tg_id, points, operation='bot_award', note=reason)
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
    cohort_code, args = parse_admin_cohort(
        message.from_user.id,
        message.text.split(maxsplit=4)[1:],
    )
    if len(args) < 3:
        await message.answer("Использование: /penalize [мю|пекин] ИМЯ БАЛЛЫ ПРИЧИНА")
        return
    name_query, points_str = args[0], args[1]
    reason = " ".join(args[2:])

    try:
        points = int(points_str)
    except Exception:
        await message.answer("❌ Баллы должны быть числом")
        return
    user = find_user_by_name(name_query, cohort_code)
    if not user:
        await message.answer(f"❌ Пользователь '{name_query}' не найден")
        return
    tg_id, full_name, current_points = user
    conn = db_connect()
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
    new_points = await change_points(tg_id, -points, operation='bot_penalize', note=reason)
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
    cohort_code, args = parse_admin_cohort(message.from_user.id, message.text.split()[1:])
    try:
        amount = int(args[0]) if args else 100
    except ValueError:
        await message.answer("Использование: /зп [мю|пекин] [СУММА]")
        return
    users = get_all_users(cohort_code)

    sent = 0
    for tg_id, full_name in users:
        if tg_id in ADMIN_IDS:
            continue
        dragon = has_dragon(tg_id)
        final = amount * 2 if dragon else amount
        try:
            await change_points(tg_id, final, operation='bot_salary', note=f'зп {amount}★' + (' x2 dragon' if dragon else ''))
        except Exception:
            continue
        try:
            bonus_text = " (x2 🐉 Красный Дракон!)" if dragon else ""
            await bot.send_message(tg_id, f"💰 Воскресная зарплата: +{final}★{bonus_text}")
            sent += 1
        except Exception:
            pass
    await message.answer(f"✅ {cohort_code.upper()}: зарплата выдана {sent} игрокам.")


@dp.message(Command("разбудить"))
async def wake_up(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора.")
        return
    cohort_code, args = parse_admin_cohort(message.from_user.id, message.text.split()[1:])
    if not args:
        await message.answer("Использование: /разбудить [мю|пекин] ИМЯ")
        return
    query = " ".join(args).strip()
    user = find_user_by_name(query, cohort_code)
    if not user or not user[0]:
        await message.answer(f"❌ Пользователь '{query}' не найден.")
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
        await notify_admins(
            f"✅ {message.from_user.first_name} подтвердил подъём.",
            cohort_code=get_user_cohort(message.from_user.id),
        )
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
    recipient = find_user_by_name(args[1], get_user_cohort(message.from_user.id))
    if not recipient:
        await message.answer(f"❌ Пользователь '{args[1]}' не найден")
        return
    to_id, to_name, _ = recipient
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
        async with session.post(
            f"{API_URL}/api/shop/gift",
            json={"purchase_id": purchase_id, "from_id": message.from_user.id, "to_id": to_id},
            headers=internal_api_headers(),
            ssl=False,
        ) as r:
            if r.status == 200:
                await message.answer(f"✅ Подарок отправлен {to_name}!\nНалог: -20★")
                try:
                    await bot.send_message(to_id, f"🎁 {message.from_user.first_name} подарил тебе предмет!")
                except Exception:
                    pass
            else:
                try:
                    data = await r.json()
                except Exception:
                    data = {}
                detail = data.get("detail")
                if detail == "Daily gift limit reached":
                    await message.answer("❌ Лимит подарков на сегодня исчерпан. Можно отправить до 5 подарков в день.")
                elif detail == "Not enough points for tax":
                    await message.answer("❌ Недостаточно звёзд для налога на подарок. Нужно 20★.")
                else:
                    await message.answer("❌ Ошибка. Предмет не найден или уже использован.")


@dp.message(Command("вопрос"))
async def anonymous_question(message: types.Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /вопрос ТЕКСТ")
        return
    question_id = save_anon_question(message, args[1])
    await message.answer("✅ Вопрос отправлен куратору!")
    username = f"@{message.from_user.username}" if message.from_user.username else "без username"
    reply_kb = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="✉️ Ответить", callback_data=f"anon_reply:{question_id}"),
        ]]
    )
    await notify_admins(
        f"🤫 Вопрос #{question_id}\n"
        f"От: {message.from_user.full_name} ({username})\n"
        f"TG: {message.from_user.id}\n\n"
        f"{args[1]}",
        reply_markup=reply_kb,
        cohort_code=get_user_cohort(message.from_user.id),
    )


@dp.callback_query(lambda c: c.data and c.data.startswith("anon_reply:"))
async def anon_reply_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет прав администратора", show_alert=True)
        return
    question_id = int(callback.data.split(":", 1)[1])
    row = get_anon_question(question_id)
    if not row:
        await callback.answer("Вопрос не найден", show_alert=True)
        return
    _target_id, _full_name, status, answered_by_name = row
    if (
        callback.from_user.id in MJU_ADMIN_IDS
        and get_user_cohort(_target_id) != COHORT_MJU
    ):
        await callback.answer("Этот вопрос относится к контуру Пекин", show_alert=True)
        return
    await state.set_state(Form.waiting_anon_reply)
    await state.update_data(anon_question_id=question_id)
    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"anon_cancel:{question_id}"),
        ]]
    )
    prefix = ""
    if status == "answered":
        prefix = f"⚠️ Этот вопрос уже отвечен ({answered_by_name or 'другой админ'}). Можешь отправить ещё один ответ или отменить.\n\n"
    await callback.message.answer(
        f"{prefix}Напиши ответ на вопрос #{question_id} одним сообщением:",
        reply_markup=cancel_kb,
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data and c.data.startswith("anon_cancel:"))
async def anon_reply_cancel(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет прав администратора", show_alert=True)
        return
    current_state = await state.get_state()
    if current_state == Form.waiting_anon_reply.state:
        await state.clear()
    question_id = callback.data.split(":", 1)[1]
    await callback.message.answer(
        f"Отменено. Вопрос #{question_id} остался без ответа — можешь нажать «✉️ Ответить» позже."
    )
    await callback.answer()


@dp.message(Form.waiting_anon_reply)
async def anon_reply_send(message: types.Message, state: FSMContext):
    data = await state.get_data()
    question_id = data.get("anon_question_id")
    await state.clear()
    row = get_anon_question(question_id) if question_id else None
    if not row:
        await message.answer("❌ Не удалось найти вопрос для ответа.")
        return
    target_telegram_id, _full_name, _status, _answered_by_name = row
    if (
        message.from_user.id in MJU_ADMIN_IDS
        and get_user_cohort(target_telegram_id) != COHORT_MJU
    ):
        await message.answer("❌ Этот вопрос относится к контуру Пекин.")
        return
    admin_name = message.from_user.full_name or str(message.from_user.id)
    try:
        await bot.send_message(
            target_telegram_id,
            f"💬 Ответ куратора на твой вопрос:\n\n{message.text or ''}",
        )
        await message.answer(f"✅ Ответ на вопрос #{question_id} отправлен.")
        mark_anon_question_answered(question_id, admin_name)
        await notify_admins(
            f"ℹ️ Вопрос #{question_id} получил ответ от {admin_name}. Отвечать ещё раз не нужно.",
            cohort_code=get_user_cohort(target_telegram_id),
        )
    except Exception:
        await message.answer("❌ Не получилось отправить ответ. Возможно, пользователь заблокировал бота.")


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
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
        async with session.post(
            f"{API_URL}/api/netwatch/strike",
            json={"telegram_id": message.from_user.id, "target_name": args[1], "points": points},
            headers=internal_api_headers(),
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
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
        async with session.post(
            f"{API_URL}/api/netwatch/blackwall",
            json={"telegram_id": message.from_user.id, "target_name": args[1]},
            headers=internal_api_headers(),
            ssl=False,
        ) as r:
            if r.status == 200:
                data = await r.json()
                await message.answer(f"🔴 Красный Файрвол активирован!\nЦель: {data['target']}\nМагазин заблокирован на 24 часа")
            elif r.status == 403:
                await message.answer("❌ У тебя нет импланта Сетевой Дозор")
            elif r.status == 429:
                data = await r.json()
                await message.answer(f"⏳ Перезарядка: {data['detail']}")
            else:
                await message.answer("❌ Ошибка. Цель не найдена?")


def _cyberpunk_active_owners(c, implant_id: str):
    """Owners of an active (durability > 0) cyberpunk-path implant whose passive
    is not currently frozen by switching to the genshin path. Admins are exempt."""
    placeholders = ",".join("?" for _ in ADMIN_IDS) or "NULL"
    c.execute(
        f'''SELECT DISTINCT ui.telegram_id FROM user_implants ui
            LEFT JOIN user_status us ON us.telegram_id = ui.telegram_id
            WHERE ui.implant_id=? AND ui.durability > 0
              AND (COALESCE(us.theme_path, 'cyberpunk') != 'genshin' OR ui.telegram_id IN ({placeholders}))''',
        [implant_id] + list(ADMIN_IDS),
    )
    return [row[0] for row in c.fetchall()]


def _genshin_active_owners(c, card_id: str):
    """Owners of an active (durability > 0) genshin-path card whose passive
    is not currently frozen by switching to the cyberpunk path. Admins are exempt."""
    placeholders = ",".join("?" for _ in ADMIN_IDS) or "NULL"
    c.execute(
        f'''SELECT DISTINCT uc.telegram_id FROM user_cards uc
            LEFT JOIN user_status us ON us.telegram_id = uc.telegram_id
            WHERE uc.card_id=? AND uc.durability > 0
              AND (us.theme_path = 'genshin' OR uc.telegram_id IN ({placeholders}))''',
        [card_id] + list(ADMIN_IDS),
    )
    return [row[0] for row in c.fetchall()]


async def moon_morning():
    conn = db_connect()
    c = conn.cursor()
    owners = _genshin_active_owners(c, 'card_moon')
    conn.close()
    for tg_id in owners:
        try:
            await change_points(tg_id, 12, operation='card_moon_passive', note='утренний пассив Богини Луны')
        except Exception:
            continue


async def netwatch_morning():
    conn = db_connect()
    c = conn.cursor()
    owners = _cyberpunk_active_owners(c, 'implant_netwatch')
    conn.close()
    for tg_id in owners:
        try:
            await change_points(tg_id, 25, operation='netwatch_passive', note='утренний пассив NetWatch')
        except Exception:
            continue


async def caishen_morning():
    conn = db_connect()
    c = conn.cursor()
    owners = _cyberpunk_active_owners(c, 'implant_caishen')
    conn.close()
    for tg_id in owners:
        try:
            await change_points(tg_id, 15, operation='caishen_passive', note='утренний пассив Цайшэнь')
        except Exception:
            continue


async def qilin_morning():
    conn = db_connect()
    c = conn.cursor()
    active_owners = _cyberpunk_active_owners(c, 'implant_qilin')
    conn.close()
    total_owners = len(active_owners)
    if total_owners == 0:
        return
    # Diminishing returns: 40★ за 1 владельца, -6★ за каждого следующего, минимум 8★
    bonus = max(8, 40 - (total_owners - 1) * 6)
    for tg_id in active_owners:
        try:
            await change_points(tg_id, bonus, operation='qilin_passive',
                                note=f'Цилинь: {total_owners} владельцев → {bonus}★')
        except Exception:
            continue


async def main():
    init_db()
    scheduler.add_job(send_checkin, CronTrigger(hour=20, minute=0, timezone=BEIJING_TZ))
    scheduler.add_job(retry_evening_presence, CronTrigger(hour=20, minute=15, timezone=BEIJING_TZ), args=[2])
    scheduler.add_job(retry_evening_presence, CronTrigger(hour=20, minute=50, timezone=BEIJING_TZ), args=[3])
    scheduler.add_job(check_missing, CronTrigger(hour=21, minute=5, timezone=BEIJING_TZ))
    scheduler.add_job(send_goodnight, CronTrigger(hour=21, minute=20, timezone=BEIJING_TZ))
    scheduler.add_job(penalize_presence, CronTrigger(hour=21, minute=35, timezone=BEIJING_TZ), args=["evening"])

    scheduler.add_job(send_morning_presence, CronTrigger(hour=7, minute=0, timezone=BEIJING_TZ))
    scheduler.add_job(retry_morning_presence, CronTrigger(hour=7, minute=10, timezone=BEIJING_TZ), args=[2])
    scheduler.add_job(retry_morning_presence, CronTrigger(hour=7, minute=30, timezone=BEIJING_TZ), args=[3])
    scheduler.add_job(check_wakeup_missing, CronTrigger(hour=7, minute=40, timezone=BEIJING_TZ))
    scheduler.add_job(penalize_presence, CronTrigger(hour=7, minute=50, timezone=BEIJING_TZ), args=["morning"])

    scheduler.add_job(netwatch_morning, CronTrigger(hour=8, minute=1, timezone=BEIJING_TZ))
    scheduler.add_job(caishen_morning, CronTrigger(hour=8, minute=2, timezone=BEIJING_TZ))
    scheduler.add_job(qilin_morning, CronTrigger(hour=8, minute=3, timezone=BEIJING_TZ))
    scheduler.add_job(moon_morning, CronTrigger(hour=8, minute=4, timezone=BEIJING_TZ))
    scheduler.add_job(check_wildai_breach_broadcast, IntervalTrigger(minutes=1))
    scheduler.start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
