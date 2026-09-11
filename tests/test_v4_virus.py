from __future__ import annotations

import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from zhidao_v4 import cipher, trade, virus
from zhidao_v4.api import create_app
from zhidao_v4.auth import provision_local_account
from zhidao_v4.db import connect_database, immediate_transaction
from zhidao_v4.migrations import apply_migrations


PASSWORD = "a secure testing password"
MORNING = datetime(2026, 9, 11, 2, 0, tzinfo=timezone.utc)   # 10:00 по Шанхаю


class VirusTests(unittest.TestCase):
    """Вирус Протокола.

    Обещания (решения пользователя): первый вирус выпускает Архитектор;
    передаётся при встрече и обмене с вероятностью 50%, если заражён один из
    двоих; фаервол отбивает; через 6 часов проходит сам; лечится тестом из
    пяти слов или антивирусом за 15★; фаервол — 20★ до утра. Кто кого
    заразил, не хранится.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "virus.sqlite"
        apply_migrations(self.path)
        conn = connect_database(self.path)
        with immediate_transaction(conn):
            self.ids = {}
            for name, role in [("arch", "architect"), ("staff", "operator"), ("alice", "participant"), ("boris", "participant")]:
                self.ids[name] = provision_local_account(conn, username=name, password=PASSWORD,
                                                         display_name=name.capitalize(), role_code=role)["id"]
            conn.execute("INSERT INTO v4_seasons(id,code,name,status,timezone) VALUES (1,'hainan','Hainan','active','Asia/Shanghai')")
            for name in ("alice", "boris"):
                conn.execute("INSERT INTO v4_season_memberships(season_id,account_id,status) VALUES (1,?,'active')", (self.ids[name],))
                conn.execute("INSERT INTO v4_case_wallets(season_id,account_id,stars) VALUES (1,?,100)", (self.ids[name],))
        conn.close()
        self.now = MORNING
        self.clock = mock.patch("zhidao_v4.shop.utcnow", side_effect=lambda: self.now)
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

    def post(self, who, path, body=None, key=False):
        headers = {"X-CSRF-Token": self.tokens[who]}
        if key:
            headers["X-Idempotency-Key"] = key if isinstance(key, str) else uuid.uuid4().hex
        return self.clients[who].post(path, headers=headers, json=body or {})

    def status(self, who):
        return self.clients[who].get("/api/v4/seasons/1/virus").json()

    def release(self, target="alice", actor="arch"):
        return self.post(actor, "/api/v4/seasons/1/virus/release", {"account_id": self.ids[target]})

    def sql(self, query, values=()):
        conn = connect_database(self.path)
        try:
            with immediate_transaction(conn):
                return conn.execute(query, values).fetchall()
        finally:
            conn.close()

    def meet(self):
        code = self.post("alice", "/api/v4/seasons/1/meet/offer").json()["code"]
        return self.post("boris", "/api/v4/seasons/1/meet/accept", {"code": code})

    # --- выпуск и передача -----------------------------------------------------------

    def test_only_the_architect_releases_the_virus(self):
        self.assertEqual(self.release(actor="staff").status_code, 403)
        self.assertEqual(self.release(actor="alice").status_code, 403)
        self.assertEqual(self.release().status_code, 200)
        self.assertTrue(self.status("alice")["infected"])
        self.assertFalse(self.status("boris")["infected"])

    def test_it_spreads_at_a_meeting_when_the_coin_says_so(self):
        self.release("alice")
        with mock.patch.object(virus._rng, "random", return_value=0.9):
            first = self.meet()
        self.assertEqual(first.status_code, 200, first.text)
        self.assertIsNone(first.json()["virus"])
        self.assertFalse(self.status("boris")["infected"])
        # На следующий день та же пара снова может встретиться; Алису заражаем заново.
        self.now = MORNING + timedelta(days=1)
        self.assertEqual(self.release("alice").status_code, 200)
        with mock.patch.object(virus._rng, "random", return_value=0.1):
            second = self.meet()
        self.assertEqual(second.json()["virus"], "caught")
        self.assertTrue(self.status("boris")["infected"])

    def test_a_firewall_blocks_the_spread(self):
        self.release("alice")
        self.assertEqual(self.post("boris", "/api/v4/seasons/1/virus/firewall", key=True).status_code, 200)
        with mock.patch.object(virus._rng, "random", return_value=0.0):
            body = self.meet().json()
        self.assertEqual(body["virus"], "blocked")
        self.assertFalse(self.status("boris")["infected"])

    def test_it_spreads_on_a_trade_too(self):
        self.release("boris")
        for who, code in (("alice", "fate_guard"), ("boris", "implant_panda")):
            effect = trade.catalogue()[code]["effect_state"]
            self.sql("INSERT INTO v4_case_inventory(season_id,account_id,item_code,quantity,effect_state) VALUES (1,?,?,2,?)",
                     (self.ids[who], code, effect))
        offer = self.post("alice", "/api/v4/seasons/1/trade/offer", {"item_code": "fate_guard"}).json()["code"]
        self.post("boris", "/api/v4/seasons/1/trade/join", {"code": offer, "item_code": "implant_panda"})
        self.post("alice", f"/api/v4/seasons/1/trade/{offer}/confirm", {"acknowledge_unequal": False})
        with mock.patch.object(virus._rng, "random", return_value=0.0):
            done = self.post("boris", f"/api/v4/seasons/1/trade/{offer}/confirm", {"acknowledge_unequal": True}).json()
        self.assertEqual(done["state"], "done")
        self.assertTrue(self.status("alice")["infected"])
        view = self.clients["alice"].get(f"/api/v4/seasons/1/trade/{offer}").json()
        self.assertEqual(view["result"]["virus"], "caught")

    def test_it_wears_off_after_six_hours(self):
        self.release("alice")
        self.now = MORNING + timedelta(hours=virus.DURATION_HOURS, minutes=1)
        self.assertFalse(self.status("alice")["infected"])

    def test_the_table_does_not_remember_who_infected_whom(self):
        columns = {row["name"] for row in self.sql("PRAGMA table_info(v4_virus_state)")}
        self.assertEqual(columns, {"season_id", "account_id", "infected_until", "firewall_until"})

    # --- лечение и защита --------------------------------------------------------------

    def test_antivirus_cures_for_fifteen_stars_once(self):
        self.assertEqual(self.post("alice", "/api/v4/seasons/1/virus/antivirus", key=True).status_code, 409)
        self.release("alice")
        first = self.post("alice", "/api/v4/seasons/1/virus/antivirus", key="antivirus-once")
        self.assertEqual(first.status_code, 200, first.text)
        again = self.post("alice", "/api/v4/seasons/1/virus/antivirus", key="antivirus-once")
        self.assertEqual(again.json(), first.json())
        self.assertFalse(self.status("alice")["infected"])
        self.assertEqual(self.status("alice")["stars"], 100 - virus.ANTIVIRUS_PRICE)
        ops = self.sql("SELECT operation, stars_delta FROM v4_economy_operations")
        self.assertEqual([tuple(r) for r in ops], [("virus.antivirus", -virus.ANTIVIRUS_PRICE)])

    def test_firewall_costs_twenty_and_lasts_until_seven(self):
        body = self.post("boris", "/api/v4/seasons/1/virus/firewall", key=True).json()
        # 07:00 по Шанхаю 12 сентября = 23:00 UTC 11 сентября.
        self.assertEqual(body["firewall_until"], "2026-09-11T23:00:00.000000Z")
        self.assertEqual(self.status("boris")["stars"], 100 - virus.FIREWALL_PRICE)
        self.assertEqual(self.post("boris", "/api/v4/seasons/1/virus/firewall", key=True).status_code, 409)
        self.assertEqual(self.release("boris").status_code, 409)
        self.now = datetime(2026, 9, 11, 23, 1, tzinfo=timezone.utc)
        self.assertFalse(self.status("boris")["firewall"])

    def test_the_word_test_cures_with_four_of_five_and_hides_the_answers(self):
        self.release("alice")
        test = self.post("alice", "/api/v4/seasons/1/virus/test").json()
        self.assertEqual(len(test["questions"]), virus.TEST_SIZE)
        self.assertTrue(all(len(q["options"]) == virus.TEST_OPTIONS for q in test["questions"]))
        self.assertNotIn("answer", str(test))
        words = {w["zh"]: w["ru"] for w in cipher.content()["words"]}
        right = [q["options"].index(words[q["zh"]]) for q in test["questions"]]
        wrong_once = right[:]
        wrong_once[0] = (right[0] + 1) % virus.TEST_OPTIONS
        result = self.post("alice", "/api/v4/seasons/1/virus/test/answer", {"answers": wrong_once}).json()
        self.assertEqual((result["correct"], result["cured"]), (4, True))
        self.assertFalse(self.status("alice")["infected"])

    def test_failing_the_test_leaves_you_infected_and_the_test_is_used_up(self):
        self.release("alice")
        test = self.post("alice", "/api/v4/seasons/1/virus/test").json()
        words = {w["zh"]: w["ru"] for w in cipher.content()["words"]}
        wrong = [(q["options"].index(words[q["zh"]]) + 1) % virus.TEST_OPTIONS for q in test["questions"]]
        result = self.post("alice", "/api/v4/seasons/1/virus/test/answer", {"answers": wrong}).json()
        self.assertFalse(result["cured"])
        self.assertTrue(self.status("alice")["infected"])
        self.assertEqual(self.post("alice", "/api/v4/seasons/1/virus/test/answer", {"answers": wrong}).status_code, 409)

    def test_no_test_for_the_healthy(self):
        self.assertEqual(self.post("boris", "/api/v4/seasons/1/virus/test").status_code, 409)


if __name__ == "__main__":
    unittest.main()
