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
            for name, role in [("staff", "operator"), ("architect", "architect"), ("admin", "system_admin"),
                               ("alice", "participant"), ("boris", "participant")]:
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

    def grant(self, who="alice", actor="staff", key=None, stars_delta=0, rep_delta=0, reason="за смелость"):
        return self.clients[actor].post(
            "/api/v4/seasons/1/economy/grant",
            headers={"X-CSRF-Token": self.tokens[actor], "X-Idempotency-Key": key or uuid.uuid4().hex},
            json={"account_id": self.ids[who], "stars_delta": stars_delta, "rep_delta": rep_delta, "reason": reason},
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

    # --- ручное начисление ★ и REP (решение 2026-09-17, перенесено из Пекина) ------

    def test_operator_architect_and_admin_grant_on_equal_terms(self):
        for actor in ("staff", "architect", "admin"):
            response = self.grant(actor=actor, stars_delta=5, key=f"equal-{actor}")
            self.assertEqual(response.status_code, 200, response.text)
        wallet = self.execute("SELECT stars FROM v4_case_wallets WHERE account_id=?", (self.ids["alice"],))[0]
        self.assertEqual(wallet["stars"], 15)

    def test_participants_cannot_grant(self):
        self.assertEqual(self.grant(actor="alice").status_code, 403)

    def test_stars_and_rep_move_together_are_journalled_and_never_go_below_zero(self):
        response = self.grant(stars_delta=30, rep_delta=10, reason="дежурство по столовой")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual((body["stars_delta"], body["rep_delta"]), (30, 10))
        wallet = self.execute("SELECT stars, rep FROM v4_case_wallets WHERE account_id=?", (self.ids["alice"],))[0]
        self.assertEqual((wallet["stars"], wallet["rep"]), (30, 10))
        op = self.execute(
            "SELECT operation, actor_account_id, stars_delta, rep_delta, details_json FROM v4_economy_operations "
            "WHERE operation=?", (economy.GRANT_OPERATION,))[0]
        self.assertEqual((op["operation"], op["actor_account_id"], op["stars_delta"], op["rep_delta"]),
                          (economy.GRANT_OPERATION, self.ids["staff"], 30, 10))
        self.assertIn("дежурство", op["details_json"])
        # Списание больше остатка останавливается на нуле, не уходит в минус.
        self.assertEqual(self.grant(stars_delta=-100, key="floor-test").status_code, 200)
        wallet = self.execute("SELECT stars FROM v4_case_wallets WHERE account_id=?", (self.ids["alice"],))[0]
        self.assertEqual(wallet["stars"], 0)

    def test_reason_is_required_and_deltas_are_capped(self):
        self.assertEqual(self.grant(stars_delta=5, reason="ок").status_code, 400)  # короче 3 символов
        self.assertEqual(self.grant(stars_delta=0, rep_delta=0).status_code, 400)  # нечего менять
        self.assertEqual(self.grant(stars_delta=101).status_code, 400)
        self.assertEqual(self.grant(rep_delta=51).status_code, 400)
        self.assertEqual(self.grant(stars_delta=100).status_code, 200)
        self.assertEqual(self.grant(rep_delta=-50, key="rep-cap-test").status_code, 200)

    def test_staff_cannot_be_the_target_and_retry_does_not_grant_twice(self):
        # Без всякого членства архитектор просто не проходит базовую
        # проверку участника (403). Настоящая защита — на случай, если он
        # уже играл в какую-то другую игру и получил настоящее членство:
        # даже тогда начисление ему отказывает, отдельно и по роли.
        self.assertEqual(self.grant(who="architect", stars_delta=5).status_code, 403)
        self.execute("INSERT INTO v4_season_memberships(season_id, account_id, status) VALUES (1, ?, 'active')",
                     (self.ids["architect"],))
        self.assertEqual(self.grant(who="architect", stars_delta=5, key="staff-target").status_code, 409)
        key = "grant-once"
        first = self.grant(stars_delta=7, key=key)
        second = self.grant(stars_delta=7, key=key)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.json(), first.json())
        self.assertEqual(second.headers["x-idempotent-replayed"], "true")
        wallet = self.execute("SELECT stars FROM v4_case_wallets WHERE account_id=?", (self.ids["alice"],))[0]
        self.assertEqual(wallet["stars"], 7)


if __name__ == "__main__":
    unittest.main()
