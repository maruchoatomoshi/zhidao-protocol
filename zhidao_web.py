"""Standalone web edition of ZHIDAO Protocol.

This application intentionally uses its own SQLite database.  The legacy
Telegram Mini App, travel data and /root/zhidao.db are not modified.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
DB_PATH = Path(os.getenv("ZHIDAO_WEB_DB_PATH", str(ROOT / "data" / "zhidao_web.db"))).resolve()
UPLOAD_ROOT = Path(os.getenv("ZHIDAO_UPLOAD_PATH", str(ROOT / "uploads" / "learning"))).resolve()
TRAVEL_URL = os.getenv(
    "ZHIDAO_TRAVEL_URL",
    "https://maruchoatomoshi.github.io/zhidao-protocol/",
).strip()
COOKIE_NAME = "zhidao_session"
SESSION_DAYS = max(1, int(os.getenv("ZHIDAO_SESSION_DAYS", "7") or "7"))
COOKIE_SECURE = os.getenv("ZHIDAO_COOKIE_SECURE", "0").lower() in {"1", "true", "yes", "on"}
MAX_VOICE_BYTES = max(256_000, int(os.getenv("ZHIDAO_MAX_VOICE_BYTES", "6000000") or "6000000"))

DB_PATH.parent.mkdir(parents=True, exist_ok=True)
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

DB_LOCK = threading.RLock()
LOGIN_FAILURES: dict[str, list[float]] = {}
LOGIN_LOCK = threading.Lock()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def hash_secret(secret: str) -> str:
    if len(secret) < 4:
        raise ValueError("Секрет должен содержать минимум 4 символа")
    salt = secrets.token_bytes(16)
    n, r, p = 2**14, 8, 1
    digest = hashlib.scrypt(secret.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32)
    return "scrypt${}${}${}${}${}".format(
        n,
        r,
        p,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_secret(secret: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = encoded.split("$", 5)
        if scheme != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
        actual = hashlib.scrypt(
            secret.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


CHAPTER_SEEDS = [
    {
        "id": "chapter-greetings",
        "order_index": 1,
        "title": "Приветствие и знакомство",
        "subtitle": "Глава 01 // Первый сигнал",
    },
    {
        "id": "chapter-form-scan",
        "order_index": 2,
        "title": "Форма и биометрия",
        "subtitle": "Глава 02 // Контур объекта",
    },
]


MISSION_SEEDS = [
    {
        "id": "mission-first-contact",
        "chapter_id": "chapter-greetings",
        "order_index": 1,
        "title": "Первый контакт",
        "subtitle": "Установи безопасное соединение",
        "lore": "В городском секторе замечен новый оператор. Архитектор поручает тебе передать первый дружественный сигнал.",
        "reward_xp": 80,
        "reward_stars": 15,
        "reward_code": "first_contact",
        "reward_title": "Знак первого контакта",
        "content": {
            "lesson_label": "ЗАНЯТИЕ 01 // CONTACT NODE",
            "words": [
                {"hanzi": "你好", "pinyin": "Nǐ hǎo", "translation": "привет"},
                {"hanzi": "我叫……", "pinyin": "Wǒ jiào…", "translation": "меня зовут…"},
            ],
            "tasks": [
                {
                    "id": "m1-meaning",
                    "type": "choice",
                    "prompt": "Что означает 你好?",
                    "focus": {"hanzi": "你好", "pinyin": "Nǐ hǎo"},
                    "options": ["Привет", "Спасибо", "До свидания"],
                    "correct": "Привет",
                    "explanation": "你好 — привет или здравствуй.",
                },
                {
                    "id": "m1-signal",
                    "type": "choice",
                    "prompt": "Как передать: «Меня зовут…»?",
                    "focus": {"hanzi": "我叫……", "pinyin": "Wǒ jiào…"},
                    "options": ["你叫……", "我叫……", "再见"],
                    "option_pinyin": {
                        "你叫……": "Nǐ jiào…",
                        "我叫……": "Wǒ jiào…",
                        "再见": "Zàijiàn",
                    },
                    "correct": "我叫……",
                    "explanation": "我 — я, 叫 — называться.",
                },
                {
                    "id": "m1-order",
                    "type": "order",
                    "prompt": "Собери фразу в правильном порядке",
                    "options": ["我", "叫", "小明"],
                    "token_pinyin": {"我": "wǒ", "叫": "jiào", "小明": "Xiǎomíng"},
                    "correct": ["我", "叫", "小明"],
                    "explanation": "Сначала 我, затем 叫 и имя.",
                },
                {
                    "id": "m1-write",
                    "type": "written",
                    "prompt": "Напиши своё имя по формуле: 我叫……",
                    "focus": {"hanzi": "我叫……", "pinyin": "Wǒ jiào…"},
                    "placeholder": "我叫……",
                    "required": True,
                },
            ],
        },
    },
    {
        "id": "mission-handshake",
        "chapter_id": "chapter-greetings",
        "order_index": 2,
        "title": "Протокол рукопожатия",
        "subtitle": "Заверши первый диалог",
        "lore": "Связь установлена. Теперь новый оператор должен узнать твоё имя и безопасно завершить сеанс.",
        "reward_xp": 120,
        "reward_stars": 20,
        "reward_code": "handshake_complete",
        "reward_title": "Ключ рукопожатия",
        "content": {
            "lesson_label": "ЗАНЯТИЕ 02 // HANDSHAKE",
            "words": [
                {"hanzi": "你叫什么名字？", "pinyin": "Nǐ jiào shénme míngzi?", "translation": "как тебя зовут?"},
                {"hanzi": "再见", "pinyin": "Zàijiàn", "translation": "до свидания"},
            ],
            "tasks": [
                {
                    "id": "m2-answer",
                    "type": "choice",
                    "prompt": "Что ответить на 你叫什么名字？",
                    "focus": {"hanzi": "你叫什么名字？", "pinyin": "Nǐ jiào shénme míngzi?"},
                    "options": ["我叫……", "再见", "你好？"],
                    "option_pinyin": {
                        "我叫……": "Wǒ jiào…",
                        "再见": "Zàijiàn",
                        "你好？": "Nǐ hǎo?",
                    },
                    "correct": "我叫……",
                    "explanation": "В ответ называем себя: 我叫 + имя.",
                },
                {
                    "id": "m2-goodbye",
                    "type": "choice",
                    "prompt": "Как завершить разговор?",
                    "focus": {"hanzi": "再见", "pinyin": "Zàijiàn"},
                    "options": ["我叫", "再见", "什么"],
                    "option_pinyin": {"我叫": "Wǒ jiào", "再见": "Zàijiàn", "什么": "shénme"},
                    "correct": "再见",
                    "explanation": "再见 — до свидания.",
                },
                {
                    "id": "m2-dialogue",
                    "type": "order",
                    "prompt": "Восстанови короткий диалог",
                    "options": ["你好！", "你叫什么名字？", "我叫小明。", "再见！"],
                    "token_pinyin": {
                        "你好！": "Nǐ hǎo!",
                        "你叫什么名字？": "Nǐ jiào shénme míngzi?",
                        "我叫小明。": "Wǒ jiào Xiǎomíng.",
                        "再见！": "Zàijiàn!",
                    },
                    "correct": ["你好！", "你叫什么名字？", "我叫小明。", "再见！"],
                    "explanation": "Приветствие → вопрос → ответ → прощание.",
                },
                {
                    "id": "m2-voice",
                    "type": "voice",
                    "prompt": "Запиши голосовой сигнал: 你好！我叫……。再见！",
                    "focus": {
                        "hanzi": "你好！我叫……。再见！",
                        "pinyin": "Nǐ hǎo! Wǒ jiào… Zàijiàn!",
                    },
                    "required": True,
                },
            ],
        },
    },
    {
        "id": "mission-scale-protocol",
        "chapter_id": "chapter-form-scan",
        "order_index": 1,
        "title": "Протокол масштаба",
        "subtitle": "Калибруй признаки объектов",
        "lore": "Сканеры Неон-Сити потеряли масштаб. Архитектор передаёт четыре сигнала: определи, что большое, маленькое, длинное и высокое.",
        "reward_xp": 100,
        "reward_stars": 18,
        "reward_code": "scale_calibrator",
        "reward_title": "Калибровщик формы",
        "content": {
            "lesson_label": "ЗАНЯТИЕ 03 // SCALE PROTOCOL",
            "glyph": "尺",
            "signal_code": "scale",
            "words": [
                {"hanzi": "小", "pinyin": "xiǎo", "translation": "маленький"},
                {"hanzi": "大", "pinyin": "dà", "translation": "большой"},
                {"hanzi": "长", "pinyin": "cháng", "translation": "длинный"},
                {"hanzi": "高", "pinyin": "gāo", "translation": "высокий"},
            ],
            "tasks": [
                {
                    "id": "scale-big",
                    "type": "choice",
                    "prompt": "Что означает 大?",
                    "options": ["большой", "маленький", "длинный"],
                    "correct": "большой",
                    "explanation": "大 — большой.",
                },
                {
                    "id": "scale-small",
                    "type": "choice",
                    "prompt": "Как передать сигнал «маленький»?",
                    "options": ["大", "小", "高"],
                    "option_pinyin": {"大": "dà", "小": "xiǎo", "高": "gāo"},
                    "correct": "小",
                    "explanation": "小 — маленький.",
                },
                {
                    "id": "scale-giraffe",
                    "type": "choice",
                    "prompt": "Какой сигнал подходит для высокого жирафа?",
                    "options": ["长", "高", "小"],
                    "option_pinyin": {"长": "cháng", "高": "gāo", "小": "xiǎo"},
                    "correct": "高",
                    "explanation": "高 описывает высокий рост.",
                },
                {
                    "id": "scale-snake",
                    "type": "choice",
                    "prompt": "Какой сигнал подходит для длинной змеи?",
                    "options": ["大", "长", "高"],
                    "option_pinyin": {"大": "dà", "长": "cháng", "高": "gāo"},
                    "correct": "长",
                    "explanation": "长 — длинный.",
                },
                {
                    "id": "scale-voice",
                    "type": "voice",
                    "prompt": "Передай четыре сигнала по-китайски: большой, маленький, длинный, высокий.",
                    "required": True,
                },
            ],
        },
    },
    {
        "id": "mission-biometric-scan",
        "chapter_id": "chapter-form-scan",
        "order_index": 2,
        "title": "Биометрический скан",
        "subtitle": "Собери контур киберзверя",
        "lore": "В архив поступил неизвестный киберзверь. Восстанови его биометрический профиль по частям тела и отправь Архитектору голосовое описание.",
        "reward_xp": 130,
        "reward_stars": 24,
        "reward_code": "biometric_scan",
        "reward_title": "Знак биосканера",
        "content": {
            "lesson_label": "ЗАНЯТИЕ 04 // BIOMETRIC SCAN",
            "glyph": "体",
            "signal_code": "body",
            "words": [
                {"hanzi": "手", "pinyin": "shǒu", "translation": "рука"},
                {"hanzi": "鼻子", "pinyin": "bízi", "translation": "нос"},
                {"hanzi": "耳朵", "pinyin": "ěrduo", "translation": "ухо"},
                {"hanzi": "眼睛", "pinyin": "yǎnjing", "translation": "глаза"},
                {"hanzi": "头发", "pinyin": "tóufa", "translation": "волосы"},
            ],
            "tasks": [
                {
                    "id": "body-eyes",
                    "type": "choice",
                    "prompt": "Что означает 眼睛?",
                    "options": ["глаза", "уши", "волосы"],
                    "correct": "глаза",
                    "explanation": "眼睛 — глаза.",
                },
                {
                    "id": "body-nose",
                    "type": "choice",
                    "prompt": "Как передать сигнал «нос»?",
                    "options": ["手", "鼻子", "耳朵"],
                    "option_pinyin": {"手": "shǒu", "鼻子": "bízi", "耳朵": "ěrduo"},
                    "correct": "鼻子",
                    "explanation": "鼻子 — нос.",
                },
                {
                    "id": "body-hair",
                    "type": "choice",
                    "prompt": "Как передать сигнал «волосы»?",
                    "options": ["眼睛", "头发", "手"],
                    "option_pinyin": {"眼睛": "yǎnjing", "头发": "tóufa", "手": "shǒu"},
                    "correct": "头发",
                    "explanation": "头发 — волосы.",
                },
                {
                    "id": "body-order",
                    "type": "order",
                    "prompt": "Собери фразу: «У меня большие глаза»",
                    "options": ["我的", "眼睛", "很", "大"],
                    "token_pinyin": {"我的": "wǒ de", "眼睛": "yǎnjing", "很": "hěn", "大": "dà"},
                    "correct": ["我的", "眼睛", "很", "大"],
                    "explanation": "我的眼睛很大 — у меня большие глаза.",
                },
                {
                    "id": "body-voice",
                    "type": "voice",
                    "prompt": "Опиши киберзверя двумя фразами: какие у него глаза и какой нос?",
                    "coach": {
                        "hanzi": "它的眼睛很……。它的鼻子很……。",
                        "pinyin": "Tā de yǎnjing hěn… Tā de bízi hěn…",
                    },
                    "required": True,
                },
            ],
        },
    },
]


def init_db() -> None:
    with DB_LOCK:
        conn = db_connect()
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS web_users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('student','teacher')),
                secret_hash TEXT NOT NULL,
                avatar_code TEXT NOT NULL DEFAULT 'operator',
                stars INTEGER NOT NULL DEFAULT 0,
                rep_score INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS web_sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES web_users(id) ON DELETE CASCADE,
                csrf_token TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS learning_profiles (
                user_id TEXT PRIMARY KEY REFERENCES web_users(id) ON DELETE CASCADE,
                xp INTEGER NOT NULL DEFAULT 0,
                level INTEGER NOT NULL DEFAULT 1,
                lesson_streak INTEGER NOT NULL DEFAULT 0,
                last_completed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS learning_chapters (
                id TEXT PRIMARY KEY,
                order_index INTEGER NOT NULL,
                title TEXT NOT NULL,
                subtitle TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'published',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS learning_missions (
                id TEXT PRIMARY KEY,
                chapter_id TEXT NOT NULL REFERENCES learning_chapters(id),
                order_index INTEGER NOT NULL,
                title TEXT NOT NULL,
                subtitle TEXT NOT NULL,
                lore TEXT NOT NULL,
                content_json TEXT NOT NULL,
                reward_xp INTEGER NOT NULL DEFAULT 0,
                reward_stars INTEGER NOT NULL DEFAULT 0,
                reward_code TEXT NOT NULL,
                reward_title TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'published',
                created_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS learning_assignments (
                id TEXT PRIMARY KEY,
                mission_id TEXT NOT NULL REFERENCES learning_missions(id),
                student_id TEXT NOT NULL REFERENCES web_users(id),
                status TEXT NOT NULL DEFAULT 'assigned',
                mission_snapshot_json TEXT NOT NULL,
                assigned_at TEXT NOT NULL,
                started_at TEXT,
                submitted_at TEXT,
                reviewed_at TEXT,
                reviewed_by TEXT,
                feedback TEXT NOT NULL DEFAULT '',
                UNIQUE(mission_id, student_id)
            );
            CREATE TABLE IF NOT EXISTS learning_attempts (
                assignment_id TEXT NOT NULL REFERENCES learning_assignments(id) ON DELETE CASCADE,
                step_id TEXT NOT NULL,
                answer_json TEXT NOT NULL,
                is_correct INTEGER,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(assignment_id, step_id)
            );
            CREATE TABLE IF NOT EXISTS learning_submissions (
                id TEXT PRIMARY KEY,
                assignment_id TEXT NOT NULL UNIQUE REFERENCES learning_assignments(id) ON DELETE CASCADE,
                written_answer TEXT NOT NULL DEFAULT '',
                voice_filename TEXT,
                voice_mime TEXT,
                auto_score INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'submitted',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS learning_reward_log (
                id TEXT PRIMARY KEY,
                assignment_id TEXT NOT NULL UNIQUE REFERENCES learning_assignments(id),
                user_id TEXT NOT NULL REFERENCES web_users(id),
                xp INTEGER NOT NULL,
                stars INTEGER NOT NULL,
                reward_code TEXT NOT NULL,
                reward_title TEXT NOT NULL,
                awarded_by TEXT NOT NULL,
                awarded_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS mentor_messages (
                id TEXT PRIMARY KEY,
                student_id TEXT NOT NULL REFERENCES web_users(id) ON DELETE CASCADE,
                author_id TEXT REFERENCES web_users(id),
                text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                read_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_learning_assignments_student
              ON learning_assignments(student_id, status);
            CREATE INDEX IF NOT EXISTS idx_mentor_messages_student
              ON mentor_messages(student_id, created_at DESC);
            """
        )
        now = utc_now()
        for chapter in CHAPTER_SEEDS:
            conn.execute(
                """INSERT OR IGNORE INTO learning_chapters
                   (id, order_index, title, subtitle, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'published', ?, ?)""",
                (
                    chapter["id"],
                    chapter["order_index"],
                    chapter["title"],
                    chapter["subtitle"],
                    now,
                    now,
                ),
            )
        for seed in MISSION_SEEDS:
            conn.execute(
                """INSERT OR IGNORE INTO learning_missions
                   (id, chapter_id, order_index, title, subtitle, lore, content_json,
                    reward_xp, reward_stars, reward_code, reward_title, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    seed["id"],
                    seed["chapter_id"],
                    seed["order_index"],
                    seed["title"],
                    seed["subtitle"],
                    seed["lore"],
                    json.dumps(seed["content"], ensure_ascii=False),
                    seed["reward_xp"],
                    seed["reward_stars"],
                    seed["reward_code"],
                    seed["reward_title"],
                    now,
                    now,
                ),
            )
        conn.commit()
        conn.close()
    seed_accounts_from_env()


def mission_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "chapter_id": row["chapter_id"],
        "order_index": row["order_index"],
        "title": row["title"],
        "subtitle": row["subtitle"],
        "lore": row["lore"],
        "content": json.loads(row["content_json"]),
        "reward_xp": row["reward_xp"],
        "reward_stars": row["reward_stars"],
        "reward_code": row["reward_code"],
        "reward_title": row["reward_title"],
        "version": row["version"],
        "status": row["status"],
    }


def ensure_first_assignment(conn: sqlite3.Connection, student_id: str) -> None:
    row = conn.execute(
        """SELECT m.* FROM learning_missions m
           JOIN learning_chapters c ON c.id=m.chapter_id
           WHERE m.status='published' AND c.status='published'
           ORDER BY c.order_index, m.order_index LIMIT 1"""
    ).fetchone()
    if not row:
        return
    payload = mission_payload(row)
    conn.execute(
        """INSERT OR IGNORE INTO learning_assignments
           (id, mission_id, student_id, status, mission_snapshot_json, assigned_at)
           VALUES (?, ?, ?, 'assigned', ?, ?)""",
        (str(uuid.uuid4()), row["id"], student_id, json.dumps(payload, ensure_ascii=False), utc_now()),
    )


def create_or_update_user(
    username: str,
    display_name: str,
    role: Literal["student", "teacher"],
    secret: str,
) -> str:
    username = username.strip().lower()
    display_name = display_name.strip()
    if not username or not display_name:
        raise ValueError("Имя входа и отображаемое имя обязательны")
    now = utc_now()
    with DB_LOCK:
        conn = db_connect()
        existing = conn.execute("SELECT id FROM web_users WHERE username=?", (username,)).fetchone()
        user_id = existing["id"] if existing else str(uuid.uuid4())
        encoded = hash_secret(secret)
        conn.execute(
            """INSERT INTO web_users
               (id, username, display_name, role, secret_hash, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(username) DO UPDATE SET
                 display_name=excluded.display_name,
                 role=excluded.role,
                 secret_hash=excluded.secret_hash,
                 active=1,
                 updated_at=excluded.updated_at""",
            (user_id, username, display_name, role, encoded, now, now),
        )
        if role == "student":
            conn.execute(
                """INSERT OR IGNORE INTO learning_profiles
                   (user_id, xp, level, lesson_streak, created_at, updated_at)
                   VALUES (?, 0, 1, 0, ?, ?)""",
                (user_id, now, now),
            )
            ensure_first_assignment(conn, user_id)
        conn.commit()
        conn.close()
    return user_id


def seed_accounts_from_env() -> None:
    teacher_username = os.getenv("ZHIDAO_TEACHER_USERNAME", "").strip()
    teacher_password = os.getenv("ZHIDAO_TEACHER_PASSWORD", "")
    student_username = os.getenv("ZHIDAO_STUDENT_USERNAME", "").strip()
    student_pin = os.getenv("ZHIDAO_STUDENT_PIN", "")
    if teacher_username and teacher_password:
        with db_connect() as conn:
            exists = conn.execute("SELECT 1 FROM web_users WHERE username=?", (teacher_username,)).fetchone()
        if not exists:
            create_or_update_user(
                teacher_username,
                os.getenv("ZHIDAO_TEACHER_NAME", "Марк Альбертович"),
                "teacher",
                teacher_password,
            )
    if student_username and student_pin:
        with db_connect() as conn:
            exists = conn.execute("SELECT 1 FROM web_users WHERE username=?", (student_username,)).fetchone()
        if not exists:
            create_or_update_user(
                student_username,
                os.getenv("ZHIDAO_STUDENT_NAME", "Оператор"),
                "student",
                student_pin,
            )


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    secret: str = Field(min_length=4, max_length=128)


class AnswerRequest(BaseModel):
    step_id: str = Field(min_length=1, max_length=80)
    answer: Any


class SubmitRequest(BaseModel):
    written_answer: str = Field(default="", max_length=1000)


class ReviewRequest(BaseModel):
    decision: Literal["approve", "revise"]
    feedback: str = Field(default="", max_length=600)
    xp: Optional[int] = Field(default=None, ge=0, le=1000)
    stars: Optional[int] = Field(default=None, ge=0, le=500)
    unlock_next: bool = True


class MessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=400)


class MissionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    subtitle: str = Field(default="", max_length=160)
    lore: str = Field(default="", max_length=1200)
    order_index: int = Field(ge=1, le=999)
    reward_xp: int = Field(default=50, ge=0, le=1000)
    reward_stars: int = Field(default=10, ge=0, le=500)
    reward_code: str = Field(min_length=1, max_length=80)
    reward_title: str = Field(min_length=1, max_length=120)
    content: dict[str, Any]


class AssignRequest(BaseModel):
    student_id: str


def public_user(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "role": row["role"],
        "avatar_code": row["avatar_code"],
        "stars": row["stars"],
    }


def session_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(conn: sqlite3.Connection, user_id: str) -> tuple[str, str, str]:
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    conn.execute(
        """INSERT INTO web_sessions (token_hash, user_id, csrf_token, expires_at, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (session_hash(token), user_id, csrf, expires.replace(microsecond=0).isoformat(), utc_now()),
    )
    return token, csrf, expires.replace(microsecond=0).isoformat()


def current_session(request: Request) -> dict[str, Any]:
    token = request.cookies.get(COOKIE_NAME, "")
    if not token:
        raise HTTPException(status_code=401, detail="Требуется вход")
    conn = db_connect()
    row = conn.execute(
        """SELECT s.token_hash, s.csrf_token, s.expires_at,
                  u.id, u.username, u.display_name, u.role, u.avatar_code, u.stars, u.active
           FROM web_sessions s JOIN web_users u ON u.id=s.user_id
           WHERE s.token_hash=?""",
        (session_hash(token),),
    ).fetchone()
    conn.close()
    if not row or not row["active"]:
        raise HTTPException(status_code=401, detail="Сессия недействительна")
    try:
        if datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Сессия истекла")
    except ValueError:
        raise HTTPException(status_code=401, detail="Сессия повреждена")
    return dict(row)


def require_role(role: str):
    def dependency(session: dict[str, Any] = Depends(current_session)) -> dict[str, Any]:
        if session["role"] != role:
            raise HTTPException(status_code=403, detail="Недостаточно прав")
        return session

    return dependency


def require_csrf(request: Request, session: dict[str, Any], supplied: Optional[str]) -> None:
    if not supplied or not hmac.compare_digest(supplied, session["csrf_token"]):
        raise HTTPException(status_code=403, detail="CSRF-проверка не пройдена")


def login_locked(key: str) -> bool:
    cutoff = time.time() - 600
    with LOGIN_LOCK:
        attempts = [ts for ts in LOGIN_FAILURES.get(key, []) if ts > cutoff]
        LOGIN_FAILURES[key] = attempts
        return len(attempts) >= 5


def record_login_failure(key: str) -> None:
    with LOGIN_LOCK:
        LOGIN_FAILURES.setdefault(key, []).append(time.time())


def clear_login_failures(key: str) -> None:
    with LOGIN_LOCK:
        LOGIN_FAILURES.pop(key, None)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="ZHIDAO Learning Protocol", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=WEB_ROOT), name="static")


@app.get("/", include_in_schema=False)
def student_page():
    return FileResponse(WEB_ROOT / "index.html")


@app.get("/teacher", include_in_schema=False)
def teacher_page():
    return FileResponse(WEB_ROOT / "teacher.html")


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    return FileResponse(WEB_ROOT / "sw.js", media_type="application/javascript")


@app.get("/travel", include_in_schema=False)
def travel_page():
    return RedirectResponse(TRAVEL_URL, status_code=302)


ARCHITECT_MEDIA = {
    "explaining": ROOT / "architect_explaining.png",
    "happy": ROOT / "architect_happy.png",
    "thinking": ROOT / "atchitect_thinking.png",
    "surprising": ROOT / "architect_surprising.png",
    "logo": ROOT / "architect_logo.png",
}


@app.get("/media/architect/{name}", include_in_schema=False)
def architect_media(name: str):
    path = ARCHITECT_MEDIA.get(name)
    if not path or not path.is_file():
        raise HTTPException(status_code=404, detail="Изображение не найдено")
    return FileResponse(path)


@app.get("/api/health")
def health():
    conn = db_connect()
    conn.execute("SELECT 1").fetchone()
    conn.close()
    return {"status": "ok", "mode": "learning-web"}


@app.get("/api/public/setup")
def setup_status():
    conn = db_connect()
    counts = {
        row["role"]: row["count"]
        for row in conn.execute("SELECT role, COUNT(*) AS count FROM web_users WHERE active=1 GROUP BY role")
    }
    conn.close()
    return {"ready": bool(counts.get("student") and counts.get("teacher"))}


@app.post("/api/auth/login")
def login(data: LoginRequest, request: Request, response: Response):
    username = data.username.strip().lower()
    key = f"{request.client.host if request.client else 'unknown'}:{username}"
    if login_locked(key):
        raise HTTPException(status_code=429, detail="Слишком много попыток. Подожди 10 минут")
    conn = db_connect()
    row = conn.execute("SELECT * FROM web_users WHERE username=? AND active=1", (username,)).fetchone()
    if not row or not verify_secret(data.secret, row["secret_hash"]):
        conn.close()
        record_login_failure(key)
        raise HTTPException(status_code=401, detail="Неверное имя или код доступа")
    token, csrf, expires = create_session(conn, row["id"])
    conn.commit()
    conn.close()
    clear_login_failures(key)
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
    return {"user": public_user(row), "csrf_token": csrf, "expires_at": expires}


@app.get("/api/auth/me")
def auth_me(session: dict[str, Any] = Depends(current_session)):
    return {
        "user": {k: session[k] for k in ("id", "username", "display_name", "role", "avatar_code", "stars")},
        "csrf_token": session["csrf_token"],
    }


@app.post("/api/auth/logout")
def logout(
    request: Request,
    response: Response,
    x_csrf_token: Optional[str] = Header(default=None),
    session: dict[str, Any] = Depends(current_session),
):
    require_csrf(request, session, x_csrf_token)
    conn = db_connect()
    conn.execute("DELETE FROM web_sessions WHERE token_hash=?", (session["token_hash"],))
    conn.commit()
    conn.close()
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@app.get("/api/student/dashboard")
def student_dashboard(session: dict[str, Any] = Depends(require_role("student"))):
    conn = db_connect()
    profile = conn.execute("SELECT * FROM learning_profiles WHERE user_id=?", (session["id"],)).fetchone()
    chapter = conn.execute(
        """SELECT c.* FROM learning_chapters c
           JOIN learning_missions m ON m.chapter_id=c.id
           JOIN learning_assignments a ON a.mission_id=m.id
           WHERE a.student_id=? AND c.status='published'
           ORDER BY
             CASE WHEN a.status IN ('assigned','in_progress','submitted','revision_requested') THEN 0 ELSE 1 END,
             a.assigned_at DESC,
             c.order_index DESC
           LIMIT 1""",
        (session["id"],),
    ).fetchone()
    if not chapter:
        chapter = conn.execute(
            "SELECT * FROM learning_chapters WHERE status='published' ORDER BY order_index LIMIT 1"
        ).fetchone()
    rows = conn.execute(
        """SELECT m.*, a.id AS assignment_id, a.status AS assignment_status,
                  a.feedback, a.submitted_at
           FROM learning_missions m
           LEFT JOIN learning_assignments a ON a.mission_id=m.id AND a.student_id=?
           WHERE m.chapter_id=? AND m.status='published'
           ORDER BY m.order_index""",
        (session["id"], chapter["id"]),
    ).fetchall()
    missions = []
    for row in rows:
        status = row["assignment_status"] or "locked"
        content = json.loads(row["content_json"])
        missions.append(
            {
                "id": row["id"],
                "assignment_id": row["assignment_id"],
                "order_index": row["order_index"],
                "title": row["title"],
                "subtitle": row["subtitle"],
                "reward_xp": row["reward_xp"],
                "reward_stars": row["reward_stars"],
                "status": status,
                "feedback": row["feedback"] or "",
                "focus_words": content.get("words", [])[:3],
                "glyph": content.get("glyph", "任"),
                "signal_code": content.get("signal_code", "core"),
            }
        )
    rewards = [
        dict(row)
        for row in conn.execute(
            """SELECT reward_code, reward_title, xp, stars, awarded_at
               FROM learning_reward_log WHERE user_id=? ORDER BY awarded_at DESC""",
            (session["id"],),
        ).fetchall()
    ]
    messages = [
        dict(row)
        for row in conn.execute(
            """SELECT mm.id, mm.text, mm.created_at, u.display_name AS author_name
               FROM mentor_messages mm LEFT JOIN web_users u ON u.id=mm.author_id
               WHERE mm.student_id=? ORDER BY mm.created_at DESC LIMIT 5""",
            (session["id"],),
        ).fetchall()
    ]
    conn.close()
    xp = profile["xp"] if profile else 0
    return {
        "user": {k: session[k] for k in ("id", "display_name", "avatar_code", "stars")},
        "profile": {
            "xp": xp,
            "level": profile["level"] if profile else 1,
            "lesson_streak": profile["lesson_streak"] if profile else 0,
            "level_floor": ((xp // 200) * 200),
            "level_ceiling": ((xp // 200) + 1) * 200,
        },
        "chapter": dict(chapter) if chapter else None,
        "missions": missions,
        "rewards": rewards,
        "messages": messages,
    }


def student_assignment(conn: sqlite3.Connection, student_id: str, mission_id: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM learning_assignments WHERE student_id=? AND mission_id=?",
        (student_id, mission_id),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=403, detail="Миссия пока заблокирована")
    return row


@app.get("/api/student/missions/{mission_id}")
def get_student_mission(mission_id: str, session: dict[str, Any] = Depends(require_role("student"))):
    conn = db_connect()
    assignment = student_assignment(conn, session["id"], mission_id)
    attempts = {
        row["step_id"]: {"answer": json.loads(row["answer_json"]), "is_correct": row["is_correct"]}
        for row in conn.execute(
            "SELECT step_id, answer_json, is_correct FROM learning_attempts WHERE assignment_id=?",
            (assignment["id"],),
        ).fetchall()
    }
    submission = conn.execute(
        "SELECT written_answer, voice_filename, status FROM learning_submissions WHERE assignment_id=?",
        (assignment["id"],),
    ).fetchone()
    conn.close()
    return {
        "assignment_id": assignment["id"],
        "status": assignment["status"],
        "feedback": assignment["feedback"],
        "mission": json.loads(assignment["mission_snapshot_json"]),
        "attempts": attempts,
        "submission": dict(submission) if submission else None,
    }


@app.post("/api/student/missions/{mission_id}/start")
def start_mission(
    mission_id: str,
    request: Request,
    x_csrf_token: Optional[str] = Header(default=None),
    session: dict[str, Any] = Depends(require_role("student")),
):
    require_csrf(request, session, x_csrf_token)
    conn = db_connect()
    assignment = student_assignment(conn, session["id"], mission_id)
    if assignment["status"] in {"assigned", "revision_requested"}:
        conn.execute(
            "UPDATE learning_assignments SET status='in_progress', started_at=COALESCE(started_at, ?) WHERE id=?",
            (utc_now(), assignment["id"]),
        )
        conn.commit()
    conn.close()
    return {"ok": True}


def grade_task(task: dict[str, Any], answer: Any) -> Optional[bool]:
    if task.get("type") not in {"choice", "order"}:
        return None
    expected = task.get("correct")
    if isinstance(expected, list):
        return list(answer or []) == expected
    return str(answer).strip() == str(expected).strip()


@app.post("/api/student/missions/{mission_id}/answer")
def answer_mission(
    mission_id: str,
    data: AnswerRequest,
    request: Request,
    x_csrf_token: Optional[str] = Header(default=None),
    session: dict[str, Any] = Depends(require_role("student")),
):
    require_csrf(request, session, x_csrf_token)
    conn = db_connect()
    assignment = student_assignment(conn, session["id"], mission_id)
    if assignment["status"] in {"submitted", "approved"}:
        conn.close()
        raise HTTPException(status_code=409, detail="Миссия уже отправлена")
    mission = json.loads(assignment["mission_snapshot_json"])
    task = next((item for item in mission["content"].get("tasks", []) if item.get("id") == data.step_id), None)
    if not task:
        conn.close()
        raise HTTPException(status_code=404, detail="Задание не найдено")
    correct = grade_task(task, data.answer)
    conn.execute(
        """INSERT INTO learning_attempts (assignment_id, step_id, answer_json, is_correct, updated_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(assignment_id, step_id) DO UPDATE SET
             answer_json=excluded.answer_json,
             is_correct=excluded.is_correct,
             updated_at=excluded.updated_at""",
        (
            assignment["id"],
            data.step_id,
            json.dumps(data.answer, ensure_ascii=False),
            None if correct is None else int(correct),
            utc_now(),
        ),
    )
    conn.execute(
        "UPDATE learning_assignments SET status='in_progress', started_at=COALESCE(started_at, ?) WHERE id=?",
        (utc_now(), assignment["id"]),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "is_correct": correct, "explanation": task.get("explanation", "")}


VOICE_MIME_EXTENSIONS = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
}


@app.post("/api/student/missions/{mission_id}/voice")
async def upload_voice(
    mission_id: str,
    request: Request,
    x_audio_mime: Optional[str] = Header(default=None),
    x_csrf_token: Optional[str] = Header(default=None),
    session: dict[str, Any] = Depends(require_role("student")),
):
    require_csrf(request, session, x_csrf_token)
    mime = (x_audio_mime or request.headers.get("content-type", "")).split(";", 1)[0].strip().lower()
    if mime not in VOICE_MIME_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Неподдерживаемый формат аудио")
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_VOICE_BYTES:
            raise HTTPException(status_code=413, detail="Запись слишком большая")
        chunks.append(chunk)
    body = b"".join(chunks)
    if not body:
        raise HTTPException(status_code=413, detail="Запись пустая или слишком большая")
    conn = db_connect()
    assignment = student_assignment(conn, session["id"], mission_id)
    if assignment["status"] in {"submitted", "approved"}:
        conn.close()
        raise HTTPException(status_code=409, detail="Миссия уже отправлена")
    filename = f"{assignment['id']}-{uuid.uuid4().hex}{VOICE_MIME_EXTENSIONS[mime]}"
    (UPLOAD_ROOT / filename).write_bytes(body)
    now = utc_now()
    conn.execute(
        """INSERT INTO learning_submissions
           (id, assignment_id, voice_filename, voice_mime, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, 'draft', ?, ?)
           ON CONFLICT(assignment_id) DO UPDATE SET
             voice_filename=excluded.voice_filename,
             voice_mime=excluded.voice_mime,
             updated_at=excluded.updated_at""",
        (str(uuid.uuid4()), assignment["id"], filename, mime, now, now),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "filename": filename}


@app.post("/api/student/missions/{mission_id}/submit")
def submit_mission(
    mission_id: str,
    data: SubmitRequest,
    request: Request,
    x_csrf_token: Optional[str] = Header(default=None),
    session: dict[str, Any] = Depends(require_role("student")),
):
    require_csrf(request, session, x_csrf_token)
    conn = db_connect()
    assignment = student_assignment(conn, session["id"], mission_id)
    if assignment["status"] == "approved":
        conn.close()
        raise HTTPException(status_code=409, detail="Миссия уже принята")
    mission = json.loads(assignment["mission_snapshot_json"])
    tasks = mission["content"].get("tasks", [])
    attempts = conn.execute(
        "SELECT step_id, is_correct FROM learning_attempts WHERE assignment_id=?",
        (assignment["id"],),
    ).fetchall()
    attempted_ids = {row["step_id"] for row in attempts}
    required_written = any(task.get("type") == "written" and task.get("required") for task in tasks)
    required_voice = any(task.get("type") == "voice" and task.get("required") for task in tasks)
    submission = conn.execute(
        "SELECT * FROM learning_submissions WHERE assignment_id=?",
        (assignment["id"],),
    ).fetchone()
    auto_tasks = [task for task in tasks if task.get("type") in {"choice", "order"}]
    if any(task["id"] not in attempted_ids for task in auto_tasks):
        conn.close()
        raise HTTPException(status_code=400, detail="Сначала выполни все короткие задания")
    if required_written and not data.written_answer.strip():
        conn.close()
        raise HTTPException(status_code=400, detail="Добавь письменный ответ")
    if required_voice and (not submission or not submission["voice_filename"]):
        conn.close()
        raise HTTPException(status_code=400, detail="Добавь голосовой ответ")
    correct_count = sum(1 for row in attempts if row["is_correct"] == 1)
    score = round(correct_count * 100 / max(1, len(auto_tasks)))
    now = utc_now()
    conn.execute(
        """INSERT INTO learning_submissions
           (id, assignment_id, written_answer, auto_score, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, 'submitted', ?, ?)
           ON CONFLICT(assignment_id) DO UPDATE SET
             written_answer=excluded.written_answer,
             auto_score=excluded.auto_score,
             status='submitted',
             updated_at=excluded.updated_at""",
        (str(uuid.uuid4()), assignment["id"], data.written_answer.strip(), score, now, now),
    )
    conn.execute(
        "UPDATE learning_assignments SET status='submitted', submitted_at=? WHERE id=?",
        (now, assignment["id"]),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "auto_score": score}


@app.get("/api/teacher/overview")
def teacher_overview(session: dict[str, Any] = Depends(require_role("teacher"))):
    conn = db_connect()
    students = []
    for row in conn.execute(
        """SELECT u.id, u.username, u.display_name, u.stars,
                  p.xp, p.level, p.lesson_streak, p.last_completed_at
           FROM web_users u LEFT JOIN learning_profiles p ON p.user_id=u.id
           WHERE u.role='student' AND u.active=1 ORDER BY u.display_name"""
    ).fetchall():
        status_counts = {
            item["status"]: item["count"]
            for item in conn.execute(
                """SELECT status, COUNT(*) AS count FROM learning_assignments
                   WHERE student_id=? GROUP BY status""",
                (row["id"],),
            ).fetchall()
        }
        item = dict(row)
        item["assignment_counts"] = status_counts
        students.append(item)
    missions = [
        mission_payload(row)
        for row in conn.execute(
            """SELECT m.* FROM learning_missions m
               JOIN learning_chapters c ON c.id=m.chapter_id
               ORDER BY c.order_index, m.order_index"""
        ).fetchall()
    ]
    submissions = [
        dict(row)
        for row in conn.execute(
            """SELECT a.id AS assignment_id, a.status, a.submitted_at, a.feedback,
                      m.id AS mission_id, m.title AS mission_title,
                      u.id AS student_id, u.display_name AS student_name,
                      s.written_answer, s.voice_filename, s.auto_score, s.updated_at
               FROM learning_assignments a
               JOIN learning_missions m ON m.id=a.mission_id
               JOIN web_users u ON u.id=a.student_id
               LEFT JOIN learning_submissions s ON s.assignment_id=a.id
               WHERE a.status IN ('submitted','revision_requested','approved')
               ORDER BY COALESCE(a.submitted_at, a.assigned_at) DESC"""
        ).fetchall()
    ]
    conn.close()
    return {"teacher": {"display_name": session["display_name"]}, "students": students, "missions": missions, "submissions": submissions}


@app.post("/api/teacher/messages/{student_id}")
def send_mentor_message(
    student_id: str,
    data: MessageRequest,
    request: Request,
    x_csrf_token: Optional[str] = Header(default=None),
    session: dict[str, Any] = Depends(require_role("teacher")),
):
    require_csrf(request, session, x_csrf_token)
    conn = db_connect()
    exists = conn.execute("SELECT 1 FROM web_users WHERE id=? AND role='student'", (student_id,)).fetchone()
    if not exists:
        conn.close()
        raise HTTPException(status_code=404, detail="Ученик не найден")
    conn.execute(
        "INSERT INTO mentor_messages (id, student_id, author_id, text, created_at) VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), student_id, session["id"], data.text.strip(), utc_now()),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/teacher/missions")
def create_mission(
    data: MissionRequest,
    request: Request,
    x_csrf_token: Optional[str] = Header(default=None),
    session: dict[str, Any] = Depends(require_role("teacher")),
):
    require_csrf(request, session, x_csrf_token)
    mission_id = f"mission-{uuid.uuid4().hex[:12]}"
    now = utc_now()
    conn = db_connect()
    conn.execute(
        """INSERT INTO learning_missions
           (id, chapter_id, order_index, title, subtitle, lore, content_json,
            reward_xp, reward_stars, reward_code, reward_title, created_by, created_at, updated_at)
           VALUES (?, 'chapter-greetings', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            mission_id,
            data.order_index,
            data.title,
            data.subtitle,
            data.lore,
            json.dumps(data.content, ensure_ascii=False),
            data.reward_xp,
            data.reward_stars,
            data.reward_code,
            data.reward_title,
            session["id"],
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "id": mission_id}


@app.put("/api/teacher/missions/{mission_id}")
def update_mission(
    mission_id: str,
    data: MissionRequest,
    request: Request,
    x_csrf_token: Optional[str] = Header(default=None),
    session: dict[str, Any] = Depends(require_role("teacher")),
):
    require_csrf(request, session, x_csrf_token)
    conn = db_connect()
    cur = conn.execute(
        """UPDATE learning_missions SET
             order_index=?, title=?, subtitle=?, lore=?, content_json=?, reward_xp=?,
             reward_stars=?, reward_code=?, reward_title=?, version=version+1, updated_at=?
           WHERE id=?""",
        (
            data.order_index,
            data.title,
            data.subtitle,
            data.lore,
            json.dumps(data.content, ensure_ascii=False),
            data.reward_xp,
            data.reward_stars,
            data.reward_code,
            data.reward_title,
            utc_now(),
            mission_id,
        ),
    )
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Миссия не найдена")
    return {"ok": True}


@app.post("/api/teacher/missions/{mission_id}/assign")
def assign_mission(
    mission_id: str,
    data: AssignRequest,
    request: Request,
    x_csrf_token: Optional[str] = Header(default=None),
    session: dict[str, Any] = Depends(require_role("teacher")),
):
    require_csrf(request, session, x_csrf_token)
    conn = db_connect()
    mission = conn.execute("SELECT * FROM learning_missions WHERE id=?", (mission_id,)).fetchone()
    student = conn.execute("SELECT 1 FROM web_users WHERE id=? AND role='student'", (data.student_id,)).fetchone()
    if not mission or not student:
        conn.close()
        raise HTTPException(status_code=404, detail="Миссия или ученик не найдены")
    payload = mission_payload(mission)
    conn.execute(
        """INSERT OR IGNORE INTO learning_assignments
           (id, mission_id, student_id, status, mission_snapshot_json, assigned_at)
           VALUES (?, ?, ?, 'assigned', ?, ?)""",
        (str(uuid.uuid4()), mission_id, data.student_id, json.dumps(payload, ensure_ascii=False), utc_now()),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


def unlock_next_mission(conn: sqlite3.Connection, assignment: sqlite3.Row) -> None:
    current = conn.execute("SELECT * FROM learning_missions WHERE id=?", (assignment["mission_id"],)).fetchone()
    if not current:
        return
    nxt = conn.execute(
        """SELECT * FROM learning_missions
           WHERE chapter_id=? AND status='published' AND order_index>?
           ORDER BY order_index LIMIT 1""",
        (current["chapter_id"], current["order_index"]),
    ).fetchone()
    if not nxt:
        return
    conn.execute(
        """INSERT OR IGNORE INTO learning_assignments
           (id, mission_id, student_id, status, mission_snapshot_json, assigned_at)
           VALUES (?, ?, ?, 'assigned', ?, ?)""",
        (
            str(uuid.uuid4()),
            nxt["id"],
            assignment["student_id"],
            json.dumps(mission_payload(nxt), ensure_ascii=False),
            utc_now(),
        ),
    )


@app.post("/api/teacher/assignments/{assignment_id}/review")
def review_assignment(
    assignment_id: str,
    data: ReviewRequest,
    request: Request,
    x_csrf_token: Optional[str] = Header(default=None),
    session: dict[str, Any] = Depends(require_role("teacher")),
):
    require_csrf(request, session, x_csrf_token)
    with DB_LOCK:
        conn = db_connect()
        conn.execute("BEGIN IMMEDIATE")
        assignment = conn.execute("SELECT * FROM learning_assignments WHERE id=?", (assignment_id,)).fetchone()
        if not assignment:
            conn.rollback()
            conn.close()
            raise HTTPException(status_code=404, detail="Назначение не найдено")
        if data.decision == "revise":
            conn.execute(
                """UPDATE learning_assignments SET status='revision_requested', feedback=?,
                   reviewed_at=?, reviewed_by=? WHERE id=?""",
                (data.feedback.strip(), utc_now(), session["id"], assignment_id),
            )
            conn.execute(
                "UPDATE learning_submissions SET status='revision_requested', updated_at=? WHERE assignment_id=?",
                (utc_now(), assignment_id),
            )
            if data.feedback.strip():
                conn.execute(
                    "INSERT INTO mentor_messages (id, student_id, author_id, text, created_at) VALUES (?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), assignment["student_id"], session["id"], data.feedback.strip(), utc_now()),
                )
            conn.commit()
            conn.close()
            return {"ok": True, "status": "revision_requested"}
        if assignment["status"] == "approved":
            conn.rollback()
            conn.close()
            return {"ok": True, "status": "approved", "already_awarded": True}
        mission = conn.execute("SELECT * FROM learning_missions WHERE id=?", (assignment["mission_id"],)).fetchone()
        snapshot = json.loads(assignment["mission_snapshot_json"])
        xp = snapshot["reward_xp"] if data.xp is None else data.xp
        stars = snapshot["reward_stars"] if data.stars is None else data.stars
        reward_exists = conn.execute(
            "SELECT 1 FROM learning_reward_log WHERE assignment_id=?", (assignment_id,)
        ).fetchone()
        if not reward_exists:
            profile = conn.execute(
                "SELECT xp FROM learning_profiles WHERE user_id=?", (assignment["student_id"],)
            ).fetchone()
            new_xp = (profile["xp"] if profile else 0) + xp
            new_level = 1 + (new_xp // 200)
            conn.execute(
                """UPDATE learning_profiles SET xp=?, level=?, lesson_streak=lesson_streak+1,
                   last_completed_at=?, updated_at=? WHERE user_id=?""",
                (new_xp, new_level, utc_now(), utc_now(), assignment["student_id"]),
            )
            conn.execute("UPDATE web_users SET stars=stars+?, updated_at=? WHERE id=?", (stars, utc_now(), assignment["student_id"]))
            conn.execute(
                """INSERT INTO learning_reward_log
                   (id, assignment_id, user_id, xp, stars, reward_code, reward_title, awarded_by, awarded_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()),
                    assignment_id,
                    assignment["student_id"],
                    xp,
                    stars,
                    snapshot["reward_code"],
                    snapshot["reward_title"],
                    session["id"],
                    utc_now(),
                ),
            )
        feedback = data.feedback.strip() or "Сигнал принят. Отличная работа, оператор!"
        conn.execute(
            """UPDATE learning_assignments SET status='approved', feedback=?, reviewed_at=?, reviewed_by=?
               WHERE id=?""",
            (feedback, utc_now(), session["id"], assignment_id),
        )
        conn.execute(
            "UPDATE learning_submissions SET status='approved', updated_at=? WHERE assignment_id=?",
            (utc_now(), assignment_id),
        )
        conn.execute(
            "INSERT INTO mentor_messages (id, student_id, author_id, text, created_at) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), assignment["student_id"], session["id"], feedback, utc_now()),
        )
        if data.unlock_next:
            unlock_next_mission(conn, assignment)
        conn.commit()
        conn.close()
    return {"ok": True, "status": "approved", "xp": xp, "stars": stars}


@app.get("/api/teacher/audio/{filename}")
def teacher_audio(filename: str, _: dict[str, Any] = Depends(require_role("teacher"))):
    if Path(filename).name != filename:
        raise HTTPException(status_code=400, detail="Некорректное имя файла")
    path = UPLOAD_ROOT / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Запись не найдена")
    return FileResponse(path)
