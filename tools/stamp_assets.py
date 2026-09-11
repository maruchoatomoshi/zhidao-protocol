"""Проставляет в index.html версии, посчитанные из содержимого файлов.

Зачем. Приложение отдаёт версионные адреса как `immutable` на год (см.
`zhidao_v4/api.py`, middleware `security_headers`). Это правильно ровно до
того момента, когда файл меняют, а `?v=` в разметке — нет: тогда браузер
годами держит старую копию и совершенно законно. Один раз это уже стоило
выкаченного каталога имплантов без единого стиля.

Ручная дисциплина «не забудь поменять тег» тут не работает: забыть легко, а
последствия видны только на чужом телефоне. Поэтому тег не выдумывается, а
считается — короткий SHA-256 содержимого. Изменился файл — изменился адрес,
и никакого решения принимать не нужно.

    python tools/stamp_assets.py          проставить
    python tools/stamp_assets.py --check  только проверить (для тестов)

Возвращает 1, если что-то разошлось.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1] / "zhidao_v4" / "static" / "app"
INDEX = APP_DIR / "index.html"

# Ссылки вида ./file.ext?v=xxxx в разметке приложения.
REFERENCE = re.compile(r'(?P<prefix>(?:src|href)="\./)(?P<path>[^"?]+)\?v=(?P<version>[^"]*)"')

# Файлы, на которые ссылается не разметка, а сам код. Их версии живут в
# исходниках, поэтому и правятся там же.
IN_CODE = {
    APP_DIR / "campus-map.js": (
        re.compile(r'(?P<prefix>CAMPUS_SOURCE = "\./)(?P<path>[^"?]+)\?v=(?P<version>[^"]*)"'),
        None,
    ),
    APP_DIR / "implants.js": (
        re.compile(r'(?P<prefix>SOURCE = "\./)(?P<path>[^"?]+)\?v=(?P<version>[^"]*)"'),
        None,
    ),
    APP_DIR / "cases.js": (
        re.compile(r'(?P<prefix>SOURCE = "\./)(?P<path>[^"?]+)\?v=(?P<version>[^"]*)"'),
        None,
    ),
}


def digest(path: Path) -> str:
    # Хешируем содержимое так, как оно лежит в git и уезжает на сервер: с LF.
    # На Windows с core.autocrlf=true рабочая копия отдаёт CRLF, и без этой
    # нормализации метки зависели от того, в чьей копии их проставили —
    # 2026-09-11 так в main ушла 21 метка, не совпадающая с файлами.
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:10]


def stamp_text(text: str, pattern: re.Pattern, base: Path, problems: list[str]) -> str:
    def replace(match: re.Match) -> str:
        target = base / match.group("path")
        if not target.exists():
            problems.append(f"ссылка на несуществующий файл: {match.group('path')}")
            return match.group(0)
        expected = digest(target)
        if match.group("version") != expected:
            problems.append(
                f"{match.group('path')}: в разметке ?v={match.group('version')}, "
                f"по содержимому {expected}"
            )
        return f'{match.group("prefix")}{match.group("path")}?v={expected}"'

    return pattern.sub(replace, text)


def one_pass(check: bool, problems: list[str]) -> list[Path]:
    """Один проход. Возвращает файлы, которые пришлось (или пришлось бы) менять."""
    changed: list[Path] = []

    text = INDEX.read_text(encoding="utf-8")
    stamped = stamp_text(text, REFERENCE, APP_DIR, problems)
    if stamped != text:
        changed.append(INDEX)
        if not check:
            INDEX.write_text(stamped, encoding="utf-8", newline="")

    for source, (pattern, _) in IN_CODE.items():
        if not source.exists():
            continue
        code = source.read_text(encoding="utf-8")
        stamped_code = stamp_text(code, pattern, APP_DIR, problems)
        if stamped_code != code:
            changed.append(source)
            if not check:
                source.write_text(stamped_code, encoding="utf-8", newline="")

    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python tools/stamp_assets.py")
    parser.add_argument(
        "--check", action="store_true", help="только проверить, ничего не писать"
    )
    args = parser.parse_args(argv)

    problems: list[str] = []
    changed: list[Path] = []

    # Правка файла меняет его собственный хеш, а на него ссылается разметка.
    # Поэтому проходов несколько — до неподвижной точки. Ссылок немного, так
    # что двух-трёх хватает всегда; предел стоит от зацикливания, а не от
    # ожидаемой глубины.
    for _ in range(5):
        problems = []
        step = one_pass(args.check, problems)
        changed.extend(step)
        if not step or args.check:
            break

    if args.check:
        if problems:
            print("Версии ассетов разошлись с содержимым:")
            for problem in problems:
                print(f"  {problem}")
            print("\nПочинить: python tools/stamp_assets.py")
            return 1
        print("Версии ассетов совпадают с содержимым.")
        return 0

    if changed:
        for path in changed:
            print(f"обновлено: {path.name}")
    else:
        print("всё уже совпадает")
    return 0


if __name__ == "__main__":
    sys.exit(main())
