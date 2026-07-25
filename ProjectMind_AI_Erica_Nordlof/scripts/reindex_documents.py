from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db import fetchall
from documents import reindex_project


def main() -> int:
    projects = fetchall("SELECT id,name FROM projects ORDER BY updated_at DESC")
    if not projects:
        print("Inga projekt hittades.")
        return 0
    for project in projects:
        print(f"\n{project['name']}")
        for result in reindex_project(project["id"], force=True):
            status = result.get("error") or f"{result.get('locator_count', 0)} källavsnitt"
            print(f"  - {result['file']}: {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
