"""Маршруты Зомби-протокола. Права и CSRF — как у Протокола 60, станции — как у Захвата."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from . import campus, zombie
from .cases import CaseError
from .db import connect_database, immediate_transaction
from .seasons import SeasonValidationError

ACTIONS_PER_MINUTE = 40
# Кодов миллион, а попыток шесть в минуту: подобрать чужой код за раунд нельзя.
TAGS_PER_MINUTE = 6
VACCINES_PER_MINUTE = 12


class TagPayload(BaseModel):
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


def register_zombie(app, current_principal, csrf_principal):
    zombie.config()  # битый zombie.json — ошибка старта, а не посреди вечера
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

    @app.get("/api/v4/zombie")
    def zombie_view(principal=Depends(current_principal)):
        with database() as conn:
            season_id = campus.active_season_id(conn, principal.account_id)
            if season_id is None:
                return {"game": None, "can_host": False, "can_play": False, "stations": []}
            # Во время раунда телефоны опрашивают раз в три секунды: блокировку на
            # запись берём, только если раунд пора закончить или почистить.
            try:
                conn.execute("BEGIN")
                result = zombie.current(conn, principal.account_id, season_id, allow_write=False)
                conn.execute("COMMIT")
                return result
            except zombie.NeedsWrite:
                conn.execute("ROLLBACK")
            with immediate_transaction(conn):
                return zombie.current(conn, principal.account_id, season_id, allow_write=True)

    @app.post("/api/v4/zombie/create")
    def zombie_create(principal=Depends(csrf_principal)):
        return write(principal, zombie.create)

    @app.post("/api/v4/zombie/start")
    def zombie_start(principal=Depends(csrf_principal)):
        return write(principal, zombie.start)

    @app.post("/api/v4/zombie/cancel")
    def zombie_cancel(principal=Depends(csrf_principal)):
        return write(principal, zombie.cancel)

    @app.post("/api/v4/zombie/join")
    def zombie_join(principal=Depends(csrf_principal)):
        return write(principal, zombie.join)

    @app.post("/api/v4/zombie/leave")
    def zombie_leave(principal=Depends(csrf_principal)):
        return write(principal, zombie.leave)

    @app.post("/api/v4/zombie/tag")
    def zombie_tag(payload: TagPayload, principal=Depends(csrf_principal)):
        return write(principal, lambda conn, actor, season_id: zombie.tag(conn, actor, season_id, payload.code),
                     kind="tag", limit=TAGS_PER_MINUTE)

    @app.post("/api/v4/zombie/vaccine/challenge")
    def zombie_vaccine_challenge(payload: StationPayload, principal=Depends(csrf_principal)):
        return write(principal, lambda conn, actor, season_id: zombie.vaccine_challenge(
            conn, actor, season_id, payload.point, lon=payload.lon, lat=payload.lat, accuracy_m=payload.accuracy_m),
            kind="vaccine", limit=VACCINES_PER_MINUTE)

    @app.post("/api/v4/zombie/vaccine/answer")
    def zombie_vaccine_answer(payload: AnswerPayload, principal=Depends(csrf_principal)):
        return write(principal, lambda conn, actor, season_id: zombie.vaccine_answer(conn, actor, season_id, payload.choice),
                     kind="vaccine", limit=VACCINES_PER_MINUTE)
