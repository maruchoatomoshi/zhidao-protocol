from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from zhidao_v4 import rooms, smuggle
from zhidao_v4.api import create_app
from zhidao_v4.auth import provision_local_account
from zhidao_v4.bootstrap import bootstrap_system_admin
from zhidao_v4.db import connect_database, immediate_transaction


ADMIN_PASSWORD = "correct horse battery staple"
USER_PASSWORD = "another correct horse battery"
KIDS = ("kid1", "kid2", "kid3", "kid4")


class SmuggleTests(unittest.TestCase):
    """Контрабанда (V4_GAMES.md §4.12).

    Обещания (решения пользователя 2026-09-13): рука и сумка видны только
    владельцу; в режиме «Иероглифы» таможенник во вскрытой сумке видит только
    знаки; заявить можно только разрешённый товар, число товаров честное;
    пропуск отдаёт взятку, вскрытая честная сумка стоит таможеннику штрафов,
    отмеченная запрещёнка конфискуется, неотмеченная проскальзывает, ложная
    отметка стоит таможеннику; роли и события меняют правила; в итоге юани,
    товары, короли рынка и сеты; победитель партии от четырёх игроков получает
    10★, но не чаще раза в день; юани — только в комнате.
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
                for index, name in enumerate(KIDS, start=1):
                    account = provision_local_account(conn, username=name, password=USER_PASSWORD,
                                                      display_name=f"Купец {index}", role_code="participant",
                                                      actor_account_id=bootstrap["account"]["id"])
                    self.ids[name] = int(account["id"])
                    conn.execute("INSERT INTO v4_season_memberships(season_id, account_id, status) VALUES (1, ?, 'active')",
                                 (self.ids[name],))
                conn.execute("UPDATE v4_seasons SET status='active' WHERE id=1")
        finally:
            conn.close()
        self.app = create_app(self.db_path, cookie_secure=False, session_hours=1)
        self.sessions: dict[str, tuple[TestClient, str]] = {}
        self.code = None

    def tearDown(self):
        for client, _ in self.sessions.values():
            client.close()
        self.temp_dir.cleanup()

    # --- помощники ---------------------------------------------------------------------

    def session(self, username):
        if username not in self.sessions:
            client = TestClient(self.app)
            response = client.post("/api/v4/auth/login", json={"username": username, "password": USER_PASSWORD})
            self.assertEqual(response.status_code, 200, response.text)
            self.sessions[username] = (client, response.json()["csrf_token"])
        return self.sessions[username]

    def post(self, who, path, body=None):
        client, csrf = self.session(who)
        return client.post(path, json=body or {}, headers={"X-CSRF-Token": csrf})

    def act(self, who, action, body=None):
        return self.post(who, f"/api/v4/games/rooms/{self.code}/smuggle/{action}", body)

    def ok(self, response):
        self.assertLess(response.status_code, 300, response.text)
        return response.json()

    def seen(self, who):
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

    def pid(self, who):
        return str(self.ids[who])

    def table(self, players=KIDS, mode=None):
        host, *others = players
        self.code = self.ok(self.post(host, "/api/v4/games/rooms", {"game": "smuggle"}))["room"]["code"]
        for who in others:
            self.ok(self.post(who, "/api/v4/games/rooms/join", {"code": self.code}))
        if mode:
            self.ok(self.post(host, f"/api/v4/games/rooms/{self.code}/settings", {"mode": mode}))
        self.ok(self.act(host, "start"))

    def rig(self, players=KIDS, officer="kid1", event="calm", hands=None, roles=None, stalls=None, rounds=None):
        """Раскладывает раунд по-своему: кто таможенник, что на руках, какие роли."""
        state = self.state()
        hands, roles, stalls = hands or {}, roles or {}, stalls or {}
        state["order"] = [self.pid(p) for p in players]
        state["officer"] = self.pid(officer)
        state["event"] = event
        state["round"] = 1
        state["rounds"] = rounds or len(players)
        for who in players:
            state["players"][self.pid(who)].update(hand=list(hands.get(who, ["mango"] * 6)), money=30,
                                                   stall=[{"code": c, "bonus": 0} for c in stalls.get(who, [])],
                                                   role=roles.get(who, "informant"), role_used=False)
        state.update(phase="pack", bags={}, decisions={}, opened=[], peek={}, double=[], opens_used=0,
                     last_round=None, result=None)
        self.write_state(state)

    def pack(self, who, cards=(0,), declared="mango", bribe=0, trick=None):
        body = {"cards": list(cards), "declared": declared, "bribe": bribe}
        if trick:
            body["trick"] = trick
        return self.act(who, "pack", body)

    def money(self, who):
        return self.state()["players"][self.pid(who)]["money"]

    def stall(self, who):
        return [item["code"] for item in self.state()["players"][self.pid(who)]["stall"]]

    def wallet(self, who):
        conn = connect_database(self.db_path)
        try:
            row = conn.execute("SELECT stars FROM v4_case_wallets WHERE season_id=1 AND account_id=?", (self.ids[who],)).fetchone()
            return int(row["stars"]) if row else 0
        finally:
            conn.close()

    # --- тайны --------------------------------------------------------------------------

    def test_hands_and_bags_stay_private_and_hanzi_mode_hides_the_translation(self):
        self.table()
        self.rig(hands={"kid2": ["pearl", "mango", "mango", "rice", "tea", "tea"]})
        self.assertEqual(len(self.seen("kid2")["you"]["hand"]), 6)
        self.ok(self.pack("kid2", cards=(0, 1), bribe=4))
        self.ok(self.pack("kid3"))
        self.ok(self.pack("kid4"))
        rival = json.dumps(self.seen("kid3"))
        self.assertNotIn("pearl", rival)
        self.assertNotIn("珍珠", rival)
        officer = self.seen("kid1")
        self.assertEqual(officer["bags"][self.pid("kid2")], {"declared": "mango", "count": 2})
        self.assertEqual(officer["you"]["bribes"][self.pid("kid2")], 4)
        self.assertEqual(officer["you"]["inspecting"], {})
        self.ok(self.act("kid1", "open", {"merchant": self.ids["kid2"]}))
        inspecting = self.seen("kid1")["you"]["inspecting"][self.pid("kid2")]
        self.assertEqual(inspecting, [{"zh": "珍珠"}, {"zh": "芒果"}])
        self.assertNotIn("inspecting", self.seen("kid3").get("you", {}))

    def test_translated_mode_shows_the_officer_the_translation(self):
        self.table(mode="translated")
        self.rig()
        for who in ("kid2", "kid3", "kid4"):
            self.ok(self.pack(who))
        self.ok(self.act("kid1", "open", {"merchant": self.ids["kid2"]}))
        self.assertEqual(self.seen("kid1")["you"]["inspecting"][self.pid("kid2")][0]["ru"], "манго")

    # --- сумка ------------------------------------------------------------------------------

    def test_packing_rules(self):
        self.table()
        self.rig(hands={"kid2": ["pearl"] + ["mango"] * 5})
        self.assertEqual(self.pack("kid2", declared="pearl").status_code, 400)
        self.assertEqual(self.pack("kid2", cards=()).status_code, 400)
        self.assertEqual(self.pack("kid2", cards=(0, 1, 2, 3, 4, 5)).status_code, 400)
        self.assertEqual(self.pack("kid2", bribe=31).status_code, 409)
        self.assertEqual(self.pack("kid1").status_code, 403)                        # таможенник
        self.assertEqual(self.pack("kid2", trick="hack").status_code, 409)          # не его роль
        self.ok(self.pack("kid2"))
        self.assertEqual(self.pack("kid2").status_code, 409)
        self.ok(self.act("kid2", "unpack"))
        self.assertEqual(len(self.seen("kid2")["you"]["hand"]), 6)

    def test_events_typhoon_and_lantern_limit_the_bag_and_the_bribe(self):
        self.table()
        self.rig(event="typhoon")
        self.assertEqual(self.pack("kid2", cards=(0, 1, 2, 3)).status_code, 400)
        self.ok(self.pack("kid2", cards=(0, 1, 2)))
        self.rig(event="lantern")
        self.assertEqual(self.pack("kid2", bribe=6).status_code, 409)
        self.ok(self.pack("kid2", bribe=5))

    # --- досмотр ------------------------------------------------------------------------------

    def test_passing_pays_the_bribe_and_every_good_reaches_the_stall(self):
        self.table()
        self.rig(hands={"kid2": ["pearl", "mango"] + ["rice"] * 4})
        self.ok(self.pack("kid2", cards=(0, 1), bribe=5))
        self.ok(self.pack("kid3"))
        self.ok(self.pack("kid4"))
        self.ok(self.act("kid1", "pass", {"merchant": self.ids["kid2"]}))
        self.assertEqual((self.money("kid2"), self.money("kid1")), (25, 35))
        self.assertEqual(sorted(self.stall("kid2")), ["mango", "pearl"])

    def test_an_honest_bag_that_was_opened_costs_the_officer(self):
        self.table()
        self.rig()
        self.ok(self.pack("kid2", cards=(0, 1, 2)))
        self.ok(self.pack("kid3"))
        self.ok(self.pack("kid4"))
        self.ok(self.act("kid1", "open", {"merchant": self.ids["kid2"]}))
        self.ok(self.act("kid1", "judge", {"merchant": self.ids["kid2"], "marks": []}))
        self.assertEqual((self.money("kid2"), self.money("kid1")), (36, 24))
        self.assertEqual(self.stall("kid2"), ["mango"] * 3)

    def test_marked_contraband_is_confiscated_unmarked_slips_and_a_false_mark_costs(self):
        self.table()
        self.rig(hands={"kid2": ["pearl", "disc", "mango", "rice", "rice", "tea"]})
        self.ok(self.pack("kid2", cards=(0, 1, 2)))
        self.ok(self.pack("kid3"))
        self.ok(self.pack("kid4"))
        self.assertEqual(self.act("kid1", "judge", {"merchant": self.ids["kid2"], "marks": [0]}).status_code, 409)
        self.ok(self.act("kid1", "open", {"merchant": self.ids["kid2"]}))
        self.ok(self.act("kid1", "judge", {"merchant": self.ids["kid2"], "marks": [0, 2]}))
        self.assertEqual((self.money("kid2"), self.money("kid1")), (30 - 5 + 2, 30 + 5 - 2))
        self.assertEqual(sorted(self.stall("kid2")), ["disc", "mango"])
        self.ok(self.act("kid1", "pass", {"merchant": self.ids["kid3"]}))
        self.ok(self.act("kid1", "pass", {"merchant": self.ids["kid4"]}))
        merchant = self.seen("kid2")["last_round"]["decisions"][self.pid("kid2")]
        public = self.seen("kid3")["last_round"]["decisions"][self.pid("kid2")]
        self.assertEqual((merchant["confiscated"], merchant["slipped"]), (["pearl"], 1))
        self.assertNotIn("slipped", public)
        self.assertEqual(self.seen("kid3")["round"], 2)

    def test_raid_doubles_fines_and_duty_free_allows_one_opening(self):
        self.table()
        self.rig(event="raid", hands={"kid2": ["phone"] + ["mango"] * 5})
        self.ok(self.pack("kid2", cards=(0,)))
        self.ok(self.pack("kid3"))
        self.ok(self.pack("kid4"))
        self.ok(self.act("kid1", "open", {"merchant": self.ids["kid2"]}))
        self.ok(self.act("kid1", "judge", {"merchant": self.ids["kid2"], "marks": [0]}))
        self.assertEqual(self.money("kid2"), 30 - 10)
        self.rig(event="dutyfree")
        for who in ("kid2", "kid3", "kid4"):
            self.ok(self.pack(who))
        self.ok(self.act("kid1", "open", {"merchant": self.ids["kid2"]}))
        self.assertEqual(self.act("kid1", "open", {"merchant": self.ids["kid3"]}).status_code, 409)

    # --- роли ---------------------------------------------------------------------------------

    def test_merchant_roles_double_bottom_and_hack(self):
        self.table()
        self.rig(roles={"kid2": "virtuoso", "kid3": "hacker"},
                 hands={"kid2": ["pearl", "mango"] + ["rice"] * 4, "kid3": ["phone"] + ["tea"] * 5})
        self.ok(self.pack("kid2", cards=(0, 1), trick="compartment"))
        self.ok(self.pack("kid3", cards=(0,), declared="tea", bribe=10, trick="hack"))
        self.ok(self.pack("kid4"))
        hacked = self.seen("kid1")["decisions"][self.pid("kid3")]
        self.assertEqual((hacked["kind"], hacked["bribe"]), ("hacked", 0))
        self.assertEqual(self.act("kid1", "open", {"merchant": self.ids["kid3"]}).status_code, 409)
        self.assertEqual(self.stall("kid3"), ["phone"])
        self.ok(self.act("kid1", "open", {"merchant": self.ids["kid2"]}))
        self.ok(self.act("kid1", "judge", {"merchant": self.ids["kid2"], "marks": []}))
        self.assertEqual(sorted(self.stall("kid2")), ["mango", "pearl"])       # двойное дно: сумка «честная»
        self.assertEqual(self.money("kid1"), 30 - (5 + 2))

    def test_officer_roles_peek_and_double_fines_once(self):
        self.table()
        self.rig(roles={"kid1": "inspector"}, hands={"kid4": ["phone"] + ["rice"] * 5})
        for who in ("kid2", "kid3"):
            self.ok(self.pack(who))
        self.ok(self.pack("kid4", cards=(0,), declared="rice"))
        self.assertEqual(self.act("kid1", "peek", {"merchant": self.ids["kid2"]}).status_code, 409)   # не его роль
        self.ok(self.act("kid1", "double", {"merchant": self.ids["kid4"]}))
        self.assertEqual(self.act("kid1", "double", {"merchant": self.ids["kid3"]}).status_code, 409)
        self.ok(self.act("kid1", "open", {"merchant": self.ids["kid4"]}))
        self.ok(self.act("kid1", "judge", {"merchant": self.ids["kid4"], "marks": [0]}))
        self.assertEqual(self.money("kid4"), 30 - 10)
        self.rig(roles={"kid1": "informant"})
        for who in ("kid2", "kid3", "kid4"):
            self.ok(self.pack(who))
        self.ok(self.act("kid1", "peek", {"merchant": self.ids["kid2"]}))
        self.assertEqual(self.seen("kid1")["you"]["peek"][self.pid("kid2")]["card"], {"zh": "芒果"})
        self.assertNotIn("peek", self.seen("kid2")["you"])

    # --- итоги и приз ----------------------------------------------------------------------------

    def finish_with_kid2_ahead(self):
        self.rig(rounds=1, stalls={"kid2": ["mango"] * 3, "kid3": ["mango"]})
        for who in ("kid2", "kid3", "kid4"):
            self.ok(self.pack(who))
        for who in ("kid2", "kid3", "kid4"):
            self.ok(self.act("kid1", "pass", {"merchant": self.ids[who]}))
        return self.seen("kid2")

    def test_the_final_score_counts_money_goods_kings_and_the_winner_gets_ten_stars_once_a_day(self):
        self.table()
        game = self.finish_with_kid2_ahead()
        self.assertEqual(game["phase"], "over")
        scores = game["result"]["scores"]
        self.assertEqual(scores[self.pid("kid2")], {"money": 30, "goods": 8, "king": 8, "sets": 0, "contraband": 0, "total": 46})
        self.assertEqual(scores[self.pid("kid3")]["king"], 4)                     # королева рынка
        self.assertEqual(game["result"]["winners"], [self.ids["kid2"]])
        self.assertEqual(game["result"]["prizes"], {self.pid("kid2"): "granted"})
        self.assertEqual(self.wallet("kid2"), 10)
        self.ok(self.act("kid1", "start"))
        again = self.finish_with_kid2_ahead()
        self.assertEqual(again["game"], 2)
        self.assertEqual(again["result"]["prizes"], {self.pid("kid2"): "limited"})
        self.assertEqual(self.wallet("kid2"), 10)

    def test_a_three_player_game_brings_no_prize_and_leaving_below_three_ends_it(self):
        self.table(players=("kid1", "kid2", "kid3"))
        self.rig(players=("kid1", "kid2", "kid3"), rounds=1, stalls={"kid2": ["pearl"]})
        for who in ("kid2", "kid3"):
            self.ok(self.pack(who))
        for who in ("kid2", "kid3"):
            self.ok(self.act("kid1", "pass", {"merchant": self.ids[who]}))
        self.assertEqual(self.seen("kid1")["result"]["prizes"], {})
        self.assertEqual(self.wallet("kid2"), 0)
        self.ok(self.act("kid1", "start"))
        self.ok(self.post("kid3", f"/api/v4/games/rooms/{self.code}/leave"))
        game = self.seen("kid1")
        self.assertEqual((game["phase"], game["result"]["reason"]), ("over", "too_few"))


if __name__ == "__main__":
    unittest.main()
