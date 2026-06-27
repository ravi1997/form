from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class FormSnapshot:
    form_id: str
    title: str
    sections: list[dict]
    question_index: dict[str, dict]
    snapshot_version: int = 1
    created_at: str = field(default_factory=now_utc)
    updated_at: str = field(default_factory=now_utc)


@dataclass
class ResponseRecord:
    form_id: str
    answers: dict[str, Any]
    status: str = "draft"
    response_id: str = field(default_factory=lambda: str(uuid4()))
    submitted_at: str | None = None
    updated_at: str = field(default_factory=now_utc)
    form_snapshot_version: int = 1

