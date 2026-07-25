from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import psycopg

SQLITE_PATH = Path(os.getenv("SQLITE_PATH", "./storage/projectmind.db"))
DATABASE_URL = os.environ["DATABASE_URL"]
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]

TABLES = [
    "projects",
    "project_files",
    "versions",
    "chats",
    "messages",
    "chat_attachments",
]

if not SQLITE_PATH.exists():
    raise SystemExit(f"SQLite-filen finns inte: {SQLITE_PATH}")

source = sqlite3.connect(SQLITE_PATH)
source.row_factory = sqlite3.Row

with psycopg.connect(DATABASE_URL) as target:
    for table in TABLES:
        rows = source.execute(f"SELECT * FROM {table}").fetchall()
        if not rows:
            print(f"{table}: 0")
            continue
        columns = rows[0].keys()
        placeholders = ",".join(["%s"] * len(columns))
        column_sql = ",".join(columns)
        update_columns = [column for column in columns if column != "id"]
        update_sql = ",".join(
            f"{column}=EXCLUDED.{column}" for column in update_columns
        )
        sql = (
            f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders}) "
            f"ON CONFLICT (id) DO UPDATE SET {update_sql}"
        )
        with target.cursor() as cursor:
            cursor.executemany(sql, [tuple(row[column] for column in columns) for row in rows])
        print(f"{table}: {len(rows)}")

source.close()
print("Migreringen är klar.")
