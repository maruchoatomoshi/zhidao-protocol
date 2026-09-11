"""Маршруты обмена дубликатами. Права и CSRF — как у кейсов."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from . import meet, trade
from .cases import CaseError
from .db import connect_database, immediate_transaction
from .seasons import SeasonValidationError

JOINS_PER_MINUTE = 10


class OfferPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_code: str = Field(min_length=1, max_length=40)


class JoinPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^\d{6}$")
    item_code: str = Field(min_length=1, max_length=40)


class ConfirmPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    acknowledge_unequal: bool = False


def register_trade(app, current_principal, csrf_principal):
    desk = trade.Desk()
    app.state.trade_desk = desk
    joins = defaultdict(deque)
    joins_lock = threading.Lock()

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

    def consume_join_slot(account_id: int) -> None:
        now = time.monotonic()
        with joins_lock:
            marks = joins[account_id]
            while marks and now - marks[0] >= 60:
                marks.popleft()
            if len(marks) >= JOINS_PER_MINUTE:
                raise HTTPException(429, "Слишком много попыток. Подождите минуту.", headers={"Retry-After": "60"})
            marks.append(now)

    def names_for(conn, entry) -> dict[int, str]:
        ids = [side["account"] for side in (entry["a"], entry["b"]) if side]
        marks = ",".join("?" for _ in ids)
        return {row["id"]: row["display_name"] for row in
                conn.execute(f"SELECT id, display_name FROM v4_accounts WHERE id IN ({marks})", ids)}

    def my_trade(season_id: int, code: str, account_id: int) -> dict:
        entry = desk.find(code)
        if not entry or entry["season_id"] != season_id or trade.side_of(entry, account_id) is None:
            raise HTTPException(404, "Обмен не найден или уже закрыт.")
        return entry

    def render(conn, entry, account_id):
        return trade.view(entry, account_id, names_for(conn, entry), meet.clock())

    @app.get("/api/v4/seasons/{season_id}/trade")
    def trade_overview(season_id: int, principal=Depends(current_principal)):
        with database() as conn:
            conn.execute("BEGIN")
            body = trade.overview(conn, principal.account_id, season_id)
        code = desk.by_account.get(principal.account_id)
        current = desk.find(code) if code else None
        body["current"] = code if current and current["state"] in ("open", "ready") else None
        return body

    @app.post("/api/v4/seasons/{season_id}/trade/offer")
    def trade_offer(season_id: int, payload: OfferPayload, principal=Depends(csrf_principal)):
        with database() as conn:
            conn.execute("BEGIN")
            trade.check_side(conn, principal.account_id, season_id, payload.item_code)
            entry = desk.create(principal.account_id, season_id, payload.item_code)
            return render(conn, entry, principal.account_id)

    @app.post("/api/v4/seasons/{season_id}/trade/join")
    def trade_join(season_id: int, payload: JoinPayload, principal=Depends(csrf_principal)):
        consume_join_slot(principal.account_id)
        entry = desk.find(payload.code)
        now = meet.clock()
        if not entry or entry["season_id"] != season_id or not desk.live(entry, now):
            raise HTTPException(404, "Код не найден или уже истёк. Попросите показать новый.")
        if entry["a"]["account"] == principal.account_id:
            raise HTTPException(409, "Это ваш собственный обмен. Покажите код другому человеку.")
        with database() as conn:
            conn.execute("BEGIN")
            trade.check_side(conn, principal.account_id, season_id, payload.item_code)
            with desk.lock:
                if entry["b"] and entry["b"]["account"] != principal.account_id:
                    raise HTTPException(409, "К этому обмену уже подключился другой человек.")
                if entry["state"] not in ("open", "ready"):
                    raise HTTPException(404, "Код не найден или уже истёк. Попросите показать новый.")
                entry["b"] = {"account": principal.account_id, "item": payload.item_code, "confirmed": False}
                # Состав поменялся — прежние подтверждения больше ничего не значат.
                entry["a"]["confirmed"] = False
                entry["state"] = "ready"
                desk.by_account[principal.account_id] = entry["code"]
            return render(conn, entry, principal.account_id)

    @app.get("/api/v4/seasons/{season_id}/trade/{code}")
    def trade_view(season_id: int, code: str, principal=Depends(current_principal)):
        entry = my_trade(season_id, code, principal.account_id)
        with database() as conn:
            return render(conn, entry, principal.account_id)

    @app.post("/api/v4/seasons/{season_id}/trade/{code}/confirm")
    def trade_confirm(season_id: int, code: str, payload: ConfirmPayload, principal=Depends(csrf_principal)):
        entry = my_trade(season_id, code, principal.account_id)
        side = trade.side_of(entry, principal.account_id)
        with desk.lock:
            if entry["state"] != "ready" or not desk.live(entry, meet.clock()):
                raise HTTPException(409, "Обмен ещё не готов или уже закрыт.")
            if trade.gives_rarer(entry, side) and not payload.acknowledge_unequal:
                raise HTTPException(409, "Вы отдаёте более редкий предмет. Подтвердите неравный обмен.")
            entry[side]["confirmed"] = True
            run = entry["a"]["confirmed"] and entry["b"]["confirmed"] and not entry["executing"]
            if run:
                entry["executing"] = True
        if run:
            try:
                with database() as conn:
                    with immediate_transaction(conn):
                        entry["results"] = trade.execute(conn, season_id, entry)
                entry["state"] = "done"
            except HTTPException as exc:
                entry["state"] = "failed"
                entry["message"] = f"Обмен не состоялся: {exc.detail}"
            finally:
                entry["executing"] = False
        with database() as conn:
            return render(conn, entry, principal.account_id)

    @app.post("/api/v4/seasons/{season_id}/trade/{code}/cancel")
    def trade_cancel(season_id: int, code: str, principal=Depends(csrf_principal)):
        entry = my_trade(season_id, code, principal.account_id)
        with desk.lock:
            if entry["state"] in ("open", "ready") and not entry["executing"]:
                entry["state"] = "cancelled"
                entry["message"] = "Обмен отменён."
        with database() as conn:
            return render(conn, entry, principal.account_id)
