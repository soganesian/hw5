"""Create a clean working copy of the Campus Customs database and inspect it."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from backend.paths import ACTIVE_DATABASE_PATH, CLEAN_REFERENCE_DATABASE_PATH

SOURCE_DB = CLEAN_REFERENCE_DATABASE_PATH
WORKING_DB = ACTIVE_DATABASE_PATH
DATA_DIR = WORKING_DB.parent
REQUIRED_TABLES = (
    "desk",
    "tickets",
    "inventory",
    "pricing",
    "vendors",
    "leases",
    "cash_accounts",
    "payments",
    "invoices",
)


def inspect_schema(connection: sqlite3.Connection) -> dict[str, list[tuple]]:
    """Return column metadata for required tables; raise if a table is missing."""
    existing = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    missing = [table for table in REQUIRED_TABLES if table not in existing]
    if missing:
        raise RuntimeError(f"Database is missing required tables: {', '.join(missing)}")

    return {
        table: connection.execute(f'PRAGMA table_info("{table}")').fetchall()
        for table in REQUIRED_TABLES
    }


def create_working_copy() -> dict[str, list[tuple]]:
    if not SOURCE_DB.is_file():
        raise FileNotFoundError(f"Source database not found: {SOURCE_DB}")
    if SOURCE_DB.resolve() == WORKING_DB.resolve():
        raise ValueError("Source and working database paths must be different")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="campus_customs_", suffix=".db.tmp", dir=DATA_DIR, delete=False
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)

        # SQLite's backup API produces a consistent copy, including committed data.
        with closing(sqlite3.connect(SOURCE_DB)) as source, closing(
            sqlite3.connect(temporary_path)
        ) as target:
            source.backup(target)
        with closing(sqlite3.connect(temporary_path)) as copied_db:
            schema = inspect_schema(copied_db)

        # Publish only after the copied database passes the required-table check.
        os.replace(temporary_path, WORKING_DB)
        temporary_path = None
        return schema
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main() -> None:
    schema = create_working_copy()
    print(f"Working database created: {WORKING_DB}")
    print(f"Clean source preserved:   {SOURCE_DB}")
    print("\nRequired table schemas:")
    for table, columns in schema.items():
        print(f"\n{table}")
        for _, name, declared_type, not_null, default, primary_key in columns:
            details = [declared_type or "(no declared type)"]
            if primary_key:
                details.append("PRIMARY KEY")
            if not_null:
                details.append("NOT NULL")
            if default is not None:
                details.append(f"DEFAULT {default}")
            print(f"  - {name}: {', '.join(details)}")


if __name__ == "__main__":
    main()
