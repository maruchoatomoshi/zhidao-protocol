"""Дуэли Захвата кампуса (V4_GAMES.md §4.12, этап 2). Записи — внутри BEGIN IMMEDIATE.

Двое из разных фракций стоят рядом: один показывает код из шести цифр, второй
вводит его. Вид дуэли выбирает сервер, чтобы никто не навязывал свою сильную
сторону:

- «Китайский поединок» — пять одинаковых для обоих слов, три перевода на
  каждое; больше верных — победа, при равенстве побеждает быстрый;
- «Реакция» — перевод и шесть иероглифов; очки за верный ответ тем больше,
  чем он быстрее;
- «攻守巧» — тайный ход в каждом раунде: атака бьёт хитрость, хитрость бьёт
  защиту, защита бьёт атаку; до двух побед. Кто не сходил за время раунда,
  раунд проигрывает.

Итог. Обычная дуэль приносит фракции победителя бонусные очки. Дуэль,
начатая у подтверждённой точки, вместо очков делает за фракцию победителя ход
на этой точке — как правильный ответ в Захвате. Ничья ничего не даёт. Сдался
после первого хода — проиграл; до первого хода — дуэль просто отменена.

Решения по умолчанию, принятые Claude 2026-09-13 (пользователь их может
поменять, числа — в capture.json → duels): вид дуэли случайный; дуэли в любом
месте кампуса и за точку; не больше пяти в день на человека и не с тем же
соперником два раза подряд; дневные окна и выключатель — как у Захвата.

Приватность. Кто с кем сражается, живёт в строке дуэли, пока она идёт и
несколько минут после, чтобы оба увидели итог; потом строка удаляется. «Не с
тем же подряд» помнится в памяти процесса. Правильные ответы и ход соперника в
текущем раунде на телефон не уходят.
"""
from __future__ import annotations

import copy
import json
import random
import threading
from datetime import datetime, timedelta

from . import capture, cipher, rooms, shop, story
from .cases import CaseError, authorize
from .meet import Offers

KINDS = ("quiz", "reaction", "tactics")
SHEETS = ("quiz", "reaction")
MOVES = ("attack", "defend", "trick")
BEATS = {"attack": "trick", "trick": "defend", "defend": "attack"}
STALE_ACTIVE_MINUTES = 30
_rng = random.SystemRandom()


class NeedsWrite(RuntimeError):
    """Опрос обнаружил, что дуэль пора довести или почистить: нужна блокировка на запись."""


def utcnow() -> datetime:
    return capture.utcnow()


def rules() -> dict:
    return capture.config()["duels"]


def pick_kind() -> str:
    return _rng.choice(KINDS)


class DuelOffers(Offers):
    """Коды дуэлей: те же шесть цифр и минута жизни, что у рукопожатия, плюс точка."""

    def create_for(self, account_id: int, season_id: int, point: str | None) -> dict:
        offer = self.create(account_id, season_id)
        with self._lock:
            self._by_code[offer["code"]]["point"] = point
        return {**offer, "point": point}

    def mine(self, account_id: int) -> dict | None:
        with self._lock:
            code = self._by_account.get(account_id)
        if not code:
            return None
        offer = self.peek(code)
        if not offer or not offer["live"]:
            return None
        return {"code": code, "expires_in": offer["expires_in"], "point": offer.get("point")}

    def withdraw(self, account_id: int) -> None:
        with self._lock:
            code = self._by_account.pop(account_id, None)
            if code:
                self._by_code.pop(code, None)


offers = DuelOffers()
last_rival: dict[int, int] = {}
_rival_lock = threading.Lock()


# --- строки и лимиты --------------------------------------------------------------------

def _active_row(conn, account_id: int):
    return conn.execute(
        "SELECT * FROM v4_capture_duels WHERE status='active' AND (a_account_id=? OR b_account_id=?) ORDER BY id DESC LIMIT 1",
        (account_id, account_id)).fetchone()


def _latest_row(conn, account_id: int):
    return conn.execute(
        "SELECT * FROM v4_capture_duels WHERE a_account_id=? OR b_account_id=? ORDER BY id DESC LIMIT 1",
        (account_id, account_id)).fetchone()


def _cutoffs(now: datetime) -> tuple[str, str]:
    return rooms.iso(now - timedelta(minutes=rules()["keep_minutes"])), rooms.iso(now - timedelta(minutes=STALE_ACTIVE_MINUTES))


def _stale_exists(conn, now: datetime) -> bool:
    finished, active = _cutoffs(now)
    return conn.execute(
        """SELECT 1 FROM v4_capture_duels WHERE (status<>'active' AND finished_at < ?)
           OR (status='active' AND updated_at < ?) LIMIT 1""", (finished, active)).fetchone() is not None


def purge(conn, now: datetime) -> None:
    """Закончившиеся дуэли забываются: кто с кем сражался, не хранится дольше нужного."""
    finished, active = _cutoffs(now)
    conn.execute("DELETE FROM v4_capture_duels WHERE (status<>'active' AND finished_at < ?) OR (status='active' AND updated_at < ?)",
                 (finished, active))


def _used(conn, season_id: int, account_id: int, day: str) -> int:
    row = conn.execute("SELECT used FROM v4_capture_duel_quota WHERE season_id=? AND account_id=? AND duel_day=?",
                       (season_id, account_id, day)).fetchone()
    return int(row["used"]) if row else 0


def _consume(conn, season_id: int, account_id: int, day: str) -> None:
    conn.execute(
        """INSERT INTO v4_capture_duel_quota(season_id, account_id, duel_day, used) VALUES (?,?,?,1)
           ON CONFLICT(season_id, account_id, duel_day) DO UPDATE SET used = used + 1""",
        (season_id, account_id, day))


def _guard(conn, actor: int, season_id: int, now: datetime):
    season = authorize(conn, actor, season_id, write=True)
    if not capture.enabled(conn, season_id):
        raise CaseError("Захват сейчас выключен — дуэли тоже.", 409)
    if not capture.window_state(season, now)["open"]:
        raise CaseError("Дуэли идут только в дневные окна Захвата.", 409)
    return season, capture.assign_faction(conn, season_id, actor)


# --- партия ------------------------------------------------------------------------------------

def _sheet(kind: str) -> list[dict]:
    words = cipher.content()["words"]
    items = []
    for word in _rng.sample(words, rules()["questions"]):
        if kind == "quiz":
            pool = sorted({w["ru"] for w in words} - {word["ru"]})
            options = _rng.sample(pool, 2) + [word["ru"]]
            prompt = {"zh": word["zh"], "pinyin": word["pinyin"]}
            right = word["ru"]
        else:
            pool = sorted({w["zh"] for w in words} - {word["zh"]})
            options = _rng.sample(pool, rules()["reaction_options"] - 1) + [word["zh"]]
            prompt = {"ru": word["ru"]}
            right = word["zh"]
        _rng.shuffle(options)
        items.append({"prompt": prompt, "options": options, "answer": options.index(right)})
    return items


def _new_state(kind: str, a: int, b: int, factions: dict[str, str], now: datetime) -> dict:
    players = [str(a), str(b)]
    state = {"kind": kind, "players": players, "factions": factions, "moved": False, "over": False}
    if kind in SHEETS:
        state["items"] = _sheet(kind)
        state["progress"] = {p: {"answers": [], "times": [], "served_at": rooms.iso(now)} for p in players}
        state["deadline"] = rooms.iso(now + timedelta(seconds=rules()["sheet_seconds"]))
    else:
        state.update(round=1, wins={p: 0 for p in players}, moves={p: None for p in players}, history=[],
                     round_deadline=rooms.iso(now + timedelta(seconds=rules()["round_seconds"])))
    return state


def _other(state: dict, player: str) -> str:
    a, b = state["players"]
    return b if player == a else a


def _resolve_round(state: dict, now: datetime) -> None:
    a, b = state["players"]
    ma, mb = state["moves"][a], state["moves"][b]
    if ma and mb:
        winner = a if BEATS[ma] == mb else b if BEATS[mb] == ma else None
    else:
        winner = a if ma else b if mb else None   # не сходил — раунд проиграл
    state["history"].append({a: ma, b: mb, "winner": winner})
    if winner:
        state["wins"][winner] += 1
    if max(state["wins"].values()) >= rules()["wins_needed"] or state["round"] >= rules()["max_rounds"]:
        state["over"] = True
        return
    state["round"] += 1
    state["moves"] = {p: None for p in state["players"]}
    state["round_deadline"] = rooms.iso(now + timedelta(seconds=rules()["round_seconds"]))


def advance(state: dict, now: datetime) -> bool:
    """Доводит дуэль до «сейчас» по часам сервера. True — что-то сдвинулось."""
    if state["over"]:
        return False
    if state["kind"] in SHEETS:
        if now >= rooms.parse(state["deadline"]):
            state["over"] = True
            return True
        return False
    changed = False
    while not state["over"] and now >= rooms.parse(state["round_deadline"]):
        _resolve_round(state, now)
        changed = True
    return changed


def _sheet_scores(state: dict) -> dict[str, dict]:
    limit_ms = rules()["sheet_seconds"] * 1000
    result = {}
    for player in state["players"]:
        progress = state["progress"][player]
        correct = points = total_ms = 0
        for index, item in enumerate(state["items"]):
            if index < len(progress["answers"]):
                ms = progress["times"][index]
                total_ms += ms
                if progress["answers"][index] == item["answer"]:
                    correct += 1
                    points += max(10, 100 - ms // 50)
            else:
                total_ms += limit_ms
        result[player] = {"correct": correct, "points": points, "ms": total_ms}
    return result


def _winner(state: dict) -> str | None:
    if state.get("forfeit"):
        return _other(state, state["forfeit"])
    a, b = state["players"]
    if state["kind"] in SHEETS:
        scores = _sheet_scores(state)
        if state["kind"] == "quiz":
            key = {p: (scores[p]["correct"], -scores[p]["ms"]) for p in (a, b)}
        else:
            key = {p: (scores[p]["points"],) for p in (a, b)}
    else:
        key = {p: (state["wins"][p],) for p in (a, b)}
    if key[a] == key[b]:
        return None
    return a if key[a] > key[b] else b


def _finish(conn, row, state: dict, now: datetime) -> None:
    winner = _winner(state)
    effect = None
    season = conn.execute("SELECT * FROM v4_seasons WHERE id=?", (row["season_id"],)).fetchone()
    # Сыгранная дуэль — это «сегодня играл» для награды лидера дня.
    for player in state["players"]:
        capture.record_activity(conn, season, int(player), now)
    if row["point_code"]:
        capture.count_move(conn, season, row["point_code"], now)
    if winner:
        faction = state["factions"][winner]
        if row["point_code"]:
            action, _ = capture.apply_move(conn, season, row["point_code"], faction, now)
            effect = {"kind": "point", "code": row["point_code"], "action": action}
        else:
            capture.add_bonus(conn, season, faction, rules()["bonus"], now)
            effect = {"kind": "bonus", "points": rules()["bonus"], "faction": faction}
    state["over"] = True
    state["outcome"] = {"winner": winner, "effect": effect}
    conn.execute("UPDATE v4_capture_duels SET state_json=?, status='done', updated_at=?, finished_at=? WHERE id=?",
                 (json.dumps(state, ensure_ascii=False), rooms.iso(now), rooms.iso(now), row["id"]))


def _save(conn, row, state: dict, now: datetime) -> None:
    if state["over"]:
        _finish(conn, row, state, now)
        return
    conn.execute("UPDATE v4_capture_duels SET state_json=?, updated_at=? WHERE id=?",
                 (json.dumps(state, ensure_ascii=False), rooms.iso(now), row["id"]))


# --- что видит телефон -------------------------------------------------------------------------

def _point_info(code: str | None) -> dict | None:
    if not code or code not in capture.points():
        return None
    names = story.feature_names().get(capture.points()[code]["feature"], {})
    return {"code": code, "name_ru": names.get("name_ru"), "name_zh": names.get("name_zh")}


def duel_view(conn, row, viewer: int) -> dict:
    state = json.loads(row["state_json"])
    me = str(viewer)
    rival = _other(state, me)
    name = conn.execute("SELECT display_name FROM v4_accounts WHERE id=?", (int(rival),)).fetchone()
    view = {
        "id": int(row["id"]), "kind": state["kind"], "status": row["status"], "point": _point_info(row["point_code"]),
        "you": {"faction": state["factions"][me]},
        "rival": {"name": name["display_name"] if name else "Соперник", "faction": state["factions"][rival]},
    }
    if state["kind"] in SHEETS:
        mine, theirs = state["progress"][me], state["progress"][rival]
        total = len(state["items"])
        answered = len(mine["answers"])
        current = None
        if row["status"] == "active" and answered < total:
            item = state["items"][answered]
            current = {"prompt": item["prompt"], "options": item["options"]}
        view["sheet"] = {"total": total, "answered": answered, "rival_answered": len(theirs["answers"]),
                         "deadline": state["deadline"], "current": current}
    else:
        last = None
        if state["history"]:
            h = state["history"][-1]
            last = {"you": h[me], "rival": h[rival],
                    "winner": "tie" if h["winner"] is None else "you" if h["winner"] == me else "rival"}
        view["tactics"] = {"round": state["round"], "needed": rules()["wins_needed"],
                           "wins": {"you": state["wins"][me], "rival": state["wins"][rival]},
                           "your_move": state["moves"][me], "rival_moved": state["moves"][rival] is not None,
                           "round_deadline": state["round_deadline"], "last": last}
    if row["status"] == "done":
        outcome = state.get("outcome") or {}
        winner = outcome.get("winner")
        result = {"result": "draw" if winner is None else "win" if winner == me else "lose",
                  "effect": outcome.get("effect"), "forfeit": "you" if state.get("forfeit") == me
                  else "rival" if state.get("forfeit") == rival else None}
        if state["kind"] in SHEETS:
            scores = _sheet_scores(state)
            result["score"] = {"you": {k: scores[me][k] for k in ("correct", "points")},
                               "rival": {k: scores[rival][k] for k in ("correct", "points")}}
        else:
            result["score"] = {"you": state["wins"][me], "rival": state["wins"][rival]}
        view["result"] = result
    elif row["status"] == "cancelled":
        view["result"] = {"result": "cancelled"}
    return view


def current(conn, actor: int, season_id: int, *, allow_write: bool) -> dict:
    """Дуэль и код человека сейчас. Пишет, только если дуэль пора довести или почистить."""
    member = conn.execute("SELECT status FROM v4_season_memberships WHERE season_id=? AND account_id=?",
                          (season_id, actor)).fetchone()
    if not member or member["status"] != "active":
        return {"duel": None, "offer": None, "duels_left": None}
    now = utcnow()
    row = _active_row(conn, actor)
    due = bool(row) and advance(copy.deepcopy(json.loads(row["state_json"])), now)
    if (due or _stale_exists(conn, now)) and not allow_write:
        raise NeedsWrite()
    if due:
        state = json.loads(row["state_json"])
        advance(state, now)
        _save(conn, row, state, now)
    if allow_write:
        purge(conn, now)
    latest = _latest_row(conn, actor)
    season = conn.execute("SELECT * FROM v4_seasons WHERE id=?", (season_id,)).fetchone()
    left = max(0, rules()["daily_limit"] - _used(conn, season_id, actor, shop.shop_day(season, now)))
    return {"duel": duel_view(conn, latest, actor) if latest else None, "offer": offers.mine(actor), "duels_left": left,
            "bonus": rules()["bonus"]}


# --- ходы ----------------------------------------------------------------------------------------

def offer(conn, actor: int, season_id: int, *, point: str | None, lon, lat, accuracy_m) -> dict:
    now = utcnow()
    season, _ = _guard(conn, actor, season_id, now)
    purge(conn, now)
    if _active_row(conn, actor):
        raise CaseError("Сначала закончите текущую дуэль.", 409)
    if _used(conn, season_id, actor, shop.shop_day(season, now)) >= rules()["daily_limit"]:
        raise CaseError(f"Сегодня уже {rules()['daily_limit']} дуэлей. Завтра можно снова.", 409)
    if point is not None:
        if point not in capture.points():
            raise CaseError("Такой точки нет.", 404)
        row = capture._point_rows(conn, season_id).get(point)
        if row is None:
            raise CaseError("Точка ещё не подтверждена вожатым.", 404)
        if lon is None or lat is None:
            raise CaseError("Для дуэли за точку нужна ваша позиция.")
        capture._present(row, lon, lat, accuracy_m)
    return offers.create_for(actor, season_id, point)


def join(conn, actor: int, season_id: int, code: str) -> dict:
    now = utcnow()
    season, faction = _guard(conn, actor, season_id, now)
    claimed = offers.claim(code)
    if not claimed or claimed["season_id"] != season_id:
        if claimed:
            offers.release(code)
        raise CaseError("Код не найден или устарел. Попросите соперника показать новый.", 404)
    host = int(claimed["account_id"])
    try:
        if host == actor:
            raise CaseError("Это ваш собственный код. Покажите его сопернику.", 409)
        authorize(conn, host, season_id, write=True)
        host_faction = capture.assign_faction(conn, season_id, host)
        if host_faction == faction:
            raise CaseError("Вы из одной фракции. Дуэль — только с соперником.", 409)
        purge(conn, now)
        if _active_row(conn, host) or _active_row(conn, actor):
            raise CaseError("Кто-то из вас уже в дуэли.", 409)
        day = shop.shop_day(season, now)
        if any(_used(conn, season_id, pid, day) >= rules()["daily_limit"] for pid in (host, actor)):
            raise CaseError("У кого-то из вас дуэли на сегодня закончились.", 409)
        with _rival_lock:
            # Подряд — это когда прошлая дуэль у обоих была друг с другом.
            if last_rival.get(host) == actor and last_rival.get(actor) == host:
                raise CaseError("Вы только что сражались. Сначала дуэль с кем-то другим.", 409)
        point = claimed.get("point")
        if point and capture._point_rows(conn, season_id).get(point) is None:
            raise CaseError("Точка больше недоступна.", 409)
    except CaseError:
        offers.release(code)
        raise
    for pid in (host, actor):
        _consume(conn, season_id, pid, day)
    kind = pick_kind()
    state = _new_state(kind, host, actor, {str(host): host_faction, str(actor): faction}, now)
    conn.execute(
        """INSERT INTO v4_capture_duels(season_id, a_account_id, b_account_id, kind, point_code, state_json,
               created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)""",
        (season_id, host, actor, kind, point, json.dumps(state, ensure_ascii=False), rooms.iso(now), rooms.iso(now)))
    with _rival_lock:
        last_rival[host], last_rival[actor] = actor, host
    offers.finish(code, {"state": "started"})
    return current(conn, actor, season_id, allow_write=True)


def _playing(conn, actor: int, season_id: int, now: datetime):
    authorize(conn, actor, season_id, write=True)
    row = _active_row(conn, actor)
    if row is None:
        raise CaseError("Дуэль не найдена или уже закончилась.", 404)
    state = json.loads(row["state_json"])
    # Время вышло раньше хода: итог записывается и возвращается, а не теряется
    # вместе с ошибкой (ошибка откатила бы транзакцию).
    if advance(state, now):
        _save(conn, row, state, now)
    return row, state


def answer(conn, actor: int, season_id: int, choice: int) -> dict:
    now = utcnow()
    row, state = _playing(conn, actor, season_id, now)
    if state["over"]:
        return current(conn, actor, season_id, allow_write=True)
    if state["kind"] not in SHEETS:
        raise CaseError("В этой дуэли не отвечают, а ходят.", 409)
    progress = state["progress"][str(actor)]
    index = len(progress["answers"])
    if index >= len(state["items"]):
        raise CaseError("Вы уже ответили на все вопросы.", 409)
    if not 0 <= choice < len(state["items"][index]["options"]):
        raise CaseError("Такого варианта нет.")
    elapsed = int((now - rooms.parse(progress["served_at"])).total_seconds() * 1000)
    progress["answers"].append(choice)
    progress["times"].append(max(0, elapsed))
    progress["served_at"] = rooms.iso(now)
    state["moved"] = True
    total = len(state["items"])
    if all(len(state["progress"][p]["answers"]) >= total for p in state["players"]):
        state["over"] = True
    _save(conn, row, state, now)
    return current(conn, actor, season_id, allow_write=True)


def move(conn, actor: int, season_id: int, choice: str) -> dict:
    now = utcnow()
    row, state = _playing(conn, actor, season_id, now)
    if state["over"]:
        return current(conn, actor, season_id, allow_write=True)
    if state["kind"] != "tactics":
        raise CaseError("В этой дуэли отвечают на вопросы.", 409)
    if choice not in MOVES:
        raise CaseError("Такого хода нет.")
    me = str(actor)
    if state["moves"][me] is not None:
        raise CaseError("Вы уже сходили в этом раунде.", 409)
    state["moves"][me] = choice
    state["moved"] = True
    if all(state["moves"][p] for p in state["players"]):
        _resolve_round(state, now)
    _save(conn, row, state, now)
    return current(conn, actor, season_id, allow_write=True)


def leave(conn, actor: int, season_id: int) -> dict:
    now = utcnow()
    offers.withdraw(actor)
    authorize(conn, actor, season_id, write=True)
    row = _active_row(conn, actor)
    if row is not None:
        state = json.loads(row["state_json"])
        if not state["moved"]:
            conn.execute("UPDATE v4_capture_duels SET status='cancelled', updated_at=?, finished_at=? WHERE id=?",
                         (rooms.iso(now), rooms.iso(now), row["id"]))
        else:
            state["forfeit"] = str(actor)
            _finish(conn, row, state, now)
    return current(conn, actor, season_id, allow_write=True)
