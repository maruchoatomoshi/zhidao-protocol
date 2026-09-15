"""Вход по паролю не держит запись в базу, пока считается scrypt.

scrypt нарочно медленный. Пока он считался внутри BEGIN IMMEDIATE, каждый
вход занимал единственное место писателя SQLite, и серия логинов тормозила
посторонние игровые записи. Теперь пароль проверяется вне транзакции, а
решение принимается в короткой транзакции по заново прочитанному состоянию.
Эти тесты держат проверку пароля «на паузе» и смотрят, что происходит вокруг.
"""

from __future__ import annotations

import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from zhidao_v4 import auth
from zhidao_v4.auth import AuthenticationError, authenticate_local
from zhidao_v4.bootstrap import bootstrap_system_admin
from zhidao_v4.security import hash_password


USERNAME = "architect"
PASSWORD = "correct horse battery staple"


class PausedVerification:
    """verify_password с настоящим результатом, но ждёт сигнала перед ответом."""

    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.real = auth.verify_password

    def __call__(self, password: str, encoded: str) -> bool:
        self.started.set()
        self.release.wait(10)
        return self.real(password, encoded)


class V4AuthLockTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "zhidao.db"
        bootstrap_system_admin(
            self.db_path,
            username=USERNAME,
            password=PASSWORD,
            display_name="Architect",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def login_in_background(self, password: str) -> tuple[threading.Thread, dict]:
        outcome: dict = {}

        def run():
            try:
                outcome["result"] = authenticate_local(
                    self.db_path, username=USERNAME, password=password
                )
            except AuthenticationError as exc:
                outcome["error"] = exc

        thread = threading.Thread(target=run)
        thread.start()
        return thread, outcome

    def write_while_paused(self, verification: PausedVerification, sql: str, params=()):
        """Пишет в базу, пока вход стоит на проверке пароля.

        Таймаут занятости короткий: если вход держит блокировку записи,
        BEGIN IMMEDIATE падает с «database is locked», и тест это покажет.
        """
        self.assertTrue(verification.started.wait(10), "login never reached scrypt")
        conn = sqlite3.connect(self.db_path, timeout=0.5, isolation_level=None)
        try:
            conn.execute("PRAGMA busy_timeout=500")
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(sql, params)
            conn.execute("COMMIT")
        finally:
            conn.close()

    def credential_state(self) -> tuple[int, str | None, int]:
        conn = sqlite3.connect(self.db_path)
        try:
            failed_attempts, locked_until = conn.execute(
                "SELECT failed_attempts, locked_until FROM v4_local_credentials"
            ).fetchone()
            sessions = conn.execute("SELECT count(*) FROM v4_sessions").fetchone()[0]
        finally:
            conn.close()
        return failed_attempts, locked_until, sessions

    def run_paused_login(self, password: str, sql: str, params=()) -> dict:
        verification = PausedVerification()
        with mock.patch.object(auth, "verify_password", verification):
            thread, outcome = self.login_in_background(password)
            try:
                self.write_while_paused(verification, sql, params)
            finally:
                verification.release.set()
                thread.join(10)
        self.assertFalse(thread.is_alive())
        return outcome

    def test_a_game_write_is_not_blocked_by_a_password_check(self):
        outcome = self.run_paused_login(
            PASSWORD,
            "INSERT INTO v4_audit_log(action, entity_type, entity_id)"
            " VALUES ('test.concurrent_write', 'test', 'during-login')",
        )

        self.assertIn("result", outcome)
        self.assertEqual(self.credential_state(), (0, None, 1))

    def test_a_lock_placed_during_the_check_refuses_the_right_password(self):
        outcome = self.run_paused_login(
            PASSWORD,
            "UPDATE v4_local_credentials"
            " SET failed_attempts = 5, locked_until = '2999-01-01T00:00:00.000Z'",
        )

        self.assertIn("error", outcome)
        self.assertEqual(
            self.credential_state(), (5, "2999-01-01T00:00:00.000Z", 0)
        )

    def test_a_password_changed_during_the_check_is_not_accepted_or_counted(self):
        outcome = self.run_paused_login(
            PASSWORD,
            "UPDATE v4_local_credentials SET password_hash = ?",
            (hash_password("a brand new passphrase"),),
        )

        self.assertIn("error", outcome)
        self.assertEqual(self.credential_state(), (0, None, 0))

    def test_parallel_wrong_passwords_are_all_counted(self):
        threads = [self.login_in_background("still wrong")[0] for _ in range(5)]
        for thread in threads:
            thread.join(30)

        failed_attempts, locked_until, sessions = self.credential_state()
        self.assertEqual(failed_attempts, 5)
        self.assertIsNotNone(locked_until)
        self.assertEqual(sessions, 0)


if __name__ == "__main__":
    unittest.main()
