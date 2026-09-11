"""Обмен дубликатами из рук в руки (V4_GAMES.md §4.5).

Решения пользователя: сбор 5★ с каждого (сжигается), не больше 3 обменов в
сезон-день, отдавать можно только дубликаты — один экземпляр всегда остаётся у
владельца; косметика и купоны не обмениваются; неравный по редкости обмен
разрешён, но тот, кто отдаёт более редкое, подтверждает это отдельно.

Как идёт обмен:

1. Первый выбирает свой дубликат и показывает код (шесть цифр, три минуты).
2. Второй вводит код и выбирает свой дубликат.
3. Оба видят «отдаёте / получаете» и подтверждают. Когда подтвердили оба,
   сервер ещё раз проверяет всё — дубликаты на месте, у каждого есть 5★,
   лимит не исчерпан — и одной транзакцией переносит предметы и списывает сбор.

Незавершённые обмены живут в памяти процесса: до подтверждения ничего не
двигается, и перезапуск просто отменяет их. Совершённый обмен — две операции
`trade.swap` в журнале экономики, по одной на каждого.
"""
from __future__ import annotations

import secrets
import threading

from . import cases, meet
from .cases import CaseError, authorize, encoded, ensure_wallet
from .diary import full_wallet
from .shop import shop_day

FEE = 5
DAILY_LIMIT = 3
TRADE_SECONDS = 180
OPERATION = "trade.swap"
RARITY = {"gold": 1, "purple": 2, "black": 3}
RARITY_RU = {"gold": "обычный", "purple": "редкий", "black": "легендарный"}
NOT_TRADEABLE = {"walk"}   # купон «+30 минут» гасит вожатый, его не передают


def catalogue() -> dict[str, dict]:
    """Предметы из кейсов, которые вообще можно обменивать."""
    items = {}
    for tier in cases.rules()["tiers"]:
        for prize in tier["prizes"]:
            reward = prize["reward"]
            if reward["kind"] == "item" and prize["code"] not in NOT_TRADEABLE:
                items[prize["code"]] = {"code": prize["code"], "name_ru": prize["name_ru"], "tier": tier["code"],
                                        "rank": RARITY[tier["code"]], "effect_state": reward["effect_state"]}
    return items


def quantity(conn, account_id: int, season_id: int, item_code: str) -> int:
    row = conn.execute(
        "SELECT quantity FROM v4_case_inventory WHERE season_id=? AND account_id=? AND item_code=?",
        (season_id, account_id, item_code),
    ).fetchone()
    return int(row["quantity"]) if row else 0


def tradeable(conn, account_id: int, season_id: int) -> list[dict]:
    known = catalogue()
    return [
        {**{k: known[row["item_code"]][k] for k in ("code", "name_ru", "tier")}, "quantity": int(row["quantity"])}
        for row in conn.execute(
            """SELECT item_code, quantity FROM v4_case_inventory
               WHERE season_id=? AND account_id=? AND quantity >= 2 ORDER BY item_code""",
            (season_id, account_id),
        )
        if row["item_code"] in known
    ]


def trades_today(conn, account_id: int, season_id: int, day: str) -> int:
    return int(conn.execute(
        """SELECT COUNT(*) FROM v4_economy_operations
           WHERE season_id=? AND account_id=? AND operation=? AND json_extract(details_json, '$.day')=?""",
        (season_id, account_id, OPERATION, day),
    ).fetchone()[0])


def check_side(conn, account_id: int, season_id: int, item_code: str) -> None:
    """Всё, что должно быть правдой у одной стороны перед обменом."""
    season = authorize(conn, account_id, season_id, write=True)
    if item_code not in catalogue():
        raise CaseError("Этот предмет не обменивается.")
    if quantity(conn, account_id, season_id, item_code) < 2:
        raise CaseError("Обменять можно только дубликат: один экземпляр остаётся у владельца.", 409)
    if full_wallet(conn, account_id, season_id)["stars"] < FEE:
        raise CaseError(f"Для обмена нужно {FEE}★ сбора.", 409)
    if trades_today(conn, account_id, season_id, shop_day(season)) >= DAILY_LIMIT:
        raise CaseError(f"Сегодня уже {DAILY_LIMIT} обмена. Завтра можно снова.", 409)


def overview(conn, account_id: int, season_id: int) -> dict:
    season = authorize(conn, account_id, season_id)
    return {"season_id": season_id, "season_status": season["status"], "items": tradeable(conn, account_id, season_id),
            "stars": full_wallet(conn, account_id, season_id)["stars"],
            "trades_today": trades_today(conn, account_id, season_id, shop_day(season)),
            "limit": DAILY_LIMIT, "fee": FEE}


def execute(conn, season_id: int, trade: dict) -> dict[int, dict]:
    """Сам обмен. Внутри BEGIN IMMEDIATE; любая неправда — откат целиком."""
    a, b = trade["a"], trade["b"]
    for side in (a, b):
        check_side(conn, side["account"], season_id, side["item"])
    season = authorize(conn, a["account"], season_id, write=True)
    day = shop_day(season)
    known = catalogue()
    results = {}
    for giver, taker in ((a, b), (b, a)):
        conn.execute(
            "UPDATE v4_case_inventory SET quantity = quantity - 1 WHERE season_id=? AND account_id=? AND item_code=?",
            (season_id, giver["account"], giver["item"]),
        )
        conn.execute(
            """INSERT INTO v4_case_inventory(season_id, account_id, item_code, quantity, effect_state)
               VALUES (?,?,?,1,?) ON CONFLICT(season_id, account_id, item_code) DO UPDATE SET quantity = quantity + 1""",
            (season_id, taker["account"], giver["item"], known[giver["item"]]["effect_state"]),
        )
    for side, other in ((a, b), (b, a)):
        ensure_wallet(conn, side["account"], season_id)
        before = full_wallet(conn, side["account"], season_id)
        conn.execute("UPDATE v4_case_wallets SET stars = stars - ? WHERE season_id=? AND account_id=?",
                     (FEE, season_id, side["account"]))
        after = full_wallet(conn, side["account"], season_id)
        details = {"day": day, "gave": side["item"], "got": other["item"], "fee": FEE,
                   "partner_account_id": other["account"], "trade_code": trade["code"]}
        conn.execute(
            """INSERT INTO v4_economy_operations(season_id, account_id, actor_account_id, operation,
                   stars_delta, scans_delta, rep_delta, stars_after, scans_after, rep_after, details_json)
               VALUES (?,?,?,?,?,0,0,?,?,?,?)""",
            (season_id, side["account"], side["account"], OPERATION, after["stars"] - before["stars"],
             after["stars"], after["scans"], after["rep"], encoded(details)),
        )
        results[side["account"]] = {"gave": known[side["item"]]["name_ru"], "got": known[other["item"]]["name_ru"],
                                    "fee": FEE, "stars": after["stars"]}
    conn.execute(
        """INSERT INTO v4_audit_log(actor_account_id, season_id, action, entity_type, entity_id, after_json)
           VALUES (?,?,?,'trade',?,?)""",
        (b["account"], season_id, OPERATION, trade["code"],
         encoded({"a": {"account": a["account"], "item": a["item"]}, "b": {"account": b["account"], "item": b["item"]}})),
    )
    return results


class Desk:
    """Незавершённые обмены. Один открытый обмен на человека."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.trades: dict[str, dict] = {}
        self.by_account: dict[int, str] = {}

    def _sweep(self, now: float) -> None:
        for code, trade in list(self.trades.items()):
            finished = trade["state"] in ("done", "cancelled", "failed")
            if now - trade["created"] > TRADE_SECONDS + (60 if finished else 0):
                self.trades.pop(code, None)
                for side in (trade["a"], trade["b"]):
                    if side and self.by_account.get(side["account"]) == code:
                        self.by_account.pop(side["account"], None)

    def live(self, trade: dict, now: float) -> bool:
        return trade["state"] in ("open", "ready") and now - trade["created"] <= TRADE_SECONDS

    def create(self, account_id: int, season_id: int, item_code: str) -> dict:
        now = meet.clock()
        with self.lock:
            self._sweep(now)
            old = self.by_account.get(account_id)
            if old and old in self.trades and self.trades[old]["state"] in ("open", "ready"):
                self.trades[old]["state"] = "cancelled"
                self.trades[old]["message"] = "Обмен отменён: предложен новый."
            while True:
                code = f"{secrets.randbelow(1_000_000):06d}"
                if code not in self.trades:
                    break
            self.trades[code] = {"code": code, "season_id": season_id, "created": now, "state": "open",
                                 "a": {"account": account_id, "item": item_code, "confirmed": False},
                                 "b": None, "results": None, "message": None, "executing": False}
            self.by_account[account_id] = code
            return self.trades[code]

    def find(self, code: str) -> dict | None:
        with self.lock:
            self._sweep(meet.clock())
            return self.trades.get(code)


def side_of(trade: dict, account_id: int) -> str | None:
    if trade["a"]["account"] == account_id:
        return "a"
    if trade["b"] and trade["b"]["account"] == account_id:
        return "b"
    return None


def gives_rarer(trade: dict, side: str) -> bool:
    if not trade["b"]:
        return False
    known = catalogue()
    mine = trade[side]["item"]
    theirs = trade["b" if side == "a" else "a"]["item"]
    return known[mine]["rank"] > known[theirs]["rank"]


def view(trade: dict, viewer: int, names: dict[int, str], now: float) -> dict:
    side = side_of(trade, viewer)
    other = "b" if side == "a" else "a"
    known = catalogue()

    def describe(entry):
        if not entry:
            return None
        item = known[entry["item"]]
        return {"account_id": entry["account"], "name": names.get(entry["account"]),
                "item": {"code": item["code"], "name_ru": item["name_ru"], "tier": item["tier"]},
                "confirmed": entry["confirmed"]}

    body = {"code": trade["code"], "state": trade["state"], "role": side,
            "expires_in": max(0, int(TRADE_SECONDS - (now - trade["created"]))),
            "you": describe(trade[side]), "partner": describe(trade[other]),
            "gives_rarer": gives_rarer(trade, side), "fee": FEE, "message": trade["message"]}
    if trade["state"] == "done" and trade["results"]:
        body["result"] = trade["results"].get(viewer)
    return body
