from __future__ import annotations

import os

from repositories.mongodb import MongoDBRepository
from repositories.interface import RepositoryInterface


def bootstrap_repository(database_url: str) -> RepositoryInterface:
    if not (database_url.startswith("mongodb://") or database_url.startswith("mongodb+srv://")):
        raise ValueError("DATABASE_URL must start with mongodb:// or mongodb+srv://")
    repo = MongoDBRepository(database_url)
    repo.initialize()
    return repo


def main() -> int:
    database_url = os.getenv("DATABASE_URL", "mongodb://localhost:27017/form_response")
    repo = bootstrap_repository(database_url)
    print(f"MongoDB repository initialized at {database_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


