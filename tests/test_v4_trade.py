from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from zhidao_v4 import meet, trade
from zhidao_v4.api import create_app
from zhidao_v4.auth import provision_local_account
from zhidao_v4.db import connect_database, immediate_transaction
from zhidao_v4.migrations import apply_migrations


PASSWORD = "a secure testing password"
MORNING = datetime(2026, 9, 11, 2, 0, tzinfo=timezone.utc)
COMMON = "fate_guard"          # gold
RARE = "implant_panda"         # purple
LEGEND = "implant_red_dragon"  # black


class TradeTests(unittest.TestCase):
    """Обмен дубликатами.

    Обещания (решения пользователя): отдаётся только дубликат; оба платят 5★;
    не больше трёх обменов в день; неравный обмен проходит только после
    отдельного подтверждения от того, кто отдаёт более редкое; до двух
    подтверждений ничего не двигается, а если к моменту обмена что-то
    изменилось — не двигается вовсе.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "trade.sqlite"
        apply_migrations(self.path)
        conn = connect_database(self.path)
        with immediate_transaction(conn):
            self.ids = {}
            for name in ("alice", "boris", "stranger"):
                self.ids[name] = provision_local_account(conn, username=name, password=PASSWORD,
                                                         display_name=name.capitalize(), role_code="participant")["id"]
            conn.execute("INSERT INTO v4_seasons(id,code,name,status,timezone) VALUES (1,'hainan','Hainan','active','Asia/Shanghai')")
            for name in ("alice", "boris"):
                conn.execute("INSERT INTO v4_season_memberships(season_id,account_id,status) VALUES (1,?,'active')", (self.ids[name],))
                conn.execute("INSERT INTO v4_case_wallets(season_id,account_id,stars) VALUES (1,?,100)", (self.ids[name],))
        conn.close()
        self.give("alice", COMMON, 3)
        self.give("boris", RARE, 2)
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

    def give(self, who, code, quantity):
        # Купона нет в каталоге обмена — намеренно; для него состояние «ожидает».
        effect = trade.catalogue().get(code, {}).get("effect_state", "pending")
        self.sql("""INSERT INTO v4_case_inventory(season_id,account_id,item_code,quantity,effect_state) VALUES (1,?,?,?,?)
                    ON CONFLICT(season_id,account_id,item_code) DO UPDATE SET quantity=excluded.quantity""",
                 (self.ids[who], code, quantity, effect))

    def qty(self, who, code):
        row = self.sql("SELECT quantity FROM v4_case_inventory WHERE account_id=? AND item_code=?", (self.ids[who], code))
        return row[0][0] if row else 0

    def stars(self, who):
        return self.sql("SELECT stars FROM v4_case_wallets WHERE account_id=?", (self.ids[who],))[0][0]

    def post(self, who, path, body=None):
        return self.clients[who].post(path, headers={"X-CSRF-Token": self.tokens[who]}, json=body or {})

    def offer(self, who="alice", item=COMMON):
        return self.post(who, "/api/v4/seasons/1/trade/offer", {"item_code": item})

    def join(self, code, who="boris", item=RARE):
        return self.post(who, "/api/v4/seasons/1/trade/join", {"code": code, "item_code": item})

    def confirm(self, code, who, acknowledge=False):
        return self.post(who, f"/api/v4/seasons/1/trade/{code}/confirm", {"acknowledge_unequal": acknowledge})

    def ready_trade(self, a_item=COMMON, b_item=RARE):
        response = self.offer(item=a_item)
        self.assertEqual(response.status_code, 200, response.text)
        code = response.json()["code"]
        joined = self.join(code, item=b_item)
        self.assertEqual(joined.status_code, 200, joined.text)
        return code

    # --- что можно обменивать -------------------------------------------------------

    def test_only_duplicates_are_offered_and_coupons_or_cosmetics_never(self):
        self.give("alice", RARE, 1)
        self.give("alice", "walk", 4)
        self.sql("INSERT INTO v4_case_inventory(season_id,account_id,item_code,quantity,effect_state) VALUES (1,?,'wp_grid',2,'active')",
                 (self.ids["alice"],))
        items = self.clients["alice"].get("/api/v4/seasons/1/trade").json()["items"]
        self.assertEqual([item["code"] for item in items], [COMMON])
        self.assertEqual(self.offer(item=RARE).status_code, 409)
        self.assertEqual(self.offer(item="walk").status_code, 400)

    # --- обмен ------------------------------------------------------------------------

    def test_two_confirmations_swap_the_items_and_burn_the_fee(self):
        code = self.ready_trade()
        # Алиса отдаёт обычный за редкий — ей неравенство не мешает.
        first = self.confirm(code, "alice")
        self.assertEqual(first.json()["state"], "ready")
        self.assertEqual((self.qty("alice", COMMON), self.qty("boris", RARE)), (3, 2))   # пока ничего не двинулось
        # Борис отдаёт более редкое — без подтверждения неравенства нельзя.
        self.assertEqual(self.confirm(code, "boris").status_code, 409)
        done = self.confirm(code, "boris", acknowledge=True).json()
        self.assertEqual(done["state"], "done")
        self.assertEqual((self.qty("alice", COMMON), self.qty("alice", RARE)), (2, 1))
        self.assertEqual((self.qty("boris", RARE), self.qty("boris", COMMON)), (1, 1))
        self.assertEqual((self.stars("alice"), self.stars("boris")), (95, 95))
        ops = self.sql("SELECT account_id, operation, stars_delta FROM v4_economy_operations ORDER BY account_id")
        self.assertEqual(sorted(tuple(r) for r in ops),
                         sorted([(self.ids["alice"], trade.OPERATION, -5), (self.ids["boris"], trade.OPERATION, -5)]))
        view = self.clients["alice"].get(f"/api/v4/seasons/1/trade/{code}").json()
        self.assertEqual(view["result"]["got"], trade.catalogue()[RARE]["name_ru"])

    def test_confirming_twice_does_not_trade_twice(self):
        code = self.ready_trade(b_item=RARE)
        self.confirm(code, "alice")
        self.confirm(code, "boris", acknowledge=True)
        self.assertEqual(self.confirm(code, "boris", acknowledge=True).status_code, 409)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM v4_economy_operations")[0][0], 2)

    def test_the_rarer_side_must_acknowledge_an_unequal_trade(self):
        self.give("boris", LEGEND, 2)
        code = self.ready_trade(b_item=LEGEND)
        view = self.clients["boris"].get(f"/api/v4/seasons/1/trade/{code}").json()
        self.assertTrue(view["gives_rarer"])
        self.assertFalse(self.clients["alice"].get(f"/api/v4/seasons/1/trade/{code}").json()["gives_rarer"])

    def test_three_trades_a_day_at_most(self):
        self.give("alice", COMMON, 9)
        self.give("boris", RARE, 9)
        for _ in range(3):
            code = self.ready_trade()
            self.confirm(code, "alice")
            self.assertEqual(self.confirm(code, "boris", acknowledge=True).json()["state"], "done")
        self.assertEqual(self.offer().status_code, 409)

    def test_nothing_moves_if_something_changed_before_the_swap(self):
        code = self.ready_trade()
        self.confirm(code, "alice")
        self.give("alice", COMMON, 1)          # дубликат потратили, пока ждали
        result = self.confirm(code, "boris", acknowledge=True).json()
        self.assertEqual(result["state"], "failed")
        self.assertEqual((self.qty("alice", COMMON), self.qty("boris", RARE), self.qty("boris", COMMON)), (1, 2, 0))
        self.assertEqual((self.stars("alice"), self.stars("boris")), (100, 100))
        self.assertEqual(self.sql("SELECT COUNT(*) FROM v4_economy_operations")[0][0], 0)

    def test_not_enough_stars_for_the_fee(self):
        self.sql("UPDATE v4_case_wallets SET stars=4 WHERE account_id=?", (self.ids["boris"],))
        code = self.offer().json()["code"]
        self.assertEqual(self.join(code).status_code, 409)

    def test_cancel_closes_the_trade_for_both(self):
        code = self.ready_trade()
        self.assertEqual(self.post("boris", f"/api/v4/seasons/1/trade/{code}/cancel").json()["state"], "cancelled")
        self.assertEqual(self.confirm(code, "alice").status_code, 409)

    # --- код -----------------------------------------------------------------------

    def test_codes_are_not_for_yourself_expire_and_are_private(self):
        code = self.offer().json()["code"]
        self.assertEqual(self.join(code, who="alice", item=COMMON).status_code, 409)
        self.assertEqual(self.clients["stranger"].get(f"/api/v4/seasons/1/trade/{code}").status_code, 404)
        self.assertEqual(self.join(code, who="stranger").status_code, 403)
        start = meet.clock()
        with mock.patch("zhidao_v4.meet.clock", return_value=start + trade.TRADE_SECONDS + 1):
            self.assertEqual(self.join(code).status_code, 404)

    def test_guessing_trade_codes_hits_the_limit(self):
        codes = {self.join(f"{n:06d}").status_code for n in range(12)}
        self.assertIn(429, codes)


if __name__ == "__main__":
    unittest.main()
