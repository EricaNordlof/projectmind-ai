from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Any, Iterable, Iterator

from config import settings

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # Local SQLite development can run without psycopg installed.
    psycopg = None
    dict_row = None


DB_PATH = settings.data_dir / "projectmind.db"


def sql(statement: str) -> str:
    return statement.replace("?", "%s") if settings.using_postgres else statement


@contextmanager
def connection() -> Iterator[Any]:
    if settings.using_postgres:
        if psycopg is None:
            raise RuntimeError("psycopg saknas men DATABASE_URL pekar på PostgreSQL.")
        conn = psycopg.connect(settings.database_url, row_factory=dict_row)
    else:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 30000")

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'active',
        stack TEXT NOT NULL DEFAULT '',
        notes TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS project_files (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        original_name TEXT NOT NULL,
        stored_name TEXT NOT NULL,
        mime_type TEXT NOT NULL DEFAULT '',
        size_bytes BIGINT NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS document_text_cache (
        file_id TEXT PRIMARY KEY REFERENCES project_files(id) ON DELETE CASCADE,
        content_sha256 TEXT NOT NULL,
        extracted_text TEXT NOT NULL DEFAULT '',
        locator_count INTEGER NOT NULL DEFAULT 0,
        extraction_error TEXT NOT NULL DEFAULT '',
        extracted_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS versions (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        version_label TEXT NOT NULL,
        comment TEXT NOT NULL DEFAULT '',
        original_name TEXT NOT NULL,
        stored_name TEXT NOT NULL,
        size_bytes BIGINT NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chats (
        id TEXT PRIMARY KEY,
        project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
        role TEXT NOT NULL CHECK(role IN ('user','assistant')),
        content TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chat_attachments (
        id TEXT PRIMARY KEY,
        message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
        chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
        original_name TEXT NOT NULL,
        stored_name TEXT NOT NULL,
        mime_type TEXT NOT NULL,
        size_bytes BIGINT NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_files_project ON project_files(project_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_versions_project ON versions(project_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_chats_project ON chats(project_id, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id, created_at ASC)",
    "CREATE INDEX IF NOT EXISTS idx_chat_attachments_message ON chat_attachments(message_id, created_at ASC)",
]


def init_db() -> None:
    with connection() as conn:
        for statement in SCHEMA:
            conn.execute(sql(statement))


def fetchone(statement: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute(sql(statement), params).fetchone()
    return dict(row) if row else None


def fetchall(statement: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(sql(statement), params).fetchall()
    return [dict(row) for row in rows]


def execute(statement: str, params: tuple[Any, ...] = ()) -> None:
    with connection() as conn:
        conn.execute(sql(statement), params)


def executemany(statement: str, rows: Iterable[tuple[Any, ...]]) -> None:
    with connection() as conn:
        conn.executemany(sql(statement), list(rows))


init_db()
