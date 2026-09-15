from __future__ import annotations

import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from zhidao_v4.api import create_app
from zhidao_v4.auth import provision_local_account
from zhidao_v4.bootstrap import bootstrap_system_admin
from zhidao_v4.db import connect_database, immediate_transaction


ADMIN_PASSWORD = "correct horse battery staple"
USER_PASSWORD = "another correct horse battery"
MORNING = datetime(2026, 9, 12, 2, 30, tzinfo=timezone.utc)   # 10:30 по Шанхаю: рынок открыт
NIGHT = datetime(2026, 9, 12, 16, 0, tzinfo=timezone.utc)     # полночь по Шанхаю: рынок закрыт


class TodayTests(unittest.TestCase):
    """«Сейчас в сезоне» на главной (дизайн-проход 2026-09-14).

    Обещания: один снимок того, что идёт прямо сейчас; только чтение; ни имён,
    ни ролей и целей; гость не получает ничего, человек вне сезона — пустой список.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "zhidao.db"
        bootstrap = bootstrap_system_admin(self.db_path, username="architect", password=ADMIN_PASSWORD,
                                           display_name="Архитектор")
        conn = connect_database(self.db_path)
        try:
            with immediate_transaction(conn):
                self.ids = {}
                for name in ("kid1", "kid2", "outsider"):
                    account = provision_local_account(conn, username=name, password=USER_PASSWORD, display_name=name,
                                                      role_code="participant",
                                                      actor_account_id=bootstrap["account"]["id"])
                    self.ids[name] = account["id"]
                    if name != "outsider":
                        conn.execute("INSERT INTO v4_season_memberships(season_id, account_id, status) VALUES (1, ?, 'active')",
                                     (account["id"],))
                # История сезона ещё не началась: без даты старта первый заход сам
                # запускает скрытые файлы, и тихое утро было бы не тихим.
                conn.execute("UPDATE v4_seasons SET status='active', starts_on='2026-10-01' WHERE id=1")
                self.admin_id = bootstrap["account"]["id"]
        finally:
            conn.close()
        self.now = MORNING
        self.clock = mock.patch("zhidao_v4.shop.utcnow", side_effect=lambda: self.now)
        self.clock.start()
        self.app = create_app(self.db_path, cookie_secure=False, session_hours=1)
        self.clients, self.tokens = {}, {}
        for name, password in (("architect", ADMIN_PASSWORD), ("kid1", USER_PASSWORD), ("kid2", USER_PASSWORD),
                               ("outsider", USER_PASSWORD)):
            client = TestClient(self.app)
            response = client.post("/api/v4/auth/login", json={"username": name, "password": password})
            self.assertEqual(response.status_code, 200, response.text)
            self.clients[name], self.tokens[name] = client, response.json()["csrf_token"]

    def tearDown(self):
        self.clock.stop()
        for client in self.clients.values():
            client.close()
        self.temp_dir.cleanup()

    def sql(self, query, values=()):
        conn = connect_database(self.db_path)
        try:
            with immediate_transaction(conn):
                return conn.execute(query, values).fetchall()
        finally:
            conn.close()

    def post(self, who, path, headers=None):
        return self.clients[who].post(path, json={}, headers={"X-CSRF-Token": self.tokens[who], **(headers or {})})

    def today(self, who="kid1"):
        response = self.clients[who].get("/api/v4/today")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def items(self, who="kid1"):
        return {item["key"]: item for item in self.today(who)["items"]}

    def test_a_quiet_morning_shows_the_open_market_and_nothing_invented(self):
        items = self.items()
        self.assertEqual(set(items), {"market"})
        self.assertEqual((items["market"]["state"], items["market"]["joined"]), ("open", False))
        self.now = NIGHT
        self.assertEqual(self.items(), {})

    def test_live_lobbies_and_joining_the_market_show_up(self):
        self.assertEqual(self.post("architect", "/api/v4/royale/create").status_code, 200)
        self.assertEqual(self.post("kid2", "/api/v4/royale/join").status_code, 200)
        stamp = MORNING.isoformat()
        self.sql("""INSERT INTO v4_zombie_games(season_id, host_account_id, status, state_json, created_at, updated_at)
                    VALUES (1, ?, 'lobby', '{}', ?, ?)""", (self.admin_id, stamp, stamp))
        self.assertEqual(self.post("kid1", "/api/v4/market/join", {"X-Idempotency-Key": str(uuid.uuid4())}).status_code, 200)
        items = self.items()
        self.assertEqual(items["royale"], {"key": "royale", "state": "lobby", "players": 1})
        self.assertEqual(items["zombie"], {"key": "zombie", "state": "lobby"})
        self.assertTrue(items["market"]["joined"])
        self.assertFalse(self.items("kid2")["market"]["joined"])

    def test_an_open_story_file_is_announced(self):
        self.sql("UPDATE v4_seasons SET starts_on='2026-09-12' WHERE id=1")
        self.assertEqual(self.items()["story"], {"key": "story", "state": "open"})

    def test_nobody_is_named_and_outsiders_and_guests_get_nothing(self):
        self.post("architect", "/api/v4/royale/create")
        self.post("kid2", "/api/v4/royale/join")
        text = self.clients["kid1"].get("/api/v4/today").text
        for name in ("kid2", "architect", "Архитектор"):
            self.assertNotIn(name, text)
        self.assertEqual(self.today("outsider"), {"season_id": None, "items": []})
        with TestClient(self.app) as guest:
            self.assertEqual(guest.get("/api/v4/today").status_code, 401)

    def test_the_feed_lists_what_others_did_for_me_recently_and_nobody_is_named(self):
        fresh = (MORNING - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        stale = (MORNING - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        rows = [
            ("kid1", "diary.rate", 25, 50, fresh),
            ("kid1", "royale.prize", 30, 30, fresh),
            ("kid1", "shop.buy", -10, 0, fresh),      # собственная покупка — не новость
            ("kid1", "trade.swap", 0, 0, stale),       # старше двух суток
            ("kid2", "diary.rate", 8, 15, fresh),
        ]
        for who, operation, stars, rep, at in rows:
            self.sql("""INSERT INTO v4_economy_operations(season_id, account_id, actor_account_id, operation,
                            stars_delta, scans_delta, rep_delta, stars_after, scans_after, rep_after, details_json, created_at)
                        VALUES (1, ?, ?, ?, ?, 0, ?, ?, 0, ?, '{}', ?)""",
                     (self.ids[who], self.admin_id, operation, stars, rep, max(stars, 0), rep, at))
        feed = self.today()["feed"]
        self.assertEqual([(f["kind"], f.get("game")) for f in feed], [("prize", "royale"), ("diary", None)])
        self.assertEqual((feed[1]["rep"], feed[1]["stars"]), (50, 25))
        self.assertEqual([f["kind"] for f in self.today("kid2")["feed"]], ["diary"])
        text = self.clients["kid1"].get("/api/v4/today").text
        for name in ("kid2", "architect", "Архитектор"):
            self.assertNotIn(name, text)

    def test_the_home_card_does_not_start_the_story_for_the_season(self):
        self.sql("UPDATE v4_seasons SET starts_on=NULL WHERE id=1")
        self.assertNotIn("story", self.items())
        self.assertEqual(self.sql("SELECT COUNT(*) FROM v4_story_state")[0][0], 0)

    def test_reading_the_home_card_writes_nothing_to_the_games(self):
        before = self.sql("SELECT COUNT(*) FROM v4_market_players")[0][0]
        self.now = MORNING + timedelta(days=1)
        self.items()
        self.assertEqual(self.sql("SELECT COUNT(*) FROM v4_market_players")[0][0], before)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM v4_royale_games")[0][0], 0)


if __name__ == "__main__":
    unittest.main()
