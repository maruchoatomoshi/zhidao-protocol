from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from zhidao_v4 import rooms
from zhidao_v4.auth import provision_local_account
from zhidao_v4.bootstrap import bootstrap_system_admin
from zhidao_v4.db import connect_database, immediate_transaction


ADMIN_PASSWORD = "correct horse battery staple"
USER_PASSWORD = "another correct horse battery"


class GameRoomsSeasonTests(unittest.TestCase):
    """Migration 0026: v4_game_rooms.season_id (V4_GAMES.md audit, 2026-09-17).

    A room now belongs to exactly one season, resolved from the host at
    creation, and joining is refused across seasons — closing the gap where
    an account in more than one season could leave a room's points with no
    clear season to count toward.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "zhidao.db"
        bootstrap = bootstrap_system_admin(
            self.db_path, username="architect", password=ADMIN_PASSWORD, display_name="Архитектор"
        )
        self.admin_id = int(bootstrap["account"]["id"])
        self.ids: dict[str, int] = {}
        conn = connect_database(self.db_path)
        try:
            with immediate_transaction(conn):
                for name in ("alice", "boris", "carl"):
                    account = provision_local_account(
                        conn, username=name, password=USER_PASSWORD,
                        display_name=name.capitalize(), role_code="participant",
                    )
                    self.ids[name] = int(account["id"])
                # A second season alice belongs to, so the resolver has an
                # actual choice to make, not just one row lying around.
                conn.execute("INSERT INTO v4_seasons(id, code, name, status, timezone) "
                             "VALUES (2, 'later', 'Later season', 'draft', 'Asia/Shanghai')")
                conn.execute("UPDATE v4_seasons SET status='active' WHERE id=1")
                conn.execute("INSERT INTO v4_season_memberships(season_id, account_id, status) VALUES (1, ?, 'active')",
                             (self.ids["alice"],))
                conn.execute("INSERT INTO v4_season_memberships(season_id, account_id, status) VALUES (2, ?, 'active')",
                             (self.ids["alice"],))
                conn.execute("INSERT INTO v4_season_memberships(season_id, account_id, status) VALUES (1, ?, 'active')",
                             (self.ids["boris"],))
                # carl: never a member of anything.
        finally:
            conn.close()

    def conn(self):
        return connect_database(self.db_path)

    def test_room_records_the_hosts_active_season(self):
        conn = self.conn()
        with immediate_transaction(conn):
            room = rooms.create_room(conn, self.ids["boris"], "spy", {}, rooms.utcnow())
        self.assertEqual(int(room["season_id"]), 1)
        conn.close()

    def test_membership_in_more_than_one_active_season_picks_the_newest(self):
        conn = self.conn()
        with immediate_transaction(conn):
            conn.execute("UPDATE v4_seasons SET status='active' WHERE id=2")
        with immediate_transaction(conn):
            room = rooms.create_room(conn, self.ids["alice"], "spy", {}, rooms.utcnow())
        self.assertEqual(int(room["season_id"]), 2)
        conn.close()

    def test_creating_a_room_without_any_active_season_is_refused(self):
        conn = self.conn()
        with self.assertRaises(rooms.GameError) as cm:
            with immediate_transaction(conn):
                rooms.create_room(conn, self.ids["carl"], "spy", {}, rooms.utcnow())
        self.assertEqual(cm.exception.status_code, 403)
        conn.close()

    def test_joining_a_room_from_a_different_season_is_refused(self):
        conn = self.conn()
        with immediate_transaction(conn):
            room = rooms.create_room(conn, self.ids["boris"], "spy", {}, rooms.utcnow())
        with self.assertRaises(rooms.GameError) as cm:
            with immediate_transaction(conn):
                rooms.join_room(conn, self.ids["carl"], room["code"], rooms.utcnow(), joinable=lambda r: True)
        self.assertEqual(cm.exception.status_code, 403)
        conn.close()

    def test_joining_a_room_from_the_same_season_works(self):
        conn = self.conn()
        with immediate_transaction(conn):
            room = rooms.create_room(conn, self.ids["boris"], "spy", {}, rooms.utcnow())
        with immediate_transaction(conn):
            joined = rooms.join_room(conn, self.ids["alice"], room["code"], rooms.utcnow(), joinable=lambda r: True)
        self.assertEqual(int(joined["season_id"]), 1)
        conn.close()


if __name__ == "__main__":
    unittest.main()
