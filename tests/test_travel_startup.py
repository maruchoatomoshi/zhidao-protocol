from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TravelStartupTests(unittest.TestCase):
    def test_api_initializes_an_isolated_database_and_reports_health(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = root / "travel.db"
            env = os.environ.copy()
            env.update(
                {
                    "ZHIDAO_DB_PATH": str(db_path),
                    "ZHIDAO_API_ERROR_LOG": str(root / "api-error.log"),
                    "TELEGRAM_AUTH_REQUIRED": "1",
                    "ZHIDAO_ENABLE_WAL_CHECKPOINT": "0",
                }
            )
            code = """
import json
import os
import sqlite3
import zhidao_api_ready as api

health = api.api_health()
conn = sqlite3.connect(os.environ["ZHIDAO_DB_PATH"])
tables = {row[0] for row in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table'"
)}
conn.close()
print(json.dumps({
    "health": health,
    "table_count": len(tables),
    "required_tables": sorted({"users", "events", "economy_log", "admin_action_logs"} & tables),
}))
"""
            result = subprocess.run(
                [sys.executable, "-c", code],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout.strip().splitlines()[-1])
            self.assertEqual(payload["health"]["status"], "ok")
            self.assertEqual(payload["health"]["mode"], "travel-legacy")
            self.assertTrue(payload["health"]["database_ready"])
            self.assertGreaterEqual(payload["table_count"], 50)
            self.assertEqual(
                payload["required_tables"],
                ["admin_action_logs", "economy_log", "events", "users"],
            )

    def test_bot_imports_with_the_same_database_setting(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "travel.db"
            env = os.environ.copy()
            env.update(
                {
                    "ZHIDAO_DB_PATH": str(db_path),
                    "BOT_TOKEN": "123456:" + "A" * 35,
                }
            )
            code = """
import json
import zhidao_bot_ready as bot
print(json.dumps({"db_path": bot.DB_PATH}))
"""
            result = subprocess.run(
                [sys.executable, "-c", code],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout.strip().splitlines()[-1])
            self.assertEqual(Path(payload["db_path"]), db_path)


if __name__ == "__main__":
    unittest.main()
