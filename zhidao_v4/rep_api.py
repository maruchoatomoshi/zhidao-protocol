"""Маршрут REP сезона. Права — как у дневника: участник или организатор сезона."""
from __future__ import annotations

from fastapi import Depends, HTTPException

from . import rep
from .cases import CaseError
from .db import connect_database


def register_rep(app, current_principal):
    @app.get("/api/v4/seasons/{season_id}/rep/board")
    def rep_board(season_id: int, principal=Depends(current_principal)):
        conn = connect_database(app.state.db_path)
        try:
            # Обычная транзакция чтения, без блокировки на запись.
            conn.execute("BEGIN")
            try:
                result = rep.board(conn, principal.account_id, season_id)
                conn.execute("COMMIT")
                return result
            except Exception:
                conn.execute("ROLLBACK")
                raise
        except CaseError as exc:
            raise HTTPException(exc.status, str(exc)) from exc
        finally:
            conn.close()
