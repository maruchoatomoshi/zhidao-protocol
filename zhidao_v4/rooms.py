"""Комнаты вечерних игр: код, состав, ведущий, выключатель.

Модуль ничего не знает о правилах. Шпион, Шифровальщики и Сбой системы
приходят сюда за одним и тем же: четыре цифры, которые можно продиктовать,
список людей за столом и место, куда положить состояние партии.

Три обещания, которые здесь держатся:

- человек сидит не больше чем в одной комнате — вход в новую выводит из
  старой, иначе после вечера у него повиснет десяток «живых» комнат;
- ведущий не пропадает: ушёл — роль переходит к следующему за столом;
- комната временная. Полчаса без действий — и она удаляется вместе с
  составом. Кто с кем играл, после вечера не хранится.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone


GAMES = ("spy", "cipher")
MAX_PLAYERS = 8
ROOM_IDLE_MINUTES = 30
TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


class GameError(RuntimeError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


# Тело действия приходит свободным JSON: у каждой игры свои поля. Проверяем
# их здесь, строго по типу — `True` не должен сойти за единицу, а строка за
# номер карточки.

def int_field(body: dict | None, key: str, low: int | None = None, high: int | None = None) -> int:
    value = (body or {}).get(key)
    if type(value) is not int:
        raise GameError(f"Поле {key} должно быть целым числом.")
    if (low is not None and value < low) or (high is not None and value > high):
        raise GameError(f"Поле {key} вне допустимого диапазона.")
    return value


def bool_field(body: dict | None, key: str) -> bool:
    value = (body or {}).get(key)
    if type(value) is not bool:
        raise GameError(f"Поле {key} должно быть true или false.")
    return value


def text_field(body: dict | None, key: str, max_length: int = 40) -> str:
    value = (body or {}).get(key)
    if not isinstance(value, str) or not value or len(value) > max_length:
        raise GameError(f"Поле {key} заполнено неверно.")
    return value


def utcnow() -> datetime:
    """Часы игр. Одна точка, чтобы тесты могли их подменить."""
    return datetime.now(timezone.utc)


def iso(moment: datetime) -> str:
    # Формат фиксированный, с микросекундами всегда: время сравнивается и в
    # SQL строками, а isoformat() выбрасывает нулевые микросекунды, и
    # лексикографический порядок тогда врёт.
    return moment.astimezone(timezone.utc).strftime(TIME_FORMAT)


def parse(value: str) -> datetime:
    return datetime.strptime(value, TIME_FORMAT).replace(tzinfo=timezone.utc)


def cleanup(conn: sqlite3.Connection, now: datetime) -> None:
    cutoff = iso(now - timedelta(minutes=ROOM_IDLE_MINUTES))
    conn.execute("DELETE FROM v4_game_rooms WHERE last_activity_at < ?", (cutoff,))


def game_enabled(conn: sqlite3.Connection, game: str) -> bool:
    row = conn.execute("SELECT enabled FROM v4_game_switches WHERE game = ?", (game,)).fetchone()
    return row is None or bool(row["enabled"])


def switches(conn: sqlite3.Connection) -> dict[str, bool]:
    return {game: game_enabled(conn, game) for game in GAMES}


def set_switch(
    conn: sqlite3.Connection, game: str, enabled: bool, actor_account_id: int, now: datetime
) -> None:
    if game not in GAMES:
        raise GameError("Такой игры нет.", 404)
    conn.execute(
        """
        INSERT INTO v4_game_switches(game, enabled, updated_by_account_id, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(game) DO UPDATE SET
            enabled = excluded.enabled,
            updated_by_account_id = excluded.updated_by_account_id,
            updated_at = excluded.updated_at
        """,
        (game, int(enabled), actor_account_id, iso(now)),
    )
    conn.execute(
        """
        INSERT INTO v4_audit_log(actor_account_id, action, entity_type, entity_id, after_json)
        VALUES (?, 'game.switch', 'game', ?, ?)
        """,
        (actor_account_id, game, json.dumps({"enabled": bool(enabled)})),
    )
    if not enabled:
        # Выключение гасит и идущие партии: иначе «выключенная» игра
        # продолжала бы жить у тех, кто уже сидит в комнате.
        conn.execute("DELETE FROM v4_game_rooms WHERE game = ?", (game,))


def require_enabled(conn: sqlite3.Connection, game: str) -> None:
    if not game_enabled(conn, game):
        raise GameError("Эта игра сейчас выключена организаторами.", 409)


def load_room(conn: sqlite3.Connection, code: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM v4_game_rooms WHERE code = ?", (code,)).fetchone()


def room_for_account(conn: sqlite3.Connection, account_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT r.* FROM v4_game_rooms r
        JOIN v4_game_room_players p ON p.room_id = r.id
        WHERE p.account_id = ?
        """,
        (account_id,),
    ).fetchone()


def players(conn: sqlite3.Connection, room_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT p.account_id, p.seat, p.score, a.display_name
        FROM v4_game_room_players p JOIN v4_accounts a ON a.id = p.account_id
        WHERE p.room_id = ? ORDER BY p.seat
        """,
        (room_id,),
    ).fetchall()


def _new_code(conn: sqlite3.Connection) -> str:
    for _ in range(64):
        code = f"{secrets.randbelow(10000):04d}"
        if conn.execute("SELECT 1 FROM v4_game_rooms WHERE code = ?", (code,)).fetchone() is None:
            return code
    # Десять тысяч кодов на шестьдесят человек не кончаются; сюда попадаем,
    # только если что-то пошло совсем не так.
    raise GameError("Не удалось подобрать код комнаты. Попробуйте ещё раз.", 503)


def leave_current(conn: sqlite3.Connection, account_id: int, now: datetime) -> None:
    row = conn.execute(
        "SELECT room_id FROM v4_game_room_players WHERE account_id = ?", (account_id,)
    ).fetchone()
    if row is None:
        return
    room_id = int(row["room_id"])
    conn.execute(
        "DELETE FROM v4_game_room_players WHERE room_id = ? AND account_id = ?",
        (room_id, account_id),
    )
    rest = players(conn, room_id)
    if not rest:
        conn.execute("DELETE FROM v4_game_rooms WHERE id = ?", (room_id,))
        return
    conn.execute(
        """
        UPDATE v4_game_rooms
        SET host_account_id = CASE WHEN host_account_id = ? THEN ? ELSE host_account_id END,
            revision = revision + 1, last_activity_at = ?
        WHERE id = ?
        """,
        (account_id, int(rest[0]["account_id"]), iso(now), room_id),
    )


def create_room(
    conn: sqlite3.Connection, account_id: int, game: str, settings: dict, now: datetime
) -> sqlite3.Row:
    if game not in GAMES:
        raise GameError("Такой игры нет.", 404)
    cleanup(conn, now)
    require_enabled(conn, game)
    leave_current(conn, account_id, now)
    stamp = iso(now)
    cursor = conn.execute(
        """
        INSERT INTO v4_game_rooms(code, game, host_account_id, status, settings_json,
                                  state_json, created_at, last_activity_at)
        VALUES (?, ?, ?, 'lobby', ?, '{}', ?, ?)
        """,
        (_new_code(conn), game, account_id, json.dumps(settings), stamp, stamp),
    )
    room_id = int(cursor.lastrowid)
    conn.execute(
        "INSERT INTO v4_game_room_players(room_id, account_id, seat, joined_at) VALUES (?, ?, 1, ?)",
        (room_id, account_id, stamp),
    )
    return conn.execute("SELECT * FROM v4_game_rooms WHERE id = ?", (room_id,)).fetchone()


def join_room(
    conn: sqlite3.Connection, account_id: int, code: str, now: datetime, *, joinable
) -> sqlite3.Row:
    cleanup(conn, now)
    room = load_room(conn, code)
    if room is None:
        raise GameError("Комнаты с таким кодом нет. Проверьте цифры.", 404)
    require_enabled(conn, room["game"])
    seated = conn.execute(
        "SELECT 1 FROM v4_game_room_players WHERE room_id = ? AND account_id = ?",
        (room["id"], account_id),
    ).fetchone()
    if seated is not None:
        return room
    if not joinable(room):
        raise GameError("Партия уже идёт. Дождитесь конца раунда.", 409)
    seats = players(conn, int(room["id"]))
    if len(seats) >= MAX_PLAYERS:
        raise GameError(f"В комнате уже {MAX_PLAYERS} игроков.", 409)
    leave_current(conn, account_id, now)
    # Код мог принадлежать комнате, которая только что опустела и удалилась
    # вместе с уходом из неё этого же человека.
    room = load_room(conn, code)
    if room is None:
        raise GameError("Комнаты с таким кодом нет. Проверьте цифры.", 404)
    seat = 1 + max((int(p["seat"]) for p in players(conn, int(room["id"]))), default=0)
    conn.execute(
        "INSERT INTO v4_game_room_players(room_id, account_id, seat, joined_at) VALUES (?, ?, ?, ?)",
        (room["id"], account_id, seat, iso(now)),
    )
    touch(conn, int(room["id"]), now)
    return load_room(conn, code)


def touch(conn: sqlite3.Connection, room_id: int, now: datetime) -> None:
    conn.execute(
        "UPDATE v4_game_rooms SET revision = revision + 1, last_activity_at = ? WHERE id = ?",
        (iso(now), room_id),
    )


def save(
    conn: sqlite3.Connection,
    room_id: int,
    *,
    status: str,
    state: dict,
    now: datetime,
    settings: dict | None = None,
) -> None:
    if settings is None:
        conn.execute(
            """
            UPDATE v4_game_rooms SET status = ?, state_json = ?,
                revision = revision + 1, last_activity_at = ?
            WHERE id = ?
            """,
            (status, json.dumps(state, ensure_ascii=False), iso(now), room_id),
        )
    else:
        conn.execute(
            """
            UPDATE v4_game_rooms SET status = ?, state_json = ?, settings_json = ?,
                revision = revision + 1, last_activity_at = ?
            WHERE id = ?
            """,
            (status, json.dumps(state, ensure_ascii=False), json.dumps(settings),
             iso(now), room_id),
        )


def add_points(conn: sqlite3.Connection, room_id: int, points: dict[int, int]) -> None:
    for account_id, amount in points.items():
        if amount:
            conn.execute(
                "UPDATE v4_game_room_players SET score = score + ? WHERE room_id = ? AND account_id = ?",
                (int(amount), room_id, int(account_id)),
            )
