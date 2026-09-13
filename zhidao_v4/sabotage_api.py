"""Маршруты Саботажа. Права и CSRF — как у Зомби-протокола, станции — как у Захвата."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from . import campus, sabotage
from .cases import CaseError
from .db import connect_database, immediate_transaction
from .seasons import SeasonValidationError

ACTIONS_PER_MINUTE = 40
# Кодов миллион, а попыток шесть в минуту: подобрать чужой код за игру нельзя.
ELIMINATIONS_PER_MINUTE = 6
TASKS_PER_MINUTE = 12


class CodePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^\d{6}$")


class StationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    point: str = Field(min_length=1, max_length=40)
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    accuracy_m: float = Field(ge=0.0, le=100000.0)


class AnswerPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    choice: int = Field(strict=True, ge=0, le=9)


class VotePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    choice: int = Field(strict=True, ge=0)


def register_sabotage(app, current_principal, csrf_principal):
    sabotage.config()  # битый sabotage.json — ошибка старта, а не посреди вечера
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

    def write(principal, handler, kind="act", limit=ACTIONS_PER_MINUTE):
        throttle(kind, principal.account_id, limit)
        with database() as conn:
            season_id = campus.active_season_id(conn, principal.account_id)
            if season_id is None:
                raise HTTPException(409, "Нет активного сезона.")
            with immediate_transaction(conn):
                return handler(conn, principal.account_id, season_id)

    @app.get("/api/v4/sabotage")
    def sabotage_view(principal=Depends(current_principal)):
        with database() as conn:
            season_id = campus.active_season_id(conn, principal.account_id)
            if season_id is None:
                return {"game": None, "can_host": False, "can_play": False, "stations": 0}
            # Телефоны опрашивают раз в три секунды: блокировку на запись берём,
            # только если собрание пора подсчитать, игру закончить или почистить.
            try:
                conn.execute("BEGIN")
                result = sabotage.current(conn, principal.account_id, season_id, allow_write=False)
                conn.execute("COMMIT")
                return result
            except sabotage.NeedsWrite:
                conn.execute("ROLLBACK")
            with immediate_transaction(conn):
                return sabotage.current(conn, principal.account_id, season_id, allow_write=True)

    @app.post("/api/v4/sabotage/create")
    def sabotage_create(principal=Depends(csrf_principal)):
        return write(principal, sabotage.create)

    @app.post("/api/v4/sabotage/start")
    def sabotage_start(principal=Depends(csrf_principal)):
        return write(principal, sabotage.start)

    @app.post("/api/v4/sabotage/cancel")
    def sabotage_cancel(principal=Depends(csrf_principal)):
        return write(principal, sabotage.cancel)

    @app.post("/api/v4/sabotage/join")
    def sabotage_join(principal=Depends(csrf_principal)):
        return write(principal, sabotage.join)

    @app.post("/api/v4/sabotage/leave")
    def sabotage_leave(principal=Depends(csrf_principal)):
        return write(principal, sabotage.leave)

    @app.post("/api/v4/sabotage/eliminate")
    def sabotage_eliminate(payload: CodePayload, principal=Depends(csrf_principal)):
        return write(principal, lambda conn, actor, season_id: sabotage.eliminate(conn, actor, season_id, payload.code),
                     kind="eliminate", limit=ELIMINATIONS_PER_MINUTE)

    @app.post("/api/v4/sabotage/task/challenge")
    def sabotage_task_challenge(payload: StationPayload, principal=Depends(csrf_principal)):
        return write(principal, lambda conn, actor, season_id: sabotage.task_challenge(
            conn, actor, season_id, payload.point, lon=payload.lon, lat=payload.lat, accuracy_m=payload.accuracy_m),
            kind="task", limit=TASKS_PER_MINUTE)

    @app.post("/api/v4/sabotage/task/answer")
    def sabotage_task_answer(payload: AnswerPayload, principal=Depends(csrf_principal)):
        return write(principal, lambda conn, actor, season_id: sabotage.task_answer(conn, actor, season_id, payload.choice),
                     kind="task", limit=TASKS_PER_MINUTE)

    @app.post("/api/v4/sabotage/meeting")
    def sabotage_meeting(principal=Depends(csrf_principal)):
        return write(principal, sabotage.call_meeting)

    @app.post("/api/v4/sabotage/vote")
    def sabotage_vote(payload: VotePayload, principal=Depends(csrf_principal)):
        return write(principal, lambda conn, actor, season_id: sabotage.vote(conn, actor, season_id, payload.choice))
