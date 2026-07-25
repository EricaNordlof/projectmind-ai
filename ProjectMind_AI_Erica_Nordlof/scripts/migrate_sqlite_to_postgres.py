from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SQLITE_PATH = Path(os.getenv("SQLITE_PATH", ROOT / "storage" / "projectmind.db"))
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if not DATABASE_URL.startswith(("postgresql://", "postgres://")):
    raise SystemExit("DATABASE_URL måste peka på PostgreSQL.")
if not SQLITE_PATH.exists():
    raise SystemExit(f"SQLite-filen finns inte: {SQLITE_PATH}")

from db import connection, init_db

TABLES = [
    "projects",
    "project_files",
    "versions",
    "chats",
    "messages",
    "chat_attachments",
    "document_text_cache",
]


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def main() -> int:
    init_db()
    source = sqlite3.connect(SQLITE_PATH)
    source.row_factory = sqlite3.Row
    try:
        with connection() as target:
            for table in TABLES:
                if not table_exists(source, table):
                    print(f"Hoppar över {table}: tabellen saknas i SQLite.")
                    continue
                rows = source.execute(f"SELECT * FROM {table}").fetchall()
                if not rows:
                    print(f"{table}: 0 rader")
                    continue
                columns = rows[0].keys()
                placeholders = ",".join(["%s"] * len(columns))
                column_list = ",".join(columns)
                statement = f"INSERT INTO {table} ({column_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
                for row in rows:
                    target.execute(statement, tuple(row[column] for column in columns))
                print(f"{table}: {len(rows)} rader behandlade")
    finally:
        source.close()
    print("Databasmigreringen är klar. Kopiera även filerna till vald objektlagring.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
