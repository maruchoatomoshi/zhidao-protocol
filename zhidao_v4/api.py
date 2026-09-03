from __future__ import annotations

import os
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .admin import architect_overview
from .auth import (
    AuthenticationError,
    Principal,
    authenticate_local,
    csrf_is_valid,
    load_principal,
    revoke_session,
)
from .db import connect_database, immediate_transaction
from .migrations import apply_migrations
from .seasons import (
    IdempotencyConflict,
    SeasonConflict,
    SeasonNotFound,
    SeasonRevisionConflict,
    SeasonStateConflict,
    SeasonValidationError,
    create_draft_season,
    list_seasons,
    update_draft_season,
)


SESSION_COOKIE = "zhidao_v4_session"
CSRF_COOKIE = "zhidao_v4_csrf"
ARCHITECT_STATIC_DIR = Path(__file__).resolve().parent / "static" / "architect"
APP_STATIC_DIR = Path(__file__).resolve().parent / "static" / "app"


class LoginPayload(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class SeasonCreatePayload(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    starts_on: date | None = None
    ends_on: date | None = None
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=64)
    theme_key: str | None = Field(default=None, max_length=64)


class SeasonUpdatePayload(BaseModel):
    expected_revision: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=120)
    starts_on: date | None = None
    ends_on: date | None = None
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=64)
    theme_key: str | None = Field(default=None, max_length=64)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_db_path(db_path: str | Path | None) -> str:
    if db_path is not None:
        return str(db_path)
    configured = os.getenv("ZHIDAO_V4_DB_PATH") or os.getenv("ZHIDAO_DB_PATH")
    if not configured:
        raise RuntimeError("ZHIDAO_V4_DB_PATH or ZHIDAO_DB_PATH is required")
    return configured


def _current_principal(request: Request) -> Principal:
    principal = load_principal(
        request.app.state.db_path,
        request.cookies.get(SESSION_COOKIE),
    )
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return principal


def _csrf_principal(
    request: Request,
    principal: Principal = Depends(_current_principal),
) -> Principal:
    if not csrf_is_valid(
        principal,
        request.headers.get("x-csrf-token"),
        request.cookies.get(CSRF_COOKIE),
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")
    return principal


def _system_admin(
    principal: Principal = Depends(_csrf_principal),
) -> Principal:
    if not principal.has_global_role("system_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
    return principal


def _architect_reader(
    principal: Principal = Depends(_current_principal),
) -> Principal:
    if not (
        principal.has_global_role("architect")
        or principal.has_global_role("system_admin")
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
    return principal


def _architect_writer(
    principal: Principal = Depends(_csrf_principal),
) -> Principal:
    if not (
        principal.has_global_role("architect")
        or principal.has_global_role("system_admin")
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
    return principal


def create_app(
    db_path: str | Path | None = None,
    *,
    cookie_secure: bool | None = None,
    session_hours: int | None = None,
    login_attempts_per_minute: int | None = None,
) -> FastAPI:
    resolved_db_path = _resolve_db_path(db_path)
    apply_migrations(resolved_db_path)

    app = FastAPI(title="ZHIDAO Protocol V4 API", version="4.0.0-foundation")
    app.state.db_path = resolved_db_path
    app.state.cookie_secure = (
        _env_bool("ZHIDAO_V4_COOKIE_SECURE", True)
        if cookie_secure is None
        else bool(cookie_secure)
    )
    configured_hours = session_hours or int(os.getenv("ZHIDAO_V4_SESSION_HOURS", "12"))
    app.state.session_hours = max(1, min(configured_hours, 168))
    configured_login_limit = login_attempts_per_minute or int(
        os.getenv("ZHIDAO_V4_LOGIN_ATTEMPTS_PER_MINUTE", "120")
    )
    app.state.login_attempts_per_minute = max(1, min(configured_login_limit, 1000))
    app.state.login_attempts = defaultdict(deque)
    app.state.login_attempts_lock = threading.Lock()

    def consume_login_slot(request: Request) -> None:
        client_host = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with app.state.login_attempts_lock:
            attempts = app.state.login_attempts[client_host]
            while attempts and now - attempts[0] >= 60:
                attempts.popleft()
            if len(attempts) >= app.state.login_attempts_per_minute:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many login attempts",
                    headers={"Retry-After": "60"},
                )
            attempts.append(now)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        request.state.request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.path.startswith(("/architect", "/app")):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; style-src 'self'; script-src 'self'; "
                "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
                "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
            )
        if request.url.path.startswith("/api/v4/auth"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/v4/health")
    def health():
        conn = connect_database(app.state.db_path)
        try:
            version = conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM v4_schema_migrations"
            ).fetchone()[0]
        finally:
            conn.close()
        return {"status": "ok", "mode": "travel-v4", "schema_version": int(version)}

    @app.post("/api/v4/auth/login")
    def login(payload: LoginPayload, request: Request):
        consume_login_slot(request)
        try:
            result = authenticate_local(
                app.state.db_path,
                username=payload.username,
                password=payload.password,
                session_hours=app.state.session_hours,
            )
        except AuthenticationError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            ) from None

        body = {
            "account": {
                "id": result.principal.account_id,
                "public_id": result.principal.public_id,
                "display_name": result.principal.display_name,
            },
            "roles": [
                {"code": role.code, "season_id": role.season_id}
                for role in result.principal.roles
            ],
            "csrf_token": result.csrf_token,
            "expires_at": result.principal.expires_at,
        }
        response = JSONResponse(body)
        response.set_cookie(
            SESSION_COOKIE,
            result.session_token,
            max_age=result.max_age_seconds,
            httponly=True,
            secure=app.state.cookie_secure,
            samesite="lax",
            path="/",
        )
        response.set_cookie(
            CSRF_COOKIE,
            result.csrf_token,
            max_age=result.max_age_seconds,
            httponly=False,
            secure=app.state.cookie_secure,
            samesite="lax",
            path="/",
        )
        return response

    @app.get("/api/v4/auth/me")
    def me(principal: Principal = Depends(_current_principal)):
        return {
            "account": {
                "id": principal.account_id,
                "public_id": principal.public_id,
                "display_name": principal.display_name,
            },
            "roles": [
                {"code": role.code, "season_id": role.season_id}
                for role in principal.roles
            ],
            "expires_at": principal.expires_at,
        }

    @app.post("/api/v4/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
    def logout(
        principal: Principal = Depends(_csrf_principal),
    ):
        revoke_session(app.state.db_path, principal)
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        response.delete_cookie(
            SESSION_COOKIE,
            path="/",
            secure=app.state.cookie_secure,
            httponly=True,
            samesite="lax",
        )
        response.delete_cookie(
            CSRF_COOKIE,
            path="/",
            secure=app.state.cookie_secure,
            httponly=False,
            samesite="lax",
        )
        return response

    @app.get("/api/v4/seasons")
    def seasons(principal: Principal = Depends(_current_principal)):
        del principal
        conn = connect_database(app.state.db_path)
        try:
            return {"items": list_seasons(conn)}
        finally:
            conn.close()

    @app.post("/api/v4/seasons", status_code=status.HTTP_201_CREATED)
    def create_season(
        payload: SeasonCreatePayload,
        request: Request,
        principal: Principal = Depends(_system_admin),
    ):
        idempotency_key = request.headers.get("x-idempotency-key", "")
        conn = connect_database(app.state.db_path)
        try:
            with immediate_transaction(conn):
                season, replayed = create_draft_season(
                    conn,
                    actor_account_id=principal.account_id,
                    idempotency_key=idempotency_key,
                    request_id=request.state.request_id,
                    code=payload.code,
                    name=payload.name,
                    starts_on=payload.starts_on,
                    ends_on=payload.ends_on,
                    timezone=payload.timezone,
                    theme_key=payload.theme_key,
                )
        except SeasonValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except IdempotencyConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except SeasonConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        finally:
            conn.close()

        response = JSONResponse(season, status_code=status.HTTP_201_CREATED)
        response.headers["X-Idempotent-Replayed"] = str(replayed).lower()
        return response

    @app.patch("/api/v4/seasons/{season_id}")
    def update_season(
        season_id: int,
        payload: SeasonUpdatePayload,
        request: Request,
        principal: Principal = Depends(_architect_writer),
    ):
        idempotency_key = request.headers.get("x-idempotency-key", "")
        conn = connect_database(app.state.db_path)
        try:
            with immediate_transaction(conn):
                season, replayed = update_draft_season(
                    conn,
                    season_id=season_id,
                    actor_account_id=principal.account_id,
                    expected_revision=payload.expected_revision,
                    idempotency_key=idempotency_key,
                    request_id=request.state.request_id,
                    name=payload.name,
                    starts_on=payload.starts_on,
                    ends_on=payload.ends_on,
                    timezone=payload.timezone,
                    theme_key=payload.theme_key,
                )
        except SeasonValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except SeasonNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (IdempotencyConflict, SeasonStateConflict, SeasonRevisionConflict) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        finally:
            conn.close()

        response = JSONResponse(season)
        response.headers["X-Idempotent-Replayed"] = str(replayed).lower()
        return response

    @app.get("/api/v4/admin/overview")
    def admin_overview(principal: Principal = Depends(_architect_reader)):
        del principal
        conn = connect_database(app.state.db_path)
        try:
            return architect_overview(conn)
        finally:
            conn.close()

    @app.get("/", include_in_schema=False)
    def root_redirect():
        return RedirectResponse(url="/architect/")

    app.mount(
        "/architect",
        StaticFiles(directory=ARCHITECT_STATIC_DIR, html=True),
        name="architect-console",
    )
    app.mount(
        "/app",
        StaticFiles(directory=APP_STATIC_DIR, html=True),
        name="participant-app-preview",
    )

    return app
