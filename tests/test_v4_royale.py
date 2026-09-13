from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from zhidao_v4 import royale
from zhidao_v4.api import create_app
from zhidao_v4.auth import provision_local_account
from zhidao_v4.bootstrap import bootstrap_system_admin
from zhidao_v4.db import connect_database, immediate_transaction


ADMIN_PASSWORD = "correct horse battery staple"
USER_PASSWORD = "another correct horse battery"
EVENING = datetime(2026, 9, 12, 11, 0, tzinfo=timezone.utc)   # 19:00 по Шанхаю
KIDS = [f"kid{n:02d}" for n in range(1, 13)]
WALLET = 50
RULES = royale.config()


class RoyaleTests(unittest.TestCase):
    """Протокол 60 (V4_GAMES.md §4.12).

    Обещания (решения пользователя 2026-09-13): лобби открывает только вожатый,
    входят участники сезона; ошибка или молчание — выбыл; правильный вариант не
    уходит на телефон до разбора; воскрешение 15★ — один раз и только пока в
    игре больше половины; выбывшие голосуют за сюрприз следующего раунда;
    последний выживший побеждает, топ-3 получают 30/20/10★ и REP — в играх от
    десяти участников и не чаще раза в день; остановка возвращает воскрешения;
    состав и ответы забываются через полчаса после конца.
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
                for name in KIDS + ["outsider"]:
                    self.ids[name] = provision_local_account(
                        conn, username=name, password=USER_PASSWORD, display_name=name.upper(),
                        role_code="participant", actor_account_id=self.bootstrap["account"]["id"])["id"]
                    if name != "outsider":
                        conn.execute("INSERT INTO v4_season_memberships(season_id, account_id, status) VALUES (1, ?, 'active')",
                                     (self.ids[name],))
                        conn.execute("INSERT INTO v4_case_wallets(season_id, account_id, stars) VALUES (1, ?, ?)",
                                     (self.ids[name], WALLET))
                conn.execute("UPDATE v4_seasons SET status='active' WHERE id=1")
        finally:
            conn.close()
        self.now = EVENING
        self.clock = mock.patch("zhidao_v4.royale.utcnow", side_effect=lambda: self.now)
        self.clock.start()
        self.app = create_app(self.db_path, cookie_secure=False, session_hours=1)
        self.clients, self.tokens = {}, {}
        for name in ["architect"] + KIDS + ["outsider"]:
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

    def post(self, who, action, body=None, key=None):
        headers = {"X-CSRF-Token": self.tokens[who]}
        if key or action == "revive":
            headers["X-Idempotency-Key"] = key or uuid.uuid4().hex
        return self.clients[who].post(f"/api/v4/royale/{action}", headers=headers, json=body or {})

    def view(self, who="architect"):
        response = self.clients[who].get("/api/v4/royale")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def begin(self, players=KIDS):
        self.assertEqual(self.post("architect", "create").status_code, 200)
        for name in players:
            self.assertEqual(self.post(name, "join").status_code, 200)
        started = self.post("architect", "start")
        self.assertEqual(started.status_code, 200, started.text)
        self.now += timedelta(seconds=RULES["intro_seconds"])   # заставка 3-2-1 кончилась, вопрос открыт

    def state(self):
        return json.loads(self.sql("SELECT state_json FROM v4_royale_games ORDER BY id DESC LIMIT 1")[0]["state_json"])

    def answer(self, who, correct=True):
        question = self.state()["question"]
        choice = question["answer"] if correct else (question["answer"] + 1) % len(question["options"])
        response = self.post(who, "answer", {"choice": choice})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def round(self, right, wrong=()):
        for name in right:
            self.answer(name, True)
        for name in wrong:
            self.answer(name, False)

    def after_reveal(self):
        self.now += timedelta(seconds=RULES["reveal_seconds"] + 1)
        return self.view()

    def wallet(self, who):
        row = self.sql("SELECT stars, rep FROM v4_case_wallets WHERE season_id=1 AND account_id=?", (self.ids[who],))[0]
        return int(row["stars"]), int(row["rep"])

    # --- лобби ------------------------------------------------------------------------------

    def test_staff_open_the_lobby_and_season_members_join(self):
        self.assertEqual(self.post("kid01", "create").status_code, 403)
        self.assertEqual(self.post("kid01", "join").status_code, 404)
        self.assertEqual(self.post("architect", "create").status_code, 200)
        self.assertEqual(self.post("architect", "create").status_code, 409)
        self.assertEqual(self.post("kid01", "join").json()["game"]["players"], 1)
        self.assertEqual(self.post("kid01", "join").json()["game"]["players"], 1)
        self.assertEqual(self.post("outsider", "join").status_code, 409)
        self.assertEqual(self.post("architect", "start").status_code, 409)      # один игрок
        self.post("kid02", "join")
        self.assertEqual(self.post("kid01", "start").status_code, 403)
        game = self.post("architect", "start").json()["game"]
        self.assertEqual((game["status"], game["round"], game["starters"]), ("question", 1, 2))
        self.assertEqual(self.post("kid03", "join").status_code, 409)

    # --- раунды ------------------------------------------------------------------------------

    def test_the_intro_hides_the_first_word_and_does_not_eat_the_answer_time(self):
        self.assertEqual(self.post("architect", "create").status_code, 200)
        for name in ("kid01", "kid02"):
            self.post(name, "join")
        self.post("architect", "start")
        game = self.view("kid01")["game"]
        self.assertIn("intro_until", game)
        self.assertNotIn("question", game)
        self.assertNotIn(self.state()["question"]["options"][0], json.dumps(game, ensure_ascii=False))
        self.assertEqual(self.post("kid01", "answer", {"choice": 0}).status_code, 409)
        self.now += timedelta(seconds=RULES["intro_seconds"] + RULES["stages"][0]["seconds"] - 1)
        game = self.view("kid01")["game"]
        self.assertEqual(game["status"], "question")
        self.assertIn("prompt", game["question"])
        self.answer("kid01")

    def test_the_phone_sees_the_answer_only_at_the_reveal(self):
        self.begin()
        seen = self.clients["kid01"].get("/api/v4/royale").text
        self.assertNotIn('"answer"', seen)
        question = json.loads(seen)["game"]["question"]
        self.assertEqual(len(question["options"]), RULES["stages"][0]["options"])
        self.assertIsNotNone(question["prompt"]["pinyin"])
        self.round(KIDS)
        reveal = self.view("kid01")["game"]
        self.assertEqual(reveal["status"], "reveal")
        self.assertEqual(reveal["reveal"]["answer"], self.state()["question"]["answer"])

    def test_a_wrong_answer_eliminates_and_everyone_answered_closes_the_round_at_once(self):
        self.begin()
        self.round(KIDS[:11], wrong=["kid12"])
        game = self.view("kid12")["game"]
        self.assertEqual((game["status"], game["alive"], game["reveal"]["eliminated"]), ("reveal", 11, 1))
        self.assertFalse(game["me"]["alive"])
        self.assertEqual(self.post("kid12", "answer", {"choice": 0}).status_code, 409)

    def test_silence_eliminates_and_a_late_answer_changes_nothing(self):
        self.begin()
        self.round(KIDS[:6])
        self.now += timedelta(seconds=RULES["stages"][0]["seconds"], milliseconds=RULES["grace_ms"] + 100)
        late = self.post("kid07", "answer", {"choice": 0})
        self.assertEqual(late.status_code, 200, late.text)
        game = late.json()["game"]
        self.assertEqual((game["status"], game["alive"]), ("reveal", 6))
        self.assertFalse(game["me"]["alive"])

    def test_revive_costs_fifteen_once_and_only_until_half(self):
        self.begin()
        self.round(KIDS[:11], wrong=["kid12"])
        key = uuid.uuid4().hex
        first = self.post("kid12", "revive", key=key)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(self.post("kid12", "revive", key=key).headers["X-Idempotent-Replayed"], "true")
        self.assertEqual(self.wallet("kid12")[0], WALLET - RULES["revive_price"])
        self.assertTrue(self.view("kid12")["game"]["me"]["alive"])
        self.assertEqual(self.post("kid01", "revive").status_code, 409)             # жив
        self.after_reveal()
        self.round(KIDS[:5], wrong=KIDS[5:])                                        # осталось 5 из 12
        self.assertFalse(self.view("kid11")["game"]["me"]["can_revive"])
        self.assertEqual(self.post("kid11", "revive").status_code, 409)             # меньше половины
        self.assertEqual(self.post("kid12", "revive").status_code, 409)             # уже воскресал
        self.assertEqual(self.wallet("kid11")[0], WALLET)

    def test_the_eliminated_vote_for_the_next_surprise(self):
        self.begin()
        self.round(KIDS[:10], wrong=["kid11", "kid12"])
        self.assertEqual(self.post("kid01", "vote", {"surprise": "fast"}).status_code, 409)
        self.post("kid11", "vote", {"surprise": "fast"})
        self.assertEqual(self.post("kid12", "vote", {"surprise": "fast"}).json()["game"]["reveal"]["votes"]["fast"], 2)
        game = self.after_reveal()["game"]
        seconds = RULES["stages"][0]["seconds"] - RULES["surprises"]["fast_seconds"]
        self.assertEqual((game["round"], game["question"]["surprise"], game["question"]["seconds"]), (2, "fast", seconds))

    def test_mirror_and_shuffle_are_new_surprises(self):
        self.begin()
        self.round(KIDS[:10], wrong=["kid11", "kid12"])
        self.post("kid11", "vote", {"surprise": "mirror"})
        self.assertEqual(self.post("kid12", "vote", {"surprise": "mirror"}).status_code, 200)
        self.assertEqual(self.post("kid12", "vote", {"surprise": "shuffle"}).status_code, 200)
        self.post("kid12", "vote", {"surprise": "mirror"})
        game = self.after_reveal()["game"]
        self.assertEqual(game["question"]["surprise"], "mirror")

    # --- особые раунды (этап 2) ------------------------------------------------------------------

    def test_numbers_tones_and_the_round_schedule_are_built_right(self):
        self.assertEqual([royale._number_hanzi(n) for n in (5, 10, 11, 20, 75, 99)],
                         ["五", "十", "十一", "二十", "七十五", "九十九"])
        self.assertEqual(royale._retone("shuǐ"), ["shuī", "shuí", "shuǐ", "shuì"])
        self.assertEqual(royale._retone("tàiyáng"), [])
        options = royale._number_options(75, 4)
        self.assertEqual((len(set(options)), "75" in options), (4, True))
        schedule = [royale._kind_for(n) for n in range(1, 10)]
        self.assertEqual(schedule, ["word", "word", "tone", "word", "number", "word", "tone", "word", "number"])

    def test_tone_and_number_rounds_and_the_final_duel(self):
        base = lambda text: "".join(royale.MARKED[ch][0] if ch in royale.MARKED else ch for ch in text)
        self.begin(players=KIDS[:4])
        self.round(KIDS[:4])
        self.after_reveal()
        self.round(KIDS[:4])
        question = self.after_reveal()["game"]["question"]
        self.assertEqual(question["kind"], "tone")
        self.assertIsNone(question["prompt"]["pinyin"])
        self.assertEqual(len({base(option) for option in question["options"]}), 1)
        self.assertEqual(len(set(question["options"])), len(question["options"]))

        self.round(KIDS[:2], wrong=KIDS[2:4])
        question = self.after_reveal()["game"]["question"]
        self.assertTrue(question["final"])
        self.assertEqual(question["seconds"], RULES["final_seconds"])

        self.round(KIDS[:2])
        question = self.after_reveal()["game"]["question"]
        self.assertEqual(question["kind"], "number")
        self.assertTrue(all(option.isdigit() for option in question["options"]))
        self.assertTrue(set(question["prompt"]["zh"]) <= set(royale.DIGITS + "十"))

    # --- итоги ------------------------------------------------------------------------------

    def test_the_last_survivor_wins_and_the_top_three_get_prizes_once_a_day(self):
        self.begin()
        self.round(["kid01", "kid02", "kid03"], wrong=KIDS[3:])
        self.after_reveal()
        self.round(["kid01", "kid02"], wrong=["kid03"])
        self.after_reveal()
        self.round(["kid01"], wrong=["kid02"])
        game = self.after_reveal()["game"]
        self.assertEqual(game["status"], "over")
        self.assertEqual([r["name"] for r in game["results"][:3]], ["KID01", "KID02", "KID03"])
        self.assertEqual(self.wallet("kid01"), (WALLET + 30, 30))
        self.assertEqual(self.wallet("kid02"), (WALLET + 20, 20))
        self.assertEqual(self.wallet("kid03"), (WALLET + 10, 10))
        self.assertEqual(self.view("kid01")["game"]["me"]["place"], 1)
        self.now += timedelta(minutes=1)
        self.begin()
        self.round(["kid01"], wrong=KIDS[1:])
        final = self.after_reveal()["game"]
        self.assertEqual(final["results"][0]["name"], "KID01")
        self.assertTrue(final["results"][0]["limited"])
        self.assertEqual(self.wallet("kid01"), (WALLET + 30, 30))                   # второй приз за день не пришёл
        self.assertEqual([r["limited"] for r in final["results"][:3]], [True, True, True])
        self.assertEqual(len(self.sql("SELECT 1 FROM v4_economy_operations WHERE operation='royale.prize'")), 3)

    def test_a_small_game_brings_no_prizes_and_equal_rounds_go_to_the_faster(self):
        self.begin(players=["kid01", "kid02", "kid03"])
        self.now += timedelta(seconds=1)
        self.answer("kid02", False)
        self.now += timedelta(seconds=2)
        self.answer("kid01", False)
        self.answer("kid03", False)
        game = self.after_reveal()["game"]
        self.assertEqual(game["status"], "over")
        self.assertEqual(game["results"][0]["name"], "KID02")
        self.assertIsNone(game["results"][0]["prize"])
        self.assertEqual(self.wallet("kid02"), (WALLET, 0))

    def test_cancel_returns_paid_revives(self):
        self.begin()
        self.round(KIDS[:11], wrong=["kid12"])
        self.post("kid12", "revive")
        self.assertEqual(self.post("kid01", "cancel").status_code, 403)
        game = self.post("architect", "cancel").json()["game"]
        self.assertEqual((game["status"], game["cancelled"], game["results"]), ("over", True, []))
        self.assertEqual(self.wallet("kid12")[0], WALLET)

    def test_players_and_answers_are_forgotten_half_an_hour_after_the_end(self):
        self.begin(players=["kid01", "kid02"])
        self.round(["kid01"], wrong=["kid02"])
        self.after_reveal()
        self.now += timedelta(minutes=RULES["keep_minutes"] + 1)
        self.assertIsNone(self.view()["game"])
        for table in ("v4_royale_players", "v4_royale_answers", "v4_royale_votes"):
            self.assertEqual(self.sql(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"], 0, table)
        self.assertEqual(json.loads(self.sql("SELECT results_json FROM v4_royale_games")[0]["results_json"])[0]["name"], "KID01")

    def test_the_host_grid_is_for_staff_only(self):
        self.begin()
        self.assertEqual(len(self.view("architect")["game"]["grid"]), len(KIDS))
        self.assertNotIn("grid", self.view("kid01")["game"])


if __name__ == "__main__":
    unittest.main()
