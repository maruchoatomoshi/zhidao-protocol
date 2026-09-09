from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from zhidao_v4 import campus
from zhidao_v4.api import create_app
from zhidao_v4.auth import provision_local_account
from zhidao_v4.bootstrap import bootstrap_system_admin
from zhidao_v4.db import connect_database, immediate_transaction


ADMIN_PASSWORD = "correct horse battery staple"
USER_PASSWORD = "another correct horse battery"

# Точки внутри кампуса Линшуй. Обе взяты из рамки настоящих данных, а не
# придуманы: карта считает область по ним же.
INSIDE_A = (110.0210, 18.4035)
INSIDE_B = (110.0250, 18.4060)
FAR_AWAY = (37.6173, 55.7558)   # Москва


class CampusExplorationTests(unittest.TestCase):
    """Туман кампуса: клетка открывается ногами и видна всем в сезоне.

    Проверяется не только «эндпоинт отвечает 200». Механика обещает три
    вещи, и каждая может сломаться молча: клетка открывается один раз,
    открытое не переезжает в следующий сезон, и карта не открывается из дома.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "zhidao.db"
        self.bootstrap = bootstrap_system_admin(
            self.db_path,
            username="architect",
            password=ADMIN_PASSWORD,
            display_name="Архитектор",
        )
        conn = connect_database(self.db_path)
        try:
            with immediate_transaction(conn):
                self.walker = provision_local_account(
                    conn,
                    username="kid1",
                    password=USER_PASSWORD,
                    display_name="Ксения Литвинова",
                    role_code="participant",
                    actor_account_id=self.bootstrap["account"]["id"],
                )
                self.outsider = provision_local_account(
                    conn,
                    username="kid2",
                    password=USER_PASSWORD,
                    display_name="Артём Северов",
                    role_code="participant",
                    actor_account_id=self.bootstrap["account"]["id"],
                )
                conn.execute("UPDATE v4_seasons SET status='active' WHERE id=1")
                conn.execute(
                    "INSERT INTO v4_season_memberships(season_id, account_id, status)"
                    " VALUES (1, ?, 'active')",
                    (self.walker["id"],),
                )
        finally:
            conn.close()
        self.client = TestClient(
            create_app(self.db_path, cookie_secure=False, session_hours=1)
        )

    def tearDown(self):
        self.client.close()
        self.temp_dir.cleanup()

    def login(self, username: str, password: str) -> str:
        response = self.client.post(
            "/api/v4/auth/login", json={"username": username, "password": password}
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["csrf_token"]

    def visit(self, point, *, csrf: str, accuracy: float = 12.0):
        lon, lat = point
        return self.client.post(
            "/api/v4/campus/visits",
            json={"lat": lat, "lon": lon, "accuracy_m": accuracy},
            headers={"X-CSRF-Token": csrf},
        )

    def test_a_cell_opens_once_and_the_map_grows(self):
        csrf = self.login("kid1", USER_PASSWORD)

        first = self.visit(INSIDE_A, csrf=csrf)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertTrue(first.json()["opened"])
        self.assertEqual(first.json()["cells"], 1)

        # Тот же шаг на месте — watchPosition присылает точку каждые
        # несколько секунд, и вторая клетка от этого появляться не должна.
        again = self.visit(INSIDE_A, csrf=csrf)
        self.assertEqual(again.status_code, 200, again.text)
        self.assertFalse(again.json()["opened"])
        self.assertEqual(again.json()["cells"], 1)

        far = self.visit(INSIDE_B, csrf=csrf)
        self.assertTrue(far.json()["opened"])
        self.assertEqual(far.json()["cells"], 2)

    def test_exploration_is_served_in_the_shape_the_map_understands(self):
        csrf = self.login("kid1", USER_PASSWORD)
        self.visit(INSIDE_A, csrf=csrf)

        payload = self.client.get("/api/v4/campus/exploration")
        self.assertEqual(payload.status_code, 200, payload.text)
        body = payload.json()
        self.assertEqual(body["opened"], 1)
        anchor = body["anchor_points"][0]
        # Ровно та форма, которую campus-map.js уже читает у записанных в
        # данных опорных точек: иначе карта молча их проигнорирует.
        self.assertIn("id", anchor)
        self.assertEqual(len(anchor["coordinates"]), 2)
        lon, lat = anchor["coordinates"]
        self.assertAlmostEqual(lon, INSIDE_A[0], delta=campus.GRID)
        self.assertAlmostEqual(lat, INSIDE_A[1], delta=campus.GRID)

    def test_the_map_cannot_be_opened_from_home(self):
        csrf = self.login("kid1", USER_PASSWORD)
        response = self.visit(FAR_AWAY, csrf=csrf)
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.client.get("/api/v4/campus/exploration").json()["opened"], 0)

    def test_a_vague_position_does_not_smear_the_map(self):
        # В здании телефон легко отдаёт 300 метров. Такая точка открыла бы
        # клетку, в которой человек не был.
        csrf = self.login("kid1", USER_PASSWORD)
        response = self.visit(INSIDE_A, csrf=csrf, accuracy=300.0)
        self.assertEqual(response.status_code, 400, response.text)

    def test_someone_outside_the_season_has_nothing_to_open(self):
        csrf = self.login("kid1", USER_PASSWORD)
        self.visit(INSIDE_A, csrf=csrf)
        self.client.post("/api/v4/auth/logout", headers={"X-CSRF-Token": csrf})
        self.client.cookies.clear()

        other = self.login("kid2", USER_PASSWORD)
        # Артём в сезон не введён: карта у него прежняя, а отмечаться негде.
        self.assertEqual(self.client.get("/api/v4/campus/exploration").json()["opened"], 0)
        self.assertEqual(self.visit(INSIDE_B, csrf=other).status_code, 409)

    def test_visits_are_rate_limited(self):
        csrf = self.login("kid1", USER_PASSWORD)
        codes = set()
        for step in range(15):
            point = (INSIDE_A[0] + step * campus.GRID, INSIDE_A[1])
            codes.add(self.visit(point, csrf=csrf).status_code)
        self.assertIn(429, codes)

    def test_the_table_remembers_places_and_not_people(self):
        # Обещание механики, а не деталь реализации: если в таблице однажды
        # появится владелец клетки, это станет историей перемещений детей.
        conn = connect_database(self.db_path)
        try:
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(v4_campus_cells)")
            }
        finally:
            conn.close()
        self.assertEqual(
            columns, {"season_id", "cell_lon", "cell_lat", "opened_at", "visits"}
        )
