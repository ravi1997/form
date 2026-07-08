from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import Field, model_validator

from app.schemas.common import SchemaModel

ConditionType = Literal[
    "regex",
    "comparison",
    "logical",
    "custom",
    "temporal",
    "arithmetic",
    "set",
    "dsl",
]
DocumentStatus = Literal["active", "inactive", "deleted"]
LogicalJoinType = Literal["AND", "OR"]


class ConditionBase(SchemaModel):
    conditionType: ConditionType
    expression: Optional[str] = None
    targetField: Optional[str] = None
    sourceSectionUuid: Optional[str] = None
    operator: Optional[str] = None
    operands: List[Any] = Field(default_factory=list)
    isNegated: bool = False
    subConditions: List[str] = Field(default_factory=list)
    logicalJoinType: Optional[LogicalJoinType] = None
    isActive: bool = True
    errorMessage: Optional[str] = None
    description: Optional[str] = None
    priority: int = 0
    stopEvaluationIfTrue: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
    approval_state: Literal[
        "draft", "review", "published", "deprecated", "archived"
    ] = "draft"
    status: DocumentStatus = "active"

    @model_validator(mode="after")
    def validate_condition_shape(self) -> "ConditionBase":
        is_logical = self.conditionType == "logical"

        if is_logical:
            if not self.logicalJoinType:
                raise ValueError("logicalJoinType is required for logical conditions")
            if not self.subConditions:
                raise ValueError(
                    "logical conditions require at least one sub-condition"
                )
            if self.expression or self.operator or self.operands:
                raise ValueError(
                    "logical conditions cannot include expression/operator/operands"
                )
        else:
            if self.logicalJoinType:
                raise ValueError("logicalJoinType is only valid for logical conditions")
            if self.subConditions:
                raise ValueError("subConditions are only valid for logical conditions")

            if self.conditionType == "regex" and (
                not self.expression or not self.targetField
            ):
                raise ValueError("regex conditions require expression and targetField")

            if self.conditionType in ("comparison", "temporal", "set"):
                if not self.targetField or not self.operator:
                    raise ValueError(
                        "comparison conditions require targetField and operator"
                    )
                if (
                    self.operator not in ("is_empty", "is_not_empty")
                    and not self.operands
                ):
                    raise ValueError(
                        "comparison conditions require at least one operand"
                    )

            if (
                self.conditionType in ("custom", "dsl", "arithmetic")
                and not self.expression
            ):
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
    operands: Optional[List[Any]] = None
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


# ============= Debugging & Testing Schemas =============


class ConditionTestRequest(SchemaModel):
    """Request to test a condition with mock data."""

    test_context: Dict[str, Any] = Field(
        description="Mock response data to test the condition against"
    )
    enable_tracing: bool = Field(
        default=True, description="Whether to include evaluation trace in response"
    )


class ConditionTestTraceStep(SchemaModel):
    """Single step in condition evaluation trace."""

    step: int
    type: str  # regex, comparison, logical
    result: bool
    operator: Optional[str] = None
    target_field: Optional[str] = None
    field_value: Optional[Any] = None
    operands: Optional[List[Any]] = None
    error: Optional[str] = None


class ConditionTestResponse(SchemaModel):
    """Response from testing a condition."""

    condition_uuid: str
    result: bool
    test_context: Dict[str, Any]
    trace: List[ConditionTestTraceStep] = Field(
        default_factory=list,
        description="Evaluation trace showing each step (if tracing enabled)",
    )
    evaluation_time_ms: float
    error: Optional[str] = None


class ConditionUsageResponse(SchemaModel):
    """Response showing where a condition is used."""

    condition_uuid: str
    total_actions: int
    actions: List[Dict[str, Any]] = Field(
        description="List of actions using this condition"
    )
    total_questions: int
    questions: List[Dict[str, Any]] = Field(
        description="List of questions containing actions with this condition"
    )


class ConditionImpactAnalysisRequest(SchemaModel):
    """Request to analyze what would change if a condition was modified."""

    condition_uuid: str
    test_responses_sample_size: int = Field(
        default=100, description="Number of past responses to test against"
    )
    new_condition_params: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Parameters for the modified condition (to see what would change)",
    )


class ConditionImpactAnalysisResponse(SchemaModel):
    """Response showing impact of condition changes."""

    condition_uuid: str
    current_match_count: int
    current_match_rate: float
    projected_match_count: Optional[int] = None
    projected_match_rate: Optional[float] = None
    affected_actions: List[str]
    affected_questions: List[str]
    sample_size: int
    analysis_time_ms: float


class CacheStatsResponse(SchemaModel):
    """Response showing cache statistics."""

    regex_cache: Dict[str, Any] = Field(
        description="Statistics for regex pattern cache"
    )
    ttl_cache: Optional[Dict[str, Any]] = Field(
        default=None, description="Statistics for TTL evaluation cache"
    )
    request_cache: Optional[Dict[str, Any]] = Field(
        default=None, description="Statistics for request-level cache"
    )
    negative_cache: Optional[Dict[str, Any]] = Field(
        default=None, description="Statistics for negative cache"
    )
    timestamp: datetime = Field(description="Timestamp of cache stats snapshot")


class CacheMetricsResponse(SchemaModel):
    """Response showing cache metrics and performance."""

    timestamp: datetime
    regex_cache_stats: Dict[str, Any]
    ttl_cache_stats: Optional[Dict[str, Any]] = None
    negative_cache_stats: Optional[Dict[str, Any]] = None
    total_memory_bytes: int = Field(description="Total cache memory usage")
    slow_conditions: List[Dict[str, Any]] = Field(
        description="Conditions taking > 100ms to evaluate"
    )
