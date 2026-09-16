"""Мастерская дубликатов (V4_GAMES.md §4.8). Все записи — внутри BEGIN IMMEDIATE.

Решения пользователя 2026-09-17 (заменяют решения 2026-09-12):

- четыре одинаковых редких импланта → один новый имплант, гарантированно,
  без сбора звёзд;
- исход детерминирован: у каждого базового импланта ровно один целевой
  предмет, не случайный выбор внутри ступени, как было раньше;
- шесть новых имплантов (Чжуцюэ, Цзинь Чань, Мяньцзы, Кои, Тайцзи, Бяньцай)
  заменяют прежние Нефритовый страж/Дипломат/Золотой нексус — те в мастерской
  больше не собираются, их коды и картинки в репозитории остаются нетронуты.
- переплавка — один рецепт за раз.

Числа и рецепты живут в assets/workshop/workshop.json, чтобы экран и сервер
не разошлись. Купон «+30 минут» в мастерскую не принимается — его гасит
вожатый, а не переплавка; в списке рецептов его код и не встречается.
"""
from __future__ import annotations

import json
from functools import lru_cache

from . import cases
from .cases import CaseError, authorize, encoded, ensure_wallet, replay
from .diary import full_wallet

OPERATION = "workshop.craft"


@lru_cache(maxsize=1)
def config() -> dict:
    data = json.loads(cases.WORKSHOP_PATH.read_text(encoding="utf-8"))
    if type(data["input"]) is not int or data["input"] < 2:
        raise ValueError("workshop.json: неверный курс")
    codes = {item["code"] for item in data["items"]}
    seen_from = set()
    for recipe in data["recipes"]:
        if recipe["from"] in seen_from:
            raise ValueError(f"workshop.json: у {recipe['from']} два рецепта")
        seen_from.add(recipe["from"])
        if recipe["to"] not in codes:
            raise ValueError(f"workshop.json: у рецепта нет предмета {recipe['to']}")
    return data


def items_by_code() -> dict[str, dict]:
    """Только новые, собираемые в мастерской предметы (не источники)."""
    return {item["code"]: item for item in config()["items"]}


def recipe_for(item_code: str) -> dict | None:
    return next((recipe for recipe in config()["recipes"] if recipe["from"] == item_code), None)


def quantity(conn, account_id: int, season_id: int, code: str) -> int:
    row = conn.execute(
        "SELECT quantity FROM v4_case_inventory WHERE season_id=? AND account_id=? AND item_code=?",
        (season_id, account_id, code),
    ).fetchone()
    return int(row["quantity"]) if row else 0


def state(conn, account_id: int, season_id: int) -> dict:
    """Что человек может переплавить сейчас и чего ему не хватает."""
    season = authorize(conn, account_id, season_id)
    need = config()["input"]
    source_names = cases.items_by_code()
    target_names = items_by_code()
    recipes = []
    for row in conn.execute(
        "SELECT item_code, quantity FROM v4_case_inventory WHERE season_id=? AND account_id=? AND quantity>0",
        (season_id, account_id),
    ):
        recipe = recipe_for(row["item_code"])
        if not recipe:
            continue
        count = int(row["quantity"])
        target = target_names[recipe["to"]]
        recipes.append({
            "code": row["item_code"], "name_ru": source_names[row["item_code"]]["name_ru"],
            "quantity": count, "ready": count >= need, "missing": max(0, need - count),
            "to_code": recipe["to"], "to_name_ru": target["name_ru"], "to_name_zh": target.get("name_zh", ""),
        })
    recipes.sort(key=lambda r: (not r["ready"], r["code"]))
    return {"season_id": season_id, "season_status": season["status"],
            "stars": full_wallet(conn, account_id, season_id)["stars"],
            "input": need, "recipes": recipes}


def craft(conn, actor: int, season_id: int, item_code: str, key: str, request_id=None):
    authorize(conn, actor, season_id)
    key, digest, old = replay(conn, actor, OPERATION, key, {"season_id": season_id, "item_code": item_code})
    if old is not None:
        return old, True
    authorize(conn, actor, season_id, write=True)
    recipe = recipe_for(item_code)
    if not recipe:
        raise CaseError("Этот предмет в мастерской не переплавляется.")
    need = config()["input"]
    if quantity(conn, actor, season_id, item_code) < need:
        raise CaseError(f"Нужно {need} одинаковых.", 409)
    ensure_wallet(conn, actor, season_id)

    target_code = recipe["to"]
    target = items_by_code()[target_code]
    conn.execute("UPDATE v4_case_inventory SET quantity = quantity - ? WHERE season_id=? AND account_id=? AND item_code=?",
                 (need, season_id, actor, item_code))
    conn.execute(
        """INSERT INTO v4_case_inventory(season_id, account_id, item_code, quantity, effect_state)
           VALUES (?,?,?,1,?) ON CONFLICT(season_id, account_id, item_code) DO UPDATE SET quantity = quantity + 1""",
        (season_id, actor, target_code, target["effect_state"]),
    )
    after = full_wallet(conn, actor, season_id)
    details = {"gave": item_code, "count": need, "got": target_code}
    cursor = conn.execute(
        """INSERT INTO v4_economy_operations(season_id, account_id, actor_account_id, operation,
               stars_delta, scans_delta, rep_delta, stars_after, scans_after, rep_after, details_json)
           VALUES (?,?,?,?,0,0,0,?,?,?,?)""",
        (season_id, actor, actor, OPERATION, after["stars"], after["scans"], after["rep"], encoded(details)),
    )
    response = {
        "season_id": season_id,
        "gave": {"code": item_code, "name_ru": cases.items_by_code()[item_code]["name_ru"], "count": need},
        "got": {"code": target_code, "name_ru": target["name_ru"], "name_zh": target.get("name_zh", "")},
        "stars": after["stars"], "operation_id": cursor.lastrowid,
    }
    cases.finish(conn, actor, season_id, OPERATION, key, digest, response, request_id)
    return response, False
