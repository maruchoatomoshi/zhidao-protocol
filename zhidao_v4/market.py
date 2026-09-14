"""Рынок Контрабанды — этап 2 (V4_GAMES.md §4.12). Записи — внутри BEGIN IMMEDIATE.

Рынок на весь кампус на один сезон-день. Кто вышел на рынок, получает утренний
набор: игровые юани и шесть случайных товаров из колоды Контрабанды — манго и
чай, а иногда пиратский диск или поддельный телефон. Торгуют вживую: один
собирает предложение («отдаю два манго и 5 元, хочу чай») и показывает код из
шести цифр, второй вводит код, видит предложение и соглашается. Свободного
текста нет — только товары и числа.

Патрульные NetWatch — жребий дня, один на восемь торговцев. Патрульный просит
у торговца код сумки и вскрывает её: запрещёнку конфискуют, торговец платит
патрульному её штрафы; чистая сумка стоит патрульному штрафа в пользу
торговца. Одного торговца вскрывают не чаще раза в час, патрульный проверяет
не чаще раза в пять минут. Взятку патрульному предлагают обычным обменом.

В 21:00 рынок закрывается: богатство = юани + стоимость товаров + полные наборы
разрешённых товаров. Топ-3 из тех, кто в этот день торговал или проверял,
получают 10/6/3★ — если на рынок вышло не меньше четырёх человек. Юани и
товары сгорают при подведении итогов, самое позднее в 07:00.

Решения пользователя 2026-09-13: основа — обмен между игроками; юани сгорают в
07:00; ловят дети-патрульные; топ-3 дня 10/6/3★. Остальные числа — черновик
Claude в market.json.

Приватность: сумку видит только владелец, патрульный при проверке узнаёт
только найденную запрещёнку; кто с кем торговал, не записывается — только
«торговал сегодня»; предложения живут в памяти две минуты; строки дня
удаляются при подведении итогов, остаётся таблица мест.
"""
from __future__ import annotations

import json
import random
import secrets
import threading
from collections import Counter
from datetime import datetime, time, timedelta
from functools import lru_cache
from pathlib import Path

from . import cases, rooms, shop, smuggle
from .cases import CaseError, authorize, encoded, ensure_wallet
from .diary import full_wallet

CONFIG_PATH = Path(__file__).parent / "static" / "app" / "assets" / "games" / "market.json"
PRIZE_OPERATION = "market.prize"
_rng = random.SystemRandom()


class NeedsWrite(RuntimeError):
    """Опрос обнаружил, что пора подвести итоги дня или провести жребий патрульных."""


def utcnow() -> datetime:
    return shop.utcnow()


@lru_cache(maxsize=1)
def config() -> dict:
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    for key in ("min_players", "start_money", "kit", "patrol_per", "offer_seconds", "max_offer_items",
                "max_offer_money", "merchant_rest_minutes", "patrol_rest_seconds", "clean_fine", "set_bonus"):
        if type(data.get(key)) is not int or data[key] <= 0:
            raise ValueError(f"market.json: {key} должно быть положительным целым")
    if time.fromisoformat(data["open"]) >= time.fromisoformat(data["close"]):
        raise ValueError("market.json: рынок должен закрываться позже, чем открывается")
    if not data["prizes"] or any(type(p) is not int or p < 0 for p in data["prizes"]):
        raise ValueError("market.json: prizes — неотрицательные целые")
    if data["kit"] > sum(g["count"] for g in smuggle.content()["goods"]):
        raise ValueError("market.json: набор больше колоды товаров")
    return data


# --- день ---------------------------------------------------------------------------------------

def today(season, now: datetime) -> str:
    return shop.shop_day(season, now)


def phase(season, now: datetime) -> str:
    """before — рынок ещё не открылся, open — торгуют, closed — итоги дня или ночь до 07:00."""
    local = now.astimezone(shop._zone(season))
    if local.date().isoformat() != today(season, now):
        return "closed"
    if local.time() < time.fromisoformat(config()["open"]):
        return "before"
    if local.time() < time.fromisoformat(config()["close"]):
        return "open"
    return "closed"


# --- строки -------------------------------------------------------------------------------------

def _rows(conn, season_id: int, day: str) -> list:
    return conn.execute(
        """SELECT p.*, a.display_name FROM v4_market_players p JOIN v4_accounts a ON a.id = p.account_id
           WHERE p.season_id=? AND p.day=? ORDER BY p.joined_at, p.account_id""", (season_id, day)).fetchall()


def _row(conn, season_id: int, day: str, account_id: int):
    return conn.execute(
        """SELECT p.*, a.display_name FROM v4_market_players p JOIN v4_accounts a ON a.id = p.account_id
           WHERE p.season_id=? AND p.day=? AND p.account_id=?""", (season_id, day, account_id)).fetchone()


def goods_of(row) -> dict[str, int]:
    return {code: int(n) for code, n in json.loads(row["goods_json"]).items() if int(n) > 0}


def _save(conn, row, goods: dict[str, int], money: int, **extra) -> None:
    fields = {"goods_json": encoded({c: n for c, n in sorted(goods.items()) if n > 0}), "money": money, **extra}
    assignments = ", ".join(f"{column}=?" for column in fields)
    conn.execute(f"UPDATE v4_market_players SET {assignments} WHERE season_id=? AND day=? AND account_id=?",
                 (*fields.values(), row["season_id"], row["day"], row["account_id"]))


def _new_code(conn, season_id: int, day: str) -> str:
    while True:
        code = f"{secrets.randbelow(1_000_000):06d}"
        if not conn.execute("SELECT 1 FROM v4_market_players WHERE season_id=? AND day=? AND code=?",
                            (season_id, day, code)).fetchone():
            return code


def _kit() -> dict[str, int]:
    deck = [g["code"] for g in smuggle.content()["goods"] for _ in range(g["count"])]
    return dict(Counter(_rng.sample(deck, config()["kit"])))


def wealth(row) -> int:
    goods = goods_of(row)
    catalog = smuggle.goods()
    value = sum(catalog[code]["value"] * n for code, n in goods.items() if code in catalog)
    sets = min(goods.get(code, 0) for code in smuggle.legal_codes())
    return int(row["money"]) + value + sets * config()["set_bonus"]


# --- предложения ----------------------------------------------------------------------------------

class Offers:
    """Открытые предложения обмена. Живут в памяти: это минуты, а не данные. Одно на человека."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.by_code: dict[str, dict] = {}
        self.by_account: dict[int, str] = {}

    def _sweep(self, now: datetime) -> None:
        for code, offer in list(self.by_code.items()):
            if (now - offer["created"]).total_seconds() > config()["offer_seconds"]:
                self.by_code.pop(code, None)
                if self.by_account.get(offer["account_id"]) == code:
                    self.by_account.pop(offer["account_id"], None)

    def create(self, account_id: int, season_id: int, day: str, give: dict, want: dict, now: datetime) -> dict:
        with self.lock:
            self._sweep(now)
            old = self.by_account.pop(account_id, None)
            if old:
                self.by_code.pop(old, None)
            while True:
                code = f"{secrets.randbelow(1_000_000):06d}"
                if code not in self.by_code:
                    break
            offer = {"code": code, "account_id": account_id, "season_id": season_id, "day": day,
                     "give": give, "want": want, "created": now}
            self.by_code[code] = offer
            self.by_account[account_id] = code
            return dict(offer)

    def get(self, code: str, now: datetime) -> dict | None:
        with self.lock:
            self._sweep(now)
            offer = self.by_code.get(code)
            return dict(offer) if offer else None

    def mine(self, account_id: int, now: datetime) -> dict | None:
        with self.lock:
            self._sweep(now)
            code = self.by_account.get(account_id)
            return dict(self.by_code[code]) if code else None

    def take(self, code: str) -> None:
        with self.lock:
            offer = self.by_code.pop(code, None)
            if offer and self.by_account.get(offer["account_id"]) == code:
                self.by_account.pop(offer["account_id"], None)

    def cancel(self, account_id: int) -> None:
        with self.lock:
            code = self.by_account.pop(account_id, None)
            if code:
                self.by_code.pop(code, None)


offers = Offers()


def _expires_in(offer: dict, now: datetime) -> int:
    return max(0, int(config()["offer_seconds"] - (now - offer["created"]).total_seconds()))


def _basket(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    goods = {}
    for code, n in (raw.get("goods") or {}).items():
        if code not in smuggle.goods():
            raise CaseError("Такого товара нет.", 404)
        if type(n) is not int or n < 0:
            raise CaseError("Количество товара — целое число.")
        if n:
            goods[code] = n
    money = raw.get("money") or 0
    if type(money) is not int or not 0 <= money <= config()["max_offer_money"]:
        raise CaseError(f"Юаней в предложении — от 0 до {config()['max_offer_money']}.")
    return {"goods": goods, "money": money}


def _has(row, basket: dict) -> bool:
    goods = goods_of(row)
    return int(row["money"]) >= basket["money"] and all(goods.get(c, 0) >= n for c, n in basket["goods"].items())


def _moved(row, minus: dict, plus: dict) -> tuple[dict[str, int], int]:
    goods = Counter(goods_of(row))
    goods.subtract(minus["goods"])
    goods.update(plus["goods"])
    return dict(goods), int(row["money"]) - minus["money"] + plus["money"]


# --- жребий патрульных и итоги дня -------------------------------------------------------------------

def _patrol_draw(conn, season, day: str, now: datetime) -> tuple[int, list]:
    """Сколько патрульных ещё нужно и из кого тянуть жребий: торговцы, которые сегодня ещё не торговали."""
    if phase(season, now) != "open":
        return 0, []
    rows = _rows(conn, season["id"], day)
    if len(rows) < config()["min_players"]:
        return 0, []
    need = max(1, len(rows) // config()["patrol_per"]) - sum(1 for r in rows if r["role"] == "patrol")
    return need, [r for r in rows if r["role"] == "merchant" and not r["traded"]]


def _pending_days(conn, season, now: datetime) -> list[str]:
    current = today(season, now)
    closed = phase(season, now) == "closed"
    days = [row["day"] for row in conn.execute(
        """SELECT DISTINCT day FROM v4_market_players WHERE season_id=?
           AND day NOT IN (SELECT day FROM v4_market_days WHERE season_id=?) ORDER BY day""",
        (season["id"], season["id"]))]
    return [d for d in days if d < current or (d == current and closed)]


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


def _settle(conn, season, day: str, now: datetime) -> None:
    rows = _rows(conn, season["id"], day)
    rules = config()
    prizes_on = len(rows) >= rules["min_players"]
    ranked = sorted((r for r in rows if r["traded"]), key=lambda r: (-wealth(r), r["display_name"]))
    results = []
    for place, row in enumerate(ranked, start=1):
        prize = rules["prizes"][place - 1] if prizes_on and place <= len(rules["prizes"]) else 0
        if prize:
            _credit(conn, season["id"], int(row["account_id"]), prize, {"day": day, "place": place})
        results.append({"place": place, "name": row["display_name"], "wealth": wealth(row), "prize": prize,
                        "role": row["role"]})
    conn.execute("INSERT INTO v4_market_days(season_id, day, settled_at, results_json) VALUES (?,?,?,?)",
                 (season["id"], day, rooms.iso(now), encoded({"players": len(rows), "prizes": prizes_on,
                                                              "results": results[:10]})))
    conn.execute("DELETE FROM v4_market_players WHERE season_id=? AND day=?", (season["id"], day))


def _catch_up(conn, season, now: datetime, allow_write: bool) -> None:
    if season["status"] != "active":
        return
    pending = _pending_days(conn, season, now)
    need, candidates = _patrol_draw(conn, season, today(season, now), now)
    if not pending and not (need > 0 and candidates):
        return
    if not allow_write:
        raise NeedsWrite()
    for day in pending:
        _settle(conn, season, day, now)
    if need > 0 and candidates:
        for row in _rng.sample(candidates, min(need, len(candidates))):
            conn.execute("UPDATE v4_market_players SET role='patrol' WHERE season_id=? AND day=? AND account_id=?",
                         (row["season_id"], row["day"], row["account_id"]))


# --- что видит телефон ------------------------------------------------------------------------

def current(conn, actor: int, season_id: int, *, allow_write: bool) -> dict:
    season = conn.execute("SELECT * FROM v4_seasons WHERE id=?", (season_id,)).fetchone()
    now = utcnow()
    _catch_up(conn, season, now, allow_write)
    staff = cases.can_manage(conn, actor, season_id)
    if not staff:
        authorize(conn, actor, season_id)
    member = conn.execute("SELECT status FROM v4_season_memberships WHERE season_id=? AND account_id=?",
                          (season_id, actor)).fetchone()
    day = today(season, now)
    rules = config()
    rows = _rows(conn, season_id, day)
    me = next((r for r in rows if int(r["account_id"]) == actor), None)
    view = {
        "season_id": season_id, "day": day, "phase": phase(season, now), "open": rules["open"], "close": rules["close"],
        "players": len(rows), "patrols": sum(1 for r in rows if r["role"] == "patrol"),
        "min_players": rules["min_players"], "prizes": rules["prizes"], "set_bonus": rules["set_bonus"],
        "can_play": bool(member and member["status"] == "active" and season["status"] == "active"),
        "catalog": [{k: g[k] for k in ("code", "zh", "pinyin", "ru", "legal", "value", "penalty")}
                    for g in smuggle.content()["goods"]],
        "me": None, "offer": None,
    }
    if me is not None:
        mine = {"role": me["role"], "money": int(me["money"]), "goods": goods_of(me), "wealth": wealth(me),
                "traded": bool(me["traded"]), "news": json.loads(me["news_json"]) if me["news_json"] else None}
        if me["role"] == "merchant":
            mine["code"] = me["code"]
        elif me["last_inspection_at"]:
            rest = rooms.parse(me["last_inspection_at"]) + timedelta(seconds=rules["patrol_rest_seconds"])
            if rest > now:
                mine["rest_until"] = rooms.iso(rest)
        view["me"] = mine
        offer = offers.mine(actor, now)
        if offer and offer["season_id"] == season_id and offer["day"] == day:
            view["offer"] = {"code": offer["code"], "give": offer["give"], "want": offer["want"],
                             "expires_in": _expires_in(offer, now)}
    last = conn.execute("SELECT day, results_json FROM v4_market_days WHERE season_id=? ORDER BY day DESC LIMIT 1",
                        (season_id,)).fetchone()
    view["results"] = {"day": last["day"], **json.loads(last["results_json"])} if last else None
    return view


# --- действия ------------------------------------------------------------------------------------

def join(conn, actor: int, season_id: int) -> dict:
    season = authorize(conn, actor, season_id, write=True)
    now = utcnow()
    _catch_up(conn, season, now, True)
    if phase(season, now) == "closed":
        raise CaseError("Рынок на сегодня закрыт. Завтра после 07:00 можно выйти снова.", 409)
    day = today(season, now)
    if _row(conn, season_id, day, actor) is None:
        conn.execute(
            """INSERT INTO v4_market_players(season_id, day, account_id, joined_at, money, goods_json, code)
               VALUES (?,?,?,?,?,?,?)""",
            (season_id, day, actor, rooms.iso(now), config()["start_money"], encoded(_kit()),
             _new_code(conn, season_id, day)))
        _catch_up(conn, season, now, True)
    return current(conn, actor, season_id, allow_write=True)


def _trading(conn, actor: int, season_id: int):
    season = authorize(conn, actor, season_id, write=True)
    now = utcnow()
    _catch_up(conn, season, now, True)
    state = phase(season, now)
    if state == "before":
        raise CaseError(f"Рынок откроется в {config()['open']}.", 409)
    if state == "closed":
        raise CaseError("Рынок на сегодня закрыт.", 409)
    day = today(season, now)
    me = _row(conn, season_id, day, actor)
    if me is None:
        raise CaseError("Сначала выйдите на рынок.", 409)
    return season, now, day, me


def make_offer(conn, actor: int, season_id: int, give, want) -> dict:
    season, now, day, me = _trading(conn, actor, season_id)
    give, want = _basket(give), _basket(want)
    if not (give["goods"] or give["money"] or want["goods"] or want["money"]):
        raise CaseError("Предложение пустое: выберите, что отдаёте или что хотите.")
    if sum(give["goods"].values()) + sum(want["goods"].values()) > config()["max_offer_items"]:
        raise CaseError(f"В одном обмене не больше {config()['max_offer_items']} товаров.")
    if not _has(me, give):
        raise CaseError("У вас нет того, что вы отдаёте.", 409)
    offers.create(actor, season_id, day, give, want, now)
    return current(conn, actor, season_id, allow_write=True)


def cancel_offer(conn, actor: int, season_id: int) -> dict:
    authorize(conn, actor, season_id)
    offers.cancel(actor)
    return current(conn, actor, season_id, allow_write=True)


def peek(conn, actor: int, season_id: int, code: str) -> dict:
    season = authorize(conn, actor, season_id)
    now = utcnow()
    offer = offers.get(code, now)
    if not offer or offer["season_id"] != season_id or offer["day"] != today(season, now) or offer["account_id"] == actor:
        raise CaseError("Код не найден или истёк. Попросите показать новый.", 404)
    name = conn.execute("SELECT display_name FROM v4_accounts WHERE id=?", (offer["account_id"],)).fetchone()
    return {"code": code, "from": name["display_name"] if name else None, "give": offer["give"], "want": offer["want"],
            "expires_in": _expires_in(offer, now)}


def accept(conn, actor: int, season_id: int, code: str) -> dict:
    season, now, day, me = _trading(conn, actor, season_id)
    offer = offers.get(code, now)
    if not offer or offer["season_id"] != season_id or offer["day"] != day:
        raise CaseError("Код не найден или истёк. Попросите показать новый.", 404)
    if offer["account_id"] == actor:
        raise CaseError("Это ваше собственное предложение.", 409)
    them = _row(conn, season_id, day, offer["account_id"])
    if them is None:
        raise CaseError("Код не найден или истёк. Попросите показать новый.", 404)
    if not _has(them, offer["give"]):
        offers.cancel(offer["account_id"])
        raise CaseError("У торговца уже нет того, что он предлагал.", 409)
    if not _has(me, offer["want"]):
        raise CaseError("У вас нет того, что просят взамен.", 409)
    their_goods, their_money = _moved(them, offer["give"], offer["want"])
    my_goods, my_money = _moved(me, offer["want"], offer["give"])
    news = {"kind": "trade", "gave": offer["give"], "got": offer["want"], "at": rooms.iso(now)}
    _save(conn, them, their_goods, their_money, traded=1, news_json=encoded(news))
    _save(conn, me, my_goods, my_money, traded=1)
    offers.take(code)
    result = current(conn, actor, season_id, allow_write=True)
    result["trade"] = {"got": offer["give"], "gave": offer["want"]}
    return result


def inspect(conn, actor: int, season_id: int, code: str) -> dict:
    """Патрульный вводит код сумки торговца и вскрывает её."""
    season, now, day, me = _trading(conn, actor, season_id)
    rules = config()
    if me["role"] != "patrol":
        raise CaseError("Сумки вскрывают только патрульные NetWatch.", 409)
    if me["last_inspection_at"]:
        rest = rooms.parse(me["last_inspection_at"]) + timedelta(seconds=rules["patrol_rest_seconds"])
        if rest > now:
            raise CaseError(f"Следующая проверка — через {int((rest - now).total_seconds()) + 1} с.", 429)
    target = conn.execute(
        """SELECT p.*, a.display_name FROM v4_market_players p JOIN v4_accounts a ON a.id = p.account_id
           WHERE p.season_id=? AND p.day=? AND p.code=?""", (season_id, day, code)).fetchone()
    if target is None or int(target["account_id"]) == actor or target["role"] != "merchant":
        raise CaseError("Код сумки не подходит. Сверьте цифры на телефоне торговца.", 404)
    if target["last_inspected_at"] and rooms.parse(target["last_inspected_at"]) + timedelta(
            minutes=rules["merchant_rest_minutes"]) > now:
        raise CaseError("Этого торговца недавно проверяли. Дайте ему поторговать.", 409)
    catalog = smuggle.goods()
    goods = goods_of(target)
    contraband = {c: n for c, n in goods.items() if not catalog[c]["legal"]}
    if contraband:
        fine = min(int(target["money"]), sum(catalog[c]["penalty"] * n for c, n in contraband.items()))
        clean_goods = {c: n for c, n in goods.items() if c not in contraband}
        outcome = {"caught": contraband, "fine": fine}
        _save(conn, target, clean_goods, int(target["money"]) - fine, last_inspected_at=rooms.iso(now),
              news_json=encoded({"kind": "inspected", "caught": contraband, "fine": fine, "at": rooms.iso(now)}))
        _save(conn, me, goods_of(me), int(me["money"]) + fine, last_inspection_at=rooms.iso(now), traded=1)
    else:
        fine = min(int(me["money"]), rules["clean_fine"])
        outcome = {"clean": True, "fine": fine}
        _save(conn, target, goods, int(target["money"]) + fine, last_inspected_at=rooms.iso(now),
              news_json=encoded({"kind": "inspected", "clean": True, "fine": fine, "at": rooms.iso(now)}))
        _save(conn, me, goods_of(me), int(me["money"]) - fine, last_inspection_at=rooms.iso(now), traded=1)
    result = current(conn, actor, season_id, allow_write=True)
    result["inspection"] = {"merchant": target["display_name"], **outcome}
    return result
