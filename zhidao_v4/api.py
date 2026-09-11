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

from . import campus
from .admin import architect_overview
from .cases_api import register_cases
from .diary_api import register_diary
from .economy_api import register_economy
from .shop_api import register_shop
from .meet_api import register_meet
from .games_api import register_games
from .auth import (
    AuthenticationError,
    IdentityAlreadyLinkedError,
    LinkRequiredError,
    Principal,
    authenticate_local,
    authenticate_max,
    create_link_code,
    csrf_is_valid,
    load_principal,
    revoke_session,
)
from .max_auth import MaxAuthError, parse_user, verify_launch_params
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


class MaxLoginPayload(BaseModel):
    # window.WebApp.initData, forwarded byte-for-byte. Do not let a client
    # send parsed fields instead — the signature covers the exact string.
    launch_params: str = Field(min_length=1, max_length=4096)
    link_code: str | None = Field(default=None, min_length=6, max_length=16)


class CampusVisitPayload(BaseModel):
    # Границы — земные, а не кампусные: они отсекают мусор и опечатки, а
    # принадлежность к кампусу проверяет campus.inside_campus.
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    accuracy_m: float | None = Field(default=None, ge=0.0, le=100000.0)


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


def _cookie_samesite(secure: bool) -> str:
    """Значение SameSite для сессионной и CSRF-куки.

    Мини-приложение MAX на телефоне живёт в нативном WebView — первая
    сторона, и `Lax` там работает. В веб- и десктоп-клиенте то же
    приложение открывается **в iframe на max.ru**, а `Lax`-кука в
    кросс-сайтовом фрейме не отправляется. Выглядело это как «вход не
    работает»: сервер отвечал 200 и ставил куку, браузер её выбрасывал, и
    следующий запрос приходил без сессии — приложение возвращало на экран
    входа. В журнале при этом пять `auth.login_succeeded` подряд за две
    секунды.

    `None` требует `Secure`, иначе браузер отвергает куку целиком. Поэтому
    по http (локальная разработка) остаётся `Lax`: там никакого чужого
    фрейма и нет.

    Защита от CSRF на этом не держалась и не ослабевает: `_csrf_principal`
    сверяет заголовок `X-CSRF-Token` с кукой на каждом изменяющем запросе, а
    заголовок чужой сайт подставить не может.

    Не сделано намеренно: атрибут `Partitioned` (CHIPS). Он понадобится,
    если клиент начнёт блокировать сторонние куки целиком, но у него своя
    цена — `delete_cookie` в Starlette его не умеет, и выход из аккаунта
    пришлось бы собирать руками.
    """
    return "none" if secure else "lax"


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


def _operator_writer(
    principal: Principal = Depends(_csrf_principal),
) -> Principal:
    if not (
        principal.has_global_role("operator")
        or principal.has_global_role("architect")
        or principal.has_global_role("system_admin")
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
    return principal


def _operator_reader(
    principal: Principal = Depends(_current_principal),
) -> Principal:
    """Как _operator_writer, но без CSRF: чтение ростера ничего не меняет."""
    if not (
        principal.has_global_role("operator")
        or principal.has_global_role("architect")
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
    # Отметки на карте считаются по аккаунту и только в памяти: в базе у
    # клетки нет владельца, и заводить его ради ограничения частоты значило
    # бы завести историю перемещений — ровно то, чего мы не храним.
    app.state.campus_visits = defaultdict(deque)
    app.state.campus_visits_lock = threading.Lock()
    # Unset by default: MAX sign-in is opt-in infrastructure, not core to
    # bringing the API up. Registering the bot on business.max.ru/self is a
    # step the user does themselves; nothing here should block on it.
    app.state.max_bot_token = os.getenv("ZHIDAO_V4_MAX_BOT_TOKEN") or None

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
        response.headers["Referrer-Policy"] = "same-origin"
        # Геолокация нужна только участнику на /app/ и запрашивается явной
        # кнопкой «Где я». В консоли архитектора она остаётся запрещённой.
        is_participant_app = (
            request.url.path == "/app" or request.url.path.startswith("/app/")
        )
        geolocation = "(self)" if is_participant_app else "()"
        response.headers["Permissions-Policy"] = (
            f"camera=(), microphone=(), geolocation={geolocation}"
        )
        # Мини-приложение MAX открывается внутри клиента MAX: на телефоне это
        # нативный WebView (рамочные правила там не действуют), а в веб- и
        # десктоп-клиенте — iframe. Поэтому только для /app/ разрешаем
        # встраивание с доменов MAX и убираем X-Frame-Options: у него нет
        # рабочего синтаксиса со списком источников (ALLOW-FROM браузеры не
        # поддерживают), и его присутствие всё равно запретило бы фрейм.
        # Консоль архитектора остаётся полностью незакладываемой в рамку.
        if is_participant_app:
            frame_ancestors = "frame-ancestors 'self' https://max.ru https://*.max.ru"
        else:
            response.headers["X-Frame-Options"] = "DENY"
            frame_ancestors = "frame-ancestors 'none'"
        if request.url.path.startswith(("/architect", "/app")):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; style-src 'self'; script-src 'self'; "
                "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
                f"base-uri 'none'; {frame_ancestors}; form-action 'self'"
            )
        if request.url.path.startswith(("/architect", "/app")):
            # Заголовка Cache-Control здесь не было вовсе, и это ломало ровно
            # ту схему, ради которой существуют теги `?v=`: без него браузер
            # выбирает срок хранения сам (обычно доля времени с
            # last-modified), и index.html — единственный файл, где эти теги
            # записаны, — может отдаваться устаревшим. Тогда обновление на
            # сервере просто не доходит до человека, и выглядит это как
            # «ничего не изменилось».
            #
            # Правило: адрес с версией неизменен по построению, его можно
            # держать сколько угодно. Всё остальное, и прежде всего сама
            # страница, обязано спрашивать сервер — с ETag это стоит одного
            # 304 и почти ничего не весит даже на плохой связи.
            if "v" in request.query_params:
                response.headers.setdefault(
                    "Cache-Control", "public, max-age=31536000, immutable"
                )
            else:
                response.headers.setdefault("Cache-Control", "no-cache")
        if request.url.path.startswith("/api/v4/"):
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
            samesite=_cookie_samesite(app.state.cookie_secure),
            path="/",
        )
        response.set_cookie(
            CSRF_COOKIE,
            result.csrf_token,
            max_age=result.max_age_seconds,
            httponly=False,
            secure=app.state.cookie_secure,
            samesite=_cookie_samesite(app.state.cookie_secure),
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
            samesite=_cookie_samesite(app.state.cookie_secure),
        )
        response.delete_cookie(
            CSRF_COOKIE,
            path="/",
            secure=app.state.cookie_secure,
            httponly=False,
            samesite=_cookie_samesite(app.state.cookie_secure),
        )
        return response

    @app.post("/api/v4/auth/max")
    def login_max(payload: MaxLoginPayload, request: Request):
        consume_login_slot(request)
        if not app.state.max_bot_token:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="MAX sign-in is not configured on this server",
            )
        try:
            fields = verify_launch_params(payload.launch_params, app.state.max_bot_token)
            max_user = parse_user(fields)
        except MaxAuthError:
            # Same shape whether the signature failed or the payload was
            # malformed: neither tells an attacker anything more useful than
            # "no".
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not verify MAX launch data",
            ) from None

        try:
            result = authenticate_max(
                app.state.db_path,
                max_user_id=max_user.user_id,
                max_username=max_user.username,
                link_code=payload.link_code,
                session_hours=app.state.session_hours,
            )
        except IdentityAlreadyLinkedError:
            # Тоже 409 и тоже экран сопряжения, но причина другая, и человеку
            # надо сказать другое: новый код здесь не поможет.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "reason": "account_already_linked",
                    "message": (
                        "Этот аккаунт уже привязан к другому MAX. "
                        "Новый код не поможет — нужно снять прежнюю привязку."
                    ),
                },
            ) from None
        except LinkRequiredError:
            # 409, not 401: MAX proved who this is, they just have not typed
            # the code a counsellor gave them yet. The frontend shows a
            # pairing screen for this status, not a login failure.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "reason": "link_required",
                    "message": "Введите код сопряжения, который выдал вожатый.",
                },
            ) from None
        except AuthenticationError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not sign in with this MAX account",
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
            samesite=_cookie_samesite(app.state.cookie_secure),
            path="/",
        )
        response.set_cookie(
            CSRF_COOKIE,
            result.csrf_token,
            max_age=result.max_age_seconds,
            httponly=False,
            secure=app.state.cookie_secure,
            samesite=_cookie_samesite(app.state.cookie_secure),
            path="/",
        )
        return response

    @app.get("/api/v4/admin/accounts")
    def list_accounts(
        query: str | None = None,
        limit: int = 25,
        principal: Principal = Depends(_operator_reader),
    ):
        """Ростер для вожатого: по кому выдавать код сопряжения.

        Существует потому, что без него единственный способ выдать код —
        знать числовой `account_id`, которого никто наизусть не помнит.
        Отдаёт ровно то, что нужно для этого решения: как человека зовут,
        активен ли он и привязан ли уже его MAX. Ни паролей, ни хэшей, ни
        внешних идентификаторов мессенджера здесь нет: знать, что привязка
        есть, вожатому нужно, а знать чужой MAX-идентификатор — нет.
        """
        del principal
        clean_query = (query or "").strip()
        limit = max(1, min(limit, 200))
        conn = connect_database(app.state.db_path)
        try:
            sql = """
                SELECT a.id, a.public_id, a.display_name, a.status,
                       (SELECT COUNT(*) FROM v4_external_identities e
                         WHERE e.account_id = a.id AND e.provider_code = 'max')
                           AS max_linked,
                       (SELECT e.provider_subject FROM v4_external_identities e
                         WHERE e.account_id = a.id AND e.provider_code = 'local')
                           AS login
                  FROM v4_accounts a
            """
            params: list[object] = []
            if clean_query:
                # LIKE с экранированием: иначе введённый вожатым процент или
                # подчёркивание молча превратятся в шаблон.
                escaped = (
                    clean_query.replace("\\", "\\\\")
                    .replace("%", "\\%")
                    .replace("_", "\\_")
                )
                sql += " WHERE a.display_name LIKE ? ESCAPE '\\'"
                params.append(f"%{escaped}%")
            sql += " ORDER BY a.display_name COLLATE NOCASE LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()
        return {
            "items": [
                {
                    "id": int(row["id"]),
                    "public_id": str(row["public_id"]),
                    "display_name": str(row["display_name"]),
                    "status": str(row["status"]),
                    "login": row["login"],
                    "max_linked": bool(row["max_linked"]),
                }
                for row in rows
            ]
        }

    @app.post("/api/v4/admin/accounts/{account_id}/link-codes")
    def issue_max_link_code(
        account_id: int,
        principal: Principal = Depends(_operator_writer),
    ):
        # No idempotency ledger here on purpose, unlike season writes: a
        # duplicate call just invalidates the previous code and issues a new
        # one (create_link_code already does that), which is a harmless
        # outcome for a counsellor double-tapping a button — nothing like
        # the double-charge risk idempotency keys guard against elsewhere.
        conn = connect_database(app.state.db_path)
        try:
            with immediate_transaction(conn):
                account_exists = conn.execute(
                    "SELECT 1 FROM v4_accounts WHERE id = ? AND status = 'active'",
                    (account_id,),
                ).fetchone()
                if account_exists is None:
                    raise HTTPException(status_code=404, detail="Account not found")
                code = create_link_code(
                    conn,
                    account_id=account_id,
                    provider_code="max",
                    actor_account_id=principal.account_id,
                )
        finally:
            conn.close()
        # Plaintext leaves the server exactly once, in this response. The
        # database only ever holds its hash from this point on.
        return {"code": code, "provider_code": "max", "ttl_minutes": 30}

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

    def consume_campus_slot(account_id: int) -> None:
        now = time.monotonic()
        with app.state.campus_visits_lock:
            marks = app.state.campus_visits[account_id]
            while marks and now - marks[0] >= 60:
                marks.popleft()
            if len(marks) >= 12:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Слишком часто. Карта никуда не денется.",
                    headers={"Retry-After": "60"},
                )
            marks.append(now)

    @app.get("/api/v4/campus/exploration")
    def campus_exploration(principal: Principal = Depends(_current_principal)):
        """Открытые клетки текущего сезона — в формате опорных точек карты."""
        conn = connect_database(app.state.db_path)
        try:
            season_id = campus.active_season_id(conn, principal.account_id)
            if season_id is None:
                # Не ошибка: сезон ещё не запущен или человек в него не введён.
                # Карта в этом случае показывает подготовленную область, как и
                # раньше, а не пустоту.
                return {"season_id": None, "opened": 0, "anchor_points": []}
            return campus.exploration(conn, season_id)
        finally:
            conn.close()

    @app.post("/api/v4/campus/visits")
    def campus_visit(
        payload: CampusVisitPayload,
        principal: Principal = Depends(_csrf_principal),
    ):
        """Отмечает, что здесь были. Открытая клетка видна всем в сезоне."""
        consume_campus_slot(principal.account_id)
        conn = connect_database(app.state.db_path)
        try:
            season_id = campus.active_season_id(conn, principal.account_id)
            if season_id is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Нет активного сезона: открывать карту пока некому.",
                )
            with immediate_transaction(conn):
                try:
                    return campus.record_visit(
                        conn,
                        season_id,
                        lon=payload.lon,
                        lat=payload.lat,
                        accuracy_m=payload.accuracy_m,
                    )
                except campus.CampusError as exc:
                    raise HTTPException(
                        status_code=exc.status_code, detail=str(exc)
                    ) from exc
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

    register_cases(app, _current_principal, _csrf_principal)
    register_diary(app, _current_principal, _csrf_principal)
    register_economy(app, _current_principal, _csrf_principal)
    register_shop(app, _current_principal, _csrf_principal)
    register_meet(app, _current_principal, _csrf_principal)
    register_games(app, _current_principal, _csrf_principal, _architect_writer)
    return app
