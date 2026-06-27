from __future__ import annotations
import json
import sqlite3
from contextlib import closing
from dataclasses import asdict
from pathlib import Path

from models.core import FormSnapshot, ResponseRecord
from repositories.interface import RepositoryInterface


class SQLiteRepository(RepositoryInterface):
    def __init__(self, database_url: str = "sqlite:///form_response.db"):
        self.database_url = database_url
        self.db_path = self._parse_sqlite_path(database_url)

    @staticmethod
    def _parse_sqlite_path(database_url: str) -> Path:
        if not database_url.startswith("sqlite:///"):
            raise ValueError("Only sqlite:/// URLs are supported")
        return Path(database_url.removeprefix("sqlite:///"))

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def initialize(self) -> None:
        with closing(self._connect()) as conn:
            with conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS forms (
                        form_id TEXT NOT NULL,
                        snapshot_version INTEGER NOT NULL DEFAULT 1,
                        payload TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY(form_id, snapshot_version)
                    );

                    CREATE TABLE IF NOT EXISTS responses (
                        response_id TEXT PRIMARY KEY,
                        form_id TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        status TEXT NOT NULL,
                        submitted_at TEXT,
                        updated_at TEXT NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_responses_form_id ON responses(form_id);
                    CREATE INDEX IF NOT EXISTS idx_responses_status ON responses(status);
                    """
                )

    @staticmethod
    def _form_payload(form: FormSnapshot) -> dict:
        return asdict(form)

    @staticmethod
    def _response_payload(response: ResponseRecord) -> dict:
        return asdict(response)

    def health_check(self) -> bool:
        try:
            with closing(self._connect()) as conn:
                conn.execute("SELECT 1")
            return True
        except sqlite3.Error:
            return False

    def clear_forms(self) -> None:
        with closing(self._connect()) as conn:
            with conn:
                conn.execute("DELETE FROM forms")

    def clear_responses(self) -> None:
        with closing(self._connect()) as conn:
            with conn:
                conn.execute("DELETE FROM responses")

    def get_form(self, form_id: str, snapshot_version: int | None = None) -> FormSnapshot | None:
        with closing(self._connect()) as conn:
            if snapshot_version is not None:
                row = conn.execute(
                    "SELECT payload FROM forms WHERE form_id = ? AND snapshot_version = ?",
                    (form_id, snapshot_version),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT payload FROM forms WHERE form_id = ? ORDER BY snapshot_version DESC LIMIT 1",
                    (form_id,),
                ).fetchone()
        if not row:
            return None
        return FormSnapshot(**json.loads(row["payload"]))

    def upsert_form(self, form: FormSnapshot) -> None:
        payload = json.dumps(self._form_payload(form))
        with closing(self._connect()) as conn:
            with conn:
                conn.execute(
                    """
                    INSERT INTO forms(form_id, snapshot_version, payload, created_at, updated_at)
                    VALUES(?, ?, ?, ?, ?)
                    ON CONFLICT(form_id, snapshot_version) DO UPDATE SET
                        payload = excluded.payload,
                        updated_at = excluded.updated_at
                    """,
                    (form.form_id, form.snapshot_version, payload, form.created_at, form.updated_at),
                )

    def get_response(self, response_id: str) -> ResponseRecord | None:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT payload FROM responses WHERE response_id = ?", (response_id,)).fetchone()
        if not row:
            return None
        return ResponseRecord(**json.loads(row["payload"]))

    def list_responses_by_form_id(self, form_id: str) -> list[ResponseRecord]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT payload FROM responses WHERE form_id = ? ORDER BY updated_at DESC",
                (form_id,),
            ).fetchall()
        return [ResponseRecord(**json.loads(row["payload"])) for row in rows]

    def upsert_response(self, response: ResponseRecord) -> None:
        payload = json.dumps(self._response_payload(response))
        with closing(self._connect()) as conn:
            with conn:
                conn.execute(
                    """
                    INSERT INTO responses(response_id, form_id, payload, status, submitted_at, updated_at)
                    VALUES(?, ?, ?, ?, ?, ?)
                    ON CONFLICT(response_id) DO UPDATE SET
                        form_id = excluded.form_id,
                        payload = excluded.payload,
                        status = excluded.status,
                        submitted_at = excluded.submitted_at,
                        updated_at = excluded.updated_at
                    """,
                    (
                        response.response_id,
                        response.form_id,
                        payload,
                        response.status,
                        response.submitted_at,
                        response.updated_at,
                    ),
                )
