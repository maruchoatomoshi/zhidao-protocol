from __future__ import annotations

import hashlib
import hmac
import json
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import quote

from fastapi.testclient import TestClient

from zhidao_v4.api import CSRF_COOKIE, SESSION_COOKIE, create_app
from zhidao_v4.auth import provision_local_account
from zhidao_v4.bootstrap import bootstrap_system_admin
from zhidao_v4.db import connect_database, immediate_transaction
from zhidao_v4.max_auth import MaxAuthError, parse_user, verify_launch_params


ADMIN_USERNAME = "architect"
ADMIN_PASSWORD = "correct horse battery staple"
BOT_TOKEN = "123456:test-bot-token-not-a-real-one"


def sign_launch_params(
    bot_token: str = BOT_TOKEN,
    *,
    user_id: int = 770077,
    first_name: str = "Максим",
    last_name: str = "Тестов",
    username: str | None = "max_tester",
    auth_date: int | None = None,
    tamper_user: bool = False,
) -> str:
    """Builds a launch_params string the way MAX's own client would.

    Deliberately an independent implementation of the signing side rather
    than a call back into max_auth: a test that reuses the code under test to
    build its own input proves only that the module agrees with itself.
    """
    user: dict[str, object] = {
        "id": user_id,
        "first_name": first_name,
        "last_name": last_name,
    }
    if username:
        user["username"] = username
    fields = {
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "query_id": "AAtest-query-id",
        "user": json.dumps(user, ensure_ascii=False, separators=(",", ":")),
    }
    check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    fields["hash"] = hmac.new(
        secret, check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if tamper_user:
        # Swap the payload after signing: this is the attack the hash exists
        # to stop — claiming to be a different MAX account.
        parsed = json.loads(fields["user"])
        parsed["id"] = user_id + 1
        fields["user"] = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
    return "&".join(f"{key}={quote(value, safe='')}" for key, value in fields.items())


class MaxLaunchParamsTests(unittest.TestCase):
    def test_valid_launch_params_verify_and_parse(self):
        fields = verify_launch_params(sign_launch_params(), BOT_TOKEN)
        user = parse_user(fields)
        self.assertEqual(user.user_id, "770077")
        self.assertEqual(user.username, "max_tester")
        # Cyrillic must survive percent-decoding and JSON parsing intact —
        # every real name in this season is Cyrillic.
        self.assertEqual(user.display_name, "Максим Тестов")

    def test_wrong_bot_token_is_rejected(self):
        with self.assertRaises(MaxAuthError):
            verify_launch_params(sign_launch_params(), "some-other-token")

    def test_payload_edited_after_signing_is_rejected(self):
        with self.assertRaises(MaxAuthError):
            verify_launch_params(sign_launch_params(tamper_user=True), BOT_TOKEN)

    def test_stale_launch_params_are_rejected(self):
        stale = sign_launch_params(auth_date=int(time.time()) - 7200)
        with self.assertRaises(MaxAuthError):
            verify_launch_params(stale, BOT_TOKEN)
        # ...but the same string verifies while it is still inside the window,
        # so the rejection above is expiry and not a broken signature.
        self.assertTrue(verify_launch_params(stale, BOT_TOKEN, max_age_seconds=10800))

    def test_duplicate_field_is_rejected(self):
        doubled = sign_launch_params() + "&auth_date=1"
        with self.assertRaises(MaxAuthError):
            verify_launch_params(doubled, BOT_TOKEN)

    def test_launch_params_without_hash_are_rejected(self):
        unsigned = "&".join(
            part
            for part in sign_launch_params().split("&")
            if not part.startswith("hash=")
        )
        with self.assertRaises(MaxAuthError):
            verify_launch_params(unsigned, BOT_TOKEN)


class MaxSignInTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "zhidao.db"
        self.bootstrap = bootstrap_system_admin(
            self.db_path,
            username=ADMIN_USERNAME,
            password=ADMIN_PASSWORD,
            display_name="Architect",
        )
        conn = connect_database(self.db_path)
        try:
            with immediate_transaction(conn):
                self.participant = provision_local_account(
                    conn,
                    username="kid1",
                    password="participant secure passphrase",
                    display_name="Тестовый Участник",
                    role_code="participant",
                    actor_account_id=self.bootstrap["account"]["id"],
                )
        finally:
            conn.close()
        app = create_app(self.db_path, cookie_secure=False, session_hours=1)
        app.state.max_bot_token = BOT_TOKEN
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.temp_dir.cleanup()

    def account_id(self) -> int:
        return int(self.participant["id"])

    def issue_code(self) -> str:
        response = self.client.post(
            "/api/v4/auth/login",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        )
        self.assertEqual(response.status_code, 200, response.text)
        csrf = response.json()["csrf_token"]
        issued = self.client.post(
            f"/api/v4/admin/accounts/{self.account_id()}/link-codes",
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(issued.status_code, 200, issued.text)
        self.client.post("/api/v4/auth/logout", headers={"X-CSRF-Token": csrf})
        self.client.cookies.clear()
        return issued.json()["code"]

    def sign_in(self, launch_params: str, link_code: str | None = None):
        body: dict[str, str] = {"launch_params": launch_params}
        if link_code is not None:
            body["link_code"] = link_code
        return self.client.post("/api/v4/auth/max", json=body)

    def test_unlinked_max_account_is_asked_for_a_pairing_code(self):
        response = self.sign_in(sign_launch_params())
        self.assertEqual(response.status_code, 409, response.text)
        # A 409 must not hand out a session: identity is proven, membership
        # of the roster is not.
        self.assertNotIn(SESSION_COOKIE, self.client.cookies)

    def test_forged_launch_params_are_rejected_before_any_lookup(self):
        response = self.sign_in(sign_launch_params(bot_token="attacker-token"))
        self.assertEqual(response.status_code, 401, response.text)

    def test_pairing_code_links_the_account_and_cannot_be_reused(self):
        code = self.issue_code()
        linked = self.sign_in(sign_launch_params(), code)
        self.assertEqual(linked.status_code, 200, linked.text)
        self.assertEqual(linked.json()["account"]["display_name"], "Тестовый Участник")
        self.assertIn(SESSION_COOKIE, self.client.cookies)
        self.assertIn(CSRF_COOKIE, self.client.cookies)

        # Once linked, the same MAX account signs in with no code at all.
        self.client.cookies.clear()
        again = self.sign_in(sign_launch_params())
        self.assertEqual(again.status_code, 200, again.text)

        # A different MAX account must not be able to reuse the spent code to
        # attach itself to the same participant.
        self.client.cookies.clear()
        stolen = self.sign_in(sign_launch_params(user_id=880088, username="thief"), code)
        self.assertEqual(stolen.status_code, 409, stolen.text)

    def test_a_replacement_code_can_be_issued_and_retires_the_old_one(self):
        # Codes live 30 minutes and children lose them, so re-issuing is the
        # ordinary case, not an edge one: before migration 0005 the unique
        # index over unconsumed rows made the second issue fail outright.
        first = self.issue_code()
        second = self.issue_code()
        self.assertNotEqual(first, second)

        rejected = self.sign_in(sign_launch_params(), first)
        self.assertEqual(rejected.status_code, 409, rejected.text)

        accepted = self.sign_in(sign_launch_params(), second)
        self.assertEqual(accepted.status_code, 200, accepted.text)

    def test_a_code_dictated_in_groups_of_four_still_works(self):
        # Экран выдачи показывает код как «1543 6364», чтобы его можно было
        # продиктовать. Значит, набранный с пробелом он обязан подойти:
        # иначе человек получает «код неверный» за чужой формат показа.
        code = self.issue_code()
        spaced = f"{code[:4]} {code[4:]}"
        response = self.sign_in(sign_launch_params(), spaced)
        self.assertEqual(response.status_code, 200, response.text)

    def test_an_account_already_linked_names_the_real_reason(self):
        # Схема разрешает аккаунту одну привязку MAX. Вторая попытка раньше
        # падала в IntegrityError и выходила наружу как 500 с сообщением
        # «не удалось проверить данные MAX» — обвинялся мессенджер.
        self.assertEqual(self.sign_in(sign_launch_params(), self.issue_code()).status_code, 200)
        self.client.cookies.clear()

        second = self.sign_in(sign_launch_params(user_id=880088, username="other"), self.issue_code())
        self.assertEqual(second.status_code, 409, second.text)
        self.assertEqual(second.json()["detail"]["reason"], "account_already_linked")
        self.assertNotIn(SESSION_COOKIE, self.client.cookies)

    def test_sign_in_is_unavailable_when_no_bot_token_is_configured(self):
        app = create_app(self.db_path, cookie_secure=False, session_hours=1)
        app.state.max_bot_token = None
        with TestClient(app) as client:
            response = client.post(
                "/api/v4/auth/max", json={"launch_params": sign_launch_params()}
            )
            self.assertEqual(response.status_code, 503, response.text)


if __name__ == "__main__":
    unittest.main()
