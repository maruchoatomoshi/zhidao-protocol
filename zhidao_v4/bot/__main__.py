"""Точка входа бота: `python -m zhidao_v4.bot`.

Режимы
------

  --check          проверить связь и выйти. Спрашивает MAX, кто мы, и
                   логинится в API V4 служебной учёткой. Первое, что стоит
                   запускать на сервере: если что-то не так с токеном,
                   паролем или адресом, это видно сразу и без ожидания
                   первого сообщения от человека.
  --set-commands   записать меню команд в профиль бота в MAX и выйти.
  (без ключей)     длинный опрос: работать.
  --dump-updates   как обычный режим, но печатать сырой JSON каждого
                   события и ничего не отвечать. Нужен, если MAX изменит
                   форму события: сверять с реальностью, а не гадать.

Окружение
---------

  ZHIDAO_V4_MAX_BOT_TOKEN     токен бота MAX (обязательно)
  ZHIDAO_V4_API_URL           адрес API V4, по умолчанию http://127.0.0.1:8443
  ZHIDAO_V4_BOT_USERNAME      логин служебной учётки бота (обязательно)
  ZHIDAO_V4_BOT_PASSWORD      её пароль (обязательно)
  ZHIDAO_V4_BOT_OPERATORS     идентификаторы MAX вожатых через запятую
  ZHIDAO_V4_BOT_WEBAPP        публичное имя бота для кнопки мини-аппа
  ZHIDAO_V4_APP_URL           адрес приложения, запасной вариант ссылкой
  ZHIDAO_V4_MAX_API_URL       база Bot API MAX, если она когда-нибудь сменится
  ZHIDAO_V4_MAX_CA_BUNDLE     PEM с корнем «Russian Trusted Root CA»: им
                              подписан сертификат MAX, а системным корням он
                              неизвестен (см. V4_BOT.md)

Токен и пароль читаются только из окружения. В репозитории их нет и быть
не должно.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time

from .backend import BackendError, V4Backend
from .commands import MENU_COMMANDS, UPDATE_TYPES, Bot, parse_update
from .max_api import DEFAULT_BASE_URL, MaxApiError, MaxBotApi


LOG = logging.getLogger("zhidao.bot")


def _operator_ids(raw: str) -> frozenset[int]:
    ids: set[int] = set()
    for chunk in raw.replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            ids.add(int(chunk))
        except ValueError:
            LOG.warning("ZHIDAO_V4_BOT_OPERATORS: %r is not a MAX user id, skipped", chunk)
    return frozenset(ids)


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"{name} is not set. See the module docstring for the full list.")
    return value


def _max_ca_bundle() -> bool | str:
    """Набор корней для разговора с MAX. См. V4_BOT.md, раздел про сертификат."""
    path = os.getenv("ZHIDAO_V4_MAX_CA_BUNDLE", "").strip()
    if not path:
        return True
    if not os.path.isfile(path):
        raise SystemExit(
            f"ZHIDAO_V4_MAX_CA_BUNDLE points at {path}, which does not exist"
        )
    return path


def build(argv_check_only: bool = False) -> tuple[MaxBotApi, V4Backend, Bot]:
    api = MaxBotApi(
        _require("ZHIDAO_V4_MAX_BOT_TOKEN"),
        base_url=os.getenv("ZHIDAO_V4_MAX_API_URL", DEFAULT_BASE_URL),
        verify=_max_ca_bundle(),
    )
    backend = V4Backend(
        os.getenv("ZHIDAO_V4_API_URL", "http://127.0.0.1:8443"),
        username=_require("ZHIDAO_V4_BOT_USERNAME"),
        password=_require("ZHIDAO_V4_BOT_PASSWORD"),
    )
    operators = _operator_ids(os.getenv("ZHIDAO_V4_BOT_OPERATORS", ""))
    if not operators and not argv_check_only:
        # Не отказ: бот полезен и без вожатых — участники всё равно получат
        # /start и кнопку приложения. Но это почти наверняка забытая
        # переменная, и молчать о ней нельзя.
        LOG.warning(
            "ZHIDAO_V4_BOT_OPERATORS is empty: nobody will be able to issue pairing codes"
        )
    bot = Bot(
        api,
        backend,
        operator_ids=operators,
        web_app_name=os.getenv("ZHIDAO_V4_BOT_WEBAPP", "").strip(),
        app_url=os.getenv("ZHIDAO_V4_APP_URL", "").strip(),
    )
    return api, backend, bot


def run_check(api: MaxBotApi, backend: V4Backend) -> int:
    problems = 0

    try:
        me = api.get_me()
        print(f"MAX: бот «{me.get('name')}», username @{me.get('username')}, id {me.get('user_id')}")
    except MaxApiError as exc:
        print(f"MAX: НЕ ОТВЕЧАЕТ — {exc}")
        if "CERTIFICATE_VERIFY_FAILED" in str(exc):
            # Самая вероятная и самая непрозрачная ошибка при первом запуске:
            # без подсказки она читается как «MAX недоступен».
            print(
                "  Похоже, не хватает корневого сертификата. Сертификат MAX\n"
                "  подписан «Russian Trusted Sub CA» (Минцифры), системным\n"
                "  корням он неизвестен. См. V4_BOT.md, раздел про сертификат:\n"
                "  нужен ZHIDAO_V4_MAX_CA_BUNDLE."
            )
        problems += 1

    try:
        health = backend.health()
        print(f"API V4: {health.get('status')}, схема {health.get('schema_version')}")
    except BackendError as exc:
        print(f"API V4: НЕ ОТВЕЧАЕТ — {exc}")
        problems += 1
        return 1 if problems else 0

    try:
        backend.login()
        who = backend.whoami()
        account = who.get("account", {})
        roles = [role.get("code") for role in who.get("roles", [])]
        print(f"Учётка бота: {account.get('display_name')}, роли: {', '.join(roles) or 'нет'}")
        if not ({"operator", "architect", "system_admin"} & set(roles)):
            print("  ВНИМАНИЕ: у учётки нет роли оператора — коды сопряжения выдать не выйдет")
            problems += 1
    except BackendError as exc:
        print(f"Учётка бота: ВОЙТИ НЕ УДАЛОСЬ — {exc}")
        problems += 1

    return 1 if problems else 0


def run_loop(api: MaxBotApi, backend: V4Backend, bot: Bot, *, dump: bool = False) -> int:
    backend.login()
    marker: int | None = None
    # Пауза после сбоя растёт, чтобы при недоступном MAX не долбить его
    # раз в секунду и не заполнять журнал одинаковыми строками.
    backoff = 1.0
    LOG.info("polling for updates")
    while True:
        try:
            updates, next_marker = api.get_updates(marker=marker, types=UPDATE_TYPES)
            backoff = 1.0
        except MaxApiError as exc:
            LOG.warning("getUpdates failed: %s (retry in %.0fs)", exc, backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
            continue

        for update in updates:
            if dump:
                print(json.dumps(update, ensure_ascii=False, indent=2))
                continue
            incoming = parse_update(update)
            if incoming is None:
                continue
            try:
                bot.handle(incoming)
            except Exception:
                # Одно неудачное сообщение не должно останавливать бота на
                # весь остаток поездки. Пишем трассировку и живём дальше.
                LOG.exception("handler failed for user %s", incoming.user_id)

        # Сдвигаем marker только после обработки: иначе падение на середине
        # пачки потеряет остаток событий безвозвратно.
        if next_marker is not None:
            marker = next_marker


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m zhidao_v4.bot")
    parser.add_argument("--check", action="store_true", help="проверить связь и выйти")
    parser.add_argument("--set-commands", action="store_true", help="записать меню команд и выйти")
    parser.add_argument("--dump-updates", action="store_true", help="печатать сырые события")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    api, backend, bot = build(argv_check_only=args.check)
    try:
        if args.check:
            return run_check(api, backend)
        if args.set_commands:
            api.set_commands(MENU_COMMANDS)
            print(f"Меню обновлено: {', '.join('/' + name for name, _ in MENU_COMMANDS)}")
            return 0
        return run_loop(api, backend, bot, dump=args.dump_updates)
    except KeyboardInterrupt:
        LOG.info("stopped")
        return 0
    finally:
        api.close()
        backend.close()


if __name__ == "__main__":
    sys.exit(main())
