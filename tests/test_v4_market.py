from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from zhidao_v4 import market
from zhidao_v4.api import create_app
from zhidao_v4.auth import provision_local_account
from zhidao_v4.bootstrap import bootstrap_system_admin
from zhidao_v4.db import connect_database, immediate_transaction


ADMIN_PASSWORD = "correct horse battery staple"
USER_PASSWORD = "another correct horse battery"
MORNING = datetime(2026, 9, 12, 2, 0, tzinfo=timezone.utc)   # 10:00 по Шанхаю, рынок открыт
KIDS = [f"kid{n}" for n in range(1, 9)]
RULES = market.config()


class MarketTests(unittest.TestCase):
    """Рынок Контрабанды, этап 2 (V4_GAMES.md §4.12).

    Обещания (решения пользователя 2026-09-13): основа — обмен между игроками по
    коду; юани и товары живут один сезон-день и сгорают; ловят дети-патрульные
    по жребию дня; топ-3 дня получают 10/6/3★ — только те, кто торговал или
    проверял. Черновик Claude: утренний набор 20 元 и 6 товаров; сумку видит
    только владелец; патрульный вскрывает сумку по её коду: запрещёнку
    конфискуют со штрафом, чистая сумка стоит патрульному штрафа; одного
    торговца — не чаще раза в час, патрульный — раз в пять минут; кто с кем
    торговал, не хранится.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "zhidao.db"
        bootstrap = bootstrap_system_admin(self.db_path, username="architect", password=ADMIN_PASSWORD,
                                           display_name="Архитектор")
        self.ids: dict[str, int] = {}
        conn = connect_database(self.db_path)
        try:
            with immediate_transaction(conn):
                for name in KIDS:
                    self.ids[name] = int(provision_local_account(
                        conn, username=name, password=USER_PASSWORD, display_name=name, role_code="participant",
                        actor_account_id=bootstrap["account"]["id"])["id"])
                    conn.execute("INSERT INTO v4_season_memberships(season_id, account_id, status) VALUES (1, ?, 'active')",
                                 (self.ids[name],))
                conn.execute("UPDATE v4_seasons SET status='active' WHERE id=1")
        finally:
            conn.close()
        self.now = MORNING
        self.clock = mock.patch("zhidao_v4.market.utcnow", side_effect=lambda: self.now)
        self.clock.start()
        market.offers = market.Offers()
        self.app = create_app(self.db_path, cookie_secure=False, session_hours=1)
        self.clients, self.tokens = {}, {}
        for name in KIDS:
            client = TestClient(self.app)
            response = client.post("/api/v4/auth/login", json={"username": name, "password": USER_PASSWORD})
            self.assertEqual(response.status_code, 200, response.text)
            self.clients[name], self.tokens[name] = client, response.json()["csrf_token"]

    def tearDown(self):
        self.clock.stop()
        for client in self.clients.values():
            client.close()
        self.temp_dir.cleanup()

    # --- помощники ---------------------------------------------------------------------

    def sql(self, query, values=()):
        conn = connect_database(self.db_path)
        try:
            with immediate_transaction(conn):
                return conn.execute(query, values).fetchall()
        finally:
            conn.close()

    def post(self, who, path, body=None):
        return self.clients[who].post(f"/api/v4/market{path}", headers={"X-CSRF-Token": self.tokens[who]}, json=body or {})

    def ok(self, response):
        self.assertLess(response.status_code, 300, response.text)
        return response.json()

    def view(self, who):
        return self.ok(self.clients[who].get("/api/v4/market"))

    def me(self, who):
        return self.view(who)["me"]

    def open_market(self, players=KIDS):
        for who in players:
            self.ok(self.post(who, "/join"))
        self.sql("UPDATE v4_market_players SET role='merchant'")

    def stock(self, who, goods, money=20, role="merchant"):
        self.sql("UPDATE v4_market_players SET goods_json=?, money=?, role=? WHERE account_id=?",
                 (json.dumps(goods), money, role, self.ids[who]))

    def offer(self, who, give, want):
        return self.post(who, "/offer", {"give": give, "want": want})

    def stars(self, who):
        rows = self.sql("SELECT stars FROM v4_case_wallets WHERE season_id=1 AND account_id=?", (self.ids[who],))
        return int(rows[0]["stars"]) if rows else 0

    # --- набор и приватность ------------------------------------------------------------------

    def test_joining_gives_a_morning_kit_and_the_bag_stays_private(self):
        me = self.ok(self.post("kid1", "/join"))["me"]
        self.assertEqual(me["money"], RULES["start_money"])
        self.assertEqual(sum(me["goods"].values()), RULES["kit"])
        self.assertEqual(len(me["code"]), 6)
        self.ok(self.post("kid2", "/join"))
        seen = json.dumps(self.view("kid2"), ensure_ascii=False)
        self.assertNotIn(me["code"], seen)
        self.assertNotIn('"traded": true', seen)
        again = self.ok(self.post("kid1", "/join"))["me"]
        self.assertEqual(again["goods"], me["goods"])

    # --- обмен ----------------------------------------------------------------------------------

    def test_a_trade_swaps_goods_and_money_by_code(self):
        self.open_market(KIDS[:4])
        self.stock("kid1", {"mango": 2})
        self.stock("kid2", {"tea": 1})
        self.stock("kid3", {})                                                                  # случайный набор мог дать чай
        self.assertEqual(self.offer("kid1", {"goods": {"tea": 1}}, {}).status_code, 409)       # чая у kid1 нет
        self.assertEqual(self.offer("kid1", {}, {}).status_code, 400)
        code = self.ok(self.offer("kid1", {"goods": {"mango": 1}, "money": 5}, {"goods": {"tea": 1}}))["offer"]["code"]
        peek = self.ok(self.clients["kid2"].get(f"/api/v4/market/offers/{code}"))
        self.assertEqual((peek["from"], peek["give"], peek["want"]),
                         ("kid1", {"goods": {"mango": 1}, "money": 5}, {"goods": {"tea": 1}, "money": 0}))
        self.assertEqual(self.post("kid3", "/accept", {"code": code}).status_code, 409)      # у kid3 нет чая
        result = self.ok(self.post("kid2", "/accept", {"code": code}))
        self.assertEqual((result["me"]["goods"], result["me"]["money"]), ({"mango": 1}, 25))
        first = self.me("kid1")
        self.assertEqual((first["goods"], first["money"], first["traded"]), ({"mango": 1, "tea": 1}, 15, True))
        self.assertEqual(first["news"]["kind"], "trade")
        self.assertIsNone(self.view("kid1")["offer"])
        self.assertEqual(self.post("kid2", "/accept", {"code": code}).status_code, 404)

    def test_an_offer_expires_and_a_seller_who_sold_out_cannot_be_accepted(self):
        self.open_market(KIDS[:4])
        self.stock("kid1", {"mango": 1})
        self.stock("kid2", {})
        code = self.ok(self.offer("kid1", {"goods": {"mango": 1}}, {"money": 2}))["offer"]["code"]
        self.stock("kid1", {})
        self.assertEqual(self.post("kid2", "/accept", {"code": code}).status_code, 409)
        self.stock("kid1", {"mango": 1})
        code = self.ok(self.offer("kid1", {"goods": {"mango": 1}}, {"money": 2}))["offer"]["code"]
        self.now += timedelta(seconds=RULES["offer_seconds"] + 1)
        self.assertEqual(self.post("kid2", "/accept", {"code": code}).status_code, 404)

    # --- патруль --------------------------------------------------------------------------------

    def test_patrols_are_drawn_when_the_market_opens(self):
        self.now = MORNING - timedelta(hours=2)   # 08:00, рынок ещё закрыт
        for who in KIDS:
            self.ok(self.post(who, "/join"))
        self.assertEqual(self.view("kid1")["patrols"], 0)
        self.assertEqual(self.offer("kid1", {"money": 1}, {}).status_code, 409)
        self.now = MORNING
        self.assertEqual(self.view("kid1")["patrols"], len(KIDS) // RULES["patrol_per"])
        patrol = [r for r in self.sql("SELECT role FROM v4_market_players") if r["role"] == "patrol"]
        self.assertEqual(len(patrol), 1)

    def test_a_patrol_confiscates_contraband_and_pays_for_a_clean_bag(self):
        self.open_market(KIDS[:4])
        self.stock("kid1", {}, money=20, role="patrol")
        self.stock("kid2", {"disc": 1, "mango": 1}, money=20)
        self.stock("kid3", {"mango": 2}, money=20)
        bag2 = self.me("kid2")["code"]
        bag3 = self.me("kid3")["code"]
        self.assertEqual(self.post("kid3", "/inspect", {"code": bag2}).status_code, 409)       # не патрульный
        caught = self.ok(self.post("kid1", "/inspect", {"code": bag2}))["inspection"]
        disc_fine = next(g["penalty"] for g in self.view("kid1")["catalog"] if g["code"] == "disc")
        self.assertEqual((caught["caught"], caught["fine"]), ({"disc": 1}, disc_fine))
        self.assertEqual(self.me("kid2")["goods"], {"mango": 1})
        self.assertEqual(self.me("kid2")["money"], 20 - disc_fine)
        self.assertEqual(self.me("kid2")["news"]["kind"], "inspected")
        self.assertEqual(self.post("kid1", "/inspect", {"code": bag3}).status_code, 429)
        self.now += timedelta(seconds=RULES["patrol_rest_seconds"] + 1)
        clean = self.ok(self.post("kid1", "/inspect", {"code": bag3}))["inspection"]
        self.assertEqual((clean["clean"], clean["fine"]), (True, RULES["clean_fine"]))
        self.assertEqual(self.me("kid1")["money"], 20 + disc_fine - RULES["clean_fine"])
        self.assertEqual(self.me("kid3")["money"], 20 + RULES["clean_fine"])
        self.now += timedelta(seconds=RULES["patrol_rest_seconds"] + 1)
        self.assertEqual(self.post("kid1", "/inspect", {"code": bag2}).status_code, 409)       # недавно проверяли
        self.assertNotIn("code", self.me("kid1"))

    # --- итоги дня ---------------------------------------------------------------------------------

    def test_the_day_ends_with_prizes_for_the_top_three_traders_and_burns_the_market(self):
        self.open_market(KIDS[:5])
        for who, money in (("kid1", 50), ("kid2", 40), ("kid3", 30), ("kid4", 20)):
            self.stock(who, {}, money=money)
        self.stock("kid5", {}, money=999)                                                   # не торговал
        self.sql("UPDATE v4_market_players SET traded=1 WHERE account_id IN (?,?,?,?)",
                 tuple(self.ids[k] for k in KIDS[:4]))
        self.now = datetime(2026, 9, 12, 13, 0, tzinfo=timezone.utc)                        # 21:00
        results = self.view("kid1")["results"]
        self.assertEqual([(r["name"], r["prize"]) for r in results["results"]],
                         [("kid1", 10), ("kid2", 6), ("kid3", 3), ("kid4", 0)])
        self.assertEqual([self.stars(k) for k in ("kid1", "kid2", "kid3", "kid4", "kid5")], [10, 6, 3, 0, 0])
        self.assertEqual(self.sql("SELECT 1 FROM v4_market_players"), [])
        self.assertEqual(self.post("kid1", "/join").status_code, 409)                        # вечером рынок закрыт
        self.view("kid2")
        self.assertEqual(len(self.sql("SELECT 1 FROM v4_economy_operations WHERE operation='market.prize'")), 3)
        self.now = MORNING + timedelta(days=1)
        fresh = self.ok(self.post("kid1", "/join"))["me"]
        self.assertEqual(fresh["money"], RULES["start_money"])

    def test_a_small_market_pays_no_prizes(self):
        self.open_market(KIDS[:2])
        self.sql("UPDATE v4_market_players SET traded=1")
        self.now = MORNING + timedelta(days=1)
        results = self.view("kid1")["results"]
        self.assertFalse(results["prizes"])
        self.assertEqual(self.sql("SELECT 1 FROM v4_economy_operations WHERE operation='market.prize'"), [])


if __name__ == "__main__":
    unittest.main()
