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

# Defaults to "*" (unchanged behavior) to avoid breaking the live Mini App.
# Set CORS_ALLOWED_ORIGINS to a comma-separated list (e.g. "https://maruchoatomoshi.github.io")
# once the real Telegram WebView Origin behavior has been confirmed in production.
_cors_origins_env = os.getenv("CORS_ALLOWED_ORIGINS", "").strip()
CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors_origins_env.split(",") if o.strip()] or ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
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
# Many students share one campus Wi-Fi NAT, so a single client IP can carry
# dozens of distinct users. This caps total traffic per IP, separate from the
# per-user limit above.
try:
    RATE_LIMIT_MAX_REQUESTS_PER_IP = int(os.getenv("RATE_LIMIT_MAX_REQUESTS_PER_IP", "300") or "0")
except ValueError:
    RATE_LIMIT_MAX_REQUESTS_PER_IP = 300
BEIJING_TZ = pytz.timezone("Asia/Shanghai")

STUDY_GROUPS = {
    "A0": {
        "label": "1班 · A0",
        "description": "нули / начинающие",
        "duel_min_difficulty": 1,
        "duel_max_difficulty": 1,
        "rank": 1,
    },
    "A普": {
        "label": "2班 · A普",
        "description": "несколько месяцев - год",
        "duel_min_difficulty": 1,
        "duel_max_difficulty": 2,
        "rank": 2,
    },
    "A+": {
        "label": "3班 · A+",
        "description": "примерно пару лет",
        "duel_min_difficulty": 2,
        "duel_max_difficulty": 3,
        "rank": 3,
    },
    "B普": {
        "label": "4班 · B普",
        "description": "HSK 3-4",
        "duel_min_difficulty": 3,
        "duel_max_difficulty": 4,
        "rank": 4,
    },
    "SUPER": {
        "label": "5班 · SUPER",
        "description": "уверенный HSK 4",
        "duel_min_difficulty": 4,
        "duel_max_difficulty": 4,
        "rank": 5,
    },
}


def normalize_study_group(value: Optional[str]) -> Optional[str]:
    raw = str(value or "").strip()
    aliases = {
        "": None,
        "0": None,
        "none": None,
        "null": None,
        "a0": "A0",
        "а0": "A0",
        "a普": "A普",
        "а普": "A普",
        "a+": "A+",
        "а+": "A+",
        "b普": "B普",
        "б普": "B普",
        "super": "SUPER",
        "супер": "SUPER",
        "strong": "SUPER",
        "hsk4+": "SUPER",
    }
    mapped = aliases.get(raw.lower(), raw)
    return mapped if mapped in STUDY_GROUPS else None


def study_group_payload(value: Optional[str]) -> dict:
    code = normalize_study_group(value)
    meta = STUDY_GROUPS.get(code or "")
    if not code or not meta:
        return {
            "code": None,
            "label": "",
            "description": "",
            "duel_min_difficulty": None,
            "duel_max_difficulty": None,
            "rank": None,
        }
    return {"code": code, **meta}


def shop_day_str() -> str:
    """Shop daily limits/stock reset at 07:00 Beijing time, not midnight."""
    return (datetime.now(BEIJING_TZ) - timedelta(hours=7)).strftime('%Y-%m-%d')


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

COHORT_BEIJING = "beijing"
COHORT_MJU = "mju"
COHORT_CODES = {COHORT_BEIJING, COHORT_MJU}
MJU_ADMIN_IDS = frozenset(parse_int_list_env("MJU_ADMIN_IDS") or [244487659])
MJU_MEMBER_IDS = frozenset({
    5024821858, 5243992893, 5043234233, 5270862724, 1049679249,
    7366133308, 5973073048, 1324443747, 2055808907, 1295956600,
    244487659, 5983453551, 5306057873, 1541846222, 5220506877,
    5455635461, 5112589598, 5245376585, 5718009801, 5581257126,
    6480285200, 1192650264,
})
GLOBAL_ADMIN_IDS = frozenset(set(ADMIN_IDS) - set(MJU_ADMIN_IDS))
# Sanctioned accounts stay usable, but never appear in competitive rankings.
# Override through FLATLINED_IDS when the roster changes.
FLATLINED_IDS = frozenset(
    parse_int_list_env("FLATLINED_IDS")
    or [6157647579, 8579518402, 8580665130]
)
FLATLINED_ID_LIST = sorted(FLATLINED_IDS)
FLATLINED_PLACEHOLDERS = ",".join("?" * len(FLATLINED_ID_LIST))
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
    {"id": "redwall-defender", "name": "Хранитель Файрвола", "desc": "Отрази вторжение диких ИИ в Wild AI Breach",
     "category": "legendary", "check": lambda s: s["wildai_defender"]},
    {"id": "architect-victor", "name": "Покоритель Архитектора", "desc": "Победи Архитектора в Architect Protocol",
     "category": "legendary", "check": lambda s: s["architect_winner"]},
    {"id": "collector", "name": "Коллекционер протокола", "desc": "Имей 5+ разных имплантов/карточек одновременно",
     "category": "activity", "check": lambda s: len(s["implants"]) + len(s["cards"]) >= 5},
    {"id": "discipline", "name": "Дисциплинированный оператор", "desc": "Подтверди 15+ перекличек/отбоев",
     "category": "activity", "check": lambda s: s["confirmed_checks"] >= 15},
]
FRAME_IDS = {f["id"] for f in FRAME_DEFINITIONS}

# Title Player ("Титул дня") highlight presets — purely cosmetic, full-row
# glow on the leaderboard for the day. No mechanical effect, no economy impact.
TITLE_STYLE_PRESETS = [
    {"id": "cyan", "name": "Кибер-циан"},
    {"id": "gold", "name": "Золото протокола"},
    {"id": "violet", "name": "Фиолетовый сигнал"},
    {"id": "crimson", "name": "Багровая тревога"},
    {"id": "emerald", "name": "Изумрудный канал"},
]
TITLE_STYLE_IDS = {p["id"] for p in TITLE_STYLE_PRESETS}
TITLE_STYLE_DEFAULT = "cyan"


def compute_unlocked_frames(c, telegram_id: int) -> list:
    # Admins get every cosmetic frame unlocked by default — purely a display
    # perk, doesn't touch points/REP/leaderboard or any underlying stat.
    if telegram_id in ADMIN_IDS:
        return [f["id"] for f in FRAME_DEFINITIONS]

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

    c.execute("SELECT wildai_defender, architect_winner FROM user_status WHERE telegram_id=?", (telegram_id,))
    row = c.fetchone()
    wildai_defender = bool(row[0]) if row else False
    architect_winner = bool(row[1]) if row else False

    c.execute("SELECT COUNT(*) FROM daily_checks WHERE telegram_id=? AND status='confirmed'", (telegram_id,))
    confirmed_checks = c.fetchone()[0] or 0

    stats = {
        "rep": rep, "theme_path": theme_path, "implants": implants,
        "cards": cards, "raids": raids, "diary_stars": diary_stars,
        "wildai_defender": wildai_defender, "architect_winner": architect_winner,
        "confirmed_checks": confirmed_checks,
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
    if not API_INTERNAL_TOKEN:
        return False
    return hmac.compare_digest(request.headers.get("x-internal-token") or "", API_INTERNAL_TOKEN)


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
        r"^/api/diary/architect/(\d+)$",
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


async def enforce_verified_cohort(
    request: Request,
    verified_id: Optional[int],
    is_admin_request: bool,
):
    if not verified_id:
        return None

    requested_cohort = request.headers.get("x-cohort-code")
    conn = get_conn()
    try:
        c = conn.cursor()
        viewer_cohort = resolve_viewer_cohort(c, verified_id, requested_cohort)
        request.state.cohort_code = viewer_cohort

        candidate_ids = []
        path = request.url.path
        for pattern in (
            r"^/api/admin/user/(\d+)/dossier$",
            r"^/api/diary/(\d+)(?:/[^/]+)?$",
        r"^/api/diary/architect/(\d+)$",
            r"^/api/duel/(?:incoming|current|opponents)/(\d+)$",
        ):
            match = re.match(pattern, path)
            if match:
                candidate_ids.append(int(match.group(1)))

        for key in ("telegram_id", "caller_id"):
            value = request.query_params.get(key)
            if value:
                try:
                    candidate_ids.append(int(value))
                except ValueError:
                    return auth_error_response(request, f"Invalid {key}", 400)

        body = None
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if "application/json" in request.headers.get("content-type", ""):
                try:
                    body = await request.json()
                except Exception:
                    body = None
        if isinstance(body, dict):
            for key in (
                "telegram_id", "target_id", "to_id", "from_id", "opponent_id",
                "challenger_id", "creator_id", "assignee_id", "user_id",
            ):
                value = body.get(key)
                if value is None:
                    continue
                try:
                    candidate_ids.append(int(value))
                except (TypeError, ValueError):
                    return auth_error_response(request, f"Invalid {key}", 400)

        for candidate_id in set(candidate_ids):
            if candidate_id == verified_id:
                continue
            target_cohort = get_user_cohort(c, candidate_id)
            if target_cohort != viewer_cohort:
                return auth_error_response(
                    request,
                    "Пользователь находится в другом контуре",
                    403,
                )

        resource_checks = (
            (r"^/api/events/(\d+)", "events"),
            (r"^/api/contracts/(\d+)", "contracts"),
            (r"^/api/admin/contracts/(\d+)", "contracts"),
            (r"^/api/announcements/(\d+)", "announcements"),
            (r"^/api/schedule/(\d+)", "schedule"),
            (r"^/api/community-shop/proposals/(\d+)", "community_shop_proposals"),
            (r"^/api/admin/community-shop/proposals/(\d+)", "community_shop_proposals"),
            (r"^/api/laundry/schedule/(\d+)", "laundry_schedule"),
            (r"^/api/laundry/(\d+)$", "laundry"),
            (r"^/api/water/schedule/(\d+)", "water_schedule"),
        )
        for pattern, table_name in resource_checks:
            match = re.match(pattern, path)
            if not match:
                continue
            c.execute(
                f"SELECT cohort_code FROM {table_name} WHERE id=?",
                (int(match.group(1)),),
            )
            row = c.fetchone()
            if row and normalize_cohort_code(row[0]) != viewer_cohort:
                return auth_error_response(request, "Ресурс находится в другом контуре", 403)
            break

        if isinstance(body, dict) and body.get("event_id"):
            c.execute("SELECT cohort_code FROM events WHERE id=?", (int(body["event_id"]),))
            row = c.fetchone()
            if row and normalize_cohort_code(row[0]) != viewer_cohort:
                return auth_error_response(request, "Ивент находится в другом контуре", 403)
    finally:
        conn.close()

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

    verified_admin = is_verified_admin_request(request, verified_id)
    identity_error = await enforce_verified_user_identity(
        request,
        verified_id,
        verified_admin,
    )
    if identity_error:
        _log_telegram_auth(request, verified_id, "identity_mismatch")
        return identity_error

    cohort_error = await enforce_verified_cohort(request, verified_id, verified_admin)
    if cohort_error:
        _log_telegram_auth(request, verified_id, "cohort_mismatch")
        return cohort_error

    if TELEGRAM_AUTH_DEBUG_LOG and extract_path_telegram_id(request.url.path) is not None:
        _log_telegram_auth(request, verified_id, "ok")

    return await call_next(request)


# Sliding-window rate limit. nginx does not front this port (uvicorn
# terminates TLS directly on 8443), so this is the only request-volume guard.
#
# Limits are applied at two levels:
#  - per (IP, user) bucket — RATE_LIMIT_MAX_REQUESTS_PER_SECOND, catches a
#    single misbehaving client.
#  - per IP bucket — RATE_LIMIT_MAX_REQUESTS_PER_IP, catches abuse from one
#    address while still allowing many students behind one campus NAT.
_rate_limit_buckets: dict[str, deque] = {}
_rate_limit_ip_buckets: dict[str, deque] = {}
_rate_limit_lock = threading.Lock()


def _rate_limit_identity(request: Request) -> Optional[str]:
    header_id = request.headers.get("x-telegram-id") or request.headers.get("x-admin-id")
    if header_id:
        return str(header_id)
    path_id = extract_path_telegram_id(request.url.path)
    if path_id is not None:
        return str(path_id)
    query_id = request.query_params.get("telegram_id")
    if query_id:
        return str(query_id)
    return None


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if RATE_LIMIT_MAX_REQUESTS_PER_SECOND <= 0 or request_has_internal_token(request):
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    identity = _rate_limit_identity(request)
    now = time.monotonic()
    with _rate_limit_lock:
        # Per-user limit only applies when we can identify the user. Requests
        # without an identity (e.g. /api/leaderboard, /api/settings) are
        # shared by everyone behind the same NAT, so they're governed solely
        # by the higher per-IP limit below.
        if identity:
            bucket_key = f"{client_ip}:{identity}"
            bucket = _rate_limit_buckets.setdefault(bucket_key, deque())
            while bucket and now - bucket[0] > 1.0:
                bucket.popleft()
            if len(bucket) >= RATE_LIMIT_MAX_REQUESTS_PER_SECOND:
                return JSONResponse({"detail": "Too many requests"}, status_code=429)
            bucket.append(now)

        if RATE_LIMIT_MAX_REQUESTS_PER_IP > 0:
            ip_bucket = _rate_limit_ip_buckets.setdefault(client_ip, deque())
            while ip_bucket and now - ip_bucket[0] > 1.0:
                ip_bucket.popleft()
            if len(ip_bucket) >= RATE_LIMIT_MAX_REQUESTS_PER_IP:
                return JSONResponse({"detail": "Too many requests"}, status_code=429)
            ip_bucket.append(now)

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


#  Gift-code guessing throttle: locks out a telegram_id after repeated
#  "code not found" guesses, independent of the generic per-second rate
#  limiter above (which only caps request rate, not brute-force attempts
#  against a low-entropy code over time).
GIFT_CODE_MAX_FAILED_ATTEMPTS = 5
GIFT_CODE_LOCKOUT_WINDOW_SECONDS = 600
_gift_code_failed_attempts: dict[int, deque] = {}
_gift_code_lock = threading.Lock()


def _gift_code_attempt_locked_out(telegram_id: int) -> bool:
    now = time.monotonic()
    with _gift_code_lock:
        bucket = _gift_code_failed_attempts.setdefault(telegram_id, deque())
        while bucket and now - bucket[0] > GIFT_CODE_LOCKOUT_WINDOW_SECONDS:
            bucket.popleft()
        return len(bucket) >= GIFT_CODE_MAX_FAILED_ATTEMPTS


def _gift_code_record_failed_attempt(telegram_id: int) -> None:
    with _gift_code_lock:
        _gift_code_failed_attempts.setdefault(telegram_id, deque()).append(time.monotonic())


def _gift_code_clear_failed_attempts(telegram_id: int) -> None:
    with _gift_code_lock:
        _gift_code_failed_attempts.pop(telegram_id, None)


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
SHOP_EXTRA_RAID_PRICE = 30
SHOP_EXTRA_RAID_DAILY_LIMIT = 10
SHOP_ITEM_SEEDS = [
    # (code, name, desc, icon, price, daily_limit, category)
    # daily_limit=-1 → unlimited; >0 → global units sold per day cap
    ("immunity",    "Иммунитет",         "Блокирует один штраф",                          "🛡", 150,  5, "privilege"),
    ("laundry_vip", "Стирка VIP",         "Приоритет на стирку",                           "🧺", 150,  5, "privilege"),
    ("dj",          "DJ-сет",             "Право выбрать музыку",                          "🎵", 100,  1, "social"),
    ("amnesty",     "Амнистия",           "Снять один штраф по согласованию · до 00:00 по Пекину",  "🤝",  80,  5, "privilege"),
    ("kfc",         "KFC",                "Награда из специального меню",                  "🍗", 480,  5, "food"),
    ("bubbletea",   "Bubble Tea",         "Награда из специального меню",                  "🧋", 400,  5, "food"),
    ("no_report",   "Без доклада",        "Пропуск одного доклада по согласованию",        "📄", 400,  5, "vip"),
    ("poizon",      "Poizon",             "Премиальная награда",                           "👕", 600,  3, "vip"),
    ("double_win",  "Двойной сигнал",     "Удваивает очки первого открытия кейса или молитвы — после использования сгорает", "🎴", 130, 10, "privilege"),
    ("title_player","Титул дня",          "Особый титул профиля на сегодня",               "👑", 150, -1, "vip"),
    (SHOP_EXTRA_RAID_CODE, "Доп. рейд-попытка", "+1 рейд сегодня · лимит 10/день",       "⚔️", SHOP_EXTRA_RAID_PRICE, SHOP_EXTRA_RAID_DAILY_LIMIT, "privilege"),
    ("path_switch", "Смена пути 转换",    "Переключиться между NetWatch и Genshin",        "🔁", 500, -1, "vip"),
]
# Items removed from active catalog (deactivated on every startup so seeds don't re-enable them)
SHOP_ITEM_DEACTIVATE = {"extra_case", "solo_seat", "snack"}

# Items that expire at midnight (Beijing) after purchase.
# 0 = tonight 23:59 (same calendar day), 1 = tomorrow 23:59.
SHOP_ITEM_EXPIRY_DAYS = {
    'laundry_vip': 0,
    'kfc':         0,
    'bubbletea':   0,
    'immunity':    1,
    'amnesty':     0,
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
    ("gambler", "Исследователь вероятности", "Открыть кейсы или молитвы и принять результат достойно.", "♦", 0),
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
CONTRACT_EXPIRY_HOURS = 24
CONTRACT_AUTO_CONFIRM_HOURS = 24
CONTRACT_CATEGORIES = {'living', 'chinese', 'app', 'reminder', 'trade', 'other'}
LATIN_RE = re.compile(r'[A-Za-z]')
PINYIN_RE = re.compile(r"^(?:[A-Za-züÜvV:]+[1-5])+(?:[ '\\-](?:[A-Za-züÜvV:]+[1-5])+)*$")
ARCHITECT_DEFAULT_HP = 5000
ARCHITECT_DEFAULT_MIN_PLAYERS = 5
ARCHITECT_DEFAULT_MAX_PLAYERS = 15
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
WILD_AI_BREACH_FRAME_ID = "redwall-defender"
WILD_AI_BREACH_MVP_TITLE = "守墙者 / Хранитель Файрвола"

MJU_EVENT_CODE = "mju_protocol_boss"
MJU_DEFAULT_HP = 12000
MJU_DEFAULT_MIN_PLAYERS = 5
MJU_DEFAULT_MAX_PLAYERS = 15
MJU_PHASE2_THRESHOLD = 0.66
MJU_PHASE3_THRESHOLD = 0.33
MJU_VIOLATION_THRESHOLD = 18
MJU_CRITICAL_THRESHOLD = 45
MJU_BOSS_COUNTER_EVERY = 6
MJU_BOSS_COUNTER_PRESSURE = 3
MJU_REWARD_REP = 20


def _seed_question(difficulty: int, prompt: str, option_a: str, option_b: str, option_c: str, correct_option: str, explanation: str):
    return {
        "difficulty": difficulty,
        "prompt": prompt,
        "option_a": option_a,
        "option_b": option_b,
        "option_c": option_c,
        "correct_option": correct_option,
        "explanation": explanation,
    }


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

WILD_AI_BREACH_QUESTION_SEEDS["attack"].extend([
    _seed_question(1, "Сканер пишет 正在扫描病毒. Что делает система?", "Уже удалила вирус", "Сейчас сканирует вирус", "Собирается купить файл", "b", "正在 + глагол — действие происходит прямо сейчас."),
    _seed_question(1, "В отчёте: 已经删除备份了. Что произошло?", "Резервная копия уже удалена", "Резервная копия ещё создаётся", "Пароль ещё не найден", "a", "已经...了 — уже произошло."),
    _seed_question(1, "Команда узла: 把密码发给我. Что он требует?", "Сменить пароль", "Проверить учителя", "Отправить пароль мне", "c", "把密码发给我 — отправь пароль мне."),
    _seed_question(1, "Лог: 请求被系统拦截了. Что случилось с запросом?", "Запрос был перехвачен системой", "Запрос создал систему", "Запрос купил доступ", "a", "被 — пассив: запрос был перехвачен."),
    _seed_question(1, "Фраза 这个病毒比旧版本危险 означает:", "Этот вирус безопаснее старого", "Этот вирус опаснее старой версии", "Этот вирус такой же простой", "b", "比 используется для сравнения: A 比 B + качество."),
    _seed_question(1, "Сигнал 越来越快 говорит, что процесс...", "становится всё быстрее", "уже остановился", "слишком дешёвый", "a", "越来越 + прилагательное — всё более..."),
    _seed_question(1, "Что значит 一边复制一边删除?", "Сначала удалить, потом копировать", "Копировать и удалять одновременно", "Не копировать ничего", "b", "一边...一边... — делать два действия одновременно."),
    _seed_question(1, "Если в команде написано 如果连接失败，就切换节点, что делать при сбое связи?", "Переключить узел", "Закрыть дневник", "Попросить чай", "a", "如果...就... — если..., то..."),
    _seed_question(1, "虽然警报关闭，但是风险还在 означает:", "Хотя тревога выключена, риск остаётся", "Потому что риск ушёл, тревога открыта", "Если риск есть, купи билет", "a", "虽然...但是... — хотя..., но..."),
    _seed_question(1, "因为端口开放，所以被入侵了. Почему произошёл взлом?", "Потому что порт был открыт", "Потому что пароль был длинным", "Потому что система спала", "a", "因为...所以... — причина и следствие."),
    _seed_question(2, "除了管理员以外，谁都不能进入. Кто может войти?", "Все ученики", "Только администратор", "Любой с водой", "b", "除了...以外 — кроме; 谁都不能 — никто не может."),
    _seed_question(2, "这不是备份，而是陷阱. Что это?", "Не резервная копия, а ловушка", "Не ловушка, а расписание", "И резервная копия, и чай", "a", "不是...而是... — не..., а..."),
    _seed_question(1, "Команда 先下载，再运行 задаёт порядок:", "Сначала скачать, потом запустить", "Сначала запустить, потом удалить", "Сначала спать, потом сканировать", "a", "先...再... — сначала..., потом..."),
    _seed_question(2, "只要输入密码，就能进入 означает:", "Даже без пароля можно войти", "Как только введёшь пароль, можно войти", "Пароль всегда неверный", "b", "只要...就... — достаточно..., и..."),
    _seed_question(2, "连老师的设备也被攻击了. Что подчёркивает 连...也?", "Даже устройство учителя атаковано", "Только устройство ученика безопасно", "Учитель сам атаковал сеть", "a", "连...也... — даже... тоже..."),
    _seed_question(1, "可能正在监听 означает:", "Возможно, сейчас прослушивает", "Точно удалено вчера", "Нельзя сказать медленно", "a", "可能 — возможно; 正在 — сейчас делает действие."),
    _seed_question(2, "正在把数据传到外部服务器. Что происходит?", "Данные сейчас передаются на внешний сервер", "Данные уже вернулись домой", "Сервер просит обед", "a", "把数据传到... — передавать данные в..."),
    _seed_question(2, "趁管理员不在，打开后门. Когда ИИ открывает backdoor?", "Пока администратора нет", "После ужина", "Когда пароль правильный", "a", "趁... — пользуясь моментом, пока..."),
    _seed_question(1, "重新启动以后，病毒消失了. Когда вирус исчез?", "До перезапуска", "После перезапуска", "Во время покупки", "b", "以后 — после."),
    _seed_question(1, "还没检查完 означает:", "Ещё не закончили проверку", "Уже проверили дважды", "Проверять запрещено", "a", "还没...完 — ещё не закончили..."),
    _seed_question(1, "密钥被偷走了. Что произошло с ключом?", "Ключ был украден", "Ключ стал дешевле", "Ключ ждёт в комнате", "a", "被偷走了 — был украден/уведён."),
    _seed_question(2, "数据越多，风险越大 означает:", "Чем больше данных, тем больше риск", "Данные и риск не связаны", "Риск становится всё меньше", "a", "越...越... — чем..., тем..."),
    _seed_question(1, "让我看看日志. Что просит узел?", "Позволь мне посмотреть логи", "Заставь логи спать", "Купи лог за баллы", "a", "让 + кто-то + действие — позволить/дать сделать."),
    _seed_question(2, "你把防火墙关掉了吗？ Что спрашивают?", "Ты выключил файрвол?", "Ты построил файрвол?", "Ты купил файрвол?", "a", "把防火墙关掉 — выключить файрвол."),
    _seed_question(1, "好像有人控制摄像头. Что значит 好像?", "Кажется / похоже", "Никогда", "Слишком дорого", "a", "好像 — кажется, похоже."),
    _seed_question(2, "只有验证身份，才能继续. При каком условии можно продолжить?", "После проверки личности", "После покупки воды", "После сна", "a", "只有...才... — только если..., тогда..."),
    _seed_question(2, "刚才有人登录过. Что показывает 过?", "Уже был опыт/факт входа", "Вход произойдёт завтра", "Вход невозможен", "a", "过 показывает факт/опыт в прошлом."),
    _seed_question(1, "正在尝试破解密码 означает:", "Сейчас пытается взломать пароль", "Уже забыл пароль", "Просит повторить урок", "a", "尝试 + действие — пытаться что-то сделать."),
    _seed_question(2, "差点儿删除主系统. Что значит 差点儿?", "Почти удалил главную систему", "Медленно обновил систему", "Спокойно вошёл в систему", "a", "差点儿 — чуть не, почти."),
    _seed_question(2, "他把错误藏在日志里. Где спрятана ошибка?", "В логах", "В столовой", "В паспорте", "a", "把错误藏在日志里 — спрятал ошибку в логах."),
    _seed_question(2, "为了躲避扫描，它改变名字. Зачем ИИ меняет имя?", "Чтобы избежать сканирования", "Чтобы заказать еду", "Чтобы сказать спасибо", "a", "为了... — ради/для того чтобы..."),
    _seed_question(2, "一发现漏洞，就立刻攻击. Когда начинается атака?", "Как только найдена уязвимость", "Только через неделю", "Перед проверкой", "a", "一...就... — как только..., сразу..."),
    _seed_question(2, "如果不隔离进程，病毒会扩散. Что будет без изоляции процесса?", "Вирус распространится", "Система купит билет", "Файл станет учебником", "a", "会 — вероятное будущее действие."),
    _seed_question(2, "这不是普通错误，而是攻击信号. Что это?", "Обычная ошибка", "Сигнал атаки", "Домашнее задание", "b", "不是...而是... — не..., а..."),
    _seed_question(1, "系统被陌生设备连接了. Кто подключился?", "Неизвестное устройство", "Учебник китайского", "Пустой протокол", "a", "被陌生设备连接 — система подключена неизвестным устройством."),
    _seed_question(2, "越检查越奇怪 означает:", "Чем больше проверяем, тем страннее", "Проверять больше нельзя", "Чем быстрее едим, тем дешевле", "a", "越...越... — чем..., тем..."),
    _seed_question(2, "服务器已经被锁定三分钟了. Как долго сервер заблокирован?", "Три минуты", "Три дня", "Тридцать секунд", "a", "已经...三分钟了 — уже три минуты."),
    _seed_question(2, "在更新之前，先备份数据. Что нужно сделать перед обновлением?", "Сделать резервную копию данных", "Удалить учителя", "Закрыть карту", "a", "在...之前 — перед чем-то."),
    _seed_question(2, "它正在试图绕过权限. Что пытается сделать ИИ?", "Обойти права доступа", "Найти метро", "Заказать лапшу", "a", "绕过权限 — обойти права/разрешения."),
    _seed_question(1, "把可疑文件移动到隔离区. Что сделать с подозрительным файлом?", "Переместить в карантин", "Опубликовать в чат", "Съесть на завтрак", "a", "移动到隔离区 — переместить в зону изоляции."),
    _seed_question(2, "日志显示有人从外网进入. Откуда вошли?", "Из внешней сети", "Из столовой", "Из комнаты 539", "a", "从外网进入 — войти из внешней сети."),
    _seed_question(3, "即使密码正确，也不能放行. Что означает 即使...也...?", "Даже если пароль верный, всё равно нельзя пропускать", "Если пароль верный, всегда пускаем", "Пароль не нужен", "a", "即使...也... — даже если..., всё равно..."),
    _seed_question(2, "既不是学生，也不是老师. Кто это?", "Ни ученик, ни учитель", "И ученик, и учитель", "Только администратор", "a", "既不...也不... — ни..., ни..."),
    _seed_question(2, "由于网络异常，连接中断了. Почему связь прервалась?", "Из-за сетевой аномалии", "Потому что всё спокойно", "Из-за скидки в магазине", "a", "由于... — из-за/вследствие..."),
    _seed_question(2, "他一边聊天一边发送木马. Что он делает?", "Чатится и одновременно отправляет троян", "Сначала спит, потом пишет", "Только проверяет погоду", "a", "一边...一边... — одновременно."),
    _seed_question(2, "这个文件看起来像作业，其实是病毒. Что правда о файле?", "Похоже на домашку, но на самом деле вирус", "Это точно расписание", "Это обычная вода", "a", "其实 — на самом деле."),
    _seed_question(3, "不但复制了文件，还修改了权限. Что сделал ИИ?", "Не только скопировал файл, но и изменил права", "Только спросил дорогу", "Не смог ничего открыть", "a", "不但...还... — не только..., но и..."),
    _seed_question(2, "如果看到红色警报，马上断开连接. Что делать при красной тревоге?", "Сразу разорвать соединение", "Сделать селфи", "Подождать неделю", "a", "如果...马上... — если..., сразу..."),
    _seed_question(2, "它把真实地址隐藏起来了. Что сделал ИИ?", "Спрятал настоящий адрес", "Открыл карту метро", "Выучил новое слово", "a", "隐藏起来 — спрятать."),
    _seed_question(1, "防火墙还开着吗？ Что проверяют?", "Файрвол всё ещё включён?", "Кто купил чай?", "Где расписание?", "a", "着 показывает продолжающееся состояние: 开着 — включён."),
    _seed_question(2, "密码被谁改了？ Что спрашивают?", "Кем был изменён пароль?", "Кому купить пароль?", "Какой пароль вкусный?", "a", "被谁... — кем было сделано действие."),
    _seed_question(3, "除非管理员确认，否则不能执行. Когда можно выполнить команду?", "Только если администратор подтвердит", "Всегда без проверки", "Когда станет жарко", "a", "除非...否则... — если только не..., иначе..."),
    _seed_question(2, "这条命令比上一条更危险. Какая команда опаснее?", "Эта команда", "Предыдущая команда", "Обе команды безопасны", "a", "更危险 — более опасная."),
    _seed_question(1, "正在向所有节点传播. Что происходит?", "Распространяется ко всем узлам", "Возвращается в общежитие", "Просит пароль медленно", "a", "向...传播 — распространяться к/по направлению к..."),
])

WILD_AI_BREACH_QUESTION_SEEDS["protocol"].extend([
    _seed_question(1, "Как правильно сказать «отключить подозрительное соединение»?", "断开可疑连接。", "吃掉可疑连接。", "睡觉可疑连接。", "a", "断开连接 — разорвать соединение."),
    _seed_question(1, "Выбери верную фразу: «Нужно сначала проверить личность».", "需要先验证身份。", "先需要身份验证。", "身份需要吃饭。", "a", "先 ставится перед действием: сначала проверить."),
    _seed_question(1, "Правильный порядок: «Сначала изолируем вирус, потом восстановим систему».", "我们先隔离病毒，再恢复系统。", "我们病毒先系统再隔离。", "恢复先我们病毒再。", "a", "先...再... задаёт порядок действий."),
    _seed_question(1, "Как ответить на 你有没有权限？ если доступ есть?", "有，我有权限。", "我没有水。", "今天很热。", "a", "有/没有 отвечает на вопрос о наличии."),
    _seed_question(1, "Выбери команду «отправьте логи администратору».", "请把日志发给管理员。", "请把管理员吃给日志。", "请日志睡觉管理员。", "a", "把日志发给管理员 — отправить логи администратору."),
    _seed_question(1, "Как сказать «если найдёшь аномалию, сразу сообщи»?", "如果发现异常，就立刻报告。", "因为异常，所以吃饭。", "虽然报告，但是地图。", "a", "如果...就... — если..., то..."),
    _seed_question(1, "Выбери корректный 被-пассив: «данные защищены системой».", "数据被系统保护了。", "数据把系统保护了。", "系统被数据吃了。", "a", "被系统保护 — защищены системой."),
    _seed_question(1, "Как сказать «пожалуйста, закройте порт» с 把?", "请把端口关闭。", "请被端口关闭。", "请端口饭关闭。", "a", "把端口关闭 — закрыть порт."),
    _seed_question(1, "Выбери сравнение: «этот узел безопаснее того».", "这个节点比那个安全。", "这个节点被那个安全。", "这个节点把那个安全。", "a", "比 используется для сравнения."),
    _seed_question(1, "Как сказать «я уже проверял это»?", "我已经检查过了。", "我正在明天检查。", "我把昨天很贵。", "a", "已经...过了 — уже проверял/сделал."),
    _seed_question(1, "Выбери фразу «сканирование ещё не завершено».", "扫描还没有完成。", "扫描已经吃饭。", "扫描比老师完成。", "a", "还没有完成 — ещё не завершено."),
    _seed_question(2, "Как сказать «ради безопасности выйдите из системы»?", "为了安全，请退出系统。", "因为便宜，请吃系统。", "虽然安全，请买系统。", "a", "为了安全 — ради безопасности."),
    _seed_question(2, "Выбери верную конструкцию «только после подтверждения администратора можно выполнить».", "只有管理员确认，才能执行。", "只要老师吃饭，就能地图。", "除了执行以外，管理员都贵。", "a", "只有...才... — только если..., тогда..."),
    _seed_question(2, "Как сказать «как только получили тревогу, отключили соединение»?", "一收到警报，就断开连接。", "一吃到警报，就买连接。", "虽然收到，就很便宜。", "a", "一...就... — как только..., сразу..."),
    _seed_question(2, "Выбери безопасную фразу: «хотя срочно, не нажимай хаотично».", "虽然很紧急，但是不要乱点。", "因为很紧急，所以乱点。", "越紧急越买东西。", "a", "虽然...但是... — хотя..., но..."),
    _seed_question(2, "Как объяснить «соединение не удалось, потому что сеть нестабильна»?", "因为网络不稳定，所以连接失败。", "如果网络不稳定，就很好吃。", "虽然网络，连接买了。", "a", "因为...所以... — причина и результат."),
    _seed_question(1, "Выбери фразу «сначала следует сделать резервную копию».", "应该先备份数据。", "应该先删除老师。", "应该先喝端口。", "a", "应该 — следует; 先 — сначала."),
    _seed_question(1, "Как попросить повторить команду?", "请再说一遍命令。", "请再吃一遍命令。", "请再买一遍病毒。", "a", "再说一遍 — сказать ещё раз."),
    _seed_question(1, "Правильный порядок «сначала проверим список, потом продолжим».", "先检查名单，然后继续。", "名单然后先继续检查。", "继续先名单然后检查。", "a", "先...然后... — сначала..., затем..."),
    _seed_question(1, "Выбери фразу «система сейчас восстанавливается».", "系统正在恢复。", "系统已经昨天。", "系统比恢复。", "a", "正在恢复 — сейчас восстанавливается."),
    _seed_question(2, "Как сказать «чем быстрее найдём ошибку, тем безопаснее»?", "越快找到错误，越安全。", "因为找到错误，所以吃饭。", "除了错误以外，都睡觉。", "a", "越...越... — чем..., тем..."),
    _seed_question(2, "Что правильно для «кроме администратора, все выходят»?", "除了管理员以外，大家都退出。", "因为管理员以外，大家都便宜。", "把管理员以外，大家都喝水。", "a", "除了...以外 — кроме..."),
    _seed_question(3, "Выбери фразу «не только закрыли порт, но и сменили пароль».", "不但关闭了端口，还修改了密码。", "虽然关闭端口，但是吃密码。", "越端口越密码。", "a", "不但...还... — не только..., но и..."),
    _seed_question(2, "Как сказать «пожалуйста, не отправляй пароль в чат»?", "请不要把密码发到群里。", "请不要被密码群里。", "请密码不要吃群里。", "a", "把密码发到群里 — отправить пароль в группу."),
    _seed_question(2, "Выбери корректную фразу «ошибка была обнаружена системой».", "错误被系统发现了。", "错误把系统发现了。", "系统被错误买了。", "a", "被系统发现 — была обнаружена системой."),
    _seed_question(2, "Как сказать «перед запуском проверь права»?", "在运行之前，检查权限。", "运行以后之前权限。", "权限比运行之前。", "a", "在...之前 — перед..."),
    _seed_question(2, "Выбери фразу «после перезапуска снова проверь логи».", "重新启动以后，再检查日志。", "重新启动以前，已经吃日志。", "日志以后启动比再。", "a", "以后 — после; 再 — затем/ещё раз."),
    _seed_question(1, "Как сказать «давайте проверим соединение»?", "让我们检查连接。", "让连接吃我们。", "被我们检查吃饭。", "a", "让我们... — давайте..."),
    _seed_question(1, "Выбери фразу «возможно, это ложная тревога».", "这可能是假警报。", "这可能很吃饭。", "这已经比老师。", "a", "可能是 — возможно, это..."),
    _seed_question(1, "Как ответить на 是否继续执行？ если продолжаем?", "是，继续执行。", "我不吃辣。", "明天很冷。", "a", "继续执行 — продолжить выполнение."),
    _seed_question(1, "Выбери предупреждение «не открывай неизвестную ссылку».", "不要打开陌生链接。", "不要吃陌生链接。", "不要睡打开老师。", "a", "打开链接 — открыть ссылку."),
    _seed_question(1, "Как сказать «временно заблокировать аккаунт»?", "暂时锁定账号。", "暂时喝账号。", "账号暂时很热。", "a", "暂时 — временно; 锁定账号 — заблокировать аккаунт."),
    _seed_question(1, "Выбери фразу «сканирование завершено».", "扫描完成了。", "扫描太贵了。", "扫描去学校了。", "a", "完成了 — завершено."),
    _seed_question(1, "Как сказать «сохраняйте спокойствие и ждите»?", "保持冷静，等待通知。", "保持米饭，等待便宜。", "冷静保持吃通知。", "a", "保持冷静 — сохранять спокойствие."),
    _seed_question(1, "Выбери фразу «отправь скриншот учителю».", "把截图发给老师。", "把老师发给截图。", "被截图吃老师。", "a", "截图 — скриншот; 发给老师 — отправить учителю."),
    _seed_question(2, "Что правильно: «я разберусь с этой проблемой»?", "我会处理这个问题。", "我会吃这个问题。", "我会便宜这个问题。", "a", "处理问题 — разбираться/обрабатывать проблему."),
    _seed_question(1, "Как сказать «нет проблем»?", "没问题。", "没地图。", "没病毒饭。", "a", "没问题 — нет проблем."),
    _seed_question(2, "Выбери правильный порядок: «сегодня сначала встреча, потом тест».", "我们今天先开会，再测试。", "我们测试今天先开会再。", "先今天我们测试开会再。", "a", "时间 + 先...再..."),
    _seed_question(1, "Как попросить объяснить ещё раз?", "你能再解释一遍吗？", "你能再吃一遍吗？", "你能比解释地图吗？", "a", "解释一遍 — объяснить один раз."),
    _seed_question(2, "Выбери фразу «если не подключается, перезапусти приложение».", "如果连接不上，就重启应用。", "虽然连接不上，但是吃应用。", "因为应用，所以买连接。", "a", "连接不上 — не получается подключиться."),
    _seed_question(1, "Как сказать «система уже восстановлена»?", "系统已经恢复了。", "系统正在昨天。", "系统被明天了。", "a", "已经恢复了 — уже восстановлена."),
    _seed_question(1, "Выбери фразу «этот файл уже удалён».", "这个文件已经删除了。", "这个文件很吃饭。", "这个文件比老师。", "a", "已经删除了 — уже удалён."),
    _seed_question(2, "Как сказать «проверьте, открыт ли порт»?", "请检查端口是否开放。", "请吃端口是否开放。", "端口是否请买。", "a", "是否 — ли; 检查...是否... — проверить, ли..."),
    _seed_question(2, "Выбери правильное «не ошибка, а атака».", "这不是错误，而是攻击。", "这是错误，也是米饭。", "这不是攻击，因为很热。", "a", "不是...而是... — не..., а..."),
    _seed_question(3, "Как сказать «даже если всё выглядит нормально, всё равно проверь логи»?", "即使看起来正常，也要检查日志。", "因为看起来正常，所以不要检查。", "除了日志以外，都很便宜。", "a", "即使...也... — даже если..., всё равно..."),
    _seed_question(3, "Выбери фразу «если только админ не разрешит, иначе не выполняй».", "除非管理员允许，否则不要执行。", "只要管理员吃饭，就不要地图。", "虽然管理员允许，但是买执行。", "a", "除非...否则... — если только не..., иначе..."),
    _seed_question(2, "Как сказать «пока идёт проверка, не закрывай страницу»?", "检查的时候，不要关闭页面。", "页面的时候，不要吃检查。", "关闭的时候，页面很贵。", "a", "的时候 — во время/когда."),
    _seed_question(1, "Выбери фразу «не действуй один».", "不要一个人行动。", "不要一个人吃系统。", "不要行动很辣。", "a", "一个人行动 — действовать одному."),
    _seed_question(1, "Как сказать «ждите уведомления»?", "请等待通知。", "请吃通知。", "通知等待请水。", "a", "等待通知 — ждать уведомления."),
    _seed_question(2, "Выбери фразу «нам нужно снизить риск».", "我们需要降低风险。", "我们需要吃风险。", "风险需要我们很热。", "a", "降低风险 — снизить риск."),
    _seed_question(1, "Как сказать «это не твоя ошибка»?", "这不是你的错误。", "这是你的米饭。", "你的错误很便宜。", "a", "不是你的错误 — не твоя ошибка."),
    _seed_question(2, "Выбери фразу «файрвол уже перезапущен».", "防火墙已经重启了。", "防火墙正在吃饭。", "防火墙比老师。", "a", "重启 — перезапустить; 已经...了 — уже."),
    _seed_question(2, "Как сказать «команда выполняется, не закрывай окно»?", "命令正在执行，不要关闭窗口。", "命令正在吃饭，不要关闭老师。", "窗口比命令执行。", "a", "正在执行 — выполняется сейчас; 不要关闭窗口 — не закрывай окно."),
    _seed_question(3, "Выбери фразу «чем раньше сообщим, тем быстрее восстановим систему».", "越早报告，越快恢复系统。", "因为报告早，所以吃系统。", "除了系统以外，都很早。", "a", "越...越... — чем..., тем...; 恢复系统 — восстановить систему."),
])

WILD_AI_BREACH_QUESTION_SEEDS["stabilize"].extend([
    _seed_question(1, "Как сказать «успокойтесь немного»?", "冷静一点。", "便宜一点。", "吃饭一点。", "a", "冷静一点 — успокойтесь немного."),
    _seed_question(1, "Выбери фразу «проблема сейчас обрабатывается».", "问题正在处理。", "问题已经吃饭。", "问题比地图。", "a", "正在处理 — сейчас обрабатывается."),
    _seed_question(1, "Как сказать «резервная копия уже восстановлена»?", "备份已经恢复了。", "备份正在买饭。", "备份比老师远。", "a", "已经恢复了 — уже восстановлена."),
    _seed_question(1, "Если кому-то плохо, какая фраза подходит?", "如果不舒服，就告诉老师。", "如果很贵，就吃地图。", "虽然不舒服，但是买密码。", "a", "如果...就... — если..., то..."),
    _seed_question(1, "Выбери «сначала проверь, потом продолжай».", "先检查，然后继续。", "先继续，然后检查。", "检查然后先继续。", "a", "先...然后... — сначала..., затем..."),
    _seed_question(1, "Как сказать «все в безопасности»?", "大家都安全。", "大家都很贵。", "大家都吃端口。", "a", "大家都... — все..."),
    _seed_question(1, "Выбери поддержку «не волнуйся».", "不要担心。", "不要便宜。", "不要地图。", "a", "担心 — волноваться."),
    _seed_question(1, "Как сказать «я сейчас подойду»?", "我马上过来。", "我昨天买来。", "我比老师过来。", "a", "马上过来 — сейчас подойду."),
    _seed_question(1, "Выбери фразу «мы решим вместе».", "我们一起解决。", "我们一起吃病毒。", "我们一起很辣。", "a", "一起解决 — решить вместе."),
    _seed_question(1, "Как попросить объяснить ситуацию яснее?", "请把情况说清楚一点。", "请把米饭吃清楚一点。", "请情况买老师一点。", "a", "说清楚一点 — объяснить яснее."),
    _seed_question(1, "Выбери фразу «никто не потерялся».", "没有人迷路。", "没有人很贵。", "没有人吃端口。", "a", "迷路 — заблудиться."),
    _seed_question(2, "Как сказать «действуем по процедуре»?", "按照流程行动。", "按照米饭行动。", "流程比行动吃。", "a", "按照流程 — согласно процедуре."),
    _seed_question(1, "Выбери фразу «ждите на месте».", "在原地等。", "在原地买。", "等原地吃。", "a", "原地 — место, где находишься."),
    _seed_question(1, "Как сказать «не отходите от группы»?", "不要离开队伍。", "不要吃队伍。", "不要买队伍。", "a", "离开队伍 — отходить от группы."),
    _seed_question(1, "Выбери «связаться с ответственным».", "联系负责人。", "吃负责人。", "负责人很辣。", "a", "联系负责人 — связаться с ответственным."),
    _seed_question(2, "Как сказать «после подтверждения безопасности продолжим»?", "确认安全以后，我们继续。", "安全以前，我们吃饭。", "确认以后，比老师安全。", "a", "以后 — после; 确认安全 — подтвердить безопасность."),
    _seed_question(2, "虽然出了问题，但是已经解决了 означает:", "Хотя возникла проблема, её уже решили", "Потому что нет проблемы, купили рис", "Если дорогой билет, открой порт", "a", "虽然...但是... — хотя..., но..."),
    _seed_question(1, "因为信号弱，所以听不清楚. Почему плохо слышно?", "Потому что сигнал слабый", "Потому что всё безопасно", "Потому что пароль вкусный", "a", "因为...所以... — причина и следствие."),
    _seed_question(1, "Как сказать «если не понимаешь, спроси ещё раз»?", "如果不明白，就再问一遍。", "如果不明白，就吃一遍。", "虽然明白，但是买一遍。", "a", "再问一遍 — спросить ещё раз."),
    _seed_question(1, "Выбери просьбу «говорите медленнее».", "请说慢一点。", "请吃慢一点。", "请买快一点。", "a", "慢一点 — медленнее."),
    _seed_question(1, "Как сказать «я не расслышал»?", "我没听清楚。", "我没买清楚。", "我没吃地图。", "a", "没听清楚 — не расслышал."),
    _seed_question(1, "Выбери фразу «всем проверить телефоны».", "大家检查手机。", "大家吃手机。", "大家手机很贵。", "a", "检查手机 — проверить телефоны."),
    _seed_question(1, "Как сказать «держите телефон заряженным»?", "保持手机有电。", "保持手机很辣。", "手机保持吃饭。", "a", "有电 — есть заряд."),
    _seed_question(1, "Выбери вопрос «нужна помощь?»", "需要帮助吗？", "需要米饭吗？", "帮助很贵吗？", "a", "需要帮助吗 — нужна помощь?"),
    _seed_question(1, "Как сказать «мы перезапустим сервис»?", "我们会重启服务。", "我们会吃服务。", "服务会买我们。", "a", "重启服务 — перезапустить сервис."),
    _seed_question(1, "Выбери предупреждение «не трогай подозрительную ссылку».", "不要碰可疑链接。", "不要吃可疑链接。", "链接不要碰米饭。", "a", "碰 — трогать."),
    _seed_question(1, "Как сказать «данные сейчас восстанавливаются»?", "数据正在恢复。", "数据已经吃饭。", "数据比老师恢复。", "a", "正在恢复 — сейчас восстанавливаются."),
    _seed_question(2, "Выбери фразу «перед операцией сделай резервную копию».", "操作之前，先备份。", "操作以后，先吃饭。", "备份之前，操作很贵。", "a", "之前 — перед; 先 — сначала."),
    _seed_question(2, "Как сказать «когда тревога исчезнет, продолжим»?", "警报消失的时候，我们继续。", "警报吃饭的时候，我们买。", "继续消失警报很热。", "a", "的时候 — когда/во время."),
    _seed_question(2, "只要大家报告情况，就能解决. Что нужно, чтобы решить проблему?", "Чтобы все сообщили ситуацию", "Чтобы все купили чай", "Чтобы никто не говорил", "a", "只要...就... — достаточно..., и..."),
    _seed_question(2, "越冷静越安全 означает:", "Чем спокойнее, тем безопаснее", "Чем дороже, тем вкуснее", "Чем быстрее, тем холоднее", "a", "越...越... — чем..., тем..."),
    _seed_question(1, "Как сказать «не действуй один»?", "不要一个人行动。", "不要一个人吃饭。", "行动不要很贵。", "a", "一个人行动 — действовать одному."),
    _seed_question(2, "老师让我们在门口等 означает:", "Учитель попросил нас ждать у входа", "Учитель купил дверь", "Учитель спит в метро", "a", "让我们... — попросил/велел нам..."),
    _seed_question(1, "Выбери фразу «я проверяю местоположение».", "我正在确认位置。", "我已经吃位置。", "位置比我确认。", "a", "确认位置 — подтвердить местоположение."),
    _seed_question(1, "Как сказать «мы уже связались с администратором»?", "我们已经联系管理员了。", "我们正在吃管理员。", "管理员比我们联系。", "a", "已经联系...了 — уже связались."),
    _seed_question(1, "Выбери фразу «подождите три минуты».", "请等三分钟。", "请吃三分钟。", "三分钟很便宜。", "a", "等三分钟 — ждать три минуты."),
    _seed_question(1, "Как сказать «безопасная зона»?", "安全区域。", "便宜区域。", "吃饭区域。", "a", "安全区域 — безопасная зона."),
    _seed_question(2, "Если тревога продолжается, что означает 如果警报继续，就通知老师?", "Если тревога продолжится, сообщи учителю", "Если тревога вкусная, купи воду", "Хотя тревога есть, молчи", "a", "如果...就... — если..., то..."),
    _seed_question(1, "Выбери фразу «составить список».", "做名单。", "吃名单。", "名单很辣。", "a", "做名单 — сделать список."),
    _seed_question(1, "Как сказать «мы уже уведомили всех»?", "我们已经通知大家了。", "我们正在吃大家。", "大家比通知。", "a", "通知大家 — уведомить всех."),
    _seed_question(1, "Выбери фразу «не нужно спешить».", "不用着急。", "不用吃饭。", "着急很便宜。", "a", "不用着急 — не нужно спешить/волноваться."),
    _seed_question(2, "只有确认以后，才能离开. Когда можно уйти?", "Только после подтверждения", "Сразу без проверки", "Когда будет обед", "a", "只有...才... — только если/после..., тогда..."),
    _seed_question(1, "Как спросить «где ты сейчас?»", "你现在在哪儿？", "你现在吃什么？", "你现在多少钱？", "a", "在哪儿 — где находишься."),
    _seed_question(1, "Выбери просьбу «отправь геолокацию».", "请发送位置。", "请吃位置。", "位置发送很辣。", "a", "发送位置 — отправить местоположение."),
    _seed_question(2, "这不是迟到，而是在等老师. Что значит фраза?", "Это не опоздание, а ожидание учителя", "Это не учитель, а билет", "Это не ожидание, а еда", "a", "不是...而是... — не..., а..."),
    _seed_question(3, "即使害怕，也要保持冷静 означает:", "Даже если страшно, нужно сохранять спокойствие", "Если страшно, нужно бежать одному", "Потому что спокойно, надо спорить", "a", "即使...也... — даже если..., всё равно..."),
    _seed_question(1, "Как сказать «мы найдём решение»?", "我们会找到办法。", "我们会吃办法。", "办法比我们热。", "a", "找到办法 — найти способ/решение."),
    _seed_question(1, "Выбери фразу «я уже проверил, проблем нет».", "我已经检查过了，没有问题。", "我正在吃过了，很有问题。", "检查比问题过了。", "a", "检查过了 — уже проверил; 没有问题 — нет проблем."),
    _seed_question(1, "Как сказать «не передавай пароль другим»?", "不要把密码告诉别人。", "不要被密码吃别人。", "密码不要别人很贵。", "a", "告诉别人 — сообщать другим."),
    _seed_question(2, "Выбери фразу «проверь, взял ли ты вещи».", "检查一下你有没有带东西。", "吃一下你有没有带东西。", "东西有没有比检查。", "a", "有没有 — есть ли/взял ли."),
    _seed_question(1, "Как сказать «положи телефон в сумку»?", "把手机放进包里。", "被手机放进包里。", "手机吃进包里。", "a", "把手机放进包里 — положить телефон в сумку."),
    _seed_question(1, "Выбери фразу «сначала вернёмся в общежитие».", "我们先回宿舍。", "我们先吃宿舍。", "宿舍先买我们。", "a", "回宿舍 — вернуться в общежитие."),
    _seed_question(2, "Как сказать «мы будем действовать по правилам»?", "我们会按照规则行动。", "我们会吃规则行动。", "规则会比我们行动。", "a", "按照规则 — по правилам."),
    _seed_question(1, "Что означает 发生了什么事？", "Что случилось?", "Сколько стоит?", "Где метро?", "a", "发生了什么事 — что произошло/случилось?"),
])

MJU_QUESTION_SEEDS = {
    "attack": [
        {"prompt": "Проверка допуска: 纪律 означает...", "option_a": "Дисциплина", "option_b": "Скидка", "option_c": "Билет", "correct_option": "a", "explanation": "纪律 — дисциплина."},
        {"prompt": "Что значит 规则?", "option_a": "Правила", "option_b": "Подарок", "option_c": "Погода", "correct_option": "a", "explanation": "规则 — правила."},
        {"prompt": "Переведи 命令.", "option_a": "Команда / приказ", "option_b": "Ошибка", "option_c": "Перерыв", "correct_option": "a", "explanation": "命令 — команда, приказ."},
        {"prompt": "Что означает 检查?", "option_a": "Проверять", "option_b": "Покупать", "option_c": "Спать", "correct_option": "a", "explanation": "检查 — проверять."},
        {"prompt": "Выбери перевод 证件.", "option_a": "Документы / удостоверение", "option_b": "Еда", "option_c": "Зарядка", "correct_option": "a", "explanation": "证件 — документы, удостоверение."},
        {"prompt": "Что значит 禁止?", "option_a": "Запрещено", "option_b": "Разрешено", "option_c": "Бесплатно", "correct_option": "a", "explanation": "禁止 — запрещать, запрещено."},
        {"prompt": "Переведи 安静.", "option_a": "Тихо / спокойно", "option_b": "Быстро", "option_c": "Дорого", "correct_option": "a", "explanation": "安静 — тихий, спокойно."},
        {"prompt": "Что значит 排队?", "option_a": "Стоять в очереди", "option_b": "Играть", "option_c": "Забыть", "correct_option": "a", "explanation": "排队 — стоять в очереди."},
    ],
    "protocol": [
        {"prompt": "Выбери правильную фразу: «Пожалуйста, покажите документ».", "option_a": "请出示证件。", "option_b": "请喝一杯水。", "option_c": "请打开音乐。", "correct_option": "a", "explanation": "请出示证件 — пожалуйста, предъявите документ."},
        {"prompt": "Как сказать «Я понял правила»?", "option_a": "我明白规则了。", "option_b": "我买苹果了。", "option_c": "我很饿了。", "correct_option": "a", "explanation": "我明白规则了 — я понял правила."},
        {"prompt": "Выбери ответ на 你迟到了吗？", "option_a": "没有，我准时到了。", "option_b": "我不要辣。", "option_c": "这是多少钱？", "correct_option": "a", "explanation": "没有，我准时到了 — нет, я пришёл вовремя."},
        {"prompt": "Что логично ответить на 请保持安静。", "option_a": "好的，我会安静。", "option_b": "我要两碗面。", "option_c": "我去银行。", "correct_option": "a", "explanation": "好的，我会安静 — хорошо, я буду тихо."},
        {"prompt": "Как сказать «Собираемся в семь часов»?", "option_a": "七点集合。", "option_b": "七个苹果。", "option_c": "七块钱。", "correct_option": "a", "explanation": "集合 — собираться; 七点集合 — сбор в 7."},
        {"prompt": "Выбери правильный порядок: «Сначала проверим список».", "option_a": "先检查名单。", "option_b": "名单先检查。", "option_c": "检查先名单。", "correct_option": "a", "explanation": "先检查名单 — сначала проверить список."},
        {"prompt": "Как сказать «Не нарушай правила»?", "option_a": "不要违反规则。", "option_b": "不要买东西。", "option_c": "不要喝水。", "correct_option": "a", "explanation": "违反规则 — нарушать правила."},
        {"prompt": "Что означает 请按顺序来？", "option_a": "Пожалуйста, подходите по порядку", "option_b": "Пожалуйста, говорите громче", "option_c": "Пожалуйста, откройте окно", "correct_option": "a", "explanation": "按顺序 — по порядку."},
    ],
    "stabilize": [
        {"prompt": "Как сказать «Всё под контролем»?", "option_a": "一切都在控制中。", "option_b": "一切都很好吃。", "option_c": "一切都很便宜。", "correct_option": "a", "explanation": "一切都在控制中 — всё под контролем."},
        {"prompt": "Выбери фразу для спокойного подтверждения.", "option_a": "没问题，我马上处理。", "option_b": "太贵了，我不买。", "option_c": "我想吃米饭。", "correct_option": "a", "explanation": "没问题，我马上处理 — нет проблем, сейчас разберусь."},
        {"prompt": "Что значит 请冷静一点？", "option_a": "Пожалуйста, успокойтесь", "option_b": "Пожалуйста, ускорьтесь", "option_c": "Пожалуйста, заплатите", "correct_option": "a", "explanation": "冷静 — спокойный, хладнокровный."},
        {"prompt": "Как сказать «Я сейчас проверю»?", "option_a": "我现在检查一下。", "option_b": "我现在睡觉一下。", "option_c": "我现在买一下。", "correct_option": "a", "explanation": "检查一下 — проверить немного/сейчас."},
        {"prompt": "Выбери перевод 状态正常.", "option_a": "Состояние нормальное", "option_b": "Цена высокая", "option_c": "Комната пустая", "correct_option": "a", "explanation": "状态正常 — состояние нормальное."},
        {"prompt": "Что означает 已经解决了？", "option_a": "Уже решено", "option_b": "Уже потеряно", "option_c": "Уже куплено", "correct_option": "a", "explanation": "解决 — решить проблему."},
        {"prompt": "Как попросить повторить инструкцию?", "option_a": "请再说一遍说明。", "option_b": "请再买一瓶水。", "option_c": "请再去一次银行。", "correct_option": "a", "explanation": "说明 — инструкция, объяснение."},
        {"prompt": "Выбери фразу для отчёта: «Команда готова».", "option_a": "队伍准备好了。", "option_b": "队伍很便宜。", "option_c": "队伍去吃饭。", "correct_option": "a", "explanation": "队伍准备好了 — команда готова."},
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
        "option_a": "Вход",
        "option_b": "Выход",
        "option_c": "Склад",
        "correct_option": "b",
        "explanation": "出口 — выход, точка эвакуации отряда.",
        "difficulty": 1
    },
    {
        "prompt": "Бот-охранник задаёт вопрос: 你叫什么名字？ Что он спрашивает?",
        "option_a": "Твой возраст",
        "option_b": "Твоё имя",
        "option_c": "Пароль доступа",
        "correct_option": "b",
        "explanation": "你叫什么名字？ — как тебя зовут?",
        "difficulty": 1
    },
    {
        "prompt": "Перехвачена команда цели: 现在几点？ Что запрашивает система?",
        "option_a": "Местоположение",
        "option_b": "Уровень угрозы",
        "option_c": "Текущее время",
        "correct_option": "c",
        "explanation": "现在几点？ — который сейчас час?",
        "difficulty": 1
    },
    {
        "prompt": "Агент передаёт счёт ресурсов: 我有五十分。 Сколько единиц?",
        "option_a": "15",
        "option_b": "50",
        "option_c": "500",
        "correct_option": "b",
        "explanation": "五十 (wǔshí) — пятьдесят.",
        "difficulty": 1
    },
    {
        "prompt": "Цель ведёт переговоры в кафе. Слышно: 你吃什么？ О чём речь?",
        "option_a": "Что ты пьёшь",
        "option_b": "Сколько платишь",
        "option_c": "Что ты будешь есть",
        "correct_option": "c",
        "explanation": "你吃什么？ — что ты будешь есть?",
        "difficulty": 1
    },
    {
        "prompt": "Тревожный сигнал системы: 危险！ Что это значит?",
        "option_a": "Опасность",
        "option_b": "Безопасно",
        "option_c": "Продолжать",
        "correct_option": "a",
        "explanation": "危险 (wēixiǎn) — опасность.",
        "difficulty": 1
    },
    {
        "prompt": "Навигатор передаёт: 左转。 Куда повернуть?",
        "option_a": "Направо",
        "option_b": "Назад",
        "option_c": "Налево",
        "correct_option": "c",
        "explanation": "左 (zuǒ) — лево. 左转 — повернуть налево.",
        "difficulty": 1
    },
    {
        "prompt": "Агент легендируется: 我是学生。 Кем он представляется?",
        "option_a": "Врачом",
        "option_b": "Студентом",
        "option_c": "Охранником",
        "correct_option": "b",
        "explanation": "学生 (xuésheng) — студент / ученик.",
        "difficulty": 1
    },
    {
        "prompt": "Шифрованный запрос ресурсов: 这是多少钱？ Что запрашивают?",
        "option_a": "Где находится объект?",
        "option_b": "Когда начало операции?",
        "option_c": "Сколько это стоит?",
        "correct_option": "c",
        "explanation": "这是多少钱？ — сколько это стоит?",
        "difficulty": 1
    },
    {
        "difficulty": 1,
        "prompt": "На двери базы написано 入口. Что это?",
        "option_a": "Вход",
        "option_b": "Выход",
        "option_c": "Касса",
        "correct_option": "a",
        "explanation": "入口 — вход."
    },
    {
        "difficulty": 1,
        "prompt": "Маршрут построен через 地铁. Какой транспорт нужен?",
        "option_a": "Автобус",
        "option_b": "Метро",
        "option_c": "Такси",
        "correct_option": "b",
        "explanation": "地铁 — метро."
    },
    {
        "difficulty": 1,
        "prompt": "В отчёте указано 宿舍. Куда возвращается отряд?",
        "option_a": "В общежитие",
        "option_b": "В библиотеку",
        "option_c": "В магазин",
        "correct_option": "a",
        "explanation": "宿舍 — общежитие."
    },
    {
        "difficulty": 1,
        "prompt": "На карте отмечено 食堂. Что там находится?",
        "option_a": "Больница",
        "option_b": "Столовая",
        "option_c": "Станция метро",
        "correct_option": "b",
        "explanation": "食堂 — столовая."
    },
    {
        "difficulty": 1,
        "prompt": "Сканер нашёл 图书馆. Что это за место?",
        "option_a": "Спортзал",
        "option_b": "Кафе",
        "option_c": "Библиотека",
        "correct_option": "c",
        "explanation": "图书馆 — библиотека."
    },
    {
        "difficulty": 1,
        "prompt": "В экстренном маршруте стоит 医院. Что это?",
        "option_a": "Больница",
        "option_b": "Магазин",
        "option_c": "Почта",
        "correct_option": "a",
        "explanation": "医院 — больница / медпункт."
    },
    {
        "difficulty": 1,
        "prompt": "Оператор ищет 洗手间. Что ему нужно?",
        "option_a": "Столовая",
        "option_b": "Туалет",
        "option_c": "Банк",
        "correct_option": "b",
        "explanation": "洗手间 — туалет."
    },
    {
        "difficulty": 1,
        "prompt": "В сообщении: 我想喝水。 Что хочет агент?",
        "option_a": "Спать",
        "option_b": "Есть рис",
        "option_c": "Пить воду",
        "correct_option": "c",
        "explanation": "喝水 — пить воду."
    },
    {
        "difficulty": 1,
        "prompt": "Код питания: 米饭. Что заказано?",
        "option_a": "Рис",
        "option_b": "Лапша",
        "option_c": "Суп",
        "correct_option": "a",
        "explanation": "米饭 — варёный рис."
    },
    {
        "difficulty": 1,
        "prompt": "В меню найдено 面条. Что это?",
        "option_a": "Чай",
        "option_b": "Лапша",
        "option_c": "Фрукты",
        "correct_option": "b",
        "explanation": "面条 — лапша."
    },
    {
        "difficulty": 1,
        "prompt": "Система отмечает 鸡肉. Что это за еда?",
        "option_a": "Рыба",
        "option_b": "Говядина",
        "option_c": "Курица",
        "correct_option": "c",
        "explanation": "鸡肉 — куриное мясо."
    },
    {
        "difficulty": 1,
        "prompt": "Агент просит 不辣. Какой вкус ему нужен?",
        "option_a": "Не остро",
        "option_b": "Очень сладко",
        "option_c": "Очень холодно",
        "correct_option": "a",
        "explanation": "不辣 — не остро."
    },
    {
        "difficulty": 1,
        "prompt": "В погодном канале: 今天很热. Какая погода?",
        "option_a": "Холодно",
        "option_b": "Жарко",
        "option_c": "Ветрено",
        "correct_option": "b",
        "explanation": "很热 — очень жарко."
    },
    {
        "difficulty": 1,
        "prompt": "Отряд получил сигнал 冷. Что это значит?",
        "option_a": "Далеко",
        "option_b": "Дорого",
        "option_c": "Холодно",
        "correct_option": "c",
        "explanation": "冷 — холодный / холодно."
    },
    {
        "difficulty": 1,
        "prompt": "Команда говорит 今天. О каком дне речь?",
        "option_a": "Сегодня",
        "option_b": "Завтра",
        "option_c": "Вчера",
        "correct_option": "a",
        "explanation": "今天 — сегодня."
    },
    {
        "difficulty": 1,
        "prompt": "План операции на 明天. Когда это?",
        "option_a": "Вчера",
        "option_b": "Сегодня",
        "option_c": "Завтра",
        "correct_option": "c",
        "explanation": "明天 — завтра."
    },
    {
        "difficulty": 1,
        "prompt": "В журнале стоит 昨天. Когда это было?",
        "option_a": "Завтра",
        "option_b": "Вчера",
        "option_c": "Через неделю",
        "correct_option": "b",
        "explanation": "昨天 — вчера."
    },
    {
        "difficulty": 1,
        "prompt": "Навигатор показывает 右边. Где цель?",
        "option_a": "Справа",
        "option_b": "Слева",
        "option_c": "Позади",
        "correct_option": "a",
        "explanation": "右边 — справа."
    },
    {
        "difficulty": 1,
        "prompt": "Дрон пишет 前面. Где объект?",
        "option_a": "Сзади",
        "option_b": "Впереди",
        "option_c": "Внизу",
        "correct_option": "b",
        "explanation": "前面 — впереди."
    },
    {
        "difficulty": 1,
        "prompt": "На карте отмечено 后面. Где это?",
        "option_a": "Внутри",
        "option_b": "Справа",
        "option_c": "Сзади",
        "correct_option": "c",
        "explanation": "后面 — сзади / позади."
    },
    {
        "difficulty": 1,
        "prompt": "Оператор просит 一点儿. Сколько это?",
        "option_a": "Немного",
        "option_b": "Очень много",
        "option_c": "Нисколько",
        "correct_option": "a",
        "explanation": "一点儿 — немного."
    },
    {
        "difficulty": 1,
        "prompt": "Союзник пишет 谢谢. Что он говорит?",
        "option_a": "Извините",
        "option_b": "Спасибо",
        "option_c": "До свидания",
        "correct_option": "b",
        "explanation": "谢谢 — спасибо."
    },
    {
        "difficulty": 1,
        "prompt": "После ошибки агент говорит 对不起. Что это значит?",
        "option_a": "Пожалуйста",
        "option_b": "Не за что",
        "option_c": "Извините",
        "correct_option": "c",
        "explanation": "对不起 — извините."
    },
    {
        "difficulty": 1,
        "prompt": "Канал успокоения: 没关系. Как перевести?",
        "option_a": "Ничего страшного",
        "option_b": "Очень дорого",
        "option_c": "Слишком поздно",
        "correct_option": "a",
        "explanation": "没关系 — ничего страшного / всё в порядке."
    },
    {
        "difficulty": 1,
        "prompt": "Охранник говорит 请等一下. Что нужно сделать?",
        "option_a": "Бежать быстрее",
        "option_b": "Немного подождать",
        "option_c": "Купить билет",
        "correct_option": "b",
        "explanation": "请等一下 — пожалуйста, подождите немного."
    },
    {
        "difficulty": 1,
        "prompt": "Агент докладывает: 我听不懂. Что произошло?",
        "option_a": "Он всё понял",
        "option_b": "Он хочет есть",
        "option_c": "Он не понял на слух",
        "correct_option": "c",
        "explanation": "我听不懂 — я не понимаю на слух."
    },
    {
        "difficulty": 1,
        "prompt": "В инвентаре потерян 手机. Что ищем?",
        "option_a": "Телефон",
        "option_b": "Паспорт",
        "option_c": "Карту",
        "correct_option": "a",
        "explanation": "手机 — мобильный телефон."
    },
    {
        "difficulty": 2,
        "prompt": "Охранник спрашивает: 你去哪儿？ Какой ответ логичный?",
        "option_a": "我去宿舍。",
        "option_b": "三十块。",
        "option_c": "很好吃。",
        "correct_option": "a",
        "explanation": "你去哪儿？ — куда ты идёшь? 我去宿舍 — я иду в общежитие."
    },
    {
        "difficulty": 2,
        "prompt": "Бариста спрашивает: 你想喝什么？ Что ответить?",
        "option_a": "我去学校。",
        "option_b": "我想喝水。",
        "option_c": "现在八点。",
        "correct_option": "b",
        "explanation": "Вопрос о напитке: что ты хочешь пить?"
    },
    {
        "difficulty": 2,
        "prompt": "Система проверяет язык: 你会说中文吗？ Как ответить «немного умею»?",
        "option_a": "二十块。",
        "option_b": "往右走。",
        "option_c": "会一点儿。",
        "correct_option": "c",
        "explanation": "会一点儿 — умею немного."
    },
    {
        "difficulty": 2,
        "prompt": "Связь шумит. Как попросить повторить ещё раз?",
        "option_a": "请再说一遍。",
        "option_b": "请打开门。",
        "option_c": "请给我水。",
        "correct_option": "a",
        "explanation": "请再说一遍 — пожалуйста, повторите ещё раз."
    },
    {
        "difficulty": 2,
        "prompt": "Нужно спросить дорогу. Какая фраза подходит?",
        "option_a": "我很好吃。",
        "option_b": "请问，怎么走？",
        "option_c": "今天星期五。",
        "correct_option": "b",
        "explanation": "请问，怎么走？ — подскажите, как пройти?"
    },
    {
        "difficulty": 2,
        "prompt": "Агент пишет: 我迷路了. Что случилось?",
        "option_a": "Он заблудился",
        "option_b": "Он купил воду",
        "option_c": "Он пришёл вовремя",
        "correct_option": "a",
        "explanation": "迷路 — заблудиться."
    },
    {
        "difficulty": 2,
        "prompt": "Фраза: 请问，地铁站在哪儿？ Что ищет человек?",
        "option_a": "Больницу",
        "option_b": "Столовую",
        "option_c": "Станцию метро",
        "correct_option": "c",
        "explanation": "地铁站 — станция метро; 在哪儿 — где находится?"
    },
    {
        "difficulty": 2,
        "prompt": "Координатор спрашивает: 我们几点集合？ Что он хочет узнать?",
        "option_a": "Во сколько сбор",
        "option_b": "Сколько стоит еда",
        "option_c": "Где телефон",
        "correct_option": "a",
        "explanation": "几点集合？ — во сколько собираемся?"
    },
    {
        "difficulty": 2,
        "prompt": "Команда получила приказ: 七点半集合. Когда сбор?",
        "option_a": "В 7:00",
        "option_b": "В 7:30",
        "option_c": "В 8:30",
        "correct_option": "b",
        "explanation": "半 — половина; 七点半 — 7:30."
    },
    {
        "difficulty": 2,
        "prompt": "В протоколе дисциплины: 不要迟到. Что нельзя делать?",
        "option_a": "Покупать воду",
        "option_b": "Говорить громко",
        "option_c": "Опаздывать",
        "correct_option": "c",
        "explanation": "迟到 — опаздывать; 不要 — не надо."
    },
    {
        "difficulty": 2,
        "prompt": "Расписание: 先吃饭，然后上课. Что сначала?",
        "option_a": "Поесть",
        "option_b": "Пойти на урок",
        "option_c": "Вернуться в общежитие",
        "correct_option": "a",
        "explanation": "先 — сначала; 然后 — потом."
    },
    {
        "difficulty": 2,
        "prompt": "Агент докладывает: 我没有带护照. Чего у него нет с собой?",
        "option_a": "Телефона",
        "option_b": "Паспорта",
        "option_c": "Зонта",
        "correct_option": "b",
        "explanation": "没有带 — не взял с собой; 护照 — паспорт."
    },
    {
        "difficulty": 2,
        "prompt": "В магазине нужно торговаться. Какая фраза подходит?",
        "option_a": "可以便宜一点吗？",
        "option_b": "我迷路了。",
        "option_c": "请保持安静。",
        "correct_option": "a",
        "explanation": "可以便宜一点吗？ — можно немного дешевле?"
    },
    {
        "difficulty": 2,
        "prompt": "Заказ в киоске: 我要一瓶水. Что хочет агент?",
        "option_a": "Одну миску риса",
        "option_b": "Один билет",
        "option_c": "Одну бутылку воды",
        "correct_option": "c",
        "explanation": "一瓶水 — одна бутылка воды."
    },
    {
        "difficulty": 2,
        "prompt": "Покупатель говорит: 这个太贵了. Что он имеет в виду?",
        "option_a": "Это слишком дорого",
        "option_b": "Это очень вкусно",
        "option_c": "Это слишком далеко",
        "correct_option": "a",
        "explanation": "太贵了 — слишком дорого."
    },
    {
        "difficulty": 2,
        "prompt": "Нужна помощь. Какая фраза правильная?",
        "option_a": "我不吃牛肉。",
        "option_b": "请帮我一下。",
        "option_c": "天气很好。",
        "correct_option": "b",
        "explanation": "请帮我一下 — пожалуйста, помогите мне."
    },
    {
        "difficulty": 2,
        "prompt": "Союзник пишет: 我马上来. Когда он придёт?",
        "option_a": "Завтра",
        "option_b": "Уже ушёл",
        "option_c": "Сейчас / скоро",
        "correct_option": "c",
        "explanation": "马上 — сейчас, немедленно, очень скоро."
    },
    {
        "difficulty": 2,
        "prompt": "На улице жара. Какая фраза логична?",
        "option_a": "今天很热，多喝水。",
        "option_b": "今天很热，别带水。",
        "option_c": "今天很热，快睡觉。",
        "correct_option": "a",
        "explanation": "多喝水 — пей больше воды; при жаре это логично."
    },
    {
        "difficulty": 2,
        "prompt": "Прогноз: 如果下雨，带伞. Что нужно сделать, если пойдёт дождь?",
        "option_a": "Купить лапшу",
        "option_b": "Взять зонт",
        "option_c": "Сесть в метро",
        "correct_option": "b",
        "explanation": "如果 — если; 带伞 — взять зонт."
    },
    {
        "difficulty": 2,
        "prompt": "Маршрут: 我坐地铁去学校. Как агент едет в школу?",
        "option_a": "На метро",
        "option_b": "Пешком",
        "option_c": "На такси",
        "correct_option": "a",
        "explanation": "坐地铁 — ехать на метро."
    },
    {
        "difficulty": 2,
        "prompt": "Навигатор говорит: 往右走. Куда идти?",
        "option_a": "Прямо",
        "option_b": "Назад",
        "option_c": "Направо",
        "correct_option": "c",
        "explanation": "往右走 — идти направо."
    },
    {
        "difficulty": 2,
        "prompt": "Команда: 在前面的路口左转. Где повернуть налево?",
        "option_a": "У перекрёстка впереди",
        "option_b": "В комнате",
        "option_c": "На кассе",
        "correct_option": "a",
        "explanation": "前面的路口 — перекрёсток впереди; 左转 — повернуть налево."
    },
    {
        "difficulty": 2,
        "prompt": "В ресторане нужна карта блюд. Какая фраза подходит?",
        "option_a": "请给我地图。",
        "option_b": "请给我菜单。",
        "option_c": "请给我车票。",
        "correct_option": "b",
        "explanation": "菜单 — меню."
    },
    {
        "difficulty": 2,
        "prompt": "Агент предупреждает: 我不吃牛肉. Что он не ест?",
        "option_a": "Курицу",
        "option_b": "Рис",
        "option_c": "Говядину",
        "correct_option": "c",
        "explanation": "牛肉 — говядина."
    },
    {
        "difficulty": 3,
        "prompt": "В отчёте: 因为堵车，所以迟到了. Почему агент опоздал?",
        "option_a": "Из-за пробки",
        "option_b": "Из-за дождя",
        "option_c": "Из-за экзамена",
        "correct_option": "a",
        "explanation": "因为...所以... — потому что..., поэтому...; 堵车 — пробка."
    },
    {
        "difficulty": 3,
        "prompt": "Фраза после длинного дня: 虽然很累，但是很开心. Какой смысл?",
        "option_a": "Не устал и не рад",
        "option_b": "Хотя устал, но доволен",
        "option_c": "Потому что устал, ушёл",
        "correct_option": "b",
        "explanation": "虽然...但是... — хотя..., но..."
    },
    {
        "difficulty": 3,
        "prompt": "Протокол безопасности: 如果迷路了，就问老师. Что делать, если заблудился?",
        "option_a": "Спросить учителя",
        "option_b": "Купить билет",
        "option_c": "Закрыть дверь",
        "correct_option": "a",
        "explanation": "如果...就... — если..., то...; 问老师 — спросить учителя."
    },
    {
        "difficulty": 3,
        "prompt": "Агент пишет: 我把手机放在宿舍了. Где он оставил телефон?",
        "option_a": "В метро",
        "option_b": "В столовой",
        "option_c": "В общежитии",
        "correct_option": "c",
        "explanation": "把手机放在宿舍了 — положил/оставил телефон в общежитии."
    },
    {
        "difficulty": 3,
        "prompt": "Сравнение погоды: 北京比上海冷一点. Что говорится о Пекине?",
        "option_a": "Пекин немного холоднее Шанхая",
        "option_b": "Пекин намного дороже Шанхая",
        "option_c": "Пекин дальше Шанхая",
        "correct_option": "a",
        "explanation": "A 比 B + прилагательное — A более..., чем B; 冷一点 — немного холоднее."
    },
    {
        "difficulty": 3,
        "prompt": "После недели стажировки: 我们越来越熟悉北京了. Что происходит?",
        "option_a": "Мы всё меньше понимаем Пекин",
        "option_b": "Мы всё лучше узнаём Пекин",
        "option_c": "Мы уезжаем из Пекина",
        "correct_option": "b",
        "explanation": "越来越... — всё более и более...; 熟悉 — быть знакомым."
    },
    {
        "difficulty": 3,
        "prompt": "Маршрутный лог: 除了地铁以外，还可以坐公交. Что ещё можно сделать кроме метро?",
        "option_a": "Пойти в библиотеку",
        "option_b": "Купить воду",
        "option_c": "Поехать на автобусе",
        "correct_option": "c",
        "explanation": "除了...以外，还... — кроме..., ещё...; 坐公交 — ехать на автобусе."
    },
    {
        "difficulty": 3,
        "prompt": "Правило рейда: 只要按时集合，就不会扣分. При каком условии не снимут баллы?",
        "option_a": "Если прийти на сбор вовремя",
        "option_b": "Если купить чай",
        "option_c": "Если молчать весь день",
        "correct_option": "a",
        "explanation": "只要...就... — если только..., то...; 按时集合 — собраться вовремя."
    },
    {
        "difficulty": 3,
        "prompt": "Разведчик 一边走一边看地图. Что он делает?",
        "option_a": "Сначала спит, потом идёт",
        "option_b": "Идёт и одновременно смотрит карту",
        "option_c": "Смотрит меню и покупает воду",
        "correct_option": "b",
        "explanation": "一边...一边... — делать два действия одновременно."
    },
    {
        "difficulty": 3,
        "prompt": "Инструкция метро: 先刷卡，然后进站. Что сделать первым?",
        "option_a": "Выйти со станции",
        "option_b": "Спросить учителя",
        "option_c": "Приложить/провести карту",
        "correct_option": "c",
        "explanation": "先 — сначала; 刷卡 — провести/приложить карту."
    },
    {
        "difficulty": 3,
        "prompt": "Канал связи: 他正在跟老师讨论路线. Что он сейчас обсуждает с учителем?",
        "option_a": "Маршрут",
        "option_b": "Цену лапши",
        "option_c": "Погоду завтра",
        "correct_option": "a",
        "explanation": "正在 — действие происходит сейчас; 路线 — маршрут."
    },
    {
        "difficulty": 3,
        "prompt": "Оценка дистанции: 这个地方离宿舍不太远. Что известно о месте?",
        "option_a": "Оно очень дорогое",
        "option_b": "Оно не очень далеко от общежития",
        "option_c": "Оно закрыто",
        "correct_option": "b",
        "explanation": "离...远 — далеко от...; 不太远 — не очень далеко."
    },
    {
        "difficulty": 1,
        "prompt": "Сканер маршрута показывает 火车站. Что это за место?",
        "option_a": "Вокзал",
        "option_b": "Парк",
        "option_c": "Аптека",
        "correct_option": "a",
        "explanation": "火车站 — железнодорожный вокзал."
    },
    {
        "difficulty": 1,
        "prompt": "На карте операции отмечен 机场. Куда ведёт маршрут?",
        "option_a": "В аэропорт",
        "option_b": "В магазин",
        "option_c": "В столовую",
        "correct_option": "a",
        "explanation": "机场 — аэропорт."
    },
    {
        "difficulty": 1,
        "prompt": "Дрон нашёл 公园 рядом с базой. Что это?",
        "option_a": "Парк",
        "option_b": "Банк",
        "option_c": "Класс",
        "correct_option": "a",
        "explanation": "公园 — парк."
    },
    {
        "difficulty": 1,
        "prompt": "Отряд идёт в 超市. Что там можно сделать?",
        "option_a": "Купить продукты",
        "option_b": "Сдать экзамен",
        "option_c": "Постирать вещи",
        "correct_option": "a",
        "explanation": "超市 — супермаркет."
    },
    {
        "difficulty": 1,
        "prompt": "В экстренном маршруте указана 药店. Что это?",
        "option_a": "Аптека",
        "option_b": "Библиотека",
        "option_c": "Стадион",
        "correct_option": "a",
        "explanation": "药店 — аптека."
    },
    {
        "difficulty": 1,
        "prompt": "Координатор говорит 老师. О ком речь?",
        "option_a": "Об учителе",
        "option_b": "О студенте",
        "option_c": "О водителе",
        "correct_option": "a",
        "explanation": "老师 — учитель."
    },
    {
        "difficulty": 1,
        "prompt": "В списке группы написано 同学. Кто это?",
        "option_a": "Одноклассник / товарищ по учёбе",
        "option_b": "Охранник",
        "option_c": "Продавец",
        "correct_option": "a",
        "explanation": "同学 — одноклассник, сокурсник, товарищ по учёбе."
    },
    {
        "difficulty": 1,
        "prompt": "Система сообщает 早上集合. Когда сбор?",
        "option_a": "Утром",
        "option_b": "Вечером",
        "option_c": "Ночью",
        "correct_option": "a",
        "explanation": "早上 — утро."
    },
    {
        "difficulty": 1,
        "prompt": "В расписании стоит 晚上. Какое время суток?",
        "option_a": "Утро",
        "option_b": "Вечер",
        "option_c": "Полдень",
        "correct_option": "b",
        "explanation": "晚上 — вечер."
    },
    {
        "difficulty": 1,
        "prompt": "Протокол дня: 星期一. Какой это день?",
        "option_a": "Понедельник",
        "option_b": "Пятница",
        "option_c": "Воскресенье",
        "correct_option": "a",
        "explanation": "星期一 — понедельник."
    },
    {
        "difficulty": 1,
        "prompt": "Сигнал времени: 一点. Сколько времени?",
        "option_a": "Один час",
        "option_b": "Два часа",
        "option_c": "Полчаса",
        "correct_option": "a",
        "explanation": "一点 — один час."
    },
    {
        "difficulty": 1,
        "prompt": "Встреча назначена на 两点半. Когда это?",
        "option_a": "2:30",
        "option_b": "1:30",
        "option_c": "12:00",
        "correct_option": "a",
        "explanation": "两点半 — половина третьего, 2:30."
    },
    {
        "difficulty": 1,
        "prompt": "Охранник спрашивает 多少人？ Что он хочет узнать?",
        "option_a": "Сколько человек",
        "option_b": "Сколько денег",
        "option_c": "Куда идти",
        "correct_option": "a",
        "explanation": "多少人？ — сколько человек?"
    },
    {
        "difficulty": 1,
        "prompt": "Перед просьбой агент добавляет 请. Что это значит?",
        "option_a": "Пожалуйста",
        "option_b": "Опасно",
        "option_c": "Слишком дорого",
        "correct_option": "a",
        "explanation": "请 — пожалуйста; вежливый маркер просьбы."
    },
    {
        "difficulty": 2,
        "prompt": "Агент говорит: 我想买一张地铁票. Что он хочет купить?",
        "option_a": "Билет на метро",
        "option_b": "Бутылку воды",
        "option_c": "Карту города",
        "correct_option": "a",
        "explanation": "买一张地铁票 — купить один билет на метро."
    },
    {
        "difficulty": 2,
        "prompt": "Фраза для ориентации: 请问，洗手间在哪儿？ Что ищет человек?",
        "option_a": "Туалет",
        "option_b": "Выход",
        "option_c": "Столовую",
        "correct_option": "a",
        "explanation": "洗手间在哪儿？ — где туалет?"
    },
    {
        "difficulty": 2,
        "prompt": "Расписание группы: 我们明天上午八点集合. Когда сбор?",
        "option_a": "Завтра утром в 8",
        "option_b": "Сегодня вечером в 8",
        "option_c": "Вчера утром в 8",
        "correct_option": "a",
        "explanation": "明天上午八点集合 — завтра утром в 8 сбор."
    },
    {
        "difficulty": 2,
        "prompt": "Инструкция поддержки: 如果你累了，就休息一下. Что советуют сделать, если устал?",
        "option_a": "Немного отдохнуть",
        "option_b": "Бежать быстрее",
        "option_c": "Купить билет",
        "correct_option": "a",
        "explanation": "如果...就... — если..., то...; 休息一下 — немного отдохнуть."
    },
    {
        "difficulty": 2,
        "prompt": "Агент предупреждает: 我不太会说中文. Что он сообщает?",
        "option_a": "Он не очень хорошо говорит по-китайски",
        "option_b": "Он не любит китайскую еду",
        "option_c": "Он потерял телефон",
        "correct_option": "a",
        "explanation": "不太会说中文 — не очень умею говорить по-китайски."
    },
    {
        "difficulty": 2,
        "prompt": "В столовой агент говорит: 这个菜有点儿辣. Что не так с блюдом?",
        "option_a": "Немного острое",
        "option_b": "Очень холодное",
        "option_c": "Слишком дешёвое",
        "correct_option": "a",
        "explanation": "有点儿辣 — немного острое."
    },
    {
        "difficulty": 2,
        "prompt": "Маршрутный запрос: 从宿舍到教室怎么走？ Что хотят узнать?",
        "option_a": "Как пройти от общежития до аудитории",
        "option_b": "Сколько стоит обед",
        "option_c": "Где купить воду",
        "correct_option": "a",
        "explanation": "从...到...怎么走？ — как пройти от ... до ...?"
    },
    {
        "difficulty": 2,
        "prompt": "Отчёт разведчика: 我昨天去了图书馆. Где он был вчера?",
        "option_a": "В библиотеке",
        "option_b": "В больнице",
        "option_c": "В аэропорту",
        "correct_option": "a",
        "explanation": "昨天去了图书馆 — вчера ходил в библиотеку."
    },
    {
        "difficulty": 2,
        "prompt": "В кафе агент просит: 请给我一杯热水. Что ему нужно?",
        "option_a": "Стакан горячей воды",
        "option_b": "Холодная лапша",
        "option_c": "Билет на автобус",
        "correct_option": "a",
        "explanation": "一杯热水 — один стакан горячей воды."
    },
    {
        "difficulty": 2,
        "prompt": "План экскурсии: 我们坐公交车去博物馆. Как едет группа?",
        "option_a": "На автобусе",
        "option_b": "На метро",
        "option_c": "Пешком",
        "correct_option": "a",
        "explanation": "坐公交车 — ехать на автобусе; 博物馆 — музей."
    },
    {
        "difficulty": 2,
        "prompt": "Командный канал: 老师说不要迟到. Что сказал учитель?",
        "option_a": "Не опаздывать",
        "option_b": "Не пить воду",
        "option_c": "Не покупать билеты",
        "correct_option": "a",
        "explanation": "不要迟到 — не опаздывать."
    },
    {
        "difficulty": 3,
        "prompt": "Оперативный отчёт: 因为下雨，所以我们改坐地铁. Почему группа пересела на метро?",
        "option_a": "Из-за дождя",
        "option_b": "Из-за жары",
        "option_c": "Из-за пробки",
        "correct_option": "a",
        "explanation": "因为...所以... — потому что..., поэтому...; 下雨 — идёт дождь."
    },
    {
        "difficulty": 3,
        "prompt": "Агент пишет: 他把钥匙放在房间里了. Что он сделал с ключом?",
        "option_a": "Оставил/положил ключ в комнате",
        "option_b": "Купил новый ключ",
        "option_c": "Отдал ключ учителю",
        "correct_option": "a",
        "explanation": "把钥匙放在房间里 — положил ключ в комнате."
    },
    {
        "difficulty": 3,
        "prompt": "Фраза стажировки: 虽然中文有点难，但是我越来越喜欢. Какой смысл?",
        "option_a": "Хотя китайский немного сложный, он нравится всё больше",
        "option_b": "Китайский лёгкий, но не нравится",
        "option_c": "Китайский закончился вчера",
        "correct_option": "a",
        "explanation": "虽然...但是... — хотя..., но...; 越来越喜欢 — нравится всё больше."
    },
        {"difficulty": 1, "prompt": "Альфабосс мигает кодом 门. Что это?", "option_a": "Дверь", "option_b": "Окно", "option_c": "Карта", "correct_option": "a", "explanation": "门 — дверь."},
        {"difficulty": 1, "prompt": "На терминале рейда написано 开门. Что нужно сделать?", "option_a": "Закрыть дверь", "option_b": "Открыть дверь", "option_c": "Купить билет", "correct_option": "b", "explanation": "开门 — открыть дверь."},
        {"difficulty": 1, "prompt": "Система просит пароль: 密码. Что это?", "option_a": "Пароль", "option_b": "Адрес", "option_c": "Расписание", "correct_option": "a", "explanation": "密码 — пароль."},
        {"difficulty": 1, "prompt": "В логе рейда стоит ошибка 错. Что значит 错?", "option_a": "Правильно", "option_b": "Поздно", "option_c": "Ошибка / неверно", "correct_option": "c", "explanation": "错 — ошибка, неверно."},
        {"difficulty": 1, "prompt": "Команда отряда: 跟我走. Что это значит?", "option_a": "Следуй за мной", "option_b": "Жди здесь", "option_c": "Покупай воду", "correct_option": "a", "explanation": "跟我走 — иди/следуй за мной."},
        {"difficulty": 1, "prompt": "На карте отмечено 北门. Где точка?", "option_a": "Южные ворота", "option_b": "Северные ворота", "option_c": "Западная столовая", "correct_option": "b", "explanation": "北 — север, 门 — ворота/дверь."},
        {"difficulty": 1, "prompt": "Альфабосс спрашивает 几个人？ Что он хочет узнать?", "option_a": "Сколько людей", "option_b": "Сколько стоит", "option_c": "Который час", "correct_option": "a", "explanation": "几个人？ — сколько человек?"},
        {"difficulty": 1, "prompt": "Сканер показывает 红色. Какой это цвет?", "option_a": "Зелёный", "option_b": "Синий", "option_c": "Красный", "correct_option": "c", "explanation": "红色 — красный цвет."},
        {"difficulty": 1, "prompt": "Рейдовый чат: 快走！ Что значит?", "option_a": "Иди быстрее", "option_b": "Спи дольше", "option_c": "Плати меньше", "correct_option": "a", "explanation": "快走 — идти быстрее / быстрее уходим."},
        {"difficulty": 1, "prompt": "В инструкции написано 不要跑. Что запрещено?", "option_a": "Бежать", "option_b": "Пить воду", "option_c": "Слушать", "correct_option": "a", "explanation": "不要跑 — не бегай."},
        {"difficulty": 2, "prompt": "Альфабосс блокирует проход: 请排队. Что надо сделать?", "option_a": "Встать в очередь", "option_b": "Повернуть налево", "option_c": "Позвонить домой", "correct_option": "a", "explanation": "请排队 — пожалуйста, встаньте в очередь."},
        {"difficulty": 2, "prompt": "Команда координатора: 先集合，再出发. Какой порядок действий?", "option_a": "Сначала выезд, потом сбор", "option_b": "Сначала сбор, потом отправление", "option_c": "Сначала обед, потом сон", "correct_option": "b", "explanation": "先...再... — сначала..., потом..."},
        {"difficulty": 2, "prompt": "В отчёте: 门已经关上了. Что произошло с дверью?", "option_a": "Дверь уже закрыли", "option_b": "Дверь сломалась", "option_c": "Дверь стала дорогой", "correct_option": "a", "explanation": "已经关上了 — уже закрыто."},
        {"difficulty": 2, "prompt": "Система спрашивает 你带钥匙了吗？ Что проверяют?", "option_a": "Взял ли ключ", "option_b": "Купил ли рис", "option_c": "Понял ли погоду", "correct_option": "a", "explanation": "带钥匙 — взять ключ с собой."},
        {"difficulty": 2, "prompt": "Выбери правильный ответ на 你在哪儿？", "option_a": "我在宿舍门口。", "option_b": "三十块钱。", "option_c": "很好吃。", "correct_option": "a", "explanation": "На вопрос «где ты?» отвечает место."},
        {"difficulty": 2, "prompt": "Фраза 到门口等我 означает:", "option_a": "Жди меня у входа", "option_b": "Купи мне чай", "option_c": "Иди в библиотеку", "correct_option": "a", "explanation": "门口 — вход/у двери; 等我 — жди меня."},
        {"difficulty": 2, "prompt": "В канале тревоги: 不要离开队伍. Что нельзя делать?", "option_a": "Отходить от группы", "option_b": "Пить горячую воду", "option_c": "Говорить медленно", "correct_option": "a", "explanation": "离开队伍 — покидать группу."},
        {"difficulty": 2, "prompt": "Альфабосс требует: 请确认人数. Что нужно подтвердить?", "option_a": "Количество людей", "option_b": "Стоимость билета", "option_c": "Номер автобуса", "correct_option": "a", "explanation": "确认人数 — подтвердить число людей."},
        {"difficulty": 2, "prompt": "Команда в рейде: 把手机收起来. Что сделать с телефоном?", "option_a": "Убрать телефон", "option_b": "Купить телефон", "option_c": "Зарядить телефон", "correct_option": "a", "explanation": "把手机收起来 — убрать телефон."},
        {"difficulty": 2, "prompt": "Сигнал: 如果迷路，就打电话. Что делать, если заблудился?", "option_a": "Позвонить", "option_b": "Бежать", "option_c": "Молчать", "correct_option": "a", "explanation": "如果...就... — если..., то...; 打电话 — звонить."},
        {"difficulty": 2, "prompt": "Выбери верный перевод: 我们马上到。", "option_a": "Мы сейчас прибудем", "option_b": "Мы вчера купили", "option_c": "Мы далеко живём", "correct_option": "a", "explanation": "马上到 — скоро/сейчас прибудем."},
        {"difficulty": 2, "prompt": "Фраза 这里人很多 означает:", "option_a": "Здесь много людей", "option_b": "Здесь очень тихо", "option_c": "Здесь нет воды", "correct_option": "a", "explanation": "人很多 — много людей."},
        {"difficulty": 2, "prompt": "На экране: 请保持联系. Что просят делать?", "option_a": "Оставаться на связи", "option_b": "Сохранять чек", "option_c": "Открыть карту", "correct_option": "a", "explanation": "保持联系 — поддерживать связь."},
        {"difficulty": 2, "prompt": "Что означает 不要大声说话？", "option_a": "Не говорите громко", "option_b": "Не идите налево", "option_c": "Не покупайте дорого", "correct_option": "a", "explanation": "大声说话 — говорить громко."},
        {"difficulty": 2, "prompt": "Выбери правильную фразу: «Мы ждём учителя». ", "option_a": "我们等老师。", "option_b": "我们买老师。", "option_c": "我们吃老师。", "correct_option": "a", "explanation": "等老师 — ждать учителя."},
        {"difficulty": 2, "prompt": "Альфабосс пишет: 检查一下护照. Что проверить?", "option_a": "Паспорт", "option_b": "Погоду", "option_c": "Лапшу", "correct_option": "a", "explanation": "护照 — паспорт; 检查一下 — проверить."},
        {"difficulty": 2, "prompt": "Команда: 从东门进去. Откуда входить?", "option_a": "Через восточные ворота", "option_b": "Через северный парк", "option_c": "Через западную столовую", "correct_option": "a", "explanation": "东门 — восточные ворота."},
        {"difficulty": 2, "prompt": "Что значит 别忘了集合时间？", "option_a": "Не забудь время сбора", "option_b": "Не покупай билет", "option_c": "Не ешь острое", "correct_option": "a", "explanation": "别忘了 — не забудь; 集合时间 — время сбора."},
        {"difficulty": 2, "prompt": "Фраза 老师已经到了 означает:", "option_a": "Учитель уже пришёл", "option_b": "Учитель ещё спит", "option_c": "Учитель купил воду", "correct_option": "a", "explanation": "已经到了 — уже прибыл/пришёл."},
        {"difficulty": 2, "prompt": "Выбери логичный ответ на 你看到老师了吗？", "option_a": "看到了。", "option_b": "很好吃。", "option_c": "三点半。", "correct_option": "a", "explanation": "看到了 — увидел."},
        {"difficulty": 2, "prompt": "В протоколе: 走错路了. Что случилось?", "option_a": "Пошли не той дорогой", "option_b": "Купили не тот чай", "option_c": "Встали слишком рано", "correct_option": "a", "explanation": "走错路 — пойти не той дорогой."},
        {"difficulty": 2, "prompt": "Что означает 请大家一起走？", "option_a": "Пожалуйста, идите все вместе", "option_b": "Пожалуйста, ешьте отдельно", "option_c": "Пожалуйста, платите быстрее", "correct_option": "a", "explanation": "大家一起走 — все идут вместе."},
        {"difficulty": 3, "prompt": "Альфабосс даёт условие: 如果有人没到，就先等一下. Что делать, если кто-то не пришёл?", "option_a": "Сначала немного подождать", "option_b": "Сразу уехать", "option_c": "Купить ещё билет", "correct_option": "a", "explanation": "如果有人没到，就先等一下 — если кто-то не пришёл, сначала подождать."},
        {"difficulty": 3, "prompt": "Расшифруй: 虽然人很多，但是队伍很整齐. Что описано?", "option_a": "Людей много, но строй/очередь аккуратные", "option_b": "Людей мало и все ушли", "option_c": "Очередь дорогая, но вкусная", "correct_option": "a", "explanation": "虽然...但是... — хотя..., но...; 整齐 — аккуратный, стройный."},
        {"difficulty": 3, "prompt": "Фраза 他把钥匙交给老师了 означает:", "option_a": "Он передал ключ учителю", "option_b": "Он потерял учителя", "option_c": "Он купил ключ у учителя", "correct_option": "a", "explanation": "把钥匙交给老师 — передать ключ учителю."},
        {"difficulty": 3, "prompt": "Что значит 离宿舍有点远？", "option_a": "Немного далеко от общежития", "option_b": "Очень близко к столовой", "option_c": "Дешевле возле метро", "correct_option": "a", "explanation": "离...远 — далеко от...; 有点 — немного."},
        {"difficulty": 3, "prompt": "Выбери перевод: 我们到了以后再给你打电话。", "option_a": "Мы позвоним тебе после того, как приедем", "option_b": "Мы купим тебе билет до приезда", "option_c": "Мы спали, потому что опоздали", "correct_option": "a", "explanation": "到了以后 — после прибытия; 再 — затем."},
        {"difficulty": 3, "prompt": "Альфабосс пишет: 为了安全，请不要单独行动. Почему нельзя действовать одному?", "option_a": "Ради безопасности", "option_b": "Ради скидки", "option_c": "Ради завтрака", "correct_option": "a", "explanation": "为了安全 — ради безопасности; 单独行动 — действовать одному."},
        {"difficulty": 3, "prompt": "Фраза 如果听不懂，就请老师再说一遍 означает:", "option_a": "Если не понял на слух, попроси учителя повторить", "option_b": "Если не купил билет, попроси скидку", "option_c": "Если устал, открой дверь", "correct_option": "a", "explanation": "听不懂 — не понимать на слух; 再说一遍 — повторить ещё раз."},
        {"difficulty": 3, "prompt": "Что означает 先确认房间号，再发钥匙？", "option_a": "Сначала подтвердить номер комнаты, потом выдать ключ", "option_b": "Сначала купить ключ, потом забыть комнату", "option_c": "Сначала есть рис, потом идти в метро", "correct_option": "a", "explanation": "确认房间号 — подтвердить номер комнаты; 发钥匙 — выдать ключ."},
        {"difficulty": 3, "prompt": "Выбери правильный смысл: 因为下雨，所以我们改坐公交车. Почему изменили транспорт?", "option_a": "Из-за дождя", "option_b": "Из-за жары", "option_c": "Из-за экзамена", "correct_option": "a", "explanation": "因为下雨，所以... — потому что идёт дождь, поэтому..."},
        {"difficulty": 3, "prompt": "Команда: 请把名单发给我. Что нужно отправить?", "option_a": "Список имён", "option_b": "Бутылку воды", "option_c": "Номер автобуса устно", "correct_option": "a", "explanation": "名单 — список; 发给我 — отправить мне."},
        {"difficulty": 3, "prompt": "Что значит 只要大家都到了，我们就出发？", "option_a": "Как только все прибудут, мы отправимся", "option_b": "Если все устали, мы купим чай", "option_c": "Пока все спят, мы подождём", "correct_option": "a", "explanation": "只要...就... — как только/если условие выполнено, то..."},
        {"difficulty": 3, "prompt": "Расшифруй: 这个入口比那个入口近. Что сравнивают?", "option_a": "Этот вход ближе, чем тот", "option_b": "Этот билет дороже, чем тот", "option_c": "Эта комната тише, чем та", "correct_option": "a", "explanation": "比 — сравнение; 近 — близко."},
        {"difficulty": 3, "prompt": "Что означает 别忘了带学生证？", "option_a": "Не забудь взять студенческий/ученический документ", "option_b": "Не забудь купить чай", "option_c": "Не забудь закрыть метро", "correct_option": "a", "explanation": "学生证 — студенческий/ученический документ."},
        {"difficulty": 3, "prompt": "Фраза 我们按照老师的安排行动 означает:", "option_a": "Мы действуем по плану/распоряжению учителя", "option_b": "Мы едим по расписанию столовой", "option_c": "Мы спорим о цене билета", "correct_option": "a", "explanation": "按照安排行动 — действовать согласно плану."},
        {"difficulty": 3, "prompt": "Выбери смысл: 如果手机没电，就用同学的手机联系老师. Что делать, если телефон разрядился?", "option_a": "Связаться с учителем через телефон одногруппника", "option_b": "Купить новый телефон", "option_c": "Идти одному к метро", "correct_option": "a", "explanation": "没电 — разрядился; 联系老师 — связаться с учителем."},
        {"difficulty": 3, "prompt": "Альфабосс проверяет: 你能不能说明一下情况？ Что он просит?", "option_a": "Кратко объяснить ситуацию", "option_b": "Показать скидку", "option_c": "Купить воду", "correct_option": "a", "explanation": "说明情况 — объяснить ситуацию."},
        {"difficulty": 3, "prompt": "Что значит 到了以后不要乱走？", "option_a": "После прибытия не ходить куда попало", "option_b": "После еды не покупать чай", "option_c": "До приезда не говорить громко", "correct_option": "a", "explanation": "乱走 — ходить хаотично/куда попало."},
        {"difficulty": 3, "prompt": "Выбери перевод: 这件事应该先告诉负责人. Что нужно сделать сначала?", "option_a": "Сначала сообщить ответственному", "option_b": "Сначала купить билет", "option_c": "Сначала открыть окно", "correct_option": "a", "explanation": "负责人 — ответственный; 应该先 — следует сначала."},
        {"difficulty": 3, "prompt": "Фраза 为了不迟到，我们提前十分钟出发 означает:", "option_a": "Чтобы не опоздать, выходим на 10 минут раньше", "option_b": "Чтобы купить дешевле, ждём 10 минут", "option_c": "Чтобы поспать, приходим позже", "correct_option": "a", "explanation": "为了不迟到 — чтобы не опоздать; 提前 — заранее."},
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
        {"prompt": "Как переводится 左边?", "option_a": "Слева", "option_b": "Справа", "option_c": "Позади", "correct_option": "a", "explanation": "左边 — слева."},
        {"prompt": "Что значит 出口?", "option_a": "Вход", "option_b": "Выход", "option_c": "Остановка", "correct_option": "b", "explanation": "出口 — выход."},
        {"prompt": "Выбери перевод 入口.", "option_a": "Вход", "option_b": "Библиотека", "option_c": "Стадион", "correct_option": "a", "explanation": "入口 — вход."},
        {"prompt": "Как переводится 宿舍?", "option_a": "Общежитие", "option_b": "Класс", "option_c": "Магазин", "correct_option": "a", "explanation": "宿舍 — общежитие."},
        {"prompt": "Что значит 教室?", "option_a": "Столовая", "option_b": "Аудитория / класс", "option_c": "Банк", "correct_option": "b", "explanation": "教室 — аудитория, учебный класс."},
        {"prompt": "Как переводится 食堂?", "option_a": "Столовая", "option_b": "Больница", "option_c": "Почта", "correct_option": "a", "explanation": "食堂 — столовая."},
        {"prompt": "Что значит 图书馆?", "option_a": "Библиотека", "option_b": "Спортзал", "option_c": "Кофейня", "correct_option": "a", "explanation": "图书馆 — библиотека."},
        {"prompt": "Выбери перевод 医院.", "option_a": "Медпункт / больница", "option_b": "Магазин", "option_c": "Метро", "correct_option": "a", "explanation": "医院 — больница, медицинский пункт."},
        {"prompt": "Как переводится 手机?", "option_a": "Телефон", "option_b": "Паспорт", "option_c": "Карта", "correct_option": "a", "explanation": "手机 — мобильный телефон."},
        {"prompt": "Что значит 护照?", "option_a": "Билет", "option_b": "Паспорт", "option_c": "Кошелёк", "correct_option": "b", "explanation": "护照 — паспорт."},
        {"prompt": "Выбери перевод 太远了.", "option_a": "Слишком далеко", "option_b": "Слишком дорого", "option_c": "Слишком вкусно", "correct_option": "a", "explanation": "太远了 — слишком далеко."},
        {"prompt": "Как переводится 快一点?", "option_a": "Немного быстрее", "option_b": "Немного дешевле", "option_c": "Немного холоднее", "correct_option": "a", "explanation": "快一点 — немного быстрее."},
        {"difficulty": 1, "prompt": "Что значит 水?", "option_a": "Вода", "option_b": "Огонь", "option_c": "Деньги", "correct_option": "a", "explanation": "水 — вода."},
        {"difficulty": 1, "prompt": "Как переводится 茶?", "option_a": "Чай", "option_b": "Рис", "option_c": "Автобус", "correct_option": "a", "explanation": "茶 — чай."},
        {"difficulty": 1, "prompt": "Что значит 老师?", "option_a": "Учитель", "option_b": "Студент", "option_c": "Водитель", "correct_option": "a", "explanation": "老师 — учитель."},
        {"difficulty": 1, "prompt": "Как переводится 同学?", "option_a": "Одноклассник / сокурсник", "option_b": "Полицейский", "option_c": "Продавец", "correct_option": "a", "explanation": "同学 — ученик одной группы, одноклассник или сокурсник."},
        {"difficulty": 1, "prompt": "Что значит 雨?", "option_a": "Дождь", "option_b": "Солнце", "option_c": "Ветер", "correct_option": "a", "explanation": "雨 — дождь."},
        {"difficulty": 1, "prompt": "Как переводится 热水?", "option_a": "Горячая вода", "option_b": "Холодный чай", "option_c": "Сладкий рис", "correct_option": "a", "explanation": "热水 — горячая вода."},
        {"difficulty": 2, "prompt": "Что значит 打车?", "option_a": "Взять такси", "option_b": "Играть в карты", "option_c": "Открыть дверь", "correct_option": "a", "explanation": "打车 — взять такси / поехать на такси."},
        {"difficulty": 2, "prompt": "Как переводится 迷路?", "option_a": "Заблудиться", "option_b": "Опоздать", "option_c": "Поторопиться", "correct_option": "a", "explanation": "迷路 — заблудиться."},
        {"difficulty": 2, "prompt": "Что значит 集合?", "option_a": "Сбор / собираться", "option_b": "Покупка", "option_c": "Погода", "correct_option": "a", "explanation": "集合 — сбор, собираться вместе."},
        {"difficulty": 2, "prompt": "Как переводится 安全?", "option_a": "Безопасность", "option_b": "Скидка", "option_c": "Завтрак", "correct_option": "a", "explanation": "安全 — безопасность."},
        {"difficulty": 2, "prompt": "Что значит 规则?", "option_a": "Правила", "option_b": "Ключи", "option_c": "Фрукты", "correct_option": "a", "explanation": "规则 — правила."},
        {"difficulty": 2, "prompt": "Как переводится 迟到?", "option_a": "Опоздать", "option_b": "Успеть", "option_c": "Отдохнуть", "correct_option": "a", "explanation": "迟到 — опоздать."},
        {"difficulty": 2, "prompt": "Что значит 准时?", "option_a": "Вовремя", "option_b": "Случайно", "option_c": "Далеко", "correct_option": "a", "explanation": "准时 — вовремя."},
        {"difficulty": 2, "prompt": "Как переводится 充电器?", "option_a": "Зарядка", "option_b": "Кошелёк", "option_c": "Полотенце", "correct_option": "a", "explanation": "充电器 — зарядное устройство."},
        {"difficulty": 3, "prompt": "Что значит 需要帮助?", "option_a": "Нужна помощь", "option_b": "Нужен билет", "option_c": "Нужен дождь", "correct_option": "a", "explanation": "需要 — нуждаться; 帮助 — помощь."},
        {"difficulty": 3, "prompt": "Как переводится 联系老师?", "option_a": "Связаться с учителем", "option_b": "Попросить скидку", "option_c": "Закрыть комнату", "correct_option": "a", "explanation": "联系 — связаться; 老师 — учитель."},
        {"difficulty": 3, "prompt": "Что значит 保持安静?", "option_a": "Сохранять тишину", "option_b": "Быстро идти", "option_c": "Покупать воду", "correct_option": "a", "explanation": "保持 — сохранять; 安静 — тишина, спокойствие."},
        {"difficulty": 3, "prompt": "Как переводится 先集合，然后出发?", "option_a": "Сначала сбор, потом отправляемся", "option_b": "Сначала еда, потом сон", "option_c": "Сначала покупка, потом скидка", "correct_option": "a", "explanation": "先...然后... — сначала..., затем..."},
        {"difficulty": 3, "prompt": "Что значит 一直往前走?", "option_a": "Идти всё время прямо", "option_b": "Повернуть назад", "option_c": "Подождать в комнате", "correct_option": "a", "explanation": "一直 — всё время; 往前走 — идти вперёд."},
        {"difficulty": 3, "prompt": "Как переводится 附近有地铁站吗?", "option_a": "Рядом есть станция метро?", "option_b": "Сколько стоит рис?", "option_c": "Где мой паспорт?", "correct_option": "a", "explanation": "附近 — рядом; 地铁站 — станция метро."},
        {"difficulty": 2, "prompt": "Архитектор шифрует маршрут: 从宿舍到教室要走十分钟. Сколько идти от общежития до класса?", "option_a": "10 минут", "option_b": "20 минут", "option_c": "1 час", "correct_option": "a", "explanation": "要走十分钟 — нужно идти 10 минут."},
        {"difficulty": 2, "prompt": "Что значит 信号很弱，需要靠近一点？", "option_a": "Сигнал слабый, нужно подойти ближе", "option_b": "Сигнал сильный, нужно уйти", "option_c": "Сигнал дорогой, нужно купить", "correct_option": "a", "explanation": "信号很弱 — сигнал слабый; 靠近一点 — подойти ближе."},
        {"difficulty": 2, "prompt": "Выбери перевод: 这个入口暂时关闭。", "option_a": "Этот вход временно закрыт", "option_b": "Этот выход очень далеко", "option_c": "Эта дверь открыта навсегда", "correct_option": "a", "explanation": "暂时关闭 — временно закрыто."},
        {"difficulty": 2, "prompt": "Архитектор пишет: 先扫描二维码. Что сделать сначала?", "option_a": "Сначала отсканировать QR-код", "option_b": "Сначала купить воду", "option_c": "Сначала идти спать", "correct_option": "a", "explanation": "先 — сначала; 扫描二维码 — сканировать QR-код."},
        {"difficulty": 2, "prompt": "Что означает 请把护照放在桌子上？", "option_a": "Положите паспорт на стол", "option_b": "Покажите билет в метро", "option_c": "Поставьте воду под стол", "correct_option": "a", "explanation": "把护照放在桌子上 — положить паспорт на стол."},
        {"difficulty": 2, "prompt": "Выбери смысл: 我们快到了.", "option_a": "Мы скоро прибудем", "option_b": "Мы уже заблудились", "option_c": "Мы не покупаем", "correct_option": "a", "explanation": "快到了 — скоро прибудем."},
        {"difficulty": 2, "prompt": "Что значит 右边第二个门？", "option_a": "Вторая дверь справа", "option_b": "Вторая дверь слева", "option_c": "Первое окно справа", "correct_option": "a", "explanation": "右边 — справа; 第二个门 — вторая дверь."},
        {"difficulty": 2, "prompt": "Архитектор показывает 状态异常. Что с системой?", "option_a": "Состояние необычное / сбой", "option_b": "Состояние нормальное", "option_c": "Цена снижена", "correct_option": "a", "explanation": "异常 — аномалия, ненормальное состояние."},
        {"difficulty": 3, "prompt": "Расшифруй: 这个地方离地铁站比离宿舍近. Что ближе к этому месту?", "option_a": "Станция метро", "option_b": "Общежитие", "option_c": "Аэропорт", "correct_option": "a", "explanation": "比...近 — ближе, чем..."},
        {"difficulty": 3, "prompt": "Что значит 如果网络断了，就重新连接？", "option_a": "Если сеть отключилась, подключиться заново", "option_b": "Если идёт дождь, купить билет", "option_c": "Если устал, закрыть дверь", "correct_option": "a", "explanation": "如果...就... — если..., то...; 重新连接 — подключиться заново."},
        {"difficulty": 3, "prompt": "Выбери перевод: 他把资料发给老师了。", "option_a": "Он отправил материалы учителю", "option_b": "Он купил материалы в магазине", "option_c": "Он потерял учителя", "correct_option": "a", "explanation": "把资料发给老师 — отправить материалы учителю."},
        {"difficulty": 3, "prompt": "Фраза 虽然有点难，但是可以完成 означает:", "option_a": "Хотя немного сложно, но можно завершить", "option_b": "Потому что легко, можно уйти", "option_c": "Хотя дешево, но нельзя купить", "correct_option": "a", "explanation": "虽然...但是... — хотя..., но...; 完成 — завершить."},
        {"difficulty": 3, "prompt": "Архитектор спрашивает: 你能解释这个原因吗？ Что он просит?", "option_a": "Объяснить причину", "option_b": "Повторить имя", "option_c": "Сказать цену", "correct_option": "a", "explanation": "解释原因 — объяснить причину."},
        {"difficulty": 3, "prompt": "Что означает 系统正在恢复，请不要操作？", "option_a": "Система восстанавливается, не выполняйте действий", "option_b": "Система покупает билет", "option_c": "Система просит идти быстрее", "correct_option": "a", "explanation": "正在恢复 — восстанавливается; 不要操作 — не действуйте."},
        {"difficulty": 3, "prompt": "Выбери смысл: 为了节省时间，我们坐地铁. Почему едут на метро?", "option_a": "Чтобы сэкономить время", "option_b": "Чтобы купить дешевле", "option_c": "Чтобы увидеть учителя", "correct_option": "a", "explanation": "为了节省时间 — чтобы сэкономить время."},
        {"difficulty": 3, "prompt": "Что значит 入口在前面，但是出口在后面？", "option_a": "Вход впереди, а выход сзади", "option_b": "Вход справа, а выход слева", "option_c": "Вход закрыт, а выход дорогой", "correct_option": "a", "explanation": "前面 — впереди; 后面 — сзади."},
        {"difficulty": 3, "prompt": "Архитектор пишет: 只有管理员可以修改设置. Кто может менять настройки?", "option_a": "Только администратор", "option_b": "Любой студент", "option_c": "Только водитель", "correct_option": "a", "explanation": "只有...可以... — только ... может ..."},
        {"difficulty": 3, "prompt": "Выбери перевод: 请确认所有人都收到了消息。", "option_a": "Подтвердите, что все получили сообщение", "option_b": "Подтвердите, что все купили воду", "option_c": "Скажите, что сообщение дорогое", "correct_option": "a", "explanation": "确认 — подтвердить; 收到消息 — получить сообщение."},
        {"difficulty": 3, "prompt": "Что означает 数据更新以后，界面会自动刷新？", "option_a": "После обновления данных интерфейс обновится автоматически", "option_b": "После покупки билета дверь закроется", "option_c": "После ужина телефон пропадёт", "correct_option": "a", "explanation": "以后 — после; 自动刷新 — обновиться автоматически."},
        {"difficulty": 3, "prompt": "Фраза 如果发现错误，请马上报告 означает:", "option_a": "Если обнаружишь ошибку, сразу сообщи", "option_b": "Если купишь билет, сразу ешь", "option_c": "Если идёт дождь, спи", "correct_option": "a", "explanation": "发现错误 — обнаружить ошибку; 报告 — сообщить."},
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
        {"prompt": "Какой ответ подходит к 你住在哪儿？", "option_a": "我住在宿舍。", "option_b": "我吃米饭。", "option_c": "我买水。", "correct_option": "a", "explanation": "你住在哪儿？ — где ты живёшь? 我住在宿舍。 — я живу в общежитии."},
        {"prompt": "Выбери логичный ответ на 你想喝什么？", "option_a": "我想喝水。", "option_b": "我去学校。", "option_c": "现在八点。", "correct_option": "a", "explanation": "Вопрос о напитке: «Что хочешь пить?»"},
        {"prompt": "Какой ответ подходит к 你从哪儿来？", "option_a": "我从俄罗斯来。", "option_b": "我去食堂。", "option_c": "我很饿。", "correct_option": "a", "explanation": "你从哪儿来？ — откуда ты приехал?"},
        {"prompt": "Выбери правильный порядок слов для «Я сегодня иду в библиотеку».", "option_a": "我今天去图书馆。", "option_b": "去我图书馆今天。", "option_c": "今天图书馆我去。", "correct_option": "a", "explanation": "Нормальный порядок: 我 + время + 去 + место."},
        {"prompt": "Какой ответ подходит к 你会说中文吗？", "option_a": "会一点儿。", "option_b": "二十块。", "option_c": "往右走。", "correct_option": "a", "explanation": "会一点儿。 — умею немного."},
        {"prompt": "Выбери правильную фразу для покупки воды.", "option_a": "我要一瓶水。", "option_b": "我要一个地铁。", "option_c": "我要一本米饭。", "correct_option": "a", "explanation": "一瓶水 — одна бутылка воды."},
        {"prompt": "Что лучше ответить на 你累吗？", "option_a": "有点儿累。", "option_b": "我在银行。", "option_c": "不要辣。", "correct_option": "a", "explanation": "有点儿累。 — немного устал."},
        {"prompt": "Выбери правильное отрицание: «Я не понимаю».", "option_a": "我不懂。", "option_b": "我很懂。", "option_c": "我去懂。", "correct_option": "a", "explanation": "不 + глагол даёт отрицание: 我不懂。"},
        {"prompt": "Какой ответ подходит к 你要不要辣？", "option_a": "不要辣。", "option_b": "我叫马克。", "option_c": "今天星期一。", "correct_option": "a", "explanation": "不要辣。 — не острое."},
        {"prompt": "Выбери правильную фразу: «Пожалуйста, дайте чек».", "option_a": "请给我小票。", "option_b": "请给我天气。", "option_c": "请给我左边。", "correct_option": "a", "explanation": "小票 — чек."},
        {"prompt": "Какой ответ подходит к 几点集合？", "option_a": "八点集合。", "option_b": "很好吃。", "option_c": "我不买。", "correct_option": "a", "explanation": "几点集合？ — во сколько сбор?"},
        {"prompt": "Выбери правильный перевод фразы 我们一起走吧。", "option_a": "Пойдём вместе", "option_b": "Я хочу спать", "option_c": "Это слишком дорого", "correct_option": "a", "explanation": "一起 — вместе, 走吧 — пойдём."},
        {"difficulty": 1, "prompt": "Как ответить на 你是学生吗？", "option_a": "是，我是学生。", "option_b": "我买水。", "option_c": "太远了。", "correct_option": "a", "explanation": "На вопрос «Ты студент?» логично ответить: 是，我是学生。"},
        {"difficulty": 1, "prompt": "Выбери ответ на 你喝水吗？", "option_a": "喝，谢谢。", "option_b": "我去银行。", "option_c": "昨天很贵。", "correct_option": "a", "explanation": "喝，谢谢。 — буду пить, спасибо."},
        {"difficulty": 1, "prompt": "Что ответить на 你冷吗？", "option_a": "有点儿冷。", "option_b": "三十块。", "option_c": "在左边。", "correct_option": "a", "explanation": "有点儿冷 — немного холодно."},
        {"difficulty": 1, "prompt": "Выбери правильную просьбу купить чай.", "option_a": "我要一杯茶。", "option_b": "我要一张老师。", "option_c": "我要一个地铁。", "correct_option": "a", "explanation": "一杯茶 — один стакан/чашка чая."},
        {"difficulty": 1, "prompt": "Как спросить «Где туалет?»", "option_a": "洗手间在哪儿？", "option_b": "你叫什么名字？", "option_c": "现在几点？", "correct_option": "a", "explanation": "洗手间在哪儿？ — где туалет?"},
        {"difficulty": 1, "prompt": "Выбери правильную фразу: «Я живу в комнате 539».", "option_a": "我住在五三九房间。", "option_b": "我吃五三九米饭。", "option_c": "我买五三九水。", "correct_option": "a", "explanation": "住在...房间 — жить в комнате..."},
        {"difficulty": 2, "prompt": "Что ответить на 你怎么去学校？", "option_a": "我坐地铁去。", "option_b": "我很便宜。", "option_c": "我叫手机。", "correct_option": "a", "explanation": "Вопрос «Как ты едешь в школу?» — ответ про транспорт."},
        {"difficulty": 2, "prompt": "Выбери правильный порядок: «Я завтра утром в восемь пойду в класс».", "option_a": "我明天上午八点去教室。", "option_b": "去教室我八点明天上午。", "option_c": "教室明天我去八点上午。", "correct_option": "a", "explanation": "Нормальный порядок: кто + время + действие + место."},
        {"difficulty": 2, "prompt": "Как попросить сделать чуть дешевле?", "option_a": "可以便宜一点吗？", "option_b": "可以热一点吗？", "option_c": "可以远一点吗？", "correct_option": "a", "explanation": "可以...吗？ — можно ли...? 便宜一点 — немного дешевле."},
        {"difficulty": 2, "prompt": "Что логично ответить на 你为什么迟到了？", "option_a": "因为堵车了。", "option_b": "我要一碗面。", "option_c": "我住在宿舍。", "correct_option": "a", "explanation": "Почему опоздал? — 因为堵车了, потому что была пробка."},
        {"difficulty": 2, "prompt": "Выбери фразу для просьбы показать дорогу.", "option_a": "请给我看一下路。", "option_b": "请给我吃一下路。", "option_c": "请给我买一下路。", "correct_option": "a", "explanation": "给我看一下 — покажите мне; 路 — дорога."},
        {"difficulty": 2, "prompt": "Как сказать «Я не ем острое»?", "option_a": "我不吃辣。", "option_b": "我不坐辣。", "option_c": "我不买热。", "correct_option": "a", "explanation": "辣 — острый; 不吃辣 — не ем острое."},
        {"difficulty": 2, "prompt": "Что ответить на 你带护照了吗？", "option_a": "带了。", "option_b": "很好吃。", "option_c": "在右边。", "correct_option": "a", "explanation": "带了 — взял/принёс с собой."},
        {"difficulty": 2, "prompt": "Выбери правильную фразу: «Мы уже пришли».", "option_a": "我们已经到了。", "option_b": "我们已经买了。", "option_c": "我们已经贵了。", "correct_option": "a", "explanation": "已经到了 — уже пришли/прибыли."},
        {"difficulty": 3, "prompt": "Что означает 如果下雨，我们坐地铁？", "option_a": "Если будет дождь, мы поедем на метро", "option_b": "Если дорого, купим рис", "option_c": "Если устали, споём песню", "correct_option": "a", "explanation": "如果... — если...; 下雨 — дождь; 坐地铁 — ехать на метро."},
        {"difficulty": 3, "prompt": "Выбери правильную фразу: «Когда закончится занятие, мы пойдём есть».", "option_a": "下课以后，我们去吃饭。", "option_b": "吃饭以后，我们下课去。", "option_c": "我们以后下课吃饭去。", "correct_option": "a", "explanation": "以后 — после; 下课以后 — после окончания занятия."},
        {"difficulty": 3, "prompt": "Как сказать «Я забыл ключ в комнате»?", "option_a": "我把钥匙忘在房间里了。", "option_b": "我把米饭忘在地铁里了。", "option_c": "我把老师忘在水里了。", "correct_option": "a", "explanation": "把钥匙忘在房间里 — забыть ключ в комнате."},
        {"difficulty": 3, "prompt": "Что логично ответить на 你觉得今天的活动怎么样？", "option_a": "我觉得很有意思。", "option_b": "我坐右边。", "option_c": "我不要护照。", "correct_option": "a", "explanation": "觉得...怎么样 — спрашивают мнение; 很有意思 — интересно."},
        {"difficulty": 3, "prompt": "Выбери правильное продолжение: 因为太晚了，所以...", "option_a": "我们回宿舍。", "option_b": "我们买昨天。", "option_c": "我们喝左边。", "correct_option": "a", "explanation": "因为太晚了，所以我们回宿舍 — потому что слишком поздно, возвращаемся в общежитие."},
        {"difficulty": 3, "prompt": "Как вежливо уточнить, можно ли сфотографировать?", "option_a": "可以拍照吗？", "option_b": "可以睡觉吗？", "option_c": "可以迟到吗？", "correct_option": "a", "explanation": "拍照 — фотографировать; 可以...吗？ — можно ли...?"},
        {"difficulty": 2, "prompt": "Выбери правильный порядок: «Мы сегодня вечером проверим список».", "option_a": "我们今天晚上检查名单。", "option_b": "检查名单我们今天晚上。", "option_c": "今天名单我们晚上检查。", "correct_option": "a", "explanation": "Кто + время + действие + объект."},
        {"difficulty": 2, "prompt": "Как ответить на 你为什么没来集合？", "option_a": "因为我迷路了。", "option_b": "我要一杯茶。", "option_c": "这里很便宜。", "correct_option": "a", "explanation": "Вопрос почему — нужен ответ с причиной."},
        {"difficulty": 2, "prompt": "Что логично сказать администратору: «Я уже отправил сообщение»?", "option_a": "我已经发消息了。", "option_b": "我已经吃消息了。", "option_c": "我已经贵消息了。", "correct_option": "a", "explanation": "发消息 — отправить сообщение."},
        {"difficulty": 2, "prompt": "Выбери фразу: «Пожалуйста, проверьте ещё раз».", "option_a": "请再检查一遍。", "option_b": "请再吃一遍。", "option_c": "请再买一遍。", "correct_option": "a", "explanation": "再...一遍 — ещё раз выполнить действие."},
        {"difficulty": 2, "prompt": "Как спросить «Можно я задам вопрос?»", "option_a": "我可以问一个问题吗？", "option_b": "我可以吃一个问题吗？", "option_c": "我可以买一个问题吗？", "correct_option": "a", "explanation": "问一个问题 — задать вопрос."},
        {"difficulty": 2, "prompt": "Что ответить на 你收到通知了吗？", "option_a": "收到了。", "option_b": "很辣。", "option_c": "在左边。", "correct_option": "a", "explanation": "收到了 — получил."},
        {"difficulty": 2, "prompt": "Выбери правильную фразу: «Не забудь взять карту».", "option_a": "别忘了带地图。", "option_b": "别忘了吃地图。", "option_c": "别忘了买老师。", "correct_option": "a", "explanation": "带地图 — взять карту."},
        {"difficulty": 2, "prompt": "Как сказать «Я сейчас иду к входу»?", "option_a": "我现在去入口。", "option_b": "我现在吃入口。", "option_c": "我现在买入口。", "correct_option": "a", "explanation": "去入口 — идти ко входу."},
        {"difficulty": 3, "prompt": "Выбери смысл: 如果你不确定，就问负责人.", "option_a": "Если не уверен, спроси ответственного", "option_b": "Если не устал, купи билет", "option_c": "Если не холодно, открой воду", "correct_option": "a", "explanation": "不确定 — не уверен; 负责人 — ответственный."},
        {"difficulty": 3, "prompt": "Как правильно сказать: «После того как все подтвердят, мы начнём».", "option_a": "大家确认以后，我们开始。", "option_b": "我们开始以后，大家确认。", "option_c": "确认大家我们以后开始。", "correct_option": "a", "explanation": "...以后 — после того как..."},
        {"difficulty": 3, "prompt": "Что означает 他不是没来，而是迟到了？", "option_a": "Он не не пришёл, а опоздал", "option_b": "Он пришёл рано и ушёл", "option_c": "Он купил билет вместо воды", "correct_option": "a", "explanation": "不是...而是... — не..., а..."},
        {"difficulty": 3, "prompt": "Выбери корректный ответ на 你把钥匙放在哪儿了？", "option_a": "我把钥匙放在桌子上了。", "option_b": "我把桌子放在钥匙上了。", "option_c": "我把天气放在水里了。", "correct_option": "a", "explanation": "Вопрос: куда положил ключ? Ответ с 把 + ключ + место."},
        {"difficulty": 3, "prompt": "Фраза 这个问题比刚才的问题难一点 означает:", "option_a": "Этот вопрос немного сложнее предыдущего", "option_b": "Этот вопрос дешевле билета", "option_c": "Эта проблема ближе к метро", "correct_option": "a", "explanation": "比...难一点 — немного сложнее, чем..."},
        {"difficulty": 3, "prompt": "Как сказать «Я понял, но хочу уточнить одну деталь»?", "option_a": "我明白了，但是想确认一个细节。", "option_b": "我吃饭了，但是想买一个细节。", "option_c": "我迟到了，所以想睡觉。", "correct_option": "a", "explanation": "但是 — но; 确认细节 — уточнить деталь."},
        {"difficulty": 3, "prompt": "Что значит 为了避免迟到，请提前出发？", "option_a": "Чтобы избежать опоздания, выходите заранее", "option_b": "Чтобы купить дешевле, выходите позже", "option_c": "Чтобы не спать, ешьте заранее", "correct_option": "a", "explanation": "避免迟到 — избежать опоздания; 提前出发 — выйти заранее."},
        {"difficulty": 3, "prompt": "Выбери правильную фразу: «Если сообщение не пришло, обнови страницу».", "option_a": "如果消息没收到，就刷新页面。", "option_b": "如果页面没吃饭，就买消息。", "option_c": "如果老师没刷新，就迟到。", "correct_option": "a", "explanation": "刷新页面 — обновить страницу."},
        {"difficulty": 3, "prompt": "Что означает 我们先确认人数，再分组行动？", "option_a": "Сначала подтверждаем число людей, потом действуем по группам", "option_b": "Сначала едим, потом покупаем билеты", "option_c": "Сначала ждём дождь, потом идём спать", "correct_option": "a", "explanation": "分组行动 — действовать по группам."},
        {"difficulty": 3, "prompt": "Как ответить на 你能不能再说慢一点？", "option_a": "可以，我说慢一点。", "option_b": "不可以，我很贵。", "option_c": "可以，我吃慢一点。", "correct_option": "a", "explanation": "可以 — можно; 说慢一点 — говорить медленнее."},
        {"difficulty": 3, "prompt": "Фраза 只要按规则做，就不会有问题 означает:", "option_a": "Если действовать по правилам, проблем не будет", "option_b": "Если купить рис, будет скидка", "option_c": "Если идти быстро, будет дождь", "correct_option": "a", "explanation": "只要...就... — если выполнить условие, то..."},
        {"difficulty": 3, "prompt": "Что значит 请把这个情况告诉所有队员？", "option_a": "Сообщите эту ситуацию всем членам команды", "option_b": "Купите всем членам команды чай", "option_c": "Покажите всем номер комнаты", "correct_option": "a", "explanation": "告诉所有队员 — сообщить всем членам команды."},
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
        {"prompt": "Выбери фразу для вежливого извинения.", "option_a": "不好意思。", "option_b": "太好了。", "option_c": "很好吃。", "correct_option": "a", "explanation": "不好意思 — извините / неловко беспокоить."},
        {"prompt": "Что сказать, если нужно пройти?", "option_a": "借过一下。", "option_b": "我要米饭。", "option_c": "我很便宜。", "correct_option": "a", "explanation": "借过一下 — разрешите пройти."},
        {"prompt": "Как попросить говорить медленнее и понятнее?", "option_a": "请说慢一点。", "option_b": "请走快一点。", "option_c": "请买便宜一点。", "correct_option": "a", "explanation": "请说慢一点 — пожалуйста, говорите медленнее."},
        {"prompt": "Что означает 没问题?", "option_a": "Нет проблем", "option_b": "Нет денег", "option_c": "Нет времени", "correct_option": "a", "explanation": "没问题 — нет проблем."},
        {"prompt": "Выбери фразу, если потерялся.", "option_a": "我迷路了。", "option_b": "我很热。", "option_c": "我买东西。", "correct_option": "a", "explanation": "我迷路了 — я заблудился."},
        {"prompt": "Как попросить помощи у прохожего?", "option_a": "请问，可以帮我吗？", "option_b": "请问，可以吃饭吗？", "option_c": "请问，可以下雨吗？", "correct_option": "a", "explanation": "可以帮我吗？ — можете мне помочь?"},
        {"prompt": "Что значит 别着急?", "option_a": "Не спеши / не волнуйся", "option_b": "Не покупай", "option_c": "Не ешь", "correct_option": "a", "explanation": "别着急 — не спеши, не волнуйся."},
        {"prompt": "Выбери фразу для подтверждения: «Я понял».", "option_a": "我明白了。", "option_b": "我睡觉了。", "option_c": "我迟到了。", "correct_option": "a", "explanation": "我明白了 — я понял."},
        {"prompt": "Как сказать «Подождите меня»?", "option_a": "等我一下。", "option_b": "看我一下。", "option_c": "吃我一下。", "correct_option": "a", "explanation": "等我一下 — подождите меня немного."},
        {"prompt": "Что означает 没听清楚?", "option_a": "Не расслышал", "option_b": "Не купил", "option_c": "Не устал", "correct_option": "a", "explanation": "没听清楚 — не расслышал."},
        {"prompt": "Выбери фразу для просьбы показать на карте.", "option_a": "请在地图上给我看。", "option_b": "请在米饭上给我看。", "option_c": "请在水上给我看。", "correct_option": "a", "explanation": "地图 — карта; 给我看 — покажите мне."},
        {"prompt": "Как сказать «Мы вместе»?", "option_a": "我们在一起。", "option_b": "我们很贵。", "option_c": "我们不热。", "correct_option": "a", "explanation": "我们在一起 — мы вместе."},
        {"difficulty": 1, "prompt": "Как сказать «Не волнуйся»?", "option_a": "别担心。", "option_b": "别吃饭。", "option_c": "别买票。", "correct_option": "a", "explanation": "别担心 — не волнуйся."},
        {"difficulty": 1, "prompt": "Выбери спокойный ответ на 对不起.", "option_a": "没关系。", "option_b": "太贵了。", "option_c": "我饿了。", "correct_option": "a", "explanation": "На извинение часто отвечают 没关系 — ничего страшного."},
        {"difficulty": 1, "prompt": "Что сказать, если нужна вода?", "option_a": "我需要水。", "option_b": "我需要雨。", "option_c": "我需要左边。", "correct_option": "a", "explanation": "需要 — нуждаться; 水 — вода."},
        {"difficulty": 1, "prompt": "Как попросить подождать одну минуту?", "option_a": "请等一分钟。", "option_b": "请吃一分钟。", "option_c": "请买一分钟。", "correct_option": "a", "explanation": "等一分钟 — подождать одну минуту."},
        {"difficulty": 1, "prompt": "Выбери фразу «Я рядом».", "option_a": "我在附近。", "option_b": "我很便宜。", "option_c": "我不辣。", "correct_option": "a", "explanation": "附近 — рядом, поблизости."},
        {"difficulty": 1, "prompt": "Что означает 小心?", "option_a": "Осторожно", "option_b": "Дёшево", "option_c": "Сладко", "correct_option": "a", "explanation": "小心 — осторожно."},
        {"difficulty": 2, "prompt": "Как сказать «Я позвоню учителю»?", "option_a": "我给老师打电话。", "option_b": "我给老师吃米饭。", "option_c": "我给老师坐地铁。", "correct_option": "a", "explanation": "给...打电话 — звонить кому-то."},
        {"difficulty": 2, "prompt": "Выбери фразу для экстренной просьбы о помощи.", "option_a": "请马上帮我。", "option_b": "请马上买茶。", "option_c": "请马上很贵。", "correct_option": "a", "explanation": "马上 — немедленно; 帮我 — помогите мне."},
        {"difficulty": 2, "prompt": "Что сказать, если не знаешь дорогу?", "option_a": "我不知道怎么走。", "option_b": "我不知道怎么吃。", "option_c": "我不知道怎么贵。", "correct_option": "a", "explanation": "怎么走 — как идти / как пройти."},
        {"difficulty": 2, "prompt": "Как попросить написать адрес?", "option_a": "请写一下地址。", "option_b": "请喝一下地址。", "option_c": "请买一下地址。", "correct_option": "a", "explanation": "写一下地址 — напишите адрес."},
        {"difficulty": 2, "prompt": "Выбери фразу: «Пожалуйста, оставайтесь вместе».", "option_a": "请大家在一起。", "option_b": "请大家很便宜。", "option_c": "请大家吃钥匙。", "correct_option": "a", "explanation": "大家 — все; 在一起 — вместе."},
        {"difficulty": 2, "prompt": "Что означает 慢慢来?", "option_a": "Не спеши / делай постепенно", "option_b": "Покупай быстрее", "option_c": "Ешь острее", "correct_option": "a", "explanation": "慢慢来 — спокойно, не спеша."},
        {"difficulty": 2, "prompt": "Как сказать «Я уже сообщил учителю»?", "option_a": "我已经告诉老师了。", "option_b": "我已经买老师了。", "option_c": "我已经迟到老师了。", "correct_option": "a", "explanation": "告诉老师 — сообщить учителю."},
        {"difficulty": 2, "prompt": "Выбери фразу для проверки самочувствия.", "option_a": "你舒服吗？", "option_b": "你多少钱？", "option_c": "你左边吗？", "correct_option": "a", "explanation": "舒服 — комфортно, нормально по самочувствию."},
        {"difficulty": 3, "prompt": "Что значит 如果不舒服，就告诉老师?", "option_a": "Если плохо себя чувствуешь, скажи учителю", "option_b": "Если дорого, купи билет", "option_c": "Если идёт дождь, ешь рис", "correct_option": "a", "explanation": "如果...就... — если..., то...; 不舒服 — плохо себя чувствовать."},
        {"difficulty": 3, "prompt": "Как сказать «Сначала проверь паспорт, потом выходи»?", "option_a": "先检查护照，然后出去。", "option_b": "先出去护照，然后检查。", "option_c": "护照然后先出去检查。", "correct_option": "a", "explanation": "先...然后... — сначала..., затем..."},
        {"difficulty": 3, "prompt": "Выбери фразу: «Не отходи слишком далеко от группы».", "option_a": "不要离队伍太远。", "option_b": "不要吃队伍太远。", "option_c": "不要买队伍太远。", "correct_option": "a", "explanation": "离...太远 — слишком далеко от...; 队伍 — группа/команда."},
        {"difficulty": 3, "prompt": "Что означает 有问题的话，马上联系我?", "option_a": "Если есть проблема, сразу свяжись со мной", "option_b": "Если есть вода, сразу купи рис", "option_c": "Если есть билет, сразу спи", "correct_option": "a", "explanation": "有问题的话 — если есть проблема; 马上联系我 — сразу свяжись со мной."},
        {"difficulty": 3, "prompt": "Как сказать «Мы уже решили эту проблему»?", "option_a": "我们已经解决这个问题了。", "option_b": "我们已经买这个问题了。", "option_c": "我们已经喝这个问题了。", "correct_option": "a", "explanation": "解决问题 — решить проблему."},
        {"difficulty": 3, "prompt": "Выбери фразу для спокойного отчёта: «Все вернулись в общежитие».", "option_a": "大家都回宿舍了。", "option_b": "大家都买宿舍了。", "option_c": "大家都吃宿舍了。", "correct_option": "a", "explanation": "大家都...了 — все уже...; 回宿舍 — вернуться в общежитие."},
        {"difficulty": 2, "prompt": "Как сказать «Сначала успокойся, потом объясни»?", "option_a": "先冷静一下，然后解释。", "option_b": "先解释一下，然后冷静。", "option_c": "冷静然后先解释一下。", "correct_option": "a", "explanation": "先...然后... — сначала..., затем..."},
        {"difficulty": 2, "prompt": "Что означает 我来帮你处理？", "option_a": "Я помогу тебе разобраться/обработать", "option_b": "Я куплю тебе билет", "option_c": "Я пойду вместо тебя спать", "correct_option": "a", "explanation": "处理 — обработать, разобраться с делом."},
        {"difficulty": 2, "prompt": "Выбери фразу для поддержки: «Ничего, мы вместе решим». ", "option_a": "没关系，我们一起解决。", "option_b": "太贵了，我们一起吃。", "option_c": "不要辣，我们一起买。", "correct_option": "a", "explanation": "一起解决 — решить вместе."},
        {"difficulty": 2, "prompt": "Как попросить не отходить от группы?", "option_a": "请不要离开队伍。", "option_b": "请不要吃队伍。", "option_c": "请不要买队伍。", "correct_option": "a", "explanation": "离开队伍 — отходить/покидать группу."},
        {"difficulty": 2, "prompt": "Что значит 有问题马上说？", "option_a": "Если есть проблема, сразу скажи", "option_b": "Если есть деньги, сразу купи", "option_c": "Если есть дождь, сразу беги", "correct_option": "a", "explanation": "马上说 — сразу сказать."},
        {"difficulty": 2, "prompt": "Выбери фразу: «Я не расслышал, повторите пожалуйста». ", "option_a": "我没听清楚，请再说一遍。", "option_b": "我没买清楚，请再吃一遍。", "option_c": "我没走清楚，请再贵一遍。", "correct_option": "a", "explanation": "没听清楚 — не расслышал; 再说一遍 — повторите."},
        {"difficulty": 2, "prompt": "Как сказать «Подождите, я проверю список»?", "option_a": "等一下，我检查名单。", "option_b": "等一下，我吃名单。", "option_c": "等一下，我买地图。", "correct_option": "a", "explanation": "检查名单 — проверить список."},
        {"difficulty": 2, "prompt": "Что означает 大家不要着急？", "option_a": "Всем не нужно волноваться/спешить", "option_b": "Всем нужно купить воду", "option_c": "Всем нельзя пить чай", "correct_option": "a", "explanation": "不要着急 — не волнуйтесь, не спешите."},
        {"difficulty": 3, "prompt": "Выбери перевод: 如果有人不舒服，请马上告诉老师。", "option_a": "Если кому-то плохо, сразу скажите учителю", "option_b": "Если кому-то дорого, купите билет", "option_c": "Если кто-то заблудился, молчите", "correct_option": "a", "explanation": "不舒服 — плохо себя чувствовать; 告诉老师 — сказать учителю."},
        {"difficulty": 3, "prompt": "Как сказать «Мы уже связались с ответственным»?", "option_a": "我们已经联系负责人了。", "option_b": "我们已经买负责人了。", "option_c": "我们已经吃负责人了。", "correct_option": "a", "explanation": "联系负责人 — связаться с ответственным."},
        {"difficulty": 3, "prompt": "Что значит 先确认安全，再继续行动？", "option_a": "Сначала убедиться в безопасности, потом продолжать", "option_b": "Сначала купить билет, потом отдыхать", "option_c": "Сначала спорить, потом звонить", "correct_option": "a", "explanation": "确认安全 — подтвердить безопасность; 继续行动 — продолжать действовать."},
        {"difficulty": 3, "prompt": "Фраза 虽然出了问题，但是已经解决了 означает:", "option_a": "Хотя возникла проблема, её уже решили", "option_b": "Потому что проблема дорогая, её купили", "option_c": "Хотя нет воды, все ушли", "correct_option": "a", "explanation": "出了问题 — возникла проблема; 已经解决了 — уже решено."},
        {"difficulty": 3, "prompt": "Выбери фразу для отчёта: «Все в безопасности, никто не потерялся». ", "option_a": "大家都安全，没有人迷路。", "option_b": "大家都很贵，没有人吃饭。", "option_c": "大家都迟到，没有人买票。", "correct_option": "a", "explanation": "没有人迷路 — никто не заблудился."},
        {"difficulty": 3, "prompt": "Что означает 请把情况说清楚一点？", "option_a": "Пожалуйста, объясните ситуацию немного яснее", "option_b": "Пожалуйста, купите немного дешевле", "option_c": "Пожалуйста, идите немного быстрее", "correct_option": "a", "explanation": "说清楚一点 — объяснить яснее."},
        {"difficulty": 3, "prompt": "Как сказать «Если не знаешь, не действуй один»?", "option_a": "如果不知道，不要一个人行动。", "option_b": "如果不买，不要一个人吃饭。", "option_c": "如果不热，不要一个人睡觉。", "correct_option": "a", "explanation": "一个人行动 — действовать одному."},
        {"difficulty": 3, "prompt": "Выбери смысл: 为了安全，我们先回宿舍。", "option_a": "Ради безопасности сначала вернёмся в общежитие", "option_b": "Ради скидки купим чай", "option_c": "Ради времени откроем дверь", "correct_option": "a", "explanation": "为了安全 — ради безопасности; 回宿舍 — вернуться в общежитие."},
        {"difficulty": 3, "prompt": "Что значит 老师让我们在门口等？", "option_a": "Учитель попросил нас ждать у входа", "option_b": "Учитель попросил нас купить дверь", "option_c": "Учитель попросил нас спать в метро", "correct_option": "a", "explanation": "让我们... — велел/попросил нас...; 在门口等 — ждать у входа."},
        {"difficulty": 3, "prompt": "Как сказать «Я проверил, всё нормально»?", "option_a": "我检查过了，一切正常。", "option_b": "我买过了，一切很辣。", "option_c": "我睡过了，一切很远。", "correct_option": "a", "explanation": "检查过了 — уже проверил; 一切正常 — всё нормально."},
        {"difficulty": 3, "prompt": "Фраза 如果找不到路，就打开地图 означает:", "option_a": "Если не можешь найти дорогу, открой карту", "option_b": "Если нет воды, открой дверь", "option_c": "Если опоздал, купи билет", "correct_option": "a", "explanation": "找不到路 — не найти дорогу; 打开地图 — открыть карту."},
        {"difficulty": 3, "prompt": "Что означает 不要担心，我马上过来？", "option_a": "Не волнуйся, я сейчас подойду", "option_b": "Не покупай, я сейчас поем", "option_c": "Не спи, я завтра приду", "correct_option": "a", "explanation": "马上过来 — сейчас подойду/приду."},
    ],
}

# Chinese-language learning pool — educational, not lore. action_type='duel'.
DUEL_QUESTION_SEEDS = [
    {"prompt": "Как по-китайски «спасибо»?", "option_a": "谢谢 xièxie", "option_b": "对不起 duìbuqǐ", "option_c": "再见 zàijiàn", "correct_option": "a", "explanation": "谢谢 (xièxie) — спасибо."},
    {"prompt": "Что означает 你好?", "option_a": "Пока", "option_b": "Привет", "option_c": "Извините", "correct_option": "b", "explanation": "你好 (nǐ hǎo) — привет/здравствуй."},
    {"prompt": "Как сказать «до свидания»?", "option_a": "再见 zàijiàn", "option_b": "谢谢 xièxie", "option_c": "请 qǐng", "correct_option": "a", "explanation": "再见 (zàijiàn) — до свидания."},
    {"prompt": "Что значит 老师?", "option_a": "Студент", "option_b": "Учитель", "option_c": "Друг", "correct_option": "b", "explanation": "老师 (lǎoshī) — учитель."},
    {"prompt": "Как по-китайски «вода»?", "option_a": "火 huǒ", "option_b": "水 shuǐ", "option_c": "茶 chá", "correct_option": "b", "explanation": "水 (shuǐ) — вода."},
    {"prompt": "Числительное 三 означает:", "option_a": "Два", "option_b": "Три", "option_c": "Пять", "correct_option": "b", "explanation": "三 (sān) — три."},
    {"prompt": "Что значит 中国?", "option_a": "Япония", "option_b": "Китай", "option_c": "Корея", "correct_option": "b", "explanation": "中国 (Zhōngguó) — Китай."},
    {"prompt": "Как сказать «я»?", "option_a": "我 wǒ", "option_b": "你 nǐ", "option_c": "他 tā", "correct_option": "a", "explanation": "我 (wǒ) — я."},
    {"prompt": "Иероглиф 大 означает:", "option_a": "Маленький", "option_b": "Большой", "option_c": "Средний", "correct_option": "b", "explanation": "大 (dà) — большой."},
    {"prompt": "Что значит 朋友?", "option_a": "Семья", "option_b": "Друг", "option_c": "Сосед", "correct_option": "b", "explanation": "朋友 (péngyou) — друг."},
    {"prompt": "Как по-китайски «есть/кушать»?", "option_a": "喝 hē", "option_b": "吃 chī", "option_c": "看 kàn", "correct_option": "b", "explanation": "吃 (chī) — есть; 喝 (hē) — пить."},
    {"prompt": "Что означает 学生?", "option_a": "Учитель", "option_b": "Студент", "option_c": "Директор", "correct_option": "b", "explanation": "学生 (xuésheng) — студент/ученик."},
    {"prompt": "Цвет 红 — это:", "option_a": "Красный", "option_b": "Синий", "option_c": "Зелёный", "correct_option": "a", "explanation": "红 (hóng) — красный."},
    {"prompt": "Как сказать «хорошо / ок»?", "option_a": "不 bù", "option_b": "好 hǎo", "option_c": "没 méi", "correct_option": "b", "explanation": "好 (hǎo) — хорошо."},
]

DUEL_TARGET_QUESTION_COUNT = 1000

DUEL_VOCAB_BANK = [
    (1, "你好", "nǐ hǎo", "привет / здравствуйте", "приветствие"),
    (1, "谢谢", "xièxie", "спасибо", "вежливость"),
    (1, "对不起", "duìbuqǐ", "извините", "вежливость"),
    (1, "没关系", "méi guānxi", "ничего страшного", "вежливость"),
    (1, "再见", "zàijiàn", "до свидания", "вежливость"),
    (1, "请", "qǐng", "пожалуйста", "вежливость"),
    (1, "是", "shì", "быть / являться", "базовый глагол"),
    (1, "不", "bù", "не", "отрицание"),
    (1, "有", "yǒu", "иметь / есть", "наличие"),
    (1, "没有", "méiyǒu", "не иметь / нет", "отрицание"),
    (1, "我", "wǒ", "я", "местоимение"),
    (1, "你", "nǐ", "ты / вы", "местоимение"),
    (1, "他", "tā", "он", "местоимение"),
    (1, "她", "tā", "она", "местоимение"),
    (1, "我们", "wǒmen", "мы", "местоимение"),
    (1, "老师", "lǎoshī", "учитель", "люди"),
    (1, "学生", "xuésheng", "ученик / студент", "люди"),
    (1, "同学", "tóngxué", "одноклассник / сокурсник", "люди"),
    (1, "朋友", "péngyou", "друг", "люди"),
    (1, "水", "shuǐ", "вода", "еда и напитки"),
    (1, "茶", "chá", "чай", "еда и напитки"),
    (1, "米饭", "mǐfàn", "рис", "еда и напитки"),
    (1, "面条", "miàntiáo", "лапша", "еда и напитки"),
    (1, "今天", "jīntiān", "сегодня", "время"),
    (1, "明天", "míngtiān", "завтра", "время"),
    (1, "昨天", "zuótiān", "вчера", "время"),
    (1, "现在", "xiànzài", "сейчас", "время"),
    (1, "几", "jǐ", "сколько", "вопрос"),
    (1, "三", "sān", "три", "число"),
    (1, "十", "shí", "десять", "число"),
    (1, "大", "dà", "большой", "качество"),
    (1, "小", "xiǎo", "маленький", "качество"),
    (1, "热", "rè", "жарко / горячий", "качество"),
    (1, "冷", "lěng", "холодно / холодный", "качество"),
    (1, "好", "hǎo", "хороший / хорошо", "качество"),
    (1, "忙", "máng", "занятой", "качество"),
    (1, "家", "jiā", "дом / семья", "место"),
    (1, "学校", "xuéxiào", "школа", "место"),
    (1, "宿舍", "sùshè", "общежитие", "место"),
    (1, "门", "mén", "дверь / ворота", "место"),
    (1, "车", "chē", "машина / транспорт", "транспорт"),
    (1, "书", "shū", "книга", "предмет"),
    (1, "手机", "shǒujī", "мобильный телефон", "предмет"),
    (1, "钱", "qián", "деньги", "предмет"),
    (1, "中国", "Zhōngguó", "Китай", "место"),
    (1, "北京", "Běijīng", "Пекин", "место"),
    (2, "买", "mǎi", "покупать", "глагол"),
    (2, "卖", "mài", "продавать", "глагол"),
    (2, "去", "qù", "идти / ехать", "глагол"),
    (2, "来", "lái", "приходить", "глагол"),
    (2, "回", "huí", "возвращаться", "глагол"),
    (2, "坐", "zuò", "ехать на транспорте / сидеть", "глагол"),
    (2, "走", "zǒu", "идти пешком", "глагол"),
    (2, "看", "kàn", "смотреть / читать", "глагол"),
    (2, "听", "tīng", "слушать", "глагол"),
    (2, "说", "shuō", "говорить", "глагол"),
    (2, "写", "xiě", "писать", "глагол"),
    (2, "读", "dú", "читать вслух / учиться", "глагол"),
    (2, "学习", "xuéxí", "учиться", "глагол"),
    (2, "知道", "zhīdào", "знать", "глагол"),
    (2, "觉得", "juéde", "считать / чувствовать", "глагол"),
    (2, "喜欢", "xǐhuan", "нравиться", "глагол"),
    (2, "想", "xiǎng", "хотеть / думать", "модальный глагол"),
    (2, "要", "yào", "хотеть / нужно", "модальный глагол"),
    (2, "可以", "kěyǐ", "можно", "модальный глагол"),
    (2, "需要", "xūyào", "нуждаться / нужно", "модальный глагол"),
    (2, "帮助", "bāngzhù", "помощь / помогать", "глагол"),
    (2, "等", "děng", "ждать", "глагол"),
    (2, "找", "zhǎo", "искать", "глагол"),
    (2, "问", "wèn", "спрашивать", "глагол"),
    (2, "便宜", "piányi", "дешёвый", "качество"),
    (2, "贵", "guì", "дорогой", "качество"),
    (2, "快", "kuài", "быстрый", "качество"),
    (2, "慢", "màn", "медленный", "качество"),
    (2, "左边", "zuǒbian", "слева", "направление"),
    (2, "右边", "yòubian", "справа", "направление"),
    (2, "前面", "qiánmiàn", "впереди", "направление"),
    (2, "后面", "hòumiàn", "сзади", "направление"),
    (2, "地铁", "dìtiě", "метро", "транспорт"),
    (2, "公交车", "gōngjiāochē", "автобус", "транспорт"),
    (2, "出口", "chūkǒu", "выход", "место"),
    (2, "入口", "rùkǒu", "вход", "место"),
    (2, "医院", "yīyuàn", "больница", "место"),
    (2, "食堂", "shítáng", "столовая", "место"),
    (2, "图书馆", "túshūguǎn", "библиотека", "место"),
    (2, "护照", "hùzhào", "паспорт", "документ"),
    (2, "钥匙", "yàoshi", "ключ", "предмет"),
    (3, "因为", "yīnwèi", "потому что", "союз"),
    (3, "所以", "suǒyǐ", "поэтому", "союз"),
    (3, "但是", "dànshì", "но", "союз"),
    (3, "虽然", "suīrán", "хотя", "союз"),
    (3, "如果", "rúguǒ", "если", "союз"),
    (3, "然后", "ránhòu", "потом / затем", "союз"),
    (3, "已经", "yǐjīng", "уже", "время"),
    (3, "正在", "zhèngzài", "прямо сейчас делает", "аспект"),
    (3, "以后", "yǐhòu", "после / потом", "время"),
    (3, "以前", "yǐqián", "раньше / до", "время"),
    (3, "一起", "yìqǐ", "вместе", "наречие"),
    (3, "安全", "ānquán", "безопасность / безопасный", "качество"),
    (3, "问题", "wèntí", "вопрос / проблема", "существительное"),
    (3, "解决", "jiějué", "решать проблему", "глагол"),
    (3, "检查", "jiǎnchá", "проверять", "глагол"),
    (3, "确认", "quèrèn", "подтверждать", "глагол"),
    (3, "联系", "liánxì", "связаться", "глагол"),
    (3, "负责", "fùzé", "отвечать за", "глагол"),
    (3, "规则", "guīzé", "правила", "существительное"),
    (3, "迟到", "chídào", "опоздать", "глагол"),
    (3, "集合", "jíhé", "сбор / собираться", "глагол"),
    (3, "队伍", "duìwu", "команда / группа", "существительное"),
    (3, "安排", "ānpái", "распорядиться / план", "глагол"),
    (3, "情况", "qíngkuàng", "ситуация", "существительное"),
    (3, "解释", "jiěshì", "объяснять", "глагол"),
    (3, "迷路", "mílù", "заблудиться", "глагол"),
    (3, "选择", "xuǎnzé", "выбирать", "глагол"),
    (3, "比较", "bǐjiào", "сравнивать / довольно", "глагол"),
    (3, "准备", "zhǔnbèi", "готовиться", "глагол"),
    (3, "完成", "wánchéng", "завершить", "глагол"),
    (4, "影响", "yǐngxiǎng", "влиять / влияние", "абстрактное слово"),
    (4, "经验", "jīngyàn", "опыт", "абстрактное слово"),
    (4, "机会", "jīhuì", "возможность / шанс", "абстрактное слово"),
    (4, "目的", "mùdì", "цель", "абстрактное слово"),
    (4, "原因", "yuányīn", "причина", "абстрактное слово"),
    (4, "结果", "jiéguǒ", "результат", "абстрактное слово"),
    (4, "过程", "guòchéng", "процесс", "абстрактное слово"),
    (4, "发展", "fāzhǎn", "развиваться / развитие", "глагол"),
    (4, "提高", "tígāo", "повышать / улучшать", "глагол"),
    (4, "减少", "jiǎnshǎo", "уменьшать / сокращать", "глагол"),
    (4, "增加", "zēngjiā", "увеличивать / добавлять", "глагол"),
    (4, "适合", "shìhé", "подходить", "глагол"),
    (4, "复杂", "fùzá", "сложный", "качество"),
    (4, "简单", "jiǎndān", "простой", "качество"),
    (4, "重要", "zhòngyào", "важный", "качество"),
    (4, "必须", "bìxū", "обязательно / должен", "модальный глагол"),
    (4, "允许", "yǔnxǔ", "разрешать", "глагол"),
    (4, "拒绝", "jùjué", "отказываться / отказать", "глагол"),
    (4, "保护", "bǎohù", "защищать", "глагол"),
    (4, "改变", "gǎibiàn", "изменять", "глагол"),
    (4, "证明", "zhèngmíng", "доказывать / подтверждать", "глагол"),
    (4, "表示", "biǎoshì", "выражать / означать", "глагол"),
    (4, "规定", "guīdìng", "правило / устанавливать правило", "существительное"),
    (4, "讨论", "tǎolùn", "обсуждать", "глагол"),
    (4, "条件", "tiáojiàn", "условие", "абстрактное слово"),
    (4, "责任", "zérèn", "ответственность", "абстрактное слово"),
    (4, "态度", "tàidu", "отношение / позиция", "абстрактное слово"),
    (4, "顺利", "shùnlì", "гладко / успешно", "качество"),
    (4, "准确", "zhǔnquè", "точный", "качество"),
    (4, "及时", "jíshí", "своевременно", "наречие"),
]

DUEL_SENTENCE_BANK = [
    (1, "你叫什么名字？", "Как тебя зовут?", "вопросительное слово 什么"),
    (1, "我叫安娜。", "Меня зовут Анна.", "叫 для имени"),
    (1, "我是学生。", "Я ученик / студент.", "是 для роли"),
    (1, "他是老师。", "Он учитель.", "是 для роли"),
    (1, "我有手机。", "У меня есть телефон.", "有 для наличия"),
    (1, "我没有钱。", "У меня нет денег.", "没有 для отсутствия"),
    (1, "今天很热。", "Сегодня жарко.", "очень/довольно 很"),
    (1, "明天我们去学校。", "Завтра мы идём в школу.", "время перед действием"),
    (1, "我想喝水。", "Я хочу пить воду.", "想 + действие"),
    (1, "我要米饭。", "Я хочу рис.", "要 + объект"),
    (1, "请等一下。", "Пожалуйста, подождите немного.", "请 + просьба"),
    (1, "谢谢老师。", "Спасибо, учитель.", "вежливая фраза"),
    (1, "对不起，我迟到了。", "Извините, я опоздал.", "извинение + 了"),
    (1, "没关系。", "Ничего страшного.", "ответ на извинение"),
    (1, "我在宿舍。", "Я в общежитии.", "在 + место"),
    (2, "你去哪儿？", "Куда ты идёшь?", "вопросительное слово 哪儿"),
    (2, "我去食堂吃饭。", "Я иду в столовую есть.", "цель действия"),
    (2, "我们坐地铁去学校。", "Мы едем в школу на метро.", "坐 + транспорт"),
    (2, "地铁站在哪儿？", "Где станция метро?", "место + 在哪儿"),
    (2, "这个多少钱？", "Сколько это стоит?", "вопрос о цене"),
    (2, "太贵了，便宜一点。", "Слишком дорого, немного дешевле.", "太...了 и 一点"),
    (2, "我要一瓶水。", "Я хочу одну бутылку воды.", "счётное слово 瓶"),
    (2, "请再说一遍。", "Пожалуйста, повторите ещё раз.", "再 + действие"),
    (2, "我听不懂。", "Я не понимаю на слух.", "результативное 不懂"),
    (2, "慢一点说。", "Говорите медленнее.", "прилагательное + 一点"),
    (2, "我们几点集合？", "Во сколько мы собираемся?", "вопрос о времени"),
    (2, "七点半集合。", "Сбор в 7:30.", "время + 集合"),
    (2, "不要迟到。", "Не опаздывай.", "不要 + действие"),
    (2, "不要离开队伍。", "Не отходи от группы.", "запрет 不要"),
    (2, "请帮我一下。", "Пожалуйста, помогите мне.", "помощь с 一下"),
    (2, "我迷路了。", "Я заблудился.", "изменение состояния 了"),
    (2, "往右走。", "Идите направо.", "направление 往"),
    (2, "在前面的路口左转。", "На перекрёстке впереди поверните налево.", "место действия"),
    (2, "先吃饭，然后上课。", "Сначала поесть, потом занятие.", "先...然后..."),
    (2, "我昨天去了商店。", "Вчера я ходил в магазин.", "прошедшее действие с 了"),
    (2, "老师已经到了。", "Учитель уже пришёл.", "已经...了"),
    (2, "我正在写作业。", "Я сейчас пишу домашку.", "正在 + действие"),
    (2, "我们一起走吧。", "Пойдём вместе.", "一起 + действие"),
    (2, "这里人很多。", "Здесь много людей.", "существительное + 很多"),
    (2, "请保持联系。", "Пожалуйста, оставайтесь на связи.", "保持 + состояние"),
    (3, "因为下雨，所以我们坐公交车。", "Потому что идёт дождь, мы едем на автобусе.", "因为...所以..."),
    (3, "虽然很累，但是很开心。", "Хотя очень устали, но очень рады.", "虽然...但是..."),
    (3, "如果迷路了，就问老师。", "Если заблудился, спроси учителя.", "如果...就..."),
    (3, "我把手机放在宿舍了。", "Я оставил телефон в общежитии.", "конструкция 把"),
    (3, "钥匙被老师拿走了。", "Ключ был забран учителем.", "пассив 被"),
    (3, "北京比上海冷一点。", "Пекин немного холоднее Шанхая.", "сравнение 比"),
    (3, "我们越来越熟悉北京了。", "Мы всё лучше знакомимся с Пекином.", "越来越..."),
    (3, "越早出发，越不容易迟到。", "Чем раньше выйдешь, тем меньше шанс опоздать.", "越...越..."),
    (3, "一边走一边聊天。", "Идти и одновременно болтать.", "一边...一边..."),
    (3, "为了安全，请不要单独行动。", "Ради безопасности не действуйте в одиночку.", "为了..."),
    (3, "只要大家都到了，我们就出发。", "Как только все придут, мы отправимся.", "只要...就..."),
    (3, "除了老师以外，大家都在宿舍。", "Кроме учителя, все в общежитии.", "除了...以外"),
    (3, "不是我不想去，而是我没有时间。", "Не то что я не хочу идти, а у меня нет времени.", "不是...而是..."),
    (3, "即使下雨，也要按时集合。", "Даже если будет дождь, нужно собраться вовремя.", "即使...也..."),
    (3, "不但要检查护照，还要检查手机。", "Нужно проверить не только паспорт, но и телефон.", "不但...还..."),
    (3, "老师让我们在门口等。", "Учитель велел нам ждать у входа.", "让 + кто-то + действие"),
    (3, "请把情况说清楚一点。", "Пожалуйста, объясните ситуацию яснее.", "把 + объект + результат"),
    (3, "我检查过了，一切正常。", "Я уже проверил, всё нормально.", "опыт/факт 过"),
    (3, "有问题的话，马上联系我。", "Если есть проблема, сразу свяжись со мной.", "的话 для условия"),
    (3, "我们按照老师的安排行动。", "Мы действуем по распоряжению учителя.", "按照..."),
]

DUEL_ORDER_BANK = [
    (1, "Я завтра иду в школу.", "我明天去学校。", "明天学校去我。", "去我明天学校。", "Время обычно ставится перед глаголом."),
    (1, "Я хочу пить воду.", "我想喝水。", "我水想喝。", "想我水喝。", "想 + действие: хочу сделать."),
    (1, "У меня есть телефон.", "我有手机。", "手机有我。", "我手机有吗。", "有 ставится перед объектом."),
    (1, "Сегодня очень жарко.", "今天很热。", "很今天热。", "热很今天。", "Время в начале, затем качество."),
    (2, "Сколько это стоит?", "这个多少钱？", "多少这个钱？", "钱这个多少？", "多少钱 — сколько стоит."),
    (2, "Станция метро где?", "地铁站在哪儿？", "在哪儿地铁站？", "地铁在哪儿站？", "Место + 在哪儿."),
    (2, "Пожалуйста, повторите ещё раз.", "请再说一遍。", "再请一遍说。", "说请再一遍。", "请 + 再 + действие + 一遍."),
    (2, "Сначала поесть, потом идти на урок.", "先吃饭，然后上课。", "然后先上课吃饭。", "吃饭然后先上课。", "先...然后... задаёт порядок."),
    (2, "Мы едем на метро в школу.", "我们坐地铁去学校。", "我们去坐学校地铁。", "地铁我们学校坐去。", "坐 + транспорт + 去 + место."),
    (2, "Не отходи от группы.", "不要离开队伍。", "队伍不要离开。", "离开不要队伍。", "不要 + действие."),
    (3, "Потому что дождь, поэтому едем на автобусе.", "因为下雨，所以坐公交车。", "所以下雨，因为坐公交车。", "下雨因为公交车所以坐。", "因为...所以..."),
    (3, "Если заблудился, спроси учителя.", "如果迷路了，就问老师。", "就迷路了，如果问老师。", "问老师如果就迷路了。", "如果...就..."),
    (3, "Я положил телефон в общежитии.", "我把手机放在宿舍了。", "我手机把放在宿舍了。", "宿舍把我放手机了。", "把 + объект + действие/результат."),
    (3, "Пекин холоднее Шанхая.", "北京比上海冷。", "上海比北京冷吗。", "北京冷比上海。", "A 比 B + качество."),
    (3, "Чем раньше выйдем, тем лучше.", "越早出发越好。", "越出发早越好。", "早越好越出发。", "越...越..."),
    (3, "Хотя устал, но рад.", "虽然很累，但是很开心。", "但是很累，虽然很开心。", "很累虽然但是开心。", "虽然...但是..."),
    (3, "Мы действуем по правилам.", "我们按照规则行动。", "我们规则按照行动。", "行动我们按照规则。", "按照 + правило/план."),
    (3, "Пожалуйста, объясни ситуацию яснее.", "请把情况说清楚一点。", "请情况把说清楚一点。", "请说把情况清楚一点。", "把 + объект + результат."),
    (3, "Даже если дождь, всё равно собираемся вовремя.", "即使下雨，也要按时集合。", "也要下雨，即使按时集合。", "集合即使也要下雨。", "即使...也..."),
    (3, "Не только паспорт, но и телефон проверь.", "不但检查护照，还检查手机。", "还检查护照，不但检查手机。", "护照不但手机还检查。", "不但...还..."),
]

def _duel_seed(*parts) -> int:
    raw = "|".join(str(part) for part in parts)
    return int(hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16], 16)


def _duel_options(correct: str, wrongs: list[str], *seed_parts) -> dict:
    cleaned = []
    for value in [correct] + list(wrongs):
        value = str(value).strip()
        if value and value not in cleaned:
            cleaned.append(value)
    fallback = ["Нет такого значения", "Неверный порядок", "Другая грамматика", "Не подходит по смыслу"]
    for value in fallback:
        if len(cleaned) >= 3:
            break
        if value != correct and value not in cleaned:
            cleaned.append(value)
    entries = cleaned[:3]
    rng = random.Random(_duel_seed(*seed_parts))
    rng.shuffle(entries)
    correct_option = ("a", "b", "c")[entries.index(correct)]
    return {
        "option_a": entries[0],
        "option_b": entries[1],
        "option_c": entries[2],
        "correct_option": correct_option,
    }


def _duel_question(difficulty: int, prompt: str, correct: str, wrongs: list[str], explanation: str, *seed_parts) -> dict:
    options = _duel_options(correct, wrongs, prompt, *seed_parts)
    return {
        "difficulty": int(difficulty),
        "prompt": prompt,
        **options,
        "explanation": explanation,
    }


def _duel_pick(bank, key_index: int, correct: str, difficulty: int, *seed_parts) -> list[str]:
    same_level = [row[key_index] for row in bank if row[key_index] != correct and row[0] == difficulty]
    other_level = [row[key_index] for row in bank if row[key_index] != correct and row[key_index] not in same_level]
    values = same_level + other_level
    rng = random.Random(_duel_seed("pick", correct, difficulty, *seed_parts))
    rng.shuffle(values)
    out = []
    for value in values:
        if value not in out:
            out.append(value)
        if len(out) == 2:
            return out
    return out


def _duel_build_vocab_questions():
    questions = []
    for idx, (difficulty, hanzi, pinyin, meaning, category) in enumerate(DUEL_VOCAB_BANK):
        wrong_meanings = _duel_pick(DUEL_VOCAB_BANK, 3, meaning, difficulty, idx, "meaning")
        wrong_hanzi = _duel_pick(DUEL_VOCAB_BANK, 1, hanzi, difficulty, idx, "hanzi")
        wrong_pinyin = _duel_pick(DUEL_VOCAB_BANK, 2, pinyin, difficulty, idx, "pinyin")
        explanation = f"{hanzi} ({pinyin}) — {meaning}. Категория: {category}."
        questions.extend([
            _duel_question(difficulty, f"[L{difficulty}] Что означает {hanzi}?", meaning, wrong_meanings, explanation, idx, "vocab-meaning"),
            _duel_question(difficulty, f"[L{difficulty}] Как по-китайски «{meaning}»?", f"{hanzi} {pinyin}", [f"{x} {y}" for x, y in zip(wrong_hanzi, wrong_pinyin)], explanation, idx, "vocab-reverse"),
            _duel_question(difficulty, f"[L{difficulty}] Как читается {hanzi}?", pinyin, wrong_pinyin, explanation, idx, "vocab-pinyin"),
            _duel_question(difficulty, f"[L{difficulty}] В дуэли мелькнуло слово {hanzi}. Выбери перевод.", meaning, wrong_meanings, explanation, idx, "vocab-context"),
            _duel_question(difficulty, f"[L{difficulty}] Какой вариант относится к теме «{category}» и значит «{meaning}»?", f"{hanzi} {pinyin}", [f"{x} {y}" for x, y in zip(wrong_hanzi, wrong_pinyin)], explanation, idx, "vocab-category"),
            _duel_question(difficulty, f"[L{difficulty}] Если слышишь «{pinyin}», какой иероглиф подходит?", hanzi, wrong_hanzi, explanation, idx, "vocab-listening"),
        ])
    return questions


def _duel_build_sentence_questions():
    questions = []
    for idx, (difficulty, zh, ru, pattern) in enumerate(DUEL_SENTENCE_BANK):
        wrong_ru = _duel_pick(DUEL_SENTENCE_BANK, 2, ru, difficulty, idx, "sentence-ru")
        wrong_zh = _duel_pick(DUEL_SENTENCE_BANK, 1, zh, difficulty, idx, "sentence-zh")
        wrong_patterns = _duel_pick(DUEL_SENTENCE_BANK, 3, pattern, difficulty, idx, "sentence-pattern")
        explanation = f"{zh} — {ru} Здесь работает: {pattern}."
        questions.extend([
            _duel_question(difficulty, f"[L{difficulty}] Переведи фразу: {zh}", ru, wrong_ru, explanation, idx, "sentence-translate"),
            _duel_question(difficulty, f"[L{difficulty}] Как сказать по-китайски: «{ru}»?", zh, wrong_zh, explanation, idx, "sentence-reverse"),
            _duel_question(difficulty, f"[L{difficulty}] В бою соперник пишет: {zh} Что он имеет в виду?", ru, wrong_ru, explanation, idx, "sentence-context"),
            _duel_question(difficulty, f"[L{difficulty}] Какая грамматическая идея есть во фразе «{zh}»?", pattern, wrong_patterns, explanation, idx, "sentence-pattern"),
            _duel_question(difficulty, f"[L{difficulty}] Найди фразу со смыслом: «{ru}»", zh, wrong_zh, explanation, idx, "sentence-find"),
            _duel_question(difficulty, f"[L{difficulty}] Какое объяснение лучше подходит к «{zh}»?", f"Смысл: {ru}", [f"Смысл: {x}" for x in wrong_ru], explanation, idx, "sentence-explain"),
        ])
    return questions


def _duel_build_order_questions():
    questions = []
    for idx, (difficulty, ru, correct, wrong_a, wrong_b, explanation) in enumerate(DUEL_ORDER_BANK):
        questions.extend([
            _duel_question(difficulty, f"[L{difficulty}] Выбери правильный порядок слов: «{ru}»", correct, [wrong_a, wrong_b], explanation, idx, "order-main"),
            _duel_question(difficulty, f"[L{difficulty}] Какая фраза грамматически правильная?", correct, [wrong_a, wrong_b], explanation, idx, "order-grammar"),
            _duel_question(difficulty, f"[L{difficulty}] Собери китайскую фразу по смыслу: «{ru}»", correct, [wrong_a, wrong_b], explanation, idx, "order-meaning"),
            _duel_question(difficulty, f"[L{difficulty}] Какой вариант НЕ ломает порядок слов для смысла «{ru}»?", correct, [wrong_a, wrong_b], explanation, idx, "order-safe"),
        ])
    return questions


def _duel_generated_questions(existing_questions: list[dict]) -> list[dict]:
    target_extra = max(0, DUEL_TARGET_QUESTION_COUNT - len(existing_questions))
    seen = {q["prompt"] for q in existing_questions}
    generated = []
    candidates = (
        _duel_build_vocab_questions()
        + _duel_build_sentence_questions()
        + _duel_build_order_questions()
    )
    for question in candidates:
        if question["prompt"] in seen:
            continue
        seen.add(question["prompt"])
        generated.append(question)
        if len(generated) >= target_extra:
            break
    return generated


DUEL_QUESTION_SEEDS.extend(_duel_generated_questions(DUEL_QUESTION_SEEDS))


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
    # wal_autocheckpoint=0: with a nonzero threshold, commit() runs an
    # in-line PASSIVE checkpoint once the WAL crosses the page count, which
    # on this VPS's disk has been observed to block for ~48s and stack the
    # entire DB_WRITE_LOCK queue behind it. WAL size is instead managed by
    # the out-of-band wal_checkpoint_loop, which skips while the write lock
    # is held (hard rule, 2026-06-09 / 2026-06-15).
    conn.execute("PRAGMA wal_autocheckpoint=0")
    ms = (time.time() - t0) * 1000
    if ms > 50:
        print("ZHIDAO_SLOW_CONN %.0fms" % ms, flush=True)
    return conn


def normalize_cohort_code(value: Optional[str], default: str = COHORT_BEIJING) -> str:
    code = str(value or "").strip().lower()
    return code if code in COHORT_CODES else default


def cohort_setting_key(key: str, cohort_code: str) -> str:
    return f"{normalize_cohort_code(cohort_code)}:{key}"


def get_cohort_setting(c, key: str, cohort_code: str, default: Optional[str] = None):
    cohort_code = normalize_cohort_code(cohort_code)
    c.execute("SELECT value FROM settings WHERE key=?", (cohort_setting_key(key, cohort_code),))
    row = c.fetchone()
    if row:
        return row[0]
    if cohort_code == COHORT_BEIJING:
        c.execute("SELECT value FROM settings WHERE key=?", (key,))
        legacy = c.fetchone()
        if legacy:
            return legacy[0]
    return default


def set_cohort_setting(c, key: str, value, cohort_code: str):
    c.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (cohort_setting_key(key, cohort_code), str(value)),
    )


def get_user_cohort(c, telegram_id: Optional[int]) -> str:
    if telegram_id in MJU_MEMBER_IDS or telegram_id in MJU_ADMIN_IDS:
        return COHORT_MJU
    if not telegram_id:
        return COHORT_BEIJING
    c.execute("SELECT cohort_code FROM users WHERE telegram_id=?", (int(telegram_id),))
    row = c.fetchone()
    return normalize_cohort_code(row[0] if row else None)


def resolve_viewer_cohort(
    c,
    viewer_id: Optional[int],
    requested_cohort: Optional[str] = None,
) -> str:
    if viewer_id in MJU_ADMIN_IDS:
        return COHORT_MJU
    if viewer_id in GLOBAL_ADMIN_IDS:
        return normalize_cohort_code(requested_cohort)
    return get_user_cohort(c, viewer_id)


def require_target_cohort(
    c,
    viewer_id: Optional[int],
    target_id: Optional[int],
    requested_cohort: Optional[str] = None,
) -> str:
    viewer_cohort = resolve_viewer_cohort(c, viewer_id, requested_cohort)
    target_cohort = get_user_cohort(c, target_id)
    if target_cohort != viewer_cohort:
        raise HTTPException(status_code=403, detail="Пользователь находится в другом контуре")
    return viewer_cohort


def require_same_user_cohort(c, first_id: Optional[int], second_id: Optional[int]) -> str:
    first_cohort = get_user_cohort(c, first_id)
    second_cohort = get_user_cohort(c, second_id)
    if first_cohort != second_cohort:
        raise HTTPException(status_code=403, detail="Межконтурное взаимодействие запрещено")
    return first_cohort


def get_request_actor_id(
    x_telegram_id: Optional[int] = None,
    x_admin_id: Optional[int] = None,
) -> Optional[int]:
    return x_admin_id if x_admin_id in ADMIN_IDS else x_telegram_id


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

# Отдельный пул для ЧТЕНИЙ. В WAL-режиме SQLite допускает много читателей
# одновременно с единственным писателем, поэтому чтения:
#   1) НЕ берут DB_WRITE_LOCK (не встают в очередь записи);
#   2) уходят с event loop в этот пул (несколько воркеров) — раньше горячие
#      GET-эндпоинты (рейтинг, дуэль-state, контракты, ачивки) выполняли
#      синхронный SQLite прямо в event loop и на своё время морозили ВЕСЬ
#      сервер. Теперь loop свободен, а чтения идут конкурентно.
# Каждый воркер получает своё thread-local read-соединение через get_conn().
DB_READ_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="zhidao-db-reader",
)


async def db_read(fn, label=None):
    """Выполнить читающую функцию в read-пуле без write-lock.

    Использовать ТОЛЬКО для чистого чтения (никаких INSERT/UPDATE/DELETE/commit).
    Записи по-прежнему идут через db_write (единый писатель)."""
    t0 = time.time()
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(DB_READ_EXECUTOR, fn)
    exec_ms = (time.time() - t0) * 1000
    if exec_ms > 200:
        print("ZHIDAO_DB_READ fn=%s exec=%.0fms" % (label or getattr(fn, "__name__", "?"), exec_ms), flush=True)
    return result


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
                  study_group TEXT DEFAULT NULL,
                  cohort_code TEXT NOT NULL DEFAULT 'beijing',
                  points INTEGER DEFAULT 0,
                  rep_score INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS schedule
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  day TEXT, time TEXT, subject TEXT, location TEXT,
                  cohort_code TEXT NOT NULL DEFAULT 'beijing')''')
    c.execute('''CREATE TABLE IF NOT EXISTS announcements
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  text TEXT,
                  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                  cohort_code TEXT NOT NULL DEFAULT 'beijing')''')
    c.execute('''CREATE TABLE IF NOT EXISTS announcement_reactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  announcement_id INTEGER,
                  telegram_id INTEGER,
                  emoji TEXT,
                  UNIQUE(announcement_id, telegram_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS community_shop_proposals
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  telegram_id INTEGER NOT NULL,
                  title TEXT NOT NULL,
                  description TEXT NOT NULL,
                  status TEXT NOT NULL DEFAULT 'pending',
                  created_at TEXT NOT NULL,
                  moderated_by INTEGER DEFAULT NULL,
                  moderated_at TEXT DEFAULT NULL,
                  moderation_note TEXT DEFAULT NULL,
                  cohort_code TEXT NOT NULL DEFAULT 'beijing')''')
    c.execute('''CREATE TABLE IF NOT EXISTS community_shop_reactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  proposal_id INTEGER NOT NULL,
                  telegram_id INTEGER NOT NULL,
                  emoji TEXT NOT NULL,
                  UNIQUE(proposal_id, telegram_id))''')
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
                  cohort_code TEXT NOT NULL DEFAULT 'beijing',
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
                  fate_guard INTEGER DEFAULT 0,
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
                  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                  cohort_code TEXT NOT NULL DEFAULT 'beijing')''')
    c.execute('''CREATE TABLE IF NOT EXISTS raid_participants
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  raid_id INTEGER, telegram_id INTEGER,
                  UNIQUE(raid_id, telegram_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS laundry_schedule
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  day TEXT, time TEXT, note TEXT,
                  capacity INTEGER DEFAULT 1,
                  taken_by INTEGER DEFAULT NULL,
                  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                  cohort_code TEXT NOT NULL DEFAULT 'beijing')''')
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
                  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                  cohort_code TEXT NOT NULL DEFAULT 'beijing')''')
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
                  min_players INTEGER NOT NULL DEFAULT 5,
                  max_players INTEGER NOT NULL DEFAULT 15,
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
                  created_at TEXT NOT NULL,
                  cohort_code TEXT NOT NULL DEFAULT 'beijing')''')
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
    c.execute('''CREATE TABLE IF NOT EXISTS event_question_draws
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  event_id INTEGER NOT NULL,
                  action_type TEXT NOT NULL,
                  question_id INTEGER NOT NULL,
                  cycle INTEGER NOT NULL DEFAULT 1,
                  telegram_id INTEGER DEFAULT NULL,
                  created_at TEXT NOT NULL,
                  UNIQUE(event_id, action_type, question_id, cycle))''')
    c.execute('''CREATE TABLE IF NOT EXISTS trip_quiz_questions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  prompt TEXT NOT NULL,
                  option_a TEXT NOT NULL,
                  option_b TEXT NOT NULL,
                  option_c TEXT NOT NULL,
                  correct_option TEXT NOT NULL,
                  explanation TEXT DEFAULT NULL,
                  created_by INTEGER DEFAULT NULL,
                  created_at TEXT NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS trip_quiz_attempts
                 (telegram_id INTEGER PRIMARY KEY,
                  score INTEGER NOT NULL,
                  total INTEGER NOT NULL,
                  passed INTEGER NOT NULL,
                  completed_at TEXT NOT NULL)''')
    # PvP duels (Tekken-style live quiz battle). Async challenge -> accept ->
    # ready-check -> live rounds. Zero-sum stake. See CLAUDE.md PvP spec.
    c.execute('''CREATE TABLE IF NOT EXISTS duels
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  challenger_id INTEGER NOT NULL,
                  opponent_id INTEGER NOT NULL,
                  stake INTEGER NOT NULL,
                  status TEXT NOT NULL DEFAULT 'pending',
                  challenger_hp INTEGER NOT NULL DEFAULT 100,
                  opponent_hp INTEGER NOT NULL DEFAULT 100,
                  challenger_ready INTEGER NOT NULL DEFAULT 0,
                  opponent_ready INTEGER NOT NULL DEFAULT 0,
                  round_no INTEGER NOT NULL DEFAULT 0,
                  current_question_id INTEGER DEFAULT NULL,
                  round_started_at TEXT DEFAULT NULL,
                  challenger_answer TEXT DEFAULT NULL,
                  opponent_answer TEXT DEFAULT NULL,
                  challenger_answer_at TEXT DEFAULT NULL,
                  opponent_answer_at TEXT DEFAULT NULL,
                  winner_id INTEGER DEFAULT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT DEFAULT NULL,
                  accepted_at TEXT DEFAULT NULL,
                  finished_at TEXT DEFAULT NULL)''')
    c.execute("CREATE INDEX IF NOT EXISTS idx_duels_opponent ON duels(opponent_id, status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_duels_challenger ON duels(challenger_id, status)")
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
    if 'study_group' not in user_columns:
        c.execute("ALTER TABLE users ADD COLUMN study_group TEXT DEFAULT NULL")
    if 'rep_score' not in user_columns:
        c.execute("ALTER TABLE users ADD COLUMN rep_score INTEGER DEFAULT 0")
    if 'cohort_code' not in user_columns:
        c.execute("ALTER TABLE users ADD COLUMN cohort_code TEXT NOT NULL DEFAULT 'beijing'")
    c.execute("UPDATE users SET cohort_code='beijing'")
    mju_placeholders = ",".join("?" for _ in MJU_MEMBER_IDS)
    c.execute(
        f"UPDATE users SET cohort_code='mju' WHERE telegram_id IN ({mju_placeholders})",
        sorted(MJU_MEMBER_IDS),
    )

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
    if 'fate_guard' not in columns:
        c.execute("ALTER TABLE user_status ADD COLUMN fate_guard INTEGER DEFAULT 0")
    if 'equipped_frame' not in columns:
        c.execute("ALTER TABLE user_status ADD COLUMN equipped_frame TEXT DEFAULT NULL")
    if 'title_style' not in columns:
        c.execute("ALTER TABLE user_status ADD COLUMN title_style TEXT DEFAULT NULL")
    if 'wildai_defender' not in columns:
        c.execute("ALTER TABLE user_status ADD COLUMN wildai_defender INTEGER DEFAULT 0")
    if 'wildai_mvp' not in columns:
        c.execute("ALTER TABLE user_status ADD COLUMN wildai_mvp INTEGER DEFAULT 0")
    if 'architect_winner' not in columns:
        c.execute("ALTER TABLE user_status ADD COLUMN architect_winner INTEGER DEFAULT 0")
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
    if 'assignee' not in laundry_schedule_columns:
        c.execute("ALTER TABLE laundry_schedule ADD COLUMN assignee TEXT DEFAULT ''")
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
    if 'assignee' not in water_schedule_columns:
        c.execute("ALTER TABLE water_schedule ADD COLUMN assignee TEXT DEFAULT ''")
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
            c.execute("ALTER TABLE events ADD COLUMN min_players INTEGER NOT NULL DEFAULT 5")
        if 'max_players' not in event_columns:
            c.execute("ALTER TABLE events ADD COLUMN max_players INTEGER NOT NULL DEFAULT 15")
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
    if 'expires_at' not in contract_columns:
        c.execute("ALTER TABLE contracts ADD COLUMN expires_at TEXT DEFAULT NULL")
    if 'submitted_at' not in contract_columns:
        c.execute("ALTER TABLE contracts ADD COLUMN submitted_at TEXT DEFAULT NULL")
    if 'auto_confirm_at' not in contract_columns:
        c.execute("ALTER TABLE contracts ADD COLUMN auto_confirm_at TEXT DEFAULT NULL")
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

    c.execute('''CREATE TABLE IF NOT EXISTS architect_diary_unlocks
                 (telegram_id INTEGER NOT NULL,
                  entry_code TEXT NOT NULL,
                  unlocked_at TEXT NOT NULL,
                  PRIMARY KEY (telegram_id, entry_code))''')

    c.execute('''CREATE TABLE IF NOT EXISTS gift_codes
                 (code TEXT PRIMARY KEY,
                  reward_stars INTEGER NOT NULL,
                  max_uses INTEGER NOT NULL DEFAULT 1,
                  used_count INTEGER NOT NULL DEFAULT 0,
                  expires_at TEXT DEFAULT NULL,
                  created_at TEXT NOT NULL,
                  note TEXT DEFAULT NULL,
                  show_at TEXT DEFAULT NULL)''')
    try:
        c.execute("ALTER TABLE gift_codes ADD COLUMN show_at TEXT DEFAULT NULL")
    except Exception:
        pass

    c.execute('''CREATE TABLE IF NOT EXISTS gift_code_redemptions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  telegram_id INTEGER NOT NULL,
                  code TEXT NOT NULL,
                  redeemed_at TEXT NOT NULL,
                  UNIQUE(telegram_id, code))''')

    c.execute('''CREATE TABLE IF NOT EXISTS tianhao_facts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  text TEXT NOT NULL,
                  show_at TEXT NOT NULL,
                  created_at TEXT NOT NULL)''')

    cohort_tables = (
        "schedule", "announcements", "community_shop_proposals", "laundry",
        "raids", "laundry_schedule", "water_schedule", "events",
        "daily_checks", "admin_action_logs", "contracts", "gift_codes",
        "global_alerts",
    )
    for table_name in cohort_tables:
        c.execute(f"PRAGMA table_info({table_name})")
        table_columns = {row[1] for row in c.fetchall()}
        if table_columns and "cohort_code" not in table_columns:
            c.execute(
                f"ALTER TABLE {table_name} "
                "ADD COLUMN cohort_code TEXT NOT NULL DEFAULT 'beijing'"
            )

    # The legacy laundry table had a global UNIQUE(date, time), which would
    # still make identical Beijing/MJU slots conflict. Rebuild it once with the
    # cohort included in the unique key.
    c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='laundry'")
    laundry_sql_row = c.fetchone()
    normalized_laundry_sql = re.sub(r"\s+", "", (laundry_sql_row[0] if laundry_sql_row else "")).upper()
    if "UNIQUE(DATE,TIME)" in normalized_laundry_sql:
        c.execute('''CREATE TABLE laundry_cohort_new
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      date TEXT,
                      time TEXT,
                      telegram_id INTEGER,
                      username TEXT,
                      cohort_code TEXT NOT NULL DEFAULT 'beijing',
                      UNIQUE(date, time, cohort_code))''')
        c.execute('''INSERT INTO laundry_cohort_new
                     (id, date, time, telegram_id, username, cohort_code)
                     SELECT id, date, time, telegram_id, username,
                            COALESCE(NULLIF(cohort_code, ''), 'beijing')
                     FROM laundry''')
        c.execute("DROP TABLE laundry")
        c.execute("ALTER TABLE laundry_cohort_new RENAME TO laundry")

    for setting_key in (
        "blackwall", "architect_event", "wildai_event", "mju_event",
        "breach_until", "breach_seed",
    ):
        c.execute(
            "INSERT OR IGNORE INTO settings (key, value) "
            "SELECT ?, value FROM settings WHERE key=?",
            (cohort_setting_key(setting_key, COHORT_BEIJING), setting_key),
        )
        c.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (
                cohort_setting_key(setting_key, COHORT_MJU),
                "" if setting_key in {"breach_until", "breach_seed"} else "0",
            ),
        )

    c.execute('''CREATE TABLE IF NOT EXISTS shop_daily_counts_cohort
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  item_code TEXT NOT NULL,
                  date TEXT NOT NULL,
                  cohort_code TEXT NOT NULL DEFAULT 'beijing',
                  count INTEGER DEFAULT 0,
                  UNIQUE(item_code, date, cohort_code))''')
    c.execute('''INSERT OR IGNORE INTO shop_daily_counts_cohort
                 (item_code, date, cohort_code, count)
                 SELECT item_code, date, 'beijing', count
                 FROM shop_daily_counts''')

    c.execute("CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_users_cohort ON users(cohort_code, telegram_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_events_cohort ON events(cohort_code, state, code)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_raids_cohort ON raids(cohort_code, date, status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_daily_checks_cohort ON daily_checks(cohort_code, check_type, check_date)")
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
    c.execute("CREATE INDEX IF NOT EXISTS idx_event_question_draws_eac ON event_question_draws(event_id, action_type, cycle)")

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
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('mju_event', '0')")
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
    # Seed raid questions idempotently. Production already has the original
    # short pool, so count==0 would not add newly approved questions.
    created_at = datetime.utcnow().isoformat()
    for q in RAID_QUESTION_SEEDS:
        c.execute(
            '''SELECT 1 FROM event_questions
               WHERE event_code='raid' AND action_type='scan' AND prompt=?
               LIMIT 1''',
            (q["prompt"],),
        )
        if c.fetchone():
            continue
        c.execute(
            '''INSERT INTO event_questions
               (event_code, action_type, difficulty, prompt, option_a, option_b, option_c, correct_option, explanation, created_at)
               VALUES (?, 'scan', ?, ?, ?, ?, ?, ?, ?, ?)''',
            ('raid', int(q.get("difficulty") or 1), q["prompt"], q["option_a"], q["option_b"], q["option_c"],
             q["correct_option"], q.get("explanation"), created_at),
        )
    # Architect questions are seeded idempotently by prompt. The production DB
    # already has the old seed rows, so a count==0 gate would never add new
    # questions after expanding ARCHITECT_QUESTION_SEEDS.
    created_at = datetime.utcnow().isoformat()
    for action_type, questions in ARCHITECT_QUESTION_SEEDS.items():
        for question in questions:
            c.execute(
                '''SELECT 1 FROM event_questions
                   WHERE event_code='architect' AND action_type=? AND prompt=?
                   LIMIT 1''',
                (action_type, question["prompt"]),
            )
            if c.fetchone():
                continue
            c.execute(
                '''INSERT INTO event_questions
                   (event_code, action_type, difficulty, prompt, option_a, option_b, option_c, correct_option, explanation, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    'architect',
                    action_type,
                    int(question.get("difficulty") or 1),
                    question["prompt"],
                    question["option_a"],
                    question["option_b"],
                    question["option_c"],
                    question["correct_option"],
                    question.get("explanation"),
                    created_at,
                ),
            )

    created_at = datetime.utcnow().isoformat()
    for action_type, questions in WILD_AI_BREACH_QUESTION_SEEDS.items():
        for question in questions:
            c.execute(
                '''SELECT 1 FROM event_questions
                   WHERE event_code='wildai_breach' AND action_type=? AND prompt=?''',
                (action_type, question["prompt"]),
            )
            if c.fetchone():
                continue
            c.execute(
                '''INSERT INTO event_questions
                   (event_code, action_type, difficulty, prompt, option_a, option_b, option_c, correct_option, explanation, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    'wildai_breach',
                    action_type,
                    int(question.get("difficulty") or 1),
                    question["prompt"],
                    question["option_a"],
                    question["option_b"],
                    question["option_c"],
                    question["correct_option"],
                    question.get("explanation"),
                    created_at,
                ),
            )

    created_at = datetime.utcnow().isoformat()
    for action_type, questions in MJU_QUESTION_SEEDS.items():
        for question in questions:
            c.execute(
                '''SELECT 1 FROM event_questions
                   WHERE event_code=? AND action_type=? AND prompt=?
                   LIMIT 1''',
                (MJU_EVENT_CODE, action_type, question["prompt"]),
            )
            if c.fetchone():
                continue
            c.execute(
                '''INSERT INTO event_questions
                   (event_code, action_type, difficulty, prompt, option_a, option_b, option_c, correct_option, explanation, created_at)
                   VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    MJU_EVENT_CODE,
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

    # Duel question pool (Chinese-language, action_type='duel'). Educational,
    # not lore — keeps PvP duels about language learning, not random chance.
    created_at = datetime.utcnow().isoformat()
    for question in DUEL_QUESTION_SEEDS:
        c.execute(
            '''SELECT 1 FROM event_questions
               WHERE event_code='duel' AND action_type='duel' AND prompt=?
               LIMIT 1''',
            (question["prompt"],),
        )
        if c.fetchone():
            continue
        c.execute(
            '''INSERT INTO event_questions
               (event_code, action_type, difficulty, prompt, option_a, option_b, option_c, correct_option, explanation, created_at)
               VALUES ('duel', 'duel', ?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                int(question.get("difficulty") or 1),
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


def create_global_alert(alert_type: str, title: str, message: str, cohort_code: str):
    conn = get_conn()
    c = conn.cursor()
    cohort_code = normalize_cohort_code(cohort_code)
    c.execute(
        "UPDATE global_alerts SET is_active = 0 WHERE is_active = 1 AND cohort_code=?",
        (cohort_code,),
    )
    c.execute(
        "INSERT INTO global_alerts (alert_type, title, message, created_at, is_active, cohort_code) VALUES (?, ?, ?, ?, 1, ?)",
        (alert_type, title, message, datetime.utcnow().isoformat(), cohort_code),
    )
    alert_id = c.lastrowid
    conn.commit()
    conn.close()
    return alert_id


def get_current_global_alert(cohort_code: str):
    conn = get_conn()
    c = conn.cursor()
    cohort_code = normalize_cohort_code(cohort_code)
    c.execute(
        '''SELECT id, alert_type, title, message, created_at, is_active
           FROM global_alerts
           WHERE is_active = 1 AND cohort_code=?
           ORDER BY id DESC
           LIMIT 1''',
        (cohort_code,),
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
                # PASSIVE only — RESTART/TRUNCATE compete with writers and were
                # observed taking 49-72s on production (hard rule, 2026-06-09).
                row = conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
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


def latest_manual_presence_session(c, cohort_code: str) -> Optional[str]:
    today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
    c.execute(
        '''SELECT check_date
           FROM daily_checks
           WHERE check_type='manual' AND check_date LIKE ? AND cohort_code=?
           ORDER BY check_date DESC
           LIMIT 1''',
        (f"{today}__%", normalize_cohort_code(cohort_code)),
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
    cohort_code = get_user_cohort(c, telegram_id)
    c.execute(
        '''INSERT INTO daily_checks
           (check_type, check_date, telegram_id, status, note, created_at, updated_at, cohort_code)
           VALUES (?, ?, ?, 'pending', ?, ?, ?, ?)
           ON CONFLICT(check_type, check_date, telegram_id) DO NOTHING''',
        (check_type, check_date, telegram_id, note, now, now, cohort_code),
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
            ]]
        }
    if check_type == "manual":
        session = check_date or normalize_presence_date()
        return {
            "inline_keyboard": [[
                {"text": "✅ Я на месте", "callback_data": f"presence:manual:{session}:confirm"},
            ]]
        }

    return {
        "inline_keyboard": [
            [{"text": "✅ Я в комнате", "callback_data": "presence:evening:confirm"}],
            [
                {"text": "🕐 Свободное время", "callback_data": "presence:evening:free_time"},
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
        f"Попытка {attempt_no}/3. 20:00 — нужно быть в комнате.\n"
        "Если у тебя разрешение от админа или активное «Свободное время», выбери нужную кнопку."
    )


_TELEGRAM_SESSION: Optional[aiohttp.ClientSession] = None


async def _get_telegram_session() -> aiohttp.ClientSession:
    # Один переиспользуемый HTTP-клиент на весь процесс. Раньше каждый вызов
    # send_telegram_message открывал новую aiohttp.ClientSession (новое TCP+TLS
    # соединение к api.telegram.org) — при массовой рассылке по циклу это давало
    # ~200мс накладных расходов НА КАЖДОЕ сообщение. При ~90 юзерах отсюда и
    # росла заметная задержка публикации новостей (2026-07-02).
    global _TELEGRAM_SESSION
    if _TELEGRAM_SESSION is None or _TELEGRAM_SESSION.closed:
        _TELEGRAM_SESSION = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=30, keepalive_timeout=60)
        )
    return _TELEGRAM_SESSION


async def send_telegram_message(chat_id: int, text: str, reply_markup: Optional[dict] = None):
    if not BOT_TOKEN:
        return False, {"detail": "BOT_TOKEN is not configured"}

    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup

    session = await _get_telegram_session()
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


async def broadcast_announcement_to_telegram(text: str, cohort_code: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        '''SELECT telegram_id
           FROM users
           WHERE telegram_id IS NOT NULL AND cohort_code=?
           ORDER BY full_name COLLATE NOCASE''',
        (normalize_cohort_code(cohort_code),),
    )
    recipients = [int(row[0]) for row in c.fetchall() if row[0]]
    conn.close()

    message = f"📢 Объявление:\n\n{text}"

    # Раньше рассылка шла строго последовательно (один await за другим) —
    # при ~90 юзерах это и давало те самые 15-18с, пока не отправится
    # последнее сообщение, всё это время админ ждал ответа на публикацию
    # новости. Telegram допускает ~30 сообщений/сек — шлём пачками по 20
    # параллельно, с паузой между пачками, чтобы не улететь в 429.
    BATCH_SIZE = 20
    sent = 0
    failed = 0
    for i in range(0, len(recipients), BATCH_SIZE):
        batch = recipients[i:i + BATCH_SIZE]
        results = await asyncio.gather(
            *(send_telegram_message(tid, message) for tid in batch),
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, Exception) or not (isinstance(r, tuple) and r[0]):
                failed += 1
            else:
                sent += 1
        if i + BATCH_SIZE < len(recipients):
            await asyncio.sleep(0.6)

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
                  mvp_user_id, extra_participants, pressure_tick_at, cohort_code
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
        "cohort_code": row[22] or COHORT_BEIJING,
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


def apply_mju_phase_transitions(c, event_row: dict):
    if event_row.get("code") != MJU_EVENT_CODE:
        return False

    changed = False
    hp_ratio = event_row["current_hp"] / event_row["max_hp"] if event_row["max_hp"] else 0

    if event_row["state"] == "ACTIVE" and event_row["phase"] == 1 and hp_ratio <= MJU_PHASE2_THRESHOLD:
        event_row["phase"] = 2
        event_row["phase_started_at"] = now_iso()
        c.execute(
            "UPDATE events SET phase=2, phase_started_at=? WHERE id=?",
            (event_row["phase_started_at"], event_row["id"]),
        )
        add_event_log(c, event_row["id"], "boss", "ЦЕНЗОР: первичный регламент снят. Запущено сетевое сканирование.")
        changed = True

    if event_row["state"] == "ACTIVE" and event_row["phase"] == 2 and hp_ratio <= MJU_PHASE3_THRESHOLD:
        event_row["phase"] = 3
        event_row["phase_started_at"] = now_iso()
        c.execute(
            "UPDATE events SET phase=3, phase_started_at=? WHERE id=?",
            (event_row["phase_started_at"], event_row["id"]),
        )
        add_event_log(c, event_row["id"], "boss", "ЦЕНЗОР: экзаменационный режим. Любая ошибка усиливает контроль.")
        changed = True

    return changed


def activate_wildai_breach(
    c,
    admin_id: Optional[int] = None,
    reason: str = 'Wild AI Breach auto-triggered (system integrity restoration failed)',
    send_broadcast: bool = True,
    cohort_code: str = COHORT_BEIJING,
):
    cohort_code = normalize_cohort_code(cohort_code)
    until = (datetime.utcnow() + timedelta(days=WILD_AI_BREACH_DURATION_DAYS)).isoformat()
    seed = random.randint(0, 999999)
    set_cohort_setting(c, 'breach_until', until, cohort_code)
    set_cohort_setting(c, 'breach_seed', seed, cohort_code)
    set_cohort_setting(c, 'blackwall', '1', cohort_code)
    phrase = WILD_AI_BREACH_PHRASES[seed % len(WILD_AI_BREACH_PHRASES)]
    set_cohort_setting(c, 'breach_broadcast_phrase_glitch', phrase["glitch"], cohort_code)
    set_cohort_setting(c, 'breach_broadcast_phrase_translation', phrase["translation"], cohort_code)
    if send_broadcast:
        set_cohort_setting(c, 'breach_broadcast_pending', '1', cohort_code)
    c.execute(
        '''INSERT INTO admin_action_logs
           (admin_id, target_id, action_type, points_delta, reason, created_at, cohort_code)
           VALUES (?, NULL, 'wildai_breach', 0, ?, ?, ?)''',
        (admin_id if admin_id is not None else 0, reason, now_iso(), cohort_code),
    )

def distribute_architect_victory_rewards(c, event_id: int):
    c.execute("SELECT telegram_id FROM event_participants WHERE event_id=?", (event_id,))
    participant_ids = [row[0] for row in c.fetchall()]
    for telegram_id in participant_ids:
        c.execute("UPDATE user_status SET architect_winner=1 WHERE telegram_id=?", (telegram_id,))


def distribute_wildai_victory_rewards(c, event_id: int, mvp_id: Optional[int]):
    c.execute("SELECT telegram_id FROM event_participants WHERE event_id=?", (event_id,))
    participant_ids = [row[0] for row in c.fetchall()]
    for telegram_id in participant_ids:
        c.execute("UPDATE users SET rep_score = COALESCE(rep_score, 0) + ? WHERE telegram_id=?", (WILD_AI_BREACH_REWARD_REP, telegram_id))
        c.execute(
            "UPDATE user_status SET wildai_defender=1 WHERE telegram_id=?",
            (telegram_id,),
        )
        c.execute("UPDATE user_status SET wildai_mvp = ? WHERE telegram_id=?", (1 if telegram_id == mvp_id else 0, telegram_id))


def distribute_mju_victory_rewards(c, event_id: int, mvp_id: Optional[int]):
    c.execute("SELECT telegram_id FROM event_participants WHERE event_id=?", (event_id,))
    participant_ids = [row[0] for row in c.fetchall()]
    for telegram_id in participant_ids:
        c.execute("UPDATE users SET rep_score = COALESCE(rep_score, 0) + ? WHERE telegram_id=?", (MJU_REWARD_REP, telegram_id))


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
                activate_wildai_breach(c, send_broadcast=False, cohort_code=event_row.get('cohort_code', COHORT_BEIJING))

            if event_row["current_hp"] <= 0:
                event_row["current_hp"] = 0
                event_row["state"] = "FINISHED"
                event_row["ended_at"] = now_iso()
                c.execute(
                    f"""SELECT telegram_id FROM event_participants
                       WHERE event_id=?
                         AND telegram_id NOT IN ({FLATLINED_PLACEHOLDERS})
                       ORDER BY total_damage DESC, total_support DESC LIMIT 1""",
                    (event_row["id"], *FLATLINED_ID_LIST),
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

    if event_row.get("code") == MJU_EVENT_CODE:
        if event_row["state"] == "ACTIVE":
            apply_mju_phase_transitions(c, event_row)

            if event_row["overload_pressure"] >= MJU_CRITICAL_THRESHOLD:
                event_row["overload_pressure"] = MJU_CRITICAL_THRESHOLD
                c.execute(
                    "UPDATE events SET overload_pressure=? WHERE id=?",
                    (MJU_CRITICAL_THRESHOLD, event_row["id"]),
                )

            if event_row["current_hp"] <= 0:
                event_row["current_hp"] = 0
                event_row["state"] = "FINISHED"
                event_row["phase"] = 4
                event_row["ended_at"] = now_iso()
                c.execute(
                    f"""SELECT telegram_id FROM event_participants
                       WHERE event_id=?
                         AND telegram_id NOT IN ({FLATLINED_PLACEHOLDERS})
                       ORDER BY total_damage DESC, total_support DESC LIMIT 1""",
                    (event_row["id"], *FLATLINED_ID_LIST),
                )
                mvp_row = c.fetchone()
                mvp_id = mvp_row[0] if mvp_row else None
                c.execute(
                    "UPDATE events SET current_hp=0, state='FINISHED', phase=4, ended_at=?, mvp_user_id=? WHERE id=?",
                    (event_row["ended_at"], mvp_id, event_row["id"]),
                )
                event_row["mvp_user_id"] = mvp_id
                add_event_log(c, event_row["id"], "system", "Босс Протокола пройден. Цензор признал команду.")
                distribute_mju_victory_rewards(c, event_row["id"], mvp_id)

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
            f"""SELECT telegram_id FROM event_participants
               WHERE event_id=?
                 AND telegram_id NOT IN ({FLATLINED_PLACEHOLDERS})
               ORDER BY total_damage DESC, total_support DESC LIMIT 1""",
            (event_row["id"], *FLATLINED_ID_LIST),
        )
        mvp_row = c.fetchone()
        mvp_id = mvp_row[0] if mvp_row else None
        c.execute(
            "UPDATE events SET current_hp=0, state='FINISHED', phase=4, ended_at=?, mvp_user_id=? WHERE id=?",
            (event_row["ended_at"], mvp_id, event_row["id"]),
        )
        event_row["mvp_user_id"] = mvp_id
        distribute_architect_victory_rewards(c, event_row["id"])
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
    overload_threshold = MJU_VIOLATION_THRESHOLD if event_row.get("code") == MJU_EVENT_CODE else ARCHITECT_OVERLOAD_PENALTY_THRESHOLD

    snapshot = {
        **event_row,
        "team_members": team_members,
        "team_count": len(team_members),
        "logs": logs,
        "total_actions": total_actions,
        "total_damage": total_damage,
        "vulnerability_active": is_vulnerability_active(event_row),
        "vulnerability_until": event_row.get("vulnerability_until"),
        "overload_penalty_active": event_row["overload_pressure"] >= overload_threshold,
    }
    conn.close()
    return snapshot


ARCHITECT_RESULT_VISIBLE_HOURS = 12


def get_current_or_latest_event_id(event_code: Optional[str] = None, cohort_code: str = COHORT_BEIJING):
    conn = get_conn()
    c = conn.cursor()
    cohort_code = normalize_cohort_code(cohort_code)
    if event_code:
        c.execute(
            "SELECT id FROM events WHERE state IN ('REGISTRATION', 'ACTIVE') AND code=? AND cohort_code=? ORDER BY id DESC",
            (event_code, cohort_code),
        )
    else:
        c.execute(
            "SELECT id FROM events WHERE state IN ('REGISTRATION', 'ACTIVE') AND cohort_code=? ORDER BY id DESC",
            (cohort_code,),
        )
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

    if event_code:
        c.execute(
            "SELECT id, ended_at FROM events WHERE state IN ('FINISHED', 'FAILED') AND code=? AND cohort_code=? ORDER BY id DESC LIMIT 1",
            (event_code, cohort_code),
        )
    else:
        c.execute(
            "SELECT id, ended_at FROM events WHERE state IN ('FINISHED', 'FAILED') AND cohort_code=? ORDER BY id DESC LIMIT 1",
            (cohort_code,),
        )
    terminal = c.fetchone()
    conn.close()
    if terminal:
        ended = parse_iso(terminal[1])
        if ended and datetime.utcnow() - ended <= timedelta(hours=ARCHITECT_RESULT_VISIBLE_HOURS):
            return terminal[0]
    return None


def get_blocking_event_id(event_code: Optional[str] = None, cohort_code: str = COHORT_BEIJING):
    conn = get_conn()
    c = conn.cursor()
    cohort_code = normalize_cohort_code(cohort_code)
    if event_code:
        c.execute(
            "SELECT id FROM events WHERE state IN ('REGISTRATION', 'ACTIVE') AND code=? AND cohort_code=? ORDER BY id DESC",
            (event_code, cohort_code),
        )
    else:
        c.execute(
            "SELECT id FROM events WHERE state IN ('REGISTRATION', 'ACTIVE') AND cohort_code=? ORDER BY id DESC",
            (cohort_code,),
        )
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

def _event_question_payload(row):
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


QUESTION_OPTION_KEYS = ("a", "b", "c")


def stable_question_seed(*parts) -> int:
    raw = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def shuffled_question_options(option_a: str, option_b: str, option_c: str, *seed_parts):
    entries = [
        ("a", option_a),
        ("b", option_b),
        ("c", option_c),
    ]
    rng = random.Random(stable_question_seed(*seed_parts))
    rng.shuffle(entries)
    options = {}
    display_to_original = {}
    for display_key, (original_key, text) in zip(QUESTION_OPTION_KEYS, entries):
        options[display_key] = text
        display_to_original[display_key] = original_key
    return options, display_to_original


def is_shuffled_answer_correct(
    answer_option: str,
    correct_option: str,
    option_a: str,
    option_b: str,
    option_c: str,
    *seed_parts,
) -> bool:
    _, display_to_original = shuffled_question_options(option_a, option_b, option_c, *seed_parts)
    return display_to_original.get(answer_option) == correct_option


def choose_architect_question(
    c,
    action_type: str,
    event_code: str = 'architect',
    event_id: Optional[int] = None,
    telegram_id: Optional[int] = None,
):
    """Pick a question without repeats inside the current event/action cycle."""
    if event_id is None:
        c.execute(
            '''SELECT id, prompt, option_a, option_b, option_c, explanation
               FROM event_questions
               WHERE event_code=? AND action_type=?
               ORDER BY RANDOM()
               LIMIT 1''',
            (event_code, action_type),
        )
        return _event_question_payload(c.fetchone())

    c.execute(
        "SELECT COUNT(*) FROM event_questions WHERE event_code=? AND action_type=?",
        (event_code, action_type),
    )
    if (c.fetchone()[0] or 0) <= 0:
        return None

    c.execute(
        "SELECT COALESCE(MAX(cycle), 1) FROM event_question_draws WHERE event_id=? AND action_type=?",
        (int(event_id), action_type),
    )
    current_cycle = int(c.fetchone()[0] or 1)

    for _ in range(3):
        c.execute(
            '''SELECT id, prompt, option_a, option_b, option_c, explanation
               FROM event_questions
               WHERE event_code=? AND action_type=?
                 AND id NOT IN (
                     SELECT question_id
                     FROM event_question_draws
                     WHERE event_id=? AND action_type=? AND cycle=?
                 )
               ORDER BY RANDOM()
               LIMIT 1''',
            (event_code, action_type, int(event_id), action_type, current_cycle),
        )
        row = c.fetchone()
        if row:
            try:
                c.execute(
                    '''INSERT INTO event_question_draws
                       (event_id, action_type, question_id, cycle, telegram_id, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)''',
                    (int(event_id), action_type, int(row[0]), current_cycle, telegram_id, now_iso()),
                )
                return _event_question_payload(row)
            except sqlite3.IntegrityError:
                continue
        current_cycle += 1

    c.execute(
        '''SELECT id, prompt, option_a, option_b, option_c, explanation
           FROM event_questions
           WHERE event_code=? AND action_type=?
           ORDER BY RANDOM()
           LIMIT 1''',
        (event_code, action_type),
    )
    return _event_question_payload(c.fetchone())


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


def get_mju_base_value(phase: int, action_type: str, is_correct: bool) -> int:
    if action_type == "sync":
        return 0

    phase_values = {
        1: {"attack": 30, "protocol": 24, "stabilize": 14},
        2: {"attack": 24, "protocol": 34, "stabilize": 18},
        3: {"attack": 20, "protocol": 42, "stabilize": 22},
    }
    full = phase_values.get(phase, phase_values[3]).get(action_type, 0)
    if not is_correct:
        return max(0, round(full * 0.2))
    return full


def compute_mju_action_result(c, event_row: dict, participant: dict, action_type: str, is_correct: bool, telegram_id: int = 0):
    phase = int(event_row.get("phase") or 1)
    base_value = get_mju_base_value(phase, action_type, is_correct)
    final_value = base_value
    support_value = 0
    pressure_delta = 0
    penalty_active = event_row["overload_pressure"] >= MJU_VIOLATION_THRESHOLD

    if action_type == "sync":
        support_value = 2 if is_correct else 0
        pressure_delta = -3 if is_correct else 4
        maybe_trigger_sync_window(c, event_row)
        return {
            "base_value": 0,
            "modifier_value": 0,
            "final_value": 0,
            "support_value": support_value,
            "pressure_delta": pressure_delta,
            "active_note": None,
            "penalty_active": penalty_active,
            "overload_threshold": MJU_VIOLATION_THRESHOLD,
            "overload_pct_str": "35%",
        }

    if action_type in ("attack", "protocol"):
        if not is_correct:
            pressure_delta = 5
        elif action_type == "attack":
            pressure_delta = 1

        if is_vulnerability_active(event_row) and final_value > 0:
            bonus = max(1, round(final_value * 0.25))
            final_value += bonus

        if penalty_active and final_value > 0:
            final_value = max(1, round(final_value * 0.65))

        return {
            "base_value": base_value,
            "modifier_value": final_value - base_value,
            "final_value": final_value,
            "support_value": 0,
            "pressure_delta": pressure_delta,
            "active_note": None,
            "penalty_active": penalty_active,
            "overload_threshold": MJU_VIOLATION_THRESHOLD,
            "overload_pct_str": "35%",
        }

    if is_correct:
        support_value = base_value
        pressure_delta = -6
    else:
        pressure_delta = 4

    return {
        "base_value": base_value,
        "modifier_value": 0,
        "final_value": 0,
        "support_value": support_value,
        "pressure_delta": pressure_delta,
        "active_note": None,
        "penalty_active": penalty_active,
        "overload_threshold": MJU_VIOLATION_THRESHOLD,
        "overload_pct_str": "35%",
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
    elif event_row.get("code") == MJU_EVENT_CODE:
        result = compute_mju_action_result(c, event_row, participant, action_type, is_correct, telegram_id=telegram_id)
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


def user_raid_attempt_count(c, today: str, telegram_id: int, cohort_code: str) -> int:
    c.execute(
        '''SELECT COUNT(DISTINCT rp.raid_id)
           FROM raid_participants rp
           JOIN raids r ON r.id = rp.raid_id
           WHERE rp.telegram_id=? AND r.date=? AND r.cohort_code=?''',
        (telegram_id, today, cohort_code),
    )
    row = c.fetchone()
    return row[0] if row and row[0] is not None else 0


def public_finished_raid_count(c, today: str, cohort_code: str) -> int:
    placeholders = ','.join('?' * len(ADMIN_IDS))
    c.execute(
        f'''SELECT COUNT(DISTINCT r.id)
            FROM raids r
            JOIN raid_participants rp ON rp.raid_id = r.id
            WHERE r.date=? AND r.status='finished' AND r.cohort_code=?
            AND rp.telegram_id NOT IN ({placeholders})''',
        [today, cohort_code] + ADMIN_IDS,
    )
    row = c.fetchone()
    return row[0] if row and row[0] is not None else 0


def latest_visible_raid(c, today: str, telegram_id: int, cohort_code: str):
    if telegram_id in ADMIN_IDS:
        c.execute(
            "SELECT id, status, result FROM raids WHERE date=? AND cohort_code=? ORDER BY id DESC LIMIT 1",
            (today, cohort_code),
        )
        return c.fetchone()

    placeholders = ','.join('?' * len(ADMIN_IDS))
    c.execute(
        f'''SELECT r.id, r.status, r.result
            FROM raids r
            WHERE r.date=? AND r.cohort_code=?
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
        [today, cohort_code] + ADMIN_IDS,
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

TRIP_QUIZ_REWARD_POINTS = 50
TRIP_QUIZ_PASS_RATIO = 0.7

COMMUNITY_SHOP_REACTIONS = ['👍', '❤️', '🔥', '😂', '😮', '👑']
COMMUNITY_SHOP_VOTE_EMOJI = '👑'
COMMUNITY_SHOP_DEMAND_LIKES = 70


def award_achievement(c, telegram_id: int, code: str) -> bool:
    """Awards an achievement if not already earned. Returns True if newly granted."""
    c.execute(
        "INSERT OR IGNORE INTO user_achievements (telegram_id, achievement_code) VALUES (?,?)",
        (telegram_id, code),
    )
    granted = c.rowcount > 0
    if granted:
        unlock_diary_entry(c, telegram_id, "first_achievement")
    return granted


ARCHITECT_DIARY_CLIENT_UNLOCKABLE = {"architect_intro", "architect_victory", "architect_defeat"}


def unlock_diary_entry(c, telegram_id: int, entry_code: str) -> bool:
    """Marks an Architect's Diary entry as unlocked for a user. Returns True if newly unlocked."""
    c.execute(
        "INSERT OR IGNORE INTO architect_diary_unlocks (telegram_id, entry_code, unlocked_at) VALUES (?,?,?)",
        (telegram_id, entry_code, now_iso()),
    )
    return c.rowcount > 0


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


def try_block_penalty_with_immunity(c, telegram_id: int, use_key: str) -> bool:
    c.execute("SELECT immunity FROM user_status WHERE telegram_id=?", (telegram_id,))
    row = c.fetchone()
    if not row or not row[0]:
        return False
    c.execute("UPDATE user_status SET immunity=0 WHERE telegram_id=?", (telegram_id,))
    c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
    balance_after = (c.fetchone() or [0])[0] or 0
    log_economy(c, telegram_id, "immunity_block", 0, balance_after, None, "shop", use_key)
    return True


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
                  created_at, accepted_at, completed_at, cancelled_at, disputed_at,
                  submitted_at, auto_confirm_at
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


# /api/user (профиль) — самый частый запрос в приложении. Раньше он на КАЖДУЮ
# загрузку логинился в Marzban за токеном и открывал две новые сессии, без
# таймаута. Это: (1) тормозило профиль на два внешних round-trip; (2) при
# недоступном/отвечающем с ошибкой Marzban могло подвесить профиль (и дать
# чёрный экран); (3) спамило Marzban запросами /api/admin/token (те 401 в
# логах). Кешируем токен (живёт ~сутки), держим одну сессию с таймаутом и
# мягко деградируем к профилю без VPN-данных, если Marzban недоступен.
_MARZBAN_TOKEN_CACHE = {"token": None, "expires_at": 0.0}
_MARZBAN_SESSION: Optional[aiohttp.ClientSession] = None


async def _get_marzban_session() -> aiohttp.ClientSession:
    global _MARZBAN_SESSION
    if _MARZBAN_SESSION is None or _MARZBAN_SESSION.closed:
        _MARZBAN_SESSION = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=6)
        )
    return _MARZBAN_SESSION


async def get_token(force_refresh: bool = False):
    now = time.time()
    if not force_refresh and _MARZBAN_TOKEN_CACHE["token"] and _MARZBAN_TOKEN_CACHE["expires_at"] > now:
        return _MARZBAN_TOKEN_CACHE["token"]
    try:
        session = await _get_marzban_session()
        async with session.post(
            f"{MARZBAN_URL}/api/admin/token",
            data={"username": MARZBAN_USER, "password": MARZBAN_PASS},
        ) as r:
            data = await r.json()
            token = data.get("access_token")
            if token:
                # токены Marzban живут ~24ч; кешируем на 23ч с запасом
                _MARZBAN_TOKEN_CACHE["token"] = token
                _MARZBAN_TOKEN_CACHE["expires_at"] = now + 23 * 3600
            return token
    except Exception as e:
        print("ZHIDAO_MARZBAN_TOKEN_ERROR %s" % e, flush=True)
        return None


async def get_user_data(marzban_username):
    token = await get_token()
    if not token:
        return {}
    try:
        session = await _get_marzban_session()
        url = f"{MARZBAN_URL}/api/user/{marzban_username}"
        headers = {"Authorization": f"Bearer {token}"}
        async with session.get(url, headers=headers) as r:
            if r.status == 401:
                # кешированный токен протух — один повтор со свежим
                token = await get_token(force_refresh=True)
                if not token:
                    return {}
                async with session.get(url, headers={"Authorization": f"Bearer {token}"}) as r2:
                    return await r2.json() if r2.status < 400 else {}
            return await r.json() if r.status < 400 else {}
    except Exception as e:
        print("ZHIDAO_MARZBAN_USER_ERROR %s" % e, flush=True)
        return {}


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
                  us.wildai_mvp, u.study_group, u.cohort_code
           FROM users u
           LEFT JOIN user_status us ON us.telegram_id = u.telegram_id
           WHERE u.telegram_id=?''',
        (telegram_id,),
    )
    user_row = c.fetchone()
    if not user_row:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    full_name, points, avatar_url, theme_path, manual_showcase_kind, manual_showcase_code, rep_score, equipped_frame, wildai_mvp, study_group, cohort_code = user_row
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
    # Manual showcase picks must keep showing even if that specific item's
    # durability later drops to 0 — otherwise the user's choice silently
    # falls back to "auto" with no way to tell why.
    c.execute(
        "SELECT implant_id, durability FROM user_implants WHERE telegram_id=?",
        (telegram_id,),
    )
    all_implants = c.fetchall()
    c.execute(
        "SELECT card_id, durability FROM user_cards WHERE telegram_id=?",
        (telegram_id,),
    )
    all_cards = c.fetchall()

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
        manual_implant = next((row for row in all_implants if row[0] == manual_code), None)
        if manual_implant:
            showcase = implant_showcase(manual_implant[0], manual_implant[1], "manual")
    elif manual_kind == "card" and manual_code:
        manual_card = next((row for row in all_cards if row[0] == manual_code), None)
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

    rank_excluded_ids = sorted(set(ADMIN_IDS) | FLATLINED_IDS)
    rank_placeholders = ','.join('?' * len(rank_excluded_ids))
    leaderboard_rank = None
    if telegram_id not in rank_excluded_ids:
        c.execute(
            f'''SELECT COUNT(*) + 1
                FROM users
                WHERE telegram_id IS NOT NULL
                  AND cohort_code=?
                  AND telegram_id NOT IN ({rank_placeholders})
                  AND points > ?''',
            [normalize_cohort_code(cohort_code)] + rank_excluded_ids + [points],
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

    # Admins always display as SS-rank / fully synced — cosmetic display
    # override only, the underlying reputation_score (and the breakdown a
    # student would see for themselves) stays based on real stats.
    if telegram_id in ADMIN_IDS:
        rank = "SS"
        sync_rate = 99

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
        title = "红墙幸存者 / Выживший у Красного Файрвола"
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
        "flatlined": telegram_id in FLATLINED_IDS,
        "study_group": study_group_payload(study_group),
        "cohort_code": normalize_cohort_code(cohort_code),
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
        "status_line": (
            "状态：断开 // NETWATCH：FLATLINED // 排名权限已撤销"
            if telegram_id in FLATLINED_IDS
            else f"状态：在线 // 权限：{permission_label} // 同步率：{sync_rate}%"
        ),
    }


# Trip window for Rewind's "duration" framing — there is no per-user
# registration timestamp on `users`, so trip length must come from these
# fixed dates rather than from the DB. Update before each trip.
REWIND_TRIP_START = "2026-07-04"
REWIND_TRIP_END = "2026-07-27"


def _rewind_format_date_range(start_iso: str, end_iso: str) -> str:
    start = datetime.strptime(start_iso, "%Y-%m-%d")
    end = datetime.strptime(end_iso, "%Y-%m-%d")
    return f"{start.strftime('%d.%m')} — {end.strftime('%d.%m.%Y')}"


REWIND_CASE_PRIZE_INFO = {
    "jackpot":             {"name": "ДЖЕКПОТ! +100★",              "rarity": "epic"},
    "medium":              {"name": "+60 баллов",                    "rarity": "rare"},
    "small":               {"name": "+30 баллов",                    "rarity": "common"},
    "walk":                {"name": "+30 мин свободы",                "rarity": "common"},
    "laundry":             {"name": "Вне очереди!",                  "rarity": "common"},
    "skip":                {"name": "Иммунитет!",                    "rarity": "rare"},
    "empty":               {"name": "Пустая миска риса",              "rarity": "common"},
    "implant_guanxi":      {"name": "Имплант Гуаньси 关系",            "rarity": "epic"},
    "implant_terracota":   {"name": "Имплант Терракота 兵马俑",        "rarity": "legendary"},
    "implant_panda":       {"name": "Имплант Панда 🐼",               "rarity": "epic"},
    "implant_shaolin":     {"name": "Имплант Шаолинь 少林",            "rarity": "epic"},
    "implant_linguasoft":  {"name": "Имплант Linguasoft 口才",        "rarity": "epic"},
    "implant_caishen":     {"name": "Имплант Цайшэнь 财神",            "rarity": "epic"},
    "implant_qilin":       {"name": "Имплант Цилинь 麒麟",             "rarity": "epic"},
    "implant_red_dragon":  {"name": "Протокол Красный Дракон 红龙",   "rarity": "legendary"},
}
# Mirrors IMPLANT_IMGS / GENSHIN_IMGS in js/casino.js so the Rewind "best
# drop" slide can show the actual item art instead of just its name.
REWIND_IMPLANT_IMAGES = {
    "implant_guanxi":     "https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/guanxi_implant.png?raw=true",
    "implant_terracota":  "https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/armor.png",
    "implant_red_dragon": "https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/honglong_implant.png?raw=true",
    "implant_panda":      "https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/panda_implant.png?raw=true",
    "implant_shaolin":    "https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/shaolin_implant.png?raw=true",
    "implant_linguasoft": "https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/linguasoft_implant.png?raw=true",
    "implant_caishen":    "https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/caishen.png?raw=true",
    "implant_qilin":      "https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/qilin_implant.png?raw=true",
}
REWIND_CARD_IMAGES = {
    "card_zhongli":    "https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_zhongli.png",
    "card_pyro":       "https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_pyro.png",
    "card_fox":        "https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_fox.png",
    "card_fairy":      "https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_fairy.png",
    "card_literature": "https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_literature.png",
    "card_forest":     "https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_forest.png",
    "card_sea":        "https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_sea.png",
    "card_moon":       "https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/moon_card.png",
    "card_star":       "https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_star.png",
}
REWIND_RARITY_RANK = {"common": 0, "rare": 1, "epic": 2, "legendary": 3}
# Must stay in sync with REWIND_CASE_PRIZE_INFO's "legendary" entries and
# CARD_INFO's 5-star cards (genshin_<card_id>).
REWIND_LEGENDARY_PRIZE_CODES = ["implant_red_dragon", "implant_terracota", "genshin_card_zhongli", "genshin_card_star"]


def _rewind_admin_exclude_clause(column: str):
    """SQL snippet + params to drop admin/test accounts from cross-user
    Rewind comparisons, so 'best of the trip' titles reflect real students."""
    if not ADMIN_IDS:
        return "", []
    placeholders = ','.join('?' * len(ADMIN_IDS))
    return f" AND {column} NOT IN ({placeholders})", list(ADMIN_IDS)


def _rewind_drop_info(prize_code: str):
    """Resolve a casino_log.prize code to a display name + rarity for Rewind's
    'best drop' slide. Cases use REWIND_CASE_PRIZE_INFO; prayers (genshin_*)
    fall back to CARD_INFO rarity (5★→legendary, 4★→epic) or are skipped if
    the drop was just points/a buff with no collectible attached."""
    if prize_code.startswith("genshin_"):
        card_id = prize_code[len("genshin_"):]
        if card_id.startswith("card_") and card_id in CARD_INFO:
            info = CARD_INFO[card_id]
            rarity = "legendary" if info.get("rarity", 4) >= 5 else "epic"
            return {"name": info.get("name", card_id), "rarity": rarity, "image_url": REWIND_CARD_IMAGES.get(card_id)}
        return None
    info = REWIND_CASE_PRIZE_INFO.get(prize_code)
    if not info:
        return None
    return {"name": info["name"], "rarity": info["rarity"], "image_url": REWIND_IMPLANT_IMAGES.get(prize_code)}


@app.get("/api/rewind/{telegram_id}")
def get_trip_rewind(telegram_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT full_name, points FROM users WHERE telegram_id=?", (telegram_id,))
    user_row = c.fetchone()
    if not user_row:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    full_name, final_balance = user_row
    final_balance = final_balance or 0

    c.execute(
        '''SELECT
             COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0),
             COALESCE(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END), 0)
           FROM economy_log WHERE telegram_id=?''',
        (telegram_id,),
    )
    points_earned, points_spent = c.fetchone()

    c.execute("SELECT prize FROM casino_log WHERE telegram_id=?", (telegram_id,))
    drop_rows = c.fetchall()
    cases_opened = sum(1 for (prize,) in drop_rows if not prize.startswith("genshin_"))
    best_drop = None
    best_rank = -1
    for (prize,) in drop_rows:
        drop = _rewind_drop_info(prize)
        if not drop:
            continue
        rank = REWIND_RARITY_RANK.get(drop["rarity"], 0)
        if rank > best_rank:
            best_rank = rank
            best_drop = drop

    c.execute(
        '''SELECT COUNT(DISTINCT check_date),
                  COUNT(DISTINCT CASE WHEN status IN ('confirmed','free_time','admin_approved') THEN check_date END)
           FROM daily_checks WHERE telegram_id=?''',
        (telegram_id,),
    )
    total_check_dates, ok_check_dates = c.fetchone()
    attendance_pct = round(100 * ok_check_dates / total_check_dates) if total_check_dates else 100

    c.execute(
        "SELECT COUNT(*) FROM diary_entries WHERE telegram_id=? AND status IN ('submitted','locked')",
        (telegram_id,),
    )
    diary_entries = c.fetchone()[0] or 0
    c.execute(
        '''SELECT AVG(ds.stars) FROM diary_stars ds
           JOIN diary_entries de ON de.telegram_id=ds.telegram_id AND de.entry_date=ds.entry_date
           WHERE ds.telegram_id=? AND de.status IN ('submitted','locked')''',
        (telegram_id,),
    )
    diary_avg_stars = c.fetchone()[0] or 0

    c.execute("SELECT COUNT(DISTINCT event_id) FROM event_participants WHERE telegram_id=?", (telegram_id,))
    events_repelled = c.fetchone()[0] or 0
    c.execute(
        "SELECT COUNT(*), COALESCE(SUM(is_correct),0) FROM event_actions WHERE telegram_id=?",
        (telegram_id,),
    )
    total_actions, correct_actions = c.fetchone()
    event_accuracy = round(100 * correct_actions / total_actions) if total_actions else 0

    c.execute("SELECT COUNT(*) FROM shop_purchases WHERE given_to=?", (telegram_id,))
    gifts_given = c.fetchone()[0] or 0

    # Weekly activity timeline: bucket points earned into 7-day windows from
    # the trip start so the "когда ты фармил больше всего" slide has data
    # without needing a new table — reuses economy_log timestamps.
    trip_start_dt = datetime.strptime(REWIND_TRIP_START, "%Y-%m-%d")
    c.execute(
        "SELECT created_at, amount FROM economy_log WHERE telegram_id=? AND amount>0",
        (telegram_id,),
    )
    week_totals = {}
    for created_at, amount in c.fetchall():
        entry_dt = parse_iso(created_at) or trip_start_dt
        week_idx = max(0, (entry_dt - trip_start_dt).days // 7)
        week_totals[week_idx] = week_totals.get(week_idx, 0) + amount
    timeline = [
        {"label": f"Нед. {i + 1}", "value": week_totals[i]}
        for i in sorted(week_totals.keys())
    ]

    # Cross-user comparison ("top X% by points earned"), same admin-exclusion
    # rule as the role highlights below — admins viewing their own Rewind
    # don't get a percentile since they're not part of the comparison pool.
    percentile = None
    beaten_count = None
    if telegram_id not in ADMIN_IDS:
        clause, params = _rewind_admin_exclude_clause('telegram_id')
        c.execute(
            f'''SELECT telegram_id, SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END)
                FROM economy_log
                WHERE 1=1{clause}
                GROUP BY telegram_id''',
            params,
        )
        earn_rows = [(tid, v or 0) for tid, v in c.fetchall()]
        total_n = len(earn_rows)
        if total_n > 0:
            ahead = sum(1 for _, v in earn_rows if v > points_earned)
            beaten_count = max(0, total_n - ahead - 1)
            percentile = max(1, round(100 * (ahead + 1) / total_n))

    # Anti-record: a self-deprecating stat for balance against the otherwise
    # all-praise slides. Prefers a string of empty case draws (funnier/more
    # relatable than a raw points number) and falls back to the single
    # biggest one-shot spend.
    empty_draws = sum(1 for (prize,) in drop_rows if prize == "empty")
    c.execute(
        "SELECT amount FROM economy_log WHERE telegram_id=? AND amount<0 ORDER BY amount ASC LIMIT 1",
        (telegram_id,),
    )
    biggest_spend_row = c.fetchone()
    if empty_draws >= 3:
        antirecord = {"label": "невезение протокола", "value": f"{empty_draws}x", "sub": "пустая миска риса в кейсах"}
    elif biggest_spend_row and biggest_spend_row[0] <= -50:
        antirecord = {"label": "самый дорогой порыв", "value": f"-{abs(biggest_spend_row[0])}", "sub": "потрачено за один раз"}
    else:
        antirecord = {"label": "без явных проколов", "value": "0", "sub": "ни одного заметного прокола за поездку"}

    # Role: who's the most pronounced at each highlight-worthy stat across the
    # whole trip (not just against their own numbers), so the closing slide
    # can call out "единственный, кто..." when that's actually true. Admins/
    # test accounts are excluded from the comparison pool so their seed data
    # doesn't steal the spotlight from real students; an admin viewing their
    # own Rewind just gets the generic fallback title.
    role = None
    if telegram_id not in ADMIN_IDS:
        clause, params = _rewind_admin_exclude_clause('telegram_id')
        code_ph = ','.join('?' * len(REWIND_LEGENDARY_PRIZE_CODES))
        c.execute(
            f'''SELECT telegram_id, COUNT(*) FROM casino_log
                WHERE prize IN ({code_ph}){clause}
                GROUP BY telegram_id''',
            REWIND_LEGENDARY_PRIZE_CODES + params,
        )
        legendary_holders = [tid for tid, cnt in c.fetchall() if cnt > 0]
        if telegram_id in legendary_holders:
            if len(legendary_holders) == 1:
                role = {"title": "ЛЮБИМЕЦ РАНДОМА", "subtitle": "единственный, кто выбил легендарный дроп за поездку"}
            else:
                role = {"title": "ЛЮБИМЕЦ РАНДОМА", "subtitle": f"один из {len(legendary_holders)} операторов с легендарным дропом"}

        if not role:
            clause, params = _rewind_admin_exclude_clause('telegram_id')
            c.execute(
                f'''SELECT telegram_id,
                           100.0 * COUNT(DISTINCT CASE WHEN status IN ('confirmed','free_time','admin_approved') THEN check_date END)
                           / COUNT(DISTINCT check_date)
                    FROM daily_checks
                    WHERE 1=1{clause}
                    GROUP BY telegram_id''',
                params,
            )
            attendance_rows = [(tid, pct) for tid, pct in c.fetchall() if pct is not None]
            if attendance_rows:
                top_pct = max(pct for _, pct in attendance_rows)
                leaders = [tid for tid, pct in attendance_rows if pct == top_pct]
                if telegram_id in leaders and top_pct >= 95:
                    role = {
                        "title": "ОБРАЗЦОВЫЙ ОПЕРАТОР",
                        "subtitle": "лучшая дисциплина отметок за поездку" if len(leaders) == 1 else "в числе лучших по дисциплине отметок",
                    }

        if not role:
            clause, params = _rewind_admin_exclude_clause('telegram_id')
            c.execute(
                f'''SELECT telegram_id, COUNT(*), SUM(is_correct) FROM event_actions
                    WHERE 1=1{clause}
                    GROUP BY telegram_id
                    HAVING COUNT(*) >= 5''',
                params,
            )
            accuracy_rows = [(tid, 100.0 * correct / total) for tid, total, correct in c.fetchall()]
            if accuracy_rows:
                top_acc = max(acc for _, acc in accuracy_rows)
                leaders = [tid for tid, acc in accuracy_rows if acc == top_acc]
                if telegram_id in leaders:
                    role = {
                        "title": "СТРАТЕГ ПРОТОКОЛА",
                        "subtitle": "самая высокая точность ответов в ивентах" if len(leaders) == 1 else "в числе самых точных операторов в ивентах",
                    }

        if not role:
            clause, params = _rewind_admin_exclude_clause('given_to')
            c.execute(
                f'''SELECT given_to, COUNT(*) FROM shop_purchases
                    WHERE given_to IS NOT NULL{clause}
                    GROUP BY given_to''',
                params,
            )
            gift_rows = c.fetchall()
            if gift_rows:
                top_gifts = max(cnt for _, cnt in gift_rows)
                leaders = [tid for tid, cnt in gift_rows if cnt == top_gifts]
                if telegram_id in leaders and top_gifts >= 1:
                    role = {
                        "title": "МЕЦЕНАТ ПРОТОКОЛА",
                        "subtitle": "больше всех делился баллами с другими операторами" if len(leaders) == 1 else "в числе самых щедрых операторов",
                    }

        if not role:
            clause, params = _rewind_admin_exclude_clause('telegram_id')
            c.execute(
                f'''SELECT telegram_id, SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END) FROM economy_log
                    WHERE 1=1{clause}
                    GROUP BY telegram_id''',
                params,
            )
            spend_rows = [(tid, v) for tid, v in c.fetchall() if v]
            if spend_rows:
                top_spend = max(v for _, v in spend_rows)
                leaders = [tid for tid, v in spend_rows if v == top_spend]
                if telegram_id in leaders and top_spend > 0:
                    role = {
                        "title": "ШОПОГОЛИК ПРОТОКОЛА",
                        "subtitle": "потратил больше всех баллов за поездку" if len(leaders) == 1 else "в числе самых активных по тратам",
                    }

    conn.close()

    if not role:
        role = {"title": "ОПЕРАТОР ПРОТОКОЛА", "subtitle": "стабильно выполнял свою часть работы"}

    return {
        "name": full_name,
        "date_range": _rewind_format_date_range(REWIND_TRIP_START, REWIND_TRIP_END),
        "points_earned": points_earned,
        "points_spent": points_spent,
        "final_balance": final_balance,
        "cases_opened": cases_opened,
        "best_drop": best_drop,
        "attendance_pct": attendance_pct,
        "diary_entries": diary_entries,
        "diary_avg_stars": round(diary_avg_stars, 1),
        "events_repelled": events_repelled,
        "event_accuracy": event_accuracy,
        "gifts_given": gifts_given,
        "role": role,
        "timeline": timeline,
        "percentile": percentile,
        "beaten_count": beaten_count,
        "antirecord": antirecord,
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
async def create_global_alert_endpoint(
    data: dict,
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    caller_id = x_admin_id or data.get("telegram_id")
    if caller_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    alert_type = data.get("alert_type") or "architect"
    title = data.get("title") or "ARCHITECT ONLINE"
    message = data.get("message") or "Critical override detected."

    conn = get_conn()
    try:
        cohort_code = resolve_viewer_cohort(conn.cursor(), caller_id, x_cohort_code)
    finally:
        conn.close()
    alert_id = create_global_alert(alert_type, title, message, cohort_code)
    return {
        "success": True,
        "alert_id": alert_id,
    }


@app.get("/api/global-alert/current")
async def get_global_alert_current(
    x_telegram_id: Optional[int] = Header(None),
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    conn = get_conn()
    try:
        cohort_code = resolve_viewer_cohort(
            conn.cursor(), get_request_actor_id(x_telegram_id, x_admin_id), x_cohort_code
        )
    finally:
        conn.close()
    return {
        "alert": get_current_global_alert(cohort_code),
    }


@app.get("/api/schedule")
def get_schedule(
    x_telegram_id: Optional[int] = Header(None),
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    conn = get_conn()
    c = conn.cursor()
    cohort_code = resolve_viewer_cohort(
        c, get_request_actor_id(x_telegram_id, x_admin_id), x_cohort_code
    )
    c.execute(
        "SELECT id, day, time, subject, location FROM schedule "
        "WHERE cohort_code=? ORDER BY day, time",
        (cohort_code,),
    )
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "day": r[1], "time": r[2], "subject": r[3], "location": r[4]} for r in rows]


@app.post("/api/schedule")
async def add_schedule(
    item: ScheduleItem,
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    def _run():
        if x_admin_id not in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Forbidden")
        conn = get_conn()
        c = conn.cursor()
        cohort_code = resolve_viewer_cohort(c, x_admin_id, x_cohort_code)
        c.execute(
            "INSERT INTO schedule (day, time, subject, location, cohort_code) VALUES (?,?,?,?,?)",
            (item.day, item.time, item.subject, item.location, cohort_code),
        )
        conn.commit()
        conn.close()
        return {"success": True}
    return await db_write(_run)


@app.delete("/api/schedule/{item_id}")
async def delete_schedule(
    item_id: int,
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    def _run():
        if x_admin_id not in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Forbidden")
        conn = get_conn()
        c = conn.cursor()
        cohort_code = resolve_viewer_cohort(c, x_admin_id, x_cohort_code)
        c.execute("DELETE FROM schedule WHERE id=? AND cohort_code=?", (item_id, cohort_code))
        conn.commit()
        conn.close()
        return {"success": True}
    return await db_write(_run)


@app.get("/api/announcements")
def get_announcements(
    x_telegram_id: Optional[int] = Header(None),
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    conn = get_conn()
    c = conn.cursor()
    cohort_code = resolve_viewer_cohort(
        c, get_request_actor_id(x_telegram_id, x_admin_id), x_cohort_code
    )
    c.execute(
        "SELECT id, text, created_at FROM announcements "
        "WHERE cohort_code=? ORDER BY created_at DESC LIMIT 10",
        (cohort_code,),
    )
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "text": r[1], "created_at": r[2]} for r in rows]


@app.post("/api/announcements")
async def add_announcement(
    item: Announcement,
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")
    text = item.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Announcement text is empty")

    def _run():
        conn = get_conn()
        c = conn.cursor()
        try:
            cohort_code = resolve_viewer_cohort(c, x_admin_id, x_cohort_code)
            c.execute(
                "INSERT INTO announcements (text, cohort_code) VALUES (?,?)",
                (text, cohort_code),
            )
            announcement_id = c.lastrowid
            conn.commit()
            return announcement_id
        finally:
            conn.close()

    announcement_id = await db_write(_run)
    conn = get_conn()
    cohort_code = resolve_viewer_cohort(conn.cursor(), x_admin_id, x_cohort_code)
    conn.close()
    telegram_delivery = await broadcast_announcement_to_telegram(text, cohort_code)
    return {"success": True, "id": announcement_id, "telegram_delivery": telegram_delivery}


@app.delete("/api/announcements/{item_id}")
async def delete_announcement(
    item_id: int,
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    def _run():
        if x_admin_id not in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Forbidden")
        conn = get_conn()
        c = conn.cursor()
        cohort_code = resolve_viewer_cohort(c, x_admin_id, x_cohort_code)
        c.execute(
            "DELETE FROM announcements WHERE id=? AND cohort_code=?",
            (item_id, cohort_code),
        )
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


COMMUNITY_SHOP_DEMAND_PCT = 0.70


def _community_shop_demand(c, proposal_id: int):
    c.execute("SELECT emoji, COUNT(*) FROM community_shop_reactions WHERE proposal_id=? GROUP BY emoji", (proposal_id,))
    reaction_counts = {row[0]: row[1] for row in c.fetchall()}
    crown_count = reaction_counts.get(COMMUNITY_SHOP_VOTE_EMOJI, 0)
    c.execute(
        "SELECT cohort_code FROM community_shop_proposals WHERE id=?",
        (proposal_id,),
    )
    proposal_row = c.fetchone()
    proposal_cohort = normalize_cohort_code(proposal_row[0] if proposal_row else None)
    c.execute("SELECT COUNT(*) FROM users WHERE cohort_code=?", (proposal_cohort,))
    total_users = c.fetchone()[0] or 0
    participation_pct = (crown_count / total_users) if total_users else 0.0
    demand_confirmed = crown_count >= COMMUNITY_SHOP_DEMAND_LIKES or participation_pct >= COMMUNITY_SHOP_DEMAND_PCT
    return reaction_counts, crown_count, demand_confirmed, participation_pct


@app.post("/api/community-shop/propose")
async def community_shop_propose(data: dict):
    telegram_id = int(data.get("telegram_id") or 0)
    title = str(data.get("title") or "").strip()
    description = str(data.get("description") or "").strip()
    if not telegram_id:
        raise HTTPException(status_code=400, detail="telegram_id required")
    if not title or not description:
        raise HTTPException(status_code=400, detail="title and description required")

    def _run():
        conn = get_conn()
        try:
            c = conn.cursor()
            cohort_code = get_user_cohort(c, telegram_id)
            c.execute(
                "INSERT INTO community_shop_proposals "
                "(telegram_id, title, description, created_at, cohort_code) "
                "VALUES (?,?,?,?,?)",
                (telegram_id, title, description, now_iso(), cohort_code),
            )
            conn.commit()
            return {"success": True, "id": c.lastrowid}
        finally:
            conn.close()

    return await db_write(_run)


@app.get("/api/community-shop/proposals")
def community_shop_proposals(
    x_telegram_id: Optional[int] = Header(None),
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    conn = get_conn()
    c = conn.cursor()
    cohort_code = resolve_viewer_cohort(
        c, get_request_actor_id(x_telegram_id, x_admin_id), x_cohort_code
    )
    c.execute(
        '''SELECT p.id, p.title, p.description, p.status, p.created_at, p.telegram_id, COALESCE(u.full_name, p.telegram_id)
           FROM community_shop_proposals p LEFT JOIN users u ON u.telegram_id = p.telegram_id
           WHERE p.status != 'rejected' AND p.cohort_code=?
           ORDER BY p.created_at DESC''',
        (cohort_code,),
    )
    rows = c.fetchall()
    result = []
    for r in rows:
        _, crown_count, demand_confirmed, participation_pct = _community_shop_demand(c, r[0])
        result.append({
            "id": r[0], "title": r[1], "description": r[2], "status": r[3], "created_at": r[4],
            "telegram_id": r[5], "author_name": str(r[6]),
            "crown_count": crown_count, "demand_confirmed": demand_confirmed,
            "participation_pct": round(participation_pct * 100, 1),
        })
    conn.close()
    return result


@app.get("/api/community-shop/proposals/{proposal_id}/reactions")
def community_shop_reactions(proposal_id: int, telegram_id: int = None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT emoji, COUNT(*) as cnt FROM community_shop_reactions WHERE proposal_id=? GROUP BY emoji", (proposal_id,))
    rows = c.fetchall()
    my_emoji = None
    if telegram_id is not None:
        c.execute("SELECT emoji FROM community_shop_reactions WHERE proposal_id=? AND telegram_id=?", (proposal_id, telegram_id))
        my_row = c.fetchone()
        my_emoji = my_row[0] if my_row else None
    conn.close()
    return [{"emoji": r[0], "count": r[1], "you": r[0] == my_emoji} for r in rows]


@app.post("/api/community-shop/proposals/{proposal_id}/react")
async def community_shop_react(proposal_id: int, data: dict):
    def _run():
        telegram_id = data.get("telegram_id")
        emoji = data.get("emoji")
        if not telegram_id or not emoji:
            raise HTTPException(status_code=400, detail="Missing data")
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT emoji FROM community_shop_reactions WHERE proposal_id=? AND telegram_id=?", (proposal_id, telegram_id))
        existing = c.fetchone()
        if existing and existing[0] == emoji:
            c.execute("DELETE FROM community_shop_reactions WHERE proposal_id=? AND telegram_id=?", (proposal_id, telegram_id))
        else:
            c.execute("INSERT OR REPLACE INTO community_shop_reactions (proposal_id, telegram_id, emoji) VALUES (?,?,?)", (proposal_id, telegram_id, emoji))
        conn.commit()
        conn.close()
        return {"success": True}
    return await db_write(_run)


@app.get("/api/admin/community-shop/proposals")
def admin_community_shop_proposals(
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = get_conn()
    c = conn.cursor()
    cohort_code = resolve_viewer_cohort(c, x_admin_id, x_cohort_code)
    c.execute(
        '''SELECT p.id, p.title, p.description, p.status, p.created_at, p.telegram_id,
                  COALESCE(u.full_name, p.telegram_id), p.moderation_note
           FROM community_shop_proposals p LEFT JOIN users u ON u.telegram_id = p.telegram_id
           WHERE p.cohort_code=?
           ORDER BY p.created_at DESC''',
        (cohort_code,),
    )
    rows = c.fetchall()
    result = []
    for r in rows:
        _, crown_count, demand_confirmed, participation_pct = _community_shop_demand(c, r[0])
        result.append({
            "id": r[0], "title": r[1], "description": r[2], "status": r[3], "created_at": r[4],
            "telegram_id": r[5], "author_name": str(r[6]), "moderation_note": r[7],
            "crown_count": crown_count, "demand_confirmed": demand_confirmed,
            "participation_pct": round(participation_pct * 100, 1),
        })
    conn.close()
    result.sort(key=lambda p: p["crown_count"], reverse=True)
    return result


@app.post("/api/admin/community-shop/proposals/{proposal_id}/promote")
async def admin_promote_community_shop_proposal(proposal_id: int, data: dict, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")
    price = data.get("price")
    if not isinstance(price, int) or price <= 0:
        raise HTTPException(status_code=400, detail="Valid price required")
    icon = str(data.get("icon") or "🏮").strip()
    category = str(data.get("category") or "folk").strip()
    daily_limit = data.get("daily_limit")
    daily_limit = int(daily_limit) if isinstance(daily_limit, int) else -1

    def _run():
        conn = get_conn()
        try:
            c = conn.cursor()
            c.execute("SELECT title, description, status FROM community_shop_proposals WHERE id=?", (proposal_id,))
            row = c.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Proposal not found")
            title, description, status = row
            if status == 'promoted':
                raise HTTPException(status_code=409, detail="Already promoted")
            code = f"community_{proposal_id}"
            c.execute(
                '''INSERT INTO shop_items (code, name, description, icon, price, daily_limit, category, active)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                   ON CONFLICT(code) DO UPDATE SET name=excluded.name, description=excluded.description,
                     icon=excluded.icon, price=excluded.price, daily_limit=excluded.daily_limit,
                     category=excluded.category, active=1''',
                (code, title, description, icon, price, daily_limit, category),
            )
            c.execute(
                "UPDATE community_shop_proposals SET status='promoted', moderated_by=?, moderated_at=? WHERE id=?",
                (x_admin_id, now_iso(), proposal_id),
            )
            conn.commit()
            return {"success": True, "item_code": code}
        finally:
            conn.close()

    return await db_write(_run)


@app.post("/api/admin/community-shop/proposals/{proposal_id}/reject")
async def admin_reject_community_shop_proposal(proposal_id: int, data: dict, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")
    note = str(data.get("note") or "").strip() or None

    def _run():
        conn = get_conn()
        try:
            c = conn.cursor()
            c.execute(
                "UPDATE community_shop_proposals SET status='rejected', moderated_by=?, moderated_at=?, moderation_note=? WHERE id=?",
                (x_admin_id, now_iso(), note, proposal_id),
            )
            conn.commit()
            return {"success": True}
        finally:
            conn.close()

    return await db_write(_run)


@app.get("/api/laundry")
def get_laundry(
    x_telegram_id: Optional[int] = Header(None),
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    conn = get_conn()
    c = conn.cursor()
    cohort_code = resolve_viewer_cohort(
        c, get_request_actor_id(x_telegram_id, x_admin_id), x_cohort_code
    )
    c.execute(
        "SELECT id, date, time, telegram_id, username FROM laundry WHERE cohort_code=? ORDER BY date, time",
        (cohort_code,),
    )
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "date": r[1], "time": r[2], "telegram_id": r[3], "username": r[4]} for r in rows]


@app.post("/api/laundry")
async def book_laundry(item: LaundryBook):
    def _run():
        conn = get_conn()
        c = conn.cursor()
        cohort_code = get_user_cohort(c, item.telegram_id)
        c.execute(
            "SELECT id FROM laundry WHERE date=? AND time=? AND cohort_code=?",
            (item.date, item.time, cohort_code),
        )
        if c.fetchone():
            conn.close()
            raise HTTPException(status_code=409, detail="Slot already booked")
        c.execute("SELECT id FROM laundry WHERE telegram_id=? AND date=?", (item.telegram_id, item.date))
        if c.fetchone():
            conn.close()
            raise HTTPException(status_code=409, detail="Already booked for this day")
        c.execute(
            "INSERT INTO laundry (date, time, telegram_id, username, cohort_code) VALUES (?,?,?,?,?)",
            (item.date, item.time, item.telegram_id, item.username, cohort_code),
        )
        diary_unlocked = []
        if unlock_diary_entry(c, item.telegram_id, "first_laundry"):
            diary_unlocked.append("first_laundry")
        conn.commit()
        conn.close()
        return {"success": True, "diary_unlocked": diary_unlocked}
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
    c.execute("SELECT points, full_name, rep_score, cohort_code FROM users WHERE telegram_id=?", (telegram_id,))
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
        "cohort_code": normalize_cohort_code(result[3]),
        "double_win": status[0] if status else 0,
        "extra_cases": status[1] if status else 0,
        "immunity": status[2] if status else 0,
        "extra_raids": status[3] if status else 0,
        "theme_path": status[4] if status else None,
        "flatlined": telegram_id in FLATLINED_IDS,
    }


@app.get("/api/admin/users")
def admin_search_users(
    q: str = "",
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    query = str(q or "").strip()
    conn = get_conn()
    c = conn.cursor()
    cohort_code = resolve_viewer_cohort(c, x_admin_id, x_cohort_code)
    if query and query.isdigit():
        like = f"%{query}%"
        c.execute(
            '''SELECT telegram_id, full_name, marzban_username, points, avatar_url, room_number, study_group
               FROM users
               WHERE telegram_id IS NOT NULL AND cohort_code=?
                 AND (CAST(telegram_id AS TEXT) LIKE ? OR full_name LIKE ? OR marzban_username LIKE ?)
               ORDER BY points DESC
               LIMIT 20''',
            (cohort_code, like, like, like),
        )
        rows = c.fetchall()
    elif query:
        # SQLite's LIKE only case-folds ASCII letters, so Cyrillic names with a
        # different case (e.g. "марк" vs "Марк") never matched — filter in
        # Python with a Unicode-aware lower() instead.
        c.execute(
            '''SELECT telegram_id, full_name, marzban_username, points, avatar_url, room_number, study_group
               FROM users
               WHERE telegram_id IS NOT NULL AND cohort_code=?
               ORDER BY points DESC''',
            (cohort_code,),
        )
        needle = query.lower()
        rows = [
            row for row in c.fetchall()
            if needle in str(row[1] or "").lower() or needle in str(row[2] or "").lower()
        ][:20]
    else:
        c.execute(
            '''SELECT telegram_id, full_name, marzban_username, points, avatar_url, room_number, study_group
               FROM users
               WHERE telegram_id IS NOT NULL AND cohort_code=?
               ORDER BY points DESC
               LIMIT 20''',
            (cohort_code,),
        )
        rows = c.fetchall()
    roommate_map = {}
    room_numbers = sorted({row[5] for row in rows if row[5]})
    for room_number in room_numbers:
        c.execute(
            '''SELECT telegram_id, full_name, avatar_url
               FROM users
               WHERE room_number=? AND cohort_code=? AND telegram_id IS NOT NULL
               ORDER BY full_name COLLATE NOCASE''',
            (room_number, cohort_code),
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
                "study_group": study_group_payload(row[6]),
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
async def admin_update_user_room(
    data: dict,
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
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
        cohort_code = require_target_cohort(c, x_admin_id, telegram_id, x_cohort_code)
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
                     AND cohort_code=?
                     AND telegram_id IS NOT NULL
                     AND telegram_id != ?
                   ORDER BY full_name COLLATE NOCASE''',
                (room_number, cohort_code, telegram_id),
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


@app.post("/api/admin/user/study-group")
async def admin_update_user_study_group(data: dict, x_admin_id: Optional[int] = Header(None)):
    def _run():
        if x_admin_id not in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Forbidden")

        try:
            telegram_id = int(data.get("telegram_id"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid telegram_id")

        raw_group = str(data.get("study_group") or "").strip()
        study_group = normalize_study_group(raw_group)
        if raw_group and not study_group:
            raise HTTPException(status_code=400, detail="Invalid study group")

        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT full_name FROM users WHERE telegram_id=?", (telegram_id,))
        target = c.fetchone()
        if not target:
            conn.close()
            raise HTTPException(status_code=404, detail="User not found")

        c.execute(
            "UPDATE users SET study_group=? WHERE telegram_id=?",
            (study_group, telegram_id),
        )
        c.execute(
            '''INSERT INTO admin_action_logs
               (admin_id, target_id, action_type, points_delta, reason, created_at)
               VALUES (?, ?, 'study_group_update', 0, ?, ?)''',
            (x_admin_id, telegram_id, f"study_group: {study_group or 'empty'}", now_iso()),
        )
        conn.commit()
        conn.close()
        return {
            "success": True,
            "telegram_id": telegram_id,
            "full_name": target[0] or str(telegram_id),
            "study_group": study_group_payload(study_group),
        }
    return await db_write(_run)


@app.post("/api/admin/user/reset_avatar")
async def admin_reset_user_avatar(data: dict, x_admin_id: Optional[int] = Header(None)):
    def _run():
        if x_admin_id not in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Forbidden")

        try:
            telegram_id = int(data.get("telegram_id"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid telegram_id")

        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT full_name FROM users WHERE telegram_id=?", (telegram_id,))
        target = c.fetchone()
        if not target:
            conn.close()
            raise HTTPException(status_code=404, detail="User not found")

        c.execute("UPDATE users SET avatar_url=NULL WHERE telegram_id=?", (telegram_id,))
        c.execute(
            '''INSERT INTO admin_action_logs
               (admin_id, target_id, action_type, points_delta, reason, created_at)
               VALUES (?, ?, 'avatar_reset', 0, ?, ?)''',
            (x_admin_id, telegram_id, "avatar reset by admin", now_iso()),
        )
        conn.commit()
        conn.close()
        return {
            "success": True,
            "telegram_id": telegram_id,
            "full_name": target[0] or str(telegram_id),
        }
    return await db_write(_run)


@app.get("/api/admin/user/{telegram_id}/dossier")
def admin_user_dossier(
    telegram_id: int,
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    conn = get_conn()
    c = conn.cursor()
    cohort_code = require_target_cohort(c, x_admin_id, telegram_id, x_cohort_code)
    c.execute(
        '''SELECT u.telegram_id, u.full_name, u.marzban_username, u.points,
                  u.avatar_url, u.room_number, u.study_group, us.theme_path, u.rep_score
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
                 AND cohort_code=?
                 AND telegram_id IS NOT NULL
                 AND telegram_id != ?
               ORDER BY full_name COLLATE NOCASE''',
            (room_number, cohort_code, telegram_id),
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
            "rep_score": user_row[8] or 0,
            "avatar_url": user_row[4],
            "room_number": room_number,
            "study_group": study_group_payload(user_row[6]),
            "theme_path": user_row[7],
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
            blocked_by_immunity = local_delta < 0 and try_block_penalty_with_immunity(c, target_id, f"admin_points: {reason}")
            blocked_by_implant = not blocked_by_immunity and local_delta < 0 and try_block_penalty_with_terracota(c, target_id, f"admin_points: {reason}")
            if not blocked_by_immunity and not blocked_by_implant:
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
            unlock_diary_entry(c, target_id, "first_economy")
            conn.commit()
            return {
                "full_name": row[0] or str(target_id),
                "previous_points": previous_points,
                "new_points": new_points,
                "actual_delta": actual_delta,
                "blocked_by_immunity": blocked_by_immunity,
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
    if abs(delta) > 1000:
        raise HTTPException(status_code=400, detail="Delta too large")
    if len(reason) < 3:
        raise HTTPException(status_code=400, detail="Reason required")
    requested_delta = delta

    def _run():
        conn = get_conn()
        try:
            c = conn.cursor()
            c.execute("SELECT full_name, rep_score, points FROM users WHERE telegram_id=?", (target_id,))
            row = c.fetchone()
            if not row:
                return None

            previous_rep = row[1] or 0
            c.execute(
                "UPDATE users SET rep_score = MAX(0, COALESCE(rep_score, 0) + ?) WHERE telegram_id=?",
                (delta, target_id),
            )
            c.execute("SELECT rep_score, points FROM users WHERE telegram_id=?", (target_id,))
            new_rep, points = c.fetchone()
            new_rep = new_rep or 0
            actual_delta = new_rep - previous_rep
            c.execute(
                '''INSERT INTO admin_action_logs
                   (admin_id, target_id, action_type, points_delta, reason, created_at)
                   VALUES (?, ?, 'rep_adjust', ?, ?, ?)''',
                (x_admin_id, target_id, actual_delta, reason, now_iso()),
            )
            log_economy(c, target_id, 'admin_rep', actual_delta, points or 0, x_admin_id, 'admin', reason)
            conn.commit()
            return {
                "full_name": row[0] or str(target_id),
                "previous_rep": previous_rep,
                "new_rep": new_rep,
                "points": points or 0,
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
        "previous_rep_score": result["previous_rep"],
        "new_rep_score": result["new_rep"],
        "points": result["points"],
        "delta": result["actual_delta"],
        "requested_delta": requested_delta,
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

    if delta == 0:
        raise HTTPException(status_code=400, detail="Delta must not be zero")
    if abs(delta) > 5000:
        raise HTTPException(status_code=400, detail="Delta too large")

    operation = str(data.get("operation") or "bot_manual")
    note = data.get("note")

    def _run():
        conn = get_conn()
        try:
            c = conn.cursor()
            c.execute("UPDATE users SET points = MAX(0, COALESCE(points, 0) + ?) WHERE telegram_id=?", (delta, target_id))
            c.execute("SELECT points FROM users WHERE telegram_id=?", (target_id,))
            row = c.fetchone()
            if not row:
                return None
            new_points = row[0]
            log_economy(c, target_id, operation, delta, new_points, reference_type='bot', note=note)
            unlock_diary_entry(c, target_id, "first_economy")
            conn.commit()
            return new_points
        finally:
            conn.close()

    new_points = await db_write(_run)
    if new_points is None:
        raise HTTPException(status_code=404, detail="User not found")

    return {"success": True, "telegram_id": target_id, "new_points": new_points}


@app.post("/api/gift-code/redeem")
async def redeem_gift_code(data: dict):
    try:
        telegram_id = int(data.get("telegram_id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid payload")

    code = str(data.get("code") or "").strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="Code required")

    if _gift_code_attempt_locked_out(telegram_id):
        raise HTTPException(status_code=429, detail="Too many attempts, try again later")

    def _run():
        conn = get_conn()
        try:
            c = conn.cursor()
            c.execute("SELECT reward_stars, max_uses, used_count, expires_at FROM gift_codes WHERE code=?", (code,))
            row = c.fetchone()
            if not row:
                return {"error": "Code not found", "status": 404}
            reward_stars, max_uses, used_count, expires_at = row

            expires_dt = parse_iso(expires_at)
            if expires_dt and datetime.utcnow() > expires_dt:
                return {"error": "Code expired", "status": 410}
            if used_count >= max_uses:
                return {"error": "Code exhausted", "status": 410}

            c.execute(
                "INSERT OR IGNORE INTO gift_code_redemptions (telegram_id, code, redeemed_at) VALUES (?,?,?)",
                (telegram_id, code, now_iso()),
            )
            if c.rowcount == 0:
                return {"error": "Already redeemed", "status": 409}

            c.execute("UPDATE gift_codes SET used_count = used_count + 1 WHERE code=?", (code,))
            c.execute("UPDATE users SET points = COALESCE(points, 0) + ? WHERE telegram_id=?", (reward_stars, telegram_id))
            c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
            urow = c.fetchone()
            if not urow:
                return {"error": "User not found", "status": 404}
            new_points = urow[0]
            log_economy(c, telegram_id, 'gift_code', reward_stars, new_points, reference_type='gift_code', note=code)
            conn.commit()
            return {"reward_stars": reward_stars, "new_points": new_points}
        finally:
            conn.close()

    result = await db_write(_run)
    if "error" in result:
        if result["status"] == 404:
            _gift_code_record_failed_attempt(telegram_id)
        raise HTTPException(status_code=result["status"], detail=result["error"])

    _gift_code_clear_failed_attempts(telegram_id)
    return {"success": True, "reward_stars": result["reward_stars"], "new_points": result["new_points"]}


@app.post("/api/admin/gift-code")
async def admin_create_gift_code(data: dict, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    code = str(data.get("code") or "").strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="Code required")
    try:
        reward_stars = int(data.get("reward_stars"))
        max_uses = int(data.get("max_uses") or 1)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid payload")
    if reward_stars <= 0 or max_uses <= 0:
        raise HTTPException(status_code=400, detail="Invalid values")

    expires_at = data.get("expires_at") or None
    note = data.get("note") or None
    show_at = data.get("show_at") or None

    def _run():
        conn = get_conn()
        try:
            c = conn.cursor()
            c.execute(
                '''INSERT OR REPLACE INTO gift_codes (code, reward_stars, max_uses, used_count, expires_at, created_at, note, show_at)
                   VALUES (?, ?, ?, COALESCE((SELECT used_count FROM gift_codes WHERE code=?), 0), ?, ?, ?, ?)''',
                (code, reward_stars, max_uses, code, expires_at, now_iso(), note, show_at),
            )
            conn.commit()
            return {"success": True}
        finally:
            conn.close()

    return await db_write(_run)


@app.get("/api/gift-code/active")
def get_active_gift_code():
    conn = get_conn()
    c = conn.cursor()
    now_dt = datetime.now(BEIJING_TZ)
    now = now_dt.strftime('%Y-%m-%d %H:%M:%S')
    window_end = (now_dt - timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M:%S')
    c.execute(
        "SELECT code, reward_stars, max_uses, used_count FROM gift_codes "
        "WHERE show_at IS NOT NULL AND show_at <= ? AND show_at >= ? AND used_count < max_uses "
        "AND (expires_at IS NULL OR expires_at > ?) ORDER BY show_at DESC LIMIT 1",
        (now, window_end, now)
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return {"active": False}
    return {"active": True, "code": row[0], "reward_stars": row[1], "max_uses": row[2], "used_count": row[3]}


@app.get("/api/admin/gift-code")
def admin_list_gift_codes(x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT code, reward_stars, max_uses, used_count, expires_at, created_at, note, show_at FROM gift_codes ORDER BY created_at DESC")
    rows = c.fetchall()

    return {"codes": [
        {"code": r[0], "reward_stars": r[1], "max_uses": r[2], "used_count": r[3], "expires_at": r[4], "created_at": r[5], "note": r[6], "show_at": r[7]}
        for r in rows
    ]}


@app.post("/api/admin/tianhao-fact")
async def admin_create_tianhao_fact(data: dict, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    text = str(data.get("text") or "").strip()
    show_at = data.get("show_at") or None
    if not text or not show_at:
        raise HTTPException(status_code=400, detail="text and show_at required")

    def _run():
        conn = get_conn()
        try:
            c = conn.cursor()
            c.execute(
                "INSERT INTO tianhao_facts (text, show_at, created_at) VALUES (?, ?, ?)",
                (text, show_at, now_iso()),
            )
            conn.commit()
            return {"success": True}
        finally:
            conn.close()

    return await db_write(_run)


@app.get("/api/tianhao-fact/active")
def get_active_tianhao_fact():
    conn = get_conn()
    c = conn.cursor()
    now_dt = datetime.now(BEIJING_TZ)
    now = now_dt.strftime('%Y-%m-%d %H:%M:%S')
    window_end = (now_dt - timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M:%S')
    c.execute(
        "SELECT id, text FROM tianhao_facts WHERE show_at <= ? AND show_at >= ? ORDER BY show_at DESC LIMIT 1",
        (now, window_end)
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return {"active": False}
    return {"active": True, "id": row[0], "text": row[1]}


@app.get("/api/admin/tianhao-fact")
def admin_list_tianhao_facts(x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, text, show_at, created_at FROM tianhao_facts ORDER BY show_at DESC LIMIT 50")
    rows = c.fetchall()

    return {"facts": [
        {"id": r[0], "text": r[1], "show_at": r[2], "created_at": r[3]}
        for r in rows
    ]}


@app.post("/api/admin/trip-quiz/questions")
async def admin_create_trip_quiz_question(data: dict, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    prompt = str(data.get("prompt") or "").strip()
    option_a = str(data.get("option_a") or "").strip()
    option_b = str(data.get("option_b") or "").strip()
    option_c = str(data.get("option_c") or "").strip()
    correct_option = str(data.get("correct_option") or "").strip().lower()
    explanation = str(data.get("explanation") or "").strip() or None
    if not prompt or not option_a or not option_b or not option_c:
        raise HTTPException(status_code=400, detail="prompt and all options required")
    if correct_option not in ("a", "b", "c"):
        raise HTTPException(status_code=400, detail="correct_option must be a, b or c")

    def _run():
        conn = get_conn()
        try:
            c = conn.cursor()
            c.execute(
                '''INSERT INTO trip_quiz_questions
                   (prompt, option_a, option_b, option_c, correct_option, explanation, created_by, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                (prompt, option_a, option_b, option_c, correct_option, explanation, x_admin_id, now_iso()),
            )
            conn.commit()
            return {"success": True}
        finally:
            conn.close()

    return await db_write(_run)


@app.get("/api/admin/trip-quiz/questions")
def admin_list_trip_quiz_questions(x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    conn = get_conn()
    c = conn.cursor()
    c.execute(
        '''SELECT id, prompt, option_a, option_b, option_c, correct_option, explanation, created_at
           FROM trip_quiz_questions ORDER BY created_at DESC'''
    )
    rows = c.fetchall()
    conn.close()
    return {"questions": [
        {
            "id": r[0], "prompt": r[1], "option_a": r[2], "option_b": r[3], "option_c": r[4],
            "correct_option": r[5], "explanation": r[6], "created_at": r[7],
        }
        for r in rows
    ]}


@app.delete("/api/admin/trip-quiz/questions/{question_id}")
async def admin_delete_trip_quiz_question(question_id: int, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    def _run():
        conn = get_conn()
        try:
            c = conn.cursor()
            c.execute("DELETE FROM trip_quiz_questions WHERE id=?", (question_id,))
            conn.commit()
            return {"success": True}
        finally:
            conn.close()

    return await db_write(_run)


@app.get("/api/trip-quiz/status/{telegram_id}")
def trip_quiz_status(telegram_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM trip_quiz_questions")
    question_count = c.fetchone()[0] or 0
    c.execute(
        "SELECT score, total, passed, completed_at FROM trip_quiz_attempts WHERE telegram_id=?",
        (telegram_id,),
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return {"available": question_count > 0, "attempted": False}
    return {
        "available": question_count > 0,
        "attempted": True,
        "score": row[0],
        "total": row[1],
        "passed": bool(row[2]),
        "completed_at": row[3],
    }


@app.get("/api/trip-quiz/questions/{telegram_id}")
def trip_quiz_questions(telegram_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT 1 FROM trip_quiz_attempts WHERE telegram_id=?", (telegram_id,))
    if c.fetchone():
        conn.close()
        raise HTTPException(status_code=409, detail="Quiz already completed")
    c.execute(
        "SELECT id, prompt, option_a, option_b, option_c FROM trip_quiz_questions ORDER BY id"
    )
    rows = c.fetchall()
    conn.close()
    if not rows:
        raise HTTPException(status_code=404, detail="No quiz questions configured")
    return {
        "reward": TRIP_QUIZ_REWARD_POINTS,
        "pass_ratio": TRIP_QUIZ_PASS_RATIO,
        "questions": [
            {"id": r[0], "prompt": r[1], "option_a": r[2], "option_b": r[3], "option_c": r[4]}
            for r in rows
        ],
    }


@app.post("/api/trip-quiz/submit")
async def trip_quiz_submit(data: dict):
    telegram_id = int(data.get("telegram_id") or 0)
    answers = data.get("answers") or []
    if not telegram_id:
        raise HTTPException(status_code=400, detail="telegram_id required")
    if not isinstance(answers, list) or not answers:
        raise HTTPException(status_code=400, detail="answers required")

    def _run():
        conn = get_conn()
        try:
            c = conn.cursor()
            c.execute("SELECT 1 FROM trip_quiz_attempts WHERE telegram_id=?", (telegram_id,))
            if c.fetchone():
                raise HTTPException(status_code=409, detail="Quiz already completed")
            c.execute("SELECT id, correct_option FROM trip_quiz_questions")
            correct_map = {row[0]: row[1] for row in c.fetchall()}
            if not correct_map:
                raise HTTPException(status_code=400, detail="No quiz questions configured")

            total = len(correct_map)
            score = 0
            answered_ids = set()
            for a in answers:
                qid = a.get("question_id")
                if qid in answered_ids:
                    continue
                answered_ids.add(qid)
                selected = str(a.get("selected_option") or "").strip().lower()
                if qid in correct_map and selected == correct_map[qid]:
                    score += 1

            passed = 1 if (score / total) >= TRIP_QUIZ_PASS_RATIO else 0
            completed_at = now_iso()
            c.execute(
                "INSERT INTO trip_quiz_attempts (telegram_id, score, total, passed, completed_at) VALUES (?,?,?,?,?)",
                (telegram_id, score, total, passed, completed_at),
            )

            reward = 0
            new_points = None
            if passed:
                c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (TRIP_QUIZ_REWARD_POINTS, telegram_id))
                c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
                row = c.fetchone()
                new_points = row[0] if row else None
                log_economy(c, telegram_id, "trip_quiz_reward", TRIP_QUIZ_REWARD_POINTS, new_points, None, "trip_quiz", "Факты о поездке")
                reward = TRIP_QUIZ_REWARD_POINTS

            conn.commit()
            return {
                "success": True,
                "score": score,
                "total": total,
                "passed": bool(passed),
                "reward": reward,
                "new_points": new_points,
            }
        finally:
            conn.close()

    return await db_write(_run)



@app.get("/api/admin/actions")
def admin_action_log(
    limit: int = 30,
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    safe_limit = max(1, min(int(limit or 30), 100))
    conn = get_conn()
    c = conn.cursor()
    cohort_code = resolve_viewer_cohort(c, x_admin_id, x_cohort_code)
    c.execute(
        '''SELECT l.id, l.admin_id, au.full_name, l.target_id, tu.full_name,
                  l.action_type, l.points_delta, l.reason, l.created_at
           FROM admin_action_logs l
           LEFT JOIN users au ON au.telegram_id = l.admin_id
           LEFT JOIN users tu ON tu.telegram_id = l.target_id
           WHERE COALESCE(tu.cohort_code, au.cohort_code, l.cohort_code, 'beijing')=?
           ORDER BY l.id DESC
           LIMIT ?''',
        (cohort_code, safe_limit),
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
async def start_presence_check(
    data: dict,
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    def _run():
        if x_admin_id not in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Forbidden")

        check_type = normalize_presence_check_type(data.get("check_type"))
        check_date = new_manual_presence_session() if check_type == "manual" and not data.get("check_date") else normalize_presence_date(data.get("check_date"))
        target_ids = data.get("telegram_ids")
        note = str(data.get("note") or "").strip()

        conn = get_conn()
        c = conn.cursor()
        cohort_code = resolve_viewer_cohort(c, x_admin_id, x_cohort_code)
        if target_ids:
            ids = []
            for raw_id in target_ids:
                try:
                    ids.append(int(raw_id))
                except (TypeError, ValueError):
                    continue
            ids = [
                tid for tid in ids
                if tid not in ADMIN_IDS and get_user_cohort(c, tid) == cohort_code
            ]
        else:
            placeholders = ','.join('?' * len(ADMIN_IDS))
            c.execute(
                f'''SELECT telegram_id
                    FROM users
                    WHERE telegram_id IS NOT NULL
                      AND telegram_id NOT IN ({placeholders})
                      AND cohort_code=?''',
                ADMIN_IDS + [cohort_code],
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
async def dispatch_presence_check(
    data: dict,
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
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
            cohort_code = resolve_viewer_cohort(c, x_admin_id, x_cohort_code)
            if target_ids:
                ids = []
                for raw_id in target_ids:
                    try:
                        ids.append(int(raw_id))
                    except (TypeError, ValueError):
                        continue
                ids = [
                    tid for tid in ids
                    if tid not in ADMIN_IDS and get_user_cohort(c, tid) == cohort_code
                ]
            else:
                placeholders = ','.join('?' * len(ADMIN_IDS))
                c.execute(
                    f'''SELECT telegram_id
                        FROM users
                        WHERE telegram_id IS NOT NULL
                          AND telegram_id NOT IN ({placeholders})
                          AND cohort_code=?''',
                    ADMIN_IDS + [cohort_code],
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
    # Раньше перекличка рассылалась строго последовательно — при ~90 учениках
    # это ~15-18с, всё это время админ ждёт ответа на запуск. Шлём пачками по
    # 20 параллельно с паузой между пачками (лимит Telegram ~30 msg/s).
    BATCH_SIZE = 20
    for i in range(0, len(eligible), BATCH_SIZE):
        batch = eligible[i:i + BATCH_SIZE]
        results = await asyncio.gather(
            *(send_telegram_message(tid, text, markup) for tid in batch),
            return_exceptions=True,
        )
        for tid, r in zip(batch, results):
            if isinstance(r, Exception):
                failed.append({"telegram_id": tid, "error": str(r)})
            elif isinstance(r, tuple) and r[0]:
                sent.append(tid)
            else:
                failed.append({"telegram_id": tid, "error": r[1] if isinstance(r, tuple) else "unknown"})
        if i + BATCH_SIZE < len(eligible):
            await asyncio.sleep(0.6)

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


def _presence_confirm_logic(c, telegram_id, check_type, check_date, action, note):
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
                    # Base guaranteed reward for an ordinary confirmation, independent of
                    # any card/implant bonus — kept below the weakest card bonus (Forest +8)
                    # so owning a card still feels like an upgrade over the base reward.
                    c.execute("UPDATE users SET points = points + 5 WHERE telegram_id=?", (telegram_id,))
                    c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
                    balance_after = c.fetchone()[0] or 0
                    log_economy(
                        c, telegram_id, "presence_base_reward", 5, balance_after,
                        None, "presence", f"{check_type} {check_date}",
                    )
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

            return {"check": row}


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
            result = _presence_confirm_logic(c, telegram_id, check_type, check_date, action, note)
            if "error" not in result:
                conn.commit()
            return result
        finally:
            conn.close()

    result = await db_write(_run)
    if "error" in result:
        raise HTTPException(status_code=result["status"], detail=result["error"])

    return {"success": True, "check": result["check"]}


@app.post("/api/presence/admin/mark")
async def admin_mark_presence(data: dict, x_admin_id: Optional[int] = Header(None)):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        telegram_id = int(data.get("telegram_id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid telegram_id")

    check_type = normalize_presence_check_type(data.get("check_type"))
    check_date = normalize_presence_date(data.get("check_date"))
    note = str(data.get("note") or "отметка администратором").strip()

    def _run():
        conn = get_conn()
        try:
            c = conn.cursor()
            result = _presence_confirm_logic(c, telegram_id, check_type, check_date, "confirm", note)
            if "error" in result:
                return result
            c.execute(
                '''INSERT INTO admin_action_logs
                   (admin_id, target_id, action_type, points_delta, reason, created_at)
                   VALUES (?, ?, 'presence_admin_mark', 0, ?, ?)''',
                (x_admin_id, telegram_id, f"{check_type} {check_date}: {note}", now_iso()),
            )
            conn.commit()
            return result
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
async def cancel_presence_check(
    data: dict,
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    def _run():
        if x_admin_id not in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Forbidden")

        check_type = normalize_presence_check_type(data.get("check_type"))
        reason = str(data.get("reason") or "manual cancel").strip()
        now = now_iso()

        conn = get_conn()
        c = conn.cursor()
        cohort_code = resolve_viewer_cohort(c, x_admin_id, x_cohort_code)
        check_date = str(data.get("check_date") or "").strip()
        if not check_date and check_type == "manual":
            check_date = latest_manual_presence_session(c, cohort_code) or normalize_presence_date()
        else:
            check_date = normalize_presence_date(check_date)
        c.execute(
            '''UPDATE daily_checks
               SET status='skipped',
                   note=?,
                   updated_at=?
               WHERE check_type=?
                 AND check_date=?
                 AND status IN ('pending', 'leave_requested', 'leave_rejected', 'needs_attention')
                 AND cohort_code=?''',
            (reason, now, check_type, check_date, cohort_code),
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
            if try_block_penalty_with_immunity(c, telegram_id, f"presence: {check_type} {check_date}"):
                c.execute(
                    '''UPDATE daily_checks
                       SET status='penalized',
                           penalized_at=?,
                           penalty_points=0,
                           note=TRIM(COALESCE(note, '') || ' // immunity blocked penalty'),
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
                    "blocked_by_immunity": True,
                })
                continue
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
def presence_admin_overview(
    check_type: str,
    check_date: Optional[str] = None,
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    check_type = normalize_presence_check_type(check_type)
    conn = get_conn()
    c = conn.cursor()
    cohort_code = resolve_viewer_cohort(c, x_admin_id, x_cohort_code)
    if not check_date and check_type == "manual":
        check_date = latest_manual_presence_session(c, cohort_code) or normalize_presence_date()
    else:
        check_date = normalize_presence_date(check_date)
    c.execute(
        '''SELECT dc.id, dc.check_type, dc.check_date, dc.telegram_id, u.full_name,
                  dc.status, dc.attempts_sent, dc.first_sent_at, dc.last_attempt_at,
                  dc.confirmed_at, dc.escalated_at, dc.penalized_at,
                  dc.penalty_points, dc.note, u.points, u.room_number
           FROM daily_checks dc
           LEFT JOIN users u ON u.telegram_id = dc.telegram_id
           WHERE dc.check_type=? AND dc.check_date=? AND dc.cohort_code=?
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
        (check_type, check_date, cohort_code),
    )
    checks = []
    for row in c.fetchall():
        item = serialize_presence_row(row)
        item["room_number"] = row[15] or ""
        checks.append(item)
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
def diary_admin_overview(
    entry_date: Optional[str] = None,
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    if not is_diary_staff(x_admin_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    target_date = entry_date or datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
    conn = get_conn()
    c = conn.cursor()
    cohort_code = resolve_viewer_cohort(c, x_admin_id, x_cohort_code)
    admin_placeholders = ",".join("?" for _ in ADMIN_IDS)
    c.execute(
        f'''SELECT u.telegram_id, u.full_name, de.id, de.status, de.submitted_at, de.locked_at,
                  COALESCE(ds.lesson_score, ''), COALESCE(ds.diary_score, ''),
                  COALESCE(ds.awarded_diary_points, 0), COALESCE(ds.auto_diary_points, 0),
                  ds.manual_diary_points, COALESCE(ds.validation_warnings, '[]')
           FROM users u
           LEFT JOIN diary_entries de
             ON de.telegram_id = u.telegram_id AND de.entry_date = ?
           LEFT JOIN diary_scores ds
             ON ds.entry_id = de.id
           WHERE u.telegram_id IS NOT NULL
             AND u.cohort_code=?
             AND u.telegram_id NOT IN ({admin_placeholders})
           ORDER BY u.full_name COLLATE NOCASE''',
        [target_date, cohort_code] + ADMIN_IDS,
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
def get_diary_stars_overview(
    entry_date: str,
    x_telegram_id: Optional[int] = Header(None),
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    viewer_id = x_admin_id if is_diary_staff(x_admin_id) else x_telegram_id
    if not entry_date:
        raise HTTPException(status_code=400, detail="Missing entry_date")

    placeholders = ','.join('?' * len(ADMIN_IDS))
    conn = get_conn()
    c = conn.cursor()
    cohort_code = resolve_viewer_cohort(c, viewer_id, x_cohort_code)
    c.execute(
        f'''SELECT u.telegram_id, u.full_name,
                  COALESCE(ds.stars, 0), COALESCE(ds.bonus, 0),
                  ds.rated_by, ds.rated_at
           FROM users u
           LEFT JOIN diary_stars ds
             ON ds.telegram_id = u.telegram_id AND ds.entry_date = ?
           WHERE u.telegram_id IS NOT NULL
             AND u.cohort_code=?
             AND u.telegram_id NOT IN ({placeholders})
           ORDER BY u.full_name COLLATE NOCASE''',
        [entry_date, cohort_code] + ADMIN_IDS,
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
def get_diary_stars_leaderboard(
    x_telegram_id: Optional[int] = Header(None),
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    excluded_ids = sorted(set(ADMIN_IDS) | FLATLINED_IDS)
    placeholders = ','.join('?' * len(excluded_ids))
    conn = get_conn()
    c = conn.cursor()
    viewer_id = get_request_actor_id(x_telegram_id, x_admin_id)
    cohort_code = resolve_viewer_cohort(c, viewer_id, x_cohort_code)
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
             AND u.cohort_code=?
             AND u.telegram_id NOT IN ({placeholders})
           GROUP BY u.telegram_id, u.full_name, u.avatar_url, us.theme_path
           ORDER BY total_stars DESC, days_rated DESC, total_bonus DESC, u.full_name COLLATE NOCASE''',
        [cohort_code] + excluded_ids,
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


@app.get("/api/diary/architect/{telegram_id}")
def get_architect_diary(telegram_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT entry_code, unlocked_at FROM architect_diary_unlocks WHERE telegram_id=?",
        (telegram_id,)
    )
    rows = c.fetchall()
    conn.close()
    return {
        "telegram_id": telegram_id,
        "entries": [{"entry_code": row[0], "unlocked_at": row[1]} for row in rows]
    }


class ArchitectDiaryUnlockRequest(BaseModel):
    telegram_id: int
    entry_code: str


@app.post("/api/diary/architect/unlock")
async def post_architect_diary_unlock(payload: ArchitectDiaryUnlockRequest):
    if payload.entry_code not in ARCHITECT_DIARY_CLIENT_UNLOCKABLE:
        raise HTTPException(status_code=400, detail="Entry code not client-unlockable")

    def _run():
        conn = get_conn()
        c = conn.cursor()
        unlocked = unlock_diary_entry(c, payload.telegram_id, payload.entry_code)
        conn.commit()
        conn.close()
        return unlocked

    unlocked = await db_write(_run, label="architect_diary_unlock")
    return {"success": True, "unlocked": unlocked}


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
async def get_leaderboard(
    x_telegram_id: Optional[int] = Header(None),
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
    excluded_ids = sorted(set(ADMIN_IDS) | FLATLINED_IDS)
    placeholders = ','.join('?' * len(excluded_ids))

    def _read():
        conn = get_conn()
        c = conn.cursor()
        viewer_id = get_request_actor_id(x_telegram_id, x_admin_id)
        cohort_code = resolve_viewer_cohort(c, viewer_id, x_cohort_code)
        c.execute(
            f'''SELECT u.full_name, u.rep_score, u.telegram_id, u.avatar_url, us.theme_path,
                     CASE WHEN us.title_date=? THEN 1 ELSE 0 END as has_title,
                     us.equipped_frame,
                     CASE WHEN us.title_date=? THEN us.title_style ELSE NULL END as title_style,
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
                     AND u.cohort_code=?
                     AND u.telegram_id NOT IN ({placeholders})
                     ORDER BY u.rep_score DESC, u.rowid ASC''',
            [today, today, cohort_code] + excluded_ids,
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

        c.execute(
            '''SELECT 1 FROM leaderboard_snapshots ls
               JOIN users u ON u.telegram_id=ls.telegram_id
               WHERE ls.snapshot_date=? AND u.cohort_code=? LIMIT 1''',
            (today, cohort_code),
        )
        has_today_snapshot = c.fetchone() is not None
        conn.close()
        return result, prev_ranks, has_today_snapshot

    result, prev_ranks, has_today_snapshot = await db_read(_read, label="leaderboard")

    if not has_today_snapshot:
        def _snapshot():
            conn2 = get_conn()
            try:
                c2 = conn2.cursor()
                c2.execute(
                    f'''INSERT OR IGNORE INTO leaderboard_snapshots (telegram_id, rank, rep, snapshot_date)
                        SELECT telegram_id, ROW_NUMBER() OVER (ORDER BY rep_score DESC, rowid ASC), rep_score, ?
                        FROM users
                        WHERE telegram_id IS NOT NULL
                          AND cohort_code=?
                          AND telegram_id NOT IN ({placeholders})
                          AND rep_score > 0''',
                    [today, cohort_code] + excluded_ids,
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
            "title_style": r[7] if r[7] in TITLE_STYLE_IDS else None,
            "implant": r[8],
            "card": r[9],
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
async def get_user_achievements(telegram_id: int):
    def _read():
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT code, name, description, icon, secret FROM achievements")
        all_achievements = c.fetchall()
        c.execute("SELECT achievement_code, earned_at FROM user_achievements WHERE telegram_id=?", (telegram_id,))
        earned = {row[0]: row[1] for row in c.fetchall()}
        conn.close()
        return all_achievements, earned
    all_achievements, earned = await db_read(_read, label="achievements")

    if "legend" not in earned:
        def _check_legend():
            conn2 = get_conn()
            c2 = conn2.cursor()
            try:
                c2.execute("SELECT rep_score FROM users WHERE telegram_id=?", (telegram_id,))
                row = c2.fetchone()
                rep_score = (row[0] or 0) if row else 0
                if rep_score >= 600 and award_achievement(c2, telegram_id, "legend"):
                    conn2.commit()
                    return datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
                return None
            finally:
                conn2.close()
        legend_earned_at = await db_write(_check_legend)
        if legend_earned_at:
            earned["legend"] = legend_earned_at

    # Admins see every achievement as earned — purely cosmetic display
    # override, same as the frame unlock; doesn't write to user_achievements
    # or affect real progress/economy.
    is_admin_view = telegram_id in ADMIN_IDS

    result = []
    for code, name, description, icon, secret in all_achievements:
        is_earned = code in earned or is_admin_view
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
            granted = award_achievement(c, telegram_id, code)
            conn.commit()
            conn.close()
            if granted:
                return {"success": True}
            return {"success": False, "detail": "Already earned"}
        except Exception:
            conn.close()
            return {"success": False, "detail": "Error"}
    return await db_write(_run)

@app.get("/api/user/scans/{telegram_id}")
def get_user_scans(telegram_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT scan_attempts FROM user_status WHERE telegram_id=?", (telegram_id,))
    row = c.fetchone()
    conn.close()
    return {
        "scan_attempts": row[0] if row else 0,
    }

@app.post("/api/casino/open")
async def open_case(data: dict):
    telegram_id = data.get("telegram_id")
    if not telegram_id:
        raise HTTPException(status_code=400, detail="No telegram_id")

    case_type = random.choices(['gold', 'purple', 'black'], weights=[848, 150, 2], k=1)[0]
    if case_type == 'gold':
        prizes = [
            {"code": "empty",   "name": "Пустая миска риса", "points": 0,   "weight": 40, "icon": "🍚", "case_type": "gold"},
            {"code": "small",   "name": "+30 баллов",         "points": 30,  "weight": 24, "icon": "⭐", "case_type": "gold"},
            {"code": "medium",  "name": "+60 баллов",         "points": 60,  "weight": 12, "icon": "💫", "case_type": "gold"},
            {"code": "walk",    "name": "+30 мин свободы",    "points": 0,   "weight": 8,  "icon": "🕐", "case_type": "gold"},
            {"code": "fate_guard", "name": "Гарант судьбы",       "points": 0,   "weight": 10, "icon": "🔁", "case_type": "gold"},
            {"code": "scan",    "name": "+1 попытка",         "points": 0,   "weight": 5,  "icon": "🎲", "case_type": "gold"},
            {"code": "jackpot", "name": "ДЖЕКПОТ! +100★",     "points": 100, "weight": 1,  "icon": "👑", "case_type": "gold"},
        ]
    elif case_type == 'purple':
        prizes = [
            {"code": "implant_guanxi",     "name": "Имплант Гуаньси 关系",      "points": 0, "weight": 68, "icon": "🤝", "case_type": "purple"},
            {"code": "implant_panda",      "name": "Имплант Панда 🐼",          "points": 0, "weight": 64, "icon": "🐼", "case_type": "purple"},
            {"code": "implant_shaolin",    "name": "Имплант Шаолинь 少林",      "points": 0, "weight": 62, "icon": "🥋", "case_type": "purple"},
            {"code": "implant_linguasoft", "name": "Имплант Linguasoft 口才",   "points": 0, "weight": 60, "icon": "🎙", "case_type": "purple"},
            {"code": "implant_caishen",    "name": "Имплант Цайшэнь 财神",      "points": 0, "weight": 75, "icon": "💰", "case_type": "purple"},
            {"code": "implant_qilin",      "name": "Имплант Цилинь 麒麟",       "points": 0, "weight": 85, "icon": "🐉", "case_type": "purple"},
        ]
    else:
        prizes = [
            {"code": "implant_red_dragon", "name": "Протокол Красный Дракон 红龙", "points": 0, "weight": 1, "icon": "🐉", "case_type": "black"},
            {"code": "implant_terracota",  "name": "Имплант Терракота 兵马俑",     "points": 0, "weight": 1, "icon": "🗿", "case_type": "black"},
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
                c.execute("""INSERT INTO user_status (telegram_id, scan_attempts) VALUES (?,0)
                             ON CONFLICT(telegram_id) DO UPDATE SET
                               scan_attempts = MAX(0, scan_attempts - 1)""", (telegram_id,))

            selected_prize = dict(prize)
            fate_guard_used = False
            if selected_prize["code"] == "empty":
                c.execute("SELECT fate_guard FROM user_status WHERE telegram_id=?", (telegram_id,))
                guard_row = c.fetchone()
                if guard_row and (guard_row[0] or 0) > 0:
                    c.execute("""UPDATE user_status
                                 SET fate_guard=MAX(0, COALESCE(fate_guard,0)-1)
                                 WHERE telegram_id=?""", (telegram_id,))
                    reroll_prizes = [p for p in prizes if p["code"] != "empty"]
                    selected_prize = dict(random.choices(reroll_prizes, weights=[p["weight"] for p in reroll_prizes], k=1)[0])
                    selected_prize["name"] = f'Гарант судьбы → {selected_prize["name"]}'
                    fate_guard_used = True

            if selected_prize["code"] == "fate_guard":
                c.execute("""INSERT INTO user_status (telegram_id, fate_guard) VALUES (?,1)
                             ON CONFLICT(telegram_id) DO UPDATE SET fate_guard=COALESCE(fate_guard,0)+1""", (telegram_id,))
            elif selected_prize["code"] == "scan":
                c.execute("""INSERT INTO user_status (telegram_id, scan_attempts) VALUES (?,1)
                             ON CONFLICT(telegram_id) DO UPDATE SET scan_attempts=MIN(7, scan_attempts+1)""", (telegram_id,))
            elif selected_prize["code"] == "walk":
                expires = now_beijing.strftime('%Y-%m-%d') + ' 22:00:00'
                c.execute("INSERT INTO shop_purchases (telegram_id, item_code, purchased_at, status, expires_at) VALUES (?,?,?,?,?)", (telegram_id, 'casino_walk', now_str, 'active', expires))
            elif selected_prize["code"].startswith("implant_"):
                c.execute("INSERT INTO user_implants (telegram_id, implant_id, durability, obtained_at) VALUES (?,?,3,?)", (telegram_id, selected_prize["code"], now_str))
            c.execute("SELECT double_win FROM user_status WHERE telegram_id=?", (telegram_id,))
            dw_row = c.fetchone()
            dw_active = bool(dw_row and dw_row[0])
            doubled_win = False
            if selected_prize.get("points", 0) > 0:
                if dw_active:
                    selected_prize["points"] *= 2
                    selected_prize["name"] = f'{selected_prize["name"]} ×2'
                    doubled_win = True
                    c.execute("UPDATE user_status SET double_win=0 WHERE telegram_id=?", (telegram_id,))
                c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (selected_prize["points"], telegram_id))

            c.execute("INSERT INTO casino_log (telegram_id, date, prize, created_at) VALUES (?,?,?,?)", (telegram_id, today, selected_prize["code"], now_str))
            c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
            new_points = c.fetchone()[0]
            c.execute("SELECT scan_attempts FROM user_status WHERE telegram_id=?", (telegram_id,))
            scan_row = c.fetchone()
            log_economy(c, telegram_id, 'case_open', 0, new_points, None, selected_prize.get("case_type") or "case", selected_prize.get("name") or selected_prize.get("code"))
            if fate_guard_used:
                log_economy(c, telegram_id, 'fate_guard_consumed', 0, new_points, None, "case", "Гарант судьбы")

            diary_unlocked = []
            if unlock_diary_entry(c, telegram_id, "first_spin"):
                diary_unlocked.append("first_spin")
            if selected_prize["code"].startswith("implant_"):
                if unlock_diary_entry(c, telegram_id, "first_item"):
                    diary_unlocked.append("first_item")

            award_achievement(c, telegram_id, "gambler")
            if selected_prize["code"] in ("jackpot", "implant_red_dragon"):
                award_achievement(c, telegram_id, "lucky")
            if selected_prize["code"] == "implant_red_dragon":
                award_achievement(c, telegram_id, "dragon")
            if doubled_win:
                log_economy(c, telegram_id, 'double_win_consumed', 0, new_points, None, "shop_item", "Двойной сигнал")
            conn.commit()
            return {
                "prize": selected_prize,
                "new_points": new_points,
                "scan_attempts": scan_row[0] if scan_row else 0,
                "doubled_win": doubled_win,
                "fate_guard_used": fate_guard_used,
                "diary_unlocked": diary_unlocked,
            }
        finally:
            conn.close()

    result = await db_write(_run)
    if "error" in result:
        raise HTTPException(status_code=result["status"], detail=result["error"])

    return {
        "prize": result["prize"],
        "new_points": result["new_points"],
        "scan_attempts": result["scan_attempts"],
        "doubled_win": result["doubled_win"],
        "fate_guard_used": result["fate_guard_used"],
        "diary_unlocked": result["diary_unlocked"],
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
        "fate_guard": {"name": "Гарант судьбы", "icon": "🔁"},
        "scan": {"name": "+1 попытка", "icon": "🎲"},
        "jackpot": {"name": "ДЖЕКПОТ! +100!", "icon": "👑"},
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
        "🔴 NetWatch активировал «Взлом Файрвола».\n"
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
        c.execute("UPDATE users SET points = points + 50 WHERE telegram_id=?", (telegram_id,))
        c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
        new_points = c.fetchone()[0]
        log_economy(c, telegram_id, 'implant_disassemble', 50, new_points, implant_id, 'implant', implant_type)
        conn.commit()
        conn.close()
        return {"success": True, "refund": 50, "new_points": new_points}
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
def get_shop(
    telegram_id: int = 0,
    x_telegram_id: Optional[int] = Header(None),
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    today = shop_day_str()
    conn = get_conn()
    c = conn.cursor()
    actor_id = get_request_actor_id(x_telegram_id, x_admin_id) or telegram_id
    cohort_code = resolve_viewer_cohort(c, actor_id, x_cohort_code)
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
        c.execute(
            "SELECT count FROM shop_daily_counts_cohort WHERE item_code=? AND date=? AND cohort_code=?",
            (code, today, cohort_code),
        )
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
    title_style = data.get("style") if data.get("style") in TITLE_STYLE_IDS else TITLE_STYLE_DEFAULT
    if not telegram_id or not item_code:
        raise HTTPException(status_code=400, detail="Missing data")

    def _run():
        today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
        shop_day = shop_day_str()
        conn = get_conn()
        try:
            c = conn.cursor()
            cohort_code = get_user_cohort(c, telegram_id)
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
                c.execute(
                    "SELECT count FROM shop_daily_counts_cohort WHERE item_code=? AND date=? AND cohort_code=?",
                    (item_code, shop_day, cohort_code),
                )
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
                c.execute("""INSERT INTO user_status (telegram_id, title_date, title_style) VALUES (?,?,?)
                             ON CONFLICT(telegram_id) DO UPDATE SET title_date=?, title_style=?""",
                          (telegram_id, today, title_style, today, title_style))

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
            c.execute(
                """INSERT INTO shop_daily_counts_cohort (item_code, date, cohort_code, count)
                   VALUES (?,?,?,1)
                   ON CONFLICT(item_code, date, cohort_code) DO UPDATE SET count=count+1""",
                (item_code, shop_day, cohort_code),
            )
            c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
            new_points = c.fetchone()[0]
            log_economy(c, telegram_id, 'shop_purchase', -price, new_points, None, 'shop_item', name)
            diary_unlocked = []
            if unlock_diary_entry(c, telegram_id, "first_shop_tx"):
                diary_unlocked.append("first_shop_tx")
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
                "diary_unlocked": diary_unlocked,
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
        "diary_unlocked": result["diary_unlocked"],
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
    c.execute("SELECT cohort_code FROM users WHERE telegram_id=?", (caller_id,))
    caller_row = c.fetchone()
    if not caller_row:
        conn.close()
        raise HTTPException(status_code=403, detail="Unknown caller")
    cohort_code = normalize_cohort_code(caller_row[0])
    query = str(q or "").strip()
    if query:
        like = f"%{query}%"
        c.execute(
            '''SELECT telegram_id, full_name, avatar_url, points
               FROM users
               WHERE telegram_id IS NOT NULL AND telegram_id != ?
                 AND cohort_code=?
                 AND (full_name LIKE ? OR CAST(telegram_id AS TEXT) LIKE ?)
               ORDER BY full_name COLLATE NOCASE
               LIMIT 15''',
            (caller_id, cohort_code, like, like),
        )
    else:
        c.execute(
            '''SELECT telegram_id, full_name, avatar_url, points
               FROM users
               WHERE telegram_id IS NOT NULL AND telegram_id != ?
                 AND cohort_code=?
               ORDER BY full_name COLLATE NOCASE
               LIMIT 20''',
            (caller_id, cohort_code),
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
        try:
            c = conn.cursor()
            c.execute("SELECT item_code FROM shop_purchases WHERE id=? AND telegram_id=? AND status='active'", (purchase_id, from_id))
            purchase = c.fetchone()
            if not purchase:
                raise HTTPException(status_code=404, detail="Purchase not found")
            if purchase[0] == 'amnesty':
                raise HTTPException(status_code=400, detail="Cannot gift amnesty")
            if from_id not in ADMIN_IDS:
                c.execute(
                    """SELECT COUNT(*) FROM shop_purchases
                       WHERE given_to=? AND date(gifted_at)=?""",
                    (from_id, today),
                )
                gifts_today = c.fetchone()[0] or 0
                if gifts_today >= SHOP_GIFT_DAILY_LIMIT:
                    raise HTTPException(status_code=400, detail="Daily gift limit reached")
            c.execute("SELECT points FROM users WHERE telegram_id=?", (from_id,))
            user = c.fetchone()
            fox_gift_trick = (
                has_active_card(c, from_id, "card_fox")
                and not has_used_card_today(c, from_id, "card_fox", "gift_tax_trick", today)
            )
            gift_tax = 15 if fox_gift_trick else 20
            if not user or (user[0] or 0) < gift_tax:
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
            diary_unlocked = []
            if unlock_diary_entry(c, from_id, "first_shop_tx"):
                diary_unlocked.append("first_shop_tx")
            award_achievement(c, from_id, "helper")
            conn.commit()
            return {"success": True, "diary_unlocked": diary_unlocked}
        finally:
            conn.close()
    return await db_write(_run)


@app.post("/api/shop/sell")
async def sell_item(data: dict):
    def _run():
        purchase_id = data.get("purchase_id")
        telegram_id = data.get("telegram_id")
        conn = get_conn()
        try:
            c = conn.cursor()
            c.execute("""SELECT sp.item_code, si.price FROM shop_purchases sp
                         JOIN shop_items si ON sp.item_code = si.code
                         WHERE sp.id=? AND sp.telegram_id=? AND sp.status='active'""", (purchase_id, telegram_id))
            purchase = c.fetchone()
            if not purchase:
                raise HTTPException(status_code=404, detail="Not found")
            if purchase[0] == 'amnesty':
                raise HTTPException(status_code=400, detail="Cannot sell amnesty")
            sell_rate = 0.6 if has_active_implant(c, telegram_id, "implant_panda") else 0.5
            refund = int(purchase[1] * sell_rate)
            c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (refund, telegram_id))
            c.execute("UPDATE shop_purchases SET status='sold' WHERE id=?", (purchase_id,))
            c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
            new_points = c.fetchone()[0]
            log_economy(c, telegram_id, 'shop_refund', refund, new_points, purchase_id, 'shop_item', purchase[0])
            diary_unlocked = []
            if unlock_diary_entry(c, telegram_id, "first_shop_tx"):
                diary_unlocked.append("first_shop_tx")
            conn.commit()
            return {"success": True, "refund": refund, "new_points": new_points, "sell_rate": sell_rate, "diary_unlocked": diary_unlocked}
        finally:
            conn.close()
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

        extra = {}
        if item_code == 'amnesty':
            target_id = data.get("target_id")
            if not target_id:
                conn.close()
                raise HTTPException(status_code=400, detail="target_id required")
            target_id = int(target_id)
            if target_id == telegram_id:
                conn.close()
                raise HTTPException(status_code=400, detail="Cannot target yourself")
            c.execute("SELECT full_name FROM users WHERE telegram_id=?", (target_id,))
            target_row = c.fetchone()
            if not target_row:
                conn.close()
                raise HTTPException(status_code=404, detail="Target not found")
            today_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
            c.execute(
                '''SELECT id, operation, amount, note
                   FROM economy_log
                   WHERE telegram_id=? AND amount < 0
                     AND operation IN ('presence_penalty', 'admin_points', 'bot_penalize')
                     AND created_at >= ?
                     AND NOT EXISTS (
                       SELECT 1 FROM economy_log resets
                       WHERE resets.operation='amnesty_reset'
                         AND resets.reference_id=economy_log.id
                     )
                   ORDER BY created_at DESC LIMIT 1''',
                (target_id, today_str),
            )
            penalty_row = c.fetchone()
            if not penalty_row:
                conn.close()
                raise HTTPException(status_code=404, detail="No eligible penalty for today found")
            penalty_id, operation, amount, note = penalty_row
            refund = abs(amount)
            c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (refund, target_id))
            c.execute("SELECT points FROM users WHERE telegram_id=?", (target_id,))
            target_balance = c.fetchone()[0] or 0
            log_economy(c, target_id, "amnesty_reset", refund, target_balance, penalty_id, "shop_item", note or operation)
            extra = {"target_name": target_row[0], "refunded": refund, "target_id": target_id}

        c.execute("UPDATE shop_purchases SET status='used' WHERE id=?", (purchase_id,))

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
    result = await db_write(_run)
    if result.get("target_id"):
        await send_telegram_message(
            int(result["target_id"]),
            f"🤝 АМНИСТИЯ\n\nС тебя сняли штраф на {result['refunded']}★ по согласованию.",
        )
    return result

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
async def reset_shop(
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    def _run():
        if x_admin_id not in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Forbidden")
        today = shop_day_str()
        conn = get_conn()
        c = conn.cursor()
        cohort_code = resolve_viewer_cohort(c, x_admin_id, x_cohort_code)
        c.execute(
            "DELETE FROM shop_daily_counts_cohort WHERE date=? AND cohort_code=?",
            (today, cohort_code),
        )
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

    def _run():
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT full_name FROM users WHERE telegram_id=?", (telegram_id,))
        result = c.fetchone()
        name = result[0] if result else str(telegram_id)
        now_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
        c.execute(
            '''INSERT INTO anon_questions (telegram_id, full_name, username, text, created_at)
               VALUES (?, ?, ?, ?, ?)''',
            (telegram_id, name, '', question, now_str),
        )
        question_id = c.lastrowid
        conn.commit()
        conn.close()
        return question_id, name

    question_id, name = await db_write(_run)
    reply_markup = {
        "inline_keyboard": [[
            {"text": "✉️ Ответить", "callback_data": f"anon_reply:{question_id}"}
        ]]
    }
    for admin_id in ADMIN_IDS:
        if admin_id <= 0:
            continue
        await send_telegram_message(
            admin_id,
            f"🤫 Вопрос #{question_id}\n👤 От: {name}\n\n{question}",
            reply_markup=reply_markup,
        )
    return {"success": True, "question_id": question_id}


def get_wild_ai_breach_state(c, cohort_code: str) -> dict:
    """Returns the current cohort's Wild AI Breach state."""
    cohort_code = normalize_cohort_code(cohort_code)
    until_raw = get_cohort_setting(c, 'breach_until', cohort_code, '')
    until = parse_iso(until_raw) if until_raw else None

    if until and datetime.utcnow() >= until:
        set_cohort_setting(c, 'breach_until', '', cohort_code)
        set_cohort_setting(c, 'breach_seed', '', cohort_code)
        set_cohort_setting(c, 'blackwall', '0', cohort_code)
        return {"breach_active": False, "breach_until": None, "breach_seed": None, "breach_phrase": None}

    if not until:
        return {"breach_active": False, "breach_until": None, "breach_seed": None, "breach_phrase": None}

    seed_raw = get_cohort_setting(c, 'breach_seed', cohort_code, '0')
    seed = int(seed_raw or 0)
    hours_elapsed = int(
        (datetime.utcnow() - (until - timedelta(days=WILD_AI_BREACH_DURATION_DAYS))).total_seconds() // 3600
    )
    phrase_index = (seed + hours_elapsed // WILD_AI_BREACH_PHRASE_ROTATE_HOURS) % len(WILD_AI_BREACH_PHRASES)

    return {
        "breach_active": True,
        "breach_until": until.isoformat(),
        "breach_seed": seed,
        "breach_phrase": WILD_AI_BREACH_PHRASES[phrase_index],
    }


@app.get("/api/settings")
async def get_settings(
    x_telegram_id: Optional[int] = Header(None),
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    def _run():
        conn = get_conn()
        c = conn.cursor()
        cohort_code = resolve_viewer_cohort(
            c, get_request_actor_id(x_telegram_id, x_admin_id), x_cohort_code
        )
        breach = get_wild_ai_breach_state(c, cohort_code)
        result = {
            "cohort_code": cohort_code,
            "blackwall": get_cohort_setting(c, 'blackwall', cohort_code, '0') == '1',
            "architect_event": get_cohort_setting(c, 'architect_event', cohort_code, '0') == '1',
            "wildai_event": get_cohort_setting(c, 'wildai_event', cohort_code, '0') == '1',
            "mju_event": get_cohort_setting(c, 'mju_event', cohort_code, '0') == '1',
            **breach,
        }
        conn.commit()
        conn.close()
        return result
    return await db_write(_run)

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
async def toggle_blackwall(data: dict, x_admin_id: Optional[int] = Header(None), x_cohort_code: Optional[str] = Header(None)):
    def _run():
        if x_admin_id not in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Forbidden")
        enabled = data.get("enabled", False)
        conn = get_conn()
        c = conn.cursor()
        cohort_code = resolve_viewer_cohort(c, x_admin_id, x_cohort_code)
        set_cohort_setting(c, 'blackwall', '1' if enabled else '0', cohort_code)
        c.execute(
            '''INSERT INTO admin_action_logs
               (admin_id, target_id, action_type, points_delta, reason, created_at, cohort_code)
               VALUES (?, NULL, 'blackwall', 0, ?, ?, ?)''',
            (x_admin_id, 'Red Firewall enabled' if enabled else 'Red Firewall disabled', now_iso(), cohort_code),
        )
        conn.commit()
        conn.close()
        return {"success": True, "blackwall": enabled}
    return await db_write(_run)


@app.post("/api/admin/wildai-breach")
async def toggle_wildai_breach(data: dict, x_admin_id: Optional[int] = Header(None), x_cohort_code: Optional[str] = Header(None)):
    def _run():
        if x_admin_id not in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Forbidden")
        enabled = data.get("enabled", False)
        conn = get_conn()
        c = conn.cursor()
        cohort_code = resolve_viewer_cohort(c, x_admin_id, x_cohort_code)
        if enabled:
            # TEMPORARY (2026-06-25): broadcast disabled during testing so manual
            # toggles don't spam every user. Set back to default (omit the
            # argument, or pass True) once testing is done.
            activate_wildai_breach(c, admin_id=x_admin_id, reason='Wild AI Breach enabled (manual)', send_broadcast=False, cohort_code=cohort_code)
        else:
            set_cohort_setting(c, 'breach_until', '', cohort_code)
            set_cohort_setting(c, 'breach_seed', '', cohort_code)
            set_cohort_setting(c, 'blackwall', '0', cohort_code)
            c.execute(
                '''INSERT INTO admin_action_logs
                   (admin_id, target_id, action_type, points_delta, reason, created_at, cohort_code)
                   VALUES (?, NULL, 'wildai_breach', 0, ?, ?, ?)''',
                (x_admin_id, 'Wild AI Breach disabled', now_iso(), cohort_code),
            )
        conn.commit()
        conn.close()
        return {"success": True, "breach_active": enabled}
    return await db_write(_run)


@app.post("/api/admin/architect-event")
async def toggle_architect_event(data: dict, x_admin_id: Optional[int] = Header(None), x_cohort_code: Optional[str] = Header(None)):
    def _run():
        if x_admin_id not in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Forbidden")
        enabled = bool(data.get("enabled", False))
        conn = get_conn()
        c = conn.cursor()
        cohort_code = resolve_viewer_cohort(c, x_admin_id, x_cohort_code)
        set_cohort_setting(c, 'architect_event', '1' if enabled else '0', cohort_code)
        c.execute(
            '''INSERT INTO admin_action_logs
               (admin_id, target_id, action_type, points_delta, reason, created_at, cohort_code)
               VALUES (?, NULL, 'architect_event', 0, ?, ?, ?)''',
            (x_admin_id, 'Architect event enabled' if enabled else 'Architect event disabled', now_iso(), cohort_code),
        )
        conn.commit()
        conn.close()
        return {"success": True, "architect_event": enabled}
    return await db_write(_run)


@app.post("/api/admin/wildai-event")
async def toggle_wildai_event(data: dict, x_admin_id: Optional[int] = Header(None), x_cohort_code: Optional[str] = Header(None)):
    def _run():
        if x_admin_id not in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Forbidden")
        enabled = bool(data.get("enabled", False))
        conn = get_conn()
        c = conn.cursor()
        cohort_code = resolve_viewer_cohort(c, x_admin_id, x_cohort_code)
        set_cohort_setting(c, 'wildai_event', '1' if enabled else '0', cohort_code)
        c.execute(
            '''INSERT INTO admin_action_logs
               (admin_id, target_id, action_type, points_delta, reason, created_at, cohort_code)
               VALUES (?, NULL, 'wildai_event', 0, ?, ?, ?)''',
            (x_admin_id, 'Wild AI event enabled' if enabled else 'Wild AI event disabled', now_iso(), cohort_code),
        )
        conn.commit()
        conn.close()
        return {"success": True, "wildai_event": enabled}
    return await db_write(_run)


@app.post("/api/admin/mju-event")
async def toggle_mju_event(data: dict, x_admin_id: Optional[int] = Header(None), x_cohort_code: Optional[str] = Header(None)):
    def _run():
        if x_admin_id not in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Forbidden")
        enabled = bool(data.get("enabled", False))
        conn = get_conn()
        c = conn.cursor()
        cohort_code = resolve_viewer_cohort(c, x_admin_id, x_cohort_code)
        set_cohort_setting(c, 'mju_event', '1' if enabled else '0', cohort_code)
        c.execute(
            '''INSERT INTO admin_action_logs
               (admin_id, target_id, action_type, points_delta, reason, created_at, cohort_code)
               VALUES (?, NULL, 'mju_event', 0, ?, ?, ?)''',
            (x_admin_id, 'MJU event enabled' if enabled else 'MJU event disabled', now_iso(), cohort_code),
        )
        conn.commit()
        conn.close()
        return {"success": True, "mju_event": enabled}
    return await db_write(_run)


@app.get("/api/raid/status")
def get_raid_status(
    telegram_id: int = 0,
    x_telegram_id: Optional[int] = Header(None),
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
    conn = get_conn()
    c = conn.cursor()
    actor_id = get_request_actor_id(x_telegram_id, x_admin_id) or telegram_id
    cohort_code = resolve_viewer_cohort(c, actor_id, x_cohort_code)
    finished_today = public_finished_raid_count(c, today, cohort_code)
    extra_raids = 0 if telegram_id in ADMIN_IDS else (get_extra_raids(c, telegram_id) if telegram_id else 0)
    user_attempts = 0 if telegram_id in ADMIN_IDS else (user_raid_attempt_count(c, today, telegram_id, cohort_code) if telegram_id else 0)
    base_remaining = max(0, RAID_USER_DAILY_LIMIT - user_attempts)
    if finished_today >= RAID_DAILY_LIMIT:
        base_remaining = 0
    remaining_today = 999 if telegram_id in ADMIN_IDS else base_remaining + extra_raids
    raid = latest_visible_raid(c, today, telegram_id, cohort_code)
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

        cohort_code = get_user_cohort(c, telegram_id)
        finished_count = public_finished_raid_count(c, today, cohort_code)
        extra_raids = 0 if telegram_id in ADMIN_IDS else get_extra_raids(c, telegram_id)
        user_attempts = 0 if telegram_id in ADMIN_IDS else user_raid_attempt_count(c, today, telegram_id, cohort_code)
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
                     WHERE r.date=? AND r.status='open' AND r.cohort_code=?
                     AND r.id NOT IN (SELECT raid_id FROM raid_participants WHERE telegram_id=?)
                     LIMIT 1""", (today, cohort_code, telegram_id))
        raid = c.fetchone()
        if not raid:
            c.execute(
                "INSERT INTO raids (date, created_at, cohort_code) VALUES (?,?,?)",
                (today, now_str, cohort_code),
            )
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
                "SELECT option_a, option_b, option_c, correct_option FROM event_questions WHERE id=? AND event_code='raid'",
                (int(question_id),),
            )
            q_row = c.fetchone()
            if q_row and is_shuffled_answer_correct(
                answer,
                q_row[3],
                q_row[0],
                q_row[1],
                q_row[2],
                "raid",
                datetime.now(BEIJING_TZ).strftime('%Y-%m-%d'),
                int(question_id),
            ):
                answer_correct = 1
        c.execute(
            "UPDATE raid_participants SET answer_correct=? WHERE raid_id=? AND telegram_id=?",
            (answer_correct, raid_id, telegram_id),
        )

        c.execute("UPDATE users SET points = points - ? WHERE telegram_id=?", (RAID_ENTRY_COST, telegram_id))
        c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
        raid_entry_balance = c.fetchone()[0] or 0
        log_economy(c, telegram_id, 'raid_entry', -RAID_ENTRY_COST, raid_entry_balance, raid_id, 'raid', f"Raid {today}")
        diary_unlocked = []
        if unlock_diary_entry(c, telegram_id, "first_raid"):
            diary_unlocked.append("first_raid")
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
        finished_today = public_finished_raid_count(c, today, cohort_code)
        attempts_today = 0 if telegram_id in ADMIN_IDS else user_raid_attempt_count(c, today, telegram_id, cohort_code)
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
            "diary_unlocked": diary_unlocked,
            "points_change": ((RAID_SUCCESS_REWARD - RAID_ENTRY_COST) if (launched and result == 'success') else -RAID_ENTRY_COST) + card_raid_bonus,
            "message": (
                f"🏆 РЕЙД УСПЕШЕН! +{RAID_SUCCESS_REWARD}★ каждому!" if (launched and result == 'success') else
                "🛡 АЛЬФАБОСС ЗАЩИТИЛСЯ! Ставки сгорели 🔥" if (launched and result == 'defended') else
                f"⚔️ Ты в отряде! Бойцов: {count}/{RAID_MIN_PLAYERS}"
            ),
        }
    return await db_write(_run)


@app.get("/api/raid/question")
def get_raid_question(
    telegram_id: int = 0,
    x_telegram_id: Optional[int] = Header(None),
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    conn = get_conn()
    c = conn.cursor()
    actor_id = get_request_actor_id(x_telegram_id, x_admin_id) or telegram_id
    cohort_code = resolve_viewer_cohort(c, actor_id, x_cohort_code)
    today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
    day_seed = int(datetime.now(BEIJING_TZ).strftime('%Y%m%d'))
    c.execute("SELECT COUNT(*) FROM event_questions WHERE event_code='raid' AND action_type='scan'")
    total_questions = c.fetchone()[0] or 0
    if total_questions <= 0:
        conn.close()
        raise HTTPException(status_code=404, detail="No raid questions available")
    c.execute(
        '''SELECT COUNT(*)
           FROM raid_participants rp
           JOIN raids r ON r.id = rp.raid_id
           WHERE r.date=? AND r.cohort_code=?''',
        (today, cohort_code),
    )
    daily_offset = (c.fetchone()[0] or 0) % total_questions
    c.execute(
        '''SELECT id, prompt, option_a, option_b, option_c, difficulty
           FROM event_questions
           WHERE event_code='raid' AND action_type='scan'
           ORDER BY ((id * 1103515245 + ?) % 2147483647), id
           LIMIT 1 OFFSET ?''',
        (day_seed, daily_offset),
    )
    row = c.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="No raid questions available")
    options, _ = shuffled_question_options(
        row[2],
        row[3],
        row[4],
        "raid",
        today,
        int(row[0]),
    )
    return {
        "id": row[0],
        "prompt": row[1],
        "option_a": options["a"],
        "option_b": options["b"],
        "option_c": options["c"],
        "difficulty": row[5],
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
        'weight': 848,
        'items': [
            {'type': 'empty', 'weight': 40},
            {'type': 'points', 'amount': 30, 'weight': 24},
            {'type': 'points', 'amount': 60, 'weight': 12},
            {'type': 'walk', 'weight': 8},
            {'type': 'fate_guard', 'weight': 10},
            {'type': 'scan', 'weight': 5},
        ],
    },
    'purple': {
        'weight': 150,
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
        'weight': 2,
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
            c.execute("""INSERT INTO user_status (telegram_id, scan_attempts) VALUES (?,0)
                         ON CONFLICT(telegram_id) DO UPDATE SET
                           scan_attempts=MAX(0, scan_attempts-1)""", (telegram_id,))
        else:
            c.execute("SELECT scan_attempts FROM user_status WHERE telegram_id=?", (telegram_id,))
            status_row = c.fetchone()

        pool_name = random.choices(['blue', 'purple', 'gold'], weights=[848, 150, 2])[0]
        pool = GENSHIN_POOL[pool_name]
        item = random.choices(pool['items'], weights=[it['weight'] for it in pool['items']])[0]
        today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
        now_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
        result = {}

        c.execute("SELECT double_win FROM user_status WHERE telegram_id=?", (telegram_id,))
        dw_row = c.fetchone()
        dw_active = bool(dw_row and dw_row[0])
        fate_guard_used = False
        if item['type'] == 'empty':
            c.execute("SELECT fate_guard FROM user_status WHERE telegram_id=?", (telegram_id,))
            guard_row = c.fetchone()
            if guard_row and (guard_row[0] or 0) > 0:
                c.execute("""UPDATE user_status
                             SET fate_guard=MAX(0, COALESCE(fate_guard,0)-1)
                             WHERE telegram_id=?""", (telegram_id,))
                reroll_items = [it for it in pool['items'] if it['type'] != 'empty']
                item = random.choices(reroll_items, weights=[it['weight'] for it in reroll_items])[0]
                fate_guard_used = True

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
            if dw_active:
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
                log_economy(c, telegram_id, "double_win_consumed", 0, balance_after, None, "shop_item", "Двойной сигнал")
            result = {"type": "points", "amount": amount, "pool": pool_name, "name": f"+{amount} ★" + (" ×2" if doubled_win else ""), "rarity": 0, "card_bonus": fox_bonus, "doubled_win": doubled_win}
        elif item['type'] == 'fate_guard':
            c.execute("""INSERT INTO user_status (telegram_id, fate_guard) VALUES (?,1)
                         ON CONFLICT(telegram_id) DO UPDATE SET fate_guard=COALESCE(fate_guard,0)+1""", (telegram_id,))
            prize_code = "genshin_fate_guard"
            result = {"type": "fate_guard", "pool": pool_name, "name": "Гарант судьбы", "rarity": 0}
        elif item['type'] == 'scan':
            c.execute("""INSERT INTO user_status (telegram_id, scan_attempts) VALUES (?,1)
                         ON CONFLICT(telegram_id) DO UPDATE SET scan_attempts=MIN(7, scan_attempts+1)""", (telegram_id,))
            prize_code = "genshin_scan"
            result = {"type": "scan", "pool": pool_name, "name": "+1 попытка", "rarity": 0}
        elif item['type'] == 'empty':
            prize_code = "genshin_empty"
            result = {"type": "empty", "pool": pool_name, "name": "Пустая миска риса", "rarity": 0}
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
        c.execute("SELECT scan_attempts FROM user_status WHERE telegram_id=?", (telegram_id,))
        sc_row = c.fetchone()
        log_economy(c, telegram_id, 'prayer_open', new_points - points, new_points, None, pool_name, result.get("name") or prize_code)
        if fate_guard_used:
            log_economy(c, telegram_id, "fate_guard_consumed", 0, new_points, None, "prayer", "Гарант судьбы")

        diary_unlocked = []
        if unlock_diary_entry(c, telegram_id, "first_spin"):
            diary_unlocked.append("first_spin")
        if result.get("type") == "card" and not result.get("duplicate"):
            if unlock_diary_entry(c, telegram_id, "first_item"):
                diary_unlocked.append("first_item")

        award_achievement(c, telegram_id, "gambler")
        if pool_name == "gold" and not result.get("duplicate"):
            award_achievement(c, telegram_id, "lucky")
        if result.get("card_id") == "card_zhongli" and not result.get("duplicate"):
            award_achievement(c, telegram_id, "dragon")

        conn.commit()
        conn.close()
        result["new_points"] = new_points
        if sea_bonus:
            result["sea_bonus"] = sea_bonus
        result["scan_attempts"] = sc_row[0] if sc_row else 0
        result["fate_guard_used"] = fate_guard_used
        result["diary_unlocked"] = diary_unlocked
        return result
    return await db_write(_run)


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
def get_laundry_schedule(
    x_telegram_id: Optional[int] = Header(None),
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    conn = get_conn()
    c = conn.cursor()
    cohort_code = resolve_viewer_cohort(
        c, get_request_actor_id(x_telegram_id, x_admin_id), x_cohort_code
    )
    c.execute(
        "SELECT id, day, time, note, COALESCE(capacity, 1), COALESCE(assignee, '') "
        "FROM laundry_schedule WHERE cohort_code=? ORDER BY id",
        (cohort_code,),
    )
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
            "assignee": row[5],
            "booked": len(bookings),
            "bookings": bookings,
            "taken_by": bookings[0] if bookings else None,
        })
    conn.close()
    return result


@app.post("/api/laundry/schedule")
async def add_laundry_slot(
    data: dict,
    x_admin_id: int = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    def _run():
        if x_admin_id not in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Not admin")
        conn = get_conn()
        c = conn.cursor()
        cohort_code = resolve_viewer_cohort(c, x_admin_id, x_cohort_code)
        capacity = max(int(data.get("capacity") or 1), 1)
        c.execute(
            "INSERT INTO laundry_schedule (day, time, note, capacity, assignee, cohort_code) VALUES (?,?,?,?,?,?)",
            (data.get("day"), data.get("time"), data.get("note", ""), capacity, data.get("assignee", ""), cohort_code),
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
        diary_unlocked = []
        if unlock_diary_entry(c, telegram_id, "first_laundry"):
            diary_unlocked.append("first_laundry")
        conn.commit()
        conn.close()
        return {"success": True, "diary_unlocked": diary_unlocked}
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
def get_water_schedule(
    x_telegram_id: Optional[int] = Header(None),
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    conn = get_conn()
    c = conn.cursor()
    cohort_code = resolve_viewer_cohort(
        c, get_request_actor_id(x_telegram_id, x_admin_id), x_cohort_code
    )
    c.execute(
        "SELECT id, day, time, COALESCE(floor, ''), note, COALESCE(capacity, 1), COALESCE(assignee, '') "
        "FROM water_schedule WHERE cohort_code=? ORDER BY id",
        (cohort_code,),
    )
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
            "assignee": row[6],
            "booked": len(bookings),
            "bookings": bookings,
        })
    conn.close()
    return result


@app.post("/api/water/schedule")
async def add_water_slot(
    data: dict,
    x_admin_id: int = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    def _run():
        if x_admin_id not in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Not admin")
        conn = get_conn()
        c = conn.cursor()
        cohort_code = resolve_viewer_cohort(c, x_admin_id, x_cohort_code)
        capacity = max(int(data.get("capacity") or 1), 1)
        c.execute(
            "INSERT INTO water_schedule (day, time, floor, note, capacity, assignee, cohort_code) VALUES (?,?,?,?,?,?,?)",
            (
                data.get("day"),
                data.get("time"),
                data.get("floor", ""),
                data.get("note", ""),
                capacity,
                data.get("assignee", ""),
                cohort_code,
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
        c.execute("SELECT id FROM water_schedule WHERE id=?", (slot_id,))
        slot = c.fetchone()
        if not slot:
            conn.close()
            raise HTTPException(status_code=404, detail="Not found")
        # Вода — без лимита мест (наработка от МЮ, 2026-06-24): не проверяем capacity.
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
async def create_architect_event(
    data: dict,
    x_admin_id: int = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    def _run():
        admin_id = x_admin_id if x_admin_id is not None else data.get("telegram_id")
        if admin_id not in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Forbidden")

        scope_conn = get_conn()
        try:
            cohort_code = resolve_viewer_cohort(scope_conn.cursor(), admin_id, x_cohort_code)
        finally:
            scope_conn.close()
        blocking_event_id = get_blocking_event_id('architect', cohort_code)
        if blocking_event_id:
            raise HTTPException(status_code=409, detail="Another Architect Protocol event is already active")

        conn = get_conn()
        c = conn.cursor()

        title = data.get("title") or "ARCHITECT PROTOCOL"
        boss_name = data.get("boss_name") or "Архитектор"
        boss_image = data.get("boss_image")
        reward_text = data.get("reward_text") or "Приз не указан"
        min_players = int(data.get("min_players") or ARCHITECT_DEFAULT_MIN_PLAYERS)
        max_players = int(data.get("max_players") or ARCHITECT_DEFAULT_MAX_PLAYERS)
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
                phase_started_at, started_at, final_phase_deadline, vulnerability_until, overload_pressure, created_at,
                cohort_code)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'REGISTRATION', NULL, NULL, NULL, NULL, 0, ?, ?)''',
            ('architect', title, boss_name, boss_image, reward_text, min_players, max_players, max_hp, max_hp, created_at, cohort_code),
        )
        event_id = c.lastrowid
        add_event_log(c, event_id, "system", "Architect event created. Team registration is open.")
        add_event_log(c, event_id, "boss", f"Набор команды открыт. Приз: {reward_text}")
        conn.commit()
        conn.close()
        return get_event_snapshot(event_id)
    return await db_write(_run)


@app.post("/api/events/wildai/create")
async def create_wildai_event(
    data: dict,
    x_admin_id: int = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    def _run():
        admin_id = x_admin_id if x_admin_id is not None else data.get("telegram_id")
        if admin_id not in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Forbidden")

        scope_conn = get_conn()
        try:
            cohort_code = resolve_viewer_cohort(scope_conn.cursor(), admin_id, x_cohort_code)
        finally:
            scope_conn.close()
        blocking_event_id = get_blocking_event_id('wildai_breach', cohort_code)
        if blocking_event_id:
            raise HTTPException(status_code=409, detail="A WILD AI BREACH event is already active")

        conn = get_conn()
        c = conn.cursor()

        title = data.get("title") or "WILD AI BREACH"
        boss_name = data.get("boss_name") or "Дикий ИИ"
        boss_image = data.get("boss_image")
        reward_text = data.get("reward_text") or f"+{WILD_AI_BREACH_REWARD_REP} REP, рамка «{WILD_AI_BREACH_FRAME_ID}»"
        min_players = int(data.get("min_players") or 3)
        max_players = int(data.get("max_players") or 15)
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
                phase_started_at, started_at, final_phase_deadline, vulnerability_until, overload_pressure, created_at,
                cohort_code)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'REGISTRATION', NULL, NULL, NULL, NULL, 0, ?, ?)''',
            ('wildai_breach', title, boss_name, boss_image, reward_text, min_players, max_players, max_hp, max_hp, created_at, cohort_code),
        )
        event_id = c.lastrowid
        add_event_log(c, event_id, "system", "WILD AI BREACH: обнаружено вторжение. Набор команды для зачистки открыт.")
        add_event_log(c, event_id, "boss", f"Набор команды открыт. Награда: {reward_text}")
        conn.commit()
        conn.close()
        return get_event_snapshot(event_id)
    return await db_write(_run)


@app.post("/api/events/mju/create")
async def create_mju_event(
    data: dict,
    x_admin_id: int = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    def _run():
        admin_id = x_admin_id if x_admin_id is not None else data.get("telegram_id")
        if admin_id not in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Forbidden")

        scope_conn = get_conn()
        try:
            cohort_code = resolve_viewer_cohort(scope_conn.cursor(), admin_id, x_cohort_code)
        finally:
            scope_conn.close()
        blocking_event_id = get_blocking_event_id(MJU_EVENT_CODE, cohort_code)
        if blocking_event_id:
            raise HTTPException(status_code=409, detail="A Protocol Boss event is already active")

        conn = get_conn()
        c = conn.cursor()

        title = data.get("title") or "БОСС ПРОТОКОЛА"
        boss_name = data.get("boss_name") or "Михаил Юрьевич"
        boss_image = data.get("boss_image")
        reward_text = data.get("reward_text") or f"+{MJU_REWARD_REP} REP каждому участнику"
        min_players = int(data.get("min_players") or MJU_DEFAULT_MIN_PLAYERS)
        max_players = int(data.get("max_players") or MJU_DEFAULT_MAX_PLAYERS)
        max_hp = int(data.get("max_hp") or MJU_DEFAULT_HP)
        created_at = now_iso()
        if min_players < 1:
            min_players = 1
        if max_players < min_players:
            max_players = min_players
        c.execute(
            '''INSERT INTO events
               (code, title, boss_name, boss_image, reward_text, min_players, max_players,
                max_hp, current_hp, phase, state,
                phase_started_at, started_at, final_phase_deadline, vulnerability_until, overload_pressure, created_at,
                cohort_code)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'REGISTRATION', NULL, NULL, NULL, NULL, 0, ?, ?)''',
            (MJU_EVENT_CODE, title, boss_name, boss_image, reward_text, min_players, max_players, max_hp, max_hp, created_at, cohort_code),
        )
        event_id = c.lastrowid
        add_event_log(c, event_id, "system", "Босс Протокола: набор команды открыт.")
        add_event_log(c, event_id, "boss", "ЦЕНЗОР: ожидаю операторов. Нарушения будут зафиксированы.")
        conn.commit()
        conn.close()
        return get_event_snapshot(event_id)
    return await db_write(_run)


@app.get("/api/events/current")
async def get_current_event(
    code: Optional[str] = None,
    x_telegram_id: Optional[int] = Header(None),
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    def _run():
        conn = get_conn()
        try:
            cohort_code = resolve_viewer_cohort(
                conn.cursor(), get_request_actor_id(x_telegram_id, x_admin_id), x_cohort_code
            )
        finally:
            conn.close()
        event_id = get_current_or_latest_event_id(code, cohort_code)
        return {"event": get_event_snapshot(event_id) if event_id else None}
    return await db_write(_run)


@app.get("/api/events/{event_id}")
async def get_event_details(event_id: int):
    def _run():
        snapshot = get_event_snapshot(event_id)
        if not snapshot:
            raise HTTPException(status_code=404, detail="Event not found")
        return snapshot
    return await db_write(_run)


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
    def _run():
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
    return await db_write(_run)


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
        elif event_row["code"] == MJU_EVENT_CODE:
            add_event_log(c, event_id, "system", "Босс Протокола: проверка допуска начата.")
            add_event_log(c, event_id, "boss", "ЦЕНЗОР: тишина в сети. Отвечайте точно.")
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
        c.execute("DELETE FROM event_question_draws WHERE event_id=?", (event_id,))
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

        question = choose_architect_question(
            c,
            action_type,
            event_code=event_code,
            event_id=int(event_id),
            telegram_id=int(telegram_id),
        )
        conn.commit()
        conn.close()
        if not question:
            raise HTTPException(status_code=404, detail="Question not found")
        options, _ = shuffled_question_options(
            question["option_a"],
            question["option_b"],
            question["option_c"],
            "event",
            int(event_id),
            int(telegram_id),
            action_type,
            int(question["id"]),
            event_code,
        )
        return {
            "event_id": event_id,
            "action_type": action_type,
            "question": {
                "id": question["id"],
                "prompt": question["prompt"],
                "options": {
                    "a": options["a"],
                    "b": options["b"],
                    "c": options["c"],
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
                '''SELECT id, option_a, option_b, option_c, correct_option, explanation
                   FROM event_questions
                   WHERE id=? AND event_code=? AND action_type=?''',
                (question_id, event_row["code"], action_type),
            )
            row = c.fetchone()
            if not row:
                conn.close()
                raise HTTPException(status_code=404, detail="Question not found")
            question = {"id": row[0], "correct_option": row[4], "explanation": row[5]}
            is_correct = 1 if is_shuffled_answer_correct(
                answer_option,
                row[4],
                row[1],
                row[2],
                row[3],
                "event",
                int(event_id),
                int(telegram_id),
                action_type,
                int(question_id),
                event_row["code"],
            ) else 0

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
        is_mju = event_row["code"] == MJU_EVENT_CODE
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
            elif is_mju:
                mju_action_name = "регламент" if action_type == "protocol" else "удар"
                if is_correct:
                    if result.get("penalty_active"):
                        add_event_log(c, int(event_id), "system", f"⚠ КОНТРОЛЬ ЦЕНЗОРА: {actor_name} провёл(ела) {mju_action_name}, но урон снижен ({result['final_value']})")
                    else:
                        add_event_log(c, int(event_id), "action", f"{actor_name} провёл(ела) {mju_action_name} по протоколу и снял(а) {result['final_value']} HP")
                else:
                    partial = result['final_value']
                    if partial > 0:
                        add_event_log(c, int(event_id), "action", f"{actor_name} допустил(а) нарушение — частичный эффект {partial} HP")
                    else:
                        add_event_log(c, int(event_id), "action", f"{actor_name} ошибся(лась) — Цензор зафиксировал нарушение")
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
            elif is_mju:
                if is_correct:
                    add_event_log(c, int(event_id), "action", f"{actor_name} стабилизировал(а) дисциплину команды — нарушения снижены")
                else:
                    add_event_log(c, int(event_id), "action", f"{actor_name} ошибся(лась) при стабилизации — Цензор усиливает контроль")
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
            elif is_mju:
                add_event_log(c, int(event_id), "action", f"{actor_name} прошёл(ла) сетевое сканирование — регламент ослаблен")
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
        elif action_type in ("attack", "protocol", "stabilize", "sync") and result["pressure_delta"] != 0:
            ovl_threshold = result["overload_threshold"]
            pct_str = result.get("overload_pct_str", "50%")
            old_pressure = event_row["overload_pressure"]
            pressure_cap = MJU_CRITICAL_THRESHOLD if is_mju else 999999
            event_row["overload_pressure"] = min(pressure_cap, max(0, old_pressure + result["pressure_delta"]))
            c.execute("UPDATE events SET overload_pressure=? WHERE id=?", (event_row["overload_pressure"], int(event_id)))
            if is_mju:
                if old_pressure < ovl_threshold <= event_row["overload_pressure"]:
                    add_event_log(c, int(event_id), "system", f"⚠ НАРУШЕНИЯ ПРОТОКОЛА: контроль Цензора активен, урон снижен на {pct_str}")
                elif old_pressure >= ovl_threshold > event_row["overload_pressure"]:
                    add_event_log(c, int(event_id), "system", "✓ Нарушения снижены — регламент снова пробивается")
                if event_row["overload_pressure"] >= MJU_CRITICAL_THRESHOLD:
                    add_event_log(c, int(event_id), "boss", "ЦЕНЗОР: критический уровень нарушений. Исправляйте протокол.")
            else:
                if old_pressure < ovl_threshold <= event_row["overload_pressure"]:
                    add_event_log(c, int(event_id), "system", f"⚠ ПЕРЕГРУЗКА АКТИВНА — урон от атак снижен на {pct_str}")
                elif old_pressure >= ovl_threshold > event_row["overload_pressure"]:
                    add_event_log(c, int(event_id), "system", "✓ Перегрузка снята — атаки снова в полную силу")

        # Boss counter-attack: every N total actions adds pressure
        if not is_wildai:
            c.execute("SELECT COUNT(*) FROM event_actions WHERE event_id=?", (int(event_id),))
            total_actions_count = c.fetchone()[0]
            if is_mju:
                if total_actions_count > 0 and total_actions_count % MJU_BOSS_COUNTER_EVERY == 0:
                    new_pressure = min(MJU_CRITICAL_THRESHOLD, event_row["overload_pressure"] + MJU_BOSS_COUNTER_PRESSURE)
                    c.execute("UPDATE events SET overload_pressure=? WHERE id=?", (new_pressure, int(event_id)))
                    event_row["overload_pressure"] = new_pressure
                    add_event_log(c, int(event_id), "boss", f"ЦЕНЗОР ПРОВОДИТ СКАНИРОВАНИЕ (+{MJU_BOSS_COUNTER_PRESSURE} нарушения)")
            elif total_actions_count > 0 and total_actions_count % ARCHITECT_BOSS_COUNTER_EVERY == 0:
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
        f'''SELECT telegram_id, total_damage, total_support
           FROM event_participants
           WHERE event_id=?
             AND telegram_id NOT IN ({FLATLINED_PLACEHOLDERS})
           ORDER BY total_damage DESC, total_support DESC, telegram_id ASC''',
        (event_id, *FLATLINED_ID_LIST),
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
        "expires_at": row[16],
        "submitted_at": row[17],
        "auto_confirm_at": row[18],
        "role": ("creator" if viewer_id and row[6] == viewer_id else
                 "assignee" if viewer_id and row[7] == viewer_id else None),
    }


def expire_stale_open_contracts():
    """Marks 'open' contracts past their expires_at as 'expired' and refunds the
    creator's frozen reward in full."""
    conn = get_conn()
    try:
        c = conn.cursor()
        now_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
        c.execute(
            "SELECT id, creator_telegram_id, reward_stars FROM contracts "
            "WHERE status='open' AND expires_at IS NOT NULL AND expires_at < ?",
            (now_str,),
        )
        rows = c.fetchall()
        for cid, creator_id, reward in rows:
            c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (reward, creator_id))
            c.execute("SELECT points FROM users WHERE telegram_id=?", (creator_id,))
            bal = c.fetchone()[0] or 0
            c.execute("UPDATE contracts SET status='expired', cancelled_at=? WHERE id=?", (now_str, cid))
            log_economy(c, creator_id, 'contract_expired_refund', reward, bal, cid, 'contract',
                        f"Контракт #{cid} сгорел, возврат")
        conn.commit()
    finally:
        conn.close()


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
    cohort_code = get_user_cohort(c, user_id)
    blackwall_active = get_cohort_setting(c, 'blackwall', cohort_code, '0') == '1'
    if blackwall_active and (user_id is None or user_id not in ADMIN_IDS):
        raise HTTPException(status_code=403, detail="Доска поручений временно заблокирована режимом Великого Красного Файрвола")


@app.get("/api/contracts")
async def list_open_contracts(x_telegram_id: Optional[int] = Header(None)):
    await db_write(expire_stale_open_contracts, label="expire_stale_open_contracts")

    def _read():
        conn = get_conn()
        c = conn.cursor()
        _check_blackwall(c, x_telegram_id)
        cohort_code = get_user_cohort(c, x_telegram_id)
        c.execute(
            '''SELECT id, title, description, category, reward_stars, fee_stars,
                      creator_telegram_id, assignee_telegram_id, status,
                      is_suspicious, suspicious_reason,
                      created_at, accepted_at, completed_at, cancelled_at, disputed_at,
                      expires_at, submitted_at, auto_confirm_at, is_anonymous
               FROM contracts
               WHERE status='open' AND cohort_code=?
               ORDER BY created_at DESC
               LIMIT 50''',
            (cohort_code,),
        )
        rows = c.fetchall()
        result = []
        for row in rows:
            cn, an, ca, aa = _resolve_names(c, row[6], row[7])
            result.append(_contract_to_dict(row[:19], cn, an, ca, aa, x_telegram_id, bool(row[19]), True))
        conn.close()
        return result
    return await db_read(_read, label="contracts")


@app.get("/api/contracts/my")
async def my_contracts(x_telegram_id: Optional[int] = Header(None)):
    if not x_telegram_id:
        raise HTTPException(status_code=401, detail="Not authorized")

    await db_write(expire_stale_open_contracts, label="expire_stale_open_contracts")
    await db_write(auto_confirm_submitted_contracts, label="auto_confirm_submitted_contracts")

    def _read():
        conn = get_conn()
        c = conn.cursor()
        _check_blackwall(c, x_telegram_id)
        c.execute(
            '''SELECT id, title, description, category, reward_stars, fee_stars,
                      creator_telegram_id, assignee_telegram_id, status,
                      is_suspicious, suspicious_reason,
                      created_at, accepted_at, completed_at, cancelled_at, disputed_at,
                      expires_at, submitted_at, auto_confirm_at, is_anonymous
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
            result.append(_contract_to_dict(row[:19], cn, an, ca, aa, x_telegram_id, bool(row[19]), False))
        conn.close()
        return result
    return await db_read(_read, label="contracts_my")


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
    try:
        expires_hours = int(data.get("expires_hours", CONTRACT_EXPIRY_HOURS))
    except (TypeError, ValueError):
        expires_hours = CONTRACT_EXPIRY_HOURS
    if expires_hours < 1 or expires_hours > CONTRACT_EXPIRY_HOURS:
        expires_hours = CONTRACT_EXPIRY_HOURS

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
            now = datetime.now(BEIJING_TZ)
            now_str = now.strftime('%Y-%m-%d %H:%M:%S')
            expires_at = (now + timedelta(hours=expires_hours)).strftime('%Y-%m-%d %H:%M:%S')

            c.execute("UPDATE users SET points = points - ? WHERE telegram_id=?", (reward, x_telegram_id))
            c.execute("SELECT points FROM users WHERE telegram_id=?", (x_telegram_id,))
            balance_after = c.fetchone()[0] or 0

            cohort_code = get_user_cohort(c, x_telegram_id)
            c.execute(
                '''INSERT INTO contracts
                   (title, description, category, reward_stars, fee_stars,
                    creator_telegram_id, status, is_suspicious, suspicious_reason,
                    is_anonymous, created_at, expires_at, cohort_code)
                   VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?)''',
                (
                    title, description, category, reward, local_fee,
                    x_telegram_id, int(is_susp), susp_reason,
                    int(is_anonymous), now_str, expires_at, cohort_code,
                ),
            )
            contract_id = c.lastrowid
            log_economy(c, x_telegram_id, 'contract_freeze', -reward, balance_after,
                        contract_id, 'contract', f"Заморозка: контракт #{contract_id}")
            if zhongli_fee_reduction:
                log_economy(c, x_telegram_id, 'card_zhongli_contract_seal', 0, balance_after,
                            contract_id, 'card', f"Комиссия снижена на {zhongli_fee_reduction}★")
            diary_unlocked = []
            if unlock_diary_entry(c, x_telegram_id, "first_contract"):
                diary_unlocked.append("first_contract")
            conn.commit()
            return {"contract_id": contract_id, "fee_stars": local_fee, "new_points": balance_after, "diary_unlocked": diary_unlocked}
        finally:
            conn.close()

    result = await db_write(_run)
    if "error" in result:
        raise HTTPException(status_code=result["status"], detail=result["error"])

    return {"success": True, "id": result["contract_id"], "fee_stars": result["fee_stars"],
            "payout_stars": reward - result["fee_stars"], "new_points": result["new_points"],
            "diary_unlocked": result["diary_unlocked"]}


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


def _finalize_contract_payout(c, contract_id, row, now, auto=False):
    """Pays out an accepted/submitted contract: assignee gets the reward minus
    fee, creator's frozen fee is burned, contract becomes 'completed'."""
    creator_id, assignee_id, reward, fee = row[6], row[7], row[4], row[5]
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')
    payout = reward - fee
    c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (payout, assignee_id))
    c.execute("SELECT points FROM users WHERE telegram_id=?", (assignee_id,))
    assignee_bal = c.fetchone()[0] or 0
    payout_reason = 'contract_auto_payout' if auto else 'contract_payout'
    payout_note = 'Автовыплата' if auto else 'Выплата'
    log_economy(c, assignee_id, payout_reason, payout, assignee_bal, contract_id, 'contract',
                f"{payout_note} за контракт #{contract_id}")
    sea_bonus = grant_card_points_once(
        c, assignee_id, "card_sea", "contract_current", 5,
        "card_sea_current", f"контракт #{contract_id}", now.strftime('%Y-%m-%d'),
        contract_id, "contract",
    )
    c.execute("UPDATE contracts SET status='completed', completed_at=? WHERE id=?", (now_str, contract_id))
    log_economy(c, creator_id, 'contract_fee_burn', -fee, None, contract_id, 'contract',
                f"Комиссия Сетевого Дозора: контракт #{contract_id}")
    return {"success": True, "payout": payout, "fee_burned": fee, "card_sea_bonus": sea_bonus}


def auto_confirm_submitted_contracts():
    """Auto-confirms 'submitted' contracts whose auto_confirm_at has passed,
    paying out the assignee as if the creator had confirmed."""
    conn = get_conn()
    c = conn.cursor()
    now = datetime.now(BEIJING_TZ)
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')
    c.execute(
        '''SELECT id, title, description, category, reward_stars, fee_stars,
                  creator_telegram_id, assignee_telegram_id, status,
                  is_suspicious, suspicious_reason,
                  created_at, accepted_at, completed_at, cancelled_at, disputed_at,
                  submitted_at, auto_confirm_at
           FROM contracts
           WHERE status='submitted' AND auto_confirm_at IS NOT NULL AND auto_confirm_at < ?''',
        (now_str,),
    )
    rows = c.fetchall()
    for row in rows:
        _finalize_contract_payout(c, row[0], row, now, auto=True)
    conn.commit()
    conn.close()


@app.post("/api/contracts/{contract_id}/submit")
async def submit_contract(contract_id: int, x_telegram_id: Optional[int] = Header(None)):
    if not x_telegram_id:
        raise HTTPException(status_code=401, detail="Not authorized")

    def _run():
        conn = get_conn()
        try:
            c = conn.cursor()
            row = get_contract_row(c, contract_id)
            if not row:
                return {"error": "Контракт не найден", "status": 404}
            assignee_id, status, accepted_at = row[7], row[8], row[12]
            susp_reason = row[10]
            if status != 'accepted':
                return {"error": "Контракт не в работе", "status": 400}
            if x_telegram_id != assignee_id:
                return {"error": "Только исполнитель может отметить выполнение", "status": 403}

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

            auto_confirm_at = (now + timedelta(hours=CONTRACT_AUTO_CONFIRM_HOURS)).strftime('%Y-%m-%d %H:%M:%S')
            c.execute(
                "UPDATE contracts SET status='submitted', submitted_at=?, auto_confirm_at=? WHERE id=?",
                (now_str, auto_confirm_at, contract_id),
            )
            log_economy(c, x_telegram_id, 'contract_submit', 0, None, contract_id, 'contract',
                        f"Исполнитель отметил выполнение: контракт #{contract_id}")
            conn.commit()
            return {"success": True, "auto_confirm_at": auto_confirm_at}
        finally:
            conn.close()

    result = await db_write(_run)
    if "error" in result:
        raise HTTPException(status_code=result["status"], detail=result["error"])
    return result


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
        creator_id, status, accepted_at = row[6], row[8], row[12]
        susp_reason = row[10]
        if status not in ('accepted', 'submitted'):
            conn.close()
            raise HTTPException(status_code=400, detail="Можно завершить только принятый или сданный на проверку контракт")
        if x_admin_id not in ADMIN_IDS and acting_id != creator_id:
            conn.close()
            raise HTTPException(status_code=403, detail="Только заказчик или администратор может подтвердить выполнение")

        now = datetime.now(BEIJING_TZ)
        # Creator confirmed straight from 'accepted' (skipping the assignee's
        # submit step) — keep the existing too-fast-completion suspicion check.
        if status == 'accepted' and accepted_at:
            try:
                accepted_dt = datetime.strptime(accepted_at, '%Y-%m-%d %H:%M:%S')
                elapsed = (now.replace(tzinfo=None) - accepted_dt).total_seconds()
                if elapsed < CONTRACT_MIN_COMPLETE_SECONDS:
                    new_reason = ((susp_reason or '') + '; слишком быстрое завершение').lstrip('; ')
                    c.execute("UPDATE contracts SET is_suspicious=1, suspicious_reason=? WHERE id=?",
                              (new_reason, contract_id))
            except Exception:
                pass

        result = _finalize_contract_payout(c, contract_id, row, now, auto=False)
        conn.commit()
        conn.close()
        return result
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
        if status not in ('open', 'accepted', 'submitted', 'disputed'):
            conn.close()
            raise HTTPException(status_code=400, detail="Контракт нельзя отменить в текущем статусе")
        if status == 'open' and acting_id != creator_id and x_admin_id not in ADMIN_IDS:
            conn.close()
            raise HTTPException(status_code=403, detail="Только заказчик может отменить открытый контракт")
        if status in ('accepted', 'submitted', 'disputed') and x_admin_id not in ADMIN_IDS:
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
        if status not in ('accepted', 'submitted'):
            conn.close()
            raise HTTPException(status_code=400, detail="Спор можно открыть только для принятого или сданного на проверку контракта")
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
def admin_list_contracts(
    x_admin_id: Optional[int] = Header(None),
    status: Optional[str] = None,
    x_cohort_code: Optional[str] = Header(None),
):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = get_conn()
    c = conn.cursor()
    cohort_code = resolve_viewer_cohort(c, x_admin_id, x_cohort_code)
    if status:
        c.execute(
            '''SELECT c.id, c.title, c.description, c.category, c.reward_stars, c.fee_stars,
                      c.creator_telegram_id, c.assignee_telegram_id, c.status,
                      c.is_suspicious, c.suspicious_reason,
                      c.created_at, c.accepted_at, c.completed_at, c.cancelled_at, c.disputed_at,
                      c.expires_at, c.submitted_at, c.auto_confirm_at,
                      u1.full_name, u2.full_name, u1.avatar_url, u2.avatar_url, c.is_anonymous
               FROM contracts c
               LEFT JOIN users u1 ON u1.telegram_id=c.creator_telegram_id
               LEFT JOIN users u2 ON u2.telegram_id=c.assignee_telegram_id
               WHERE c.status=? AND c.cohort_code=?
               ORDER BY c.created_at DESC LIMIT 100''',
            (status, cohort_code),
        )
    else:
        c.execute(
            '''SELECT c.id, c.title, c.description, c.category, c.reward_stars, c.fee_stars,
                      c.creator_telegram_id, c.assignee_telegram_id, c.status,
                      c.is_suspicious, c.suspicious_reason,
                      c.created_at, c.accepted_at, c.completed_at, c.cancelled_at, c.disputed_at,
                      c.expires_at, c.submitted_at, c.auto_confirm_at,
                      u1.full_name, u2.full_name, u1.avatar_url, u2.avatar_url, c.is_anonymous
               FROM contracts c
               LEFT JOIN users u1 ON u1.telegram_id=c.creator_telegram_id
               LEFT JOIN users u2 ON u2.telegram_id=c.assignee_telegram_id
               WHERE c.cohort_code=?
               ORDER BY c.created_at DESC LIMIT 100''',
            (cohort_code,),
        )
    rows = c.fetchall()
    conn.close()
    return [
        {**_contract_to_dict(row[:19], row[19], row[20], row[21], row[22], None, bool(row[23]), False),
         "creator_name": row[19], "assignee_name": row[20],
         "creator_avatar_url": _safe_contract_avatar_url(row[21]),
         "assignee_avatar_url": _safe_contract_avatar_url(row[22]),
         "is_anonymous": bool(row[23])}
        for row in rows
    ]


@app.get("/api/admin/contracts/monitor")
def admin_contract_monitor(
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = get_conn()
    c = conn.cursor()
    cohort_code = resolve_viewer_cohort(c, x_admin_id, x_cohort_code)

    c.execute(
        '''SELECT status, COUNT(*), COALESCE(SUM(reward_stars),0),
                  COALESCE(SUM(CASE WHEN status='completed' THEN fee_stars ELSE 0 END),0)
           FROM contracts
           WHERE cohort_code=?
           GROUP BY status''',
        (cohort_code,),
    )
    status_rows = c.fetchall()
    status_counts = {row[0]: row[1] for row in status_rows}
    reward_by_status = {row[0]: row[2] for row in status_rows}
    fee_burned = sum(row[3] or 0 for row in status_rows)

    c.execute(
        "SELECT COUNT(*), COALESCE(SUM(reward_stars),0) FROM contracts WHERE cohort_code=?",
        (cohort_code,),
    )
    total_count, total_turnover = c.fetchone()
    c.execute(
        "SELECT COUNT(*) FROM contracts WHERE is_suspicious=1 AND cohort_code=?",
        (cohort_code,),
    )
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
           WHERE c.assignee_telegram_id IS NOT NULL AND c.cohort_code=?
           GROUP BY c.creator_telegram_id, c.assignee_telegram_id
           ORDER BY reward_total DESC, contract_count DESC
           LIMIT 30''',
        (cohort_code,),
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
           WHERE sp.given_to IS NOT NULL AND ut.cohort_code=?
           GROUP BY sp.given_to, sp.telegram_id
           ORDER BY item_value DESC, gift_count DESC
           LIMIT 30''',
        (cohort_code,),
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
           WHERE sp.given_to IS NOT NULL AND ut.cohort_code=?
           ORDER BY COALESCE(sp.gifted_at, sp.purchased_at) DESC
           LIMIT 50''',
        (cohort_code,),
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
def admin_economy_report(
    since: Optional[str] = None,
    until: Optional[str] = None,
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
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
    cohort_code = resolve_viewer_cohort(c, x_admin_id, x_cohort_code)

    admin_placeholders = ','.join('?' * len(ADMIN_IDS))
    c.execute(
        '''SELECT
             u.telegram_id,
             COALESCE(u.full_name, u.telegram_id) AS full_name,
             u.points,
             COALESCE(e.tx_count, 0) AS tx_count,
             COALESCE(e.earned, 0) AS earned,
             COALESCE(e.spent, 0) AS spent,
             COALESCE(e.shop_spent, 0) AS shop_spent,
             COALESCE(e.cases_opened, 0) AS cases_opened,
             COALESCE(e.cases_spent, 0) AS cases_spent,
             COALESCE(e.cases_won, 0) AS cases_won,
             COALESCE(e.raids_entered, 0) AS raids_entered,
             COALESCE(e.raids_won, 0) AS raids_won,
             COALESCE(e.gifts_sent, 0) AS gifts_sent,
             COALESCE(e.gifts_received, 0) AS gifts_received,
             COALESCE(e.penalties, 0) AS penalties,
             COALESCE(e.salary_award_total, 0) AS salary_award_total,
             COALESCE(e.contract_earnings, 0) AS contract_earnings,
             COALESCE(e.contract_spent, 0) AS contract_spent
           FROM users u
           LEFT JOIN (
             SELECT
               telegram_id,
               COUNT(*) AS tx_count,
               COALESCE(SUM(CASE WHEN amount>0 THEN amount ELSE 0 END),0) AS earned,
               COALESCE(SUM(CASE WHEN amount<0 THEN -amount ELSE 0 END),0) AS spent,
               COALESCE(SUM(CASE WHEN operation='shop_purchase' THEN -amount ELSE 0 END),0) AS shop_spent,
               COALESCE(SUM(CASE WHEN operation IN ('case_open','prayer_open') THEN 1 ELSE 0 END),0) AS cases_opened,
               COALESCE(SUM(CASE WHEN operation IN ('case_open','prayer_open') THEN -amount ELSE 0 END),0) AS cases_spent,
               COALESCE(SUM(CASE WHEN operation IN ('case_open','prayer_open') AND amount>0 THEN amount ELSE 0 END),0) AS cases_won,
               COALESCE(SUM(CASE WHEN operation='raid_entry' THEN 1 ELSE 0 END),0) AS raids_entered,
               COALESCE(SUM(CASE WHEN operation='raid_reward' THEN 1 ELSE 0 END),0) AS raids_won,
               COALESCE(SUM(CASE WHEN operation='gift_tax' THEN 1 ELSE 0 END),0) AS gifts_sent,
               COALESCE(SUM(CASE WHEN operation='gift_receive' THEN 1 ELSE 0 END),0) AS gifts_received,
               COALESCE(SUM(CASE WHEN operation IN ('presence_penalty','presence_rep_penalty','admin_points','bot_penalize') AND amount<0 THEN 1 ELSE 0 END),0) AS penalties,
               COALESCE(SUM(CASE WHEN operation IN ('bot_salary','bot_award') THEN amount ELSE 0 END),0) AS salary_award_total,
               COALESCE(SUM(CASE WHEN operation='contract_payout' THEN amount ELSE 0 END),0) AS contract_earnings,
               COALESCE(SUM(CASE WHEN operation='contract_freeze' THEN -amount ELSE 0 END),0) AS contract_spent
             FROM economy_log
             WHERE created_at BETWEEN ? AND ?
             GROUP BY telegram_id
           ) e ON e.telegram_id = u.telegram_id
           WHERE u.telegram_id IS NOT NULL
             AND u.cohort_code=?
             AND u.telegram_id NOT IN ({})
           ORDER BY tx_count DESC, u.full_name COLLATE NOCASE'''.format(admin_placeholders),
        [since, until, cohort_code] + ADMIN_IDS,
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
            "active_players": sum(1 for p in players if p["tx_count"] > 0),
            "total_earned": sum(p["earned"] for p in players),
            "total_spent": sum(p["spent"] for p in players),
            "total_cases_opened": sum(p["cases_opened"] for p in players),
            "total_raids_entered": sum(p["raids_entered"] for p in players),
            "total_gifts": sum(p["gifts_sent"] for p in players),
            "total_penalties": sum(p["penalties"] for p in players),
        },
        "players": players,
    }


@app.get("/api/admin/activity/report")
def admin_activity_report(
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    if x_admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')

    conn = get_conn()
    c = conn.cursor()
    cohort_code = resolve_viewer_cohort(c, x_admin_id, x_cohort_code)

    admin_placeholders = ','.join('?' * len(ADMIN_IDS))
    c.execute(
        '''SELECT
             u.telegram_id,
             COALESCE(u.full_name, u.telegram_id) AS full_name,
             COALESCE(a.total_count, 0) AS total_count,
             COALESCE(a.today_count, 0) AS today_count,
             a.last_active
           FROM users u
           LEFT JOIN (
             SELECT
               telegram_id,
               COUNT(*) AS total_count,
               COALESCE(SUM(CASE WHEN substr(ts, 1, 10) = ? THEN 1 ELSE 0 END), 0) AS today_count,
               MAX(ts) AS last_active
             FROM (
               SELECT telegram_id, created_at AS ts FROM economy_log
               UNION ALL
               SELECT telegram_id, confirmed_at AS ts FROM daily_checks WHERE confirmed_at IS NOT NULL
               UNION ALL
               SELECT telegram_id, updated_at AS ts FROM diary_entries WHERE updated_at IS NOT NULL
               UNION ALL
               SELECT telegram_id, created_at AS ts FROM casino_log
               UNION ALL
               SELECT telegram_id, created_at AS ts FROM event_actions
             )
             GROUP BY telegram_id
           ) a ON a.telegram_id = u.telegram_id
           WHERE u.telegram_id IS NOT NULL
             AND u.cohort_code=?
             AND u.telegram_id NOT IN ({})
           ORDER BY today_count DESC, total_count DESC, u.full_name COLLATE NOCASE'''.format(admin_placeholders),
        [today, cohort_code] + ADMIN_IDS,
    )
    rows = c.fetchall()
    conn.close()

    players = [
        {
            "telegram_id": row[0],
            "full_name": str(row[1]),
            "total_count": row[2] or 0,
            "today_count": row[3] or 0,
            "last_active": row[4],
        }
        for row in rows
    ]

    return {
        "today": today,
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
        return {"success": True, "action": action}
    return await db_write(_run)


# ======================================================================
# PvP DUELS (Tekken-style live quiz battle)
# Async challenge -> accept -> ready-check -> live polled rounds.
# Zero-sum fixed stake tiers. Admin/flag-gated until DUELS_PUBLIC=True.
# See CLAUDE.md PvP spec.
# ======================================================================

DUELS_PUBLIC = True
DUEL_STAKE_TIERS = [10, 25, 50, 100]
ALPHABOSS_ID = int(os.getenv("ALPHABOSS_ID", "244487659") or "244487659")
DUEL_ALPHABOSS_STAKE = int(os.getenv("DUEL_ALPHABOSS_STAKE", "200") or "200")
DUEL_MAX_HP = 100
DUEL_HIT_DAMAGE = 20
DUEL_MAX_ROUNDS = 7
DUEL_ROUND_SECONDS = 20       # answer window per round
DUEL_CHALLENGE_EXPIRY_SECONDS = 86400  # 24h to accept a challenge

DUEL_COLUMNS = [
    "id", "challenger_id", "opponent_id", "stake", "status",
    "challenger_hp", "opponent_hp", "challenger_ready", "opponent_ready",
    "round_no", "current_question_id", "round_started_at",
    "challenger_answer", "opponent_answer", "challenger_answer_at", "opponent_answer_at",
    "winner_id", "created_at", "updated_at", "accepted_at", "finished_at",
]

def _duel_allowed(telegram_id) -> bool:
    return DUELS_PUBLIC or telegram_id in ADMIN_IDS


def _duel_required_stake(challenger_id, opponent_id) -> Optional[int]:
    if opponent_id == ALPHABOSS_ID and challenger_id != ALPHABOSS_ID:
        return DUEL_ALPHABOSS_STAKE
    return None


def _duel_stake_allowed(challenger_id, opponent_id, stake) -> bool:
    required_stake = _duel_required_stake(challenger_id, opponent_id)
    if required_stake is not None:
        return stake == required_stake
    return stake in DUEL_STAKE_TIERS


def _duel_user_study_group(c, telegram_id) -> Optional[str]:
    c.execute("SELECT study_group FROM users WHERE telegram_id=?", (telegram_id,))
    row = c.fetchone()
    return normalize_study_group(row[0]) if row else None


def _duel_group_bypass(*telegram_ids) -> bool:
    return any(int(tid) in ADMIN_IDS for tid in telegram_ids if tid is not None)


def _duel_groups_compatible(c, challenger_id, opponent_id) -> tuple[bool, Optional[str], Optional[str]]:
    challenger_group = _duel_user_study_group(c, challenger_id)
    opponent_group = _duel_user_study_group(c, opponent_id)
    if _duel_group_bypass(challenger_id, opponent_id):
        return True, challenger_group, opponent_group
    return bool(challenger_group and challenger_group == opponent_group), challenger_group, opponent_group


def _duel_match_study_group(c, duel: dict) -> Optional[str]:
    challenger_group = _duel_user_study_group(c, duel["challenger_id"])
    opponent_group = _duel_user_study_group(c, duel["opponent_id"])
    if challenger_group and challenger_group == opponent_group:
        return challenger_group
    if challenger_group and duel["opponent_id"] in ADMIN_IDS:
        return challenger_group
    if opponent_group and duel["challenger_id"] in ADMIN_IDS:
        return opponent_group
    return None


def _duel_role(duel: dict, telegram_id):
    if telegram_id == duel["challenger_id"]:
        return "challenger"
    if telegram_id == duel["opponent_id"]:
        return "opponent"
    return None


def _fetch_duel(c, duel_id):
    c.execute(f"SELECT {','.join(DUEL_COLUMNS)} FROM duels WHERE id=?", (duel_id,))
    row = c.fetchone()
    if not row:
        return None
    return dict(zip(DUEL_COLUMNS, row))


def choose_duel_question(c, exclude_id=None, study_group: Optional[str] = None):
    group = normalize_study_group(study_group)
    difficulty_filter = ""
    params = []
    if group:
        meta = STUDY_GROUPS[group]
        difficulty_filter = " AND difficulty BETWEEN ? AND ?"
        params.extend([meta["duel_min_difficulty"], meta["duel_max_difficulty"]])

    if exclude_id:
        c.execute(
            "SELECT id, prompt, option_a, option_b, option_c FROM event_questions "
            f"WHERE event_code='duel'{difficulty_filter} AND id!=? ORDER BY RANDOM() LIMIT 1",
            tuple(params + [exclude_id]),
        )
        row = c.fetchone()
        if row:
            return {"id": row[0], "prompt": row[1], "option_a": row[2], "option_b": row[3], "option_c": row[4]}
    c.execute(
        "SELECT id, prompt, option_a, option_b, option_c FROM event_questions "
        f"WHERE event_code='duel'{difficulty_filter} ORDER BY RANDOM() LIMIT 1",
        tuple(params),
    )
    row = c.fetchone()
    if not row and group:
        c.execute(
            "SELECT id, prompt, option_a, option_b, option_c FROM event_questions "
            "WHERE event_code='duel' ORDER BY RANDOM() LIMIT 1"
        )
        row = c.fetchone()
    if not row:
        return None
    return {"id": row[0], "prompt": row[1], "option_a": row[2], "option_b": row[3], "option_c": row[4]}


def _round_due(duel: dict) -> bool:
    """A round is ready to resolve when both answered, or the timer expired."""
    if duel["status"] != "active":
        return False
    if duel["challenger_answer"] is not None and duel["opponent_answer"] is not None:
        return True
    started = parse_iso(duel["round_started_at"])
    if started and (datetime.utcnow() - started).total_seconds() >= DUEL_ROUND_SECONDS:
        return True
    return False


def _settle_duel(c, duel: dict, winner_id):
    """Zero-sum stake transfer. transfer = min(stake, loser balance) keeps it
    exactly zero-sum even if the loser spent points after accepting."""
    if not winner_id:
        return  # draw — no transfer
    stake = duel["stake"]
    loser_id = duel["opponent_id"] if winner_id == duel["challenger_id"] else duel["challenger_id"]
    c.execute("SELECT COALESCE(points, 0) FROM users WHERE telegram_id=?", (loser_id,))
    row = c.fetchone()
    bal = row[0] if row else 0
    transfer = min(stake, max(0, bal))
    if transfer <= 0:
        return
    c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (transfer, winner_id))
    c.execute("UPDATE users SET points = MAX(0, COALESCE(points, 0) - ?) WHERE telegram_id=?", (transfer, loser_id))
    log_economy(c, winner_id, 'duel_win', transfer, None, duel["id"], 'duel', f"Победа в дуэли #{duel['id']}")
    log_economy(c, loser_id, 'duel_loss', -transfer, None, duel["id"], 'duel', f"Поражение в дуэли #{duel['id']}")


def _resolve_round(c, duel: dict):
    """Resolve the current round (called when both answered or timer expired),
    then either finish the match or advance to the next round. Idempotent guard
    is the caller's responsibility (status=='active' and _round_due)."""
    c.execute("SELECT correct_option FROM event_questions WHERE id=?", (duel["current_question_id"],))
    row = c.fetchone()
    correct = row[0] if row else None

    ch_ok = correct is not None and duel["challenger_answer"] == correct
    op_ok = correct is not None and duel["opponent_answer"] == correct
    ch_hp = duel["challenger_hp"]
    op_hp = duel["opponent_hp"]

    hit_role = None
    if ch_ok and op_ok:
        ch_t = parse_iso(duel["challenger_answer_at"])
        op_t = parse_iso(duel["opponent_answer_at"])
        if ch_t and op_t and ch_t < op_t:
            hit_role = "challenger"
        elif ch_t and op_t and op_t < ch_t:
            hit_role = "opponent"
    elif ch_ok:
        hit_role = "challenger"
    elif op_ok:
        hit_role = "opponent"

    if hit_role == "challenger":
        op_hp = max(0, op_hp - DUEL_HIT_DAMAGE)
    elif hit_role == "opponent":
        ch_hp = max(0, ch_hp - DUEL_HIT_DAMAGE)

    now = now_iso()
    finished = False
    winner_id = None
    if ch_hp <= 0 or op_hp <= 0:
        finished = True
        if op_hp <= 0 and ch_hp > 0:
            winner_id = duel["challenger_id"]
        elif ch_hp <= 0 and op_hp > 0:
            winner_id = duel["opponent_id"]
        else:
            winner_id = None
    elif duel["round_no"] >= DUEL_MAX_ROUNDS:
        finished = True
        if ch_hp > op_hp:
            winner_id = duel["challenger_id"]
        elif op_hp > ch_hp:
            winner_id = duel["opponent_id"]
        else:
            winner_id = None

    if finished:
        c.execute(
            "UPDATE duels SET challenger_hp=?, opponent_hp=?, status='finished', winner_id=?, "
            "finished_at=?, updated_at=?, current_question_id=NULL WHERE id=?",
            (ch_hp, op_hp, winner_id, now, now, duel["id"]),
        )
        settled = _fetch_duel(c, duel["id"])
        _settle_duel(c, settled, winner_id)
    else:
        nextq = choose_duel_question(
            c,
            exclude_id=duel["current_question_id"],
            study_group=_duel_match_study_group(c, duel),
        )
        c.execute(
            "UPDATE duels SET challenger_hp=?, opponent_hp=?, round_no=round_no+1, current_question_id=?, "
            "round_started_at=?, challenger_answer=NULL, opponent_answer=NULL, "
            "challenger_answer_at=NULL, opponent_answer_at=NULL, updated_at=? WHERE id=?",
            (ch_hp, op_hp, nextq["id"] if nextq else None, now, now, duel["id"]),
        )
    return _fetch_duel(c, duel["id"])


def _resolve_round_locked(duel_id):
    """Re-fetch under the write lock, re-check, resolve. Used for timer-expiry
    resolution triggered from the (read) state endpoint."""
    conn = get_conn()
    c = conn.cursor()
    duel = _fetch_duel(c, duel_id)
    if duel and duel["status"] == "active" and _round_due(duel):
        duel = _resolve_round(c, duel)
        conn.commit()
    conn.close()
    return duel


def _public_duel_state(duel: dict, viewer_id):
    """Build the viewer-facing duel state. Never leaks correct_option."""
    if not duel:
        return {"exists": False}
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT telegram_id, full_name, avatar_url, study_group FROM users WHERE telegram_id IN (?,?)",
        (duel["challenger_id"], duel["opponent_id"]),
    )
    names = {}
    avatars = {}
    groups = {}
    for r in c.fetchall():
        names[r[0]] = r[1]
        avatars[r[0]] = r[2]
        groups[r[0]] = study_group_payload(r[3])
    question = None
    if duel["status"] == "active" and duel["current_question_id"]:
        c.execute(
            "SELECT id, prompt, option_a, option_b, option_c FROM event_questions WHERE id=?",
            (duel["current_question_id"],),
        )
        r = c.fetchone()
        if r:
            question = {"id": r[0], "prompt": r[1], "options": {"a": r[2], "b": r[3], "c": r[4]}}
    conn.close()

    role = _duel_role(duel, viewer_id)
    you_ch = role == "challenger"
    opp_id = duel["opponent_id"] if you_ch else duel["challenger_id"]
    you_id = duel["challenger_id"] if you_ch else duel["opponent_id"]
    your_hp = duel["challenger_hp"] if you_ch else duel["opponent_hp"]
    opp_hp = duel["opponent_hp"] if you_ch else duel["challenger_hp"]
    your_ready = duel["challenger_ready"] if you_ch else duel["opponent_ready"]
    opp_ready = duel["opponent_ready"] if you_ch else duel["challenger_ready"]
    your_ans = duel["challenger_answer"] if you_ch else duel["opponent_answer"]
    opp_ans = duel["opponent_answer"] if you_ch else duel["challenger_answer"]

    out = {
        "exists": True,
        "id": duel["id"],
        "status": duel["status"],
        "stake": duel["stake"],
        "role": role,
        "round_no": duel["round_no"],
        "max_hp": DUEL_MAX_HP,
        "max_rounds": DUEL_MAX_ROUNDS,
        "round_seconds": DUEL_ROUND_SECONDS,
        "you": {
            "telegram_id": you_id,
            "name": names.get(you_id, "ТЫ"),
            "avatar_url": avatars.get(you_id),
            "study_group": groups.get(you_id, study_group_payload(None)),
            "hp": your_hp,
            "ready": bool(your_ready),
            "answered": your_ans is not None,
        },
        "opponent": {
            "telegram_id": opp_id,
            "name": names.get(opp_id, str(opp_id)),
            "avatar_url": avatars.get(opp_id),
            "study_group": groups.get(opp_id, study_group_payload(None)),
            "hp": opp_hp,
            "ready": bool(opp_ready),
            "answered": opp_ans is not None,
        },
    }
    if duel["status"] == "active":
        started = parse_iso(duel["round_started_at"])
        out["seconds_left"] = (
            max(0, int(DUEL_ROUND_SECONDS - (datetime.utcnow() - started).total_seconds()))
            if started else DUEL_ROUND_SECONDS
        )
        out["question"] = question
    if duel["status"] == "finished":
        out["winner_id"] = duel["winner_id"]
        out["you_won"] = duel["winner_id"] == viewer_id
        out["draw"] = duel["winner_id"] is None
    return out


@app.post("/api/duel/challenge")
async def duel_challenge(data: dict):
    try:
        challenger_id = int(data.get("challenger_id"))
        opponent_id = int(data.get("opponent_id"))
        stake = int(data.get("stake"))
    except (TypeError, ValueError):
        challenger_id = None
        opponent_id = None
        stake = None

    def _run():
        if not challenger_id or not opponent_id:
            raise HTTPException(status_code=400, detail="Не указаны игроки")
        if challenger_id == opponent_id:
            raise HTTPException(status_code=400, detail="Нельзя вызвать самого себя")
        if challenger_id not in ADMIN_IDS and opponent_id in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Админов могут вызывать только админы")
        required_stake = _duel_required_stake(challenger_id, opponent_id)
        if not _duel_stake_allowed(challenger_id, opponent_id, stake):
            if required_stake is not None:
                raise HTTPException(status_code=400, detail=f"Вызов Альфабосса стоит {required_stake}★")
            raise HTTPException(status_code=400, detail="Недопустимая ставка")
        if not _duel_allowed(challenger_id) or not _duel_allowed(opponent_id):
            raise HTTPException(status_code=403, detail="Дуэли пока доступны только админам")
        conn = get_conn()
        c = conn.cursor()
        if challenger_id not in GLOBAL_ADMIN_IDS:
            require_same_user_cohort(c, challenger_id, opponent_id)
        c.execute(
            "SELECT telegram_id, full_name, COALESCE(points,0) FROM users WHERE telegram_id IN (?,?)",
            (challenger_id, opponent_id),
        )
        rows = {r[0]: (r[1], r[2]) for r in c.fetchall()}
        if challenger_id not in rows or opponent_id not in rows:
            conn.close()
            raise HTTPException(status_code=404, detail="Игрок не найден")
        if rows[challenger_id][1] < stake:
            conn.close()
            raise HTTPException(status_code=400, detail="Недостаточно баллов для ставки")
        compatible, challenger_group, opponent_group = _duel_groups_compatible(c, challenger_id, opponent_id)
        if not compatible:
            conn.close()
            if not challenger_group or not opponent_group:
                raise HTTPException(status_code=400, detail="Сначала нужно назначить учебную группу обоим игрокам")
            raise HTTPException(status_code=403, detail="Дуэль доступна только внутри своей учебной группы")
        c.execute(
            "SELECT id FROM duels WHERE status IN ('pending','accepted','ready','active') "
            "AND (challenger_id=? OR opponent_id=?) LIMIT 1",
            (challenger_id, challenger_id),
        )
        if c.fetchone():
            conn.close()
            raise HTTPException(status_code=409, detail="У тебя уже есть активная дуэль")
        c.execute(
            "SELECT id FROM duels WHERE status IN ('ready','active') AND (challenger_id=? OR opponent_id=?) LIMIT 1",
            (opponent_id, opponent_id),
        )
        if c.fetchone():
            conn.close()
            raise HTTPException(status_code=409, detail="Соперник сейчас в бою")
        now = now_iso()
        c.execute(
            "INSERT INTO duels (challenger_id, opponent_id, stake, status, created_at, updated_at) "
            "VALUES (?,?,?, 'pending', ?, ?)",
            (challenger_id, opponent_id, stake, now, now),
        )
        duel_id = c.lastrowid
        conn.commit()
        ch_name = rows[challenger_id][0]
        conn.close()
        return {"duel_id": duel_id, "challenger_name": ch_name}

    result = await db_write(_run)
    await send_telegram_message(
        opponent_id,
        f"⚔️ {result['challenger_name']} вызывает тебя на дуэль!\nСтавка: {stake}★\n\n"
        f"Открой приложение → Рейтинг → ⚔ ДУЭЛИ, чтобы принять или отклонить.",
    )
    return {"success": True, "duel_id": result["duel_id"]}


@app.get("/api/duel/incoming/{telegram_id}")
def duel_incoming(telegram_id: int):
    conn = get_conn()
    c = conn.cursor()
    cutoff = (datetime.utcnow() - timedelta(seconds=DUEL_CHALLENGE_EXPIRY_SECONDS)).isoformat()
    c.execute(
        "SELECT d.id, d.challenger_id, u.full_name, d.stake, d.created_at, u.study_group FROM duels d "
        "JOIN users u ON u.telegram_id = d.challenger_id "
        "WHERE d.opponent_id=? AND d.status='pending' AND d.created_at>=? ORDER BY d.id DESC",
        (telegram_id, cutoff),
    )
    items = [
        {
            "duel_id": r[0],
            "challenger_id": r[1],
            "challenger_name": r[2],
            "stake": r[3],
            "created_at": r[4],
            "study_group": study_group_payload(r[5]),
        }
        for r in c.fetchall()
    ]
    conn.close()
    return {"challenges": items}


@app.get("/api/duel/current/{telegram_id}")
def duel_current(telegram_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT id FROM duels WHERE status IN ('accepted','ready','active') "
        "AND (challenger_id=? OR opponent_id=?) ORDER BY id DESC LIMIT 1",
        (telegram_id, telegram_id),
    )
    row = c.fetchone()
    active_id = row[0] if row else None
    c.execute(
        "SELECT id, opponent_id, stake FROM duels WHERE status='pending' AND challenger_id=? ORDER BY id DESC LIMIT 1",
        (telegram_id,),
    )
    sent = c.fetchone()
    conn.close()
    return {
        "enabled": _duel_allowed(telegram_id),
        "active_duel_id": active_id,
        "pending_sent": ({"duel_id": sent[0], "opponent_id": sent[1], "stake": sent[2]} if sent else None),
    }


@app.post("/api/duel/{duel_id}/accept")
async def duel_accept(duel_id: int, data: dict):
    telegram_id = data.get("telegram_id")

    def _run():
        conn = get_conn()
        c = conn.cursor()
        duel = _fetch_duel(c, duel_id)
        if not duel:
            conn.close()
            raise HTTPException(status_code=404, detail="Дуэль не найдена")
        if duel["opponent_id"] != telegram_id:
            conn.close()
            raise HTTPException(status_code=403, detail="Это не твой вызов")
        if duel["status"] != "pending":
            conn.close()
            raise HTTPException(status_code=409, detail="Вызов уже не активен")
        compatible, challenger_group, opponent_group = _duel_groups_compatible(c, duel["challenger_id"], duel["opponent_id"])
        if not compatible:
            conn.close()
            raise HTTPException(status_code=403, detail="Дуэль доступна только внутри своей учебной группы")
        created = parse_iso(duel["created_at"])
        if created and (datetime.utcnow() - created).total_seconds() > DUEL_CHALLENGE_EXPIRY_SECONDS:
            c.execute("UPDATE duels SET status='expired', updated_at=? WHERE id=?", (now_iso(), duel_id))
            conn.commit()
            conn.close()
            raise HTTPException(status_code=409, detail="Вызов истёк")
        c.execute("SELECT COALESCE(points,0) FROM users WHERE telegram_id=?", (telegram_id,))
        bal = (c.fetchone() or [0])[0]
        if bal < duel["stake"]:
            conn.close()
            raise HTTPException(status_code=400, detail="Недостаточно баллов для ставки")
        now = now_iso()
        c.execute("UPDATE duels SET status='accepted', accepted_at=?, updated_at=? WHERE id=?", (now, now, duel_id))
        conn.commit()
        conn.close()
        return {"challenger_id": duel["challenger_id"], "stake": duel["stake"]}

    res = await db_write(_run)
    await send_telegram_message(
        res["challenger_id"],
        f"⚔️ Твой вызов принят! Ставка {res['stake']}★.\n"
        f"Открой приложение → Рейтинг → ⚔ ДУЭЛИ и нажми «Готов», когда будешь у телефона.",
    )
    return {"success": True}


@app.post("/api/duel/{duel_id}/decline")
async def duel_decline(duel_id: int, data: dict):
    telegram_id = data.get("telegram_id")

    def _run():
        conn = get_conn()
        c = conn.cursor()
        duel = _fetch_duel(c, duel_id)
        if not duel:
            conn.close()
            raise HTTPException(status_code=404, detail="Дуэль не найдена")
        role = _duel_role(duel, telegram_id)
        if duel["status"] == "pending":
            if duel["opponent_id"] != telegram_id:
                conn.close()
                raise HTTPException(status_code=403, detail="Это не твой вызов")
            next_status = "declined"
            notify_id = duel["challenger_id"]
        elif duel["status"] in ("accepted", "ready") and role:
            next_status = "cancelled"
            notify_id = duel["opponent_id"] if role == "challenger" else duel["challenger_id"]
        else:
            conn.close()
            raise HTTPException(status_code=409, detail="Дуэль уже нельзя отклонить")
        c.execute("UPDATE duels SET status=?, updated_at=? WHERE id=?", (next_status, now_iso(), duel_id))
        conn.commit()
        conn.close()
        return {"notify_id": notify_id, "status": next_status}

    res = await db_write(_run)
    await send_telegram_message(
        res["notify_id"],
        "⚔️ Твой вызов на дуэль отклонён." if res["status"] == "declined" else "⚔️ Дуэль отменена до старта боя.",
    )
    return {"success": True}


@app.post("/api/duel/{duel_id}/cancel")
async def duel_cancel(duel_id: int, data: dict):
    telegram_id = data.get("telegram_id")

    def _run():
        conn = get_conn()
        c = conn.cursor()
        duel = _fetch_duel(c, duel_id)
        if not duel:
            conn.close()
            raise HTTPException(status_code=404, detail="Дуэль не найдена")
        if duel["challenger_id"] != telegram_id:
            conn.close()
            raise HTTPException(status_code=403, detail="Это не твой вызов")
        if duel["status"] not in ("pending", "accepted", "ready"):
            conn.close()
            raise HTTPException(status_code=409, detail="Дуэль уже нельзя отменить")
        c.execute("UPDATE duels SET status='cancelled', updated_at=? WHERE id=?", (now_iso(), duel_id))
        conn.commit()
        conn.close()
        return True

    await db_write(_run)
    return {"success": True}


@app.post("/api/duel/{duel_id}/ready")
async def duel_ready(duel_id: int, data: dict):
    telegram_id = data.get("telegram_id")

    def _run():
        conn = get_conn()
        c = conn.cursor()
        duel = _fetch_duel(c, duel_id)
        if not duel:
            conn.close()
            raise HTTPException(status_code=404, detail="Дуэль не найдена")
        role = _duel_role(duel, telegram_id)
        if not role:
            conn.close()
            raise HTTPException(status_code=403, detail="Ты не участник дуэли")
        compatible, challenger_group, opponent_group = _duel_groups_compatible(c, duel["challenger_id"], duel["opponent_id"])
        if not compatible:
            conn.close()
            raise HTTPException(status_code=403, detail="Дуэль доступна только внутри своей учебной группы")
        if duel["status"] not in ("accepted", "ready"):
            conn.close()
            raise HTTPException(status_code=409, detail="Сейчас нельзя готовиться")
        now = now_iso()
        col = "challenger_ready" if role == "challenger" else "opponent_ready"
        c.execute(f"UPDATE duels SET {col}=1, status='ready', updated_at=? WHERE id=?", (now, duel_id))
        duel = _fetch_duel(c, duel_id)
        if duel["challenger_ready"] and duel["opponent_ready"]:
            q = choose_duel_question(c, study_group=_duel_match_study_group(c, duel))
            c.execute(
                "UPDATE duels SET status='active', round_no=1, current_question_id=?, round_started_at=?, "
                "challenger_hp=?, opponent_hp=?, updated_at=? WHERE id=?",
                (q["id"] if q else None, now, DUEL_MAX_HP, DUEL_MAX_HP, now, duel_id),
            )
        conn.commit()
        conn.close()
        return True

    await db_write(_run)
    return {"success": True}


@app.post("/api/duel/{duel_id}/answer")
async def duel_answer(duel_id: int, data: dict):
    telegram_id = data.get("telegram_id")
    option = data.get("option")
    question_id = data.get("question_id")

    def _run():
        conn = get_conn()
        c = conn.cursor()
        duel = _fetch_duel(c, duel_id)
        if not duel:
            conn.close()
            raise HTTPException(status_code=404, detail="Дуэль не найдена")
        role = _duel_role(duel, telegram_id)
        if not role:
            conn.close()
            raise HTTPException(status_code=403, detail="Ты не участник дуэли")
        if duel["status"] != "active":
            conn.close()
            raise HTTPException(status_code=409, detail="Бой не идёт")
        if option not in ("a", "b", "c"):
            conn.close()
            raise HTTPException(status_code=400, detail="Неверный вариант")
        if question_id and int(question_id) != duel["current_question_id"]:
            conn.close()
            raise HTTPException(status_code=409, detail="Раунд уже сменился")
        ans_col = "challenger_answer" if role == "challenger" else "opponent_answer"
        at_col = "challenger_answer_at" if role == "challenger" else "opponent_answer_at"
        if duel[ans_col] is None:
            now = now_iso()
            c.execute(f"UPDATE duels SET {ans_col}=?, {at_col}=?, updated_at=? WHERE id=?", (option, now, now, duel_id))
            duel = _fetch_duel(c, duel_id)
            if _round_due(duel):
                duel = _resolve_round(c, duel)
            conn.commit()
        conn.close()
        return duel

    duel = await db_write(_run)
    return _public_duel_state(duel, telegram_id)


@app.get("/api/duel/{duel_id}/state")
async def duel_state(duel_id: int, telegram_id: int):
    def _read_duel():
        conn = get_conn()
        c = conn.cursor()
        d = _fetch_duel(c, duel_id)
        conn.close()
        return d
    duel = await db_read(_read_duel, label="duel_state_fetch")
    if duel and duel["status"] == "active" and _round_due(duel):
        duel = await db_write(lambda: _resolve_round_locked(duel_id))
    return await db_read(lambda: _public_duel_state(duel, telegram_id), label="duel_state_public")


@app.get("/api/duel/leaderboard")
def duel_leaderboard(
    x_telegram_id: Optional[int] = Header(None),
    x_admin_id: Optional[int] = Header(None),
    x_cohort_code: Optional[str] = Header(None),
):
    conn = get_conn()
    c = conn.cursor()
    viewer_id = get_request_actor_id(x_telegram_id, x_admin_id)
    cohort_code = resolve_viewer_cohort(c, viewer_id, x_cohort_code)
    c.execute(
        "SELECT winner_id, COUNT(*) FROM duels WHERE status='finished' AND winner_id IS NOT NULL GROUP BY winner_id"
    )
    wins = {r[0]: r[1] for r in c.fetchall()}
    c.execute(
        "SELECT CASE WHEN winner_id=challenger_id THEN opponent_id ELSE challenger_id END AS loser, COUNT(*) "
        "FROM duels WHERE status='finished' AND winner_id IS NOT NULL GROUP BY loser"
    )
    losses = {r[0]: r[1] for r in c.fetchall()}
    # Admin and FLATLINED duel activity is operational/sanctioned noise.
    ids = (set(wins) | set(losses)) - set(ADMIN_IDS) - FLATLINED_IDS
    names = {}
    if ids:
        qmarks = ",".join("?" * len(ids))
        c.execute(
            f"SELECT telegram_id, full_name, avatar_url FROM users "
            f"WHERE cohort_code=? AND telegram_id IN ({qmarks})",
            (cohort_code, *tuple(ids)),
        )
        names = {r[0]: (r[1], r[2]) for r in c.fetchall()}
        ids &= set(names)
    conn.close()
    board = []
    for tid in ids:
        w = wins.get(tid, 0)
        l = losses.get(tid, 0)
        nm = names.get(tid, (str(tid), None))
        board.append({"telegram_id": tid, "name": nm[0], "avatar_url": nm[1], "wins": w, "losses": l, "total": w + l})
    board.sort(key=lambda x: (-x["wins"], x["losses"], -x["total"]))
    return {"leaderboard": board}


@app.get("/api/duel/opponents/{telegram_id}")
def duel_opponents(
    telegram_id: int,
    x_cohort_code: Optional[str] = Header(None),
):
    """Pickable opponents. Students are group-matched against students.
    Admins can challenge anyone, but students cannot challenge admins."""
    conn = get_conn()
    c = conn.cursor()
    viewer_group = _duel_user_study_group(c, telegram_id)
    cohort_code = resolve_viewer_cohort(c, telegram_id, x_cohort_code)
    c.execute(
        "SELECT telegram_id, full_name, avatar_url, COALESCE(rep_score,0), study_group FROM users "
        "WHERE telegram_id IS NOT NULL AND telegram_id!=? AND cohort_code=? "
        "ORDER BY full_name COLLATE NOCASE",
        (telegram_id, cohort_code),
    )
    rows = c.fetchall()
    conn.close()
    out = []
    for r in rows:
        if not DUELS_PUBLIC and r[0] not in ADMIN_IDS:
            continue
        opponent_group = normalize_study_group(r[4])
        if telegram_id not in ADMIN_IDS:
            if r[0] in ADMIN_IDS:
                continue
            if not viewer_group:
                continue
            if opponent_group != viewer_group:
                continue
        required_stake = _duel_required_stake(telegram_id, r[0])
        out.append({
            "telegram_id": r[0],
            "name": r[1] or str(r[0]),
            "avatar_url": r[2],
            "rep": r[3],
            "study_group": study_group_payload(opponent_group),
            "is_admin": r[0] in ADMIN_IDS,
            "required_stake": required_stake,
            "stake_tiers": [required_stake] if required_stake is not None else DUEL_STAKE_TIERS,
        })
    message = ""
    if DUELS_PUBLIC and telegram_id not in ADMIN_IDS and not viewer_group and not out:
        message = "Сначала попроси вожатого назначить учебную группу"
    return {
        "opponents": out,
        "enabled": _duel_allowed(telegram_id),
        "study_group": study_group_payload(viewer_group),
        "message": message,
    }
