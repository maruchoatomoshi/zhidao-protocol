"""Маршруты Захвата кампуса. Права и CSRF — как у меток, сезон — как у тумана."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager

from typing import Literal

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import campus, capture, duels
from .cases import CaseError
from .db import connect_database, immediate_transaction
from .seasons import SeasonValidationError

CHALLENGES_PER_MINUTE = 12
ANSWERS_PER_MINUTE = 20
DUEL_JOINS_PER_MINUTE = 10
DUEL_ACTIONS_PER_MINUTE = 60


class PositionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    accuracy_m: float = Field(ge=0.0, le=100000.0)


class AnswerPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    choice: int = Field(ge=0, le=9)


class SwitchPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


class DuelOfferPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    point: str | None = Field(default=None, min_length=1, max_length=40)
    lat: float | None = Field(default=None, ge=-90.0, le=90.0)
    lon: float | None = Field(default=None, ge=-180.0, le=180.0)
    accuracy_m: float | None = Field(default=None, ge=0.0, le=100000.0)


class DuelJoinPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^\d{6}$")


class DuelMovePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    move: Literal["attack", "defend", "trick"]


class PoolPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ability: Literal["shield", "fog", "double", "scout"]
    target: str | None = Field(default=None, min_length=1, max_length=40)
    amount: int = Field(strict=True, ge=1, le=1000)


def register_capture(app, current_principal, csrf_principal):
    history = defaultdict(deque)
    history_lock = threading.Lock()

    def throttle(kind: str, account_id: int, limit: int) -> None:
        now = time.monotonic()
        with history_lock:
            queue = history[(kind, account_id)]
            while queue and now - queue[0] >= 60:
                queue.popleft()
            if len(queue) >= limit:
                raise HTTPException(429, "Слишком часто. Подождите минуту.", headers={"Retry-After": "60"})
            queue.append(now)

    @contextmanager
    def database():
        conn = connect_database(app.state.db_path)
        try:
            yield conn
        except CaseError as exc:
            raise HTTPException(exc.status, str(exc)) from exc
        except campus.CampusError as exc:
            raise HTTPException(exc.status_code, str(exc)) from exc
        except SeasonValidationError as exc:
            raise HTTPException(400, str(exc)) from exc
        finally:
            conn.close()

    def season_of(conn, account_id: int) -> int:
        season_id = campus.active_season_id(conn, account_id)
        if season_id is None:
            raise HTTPException(409, "Нет активного сезона: захватывать пока нечего.")
        return season_id

    @app.get("/api/v4/capture")
    def capture_view(principal=Depends(current_principal)):
        with database() as conn:
            season_id = campus.active_season_id(conn, principal.account_id)
            if season_id is None:
                return {"season_id": None, "points": [], "factions": [], "you": None, "can_manage": False}
            # Первый заход выдаёт фракцию — это запись.
            with immediate_transaction(conn):
                return capture.view(conn, principal.account_id, season_id)

    @app.post("/api/v4/capture/points/{code}/challenge")
    def capture_challenge(code: str, payload: PositionPayload, principal=Depends(csrf_principal)):
        throttle("challenge", principal.account_id, CHALLENGES_PER_MINUTE)
        with database() as conn:
            season_id = season_of(conn, principal.account_id)
            with immediate_transaction(conn):
                return capture.challenge(conn, principal.account_id, season_id, code,
                                         lon=payload.lon, lat=payload.lat, accuracy_m=payload.accuracy_m)

    @app.post("/api/v4/capture/points/{code}/answer")
    def capture_answer(code: str, payload: AnswerPayload, principal=Depends(csrf_principal)):
        throttle("answer", principal.account_id, ANSWERS_PER_MINUTE)
        with database() as conn:
            season_id = season_of(conn, principal.account_id)
            with immediate_transaction(conn):
                return capture.answer(conn, principal.account_id, season_id, code, payload.choice)

    @app.post("/api/v4/capture/points/{code}/confirm")
    def capture_confirm(code: str, payload: PositionPayload, principal=Depends(csrf_principal)):
        with database() as conn:
            season_id = season_of(conn, principal.account_id)
            with immediate_transaction(conn):
                return capture.confirm(conn, principal.account_id, season_id, code,
                                       lon=payload.lon, lat=payload.lat, accuracy_m=payload.accuracy_m)

    # --- дуэли ------------------------------------------------------------------------

    @app.get("/api/v4/capture/duel")
    def duel_view(principal=Depends(current_principal)):
        with database() as conn:
            season_id = campus.active_season_id(conn, principal.account_id)
            if season_id is None:
                return {"duel": None, "offer": None, "duels_left": None}
            # Опросы идут от двух телефонов раз в полторы секунды: блокировку на
            # запись берём, только если дуэль пора довести или почистить.
            try:
                conn.execute("BEGIN")
                result = duels.current(conn, principal.account_id, season_id, allow_write=False)
                conn.execute("COMMIT")
                return result
            except duels.NeedsWrite:
                conn.execute("ROLLBACK")
            with immediate_transaction(conn):
                return duels.current(conn, principal.account_id, season_id, allow_write=True)

    @app.post("/api/v4/capture/duels/offer")
    def duel_offer(payload: DuelOfferPayload, principal=Depends(csrf_principal)):
        throttle("duel-offer", principal.account_id, CHALLENGES_PER_MINUTE)
        with database() as conn:
            season_id = season_of(conn, principal.account_id)
            with immediate_transaction(conn):
                return duels.offer(conn, principal.account_id, season_id, point=payload.point,
                                   lon=payload.lon, lat=payload.lat, accuracy_m=payload.accuracy_m)

    @app.post("/api/v4/capture/duels/join")
    def duel_join(payload: DuelJoinPayload, principal=Depends(csrf_principal)):
        throttle("duel-join", principal.account_id, DUEL_JOINS_PER_MINUTE)
        with database() as conn:
            season_id = season_of(conn, principal.account_id)
            with immediate_transaction(conn):
                return duels.join(conn, principal.account_id, season_id, payload.code)

    @app.post("/api/v4/capture/duel/answer")
    def duel_answer(payload: AnswerPayload, principal=Depends(csrf_principal)):
        throttle("duel-action", principal.account_id, DUEL_ACTIONS_PER_MINUTE)
        with database() as conn:
            season_id = season_of(conn, principal.account_id)
            with immediate_transaction(conn):
                return duels.answer(conn, principal.account_id, season_id, payload.choice)

    @app.post("/api/v4/capture/duel/move")
    def duel_move(payload: DuelMovePayload, principal=Depends(csrf_principal)):
        throttle("duel-action", principal.account_id, DUEL_ACTIONS_PER_MINUTE)
        with database() as conn:
            season_id = season_of(conn, principal.account_id)
            with immediate_transaction(conn):
                return duels.move(conn, principal.account_id, season_id, payload.move)

    @app.post("/api/v4/capture/duel/leave")
    def duel_leave(principal=Depends(csrf_principal)):
        with database() as conn:
            season_id = season_of(conn, principal.account_id)
            with immediate_transaction(conn):
                return duels.leave(conn, principal.account_id, season_id)

    # --- способности и война ----------------------------------------------------------

    @app.post("/api/v4/capture/pool")
    def capture_pool(payload: PoolPayload, request: Request, principal=Depends(csrf_principal)):
        throttle("pool", principal.account_id, ANSWERS_PER_MINUTE)
        with database() as conn:
            season_id = season_of(conn, principal.account_id)
            with immediate_transaction(conn):
                result, replayed = capture.contribute(
                    conn, principal.account_id, season_id, ability=payload.ability, target=payload.target,
                    amount=payload.amount, key=request.headers.get("x-idempotency-key", ""),
                    request_id=request.state.request_id)
        return JSONResponse(result, headers={"X-Idempotent-Replayed": str(replayed).lower()})

    @app.post("/api/v4/capture/finish")
    def capture_finish(principal=Depends(csrf_principal)):
        with database() as conn:
            season_id = season_of(conn, principal.account_id)
            with immediate_transaction(conn):
                return capture.finish_war(conn, principal.account_id, season_id)

    @app.post("/api/v4/capture/new-war")
    def capture_new_war(principal=Depends(csrf_principal)):
        with database() as conn:
            season_id = season_of(conn, principal.account_id)
            with immediate_transaction(conn):
                return capture.new_war(conn, principal.account_id, season_id)

    @app.post("/api/v4/capture/switch")
    def capture_switch(payload: SwitchPayload, principal=Depends(csrf_principal)):
        with database() as conn:
            season_id = season_of(conn, principal.account_id)
            with immediate_transaction(conn):
                return capture.set_enabled(conn, principal.account_id, season_id, payload.enabled)
