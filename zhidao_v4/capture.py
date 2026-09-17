"""Захват кампуса (V4_GAMES.md §4.12). Все записи — внутри BEGIN IMMEDIATE.

По мотивам Ingress. Три цветные фракции на всю смену воюют за настоящие точки
кампуса. Чтобы сделать ход, нужно стоять у точки (GPS) и ответить на китайский
вопрос. Ход зависит от того, чья точка:

- ничья — фракция захватывает её на первом уровне;
- своя — укрепляет, до третьего уровня;
- чужая — пробивает защиту на уровень, а с первого уровня перехватывает.

Очки фракция копит за удержание: одно очко за каждые 10 минут на точку, но
только в дневные окна (10–12 и 15–18 по поясу сезона), плюс бонус за
выигранные дуэли (duels.py). Вне окон, ночью и когда вожатый выключил игру,
ходов нет и очки не идут.

Этап 3 — способности, лидер дня, итоги войны (решения пользователя
2026-09-13). Способности покупаются складчиной фракции: любой участник вносит
сколько хочет, способность срабатывает, когда копилка полна. Щит (15★) —
чужие не пробивают точку 30 минут; туман (10★) — соперники час не видят
уровни защиты точек фракции; двойные очки (20★) — точка час приносит вдвое;
разведка (5★) — фракция час видит, сколько ходов сегодня было у точки. В конце
дня лидер дня получает +8★ и +10 REP — но только те его участники, кто в этот
день сделал ход или сыграл дуэль: пассивного дохода нет. Войну заканчивает
вожатый кнопкой «Подвести итоги»: очки замирают, фракция-победитель получает
кубок и рамку «Кубок фракции», несобранные копилки возвращаются. Новая война
начинается с ничьей карты.

Решения пользователя 2026-09-13: фракции, а не отряды; карта живёт всю смену;
очки в дневные окна.

Точку нельзя выдумать (правило CLAUDE.md): точки — объекты campus.geojson, и
играть на точке можно только после того, как вожатый подтвердил её, стоя на
месте с точным GPS. До подтверждения участники точку не видят.

Приватность: точки, отрезки удержания, эффекты, копилки и счётчики ходов
принадлежат фракции. Кто захватил, пробил, укрепил или сколько внёс в копилку,
на телефон не уходит; взносы видны только в журнале экономики, как любая
трата. «Кто в этот день играл» удаляется при подведении дня. Вопросы и
кулдауны живут в памяти процесса — перезапуск их просто сбрасывает.
"""
from __future__ import annotations

import json
import math
import random
import threading
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from pathlib import Path

from . import campus, cases, cipher, rooms, shop, story
from .cases import CaseError, authorize, encoded, ensure_wallet, replay
from .diary import full_wallet

CONFIG_PATH = Path(__file__).parent / "static" / "app" / "assets" / "campus" / "capture.json"
ABILITIES = ("shield", "fog", "double", "scout")
TARGETS = {"shield": "own", "fog": "none", "double": "own", "scout": "any"}
POOL_OPERATION = "capture.pool"
REFUND_OPERATION = "capture.refund"
DAILY_OPERATION = "capture.daily"
QUESTION_OPTIONS = 3
_rng = random.SystemRandom()


def utcnow() -> datetime:
    return shop.utcnow()


@lru_cache(maxsize=1)
def config() -> dict:
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    codes = [f["code"] for f in data["factions"]]
    point_codes = [p["code"] for p in data["points"]]
    if len(codes) < 2 or len(codes) != len(set(codes)):
        raise ValueError("capture.json: нужно не меньше двух фракций без повторов")
    if not point_codes or len(point_codes) != len(set(point_codes)):
        raise ValueError("capture.json: точки пусты или с повторами")
    for point in data["points"]:
        if point["feature"] not in story.feature_centres():
            raise ValueError(f"capture.json: объекта {point['feature']} нет в campus.geojson")
    for key in ("daily_limit", "bonus", "questions", "sheet_seconds", "reaction_options", "round_seconds",
                "wins_needed", "max_rounds", "keep_minutes"):
        if type(data["duels"].get(key)) is not int or data["duels"][key] <= 0:
            raise ValueError(f"capture.json: duels.{key} должно быть положительным целым")
    if set(data["abilities"]) != set(ABILITIES):
        raise ValueError("capture.json: способности — ровно shield, fog, double, scout")
    for code, spec in data["abilities"].items():
        for key in ("price", "minutes"):
            if type(spec.get(key)) is not int or spec[key] <= 0:
                raise ValueError(f"capture.json: abilities.{code}.{key} должно быть положительным целым")
    for key in ("stars", "rep"):
        if type(data["daily_reward"].get(key)) is not int or data["daily_reward"][key] < 0:
            raise ValueError(f"capture.json: daily_reward.{key} должно быть неотрицательным целым")
    award = shop.items_by_code().get(data["award_frame"])
    if not award or award["kind"] != "award" or award["slot"] != "frame":
        raise ValueError("capture.json: award_frame должна быть наградной рамкой из shop.json")
    for start, end in data["windows"]:
        if time.fromisoformat(start) >= time.fromisoformat(end):
            raise ValueError("capture.json: окно должно кончаться позже, чем начинается")
    return data


def factions() -> dict[str, dict]:
    return {f["code"]: f for f in config()["factions"]}


def points() -> dict[str, dict]:
    return {p["code"]: p for p in config()["points"]}


def abilities() -> dict[str, dict]:
    return config()["abilities"]


def distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# --- окна и дни ---------------------------------------------------------------------------

def _zone(season):
    return shop._zone(season)


def local_day(season, now: datetime) -> date:
    return now.astimezone(_zone(season)).date()


def clock_text(season, moment: datetime) -> str:
    return moment.astimezone(_zone(season)).strftime("%H:%M")


def windows_on(season, day: date) -> list[tuple[datetime, datetime]]:
    """Окна одного местного дня как отрезки с поясом сезона."""
    zone = _zone(season)
    return [(datetime.combine(day, time.fromisoformat(start), tzinfo=zone),
             datetime.combine(day, time.fromisoformat(end), tzinfo=zone))
            for start, end in config()["windows"]]


def window_state(season, now: datetime) -> dict:
    today = local_day(season, now)
    for a, b in windows_on(season, today):
        if a <= now < b:
            return {"open": True, "closes_at": b.isoformat()}
    upcoming = [a for day in (today, today + timedelta(days=1)) for a, _ in windows_on(season, day) if a > now]
    return {"open": False, "opens_at": min(upcoming).isoformat() if upcoming else None}


def scored_minutes(season, since: datetime, until: datetime, only_day: date | None = None) -> float:
    """Сколько минут отрезка пришлось на дневные окна (всех дней или одного)."""
    if until <= since:
        return 0.0
    if only_day is not None:
        days = [only_day]
    else:
        first, last = local_day(season, since) - timedelta(days=1), local_day(season, until)
        days = [first + timedelta(days=n) for n in range((last - first).days + 1)]
    total = 0.0
    for day in days:
        for a, b in windows_on(season, day):
            overlap = (min(b, until) - max(a, since)).total_seconds()
            if overlap > 0:
                total += overlap / 60
    return total


# --- война и выключатель -----------------------------------------------------------------------

def state_row(conn, season_id: int):
    return conn.execute("SELECT * FROM v4_capture_state WHERE season_id=?", (season_id,)).fetchone()


def war_number(conn, season_id: int) -> int:
    row = state_row(conn, season_id)
    return int(row["war"]) if row else 1


def war_finished(conn, season_id: int) -> bool:
    row = state_row(conn, season_id)
    return bool(row and row["war_finished_at"])


def enabled(conn, season_id: int) -> bool:
    row = state_row(conn, season_id)
    return bool(row and row["enabled"] and not row["war_finished_at"])


# --- фракции и точки ----------------------------------------------------------------------------

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


def active_effects(conn, season_id: int, now: datetime) -> list[dict]:
    return [dict(row) for row in conn.execute(
        "SELECT * FROM v4_capture_effects WHERE season_id=? AND until > ?", (season_id, rooms.iso(now)))]


def _effect(effects: list[dict], ability: str, *, faction: str | None = None, target: str | None = None) -> dict | None:
    for effect in effects:
        if (effect["ability"] == ability and (faction is None or effect["faction"] == faction)
                and (target is None or effect["target"] == target)):
            return effect
    return None


# --- очки ---------------------------------------------------------------------------------------

def scores(conn, season, now: datetime, only_day: date | None = None) -> dict[str, int]:
    """Очки войны или одного дня: удержание в окнах, двойные очки и бонус дуэлей."""
    minutes = {code: 0.0 for code in factions()}
    doubles = [dict(row) for row in conn.execute(
        "SELECT * FROM v4_capture_effects WHERE season_id=? AND ability='double'", (season["id"],))]
    for row in conn.execute("SELECT point_code, faction, since, until FROM v4_capture_holds WHERE season_id=?",
                            (season["id"],)):
        if row["faction"] not in minutes:
            continue
        since = rooms.parse(row["since"])
        end = min(rooms.parse(row["until"]) if row["until"] else now, now)
        minutes[row["faction"]] += scored_minutes(season, since, end, only_day)
        for effect in doubles:
            if effect["target"] == row["point_code"] and effect["faction"] == row["faction"]:
                minutes[row["faction"]] += scored_minutes(
                    season, max(since, rooms.parse(effect["since"])), min(end, rooms.parse(effect["until"])), only_day)
    step = config()["score_minutes"]
    total = {code: int(value // step) for code, value in minutes.items()}
    if only_day is None:
        rows = conn.execute("SELECT faction, points FROM v4_capture_bonus WHERE season_id=?", (season["id"],))
    else:
        rows = conn.execute("SELECT faction, points FROM v4_capture_daily_bonus WHERE season_id=? AND bonus_day=?",
                            (season["id"], only_day.isoformat()))
    for row in rows:
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


def apply_move(conn, season, code: str, faction: str, now: datetime) -> tuple[str | None, dict | None]:
    """Ход фракции на точке — общий для правильного ответа и выигранной дуэли."""
    season_id = season["id"]
    row = _point_rows(conn, season_id).get(code)
    if row is None:
        return None, None
    action = action_for(row, faction)
    if action == "attack" and _effect(active_effects(conn, season_id, now), "shield", faction=row["owner"], target=code):
        return "shielded", row
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


def add_bonus(conn, season, faction: str, amount: int, now: datetime) -> None:
    """Бонусные очки фракции — за выигранные дуэли. Человек не записывается."""
    conn.execute(
        """INSERT INTO v4_capture_bonus(season_id, faction, points) VALUES (?,?,?)
           ON CONFLICT(season_id, faction) DO UPDATE SET points = points + excluded.points""",
        (season["id"], faction, int(amount)))
    conn.execute(
        """INSERT INTO v4_capture_daily_bonus(season_id, faction, bonus_day, points) VALUES (?,?,?,?)
           ON CONFLICT(season_id, faction, bonus_day) DO UPDATE SET points = points + excluded.points""",
        (season["id"], faction, local_day(season, now).isoformat(), int(amount)))


def count_move(conn, season, code: str, now: datetime) -> None:
    """Сколько ходов сегодня было у точки — то, что показывает разведка. Без людей."""
    conn.execute(
        """INSERT INTO v4_capture_point_moves(season_id, point_code, move_day, moves) VALUES (?,?,?,1)
           ON CONFLICT(season_id, point_code, move_day) DO UPDATE SET moves = moves + 1""",
        (season["id"], code, local_day(season, now).isoformat()))


def record_activity(conn, season, account_id: int, now: datetime) -> None:
    """Человек сегодня играл — нужно, чтобы награда лидера дня не была пассивной."""
    conn.execute("INSERT OR IGNORE INTO v4_capture_activity(season_id, account_id, activity_day) VALUES (?,?,?)",
                 (season["id"], account_id, local_day(season, now).isoformat()))


# --- звёзды: награды и возвраты --------------------------------------------------------------------

def _credit(conn, season_id: int, account_id: int, *, stars: int, rep: int, operation: str, details: dict) -> None:
    ensure_wallet(conn, account_id, season_id)
    before = full_wallet(conn, account_id, season_id)
    conn.execute("UPDATE v4_case_wallets SET stars = stars + ?, rep = rep + ? WHERE season_id=? AND account_id=?",
                 (stars, rep, season_id, account_id))
    after = full_wallet(conn, account_id, season_id)
    conn.execute(
        """INSERT INTO v4_economy_operations(season_id, account_id, actor_account_id, operation,
               stars_delta, scans_delta, rep_delta, stars_after, scans_after, rep_after, details_json)
           VALUES (?,?,?,?,?,0,?,?,?,?,?)""",
        (season_id, account_id, account_id, operation, after["stars"] - before["stars"], after["rep"] - before["rep"],
         after["stars"], after["scans"], after["rep"], encoded(details)))


def settle_days(conn, season, now: datetime, *, force_today: bool = False) -> None:
    """Подводит закончившиеся дни: лидер дня получает награду, «кто играл» забывается."""
    if war_finished(conn, season["id"]):
        return
    today = local_day(season, now)
    day_over = now >= max(b for _, b in windows_on(season, today))
    war = war_number(conn, season["id"])
    pending = [row["activity_day"] for row in conn.execute(
        """SELECT DISTINCT activity_day FROM v4_capture_activity WHERE season_id=?
           AND activity_day NOT IN (SELECT day FROM v4_capture_days WHERE season_id=? AND war=?)
           ORDER BY activity_day""", (season["id"], season["id"], war))]
    for text in pending:
        day = date.fromisoformat(text)
        if day > today or (day == today and not (day_over or force_today)):
            continue
        _settle_day(conn, season, day, war, now)


def _settle_day(conn, season, day: date, war: int, now: datetime) -> None:
    daily = scores(conn, season, now, only_day=day)
    top = max(daily.values())
    winners = sorted(code for code, value in daily.items() if top > 0 and value == top)
    reward = config()["daily_reward"]
    rewarded = 0
    for row in conn.execute(
        """SELECT a.account_id, f.faction FROM v4_capture_activity a
           JOIN v4_capture_factions f ON f.season_id = a.season_id AND f.account_id = a.account_id
           JOIN v4_season_memberships m ON m.season_id = a.season_id AND m.account_id = a.account_id AND m.status='active'
           WHERE a.season_id=? AND a.activity_day=?""", (season["id"], day.isoformat())).fetchall():
        if row["faction"] in winners and (reward["stars"] or reward["rep"]):
            _credit(conn, season["id"], int(row["account_id"]), stars=reward["stars"], rep=reward["rep"],
                    operation=DAILY_OPERATION, details={"day": day.isoformat(), "faction": row["faction"], "war": war})
            rewarded += 1
    conn.execute("INSERT INTO v4_capture_days(season_id, war, day, winners_json, rewarded, settled_at) VALUES (?,?,?,?,?,?)",
                 (season["id"], war, day.isoformat(), encoded(winners), rewarded, rooms.iso(now)))
    conn.execute("DELETE FROM v4_capture_activity WHERE season_id=? AND activity_day=?", (season["id"], day.isoformat()))


def _refund_pools(conn, season, now: datetime) -> int:
    """Несобранные копилки возвращаются тем, кто вносил, — по журналу экономики."""
    refunded = 0
    for pool in conn.execute("SELECT * FROM v4_capture_pools WHERE season_id=?", (season["id"],)).fetchall():
        for row in conn.execute(
            """SELECT account_id, -SUM(stars_delta) AS paid FROM v4_economy_operations
               WHERE season_id=? AND operation=? AND json_extract(details_json, '$.pool') = ?
               GROUP BY account_id""", (season["id"], POOL_OPERATION, int(pool["id"]))).fetchall():
            if int(row["paid"]) > 0:
                _credit(conn, season["id"], int(row["account_id"]), stars=int(row["paid"]), rep=0,
                        operation=REFUND_OPERATION, details={"pool": int(pool["id"]), "ability": pool["ability"]})
                refunded += 1
    conn.execute("DELETE FROM v4_capture_pools WHERE season_id=?", (season["id"],))
    return refunded


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


def point_view(code: str, row: dict | None, *, staff: bool, faction: str | None, cooldown: int,
               effects: list[dict] | None = None, moves_today: int = 0) -> dict:
    names = story.feature_names().get(points()[code]["feature"], {})
    view = {"code": code, "name_ru": names.get("name_ru"), "name_zh": names.get("name_zh"),
            "confirmed": row is not None, "owner": row["owner"] if row else None,
            "level": int(row["level"]) if row else 0, "max_level": config()["max_level"]}
    if row:
        effects = effects or []
        view["coordinates"] = [row["lon"], row["lat"]]
        view["action"] = action_for(row, faction)
        view["cooldown_seconds"] = cooldown
        owner = row["owner"]
        if owner:
            shield = _effect(effects, "shield", faction=owner, target=code)
            double = _effect(effects, "double", faction=owner, target=code)
            if shield:
                view["shield_until"] = shield["until"]
            if double:
                view["double_until"] = double["until"]
            # Туман: соперники не видят уровень защиты. Своя фракция и вожатый — видят.
            if _effect(effects, "fog", faction=owner) and not staff and faction != owner:
                view["level"] = None
                view["hidden"] = True
        if faction and _effect(effects, "scout", faction=faction, target=code):
            view["scouted"] = {"moves_today": moves_today}
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
    if season["status"] == "active":
        settle_days(conn, season, now)
    rows = _point_rows(conn, season_id)
    effects = active_effects(conn, season_id, now)
    counts = {row["faction"]: int(row["n"]) for row in conn.execute(
        "SELECT faction, COUNT(*) AS n FROM v4_capture_factions WHERE season_id=? GROUP BY faction", (season_id,))}
    total = scores(conn, season, now)
    today = scores(conn, season, now, only_day=local_day(season, now))
    moves = {row["point_code"]: int(row["moves"]) for row in conn.execute(
        "SELECT point_code, moves FROM v4_capture_point_moves WHERE season_id=? AND move_day=?",
        (season_id, local_day(season, now).isoformat()))}
    held = {code: 0 for code in factions()}
    for row in rows.values():
        if row["owner"] in held:
            held[row["owner"]] += 1
    visible = [code for code in points() if staff or code in rows]
    pools = []
    if faction:
        pools = [{"ability": row["ability"], "target": row["target"] or None, "collected": int(row["collected"]),
                  "price": abilities()[row["ability"]]["price"]}
                 for row in conn.execute("SELECT * FROM v4_capture_pools WHERE season_id=? AND faction=? ORDER BY id",
                                         (season_id, faction))]
    return {
        "season_id": season_id,
        "enabled": enabled(conn, season_id),
        "window": window_state(season, now),
        "windows": config()["windows"],
        "radius_m": config()["radius_m"],
        "you": {"faction": faction} if faction else None,
        "can_manage": staff,
        "factions": [{**factions()[code], "score": total[code], "today": today[code], "points": held[code],
                      "members": counts.get(code, 0)} for code in factions()],
        "points": [point_view(code, rows.get(code), staff=staff, faction=faction,
                              cooldown=challenges.cooldown_left(account_id, code, now) if faction else 0,
                              effects=effects, moves_today=moves.get(code, 0))
                   for code in visible],
        "abilities": {code: {**spec, "target": TARGETS[code]} for code, spec in abilities().items()},
        "daily_reward": config()["daily_reward"],
        "effects": [{"ability": e["ability"], "target": e["target"] or None, "until": e["until"]}
                    for e in effects if faction and e["faction"] == faction],
        "pools": pools,
        "war": {"number": war_number(conn, season_id), "finished": war_finished(conn, season_id)},
        "wars": [{"number": int(row["number"]), "winners": json.loads(row["winners_json"]),
                  "scores": json.loads(row["scores_json"]), "finished_at": row["finished_at"]}
                 for row in conn.execute("SELECT * FROM v4_capture_wars WHERE season_id=? ORDER BY number", (season_id,))],
    }


# --- ходы ------------------------------------------------------------------------------------------

def _playable(conn, actor: int, season_id: int, code: str, now: datetime):
    season = authorize(conn, actor, season_id, write=True, staff_may_play=True)
    if code not in points():
        raise CaseError("Такой точки нет.", 404)
    row = _point_rows(conn, season_id).get(code)
    if row is None:
        raise CaseError("Точка ещё не подтверждена вожатым.", 404)
    if war_finished(conn, season_id):
        raise CaseError("Война окончена. Ждём, когда вожатый начнёт новую.", 409)
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
    season, row = _playable(conn, actor, season_id, code, now)
    faction = assign_faction(conn, season_id, actor)
    wait = challenges.cooldown_left(actor, code, now)
    if wait:
        raise CaseError(f"Эта точка ждёт вас через {wait} с.", 429)
    _present(row, lon, lat, accuracy_m)
    action = action_for(row, faction)
    if action is None:
        raise CaseError("Точка вашей фракции уже укреплена до предела.", 409)
    shield = _effect(active_effects(conn, season_id, now), "shield", faction=row["owner"], target=code)
    if action == "attack" and shield:
        raise CaseError(f"Точка под щитом до {clock_text(season, rooms.parse(shield['until']))}.", 409)
    # Ход у точки открывает туман там, где стоят.
    campus.record_visit(conn, season_id, lon=lon, lat=lat, accuracy_m=accuracy_m)
    return {"code": code, "action": action, "question": challenges.make(actor, season_id, code, now),
            "seconds": config()["question_seconds"]}


def answer(conn, actor: int, season_id: int, code: str, choice: int) -> dict:
    now = utcnow()
    season, row = _playable(conn, actor, season_id, code, now)
    right = challenges.take(actor, season_id, code, now)
    challenges.rest(actor, code, now)
    faction = assign_faction(conn, season_id, actor)
    record_activity(conn, season, actor, now)
    count_move(conn, season, code, now)
    effects = active_effects(conn, season_id, now)
    if choice != right:
        return {"correct": False, "point": point_view(code, row, staff=False, faction=faction, effects=effects,
                                                      cooldown=config()["cooldown_seconds"])}
    # Ход считается от состояния точки сейчас: пока думали, её могли перехватить.
    action, row = apply_move(conn, season, code, faction, now)
    return {"correct": True, "action": action,
            "point": point_view(code, row, staff=False, faction=faction, effects=active_effects(conn, season_id, now),
                                cooldown=config()["cooldown_seconds"])}


# --- способности ----------------------------------------------------------------------------------

def contribute(conn, actor: int, season_id: int, *, ability: str, target: str | None, amount: int, key: str,
               request_id=None):
    """Взнос в копилку фракции. Когда копилка полна, способность включается сразу."""
    authorize(conn, actor, season_id, staff_may_play=True)
    payload = {"season_id": season_id, "ability": ability, "target": target, "amount": amount}
    key, digest, old = replay(conn, actor, POOL_OPERATION, key, payload)
    if old is not None:
        return old, True
    season = authorize(conn, actor, season_id, write=True, staff_may_play=True)
    now = utcnow()
    if ability not in ABILITIES:
        raise CaseError("Такой способности нет.", 404)
    if war_finished(conn, season_id):
        raise CaseError("Война окончена: копилки закрыты.", 409)
    if not enabled(conn, season_id) or not window_state(season, now)["open"]:
        raise CaseError("Способности покупаются, пока идёт Захват — в дневные окна.", 409)
    if type(amount) is not int or amount <= 0:
        raise CaseError("Взнос — положительное целое число звёзд.")
    faction = assign_faction(conn, season_id, actor)
    spec = abilities()[ability]
    kind = TARGETS[ability]
    if kind == "none":
        target_code = ""
    else:
        if not target or target not in points():
            raise CaseError("Выберите точку.", 404)
        row = _point_rows(conn, season_id).get(target)
        if row is None:
            raise CaseError("Точка ещё не подтверждена вожатым.", 404)
        if kind == "own" and row["owner"] != faction:
            raise CaseError("Эту способность ставят только на точки своей фракции.", 409)
        target_code = target
    live = _effect(active_effects(conn, season_id, now), ability, faction=faction, target=target_code)
    if live:
        raise CaseError(f"Уже действует до {clock_text(season, rooms.parse(live['until']))}.", 409)
    pool = conn.execute("SELECT * FROM v4_capture_pools WHERE season_id=? AND faction=? AND ability=? AND target=?",
                        (season_id, faction, ability, target_code)).fetchone()
    if pool is None:
        cursor = conn.execute(
            "INSERT INTO v4_capture_pools(season_id, faction, ability, target, collected, created_at) VALUES (?,?,?,?,0,?)",
            (season_id, faction, ability, target_code, rooms.iso(now)))
        pool = conn.execute("SELECT * FROM v4_capture_pools WHERE id=?", (cursor.lastrowid,)).fetchone()
    paid = min(amount, spec["price"] - int(pool["collected"]))
    ensure_wallet(conn, actor, season_id)
    before = full_wallet(conn, actor, season_id)
    if before["stars"] < paid:
        raise CaseError(f"Не хватает звёзд: взнос {paid}★, у вас {before['stars']}★.", 409)
    conn.execute("UPDATE v4_case_wallets SET stars = stars - ? WHERE season_id=? AND account_id=?",
                 (paid, season_id, actor))
    after = full_wallet(conn, actor, season_id)
    details = {"pool": int(pool["id"]), "ability": ability, "target": target_code or None, "paid": paid,
               "war": war_number(conn, season_id)}
    conn.execute(
        """INSERT INTO v4_economy_operations(season_id, account_id, actor_account_id, operation,
               stars_delta, scans_delta, rep_delta, stars_after, scans_after, rep_after, details_json)
           VALUES (?,?,?,?,?,0,0,?,?,?,?)""",
        (season_id, actor, actor, POOL_OPERATION, -paid, after["stars"], after["scans"], after["rep"], encoded(details)))
    collected = int(pool["collected"]) + paid
    activated = collected >= spec["price"]
    until = None
    if activated:
        until = rooms.iso(now + timedelta(minutes=spec["minutes"]))
        conn.execute("DELETE FROM v4_capture_pools WHERE id=?", (pool["id"],))
        conn.execute("INSERT INTO v4_capture_effects(season_id, faction, ability, target, since, until) VALUES (?,?,?,?,?,?)",
                     (season_id, faction, ability, target_code, rooms.iso(now), until))
    else:
        conn.execute("UPDATE v4_capture_pools SET collected=? WHERE id=?", (collected, pool["id"]))
    response = {"ability": ability, "target": target_code or None, "paid": paid, "collected": min(collected, spec["price"]),
                "price": spec["price"], "activated": activated, "until": until, "stars": after["stars"]}
    serialized = encoded(response)
    conn.execute(
        """INSERT INTO v4_idempotency_keys(account_id, operation, idempotency_key, request_hash,
               response_status, response_json) VALUES (?,?,?,?,200,?)""",
        (actor, POOL_OPERATION, key, digest, serialized))
    conn.execute(
        """INSERT INTO v4_audit_log(actor_account_id, season_id, action, entity_type, entity_id, request_id,
               after_json, metadata_json) VALUES (?,?,?,'capture_pool',?,?,?,?)""",
        (actor, season_id, POOL_OPERATION, str(pool["id"]), request_id, serialized, encoded({"idempotency_key": key})))
    return response, False


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
        (actor, season_id, code, encoded({"accuracy_m": round(accuracy_m), "offset_m": round(offset)})))
    return {"code": code, "confirmed": True, "offset_m": round(offset)}


def set_enabled(conn, actor: int, season_id: int, value: bool) -> dict:
    """Выключатель на сезон. Выключение замораживает удержание, включение продолжает его."""
    authorize(conn, actor, season_id, manage=True, write=True)
    if value and war_finished(conn, season_id):
        raise CaseError("Война окончена. Сначала начните новую.", 409)
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
        (actor, season_id, str(season_id), encoded({"enabled": bool(value)})))
    return {"season_id": season_id, "enabled": bool(value)}


def finish_war(conn, actor: int, season_id: int) -> dict:
    """«Подвести итоги»: очки замирают, победитель получает кубок и рамку, копилки возвращаются."""
    season = authorize(conn, actor, season_id, manage=True, write=True)
    if war_finished(conn, season_id):
        raise CaseError("Итоги этой войны уже подведены.", 409)
    now = utcnow()
    settle_days(conn, season, now, force_today=True)
    final = scores(conn, season, now)
    top = max(final.values())
    winners = sorted(code for code, value in final.items() if top > 0 and value == top)
    war = war_number(conn, season_id)
    _close_holds(conn, season_id, now)
    conn.execute(
        """INSERT INTO v4_capture_state(season_id, enabled, updated_by_account_id, updated_at, war, war_finished_at)
           VALUES (?,0,?,?,?,?)
           ON CONFLICT(season_id) DO UPDATE SET enabled=0, updated_by_account_id=excluded.updated_by_account_id,
               updated_at=excluded.updated_at, war_finished_at=excluded.war_finished_at""",
        (season_id, actor, rooms.iso(now), war, rooms.iso(now)))
    conn.execute("INSERT INTO v4_capture_wars(season_id, number, finished_at, winners_json, scores_json) VALUES (?,?,?,?,?)",
                 (season_id, war, rooms.iso(now), encoded(winners), encoded(final)))
    frame = config()["award_frame"]
    awarded = 0
    for code in winners:
        for row in conn.execute(
            """SELECT f.account_id FROM v4_capture_factions f
               JOIN v4_season_memberships m ON m.season_id = f.season_id AND m.account_id = f.account_id AND m.status='active'
               WHERE f.season_id=? AND f.faction=?""", (season_id, code)).fetchall():
            awarded += conn.execute(
                """INSERT OR IGNORE INTO v4_case_inventory(season_id, account_id, item_code, quantity, effect_state)
                   VALUES (?,?,?,1,'active')""", (season_id, int(row["account_id"]), frame)).rowcount
    refunded = _refund_pools(conn, season, now)
    result = {"war": war, "winners": winners, "scores": final, "frames_awarded": awarded, "pool_refunds": refunded}
    conn.execute(
        """INSERT INTO v4_audit_log(actor_account_id, season_id, action, entity_type, entity_id, after_json)
           VALUES (?, ?, 'capture.finish', 'season', ?, ?)""", (actor, season_id, str(season_id), encoded(result)))
    return result


def new_war(conn, actor: int, season_id: int) -> dict:
    """Новая война с ничьей картой. Прежние итоги остаются в истории войн."""
    season = authorize(conn, actor, season_id, manage=True, write=True)
    if not war_finished(conn, season_id):
        raise CaseError("Сначала подведите итоги текущей войны.", 409)
    now = utcnow()
    _refund_pools(conn, season, now)
    for table in ("v4_capture_holds", "v4_capture_bonus", "v4_capture_daily_bonus", "v4_capture_effects",
                  "v4_capture_point_moves", "v4_capture_activity"):
        conn.execute(f"DELETE FROM {table} WHERE season_id=?", (season_id,))
    conn.execute("UPDATE v4_capture_points SET owner=NULL, level=0, changed_at=? WHERE season_id=?",
                 (rooms.iso(now), season_id))
    war = war_number(conn, season_id) + 1
    conn.execute("UPDATE v4_capture_state SET war=?, war_finished_at=NULL, enabled=0, updated_by_account_id=?, updated_at=? "
                 "WHERE season_id=?", (war, actor, rooms.iso(now), season_id))
    conn.execute(
        """INSERT INTO v4_audit_log(actor_account_id, season_id, action, entity_type, entity_id, after_json)
           VALUES (?, ?, 'capture.new_war', 'season', ?, ?)""", (actor, season_id, str(season_id), encoded({"war": war})))
    return {"war": war, "enabled": False}
