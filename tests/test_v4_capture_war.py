from __future__ import annotations

import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from zhidao_v4 import capture, duels, story
from zhidao_v4.api import create_app
from zhidao_v4.auth import provision_local_account
from zhidao_v4.bootstrap import bootstrap_system_admin
from zhidao_v4.db import connect_database, immediate_transaction


ADMIN_PASSWORD = "correct horse battery staple"
USER_PASSWORD = "another correct horse battery"
MORNING = datetime(2026, 9, 12, 2, 0, tzinfo=timezone.utc)   # 10:00 по Шанхаю
KIDS = [f"kid{n}" for n in range(1, 7)]
WALLET = 50
REST = timedelta(seconds=capture.config()["cooldown_seconds"] + 1)


def near(code: str) -> tuple[float, float]:
    lon, lat = story.feature_centres()[capture.points()[code]["feature"]]
    return lon, lat + 20 / 111320


class CaptureWarTests(unittest.TestCase):
    """Захват кампуса, этап 3 (V4_GAMES.md §4.12).

    Обещания (решения пользователя 2026-09-13): способности покупает фракция
    складчиной — щит 15★, туман 10★, двойные очки 20★, разведка 5★; щит и
    двойные очки — только на свои точки, разведка — на любую; туман прячет
    уровни только от соперников; лидер дня получает +8★ и +10 REP, но только
    те, кто в этот день играл, и один раз; «Подвести итоги» замораживает войну,
    даёт победителю рамку-кубок и возвращает несобранные копилки; новая война
    начинается с ничьей карты; повторный взнос с тем же ключом не списывает
    дважды.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "zhidao.db"
        self.bootstrap = bootstrap_system_admin(self.db_path, username="architect", password=ADMIN_PASSWORD,
                                                display_name="Архитектор")
        conn = connect_database(self.db_path)
        try:
            with immediate_transaction(conn):
                self.ids = {}
                for name in KIDS:
                    self.ids[name] = provision_local_account(
                        conn, username=name, password=USER_PASSWORD, display_name=name, role_code="participant",
                        actor_account_id=self.bootstrap["account"]["id"])["id"]
                    conn.execute("INSERT INTO v4_season_memberships(season_id, account_id, status) VALUES (1, ?, 'active')",
                                 (self.ids[name],))
                    conn.execute("INSERT INTO v4_case_wallets(season_id, account_id, stars) VALUES (1, ?, ?)",
                                 (self.ids[name], WALLET))
                conn.execute("UPDATE v4_seasons SET status='active' WHERE id=1")
        finally:
            conn.close()
        self.now = MORNING
        self.clock = mock.patch("zhidao_v4.capture.utcnow", side_effect=lambda: self.now)
        self.clock.start()
        capture.challenges = capture.Challenges()
        duels.offers = duels.DuelOffers()
        duels.last_rival.clear()
        self.app = create_app(self.db_path, cookie_secure=False, session_hours=1)
        self.clients, self.tokens = {}, {}
        for name in ["architect"] + KIDS:
            client = TestClient(self.app)
            password = ADMIN_PASSWORD if name == "architect" else USER_PASSWORD
            response = client.post("/api/v4/auth/login", json={"username": name, "password": password})
            self.assertEqual(response.status_code, 200, response.text)
            self.clients[name], self.tokens[name] = client, response.json()["csrf_token"]
        for code in ("stadium", "canteen"):
            lon, lat = story.feature_centres()[capture.points()[code]["feature"]]
            self.assertEqual(self.post("architect", f"/api/v4/capture/points/{code}/confirm",
                                       {"lon": lon, "lat": lat, "accuracy_m": 8}).status_code, 200)
        self.assertEqual(self.post("architect", "/api/v4/capture/switch", {"enabled": True}).status_code, 200)
        teams = {}
        for name in KIDS:
            teams.setdefault(self.view(name)["you"]["faction"], []).append(name)
        groups = list(teams.values())
        self.a, self.mate, self.b = groups[0][0], groups[0][1], groups[1][0]
        self.fa, self.fb = list(teams)[0], list(teams)[1]

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

    def post(self, who, path, body=None, key=None):
        headers = {"X-CSRF-Token": self.tokens[who]}
        if key:
            headers["X-Idempotency-Key"] = key
        return self.clients[who].post(path, headers=headers, json=body or {})

    def view(self, who):
        response = self.clients[who].get("/api/v4/capture")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def point(self, who, code="stadium"):
        return next(p for p in self.view(who)["points"] if p["code"] == code)

    def challenge(self, who, code="stadium"):
        lon, lat = near(code)
        return self.post(who, f"/api/v4/capture/points/{code}/challenge", {"lon": lon, "lat": lat, "accuracy_m": 10})

    def play(self, who, code="stadium", correct=True):
        response = self.challenge(who, code)
        self.assertEqual(response.status_code, 200, response.text)
        right = capture.challenges.pending[(self.ids[who], code)]["answer"]
        choice = right if correct else (right + 1) % capture.QUESTION_OPTIONS
        result = self.post(who, f"/api/v4/capture/points/{code}/answer", {"choice": choice})
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def pool(self, who, ability, amount, target=None, key=None):
        body = {"ability": ability, "amount": amount}
        if target:
            body["target"] = target
        return self.post(who, "/api/v4/capture/pool", body, key=key or uuid.uuid4().hex)

    def wallet(self, who):
        row = self.sql("SELECT stars, rep FROM v4_case_wallets WHERE season_id=1 AND account_id=?", (self.ids[who],))[0]
        return int(row["stars"]), int(row["rep"])

    def score(self, faction):
        return next(f["score"] for f in self.view("architect")["factions"] if f["code"] == faction)

    # --- способности ----------------------------------------------------------------------

    def test_a_pool_fills_from_several_members_and_turns_on_the_shield(self):
        self.play(self.a)
        first = self.pool(self.a, "shield", 10, target="stadium").json()
        self.assertEqual((first["paid"], first["collected"], first["activated"]), (10, 10, False))
        second = self.pool(self.mate, "shield", 10, target="stadium").json()
        self.assertEqual((second["paid"], second["activated"]), (5, True))
        self.assertEqual((self.wallet(self.a)[0], self.wallet(self.mate)[0]), (WALLET - 10, WALLET - 5))
        self.assertIn("shield_until", self.point(self.b))
        self.assertEqual(self.challenge(self.b).status_code, 409)
        self.assertEqual(self.pool(self.a, "shield", 5, target="stadium").status_code, 409)   # уже действует
        self.now += timedelta(minutes=31)
        self.assertEqual(self.challenge(self.b).status_code, 200)

    def test_shield_and_double_go_on_own_points_and_scouting_on_any(self):
        self.play(self.a)
        self.assertEqual(self.pool(self.a, "shield", 15, target="canteen").status_code, 409)   # ничья точка
        self.assertEqual(self.pool(self.b, "double", 20, target="stadium").status_code, 409)   # чужая
        self.assertEqual(self.pool(self.b, "scout", 5).status_code, 404)                       # без точки
        self.assertTrue(self.pool(self.b, "scout", 5, target="stadium").json()["activated"])
        self.assertEqual(self.point(self.b)["scouted"], {"moves_today": 1})
        self.assertNotIn("scouted", self.point(self.a))

    def test_fog_hides_levels_from_rivals_only(self):
        self.play(self.a)
        self.assertTrue(self.pool(self.a, "fog", 10).json()["activated"])
        rival = self.point(self.b)
        self.assertEqual((rival["owner"], rival["level"], rival.get("hidden")), (self.fa, None, True))
        self.assertEqual(self.point(self.mate)["level"], 1)
        self.assertEqual(self.point("architect")["level"], 1)
        self.now += timedelta(minutes=61)
        self.assertEqual(self.point(self.b)["level"], 1)

    def test_double_points_count_twice_while_active(self):
        self.play(self.a)                                                   # 10:00
        self.assertTrue(self.pool(self.a, "double", 20, target="stadium").json()["activated"])
        self.now = MORNING + timedelta(hours=1)
        self.assertEqual(self.score(self.fa), 12)
        self.now = MORNING + timedelta(minutes=90)
        self.assertEqual(self.score(self.fa), 15)

    def test_a_retried_contribution_is_charged_once(self):
        key = uuid.uuid4().hex
        self.assertEqual(self.pool(self.a, "fog", 4, key=key).status_code, 200)
        again = self.pool(self.a, "fog", 4, key=key)
        self.assertEqual(again.headers["X-Idempotent-Replayed"], "true")
        self.assertEqual(self.wallet(self.a)[0], WALLET - 4)
        self.assertEqual(self.view(self.mate)["pools"], [{"ability": "fog", "target": None, "collected": 4, "price": 10}])
        self.assertEqual(self.view(self.b)["pools"], [])

    def test_contributions_wait_for_the_open_window(self):
        self.now = MORNING + timedelta(hours=11)
        self.assertEqual(self.pool(self.a, "fog", 10).status_code, 409)
        self.assertEqual(self.wallet(self.a)[0], WALLET)

    # --- лидер дня ------------------------------------------------------------------------

    def test_the_day_leader_rewards_only_members_who_played_and_only_once(self):
        self.play(self.a)
        self.play(self.b, code="canteen", correct=False)
        self.now = MORNING + timedelta(hours=8, minutes=1)                  # 18:01
        self.view("architect")
        self.view("architect")
        self.assertEqual(self.wallet(self.a), (WALLET + 8, 10))
        self.assertEqual(self.wallet(self.mate), (WALLET, 0))                # не играл
        self.assertEqual(self.wallet(self.b), (WALLET, 0))                   # играл, но не лидер
        self.assertEqual(len(self.sql("SELECT 1 FROM v4_economy_operations WHERE operation='capture.daily'")), 1)
        self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM v4_capture_activity")[0]["n"], 0)

    def test_no_reward_before_the_day_is_over(self):
        self.play(self.a)
        self.now = MORNING + timedelta(hours=5)                              # 15:00, день ещё идёт
        self.view("architect")
        self.assertEqual(self.wallet(self.a), (WALLET, 0))

    # --- итоги и новая война ------------------------------------------------------------------

    def test_finishing_the_war_crowns_the_winner_and_returns_unfilled_pools(self):
        self.play(self.a)
        self.assertEqual(self.pool(self.b, "fog", 3).json()["activated"], False)
        self.assertEqual(self.wallet(self.b)[0], WALLET - 3)
        self.now += timedelta(minutes=30)
        self.assertEqual(self.post(self.a, "/api/v4/capture/finish").status_code, 403)
        result = self.post("architect", "/api/v4/capture/finish").json()
        self.assertEqual(result["winners"], [self.fa])
        self.assertEqual(self.wallet(self.b)[0], WALLET)
        seen = self.view(self.a)
        self.assertEqual((seen["war"], seen["enabled"]), ({"number": 1, "finished": True}, False))
        self.assertEqual(seen["wars"][0]["winners"], [self.fa])
        self.now += REST
        self.assertEqual(self.challenge(self.a).status_code, 409)
        self.assertEqual(self.post("architect", "/api/v4/capture/switch", {"enabled": True}).status_code, 409)
        shop = self.clients[self.a].get("/api/v4/seasons/1/shop").json()
        self.assertIn("fr_cup", [item["code"] for item in shop["cosmetics"]])
        self.assertEqual(self.post(self.a, "/api/v4/seasons/1/shop/equip", {"slot": "frame", "item_code": "fr_cup"}).status_code, 200)
        self.assertEqual(self.post(self.b, "/api/v4/seasons/1/shop/equip", {"slot": "frame", "item_code": "fr_cup"}).status_code, 409)
        self.assertEqual(self.post("architect", "/api/v4/capture/finish").status_code, 409)

    def test_a_new_war_starts_from_an_empty_map(self):
        self.play(self.a)
        self.assertEqual(self.post("architect", "/api/v4/capture/new-war").status_code, 409)
        self.now += timedelta(minutes=30)
        self.post("architect", "/api/v4/capture/finish")
        self.assertEqual(self.post("architect", "/api/v4/capture/new-war").json(), {"war": 2, "enabled": False})
        seen = self.view(self.a)
        self.assertEqual((seen["war"]["number"], seen["enabled"], len(seen["wars"])), (2, False, 1))
        self.assertIsNone(self.point(self.a)["owner"])
        self.assertEqual(self.score(self.fa), 0)
        self.assertEqual(self.post("architect", "/api/v4/capture/switch", {"enabled": True}).status_code, 200)
        self.assertEqual(self.challenge(self.a).status_code, 200)


if __name__ == "__main__":
    unittest.main()
