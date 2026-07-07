from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import Field, model_validator

from app.schemas.common import SchemaModel
from app.schemas.version import VersionCreateInput, VersionOutput, VersionUpdateInput


DocumentStatus = Literal["active", "inactive", "deleted"]


class SectionBase(SchemaModel):
    questions: Dict[str, List[str]] = Field(default_factory=dict)
    add_button: bool = False
    is_repeatable: bool = False
    repeatable_condition: Optional[str] = None
    check_repeat_on: Optional[str] = None
    min_repeatable_count: Optional[int] = None
    max_repeatable_count: Optional[int] = None
    title: Optional[str] = None
    description: Optional[str] = None
    isDeleted: bool = False
    deletedBy: Optional[str] = None
    deletedAt: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None
    visibility_condition: Optional[str] = None
    validation_conditions: List[str] = Field(default_factory=list)
    validation_condition_messages: Dict[str, str] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)
    icon: Optional[str] = None
    status: DocumentStatus = "active"

    @model_validator(mode="after")
    def validate_repeatable_bounds(self) -> "SectionBase":
        if (
            self.min_repeatable_count is not None
            and self.max_repeatable_count is not None
            and self.min_repeatable_count > self.max_repeatable_count
        ):
            raise ValueError("min_repeatable_count cannot be greater than max_repeatable_count")
        return self


class SectionCreateInput(SectionBase):
    uuid: str
    versions: List[VersionCreateInput] = Field(default_factory=list)


class SectionUpdateInput(SchemaModel):
    versions: Optional[List[VersionUpdateInput]] = None
    questions: Optional[Dict[str, List[str]]] = None
    add_button: Optional[bool] = None
    is_repeatable: Optional[bool] = None
    repeatable_condition: Optional[str] = None
    check_repeat_on: Optional[str] = None
    min_repeatable_count: Optional[int] = None
    max_repeatable_count: Optional[int] = None
    title: Optional[str] = None
    description: Optional[str] = None
    isDeleted: Optional[bool] = None
    deletedBy: Optional[str] = None
    deletedAt: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None
    visibility_condition: Optional[str] = None
    validation_conditions: Optional[List[str]] = None
    validation_condition_messages: Optional[Dict[str, str]] = None
    tags: Optional[List[str]] = None
    icon: Optional[str] = None
    status: Optional[DocumentStatus] = None


class SectionRef(SchemaModel):
    uuid: str
    title: Optional[str] = None


class SectionOutput(SectionBase):
    uuid: str
    versions: List[VersionOutput] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
