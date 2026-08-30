from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .auth import utc_text


SEASON_CODE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
HAINAN_DRAFT = {
    "code": "hainan-v4",
    "name": "ZHIDAO Protocol V4.0 Hainan",
    "starts_on": None,
    "ends_on": None,
    "timezone": "Asia/Shanghai",
    "theme_key": "hainan-aqua",
}


class SeasonValidationError(ValueError):
    pass


class SeasonConflict(RuntimeError):
    pass


class IdempotencyConflict(RuntimeError):
    pass


class SeasonNotFound(RuntimeError):
    pass


class SeasonStateConflict(RuntimeError):
    pass


class SeasonRevisionConflict(RuntimeError):
    pass


def normalize_season_code(code: str) -> str:
    normalized = str(code or "").strip().lower()
    if not SEASON_CODE_RE.fullmatch(normalized):
        raise SeasonValidationError(
            "Season code must be 2-64 lowercase ASCII letters, digits, or dashes"
        )
    return normalized


def normalize_idempotency_key(value: str) -> str:
    normalized = str(value or "").strip()
    if not IDEMPOTENCY_KEY_RE.fullmatch(normalized):
        raise SeasonValidationError(
            "Idempotency key must be 8-128 ASCII letters, digits, dots, dashes, underscores, or colons"
        )
    return normalized


def _date_text(value: date | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError as exc:
        raise SeasonValidationError("Season dates must use ISO YYYY-MM-DD") from exc


def _normalize_payload(
    *,
    code: str,
    name: str,
    starts_on: date | str | None,
    ends_on: date | str | None,
    timezone: str,
    theme_key: str | None,
) -> dict:
    clean_code = normalize_season_code(code)
    clean_name = str(name or "").strip()
    if not 1 <= len(clean_name) <= 120:
        raise SeasonValidationError("Season name must contain 1-120 characters")
    start_value = _date_text(starts_on)
    end_value = _date_text(ends_on)
    if start_value and end_value and start_value > end_value:
        raise SeasonValidationError("Season end date cannot be before its start date")
    clean_timezone = str(timezone or "").strip()
    try:
        ZoneInfo(clean_timezone)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise SeasonValidationError("Unknown IANA timezone") from exc
    clean_theme = str(theme_key).strip() if theme_key is not None else None
    if clean_theme == "":
        clean_theme = None
    if clean_theme and len(clean_theme) > 64:
        raise SeasonValidationError("Theme key must not exceed 64 characters")
    return {
        "code": clean_code,
        "name": clean_name,
        "starts_on": start_value,
        "ends_on": end_value,
        "timezone": clean_timezone,
        "theme_key": clean_theme,
    }


def _canonical_json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": int(row["id"]),
        "code": str(row["code"]),
        "name": str(row["name"]),
        "status": str(row["status"]),
        "starts_on": row["starts_on"],
        "ends_on": row["ends_on"],
        "timezone": str(row["timezone"]),
        "theme_key": row["theme_key"],
        "created_by_account_id": row["created_by_account_id"],
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "revision": int(row["revision"]),
    }


def create_draft_season(
    conn: sqlite3.Connection,
    *,
    actor_account_id: int,
    idempotency_key: str,
    code: str,
    name: str,
    starts_on: date | str | None = None,
    ends_on: date | str | None = None,
    timezone: str = "Asia/Shanghai",
    theme_key: str | None = None,
    request_id: str | None = None,
) -> tuple[dict, bool]:
    key = normalize_idempotency_key(idempotency_key)
    payload = _normalize_payload(
        code=code,
        name=name,
        starts_on=starts_on,
        ends_on=ends_on,
        timezone=timezone,
        theme_key=theme_key,
    )
    request_hash = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    operation = "season.create"

    existing = conn.execute(
        """
        SELECT request_hash, response_json
        FROM v4_idempotency_keys
        WHERE account_id = ? AND operation = ? AND idempotency_key = ?
        """,
        (actor_account_id, operation, key),
    ).fetchone()
    if existing:
        if str(existing["request_hash"]) != request_hash:
            raise IdempotencyConflict("Idempotency key was already used for another request")
        return json.loads(str(existing["response_json"])), True

    now = utc_text()
    try:
        cursor = conn.execute(
            """
            INSERT INTO v4_seasons(
                code, name, status, starts_on, ends_on, timezone, theme_key,
                created_by_account_id, created_at, updated_at
            ) VALUES (?, ?, 'draft', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["code"],
                payload["name"],
                payload["starts_on"],
                payload["ends_on"],
                payload["timezone"],
                payload["theme_key"],
                actor_account_id,
                now,
                now,
            ),
        )
    except sqlite3.IntegrityError as exc:
        raise SeasonConflict(f"Season code already exists: {payload['code']}") from exc

    season_id = int(cursor.lastrowid)
    row = conn.execute(
        """
        SELECT id, code, name, status, starts_on, ends_on, timezone, theme_key,
               created_by_account_id, created_at, updated_at, revision
        FROM v4_seasons WHERE id = ?
        """,
        (season_id,),
    ).fetchone()
    response = _row_to_dict(row)
    response_json = _canonical_json(response)
    conn.execute(
        """
        INSERT INTO v4_audit_log(
            actor_account_id, season_id, action, entity_type, entity_id,
            request_id, after_json, metadata_json
        ) VALUES (?, ?, 'season.created', 'season', ?, ?, ?, ?)
        """,
        (
            actor_account_id,
            season_id,
            str(season_id),
            request_id,
            response_json,
            _canonical_json({"idempotency_key": key}),
        ),
    )
    conn.execute(
        """
        INSERT INTO v4_idempotency_keys(
            account_id, operation, idempotency_key, request_hash,
            response_status, response_json
        ) VALUES (?, ?, ?, ?, 201, ?)
        """,
        (actor_account_id, operation, key, request_hash, response_json),
    )
    return response, False


def update_draft_season(
    conn: sqlite3.Connection,
    *,
    season_id: int,
    actor_account_id: int,
    expected_revision: int,
    idempotency_key: str,
    name: str,
    starts_on: date | str | None,
    ends_on: date | str | None,
    timezone: str,
    theme_key: str | None,
    request_id: str | None = None,
) -> tuple[dict, bool]:
    key = normalize_idempotency_key(idempotency_key)
    if expected_revision < 1:
        raise SeasonValidationError("Expected revision must be positive")
    editable = _normalize_payload(
        code="placeholder",
        name=name,
        starts_on=starts_on,
        ends_on=ends_on,
        timezone=timezone,
        theme_key=theme_key,
    )
    editable.pop("code")
    request_payload = {
        "season_id": season_id,
        "expected_revision": expected_revision,
        **editable,
    }
    request_hash = hashlib.sha256(
        _canonical_json(request_payload).encode("utf-8")
    ).hexdigest()
    operation = f"season.update:{season_id}"

    existing = conn.execute(
        """
        SELECT request_hash, response_json
        FROM v4_idempotency_keys
        WHERE account_id = ? AND operation = ? AND idempotency_key = ?
        """,
        (actor_account_id, operation, key),
    ).fetchone()
    if existing:
        if str(existing["request_hash"]) != request_hash:
            raise IdempotencyConflict("Idempotency key was already used for another request")
        return json.loads(str(existing["response_json"])), True

    row = conn.execute(
        """
        SELECT id, code, name, status, starts_on, ends_on, timezone, theme_key,
               created_by_account_id, created_at, updated_at, revision
        FROM v4_seasons WHERE id = ?
        """,
        (season_id,),
    ).fetchone()
    if row is None:
        raise SeasonNotFound("Season not found")
    if str(row["status"]) != "draft":
        raise SeasonStateConflict("Only a draft season can be edited")
    if int(row["revision"]) != expected_revision:
        raise SeasonRevisionConflict("Season was changed in another session")

    before = _row_to_dict(row)
    now = utc_text()
    cursor = conn.execute(
        """
        UPDATE v4_seasons
        SET name = ?, starts_on = ?, ends_on = ?, timezone = ?, theme_key = ?,
            updated_at = ?, revision = revision + 1
        WHERE id = ? AND status = 'draft' AND revision = ?
        """,
        (
            editable["name"],
            editable["starts_on"],
            editable["ends_on"],
            editable["timezone"],
            editable["theme_key"],
            now,
            season_id,
            expected_revision,
        ),
    )
    if cursor.rowcount != 1:
        raise SeasonRevisionConflict("Season was changed in another session")

    updated_row = conn.execute(
        """
        SELECT id, code, name, status, starts_on, ends_on, timezone, theme_key,
               created_by_account_id, created_at, updated_at, revision
        FROM v4_seasons WHERE id = ?
        """,
        (season_id,),
    ).fetchone()
    response = _row_to_dict(updated_row)
    response_json = _canonical_json(response)
    conn.execute(
        """
        INSERT INTO v4_audit_log(
            actor_account_id, season_id, action, entity_type, entity_id,
            request_id, before_json, after_json, metadata_json
        ) VALUES (?, ?, 'season.updated', 'season', ?, ?, ?, ?, ?)
        """,
        (
            actor_account_id,
            season_id,
            str(season_id),
            request_id,
            _canonical_json(before),
            response_json,
            _canonical_json({"idempotency_key": key}),
        ),
    )
    conn.execute(
        """
        INSERT INTO v4_idempotency_keys(
            account_id, operation, idempotency_key, request_hash,
            response_status, response_json
        ) VALUES (?, ?, ?, ?, 200, ?)
        """,
        (actor_account_id, operation, key, request_hash, response_json),
    )
    return response, False


def list_seasons(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, code, name, status, starts_on, ends_on, timezone, theme_key,
               created_by_account_id, created_at, updated_at, revision
        FROM v4_seasons
        ORDER BY created_at DESC, id DESC
        """
    )
    return [_row_to_dict(row) for row in rows]
