"""Маршруты вируса Протокола. Права, CSRF и защита от повтора — как у кейсов."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import virus
from .cases import CaseError
from .db import connect_database, immediate_transaction
from .seasons import SeasonValidationError

TESTS_PER_MINUTE = 6


class AnswerPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answers: list[int] = Field(min_length=1, max_length=10)


class ReleasePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: int = Field(gt=0, strict=True)


def register_virus(app, current_principal, csrf_principal):
    tests = virus.Tests()
    marks = defaultdict(deque)
    marks_lock = threading.Lock()

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

    def consume_test_slot(account_id: int) -> None:
        now = time.monotonic()
        with marks_lock:
            queue = marks[account_id]
            while queue and now - queue[0] >= 60:
                queue.popleft()
            if len(queue) >= TESTS_PER_MINUTE:
                raise HTTPException(429, "Слишком много тестов подряд. Подождите минуту.", headers={"Retry-After": "60"})
            queue.append(now)

    @app.get("/api/v4/seasons/{season_id}/virus")
    def virus_status(season_id: int, principal=Depends(current_principal)):
        with database() as conn:
            conn.execute("BEGIN")
            return virus.status(conn, principal.account_id, season_id)

    @app.post("/api/v4/seasons/{season_id}/virus/antivirus")
    def virus_antivirus(season_id: int, request: Request, principal=Depends(csrf_principal)):
        with database() as conn:
            with immediate_transaction(conn):
                result, replayed = virus.buy_antivirus(conn, principal.account_id, season_id,
                                                       request.headers.get("x-idempotency-key", ""),
                                                       request.state.request_id)
        return JSONResponse(result, headers={"X-Idempotent-Replayed": str(replayed).lower()})

    @app.post("/api/v4/seasons/{season_id}/virus/firewall")
    def virus_firewall(season_id: int, request: Request, principal=Depends(csrf_principal)):
        with database() as conn:
            with immediate_transaction(conn):
                result, replayed = virus.buy_firewall(conn, principal.account_id, season_id,
                                                      request.headers.get("x-idempotency-key", ""),
                                                      request.state.request_id)
        return JSONResponse(result, headers={"X-Idempotent-Replayed": str(replayed).lower()})

    @app.post("/api/v4/seasons/{season_id}/virus/test")
    def virus_test(season_id: int, principal=Depends(csrf_principal)):
        consume_test_slot(principal.account_id)
        with database() as conn:
            conn.execute("BEGIN")
            if not virus.status(conn, principal.account_id, season_id)["infected"]:
                raise HTTPException(409, "Вы не заражены — лечиться не от чего.")
        return tests.make(principal.account_id, season_id)

    @app.post("/api/v4/seasons/{season_id}/virus/test/answer")
    def virus_answer(season_id: int, payload: AnswerPayload, principal=Depends(csrf_principal)):
        try:
            correct = tests.check(principal.account_id, season_id, payload.answers)
        except CaseError as exc:
            raise HTTPException(exc.status, str(exc)) from exc
        with database() as conn:
            with immediate_transaction(conn):
                return virus.pass_test(conn, principal.account_id, season_id, correct)

    @app.post("/api/v4/seasons/{season_id}/virus/release")
    def virus_release(season_id: int, payload: ReleasePayload, principal=Depends(csrf_principal)):
        # Выпускает Архитектор (или системный администратор) — не вожатый.
        if not (principal.has_global_role("architect") or principal.has_global_role("system_admin")):
            raise HTTPException(403, "Выпускать вирус может только Архитектор.")
        with database() as conn:
            with immediate_transaction(conn):
                return virus.release(conn, principal.account_id, season_id, payload.account_id)
