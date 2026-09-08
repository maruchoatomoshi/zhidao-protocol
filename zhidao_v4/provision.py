"""Заведение локальной учётной записи: `python -m zhidao_v4.provision`.

`zhidao_v4.bootstrap` создаёт только первого системного администратора и
только один раз. Всё остальное — вожатые, участники, служебная учётка бота —
до сих пор заводилось из интерпретатора руками. Для бота это перестало быть
терпимым: без учётки с ролью оператора он не запускается вовсе.

Пароль не берётся из аргументов командной строки: он остался бы в истории
оболочки и в `ps`. Либо спрашиваем интерактивно, либо (`--random-password`)
генерируем и печатаем один раз — второй вариант и нужен служебной учётке,
чей пароль всё равно поедет прямиком в `/etc/zhidao-v4/v4.env`.

Инструмент пишет в базу напрямую. Это единственный дозволенный случай
второго писателя: одна короткая транзакция, запускается вручную, ничего не
ждёт по сети внутри неё. Правило из CLAUDE.md запрещает долгоживущего
второго писателя — такого, каким был бот сезона 1.
"""

from __future__ import annotations

import argparse
import getpass
import json
import secrets
import string

from .auth import ProvisioningError, provision_local_account
from .db import connect_database, immediate_transaction
from .security import normalize_local_username


ROLE_CODES = ("system_admin", "architect", "operator", "participant")


def generate_password(length: int = 32) -> str:
    # Без похожих друг на друга знаков: этот пароль будут переносить руками
    # в файл окружения на сервере, и «l» вместо «1» стоит часа поисков.
    alphabet = "".join(
        ch for ch in string.ascii_letters + string.digits if ch not in "Il1O0"
    )
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _list_accounts(db_path: str) -> int:
    """Кто уже заведён. Нужно ровно затем, чтобы не гадать после «логин занят»."""
    conn = connect_database(db_path)
    try:
        rows = conn.execute(
            """
            SELECT a.id, a.display_name, a.status,
                   e.provider_subject AS login,
                   (SELECT GROUP_CONCAT(r.role_code, ', ')
                      FROM v4_role_assignments r
                     WHERE r.account_id = a.id) AS roles
              FROM v4_accounts a
              LEFT JOIN v4_external_identities e
                     ON e.account_id = a.id AND e.provider_code = 'local'
             ORDER BY a.id
            """
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        print("Локальных учётных записей пока нет.")
        return 0
    for row in rows:
        status = "" if row["status"] == "active" else f" [{row['status']}]"
        print(
            f"#{row['id']} {row['login'] or '(без локального логина)'} — "
            f"{row['display_name']}{status} — роли: {row['roles'] or 'нет'}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m zhidao_v4.provision",
        description="Create a local V4 account with a role",
    )
    parser.add_argument("--db", required=True, help="SQLite database path")
    # Не required: с --list они бессмысленны, а argparse иначе не даст даже
    # посмотреть список. Проверяются ниже, когда действительно нужны.
    parser.add_argument("--username", help="Lowercase local login")
    parser.add_argument("--display-name", help="Name shown in the app")
    parser.add_argument("--role", choices=ROLE_CODES)
    parser.add_argument(
        "--actor-account-id",
        type=int,
        default=None,
        help="Who is creating this account; goes into the audit log",
    )
    parser.add_argument(
        "--random-password",
        action="store_true",
        help="Generate the password and print it once instead of asking",
    )
    parser.add_argument(
        "--must-change-password",
        action="store_true",
        help="Force a password change on first sign-in",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Show existing local accounts and exit",
    )
    args = parser.parse_args(argv)

    if args.list:
        return _list_accounts(args.db)

    missing = [
        name
        for name, value in (
            ("--username", args.username),
            ("--display-name", args.display_name),
            ("--role", args.role),
        )
        if not value
    ]
    if missing:
        raise SystemExit(f"Required for creating an account: {', '.join(missing)}")

    if args.random_password:
        password = generate_password()
    else:
        password = getpass.getpass("New password (12+ characters): ")
        if password != getpass.getpass("Repeat password: "):
            raise SystemExit("Passwords do not match")

    conn = connect_database(args.db)
    try:
        with immediate_transaction(conn):
            account = provision_local_account(
                conn,
                username=args.username,
                password=password,
                display_name=args.display_name,
                role_code=args.role,
                actor_account_id=args.actor_account_id,
                must_change_password=args.must_change_password,
            )
    except ProvisioningError as exc:
        # Самая частая ошибка здесь — повторный запуск с тем же логином, и
        # сырое «UNIQUE constraint failed: v4_external_identities...» об этом
        # не говорит ничего. Учётка при этом уже существует и цела: подсказать
        # надо, как её найти, а не как создать заново.
        if "v4_external_identities" in str(exc):
            raise SystemExit(
                f"Логин {normalize_local_username(args.username)!r} уже занят — "
                "учётная запись с ним существует.\n"
                "Посмотреть её: python -m zhidao_v4.provision --db … --list, "
                "сменить пароль: python -m zhidao_v4.passwd."
            ) from None
        raise SystemExit(str(exc)) from None
    finally:
        conn.close()

    print(json.dumps(account, ensure_ascii=False))
    if args.random_password:
        # Единственный раз, когда пароль виден. В базе с этого момента
        # только его scrypt-хэш.
        print(f"password: {password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
