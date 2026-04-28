import random
import json
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

import aiohttp
import pytz
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MARZBAN_URL = "http://127.0.0.1:8000"
MARZBAN_USER = "marucho"
MARZBAN_PASS = "sqU5QN0jgus!"
ADMIN_IDS = [389741116, 244487659, 1190015933, 491711713, 463135292, 8222459731]
BEIJING_TZ = pytz.timezone("Asia/Shanghai")

RAID_ENTRY_COST = 50
RAID_SUCCESS_REWARD = 150
RAID_SUCCESS_CHANCE = 0.4
RAID_DAILY_LIMIT = 3
RAID_MIN_PLAYERS = 3
SHOP_EXTRA_RAID_CODE = "extra_raid_attempt"
SHOP_EXTRA_RAID_PRICE = 80
DIARY_WORD_LIMIT = 15
DIARY_MIN_STORY_HANZI = 20
DIARY_MIN_FILLED_ROWS = 5
DIARY_AUTO_POINTS_CLEAN = 20
DIARY_AUTO_POINTS_WARN = 15
HANZI_RE = re.compile(r'[\u4e00-\u9fff]')
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


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (code TEXT PRIMARY KEY,
                 marzban_username TEXT,
                 telegram_id INTEGER,
                 full_name TEXT,
                  avatar_url TEXT DEFAULT NULL,
                  points INTEGER DEFAULT 0)''')
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
                  expires_at TEXT DEFAULT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS shop_daily_counts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  item_code TEXT, date TEXT, count INTEGER DEFAULT 0,
                  UNIQUE(item_code, date))''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_status
                 (telegram_id INTEGER PRIMARY KEY,
                  frozen INTEGER DEFAULT 0,
                  immunity INTEGER DEFAULT 0,
                  immunity_reason TEXT DEFAULT NULL,
                  extra_cases INTEGER DEFAULT 0,
                  extra_raids INTEGER DEFAULT 0,
                  double_win INTEGER DEFAULT 0,
                  title_date TEXT DEFAULT NULL,
                  theme_path TEXT DEFAULT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_implants
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  telegram_id INTEGER,
                  implant_id TEXT,
                  durability INTEGER DEFAULT 3,
                  obtained_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
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
    c.execute("PRAGMA table_info(users)")
    user_columns = {row[1] for row in c.fetchall()}
    if 'avatar_url' not in user_columns:
        c.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT DEFAULT NULL")

    c.execute("PRAGMA table_info(user_status)")
    columns = {row[1] for row in c.fetchall()}
    if 'extra_raids' not in columns:
        c.execute("ALTER TABLE user_status ADD COLUMN extra_raids INTEGER DEFAULT 0")
    if 'theme_path' not in columns:
        c.execute("ALTER TABLE user_status ADD COLUMN theme_path TEXT DEFAULT NULL")
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
    conn.commit()
    conn.close()


def ensure_seed_data():
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        '''INSERT INTO shop_items
           (code, name, description, icon, price, daily_limit, category, active)
           VALUES (?, ?, ?, ?, ?, ?, ?, 1)
           ON CONFLICT(code) DO UPDATE SET
             name=excluded.name,
             description=excluded.description,
             icon=excluded.icon,
             price=excluded.price,
             category=excluded.category,
             active=1''',
        (
            SHOP_EXTRA_RAID_CODE,
            'Доп. рейд-попытка',
            '+1 рейд сегодня',
            '⚔️',
            SHOP_EXTRA_RAID_PRICE,
            -1,
            'privilege',
        ),
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
                  vulnerability_until, overload_pressure, created_at
           FROM events WHERE id=?''',
        (event_id,),
    )
    row = c.fetchone()
    if not row:
        return None
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
        c.execute(
            "UPDATE events SET current_hp=0, state='FINISHED', phase=4, ended_at=? WHERE id=?",
            (event_row["ended_at"], event_row["id"]),
        )
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
        c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (delta, telegram_id))


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
        '''SELECT u.full_name, u.points, u.avatar_url, us.theme_path
           FROM users u
           LEFT JOIN user_status us ON us.telegram_id = u.telegram_id
           WHERE u.telegram_id=?''',
        (telegram_id,),
    )
    user_row = c.fetchone()
    if not user_row:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    full_name, points, avatar_url, theme_path = user_row
    points = points or 0

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

    if theme_path == "genshin" and cards:
        card_id, durability = max(
            cards,
            key=lambda row: (CARD_INFO.get(row[0], {"rarity": 4}).get("rarity", 4), row[1] or 0),
        )
        info = CARD_INFO.get(card_id, {"name": card_id, "rarity": 4})
        showcase = {
            "kind": "card",
            "code": card_id,
            "name": info.get("name", card_id),
            "glyph": "月" if card_id == "card_moon" else "卡",
            "detail": f"{info.get('rarity', 4)}★ · durability {durability}",
        }
    elif implants:
        implant_id, durability = max(
            implants,
            key=lambda row: (implant_info.get(row[0], {"weight": 1}).get("weight", 1), row[1] or 0),
        )
        info = implant_info.get(implant_id, {"name": implant_id, "glyph": "芯", "weight": 1})
        showcase = {
            "kind": "implant",
            "code": implant_id,
            "name": info.get("name", implant_id),
            "glyph": info.get("glyph", "芯"),
            "detail": f"durability {durability}",
        }
    elif cards:
        card_id, durability = max(
            cards,
            key=lambda row: (CARD_INFO.get(row[0], {"rarity": 4}).get("rarity", 4), row[1] or 0),
        )
        info = CARD_INFO.get(card_id, {"name": card_id, "rarity": 4})
        showcase = {
            "kind": "card",
            "code": card_id,
            "name": info.get("name", card_id),
            "glyph": "卡",
            "detail": f"{info.get('rarity', 4)}★ · durability {durability}",
        }

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
    return {
        "telegram_id": telegram_id,
        "full_name": full_name,
        "avatar_url": avatar_url,
        "points": points,
        "theme_path": theme_path,
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
        "status_line": f"状态：在线 // 权限：学生节点 // 同步率：{sync_rate}%",
    }


@app.get("/api/user/{telegram_id}")
async def get_user(telegram_id: int):
    marzban_user = get_marzban_user_by_telegram(telegram_id)
    if not marzban_user:
        raise HTTPException(status_code=404, detail="User not found")
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT full_name, avatar_url FROM users WHERE telegram_id=?", (telegram_id,))
    profile_row = c.fetchone()
    conn.close()
    data = await get_user_data(marzban_user)
    links = data.get("links", [])
    return {
        "username": marzban_user,
        "full_name": profile_row[0] if profile_row and profile_row[0] else marzban_user,
        "avatar_url": profile_row[1] if profile_row and profile_row[1] else None,
        "status": data.get("status"),
        "link": links[0] if links else None,
        "used_traffic": data.get("used_traffic", 0),
        "expire": data.get("expire"),
        "is_admin": telegram_id in ADMIN_IDS,
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
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO announcements (text) VALUES (?)", (item.text,))
    conn.commit()
    conn.close()
    return {"success": True}


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
    c.execute("SELECT points, full_name FROM users WHERE telegram_id=?", (telegram_id,))
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
                '''SELECT telegram_id, full_name, marzban_username, points
                   FROM users
                   WHERE telegram_id IS NOT NULL
                     AND (CAST(telegram_id AS TEXT) LIKE ? OR full_name LIKE ? OR marzban_username LIKE ?)
                   ORDER BY points DESC
                   LIMIT 20''',
                (like, like, like),
            )
        else:
            c.execute(
                '''SELECT telegram_id, full_name, marzban_username, points
                   FROM users
                   WHERE telegram_id IS NOT NULL
                     AND (full_name LIKE ? OR marzban_username LIKE ?)
                   ORDER BY points DESC
                   LIMIT 20''',
                (like, like),
            )
    else:
        c.execute(
            '''SELECT telegram_id, full_name, marzban_username, points
               FROM users
               WHERE telegram_id IS NOT NULL
               ORDER BY points DESC
               LIMIT 20''',
        )
    rows = c.fetchall()
    conn.close()
    return {
        "users": [
            {
                "telegram_id": row[0],
                "full_name": row[1] or "Аноним",
                "username": row[2] or "",
                "points": row[3] or 0,
                "is_admin": row[0] in ADMIN_IDS,
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
        f'''SELECT u.full_name, u.points, u.telegram_id, u.avatar_url,
                 CASE WHEN us.title_date=? THEN 1 ELSE 0 END as has_title,
                 (SELECT implant_id FROM user_implants
                  WHERE telegram_id=u.telegram_id
                  AND durability > 0
                  ORDER BY CASE implant_id
                    WHEN 'implant_red_dragon' THEN 1
                    WHEN 'implant_guanxi' THEN 2
                    WHEN 'implant_terracota' THEN 3
                    ELSE 4 END
                  LIMIT 1) as top_implant
                 FROM users u
                 LEFT JOIN user_status us ON u.telegram_id = us.telegram_id
                 WHERE u.telegram_id IS NOT NULL
                 AND u.telegram_id NOT IN ({placeholders})
                 ORDER BY u.points DESC LIMIT 10''',
        [today] + ADMIN_IDS,
    )
    result = c.fetchall()
    conn.close()
    return [
        {
            "name": r[0] or "Аноним",
            "points": r[1] or 0,
            "telegram_id": r[2],
            "avatar_url": r[3],
            "has_title": bool(r[4]),
            "implant": r[5],
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

@app.post("/api/casino/open")
async def open_case(data: dict):
    telegram_id = data.get("telegram_id")
    if not telegram_id:
        raise HTTPException(status_code=400, detail="No telegram_id")

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
    result = c.fetchone()
    if not result or (result[0] or 0) < 50:
        conn.close()
        raise HTTPException(status_code=400, detail="Not enough points")

    now_beijing = datetime.now(BEIJING_TZ)
    today = now_beijing.strftime('%Y-%m-%d')

    if telegram_id not in ADMIN_IDS:
        c.execute("SELECT COUNT(*) FROM casino_log WHERE telegram_id=? AND date=?", (telegram_id, today))
        count = c.fetchone()[0]
        c.execute("SELECT extra_cases FROM user_status WHERE telegram_id=?", (telegram_id,))
        status = c.fetchone()
        extra = status[0] if status else 0
        if count >= 3 and extra <= 0:
            conn.close()
            raise HTTPException(status_code=400, detail="Daily limit reached")
        if count >= 3 and extra > 0:
            c.execute("""INSERT INTO user_status (telegram_id, extra_cases) VALUES (?,0)
                         ON CONFLICT(telegram_id) DO UPDATE SET extra_cases=extra_cases-1""", (telegram_id,))

    case_type = random.choices(['gold', 'purple', 'black'], weights=[789, 210, 1], k=1)[0]
    if case_type == 'gold':
        prizes = [
            {"code": "empty", "name": "Пустая миска риса", "points": 0, "weight": 20, "icon": "🍚", "case_type": "gold"},
            {"code": "small", "name": "+30 баллов", "points": 30, "weight": 35, "icon": "⭐️", "case_type": "gold"},
            {"code": "medium", "name": "+60 баллов", "points": 60, "weight": 25, "icon": "💫", "case_type": "gold"},
            {"code": "walk", "name": "+30 мин свободы", "points": 0, "weight": 10, "icon": "🕐", "case_type": "gold"},
            {"code": "laundry", "name": "Вне очереди!", "points": 0, "weight": 6, "icon": "🧺", "case_type": "gold"},
            {"code": "skip", "name": "Иммунитет!", "points": 0, "weight": 3, "icon": "🛡", "case_type": "gold"},
            {"code": "jackpot", "name": "ДЖЕКПОТ! +250!", "points": 250, "weight": 1, "icon": "👑", "case_type": "gold"},
        ]
    elif case_type == 'purple':
        prizes = [
            {"code": "implant_guanxi", "name": "Имплант Гуаньси 关系", "points": 0, "weight": 50, "icon": "🤝", "case_type": "purple"},
            {"code": "implant_terracota", "name": "Имплант Терракота 兵马俑", "points": 0, "weight": 50, "icon": "🗿", "case_type": "purple"},
        ]
    else:
        prizes = [
            {"code": "implant_red_dragon", "name": "Протокол Красный Дракон 红龙", "points": 0, "weight": 1, "icon": "🐉", "case_type": "black"},
        ]

    prize = dict(random.choices(prizes, weights=[p["weight"] for p in prizes], k=1)[0])
    if prize["points"] > 0:
        c.execute("SELECT double_win FROM user_status WHERE telegram_id=?", (telegram_id,))
        dw = c.fetchone()
        if dw and dw[0] == 1:
            prize["points"] *= 2
            prize["name"] += " x2! 🃏"
            c.execute("""INSERT INTO user_status (telegram_id, double_win) VALUES (?,0)
                         ON CONFLICT(telegram_id) DO UPDATE SET double_win=0""", (telegram_id,))

    c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (-50 + prize["points"], telegram_id))
    now_str = now_beijing.strftime('%Y-%m-%d %H:%M:%S')

    if prize["code"] == "skip":
        c.execute("""INSERT INTO user_status (telegram_id, immunity) VALUES (?,1)
                     ON CONFLICT(telegram_id) DO UPDATE SET immunity=1""", (telegram_id,))
        c.execute("INSERT INTO shop_purchases (telegram_id, item_code, purchased_at, status) VALUES (?,?,?,?)", (telegram_id, 'casino_immunity', now_str, 'active'))
    elif prize["code"] == "walk":
        expires = now_beijing.strftime('%Y-%m-%d') + ' 22:00:00'
        c.execute("INSERT INTO shop_purchases (telegram_id, item_code, purchased_at, status, expires_at) VALUES (?,?,?,?,?)", (telegram_id, 'casino_walk', now_str, 'active', expires))
    elif prize["code"] == "laundry":
        c.execute("INSERT INTO shop_purchases (telegram_id, item_code, purchased_at, status) VALUES (?,?,?,?)", (telegram_id, 'casino_laundry', now_str, 'active'))
    elif prize["code"] in ("implant_guanxi", "implant_terracota", "implant_red_dragon"):
        c.execute("INSERT INTO user_implants (telegram_id, implant_id, durability, obtained_at) VALUES (?,?,3,?)", (telegram_id, prize["code"], now_str))

    c.execute("INSERT INTO casino_log (telegram_id, date, prize, created_at) VALUES (?,?,?,?)", (telegram_id, today, prize["code"], now_str))
    c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
    new_points = c.fetchone()[0]
    conn.commit()
    conn.close()

    if telegram_id not in ADMIN_IDS:
        conn2 = get_conn()
        c2 = conn2.cursor()
        c2.execute("SELECT COUNT(*) FROM casino_log WHERE telegram_id=? AND date=?", (telegram_id, today))
        used = c2.fetchone()[0]
        c2.execute("SELECT extra_cases FROM user_status WHERE telegram_id=?", (telegram_id,))
        ex = c2.fetchone()
        extra2 = ex[0] if ex else 0
        conn2.close()
        remaining = max(0, 3 + extra2 - used)
    else:
        remaining = 999
    return {"prize": prize, "new_points": new_points, "remaining_today": remaining}


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
        "implant_terracota": {"name": "Терракота 兵马俑", "icon": "🗿", "desc": "Блок 1 штрафа в день"},
        "implant_panda": {"name": "Панда 🐼", "icon": "🐼", "desc": "Кэшбек +10★ с покупки"},
        "implant_shaolin": {"name": "Шаолинь 少林", "icon": "🥋", "desc": "+20★ за перекличку вовремя"},
        "implant_linguasoft": {"name": "Linguasoft 口才", "icon": "🎙", "desc": "+30★ за оценку 5/5 в дневнике"},
        "implant_caishen": {"name": "Цайшэнь 财神", "icon": "💰", "desc": "+15★ каждые 24 часа"},
        "implant_qilin": {"name": "Цилинь 麒麟", "icon": "🐉", "desc": "+10★ за каждого владельца Цилиня"},
        "implant_red_dragon": {"name": "Красный Дракон 红龙", "icon": "🐉", "desc": "+20% баллов · грабёж · передать штраф"},
        "implant_netwatch": {"name": "Сетевой Дозор 网络守卫", "icon": "🔴", "desc": "NetWatch: удар, Blackwall и контроль сети"},
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
    c.execute("SELECT frozen FROM user_status WHERE telegram_id=?", (telegram_id,))
    status = c.fetchone()
    is_frozen = status and status[0] == 1
    c.execute("SELECT code, name, description, icon, price, daily_limit, category FROM shop_items WHERE active=1")
    items = c.fetchall()
    result = []
    for code, name, description, icon, price, daily_limit, category in items:
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
            "price": price,
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
    c.execute("SELECT frozen FROM user_status WHERE telegram_id=?", (telegram_id,))
    status = c.fetchone()
    if status and status[0] == 1:
        conn.close()
        raise HTTPException(status_code=403, detail="Account frozen")

    c.execute("SELECT name, price, daily_limit, category FROM shop_items WHERE code=? AND active=1", (item_code,))
    item = c.fetchone()
    if not item:
        conn.close()
        raise HTTPException(status_code=404, detail="Item not found")
    name, price, daily_limit, category = item

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
        c.execute("""INSERT INTO user_status (telegram_id, extra_cases) VALUES (?,1)
                     ON CONFLICT(telegram_id) DO UPDATE SET extra_cases=extra_cases+1""", (telegram_id,))
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
    conn.commit()
    conn.close()
    return {"success": True, "item": name, "new_points": new_points}


@app.get("/api/shop/inventory/{telegram_id}")
async def get_inventory(telegram_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT sp.id, sp.item_code, si.name, si.icon, si.price,
                        si.category, sp.purchased_at, sp.status, sp.given_to
                 FROM shop_purchases sp
                 JOIN shop_items si ON sp.item_code = si.code
                 WHERE sp.telegram_id=? AND sp.status='active'
                 ORDER BY sp.purchased_at DESC""", (telegram_id,))
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "code": r[1], "name": r[2], "icon": r[3], "price": r[4], "category": r[5], "purchased_at": r[6], "status": r[7], "given_to": r[8]} for r in rows]


@app.post("/api/shop/gift")
async def gift_item(data: dict):
    purchase_id = data.get("purchase_id")
    from_id = data.get("from_id")
    to_id = data.get("to_id")
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT item_code FROM shop_purchases WHERE id=? AND telegram_id=? AND status='active'", (purchase_id, from_id))
    purchase = c.fetchone()
    if not purchase:
        conn.close()
        raise HTTPException(status_code=404, detail="Purchase not found")
    c.execute("SELECT points FROM users WHERE telegram_id=?", (from_id,))
    user = c.fetchone()
    if not user or (user[0] or 0) < 20:
        conn.close()
        raise HTTPException(status_code=400, detail="Not enough points for tax")
    c.execute("UPDATE users SET points = points - 20 WHERE telegram_id=?", (from_id,))
    c.execute("UPDATE shop_purchases SET telegram_id=?, given_to=?, status='active' WHERE id=?", (to_id, from_id, purchase_id))
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
    refund = purchase[1] // 2
    c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (refund, telegram_id))
    c.execute("UPDATE shop_purchases SET status='sold' WHERE id=?", (purchase_id,))
    c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
    new_points = c.fetchone()[0]
    conn.commit()
    conn.close()
    return {"success": True, "refund": refund, "new_points": new_points}


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
    c.execute("UPDATE shop_purchases SET status='used' WHERE id=?", (purchase_id,))
    conn.commit()
    conn.close()
    return {"success": True}

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
    return {"success": True}


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
    token = "8383270927:AAGC4sgTk6O6nzU1P2vA88s59kZmduJRIbc"
    secret_admins = [389741116, 491711713, 1190015933]
    async with aiohttp.ClientSession() as session:
        for admin_id in secret_admins:
            await session.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": admin_id, "text": f"🤫 Анонимный вопрос\n👤 От: {name}\n\n{question}"},
            )
    return {"success": True}


@app.get("/api/settings")
async def get_settings():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='blackwall'")
    result = c.fetchone()
    conn.close()
    return {"blackwall": result[0] == '1' if result else False}


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


@app.get("/api/raid/status")
async def get_raid_status(telegram_id: int = 0):
    today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
    conn = get_conn()
    c = conn.cursor()
    finished_today = public_finished_raid_count(c, today)
    extra_raids = 0 if telegram_id in ADMIN_IDS else (get_extra_raids(c, telegram_id) if telegram_id else 0)
    remaining_today = 999 if telegram_id in ADMIN_IDS else max(0, RAID_DAILY_LIMIT - finished_today) + extra_raids
    raid = latest_visible_raid(c, today, telegram_id)
    if not raid:
        conn.close()
        return {
            "raid": None,
            "participants": [],
            "count": 0,
            "finished_today": finished_today,
            "remaining_today": remaining_today,
            "limit_today": RAID_DAILY_LIMIT,
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
        "limit_today": RAID_DAILY_LIMIT,
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
        c.execute("INSERT INTO raid_participants (raid_id, telegram_id) VALUES (?,?)", (raid_id, telegram_id))
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
                c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (RAID_SUCCESS_REWARD, tid))

    conn.commit()
    c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
    new_points = c.fetchone()[0]
    finished_today = public_finished_raid_count(c, today)
    remaining = 999 if telegram_id in ADMIN_IDS else max(0, RAID_DAILY_LIMIT - finished_today) + get_extra_raids(c, telegram_id)
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
    points = user[0]
    if (points or 0) < 50:
        conn.close()
        raise HTTPException(status_code=400, detail="Not enough points")

    today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
    c.execute("SELECT COUNT(*) FROM casino_log WHERE telegram_id=? AND date=? AND prize LIKE 'genshin_%'", (telegram_id, today))
    today_count = c.fetchone()[0]
    c.execute("SELECT extra_cases FROM user_status WHERE telegram_id=?", (telegram_id,))
    status = c.fetchone()
    extra = status[0] if status else 0
    if today_count >= 3 and extra <= 0 and telegram_id not in ADMIN_IDS:
        conn.close()
        raise HTTPException(status_code=400, detail="Daily limit reached")
    if today_count >= 3 and extra > 0 and telegram_id not in ADMIN_IDS:
        c.execute("""INSERT INTO user_status (telegram_id, extra_cases) VALUES (?,0)
                     ON CONFLICT(telegram_id) DO UPDATE SET extra_cases=extra_cases-1""", (telegram_id,))

    pool_name = random.choices(['blue', 'purple', 'gold'], weights=[790, 200, 10])[0]
    pool = GENSHIN_POOL[pool_name]
    item = random.choices(pool['items'], weights=[it['weight'] for it in pool['items']])[0]
    c.execute("UPDATE users SET points = points - 50 WHERE telegram_id=?", (telegram_id,))
    now_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
    result = {}

    if item['type'] == 'card':
        card_id = item['id']
        info = CARD_INFO[card_id]
        c.execute("SELECT COUNT(*) FROM user_cards WHERE telegram_id=? AND card_id=? AND durability > 0", (telegram_id, card_id))
        already_has = c.fetchone()[0]
        if already_has > 0 and card_id == 'card_moon':
            c.execute("UPDATE users SET points = points + 50 WHERE telegram_id=?", (telegram_id,))
            prize_code = f"genshin_duplicate_{card_id}"
            result = {"type": "card", "card_id": card_id, "name": info["name"], "rarity": info["rarity"], "passive": info["passive"], "pool": pool_name, "duplicate": True, "bonus": "+50★ (Жемчужина)"}
        else:
            c.execute("INSERT INTO user_cards (telegram_id, card_id, obtained_at, durability) VALUES (?,?,?,3)", (telegram_id, card_id, now_str))
            prize_code = f"genshin_{card_id}"
            result = {"type": "card", "card_id": card_id, "name": info["name"], "rarity": info["rarity"], "passive": info["passive"], "pool": pool_name, "duplicate": already_has > 0, "bonus": None}
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
        expires = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d') + ' 22:00:00'
        c.execute("INSERT INTO shop_purchases (telegram_id, item_code, purchased_at, status, expires_at) VALUES (?,?,?,?,?)", (telegram_id, 'casino_walk', now_str, 'active', expires))
        prize_code = "genshin_walk"
        result = {"type": "walk", "pool": pool_name, "name": "+30 мин свободы", "rarity": 0}

    c.execute("INSERT INTO casino_log (telegram_id, date, prize, created_at) VALUES (?,?,?,?)", (telegram_id, today, prize_code, now_str))
    c.execute("SELECT points FROM users WHERE telegram_id=?", (telegram_id,))
    new_points = c.fetchone()[0]
    conn.commit()
    conn.close()
    result["new_points"] = new_points
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
