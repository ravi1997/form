from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import Field, model_validator

from app.schemas.common import SchemaModel


ConditionType = Literal["regex", "comparison", "logical", "custom"]
DocumentStatus = Literal["active", "inactive", "deleted"]
LogicalJoinType = Literal["AND", "OR"]


class ConditionBase(SchemaModel):
    conditionType: ConditionType
    expression: Optional[str] = None
    targetField: Optional[str] = None
    sourceSectionUuid: Optional[str] = None
    operator: Optional[str] = None
    operands: List[str] = Field(default_factory=list)
    isNegated: bool = False
    subConditions: List[str] = Field(default_factory=list)
    logicalJoinType: Optional[LogicalJoinType] = None
    isActive: bool = True
    errorMessage: Optional[str] = None
    description: Optional[str] = None
    priority: int = 0
    stopEvaluationIfTrue: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
    status: DocumentStatus = "active"

    @model_validator(mode="after")
    def validate_condition_shape(self) -> "ConditionBase":
        is_logical = self.conditionType == "logical"

        if is_logical:
            if not self.logicalJoinType:
                raise ValueError("logicalJoinType is required for logical conditions")
            if not self.subConditions:
                raise ValueError("logical conditions require at least one sub-condition")
            if self.expression or self.operator or self.operands:
                raise ValueError(
                    "logical conditions cannot include expression/operator/operands"
                )
        else:
            if self.logicalJoinType:
                raise ValueError("logicalJoinType is only valid for logical conditions")
            if self.subConditions:
                raise ValueError("subConditions are only valid for logical conditions")

            if self.conditionType == "regex" and (not self.expression or not self.targetField):
                raise ValueError("regex conditions require expression and targetField")

            if self.conditionType == "comparison":
                if not self.targetField or not self.operator:
                    raise ValueError("comparison conditions require targetField and operator")
                if not self.operands:
                    raise ValueError("comparison conditions require at least one operand")

            if self.conditionType == "custom" and not self.expression:
                raise ValueError("custom conditions require expression")

        return self


class ConditionCreateInput(ConditionBase):
    uuid: str


class ConditionUpdateInput(SchemaModel):
    conditionType: Optional[ConditionType] = None
    expression: Optional[str] = None
    targetField: Optional[str] = None
    sourceSectionUuid: Optional[str] = None
    operator: Optional[str] = None
    operands: Optional[List[str]] = None
    isNegated: Optional[bool] = None
    subConditions: Optional[List[str]] = None
    logicalJoinType: Optional[LogicalJoinType] = None
    isActive: Optional[bool] = None
    errorMessage: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[int] = None
    stopEvaluationIfTrue: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None
    status: Optional[DocumentStatus] = None


class ConditionRef(SchemaModel):
    uuid: str


class ConditionOutput(ConditionBase):
    uuid: str
    created_at: datetime
    updated_at: datetime
