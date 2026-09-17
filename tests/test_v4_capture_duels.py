from __future__ import annotations

import json
import tempfile
import unittest
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
MORNING = datetime(2026, 9, 12, 2, 0, tzinfo=timezone.utc)   # 10:00 по Шанхаю, окно открыто
KIDS = [f"kid{n}" for n in range(1, 7)]
CENTRE = story.feature_centres()[capture.points()["stadium"]["feature"]]
RULES = capture.config()["duels"]


class DuelTests(unittest.TestCase):
    """Дуэли Захвата кампуса (V4_GAMES.md §4.12, этап 2).

    Обещания: дуэль — только между разными фракциями, в окно и при включённой
    игре; в поединке побеждает больше верных, при равенстве быстрый; в реакции
    решает скорость; в 攻守巧 — две победы в раундах, молчание проигрывает
    раунд; победа приносит фракции бонус, а у точки — ход на точке; сдача после
    первого хода — поражение; не больше пяти дуэлей в день и не с тем же
    соперником подряд; ответы и текущий ход соперника не уходят на телефон;
    закончившиеся дуэли забываются.
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
                for name in KIDS + ["kid7"]:
                    self.ids[name] = provision_local_account(
                        conn, username=name, password=USER_PASSWORD, display_name=name.upper(),
                        role_code="participant", actor_account_id=self.bootstrap["account"]["id"])["id"]
                    if name != "kid7":
                        conn.execute("INSERT INTO v4_season_memberships(season_id, account_id, status) VALUES (1, ?, 'active')",
                                     (self.ids[name],))
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
        for name in ["architect"] + KIDS + ["kid7"]:
            client = TestClient(self.app)
            password = ADMIN_PASSWORD if name == "architect" else USER_PASSWORD
            response = client.post("/api/v4/auth/login", json={"username": name, "password": password})
            self.assertEqual(response.status_code, 200, response.text)
            self.clients[name], self.tokens[name] = client, response.json()["csrf_token"]
        self.switch(True)
        self.teams = {}
        for name in KIDS:
            self.teams.setdefault(self.clients[name].get("/api/v4/capture").json()["you"]["faction"], []).append(name)
        groups = list(self.teams.values())
        self.a, self.b, self.c = groups[0][0], groups[1][0], groups[2][0]
        self.mate = groups[0][1]
        self.faction = {name: f for f, names in self.teams.items() for name in names}

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

    def switch(self, on):
        self.assertEqual(self.post("architect", "/api/v4/capture/switch", {"enabled": on}).status_code, 200)

    def offer(self, who, **body):
        return self.post(who, "/api/v4/capture/duels/offer", body)

    def start(self, a, b, kind="quiz", **body):
        with mock.patch("zhidao_v4.duels.pick_kind", return_value=kind):
            offered = self.offer(a, **body)
            self.assertEqual(offered.status_code, 200, offered.text)
            joined = self.post(b, "/api/v4/capture/duels/join", {"code": offered.json()["code"]})
        self.assertEqual(joined.status_code, 200, joined.text)
        return joined.json()

    def state(self):
        return json.loads(self.sql("SELECT state_json FROM v4_capture_duels ORDER BY id DESC LIMIT 1")[0]["state_json"])

    def current(self, who):
        response = self.clients[who].get("/api/v4/capture/duel")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def reply(self, who, correct=True):
        state = self.state()
        item = state["items"][len(state["progress"][str(self.ids[who])]["answers"])]
        choice = item["answer"] if correct else (item["answer"] + 1) % len(item["options"])
        response = self.post(who, "/api/v4/capture/duel/answer", {"choice": choice})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def move(self, who, move):
        response = self.post(who, "/api/v4/capture/duel/move", {"move": move})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def score(self, faction):
        factions = self.clients["architect"].get("/api/v4/capture").json()["factions"]
        return next(f["score"] for f in factions if f["code"] == faction)

    # --- кто и когда ----------------------------------------------------------------------

    def test_duels_need_rivals_an_open_window_and_the_switch(self):
        code = self.offer(self.a).json()["code"]
        self.assertEqual(self.post(self.a, "/api/v4/capture/duels/join", {"code": code}).status_code, 409)
        self.assertEqual(self.post(self.mate, "/api/v4/capture/duels/join", {"code": code}).status_code, 409)
        self.assertEqual(self.post(self.b, "/api/v4/capture/duels/join", {"code": "000000"}).status_code, 404)
        self.now = MORNING + timedelta(hours=11)                    # 21:00
        self.assertEqual(self.offer(self.a).status_code, 409)
        self.now = MORNING
        self.switch(False)
        self.assertEqual(self.offer(self.a).status_code, 409)
        # Штат теперь тоже может играть (решение 2026-09-17) — architect
        # упирается в тот же выключенный переключатель, что и участник,
        # не в старое «вы не участник».
        self.assertEqual(self.offer("architect").status_code, 409)
        self.assertEqual(self.offer("kid7").status_code, 409)

    # --- виды дуэлей ---------------------------------------------------------------------

    def test_the_quiz_goes_to_more_correct_answers_and_brings_the_faction_bonus(self):
        self.start(self.a, self.b)
        for _ in range(RULES["questions"]):
            self.reply(self.a, correct=True)
            self.reply(self.b, correct=False)
        result = self.current(self.b)["duel"]["result"]
        self.assertEqual(result["result"], "lose")
        self.assertEqual(self.current(self.a)["duel"]["result"]["result"], "win")
        self.assertEqual(self.score(self.faction[self.a]), RULES["bonus"])
        self.assertEqual(self.score(self.faction[self.b]), 0)

    def test_an_equal_quiz_goes_to_the_faster(self):
        self.start(self.a, self.b)
        for _ in range(RULES["questions"]):
            self.now += timedelta(seconds=1)
            self.reply(self.a)
        for _ in range(RULES["questions"]):
            self.now += timedelta(seconds=3)
            self.reply(self.b)
        self.assertEqual(self.current(self.a)["duel"]["result"]["result"], "win")

    def test_reaction_rewards_speed(self):
        view = self.start(self.a, self.b, kind="reaction")
        self.assertEqual(len(view["duel"]["sheet"]["current"]["options"]), RULES["reaction_options"])
        self.assertIn("ru", view["duel"]["sheet"]["current"]["prompt"])
        for _ in range(RULES["questions"]):
            self.now += timedelta(milliseconds=500)
            self.reply(self.a)
        for _ in range(RULES["questions"]):
            self.now += timedelta(seconds=4)
            self.reply(self.b)
        result = self.current(self.a)["duel"]["result"]
        self.assertEqual(result["result"], "win")
        self.assertGreater(result["score"]["you"]["points"], result["score"]["rival"]["points"])

    def test_tactics_is_first_to_two_round_wins_and_ties_do_not_count(self):
        self.start(self.a, self.b, kind="tactics")
        self.move(self.a, "attack")
        after = self.move(self.b, "trick")["duel"]["tactics"]
        self.assertEqual((after["wins"], after["last"]["winner"]), ({"you": 0, "rival": 1}, "rival"))
        self.move(self.a, "defend")
        self.move(self.b, "defend")
        self.move(self.a, "defend")
        final = self.move(self.b, "attack")["duel"]
        self.assertEqual(final["status"], "done")
        self.assertEqual(final["result"]["result"], "lose")
        self.assertEqual(final["result"]["score"], {"you": 0, "rival": 2})

    def test_silence_loses_the_round_when_time_runs_out(self):
        self.start(self.a, self.b, kind="tactics")
        self.move(self.a, "attack")
        self.now += timedelta(seconds=RULES["round_seconds"] + 1)
        tactics = self.current(self.a)["duel"]["tactics"]
        self.assertEqual(tactics["wins"], {"you": 1, "rival": 0})
        self.assertEqual(tactics["round"], 2)

    def test_a_late_answer_after_the_deadline_still_records_the_result(self):
        self.start(self.a, self.b)
        self.reply(self.a)
        self.now += timedelta(seconds=RULES["sheet_seconds"] + 1)
        state = self.state()
        item = state["items"][1]
        response = self.post(self.a, "/api/v4/capture/duel/answer", {"choice": item["answer"]})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["duel"]["result"]["result"], "win")
        self.assertEqual(self.score(self.faction[self.a]), RULES["bonus"])

    # --- тайны ----------------------------------------------------------------------------

    def test_the_phone_never_sees_answers_or_the_rival_move_of_this_round(self):
        view = self.start(self.a, self.b)
        self.assertNotIn('"answer"', json.dumps(view))
        self.assertNotIn('"answer"', self.clients[self.a].get("/api/v4/capture/duel").text)
        self.post(self.a, "/api/v4/capture/duel/leave")               # до первого хода — отмена
        self.now += timedelta(seconds=1)
        self.start(self.a, self.c, kind="tactics")
        self.move(self.a, "trick")
        seen = self.clients[self.c].get("/api/v4/capture/duel").text
        self.assertNotIn("trick", seen)
        self.assertTrue(json.loads(seen)["duel"]["tactics"]["rival_moved"])

    # --- итоги ----------------------------------------------------------------------------

    def test_a_duel_at_a_point_moves_the_point_instead_of_the_bonus(self):
        self.assertEqual(self.post("architect", "/api/v4/capture/points/stadium/confirm",
                                   {"lon": CENTRE[0], "lat": CENTRE[1], "accuracy_m": 8}).status_code, 200)
        self.assertEqual(self.offer(self.a, point="stadium").status_code, 400)          # без позиции
        far = {"point": "stadium", "lon": CENTRE[0], "lat": CENTRE[1] + 0.005, "accuracy_m": 10}
        self.assertEqual(self.offer(self.a, **far).status_code, 400)
        view = self.start(self.a, self.b, point="stadium", lon=CENTRE[0], lat=CENTRE[1], accuracy_m=10)
        self.assertEqual(view["duel"]["point"]["name_zh"], "体育场")
        for _ in range(RULES["questions"]):
            self.reply(self.a)
            self.reply(self.b, correct=False)
        effect = self.current(self.a)["duel"]["result"]["effect"]
        self.assertEqual(effect, {"kind": "point", "code": "stadium", "action": "capture"})
        point = next(p for p in self.clients[self.a].get("/api/v4/capture").json()["points"] if p["code"] == "stadium")
        self.assertEqual((point["owner"], point["level"]), (self.faction[self.a], 1))
        self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM v4_capture_bonus")[0]["n"], 0)

    def test_leaving_before_a_move_cancels_and_after_a_move_forfeits(self):
        self.start(self.a, self.b)
        self.assertEqual(self.post(self.b, "/api/v4/capture/duel/leave").json()["duel"]["result"]["result"], "cancelled")
        self.assertEqual(self.score(self.faction[self.a]), 0)
        self.start(self.a, self.c)
        self.reply(self.a)
        left = self.post(self.c, "/api/v4/capture/duel/leave").json()["duel"]["result"]
        self.assertEqual((left["result"], left["forfeit"]), ("lose", "you"))
        self.assertEqual(self.score(self.faction[self.a]), RULES["bonus"])

    def test_five_duels_a_day_and_no_rematch_in_a_row(self):
        self.start(self.a, self.b)
        self.post(self.a, "/api/v4/capture/duel/leave")
        code = self.offer(self.a).json()["code"]
        self.assertEqual(self.post(self.b, "/api/v4/capture/duels/join", {"code": code}).status_code, 409)
        self.start(self.a, self.c)
        self.post(self.a, "/api/v4/capture/duel/leave")
        self.start(self.a, self.b)                                    # после другого соперника — можно
        self.post(self.a, "/api/v4/capture/duel/leave")
        self.sql("UPDATE v4_capture_duel_quota SET used=? WHERE account_id=?", (RULES["daily_limit"], self.ids[self.a]))
        self.assertEqual(self.offer(self.a).status_code, 409)
        self.assertEqual(self.current(self.a)["duels_left"], 0)
        self.now = MORNING + timedelta(days=1)
        self.assertEqual(self.offer(self.a).status_code, 200)

    def test_finished_duels_are_forgotten(self):
        self.start(self.a, self.b)
        self.post(self.b, "/api/v4/capture/duel/leave")
        self.now += timedelta(minutes=RULES["keep_minutes"] + 1)
        self.assertIsNone(self.current(self.a)["duel"])
        self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM v4_capture_duels")[0]["n"], 0)
        for table in ("v4_capture_duel_quota", "v4_capture_bonus"):
            columns = {row["name"] for row in self.sql(f"PRAGMA table_info({table})")}
            self.assertFalse({"rival_account_id", "b_account_id", "opponent"} & columns, table)


if __name__ == "__main__":
    unittest.main()
