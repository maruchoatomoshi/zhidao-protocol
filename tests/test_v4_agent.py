from __future__ import annotations

import json
import tempfile
import unittest
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
MORNING = datetime(2026, 9, 12, 2, 0, tzinfo=timezone.utc)   # 10:00 по Шанхаю
KIDS = [f"kid{n}" for n in range(1, 6)]


class AgentTests(unittest.TestCase):
    """Тайный агент (V4_GAMES.md §4.12).

    Обещания (решения пользователя 2026-09-13 и черновик, одобренный «пока
    окей»): у каждого вступившего одна тайная цель и один охотник; круг не
    собирается, пока агентов меньше минимума; на телефон уходит только своя
    цель и вопрос от своего агента; миссия с подтверждением засчитывается
    ответом цели «да», «нет» оставляет миссию и копит отказы для вожатого;
    автоматические миссии (рукопожатие, стол) засчитываются сами и цель не
    узнаёт; миссия +3 очка и новая цель, 5★ — не больше двух миссий в день;
    раз в день можно назвать охотника: угадал +2, ошибся −1; раскрывшегося
    агента назвать ради очков нельзя; в 07:00 круг пересобирается без
    вчерашних целей; вышедший пропадает из круга и из базы; итоги смены дают
    лучшему рамку и оставляют только таблицу мест.
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
        self.now = MORNING
        self.clock = mock.patch("zhidao_v4.agent.utcnow", side_effect=lambda: self.now)
        self.clock.start()
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
        return self.ok(self.clients[who].get("/api/v4/agent"))

    def begin(self, players=KIDS):
        for who in players:
            self.ok(self.post(who, "/api/v4/agent/join"))
        self.ok(self.post("architect", "/api/v4/agent/start"))

    def circle(self) -> dict[str, str]:
        return {self.names[int(row["agent_account_id"])]: self.names[int(row["target_account_id"])]
                for row in self.sql("SELECT agent_account_id, target_account_id FROM v4_agent_links")}

    def hunter_of(self, who):
        return next(agent for agent, target in self.circle().items() if target == who)

    def set_mission(self, who, code):
        self.sql("UPDATE v4_agent_links SET mission=? WHERE agent_account_id=?", (code, self.ids[who]))

    def stars(self, who):
        rows = self.sql("SELECT stars FROM v4_case_wallets WHERE season_id=1 AND account_id=?", (self.ids[who],))
        return int(rows[0]["stars"]) if rows else 0

    def assertCircle(self, players):
        circle = self.circle()
        self.assertEqual(set(circle), set(players))
        self.assertEqual(sorted(circle.values()), sorted(players))
        self.assertTrue(all(agent != target for agent, target in circle.items()))

    def catch(self, agent, code="xiexie"):
        target = self.circle()[agent]
        self.set_mission(agent, code)
        self.ok(self.post(agent, "/api/v4/agent/ask"))
        self.ok(self.post(target, "/api/v4/agent/answer", {"yes": True}))
        return target

    # --- круг ----------------------------------------------------------------------------

    def test_everyone_gets_one_secret_target_and_sees_nobody_elses(self):
        self.begin()
        self.assertCircle(KIDS)
        circle = self.circle()
        for who in KIDS:
            seen = self.view(who)
            self.assertEqual(seen["target"]["name"], circle[who])
            self.assertIsNone(seen["incoming"])
            self.assertNotIn("staff", seen)
            text = json.dumps(seen, ensure_ascii=False)
            self.assertNotIn("target_account_id", text)
            self.assertNotIn("refusals", text)
        staff = self.view("architect")
        self.assertIsNone(staff["target"])
        self.assertNotIn("target_account_id", json.dumps(staff))

    def test_the_circle_waits_for_enough_agents(self):
        self.begin(KIDS[:3])
        self.assertEqual(self.circle(), {})
        self.assertIsNone(self.view("kid1")["target"])
        self.ok(self.post("kid4", "/api/v4/agent/join"))
        self.assertCircle(KIDS[:4])

    # --- миссии --------------------------------------------------------------------------

    def test_a_confirmed_mission_pays_points_and_stars_and_brings_a_new_target(self):
        self.begin()
        target = self.circle()["kid1"]
        self.set_mission("kid1", "xiexie")
        self.ok(self.post("kid1", "/api/v4/agent/ask"))
        self.assertTrue(self.view("kid1")["target"]["asking"])
        self.assertEqual(self.post("kid1", "/api/v4/agent/ask").status_code, 409)
        incoming = self.view(target)["incoming"]
        self.assertEqual(incoming["agent"], "kid1")
        self.assertIn("谢谢", incoming["mission_text"])
        self.ok(self.post(target, "/api/v4/agent/answer", {"yes": True}))
        you = self.view("kid1")["you"]
        self.assertEqual((you["points"], you["missions"], you["stars_today"]), (3, 1, 1))
        self.assertEqual(self.stars("kid1"), 5)
        self.assertNotEqual(self.circle()["kid1"], target)
        self.assertCircle(KIDS)
        journal = self.sql("SELECT details_json FROM v4_economy_operations WHERE operation='agent.mission'")
        self.assertEqual(len(journal), 1)
        self.assertEqual(set(json.loads(journal[0]["details_json"])), {"day", "mission"})

    def test_a_refusal_keeps_the_mission_and_only_staff_sees_the_count(self):
        self.begin()
        target = self.circle()["kid1"]
        self.set_mission("kid1", "teach")
        for _ in range(3):
            self.ok(self.post("kid1", "/api/v4/agent/ask"))
            self.ok(self.post(target, "/api/v4/agent/answer", {"yes": False}))
        self.assertEqual(self.post("kid1", "/api/v4/agent/ask").status_code, 429)
        seen = self.view("kid1")
        self.assertEqual((seen["you"]["points"], seen["target"]["name"]), (0, target))
        self.assertEqual(seen["you"]["news"]["kind"], "refused")
        staff = {p["name"]: p for p in self.view("architect")["staff"]["players"]}
        self.assertEqual(staff["kid1"]["refusals"], 3)

    def test_only_two_missions_a_day_pay_stars(self):
        self.begin()
        for _ in range(3):
            self.catch("kid1")
        you = self.view("kid1")["you"]
        self.assertEqual((you["points"], you["missions"], you["stars_today"]), (9, 3, 2))
        self.assertEqual(self.stars("kid1"), 10)
        self.now += timedelta(days=1)
        self.view("kid1")
        self.catch("kid1")
        self.assertEqual(self.stars("kid1"), 15)

    def test_a_handshake_mission_counts_by_itself_and_the_target_does_not_learn(self):
        self.begin()
        target = self.circle()["kid1"]
        self.set_mission("kid1", "handshake")
        offer = self.ok(self.post(target, "/api/v4/seasons/1/meet/offer"))
        self.ok(self.post("kid1", "/api/v4/seasons/1/meet/accept", {"code": offer["code"]}))
        self.assertEqual(self.view("kid1")["you"]["points"], 3)
        seen = self.view(target)
        self.assertIsNone(seen["incoming"])
        self.assertIsNone(seen["you"]["news"])

    def test_playing_at_one_table_counts_the_room_mission(self):
        self.begin()
        self.sql("UPDATE v4_agent_links SET mission='xiexie'")
        target = self.circle()["kid1"]
        self.set_mission("kid1", "room")
        third = next(k for k in KIDS if k not in ("kid1", target))
        code = self.ok(self.post("kid1", "/api/v4/games/rooms", {"game": "smuggle"}))["room"]["code"]
        for who in (target, third):
            self.ok(self.post(who, "/api/v4/games/rooms/join", {"code": code}))
        self.assertEqual(self.view("kid1")["you"]["points"], 0)
        self.ok(self.post("kid1", f"/api/v4/games/rooms/{code}/smuggle/start"))
        self.assertEqual(self.view("kid1")["you"]["points"], 3)

    def test_missions_do_not_count_at_night(self):
        self.begin()
        target = self.circle()["kid1"]
        self.set_mission("kid1", "nihao")
        self.now = MORNING.replace(hour=14)   # 22:00 по Шанхаю
        self.assertEqual(self.post("kid1", "/api/v4/agent/ask").status_code, 409)
        self.assertIsNone(self.view(target)["incoming"])

    # --- раскрытие -------------------------------------------------------------------------

    def test_naming_your_hunter_once_a_day(self):
        self.begin()
        self.sql("UPDATE v4_agent_players SET points=5 WHERE account_id=?", (self.ids["kid1"],))
        hunter = self.hunter_of("kid1")
        wrong = next(k for k in KIDS if k not in ("kid1", hunter))
        self.ok(self.post("kid1", "/api/v4/agent/guess", {"suspect": self.ids[wrong]}))
        self.assertEqual(self.view("kid1")["you"]["points"], 4)
        self.assertEqual(self.post("kid1", "/api/v4/agent/guess", {"suspect": self.ids[hunter]}).status_code, 409)

        self.now += timedelta(days=1)
        self.view("kid1")
        hunter = self.hunter_of("kid1")
        self.ok(self.post("kid1", "/api/v4/agent/guess", {"suspect": self.ids[hunter]}))
        you = self.view("kid1")["you"]
        self.assertEqual((you["points"], you["reveals"]), (6, 1))
        self.assertNotEqual(self.circle()[hunter], "kid1")
        self.assertCircle(KIDS)
        self.assertEqual(self.view(hunter)["you"]["news"]["kind"], "exposed")

    def test_an_agent_who_asked_cannot_be_named_for_points(self):
        self.begin()
        hunter = self.hunter_of("kid1")
        self.set_mission(hunter, "meal")
        self.ok(self.post(hunter, "/api/v4/agent/ask"))
        self.assertEqual(self.post("kid1", "/api/v4/agent/guess", {"suspect": self.ids[hunter]}).status_code, 409)
        self.assertFalse(self.view("kid1")["you"]["guess_used"])

    # --- день, выход, итоги ------------------------------------------------------------------

    def test_the_circle_changes_at_seven_without_yesterdays_targets(self):
        self.begin()
        before = self.circle()
        self.now = datetime(2026, 9, 12, 22, 30, tzinfo=timezone.utc)   # 06:30 следующего утра
        self.view("kid2")
        self.assertEqual(self.circle(), before)
        self.now = datetime(2026, 9, 12, 23, 30, tzinfo=timezone.utc)   # 07:30
        self.view("kid2")
        after = self.circle()
        self.assertCircle(KIDS)
        self.assertTrue(all(after[agent] != before[agent] for agent in KIDS))

    def test_leaving_repairs_the_circle_and_forgets_the_player(self):
        self.begin()
        self.ok(self.post("kid3", "/api/v4/agent/leave"))
        self.assertCircle([k for k in KIDS if k != "kid3"])
        self.assertEqual(self.sql("SELECT 1 FROM v4_agent_players WHERE account_id=?", (self.ids["kid3"],)), [])
        seen = self.view("kid3")
        self.assertIsNone(seen["you"])
        self.assertIsNone(seen["target"])

    def test_staff_can_exclude_and_participants_cannot_manage(self):
        self.begin()
        self.assertEqual(self.post("kid1", "/api/v4/agent/finish").status_code, 403)
        self.assertEqual(self.post("kid1", "/api/v4/agent/exclude", {"account_id": self.ids["kid2"]}).status_code, 403)
        self.ok(self.post("architect", "/api/v4/agent/exclude", {"account_id": self.ids["kid2"]}))
        self.assertCircle([k for k in KIDS if k != "kid2"])
        self.assertEqual(self.post("kid2", "/api/v4/agent/join").status_code, 403)
        self.assertTrue(self.view("kid2")["you"]["excluded"])

    def test_finishing_the_shift_awards_the_frame_and_keeps_only_the_rating(self):
        self.begin()
        self.sql("UPDATE v4_agent_players SET points=9 WHERE account_id=?", (self.ids["kid1"],))
        self.sql("UPDATE v4_agent_players SET points=4 WHERE account_id=?", (self.ids["kid2"],))
        self.ok(self.post("architect", "/api/v4/agent/finish"))
        frames = {self.names[int(row["account_id"])] for row in self.sql(
            "SELECT account_id FROM v4_case_inventory WHERE item_code='fr_agent'")}
        self.assertEqual(frames, {"kid1"})
        self.assertEqual(self.sql("SELECT 1 FROM v4_agent_links"), [])
        self.assertEqual(self.sql("SELECT 1 FROM v4_agent_players"), [])
        seen = self.view("kid1")
        self.assertFalse(seen["running"])
        self.assertEqual(seen["shift"], 2)
        self.assertEqual(seen["shifts"][0]["results"][0], {"place": 1, "name": "kid1", "points": 9, "missions": 0,
                                                            "reveals": 0, "best": True})
        self.assertEqual(self.post("architect", "/api/v4/agent/finish").status_code, 409)


if __name__ == "__main__":
    unittest.main()
