"""Мастерская дубликатов (V4_GAMES.md §4.8). Все записи — внутри BEGIN IMMEDIATE.

Решения пользователя 2026-09-12:

- три одинаковых предмета → один предмет ступенью выше; один экземпляр
  всегда остаётся у владельца, поэтому одинаковых нужно хотя бы четыре;
- сбор сжигается: обычный → редкий 10★, каждая ступень выше — 25★;
- новые импланты (Нефритовый страж, Дипломат, Золотой нексус) — ступень
  «Улучшенный» между редким и легендарным, из кейсов не выпадают;
- ступень гарантирована: обычные → случайный редкий, редкие → случайный
  улучшенный, улучшенные → случайный легендарный; легендарные дальше не идут.

Исход выбирает сервер, каждый предмет целевой ступени — с равным шансом.
Купон «+30 минут» в мастерскую не принимается: его гасит вожатый. Числа живут
в assets/workshop/workshop.json, чтобы экран и сервер не разошлись.
"""
from __future__ import annotations

import json
import random
from functools import lru_cache

from . import cases
from .cases import CaseError, authorize, encoded, ensure_wallet, replay
from .diary import full_wallet

OPERATION = "workshop.craft"
_rng = random.SystemRandom()


@lru_cache(maxsize=1)
def config() -> dict:
    data = json.loads(cases.WORKSHOP_PATH.read_text(encoding="utf-8"))
    if type(data["input"]) is not int or data["input"] < 2 or type(data["keep"]) is not int or data["keep"] < 1:
        raise ValueError("workshop.json: неверный курс")
    for step in data["steps"]:
        if type(step["fee"]) is not int or step["fee"] < 0:
            raise ValueError("workshop.json: сбор должен быть неотрицательным целым")
        for tier in (step["from"], step["to"]):
            if tier not in data["tier_names"]:
                raise ValueError(f"workshop.json: у ступени {tier} нет названия")
    return data


@lru_cache(maxsize=1)
def tiers() -> dict[str, list[dict]]:
    """Предметы по ступеням: предметы из кейсов (без купона) и из мастерской."""
    excluded = set(config()["not_accepted"])
    grouped: dict[str, list[dict]] = {}
    for tier in cases.rules()["tiers"]:
        for prize in tier["prizes"]:
            if prize["reward"]["kind"] == "item" and prize["code"] not in excluded:
                grouped.setdefault(tier["code"], []).append(
                    {"code": prize["code"], "name_ru": prize["name_ru"], "effect_state": prize["reward"]["effect_state"]})
    for item in config()["items"]:
        grouped.setdefault(item["tier"], []).append(
            {"code": item["code"], "name_ru": item["name_ru"], "effect_state": item["effect_state"]})
    for step in config()["steps"]:
        if not grouped.get(step["to"]):
            raise ValueError(f"workshop.json: в ступени {step['to']} нет предметов")
    return grouped


def find(code: str) -> tuple[str, dict] | tuple[None, None]:
    for tier, items in tiers().items():
        for item in items:
            if item["code"] == code:
                return tier, item
    return None, None


def step_from(tier: str | None) -> dict | None:
    return next((step for step in config()["steps"] if step["from"] == tier), None)


def tier_name(tier: str) -> str:
    return config()["tier_names"][tier]["name_ru"]


def quantity(conn, account_id: int, season_id: int, code: str) -> int:
    row = conn.execute(
        "SELECT quantity FROM v4_case_inventory WHERE season_id=? AND account_id=? AND item_code=?",
        (season_id, account_id, code),
    ).fetchone()
    return int(row["quantity"]) if row else 0


def state(conn, account_id: int, season_id: int) -> dict:
    """Что человек может переплавить сейчас и чего ему не хватает."""
    season = authorize(conn, account_id, season_id)
    need = config()["input"] + config()["keep"]
    recipes = []
    for row in conn.execute(
        "SELECT item_code, quantity FROM v4_case_inventory WHERE season_id=? AND account_id=? AND quantity>0",
        (season_id, account_id),
    ):
        tier, item = find(row["item_code"])
        step = step_from(tier)
        if not step:
            continue
        count = int(row["quantity"])
        recipes.append({
            "code": item["code"], "name_ru": item["name_ru"], "tier": tier, "tier_name": tier_name(tier),
            "quantity": count, "ready": count >= need, "missing": max(0, need - count), "fee": step["fee"],
            "to_tier": step["to"], "to_tier_name": tier_name(step["to"]),
            "outcomes": [candidate["name_ru"] for candidate in tiers()[step["to"]]],
        })
    order = [step["from"] for step in config()["steps"]]
    recipes.sort(key=lambda r: (not r["ready"], -order.index(r["tier"]), r["code"]))
    return {"season_id": season_id, "season_status": season["status"],
            "stars": full_wallet(conn, account_id, season_id)["stars"],
            "input": config()["input"], "keep": config()["keep"], "recipes": recipes}


def craft(conn, actor: int, season_id: int, item_code: str, key: str, request_id=None):
    authorize(conn, actor, season_id)
    key, digest, old = replay(conn, actor, OPERATION, key, {"season_id": season_id, "item_code": item_code})
    if old is not None:
        return old, True
    authorize(conn, actor, season_id, write=True)
    tier, item = find(item_code)
    step = step_from(tier)
    if not step:
        raise CaseError("Этот предмет в мастерской не переплавляется.")
    need = config()["input"] + config()["keep"]
    if quantity(conn, actor, season_id, item_code) < need:
        raise CaseError(f"Нужно {need} одинаковых: {config()['input']} уйдут в переплавку, "
                        f"{config()['keep']} останется у вас.", 409)
    ensure_wallet(conn, actor, season_id)
    before = full_wallet(conn, actor, season_id)
    if before["stars"] < step["fee"]:
        raise CaseError(f"Не хватает звёзд: нужно {step['fee']}★, у вас {before['stars']}★.", 409)

    outcome = _rng.choice(tiers()[step["to"]])
    conn.execute("UPDATE v4_case_inventory SET quantity = quantity - ? WHERE season_id=? AND account_id=? AND item_code=?",
                 (config()["input"], season_id, actor, item_code))
    conn.execute(
        """INSERT INTO v4_case_inventory(season_id, account_id, item_code, quantity, effect_state)
           VALUES (?,?,?,1,?) ON CONFLICT(season_id, account_id, item_code) DO UPDATE SET quantity = quantity + 1""",
        (season_id, actor, outcome["code"], outcome["effect_state"]),
    )
    conn.execute("UPDATE v4_case_wallets SET stars = stars - ? WHERE season_id=? AND account_id=?",
                 (step["fee"], season_id, actor))
    after = full_wallet(conn, actor, season_id)
    details = {"gave": item_code, "count": config()["input"], "from_tier": tier,
               "got": outcome["code"], "to_tier": step["to"], "fee": step["fee"]}
    cursor = conn.execute(
        """INSERT INTO v4_economy_operations(season_id, account_id, actor_account_id, operation,
               stars_delta, scans_delta, rep_delta, stars_after, scans_after, rep_after, details_json)
           VALUES (?,?,?,?,?,0,0,?,?,?,?)""",
        (season_id, actor, actor, OPERATION, after["stars"] - before["stars"],
         after["stars"], after["scans"], after["rep"], encoded(details)),
    )
    response = {
        "season_id": season_id,
        "gave": {"code": item_code, "name_ru": item["name_ru"], "count": config()["input"]},
        "got": {"code": outcome["code"], "name_ru": outcome["name_ru"], "tier": step["to"],
                "tier_name": tier_name(step["to"])},
        "fee": step["fee"], "stars": after["stars"], "operation_id": cursor.lastrowid,
    }
    cases.finish(conn, actor, season_id, OPERATION, key, digest, response, request_id)
    return response, False
