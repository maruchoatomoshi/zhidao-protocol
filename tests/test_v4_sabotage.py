from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from zhidao_v4 import capture, sabotage, story
from zhidao_v4.api import create_app
from zhidao_v4.auth import provision_local_account
from zhidao_v4.bootstrap import bootstrap_system_admin
from zhidao_v4.db import connect_database, immediate_transaction


ADMIN_PASSWORD = "correct horse battery staple"
USER_PASSWORD = "another correct horse battery"
EVENING = datetime(2026, 9, 12, 11, 0, tzinfo=timezone.utc)   # 19:00 по Шанхаю
KIDS = [f"kid{n}" for n in range(1, 9)]
STATIONS = ("stadium", "canteen")
REST = timedelta(seconds=sabotage.config()["kill_cooldown_seconds"] + 1)


def near(code: str) -> dict:
    lon, lat = story.feature_centres()[capture.points()[code]["feature"]]
    return {"point": code, "lon": lon, "lat": lat + 20 / 111320, "accuracy_m": 10}


class SabotageTests(unittest.TestCase):
    """Саботаж (V4_GAMES.md §4.12).

    Обещания (решения пользователя 2026-09-13): станции — подтверждённые точки
    по GPS; саботажники только выводят — кодом с телефона жертвы; задания —
    китайский вопрос у станции; собрания созывают капитаны. Черновик Claude:
    роли и коды видит только хозяин, саботажники видят друг друга, капитанов —
    все; у капитана два собрания; ничья и «пропустить» никого не выгоняют;
    задания саботажников полосу не двигают, а полоса обновляется на собраниях;
    экипаж побеждает заданиями или выгнав саботажников, саботажники — числом
    или по времени; собрание останавливает часы; победители получают 10★ в
    играх от 8 человек, раз в день; состав удаляется через полчаса.
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
        self.names = {pid: name for name, pid in self.ids.items()}
        self.now = EVENING
        self.clock = mock.patch("zhidao_v4.sabotage.utcnow", side_effect=lambda: self.now)
        self.clock.start()
        sabotage.questions = sabotage.TaskQuestions()
        self.app = create_app(self.db_path, cookie_secure=False, session_hours=1)
        self.clients, self.tokens = {}, {}
        for name in ["architect"] + KIDS:
            client = TestClient(self.app)
            password = ADMIN_PASSWORD if name == "architect" else USER_PASSWORD
            response = client.post("/api/v4/auth/login", json={"username": name, "password": password})
            self.assertEqual(response.status_code, 200, response.text)
            self.clients[name], self.tokens[name] = client, response.json()["csrf_token"]
        for code in STATIONS:
            lon, lat = story.feature_centres()[capture.points()[code]["feature"]]
            self.ok(self.post("architect", f"/api/v4/capture/points/{code}/confirm", {"lon": lon, "lat": lat, "accuracy_m": 8}))

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
        return self.ok(self.clients[who].get("/api/v4/sabotage"))

    def me(self, who):
        return self.view(who)["game"]["me"]

    def game(self, players=KIDS):
        self.ok(self.post("architect", "/api/v4/sabotage/create"))
        for who in players:
            self.ok(self.post(who, "/api/v4/sabotage/join"))
        return self.ok(self.post("architect", "/api/v4/sabotage/start"))

    def rows(self):
        return {self.names[int(row["account_id"])]: row for row in self.sql(
            "SELECT * FROM v4_sabotage_players WHERE game_id=(SELECT MAX(id) FROM v4_sabotage_games)")}

    def saboteurs(self):
        return sorted(n for n, r in self.rows().items() if r["role"] == "saboteur")

    def crew(self, captains=True):
        return sorted(n for n, r in self.rows().items() if r["role"] == "crew" and (captains or not r["captain"]))

    def captains(self):
        return sorted(n for n, r in self.rows().items() if r["captain"])

    def eliminate(self, saboteur, victim):
        return self.post(saboteur, "/api/v4/sabotage/eliminate", {"code": self.rows()[victim]["code"]})

    def do_task(self, who, point, correct=True):
        self.ok(self.post(who, "/api/v4/sabotage/task/challenge", near(point)))
        right = sabotage.questions.pending[self.ids[who]]["answer"]
        choice = right if correct else (right + 1) % sabotage.QUESTION_OPTIONS
        return self.ok(self.post(who, "/api/v4/sabotage/task/answer", {"choice": choice}))

    def vote_all(self, choices: dict[str, int]):
        for who, choice in choices.items():
            self.ok(self.post(who, "/api/v4/sabotage/vote", {"choice": choice}))

    def stars(self, who):
        rows = self.sql("SELECT stars FROM v4_case_wallets WHERE season_id=1 AND account_id=?", (self.ids[who],))
        return int(rows[0]["stars"]) if rows else 0

    # --- роли ------------------------------------------------------------------------------

    def test_roles_stay_secret_and_saboteurs_see_each_other(self):
        with mock.patch.dict(sabotage.config(), {"saboteur_per": 4}):
            self.game()
        saboteurs = self.saboteurs()
        self.assertEqual(len(saboteurs), 2)
        for s in saboteurs:
            self.assertEqual(self.me(s)["allies"], [x for x in saboteurs if x != s])
        captains = self.captains()
        self.assertTrue(captains and set(captains) <= set(self.crew()))
        for c in self.crew():
            seen = self.view(c)
            text = json.dumps(seen)
            self.assertNotIn("saboteur", text)
            self.assertNotIn("grid", seen["game"])
            self.assertEqual(seen["game"]["captains"], captains)
            for other in KIDS:
                if other != c:
                    self.assertNotIn(self.rows()[other]["code"], text)
        self.assertEqual(len(self.view("architect")["game"]["grid"]), len(KIDS))

    def test_a_saboteur_takes_out_crew_with_their_code(self):
        self.game()
        s = self.saboteurs()[0]
        c1, c2 = self.crew()[:2]
        self.assertEqual(self.eliminate(s, c1).status_code, 429)
        self.now += REST
        self.assertEqual(self.post(c2, "/api/v4/sabotage/eliminate", {"code": self.rows()[c1]["code"]}).status_code, 409)
        codes = {r["code"] for r in self.rows().values()}
        wrong = next(f"{n:06d}" for n in range(1_000_000) if f"{n:06d}" not in codes)
        self.assertEqual(self.post(s, "/api/v4/sabotage/eliminate", {"code": wrong}).status_code, 404)
        result = self.ok(self.eliminate(s, c1))
        self.assertEqual(result["eliminated"], c1)
        ghost = self.me(c1)
        self.assertFalse(ghost["alive"])
        self.assertNotIn("code", ghost)
        self.assertEqual(self.eliminate(s, c2).status_code, 429)
        self.now += REST
        self.assertEqual(self.eliminate(s, c1).status_code, 404)

    # --- задания и собрания --------------------------------------------------------------------

    def test_tasks_count_only_for_crew_and_the_bar_moves_at_meetings(self):
        self.game()
        s = self.saboteurs()[0]
        c = self.crew(captains=False)[0]
        cap = self.captains()[0]
        first, second = [t["code"] for t in self.me(c)["tasks"]]
        self.assertTrue(self.do_task(c, first)["task"]["correct"])
        self.assertEqual([t["done"] for t in self.me(c)["tasks"]], [True, False])
        fake = self.me(s)["tasks"][0]["code"]
        self.do_task(s, fake)
        self.assertTrue(self.me(s)["tasks"][0]["done"])
        self.assertEqual(self.view(c)["game"]["bar"], 0)
        self.assertFalse(self.do_task(c, second, correct=False)["task"]["correct"])
        self.assertEqual(self.post(c, "/api/v4/sabotage/task/challenge", near(second)).status_code, 429)

        self.ok(self.post(cap, "/api/v4/sabotage/meeting"))
        self.vote_all({who: 0 for who in KIDS})
        game = self.view(c)["game"]
        self.assertEqual(game["status"], "running")
        total = sum(len(json.loads(r["tasks_json"])) for r in self.rows().values() if r["role"] == "crew")
        self.assertEqual(game["bar"], round(100 / total))

    def test_only_captains_call_meetings_and_a_vote_ejects_the_saboteur(self):
        self.game()
        s = self.saboteurs()[0]
        cap = self.captains()[0]
        plain = self.crew(captains=False)[0]
        self.assertEqual(self.post(plain, "/api/v4/sabotage/meeting").status_code, 409)
        self.assertEqual(self.post(s, "/api/v4/sabotage/meeting").status_code, 409)
        self.ok(self.post(cap, "/api/v4/sabotage/meeting"))
        meeting = self.view(plain)["game"]["meeting"]
        self.assertEqual((meeting["caller"], meeting["voters"]), (cap, len(KIDS)))
        self.now += REST
        self.assertEqual(self.eliminate(s, plain).status_code, 409)
        self.assertEqual(self.post(plain, "/api/v4/sabotage/task/challenge", near(STATIONS[0])).status_code, 409)
        self.vote_all({who: self.ids[s] for who in KIDS})
        game = self.view(plain)["game"]
        self.assertEqual(game["status"], "over")
        results = game["results"]
        self.assertEqual((results["winner"], results["reason"]), ("crew", "ejected"))
        self.assertEqual(results["saboteurs"], [s])
        self.assertEqual(results["history"][0]["ejected"], s)
        self.assertTrue(results["history"][0]["was_saboteur"])
        for who in self.crew():
            self.assertEqual(self.stars(who), 10)
        self.assertEqual(self.stars(s), 0)
        self.assertEqual(self.sql("SELECT 1 FROM v4_sabotage_votes"), [])

    def test_a_tie_ejects_nobody_and_a_captain_has_two_meetings(self):
        self.game()
        cap = self.captains()[0]
        a, b = self.crew(captains=False)[:2]
        self.ok(self.post(cap, "/api/v4/sabotage/meeting"))
        self.vote_all({who: self.ids[a] if i % 2 == 0 else self.ids[b] for i, who in enumerate(KIDS)})
        game = self.view(cap)["game"]
        self.assertEqual(game["status"], "running")
        self.assertIsNone(game["history"][0]["ejected"])
        self.assertTrue(all(r["alive"] for r in self.rows().values()))
        self.ok(self.post(cap, "/api/v4/sabotage/meeting"))
        self.vote_all({who: 0 for who in KIDS})
        self.assertEqual(self.post(cap, "/api/v4/sabotage/meeting").status_code, 409)

    # --- победы --------------------------------------------------------------------------------

    def test_saboteurs_win_when_they_match_the_crew(self):
        self.game(KIDS[:5])
        s = self.saboteurs()[0]
        for victim in self.crew()[:3]:
            self.now += REST
            self.ok(self.eliminate(s, victim))
        results = self.view(s)["game"]["results"]
        self.assertEqual((results["winner"], results["reason"]), ("saboteurs", "parity"))
        self.assertEqual(self.sql("SELECT 1 FROM v4_economy_operations WHERE operation='sabotage.prize'"), [])

    def test_the_crew_wins_by_finishing_every_task(self):
        self.game(KIDS[:5])
        for who in self.crew():
            for task in self.me(who)["tasks"]:
                self.do_task(who, task["code"])
        results = self.view(KIDS[0])["game"]["results"]
        self.assertEqual((results["winner"], results["reason"]), ("crew", "tasks"))

    def test_time_runs_out_for_the_crew_but_meetings_pause_the_clock(self):
        self.game(KIDS[:5])
        cap = self.captains()[0]
        self.now = EVENING + timedelta(minutes=10)
        self.ok(self.post(cap, "/api/v4/sabotage/meeting"))
        pause = sabotage.config()["meeting_seconds"] + 1
        self.now += timedelta(seconds=pause)
        self.assertEqual(self.view(cap)["game"]["status"], "running")
        end = EVENING + timedelta(minutes=sabotage.config()["round_minutes"])
        self.now = end + timedelta(seconds=pause - 30)
        self.assertEqual(self.view(cap)["game"]["status"], "running")
        self.now = end + timedelta(seconds=pause + 1)
        results = self.view(cap)["game"]["results"]
        self.assertEqual((results["winner"], results["reason"]), ("saboteurs", "time"))

    # --- вожатый и память -----------------------------------------------------------------------

    def test_start_needs_stations_and_the_roster_is_forgotten(self):
        self.assertEqual(self.post("kid1", "/api/v4/sabotage/create").status_code, 403)
        self.sql("DELETE FROM v4_capture_points")
        self.ok(self.post("architect", "/api/v4/sabotage/create"))
        for who in KIDS[:5]:
            self.ok(self.post(who, "/api/v4/sabotage/join"))
        self.assertEqual(self.post("architect", "/api/v4/sabotage/start").status_code, 409)
        self.ok(self.post("architect", "/api/v4/sabotage/cancel"))
        self.assertTrue(self.view("kid1")["game"]["cancelled"])
        self.now += timedelta(minutes=sabotage.config()["keep_minutes"] + 1)
        self.assertIsNone(self.view("kid1")["game"])
        self.assertEqual(self.sql("SELECT 1 FROM v4_sabotage_players"), [])


if __name__ == "__main__":
    unittest.main()
