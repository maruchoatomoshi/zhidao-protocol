"""Маршруты Захвата кампуса. Права и CSRF — как у меток, сезон — как у тумана."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from . import campus, capture
from .cases import CaseError
from .db import connect_database, immediate_transaction
from .seasons import SeasonValidationError

CHALLENGES_PER_MINUTE = 12
ANSWERS_PER_MINUTE = 20


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

    @app.post("/api/v4/capture/switch")
    def capture_switch(payload: SwitchPayload, principal=Depends(csrf_principal)):
        with database() as conn:
            season_id = season_of(conn, principal.account_id)
            with immediate_transaction(conn):
                return capture.set_enabled(conn, principal.account_id, season_id, payload.enabled)
