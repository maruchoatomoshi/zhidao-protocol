from __future__ import annotations

import contextlib
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from zhidao_v4.api import create_app
from zhidao_v4.bootstrap import bootstrap_system_admin
from zhidao_v4.passwd import main as passwd_main
from zhidao_v4.provision import generate_password
from zhidao_v4.provision import main as provision_main
from zhidao_v4.roles import main as roles_main


ADMIN_USERNAME = "architect"
ADMIN_PASSWORD = "correct horse battery staple"


@contextlib.contextmanager
def _capture():
    """Перехватывает stdout: пароль печатается туда и только туда."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        yield buffer


class AccountCliTests(unittest.TestCase):
    """Заведение учёток и смена пароля из командной строки.

    Проверяется не «команда отработала без исключения», а то, что после неё
    человек действительно входит новым паролем и не входит старым — через
    настоящий эндпоинт логина.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "zhidao.db"
        self.bootstrap = bootstrap_system_admin(
            self.db_path,
            username=ADMIN_USERNAME,
            password=ADMIN_PASSWORD,
            display_name="Архитектор",
        )
        self.client = TestClient(
            create_app(self.db_path, cookie_secure=False, session_hours=1)
        )

    def tearDown(self):
        self.client.close()
        self.temp_dir.cleanup()

    def login(self, username: str, password: str):
        return self.client.post(
            "/api/v4/auth/login", json={"username": username, "password": password}
        )

    def read_password(self, output: str) -> str:
        line = [ln for ln in output.splitlines() if ln.startswith("password: ")][-1]
        return line[len("password: "):]

    def test_generated_passwords_avoid_look_alike_characters(self):
        # Их переносят руками в файл окружения на сервере; «l» вместо «1»
        # стоит часа поисков.
        joined = "".join(generate_password() for _ in range(40))
        self.assertGreaterEqual(len(joined), 40)
        for char in "Il1O0":
            self.assertNotIn(char, joined)

    def test_provision_creates_an_account_that_can_sign_in(self):
        with _capture() as out:
            code = provision_main(
                [
                    "--db", str(self.db_path),
                    "--username", "mikhail",
                    "--display-name", "Михаил Юрьевич",
                    "--role", "operator",
                    "--random-password",
                    "--actor-account-id", str(self.bootstrap["account"]["id"]),
                ]
            )
        self.assertEqual(code, 0)
        password = self.read_password(out.getvalue())

        response = self.login("mikhail", password)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["account"]["display_name"], "Михаил Юрьевич")
        self.assertEqual(
            [role["code"] for role in response.json()["roles"]], ["operator"]
        )

    def test_a_taken_login_says_so_in_words(self):
        # Сырое «UNIQUE constraint failed: v4_external_identities...» человеку
        # не говорит ничего — а повторный запуск с тем же логином здесь самая
        # частая ошибка.
        with self.assertRaises(SystemExit) as caught, _capture():
            provision_main(
                [
                    "--db", str(self.db_path),
                    "--username", ADMIN_USERNAME,
                    "--display-name", "Второй Архитектор",
                    "--role", "operator",
                    "--random-password",
                ]
            )
        message = str(caught.exception)
        self.assertIn("уже занят", message)
        self.assertNotIn("UNIQUE constraint", message)

        # И главное: первая учётка цела, пароль у неё прежний.
        self.assertEqual(self.login(ADMIN_USERNAME, ADMIN_PASSWORD).status_code, 200)

    def test_list_shows_logins_names_and_roles(self):
        with _capture() as out:
            code = provision_main(["--db", str(self.db_path), "--list"])
        self.assertEqual(code, 0)
        listing = out.getvalue()
        self.assertIn(ADMIN_USERNAME, listing)
        self.assertIn("Архитектор", listing)
        self.assertIn("system_admin", listing)

    def test_creating_without_the_required_arguments_names_them(self):
        with self.assertRaises(SystemExit) as caught, _capture():
            provision_main(["--db", str(self.db_path), "--username", "someone"])
        self.assertIn("--display-name", str(caught.exception))
        self.assertIn("--role", str(caught.exception))

    def test_password_change_replaces_the_old_one_and_keeps_the_account(self):
        before = self.login(ADMIN_USERNAME, ADMIN_PASSWORD)
        self.assertEqual(before.status_code, 200, before.text)
        public_id = before.json()["account"]["public_id"]
        self.client.cookies.clear()

        with _capture() as out:
            code = passwd_main(
                ["--db", str(self.db_path), "--username", ADMIN_USERNAME, "--random-password"]
            )
        self.assertEqual(code, 0)
        new_password = self.read_password(out.getvalue())

        self.assertEqual(self.login(ADMIN_USERNAME, ADMIN_PASSWORD).status_code, 401)
        after = self.login(ADMIN_USERNAME, new_password)
        self.assertEqual(after.status_code, 200, after.text)
        # Та же учётная запись, а не новая рядом: public_id и роли на месте.
        self.assertEqual(after.json()["account"]["public_id"], public_id)
        # Загрузочная учётка несёт обе роли — architect и system_admin;
        # смена пароля не должна тронуть ни одну.
        self.assertEqual(
            sorted(role["code"] for role in after.json()["roles"]),
            ["architect", "system_admin"],
        )

    def test_password_change_revokes_existing_sessions(self):
        signed_in = TestClient(
            create_app(self.db_path, cookie_secure=False, session_hours=1)
        )
        try:
            login = signed_in.post(
                "/api/v4/auth/login",
                json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
            )
            self.assertEqual(login.status_code, 200, login.text)
            self.assertEqual(signed_in.get("/api/v4/auth/me").status_code, 200)

            with _capture():
                passwd_main(
                    [
                        "--db", str(self.db_path),
                        "--username", ADMIN_USERNAME,
                        "--random-password",
                    ]
                )

            # Смысл смены пароля в том, чтобы прежний доступ прекратился.
            self.assertEqual(signed_in.get("/api/v4/auth/me").status_code, 401)
        finally:
            signed_in.close()

    def test_password_change_clears_a_lockout(self):
        for _ in range(12):
            self.login(ADMIN_USERNAME, "wrong password entirely")
        conn = sqlite3.connect(self.db_path)
        try:
            locked_before = conn.execute(
                "SELECT locked_until FROM v4_local_credentials"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertIsNotNone(locked_before, "аккаунт должен был заблокироваться")

        with _capture() as out:
            passwd_main(
                ["--db", str(self.db_path), "--username", ADMIN_USERNAME, "--random-password"]
            )
        new_password = self.read_password(out.getvalue())

        # Человек, пришедший к администратору за новым паролем, уже доказал,
        # кто он: ждать окончания блокировки ему незачем.
        response = self.login(ADMIN_USERNAME, new_password)
        self.assertEqual(response.status_code, 200, response.text)

    def test_password_change_for_an_unknown_login_fails_loudly(self):
        with self.assertRaises(SystemExit) as caught, _capture():
            passwd_main(
                ["--db", str(self.db_path), "--username", "nobody", "--random-password"]
            )
        self.assertIn("No local account", str(caught.exception))

    def test_login_is_normalised_the_same_way_on_both_commands(self):
        with _capture() as out:
            provision_main(
                [
                    "--db", str(self.db_path),
                    "--username", "  MixedCase  ",
                    "--display-name", "Смешанный Регистр",
                    "--role", "participant",
                    "--random-password",
                ]
            )
        created = self.read_password(out.getvalue())
        self.assertEqual(self.login("mixedcase", created).status_code, 200)

        with _capture() as out:
            passwd_main(
                ["--db", str(self.db_path), "--username", "MIXEDCASE", "--random-password"]
            )
        changed = self.read_password(out.getvalue())
        self.assertEqual(self.login("mixedcase", changed).status_code, 200)



class RoleCliTests(unittest.TestCase):
    """Выдача и отзыв роли уже существующей учётке.

    До этого роль назначалась только при заведении: повысить вожатого до
    администратора было нечем, кроме правки базы руками.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "zhidao.db"
        self.bootstrap = bootstrap_system_admin(
            self.db_path,
            username=ADMIN_USERNAME,
            password=ADMIN_PASSWORD,
            display_name="Архитектор",
        )
        with _capture() as out:
            provision_main(
                [
                    "--db", str(self.db_path),
                    "--username", "mikhail",
                    "--display-name", "Михаил Юрьевич",
                    "--role", "operator",
                    "--random-password",
                    "--actor-account-id", str(self.bootstrap["account"]["id"]),
                ]
            )
        line = [ln for ln in out.getvalue().splitlines() if ln.startswith("password: ")][-1]
        self.password = line[len("password: "):]
        self.client = TestClient(
            create_app(self.db_path, cookie_secure=False, session_hours=1)
        )

    def tearDown(self):
        self.client.close()
        self.temp_dir.cleanup()

    def login(self):
        return self.client.post(
            "/api/v4/auth/login",
            json={"username": "mikhail", "password": self.password},
        )

    def grant(self, role: str, *extra: str):
        with _capture() as out:
            code = roles_main(
                ["--db", str(self.db_path), "--username", "mikhail", "--grant", role, *extra]
            )
        self.assertEqual(code, 0)
        return json.loads(out.getvalue().splitlines()[-1])

    def test_granting_a_role_adds_it_without_losing_the_old_one(self):
        result = self.grant("system_admin")
        self.assertEqual(result["roles_before"], ["operator"])
        self.assertEqual(result["roles_after"], ["operator", "system_admin"])

        response = self.login()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            sorted(role["code"] for role in response.json()["roles"]),
            ["operator", "system_admin"],
        )

    def test_a_granted_role_takes_effect_on_an_open_session(self):
        # Роли перечитываются на каждом запросе, а не запекаются в сессию:
        # повышение не должно требовать перезахода.
        login = self.login()
        self.assertEqual(login.status_code, 200, login.text)
        csrf = login.json()["csrf_token"]

        denied = self.client.post(
            "/api/v4/seasons",
            json={"code": "before-promotion", "name": "Before"},
            headers={"x-csrf-token": csrf, "x-idempotency-key": "roles:before"},
        )
        self.assertEqual(denied.status_code, 403)

        self.grant("system_admin")

        allowed = self.client.post(
            "/api/v4/seasons",
            json={"code": "after-promotion", "name": "After"},
            headers={"x-csrf-token": csrf, "x-idempotency-key": "roles:after"},
        )
        self.assertEqual(allowed.status_code, 201, allowed.text)

    def test_revoking_keeps_the_history(self):
        self.grant("system_admin")
        with _capture() as out:
            code = roles_main(
                [
                    "--db", str(self.db_path),
                    "--username", "mikhail",
                    "--revoke", "system_admin",
                ]
            )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue().splitlines()[-1])["roles_after"], ["operator"])

        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT r.role_code, r.revoked_at
                  FROM v4_role_assignments r
                  JOIN v4_external_identities e ON e.account_id = r.account_id
                 WHERE r.role_code = 'system_admin'
                   AND e.provider_code = 'local' AND e.provider_subject = 'mikhail'
                """
            ).fetchall()
        finally:
            conn.close()
        # Строка осталась, помечена отозванной: кто и когда имел права —
        # это история, её не стирают.
        self.assertEqual(len(rows), 1)
        self.assertIsNotNone(rows[0][1])

    def test_granting_twice_is_refused_rather_than_duplicated(self):
        self.grant("system_admin")
        with self.assertRaises(SystemExit) as caught, _capture():
            roles_main(
                [
                    "--db", str(self.db_path),
                    "--username", "mikhail",
                    "--grant", "system_admin",
                ]
            )
        self.assertIn("already has", str(caught.exception))

    def test_revoking_a_role_nobody_holds_says_so(self):
        with self.assertRaises(SystemExit) as caught, _capture():
            roles_main(
                [
                    "--db", str(self.db_path),
                    "--username", "mikhail",
                    "--revoke", "architect",
                ]
            )
        self.assertIn("does not currently have", str(caught.exception))

    def test_exactly_one_of_grant_or_revoke_is_required(self):
        for extra in ([], ["--grant", "operator", "--revoke", "operator"]):
            with self.assertRaises(SystemExit) as caught, _capture():
                roles_main(
                    ["--db", str(self.db_path), "--username", "mikhail", *extra]
                )
            self.assertIn("exactly one", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
