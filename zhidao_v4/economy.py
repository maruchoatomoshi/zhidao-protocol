"""Экономика сезона: панель для вожатых и погашение купонов «+30 минут».

Панель отвечает на один вопрос из решения об экономике (V4_GAMES.md §5):
тратятся ли звёзды или копятся. Поэтому в ней не «всё про деньги», а ровно
то, по чему накопление видно на третий день, а не в конце поездки: сколько ★
выпущено и сожжено по дням, средний и медианный баланс, какая доля звёзд у
первых десяти и какая часть заработанного потрачена.

Всё считается из журнала экономики и кошельков; ничего не хранится отдельно и
не может разойтись с тем, что на самом деле произошло.

Купон «+30 минут свободы» — единственная трата в реальной жизни. Гасит его
вожатый, когда участник приходит отпроситься; погашение — операция журнала
без движения ★, с защитой от повторной отправки и записью в аудит.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from statistics import median
from zoneinfo import ZoneInfo

from .cases import CaseError, authorize, encoded, ensure_wallet, replay
from .diary import full_wallet

WALK_CODE = "walk"
REDEEM_OPERATION = "coupon.redeem"
# Накопление: за три дня с операциями потрачено меньше трети заработанного.
HOARDING_DAYS = 3
HOARDING_RATIO = 0.3
# Доля первых десяти имеет смысл, только когда участников больше десяти.
TOP = 10


def _local_day(created_at: str, tz) -> str:
    moment = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(tz).date().isoformat()


def overview(conn, actor: int, season_id: int) -> dict:
    season = authorize(conn, actor, season_id, manage=True)
    tz = ZoneInfo(season["timezone"] or "Asia/Shanghai")
    members = conn.execute(
        """SELECT a.id, COALESCE(w.stars, 0) AS stars
           FROM v4_season_memberships m JOIN v4_accounts a ON a.id = m.account_id
           LEFT JOIN v4_case_wallets w ON w.season_id = m.season_id AND w.account_id = m.account_id
           WHERE m.season_id = ? AND m.status IN ('active', 'completed')""",
        (season_id,),
    ).fetchall()
    balances = sorted((int(row["stars"]) for row in members), reverse=True)
    total = sum(balances)

    def bucket():
        return {"minted": 0, "burned": 0, "operations": 0}

    days = defaultdict(bucket)
    sources = defaultdict(bucket)
    for row in conn.execute(
        "SELECT created_at, operation, stars_delta FROM v4_economy_operations WHERE season_id = ?",
        (season_id,),
    ):
        delta = int(row["stars_delta"])
        for target in (days[_local_day(row["created_at"], tz)], sources[row["operation"]]):
            target["operations"] += 1
            if delta > 0:
                target["minted"] += delta
            elif delta < 0:
                target["burned"] -= delta

    earned = sum(day["minted"] for day in days.values())
    spent = sum(day["burned"] for day in days.values())
    ratio = round(spent / earned, 3) if earned else None
    coupons = conn.execute(
        """SELECT a.id AS account_id, a.display_name, i.quantity
           FROM v4_case_inventory i
           JOIN v4_accounts a ON a.id = i.account_id
           JOIN v4_season_memberships m ON m.season_id = i.season_id AND m.account_id = i.account_id
           WHERE i.season_id = ? AND i.item_code = ? AND i.quantity > 0 AND m.status = 'active'
           ORDER BY a.display_name, a.id""",
        (season_id, WALK_CODE),
    ).fetchall()
    return {
        "season_id": season_id,
        "season_name": season["name"],
        "season_status": season["status"],
        "today": datetime.now(tz).date().isoformat(),
        "members": len(balances),
        "stars_total": total,
        "stars_average": round(total / len(balances), 1) if balances else None,
        "stars_median": median(balances) if balances else None,
        "top10_share": round(sum(balances[:TOP]) / total, 3) if total and len(balances) > TOP else None,
        "earned": earned,
        "spent": spent,
        "spent_ratio": ratio,
        "hoarding": len(days) >= HOARDING_DAYS and ratio is not None and ratio < HOARDING_RATIO,
        "days": [{"date": day, **values, "net": values["minted"] - values["burned"]}
                 for day, values in sorted(days.items(), reverse=True)[:14]],
        "sources": [{"operation": name, **values} for name, values in sorted(sources.items())],
        "coupons": [dict(row) for row in coupons],
    }


def redeem_walk(conn, actor: int, season_id: int, key: str, account_id: int, request_id=None):
    authorize(conn, actor, season_id, manage=True)
    key, digest, old = replay(conn, actor, REDEEM_OPERATION, key,
                              {"season_id": season_id, "account_id": account_id})
    if old is not None:
        return old, True
    authorize(conn, actor, season_id, manage=True, write=True)
    authorize(conn, account_id, season_id, write=True)
    row = conn.execute(
        "SELECT quantity FROM v4_case_inventory WHERE season_id=? AND account_id=? AND item_code=?",
        (season_id, account_id, WALK_CODE),
    ).fetchone()
    if not row or row["quantity"] <= 0:
        raise CaseError("У участника нет купона «+30 минут».", 409)
    conn.execute(
        "UPDATE v4_case_inventory SET quantity = quantity - 1 WHERE season_id=? AND account_id=? AND item_code=?",
        (season_id, account_id, WALK_CODE),
    )
    ensure_wallet(conn, account_id, season_id)
    wallet = full_wallet(conn, account_id, season_id)
    details = {"item_code": WALK_CODE, "minutes": 30, "quantity_after": row["quantity"] - 1}
    cursor = conn.execute(
        """INSERT INTO v4_economy_operations(season_id, account_id, actor_account_id, operation,
               stars_delta, scans_delta, rep_delta, stars_after, scans_after, rep_after, details_json)
           VALUES (?,?,?,?,0,0,0,?,?,?,?)""",
        (season_id, account_id, actor, REDEEM_OPERATION, wallet["stars"], wallet["scans"], wallet["rep"],
         encoded(details)),
    )
    response = {"season_id": season_id, "account_id": account_id, "operation_id": cursor.lastrowid,
                "quantity": row["quantity"] - 1}
    serialized = encoded(response)
    conn.execute(
        """INSERT INTO v4_idempotency_keys(account_id, operation, idempotency_key,
               request_hash, response_status, response_json) VALUES (?,?,?,?,200,?)""",
        (actor, REDEEM_OPERATION, key, digest, serialized),
    )
    conn.execute(
        """INSERT INTO v4_audit_log(actor_account_id, season_id, action, entity_type,
               entity_id, request_id, after_json, metadata_json) VALUES (?,?,?,'coupon',?,?,?,?)""",
        (actor, season_id, REDEEM_OPERATION, str(account_id), request_id, serialized,
         encoded({"idempotency_key": key})),
    )
    return response, False
