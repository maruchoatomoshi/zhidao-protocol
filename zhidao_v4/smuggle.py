"""Контрабанда — игра за столом (V4_GAMES.md §4.12).

По мотивам «Шерифа Ноттингема», название не используем. Порт Хайнаня, таможня
BlueJoy. В каждом раунде один игрок — таможенник, остальные — купцы. Купец
тайно кладёт в сумку от одного до пяти товаров и заявляет вслух и в приложении
один разрешённый товар: «везу три манго». Количество всегда честное, тип — как
повезёт. К сумке можно приложить взятку. Таможенник смотрит в глаза и решает:

- пропустить — взятка его, все товары уходят купцу на прилавок;
- вскрыть — если сумка честная, таможенник сам платит штрафы за каждый товар;
  если нет, он отмечает, какие карты не совпадают с заявленным. Отмеченная
  запрещёнка конфискуется, купец платит штраф; неотмеченная проскальзывает;
  честный товар, отмеченный зря, стоит таможеннику штрафа.

Решения пользователя 2026-09-13: платят **игровыми юанями** — они живут в
комнате и сгорают, настоящие ★ получает только победитель (**10★, один раз в
день**, в партиях от четырёх игроков); сначала игра за столом, рынок на весь
кампус — вторым этапом; расширения — все четыре:

- **иероглифы на товарах**: в режиме «Иероглифы» таможенник видит во вскрытой
  сумке только знаки и должен прочитать, что там на самом деле;
- **роли** со способностью раз за партию: осведомитель подсматривает карту,
  контрабандист-виртуоз прячет запрещёнку двойным дном, инспектор NetWatch
  удваивает штрафы, хакер BlueJoy заставляет таможню пропустить сумку;
- **события рынка** в начале раунда: тайфун, рейд, праздник фонарей, чёрный
  рынок, день без пошлин;
- **сеты**: больше всех одного разрешённого товара — «король рынка» (+8 元),
  второй — «королева» (+4 元), каждый полный набор всех разрешённых — +6 元.

Итог: юани + стоимость товаров на прилавке + бонусы. Свободного текста нет:
торг идёт голосом за столом, в приложение — только выбор и числа. Чужая рука,
содержимое сумок и провезённая запрещёнка не уходят на чужой телефон.
"""

from __future__ import annotations

import json
import random
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from . import rooms, shop
from .cases import encoded, ensure_wallet
from .diary import full_wallet
from .rooms import GameError


GAME = "smuggle"
CONTENT = Path(__file__).resolve().parent / "static" / "app" / "assets" / "games" / "smuggle.json"
MIN_PLAYERS = 3
MODES = ("hanzi", "translated")
DEFAULT_SETTINGS = {"mode": "hanzi"}
ROLES = ("informant", "virtuoso", "inspector", "hacker")
MERCHANT_TRICKS = {"compartment": "virtuoso", "hack": "hacker"}
OFFICER_TRICKS = {"peek": "informant", "double": "inspector"}
PRIZE_OPERATION = "smuggle.prize"
WIN_POINTS = 1

_rng = random.SystemRandom()


@lru_cache(maxsize=1)
def content() -> dict:
    data = json.loads(CONTENT.read_text(encoding="utf-8"))
    codes = set()
    for good in data["goods"]:
        for key in ("code", "zh", "pinyin", "ru"):
            if not str(good.get(key) or "").strip():
                raise RuntimeError(f"smuggle.json: у товара нет поля {key}")
        if good["code"] in codes:
            raise RuntimeError(f"smuggle.json: повтор товара {good['code']}")
        codes.add(good["code"])
        for key in ("value", "penalty", "count"):
            if type(good.get(key)) is not int or good[key] <= 0:
                raise RuntimeError(f"smuggle.json: {good['code']}.{key} — положительное целое")
    if sum(1 for g in data["goods"] if g["legal"]) < 3 or sum(1 for g in data["goods"] if not g["legal"]) < 2:
        raise RuntimeError("smuggle.json: нужно хотя бы 3 разрешённых и 2 запрещённых товара")
    if {r["code"] for r in data["roles"]} != set(ROLES):
        raise RuntimeError("smuggle.json: роли — ровно informant, virtuoso, inspector, hacker")
    if not data["events"] or data["events"][0]["code"] != "calm":
        raise RuntimeError("smuggle.json: первое событие — спокойный день")
    return data


def goods() -> dict[str, dict]:
    return {g["code"]: g for g in content()["goods"]}


def legal_codes() -> list[str]:
    return [g["code"] for g in content()["goods"] if g["legal"]]


def settings_from(body: dict | None) -> dict:
    mode = rooms.text_field(body, "mode", 16)
    if mode not in MODES:
        raise GameError("Неизвестный режим.")
    return {"mode": mode}


def in_round(state: dict) -> bool:
    return state.get("phase") in ("pack", "inspect")


def joinable(status: str, state: dict) -> bool:
    return status == "lobby" or not in_round(state)


# --- колода и деньги ----------------------------------------------------------------

def _draw(state: dict, count: int) -> list[str]:
    cards = []
    for _ in range(count):
        if not state["deck"]:
            state["deck"], state["discard"] = state["discard"], []
            _rng.shuffle(state["deck"])
            if not state["deck"]:
                break
        cards.append(state["deck"].pop())
    return cards


def _pay(state: dict, payer: str, receiver: str, amount: int) -> int:
    paid = max(0, min(amount, state["players"][payer]["money"]))
    state["players"][payer]["money"] -= paid
    state["players"][receiver]["money"] += paid
    return paid


def _to_stall(state: dict, pid: str, code: str) -> None:
    bonus = content()["blackmarket_bonus"] if state["event"] == "blackmarket" and not goods()[code]["legal"] else 0
    state["players"][pid]["stall"].append({"code": code, "bonus": bonus})


def _merchants(state: dict) -> list[str]:
    return [pid for pid in state["order"] if pid != state["officer"]]


# --- партия ---------------------------------------------------------------------------

def _start(state: dict, seated: set[int]) -> None:
    if len(seated) < MIN_PLAYERS:
        raise GameError(f"Нужно минимум {MIN_PLAYERS} игрока.", 409)
    data = content()
    order = [str(pid) for pid in sorted(seated)]
    _rng.shuffle(order)
    deck = [g["code"] for g in data["goods"] for _ in range(g["count"])]
    _rng.shuffle(deck)
    roles = list(ROLES)
    _rng.shuffle(roles)
    number = int(state.get("game") or 0) + 1
    state.clear()
    state.update({
        "game": number,
        "phase": "pack",
        "round": 0,
        "rounds": len(order) * (2 if len(order) == 3 else 1),
        "order": order,
        "starters": len(order),
        "deck": deck,
        "discard": [],
        "players": {pid: {"hand": [], "stall": [], "money": data["start_money"], "role": roles[i % len(roles)],
                          "role_used": False} for i, pid in enumerate(order)},
        "last_round": None,
        "result": None,
    })
    _begin_round(state)


def _begin_round(state: dict) -> None:
    state["round"] += 1
    state["officer"] = state["order"][(state["round"] - 1) % len(state["order"])]
    events = [e["code"] for e in content()["events"]]
    state["event"] = "calm" if state["round"] == 1 else _rng.choice(events)
    for pid in state["order"]:
        hand = state["players"][pid]["hand"]
        hand.extend(_draw(state, content()["hand"] - len(hand)))
    state.update(phase="pack", bags={}, decisions={}, opened=[], peek={}, double=[], opens_used=0)


def _end_round(state: dict) -> dict[int, int]:
    # Если таможенник ушёл, неразобранные сумки проходят без взятки.
    for pid, bag in state["bags"].items():
        if pid not in state["decisions"] and pid in state["players"]:
            for code in bag["cards"]:
                _to_stall(state, pid, code)
            state["decisions"][pid] = {"kind": "pass", "count": len(bag["cards"]), "bribe": 0}
    state["last_round"] = {"round": state["round"], "officer": state["officer"], "event": state["event"],
                           "declared": {pid: {"declared": b["declared"], "count": len(b["cards"])} for pid, b in state["bags"].items()},
                           "decisions": state["decisions"]}
    if state["round"] >= state["rounds"]:
        return _finish(state, "done")
    _begin_round(state)
    return {}


def _scores(state: dict) -> dict[str, dict]:
    bonuses = content()["bonuses"]
    table = {}
    counts = {pid: {code: 0 for code in legal_codes()} for pid in state["order"]}
    for pid in state["order"]:
        player = state["players"][pid]
        goods_value = sum(goods()[item["code"]]["value"] + item["bonus"] for item in player["stall"])
        for item in player["stall"]:
            if item["code"] in counts[pid]:
                counts[pid][item["code"]] += 1
        sets = min(counts[pid].values()) if counts[pid] else 0
        table[pid] = {"money": player["money"], "goods": goods_value, "king": 0, "sets": sets * bonuses["set"],
                      "contraband": sum(1 for item in player["stall"] if not goods()[item["code"]]["legal"])}
    for code in legal_codes():
        values = sorted({counts[pid][code] for pid in state["order"] if counts[pid][code] > 0}, reverse=True)
        if not values:
            continue
        kings = [pid for pid in state["order"] if counts[pid][code] == values[0]]
        for pid in kings:
            table[pid]["king"] += bonuses["king"]
        if len(kings) == 1 and len(values) > 1:
            for pid in state["order"]:
                if counts[pid][code] == values[1]:
                    table[pid]["king"] += bonuses["queen"]
    for pid, row in table.items():
        row["total"] = row["money"] + row["goods"] + row["king"] + row["sets"]
    return table


def _finish(state: dict, reason: str) -> dict[int, int]:
    state["phase"] = "over"
    if reason != "done":
        state["result"] = {"reason": reason, "winners": [], "scores": {}, "prizes": {}}
        return {}
    table = _scores(state)
    top = max(row["total"] for row in table.values())
    winners = [pid for pid, row in table.items() if row["total"] == top]
    state["result"] = {"reason": reason, "winners": winners, "scores": table, "prizes": {}, "prized": False}
    return {int(pid): WIN_POINTS for pid in winners}


def tick(state: dict, seated: set[int], now: datetime) -> dict[int, int]:
    del now  # Таймеров нет: торг идёт голосом, раунд ждёт людей.
    if not in_round(state):
        return {}
    present = [pid for pid in state["order"] if int(pid) in seated]
    if len(present) < MIN_PLAYERS:
        return _finish(state, "too_few")
    if present == state["order"]:
        return {}
    gone = set(state["order"]) - set(present)
    state["order"] = present
    for pid in gone:
        state["bags"].pop(pid, None)
        state["decisions"].pop(pid, None)
    if state["officer"] in gone:
        return _end_round(state)
    return _advance(state)


# --- ходы --------------------------------------------------------------------------------

def _int_list(body: dict | None, key: str, max_len: int, high: int) -> list[int]:
    value = (body or {}).get(key)
    if (not isinstance(value, list) or len(value) > max_len or len(set(value)) != len(value)
            or any(type(v) is not int or not 0 <= v < high for v in value)):
        raise GameError(f"Поле {key} заполнено неверно.")
    return value


def _merchant_of(state: dict, body: dict | None) -> str:
    target = str(rooms.int_field(body, "merchant"))
    if target not in state["bags"] or target == state["officer"]:
        raise GameError("Такой сумки нет.", 404)
    return target


def _pack(state: dict, me: str, body: dict | None) -> None:
    data = content()
    if state["phase"] != "pack":
        raise GameError("Сумки уже на таможне.", 409)
    if me == state["officer"]:
        raise GameError("Таможенник в этом раунде товар не везёт.", 403)
    if me in state["bags"]:
        raise GameError("Сумка уже собрана.", 409)
    player = state["players"][me]
    limit = data["typhoon_bag"] if state["event"] == "typhoon" else data["max_bag"]
    cards = _int_list(body, "cards", limit, len(player["hand"]))
    if not cards:
        raise GameError("Положите в сумку хотя бы один товар.")
    declared = rooms.text_field(body, "declared", 20)
    if declared not in goods() or not goods()[declared]["legal"]:
        raise GameError("Заявить можно только разрешённый товар.")
    bribe = rooms.int_field(body, "bribe", 0, 999)
    if bribe > player["money"]:
        raise GameError("Столько юаней у вас нет.", 409)
    if state["event"] == "lantern" and bribe > data["lantern_bribe"]:
        raise GameError(f"Праздник фонарей: взятка не больше {data['lantern_bribe']} 元.", 409)
    trick = (body or {}).get("trick")
    if trick is not None:
        if trick not in MERCHANT_TRICKS:
            raise GameError("Такой способности нет.")
        if player["role"] != MERCHANT_TRICKS[trick] or player["role_used"]:
            raise GameError("Эта способность вам недоступна.", 409)
        player["role_used"] = True
    chosen = set(cards)
    bag = [player["hand"][i] for i in cards]
    player["hand"] = [code for i, code in enumerate(player["hand"]) if i not in chosen]
    state["bags"][me] = {"cards": bag, "declared": declared, "bribe": bribe,
                         "hack": trick == "hack", "compartment": trick == "compartment"}


def _pass(state: dict, target: str) -> None:
    bag = state["bags"][target]
    paid = 0 if bag["hack"] else _pay(state, target, state["officer"], bag["bribe"])
    for code in bag["cards"]:
        _to_stall(state, target, code)
    state["decisions"][target] = {"kind": "hacked" if bag["hack"] else "pass", "count": len(bag["cards"]), "bribe": paid}


def _judge(state: dict, target: str, marks: list[int]) -> None:
    bag = state["bags"][target]
    officer = state["officer"]
    declared = bag["declared"]
    disguised = None
    if bag["compartment"]:
        disguised = next((i for i, code in enumerate(bag["cards"]) if not goods()[code]["legal"]), None)
    mismatched = [i for i, code in enumerate(bag["cards"]) if code != declared and i != disguised]
    factor = (2 if state["event"] == "raid" else 1) * (2 if target in state["double"] else 1)
    decision = {"kind": "inspect", "count": len(bag["cards"]), "honest": not mismatched, "confiscated": [],
                "fine": 0, "officer_paid": 0, "slipped": 0}
    if not mismatched:
        owed = sum(goods()[code]["penalty"] for code in bag["cards"])
        decision["officer_paid"] = _pay(state, officer, target, owed)
        for code in bag["cards"]:
            _to_stall(state, target, code)
    else:
        fine = false_marks = 0
        for i, code in enumerate(bag["cards"]):
            if i in mismatched and i in marks:
                decision["confiscated"].append(code)
                state["discard"].append(code)
                fine += goods()[code]["penalty"] * factor
            else:
                if i in mismatched:
                    decision["slipped"] += 1
                elif i in marks:
                    false_marks += goods()[code]["penalty"]
                _to_stall(state, target, code)
        decision["fine"] = _pay(state, target, officer, fine)
        decision["officer_paid"] = _pay(state, officer, target, false_marks)
    state["decisions"][target] = decision


def _advance(state: dict) -> dict[int, int]:
    merchants = _merchants(state)
    if state["phase"] == "pack" and merchants and all(pid in state["bags"] for pid in merchants):
        state["phase"] = "inspect"
        for pid in merchants:
            if state["bags"][pid]["hack"]:
                _pass(state, pid)
    if state["phase"] == "inspect" and all(pid in state["decisions"] for pid in merchants):
        return _end_round(state)
    return {}


def act(action: str, state: dict, actor: int, body: dict | None, *,
        seated: set[int], host: int, now: datetime, settings: dict) -> tuple[str | None, dict[int, int]]:
    del now, settings
    me = str(actor)
    if action == "start":
        if in_round(state):
            raise GameError("Партия уже идёт.", 409)
        if actor != host:
            raise GameError("Партию запускает ведущий.", 403)
        _start(state, seated)
        return "playing", {}
    if not in_round(state):
        raise GameError("Партия ещё не началась.", 409)
    if me not in state["order"]:
        raise GameError("Вы не участвуете в этой партии.", 403)
    if action == "pack":
        _pack(state, me, body)
    elif action == "unpack":
        if state["phase"] != "pack" or me not in state["bags"]:
            raise GameError("Нечего разбирать.", 409)
        bag = state["bags"].pop(me)
        state["players"][me]["hand"].extend(bag["cards"])
    elif action in OFFICER_TRICKS:
        if state["phase"] != "inspect" or me != state["officer"]:
            raise GameError("Эта способность — у таможенника во время досмотра.", 403)
        player = state["players"][me]
        if player["role"] != OFFICER_TRICKS[action] or player["role_used"]:
            raise GameError("Эта способность вам недоступна.", 409)
        target = _merchant_of(state, body)
        if target in state["decisions"] or target in state["opened"]:
            raise GameError("По этой сумке уже решено.", 409)
        player["role_used"] = True
        if action == "peek":
            state["peek"][target] = _rng.randrange(len(state["bags"][target]["cards"]))
        else:
            state["double"].append(target)
    elif action in ("pass", "open", "judge"):
        if state["phase"] != "inspect":
            raise GameError("Досмотр ещё не начался.", 409)
        if me != state["officer"]:
            raise GameError("Решает таможенник.", 403)
        target = _merchant_of(state, body)
        if target in state["decisions"]:
            raise GameError("По этой сумке уже решено.", 409)
        if action == "pass":
            _pass(state, target)
        elif action == "open":
            if target in state["opened"]:
                raise GameError("Сумка уже вскрыта.", 409)
            if state["event"] == "dutyfree" and state["opens_used"] >= 1:
                raise GameError("День без пошлин: вскрыть можно только одну сумку.", 409)
            state["opened"].append(target)
            state["opens_used"] += 1
        else:
            if target not in state["opened"]:
                raise GameError("Сначала вскройте сумку.", 409)
            cards = state["bags"][target]["cards"]
            _judge(state, target, _int_list(body, "marks", len(cards), len(cards)))
    else:
        raise GameError("Такого действия в игре нет.", 404)
    return None, _advance(state)


# --- приз ------------------------------------------------------------------------------------

def award(conn, state: dict, now: datetime) -> None:
    """10★ победителю партии от четырёх игроков — не чаще раза в сезон-день.

    Вызывается маршрутом комнаты внутри той же транзакции, что и последний ход:
    модуль правил базы не знает, а приз — это журнал экономики."""
    result = state.get("result")
    if not result or result.get("reason") != "done" or result.get("prized"):
        return
    result["prized"] = True
    rules = content()["prize"]
    if state.get("starters", 0) < rules["min_players"]:
        return
    for pid in result["winners"]:
        season = conn.execute(
            """SELECT s.* FROM v4_seasons s JOIN v4_season_memberships m ON m.season_id = s.id
               WHERE s.status='active' AND m.account_id=? AND m.status='active' ORDER BY s.id DESC LIMIT 1""",
            (int(pid),)).fetchone()
        if season is None:
            result["prizes"][pid] = "no_season"
            continue
        day = shop.shop_day(season, now)
        taken = conn.execute("INSERT OR IGNORE INTO v4_smuggle_prize_days(season_id, account_id, prize_day) VALUES (?,?,?)",
                             (season["id"], int(pid), day)).rowcount
        if not taken:
            result["prizes"][pid] = "limited"
            continue
        ensure_wallet(conn, int(pid), season["id"])
        before = full_wallet(conn, int(pid), season["id"])
        conn.execute("UPDATE v4_case_wallets SET stars = stars + ? WHERE season_id=? AND account_id=?",
                     (rules["stars"], season["id"], int(pid)))
        after = full_wallet(conn, int(pid), season["id"])
        conn.execute(
            """INSERT INTO v4_economy_operations(season_id, account_id, actor_account_id, operation,
                   stars_delta, scans_delta, rep_delta, stars_after, scans_after, rep_after, details_json)
               VALUES (?,?,?,?,?,0,0,?,?,?,?)""",
            (season["id"], int(pid), int(pid), PRIZE_OPERATION, after["stars"] - before["stars"], after["stars"],
             after["scans"], after["rep"], encoded({"day": day, "players": state["starters"]})))
        result["prizes"][pid] = "granted"


# --- что видит телефон ----------------------------------------------------------------------

def _card(code: str) -> dict:
    g = goods()[code]
    return {k: g[k] for k in ("code", "zh", "pinyin", "ru", "legal", "value", "penalty")}


def _seen_card(code: str, mode: str) -> dict:
    """Карта во вскрытой сумке глазами таможенника: в режиме «Иероглифы» — только знаки."""
    g = goods()[code]
    return {"zh": g["zh"]} if mode == "hanzi" else {"zh": g["zh"], "pinyin": g["pinyin"], "ru": g["ru"]}


def _decision_view(decision: dict, owner: bool) -> dict:
    view = {k: v for k, v in decision.items() if k != "slipped"}
    if owner and "slipped" in decision:
        view["slipped"] = decision["slipped"]
    return view


def view(state: dict, viewer: int, settings: dict, seated: set[int], now: datetime) -> dict:
    del seated, now
    mode = settings.get("mode", DEFAULT_SETTINGS["mode"])
    phase = state.get("phase") or "lobby"
    out = {"phase": phase, "game": int(state.get("game") or 0), "mode": mode, "round": state.get("round", 0),
           "rounds": state.get("rounds", 0)}
    if "players" not in state:
        return out
    me = str(viewer)
    officer = state.get("officer")
    out.update(officer=int(officer) if officer else None, event=state.get("event"),
               order=[int(pid) for pid in state["order"]])
    out["table"] = {}
    for pid in state["order"]:
        stall = state["players"][pid]["stall"]
        legal = {}
        for item in stall:
            if goods()[item["code"]]["legal"]:
                legal[item["code"]] = legal.get(item["code"], 0) + 1
        out["table"][pid] = {"money": state["players"][pid]["money"], "legal": legal,
                             "hidden": sum(1 for item in stall if not goods()[item["code"]]["legal"])}
    if state.get("last_round"):
        last = state["last_round"]
        out["last_round"] = {**{k: last[k] for k in ("round", "officer", "event", "declared")},
                             "decisions": {pid: _decision_view(d, pid == me or last["officer"] == me)
                                           for pid, d in last["decisions"].items()}}
    if in_round(state):
        out["bags"] = {pid: {"declared": bag["declared"], "count": len(bag["cards"])} for pid, bag in state["bags"].items()}
        out["waiting"] = [int(pid) for pid in _merchants(state) if pid not in state["bags"]]
        out["decisions"] = {pid: _decision_view(d, pid == me or officer == me) for pid, d in state["decisions"].items()}
        out["opened"] = [int(pid) for pid in state["opened"]]
        mine = state["players"].get(me)
        if mine is not None:
            you = {"hand": [_card(code) for code in mine["hand"]], "role": mine["role"], "role_used": mine["role_used"],
                   "officer": me == officer}
            bag = state["bags"].get(me)
            if bag:
                you["bag"] = {"cards": [_card(code) for code in bag["cards"]], "declared": bag["declared"],
                              "bribe": bag["bribe"], "hack": bag["hack"], "compartment": bag["compartment"]}
            if me == officer and state["phase"] == "inspect":
                you["bribes"] = {pid: bag["bribe"] for pid, bag in state["bags"].items()}
                you["inspecting"] = {pid: [_seen_card(code, mode) for code in state["bags"][pid]["cards"]]
                                     for pid in state["opened"] if pid not in state["decisions"]}
                you["peek"] = {pid: {"index": index, "card": _seen_card(state["bags"][pid]["cards"][index], mode)}
                               for pid, index in state["peek"].items()}
                you["double"] = [int(pid) for pid in state["double"]]
            out["you"] = you
    result = state.get("result")
    if result:
        out["result"] = {"reason": result["reason"], "winners": [int(pid) for pid in result["winners"]],
                         "scores": result["scores"], "prizes": result.get("prizes", {})}
    return out
