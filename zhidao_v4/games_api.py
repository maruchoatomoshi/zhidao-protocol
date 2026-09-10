"""Маршруты вечерних игр. Права и CSRF — те же зависимости, что у кейсов.

Комнатам не нужен активный сезон: вечерние игры должны работать и тогда,
когда сезон ещё черновик, и у организаторов, у которых нет участия.

Присутствие («кто сейчас смотрит на экран») держится в памяти процесса:
его отметки идут на каждый опрос, и писать их в SQLite незачем. После
перезапуска сервера оно восстанавливается за пару секунд само — телефоны
продолжают опрашивать. Состояние партии при этом лежит в базе и не теряется.
"""

from __future__ import annotations

import json
import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from typing import Literal

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from . import rooms, spy
from .db import connect_database, immediate_transaction


PRESENCE_SECONDS = 20
JOINS_PER_MINUTE = 20


class RoomCreatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    game: Literal["spy"]


class RoomJoinPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^\d{4}$")


class SettingsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["translated", "hanzi"]
    minutes: int = Field(ge=spy.MINUTES[0], le=spy.MINUTES[1], strict=True)


class TargetPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_account_id: int = Field(gt=0, strict=True)


class VotePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    yes: bool = Field(strict=True)


class GuessPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    location_id: str = Field(min_length=1, max_length=40)


class SwitchPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = Field(strict=True)


def register_games(app, current_principal, csrf_principal, architect_writer):
    spy.content()  # Битые данные мест — ошибка старта, а не посреди вечера.

    app.state.game_presence = {}
    app.state.game_presence_lock = threading.Lock()
    app.state.game_joins = defaultdict(deque)
    app.state.game_joins_lock = threading.Lock()

    def mark_present(account_id: int) -> None:
        with app.state.game_presence_lock:
            app.state.game_presence[account_id] = time.monotonic()

    def present_among(ids) -> set[int]:
        now = time.monotonic()
        with app.state.game_presence_lock:
            return {
                pid for pid in ids
                if now - app.state.game_presence.get(pid, float("-inf")) < PRESENCE_SECONDS
            }

    def consume_join_slot(account_id: int) -> None:
        # Кодов всего десять тысяч. Без ограничения чужую комнату нашли бы
        # перебором за пару минут.
        now = time.monotonic()
        with app.state.game_joins_lock:
            marks = app.state.game_joins[account_id]
            while marks and now - marks[0] >= 60:
                marks.popleft()
            if len(marks) >= JOINS_PER_MINUTE:
                raise HTTPException(429, "Слишком много попыток входа. Подождите минуту.",
                                    headers={"Retry-After": "60"})
            marks.append(now)

    @contextmanager
    def database():
        conn = connect_database(app.state.db_path)
        try:
            yield conn
        except rooms.GameError as exc:
            raise HTTPException(exc.status_code, str(exc)) from exc
        finally:
            conn.close()

    def seated_ids(conn, room_id: int) -> list[int]:
        return [int(p["account_id"]) for p in rooms.players(conn, room_id)]

    def settle(conn, room) -> None:
        """Доводит партию до «сейчас» и пишет, только если что-то сдвинулось.

        Опросы идут от каждого телефона раз в пару секунд. Брать ради них
        блокировку на запись — значит толкаться с кейсами; поэтому сначала
        смотрим без блокировки и лишь при настоящем переходе перечитываем
        комнату уже внутри BEGIN IMMEDIATE.
        """
        state = json.loads(room["state_json"])
        seated = set(seated_ids(conn, int(room["id"])))
        probe = json.loads(room["state_json"])
        if not spy.in_round(state):
            return
        spy.tick(probe, seated, rooms.utcnow())
        if probe == state:
            return
        with immediate_transaction(conn):
            fresh = conn.execute("SELECT * FROM v4_game_rooms WHERE id = ?", (room["id"],)).fetchone()
            if fresh is None:
                return
            state = json.loads(fresh["state_json"])
            seated = set(seated_ids(conn, int(fresh["id"])))
            now = rooms.utcnow()
            points = spy.tick(state, seated, now)
            rooms.add_points(conn, int(fresh["id"]), points)
            rooms.save(conn, int(fresh["id"]), status=fresh["status"], state=state, now=now)

    def room_view(conn, room, viewer: int) -> dict:
        seats = rooms.players(conn, int(room["id"]))
        seated = {int(p["account_id"]) for p in seats}
        present = present_among(seated)
        settings = json.loads(room["settings_json"])
        state = json.loads(room["state_json"])
        return {
            "room": {
                "code": room["code"],
                "game": room["game"],
                "status": room["status"],
                "revision": int(room["revision"]),
                "host_account_id": int(room["host_account_id"]),
                "is_host": int(room["host_account_id"]) == viewer,
                "settings": settings,
                "joinable": spy.joinable(room["status"], state),
                "min_players": spy.MIN_PLAYERS,
                "max_players": rooms.MAX_PLAYERS,
            },
            "you": viewer,
            "players": [
                {
                    "account_id": int(p["account_id"]),
                    "display_name": p["display_name"],
                    "seat": int(p["seat"]),
                    "score": int(p["score"]),
                    "present": int(p["account_id"]) in present,
                }
                for p in seats
            ],
            "spy": spy.view(state, viewer, settings, seated, rooms.utcnow()),
        }

    def member_room(conn, code: str, account_id: int):
        room = rooms.load_room(conn, code)
        if room is None or account_id not in seated_ids(conn, int(room["id"])):
            # Одинаковый ответ «нет такой» и «не ваша»: по нему нельзя
            # узнать, что комната с этим кодом существует.
            raise rooms.GameError("Комната не найдена.", 404)
        return room

    def act(code: str, account_id: int, action):
        """Общий путь действия игрока: блокировка, доводка до «сейчас», ход."""
        mark_present(account_id)
        with database() as conn:
            with immediate_transaction(conn):
                room = member_room(conn, code, account_id)
                rooms.require_enabled(conn, room["game"])
                state = json.loads(room["state_json"])
                settings = json.loads(room["settings_json"])
                seated = set(seated_ids(conn, int(room["id"])))
                now = rooms.utcnow()
                points = spy.tick(state, seated, now)
                status, new_settings, more = action(room, state, settings, seated, now)
                for pid, amount in (more or {}).items():
                    points[pid] = points.get(pid, 0) + amount
                rooms.add_points(conn, int(room["id"]), points)
                rooms.save(conn, int(room["id"]), status=status, state=state, now=now,
                           settings=new_settings)
            return room_view(conn, rooms.load_room(conn, code), account_id)

    # --- комнаты --------------------------------------------------------------

    @app.get("/api/v4/games/rooms/current")
    def current_room(principal=Depends(current_principal)):
        mark_present(principal.account_id)
        with database() as conn:
            room = rooms.room_for_account(conn, principal.account_id)
            if room is None:
                return {"room": None, "switches": rooms.switches(conn)}
            settle(conn, room)
            room = rooms.room_for_account(conn, principal.account_id)
            if room is None:
                return {"room": None, "switches": rooms.switches(conn)}
            return room_view(conn, room, principal.account_id)

    @app.post("/api/v4/games/rooms")
    def create_room(payload: RoomCreatePayload, principal=Depends(csrf_principal)):
        mark_present(principal.account_id)
        with database() as conn:
            with immediate_transaction(conn):
                room = rooms.create_room(conn, principal.account_id, payload.game,
                                         dict(spy.DEFAULT_SETTINGS), rooms.utcnow())
            return room_view(conn, room, principal.account_id)

    @app.post("/api/v4/games/rooms/join")
    def join_room(payload: RoomJoinPayload, principal=Depends(csrf_principal)):
        consume_join_slot(principal.account_id)
        mark_present(principal.account_id)
        with database() as conn:
            with immediate_transaction(conn):
                room = rooms.join_room(
                    conn, principal.account_id, payload.code, rooms.utcnow(),
                    joinable=lambda r: spy.joinable(r["status"], json.loads(r["state_json"])),
                )
            return room_view(conn, room, principal.account_id)

    @app.get("/api/v4/games/rooms/{code}")
    def get_room(code: str, principal=Depends(current_principal)):
        mark_present(principal.account_id)
        with database() as conn:
            room = member_room(conn, code, principal.account_id)
            settle(conn, room)
            return room_view(conn, member_room(conn, code, principal.account_id), principal.account_id)

    @app.post("/api/v4/games/rooms/{code}/leave")
    def leave_room(code: str, principal=Depends(csrf_principal)):
        with database() as conn:
            with immediate_transaction(conn):
                member_room(conn, code, principal.account_id)
                rooms.leave_current(conn, principal.account_id, rooms.utcnow())
            return {"room": None, "switches": rooms.switches(conn)}

    @app.post("/api/v4/games/rooms/{code}/settings")
    def room_settings(code: str, payload: SettingsPayload, principal=Depends(csrf_principal)):
        def action(room, state, settings, seated, now):
            if int(room["host_account_id"]) != principal.account_id:
                raise rooms.GameError("Настройки меняет ведущий.", 403)
            if spy.in_round(state):
                raise rooms.GameError("Настройки меняются между раундами.", 409)
            return room["status"], spy.clean_settings(payload.mode, payload.minutes), None
        return act(code, principal.account_id, action)

    # --- Шпион ---------------------------------------------------------------

    @app.post("/api/v4/games/rooms/{code}/spy/start")
    def spy_start(code: str, principal=Depends(csrf_principal)):
        def action(room, state, settings, seated, now):
            if int(room["host_account_id"]) != principal.account_id:
                raise rooms.GameError("Раунд запускает ведущий.", 403)
            # Порядок не важен: шпиона и роли всё равно выбирает жребий.
            fresh = spy.start_round(state, sorted(seated), settings, now)
            state.clear()
            state.update(fresh)
            return "playing", None, None
        return act(code, principal.account_id, action)

    @app.post("/api/v4/games/rooms/{code}/spy/accuse")
    def spy_accuse(code: str, payload: TargetPayload, principal=Depends(csrf_principal)):
        def action(room, state, settings, seated, now):
            spy.accuse(state, principal.account_id, payload.target_account_id, seated, now)
            return room["status"], None, None
        return act(code, principal.account_id, action)

    @app.post("/api/v4/games/rooms/{code}/spy/vote")
    def spy_vote(code: str, payload: VotePayload, principal=Depends(csrf_principal)):
        def action(room, state, settings, seated, now):
            spy.vote(state, principal.account_id, payload.yes, seated)
            # Голос мог оказаться решающим — доводим сразу, а не при следующем опросе.
            points = spy.tick(state, seated, now)
            return room["status"], None, points
        return act(code, principal.account_id, action)

    @app.post("/api/v4/games/rooms/{code}/spy/guess")
    def spy_guess(code: str, payload: GuessPayload, principal=Depends(csrf_principal)):
        def action(room, state, settings, seated, now):
            points = spy.guess(state, principal.account_id, payload.location_id, seated)
            return room["status"], None, points
        return act(code, principal.account_id, action)

    @app.post("/api/v4/games/rooms/{code}/spy/final-vote")
    def spy_final_vote(code: str, payload: TargetPayload, principal=Depends(csrf_principal)):
        def action(room, state, settings, seated, now):
            spy.final_vote(state, principal.account_id, payload.target_account_id, seated)
            points = spy.tick(state, seated, now)
            return room["status"], None, points
        return act(code, principal.account_id, action)

    # --- выключатели ------------------------------------------------------------

    @app.get("/api/v4/games/switches")
    def game_switches(principal=Depends(current_principal)):
        del principal
        with database() as conn:
            return {"switches": rooms.switches(conn)}

    @app.post("/api/v4/games/switches/{game}")
    def set_game_switch(game: str, payload: SwitchPayload, principal=Depends(architect_writer)):
        with database() as conn:
            with immediate_transaction(conn):
                rooms.set_switch(conn, game, payload.enabled, principal.account_id, rooms.utcnow())
            return {"switches": rooms.switches(conn)}
