"""Вирус Протокола (V4_GAMES.md §4.7). Все записи — внутри BEGIN IMMEDIATE.

Шуточная «инфекция» в духе нулевых. Решения пользователя:

- передаётся при обмене и при встрече с вероятностью 50%, если заражён один
  из двоих; первый вирус выпускает Архитектор из админки;
- без лечения держится 6 часов;
- бесплатное лечение — тест из пяти китайских слов (засчитан при 4 верных);
- «антивирус без теста» — 15★, «фаервол» — 20★ до конца сезон-дня (07:00).

Эффекты только смешные и живут на экране заражённого (virus.js). Хранится
только «заражён до» и «фаервол до»: кто кого заразил, не записывается нигде.
"""
from __future__ import annotations

import random
import threading
from datetime import datetime, timedelta

from . import cipher, rooms, shop
from .cases import CaseError, authorize, encoded, ensure_wallet, replay
from .diary import full_wallet

DURATION_HOURS = 6
SPREAD_CHANCE = 0.5
ANTIVIRUS_PRICE = 15
FIREWALL_PRICE = 20
TEST_SIZE = 5
TEST_PASS = 4
TEST_OPTIONS = 3
TEST_SECONDS = 300
_rng = random.SystemRandom()


def utcnow() -> datetime:
    # Те же часы, что у витрины: сезон-день и фаервол считаются одинаково.
    return shop.utcnow()


def _row(conn, season_id: int, account_id: int):
    return conn.execute("SELECT * FROM v4_virus_state WHERE season_id=? AND account_id=?",
                        (season_id, account_id)).fetchone()


def _active(value: str | None, now: datetime) -> bool:
    return bool(value) and rooms.parse(value) > now


def is_infected(conn, season_id: int, account_id: int, now: datetime | None = None) -> bool:
    row = _row(conn, season_id, account_id)
    return bool(row) and _active(row["infected_until"], now or utcnow())


def _set(conn, season_id: int, account_id: int, **fields) -> None:
    conn.execute("INSERT OR IGNORE INTO v4_virus_state(season_id, account_id) VALUES (?, ?)", (season_id, account_id))
    for column, value in fields.items():
        conn.execute(f"UPDATE v4_virus_state SET {column}=? WHERE season_id=? AND account_id=?",
                     (value, season_id, account_id))


def _infect(conn, season_id: int, account_id: int, now: datetime) -> None:
    _set(conn, season_id, account_id, infected_until=rooms.iso(now + timedelta(hours=DURATION_HOURS)))


def status(conn, account_id: int, season_id: int) -> dict:
    season = authorize(conn, account_id, season_id)
    now = utcnow()
    row = _row(conn, season_id, account_id)
    infected = bool(row) and _active(row["infected_until"], now)
    firewall = bool(row) and _active(row["firewall_until"], now)
    return {
        "season_id": season_id,
        "season_status": season["status"],
        "infected": infected,
        "seconds_left": int((rooms.parse(row["infected_until"]) - now).total_seconds()) if infected else 0,
        "firewall": firewall,
        "firewall_until": row["firewall_until"] if firewall else None,
        "prices": {"antivirus": ANTIVIRUS_PRICE, "firewall": FIREWALL_PRICE},
        "test": {"size": TEST_SIZE, "pass": TEST_PASS},
        "stars": full_wallet(conn, account_id, season_id)["stars"],
    }


def spread(conn, season_id: int, first: int, second: int) -> dict[int, str]:
    """Встреча или обмен двух людей. Возвращает исход только для того, кому
    вирус мог передаться: «caught» — заразился, «blocked» — фаервол отбил."""
    now = utcnow()
    infected = [pid for pid in (first, second) if is_infected(conn, season_id, pid, now)]
    if len(infected) != 1:
        return {}
    target = second if infected[0] == first else first
    row = _row(conn, season_id, target)
    if row and _active(row["firewall_until"], now):
        return {target: "blocked"}
    if _rng.random() >= SPREAD_CHANCE:
        return {}
    _infect(conn, season_id, target, now)
    return {target: "caught"}


def release(conn, actor: int, season_id: int, target: int) -> dict:
    """Архитектор выпускает первый вирус. Фаервол защищает и от него."""
    authorize(conn, actor, season_id, manage=True, write=True)
    authorize(conn, target, season_id, write=True)
    now = utcnow()
    row = _row(conn, season_id, target)
    if row and _active(row["firewall_until"], now):
        raise CaseError("У участника включён фаервол — вирус не прошёл.", 409)
    _infect(conn, season_id, target, now)
    conn.execute(
        """INSERT INTO v4_audit_log(actor_account_id, season_id, action, entity_type, entity_id, after_json)
           VALUES (?, ?, 'virus.release', 'virus', ?, ?)""",
        (actor, season_id, str(target), encoded({"hours": DURATION_HOURS})),
    )
    return {"season_id": season_id, "account_id": target, "infected": True}


def _charge(conn, actor: int, season_id: int, key: str, operation: str, price: int, details: dict, request_id):
    """Покупка за ★ с защитой от повтора и записью в журнал и аудит."""
    ensure_wallet(conn, actor, season_id)
    before = full_wallet(conn, actor, season_id)
    if before["stars"] < price:
        raise CaseError(f"Не хватает звёзд: нужно {price}★, у вас {before['stars']}★.", 409)
    conn.execute("UPDATE v4_case_wallets SET stars = stars - ? WHERE season_id=? AND account_id=?",
                 (price, season_id, actor))
    after = full_wallet(conn, actor, season_id)
    cursor = conn.execute(
        """INSERT INTO v4_economy_operations(season_id, account_id, actor_account_id, operation,
               stars_delta, scans_delta, rep_delta, stars_after, scans_after, rep_after, details_json)
           VALUES (?,?,?,?,?,0,0,?,?,?,?)""",
        (season_id, actor, actor, operation, -price, after["stars"], after["scans"], after["rep"], encoded(details)),
    )
    return after, cursor.lastrowid


def _finish(conn, actor, season_id, operation, key, digest, response, request_id):
    serialized = encoded(response)
    conn.execute(
        """INSERT INTO v4_idempotency_keys(account_id, operation, idempotency_key, request_hash,
               response_status, response_json) VALUES (?,?,?,?,200,?)""",
        (actor, operation, key, digest, serialized),
    )
    conn.execute(
        """INSERT INTO v4_audit_log(actor_account_id, season_id, action, entity_type, entity_id, request_id,
               after_json, metadata_json) VALUES (?,?,?,'virus',?,?,?,?)""",
        (actor, season_id, operation, str(actor), request_id, serialized, encoded({"idempotency_key": key})),
    )


def buy_antivirus(conn, actor: int, season_id: int, key: str, request_id=None):
    authorize(conn, actor, season_id)
    key, digest, old = replay(conn, actor, "virus.antivirus", key, {"season_id": season_id})
    if old is not None:
        return old, True
    authorize(conn, actor, season_id, write=True)
    if not is_infected(conn, season_id, actor):
        raise CaseError("Вы не заражены — антивирус не нужен.", 409)
    after, operation_id = _charge(conn, actor, season_id, key, "virus.antivirus", ANTIVIRUS_PRICE,
                                  {"price": ANTIVIRUS_PRICE}, request_id)
    _set(conn, season_id, actor, infected_until=None)
    response = {"season_id": season_id, "cured": True, "stars": after["stars"], "operation_id": operation_id}
    _finish(conn, actor, season_id, "virus.antivirus", key, digest, response, request_id)
    return response, False


def buy_firewall(conn, actor: int, season_id: int, key: str, request_id=None):
    authorize(conn, actor, season_id)
    key, digest, old = replay(conn, actor, "virus.firewall", key, {"season_id": season_id})
    if old is not None:
        return old, True
    season = authorize(conn, actor, season_id, write=True)
    now = utcnow()
    row = _row(conn, season_id, actor)
    if row and _active(row["firewall_until"], now):
        raise CaseError("Фаервол уже включён до утра.", 409)
    # До ближайших 07:00 по поясу сезона — «на день», как витрина.
    until = rooms.iso(datetime.fromisoformat(shop.refresh_at(season, shop.shop_day(season, now))))
    after, operation_id = _charge(conn, actor, season_id, key, "virus.firewall", FIREWALL_PRICE,
                                  {"price": FIREWALL_PRICE, "until": until}, request_id)
    _set(conn, season_id, actor, firewall_until=until)
    response = {"season_id": season_id, "firewall_until": until, "stars": after["stars"], "operation_id": operation_id}
    _finish(conn, actor, season_id, "virus.firewall", key, digest, response, request_id)
    return response, False


class Tests:
    """Тесты на лечение живут в памяти: пять вопросов и ответы к ним.

    Ответы не уходят на телефон — только иероглифы и варианты перевода."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.pending: dict[int, dict] = {}

    def make(self, account_id: int, season_id: int) -> dict:
        words = cipher.content()["words"]
        chosen = _rng.sample(words, TEST_SIZE)
        questions, answers = [], []
        for word in chosen:
            wrong = _rng.sample([w["ru"] for w in words if w["ru"] != word["ru"]], TEST_OPTIONS - 1)
            options = wrong + [word["ru"]]
            _rng.shuffle(options)
            questions.append({"zh": word["zh"], "pinyin": word["pinyin"], "options": options})
            answers.append(options.index(word["ru"]))
        with self.lock:
            self.pending[account_id] = {"season_id": season_id, "answers": answers, "created": utcnow()}
        return {"questions": questions, "size": TEST_SIZE, "pass": TEST_PASS}

    def check(self, account_id: int, season_id: int, given: list[int]) -> int:
        with self.lock:
            test = self.pending.pop(account_id, None)
        if not test or test["season_id"] != season_id or (utcnow() - test["created"]).total_seconds() > TEST_SECONDS:
            raise CaseError("Тест не найден или устарел. Начните новый.", 409)
        if len(given) != TEST_SIZE:
            raise CaseError(f"Нужно ответить на все {TEST_SIZE} вопросов.")
        return sum(1 for mine, right in zip(given, test["answers"]) if mine == right)


def pass_test(conn, account_id: int, season_id: int, correct: int) -> dict:
    authorize(conn, account_id, season_id, write=True)
    cured = correct >= TEST_PASS and is_infected(conn, season_id, account_id)
    if cured:
        _set(conn, season_id, account_id, infected_until=None)
    return {"correct": correct, "size": TEST_SIZE, "pass": TEST_PASS, "cured": cured}
