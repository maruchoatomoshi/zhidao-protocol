"""Маршруты меток на кампусе (beacons.py). Сезон — как у тумана и Захвата."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import beacons, campus
from .cases import CaseError
from .db import connect_database, immediate_transaction
from .seasons import SeasonValidationError

SCANS_PER_MINUTE = 12


class ScanPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=300)
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    accuracy_m: float = Field(ge=0.0, le=100000.0)


class IssuePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    points: list[str] = Field(min_length=1, max_length=40)


def register_beacons(app, current_principal, csrf_principal):
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
            raise HTTPException(409, "Нет активного сезона.")
        return season_id

    @app.get("/api/v4/beacons")
    def beacons_status(principal=Depends(current_principal)):
        with database() as conn:
            season_id = season_of(conn, principal.account_id)
            conn.execute("BEGIN")
            return beacons.status(conn, principal.account_id, season_id)

    @app.get("/api/v4/beacons/labels")
    def beacons_labels(request: Request, principal=Depends(current_principal)):
        with database() as conn:
            season_id = season_of(conn, principal.account_id)
            conn.execute("BEGIN")
            return beacons.labels(conn, principal.account_id, season_id, str(request.base_url))

    @app.post("/api/v4/beacons/issue")
    def beacons_issue(payload: IssuePayload, request: Request, principal=Depends(csrf_principal)):
        with database() as conn:
            season_id = season_of(conn, principal.account_id)
            with immediate_transaction(conn):
                result, replayed = beacons.issue(conn, principal.account_id, season_id, payload.points,
                                                 request.headers.get("x-idempotency-key", ""),
                                                 request.state.request_id)
        return JSONResponse(result, headers={"X-Idempotent-Replayed": str(replayed).lower()})

    @app.post("/api/v4/beacons/install")
    def beacons_install(payload: ScanPayload, principal=Depends(csrf_principal)):
        throttle("install", principal.account_id, SCANS_PER_MINUTE)
        with database() as conn:
            season_id = season_of(conn, principal.account_id)
            with immediate_transaction(conn):
                return beacons.install(conn, principal.account_id, season_id, text=payload.text,
                                       lon=payload.lon, lat=payload.lat, accuracy_m=payload.accuracy_m)

    @app.post("/api/v4/beacons/scan")
    def beacons_scan(payload: ScanPayload, principal=Depends(csrf_principal)):
        throttle("scan", principal.account_id, SCANS_PER_MINUTE)
        with database() as conn:
            season_id = season_of(conn, principal.account_id)
            with immediate_transaction(conn):
                return beacons.scan(conn, principal.account_id, season_id, text=payload.text,
                                    lon=payload.lon, lat=payload.lat, accuracy_m=payload.accuracy_m)
