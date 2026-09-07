from __future__ import annotations

import json
import hmac
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .db import connect_database, immediate_transaction
from .security import (
    DUMMY_PASSWORD_HASH,
    CredentialValidationError,
    hash_password,
    new_token,
    normalize_local_username,
    token_hash,
    verify_password,
)


LOGIN_FAILURE_LIMIT = 5
LOGIN_LOCK_MINUTES = 15


class AuthenticationError(RuntimeError):
    pass


class ProvisioningError(RuntimeError):
    pass


@dataclass(frozen=True)
class RoleGrant:
    code: str
    season_id: int | None


@dataclass(frozen=True)
class Principal:
    account_id: int
    public_id: str
    display_name: str
    token_hash: str
    csrf_token_hash: str
    expires_at: str
    roles: tuple[RoleGrant, ...]

    def has_global_role(self, role_code: str) -> bool:
        return any(
            grant.code == role_code and grant.season_id is None for grant in self.roles
        )

    def has_role(self, role_code: str, season_id: int | None = None) -> bool:
        return any(
            grant.code == role_code
            and (grant.season_id is None or grant.season_id == season_id)
            for grant in self.roles
        )


@dataclass(frozen=True)
class LoginResult:
    principal: Principal
    session_token: str
    csrf_token: str
    max_age_seconds: int


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_text(value: datetime | None = None) -> str:
    actual = value or utc_now()
    return actual.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _load_roles(conn: sqlite3.Connection, account_id: int) -> tuple[RoleGrant, ...]:
    return tuple(
        RoleGrant(code=str(row[0]), season_id=row[1])
        for row in conn.execute(
            """
            SELECT role_code, season_id
            FROM v4_role_assignments
            WHERE account_id = ? AND revoked_at IS NULL
            ORDER BY role_code, season_id
            """,
            (account_id,),
        )
    )


def provision_local_account(
    conn: sqlite3.Connection,
    *,
    username: str,
    password: str,
    display_name: str,
    role_code: str,
    actor_account_id: int | None = None,
    season_id: int | None = None,
    must_change_password: bool = False,
) -> dict:
    normalized_username = normalize_local_username(username)
    clean_display_name = str(display_name or "").strip()
    if not clean_display_name:
        raise ProvisioningError("Display name is required")
    encoded_password = hash_password(password)
    now = utc_text()
    public_id = f"acct_{uuid.uuid4().hex}"

    try:
        cursor = conn.execute(
            """
            INSERT INTO v4_accounts(public_id, display_name, status, created_at, updated_at)
            VALUES (?, ?, 'active', ?, ?)
            """,
            (public_id, clean_display_name, now, now),
        )
        account_id = int(cursor.lastrowid)
        identity_cursor = conn.execute(
            """
            INSERT INTO v4_external_identities(
                account_id, provider_code, provider_subject, verified_at, created_at
            ) VALUES (?, 'local', ?, ?, ?)
            """,
            (account_id, normalized_username, now, now),
        )
        identity_id = int(identity_cursor.lastrowid)
        conn.execute(
            """
            INSERT INTO v4_local_credentials(
                identity_id, password_hash, must_change_password, password_changed_at
            ) VALUES (?, ?, ?, ?)
            """,
            (identity_id, encoded_password, int(must_change_password), now),
        )
        role_cursor = conn.execute(
            """
            INSERT INTO v4_role_assignments(
                account_id, role_code, season_id, granted_by_account_id, granted_at,
                reason
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                account_id,
                role_code,
                season_id,
                actor_account_id or account_id,
                now,
                "initial local account role",
            ),
        )
        conn.execute(
            """
            INSERT INTO v4_audit_log(
                actor_account_id, season_id, action, entity_type, entity_id,
                after_json, metadata_json
            ) VALUES (?, ?, 'account.created', 'account', ?, ?, ?)
            """,
            (
                actor_account_id or account_id,
                season_id,
                public_id,
                json.dumps(
                    {
                        "display_name": clean_display_name,
                        "status": "active",
                        "identity_provider": "local",
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                json.dumps(
                    {"role_code": role_code},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            ),
        )
        conn.execute(
            """
            INSERT INTO v4_audit_log(
                actor_account_id, season_id, action, entity_type, entity_id,
                after_json
            ) VALUES (?, ?, 'role.assigned', 'role_assignment', ?, ?)
            """,
            (
                actor_account_id or account_id,
                season_id,
                str(int(role_cursor.lastrowid)),
                json.dumps(
                    {
                        "account_id": account_id,
                        "role_code": role_code,
                        "season_id": season_id,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            ),
        )
    except sqlite3.IntegrityError as exc:
        raise ProvisioningError(f"Could not create local account: {exc}") from exc

    return {
        "id": account_id,
        "public_id": public_id,
        "display_name": clean_display_name,
        "username": normalized_username,
        "role_code": role_code,
        "season_id": season_id,
    }


def authenticate_local(
    db_path: str | Path,
    *,
    username: str,
    password: str,
    session_hours: int = 12,
) -> LoginResult:
    try:
        normalized_username = normalize_local_username(username)
    except CredentialValidationError:
        verify_password(str(password or ""), DUMMY_PASSWORD_HASH)
        raise AuthenticationError("Invalid username or password") from None

    conn = connect_database(db_path)
    failure = False
    result: LoginResult | None = None
    try:
        with immediate_transaction(conn):
            row = conn.execute(
                """
                SELECT
                    a.id AS account_id,
                    a.public_id,
                    a.display_name,
                    a.status AS account_status,
                    e.id AS identity_id,
                    p.is_enabled AS provider_enabled,
                    c.password_hash,
                    c.failed_attempts,
                    c.locked_until
                FROM v4_external_identities e
                JOIN v4_identity_providers p ON p.code = e.provider_code
                JOIN v4_accounts a ON a.id = e.account_id
                JOIN v4_local_credentials c ON c.identity_id = e.id
                WHERE e.provider_code = 'local' AND e.provider_subject = ?
                """,
                (normalized_username,),
            ).fetchone()

            if row is None:
                verify_password(str(password or ""), DUMMY_PASSWORD_HASH)
                failure = True
            else:
                password_matches = verify_password(
                    str(password or ""), str(row["password_hash"])
                )
                now = utc_now()
                now_value = utc_text(now)
                locked = bool(
                    row["locked_until"] and str(row["locked_until"]) > now_value
                )
                usable = (
                    str(row["account_status"]) == "active"
                    and bool(row["provider_enabled"])
                    and not locked
                )

                if not password_matches or not usable:
                    if not locked and str(row["account_status"]) == "active":
                        failed_attempts = int(row["failed_attempts"]) + 1
                        locked_until = None
                        if failed_attempts >= LOGIN_FAILURE_LIMIT:
                            locked_until = utc_text(
                                now + timedelta(minutes=LOGIN_LOCK_MINUTES)
                            )
                        conn.execute(
                            """
                            UPDATE v4_local_credentials
                            SET failed_attempts = ?, locked_until = ?
                            WHERE identity_id = ?
                            """,
                            (failed_attempts, locked_until, int(row["identity_id"])),
                        )
                        conn.execute(
                            """
                            INSERT INTO v4_audit_log(
                                action, entity_type, entity_id, metadata_json
                            ) VALUES ('auth.login_failed', 'account', ?, ?)
                            """,
                            (
                                str(row["public_id"]),
                                json.dumps(
                                    {
                                        "failed_attempts": failed_attempts,
                                        "locked": locked_until is not None,
                                    },
                                    separators=(",", ":"),
                                ),
                            ),
                        )
                    failure = True
                else:
                    account_id = int(row["account_id"])
                    session_token = new_token()
                    csrf_token = new_token()
                    expires = now + timedelta(hours=session_hours)
                    expires_value = utc_text(expires)
                    session_token_hash = token_hash(session_token)
                    csrf_hash = token_hash(csrf_token)
                    conn.execute(
                        """
                        UPDATE v4_local_credentials
                        SET failed_attempts = 0, locked_until = NULL
                        WHERE identity_id = ?
                        """,
                        (int(row["identity_id"]),),
                    )
                    conn.execute(
                        "UPDATE v4_external_identities SET last_seen_at = ? WHERE id = ?",
                        (now_value, int(row["identity_id"])),
                    )
                    conn.execute(
                        """
                        INSERT INTO v4_sessions(
                            token_hash, csrf_token_hash, account_id, created_at,
                            expires_at, last_seen_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            session_token_hash,
                            csrf_hash,
                            account_id,
                            now_value,
                            expires_value,
                            now_value,
                        ),
                    )
                    conn.execute(
                        """
                        INSERT INTO v4_audit_log(
                            actor_account_id, action, entity_type, entity_id
                        ) VALUES (?, 'auth.login_succeeded', 'account', ?)
                        """,
                        (account_id, str(row["public_id"])),
                    )
                    roles = _load_roles(conn, account_id)
                    principal = Principal(
                        account_id=account_id,
                        public_id=str(row["public_id"]),
                        display_name=str(row["display_name"]),
                        token_hash=session_token_hash,
                        csrf_token_hash=csrf_hash,
                        expires_at=expires_value,
                        roles=roles,
                    )
                    result = LoginResult(
                        principal=principal,
                        session_token=session_token,
                        csrf_token=csrf_token,
                        max_age_seconds=session_hours * 60 * 60,
                    )
    finally:
        conn.close()

    if failure or result is None:
        raise AuthenticationError("Invalid username or password")
    return result


class LinkRequiredError(AuthenticationError):
    """The MAX user is verified but has no linked account yet.

    Distinct from AuthenticationError so the API layer can tell "wrong
    credentials" (401, stop) apart from "right person, needs to type the
    code an operator gave them" (a different screen, not a failure)."""


def _issue_session(
    conn: sqlite3.Connection, *, account_id: int, session_hours: int
) -> LoginResult:
    now = utc_now()
    now_value = utc_text(now)
    session_token = new_token()
    csrf_token = new_token()
    expires_value = utc_text(now + timedelta(hours=session_hours))
    session_token_hash = token_hash(session_token)
    csrf_hash = token_hash(csrf_token)
    conn.execute(
        """
        INSERT INTO v4_sessions(
            token_hash, csrf_token_hash, account_id, created_at,
            expires_at, last_seen_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (session_token_hash, csrf_hash, account_id, now_value, expires_value, now_value),
    )
    account_row = conn.execute(
        "SELECT public_id, display_name FROM v4_accounts WHERE id = ?", (account_id,)
    ).fetchone()
    roles = _load_roles(conn, account_id)
    principal = Principal(
        account_id=account_id,
        public_id=str(account_row["public_id"]),
        display_name=str(account_row["display_name"]),
        token_hash=session_token_hash,
        csrf_token_hash=csrf_hash,
        expires_at=expires_value,
        roles=roles,
    )
    return LoginResult(
        principal=principal,
        session_token=session_token,
        csrf_token=csrf_token,
        max_age_seconds=session_hours * 60 * 60,
    )


def create_link_code(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    provider_code: str,
    actor_account_id: int,
    ttl_minutes: int = 30,
) -> str:
    """Issues a fresh pairing code for an operator to hand a participant.

    Any earlier code for the same account and provider that is neither
    consumed nor already revoked is revoked first. This is not merely tidy:
    the partial unique index from migration 0005 permits exactly one such row,
    so without the revoke a re-issue would fail outright. Pushing `expires_at`
    into the past is not enough — an expired code is still an unconsumed row
    and still occupies the slot (that was the bug 0005 fixes).
    """
    now = utc_now()
    now_value = utc_text(now)
    conn.execute(
        """
        UPDATE v4_link_codes SET revoked_at = ?, revoked_by_account_id = ?
        WHERE account_id = ? AND provider_code = ?
          AND consumed_at IS NULL AND revoked_at IS NULL
        """,
        (now_value, actor_account_id, account_id, provider_code),
    )
    # secrets.token_hex would include 0/o/1/l-style ambiguity in spirit if we
    # ever switch to letters; digits sidestep that entirely and are what a
    # counsellor can read aloud without spelling anything out.
    code = f"{secrets.randbelow(10**8):08d}"
    conn.execute(
        """
        INSERT INTO v4_link_codes(
            account_id, provider_code, code_hash, created_at, expires_at,
            created_by_account_id
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            account_id,
            provider_code,
            token_hash(code),
            now_value,
            utc_text(now + timedelta(minutes=ttl_minutes)),
            actor_account_id,
        ),
    )
    # entity_id — публичный идентификатор аккаунта, как во всех остальных
    # записях журнала ('identity.linked', 'auth.login_succeeded'). Внутренний
    # rowid здесь сделал бы журнал нечитаемым в одном запросе.
    public_id_row = conn.execute(
        "SELECT public_id FROM v4_accounts WHERE id = ?", (account_id,)
    ).fetchone()
    conn.execute(
        """
        INSERT INTO v4_audit_log(
            actor_account_id, action, entity_type, entity_id, metadata_json
        ) VALUES (?, 'link_code.issued', 'account', ?, ?)
        """,
        (
            actor_account_id,
            str(public_id_row["public_id"]) if public_id_row else str(account_id),
            json.dumps(
                {"provider_code": provider_code, "ttl_minutes": ttl_minutes},
                separators=(",", ":"),
            ),
        ),
    )
    return code


def authenticate_max(
    db_path: str | Path,
    *,
    max_user_id: str,
    max_username: str | None,
    link_code: str | None = None,
    session_hours: int = 12,
) -> LoginResult:
    """Logs in a MAX Mini App user already verified by max_auth.verify_launch_params.

    Signature verification happens one layer up (it needs no database and is
    unit-tested on its own); this function only ever sees a `max_user_id`
    the caller has already proven MAX actually issued.

    Two paths:
      - an existing `max` identity for this user_id -> ordinary login;
      - no identity yet -> `link_code` must match a code that is unexpired,
        unconsumed and not revoked (an operator revokes the old one whenever
        they issue a replacement), which permanently binds this MAX id to
        that code's account.
        Without a valid code this raises LinkRequiredError, not
        AuthenticationError: the person is who they say they are, they just
        have not proven which roster account is theirs yet.
    """
    conn = connect_database(db_path)
    try:
        with immediate_transaction(conn):
            row = conn.execute(
                """
                SELECT e.id AS identity_id, e.account_id, p.is_enabled AS provider_enabled,
                       a.status AS account_status, a.public_id, a.display_name
                FROM v4_external_identities e
                JOIN v4_identity_providers p ON p.code = e.provider_code
                JOIN v4_accounts a ON a.id = e.account_id
                WHERE e.provider_code = 'max' AND e.provider_subject = ?
                """,
                (max_user_id,),
            ).fetchone()

            if row is not None:
                if not bool(row["provider_enabled"]) or str(row["account_status"]) != "active":
                    raise AuthenticationError("MAX sign-in is not available for this account")
                now_value = utc_text()
                conn.execute(
                    "UPDATE v4_external_identities SET last_seen_at = ? WHERE id = ?",
                    (now_value, int(row["identity_id"])),
                )
                conn.execute(
                    """
                    INSERT INTO v4_audit_log(
                        actor_account_id, action, entity_type, entity_id
                    ) VALUES (?, 'auth.login_succeeded', 'account', ?)
                    """,
                    (int(row["account_id"]), str(row["public_id"])),
                )
                return _issue_session(
                    conn, account_id=int(row["account_id"]), session_hours=session_hours
                )

            # No identity yet. A code is the only way in from here.
            if not link_code:
                raise LinkRequiredError("This MAX account is not linked yet")

            code_row = conn.execute(
                """
                SELECT id, account_id FROM v4_link_codes
                WHERE provider_code = 'max' AND code_hash = ?
                  AND consumed_at IS NULL AND revoked_at IS NULL
                  AND expires_at > ?
                """,
                (token_hash(str(link_code)), utc_text()),
            ).fetchone()
            if code_row is None:
                raise LinkRequiredError("This pairing code is invalid or expired")

            account_id = int(code_row["account_id"])
            account_row = conn.execute(
                "SELECT status, public_id FROM v4_accounts WHERE id = ?", (account_id,)
            ).fetchone()
            if account_row is None or str(account_row["status"]) != "active":
                raise AuthenticationError("The linked account is not active")

            now_value = utc_text()
            identity_cursor = conn.execute(
                """
                INSERT INTO v4_external_identities(
                    account_id, provider_code, provider_subject, provider_username,
                    verified_at, last_seen_at, created_at
                ) VALUES (?, 'max', ?, ?, ?, ?, ?)
                """,
                (
                    account_id,
                    max_user_id,
                    (max_username or "").strip()[:120] or None,
                    now_value,
                    now_value,
                    now_value,
                ),
            )
            conn.execute(
                "UPDATE v4_link_codes SET consumed_at = ?, consumed_identity_id = ? WHERE id = ?",
                (now_value, int(identity_cursor.lastrowid), int(code_row["id"])),
            )
            conn.execute(
                """
                INSERT INTO v4_audit_log(
                    actor_account_id, action, entity_type, entity_id, metadata_json
                ) VALUES (?, 'identity.linked', 'account', ?, ?)
                """,
                (
                    account_id,
                    str(account_row["public_id"]),
                    json.dumps({"provider_code": "max"}, separators=(",", ":")),
                ),
            )
            conn.execute(
                """
                INSERT INTO v4_audit_log(
                    actor_account_id, action, entity_type, entity_id
                ) VALUES (?, 'auth.login_succeeded', 'account', ?)
                """,
                (account_id, str(account_row["public_id"])),
            )
            return _issue_session(conn, account_id=account_id, session_hours=session_hours)
    finally:
        conn.close()


def load_principal(db_path: str | Path, session_token: str | None) -> Principal | None:
    if not session_token or len(session_token) > 256:
        return None
    session_token_hash = token_hash(session_token)
    now_value = utc_text()
    conn = connect_database(db_path)
    try:
        row = conn.execute(
            """
            SELECT
                s.account_id,
                s.token_hash,
                s.csrf_token_hash,
                s.expires_at,
                a.public_id,
                a.display_name
            FROM v4_sessions s
            JOIN v4_accounts a ON a.id = s.account_id
            WHERE s.token_hash = ?
              AND s.revoked_at IS NULL
              AND s.expires_at > ?
              AND a.status = 'active'
            """,
            (session_token_hash, now_value),
        ).fetchone()
        if row is None:
            return None
        account_id = int(row["account_id"])
        return Principal(
            account_id=account_id,
            public_id=str(row["public_id"]),
            display_name=str(row["display_name"]),
            token_hash=str(row["token_hash"]),
            csrf_token_hash=str(row["csrf_token_hash"]),
            expires_at=str(row["expires_at"]),
            roles=_load_roles(conn, account_id),
        )
    finally:
        conn.close()


def csrf_is_valid(
    principal: Principal,
    header_token: str | None,
    cookie_token: str | None,
) -> bool:
    if not header_token or not cookie_token:
        return False
    if len(header_token) > 256 or not hmac_compare(header_token, cookie_token):
        return False
    return hmac_compare(token_hash(header_token), principal.csrf_token_hash)


def hmac_compare(left: str, right: str) -> bool:
    return hmac.compare_digest(left, right)


def revoke_session(db_path: str | Path, principal: Principal) -> None:
    conn = connect_database(db_path)
    try:
        with immediate_transaction(conn):
            now_value = utc_text()
            conn.execute(
                """
                UPDATE v4_sessions
                SET revoked_at = ?
                WHERE token_hash = ? AND revoked_at IS NULL
                """,
                (now_value, principal.token_hash),
            )
            conn.execute(
                """
                INSERT INTO v4_audit_log(
                    actor_account_id, action, entity_type, entity_id
                ) VALUES (?, 'auth.logout', 'account', ?)
                """,
                (principal.account_id, principal.public_id),
            )
    finally:
        conn.close()
