from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import Field, model_validator

from app.schemas.common import SchemaModel

ActionTarget = Literal["frontend", "backend"]
ActionTrigger = Literal["click", "change", "load", "manual"]
ActionAuditPolicy = Literal["always", "backend_only", "never"]
ActionStepErrorPolicy = Literal["stop", "continue"]
ActionExecutionStatus = Literal[
    "pending",
    "success",
    "partial",
    "failed",
    "rejected",
    "idempotent",
]


class ActionStepBase(SchemaModel):
    id: str
    target: ActionTarget
    type: str
    config: Dict[str, Any] = Field(default_factory=dict)
    on_error: ActionStepErrorPolicy = "stop"


class ActionStepInput(ActionStepBase):
    pass


class ActionStepOutput(ActionStepBase):
    pass


class ActionDefinitionBase(SchemaModel):
    id: str
    label: str
    icon: Optional[str] = None
    button_variant: Optional[str] = None
    trigger: ActionTrigger = "click"
    confirmation_message: Optional[str] = None
    schema_version: int = Field(default=1, ge=1)
    audit_policy: ActionAuditPolicy = "always"
    allowed_roles: List[str] = Field(default_factory=list)
    visibility_condition: Optional[str] = None
    enabled_condition: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    steps: List[ActionStepInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_action_definition(self) -> "ActionDefinitionBase":
        if not self.steps:
            raise ValueError("action definitions require at least one step")
        step_ids = [step.id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("action definition step ids must be unique")
        return self


class ActionDefinitionInput(ActionDefinitionBase):
    pass


class ActionDefinitionOutput(SchemaModel):
    id: str
    label: str
    icon: Optional[str] = None
    button_variant: Optional[str] = None
    trigger: ActionTrigger = "click"
    confirmation_message: Optional[str] = None
    schema_version: int = Field(default=1, ge=1)
    audit_policy: ActionAuditPolicy = "always"
    allowed_roles: List[str] = Field(default_factory=list)
    visibility_condition: Optional[str] = None
    enabled_condition: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    steps: List[ActionStepOutput] = Field(default_factory=list)


class ActionTriggerRequest(SchemaModel):
    response_uuid: Optional[str] = None
    confirmed: bool = False
    idempotency_key: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)
    client_state: Dict[str, Any] = Field(default_factory=dict)
    response_snapshot: Optional[Dict[str, Any]] = None


class ActionExecutionStepOutput(SchemaModel):
    step_id: str
    target: ActionTarget
    type: str
    status: ActionExecutionStatus
    output: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    executed_at: datetime


class ActionExecutionOutput(SchemaModel):
    uuid: str
    project_uuid: str
    form_uuid: str
    section_uuid: str
    question_uuid: str
    action_id: str
    response_uuid: Optional[str] = None
    actor_user_uuid: str
    idempotency_key: Optional[str] = None
    status: ActionExecutionStatus
    frontend_steps: List[ActionStepOutput] = Field(default_factory=list)
    step_results: List[ActionExecutionStepOutput] = Field(default_factory=list)
    request_context: Dict[str, Any] = Field(default_factory=dict)
    client_state: Dict[str, Any] = Field(default_factory=dict)
    output: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    request_id: Optional[str] = None


class ActionTriggerResponse(SchemaModel):
    execution: ActionExecutionOutput
    frontend_steps: List[ActionStepOutput] = Field(default_factory=list)
    idempotent: bool = False


class ActionExecutionListResponse(SchemaModel):
    items: List[ActionExecutionOutput]
    page: int
    page_size: int
    total_items: Optional[int] = None
    total_pages: Optional[int] = None
    next_cursor: Optional[str] = None
