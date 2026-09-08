"""Выдача и отзыв ролей: `python -m zhidao_v4.roles`.

Роль до сих пор можно было назначить только в момент заведения учётной
записи. Повысить вожатого до администратора или, наоборот, снять права
после поездки было нечем — только правкой базы руками.

Роль отзывается пометкой `revoked_at`, а не удалением строки: кто и когда
имел права — это ровно то, что должно оставаться в истории, а частичный
уникальный индекс из миграции 0001 всё равно считает действующей только
строку без `revoked_at`. Повторная выдача уже действующей роли поэтому не
создаёт дубликата, а честно сообщает, что она уже есть.

Как и остальные команды администратора, пишет в базу напрямую: одна
короткая транзакция, запуск вручную, никакого ожидания сети внутри неё.
"""

from __future__ import annotations

import argparse
import json

from .auth import utc_text
from .db import connect_database, immediate_transaction
from .security import normalize_local_username


ROLE_CODES = ("system_admin", "architect", "operator", "participant")


def _resolve_account(conn, username: str) -> dict:
    row = conn.execute(
        """
        SELECT a.id, a.public_id, a.display_name, a.status
          FROM v4_external_identities e
          JOIN v4_accounts a ON a.id = e.account_id
         WHERE e.provider_code = 'local' AND e.provider_subject = ?
        """,
        (username,),
    ).fetchone()
    if row is None:
        raise SystemExit(f"No local account with login {username!r}")
    return row


def _active_roles(conn, account_id: int) -> list[str]:
    return [
        str(row["role_code"])
        for row in conn.execute(
            """
            SELECT role_code FROM v4_role_assignments
             WHERE account_id = ? AND season_id IS NULL AND revoked_at IS NULL
             ORDER BY role_code
            """,
            (account_id,),
        )
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m zhidao_v4.roles",
        description="Grant or revoke a global role on a local V4 account",
    )
    parser.add_argument("--db", required=True, help="SQLite database path")
    parser.add_argument("--username", required=True, help="Local login of the account")
    parser.add_argument("--grant", choices=ROLE_CODES, help="Role to grant")
    parser.add_argument("--revoke", choices=ROLE_CODES, help="Role to revoke")
    parser.add_argument(
        "--actor-account-id",
        type=int,
        default=None,
        help="Who is making the change; goes into the audit log",
    )
    parser.add_argument(
        "--reason", default=None, help="Free-text note stored with the assignment"
    )
    args = parser.parse_args(argv)

    if bool(args.grant) == bool(args.revoke):
        raise SystemExit("Pass exactly one of --grant or --revoke")

    username = normalize_local_username(args.username)

    conn = connect_database(args.db)
    try:
        with immediate_transaction(conn):
            account = _resolve_account(conn, username)
            account_id = int(account["id"])
            actor = args.actor_account_id or account_id
            now = utc_text()
            before = _active_roles(conn, account_id)

            if args.grant:
                if args.grant in before:
                    raise SystemExit(
                        f"{username!r} already has the role {args.grant!r}"
                    )
                conn.execute(
                    """
                    INSERT INTO v4_role_assignments(
                        account_id, role_code, season_id, granted_by_account_id,
                        granted_at, reason
                    ) VALUES (?, ?, NULL, ?, ?, ?)
                    """,
                    (account_id, args.grant, actor, now, args.reason or "granted via CLI"),
                )
                action, role = "role.assigned", args.grant
            else:
                changed = conn.execute(
                    """
                    UPDATE v4_role_assignments SET revoked_at = ?
                     WHERE account_id = ? AND role_code = ?
                       AND season_id IS NULL AND revoked_at IS NULL
                    """,
                    (now, account_id, args.revoke),
                ).rowcount
                if not changed:
                    raise SystemExit(
                        f"{username!r} does not currently have the role {args.revoke!r}"
                    )
                action, role = "role.revoked", args.revoke

            conn.execute(
                """
                INSERT INTO v4_audit_log(
                    actor_account_id, action, entity_type, entity_id, metadata_json
                ) VALUES (?, ?, 'account', ?, ?)
                """,
                (
                    actor,
                    action,
                    str(account["public_id"]),
                    json.dumps(
                        {"login": username, "role_code": role, "reason": args.reason},
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                ),
            )
            after = _active_roles(conn, account_id)
    finally:
        conn.close()

    print(
        json.dumps(
            {
                "account_id": account_id,
                "public_id": str(account["public_id"]),
                "display_name": str(account["display_name"]),
                "login": username,
                "roles_before": before,
                "roles_after": after,
            },
            ensure_ascii=False,
        )
    )
    # Роли читаются при каждом запросе, а не запекаются в сессию, — значит
    # изменение действует немедленно и на уже открытые сессии тоже.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
