from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from zhidao_v4.api import create_app
from zhidao_v4.auth import provision_local_account
from zhidao_v4.bootstrap import bootstrap_system_admin
from zhidao_v4.db import connect_database, immediate_transaction


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "zhidao_v4" / "static" / "app"
INDEX = APP_DIR / "index.html"

ADMIN_PASSWORD = "correct horse battery staple"
USER_PASSWORD = "another correct horse battery"


class AdminConsoleAccessTests(unittest.TestCase):
    """Служебные эндпоинты, на которые ходит экран «Админка».

    Плитка админки спрятана от участника, но проверяется здесь не это.
    Спрятанная кнопка — удобство; доступ решает сервер, и если он однажды
    перестанет решать, участник дойдёт до ростера и кодов сопряжения простым
    запросом. Поэтому тест ходит мимо интерфейса и требует отказа.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "zhidao.db"
        self.bootstrap = bootstrap_system_admin(
            self.db_path,
            username="architect",
            password=ADMIN_PASSWORD,
            display_name="Архитектор",
        )
        conn = connect_database(self.db_path)
        try:
            with immediate_transaction(conn):
                self.participant = provision_local_account(
                    conn,
                    username="kseniya",
                    password=USER_PASSWORD,
                    display_name="Ксения Литвинова",
                    role_code="participant",
                    actor_account_id=self.bootstrap["account"]["id"],
                )
                self.operator = provision_local_account(
                    conn,
                    username="mikhail",
                    password=USER_PASSWORD,
                    display_name="Михаил Юрьевич",
                    role_code="operator",
                    actor_account_id=self.bootstrap["account"]["id"],
                )
        finally:
            conn.close()
        self.client = TestClient(
            create_app(self.db_path, cookie_secure=False, session_hours=1)
        )

    def tearDown(self):
        self.client.close()
        self.temp_dir.cleanup()

    def login(self, username: str, password: str) -> str:
        response = self.client.post(
            "/api/v4/auth/login", json={"username": username, "password": password}
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["csrf_token"]

    def test_a_participant_is_refused_every_service_endpoint(self):
        csrf = self.login("kseniya", USER_PASSWORD)
        target = self.operator["id"]

        self.assertEqual(self.client.get("/api/v4/admin/overview").status_code, 403)
        self.assertEqual(self.client.get("/api/v4/admin/accounts").status_code, 403)
        self.assertEqual(
            self.client.post(
                f"/api/v4/admin/accounts/{target}/link-codes",
                headers={"X-CSRF-Token": csrf},
            ).status_code,
            403,
        )

    def test_an_operator_reaches_the_roster_but_not_the_overview(self):
        # Ровно та разница, которую экран объясняет словами: коды выдаёт
        # вожатый, сводку смотрит архитектор. Если разница исчезнет, надпись
        # на экране станет неправдой.
        csrf = self.login("mikhail", USER_PASSWORD)

        roster = self.client.get("/api/v4/admin/accounts")
        self.assertEqual(roster.status_code, 200, roster.text)
        self.assertTrue(roster.json()["items"])

        self.assertEqual(self.client.get("/api/v4/admin/overview").status_code, 403)

        issued = self.client.post(
            f"/api/v4/admin/accounts/{self.participant['id']}/link-codes",
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(issued.status_code, 200, issued.text)
        self.assertRegex(issued.json()["code"], r"^\d{8}$")

    def test_the_roster_never_hands_out_hashes_or_messenger_ids(self):
        self.login("architect", ADMIN_PASSWORD)
        payload = self.client.get("/api/v4/admin/accounts").json()
        for item in payload["items"]:
            self.assertEqual(
                set(item),
                {"id", "public_id", "display_name", "status", "login", "max_linked"},
            )

    def test_the_overview_answers_the_architect(self):
        self.login("architect", ADMIN_PASSWORD)
        overview = self.client.get("/api/v4/admin/overview")
        self.assertEqual(overview.status_code, 200, overview.text)
        body = overview.json()
        self.assertIn("accounts", body["counts"])
        self.assertGreaterEqual(body["schema_version"], 6)


class AdminConsoleMarkupTests(unittest.TestCase):
    """Разметка служебного экрана.

    Проверяются два свойства, которые ломаются молча: плитка не должна
    приезжать на сервер видимой (её показывает роль, а не разметка), и у
    каждой вкладки должна быть своя панель — иначе нажатие просто прячет
    всё, и раздел выглядит пустым.
    """

    @classmethod
    def setUpClass(cls):
        cls.markup = INDEX.read_text(encoding="utf-8")

    def test_the_hub_tile_ships_hidden(self):
        tile = re.search(r"<button[^>]*id=\"adminHubTile\"[^>]*>", self.markup)
        self.assertIsNotNone(tile, "плитка админки исчезла из «Ещё»")
        self.assertIn("hidden", tile.group(0))
        self.assertIn('data-open-screen="admin"', tile.group(0))

    def test_every_tab_has_a_panel(self):
        self.assertIn('data-tab-group="admin"', self.markup)
        section = self.markup.split('data-screen="admin"', 1)[1].split("</section>", 1)[0]
        names = set(re.findall(r'data-tab="([a-z]+)"', section))
        panels = set(re.findall(r'data-tab-panel="admin:([a-z]+)"', section))
        self.assertEqual(names, panels)

    def test_the_admin_script_is_loaded_and_versioned(self):
        self.assertRegex(self.markup, r'src="\./admin\.js\?v=[0-9a-f]{10}"')
