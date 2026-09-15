"""Собирает V4_SCHEMA_TABLES.md из миграций — справочник текущей схемы.

Зачем. Рукописный V4_SCHEMA.md остановился на миграции 0006, а схема дошла
до десятков таблиц. Список таблиц руками не обновляется: забыть легко, а
документ, который выглядит полным и не является им, хуже его отсутствия.
Поэтому справочник не пишется, а считается — миграции применяются к пустой
временной базе по одной, и из самой SQLite читаются колонки, ключи, индексы и
триггеры. Для каждой таблицы видно, какая миграция её создала и какая
последней меняла.

Берутся только PRAGMA-сведения: они не зависят от версии SQLite. Текст CREATE
из sqlite_master SQLite переписывает при RENAME по-разному в разных версиях,
и проверка падала бы в CI без изменения схемы. CHECK-ограничения поэтому
остаются в самих файлах миграций — справочник на них ссылается.

    python tools/schema_doc.py          пересобрать V4_SCHEMA_TABLES.md
    python tools/schema_doc.py --check  только проверить (для тестов)

Возвращает 1, если файл разошёлся со схемой.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from zhidao_v4.migrations import DEFAULT_MIGRATION_DIR, MIGRATION_NAME_RE, apply_migrations  # noqa: E402


OUTPUT = ROOT / "V4_SCHEMA_TABLES.md"


def cell(value: object) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def describe(path: Path) -> str:
    """Первая строка комментария в начале миграции — её назначение."""
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("--"):
            return stripped.lstrip("-").strip()
        break
    return ""


def snapshot(conn: sqlite3.Connection) -> dict[str, str]:
    """Отпечаток каждой таблицы: колонки, ключи и индексы в стабильном виде."""
    prints: dict[str, str] = {}
    for (name,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ):
        parts = [
            repr(conn.execute(f'PRAGMA table_info("{name}")').fetchall()),
            repr(conn.execute(f'PRAGMA foreign_key_list("{name}")').fetchall()),
            repr(sorted(index_rows(conn, name))),
        ]
        prints[name] = "\n".join(parts)
    return prints


def index_rows(conn: sqlite3.Connection, table: str) -> list[tuple]:
    rows = []
    for _seq, name, unique, origin, partial in conn.execute(f'PRAGMA index_list("{table}")'):
        if origin == "pk":
            continue
        columns = tuple(
            row[2] for row in conn.execute(f'PRAGMA index_info("{name}")').fetchall()
        )
        rows.append((name, bool(unique), origin, bool(partial), columns))
    return rows


def build() -> str:
    files = sorted(
        path for path in DEFAULT_MIGRATION_DIR.glob("*.sql") if MIGRATION_NAME_RE.fullmatch(path.name)
    )
    created: dict[str, str] = {}
    changed: dict[str, str] = {}

    with tempfile.TemporaryDirectory() as tmp:
        partial_dir = Path(tmp) / "migrations"
        partial_dir.mkdir()
        db = Path(tmp) / "schema.db"
        previous: dict[str, str] = {}
        for path in files:
            shutil.copyfile(path, partial_dir / path.name)
            apply_migrations(db, partial_dir)
            version = path.name[:4]
            conn = sqlite3.connect(db)
            try:
                current = snapshot(conn)
            finally:
                conn.close()
            for name, fingerprint in current.items():
                if name not in previous:
                    created[name] = version
                    changed[name] = version
                elif previous[name] != fingerprint:
                    changed[name] = version
            for name in set(previous) - set(current):
                created.pop(name, None)
                changed.pop(name, None)
            previous = current

        conn = sqlite3.connect(db)
        try:
            return render(conn, files, created, changed)
        finally:
            conn.close()


def render(
    conn: sqlite3.Connection,
    files: list[Path],
    created: dict[str, str],
    changed: dict[str, str],
) -> str:
    tables = sorted(created)
    triggers: dict[str, list[str]] = {}
    for name, table in conn.execute(
        "SELECT name, tbl_name FROM sqlite_master WHERE type = 'trigger' ORDER BY name"
    ):
        triggers.setdefault(table, []).append(name)
    index_total = sum(
        1 for table in tables for row in index_rows(conn, table) if row[2] == "c"
    )

    lines = [
        "# ZHIDAO V4 — таблицы текущей схемы",
        "",
        "<!-- Сгенерировано tools/schema_doc.py из migrations/v4. Не править руками:",
        "     python tools/schema_doc.py пересобирает файл, тест сверяет его со схемой. -->",
        "",
        f"Последняя миграция: **{files[-1].name[:4]}**. Таблиц: **{len(tables)}**, "
        f"явных индексов: **{index_total}**, триггеров: **{sum(map(len, triggers.values()))}**.",
        "",
        "Здесь только то, что SQLite сообщает о структуре: колонки, внешние ключи,",
        "индексы, триггеры. CHECK-ограничения, комментарии и причины решений — в",
        "самих файлах `migrations/v4/`. Модель данных и её правила — `V4_SCHEMA.md`.",
        "",
        "## Миграции",
        "",
        "| № | Файл | Назначение |",
        "|---|---|---|",
    ]
    for path in files:
        lines.append(f"| {path.name[:4]} | `{path.name}` | {cell(describe(path))} |")

    by_migration: dict[str, list[str]] = {}
    for table in tables:
        by_migration.setdefault(created[table], []).append(table)

    lines += ["", "## Таблицы", ""]
    for path in files:
        version = path.name[:4]
        if version not in by_migration:
            continue
        lines += [f"### Созданы в {version} — `{path.name}`", ""]
        for table in by_migration[version]:
            lines += render_table(conn, table, created[table], changed[table], triggers.get(table, []))
    return "\n".join(lines).rstrip() + "\n"


def render_table(
    conn: sqlite3.Connection, table: str, created: str, changed: str, triggers: list[str]
) -> list[str]:
    # «Структура» — колонки, ключи и индексы. Пересборка ради одного CHECK
    # (как 0009 для комнат) сюда не попадает: CHECK видны только в миграциях.
    history = f"создана в {created}" + (
        f", колонки, ключи или индексы последний раз менялись в {changed}" if changed != created else ""
    )
    lines = [
        f"#### `{table}`",
        "",
        f"_{history}_",
        "",
        "| Колонка | Тип | NOT NULL | По умолчанию | PK |",
        "|---|---|---|---|---|",
    ]
    for _cid, name, kind, notnull, default, pk in conn.execute(f'PRAGMA table_info("{table}")'):
        lines.append(
            f"| `{cell(name)}` | {cell(kind)} | {'да' if notnull else ''} | "
            f"{('`' + cell(default) + '`') if default is not None else ''} | {pk or ''} |"
        )

    keys: dict[int, list[tuple]] = {}
    for key_id, _seq, parent, source, target, on_update, on_delete, _match in conn.execute(
        f'PRAGMA foreign_key_list("{table}")'
    ):
        keys.setdefault(key_id, []).append((parent, source, target, on_update, on_delete))
    if keys:
        lines += ["", "Внешние ключи:"]
        for key_id in sorted(keys):
            parts = keys[key_id]
            parent = parts[0][0]
            sources = ", ".join(part[1] for part in parts)
            targets = ", ".join(str(part[2]) if part[2] is not None else "PK" for part in parts)
            actions = [
                f"ON {label} {action}"
                for label, action in (("UPDATE", parts[0][3]), ("DELETE", parts[0][4]))
                if action and action != "NO ACTION"
            ]
            suffix = f" {' '.join(actions)}" if actions else ""
            lines.append(f"- ({sources}) → `{parent}`({targets}){suffix}")

    indexes = sorted(index_rows(conn, table))
    if indexes:
        lines += ["", "Индексы и уникальность:"]
        for name, unique, origin, partial, columns in indexes:
            kind = "UNIQUE-ограничение" if origin == "u" else ("уникальный индекс" if unique else "индекс")
            note = ", частичный (WHERE — в миграции)" if partial else ""
            label = f"`{name}`" if origin == "c" else "из определения таблицы"
            lines.append(f"- {label}: {kind}{note} — ({', '.join(columns)})")

    if triggers:
        lines += ["", "Триггеры: " + ", ".join(f"`{name}`" for name in triggers)]
    lines.append("")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python tools/schema_doc.py")
    parser.add_argument("--check", action="store_true", help="только проверить, ничего не писать")
    args = parser.parse_args(argv)

    expected = build()
    # Сравниваем как в git — с LF: на Windows рабочая копия может отдавать CRLF.
    actual = OUTPUT.read_bytes().replace(b"\r\n", b"\n").decode("utf-8") if OUTPUT.exists() else None

    if args.check:
        if actual != expected:
            print(f"{OUTPUT.name} разошёлся со схемой из migrations/v4.")
            print("\nПочинить: python tools/schema_doc.py")
            return 1
        print(f"{OUTPUT.name} совпадает со схемой.")
        return 0

    if actual == expected:
        print("всё уже совпадает")
    else:
        OUTPUT.write_text(expected, encoding="utf-8", newline="\n")
        print(f"обновлено: {OUTPUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
