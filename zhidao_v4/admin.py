from __future__ import annotations

import sqlite3

from .auth import utc_text


def architect_overview(conn: sqlite3.Connection) -> dict:
    now = utc_text()
    counts = {
        "accounts": conn.execute("SELECT COUNT(*) FROM v4_accounts").fetchone()[0],
        "seasons": conn.execute("SELECT COUNT(*) FROM v4_seasons").fetchone()[0],
        "draft_seasons": conn.execute(
            "SELECT COUNT(*) FROM v4_seasons WHERE status = 'draft'"
        ).fetchone()[0],
        "active_sessions": conn.execute(
            """
            SELECT COUNT(*) FROM v4_sessions
            WHERE revoked_at IS NULL AND expires_at > ?
            """,
            (now,),
        ).fetchone()[0],
        "audit_entries": conn.execute("SELECT COUNT(*) FROM v4_audit_log").fetchone()[0],
    }
    schema_version = conn.execute(
        "SELECT COALESCE(MAX(version), 0) FROM v4_schema_migrations"
    ).fetchone()[0]
    activity = [
        {
            "id": int(row["id"]),
            "occurred_at": str(row["occurred_at"]),
            "actor": row["actor"],
            "action": str(row["action"]),
            "entity_type": str(row["entity_type"]),
            "entity_id": row["entity_id"],
            "season_id": row["season_id"],
        }
        for row in conn.execute(
            """
            SELECT l.id, l.occurred_at, a.display_name AS actor, l.action,
                   l.entity_type, l.entity_id, l.season_id
            FROM v4_audit_log l
            LEFT JOIN v4_accounts a ON a.id = l.actor_account_id
            ORDER BY l.id DESC
            LIMIT 12
            """
        )
    ]
    return {
        "status": "ok",
        "schema_version": int(schema_version),
        "counts": {key: int(value) for key, value in counts.items()},
        "recent_activity": activity,
    }
