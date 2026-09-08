from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "zhidao_v4" / "static" / "app"
INDEX = APP_DIR / "index.html"


class AppAssetVersionTests(unittest.TestCase):
    """Версия в адресе должна соответствовать содержимому файла.

    Приложение отдаёт версионные адреса как `immutable` на год. Пока тег
    правился руками, забыть его было делом одной правки CSS — и каталог
    имплантов уехал на сервер без единого стиля, потому что браузер
    совершенно законно держал прежнюю копию `aero-grade.css`. Ошибка при
    этом не видна ни в одном логе: сервер отдаёт новый файл тем, кто его
    просит, а никто не просит.
    """

    def test_versions_match_file_contents(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "stamp_assets.py"), "--check"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=ROOT,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"{result.stdout}\n{result.stderr}",
        )

    def test_every_local_asset_reference_is_versioned(self):
        # Адрес без ?v= обслуживается как no-cache: работать будет, но каждый
        # заход снова спрашивает сервер. Для файла, который не меняется
        # месяцами, это лишний обмен на плохой связи.
        text = INDEX.read_text(encoding="utf-8")
        unversioned = [
            match.group("path")
            for match in re.finditer(
                r'(?:src|href)="\./(?P<path>[^"?]+\.(?:css|js))"', text
            )
        ]
        self.assertEqual(unversioned, [], "ссылки без версии")

    def test_referenced_files_exist(self):
        text = INDEX.read_text(encoding="utf-8")
        missing = [
            match.group("path")
            for match in re.finditer(r'(?:src|href)="\./(?P<path>[^"?]+)\?v=', text)
            if not (APP_DIR / match.group("path")).exists()
        ]
        self.assertEqual(missing, [], "ссылки на несуществующие файлы")


if __name__ == "__main__":
    unittest.main()
