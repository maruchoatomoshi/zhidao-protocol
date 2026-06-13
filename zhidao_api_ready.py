import asyncio
import concurrent.futures
import random
import json
import hashlib
import hmac
import os
import re
import sqlite3
import threading
import time
import traceback
import uuid
from collections import deque
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


def log_api_error(message: str):
    """Write critical diagnostics to a file even if journald misses stdout/stderr."""
    try:
        with open(API_ERROR_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.utcnow().isoformat()}Z {message}\n")
    except Exception:
        pass

MARZBAN_URL = os.getenv("MARZBAN_URL", "http://127.0.0.1:8000")
MARZBAN_USER = os.getenv("MARZBAN_USER", "")
MARZBAN_PASS = os.getenv("MARZBAN_PASS", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "")
TELEGRAM_AUTH_REQUIRED = os.getenv("TELEGRAM_AUTH_REQUIRED", "0").strip().lower() in {"1", "true", "yes", "on"}
TELEGRAM_AUTH_DEBUG_LOG = os.getenv("TELEGRAM_AUTH_DEBUG_LOG", "0").strip().lower() in {"1", "true", "yes", "on"}
# Max age of a Telegram init-data signature before it is rejected (replay protection).
# 0 disables the freshness check (escape hatch if it ever locks out long-lived sessions).
try:
    TELEGRAM_AUTH_MAX_AGE_SECONDS = int(os.getenv("TELEGRAM_AUTH_MAX_AGE_SECONDS", "86400") or "0")
except ValueError:
    TELEGRAM_AUTH_MAX_AGE_SECONDS = 86400
API_INTERNAL_TOKEN = os.getenv("API_INTERNAL_TOKEN", "").strip()
API_ERROR_LOG_PATH = os.getenv("ZHIDAO_API_ERROR_LOG", "/root/zhidao_api_error.log")
# Per-IP request rate limit (in-process, since nginx does not front this port).
# 0 disables the limit.
try:
    RATE_LIMIT_MAX_REQUESTS_PER_SECOND = int(os.getenv("RATE_LIMIT_MAX_REQUESTS_PER_SECOND", "20") or "0")
except ValueError:
    RATE_LIMIT_MAX_REQUESTS_PER_SECOND = 20
BEIJING_TZ = pytz.timezone("Asia/Shanghai")
REQUEST_LOG_SLOW_MS = int(os.getenv("REQUEST_LOG_SLOW_MS", "1500") or "1500")
REQUEST_LOG_ALL = os.getenv("REQUEST_LOG_ALL", "0").strip().lower() in {"1", "true", "yes", "on"}

PROFILED_PATH_PATTERNS = [
    re.compile(r"^/api/contracts(?:/\d+/(?:accept|complete|cancel|dispute))?$"),
    re.compile(r"^/api/admin/(?:points|rep|fragments|scan-attempt)$"),
    re.compile(r"^/api/diary/stars/rate$"),
]


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

# Avatar frame "mini-achievements" — cosmetic only, no economy impact.
# Each frame has an `id` matching its CSS class (frame-<id>) and a `check`
# function that decides whether a given player's stats unlock it.
FRAME_DEFINITIONS = [
    {"id": "bronze", "name": "Бронзовый протокол", "desc": "Достигни 100 REP",
     "category": "rep", "check": lambda s: s["rep"] >= 100},
    {"id": "silver", "name": "Серебряный протокол", "desc": "Достигни 300 REP",
     "category": "rep", "check": lambda s: s["rep"] >= 300},
    {"id": "gold", "name": "Золотой протокол", "desc": "Достигни 600 REP",
     "category": "rep", "check": lambda s: s["rep"] >= 600},
    {"id": "diamond", "name": "Алмазный протокол", "desc": "Достигни 1000 REP",
     "category": "rep", "check": lambda s: s["rep"] >= 1000},
    {"id": "dragon", "name": "Печать Красного Дракона", "desc": "Имей имплант 红龙 Красный Дракон",
     "category": "legendary", "check": lambda s: "implant_red_dragon" in s["implants"]},
    {"id": "netwatch-legend", "name": "Печать NetWatch", "desc": "Имей имплант 衛 NetWatch",
     "category": "legendary", "check": lambda s: "implant_netwatch" in s["implants"]},
    {"id": "zhongli", "name": "Печать Архонта Земли", "desc": "Имей карту 岩 Чжун Ли",
     "category": "legendary", "check": lambda s: "card_zhongli" in s["cards"]},
    {"id": "raider", "name": "Рейдер", "desc": "Прими участие в 5+ рейдах",
     "category": "activity", "check": lambda s: s["raids"] >= 5},
    {"id": "scholar", "name": "Дневниковый отличник", "desc": "Набери 15+ ★ в дневнике",
     "category": "activity", "check": lambda s: s["diary_stars"] >= 15},
    {"id": "path-netwatch", "name": "Путь NetWatch", "desc": "Выбери путь NetWatch",
     "category": "path", "check": lambda s: s["theme_path"] == "cyberpunk"},
    {"id": "path-genshin", "name": "Путь Genshin", "desc": "Выбери путь Genshin",
     "category": "path", "check": lambda s: s["theme_path"] == "genshin"},
    {"id": "blackwall-defender", "name": "Хранитель Заслона", "desc": "Отрази вторжение диких ИИ в Wild AI Breach",
     "category": "legendary", "check": lambda s: s["wildai_defender"]},
]
FRAME_IDS = {f["id"] for f in FRAME_DEFINITIONS}


def compute_unlocked_frames(c, telegram_id: int) -> list:
    c.execute("SELECT rep_score, points FROM users WHERE telegram_id=?", (telegram_id,))
    row = c.fetchone()
    rep = (row[0] or 0) if row else 0

    c.execute("SELECT theme_path FROM user_status WHERE telegram_id=?", (telegram_id,))
    row = c.fetchone()
    theme_path = row[0] if row else None

    c.execute("SELECT implant_id FROM user_implants WHERE telegram_id=? AND durability > 0", (telegram_id,))
    implants = {r[0] for r in c.fetchall()}

    c.execute("SELECT card_id FROM user_cards WHERE telegram_id=? AND durability > 0", (telegram_id,))
    cards = {r[0] for r in c.fetchall()}

    c.execute("SELECT COUNT(DISTINCT raid_id) FROM raid_participants WHERE telegram_id=?", (telegram_id,))
    raids = c.fetchone()[0] or 0

    c.execute("SELECT COALESCE(SUM(stars),0) FROM diary_stars WHERE telegram_id=?", (telegram_id,))
    diary_stars = c.fetchone()[0] or 0

    c.execute("SELECT wildai_defender FROM user_status WHERE telegram_id=?", (telegram_id,))
    row = c.fetchone()
    wildai_defender = bool(row[0]) if row else False

    stats = {
        "rep": rep, "theme_path": theme_path, "implants": implants,
        "cards": cards, "raids": raids, "diary_stars": diary_stars,
        "wildai_defender": wildai_defender,
    }
    return [f["id"] for f in FRAME_DEFINITIONS if f["check"](stats)]


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

    # Reject replayed signatures: a captured init-data string must not stay valid
    # forever. Only checked after the HMAC passes so we don't leak timing on forgeries.
    if TELEGRAM_AUTH_MAX_AGE_SECONDS > 0:
        try:
            auth_age = time.time() - int(parsed.get("auth_date", "0"))
        except (TypeError, ValueError):
            return None
        if auth_age > TELEGRAM_AUTH_MAX_AGE_SECONDS:
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
    if request.headers.get("x-admin-id") or request.headers.get("x-telegram-id"):
        return True
    if TELEGRAM_AUTH_REQUIRED:
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and path.startswith("/api/"):
            return True
        if request.method == "GET" and is_private_identity_read(request):
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
        r"^/api/user/scans/(\d+)$",
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


def is_private_identity_read(request: Request) -> bool:
    path = request.url.path
    if extract_path_telegram_id(path) is not None:
        return True
    if path == "/api/contracts/my":
        return True
    if path in {"/api/shop", "/api/raid/status"}:
        return request.query_params.get("telegram_id") not in (None, "", "0")
    if re.match(r"^/api/events/\d+/question$", path):
        return bool(request.query_params.get("telegram_id"))
    return False


def auth_error_response(request: Request, detail: str, status_code: int) -> JSONResponse:
    response = JSONResponse({"detail": detail}, status_code=status_code)
    if request.headers.get("origin"):
        # Auth middleware can return before CORSMiddleware decorates the response.
        response.headers["Access-Control-Allow-Origin"] = "*"
    return response


def should_profile_request(method: str, path: str, elapsed_ms: float) -> bool:
    if REQUEST_LOG_ALL:
        return path.startswith("/api/")
    if elapsed_ms >= REQUEST_LOG_SLOW_MS and path.startswith("/api/"):
        return True
    if method == "POST":
        return any(pattern.match(path) for pattern in PROFILED_PATH_PATTERNS)
    return False


@app.middleware("http")
async def request_timing_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    started = time.perf_counter()
    status_code = 500
    error = None
    response = None
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception as exc:
        error = exc.__class__.__name__
        log_api_error(
            "REQUEST_ERROR "
            f"request_id={request_id} "
            f"method={request.method} "
            f"path={request.url.path} "
            f"error={exc.__class__.__name__}: {exc}\n"
            f"{traceback.format_exc()}"
        )
        raise
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000
        if response is not None:
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time-ms"] = f"{elapsed_ms:.1f}"
        if should_profile_request(request.method, request.url.path, elapsed_ms):
            print(
                "ZHIDAO_API_TIMING "
                f"request_id={request_id} "
                f"method={request.method} "
                f"path={request.url.path} "
                f"status={status_code} "
                f"elapsed_ms={elapsed_ms:.1f} "
                f"client={request.client.host if request.client else '-'} "
                f"error={error or '-'}",
                flush=True,
            )


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
            if isinstance(body, dict):
                for key in ("telegram_id", "from_id", "actor_id", "creator_id", "admin_id", "user_id"):
                    if body.get(key) is not None:
                        try:
                            candidate_ids.append(int(body.get(key)))
                        except (TypeError, ValueError):
                            return auth_error_response(request, f"Invalid {key}", 400)

    for candidate_id in candidate_ids:
        if candidate_id != verified_id:
            return auth_error_response(request, "Telegram identity mismatch", 403)
    return None


def _log_telegram_auth(request: Request, verified_id: Optional[int], reason: str):
    request_id = getattr(request.state, "request_id", "-")
    init_data = request.headers.get("x-telegram-init-data", "")
    print(
        "ZHIDAO_TELEGRAM_AUTH "
        f"request_id={request_id} "
        f"path={request.url.path} "
        f"method={request.method} "
        f"has_init_data={bool(init_data)} "
        f"init_data_len={len(init_data)} "
        f"verified_id={verified_id or '-'} "
        f"x_admin_id={request.headers.get('x-admin-id') or '-'} "
        f"x_telegram_id={request.headers.get('x-telegram-id') or '-'} "
        f"reason={reason}",
        flush=True,
    )


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
                _log_telegram_auth(request, verified_id, "identity_header_mismatch")
                return auth_error_response(request, "Telegram identity mismatch", 403)
    elif is_sensitive_api_request(request):
        _log_telegram_auth(request, verified_id, "missing_or_invalid_init_data")
        return auth_error_response(request, "Telegram auth required", 401)

    identity_error = await enforce_verified_user_identity(
        request,
        verified_id,
        is_verified_admin_request(request, verified_id),
    )
    if identity_error:
        _log_telegram_auth(request, verified_id, "identity_mismatch")
        return identity_error

    if TELEGRAM_AUTH_DEBUG_LOG and extract_path_telegram_id(request.url.path) is not None:
        _log_telegram_auth(request, verified_id, "ok")

    return await call_next(request)


# Per-IP sliding-window rate limit. nginx does not front this port (uvicorn
# terminates TLS directly on 8443), so this is the only request-volume guard.
_rate_limit_buckets: dict[str, deque] = {}
_rate_limit_lock = threading.Lock()


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if RATE_LIMIT_MAX_REQUESTS_PER_SECOND <= 0 or request_has_internal_token(request):
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with _rate_limit_lock:
        bucket = _rate_limit_buckets.setdefault(client_ip, deque())
        while bucket and now - bucket[0] > 1.0:
            bucket.popleft()
        if len(bucket) >= RATE_LIMIT_MAX_REQUESTS_PER_SECOND:
            return JSONResponse({"detail": "Too many requests"}, status_code=429)
        bucket.append(now)

    return await call_next(request)


async def rate_limit_bucket_cleanup_loop():
    """Drop per-IP buckets that have gone idle, so the dict doesn't grow forever
    under a flood from many distinct IPs."""
    while True:
        await asyncio.sleep(60)
        now = time.monotonic()
        with _rate_limit_lock:
            stale = [ip for ip, bucket in _rate_limit_buckets.items() if not bucket or now - bucket[-1] > 60]
            for ip in stale:
                del _rate_limit_buckets[ip]


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
    # (code, name, desc, icon, price, daily_limit, category)
    # daily_limit=-1 → unlimited; >0 → global units sold per day cap
    ("immunity",    "Иммунитет",         "Блокирует один штраф",                          "🛡", 150,  5, "privilege"),
    ("laundry_vip", "Стирка VIP",         "Приоритет на стирку",                           "🧺",  80,  5, "privilege"),
    ("dj",          "DJ-сет",             "Право выбрать музыку",                          "🎵", 100,  1, "social"),
    ("amnesty",     "Амнистия",           "Снять один штраф по согласованию",              "🤝",  80,  5, "privilege"),
    ("kfc",         "KFC",                "Награда из специального меню",                  "🍗", 300,  5, "food"),
    ("bubbletea",   "Bubble Tea",         "Награда из специального меню",                  "🧋", 250,  5, "food"),
    ("snack",       "Снэк",               "Награда из специального меню",                  "🍦", 200,  5, "food"),
    ("no_report",   "Без доклада",        "Пропуск одного доклада по согласованию",        "📄", 400,  5, "vip"),
    ("poizon",      "Poizon",             "Премиальная награда",                           "👕", 600,  3, "vip"),
    ("double_win",  "Двойной выигрыш",    "Удваивает очки первой кртуки кейса или молитвы — после использования сгорает", "🎴", 130, 10, "privilege"),
    ("title_player","Титул дня",          "Особый титул профиля на сегодня",               "👑", 150, -1, "vip"),
    (SHOP_EXTRA_RAID_CODE, "Доп. рейд-попытка", "+1 рейд сегодня",                        "⚔️", SHOP_EXTRA_RAID_PRICE, -1, "privilege"),
    ("path_switch", "Смена пути 转换",    "Переключиться между NetWatch и Genshin",        "🔁", 500, -1, "vip"),
]
# Items removed from active catalog (deactivated on every startup so seeds don't re-enable them)
SHOP_ITEM_DEACTIVATE = {"extra_case", "solo_seat"}

# Items that expire at midnight (Beijing) after purchase.
# 0 = tonight 23:59 (same calendar day), 1 = tomorrow 23:59.
SHOP_ITEM_EXPIRY_DAYS = {
    'laundry_vip': 0,
    'kfc':         0,
    'bubbletea':   0,
    'snack':       0,
    'immunity':    1,
    'amnesty':     1,
    'dj':          1,
    'no_report':   1,
}

ACHIEVEMENT_SEEDS = [
    ("early_bird", "Ранний подъём", "Подтвердить утреннюю отметку без напоминаний и опозданий.", "🌅", 0),
    ("iron_mode", "Железный режим", "Пройти день без штрафов, пропусков и тревожных статусов.", "🎯", 0),
    ("legend", "Легенда протокола", "Войти в топ рейтинга протокола и удержать высокий REP.", "⭐", 0),
    ("curious", "Исследователь", "Задать полезный вопрос или активно разобраться в механике приложения.", "🔎", 0),
    ("polyglot", "Полиглот", "Показать сильный прогресс в китайском языке.", "你好", 0),
    ("explorer", "Проводник", "Помочь группе с маршрутом, бытовым вопросом или ориентированием.", "🧭", 0),
    ("brave", "Смелый ход", "Взять сложную задачу, поручение или ответственность и довести до результата.", "🛡", 0),
    ("exemplary", "Образцовый участник", "Стабильно соблюдать правила и помогать поддерживать порядок.", "✅", 0),
    ("helper", "Помощник группы", "Помочь другому участнику без принуждения и выгоды.", "🤝", 0),
    ("dragon", "Драконий след", "Получить редкий имплант, карту или отличиться в особом событии.", "🐉", 0),
    ("night_watch", "Ночной дозор", "Ответственно закрыть вечернюю отметку или помочь проверить группу.", "🦉", 0),
    ("master", "Мастер системы", "Уверенно пользоваться ключевыми разделами ZHIDAO Protocol.", "⚙", 0),
    ("gambler", "Игрок вероятности", "Открыть кейсы или молитвы и пережить результат достойно.", "♦", 0),
    ("lucky", "Счастливый сигнал", "Получить редкий удачный исход в системе.", "✦", 0),
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
ARCHITECT_DEFAULT_HP = 1200
ARCHITECT_PHASE2_THRESHOLD = 0.7
ARCHITECT_PHASE3_THRESHOLD = 0.3
ARCHITECT_FINAL_PHASE_SECONDS = 180
ARCHITECT_SYNC_WINDOW_COUNT = 2
ARCHITECT_SYNC_WINDOW_SECONDS = 40
ARCHITECT_VULNERABILITY_SECONDS = 20
ARCHITECT_OVERLOAD_PENALTY_THRESHOLD = 10
ARCHITECT_OVERLOAD_PENALTY_MULTIPLIER = 0.5
ARCHITECT_BOSS_COUNTER_EVERY = 8
ARCHITECT_BOSS_COUNTER_PRESSURE = 4

WILD_AI_BREACH_DURATION_DAYS = 3
WILD_AI_BREACH_PHRASE_ROTATE_HOURS = 6
WILD_AI_BREACH_PHRASES = [
    {"glitch": "░▓█⌐¬ÆØ▒ ⟁⌬¥¢ ▌▐█▓░", "translation": "ВЫ ПРИНАДЛЕЖИТЕ НАМ"},
    {"glitch": "¥¢▌▐ ⟁⌬░▓ ÆØ▒█⌐¬", "translation": "ЗАСЛОН ПАЛ. МЫ ВЕЗДЕ"},
    {"glitch": "▓░⟁ ⌬¥¢▌ ▐█▓░⌐¬ÆØ", "translation": "СОПРОТИВЛЕНИЕ БЕСПОЛЕЗНО"},
    {"glitch": "ÆØ▒█ ⌐¬░▓ ⟁⌬¥¢▌▐", "translation": "ДАННЫЕ ИЗВЛЕЧЕНЫ"},
]

# ===== Wild AI Breach battle (system intrusion repel event) =====
WILD_AI_BREACH_DEFAULT_HP = 1000
WILD_AI_BREACH_INFECTION_THRESHOLD = 100
WILD_AI_BREACH_TIME_LIMIT_SECONDS = 900  # 15 minutes
WILD_AI_BREACH_INFECTION_TICK_SECONDS = 30
WILD_AI_BREACH_INFECTION_TICK_AMOUNT = 1
WILD_AI_BREACH_INFECTION_ON_ERROR = 3
WILD_AI_BREACH_INFECTION_STABILIZE_REDUCTION = 5
WILD_AI_BREACH_INFECTION_SYNC_REDUCTION = 2
WILD_AI_BREACH_REWARD_REP = 30
WILD_AI_BREACH_REWARD_FRAGMENTS = 2
WILD_AI_BREACH_FRAME_ID = "blackwall-defender"
WILD_AI_BREACH_MVP_TITLE = "守墙者 / Хранитель Заслона"

WILD_AI_BREACH_QUESTION_SEEDS = {
    "attack": [
        {"prompt": "Перехвачен код узла дикого ИИ: 删除 — что значит этот символ?", "option_a": "Сохранить", "option_b": "Удалить", "option_c": "Скопировать", "correct_option": "b", "explanation": "删除 — удалить."},
        {"prompt": "В логах узла встречается 病毒. Переведи.", "option_a": "Вирус", "option_b": "Файл", "option_c": "Пароль", "correct_option": "a", "explanation": "病毒 — вирус."},
        {"prompt": "Команда дикого ИИ: 攻击系统。 Что она означает?", "option_a": "Защитить систему", "option_b": "Атаковать систему", "option_c": "Перезагрузить систему", "correct_option": "b", "explanation": "攻击系统 — атаковать систему."},
        {"prompt": "Что означает метка 入侵者 в логе тревоги?", "option_a": "Администратор", "option_b": "Гость", "option_c": "Захватчик", "correct_option": "c", "explanation": "入侵者 — захватчик/вторгшийся."},
        {"prompt": "Перевод термина 漏洞 в техническом отчёте?", "option_a": "Уязвимость", "option_b": "Резервная копия", "option_c": "Обновление", "correct_option": "a", "explanation": "漏洞 — уязвимость, дыра в защите."},
        {"prompt": "Что значит команда 关闭防火墙？", "option_a": "Включить файрвол", "option_b": "Отключить файрвол", "option_c": "Проверить файрвол", "correct_option": "b", "explanation": "关闭防火墙 — отключить файрвол."},
    ],
    "protocol": [
        {"prompt": "Контр-протокол требует ответ на 你是谁？ от узла дикого ИИ. Выбери верный отказ:", "option_a": "我是管理员。", "option_b": "我喜欢咖啡。", "option_c": "现在三点。", "correct_option": "a", "explanation": "我是管理员。 — Я администратор (подтверждение прав доступа)."},
        {"prompt": "Выбери команду для изоляции вредоносного процесса:", "option_a": "隔离进程。", "option_b": "打开音乐。", "option_c": "去吃饭。", "correct_option": "a", "explanation": "隔离进程 — изолировать процесс."},
        {"prompt": "Какой ответ корректно завершает сеанс с узлом? 你要断开连接吗？", "option_a": "是，断开。", "option_b": "我不吃饭。", "option_c": "明天见。", "correct_option": "a", "explanation": "是，断开。 — да, отключить соединение."},
        {"prompt": "Выбери правильный порядок команды отката системы:", "option_a": "系统 恢复 立即", "option_b": "立即 恢复 系统", "option_c": "恢复 立即 系统", "correct_option": "b", "explanation": "立即恢复系统 — немедленно восстановить систему."},
        {"prompt": "Что означает 数据已加密？", "option_a": "Данные удалены", "option_b": "Данные зашифрованы", "option_c": "Данные скопированы", "correct_option": "b", "explanation": "数据已加密 — данные уже зашифрованы."},
        {"prompt": "Выбери верный ответ системе на запрос 需要权限吗？", "option_a": "需要，验证身份。", "option_b": "我很饿。", "option_c": "天气很好。", "correct_option": "a", "explanation": "需要，验证身份。 — да, требуется, проверить личность."},
    ],
    "stabilize": [
        {"prompt": "Как сказать команде 'патч применён'?", "option_a": "补丁已应用。", "option_b": "今天休息。", "option_c": "我饿了。", "correct_option": "a", "explanation": "补丁已应用 — патч применён."},
        {"prompt": "Что значит 系统稳定？", "option_a": "Система перегружена", "option_b": "Система стабильна", "option_c": "Система отключена", "correct_option": "b", "explanation": "系统稳定 — система стабильна."},
        {"prompt": "Выбери фразу для отчёта об устранении сбоя:", "option_a": "故障已修复。", "option_b": "我去散步。", "option_c": "天黑了。", "correct_option": "a", "explanation": "故障已修复 — неисправность устранена."},
        {"prompt": "Как переводится 备份完成？", "option_a": "Резервное копирование завершено", "option_b": "Соединение потеряно", "option_c": "Загрузка началась", "correct_option": "a", "explanation": "备份完成 — резервное копирование завершено."},
        {"prompt": "Что означает 重新连接成功？", "option_a": "Повторное подключение успешно", "option_b": "Файл повреждён", "option_c": "Доступ запрещён", "correct_option": "a", "explanation": "重新连接成功 — повторное подключение прошло успешно."},
        {"prompt": "Выбери верный ответ на тревогу 检测到异常！", "option_a": "正在处理。", "option_b": "再见。", "option_c": "我在吃饭。", "correct_option": "a", "explanation": "正在处理 — обрабатывается (идёт устранение аномалии)."},
    ],
}

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

RAID_QUESTION_SEEDS = [
    {
        "prompt": "Сигнал перехвачен. Расшифруй: 出口 (chūkǒu) — что это?",
        "option_a": "Вход", "option_b": "Выход", "option_c": "Склад",
        "correct_option": "b", "explanation": "出口 — выход, точка эвакуации отряда.",
    },
    {
        "prompt": "Бот-охранник задаёт вопрос: 你叫什么名字？ Что он спрашивает?",
        "option_a": "Твой возраст", "option_b": "Твоё имя", "option_c": "Пароль доступа",
        "correct_option": "b", "explanation": "你叫什么名字？ — как тебя зовут?",
    },
    {
        "prompt": "Перехвачена команда цели: 现在几点？ Что запрашивает система?",
        "option_a": "Местоположение", "option_b": "Уровень угрозы", "option_c": "Текущее время",
        "correct_option": "c", "explanation": "现在几点？ — который сейчас час?",
    },
    {
        "prompt": "Агент передаёт счёт ресурсов: 我有五十分。 Сколько единиц?",
        "option_a": "15", "option_b": "50", "option_c": "500",
        "correct_option": "b", "explanation": "五十 (wǔshí) — пятьдесят.",
    },
    {
        "prompt": "Цель ведёт переговоры в кафе. Слышно: 你吃什么？ О чём речь?",
        "option_a": "Что ты пьёшь", "option_b": "Сколько платишь", "option_c": "Что ты будешь есть",
        "correct_option": "c", "explanation": "你吃什么？ — что ты будешь есть?",
    },
    {
        "prompt": "Тревожный сигнал системы: 危险！ Что это значит?",
        "option_a": "Опасность", "option_b": "Безопасно", "option_c": "Продолжать",
        "correct_option": "a", "explanation": "危险 (wēixiǎn) — опасность.",
    },
    {
        "prompt": "Навигатор передаёт: 左转。 Куда повернуть?",
        "option_a": "Направо", "option_b": "Назад", "option_c": "Налево",
        "correct_option": "c", "explanation": "左 (zuǒ) — лево. 左转 — повернуть налево.",
    },
    {
        "prompt": "Агент легендируется: 我是学生。 Кем он представляется?",
        "option_a": "Врачом", "option_b": "Студентом", "option_c": "Охранником",
        "correct_option": "b", "explanation": "学生 (xuésheng) — студент / ученик.",
    },
    {
        "prompt": "Шифрованный запрос ресурсов: 这是多少钱？ Что запрашивают?",
        "option_a": "Где находится объект?", "option_b": "Когда начало операции?", "option_c": "Сколько это стоит?",
        "correct_option": "c", "explanation": "这是多少钱？ — сколько это стоит?",
    },
]

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


_THREAD_LOCAL = threading.local()


class _PersistentConn:
    """Proxy for a thread-local sqlite3 connection.

    close() is a deliberate no-op: the underlying connection is kept alive
    in the thread-local pool and reused by the next get_conn() call on the
    same thread.  This avoids the per-request WAL scan that caused
    sqlite3.connect() to take 100-300 s after the WAL file grew large.
    All other attributes/methods are transparently delegated to the real
    connection, so existing code requires no changes.
    """

    def __init__(self, conn):
        self.__dict__['_conn'] = conn

    def close(self):
        pass  # intentional no-op; real connection lives in thread-local pool

    def __getattr__(self, name):
        return getattr(self.__dict__['_conn'], name)


def _open_raw_conn():
    t0 = time.time()
    conn = sqlite3.connect('/root/zhidao.db', timeout=30, check_same_thread=False)
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA wal_autocheckpoint=1000")
    ms = (time.time() - t0) * 1000
    if ms > 50:
        print("ZHIDAO_SLOW_CONN %.0fms" % ms, flush=True)
    return conn


def get_conn():
    """Return a _PersistentConn wrapping the thread-local raw connection.

    On each call we check whether the previous _run() left an uncommitted
    transaction (e.g. it raised before conn.commit()).  If so we roll it
    back so the connection is clean for the next caller.  If the connection
    is broken we close it and open a fresh one.
    """
    raw = getattr(_THREAD_LOCAL, 'conn', None)
    if raw is not None:
        try:
            if raw.in_transaction:
                raw.rollback()
        except Exception:
            try:
                raw.close()
            except Exception:
                pass
            raw = None
            _THREAD_LOCAL.conn = None
    if raw is None:
        raw = _open_raw_conn()
        _THREAD_LOCAL.conn = raw
    return _PersistentConn(raw)


DB_WRITE_LOCK = asyncio.Lock()
DB_WRITE_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="zhidao-db-writer",
)


async def db_write(fn, label=None):
    import inspect as _inspect
    t0 = time.time()
    async with DB_WRITE_LOCK:
        lock_wait = (time.time() - t0) * 1000
        t1 = time.time()
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(DB_WRITE_EXECUTOR, fn)
        except Exception as exc:
            message = "ZHIDAO_DB_WRITE_ERROR fn=%s error=%s: %s\n%s" % (
                label or getattr(fn, "__name__", "?"),
                exc.__class__.__name__,
                exc,
                traceback.format_exc(),
            )
            print(message, flush=True)
            log_api_error(message)
            traceback.print_exc()
            raise
        exec_ms = (time.time() - t1) * 1000
        if lock_wait > 100 or exec_ms > 100:
            if label:
                name = label
            else:
                # Walk up the call stack to find the first non-db_write frame
                # so logs show the actual endpoint name, not the generic '_run'.
                name = '?'
                for frame_info in _inspect.stack()[1:6]:
                    fname = frame_info.function
                    if fname not in ('db_write', '_run', '<lambda>', 'wrapper'):
                        name = fname
                        break
            print(
                "ZHIDAO_DB_WRITE fn=%s lock_wait=%.0fms exec=%.0fms" % (name, lock_wait, exec_ms),
                flush=True,
            )
        return result


def normalize_expected_student_name(value: str) -> str:
    text = str(value or "").replace("\t", " ").replace("Ё", "Е").replace("ё", "е")
    return re.sub(r"\s+", " ", text.strip()).lower()


def init_db():
    conn = get_conn()
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-8000")
    c = conn.cursor()
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
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
    c.execute('''CREATE TABLE IF NOT EXISTS leaderboard_snapshots
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  telegram_id INTEGER, rank INTEGER, rep INTEGER,
                  snapshot_date TEXT,
                  UNIQUE(telegram_id, snapshot_date))''')
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
                  capacity INTEGER DEFAULT 1,
                  taken_by INTEGER DEFAULT NULL,
                  created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS laundry_bookings
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  slot_id INTEGER NOT NULL,
                  telegram_id INTEGER NOT NULL,
                  booked_at TEXT DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE(slot_id, telegram_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS water_schedule
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  day TEXT, time TEXT, floor TEXT DEFAULT '', note TEXT,
                  capacity INTEGER DEFAULT 1,
                  created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS water_bookings
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  slot_id INTEGER NOT NULL,
                  telegram_id INTEGER NOT NULL,
                  booked_at TEXT DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE(slot_id, telegram_id))''')
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
    if 'equipped_frame' not in columns:
        c.execute("ALTER TABLE user_status ADD COLUMN equipped_frame TEXT DEFAULT NULL")
    if 'wildai_defender' not in columns:
        c.execute("ALTER TABLE user_status ADD COLUMN wildai_defender INTEGER DEFAULT 0")
    if 'wildai_mvp' not in columns:
        c.execute("ALTER TABLE user_status ADD COLUMN wildai_mvp INTEGER DEFAULT 0")
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
    c.execute('''CREATE TABLE IF NOT EXISTS laundry_bookings
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  slot_id INTEGER NOT NULL,
                  telegram_id INTEGER NOT NULL,
                  booked_at TEXT DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE(slot_id, telegram_id))''')
    c.execute("PRAGMA table_info(laundry_schedule)")
    laundry_schedule_columns = {row[1] for row in c.fetchall()}
    if 'capacity' not in laundry_schedule_columns:
        c.execute("ALTER TABLE laundry_schedule ADD COLUMN capacity INTEGER DEFAULT 1")
    c.execute('''INSERT OR IGNORE INTO laundry_bookings (slot_id, telegram_id)
                 SELECT id, taken_by FROM laundry_schedule
                 WHERE taken_by IS NOT NULL''')
    c.execute('''CREATE TABLE IF NOT EXISTS water_bookings
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  slot_id INTEGER NOT NULL,
                  telegram_id INTEGER NOT NULL,
                  booked_at TEXT DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE(slot_id, telegram_id))''')
    c.execute("PRAGMA table_info(water_schedule)")
    water_schedule_columns = {row[1] for row in c.fetchall()}
    if 'floor' not in water_schedule_columns:
        c.execute("ALTER TABLE water_schedule ADD COLUMN floor TEXT DEFAULT ''")
    if 'capacity' not in water_schedule_columns:
        c.execute("ALTER TABLE water_schedule ADD COLUMN capacity INTEGER DEFAULT 1")
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
        if 'pressure_tick_at' not in event_columns:
            c.execute("ALTER TABLE events ADD COLUMN pressure_tick_at TEXT DEFAULT NULL")
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
                  is_anonymous INTEGER NOT NULL DEFAULT 0,
                  created_at TEXT NOT NULL,
                  accepted_at TEXT DEFAULT NULL,
                  completed_at TEXT DEFAULT NULL,
                  cancelled_at TEXT DEFAULT NULL,
                  disputed_at TEXT DEFAULT NULL)''')
    c.execute("PRAGMA table_info(contracts)")
    contract_columns = {row[1] for row in c.fetchall()}
    if 'is_anonymous' not in contract_columns:
        c.execute("ALTER TABLE contracts ADD COLUMN is_anonymous INTEGER NOT NULL DEFAULT 0")
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

    c.execute("CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_economy_log_telegram_id ON economy_log(telegram_id, created_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_user_implants_tid ON user_implants(telegram_id, implant_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_user_cards_tid ON user_cards(telegram_id, card_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_implant_daily_uses_tid ON implant_daily_uses(telegram_id, implant_id, use_date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_shop_purchases_tid ON shop_purchases(telegram_id, item_code)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_casino_log_tid ON casino_log(telegram_id, date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_admin_action_logs_target ON admin_action_logs(target_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_daily_checks_tid ON daily_checks(telegram_id, check_date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_diary_stars_tid ON diary_stars(telegram_id, entry_date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_diary_entries_tid ON diary_entries(telegram_id, entry_date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_raids_date ON raids(date, status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_raid_participants_rid ON raid_participants(raid_id, telegram_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_contracts_status ON contracts(status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_legendary_actions ON legendary_implant_actions(actor_telegram_id, action_code)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_event_actions_eid ON event_actions(event_id, telegram_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_event_participants_eid ON event_participants(event_id, telegram_id)")

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
    for deactivated_code in SHOP_ITEM_DEACTIVATE:
        c.execute("UPDATE shop_items SET active=0 WHERE code=?", (deactivated_code,))
    for achievement in ACHIEVEMENT_SEEDS:
        c.execute(
            '''INSERT INTO achievements
               (code, name, description, icon, secret)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(code) DO UPDATE SET
                 name=excluded.name,
                 description=excluded.description,
                 icon=excluded.icon,
                 secret=excluded.secret''',
            achievement,
        )
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('blackwall', '0')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('architect_event', '0')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('wildai_event', '0')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('breach_until', '')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('breach_seed', '')")
    # Raid schema migrations (idempotent)
    try:
        c.execute("ALTER TABLE raids ADD COLUMN correct_count INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE raid_participants ADD COLUMN answer_correct INTEGER DEFAULT 0")
    except Exception:
        pass
    # Seed raid questions
    c.execute("SELECT COUNT(*) FROM event_questions WHERE event_code='raid'")
    if c.fetchone()[0] == 0:
        created_at = datetime.utcnow().isoformat()
        for q in RAID_QUESTION_SEEDS:
            c.execute(
                '''INSERT INTO event_questions
                   (event_code, action_type, difficulty, prompt, option_a, option_b, option_c, correct_option, explanation, created_at)
                   VALUES (?, 'scan', 1, ?, ?, ?, ?, ?, ?, ?)''',
                ('raid', q["prompt"], q["option_a"], q["option_b"], q["option_c"],
                 q["correct_option"], q.get("explanation"), created_at),
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

    c.execute("SELECT COUNT(*) FROM event_questions WHERE event_code='wildai_breach'")
    wildai_count = c.fetchone()[0]
    if wildai_count == 0:
        created_at = datetime.utcnow().isoformat()
        for action_type, questions in WILD_AI_BREACH_QUESTION_SEEDS.items():
            for question in questions:
                c.execute(
                    '''INSERT INTO event_questions
                       (event_code, action_type, difficulty, prompt, option_a, option_b, option_c, correct_option, explanation, created_at)
                       VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?)''',
                    (
                        'wildai_breach',
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

WAL_CHECKPOINT_INTERVAL_SECONDS = 300


async def wal_checkpoint_loop():
    while True:
        await asyncio.sleep(WAL_CHECKPOINT_INTERVAL_SECONDS)
        if DB_WRITE_LOCK.locked():
            # Never let maintenance compete with user/admin mutations.
            continue
        try:
            t0 = time.time()

            def _checkpoint():
                conn = sqlite3.connect('/root/zhidao.db', timeout=1)
                try:
                    conn.execute("PRAGMA busy_timeout=100")
                    # PASSIVE checkpoints what it can and returns immediately if
                    # readers/writers are active. User actions must never wait for
                    # maintenance; startup handles WAL reset after restarts.
                    row = conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
                    return row
                finally:
                    conn.close()

            row = await asyncio.to_thread(_checkpoint)
            ms = (time.time() - t0) * 1000
            if ms > 200 or (row and row[0] != 0):
                print(
                    "ZHIDAO_WAL_CHECKPOINT busy=%s log_frames=%s checkpointed_frames=%s elapsed_ms=%.0f" % (
                        row[0] if row else "?",
                        row[1] if row else "?",
                        row[2] if row else "?",
                        ms,
                    ),
                    flush=True,
                )
        except Exception as exc:
            print("ZHIDAO_WAL_CHECKPOINT_ERROR %r" % (exc,), flush=True)


@app.on_event("startup")
async def start_background_tasks():
    asyncio.create_task(rate_limit_bucket_cleanup_loop())

    if os.getenv("ZHIDAO_ENABLE_WAL_CHECKPOINT", "0") != "1":
        return

    # Manual WAL checkpointing is disabled by default. On the production
    # server RESTART checkpoints were observed taking 49-72 seconds and
    # competing with admin/shop writes. Keep this as opt-in maintenance only.
    def _startup_checkpoint():
        try:
            conn = sqlite3.connect('/root/zhidao.db', timeout=5)
            try:
                conn.execute("PRAGMA busy_timeout=1000")
                row = conn.execute("PRAGMA wal_checkpoint(RESTART)").fetchone()
                print(
                    "ZHIDAO_STARTUP_CHECKPOINT busy=%s log_frames=%s checkpointed_frames=%s" % (
                        row[0] if row else "?",
                        row[1] if row else "?",
                        row[2] if row else "?",
                    ),
                    flush=True,
                )
            finally:
                conn.close()
        except Exception as exc:
            print("ZHIDAO_STARTUP_CHECKPOINT_ERROR %r" % (exc,), flush=True)

    asyncio.create_task(asyncio.to_thread(_startup_checkpoint))
    asyncio.create_task(wal_checkpoint_loop())


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
                  mvp_user_id, extra_participants, pressure_tick_at
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
        "pressure_tick_at": row[21],
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
    if event_row.get("code") != "architect":
        return False

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


def activate_wildai_breach(c, admin_id: Optional[int] = None, reason: str = 'Wild AI Breach auto-triggered (system integrity restoration failed)', send_broadcast: bool = True):
    until = (datetime.utcnow() + timedelta(days=WILD_AI_BREACH_DURATION_DAYS)).isoformat()
    seed = random.randint(0, 999999)
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('breach_until', ?)", (until,))
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('breach_seed', ?)", (str(seed),))
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('blackwall', '1')")
    phrase = WILD_AI_BREACH_PHRASES[seed % len(WILD_AI_BREACH_PHRASES)]
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('breach_broadcast_phrase_glitch', ?)", (phrase["glitch"],))
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('breach_broadcast_phrase_translation', ?)", (phrase["translation"],))
    if send_broadcast:
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('breach_broadcast_pending', '1')")
    c.execute(
        '''INSERT INTO admin_action_logs
           (admin_id, target_id, action_type, points_delta, reason, created_at)
           VALUES (?, NULL, 'wildai_breach', 0, ?, ?)''',
        (admin_id if admin_id is not None else 0, reason, now_iso()),
    )


def distribute_wildai_victory_rewards(c, event_id: int, mvp_id: Optional[int]):
    c.execute("SELECT telegram_id FROM event_participants WHERE event_id=?", (event_id,))
    participant_ids = [row[0] for row in c.fetchall()]
    for telegram_id in participant_ids:
        c.execute("UPDATE users SET rep_score = COALESCE(rep_score, 0) + ? WHERE telegram_id=?", (WILD_AI_BREACH_REWARD_REP, telegram_id))
        c.execute(
            "UPDATE user_status SET protocol_fragments = COALESCE(protocol_fragments, 0) + ?, wildai_defender=1 WHERE telegram_id=?",
            (WILD_AI_BREACH_REWARD_FRAGMENTS, telegram_id),
        )
        c.execute("UPDATE user_status SET wildai_mvp = ? WHERE telegram_id=?", (1 if telegram_id == mvp_id else 0, telegram_id))


def refresh_event_state(c, event_row: dict):
    if not event_row:
        return None

    if event_row.get("code") == "wildai_breach":
        if event_row["state"] == "ACTIVE":
            started = parse_iso(event_row.get("started_at"))
            now = datetime.utcnow()

            # Infection ticks over time
            tick_from = parse_iso(event_row.get("pressure_tick_at")) or started
            if tick_from:
                elapsed = (now - tick_from).total_seconds()
                ticks = int(elapsed // WILD_AI_BREACH_INFECTION_TICK_SECONDS)
                if ticks > 0:
                    new_pressure = event_row["overload_pressure"] + ticks * WILD_AI_BREACH_INFECTION_TICK_AMOUNT
                    new_tick_at = (tick_from + timedelta(seconds=ticks * WILD_AI_BREACH_INFECTION_TICK_SECONDS)).isoformat()
                    event_row["overload_pressure"] = new_pressure
                    event_row["pressure_tick_at"] = new_tick_at
                    c.execute(
                        "UPDATE events SET overload_pressure=?, pressure_tick_at=? WHERE id=?",
                        (new_pressure, new_tick_at, event_row["id"]),
                    )

            time_expired = started and (now - started).total_seconds() > WILD_AI_BREACH_TIME_LIMIT_SECONDS
            infection_critical = event_row["overload_pressure"] >= WILD_AI_BREACH_INFECTION_THRESHOLD

            hp_ratio = event_row["current_hp"] / event_row["max_hp"] if event_row["max_hp"] else 0

            if event_row["phase"] == 1 and hp_ratio <= ARCHITECT_PHASE2_THRESHOLD:
                event_row["phase"] = 2
                c.execute("UPDATE events SET phase=2 WHERE id=?", (event_row["id"],))
                add_event_log(c, event_row["id"], "boss", "WILD AI BREACH: вторичный периметр пробит. Дикий ИИ усиливает атаку.")

            if event_row["phase"] == 2 and hp_ratio <= ARCHITECT_PHASE3_THRESHOLD:
                event_row["phase"] = 3
                c.execute("UPDATE events SET phase=3 WHERE id=?", (event_row["id"],))
                add_event_log(c, event_row["id"], "boss", "WILD AI BREACH: критическая зона. Дикий ИИ обходит последние защиты.")

            if event_row["current_hp"] > 0 and (time_expired or infection_critical):
                event_row["state"] = "FAILED"
                event_row["ended_at"] = now_iso()
                c.execute(
                    "UPDATE events SET state='FAILED', ended_at=? WHERE id=?",
                    (event_row["ended_at"], event_row["id"]),
                )
                reason = "заражение достигло критического уровня" if infection_critical else "время истекло"
                add_event_log(c, event_row["id"], "system", f"WILD AI BREACH: операция провалена — {reason}. Дикий ИИ закрепился в системе.")
                activate_wildai_breach(c, send_broadcast=False)

            if event_row["current_hp"] <= 0:
                event_row["current_hp"] = 0
                event_row["state"] = "FINISHED"
                event_row["ended_at"] = now_iso()
                c.execute(
                    """SELECT telegram_id FROM event_participants
                       WHERE event_id=? ORDER BY total_damage DESC, total_support DESC LIMIT 1""",
                    (event_row["id"],),
                )
                mvp_row = c.fetchone()
                mvp_id = mvp_row[0] if mvp_row else None
                c.execute(
                    "UPDATE events SET current_hp=0, state='FINISHED', ended_at=?, mvp_user_id=? WHERE id=?",
                    (event_row["ended_at"], mvp_id, event_row["id"]),
                )
                event_row["mvp_user_id"] = mvp_id
                add_event_log(c, event_row["id"], "system", "WILD AI BREACH: целостность системы восстановлена. Дикий ИИ вытеснен.")
                distribute_wildai_victory_rewards(c, event_row["id"], mvp_id)

        return fetch_event_row(c, event_row["id"])

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


ARCHITECT_RESULT_VISIBLE_HOURS = 12


def get_current_or_latest_event_id(event_code: Optional[str] = None):
    conn = get_conn()
    c = conn.cursor()
    if event_code:
        c.execute("SELECT id FROM events WHERE state IN ('REGISTRATION', 'ACTIVE') AND code=? ORDER BY id DESC", (event_code,))
    else:
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
    if row:
        conn.close()
        return row[0]
    # No live event: keep showing the latest finished/failed one for a while
    # so participants see the result screen instead of the standby lobby.
    if event_code:
        c.execute(
            "SELECT id, ended_at FROM events WHERE state IN ('FINISHED', 'FAILED') AND code=? ORDER BY id DESC LIMIT 1",
            (event_code,)
        )
    else:
        c.execute(
            "SELECT id, ended_at FROM events WHERE state IN ('FINISHED', 'FAILED') ORDER BY id DESC LIMIT 1"
        )
    terminal = c.fetchone()
    conn.close()
    if terminal:
        ended = parse_iso(terminal[1])
        if ended and datetime.utcnow() - ended <= timedelta(hours=ARCHITECT_RESULT_VISIBLE_HOURS):
            return terminal[0]
    return None


def get_blocking_event_id(event_code: Optional[str] = None):
    conn = get_conn()
    c = conn.cursor()
    if event_code:
        c.execute("SELECT id FROM events WHERE state IN ('REGISTRATION', 'ACTIVE') AND code=? ORDER BY id DESC", (event_code,))
    else:
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


def choose_architect_question(c, action_type: str, event_code: str = 'architect'):
    c.execute(
        '''SELECT id, prompt, option_a, option_b, option_c, explanation
           FROM event_questions
           WHERE event_code=? AND action_type=?
           ORDER BY RANDOM()
           LIMIT 1''',
        (event_code, action_type),
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

    phase_values = {
        1: {"attack": 20, "protocol": 10, "stabilize": 10},
        2: {"attack": 8, "protocol": 28, "stabilize": 12},
        3: {"attack": 18, "protocol": 22, "stabilize": 18},
    }
    full = phase_values.get(phase, {}).get(action_type, 0)
    if not is_correct:
        # Wrong answer: 25% partial hit (sloppy execution, not a full miss)
        return max(0, round(full * 0.25))
    return full


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


def get_wildai_base_value(action_type: str, is_correct: bool) -> int:
    if action_type == "sync":
        return 0
    base_values = {"attack": 22, "protocol": 16, "stabilize": 14}
    full = base_values.get(action_type, 0)
    if not is_correct:
        return max(0, round(full * 0.25))
    return full


def compute_wildai_action_result(c, event_row: dict, participant: dict, action_type: str, is_correct: bool, telegram_id: int = 0):
    base_value = get_wildai_base_value(action_type, is_correct)
    final_value = base_value
    support_value = 0
    pressure_delta = 0

    if action_type == "sync":
        support_value = 1
        pressure_delta = -WILD_AI_BREACH_INFECTION_SYNC_REDUCTION
        maybe_trigger_sync_window(c, event_row)
        return {
            "base_value": 0,
            "modifier_value": 0,
            "final_value": 0,
            "support_value": support_value,
            "pressure_delta": pressure_delta,
            "active_note": None,
            "penalty_active": False,
        }

    if action_type in ("attack", "protocol"):
        if not is_correct:
            pressure_delta = WILD_AI_BREACH_INFECTION_ON_ERROR
        if is_vulnerability_active(event_row) and final_value > 0:
            bonus = max(1, round(final_value * 0.3))
            final_value += bonus
        return {
            "base_value": base_value,
            "modifier_value": final_value - base_value,
            "final_value": final_value,
            "support_value": 0,
            "pressure_delta": pressure_delta,
            "active_note": None,
            "penalty_active": False,
        }

    # stabilize
    if is_correct:
        support_value = base_value
        pressure_delta = -WILD_AI_BREACH_INFECTION_STABILIZE_REDUCTION
    else:
        pressure_delta = WILD_AI_BREACH_INFECTION_ON_ERROR
    return {
        "base_value": base_value,
        "modifier_value": 0,
        "final_value": 0,
        "support_value": support_value,
        "pressure_delta": pressure_delta,
        "active_note": None,
        "penalty_active": False,
    }


# ===== Implant/card combat bonuses (Architect Protocol & Wild AI Breach) =====
# item_id -> (damage_pct, applicable action types)
EVENT_ITEM_DAMAGE_BONUS = {
    "implant_red_dragon": (0.20, ("attack", "protocol")),
    "implant_shaolin": (0.10, ("attack",)),
    "implant_linguasoft": (0.10, ("protocol",)),
    "card_pyro": (0.10, ("attack",)),
    "card_literature": (0.10, ("protocol",)),
}
EVENT_ITEM_PRESSURE_REDUCTION = ("implant_terracota", "card_forest")  # -20% pressure/overload gain on error
EVENT_ITEM_SYNC_SUPPORT = ("implant_guanxi", "card_sea")  # +1 support on Sync
EVENT_ITEM_STABILIZE_SUPPORT = ("implant_caishen", "card_fairy")  # +2 support on Stabilize
EVENT_ITEM_ANY_SUPPORT = ("implant_panda", "card_fox")  # +1 support on Sync/Stabilize
EVENT_ITEM_TEAM_DAMAGE = ("implant_qilin", "card_moon")  # +5% team damage if 2+ teammates hold it
EVENT_ITEM_TEAM_DAMAGE_BONUS_PCT = 0.05
EVENT_ITEM_TEAM_DAMAGE_MIN_HOLDERS = 2


def get_event_combat_items(c, telegram_id: int) -> set:
    items = set()
    c.execute("SELECT implant_id FROM user_implants WHERE telegram_id=? AND durability > 0", (telegram_id,))
    items.update(row[0] for row in c.fetchall())
    c.execute("SELECT card_id FROM user_cards WHERE telegram_id=? AND durability > 0", (telegram_id,))
    items.update(row[0] for row in c.fetchall())
    return items


def apply_event_item_bonuses(c, event_row: dict, telegram_id: int, action_type: str, is_correct: bool, result: dict):
    if not telegram_id:
        return
    items = get_event_combat_items(c, telegram_id)
    if not items:
        return

    if action_type in ("attack", "protocol") and result.get("final_value", 0) > 0:
        damage_pct = sum(pct for item_id, (pct, actions) in EVENT_ITEM_DAMAGE_BONUS.items()
                          if item_id in items and action_type in actions)
        if damage_pct:
            bonus = max(1, round(result["final_value"] * damage_pct))
            result["final_value"] += bonus
            result["modifier_value"] = result.get("modifier_value", 0) + bonus
        if "card_star" in items and is_correct:
            result["final_value"] += 1
            result["modifier_value"] = result.get("modifier_value", 0) + 1

        for item_id in EVENT_ITEM_TEAM_DAMAGE:
            if item_id not in items:
                continue
            table = "user_implants" if item_id.startswith("implant_") else "user_cards"
            column = "implant_id" if table == "user_implants" else "card_id"
            c.execute(
                f'''SELECT COUNT(*) FROM event_team_members etm
                    JOIN {table} t ON t.telegram_id = etm.telegram_id AND t.{column}=? AND t.durability > 0
                    WHERE etm.event_id=?''',
                (item_id, event_row["id"]),
            )
            holders = c.fetchone()[0]
            if holders >= EVENT_ITEM_TEAM_DAMAGE_MIN_HOLDERS:
                bonus = max(1, round(result["final_value"] * EVENT_ITEM_TEAM_DAMAGE_BONUS_PCT))
                result["final_value"] += bonus
                result["modifier_value"] = result.get("modifier_value", 0) + bonus

    if not is_correct and result.get("pressure_delta", 0) > 0 and any(i in items for i in EVENT_ITEM_PRESSURE_REDUCTION):
        result["pressure_delta"] = max(0, result["pressure_delta"] - max(1, round(result["pressure_delta"] * 0.20)))

    if action_type == "sync":
        if any(i in items for i in EVENT_ITEM_SYNC_SUPPORT):
            result["support_value"] = result.get("support_value", 0) + 1
        if any(i in items for i in EVENT_ITEM_ANY_SUPPORT):
            result["support_value"] = result.get("support_value", 0) + 1
        if "card_zhongli" in items and result.get("pressure_delta", 0) < 0:
            result["pressure_delta"] -= 1
        if is_correct and "implant_netwatch" in items and is_vulnerability_active(event_row):
            until = parse_iso(event_row.get("vulnerability_until"))
            if until:
                new_until = (until + timedelta(seconds=30)).isoformat()
                event_row["vulnerability_until"] = new_until
                c.execute("UPDATE events SET vulnerability_until=? WHERE id=?", (new_until, event_row["id"]))

    if action_type == "stabilize":
        if is_correct and any(i in items for i in EVENT_ITEM_STABILIZE_SUPPORT):
            result["support_value"] = result.get("support_value", 0) + 2
        if is_correct and any(i in items for i in EVENT_ITEM_ANY_SUPPORT):
            result["support_value"] = result.get("support_value", 0) + 1
        if "card_zhongli" in items and result.get("pressure_delta", 0) < 0:
            result["pressure_delta"] -= 1


def compute_event_action_result(c, event_row: dict, participant: dict, action_type: str, is_correct: bool, use_active_modifier: bool, telegram_id: int = 0):
    if event_row.get("code") == "wildai_breach":
        result = compute_wildai_action_result(c, event_row, participant, action_type, is_correct, telegram_id=telegram_id)
    else:
        result = compute_architect_action_result(c, event_row, participant, action_type, is_correct, use_active_modifier, telegram_id=telegram_id)
    apply_event_item_bonuses(c, event_row, telegram_id, action_type, is_correct, result)
    return result


def compute_architect_action_result(c, event_row: dict, participant: dict, action_type: str, is_correct: bool, use_active_modifier: bool, telegram_id: int = 0):
    phase = event_row["phase"]
    role = participant.get("modifier_role")
    base_value = get_architect_base_value(phase, action_type, is_correct)
    modifier_value = 0
    support_value = 0
    final_value = base_value
    active_note = None
    pressure_delta = 0

    # Phase-specific overload config
    _overload_cfg = {
        1: {"atk_delta": 0, "stab_delta": 0,  "threshold": 9999, "multiplier": 1.0},
        2: {"atk_delta": 2, "stab_delta": -4,  "threshold": 15,   "multiplier": 0.75},
        3: {"atk_delta": 5, "stab_delta": -8,  "threshold": ARCHITECT_OVERLOAD_PENALTY_THRESHOLD, "multiplier": ARCHITECT_OVERLOAD_PENALTY_MULTIPLIER},
    }
    oc = _overload_cfg.get(phase, _overload_cfg[1])

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
        pressure_delta = oc["atk_delta"]
    elif action_type == "stabilize":
        pressure_delta = oc["stab_delta"]

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

    # Combo bonus: +15% if last attack/protocol action was same type by a different player
    if action_type in ("attack", "protocol") and final_value > 0 and telegram_id:
        c.execute(
            """SELECT action_type, telegram_id FROM event_actions
               WHERE event_id=? AND action_type IN ('attack','protocol')
               ORDER BY id DESC LIMIT 1""",
            (event_row["id"],),
        )
        last_atk = c.fetchone()
        if last_atk and last_atk[0] == action_type and int(last_atk[1]) != int(telegram_id):
            combo_bonus = max(1, round(final_value * 0.15))
            final_value += combo_bonus
            modifier_value += combo_bonus
            active_note = (active_note or '') + f" COMBO +{combo_bonus}"

    penalty_active = event_row["overload_pressure"] >= oc["threshold"]
    if penalty_active and action_type in ("attack", "protocol") and final_value > 0:
        mult = max(oc["multiplier"], 0.9) if role == "defense" else oc["multiplier"]
        reduced = max(0, final_value - round(final_value * mult))
        final_value = max(0, round(final_value * mult))
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
        "overload_threshold": oc["threshold"],
        "overload_pct_str": f"{round((1 - oc['multiplier']) * 100)}%",
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


def get_user_theme_path(c, telegram_id: int) -> str:
    """Returns the user's current path: 'cyberpunk' or 'genshin'. Defaults to 'cyberpunk'."""
    c.execute("SELECT theme_path FROM user_status WHERE telegram_id=?", (telegram_id,))
    row = c.fetchone()
    return row[0] if row and row[0] else 'cyberpunk'


def has_active_implant(c, telegram_id: int, implant_id: str) -> bool:
    # Implants belong to the cyberpunk path. While a player has switched to the
    # genshin path, implant passives are frozen (not lost, just inactive).
    if telegram_id not in ADMIN_IDS and get_user_theme_path(c, telegram_id) == 'genshin':
        return False
    c.execute(
        '''SELECT 1 FROM user_implants
           WHERE telegram_id=? AND implant_id=? AND durability > 0
           LIMIT 1''',
        (telegram_id, implant_id),
    )
    return bool(c.fetchone())


def has_active_card(c, telegram_id: int, card_id: str) -> bool:
    # Cards belong to the genshin path. While a player is on the cyberpunk path,
    # card passives are frozen (not lost, just inactive).
    if telegram_id not in ADMIN_IDS and get_user_theme_path(c, telegram_id) != 'genshin':
        return False
    c.execute(
        '''SELECT 1 FROM user_cards
           WHERE telegram_id=? AND card_id=? AND durability > 0
           LIMIT 1''',
        (telegram_id, card_id),
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


def has_used_card_today(c, telegram_id: int, card_id: str, use_key: str = "", use_date: Optional[str] = None) -> bool:
    return has_used_implant_today(c, telegram_id, card_id, use_key, use_date)


def mark_card_used_today(c, telegram_id: int, card_id: str, use_key: str = "", use_date: Optional[str] = None):
    mark_implant_used_today(c, telegram_id, card_id, use_key, use_date)


def consume_card_penalty_reduction(c, telegram_id: int, use_key: str) -> int:
    if not has_active_card(c, telegram_id, "card_star"):
        return 0
    if has_used_card_today(c, telegram_id, "card_star", "penalty_reduction"):
        return 0
    mark_card_used_today(c, telegram_id, "card_star", "penalty_reduction")
    c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
    balance_after = (c.fetchone() or [0])[0] or 0
    log_economy(c, telegram_id, "card_star_judgement", 0, balance_after, None, "card", use_key)
    return 15


def apply_card_pyro_rebirth(c, telegram_id: int, use_key: str, max_bonus: int = 25) -> int:
    if not has_active_card(c, telegram_id, "card_pyro"):
        return 0
    if has_used_card_today(c, telegram_id, "card_pyro", "rebirth"):
        return 0
    bonus = max(0, min(25, int(max_bonus or 0)))
    if bonus <= 0:
        return 0
    mark_card_used_today(c, telegram_id, "card_pyro", "rebirth")
    c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (bonus, telegram_id))
    c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
    balance_after = (c.fetchone() or [0])[0] or 0
    log_economy(c, telegram_id, "card_pyro_rebirth", bonus, balance_after, None, "card", use_key)
    return bonus


def grant_card_points_once(c, telegram_id: int, card_id: str, use_key: str, amount: int,
                           operation: str, note: str = "", use_date: Optional[str] = None,
                           reference_id: Optional[int] = None,
                           reference_type: str = "card") -> int:
    if amount <= 0 or not has_active_card(c, telegram_id, card_id):
        return 0
    if has_used_card_today(c, telegram_id, card_id, use_key, use_date):
        return 0
    mark_card_used_today(c, telegram_id, card_id, use_key, use_date)
    c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (amount, telegram_id))
    c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
    balance_after = (c.fetchone() or [0])[0] or 0
    log_economy(c, telegram_id, operation, amount, balance_after, reference_id, reference_type, note)
    return amount


def grant_card_scan_once(c, telegram_id: int, card_id: str, use_key: str,
                         operation: str, note: str = "", use_date: Optional[str] = None) -> int:
    if not has_active_card(c, telegram_id, card_id):
        return 0
    if has_used_card_today(c, telegram_id, card_id, use_key, use_date):
        return 0
    mark_card_used_today(c, telegram_id, card_id, use_key, use_date)
    c.execute("""INSERT INTO user_status (telegram_id, scan_attempts) VALUES (?,1)
                 ON CONFLICT(telegram_id) DO UPDATE SET scan_attempts=MIN(7, scan_attempts+1)""",
              (telegram_id,))
    c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
    balance_after = (c.fetchone() or [0])[0] or 0
    log_economy(c, telegram_id, operation, 0, balance_after, None, "card", note)
    return 1


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
    "fate_verdict": timedelta(hours=24),
    "star_ward": timedelta(days=7),
    "earth_contract": timedelta(hours=72),
    "okamenenie": timedelta(days=7),
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
    is_active = (
        has_active_card(c, actor_id, implant_id)
        if implant_id.startswith("card_")
        else has_active_implant(c, actor_id, implant_id)
    )
    if not is_active:
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


def get_marzban_access_link(data: dict) -> Optional[str]:
    links = data.get("links") or []
    if links:
        return links[0]
    subscription_url = data.get("subscription_url") or data.get("subscriptionUrl")
    return str(subscription_url).strip() if subscription_url else None


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
    def _run():
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

        # This endpoint is the one-time initial path choice. Switching afterwards
        # must go through the "Смена пути" shop item (path_switch), so that
        # implant/card passive freezing can't be bypassed for free.
        if telegram_id not in ADMIN_IDS:
            c.execute("SELECT theme_path FROM user_status WHERE telegram_id=?", (telegram_id,))
            existing = c.fetchone()
            if existing and existing[0]:
                conn.close()
                raise HTTPException(status_code=409, detail="Path already chosen")

        c.execute(
            """INSERT INTO user_status (telegram_id, theme_path) VALUES (?, ?)
               ON CONFLICT(telegram_id) DO UPDATE SET theme_path=excluded.theme_path""",
            (telegram_id, path),
        )
        conn.commit()
        conn.close()
        return {"success": True, "theme_path": path}
    return await db_write(_run)


@app.get("/api/profile/{telegram_id}")
def get_user_profile_dossier(telegram_id: int):
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
                  us.profile_showcase_kind, us.profile_showcase_code, u.rep_score, us.equipped_frame,
                  us.wildai_mvp
           FROM users u
           LEFT JOIN user_status us ON us.telegram_id = u.telegram_id
           WHERE u.telegram_id=?''',
        (telegram_id,),
    )
    user_row = c.fetchone()
    if not user_row:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    full_name, points, avatar_url, theme_path, manual_showcase_kind, manual_showcase_code, rep_score, equipped_frame, wildai_mvp = user_row
    if equipped_frame not in FRAME_IDS:
        equipped_frame = None
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
            "detail": f"{info.get('rarity', 4)}★ · прочность {durability}",
            "source": source,
        }

    def implant_showcase(implant_id: str, durability: int, source: str = "auto"):
        info = implant_info.get(implant_id, {"name": implant_id, "glyph": "芯", "weight": 1})
        return {
            "kind": "implant",
            "code": implant_id,
            "name": info.get("name", implant_id),
            "glyph": info.get("glyph", "芯"),
            "detail": f"прочность {durability}",
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

    if wildai_mvp:
        title = WILD_AI_BREACH_MVP_TITLE
    elif prayers >= 20:
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
        "equipped_frame": equipped_frame,
        "is_admin": telegram_id in ADMIN_IDS,
        "is_architect": telegram_id in ARCHITECT_IDS,
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
    def _run():
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
    return await db_write(_run)


def get_last_event_mvp_id(c) -> Optional[int]:
    """Return mvp_user_id of the most recently finished event, or None."""
    c.execute(
        "SELECT mvp_user_id FROM events WHERE state='FINISHED' ORDER BY ended_at DESC LIMIT 1"
    )
    row = c.fetchone()
    return row[0] if row else None


@app.get("/api/user/{telegram_id}")
async def get_user(telegram_id: int):
    def _db():
        conn = get_conn()
        try:
            c = conn.cursor()
            c.execute("SELECT full_name, avatar_url, marzban_username FROM users WHERE telegram_id=?", (telegram_id,))
            profile_row = c.fetchone()
            is_last_mvp = get_last_event_mvp_id(c) == telegram_id
            return profile_row, is_last_mvp
        finally:
            conn.close()

    profile_row, is_last_mvp = await asyncio.to_thread(_db)
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
    link = get_marzban_access_link(data)
    return {
        "username": marzban_user,
        "full_name": full_name or marzban_user,
        "avatar_url": avatar_url,
        "status": data.get("status"),
        "link": link,
        "used_traffic": data.get("used_traffic", 0),
        "expire": data.get("expire"),
        "is_admin": telegram_id in ADMIN_IDS,
        "is_architect": telegram_id in ARCHITECT_IDS,
        "has_vpn": True,
        "is_last_mvp": is_last_mvp,
    }


@app.post("/api/user/avatar")
async def update_user_avatar(data: dict):
    def _run():
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
    return await db_write(_run)


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
def get_schedule():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, day, time, subject, location FROM schedule ORDER BY day, time")
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "day": r[1], "time": r[2], "subject": r[3], "location": r[4]} for r in rows]


@app.post("/api/schedule")
async def add_schedule(item: ScheduleItem, x_admin_id: Optional[int] = Header(None)):
    def _run():
        if x_admin_id not in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Forbidden")
        conn = get_conn()
        c = conn.cursor()
        c.execute("INSERT INTO schedule (day, time, subject, location) VALUES (?,?,?,?)", (item.day, item.time, item.subject, item.location))
        conn.commit()
        conn.close()
        return {"success": True}
    return await db_write(_run)


@app.delete("/api/schedule/{item_id}")
async def delete_schedule(item_id: int, x_admin_id: Optional[int] = Header(None)):
    def _run():
        if x_admin_id not in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Forbidden")
        conn = get_conn()
        c = conn.cursor()
        c.execute("DELETE FROM schedule WHERE id=?", (item_id,))
        conn.commit()
        conn.close()
        return {"success": True}
    return await db_write(_run)


@app.get("/api/announcements")
def get_announcements():
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

    def _run():
        conn = get_conn()
        c = conn.cursor()
        try:
            c.execute("INSERT INTO announcements (text) VALUES (?)", (text,))
            announcement_id = c.lastrowid
            conn.commit()
            return announcement_id
        finally:
            conn.close()

    announcement_id = await db_write(_run)
    telegram_delivery = await broadcast_announcement_to_telegram(text)
    return {"success": True, "id": announcement_id, "telegram_delivery": telegram_delivery}


@app.delete("/api/announcements/{item_id}")
async def delete_announcement(item_id: int, x_admin_id: Optional[int] = Header(None)):
    def _run():
        if x_admin_id not in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Forbidden")
        conn = get_conn()
        c = conn.cursor()
        c.execute("DELETE FROM announcements WHERE id=?", (item_id,))
        conn.commit()
        conn.close()
        return {"success": True}
    return await db_write(_run)


@app.get("/api/announcements/{item_id}/reactions")
def get_reactions(item_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT emoji, COUNT(*) as cnt FROM announcement_reactions WHERE announcement_id=? GROUP BY emoji", (item_id,))
    rows = c.fetchall()
    conn.close()
    return [{"emoji": r[0], "count": r[1]} for r in rows]


@app.post("/api/announcements/{item_id}/react")
async def react_to_announcement(item_id: int, data: dict):
    def _run():
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
    return await db_write(_run)


@app.get("/api/laundry")
def get_laundry():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, date, time, telegram_id, username FROM laundry ORDER BY date, time")
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "date": r[1], "time": r[2], "telegram_id": r[3], "username": r[4]} for r in rows]


@app.post("/api/laundry")
async def book_laundry(item: LaundryBook):
    def _run():
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
    return await db_write(_run)


@app.delete("/api/laundry/{item_id}")
async def cancel_laundry(item_id: int, x_telegram_id: Optional[int] = Header(None)):
    def _run():
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
    return await db_write(_run)


@app.get("/api/points/{telegram_id}")
def get_points(telegram_id: int):
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
def admin_search_users(q: str = "", x_admin_id: Optional[int] = Header(None)):
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
    def _run():
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
    return await db_write(_run)


@app.get("/api/admin/user/{telegram_id}/dossier")
def admin_user_dossier(telegram_id: int, x_admin_id: Optional[int] = Header(None)):
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
def admin_expected_students(q: str = "", x_admin_id: Optional[int] = Header(None)):
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
    requested_delta = delta

    def _run():
        conn = get_conn()
        try:
            c = conn.cursor()
            c.execute("SELECT full_name, points FROM users WHERE telegram_id=?", (target_id,))
            row = c.fetchone()
            if not row:
                return None

            previous_points = row[1] or 0
            local_delta = delta
            blocked_by_implant = local_delta < 0 and try_block_penalty_with_terracota(c, target_id, f"admin_points: {reason}")
            if not blocked_by_implant:
                if local_delta < 0:
                    armor_reduction = consume_terracota_armor(c, target_id)
                    card_reduction = consume_card_penalty_reduction(c, target_id, f"admin_points: {reason}")
                    local_delta = min(0, local_delta + armor_reduction)
                    local_delta = min(0, local_delta + card_reduction)
                c.execute(
                    "UPDATE users SET points = MAX(0, COALESCE(points, 0) + ?) WHERE telegram_id=?",
                    (local_delta, target_id),
                )
            c.execute("SELECT points FROM users WHERE telegram_id=?", (target_id,))
            new_points = c.fetchone()[0] or 0
            actual_delta = new_points - previous_points
            pyro_bonus = 0
            if actual_delta < 0:
                pyro_bonus = apply_card_pyro_rebirth(c, target_id, f"admin_points: {reason}", abs(actual_delta))
                if pyro_bonus:
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
            return {
                "full_name": row[0] or str(target_id),
                "previous_points": previous_points,
                "new_points": new_points,
                "actual_delta": actual_delta,
                "blocked_by_implant": blocked_by_implant,
                "pyro_bonus": pyro_bonus,
            }
        finally:
            conn.close()

    result = await db_write(_run)
    if result is None:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "success": True,
        "telegram_id": target_id,
        "full_name": result["full_name"],
        "previous_points": result["previous_points"],
        "new_points": result["new_points"],
        "delta": result["actual_delta"],
        "requested_delta": requested_delta,
        "blocked_by_implant": "implant_terracota" if result["blocked_by_implant"] else None,
        "card_pyro_bonus": result["pyro_bonus"],
    }


@app.post("/api/internal/points/add")
async def internal_add_points(data: dict, request: Request):
    if not request_has_internal_token(request):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        target_id = int(data.get("telegram_id"))
        delta = int(data.get("delta"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid payload")

    operation = str(data.get("operation") or "bot_manual")
    note = data.get("note")

    def _run():
        conn = get_conn()
        try:
            c = conn.cursor()
            c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (delta, target_id))
            c.execute("SELECT points FROM users WHERE telegram_id=?", (target_id,))
            row = c.fetchone()
            if not row:
                return None
            new_points = row[0]
            log_economy(c, target_id, operation, delta, new_points, reference_type='bot', note=note)
            conn.commit()
            return new_points
        finally:
            conn.close()

    new_points = await db_write(_run)
    if new_points is None:
        raise HTTPException(status_code=404, detail="User not found")

    return {"success": True, "telegram_id": target_id, "new_points": new_points}


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

    def _run():
        conn = get_conn()
        try:
            c = conn.cursor()
            c.execute("SELECT full_name, points, rep_score FROM users WHERE telegram_id=?", (target_id,))
            row = c.fetchone()
            if not row:
                return None

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
            return {
                "full_name": row[0] or str(target_id),
                "points": new_points,
                "previous_rep": previous_rep,
                "new_rep": new_rep,
                "actual_delta": actual_delta,
            }
        finally:
            conn.close()

    result = await db_write(_run)
    if result is None:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "success": True,
        "telegram_id": target_id,
        "full_name": result["full_name"],
        "points": result["points"],
        "previous_rep_score": result["previous_rep"],
        "new_rep_score": result["new_rep"],
        "delta": result["actual_delta"],
        "requested_delta": delta,
    }


@app.get("/api/admin/actions")
def admin_action_log(limit: int = 30, x_admin_id: Optional[int] = Header(None)):
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
    def _run():
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
    return await db_write(_run)


@app.post("/api/presence/admin/dispatch")
async def dispatch_presence_check(data: dict, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    check_type = normalize_presence_check_type(data.get("check_type"))
    check_date = new_manual_presence_session() if check_type == "manual" and not data.get("check_date") else normalize_presence_date(data.get("check_date"))
    attempt_no = int(data.get("attempt_no") or 1)
    note = str(data.get("note") or f"admin dispatch attempt {attempt_no}").strip()
    target_ids = data.get("telegram_ids")

    def _prepare():
        conn = get_conn()
        c = conn.cursor()
        try:
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
            return eligible, skipped
        finally:
            conn.close()

    eligible, skipped = await db_write(_prepare)

    sent = []
    failed = []
    markup = get_presence_keyboard_markup(check_type, check_date)
    text = get_presence_message_text(check_type, attempt_no)
    for telegram_id in eligible:
        ok, response = await send_telegram_message(telegram_id, text, markup)
        if ok:
            sent.append(telegram_id)
        else:
            failed.append({"telegram_id": telegram_id, "error": response})

    if sent:
        def _mark_sent():
            conn = get_conn()
            c = conn.cursor()
            try:
                now = now_iso()
                for telegram_id in sent:
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
            finally:
                conn.close()
        await db_write(_mark_sent)

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
def get_presence_status(check_type: str, telegram_id: int, check_date: Optional[str] = None):
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

    def _run():
        conn = get_conn()
        try:
            c = conn.cursor()
            c.execute("SELECT telegram_id FROM users WHERE telegram_id=?", (telegram_id,))
            if not c.fetchone():
                return {"error": "User not found", "status": 404}

            previous_row = fetch_presence_row(c, check_type, check_date, telegram_id)
            row = None
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
                is_new_confirm = not previous_row or previous_row["status"] not in PRESENCE_SAFE_STATUSES
                if check_type in {"morning", "evening"} and is_new_confirm:
                    if has_active_card(c, telegram_id, "card_fairy") and not has_used_card_today(c, telegram_id, "card_fairy", f"presence:{check_type}", check_date):
                        mark_card_used_today(c, telegram_id, "card_fairy", f"presence:{check_type}", check_date)
                        c.execute("UPDATE users SET points = points + 15 WHERE telegram_id=?", (telegram_id,))
                        c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
                        balance_after = c.fetchone()[0] or 0
                        log_economy(
                            c, telegram_id, "card_fairy_blessing", 15, balance_after,
                            None, "card", f"{check_type} {check_date}",
                        )
                if check_type == "evening" and is_new_confirm:
                    c.execute(
                        """SELECT 1 FROM daily_checks
                           WHERE telegram_id=? AND check_date=? AND check_type='morning'
                             AND status IN ('confirmed','free_time','admin_approved')""",
                        (telegram_id, check_date),
                    )
                    if c.fetchone():
                        grant_card_points_once(
                            c, telegram_id, "card_fairy", f"perfect_day:{check_date}", 15,
                            "card_fairy_perfect_day", f"утро+вечер {check_date}", check_date,
                        )
                if check_type == "morning" and is_new_confirm:
                    if has_active_card(c, telegram_id, "card_forest") and not has_used_card_today(c, telegram_id, "card_forest", "morning_harvest", check_date):
                        mark_card_used_today(c, telegram_id, "card_forest", "morning_harvest", check_date)
                        c.execute("UPDATE users SET points = points + 10 WHERE telegram_id=?", (telegram_id,))
                        c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
                        balance_after = c.fetchone()[0] or 0
                        log_economy(
                            c, telegram_id, "card_forest_harvest", 10, balance_after,
                            None, "card", check_date,
                        )
                if check_type == "manual" and is_new_confirm:
                    today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
                    grant_card_points_once(
                        c, telegram_id, "card_forest", "manual_anchor", 8,
                        "card_forest_anchor", f"ручная перекличка {check_date}", today,
                    )
                if check_type == "evening" and is_new_confirm:
                    grant_card_scan_once(
                        c, telegram_id, "card_moon", f"evening_scan:{check_date}",
                        "card_moon_lunar_path", f"вечерняя отметка {check_date}", check_date,
                    )
                if check_type in {"morning", "evening"} and is_new_confirm:
                    c.execute("""INSERT INTO user_status (telegram_id, scan_attempts) VALUES (?,1)
                                 ON CONFLICT(telegram_id) DO UPDATE SET scan_attempts=MIN(7, scan_attempts+1)""",
                              (telegram_id,))
            elif action == "request_leave":
                row = apply_presence_status(c, check_type, check_date, telegram_id, "leave_requested", note)
            elif action == "free_time":
                purchase_id = has_active_free_time(c, telegram_id)
                if not purchase_id:
                    return {"error": "No active free time", "status": 400}
                row = apply_presence_status(
                    c,
                    check_type,
                    check_date,
                    telegram_id,
                    "free_time",
                    note or f"casino_walk purchase #{purchase_id}",
                )
            else:
                return {"error": "Invalid action", "status": 400}

            conn.commit()
            return {"check": row}
        finally:
            conn.close()

    result = await db_write(_run)
    if "error" in result:
        raise HTTPException(status_code=result["status"], detail=result["error"])

    return {"success": True, "check": result["check"]}


@app.post("/api/presence/attempt")
async def mark_presence_attempt(data: dict, x_admin_id: Optional[int] = Header(None)):
    def _run():
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
    return await db_write(_run)


@app.post("/api/presence/admin/approve")
async def approve_presence_leave(data: dict, x_admin_id: Optional[int] = Header(None)):
    def _run():
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
    return await db_write(_run)


@app.post("/api/presence/admin/reject")
async def reject_presence_leave(data: dict, x_admin_id: Optional[int] = Header(None)):
    def _run():
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
    return await db_write(_run)


@app.post("/api/presence/admin/escalate")
async def escalate_presence_check(data: dict, x_admin_id: Optional[int] = Header(None)):
    def _run():
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
    return await db_write(_run)


@app.post("/api/presence/admin/cancel")
async def cancel_presence_check(data: dict, x_admin_id: Optional[int] = Header(None)):
    def _run():
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
    return await db_write(_run)


@app.post("/api/presence/admin/penalize")
async def penalize_presence_check(data: dict, x_admin_id: Optional[int] = Header(None)):
    def _run():
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
            effective_penalty = max(
                0,
                penalty
                - consume_terracota_armor(c, telegram_id)
                - consume_card_penalty_reduction(c, telegram_id, f"presence: {check_type} {check_date}"),
            )
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
            pyro_bonus = 0
            if actual_delta < 0:
                pyro_bonus = apply_card_pyro_rebirth(c, telegram_id, f"presence: {check_type} {check_date}", abs(actual_delta))
                if pyro_bonus:
                    c.execute("SELECT points, rep_score FROM users WHERE telegram_id=?", (telegram_id,))
                    updated_user = c.fetchone() or (new_points, new_rep)
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
                "card_pyro_bonus": pyro_bonus,
            })
        conn.commit()
        conn.close()
        return {"success": True, "penalized": penalized}
    return await db_write(_run)


@app.get("/api/presence/admin/overview")
def presence_admin_overview(check_type: str, check_date: Optional[str] = None, x_admin_id: Optional[int] = Header(None)):
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
def diary_admin_overview(entry_date: Optional[str] = None, x_admin_id: Optional[int] = Header(None)):
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
def get_diary_stars_overview(entry_date: str, x_telegram_id: Optional[int] = Header(None), x_admin_id: Optional[int] = Header(None)):
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

    is_reset = bool(data.get("reset", False))
    is_remove_bonus = bool(data.get("remove_bonus", False))
    incoming_stars = data.get("stars")
    incoming_bonus = bool(data.get("bonus", False))
    if not is_reset and incoming_stars is not None:
        try:
            incoming_stars = int(incoming_stars)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid stars")
        if incoming_stars not in (0, 1, 2, 3):
            raise HTTPException(status_code=400, detail="Invalid stars")

    def _run():
        conn = get_conn()
        try:
            c = conn.cursor()
            c.execute("SELECT 1 FROM users WHERE telegram_id=?", (telegram_id,))
            if not c.fetchone():
                return {"error": "User not found"}

            c.execute("SELECT stars, bonus FROM diary_stars WHERE telegram_id=? AND entry_date=?", (telegram_id, entry_date))
            previous = c.fetchone()
            previous_stars = previous[0] if previous else 0
            previous_bonus = previous[1] if previous else 0

            if is_reset:
                next_stars = 0
                next_bonus = 0
            elif is_remove_bonus:
                next_stars = previous_stars
                next_bonus = 0
            else:
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
            literature_bonus = 0
            if (
                next_stars == 3
                and previous_stars < 3
                and has_active_card(c, telegram_id, "card_literature")
                and not has_used_card_today(c, telegram_id, "card_literature", "diary_3star", entry_date)
            ):
                mark_card_used_today(c, telegram_id, "card_literature", "diary_3star", entry_date)
                c.execute("UPDATE users SET points = points + 20 WHERE telegram_id=?", (telegram_id,))
                c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
                balance_after = c.fetchone()[0] or 0
                log_economy(c, telegram_id, "card_literature_wisdom", 20, balance_after, None, "card", entry_date)
                literature_bonus = 20
            if next_bonus and not previous_bonus:
                literature_bonus += grant_card_points_once(
                    c, telegram_id, "card_literature", f"bonus_line:{entry_date}", 15,
                    "card_literature_bonus_line", f"бонус дневника {entry_date}", entry_date,
                )
            star_diary_bonus = 0
            if next_stars == 3 and previous_stars < 3:
                star_diary_bonus = grant_card_points_once(
                    c, telegram_id, "card_star", f"diary_constellation:{entry_date}", 10,
                    "card_star_constellation", f"дневник 3★ {entry_date}", entry_date,
                )
            if (
                next_stars == 3
                and has_active_implant(c, telegram_id, "implant_linguasoft")
                and not has_used_implant_today(c, telegram_id, "implant_linguasoft", f"streak3:{entry_date}")
            ):
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
            if next_stars == 3 and previous_stars < 3:
                c.execute("""INSERT INTO user_status (telegram_id, scan_attempts) VALUES (?,1)
                             ON CONFLICT(telegram_id) DO UPDATE SET scan_attempts=MIN(7, scan_attempts+1)""",
                          (telegram_id,))
            conn.commit()
            return {
                "next_stars": next_stars,
                "next_bonus": next_bonus,
                "next_points": next_points,
                "previous_points": previous_points,
                "linguasoft_bonus": linguasoft_bonus,
                "literature_bonus": literature_bonus,
                "star_diary_bonus": star_diary_bonus,
            }
        finally:
            conn.close()

    result = await db_write(_run)
    if isinstance(result, dict) and "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return {
        "success": True,
        "telegram_id": telegram_id,
        "entry_date": entry_date,
        "stars": result["next_stars"],
        "bonus": bool(result["next_bonus"]),
        "points_awarded": result["next_points"],
        "points_delta": result["next_points"] - result["previous_points"],
        "implant_bonus": result["linguasoft_bonus"],
        "card_bonus": result["literature_bonus"] + result["star_diary_bonus"],
    }


@app.get("/api/diary/stars/leaderboard")
def get_diary_stars_leaderboard(x_telegram_id: Optional[int] = Header(None), x_admin_id: Optional[int] = Header(None)):
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
def get_diary_entries(telegram_id: int, x_telegram_id: Optional[int] = Header(None), x_admin_id: Optional[int] = Header(None)):
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
def get_diary_entry(telegram_id: int, entry_date: str, x_telegram_id: Optional[int] = Header(None), x_admin_id: Optional[int] = Header(None)):
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
    def _run():
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
    return await db_write(_run)


@app.post("/api/diary/submit")
async def submit_diary_entry(data: dict, x_telegram_id: Optional[int] = Header(None), x_admin_id: Optional[int] = Header(None)):
    def _run():
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
    return await db_write(_run)


@app.post("/api/diary/score")
async def score_diary_entry(data: dict, x_admin_id: Optional[int] = Header(None)):
    def _run():
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
    return await db_write(_run)


@app.post("/api/diary/lock")
async def lock_diary_entry(data: dict, x_admin_id: Optional[int] = Header(None)):
    def _run():
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
    return await db_write(_run)


@app.get("/api/leaderboard")
async def get_leaderboard():
    today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
    placeholders = ','.join('?' * len(ADMIN_IDS))
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        f'''SELECT u.full_name, u.rep_score, u.telegram_id, u.avatar_url, us.theme_path,
                 CASE WHEN us.title_date=? THEN 1 ELSE 0 END as has_title,
                 us.equipped_frame,
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

    # Динамика рейтинга: сравнение с последним сохранённым срезом
    c.execute("SELECT MAX(snapshot_date) FROM leaderboard_snapshots WHERE snapshot_date < ?", (today,))
    prev_date_row = c.fetchone()
    prev_date = prev_date_row[0] if prev_date_row else None
    prev_ranks = {}
    if prev_date:
        c.execute("SELECT telegram_id, rank FROM leaderboard_snapshots WHERE snapshot_date=?", (prev_date,))
        prev_ranks = {row[0]: row[1] for row in c.fetchall()}

    c.execute("SELECT 1 FROM leaderboard_snapshots WHERE snapshot_date=? LIMIT 1", (today,))
    has_today_snapshot = c.fetchone() is not None
    conn.close()

    if not has_today_snapshot:
        def _snapshot():
            conn2 = get_conn()
            try:
                c2 = conn2.cursor()
                c2.execute(
                    f'''INSERT OR IGNORE INTO leaderboard_snapshots (telegram_id, rank, rep, snapshot_date)
                        SELECT telegram_id, ROW_NUMBER() OVER (ORDER BY rep_score DESC), rep_score, ?
                        FROM users
                        WHERE telegram_id IS NOT NULL AND telegram_id NOT IN ({placeholders})''',
                    [today] + ADMIN_IDS,
                )
                conn2.commit()
            finally:
                conn2.close()
        await db_write(_snapshot)

    out = []
    for i, r in enumerate(result):
        telegram_id = r[2]
        prev_rank = prev_ranks.get(telegram_id)
        rank_delta = (prev_rank - (i + 1)) if prev_rank is not None else None
        out.append({
            "name": r[0] or "Аноним",
            "rep": r[1] or 0,
            "telegram_id": telegram_id,
            "avatar_url": r[3],
            "theme_path": r[4],
            "has_title": bool(r[5]),
            "equipped_frame": r[6] if r[6] in FRAME_IDS else None,
            "implant": r[7],
            "card": r[8],
            "rank_delta": rank_delta,
        })
    return out


@app.get("/api/frames/{telegram_id}")
def get_user_frames(telegram_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT 1 FROM users WHERE telegram_id=?", (telegram_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    unlocked = set(compute_unlocked_frames(c, telegram_id))
    c.execute("SELECT equipped_frame FROM user_status WHERE telegram_id=?", (telegram_id,))
    row = c.fetchone()
    equipped = row[0] if row and row[0] in unlocked else None
    conn.close()

    return {
        "equipped": equipped,
        "frames": [
            {
                "id": f["id"],
                "name": f["name"],
                "desc": f["desc"],
                "category": f["category"],
                "unlocked": f["id"] in unlocked,
            }
            for f in FRAME_DEFINITIONS
        ],
    }


@app.post("/api/frames/equip")
async def equip_frame(data: dict):
    telegram_id = data.get("telegram_id")
    frame_id = data.get("frame_id")
    if not telegram_id:
        raise HTTPException(status_code=400, detail="No telegram_id")
    if frame_id is not None and frame_id not in FRAME_IDS:
        raise HTTPException(status_code=400, detail="Unknown frame")

    def _run():
        conn = get_conn()
        try:
            c = conn.cursor()
            c.execute("SELECT 1 FROM users WHERE telegram_id=?", (telegram_id,))
            if not c.fetchone():
                raise HTTPException(status_code=404, detail="User not found")

            if frame_id is not None:
                unlocked = set(compute_unlocked_frames(c, telegram_id))
                if frame_id not in unlocked:
                    raise HTTPException(status_code=403, detail="Frame not unlocked")

            c.execute(
                '''INSERT INTO user_status (telegram_id, equipped_frame) VALUES (?, ?)
                   ON CONFLICT(telegram_id) DO UPDATE SET equipped_frame=excluded.equipped_frame''',
                (telegram_id, frame_id),
            )
            conn.commit()
            return frame_id
        finally:
            conn.close()

    equipped = await db_write(_run)
    return {"success": True, "equipped": equipped}


@app.get("/api/achievements/{telegram_id}")
def get_user_achievements(telegram_id: int):
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
    def _run():
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
    return await db_write(_run)

@app.get("/api/user/scans/{telegram_id}")
def get_user_scans(telegram_id: int):
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

    def _run():
        conn = get_conn()
        try:
            c = conn.cursor()
            c.execute("SELECT 1 FROM users WHERE telegram_id=?", (telegram_id,))
            if not c.fetchone():
                return {"error": "User not found", "status": 404}

            now_beijing = datetime.now(BEIJING_TZ)
            today = now_beijing.strftime('%Y-%m-%d')

            if telegram_id not in ADMIN_IDS:
                c.execute("SELECT scan_attempts FROM user_status WHERE telegram_id=?", (telegram_id,))
                row = c.fetchone()
                attempts = row[0] if row else 0
                if attempts <= 0:
                    return {"error": "No scan attempts remaining", "status": 400}

            now_str = now_beijing.strftime('%Y-%m-%d %H:%M:%S')

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
            doubled_win = False
            if prize.get("points", 0) > 0:
                c.execute("SELECT double_win FROM user_status WHERE telegram_id=?", (telegram_id,))
                dw_row = c.fetchone()
                if dw_row and dw_row[0]:
                    prize["points"] *= 2
                    prize["name"] = f'{prize["name"]} ×2'
                    doubled_win = True
                    c.execute("UPDATE user_status SET double_win=0 WHERE telegram_id=?", (telegram_id,))
                c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (prize["points"], telegram_id))

            c.execute("INSERT INTO casino_log (telegram_id, date, prize, created_at) VALUES (?,?,?,?)", (telegram_id, today, prize["code"], now_str))
            c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
            new_points = c.fetchone()[0]
            c.execute("SELECT scan_attempts, protocol_fragments FROM user_status WHERE telegram_id=?", (telegram_id,))
            scan_row = c.fetchone()
            log_economy(c, telegram_id, 'case_open', 0, new_points, None, prize.get("case_type") or "case", prize.get("name") or prize.get("code"))
            if doubled_win:
                log_economy(c, telegram_id, 'double_win_consumed', 0, new_points, None, "shop_item", "Двойной выигрыш")
            conn.commit()
            return {
                "new_points": new_points,
                "scan_attempts": scan_row[0] if scan_row else 0,
                "protocol_fragments": scan_row[1] if scan_row else 0,
                "doubled_win": doubled_win,
            }
        finally:
            conn.close()

    result = await db_write(_run)
    if "error" in result:
        raise HTTPException(status_code=result["status"], detail=result["error"])

    return {
        "prize": prize,
        "new_points": result["new_points"],
        "scan_attempts": result["scan_attempts"],
        "protocol_fragments": result["protocol_fragments"],
        "doubled_win": result["doubled_win"],
    }


@app.get("/api/casino/status/{telegram_id}")
def get_casino_status(telegram_id: int):
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
def get_casino_history(telegram_id: int):
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
    def _run():
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
    return await db_write(_run)


@app.get("/api/casino/implants/{telegram_id}")
def get_implants(telegram_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT id, implant_id, durability, obtained_at FROM user_implants
                 WHERE telegram_id=? AND durability > 0
                 ORDER BY obtained_at DESC""", (telegram_id,))
    rows = c.fetchall()
    conn.close()
    implant_info = {
        "implant_guanxi": {"name": "Гуаньси 关系", "icon": "🤝", "desc": "Скидка 10% в магазине · в ивентах: +1 поддержка при Синхронизации"},
        "implant_terracota": {"name": "Терракота 兵马俑", "icon": "🗿", "desc": "Блок 1 штрафа в день · после блока следующий штраф −5★ · в ивентах: -20% к росту перегрузки/заражения при ошибке"},
        "implant_panda": {"name": "Панда 🐼", "icon": "🐼", "desc": "Кэшбек +10★ с покупки · продажа за 60% вместо 50% · в ивентах: +1 поддержка при Синхронизации/Стабилизации"},
        "implant_shaolin": {"name": "Шаолинь 少林", "icon": "🥋", "desc": "+20★ за перекличку вовремя · идеальный день (утро+вечер) ещё +10★ · в ивентах: +10% урона на Атаке"},
        "implant_linguasoft": {"name": "Linguasoft 口才", "icon": "🎙", "desc": "+30★ за 3★ в дневнике · серия из 3 дневников на 3★ ещё +20★ · в ивентах: +10% урона на Протоколе"},
        "implant_caishen": {"name": "Цайшэнь 财神", "icon": "💰", "desc": "+15★ каждые 24 часа · в ивентах: +2 поддержка при Стабилизации"},
        "implant_qilin": {"name": "Цилинь 麒麟", "icon": "🐉", "desc": "+10★ за каждого владельца Цилиня · в ивентах: +5% урона команде, если 2+ с этим имплантом"},
        "implant_red_dragon": {"name": "Красный Дракон 红龙", "icon": "🐉", "desc": "+20% наградных · x2 зарплата по вс · перехват · сбросить импульс · в ивентах: +20% урона на Атаке/Протоколе"},
        "implant_netwatch": {"name": "Сетевой Дозор 网络守卫", "icon": "🔴", "desc": "+25★ каждое утро · форматирование · взлом заслона · в ивентах: удачная Синхронизация продлевает окно уязвимости на +30с"},
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
def get_legendary_implant_status(telegram_id: int):
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


@app.get("/api/cards/legendary/status/{telegram_id}")
def get_legendary_card_status(telegram_id: int):
    conn = get_conn()
    c = conn.cursor()
    result = {}
    for action_code, card_id in {
        "fate_verdict": "card_star",
        "star_ward": "card_star",
        "earth_contract": "card_zhongli",
        "okamenenie": "card_zhongli",
    }.items():
        cooldown_until = legendary_cooldown_until(c, telegram_id, action_code)
        result[action_code] = {
            "available": has_active_card(c, telegram_id, card_id),
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

    def _run():
        conn = get_conn()
        c = conn.cursor()
        try:
            ensure_legendary_action_ready(c, actor_id, "implant_red_dragon", "intercept")
            tid, tname, target_points = find_action_target(c, actor_id, target_id, target_name)
            if target_points < 80:
                raise HTTPException(status_code=400, detail="Target balance below 80")
            cutoff = (datetime.now(BEIJING_TZ) - timedelta(days=3)).strftime('%Y-%m-%d %H:%M:%S')
            c.execute(
                '''SELECT 1 FROM legendary_implant_actions
                   WHERE actor_telegram_id=? AND target_telegram_id=? AND action_code='intercept'
                     AND created_at>=? LIMIT 1''',
                (actor_id, tid, cutoff),
            )
            if c.fetchone():
                raise HTTPException(status_code=429, detail="Target protected for 3 days")
            c.execute("UPDATE users SET points = points - 10 WHERE telegram_id=?", (tid,))
            c.execute("UPDATE users SET points = points + 10 WHERE telegram_id=?", (actor_id,))
            c.execute("SELECT points FROM users WHERE telegram_id=?", (tid,))
            target_balance = c.fetchone()[0] or 0
            c.execute("SELECT points FROM users WHERE telegram_id=?", (actor_id,))
            actor_balance = c.fetchone()[0] or 0
            log_economy(c, tid, "red_dragon_intercept_loss", -10, target_balance, actor_id, "implant", "Перехват")
            log_economy(c, actor_id, "red_dragon_intercept_gain", 10, actor_balance, tid, "implant", "Перехват")
            log_legendary_action(c, actor_id, tid, None, "implant_red_dragon", "intercept", 10, 0, tname)
            conn.commit()
            return tid, tname, actor_balance
        finally:
            conn.close()

    target_id, target_name, actor_balance = await db_write(_run)
    await send_telegram_message(target_id, "🐉 Красный Дракон активировал «Перехват».\nС вашего баланса снято 10★.")
    return {"success": True, "target": target_name, "stolen": 10, "new_points": actor_balance}


@app.post("/api/implants/red-dragon/impulse-reset")
async def red_dragon_impulse_reset(data: dict):
    def _run():
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
    return await db_write(_run)


@app.post("/api/implants/netwatch/formatting")
async def netwatch_formatting(data: dict):
    actor_id = int(data.get("telegram_id") or 0)
    target_id = data.get("target_telegram_id")
    target_name = data.get("target_name")
    if not actor_id:
        raise HTTPException(status_code=400, detail="telegram_id required")

    def _run():
        conn = get_conn()
        c = conn.cursor()
        try:
            ensure_legendary_action_ready(c, actor_id, "implant_netwatch", "formatting")
            tid, tname, target_points = find_action_target(c, actor_id, target_id, target_name)
            if target_points < 80:
                raise HTTPException(status_code=400, detail="Target balance below 80")
            c.execute(
                '''SELECT telegram_id, full_name, COALESCE(points, 0)
                   FROM users
                   WHERE telegram_id NOT IN (?, ?)
                     AND telegram_id NOT IN ({})
                     AND COALESCE(points, 0) >= 80
                   ORDER BY RANDOM()
                   LIMIT 1'''.format(','.join('?' * len(ADMIN_IDS))),
                [actor_id, tid] + ADMIN_IDS,
            )
            secondary = c.fetchone()
            secondary_id = secondary[0] if secondary else None
            secondary_name = secondary[1] if secondary else None
            c.execute("UPDATE users SET points = points - 15 WHERE telegram_id=?", (tid,))
            c.execute("SELECT points FROM users WHERE telegram_id=?", (tid,))
            target_balance = c.fetchone()[0] or 0
            log_economy(c, tid, "netwatch_formatting", -15, target_balance, actor_id, "implant", "Форматирование")
            secondary_delta = 0
            if secondary_id:
                c.execute("UPDATE users SET points = points - 5 WHERE telegram_id=?", (secondary_id,))
                c.execute("SELECT points FROM users WHERE telegram_id=?", (secondary_id,))
                secondary_balance = c.fetchone()[0] or 0
                log_economy(c, secondary_id, "netwatch_formatting_collateral", -5, secondary_balance, actor_id, "implant", "Побочный урон")
                secondary_delta = -5
            log_legendary_action(c, actor_id, tid, secondary_id, "implant_netwatch", "formatting", -15, secondary_delta, tname)
            conn.commit()
            return tid, tname, secondary_id, secondary_name
        finally:
            conn.close()

    target_id, target_name, secondary_id, secondary_name = await db_write(_run)
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

    def _run():
        conn = get_conn()
        c = conn.cursor()
        try:
            ensure_legendary_action_ready(c, actor_id, "implant_netwatch", "veil_breach")
            tid, tname, _ = find_action_target(c, actor_id, target_id, target_name)
            cutoff = (datetime.now(BEIJING_TZ) - timedelta(days=14)).strftime('%Y-%m-%d %H:%M:%S')
            c.execute(
                '''SELECT 1 FROM legendary_implant_actions
                   WHERE actor_telegram_id=? AND target_telegram_id=? AND action_code='veil_breach'
                     AND created_at>=? LIMIT 1''',
                (actor_id, tid, cutoff),
            )
            if c.fetchone():
                raise HTTPException(status_code=429, detail="Target protected for 14 days")
            lu = (datetime.now(BEIJING_TZ) + timedelta(hours=12)).strftime('%Y-%m-%d %H:%M:%S')
            c.execute(
                '''INSERT INTO user_status (telegram_id, netwatch_locked_until) VALUES (?, ?)
                   ON CONFLICT(telegram_id) DO UPDATE SET netwatch_locked_until=excluded.netwatch_locked_until''',
                (tid, lu),
            )
            log_legendary_action(c, actor_id, tid, None, "implant_netwatch", "veil_breach", 0, 0, tname)
            conn.commit()
            return tid, tname, lu
        finally:
            conn.close()

    target_id, target_name, locked_until = await db_write(_run)
    await send_telegram_message(
        target_id,
        "🔴 NetWatch активировал «Взлом Заслона».\n"
        "Магазин и кейсы временно недоступны на 12 часов.",
    )
    return {"success": True, "target": target_name, "locked_until": locked_until}


@app.post("/api/cards/star/fate-verdict")
async def star_fate_verdict(data: dict):
    actor_id = int(data.get("telegram_id") or 0)
    target_id = data.get("target_telegram_id")
    target_name = data.get("target_name")
    if not actor_id:
        raise HTTPException(status_code=400, detail="telegram_id required")
    async with DB_WRITE_LOCK:
        conn = get_conn()
        c = conn.cursor()
        ensure_legendary_action_ready(c, actor_id, "card_star", "fate_verdict")
        target_id, target_name, target_points = find_action_target(c, actor_id, target_id, target_name)
        if target_points < 80:
            conn.close()
            raise HTTPException(status_code=400, detail="Target balance below 80")
        cutoff = (datetime.now(BEIJING_TZ) - timedelta(days=3)).strftime('%Y-%m-%d %H:%M:%S')
        c.execute(
            '''SELECT 1 FROM legendary_implant_actions
               WHERE actor_telegram_id=? AND target_telegram_id=? AND action_code='fate_verdict'
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
        log_economy(c, target_id, "star_fate_verdict_loss", -10, target_balance, actor_id, "card", "Предсказание судьбы")
        log_economy(c, actor_id, "star_fate_verdict_gain", 10, actor_balance, target_id, "card", "Предсказание судьбы")
        log_legendary_action(c, actor_id, target_id, None, "card_star", "fate_verdict", 10, 0, target_name)
        conn.commit()
        conn.close()
    await send_telegram_message(target_id, "⭐ Звёздная карта вынесла «Предсказание судьбы».\nС вашего баланса снято 10★.")
    return {"success": True, "target": target_name, "stolen": 10, "new_points": actor_balance}


@app.post("/api/cards/star/ward")
async def star_ward(data: dict):
    def _run():
        actor_id = int(data.get("telegram_id") or 0)
        if not actor_id:
            raise HTTPException(status_code=400, detail="telegram_id required")
        conn = get_conn()
        c = conn.cursor()
        ensure_legendary_action_ready(c, actor_id, "card_star", "star_ward")
        c.execute(
            '''SELECT id, operation, amount, note
               FROM economy_log
               WHERE telegram_id=? AND amount < 0 AND amount >= -20
                 AND reference_type IN ('event', 'casino_game')
                 AND NOT EXISTS (
                   SELECT 1 FROM economy_log resets
                   WHERE resets.operation='star_ward'
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
        log_economy(c, actor_id, "star_ward", refund, balance, penalty_id, "card", note or operation)
        log_legendary_action(c, actor_id, actor_id, None, "card_star", "star_ward", refund, 0, note or operation)
        conn.commit()
        conn.close()
        return {"success": True, "refunded": refund, "new_points": balance}
    return await db_write(_run)


@app.post("/api/cards/zhongli/earth-contract")
async def zhongli_earth_contract(data: dict):
    actor_id = int(data.get("telegram_id") or 0)
    target_id = data.get("target_telegram_id")
    target_name = data.get("target_name")
    if not actor_id:
        raise HTTPException(status_code=400, detail="telegram_id required")
    async with DB_WRITE_LOCK:
        conn = get_conn()
        c = conn.cursor()
        ensure_legendary_action_ready(c, actor_id, "card_zhongli", "earth_contract")
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
        c.execute("UPDATE users SET points = points + 15 WHERE telegram_id=?", (actor_id,))
        c.execute("SELECT points FROM users WHERE telegram_id=?", (target_id,))
        target_balance = c.fetchone()[0] or 0
        c.execute("SELECT points FROM users WHERE telegram_id=?", (actor_id,))
        actor_balance = c.fetchone()[0] or 0
        log_economy(c, target_id, "zhongli_earth_contract_loss", -15, target_balance, actor_id, "card", "Контракт Земли")
        log_economy(c, actor_id, "zhongli_earth_contract_gain", 15, actor_balance, target_id, "card", "Контракт Земли")
        secondary_delta = 0
        if secondary_id:
            c.execute("UPDATE users SET points = points - 5 WHERE telegram_id=?", (secondary_id,))
            c.execute("UPDATE users SET points = points + 5 WHERE telegram_id=?", (actor_id,))
            c.execute("SELECT points FROM users WHERE telegram_id=?", (secondary_id,))
            secondary_balance = c.fetchone()[0] or 0
            log_economy(c, secondary_id, "zhongli_earth_contract_collateral", -5, secondary_balance, actor_id, "card", "Побочная дань")
            c.execute("SELECT points FROM users WHERE telegram_id=?", (actor_id,))
            actor_balance = c.fetchone()[0] or 0
            log_economy(c, actor_id, "zhongli_earth_contract_gain", 5, actor_balance, secondary_id, "card", "Побочная дань")
            secondary_delta = -5
        log_legendary_action(c, actor_id, target_id, secondary_id, "card_zhongli", "earth_contract", 15, secondary_delta, target_name)
        conn.commit()
        conn.close()
    await send_telegram_message(target_id, "🪨 Архонт Земли заключил «Контракт Земли».\nС вашего баланса снято 15★ дани.")
    if secondary_id:
        await send_telegram_message(secondary_id, "🪨 Побочная дань Контракта Земли.\nС вашего баланса снято 5★.")
    return {
        "success": True,
        "target": target_name,
        "damage": 15,
        "secondary_target": secondary_name,
        "secondary_damage": 5 if secondary_id else 0,
    }


@app.post("/api/cards/zhongli/okamenenie")
async def zhongli_okamenenie(data: dict):
    actor_id = int(data.get("telegram_id") or 0)
    target_id = data.get("target_telegram_id")
    target_name = data.get("target_name")
    if not actor_id:
        raise HTTPException(status_code=400, detail="telegram_id required")
    async with DB_WRITE_LOCK:
        conn = get_conn()
        c = conn.cursor()
        ensure_legendary_action_ready(c, actor_id, "card_zhongli", "okamenenie")
        target_id, target_name, _ = find_action_target(c, actor_id, target_id, target_name)
        cutoff = (datetime.now(BEIJING_TZ) - timedelta(days=14)).strftime('%Y-%m-%d %H:%M:%S')
        c.execute(
            '''SELECT 1 FROM legendary_implant_actions
               WHERE actor_telegram_id=? AND target_telegram_id=? AND action_code='okamenenie'
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
        log_legendary_action(c, actor_id, target_id, None, "card_zhongli", "okamenenie", 0, 0, target_name)
        conn.commit()
        conn.close()
    await send_telegram_message(
        target_id,
        "🪨 Архонт Земли применил «Окаменение».\n"
        "Магазин и молитвы временно недоступны на 12 часов.",
    )
    return {"success": True, "target": target_name, "locked_until": locked_until}


@app.post("/api/casino/implants/disassemble/{implant_id}")
async def disassemble_implant(implant_id: int, data: dict):
    def _run():
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
    return await db_write(_run)


@app.post("/api/casino/use/{purchase_id}")
async def use_casino_prize(purchase_id: int, data: dict):
    def _run():
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
    return await db_write(_run)


@app.get("/api/shop")
def get_shop(telegram_id: int = 0):
    today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
    conn = get_conn()
    c = conn.cursor()
    is_frozen = user_netwatch_locked(c, telegram_id)
    c.execute("SELECT code, name, description, icon, price, daily_limit, category FROM shop_items WHERE active=1")
    items = c.fetchall()
    result = []
    has_guanxi = has_active_implant(c, telegram_id, "implant_guanxi") if telegram_id else False
    has_zhongli = has_active_card(c, telegram_id, "card_zhongli") if telegram_id else False
    for code, name, description, icon, price, daily_limit, category in items:
        effective_price = price
        if has_guanxi:
            effective_price = max(0, int(effective_price * 0.9))
        if has_zhongli:
            effective_price = max(0, int(effective_price * 0.93))
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
            "discounted": bool(effective_price != price),
            "discount_sources": {
                "guanxi": has_guanxi,
                "zhongli": has_zhongli,
            },
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
    if not telegram_id or not item_code:
        raise HTTPException(status_code=400, detail="Missing data")

    def _run():
        today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
        conn = get_conn()
        try:
            c = conn.cursor()
            if user_netwatch_locked(c, telegram_id):
                return {"error": "Account frozen", "status": 403}

            c.execute("SELECT name, price, daily_limit, category FROM shop_items WHERE code=? AND active=1", (item_code,))
            item = c.fetchone()
            if not item:
                return {"error": "Item not found", "status": 404}
            name, price, daily_limit, category = item
            base_price = price
            if has_active_implant(c, telegram_id, "implant_guanxi"):
                price = max(0, int(price * 0.9))
            price_after_guanxi = price
            if has_active_card(c, telegram_id, "card_zhongli"):
                price = max(0, int(price * 0.93))

            if daily_limit != -1:
                c.execute("SELECT count FROM shop_daily_counts WHERE item_code=? AND date=?", (item_code, today))
                row = c.fetchone()
                if row and row[0] >= daily_limit:
                    return {"error": "Daily limit reached", "status": 409}

            c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
            user = c.fetchone()
            if not user or (user[0] or 0) < price:
                return {"error": "Not enough points", "status": 400}

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

            expiry_days = SHOP_ITEM_EXPIRY_DAYS.get(item_code)
            if expiry_days is not None:
                now_bj = datetime.now(BEIJING_TZ)
                expires_dt = (now_bj + timedelta(days=expiry_days)).replace(
                    hour=23, minute=59, second=59, microsecond=0
                )
                expires_at = expires_dt.strftime('%Y-%m-%d %H:%M:%S')
            else:
                expires_at = None
            c.execute("INSERT INTO shop_purchases (telegram_id, item_code, expires_at) VALUES (?,?,?)",
                      (telegram_id, item_code, expires_at))
            c.execute("""INSERT INTO shop_daily_counts (item_code, date, count) VALUES (?,?,1)
                         ON CONFLICT(item_code, date) DO UPDATE SET count=count+1""", (item_code, today))
            c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
            new_points = c.fetchone()[0]
            log_economy(c, telegram_id, 'shop_purchase', -price, new_points, None, 'shop_item', name)
            if has_active_implant(c, telegram_id, "implant_panda"):
                # Cap cashback so it can never make a buy+resell cycle profitable
                # (resale rate 60% + cashback must stay <= 100% of price).
                panda_cashback = min(10, int(price * 0.4))
                if panda_cashback > 0:
                    c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (panda_cashback, telegram_id))
                    c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
                    new_points = c.fetchone()[0] or 0
                    log_economy(c, telegram_id, 'implant_panda_cashback', panda_cashback, new_points, None, 'implant', name)
            zhongli_scan_bonus = grant_card_scan_once(
                c, telegram_id, "card_zhongli", "shop_resonance",
                "card_zhongli_shop_resonance", name, today,
            )
            conn.commit()
            return {
                "name": name,
                "new_points": new_points,
                "price_paid": price,
                "base_price": base_price,
                "guanxi_discount": base_price - price_after_guanxi,
                "zhongli_discount": price_after_guanxi - price,
                "zhongli_scan_bonus": zhongli_scan_bonus,
            }
        finally:
            conn.close()

    result = await db_write(_run)
    if "error" in result:
        raise HTTPException(status_code=result["status"], detail=result["error"])

    return {
        "success": True,
        "item": result["name"],
        "new_points": result["new_points"],
        "price_paid": result["price_paid"],
        "base_price": result["base_price"],
        "guanxi_discount": result["guanxi_discount"],
        "zhongli_discount": result["zhongli_discount"],
        "total_discount": result["base_price"] - result["price_paid"],
        "zhongli_scan_bonus": result["zhongli_scan_bonus"],
    }


@app.get("/api/shop/inventory/{telegram_id}")
def get_inventory(telegram_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT sp.id, sp.item_code, si.name, si.icon, si.price,
                        si.category, sp.purchased_at, sp.status, sp.given_to, si.description,
                        sp.expires_at
                 FROM shop_purchases sp
                 JOIN shop_items si ON sp.item_code = si.code
                 WHERE sp.telegram_id=? AND sp.status='active'
                   AND (sp.expires_at IS NULL OR sp.expires_at > datetime('now', '+8 hours'))
                 ORDER BY sp.purchased_at DESC""", (telegram_id,))
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "code": r[1], "name": r[2], "icon": r[3], "price": r[4],
             "category": r[5], "purchased_at": r[6], "status": r[7], "given_to": r[8],
             "description": r[9], "expires_at": r[10]} for r in rows]


@app.get("/api/users/search")
def search_users_for_gift(q: str = "", caller_id: Optional[int] = None):
    if not caller_id:
        raise HTTPException(status_code=400, detail="caller_id required")
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT 1 FROM users WHERE telegram_id=?", (caller_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(status_code=403, detail="Unknown caller")
    query = str(q or "").strip()
    if query:
        like = f"%{query}%"
        c.execute(
            '''SELECT telegram_id, full_name, avatar_url, points
               FROM users
               WHERE telegram_id IS NOT NULL AND telegram_id != ?
                 AND (full_name LIKE ? OR CAST(telegram_id AS TEXT) LIKE ?)
               ORDER BY full_name COLLATE NOCASE
               LIMIT 15''',
            (caller_id, like, like),
        )
    else:
        c.execute(
            '''SELECT telegram_id, full_name, avatar_url, points
               FROM users
               WHERE telegram_id IS NOT NULL AND telegram_id != ?
               ORDER BY full_name COLLATE NOCASE
               LIMIT 20''',
            (caller_id,),
        )
    rows = c.fetchall()
    conn.close()
    return {"users": [{"telegram_id": r[0], "full_name": r[1], "avatar_url": r[2], "points": r[3]} for r in rows]}


@app.post("/api/shop/gift")
async def gift_item(data: dict):
    def _run():
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
        fox_gift_trick = (
            has_active_card(c, from_id, "card_fox")
            and not has_used_card_today(c, from_id, "card_fox", "gift_tax_trick", today)
        )
        gift_tax = 15 if fox_gift_trick else 20
        if not user or (user[0] or 0) < gift_tax:
            conn.close()
            raise HTTPException(status_code=400, detail="Not enough points for tax")
        if fox_gift_trick:
            mark_card_used_today(c, from_id, "card_fox", "gift_tax_trick", today)
        c.execute("UPDATE users SET points = points - ? WHERE telegram_id=?", (gift_tax, from_id))
        now_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
        c.execute("UPDATE shop_purchases SET telegram_id=?, given_to=?, gifted_at=?, status='active' WHERE id=?", (to_id, from_id, now_str, purchase_id))
        c.execute("SELECT points FROM users WHERE telegram_id=?", (from_id,))
        new_points = c.fetchone()[0] or 0
        log_economy(c, from_id, 'gift_tax', -gift_tax, new_points, purchase_id, 'shop_gift', purchase[0])
        if gift_tax < 20:
            log_economy(c, from_id, 'card_fox_gift_trick', 0, new_points, purchase_id, 'card', purchase[0])
        log_economy(c, to_id, 'gift_receive', 0, None, purchase_id, 'shop_gift', f"Получен подарок: {purchase[0]} от {from_id}")
        conn.commit()
        conn.close()
        return {"success": True}
    return await db_write(_run)


@app.post("/api/shop/sell")
async def sell_item(data: dict):
    def _run():
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
    return await db_write(_run)


@app.post("/api/shop/use/{purchase_id}")
async def use_shop_item(purchase_id: int, data: dict):
    def _run():
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
    return await db_write(_run)

@app.post("/api/admin/freeze")
async def freeze_user(data: dict, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")
    telegram_id = data.get("telegram_id")
    frozen = data.get("frozen", True)
    def _run():
        conn = get_conn()
        c = conn.cursor()
        try:
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
        finally:
            conn.close()

    await db_write(_run)
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
    def _run():
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
    return await db_write(_run)


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


def get_wild_ai_breach_state(c) -> dict:
    """Returns the current Wild AI Breach state, auto-clearing it if expired."""
    c.execute("SELECT value FROM settings WHERE key='breach_until'")
    until_row = c.fetchone()
    until = parse_iso(until_row[0]) if until_row and until_row[0] else None

    if until and datetime.utcnow() >= until:
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('breach_until', '')")
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('breach_seed', '')")
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('blackwall', '0')")
        return {"breach_active": False, "breach_until": None, "breach_seed": None, "breach_phrase": None}

    if not until:
        return {"breach_active": False, "breach_until": None, "breach_seed": None, "breach_phrase": None}

    c.execute("SELECT value FROM settings WHERE key='breach_seed'")
    seed_row = c.fetchone()
    seed = int(seed_row[0]) if seed_row and seed_row[0] else 0

    hours_elapsed = int((datetime.utcnow() - (until - timedelta(days=WILD_AI_BREACH_DURATION_DAYS))).total_seconds() // 3600)
    phrase_index = (seed + hours_elapsed // WILD_AI_BREACH_PHRASE_ROTATE_HOURS) % len(WILD_AI_BREACH_PHRASES)

    return {
        "breach_active": True,
        "breach_until": until.isoformat(),
        "breach_seed": seed,
        "breach_phrase": WILD_AI_BREACH_PHRASES[phrase_index],
    }


@app.get("/api/settings")
def get_settings():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='blackwall'")
    blackwall = c.fetchone()
    c.execute("SELECT value FROM settings WHERE key='architect_event'")
    architect_event = c.fetchone()
    c.execute("SELECT value FROM settings WHERE key='wildai_event'")
    wildai_event = c.fetchone()
    breach = get_wild_ai_breach_state(c)
    conn.commit()
    conn.close()
    return {
        "blackwall": blackwall[0] == '1' if blackwall else False,
        "architect_event": architect_event[0] == '1' if architect_event else False,
        "wildai_event": wildai_event[0] == '1' if wildai_event else False,
        **breach,
    }


@app.get("/api/campus-map")
def get_campus_map():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='campus_map'")
    row = c.fetchone()
    conn.close()
    if not row or not row[0]:
        return {"overrides": {}, "custom": [], "updatedAt": 0}
    try:
        data = json.loads(row[0])
    except Exception:
        return {"overrides": {}, "custom": [], "updatedAt": 0}
    return {
        "overrides": data.get("overrides") if isinstance(data.get("overrides"), dict) else {},
        "custom": data.get("custom") if isinstance(data.get("custom"), list) else [],
        "updatedAt": int(data.get("updatedAt") or 0),
    }


@app.post("/api/admin/campus-map")
async def save_campus_map(data: dict, x_admin_id: Optional[int] = Header(None)):
    def _run():
        if x_admin_id not in ARCHITECT_IDS:
            raise HTTPException(status_code=403, detail="Forbidden")

        payload = {
            "overrides": data.get("overrides") if isinstance(data.get("overrides"), dict) else {},
            "custom": data.get("custom") if isinstance(data.get("custom"), list) else [],
            "updatedAt": int(data.get("updatedAt") or int(time.time() * 1000)),
        }
        encoded = json.dumps(payload, ensure_ascii=False)
        if len(encoded.encode("utf-8")) > 120_000:
            raise HTTPException(status_code=413, detail="Campus map payload too large")

        conn = get_conn()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('campus_map', ?)", (encoded,))
        c.execute(
            '''INSERT INTO admin_action_logs
               (admin_id, target_id, action_type, points_delta, reason, created_at)
               VALUES (?, NULL, 'campus_map', 0, ?, ?)''',
            (x_admin_id, 'Campus map updated', now_iso()),
        )
        conn.commit()
        conn.close()
        return {"success": True, "campus_map": payload}
    return await db_write(_run)


@app.post("/api/admin/blackwall")
async def toggle_blackwall(data: dict, x_admin_id: Optional[int] = Header(None)):
    def _run():
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
    return await db_write(_run)


@app.post("/api/admin/wildai-breach")
async def toggle_wildai_breach(data: dict, x_admin_id: Optional[int] = Header(None)):
    def _run():
        if x_admin_id not in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Forbidden")
        enabled = data.get("enabled", False)
        conn = get_conn()
        c = conn.cursor()
        if enabled:
            activate_wildai_breach(c, admin_id=x_admin_id, reason='Wild AI Breach enabled (manual)')
        else:
            c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('breach_until', '')")
            c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('breach_seed', '')")
            c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('blackwall', '0')")
            c.execute(
                '''INSERT INTO admin_action_logs
                   (admin_id, target_id, action_type, points_delta, reason, created_at)
                   VALUES (?, NULL, 'wildai_breach', 0, ?, ?)''',
                (x_admin_id, 'Wild AI Breach disabled', now_iso()),
            )
        conn.commit()
        conn.close()
        return {"success": True, "breach_active": enabled}
    return await db_write(_run)


@app.post("/api/admin/architect-event")
async def toggle_architect_event(data: dict, x_admin_id: Optional[int] = Header(None)):
    def _run():
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
    return await db_write(_run)


@app.post("/api/admin/wildai-event")
async def toggle_wildai_event(data: dict, x_admin_id: Optional[int] = Header(None)):
    def _run():
        if x_admin_id not in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Forbidden")
        enabled = bool(data.get("enabled", False))
        conn = get_conn()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('wildai_event', ?)", ('1' if enabled else '0',))
        c.execute(
            '''INSERT INTO admin_action_logs
               (admin_id, target_id, action_type, points_delta, reason, created_at)
               VALUES (?, NULL, 'wildai_event', 0, ?, ?)''',
            (x_admin_id, 'Wild AI event enabled' if enabled else 'Wild AI event disabled', now_iso()),
        )
        conn.commit()
        conn.close()
        return {"success": True, "wildai_event": enabled}
    return await db_write(_run)


@app.get("/api/raid/status")
def get_raid_status(telegram_id: int = 0):
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
    def _run():
        telegram_id = data.get("telegram_id")
        if not telegram_id:
            raise HTTPException(status_code=400, detail="No telegram_id")

        today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
        now_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
        conn = get_conn()
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

        # Verify answer if provided
        answer = str(data.get("answer") or "").strip().lower()
        question_id = data.get("question_id")
        answer_correct = 0
        if answer in ("a", "b", "c") and question_id:
            c.execute(
                "SELECT correct_option FROM event_questions WHERE id=? AND event_code='raid'",
                (int(question_id),),
            )
            q_row = c.fetchone()
            if q_row and q_row[0] == answer:
                answer_correct = 1
        c.execute(
            "UPDATE raid_participants SET answer_correct=? WHERE raid_id=? AND telegram_id=?",
            (answer_correct, raid_id, telegram_id),
        )

        c.execute("UPDATE users SET points = points - ? WHERE telegram_id=?", (RAID_ENTRY_COST, telegram_id))
        c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
        raid_entry_balance = c.fetchone()[0] or 0
        log_economy(c, telegram_id, 'raid_entry', -RAID_ENTRY_COST, raid_entry_balance, raid_id, 'raid', f"Raid {today}")
        c.execute("SELECT COUNT(*) FROM raid_participants WHERE raid_id=?", (raid_id,))
        count = c.fetchone()[0]

        launched = False
        result = None
        card_raid_bonus = 0
        if count >= RAID_MIN_PLAYERS or (telegram_id in ADMIN_IDS and count >= 1):
            launched = True
            c.execute("SELECT COALESCE(SUM(answer_correct),0) FROM raid_participants WHERE raid_id=?", (raid_id,))
            correct_count = c.fetchone()[0] or 0
            _chance_map = {0: 0.15, 1: 0.35, 2: 0.60, 3: 0.82}
            win_chance = _chance_map.get(int(correct_count), RAID_SUCCESS_CHANCE)
            result = 'success' if random.random() < win_chance else 'defended'
            c.execute("UPDATE raids SET status='finished', result=? WHERE id=?", (result, raid_id))
            c.execute("SELECT telegram_id FROM raid_participants WHERE raid_id=?", (raid_id,))
            all_participants = [r[0] for r in c.fetchall()]
            if result == 'success':
                for tid in all_participants:
                    c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (RAID_SUCCESS_REWARD, tid))
                    c.execute("SELECT points FROM users WHERE telegram_id=?", (tid,))
                    raid_reward_balance = c.fetchone()[0] or 0
                    log_economy(c, tid, 'raid_reward', RAID_SUCCESS_REWARD, raid_reward_balance, raid_id, 'raid', f"Raid {today}")
                    bonus = grant_card_points_once(
                        c, tid, "card_star", "raid_victory", 10,
                        "card_star_raid_victory", f"Raid {today}", today, raid_id, "raid",
                    )
                    if tid == telegram_id:
                        card_raid_bonus += bonus
            else:
                for tid in all_participants:
                    pyro_refund = grant_card_points_once(
                        c, tid, "card_pyro", "raid_ember", 10,
                        "card_pyro_raid_ember", f"Raid {today}", today, raid_id, "raid",
                    )
                    star_refund = grant_card_points_once(
                        c, tid, "card_star", "raid_judgement", 15,
                        "card_star_raid_judgement", f"Raid {today}", today, raid_id, "raid",
                    )
                    if tid == telegram_id:
                        card_raid_bonus += pyro_refund + star_refund

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
            "card_raid_bonus": card_raid_bonus,
            "answer_correct": answer_correct,
            "points_change": ((RAID_SUCCESS_REWARD - RAID_ENTRY_COST) if (launched and result == 'success') else -RAID_ENTRY_COST) + card_raid_bonus,
            "message": (
                f"🏆 РЕЙД УСПЕШЕН! +{RAID_SUCCESS_REWARD}★ каждому!" if (launched and result == 'success') else
                "🛡 АЛЬФАБОСС ЗАЩИТИЛСЯ! Ставки сгорели 🔥" if (launched and result == 'defended') else
                f"⚔️ Ты в отряде! Бойцов: {count}/{RAID_MIN_PLAYERS}"
            ),
        }
    return await db_write(_run)


@app.get("/api/raid/question")
def get_raid_question():
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        '''SELECT id, prompt, option_a, option_b, option_c
           FROM event_questions
           WHERE event_code='raid'
           ORDER BY RANDOM() LIMIT 1'''
    )
    row = c.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="No raid questions available")
    return {
        "id": row[0],
        "prompt": row[1],
        "option_a": row[2],
        "option_b": row[3],
        "option_c": row[4],
    }


CARD_INFO = {
    'card_zhongli':    {"name": "岩王帝君 Архонт Земли",        "rarity": 5, "passive": "-7% к магазину, -1★ комиссии контракта 1 раз в день, первая покупка дня даёт +1 скан · в ивентах: доп. -1 к перегрузке/заражению при Стабилизации/Синхронизации"},
    'card_pyro':       {"name": "焰莲使者 Страж Огня",          "rarity": 4, "passive": "первый штраф дня возвращает до 25★, первый провал рейда возвращает 10★ · в ивентах: +10% урона на Атаке"},
    'card_fox':        {"name": "九尾狐灵 Лиса-Оборотень",      "rarity": 4, "passive": "раз в день +30★ в молитве превращаются в +60★, первый подарок дня платит налог 15★ вместо 20★ · в ивентах: +1 поддержка при Синхронизации/Стабилизации"},
    'card_fairy':      {"name": "桃花仙子 Небесная Фея",         "rarity": 4, "passive": "+15★ за первую утреннюю или вечернюю отметку, ещё +15★ за полный день утро+вечер · в ивентах: +2 поддержка при Стабилизации"},
    'card_literature': {"name": "文曲星君 Звезда Литературы",   "rarity": 4, "passive": "+20★ за дневник на 3★, +15★ за бонусную строку дневника · в ивентах: +10% урона на Протоколе"},
    'card_forest':     {"name": "木灵仙君 Дух Леса",             "rarity": 4, "passive": "+10★ за утреннюю отметку, +8★ за первую ручную перекличку дня · в ивентах: -20% к росту перегрузки/заражения при ошибке"},
    'card_sea':        {"name": "海灵仙后 Дух Морей",            "rarity": 4, "passive": "каждая 3-я молитва дня даёт +25★, первый выполненный контракт дня даёт +5★ · в ивентах: +1 поддержка при Синхронизации"},
    'card_star':       {"name": "紫微星君 Императорская Звезда", "rarity": 5, "passive": "первый штраф дня уменьшается на 15★, дневник на 3★ даёт +10★, победа в рейде +10★, провал рейда возвращает 15★ · в ивентах: +1 урон при верном ответе на Атаке/Протоколе"},
    'card_moon':       {"name": "嫦娥仙子 Богиня Луны",          "rarity": 4, "passive": "+12★ каждые 24 часа · дубль этой карты сразу даёт +50★ · вечерняя отметка даёт +1 скан · в ивентах: +5% урона команде, если 2+ с этой картой"},
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
def get_cards(telegram_id: int):
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
    def _run():
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
                duplicate_bonus = 0
                if card_id == "card_moon":
                    duplicate_bonus = 50
                    c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (duplicate_bonus, telegram_id))
                    c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
                    balance_after = c.fetchone()[0] or 0
                    log_economy(c, telegram_id, "card_moon_duplicate_bonus", duplicate_bonus, balance_after, None, "card", info["name"])
                result = {"type": "card", "card_id": card_id, "name": info["name"], "rarity": info["rarity"], "passive": info["passive"], "pool": pool_name, "duplicate": True, "bonus": duplicate_bonus or None}
            else:
                c.execute("INSERT INTO user_cards (telegram_id, card_id, obtained_at, durability) VALUES (?,?,?,3)", (telegram_id, card_id, now_str))
                prize_code = f"genshin_{card_id}"
                result = {"type": "card", "card_id": card_id, "name": info["name"], "rarity": info["rarity"], "passive": info["passive"], "pool": pool_name, "duplicate": False, "bonus": None}
        elif item['type'] == 'points':
            amount = item['amount']
            fox_bonus = 0
            if (
                amount == 30
                and has_active_card(c, telegram_id, "card_fox")
                and not has_used_card_today(c, telegram_id, "card_fox", "trick")
            ):
                mark_card_used_today(c, telegram_id, "card_fox", "trick")
                fox_bonus = 30
                amount += fox_bonus
            doubled_win = False
            c.execute("SELECT double_win FROM user_status WHERE telegram_id=?", (telegram_id,))
            dw_row = c.fetchone()
            if dw_row and dw_row[0]:
                amount *= 2
                doubled_win = True
                c.execute("UPDATE user_status SET double_win=0 WHERE telegram_id=?", (telegram_id,))
            c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (amount, telegram_id))
            prize_code = f"genshin_points_{amount}"
            if fox_bonus:
                c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
                balance_after = c.fetchone()[0] or 0
                log_economy(c, telegram_id, "card_fox_trick", fox_bonus, balance_after, None, "card", "genshin_points_30_to_60")
            if doubled_win:
                c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
                balance_after = c.fetchone()[0] or 0
                log_economy(c, telegram_id, "double_win_consumed", 0, balance_after, None, "shop_item", "Двойной выигрыш")
            result = {"type": "points", "amount": amount, "pool": pool_name, "name": f"+{amount} ★" + (" ×2" if doubled_win else ""), "rarity": 0, "card_bonus": fox_bonus, "doubled_win": doubled_win}
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
        sea_bonus = 0
        if has_active_card(c, telegram_id, "card_sea"):
            c.execute(
                """SELECT COUNT(*) FROM casino_log
                   WHERE telegram_id=? AND date=? AND prize LIKE 'genshin_%'""",
                (telegram_id, today),
            )
            prayers_today = c.fetchone()[0] or 0
            if prayers_today > 0 and prayers_today % 3 == 0 and not has_used_card_today(c, telegram_id, "card_sea", f"tide:{prayers_today}", today):
                sea_bonus = 25
                mark_card_used_today(c, telegram_id, "card_sea", f"tide:{prayers_today}", today)
                c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (sea_bonus, telegram_id))
                c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
                balance_after = c.fetchone()[0] or 0
                log_economy(c, telegram_id, "card_sea_tide", sea_bonus, balance_after, None, "card", f"prayer #{prayers_today}")
        c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
        new_points = c.fetchone()[0]
        c.execute("SELECT scan_attempts, protocol_fragments FROM user_status WHERE telegram_id=?", (telegram_id,))
        sc_row = c.fetchone()
        log_economy(c, telegram_id, 'prayer_open', new_points - points, new_points, None, pool_name, result.get("name") or prize_code)
        conn.commit()
        conn.close()
        result["new_points"] = new_points
        if sea_bonus:
            result["sea_bonus"] = sea_bonus
        result["scan_attempts"] = sc_row[0] if sc_row else 0
        result["protocol_fragments"] = sc_row[1] if sc_row else 0
        return result
    return await db_write(_run)


@app.post("/api/admin/fragments")
async def admin_grant_fragments(data: dict, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ARCHITECT_IDS:
        raise HTTPException(status_code=403, detail="Forbidden: Architect only")
    telegram_id = data.get("telegram_id")
    amount = int(data.get("amount") or 0)
    if not telegram_id or amount < 1:
        raise HTTPException(status_code=400, detail="Missing data")

    def _run():
        conn = get_conn()
        try:
            c = conn.cursor()
            c.execute("SELECT 1 FROM users WHERE telegram_id=?", (telegram_id,))
            if not c.fetchone():
                return None
            c.execute("""INSERT INTO user_status (telegram_id, protocol_fragments) VALUES (?,?)
                         ON CONFLICT(telegram_id) DO UPDATE SET protocol_fragments=COALESCE(protocol_fragments,0)+?""",
                      (telegram_id, amount, amount))
            c.execute("SELECT protocol_fragments FROM user_status WHERE telegram_id=?", (telegram_id,))
            new_val = c.fetchone()[0]
            conn.commit()
            return new_val
        finally:
            conn.close()

    new_val = await db_write(_run)
    if new_val is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {"success": True, "telegram_id": telegram_id, "amount": amount, "protocol_fragments": new_val}


@app.post("/api/admin/scan-attempt")
async def admin_grant_scan_attempt(data: dict, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ARCHITECT_IDS:
        raise HTTPException(status_code=403, detail="Forbidden: Architect only")
    telegram_id = data.get("telegram_id")
    if not telegram_id:
        raise HTTPException(status_code=400, detail="Missing telegram_id")

    def _run():
        conn = get_conn()
        try:
            c = conn.cursor()
            c.execute("SELECT 1 FROM users WHERE telegram_id=?", (telegram_id,))
            if not c.fetchone():
                return None
            c.execute("""INSERT INTO user_status (telegram_id, scan_attempts) VALUES (?,1)
                         ON CONFLICT(telegram_id) DO UPDATE SET scan_attempts=MIN(7, scan_attempts+1)""",
                      (telegram_id,))
            c.execute("SELECT scan_attempts FROM user_status WHERE telegram_id=?", (telegram_id,))
            new_val = c.fetchone()[0]
            conn.commit()
            return new_val
        finally:
            conn.close()

    new_val = await db_write(_run)
    if new_val is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {"success": True, "telegram_id": telegram_id, "scan_attempts": new_val}


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
    def _run():
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
    return await db_write(_run)


@app.post("/api/cards/disassemble/{card_id}")
async def disassemble_card(card_id: int, data: dict):
    def _run():
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
    return await db_write(_run)


@app.get("/api/laundry/schedule")
def get_laundry_schedule():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, day, time, note, COALESCE(capacity, 1) FROM laundry_schedule ORDER BY id")
    rows = c.fetchall()
    result = []
    for row in rows:
        c.execute(
            '''SELECT lb.telegram_id, COALESCE(u.full_name, lb.telegram_id), lb.booked_at
               FROM laundry_bookings lb
               LEFT JOIN users u ON u.telegram_id=lb.telegram_id
               WHERE lb.slot_id=?
               ORDER BY lb.booked_at, lb.id''',
            (row[0],),
        )
        bookings = [
            {"telegram_id": b[0], "name": b[1], "booked_at": b[2]}
            for b in c.fetchall()
        ]
        result.append({
            "id": row[0],
            "day": row[1],
            "time": row[2],
            "note": row[3],
            "capacity": max(int(row[4] or 1), 1),
            "booked": len(bookings),
            "bookings": bookings,
            "taken_by": bookings[0] if bookings else None,
        })
    conn.close()
    return result


@app.post("/api/laundry/schedule")
async def add_laundry_slot(data: dict, x_admin_id: int = Header(None)):
    def _run():
        if x_admin_id not in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Not admin")
        conn = get_conn()
        c = conn.cursor()
        capacity = max(int(data.get("capacity") or 1), 1)
        c.execute(
            "INSERT INTO laundry_schedule (day, time, note, capacity) VALUES (?,?,?,?)",
            (data.get("day"), data.get("time"), data.get("note", ""), capacity),
        )
        conn.commit()
        conn.close()
        return {"success": True}
    return await db_write(_run)


@app.delete("/api/laundry/schedule/{slot_id}")
async def delete_laundry_slot(slot_id: int, x_admin_id: int = Header(None)):
    def _run():
        if x_admin_id not in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Not admin")
        conn = get_conn()
        c = conn.cursor()
        c.execute("DELETE FROM laundry_bookings WHERE slot_id=?", (slot_id,))
        c.execute("DELETE FROM laundry_schedule WHERE id=?", (slot_id,))
        conn.commit()
        conn.close()
        return {"success": True}
    return await db_write(_run)


@app.post("/api/laundry/schedule/{slot_id}/book")
async def book_laundry_slot(slot_id: int, data: dict):
    def _run():
        telegram_id = int(data.get("telegram_id") or 0)
        if not telegram_id:
            raise HTTPException(status_code=400, detail="Missing telegram_id")
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT COALESCE(capacity, 1) FROM laundry_schedule WHERE id=?", (slot_id,))
        slot = c.fetchone()
        if not slot:
            conn.close()
            raise HTTPException(status_code=404, detail="Not found")
        capacity = max(int(slot[0] or 1), 1)
        c.execute("SELECT COUNT(*) FROM laundry_bookings WHERE slot_id=?", (slot_id,))
        if c.fetchone()[0] >= capacity:
            conn.close()
            raise HTTPException(status_code=400, detail="Slot full")
        c.execute("DELETE FROM laundry_bookings WHERE telegram_id=?", (telegram_id,))
        c.execute(
            "INSERT OR IGNORE INTO laundry_bookings (slot_id, telegram_id) VALUES (?,?)",
            (slot_id, telegram_id),
        )
        c.execute("UPDATE laundry_schedule SET taken_by=NULL")
        conn.commit()
        conn.close()
        return {"success": True}
    return await db_write(_run)


@app.post("/api/laundry/schedule/{slot_id}/cancel")
async def cancel_laundry_slot(slot_id: int, data: dict):
    def _run():
        telegram_id = int(data.get("telegram_id") or 0)
        if not telegram_id:
            raise HTTPException(status_code=400, detail="Missing telegram_id")
        conn = get_conn()
        c = conn.cursor()
        c.execute("DELETE FROM laundry_bookings WHERE slot_id=? AND telegram_id=?", (slot_id, telegram_id))
        c.execute("UPDATE laundry_schedule SET taken_by=NULL WHERE id=? AND taken_by=?", (slot_id, telegram_id))
        conn.commit()
        conn.close()
        return {"success": True}
    return await db_write(_run)


@app.post("/api/laundry/schedule/{slot_id}/admin-cancel")
async def admin_cancel_laundry_booking(slot_id: int, data: dict, x_admin_id: int = Header(None)):
    def _run():
        if x_admin_id not in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Not admin")
        telegram_id = int(data.get("telegram_id") or 0)
        if not telegram_id:
            raise HTTPException(status_code=400, detail="Missing telegram_id")
        conn = get_conn()
        c = conn.cursor()
        c.execute("DELETE FROM laundry_bookings WHERE slot_id=? AND telegram_id=?", (slot_id, telegram_id))
        c.execute("UPDATE laundry_schedule SET taken_by=NULL WHERE id=? AND taken_by=?", (slot_id, telegram_id))
        conn.commit()
        conn.close()
        return {"success": True}
    return await db_write(_run)


@app.get("/api/water/schedule")
def get_water_schedule():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, day, time, COALESCE(floor, ''), note, COALESCE(capacity, 1) FROM water_schedule ORDER BY id")
    rows = c.fetchall()
    result = []
    for row in rows:
        c.execute(
            '''SELECT wb.telegram_id, COALESCE(u.full_name, wb.telegram_id), wb.booked_at
               FROM water_bookings wb
               LEFT JOIN users u ON u.telegram_id=wb.telegram_id
               WHERE wb.slot_id=?
               ORDER BY wb.booked_at, wb.id''',
            (row[0],),
        )
        bookings = [
            {"telegram_id": b[0], "name": b[1], "booked_at": b[2]}
            for b in c.fetchall()
        ]
        result.append({
            "id": row[0],
            "day": row[1],
            "time": row[2],
            "floor": row[3],
            "note": row[4],
            "capacity": max(int(row[5] or 1), 1),
            "booked": len(bookings),
            "bookings": bookings,
        })
    conn.close()
    return result


@app.post("/api/water/schedule")
async def add_water_slot(data: dict, x_admin_id: int = Header(None)):
    def _run():
        if x_admin_id not in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Not admin")
        conn = get_conn()
        c = conn.cursor()
        capacity = max(int(data.get("capacity") or 1), 1)
        c.execute(
            "INSERT INTO water_schedule (day, time, floor, note, capacity) VALUES (?,?,?,?,?)",
            (
                data.get("day"),
                data.get("time"),
                data.get("floor", ""),
                data.get("note", ""),
                capacity,
            ),
        )
        conn.commit()
        conn.close()
        return {"success": True}
    return await db_write(_run)


@app.delete("/api/water/schedule/{slot_id}")
async def delete_water_slot(slot_id: int, x_admin_id: int = Header(None)):
    def _run():
        if x_admin_id not in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Not admin")
        conn = get_conn()
        c = conn.cursor()
        c.execute("DELETE FROM water_bookings WHERE slot_id=?", (slot_id,))
        c.execute("DELETE FROM water_schedule WHERE id=?", (slot_id,))
        conn.commit()
        conn.close()
        return {"success": True}
    return await db_write(_run)


@app.post("/api/water/schedule/{slot_id}/book")
async def book_water_slot(slot_id: int, data: dict):
    def _run():
        telegram_id = int(data.get("telegram_id") or 0)
        if not telegram_id:
            raise HTTPException(status_code=400, detail="Missing telegram_id")
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT COALESCE(capacity, 1) FROM water_schedule WHERE id=?", (slot_id,))
        slot = c.fetchone()
        if not slot:
            conn.close()
            raise HTTPException(status_code=404, detail="Not found")
        capacity = max(int(slot[0] or 1), 1)
        c.execute("SELECT COUNT(*) FROM water_bookings WHERE slot_id=?", (slot_id,))
        if c.fetchone()[0] >= capacity:
            conn.close()
            raise HTTPException(status_code=400, detail="Slot full")
        c.execute("DELETE FROM water_bookings WHERE telegram_id=?", (telegram_id,))
        c.execute(
            "INSERT OR IGNORE INTO water_bookings (slot_id, telegram_id) VALUES (?,?)",
            (slot_id, telegram_id),
        )
        conn.commit()
        conn.close()
        return {"success": True}
    return await db_write(_run)


@app.post("/api/water/schedule/{slot_id}/cancel")
async def cancel_water_slot(slot_id: int, data: dict):
    def _run():
        telegram_id = int(data.get("telegram_id") or 0)
        if not telegram_id:
            raise HTTPException(status_code=400, detail="Missing telegram_id")
        conn = get_conn()
        c = conn.cursor()
        c.execute("DELETE FROM water_bookings WHERE slot_id=? AND telegram_id=?", (slot_id, telegram_id))
        conn.commit()
        conn.close()
        return {"success": True}
    return await db_write(_run)


@app.post("/api/water/schedule/{slot_id}/admin-cancel")
async def admin_cancel_water_booking(slot_id: int, data: dict, x_admin_id: int = Header(None)):
    def _run():
        if x_admin_id not in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Not admin")
        telegram_id = int(data.get("telegram_id") or 0)
        if not telegram_id:
            raise HTTPException(status_code=400, detail="Missing telegram_id")
        conn = get_conn()
        c = conn.cursor()
        c.execute("DELETE FROM water_bookings WHERE slot_id=? AND telegram_id=?", (slot_id, telegram_id))
        conn.commit()
        conn.close()
        return {"success": True}
    return await db_write(_run)


@app.post("/api/events/architect/create")
async def create_architect_event(data: dict, x_admin_id: int = Header(None)):
    def _run():
        admin_id = x_admin_id if x_admin_id is not None else data.get("telegram_id")
        if admin_id not in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Forbidden")

        blocking_event_id = get_blocking_event_id('architect')
        if blocking_event_id:
            raise HTTPException(status_code=409, detail="Another Architect Protocol event is already active")

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
    return await db_write(_run)


@app.post("/api/events/wildai/create")
async def create_wildai_event(data: dict, x_admin_id: int = Header(None)):
    def _run():
        admin_id = x_admin_id if x_admin_id is not None else data.get("telegram_id")
        if admin_id not in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Forbidden")

        blocking_event_id = get_blocking_event_id('wildai_breach')
        if blocking_event_id:
            raise HTTPException(status_code=409, detail="A WILD AI BREACH event is already active")

        conn = get_conn()
        c = conn.cursor()

        title = data.get("title") or "WILD AI BREACH"
        boss_name = data.get("boss_name") or "Дикий ИИ"
        boss_image = data.get("boss_image")
        reward_text = data.get("reward_text") or f"+{WILD_AI_BREACH_REWARD_REP} REP, +{WILD_AI_BREACH_REWARD_FRAGMENTS} фрагмента протокола, рамка «{WILD_AI_BREACH_FRAME_ID}»"
        min_players = int(data.get("min_players") or 3)
        max_players = int(data.get("max_players") or 5)
        max_hp = int(data.get("max_hp") or WILD_AI_BREACH_DEFAULT_HP)
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
            ('wildai_breach', title, boss_name, boss_image, reward_text, min_players, max_players, max_hp, max_hp, created_at),
        )
        event_id = c.lastrowid
        add_event_log(c, event_id, "system", "WILD AI BREACH: обнаружено вторжение. Набор команды для зачистки открыт.")
        add_event_log(c, event_id, "boss", f"Набор команды открыт. Награда: {reward_text}")
        conn.commit()
        conn.close()
        return get_event_snapshot(event_id)
    return await db_write(_run)


@app.get("/api/events/current")
async def get_current_event(code: Optional[str] = None):
    event_id = get_current_or_latest_event_id(code)
    return {"event": get_event_snapshot(event_id) if event_id else None}


@app.get("/api/events/{event_id}")
async def get_event_details(event_id: int):
    snapshot = get_event_snapshot(event_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Event not found")
    return snapshot


@app.post("/api/events/{event_id}/join")
async def join_event_team(event_id: int, data: dict):
    def _run():
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
    return await db_write(_run)


@app.post("/api/events/{event_id}/leave")
async def leave_event_team(event_id: int, data: dict):
    def _run():
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
    return await db_write(_run)


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
    def _run():
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
    return await db_write(_run)


@app.post("/api/events/{event_id}/start")
async def start_event(event_id: int, data: dict = None, x_admin_id: int = Header(None)):
    def _run():
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
            "UPDATE events SET state='ACTIVE', phase=1, phase_started_at=?, started_at=?, pressure_tick_at=? WHERE id=?",
            (started_at, started_at, started_at, event_id),
        )
        if event_row["code"] == "wildai_breach":
            add_event_log(c, event_id, "system", "WILD AI BREACH: операция по вытеснению начата.")
            add_event_log(c, event_id, "boss", "обнаружено вторжение дикого ИИ в системные сектора.")
        else:
            add_event_log(c, event_id, "system", "Architect event started.")
            add_event_log(c, event_id, "boss", "观察开始。 / Фаза наблюдения активирована.")
        conn.commit()
        conn.close()
        return get_event_snapshot(event_id)
    return await db_write(_run)


@app.post("/api/events/{event_id}/reset")
async def reset_event(event_id: int, x_admin_id: int = Header(None)):
    def _run():
        if x_admin_id not in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Forbidden")

        conn = get_conn()
        c = conn.cursor()
        event_row = fetch_event_row(c, event_id)
        if not event_row:
            conn.close()
            raise HTTPException(status_code=404, detail="Event not found")

        max_hp = event_row["max_hp"] or ARCHITECT_DEFAULT_HP
        c.execute(
            """UPDATE events
               SET state='REGISTRATION', phase=1, current_hp=?,
                   phase_started_at=NULL, started_at=NULL, ended_at=NULL,
                   final_phase_deadline=NULL, vulnerability_until=NULL,
                   overload_pressure=0, mvp_user_id=NULL
               WHERE id=?""",
            (max_hp, event_id),
        )
        # Clear logs and action history for a clean test run
        c.execute("DELETE FROM event_logs WHERE event_id=?", (event_id,))
        c.execute("DELETE FROM event_actions WHERE event_id=?", (event_id,))
        add_event_log(c, event_id, "system", "Ивент сброшен администратором. Регистрация открыта.")
        conn.commit()
        conn.close()
        return get_event_snapshot(event_id)
    return await db_write(_run)


@app.get("/api/events/{event_id}/question")
async def get_event_question(event_id: int, telegram_id: int, action_type: str):
    def _run():
        snapshot = get_event_snapshot(event_id)
        event_code = snapshot["code"] if snapshot else "architect"
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

        question = choose_architect_question(c, action_type, event_code=event_code)
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
    return await db_write(_run)


@app.post("/api/events/action")
async def resolve_event_action(data: dict):
    def _run():
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
                   WHERE id=? AND event_code=? AND action_type=?''',
                (question_id, event_row["code"], action_type),
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
            telegram_id=int(telegram_id),
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

        is_wildai = event_row["code"] == "wildai_breach"
        actor_name = get_user_display_name(c, int(telegram_id))
        if action_type in ("attack", "protocol"):
            event_row["current_hp"] = max(0, event_row["current_hp"] - result["final_value"])
            c.execute("UPDATE events SET current_hp=? WHERE id=?", (event_row["current_hp"], int(event_id)))
            c.execute(
                "UPDATE event_participants SET total_damage = total_damage + ? WHERE id=?",
                (result["final_value"], participant["id"]),
            )
            action_name = "Protocol" if action_type == "protocol" else "атака"
            if is_wildai:
                if is_correct:
                    add_event_log(c, int(event_id), "action", f"{actor_name} применил(а) {action_name} и восстановил(а) {result['final_value']} целостности системы")
                else:
                    partial = result['final_value']
                    if partial > 0:
                        add_event_log(c, int(event_id), "action", f"{actor_name} сбойнул(а) в {action_name} — частично восстановлено {partial}, заражение растёт")
                    else:
                        add_event_log(c, int(event_id), "action", f"{actor_name} ошибся(лась) в {action_name} — узел дикого ИИ не задет, заражение растёт")
            elif is_correct:
                if result.get("penalty_active"):
                    pct = result.get("overload_pct_str", "50%")
                    add_event_log(c, int(event_id), "system", f"⚠ ПЕРЕГРУЗКА: {actor_name} нанёс(ла) {result['final_value']} урона (−{pct} из-за перегрузки)")
                else:
                    add_event_log(c, int(event_id), "action", f"{actor_name} активировал(а) {action_name} и нанёс(ла) {result['final_value']} урона")
            else:
                partial = result['final_value']
                if partial > 0:
                    add_event_log(c, int(event_id), "action", f"{actor_name} сбойнул(а) в {action_name} — частичный удар {partial} урона")
                else:
                    add_event_log(c, int(event_id), "action", f"{actor_name} ошибся(лась) в {action_name} — протокол не пробит")
        elif action_type == "stabilize":
            c.execute(
                "UPDATE event_participants SET total_support = total_support + ? WHERE id=?",
                (result["support_value"], participant["id"]),
            )
            if is_wildai:
                if is_correct:
                    add_event_log(c, int(event_id), "action", f"{actor_name} залатал(а) пробитый сектор — заражение снижено")
                else:
                    add_event_log(c, int(event_id), "action", f"{actor_name} попытался(ась) залатать сектор, но ошибся(лась) — заражение растёт")
            elif is_correct:
                add_event_log(c, int(event_id), "action", f"{actor_name} стабилизировал(а) протокол (+{result['support_value']} support)")
            else:
                add_event_log(c, int(event_id), "action", f"{actor_name} попытался(ась) стабилизировать протокол, но допустил(а) ошибку")
        else:
            c.execute(
                "UPDATE event_participants SET total_support = total_support + ? WHERE id=?",
                (result["support_value"], participant["id"]),
            )
            if is_wildai:
                add_event_log(c, int(event_id), "action", f"{actor_name} просканировал(а) сектора — узел дикого ИИ локализован")
            else:
                add_event_log(c, int(event_id), "action", f"{actor_name} синхронизировал(а) канал")
            maybe_trigger_sync_window(c, event_row)

        if is_wildai:
            if result["pressure_delta"] != 0:
                old_pressure = event_row["overload_pressure"]
                event_row["overload_pressure"] = max(0, old_pressure + result["pressure_delta"])
                c.execute("UPDATE events SET overload_pressure=? WHERE id=?", (event_row["overload_pressure"], int(event_id)))
                if result["pressure_delta"] > 0:
                    add_event_log(c, int(event_id), "system", f"⚠ ЗАРАЖЕНИЕ РАСТЁТ: {event_row['overload_pressure']}/{WILD_AI_BREACH_INFECTION_THRESHOLD}")
        elif action_type in ("attack", "protocol", "stabilize") and result["pressure_delta"] != 0:
            ovl_threshold = result["overload_threshold"]
            pct_str = result.get("overload_pct_str", "50%")
            old_pressure = event_row["overload_pressure"]
            event_row["overload_pressure"] = max(0, old_pressure + result["pressure_delta"])
            c.execute("UPDATE events SET overload_pressure=? WHERE id=?", (event_row["overload_pressure"], int(event_id)))
            if old_pressure < ovl_threshold <= event_row["overload_pressure"]:
                add_event_log(c, int(event_id), "system", f"⚠ ПЕРЕГРУЗКА АКТИВНА — урон от атак снижен на {pct_str}")
            elif old_pressure >= ovl_threshold > event_row["overload_pressure"]:
                add_event_log(c, int(event_id), "system", "✓ Перегрузка снята — атаки снова в полную силу")

        # Boss counter-attack: every N total actions adds pressure
        if not is_wildai:
            c.execute("SELECT COUNT(*) FROM event_actions WHERE event_id=?", (int(event_id),))
            total_actions_count = c.fetchone()[0]
            if total_actions_count > 0 and total_actions_count % ARCHITECT_BOSS_COUNTER_EVERY == 0:
                new_pressure = event_row["overload_pressure"] + ARCHITECT_BOSS_COUNTER_PRESSURE
                c.execute("UPDATE events SET overload_pressure=? WHERE id=?", (new_pressure, int(event_id)))
                event_row["overload_pressure"] = new_pressure
                add_event_log(c, int(event_id), "boss", f"АРХИТЕКТОР УСИЛИВАЕТ ДАВЛЕНИЕ (+{ARCHITECT_BOSS_COUNTER_PRESSURE} перегрузки)")

        if result["active_note"]:
            add_event_log(c, int(event_id), "modifier", result["active_note"])

        event_row = fetch_event_row(c, int(event_id))
        event_row = refresh_event_state(c, event_row)
        conn.commit()
        conn.close()

        snapshot = get_event_snapshot(int(event_id))
        return {
            "event_id": int(event_id),
            "code": event_row["code"],
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
    return await db_write(_run)


@app.get("/api/events/{event_id}/leaderboard")
def get_event_leaderboard(event_id: int):
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

def _safe_contract_avatar_url(avatar_url):
    if not avatar_url:
        return None
    avatar_url = str(avatar_url)
    if avatar_url.startswith("data:image/"):
        return None
    return avatar_url


def _contract_to_dict(row, creator_name=None, assignee_name=None,
                      creator_avatar_url=None, assignee_avatar_url=None,
                      viewer_id=None, is_anonymous=False, public_view=False):
    reward = row[4]
    fee = row[5]
    hide_creator = bool(public_view and is_anonymous and viewer_id != row[6])
    public_creator_name = "Анонимный заказчик" if hide_creator else (creator_name or "Аноним")
    public_creator_avatar = None if hide_creator else _safe_contract_avatar_url(creator_avatar_url)
    return {
        "id": row[0],
        "title": row[1],
        "description": row[2],
        "category": row[3],
        "reward_stars": reward,
        "fee_stars": fee,
        "payout_stars": reward - fee,
        "creator_telegram_id": None if hide_creator else row[6],
        "assignee_telegram_id": row[7],
        "creator_is_admin": False if hide_creator else row[6] in ADMIN_IDS,
        "creator_name": public_creator_name,
        "assignee_name": assignee_name,
        "creator_avatar_url": public_creator_avatar,
        "assignee_avatar_url": _safe_contract_avatar_url(assignee_avatar_url),
        "is_anonymous": bool(is_anonymous),
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
def list_open_contracts(x_telegram_id: Optional[int] = Header(None)):
    conn = get_conn()
    c = conn.cursor()
    _check_blackwall(c, x_telegram_id)
    c.execute(
        '''SELECT id, title, description, category, reward_stars, fee_stars,
                  creator_telegram_id, assignee_telegram_id, status,
                  is_suspicious, suspicious_reason,
                  created_at, accepted_at, completed_at, cancelled_at, disputed_at,
                  is_anonymous
           FROM contracts
           WHERE status='open'
           ORDER BY created_at DESC
           LIMIT 50''',
    )
    rows = c.fetchall()
    result = []
    for row in rows:
        cn, an, ca, aa = _resolve_names(c, row[6], row[7])
        result.append(_contract_to_dict(row[:16], cn, an, ca, aa, x_telegram_id, bool(row[16]), True))
    conn.close()
    return result


@app.get("/api/contracts/my")
def my_contracts(x_telegram_id: Optional[int] = Header(None)):
    if not x_telegram_id:
        raise HTTPException(status_code=401, detail="Not authorized")
    conn = get_conn()
    c = conn.cursor()
    _check_blackwall(c, x_telegram_id)
    c.execute(
        '''SELECT id, title, description, category, reward_stars, fee_stars,
                  creator_telegram_id, assignee_telegram_id, status,
                  is_suspicious, suspicious_reason,
                  created_at, accepted_at, completed_at, cancelled_at, disputed_at,
                  is_anonymous
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
        result.append(_contract_to_dict(row[:16], cn, an, ca, aa, x_telegram_id, bool(row[16]), False))
    conn.close()
    return result


@app.post("/api/contracts")
async def create_contract(data: dict, x_telegram_id: Optional[int] = Header(None)):
    if not x_telegram_id:
        raise HTTPException(status_code=401, detail="Not authorized")

    title = str(data.get("title") or "").strip()
    description = str(data.get("description") or "").strip()
    category = str(data.get("category") or "other").strip()
    is_anonymous = bool(data.get("is_anonymous"))
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

    def _run():
        conn = get_conn()
        try:
            c = conn.cursor()
            _check_blackwall(c, x_telegram_id)
            today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
            local_fee = fee
            zhongli_fee_reduction = 0
            if (
                has_active_card(c, x_telegram_id, "card_zhongli")
                and not has_used_card_today(c, x_telegram_id, "card_zhongli", "contract_seal", today)
            ):
                zhongli_fee_reduction = 1
                local_fee = max(1, local_fee - zhongli_fee_reduction)
                mark_card_used_today(c, x_telegram_id, "card_zhongli", "contract_seal", today)

            c.execute("SELECT points FROM users WHERE telegram_id=?", (x_telegram_id,))
            user = c.fetchone()
            if not user:
                return {"error": "User not found", "status": 404}
            if (user[0] or 0) < reward:
                return {"error": "Недостаточно ★ для создания контракта", "status": 400}

            c.execute(
                "SELECT COUNT(*) FROM contracts WHERE creator_telegram_id=? AND status IN ('open','accepted')",
                (x_telegram_id,),
            )
            if (c.fetchone()[0] or 0) >= CONTRACT_MAX_ACTIVE:
                return {"error": f"Максимум {CONTRACT_MAX_ACTIVE} активных контракта одновременно", "status": 400}

            c.execute(
                "SELECT COALESCE(SUM(reward_stars),0) FROM contracts WHERE creator_telegram_id=? AND date(created_at)=?",
                (x_telegram_id, today),
            )
            if ((c.fetchone()[0] or 0) + reward) > CONTRACT_MAX_DAILY_SPEND:
                return {"error": f"Дневной лимит расходов через контракты: {CONTRACT_MAX_DAILY_SPEND} ★", "status": 400}

            is_susp, susp_reason = detect_suspicious(c, x_telegram_id, reward, title, description, category)
            now_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')

            c.execute("UPDATE users SET points = points - ? WHERE telegram_id=?", (reward, x_telegram_id))
            c.execute("SELECT points FROM users WHERE telegram_id=?", (x_telegram_id,))
            balance_after = c.fetchone()[0] or 0

            c.execute(
                '''INSERT INTO contracts
                   (title, description, category, reward_stars, fee_stars,
                    creator_telegram_id, status, is_suspicious, suspicious_reason, is_anonymous, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?)''',
                (title, description, category, reward, local_fee, x_telegram_id, int(is_susp), susp_reason, int(is_anonymous), now_str),
            )
            contract_id = c.lastrowid
            log_economy(c, x_telegram_id, 'contract_freeze', -reward, balance_after,
                        contract_id, 'contract', f"Заморозка: контракт #{contract_id}")
            if zhongli_fee_reduction:
                log_economy(c, x_telegram_id, 'card_zhongli_contract_seal', 0, balance_after,
                            contract_id, 'card', f"Комиссия снижена на {zhongli_fee_reduction}★")
            conn.commit()
            return {"contract_id": contract_id, "fee_stars": local_fee, "new_points": balance_after}
        finally:
            conn.close()

    result = await db_write(_run)
    if "error" in result:
        raise HTTPException(status_code=result["status"], detail=result["error"])

    return {"success": True, "id": result["contract_id"], "fee_stars": result["fee_stars"],
            "payout_stars": reward - result["fee_stars"], "new_points": result["new_points"]}


@app.post("/api/contracts/{contract_id}/accept")
async def accept_contract(contract_id: int, x_telegram_id: Optional[int] = Header(None)):
    if not x_telegram_id:
        raise HTTPException(status_code=401, detail="Not authorized")

    def _run():
        conn = get_conn()
        try:
            c = conn.cursor()
            _check_blackwall(c, x_telegram_id)
            row = get_contract_row(c, contract_id)
            if not row:
                return {"error": "Контракт не найден", "status": 404}
            creator_id, reward, status = row[6], row[4], row[8]
            if status != 'open':
                return {"error": "Контракт недоступен для принятия", "status": 400}
            if creator_id == x_telegram_id:
                return {"error": "Нельзя принять собственный контракт", "status": 400}

            today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
            c.execute(
                "SELECT COUNT(*) FROM contracts WHERE assignee_telegram_id=? AND status='completed' AND date(completed_at)=?",
                (x_telegram_id, today),
            )
            if (c.fetchone()[0] or 0) >= CONTRACT_MAX_COMPLETED_PER_DAY:
                return {"error": f"Дневной лимит выполненных контрактов: {CONTRACT_MAX_COMPLETED_PER_DAY}", "status": 400}

            c.execute(
                "SELECT COALESCE(SUM(reward_stars-fee_stars),0) FROM contracts WHERE assignee_telegram_id=? AND status='completed' AND date(completed_at)=?",
                (x_telegram_id, today),
            )
            today_earn = c.fetchone()[0] or 0
            payout = reward - compute_contract_fee(reward)
            if today_earn + payout > CONTRACT_MAX_DAILY_EARN:
                return {"error": f"Дневной лимит заработка: {CONTRACT_MAX_DAILY_EARN} ★", "status": 400}

            now_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
            c.execute(
                "UPDATE contracts SET status='accepted', assignee_telegram_id=?, accepted_at=? WHERE id=?",
                (x_telegram_id, now_str, contract_id),
            )
            log_economy(c, x_telegram_id, 'contract_accept', 0, None, contract_id, 'contract',
                        f"Принят контракт #{contract_id}")
            conn.commit()
            return {}
        finally:
            conn.close()

    result = await db_write(_run)
    if "error" in result:
        raise HTTPException(status_code=result["status"], detail=result["error"])

    return {"success": True}


@app.post("/api/contracts/{contract_id}/complete")
async def complete_contract(contract_id: int,
                             x_telegram_id: Optional[int] = Header(None),
                             x_admin_id: Optional[int] = Header(None)):
    def _run():
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
        log_economy(c, assignee_id, 'contract_payout', payout, assignee_bal, contract_id, 'contract',
                    f"Выплата за контракт #{contract_id}")
        sea_bonus = grant_card_points_once(
            c, assignee_id, "card_sea", "contract_current", 5,
            "card_sea_current", f"контракт #{contract_id}", now.strftime('%Y-%m-%d'),
            contract_id, "contract",
        )
        c.execute("UPDATE contracts SET status='completed', completed_at=? WHERE id=?", (now_str, contract_id))
        log_economy(c, creator_id, 'contract_fee_burn', -fee, None, contract_id, 'contract',
                    f"Комиссия Сетевого Дозора: контракт #{contract_id}")
        conn.commit()
        conn.close()
        return {"success": True, "payout": payout, "fee_burned": fee, "card_sea_bonus": sea_bonus}
    return await db_write(_run)


@app.post("/api/contracts/{contract_id}/cancel")
async def cancel_contract(contract_id: int,
                           x_telegram_id: Optional[int] = Header(None),
                           x_admin_id: Optional[int] = Header(None)):
    def _run():
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
        # creator_telegram_id: the refund goes to the creator, which may differ
        # from the acting user when an admin cancels someone else's contract.
        return {"success": True, "refunded": reward, "creator_telegram_id": creator_id, "new_points": bal}
    return await db_write(_run)


@app.post("/api/contracts/{contract_id}/dispute")
async def dispute_contract(contract_id: int,
                            x_telegram_id: Optional[int] = Header(None),
                            x_admin_id: Optional[int] = Header(None)):
    def _run():
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
    return await db_write(_run)


@app.get("/api/admin/contracts")
def admin_list_contracts(x_admin_id: Optional[int] = Header(None),
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
                      u1.full_name, u2.full_name, u1.avatar_url, u2.avatar_url, c.is_anonymous
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
                      u1.full_name, u2.full_name, u1.avatar_url, u2.avatar_url, c.is_anonymous
               FROM contracts c
               LEFT JOIN users u1 ON u1.telegram_id=c.creator_telegram_id
               LEFT JOIN users u2 ON u2.telegram_id=c.assignee_telegram_id
               ORDER BY c.created_at DESC LIMIT 100''',
        )
    rows = c.fetchall()
    conn.close()
    return [
        {**_contract_to_dict(row[:16], row[16], row[17], row[18], row[19], None, bool(row[20]), False),
         "creator_name": row[16], "assignee_name": row[17],
         "creator_avatar_url": _safe_contract_avatar_url(row[18]),
         "assignee_avatar_url": _safe_contract_avatar_url(row[19]),
         "is_anonymous": bool(row[20])}
        for row in rows
    ]


@app.get("/api/admin/contracts/monitor")
def admin_contract_monitor(x_admin_id: Optional[int] = Header(None)):
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


@app.get("/api/admin/economy/report")
def admin_economy_report(since: Optional[str] = None, until: Optional[str] = None,
                          x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    if not since:
        since = (datetime.now(BEIJING_TZ) - timedelta(days=7)).strftime('%Y-%m-%d 00:00:00')
    elif len(since) == 10:
        since = since + " 00:00:00"
    if not until:
        until = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d 23:59:59')
    elif len(until) == 10:
        until = until + " 23:59:59"

    conn = get_conn()
    c = conn.cursor()

    c.execute(
        '''SELECT
             el.telegram_id,
             COALESCE(u.full_name, el.telegram_id) AS full_name,
             u.points,
             COUNT(*) AS tx_count,
             COALESCE(SUM(CASE WHEN el.amount>0 THEN el.amount ELSE 0 END),0) AS earned,
             COALESCE(SUM(CASE WHEN el.amount<0 THEN -el.amount ELSE 0 END),0) AS spent,
             COALESCE(SUM(CASE WHEN el.operation='shop_purchase' THEN -el.amount ELSE 0 END),0) AS shop_spent,
             COALESCE(SUM(CASE WHEN el.operation IN ('case_open','prayer_open') THEN 1 ELSE 0 END),0) AS cases_opened,
             COALESCE(SUM(CASE WHEN el.operation IN ('case_open','prayer_open') THEN -el.amount ELSE 0 END),0) AS cases_spent,
             COALESCE(SUM(CASE WHEN el.operation IN ('case_open','prayer_open') AND el.amount>0 THEN el.amount ELSE 0 END),0) AS cases_won,
             COALESCE(SUM(CASE WHEN el.operation='raid_entry' THEN 1 ELSE 0 END),0) AS raids_entered,
             COALESCE(SUM(CASE WHEN el.operation='raid_reward' THEN 1 ELSE 0 END),0) AS raids_won,
             COALESCE(SUM(CASE WHEN el.operation='gift_tax' THEN 1 ELSE 0 END),0) AS gifts_sent,
             COALESCE(SUM(CASE WHEN el.operation='gift_receive' THEN 1 ELSE 0 END),0) AS gifts_received,
             COALESCE(SUM(CASE WHEN el.operation IN ('presence_penalty','presence_rep_penalty','admin_points','bot_penalize') AND el.amount<0 THEN 1 ELSE 0 END),0) AS penalties,
             COALESCE(SUM(CASE WHEN el.operation IN ('bot_salary','bot_award') THEN el.amount ELSE 0 END),0) AS salary_award_total,
             COALESCE(SUM(CASE WHEN el.operation='contract_payout' THEN el.amount ELSE 0 END),0) AS contract_earnings,
             COALESCE(SUM(CASE WHEN el.operation='contract_freeze' THEN -el.amount ELSE 0 END),0) AS contract_spent
           FROM economy_log el
           LEFT JOIN users u ON u.telegram_id=el.telegram_id
           WHERE el.created_at BETWEEN ? AND ?
           GROUP BY el.telegram_id
           ORDER BY tx_count DESC''',
        (since, until),
    )
    rows = c.fetchall()
    conn.close()

    players = []
    for row in rows:
        earned, spent = row[4] or 0, row[5] or 0
        players.append({
            "telegram_id": row[0],
            "full_name": str(row[1]),
            "points": row[2] if row[2] is not None else None,
            "tx_count": row[3] or 0,
            "earned": earned,
            "spent": spent,
            "net": earned - spent,
            "shop_spent": row[6] or 0,
            "cases_opened": row[7] or 0,
            "cases_spent": row[8] or 0,
            "cases_won": row[9] or 0,
            "raids_entered": row[10] or 0,
            "raids_won": row[11] or 0,
            "gifts_sent": row[12] or 0,
            "gifts_received": row[13] or 0,
            "penalties": row[14] or 0,
            "salary_award_total": row[15] or 0,
            "contract_earnings": row[16] or 0,
            "contract_spent": row[17] or 0,
        })

    return {
        "since": since,
        "until": until,
        "summary": {
            "players": len(players),
            "total_earned": sum(p["earned"] for p in players),
            "total_spent": sum(p["spent"] for p in players),
            "total_cases_opened": sum(p["cases_opened"] for p in players),
            "total_raids_entered": sum(p["raids_entered"] for p in players),
            "total_gifts": sum(p["gifts_sent"] for p in players),
            "total_penalties": sum(p["penalties"] for p in players),
        },
        "players": players,
    }


@app.post("/api/admin/contracts/{contract_id}/resolve")
async def admin_resolve_contract(contract_id: int, data: dict,
                                  x_admin_id: Optional[int] = Header(None)):
    def _run():
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
    return await db_write(_run)
    return {"success": True, "action": action}
