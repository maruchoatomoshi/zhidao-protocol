"""Routes reuse the app's session/CSRF dependencies; staff rights are seasonal."""
from contextlib import contextmanager

from fastapi import Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ConfigDict

from . import cases
from .db import connect_database, immediate_transaction
from .seasons import SeasonValidationError


class GrantPayload(BaseModel):
    model_config = ConfigDict(extra='forbid')
    account_ids: list[int] = Field(default_factory=list, max_length=200)
    group_id: int | None = Field(default=None, gt=0)
    amount: int = Field(ge=1, le=7, strict=True)
    reason: str = Field(min_length=1, max_length=300)


def register_cases(app, current_principal, csrf_principal):
    cases.rules()  # Fail startup rather than discover malformed rewards mid-write.

    @contextmanager
    def database():
        conn = connect_database(app.state.db_path)
        try:
            yield conn
        except cases.CaseError as exc:
            raise HTTPException(exc.status, str(exc)) from exc
        except SeasonValidationError as exc:
            raise HTTPException(400, str(exc)) from exc
        finally:
            conn.close()

    @app.get('/api/v4/cases/rules')
    def rules():
        return cases.rules()

    @app.get('/api/v4/cases/context')
    def context(principal=Depends(current_principal)):
        with database() as conn:
            return cases.contexts(conn, principal.account_id)

    @app.get('/api/v4/seasons/{season_id}/cases/state')
    def state(season_id: int, principal=Depends(current_principal)):
        with database() as conn:
            # One snapshot for wallet + inventory + history during concurrent opens.
            conn.execute('BEGIN')
            return cases.state(conn, principal.account_id, season_id)

    @app.get('/api/v4/seasons/{season_id}/cases/history')
    def history(season_id: int, before: int | None = Query(default=None, gt=0), principal=Depends(current_principal)):
        with database() as conn:
            cases.authorize(conn, principal.account_id, season_id)
            return cases.history(conn, principal.account_id, season_id, before)

    @app.get('/api/v4/seasons/{season_id}/cases/inventory')
    def inventory(season_id: int, principal=Depends(current_principal)):
        with database() as conn:
            cases.authorize(conn, principal.account_id, season_id)
            return {'items': cases.inventory(conn, principal.account_id, season_id)}

    @app.post('/api/v4/seasons/{season_id}/cases/open')
    def open_case(season_id: int, request: Request, principal=Depends(csrf_principal)):
        with database() as conn:
            with immediate_transaction(conn):
                result, replayed = cases.open_case(conn, principal.account_id, season_id,
                    request.headers.get('x-idempotency-key', ''), request.state.request_id)
        return JSONResponse(result, headers={'X-Idempotent-Replayed': str(replayed).lower()})

    @app.get('/api/v4/seasons/{season_id}/cases/admin/roster')
    def roster(season_id: int, principal=Depends(current_principal)):
        with database() as conn:
            return cases.roster(conn, principal.account_id, season_id)

    @app.get('/api/v4/seasons/{season_id}/cases/admin/grants')
    def grants(season_id: int, before: int | None = Query(default=None, gt=0), principal=Depends(current_principal)):
        with database() as conn:
            cases.authorize(conn, principal.account_id, season_id, manage=True)
            rows = conn.execute('''SELECT o.*,a.display_name,actor.display_name AS actor_name
                FROM v4_economy_operations o JOIN v4_accounts a ON a.id=o.account_id
                JOIN v4_accounts actor ON actor.id=o.actor_account_id
                WHERE o.season_id=? AND o.operation='case.grant' AND (? IS NULL OR o.id<?)
                ORDER BY o.id DESC LIMIT 50''', (season_id, before, before)).fetchall()
            return {'items': [cases.operation_view(r) for r in rows],
                    'next_before': rows[-1]['id'] if len(rows) == 50 else None}

    @app.post('/api/v4/seasons/{season_id}/cases/admin/grants')
    def grant(season_id: int, payload: GrantPayload, request: Request, principal=Depends(csrf_principal)):
        with database() as conn:
            with immediate_transaction(conn):
                result, replayed = cases.grant(conn, principal.account_id, season_id,
                    request.headers.get('x-idempotency-key', ''), payload.account_ids,
                    payload.group_id, payload.amount, payload.reason, request.state.request_id)
        return JSONResponse(result, headers={'X-Idempotent-Replayed': str(replayed).lower()})
