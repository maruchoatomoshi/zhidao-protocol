from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from zhidao_v4.migrations import MigrationError, apply_migrations


ROOT = Path(__file__).resolve().parents[1]


class V4MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "zhidao.db"
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("CREATE TABLE legacy_probe(value TEXT NOT NULL)")
        self.conn.execute("INSERT INTO legacy_probe(value) VALUES ('preserved')")
        self.conn.commit()
        self.conn.close()

    def tearDown(self):
        self.temp_dir.cleanup()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def test_migration_is_additive_and_idempotent(self):
        first = apply_migrations(self.db_path)
        second = apply_migrations(self.db_path)

        self.assertEqual(first, ["0001_identity_seasons_groups.sql"])
        self.assertEqual(second, [])

        conn = self.connect()
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            expected = {
                "v4_accounts",
                "v4_external_identities",
                "v4_seasons",
                "v4_season_memberships",
                "v4_roles",
                "v4_role_assignments",
                "v4_groups",
                "v4_group_memberships",
                "v4_audit_log",
            }
            self.assertTrue(expected.issubset(tables))
            self.assertEqual(
                conn.execute("SELECT value FROM legacy_probe").fetchone()[0],
                "preserved",
            )
            roles = {
                row[0]
                for row in conn.execute("SELECT code FROM v4_roles ORDER BY code")
            }
            self.assertEqual(
                roles,
                {"participant", "operator", "architect", "system_admin"},
            )
            self.assertEqual(
                conn.execute(
                    "SELECT is_enabled FROM v4_identity_providers WHERE code = 'max'"
                ).fetchone()[0],
                0,
            )
        finally:
            conn.close()

    def test_migration_coexists_with_the_real_legacy_schema(self):
        env = os.environ.copy()
        env.update(
            {
                "ZHIDAO_DB_PATH": str(self.db_path),
                "ZHIDAO_API_ERROR_LOG": str(Path(self.temp_dir.name) / "api-error.log"),
                "TELEGRAM_AUTH_REQUIRED": "1",
                "ZHIDAO_ENABLE_WAL_CHECKPOINT": "0",
            }
        )
        code = """
import json
import os
import sqlite3

import zhidao_api_ready as legacy
from zhidao_v4.migrations import apply_migrations

applied = apply_migrations(os.environ["ZHIDAO_DB_PATH"])
conn = sqlite3.connect(os.environ["ZHIDAO_DB_PATH"])
tables = {row[0] for row in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table'"
)}
foreign_key_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
conn.close()
print(json.dumps({
    "applied": applied,
    "health": legacy.api_health(),
    "has_legacy": {"users", "events", "economy_log"}.issubset(tables),
    "has_v4": {"v4_accounts", "v4_seasons", "v4_groups"}.issubset(tables),
    "foreign_key_errors": foreign_key_errors,
}))
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(payload["applied"], ["0001_identity_seasons_groups.sql"])
        self.assertEqual(payload["health"]["status"], "ok")
        self.assertTrue(payload["has_legacy"])
        self.assertTrue(payload["has_v4"])
        self.assertEqual(payload["foreign_key_errors"], [])

    def test_identity_role_and_group_invariants(self):
        apply_migrations(self.db_path)
        conn = self.connect()
        try:
            conn.execute(
                "INSERT INTO v4_accounts(public_id, display_name) VALUES (?, ?)",
                ("acct-admin-001", "Architect"),
            )
            conn.execute(
                "INSERT INTO v4_accounts(public_id, display_name) VALUES (?, ?)",
                ("acct-child-001", "Participant"),
            )
            admin_id, child_id = [
                row[0] for row in conn.execute("SELECT id FROM v4_accounts ORDER BY id")
            ]
            conn.execute(
                """
                INSERT INTO v4_external_identities(
                    account_id, provider_code, provider_subject
                ) VALUES (?, 'telegram', '10001')
                """,
                (child_id,),
            )
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO v4_external_identities(
                        account_id, provider_code, provider_subject
                    ) VALUES (?, 'telegram', '10001')
                    """,
                    (admin_id,),
                )

            conn.execute(
                """
                INSERT INTO v4_seasons(code, name, created_by_account_id)
                VALUES ('hainan-2027', 'ZHIDAO Hainan', ?)
                """,
                (admin_id,),
            )
            season_id = conn.execute("SELECT id FROM v4_seasons").fetchone()[0]
            conn.execute(
                """
                INSERT INTO v4_season_memberships(
                    season_id, account_id, member_number, status
                ) VALUES (?, ?, 1, 'active')
                """,
                (season_id, child_id),
            )
            season_member_id = conn.execute(
                "SELECT id FROM v4_season_memberships"
            ).fetchone()[0]
            conn.executemany(
                "INSERT INTO v4_groups(season_id, code, name) VALUES (?, ?, ?)",
                [
                    (season_id, "dragon", "Драконы"),
                    (season_id, "qilin", "Цилини"),
                ],
            )
            dragon_id, qilin_id = [
                row[0] for row in conn.execute("SELECT id FROM v4_groups ORDER BY id")
            ]
            conn.execute(
                """
                INSERT INTO v4_group_memberships(
                    season_id, group_id, season_membership_id, membership_role
                ) VALUES (?, ?, ?, 'member')
                """,
                (season_id, dragon_id, season_member_id),
            )
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO v4_group_memberships(
                        season_id, group_id, season_membership_id, membership_role
                    ) VALUES (?, ?, ?, 'member')
                    """,
                    (season_id, qilin_id, season_member_id),
                )

            conn.execute(
                """
                INSERT INTO v4_role_assignments(
                    account_id, role_code, granted_by_account_id
                ) VALUES (?, 'operator', ?)
                """,
                (admin_id, admin_id),
            )
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO v4_role_assignments(
                        account_id, role_code, granted_by_account_id
                    ) VALUES (?, 'operator', ?)
                    """,
                    (admin_id, admin_id),
                )
            conn.rollback()
        finally:
            conn.close()

    def test_audit_log_is_append_only_and_checksum_is_verified(self):
        apply_migrations(self.db_path)
        conn = self.connect()
        try:
            conn.execute(
                """
                INSERT INTO v4_audit_log(action, entity_type, entity_id, after_json)
                VALUES ('season.created', 'season', '1', '{"status":"draft"}')
                """
            )
            conn.commit()
            with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
                conn.execute("UPDATE v4_audit_log SET action = 'changed' WHERE id = 1")
            conn.rollback()
            with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
                conn.execute("DELETE FROM v4_audit_log WHERE id = 1")
            conn.rollback()

            conn.execute(
                "UPDATE v4_schema_migrations SET checksum = ? WHERE version = 1",
                ("0" * 64,),
            )
            conn.commit()
        finally:
            conn.close()

        with self.assertRaisesRegex(MigrationError, "does not match"):
            apply_migrations(self.db_path)


if __name__ == "__main__":
    unittest.main()
