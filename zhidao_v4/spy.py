"""Шпион Протокола — правила партии.

По мотивам Spyfall (V4_GAMES.md §4.9). Всем за столом приходит одно место и
роль в нём, одному — «ты шпион». Дальше играют голосом, а телефон держит
тайну, таймер и голосование.

Главное правило модуля: тайна не покидает сервер. Функция `view` собирает
для каждого игрока только его собственный экран; у шпиона в ответе нет места
вовсе — ни в поле, ни в скрытом ключе. Иначе его вытащили бы из инструментов
разработчика за минуту, и игра кончилась бы в первый же вечер.

Состояние — простой словарь, который целиком лежит в `state_json`. Время не
идёт само: переходы (кончился таймер, истекло голосование, шпион вышел)
вычисляет `tick` в момент любого запроса. Фонового цикла нет и не нужно —
никто не увидит перехода, пока не спросит.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

from . import rooms
from .rooms import GameError


GAME = "spy"
CONTENT = Path(__file__).resolve().parent / "static" / "app" / "assets" / "games" / "spy.json"

MIN_PLAYERS = 4
MIN_TO_CONTINUE = 3
VOTE_SECONDS = 60
FINAL_VOTE_SECONDS = 90
MODES = ("translated", "hanzi")
MINUTES = (5, 12)
DEFAULT_SETTINGS = {"mode": "translated", "minutes": 8}

# Очки из оригинальных правил. Живут только внутри вечера: ни в ★, ни в REP
# не идут, иначе компания друзей нафармит их за час.
SPY_GUESSED = 4
SPY_FRAMED = 4
SPY_SURVIVED = 2
AGENT_WIN = 1
ACCUSER_WIN = 2

_rng = random.SystemRandom()


@lru_cache(maxsize=1)
def content() -> dict:
    data = json.loads(CONTENT.read_text(encoding="utf-8"))
    locations = data.get("locations") or []
    seen: set[str] = set()
    for item in locations:
        for key in ("id", "zh", "pinyin", "ru"):
            if not str(item.get(key) or "").strip():
                raise RuntimeError(f"spy.json: у места нет поля {key}: {item!r}")
        if item["id"] in seen:
            raise RuntimeError(f"spy.json: повтор места {item['id']}")
        seen.add(item["id"])
        roles = item.get("roles") or []
        # Ролей хватает на всех, кроме шпиона, и они не повторяются — два
        # «повара» за одним столом сразу выдали бы друг друга.
        if len(set(roles)) != len(roles) or len(roles) < rooms.MAX_PLAYERS - 1:
            raise RuntimeError(f"spy.json: у места {item['id']} мало разных ролей")
    if len(locations) < 10:
        raise RuntimeError("spy.json: слишком мало мест для игры")
    return data


def locations_by_id() -> dict[str, dict]:
    return {item["id"]: item for item in content()["locations"]}


def clean_settings(mode: str, minutes: int) -> dict:
    if mode not in MODES:
        raise GameError("Неизвестный режим.")
    if not MINUTES[0] <= int(minutes) <= MINUTES[1]:
        raise GameError(f"Раунд длится от {MINUTES[0]} до {MINUTES[1]} минут.")
    return {"mode": mode, "minutes": int(minutes)}


def settings_from(body: dict | None) -> dict:
    return clean_settings(rooms.text_field(body, "mode", 16), rooms.int_field(body, "minutes"))


def act(action: str, state: dict, actor: int, body: dict | None, *,
        seated: set[int], host: int, now: datetime, settings: dict) -> tuple[str | None, dict[int, int]]:
    """Единая точка входа для маршрутов: действие → (новый статус комнаты, очки)."""
    if action == "start":
        if actor != host:
            raise GameError("Раунд запускает ведущий.", 403)
        # Порядок не важен: шпиона и роли всё равно выбирает жребий.
        fresh = start_round(state, sorted(seated), settings, now)
        state.clear()
        state.update(fresh)
        return "playing", {}
    if action == "accuse":
        accuse(state, actor, rooms.int_field(body, "target_account_id", 1), seated, now)
        return None, {}
    if action == "vote":
        vote(state, actor, rooms.bool_field(body, "yes"), seated)
        # Голос мог оказаться решающим — доводим сразу, а не при следующем опросе.
        return None, tick(state, seated, now)
    if action == "guess":
        return None, guess(state, actor, rooms.text_field(body, "location_id"), seated)
    if action == "final-vote":
        final_vote(state, actor, rooms.int_field(body, "target_account_id", 1), seated)
        return None, tick(state, seated, now)
    raise GameError("Такого действия в игре нет.", 404)


def joinable(status: str, state: dict) -> bool:
    """Подсесть можно в лобби и между раундами, но не посреди раунда."""
    return status == "lobby" or state.get("phase") == "reveal"


def in_round(state: dict) -> bool:
    return state.get("phase") in ("discussion", "vote", "final_vote")


# --- переходы ---------------------------------------------------------------


def start_round(state: dict, player_ids: list[int], settings: dict, now: datetime) -> dict:
    if in_round(state):
        raise GameError("Раунд уже идёт.", 409)
    if len(player_ids) < MIN_PLAYERS:
        raise GameError(f"Нужно минимум {MIN_PLAYERS} игрока.", 409)
    if len(player_ids) > rooms.MAX_PLAYERS:
        raise GameError(f"Играют не больше {rooms.MAX_PLAYERS} человек.", 409)

    places = content()["locations"]
    # Прошлое место не выпадает два раза подряд: иначе второй раунд
    # разгадывается словом «опять».
    choices = [p for p in places if p["id"] != state.get("location")] or places
    place = _rng.choice(choices)
    spy = _rng.choice(player_ids)
    agents = [pid for pid in player_ids if pid != spy]
    roles = _rng.sample(place["roles"], len(agents))
    return {
        "round": int(state.get("round") or 0) + 1,
        "phase": "discussion",
        "participants": list(player_ids),
        "spy": spy,
        "location": place["id"],
        "roles": {str(pid): role for pid, role in zip(agents, roles)},
        "ends_at": rooms.iso(now + timedelta(minutes=int(settings["minutes"]))),
        "remaining": None,
        "accusers": [],
        "vote": None,
        "final_votes": {},
        "final_deadline": None,
        "result": None,
    }


def _finish(state: dict, winner: str, reason: str, points: dict[int, int]) -> dict[int, int]:
    state["phase"] = "reveal"
    state["vote"] = None
    state["result"] = {
        "winner": winner,
        "reason": reason,
        "points": {str(pid): amount for pid, amount in points.items() if amount},
    }
    return points


def _agents(state: dict, seated: set[int]) -> list[int]:
    return [pid for pid in state["participants"] if pid != state["spy"] and pid in seated]


def _agents_win(state: dict, seated: set[int], reason: str, accuser: int | None = None) -> dict[int, int]:
    points = {pid: AGENT_WIN for pid in _agents(state, seated)}
    if accuser is not None and accuser in points:
        points[accuser] = ACCUSER_WIN
    return _finish(state, "agents", reason, points)


def _resume_discussion(state: dict, now: datetime) -> None:
    remaining = float(state.get("remaining") or 0)
    state["phase"] = "discussion"
    state["ends_at"] = rooms.iso(now + timedelta(seconds=remaining))
    state["remaining"] = None
    state["vote"] = None


def _convict(state: dict, vote_state: dict, in_room: set[int]) -> dict[int, int]:
    if int(vote_state["target"]) == state["spy"]:
        return _agents_win(state, in_room, "accused", accuser=int(vote_state["accuser"]))
    return _finish(state, "spy", "framed", {state["spy"]: SPY_FRAMED})


def tick(state: dict, seated: set[int], now: datetime) -> dict[int, int]:
    """Доводит партию до текущего момента. Меняет `state`, возвращает очки.

    Присутствие («кто сейчас смотрит на экран») сюда намеренно не входит.
    Сначала голосование считало только тех, кто на связи, — и на первой же
    живой проверке обвинитель осудил шпиона в одиночку, пока остальные
    свернули приложение. Поэтому решения принимает весь стол; не успевший
    лишь затягивает голосование до таймера, но не решает за других.
    """
    if not in_round(state):
        return {}
    in_room = set(state["participants"]) & seated
    if state["spy"] not in seated:
        return _finish(state, "void", "spy_left", {})
    if len(in_room) < MIN_TO_CONTINUE:
        return _finish(state, "void", "too_few", {})

    if state["phase"] == "discussion" and now >= rooms.parse(state["ends_at"]):
        state["phase"] = "final_vote"
        state["final_votes"] = {}
        state["final_deadline"] = rooms.iso(now + timedelta(seconds=FINAL_VOTE_SECONDS))

    if state["phase"] == "vote":
        vote = state["vote"]
        target = int(vote["target"])
        votes = {int(k): bool(v) for k, v in vote["votes"].items()}
        voters = in_room - {target}
        yes = sum(1 for pid in voters if votes.get(pid) is True)
        if target not in in_room or any(votes.get(pid) is False for pid in voters):
            _resume_discussion(state, now)
        elif yes == len(voters):
            return _convict(state, vote, in_room)
        elif now >= rooms.parse(vote["deadline"]):
            # Кто-то не успел проголосовать. Ждать его вечно нельзя, решать за
            # него одному обвинителю — тоже: осуждает только явное большинство
            # стола, не меньше двух голосов и ни одного «нет».
            if yes >= 2 and yes * 2 > len(voters):
                return _convict(state, vote, in_room)
            _resume_discussion(state, now)

    if state["phase"] == "final_vote":
        votes = {int(k): int(v) for k, v in state["final_votes"].items() if int(k) in in_room}
        if len(votes) == len(in_room) or now >= rooms.parse(state["final_deadline"]):
            against_spy = sum(1 for target in votes.values() if target == state["spy"])
            # Большинство всего стола, а не только проголосовавших: иначе при
            # свёрнутых приложениях раунд решал бы один голос.
            if against_spy * 2 > len(in_room):
                return _agents_win(state, in_room, "final_vote")
            return _finish(state, "spy", "survived", {state["spy"]: SPY_SURVIVED})
    return {}


# --- действия игроков -------------------------------------------------------


def _seated_participant(state: dict, actor: int, seated: set[int]) -> None:
    if actor not in state.get("participants", []) or actor not in seated:
        raise GameError("Вы не участвуете в этом раунде.", 403)


def accuse(state: dict, actor: int, target: int, seated: set[int], now: datetime) -> None:
    if state.get("phase") != "discussion":
        raise GameError("Обвинить можно только во время обсуждения.", 409)
    _seated_participant(state, actor, seated)
    if target == actor:
        raise GameError("Себя обвинить нельзя.")
    if target not in state["participants"] or target not in seated:
        raise GameError("Этого игрока нет за столом.")
    if actor in state["accusers"]:
        raise GameError("Своё обвинение в этом раунде вы уже использовали.", 409)
    state["accusers"].append(actor)
    state["remaining"] = max(0.0, (rooms.parse(state["ends_at"]) - now).total_seconds())
    state["phase"] = "vote"
    state["vote"] = {
        "accuser": actor,
        "target": target,
        "votes": {str(actor): True},
        "deadline": rooms.iso(now + timedelta(seconds=VOTE_SECONDS)),
    }


def vote(state: dict, actor: int, yes: bool, seated: set[int]) -> None:
    if state.get("phase") != "vote":
        raise GameError("Сейчас нет голосования.", 409)
    _seated_participant(state, actor, seated)
    if actor == int(state["vote"]["target"]):
        raise GameError("Обвиняемый не голосует.", 403)
    state["vote"]["votes"][str(actor)] = bool(yes)


def guess(state: dict, actor: int, location_id: str, seated: set[int]) -> dict[int, int]:
    if state.get("phase") != "discussion":
        raise GameError("Назвать место можно только во время обсуждения.", 409)
    _seated_participant(state, actor, seated)
    if actor != state["spy"]:
        raise GameError("Назвать место может только шпион.", 403)
    if location_id not in locations_by_id():
        raise GameError("Такого места нет в списке.")
    if location_id == state["location"]:
        return _finish(state, "spy", "guessed", {actor: SPY_GUESSED})
    state["guessed"] = location_id
    return _agents_win(state, set(state["participants"]) & seated, "wrong_guess")


def final_vote(state: dict, actor: int, target: int, seated: set[int]) -> None:
    if state.get("phase") != "final_vote":
        raise GameError("Финальное голосование ещё не началось.", 409)
    _seated_participant(state, actor, seated)
    if target == actor:
        raise GameError("За себя голосовать нельзя.")
    if target not in state["participants"] or target not in seated:
        raise GameError("Этого игрока нет за столом.")
    state["final_votes"][str(actor)] = target


# --- что видит игрок ---------------------------------------------------------


def _place(item: dict, mode: str, *, full: bool = False) -> dict:
    if full or mode == "translated":
        return {"id": item["id"], "zh": item["zh"], "pinyin": item["pinyin"], "ru": item["ru"]}
    # «Только иероглифы»: мирный житель, не узнавший 夜市, сам почти шпион.
    return {"id": item["id"], "zh": item["zh"]}


def _seconds_left(until: str | None, now: datetime) -> int | None:
    if not until:
        return None
    return max(0, int(round((rooms.parse(until) - now).total_seconds())))


def view(state: dict, viewer: int, settings: dict, seated: set[int], now: datetime) -> dict:
    mode = settings.get("mode", "translated")
    places = locations_by_id()
    listing = [_place(item, mode) for item in content()["locations"]]
    if not state.get("phase"):
        return {"locations": listing, "round": None}

    phase = state["phase"]
    participants = state["participants"]
    in_room = set(participants) & seated
    playing = viewer in participants
    body: dict = {
        "number": state["round"],
        "phase": phase,
        "participants": participants,
        "you": None,
    }

    if playing:
        if viewer == state["spy"]:
            body["you"] = {"spy": True}
        else:
            body["you"] = {
                "spy": False,
                "location": _place(places[state["location"]], mode),
                "role": state["roles"].get(str(viewer)),
            }
        body["can_accuse"] = phase == "discussion" and viewer not in state["accusers"]

    if phase == "discussion":
        body["seconds_left"] = _seconds_left(state["ends_at"], now)
    elif phase == "vote":
        vote_state = state["vote"]
        target = int(vote_state["target"])
        votes = {int(k): bool(v) for k, v in vote_state["votes"].items()}
        voters = in_room - {target}
        body["seconds_left"] = int(round(float(state.get("remaining") or 0)))
        body["vote"] = {
            "accuser": int(vote_state["accuser"]),
            "target": target,
            "yes": sum(1 for pid in voters if votes.get(pid) is True),
            "required": len(voters),
            "your_vote": votes.get(viewer),
            "can_vote": playing and viewer != target,
            "seconds_left": _seconds_left(vote_state["deadline"], now),
        }
    elif phase == "final_vote":
        votes = {int(k): int(v) for k, v in state["final_votes"].items()}
        body["final_vote"] = {
            # Кто за кого — не показываем до конца: иначе последний голосующий
            # просто присоединяется к большинству.
            "voted": sum(1 for pid in votes if pid in in_room),
            "expected": len(in_room),
            "your_vote": votes.get(viewer),
            "seconds_left": _seconds_left(state["final_deadline"], now),
        }
    elif phase == "reveal":
        result = state["result"]
        body["result"] = {
            "winner": result["winner"],
            "reason": result["reason"],
            "points": {int(k): int(v) for k, v in result["points"].items()},
            "spy": state["spy"],
            # На раскрытии перевод показываем всегда: это и есть момент,
            # когда слово запоминается.
            "location": _place(places[state["location"]], mode, full=True),
            "guessed": _place(places[state["guessed"]], mode, full=True) if state.get("guessed") else None,
            "roles": {int(k): v for k, v in state["roles"].items()},
        }
    return {"locations": listing, "round": body}
