"""Метки на карте (V4_GAMES.md §4.2). Все записи — внутри BEGIN IMMEDIATE.

По мотивам Dark Souls: метку собирают из готовых слов — шаблон и слово
(«Осторожно: геккон 壁虎») — и оставляют там, где стоят. Её видят все в сезоне
на открытом участке тумана и могут отметить полезной.

Решения пользователя 2026-09-12: первая метка за сезон-день бесплатно,
следующие — по 5★; не больше трёх в день; метка живёт двое суток, каждая
отметка «полезно» продлевает её на 12 часов, но не дольше недели с появления.
Вожатый может скрыть метку. Словарь — assets/campus/marks.json.

Приватность — главное обещание механики. В таблице меток нет автора, время
появления округлено до часа. Дневной лимит считает отдельная таблица
«человек — день — сколько», без ссылки на метку. Ответ, сохраняемый для
повтора запроса, не содержит ни метки, ни места. Честная оговорка: платная
метка оставляет строку в журнале экономики со временем, и если в этот час
метка была одна, их можно сопоставить. Кто отметил «полезно», хранится ровно
столько, сколько живёт метка, — чтобы нельзя было голосовать дважды.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

from . import campus, cases, rooms, shop
from .cases import CaseError, authorize, encoded, ensure_wallet, replay
from .diary import full_wallet

DICTIONARY_PATH = Path(__file__).parent / "static" / "app" / "assets" / "campus" / "marks.json"
DAILY_LIMIT = 3
FREE_PER_DAY = 1
PRICE = 5
LIFETIME_HOURS = 48
USEFUL_BONUS_HOURS = 12
MAX_LIFETIME_HOURS = 24 * 7
OPERATION = "map.mark"


def utcnow():
    # Те же часы, что у витрины: сезон-день начинается в 07:00 по поясу сезона.
    return shop.utcnow()


@lru_cache(maxsize=1)
def dictionary() -> dict:
    data = json.loads(DICTIONARY_PATH.read_text(encoding="utf-8"))
    result = {}
    for part in ("templates", "words"):
        codes = [entry["code"] for entry in data[part]]
        if not codes or len(codes) != len(set(codes)):
            raise ValueError(f"marks.json: раздел {part} пуст или с повторами")
        for entry in data[part]:
            if not all(entry.get(key) for key in ("ru", "zh", "pinyin")):
                raise ValueError(f"marks.json: у {entry['code']} нет ru, zh или pinyin")
        result[part] = {entry["code"]: entry for entry in data[part]}
    return result


def known(template_code: str, word_code: str) -> bool:
    return template_code in dictionary()["templates"] and word_code in dictionary()["words"]


def text_of(template_code: str, word_code: str) -> dict:
    template = dictionary()["templates"][template_code]
    word = dictionary()["words"][word_code]
    return {"ru": f"{template['ru']} {word['ru']}", "zh": f"{template['zh']}{word['zh']}",
            "pinyin": f"{template['pinyin']} {word['pinyin']}"}


def purge(conn, season_id: int, now) -> None:
    """Истёкшие метки удаляются вместе с голосами — социальные данные не живут дольше метки."""
    stale = "SELECT id FROM v4_map_marks WHERE season_id=? AND expires_at <= ?"
    conn.execute(f"DELETE FROM v4_map_mark_votes WHERE mark_id IN ({stale})", (season_id, rooms.iso(now)))
    conn.execute("DELETE FROM v4_map_marks WHERE season_id=? AND expires_at <= ?", (season_id, rooms.iso(now)))


def used_today(conn, season_id: int, account_id: int, day: str) -> int:
    row = conn.execute("SELECT used FROM v4_map_mark_quota WHERE season_id=? AND account_id=? AND mark_day=?",
                       (season_id, account_id, day)).fetchone()
    return int(row["used"]) if row else 0


def quota_view(used: int, stars: int) -> dict:
    left = max(0, DAILY_LIMIT - used)
    next_price = None if not left else (0 if used < FREE_PER_DAY else PRICE)
    return {"used": used, "limit": DAILY_LIMIT, "left": left, "next_price": next_price, "stars": stars}


def mark_view(row, voted: bool) -> dict:
    lon, lat = campus.cell_centre(int(row["cell_lon"]), int(row["cell_lat"]))
    return {"id": int(row["id"]), "coordinates": [lon, lat], "text": text_of(row["template_code"], row["word_code"]),
            "useful": int(row["useful"]), "voted": voted, "expires_at": row["expires_at"],
            "hidden": row["hidden_at"] is not None}


def view(conn, account_id: int, season_id: int) -> dict:
    """Живые метки сезона на открытых клетках. Вожатый видит и скрытые."""
    season = conn.execute("SELECT * FROM v4_seasons WHERE id=?", (season_id,)).fetchone()
    staff = cases.can_manage(conn, account_id, season_id)
    now = utcnow()
    rows = conn.execute(
        """SELECT m.*, EXISTS(SELECT 1 FROM v4_map_mark_votes v WHERE v.mark_id = m.id AND v.account_id = ?) AS voted
           FROM v4_map_marks m
           JOIN v4_campus_cells c ON c.season_id = m.season_id AND c.cell_lon = m.cell_lon AND c.cell_lat = m.cell_lat
           WHERE m.season_id = ? AND m.expires_at > ? AND (m.hidden_at IS NULL OR ?)
           ORDER BY m.id""",
        (account_id, season_id, rooms.iso(now), 1 if staff else 0),
    ).fetchall()
    marks = [mark_view(row, bool(row["voted"])) for row in rows if known(row["template_code"], row["word_code"])]
    member = conn.execute("SELECT status FROM v4_season_memberships WHERE season_id=? AND account_id=?",
                          (season_id, account_id)).fetchone()
    quota = None
    if member and member["status"] == "active":
        quota = quota_view(used_today(conn, season_id, account_id, shop.shop_day(season, now)),
                           full_wallet(conn, account_id, season_id)["stars"])
    return {"season_id": season_id, "season_status": season["status"], "marks": marks, "quota": quota,
            "can_moderate": staff}


def place(conn, actor: int, season_id: int, *, lon: float, lat: float, accuracy_m: float,
          template: str, word: str, key: str, request_id=None):
    authorize(conn, actor, season_id)
    # Координаты в отпечаток не входят: при повторе GPS отдаст чуть другую точку.
    key, digest, old = replay(conn, actor, OPERATION, key, {"season_id": season_id, "template": template, "word": word})
    if old is not None:
        return old, True
    season = authorize(conn, actor, season_id, write=True)
    if not known(template, word):
        raise CaseError("Такой фразы нет в словаре меток.")
    if accuracy_m is None or accuracy_m > campus.MAX_ACCURACY_M:
        raise CaseError("Нужна точная позиция: выйдите под открытое небо и попробуйте ещё раз.")
    if not campus.inside_campus(lon, lat):
        raise CaseError("Метку можно оставить только на территории кампуса.")
    now = utcnow()
    purge(conn, season_id, now)
    day = shop.shop_day(season, now)
    used = used_today(conn, season_id, actor, day)
    if used >= DAILY_LIMIT:
        raise CaseError(f"Сегодня уже {DAILY_LIMIT} метки. Завтра можно снова.", 409)
    fee = 0 if used < FREE_PER_DAY else PRICE
    ensure_wallet(conn, actor, season_id)
    before = full_wallet(conn, actor, season_id)
    if before["stars"] < fee:
        raise CaseError(f"Не хватает звёзд: метка стоит {fee}★, у вас {before['stars']}★.", 409)

    # Метка открывает клетку тумана там, где стоят.
    campus.record_visit(conn, season_id, lon=lon, lat=lat, accuracy_m=accuracy_m)
    after = before
    if fee:
        conn.execute("UPDATE v4_case_wallets SET stars = stars - ? WHERE season_id=? AND account_id=?",
                     (fee, season_id, actor))
        after = full_wallet(conn, actor, season_id)
        # В журнале и аудите — только день и сумма: ни клетки, ни метки.
        conn.execute(
            """INSERT INTO v4_economy_operations(season_id, account_id, actor_account_id, operation,
                   stars_delta, scans_delta, rep_delta, stars_after, scans_after, rep_after, details_json)
               VALUES (?,?,?,?,?,0,0,?,?,?,?)""",
            (season_id, actor, actor, OPERATION, -fee, after["stars"], after["scans"], after["rep"],
             encoded({"day": day, "fee": fee})),
        )
        conn.execute(
            """INSERT INTO v4_audit_log(actor_account_id, season_id, action, entity_type, entity_id, request_id, after_json)
               VALUES (?, ?, ?, 'wallet', ?, ?, ?)""",
            (actor, season_id, OPERATION, str(actor), request_id, encoded({"day": day, "fee": fee})),
        )
    conn.execute(
        """INSERT INTO v4_map_mark_quota(season_id, account_id, mark_day, used) VALUES (?,?,?,1)
           ON CONFLICT(season_id, account_id, mark_day) DO UPDATE SET used = used + 1""",
        (season_id, actor, day),
    )
    cell_lon, cell_lat = campus.snap(lon, lat)
    cursor = conn.execute(
        """INSERT INTO v4_map_marks(season_id, cell_lon, cell_lat, template_code, word_code, placed_hour, expires_at)
           VALUES (?,?,?,?,?,?,?)""",
        (season_id, cell_lon, cell_lat, template, word,
         rooms.iso(now.replace(minute=0, second=0, microsecond=0)), rooms.iso(now + timedelta(hours=LIFETIME_HOURS))),
    )
    # Для повтора сохраняется ответ без метки и места: в таблице ключей есть
    # account_id, и полный ответ навсегда связал бы автора с меткой.
    stored = {"placed": True, "fee": fee, "stars": after["stars"], "quota": quota_view(used + 1, after["stars"])}
    conn.execute(
        """INSERT INTO v4_idempotency_keys(account_id, operation, idempotency_key, request_hash,
               response_status, response_json) VALUES (?,?,?,?,200,?)""",
        (actor, OPERATION, key, digest, encoded(stored)),
    )
    mark = conn.execute("SELECT * FROM v4_map_marks WHERE id=?", (cursor.lastrowid,)).fetchone()
    return {**stored, "mark": mark_view(mark, False)}, False


def useful(conn, actor: int, season_id: int, mark_id: int) -> dict:
    authorize(conn, actor, season_id, write=True)
    now = utcnow()
    purge(conn, season_id, now)
    row = conn.execute("SELECT * FROM v4_map_marks WHERE id=? AND season_id=? AND hidden_at IS NULL",
                       (mark_id, season_id)).fetchone()
    if not row:
        raise CaseError("Метки больше нет: её скрыли или время вышло.", 404)
    try:
        conn.execute("INSERT INTO v4_map_mark_votes(mark_id, account_id) VALUES (?,?)", (mark_id, actor))
    except sqlite3.IntegrityError as exc:
        raise CaseError("Вы уже отметили эту метку.", 409) from exc
    cap = rooms.parse(row["placed_hour"]) + timedelta(hours=MAX_LIFETIME_HOURS)
    expires = min(rooms.parse(row["expires_at"]) + timedelta(hours=USEFUL_BONUS_HOURS), cap)
    conn.execute("UPDATE v4_map_marks SET useful = useful + 1, expires_at = ? WHERE id=?", (rooms.iso(expires), mark_id))
    return mark_view(conn.execute("SELECT * FROM v4_map_marks WHERE id=?", (mark_id,)).fetchone(), True)


def hide(conn, actor: int, season_id: int, mark_id: int) -> dict:
    authorize(conn, actor, season_id, manage=True, write=True)
    row = conn.execute("SELECT * FROM v4_map_marks WHERE id=? AND season_id=?", (mark_id, season_id)).fetchone()
    if not row:
        raise CaseError("Метка не найдена.", 404)
    if row["hidden_at"] is None:
        conn.execute("UPDATE v4_map_marks SET hidden_at=?, hidden_by_account_id=? WHERE id=?",
                     (rooms.iso(utcnow()), actor, mark_id))
        conn.execute(
            """INSERT INTO v4_audit_log(actor_account_id, season_id, action, entity_type, entity_id, after_json)
               VALUES (?, ?, 'map.hide', 'map_mark', ?, ?)""",
            (actor, season_id, str(mark_id),
             encoded(text_of(row["template_code"], row["word_code"]) if known(row["template_code"], row["word_code"]) else {})),
        )
    return {"id": mark_id, "hidden": True}
