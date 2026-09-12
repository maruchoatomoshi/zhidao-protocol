from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from zhidao_v4 import workshop
from zhidao_v4.api import create_app
from zhidao_v4.auth import provision_local_account
from zhidao_v4.db import connect_database, immediate_transaction
from zhidao_v4.migrations import apply_migrations


PASSWORD = "a secure testing password"


class WorkshopTests(unittest.TestCase):
    """Мастерская дубликатов (V4_GAMES.md §4.8).

    Обещания: три одинаковых превращаются в один предмет ступенью выше, а
    четвёртый остаётся у владельца; сбор 10★ / 25★ сжигается и пишется в
    журнал; повтор запроса с тем же ключом не переплавляет дважды; купон и
    легендарные не принимаются; при нехватке ничего не меняется; улучшенные
    импланты видны в коллекции; переплавлять может только участник сезона.
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

    def first_outcome(self):
        return mock.patch.object(workshop._rng, "choice", side_effect=lambda items: items[0])

    def test_three_duplicates_become_one_item_of_the_next_tier(self):
        self.give("fate_guard", 4)
        with self.first_outcome():
            response = self.craft("fate_guard")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["got"]["tier"], "purple")
        self.assertEqual(self.owned("fate_guard"), 1)
        self.assertEqual(self.owned(body["got"]["code"]), 1)
        self.assertEqual(self.stars(), 90)
        rows = self.sql("SELECT stars_delta, details_json FROM v4_economy_operations WHERE operation='workshop.craft'")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["stars_delta"], -10)
        self.assertEqual(json.loads(rows[0]["details_json"])["got"], body["got"]["code"])

    def test_each_step_above_costs_twenty_five_and_reaches_legendary(self):
        self.give("implant_qilin", 4)
        with self.first_outcome():
            upgraded = self.craft("implant_qilin").json()["got"]
        self.assertEqual(upgraded["tier"], "upgraded")
        self.assertEqual(self.stars(), 75)
        self.give(upgraded["code"], 3)
        with self.first_outcome():
            legendary = self.craft(upgraded["code"])
        self.assertEqual(legendary.status_code, 200, legendary.text)
        self.assertEqual(legendary.json()["got"]["tier"], "black")
        self.assertEqual(self.owned(upgraded["code"]), 1)
        self.assertEqual(self.stars(), 50)

    def test_outcome_is_chosen_among_the_whole_next_tier(self):
        self.give("implant_panda", 4)
        with mock.patch.object(workshop._rng, "choice", side_effect=lambda items: items[-1]) as choice:
            self.assertEqual(self.craft("implant_panda").status_code, 200)
        offered = {item["code"] for item in choice.call_args.args[0]}
        self.assertEqual(offered, {"implant_jade_warden", "implant_diplomat", "implant_golden_nexus"})

    def test_one_copy_always_stays_with_the_owner(self):
        self.give("implant_panda", 3)
        response = self.craft("implant_panda")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.owned("implant_panda"), 3)
        self.assertEqual(self.stars(), 100)

    def test_retry_with_the_same_key_does_not_craft_twice(self):
        self.give("fate_guard", 7)
        key = uuid.uuid4().hex
        first = self.craft("fate_guard", key=key)
        second = self.craft("fate_guard", key=key)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.headers["X-Idempotent-Replayed"], "true")
        self.assertEqual(second.json(), first.json())
        self.assertEqual(self.owned("fate_guard"), 4)
        self.assertEqual(self.stars(), 90)
        self.assertEqual(len(self.sql("SELECT 1 FROM v4_economy_operations WHERE operation='workshop.craft'")), 1)

    def test_coupon_legendary_and_unknown_items_are_refused(self):
        for code in ("walk", "implant_red_dragon", "nothing_like_this"):
            self.give(code, 5)
            self.assertEqual(self.craft(code).status_code, 400, code)
        self.assertEqual(self.stars(), 100)

    def test_not_enough_stars_changes_nothing(self):
        self.sql("UPDATE v4_case_wallets SET stars=5 WHERE season_id=1 AND account_id=?", (self.ids["alice"],))
        self.give("fate_guard", 4)
        self.assertEqual(self.craft("fate_guard").status_code, 409)
        self.assertEqual(self.owned("fate_guard"), 4)
        self.assertEqual(self.stars(), 5)

    def test_state_shows_progress_and_upgraded_items_reach_the_collection(self):
        self.give("fate_guard", 2)
        self.give("implant_jade_warden", 1)
        state = self.clients["alice"].get("/api/v4/seasons/1/workshop").json()
        recipes = {recipe["code"]: recipe for recipe in state["recipes"]}
        self.assertFalse(recipes["fate_guard"]["ready"])
        self.assertEqual(recipes["fate_guard"]["missing"], 2)
        self.assertEqual(recipes["implant_jade_warden"]["fee"], 25)
        self.assertEqual(set(recipes["implant_jade_warden"]["outcomes"]), {"Красный Дракон 红龙", "Терракота 兵马俑"})
        collection = self.clients["alice"].get("/api/v4/seasons/1/cases/state")
        self.assertEqual(collection.status_code, 200, collection.text)
        names = {item["item_code"]: item["name_ru"] for item in collection.json()["inventory"]}
        self.assertEqual(names["implant_jade_warden"], "Нефритовый страж")

    def test_only_active_members_can_use_the_workshop(self):
        self.assertEqual(self.clients["boris"].get("/api/v4/seasons/1/workshop").status_code, 403)
        self.assertEqual(self.craft("fate_guard", who="boris").status_code, 403)


if __name__ == "__main__":
    unittest.main()
