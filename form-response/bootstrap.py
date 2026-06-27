from __future__ import annotations

import os
from pathlib import Path

from repositories.sqlite import SQLiteRepository


def resolve_sqlite_path(database_url: str) -> Path:
    if not database_url.startswith("sqlite:///"):
        raise ValueError("DATABASE_URL must use sqlite:///")
    raw_path = database_url.removeprefix("sqlite:///")
    if not raw_path:
        raise ValueError("DATABASE_URL must include a file path")
    return Path(raw_path).expanduser().resolve()


def ensure_parent_directory(database_url: str) -> Path:
    db_path = resolve_sqlite_path(database_url)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def bootstrap_repository(database_url: str) -> SQLiteRepository:
    db_path = ensure_parent_directory(database_url)
    repo = SQLiteRepository(f"sqlite:///{db_path}")
    repo.initialize()
    return repo


def main() -> int:
    database_url = os.getenv("DATABASE_URL", "sqlite:///form_response.db")
    repo = bootstrap_repository(database_url)
    print(f"SQLite schema initialized at {repo.db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
