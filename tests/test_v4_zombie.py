from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from zhidao_v4 import capture, rooms, story, zombie
from zhidao_v4.api import create_app
from zhidao_v4.auth import provision_local_account
from zhidao_v4.bootstrap import bootstrap_system_admin
from zhidao_v4.db import connect_database, immediate_transaction


ADMIN_PASSWORD = "correct horse battery staple"
USER_PASSWORD = "another correct horse battery"
EVENING = datetime(2026, 9, 12, 11, 0, tzinfo=timezone.utc)   # 19:00 по Шанхаю
KIDS = [f"kid{n}" for n in range(1, 9)]
REST = timedelta(seconds=zombie.config()["tag_cooldown_seconds"] + 1)


def near(code: str) -> tuple[float, float]:
    lon, lat = story.feature_centres()[capture.points()[code]["feature"]]
    return lon, lat + 20 / 111320


class ZombieTests(unittest.TestCase):
    """Зомби-протокол (V4_GAMES.md §4.12).

    Обещания (решения пользователя 2026-09-13): заражение — вводом кода с
    телефона жертвы; первые зомби — кто болеет Вирусом Протокола, но не больше
    трети, иначе жребий; вакцина — у подтверждённой станции по GPS и китайскому
    вопросу, один раз за раунд, с иммунитетом и новым кодом; выжившие и лучший
    зомби получают по 10★ в раундах от 8 игроков, не чаще раза в день; раунд
    кончается по времени или когда людей не осталось; код видит только
    хозяин; кто кого заразил, не хранится, состав удаляется через полчаса.
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
        self.now = EVENING
        self.clock = mock.patch("zhidao_v4.zombie.utcnow", side_effect=lambda: self.now)
        self.clock.start()
        zombie.vaccines = zombie.Vaccines()
        self.app = create_app(self.db_path, cookie_secure=False, session_hours=1)
        self.clients, self.tokens = {}, {}
        for name in ["architect"] + KIDS:
            client = TestClient(self.app)
            password = ADMIN_PASSWORD if name == "architect" else USER_PASSWORD
            response = client.post("/api/v4/auth/login", json={"username": name, "password": password})
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
        return self.clients[who].post(path, headers={"X-CSRF-Token": self.tokens[who]}, json=body or {})

    def ok(self, response):
        self.assertLess(response.status_code, 300, response.text)
        return response.json()

    def view(self, who):
        return self.ok(self.clients[who].get("/api/v4/zombie"))

    def round(self, players=KIDS):
        self.ok(self.post("architect", "/api/v4/zombie/create"))
        for who in players:
            self.ok(self.post(who, "/api/v4/zombie/join"))
        return self.ok(self.post("architect", "/api/v4/zombie/start"))

    def sides(self) -> dict[str, str]:
        names = {pid: name for name, pid in self.ids.items()}
        return {names[int(row["account_id"])]: row["side"] for row in self.sql(
            "SELECT account_id, side FROM v4_zombie_players WHERE game_id=(SELECT MAX(id) FROM v4_zombie_games)")}

    def zombies(self):
        return sorted(name for name, side in self.sides().items() if side == "zombie")

    def humans(self):
        return sorted(name for name, side in self.sides().items() if side == "human")

    def code_of(self, who):
        return self.view(who)["game"]["me"]["code"]

    def tag(self, zombie_name, victim):
        return self.post(zombie_name, "/api/v4/zombie/tag", {"code": self.code_of(victim)})

    def infect(self, *names):
        for name in names:
            self.sql("INSERT INTO v4_virus_state(season_id, account_id, infected_until) VALUES (1, ?, ?)",
                     (self.ids[name], rooms.iso(datetime(2099, 1, 1, tzinfo=timezone.utc))))

    def stars(self, who):
        rows = self.sql("SELECT stars FROM v4_case_wallets WHERE season_id=1 AND account_id=?", (self.ids[who],))
        return int(rows[0]["stars"]) if rows else 0

    # --- старт ---------------------------------------------------------------------------

    def test_virus_carriers_start_as_zombies(self):
        self.infect("kid3")
        self.round()
        self.assertEqual(self.zombies(), ["kid3"])
        me = self.view("kid3")["game"]["me"]
        self.assertTrue(me["starter"])
        self.assertEqual(self.view("kid1")["game"]["source"], "virus")

    def test_no_more_than_a_third_start_as_zombies(self):
        self.infect("kid1", "kid2", "kid3", "kid4", "kid5")
        self.round()
        zombies = self.zombies()
        self.assertEqual(len(zombies), len(KIDS) // 3)
        self.assertTrue(set(zombies) <= {"kid1", "kid2", "kid3", "kid4", "kid5"})

    def test_a_lottery_picks_the_first_zombie_when_nobody_is_ill(self):
        self.round()
        self.assertEqual(len(self.zombies()), 1)
        self.assertEqual(self.view("kid1")["game"]["source"], "lottery")

    # --- заражение ---------------------------------------------------------------------------

    def test_a_zombie_turns_a_human_with_the_victims_code(self):
        self.round()
        z = self.zombies()[0]
        h1, h2, h3, h4 = self.humans()[:4]
        seen = self.view(z)
        self.assertNotIn("code", seen["game"]["me"])
        self.assertNotIn("grid", seen["game"])
        text = json.dumps(seen)
        for human in self.humans():
            self.assertNotIn(self.code_of(human), text)
        codes = {row["code"] for row in self.sql("SELECT code FROM v4_zombie_players")}
        wrong = next(f"{n:06d}" for n in range(1_000_000) if f"{n:06d}" not in codes)
        self.assertEqual(self.tag(z, h1).status_code, 429)   # первый зомби тоже приходит в себя: люди расходятся
        self.now += REST
        self.assertEqual(self.post(z, "/api/v4/zombie/tag", {"code": wrong}).status_code, 404)
        old_code = self.code_of(h1)
        result = self.ok(self.tag(z, h1))
        self.assertEqual(result["tagged"], h1)
        self.assertEqual(self.sides()[h1], "zombie")
        self.assertEqual(result["game"]["me"]["tags"], 1)
        self.assertEqual(self.tag(z, h2).status_code, 429)
        self.assertEqual(self.tag(h1, h2).status_code, 429)
        self.assertEqual(self.post(h3, "/api/v4/zombie/tag", {"code": self.code_of(h4)}).status_code, 409)
        self.now += REST
        self.assertEqual(self.post(z, "/api/v4/zombie/tag", {"code": old_code}).status_code, 409)
        self.ok(self.tag(h1, h2))
        self.assertEqual(self.sides()[h2], "zombie")

    def test_a_vaccine_at_a_station_brings_a_zombie_back_once(self):
        lon, lat = story.feature_centres()[capture.points()["stadium"]["feature"]]
        self.ok(self.post("architect", "/api/v4/capture/points/stadium/confirm", {"lon": lon, "lat": lat, "accuracy_m": 8}))
        self.round()
        z = self.zombies()[0]
        h = self.humans()[0]
        self.assertEqual([s["code"] for s in self.view(h)["stations"]], ["stadium"])
        self.now += REST
        old_code = self.code_of(h)
        self.ok(self.tag(z, h))
        there = dict(zip(("lon", "lat"), near("stadium")), accuracy_m=10, point="stadium")
        far = {**there, "lat": there["lat"] + 0.01}
        self.assertEqual(self.post(h, "/api/v4/zombie/vaccine/challenge", far).status_code, 400)

        self.ok(self.post(h, "/api/v4/zombie/vaccine/challenge", there))
        right = zombie.vaccines.pending[self.ids[h]]["answer"]
        miss = self.ok(self.post(h, "/api/v4/zombie/vaccine/answer", {"choice": (right + 1) % zombie.QUESTION_OPTIONS}))
        self.assertFalse(miss["vaccine"]["correct"])
        self.assertEqual(self.post(h, "/api/v4/zombie/vaccine/challenge", there).status_code, 429)

        self.now += timedelta(seconds=zombie.config()["wrong_cooldown_seconds"] + 1)
        self.ok(self.post(h, "/api/v4/zombie/vaccine/challenge", there))
        right = zombie.vaccines.pending[self.ids[h]]["answer"]
        cured = self.ok(self.post(h, "/api/v4/zombie/vaccine/answer", {"choice": right}))
        self.assertTrue(cured["vaccine"]["correct"])
        me = cured["game"]["me"]
        self.assertEqual(me["side"], "human")
        self.assertIn("immune_until", me)
        self.assertNotEqual(me["code"], old_code)
        self.assertEqual(self.post(z, "/api/v4/zombie/tag", {"code": old_code}).status_code, 404)
        self.assertEqual(self.tag(z, h).status_code, 409)

        self.now += timedelta(seconds=zombie.config()["immune_seconds"] + 1)
        self.ok(self.tag(z, h))
        self.now += REST
        self.assertEqual(self.post(h, "/api/v4/zombie/vaccine/challenge", there).status_code, 409)

    # --- конец раунда --------------------------------------------------------------------------

    def test_the_round_ends_on_time_and_pays_survivors_and_the_best_zombie(self):
        self.round()
        z = self.zombies()[0]
        h1, h2 = self.humans()[:2]
        for victim in (h1, h2):
            self.now += REST
            self.ok(self.tag(z, victim))
        survivors = self.humans()
        self.now = EVENING + timedelta(minutes=zombie.config()["round_minutes"], seconds=1)
        game = self.view(z)["game"]
        self.assertEqual(game["status"], "over")
        results = game["results"]
        self.assertEqual(results["reason"], "time")
        self.assertEqual(sorted(r["name"] for r in results["survivors"]), survivors)
        self.assertEqual([(r["name"], r["tags"]) for r in results["best_zombies"]], [(z, 2)])
        self.assertTrue(all("account_id" not in r for r in results["survivors"]))
        for name in survivors + [z]:
            self.assertEqual(self.stars(name), 10)
        for name in (h1, h2):
            self.assertEqual(self.stars(name), 0)
        self.assertTrue(self.view(survivors[0])["game"]["me"]["survived"])

        # Второй раунд в тот же день: призы уже были — не больше одного на человека.
        self.round()
        self.now += timedelta(minutes=zombie.config()["round_minutes"], seconds=1)
        results = self.view("kid1")["game"]["results"]
        self.assertTrue(any(r["limited"] for r in results["survivors"]))
        paid = self.sql("SELECT account_id, COUNT(*) AS n FROM v4_economy_operations WHERE operation='zombie.prize' "
                        "GROUP BY account_id")
        self.assertTrue(all(int(row["n"]) == 1 for row in paid))

    def test_turning_everyone_ends_the_round_early_and_small_rounds_pay_nothing(self):
        self.round(KIDS[:4])
        z = self.zombies()[0]
        for victim in self.humans():
            self.now += REST
            self.ok(self.tag(z, victim))
        game = self.view("kid1")["game"]
        self.assertEqual((game["status"], game["results"]["reason"]), ("over", "all_turned"))
        self.assertEqual(self.sql("SELECT 1 FROM v4_economy_operations WHERE operation='zombie.prize'"), [])

    def test_the_roster_is_forgotten_half_an_hour_after_the_end(self):
        self.round(KIDS[:4])
        self.ok(self.post("architect", "/api/v4/zombie/cancel"))
        self.assertTrue(self.view("kid1")["game"]["cancelled"])
        self.assertEqual(self.sql("SELECT 1 FROM v4_economy_operations WHERE operation='zombie.prize'"), [])
        self.now += timedelta(minutes=zombie.config()["keep_minutes"] + 1)
        self.assertIsNone(self.view("kid1")["game"])
        self.assertEqual(self.sql("SELECT 1 FROM v4_zombie_players"), [])

    def test_participants_cannot_host_and_small_lobbies_do_not_start(self):
        self.assertEqual(self.post("kid1", "/api/v4/zombie/create").status_code, 403)
        self.assertEqual(self.post("kid1", "/api/v4/zombie/join").status_code, 404)
        self.ok(self.post("architect", "/api/v4/zombie/create"))
        for who in KIDS[:2]:
            self.ok(self.post(who, "/api/v4/zombie/join"))
        self.assertEqual(self.post("architect", "/api/v4/zombie/start").status_code, 409)
        self.assertIn("grid", self.view("architect")["game"])


if __name__ == "__main__":
    unittest.main()
