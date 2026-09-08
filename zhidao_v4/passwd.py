"""Смена пароля локальной учётной записи: `python -m zhidao_v4.passwd`.

До сих пор в репозитории не было ни одной команды для этого. Пароль
задавался один раз при заведении учётки и после этого не менялся ничем:
забытый пароль Архитектора означал бы либо правку базы руками, либо
заведение второй учётки рядом с первой. Ни то, ни другое не годится.

Команда меняет пароль на месте — учётная запись, её `public_id`, роли,
привязанные внешние личности и весь журнал остаются теми же. Заодно
снимается блокировка после неудачных попыток входа: человек, который
пришёл менять пароль через администратора, уже доказал, кто он.

Пишет в базу напрямую, как и `zhidao_v4.provision`. Это дозволенный случай
второго писателя: одна короткая транзакция, запуск вручную, никакого
ожидания сети внутри неё. Правило из CLAUDE.md запрещает долгоживущего
второго писателя, каким был бот сезона 1.
"""

from __future__ import annotations

import argparse
import getpass
import json

from .auth import utc_text
from .db import connect_database, immediate_transaction
from .provision import generate_password
from .security import hash_password, normalize_local_username


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m zhidao_v4.passwd",
        description="Set a new password for an existing local V4 account",
    )
    parser.add_argument("--db", required=True, help="SQLite database path")
    parser.add_argument("--username", required=True, help="Local login of the account")
    parser.add_argument(
        "--actor-account-id",
        type=int,
        default=None,
        help="Who is changing the password; goes into the audit log",
    )
    parser.add_argument(
        "--random-password",
        action="store_true",
        help="Generate the password and print it once instead of asking",
    )
    args = parser.parse_args(argv)

    username = normalize_local_username(args.username)

    if args.random_password:
        password = generate_password()
    else:
        password = getpass.getpass("New password (12+ characters): ")
        if password != getpass.getpass("Repeat password: "):
            raise SystemExit("Passwords do not match")

    conn = connect_database(args.db)
    try:
        with immediate_transaction(conn):
            row = conn.execute(
                """
                SELECT e.id AS identity_id, a.id AS account_id, a.public_id,
                       a.display_name, a.status
                  FROM v4_external_identities e
                  JOIN v4_accounts a ON a.id = e.account_id
                 WHERE e.provider_code = 'local' AND e.provider_subject = ?
                """,
                (username,),
            ).fetchone()
            if row is None:
                raise SystemExit(f"No local account with login {username!r}")

            now = utc_text()
            conn.execute(
                """
                UPDATE v4_local_credentials
                   SET password_hash = ?, password_changed_at = ?,
                       failed_attempts = 0, locked_until = NULL
                 WHERE identity_id = ?
                """,
                (hash_password(password), now, int(row["identity_id"])),
            )
            # Старые сессии после смены пароля недействительны. Иначе тот,
            # ради кого пароль меняли, остался бы в системе с прежней
            # сессией — а это ровно тот случай, когда пароль и меняют.
            revoked = conn.execute(
                "DELETE FROM v4_sessions WHERE account_id = ?", (int(row["account_id"]),)
            ).rowcount
            conn.execute(
                """
                INSERT INTO v4_audit_log(
                    actor_account_id, action, entity_type, entity_id, metadata_json
                ) VALUES (?, 'account.password_changed', 'account', ?, ?)
                """,
                (
                    args.actor_account_id or int(row["account_id"]),
                    str(row["public_id"]),
                    json.dumps(
                        {"login": username, "revoked_sessions": revoked},
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                ),
            )
    finally:
        conn.close()

    print(
        json.dumps(
            {
                "account_id": int(row["account_id"]),
                "public_id": str(row["public_id"]),
                "display_name": str(row["display_name"]),
                "status": str(row["status"]),
                "login": username,
                "revoked_sessions": revoked,
            },
            ensure_ascii=False,
        )
    )
    if args.random_password:
        # Единственный раз, когда пароль виден.
        print(f"password: {password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
