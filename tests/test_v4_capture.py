from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from zhidao_v4 import capture, story
from zhidao_v4.api import create_app
from zhidao_v4.auth import provision_local_account
from zhidao_v4.bootstrap import bootstrap_system_admin
from zhidao_v4.db import connect_database, immediate_transaction


ADMIN_PASSWORD = "correct horse battery staple"
USER_PASSWORD = "another correct horse battery"
# 10:00 по Шанхаю 12 сентября — окно захвата 10–12 открыто.
MORNING = datetime(2026, 9, 12, 2, 0, tzinfo=timezone.utc)
KIDS = [f"kid{n}" for n in range(1, 7)]
CENTRE = story.feature_centres()[capture.points()["stadium"]["feature"]]
REST = timedelta(seconds=capture.config()["cooldown_seconds"] + 1)


def north(metres: float) -> tuple[float, float]:
    return CENTRE[0], CENTRE[1] + metres / 111320


class CaptureTests(unittest.TestCase):
    """Захват кампуса (V4_GAMES.md §4.12).

    Обещания: фракции выдаёт сервер поровну и навсегда; точка появляется у
    участников только после подтверждения вожатым на месте; ход — только при
    включённой игре, в дневное окно и у самой точки; правильный ответ
    захватывает ничью, укрепляет свою до третьего уровня, пробивает чужую и с
    первого уровня перехватывает; ошибка ничего не меняет, но даёт паузу;
    очки идут только в окна и замирают при выключении; кто ходил, не хранится;
    правильный ответ не уходит на телефон.
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
                        conn, username=name, password=USER_PASSWORD, display_name=name, role_code="participant",
                        actor_account_id=self.bootstrap["account"]["id"])["id"]
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
        self.app = create_app(self.db_path, cookie_secure=False, session_hours=1)
        self.clients, self.tokens = {}, {}
        for name in ["architect"] + KIDS + ["kid7"]:
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

    def sql(self, query, values=()):
        conn = connect_database(self.db_path)
        try:
            with immediate_transaction(conn):
                return conn.execute(query, values).fetchall()
        finally:
            conn.close()

    def post(self, who, path, body=None):
        return self.clients[who].post(path, headers={"X-CSRF-Token": self.tokens[who]}, json=body or {})

    def view(self, who="kid1"):
        response = self.clients[who].get("/api/v4/capture")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def confirm(self, point="stadium", at=CENTRE, accuracy=8.0, who="architect"):
        return self.post(who, f"/api/v4/capture/points/{point}/confirm",
                         {"lon": at[0], "lat": at[1], "accuracy_m": accuracy})

    def switch(self, on=True):
        response = self.post("architect", "/api/v4/capture/switch", {"enabled": on})
        self.assertEqual(response.status_code, 200, response.text)

    def challenge(self, who, point="stadium", at=None, accuracy=10.0):
        lon, lat = at or north(20)
        return self.post(who, f"/api/v4/capture/points/{point}/challenge", {"lon": lon, "lat": lat, "accuracy_m": accuracy})

    def answer(self, who, point="stadium", correct=True):
        right = capture.challenges.pending[(self.ids[who], point)]["answer"]
        choice = right if correct else (right + 1) % capture.QUESTION_OPTIONS
        return self.post(who, f"/api/v4/capture/points/{point}/answer", {"choice": choice})

    def play(self, who, point="stadium", correct=True):
        response = self.challenge(who, point)
        self.assertEqual(response.status_code, 200, response.text)
        result = self.answer(who, point, correct)
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def ready(self):
        self.assertEqual(self.confirm().status_code, 200)
        self.switch(True)

    def rivals(self):
        for name in KIDS:
            self.view(name)
        by_faction = {}
        for name in KIDS:
            faction = self.sql("SELECT faction FROM v4_capture_factions WHERE account_id=?", (self.ids[name],))[0]["faction"]
            by_faction.setdefault(faction, []).append(name)
        (fa, a), (fb, b) = list(by_faction.items())[:2]
        return (a[0], fa), (b[0], fb)

    def point(self, who="kid1", code="stadium"):
        return next(p for p in self.view(who)["points"] if p["code"] == code)

    def score(self, faction):
        return next(f["score"] for f in self.view("architect")["factions"] if f["code"] == faction)

    # --- фракции и точки ----------------------------------------------------------------

    def test_factions_are_dealt_evenly_and_stick(self):
        first = {name: self.view(name)["you"]["faction"] for name in KIDS}
        counts = {code: list(first.values()).count(code) for code in capture.factions()}
        self.assertEqual(sorted(counts.values()), [2, 2, 2])
        self.assertEqual({name: self.view(name)["you"]["faction"] for name in KIDS}, first)
        self.assertIsNone(self.view("architect")["you"])

    def test_points_appear_only_after_staff_confirms_them_on_site(self):
        self.assertEqual(self.view("kid1")["points"], [])
        staff = self.view("architect")["points"]
        self.assertEqual(len(staff), len(capture.points()))
        self.assertFalse(any(p["confirmed"] for p in staff))
        self.assertEqual(self.confirm(who="kid1").status_code, 403)
        self.assertEqual(self.confirm(accuracy=50.0).status_code, 400)
        self.assertEqual(self.confirm(at=north(1000)).status_code, 400)
        self.assertEqual(self.confirm(point="nowhere").status_code, 404)
        self.assertEqual(self.confirm(at=north(15)).status_code, 200)
        points = self.view("kid1")["points"]
        self.assertEqual([p["code"] for p in points], ["stadium"])
        self.assertEqual(points[0]["name_zh"], "体育场")

    def test_a_move_needs_the_switch_the_window_and_being_there(self):
        self.assertEqual(self.confirm().status_code, 200)
        self.assertEqual(self.challenge("kid1").status_code, 409)          # игра выключена
        self.switch(True)
        self.now = MORNING + timedelta(hours=11)                            # 21:00 — окно закрыто
        self.assertEqual(self.challenge("kid1").status_code, 409)
        self.now = MORNING
        self.assertEqual(self.challenge("kid1", at=north(150)).status_code, 400)
        self.assertEqual(self.challenge("kid1", accuracy=250.0).status_code, 400)
        self.assertEqual(self.challenge("kid1", point="canteen").status_code, 404)   # не подтверждена
        response = self.challenge("kid1", at=north(40))
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["action"], "capture")
        self.assertEqual(set(body["question"]), {"zh", "pinyin", "options"})
        self.assertNotIn("answer", response.text)

    def test_capture_reinforce_then_a_rival_breaks_through_and_takes_it(self):
        self.ready()
        (a, fa), (b, fb) = self.rivals()
        self.assertEqual(self.play(a)["action"], "capture")
        for level in (2, 3):
            self.now += REST
            result = self.play(a)
            self.assertEqual((result["action"], result["point"]["level"]), ("reinforce", level))
        self.now += REST
        self.assertEqual(self.challenge(a).status_code, 409)                # укреплена до предела
        self.assertEqual(self.point(b)["action"], "attack")
        for level in (2, 1):
            result = self.play(b)
            self.assertEqual((result["action"], result["point"]["owner"], result["point"]["level"]), ("attack", fa, level))
            self.now += REST
        result = self.play(b)
        self.assertEqual((result["action"], result["point"]["owner"], result["point"]["level"]), ("flip", fb, 1))

    def test_a_wrong_answer_changes_nothing_and_makes_you_wait(self):
        self.ready()
        result = self.play("kid1", correct=False)
        self.assertFalse(result["correct"])
        self.assertIsNone(self.point()["owner"])
        self.assertEqual(self.challenge("kid1").status_code, 429)
        self.now += REST
        self.assertEqual(self.challenge("kid1").status_code, 200)

    def test_a_late_answer_is_refused(self):
        self.ready()
        self.assertEqual(self.challenge("kid1").status_code, 200)
        self.now += timedelta(seconds=capture.config()["question_seconds"] + 1)
        self.assertEqual(self.answer("kid1").status_code, 409)
        self.assertIsNone(self.point()["owner"])

    # --- очки ------------------------------------------------------------------------------

    def test_points_score_only_inside_windows_and_freeze_when_switched_off(self):
        self.ready()
        faction = self.view("kid1")["you"]["faction"]
        self.play("kid1")                                                   # 10:00
        self.now = MORNING + timedelta(minutes=30)
        self.assertEqual(self.score(faction), 3)
        self.now = MORNING + timedelta(hours=3)                             # 13:00, окно 10–12 прошло
        self.assertEqual(self.score(faction), 12)
        self.now = MORNING + timedelta(hours=5, minutes=30)                 # 15:30
        self.assertEqual(self.score(faction), 15)
        self.switch(False)
        self.now = MORNING + timedelta(hours=6, minutes=30)
        self.assertEqual(self.score(faction), 15)
        self.switch(True)
        self.now = MORNING + timedelta(hours=7)                             # 17:00
        self.assertEqual(self.score(faction), 18)

    # --- приватность и доступ ---------------------------------------------------------------

    def test_points_and_holds_belong_to_factions_not_people(self):
        self.ready()
        self.play("kid1")
        for table in ("v4_capture_points", "v4_capture_holds"):
            columns = {row["name"] for row in self.sql(f"PRAGMA table_info({table})")}
            self.assertFalse(any("account" in column for column in columns), table)
        # Чужие фракции и авторы ходов не уходят на телефон: только своя фракция и итоги.
        seen = self.clients["kid2"].get("/api/v4/capture").text
        self.assertNotIn("account", seen)
        self.assertNotIn("kid1", seen)

    def test_an_outsider_sees_nothing_and_cannot_play(self):
        self.ready()
        self.assertEqual(self.view("kid7"),
                         {"season_id": None, "points": [], "factions": [], "you": None, "can_manage": False})
        self.assertEqual(self.challenge("kid7").status_code, 409)


if __name__ == "__main__":
    unittest.main()
