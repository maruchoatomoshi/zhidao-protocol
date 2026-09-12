from __future__ import annotations

import json
import tempfile
import unittest
import uuid
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
# Точки внутри кампуса Линшуй — те же, что в тестах тумана.
INSIDE_A = (110.0210, 18.4035)
INSIDE_B = (110.0250, 18.4060)
FAR_AWAY = (37.6173, 55.7558)
# 10:00 по Шанхаю 12 сентября — сезон-день 2026-09-12.
MORNING = datetime(2026, 9, 12, 2, 0, tzinfo=timezone.utc)


class MapMarkTests(unittest.TestCase):
    """Метки на карте (V4_GAMES.md §4.2).

    Обещания: первая за день бесплатно, дальше по 5★, не больше трёх; метку
    видят все в сезоне, а автора не хранит никто; метка открывает туман там,
    где стоят; неточная или чужая позиция не тратит лимит; «полезно» — один
    раз от человека и продлевает жизнь; через двое суток метка исчезает;
    скрывает только вожатый; повтор запроса не ставит метку дважды.
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
                for name, display in (("kid1", "Ксения"), ("kid2", "Артём"), ("kid3", "Вера")):
                    self.ids[name] = provision_local_account(
                        conn, username=name, password=USER_PASSWORD, display_name=display, role_code="participant",
                        actor_account_id=self.bootstrap["account"]["id"])["id"]
                conn.execute("UPDATE v4_seasons SET status='active' WHERE id=1")
                for name in ("kid1", "kid2"):
                    conn.execute("INSERT INTO v4_season_memberships(season_id, account_id, status) VALUES (1, ?, 'active')",
                                 (self.ids[name],))
                conn.execute("INSERT INTO v4_case_wallets(season_id, account_id, stars) VALUES (1, ?, 20)",
                             (self.ids["kid1"],))
        finally:
            conn.close()
        self.now = MORNING
        self.clock = mock.patch("zhidao_v4.marks.utcnow", side_effect=lambda: self.now)
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

    def place(self, who="kid1", point=INSIDE_A, template="careful", word="gecko", accuracy=12.0, key=None):
        lon, lat = point
        return self.clients[who].post(
            "/api/v4/campus/marks",
            headers={"X-CSRF-Token": self.tokens[who], "X-Idempotency-Key": key or uuid.uuid4().hex},
            json={"lat": lat, "lon": lon, "accuracy_m": accuracy, "template": template, "word": word},
        )

    def view(self, who="kid2"):
        response = self.clients[who].get("/api/v4/campus/marks")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def post(self, who, path):
        return self.clients[who].post(path, headers={"X-CSRF-Token": self.tokens[who]})

    def stars(self):
        return self.sql("SELECT stars FROM v4_case_wallets WHERE season_id=1 AND account_id=?", (self.ids["kid1"],))[0]["stars"]

    def test_first_mark_is_free_then_five_stars_and_three_a_day(self):
        fees = [self.place().json()["fee"] for _ in range(3)]
        self.assertEqual(fees, [0, 5, 5])
        self.assertEqual(self.stars(), 10)
        refused = self.place()
        self.assertEqual(refused.status_code, 409)
        self.assertEqual(self.stars(), 10)
        journal = self.sql("SELECT stars_delta, details_json FROM v4_economy_operations WHERE operation='map.mark'")
        self.assertEqual([row["stars_delta"] for row in journal], [-5, -5])
        self.assertEqual({key for row in journal for key in json.loads(row["details_json"])}, {"day", "fee"})

    def test_the_new_day_brings_back_the_free_mark(self):
        for _ in range(3):
            self.place()
        self.now = MORNING + timedelta(days=1)
        response = self.place(point=INSIDE_B)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["fee"], 0)

    def test_everyone_sees_the_mark_and_nobody_stores_the_author(self):
        self.assertEqual(self.place(template="careful", word="gecko").status_code, 200)
        marks = self.view("kid2")["marks"]
        self.assertEqual(len(marks), 1)
        self.assertEqual(marks[0]["text"]["ru"], "Осторожно: геккон")
        self.assertEqual(marks[0]["text"]["zh"], "小心壁虎")
        columns = {row["name"] for row in self.sql("PRAGMA table_info(v4_map_marks)")}
        self.assertFalse({"account_id", "author_account_id", "created_by_account_id"} & columns)
        placed_hour = self.sql("SELECT placed_hour FROM v4_map_marks")[0]["placed_hour"]
        self.assertTrue(placed_hour.startswith("2026-09-12T02:00:00"), placed_hour)
        stored = self.sql("SELECT response_json FROM v4_idempotency_keys WHERE operation='map.mark'")[0]["response_json"]
        self.assertNotIn("mark", json.loads(stored))
        self.assertNotIn("coordinates", stored)

    def test_a_mark_opens_the_fog_where_it_stands(self):
        self.assertEqual(self.place().status_code, 200)
        exploration = self.clients["kid2"].get("/api/v4/campus/exploration").json()
        self.assertEqual(exploration["opened"], 1)

    def test_a_vague_distant_or_unknown_mark_is_refused_without_spending_the_quota(self):
        self.assertEqual(self.place(accuracy=250.0).status_code, 400)
        self.assertEqual(self.place(point=FAR_AWAY).status_code, 400)
        self.assertEqual(self.place(template="nope").status_code, 400)
        self.assertEqual(self.place(word="nope").status_code, 400)
        response = self.place()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["fee"], 0)
        self.assertEqual(response.json()["quota"]["left"], 2)

    def test_useful_counts_once_per_person_and_extends_the_life(self):
        mark = self.place().json()["mark"]
        first = self.post("kid2", f"/api/v4/campus/marks/{mark['id']}/useful")
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["useful"], 1)
        self.assertEqual(self.post("kid2", f"/api/v4/campus/marks/{mark['id']}/useful").status_code, 409)
        self.now = MORNING + timedelta(hours=59)
        self.assertEqual(len(self.view("kid2")["marks"]), 1)
        self.now = MORNING + timedelta(hours=61)
        self.assertEqual(self.view("kid2")["marks"], [])

    def test_marks_fade_after_two_days_and_take_their_votes_along(self):
        mark = self.place().json()["mark"]
        self.post("kid2", f"/api/v4/campus/marks/{mark['id']}/useful")
        self.now = MORNING + timedelta(hours=48, minutes=1) + timedelta(hours=12)
        self.assertEqual(self.view("kid2")["marks"], [])
        self.place(point=INSIDE_B)   # любая запись чистит истёкшее
        self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM v4_map_mark_votes")[0]["n"], 0)

    def test_only_staff_can_hide_a_mark(self):
        mark = self.place().json()["mark"]
        self.assertEqual(self.post("kid2", f"/api/v4/campus/marks/{mark['id']}/hide").status_code, 403)
        self.assertEqual(self.post("architect", f"/api/v4/campus/marks/{mark['id']}/hide").status_code, 200)
        self.assertEqual(self.view("kid2")["marks"], [])
        staff_view = self.view("architect")
        self.assertTrue(staff_view["can_moderate"])
        self.assertTrue(staff_view["marks"][0]["hidden"])

    def test_retry_with_the_same_key_does_not_place_twice(self):
        key = uuid.uuid4().hex
        first = self.place(key=key)
        second = self.place(key=key, point=INSIDE_B)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.headers["X-Idempotent-Replayed"], "true")
        self.assertEqual(len(self.view("kid2")["marks"]), 1)
        self.assertEqual(self.view("kid1")["quota"]["used"], 1)

    def test_someone_outside_the_season_has_no_marks(self):
        self.assertEqual(self.view("kid3"), {"season_id": None, "marks": [], "quota": None, "can_moderate": False})
        self.assertEqual(self.place(who="kid3").status_code, 409)


if __name__ == "__main__":
    unittest.main()
