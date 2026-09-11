"""Витрина дня: косметика и «+30 минут». Все записи — внутри BEGIN IMMEDIATE.

Витрина — главная трата сезона (V4_GAMES.md §5). Её обещания:

- **Одна на весь сезон-день.** Набор товаров и запас выбираются один раз,
  когда витрину впервые открыли после 07:00 по поясу сезона, и сохраняются в
  базе: перезапуск сервера, второй вожатый или новый участник видят то же.
- **Дефицит настоящий.** У товара 3–5 штук на день; последнюю штуку покупает
  один человек, второй получает «закончилось», даже если нажали одновременно.
- **Покупка — операция журнала.** С защитой от повторной отправки: потерянный
  ответ не спишет ★ дважды.
- **Витрина обновилась — старая покупка не проходит.** Кто держал экран
  открытым с утра вчерашнего дня, получит «витрина уже обновилась», а не
  товар, которого сегодня нет.

Косметика покупается один раз и лежит в `v4_case_inventory` (количество 1);
купон «+30 минут» копится и гасится вожатым (`economy.redeem_walk`).
"""
from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from .cases import CaseError, authorize, encoded, ensure_wallet, replay
from .diary import full_wallet

CATALOGUE_PATH = Path(__file__).parent / "static/app/assets/shop/shop.json"
BUY_OPERATION = "shop.buy"
SLOTS = ("wallpaper", "frame", "sounds")
WALK_CODE = "walk"


def utcnow() -> datetime:
    """Часы витрины. Одна точка, чтобы тесты могли их подменить."""
    return datetime.now(timezone.utc)


@lru_cache(maxsize=1)
def catalogue() -> dict:
    data = json.loads(CATALOGUE_PATH.read_text(encoding="utf-8"))
    codes = set()
    cosmetics = 0
    for item in data["items"]:
        if item["code"] in codes:
            raise ValueError(f"shop.json: повтор товара {item['code']}")
        codes.add(item["code"])
        if type(item["price"]) is not int or item["price"] <= 0:
            raise ValueError(f"shop.json: цена {item['code']} — положительное целое")
        if item["kind"] == "cosmetic":
            cosmetics += 1
            if item["slot"] not in SLOTS:
                raise ValueError(f"shop.json: у {item['code']} неизвестный слот")
            if not data["cosmetic_price_min"] <= item["price"] <= data["cosmetic_price_max"]:
                raise ValueError(f"shop.json: цена {item['code']} вне решения пользователя")
        elif item["kind"] != "coupon" or item["code"] != WALK_CODE:
            raise ValueError(f"shop.json: неизвестный товар {item['code']}")
    if WALK_CODE not in codes:
        raise ValueError("shop.json: нет купона «+30 минут»")
    if cosmetics < data["cosmetics_per_day"]:
        raise ValueError("shop.json: косметики меньше, чем мест на витрине")
    if not 1 <= data["stock_min"] <= data["stock_max"]:
        raise ValueError("shop.json: неверный запас")
    data["catalogue_version"] = hashlib.sha256(encoded(data).encode()).hexdigest()[:16]
    return data


def items_by_code() -> dict[str, dict]:
    return {item["code"]: item for item in catalogue()["items"]}


def _zone(season) -> ZoneInfo:
    return ZoneInfo(season["timezone"] or "Asia/Shanghai")


def shop_day(season, now: datetime | None = None) -> str:
    """День витрины: до 07:00 по поясу сезона ещё идёт вчерашний."""
    local = (now or utcnow()).astimezone(_zone(season))
    return (local - timedelta(hours=catalogue()["refresh_hour"])).date().isoformat()


def refresh_at(season, day: str) -> str:
    """Когда витрина этого дня сменится — в поясе сезона, ISO."""
    start = datetime.fromisoformat(day).replace(tzinfo=_zone(season))
    return (start + timedelta(days=1, hours=catalogue()["refresh_hour"])).isoformat()


def _ensure_stock(conn, season_id: int, day: str) -> None:
    if conn.execute("SELECT 1 FROM v4_shop_stock WHERE season_id=? AND shop_day=? LIMIT 1",
                    (season_id, day)).fetchone():
        return
    data = catalogue()
    # Набор дня выбирает системный жребий, а сохранённая строка делает его
    # неизменным до следующего утра.
    rng = random.SystemRandom()
    cosmetics = [item for item in data["items"] if item["kind"] == "cosmetic"]
    chosen = [items_by_code()[WALK_CODE]] + rng.sample(cosmetics, data["cosmetics_per_day"])
    for item in chosen:
        conn.execute(
            """INSERT OR IGNORE INTO v4_shop_stock(season_id, shop_day, item_code, stock, sold)
               VALUES (?, ?, ?, ?, 0)""",
            (season_id, day, item["code"], rng.randint(data["stock_min"], data["stock_max"])),
        )


def _owned(conn, account_id: int, season_id: int) -> dict[str, int]:
    return {row["item_code"]: int(row["quantity"]) for row in conn.execute(
        "SELECT item_code, quantity FROM v4_case_inventory WHERE season_id=? AND account_id=? AND quantity>0",
        (season_id, account_id))}


def _equipped(conn, account_id: int, season_id: int) -> dict:
    result = {slot: None for slot in SLOTS}
    for row in conn.execute(
        "SELECT slot, item_code FROM v4_cosmetics_equipped WHERE season_id=? AND account_id=?",
        (season_id, account_id),
    ):
        result[row["slot"]] = row["item_code"]
    return result


def state(conn, account_id: int, season_id: int) -> dict:
    """Витрина дня и то, что у человека уже есть."""
    season = authorize(conn, account_id, season_id)
    day = shop_day(season)
    if season["status"] == "active":
        _ensure_stock(conn, season_id, day)
    owned = _owned(conn, account_id, season_id)
    catalogue_items = items_by_code()
    vitrine = []
    for row in conn.execute(
        "SELECT item_code, stock, sold FROM v4_shop_stock WHERE season_id=? AND shop_day=?",
        (season_id, day),
    ):
        item = catalogue_items.get(row["item_code"])
        if item is None:
            continue  # товар убрали из каталога посреди дня — не продаём
        vitrine.append({
            **{k: item[k] for k in ("code", "kind", "slot", "price", "name_ru", "note_ru")},
            "stock": int(row["stock"]),
            "remaining": int(row["stock"]) - int(row["sold"]),
            "owned": owned.get(item["code"], 0),
        })
    vitrine.sort(key=lambda item: (item["kind"] != "coupon", item["price"], item["code"]))
    return {
        "season_id": season_id,
        "season_status": season["status"],
        "shop_day": day,
        "refresh_at": refresh_at(season, day),
        "stars": full_wallet(conn, account_id, season_id)["stars"],
        "vitrine": vitrine,
        "cosmetics": [
            {**{k: catalogue_items[code][k] for k in ("code", "slot", "name_ru", "note_ru")}}
            for code in sorted(owned) if code in catalogue_items and catalogue_items[code]["kind"] == "cosmetic"
        ],
        "walk_coupons": owned.get(WALK_CODE, 0),
        "equipped": _equipped(conn, account_id, season_id),
    }


def buy(conn, actor: int, season_id: int, key: str, item_code: str, day: str, request_id=None):
    authorize(conn, actor, season_id)
    payload = {"season_id": season_id, "item_code": item_code, "shop_day": day}
    key, digest, old = replay(conn, actor, BUY_OPERATION, key, payload)
    if old is not None:
        return old, True
    season = authorize(conn, actor, season_id, write=True)
    today = shop_day(season)
    if day != today:
        raise CaseError("Витрина уже обновилась. Посмотрите, что на ней сегодня.", 409)
    item = items_by_code().get(item_code)
    if item is None:
        raise CaseError("Такого товара нет.", 404)
    _ensure_stock(conn, season_id, today)
    row = conn.execute(
        "SELECT stock, sold FROM v4_shop_stock WHERE season_id=? AND shop_day=? AND item_code=?",
        (season_id, today, item_code),
    ).fetchone()
    if row is None:
        raise CaseError("Этого товара сегодня нет на витрине.", 409)
    owned = _owned(conn, actor, season_id)
    if item["kind"] == "cosmetic" and owned.get(item_code):
        raise CaseError("Это у вас уже есть.", 409)
    ensure_wallet(conn, actor, season_id)
    before = full_wallet(conn, actor, season_id)
    if before["stars"] < item["price"]:
        raise CaseError(f"Не хватает звёзд: нужно {item['price']}★, у вас {before['stars']}★.", 409)
    # Условное списание запаса: последнюю штуку получает один покупатель.
    taken = conn.execute(
        """UPDATE v4_shop_stock SET sold = sold + 1
           WHERE season_id=? AND shop_day=? AND item_code=? AND sold < stock""",
        (season_id, today, item_code),
    ).rowcount
    if taken != 1:
        raise CaseError("Закончилось. Витрина обновится завтра в 07:00.", 409)
    stars_after = before["stars"] - item["price"]
    conn.execute("UPDATE v4_case_wallets SET stars=? WHERE season_id=? AND account_id=?",
                 (stars_after, season_id, actor))
    effect = "active" if item["kind"] == "cosmetic" else "pending"
    conn.execute(
        """INSERT INTO v4_case_inventory(season_id, account_id, item_code, quantity, effect_state)
           VALUES (?,?,?,1,?) ON CONFLICT(season_id, account_id, item_code) DO UPDATE SET quantity=quantity+1""",
        (season_id, actor, item_code, effect),
    )
    details = {"item_code": item_code, "price": item["price"], "shop_day": today,
               "catalogue_version": catalogue()["catalogue_version"]}
    cursor = conn.execute(
        """INSERT INTO v4_economy_operations(season_id, account_id, actor_account_id, operation,
               stars_delta, scans_delta, rep_delta, stars_after, scans_after, rep_after, details_json)
           VALUES (?,?,?,?,?,0,0,?,?,?,?)""",
        (season_id, actor, actor, BUY_OPERATION, -item["price"], stars_after, before["scans"], before["rep"],
         encoded(details)),
    )
    remaining = conn.execute(
        "SELECT stock - sold FROM v4_shop_stock WHERE season_id=? AND shop_day=? AND item_code=?",
        (season_id, today, item_code),
    ).fetchone()[0]
    response = {"season_id": season_id, "item_code": item_code, "price": item["price"], "shop_day": today,
                "stars": stars_after, "remaining": int(remaining), "operation_id": cursor.lastrowid}
    serialized = encoded(response)
    conn.execute(
        """INSERT INTO v4_idempotency_keys(account_id, operation, idempotency_key,
               request_hash, response_status, response_json) VALUES (?,?,?,?,200,?)""",
        (actor, BUY_OPERATION, key, digest, serialized),
    )
    conn.execute(
        """INSERT INTO v4_audit_log(actor_account_id, season_id, action, entity_type,
               entity_id, request_id, after_json, metadata_json) VALUES (?,?,?,'shop',?,?,?,?)""",
        (actor, season_id, BUY_OPERATION, item_code, request_id, serialized, encoded({"idempotency_key": key})),
    )
    return response, False


def equip(conn, actor: int, season_id: int, slot: str, item_code: str | None) -> dict:
    authorize(conn, actor, season_id, write=True)
    if slot not in SLOTS:
        raise CaseError("Такого места для косметики нет.")
    if item_code is None:
        conn.execute("DELETE FROM v4_cosmetics_equipped WHERE season_id=? AND account_id=? AND slot=?",
                     (season_id, actor, slot))
    else:
        item = items_by_code().get(item_code)
        if item is None or item["kind"] != "cosmetic" or item["slot"] != slot:
            raise CaseError("Этот предмет сюда не надевается.")
        if not _owned(conn, actor, season_id).get(item_code):
            raise CaseError("Сначала купите этот предмет.", 409)
        conn.execute(
            """INSERT INTO v4_cosmetics_equipped(season_id, account_id, slot, item_code) VALUES (?,?,?,?)
               ON CONFLICT(season_id, account_id, slot) DO UPDATE SET item_code=excluded.item_code""",
            (season_id, actor, slot, item_code),
        )
    return {"season_id": season_id, "equipped": _equipped(conn, actor, season_id)}


def frames_for(conn, account_ids) -> dict[int, str]:
    """Надетые рамки — чтобы их видели другие в рейтингах и за игровым столом.

    Берётся активный сезон каждого человека: за игровым столом сезонов нет, а
    рамка покупалась в сезоне."""
    ids = sorted({int(i) for i in account_ids})
    if not ids:
        return {}
    marks = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"""SELECT e.account_id, e.item_code FROM v4_cosmetics_equipped e
            JOIN v4_seasons s ON s.id = e.season_id AND s.status = 'active'
            JOIN v4_season_memberships m ON m.season_id = e.season_id AND m.account_id = e.account_id
                 AND m.status = 'active'
            WHERE e.slot = 'frame' AND e.account_id IN ({marks})
            ORDER BY e.season_id""",
        ids,
    ).fetchall()
    return {int(row["account_id"]): row["item_code"] for row in rows}
