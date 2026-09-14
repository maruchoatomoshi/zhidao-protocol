from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from zhidao_v4 import campus, story
from zhidao_v4.api import create_app
from zhidao_v4.auth import provision_local_account
from zhidao_v4.bootstrap import bootstrap_system_admin
from zhidao_v4.db import connect_database, immediate_transaction


ADMIN_PASSWORD = "correct horse battery staple"
USER_PASSWORD = "another correct horse battery"
# 10:00 по Шанхаю 12 сентября — сезон-день 2026-09-12.
MORNING = datetime(2026, 9, 12, 2, 0, tzinfo=timezone.utc)
ANSWERS = {f["code"]: f["answers"][0] for f in story.scenario()["fragments"]}
PLACES = {f["code"]: f["place"] for f in story.scenario()["fragments"] if f.get("place")}


class StoryTests(unittest.TestCase):
    """Скрытые файлы (V4_GAMES.md §4.4).

    Обещания: по фрагменту в сезон-день, но следующий открывается только после
    разгадки предыдущего, и отставшие догоняют; фрагмент на месте ждёт открытой
    клетки у настоящего объекта; ответ сверяется без учёта регистра, пробелов и
    тонов; прогресс общий, а кто решил — не хранится; правильные ответы не
    уходят на телефон; десять слов складываются в сообщение Архитектора.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "zhidao.db"
        self.bootstrap = bootstrap_system_admin(self.db_path, username="architect", password=ADMIN_PASSWORD,
                                                display_name="Архитектор")
        conn = connect_database(self.db_path)
        try:
            with immediate_transaction(conn):
                for name in ("kid1", "kid2", "kid3"):
                    account = provision_local_account(conn, username=name, password=USER_PASSWORD, display_name=name,
                                                      role_code="participant",
                                                      actor_account_id=self.bootstrap["account"]["id"])
                    if name != "kid3":
                        conn.execute("INSERT INTO v4_season_memberships(season_id, account_id, status) VALUES (1, ?, 'active')",
                                     (account["id"],))
                conn.execute("UPDATE v4_seasons SET status='active', starts_on=NULL WHERE id=1")
                # История началась 12 сентября: сдвиг часов в тестах — это «прошло N дней».
                conn.execute("INSERT INTO v4_story_state(season_id, started_day) VALUES (1, '2026-09-12')")
        finally:
            conn.close()
        self.now = MORNING
        self.clock = mock.patch("zhidao_v4.story.utcnow", side_effect=lambda: self.now)
        self.clock.start()
        self.app = create_app(self.db_path, cookie_secure=False, session_hours=1)
        self.clients, self.tokens = {}, {}
        for name, password in (("architect", ADMIN_PASSWORD), ("kid1", USER_PASSWORD), ("kid2", USER_PASSWORD),
                               ("kid3", USER_PASSWORD)):
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

    def view(self, who="kid1"):
        response = self.clients[who].get("/api/v4/story")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def answer(self, code, text, who="kid1"):
        return self.clients[who].post(f"/api/v4/story/{code}/answer", headers={"X-CSRF-Token": self.tokens[who]},
                                      json={"answer": text})

    def states(self, who="kid1"):
        return {f["code"]: f["state"] for f in self.view(who)["fragments"]}

    def open_place(self, code):
        lon, lat = story.feature_centres()[PLACES[code]]
        cell_lon, cell_lat = campus.snap(lon, lat)
        self.sql("INSERT OR IGNORE INTO v4_campus_cells(season_id, cell_lon, cell_lat) VALUES (1, ?, ?)",
                 (cell_lon + 1, cell_lat))   # соседняя клетка тоже засчитывается

    def test_one_fragment_a_day_and_the_chain_holds(self):
        self.assertEqual(self.states(), {"f01": "open"})
        self.now = MORNING + timedelta(days=1)
        self.assertEqual(self.states(), {"f01": "open", "f02": "locked_previous"})
        self.assertTrue(self.answer("f01", ANSWERS["f01"]).json()["correct"])
        self.assertEqual(self.states(), {"f01": "solved", "f02": "open"})
        self.assertEqual(self.answer("f03", "火").status_code, 404)

    def test_latecomers_catch_up_on_the_same_day(self):
        self.now = MORNING + timedelta(days=2)
        for code in ("f01", "f02", "f03"):
            response = self.answer(code, ANSWERS[code])
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(response.json()["correct"], code)
        self.assertEqual(set(self.states().values()), {"solved"})

    def test_answers_ignore_case_spaces_and_tones(self):
        for text in ("  Ни Хао ", "nǐ hǎo", "你好", "NIHAO!"):
            self.assertTrue(self.answer("f01", text, who="kid2").json()["correct"], text)
        self.assertFalse(self.answer("f02", "8").json().get("correct", False))

    def test_a_wrong_answer_changes_nothing(self):
        response = self.answer("f01", "здравствуйте")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["correct"])
        self.assertEqual(self.states(), {"f01": "open"})

    def test_progress_is_shared_and_nobody_is_recorded(self):
        self.answer("f01", ANSWERS["f01"], who="kid1")
        other = self.view("kid2")
        self.assertEqual(other["fragments"][0]["state"], "solved")
        self.assertEqual(other["message"][0], "Они")
        for table in ("v4_story_state", "v4_story_solved"):
            columns = {row["name"] for row in self.sql(f"PRAGMA table_info({table})")}
            self.assertFalse(any("account" in column for column in columns), table)

    def test_the_phone_never_receives_answers(self):
        self.now = MORNING + timedelta(days=9)
        text = self.clients["kid1"].get("/api/v4/story").text
        self.assertNotIn("answers", text)
        self.assertNotIn("nihao", text)
        self.assertNotIn("\"создана\"", text)

    def test_a_place_fragment_waits_for_the_fog_near_the_real_object(self):
        self.now = MORNING + timedelta(days=3)
        for code in ("f01", "f02", "f03"):
            self.answer(code, ANSWERS[code])
        fragment = next(f for f in self.view()["fragments"] if f["code"] == "f04")
        self.assertEqual(fragment["state"], "locked_place")
        self.assertNotIn("question", fragment)
        self.assertEqual(fragment["place"]["name_zh"], "学生食堂")
        self.assertEqual(self.answer("f04", ANSWERS["f04"]).status_code, 409)
        self.open_place("f04")
        self.assertEqual(self.states()["f04"], "open")
        self.assertTrue(self.answer("f04", "четыре").json()["correct"])

    def test_ten_words_make_the_architect_message(self):
        self.now = MORNING + timedelta(days=9)
        for code in PLACES:
            self.open_place(code)
        for code in ANSWERS:
            self.assertTrue(self.answer(code, ANSWERS[code]).json()["correct"], code)
        final = self.view("kid2")
        self.assertTrue(final["complete"])
        self.assertEqual(" ".join(final["message"]), "Они поняли механику, но не поняли, зачем она была создана.")
        self.assertIn("epilogue", final)

        # Награда всем участникам сезона: рамка и 20★, по одному разу, без следа того, кто решил.
        reward = final["reward"]
        self.assertEqual((reward["stars"], reward["frame"], reward["name_ru"], reward["received"]),
                         (20, "fr_architect", "Послание Архитектора", True))
        members = {row["account_id"] for row in self.sql("SELECT account_id FROM v4_season_memberships WHERE season_id=1")}
        journal = self.sql("SELECT account_id, actor_account_id, stars_delta FROM v4_economy_operations "
                           "WHERE operation='story.finale'")
        self.assertEqual(sorted(row["account_id"] for row in journal), sorted(members))
        self.assertTrue(all(row["actor_account_id"] == row["account_id"] and row["stars_delta"] == 20 for row in journal))
        self.assertEqual({row["account_id"] for row in self.sql(
            "SELECT account_id FROM v4_case_inventory WHERE item_code='fr_architect'")}, members)
        self.assertEqual({row["stars"] for row in self.sql(
            "SELECT stars FROM v4_case_wallets WHERE season_id=1 AND account_id IN (SELECT account_id FROM v4_season_memberships)")}, {20})
        last = list(ANSWERS)[-1]
        self.assertTrue(self.answer(last, ANSWERS[last], who="kid2").json()["already"])
        self.assertEqual(len(self.sql("SELECT 1 FROM v4_economy_operations WHERE operation='story.finale'")), len(members))
        self.assertFalse(self.view("architect")["reward"]["received"])       # вожатый не участник
        shop = self.clients["kid2"].get("/api/v4/seasons/1/shop").json()
        self.assertIn("fr_architect", [item["code"] for item in shop["cosmetics"]])

    def test_staff_can_read_but_only_members_answer_and_outsiders_see_nothing(self):
        self.assertEqual(self.view("architect")["fragments"][0]["state"], "open")
        self.assertEqual(self.answer("f01", ANSWERS["f01"], who="architect").status_code, 403)
        self.assertEqual(self.view("kid3"), {"season_id": None, "fragments": [], "message": [], "complete": False})
        self.assertEqual(self.answer("f01", ANSWERS["f01"], who="kid3").status_code, 409)

    def test_the_season_start_date_sets_the_calendar(self):
        self.sql("UPDATE v4_seasons SET starts_on='2026-09-10' WHERE id=1")
        self.assertEqual(self.view()["day"], 3)
        self.assertEqual(self.view()["released"], 3)


if __name__ == "__main__":
    unittest.main()
