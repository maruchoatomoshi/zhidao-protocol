from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from zhidao_v4 import cases, workshop
from zhidao_v4.api import create_app
from zhidao_v4.auth import provision_local_account
from zhidao_v4.db import connect_database, immediate_transaction
from zhidao_v4.migrations import apply_migrations


PASSWORD = "a secure testing password"

IMPLANTS_PATH = Path(__file__).resolve().parents[1] / "zhidao_v4/static/app/assets/implants/implants.json"


class WorkshopCatalogueTests(unittest.TestCase):
    """Every crafted item needs a real, illustrated entry — not a silent gap.

    workshop.json is the server's source of truth for names; implants.json is
    the frontend's illustrated reference catalogue. They must agree, and the
    art file each entry points to must actually exist on disk, or the
    Коллекция screen shows a broken image instead of an honest placeholder.
    """

    def test_every_workshop_item_has_an_illustrated_catalogue_entry_with_real_art(self):
        catalogue = {item["code"]: item for item in json.loads(IMPLANTS_PATH.read_text(encoding="utf-8"))["implants"]}
        for code, item in workshop.items_by_code().items():
            self.assertIn(code, catalogue, f"{code} is craftable but missing from implants.json")
            entry = catalogue[code]
            self.assertEqual(entry["name_ru"], item["name_ru"], code)
            art_path = IMPLANTS_PATH.parent / entry["art"]
            self.assertTrue(art_path.is_file(), f"{code}: art file {entry['art']} does not exist")


class WorkshopTests(unittest.TestCase):
    """Мастерская дубликатов (V4_GAMES.md §4.8), решения пользователя 2026-09-17.

    Обещания: четыре одинаковых редких импланта превращаются в один новый,
    полностью, без сбора звёзд; исход детерминирован — один базовый предмет
    даёт ровно один целевой, не случайный выбор; повтор запроса с тем же
    ключом не переплавляет дважды; предметы без рецепта отказываются; при
    нехватке ничего не меняется; новые импланты видны в коллекции;
    переплавлять может только участник сезона.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "workshop.sqlite"
        apply_migrations(self.path)
        conn = connect_database(self.path)
        with immediate_transaction(conn):
            self.ids = {}
            for name in ("alice", "boris"):
                self.ids[name] = provision_local_account(conn, username=name, password=PASSWORD,
                                                         display_name=name.capitalize(), role_code="participant")["id"]
            conn.execute("INSERT INTO v4_seasons(id,code,name,status,timezone) VALUES (1,'hainan','Hainan','active','Asia/Shanghai')")
            conn.execute("INSERT INTO v4_season_memberships(season_id,account_id,status) VALUES (1,?,'active')",
                         (self.ids["alice"],))
            conn.execute("INSERT INTO v4_case_wallets(season_id,account_id,stars) VALUES (1,?,100)", (self.ids["alice"],))
        conn.close()
        self.app = create_app(self.path, cookie_secure=False)
        self.clients, self.tokens = {}, {}
        for name in self.ids:
            client = TestClient(self.app)
            response = client.post("/api/v4/auth/login", json={"username": name, "password": PASSWORD})
            self.assertEqual(response.status_code, 200, response.text)
            self.clients[name], self.tokens[name] = client, response.json()["csrf_token"]

    def tearDown(self):
        for client in self.clients.values():
            client.close()
        self.temp.cleanup()

    def sql(self, query, values=()):
        conn = connect_database(self.path)
        try:
            with immediate_transaction(conn):
                return conn.execute(query, values).fetchall()
        finally:
            conn.close()

    def give(self, code, count):
        self.sql("""INSERT INTO v4_case_inventory(season_id, account_id, item_code, quantity, effect_state)
                    VALUES (1, ?, ?, ?, 'pending')
                    ON CONFLICT(season_id, account_id, item_code) DO UPDATE SET quantity = quantity + excluded.quantity""",
                 (self.ids["alice"], code, count))

    def owned(self, code):
        rows = self.sql("SELECT quantity FROM v4_case_inventory WHERE season_id=1 AND account_id=? AND item_code=?",
                        (self.ids["alice"], code))
        return rows[0]["quantity"] if rows else 0

    def stars(self):
        return self.sql("SELECT stars FROM v4_case_wallets WHERE season_id=1 AND account_id=?", (self.ids["alice"],))[0]["stars"]

    def craft(self, code, who="alice", key=None):
        return self.clients[who].post(
            "/api/v4/seasons/1/workshop/craft",
            headers={"X-CSRF-Token": self.tokens[who], "X-Idempotency-Key": key or uuid.uuid4().hex},
            json={"item_code": code},
        )

    def test_four_duplicates_become_one_new_deterministic_item(self):
        self.give("implant_qilin", 4)
        response = self.craft("implant_qilin")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["got"]["code"], "implant_zhuque")
        self.assertEqual(body["got"]["name_ru"], "Чжуцюэ")
        self.assertEqual(self.owned("implant_qilin"), 0)
        self.assertEqual(self.owned("implant_zhuque"), 1)
        self.assertEqual(self.stars(), 100, "no star fee in the new recipe")
        rows = self.sql("SELECT stars_delta, details_json FROM v4_economy_operations WHERE operation='workshop.craft'")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["stars_delta"], 0)
        self.assertEqual(json.loads(rows[0]["details_json"])["got"], "implant_zhuque")

    def test_every_base_implant_has_its_own_fixed_target(self):
        expected = {
            "implant_qilin": "implant_zhuque", "implant_caishen": "implant_jinchan",
            "implant_guanxi": "implant_mianzi", "implant_panda": "implant_koi",
            "implant_shaolin": "implant_taiji", "implant_linguasoft": "implant_biancai",
        }
        for base, target in expected.items():
            self.give(base, 4)
            body = self.craft(base).json()
            self.assertEqual(body["got"]["code"], target, base)

    def test_exactly_four_are_needed_none_are_kept(self):
        self.give("implant_panda", 3)
        response = self.craft("implant_panda")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.owned("implant_panda"), 3)

    def test_retry_with_the_same_key_does_not_craft_twice(self):
        self.give("implant_shaolin", 8)
        key = uuid.uuid4().hex
        first = self.craft("implant_shaolin", key=key)
        second = self.craft("implant_shaolin", key=key)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.headers["X-Idempotent-Replayed"], "true")
        self.assertEqual(second.json(), first.json())
        self.assertEqual(self.owned("implant_shaolin"), 4)
        self.assertEqual(self.owned("implant_taiji"), 1)
        self.assertEqual(len(self.sql("SELECT 1 FROM v4_economy_operations WHERE operation='workshop.craft'")), 1)

    def test_items_without_a_recipe_are_refused(self):
        for code in ("walk", "fate_guard", "implant_red_dragon", "implant_terracota", "nothing_like_this"):
            self.give(code, 5)
            self.assertEqual(self.craft(code).status_code, 400, code)
        self.assertEqual(self.stars(), 100)

    def test_state_shows_progress_and_new_items_reach_the_collection(self):
        self.give("implant_caishen", 2)
        self.give("implant_jinchan", 1)
        state = self.clients["alice"].get("/api/v4/seasons/1/workshop").json()
        self.assertEqual(state["input"], 4)
        recipes = {recipe["code"]: recipe for recipe in state["recipes"]}
        self.assertFalse(recipes["implant_caishen"]["ready"])
        self.assertEqual(recipes["implant_caishen"]["missing"], 2)
        self.assertEqual(recipes["implant_caishen"]["to_code"], "implant_jinchan")
        self.assertEqual(recipes["implant_caishen"]["to_name_ru"], "Цзинь Чань")
        # implant_jinchan itself has no recipe (it's a target, not a source).
        self.assertNotIn("implant_jinchan", recipes)
        collection = self.clients["alice"].get("/api/v4/seasons/1/cases/state")
        self.assertEqual(collection.status_code, 200, collection.text)
        names = {item["item_code"]: item["name_ru"] for item in collection.json()["inventory"]}
        self.assertEqual(names["implant_jinchan"], "Цзинь Чань")

    def test_only_active_members_can_use_the_workshop(self):
        self.assertEqual(self.clients["boris"].get("/api/v4/seasons/1/workshop").status_code, 403)
        self.assertEqual(self.craft("implant_qilin", who="boris").status_code, 403)


if __name__ == "__main__":
    unittest.main()
