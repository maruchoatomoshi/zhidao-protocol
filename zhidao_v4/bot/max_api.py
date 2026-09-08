"""Тонкий клиент Bot API мессенджера MAX.

Ровно те методы, которыми пользуется бот, и ничего сверх. Библиотеку не
тянем: `httpx` уже в requirements-web.txt, а весь протокол — четыре
GET/POST с JSON.

Сверено со схемой официального клиента MAX
(github.com/max-messenger/max-bot-api-client-go, ветка v2, `schema.yaml` и
`const.go`, прочитано 2026-09-07):

  - база `https://platform-api2.max.ru`; старый `platform-api.max.ru`
    помечен в клиенте как Deprecated: not allowed;
  - токен идёт заголовком `Authorization: <токен>`, без `Bearer`;
    передача токена в query-параметре больше не поддерживается;
  - `GET /updates` — длинный опрос с `marker`, `limit`, `timeout`, `types`;
    ответ `{updates: [...], marker: N}`, и `marker` подтверждает всё, что
    было до него;
  - `POST /messages?user_id=…` с телом `NewMessageBody`;
  - `PATCH /me/commands` со списком `{name, description}`.

Формы объектов брать из схемы, а не из головы: у сообщения текст лежит в
`message.body.text`, отправитель — в `message.sender.user_id`, а адресат —
в `message.recipient.{user_id,chat_id,chat_type}`.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Sequence

import httpx


LOG = logging.getLogger("zhidao.bot.max")

DEFAULT_BASE_URL = "https://platform-api2.max.ru"

# Потолок длинного опроса в схеме — 90 секунд; 30 берём как компромисс
# между задержкой ответа и числом висящих запросов.
POLL_TIMEOUT_SECONDS = 30


class MaxApiError(RuntimeError):
    """Bot API MAX ответил ошибкой или не ответил вовсе."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class MaxBotApi:
    def __init__(
        self,
        token: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        client: httpx.Client | None = None,
    ) -> None:
        if not token:
            raise ValueError("MAX bot token is empty")
        self._token = token
        self._base_url = base_url.rstrip("/")
        # Клиентский таймаут заведомо больше серверного long poll'а, иначе
        # httpx оборвёт каждый пустой опрос как «сеть отвалилась».
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(POLL_TIMEOUT_SECONDS + 30.0, connect=10.0)
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "MaxBotApi":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
    ) -> Any:
        url = f"{self._base_url}{path}"
        headers = {"Authorization": self._token}
        try:
            response = self._client.request(
                method, url, params=params, json=json_body, headers=headers
            )
        except httpx.HTTPError as exc:
            raise MaxApiError(f"{method} {path}: {exc}") from exc
        if response.status_code >= 300:
            # Тело ошибки MAX короткое и осмысленное; обрезаем на случай
            # HTML-страницы от промежуточного прокси.
            raise MaxApiError(
                f"{method} {path} -> {response.status_code}: {response.text[:300]}",
                status_code=response.status_code,
            )
        if not response.content:
            return None
        return response.json()

    # --- боту о себе ------------------------------------------------------

    def get_me(self) -> dict:
        return self._request("GET", "/me") or {}

    def set_commands(self, commands: Sequence[tuple[str, str]]) -> dict:
        """Список команд в меню бота. Имена — без ведущей косой черты."""
        payload = {
            "commands": [
                {"name": name.lstrip("/"), "description": description[:128]}
                for name, description in commands
            ]
        }
        return self._request("PATCH", "/me/commands", json_body=payload) or {}

    # --- события ----------------------------------------------------------

    def get_updates(
        self,
        *,
        marker: int | None = None,
        limit: int = 100,
        timeout: int = POLL_TIMEOUT_SECONDS,
        types: Iterable[str] | None = None,
    ) -> tuple[list[dict], int | None]:
        params: dict[str, Any] = {"limit": limit, "timeout": timeout}
        # marker=None означает «всё, что ещё не подтверждено». Передать его
        # явным null нельзя — параметр надо просто опустить.
        if marker is not None:
            params["marker"] = marker
        if types:
            params["types"] = ",".join(types)
        payload = self._request("GET", "/updates", params=params) or {}
        updates = payload.get("updates") or []
        return list(updates), payload.get("marker")

    # --- сообщения --------------------------------------------------------

    def send_message(
        self,
        *,
        user_id: int | None = None,
        chat_id: int | None = None,
        text: str,
        buttons: Sequence[Sequence[dict]] | None = None,
        notify: bool = True,
    ) -> dict:
        if user_id is None and chat_id is None:
            raise ValueError("send_message needs user_id or chat_id")
        params: dict[str, Any] = {}
        if user_id is not None:
            params["user_id"] = user_id
        if chat_id is not None:
            params["chat_id"] = chat_id
        # Схема требует текст до 4000 символов; режем сами, чтобы длинная
        # выдача ростера не роняла ответ целиком.
        body: dict[str, Any] = {"text": text[:4000], "notify": notify}
        if buttons:
            body["attachments"] = [
                {"type": "inline_keyboard", "payload": {"buttons": list(buttons)}}
            ]
        return self._request("POST", "/messages", params=params, json_body=body) or {}


def link_button(text: str, url: str) -> dict:
    return {"type": "link", "text": text, "url": url}


def open_app_button(text: str, web_app: str) -> dict:
    """Кнопка запуска мини-приложения.

    `web_app` — публичное имя бота, к которому привязан мини-апп; в схеме
    это поле обязательное (OpenAppButton.web_app). Сам адрес мини-аппа
    задаётся в настройках бота в MAX, здесь его нет.
    """
    return {"type": "open_app", "text": text, "web_app": web_app}
