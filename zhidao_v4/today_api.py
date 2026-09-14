"""Маршрут «Сейчас в сезоне» для главной. Сезон — как у тумана, права — как у истории."""
from __future__ import annotations

from fastapi import Depends, HTTPException

from . import campus, today
from .cases import CaseError
from .db import connect_database


def register_today(app, current_principal):
    @app.get("/api/v4/today")
    def today_view(principal=Depends(current_principal)):
        conn = connect_database(app.state.db_path)
        try:
            season_id = campus.active_season_id(conn, principal.account_id)
            if season_id is None:
                return {"season_id": None, "items": []}
            # Обычная транзакция чтения: шестьдесят главных раз в минуту не должны
            # брать блокировку на запись.
            conn.execute("BEGIN")
            try:
                result = today.snapshot(conn, principal.account_id, season_id)
                conn.execute("COMMIT")
                return result
            except Exception:
                conn.execute("ROLLBACK")
                raise
        except CaseError as exc:
            raise HTTPException(exc.status, str(exc)) from exc
        finally:
            conn.close()
