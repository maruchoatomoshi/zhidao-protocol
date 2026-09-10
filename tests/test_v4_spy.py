from __future__ import annotations

import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from zhidao_v4 import rooms, spy
from zhidao_v4.api import create_app
from zhidao_v4.auth import provision_local_account
from zhidao_v4.bootstrap import bootstrap_system_admin
from zhidao_v4.db import connect_database, immediate_transaction


ADMIN_PASSWORD = "correct horse battery staple"
USER_PASSWORD = "another correct horse battery"
NAMES = ["Ксения", "Артём", "Милана", "Тимур", "Вера"]


class SpyGameTests(unittest.TestCase):
    """Шпион Протокола.

    Главное, что здесь проверяется, — не «эндпоинт отвечает», а обещания
    игры: тайна не уходит на телефон, которому не положена; голосование
    нельзя провести в обход стола; ушедший шпион не оставляет партию висеть;
    перезапуск сервера не убивает вечер; после вечера не остаётся, кто с кем
    играл.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "zhidao.db"
        bootstrap_system_admin(
            self.db_path, username="architect", password=ADMIN_PASSWORD, display_name="Архитектор"
        )
        self.ids: dict[str, int] = {}
        conn = connect_database(self.db_path)
        try:
            with immediate_transaction(conn):
                for index, name in enumerate(NAMES, start=1):
                    account = provision_local_account(
                        conn,
                        username=f"kid{index}",
                        password=USER_PASSWORD,
                        display_name=name,
                        role_code="participant",
                    )
                    self.ids[f"kid{index}"] = int(account["id"])
        finally:
            conn.close()
        self.app = create_app(self.db_path, cookie_secure=False, session_hours=1)
        self.sessions: dict[str, tuple[TestClient, str]] = {}

    def tearDown(self):
        for client, _ in self.sessions.values():
            client.close()
        self.temp_dir.cleanup()

    # --- помощники ---------------------------------------------------------

    def session(self, username: str, app=None):
        key = username if app is None else f"{username}@{id(app)}"
        if key not in self.sessions:
            client = TestClient(app or self.app)
            password = ADMIN_PASSWORD if username == "architect" else USER_PASSWORD
            response = client.post("/api/v4/auth/login", json={"username": username, "password": password})
            self.assertEqual(response.status_code, 200, response.text)
            self.sessions[key] = (client, response.json()["csrf_token"])
        return self.sessions[key]

    def post(self, who, path, body=None, app=None):
        client, csrf = self.session(who, app)
        return client.post(path, json=body or {}, headers={"X-CSRF-Token": csrf})

    def get(self, who, path, app=None):
        client, _ = self.session(who, app)
        return client.get(path)

    def ok(self, response):
        self.assertLess(response.status_code, 300, response.text)
        return response.json()

    def seat(self, count=4):
        code = self.ok(self.post("kid1", "/api/v4/games/rooms", {"game": "spy"}))["room"]["code"]
        for index in range(2, count + 1):
            self.ok(self.post(f"kid{index}", "/api/v4/games/rooms/join", {"code": code}))
        return code

    def start(self, count=4):
        code = self.seat(count)
        self.ok(self.post("kid1", f"/api/v4/games/rooms/{code}/spy/start"))
        return code

    def state(self, code) -> dict:
        conn = connect_database(self.db_path)
        try:
            return json.loads(rooms.load_room(conn, code)["state_json"])
        finally:
            conn.close()

    def who(self, account_id: int) -> str:
        return next(name for name, value in self.ids.items() if value == account_id)

    def roles(self, code):
        state = self.state(code)
        spy_name = self.who(state["spy"])
        agents = [self.who(pid) for pid in state["participants"] if pid != state["spy"]]
        return state, spy_name, agents

    def scores(self, code, who="kid1"):
        view = self.ok(self.get(who, f"/api/v4/games/rooms/{code}"))
        return {self.who(p["account_id"]): p["score"] for p in view["players"]}, view

    # --- тайна ---------------------------------------------------------------

    def test_the_spy_never_receives_the_location(self):
        code = self.start()
        state, spy_name, agents = self.roles(code)
        place = spy.locations_by_id()[state["location"]]

        spy_round = self.ok(self.get(spy_name, f"/api/v4/games/rooms/{code}"))["game"]["round"]
        self.assertEqual(spy_round["you"], {"spy": True})
        # Весь экран шпиона, кроме общего списка мест, не содержит ни следа
        # места: ни id, ни иероглифов, ни перевода, ни ролей.
        leaked = json.dumps(spy_round, ensure_ascii=False)
        for secret in (place["id"], place["zh"], place["ru"], *place["roles"]):
            self.assertNotIn(secret, leaked)

        for agent in agents:
            agent_round = self.ok(self.get(agent, f"/api/v4/games/rooms/{code}"))["game"]["round"]
            self.assertEqual(agent_round["you"]["location"]["id"], place["id"])
            self.assertEqual(agent_round["you"]["role"], state["roles"][str(self.ids[agent])])
            # И никто за столом не получает имени шпиона до раскрытия.
            self.assertNotIn("result", agent_round)
            self.assertNotIn("spy", agent_round)

    def test_hanzi_mode_hides_pinyin_and_translation(self):
        code = self.seat()
        self.ok(self.post("kid1", f"/api/v4/games/rooms/{code}/settings", {"mode": "hanzi", "minutes": 6}))
        self.ok(self.post("kid1", f"/api/v4/games/rooms/{code}/spy/start"))
        _, _, agents = self.roles(code)
        body = self.ok(self.get(agents[0], f"/api/v4/games/rooms/{code}"))["game"]
        self.assertEqual(set(body["round"]["you"]["location"]), {"id", "zh"})
        self.assertTrue(all(set(item) == {"id", "zh"} for item in body["locations"]))

    # --- состав и права ---------------------------------------------------------

    def test_three_players_are_not_enough(self):
        code = self.seat(3)
        response = self.post("kid1", f"/api/v4/games/rooms/{code}/spy/start")
        self.assertEqual(response.status_code, 409, response.text)

    def test_only_the_host_starts_and_configures(self):
        code = self.seat()
        self.assertEqual(self.post("kid2", f"/api/v4/games/rooms/{code}/spy/start").status_code, 403)
        self.assertEqual(
            self.post("kid2", f"/api/v4/games/rooms/{code}/settings", {"mode": "hanzi", "minutes": 8}).status_code,
            403,
        )

    def test_strangers_cannot_read_a_room(self):
        code = self.seat()
        self.assertEqual(self.get("kid5", f"/api/v4/games/rooms/{code}").status_code, 404)

    def test_nobody_sits_down_in_the_middle_of_a_round(self):
        code = self.start()
        self.assertEqual(self.post("kid5", "/api/v4/games/rooms/join", {"code": code}).status_code, 409)
        _, spy_name, _ = self.roles(code)
        state = self.state(code)
        self.ok(self.post(spy_name, f"/api/v4/games/rooms/{code}/spy/guess", {"location_id": state["location"]}))
        # Между раундами — пожалуйста.
        self.ok(self.post("kid5", "/api/v4/games/rooms/join", {"code": code}))

    def test_joining_another_room_leaves_the_first_and_passes_the_host_on(self):
        first = self.ok(self.post("kid1", "/api/v4/games/rooms", {"game": "spy"}))["room"]["code"]
        self.ok(self.post("kid2", "/api/v4/games/rooms/join", {"code": first}))
        self.ok(self.post("kid1", "/api/v4/games/rooms", {"game": "spy"}))
        view = self.ok(self.get("kid2", f"/api/v4/games/rooms/{first}"))
        self.assertEqual(view["room"]["host_account_id"], self.ids["kid2"])
        self.assertEqual([p["account_id"] for p in view["players"]], [self.ids["kid2"]])

    def test_guessing_codes_is_rate_limited(self):
        codes = {self.post("kid5", "/api/v4/games/rooms/join", {"code": f"{n:04d}"}).status_code for n in range(25)}
        self.assertIn(429, codes)

    # --- исходы -----------------------------------------------------------------

    def test_a_spy_who_names_the_place_scores_four(self):
        code = self.start()
        state, spy_name, _ = self.roles(code)
        body = self.ok(self.post(spy_name, f"/api/v4/games/rooms/{code}/spy/guess", {"location_id": state["location"]}))
        result = body["game"]["round"]["result"]
        self.assertEqual((result["winner"], result["reason"]), ("spy", "guessed"))
        self.assertEqual(result["location"]["id"], state["location"])
        scores, _ = self.scores(code)
        self.assertEqual(scores[spy_name], spy.SPY_GUESSED)
        self.assertEqual(sum(scores.values()), spy.SPY_GUESSED)

    def test_a_wrong_guess_gives_every_agent_a_point(self):
        code = self.start()
        state, spy_name, agents = self.roles(code)
        wrong = next(pid for pid in spy.locations_by_id() if pid != state["location"])
        self.ok(self.post(spy_name, f"/api/v4/games/rooms/{code}/spy/guess", {"location_id": wrong}))
        scores, _ = self.scores(code)
        self.assertEqual({name: scores[name] for name in agents}, {name: 1 for name in agents})
        self.assertEqual(scores[spy_name], 0)

    def test_only_the_spy_may_name_the_place(self):
        code = self.start()
        state, _, agents = self.roles(code)
        response = self.post(agents[0], f"/api/v4/games/rooms/{code}/spy/guess", {"location_id": state["location"]})
        self.assertEqual(response.status_code, 403)

    def test_a_unanimous_accusation_catches_the_spy(self):
        code = self.start()
        _, spy_name, agents = self.roles(code)
        accuser, *others = agents
        self.ok(self.post(accuser, f"/api/v4/games/rooms/{code}/spy/accuse",
                          {"target_account_id": self.ids[spy_name]}))
        # Обвиняемый не голосует за собственную судьбу.
        self.assertEqual(self.post(spy_name, f"/api/v4/games/rooms/{code}/spy/vote", {"yes": False}).status_code, 403)
        for voter in others:
            body = self.ok(self.post(voter, f"/api/v4/games/rooms/{code}/spy/vote", {"yes": True}))
        result = body["game"]["round"]["result"]
        self.assertEqual((result["winner"], result["reason"]), ("agents", "accused"))
        scores, _ = self.scores(code)
        self.assertEqual(scores[accuser], spy.ACCUSER_WIN)
        self.assertTrue(all(scores[name] == spy.AGENT_WIN for name in others))
        self.assertEqual(scores[spy_name], 0)

    def test_convicting_an_innocent_hands_the_spy_four(self):
        code = self.start()
        _, spy_name, agents = self.roles(code)
        accuser, victim, bystander = agents
        self.ok(self.post(accuser, f"/api/v4/games/rooms/{code}/spy/accuse", {"target_account_id": self.ids[victim]}))
        self.ok(self.post(spy_name, f"/api/v4/games/rooms/{code}/spy/vote", {"yes": True}))
        self.ok(self.post(bystander, f"/api/v4/games/rooms/{code}/spy/vote", {"yes": True}))
        scores, view = self.scores(code)
        self.assertEqual(view["game"]["round"]["result"]["reason"], "framed")
        self.assertEqual(scores[spy_name], spy.SPY_FRAMED)

    def test_a_lone_accuser_cannot_convict_while_the_table_is_away(self):
        # Найдено на живой проверке: пока голосование считало только тех, кто
        # на связи, обвинитель осуждал в одиночку, стоило остальным свернуть
        # приложение.
        code = self.start()
        _, spy_name, agents = self.roles(code)
        accuser = agents[0]
        body = self.ok(self.post(accuser, f"/api/v4/games/rooms/{code}/spy/accuse",
                                 {"target_account_id": self.ids[spy_name]}))
        self.assertEqual(body["game"]["round"]["phase"], "vote")
        later = rooms.utcnow() + timedelta(seconds=spy.VOTE_SECONDS + 1)
        with mock.patch("zhidao_v4.rooms.utcnow", return_value=later):
            phase = self.ok(self.get(accuser, f"/api/v4/games/rooms/{code}"))["game"]["round"]["phase"]
        self.assertEqual(phase, "discussion")

    def test_a_clear_majority_without_objections_convicts_when_the_vote_times_out(self):
        code = self.start()
        _, spy_name, agents = self.roles(code)
        accuser, second, _silent = agents
        self.ok(self.post(accuser, f"/api/v4/games/rooms/{code}/spy/accuse",
                          {"target_account_id": self.ids[spy_name]}))
        body = self.ok(self.post(second, f"/api/v4/games/rooms/{code}/spy/vote", {"yes": True}))
        self.assertEqual(body["game"]["round"]["phase"], "vote")
        later = rooms.utcnow() + timedelta(seconds=spy.VOTE_SECONDS + 1)
        with mock.patch("zhidao_v4.rooms.utcnow", return_value=later):
            result = self.ok(self.get(accuser, f"/api/v4/games/rooms/{code}"))["game"]["round"]["result"]
        self.assertEqual((result["winner"], result["reason"]), ("agents", "accused"))

    def test_one_no_vote_fails_the_accusation_and_spends_it(self):
        code = self.start()
        _, spy_name, agents = self.roles(code)
        accuser, target, doubter = agents
        before = self.state(code)["ends_at"]
        self.ok(self.post(accuser, f"/api/v4/games/rooms/{code}/spy/accuse", {"target_account_id": self.ids[target]}))
        body = self.ok(self.post(doubter, f"/api/v4/games/rooms/{code}/spy/vote", {"yes": False}))
        self.assertEqual(body["game"]["round"]["phase"], "discussion")
        # Таймер стоял, пока голосовали, а не тикал дальше.
        after = rooms.parse(self.state(code)["ends_at"])
        self.assertGreaterEqual(after, rooms.parse(before) - timedelta(seconds=2))
        again = self.post(accuser, f"/api/v4/games/rooms/{code}/spy/accuse", {"target_account_id": self.ids[spy_name]})
        self.assertEqual(again.status_code, 409)

    def test_when_time_runs_out_the_table_votes_and_a_majority_catches_the_spy(self):
        code = self.start()
        _, spy_name, agents = self.roles(code)
        later = rooms.utcnow() + timedelta(minutes=9)
        with mock.patch("zhidao_v4.rooms.utcnow", return_value=later):
            phase = self.ok(self.get("kid1", f"/api/v4/games/rooms/{code}"))["game"]["round"]["phase"]
            self.assertEqual(phase, "final_vote")
            # Шпиону нельзя назвать место, когда время вышло.
            state = self.state(code)
            late = self.post(spy_name, f"/api/v4/games/rooms/{code}/spy/guess", {"location_id": state["location"]})
            self.assertEqual(late.status_code, 409)
            for agent in agents:
                self.ok(self.post(agent, f"/api/v4/games/rooms/{code}/spy/final-vote",
                                  {"target_account_id": self.ids[spy_name]}))
            body = self.ok(self.post(spy_name, f"/api/v4/games/rooms/{code}/spy/final-vote",
                                     {"target_account_id": self.ids[agents[0]]}))
        result = body["game"]["round"]["result"]
        self.assertEqual((result["winner"], result["reason"]), ("agents", "final_vote"))

    def test_a_spy_who_walks_away_voids_the_round(self):
        code = self.start()
        _, spy_name, agents = self.roles(code)
        self.ok(self.post(spy_name, f"/api/v4/games/rooms/{code}/leave"))
        scores, view = self.scores(code, who=agents[0])
        result = view["game"]["round"]["result"]
        self.assertEqual((result["winner"], result["reason"]), ("void", "spy_left"))
        self.assertEqual(sum(scores.values()), 0)

    # --- устойчивость и приватность ------------------------------------------------

    def test_the_round_survives_a_server_restart(self):
        code = self.start()
        before = self.state(code)
        restarted = create_app(self.db_path, cookie_secure=False, session_hours=1)
        view = self.ok(self.get("kid2", "/api/v4/games/rooms/current", app=restarted))
        self.assertEqual(view["room"]["code"], code)
        self.assertEqual(view["game"]["round"]["number"], before["round"])
        self.assertEqual(self.state(code)["location"], before["location"])

    def test_idle_rooms_disappear_with_who_sat_in_them(self):
        self.seat()
        later = rooms.utcnow() + timedelta(minutes=rooms.ROOM_IDLE_MINUTES + 1)
        with mock.patch("zhidao_v4.rooms.utcnow", return_value=later):
            self.ok(self.post("kid5", "/api/v4/games/rooms", {"game": "spy"}))
        conn = connect_database(self.db_path)
        try:
            seated = [row[0] for row in conn.execute("SELECT account_id FROM v4_game_room_players")]
            count = conn.execute("SELECT COUNT(*) FROM v4_game_rooms").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(seated, [self.ids["kid5"]])
        self.assertEqual(count, 1)

    def test_organisers_can_switch_the_game_off(self):
        code = self.seat()
        self.assertEqual(self.post("kid1", "/api/v4/games/switches/spy", {"enabled": False}).status_code, 403)
        self.ok(self.post("architect", "/api/v4/games/switches/spy", {"enabled": False}))
        # Выключение гасит и уже идущие комнаты.
        self.assertEqual(self.get("kid2", f"/api/v4/games/rooms/{code}").status_code, 404)
        self.assertEqual(self.post("kid1", "/api/v4/games/rooms", {"game": "spy"}).status_code, 409)
        self.ok(self.post("architect", "/api/v4/games/switches/spy", {"enabled": True}))
        self.ok(self.post("kid1", "/api/v4/games/rooms", {"game": "spy"}))


class SpyContentTests(unittest.TestCase):
    def test_every_place_has_enough_distinct_roles(self):
        places = spy.content()["locations"]
        self.assertGreaterEqual(len(places), 20)
        for place in places:
            self.assertGreaterEqual(len(set(place["roles"])), rooms.MAX_PLAYERS - 1, place["id"])

    def test_content_is_marked_unreviewed_until_a_human_checks_the_chinese(self):
        # Флаг снимает человек, знающий язык. Этот тест упадёт, когда флаг
        # снимут, — и напомнит обновить V4_GAMES.md.
        self.assertIs(spy.content()["reviewed"], False)


if __name__ == "__main__":
    unittest.main()
