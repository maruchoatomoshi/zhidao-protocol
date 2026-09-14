"""Маршруты Рынка Контрабанды. Права и CSRF — как у Тайного агента, сезон — как у тумана."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from . import campus, market
from .cases import CaseError
from .db import connect_database, immediate_transaction
from .seasons import SeasonValidationError

ACTIONS_PER_MINUTE = 40
# Кодов миллион, живут минуты; ограничение делает перебор бессмысленным.
CODES_PER_MINUTE = 10


class Basket(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goods: dict[str, int] = Field(default_factory=dict, max_length=12)
    money: int = Field(default=0, strict=True, ge=0, le=100000)


class OfferPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    give: Basket
    want: Basket


class CodePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^\d{6}$")


def register_market(app, current_principal, csrf_principal):
    market.config()  # битый market.json — ошибка старта, а не посреди дня
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
        except SeasonValidationError as exc:
            raise HTTPException(400, str(exc)) from exc
        finally:
            conn.close()

    def season_of(conn, account_id: int) -> int:
        season_id = campus.active_season_id(conn, account_id)
        if season_id is None:
            raise HTTPException(409, "Нет активного сезона.")
        return season_id

    def write(principal, handler, kind="act", limit=ACTIONS_PER_MINUTE):
        throttle(kind, principal.account_id, limit)
        with database() as conn:
            season_id = season_of(conn, principal.account_id)
            with immediate_transaction(conn):
                return handler(conn, principal.account_id, season_id)

    @app.get("/api/v4/market")
    def market_view(principal=Depends(current_principal)):
        with database() as conn:
            season_id = campus.active_season_id(conn, principal.account_id)
            if season_id is None:
                return {"season_id": None, "me": None, "can_play": False}
            # Запись нужна, только когда пора подвести итоги дня или провести жребий патрульных.
            try:
                conn.execute("BEGIN")
                result = market.current(conn, principal.account_id, season_id, allow_write=False)
                conn.execute("COMMIT")
                return result
            except market.NeedsWrite:
                conn.execute("ROLLBACK")
            with immediate_transaction(conn):
                return market.current(conn, principal.account_id, season_id, allow_write=True)

    @app.post("/api/v4/market/join")
    def market_join(principal=Depends(csrf_principal)):
        return write(principal, market.join)

    @app.post("/api/v4/market/offer")
    def market_offer(payload: OfferPayload, principal=Depends(csrf_principal)):
        give, want = payload.give.model_dump(), payload.want.model_dump()
        return write(principal, lambda conn, actor, season_id: market.make_offer(conn, actor, season_id, give, want))

    @app.post("/api/v4/market/offer/cancel")
    def market_offer_cancel(principal=Depends(csrf_principal)):
        return write(principal, market.cancel_offer)

    @app.get("/api/v4/market/offers/{code}")
    def market_peek(code: str, principal=Depends(current_principal)):
        throttle("code", principal.account_id, CODES_PER_MINUTE)
        if not (len(code) == 6 and code.isdigit()):
            raise HTTPException(404, "Код не найден или истёк. Попросите показать новый.")
        with database() as conn:
            season_id = season_of(conn, principal.account_id)
            return market.peek(conn, principal.account_id, season_id, code)

    @app.post("/api/v4/market/accept")
    def market_accept(payload: CodePayload, principal=Depends(csrf_principal)):
        return write(principal, lambda conn, actor, season_id: market.accept(conn, actor, season_id, payload.code),
                     kind="code", limit=CODES_PER_MINUTE)

    @app.post("/api/v4/market/inspect")
    def market_inspect(payload: CodePayload, principal=Depends(csrf_principal)):
        return write(principal, lambda conn, actor, season_id: market.inspect(conn, actor, season_id, payload.code),
                     kind="code", limit=CODES_PER_MINUTE)
