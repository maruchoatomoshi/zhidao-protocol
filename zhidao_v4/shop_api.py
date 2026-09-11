"""Маршруты витрины дня. Права, CSRF и защита от повтора — как у кейсов."""
from contextlib import contextmanager
from typing import Literal

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import shop
from .cases import CaseError
from .db import connect_database, immediate_transaction
from .seasons import SeasonValidationError


class BuyPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_code: str = Field(min_length=1, max_length=40)
    # День витрины, которую видел покупатель: вчерашняя витрина не продаёт.
    shop_day: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class EquipPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slot: Literal["wallpaper", "frame", "sounds"]
    item_code: str | None = Field(default=None, max_length=40)


def register_shop(app, current_principal, csrf_principal):
    shop.catalogue()  # Битый каталог — ошибка старта, а не посреди покупки.

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

    @app.get("/api/v4/shop/catalogue")
    def shop_catalogue():
        return shop.catalogue()

    @app.get("/api/v4/seasons/{season_id}/shop")
    def shop_state(season_id: int, principal=Depends(current_principal)):
        with database() as conn:
            # Первое открытие витрины за день сохраняет её набор — это запись.
            with immediate_transaction(conn):
                return shop.state(conn, principal.account_id, season_id)

    @app.post("/api/v4/seasons/{season_id}/shop/buy")
    def shop_buy(season_id: int, payload: BuyPayload, request: Request, principal=Depends(csrf_principal)):
        with database() as conn:
            with immediate_transaction(conn):
                result, replayed = shop.buy(
                    conn, principal.account_id, season_id, request.headers.get("x-idempotency-key", ""),
                    payload.item_code, payload.shop_day, request.state.request_id,
                )
        return JSONResponse(result, headers={"X-Idempotent-Replayed": str(replayed).lower()})

    @app.post("/api/v4/seasons/{season_id}/shop/equip")
    def shop_equip(season_id: int, payload: EquipPayload, principal=Depends(csrf_principal)):
        with database() as conn:
            with immediate_transaction(conn):
                return shop.equip(conn, principal.account_id, season_id, payload.slot, payload.item_code)
