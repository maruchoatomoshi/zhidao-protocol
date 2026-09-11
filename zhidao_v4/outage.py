"""Сбой системы — правила партии.

По мотивам Keep Talking and Nobody Explodes (V4_GAMES.md §4.11). Один игрок —
техник: он видит сломанные модули Протокола, но не знает, как их чинить.
Остальные — эксперты: у них инструкция, но модулей они не видят. Починить
систему можно только разговором, а говорить приходится о китайских знаках:
на модулях написано 红, 左, 四十五, а инструкция объясняет, что с ними делать.

Главное правило модуля — у каждой стороны только своя половина:

- техник не получает инструкцию и ответов ни в каком виде;
- эксперты не получают того, что нарисовано на модулях;
- ответы (какой провод, в каком порядке) не уходят никому до конца раунда.

Поэтому инструкция живёт здесь, в коде сервера, а не в статических файлах
приложения: оттуда техник прочитал бы её сам, открыв адрес в браузере.

Правила модулей придуманы для ZHIDAO, а не переписаны из оригинальной игры.
Тексты инструкции стоят рядом с функциями, которые проверяют ответ: правило и
его описание меняются только вместе (tests/test_v4_outage.py проверяет, что
решатель проводов ведёт себя так, как написано).
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from . import rooms
from .rooms import GameError


GAME = "outage"
MIN_PLAYERS = 2
MAX_STRIKES = 3
SUCCESS_POINTS = 1
DIFFICULTY = {
    "easy": {"modules": 2, "seconds": 300},
    "normal": {"modules": 3, "seconds": 300},
    "hard": {"modules": 4, "seconds": 240},
}
DEFAULT_SETTINGS = {"difficulty": "normal"}
# Китайский текст проверяет человек, знающий язык, до выхода в сезон.
CONTENT_REVIEWED = False

_rng = random.SystemRandom()

# --- словарь -----------------------------------------------------------------

COLORS = {
    "red": ("红", "hóng", "красный"),
    "blue": ("蓝", "lán", "синий"),
    "yellow": ("黄", "huáng", "жёлтый"),
    "white": ("白", "bái", "белый"),
    "black": ("黑", "hēi", "чёрный"),
    "green": ("绿", "lǜ", "зелёный"),
}

HANZI = {
    "日": ("rì", "солнце, день"), "月": ("yuè", "луна, месяц"), "山": ("shān", "гора"),
    "田": ("tián", "поле"), "口": ("kǒu", "рот"), "目": ("mù", "глаз"),
    "水": ("shuǐ", "вода"), "火": ("huǒ", "огонь"), "木": ("mù", "дерево"),
    "人": ("rén", "человек"), "天": ("tiān", "небо"), "大": ("dà", "большой"),
    "手": ("shǒu", "рука"), "心": ("xīn", "сердце"), "土": ("tǔ", "земля"),
    "金": ("jīn", "золото, металл"), "耳": ("ěr", "ухо"), "力": ("lì", "сила"),
    "中": ("zhōng", "середина"), "小": ("xiǎo", "маленький"),
}

KEYPAD_COLUMNS = [
    ["日", "月", "山", "田", "口", "目"],
    ["水", "火", "山", "木", "人", "口"],
    ["天", "大", "人", "手", "心", "月"],
    ["土", "金", "木", "目", "耳", "力"],
    ["中", "小", "大", "田", "火", "手"],
]

DIRECTIONS = {
    "上": ("shàng", "up"), "下": ("xià", "down"), "左": ("zuǒ", "left"), "右": ("yòu", "right"),
    "北": ("běi", "up"), "南": ("nán", "down"), "西": ("xī", "left"), "东": ("dōng", "right"),
}
DIRECTION_RU = {"up": "вверх", "down": "вниз", "left": "влево", "right": "вправо"}

DIGITS = {
    1: ("一", "yī"), 2: ("二", "èr"), 3: ("三", "sān"), 4: ("四", "sì"), 5: ("五", "wǔ"),
    6: ("六", "liù"), 7: ("七", "qī"), 8: ("八", "bā"), 9: ("九", "jiǔ"), 10: ("十", "shí"),
}

# --- провода -------------------------------------------------------------------

WIRE_RULES = {
    3: [
        "Есть хотя бы один 绿 — режьте первый 绿.",
        "Иначе, если первый и последний провод одного цвета, — режьте второй.",
        "Иначе режьте последний.",
    ],
    4: [
        "Два и больше 红 — режьте второй 红.",
        "Иначе, если нет ни одного 蓝, — режьте первый.",
        "Иначе, если последний провод 白, — режьте третий.",
        "Иначе режьте последний 蓝.",
    ],
    5: [
        "Ровно один 黑 — режьте провод сразу после него (если 黑 последний — первый).",
        "Иначе, если 黄 больше, чем 红, — режьте последний 黄.",
        "Иначе, если все пять проводов разного цвета, — режьте четвёртый.",
        "Иначе режьте второй.",
    ],
    6: [
        "Нет ни одного 白 — режьте пятый.",
        "Иначе, если первый провод 红 или 蓝, — режьте первый 白.",
        "Иначе, если 绿 два и больше, — режьте последний 绿.",
        "Иначе режьте третий.",
    ],
}


def _positions(wires: list[str], color: str) -> list[int]:
    return [i for i, wire in enumerate(wires) if wire == color]


def solve_wires(wires: list[str]) -> int:
    """Номер провода (с нуля), который нужно перерезать. Ровно по WIRE_RULES."""
    count = len(wires)
    if count == 3:
        if "green" in wires:
            return _positions(wires, "green")[0]
        if wires[0] == wires[-1]:
            return 1
        return 2
    if count == 4:
        if len(_positions(wires, "red")) >= 2:
            return _positions(wires, "red")[1]
        if "blue" not in wires:
            return 0
        if wires[-1] == "white":
            return 2
        return _positions(wires, "blue")[-1]
    if count == 5:
        blacks = _positions(wires, "black")
        if len(blacks) == 1:
            return 0 if blacks[0] == 4 else blacks[0] + 1
        if len(_positions(wires, "yellow")) > len(_positions(wires, "red")):
            return _positions(wires, "yellow")[-1]
        if len(set(wires)) == 5:
            return 3
        return 1
    if count == 6:
        if "white" not in wires:
            return 4
        if wires[0] in ("red", "blue"):
            return _positions(wires, "white")[0]
        if len(_positions(wires, "green")) >= 2:
            return _positions(wires, "green")[-1]
        return 2
    raise ValueError("Проводов бывает от 3 до 6")


# --- генерация модулей -------------------------------------------------------------


def _number_zh(value: int) -> str:
    tens, ones = divmod(value, 10)
    head = "十" if tens == 1 else f"{DIGITS[tens][0]}十"
    return head + (DIGITS[ones][0] if ones else "")


def _make_wires() -> dict:
    wires = [_rng.choice(list(COLORS)) for _ in range(_rng.randint(3, 6))]
    return {"type": "wires", "wires": wires, "cut": [], "answer": solve_wires(wires), "solved": False}


def _make_keypad() -> dict:
    while True:
        column = _rng.choice(KEYPAD_COLUMNS)
        chosen = _rng.sample(column, 4)
        # Четыре знака должны вместе встречаться ровно в одном столбце — иначе
        # у задачи было бы два ответа, и эксперт не виноват в ошибке.
        if sum(1 for other in KEYPAD_COLUMNS if set(chosen) <= set(other)) == 1:
            break
    shown = chosen[:]
    _rng.shuffle(shown)
    return {"type": "keypad", "shown": shown, "order": sorted(chosen, key=column.index),
            "pressed": [], "solved": False}


def _make_compass() -> dict:
    return {"type": "compass", "sequence": [_rng.choice(list(DIRECTIONS)) for _ in range(4)],
            "progress": 0, "solved": False}


def _make_number() -> dict:
    value = _rng.randint(11, 99)
    return {"type": "number", "zh": _number_zh(value), "value": value, "solved": False}


MAKERS = {"wires": _make_wires, "keypad": _make_keypad, "compass": _make_compass, "number": _make_number}


# --- инструкция ----------------------------------------------------------------------


def manual(types) -> dict:
    """Инструкция экспертов — только для модулей этого раунда."""
    sections = {}
    if "wires" in types:
        sections["wires"] = {
            "intro": "Провода считаются сверху вниз. Правила зависят от числа проводов; выполняйте первое подходящее.",
            "colors": [{"zh": zh, "pinyin": py, "ru": ru} for zh, py, ru in COLORS.values()],
            "rules": {str(n): rules for n, rules in WIRE_RULES.items()},
        }
    if "keypad" in types:
        sections["keypad"] = {
            "intro": "Найдите столбец, в котором есть все четыре знака с модуля. Нажимать их нужно в том порядке, "
                     "в каком они стоят в столбце сверху вниз. Неверное нажатие — ошибка, верные остаются нажатыми.",
            "columns": [[{"zh": zh, "pinyin": HANZI[zh][0], "ru": HANZI[zh][1]} for zh in column]
                        for column in KEYPAD_COLUMNS],
        }
    if "compass" in types:
        sections["compass"] = {
            "intro": "На модуле четыре знака. Нажимайте стрелки по порядку слева направо. Ошибка сбрасывает ввод.",
            "table": [{"zh": zh, "pinyin": py, "direction": direction, "ru": DIRECTION_RU[direction]}
                      for zh, (py, direction) in DIRECTIONS.items()],
        }
    if "number" in types:
        sections["number"] = {
            "intro": "На модуле число от 11 до 99. Десятки пишутся перед 十, единицы — после: "
                     "十三 = 13, 二十 = 20, 四十五 = 45. Техник вводит число цифрами.",
            "digits": [{"value": value, "zh": zh, "pinyin": py} for value, (zh, py) in DIGITS.items()],
        }
    return sections


# --- ход партии -------------------------------------------------------------------------


def settings_from(body: dict | None) -> dict:
    difficulty = rooms.text_field(body, "difficulty", 16)
    if difficulty not in DIFFICULTY:
        raise GameError("Неизвестная сложность.")
    return {"difficulty": difficulty}


def content() -> dict:
    # У Сбоя нет файла с данными: словарь и инструкция — в этом модуле.
    # Проверяем, что столбцы замка не ссылаются на знаки без описания.
    missing = {zh for column in KEYPAD_COLUMNS for zh in column} - set(HANZI)
    if missing:
        raise RuntimeError(f"outage: нет описания знаков {sorted(missing)}")
    return {"reviewed": CONTENT_REVIEWED}


def in_round(state: dict) -> bool:
    return state.get("phase") == "defuse"


def joinable(status: str, state: dict) -> bool:
    return not in_round(state)


def _finish(state: dict, success: bool | None, reason: str, seated: set[int]) -> dict[int, int]:
    state["phase"] = "over"
    points = {pid: SUCCESS_POINTS for pid in state["participants"] if pid in seated} if success else {}
    state["result"] = {"success": success, "reason": reason,
                       "points": {str(pid): amount for pid, amount in points.items()}}
    return points


def tick(state: dict, seated: set[int], now: datetime) -> dict[int, int]:
    if not in_round(state):
        return {}
    if state["technician"] not in seated:
        return _finish(state, None, "technician_left", seated)
    if len(set(state["participants"]) & seated) < MIN_PLAYERS:
        return _finish(state, None, "too_few", seated)
    if now >= rooms.parse(state["ends_at"]):
        return _finish(state, False, "time", seated)
    return {}


def _start(state: dict, seated: set[int], settings: dict, now: datetime) -> None:
    if len(seated) < MIN_PLAYERS:
        raise GameError(f"Нужно минимум {MIN_PLAYERS} игрока.", 409)
    order = sorted(seated)
    technician = state.get("technician_choice")
    if technician not in seated:
        # Никого не назначили — техником становится следующий за прошлым:
        # за вечер у пульта посидит каждый.
        last = state.get("technician")
        later = [pid for pid in order if last is not None and pid > last]
        technician = later[0] if later else order[0]
    config = DIFFICULTY[settings.get("difficulty", "normal")]
    # Типы в раунде не повторяются: четыре модуля — четыре разные задачи, а
    # не две одинаковые «Навигации» (так было на первой живой проверке).
    types = _rng.sample(list(MAKERS), config["modules"])
    state.update({
        "round": int(state.get("round") or 0) + 1,
        "phase": "defuse",
        "technician": technician,
        "technician_choice": None,
        "participants": order,
        "modules": [MAKERS[kind]() for kind in types],
        "strikes": 0,
        "ends_at": rooms.iso(now + timedelta(seconds=config["seconds"])),
        "result": None,
    })


def _module(state: dict, actor: int, body: dict | None, kind: str) -> tuple[int, dict]:
    if not in_round(state):
        raise GameError("Сейчас нечего чинить.", 409)
    if actor != state["technician"]:
        raise GameError("Модули трогает только техник. Эксперты помогают голосом.", 403)
    index = rooms.int_field(body, "module", 0, len(state["modules"]) - 1)
    module = state["modules"][index]
    if module["type"] != kind:
        raise GameError("Это действие для другого модуля.")
    if module["solved"]:
        raise GameError("Этот модуль уже исправлен.", 409)
    return index, module


def _after_move(state: dict, correct: bool, seated: set[int]) -> dict[int, int]:
    if not correct:
        state["strikes"] += 1
        if state["strikes"] >= MAX_STRIKES:
            return _finish(state, False, "strikes", seated)
    if all(module["solved"] for module in state["modules"]):
        return _finish(state, True, "defused", seated)
    return {}


def act(action: str, state: dict, actor: int, body: dict | None, *,
        seated: set[int], host: int, now: datetime, settings: dict) -> tuple[str | None, dict[int, int]]:
    if action == "technician":
        if in_round(state):
            raise GameError("Техника назначают до начала раунда.", 409)
        if actor != host:
            raise GameError("Техника назначает ведущий.", 403)
        chosen = rooms.int_field(body, "account_id", 1)
        if chosen not in seated:
            raise GameError("Этого игрока нет за столом.")
        state["technician_choice"] = chosen
        return None, {}
    if action == "start":
        if in_round(state):
            raise GameError("Раунд уже идёт.", 409)
        if actor != host:
            raise GameError("Раунд запускает ведущий.", 403)
        _start(state, seated, settings, now)
        return "playing", {}
    if action == "cut":
        _, module = _module(state, actor, body, "wires")
        wire = rooms.int_field(body, "wire", 0, len(module["wires"]) - 1)
        if wire in module["cut"]:
            raise GameError("Этот провод уже перерезан.", 409)
        module["cut"].append(wire)
        correct = wire == module["answer"]
        module["solved"] = correct
        return None, _after_move(state, correct, seated)
    if action == "press":
        _, module = _module(state, actor, body, "keypad")
        symbol = module["shown"][rooms.int_field(body, "symbol", 0, 3)]
        if symbol in module["pressed"]:
            raise GameError("Этот знак уже нажат.", 409)
        correct = symbol == module["order"][len(module["pressed"])]
        if correct:
            module["pressed"].append(symbol)
            module["solved"] = len(module["pressed"]) == 4
        return None, _after_move(state, correct, seated)
    if action == "direction":
        _, module = _module(state, actor, body, "compass")
        direction = rooms.text_field(body, "direction", 8)
        if direction not in DIRECTION_RU:
            raise GameError("Такого направления нет.")
        correct = direction == DIRECTIONS[module["sequence"][module["progress"]]][1]
        if correct:
            module["progress"] += 1
            module["solved"] = module["progress"] == len(module["sequence"])
        else:
            module["progress"] = 0
        return None, _after_move(state, correct, seated)
    if action == "number":
        _, module = _module(state, actor, body, "number")
        correct = rooms.int_field(body, "value", 0, 999) == module["value"]
        module["solved"] = correct
        return None, _after_move(state, correct, seated)
    raise GameError("Такого действия в игре нет.", 404)


# --- что видит игрок -------------------------------------------------------------------


def _surface(module: dict, reveal: bool) -> dict:
    """То, что нарисовано на модуле. С reveal — ещё и ответ (после конца раунда)."""
    kind = module["type"]
    view: dict = {"type": kind, "solved": module["solved"]}
    if kind == "wires":
        view["wires"] = [{"zh": COLORS[color][0], "cut": i in module["cut"]} for i, color in enumerate(module["wires"])]
        if reveal:
            view["answer"] = module["answer"]
    elif kind == "keypad":
        view["symbols"] = [{"zh": zh, "pressed": zh in module["pressed"]} for zh in module["shown"]]
        if reveal:
            view["answer"] = module["order"]
    elif kind == "compass":
        view["sequence"] = module["sequence"]
        view["progress"] = module["progress"]
        if reveal:
            view["answer"] = [DIRECTIONS[zh][1] for zh in module["sequence"]]
    elif kind == "number":
        view["zh"] = module["zh"]
        if reveal:
            view["answer"] = module["value"]
    return view


def view(state: dict, viewer: int, settings: dict, seated: set[int], now: datetime) -> dict:
    phase = state.get("phase")
    body: dict = {
        "phase": phase,
        "round": state.get("round"),
        "technician_choice": state.get("technician_choice"),
        "technician": state.get("technician"),
    }
    if not state.get("modules"):
        return body
    live = phase == "defuse"
    over = phase == "over"
    is_technician = viewer == state["technician"]
    body.update({
        "participants": state["participants"],
        "strikes": state["strikes"],
        "max_strikes": MAX_STRIKES,
        "you_technician": is_technician,
        "summary": [{"index": i, "type": m["type"], "solved": m["solved"]} for i, m in enumerate(state["modules"])],
    })
    if live:
        body["seconds_left"] = max(0, int(round((rooms.parse(state["ends_at"]) - now).total_seconds())))
    if (live and is_technician) or over:
        body["modules"] = [_surface(module, reveal=over) for module in state["modules"]]
    if (live and not is_technician and viewer in state["participants"]) or over:
        body["manual"] = manual({module["type"] for module in state["modules"]})
    if over and state.get("result"):
        result = state["result"]
        body["result"] = {"success": result["success"], "reason": result["reason"],
                          "points": {int(k): int(v) for k, v in result["points"].items()}}
    return body
