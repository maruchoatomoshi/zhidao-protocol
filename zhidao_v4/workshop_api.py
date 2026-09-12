"""Маршруты мастерской дубликатов. Права, CSRF и защита от повтора — как у кейсов."""
from __future__ import annotations

from contextlib import contextmanager

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import workshop
from .cases import CaseError
from .db import connect_database, immediate_transaction
from .seasons import SeasonValidationError


class CraftPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_code: str = Field(min_length=1, max_length=40)


def register_workshop(app, current_principal, csrf_principal):
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

    @app.get("/api/v4/seasons/{season_id}/workshop")
    def workshop_state(season_id: int, principal=Depends(current_principal)):
        with database() as conn:
            conn.execute("BEGIN")
            return workshop.state(conn, principal.account_id, season_id)

    @app.post("/api/v4/seasons/{season_id}/workshop/craft")
    def workshop_craft(season_id: int, payload: CraftPayload, request: Request, principal=Depends(csrf_principal)):
        with database() as conn:
            with immediate_transaction(conn):
                result, replayed = workshop.craft(conn, principal.account_id, season_id, payload.item_code,
                                                  request.headers.get("x-idempotency-key", ""),
                                                  request.state.request_id)
        return JSONResponse(result, headers={"X-Idempotent-Replayed": str(replayed).lower()})
