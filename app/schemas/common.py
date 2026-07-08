"""Pydantic v2 schema base classes shared across all schema modules.

``SchemaModel`` adds ``extra="forbid"`` to every schema so unexpected fields
in requests are rejected at validation time rather than silently ignored.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class SchemaModel(BaseModel):
    """Base config used by all schema models."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class TimestampedOutput(SchemaModel):
    created_at: datetime
    updated_at: datetime


class SoftDeleteOutput(SchemaModel):
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None
