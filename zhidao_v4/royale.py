"""Протокол 60 — королевская битва на всю смену (V4_GAMES.md §4.12). Записи — внутри BEGIN IMMEDIATE.

Вожатый открывает лобби и выводит игру на большой экран. Участники сезона
входят со своих телефонов, и вся смена одновременно отвечает на китайские
слова. Ошибся или не успел — выбыл. Вопросы усложняются: сначала иероглиф с
пиньинем и три перевода, потом без пиньиня и четыре варианта, потом перевод →
иероглиф и меньше времени. Выбывшие не скучают: между раундами они голосуют за
«сюрприз» выжившим — меньше времени, без пиньиня или лишний вариант.

Решения пользователя 2026-09-13: одна ошибка — выбыл; вопросы из словаря
китайских слов; воскрешение за 15★ — один раз за игру и только пока в игре
больше половины начавших; топ-3 получают 30/20/10★ и столько же REP.
Защита экономики, добавленная Claude (числа — royale.json): призы только в
играх от 10 участников, и один человек получает приз не чаще раза в сезон-день.

Места: выжившие выше выбывших; выбывшие позже выше выбывших раньше; при
равенстве выше тот, кто суммарно отвечал быстрее (молчание считается полным
временем раунда).

Честность: время и исход считает сервер; правильный вариант не уходит на
телефон до разбора раунда. Приватность: состав, ответы и голоса удаляются через
полчаса после конца игры; остаётся только таблица мест.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

from . import capture, cases, cipher, rooms, shop
from .cases import CaseError, authorize, encoded, ensure_wallet, replay
from .diary import full_wallet

CONFIG_PATH = Path(__file__).parent / "static" / "app" / "assets" / "games" / "royale.json"
SURPRISES = ("fast", "hanzi", "more", "mirror", "shuffle")
SPECIAL_KINDS = ("tone", "number", "odd", "pair")
TONES = {"a": "āáǎà", "e": "ēéěè", "i": "īíǐì", "o": "ōóǒò", "u": "ūúǔù", "ü": "ǖǘǚǜ"}
MARKED = {mark: (vowel, tone) for vowel, marks in TONES.items() for tone, mark in enumerate(marks, start=1)}
DIGITS = "零一二三四五六七八九"
REVIVE_OPERATION = "royale.revive"
PRIZE_OPERATION = "royale.prize"
REFUND_OPERATION = "royale.refund"
ACTIVE = ("lobby", "question", "reveal")
_rng = random.SystemRandom()


class NeedsWrite(RuntimeError):
    """Опрос обнаружил, что раунд пора закрыть или игру почистить."""


def utcnow() -> datetime:
    return shop.utcnow()


@lru_cache(maxsize=1)
def config() -> dict:
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    for key in ("min_players", "max_players", "prize_min_players", "grace_ms", "intro_seconds", "reveal_seconds",
                "max_rounds", "revive_price", "keep_minutes"):
        if type(data.get(key)) is not int or data[key] <= 0:
            raise ValueError(f"royale.json: {key} должно быть положительным целым")
    if data["min_players"] < 2:
        raise ValueError("royale.json: в битве нужно хотя бы двое")
    if not data["prizes"] or any(type(p.get("stars")) is not int or type(p.get("rep")) is not int for p in data["prizes"]):
        raise ValueError("royale.json: призы — целые stars и rep")
    stages = data["stages"]
    if not stages or stages[0]["from_round"] != 1:
        raise ValueError("royale.json: первая ступень начинается с раунда 1")
    for stage in stages:
        if stage["direction"] not in ("zh", "ru") or not 2 <= stage["options"] <= 8 or stage["seconds"] < 3:
            raise ValueError("royale.json: ступень задана неверно")
    for special in data.get("specials", []):
        if (special.get("kind") not in SPECIAL_KINDS or type(special.get("from_round")) is not int
                or type(special.get("every")) is not int or special["from_round"] < 1 or special["every"] < 1):
            raise ValueError("royale.json: особый раунд задан неверно")
    if "odd" in {special["kind"] for special in data.get("specials", [])}:
        topics = data.get("odd_topics") or {}
        known = {word["zh"] for word in cipher.content()["words"]}
        seen: set[str] = set()
        if len(topics) < 2:
            raise ValueError("royale.json: для «лишнего слова» нужны хотя бы две темы")
        for code, topic in topics.items():
            words = topic.get("words") or []
            if not str(topic.get("ru") or "").strip() or len(words) < 4:
                raise ValueError(f"royale.json: у темы {code} нужны название и хотя бы 4 слова")
            for zh in words:
                if zh not in known or zh in seen:
                    raise ValueError(f"royale.json: слова {zh} (тема {code}) нет в словаре или оно уже в другой теме")
                seen.add(zh)
    if type(data.get("final_seconds")) is not int or data["final_seconds"] < 3:
        raise ValueError("royale.json: final_seconds — целое не меньше 3")
    return data


# --- строки ------------------------------------------------------------------------------

def _active(conn, season_id: int):
    return conn.execute(
        "SELECT * FROM v4_royale_games WHERE season_id=? AND status IN ('lobby','question','reveal') ORDER BY id DESC LIMIT 1",
        (season_id,)).fetchone()


def _latest(conn, season_id: int):
    return conn.execute(
        "SELECT * FROM v4_royale_games WHERE season_id=? AND (status<>'over' OR purged=0) ORDER BY id DESC LIMIT 1",
        (season_id,)).fetchone()


def _game(conn, game_id: int):
    return conn.execute("SELECT * FROM v4_royale_games WHERE id=?", (game_id,)).fetchone()


def _players(conn, game_id: int) -> list:
    return conn.execute(
        """SELECT p.*, a.display_name FROM v4_royale_players p JOIN v4_accounts a ON a.id = p.account_id
           WHERE p.game_id=? ORDER BY p.joined_at, p.account_id""", (game_id,)).fetchall()


def _alive_count(conn, game_id: int) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM v4_royale_players WHERE game_id=? AND alive=1", (game_id,)).fetchone()[0])


def _answers(conn, game_id: int, round_no: int) -> dict[int, dict]:
    return {int(row["account_id"]): dict(row) for row in conn.execute(
        "SELECT * FROM v4_royale_answers WHERE game_id=? AND round=?", (game_id, round_no))}


def _save(conn, game_id: int, *, status: str, round_no: int, state: dict, now: datetime,
          results: list | None = None, finished: bool = False) -> None:
    conn.execute(
        """UPDATE v4_royale_games SET status=?, round=?, state_json=?, updated_at=?,
               results_json=COALESCE(?, results_json), finished_at=CASE WHEN ? THEN ? ELSE finished_at END
           WHERE id=?""",
        (status, round_no, json.dumps(state, ensure_ascii=False), rooms.iso(now),
         json.dumps(results, ensure_ascii=False) if results is not None else None,
         1 if finished else 0, rooms.iso(now), game_id))


def _cutoff(now: datetime) -> str:
    return rooms.iso(now - timedelta(minutes=config()["keep_minutes"]))


def _stale(conn, now: datetime) -> bool:
    return conn.execute("SELECT 1 FROM v4_royale_games WHERE status='over' AND purged=0 AND finished_at < ? LIMIT 1",
                        (_cutoff(now),)).fetchone() is not None


def purge(conn, now: datetime) -> None:
    """Через полчаса после конца игры забываются состав, ответы и голоса."""
    for row in conn.execute("SELECT id FROM v4_royale_games WHERE status='over' AND purged=0 AND finished_at < ?",
                            (_cutoff(now),)).fetchall():
        for table in ("v4_royale_answers", "v4_royale_votes", "v4_royale_players"):
            conn.execute(f"DELETE FROM {table} WHERE game_id=?", (row["id"],))
        conn.execute("UPDATE v4_royale_games SET purged=1, state_json='{}' WHERE id=?", (row["id"],))


# --- вопросы --------------------------------------------------------------------------------

def _stage(round_no: int) -> dict:
    current = config()["stages"][0]
    for stage in config()["stages"]:
        if stage["from_round"] <= round_no:
            current = stage
    return dict(current)


def _kind_for(round_no: int) -> str:
    """Особые раунды по расписанию royale.json: тоны и числа. Остальные — слово."""
    for special in config().get("specials", []):
        if round_no >= special["from_round"] and (round_no - special["from_round"]) % special["every"] == 0:
            return special["kind"]
    return "word"


def _retone(pinyin: str) -> list[str]:
    """Тот же слог во всех четырёх тонах. Только для слога с одной отметкой тона."""
    marks = [i for i, ch in enumerate(pinyin) if ch in MARKED]
    if len(marks) != 1:
        return []
    i = marks[0]
    vowel, _ = MARKED[pinyin[i]]
    return [pinyin[:i] + mark + pinyin[i + 1:] for mark in TONES[vowel]]


def _number_hanzi(n: int) -> str:
    """Число 1–99 иероглифами: 十, 十一, 二十, 七十五."""
    tens, ones = divmod(n, 10)
    text = ("" if tens == 1 else DIGITS[tens]) + "十" if tens else ""
    return text + (DIGITS[ones] if ones else "")


def _number_options(n: int, count: int) -> list[str]:
    """Ловушки для числа: соседние, ±10 и переставленные цифры (75 и 57)."""
    near = {n + 1, n - 1, n + 10, n - 10}
    if n % 10:
        near.add(int(str(n)[::-1]))
    pool = sorted(x for x in near if 11 <= x <= 99 and x != n)
    picks = _rng.sample(pool, min(count - 1, len(pool)))
    while len(picks) < count - 1:
        extra = _rng.randint(11, 99)
        if extra != n and extra not in picks:
            picks.append(extra)
    return [str(x) for x in picks] + [str(n)]


def _make_question(state: dict, round_no: int, now: datetime, *, final: bool = False) -> None:
    params = _stage(round_no)
    rules = config()["surprises"]
    surprise = state.get("surprise")
    seconds, options, pinyin = params["seconds"], params["options"], params["pinyin"]
    direction, kind = params["direction"], _kind_for(round_no)
    if final:
        seconds = config()["final_seconds"]
    if surprise == "fast":
        seconds = max(rules["min_seconds"], seconds - rules["fast_seconds"])
    elif surprise == "hanzi":
        pinyin = False
    elif surprise == "more":
        options = min(rules["max_options"], options + 1)
    words = cipher.content()["words"]
    used = set(state.get("used", []))
    toned = [w for w in words if len(w["zh"]) == 1 and len(_retone(w["pinyin"])) == 4]
    if kind == "tone" and not toned:
        kind = "word"
    explain, hints = None, None
    by_zh = {w["zh"]: w for w in words}
    if kind == "number":
        number = _rng.randint(11, 99)
        right = str(number)
        prompt = {"zh": _number_hanzi(number), "pinyin": None}
        choices = _number_options(number, options)
        direction = "number"
    elif kind == "odd":
        # «Лишнее слово»: все варианты, кроме одного, — из одной темы royale.json.
        topics = config()["odd_topics"]
        code = _rng.choice(sorted(topics))
        same = topics[code]["words"]
        group = _rng.sample(same, min(options, len(same) + 1) - 1)
        right = _rng.choice(topics[_rng.choice(sorted(set(topics) - {code}))]["words"])
        choices = group + [right]
        prompt = {"task": "odd"}
        direction = "odd"
        explain = f"Лишнее — {right} ({by_zh[right]['ru']}), остальные — {topics[code]['ru']}."
    elif kind == "pair":
        # «Собери слово»: первый знак и перевод, выбрать второй. Ловушка не должна складываться в другое слово словаря.
        twos = [w for w in words if len(w["zh"]) == 2]
        word = _rng.choice([w for w in twos if w["zh"] not in used] or twos)
        state.setdefault("used", []).append(word["zh"])
        head, right = word["zh"][0], word["zh"][1]
        others = sorted(ch for ch in {w["zh"][1] for w in twos} if ch != right and head + ch not in by_zh)
        choices = _rng.sample(others, min(options - 1, len(others))) + [right]
        prompt = {"zh": head + "？", "ru": word["ru"], "pinyin": None}
        direction = "pair"
        explain = f"{word['zh']} {word['pinyin']} — {word['ru']}."
    else:
        pool = toned if kind == "tone" else words
        word = _rng.choice([w for w in pool if w["zh"] not in used] or pool)
        state.setdefault("used", []).append(word["zh"])
        if kind == "tone":
            right = word["pinyin"]
            others = [p for p in _retone(right) if p != right]
            prompt = {"zh": word["zh"], "pinyin": None}
            options = min(options, 4)
            direction = "tone"
        elif direction == "zh":
            right = word["ru"]
            others = sorted({w["ru"] for w in words} - {right})
            prompt = {"zh": word["zh"], "pinyin": word["pinyin"] if pinyin else None}
        else:
            right = word["zh"]
            others = sorted({w["zh"] for w in words} - {right})
            prompt = {"ru": word["ru"]}
        choices = _rng.sample(others, min(options - 1, len(others))) + [right]
    _rng.shuffle(choices)
    if kind == "odd" and pinyin:
        hints = [by_zh[choice]["pinyin"] for choice in choices]
    # explain — пояснение к разбору; на телефон оно уходит только после конца раунда.
    state["question"] = {"prompt": prompt, "options": choices, "answer": choices.index(right), "seconds": seconds,
                         "surprise": surprise, "direction": direction, "kind": kind, "final": final,
                         "explain": explain, "hints": hints}
    state["started_at"] = rooms.iso(now)
    state["deadline"] = rooms.iso(now + timedelta(seconds=seconds))
    state.pop("reveal", None)


# --- ход игры -------------------------------------------------------------------------------

def _due(conn, game, now: datetime) -> bool:
    if game["status"] not in ("question", "reveal"):
        return False
    state = json.loads(game["state_json"])
    if game["status"] == "reveal":
        return now >= rooms.parse(state["reveal_until"])
    if now >= rooms.parse(state["deadline"]) + timedelta(milliseconds=config()["grace_ms"]):
        return True
    alive = _alive_count(conn, game["id"])
    answered = conn.execute(
        """SELECT COUNT(*) FROM v4_royale_answers a JOIN v4_royale_players p
               ON p.game_id = a.game_id AND p.account_id = a.account_id AND p.alive = 1
           WHERE a.game_id=? AND a.round=?""", (game["id"], game["round"])).fetchone()[0]
    return alive > 0 and answered >= alive


def _close_round(conn, game, state: dict, now: datetime) -> None:
    question = state["question"]
    answers = _answers(conn, game["id"], game["round"])
    eliminated = 0
    for player in conn.execute("SELECT account_id FROM v4_royale_players WHERE game_id=? AND alive=1",
                               (game["id"],)).fetchall():
        pid = int(player["account_id"])
        given = answers.get(pid)
        ms = given["ms"] if given else question["seconds"] * 1000
        conn.execute("UPDATE v4_royale_players SET total_ms = total_ms + ? WHERE game_id=? AND account_id=?",
                     (ms, game["id"], pid))
        if not given or not given["correct"]:
            conn.execute("UPDATE v4_royale_players SET alive=0, out_round=? WHERE game_id=? AND account_id=?",
                         (game["round"], game["id"], pid))
            eliminated += 1
    alive = _alive_count(conn, game["id"])
    state.setdefault("history", []).append({"round": game["round"], "eliminated": eliminated, "alive": alive})
    state["reveal"] = {"answer": question["answer"], "eliminated": eliminated}
    state["reveal_until"] = rooms.iso(now + timedelta(seconds=config()["reveal_seconds"]))
    _save(conn, game["id"], status="reveal", round_no=game["round"], state=state, now=now)


def _next_or_finish(conn, game, state: dict, now: datetime) -> None:
    if _alive_count(conn, game["id"]) <= 1 or game["round"] >= config()["max_rounds"]:
        _finish(conn, game, state, now)
        return
    votes = {row["surprise"]: int(row["n"]) for row in conn.execute(
        "SELECT surprise, COUNT(*) AS n FROM v4_royale_votes WHERE game_id=? AND round=? GROUP BY surprise",
        (game["id"], game["round"]))}
    if votes:
        top = max(votes.values())
        state["surprise"] = _rng.choice(sorted(code for code, n in votes.items() if n == top))
    else:
        state["surprise"] = None
    round_no = game["round"] + 1
    # Остались двое из большой игры — финальная дуэль: своё время на ответ и своя заставка на экране.
    final = int(state.get("starters") or 0) > 2 and _alive_count(conn, game["id"]) == 2
    _make_question(state, round_no, now, final=final)
    _save(conn, game["id"], status="question", round_no=round_no, state=state, now=now)


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


def _finish(conn, game, state: dict, now: datetime) -> None:
    season = conn.execute("SELECT * FROM v4_seasons WHERE id=?", (game["season_id"],)).fetchone()
    last = game["round"] + 1
    ordered = sorted(_players(conn, game["id"]),
                     key=lambda p: (0 if p["alive"] else 1, -(last if p["alive"] else (p["out_round"] or 0)), p["total_ms"]))
    prizes = config()["prizes"] if state.get("starters", 0) >= config()["prize_min_players"] else []
    day = shop.shop_day(season, now)
    results = []
    for place, player in enumerate(ordered[:10], start=1):
        pid = int(player["account_id"])
        entry = {"place": place, "account_id": pid, "name": player["display_name"], "prize": None, "limited": False}
        if place <= len(prizes):
            prize = prizes[place - 1]
            taken = conn.execute("INSERT OR IGNORE INTO v4_royale_prize_days(season_id, account_id, prize_day) VALUES (?,?,?)",
                                 (season["id"], pid, day)).rowcount
            if taken:
                _credit(conn, season["id"], pid, stars=prize["stars"], rep=prize["rep"], operation=PRIZE_OPERATION,
                        details={"game": int(game["id"]), "place": place})
                entry["prize"] = prize
            else:
                entry["limited"] = True
        results.append(entry)
    state.pop("question", None) if state.get("cancelled") else None
    _save(conn, game["id"], status="over", round_no=game["round"], state=state, now=now, results=results, finished=True)


def advance(conn, game_id: int, now: datetime) -> bool:
    """Доводит игру до «сейчас». True — что-то сдвинулось."""
    changed = False
    for _ in range(4):
        game = _game(conn, game_id)
        if game is None or not _due(conn, game, now):
            break
        state = json.loads(game["state_json"])
        if game["status"] == "question":
            _close_round(conn, game, state, now)
        else:
            _next_or_finish(conn, game, state, now)
        changed = True
    return changed


# --- что видит телефон ------------------------------------------------------------------------

def _public_question(state: dict) -> dict:
    q = state["question"]
    return {"prompt": q["prompt"], "options": q["options"], "seconds": q["seconds"], "surprise": q["surprise"],
            "direction": q["direction"], "deadline": state["deadline"], "opens_at": state["started_at"],
            "kind": q.get("kind", "word"), "final": bool(q.get("final")), "hints": q.get("hints")}


def _view(conn, game, viewer: int, staff: bool, now: datetime) -> dict:
    state = json.loads(game["state_json"])
    # Заставка 3-2-1 перед первым вопросом: слово не уходит на телефон, пока идёт отсчёт.
    intro = game["status"] == "question" and now < rooms.parse(state["started_at"])
    players = _players(conn, game["id"])
    alive = sum(1 for p in players if p["alive"])
    starters = int(state.get("starters") or len(players))
    answers = _answers(conn, game["id"], game["round"]) if game["status"] in ("question", "reveal") else {}
    me = next((p for p in players if int(p["account_id"]) == viewer), None)
    view = {"id": int(game["id"]), "status": game["status"], "round": int(game["round"]), "starters": starters,
            "players": len(players), "alive": alive, "revive_price": config()["revive_price"],
            "cancelled": bool(state.get("cancelled")), "history": state.get("history", [])}
    if intro:
        view["intro_until"] = state["started_at"]
        view["answered"] = 0
    elif game["status"] == "question":
        view["question"] = _public_question(state)
        view["answered"] = sum(1 for pid in answers if any(int(p["account_id"]) == pid and p["alive"] for p in players))
    elif game["status"] == "reveal":
        view["question"] = _public_question(state)
        if state["question"].get("explain"):
            view["question"]["explain"] = state["question"]["explain"]
        votes = {code: 0 for code in SURPRISES}
        for row in conn.execute("SELECT surprise, COUNT(*) AS n FROM v4_royale_votes WHERE game_id=? AND round=? GROUP BY surprise",
                                (game["id"], game["round"])):
            votes[row["surprise"]] = int(row["n"])
        view["reveal"] = {**state["reveal"], "until": state["reveal_until"], "votes": votes}
    if me is not None:
        mine = answers.get(viewer)
        my_vote = conn.execute("SELECT surprise FROM v4_royale_votes WHERE game_id=? AND round=? AND account_id=?",
                               (game["id"], game["round"], viewer)).fetchone()
        view["me"] = {
            "alive": bool(me["alive"]), "out_round": me["out_round"], "revived": bool(me["revived"]),
            "answered": mine is not None, "choice": mine["choice"] if mine else None,
            "can_revive": game["status"] == "reveal" and not me["alive"] and not me["revived"] and alive * 2 > starters,
            "vote": my_vote["surprise"] if my_vote else None,
        }
    if game["status"] == "over":
        results = json.loads(game["results_json"])
        view["results"] = [{k: r[k] for k in ("place", "name", "prize", "limited")} for r in results]
        mine = next((r for r in results if r["account_id"] == viewer), None)
        if me is not None or mine:
            view.setdefault("me", {})["place"] = mine["place"] if mine else None
    if staff:
        frames = shop.frames_for(conn, [p["account_id"] for p in players])
        colors = {code: faction["color"] for code, faction in capture.factions().items()}
        view["grid"] = [{"name": p["display_name"], "alive": bool(p["alive"]), "revived": bool(p["revived"]),
                         "answered": int(p["account_id"]) in answers and game["status"] == "question",
                         "out_round": p["out_round"], "frame": frames.get(int(p["account_id"])),
                         "color": colors.get(capture.faction_of(conn, game["season_id"], int(p["account_id"])))}
                        for p in players]
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
    return {"game": _view(conn, game, actor, staff, now) if game else None, "can_host": staff, "can_play": member,
            "revive_price": config()["revive_price"], "prizes": config()["prizes"],
            "prize_min_players": config()["prize_min_players"]}


# --- действия участников ------------------------------------------------------------------------

def join(conn, actor: int, season_id: int) -> dict:
    authorize(conn, actor, season_id, write=True, staff_may_play=True)
    game = _active(conn, season_id)
    if game is None:
        raise CaseError("Сейчас нет открытой игры. Её открывает вожатый.", 404)
    if game["status"] != "lobby":
        raise CaseError("Игра уже началась. Дождитесь следующей.", 409)
    count = int(conn.execute("SELECT COUNT(*) FROM v4_royale_players WHERE game_id=?", (game["id"],)).fetchone()[0])
    if count >= config()["max_players"]:
        raise CaseError("Лобби заполнено.", 409)
    conn.execute("INSERT OR IGNORE INTO v4_royale_players(game_id, account_id, joined_at) VALUES (?,?,?)",
                 (game["id"], actor, rooms.iso(utcnow())))
    return current(conn, actor, season_id, allow_write=True)


def leave(conn, actor: int, season_id: int) -> dict:
    authorize(conn, actor, season_id, staff_may_play=True)
    game = _active(conn, season_id)
    if game is None or game["status"] != "lobby":
        raise CaseError("Выйти можно только из лобби.", 409)
    conn.execute("DELETE FROM v4_royale_players WHERE game_id=? AND account_id=?", (game["id"], actor))
    return current(conn, actor, season_id, allow_write=True)


def _in_play(conn, actor: int, season_id: int, now: datetime):
    authorize(conn, actor, season_id, write=True, staff_may_play=True)
    game = _active(conn, season_id)
    if game is None:
        raise CaseError("Игра не найдена.", 404)
    moved = False
    if _due(conn, game, now):
        moved = advance(conn, game["id"], now)
        game = _game(conn, game["id"])
    player = conn.execute("SELECT * FROM v4_royale_players WHERE game_id=? AND account_id=?",
                          (game["id"], actor)).fetchone()
    if player is None and not moved:
        raise CaseError("Вы не в этой игре.", 404)
    return game, player, moved


def answer(conn, actor: int, season_id: int, choice: int) -> dict:
    now = utcnow()
    game, player, moved = _in_play(conn, actor, season_id, now)
    if game["status"] != "question":
        # Время вышло раньше ответа: разбор раунда уже записан и возвращается, а не теряется.
        if moved:
            return current(conn, actor, season_id, allow_write=True)
        raise CaseError("Сейчас не время отвечать.", 409)
    if player is None or not player["alive"]:
        raise CaseError("Вы выбыли из этой игры.", 409)
    if conn.execute("SELECT 1 FROM v4_royale_answers WHERE game_id=? AND round=? AND account_id=?",
                    (game["id"], game["round"], actor)).fetchone():
        raise CaseError("Ответ уже принят.", 409)
    state = json.loads(game["state_json"])
    question = state["question"]
    if now < rooms.parse(state["started_at"]):
        raise CaseError("Вопрос ещё не открыт: идёт отсчёт.", 409)
    if not 0 <= choice < len(question["options"]):
        raise CaseError("Такого варианта нет.")
    ms = max(0, int((now - rooms.parse(state["started_at"])).total_seconds() * 1000))
    conn.execute("INSERT INTO v4_royale_answers(game_id, round, account_id, choice, ms, correct) VALUES (?,?,?,?,?,?)",
                 (game["id"], game["round"], actor, choice, ms, 1 if choice == question["answer"] else 0))
    advance(conn, game["id"], now)   # ответили все живые — раунд закрывается сразу
    return current(conn, actor, season_id, allow_write=True)


def vote(conn, actor: int, season_id: int, surprise: str) -> dict:
    now = utcnow()
    game, player, moved = _in_play(conn, actor, season_id, now)
    if surprise not in SURPRISES:
        raise CaseError("Такого сюрприза нет.")
    if game["status"] != "reveal":
        if moved:
            return current(conn, actor, season_id, allow_write=True)
        raise CaseError("Голосуют между раундами.", 409)
    if player is None or player["alive"]:
        raise CaseError("Сюрприз выбирают выбывшие.", 409)
    conn.execute(
        """INSERT INTO v4_royale_votes(game_id, round, account_id, surprise) VALUES (?,?,?,?)
           ON CONFLICT(game_id, round, account_id) DO UPDATE SET surprise=excluded.surprise""",
        (game["id"], game["round"], actor, surprise))
    return current(conn, actor, season_id, allow_write=True)


def revive(conn, actor: int, season_id: int, key: str, request_id=None):
    authorize(conn, actor, season_id, staff_may_play=True)
    game = _active(conn, season_id)
    key, digest, old = replay(conn, actor, REVIVE_OPERATION, key,
                              {"season_id": season_id, "game": int(game["id"]) if game else None})
    if old is not None:
        return old, True
    now = utcnow()
    game, player, _ = _in_play(conn, actor, season_id, now)
    if game["status"] != "reveal":
        raise CaseError("Воскреснуть можно только между раундами.", 409)
    if player is None or player["alive"]:
        raise CaseError("Вы и так в игре.", 409)
    if player["revived"]:
        raise CaseError("Воскрешение — один раз за игру.", 409)
    state = json.loads(game["state_json"])
    if _alive_count(conn, game["id"]) * 2 <= int(state.get("starters") or 0):
        raise CaseError("Воскрешение доступно только до середины игры.", 409)
    price = config()["revive_price"]
    ensure_wallet(conn, actor, season_id)
    before = full_wallet(conn, actor, season_id)
    if before["stars"] < price:
        raise CaseError(f"Не хватает звёзд: воскрешение стоит {price}★, у вас {before['stars']}★.", 409)
    conn.execute("UPDATE v4_case_wallets SET stars = stars - ? WHERE season_id=? AND account_id=?",
                 (price, season_id, actor))
    after = full_wallet(conn, actor, season_id)
    conn.execute(
        """INSERT INTO v4_economy_operations(season_id, account_id, actor_account_id, operation,
               stars_delta, scans_delta, rep_delta, stars_after, scans_after, rep_after, details_json)
           VALUES (?,?,?,?,?,0,0,?,?,?,?)""",
        (season_id, actor, actor, REVIVE_OPERATION, -price, after["stars"], after["scans"], after["rep"],
         encoded({"game": int(game["id"]), "round": int(game["round"]), "price": price})))
    conn.execute("UPDATE v4_royale_players SET alive=1, out_round=NULL, revived=1 WHERE game_id=? AND account_id=?",
                 (game["id"], actor))
    response = {"revived": True, "price": price, "stars": after["stars"], "game": int(game["id"])}
    serialized = encoded(response)
    conn.execute(
        """INSERT INTO v4_idempotency_keys(account_id, operation, idempotency_key, request_hash,
               response_status, response_json) VALUES (?,?,?,?,200,?)""",
        (actor, REVIVE_OPERATION, key, digest, serialized))
    conn.execute(
        """INSERT INTO v4_audit_log(actor_account_id, season_id, action, entity_type, entity_id, request_id,
               after_json, metadata_json) VALUES (?,?,?,'royale',?,?,?,?)""",
        (actor, season_id, REVIVE_OPERATION, str(game["id"]), request_id, serialized, encoded({"idempotency_key": key})))
    return response, False


# --- вожатый ---------------------------------------------------------------------------------------

def create(conn, actor: int, season_id: int) -> dict:
    authorize(conn, actor, season_id, manage=True, write=True)
    if _active(conn, season_id):
        raise CaseError("Игра уже идёт или ждёт игроков.", 409)
    now = utcnow()
    conn.execute(
        """INSERT INTO v4_royale_games(season_id, host_account_id, status, round, state_json, created_at, updated_at)
           VALUES (?,?, 'lobby', 0, ?, ?, ?)""",
        (season_id, actor, json.dumps({"used": [], "history": []}), rooms.iso(now), rooms.iso(now)))
    return current(conn, actor, season_id, allow_write=True)


def start(conn, actor: int, season_id: int) -> dict:
    authorize(conn, actor, season_id, manage=True, write=True)
    game = _active(conn, season_id)
    if game is None or game["status"] != "lobby":
        raise CaseError("Нет лобби, которое можно запустить.", 409)
    count = int(conn.execute("SELECT COUNT(*) FROM v4_royale_players WHERE game_id=?", (game["id"],)).fetchone()[0])
    if count < config()["min_players"]:
        raise CaseError(f"Нужно хотя бы {config()['min_players']} игрока.", 409)
    now = utcnow()
    state = json.loads(game["state_json"])
    state.update(starters=count, surprise=None)
    # Первый вопрос открывается после заставки: отсчёт не съедает время на ответ.
    _make_question(state, 1, now + timedelta(seconds=config()["intro_seconds"]))
    _save(conn, game["id"], status="question", round_no=1, state=state, now=now)
    conn.execute(
        """INSERT INTO v4_audit_log(actor_account_id, season_id, action, entity_type, entity_id, after_json)
           VALUES (?, ?, 'royale.start', 'royale', ?, ?)""", (actor, season_id, str(game["id"]), encoded({"players": count})))
    return current(conn, actor, season_id, allow_write=True)


def cancel(conn, actor: int, season_id: int) -> dict:
    """Остановить игру без призов. Оплаченные воскрешения возвращаются."""
    authorize(conn, actor, season_id, manage=True, write=True)
    game = _active(conn, season_id)
    if game is None:
        raise CaseError("Нет игры, которую можно остановить.", 409)
    now = utcnow()
    for row in conn.execute(
        """SELECT account_id, -SUM(stars_delta) AS paid FROM v4_economy_operations
           WHERE season_id=? AND operation=? AND json_extract(details_json, '$.game') = ? GROUP BY account_id""",
        (season_id, REVIVE_OPERATION, int(game["id"]))).fetchall():
        if int(row["paid"]) > 0:
            _credit(conn, season_id, int(row["account_id"]), stars=int(row["paid"]), rep=0, operation=REFUND_OPERATION,
                    details={"game": int(game["id"])})
    state = json.loads(game["state_json"])
    state["cancelled"] = True
    state.pop("question", None)
    _save(conn, game["id"], status="over", round_no=game["round"], state=state, now=now, results=[], finished=True)
    conn.execute(
        """INSERT INTO v4_audit_log(actor_account_id, season_id, action, entity_type, entity_id, after_json)
           VALUES (?, ?, 'royale.cancel', 'royale', ?, '{}')""", (actor, season_id, str(game["id"])))
    return current(conn, actor, season_id, allow_write=True)
