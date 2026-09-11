"""Оценка бумажного дневника. Все записи — внутри BEGIN IMMEDIATE вызывающего.

Дневник пишут на бумаге; вожатый ставит за день 0–3 звезды и бонус. Оценка
приносит REP и ★ по `diary.json` и первую за день попытку кейса за 3 звезды.

Три вещи, которые модуль обещает:

- **Начисляется разница, а не сумма.** Переоценка 2★ → 3★ добавляет разницу
  наград; каждая правка — отдельная операция журнала, прошлое не
  переписывается.
- **Два вожатых не перезаписывают друг друга молча.** Правка несёт ревизию,
  которую видел вожатый; устаревшая ревизия получает 409.
- **★ не уходят в минус.** Если оценку снизили, а звёзды уже потрачены, баланс
  останавливается на нуле, и журнал записывает фактическое списание. REP
  списывается полностью: он не тратится и не может «кончиться».

Бонусы карт и имплантов сезона 1 (Linguasoft, Literature, Star) сюда не
перенесены: эффекты имплантов в V4 ещё не подключены, а по решению об
экономике (V4_GAMES.md §5) они станут бонусами к действиям позже.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from .cases import CaseError, authorize, can_manage, encoded, ensure_wallet, replay

RULES_PATH = Path(__file__).parent / "static/app/assets/diary/diary.json"
OPERATION = "diary.rate"
SCAN_CAP = 7
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@lru_cache(maxsize=1)
def rules() -> dict:
    data = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    for key in ("rep", "stars"):
        values = data[key]
        if (len(values) != 4 or any(type(v) is not int for v in values) or values[0] != 0
                or values != sorted(values)):
            raise ValueError(f"diary.json: {key} должен быть четырьмя растущими целыми от 0")
    for key in ("rep_bonus", "stars_bonus"):
        if type(data[key]) is not int or data[key] < 0:
            raise ValueError(f"diary.json: {key} должен быть неотрицательным целым")
    if data["scan_for_three_stars"] not in (0, 1):
        raise ValueError("diary.json: scan_for_three_stars — 0 или 1")
    data["rules_version"] = hashlib.sha256(encoded(data).encode()).hexdigest()[:16]
    return data


def reward(stars: int, bonus: bool) -> dict:
    r = rules()
    return {
        "rep": r["rep"][stars] + (r["rep_bonus"] if bonus else 0),
        "stars": r["stars"][stars] + (r["stars_bonus"] if bonus else 0),
    }


def season_today(season) -> date:
    return datetime.now(ZoneInfo(season["timezone"] or "Asia/Shanghai")).date()


def check_date(season, value: str) -> str:
    if not isinstance(value, str) or not DATE_RE.fullmatch(value):
        raise CaseError("Дата дневника — в формате ГГГГ-ММ-ДД.")
    try:
        day = date.fromisoformat(value)
    except ValueError as exc:
        raise CaseError("Такой даты нет.") from exc
    if day > season_today(season):
        # Бумажный дневник за завтра ещё не написан.
        raise CaseError("Нельзя оценить дневник за день, который ещё не наступил.")
    if season["starts_on"] and value < season["starts_on"]:
        raise CaseError("Эта дата раньше начала сезона.")
    if season["ends_on"] and value > season["ends_on"]:
        raise CaseError("Эта дата позже конца сезона.")
    return value


def full_wallet(conn, account_id: int, season_id: int) -> dict:
    row = conn.execute(
        "SELECT stars, scans, rep FROM v4_case_wallets WHERE season_id=? AND account_id=?",
        (season_id, account_id),
    ).fetchone()
    return dict(row) if row else {"stars": 0, "scans": 0, "rep": 0}


def _rating(conn, season_id: int, account_id: int, entry_date: str):
    return conn.execute(
        """SELECT r.*, a.display_name AS rated_by_name FROM v4_diary_ratings r
           JOIN v4_accounts a ON a.id = r.rated_by_account_id
           WHERE r.season_id=? AND r.account_id=? AND r.entry_date=?""",
        (season_id, account_id, entry_date),
    ).fetchone()


def day(conn, actor: int, season_id: int, entry_date: str | None) -> dict:
    season = authorize(conn, actor, season_id, manage=True)
    entry_date = check_date(season, entry_date or season_today(season).isoformat())
    rows = conn.execute(
        """SELECT a.id AS account_id, a.display_name, g.name AS group_name,
                  r.stars, r.bonus, r.revision, r.rated_at, rater.display_name AS rated_by_name
           FROM v4_season_memberships m
           JOIN v4_accounts a ON a.id = m.account_id
           LEFT JOIN v4_group_memberships gm ON gm.season_membership_id = m.id AND gm.left_at IS NULL
                AND gm.membership_role IN ('member', 'leader')
           LEFT JOIN v4_groups g ON g.id = gm.group_id
           LEFT JOIN v4_diary_ratings r ON r.season_id = m.season_id AND r.account_id = m.account_id
                AND r.entry_date = ?
           LEFT JOIN v4_accounts rater ON rater.id = r.rated_by_account_id
           WHERE m.season_id = ? AND m.status = 'active' AND a.status = 'active'
           ORDER BY g.name IS NULL, g.name, a.display_name, a.id""",
        (entry_date, season_id),
    ).fetchall()
    return {
        "season_id": season_id,
        "season_status": season["status"],
        "entry_date": entry_date,
        "today": season_today(season).isoformat(),
        "members": [
            {
                "account_id": row["account_id"],
                "display_name": row["display_name"],
                "group": row["group_name"],
                "stars": row["stars"] or 0,
                "bonus": bool(row["bonus"]),
                "revision": row["revision"] or 0,
                "rated_at": row["rated_at"],
                "rated_by": row["rated_by_name"],
            }
            for row in rows
        ],
    }


def rate(conn, actor: int, season_id: int, key: str, account_id: int, entry_date: str,
         stars: int, bonus: bool, expected_revision: int, request_id=None):
    authorize(conn, actor, season_id, manage=True)
    payload = {"season_id": season_id, "account_id": account_id, "entry_date": entry_date,
               "stars": stars, "bonus": bonus, "expected_revision": expected_revision}
    key, digest, old = replay(conn, actor, OPERATION, key, payload)
    if old is not None:
        return old, True
    season = authorize(conn, actor, season_id, manage=True, write=True)
    entry_date = check_date(season, entry_date)
    if stars not in (0, 1, 2, 3):
        raise CaseError("Оценка — от 0 до 3 звёзд.")
    authorize(conn, account_id, season_id, write=True)

    current = _rating(conn, season_id, account_id, entry_date)
    if (current["revision"] if current else 0) != expected_revision:
        raise CaseError(
            f"Оценку уже изменил(а) {current['rated_by_name'] if current else 'другой вожатый'}. Обновите список.",
            409,
        )
    previous = {"stars": current["stars"], "bonus": bool(current["bonus"])} if current else {"stars": 0, "bonus": False}
    if current and previous == {"stars": stars, "bonus": bool(bonus)}:
        response = {"season_id": season_id, "account_id": account_id, "entry_date": entry_date,
                    "stars": stars, "bonus": bool(bonus), "revision": current["revision"],
                    "changed": False, "operation_id": None,
                    "wallet": full_wallet(conn, account_id, season_id)}
        _finish(conn, actor, season_id, key, digest, response, request_id)
        return response, False

    old_reward = reward(previous["stars"], previous["bonus"])
    new_reward = reward(stars, bool(bonus))
    ensure_wallet(conn, account_id, season_id)
    before = full_wallet(conn, account_id, season_id)
    wanted_stars = before["stars"] + new_reward["stars"] - old_reward["stars"]
    already_scanned = bool(current and current["scan_granted"])
    grant_scan = stars == 3 and not already_scanned and rules()["scan_for_three_stars"] == 1
    after = {
        "stars": max(0, wanted_stars),
        "scans": min(SCAN_CAP, before["scans"] + (1 if grant_scan else 0)),
        "rep": before["rep"] + new_reward["rep"] - old_reward["rep"],
    }
    scan_granted = int(already_scanned or grant_scan)

    if current:
        conn.execute(
            """UPDATE v4_diary_ratings SET stars=?, bonus=?, scan_granted=?, revision=revision+1,
                   rated_by_account_id=?, rated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
               WHERE season_id=? AND account_id=? AND entry_date=?""",
            (stars, int(bool(bonus)), scan_granted, actor, season_id, account_id, entry_date),
        )
    else:
        conn.execute(
            """INSERT INTO v4_diary_ratings(season_id, account_id, entry_date, stars, bonus,
                   scan_granted, rated_by_account_id) VALUES (?,?,?,?,?,?,?)""",
            (season_id, account_id, entry_date, stars, int(bool(bonus)), scan_granted, actor),
        )
    conn.execute(
        "UPDATE v4_case_wallets SET stars=?, scans=?, rep=? WHERE season_id=? AND account_id=?",
        (after["stars"], after["scans"], after["rep"], season_id, account_id),
    )
    details = {
        "entry_date": entry_date,
        "stars": stars,
        "bonus": bool(bonus),
        "previous": previous,
        "reward": new_reward,
        "previous_reward": old_reward,
        # Списание упёрлось в ноль: часть звёзд человек уже потратил.
        "stars_clamped": wanted_stars < 0,
        "scan_granted": grant_scan,
        "scan_capped": grant_scan and after["scans"] == before["scans"],
        "rules_version": rules()["rules_version"],
    }
    cursor = conn.execute(
        """INSERT INTO v4_economy_operations(season_id, account_id, actor_account_id, operation,
               stars_delta, scans_delta, rep_delta, stars_after, scans_after, rep_after, details_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (season_id, account_id, actor, OPERATION, after["stars"] - before["stars"],
         after["scans"] - before["scans"], after["rep"] - before["rep"],
         after["stars"], after["scans"], after["rep"], encoded(details)),
    )
    revision = _rating(conn, season_id, account_id, entry_date)["revision"]
    response = {
        "season_id": season_id, "account_id": account_id, "entry_date": entry_date,
        "stars": stars, "bonus": bool(bonus), "revision": revision, "changed": True,
        "operation_id": cursor.lastrowid,
        "rep_delta": after["rep"] - before["rep"],
        "stars_delta": after["stars"] - before["stars"],
        "scans_delta": after["scans"] - before["scans"],
        "stars_clamped": details["stars_clamped"],
        "wallet": after,
    }
    _finish(conn, actor, season_id, key, digest, response, request_id)
    return response, False


def _finish(conn, actor, season_id, key, digest, response, request_id):
    serialized = encoded(response)
    conn.execute(
        """INSERT INTO v4_idempotency_keys(account_id, operation, idempotency_key,
               request_hash, response_status, response_json) VALUES (?,?,?,?,200,?)""",
        (actor, OPERATION, key, digest, serialized),
    )
    conn.execute(
        """INSERT INTO v4_audit_log(actor_account_id, season_id, action, entity_type,
               entity_id, request_id, after_json, metadata_json) VALUES (?,?,?,'diary',?,?,?,?)""",
        (actor, season_id, OPERATION, f"{response['account_id']}:{response['entry_date']}",
         request_id, serialized, encoded({"idempotency_key": key})),
    )


def mine(conn, actor: int, season_id: int) -> dict:
    season = authorize(conn, actor, season_id)
    rows = conn.execute(
        """SELECT entry_date, stars, bonus FROM v4_diary_ratings
           WHERE season_id=? AND account_id=? ORDER BY entry_date DESC""",
        (season_id, actor),
    ).fetchall()
    items = []
    for row in rows:
        items.append({"entry_date": row["entry_date"], "stars": row["stars"], "bonus": bool(row["bonus"]),
                      **{f"{k}_reward": v for k, v in reward(row["stars"], bool(row["bonus"])).items()}})
    return {
        "season_id": season_id,
        "season_status": season["status"],
        "items": items,
        "total_stars": sum(i["stars"] for i in items),
        "days_rated": sum(1 for i in items if i["stars"] or i["bonus"]),
        "bonus_count": sum(1 for i in items if i["bonus"]),
        "rep": full_wallet(conn, actor, season_id)["rep"],
    }


def leaderboard(conn, actor: int, season_id: int) -> dict:
    """Дневниковый рейтинг сезона: как в сезоне 1, видят все участники.

    Показываются только имя и итоги, без оценок по дням: подробности своих
    оценок человек видит у себя, чужие — только вожатые."""
    authorize(conn, actor, season_id, manage=can_manage(conn, actor, season_id))
    rows = conn.execute(
        """SELECT a.id AS account_id, a.display_name,
                  COALESCE(SUM(r.stars), 0) AS total_stars,
                  COUNT(CASE WHEN r.stars > 0 OR r.bonus > 0 THEN 1 END) AS days_rated,
                  COALESCE(SUM(r.bonus), 0) AS bonus_count,
                  (SELECT COALESCE(SUM(o.rep_delta), 0) FROM v4_economy_operations o
                    WHERE o.season_id = m.season_id AND o.account_id = m.account_id
                      AND o.operation = 'diary.rate') AS diary_rep
           FROM v4_season_memberships m
           JOIN v4_accounts a ON a.id = m.account_id
           LEFT JOIN v4_diary_ratings r ON r.season_id = m.season_id AND r.account_id = m.account_id
           WHERE m.season_id = ? AND m.status IN ('active', 'completed') AND a.status = 'active'
           GROUP BY m.id
           ORDER BY total_stars DESC, days_rated DESC, bonus_count DESC, a.display_name, a.id""",
        (season_id,),
    ).fetchall()
    # Импорт здесь, а не наверху: витрина сама пользуется кошельком из этого модуля.
    from .shop import frames_for

    frames = frames_for(conn, [row["account_id"] for row in rows])
    return {
        "season_id": season_id,
        "items": [{**dict(row), "is_you": row["account_id"] == actor, "frame": frames.get(row["account_id"])}
                  for row in rows],
    }
