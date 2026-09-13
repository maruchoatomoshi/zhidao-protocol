"""Захват кампуса (V4_GAMES.md §4.12). Все записи — внутри BEGIN IMMEDIATE.

По мотивам Ingress. Три цветные фракции на всю смену воюют за настоящие точки
кампуса. Чтобы сделать ход, нужно стоять у точки (GPS) и ответить на китайский
вопрос. Ход зависит от того, чья точка:

- ничья — фракция захватывает её на первом уровне;
- своя — укрепляет, до третьего уровня;
- чужая — пробивает защиту на уровень, а с первого уровня перехватывает.

Очки фракция копит за удержание: одно очко за каждые 10 минут на точку, но
только в дневные окна (10–12 и 15–18 по поясу сезона). Вне окон, ночью и когда
вожатый выключил игру, ходов нет и очки не идут.

Решения пользователя 2026-09-13: фракции, а не отряды; карта живёт всю смену;
очки в дневные окна. Дуэли, способности за ★ и награды — следующие этапы.

Точку нельзя выдумать (правило CLAUDE.md): точки — объекты campus.geojson, и
играть на точке можно только после того, как вожатый подтвердил её, стоя на
месте с точным GPS. До подтверждения участники точку не видят.

Приватность: точки и отрезки удержания принадлежат фракции. Кто захватил,
пробил или укрепил, не пишется нигде. Вопросы и кулдауны живут в памяти
процесса — перезапуск их просто сбрасывает.
"""
from __future__ import annotations

import json
import math
import random
import threading
from datetime import datetime, time, timedelta
from functools import lru_cache
from pathlib import Path

from . import campus, cases, cipher, rooms, shop, story
from .cases import CaseError, authorize

CONFIG_PATH = Path(__file__).parent / "static" / "app" / "assets" / "campus" / "capture.json"
_rng = random.SystemRandom()
QUESTION_OPTIONS = 3


def utcnow() -> datetime:
    return shop.utcnow()


@lru_cache(maxsize=1)
def config() -> dict:
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    factions = [f["code"] for f in data["factions"]]
    points = [p["code"] for p in data["points"]]
    if len(factions) < 2 or len(factions) != len(set(factions)):
        raise ValueError("capture.json: нужно не меньше двух фракций без повторов")
    if not points or len(points) != len(set(points)):
        raise ValueError("capture.json: точки пусты или с повторами")
    for point in data["points"]:
        if point["feature"] not in story.feature_centres():
            raise ValueError(f"capture.json: объекта {point['feature']} нет в campus.geojson")
    for key in ("daily_limit", "bonus", "questions", "sheet_seconds", "reaction_options", "round_seconds",
                "wins_needed", "max_rounds", "keep_minutes"):
        if type(data["duels"].get(key)) is not int or data["duels"][key] <= 0:
            raise ValueError(f"capture.json: duels.{key} должно быть положительным целым")
    for start, end in data["windows"]:
        if time.fromisoformat(start) >= time.fromisoformat(end):
            raise ValueError("capture.json: окно должно кончаться позже, чем начинается")
    return data


def factions() -> dict[str, dict]:
    return {f["code"]: f for f in config()["factions"]}


def points() -> dict[str, dict]:
    return {p["code"]: p for p in config()["points"]}


def distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# --- окна --------------------------------------------------------------------------------

def _zone(season):
    return shop._zone(season)


def windows_on(season, day) -> list[tuple[datetime, datetime]]:
    """Окна одного местного дня как отрезки UTC."""
    zone = _zone(season)
    result = []
    for start, end in config()["windows"]:
        a = datetime.combine(day, time.fromisoformat(start), tzinfo=zone)
        b = datetime.combine(day, time.fromisoformat(end), tzinfo=zone)
        result.append((a, b))
    return result


def window_state(season, now: datetime) -> dict:
    local = now.astimezone(_zone(season))
    for a, b in windows_on(season, local.date()):
        if a <= now < b:
            return {"open": True, "closes_at": b.isoformat()}
    upcoming = [a for day in (local.date(), local.date() + timedelta(days=1))
                for a, _ in windows_on(season, day) if a > now]
    return {"open": False, "opens_at": min(upcoming).isoformat() if upcoming else None}


def scored_minutes(season, since: datetime, until: datetime) -> float:
    """Сколько минут отрезка удержания пришлось на дневные окна."""
    if until <= since:
        return 0.0
    zone = _zone(season)
    day = since.astimezone(zone).date() - timedelta(days=1)
    last = until.astimezone(zone).date()
    total = 0.0
    while day <= last:
        for a, b in windows_on(season, day):
            overlap = (min(b, until) - max(a, since)).total_seconds()
            if overlap > 0:
                total += overlap / 60
        day += timedelta(days=1)
    return total


# --- состояние ------------------------------------------------------------------------------

def enabled(conn, season_id: int) -> bool:
    row = conn.execute("SELECT enabled FROM v4_capture_state WHERE season_id=?", (season_id,)).fetchone()
    return bool(row and row["enabled"])


def faction_of(conn, season_id: int, account_id: int) -> str | None:
    row = conn.execute("SELECT faction FROM v4_capture_factions WHERE season_id=? AND account_id=?",
                       (season_id, account_id)).fetchone()
    return row["faction"] if row and row["faction"] in factions() else None


def assign_faction(conn, season_id: int, account_id: int) -> str:
    """Фракцию выдаёт сервер: в самую маленькую, при равенстве — жребий."""
    existing = faction_of(conn, season_id, account_id)
    if existing:
        return existing
    counts = {code: 0 for code in factions()}
    for row in conn.execute("SELECT faction, COUNT(*) AS n FROM v4_capture_factions WHERE season_id=? GROUP BY faction",
                            (season_id,)):
        if row["faction"] in counts:
            counts[row["faction"]] = int(row["n"])
    smallest = min(counts.values())
    choice = _rng.choice([code for code, n in counts.items() if n == smallest])
    conn.execute("INSERT INTO v4_capture_factions(season_id, account_id, faction) VALUES (?,?,?)",
                 (season_id, account_id, choice))
    return choice


def _point_rows(conn, season_id: int) -> dict[str, dict]:
    return {row["point_code"]: dict(row) for row in conn.execute(
        "SELECT * FROM v4_capture_points WHERE season_id=?", (season_id,)) if row["point_code"] in points()}


def scores(conn, season, now: datetime) -> dict[str, int]:
    minutes = {code: 0.0 for code in factions()}
    for row in conn.execute("SELECT faction, since, until FROM v4_capture_holds WHERE season_id=?", (season["id"],)):
        if row["faction"] in minutes:
            end = rooms.parse(row["until"]) if row["until"] else now
            minutes[row["faction"]] += scored_minutes(season, rooms.parse(row["since"]), min(end, now))
    step = config()["score_minutes"]
    total = {code: int(value // step) for code, value in minutes.items()}
    for row in conn.execute("SELECT faction, points FROM v4_capture_bonus WHERE season_id=?", (season["id"],)):
        if row["faction"] in total:
            total[row["faction"]] += int(row["points"])
    return total


def _open_hold(conn, season_id: int, code: str, faction: str, now: datetime) -> None:
    conn.execute("INSERT INTO v4_capture_holds(season_id, point_code, faction, since) VALUES (?,?,?,?)",
                 (season_id, code, faction, rooms.iso(now)))


def _close_holds(conn, season_id: int, now: datetime, code: str | None = None) -> None:
    if code is None:
        conn.execute("UPDATE v4_capture_holds SET until=? WHERE season_id=? AND until IS NULL",
                     (rooms.iso(now), season_id))
    else:
        conn.execute("UPDATE v4_capture_holds SET until=? WHERE season_id=? AND point_code=? AND until IS NULL",
                     (rooms.iso(now), season_id, code))


def apply_move(conn, season_id: int, code: str, faction: str, now: datetime) -> tuple[str | None, dict | None]:
    """Ход фракции на точке — общий для правильного ответа и выигранной дуэли."""
    row = _point_rows(conn, season_id).get(code)
    if row is None:
        return None, None
    action = action_for(row, faction)
    owner, level = row["owner"], int(row["level"])
    live = enabled(conn, season_id)
    if action == "capture":
        owner, level = faction, 1
        if live:
            _open_hold(conn, season_id, code, faction, now)
    elif action == "reinforce":
        level += 1
    elif action == "attack":
        if level > 1:
            level -= 1
        else:
            action = "flip"
            _close_holds(conn, season_id, now, code)
            owner, level = faction, 1
            if live:
                _open_hold(conn, season_id, code, faction, now)
    if action:
        conn.execute("UPDATE v4_capture_points SET owner=?, level=?, changed_at=? WHERE season_id=? AND point_code=?",
                     (owner, level, rooms.iso(now), season_id, code))
    return action, {**row, "owner": owner, "level": level}


def add_bonus(conn, season_id: int, faction: str, points: int) -> None:
    """Бонусные очки фракции — за выигранные дуэли. Человек не записывается."""
    conn.execute(
        """INSERT INTO v4_capture_bonus(season_id, faction, points) VALUES (?,?,?)
           ON CONFLICT(season_id, faction) DO UPDATE SET points = points + excluded.points""",
        (season_id, faction, int(points)))


# --- вопросы и кулдауны -------------------------------------------------------------------

class Challenges:
    """Вопрос на точке и кулдаун после ответа. Живут в памяти: ответ на телефон не уходит."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.pending: dict[tuple[int, str], dict] = {}
        self.cooldowns: dict[tuple[int, str], datetime] = {}

    def cooldown_left(self, account_id: int, code: str, now: datetime) -> int:
        with self.lock:
            until = self.cooldowns.get((account_id, code))
        return max(0, math.ceil((until - now).total_seconds())) if until else 0

    def make(self, account_id: int, season_id: int, code: str, now: datetime) -> dict:
        words = cipher.content()["words"]
        word = _rng.choice(words)
        wrong = _rng.sample([w["ru"] for w in words if w["ru"] != word["ru"]], QUESTION_OPTIONS - 1)
        options = wrong + [word["ru"]]
        _rng.shuffle(options)
        with self.lock:
            self.pending[(account_id, code)] = {"season_id": season_id, "answer": options.index(word["ru"]),
                                                "created": now}
        return {"zh": word["zh"], "pinyin": word["pinyin"], "options": options}

    def take(self, account_id: int, season_id: int, code: str, now: datetime) -> int:
        with self.lock:
            question = self.pending.pop((account_id, code), None)
        if (not question or question["season_id"] != season_id
                or (now - question["created"]).total_seconds() > config()["question_seconds"]):
            raise CaseError("Вопрос не найден или время вышло. Попробуйте ещё раз.", 409)
        return question["answer"]

    def rest(self, account_id: int, code: str, now: datetime) -> None:
        with self.lock:
            self.cooldowns[(account_id, code)] = now + timedelta(seconds=config()["cooldown_seconds"])
            stale = [key for key, until in self.cooldowns.items() if until <= now]
            for key in stale:
                del self.cooldowns[key]


challenges = Challenges()


# --- представление ----------------------------------------------------------------------------

def action_for(row: dict | None, faction: str | None) -> str | None:
    if not faction or row is None:
        return None
    if row["owner"] is None:
        return "capture"
    if row["owner"] == faction:
        return "reinforce" if row["level"] < config()["max_level"] else None
    return "attack"


def point_view(code: str, row: dict | None, *, staff: bool, faction: str | None, cooldown: int) -> dict:
    names = story.feature_names().get(points()[code]["feature"], {})
    view = {"code": code, "name_ru": names.get("name_ru"), "name_zh": names.get("name_zh"),
            "confirmed": row is not None, "owner": row["owner"] if row else None,
            "level": int(row["level"]) if row else 0, "max_level": config()["max_level"]}
    if row:
        view["coordinates"] = [row["lon"], row["lat"]]
        view["action"] = action_for(row, faction)
        view["cooldown_seconds"] = cooldown
    elif staff:
        lon, lat = story.feature_centres()[points()[code]["feature"]]
        view["coordinates"] = [round(lon, 6), round(lat, 6)]
    return view


def view(conn, account_id: int, season_id: int) -> dict:
    season = conn.execute("SELECT * FROM v4_seasons WHERE id=?", (season_id,)).fetchone()
    staff = cases.can_manage(conn, account_id, season_id)
    member = conn.execute("SELECT status FROM v4_season_memberships WHERE season_id=? AND account_id=?",
                          (season_id, account_id)).fetchone()
    playing = bool(member and member["status"] == "active" and season["status"] == "active")
    if not staff:
        authorize(conn, account_id, season_id)
    faction = assign_faction(conn, season_id, account_id) if playing else None
    now = utcnow()
    rows = _point_rows(conn, season_id)
    counts = {row["faction"]: int(row["n"]) for row in conn.execute(
        "SELECT faction, COUNT(*) AS n FROM v4_capture_factions WHERE season_id=? GROUP BY faction", (season_id,))}
    total = scores(conn, season, now)
    held = {code: 0 for code in factions()}
    for row in rows.values():
        if row["owner"] in held:
            held[row["owner"]] += 1
    visible = [code for code in points() if staff or code in rows]
    return {
        "season_id": season_id,
        "enabled": enabled(conn, season_id),
        "window": window_state(season, now),
        "windows": config()["windows"],
        "radius_m": config()["radius_m"],
        "you":{"faction": faction} if faction else None,
        "can_manage": staff,
        "factions": [{**factions()[code], "score": total[code], "points": held[code], "members": counts.get(code, 0)}
                     for code in factions()],
        "points": [point_view(code, rows.get(code), staff=staff, faction=faction,
                              cooldown=challenges.cooldown_left(account_id, code, now) if faction else 0)
                   for code in visible],
    }


# --- ходы ------------------------------------------------------------------------------------------

def _playable(conn, actor: int, season_id: int, code: str, now: datetime):
    season = authorize(conn, actor, season_id, write=True)
    if code not in points():
        raise CaseError("Такой точки нет.", 404)
    row = _point_rows(conn, season_id).get(code)
    if row is None:
        raise CaseError("Точка ещё не подтверждена вожатым.", 404)
    if not enabled(conn, season_id):
        raise CaseError("Захват сейчас выключен.", 409)
    if not window_state(season, now)["open"]:
        raise CaseError("Захват идёт только в дневные окна.", 409)
    return season, row


def _present(row: dict, lon: float, lat: float, accuracy_m: float) -> None:
    if accuracy_m is None or accuracy_m > campus.MAX_ACCURACY_M:
        raise CaseError("Нужна точная позиция: выйдите под открытое небо и попробуйте ещё раз.")
    if distance_m(lon, lat, row["lon"], row["lat"]) > config()["radius_m"]:
        raise CaseError(f"Подойдите ближе: точка засчитывается в радиусе {config()['radius_m']} м.")


def challenge(conn, actor: int, season_id: int, code: str, *, lon: float, lat: float, accuracy_m: float) -> dict:
    now = utcnow()
    _, row = _playable(conn, actor, season_id, code, now)
    faction = assign_faction(conn, season_id, actor)
    wait = challenges.cooldown_left(actor, code, now)
    if wait:
        raise CaseError(f"Эта точка ждёт вас через {wait} с.", 429)
    _present(row, lon, lat, accuracy_m)
    action = action_for(row, faction)
    if action is None:
        raise CaseError("Точка вашей фракции уже укреплена до предела.", 409)
    # Ход у точки открывает туман там, где стоят.
    campus.record_visit(conn, season_id, lon=lon, lat=lat, accuracy_m=accuracy_m)
    return {"code": code, "action": action, "question": challenges.make(actor, season_id, code, now),
            "seconds": config()["question_seconds"]}


def answer(conn, actor: int, season_id: int, code: str, choice: int) -> dict:
    now = utcnow()
    _, row = _playable(conn, actor, season_id, code, now)
    right = challenges.take(actor, season_id, code, now)
    challenges.rest(actor, code, now)
    faction = assign_faction(conn, season_id, actor)
    if choice != right:
        return {"correct": False, "point": point_view(code, row, staff=False, faction=faction,
                                                      cooldown=config()["cooldown_seconds"])}
    # Ход считается от состояния точки сейчас: пока думали, её могли перехватить.
    action, row = apply_move(conn, season_id, code, faction, now)
    return {"correct": True, "action": action,
            "point": point_view(code, row, staff=False, faction=faction, cooldown=config()["cooldown_seconds"])}


# --- вожатый ---------------------------------------------------------------------------------------

def confirm(conn, actor: int, season_id: int, code: str, *, lon: float, lat: float, accuracy_m: float) -> dict:
    """Вожатый стоит у объекта и подтверждает точку. Координата — его, а не выдуманная."""
    authorize(conn, actor, season_id, manage=True, write=True)
    if code not in points():
        raise CaseError("Такой точки нет.", 404)
    if accuracy_m is None or accuracy_m > config()["confirm_accuracy_m"]:
        raise CaseError(f"Для подтверждения нужна точность не хуже {config()['confirm_accuracy_m']} м.")
    if not campus.inside_campus(lon, lat):
        raise CaseError("Эта позиция не на территории кампуса.")
    centre = story.feature_centres()[points()[code]["feature"]]
    offset = distance_m(lon, lat, *centre)
    if offset > config()["confirm_max_offset_m"]:
        raise CaseError(f"Вы в {round(offset)} м от объекта на карте. Подойдите к нему.")
    now = utcnow()
    conn.execute(
        """INSERT INTO v4_capture_points(season_id, point_code, lon, lat, confirmed_at) VALUES (?,?,?,?,?)
           ON CONFLICT(season_id, point_code) DO UPDATE SET lon=excluded.lon, lat=excluded.lat,
               confirmed_at=excluded.confirmed_at""",
        (season_id, code, round(lon, 6), round(lat, 6), rooms.iso(now)))
    conn.execute(
        """INSERT INTO v4_audit_log(actor_account_id, season_id, action, entity_type, entity_id, after_json)
           VALUES (?, ?, 'capture.confirm', 'capture_point', ?, ?)""",
        (actor, season_id, code, cases.encoded({"accuracy_m": round(accuracy_m), "offset_m": round(offset)})))
    return {"code": code, "confirmed": True, "offset_m": round(offset)}


def set_enabled(conn, actor: int, season_id: int, value: bool) -> dict:
    """Выключатель на сезон. Выключение замораживает удержание, включение продолжает его."""
    authorize(conn, actor, season_id, manage=True, write=True)
    now = utcnow()
    was = enabled(conn, season_id)
    conn.execute(
        """INSERT INTO v4_capture_state(season_id, enabled, updated_by_account_id, updated_at) VALUES (?,?,?,?)
           ON CONFLICT(season_id) DO UPDATE SET enabled=excluded.enabled,
               updated_by_account_id=excluded.updated_by_account_id, updated_at=excluded.updated_at""",
        (season_id, 1 if value else 0, actor, rooms.iso(now)))
    if was and not value:
        _close_holds(conn, season_id, now)
    elif value and not was:
        for code, row in _point_rows(conn, season_id).items():
            if row["owner"]:
                _open_hold(conn, season_id, code, row["owner"], now)
    conn.execute(
        """INSERT INTO v4_audit_log(actor_account_id, season_id, action, entity_type, entity_id, after_json)
           VALUES (?, ?, 'capture.switch', 'season', ?, ?)""",
        (actor, season_id, str(season_id), cases.encoded({"enabled": bool(value)})))
    return {"season_id": season_id, "enabled": bool(value)}
