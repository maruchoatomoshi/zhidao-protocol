from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_MIGRATION_DIR = Path(__file__).resolve().parents[1] / "migrations" / "v4"
MIGRATION_NAME_RE = re.compile(r"^(?P<version>\d{4})_(?P<name>[a-z0-9_]+)\.sql$")


class MigrationError(RuntimeError):
    """Raised when a V4 schema migration cannot be applied safely."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path
    checksum: str
    sql: str


def _discover_migrations(migration_dir: Path) -> list[Migration]:
    if not migration_dir.is_dir():
        raise MigrationError(f"Migration directory does not exist: {migration_dir}")

    migrations: list[Migration] = []
    versions: set[int] = set()
    for path in sorted(migration_dir.glob("*.sql")):
        match = MIGRATION_NAME_RE.fullmatch(path.name)
        if not match:
            raise MigrationError(f"Invalid migration filename: {path.name}")
        version = int(match.group("version"))
        if version in versions:
            raise MigrationError(f"Duplicate migration version: {version:04d}")
        versions.add(version)
        sql = path.read_text(encoding="utf-8")
        migrations.append(
            Migration(
                version=version,
                name=match.group("name"),
                path=path,
                checksum=hashlib.sha256(sql.encode("utf-8")).hexdigest(),
                sql=sql,
            )
        )
    return migrations


def _iter_statements(sql: str) -> Iterable[str]:
    buffer: list[str] = []
    for line in sql.splitlines(keepends=True):
        buffer.append(line)
        candidate = "".join(buffer)
        if sqlite3.complete_statement(candidate):
            statement = candidate.strip()
            buffer.clear()
            if statement:
                yield statement

    remainder = "".join(buffer).strip()
    if remainder:
        raise MigrationError("Migration contains an incomplete SQL statement")


def _ensure_migration_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS v4_schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            checksum TEXT NOT NULL CHECK (length(checksum) = 64),
            applied_at TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            )
        )
        """
    )


def apply_migrations(
    db_path: str | Path,
    migration_dir: str | Path = DEFAULT_MIGRATION_DIR,
) -> list[str]:
    """Apply every pending V4 migration and return their filenames.

    Legacy tables are not inspected, renamed, or removed. Every migration is
    executed in its own immediate transaction, together with its ledger row.
    An already-applied migration whose name or checksum changed is rejected.
    """

    db_value = str(db_path)
    if db_value != ":memory:":
        Path(db_value).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

    migrations = _discover_migrations(Path(migration_dir))
    conn = sqlite3.connect(db_value, timeout=30, isolation_level=None)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        _ensure_migration_table(conn)
        applied = {
            int(row[0]): (str(row[1]), str(row[2]))
            for row in conn.execute(
                "SELECT version, name, checksum FROM v4_schema_migrations"
            )
        }
        applied_files: list[str] = []

        for migration in migrations:
            existing = applied.get(migration.version)
            if existing:
                if existing != (migration.name, migration.checksum):
                    raise MigrationError(
                        "Applied migration does not match its source file: "
                        f"{migration.path.name}"
                    )
                continue

            conn.execute("BEGIN IMMEDIATE")
            try:
                for statement in _iter_statements(migration.sql):
                    conn.execute(statement)
                conn.execute(
                    """
                    INSERT INTO v4_schema_migrations(version, name, checksum)
                    VALUES (?, ?, ?)
                    """,
                    (migration.version, migration.name, migration.checksum),
                )
                conn.execute("COMMIT")
            except Exception as exc:
                conn.execute("ROLLBACK")
                if isinstance(exc, MigrationError):
                    raise
                raise MigrationError(
                    f"Failed to apply migration {migration.path.name}: {exc}"
                ) from exc
            applied_files.append(migration.path.name)

        return applied_files
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply additive ZHIDAO V4 migrations")
    parser.add_argument("--db", required=True, help="SQLite database path")
    parser.add_argument(
        "--migrations",
        default=str(DEFAULT_MIGRATION_DIR),
        help="Directory containing ordered V4 SQL migrations",
    )
    args = parser.parse_args()
    applied = apply_migrations(args.db, args.migrations)
    print(json.dumps({"database": str(Path(args.db)), "applied": applied}, ensure_ascii=False))


if __name__ == "__main__":
    main()
