"""Маршруты Протокола 60. Права и CSRF — как у Захвата, сезон — как у тумана."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from typing import Literal

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import campus, royale
from .cases import CaseError
from .db import connect_database, immediate_transaction
from .seasons import SeasonValidationError

ACTIONS_PER_MINUTE = 60


class AnswerPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    choice: int = Field(strict=True, ge=0, le=9)


class VotePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    surprise: Literal["fast", "hanzi", "more"]


def register_royale(app, current_principal, csrf_principal):
    royale.config()  # битый royale.json — ошибка старта, а не посреди вечера
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
        except SeasonValidationError as exc:
            raise HTTPException(400, str(exc)) from exc
        finally:
            conn.close()

    def season_of(conn, account_id: int) -> int:
        season_id = campus.active_season_id(conn, account_id)
        if season_id is None:
            raise HTTPException(409, "Нет активного сезона.")
        return season_id

    def write(principal, handler):
        throttle("act", principal.account_id, ACTIONS_PER_MINUTE)
        with database() as conn:
            season_id = season_of(conn, principal.account_id)
            with immediate_transaction(conn):
                return handler(conn, principal.account_id, season_id)

    @app.get("/api/v4/royale")
    def royale_view(principal=Depends(current_principal)):
        with database() as conn:
            season_id = campus.active_season_id(conn, principal.account_id)
            if season_id is None:
                return {"game": None, "can_host": False, "can_play": False}
            # Шестьдесят телефонов опрашивают раз в секунду: блокировку на запись
            # берём, только если раунд пора закрыть или игру почистить.
            try:
                conn.execute("BEGIN")
                result = royale.current(conn, principal.account_id, season_id, allow_write=False)
                conn.execute("COMMIT")
                return result
            except royale.NeedsWrite:
                conn.execute("ROLLBACK")
            with immediate_transaction(conn):
                return royale.current(conn, principal.account_id, season_id, allow_write=True)

    @app.post("/api/v4/royale/create")
    def royale_create(principal=Depends(csrf_principal)):
        return write(principal, royale.create)

    @app.post("/api/v4/royale/start")
    def royale_start(principal=Depends(csrf_principal)):
        return write(principal, royale.start)

    @app.post("/api/v4/royale/cancel")
    def royale_cancel(principal=Depends(csrf_principal)):
        return write(principal, royale.cancel)

    @app.post("/api/v4/royale/join")
    def royale_join(principal=Depends(csrf_principal)):
        return write(principal, royale.join)

    @app.post("/api/v4/royale/leave")
    def royale_leave(principal=Depends(csrf_principal)):
        return write(principal, royale.leave)

    @app.post("/api/v4/royale/answer")
    def royale_answer(payload: AnswerPayload, principal=Depends(csrf_principal)):
        return write(principal, lambda conn, actor, season_id: royale.answer(conn, actor, season_id, payload.choice))

    @app.post("/api/v4/royale/vote")
    def royale_vote(payload: VotePayload, principal=Depends(csrf_principal)):
        return write(principal, lambda conn, actor, season_id: royale.vote(conn, actor, season_id, payload.surprise))

    @app.post("/api/v4/royale/revive")
    def royale_revive(request: Request, principal=Depends(csrf_principal)):
        throttle("revive", principal.account_id, 10)
        with database() as conn:
            season_id = season_of(conn, principal.account_id)
            with immediate_transaction(conn):
                result, replayed = royale.revive(conn, principal.account_id, season_id,
                                                 request.headers.get("x-idempotency-key", ""),
                                                 request_id=request.state.request_id)
        return JSONResponse(result, headers={"X-Idempotent-Replayed": str(replayed).lower()})
