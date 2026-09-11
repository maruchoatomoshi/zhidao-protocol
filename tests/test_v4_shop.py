from __future__ import annotations

import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from zhidao_v4 import shop
from zhidao_v4.api import create_app
from zhidao_v4.auth import provision_local_account
from zhidao_v4.db import connect_database, immediate_transaction
from zhidao_v4.migrations import apply_migrations


PASSWORD = "a secure testing password"
# 10:00 по Шанхаю 11 сентября — витрина дня 2026-09-11.
MORNING = datetime(2026, 9, 11, 2, 0, tzinfo=timezone.utc)


class ShopTests(unittest.TestCase):
    """Витрина дня.

    Проверяются обещания витрины: одна на весь сезон-день и переживает
    перезапуск; день начинается в 07:00 по поясу сезона; покупка списывает ★
    один раз и пишется в журнал; последняя штука достаётся одному; вчерашняя
    витрина не продаёт; косметика покупается один раз, купон копится;
    надеть можно только своё.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "shop.sqlite"
        apply_migrations(self.path)
        conn = connect_database(self.path)
        with immediate_transaction(conn):
            self.ids = {}
            for name, role in [("staff", "operator"), ("alice", "participant"), ("boris", "participant"),
                               ("stranger", "participant")]:
                self.ids[name] = provision_local_account(conn, username=name, password=PASSWORD,
                                                         display_name=name.capitalize(), role_code=role)["id"]
            conn.execute("INSERT INTO v4_seasons(id,code,name,status,timezone) VALUES (1,'hainan','Hainan','active','Asia/Shanghai')")
            for name in ("alice", "boris"):
                conn.execute("INSERT INTO v4_season_memberships(season_id,account_id,status) VALUES (1,?,'active')",
                             (self.ids[name],))
                conn.execute("INSERT INTO v4_case_wallets(season_id,account_id,stars) VALUES (1,?,500)", (self.ids[name],))
        conn.close()
        self.clock = mock.patch("zhidao_v4.shop.utcnow", return_value=MORNING)
        self.clock.start()
        self.app = create_app(self.path, cookie_secure=False)
        self.clients, self.tokens = {}, {}
        for name in self.ids:
            client = TestClient(self.app)
            response = client.post("/api/v4/auth/login", json={"username": name, "password": PASSWORD})
            self.assertEqual(response.status_code, 200, response.text)
            self.clients[name], self.tokens[name] = client, response.json()["csrf_token"]

    def tearDown(self):
        self.clock.stop()
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

    def state(self, who="alice"):
        response = self.clients[who].get("/api/v4/seasons/1/shop")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def buy(self, code, who="alice", day="2026-09-11", key=None):
        return self.clients[who].post(
            "/api/v4/seasons/1/shop/buy",
            headers={"X-CSRF-Token": self.tokens[who], "X-Idempotency-Key": key or uuid.uuid4().hex},
            json={"item_code": code, "shop_day": day},
        )

    def equip(self, slot, code, who="alice"):
        return self.clients[who].post("/api/v4/seasons/1/shop/equip",
                                      headers={"X-CSRF-Token": self.tokens[who]},
                                      json={"slot": slot, "item_code": code})

    def cosmetic_on_vitrine(self, state=None):
        return next(item for item in (state or self.state())["vitrine"] if item["kind"] == "cosmetic")

    # --- витрина -----------------------------------------------------------------

    def test_the_catalogue_follows_the_user_decisions(self):
        data = shop.catalogue()
        for item in data["items"]:
            if item["kind"] == "cosmetic":
                self.assertTrue(20 <= item["price"] <= 60, item["code"])
        self.assertEqual(shop.items_by_code()["walk"]["price"], 120)
        self.assertEqual((data["stock_min"], data["stock_max"], data["refresh_hour"]), (3, 5, 7))

    def test_one_vitrine_per_day_for_everyone_and_it_survives_a_restart(self):
        first = self.state("alice")
        self.assertEqual(first["shop_day"], "2026-09-11")
        codes = [item["code"] for item in first["vitrine"]]
        self.assertEqual(codes[0], "walk")
        self.assertEqual(len(codes), 1 + shop.catalogue()["cosmetics_per_day"])
        self.assertTrue(all(3 <= item["stock"] <= 5 for item in first["vitrine"]))
        self.assertEqual([i["code"] for i in self.state("boris")["vitrine"]], codes)
        restarted = TestClient(create_app(self.path, cookie_secure=False))
        restarted.post("/api/v4/auth/login", json={"username": "boris", "password": PASSWORD})
        self.assertEqual([i["code"] for i in restarted.get("/api/v4/seasons/1/shop").json()["vitrine"]], codes)
        restarted.close()

    def test_the_day_turns_at_seven_in_the_season_time_zone(self):
        season = {"timezone": "Asia/Shanghai"}
        # 06:59 по Шанхаю — ещё вчерашняя витрина, 07:00 — уже сегодняшняя.
        self.assertEqual(shop.shop_day(season, datetime(2026, 9, 10, 22, 59, tzinfo=timezone.utc)), "2026-09-10")
        self.assertEqual(shop.shop_day(season, datetime(2026, 9, 10, 23, 0, tzinfo=timezone.utc)), "2026-09-11")

    # --- покупка ---------------------------------------------------------------------

    def test_buying_charges_once_and_is_journalled(self):
        item = self.cosmetic_on_vitrine()
        first = self.buy(item["code"], key="shop-buy-once")
        self.assertEqual(first.status_code, 200, first.text)
        again = self.buy(item["code"], key="shop-buy-once")
        self.assertEqual(again.json(), first.json())
        self.assertEqual(again.headers["x-idempotent-replayed"], "true")
        state = self.state()
        self.assertEqual(state["stars"], 500 - item["price"])
        bought = next(i for i in state["vitrine"] if i["code"] == item["code"])
        self.assertEqual((bought["remaining"], bought["owned"]), (item["stock"] - 1, 1))
        ops = self.sql("SELECT operation, stars_delta FROM v4_economy_operations")
        self.assertEqual([tuple(r) for r in ops], [(shop.BUY_OPERATION, -item["price"])])

    def test_a_cosmetic_is_bought_once_but_coupons_stack(self):
        item = self.cosmetic_on_vitrine()
        self.assertEqual(self.buy(item["code"]).status_code, 200)
        self.assertEqual(self.buy(item["code"]).status_code, 409)
        self.assertEqual(self.buy("walk").status_code, 200)
        self.assertEqual(self.buy("walk").status_code, 200)
        self.assertEqual(self.state()["walk_coupons"], 2)

    def test_not_enough_stars_is_refused(self):
        self.sql("UPDATE v4_case_wallets SET stars=10 WHERE account_id=?", (self.ids["alice"],))
        response = self.buy("walk")
        self.assertEqual(response.status_code, 409)
        self.assertIn("120", response.json()["detail"])

    def test_the_last_one_goes_to_one_buyer(self):
        self.state()
        self.sql("UPDATE v4_shop_stock SET sold = stock - 1 WHERE item_code='walk'")
        self.assertEqual(self.buy("walk", who="alice").status_code, 200)
        sold_out = self.buy("walk", who="boris")
        self.assertEqual(sold_out.status_code, 409)
        self.assertEqual(self.state("boris")["stars"], 500)

    def test_yesterdays_vitrine_does_not_sell(self):
        self.assertEqual(self.buy("walk", day="2026-09-10").status_code, 409)

    def test_items_not_on_todays_vitrine_cannot_be_bought(self):
        on_sale = {item["code"] for item in self.state()["vitrine"]}
        absent = next(item["code"] for item in shop.catalogue()["items"] if item["code"] not in on_sale)
        self.assertEqual(self.buy(absent).status_code, 409)

    def test_outsiders_cannot_shop(self):
        self.assertEqual(self.clients["stranger"].get("/api/v4/seasons/1/shop").status_code, 403)
        self.assertEqual(self.buy("walk", who="stranger").status_code, 403)

    # --- косметика ------------------------------------------------------------------

    def test_only_owned_cosmetics_can_be_worn(self):
        item = self.cosmetic_on_vitrine()
        self.assertEqual(self.equip(item["slot"], item["code"]).status_code, 409)
        self.assertEqual(self.buy(item["code"]).status_code, 200)
        body = self.equip(item["slot"], item["code"])
        self.assertEqual(body.status_code, 200, body.text)
        self.assertEqual(body.json()["equipped"][item["slot"]], item["code"])
        wrong_slot = next(s for s in shop.SLOTS if s != item["slot"])
        self.assertEqual(self.equip(wrong_slot, item["code"]).status_code, 400)
        self.assertIsNone(self.equip(item["slot"], None).json()["equipped"][item["slot"]])

    def test_frames_are_visible_to_others(self):
        frame = "fr_gold"
        self.sql("""INSERT INTO v4_case_inventory(season_id, account_id, item_code, quantity, effect_state)
                    VALUES (1, ?, ?, 1, 'active')""", (self.ids["alice"], frame))
        self.assertEqual(self.equip("frame", frame).status_code, 200)
        conn = connect_database(self.path)
        try:
            self.assertEqual(shop.frames_for(conn, [self.ids["alice"], self.ids["boris"]]), {self.ids["alice"]: frame})
        finally:
            conn.close()
        # В рейтинге дневников — чужими глазами.
        board = self.clients["boris"].get("/api/v4/seasons/1/diary/leaderboard").json()["items"]
        self.assertEqual({row["display_name"]: row["frame"] for row in board}, {"Alice": frame, "Boris": None})
        # И за игровым столом, где сезона нет вовсе.
        headers = {"X-CSRF-Token": self.tokens["boris"]}
        code = self.clients["boris"].post("/api/v4/games/rooms", headers=headers, json={"game": "spy"}).json()["room"]["code"]
        self.clients["alice"].post("/api/v4/games/rooms/join", headers={"X-CSRF-Token": self.tokens["alice"]}, json={"code": code})
        players = self.clients["boris"].get("/api/v4/games/rooms/current").json()["players"]
        self.assertEqual({p["display_name"]: p["frame"] for p in players}, {"Alice": frame, "Boris": None})


if __name__ == "__main__":
    unittest.main()
