from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings
from db import connection
from storage import healthcheck


def main() -> int:
    database_ok = False
    database_error = ""
    try:
        with connection() as conn:
            conn.execute("SELECT 1")
        database_ok = True
    except Exception as exc:
        database_error = str(exc)

    storage_ok, storage_error = healthcheck()
    result = {
        "database": "postgresql" if settings.using_postgres else "sqlite",
        "database_ok": database_ok,
        "storage": settings.storage_backend,
        "storage_ok": storage_ok,
        "persistent": settings.persistence_ok,
        "persistence_mode": settings.persistence_mode,
        "data_dir": str(settings.data_dir),
        "errors": [value for value in (database_error, storage_error) if value],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if database_ok and storage_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
