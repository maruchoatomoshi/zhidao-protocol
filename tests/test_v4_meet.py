from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from zhidao_v4 import meet
from zhidao_v4.api import create_app
from zhidao_v4.auth import provision_local_account
from zhidao_v4.db import connect_database, immediate_transaction
from zhidao_v4.migrations import apply_migrations


PASSWORD = "a secure testing password"
MORNING = datetime(2026, 9, 11, 2, 0, tzinfo=timezone.utc)   # 10:00 по Шанхаю


class MeetTests(unittest.TestCase):
    """Рукопожатие и пазл встреч.

    Обещания: кусок получают оба; одна пара — один кусок в сезон-день; код
    срабатывает один раз, живёт минуту и не подходит самому себе; кто с кем
    встречался, после дня не хранится; перебор кода упирается в лимит.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "meet.sqlite"
        apply_migrations(self.path)
        conn = connect_database(self.path)
        with immediate_transaction(conn):
            self.ids = {}
            for name in ("alice", "boris", "vera", "stranger"):
                self.ids[name] = provision_local_account(conn, username=name, password=PASSWORD,
                                                         display_name=name.capitalize(), role_code="participant")["id"]
            conn.execute("INSERT INTO v4_seasons(id,code,name,status,timezone) VALUES (1,'hainan','Hainan','active','Asia/Shanghai')")
            for name in ("alice", "boris", "vera"):
                conn.execute("INSERT INTO v4_season_memberships(season_id,account_id,status) VALUES (1,?,'active')",
                             (self.ids[name],))
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

    def post(self, who, path, body=None):
        return self.clients[who].post(path, headers={"X-CSRF-Token": self.tokens[who]}, json=body or {})

    def offer(self, who):
        response = self.post(who, "/api/v4/seasons/1/meet/offer")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["code"]

    def accept(self, who, code):
        return self.post(who, "/api/v4/seasons/1/meet/accept", {"code": code})

    def puzzles(self, who):
        return self.clients[who].get("/api/v4/seasons/1/puzzles").json()

    def sql(self, query, values=()):
        conn = connect_database(self.path)
        try:
            return conn.execute(query, values).fetchall()
        finally:
            conn.close()

    # --- встреча -----------------------------------------------------------------

    def test_both_people_get_a_piece_and_the_offerer_sees_the_result(self):
        code = self.offer("alice")
        response = self.accept("boris", code)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual((body["state"], body["partner"]), ("met", "Alice"))
        self.assertEqual(body["piece"]["puzzle"], "hainan")
        status = self.clients["alice"].get(f"/api/v4/seasons/1/meet/offer/{code}").json()
        self.assertEqual((status["state"], status["partner"]), ("met", "Boris"))
        for who in ("alice", "boris"):
            current = next(p for p in self.puzzles(who)["puzzles"] if p["code"] == "hainan")
            self.assertEqual(len(current["pieces"]), 1)

    def test_one_pair_one_piece_per_day_but_other_people_still_count(self):
        self.assertEqual(self.accept("boris", self.offer("alice")).status_code, 200)
        again = self.accept("boris", self.offer("alice"))
        self.assertEqual(again.status_code, 409)
        self.assertEqual(self.accept("vera", self.offer("alice")).status_code, 200)
        self.assertEqual(self.puzzles("alice")["met_today"], 2)

    def test_the_next_day_the_pair_meets_again_and_yesterday_is_forgotten(self):
        self.assertEqual(self.accept("boris", self.offer("alice")).status_code, 200)
        self.now = MORNING + timedelta(days=1)
        self.assertEqual(self.accept("boris", self.offer("alice")).status_code, 200)
        days = {row[0] for row in self.sql("SELECT meet_day FROM v4_meet_pairs")}
        self.assertEqual(days, {"2026-09-12"})
        self.now = MORNING + timedelta(days=2)
        self.puzzles("alice")   # простое открытие пазла тоже стирает вчерашних
        self.assertEqual(self.sql("SELECT COUNT(*) FROM v4_meet_pairs")[0][0], 0)

    def test_the_pairs_table_holds_only_today_and_who(self):
        columns = {row["name"] for row in self.sql("PRAGMA table_info(v4_meet_pairs)")}
        self.assertEqual(columns, {"season_id", "meet_day", "account_low", "account_high"})
        piece_columns = {row["name"] for row in self.sql("PRAGMA table_info(v4_puzzle_pieces)")}
        self.assertNotIn("from_account_id", piece_columns)

    # --- код ---------------------------------------------------------------------

    def test_a_code_works_once_and_not_for_its_owner(self):
        code = self.offer("alice")
        self.assertEqual(self.accept("alice", code).status_code, 409)
        self.assertEqual(self.accept("boris", code).status_code, 200)
        self.assertEqual(self.accept("vera", code).status_code, 404)

    def test_a_code_expires_after_a_minute(self):
        start = meet.clock()
        with mock.patch("zhidao_v4.meet.clock", return_value=start):
            code = self.offer("alice")
        with mock.patch("zhidao_v4.meet.clock", return_value=start + meet.OFFER_SECONDS + 1):
            self.assertEqual(self.accept("boris", code).status_code, 404)
            self.assertEqual(self.clients["alice"].get(f"/api/v4/seasons/1/meet/offer/{code}").json()["state"], "expired")

    def test_a_new_code_replaces_the_old_one(self):
        first = self.offer("alice")
        self.offer("alice")
        self.assertEqual(self.accept("boris", first).status_code, 404)

    def test_guessing_codes_hits_the_limit(self):
        codes = {self.accept("boris", f"{n:06d}").status_code for n in range(12)}
        self.assertIn(429, codes)

    def test_outsiders_cannot_meet(self):
        self.assertEqual(self.post("stranger", "/api/v4/seasons/1/meet/offer").status_code, 403)
        self.assertEqual(self.accept("stranger", self.offer("alice")).status_code, 403)

    def test_a_failed_accept_does_not_burn_the_code(self):
        code = self.offer("alice")
        self.assertEqual(self.accept("stranger", code).status_code, 403)
        self.assertEqual(self.accept("boris", code).status_code, 200)

    # --- пазл --------------------------------------------------------------------

    def test_the_last_piece_completes_the_puzzle(self):
        conn = connect_database(self.path)
        with immediate_transaction(conn):
            for piece in range(8):
                conn.execute("INSERT INTO v4_puzzle_pieces(season_id,account_id,puzzle_code,piece) VALUES (1,?,?,?)",
                             (self.ids["alice"], "hainan", piece))
        conn.close()
        code = self.offer("alice")
        self.assertEqual(self.accept("boris", code).status_code, 200)
        status = self.clients["alice"].get(f"/api/v4/seasons/1/meet/offer/{code}").json()
        self.assertTrue(status["piece"]["complete"])
        state = self.puzzles("alice")
        hainan = next(p for p in state["puzzles"] if p["code"] == "hainan")
        self.assertTrue(hainan["complete"])
        self.assertEqual(hainan["pieces"], list(range(9)))
        self.assertIsNone(state["current"])


if __name__ == "__main__":
    unittest.main()
