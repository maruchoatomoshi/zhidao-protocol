"""Маршруты оценки дневника. Права, CSRF и защита от повтора — как у кейсов."""
from contextlib import contextmanager

from fastapi import Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import diary
from .cases import CaseError
from .db import connect_database, immediate_transaction
from .seasons import SeasonValidationError


class RatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: int = Field(gt=0, strict=True)
    entry_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    stars: int = Field(ge=0, le=3, strict=True)
    bonus: bool = Field(strict=True)
    # Ревизия, которую видел вожатый. 0 — оценки ещё не было.
    expected_revision: int = Field(ge=0, strict=True)


def register_diary(app, current_principal, csrf_principal):
    diary.rules()  # Битые правила — ошибка старта, а не посреди оценки.

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

    @app.get("/api/v4/diary/rules")
    def diary_rules():
        return diary.rules()

    @app.get("/api/v4/seasons/{season_id}/diary/mine")
    def diary_mine(season_id: int, principal=Depends(current_principal)):
        with database() as conn:
            conn.execute("BEGIN")
            return diary.mine(conn, principal.account_id, season_id)

    @app.get("/api/v4/seasons/{season_id}/diary/leaderboard")
    def diary_leaderboard(season_id: int, principal=Depends(current_principal)):
        with database() as conn:
            conn.execute("BEGIN")
            return diary.leaderboard(conn, principal.account_id, season_id)

    @app.get("/api/v4/seasons/{season_id}/diary/day")
    def diary_day(season_id: int, date: str | None = Query(default=None, max_length=10),
                  principal=Depends(current_principal)):
        with database() as conn:
            conn.execute("BEGIN")
            return diary.day(conn, principal.account_id, season_id, date)

    @app.post("/api/v4/seasons/{season_id}/diary/ratings")
    def diary_rate(season_id: int, payload: RatePayload, request: Request,
                   principal=Depends(csrf_principal)):
        with database() as conn:
            with immediate_transaction(conn):
                result, replayed = diary.rate(
                    conn, principal.account_id, season_id,
                    request.headers.get("x-idempotency-key", ""),
                    payload.account_id, payload.entry_date, payload.stars, payload.bonus,
                    payload.expected_revision, request.state.request_id,
                )
        return JSONResponse(result, headers={"X-Idempotent-Replayed": str(replayed).lower()})
