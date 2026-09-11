from __future__ import annotations

import shutil
import sqlite3
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from zhidao_v4 import diary
from zhidao_v4.api import create_app
from zhidao_v4.auth import provision_local_account
from zhidao_v4.db import connect_database, immediate_transaction
from zhidao_v4.migrations import DEFAULT_MIGRATION_DIR, apply_migrations


PASSWORD = "a secure testing password"


def today() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()


def days_ago(n: int) -> str:
    return (datetime.now(ZoneInfo("Asia/Shanghai")).date() - timedelta(days=n)).isoformat()


class DiaryTests(unittest.TestCase):
    """Оценка бумажного дневника.

    Проверяются обещания, от которых зависит честность рейтинга и кошелька:
    начисляется разница, а не сумма; попытка за 3★ выдаётся раз в день;
    потраченные ★ не уводят баланс в минус; два вожатых не перезаписывают друг
    друга молча; повтор запроса не удваивает награду; участник не ставит оценки.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "diary.sqlite"
        apply_migrations(self.path)
        conn = connect_database(self.path)
        with immediate_transaction(conn):
            self.ids = {}
            for name, role in [("staff", "operator"), ("staff2", "operator"),
                               ("alice", "participant"), ("boris", "participant")]:
                self.ids[name] = provision_local_account(conn, username=name, password=PASSWORD,
                                                         display_name=name.capitalize(), role_code=role)["id"]
            conn.execute("INSERT INTO v4_seasons(id,code,name,status) VALUES (1,'hainan','Hainan','active')")
            for name in ("alice", "boris"):
                conn.execute("INSERT INTO v4_season_memberships(season_id,account_id,status) VALUES (1,?,'active')",
                             (self.ids[name],))
        conn.close()
        self.app = create_app(self.path, cookie_secure=False)
        self.clients, self.tokens = {}, {}
        for name in self.ids:
            client = TestClient(self.app)
            response = client.post("/api/v4/auth/login", json={"username": name, "password": PASSWORD})
            self.assertEqual(response.status_code, 200, response.text)
            self.clients[name], self.tokens[name] = client, response.json()["csrf_token"]

    def tearDown(self):
        for client in self.clients.values():
            client.close()
        self.temp.cleanup()

    def rate(self, stars, bonus=False, who="alice", date=None, revision=None, actor="staff", key=None):
        if revision is None:
            revision = self.revision(who, date or today())
        return self.clients[actor].post(
            "/api/v4/seasons/1/diary/ratings",
            headers={"X-CSRF-Token": self.tokens[actor], "X-Idempotency-Key": key or uuid.uuid4().hex},
            json={"account_id": self.ids[who], "entry_date": date or today(), "stars": stars,
                  "bonus": bonus, "expected_revision": revision},
        )

    def revision(self, who, date):
        row = self.sql("SELECT revision FROM v4_diary_ratings WHERE account_id=? AND entry_date=?",
                       (self.ids[who], date))
        return row[0][0] if row else 0

    def wallet(self, who="alice"):
        row = self.sql("SELECT stars, scans, rep FROM v4_case_wallets WHERE season_id=1 AND account_id=?",
                       (self.ids[who],))
        return tuple(row[0]) if row else (0, 0, 0)

    def sql(self, query, values=()):
        conn = connect_database(self.path)
        try:
            return conn.execute(query, values).fetchall()
        finally:
            conn.close()

    def ok(self, response):
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    # --- награды ----------------------------------------------------------------

    def test_a_rating_pays_rep_and_half_as_many_stars(self):
        rules = diary.rules()
        self.assertEqual(rules["rep"], [0, 15, 30, 50])
        self.assertEqual(rules["stars"], [0, 8, 15, 25])
        self.ok(self.rate(2))
        self.assertEqual(self.wallet(), (15, 0, 30))
        op = self.sql("SELECT operation, rep_delta, stars_delta, rep_after FROM v4_economy_operations")
        self.assertEqual([tuple(r) for r in op], [("diary.rate", 30, 15, 30)])

    def test_re_rating_pays_the_difference_not_the_sum(self):
        self.ok(self.rate(2))
        body = self.ok(self.rate(3, bonus=True))
        self.assertEqual((body["rep_delta"], body["stars_delta"]), (40, 20))
        self.assertEqual(self.wallet()[0::2], (35, 70))
        self.assertEqual(self.sql("SELECT COUNT(*) FROM v4_economy_operations")[0][0], 2)

    def test_three_stars_grant_one_case_attempt_per_day_only_once(self):
        self.ok(self.rate(3))
        self.assertEqual(self.wallet()[1], 1)
        self.ok(self.rate(2))
        self.ok(self.rate(3))
        self.assertEqual(self.wallet()[1], 1)
        # Другой день — своя попытка.
        self.ok(self.rate(3, date=days_ago(1)))
        self.assertEqual(self.wallet()[1], 2)

    def test_spent_stars_do_not_push_the_balance_below_zero(self):
        self.ok(self.rate(3))
        conn = connect_database(self.path)
        conn.execute("UPDATE v4_case_wallets SET stars=5 WHERE account_id=?", (self.ids["alice"],))
        conn.close()
        body = self.ok(self.rate(0))
        self.assertEqual(self.wallet(), (0, 1, 0))
        self.assertTrue(body["stars_clamped"])
        self.assertEqual(body["stars_delta"], -5)
        self.assertEqual(body["rep_delta"], -50)

    def test_the_same_rating_twice_changes_nothing(self):
        self.ok(self.rate(1))
        body = self.ok(self.rate(1))
        self.assertFalse(body["changed"])
        self.assertEqual(self.sql("SELECT COUNT(*) FROM v4_economy_operations")[0][0], 1)
        self.assertEqual(self.revision("alice", today()), 1)

    # --- совместная работа и повторы -------------------------------------------------

    def test_two_operators_cannot_silently_overwrite_each_other(self):
        self.ok(self.rate(2, revision=0))
        stale = self.rate(3, revision=0, actor="staff2")
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertEqual(self.wallet()[2], 30)

    def test_a_repeated_request_does_not_pay_twice(self):
        first = self.rate(3, key="diary-replay-1", revision=0)
        again = self.rate(3, key="diary-replay-1", revision=0)
        self.assertEqual(again.json(), first.json())
        self.assertEqual(again.headers["x-idempotent-replayed"], "true")
        self.assertEqual(self.wallet(), (25, 1, 50))
        self.assertEqual(self.rate(2, key="diary-replay-1", revision=0).status_code, 409)

    # --- права и границы ----------------------------------------------------------

    def test_participants_cannot_rate_and_non_members_cannot_be_rated(self):
        self.assertEqual(self.rate(3, who="alice", actor="alice").status_code, 403)
        self.assertEqual(self.rate(3, who="staff2").status_code, 403)

    def test_dates_must_be_real_and_not_in_the_future(self):
        tomorrow = (datetime.now(ZoneInfo("Asia/Shanghai")).date() + timedelta(days=1)).isoformat()
        self.assertEqual(self.rate(2, date=tomorrow, revision=0).status_code, 400)
        self.assertEqual(self.rate(2, date="2026-02-30", revision=0).status_code, 400)
        self.assertEqual(self.rate(4, revision=0).status_code, 422)
        conn = connect_database(self.path)
        conn.execute("UPDATE v4_seasons SET starts_on=? WHERE id=1", (today(),))
        conn.close()
        self.assertEqual(self.rate(2, date=days_ago(3), revision=0).status_code, 400)

    def test_a_closed_season_cannot_be_rated(self):
        conn = connect_database(self.path)
        conn.execute("UPDATE v4_seasons SET status='closed' WHERE id=1")
        conn.close()
        self.assertEqual(self.rate(2, revision=0).status_code, 409)

    # --- что видят люди -------------------------------------------------------------

    def test_a_participant_sees_their_own_ratings_and_a_shared_leaderboard(self):
        self.ok(self.rate(3, bonus=True))
        self.ok(self.rate(1, who="boris"))
        mine = self.ok(self.clients["alice"].get("/api/v4/seasons/1/diary/mine"))
        self.assertEqual((mine["total_stars"], mine["bonus_count"], mine["rep"]), (3, 1, 70))
        self.assertEqual(len(mine["items"]), 1)
        board = self.ok(self.clients["boris"].get("/api/v4/seasons/1/diary/leaderboard"))["items"]
        self.assertEqual([row["display_name"] for row in board], ["Alice", "Boris"])
        self.assertEqual(board[0]["diary_rep"], 70)
        self.assertTrue(board[1]["is_you"])
        # В общем рейтинге нет оценок по дням — только итоги.
        self.assertNotIn("items", board[0])
        anon = TestClient(self.app)
        self.assertEqual(anon.get("/api/v4/seasons/1/diary/leaderboard").status_code, 401)
        anon.close()

    def test_the_day_sheet_is_for_operators_only(self):
        self.ok(self.rate(2))
        sheet = self.ok(self.clients["staff"].get(f"/api/v4/seasons/1/diary/day?date={today()}"))
        rows = {row["display_name"]: row for row in sheet["members"]}
        self.assertEqual(set(rows), {"Alice", "Boris"})
        self.assertEqual((rows["Alice"]["stars"], rows["Alice"]["revision"], rows["Alice"]["rated_by"]), (2, 1, "Staff"))
        self.assertEqual((rows["Boris"]["stars"], rows["Boris"]["revision"]), (0, 0))
        self.assertEqual(self.clients["alice"].get("/api/v4/seasons/1/diary/day").status_code, 403)

    def test_case_operations_keep_the_real_rep_after_a_diary_rating(self):
        self.ok(self.rate(2))
        grant = self.clients["staff"].post(
            "/api/v4/seasons/1/cases/admin/grants",
            headers={"X-CSRF-Token": self.tokens["staff"], "X-Idempotency-Key": uuid.uuid4().hex},
            json={"account_ids": [self.ids["alice"]], "group_id": None, "amount": 1, "reason": "Проверка"},
        )
        self.assertEqual(grant.status_code, 200, grant.text)
        row = self.sql("SELECT rep_delta, rep_after FROM v4_economy_operations WHERE operation='case.grant'")[0]
        self.assertEqual(tuple(row), (0, 30))


class DiaryMigrationTests(unittest.TestCase):
    def test_the_ledger_rebuild_keeps_old_operations_and_stays_append_only(self):
        with tempfile.TemporaryDirectory() as temp:
            old_dir = Path(temp) / "old"
            old_dir.mkdir()
            for path in sorted(DEFAULT_MIGRATION_DIR.glob("*.sql")):
                if path.name < "0010":
                    shutil.copy(path, old_dir / path.name)
            db = Path(temp) / "ledger.sqlite"
            apply_migrations(db, old_dir)
            conn = connect_database(db)
            with immediate_transaction(conn):
                account = provision_local_account(conn, username="kid", password=PASSWORD,
                                                  display_name="Kid", role_code="participant")["id"]
                conn.execute("INSERT INTO v4_seasons(id,code,name,status) VALUES (1,'hainan','Hainan','active')")
                conn.execute("INSERT INTO v4_season_memberships(season_id,account_id,status) VALUES (1,?,'active')", (account,))
                conn.execute("INSERT INTO v4_case_wallets(season_id,account_id,stars,scans) VALUES (1,?,30,2)", (account,))
                conn.execute("""INSERT INTO v4_economy_operations(season_id,account_id,actor_account_id,operation,
                    stars_delta,scans_delta,stars_after,scans_after,details_json)
                    VALUES (1,?,?,'case.open',30,-1,30,2,'{"prize":"small"}')""", (account, account))
            conn.close()

            # Первой применяется пересборка журнала; следом могут идти более новые миграции.
            self.assertEqual(apply_migrations(db)[0], "0010_diary_ratings.sql")
            conn = connect_database(db)
            try:
                row = conn.execute("SELECT operation, stars_delta, scans_delta, rep_delta, rep_after, details_json "
                                   "FROM v4_economy_operations").fetchone()
                self.assertEqual(tuple(row), ("case.open", 30, -1, 0, 0, '{"prize":"small"}'))
                self.assertEqual(tuple(conn.execute("SELECT stars, scans, rep FROM v4_case_wallets").fetchone()), (30, 2, 0))
                with self.assertRaises(sqlite3.DatabaseError):
                    conn.execute("UPDATE v4_economy_operations SET stars_delta=999")
                with self.assertRaises(sqlite3.DatabaseError):
                    conn.execute("DELETE FROM v4_economy_operations")
                self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
