from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path

from .auth import ProvisioningError, provision_local_account
from .db import connect_database, immediate_transaction
from .migrations import apply_migrations
from .security import CredentialValidationError
from .seasons import HAINAN_DRAFT, create_draft_season


class BootstrapError(RuntimeError):
    pass


def bootstrap_system_admin(
    db_path: str | Path,
    *,
    username: str,
    password: str,
    display_name: str,
    create_hainan_draft: bool = True,
) -> dict:
    apply_migrations(db_path)
    conn = connect_database(db_path)
    try:
        with immediate_transaction(conn):
            existing = conn.execute(
                """
                SELECT 1
                FROM v4_role_assignments
                WHERE role_code = 'system_admin'
                  AND season_id IS NULL
                  AND revoked_at IS NULL
                LIMIT 1
                """
            ).fetchone()
            if existing:
                raise BootstrapError("An active system administrator already exists")

            try:
                account = provision_local_account(
                    conn,
                    username=username,
                    password=password,
                    display_name=display_name,
                    role_code="system_admin",
                )
            except (CredentialValidationError, ProvisioningError) as exc:
                raise BootstrapError(str(exc)) from exc

            role_cursor = conn.execute(
                """
                INSERT INTO v4_role_assignments(
                    account_id, role_code, granted_by_account_id, reason
                ) VALUES (?, 'architect', ?, 'bootstrap Architect console')
                """,
                (account["id"], account["id"]),
            )
            conn.execute(
                """
                INSERT INTO v4_audit_log(
                    actor_account_id, action, entity_type, entity_id, after_json
                ) VALUES (?, 'role.assigned', 'role_assignment', ?, ?)
                """,
                (
                    account["id"],
                    str(int(role_cursor.lastrowid)),
                    json.dumps(
                        {
                            "account_id": account["id"],
                            "role_code": "architect",
                            "season_id": None,
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                ),
            )
            account["role_codes"] = ["system_admin", "architect"]

            season = None
            if create_hainan_draft:
                season, _ = create_draft_season(
                    conn,
                    actor_account_id=account["id"],
                    idempotency_key="bootstrap:hainan-v4:0001",
                    **HAINAN_DRAFT,
                )
            return {"account": account, "season": season}
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create the first local V4 system administrator"
    )
    parser.add_argument("--db", required=True, help="SQLite database path")
    parser.add_argument("--username", required=True, help="Lowercase local login")
    parser.add_argument("--display-name", required=True, help="Administrator display name")
    parser.add_argument(
        "--skip-hainan-draft",
        action="store_true",
        help="Do not create the initial Hainan draft season",
    )
    args = parser.parse_args()

    password = getpass.getpass("New password (12+ characters): ")
    confirmation = getpass.getpass("Repeat password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match")

    result = bootstrap_system_admin(
        args.db,
        username=args.username,
        password=password,
        display_name=args.display_name,
        create_hainan_draft=not args.skip_hainan_draft,
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
