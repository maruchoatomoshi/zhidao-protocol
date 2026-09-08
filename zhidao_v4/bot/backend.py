"""Клиент API V4 для бота.

Бот ходит в собственный API приложения по HTTP под служебной учёткой с
ролью оператора. Он **не открывает файл базы**. Причина в CLAUDE.md и в
аварии 2026-06-09: в сезоне 1 бот был вторым писателем в ту же SQLite,
держал write-lock через сетевые вызовы мессенджера, и запросы к API
вставали на 27–1463 секунды. Единственный писатель — API.

Побочная выгода: всё, что делает бот, проходит те же проверки ролей и
попадает в тот же журнал (`v4_audit_log`), что и действия человека в
консоли. «Кто выдал этот код» остаётся ответимым вопросом.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx


LOG = logging.getLogger("zhidao.bot.backend")

SESSION_COOKIE = "zhidao_v4_session"
CSRF_COOKIE = "zhidao_v4_csrf"


class BackendError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class V4Backend:
    def __init__(
        self,
        base_url: str,
        *,
        username: str,
        password: str,
        client: httpx.Client | None = None,
        verify: bool | str = True,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(20.0, connect=10.0), verify=verify
        )
        self._csrf_token: str | None = None
        self._session_token: str | None = None

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "V4Backend":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # --- сессия -----------------------------------------------------------

    def login(self) -> dict:
        response = self._client.post(
            f"{self._base_url}/api/v4/auth/login",
            json={"username": self._username, "password": self._password},
        )
        if response.status_code != 200:
            raise BackendError(
                f"bot service account could not sign in: {response.status_code} "
                f"{response.text[:200]}",
                status_code=response.status_code,
            )
        payload = response.json()
        self._csrf_token = payload.get("csrf_token")
        self._session_token = response.cookies.get(SESSION_COOKIE)
        if not self._session_token:
            raise BackendError("login succeeded but returned no session cookie")
        LOG.info("signed in to V4 API as %s", payload.get("account", {}).get("display_name"))
        return payload

    def _cookie_header(self) -> str | None:
        """Собирает заголовок Cookie вручную — и это не изобретение велосипеда.

        API помечает сессионную куку флагом `Secure`, а бот ходит в неё на
        `http://127.0.0.1:8770`. Банка кук httpx честно кладёт такую куку к
        себе, но по обычному HTTP её не отдаёт — по правилам она уходит
        только по TLS. В итоге логин отвечал 200, а следующий же запрос —
        401, и клиент бесконечно перелогинивался.

        Отправлять её явным заголовком здесь безопасно и правильно:
        соединение идёт на петлевой интерфейс и машину не покидает — тот
        самый случай, который и браузеры считают безопасным контекстом
        (`http://localhost`). Альтернативы хуже: снимать `Secure` — значит
        ослабить куку для всех настоящих пользователей, а ходить через
        публичный HTTPS — значит гонять трафик наружу и обратно и завязать
        бота на сертификат, который продлевается вручную.
        """
        parts = []
        if self._session_token:
            parts.append(f"{SESSION_COOKIE}={self._session_token}")
        if self._csrf_token:
            parts.append(f"{CSRF_COOKIE}={self._csrf_token}")
        return "; ".join(parts) or None

    def _call(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        _retried: bool = False,
    ) -> Any:
        headers: dict[str, str] = {}
        cookie_header = self._cookie_header()
        if cookie_header:
            headers["Cookie"] = cookie_header
        if method != "GET" and self._csrf_token:
            headers["X-CSRF-Token"] = self._csrf_token
        try:
            response = self._client.request(
                method,
                f"{self._base_url}{path}",
                params=params,
                json=json_body,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise BackendError(f"{method} {path}: {exc}") from exc

        # Сессия живёт 12 часов, бот — дольше. Один раз перелогиниваемся
        # молча; если и после этого 401/403, значит дело не в сроке.
        if response.status_code in (401, 403) and not _retried:
            LOG.info("session rejected (%s), signing in again", response.status_code)
            self.login()
            return self._call(
                method, path, params=params, json_body=json_body, _retried=True
            )

        if response.status_code >= 300:
            raise BackendError(
                f"{method} {path} -> {response.status_code}: {response.text[:300]}",
                status_code=response.status_code,
            )
        if not response.content:
            return None
        return response.json()

    # --- то, чем пользуется бот -------------------------------------------

    def health(self) -> dict:
        return self._call("GET", "/api/v4/health") or {}

    def whoami(self) -> dict:
        return self._call("GET", "/api/v4/auth/me") or {}

    def find_accounts(self, query: str = "", limit: int = 10) -> list[dict]:
        payload = self._call(
            "GET", "/api/v4/admin/accounts", params={"query": query, "limit": limit}
        ) or {}
        return list(payload.get("items") or [])

    def issue_link_code(self, account_id: int) -> dict:
        return self._call(
            "POST", f"/api/v4/admin/accounts/{account_id}/link-codes"
        ) or {}
