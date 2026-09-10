"""Шифровальщики — правила партии.

По мотивам Codenames (название не используем; V4_GAMES.md §4.10). Две
команды, «синие» и «красные», поле 5×5 китайских слов. Капитаны видят, какие
слова чьи; вслух они дают подсказку — одно русское слово и число, — а в
приложение вводят только число. Отгадчики открывают карточки.

Свободного текста в игре нет вовсе: подсказка звучит голосом за столом, а не
пишется в приложении. Модерировать нечего.

Главное правило модуля то же, что у Шпиона: раскладка не покидает сервер.
`view` отдаёт цвет закрытой карточки только капитанам; у отгадчика его нет ни
в поле, ни в скрытом ключе.

Капитан всегда видит слово полностью — иероглифы, пиньинь и перевод, — даже в
режиме «только иероглифы». Подсказку он даёт по-русски, и понимать слова ему
нужно; а вот отгадчику, чтобы связать подсказку с карточкой, нужно знать, что
значит иероглиф. Китайский тренирует тот, кто отгадывает.
"""

from __future__ import annotations

import json
import random
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from . import rooms
from .rooms import GameError


GAME = "cipher"
CONTENT = Path(__file__).resolve().parent / "static" / "app" / "assets" / "games" / "cipher.json"

MIN_PLAYERS = 4
TEAMS = ("blue", "red")
BOARD_SIZE = 25
FIRST_TEAM_CARDS = 9
SECOND_TEAM_CARDS = 8
NEUTRAL_CARDS = 7
VIRUS_CARDS = 1
MAX_CLUE = 9
MODES = ("translated", "pinyin", "hanzi")
DEFAULT_SETTINGS = {"mode": "translated"}
WIN_POINTS = 1

_rng = random.SystemRandom()


@lru_cache(maxsize=1)
def content() -> dict:
    data = json.loads(CONTENT.read_text(encoding="utf-8"))
    words = data.get("words") or []
    seen: set[str] = set()
    for item in words:
        for key in ("zh", "pinyin", "ru"):
            if not str(item.get(key) or "").strip():
                raise RuntimeError(f"cipher.json: у слова нет поля {key}: {item!r}")
        if item["zh"] in seen:
            raise RuntimeError(f"cipher.json: повтор слова {item['zh']}")
        seen.add(item["zh"])
    # Слов нужно заметно больше одного поля, иначе второй вечер повторит первый.
    if len(words) < BOARD_SIZE * 4:
        raise RuntimeError("cipher.json: слишком мало слов")
    return data


def words_by_zh() -> dict[str, dict]:
    return {item["zh"]: item for item in content()["words"]}


def settings_from(body: dict | None) -> dict:
    mode = rooms.text_field(body, "mode", 16)
    if mode not in MODES:
        raise GameError("Неизвестный режим.")
    return {"mode": mode}


def in_round(state: dict) -> bool:
    return state.get("phase") in ("clue", "guess")


def joinable(status: str, state: dict) -> bool:
    return status == "lobby" or state.get("phase") == "over"


def _other(team: str) -> str:
    return "red" if team == "blue" else "blue"


def _members(state: dict, seated: set[int]) -> dict[str, list[int]]:
    teams = state.get("teams") or {}
    return {team: sorted(pid for pid in seated if teams.get(str(pid)) == team) for team in TEAMS}


def _normalise(state: dict, seated: set[int]) -> None:
    """Сверяет составы команд с тем, кто сейчас сидит за столом."""
    state["teams"] = {
        key: team for key, team in (state.get("teams") or {}).items()
        if int(key) in seated and team in TEAMS
    }
    captains = state.setdefault("captains", {})
    members = _members(state, seated)
    for team in TEAMS:
        if captains.get(team) not in members[team]:
            # Ушёл капитан посреди партии — его место занимает следующий из
            # команды: иначе команда не может сделать ход вовсе. До начала
            # игры капитана выбирают сами.
            captains[team] = members[team][0] if in_round(state) and members[team] else None


def _remaining(state: dict, team: str) -> int:
    return sum(1 for card in state.get("board", []) if card["key"] == team and not card["revealed"])


def _finish(state: dict, winner: str | None, reason: str, seated: set[int]) -> dict[int, int]:
    points = {pid: WIN_POINTS for pid in _members(state, seated)[winner]} if winner else {}
    state["phase"] = "over"
    state["result"] = {
        "winner": winner,
        "reason": reason,
        "points": {str(pid): amount for pid, amount in points.items()},
    }
    return points


def tick(state: dict, seated: set[int], now: datetime) -> dict[int, int]:
    del now  # Таймеров у Шифровальщиков нет: ход ждёт команду, а не часы.
    _normalise(state, seated)
    if in_round(state):
        members = _members(state, seated)
        if any(len(members[team]) < 2 for team in TEAMS):
            return _finish(state, None, "too_few", seated)
    return {}


# --- лобби -------------------------------------------------------------------


def _require_lobby(state: dict) -> None:
    if in_round(state):
        raise GameError("Составы меняются до начала партии.", 409)


def _start(state: dict, seated: set[int]) -> None:
    if len(seated) < MIN_PLAYERS:
        raise GameError(f"Нужно минимум {MIN_PLAYERS} игрока.", 409)
    teams = state["teams"]
    # Кто не выбрал команду — садится туда, где меньше людей.
    for pid in sorted(seated):
        if str(pid) not in teams:
            counts = {team: sum(1 for value in teams.values() if value == team) for team in TEAMS}
            teams[str(pid)] = min(TEAMS, key=lambda team: counts[team])
    members = _members(state, seated)
    if any(len(members[team]) < 2 for team in TEAMS):
        raise GameError("В каждой команде нужно минимум двое: капитан и отгадчик.", 409)
    for team in TEAMS:
        if state["captains"].get(team) not in members[team]:
            state["captains"][team] = members[team][0]

    first = _rng.choice(TEAMS)
    words = _rng.sample(content()["words"], BOARD_SIZE)
    keys = ([first] * FIRST_TEAM_CARDS + [_other(first)] * SECOND_TEAM_CARDS
            + ["neutral"] * NEUTRAL_CARDS + ["virus"] * VIRUS_CARDS)
    _rng.shuffle(keys)
    state.update({
        "round": int(state.get("round") or 0) + 1,
        "phase": "clue",
        "first": first,
        "turn": first,
        "board": [{"word": word["zh"], "key": key, "revealed": False} for word, key in zip(words, keys)],
        "clue": None,
        "guesses_left": 0,
        "guesses_made": 0,
        "log": [],
        "last": None,
        "result": None,
    })


# --- ход -------------------------------------------------------------------------


def _pass_turn(state: dict) -> None:
    state["turn"] = _other(state["turn"])
    state["phase"] = "clue"
    state["clue"] = None
    state["guesses_left"] = 0
    state["guesses_made"] = 0


def _operative_of_turn(state: dict, actor: int) -> str:
    if state.get("phase") != "guess":
        raise GameError("Сейчас не время отгадывать.", 409)
    team = state["turn"]
    if state["teams"].get(str(actor)) != team:
        raise GameError("Сейчас ходит другая команда.", 403)
    if state["captains"].get(team) == actor:
        raise GameError("Капитан не отгадывает — он знает ответы.", 403)
    return team


def _clue(state: dict, actor: int, count: int) -> None:
    if state.get("phase") != "clue":
        raise GameError("Сейчас не время подсказки.", 409)
    team = state["turn"]
    if state["captains"].get(team) != actor:
        raise GameError("Подсказку даёт капитан команды, которая ходит.", 403)
    state["phase"] = "guess"
    state["clue"] = count
    # Классическое правило: на одну попытку больше числа — чтобы добрать
    # слово, недоотгаданное в прошлый ход.
    state["guesses_left"] = count + 1
    state["guesses_made"] = 0
    state["log"].append({"team": team, "count": count})


def _guess(state: dict, actor: int, index: int, seated: set[int]) -> dict[int, int]:
    team = _operative_of_turn(state, actor)
    card = state["board"][index]
    if card["revealed"]:
        raise GameError("Эта карточка уже открыта.", 409)
    card["revealed"] = True
    card["by"] = team
    state["guesses_made"] += 1
    state["guesses_left"] -= 1
    state["last"] = {"index": index, "team": team, "key": card["key"]}
    if card["key"] == "virus":
        return _finish(state, _other(team), "virus", seated)
    if card["key"] in TEAMS and _remaining(state, card["key"]) == 0:
        return _finish(state, card["key"], "all_found", seated)
    if card["key"] != team or state["guesses_left"] <= 0:
        _pass_turn(state)
    return {}


def act(action: str, state: dict, actor: int, body: dict | None, *,
        seated: set[int], host: int, now: datetime, settings: dict) -> tuple[str | None, dict[int, int]]:
    del now, settings
    _normalise(state, seated)
    if action == "team":
        _require_lobby(state)
        team = rooms.text_field(body, "team", 8)
        if team not in TEAMS:
            raise GameError("Такой команды нет.")
        previous = state["teams"].get(str(actor))
        state["teams"][str(actor)] = team
        if previous and previous != team and state["captains"].get(previous) == actor:
            state["captains"][previous] = None
        return None, {}
    if action == "captain":
        _require_lobby(state)
        team = state["teams"].get(str(actor))
        if team is None:
            raise GameError("Сначала выберите команду.", 409)
        state["captains"][team] = actor
        return None, {}
    if action == "shuffle":
        _require_lobby(state)
        if actor != host:
            raise GameError("Перемешивает ведущий.", 403)
        order = sorted(seated)
        _rng.shuffle(order)
        state["teams"] = {str(pid): TEAMS[i % 2] for i, pid in enumerate(order)}
        state["captains"] = {team: None for team in TEAMS}
        for pid in order:
            team = state["teams"][str(pid)]
            if state["captains"][team] is None:
                state["captains"][team] = pid
        return None, {}
    if action == "start":
        _require_lobby(state)
        if actor != host:
            raise GameError("Партию запускает ведущий.", 403)
        _start(state, seated)
        return "playing", {}
    if action == "clue":
        _clue(state, actor, rooms.int_field(body, "count", 1, MAX_CLUE))
        return None, {}
    if action == "guess":
        return None, _guess(state, actor, rooms.int_field(body, "index", 0, BOARD_SIZE - 1), seated)
    if action == "end-turn":
        _operative_of_turn(state, actor)
        if state["guesses_made"] < 1:
            raise GameError("Сначала хотя бы одна попытка.", 409)
        _pass_turn(state)
        return None, {}
    raise GameError("Такого действия в игре нет.", 404)


# --- что видит игрок ---------------------------------------------------------------


def _word(item: dict, mode: str, full: bool) -> dict:
    if full or mode == "translated":
        return {"zh": item["zh"], "pinyin": item["pinyin"], "ru": item["ru"]}
    if mode == "pinyin":
        return {"zh": item["zh"], "pinyin": item["pinyin"]}
    return {"zh": item["zh"]}


def view(state: dict, viewer: int, settings: dict, seated: set[int], now: datetime) -> dict:
    del now
    # Вид не должен менять сохранённую партию: сверяем составы на копии.
    state = json.loads(json.dumps(state))
    _normalise(state, seated)
    mode = settings.get("mode", "translated")
    members = _members(state, seated)
    captains = state.get("captains") or {}
    your_team = state["teams"].get(str(viewer))
    is_captain = your_team is not None and captains.get(your_team) == viewer
    phase = state.get("phase")

    body: dict = {
        "phase": phase,
        "round": state.get("round"),
        "teams": {team: {"members": members[team], "captain": captains.get(team)} for team in TEAMS},
        "unassigned": sorted(pid for pid in seated if str(pid) not in state["teams"]),
        "you": {"team": your_team, "captain": is_captain},
    }
    if state.get("board"):
        over = phase == "over"
        # Раскладку видит капитан во время партии и все — после её конца.
        sees_key = over or (is_captain and in_round(state))
        words = words_by_zh()
        cards = []
        for index, card in enumerate(state["board"]):
            item = {
                "index": index,
                "word": _word(words[card["word"]], mode, full=sees_key),
                "revealed": bool(card["revealed"]),
            }
            if card["revealed"] or sees_key:
                item["key"] = card["key"]
            cards.append(item)
        body["board"] = cards
        body["remaining"] = {team: _remaining(state, team) for team in TEAMS}
        body["turn"] = {
            "team": state["turn"],
            "first": state["first"],
            "clue": state["clue"],
            "guesses_left": state["guesses_left"],
            "guesses_made": state["guesses_made"],
        }
        body["log"] = state["log"][-8:]
        body["last"] = state.get("last")
    if phase == "over" and state.get("result"):
        result = state["result"]
        body["result"] = {
            "winner": result["winner"],
            "reason": result["reason"],
            "points": {int(k): int(v) for k, v in result["points"].items()},
        }
    return body
