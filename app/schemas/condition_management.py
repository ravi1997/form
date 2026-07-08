from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import Field

from app.schemas.common import SchemaModel


class ConditionTestInput(SchemaModel):
    condition_uuid: str
    context: Dict[str, Any] = Field(default_factory=dict)
    enable_tracing: bool = True


class BatchConditionTestInput(SchemaModel):
    tests: List[ConditionTestInput] = Field(default_factory=list)


class BulkCreateConditionInput(SchemaModel):
    items: List[Dict[str, Any]]


class BulkUpdateConditionInput(SchemaModel):
    items: List[Dict[str, Any]]


class BulkDeleteConditionInput(SchemaModel):
    condition_uuids: List[str]


class BulkValidateConditionInput(SchemaModel):
    items: List[Dict[str, Any]]


class ApprovalTransitionInput(SchemaModel):
    target_state: str
    actor_user_uuid: Optional[str] = None
    note: Optional[str] = None


class ActorUserInput(SchemaModel):
    actor_user_uuid: Optional[str] = None


class VersionRestoreInput(SchemaModel):
    version: int
    actor_user_uuid: Optional[str] = None


class VersionRecordInput(SchemaModel):
    actor_user_uuid: Optional[str] = None
    action: str = "update"
    changelog: str = "manual"


class PresetUpsertInput(SchemaModel):
    uuid: str
    name: str
    condition_uuid: str
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    references: List[str] = Field(default_factory=list)
    auto_update: bool = False
    actor_user_uuid: Optional[str] = None
    changelog: str = "manual update"


class ImportPresetsInput(SchemaModel):
    presets: List[Dict[str, Any]] = Field(default_factory=list)
    actor_user_uuid: Optional[str] = None


class ConditionImpactInput(SchemaModel):
    sample_contexts: List[Dict[str, Any]] = Field(default_factory=list)


class BulkTestInput(SchemaModel):
    tests: List[ConditionTestInput] = Field(default_factory=list)


class BulkImportConditionsInput(SchemaModel):
    items: List[Dict[str, Any]] = Field(default_factory=list)
    overwrite: bool = False


class AsyncEvaluationInput(SchemaModel):
    condition_uuid: str
    context: Dict[str, Any] = Field(default_factory=dict)
    timeout_ms: int = 1000
    retries: int = 0
    fallback_result: bool = False


class ConditionMetadataResponse(SchemaModel):
    condition_types: List[str]
    operator_metadata: Dict[str, Dict[str, Any]]
    temporal_operators: List[str]
    arithmetic_functions: List[str]
    set_operators: List[str]


class ConditionTestResult(SchemaModel):
    condition_uuid: str
    matched: bool
    duration_ms: float
    trace: List[Dict[str, Any]] = Field(default_factory=list)
    execution_path: List[str] = Field(default_factory=list)
    operator: Optional[str] = None
    condition_type: Optional[str] = None


class BatchConditionTestResponse(SchemaModel):
    total: int
    matched: int
    failed: int
    results: List[ConditionTestResult] = Field(default_factory=list)
    started_at: datetime
    completed_at: datetime


class MessageResponse(SchemaModel):
    message: str


class ErrorResponse(SchemaModel):
    message: str
