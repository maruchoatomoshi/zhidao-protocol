"""Тайный агент (V4_GAMES.md §4.12). Все записи — внутри BEGIN IMMEDIATE.

По мотивам Assassin, но без «убийств» и без выбывания. У каждого вступившего
всегда есть тайная цель и безобидная миссия на день, и каждый — чья-то цель:
агенты стоят кругом. Выполненная миссия даёт очки агента и новую цель; итог
смены — рейтинг агентов, лучший получает рамку «Тайный агент».

Решения пользователя 2026-09-13: без выбывания, на очки; проверка — смесь:
часть миссий засчитывает сервер сам (рукопожатие, обмен, дуэль Захвата, одна
комната в игре с целью), часть подтверждает цель кнопкой «да, меня поймали»;
игра на всю смену, круг и миссии меняются каждое утро в 07:00; 5★ за миссию,
но не больше двух оплаченных миссий в день.

Черновик Claude, одобренный «пока окей»: миссия +3 очка агента; раз в день
можно назвать, кто за тобой охотится, — угадал +2, ошибся −1 (ниже нуля очки
не падают). Агент, который сам спросил цель «поймал?», уже раскрыт — назвать
его ради очков нельзя. «Нет» от цели оставляет миссию и копит отказы, которые
видит вожатый — без миссий и без того, кто кому отказал.

Новая цель после миссии или раскрытия — обмен с другим агентом: агент берёт
его цель, а тот — прежнюю цель агента. Так у каждого по-прежнему одна цель и
один охотник.

Приватность: на телефон уходит только своя цель и вопрос от своего агента,
когда он сам спросил. Круг дня удаляется при пересборке в 07:00, вчерашний не
хранится; в журнале экономики у награды — день и миссия, без цели. Конец
смены удаляет круг и игроков, остаётся таблица мест.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, time
from functools import lru_cache
from pathlib import Path

from . import cases, rooms, shop
from .cases import CaseError, authorize, encoded, ensure_wallet
from .diary import full_wallet

CONFIG_PATH = Path(__file__).parent / "static" / "app" / "assets" / "games" / "agent.json"
KINDS = ("handshake", "trade", "duel", "room", "confirm")
MISSION_OPERATION = "agent.mission"
MIN_CIRCLE = 3
_rng = random.SystemRandom()


class NeedsWrite(Exception):
    """Опрос застал новый сезон-день: круг пора пересобрать под блокировкой на запись."""


def utcnow() -> datetime:
    return shop.utcnow()


@lru_cache(maxsize=1)
def config() -> dict:
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    codes = [m["code"] for m in data["missions"]]
    if len(codes) < 2 or len(codes) != len(set(codes)):
        raise ValueError("agent.json: нужно не меньше двух миссий без повторов")
    for mission in data["missions"]:
        if mission["kind"] not in KINDS or not mission.get("text_ru") or not mission.get("hint_ru"):
            raise ValueError(f"agent.json: у миссии {mission['code']} нет вида или текста")
    if type(data["min_players"]) is not int or data["min_players"] < MIN_CIRCLE:
        raise ValueError(f"agent.json: min_players — целое не меньше {MIN_CIRCLE}")
    for key in ("mission", "reveal", "wrong_guess"):
        if type(data["points"].get(key)) is not int or data["points"][key] < 0:
            raise ValueError(f"agent.json: points.{key} — неотрицательное целое")
    for key in ("stars", "daily_limit"):
        if type(data["reward"].get(key)) is not int or data["reward"][key] <= 0:
            raise ValueError(f"agent.json: reward.{key} — положительное целое")
    if type(data["asks_per_day"]) is not int or data["asks_per_day"] <= 0:
        raise ValueError("agent.json: asks_per_day — положительное целое")
    start, end = (time.fromisoformat(value) for value in data["hours"])
    if start >= end:
        raise ValueError("agent.json: часы миссий должны кончаться позже, чем начинаются")
    award = shop.items_by_code().get(data["award_frame"])
    if not award or award["kind"] != "award" or award["slot"] != "frame":
        raise ValueError("agent.json: award_frame должна быть наградной рамкой из shop.json")
    return data


def missions() -> dict[str, dict]:
    return {m["code"]: m for m in config()["missions"]}


# --- день, часы, состояние -------------------------------------------------------------------

def today(season, now: datetime) -> str:
    """Сезон-день агентов — тот же, что у витрины: до 07:00 ещё идёт вчерашний."""
    return shop.shop_day(season, now)


def in_hours(season, now: datetime) -> bool:
    local = now.astimezone(shop._zone(season)).time()
    start, end = (time.fromisoformat(value) for value in config()["hours"])
    return start <= local < end


def state_row(conn, season_id: int):
    return conn.execute("SELECT * FROM v4_agent_state WHERE season_id=?", (season_id,)).fetchone()


def running(conn, season_id: int) -> bool:
    row = state_row(conn, season_id)
    return bool(row and row["running"])


def _player(conn, season_id: int, account_id: int):
    return conn.execute("SELECT * FROM v4_agent_players WHERE season_id=? AND account_id=?",
                        (season_id, account_id)).fetchone()


def _players(conn, season_id: int) -> list[int]:
    """Кто сейчас в игре: вступил, не исключён, участник сезона и аккаунт жив."""
    return [int(row["account_id"]) for row in conn.execute(
        """SELECT p.account_id FROM v4_agent_players p
           JOIN v4_season_memberships m ON m.season_id = p.season_id AND m.account_id = p.account_id AND m.status='active'
           JOIN v4_accounts a ON a.id = p.account_id AND a.status='active'
           WHERE p.season_id=? AND p.excluded=0 ORDER BY p.account_id""", (season_id,))]


def _links(conn, season_id: int) -> dict[int, dict]:
    return {int(row["agent_account_id"]): dict(row) for row in conn.execute(
        "SELECT * FROM v4_agent_links WHERE season_id=?", (season_id,))}


def _names(conn, ids) -> dict[int, str]:
    ids = sorted({int(i) for i in ids})
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    return {int(row["id"]): row["display_name"] for row in conn.execute(
        f"SELECT id, display_name FROM v4_accounts WHERE id IN ({marks})", ids)}


# --- круг --------------------------------------------------------------------------------------

def _mission_for(conn, season_id: int, avoid: str | None = None) -> str:
    # Дуэль Захвата — только когда Захват включён, иначе миссию не выполнить.
    from . import capture
    duels_open = capture.enabled(conn, season_id)
    pool = [code for code, m in missions().items() if code != avoid and (m["kind"] != "duel" or duels_open)]
    return _rng.choice(pool)


def _set_link(conn, season_id: int, agent: int, target: int, day: str, now: datetime, avoid: str | None = None) -> None:
    conn.execute(
        """INSERT INTO v4_agent_links(season_id, agent_account_id, target_account_id, day, mission, asks, asking, known, since)
           VALUES (?,?,?,?,?,0,0,0,?)
           ON CONFLICT(season_id, agent_account_id) DO UPDATE SET target_account_id=excluded.target_account_id,
               day=excluded.day, mission=excluded.mission, asks=0, asking=0, known=0, since=excluded.since""",
        (season_id, agent, target, day, _mission_for(conn, season_id, avoid), rooms.iso(now)))


def _build(conn, season, now: datetime) -> None:
    """Пересобирает круг дня. Вчерашний круг нужен только здесь — чтобы не повторить цели."""
    season_id = season["id"]
    previous = {agent: int(row["target_account_id"]) for agent, row in _links(conn, season_id).items()}
    conn.execute("DELETE FROM v4_agent_links WHERE season_id=?", (season_id,))
    conn.execute("UPDATE v4_agent_state SET day=? WHERE season_id=?", (today(season, now), season_id))
    ids = _players(conn, season_id)
    if len(ids) < config()["min_players"]:
        return
    pairs: dict[int, int] = {}
    for _ in range(60):
        _rng.shuffle(ids)
        pairs = {ids[i]: ids[(i + 1) % len(ids)] for i in range(len(ids))}
        if all(previous.get(agent) != target for agent, target in pairs.items()):
            break
    for agent, target in pairs.items():
        _set_link(conn, season_id, agent, target, today(season, now), now)


def _ensure_day(conn, season, now: datetime, allow_write: bool) -> None:
    row = state_row(conn, season["id"])
    if not row or not row["running"] or season["status"] != "active":
        return
    if row["day"] != today(season, now):
        if not allow_write:
            raise NeedsWrite()
        _build(conn, season, now)


def _retarget(conn, season, agent: int, now: datetime) -> None:
    """Новая цель агенту — обменом с другим агентом, чтобы у каждого остался один охотник."""
    season_id = season["id"]
    links = _links(conn, season_id)
    mine = links.get(agent)
    if not mine:
        return
    old = int(mine["target_account_id"])
    swaps = [x for x, row in links.items()
             if x not in (agent, old) and int(row["target_account_id"]) != agent and not row["asking"]]
    if swaps:
        other = _rng.choice(swaps)
        _set_link(conn, season_id, agent, int(links[other]["target_account_id"]), mine["day"], now, avoid=mine["mission"])
        _set_link(conn, season_id, other, old, mine["day"], now, avoid=links[other]["mission"])
    else:
        _set_link(conn, season_id, agent, old, mine["day"], now, avoid=mine["mission"])


def _drop(conn, season, account: int, now: datetime) -> None:
    """Человек вышел из круга: его охотник получает его цель."""
    season_id = season["id"]
    links = _links(conn, season_id)
    if account not in links:
        return
    target = int(links[account]["target_account_id"])
    hunter = next((a for a, row in links.items() if int(row["target_account_id"]) == account), None)
    conn.execute("DELETE FROM v4_agent_links WHERE season_id=? AND agent_account_id=?", (season_id, account))
    if hunter is None:
        return
    if len(links) - 1 < MIN_CIRCLE or hunter == target:
        conn.execute("DELETE FROM v4_agent_links WHERE season_id=?", (season_id,))
    else:
        _set_link(conn, season_id, hunter, target, links[hunter]["day"], now, avoid=links[hunter]["mission"])


# --- очки и звёзды -----------------------------------------------------------------------------

def _news(conn, season_id: int, account_id: int, news: dict) -> None:
    conn.execute("UPDATE v4_agent_players SET news_json=? WHERE season_id=? AND account_id=?",
                 (encoded(news), season_id, account_id))


def stars_today(conn, season_id: int, account_id: int, day: str) -> int:
    return int(conn.execute(
        """SELECT COUNT(*) FROM v4_economy_operations WHERE season_id=? AND account_id=? AND operation=?
           AND json_extract(details_json, '$.day') = ?""", (season_id, account_id, MISSION_OPERATION, day)).fetchone()[0])


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
        (season_id, account_id, account_id, MISSION_OPERATION, after["stars"] - before["stars"],
         after["stars"], after["scans"], after["rep"], encoded(details)))


def _complete(conn, season, link: dict, now: datetime) -> dict:
    season_id = season["id"]
    agent = int(link["agent_account_id"])
    rules = config()
    conn.execute("UPDATE v4_agent_players SET points = points + ?, missions = missions + 1 WHERE season_id=? AND account_id=?",
                 (rules["points"]["mission"], season_id, agent))
    stars = 0
    if stars_today(conn, season_id, agent, link["day"]) < rules["reward"]["daily_limit"]:
        stars = rules["reward"]["stars"]
        _credit(conn, season_id, agent, stars, {"day": link["day"], "mission": link["mission"]})
    outcome = {"kind": "mission", "mission": link["mission"], "points": rules["points"]["mission"],
               "stars": stars, "at": rooms.iso(now)}
    _news(conn, season_id, agent, outcome)
    _retarget(conn, season, agent, now)
    return outcome


def note(conn, season_id: int, first: int, second: int, kind: str) -> None:
    """Двое что-то сделали вместе (встреча, обмен, дуэль, стол). Засчитывает миссию, если это она.

    Цель об этом не узнаёт: автоматическая миссия агента не раскрывает.
    """
    now = utcnow()
    season = conn.execute("SELECT * FROM v4_seasons WHERE id=?", (season_id,)).fetchone()
    if not season or season["status"] != "active" or not running(conn, season_id) or not in_hours(season, now):
        return
    day = today(season, now)
    codes = {code for code, m in missions().items() if m["kind"] == kind}
    for agent, target in ((int(first), int(second)), (int(second), int(first))):
        link = conn.execute(
            "SELECT * FROM v4_agent_links WHERE season_id=? AND agent_account_id=? AND target_account_id=? AND day=?",
            (season_id, agent, target, day)).fetchone()
        if link and link["mission"] in codes:
            _complete(conn, season, dict(link), now)


def note_room(conn, seated) -> None:
    """Партия за столом идёт: агент и его цель за одним столом — миссия «сыграйте вместе»."""
    ids = sorted({int(i) for i in seated})
    if len(ids) < 2:
        return
    marks = ",".join("?" * len(ids))
    rows = conn.execute(
        f"""SELECT season_id, agent_account_id, target_account_id FROM v4_agent_links
            WHERE agent_account_id IN ({marks}) AND target_account_id IN ({marks})""", ids + ids).fetchall()
    for row in rows:
        note(conn, int(row["season_id"]), int(row["agent_account_id"]), int(row["target_account_id"]), "room")


# --- представление ----------------------------------------------------------------------------

def current(conn, actor: int, season_id: int, *, allow_write: bool) -> dict:
    season = conn.execute("SELECT * FROM v4_seasons WHERE id=?", (season_id,)).fetchone()
    staff = cases.can_manage(conn, actor, season_id)
    if not staff:
        authorize(conn, actor, season_id)
    member = conn.execute("SELECT status FROM v4_season_memberships WHERE season_id=? AND account_id=?",
                          (season_id, actor)).fetchone()
    can_play = bool(member and member["status"] == "active" and season["status"] == "active")
    now = utcnow()
    _ensure_day(conn, season, now, allow_write)
    state = state_row(conn, season_id)
    day = today(season, now)
    rules = config()
    players = _players(conn, season_id)
    me = _player(conn, season_id, actor)
    you = None
    target = incoming = None
    suspects = []
    if me and me["excluded"]:
        you = {"joined": False, "excluded": True}
    elif me:
        you = {"joined": True, "points": int(me["points"]), "missions": int(me["missions"]),
               "reveals": int(me["reveals"]), "guess_used": me["guessed_day"] == day,
               "news": json.loads(me["news_json"]) if me["news_json"] else None,
               "stars_today": stars_today(conn, season_id, actor, day)}
        mine = conn.execute("SELECT * FROM v4_agent_links WHERE season_id=? AND agent_account_id=? AND day=?",
                            (season_id, actor, day)).fetchone()
        if mine:
            mission = missions()[mine["mission"]]
            target = {"name": _names(conn, [mine["target_account_id"]]).get(int(mine["target_account_id"])),
                      "mission": {"code": mine["mission"], "kind": mission["kind"], "text_ru": mission["text_ru"],
                                  "hint_ru": mission["hint_ru"]},
                      "asking": bool(mine["asking"]), "asks_left": max(0, rules["asks_per_day"] - int(mine["asks"])),
                      "since": mine["since"]}
        asked = conn.execute("SELECT * FROM v4_agent_links WHERE season_id=? AND target_account_id=? AND day=? AND asking=1",
                             (season_id, actor, day)).fetchone()
        if asked:
            incoming = {"agent": _names(conn, [asked["agent_account_id"]]).get(int(asked["agent_account_id"])),
                        "mission_text": missions()[asked["mission"]]["text_ru"]}
        names = _names(conn, players)
        suspects = [{"account_id": pid, "name": names.get(pid)} for pid in players if pid != actor]
    rating = [{"name": row["display_name"], "points": int(row["points"]), "missions": int(row["missions"]),
               "reveals": int(row["reveals"])}
              for row in conn.execute(
                  """SELECT a.display_name, p.points, p.missions, p.reveals FROM v4_agent_players p
                     JOIN v4_accounts a ON a.id = p.account_id
                     WHERE p.season_id=? AND p.excluded=0 ORDER BY p.points DESC, p.missions DESC, a.display_name""",
                  (season_id,))]
    result = {
        "season_id": season_id,
        "running": bool(state and state["running"]),
        "shift": int(state["shift"]) if state else 1,
        "day": day,
        "hours": rules["hours"],
        "min_players": rules["min_players"],
        "players": len(players),
        "points": rules["points"],
        "reward": rules["reward"],
        "can_play": can_play,
        "can_manage": staff,
        "you": you,
        "target": target,
        "incoming": incoming,
        "suspects": suspects,
        "rating": rating,
        "shifts": [{"number": int(row["number"]), "finished_at": row["finished_at"],
                    "results": json.loads(row["results_json"])}
                   for row in conn.execute("SELECT * FROM v4_agent_shifts WHERE season_id=? ORDER BY number DESC LIMIT 3",
                                           (season_id,))],
    }
    if staff:
        result["staff"] = {"players": [
            {"account_id": int(row["account_id"]), "name": row["display_name"], "points": int(row["points"]),
             "refusals": int(row["refusals"]), "excluded": bool(row["excluded"])}
            for row in conn.execute(
                """SELECT p.account_id, a.display_name, p.points, p.refusals, p.excluded FROM v4_agent_players p
                   JOIN v4_accounts a ON a.id = p.account_id WHERE p.season_id=? ORDER BY a.display_name""",
                (season_id,))]}
    return result


# --- ходы участника -----------------------------------------------------------------------------

def _in_game(conn, season_id: int, actor: int):
    me = _player(conn, season_id, actor)
    if not me or me["excluded"]:
        raise CaseError("Сначала вступите в игру.", 409)
    return me


def join(conn, actor: int, season_id: int) -> dict:
    season = authorize(conn, actor, season_id, write=True, staff_may_play=True)
    now = utcnow()
    me = _player(conn, season_id, actor)
    if me and me["excluded"]:
        raise CaseError("Вожатый исключил вас из этой смены агентов.", 403)
    if not me:
        conn.execute("INSERT INTO v4_agent_players(season_id, account_id, joined_at) VALUES (?,?,?)",
                     (season_id, actor, rooms.iso(now)))
    if running(conn, season_id):
        _ensure_day(conn, season, now, True)
        # Круга ещё нет (не хватало агентов) — собираем, как только набралось.
        if not _links(conn, season_id) and len(_players(conn, season_id)) >= config()["min_players"]:
            _build(conn, season, now)
    return current(conn, actor, season_id, allow_write=True)


def leave(conn, actor: int, season_id: int) -> dict:
    season = authorize(conn, actor, season_id, write=True, staff_may_play=True)
    me = _in_game(conn, season_id, actor)
    del me
    _drop(conn, season, actor, utcnow())
    conn.execute("DELETE FROM v4_agent_players WHERE season_id=? AND account_id=?", (season_id, actor))
    return current(conn, actor, season_id, allow_write=True)


def _today_link(conn, season, actor: int, now: datetime):
    _ensure_day(conn, season, now, True)
    if not running(conn, season["id"]):
        raise CaseError("Смена агентов сейчас не идёт.", 409)
    return conn.execute("SELECT * FROM v4_agent_links WHERE season_id=? AND agent_account_id=? AND day=?",
                        (season["id"], actor, today(season, now))).fetchone()


def ask(conn, actor: int, season_id: int) -> dict:
    """Агент говорит «миссия выполнена» — цели приходит вопрос. Этим он себя раскрывает."""
    season = authorize(conn, actor, season_id, write=True, staff_may_play=True)
    _in_game(conn, season_id, actor)
    now = utcnow()
    link = _today_link(conn, season, actor, now)
    if not link:
        raise CaseError("Сегодня у вас нет цели.", 409)
    if missions()[link["mission"]]["kind"] != "confirm":
        raise CaseError("Эта миссия засчитывается сама.", 409)
    start, end = config()["hours"]
    if not in_hours(season, now):
        raise CaseError(f"Миссии засчитываются с {start} до {end}.", 409)
    if link["asking"]:
        raise CaseError("Цель ещё не ответила.", 409)
    if int(link["asks"]) >= config()["asks_per_day"]:
        raise CaseError("Сегодня вы уже спрашивали эту цель слишком часто. Завтра будет новая.", 429)
    conn.execute("UPDATE v4_agent_links SET asking=1, known=1, asks = asks + 1 WHERE season_id=? AND agent_account_id=?",
                 (season_id, actor))
    return current(conn, actor, season_id, allow_write=True)


def answer(conn, actor: int, season_id: int, yes: bool) -> dict:
    """Цель отвечает агенту. «Да» — миссия засчитана; «нет» — миссия остаётся, отказ видит вожатый."""
    season = authorize(conn, actor, season_id, write=True, staff_may_play=True)
    now = utcnow()
    link = conn.execute("SELECT * FROM v4_agent_links WHERE season_id=? AND target_account_id=? AND day=? AND asking=1",
                        (season_id, actor, today(season, now))).fetchone()
    if not link:
        raise CaseError("Вопросов от агентов нет.", 409)
    agent = int(link["agent_account_id"])
    if yes:
        _complete(conn, season, dict(link), now)
    else:
        conn.execute("UPDATE v4_agent_links SET asking=0 WHERE season_id=? AND agent_account_id=?", (season_id, agent))
        conn.execute("UPDATE v4_agent_players SET refusals = refusals + 1 WHERE season_id=? AND account_id=?",
                     (season_id, agent))
        _news(conn, season_id, agent, {"kind": "refused", "at": rooms.iso(now)})
    return current(conn, actor, season_id, allow_write=True)


def guess(conn, actor: int, season_id: int, suspect: int) -> dict:
    """Раз в день: назвать, кто за тобой охотится. Угадал — очки и агенту новая цель."""
    season = authorize(conn, actor, season_id, write=True, staff_may_play=True)
    me = _in_game(conn, season_id, actor)
    now = utcnow()
    _ensure_day(conn, season, now, True)
    if not running(conn, season_id):
        raise CaseError("Смена агентов сейчас не идёт.", 409)
    day = today(season, now)
    if me["guessed_day"] == day:
        raise CaseError("Назвать агента можно раз в день. Завтра в 07:00 — снова.", 409)
    if suspect == actor or suspect not in _players(conn, season_id):
        raise CaseError("Такого агента в игре нет.", 404)
    hunter = conn.execute("SELECT * FROM v4_agent_links WHERE season_id=? AND target_account_id=? AND day=?",
                          (season_id, actor, day)).fetchone()
    if not hunter:
        raise CaseError("Сегодня за вами никто не охотится: круг ещё не собран.", 409)
    right = int(hunter["agent_account_id"]) == suspect
    if right and hunter["known"]:
        raise CaseError("Этот агент уже сам раскрылся, когда спрашивал вас. За него очков нет.", 409)
    rules = config()["points"]
    conn.execute("UPDATE v4_agent_players SET guessed_day=? WHERE season_id=? AND account_id=?", (day, season_id, actor))
    if right:
        conn.execute("UPDATE v4_agent_players SET points = points + ?, reveals = reveals + 1 WHERE season_id=? AND account_id=?",
                     (rules["reveal"], season_id, actor))
        _news(conn, season_id, suspect, {"kind": "exposed", "at": rooms.iso(now)})
        _retarget(conn, season, suspect, now)
    else:
        conn.execute("UPDATE v4_agent_players SET points = MAX(points - ?, 0) WHERE season_id=? AND account_id=?",
                     (rules["wrong_guess"], season_id, actor))
    _news(conn, season_id, actor, {"kind": "guess", "right": right,
                                   "points": rules["reveal"] if right else -rules["wrong_guess"], "at": rooms.iso(now)})
    return current(conn, actor, season_id, allow_write=True)


# --- вожатый ---------------------------------------------------------------------------------------

def _audit(conn, actor: int, season_id: int, action: str, after: dict) -> None:
    conn.execute(
        """INSERT INTO v4_audit_log(actor_account_id, season_id, action, entity_type, entity_id, after_json)
           VALUES (?, ?, ?, 'season', ?, ?)""", (actor, season_id, action, str(season_id), encoded(after)))


def start(conn, actor: int, season_id: int) -> dict:
    season = authorize(conn, actor, season_id, manage=True, write=True)
    now = utcnow()
    if running(conn, season_id):
        raise CaseError("Смена агентов уже идёт.", 409)
    conn.execute(
        """INSERT INTO v4_agent_state(season_id, running, updated_by_account_id, updated_at) VALUES (?,1,?,?)
           ON CONFLICT(season_id) DO UPDATE SET running=1, updated_by_account_id=excluded.updated_by_account_id,
               updated_at=excluded.updated_at""", (season_id, actor, rooms.iso(now)))
    _build(conn, season, now)
    _audit(conn, actor, season_id, "agent.start", {"players": len(_players(conn, season_id))})
    return current(conn, actor, season_id, allow_write=True)


def reshuffle(conn, actor: int, season_id: int) -> dict:
    """Пересобрать круг сейчас — когда вечером вступили новые агенты."""
    season = authorize(conn, actor, season_id, manage=True, write=True)
    if not running(conn, season_id):
        raise CaseError("Смена агентов сейчас не идёт.", 409)
    _build(conn, season, utcnow())
    _audit(conn, actor, season_id, "agent.reshuffle", {"players": len(_players(conn, season_id))})
    return current(conn, actor, season_id, allow_write=True)


def exclude(conn, actor: int, season_id: int, account_id: int) -> dict:
    season = authorize(conn, actor, season_id, manage=True, write=True)
    row = _player(conn, season_id, account_id)
    if not row or row["excluded"]:
        raise CaseError("Такого агента в игре нет.", 404)
    _drop(conn, season, account_id, utcnow())
    conn.execute("UPDATE v4_agent_players SET excluded=1, news_json=NULL WHERE season_id=? AND account_id=?",
                 (season_id, account_id))
    _audit(conn, actor, season_id, "agent.exclude", {"account_id": account_id})
    return current(conn, actor, season_id, allow_write=True)


def finish(conn, actor: int, season_id: int) -> dict:
    """Итоги смены: лучшему агенту — рамка; круг и игроки удаляются, остаётся таблица мест."""
    authorize(conn, actor, season_id, manage=True, write=True)
    state = state_row(conn, season_id)
    if not state or not state["running"]:
        raise CaseError("Смена агентов сейчас не идёт.", 409)
    now = utcnow()
    rows = conn.execute(
        """SELECT p.account_id, a.display_name, p.points, p.missions, p.reveals FROM v4_agent_players p
           JOIN v4_accounts a ON a.id = p.account_id
           WHERE p.season_id=? AND p.excluded=0 ORDER BY p.points DESC, p.missions DESC, a.display_name""",
        (season_id,)).fetchall()
    top = max((int(row["points"]) for row in rows), default=0)
    frame = config()["award_frame"]
    results = []
    awarded = 0
    for place, row in enumerate(rows, start=1):
        best = top > 0 and int(row["points"]) == top
        if best:
            awarded += conn.execute(
                """INSERT OR IGNORE INTO v4_case_inventory(season_id, account_id, item_code, quantity, effect_state)
                   VALUES (?,?,?,1,'active')""", (season_id, int(row["account_id"]), frame)).rowcount
        results.append({"place": place, "name": row["display_name"], "points": int(row["points"]),
                        "missions": int(row["missions"]), "reveals": int(row["reveals"]), "best": best})
    conn.execute("INSERT INTO v4_agent_shifts(season_id, number, finished_at, results_json) VALUES (?,?,?,?)",
                 (season_id, int(state["shift"]), rooms.iso(now), encoded(results)))
    conn.execute("DELETE FROM v4_agent_links WHERE season_id=?", (season_id,))
    conn.execute("DELETE FROM v4_agent_players WHERE season_id=?", (season_id,))
    conn.execute("UPDATE v4_agent_state SET running=0, day=NULL, shift = shift + 1, updated_by_account_id=?, updated_at=? "
                 "WHERE season_id=?", (actor, rooms.iso(now), season_id))
    _audit(conn, actor, season_id, "agent.finish", {"shift": int(state["shift"]), "frames_awarded": awarded,
                                                     "players": len(results)})
    return current(conn, actor, season_id, allow_write=True)
