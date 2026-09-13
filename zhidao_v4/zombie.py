"""Зомби-протокол (V4_GAMES.md §4.12). Записи — внутри BEGIN IMMEDIATE.

По мотивам Humans vs Zombies и скрещён с Вирусом Протокола (§4.7). Вечерний
раунд в границах зоны, которую называет вожатый: люди уходят шагом, зомби
касаются плеча. Коснулся — вводит у себя шестизначный код с телефона жертвы,
и жертва становится зомби. Зомби может один раз за раунд вернуться в люди:
дойти до станции (подтверждённой точки кампуса, как в Захвате) и ответить на
китайский вопрос.

Решения пользователя 2026-09-13: заражение — кодом жертвы; первые зомби — те,
кто на старте болеет Вирусом Протокола (если таких нет — жребий); вакцина —
станции по GPS; награды — выжившим и лучшему зомби.

Числа — черновик Claude в zombie.json: раунд 20 минут; первых зомби не больше
трети игроков, жребий — один на десять; призы по 10★ в раундах от 8 игроков и
не чаще раза в сезон-день на человека; после заражения зомби 30 секунд
приходит в себя; после вакцины 2 минуты иммунитета и новый код — старый уже
знает тот, кто заразил.

Честность: код видит только его хозяин; перебор бессмысленен — кодов миллион,
попыток шесть в минуту. Правильный вариант вопроса не уходит на телефон.
Приватность: кто кого заразил, не записывается — только число заражений.
Через полчаса после конца раунда удаляется состав, остаются итоги.
"""
from __future__ import annotations

import json
import math
import random
import secrets
import threading
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

from . import capture, cases, cipher, rooms, shop, story, virus
from .cases import CaseError, authorize, encoded, ensure_wallet
from .diary import full_wallet

CONFIG_PATH = Path(__file__).parent / "static" / "app" / "assets" / "games" / "zombie.json"
PRIZE_OPERATION = "zombie.prize"
QUESTION_OPTIONS = 3
_rng = random.SystemRandom()


class NeedsWrite(RuntimeError):
    """Опрос обнаружил, что раунд пора закончить или почистить."""


def utcnow() -> datetime:
    return shop.utcnow()


@lru_cache(maxsize=1)
def config() -> dict:
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    for key in ("min_players", "max_players", "round_minutes", "start_share", "lottery_per", "tag_cooldown_seconds",
                "immune_seconds", "question_seconds", "wrong_cooldown_seconds", "keep_minutes", "prize_min_players"):
        if type(data.get(key)) is not int or data[key] <= 0:
            raise ValueError(f"zombie.json: {key} должно быть положительным целым")
    if data["min_players"] < 3 or data["start_share"] < 2:
        raise ValueError("zombie.json: нужно хотя бы трое, и людей на старте должно быть больше, чем зомби")
    for key in ("survivor_stars", "zombie_stars"):
        if type(data["prize"].get(key)) is not int or data["prize"][key] < 0:
            raise ValueError(f"zombie.json: prize.{key} — неотрицательное целое")
    return data


# --- строки ------------------------------------------------------------------------------

def _active(conn, season_id: int):
    return conn.execute(
        "SELECT * FROM v4_zombie_games WHERE season_id=? AND status IN ('lobby','running') ORDER BY id DESC LIMIT 1",
        (season_id,)).fetchone()


def _latest(conn, season_id: int):
    return conn.execute(
        "SELECT * FROM v4_zombie_games WHERE season_id=? AND (status<>'over' OR purged=0) ORDER BY id DESC LIMIT 1",
        (season_id,)).fetchone()


def _game(conn, game_id: int):
    return conn.execute("SELECT * FROM v4_zombie_games WHERE id=?", (game_id,)).fetchone()


def _players(conn, game_id: int) -> list:
    return conn.execute(
        """SELECT p.*, a.display_name FROM v4_zombie_players p JOIN v4_accounts a ON a.id = p.account_id
           WHERE p.game_id=? ORDER BY p.joined_at, p.account_id""", (game_id,)).fetchall()


def _player(conn, game_id: int, account_id: int):
    return conn.execute("SELECT * FROM v4_zombie_players WHERE game_id=? AND account_id=?",
                        (game_id, account_id)).fetchone()


def _humans(conn, game_id: int) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM v4_zombie_players WHERE game_id=? AND side='human'",
                            (game_id,)).fetchone()[0])


def _new_code(conn, game_id: int) -> str:
    while True:
        code = f"{secrets.randbelow(1_000_000):06d}"
        if not conn.execute("SELECT 1 FROM v4_zombie_players WHERE game_id=? AND code=?", (game_id, code)).fetchone():
            return code


def _later(value: str | None, now: datetime) -> bool:
    return bool(value) and rooms.parse(value) > now


def _rest_until(player) -> datetime | None:
    """Зомби приходит в себя после заражения и после каждого своего заражения."""
    moments = [rooms.parse(v) for v in (player["turned_at"], player["last_tag_at"]) if v]
    if not moments:
        return None
    return max(moments) + timedelta(seconds=config()["tag_cooldown_seconds"])


def _cutoff(now: datetime) -> str:
    return rooms.iso(now - timedelta(minutes=config()["keep_minutes"]))


def _stale(conn, now: datetime) -> bool:
    return conn.execute("SELECT 1 FROM v4_zombie_games WHERE status='over' AND purged=0 AND finished_at < ? LIMIT 1",
                        (_cutoff(now),)).fetchone() is not None


def purge(conn, now: datetime) -> None:
    """Через полчаса после конца раунда забывается состав: стороны, коды, заражения."""
    for row in conn.execute("SELECT id FROM v4_zombie_games WHERE status='over' AND purged=0 AND finished_at < ?",
                            (_cutoff(now),)).fetchall():
        conn.execute("DELETE FROM v4_zombie_players WHERE game_id=?", (row["id"],))
        conn.execute("UPDATE v4_zombie_games SET purged=1, state_json='{}' WHERE id=?", (row["id"],))


# --- конец раунда ---------------------------------------------------------------------------

def _due(conn, game, now: datetime) -> bool:
    if game["status"] != "running":
        return False
    return now >= rooms.parse(game["ends_at"]) or _humans(conn, game["id"]) == 0


def _credit(conn, season_id: int, account_id: int, stars: int, details: dict) -> None:
    ensure_wallet(conn, account_id, season_id)
    before = full_wallet(conn, account_id, season_id)
    conn.execute("UPDATE v4_case_wallets SET stars = stars + ? WHERE season_id=? AND account_id=?",
                 (stars, season_id, account_id))
    after = full_wallet(conn, account_id, season_id)
    conn.execute(
        """INSERT INTO v4_economy_operations(season_id, account_id, actor_account_id, operation,
               stars_delta, scans_delta, rep_delta, stars_after, scans_after, rep_after, details_json)
           VALUES (?,?,?,?,?,0,0,?,?,?,?)""",
        (season_id, account_id, account_id, PRIZE_OPERATION, after["stars"] - before["stars"],
         after["stars"], after["scans"], after["rep"], encoded(details)))


def _finish(conn, game, now: datetime, reason: str) -> None:
    season = conn.execute("SELECT * FROM v4_seasons WHERE id=?", (game["season_id"],)).fetchone()
    state = json.loads(game["state_json"])
    rules = config()
    players = _players(conn, game["id"])
    prizes_on = int(state.get("starters") or 0) >= rules["prize_min_players"]
    day = shop.shop_day(season, now)

    def pay(account_id: int, stars: int, why: str) -> tuple[int, bool]:
        if not prizes_on or stars <= 0:
            return 0, False
        if not conn.execute("INSERT OR IGNORE INTO v4_zombie_prize_days(season_id, account_id, prize_day) VALUES (?,?,?)",
                            (season["id"], account_id, day)).rowcount:
            return 0, True
        _credit(conn, season["id"], account_id, stars, {"game": int(game["id"]), "for": why})
        return stars, False

    survivors, best = [], []
    for p in players:
        if p["side"] == "human":
            stars, limited = pay(int(p["account_id"]), rules["prize"]["survivor_stars"], "survivor")
            survivors.append({"account_id": int(p["account_id"]), "name": p["display_name"], "prize": stars,
                              "limited": limited})
    top = max((int(p["tags"]) for p in players), default=0)
    for p in players:
        if top > 0 and int(p["tags"]) == top:
            stars, limited = pay(int(p["account_id"]), rules["prize"]["zombie_stars"], "zombie")
            best.append({"account_id": int(p["account_id"]), "name": p["display_name"], "tags": top, "prize": stars,
                         "limited": limited})
    humans = sum(1 for p in players if p["side"] == "human")
    results = {"reason": reason, "players": len(players), "humans": humans, "zombies": len(players) - humans,
               "prizes": prizes_on, "survivors": survivors, "best_zombies": best}
    state["reason"] = reason
    conn.execute("UPDATE v4_zombie_games SET status='over', state_json=?, results_json=?, updated_at=?, finished_at=? WHERE id=?",
                 (encoded(state), encoded(results), rooms.iso(now), rooms.iso(now), game["id"]))


def advance(conn, game_id: int, now: datetime) -> bool:
    game = _game(conn, game_id)
    if game is None or not _due(conn, game, now):
        return False
    _finish(conn, game, now, "all_turned" if _humans(conn, game_id) == 0 else "time")
    return True


# --- что видит телефон ------------------------------------------------------------------------

def _stations(conn, season_id: int) -> list[dict]:
    names = story.feature_names()
    return [{"code": code, "name_ru": names.get(capture.points()[code]["feature"], {}).get("name_ru"),
             "name_zh": names.get(capture.points()[code]["feature"], {}).get("name_zh")}
            for code in capture.points() if code in capture._point_rows(conn, season_id)]


def _view(conn, game, viewer: int, staff: bool, now: datetime) -> dict:
    state = json.loads(game["state_json"])
    players = _players(conn, game["id"])
    humans = sum(1 for p in players if p["side"] == "human")
    view = {"id": int(game["id"]), "status": game["status"], "players": len(players), "humans": humans,
            "zombies": len(players) - humans, "ends_at": game["ends_at"], "cancelled": bool(state.get("cancelled")),
            "source": state.get("source")}
    me = next((p for p in players if int(p["account_id"]) == viewer), None)
    if me is not None:
        mine = {"side": me["side"], "tags": int(me["tags"]), "vaccinated": bool(me["vaccinated"]),
                "starter": bool(me["starter"])}
        if me["side"] == "human" and game["status"] != "over":
            mine["code"] = me["code"]
        if _later(me["immune_until"], now):
            mine["immune_until"] = me["immune_until"]
        rest = _rest_until(me) if me["side"] == "zombie" else None
        if rest and rest > now:
            mine["rest_until"] = rooms.iso(rest)
        view["me"] = mine
    if game["status"] == "over":
        results = json.loads(game["results_json"])
        strip = lambda rows: [{k: v for k, v in row.items() if k != "account_id"} for row in rows]
        view["results"] = {**results, "survivors": strip(results.get("survivors", [])),
                           "best_zombies": strip(results.get("best_zombies", []))}
        mine = view.setdefault("me", {}) if me is not None else None
        if mine is not None:
            mine["survived"] = any(r["account_id"] == viewer for r in results.get("survivors", []))
            mine["best_zombie"] = any(r["account_id"] == viewer for r in results.get("best_zombies", []))
    if staff:
        view["grid"] = [{"name": p["display_name"], "side": p["side"], "tags": int(p["tags"])} for p in players]
    return view


def current(conn, actor: int, season_id: int, *, allow_write: bool) -> dict:
    now = utcnow()
    game = _latest(conn, season_id)
    due = bool(game) and _due(conn, game, now)
    stale = _stale(conn, now)
    if (due or stale) and not allow_write:
        raise NeedsWrite()
    if due:
        advance(conn, game["id"], now)
    if stale:
        purge(conn, now)
    game = _latest(conn, season_id)
    staff = cases.can_manage(conn, actor, season_id)
    member = conn.execute(
        """SELECT 1 FROM v4_season_memberships m JOIN v4_seasons s ON s.id = m.season_id
           WHERE m.season_id=? AND m.account_id=? AND m.status='active' AND s.status='active'""",
        (season_id, actor)).fetchone() is not None
    rules = config()
    return {"game": _view(conn, game, actor, staff, now) if game else None, "can_host": staff, "can_play": member,
            "stations": _stations(conn, season_id),
            "rules": {k: rules[k] for k in ("min_players", "round_minutes", "tag_cooldown_seconds", "immune_seconds",
                                            "prize_min_players", "prize")}}


# --- действия участников ------------------------------------------------------------------------

def join(conn, actor: int, season_id: int) -> dict:
    authorize(conn, actor, season_id, write=True)
    game = _active(conn, season_id)
    if game is None:
        raise CaseError("Сейчас нет открытого раунда. Его открывает вожатый.", 404)
    if game["status"] != "lobby":
        raise CaseError("Раунд уже начался. Дождитесь следующего.", 409)
    if _player(conn, game["id"], actor) is None:
        count = int(conn.execute("SELECT COUNT(*) FROM v4_zombie_players WHERE game_id=?", (game["id"],)).fetchone()[0])
        if count >= config()["max_players"]:
            raise CaseError("Лобби заполнено.", 409)
        conn.execute("INSERT INTO v4_zombie_players(game_id, account_id, joined_at, code) VALUES (?,?,?,?)",
                     (game["id"], actor, rooms.iso(utcnow()), _new_code(conn, game["id"])))
    return current(conn, actor, season_id, allow_write=True)


def leave(conn, actor: int, season_id: int) -> dict:
    authorize(conn, actor, season_id)
    game = _active(conn, season_id)
    if game is None or game["status"] != "lobby":
        raise CaseError("Выйти можно только из лобби.", 409)
    conn.execute("DELETE FROM v4_zombie_players WHERE game_id=? AND account_id=?", (game["id"], actor))
    return current(conn, actor, season_id, allow_write=True)


def _running(conn, actor: int, season_id: int, now: datetime):
    """Раунд и игрок. (None, None) — раунд только что закончился: итоги записаны, ошибкой их не откатываем."""
    authorize(conn, actor, season_id, write=True)
    game = _active(conn, season_id)
    if game is None:
        raise CaseError("Сейчас нет раунда.", 404)
    if _due(conn, game, now):
        advance(conn, game["id"], now)
        return None, None
    if game["status"] != "running":
        raise CaseError("Раунд ещё не начался.", 409)
    me = _player(conn, game["id"], actor)
    if me is None:
        raise CaseError("Вы не в этом раунде.", 404)
    return game, me


def tag(conn, actor: int, season_id: int, code: str) -> dict:
    """Зомби коснулся плеча и вводит код с телефона жертвы."""
    now = utcnow()
    game, me = _running(conn, actor, season_id, now)
    if game is None:
        return current(conn, actor, season_id, allow_write=True)
    if me["side"] != "zombie":
        raise CaseError("Заражать могут только зомби.", 409)
    rest = _rest_until(me)
    if rest and rest > now:
        raise CaseError(f"Зомби приходит в себя ещё {math.ceil((rest - now).total_seconds())} с.", 429)
    victim = conn.execute(
        """SELECT p.*, a.display_name FROM v4_zombie_players p JOIN v4_accounts a ON a.id = p.account_id
           WHERE p.game_id=? AND p.code=?""", (game["id"], code)).fetchone()
    if victim is None or int(victim["account_id"]) == actor:
        raise CaseError("Код не подходит. Сверьте цифры на телефоне человека.", 404)
    if victim["side"] == "zombie":
        raise CaseError("Этот игрок уже зомби.", 409)
    if _later(victim["immune_until"], now):
        raise CaseError("У этого человека иммунитет после вакцины.", 409)
    conn.execute("UPDATE v4_zombie_players SET side='zombie', turned_at=?, immune_until=NULL WHERE game_id=? AND account_id=?",
                 (rooms.iso(now), game["id"], victim["account_id"]))
    conn.execute("UPDATE v4_zombie_players SET tags = tags + 1, last_tag_at=? WHERE game_id=? AND account_id=?",
                 (rooms.iso(now), game["id"], actor))
    advance(conn, game["id"], now)   # заразили последнего человека — раунд кончается сразу
    result = current(conn, actor, season_id, allow_write=True)
    result["tagged"] = victim["display_name"]
    return result


class Vaccines:
    """Вопросы на станциях и пауза после ошибки. Живут в памяти: ответ на телефон не уходит."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.pending: dict[int, dict] = {}
        self.cooldowns: dict[int, datetime] = {}

    def cooldown_left(self, account_id: int, now: datetime) -> int:
        with self.lock:
            until = self.cooldowns.get(account_id)
        return max(0, math.ceil((until - now).total_seconds())) if until else 0

    def make(self, account_id: int, game_id: int, now: datetime) -> dict:
        words = cipher.content()["words"]
        word = _rng.choice(words)
        options = _rng.sample([w["ru"] for w in words if w["ru"] != word["ru"]], QUESTION_OPTIONS - 1) + [word["ru"]]
        _rng.shuffle(options)
        with self.lock:
            self.pending[account_id] = {"game_id": game_id, "answer": options.index(word["ru"]), "created": now}
        return {"zh": word["zh"], "pinyin": word["pinyin"], "options": options}

    def take(self, account_id: int, game_id: int, now: datetime) -> int:
        with self.lock:
            question = self.pending.pop(account_id, None)
        if (not question or question["game_id"] != game_id
                or (now - question["created"]).total_seconds() > config()["question_seconds"]):
            raise CaseError("Вопрос не найден или время вышло. Попробуйте ещё раз у станции.", 409)
        return question["answer"]

    def rest(self, account_id: int, now: datetime) -> None:
        with self.lock:
            self.cooldowns[account_id] = now + timedelta(seconds=config()["wrong_cooldown_seconds"])
            for key in [k for k, until in self.cooldowns.items() if until <= now]:
                del self.cooldowns[key]


vaccines = Vaccines()


def vaccine_challenge(conn, actor: int, season_id: int, point: str, *, lon: float, lat: float, accuracy_m: float) -> dict:
    now = utcnow()
    game, me = _running(conn, actor, season_id, now)
    if game is None:
        return current(conn, actor, season_id, allow_write=True)
    if me["side"] != "zombie":
        raise CaseError("Вакцина нужна только зомби.", 409)
    if me["vaccinated"]:
        raise CaseError("Вакцина — одна на раунд, вы её уже получили.", 409)
    wait = vaccines.cooldown_left(actor, now)
    if wait:
        raise CaseError(f"Станция ждёт вас через {wait} с.", 429)
    if point not in capture.points():
        raise CaseError("Такой станции нет.", 404)
    row = capture._point_rows(conn, season_id).get(point)
    if row is None:
        raise CaseError("Станция ещё не подтверждена вожатым.", 404)
    capture._present(row, lon, lat, accuracy_m)
    return {"point": point, "question": vaccines.make(actor, int(game["id"]), now),
            "seconds": config()["question_seconds"]}


def vaccine_answer(conn, actor: int, season_id: int, choice: int) -> dict:
    now = utcnow()
    game, me = _running(conn, actor, season_id, now)
    if game is None:
        return current(conn, actor, season_id, allow_write=True)
    right = vaccines.take(actor, int(game["id"]), now)
    if me["side"] != "zombie" or me["vaccinated"]:
        raise CaseError("Вакцина вам сейчас не нужна.", 409)
    correct = choice == right
    if correct:
        # Новый код: старый уже знает тот, кто заразил.
        conn.execute(
            """UPDATE v4_zombie_players SET side='human', vaccinated=1, immune_until=?, code=?, turned_at=NULL
               WHERE game_id=? AND account_id=?""",
            (rooms.iso(now + timedelta(seconds=config()["immune_seconds"])), _new_code(conn, game["id"]),
             game["id"], actor))
    else:
        vaccines.rest(actor, now)
    result = current(conn, actor, season_id, allow_write=True)
    result["vaccine"] = {"correct": correct}
    return result


# --- вожатый ---------------------------------------------------------------------------------------

def create(conn, actor: int, season_id: int) -> dict:
    authorize(conn, actor, season_id, manage=True, write=True)
    if _active(conn, season_id):
        raise CaseError("Раунд уже идёт или ждёт игроков.", 409)
    now = utcnow()
    conn.execute(
        """INSERT INTO v4_zombie_games(season_id, host_account_id, status, state_json, created_at, updated_at)
           VALUES (?,?, 'lobby', '{}', ?, ?)""", (season_id, actor, rooms.iso(now), rooms.iso(now)))
    return current(conn, actor, season_id, allow_write=True)


def start(conn, actor: int, season_id: int) -> dict:
    authorize(conn, actor, season_id, manage=True, write=True)
    game = _active(conn, season_id)
    if game is None or game["status"] != "lobby":
        raise CaseError("Нет лобби, которое можно запустить.", 409)
    rules = config()
    ids = [int(p["account_id"]) for p in _players(conn, game["id"])]
    if len(ids) < rules["min_players"]:
        raise CaseError(f"Нужно хотя бы {rules['min_players']} игрока.", 409)
    now = utcnow()
    # Скрещение с Вирусом: кто сейчас болеет, тот и первый зомби. Не больше трети — иначе людям не убежать.
    infected = [pid for pid in ids if virus.is_infected(conn, season_id, pid)]
    if infected:
        _rng.shuffle(infected)
        starters, source = infected[:max(1, len(ids) // rules["start_share"])], "virus"
    else:
        starters, source = _rng.sample(ids, max(1, len(ids) // rules["lottery_per"])), "lottery"
    for pid in starters:
        conn.execute("UPDATE v4_zombie_players SET side='zombie', starter=1, turned_at=? WHERE game_id=? AND account_id=?",
                     (rooms.iso(now), game["id"], pid))
    state = {"starters": len(ids), "first_zombies": len(starters), "source": source}
    conn.execute("UPDATE v4_zombie_games SET status='running', state_json=?, started_at=?, ends_at=?, updated_at=? WHERE id=?",
                 (encoded(state), rooms.iso(now), rooms.iso(now + timedelta(minutes=rules["round_minutes"])),
                  rooms.iso(now), game["id"]))
    conn.execute(
        """INSERT INTO v4_audit_log(actor_account_id, season_id, action, entity_type, entity_id, after_json)
           VALUES (?, ?, 'zombie.start', 'zombie', ?, ?)""", (actor, season_id, str(game["id"]), encoded(state)))
    return current(conn, actor, season_id, allow_write=True)


def cancel(conn, actor: int, season_id: int) -> dict:
    """Остановить раунд без призов."""
    authorize(conn, actor, season_id, manage=True, write=True)
    game = _active(conn, season_id)
    if game is None:
        raise CaseError("Нет раунда, который можно остановить.", 409)
    now = utcnow()
    state = json.loads(game["state_json"])
    state["cancelled"] = True
    conn.execute("UPDATE v4_zombie_games SET status='over', state_json=?, results_json=?, updated_at=?, finished_at=? WHERE id=?",
                 (encoded(state), encoded({"reason": "cancelled", "survivors": [], "best_zombies": []}),
                  rooms.iso(now), rooms.iso(now), game["id"]))
    conn.execute(
        """INSERT INTO v4_audit_log(actor_account_id, season_id, action, entity_type, entity_id, after_json)
           VALUES (?, ?, 'zombie.cancel', 'zombie', ?, '{}')""", (actor, season_id, str(game["id"])))
    return current(conn, actor, season_id, allow_write=True)
