import random
import json
import hashlib
import hmac
import os
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import parse_qsl

import aiohttp
import pytz
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MARZBAN_URL = os.getenv("MARZBAN_URL", "http://127.0.0.1:8000")
MARZBAN_USER = os.getenv("MARZBAN_USER", "")
MARZBAN_PASS = os.getenv("MARZBAN_PASS", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "")
TELEGRAM_AUTH_REQUIRED = os.getenv("TELEGRAM_AUTH_REQUIRED", "0").strip().lower() in {"1", "true", "yes", "on"}
API_INTERNAL_TOKEN = os.getenv("API_INTERNAL_TOKEN", "").strip()
BEIJING_TZ = pytz.timezone("Asia/Shanghai")


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


def parse_text_list_env(name: str) -> list[str]:
    raw = os.getenv(name, "")
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except json.JSONDecodeError:
        pass
    return [line.strip() for line in raw.replace(";", "\n").splitlines() if line.strip()]


def load_expected_student_names() -> list[str]:
    names = parse_text_list_env("EXPECTED_STUDENT_NAMES")
    if names:
        return names

    path = os.getenv("EXPECTED_STUDENTS_FILE", "").strip()
    if path:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return [line.strip() for line in f if line.strip()]
        except OSError:
            return []

    return []


ADMIN_IDS = parse_int_list_env("ADMIN_IDS") or [-1]
ARCHITECT_IDS = parse_int_list_env("ARCHITECT_IDS") or [-1]
INTRO_CYBERPUNK_ADMIN_IDS = set(parse_int_list_env("INTRO_CYBERPUNK_ADMIN_IDS"))
INTRO_GENSHIN_ADMIN_IDS = set(parse_int_list_env("INTRO_GENSHIN_ADMIN_IDS"))


def verify_telegram_init_data(init_data: str) -> Optional[dict]:
    if not init_data or not BOT_TOKEN:
        return None

    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", "")
    if not received_hash:
        return None

    data_check_string = "\n".join(f"{key}={parsed[key]}" for key in sorted(parsed))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode("utf-8"), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated_hash, received_hash):
        return None

    try:
        user = json.loads(parsed.get("user", "{}"))
    except json.JSONDecodeError:
        user = {}
    user_id = user.get("id")
    if not user_id:
        return None

    return {"telegram_id": int(user_id), "user": user, "auth_date": parsed.get("auth_date")}


def request_has_internal_token(request: Request) -> bool:
    return bool(API_INTERNAL_TOKEN and request.headers.get("x-internal-token") == API_INTERNAL_TOKEN)


def is_sensitive_api_request(request: Request) -> bool:
    path = request.url.path
    if request.method == "OPTIONS":
        return False
    if path.startswith((
        "/api/admin",
        "/api/presence/admin",
        "/api/diary/admin",
    )):
        return True
    if request.headers.get("x-admin-id"):
        return True
    if TELEGRAM_AUTH_REQUIRED and request.method in {"POST", "PUT", "PATCH", "DELETE"} and path.startswith("/api/"):
        return True
    return False


def is_verified_admin_request(request: Request, verified_id: Optional[int]) -> bool:
    header_value = request.headers.get("x-admin-id")
    if not header_value or not verified_id:
        return False
    try:
        header_id = int(header_value)
    except ValueError:
        return False
    return header_id == verified_id and verified_id in ADMIN_IDS


def extract_path_telegram_id(path: str) -> Optional[int]:
    protected_patterns = [
        r"^/api/points/(\d+)$",
        r"^/api/profile/(\d+)$",
        r"^/api/user/(\d+)$",
        r"^/api/achievements/(\d+)$",
        r"^/api/casino/status/(\d+)$",
        r"^/api/casino/history/(\d+)$",
        r"^/api/casino/inventory/(\d+)$",
        r"^/api/casino/implants/(\d+)$",
        r"^/api/implants/legendary/status/(\d+)$",
        r"^/api/shop/inventory/(\d+)$",
        r"^/api/cards/(\d+)$",
        r"^/api/diary/(\d+)(?:/[^/]+)?$",
    ]
    for pattern in protected_patterns:
        match = re.match(pattern, path)
        if match:
            return int(match.group(1))
    return None


def auth_error_response(request: Request, detail: str, status_code: int) -> JSONResponse:
    response = JSONResponse({"detail": detail}, status_code=status_code)
    if request.headers.get("origin"):
        # Auth middleware can return before CORSMiddleware decorates the response.
        response.headers["Access-Control-Allow-Origin"] = "*"
    return response


async def enforce_verified_user_identity(request: Request, verified_id: Optional[int], is_admin_request: bool):
    if not verified_id or is_admin_request:
        return None

    candidate_ids = []
    path_id = extract_path_telegram_id(request.url.path)
    if path_id:
        candidate_ids.append(path_id)

    query_id = request.query_params.get("telegram_id")
    if query_id:
        try:
            candidate_ids.append(int(query_id))
        except ValueError:
            return auth_error_response(request, "Invalid telegram_id", 400)

    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                body = await request.json()
            except Exception:
                body = None
            if isinstance(body, dict) and body.get("telegram_id") is not None:
                try:
                    candidate_ids.append(int(body.get("telegram_id")))
                except (TypeError, ValueError):
                    return auth_error_response(request, "Invalid telegram_id", 400)

    for candidate_id in candidate_ids:
        if candidate_id != verified_id:
            return auth_error_response(request, "Telegram identity mismatch", 403)
    return None


@app.middleware("http")
async def telegram_auth_middleware(request: Request, call_next):
    if request_has_internal_token(request):
        return await call_next(request)

    init_data = request.headers.get("x-telegram-init-data", "")
    verified = verify_telegram_init_data(init_data)
    verified_id = verified["telegram_id"] if verified else None
    if verified:
        request.state.telegram_id = verified_id
        request.state.telegram_user = verified["user"]

        for header_name in ("x-admin-id", "x-telegram-id"):
            header_value = request.headers.get(header_name)
            if header_value and str(header_value) != str(verified_id):
                return auth_error_response(request, "Telegram identity mismatch", 403)
    elif is_sensitive_api_request(request):
        return auth_error_response(request, "Telegram auth required", 401)

    identity_error = await enforce_verified_user_identity(
        request,
        verified_id,
        is_verified_admin_request(request, verified_id),
    )
    if identity_error:
        return identity_error

    return await call_next(request)


PRESENCE_CHECK_TYPES = {"morning", "evening", "manual"}
PRESENCE_STATUSES = {
    "pending",
    "confirmed",
    "free_time",
    "leave_requested",
    "admin_approved",
    "leave_rejected",
    "needs_attention",
    "penalized",
    "skipped",
}
PRESENCE_SAFE_STATUSES = {"confirmed", "free_time", "admin_approved", "skipped"}
PRESENCE_ATTEMPT_LIMIT = 3
PRESENCE_PENALTY_POINTS = 50

EXPECTED_STUDENT_NAMES = load_expected_student_names()

RAID_ENTRY_COST = 50
RAID_SUCCESS_REWARD = 100
RAID_SUCCESS_CHANCE = 0.4
RAID_DAILY_LIMIT = 3
RAID_USER_DAILY_LIMIT = 2
RAID_MIN_PLAYERS = 3
SHOP_EXTRA_RAID_CODE = "extra_raid_attempt"
SHOP_EXTRA_RAID_PRICE = 80
SHOP_ITEM_SEEDS = [
    ("immunity", "Иммунитет", "Блокирует один штраф", "🛡", 150, -1, "privilege"),
    ("laundry_vip", "Стирка VIP", "Приоритет на стирку", "🧺", 80, -1, "privilege"),
    ("dj", "DJ-сет", "Право выбрать музыку", "🎵", 100, -1, "social"),
    ("solo_seat", "Место соло", "Отдельное место по согласованию", "🪑", 120, -1, "privilege"),
    ("amnesty", "Амнистия", "Снять один штраф по согласованию", "🤝", 80, -1, "privilege"),
    ("kfc", "KFC", "Награда из специального меню", "🍗", 300, -1, "food"),
    ("bubbletea", "Bubble Tea", "Награда из специального меню", "🧋", 250, -1, "food"),
    ("snack", "Снэк", "Награда из специального меню", "🍦", 200, -1, "food"),
    ("no_report", "Без доклада", "Пропуск одного доклада по согласованию", "📄", 400, -1, "vip"),
    ("poizon", "Poizon", "Премиальная награда", "👕", 600, -1, "vip"),
    ("extra_case", "Дополнительный кейс", "Открыть ещё один кейс сверх дневного лимита", "📦", 180, -1, "privilege"),
    ("double_win", "Двойной выигрыш", "Удвоить следующий денежный выигрыш", "🎴", 130, -1, "privilege"),
    ("title_player", "Титул дня", "Особый титул профиля на день", "👑", 150, -1, "vip"),
    (SHOP_EXTRA_RAID_CODE, "Доп. рейд-попытка", "+1 рейд сегодня", "⚔️", SHOP_EXTRA_RAID_PRICE, -1, "privilege"),
    ("path_switch", "Смена пути 转换", "Переключиться между NetWatch и Genshin", "🔁", 500, -1, "vip"),
]
SHOP_GIFT_DAILY_LIMIT = 5
DIARY_WORD_LIMIT = 15
DIARY_MIN_STORY_HANZI = 20
DIARY_MIN_FILLED_ROWS = 5
DIARY_AUTO_POINTS_CLEAN = 20
DIARY_AUTO_POINTS_WARN = 15
HANZI_RE = re.compile(r'[\u4e00-\u9fff]')

CONTRACT_MIN_REWARD = 5
CONTRACT_MAX_REWARD = 50
CONTRACT_ADMIN_MAX_REWARD = 100
CONTRACT_FEE_PCT = 0.10
CONTRACT_FEE_MIN = 2
CONTRACT_MAX_ACTIVE = 3
CONTRACT_MAX_COMPLETED_PER_DAY = 5
CONTRACT_MAX_DAILY_SPEND = 150
CONTRACT_MAX_DAILY_EARN = 150
CONTRACT_MIN_COMPLETE_SECONDS = 300
CONTRACT_CATEGORIES = {'living', 'chinese', 'app', 'reminder', 'trade', 'other'}
LATIN_RE = re.compile(r'[A-Za-z]')
PINYIN_RE = re.compile(r"^(?:[A-Za-züÜvV:]+[1-5])+(?:[ '\\-](?:[A-Za-züÜvV:]+[1-5])+)*$")
ARCHITECT_DEFAULT_HP = 1000
ARCHITECT_PHASE2_THRESHOLD = 0.7
ARCHITECT_PHASE3_THRESHOLD = 0.3
ARCHITECT_FINAL_PHASE_SECONDS = 180
ARCHITECT_SYNC_WINDOW_COUNT = 3
ARCHITECT_SYNC_WINDOW_SECONDS = 10
ARCHITECT_VULNERABILITY_SECONDS = 8
ARCHITECT_OVERLOAD_PENALTY_THRESHOLD = 20
ARCHITECT_OVERLOAD_PENALTY_MULTIPLIER = 0.8

EVENT_MODIFIER_ROLE_MAP = {
    "implant_red_dragon": ("implant", "assault"),
    "implant_terracota": ("implant", "defense"),
    "implant_guanxi": ("implant", "control"),
    "card_pyro": ("card", "assault"),
    "card_star": ("card", "assault"),
    "card_zhongli": ("card", "defense"),
    "card_fairy": ("card", "defense"),
    "card_fox": ("card", "control"),
    "card_literature": ("card", "control"),
    "card_forest": ("card", "defense"),
    "card_sea": ("card", "control"),
    "card_moon": ("card", "defense"),
}

ARCHITECT_QUESTION_SEEDS = {
    "attack": [
        {"prompt": "Как переводится 买东西?", "option_a": "Покупать вещи", "option_b": "Идти домой", "option_c": "Пить воду", "correct_option": "a", "explanation": "买东西 — покупать вещи."},
        {"prompt": "Что значит 米饭?", "option_a": "Лапша", "option_b": "Рис", "option_c": "Суп", "correct_option": "b", "explanation": "米饭 — варёный рис."},
        {"prompt": "Выбери перевод 现在几点？", "option_a": "Который час?", "option_b": "Где вокзал?", "option_c": "Сколько стоит?", "correct_option": "a", "explanation": "现在几点？ — который сейчас час?"},
        {"prompt": "Как переводится 地铁?", "option_a": "Автобус", "option_b": "Метро", "option_c": "Такси", "correct_option": "b", "explanation": "地铁 — метро."},
        {"prompt": "Что значит 今天很热?", "option_a": "Сегодня холодно", "option_b": "Сегодня ветрено", "option_c": "Сегодня жарко", "correct_option": "c", "explanation": "很热 — очень жарко."},
        {"prompt": "Выбери перевод 我想喝水。", "option_a": "Я хочу пить воду", "option_b": "Я хочу есть рис", "option_c": "Я хочу идти домой", "correct_option": "a", "explanation": "我想喝水 — я хочу пить воду."},
        {"prompt": "Как переводится 右边?", "option_a": "Слева", "option_b": "Справа", "option_c": "Прямо", "correct_option": "b", "explanation": "右边 — справа."},
        {"prompt": "Что значит 便宜一点?", "option_a": "Немного дешевле", "option_b": "Немного быстрее", "option_c": "Немного дальше", "correct_option": "a", "explanation": "便宜一点 — немного дешевле."},
    ],
    "protocol": [
        {"prompt": "Выбери логичный ответ на 你去哪儿？", "option_a": "我去商店。", "option_b": "三点半。", "option_c": "很好吃。", "correct_option": "a", "explanation": "На вопрос «Куда ты идёшь?» подходит «Я иду в магазин»."},
        {"prompt": "Что лучше ответить на 你吃饭了吗？", "option_a": "我坐地铁。", "option_b": "吃了，谢谢。", "option_c": "我买苹果。", "correct_option": "b", "explanation": "吃了，谢谢。 — уже поел, спасибо."},
        {"prompt": "Выбери правильный порядок слов:", "option_a": "我 明天 去 学校", "option_b": "明天 我 去 学校", "option_c": "去 我 学校 明天", "correct_option": "b", "explanation": "Время обычно ставится перед глаголом: 明天我去学校。"},
        {"prompt": "Какой ответ подходит к 这个多少钱？", "option_a": "二十块。", "option_b": "我不坐车。", "option_c": "今天星期五。", "correct_option": "a", "explanation": "二十块。 — двадцать юаней."},
        {"prompt": "Выбери правильную реплику в ресторане:", "option_a": "我要一碗面。", "option_b": "我在北京大学。", "option_c": "我看电影。", "correct_option": "a", "explanation": "我要一碗面。 — я хочу одну миску лапши."},
        {"prompt": "Что лучше ответить на 你叫什么名字？", "option_a": "我叫安娜。", "option_b": "我去车站。", "option_c": "我八点起床。", "correct_option": "a", "explanation": "我叫... — меня зовут..."},
        {"prompt": "Выбери правильную фразу:", "option_a": "我昨天去商店了。", "option_b": "我商店昨天去了。", "option_c": "昨天了我去商店。", "correct_option": "a", "explanation": "Нормальный порядок: 我昨天去商店了。"},
        {"prompt": "Что означает 请再说一遍？", "option_a": "Пожалуйста, повторите ещё раз", "option_b": "Пожалуйста, закрой дверь", "option_c": "Пожалуйста, дайте счёт", "correct_option": "a", "explanation": "请再说一遍 — пожалуйста, повторите ещё раз."},
    ],
    "stabilize": [
        {"prompt": "Выбери вежливую просьбу о помощи:", "option_a": "请帮我一下。", "option_b": "你很贵。", "option_c": "我不喜欢坐车。", "correct_option": "a", "explanation": "请帮我一下。 — пожалуйста, помогите мне."},
        {"prompt": "Что лучше сказать, если не понял?", "option_a": "我不知道。", "option_b": "我听不懂。", "option_c": "我不回家。", "correct_option": "b", "explanation": "我听不懂。 — я не понимаю на слух."},
        {"prompt": "Выбери правильную фразу для успокоения:", "option_a": "没关系。", "option_b": "太贵了。", "option_c": "我饿了。", "correct_option": "a", "explanation": "没关系。 — ничего страшного / всё в порядке."},
        {"prompt": "Как переводится 请等一下?", "option_a": "Пожалуйста, подождите немного", "option_b": "Пожалуйста, идите быстрее", "option_c": "Пожалуйста, купите это", "correct_option": "a", "explanation": "请等一下 — пожалуйста, подождите минутку."},
        {"prompt": "Выбери правильный ответ на 谢谢你。", "option_a": "对不起。", "option_b": "不客气。", "option_c": "没时间。", "correct_option": "b", "explanation": "不客气。 — не за что."},
        {"prompt": "Что означает 慢一点说?", "option_a": "Говорите медленнее", "option_b": "Говорите громче", "option_c": "Говорите тише", "correct_option": "a", "explanation": "慢一点说 — говорите немного медленнее."},
        {"prompt": "Выбери фразу для уточнения дороги:", "option_a": "请问，怎么走？", "option_b": "我会开车。", "option_c": "今天不忙。", "correct_option": "a", "explanation": "请问，怎么走？ — подскажите, как пройти?"},
        {"prompt": "Как переводится 我马上来?", "option_a": "Я сейчас приду", "option_b": "Я уже ушёл", "option_c": "Я хочу остаться", "correct_option": "a", "explanation": "我马上来 — я сейчас приду."},
    ],
}


def get_conn():
    return sqlite3.connect('/root/zhidao.db')


def normalize_expected_student_name(value: str) -> str:
    text = str(value or "").replace("\t", " ").replace("Ё", "Е").replace("ё", "е")
    return re.sub(r"\s+", " ", text.strip()).lower()


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (code TEXT PRIMARY KEY,
                 marzban_username TEXT,
                 telegram_id INTEGER,
                 full_name TEXT,
                  avatar_url TEXT DEFAULT NULL,
                  room_number TEXT DEFAULT NULL,
                  points INTEGER DEFAULT 0,
                  rep_score INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS schedule
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  day TEXT, time TEXT, subject TEXT, location TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS announcements
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  text TEXT,
                  created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS announcement_reactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  announcement_id INTEGER,
                  telegram_id INTEGER,
                  emoji TEXT,
                  UNIQUE(announcement_id, telegram_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS admin_action_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  admin_id INTEGER NOT NULL,
                  target_id INTEGER DEFAULT NULL,
                  action_type TEXT NOT NULL,
                  points_delta INTEGER DEFAULT 0,
                  reason TEXT DEFAULT '',
                  created_at TEXT NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS expected_students
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  full_name TEXT NOT NULL,
                  normalized_name TEXT UNIQUE NOT NULL,
                  group_label TEXT DEFAULT '',
                  room_number TEXT DEFAULT NULL,
                  telegram_id INTEGER DEFAULT NULL,
                  status TEXT DEFAULT 'pending',
                  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                  updated_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS laundry
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  date TEXT, time TEXT, telegram_id INTEGER, username TEXT,
                  UNIQUE(date, time))''')
    c.execute('''CREATE TABLE IF NOT EXISTS casino_log
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  telegram_id INTEGER, date TEXT, prize TEXT,
                  created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS shop_items
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  code TEXT UNIQUE, name TEXT, description TEXT,
                  icon TEXT, price INTEGER, daily_limit INTEGER DEFAULT -1,
                  category TEXT, active INTEGER DEFAULT 1)''')
    c.execute('''CREATE TABLE IF NOT EXISTS shop_purchases
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  telegram_id INTEGER, item_code TEXT,
                  purchased_at TEXT DEFAULT CURRENT_TIMESTAMP,
                  status TEXT DEFAULT 'active',
                  given_to INTEGER DEFAULT NULL,
                  gifted_at TEXT DEFAULT NULL,
                  expires_at TEXT DEFAULT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS shop_daily_counts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  item_code TEXT, date TEXT, count INTEGER DEFAULT 0,
                  UNIQUE(item_code, date))''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_status
                 (telegram_id INTEGER PRIMARY KEY,
                  frozen INTEGER DEFAULT 0,
                  netwatch_locked_until TEXT DEFAULT NULL,
                  immunity INTEGER DEFAULT 0,
                  immunity_reason TEXT DEFAULT NULL,
                  extra_cases INTEGER DEFAULT 0,
                  extra_raids INTEGER DEFAULT 0,
                  double_win INTEGER DEFAULT 0,
                  title_date TEXT DEFAULT NULL,
                  theme_path TEXT DEFAULT NULL,
                  profile_showcase_kind TEXT DEFAULT NULL,
                  profile_showcase_code TEXT DEFAULT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_implants
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  telegram_id INTEGER,
                  implant_id TEXT,
                  durability INTEGER DEFAULT 3,
                  obtained_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS implant_daily_uses
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  telegram_id INTEGER NOT NULL,
                  implant_id TEXT NOT NULL,
                  use_date TEXT NOT NULL,
                  use_key TEXT DEFAULT '',
                  used_at TEXT DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE(telegram_id, implant_id, use_date, use_key))''')
    c.execute('''CREATE TABLE IF NOT EXISTS legendary_implant_actions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  actor_telegram_id INTEGER NOT NULL,
                  target_telegram_id INTEGER DEFAULT NULL,
                  secondary_telegram_id INTEGER DEFAULT NULL,
                  implant_id TEXT NOT NULL,
                  action_code TEXT NOT NULL,
                  points_delta INTEGER DEFAULT 0,
                  secondary_delta INTEGER DEFAULT 0,
                  detail TEXT DEFAULT '',
                  created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_cards
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  telegram_id INTEGER,
                  card_id TEXT,
                  obtained_at TEXT DEFAULT CURRENT_TIMESTAMP,
                  durability INTEGER DEFAULT 3)''')
    c.execute('''CREATE TABLE IF NOT EXISTS achievements
                 (code TEXT PRIMARY KEY,
                  name TEXT,
                  description TEXT,
                  icon TEXT,
                  secret INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_achievements
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  telegram_id INTEGER,
                  achievement_code TEXT,
                  earned_at TEXT DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE(telegram_id, achievement_code))''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings
                 (key TEXT PRIMARY KEY, value TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS raids
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  date TEXT, status TEXT DEFAULT 'open',
                  result TEXT DEFAULT NULL,
                  created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS raid_participants
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  raid_id INTEGER, telegram_id INTEGER,
                  UNIQUE(raid_id, telegram_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS laundry_schedule
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  day TEXT, time TEXT, note TEXT,
                  taken_by INTEGER DEFAULT NULL,
                  created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS water_schedule
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  day TEXT, time TEXT, note TEXT,
                  created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS diary_entries
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  telegram_id INTEGER NOT NULL,
                  entry_date TEXT NOT NULL,
                  weekday TEXT,
                  weather TEXT,
                  discussion_rating INTEGER DEFAULT 0,
                  discussion_person TEXT,
                  discussion_topic TEXT,
                  story TEXT,
                  status TEXT DEFAULT 'draft',
                  submitted_at TEXT DEFAULT NULL,
                  locked_at TEXT DEFAULT NULL,
                  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                  updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE(telegram_id, entry_date))''')
    c.execute('''CREATE TABLE IF NOT EXISTS diary_words
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  entry_id INTEGER NOT NULL,
                  row_number INTEGER NOT NULL,
                  hanzi TEXT DEFAULT '',
                  pinyin TEXT DEFAULT '',
                  translation TEXT DEFAULT '',
                  UNIQUE(entry_id, row_number))''')
    c.execute('''CREATE TABLE IF NOT EXISTS diary_stars
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  telegram_id INTEGER NOT NULL,
                  entry_date TEXT NOT NULL,
                  stars INTEGER DEFAULT 0,
                  bonus INTEGER DEFAULT 0,
                  rated_by INTEGER DEFAULT NULL,
                  rated_at TEXT DEFAULT NULL,
                  UNIQUE(telegram_id, entry_date))''')
    c.execute('''CREATE TABLE IF NOT EXISTS diary_scores
                 (entry_id INTEGER PRIMARY KEY,
                  lesson_score TEXT DEFAULT '',
                  diary_score TEXT DEFAULT '',
                  lesson_comment TEXT DEFAULT '',
                  diary_comment TEXT DEFAULT '',
                  rated_by INTEGER DEFAULT NULL,
                  updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                  auto_diary_points INTEGER DEFAULT 0,
                  manual_diary_points INTEGER DEFAULT NULL,
                  awarded_diary_points INTEGER DEFAULT 0,
                  validation_warnings TEXT DEFAULT '[]')''')
    c.execute('''CREATE TABLE IF NOT EXISTS global_alerts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  alert_type TEXT NOT NULL,
                  title TEXT NOT NULL,
                  message TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  is_active INTEGER DEFAULT 1)''')
    c.execute('''CREATE TABLE IF NOT EXISTS daily_checks
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  check_type TEXT NOT NULL,
                  check_date TEXT NOT NULL,
                  telegram_id INTEGER NOT NULL,
                  status TEXT NOT NULL DEFAULT 'pending',
                  attempts_sent INTEGER NOT NULL DEFAULT 0,
                  first_sent_at TEXT DEFAULT NULL,
                  last_attempt_at TEXT DEFAULT NULL,
                  confirmed_at TEXT DEFAULT NULL,
                  escalated_at TEXT DEFAULT NULL,
                  penalized_at TEXT DEFAULT NULL,
                  penalty_points INTEGER NOT NULL DEFAULT 0,
                  note TEXT DEFAULT '',
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  UNIQUE(check_type, check_date, telegram_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS daily_check_exemptions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  telegram_id INTEGER NOT NULL,
                  check_type TEXT NOT NULL,
                  check_date TEXT NOT NULL,
                  reason_text TEXT DEFAULT '',
                  starts_at TEXT DEFAULT NULL,
                  ends_at TEXT DEFAULT NULL,
                  created_by INTEGER NOT NULL,
                  created_at TEXT NOT NULL,
                  status TEXT NOT NULL DEFAULT 'active')''')
    c.execute('''CREATE TABLE IF NOT EXISTS events
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  code TEXT NOT NULL,
                  title TEXT NOT NULL,
                  boss_name TEXT NOT NULL,
                  boss_image TEXT DEFAULT NULL,
                  reward_text TEXT DEFAULT NULL,
                  min_players INTEGER NOT NULL DEFAULT 3,
                  max_players INTEGER NOT NULL DEFAULT 5,
                  max_hp INTEGER NOT NULL,
                  current_hp INTEGER NOT NULL,
                  phase INTEGER NOT NULL,
                  state TEXT NOT NULL,
                  phase_started_at TEXT DEFAULT NULL,
                  started_at TEXT DEFAULT NULL,
                  ended_at TEXT DEFAULT NULL,
                  final_phase_deadline TEXT DEFAULT NULL,
                  vulnerability_until TEXT DEFAULT NULL,
                  overload_pressure INTEGER NOT NULL DEFAULT 0,
                  created_at TEXT NOT NULL)''')
    # Migrate: add mvp_user_id and extra_participants if not present
    try:
        c.execute("ALTER TABLE events ADD COLUMN mvp_user_id INTEGER DEFAULT NULL")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE events ADD COLUMN extra_participants TEXT DEFAULT NULL")
    except Exception:
        pass
    c.execute('''CREATE TABLE IF NOT EXISTS event_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  event_id INTEGER NOT NULL,
                  log_type TEXT NOT NULL,
                  message TEXT NOT NULL,
                  created_at TEXT NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS event_actions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  event_id INTEGER NOT NULL,
                  telegram_id INTEGER NOT NULL,
                  action_type TEXT NOT NULL,
                  question_id INTEGER DEFAULT NULL,
                  is_correct INTEGER NOT NULL,
                  base_value INTEGER NOT NULL,
                  modifier_value INTEGER NOT NULL,
                  final_value INTEGER NOT NULL,
                  created_at TEXT NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS event_participants
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  event_id INTEGER NOT NULL,
                  telegram_id INTEGER NOT NULL,
                  modifier_kind TEXT DEFAULT NULL,
                  modifier_code TEXT DEFAULT NULL,
                  modifier_role TEXT DEFAULT NULL,
                  active_used_phase1 INTEGER NOT NULL DEFAULT 0,
                  active_used_phase2 INTEGER NOT NULL DEFAULT 0,
                  active_used_phase3 INTEGER NOT NULL DEFAULT 0,
                  total_damage INTEGER NOT NULL DEFAULT 0,
                  total_support INTEGER NOT NULL DEFAULT 0,
                  created_at TEXT NOT NULL,
                  UNIQUE(event_id, telegram_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS event_team_members
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  event_id INTEGER NOT NULL,
                  telegram_id INTEGER NOT NULL,
                  joined_at TEXT NOT NULL,
                  UNIQUE(event_id, telegram_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS event_questions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  event_code TEXT NOT NULL,
                  action_type TEXT NOT NULL,
                  difficulty INTEGER NOT NULL DEFAULT 1,
                  prompt TEXT NOT NULL,
                  option_a TEXT NOT NULL,
                  option_b TEXT NOT NULL,
                  option_c TEXT NOT NULL,
                  correct_option TEXT NOT NULL,
                  explanation TEXT DEFAULT NULL,
                  created_at TEXT NOT NULL)''')
    conn.commit()
    conn.close()


def migrate_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS expected_students
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  full_name TEXT NOT NULL,
                  normalized_name TEXT UNIQUE NOT NULL,
                  group_label TEXT DEFAULT '',
                  room_number TEXT DEFAULT NULL,
                  telegram_id INTEGER DEFAULT NULL,
                  status TEXT DEFAULT 'pending',
                  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                  updated_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    c.execute("PRAGMA table_info(users)")
    user_columns = {row[1] for row in c.fetchall()}
    if 'avatar_url' not in user_columns:
        c.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT DEFAULT NULL")
    if 'room_number' not in user_columns:
        c.execute("ALTER TABLE users ADD COLUMN room_number TEXT DEFAULT NULL")
    if 'rep_score' not in user_columns:
        c.execute("ALTER TABLE users ADD COLUMN rep_score INTEGER DEFAULT 0")

    c.execute("PRAGMA table_info(shop_purchases)")
    shop_purchase_columns = {row[1] for row in c.fetchall()}
    if 'gifted_at' not in shop_purchase_columns:
        c.execute("ALTER TABLE shop_purchases ADD COLUMN gifted_at TEXT DEFAULT NULL")

    c.execute("PRAGMA table_info(user_status)")
    columns = {row[1] for row in c.fetchall()}
    if 'extra_raids' not in columns:
        c.execute("ALTER TABLE user_status ADD COLUMN extra_raids INTEGER DEFAULT 0")
    if 'theme_path' not in columns:
        c.execute("ALTER TABLE user_status ADD COLUMN theme_path TEXT DEFAULT NULL")
    if 'profile_showcase_kind' not in columns:
        c.execute("ALTER TABLE user_status ADD COLUMN profile_showcase_kind TEXT DEFAULT NULL")
    if 'profile_showcase_code' not in columns:
        c.execute("ALTER TABLE user_status ADD COLUMN profile_showcase_code TEXT DEFAULT NULL")
    if 'netwatch_locked_until' not in columns:
        c.execute("ALTER TABLE user_status ADD COLUMN netwatch_locked_until TEXT DEFAULT NULL")
    if 'terracota_armor' not in columns:
        c.execute("ALTER TABLE user_status ADD COLUMN terracota_armor INTEGER DEFAULT 0")
    if 'scan_attempts' not in columns:
        c.execute("ALTER TABLE user_status ADD COLUMN scan_attempts INTEGER DEFAULT 0")
    if 'protocol_fragments' not in columns:
        c.execute("ALTER TABLE user_status ADD COLUMN protocol_fragments INTEGER DEFAULT 0")
    c.execute("PRAGMA table_info(diary_scores)")
    diary_score_columns = {row[1] for row in c.fetchall()}
    if 'auto_diary_points' not in diary_score_columns:
        c.execute("ALTER TABLE diary_scores ADD COLUMN auto_diary_points INTEGER DEFAULT 0")
    if 'manual_diary_points' not in diary_score_columns:
        c.execute("ALTER TABLE diary_scores ADD COLUMN manual_diary_points INTEGER DEFAULT NULL")
    if 'awarded_diary_points' not in diary_score_columns:
        c.execute("ALTER TABLE diary_scores ADD COLUMN awarded_diary_points INTEGER DEFAULT 0")
    if 'validation_warnings' not in diary_score_columns:
        c.execute("ALTER TABLE diary_scores ADD COLUMN validation_warnings TEXT DEFAULT '[]'")
    c.execute("PRAGMA table_info(events)")
    event_columns = {row[1] for row in c.fetchall()}
    if event_columns:
        if 'phase_started_at' not in event_columns:
            c.execute("ALTER TABLE events ADD COLUMN phase_started_at TEXT DEFAULT NULL")
        if 'started_at' not in event_columns:
            c.execute("ALTER TABLE events ADD COLUMN started_at TEXT DEFAULT NULL")
        if 'ended_at' not in event_columns:
            c.execute("ALTER TABLE events ADD COLUMN ended_at TEXT DEFAULT NULL")
        if 'final_phase_deadline' not in event_columns:
            c.execute("ALTER TABLE events ADD COLUMN final_phase_deadline TEXT DEFAULT NULL")
        if 'vulnerability_until' not in event_columns:
            c.execute("ALTER TABLE events ADD COLUMN vulnerability_until TEXT DEFAULT NULL")
        if 'overload_pressure' not in event_columns:
            c.execute("ALTER TABLE events ADD COLUMN overload_pressure INTEGER NOT NULL DEFAULT 0")
        if 'reward_text' not in event_columns:
            c.execute("ALTER TABLE events ADD COLUMN reward_text TEXT DEFAULT NULL")
        if 'min_players' not in event_columns:
            c.execute("ALTER TABLE events ADD COLUMN min_players INTEGER NOT NULL DEFAULT 3")
        if 'max_players' not in event_columns:
            c.execute("ALTER TABLE events ADD COLUMN max_players INTEGER NOT NULL DEFAULT 5")
    c.execute('''CREATE TABLE IF NOT EXISTS event_team_members
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  event_id INTEGER NOT NULL,
                  telegram_id INTEGER NOT NULL,
                  joined_at TEXT NOT NULL,
                  UNIQUE(event_id, telegram_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS daily_checks
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  check_type TEXT NOT NULL,
                  check_date TEXT NOT NULL,
                  telegram_id INTEGER NOT NULL,
                  status TEXT NOT NULL DEFAULT 'pending',
                  attempts_sent INTEGER NOT NULL DEFAULT 0,
                  first_sent_at TEXT DEFAULT NULL,
                  last_attempt_at TEXT DEFAULT NULL,
                  confirmed_at TEXT DEFAULT NULL,
                  escalated_at TEXT DEFAULT NULL,
                  penalized_at TEXT DEFAULT NULL,
                  penalty_points INTEGER NOT NULL DEFAULT 0,
                  note TEXT DEFAULT '',
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  UNIQUE(check_type, check_date, telegram_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS daily_check_exemptions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  telegram_id INTEGER NOT NULL,
                  check_type TEXT NOT NULL,
                  check_date TEXT NOT NULL,
                  reason_text TEXT DEFAULT '',
                  starts_at TEXT DEFAULT NULL,
                  ends_at TEXT DEFAULT NULL,
                  created_by INTEGER NOT NULL,
                  created_at TEXT NOT NULL,
                  status TEXT NOT NULL DEFAULT 'active')''')
    c.execute('''CREATE TABLE IF NOT EXISTS contracts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  title TEXT NOT NULL,
                  description TEXT NOT NULL,
                  category TEXT NOT NULL DEFAULT 'other',
                  reward_stars INTEGER NOT NULL,
                  fee_stars INTEGER NOT NULL,
                  creator_telegram_id INTEGER NOT NULL,
                  assignee_telegram_id INTEGER DEFAULT NULL,
                  status TEXT NOT NULL DEFAULT 'open',
                  is_suspicious INTEGER NOT NULL DEFAULT 0,
                  suspicious_reason TEXT DEFAULT NULL,
                  created_at TEXT NOT NULL,
                  accepted_at TEXT DEFAULT NULL,
                  completed_at TEXT DEFAULT NULL,
                  cancelled_at TEXT DEFAULT NULL,
                  disputed_at TEXT DEFAULT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS economy_log
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  telegram_id INTEGER NOT NULL,
                  operation TEXT NOT NULL,
                  amount INTEGER NOT NULL,
                  balance_after INTEGER DEFAULT NULL,
                  reference_id INTEGER DEFAULT NULL,
                  reference_type TEXT DEFAULT NULL,
                  note TEXT DEFAULT NULL,
                  created_at TEXT NOT NULL)''')
    conn.commit()
    conn.close()


def ensure_seed_data():
    conn = get_conn()
    c = conn.cursor()
    for full_name in EXPECTED_STUDENT_NAMES:
        normalized_name = normalize_expected_student_name(full_name)
        c.execute(
            '''INSERT INTO expected_students
               (full_name, normalized_name, group_label, status)
               VALUES (?, ?, 'beijing_2026', 'pending')
               ON CONFLICT(normalized_name) DO UPDATE SET
                 full_name=excluded.full_name,
                 group_label=COALESCE(NULLIF(expected_students.group_label, ''), excluded.group_label),
                 updated_at=CURRENT_TIMESTAMP''',
            (full_name, normalized_name),
        )
    for item in SHOP_ITEM_SEEDS:
        c.execute(
            '''INSERT INTO shop_items
               (code, name, description, icon, price, daily_limit, category, active)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1)
               ON CONFLICT(code) DO UPDATE SET
                 name=excluded.name,
                 description=excluded.description,
                 icon=excluded.icon,
                 price=excluded.price,
                 daily_limit=excluded.daily_limit,
                 category=excluded.category,
                 active=1''',
            item,
        )
    c.execute("SELECT COUNT(*) FROM event_questions WHERE event_code='architect'")
    architect_count = c.fetchone()[0]
    if architect_count == 0:
        created_at = datetime.utcnow().isoformat()
        for action_type, questions in ARCHITECT_QUESTION_SEEDS.items():
            for question in questions:
                c.execute(
                    '''INSERT INTO event_questions
                       (event_code, action_type, difficulty, prompt, option_a, option_b, option_c, correct_option, explanation, created_at)
                       VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?)''',
                    (
                        'architect',
                        action_type,
                        question["prompt"],
                        question["option_a"],
                        question["option_b"],
                        question["option_c"],
                        question["correct_option"],
                        question.get("explanation"),
                        created_at,
                    ),
                )
    conn.commit()
    conn.close()


def create_global_alert(alert_type: str, title: str, message: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE global_alerts SET is_active = 0 WHERE is_active = 1")
    c.execute(
        "INSERT INTO global_alerts (alert_type, title, message, created_at, is_active) VALUES (?, ?, ?, ?, 1)",
        (alert_type, title, message, datetime.utcnow().isoformat()),
    )
    alert_id = c.lastrowid
    conn.commit()
    conn.close()
    return alert_id


def get_current_global_alert():
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        '''SELECT id, alert_type, title, message, created_at, is_active
           FROM global_alerts
           WHERE is_active = 1
           ORDER BY id DESC
           LIMIT 1'''
    )
    row = c.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "id": row[0],
        "alert_type": row[1],
        "title": row[2],
        "message": row[3],
        "created_at": row[4],
        "is_active": bool(row[5]),
    }


init_db()
migrate_db()
ensure_seed_data()


def now_iso() -> str:
    return datetime.utcnow().isoformat()


def parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def add_event_log(c, event_id: int, log_type: str, message: str):
    c.execute(
        "INSERT INTO event_logs (event_id, log_type, message, created_at) VALUES (?, ?, ?, ?)",
        (event_id, log_type, message, now_iso()),
    )


def get_user_display_name(c, telegram_id: int) -> str:
    c.execute("SELECT full_name FROM users WHERE telegram_id=?", (telegram_id,))
    row = c.fetchone()
    return row[0] if row and row[0] else str(telegram_id)


def normalize_presence_check_type(value: str) -> str:
    check_type = str(value or "").strip().lower()
    if check_type not in PRESENCE_CHECK_TYPES:
        raise HTTPException(status_code=400, detail="Invalid check_type")
    return check_type


def normalize_presence_date(value: Optional[str] = None) -> str:
    return str(value or datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')).strip()


def new_manual_presence_session() -> str:
    return datetime.now(BEIJING_TZ).strftime('%Y-%m-%d__%H%M%S%f')


def latest_manual_presence_session(c) -> Optional[str]:
    today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
    c.execute(
        '''SELECT check_date
           FROM daily_checks
           WHERE check_type='manual' AND check_date LIKE ?
           ORDER BY check_date DESC
           LIMIT 1''',
        (f"{today}__%",),
    )
    row = c.fetchone()
    return row[0] if row else None


def serialize_presence_row(row):
    return {
        "id": row[0],
        "check_type": row[1],
        "check_date": row[2],
        "telegram_id": row[3],
        "full_name": row[4] or str(row[3]),
        "status": row[5],
        "attempts_sent": row[6],
        "first_sent_at": row[7],
        "last_attempt_at": row[8],
        "confirmed_at": row[9],
        "escalated_at": row[10],
        "penalized_at": row[11],
        "penalty_points": row[12],
        "note": row[13] or "",
        "points": row[14] or 0,
    }


def fetch_presence_row(c, check_type: str, check_date: str, telegram_id: int):
    c.execute(
        '''SELECT dc.id, dc.check_type, dc.check_date, dc.telegram_id, u.full_name,
                  dc.status, dc.attempts_sent, dc.first_sent_at, dc.last_attempt_at,
                  dc.confirmed_at, dc.escalated_at, dc.penalized_at,
                  dc.penalty_points, dc.note, u.points
           FROM daily_checks dc
           LEFT JOIN users u ON u.telegram_id = dc.telegram_id
           WHERE dc.check_type=? AND dc.check_date=? AND dc.telegram_id=?''',
        (check_type, check_date, telegram_id),
    )
    row = c.fetchone()
    return serialize_presence_row(row) if row else None


def ensure_presence_check(c, check_type: str, check_date: str, telegram_id: int, note: str = ""):
    now = now_iso()
    c.execute(
        '''INSERT INTO daily_checks
           (check_type, check_date, telegram_id, status, note, created_at, updated_at)
           VALUES (?, ?, ?, 'pending', ?, ?, ?)
           ON CONFLICT(check_type, check_date, telegram_id) DO NOTHING''',
        (check_type, check_date, telegram_id, note, now, now),
    )
    return fetch_presence_row(c, check_type, check_date, telegram_id)


def has_active_free_time(c, telegram_id: int) -> Optional[int]:
    now_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
    c.execute(
        '''SELECT id
           FROM shop_purchases
           WHERE telegram_id=?
             AND item_code='casino_walk'
             AND status='active'
             AND (expires_at IS NULL OR expires_at >= ?)
           ORDER BY id DESC
           LIMIT 1''',
        (telegram_id, now_str),
    )
    row = c.fetchone()
    return row[0] if row else None


def apply_presence_status(c, check_type: str, check_date: str, telegram_id: int, status: str, note: str = ""):
    if status not in PRESENCE_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")

    ensure_presence_check(c, check_type, check_date, telegram_id)
    now = now_iso()
    confirmed_at = now if status in ("confirmed", "free_time", "admin_approved") else None
    c.execute(
        '''UPDATE daily_checks
           SET status=?,
               note=?,
               confirmed_at=COALESCE(?, confirmed_at),
               updated_at=?
           WHERE check_type=? AND check_date=? AND telegram_id=?''',
        (status, note, confirmed_at, now, check_type, check_date, telegram_id),
    )
    return fetch_presence_row(c, check_type, check_date, telegram_id)


def get_presence_keyboard_markup(check_type: str, check_date: Optional[str] = None):
    if check_type == "morning":
        return {
            "inline_keyboard": [[
                {"text": "✅ Я проснулся", "callback_data": "presence:morning:confirm"},
                {"text": "🙋 Нужна помощь", "callback_data": "presence:morning:request_leave"},
            ]]
        }
    if check_type == "manual":
        session = check_date or normalize_presence_date()
        return {
            "inline_keyboard": [[
                {"text": "✅ Я на месте", "callback_data": f"presence:manual:{session}:confirm"},
                {"text": "🙋 Нужен отгул", "callback_data": f"presence:manual:{session}:request_leave"},
            ]]
        }

    return {
        "inline_keyboard": [
            [{"text": "✅ Я в комнате", "callback_data": "presence:evening:confirm"}],
            [
                {"text": "🕐 Свободное время", "callback_data": "presence:evening:free_time"},
                {"text": "🙋 Нужен отгул", "callback_data": "presence:evening:request_leave"},
            ],
        ]
    }


def get_presence_message_text(check_type: str, attempt_no: int = 1):
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
        f"Попытка {attempt_no}/3. 21:00 — нужно быть в комнате.\n"
        "Если у тебя разрешение от админа или активное «Свободное время», выбери нужную кнопку."
    )


async def send_telegram_message(chat_id: int, text: str, reply_markup: Optional[dict] = None):
    if not BOT_TOKEN:
        return False, {"detail": "BOT_TOKEN is not configured"}

    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json=payload,
        ) as r:
            if r.status >= 400:
                try:
                    data = await r.json()
                except Exception:
                    data = {"detail": await r.text()}
                return False, data
            return True, await r.json()


async def broadcast_announcement_to_telegram(text: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        '''SELECT telegram_id
           FROM users
           WHERE telegram_id IS NOT NULL
           ORDER BY full_name COLLATE NOCASE'''
    )
    recipients = [int(row[0]) for row in c.fetchall() if row[0]]
    conn.close()

    sent = 0
    failed = 0
    message = f"📢 Объявление:\n\n{text}"
    for telegram_id in recipients:
        ok, _ = await send_telegram_message(telegram_id, message)
        if ok:
            sent += 1
        else:
            failed += 1

    return {"total": len(recipients), "sent": sent, "failed": failed}


def get_player_modifier(c, telegram_id: int):
    c.execute(
        '''SELECT implant_id
           FROM user_implants
           WHERE telegram_id=? AND durability > 0
           ORDER BY CASE implant_id
             WHEN 'implant_red_dragon' THEN 1
             WHEN 'implant_terracota' THEN 2
             WHEN 'implant_guanxi' THEN 3
             ELSE 99
           END
           LIMIT 1''',
        (telegram_id,),
    )
    implant = c.fetchone()
    if implant and implant[0] in EVENT_MODIFIER_ROLE_MAP:
        kind, role = EVENT_MODIFIER_ROLE_MAP[implant[0]]
        return {"modifier_kind": kind, "modifier_code": implant[0], "modifier_role": role}

    c.execute(
        '''SELECT card_id
           FROM user_cards
           WHERE telegram_id=? AND durability > 0
           ORDER BY CASE card_id
             WHEN 'card_star' THEN 1
             WHEN 'card_zhongli' THEN 2
             WHEN 'card_pyro' THEN 3
             WHEN 'card_fox' THEN 4
             WHEN 'card_fairy' THEN 5
             WHEN 'card_literature' THEN 6
             WHEN 'card_forest' THEN 7
             WHEN 'card_sea' THEN 8
             WHEN 'card_moon' THEN 9
             ELSE 99
           END
           LIMIT 1''',
        (telegram_id,),
    )
    card = c.fetchone()
    if card and card[0] in EVENT_MODIFIER_ROLE_MAP:
        kind, role = EVENT_MODIFIER_ROLE_MAP[card[0]]
        return {"modifier_kind": kind, "modifier_code": card[0], "modifier_role": role}
    return {"modifier_kind": None, "modifier_code": None, "modifier_role": None}


def ensure_event_participant(c, event_id: int, telegram_id: int):
    c.execute(
        '''SELECT id, modifier_kind, modifier_code, modifier_role,
                  active_used_phase1, active_used_phase2, active_used_phase3,
                  total_damage, total_support
           FROM event_participants
           WHERE event_id=? AND telegram_id=?''',
        (event_id, telegram_id),
    )
    row = c.fetchone()
    if row:
        return {
            "id": row[0],
            "modifier_kind": row[1],
            "modifier_code": row[2],
            "modifier_role": row[3],
            "active_used_phase1": row[4],
            "active_used_phase2": row[5],
            "active_used_phase3": row[6],
            "total_damage": row[7],
            "total_support": row[8],
        }

    modifier = get_player_modifier(c, telegram_id)
    c.execute(
        '''INSERT INTO event_participants
           (event_id, telegram_id, modifier_kind, modifier_code, modifier_role, created_at)
           VALUES (?, ?, ?, ?, ?, ?)''',
        (
            event_id,
            telegram_id,
            modifier["modifier_kind"],
            modifier["modifier_code"],
            modifier["modifier_role"],
            now_iso(),
        ),
    )
    return ensure_event_participant(c, event_id, telegram_id)


def fetch_event_row(c, event_id: int):
    c.execute(
        '''SELECT id, code, title, boss_name, boss_image,
                  reward_text, min_players, max_players,
                  max_hp, current_hp, phase, state,
                  phase_started_at, started_at, ended_at, final_phase_deadline,
                  vulnerability_until, overload_pressure, created_at,
                  mvp_user_id, extra_participants
           FROM events WHERE id=?''',
        (event_id,),
    )
    row = c.fetchone()
    if not row:
        return None
    import json as _json
    raw_extra = row[20]
    try:
        extra = _json.loads(raw_extra) if raw_extra else []
    except Exception:
        extra = []
    return {
        "id": row[0],
        "code": row[1],
        "title": row[2],
        "boss_name": row[3],
        "boss_image": row[4],
        "reward_text": row[5],
        "min_players": row[6],
        "max_players": row[7],
        "max_hp": row[8],
        "current_hp": row[9],
        "phase": row[10],
        "state": row[11],
        "phase_started_at": row[12],
        "started_at": row[13],
        "ended_at": row[14],
        "final_phase_deadline": row[15],
        "vulnerability_until": row[16],
        "overload_pressure": row[17],
        "created_at": row[18],
        "mvp_user_id": row[19],
        "extra_participants": extra,
    }


def get_event_team_members(c, event_id: int):
    c.execute(
        '''SELECT etm.telegram_id, u.full_name, etm.joined_at
           FROM event_team_members etm
           LEFT JOIN users u ON u.telegram_id = etm.telegram_id
           WHERE etm.event_id=?
           ORDER BY etm.id ASC''',
        (event_id,),
    )
    return [
        {
            "telegram_id": row[0],
            "full_name": row[1] or "Аноним",
            "joined_at": row[2],
        }
        for row in c.fetchall()
    ]


def is_event_team_member(c, event_id: int, telegram_id: int) -> bool:
    c.execute(
        "SELECT 1 FROM event_team_members WHERE event_id=? AND telegram_id=? LIMIT 1",
        (event_id, telegram_id),
    )
    return c.fetchone() is not None


def ensure_admin_event_team_member(c, event_id: int, telegram_id: int) -> bool:
    if telegram_id not in ADMIN_IDS:
        return False
    if is_event_team_member(c, event_id, telegram_id):
        return True
    c.execute(
        "INSERT OR IGNORE INTO event_team_members (event_id, telegram_id, joined_at) VALUES (?, ?, ?)",
        (event_id, telegram_id, now_iso()),
    )
    return True


def is_vulnerability_active(event_row: dict) -> bool:
    vulnerability_until = parse_iso(event_row.get("vulnerability_until"))
    return bool(vulnerability_until and vulnerability_until > datetime.utcnow())


def apply_architect_phase_transitions(c, event_row: dict):
    changed = False
    hp_ratio = event_row["current_hp"] / event_row["max_hp"] if event_row["max_hp"] else 0

    if event_row["state"] == "ACTIVE" and event_row["phase"] == 1 and hp_ratio <= ARCHITECT_PHASE2_THRESHOLD:
        event_row["phase"] = 2
        event_row["phase_started_at"] = now_iso()
        c.execute(
            "UPDATE events SET phase=2, phase_started_at=? WHERE id=?",
            (event_row["phase_started_at"], event_row["id"]),
        )
        add_event_log(c, event_row["id"], "boss", "协议已重写。 / Протокол переписан.")
        changed = True

    if event_row["state"] == "ACTIVE" and event_row["phase"] == 2 and hp_ratio <= ARCHITECT_PHASE3_THRESHOLD:
        event_row["phase"] = 3
        event_row["phase_started_at"] = now_iso()
        event_row["final_phase_deadline"] = (datetime.utcnow() + timedelta(seconds=ARCHITECT_FINAL_PHASE_SECONDS)).isoformat()
        c.execute(
            "UPDATE events SET phase=3, phase_started_at=?, final_phase_deadline=? WHERE id=?",
            (event_row["phase_started_at"], event_row["final_phase_deadline"], event_row["id"]),
        )
        add_event_log(c, event_row["id"], "boss", "系统过载。 / Система перегружена.")
        changed = True

    return changed


def refresh_event_state(c, event_row: dict):
    if not event_row:
        return None

    if event_row["state"] == "ACTIVE" and event_row["phase"] == 3:
        deadline = parse_iso(event_row.get("final_phase_deadline"))
        if deadline and datetime.utcnow() >= deadline and event_row["current_hp"] > 0:
            event_row["state"] = "FAILED"
            event_row["phase"] = 5
            event_row["ended_at"] = now_iso()
            c.execute(
                "UPDATE events SET state='FAILED', phase=5, ended_at=? WHERE id=?",
                (event_row["ended_at"], event_row["id"]),
            )
            add_event_log(c, event_row["id"], "system", "Architect event failed: overload timer expired.")

    if event_row["state"] == "ACTIVE" and event_row["current_hp"] <= 0:
        event_row["current_hp"] = 0
        event_row["state"] = "FINISHED"
        event_row["phase"] = 4
        event_row["ended_at"] = now_iso()
        # Calculate MVP: participant with highest total_damage
        c.execute(
            """SELECT telegram_id FROM event_participants
               WHERE event_id=? ORDER BY total_damage DESC, total_support DESC LIMIT 1""",
            (event_row["id"],),
        )
        mvp_row = c.fetchone()
        mvp_id = mvp_row[0] if mvp_row else None
        c.execute(
            "UPDATE events SET current_hp=0, state='FINISHED', phase=4, ended_at=?, mvp_user_id=? WHERE id=?",
            (event_row["ended_at"], mvp_id, event_row["id"]),
        )
        event_row["mvp_user_id"] = mvp_id
        add_event_log(c, event_row["id"], "system", "Architect event completed.")

    apply_architect_phase_transitions(c, event_row)
    return fetch_event_row(c, event_row["id"])


def get_event_snapshot(event_id: int):
    conn = get_conn()
    c = conn.cursor()
    event_row = fetch_event_row(c, event_id)
    if not event_row:
        conn.close()
        return None

    event_row = refresh_event_state(c, event_row)
    conn.commit()

    c.execute(
        "SELECT id, log_type, message, created_at FROM event_logs WHERE event_id=? ORDER BY id DESC LIMIT 30",
        (event_id,),
    )
    logs = [
        {"id": row[0], "log_type": row[1], "message": row[2], "created_at": row[3]}
        for row in c.fetchall()
    ]
    logs.reverse()

    c.execute("SELECT COUNT(*), COALESCE(SUM(CASE WHEN final_value > 0 THEN final_value ELSE 0 END), 0) FROM event_actions WHERE event_id=?", (event_id,))
    action_row = c.fetchone()
    total_actions = action_row[0] if action_row else 0
    total_damage = action_row[1] if action_row else 0
    team_members = get_event_team_members(c, event_id)

    snapshot = {
        **event_row,
        "team_members": team_members,
        "team_count": len(team_members),
        "logs": logs,
        "total_actions": total_actions,
        "total_damage": total_damage,
        "vulnerability_active": is_vulnerability_active(event_row),
        "vulnerability_until": event_row.get("vulnerability_until"),
        "overload_penalty_active": event_row["overload_pressure"] >= ARCHITECT_OVERLOAD_PENALTY_THRESHOLD,
    }
    conn.close()
    return snapshot


def get_current_or_latest_event_id():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM events WHERE state IN ('REGISTRATION', 'ACTIVE') ORDER BY id DESC")
    rows = c.fetchall()
    row = None
    for candidate in rows:
        event_row = fetch_event_row(c, candidate[0])
        event_row = refresh_event_state(c, event_row)
        if event_row and event_row["state"] in ("REGISTRATION", "ACTIVE"):
            row = candidate
            break
    conn.commit()
    conn.close()
    return row[0] if row else None


def get_blocking_event_id():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM events WHERE state IN ('REGISTRATION', 'ACTIVE') ORDER BY id DESC")
    rows = c.fetchall()
    blocking_id = None
    for candidate in rows:
        event_row = fetch_event_row(c, candidate[0])
        event_row = refresh_event_state(c, event_row)
        if event_row and event_row["state"] in ("REGISTRATION", "ACTIVE"):
            blocking_id = candidate[0]
            break
    conn.commit()
    conn.close()
    return blocking_id


def choose_architect_question(c, action_type: str):
    c.execute(
        '''SELECT id, prompt, option_a, option_b, option_c, explanation
           FROM event_questions
           WHERE event_code='architect' AND action_type=?
           ORDER BY RANDOM()
           LIMIT 1''',
        (action_type,),
    )
    row = c.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "prompt": row[1],
        "option_a": row[2],
        "option_b": row[3],
        "option_c": row[4],
        "explanation": row[5],
    }


def get_architect_base_value(phase: int, action_type: str, is_correct: bool) -> int:
    if action_type == "sync":
        return 0
    if not is_correct:
        return 0

    phase_values = {
        1: {"attack": 20, "protocol": 10, "stabilize": 10},
        2: {"attack": 8, "protocol": 28, "stabilize": 12},
        3: {"attack": 18, "protocol": 22, "stabilize": 18},
    }
    return phase_values.get(phase, {}).get(action_type, 0)


def get_current_phase_active_field(phase: int) -> Optional[str]:
    return {
        1: "active_used_phase1",
        2: "active_used_phase2",
        3: "active_used_phase3",
    }.get(phase)


def open_vulnerability_window(c, event_row: dict):
    until = (datetime.utcnow() + timedelta(seconds=ARCHITECT_VULNERABILITY_SECONDS)).isoformat()
    c.execute("UPDATE events SET vulnerability_until=? WHERE id=?", (until, event_row["id"]))
    add_event_log(c, event_row["id"], "system", "SYNC WINDOW OPENED")
    add_event_log(c, event_row["id"], "boss", "ARCHITECT VULNERABILITY EXPOSED")
    event_row["vulnerability_until"] = until


def maybe_trigger_sync_window(c, event_row: dict):
    since = (datetime.utcnow() - timedelta(seconds=ARCHITECT_SYNC_WINDOW_SECONDS)).isoformat()
    c.execute(
        '''SELECT COUNT(*)
           FROM event_actions
           WHERE event_id=? AND action_type='sync' AND created_at >= ?''',
        (event_row["id"], since),
    )
    sync_count = c.fetchone()[0]
    if sync_count >= ARCHITECT_SYNC_WINDOW_COUNT and not is_vulnerability_active(event_row):
        open_vulnerability_window(c, event_row)


def compute_event_action_result(c, event_row: dict, participant: dict, action_type: str, is_correct: bool, use_active_modifier: bool):
    phase = event_row["phase"]
    role = participant.get("modifier_role")
    base_value = get_architect_base_value(phase, action_type, is_correct)
    modifier_value = 0
    support_value = 0
    final_value = base_value
    active_note = None
    pressure_delta = 0

    if action_type == "sync":
        sync_value = 1
        if role == "control":
            sync_value = 2
            modifier_value += 1
        if use_active_modifier and role == "control":
            active_field = get_current_phase_active_field(phase)
            if active_field and not participant.get(active_field):
                sync_value += 2
                modifier_value += 2
                active_note = f"{participant['modifier_code']} усилил SYNC."
                c.execute(f"UPDATE event_participants SET {active_field}=1 WHERE id=?", (participant["id"],))
                participant[active_field] = 1
        support_value = sync_value
        final_value = 0
        return {
            "base_value": 0,
            "modifier_value": modifier_value,
            "final_value": 0,
            "support_value": support_value,
            "pressure_delta": 0,
            "active_note": active_note,
            "penalty_active": False,
        }

    if action_type in ("attack", "protocol"):
        pressure_delta = 3 if phase == 3 else 0
    elif action_type == "stabilize":
        pressure_delta = -5 if phase == 3 else 0

    if role == "assault" and action_type == "attack" and final_value > 0:
        bonus = max(1, round(final_value * 0.2))
        final_value += bonus
        modifier_value += bonus
    if role == "control" and action_type == "protocol" and final_value > 0:
        bonus = max(1, round(final_value * 0.2))
        final_value += bonus
        modifier_value += bonus
    if role == "defense" and action_type == "stabilize" and final_value > 0:
        bonus = max(1, round(final_value * 0.2))
        support_value += final_value + bonus
        modifier_value += bonus
    elif action_type == "stabilize":
        support_value += final_value

    if use_active_modifier:
        active_field = get_current_phase_active_field(phase)
        if active_field and not participant.get(active_field):
            if role == "assault" and action_type in ("attack", "protocol") and final_value > 0:
                bonus = max(1, round(final_value * 0.4))
                final_value += bonus
                modifier_value += bonus
                active_note = f"{participant['modifier_code']} усилил offensive protocol."
            elif role == "defense" and event_row["overload_pressure"] >= ARCHITECT_OVERLOAD_PENALTY_THRESHOLD:
                active_note = f"{participant['modifier_code']} нейтрализовал штраф перегрузки."
            elif role == "control":
                open_vulnerability_window(c, event_row)
                active_note = f"{participant['modifier_code']} вскрыл уязвимость Архитектора."
            if active_note:
                c.execute(f"UPDATE event_participants SET {active_field}=1 WHERE id=?", (participant["id"],))
                participant[active_field] = 1

    if is_vulnerability_active(event_row) and action_type in ("attack", "protocol") and final_value > 0:
        bonus = max(1, round(final_value * 0.3))
        final_value += bonus
        modifier_value += bonus

    penalty_active = event_row["overload_pressure"] >= ARCHITECT_OVERLOAD_PENALTY_THRESHOLD
    if penalty_active and action_type in ("attack", "protocol") and final_value > 0:
        penalty_multiplier = ARCHITECT_OVERLOAD_PENALTY_MULTIPLIER
        if role == "defense":
            penalty_multiplier = 0.9
        reduced = max(0, final_value - round(final_value * penalty_multiplier))
        final_value = max(0, round(final_value * penalty_multiplier))
        modifier_value -= reduced

    if action_type == "stabilize" and support_value == 0:
        support_value = final_value

    return {
        "base_value": base_value,
        "modifier_value": modifier_value,
        "final_value": final_value if action_type != "stabilize" else 0,
        "support_value": support_value,
        "pressure_delta": pressure_delta,
        "active_note": active_note,
        "penalty_active": penalty_active,
    }


def get_marzban_user_by_telegram(telegram_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT marzban_username FROM users WHERE telegram_id=?", (telegram_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None


def get_extra_raids(c, telegram_id: int) -> int:
    c.execute("SELECT extra_raids FROM user_status WHERE telegram_id=?", (telegram_id,))
    row = c.fetchone()
    return row[0] if row else 0


def user_raid_attempt_count(c, today: str, telegram_id: int) -> int:
    c.execute(
        '''SELECT COUNT(DISTINCT rp.raid_id)
           FROM raid_participants rp
           JOIN raids r ON r.id = rp.raid_id
           WHERE rp.telegram_id=? AND r.date=?''',
        (telegram_id, today),
    )
    row = c.fetchone()
    return row[0] if row and row[0] is not None else 0


def public_finished_raid_count(c, today: str) -> int:
    placeholders = ','.join('?' * len(ADMIN_IDS))
    c.execute(
        f'''SELECT COUNT(DISTINCT r.id)
            FROM raids r
            JOIN raid_participants rp ON rp.raid_id = r.id
            WHERE r.date=? AND r.status='finished'
            AND rp.telegram_id NOT IN ({placeholders})''',
        [today] + ADMIN_IDS,
    )
    row = c.fetchone()
    return row[0] if row and row[0] is not None else 0


def latest_visible_raid(c, today: str, telegram_id: int):
    if telegram_id in ADMIN_IDS:
        c.execute("SELECT id, status, result FROM raids WHERE date=? ORDER BY id DESC LIMIT 1", (today,))
        return c.fetchone()

    placeholders = ','.join('?' * len(ADMIN_IDS))
    c.execute(
        f'''SELECT r.id, r.status, r.result
            FROM raids r
            WHERE r.date=?
              AND (
                r.status='open'
                OR EXISTS (
                    SELECT 1
                    FROM raid_participants rp
                    WHERE rp.raid_id=r.id
                      AND rp.telegram_id NOT IN ({placeholders})
                )
              )
            ORDER BY r.id DESC
            LIMIT 1''',
        [today] + ADMIN_IDS,
    )
    return c.fetchone()


def is_diary_staff(telegram_id: Optional[int]) -> bool:
    return telegram_id in ADMIN_IDS


def get_weekday_ru(entry_date: str) -> str:
    try:
        weekday_index = datetime.strptime(entry_date, '%Y-%m-%d').weekday()
    except ValueError:
        return ''
    weekdays = [
        'Понедельник',
        'Вторник',
        'Среда',
        'Четверг',
        'Пятница',
        'Суббота',
        'Воскресенье',
    ]
    return weekdays[weekday_index]


def normalize_diary_words(words) -> list:
    source = words if isinstance(words, list) else []
    normalized = []
    for index in range(DIARY_WORD_LIMIT):
        row = source[index] if index < len(source) and isinstance(source[index], dict) else {}
        normalized.append({
            "row_number": index + 1,
            "hanzi": str(row.get("hanzi", "")).strip(),
            "pinyin": str(row.get("pinyin", "")).strip(),
            "translation": str(row.get("translation", "")).strip(),
        })
    return normalized


def count_story_hanzi(text: str) -> int:
    return len(HANZI_RE.findall(text or ''))


def count_filled_diary_rows(words: list) -> int:
    return sum(1 for row in normalize_diary_words(words) if row["hanzi"] and row["pinyin"] and row["translation"])


def validate_diary_entry_content(words: list, story: str) -> dict:
    normalized_words = normalize_diary_words(words)
    warnings = []
    filled_rows = 0

    for index, row in enumerate(normalized_words, start=1):
        hanzi = row["hanzi"]
        pinyin = row["pinyin"]
        translation = row["translation"]
        has_any = bool(hanzi or pinyin or translation)
        is_full = bool(hanzi and pinyin and translation)

        if is_full:
            filled_rows += 1
        elif has_any:
            warnings.append(f"Строка {index}: заполнена не полностью.")

        if hanzi:
            if not HANZI_RE.search(hanzi):
                warnings.append(f"Строка {index}: в 汉字 нет китайских символов.")
            if LATIN_RE.search(hanzi):
                warnings.append(f"Строка {index}: в 汉字 не должно быть латиницы.")

        if pinyin and not PINYIN_RE.fullmatch(pinyin):
            warnings.append(f"Строка {index}: pinyin должен быть в формате ni3 hao3.")

        if translation and len(translation) < 2:
            warnings.append(f"Строка {index}: перевод слишком короткий.")

    story_hanzi = count_story_hanzi(story)
    if filled_rows < DIARY_MIN_FILLED_ROWS:
        warnings.append(
            f"Полностью заполнено только {filled_rows}/15 строк. Нужно минимум {DIARY_MIN_FILLED_ROWS}."
        )
    if story_hanzi < DIARY_MIN_STORY_HANZI:
        warnings.append(
            f"В тексте дня только {story_hanzi} иероглифов. Нужно минимум {DIARY_MIN_STORY_HANZI}."
        )

    deduped_warnings = []
    seen = set()
    for warning in warnings:
        if warning not in seen:
            seen.add(warning)
            deduped_warnings.append(warning)

    return {
        "warnings": deduped_warnings,
        "filled_rows": filled_rows,
        "story_hanzi": story_hanzi,
        "auto_diary_points": DIARY_AUTO_POINTS_CLEAN if not deduped_warnings else DIARY_AUTO_POINTS_WARN,
    }


def parse_optional_diary_points(value):
    if value in (None, ''):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid diary points")
    if parsed < 0 or parsed > DIARY_AUTO_POINTS_CLEAN:
        raise HTTPException(status_code=400, detail="Diary points out of range")
    return parsed


def store_diary_words(c, entry_id: int, words: list):
    for row in normalize_diary_words(words):
        c.execute(
            '''INSERT INTO diary_words (entry_id, row_number, hanzi, pinyin, translation)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(entry_id, row_number) DO UPDATE SET
                 hanzi=excluded.hanzi,
                 pinyin=excluded.pinyin,
                 translation=excluded.translation''',
            (entry_id, row["row_number"], row["hanzi"], row["pinyin"], row["translation"]),
        )


def fetch_diary_words(c, entry_id: int) -> list:
    c.execute(
        '''SELECT row_number, hanzi, pinyin, translation
           FROM diary_words
           WHERE entry_id=?
           ORDER BY row_number''',
        (entry_id,),
    )
    rows = c.fetchall()
    by_index = {
        row[0]: {"hanzi": row[1] or '', "pinyin": row[2] or '', "translation": row[3] or ''}
        for row in rows
    }
    return [by_index.get(i, {"hanzi": '', "pinyin": '', "translation": ''}) for i in range(1, DIARY_WORD_LIMIT + 1)]


def fetch_diary_score_state(c, entry_id: int) -> dict:
    c.execute(
        '''SELECT auto_diary_points, manual_diary_points, awarded_diary_points, validation_warnings
           FROM diary_scores
           WHERE entry_id=?''',
        (entry_id,),
    )
    row = c.fetchone()
    if not row:
        return {
            "auto_diary_points": 0,
            "manual_diary_points": None,
            "awarded_diary_points": 0,
            "validation_warnings": [],
        }
    try:
        validation_warnings = json.loads(row[3] or '[]')
        if not isinstance(validation_warnings, list):
            validation_warnings = []
    except json.JSONDecodeError:
        validation_warnings = []
    return {
        "auto_diary_points": row[0] or 0,
        "manual_diary_points": row[1],
        "awarded_diary_points": row[2] or 0,
        "validation_warnings": validation_warnings,
    }


def apply_diary_points_delta(c, telegram_id: int, previous_points: int, next_points: int):
    delta = next_points - previous_points
    if delta != 0:
        c.execute(
            "UPDATE users SET points = points + ?, rep_score = rep_score + ? WHERE telegram_id=?",
            (delta, delta, telegram_id),
        )
        c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
        balance_after = c.fetchone()[0] or 0
        log_economy(c, telegram_id, 'diary_reward', delta, balance_after, None, 'diary', 'Оценка дневника')


DIARY_STAR_POINTS = {1: 15, 2: 30, 3: 50}
DIARY_STAR_BONUS_POINTS = 20


def log_economy(c, telegram_id: int, operation: str, amount: int,
                balance_after=None, reference_id=None, reference_type=None, note=None):
    now_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
    c.execute(
        '''INSERT INTO economy_log
           (telegram_id, operation, amount, balance_after, reference_id, reference_type, note, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
        (telegram_id, operation, amount, balance_after, reference_id, reference_type, note, now_str),
    )


def has_active_implant(c, telegram_id: int, implant_id: str) -> bool:
    c.execute(
        '''SELECT 1 FROM user_implants
           WHERE telegram_id=? AND implant_id=? AND durability > 0
           LIMIT 1''',
        (telegram_id, implant_id),
    )
    return bool(c.fetchone())


def has_used_implant_today(c, telegram_id: int, implant_id: str, use_key: str = "", use_date: Optional[str] = None) -> bool:
    today = use_date or datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
    c.execute(
        '''SELECT 1 FROM implant_daily_uses
           WHERE telegram_id=? AND implant_id=? AND use_date=? AND use_key=?
           LIMIT 1''',
        (telegram_id, implant_id, today, use_key),
    )
    return bool(c.fetchone())


def mark_implant_used_today(c, telegram_id: int, implant_id: str, use_key: str = "", use_date: Optional[str] = None):
    today = use_date or datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
    c.execute(
        '''INSERT OR IGNORE INTO implant_daily_uses
           (telegram_id, implant_id, use_date, use_key, used_at)
           VALUES (?, ?, ?, ?, ?)''',
        (telegram_id, implant_id, today, use_key, now_iso()),
    )


def try_block_penalty_with_terracota(c, telegram_id: int, use_key: str) -> bool:
    if not has_active_implant(c, telegram_id, "implant_terracota"):
        return False
    if has_used_implant_today(c, telegram_id, "implant_terracota", "penalty"):
        return False
    mark_implant_used_today(c, telegram_id, "implant_terracota", "penalty")
    # After blocking, activate armor — next penalty is reduced by 5★
    c.execute(
        """INSERT INTO user_status (telegram_id, terracota_armor) VALUES (?, 1)
           ON CONFLICT(telegram_id) DO UPDATE SET terracota_armor=1""",
        (telegram_id,),
    )
    c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
    balance_after = (c.fetchone() or [0])[0] or 0
    log_economy(c, telegram_id, "implant_terracota_block", 0, balance_after, None, "implant", use_key)
    return True


def consume_terracota_armor(c, telegram_id: int) -> int:
    """Returns 5 if armor was active (and consumes it), else 0."""
    c.execute("SELECT terracota_armor FROM user_status WHERE telegram_id=?", (telegram_id,))
    row = c.fetchone()
    if not row or not row[0]:
        return 0
    c.execute(
        "UPDATE user_status SET terracota_armor=0 WHERE telegram_id=?",
        (telegram_id,),
    )
    return 5


LEGENDARY_ACTION_COOLDOWNS = {
    "intercept": timedelta(hours=24),
    "impulse_reset": timedelta(days=7),
    "formatting": timedelta(hours=72),
    "veil_breach": timedelta(days=7),
}


def parse_db_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return BEIJING_TZ.localize(datetime.strptime(value, '%Y-%m-%d %H:%M:%S'))
    except (TypeError, ValueError):
        return None


def legendary_cooldown_until(c, actor_id: int, action_code: str) -> Optional[datetime]:
    cooldown = LEGENDARY_ACTION_COOLDOWNS.get(action_code)
    if not cooldown:
        return None
    c.execute(
        '''SELECT created_at FROM legendary_implant_actions
           WHERE actor_telegram_id=? AND action_code=?
           ORDER BY created_at DESC LIMIT 1''',
        (actor_id, action_code),
    )
    row = c.fetchone()
    last_used = parse_db_datetime(row[0]) if row else None
    return (last_used + cooldown) if last_used else None


def ensure_legendary_action_ready(c, actor_id: int, implant_id: str, action_code: str):
    if not has_active_implant(c, actor_id, implant_id):
        raise HTTPException(status_code=403, detail="Required legendary implant not found")
    cooldown_until = legendary_cooldown_until(c, actor_id, action_code)
    now = datetime.now(BEIJING_TZ)
    if cooldown_until and cooldown_until > now:
        raise HTTPException(
            status_code=429,
            detail=f"Cooldown until {cooldown_until.strftime('%Y-%m-%d %H:%M:%S')}",
        )


def find_action_target(c, actor_id: int, target_id: Optional[int], target_name: Optional[str]):
    if target_id:
        c.execute("SELECT telegram_id, full_name, COALESCE(points, 0) FROM users WHERE telegram_id=?", (target_id,))
    else:
        query = str(target_name or '').strip()
        if not query:
            raise HTTPException(status_code=400, detail="Target required")
        c.execute(
            '''SELECT telegram_id, full_name, COALESCE(points, 0)
               FROM users
               WHERE full_name LIKE ?
               ORDER BY CASE WHEN full_name=? THEN 0 ELSE 1 END, full_name
               LIMIT 1''',
            (f"%{query}%", query),
        )
    row = c.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Target not found")
    telegram_id, full_name, points = row
    if telegram_id == actor_id:
        raise HTTPException(status_code=400, detail="Cannot target yourself")
    if telegram_id in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Admins are protected")
    return telegram_id, full_name or str(telegram_id), points or 0


def log_legendary_action(c, actor_id: int, target_id: Optional[int], secondary_id: Optional[int],
                         implant_id: str, action_code: str, points_delta: int = 0,
                         secondary_delta: int = 0, detail: str = ""):
    c.execute(
        '''INSERT INTO legendary_implant_actions
           (actor_telegram_id, target_telegram_id, secondary_telegram_id, implant_id,
            action_code, points_delta, secondary_delta, detail, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (actor_id, target_id, secondary_id, implant_id, action_code,
         points_delta, secondary_delta, detail, now_iso()),
    )


def user_netwatch_locked(c, telegram_id: int) -> bool:
    c.execute("SELECT frozen, netwatch_locked_until FROM user_status WHERE telegram_id=?", (telegram_id,))
    row = c.fetchone()
    if not row:
        return False
    frozen, locked_until = row
    until = parse_db_datetime(locked_until)
    return bool(frozen) or bool(until and until > datetime.now(BEIJING_TZ))


def compute_contract_fee(reward: int) -> int:
    return max(CONTRACT_FEE_MIN, round(reward * CONTRACT_FEE_PCT))


def detect_suspicious(c, creator_id: int, reward: int, title: str, description: str, category: str):
    reasons = []
    if len(title.strip()) < 5:
        reasons.append("короткое название")
    if len(description.strip()) < 10:
        reasons.append("короткое описание")
    if category == 'other' and reward >= 40:
        reasons.append("категория 'Другое' с высокой наградой")
    today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
    c.execute(
        '''SELECT COUNT(*) FROM contracts
           WHERE creator_telegram_id=? AND reward_stars=? AND date(created_at)=?''',
        (creator_id, CONTRACT_MAX_REWARD, today),
    )
    if (c.fetchone()[0] or 0) >= 2:
        reasons.append("повторные контракты на максимальную сумму")
    return bool(reasons), (', '.join(reasons) if reasons else None)


def get_contract_row(c, contract_id: int):
    c.execute(
        '''SELECT id, title, description, category, reward_stars, fee_stars,
                  creator_telegram_id, assignee_telegram_id, status,
                  is_suspicious, suspicious_reason,
                  created_at, accepted_at, completed_at, cancelled_at, disputed_at
           FROM contracts WHERE id=?''',
        (contract_id,),
    )
    return c.fetchone()


def compute_diary_star_points(stars: int, bonus: int) -> int:
    return DIARY_STAR_POINTS.get(int(stars or 0), 0) + (DIARY_STAR_BONUS_POINTS if bonus else 0)


def fetch_diary_scores(c, entry_id: int) -> dict:
    c.execute(
        '''SELECT lesson_score, diary_score, lesson_comment, diary_comment, rated_by, updated_at,
                  auto_diary_points, manual_diary_points, awarded_diary_points, validation_warnings
           FROM diary_scores
           WHERE entry_id=?''',
        (entry_id,),
    )
    row = c.fetchone()
    if not row:
        return {
            "lesson_score": '',
            "diary_score": '',
            "lesson_comment": '',
            "diary_comment": '',
            "rated_by": None,
            "updated_at": None,
            "auto_diary_points": 0,
            "manual_diary_points": None,
            "awarded_diary_points": 0,
            "validation_warnings": [],
        }
    try:
        validation_warnings = json.loads(row[9] or '[]')
        if not isinstance(validation_warnings, list):
            validation_warnings = []
    except json.JSONDecodeError:
        validation_warnings = []
    return {
        "lesson_score": row[0] or '',
        "diary_score": row[1] or '',
        "lesson_comment": row[2] or '',
        "diary_comment": row[3] or '',
        "rated_by": row[4],
        "updated_at": row[5],
        "auto_diary_points": row[6] or 0,
        "manual_diary_points": row[7],
        "awarded_diary_points": row[8] or 0,
        "validation_warnings": validation_warnings,
    }


def get_or_create_diary_entry(c, telegram_id: int, entry_date: str):
    c.execute(
        "SELECT id, status, locked_at FROM diary_entries WHERE telegram_id=? AND entry_date=?",
        (telegram_id, entry_date),
    )
    row = c.fetchone()
    if row:
        return row

    weekday = get_weekday_ru(entry_date)
    c.execute(
        '''INSERT INTO diary_entries (telegram_id, entry_date, weekday, status)
           VALUES (?, ?, ?, 'draft')''',
        (telegram_id, entry_date, weekday),
    )
    entry_id = c.lastrowid
    for row_number in range(1, DIARY_WORD_LIMIT + 1):
        c.execute(
            '''INSERT OR IGNORE INTO diary_words (entry_id, row_number, hanzi, pinyin, translation)
               VALUES (?, ?, '', '', '')''',
            (entry_id, row_number),
        )
    return (entry_id, 'draft', None)


def build_diary_entry_payload(c, entry_id: int) -> dict:
    c.execute(
        '''SELECT telegram_id, entry_date, weekday, weather, discussion_rating,
                  discussion_person, discussion_topic, story, status,
                  submitted_at, locked_at, created_at, updated_at
           FROM diary_entries
           WHERE id=?''',
        (entry_id,),
    )
    row = c.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Diary entry not found")

    words = fetch_diary_words(c, entry_id)
    scores = fetch_diary_scores(c, entry_id)
    validation = validate_diary_entry_content(words, row[7] or '')
    return {
        "telegram_id": row[0],
        "entry_date": row[1],
        "weekday": row[2],
        "weather": row[3] or '',
        "discussion_rating": row[4] or 0,
        "discussion_person": row[5] or '',
        "discussion_topic": row[6] or '',
        "story": row[7] or '',
        "status": row[8] or 'draft',
        "submitted_at": row[9],
        "locked_at": row[10],
        "created_at": row[11],
        "updated_at": row[12],
        "word_count": validation["filled_rows"],
        "story_hanzi_count": validation["story_hanzi"],
        "has_warnings": bool(scores["validation_warnings"]),
        "words": words,
        "scores": scores,
    }


async def get_token():
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{MARZBAN_URL}/api/admin/token",
            data={"username": MARZBAN_USER, "password": MARZBAN_PASS},
        ) as r:
            data = await r.json()
            return data.get("access_token")


async def get_user_data(marzban_username):
    token = await get_token()
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{MARZBAN_URL}/api/user/{marzban_username}",
            headers={"Authorization": f"Bearer {token}"},
        ) as r:
            return await r.json()


@app.get("/api/weather/beijing")
async def get_beijing_weather():
    if not WEATHER_API_KEY:
        raise HTTPException(status_code=503, detail="Weather API key is not configured")

    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={
                "id": "1816670",
                "appid": WEATHER_API_KEY,
                "units": "metric",
                "lang": "ru",
            },
        ) as r:
            if r.status >= 400:
                raise HTTPException(status_code=502, detail="Weather provider unavailable")
            return await r.json()


class ScheduleItem(BaseModel):
    day: str
    time: str
    subject: str
    location: str


class Announcement(BaseModel):
    text: str


class LaundryBook(BaseModel):
    date: str
    time: str
    telegram_id: int
    username: str


@app.post("/api/user/set_path")
async def set_user_theme_path(data: dict):
    telegram_id = data.get("telegram_id")
    path = str(data.get("path") or "").strip()
    if not telegram_id:
        raise HTTPException(status_code=400, detail="No telegram_id")
    if path not in ("cyberpunk", "genshin"):
        raise HTTPException(status_code=400, detail="Invalid path")

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT telegram_id FROM users WHERE telegram_id=?", (telegram_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    c.execute(
        """INSERT INTO user_status (telegram_id, theme_path) VALUES (?, ?)
           ON CONFLICT(telegram_id) DO UPDATE SET theme_path=excluded.theme_path""",
        (telegram_id, path),
    )
    conn.commit()
    conn.close()
    return {"success": True, "theme_path": path}


@app.get("/api/profile/{telegram_id}")
async def get_user_profile_dossier(telegram_id: int):
    implant_info = {
        "implant_red_dragon": {"name": "Красный Дракон 红龙", "glyph": "龍", "weight": 100},
        "implant_netwatch": {"name": "Сетевой Дозор 网络守卫", "glyph": "衛", "weight": 95},
        "implant_qilin": {"name": "Цилинь 麒麟", "glyph": "麒", "weight": 85},
        "implant_caishen": {"name": "Цайшэнь 财神", "glyph": "财", "weight": 75},
        "implant_terracota": {"name": "Терракота 兵马俑", "glyph": "兵", "weight": 70},
        "implant_guanxi": {"name": "Гуаньси 关系", "glyph": "关", "weight": 68},
        "implant_panda": {"name": "Панда 🐼", "glyph": "熊", "weight": 64},
        "implant_shaolin": {"name": "Шаолинь 少林", "glyph": "武", "weight": 62},
        "implant_linguasoft": {"name": "Linguasoft 口才", "glyph": "言", "weight": 60},
    }

    conn = get_conn()
    c = conn.cursor()
    c.execute(
        '''SELECT u.full_name, u.points, u.avatar_url, us.theme_path,
                  us.profile_showcase_kind, us.profile_showcase_code, u.rep_score
           FROM users u
           LEFT JOIN user_status us ON us.telegram_id = u.telegram_id
           WHERE u.telegram_id=?''',
        (telegram_id,),
    )
    user_row = c.fetchone()
    if not user_row:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    full_name, points, avatar_url, theme_path, manual_showcase_kind, manual_showcase_code, rep_score = user_row
    points = points or 0
    rep_score = rep_score or 0

    c.execute("SELECT COUNT(*) FROM casino_log WHERE telegram_id=? AND prize NOT LIKE 'genshin_%'", (telegram_id,))
    case_opens = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM casino_log WHERE telegram_id=? AND prize LIKE 'genshin_%'", (telegram_id,))
    prayers = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM user_cards WHERE telegram_id=? AND durability > 0", (telegram_id,))
    cards_count = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM user_implants WHERE telegram_id=? AND durability > 0", (telegram_id,))
    implants_count = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM diary_entries WHERE telegram_id=? AND status IN ('submitted', 'locked')", (telegram_id,))
    diaries_count = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(DISTINCT raid_id) FROM raid_participants WHERE telegram_id=?", (telegram_id,))
    raid_count = c.fetchone()[0] or 0
    c.execute(
        '''SELECT COUNT(DISTINCT rp.raid_id)
           FROM raid_participants rp
           JOIN raids r ON r.id = rp.raid_id
           WHERE rp.telegram_id=? AND r.result='success' ''',
        (telegram_id,),
    )
    raid_wins = c.fetchone()[0] or 0

    showcase = None
    c.execute(
        "SELECT implant_id, durability FROM user_implants WHERE telegram_id=? AND durability > 0",
        (telegram_id,),
    )
    implants = c.fetchall()
    c.execute(
        "SELECT card_id, durability FROM user_cards WHERE telegram_id=? AND durability > 0",
        (telegram_id,),
    )
    cards = c.fetchall()

    def card_showcase(card_id: str, durability: int, source: str = "auto"):
        info = CARD_INFO.get(card_id, {"name": card_id, "rarity": 4})
        return {
            "kind": "card",
            "code": card_id,
            "name": info.get("name", card_id),
            "glyph": "月" if card_id == "card_moon" else "卡",
            "detail": f"{info.get('rarity', 4)}★ · durability {durability}",
            "source": source,
        }

    def implant_showcase(implant_id: str, durability: int, source: str = "auto"):
        info = implant_info.get(implant_id, {"name": implant_id, "glyph": "芯", "weight": 1})
        return {
            "kind": "implant",
            "code": implant_id,
            "name": info.get("name", implant_id),
            "glyph": info.get("glyph", "芯"),
            "detail": f"durability {durability}",
            "source": source,
        }

    manual_kind = (manual_showcase_kind or "").strip()
    manual_code = (manual_showcase_code or "").strip()
    if manual_kind == "implant" and manual_code:
        manual_implant = next((row for row in implants if row[0] == manual_code), None)
        if manual_implant:
            showcase = implant_showcase(manual_implant[0], manual_implant[1], "manual")
    elif manual_kind == "card" and manual_code:
        manual_card = next((row for row in cards if row[0] == manual_code), None)
        if manual_card:
            showcase = card_showcase(manual_card[0], manual_card[1], "manual")

    if not showcase and theme_path == "genshin" and cards:
        card_id, durability = max(
            cards,
            key=lambda row: (CARD_INFO.get(row[0], {"rarity": 4}).get("rarity", 4), row[1] or 0),
        )
        showcase = card_showcase(card_id, durability)
    elif not showcase and implants:
        implant_id, durability = max(
            implants,
            key=lambda row: (implant_info.get(row[0], {"weight": 1}).get("weight", 1), row[1] or 0),
        )
        showcase = implant_showcase(implant_id, durability)
    elif not showcase and cards:
        card_id, durability = max(
            cards,
            key=lambda row: (CARD_INFO.get(row[0], {"rarity": 4}).get("rarity", 4), row[1] or 0),
        )
        showcase = card_showcase(card_id, durability)

    admin_placeholders = ','.join('?' * len(ADMIN_IDS))
    leaderboard_rank = None
    if telegram_id not in ADMIN_IDS:
        c.execute(
            f'''SELECT COUNT(*) + 1
                FROM users
                WHERE telegram_id IS NOT NULL
                  AND telegram_id NOT IN ({admin_placeholders})
                  AND points > ?''',
            ADMIN_IDS + [points],
        )
        leaderboard_rank = c.fetchone()[0]
    conn.close()

    reputation_score = (
        min(points, 1000)
        + diaries_count * 35
        + implants_count * 45
        + cards_count * 35
        + raid_count * 25
        + raid_wins * 45
        + case_opens * 4
        + prayers * 4
    )
    if reputation_score >= 1650:
        rank = "SS"
    elif reputation_score >= 1150:
        rank = "S"
    elif reputation_score >= 760:
        rank = "A"
    elif reputation_score >= 420:
        rank = "B"
    elif reputation_score >= 180:
        rank = "C"
    else:
        rank = "D"
    sync_rate = min(99, max(1, round((reputation_score / 1650) * 100)))

    if prayers >= 20:
        title = "祈愿者 / Молитвенник"
    elif case_opens >= 20:
        title = "开箱狂人 / Кейсовый маньяк"
    elif diaries_count >= 7:
        title = "日记官 / Дневниковый офицер"
    elif any(row[0] == "implant_red_dragon" for row in implants):
        title = "红龙载体 / Носитель Красного Дракона"
    elif raid_wins > 0:
        title = "黑墙幸存者 / Выживший у Заслона"
    else:
        title = "协议执行者 / Исполнитель протокола"

    path_label = "网络守卫" if theme_path == "cyberpunk" else "祈愿者" if theme_path == "genshin" else "未同步"
    if telegram_id in ARCHITECT_IDS:
        permission_label = "架构师"
    elif telegram_id in ADMIN_IDS:
        permission_label = "系统架构师"
    else:
        permission_label = "学生节点"

    admin_intro_variant = None
    if telegram_id in INTRO_CYBERPUNK_ADMIN_IDS:
        admin_intro_variant = "cyberpunk"
    elif telegram_id in INTRO_GENSHIN_ADMIN_IDS:
        admin_intro_variant = "genshin"

    return {
        "telegram_id": telegram_id,
        "full_name": full_name,
        "avatar_url": avatar_url,
        "points": points,
        "rep_score": rep_score,
        "theme_path": theme_path,
        "admin_intro_variant": admin_intro_variant,
        "path_label": path_label,
        "rank": rank,
        "sync_rate": sync_rate,
        "title": title,
        "leaderboard_rank": leaderboard_rank,
        "showcase": showcase,
        "stats": {
            "case_opens": case_opens,
            "prayers": prayers,
            "cards": cards_count,
            "implants": implants_count,
            "diaries": diaries_count,
            "raids": raid_count,
            "raid_wins": raid_wins,
        },
        "status_line": f"状态：在线 // 权限：{permission_label} // 同步率：{sync_rate}%",
    }


@app.post("/api/profile/showcase")
async def set_profile_showcase(data: dict):
    telegram_id = data.get("telegram_id")
    showcase_kind = str(data.get("kind") or "auto").strip()
    showcase_code = str(data.get("code") or "").strip()

    if not telegram_id:
        raise HTTPException(status_code=400, detail="No telegram_id")
    if showcase_kind not in ("auto", "implant", "card"):
        raise HTTPException(status_code=400, detail="Invalid showcase kind")

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT 1 FROM users WHERE telegram_id=?", (telegram_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    if showcase_kind == "auto":
        c.execute(
            '''INSERT INTO user_status (telegram_id, profile_showcase_kind, profile_showcase_code)
               VALUES (?, NULL, NULL)
               ON CONFLICT(telegram_id) DO UPDATE SET
                 profile_showcase_kind=NULL,
                 profile_showcase_code=NULL''',
            (telegram_id,),
        )
    elif showcase_kind == "implant":
        c.execute(
            "SELECT 1 FROM user_implants WHERE telegram_id=? AND implant_id=? AND durability > 0 LIMIT 1",
            (telegram_id, showcase_code),
        )
        if not c.fetchone():
            conn.close()
            raise HTTPException(status_code=404, detail="Implant not found")
        c.execute(
            '''INSERT INTO user_status (telegram_id, profile_showcase_kind, profile_showcase_code)
               VALUES (?, 'implant', ?)
               ON CONFLICT(telegram_id) DO UPDATE SET
                 profile_showcase_kind='implant',
                 profile_showcase_code=excluded.profile_showcase_code''',
            (telegram_id, showcase_code),
        )
    else:
        c.execute(
            "SELECT 1 FROM user_cards WHERE telegram_id=? AND card_id=? AND durability > 0 LIMIT 1",
            (telegram_id, showcase_code),
        )
        if not c.fetchone():
            conn.close()
            raise HTTPException(status_code=404, detail="Card not found")
        c.execute(
            '''INSERT INTO user_status (telegram_id, profile_showcase_kind, profile_showcase_code)
               VALUES (?, 'card', ?)
               ON CONFLICT(telegram_id) DO UPDATE SET
                 profile_showcase_kind='card',
                 profile_showcase_code=excluded.profile_showcase_code''',
            (telegram_id, showcase_code),
        )

    conn.commit()
    conn.close()
    return {"success": True, "kind": None if showcase_kind == "auto" else showcase_kind, "code": showcase_code or None}


def get_last_event_mvp_id(c) -> Optional[int]:
    """Return mvp_user_id of the most recently finished event, or None."""
    c.execute(
        "SELECT mvp_user_id FROM events WHERE state='FINISHED' ORDER BY ended_at DESC LIMIT 1"
    )
    row = c.fetchone()
    return row[0] if row else None


@app.get("/api/user/{telegram_id}")
async def get_user(telegram_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT full_name, avatar_url, marzban_username FROM users WHERE telegram_id=?", (telegram_id,))
    profile_row = c.fetchone()
    is_last_mvp = get_last_event_mvp_id(c) == telegram_id
    conn.close()
    if not profile_row:
        raise HTTPException(status_code=404, detail="User not found")

    full_name, avatar_url, marzban_user = profile_row
    if not marzban_user:
        return {
            "username": full_name or f"student_{telegram_id}",
            "full_name": full_name or f"student_{telegram_id}",
            "avatar_url": avatar_url,
            "status": "student_only",
            "link": None,
            "used_traffic": 0,
            "expire": None,
            "is_admin": telegram_id in ADMIN_IDS,
            "is_architect": telegram_id in ARCHITECT_IDS,
            "has_vpn": False,
            "is_last_mvp": is_last_mvp,
        }

    data = await get_user_data(marzban_user)
    links = data.get("links", [])
    return {
        "username": marzban_user,
        "full_name": full_name or marzban_user,
        "avatar_url": avatar_url,
        "status": data.get("status"),
        "link": links[0] if links else None,
        "used_traffic": data.get("used_traffic", 0),
        "expire": data.get("expire"),
        "is_admin": telegram_id in ADMIN_IDS,
        "is_architect": telegram_id in ARCHITECT_IDS,
        "has_vpn": True,
        "is_last_mvp": is_last_mvp,
    }


@app.post("/api/user/avatar")
async def update_user_avatar(data: dict):
    telegram_id = data.get("telegram_id")
    avatar_url = str(data.get("avatar_url") or "").strip()
    if not telegram_id:
        raise HTTPException(status_code=400, detail="No telegram_id")
    if avatar_url and not (
        avatar_url.startswith("data:image/")
        or avatar_url.startswith("https://")
        or avatar_url.startswith("http://")
    ):
        raise HTTPException(status_code=400, detail="Invalid avatar_url")
    if len(avatar_url) > 350000:
        raise HTTPException(status_code=400, detail="Avatar is too large")

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT telegram_id FROM users WHERE telegram_id=?", (telegram_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    c.execute(
        "UPDATE users SET avatar_url=? WHERE telegram_id=?",
        (avatar_url or None, telegram_id),
    )
    conn.commit()
    conn.close()
    return {"success": True, "avatar_url": avatar_url or None}


@app.post("/api/global-alert")
async def create_global_alert_endpoint(data: dict):
    caller_id = data.get("telegram_id")
    if caller_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    alert_type = data.get("alert_type") or "architect"
    title = data.get("title") or "ARCHITECT ONLINE"
    message = data.get("message") or "Critical override detected."

    alert_id = create_global_alert(alert_type, title, message)
    return {
        "success": True,
        "alert_id": alert_id,
    }


@app.get("/api/global-alert/current")
async def get_global_alert_current():
    return {
        "alert": get_current_global_alert(),
    }


@app.get("/api/schedule")
async def get_schedule():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, day, time, subject, location FROM schedule ORDER BY day, time")
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "day": r[1], "time": r[2], "subject": r[3], "location": r[4]} for r in rows]


@app.post("/api/schedule")
async def add_schedule(item: ScheduleItem, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO schedule (day, time, subject, location) VALUES (?,?,?,?)", (item.day, item.time, item.subject, item.location))
    conn.commit()
    conn.close()
    return {"success": True}


@app.delete("/api/schedule/{item_id}")
async def delete_schedule(item_id: int, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM schedule WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    return {"success": True}


@app.get("/api/announcements")
async def get_announcements():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, text, created_at FROM announcements ORDER BY created_at DESC LIMIT 10")
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "text": r[1], "created_at": r[2]} for r in rows]


@app.post("/api/announcements")
async def add_announcement(item: Announcement, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")
    text = item.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Announcement text is empty")

    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO announcements (text) VALUES (?)", (text,))
    announcement_id = c.lastrowid
    conn.commit()
    conn.close()

    telegram_delivery = await broadcast_announcement_to_telegram(text)
    return {"success": True, "id": announcement_id, "telegram_delivery": telegram_delivery}


@app.delete("/api/announcements/{item_id}")
async def delete_announcement(item_id: int, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM announcements WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    return {"success": True}


@app.get("/api/announcements/{item_id}/reactions")
async def get_reactions(item_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT emoji, COUNT(*) as cnt FROM announcement_reactions WHERE announcement_id=? GROUP BY emoji", (item_id,))
    rows = c.fetchall()
    conn.close()
    return [{"emoji": r[0], "count": r[1]} for r in rows]


@app.post("/api/announcements/{item_id}/react")
async def react_to_announcement(item_id: int, data: dict):
    telegram_id = data.get("telegram_id")
    emoji = data.get("emoji")
    if not telegram_id or not emoji:
        raise HTTPException(status_code=400, detail="Missing data")
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT emoji FROM announcement_reactions WHERE announcement_id=? AND telegram_id=?", (item_id, telegram_id))
    existing = c.fetchone()
    if existing and existing[0] == emoji:
        c.execute("DELETE FROM announcement_reactions WHERE announcement_id=? AND telegram_id=?", (item_id, telegram_id))
    else:
        c.execute("INSERT OR REPLACE INTO announcement_reactions (announcement_id, telegram_id, emoji) VALUES (?,?,?)", (item_id, telegram_id, emoji))
    conn.commit()
    conn.close()
    return {"success": True}


@app.get("/api/laundry")
async def get_laundry():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, date, time, telegram_id, username FROM laundry ORDER BY date, time")
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "date": r[1], "time": r[2], "telegram_id": r[3], "username": r[4]} for r in rows]


@app.post("/api/laundry")
async def book_laundry(item: LaundryBook):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM laundry WHERE date=? AND time=?", (item.date, item.time))
    if c.fetchone():
        conn.close()
        raise HTTPException(status_code=409, detail="Slot already booked")
    c.execute("SELECT id FROM laundry WHERE telegram_id=? AND date=?", (item.telegram_id, item.date))
    if c.fetchone():
        conn.close()
        raise HTTPException(status_code=409, detail="Already booked for this day")
    c.execute("INSERT INTO laundry (date, time, telegram_id, username) VALUES (?,?,?,?)", (item.date, item.time, item.telegram_id, item.username))
    conn.commit()
    conn.close()
    return {"success": True}


@app.delete("/api/laundry/{item_id}")
async def cancel_laundry(item_id: int, x_telegram_id: Optional[int] = Header(None)):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT telegram_id FROM laundry WHERE id=?", (item_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Not found")
    if row[0] != x_telegram_id and x_telegram_id not in ADMIN_IDS:
        conn.close()
        raise HTTPException(status_code=403, detail="Forbidden")
    c.execute("DELETE FROM laundry WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    return {"success": True}


@app.get("/api/points/{telegram_id}")
async def get_points(telegram_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT points, full_name, rep_score FROM users WHERE telegram_id=?", (telegram_id,))
    result = c.fetchone()
    if not result:
        conn.close()
        raise HTTPException(status_code=404, detail="Not found")
    c.execute("SELECT double_win, extra_cases, immunity, extra_raids, theme_path FROM user_status WHERE telegram_id=?", (telegram_id,))
    status = c.fetchone()
    conn.close()
    return {
        "points": result[0] or 0,
        "full_name": result[1],
        "rep_score": result[2] or 0,
        "double_win": status[0] if status else 0,
        "extra_cases": status[1] if status else 0,
        "immunity": status[2] if status else 0,
        "extra_raids": status[3] if status else 0,
        "theme_path": status[4] if status else None,
    }


@app.get("/api/admin/users")
async def admin_search_users(q: str = "", x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    query = str(q or "").strip()
    conn = get_conn()
    c = conn.cursor()
    if query:
        like = f"%{query}%"
        if query.isdigit():
            c.execute(
                '''SELECT telegram_id, full_name, marzban_username, points, avatar_url, room_number
                   FROM users
                   WHERE telegram_id IS NOT NULL
                     AND (CAST(telegram_id AS TEXT) LIKE ? OR full_name LIKE ? OR marzban_username LIKE ?)
                   ORDER BY points DESC
                   LIMIT 20''',
                (like, like, like),
            )
        else:
            c.execute(
                '''SELECT telegram_id, full_name, marzban_username, points, avatar_url, room_number
                   FROM users
                   WHERE telegram_id IS NOT NULL
                     AND (full_name LIKE ? OR marzban_username LIKE ?)
                   ORDER BY points DESC
                   LIMIT 20''',
                (like, like),
            )
    else:
        c.execute(
            '''SELECT telegram_id, full_name, marzban_username, points, avatar_url, room_number
               FROM users
               WHERE telegram_id IS NOT NULL
               ORDER BY points DESC
               LIMIT 20''',
        )
    rows = c.fetchall()
    roommate_map = {}
    room_numbers = sorted({row[5] for row in rows if row[5]})
    for room_number in room_numbers:
        c.execute(
            '''SELECT telegram_id, full_name, avatar_url
               FROM users
               WHERE room_number=? AND telegram_id IS NOT NULL
               ORDER BY full_name COLLATE NOCASE''',
            (room_number,),
        )
        roommate_map[room_number] = [
            {
                "telegram_id": roommate_row[0],
                "full_name": roommate_row[1] or str(roommate_row[0]),
                "avatar_url": roommate_row[2],
            }
            for roommate_row in c.fetchall()
        ]
    conn.close()
    return {
        "users": [
            {
                "telegram_id": row[0],
                "full_name": row[1] or "Аноним",
                "username": row[2] or "",
                "points": row[3] or 0,
                "avatar_url": row[4],
                "room_number": row[5] or "",
                "roommates": [
                    roommate for roommate in roommate_map.get(row[5], [])
                    if roommate["telegram_id"] != row[0]
                ],
                "is_admin": row[0] in ADMIN_IDS,
            }
            for row in rows
        ]
    }


@app.post("/api/admin/user/room")
async def admin_update_user_room(data: dict, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        telegram_id = int(data.get("telegram_id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid telegram_id")

    room_number = str(data.get("room_number") or "").strip()
    if len(room_number) > 40:
        raise HTTPException(status_code=400, detail="Room number is too long")

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT full_name FROM users WHERE telegram_id=?", (telegram_id,))
    target = c.fetchone()
    if not target:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    c.execute(
        "UPDATE users SET room_number=? WHERE telegram_id=?",
        (room_number or None, telegram_id),
    )
    roommates = []
    if room_number:
        c.execute(
            '''SELECT telegram_id, full_name, avatar_url
               FROM users
               WHERE room_number=?
                 AND telegram_id IS NOT NULL
                 AND telegram_id != ?
               ORDER BY full_name COLLATE NOCASE''',
            (room_number, telegram_id),
        )
        roommates = [
            {
                "telegram_id": row[0],
                "full_name": row[1] or str(row[0]),
                "avatar_url": row[2],
            }
            for row in c.fetchall()
        ]
    c.execute(
        '''INSERT INTO admin_action_logs
           (admin_id, target_id, action_type, points_delta, reason, created_at)
           VALUES (?, ?, 'room_update', 0, ?, ?)''',
        (x_admin_id, telegram_id, f"room: {room_number or 'empty'}", now_iso()),
    )
    conn.commit()
    conn.close()
    return {
        "success": True,
        "telegram_id": telegram_id,
        "full_name": target[0] or str(telegram_id),
        "room_number": room_number,
        "roommates": roommates,
    }


@app.get("/api/admin/user/{telegram_id}/dossier")
async def admin_user_dossier(telegram_id: int, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    conn = get_conn()
    c = conn.cursor()
    c.execute(
        '''SELECT u.telegram_id, u.full_name, u.marzban_username, u.points,
                  u.avatar_url, u.room_number, us.theme_path, u.rep_score
           FROM users u
           LEFT JOIN user_status us ON us.telegram_id = u.telegram_id
           WHERE u.telegram_id=?''',
        (telegram_id,),
    )
    user_row = c.fetchone()
    if not user_row:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    room_number = user_row[5] or ""
    roommates = []
    if room_number:
        c.execute(
            '''SELECT telegram_id, full_name, avatar_url
               FROM users
               WHERE room_number=?
                 AND telegram_id IS NOT NULL
                 AND telegram_id != ?
               ORDER BY full_name COLLATE NOCASE''',
            (room_number, telegram_id),
        )
        roommates = [
            {
                "telegram_id": row[0],
                "full_name": row[1] or str(row[0]),
                "avatar_url": row[2],
            }
            for row in c.fetchall()
        ]

    c.execute(
        '''SELECT check_type, check_date, status, attempts_sent, penalty_points,
                  confirmed_at, escalated_at, note
           FROM daily_checks
           WHERE telegram_id=?
           ORDER BY check_date DESC, id DESC
           LIMIT 8''',
        (telegram_id,),
    )
    presence_rows = c.fetchall()

    c.execute(
        '''SELECT COALESCE(SUM(stars), 0), COALESCE(SUM(bonus), 0), COUNT(*)
           FROM diary_stars
           WHERE telegram_id=?''',
        (telegram_id,),
    )
    diary_total = c.fetchone() or (0, 0, 0)
    c.execute(
        '''SELECT entry_date, stars, bonus, rated_at
           FROM diary_stars
           WHERE telegram_id=?
           ORDER BY entry_date DESC
           LIMIT 7''',
        (telegram_id,),
    )
    diary_rows = c.fetchall()

    c.execute(
        '''SELECT l.id, l.admin_id, au.full_name, l.action_type,
                  l.points_delta, l.reason, l.created_at
           FROM admin_action_logs l
           LEFT JOIN users au ON au.telegram_id = l.admin_id
           WHERE l.target_id=?
           ORDER BY l.id DESC
           LIMIT 10''',
        (telegram_id,),
    )
    action_rows = c.fetchall()

    c.execute(
        '''SELECT
             COALESCE(SUM(CASE WHEN points_delta > 0 THEN points_delta ELSE 0 END), 0),
             COALESCE(SUM(CASE WHEN points_delta < 0 THEN ABS(points_delta) ELSE 0 END), 0),
             COUNT(*)
           FROM admin_action_logs
           WHERE target_id=?''',
        (telegram_id,),
    )
    action_total = c.fetchone() or (0, 0, 0)

    c.execute(
        '''SELECT status, COUNT(*)
           FROM daily_checks
           WHERE telegram_id=?
           GROUP BY status''',
        (telegram_id,),
    )
    presence_counts = {row[0]: row[1] for row in c.fetchall()}

    c.execute(
        '''SELECT
             COUNT(CASE WHEN creator_telegram_id=? THEN 1 END),
             COUNT(CASE WHEN assignee_telegram_id=? AND status='completed' THEN 1 END),
             COUNT(CASE WHEN (creator_telegram_id=? OR assignee_telegram_id=?) AND status='disputed' THEN 1 END),
             COALESCE(SUM(CASE WHEN creator_telegram_id=? AND status='completed' THEN reward_stars ELSE 0 END),0),
             COALESCE(SUM(CASE WHEN assignee_telegram_id=? AND status='completed' THEN (reward_stars-fee_stars) ELSE 0 END),0)
           FROM contracts
           WHERE creator_telegram_id=? OR assignee_telegram_id=?''',
        (telegram_id, telegram_id, telegram_id, telegram_id,
         telegram_id, telegram_id, telegram_id, telegram_id),
    )
    ct = c.fetchone() or (0, 0, 0, 0, 0)

    c.execute(
        '''SELECT operation, amount, reference_type, note, created_at
           FROM economy_log
           WHERE telegram_id=?
           ORDER BY id DESC LIMIT 24''',
        (telegram_id,),
    )
    econ_rows = c.fetchall()

    conn.close()

    return {
        "user": {
            "telegram_id": user_row[0],
            "full_name": user_row[1] or str(user_row[0]),
            "username": user_row[2] or "",
            "points": user_row[3] or 0,
            "rep_score": user_row[7] or 0,
            "avatar_url": user_row[4],
            "room_number": room_number,
            "theme_path": user_row[6],
            "is_admin": user_row[0] in ADMIN_IDS,
            "roommates": roommates,
        },
        "stats": {
            "points_awarded": action_total[0] or 0,
            "points_penalized": action_total[1] or 0,
            "actions_count": action_total[2] or 0,
            "presence_confirmed": presence_counts.get("confirmed", 0),
            "presence_attention": (
                presence_counts.get("needs_attention", 0)
                + presence_counts.get("penalized", 0)
                + presence_counts.get("pending", 0)
            ),
            "diary_stars": diary_total[0] or 0,
            "diary_bonus": diary_total[1] or 0,
            "diary_days": diary_total[2] or 0,
            "contracts_created": ct[0] or 0,
            "contracts_done": ct[1] or 0,
            "contracts_disputed": ct[2] or 0,
            "contracts_spent": ct[3] or 0,
            "contracts_earned": ct[4] or 0,
        },
        "presence": [
            {
                "check_type": row[0],
                "check_date": row[1],
                "status": row[2],
                "attempts_sent": row[3] or 0,
                "penalty_points": row[4] or 0,
                "confirmed_at": row[5],
                "escalated_at": row[6],
                "note": row[7] or "",
            }
            for row in presence_rows
        ],
        "diary": [
            {
                "entry_date": row[0],
                "stars": row[1] or 0,
                "bonus": row[2] or 0,
                "rated_at": row[3],
            }
            for row in diary_rows
        ],
        "actions": [
            {
                "id": row[0],
                "admin_id": row[1],
                "admin_name": row[2] or str(row[1]),
                "action_type": row[3],
                "points_delta": row[4] or 0,
                "reason": row[5] or "",
                "created_at": row[6],
            }
            for row in action_rows
        ],
        "economy": [
            {
                "operation": row[0],
                "amount": row[1],
                "reference_type": row[2],
                "note": row[3] or "",
                "created_at": row[4],
            }
            for row in econ_rows
        ],
    }


@app.get("/api/admin/expected-students")
async def admin_expected_students(q: str = "", x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    query = str(q or "").strip()
    conn = get_conn()
    c = conn.cursor()
    if query:
        like = f"%{query}%"
        c.execute(
            '''SELECT es.id, es.full_name, es.group_label, es.room_number,
                      es.telegram_id, es.status, u.full_name, u.avatar_url
               FROM expected_students es
               LEFT JOIN users u ON u.telegram_id = es.telegram_id
               WHERE es.full_name LIKE ? OR es.group_label LIKE ? OR CAST(es.telegram_id AS TEXT) LIKE ?
               ORDER BY es.status ASC, es.full_name COLLATE NOCASE
               LIMIT 120''',
            (like, like, like),
        )
    else:
        c.execute(
            '''SELECT es.id, es.full_name, es.group_label, es.room_number,
                      es.telegram_id, es.status, u.full_name, u.avatar_url
               FROM expected_students es
               LEFT JOIN users u ON u.telegram_id = es.telegram_id
               ORDER BY es.status ASC, es.full_name COLLATE NOCASE
               LIMIT 160''',
        )
    rows = c.fetchall()
    conn.close()
    return {
        "students": [
            {
                "id": row[0],
                "full_name": row[1],
                "group_label": row[2] or "",
                "room_number": row[3] or "",
                "telegram_id": row[4],
                "status": row[5] or "pending",
                "registered_name": row[6] or "",
                "avatar_url": row[7],
            }
            for row in rows
        ]
    }


@app.post("/api/admin/points")
async def admin_adjust_points(data: dict, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    target_id = data.get("telegram_id")
    reason = str(data.get("reason") or "").strip()
    try:
        target_id = int(target_id)
        delta = int(data.get("delta"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid payload")

    if delta == 0:
        raise HTTPException(status_code=400, detail="Delta must not be zero")
    if abs(delta) > 5000:
        raise HTTPException(status_code=400, detail="Delta too large")
    if len(reason) < 3:
        raise HTTPException(status_code=400, detail="Reason required")

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT full_name, points FROM users WHERE telegram_id=?", (target_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    previous_points = row[1] or 0
    blocked_by_implant = delta < 0 and try_block_penalty_with_terracota(c, target_id, f"admin_points: {reason}")
    if not blocked_by_implant:
        if delta < 0:
            armor_reduction = consume_terracota_armor(c, target_id)
            delta = min(0, delta + armor_reduction)
        c.execute(
            "UPDATE users SET points = MAX(0, COALESCE(points, 0) + ?) WHERE telegram_id=?",
            (delta, target_id),
        )
    c.execute("SELECT points FROM users WHERE telegram_id=?", (target_id,))
    new_points = c.fetchone()[0] or 0
    actual_delta = new_points - previous_points
    c.execute(
        '''INSERT INTO admin_action_logs
           (admin_id, target_id, action_type, points_delta, reason, created_at)
           VALUES (?, ?, 'points_adjust', ?, ?, ?)''',
        (x_admin_id, target_id, actual_delta, reason, now_iso()),
    )
    log_economy(c, target_id, 'admin_points', actual_delta, new_points, x_admin_id, 'admin', reason)
    conn.commit()
    conn.close()

    return {
        "success": True,
        "telegram_id": target_id,
        "full_name": row[0] or str(target_id),
        "previous_points": previous_points,
        "new_points": new_points,
        "delta": actual_delta,
        "requested_delta": delta,
        "blocked_by_implant": "implant_terracota" if blocked_by_implant else None,
    }


@app.post("/api/admin/rep")
async def admin_adjust_rep(data: dict, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    target_id = data.get("telegram_id")
    reason = str(data.get("reason") or "").strip()
    try:
        target_id = int(target_id)
        delta = int(data.get("delta"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid payload")

    if delta == 0:
        raise HTTPException(status_code=400, detail="Delta must not be zero")
    if abs(delta) > 5000:
        raise HTTPException(status_code=400, detail="Delta too large")
    if len(reason) < 3:
        raise HTTPException(status_code=400, detail="Reason required")

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT full_name, points, rep_score FROM users WHERE telegram_id=?", (target_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    previous_rep = row[2] or 0
    c.execute(
        "UPDATE users SET rep_score = MAX(0, COALESCE(rep_score, 0) + ?) WHERE telegram_id=?",
        (delta, target_id),
    )
    c.execute("SELECT points, rep_score FROM users WHERE telegram_id=?", (target_id,))
    updated = c.fetchone() or (row[1] or 0, previous_rep)
    new_points = updated[0] or 0
    new_rep = updated[1] or 0
    actual_delta = new_rep - previous_rep
    c.execute(
        '''INSERT INTO admin_action_logs
           (admin_id, target_id, action_type, points_delta, reason, created_at)
           VALUES (?, ?, 'rep_adjust', ?, ?, ?)''',
        (x_admin_id, target_id, actual_delta, reason, now_iso()),
    )
    log_economy(c, target_id, 'admin_rep', actual_delta, new_rep, x_admin_id, 'rep', reason)
    conn.commit()
    conn.close()

    return {
        "success": True,
        "telegram_id": target_id,
        "full_name": row[0] or str(target_id),
        "points": new_points,
        "previous_rep_score": previous_rep,
        "new_rep_score": new_rep,
        "delta": actual_delta,
        "requested_delta": delta,
    }


@app.get("/api/admin/actions")
async def admin_action_log(limit: int = 30, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    safe_limit = max(1, min(int(limit or 30), 100))
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        '''SELECT l.id, l.admin_id, au.full_name, l.target_id, tu.full_name,
                  l.action_type, l.points_delta, l.reason, l.created_at
           FROM admin_action_logs l
           LEFT JOIN users au ON au.telegram_id = l.admin_id
           LEFT JOIN users tu ON tu.telegram_id = l.target_id
           ORDER BY l.id DESC
           LIMIT ?''',
        (safe_limit,),
    )
    rows = c.fetchall()
    conn.close()
    return {
        "logs": [
            {
                "id": row[0],
                "admin_id": row[1],
                "admin_name": row[2] or str(row[1]),
                "target_id": row[3],
                "target_name": row[4] or (str(row[3]) if row[3] else ""),
                "action_type": row[5],
                "points_delta": row[6] or 0,
                "reason": row[7] or "",
                "created_at": row[8],
            }
            for row in rows
        ]
    }


@app.post("/api/presence/start")
async def start_presence_check(data: dict, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    check_type = normalize_presence_check_type(data.get("check_type"))
    check_date = new_manual_presence_session() if check_type == "manual" and not data.get("check_date") else normalize_presence_date(data.get("check_date"))
    target_ids = data.get("telegram_ids")
    note = str(data.get("note") or "").strip()

    conn = get_conn()
    c = conn.cursor()
    if target_ids:
        ids = []
        for raw_id in target_ids:
            try:
                ids.append(int(raw_id))
            except (TypeError, ValueError):
                continue
        ids = [tid for tid in ids if tid not in ADMIN_IDS]
    else:
        placeholders = ','.join('?' * len(ADMIN_IDS))
        c.execute(
            f'''SELECT telegram_id
                FROM users
                WHERE telegram_id IS NOT NULL
                  AND telegram_id NOT IN ({placeholders})''',
            ADMIN_IDS,
        )
        ids = [row[0] for row in c.fetchall()]

    created = []
    for telegram_id in ids:
        created.append(ensure_presence_check(c, check_type, check_date, telegram_id, note))

    conn.commit()
    conn.close()
    return {
        "success": True,
        "check_type": check_type,
        "check_date": check_date,
        "created_count": len(created),
        "checks": created,
    }


@app.post("/api/presence/admin/dispatch")
async def dispatch_presence_check(data: dict, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    check_type = normalize_presence_check_type(data.get("check_type"))
    check_date = new_manual_presence_session() if check_type == "manual" and not data.get("check_date") else normalize_presence_date(data.get("check_date"))
    attempt_no = int(data.get("attempt_no") or 1)
    note = str(data.get("note") or f"admin dispatch attempt {attempt_no}").strip()
    target_ids = data.get("telegram_ids")

    conn = get_conn()
    c = conn.cursor()
    if target_ids:
        ids = []
        for raw_id in target_ids:
            try:
                ids.append(int(raw_id))
            except (TypeError, ValueError):
                continue
        ids = [tid for tid in ids if tid not in ADMIN_IDS]
    else:
        placeholders = ','.join('?' * len(ADMIN_IDS))
        c.execute(
            f'''SELECT telegram_id
                FROM users
                WHERE telegram_id IS NOT NULL
                  AND telegram_id NOT IN ({placeholders})''',
            ADMIN_IDS,
        )
        ids = [row[0] for row in c.fetchall()]

    eligible = []
    skipped = 0
    for telegram_id in ids:
        row = ensure_presence_check(c, check_type, check_date, telegram_id, note)
        if row and row.get("status") == "skipped":
            c.execute(
                '''UPDATE daily_checks
                   SET status='pending',
                       attempts_sent=0,
                       first_sent_at=NULL,
                       last_attempt_at=NULL,
                       note=?,
                       updated_at=?
                   WHERE check_type=? AND check_date=? AND telegram_id=?''',
                (note, now_iso(), check_type, check_date, telegram_id),
            )
            row = fetch_presence_row(c, check_type, check_date, telegram_id)
        if row and row.get("status") in ("pending", "leave_rejected"):
            eligible.append(telegram_id)
        else:
            skipped += 1
    conn.commit()
    conn.close()

    sent = []
    failed = []
    markup = get_presence_keyboard_markup(check_type, check_date)
    text = get_presence_message_text(check_type, attempt_no)
    for telegram_id in eligible:
        ok, response = await send_telegram_message(telegram_id, text, markup)
        if ok:
            sent.append(telegram_id)
            conn = get_conn()
            c = conn.cursor()
            now = now_iso()
            c.execute(
                '''UPDATE daily_checks
                   SET attempts_sent=COALESCE(attempts_sent, 0) + 1,
                       first_sent_at=COALESCE(first_sent_at, ?),
                       last_attempt_at=?,
                       updated_at=?
                   WHERE check_type=? AND check_date=? AND telegram_id=?''',
                (now, now, now, check_type, check_date, telegram_id),
            )
            conn.commit()
            conn.close()
        else:
            failed.append({"telegram_id": telegram_id, "error": response})

    return {
        "success": True,
        "check_type": check_type,
        "check_date": check_date,
        "attempt_no": attempt_no,
        "eligible_count": len(eligible),
        "sent_count": len(sent),
        "skipped_count": skipped,
        "failed_count": len(failed),
        "sent": sent,
        "failed": failed,
    }


@app.get("/api/presence/status")
async def get_presence_status(check_type: str, telegram_id: int, check_date: Optional[str] = None):
    check_type = normalize_presence_check_type(check_type)
    check_date = normalize_presence_date(check_date)
    conn = get_conn()
    c = conn.cursor()
    row = fetch_presence_row(c, check_type, check_date, telegram_id)
    conn.close()
    return {
        "check_type": check_type,
        "check_date": check_date,
        "telegram_id": telegram_id,
        "check": row,
    }


@app.post("/api/presence/confirm")
async def confirm_presence(data: dict):
    try:
        telegram_id = int(data.get("telegram_id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid telegram_id")

    check_type = normalize_presence_check_type(data.get("check_type"))
    check_date = normalize_presence_date(data.get("check_date"))
    action = str(data.get("action") or "confirm").strip().lower()
    note = str(data.get("note") or "").strip()

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT telegram_id FROM users WHERE telegram_id=?", (telegram_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    previous_row = fetch_presence_row(c, check_type, check_date, telegram_id)
    if action == "confirm":
        row = apply_presence_status(c, check_type, check_date, telegram_id, "confirmed", note)
        shaolin_reward = (
            check_type in {"morning", "evening"}
            and (not previous_row or previous_row["status"] not in PRESENCE_SAFE_STATUSES)
            and has_active_implant(c, telegram_id, "implant_shaolin")
        )
        if shaolin_reward:
            use_key = f"{check_type}:{check_date}"
            if not has_used_implant_today(c, telegram_id, "implant_shaolin", use_key):
                mark_implant_used_today(c, telegram_id, "implant_shaolin", use_key)
                c.execute("UPDATE users SET points = points + 20 WHERE telegram_id=?", (telegram_id,))
                c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
                balance_after = c.fetchone()[0] or 0
                log_economy(
                    c, telegram_id, "implant_shaolin_bonus", 20, balance_after,
                    None, "implant", f"{check_type} {check_date}",
                )
        # Perfect day bonus: +10★ when evening confirmed and morning was already confirmed
        if (
            check_type == "evening"
            and has_active_implant(c, telegram_id, "implant_shaolin")
            and not has_used_implant_today(c, telegram_id, "implant_shaolin", f"perfect_day:{check_date}")
        ):
            c.execute(
                """SELECT 1 FROM daily_checks
                   WHERE telegram_id=? AND check_date=? AND check_type='morning'
                     AND status IN ('confirmed','free_time')""",
                (telegram_id, check_date),
            )
            if c.fetchone():
                mark_implant_used_today(c, telegram_id, "implant_shaolin", f"perfect_day:{check_date}")
                c.execute("UPDATE users SET points = points + 10 WHERE telegram_id=?", (telegram_id,))
                c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
                balance_after = c.fetchone()[0] or 0
                log_economy(
                    c, telegram_id, "implant_shaolin_perfect_day", 10, balance_after,
                    None, "implant", check_date,
                )
        # Scan attempt award: +1 per new morning/evening confirmation (cap 7)
        is_new_confirm = not previous_row or previous_row["status"] not in PRESENCE_SAFE_STATUSES
        if check_type in {"morning", "evening"} and is_new_confirm:
            c.execute("""INSERT INTO user_status (telegram_id, scan_attempts) VALUES (?,1)
                         ON CONFLICT(telegram_id) DO UPDATE SET scan_attempts=MIN(7, scan_attempts+1)""",
                      (telegram_id,))
    elif action == "request_leave":
        row = apply_presence_status(c, check_type, check_date, telegram_id, "leave_requested", note)
    elif action == "free_time":
        purchase_id = has_active_free_time(c, telegram_id)
        if not purchase_id:
            conn.close()
            raise HTTPException(status_code=400, detail="No active free time")
        row = apply_presence_status(
            c,
            check_type,
            check_date,
            telegram_id,
            "free_time",
            note or f"casino_walk purchase #{purchase_id}",
        )
    else:
        conn.close()
        raise HTTPException(status_code=400, detail="Invalid action")

    conn.commit()
    conn.close()
    return {"success": True, "check": row}


@app.post("/api/presence/attempt")
async def mark_presence_attempt(data: dict, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        telegram_id = int(data.get("telegram_id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid telegram_id")

    check_type = normalize_presence_check_type(data.get("check_type"))
    check_date = normalize_presence_date(data.get("check_date"))
    conn = get_conn()
    c = conn.cursor()
    ensure_presence_check(c, check_type, check_date, telegram_id)
    now = now_iso()
    c.execute(
        '''UPDATE daily_checks
           SET attempts_sent=attempts_sent+1,
               first_sent_at=COALESCE(first_sent_at, ?),
               last_attempt_at=?,
               updated_at=?
           WHERE check_type=? AND check_date=? AND telegram_id=?''',
        (now, now, now, check_type, check_date, telegram_id),
    )
    row = fetch_presence_row(c, check_type, check_date, telegram_id)
    conn.commit()
    conn.close()
    return {
        "success": True,
        "needs_admin_alert": row["attempts_sent"] >= PRESENCE_ATTEMPT_LIMIT and row["status"] not in PRESENCE_SAFE_STATUSES,
        "check": row,
    }


@app.post("/api/presence/admin/approve")
async def approve_presence_leave(data: dict, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        telegram_id = int(data.get("telegram_id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid telegram_id")

    check_type = normalize_presence_check_type(data.get("check_type"))
    check_date = normalize_presence_date(data.get("check_date"))
    reason = str(data.get("reason") or "admin_approved").strip()
    starts_at = data.get("starts_at")
    ends_at = data.get("ends_at")

    conn = get_conn()
    c = conn.cursor()
    row = apply_presence_status(c, check_type, check_date, telegram_id, "admin_approved", reason)
    c.execute(
        '''INSERT INTO daily_check_exemptions
           (telegram_id, check_type, check_date, reason_text, starts_at, ends_at, created_by, created_at, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')''',
        (telegram_id, check_type, check_date, reason, starts_at, ends_at, x_admin_id, now_iso()),
    )
    c.execute(
        '''INSERT INTO admin_action_logs
           (admin_id, target_id, action_type, points_delta, reason, created_at)
           VALUES (?, ?, 'presence_approve', 0, ?, ?)''',
        (x_admin_id, telegram_id, f"{check_type} {check_date}: {reason}", now_iso()),
    )
    conn.commit()
    conn.close()
    return {"success": True, "check": row}


@app.post("/api/presence/admin/reject")
async def reject_presence_leave(data: dict, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        telegram_id = int(data.get("telegram_id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid telegram_id")

    check_type = normalize_presence_check_type(data.get("check_type"))
    check_date = normalize_presence_date(data.get("check_date"))
    reason = str(data.get("reason") or "leave rejected").strip()
    conn = get_conn()
    c = conn.cursor()
    row = apply_presence_status(c, check_type, check_date, telegram_id, "leave_rejected", reason)
    c.execute(
        '''INSERT INTO admin_action_logs
           (admin_id, target_id, action_type, points_delta, reason, created_at)
           VALUES (?, ?, 'presence_reject', 0, ?, ?)''',
        (x_admin_id, telegram_id, f"{check_type} {check_date}: {reason}", now_iso()),
    )
    conn.commit()
    conn.close()
    return {"success": True, "check": row}


@app.post("/api/presence/admin/escalate")
async def escalate_presence_check(data: dict, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    check_type = normalize_presence_check_type(data.get("check_type"))
    check_date = normalize_presence_date(data.get("check_date"))
    conn = get_conn()
    c = conn.cursor()
    now = now_iso()
    c.execute(
        '''UPDATE daily_checks
           SET status='needs_attention',
               escalated_at=COALESCE(escalated_at, ?),
               updated_at=?
           WHERE check_type=?
             AND check_date=?
             AND status IN ('pending', 'leave_requested', 'leave_rejected')
             AND attempts_sent >= ?''',
        (now, now, check_type, check_date, PRESENCE_ATTEMPT_LIMIT),
    )
    changed = c.rowcount
    conn.commit()
    c.execute(
        '''SELECT dc.id, dc.check_type, dc.check_date, dc.telegram_id, u.full_name,
                  dc.status, dc.attempts_sent, dc.first_sent_at, dc.last_attempt_at,
                  dc.confirmed_at, dc.escalated_at, dc.penalized_at,
                  dc.penalty_points, dc.note, u.points
           FROM daily_checks dc
           LEFT JOIN users u ON u.telegram_id = dc.telegram_id
           WHERE dc.check_type=? AND dc.check_date=? AND dc.status='needs_attention'
           ORDER BY u.full_name COLLATE NOCASE''',
        (check_type, check_date),
    )
    rows = [serialize_presence_row(row) for row in c.fetchall()]
    conn.close()
    return {"success": True, "changed": changed, "needs_attention": rows}


@app.post("/api/presence/admin/cancel")
async def cancel_presence_check(data: dict, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    check_type = normalize_presence_check_type(data.get("check_type"))
    reason = str(data.get("reason") or "manual cancel").strip()
    now = now_iso()

    conn = get_conn()
    c = conn.cursor()
    check_date = str(data.get("check_date") or "").strip()
    if not check_date and check_type == "manual":
        check_date = latest_manual_presence_session(c) or normalize_presence_date()
    else:
        check_date = normalize_presence_date(check_date)
    c.execute(
        '''UPDATE daily_checks
           SET status='skipped',
               note=?,
               updated_at=?
           WHERE check_type=?
             AND check_date=?
             AND status IN ('pending', 'leave_requested', 'leave_rejected', 'needs_attention')''',
        (reason, now, check_type, check_date),
    )
    cancelled = c.rowcount
    c.execute(
        '''INSERT INTO admin_action_logs
           (admin_id, target_id, action_type, points_delta, reason, created_at)
           VALUES (?, NULL, 'presence_cancel', 0, ?, ?)''',
        (x_admin_id, f"{check_type} {check_date}: {reason}", now),
    )
    conn.commit()
    conn.close()
    return {"success": True, "cancelled": cancelled, "check_type": check_type, "check_date": check_date}


@app.post("/api/presence/admin/penalize")
async def penalize_presence_check(data: dict, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    check_type = normalize_presence_check_type(data.get("check_type"))
    check_date = normalize_presence_date(data.get("check_date"))
    penalty = int(data.get("penalty_points") or PRESENCE_PENALTY_POINTS)
    if penalty <= 0 or penalty > 500:
        raise HTTPException(status_code=400, detail="Invalid penalty")

    conn = get_conn()
    c = conn.cursor()
    c.execute(
        '''SELECT dc.telegram_id, u.full_name, COALESCE(u.points, 0), COALESCE(u.rep_score, 0)
           FROM daily_checks dc
           JOIN users u ON u.telegram_id = dc.telegram_id
           WHERE dc.check_type=?
             AND dc.check_date=?
             AND dc.status='needs_attention'
             AND dc.telegram_id NOT IN ({})'''.format(','.join('?' * len(ADMIN_IDS))),
        [check_type, check_date] + ADMIN_IDS,
    )
    targets = c.fetchall()
    penalized = []
    now = now_iso()
    for telegram_id, full_name, previous_points, previous_rep in targets:
        if (
            try_block_penalty_with_terracota(c, telegram_id, f"presence: {check_type} {check_date}")
        ):
            c.execute(
                '''UPDATE daily_checks
                   SET status='penalized',
                       penalized_at=?,
                       penalty_points=0,
                       note=TRIM(COALESCE(note, '') || ' // terracota blocked penalty'),
                       updated_at=?
                   WHERE check_type=? AND check_date=? AND telegram_id=?''',
                (now, now, check_type, check_date, telegram_id),
            )
            penalized.append({
                "telegram_id": telegram_id,
                "full_name": full_name or str(telegram_id),
                "previous_points": previous_points or 0,
                "new_points": previous_points or 0,
                "new_rep_score": previous_rep or 0,
                "delta": 0,
                "rep_delta": 0,
                "blocked_by_implant": "implant_terracota",
            })
            continue
        effective_penalty = max(0, penalty - consume_terracota_armor(c, telegram_id))
        c.execute(
            """UPDATE users
               SET points = MAX(0, COALESCE(points, 0) - ?),
                   rep_score = MAX(0, COALESCE(rep_score, 0) - ?)
               WHERE telegram_id=?""",
            (effective_penalty, effective_penalty, telegram_id),
        )
        c.execute("SELECT points, rep_score FROM users WHERE telegram_id=?", (telegram_id,))
        updated_user = c.fetchone() or (0, 0)
        new_points = updated_user[0] or 0
        new_rep = updated_user[1] or 0
        actual_delta = new_points - (previous_points or 0)
        c.execute(
            '''UPDATE daily_checks
               SET status='penalized',
                   penalized_at=?,
                   penalty_points=?,
                   updated_at=?
               WHERE check_type=? AND check_date=? AND telegram_id=?''',
            (now, abs(actual_delta), now, check_type, check_date, telegram_id),
        )
        c.execute(
            '''INSERT INTO admin_action_logs
               (admin_id, target_id, action_type, points_delta, reason, created_at)
               VALUES (?, ?, 'presence_penalty', ?, ?, ?)''',
            (x_admin_id, telegram_id, actual_delta, f"{check_type} {check_date}", now),
        )
        actual_rep_delta = new_rep - previous_rep
        log_economy(c, telegram_id, 'presence_penalty', actual_delta, new_points, None, 'presence', f"{check_type} {check_date}")
        log_economy(c, telegram_id, 'presence_rep_penalty', actual_rep_delta, new_rep, None, 'rep', f"{check_type} {check_date}")
        penalized.append({
            "telegram_id": telegram_id,
            "full_name": full_name or str(telegram_id),
            "previous_points": previous_points or 0,
            "new_points": new_points,
            "new_rep_score": new_rep,
            "delta": actual_delta,
            "rep_delta": actual_rep_delta,
        })
    conn.commit()
    conn.close()
    return {"success": True, "penalized": penalized}


@app.get("/api/presence/admin/overview")
async def presence_admin_overview(check_type: str, check_date: Optional[str] = None, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    check_type = normalize_presence_check_type(check_type)
    conn = get_conn()
    c = conn.cursor()
    if not check_date and check_type == "manual":
        check_date = latest_manual_presence_session(c) or normalize_presence_date()
    else:
        check_date = normalize_presence_date(check_date)
    c.execute(
        '''SELECT dc.id, dc.check_type, dc.check_date, dc.telegram_id, u.full_name,
                  dc.status, dc.attempts_sent, dc.first_sent_at, dc.last_attempt_at,
                  dc.confirmed_at, dc.escalated_at, dc.penalized_at,
                  dc.penalty_points, dc.note, u.points
           FROM daily_checks dc
           LEFT JOIN users u ON u.telegram_id = dc.telegram_id
           WHERE dc.check_type=? AND dc.check_date=?
           ORDER BY
             CASE dc.status
               WHEN 'needs_attention' THEN 1
               WHEN 'leave_requested' THEN 2
               WHEN 'leave_rejected' THEN 3
               WHEN 'pending' THEN 4
               WHEN 'penalized' THEN 5
               ELSE 9
             END,
             u.full_name COLLATE NOCASE''',
        (check_type, check_date),
    )
    checks = [serialize_presence_row(row) for row in c.fetchall()]
    counts = {status: 0 for status in PRESENCE_STATUSES}
    for item in checks:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    conn.close()
    return {
        "check_type": check_type,
        "check_date": check_date,
        "counts": counts,
        "checks": checks,
    }


@app.get("/api/diary/admin/overview")
async def diary_admin_overview(entry_date: Optional[str] = None, x_admin_id: Optional[int] = Header(None)):
    if not is_diary_staff(x_admin_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    target_date = entry_date or datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        '''SELECT u.telegram_id, u.full_name, de.id, de.status, de.submitted_at, de.locked_at,
                  COALESCE(ds.lesson_score, ''), COALESCE(ds.diary_score, ''),
                  COALESCE(ds.awarded_diary_points, 0), COALESCE(ds.auto_diary_points, 0),
                  ds.manual_diary_points, COALESCE(ds.validation_warnings, '[]')
           FROM users u
           LEFT JOIN diary_entries de
             ON de.telegram_id = u.telegram_id AND de.entry_date = ?
           LEFT JOIN diary_scores ds
             ON ds.entry_id = de.id
           WHERE u.telegram_id IS NOT NULL
           ORDER BY u.full_name COLLATE NOCASE''',
        (target_date,),
    )
    rows = c.fetchall()
    result = []
    for telegram_id, full_name, entry_id, status, submitted_at, locked_at, lesson_score, diary_score, awarded_diary_points, auto_diary_points, manual_diary_points, warnings_json in rows:
        words_filled = 0
        warning_count = 0
        if entry_id:
            c.execute(
                '''SELECT COUNT(*)
                   FROM diary_words
                   WHERE entry_id=?
                     AND TRIM(COALESCE(hanzi, '')) != ''
                     AND TRIM(COALESCE(pinyin, '')) != ''
                     AND TRIM(COALESCE(translation, '')) != '' ''',
                (entry_id,),
            )
            words_filled = c.fetchone()[0]
        try:
            warning_count = len(json.loads(warnings_json or '[]'))
        except json.JSONDecodeError:
            warning_count = 0
        result.append({
            "telegram_id": telegram_id,
            "full_name": full_name or "Аноним",
            "entry_date": target_date,
            "has_entry": bool(entry_id),
            "status": status or "missing",
            "submitted_at": submitted_at,
            "locked_at": locked_at,
            "lesson_score": lesson_score,
            "diary_score": diary_score,
            "words_filled": words_filled,
            "word_count": words_filled,
            "awarded_diary_points": awarded_diary_points,
            "auto_diary_points": auto_diary_points,
            "manual_diary_points": manual_diary_points,
            "warning_count": warning_count,
        })
    conn.close()
    return {"entry_date": target_date, "entries": result}


@app.get("/api/diary/stars/overview")
async def get_diary_stars_overview(entry_date: str, x_telegram_id: Optional[int] = Header(None), x_admin_id: Optional[int] = Header(None)):
    viewer_id = x_admin_id if is_diary_staff(x_admin_id) else x_telegram_id
    if not entry_date:
        raise HTTPException(status_code=400, detail="Missing entry_date")

    placeholders = ','.join('?' * len(ADMIN_IDS))
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        f'''SELECT u.telegram_id, u.full_name,
                  COALESCE(ds.stars, 0), COALESCE(ds.bonus, 0),
                  ds.rated_by, ds.rated_at
           FROM users u
           LEFT JOIN diary_stars ds
             ON ds.telegram_id = u.telegram_id AND ds.entry_date = ?
           WHERE u.telegram_id IS NOT NULL
             AND u.telegram_id NOT IN ({placeholders})
           ORDER BY u.full_name COLLATE NOCASE''',
        [entry_date] + ADMIN_IDS,
    )
    rows = c.fetchall()
    conn.close()

    entries = []
    for telegram_id, full_name, stars, bonus, rated_by, rated_at in rows:
        if viewer_id not in ADMIN_IDS and viewer_id != telegram_id:
            continue
        entries.append({
            "telegram_id": telegram_id,
            "full_name": full_name or "Аноним",
            "stars": stars or 0,
            "bonus": bool(bonus),
            "rated_by": rated_by,
            "rated_at": rated_at,
            "points": compute_diary_star_points(stars or 0, bonus or 0),
        })
    return {"entry_date": entry_date, "entries": entries}


@app.post("/api/diary/stars/rate")
async def rate_diary_stars(data: dict, x_admin_id: Optional[int] = Header(None)):
    if not is_diary_staff(x_admin_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    telegram_id = data.get("telegram_id")
    entry_date = data.get("entry_date")
    if not telegram_id or not entry_date:
        raise HTTPException(status_code=400, detail="Missing data")

    incoming_stars = data.get("stars")
    incoming_bonus = bool(data.get("bonus", False))
    if incoming_stars is not None:
        try:
            incoming_stars = int(incoming_stars)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid stars")
        if incoming_stars not in (0, 1, 2, 3):
            raise HTTPException(status_code=400, detail="Invalid stars")

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT 1 FROM users WHERE telegram_id=?", (telegram_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    c.execute("SELECT stars, bonus FROM diary_stars WHERE telegram_id=? AND entry_date=?", (telegram_id, entry_date))
    previous = c.fetchone()
    previous_stars = previous[0] if previous else 0
    previous_bonus = previous[1] if previous else 0

    next_stars = previous_stars if incoming_stars is None else incoming_stars
    next_bonus = 1 if incoming_bonus else previous_bonus
    previous_points = compute_diary_star_points(previous_stars, previous_bonus)
    next_points = compute_diary_star_points(next_stars, next_bonus)

    now_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
    c.execute(
        '''INSERT INTO diary_stars (telegram_id, entry_date, stars, bonus, rated_by, rated_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(telegram_id, entry_date) DO UPDATE SET
             stars=excluded.stars,
             bonus=excluded.bonus,
             rated_by=excluded.rated_by,
             rated_at=excluded.rated_at''',
        (telegram_id, entry_date, next_stars, next_bonus, x_admin_id, now_str),
    )
    apply_diary_points_delta(c, telegram_id, previous_points, next_points)
    linguasoft_bonus = 0
    if (
        next_stars == 3
        and previous_stars < 3
        and has_active_implant(c, telegram_id, "implant_linguasoft")
        and not has_used_implant_today(c, telegram_id, "implant_linguasoft", "diary_top_score", entry_date)
    ):
        mark_implant_used_today(c, telegram_id, "implant_linguasoft", "diary_top_score", entry_date)
        c.execute("UPDATE users SET points = points + 30 WHERE telegram_id=?", (telegram_id,))
        c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
        balance_after = c.fetchone()[0] or 0
        log_economy(c, telegram_id, "implant_linguasoft_bonus", 30, balance_after, None, "implant", entry_date)
        linguasoft_bonus = 30
    # Streak bonus: +20★ for 3 consecutive 3★ diary entries
    if (
        next_stars == 3
        and has_active_implant(c, telegram_id, "implant_linguasoft")
        and not has_used_implant_today(c, telegram_id, "implant_linguasoft", f"streak3:{entry_date}")
    ):
        c.execute(
            """SELECT COUNT(*) FROM diary_stars
               WHERE telegram_id=? AND stars=3 AND entry_date < ?
               ORDER BY entry_date DESC
               LIMIT 2""",
            (telegram_id, entry_date),
        )
        # count the two most recent entries before this one
        c.execute(
            """SELECT stars FROM diary_stars
               WHERE telegram_id=? AND entry_date < ?
               ORDER BY entry_date DESC
               LIMIT 2""",
            (telegram_id, entry_date),
        )
        prev_two = [r[0] for r in c.fetchall()]
        if len(prev_two) == 2 and all(s == 3 for s in prev_two):
            mark_implant_used_today(c, telegram_id, "implant_linguasoft", f"streak3:{entry_date}")
            c.execute("UPDATE users SET points = points + 20 WHERE telegram_id=?", (telegram_id,))
            c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
            balance_after = c.fetchone()[0] or 0
            log_economy(c, telegram_id, "implant_linguasoft_streak", 20, balance_after, None, "implant", entry_date)
            linguasoft_bonus += 20
    # Scan attempt award: +1 when diary reaches 3★ for the first time
    if next_stars == 3 and previous_stars < 3:
        c.execute("""INSERT INTO user_status (telegram_id, scan_attempts) VALUES (?,1)
                     ON CONFLICT(telegram_id) DO UPDATE SET scan_attempts=MIN(7, scan_attempts+1)""",
                  (telegram_id,))
    conn.commit()
    conn.close()
    return {
        "success": True,
        "telegram_id": telegram_id,
        "entry_date": entry_date,
        "stars": next_stars,
        "bonus": bool(next_bonus),
        "points_awarded": next_points,
        "points_delta": next_points - previous_points,
        "implant_bonus": linguasoft_bonus,
    }


@app.get("/api/diary/stars/leaderboard")
async def get_diary_stars_leaderboard(x_telegram_id: Optional[int] = Header(None), x_admin_id: Optional[int] = Header(None)):
    placeholders = ','.join('?' * len(ADMIN_IDS))
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        f'''SELECT u.telegram_id, u.full_name, u.avatar_url, us.theme_path,
                  COALESCE(SUM(ds.stars), 0) as total_stars,
                  COALESCE(SUM(ds.bonus), 0) as total_bonus,
                  COALESCE(SUM(
                    CASE COALESCE(ds.stars, 0)
                      WHEN 1 THEN 15
                      WHEN 2 THEN 30
                      WHEN 3 THEN 50
                      ELSE 0
                    END + CASE WHEN COALESCE(ds.bonus, 0) > 0 THEN 20 ELSE 0 END
                  ), 0) as total_points,
                  COUNT(CASE WHEN ds.stars > 0 OR ds.bonus > 0 THEN 1 END) as days_rated
           FROM users u
           LEFT JOIN user_status us ON us.telegram_id = u.telegram_id
           LEFT JOIN diary_stars ds ON ds.telegram_id = u.telegram_id
           WHERE u.telegram_id IS NOT NULL
             AND u.telegram_id NOT IN ({placeholders})
           GROUP BY u.telegram_id, u.full_name, u.avatar_url, us.theme_path
           ORDER BY total_stars DESC, days_rated DESC, total_bonus DESC, u.full_name COLLATE NOCASE''',
        ADMIN_IDS,
    )
    rows = c.fetchall()
    conn.close()
    return [
        {
            "telegram_id": row[0],
            "name": row[1] or "Аноним",
            "avatar_url": row[2],
            "theme_path": row[3],
            "total_stars": row[4] or 0,
            "total_bonus": row[5] or 0,
            "total_points": row[6] or 0,
            "days_rated": row[7] or 0,
        }
        for row in rows
    ]


@app.get("/api/diary/{telegram_id}")
async def get_diary_entries(telegram_id: int, x_telegram_id: Optional[int] = Header(None), x_admin_id: Optional[int] = Header(None)):
    viewer_id = x_admin_id if is_diary_staff(x_admin_id) else x_telegram_id
    if viewer_id not in (None, telegram_id) and not is_diary_staff(viewer_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    conn = get_conn()
    c = conn.cursor()
    c.execute(
        '''SELECT de.id, de.entry_date, de.weekday, de.weather, de.status,
                  de.submitted_at, de.locked_at, de.updated_at,
                  COALESCE(ds.lesson_score, ''), COALESCE(ds.diary_score, ''),
                  COALESCE(ds.awarded_diary_points, 0), COALESCE(ds.auto_diary_points, 0),
                  ds.manual_diary_points, COALESCE(ds.validation_warnings, '[]')
           FROM diary_entries de
           LEFT JOIN diary_scores ds ON ds.entry_id = de.id
           WHERE de.telegram_id=?
           ORDER BY de.entry_date DESC''',
        (telegram_id,),
    )
    rows = c.fetchall()
    entries = []
    for entry_id, entry_date, weekday, weather, status, submitted_at, locked_at, updated_at, lesson_score, diary_score, awarded_diary_points, auto_diary_points, manual_diary_points, warnings_json in rows:
        c.execute(
            '''SELECT COUNT(*)
               FROM diary_words
               WHERE entry_id=?
                 AND TRIM(COALESCE(hanzi, '')) != ''
                 AND TRIM(COALESCE(pinyin, '')) != ''
                 AND TRIM(COALESCE(translation, '')) != '' ''',
            (entry_id,),
        )
        words_filled = c.fetchone()[0]
        try:
            warning_count = len(json.loads(warnings_json or '[]'))
        except json.JSONDecodeError:
            warning_count = 0
        entries.append({
            "entry_date": entry_date,
            "weekday": weekday,
            "weather": weather or '',
            "status": status or 'draft',
            "submitted_at": submitted_at,
            "locked_at": locked_at,
            "updated_at": updated_at,
            "lesson_score": lesson_score,
            "diary_score": diary_score,
            "words_filled": words_filled,
            "word_count": words_filled,
            "awarded_diary_points": awarded_diary_points,
            "auto_diary_points": auto_diary_points,
            "manual_diary_points": manual_diary_points,
            "warning_count": warning_count,
        })
    conn.close()
    return {"telegram_id": telegram_id, "entries": entries}


@app.get("/api/diary/{telegram_id}/{entry_date}")
async def get_diary_entry(telegram_id: int, entry_date: str, x_telegram_id: Optional[int] = Header(None), x_admin_id: Optional[int] = Header(None)):
    viewer_id = x_admin_id if is_diary_staff(x_admin_id) else x_telegram_id
    if viewer_id not in (None, telegram_id) and not is_diary_staff(viewer_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM diary_entries WHERE telegram_id=? AND entry_date=?", (telegram_id, entry_date))
    row = c.fetchone()
    if not row:
        conn.close()
        return {
            "telegram_id": telegram_id,
            "entry_date": entry_date,
            "weekday": get_weekday_ru(entry_date),
            "weather": '',
            "discussion_rating": 0,
            "discussion_person": '',
            "discussion_topic": '',
            "story": '',
            "status": 'draft',
            "submitted_at": None,
            "locked_at": None,
            "created_at": None,
            "updated_at": None,
            "words": normalize_diary_words([]),
            "scores": {
                "lesson_score": '',
                "diary_score": '',
                "lesson_comment": '',
                "diary_comment": '',
                "rated_by": None,
                "updated_at": None,
                "auto_diary_points": 0,
                "manual_diary_points": None,
                "awarded_diary_points": 0,
                "validation_warnings": [],
            },
            "word_count": 0,
            "story_hanzi_count": 0,
            "has_warnings": False,
        }

    payload = build_diary_entry_payload(c, row[0])
    conn.close()
    return payload


@app.post("/api/diary/save")
async def save_diary_entry(data: dict, x_telegram_id: Optional[int] = Header(None), x_admin_id: Optional[int] = Header(None)):
    telegram_id = data.get("telegram_id")
    entry_date = data.get("entry_date")
    if not telegram_id or not entry_date:
        raise HTTPException(status_code=400, detail="Missing data")

    acting_user = x_admin_id if is_diary_staff(x_admin_id) else x_telegram_id
    is_staff = is_diary_staff(acting_user)
    if acting_user not in (None, telegram_id) and not is_staff:
        raise HTTPException(status_code=403, detail="Forbidden")

    conn = get_conn()
    c = conn.cursor()
    entry_id, current_status, locked_at = get_or_create_diary_entry(c, telegram_id, entry_date)
    if locked_at and not is_staff:
        conn.close()
        raise HTTPException(status_code=403, detail="Diary entry locked")

    now_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
    next_status = data.get("status") if is_staff and data.get("status") else ('draft' if current_status != 'locked' else 'locked')
    c.execute(
        '''UPDATE diary_entries
           SET weekday=?, weather=?, discussion_rating=?, discussion_person=?, discussion_topic=?,
               story=?, status=?, updated_at=?
           WHERE id=?''',
        (
            get_weekday_ru(entry_date),
            data.get("weather", ""),
            int(data.get("discussion_rating", 0) or 0),
            data.get("discussion_person", ""),
            data.get("discussion_topic", ""),
            data.get("story", ""),
            next_status,
            now_str,
            entry_id,
        ),
    )
    store_diary_words(c, entry_id, data.get("words", []))
    conn.commit()
    payload = build_diary_entry_payload(c, entry_id)
    conn.close()
    return {"success": True, "entry": payload}


@app.post("/api/diary/submit")
async def submit_diary_entry(data: dict, x_telegram_id: Optional[int] = Header(None), x_admin_id: Optional[int] = Header(None)):
    telegram_id = data.get("telegram_id")
    entry_date = data.get("entry_date")
    if not telegram_id or not entry_date:
        raise HTTPException(status_code=400, detail="Missing data")

    acting_user = x_admin_id if is_diary_staff(x_admin_id) else x_telegram_id
    if acting_user not in (None, telegram_id) and not is_diary_staff(acting_user):
        raise HTTPException(status_code=403, detail="Forbidden")

    conn = get_conn()
    c = conn.cursor()
    entry_id, _, locked_at = get_or_create_diary_entry(c, telegram_id, entry_date)
    if locked_at and not is_diary_staff(acting_user):
        conn.close()
        raise HTTPException(status_code=403, detail="Diary entry locked")

    now_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
    c.execute(
        "UPDATE diary_entries SET status='submitted', submitted_at=?, updated_at=? WHERE id=?",
        (now_str, now_str, entry_id),
    )
    conn.commit()
    payload = build_diary_entry_payload(c, entry_id)
    conn.close()
    return {"success": True, "entry": payload}


@app.post("/api/diary/score")
async def score_diary_entry(data: dict, x_admin_id: Optional[int] = Header(None)):
    if not is_diary_staff(x_admin_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    telegram_id = data.get("telegram_id")
    entry_date = data.get("entry_date")
    if not telegram_id or not entry_date:
        raise HTTPException(status_code=400, detail="Missing data")

    conn = get_conn()
    c = conn.cursor()
    entry_id, _, _ = get_or_create_diary_entry(c, telegram_id, entry_date)
    now_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
    c.execute(
        '''INSERT INTO diary_scores
           (entry_id, lesson_score, diary_score, lesson_comment, diary_comment, rated_by, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(entry_id) DO UPDATE SET
             lesson_score=excluded.lesson_score,
             diary_score=excluded.diary_score,
             lesson_comment=excluded.lesson_comment,
             diary_comment=excluded.diary_comment,
             rated_by=excluded.rated_by,
             updated_at=excluded.updated_at''',
        (
            entry_id,
            data.get("lesson_score", ""),
            data.get("diary_score", ""),
            data.get("lesson_comment", ""),
            data.get("diary_comment", ""),
            x_admin_id,
            now_str,
        ),
    )
    c.execute("UPDATE diary_entries SET status='reviewed', updated_at=? WHERE id=?", (now_str, entry_id))
    conn.commit()
    payload = build_diary_entry_payload(c, entry_id)
    conn.close()
    return {"success": True, "entry": payload}


@app.post("/api/diary/lock")
async def lock_diary_entry(data: dict, x_admin_id: Optional[int] = Header(None)):
    if not is_diary_staff(x_admin_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    telegram_id = data.get("telegram_id")
    entry_date = data.get("entry_date")
    locked = bool(data.get("locked", True))
    if not telegram_id or not entry_date:
        raise HTTPException(status_code=400, detail="Missing data")

    conn = get_conn()
    c = conn.cursor()
    entry_id, _, _ = get_or_create_diary_entry(c, telegram_id, entry_date)
    now_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
    if locked:
        c.execute(
            "UPDATE diary_entries SET status='locked', locked_at=?, updated_at=? WHERE id=?",
            (now_str, now_str, entry_id),
        )
    else:
        c.execute(
            "UPDATE diary_entries SET status='reviewed', locked_at=NULL, updated_at=? WHERE id=?",
            (now_str, entry_id),
        )
    conn.commit()
    payload = build_diary_entry_payload(c, entry_id)
    conn.close()
    return {"success": True, "entry": payload}


@app.get("/api/leaderboard")
async def get_leaderboard():
    today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
    placeholders = ','.join('?' * len(ADMIN_IDS))
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        f'''SELECT u.full_name, u.rep_score, u.telegram_id, u.avatar_url, us.theme_path,
                 CASE WHEN us.title_date=? THEN 1 ELSE 0 END as has_title,
                 (SELECT implant_id FROM user_implants
                  WHERE telegram_id=u.telegram_id
                  AND durability > 0
                  ORDER BY CASE implant_id
                    WHEN 'implant_red_dragon' THEN 1
                    WHEN 'implant_guanxi' THEN 2
                    WHEN 'implant_terracota' THEN 3
                    ELSE 4 END
                  LIMIT 1) as top_implant,
                 (SELECT card_id FROM user_cards
                  WHERE telegram_id=u.telegram_id
                  AND durability > 0
                  ORDER BY CASE card_id
                    WHEN 'card_star' THEN 1
                    WHEN 'card_zhongli' THEN 2
                    WHEN 'card_pyro' THEN 3
                    WHEN 'card_moon' THEN 4
                    ELSE 5 END
                  LIMIT 1) as top_card
                 FROM users u
                 LEFT JOIN user_status us ON u.telegram_id = us.telegram_id
                 WHERE u.telegram_id IS NOT NULL
                 AND u.telegram_id NOT IN ({placeholders})
                 ORDER BY u.rep_score DESC LIMIT 10''',
        [today] + ADMIN_IDS,
    )
    result = c.fetchall()
    conn.close()
    return [
        {
            "name": r[0] or "Аноним",
            "rep": r[1] or 0,
            "telegram_id": r[2],
            "avatar_url": r[3],
            "theme_path": r[4],
            "has_title": bool(r[5]),
            "implant": r[6],
            "card": r[7],
        }
        for r in result
    ]


@app.get("/api/achievements/{telegram_id}")
async def get_user_achievements(telegram_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT code, name, description, icon, secret FROM achievements")
    all_achievements = c.fetchall()
    c.execute("SELECT achievement_code, earned_at FROM user_achievements WHERE telegram_id=?", (telegram_id,))
    earned = {row[0]: row[1] for row in c.fetchall()}
    conn.close()
    result = []
    for code, name, description, icon, secret in all_achievements:
        is_earned = code in earned
        if secret and not is_earned:
            continue
        result.append({
            "code": code,
            "name": name,
            "description": description,
            "icon": icon,
            "secret": bool(secret),
            "earned": is_earned,
            "earned_at": earned.get(code),
        })
    return result


@app.post("/api/achievements/grant")
async def grant_achievement(data: dict, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")
    telegram_id = data.get("telegram_id")
    code = data.get("code")
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO user_achievements (telegram_id, achievement_code) VALUES (?,?)", (telegram_id, code))
        conn.commit()
        conn.close()
        return {"success": True}
    except Exception:
        conn.close()
        return {"success": False, "detail": "Already earned"}

@app.get("/api/user/scans/{telegram_id}")
async def get_user_scans(telegram_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT scan_attempts, protocol_fragments FROM user_status WHERE telegram_id=?", (telegram_id,))
    row = c.fetchone()
    conn.close()
    return {
        "scan_attempts": row[0] if row else 0,
        "protocol_fragments": row[1] if row else 0,
    }

@app.post("/api/casino/open")
async def open_case(data: dict):
    telegram_id = data.get("telegram_id")
    if not telegram_id:
        raise HTTPException(status_code=400, detail="No telegram_id")

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT 1 FROM users WHERE telegram_id=?", (telegram_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    now_beijing = datetime.now(BEIJING_TZ)
    today = now_beijing.strftime('%Y-%m-%d')

    if telegram_id not in ADMIN_IDS:
        c.execute("SELECT scan_attempts FROM user_status WHERE telegram_id=?", (telegram_id,))
        row = c.fetchone()
        attempts = row[0] if row else 0
        if attempts <= 0:
            conn.close()
            raise HTTPException(status_code=400, detail="No scan attempts remaining")

    case_type = random.choices(['gold', 'purple', 'black'], weights=[789, 210, 1], k=1)[0]
    if case_type == 'gold':
        prizes = [
            {"code": "empty",   "name": "Пустая миска риса", "points": 0,   "weight": 40, "icon": "🍚", "case_type": "gold"},
            {"code": "small",   "name": "+30 баллов",         "points": 30,  "weight": 30, "icon": "⭐", "case_type": "gold"},
            {"code": "medium",  "name": "+60 баллов",         "points": 60,  "weight": 15, "icon": "💫", "case_type": "gold"},
            {"code": "walk",    "name": "+30 мин свободы",    "points": 0,   "weight": 20, "icon": "🕐", "case_type": "gold"},
            {"code": "laundry", "name": "Вне очереди!",       "points": 0,   "weight": 12, "icon": "🧺", "case_type": "gold"},
            {"code": "skip",    "name": "Иммунитет!",         "points": 0,   "weight": 6,  "icon": "🛡", "case_type": "gold"},
            {"code": "jackpot", "name": "ДЖЕКПОТ! +250★",     "points": 250, "weight": 1,  "icon": "👑", "case_type": "gold"},
        ]
    elif case_type == 'purple':
        prizes = [
            {"code": "implant_guanxi",     "name": "Имплант Гуаньси 关系",      "points": 0, "weight": 68, "icon": "🤝", "case_type": "purple"},
            {"code": "implant_terracota",  "name": "Имплант Терракота 兵马俑",  "points": 0, "weight": 70, "icon": "🗿", "case_type": "purple"},
            {"code": "implant_panda",      "name": "Имплант Панда 🐼",          "points": 0, "weight": 64, "icon": "🐼", "case_type": "purple"},
            {"code": "implant_shaolin",    "name": "Имплант Шаолинь 少林",      "points": 0, "weight": 62, "icon": "🥋", "case_type": "purple"},
            {"code": "implant_linguasoft", "name": "Имплант Linguasoft 口才",   "points": 0, "weight": 60, "icon": "🎙", "case_type": "purple"},
            {"code": "implant_caishen",    "name": "Имплант Цайшэнь 财神",      "points": 0, "weight": 75, "icon": "💰", "case_type": "purple"},
            {"code": "implant_qilin",      "name": "Имплант Цилинь 麒麟",       "points": 0, "weight": 85, "icon": "🐉", "case_type": "purple"},
        ]
    else:
        prizes = [
            {"code": "implant_red_dragon", "name": "Протокол Красный Дракон 红龙", "points": 0, "weight": 1, "icon": "🐉", "case_type": "black"},
        ]

    prize = dict(random.choices(prizes, weights=[p["weight"] for p in prizes], k=1)[0])
    now_str = now_beijing.strftime('%Y-%m-%d %H:%M:%S')

    # Spend one scan attempt, earn one protocol fragment
    if telegram_id not in ADMIN_IDS:
        c.execute("""INSERT INTO user_status (telegram_id, scan_attempts, protocol_fragments) VALUES (?,0,1)
                     ON CONFLICT(telegram_id) DO UPDATE SET
                       scan_attempts = MAX(0, scan_attempts - 1),
                       protocol_fragments = COALESCE(protocol_fragments, 0) + 1""", (telegram_id,))
    else:
        c.execute("""INSERT INTO user_status (telegram_id, protocol_fragments) VALUES (?,1)
                     ON CONFLICT(telegram_id) DO UPDATE SET
                       protocol_fragments = COALESCE(protocol_fragments, 0) + 1""", (telegram_id,))

    if prize["code"] == "skip":
        c.execute("""INSERT INTO user_status (telegram_id, immunity) VALUES (?,1)
                     ON CONFLICT(telegram_id) DO UPDATE SET immunity=1""", (telegram_id,))
        c.execute("INSERT INTO shop_purchases (telegram_id, item_code, purchased_at, status) VALUES (?,?,?,?)", (telegram_id, 'casino_immunity', now_str, 'active'))
    elif prize["code"] == "walk":
        expires = now_beijing.strftime('%Y-%m-%d') + ' 22:00:00'
        c.execute("INSERT INTO shop_purchases (telegram_id, item_code, purchased_at, status, expires_at) VALUES (?,?,?,?,?)", (telegram_id, 'casino_walk', now_str, 'active', expires))
    elif prize["code"] == "laundry":
        c.execute("INSERT INTO shop_purchases (telegram_id, item_code, purchased_at, status) VALUES (?,?,?,?)", (telegram_id, 'casino_laundry', now_str, 'active'))
    elif prize["code"].startswith("implant_"):
        c.execute("INSERT INTO user_implants (telegram_id, implant_id, durability, obtained_at) VALUES (?,?,3,?)", (telegram_id, prize["code"], now_str))
    if prize.get("points", 0) > 0:
        c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (prize["points"], telegram_id))

    c.execute("INSERT INTO casino_log (telegram_id, date, prize, created_at) VALUES (?,?,?,?)", (telegram_id, today, prize["code"], now_str))
    c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
    new_points = c.fetchone()[0]
    c.execute("SELECT scan_attempts, protocol_fragments FROM user_status WHERE telegram_id=?", (telegram_id,))
    scan_row = c.fetchone()
    log_economy(c, telegram_id, 'case_open', 0, new_points, None, prize.get("case_type") or "case", prize.get("name") or prize.get("code"))
    conn.commit()
    conn.close()
    return {
        "prize": prize,
        "new_points": new_points,
        "scan_attempts": scan_row[0] if scan_row else 0,
        "protocol_fragments": scan_row[1] if scan_row else 0,
    }


@app.get("/api/casino/status/{telegram_id}")
async def get_casino_status(telegram_id: int):
    today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
    conn = get_conn()
    c = conn.cursor()
    is_frozen = user_netwatch_locked(c, telegram_id)
    c.execute("SELECT COUNT(*) FROM casino_log WHERE telegram_id=? AND date=?", (telegram_id, today))
    used = c.fetchone()[0]
    c.execute("SELECT extra_cases FROM user_status WHERE telegram_id=?", (telegram_id,))
    ex = c.fetchone()
    extra = ex[0] if ex else 0
    if telegram_id in ADMIN_IDS:
        daily_limit = 999
        remaining = 999
    else:
        daily_limit = 3 + extra
        remaining = max(0, daily_limit - used)
    conn.close()
    return {
        "frozen": is_frozen,
        "used_today": used,
        "daily_limit": daily_limit,
        "remaining_today": remaining,
        "extra_cases": extra,
    }


@app.get("/api/casino/history/{telegram_id}")
async def get_casino_history(telegram_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT prize, created_at FROM casino_log
                 WHERE telegram_id=?
                 ORDER BY created_at DESC LIMIT 20""", (telegram_id,))
    rows = c.fetchall()
    conn.close()
    prize_names = {
        "empty": {"name": "Пустая миска риса", "icon": "🍚"},
        "small": {"name": "+30 баллов", "icon": "⭐️"},
        "medium": {"name": "+60 баллов", "icon": "💫"},
        "walk": {"name": "+30 мин свободы", "icon": "🕐"},
        "laundry": {"name": "Вне очереди!", "icon": "🧺"},
        "skip": {"name": "Иммунитет!", "icon": "🛡"},
        "jackpot": {"name": "ДЖЕКПОТ! +250!", "icon": "👑"},
        "implant_guanxi": {"name": "Имплант Гуаньси 关系", "icon": "🤝"},
        "implant_terracota": {"name": "Имплант Терракота 兵马俑", "icon": "🗿"},
        "implant_panda": {"name": "Имплант Панда 🐼", "icon": "🐼"},
        "implant_shaolin": {"name": "Имплант Шаолинь 少林", "icon": "🥋"},
        "implant_linguasoft": {"name": "Имплант Linguasoft 口才", "icon": "🎙"},
        "implant_caishen": {"name": "Имплант Цайшэнь 财神", "icon": "💰"},
        "implant_qilin": {"name": "Имплант Цилинь 麒麟", "icon": "🐉"},
        "implant_red_dragon": {"name": "Красный Дракон 红龙", "icon": "🐉"},
    }
    result = []
    for code, created_at in rows:
        info = prize_names.get(code, {"name": code, "icon": "🎁"})
        result.append({"code": code, "name": info["name"], "icon": info["icon"], "created_at": created_at})
    return result


@app.get("/api/casino/inventory/{telegram_id}")
async def get_casino_inventory(telegram_id: int):
    now_beijing = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
    conn = get_conn()
    c = conn.cursor()
    c.execute("""UPDATE shop_purchases SET status='expired'
                 WHERE telegram_id=? AND status='active'
                 AND expires_at IS NOT NULL AND expires_at < ?""", (telegram_id, now_beijing))
    conn.commit()
    c.execute("""SELECT id, item_code, purchased_at, expires_at FROM shop_purchases
                 WHERE telegram_id=? AND status='active'
                 AND item_code IN ('casino_walk', 'casino_laundry', 'casino_immunity')
                 ORDER BY purchased_at DESC""", (telegram_id,))
    rows = c.fetchall()
    conn.close()
    item_info = {
        "casino_walk": {"name": "+30 мин свободы", "icon": "🕐", "desc": "Действует с 21:00 до 22:00"},
        "casino_laundry": {"name": "Вне очереди!", "icon": "🧺", "desc": "Первым на стирку или за водой"},
        "casino_immunity": {"name": "Иммунитет!", "icon": "🛡", "desc": "Один пропуск без штрафа"},
    }
    return [{
        "id": row[0],
        "code": row[1],
        "name": item_info.get(row[1], {"name": row[1]})["name"],
        "icon": item_info.get(row[1], {"icon": "🎁"})["icon"],
        "desc": item_info.get(row[1], {"desc": ""})["desc"],
        "purchased_at": row[2],
        "expires_at": row[3],
    } for row in rows]


@app.get("/api/casino/implants/{telegram_id}")
async def get_implants(telegram_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT id, implant_id, durability, obtained_at FROM user_implants
                 WHERE telegram_id=? AND durability > 0
                 ORDER BY obtained_at DESC""", (telegram_id,))
    rows = c.fetchall()
    conn.close()
    implant_info = {
        "implant_guanxi": {"name": "Гуаньси 关系", "icon": "🤝", "desc": "Скидка 10% в магазине"},
        "implant_terracota": {"name": "Терракота 兵马俑", "icon": "🗿", "desc": "Блок 1 штрафа в день · после блока следующий штраф −5★"},
        "implant_panda": {"name": "Панда 🐼", "icon": "🐼", "desc": "Кэшбек +10★ с покупки · продажа за 60% вместо 50%"},
        "implant_shaolin": {"name": "Шаолинь 少林", "icon": "🥋", "desc": "+20★ за перекличку вовремя · идеальный день (утро+вечер) ещё +10★"},
        "implant_linguasoft": {"name": "Linguasoft 口才", "icon": "🎙", "desc": "+30★ за 3★ в дневнике · серия из 3 дневников на 3★ ещё +20★"},
        "implant_caishen": {"name": "Цайшэнь 财神", "icon": "💰", "desc": "+15★ каждые 24 часа"},
        "implant_qilin": {"name": "Цилинь 麒麟", "icon": "🐉", "desc": "+10★ за каждого владельца Цилиня"},
        "implant_red_dragon": {"name": "Красный Дракон 红龙", "icon": "🐉", "desc": "+20% баллов · перехват · сбросить импульс"},
        "implant_netwatch": {"name": "Сетевой Дозор 网络守卫", "icon": "🔴", "desc": "Форматирование · Взлом Заслона · контроль сети"},
    }
    result = []
    for row in rows:
        info = implant_info.get(row[1], {"name": row[1], "icon": "💜", "desc": ""})
        result.append({
            "id": row[0],
            "implant_id": row[1],
            "name": info["name"],
            "icon": info["icon"],
            "desc": info["desc"],
            "durability": row[2],
            "obtained_at": row[3],
        })
    return result


@app.get("/api/implants/legendary/status/{telegram_id}")
async def get_legendary_implant_status(telegram_id: int):
    conn = get_conn()
    c = conn.cursor()
    result = {}
    for action_code, implant_id in {
        "intercept": "implant_red_dragon",
        "impulse_reset": "implant_red_dragon",
        "formatting": "implant_netwatch",
        "veil_breach": "implant_netwatch",
    }.items():
        cooldown_until = legendary_cooldown_until(c, telegram_id, action_code)
        result[action_code] = {
            "available": has_active_implant(c, telegram_id, implant_id),
            "cooldown_until": cooldown_until.strftime('%Y-%m-%d %H:%M:%S') if cooldown_until else None,
        }
    conn.close()
    return result


@app.post("/api/implants/red-dragon/intercept")
async def red_dragon_intercept(data: dict):
    actor_id = int(data.get("telegram_id") or 0)
    target_id = data.get("target_telegram_id")
    target_name = data.get("target_name")
    if not actor_id:
        raise HTTPException(status_code=400, detail="telegram_id required")
    conn = get_conn()
    c = conn.cursor()
    ensure_legendary_action_ready(c, actor_id, "implant_red_dragon", "intercept")
    target_id, target_name, target_points = find_action_target(c, actor_id, target_id, target_name)
    if target_points < 80:
        conn.close()
        raise HTTPException(status_code=400, detail="Target balance below 80")
    cutoff = (datetime.now(BEIJING_TZ) - timedelta(days=3)).strftime('%Y-%m-%d %H:%M:%S')
    c.execute(
        '''SELECT 1 FROM legendary_implant_actions
           WHERE actor_telegram_id=? AND target_telegram_id=? AND action_code='intercept'
             AND created_at>=? LIMIT 1''',
        (actor_id, target_id, cutoff),
    )
    if c.fetchone():
        conn.close()
        raise HTTPException(status_code=429, detail="Target protected for 3 days")
    c.execute("UPDATE users SET points = points - 10 WHERE telegram_id=?", (target_id,))
    c.execute("UPDATE users SET points = points + 10 WHERE telegram_id=?", (actor_id,))
    c.execute("SELECT points FROM users WHERE telegram_id=?", (target_id,))
    target_balance = c.fetchone()[0] or 0
    c.execute("SELECT points FROM users WHERE telegram_id=?", (actor_id,))
    actor_balance = c.fetchone()[0] or 0
    log_economy(c, target_id, "red_dragon_intercept_loss", -10, target_balance, actor_id, "implant", "Перехват")
    log_economy(c, actor_id, "red_dragon_intercept_gain", 10, actor_balance, target_id, "implant", "Перехват")
    log_legendary_action(c, actor_id, target_id, None, "implant_red_dragon", "intercept", 10, 0, target_name)
    conn.commit()
    conn.close()
    await send_telegram_message(target_id, "🐉 Красный Дракон активировал «Перехват».\nС вашего баланса снято 10★.")
    return {"success": True, "target": target_name, "stolen": 10, "new_points": actor_balance}


@app.post("/api/implants/red-dragon/impulse-reset")
async def red_dragon_impulse_reset(data: dict):
    actor_id = int(data.get("telegram_id") or 0)
    if not actor_id:
        raise HTTPException(status_code=400, detail="telegram_id required")
    conn = get_conn()
    c = conn.cursor()
    ensure_legendary_action_ready(c, actor_id, "implant_red_dragon", "impulse_reset")
    c.execute(
        '''SELECT id, operation, amount, note
           FROM economy_log
           WHERE telegram_id=? AND amount < 0 AND amount >= -20
             AND reference_type IN ('event', 'casino_game')
             AND NOT EXISTS (
               SELECT 1 FROM economy_log resets
               WHERE resets.operation='red_dragon_impulse_reset'
                 AND resets.reference_id=economy_log.id
             )
           ORDER BY created_at DESC LIMIT 1''',
        (actor_id,),
    )
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="No eligible game penalty")
    penalty_id, operation, amount, note = row
    refund = abs(amount)
    c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (refund, actor_id))
    c.execute("SELECT points FROM users WHERE telegram_id=?", (actor_id,))
    balance = c.fetchone()[0] or 0
    log_economy(c, actor_id, "red_dragon_impulse_reset", refund, balance, penalty_id, "implant", note or operation)
    log_legendary_action(c, actor_id, actor_id, None, "implant_red_dragon", "impulse_reset", refund, 0, note or operation)
    conn.commit()
    conn.close()
    return {"success": True, "refunded": refund, "new_points": balance}


@app.post("/api/implants/netwatch/formatting")
async def netwatch_formatting(data: dict):
    actor_id = int(data.get("telegram_id") or 0)
    target_id = data.get("target_telegram_id")
    target_name = data.get("target_name")
    if not actor_id:
        raise HTTPException(status_code=400, detail="telegram_id required")
    conn = get_conn()
    c = conn.cursor()
    ensure_legendary_action_ready(c, actor_id, "implant_netwatch", "formatting")
    target_id, target_name, target_points = find_action_target(c, actor_id, target_id, target_name)
    if target_points < 80:
        conn.close()
        raise HTTPException(status_code=400, detail="Target balance below 80")
    c.execute(
        '''SELECT telegram_id, full_name, COALESCE(points, 0)
           FROM users
           WHERE telegram_id NOT IN (?, ?)
             AND telegram_id NOT IN ({})
             AND COALESCE(points, 0) >= 80
           ORDER BY RANDOM()
           LIMIT 1'''.format(','.join('?' * len(ADMIN_IDS))),
        [actor_id, target_id] + ADMIN_IDS,
    )
    secondary = c.fetchone()
    secondary_id = secondary[0] if secondary else None
    secondary_name = secondary[1] if secondary else None
    c.execute("UPDATE users SET points = points - 15 WHERE telegram_id=?", (target_id,))
    c.execute("SELECT points FROM users WHERE telegram_id=?", (target_id,))
    target_balance = c.fetchone()[0] or 0
    log_economy(c, target_id, "netwatch_formatting", -15, target_balance, actor_id, "implant", "Форматирование")
    secondary_delta = 0
    if secondary_id:
        c.execute("UPDATE users SET points = points - 5 WHERE telegram_id=?", (secondary_id,))
        c.execute("SELECT points FROM users WHERE telegram_id=?", (secondary_id,))
        secondary_balance = c.fetchone()[0] or 0
        log_economy(c, secondary_id, "netwatch_formatting_collateral", -5, secondary_balance, actor_id, "implant", "Побочный урон")
        secondary_delta = -5
    log_legendary_action(c, actor_id, target_id, secondary_id, "implant_netwatch", "formatting", -15, secondary_delta, target_name)
    conn.commit()
    conn.close()
    await send_telegram_message(target_id, "🔴 NetWatch выполнил «Форматирование».\nС вашего баланса снято 15★.")
    if secondary_id:
        await send_telegram_message(secondary_id, "🔴 Побочный импульс NetWatch.\nС вашего баланса снято 5★.")
    return {
        "success": True,
        "target": target_name,
        "damage": 15,
        "secondary_target": secondary_name,
        "secondary_damage": 5 if secondary_id else 0,
    }


@app.post("/api/implants/netwatch/veil-breach")
async def netwatch_veil_breach(data: dict):
    actor_id = int(data.get("telegram_id") or 0)
    target_id = data.get("target_telegram_id")
    target_name = data.get("target_name")
    if not actor_id:
        raise HTTPException(status_code=400, detail="telegram_id required")
    conn = get_conn()
    c = conn.cursor()
    ensure_legendary_action_ready(c, actor_id, "implant_netwatch", "veil_breach")
    target_id, target_name, _ = find_action_target(c, actor_id, target_id, target_name)
    cutoff = (datetime.now(BEIJING_TZ) - timedelta(days=14)).strftime('%Y-%m-%d %H:%M:%S')
    c.execute(
        '''SELECT 1 FROM legendary_implant_actions
           WHERE actor_telegram_id=? AND target_telegram_id=? AND action_code='veil_breach'
             AND created_at>=? LIMIT 1''',
        (actor_id, target_id, cutoff),
    )
    if c.fetchone():
        conn.close()
        raise HTTPException(status_code=429, detail="Target protected for 14 days")
    locked_until = (datetime.now(BEIJING_TZ) + timedelta(hours=12)).strftime('%Y-%m-%d %H:%M:%S')
    c.execute(
        '''INSERT INTO user_status (telegram_id, netwatch_locked_until) VALUES (?, ?)
           ON CONFLICT(telegram_id) DO UPDATE SET netwatch_locked_until=excluded.netwatch_locked_until''',
        (target_id, locked_until),
    )
    log_legendary_action(c, actor_id, target_id, None, "implant_netwatch", "veil_breach", 0, 0, target_name)
    conn.commit()
    conn.close()
    await send_telegram_message(
        target_id,
        "🔴 NetWatch активировал «Взлом Заслона».\n"
        "Магазин и кейсы временно недоступны на 12 часов.",
    )
    return {"success": True, "target": target_name, "locked_until": locked_until}


@app.post("/api/casino/implants/disassemble/{implant_id}")
async def disassemble_implant(implant_id: int, data: dict):
    telegram_id = data.get("telegram_id")
    if not telegram_id:
        raise HTTPException(status_code=400, detail="No telegram_id")
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT implant_id FROM user_implants WHERE id=? AND telegram_id=? AND durability > 0", (implant_id, telegram_id))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Not found")
    implant_type = row[0]
    c.execute("""SELECT COUNT(*) FROM user_implants
                 WHERE telegram_id=? AND implant_id=? AND durability > 0""", (telegram_id, implant_type))
    count = c.fetchone()[0]
    if count < 2:
        conn.close()
        raise HTTPException(status_code=400, detail="Not a duplicate")
    c.execute("UPDATE user_implants SET durability=0 WHERE id=?", (implant_id,))
    c.execute("UPDATE users SET points = points + 100 WHERE telegram_id=?", (telegram_id,))
    c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
    new_points = c.fetchone()[0]
    log_economy(c, telegram_id, 'implant_disassemble', 100, new_points, implant_id, 'implant', implant_type)
    conn.commit()
    conn.close()
    return {"success": True, "refund": 100, "new_points": new_points}


@app.post("/api/casino/use/{purchase_id}")
async def use_casino_prize(purchase_id: int, data: dict):
    telegram_id = data.get("telegram_id")
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT telegram_id, item_code, expires_at FROM shop_purchases WHERE id=? AND status='active'", (purchase_id,))
    row = c.fetchone()
    if not row or row[0] != telegram_id:
        conn.close()
        raise HTTPException(status_code=404, detail="Not found")
    now_beijing = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
    if row[2] and row[2] < now_beijing:
        c.execute("UPDATE shop_purchases SET status='expired' WHERE id=?", (purchase_id,))
        conn.commit()
        conn.close()
        raise HTTPException(status_code=400, detail="Prize expired")
    c.execute("UPDATE shop_purchases SET status='used' WHERE id=?", (purchase_id,))
    conn.commit()
    conn.close()
    return {"success": True}


@app.get("/api/shop")
async def get_shop(telegram_id: int = 0):
    today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
    conn = get_conn()
    c = conn.cursor()
    is_frozen = user_netwatch_locked(c, telegram_id)
    c.execute("SELECT code, name, description, icon, price, daily_limit, category FROM shop_items WHERE active=1")
    items = c.fetchall()
    result = []
    has_guanxi = has_active_implant(c, telegram_id, "implant_guanxi") if telegram_id else False
    for code, name, description, icon, price, daily_limit, category in items:
        effective_price = max(0, int(price * 0.9)) if has_guanxi else price
        c.execute("SELECT count FROM shop_daily_counts WHERE item_code=? AND date=?", (code, today))
        row = c.fetchone()
        sold_today = row[0] if row else 0
        c.execute("""SELECT COUNT(*) FROM shop_purchases
                     WHERE telegram_id=? AND item_code=?
                     AND date(purchased_at)=?""", (telegram_id, code, today))
        user_bought = c.fetchone()[0]
        available = daily_limit == -1 or sold_today < daily_limit
        result.append({
            "code": code,
            "name": name,
            "description": description,
            "icon": icon,
            "price": effective_price,
            "base_price": price,
            "discounted": bool(has_guanxi and effective_price != price),
            "daily_limit": daily_limit,
            "sold_today": sold_today,
            "available": available and not is_frozen,
            "user_bought": user_bought,
            "category": category,
        })
    conn.close()
    return {"items": result, "frozen": is_frozen}


@app.post("/api/shop/buy")
async def buy_item(data: dict):
    telegram_id = data.get("telegram_id")
    item_code = data.get("item_code")
    today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
    if not telegram_id or not item_code:
        raise HTTPException(status_code=400, detail="Missing data")

    conn = get_conn()
    c = conn.cursor()
    if user_netwatch_locked(c, telegram_id):
        conn.close()
        raise HTTPException(status_code=403, detail="Account frozen")

    c.execute("SELECT name, price, daily_limit, category FROM shop_items WHERE code=? AND active=1", (item_code,))
    item = c.fetchone()
    if not item:
        conn.close()
        raise HTTPException(status_code=404, detail="Item not found")
    name, price, daily_limit, category = item
    base_price = price
    if has_active_implant(c, telegram_id, "implant_guanxi"):
        price = max(0, int(price * 0.9))

    if daily_limit != -1:
        c.execute("SELECT count FROM shop_daily_counts WHERE item_code=? AND date=?", (item_code, today))
        row = c.fetchone()
        if row and row[0] >= daily_limit:
            conn.close()
            raise HTTPException(status_code=409, detail="Daily limit reached")

    c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
    user = c.fetchone()
    if not user or (user[0] or 0) < price:
        conn.close()
        raise HTTPException(status_code=400, detail="Not enough points")

    c.execute("UPDATE users SET points = points - ? WHERE telegram_id=?", (price, telegram_id))
    if item_code == 'immunity':
        c.execute("""INSERT INTO user_status (telegram_id, immunity) VALUES (?,1)
                     ON CONFLICT(telegram_id) DO UPDATE SET immunity=1""", (telegram_id,))
    elif item_code == 'extra_case':
        c.execute("""INSERT INTO user_status (telegram_id, scan_attempts) VALUES (?,1)
                     ON CONFLICT(telegram_id) DO UPDATE SET scan_attempts=MIN(7, scan_attempts+1)""", (telegram_id,))
    elif item_code == SHOP_EXTRA_RAID_CODE:
        c.execute("""INSERT INTO user_status (telegram_id, extra_raids) VALUES (?,1)
                     ON CONFLICT(telegram_id) DO UPDATE SET extra_raids=extra_raids+1""", (telegram_id,))
    elif item_code == 'double_win':
        c.execute("""INSERT INTO user_status (telegram_id, double_win) VALUES (?,1)
                     ON CONFLICT(telegram_id) DO UPDATE SET double_win=1""", (telegram_id,))
    elif item_code == 'title_player':
        c.execute("""INSERT INTO user_status (telegram_id, title_date) VALUES (?,?)
                     ON CONFLICT(telegram_id) DO UPDATE SET title_date=?""", (telegram_id, today, today))

    c.execute("INSERT INTO shop_purchases (telegram_id, item_code) VALUES (?,?)", (telegram_id, item_code))
    c.execute("""INSERT INTO shop_daily_counts (item_code, date, count) VALUES (?,?,1)
                 ON CONFLICT(item_code, date) DO UPDATE SET count=count+1""", (item_code, today))
    c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
    new_points = c.fetchone()[0]
    log_economy(c, telegram_id, 'shop_purchase', -price, new_points, None, 'shop_item', name)
    if has_active_implant(c, telegram_id, "implant_panda"):
        c.execute("UPDATE users SET points = points + 10 WHERE telegram_id=?", (telegram_id,))
        c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
        new_points = c.fetchone()[0] or 0
        log_economy(c, telegram_id, 'implant_panda_cashback', 10, new_points, None, 'implant', name)
    conn.commit()
    conn.close()
    return {
        "success": True,
        "item": name,
        "new_points": new_points,
        "price_paid": price,
        "base_price": base_price,
        "guanxi_discount": base_price - price,
    }


@app.get("/api/shop/inventory/{telegram_id}")
async def get_inventory(telegram_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT sp.id, sp.item_code, si.name, si.icon, si.price,
                        si.category, sp.purchased_at, sp.status, sp.given_to, si.description
                 FROM shop_purchases sp
                 JOIN shop_items si ON sp.item_code = si.code
                 WHERE sp.telegram_id=? AND sp.status='active'
                 ORDER BY sp.purchased_at DESC""", (telegram_id,))
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "code": r[1], "name": r[2], "icon": r[3], "price": r[4], "category": r[5], "purchased_at": r[6], "status": r[7], "given_to": r[8], "description": r[9]} for r in rows]


@app.post("/api/shop/gift")
async def gift_item(data: dict):
    purchase_id = data.get("purchase_id")
    from_id = data.get("from_id")
    to_id = data.get("to_id")
    today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT item_code FROM shop_purchases WHERE id=? AND telegram_id=? AND status='active'", (purchase_id, from_id))
    purchase = c.fetchone()
    if not purchase:
        conn.close()
        raise HTTPException(status_code=404, detail="Purchase not found")
    if from_id not in ADMIN_IDS:
        c.execute(
            """SELECT COUNT(*) FROM shop_purchases
               WHERE given_to=? AND date(gifted_at)=?""",
            (from_id, today),
        )
        gifts_today = c.fetchone()[0] or 0
        if gifts_today >= SHOP_GIFT_DAILY_LIMIT:
            conn.close()
            raise HTTPException(status_code=400, detail="Daily gift limit reached")
    c.execute("SELECT points FROM users WHERE telegram_id=?", (from_id,))
    user = c.fetchone()
    if not user or (user[0] or 0) < 20:
        conn.close()
        raise HTTPException(status_code=400, detail="Not enough points for tax")
    c.execute("UPDATE users SET points = points - 20 WHERE telegram_id=?", (from_id,))
    now_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
    c.execute("UPDATE shop_purchases SET telegram_id=?, given_to=?, gifted_at=?, status='active' WHERE id=?", (to_id, from_id, now_str, purchase_id))
    c.execute("SELECT points FROM users WHERE telegram_id=?", (from_id,))
    new_points = c.fetchone()[0] or 0
    log_economy(c, from_id, 'gift_tax', -20, new_points, purchase_id, 'shop_gift', purchase[0])
    log_economy(c, to_id, 'gift_receive', 0, None, purchase_id, 'shop_gift', f"Получен подарок: {purchase[0]} от {from_id}")
    conn.commit()
    conn.close()
    return {"success": True}


@app.post("/api/shop/sell")
async def sell_item(data: dict):
    purchase_id = data.get("purchase_id")
    telegram_id = data.get("telegram_id")
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT sp.item_code, si.price FROM shop_purchases sp
                 JOIN shop_items si ON sp.item_code = si.code
                 WHERE sp.id=? AND sp.telegram_id=? AND sp.status='active'""", (purchase_id, telegram_id))
    purchase = c.fetchone()
    if not purchase:
        conn.close()
        raise HTTPException(status_code=404, detail="Not found")
    sell_rate = 0.6 if has_active_implant(c, telegram_id, "implant_panda") else 0.5
    refund = int(purchase[1] * sell_rate)
    c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (refund, telegram_id))
    c.execute("UPDATE shop_purchases SET status='sold' WHERE id=?", (purchase_id,))
    c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
    new_points = c.fetchone()[0]
    log_economy(c, telegram_id, 'shop_refund', refund, new_points, purchase_id, 'shop_item', purchase[0])
    conn.commit()
    conn.close()
    return {"success": True, "refund": refund, "new_points": new_points, "sell_rate": sell_rate}


@app.post("/api/shop/use/{purchase_id}")
async def use_shop_item(purchase_id: int, data: dict):
    telegram_id = data.get("telegram_id")
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT telegram_id, item_code FROM shop_purchases WHERE id=? AND status='active'", (purchase_id,))
    row = c.fetchone()
    if not row or row[0] != telegram_id:
        conn.close()
        raise HTTPException(status_code=404, detail="Not found")
    item_code = row[1]
    c.execute("UPDATE shop_purchases SET status='used' WHERE id=?", (purchase_id,))

    extra = {}
    if item_code == 'path_switch':
        c.execute("SELECT theme_path FROM user_status WHERE telegram_id=?", (telegram_id,))
        path_row = c.fetchone()
        current_path = path_row[0] if path_row else 'cyberpunk'
        new_path = 'genshin' if current_path != 'genshin' else 'cyberpunk'
        c.execute("""INSERT INTO user_status (telegram_id, theme_path) VALUES (?,?)
                     ON CONFLICT(telegram_id) DO UPDATE SET theme_path=excluded.theme_path""",
                  (telegram_id, new_path))
        extra = {"new_path": new_path}

    conn.commit()
    conn.close()
    return {"success": True, **extra}

@app.post("/api/admin/freeze")
async def freeze_user(data: dict, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")
    telegram_id = data.get("telegram_id")
    frozen = data.get("frozen", True)
    conn = get_conn()
    c = conn.cursor()
    c.execute("""INSERT INTO user_status (telegram_id, frozen) VALUES (?,?)
                 ON CONFLICT(telegram_id) DO UPDATE SET frozen=?""", (telegram_id, int(frozen), int(frozen)))
    c.execute(
        '''INSERT INTO admin_action_logs
           (admin_id, target_id, action_type, points_delta, reason, created_at)
           VALUES (?, ?, ?, 0, ?, ?)''',
        (
            x_admin_id,
            telegram_id,
            'freeze' if frozen else 'unfreeze',
            'NetWatch freeze' if frozen else 'NetWatch unfreeze',
            now_iso(),
        ),
    )
    conn.commit()
    conn.close()
    text = (
        "⛔ NETWATCH 网络保安\n\n"
        "系统检测到异常活动\n"
        "Система обнаружила подозрительную активность с вашей стороны.\n\n"
        "Ваш аккаунт временно заморожен.\n"
        "Магазин и кейсы недоступны.\n\n"
        "— NetWatch Protocol v1.4 —"
        if frozen else
        "✅ NETWATCH 网络保安\n\n"
        "访问已恢复\n"
        "Доступ восстановлен.\n\n"
        "Ваш аккаунт разморожен.\n"
        "Магазин и кейсы снова доступны.\n\n"
        "— NetWatch Protocol v1.4 —"
    )
    notified, notify_detail = await send_telegram_message(int(telegram_id), text)
    return {"success": True, "notified": notified, "notify_detail": notify_detail if not notified else None}


@app.post("/api/admin/reset_shop")
async def reset_shop(x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")
    today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM shop_daily_counts WHERE date=?", (today,))
    c.execute(
        '''INSERT INTO admin_action_logs
           (admin_id, target_id, action_type, points_delta, reason, created_at)
           VALUES (?, NULL, 'reset_shop', 0, ?, ?)''',
        (x_admin_id, f"Reset shop daily counts for {today}", now_iso()),
    )
    conn.commit()
    conn.close()
    return {"success": True, "message": "Магазин сброшен!"}


@app.post("/api/question")
async def send_question(data: dict):
    question = data.get("question")
    telegram_id = data.get("telegram_id")
    if not question:
        raise HTTPException(status_code=400, detail="No question")
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT full_name FROM users WHERE telegram_id=?", (telegram_id,))
    result = c.fetchone()
    conn.close()
    name = result[0] if result else str(telegram_id)
    for admin_id in ADMIN_IDS:
        if admin_id <= 0:
            continue
        await send_telegram_message(admin_id, f"🤫 Анонимный вопрос\n👤 От: {name}\n\n{question}")
    return {"success": True}


@app.get("/api/settings")
async def get_settings():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='blackwall'")
    blackwall = c.fetchone()
    c.execute("SELECT value FROM settings WHERE key='architect_event'")
    architect_event = c.fetchone()
    conn.close()
    return {
        "blackwall": blackwall[0] == '1' if blackwall else False,
        "architect_event": architect_event[0] == '1' if architect_event else False,
    }


@app.post("/api/admin/blackwall")
async def toggle_blackwall(data: dict, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")
    enabled = data.get("enabled", False)
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('blackwall', ?)", ('1' if enabled else '0',))
    c.execute(
        '''INSERT INTO admin_action_logs
           (admin_id, target_id, action_type, points_delta, reason, created_at)
           VALUES (?, NULL, 'blackwall', 0, ?, ?)''',
        (x_admin_id, 'BlackWall enabled' if enabled else 'BlackWall disabled', now_iso()),
    )
    conn.commit()
    conn.close()
    return {"success": True, "blackwall": enabled}


@app.post("/api/admin/architect-event")
async def toggle_architect_event(data: dict, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")
    enabled = bool(data.get("enabled", False))
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('architect_event', ?)", ('1' if enabled else '0',))
    c.execute(
        '''INSERT INTO admin_action_logs
           (admin_id, target_id, action_type, points_delta, reason, created_at)
           VALUES (?, NULL, 'architect_event', 0, ?, ?)''',
        (x_admin_id, 'Architect event enabled' if enabled else 'Architect event disabled', now_iso()),
    )
    conn.commit()
    conn.close()
    return {"success": True, "architect_event": enabled}


@app.get("/api/raid/status")
async def get_raid_status(telegram_id: int = 0):
    today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
    conn = get_conn()
    c = conn.cursor()
    finished_today = public_finished_raid_count(c, today)
    extra_raids = 0 if telegram_id in ADMIN_IDS else (get_extra_raids(c, telegram_id) if telegram_id else 0)
    user_attempts = 0 if telegram_id in ADMIN_IDS else (user_raid_attempt_count(c, today, telegram_id) if telegram_id else 0)
    base_remaining = max(0, RAID_USER_DAILY_LIMIT - user_attempts)
    if finished_today >= RAID_DAILY_LIMIT:
        base_remaining = 0
    remaining_today = 999 if telegram_id in ADMIN_IDS else base_remaining + extra_raids
    raid = latest_visible_raid(c, today, telegram_id)
    if not raid:
        conn.close()
        return {
            "raid": None,
            "participants": [],
            "count": 0,
            "finished_today": finished_today,
            "remaining_today": remaining_today,
            "limit_today": RAID_USER_DAILY_LIMIT,
            "required_players": RAID_MIN_PLAYERS,
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
        "limit_today": RAID_USER_DAILY_LIMIT,
        "required_players": RAID_MIN_PLAYERS,
    }


@app.post("/api/raid/join")
async def join_raid(data: dict):
    telegram_id = data.get("telegram_id")
    if not telegram_id:
        raise HTTPException(status_code=400, detail="No telegram_id")

    today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
    now_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
    conn = sqlite3.connect('/root/zhidao.db', isolation_level='EXCLUSIVE')
    c = conn.cursor()

    c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
    user = c.fetchone()
    if not user or (user[0] or 0) < RAID_ENTRY_COST:
        conn.close()
        raise HTTPException(status_code=400, detail="Not enough points")

    finished_count = public_finished_raid_count(c, today)
    extra_raids = 0 if telegram_id in ADMIN_IDS else get_extra_raids(c, telegram_id)
    user_attempts = 0 if telegram_id in ADMIN_IDS else user_raid_attempt_count(c, today, telegram_id)
    consumed_extra_attempt = False
    needs_extra_attempt = telegram_id not in ADMIN_IDS and (
        finished_count >= RAID_DAILY_LIMIT or user_attempts >= RAID_USER_DAILY_LIMIT
    )
    if needs_extra_attempt:
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
        c.execute("INSERT INTO raid_participants (raid_id, telegram_id) VALUES (?,?)", (raid_id, telegram_id))
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=409, detail="Already joined")

    c.execute("UPDATE users SET points = points - ? WHERE telegram_id=?", (RAID_ENTRY_COST, telegram_id))
    c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
    raid_entry_balance = c.fetchone()[0] or 0
    log_economy(c, telegram_id, 'raid_entry', -RAID_ENTRY_COST, raid_entry_balance, raid_id, 'raid', f"Raid {today}")
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
                c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (RAID_SUCCESS_REWARD, tid))
                c.execute("SELECT points FROM users WHERE telegram_id=?", (tid,))
                raid_reward_balance = c.fetchone()[0] or 0
                log_economy(c, tid, 'raid_reward', RAID_SUCCESS_REWARD, raid_reward_balance, raid_id, 'raid', f"Raid {today}")

    conn.commit()
    c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
    new_points = c.fetchone()[0]
    finished_today = public_finished_raid_count(c, today)
    attempts_today = 0 if telegram_id in ADMIN_IDS else user_raid_attempt_count(c, today, telegram_id)
    base_remaining = max(0, RAID_USER_DAILY_LIMIT - attempts_today)
    if finished_today >= RAID_DAILY_LIMIT:
        base_remaining = 0
    remaining = 999 if telegram_id in ADMIN_IDS else base_remaining + get_extra_raids(c, telegram_id)
    conn.close()
    return {
        "joined": True,
        "count": count,
        "launched": launched,
        "result": result,
        "participants_count": count,
        "new_points": new_points,
        "remaining_today": remaining,
        "limit_today": RAID_USER_DAILY_LIMIT,
        "required_players": RAID_MIN_PLAYERS,
        "consumed_extra_attempt": consumed_extra_attempt,
        "points_change": (RAID_SUCCESS_REWARD - RAID_ENTRY_COST) if (launched and result == 'success') else -RAID_ENTRY_COST,
        "message": (
            f"🏆 РЕЙД УСПЕШЕН! +{RAID_SUCCESS_REWARD}★ каждому!" if (launched and result == 'success') else
            "🛡 АЛЬФАБОСС ЗАЩИТИЛСЯ! Ставки сгорели 🔥" if (launched and result == 'defended') else
            f"⚔️ Ты в отряде! Бойцов: {count}/{RAID_MIN_PLAYERS}"
        ),
    }


CARD_INFO = {
    'card_zhongli': {"name": "岩王帝君 Архонт Земли", "rarity": 5, "passive": "Контракт — блок штрафа + -5% магазин"},
    'card_pyro': {"name": "焰莲使者 Страж Огня", "rarity": 4, "passive": "Феникс — +50★ после штрафа"},
    'card_fox': {"name": "九尾狐灵 Лиса-Оборотень", "rarity": 4, "passive": "Обман — перекрутить неудачный приз"},
    'card_fairy': {"name": "桃花仙子 Небесная Фея", "rarity": 4, "passive": "Благословение — +30★ отряду на перекличке"},
    'card_literature': {"name": "文曲星君 Звезда Литературы", "rarity": 4, "passive": "Мудрость — +25★ за каждый отчёт"},
    'card_forest': {"name": "木灵仙君 Дух Леса", "rarity": 4, "passive": "Урожай — +10★ за каждый день вовремя"},
    'card_sea': {"name": "海灵仙后 Дух Морей", "rarity": 4, "passive": "Волна — каждые 3 молитвы +30★"},
    'card_star': {"name": "紫微星君 Императорская Звезда", "rarity": 5, "passive": "Звёздный суд — передать штраф другому"},
    'card_moon': {"name": "嫦娥仙子 Богиня Луны", "rarity": 4, "passive": "Жемчужина — дубль даёт +50★"},
}

GENSHIN_POOL = {
    'blue': {
        'weight': 790,
        'items': [
            {'type': 'points', 'amount': 30, 'weight': 300},
            {'type': 'points', 'amount': 60, 'weight': 150},
            {'type': 'immunity', 'weight': 80},
            {'type': 'walk', 'weight': 50},
            {'type': 'card', 'id': 'card_fairy', 'weight': 40},
            {'type': 'card', 'id': 'card_literature', 'weight': 40},
            {'type': 'card', 'id': 'card_forest', 'weight': 40},
            {'type': 'card', 'id': 'card_sea', 'weight': 40},
            {'type': 'card', 'id': 'card_moon', 'weight': 40},
        ],
    },
    'purple': {
        'weight': 200,
        'items': [
            {'type': 'card', 'id': 'card_pyro', 'weight': 1},
            {'type': 'card', 'id': 'card_fox', 'weight': 1},
            {'type': 'card', 'id': 'card_fairy', 'weight': 1},
            {'type': 'card', 'id': 'card_literature', 'weight': 1},
            {'type': 'card', 'id': 'card_forest', 'weight': 1},
            {'type': 'card', 'id': 'card_sea', 'weight': 1},
            {'type': 'card', 'id': 'card_moon', 'weight': 1},
        ],
    },
    'gold': {
        'weight': 10,
        'items': [
            {'type': 'card', 'id': 'card_zhongli', 'weight': 1},
            {'type': 'card', 'id': 'card_star', 'weight': 1},
        ],
    },
}

@app.get("/api/cards/{telegram_id}")
async def get_cards(telegram_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, card_id, obtained_at, durability FROM user_cards WHERE telegram_id=? AND durability > 0 ORDER BY obtained_at DESC", (telegram_id,))
    rows = c.fetchall()
    conn.close()
    result = []
    for row in rows:
        info = CARD_INFO.get(row[1], {"name": row[1], "rarity": 4, "passive": ""})
        result.append({
            "id": row[0],
            "card_id": row[1],
            "name": info["name"],
            "rarity": info["rarity"],
            "passive": info["passive"],
            "durability": row[3],
            "obtained_at": row[2],
        })
    return result


@app.post("/api/genshin/open")
async def open_genshin_case(data: dict):
    telegram_id = data.get("telegram_id")
    if not telegram_id:
        raise HTTPException(status_code=400, detail="No telegram_id")
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
    user = c.fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    points = user[0] or 0

    if telegram_id not in ADMIN_IDS:
        c.execute("SELECT scan_attempts FROM user_status WHERE telegram_id=?", (telegram_id,))
        status_row = c.fetchone()
        scan_attempts = status_row[0] if status_row else 0
        if scan_attempts <= 0:
            conn.close()
            raise HTTPException(status_code=400, detail="No scan attempts")
        c.execute("""INSERT INTO user_status (telegram_id, scan_attempts, protocol_fragments) VALUES (?,0,1)
                     ON CONFLICT(telegram_id) DO UPDATE SET
                       scan_attempts=MAX(0, scan_attempts-1),
                       protocol_fragments=protocol_fragments+1""", (telegram_id,))
    else:
        c.execute("SELECT scan_attempts, protocol_fragments FROM user_status WHERE telegram_id=?", (telegram_id,))
        status_row = c.fetchone()

    pool_name = random.choices(['blue', 'purple', 'gold'], weights=[790, 200, 10])[0]
    pool = GENSHIN_POOL[pool_name]
    item = random.choices(pool['items'], weights=[it['weight'] for it in pool['items']])[0]
    today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
    now_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
    result = {}

    if item['type'] == 'card':
        card_id = item['id']
        info = CARD_INFO[card_id]
        c.execute("SELECT COUNT(*) FROM user_cards WHERE telegram_id=? AND card_id=? AND durability > 0", (telegram_id, card_id))
        already_has = c.fetchone()[0]
        if already_has > 0:
            prize_code = f"genshin_duplicate_{card_id}"
            result = {"type": "card", "card_id": card_id, "name": info["name"], "rarity": info["rarity"], "passive": info["passive"], "pool": pool_name, "duplicate": True, "bonus": None}
        else:
            c.execute("INSERT INTO user_cards (telegram_id, card_id, obtained_at, durability) VALUES (?,?,?,3)", (telegram_id, card_id, now_str))
            prize_code = f"genshin_{card_id}"
            result = {"type": "card", "card_id": card_id, "name": info["name"], "rarity": info["rarity"], "passive": info["passive"], "pool": pool_name, "duplicate": False, "bonus": None}
    elif item['type'] == 'points':
        amount = item['amount']
        c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (amount, telegram_id))
        prize_code = f"genshin_points_{amount}"
        result = {"type": "points", "amount": amount, "pool": pool_name, "name": f"+{amount} ★", "rarity": 0}
    elif item['type'] == 'immunity':
        c.execute("INSERT INTO user_status (telegram_id, immunity) VALUES (?,1) ON CONFLICT(telegram_id) DO UPDATE SET immunity=1", (telegram_id,))
        prize_code = "genshin_immunity"
        result = {"type": "immunity", "pool": pool_name, "name": "Иммунитет", "rarity": 0}
    else:
        expires = today + ' 22:00:00'
        c.execute("INSERT INTO shop_purchases (telegram_id, item_code, purchased_at, status, expires_at) VALUES (?,?,?,?,?)", (telegram_id, 'casino_walk', now_str, 'active', expires))
        prize_code = "genshin_walk"
        result = {"type": "walk", "pool": pool_name, "name": "+30 мин свободы", "rarity": 0}

    c.execute("INSERT INTO casino_log (telegram_id, date, prize, created_at) VALUES (?,?,?,?)", (telegram_id, today, prize_code, now_str))
    c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
    new_points = c.fetchone()[0]
    c.execute("SELECT scan_attempts, protocol_fragments FROM user_status WHERE telegram_id=?", (telegram_id,))
    sc_row = c.fetchone()
    log_economy(c, telegram_id, 'prayer_open', new_points - points, new_points, None, pool_name, result.get("name") or prize_code)
    conn.commit()
    conn.close()
    result["new_points"] = new_points
    result["scan_attempts"] = sc_row[0] if sc_row else 0
    result["protocol_fragments"] = sc_row[1] if sc_row else 0
    return result


@app.post("/api/admin/fragments")
async def admin_grant_fragments(data: dict, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ARCHITECT_IDS:
        raise HTTPException(status_code=403, detail="Forbidden: Architect only")
    telegram_id = data.get("telegram_id")
    amount = int(data.get("amount") or 0)
    if not telegram_id or amount < 1:
        raise HTTPException(status_code=400, detail="Missing data")
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT 1 FROM users WHERE telegram_id=?", (telegram_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    c.execute("""INSERT INTO user_status (telegram_id, protocol_fragments) VALUES (?,?)
                 ON CONFLICT(telegram_id) DO UPDATE SET protocol_fragments=COALESCE(protocol_fragments,0)+?""",
              (telegram_id, amount, amount))
    c.execute("SELECT protocol_fragments FROM user_status WHERE telegram_id=?", (telegram_id,))
    new_val = c.fetchone()[0]
    conn.commit()
    conn.close()
    return {"success": True, "telegram_id": telegram_id, "amount": amount, "protocol_fragments": new_val}


FRAGMENT_IMPLANT_POOL = [
    'implant_guanxi', 'implant_terracota', 'implant_panda',
    'implant_shaolin', 'implant_linguasoft', 'implant_caishen', 'implant_qilin',
]
FRAGMENT_CARD_POOL = [
    'card_fairy', 'card_literature', 'card_forest', 'card_sea', 'card_moon',
    'card_pyro', 'card_fox',
]
FRAGMENT_COST = 10

@app.post("/api/fragments/exchange")
async def exchange_fragments(data: dict):
    telegram_id = data.get("telegram_id")
    exchange_type = data.get("type")  # "implant" or "card"
    if not telegram_id or exchange_type not in ("implant", "card"):
        raise HTTPException(status_code=400, detail="Missing data")

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT 1 FROM users WHERE telegram_id=?", (telegram_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    c.execute("SELECT protocol_fragments FROM user_status WHERE telegram_id=?", (telegram_id,))
    row = c.fetchone()
    fragments = row[0] if row else 0
    if fragments < FRAGMENT_COST:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Not enough fragments ({fragments}/{FRAGMENT_COST})")

    now_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
    _implant_names = {
        'implant_guanxi': 'Гуаньси 关系', 'implant_terracota': 'Терракота 兵马俑',
        'implant_panda': 'Панда 🐼', 'implant_shaolin': 'Шаолинь 少林',
        'implant_linguasoft': 'Linguasoft 口才', 'implant_caishen': 'Цайшэнь 财神',
        'implant_qilin': 'Цилинь 麒麟',
    }
    if exchange_type == "implant":
        item_id = random.choice(FRAGMENT_IMPLANT_POOL)
        c.execute("INSERT INTO user_implants (telegram_id, implant_id, durability, obtained_at) VALUES (?,?,3,?)",
                  (telegram_id, item_id, now_str))
        result = {"type": "implant", "id": item_id, "name": _implant_names.get(item_id, item_id)}
    else:
        item_id = random.choice(FRAGMENT_CARD_POOL)
        info = CARD_INFO.get(item_id, {"name": item_id, "rarity": 4, "passive": ""})
        c.execute("INSERT INTO user_cards (telegram_id, card_id, obtained_at, durability) VALUES (?,?,?,3)",
                  (telegram_id, item_id, now_str))
        result = {"type": "card", "card_id": item_id, "name": info["name"],
                  "rarity": info.get("rarity", 4), "passive": info.get("passive", "")}

    c.execute("""INSERT INTO user_status (telegram_id, protocol_fragments) VALUES (?,?)
                 ON CONFLICT(telegram_id) DO UPDATE SET protocol_fragments=protocol_fragments-?""",
              (telegram_id, FRAGMENT_COST, FRAGMENT_COST))
    c.execute("SELECT protocol_fragments FROM user_status WHERE telegram_id=?", (telegram_id,))
    new_frags = c.fetchone()[0]
    conn.commit()
    conn.close()
    result["protocol_fragments"] = new_frags
    return result


@app.post("/api/cards/disassemble/{card_id}")
async def disassemble_card(card_id: int, data: dict):
    telegram_id = data.get("telegram_id")
    if not telegram_id:
        raise HTTPException(status_code=400, detail="No telegram_id")
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT card_id FROM user_cards WHERE id=? AND telegram_id=? AND durability > 0", (card_id, telegram_id))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Not found")
    card_type = row[0]
    c.execute("SELECT COUNT(*) FROM user_cards WHERE telegram_id=? AND card_id=? AND durability > 0", (telegram_id, card_type))
    count = c.fetchone()[0]
    if count < 2:
        conn.close()
        raise HTTPException(status_code=400, detail="Not a duplicate")
    c.execute("UPDATE user_cards SET durability=0 WHERE id=?", (card_id,))
    c.execute("UPDATE users SET points = points + 50 WHERE telegram_id=?", (telegram_id,))
    c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
    new_points = c.fetchone()[0]
    log_economy(c, telegram_id, 'card_disassemble', 50, new_points, card_id, 'card', card_type)
    conn.commit()
    conn.close()
    return {"success": True, "refund": 50, "new_points": new_points}


@app.get("/api/laundry/schedule")
async def get_laundry_schedule():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, day, time, note, taken_by FROM laundry_schedule ORDER BY id")
    rows = c.fetchall()
    result = []
    for row in rows:
        taken = None
        if row[4]:
            c.execute("SELECT full_name FROM users WHERE telegram_id=?", (row[4],))
            u = c.fetchone()
            taken = {"telegram_id": row[4], "name": u[0] if u else "Неизвестно"}
        result.append({"id": row[0], "day": row[1], "time": row[2], "note": row[3], "taken_by": taken})
    conn.close()
    return result


@app.post("/api/laundry/schedule")
async def add_laundry_slot(data: dict, x_admin_id: int = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Not admin")
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO laundry_schedule (day, time, note) VALUES (?,?,?)", (data.get("day"), data.get("time"), data.get("note", "")))
    conn.commit()
    conn.close()
    return {"success": True}


@app.delete("/api/laundry/schedule/{slot_id}")
async def delete_laundry_slot(slot_id: int, x_admin_id: int = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Not admin")
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM laundry_schedule WHERE id=?", (slot_id,))
    conn.commit()
    conn.close()
    return {"success": True}


@app.post("/api/laundry/schedule/{slot_id}/book")
async def book_laundry_slot(slot_id: int, data: dict):
    telegram_id = data.get("telegram_id")
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT taken_by FROM laundry_schedule WHERE id=?", (slot_id,))
    slot = c.fetchone()
    if not slot:
        conn.close()
        raise HTTPException(status_code=404, detail="Not found")
    if slot[0]:
        conn.close()
        raise HTTPException(status_code=400, detail="Already booked")
    c.execute("SELECT id FROM laundry_schedule WHERE taken_by=?", (telegram_id,))
    if c.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Already booked")
    c.execute("UPDATE laundry_schedule SET taken_by=? WHERE id=?", (telegram_id, slot_id))
    conn.commit()
    conn.close()
    return {"success": True}


@app.post("/api/laundry/schedule/{slot_id}/cancel")
async def cancel_laundry_slot(slot_id: int, data: dict):
    telegram_id = data.get("telegram_id")
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE laundry_schedule SET taken_by=NULL WHERE id=? AND taken_by=?", (slot_id, telegram_id))
    conn.commit()
    conn.close()
    return {"success": True}


@app.get("/api/water/schedule")
async def get_water_schedule():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, day, time, note FROM water_schedule ORDER BY id")
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "day": r[1], "time": r[2], "note": r[3]} for r in rows]


@app.post("/api/water/schedule")
async def add_water_slot(data: dict, x_admin_id: int = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Not admin")
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO water_schedule (day, time, note) VALUES (?,?,?)", (data.get("day"), data.get("time"), data.get("note", "")))
    conn.commit()
    conn.close()
    return {"success": True}


@app.delete("/api/water/schedule/{slot_id}")
async def delete_water_slot(slot_id: int, x_admin_id: int = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Not admin")
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM water_schedule WHERE id=?", (slot_id,))
    conn.commit()
    conn.close()
    return {"success": True}


@app.post("/api/events/architect/create")
async def create_architect_event(data: dict, x_admin_id: int = Header(None)):
    admin_id = x_admin_id if x_admin_id is not None else data.get("telegram_id")
    if admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    blocking_event_id = get_blocking_event_id()
    if blocking_event_id:
        raise HTTPException(status_code=409, detail="Another event is already active")

    conn = get_conn()
    c = conn.cursor()

    title = data.get("title") or "ARCHITECT PROTOCOL"
    boss_name = data.get("boss_name") or "Архитектор"
    boss_image = data.get("boss_image")
    reward_text = data.get("reward_text") or "Приз не указан"
    min_players = int(data.get("min_players") or 3)
    max_players = int(data.get("max_players") or 5)
    max_hp = int(data.get("max_hp") or ARCHITECT_DEFAULT_HP)
    created_at = now_iso()
    if min_players < 1:
        min_players = 1
    if max_players < min_players:
        max_players = min_players
    c.execute(
        '''INSERT INTO events
           (code, title, boss_name, boss_image, reward_text, min_players, max_players,
            max_hp, current_hp, phase, state,
            phase_started_at, started_at, final_phase_deadline, vulnerability_until, overload_pressure, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'REGISTRATION', NULL, NULL, NULL, NULL, 0, ?)''',
        ('architect', title, boss_name, boss_image, reward_text, min_players, max_players, max_hp, max_hp, created_at),
    )
    event_id = c.lastrowid
    add_event_log(c, event_id, "system", "Architect event created. Team registration is open.")
    add_event_log(c, event_id, "boss", f"Набор команды открыт. Приз: {reward_text}")
    conn.commit()
    conn.close()
    return get_event_snapshot(event_id)


@app.get("/api/events/current")
async def get_current_event():
    event_id = get_current_or_latest_event_id()
    return {"event": get_event_snapshot(event_id) if event_id else None}


@app.get("/api/events/{event_id}")
async def get_event_details(event_id: int):
    snapshot = get_event_snapshot(event_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Event not found")
    return snapshot


@app.post("/api/events/{event_id}/join")
async def join_event_team(event_id: int, data: dict):
    telegram_id = data.get("telegram_id")
    if not telegram_id:
        raise HTTPException(status_code=400, detail="No telegram_id")

    conn = get_conn()
    c = conn.cursor()
    event_row = fetch_event_row(c, event_id)
    if not event_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Event not found")
    if event_row["state"] != "REGISTRATION":
        conn.close()
        raise HTTPException(status_code=400, detail="Registration is closed")

    team_members = get_event_team_members(c, event_id)
    if any(member["telegram_id"] == telegram_id for member in team_members):
        conn.close()
        raise HTTPException(status_code=409, detail="Already in team")
    if len(team_members) >= event_row["max_players"]:
        conn.close()
        raise HTTPException(status_code=400, detail="Team is full")

    c.execute(
        "INSERT INTO event_team_members (event_id, telegram_id, joined_at) VALUES (?, ?, ?)",
        (event_id, telegram_id, now_iso()),
    )
    player_name = get_user_display_name(c, telegram_id)
    add_event_log(c, event_id, "system", f"{player_name} вступил(а) в команду")
    conn.commit()
    conn.close()
    return get_event_snapshot(event_id)


@app.post("/api/events/{event_id}/leave")
async def leave_event_team(event_id: int, data: dict):
    telegram_id = data.get("telegram_id")
    if not telegram_id:
        raise HTTPException(status_code=400, detail="No telegram_id")

    conn = get_conn()
    c = conn.cursor()
    event_row = fetch_event_row(c, event_id)
    if not event_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Event not found")
    if event_row["state"] != "REGISTRATION":
        conn.close()
        raise HTTPException(status_code=400, detail="Cannot leave after start")

    c.execute(
        "SELECT id FROM event_team_members WHERE event_id=? AND telegram_id=?",
        (event_id, telegram_id),
    )
    existing = c.fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Not in team")

    c.execute(
        "DELETE FROM event_team_members WHERE event_id=? AND telegram_id=?",
        (event_id, telegram_id),
    )
    player_name = get_user_display_name(c, telegram_id)
    add_event_log(c, event_id, "system", f"{player_name} покинул(а) команду")
    conn.commit()
    conn.close()
    return get_event_snapshot(event_id)


@app.get("/api/events/{event_id}/team")
async def get_event_team(event_id: int):
    snapshot = get_event_snapshot(event_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Event not found")
    return {
        "event_id": snapshot["id"],
        "title": snapshot["title"],
        "boss_name": snapshot["boss_name"],
        "reward_text": snapshot.get("reward_text"),
        "state": snapshot["state"],
        "min_players": snapshot.get("min_players", 3),
        "max_players": snapshot.get("max_players", 5),
        "team_count": snapshot.get("team_count", 0),
        "team_members": snapshot.get("team_members", []),
    }


@app.post("/api/events/{event_id}/extra")
async def add_event_extra_participant(
    event_id: int,
    data: dict,
    x_admin_id: int = Header(None),
):
    """Admin: add or remove a free-text name from extra_participants list."""
    import json as _json
    if not x_admin_id or x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Admin only")
    name = str(data.get("name", "")).strip()
    action = str(data.get("action", "add")).strip()  # "add" | "remove"
    if not name:
        raise HTTPException(status_code=400, detail="name required")

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT extra_participants FROM events WHERE id=?", (event_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Event not found")

    try:
        current = _json.loads(row[0]) if row[0] else []
    except Exception:
        current = []

    if action == "remove":
        current = [n for n in current if n != name]
    else:
        if name not in current:
            current.append(name)

    c.execute(
        "UPDATE events SET extra_participants=? WHERE id=?",
        (_json.dumps(current, ensure_ascii=False), event_id),
    )
    conn.commit()
    conn.close()
    return {"event_id": event_id, "extra_participants": current}


@app.post("/api/events/{event_id}/start")
async def start_event(event_id: int, data: dict = None, x_admin_id: int = Header(None)):
    admin_id = x_admin_id if x_admin_id is not None else (data or {}).get("telegram_id")
    if admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    conn = get_conn()
    c = conn.cursor()
    event_row = fetch_event_row(c, event_id)
    if not event_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Event not found")
    if event_row["state"] != "REGISTRATION":
        conn.close()
        raise HTTPException(status_code=400, detail="Event is not in registration state")

    team_members = get_event_team_members(c, event_id)
    admin_solo_mode = len(team_members) < event_row["min_players"] and admin_id in ADMIN_IDS
    if len(team_members) < event_row["min_players"] and not admin_solo_mode:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail=f"Not enough players: {len(team_members)}/{event_row['min_players']}"
        )
    if admin_solo_mode:
        ensure_admin_event_team_member(c, event_id, int(admin_id))

    started_at = now_iso()
    c.execute(
        "UPDATE events SET state='ACTIVE', phase=1, phase_started_at=?, started_at=? WHERE id=?",
        (started_at, started_at, event_id),
    )
    add_event_log(c, event_id, "system", "Architect event started.")
    add_event_log(c, event_id, "boss", "观察开始。 / Фаза наблюдения активирована.")
    conn.commit()
    conn.close()
    return get_event_snapshot(event_id)


@app.get("/api/events/{event_id}/question")
async def get_event_question(event_id: int, telegram_id: int, action_type: str):
    snapshot = get_event_snapshot(event_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Event not found")
    if snapshot["state"] != "ACTIVE":
        raise HTTPException(status_code=400, detail="Event is not active")
    if action_type not in ("attack", "protocol", "stabilize", "sync"):
        raise HTTPException(status_code=400, detail="Invalid action_type")

    conn = get_conn()
    c = conn.cursor()
    if not is_event_team_member(c, event_id, telegram_id) and not ensure_admin_event_team_member(c, event_id, int(telegram_id)):
        conn.close()
        raise HTTPException(status_code=403, detail="You are not in the event team")
    conn.commit()

    if action_type == "sync":
        conn.close()
        return {
            "event_id": event_id,
            "action_type": "sync",
            "question": None,
            "hint": "SYNC does not require a question in MVP.",
        }

    question = choose_architect_question(c, action_type)
    conn.close()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    return {
        "event_id": event_id,
        "action_type": action_type,
        "question": {
            "id": question["id"],
            "prompt": question["prompt"],
            "options": {
                "a": question["option_a"],
                "b": question["option_b"],
                "c": question["option_c"],
            },
        },
    }


@app.post("/api/events/action")
async def resolve_event_action(data: dict):
    event_id = data.get("event_id")
    telegram_id = data.get("telegram_id")
    action_type = data.get("action_type")
    question_id = data.get("question_id")
    answer_option = data.get("answer_option")
    use_active_modifier = bool(data.get("use_active_modifier"))

    if not event_id or not telegram_id or action_type not in ("attack", "protocol", "sync", "stabilize"):
        raise HTTPException(status_code=400, detail="Invalid payload")

    conn = get_conn()
    c = conn.cursor()
    event_row = fetch_event_row(c, int(event_id))
    if not event_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Event not found")

    event_row = refresh_event_state(c, event_row)
    if event_row["state"] != "ACTIVE":
        conn.commit()
        conn.close()
        raise HTTPException(status_code=400, detail="Event is not active")
    if not is_event_team_member(c, int(event_id), int(telegram_id)) and not ensure_admin_event_team_member(c, int(event_id), int(telegram_id)):
        conn.close()
        raise HTTPException(status_code=403, detail="You are not in the event team")

    participant = ensure_event_participant(c, int(event_id), int(telegram_id))

    is_correct = 1
    question = None
    if action_type != "sync":
        if not question_id or answer_option not in ("a", "b", "c"):
            conn.close()
            raise HTTPException(status_code=400, detail="Question and answer required")
        c.execute(
            '''SELECT id, correct_option, explanation
               FROM event_questions
               WHERE id=? AND event_code='architect' AND action_type=?''',
            (question_id, action_type),
        )
        row = c.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Question not found")
        question = {"id": row[0], "correct_option": row[1], "explanation": row[2]}
        is_correct = 1 if row[1] == answer_option else 0

    result = compute_event_action_result(
        c,
        event_row,
        participant,
        action_type,
        bool(is_correct),
        use_active_modifier,
    )

    c.execute(
        '''INSERT INTO event_actions
           (event_id, telegram_id, action_type, question_id, is_correct, base_value, modifier_value, final_value, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (
            int(event_id),
            int(telegram_id),
            action_type,
            question_id,
            int(is_correct),
            result["base_value"],
            result["modifier_value"],
            result["final_value"] if action_type != "stabilize" else result["support_value"],
            now_iso(),
        ),
    )

    actor_name = get_user_display_name(c, int(telegram_id))
    if action_type in ("attack", "protocol"):
        event_row["current_hp"] = max(0, event_row["current_hp"] - result["final_value"])
        c.execute("UPDATE events SET current_hp=? WHERE id=?", (event_row["current_hp"], int(event_id)))
        c.execute(
            "UPDATE event_participants SET total_damage = total_damage + ? WHERE id=?",
            (result["final_value"], participant["id"]),
        )
        action_name = "Protocol" if action_type == "protocol" else "атака"
        if is_correct:
            add_event_log(c, int(event_id), "action", f"{actor_name} активировал(а) {action_name} и нанёс(ла) {result['final_value']} урона")
        else:
            add_event_log(c, int(event_id), "action", f"{actor_name} ошибся(лась) в {action_name} и не пробил(а) протокол")
    elif action_type == "stabilize":
        c.execute(
            "UPDATE event_participants SET total_support = total_support + ? WHERE id=?",
            (result["support_value"], participant["id"]),
        )
        if is_correct:
            add_event_log(c, int(event_id), "action", f"{actor_name} стабилизировал(а) протокол (+{result['support_value']} support)")
        else:
            add_event_log(c, int(event_id), "action", f"{actor_name} попытался(ась) стабилизировать протокол, но допустил(а) ошибку")
    else:
        c.execute(
            "UPDATE event_participants SET total_support = total_support + ? WHERE id=?",
            (result["support_value"], participant["id"]),
        )
        add_event_log(c, int(event_id), "action", f"{actor_name} синхронизировал(а) канал")
        maybe_trigger_sync_window(c, event_row)

    if action_type in ("attack", "protocol", "stabilize") and result["pressure_delta"] != 0:
        old_pressure = event_row["overload_pressure"]
        event_row["overload_pressure"] = max(0, old_pressure + result["pressure_delta"])
        c.execute("UPDATE events SET overload_pressure=? WHERE id=?", (event_row["overload_pressure"], int(event_id)))
        if old_pressure < ARCHITECT_OVERLOAD_PENALTY_THRESHOLD <= event_row["overload_pressure"]:
            add_event_log(c, int(event_id), "system", "System Overload Detected")

    if result["active_note"]:
        add_event_log(c, int(event_id), "modifier", result["active_note"])

    event_row = fetch_event_row(c, int(event_id))
    event_row = refresh_event_state(c, event_row)
    conn.commit()
    conn.close()

    snapshot = get_event_snapshot(int(event_id))
    return {
        "event_id": int(event_id),
        "action_type": action_type,
        "is_correct": bool(is_correct),
        "damage_dealt": result["final_value"],
        "support_value": result["support_value"],
        "current_hp": snapshot["current_hp"],
        "phase": snapshot["phase"],
        "state": snapshot["state"],
        "vulnerability_active": snapshot["vulnerability_active"],
        "overload_pressure": snapshot["overload_pressure"],
        "logs": snapshot["logs"],
        "question_explanation": question["explanation"] if question else None,
    }


@app.get("/api/events/{event_id}/leaderboard")
async def get_event_leaderboard(event_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        '''SELECT telegram_id, total_damage, total_support
           FROM event_participants
           WHERE event_id=?
           ORDER BY total_damage DESC, total_support DESC, telegram_id ASC''',
        (event_id,),
    )
    rows = c.fetchall()
    conn.close()
    return {
        "event_id": event_id,
        "leaderboard": [
            {
                "telegram_id": row[0],
                "total_damage": row[1],
                "total_support": row[2],
            }
            for row in rows
        ],
    }


# ============================================================
# ДОСКА ПОРУЧЕНИЙ — CONTRACT BOARD
# ============================================================

def _contract_to_dict(row, creator_name=None, assignee_name=None,
                      creator_avatar_url=None, assignee_avatar_url=None,
                      viewer_id=None):
    reward = row[4]
    fee = row[5]
    return {
        "id": row[0],
        "title": row[1],
        "description": row[2],
        "category": row[3],
        "reward_stars": reward,
        "fee_stars": fee,
        "payout_stars": reward - fee,
        "creator_telegram_id": row[6],
        "assignee_telegram_id": row[7],
        "creator_is_admin": row[6] in ADMIN_IDS,
        "creator_name": creator_name or "Аноним",
        "assignee_name": assignee_name,
        "creator_avatar_url": creator_avatar_url,
        "assignee_avatar_url": assignee_avatar_url,
        "status": row[8],
        "is_suspicious": bool(row[9]),
        "suspicious_reason": row[10],
        "created_at": row[11],
        "accepted_at": row[12],
        "completed_at": row[13],
        "cancelled_at": row[14],
        "disputed_at": row[15],
        "role": ("creator" if viewer_id and row[6] == viewer_id else
                 "assignee" if viewer_id and row[7] == viewer_id else None),
    }


def _resolve_names(c, creator_id, assignee_id):
    c.execute("SELECT full_name, avatar_url FROM users WHERE telegram_id=?", (creator_id,))
    r = c.fetchone()
    creator_name = r[0] if r else "Аноним"
    creator_avatar_url = r[1] if r else None
    assignee_name = None
    assignee_avatar_url = None
    if assignee_id:
        c.execute("SELECT full_name, avatar_url FROM users WHERE telegram_id=?", (assignee_id,))
        r2 = c.fetchone()
        assignee_name = r2[0] if r2 else "Аноним"
        assignee_avatar_url = r2[1] if r2 else None
    return creator_name, assignee_name, creator_avatar_url, assignee_avatar_url


def _check_blackwall(c, user_id):
    c.execute("SELECT value FROM settings WHERE key='blackwall'")
    bw = c.fetchone()
    if bw and bw[0] == '1' and (user_id is None or user_id not in ADMIN_IDS):
        raise HTTPException(status_code=403, detail="Доска поручений временно заблокирована режимом BlackWall")


@app.get("/api/contracts")
async def list_open_contracts(x_telegram_id: Optional[int] = Header(None)):
    conn = get_conn()
    c = conn.cursor()
    _check_blackwall(c, x_telegram_id)
    c.execute(
        '''SELECT id, title, description, category, reward_stars, fee_stars,
                  creator_telegram_id, assignee_telegram_id, status,
                  is_suspicious, suspicious_reason,
                  created_at, accepted_at, completed_at, cancelled_at, disputed_at
           FROM contracts
           WHERE status='open'
           ORDER BY created_at DESC
           LIMIT 50''',
    )
    rows = c.fetchall()
    result = []
    for row in rows:
        cn, an, ca, aa = _resolve_names(c, row[6], row[7])
        result.append(_contract_to_dict(row, cn, an, ca, aa, x_telegram_id))
    conn.close()
    return result


@app.get("/api/contracts/my")
async def my_contracts(x_telegram_id: Optional[int] = Header(None)):
    if not x_telegram_id:
        raise HTTPException(status_code=401, detail="Not authorized")
    conn = get_conn()
    c = conn.cursor()
    _check_blackwall(c, x_telegram_id)
    c.execute(
        '''SELECT id, title, description, category, reward_stars, fee_stars,
                  creator_telegram_id, assignee_telegram_id, status,
                  is_suspicious, suspicious_reason,
                  created_at, accepted_at, completed_at, cancelled_at, disputed_at
           FROM contracts
           WHERE creator_telegram_id=? OR assignee_telegram_id=?
           ORDER BY created_at DESC
           LIMIT 100''',
        (x_telegram_id, x_telegram_id),
    )
    rows = c.fetchall()
    result = []
    for row in rows:
        cn, an, ca, aa = _resolve_names(c, row[6], row[7])
        result.append(_contract_to_dict(row, cn, an, ca, aa, x_telegram_id))
    conn.close()
    return result


@app.post("/api/contracts")
async def create_contract(data: dict, x_telegram_id: Optional[int] = Header(None)):
    if not x_telegram_id:
        raise HTTPException(status_code=401, detail="Not authorized")

    title = str(data.get("title") or "").strip()
    description = str(data.get("description") or "").strip()
    category = str(data.get("category") or "other").strip()
    try:
        reward = int(data.get("reward_stars"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Укажи сумму награды")

    if len(title) < 3:
        raise HTTPException(status_code=400, detail="Название слишком короткое (минимум 3 символа)")
    if len(description) < 5:
        raise HTTPException(status_code=400, detail="Описание слишком короткое (минимум 5 символов)")
    if category not in CONTRACT_CATEGORIES:
        raise HTTPException(status_code=400, detail="Недопустимая категория")
    creator_is_admin = x_telegram_id in ADMIN_IDS
    max_reward = CONTRACT_ADMIN_MAX_REWARD if creator_is_admin else CONTRACT_MAX_REWARD
    if reward < CONTRACT_MIN_REWARD or reward > max_reward:
        raise HTTPException(status_code=400, detail=f"Награда: от {CONTRACT_MIN_REWARD} до {max_reward} ★")

    fee = compute_contract_fee(reward)
    conn = get_conn()
    c = conn.cursor()
    _check_blackwall(c, x_telegram_id)

    c.execute("SELECT points FROM users WHERE telegram_id=?", (x_telegram_id,))
    user = c.fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    if (user[0] or 0) < reward:
        conn.close()
        raise HTTPException(status_code=400, detail="Недостаточно ★ для создания контракта")

    c.execute(
        "SELECT COUNT(*) FROM contracts WHERE creator_telegram_id=? AND status IN ('open','accepted')",
        (x_telegram_id,),
    )
    if (c.fetchone()[0] or 0) >= CONTRACT_MAX_ACTIVE:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Максимум {CONTRACT_MAX_ACTIVE} активных контракта одновременно")

    today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
    c.execute(
        "SELECT COALESCE(SUM(reward_stars),0) FROM contracts WHERE creator_telegram_id=? AND date(created_at)=?",
        (x_telegram_id, today),
    )
    if ((c.fetchone()[0] or 0) + reward) > CONTRACT_MAX_DAILY_SPEND:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Дневной лимит расходов через контракты: {CONTRACT_MAX_DAILY_SPEND} ★")

    is_susp, susp_reason = detect_suspicious(c, x_telegram_id, reward, title, description, category)
    now_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')

    c.execute("UPDATE users SET points = points - ? WHERE telegram_id=?", (reward, x_telegram_id))
    c.execute("SELECT points FROM users WHERE telegram_id=?", (x_telegram_id,))
    balance_after = c.fetchone()[0] or 0

    c.execute(
        '''INSERT INTO contracts
           (title, description, category, reward_stars, fee_stars,
            creator_telegram_id, status, is_suspicious, suspicious_reason, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)''',
        (title, description, category, reward, fee, x_telegram_id, int(is_susp), susp_reason, now_str),
    )
    contract_id = c.lastrowid
    log_economy(c, x_telegram_id, 'contract_freeze', -reward, balance_after,
                contract_id, 'contract', f"Заморозка: контракт #{contract_id}")
    conn.commit()
    conn.close()
    return {"success": True, "id": contract_id, "fee_stars": fee, "payout_stars": reward - fee}


@app.post("/api/contracts/{contract_id}/accept")
async def accept_contract(contract_id: int, x_telegram_id: Optional[int] = Header(None)):
    if not x_telegram_id:
        raise HTTPException(status_code=401, detail="Not authorized")
    conn = get_conn()
    c = conn.cursor()
    _check_blackwall(c, x_telegram_id)
    row = get_contract_row(c, contract_id)
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Контракт не найден")
    creator_id, reward, status = row[6], row[4], row[8]
    if status != 'open':
        conn.close()
        raise HTTPException(status_code=400, detail="Контракт недоступен для принятия")
    if creator_id == x_telegram_id:
        conn.close()
        raise HTTPException(status_code=400, detail="Нельзя принять собственный контракт")

    today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
    c.execute(
        "SELECT COUNT(*) FROM contracts WHERE assignee_telegram_id=? AND status='completed' AND date(completed_at)=?",
        (x_telegram_id, today),
    )
    if (c.fetchone()[0] or 0) >= CONTRACT_MAX_COMPLETED_PER_DAY:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Дневной лимит выполненных контрактов: {CONTRACT_MAX_COMPLETED_PER_DAY}")

    c.execute(
        "SELECT COALESCE(SUM(reward_stars-fee_stars),0) FROM contracts WHERE assignee_telegram_id=? AND status='completed' AND date(completed_at)=?",
        (x_telegram_id, today),
    )
    today_earn = c.fetchone()[0] or 0
    payout = reward - compute_contract_fee(reward)
    if today_earn + payout > CONTRACT_MAX_DAILY_EARN:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Дневной лимит заработка: {CONTRACT_MAX_DAILY_EARN} ★")

    now_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
    c.execute(
        "UPDATE contracts SET status='accepted', assignee_telegram_id=?, accepted_at=? WHERE id=?",
        (x_telegram_id, now_str, contract_id),
    )
    log_economy(c, x_telegram_id, 'contract_accept', 0, None, contract_id, 'contract',
                f"Принят контракт #{contract_id}")
    conn.commit()
    conn.close()
    return {"success": True}


@app.post("/api/contracts/{contract_id}/complete")
async def complete_contract(contract_id: int,
                             x_telegram_id: Optional[int] = Header(None),
                             x_admin_id: Optional[int] = Header(None)):
    acting_id = x_admin_id if (x_admin_id and x_admin_id in ADMIN_IDS) else x_telegram_id
    if not acting_id:
        raise HTTPException(status_code=401, detail="Not authorized")
    conn = get_conn()
    c = conn.cursor()
    row = get_contract_row(c, contract_id)
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Контракт не найден")
    creator_id, assignee_id, reward, fee, status, accepted_at = row[6], row[7], row[4], row[5], row[8], row[12]
    is_susp, susp_reason = bool(row[9]), row[10]
    if status != 'accepted':
        conn.close()
        raise HTTPException(status_code=400, detail="Можно завершить только принятый контракт")
    if x_admin_id not in ADMIN_IDS and acting_id != creator_id:
        conn.close()
        raise HTTPException(status_code=403, detail="Только заказчик или администратор может подтвердить выполнение")

    now = datetime.now(BEIJING_TZ)
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')
    if accepted_at:
        try:
            accepted_dt = datetime.strptime(accepted_at, '%Y-%m-%d %H:%M:%S')
            elapsed = (now.replace(tzinfo=None) - accepted_dt).total_seconds()
            if elapsed < CONTRACT_MIN_COMPLETE_SECONDS:
                new_reason = ((susp_reason or '') + '; слишком быстрое завершение').lstrip('; ')
                c.execute("UPDATE contracts SET is_suspicious=1, suspicious_reason=? WHERE id=?",
                          (new_reason, contract_id))
        except Exception:
            pass

    payout = reward - fee
    c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (payout, assignee_id))
    c.execute("SELECT points FROM users WHERE telegram_id=?", (assignee_id,))
    assignee_bal = c.fetchone()[0] or 0
    c.execute("UPDATE contracts SET status='completed', completed_at=? WHERE id=?", (now_str, contract_id))
    log_economy(c, assignee_id, 'contract_payout', payout, assignee_bal, contract_id, 'contract',
                f"Выплата за контракт #{contract_id}")
    log_economy(c, creator_id, 'contract_fee_burn', -fee, None, contract_id, 'contract',
                f"Комиссия Сетевого Дозора: контракт #{contract_id}")
    conn.commit()
    conn.close()
    return {"success": True, "payout": payout, "fee_burned": fee}


@app.post("/api/contracts/{contract_id}/cancel")
async def cancel_contract(contract_id: int,
                           x_telegram_id: Optional[int] = Header(None),
                           x_admin_id: Optional[int] = Header(None)):
    acting_id = x_admin_id if (x_admin_id and x_admin_id in ADMIN_IDS) else x_telegram_id
    if not acting_id:
        raise HTTPException(status_code=401, detail="Not authorized")
    conn = get_conn()
    c = conn.cursor()
    row = get_contract_row(c, contract_id)
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Контракт не найден")
    creator_id, reward, status = row[6], row[4], row[8]
    if status not in ('open', 'accepted', 'disputed'):
        conn.close()
        raise HTTPException(status_code=400, detail="Контракт нельзя отменить в текущем статусе")
    if status == 'open' and acting_id != creator_id and x_admin_id not in ADMIN_IDS:
        conn.close()
        raise HTTPException(status_code=403, detail="Только заказчик может отменить открытый контракт")
    if status in ('accepted', 'disputed') and x_admin_id not in ADMIN_IDS:
        conn.close()
        raise HTTPException(status_code=403, detail="Только администратор может отменить принятый контракт")

    now_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
    c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (reward, creator_id))
    c.execute("SELECT points FROM users WHERE telegram_id=?", (creator_id,))
    bal = c.fetchone()[0] or 0
    c.execute("UPDATE contracts SET status='cancelled', cancelled_at=? WHERE id=?", (now_str, contract_id))
    log_economy(c, creator_id, 'contract_refund', reward, bal, contract_id, 'contract',
                f"Возврат: контракт #{contract_id} отменён")
    conn.commit()
    conn.close()
    return {"success": True, "refunded": reward}


@app.post("/api/contracts/{contract_id}/dispute")
async def dispute_contract(contract_id: int,
                            x_telegram_id: Optional[int] = Header(None),
                            x_admin_id: Optional[int] = Header(None)):
    acting_id = x_admin_id if (x_admin_id and x_admin_id in ADMIN_IDS) else x_telegram_id
    if not acting_id:
        raise HTTPException(status_code=401, detail="Not authorized")
    conn = get_conn()
    c = conn.cursor()
    row = get_contract_row(c, contract_id)
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Контракт не найден")
    creator_id, assignee_id, status = row[6], row[7], row[8]
    if status != 'accepted':
        conn.close()
        raise HTTPException(status_code=400, detail="Спор можно открыть только для принятого контракта")
    if acting_id not in (creator_id, assignee_id) and x_admin_id not in ADMIN_IDS:
        conn.close()
        raise HTTPException(status_code=403, detail="Только участники контракта могут открыть спор")
    now_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
    c.execute("UPDATE contracts SET status='disputed', disputed_at=? WHERE id=?", (now_str, contract_id))
    log_economy(c, acting_id, 'contract_dispute', 0, None, contract_id, 'contract',
                f"Открыт спор: контракт #{contract_id}")
    conn.commit()
    conn.close()
    return {"success": True}


@app.get("/api/admin/contracts")
async def admin_list_contracts(x_admin_id: Optional[int] = Header(None),
                                status: Optional[str] = None):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = get_conn()
    c = conn.cursor()
    if status:
        c.execute(
            '''SELECT c.id, c.title, c.description, c.category, c.reward_stars, c.fee_stars,
                      c.creator_telegram_id, c.assignee_telegram_id, c.status,
                      c.is_suspicious, c.suspicious_reason,
                      c.created_at, c.accepted_at, c.completed_at, c.cancelled_at, c.disputed_at,
                      u1.full_name, u2.full_name, u1.avatar_url, u2.avatar_url
               FROM contracts c
               LEFT JOIN users u1 ON u1.telegram_id=c.creator_telegram_id
               LEFT JOIN users u2 ON u2.telegram_id=c.assignee_telegram_id
               WHERE c.status=?
               ORDER BY c.created_at DESC LIMIT 100''',
            (status,),
        )
    else:
        c.execute(
            '''SELECT c.id, c.title, c.description, c.category, c.reward_stars, c.fee_stars,
                      c.creator_telegram_id, c.assignee_telegram_id, c.status,
                      c.is_suspicious, c.suspicious_reason,
                      c.created_at, c.accepted_at, c.completed_at, c.cancelled_at, c.disputed_at,
                      u1.full_name, u2.full_name, u1.avatar_url, u2.avatar_url
               FROM contracts c
               LEFT JOIN users u1 ON u1.telegram_id=c.creator_telegram_id
               LEFT JOIN users u2 ON u2.telegram_id=c.assignee_telegram_id
               ORDER BY c.created_at DESC LIMIT 100''',
        )
    rows = c.fetchall()
    conn.close()
    return [
        {**_contract_to_dict(row[:16], row[16], row[17], row[18], row[19]),
         "creator_name": row[16], "assignee_name": row[17],
         "creator_avatar_url": row[18], "assignee_avatar_url": row[19]}
        for row in rows
    ]


@app.get("/api/admin/contracts/monitor")
async def admin_contract_monitor(x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = get_conn()
    c = conn.cursor()

    c.execute(
        '''SELECT status, COUNT(*), COALESCE(SUM(reward_stars),0),
                  COALESCE(SUM(CASE WHEN status='completed' THEN fee_stars ELSE 0 END),0)
           FROM contracts
           GROUP BY status'''
    )
    status_rows = c.fetchall()
    status_counts = {row[0]: row[1] for row in status_rows}
    reward_by_status = {row[0]: row[2] for row in status_rows}
    fee_burned = sum(row[3] or 0 for row in status_rows)

    c.execute("SELECT COUNT(*), COALESCE(SUM(reward_stars),0) FROM contracts")
    total_count, total_turnover = c.fetchone()
    c.execute("SELECT COUNT(*) FROM contracts WHERE is_suspicious=1")
    suspicious_count = c.fetchone()[0] or 0

    c.execute(
        '''SELECT c.creator_telegram_id, c.assignee_telegram_id,
                  COALESCE(u1.full_name, c.creator_telegram_id),
                  COALESCE(u2.full_name, c.assignee_telegram_id),
                  COUNT(*) AS contract_count,
                  COALESCE(SUM(c.reward_stars),0) AS reward_total,
                  COALESCE(SUM(CASE WHEN c.status='completed' THEN c.reward_stars-c.fee_stars ELSE 0 END),0) AS payout_total,
                  COALESCE(SUM(CASE WHEN c.status='completed' THEN c.fee_stars ELSE 0 END),0) AS fee_total,
                  COALESCE(SUM(CASE WHEN c.is_suspicious=1 THEN 1 ELSE 0 END),0) AS suspicious_total,
                  COALESCE(SUM(CASE WHEN c.status='disputed' THEN 1 ELSE 0 END),0) AS disputed_total,
                  MAX(c.created_at) AS last_at
           FROM contracts c
           LEFT JOIN users u1 ON u1.telegram_id=c.creator_telegram_id
           LEFT JOIN users u2 ON u2.telegram_id=c.assignee_telegram_id
           WHERE c.assignee_telegram_id IS NOT NULL
           GROUP BY c.creator_telegram_id, c.assignee_telegram_id
           ORDER BY reward_total DESC, contract_count DESC
           LIMIT 30'''
    )
    contract_pairs = []
    for row in c.fetchall():
        flags = []
        if (row[4] or 0) >= 3:
            flags.append("частые контракты")
        if (row[5] or 0) >= 100:
            flags.append("крупный оборот")
        if (row[8] or 0) > 0:
            flags.append("подозрительные")
        if (row[9] or 0) > 0:
            flags.append("есть спор")
        contract_pairs.append({
            "creator_id": row[0],
            "assignee_id": row[1],
            "creator_name": str(row[2]),
            "assignee_name": str(row[3]),
            "count": row[4] or 0,
            "reward_total": row[5] or 0,
            "payout_total": row[6] or 0,
            "fee_total": row[7] or 0,
            "suspicious": row[8] or 0,
            "disputed": row[9] or 0,
            "last_at": row[10],
            "flags": flags,
        })

    c.execute(
        '''SELECT sp.given_to, sp.telegram_id,
                  COALESCE(uf.full_name, sp.given_to),
                  COALESCE(ut.full_name, sp.telegram_id),
                  COUNT(*) AS gift_count,
                  COALESCE(SUM(si.price),0) AS item_value,
                  MAX(COALESCE(sp.gifted_at, sp.purchased_at)) AS last_at
           FROM shop_purchases sp
           LEFT JOIN shop_items si ON si.code=sp.item_code
           LEFT JOIN users uf ON uf.telegram_id=sp.given_to
           LEFT JOIN users ut ON ut.telegram_id=sp.telegram_id
           WHERE sp.given_to IS NOT NULL
           GROUP BY sp.given_to, sp.telegram_id
           ORDER BY item_value DESC, gift_count DESC
           LIMIT 30'''
    )
    gift_pairs = []
    for row in c.fetchall():
        flags = []
        if (row[4] or 0) >= 2:
            flags.append("повторные подарки")
        if (row[5] or 0) >= 100:
            flags.append("ценные предметы")
        gift_pairs.append({
            "from_id": row[0],
            "to_id": row[1],
            "from_name": str(row[2]),
            "to_name": str(row[3]),
            "count": row[4] or 0,
            "item_value": row[5] or 0,
            "last_at": row[6],
            "flags": flags,
        })

    c.execute(
        '''SELECT sp.id, sp.given_to, sp.telegram_id,
                  COALESCE(uf.full_name, sp.given_to),
                  COALESCE(ut.full_name, sp.telegram_id),
                  sp.item_code, COALESCE(si.name, sp.item_code), COALESCE(si.price,0),
                  COALESCE(sp.gifted_at, sp.purchased_at)
           FROM shop_purchases sp
           LEFT JOIN shop_items si ON si.code=sp.item_code
           LEFT JOIN users uf ON uf.telegram_id=sp.given_to
           LEFT JOIN users ut ON ut.telegram_id=sp.telegram_id
           WHERE sp.given_to IS NOT NULL
           ORDER BY COALESCE(sp.gifted_at, sp.purchased_at) DESC
           LIMIT 50'''
    )
    recent_gifts = [{
        "id": row[0],
        "from_id": row[1],
        "to_id": row[2],
        "from_name": str(row[3]),
        "to_name": str(row[4]),
        "item_code": row[5],
        "item_name": row[6],
        "item_price": row[7] or 0,
        "gifted_at": row[8],
    } for row in c.fetchall()]

    contract_pair_keys = {tuple(sorted((p["creator_id"], p["assignee_id"]))) for p in contract_pairs}
    gift_pair_keys = {tuple(sorted((p["from_id"], p["to_id"]))) for p in gift_pairs}

    conn.close()
    return {
        "summary": {
            "total_contracts": total_count or 0,
            "total_turnover": total_turnover or 0,
            "fee_burned": fee_burned,
            "suspicious": suspicious_count,
            "status_counts": status_counts,
            "reward_by_status": reward_by_status,
            "gift_pairs": len(gift_pairs),
            "cross_pairs": len(contract_pair_keys & gift_pair_keys),
        },
        "contract_pairs": contract_pairs,
        "gift_pairs": gift_pairs,
        "recent_gifts": recent_gifts,
    }


@app.post("/api/admin/contracts/{contract_id}/resolve")
async def admin_resolve_contract(contract_id: int, data: dict,
                                  x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")
    action = str(data.get("action") or "").strip()
    if action not in ('refund_creator', 'pay_assignee', 'split', 'cancel_no_refund', 'remove'):
        raise HTTPException(status_code=400, detail="Invalid action")
    conn = get_conn()
    c = conn.cursor()
    row = get_contract_row(c, contract_id)
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Контракт не найден")
    creator_id, assignee_id, reward, fee, status = row[6], row[7], row[4], row[5], row[8]
    if status in ('completed', 'cancelled') and action != 'remove':
        conn.close()
        raise HTTPException(status_code=400, detail="Контракт уже завершён")

    now_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
    payout = reward - fee

    if action == 'refund_creator':
        c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (reward, creator_id))
        c.execute("SELECT points FROM users WHERE telegram_id=?", (creator_id,))
        bal = c.fetchone()[0] or 0
        c.execute("UPDATE contracts SET status='cancelled', cancelled_at=? WHERE id=?", (now_str, contract_id))
        log_economy(c, creator_id, 'contract_admin_refund', reward, bal, contract_id, 'contract',
                    f"Решение админа: возврат заказчику #{contract_id}")

    elif action == 'pay_assignee':
        if not assignee_id:
            conn.close()
            raise HTTPException(status_code=400, detail="Нет исполнителя")
        c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (payout, assignee_id))
        c.execute("SELECT points FROM users WHERE telegram_id=?", (assignee_id,))
        bal = c.fetchone()[0] or 0
        c.execute("UPDATE contracts SET status='completed', completed_at=? WHERE id=?", (now_str, contract_id))
        log_economy(c, assignee_id, 'contract_admin_pay', payout, bal, contract_id, 'contract',
                    f"Решение админа: выплата исполнителю #{contract_id}")
        log_economy(c, creator_id, 'contract_fee_burn', -fee, None, contract_id, 'contract',
                    f"Комиссия Сетевого Дозора: #{contract_id}")

    elif action == 'split':
        if not assignee_id:
            conn.close()
            raise HTTPException(status_code=400, detail="Нет исполнителя")
        half = reward // 2
        c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (half, creator_id))
        c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (reward - half, assignee_id))
        c.execute("UPDATE contracts SET status='cancelled', cancelled_at=? WHERE id=?", (now_str, contract_id))
        log_economy(c, creator_id, 'contract_admin_split', half, None, contract_id, 'contract',
                    f"Решение админа: раздел #{contract_id}")
        log_economy(c, assignee_id, 'contract_admin_split', reward - half, None, contract_id, 'contract',
                    f"Решение админа: раздел #{contract_id}")

    elif action == 'cancel_no_refund':
        c.execute("UPDATE contracts SET status='cancelled', cancelled_at=? WHERE id=?", (now_str, contract_id))
        log_economy(c, creator_id, 'contract_admin_burn', -reward, None, contract_id, 'contract',
                    f"Решение админа: сгорание без возврата #{contract_id}")

    elif action == 'remove':
        if status in ('open', 'accepted', 'disputed'):
            c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (reward, creator_id))
            log_economy(c, creator_id, 'contract_admin_refund', reward, None, contract_id, 'contract',
                        f"Возврат при удалении контракта #{contract_id}")
        c.execute("DELETE FROM contracts WHERE id=?", (contract_id,))
        conn.commit()
        conn.close()
        return {"success": True, "action": action}

    conn.commit()
    conn.close()
    return {"success": True, "action": action}
