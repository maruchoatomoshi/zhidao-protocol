"""Маршруты панели экономики и погашения купонов. Права — как у кейсов."""
from contextlib import contextmanager

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import economy
from .cases import CaseError
from .db import connect_database, immediate_transaction
from .seasons import SeasonValidationError


class RedeemPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: int = Field(gt=0, strict=True)


class GrantPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: int = Field(gt=0, strict=True)
    stars_delta: int = Field(default=0, strict=True)
    rep_delta: int = Field(default=0, strict=True)
    reason: str = Field(min_length=1, max_length=300)


def register_economy(app, current_principal, csrf_principal):
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

    @app.get("/api/v4/seasons/{season_id}/economy/overview")
    def economy_overview(season_id: int, principal=Depends(current_principal)):
        with database() as conn:
            conn.execute("BEGIN")
            return economy.overview(conn, principal.account_id, season_id)

    @app.post("/api/v4/seasons/{season_id}/economy/coupons/redeem")
    def economy_redeem(season_id: int, payload: RedeemPayload, request: Request,
                       principal=Depends(csrf_principal)):
        with database() as conn:
            with immediate_transaction(conn):
                result, replayed = economy.redeem_walk(
                    conn, principal.account_id, season_id,
                    request.headers.get("x-idempotency-key", ""), payload.account_id,
                    request.state.request_id,
                )
        return JSONResponse(result, headers={"X-Idempotent-Replayed": str(replayed).lower()})

    @app.post("/api/v4/seasons/{season_id}/economy/grant")
    def economy_grant(season_id: int, payload: GrantPayload, request: Request,
                      principal=Depends(csrf_principal)):
        with database() as conn:
            with immediate_transaction(conn):
                result, replayed = economy.grant(
                    conn, principal.account_id, season_id,
                    request.headers.get("x-idempotency-key", ""), payload.account_id,
                    payload.stars_delta, payload.rep_delta, payload.reason,
                    request.state.request_id,
                )
        return JSONResponse(result, headers={"X-Idempotent-Replayed": str(replayed).lower()})
