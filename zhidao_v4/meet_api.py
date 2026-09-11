"""Маршруты рукопожатия и пазла встреч. Права и CSRF — как у кейсов."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from . import meet
from .cases import CaseError, authorize
from .db import connect_database, immediate_transaction
from .seasons import SeasonValidationError

ACCEPTS_PER_MINUTE = 10


class AcceptPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^\d{6}$")


def register_meet(app, current_principal, csrf_principal):
    meet.puzzles()  # Битый список пазлов — ошибка старта.
    app.state.meet_offers = meet.Offers()
    app.state.meet_accepts = defaultdict(deque)
    app.state.meet_accepts_lock = threading.Lock()

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

    def consume_accept_slot(account_id: int) -> None:
        # Кодов миллион, живут минуту; ограничение делает перебор бессмысленным.
        now = time.monotonic()
        with app.state.meet_accepts_lock:
            marks = app.state.meet_accepts[account_id]
            while marks and now - marks[0] >= 60:
                marks.popleft()
            if len(marks) >= ACCEPTS_PER_MINUTE:
                raise HTTPException(429, "Слишком много попыток. Подождите минуту.", headers={"Retry-After": "60"})
            marks.append(now)

    @app.get("/api/v4/seasons/{season_id}/puzzles")
    def puzzle_state(season_id: int, principal=Depends(current_principal)):
        with database() as conn:
            with immediate_transaction(conn):
                return meet.state(conn, principal.account_id, season_id)

    @app.post("/api/v4/seasons/{season_id}/meet/offer")
    def meet_offer(season_id: int, principal=Depends(csrf_principal)):
        with database() as conn:
            conn.execute("BEGIN")
            authorize(conn, principal.account_id, season_id, write=True)
        return app.state.meet_offers.create(principal.account_id, season_id)

    @app.get("/api/v4/seasons/{season_id}/meet/offer/{code}")
    def meet_offer_status(season_id: int, code: str, principal=Depends(current_principal)):
        offer = app.state.meet_offers.peek(code)
        # Чужой или неизвестный код выглядит одинаково: истёк.
        if not offer or offer["account_id"] != principal.account_id or offer["season_id"] != season_id:
            return {"state": "expired"}
        result = offer["result"]
        if result and result.get("state") != "claimed":
            return result
        return {"state": "waiting" if offer["live"] else "expired", "expires_in": offer["expires_in"]}

    @app.post("/api/v4/seasons/{season_id}/meet/accept")
    def meet_accept(season_id: int, payload: AcceptPayload, principal=Depends(csrf_principal)):
        consume_accept_slot(principal.account_id)
        offers = app.state.meet_offers
        offer = offers.peek(payload.code)
        if not offer or not offer["live"] or offer["season_id"] != season_id:
            raise HTTPException(404, "Код не найден или уже истёк. Попросите показать новый.")
        if offer["account_id"] == principal.account_id:
            raise HTTPException(409, "Это ваш собственный код. Покажите его другому человеку.")
        claimed = offers.claim(payload.code)
        if not claimed:
            raise HTTPException(404, "Код не найден или уже истёк. Попросите показать новый.")
        try:
            with database() as conn:
                with immediate_transaction(conn):
                    results = meet.meet(conn, season_id, claimed["account_id"], principal.account_id)
        except Exception:
            offers.release(payload.code)
            raise
        offers.finish(payload.code, results[claimed["account_id"]])
        return results[principal.account_id]
