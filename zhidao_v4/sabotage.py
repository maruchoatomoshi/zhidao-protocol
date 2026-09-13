"""Саботаж (V4_GAMES.md §4.12). Записи — внутри BEGIN IMMEDIATE.

Among Us вживую. Экипаж ходит по станциям — подтверждённым точкам кампуса,
как в Захвате, — и отвечает на китайские вопросы: так растёт полоса заданий.
Среди экипажа тайно прячутся саботажники. Саботажник касается плеча и вводит
шестизначный код с телефона жертвы — жертва выведена: она молчит, но может
доделывать задания призраком. Капитаны созывают собрание: все сходятся к
капитану, обсуждают вслух и голосуют в приложении; кого выбрало большинство,
тот покидает игру.

Решения пользователя 2026-09-13: станции — точки по GPS, без табличек с QR;
саботажники **только выводят** (без поломок станций); задания — **вопрос у
станции**; собрания созывают **капитаны** (предложение пользователя).

Черновик Claude, числа — sabotage.json: капитанов выбирает жребий только из
экипажа, их имена видят все (чтобы знать, к кому идти), у капитана 2 собрания
за игру; саботажник один на шесть игроков, капитан один на пять членов
экипажа; у каждого до 4 заданий на разных станциях; саботажник ждёт минуту
после старта, после каждого выведения и после собрания; собрание длится
2,5 минуты и останавливает часы игры; ничья или «пропустить» — никто не
уходит; выгнанного раскрывают. Экипаж побеждает, выполнив все задания или
выгнав всех саботажников; саботажники — сравнявшись числом с живым экипажем
или когда 30 минут истекли. Победители получают по 10★ в играх от 8 человек,
не чаще раза в сезон-день. У саботажников такие же задания, но их ответы
полосу не двигают; поэтому полоса обновляется только на собраниях.

Честность: роль, код и задания видит только их хозяин; союзники-саботажники
видят друг друга. Правильный вариант вопроса не уходит на телефон.
Приватность: кто кого вывел, не записывается; голоса удаляются после подсчёта;
через полчаса после конца удаляется состав, остаются итоги.
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

from . import capture, cases, cipher, rooms, shop, story
from .cases import CaseError, authorize, encoded, ensure_wallet
from .diary import full_wallet

CONFIG_PATH = Path(__file__).parent / "static" / "app" / "assets" / "games" / "sabotage.json"
PRIZE_OPERATION = "sabotage.prize"
QUESTION_OPTIONS = 3
LIVE = ("running", "meeting")
_rng = random.SystemRandom()


class NeedsWrite(RuntimeError):
    """Опрос обнаружил, что собрание пора подсчитать, игру закончить или почистить."""


def utcnow() -> datetime:
    return shop.utcnow()


@lru_cache(maxsize=1)
def config() -> dict:
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    for key in ("min_players", "max_players", "round_minutes", "saboteur_per", "captain_per", "captain_meetings",
                "tasks_per_player", "kill_cooldown_seconds", "meeting_seconds", "question_seconds",
                "wrong_cooldown_seconds", "keep_minutes", "prize_min_players"):
        if type(data.get(key)) is not int or data[key] <= 0:
            raise ValueError(f"sabotage.json: {key} должно быть положительным целым")
    if data["min_players"] < 4 or data["saboteur_per"] < 3:
        raise ValueError("sabotage.json: экипажа на старте должно быть заметно больше, чем саботажников")
    if type(data["prize"].get("winner_stars")) is not int or data["prize"]["winner_stars"] < 0:
        raise ValueError("sabotage.json: prize.winner_stars — неотрицательное целое")
    return data


# --- строки ------------------------------------------------------------------------------

def _active(conn, season_id: int):
    return conn.execute(
        "SELECT * FROM v4_sabotage_games WHERE season_id=? AND status IN ('lobby','running','meeting') ORDER BY id DESC LIMIT 1",
        (season_id,)).fetchone()


def _latest(conn, season_id: int):
    return conn.execute(
        "SELECT * FROM v4_sabotage_games WHERE season_id=? AND (status<>'over' OR purged=0) ORDER BY id DESC LIMIT 1",
        (season_id,)).fetchone()


def _game(conn, game_id: int):
    return conn.execute("SELECT * FROM v4_sabotage_games WHERE id=?", (game_id,)).fetchone()


def _players(conn, game_id: int) -> list:
    return conn.execute(
        """SELECT p.*, a.display_name FROM v4_sabotage_players p JOIN v4_accounts a ON a.id = p.account_id
           WHERE p.game_id=? ORDER BY p.joined_at, p.account_id""", (game_id,)).fetchall()


def _player(conn, game_id: int, account_id: int):
    return conn.execute(
        """SELECT p.*, a.display_name FROM v4_sabotage_players p JOIN v4_accounts a ON a.id = p.account_id
           WHERE p.game_id=? AND p.account_id=?""", (game_id, account_id)).fetchone()


def _new_code(conn, game_id: int) -> str:
    while True:
        code = f"{secrets.randbelow(1_000_000):06d}"
        if not conn.execute("SELECT 1 FROM v4_sabotage_players WHERE game_id=? AND code=?", (game_id, code)).fetchone():
            return code


def _votes(conn, game_id: int, meeting: int) -> dict[int, int]:
    return {int(row["account_id"]): int(row["choice"]) for row in conn.execute(
        "SELECT account_id, choice FROM v4_sabotage_votes WHERE game_id=? AND meeting=?", (game_id, meeting))}


def _progress(players) -> tuple[int, int]:
    """Сделано и всего заданий экипажа. Задания саботажников не считаются."""
    done = total = 0
    for p in players:
        if p["role"] == "crew":
            total += len(json.loads(p["tasks_json"]))
            done += len(json.loads(p["done_json"]))
    return done, total


def _percent(players) -> int:
    done, total = _progress(players)
    return round(100 * done / total) if total else 0


def _rest_until(game, state: dict, me) -> datetime:
    """Саботажник ждёт после старта, после своего выведения и после собрания."""
    moments = [rooms.parse(v) for v in (game["started_at"], me["last_kill_at"], state.get("last_meeting_end")) if v]
    return max(moments) + timedelta(seconds=config()["kill_cooldown_seconds"])


def _cutoff(now: datetime) -> str:
    return rooms.iso(now - timedelta(minutes=config()["keep_minutes"]))


def _stale(conn, now: datetime) -> bool:
    return conn.execute("SELECT 1 FROM v4_sabotage_games WHERE status='over' AND purged=0 AND finished_at < ? LIMIT 1",
                        (_cutoff(now),)).fetchone() is not None


def purge(conn, now: datetime) -> None:
    """Через полчаса после конца игры забывается состав: роли, коды, задания."""
    for row in conn.execute("SELECT id FROM v4_sabotage_games WHERE status='over' AND purged=0 AND finished_at < ?",
                            (_cutoff(now),)).fetchall():
        conn.execute("DELETE FROM v4_sabotage_votes WHERE game_id=?", (row["id"],))
        conn.execute("DELETE FROM v4_sabotage_players WHERE game_id=?", (row["id"],))
        conn.execute("UPDATE v4_sabotage_games SET purged=1, state_json='{}' WHERE id=?", (row["id"],))


# --- ход игры -------------------------------------------------------------------------------

def _winner(players, game, now: datetime) -> tuple[str, str] | None:
    saboteurs = sum(1 for p in players if p["alive"] and p["role"] == "saboteur")
    crew = sum(1 for p in players if p["alive"] and p["role"] == "crew")
    done, total = _progress(players)
    if saboteurs == 0:
        return "crew", "ejected"
    if total and done >= total:
        return "crew", "tasks"
    if saboteurs >= crew:
        return "saboteurs", "parity"
    if game["status"] == "running" and now >= rooms.parse(game["ends_at"]):
        return "saboteurs", "time"
    return None


def _due(conn, game, now: datetime) -> bool:
    if game["status"] == "running":
        return _winner(_players(conn, game["id"]), game, now) is not None
    if game["status"] == "meeting":
        meeting = json.loads(game["state_json"])["meeting"]
        if now >= rooms.parse(meeting["until"]):
            return True
        alive = {int(p["account_id"]) for p in _players(conn, game["id"]) if p["alive"]}
        return bool(alive) and alive <= set(_votes(conn, game["id"], meeting["number"]))
    return False


def _resolve_meeting(conn, game, now: datetime) -> None:
    state = json.loads(game["state_json"])
    meeting = state.pop("meeting")
    alive = {int(p["account_id"]): p for p in _players(conn, game["id"]) if p["alive"]}
    tally: dict[int, int] = {}
    for voter, choice in _votes(conn, game["id"], meeting["number"]).items():
        if voter in alive and (choice == 0 or choice in alive):
            tally[choice] = tally.get(choice, 0) + 1
    entry = {"meeting": meeting["number"], "caller": meeting["caller"], "ejected": None, "was_saboteur": None,
             "votes": sum(tally.values())}
    if tally:
        top = max(tally.values())
        leaders = [choice for choice, n in tally.items() if n == top]
        # Ничья или «пропустить» — никто не уходит.
        if len(leaders) == 1 and leaders[0] != 0:
            out = alive[leaders[0]]
            conn.execute("UPDATE v4_sabotage_players SET alive=0, ejected=1, out_at=? WHERE game_id=? AND account_id=?",
                         (rooms.iso(now), game["id"], leaders[0]))
            entry.update(ejected=out["display_name"], was_saboteur=out["role"] == "saboteur")
    conn.execute("DELETE FROM v4_sabotage_votes WHERE game_id=?", (game["id"],))
    state.setdefault("history", []).append(entry)
    state["last_meeting_end"] = rooms.iso(now)
    state["bar"] = _percent(_players(conn, game["id"]))
    # Собрание останавливает часы игры.
    paused = now - rooms.parse(meeting["started"])
    conn.execute("UPDATE v4_sabotage_games SET status='running', state_json=?, ends_at=?, updated_at=? WHERE id=?",
                 (encoded(state), rooms.iso(rooms.parse(game["ends_at"]) + paused), rooms.iso(now), game["id"]))


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


def _finish(conn, game, now: datetime, side: str, reason: str) -> None:
    season = conn.execute("SELECT * FROM v4_seasons WHERE id=?", (game["season_id"],)).fetchone()
    state = json.loads(game["state_json"])
    state.pop("meeting", None)
    rules = config()
    players = _players(conn, game["id"])
    prizes_on = int(state.get("starters") or 0) >= rules["prize_min_players"]
    day = shop.shop_day(season, now)
    role = "crew" if side == "crew" else "saboteur"
    winners = []
    for p in players:
        if p["role"] != role:
            continue
        stars, limited = 0, False
        if prizes_on and rules["prize"]["winner_stars"] > 0:
            if conn.execute("INSERT OR IGNORE INTO v4_sabotage_prize_days(season_id, account_id, prize_day) VALUES (?,?,?)",
                            (season["id"], int(p["account_id"]), day)).rowcount:
                stars = rules["prize"]["winner_stars"]
                _credit(conn, season["id"], int(p["account_id"]), stars, {"game": int(game["id"]), "side": side})
            else:
                limited = True
        winners.append({"account_id": int(p["account_id"]), "name": p["display_name"], "prize": stars, "limited": limited})
    results = {"winner": side, "reason": reason, "prizes": prizes_on, "bar": _percent(players),
               "saboteurs": [p["display_name"] for p in players if p["role"] == "saboteur"],
               "winners": winners, "history": state.get("history", [])}
    conn.execute("UPDATE v4_sabotage_games SET status='over', state_json=?, results_json=?, updated_at=?, finished_at=? WHERE id=?",
                 (encoded(state), encoded(results), rooms.iso(now), rooms.iso(now), game["id"]))


def advance(conn, game_id: int, now: datetime) -> bool:
    """Доводит игру до «сейчас»: подсчитывает собрание, объявляет победу."""
    changed = False
    for _ in range(3):
        game = _game(conn, game_id)
        if game is None or not _due(conn, game, now):
            break
        if game["status"] == "meeting":
            _resolve_meeting(conn, game, now)
        else:
            _finish(conn, game, now, *_winner(_players(conn, game_id), game, now))
        changed = True
    return changed


# --- что видит телефон ------------------------------------------------------------------------

def _station_name(code: str) -> str | None:
    return story.feature_names().get(capture.points()[code]["feature"], {}).get("name_ru")


def _view(conn, game, viewer: int, staff: bool, now: datetime) -> dict:
    state = json.loads(game["state_json"])
    players = _players(conn, game["id"])
    alive_ids = [int(p["account_id"]) for p in players if p["alive"]]
    view = {"id": int(game["id"]), "status": game["status"], "players": len(players), "alive": len(alive_ids),
            "ends_at": game["ends_at"], "cancelled": bool(state.get("cancelled")), "bar": state.get("bar", 0),
            "captains": [p["display_name"] for p in players if p["captain"]],
            "history": state.get("history", [])}
    votes = {}
    if game["status"] == "meeting":
        meeting = state["meeting"]
        votes = _votes(conn, game["id"], meeting["number"])
        view["meeting"] = {"number": meeting["number"], "caller": meeting["caller"], "until": meeting["until"],
                           "voted": len(set(votes) & set(alive_ids)), "voters": len(alive_ids),
                           "candidates": [{"account_id": int(p["account_id"]), "name": p["display_name"]}
                                          for p in players if p["alive"]]}
    me = next((p for p in players if int(p["account_id"]) == viewer), None)
    if me is not None and game["status"] != "lobby":
        done = json.loads(me["done_json"])
        mine = {"role": me["role"], "captain": bool(me["captain"]), "alive": bool(me["alive"]),
                "ejected": bool(me["ejected"]),
                "tasks": [{"code": code, "name_ru": _station_name(code), "done": code in done}
                          for code in json.loads(me["tasks_json"]) if code in capture.points()]}
        if game["status"] in LIVE:
            if me["alive"]:
                mine["code"] = me["code"]
            if me["captain"]:
                mine["meetings_left"] = int(me["meetings_left"])
            if me["role"] == "saboteur":
                mine["allies"] = [p["display_name"] for p in players
                                  if p["role"] == "saboteur" and int(p["account_id"]) != viewer]
                rest = _rest_until(game, state, me)
                if rest > now:
                    mine["rest_until"] = rooms.iso(rest)
            wait = questions.cooldown_left(viewer, now)
            if wait:
                mine["task_wait"] = wait
            if game["status"] == "meeting":
                mine["vote"] = votes.get(viewer)
        view["me"] = mine
    elif me is not None:
        view["me"] = {"joined": True}
    if game["status"] == "over":
        results = json.loads(game["results_json"])
        view["results"] = {**results, "winners": [{k: v for k, v in r.items() if k != "account_id"}
                                                  for r in results.get("winners", [])]}
        if me is not None:
            view["me"]["won"] = any(r["account_id"] == viewer for r in results.get("winners", []))
    if staff:
        view["grid"] = []
        for p in players:
            done, total = len(json.loads(p["done_json"])), len(json.loads(p["tasks_json"]))
            view["grid"].append({"name": p["display_name"], "role": p["role"], "captain": bool(p["captain"]),
                                 "alive": bool(p["alive"]), "done": done, "total": total})
    return view


def current(conn, actor: int, season_id: int, *, allow_write: bool) -> dict:
    now = utcnow()
    game = _latest(conn, season_id)
    due = bool(game) and game["status"] in LIVE and _due(conn, game, now)
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
            "stations": len(capture._point_rows(conn, season_id)),
            "rules": {k: rules[k] for k in ("min_players", "round_minutes", "captain_meetings", "meeting_seconds",
                                            "prize_min_players", "prize")}}


# --- вопросы у станций ---------------------------------------------------------------------------

class TaskQuestions:
    """Вопрос у станции и пауза после ошибки. Живут в памяти: ответ на телефон не уходит."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.pending: dict[int, dict] = {}
        self.cooldowns: dict[int, datetime] = {}

    def cooldown_left(self, account_id: int, now: datetime) -> int:
        with self.lock:
            until = self.cooldowns.get(account_id)
        return max(0, math.ceil((until - now).total_seconds())) if until else 0

    def make(self, account_id: int, game_id: int, point: str, now: datetime) -> dict:
        words = cipher.content()["words"]
        word = _rng.choice(words)
        options = _rng.sample([w["ru"] for w in words if w["ru"] != word["ru"]], QUESTION_OPTIONS - 1) + [word["ru"]]
        _rng.shuffle(options)
        with self.lock:
            self.pending[account_id] = {"game_id": game_id, "point": point, "answer": options.index(word["ru"]),
                                        "created": now}
        return {"zh": word["zh"], "pinyin": word["pinyin"], "options": options}

    def take(self, account_id: int, game_id: int, now: datetime) -> dict:
        with self.lock:
            question = self.pending.pop(account_id, None)
        if (not question or question["game_id"] != game_id
                or (now - question["created"]).total_seconds() > config()["question_seconds"]):
            raise CaseError("Вопрос не найден или время вышло. Попробуйте ещё раз у станции.", 409)
        return question

    def rest(self, account_id: int, now: datetime) -> None:
        with self.lock:
            self.cooldowns[account_id] = now + timedelta(seconds=config()["wrong_cooldown_seconds"])
            for key in [k for k, until in self.cooldowns.items() if until <= now]:
                del self.cooldowns[key]


questions = TaskQuestions()


# --- действия участников ------------------------------------------------------------------------

def join(conn, actor: int, season_id: int) -> dict:
    authorize(conn, actor, season_id, write=True)
    game = _active(conn, season_id)
    if game is None:
        raise CaseError("Сейчас нет открытой игры. Её открывает вожатый.", 404)
    if game["status"] != "lobby":
        raise CaseError("Игра уже началась. Дождитесь следующей.", 409)
    if _player(conn, game["id"], actor) is None:
        count = int(conn.execute("SELECT COUNT(*) FROM v4_sabotage_players WHERE game_id=?", (game["id"],)).fetchone()[0])
        if count >= config()["max_players"]:
            raise CaseError("Лобби заполнено.", 409)
        conn.execute("INSERT INTO v4_sabotage_players(game_id, account_id, joined_at, code) VALUES (?,?,?,?)",
                     (game["id"], actor, rooms.iso(utcnow()), _new_code(conn, game["id"])))
    return current(conn, actor, season_id, allow_write=True)


def leave(conn, actor: int, season_id: int) -> dict:
    authorize(conn, actor, season_id)
    game = _active(conn, season_id)
    if game is None or game["status"] != "lobby":
        raise CaseError("Выйти можно только из лобби.", 409)
    conn.execute("DELETE FROM v4_sabotage_players WHERE game_id=? AND account_id=?", (game["id"], actor))
    return current(conn, actor, season_id, allow_write=True)


def _live(conn, actor: int, season_id: int, now: datetime):
    """Игра и игрок. (None, None) — игра только что сдвинулась: итоги записаны, ошибкой их не откатываем."""
    authorize(conn, actor, season_id, write=True)
    game = _active(conn, season_id)
    if game is None:
        raise CaseError("Сейчас нет игры.", 404)
    if game["status"] in LIVE and _due(conn, game, now):
        advance(conn, game["id"], now)
        return None, None
    if game["status"] == "lobby":
        raise CaseError("Игра ещё не началась.", 409)
    me = _player(conn, game["id"], actor)
    if me is None:
        raise CaseError("Вы не в этой игре.", 404)
    return game, me


def eliminate(conn, actor: int, season_id: int, code: str) -> dict:
    """Саботажник коснулся плеча и вводит код с телефона жертвы."""
    now = utcnow()
    game, me = _live(conn, actor, season_id, now)
    if game is None:
        return current(conn, actor, season_id, allow_write=True)
    if game["status"] == "meeting":
        raise CaseError("Идёт собрание — сейчас никого не выводят.", 409)
    if me["role"] != "saboteur" or not me["alive"]:
        raise CaseError("Выводить могут только саботажники.", 409)
    rest = _rest_until(game, json.loads(game["state_json"]), me)
    if rest > now:
        raise CaseError(f"Саботажнику нужно выждать ещё {math.ceil((rest - now).total_seconds())} с.", 429)
    victim = conn.execute(
        """SELECT p.*, a.display_name FROM v4_sabotage_players p JOIN v4_accounts a ON a.id = p.account_id
           WHERE p.game_id=? AND p.code=?""", (game["id"], code)).fetchone()
    if victim is None or int(victim["account_id"]) == actor or not victim["alive"]:
        raise CaseError("Код не подходит. Сверьте цифры на телефоне игрока.", 404)
    if victim["role"] == "saboteur":
        raise CaseError("Это ваш союзник.", 409)
    conn.execute("UPDATE v4_sabotage_players SET alive=0, out_at=? WHERE game_id=? AND account_id=?",
                 (rooms.iso(now), game["id"], victim["account_id"]))
    conn.execute("UPDATE v4_sabotage_players SET last_kill_at=? WHERE game_id=? AND account_id=?",
                 (rooms.iso(now), game["id"], actor))
    advance(conn, game["id"], now)   # саботажники сравнялись с экипажем — игра кончается сразу
    result = current(conn, actor, season_id, allow_write=True)
    result["eliminated"] = victim["display_name"]
    return result


def task_challenge(conn, actor: int, season_id: int, point: str, *, lon: float, lat: float, accuracy_m: float) -> dict:
    now = utcnow()
    game, me = _live(conn, actor, season_id, now)
    if game is None:
        return current(conn, actor, season_id, allow_write=True)
    if game["status"] == "meeting":
        raise CaseError("Идёт собрание — задания подождут.", 409)
    if point not in json.loads(me["tasks_json"]):
        raise CaseError("Этой станции нет в ваших заданиях.", 404)
    if point in json.loads(me["done_json"]):
        raise CaseError("Это задание уже выполнено.", 409)
    wait = questions.cooldown_left(actor, now)
    if wait:
        raise CaseError(f"Станция ждёт вас через {wait} с.", 429)
    row = capture._point_rows(conn, season_id).get(point)
    if row is None:
        raise CaseError("Станция ещё не подтверждена вожатым.", 404)
    capture._present(row, lon, lat, accuracy_m)
    return {"point": point, "question": questions.make(actor, int(game["id"]), point, now),
            "seconds": config()["question_seconds"]}


def task_answer(conn, actor: int, season_id: int, choice: int) -> dict:
    now = utcnow()
    game, me = _live(conn, actor, season_id, now)
    if game is None:
        return current(conn, actor, season_id, allow_write=True)
    if game["status"] == "meeting":
        raise CaseError("Идёт собрание — задания подождут.", 409)
    question = questions.take(actor, int(game["id"]), now)
    done = json.loads(me["done_json"])
    if question["point"] in done:
        raise CaseError("Это задание уже выполнено.", 409)
    correct = choice == question["answer"]
    if correct:
        # Саботажнику задание тоже отмечается — чтобы не выдать себя, — но полосу экипажа оно не двигает.
        done.append(question["point"])
        conn.execute("UPDATE v4_sabotage_players SET done_json=? WHERE game_id=? AND account_id=?",
                     (encoded(done), game["id"], actor))
        advance(conn, game["id"], now)
    else:
        questions.rest(actor, now)
    result = current(conn, actor, season_id, allow_write=True)
    result["task"] = {"correct": correct}
    return result


def call_meeting(conn, actor: int, season_id: int) -> dict:
    now = utcnow()
    game, me = _live(conn, actor, season_id, now)
    if game is None:
        return current(conn, actor, season_id, allow_write=True)
    if game["status"] == "meeting":
        raise CaseError("Собрание уже идёт.", 409)
    if not me["captain"] or not me["alive"]:
        raise CaseError("Собрание созывают только капитаны.", 409)
    if int(me["meetings_left"]) <= 0:
        raise CaseError("Вы уже созвали все свои собрания.", 409)
    state = json.loads(game["state_json"])
    number = int(state.get("meetings") or 0) + 1
    state["meetings"] = number
    state["meeting"] = {"number": number, "caller": me["display_name"], "started": rooms.iso(now),
                        "until": rooms.iso(now + timedelta(seconds=config()["meeting_seconds"]))}
    conn.execute("UPDATE v4_sabotage_players SET meetings_left = meetings_left - 1 WHERE game_id=? AND account_id=?",
                 (game["id"], actor))
    conn.execute("UPDATE v4_sabotage_games SET status='meeting', state_json=?, updated_at=? WHERE id=?",
                 (encoded(state), rooms.iso(now), game["id"]))
    return current(conn, actor, season_id, allow_write=True)


def vote(conn, actor: int, season_id: int, choice: int) -> dict:
    """Голос на собрании: номер игрока или 0 — «пропустить»."""
    now = utcnow()
    game, me = _live(conn, actor, season_id, now)
    if game is None:
        return current(conn, actor, season_id, allow_write=True)
    if game["status"] != "meeting":
        raise CaseError("Голосуют только на собрании.", 409)
    if not me["alive"]:
        raise CaseError("Выведенные не голосуют.", 409)
    alive = {int(p["account_id"]) for p in _players(conn, game["id"]) if p["alive"]}
    if choice != 0 and choice not in alive:
        raise CaseError("Такого игрока нет среди живых.", 404)
    meeting = json.loads(game["state_json"])["meeting"]["number"]
    conn.execute(
        """INSERT INTO v4_sabotage_votes(game_id, meeting, account_id, choice) VALUES (?,?,?,?)
           ON CONFLICT(game_id, meeting, account_id) DO UPDATE SET choice=excluded.choice""",
        (game["id"], meeting, actor, choice))
    advance(conn, game["id"], now)   # проголосовали все живые — собрание подсчитывается сразу
    return current(conn, actor, season_id, allow_write=True)


# --- вожатый ---------------------------------------------------------------------------------------

def create(conn, actor: int, season_id: int) -> dict:
    authorize(conn, actor, season_id, manage=True, write=True)
    if _active(conn, season_id):
        raise CaseError("Игра уже идёт или ждёт игроков.", 409)
    now = utcnow()
    conn.execute(
        """INSERT INTO v4_sabotage_games(season_id, host_account_id, status, state_json, created_at, updated_at)
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
        raise CaseError(f"Нужно хотя бы {rules['min_players']} игроков.", 409)
    stations = sorted(capture._point_rows(conn, season_id))
    if not stations:
        raise CaseError("Нужна хотя бы одна станция: подтвердите точки Захвата на месте.", 409)
    now = utcnow()
    _rng.shuffle(ids)
    count = max(1, len(ids) // rules["saboteur_per"])
    saboteurs, crew = ids[:count], ids[count:]
    captains = set(crew[:max(1, len(crew) // rules["captain_per"])])
    for pid in ids:
        tasks = _rng.sample(stations, min(rules["tasks_per_player"], len(stations)))
        conn.execute(
            """UPDATE v4_sabotage_players SET role=?, captain=?, meetings_left=?, tasks_json=?, done_json='[]'
               WHERE game_id=? AND account_id=?""",
            ("saboteur" if pid in saboteurs else "crew", 1 if pid in captains else 0,
             rules["captain_meetings"] if pid in captains else 0, encoded(tasks), game["id"], pid))
    state = {"starters": len(ids), "saboteurs": count, "bar": 0, "history": [], "meetings": 0}
    conn.execute("UPDATE v4_sabotage_games SET status='running', state_json=?, started_at=?, ends_at=?, updated_at=? WHERE id=?",
                 (encoded(state), rooms.iso(now), rooms.iso(now + timedelta(minutes=rules["round_minutes"])),
                  rooms.iso(now), game["id"]))
    conn.execute(
        """INSERT INTO v4_audit_log(actor_account_id, season_id, action, entity_type, entity_id, after_json)
           VALUES (?, ?, 'sabotage.start', 'sabotage', ?, ?)""",
        (actor, season_id, str(game["id"]), encoded({"players": len(ids), "saboteurs": count, "captains": len(captains)})))
    return current(conn, actor, season_id, allow_write=True)


def cancel(conn, actor: int, season_id: int) -> dict:
    """Остановить игру без наград."""
    authorize(conn, actor, season_id, manage=True, write=True)
    game = _active(conn, season_id)
    if game is None:
        raise CaseError("Нет игры, которую можно остановить.", 409)
    now = utcnow()
    state = json.loads(game["state_json"])
    state.pop("meeting", None)
    state["cancelled"] = True
    conn.execute("DELETE FROM v4_sabotage_votes WHERE game_id=?", (game["id"],))
    conn.execute("UPDATE v4_sabotage_games SET status='over', state_json=?, results_json=?, updated_at=?, finished_at=? WHERE id=?",
                 (encoded(state), encoded({"reason": "cancelled", "winners": [], "saboteurs": []}),
                  rooms.iso(now), rooms.iso(now), game["id"]))
    conn.execute(
        """INSERT INTO v4_audit_log(actor_account_id, season_id, action, entity_type, entity_id, after_json)
           VALUES (?, ?, 'sabotage.cancel', 'sabotage', ?, '{}')""", (actor, season_id, str(game["id"])))
    return current(conn, actor, season_id, allow_write=True)
