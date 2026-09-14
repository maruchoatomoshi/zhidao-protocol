"""Скрытые файлы и сюжет по местам (V4_GAMES.md §4.4). Записи — внутри BEGIN IMMEDIATE.

Загадка сезона в интерфейсе нулевых: сообщение от незнакомого контакта, файл в
Корзине, окно ошибки, битый ярлык, «Свойства», сигнал с места на кампусе.
Каждый решённый фрагмент открывает слово сообщения Архитектора.

Решения пользователя 2026-09-12: черновик сценария пишет Claude, 10 дней.
Каждый сезон-день в 07:00 выходит следующий фрагмент, но открыть его можно,
только разгадав предыдущий, — отставшие догоняют. Фрагменты «на местах»
открываются, когда группа открыла на карте клетку у настоящего объекта кампуса
(campus.geojson). Объекты пока verified: false, поэтому засчитывается и
соседняя клетка.

Прогресс общий на сезон: кто разгадал, не хранится. Правильные ответы живут
только здесь и в story_scenario.json вне статики — в ответ API они не попадают.
Сценарий можно переписать без кода; проверка формы — scenario().
"""
from __future__ import annotations

import json
import unicodedata
from datetime import date
from functools import lru_cache
from pathlib import Path

from . import campus, cases, shop
from .cases import CaseError, authorize

SCENARIO_PATH = Path(__file__).parent / "story_scenario.json"
SURFACES = ("icq", "recycle_bin", "error_window", "broken_shortcut", "properties", "place")
# Решение пользователя 2026-09-14: когда сообщение собрано, награду получают все
# участники сезона — рамка и ★. Кто разгадал последний фрагмент, не записывается.
FINALE_OPERATION = "story.finale"


def utcnow():
    return shop.utcnow()


def normalize(text: str) -> str:
    """Регистр, «ё», пробелы, знаки препинания и тоны пиньиня не важны."""
    text = unicodedata.normalize("NFKD", str(text).lower().replace("ё", "е"))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return "".join(ch for ch in text if ch.isalnum())


@lru_cache(maxsize=1)
def feature_centres() -> dict[str, tuple[float, float]]:
    data = json.loads(campus.CAMPUS_GEOJSON.read_text(encoding="utf-8"))
    centres = {}
    for feature in data.get("features") or []:
        points: list[list[float]] = []

        def walk(coords) -> None:
            if coords and isinstance(coords[0], (int, float)):
                points.append(coords)
                return
            for item in coords or []:
                walk(item)

        walk((feature.get("geometry") or {}).get("coordinates"))
        feature_id = (feature.get("properties") or {}).get("id")
        if feature_id and points:
            centres[feature_id] = (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))
    return centres


@lru_cache(maxsize=1)
def feature_names() -> dict[str, dict]:
    data = json.loads(campus.CAMPUS_GEOJSON.read_text(encoding="utf-8"))
    return {f["properties"]["id"]: {"name_ru": f["properties"].get("name_ru"), "name_zh": f["properties"].get("name_zh")}
            for f in data.get("features") or [] if (f.get("properties") or {}).get("id")}


@lru_cache(maxsize=1)
def scenario() -> dict:
    data = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    fragments = data["fragments"]
    if len(fragments) != len(data["message"]):
        raise ValueError("story_scenario.json: слов в сообщении должно быть столько же, сколько фрагментов")
    codes = [fragment["code"] for fragment in fragments]
    if len(codes) != len(set(codes)):
        raise ValueError("story_scenario.json: повтор кода фрагмента")
    for fragment in fragments:
        if fragment["surface"] not in SURFACES:
            raise ValueError(f"story_scenario.json: неизвестная поверхность у {fragment['code']}")
        if not fragment.get("answers") or not all(normalize(answer) for answer in fragment["answers"]):
            raise ValueError(f"story_scenario.json: у {fragment['code']} нет ответов")
        if (fragment["surface"] == "place") != bool(fragment.get("place")):
            raise ValueError(f"story_scenario.json: место у {fragment['code']} не совпадает с поверхностью")
        if fragment.get("place") and fragment["place"] not in feature_centres():
            raise ValueError(f"story_scenario.json: объекта {fragment['place']} нет в campus.geojson")
    reward = data.get("finale_reward") or {}
    frame = shop.items_by_code().get(reward.get("frame"))
    if (not isinstance(reward.get("stars"), int) or reward["stars"] < 0 or not frame
            or frame["kind"] != "award" or frame["slot"] != "frame"):
        raise ValueError("story_scenario.json: finale_reward — это ★ и наградная рамка из shop.json")
    return data


def place_open(conn, season_id: int, feature_id: str) -> bool:
    lon, lat = feature_centres()[feature_id]
    cell_lon, cell_lat = campus.snap(lon, lat)
    return conn.execute(
        """SELECT 1 FROM v4_campus_cells WHERE season_id=? AND cell_lon BETWEEN ? AND ?
           AND cell_lat BETWEEN ? AND ? LIMIT 1""",
        (season_id, cell_lon - 1, cell_lon + 1, cell_lat - 1, cell_lat + 1),
    ).fetchone() is not None


def started_day(conn, season, today: str) -> str:
    """День первого фрагмента: дата начала сезона, а если её нет — первый заход в историю.

    Официальная дата всегда главнее: календарь не должен зависеть от того, кто
    первым открыл приложение."""
    if season["starts_on"]:
        return season["starts_on"]
    row = conn.execute("SELECT started_day FROM v4_story_state WHERE season_id=?", (season["id"],)).fetchone()
    if row:
        return row["started_day"]
    if season["status"] == "active":
        conn.execute("INSERT OR IGNORE INTO v4_story_state(season_id, started_day) VALUES (?, ?)", (season["id"], today))
    return today


def progress(conn, season) -> dict:
    today = shop.shop_day(season, utcnow())
    first = started_day(conn, season, today)
    day = max(0, (date.fromisoformat(today) - date.fromisoformat(first)).days + 1)
    solved = {row["fragment_code"] for row in conn.execute(
        "SELECT fragment_code FROM v4_story_solved WHERE season_id=?", (season["id"],))}
    states = []
    previous_solved = True
    for number, fragment in enumerate(scenario()["fragments"], start=1):
        if number > day:
            break
        if fragment["code"] in solved:
            state = "solved"
        elif not previous_solved:
            state = "locked_previous"
        elif fragment.get("place") and not place_open(conn, season["id"], fragment["place"]):
            state = "locked_place"
        else:
            state = "open"
        states.append((number, fragment, state))
        previous_solved = fragment["code"] in solved
    return {"today": today, "day": day, "solved": solved, "states": states}


def fragment_view(number: int, fragment: dict, state: str) -> dict:
    view = {"number": number, "code": fragment["code"], "surface": fragment["surface"], "title": fragment["title"],
            "state": state}
    if fragment.get("sender"):
        view["sender"] = fragment["sender"]
    if fragment.get("place"):
        view["place"] = feature_names().get(fragment["place"], {})
    if state in ("open", "solved"):
        view.update(body=fragment["body"], question=fragment["question"])
    if state == "open":
        view["hint"] = fragment["hint"]
    if state == "solved":
        view["word"] = scenario()["message"][number - 1]
    return view


def season_for(conn, account_id: int, season_id: int):
    """Смотреть историю может участник сезона или вожатый; отвечать — только участник."""
    if cases.can_manage(conn, account_id, season_id):
        return conn.execute("SELECT * FROM v4_seasons WHERE id=?", (season_id,)).fetchone()
    return authorize(conn, account_id, season_id)


def view(conn, account_id: int, season_id: int) -> dict:
    season = season_for(conn, account_id, season_id)
    state = progress(conn, season)
    data = scenario()
    total = len(data["fragments"])
    words = [data["message"][i] if fragment["code"] in state["solved"] else None
             for i, fragment in enumerate(data["fragments"])]
    complete = all(words)
    body = {
        "season_id": season_id, "season_status": season["status"], "title": data["title"],
        "day": state["day"], "released": len(state["states"]), "total": total,
        "fragments": [fragment_view(*item) for item in state["states"]],
        "message": words, "complete": complete,
    }
    if complete:
        body["epilogue"] = data["epilogue"]
        body["signature"] = data["signature"]
        reward = data["finale_reward"]
        body["reward"] = {"stars": reward["stars"], "frame": reward["frame"],
                          "name_ru": shop.items_by_code()[reward["frame"]]["name_ru"],
                          "received": rewarded(conn, season_id, account_id)}
    return body


def rewarded(conn, season_id: int, account_id: int) -> bool:
    return conn.execute("SELECT 1 FROM v4_economy_operations WHERE season_id=? AND account_id=? AND operation=? LIMIT 1",
                        (season_id, account_id, FINALE_OPERATION)).fetchone() is not None


def reward_everyone(conn, season_id: int) -> int:
    """Финал: всем активным участникам сезона — рамка и ★, каждому один раз.

    В журнале экономики участник сам себе актор: кто разгадал последний
    фрагмент, нигде не остаётся."""
    reward = scenario()["finale_reward"]
    members = [int(row["account_id"]) for row in conn.execute(
        """SELECT m.account_id FROM v4_season_memberships m JOIN v4_accounts a ON a.id = m.account_id
           WHERE m.season_id=? AND m.status='active' AND a.status='active' ORDER BY m.account_id""", (season_id,))]
    given = 0
    for account_id in members:
        if rewarded(conn, season_id, account_id):
            continue
        cases.ensure_wallet(conn, account_id, season_id)
        before = cases.wallet(conn, account_id, season_id)
        conn.execute("UPDATE v4_case_wallets SET stars = stars + ? WHERE season_id=? AND account_id=?",
                     (reward["stars"], season_id, account_id))
        cases.record(conn, account_id, account_id, season_id, FINALE_OPERATION, before,
                     cases.wallet(conn, account_id, season_id), {"frame": reward["frame"]})
        conn.execute("""INSERT OR IGNORE INTO v4_case_inventory(season_id, account_id, item_code, quantity, effect_state)
                        VALUES (?,?,?,1,'active')""", (season_id, account_id, reward["frame"]))
        given += 1
    return given


def answer(conn, actor: int, season_id: int, code: str, text: str) -> dict:
    season = authorize(conn, actor, season_id, write=True)
    state = progress(conn, season)
    found = next((item for item in state["states"] if item[1]["code"] == code), None)
    if not found:
        raise CaseError("Этот файл ещё не появился.", 404)
    number, fragment, current = found
    word = scenario()["message"][number - 1]
    if current == "solved":
        return {"correct": True, "already": True, "number": number, "word": word}
    if current != "open":
        raise CaseError("Этот файл пока закрыт: сначала разгадайте предыдущий или откройте место на карте.", 409)
    if normalize(text) not in {normalize(candidate) for candidate in fragment["answers"]}:
        return {"correct": False, "number": number}
    conn.execute("INSERT OR IGNORE INTO v4_story_solved(season_id, fragment_code, solved_day) VALUES (?,?,?)",
                 (season_id, code, state["today"]))
    solved = state["solved"] | {code}
    complete = all(f["code"] in solved for f in scenario()["fragments"])
    result = {"correct": True, "number": number, "word": word, "complete": complete}
    if complete:
        result["rewarded"] = reward_everyone(conn, season_id)
    return result
