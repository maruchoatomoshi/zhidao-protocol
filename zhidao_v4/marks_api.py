"""Маршруты меток на карте. Права и CSRF — как у кейсов, сезон — как у тумана."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import campus, marks
from .cases import CaseError
from .db import connect_database, immediate_transaction
from .seasons import SeasonValidationError

PLACES_PER_MINUTE = 5
VOTES_PER_MINUTE = 20


class MarkPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    accuracy_m: float = Field(ge=0.0, le=100000.0)
    template: str = Field(min_length=1, max_length=40)
    word: str = Field(min_length=1, max_length=40)


def register_marks(app, current_principal, csrf_principal):
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
            raise HTTPException(409, "Нет активного сезона: оставлять метки пока негде.")
        return season_id

    @app.get("/api/v4/campus/marks")
    def marks_view(principal=Depends(current_principal)):
        with database() as conn:
            season_id = campus.active_season_id(conn, principal.account_id)
            if season_id is None:
                return {"season_id": None, "marks": [], "quota": None, "can_moderate": False}
            conn.execute("BEGIN")
            return marks.view(conn, principal.account_id, season_id)

    @app.post("/api/v4/campus/marks")
    def marks_place(payload: MarkPayload, request: Request, principal=Depends(csrf_principal)):
        throttle("place", principal.account_id, PLACES_PER_MINUTE)
        with database() as conn:
            season_id = season_of(conn, principal.account_id)
            with immediate_transaction(conn):
                result, replayed = marks.place(
                    conn, principal.account_id, season_id, lon=payload.lon, lat=payload.lat,
                    accuracy_m=payload.accuracy_m, template=payload.template, word=payload.word,
                    key=request.headers.get("x-idempotency-key", ""), request_id=request.state.request_id)
        return JSONResponse(result, headers={"X-Idempotent-Replayed": str(replayed).lower()})

    @app.post("/api/v4/campus/marks/{mark_id}/useful")
    def marks_useful(mark_id: int, principal=Depends(csrf_principal)):
        throttle("useful", principal.account_id, VOTES_PER_MINUTE)
        with database() as conn:
            season_id = season_of(conn, principal.account_id)
            with immediate_transaction(conn):
                return marks.useful(conn, principal.account_id, season_id, mark_id)

    @app.post("/api/v4/campus/marks/{mark_id}/hide")
    def marks_hide(mark_id: int, principal=Depends(csrf_principal)):
        with database() as conn:
            season_id = season_of(conn, principal.account_id)
            with immediate_transaction(conn):
                return marks.hide(conn, principal.account_id, season_id, mark_id)
