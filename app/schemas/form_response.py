from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import Field, model_validator

from app.schemas.common import SchemaModel
from app.schemas.response_item import (
    ResponseItemCreateInput,
    ResponseItemOutput,
    ResponseItemUpdateInput,
)


FormResponseStatus = Literal[
    "draft",
    "submitted",
    "in_review",
    "approved",
    "rejected",
    "deleted",
]


class FormResponseBase(SchemaModel):
    form: Optional[str] = None
    form_uuid: str
    form_version_uuid: str
    project: Optional[str] = None
    project_uuid: Optional[str] = None
    organization: Optional[str] = None
    organization_uuid: Optional[str] = None
    submitted_by: Optional[str] = None
    submitted_by_uuid: Optional[str] = None
    status: FormResponseStatus = "draft"
    responses: List[ResponseItemCreateInput] = Field(default_factory=list)
    response_map: Dict[str, Any] = Field(default_factory=dict)
    score: Optional[float] = None
    validation_errors: Dict[str, str] = Field(default_factory=dict)
    submitted_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    reviewed_by: List[str] = Field(default_factory=list)
    approved_at: Optional[datetime] = None
    approved_by: List[str] = Field(default_factory=list)
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_response_keys(self) -> "FormResponseBase":
        seen = set()
        for item in self.responses:
            key = f"{item.question_uuid}:{item.repeat_index or 0}"
            if key in seen:
                raise ValueError(
                    "responses must have unique question_uuid+repeat_index combinations"
                )
            seen.add(key)
        return self


class FormResponseCreateInput(FormResponseBase):
    uuid: str


class FormResponseUpdateInput(SchemaModel):
    form: Optional[str] = None
    form_uuid: Optional[str] = None
    form_version_uuid: Optional[str] = None
    project: Optional[str] = None
    project_uuid: Optional[str] = None
    organization: Optional[str] = None
    organization_uuid: Optional[str] = None
    submitted_by: Optional[str] = None
    submitted_by_uuid: Optional[str] = None
    status: Optional[FormResponseStatus] = None
    responses: Optional[List[ResponseItemUpdateInput]] = None
    response_map: Optional[Dict[str, Any]] = None
    score: Optional[float] = None
    validation_errors: Optional[Dict[str, str]] = None
    submitted_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[List[str]] = None
    approved_at: Optional[datetime] = None
    approved_by: Optional[List[str]] = None
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class FormResponseRef(SchemaModel):
    uuid: str
    status: FormResponseStatus


class FormResponseStatusEventOutput(SchemaModel):
    transition_from: Optional[FormResponseStatus] = None
    transition_to: FormResponseStatus
    changed_at: datetime
    reason: Optional[str] = None


class FormResponseOutput(FormResponseBase):
    uuid: str
    responses: List[ResponseItemOutput] = Field(default_factory=list)
    status_history: List[FormResponseStatusEventOutput] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
