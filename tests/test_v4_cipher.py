from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from zhidao_v4 import cipher, rooms
from zhidao_v4.api import create_app
from zhidao_v4.auth import provision_local_account
from zhidao_v4.bootstrap import bootstrap_system_admin
from zhidao_v4.db import connect_database, immediate_transaction


ADMIN_PASSWORD = "correct horse battery staple"
USER_PASSWORD = "another correct horse battery"
NAMES = ["Ксения", "Артём", "Милана", "Тимур", "Вера"]


class CipherGameTests(unittest.TestCase):
    """Шифровальщики.

    Как и у Шпиона, проверяются обещания игры, а не коды ответов: раскладку
    видят только капитаны; подсказку даёт только капитан ходящей команды;
    попыток не больше, чем разрешено; вирус и полное поле заканчивают партию
    и дают очки нужной команде; ушедший капитан не ломает партию.
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
                        conn, username=f"kid{index}", password=USER_PASSWORD,
                        display_name=name, role_code="participant",
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

    def session(self, username: str):
        if username not in self.sessions:
            client = TestClient(self.app)
            password = ADMIN_PASSWORD if username == "architect" else USER_PASSWORD
            response = client.post("/api/v4/auth/login", json={"username": username, "password": password})
            self.assertEqual(response.status_code, 200, response.text)
            self.sessions[username] = (client, response.json()["csrf_token"])
        return self.sessions[username]

    def post(self, who, path, body=None):
        client, csrf = self.session(who)
        return client.post(path, json=body or {}, headers={"X-CSRF-Token": csrf})

    def get(self, who, path):
        return self.session(who)[0].get(path)

    def ok(self, response):
        self.assertLess(response.status_code, 300, response.text)
        return response.json()

    def act(self, who, action, body=None):
        return self.post(who, f"/api/v4/games/rooms/{self.code}/cipher/{action}", body)

    def seat(self, teams: dict[str, str], captains=()):
        """teams: {'kid1': 'blue', ...}. Первый в словаре — ведущий."""
        host, *others = teams
        self.code = self.ok(self.post(host, "/api/v4/games/rooms", {"game": "cipher"}))["room"]["code"]
        for who in others:
            self.ok(self.post(who, "/api/v4/games/rooms/join", {"code": self.code}))
        for who, team in teams.items():
            if team:
                self.ok(self.act(who, "team", {"team": team}))
        for who in captains:
            self.ok(self.act(who, "captain"))
        return host

    def standard(self):
        """kid1, kid2 — синие (kid1 капитан); kid3, kid4 — красные (kid3 капитан)."""
        host = self.seat({"kid1": "blue", "kid2": "blue", "kid3": "red", "kid4": "red"}, captains=("kid1", "kid3"))
        self.ok(self.act(host, "start"))
        return self.state()

    def state(self) -> dict:
        conn = connect_database(self.db_path)
        try:
            return json.loads(rooms.load_room(conn, self.code)["state_json"])
        finally:
            conn.close()

    def write_state(self, state: dict) -> None:
        conn = connect_database(self.db_path)
        try:
            conn.execute("UPDATE v4_game_rooms SET state_json = ? WHERE code = ?",
                         (json.dumps(state, ensure_ascii=False), self.code))
        finally:
            conn.close()

    def roles(self, state):
        captain = {"blue": "kid1", "red": "kid3"}
        operative = {"blue": "kid2", "red": "kid4"}
        return captain, operative

    def cards(self, state, key):
        return [i for i, card in enumerate(state["board"]) if card["key"] == key and not card["revealed"]]

    def view(self, who):
        return self.ok(self.get(who, f"/api/v4/games/rooms/{self.code}"))

    # --- тайна ---------------------------------------------------------------

    def test_operatives_never_receive_the_key_captains_do(self):
        state = self.standard()
        for who in ("kid2", "kid4"):
            board = self.view(who)["game"]["board"]
            self.assertEqual(len(board), cipher.BOARD_SIZE)
            self.assertTrue(all("key" not in card for card in board), who)
            leaked = json.dumps(self.view(who)["game"], ensure_ascii=False)
            self.assertNotIn("virus", leaked)
            self.assertNotIn("neutral", leaked)
        for who in ("kid1", "kid3"):
            board = self.view(who)["game"]["board"]
            self.assertEqual([card["key"] for card in board], [card["key"] for card in state["board"]])

    def test_an_opened_card_shows_its_colour_to_everyone(self):
        state = self.standard()
        captain, operative = self.roles(state)
        team = state["turn"]
        self.ok(self.act(captain[team], "clue", {"count": 2}))
        index = self.cards(state, "neutral")[0]
        self.ok(self.act(operative[team], "guess", {"index": index}))
        card = self.view(operative[cipher._other(team)])["game"]["board"][index]
        self.assertEqual((card["revealed"], card["key"]), (True, "neutral"))

    def test_hanzi_mode_hides_translation_from_operatives_but_not_from_captains(self):
        host = self.seat({"kid1": "blue", "kid2": "blue", "kid3": "red", "kid4": "red"}, captains=("kid1", "kid3"))
        self.ok(self.post(host, f"/api/v4/games/rooms/{self.code}/settings", {"mode": "hanzi"}))
        self.ok(self.act(host, "start"))
        operative_word = self.view("kid2")["game"]["board"][0]["word"]
        captain_word = self.view("kid1")["game"]["board"][0]["word"]
        self.assertEqual(set(operative_word), {"zh"})
        self.assertEqual(set(captain_word), {"zh", "pinyin", "ru"})

    # --- составы -----------------------------------------------------------------

    def test_each_team_needs_a_captain_and_someone_to_guess(self):
        host = self.seat({"kid1": "blue", "kid2": "blue", "kid3": "blue", "kid4": "blue"})
        self.assertEqual(self.act(host, "start").status_code, 409)

    def test_players_without_a_team_are_balanced_when_the_game_starts(self):
        host = self.seat({"kid1": None, "kid2": None, "kid3": None, "kid4": None})
        self.ok(self.act(host, "start"))
        game = self.view("kid1")["game"]
        self.assertEqual([len(game["teams"][t]["members"]) for t in cipher.TEAMS], [2, 2])
        self.assertTrue(all(game["teams"][t]["captain"] for t in cipher.TEAMS))

    def test_teams_are_fixed_once_the_game_is_running(self):
        self.standard()
        self.assertEqual(self.act("kid2", "team", {"team": "red"}).status_code, 409)

    # --- ход ---------------------------------------------------------------------

    def test_only_the_captain_of_the_moving_team_gives_a_clue(self):
        state = self.standard()
        captain, operative = self.roles(state)
        team = state["turn"]
        self.assertEqual(self.act(captain[cipher._other(team)], "clue", {"count": 1}).status_code, 403)
        self.assertEqual(self.act(operative[team], "clue", {"count": 1}).status_code, 403)
        self.assertEqual(self.act(captain[team], "clue", {"count": 0}).status_code, 400)
        self.assertEqual(self.act(captain[team], "clue", {"count": True}).status_code, 400)
        self.ok(self.act(captain[team], "clue", {"count": 1}))

    def test_the_captain_does_not_guess_and_a_turn_cannot_be_skipped_empty(self):
        state = self.standard()
        captain, operative = self.roles(state)
        team = state["turn"]
        self.ok(self.act(captain[team], "clue", {"count": 1}))
        own = self.cards(state, team)[0]
        self.assertEqual(self.act(captain[team], "guess", {"index": own}).status_code, 403)
        self.assertEqual(self.act(operative[team], "end-turn").status_code, 409)
        self.ok(self.act(operative[team], "guess", {"index": own}))
        game = self.ok(self.act(operative[team], "end-turn"))["game"]
        self.assertEqual(game["turn"]["team"], cipher._other(team))

    def test_a_clue_allows_one_guess_more_than_its_number(self):
        state = self.standard()
        captain, operative = self.roles(state)
        team = state["turn"]
        self.ok(self.act(captain[team], "clue", {"count": 1}))
        own = self.cards(state, team)
        self.assertEqual(self.ok(self.act(operative[team], "guess", {"index": own[0]}))["game"]["turn"]["team"], team)
        game = self.ok(self.act(operative[team], "guess", {"index": own[1]}))["game"]
        self.assertEqual((game["turn"]["team"], game["phase"]), (cipher._other(team), "clue"))

    def test_the_wrong_colour_ends_the_turn(self):
        state = self.standard()
        captain, operative = self.roles(state)
        team = state["turn"]
        self.ok(self.act(captain[team], "clue", {"count": 3}))
        foreign = self.cards(state, cipher._other(team))[0]
        game = self.ok(self.act(operative[team], "guess", {"index": foreign}))["game"]
        self.assertEqual(game["turn"]["team"], cipher._other(team))
        self.assertEqual(game["remaining"][cipher._other(team)], cipher.SECOND_TEAM_CARDS - 1
                         if team == state["first"] else cipher.FIRST_TEAM_CARDS - 1)

    def test_opening_the_virus_hands_the_game_to_the_other_team(self):
        state = self.standard()
        captain, operative = self.roles(state)
        team = state["turn"]
        self.ok(self.act(captain[team], "clue", {"count": 2}))
        virus = self.cards(state, "virus")[0]
        game = self.ok(self.act(operative[team], "guess", {"index": virus}))["game"]
        winner = cipher._other(team)
        self.assertEqual((game["phase"], game["result"]["winner"], game["result"]["reason"]), ("over", winner, "virus"))
        # После конца раскладку видят все.
        self.assertTrue(all("key" in card for card in self.view(operative[team])["game"]["board"]))
        scores = {p["account_id"]: p["score"] for p in self.view("kid1")["players"]}
        winners = {"blue": ("kid1", "kid2"), "red": ("kid3", "kid4")}[winner]
        self.assertEqual({who: scores[self.ids[who]] for who in winners}, {who: 1 for who in winners})
        self.assertEqual(sum(scores.values()), 2)

    def test_finding_every_card_of_your_colour_wins(self):
        state = self.standard()
        captain, operative = self.roles(state)
        team = state["turn"]
        own = self.cards(state, team)
        for index in own[:-1]:
            state["board"][index]["revealed"] = True
        self.write_state(state)
        self.ok(self.act(captain[team], "clue", {"count": 1}))
        game = self.ok(self.act(operative[team], "guess", {"index": own[-1]}))["game"]
        self.assertEqual((game["result"]["winner"], game["result"]["reason"]), (team, "all_found"))

    def test_a_card_cannot_be_opened_twice(self):
        state = self.standard()
        captain, operative = self.roles(state)
        team = state["turn"]
        self.ok(self.act(captain[team], "clue", {"count": 3}))
        own = self.cards(state, team)[0]
        self.ok(self.act(operative[team], "guess", {"index": own}))
        self.assertEqual(self.act(operative[team], "guess", {"index": own}).status_code, 409)

    # --- устойчивость ---------------------------------------------------------------

    def test_a_captain_who_leaves_is_replaced_by_a_teammate(self):
        host = self.seat({"kid1": "blue", "kid2": "blue", "kid5": "blue", "kid3": "red", "kid4": "red"},
                         captains=("kid2", "kid3"))
        self.ok(self.act(host, "start"))
        self.ok(self.post("kid2", f"/api/v4/games/rooms/{self.code}/leave"))
        game = self.view("kid1")["game"]
        self.assertIn(game["phase"], ("clue", "guess"))
        new_captain = game["teams"]["blue"]["captain"]
        self.assertIn(new_captain, (self.ids["kid1"], self.ids["kid5"]))
        # И новый капитан теперь видит раскладку.
        who = "kid1" if new_captain == self.ids["kid1"] else "kid5"
        self.assertTrue(all("key" in card for card in self.view(who)["game"]["board"]))

    def test_a_team_left_with_one_person_ends_the_game_without_points(self):
        self.standard()
        self.ok(self.post("kid2", f"/api/v4/games/rooms/{self.code}/leave"))
        game = self.view("kid1")["game"]
        self.assertEqual((game["phase"], game["result"]["reason"], game["result"]["winner"]), ("over", "too_few", None))
        self.assertEqual(sum(p["score"] for p in self.view("kid1")["players"]), 0)

    def test_a_new_game_after_the_end_keeps_the_teams(self):
        state = self.standard()
        captain, operative = self.roles(state)
        team = state["turn"]
        self.ok(self.act(captain[team], "clue", {"count": 1}))
        self.ok(self.act(operative[team], "guess", {"index": self.cards(state, "virus")[0]}))
        self.ok(self.act("kid1", "start"))
        again = self.state()
        self.assertEqual(again["phase"], "clue")
        self.assertEqual(again["round"], 2)
        self.assertEqual(again["teams"], state["teams"])

    def test_the_spy_route_does_not_drive_a_cipher_room(self):
        self.standard()
        self.assertEqual(self.post("kid1", f"/api/v4/games/rooms/{self.code}/spy/start").status_code, 404)

    def test_organisers_can_switch_ciphers_off_without_touching_spy(self):
        self.ok(self.post("architect", "/api/v4/games/switches/cipher", {"enabled": False}))
        self.assertEqual(self.post("kid1", "/api/v4/games/rooms", {"game": "cipher"}).status_code, 409)
        self.ok(self.post("kid1", "/api/v4/games/rooms", {"game": "spy"}))


class CipherContentTests(unittest.TestCase):
    def test_there_are_enough_distinct_words_for_several_evenings(self):
        words = cipher.content()["words"]
        self.assertGreaterEqual(len(words), cipher.BOARD_SIZE * 4)
        self.assertEqual(len({w["zh"] for w in words}), len(words))

    def test_content_is_marked_unreviewed_until_a_human_checks_the_chinese(self):
        self.assertIs(cipher.content()["reviewed"], False)


if __name__ == "__main__":
    unittest.main()
