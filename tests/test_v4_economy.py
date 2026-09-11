from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from zhidao_v4 import economy
from zhidao_v4.api import create_app
from zhidao_v4.auth import provision_local_account
from zhidao_v4.db import connect_database, immediate_transaction
from zhidao_v4.migrations import apply_migrations


PASSWORD = "a secure testing password"


class EconomyTests(unittest.TestCase):
    """Панель экономики и погашение купонов.

    Панель обязана считать то, что произошло, а не то, что хочется видеть:
    выпуск и сожжение по дням сезона в его часовом поясе, медиану, долю первых
    десяти и признак накопления. Купон гасится один раз, только вожатым и
    только если он у участника есть.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "economy.sqlite"
        apply_migrations(self.path)
        conn = connect_database(self.path)
        with immediate_transaction(conn):
            self.ids = {}
            for name, role in [("staff", "operator"), ("alice", "participant"), ("boris", "participant")]:
                self.ids[name] = provision_local_account(conn, username=name, password=PASSWORD,
                                                         display_name=name.capitalize(), role_code=role)["id"]
            conn.execute("INSERT INTO v4_seasons(id,code,name,status,timezone) VALUES (1,'hainan','Hainan','active','Asia/Shanghai')")
            for name in ("alice", "boris"):
                conn.execute("INSERT INTO v4_season_memberships(season_id,account_id,status) VALUES (1,?,'active')",
                             (self.ids[name],))
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

    def execute(self, sql, values=()):
        conn = connect_database(self.path)
        try:
            with immediate_transaction(conn):
                return conn.execute(sql, values).fetchall()
        finally:
            conn.close()

    def operation(self, who, operation, stars_delta, stars_after, created_at):
        self.execute(
            """INSERT INTO v4_economy_operations(season_id, account_id, actor_account_id, operation,
                   stars_delta, scans_delta, stars_after, scans_after, details_json, created_at)
               VALUES (1, ?, ?, ?, ?, 0, ?, 0, '{}', ?)""",
            (self.ids[who], self.ids["staff"], operation, stars_delta, stars_after, created_at),
        )

    def wallet(self, who, stars):
        self.execute("INSERT INTO v4_case_wallets(season_id, account_id, stars) VALUES (1, ?, ?) "
                     "ON CONFLICT(season_id, account_id) DO UPDATE SET stars=excluded.stars", (self.ids[who], stars))

    def overview(self, who="staff"):
        return self.clients[who].get("/api/v4/seasons/1/economy/overview")

    def redeem(self, who="alice", actor="staff", key=None):
        return self.clients[actor].post(
            "/api/v4/seasons/1/economy/coupons/redeem",
            headers={"X-CSRF-Token": self.tokens[actor], "X-Idempotency-Key": key or uuid.uuid4().hex},
            json={"account_id": self.ids[who]},
        )

    # --- панель -------------------------------------------------------------------

    def test_days_follow_the_season_time_zone_and_count_minted_and_burned(self):
        # 17:30 UTC 10 сентября — это уже 11 сентября в Шанхае.
        self.operation("alice", "diary.rate", 25, 25, "2026-09-10T17:30:00.000Z")
        self.operation("alice", "shop.buy", -20, 5, "2026-09-10T18:00:00.000Z")
        self.operation("boris", "case.open", 30, 30, "2026-09-10T03:00:00.000Z")
        body = self.overview().json()
        days = {day["date"]: day for day in body["days"]}
        self.assertEqual((days["2026-09-11"]["minted"], days["2026-09-11"]["burned"], days["2026-09-11"]["net"]), (25, 20, 5))
        self.assertEqual(days["2026-09-10"]["minted"], 30)
        self.assertEqual((body["earned"], body["spent"], body["spent_ratio"]), (55, 20, round(20 / 55, 3)))
        sources = {s["operation"]: s for s in body["sources"]}
        self.assertEqual(sources["shop.buy"]["burned"], 20)

    def test_balances_average_median_and_the_top_ten_share(self):
        self.wallet("alice", 90)
        self.wallet("boris", 10)
        body = self.overview().json()
        self.assertEqual((body["stars_total"], body["stars_average"], body["stars_median"]), (100, 50.0, 50.0))
        # Двое участников — доля первых десяти ничего не значит и не показывается.
        self.assertIsNone(body["top10_share"])

        conn = connect_database(self.path)
        with immediate_transaction(conn):
            for i in range(11):
                account = provision_local_account(conn, username=f"kid{i}", password=PASSWORD,
                                                  display_name=f"Kid {i}", role_code="participant")["id"]
                conn.execute("INSERT INTO v4_season_memberships(season_id,account_id,status) VALUES (1,?,'active')", (account,))
                conn.execute("INSERT INTO v4_case_wallets(season_id,account_id,stars) VALUES (1,?,10)", (account,))
        conn.close()
        body = self.overview().json()
        # 13 кошельков: 90, 12×10 → всего 210; первые десять — 90 + 9×10 = 180.
        self.assertEqual(body["stars_total"], 210)
        self.assertEqual(body["top10_share"], round(180 / 210, 3))

    def test_hoarding_is_flagged_after_three_days_of_little_spending(self):
        for day in ("09", "10", "11"):
            self.operation("alice", "diary.rate", 50, 50, f"2026-09-{day}T04:00:00.000Z")
        self.operation("alice", "shop.buy", -10, 40, "2026-09-11T05:00:00.000Z")
        self.assertTrue(self.overview().json()["hoarding"])
        self.operation("alice", "shop.buy", -40, 0, "2026-09-11T06:00:00.000Z")
        self.assertFalse(self.overview().json()["hoarding"])

    def test_the_panel_is_for_operators_only(self):
        self.assertEqual(self.overview("alice").status_code, 403)
        anon = TestClient(self.app)
        self.assertEqual(anon.get("/api/v4/seasons/1/economy/overview").status_code, 401)
        anon.close()

    # --- купоны ---------------------------------------------------------------------

    def give_walks(self, who="alice", quantity=2):
        self.execute("""INSERT INTO v4_case_inventory(season_id, account_id, item_code, quantity, effect_state)
                        VALUES (1, ?, 'walk', ?, 'pending')""", (self.ids[who], quantity))

    def test_a_coupon_is_redeemed_once_and_journalled(self):
        self.give_walks(quantity=2)
        self.assertEqual([c["quantity"] for c in self.overview().json()["coupons"]], [2])
        first = self.redeem(key="redeem-once-1")
        self.assertEqual(first.status_code, 200, first.text)
        again = self.redeem(key="redeem-once-1")
        self.assertEqual(again.json(), first.json())
        self.assertEqual(again.headers["x-idempotent-replayed"], "true")
        self.assertEqual(self.execute("SELECT quantity FROM v4_case_inventory WHERE item_code='walk'")[0][0], 1)
        op = self.execute("SELECT operation, stars_delta, scans_delta, rep_delta FROM v4_economy_operations")
        self.assertEqual([tuple(r) for r in op], [(economy.REDEEM_OPERATION, 0, 0, 0)])

    def test_no_coupon_nothing_to_redeem_and_participants_cannot_redeem(self):
        self.assertEqual(self.redeem().status_code, 409)
        self.give_walks()
        self.assertEqual(self.redeem(actor="alice").status_code, 403)
        self.assertEqual(self.redeem(who="boris").status_code, 409)


if __name__ == "__main__":
    unittest.main()
