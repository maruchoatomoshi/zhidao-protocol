from __future__ import annotations

import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from zhidao_v4 import outage, rooms
from zhidao_v4.api import create_app
from zhidao_v4.auth import provision_local_account
from zhidao_v4.bootstrap import bootstrap_system_admin
from zhidao_v4.db import connect_database, immediate_transaction


ADMIN_PASSWORD = "correct horse battery staple"
USER_PASSWORD = "another correct horse battery"


class WireRuleTests(unittest.TestCase):
    """Решатель проводов обязан делать ровно то, что написано в инструкции.

    Эти случаи выписаны из текста WIRE_RULES руками: если кто-то поменяет
    правило в коде, не поменяв описание (или наоборот), тест упадёт."""

    def test_three_wires(self):
        self.assertEqual(outage.solve_wires(["red", "green", "green"]), 1)   # первый 绿
        self.assertEqual(outage.solve_wires(["blue", "red", "blue"]), 1)     # первый и последний одного цвета
        self.assertEqual(outage.solve_wires(["blue", "red", "white"]), 2)    # иначе последний

    def test_four_wires(self):
        self.assertEqual(outage.solve_wires(["red", "blue", "red", "red"]), 2)       # второй 红
        self.assertEqual(outage.solve_wires(["white", "red", "yellow", "black"]), 0)  # нет 蓝 — первый
        self.assertEqual(outage.solve_wires(["blue", "red", "yellow", "white"]), 2)   # последний 白 — третий
        self.assertEqual(outage.solve_wires(["blue", "blue", "yellow", "green"]), 1)  # последний 蓝

    def test_five_wires(self):
        self.assertEqual(outage.solve_wires(["black", "red", "red", "red", "red"]), 1)     # после 黑
        self.assertEqual(outage.solve_wires(["red", "red", "red", "red", "black"]), 0)     # 黑 последний — первый
        self.assertEqual(outage.solve_wires(["yellow", "red", "yellow", "blue", "blue"]), 2)  # 黄 больше 红
        self.assertEqual(outage.solve_wires(["red", "blue", "white", "green", "yellow"]), 3)  # все разные
        self.assertEqual(outage.solve_wires(["red", "red", "blue", "blue", "green"]), 1)   # иначе второй

    def test_six_wires(self):
        self.assertEqual(outage.solve_wires(["red"] * 6), 4)                                          # нет 白
        self.assertEqual(outage.solve_wires(["blue", "white", "green", "white", "red", "red"]), 1)    # первый 白
        self.assertEqual(outage.solve_wires(["green", "white", "green", "red", "red", "red"]), 2)     # последний 绿
        self.assertEqual(outage.solve_wires(["yellow", "white", "red", "red", "black", "black"]), 2)  # иначе третий

    def test_keypad_puzzles_have_exactly_one_column(self):
        for _ in range(300):
            module = outage._make_keypad()
            owners = [col for col in outage.KEYPAD_COLUMNS if set(module["order"]) <= set(col)]
            self.assertEqual(len(owners), 1)
            self.assertEqual(module["order"], sorted(module["order"], key=owners[0].index))

    def test_numbers_are_written_the_chinese_way(self):
        self.assertEqual(outage._number_zh(13), "十三")
        self.assertEqual(outage._number_zh(20), "二十")
        self.assertEqual(outage._number_zh(45), "四十五")
        self.assertEqual(outage._number_zh(99), "九十九")


class OutageGameTests(unittest.TestCase):
    """Сбой системы.

    У каждой стороны только своя половина: техник не получает инструкцию и
    ответы, эксперты — не видят модули, а ответы не уходят никому до конца.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "zhidao.db"
        bootstrap_system_admin(self.db_path, username="architect", password=ADMIN_PASSWORD, display_name="Архитектор")
        self.ids: dict[str, int] = {}
        conn = connect_database(self.db_path)
        try:
            with immediate_transaction(conn):
                for index, name in enumerate(["Ксения", "Артём", "Милана"], start=1):
                    account = provision_local_account(conn, username=f"kid{index}", password=USER_PASSWORD,
                                                      display_name=name, role_code="participant")
                    self.ids[f"kid{index}"] = int(account["id"])
        finally:
            conn.close()
        self.app = create_app(self.db_path, cookie_secure=False, session_hours=1)
        self.sessions: dict[str, tuple[TestClient, str]] = {}

    def tearDown(self):
        for client, _ in self.sessions.values():
            client.close()
        self.temp_dir.cleanup()

    def session(self, who):
        if who not in self.sessions:
            client = TestClient(self.app)
            password = ADMIN_PASSWORD if who == "architect" else USER_PASSWORD
            response = client.post("/api/v4/auth/login", json={"username": who, "password": password})
            self.assertEqual(response.status_code, 200, response.text)
            self.sessions[who] = (client, response.json()["csrf_token"])
        return self.sessions[who]

    def post(self, who, path, body=None):
        client, csrf = self.session(who)
        return client.post(path, json=body or {}, headers={"X-CSRF-Token": csrf})

    def ok(self, response):
        self.assertLess(response.status_code, 300, response.text)
        return response.json()

    def act(self, who, action, body=None):
        return self.post(who, f"/api/v4/games/rooms/{self.code}/outage/{action}", body)

    def view(self, who):
        return self.ok(self.session(who)[0].get(f"/api/v4/games/rooms/{self.code}"))["game"]

    def state(self):
        conn = connect_database(self.db_path)
        try:
            return json.loads(rooms.load_room(conn, self.code)["state_json"])
        finally:
            conn.close()

    def write_state(self, state):
        conn = connect_database(self.db_path)
        try:
            conn.execute("UPDATE v4_game_rooms SET state_json=? WHERE code=?", (json.dumps(state, ensure_ascii=False), self.code))
        finally:
            conn.close()

    def start(self, players=("kid1", "kid2", "kid3"), technician="kid2", difficulty="normal"):
        host, *others = players
        self.code = self.ok(self.post(host, "/api/v4/games/rooms", {"game": "outage"}))["room"]["code"]
        for who in others:
            self.ok(self.post(who, "/api/v4/games/rooms/join", {"code": self.code}))
        if difficulty != "normal":
            self.ok(self.post(host, f"/api/v4/games/rooms/{self.code}/settings", {"difficulty": difficulty}))
        if technician:
            self.ok(self.act(host, "technician", {"account_id": self.ids[technician]}))
        self.ok(self.act(host, "start"))
        return self.state()

    def rig(self, modules):
        """Подменяет модули раунда известными — чтобы ходы в тесте были детерминированы."""
        state = self.state()
        state["modules"] = modules
        self.write_state(state)
        return state

    # --- тайны -------------------------------------------------------------------

    def test_the_technician_never_receives_the_manual_or_answers(self):
        self.start()
        game = self.view("kid2")
        self.assertTrue(game["you_technician"])
        self.assertNotIn("manual", game)
        leaked = json.dumps(game, ensure_ascii=False)
        for secret in ("answer", "order", "rules", "columns", "Режьте", "режьте"):
            self.assertNotIn(secret, leaked)
        self.assertEqual(len(game["modules"]), outage.DIFFICULTY["normal"]["modules"])

    def test_experts_never_see_the_modules(self):
        state = self.start()
        for who in ("kid1", "kid3"):
            game = self.view(who)
            self.assertFalse(game["you_technician"])
            self.assertNotIn("modules", game)
            self.assertIn("manual", game)
            leaked = json.dumps({k: v for k, v in game.items() if k != "manual"}, ensure_ascii=False)
            for module in state["modules"]:
                if module["type"] == "number":
                    self.assertNotIn(module["zh"], leaked)
            self.assertEqual({s["type"] for s in game["summary"]}, set(game["manual"]))

    def test_only_the_technician_touches_modules(self):
        self.start()
        self.rig([{"type": "number", "zh": "四十五", "value": 45, "solved": False}])
        self.assertEqual(self.act("kid1", "number", {"module": 0, "value": 45}).status_code, 403)

    # --- модули --------------------------------------------------------------------

    def test_wires_keypad_compass_and_number_can_be_fixed(self):
        self.start()
        wires = ["blue", "red", "white"]
        self.rig([
            {"type": "wires", "wires": wires, "cut": [], "answer": outage.solve_wires(wires), "solved": False},
            {"type": "keypad", "shown": ["口", "日", "田", "月"], "order": ["日", "月", "田", "口"], "pressed": [], "solved": False},
            {"type": "compass", "sequence": ["东", "上", "南", "左"], "progress": 0, "solved": False},
            {"type": "number", "zh": "二十七", "value": 27, "solved": False},
        ])
        self.ok(self.act("kid2", "cut", {"module": 0, "wire": 2}))
        for symbol in (1, 3, 2, 0):
            self.ok(self.act("kid2", "press", {"module": 1, "symbol": symbol}))
        for direction in ("right", "up", "down", "left"):
            self.ok(self.act("kid2", "direction", {"module": 2, "direction": direction}))
        game = self.ok(self.act("kid2", "number", {"module": 3, "value": 27}))["game"]
        self.assertEqual((game["phase"], game["result"]["success"], game["result"]["reason"]), ("over", True, "defused"))
        self.assertEqual(game["strikes"], 0)
        scores = {p["account_id"]: p["score"] for p in self.ok(self.session("kid1")[0].get(f"/api/v4/games/rooms/{self.code}"))["players"]}
        self.assertEqual(set(scores.values()), {outage.SUCCESS_POINTS})
        # После конца ответы открыты всем — это момент, когда слово запоминается.
        self.assertEqual(self.view("kid1")["modules"][3]["answer"], 27)

    def test_mistakes_are_strikes_and_three_bring_the_system_down(self):
        self.start()
        self.rig([
            {"type": "compass", "sequence": ["北", "北", "北", "北"], "progress": 0, "solved": False},
            {"type": "keypad", "shown": ["口", "日", "田", "月"], "order": ["日", "月", "田", "口"], "pressed": [], "solved": False},
        ])
        self.ok(self.act("kid2", "direction", {"module": 0, "direction": "up"}))
        game = self.ok(self.act("kid2", "direction", {"module": 0, "direction": "down"}))["game"]
        self.assertEqual(game["strikes"], 1)
        self.assertEqual(self.state()["modules"][0]["progress"], 0)   # ошибка сбрасывает ввод
        self.ok(self.act("kid2", "press", {"module": 1, "symbol": 1}))  # 日 — верно
        self.ok(self.act("kid2", "press", {"module": 1, "symbol": 0}))  # 口 — рано
        self.assertEqual(self.state()["modules"][1]["pressed"], ["日"])  # верные остаются нажатыми
        game = self.ok(self.act("kid2", "press", {"module": 1, "symbol": 2}))["game"]  # 田 — рано
        self.assertEqual((game["phase"], game["result"]["reason"], game["result"]["success"]), ("over", "strikes", False))
        self.assertEqual(sum(p["score"] for p in self.ok(self.session("kid1")[0].get(f"/api/v4/games/rooms/{self.code}"))["players"]), 0)

    def test_a_wrong_wire_stays_cut(self):
        self.start()
        wires = ["blue", "red", "white"]
        self.rig([{"type": "wires", "wires": wires, "cut": [], "answer": 2, "solved": False},
                  {"type": "number", "zh": "十一", "value": 11, "solved": False}])
        self.ok(self.act("kid2", "cut", {"module": 0, "wire": 0}))
        self.assertEqual(self.act("kid2", "cut", {"module": 0, "wire": 0}).status_code, 409)
        self.assertTrue(self.view("kid2")["modules"][0]["wires"][0]["cut"])

    def test_time_running_out_brings_the_system_down(self):
        self.start()
        later = rooms.utcnow() + timedelta(seconds=outage.DIFFICULTY["normal"]["seconds"] + 1)
        with mock.patch("zhidao_v4.rooms.utcnow", return_value=later):
            game = self.view("kid1")
        self.assertEqual((game["phase"], game["result"]["reason"]), ("over", "time"))

    # --- состав ---------------------------------------------------------------------

    def test_two_people_are_enough_and_the_technician_rotates(self):
        first = self.start(players=("kid1", "kid2"), technician=None)
        self.assertEqual(first["technician"], min(self.ids["kid1"], self.ids["kid2"]))
        state = self.state()
        state["phase"] = "over"
        self.write_state(state)
        self.ok(self.act("kid1", "start"))
        self.assertEqual(self.state()["technician"], max(self.ids["kid1"], self.ids["kid2"]))

    def test_a_technician_who_leaves_voids_the_round(self):
        self.start()
        self.ok(self.post("kid2", f"/api/v4/games/rooms/{self.code}/leave"))
        game = self.view("kid1")
        self.assertEqual((game["phase"], game["result"]["reason"], game["result"]["success"]), ("over", "technician_left", None))

    def test_only_the_host_picks_the_technician(self):
        self.code = self.ok(self.post("kid1", "/api/v4/games/rooms", {"game": "outage"}))["room"]["code"]
        self.ok(self.post("kid2", "/api/v4/games/rooms/join", {"code": self.code}))
        self.assertEqual(self.act("kid2", "technician", {"account_id": self.ids["kid2"]}).status_code, 403)

    def test_content_is_marked_unreviewed_until_a_human_checks_the_chinese(self):
        self.assertIs(outage.content()["reviewed"], False)


if __name__ == "__main__":
    unittest.main()
