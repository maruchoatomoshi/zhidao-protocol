from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from zhidao_v4.api import CSRF_COOKIE, SESSION_COOKIE, create_app
from zhidao_v4.auth import provision_local_account
from zhidao_v4.bootstrap import BootstrapError, bootstrap_system_admin
from zhidao_v4.db import connect_database, immediate_transaction
from zhidao_v4.security import token_hash


ADMIN_USERNAME = "architect"
ADMIN_PASSWORD = "correct horse battery staple"
OPERATOR_USERNAME = "operator.one"
OPERATOR_PASSWORD = "operator secure passphrase"


class V4AuthApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "zhidao.db"
        self.bootstrap = bootstrap_system_admin(
            self.db_path,
            username=ADMIN_USERNAME,
            password=ADMIN_PASSWORD,
            display_name="Architect",
        )
        self.client = TestClient(
            create_app(self.db_path, cookie_secure=False, session_hours=1)
        )

    def tearDown(self):
        self.client.close()
        self.temp_dir.cleanup()

    def login_admin(self) -> str:
        response = self.client.post(
            "/api/v4/auth/login",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["csrf_token"]

    def test_bootstrap_creates_admin_and_hainan_draft_once(self):
        self.assertEqual(self.bootstrap["account"]["role_code"], "system_admin")
        self.assertEqual(
            self.bootstrap["account"]["role_codes"],
            ["system_admin", "architect"],
        )
        self.assertEqual(self.bootstrap["season"]["code"], "hainan-v4")
        self.assertEqual(self.bootstrap["season"]["status"], "draft")

        with self.assertRaisesRegex(BootstrapError, "already exists"):
            bootstrap_system_admin(
                self.db_path,
                username="second.admin",
                password="another secure passphrase",
                display_name="Second Admin",
            )

        health = self.client.get("/api/v4/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["schema_version"], 3)

    def test_architect_console_is_served_with_security_headers(self):
        redirect = self.client.get("/", follow_redirects=False)
        self.assertIn(redirect.status_code, {302, 307})
        self.assertEqual(redirect.headers["location"], "/architect/")

        console = self.client.get("/architect/")
        self.assertEqual(console.status_code, 200)
        self.assertIn("Architect Console", console.text)
        self.assertIn("default-src 'self'", console.headers["content-security-policy"])
        self.assertEqual(console.headers["x-frame-options"], "DENY")
        self.assertEqual(
            console.headers["permissions-policy"],
            "camera=(), microphone=(), geolocation=()",
        )

        stylesheet = self.client.get("/architect/architect.css")
        self.assertEqual(stylesheet.status_code, 200)
        self.assertIn("text/css", stylesheet.headers["content-type"])

        hainan_scene = self.client.get(
            "/architect/assets/hainan-promised-tomorrow.png"
        )
        self.assertEqual(hainan_scene.status_code, 200)
        self.assertIn("image/png", hainan_scene.headers["content-type"])
        self.assertGreater(len(hainan_scene.content), 100_000)

    def test_participant_design_preview_is_served_without_account_data(self):
        preview = self.client.get("/app/")
        self.assertEqual(preview.status_code, 200)
        self.assertIn("DESIGN PREVIEW", preview.text)
        self.assertIn("Курс на", preview.text)
        self.assertIn("default-src 'self'", preview.headers["content-security-policy"])
        self.assertEqual(preview.headers["x-frame-options"], "DENY")
        self.assertEqual(
            preview.headers["permissions-policy"],
            "camera=(), microphone=(), geolocation=(self)",
        )

        stylesheet = self.client.get("/app/app.css")
        self.assertEqual(stylesheet.status_code, 200)
        self.assertIn("text/css", stylesheet.headers["content-type"])
        self.assertIn('"Trebuchet MS"', stylesheet.text)

        icon = self.client.get("/app/assets/icons/nav-schedule.png")
        self.assertEqual(icon.status_code, 200)
        self.assertIn("image/png", icon.headers["content-type"])
        self.assertGreater(len(icon.content), 20_000)

    def test_login_stores_only_token_hashes_and_exposes_roles(self):
        wrong = self.client.post(
            "/api/v4/auth/login",
            json={"username": ADMIN_USERNAME, "password": "wrong password"},
        )
        self.assertEqual(wrong.status_code, 401)

        csrf_token = self.login_admin()
        session_token = self.client.cookies.get(SESSION_COOKIE)
        csrf_cookie = self.client.cookies.get(CSRF_COOKIE)
        self.assertTrue(session_token)
        self.assertEqual(csrf_cookie, csrf_token)

        me = self.client.get("/api/v4/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["account"]["display_name"], "Architect")
        self.assertIn(
            {"code": "system_admin", "season_id": None},
            me.json()["roles"],
        )

        conn = sqlite3.connect(self.db_path)
        try:
            stored_session, stored_csrf = conn.execute(
                "SELECT token_hash, csrf_token_hash FROM v4_sessions"
            ).fetchone()
            password_hash = conn.execute(
                "SELECT password_hash FROM v4_local_credentials"
            ).fetchone()[0]
            with self.assertRaisesRegex(
                sqlite3.IntegrityError,
                "credential identity must remain local",
            ):
                conn.execute(
                    """
                    UPDATE v4_external_identities
                    SET provider_code = 'telegram'
                    WHERE provider_code = 'local'
                    """
                )
            conn.rollback()
        finally:
            conn.close()
        self.assertEqual(stored_session, token_hash(session_token))
        self.assertEqual(stored_csrf, token_hash(csrf_token))
        self.assertNotEqual(stored_session, session_token)
        self.assertNotEqual(stored_csrf, csrf_token)
        self.assertTrue(password_hash.startswith("scrypt$"))
        self.assertNotIn(ADMIN_PASSWORD, password_hash)

    def test_season_creation_requires_csrf_role_and_idempotency(self):
        csrf_token = self.login_admin()
        payload = {
            "code": "hainan-rehearsal",
            "name": "Hainan Rehearsal",
            "timezone": "Asia/Shanghai",
            "theme_key": "hainan-aqua",
        }

        missing_csrf = self.client.post(
            "/api/v4/seasons",
            json=payload,
            headers={"x-idempotency-key": "season:create:rehearsal"},
        )
        self.assertEqual(missing_csrf.status_code, 403)

        headers = {
            "x-csrf-token": csrf_token,
            "x-idempotency-key": "season:create:rehearsal",
        }
        created = self.client.post("/api/v4/seasons", json=payload, headers=headers)
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["status"], "draft")
        self.assertEqual(created.headers["x-idempotent-replayed"], "false")

        replay = self.client.post("/api/v4/seasons", json=payload, headers=headers)
        self.assertEqual(replay.status_code, 201, replay.text)
        self.assertEqual(replay.json(), created.json())
        self.assertEqual(replay.headers["x-idempotent-replayed"], "true")

        changed = dict(payload, name="Changed request")
        conflict = self.client.post("/api/v4/seasons", json=changed, headers=headers)
        self.assertEqual(conflict.status_code, 409)

        seasons = self.client.get("/api/v4/seasons")
        self.assertEqual(seasons.status_code, 200)
        self.assertEqual(
            {item["code"] for item in seasons.json()["items"]},
            {"hainan-v4", "hainan-rehearsal"},
        )

        conn = sqlite3.connect(self.db_path)
        try:
            rehearsal_count = conn.execute(
                "SELECT COUNT(*) FROM v4_seasons WHERE code = 'hainan-rehearsal'"
            ).fetchone()[0]
            audit_count = conn.execute(
                "SELECT COUNT(*) FROM v4_audit_log WHERE action = 'season.created'"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(rehearsal_count, 1)
        self.assertEqual(audit_count, 2)

    def test_operator_is_denied_system_admin_action(self):
        conn = connect_database(self.db_path)
        try:
            with immediate_transaction(conn):
                provision_local_account(
                    conn,
                    username=OPERATOR_USERNAME,
                    password=OPERATOR_PASSWORD,
                    display_name="Operator",
                    role_code="operator",
                    actor_account_id=self.bootstrap["account"]["id"],
                )
        finally:
            conn.close()

        operator_client = TestClient(
            create_app(self.db_path, cookie_secure=False, session_hours=1)
        )
        try:
            login = operator_client.post(
                "/api/v4/auth/login",
                json={"username": OPERATOR_USERNAME, "password": OPERATOR_PASSWORD},
            )
            self.assertEqual(login.status_code, 200, login.text)
            csrf_token = login.json()["csrf_token"]
            denied = operator_client.post(
                "/api/v4/seasons",
                json={"code": "forbidden-season", "name": "Forbidden"},
                headers={
                    "x-csrf-token": csrf_token,
                    "x-idempotency-key": "operator:forbidden:season",
                },
            )
            self.assertEqual(denied.status_code, 403)
            self.assertEqual(denied.json()["detail"], "Insufficient role")
        finally:
            operator_client.close()

    def test_role_revocation_takes_effect_for_an_existing_session(self):
        csrf_token = self.login_admin()
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                UPDATE v4_role_assignments
                SET revoked_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE account_id = ? AND role_code IN ('system_admin', 'architect')
                """,
                (self.bootstrap["account"]["id"],),
            )
            conn.commit()
        finally:
            conn.close()

        denied = self.client.post(
            "/api/v4/seasons",
            json={"code": "revoked-admin", "name": "Revoked"},
            headers={
                "x-csrf-token": csrf_token,
                "x-idempotency-key": "revoked:admin:season",
            },
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["detail"], "Insufficient role")

    def test_architect_updates_hainan_with_revision_protection(self):
        csrf_token = self.login_admin()
        seasons = self.client.get("/api/v4/seasons").json()["items"]
        hainan = next(item for item in seasons if item["code"] == "hainan-v4")
        payload = {
            "expected_revision": hainan["revision"],
            "name": "ZHIDAO V4 · Hainan Expedition",
            "starts_on": "2027-03-15",
            "ends_on": "2027-03-29",
            "timezone": "Asia/Shanghai",
            "theme_key": "hainan-aqua",
        }
        headers = {
            "x-csrf-token": csrf_token,
            "x-idempotency-key": "architect:hainan:update:0001",
        }
        updated = self.client.patch(
            f"/api/v4/seasons/{hainan['id']}",
            json=payload,
            headers=headers,
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["revision"], hainan["revision"] + 1)
        self.assertEqual(updated.json()["starts_on"], "2027-03-15")
        self.assertEqual(updated.headers["x-idempotent-replayed"], "false")

        replay = self.client.patch(
            f"/api/v4/seasons/{hainan['id']}",
            json=payload,
            headers=headers,
        )
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), updated.json())
        self.assertEqual(replay.headers["x-idempotent-replayed"], "true")

        stale = self.client.patch(
            f"/api/v4/seasons/{hainan['id']}",
            json=dict(payload, name="Stale update"),
            headers={
                "x-csrf-token": csrf_token,
                "x-idempotency-key": "architect:hainan:update:stale",
            },
        )
        self.assertEqual(stale.status_code, 409)
        self.assertIn("another session", stale.json()["detail"])

        overview = self.client.get("/api/v4/admin/overview")
        self.assertEqual(overview.status_code, 200)
        self.assertEqual(overview.json()["schema_version"], 3)
        actions = [item["action"] for item in overview.json()["recent_activity"]]
        self.assertIn("season.updated", actions)

    def test_logout_revokes_session_and_bad_passwords_lock_account(self):
        csrf_token = self.login_admin()
        logout = self.client.post(
            "/api/v4/auth/logout",
            headers={"x-csrf-token": csrf_token},
        )
        self.assertEqual(logout.status_code, 204, logout.text)
        self.assertEqual(self.client.get("/api/v4/auth/me").status_code, 401)

        for _ in range(5):
            response = self.client.post(
                "/api/v4/auth/login",
                json={"username": ADMIN_USERNAME, "password": "still wrong"},
            )
            self.assertEqual(response.status_code, 401)
        locked = self.client.post(
            "/api/v4/auth/login",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        )
        self.assertEqual(locked.status_code, 401)

        conn = sqlite3.connect(self.db_path)
        try:
            failed_attempts, locked_until = conn.execute(
                "SELECT failed_attempts, locked_until FROM v4_local_credentials"
            ).fetchone()
        finally:
            conn.close()
        self.assertGreaterEqual(failed_attempts, 5)
        self.assertIsNotNone(locked_until)

    def test_login_rate_limit_is_enforced_per_client(self):
        limited_client = TestClient(
            create_app(
                self.db_path,
                cookie_secure=False,
                session_hours=1,
                login_attempts_per_minute=2,
            )
        )
        try:
            for _ in range(2):
                response = limited_client.post(
                    "/api/v4/auth/login",
                    json={"username": "missing.user", "password": "not the password"},
                )
                self.assertEqual(response.status_code, 401)
            limited = limited_client.post(
                "/api/v4/auth/login",
                json={"username": "missing.user", "password": "not the password"},
            )
            self.assertEqual(limited.status_code, 429)
            self.assertEqual(limited.headers["retry-after"], "60")
        finally:
            limited_client.close()


if __name__ == "__main__":
    unittest.main()
