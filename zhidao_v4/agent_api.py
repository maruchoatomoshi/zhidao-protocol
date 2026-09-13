"""Маршруты Тайного агента. Права и CSRF — как у Захвата, сезон — как у тумана."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from . import agent, campus
from .cases import CaseError
from .db import connect_database, immediate_transaction
from .seasons import SeasonValidationError

ACTIONS_PER_MINUTE = 30


class AnswerPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    yes: bool = Field(strict=True)


class GuessPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    suspect: int = Field(strict=True, ge=1)


class ExcludePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: int = Field(strict=True, ge=1)


def register_agent(app, current_principal, csrf_principal):
    agent.config()  # битый agent.json — ошибка старта, а не посреди смены
    history = defaultdict(deque)
    history_lock = threading.Lock()

    def throttle(account_id: int) -> None:
        now = time.monotonic()
        with history_lock:
            queue = history[account_id]
            while queue and now - queue[0] >= 60:
                queue.popleft()
            if len(queue) >= ACTIONS_PER_MINUTE:
                raise HTTPException(429, "Слишком часто. Подождите минуту.", headers={"Retry-After": "60"})
            queue.append(now)

    @contextmanager
    def database():
        conn = connect_database(app.state.db_path)
        try:
            yield conn
        except CaseError as exc:
            raise HTTPException(exc.status, str(exc)) from exc
        except SeasonValidationError as exc:
            raise HTTPException(400, str(exc)) from exc
        finally:
            conn.close()

    def write(principal, handler):
        throttle(principal.account_id)
        with database() as conn:
            season_id = campus.active_season_id(conn, principal.account_id)
            if season_id is None:
                raise HTTPException(409, "Нет активного сезона.")
            with immediate_transaction(conn):
                return handler(conn, principal.account_id, season_id)

    @app.get("/api/v4/agent")
    def agent_view(principal=Depends(current_principal)):
        with database() as conn:
            season_id = campus.active_season_id(conn, principal.account_id)
            if season_id is None:
                return {"season_id": None, "running": False, "can_play": False, "can_manage": False}
            # Телефоны опрашивают раз в 20 секунд; запись нужна только утром,
            # когда круг пора пересобрать.
            try:
                conn.execute("BEGIN")
                result = agent.current(conn, principal.account_id, season_id, allow_write=False)
                conn.execute("COMMIT")
                return result
            except agent.NeedsWrite:
                conn.execute("ROLLBACK")
            with immediate_transaction(conn):
                return agent.current(conn, principal.account_id, season_id, allow_write=True)

    @app.post("/api/v4/agent/join")
    def agent_join(principal=Depends(csrf_principal)):
        return write(principal, agent.join)

    @app.post("/api/v4/agent/leave")
    def agent_leave(principal=Depends(csrf_principal)):
        return write(principal, agent.leave)

    @app.post("/api/v4/agent/ask")
    def agent_ask(principal=Depends(csrf_principal)):
        return write(principal, agent.ask)

    @app.post("/api/v4/agent/answer")
    def agent_answer(payload: AnswerPayload, principal=Depends(csrf_principal)):
        return write(principal, lambda conn, actor, season_id: agent.answer(conn, actor, season_id, payload.yes))

    @app.post("/api/v4/agent/guess")
    def agent_guess(payload: GuessPayload, principal=Depends(csrf_principal)):
        return write(principal, lambda conn, actor, season_id: agent.guess(conn, actor, season_id, payload.suspect))

    @app.post("/api/v4/agent/start")
    def agent_start(principal=Depends(csrf_principal)):
        return write(principal, agent.start)

    @app.post("/api/v4/agent/reshuffle")
    def agent_reshuffle(principal=Depends(csrf_principal)):
        return write(principal, agent.reshuffle)

    @app.post("/api/v4/agent/finish")
    def agent_finish(principal=Depends(csrf_principal)):
        return write(principal, agent.finish)

    @app.post("/api/v4/agent/exclude")
    def agent_exclude(payload: ExcludePayload, principal=Depends(csrf_principal)):
        return write(principal, lambda conn, actor, season_id: agent.exclude(conn, actor, season_id, payload.account_id))
