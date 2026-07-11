from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import Field, model_validator

from app.schemas.common import SchemaModel
from app.schemas.version import VersionCreateInput, VersionOutput, VersionUpdateInput

DocumentStatus = Literal["active", "inactive", "deleted"]
FormWorkflowState = Literal["draft", "submitted", "in_review", "approved", "rejected"]


class FormWorkflowEventOutput(SchemaModel):
    action: Literal["submit", "review", "approve"]
    actor_user_uuid: str
    note: Optional[str] = None
    transition_from: Optional[FormWorkflowState] = None
    transition_to: Optional[FormWorkflowState] = None
    outcome: Literal["success", "idempotent", "rejected"]
    created_at: datetime
    request_id: Optional[str] = None


class FormBase(SchemaModel):
    sections: Dict[str, List[str]] = Field(default_factory=dict)
    editors: List[str] = Field(default_factory=list)
    viewers: List[str] = Field(default_factory=list)
    reviewers: List[str] = Field(default_factory=list)
    approvers: List[str] = Field(default_factory=list)
    submitters: List[str] = Field(default_factory=list)
    requires_reviewer: bool = False
    requires_approver: bool = False
    min_reviewers_required: int = Field(default=0, ge=0)
    min_approvers_required: int = Field(default=0, ge=0)
    validation_conditions: List[str] = Field(default_factory=list)
    validation_condition_messages: Dict[str, str] = Field(default_factory=dict)
    child_sections: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    icon: Optional[str] = None
    theme_template_uuid: Optional[str] = None
    theme_revision_uuid: Optional[str] = None
    layout_template_uuid: Optional[str] = None
    layout_revision_uuid: Optional[str] = None
    ui_overrides: Dict[str, Any] = Field(default_factory=dict)
    is_public: bool = False
    status: DocumentStatus = "active"

    @model_validator(mode="after")
    def validate_reviewer_and_approver_rules(self) -> "FormBase":
        if self.min_reviewers_required > 0:
            self.requires_reviewer = True
        if self.min_approvers_required > 0:
            self.requires_approver = True

        if self.requires_reviewer and len(set(self.reviewers)) < max(
            1, self.min_reviewers_required
        ):
            raise ValueError(
                "reviewers list does not satisfy requires_reviewer constraints"
            )

        if self.requires_approver and len(set(self.approvers)) < max(
            1, self.min_approvers_required
        ):
            raise ValueError(
                "approvers list does not satisfy requires_approver constraints"
            )

        return self


class FormCreateInput(FormBase):
    uuid: str
    versions: List[VersionCreateInput] = Field(default_factory=list)


class FormUpdateInput(SchemaModel):
    versions: Optional[List[VersionUpdateInput]] = None
    sections: Optional[Dict[str, List[str]]] = None
    editors: Optional[List[str]] = None
    viewers: Optional[List[str]] = None
    reviewers: Optional[List[str]] = None
    approvers: Optional[List[str]] = None
    submitters: Optional[List[str]] = None
    requires_reviewer: Optional[bool] = None
    requires_approver: Optional[bool] = None
    min_reviewers_required: Optional[int] = Field(default=None, ge=0)
    min_approvers_required: Optional[int] = Field(default=None, ge=0)
    validation_conditions: Optional[List[str]] = None
    validation_condition_messages: Optional[Dict[str, str]] = None
    child_sections: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    icon: Optional[str] = None
    theme_template_uuid: Optional[str] = None
    theme_revision_uuid: Optional[str] = None
    layout_template_uuid: Optional[str] = None
    layout_revision_uuid: Optional[str] = None
    ui_overrides: Optional[Dict[str, Any]] = None
    is_public: Optional[bool] = None
    status: Optional[DocumentStatus] = None


class FormRef(SchemaModel):
    uuid: str


class FormOutput(FormBase):
    uuid: str
    versions: List[VersionOutput] = Field(default_factory=list)
    workflow_state: FormWorkflowState = "draft"
    workflow_updated_at: Optional[datetime] = None
    workflow_history: List[FormWorkflowEventOutput] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
