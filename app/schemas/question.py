from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import Field, model_validator

from app.schemas.choice import ChoiceCreateInput, ChoiceOutput, ChoiceUpdateInput
from app.schemas.common import SchemaModel
from app.schemas.version import VersionCreateInput, VersionOutput, VersionUpdateInput


DocumentStatus = Literal["active", "inactive", "deleted"]


class QuestionBase(SchemaModel):
    type: str
    label: str
    placeholder: Optional[str] = None
    description: Optional[str] = None
    default_value: Optional[Any] = None
    help_text: Optional[str] = None
    tooltip: Optional[str] = None

    validation_conditions: List[str] = Field(default_factory=list)
    validation_condition_messages: Dict[str, str] = Field(default_factory=dict)
    visibility_conditions: List[str] = Field(default_factory=list)

    add_button: bool = False

    is_repeatable: bool = False
    repeatable_condition: Optional[str] = None
    check_repeat_on: Optional[str] = None
    min_repeatable_count: Optional[int] = None
    max_repeatable_count: Optional[int] = None

    isAction: bool = False
    actionButtonType: Optional[str] = None
    actionType: Optional[str] = None
    actionLabel: Optional[str] = None

    tags: List[str] = Field(default_factory=list)
    choices: List[ChoiceCreateInput] = Field(default_factory=list)

    hideButton: bool = False
    actionIcon: Optional[str] = None
    status: DocumentStatus = "active"

    @model_validator(mode="after")
    def validate_question_shape(self) -> "QuestionBase":
        if (
            self.min_repeatable_count is not None
            and self.max_repeatable_count is not None
            and self.min_repeatable_count > self.max_repeatable_count
        ):
            raise ValueError("min_repeatable_count cannot be greater than max_repeatable_count")

        if self.isAction and (not self.actionType or not self.actionLabel):
            raise ValueError("action questions require actionType and actionLabel")

        return self


class QuestionCreateInput(QuestionBase):
    uuid: str
    versions: List[VersionCreateInput] = Field(default_factory=list)


class QuestionUpdateInput(SchemaModel):
    versions: Optional[List[VersionUpdateInput]] = None
    type: Optional[str] = None
    label: Optional[str] = None
    placeholder: Optional[str] = None
    description: Optional[str] = None
    default_value: Optional[Any] = None
    help_text: Optional[str] = None
    tooltip: Optional[str] = None
    validation_conditions: Optional[List[str]] = None
    validation_condition_messages: Optional[Dict[str, str]] = None
    visibility_conditions: Optional[List[str]] = None
    add_button: Optional[bool] = None
    is_repeatable: Optional[bool] = None
    repeatable_condition: Optional[str] = None
    check_repeat_on: Optional[str] = None
    min_repeatable_count: Optional[int] = None
    max_repeatable_count: Optional[int] = None
    isAction: Optional[bool] = None
    actionButtonType: Optional[str] = None
    actionType: Optional[str] = None
    actionLabel: Optional[str] = None
    tags: Optional[List[str]] = None
    choices: Optional[List[ChoiceUpdateInput]] = None
    hideButton: Optional[bool] = None
    actionIcon: Optional[str] = None
    status: Optional[DocumentStatus] = None


class QuestionRef(SchemaModel):
    uuid: str
    label: str
    type: str


class QuestionOutput(SchemaModel):
    uuid: str
    versions: List[VersionOutput] = Field(default_factory=list)
    type: str
    label: str
    placeholder: Optional[str] = None
    description: Optional[str] = None
    default_value: Optional[Any] = None
    help_text: Optional[str] = None
    tooltip: Optional[str] = None
    validation_conditions: List[str] = Field(default_factory=list)
    validation_condition_messages: Dict[str, str] = Field(default_factory=dict)
    visibility_conditions: List[str] = Field(default_factory=list)
    add_button: bool = False
    is_repeatable: bool = False
    repeatable_condition: Optional[str] = None
    check_repeat_on: Optional[str] = None
    min_repeatable_count: Optional[int] = None
    max_repeatable_count: Optional[int] = None
    isAction: bool = False
    actionButtonType: Optional[str] = None
    actionType: Optional[str] = None
    actionLabel: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    choices: List[ChoiceOutput] = Field(default_factory=list)
    hideButton: bool = False
    actionIcon: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    status: DocumentStatus = "active"
