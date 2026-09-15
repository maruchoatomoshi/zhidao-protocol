from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class V4SchemaDocTests(unittest.TestCase):
    """V4_SCHEMA_TABLES.md должен описывать схему, которую дают миграции.

    Рукописный список таблиц отстал на двадцать миграций, и это было видно
    только по внешнему аудиту. Справочник генерируется, а этот тест не даёт
    добавить миграцию, не пересобрав его: python tools/schema_doc.py.
    """

    def test_schema_reference_matches_migrations(self):
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(ROOT / "tools" / "schema_doc.py"), "--check"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=ROOT,
        )
        self.assertEqual(result.returncode, 0, f"{result.stdout}\n{result.stderr}")


if __name__ == "__main__":
    unittest.main()
