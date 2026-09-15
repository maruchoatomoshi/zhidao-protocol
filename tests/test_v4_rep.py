from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from zhidao_v4.api import create_app
from zhidao_v4.auth import provision_local_account
from zhidao_v4.bootstrap import bootstrap_system_admin
from zhidao_v4.db import connect_database, immediate_transaction


ADMIN_PASSWORD = "correct horse battery staple"
USER_PASSWORD = "another correct horse battery"
REP = {"kid1": 520, "kid2": 470, "kid3": 455, "kid4": 410, "kid5": 380, "kid6": 355, "kid7": 340, "kid8": 325}


class RepBoardTests(unittest.TestCase):
    """REP сезона (решение пользователя 2026-09-15).

    Обещания: участник видит тройку лидеров, своё место и соседей рядом, но не
    всю таблицу; организатор без участия — только тройку; чужие сезону и гости
    не видят ничего.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "zhidao.db"
        bootstrap = bootstrap_system_admin(self.db_path, username="architect", password=ADMIN_PASSWORD,
                                           display_name="Архитектор")
        conn = connect_database(self.db_path)
        try:
            with immediate_transaction(conn):
                for name in [*REP, "rookie", "outsider"]:
                    account = provision_local_account(conn, username=name, password=USER_PASSWORD, display_name=name,
                                                      role_code="participant",
                                                      actor_account_id=bootstrap["account"]["id"])
                    if name == "outsider":
                        continue
                    conn.execute("INSERT INTO v4_season_memberships(season_id, account_id, status) VALUES (1, ?, 'active')",
                                 (account["id"],))
                    if name in REP:
                        conn.execute("INSERT INTO v4_case_wallets(season_id, account_id, rep) VALUES (1, ?, ?)",
                                     (account["id"], REP[name]))
        finally:
            conn.close()
        self.app = create_app(self.db_path, cookie_secure=False, session_hours=1)
        self.clients = {}

    def tearDown(self):
        for client in self.clients.values():
            client.close()
        self.temp_dir.cleanup()

    def client(self, name):
        if name not in self.clients:
            client = TestClient(self.app)
            password = ADMIN_PASSWORD if name == "architect" else USER_PASSWORD
            response = client.post("/api/v4/auth/login", json={"username": name, "password": password})
            self.assertEqual(response.status_code, 200, response.text)
            self.clients[name] = client
        return self.clients[name]

    def board(self, name):
        response = self.client(name).get("/api/v4/seasons/1/rep/board")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_a_participant_sees_the_leaders_their_place_and_neighbours_only(self):
        data = self.board("kid7")
        self.assertEqual(data["total"], 9)
        self.assertEqual(data["me"], {"rank": 7, "rep": 340, "next_rep": 355})
        self.assertEqual([(r["rank"], r["display_name"]) for r in data["leaders"]], [(1, "kid1"), (2, "kid2"), (3, "kid3")])
        self.assertEqual([r["rank"] for r in data["around"]], [5, 6, 7, 8, 9])
        self.assertEqual([r["is_you"] for r in data["around"]], [False, False, True, False, False])
        text = self.client("kid7").get("/api/v4/seasons/1/rep/board").text
        self.assertNotIn("kid4", text)
        self.assertNotIn("account_id", text)

    def test_the_leader_has_no_place_ahead_and_neighbours_never_repeat_the_podium(self):
        first = self.board("kid1")
        self.assertEqual(first["me"], {"rank": 1, "rep": 520, "next_rep": None})
        self.assertEqual(first["around"], [])
        self.assertEqual([r["rank"] for r in self.board("kid3")["around"]], [4, 5])

    def test_a_member_without_a_wallet_counts_with_zero(self):
        self.assertEqual(self.board("rookie")["me"], {"rank": 9, "rep": 0, "next_rep": 325})

    def test_an_organiser_sees_only_the_leaders_and_strangers_see_nothing(self):
        data = self.board("architect")
        self.assertIsNone(data["me"])
        self.assertEqual(len(data["leaders"]), 3)
        self.assertEqual(data["around"], [])
        self.assertEqual(self.client("outsider").get("/api/v4/seasons/1/rep/board").status_code, 403)
        with TestClient(self.app) as guest:
            self.assertEqual(guest.get("/api/v4/seasons/1/rep/board").status_code, 401)


if __name__ == "__main__":
    unittest.main()
