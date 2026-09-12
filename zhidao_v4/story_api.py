"""Маршруты скрытых файлов. Сезон — как у тумана, права — как у кейсов."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from . import campus, story
from .cases import CaseError
from .db import connect_database, immediate_transaction
from .seasons import SeasonValidationError

ANSWERS_PER_MINUTE = 10


class AnswerPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str = Field(min_length=1, max_length=80)


def register_story(app, current_principal, csrf_principal):
    attempts = defaultdict(deque)
    attempts_lock = threading.Lock()

    def throttle(account_id: int) -> None:
        now = time.monotonic()
        with attempts_lock:
            queue = attempts[account_id]
            while queue and now - queue[0] >= 60:
                queue.popleft()
            if len(queue) >= ANSWERS_PER_MINUTE:
                raise HTTPException(429, "Слишком много попыток. Подождите минуту.", headers={"Retry-After": "60"})
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

    @app.get("/api/v4/story")
    def story_view(principal=Depends(current_principal)):
        with database() as conn:
            season_id = campus.active_season_id(conn, principal.account_id)
            if season_id is None:
                return {"season_id": None, "fragments": [], "message": [], "complete": False}
            # Первый заход в активном сезоне запоминает день старта — это запись.
            with immediate_transaction(conn):
                return story.view(conn, principal.account_id, season_id)

    @app.post("/api/v4/story/{code}/answer")
    def story_answer(code: str, payload: AnswerPayload, principal=Depends(csrf_principal)):
        throttle(principal.account_id)
        with database() as conn:
            season_id = campus.active_season_id(conn, principal.account_id)
            if season_id is None:
                raise HTTPException(409, "Нет активного сезона.")
            with immediate_transaction(conn):
                return story.answer(conn, principal.account_id, season_id, code, payload.answer)
