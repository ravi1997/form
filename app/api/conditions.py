from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List


from app.models.form import Condition
from app.schemas.common import SchemaModel
from app.schemas.condition_management import (
    ActorUserInput,
    ApprovalTransitionInput,
    AsyncEvaluationInput,
    BatchConditionTestInput,
    BatchConditionTestResponse,
    BulkImportConditionsInput,
    BulkTestInput,
    BulkCreateConditionInput,
    BulkDeleteConditionInput,
    BulkUpdateConditionInput,
    BulkValidateConditionInput,
    ConditionImpactInput,
    ConditionMetadataResponse,
    ConditionTestInput,
    ConditionTestResult,
    ErrorResponse,
    ImportPresetsInput,
    MessageResponse,
    PresetUpsertInput,
    VersionRecordInput,
    VersionRestoreInput,
)
from app.schemas.mappers import to_condition_output, to_json_ready
from app.services.condition_cache import (
    get_global_historical_cache,
    get_global_invalidation_manager,
    get_global_negative_cache,
    get_global_ttl_cache,
)
from app.services.condition_evaluator import (
    ConditionEvaluationError,
    ConditionEvaluator,
    get_regex_cache_stats,
)
from app.services.condition_management import (
    ConditionManagementError,
    create_or_update_preset,
    discover_usage,
    enqueue_async_evaluation,
    export_presets,
    get_async_job_status,
    get_monitoring_snapshot,
    impact_analysis,
    import_presets,
    list_condition_versions,
    record_condition_version,
    record_evaluation_stat,
    restore_condition_version,
    rollback_approval_state,
    sync_auto_update_presets,
    transition_approval_state,
)

try:
    from flask_openapi3 import APIBlueprint, Tag
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("flask-openapi3 is required") from exc


condition_tag = Tag(
    name="Conditions",
    description="Condition testing, cache, presets, approval, versioning and analytics",
)
conditions_api = APIBlueprint("conditions", __name__, url_prefix="/api/v1/conditions")


TEMPORAL_OPERATORS = [
    "created_within_days",
    "updated_within_days",
    "older_than_days",
    "duration_exceeds",
    "duration_less_than",
]
SET_OPERATORS = ["any", "all", "none", "subset", "superset", "intersects"]


class ConditionPath(SchemaModel):
    condition_uuid: str


class AsyncJobPath(SchemaModel):
    job_id: str


def _error(message: str, status: int = 400):
    return to_json_ready(ErrorResponse(message=message)), status


def _condition_or_error(condition_uuid: str):
    condition = Condition.objects(uuid=condition_uuid).first()
    if not condition:
        return None, _error("Condition not found", 404)
    return condition, None


@conditions_api.get(
    "/metadata",
    tags=[condition_tag],
    responses={200: ConditionMetadataResponse},
)
def get_condition_metadata():
    return to_json_ready(
        ConditionMetadataResponse(
            condition_types=sorted(list(ConditionEvaluator.CONDITION_TYPES)),
            operator_metadata=ConditionEvaluator.OPERATOR_METADATA,
            temporal_operators=TEMPORAL_OPERATORS,
            arithmetic_functions=[
                "sum",
                "average",
                "min",
                "max",
                "count",
                "percentage",
                "weighted",
            ],
            set_operators=SET_OPERATORS,
        )
    )


@conditions_api.get("/operators/metadata", tags=[condition_tag])
def get_operator_metadata():
    return to_json_ready(ConditionEvaluator.OPERATOR_METADATA)


@conditions_api.post(
    "/test",
    tags=[condition_tag],
    responses={200: ConditionTestResult, 400: ErrorResponse, 404: ErrorResponse},
)
def test_condition(body: ConditionTestInput):
    condition, err = _condition_or_error(body.condition_uuid)
    if err:
        return err

    evaluator = ConditionEvaluator(
        context=body.context, enable_tracing=body.enable_tracing
    )
    started = datetime.utcnow()
    try:
        matched = evaluator.evaluate(condition)
    except ConditionEvaluationError as exc:
        return _error(str(exc), 400)

    ended = datetime.utcnow()
    duration_ms = (ended - started).total_seconds() * 1000
    record_evaluation_stat(condition, matched, duration_ms, endpoint="test")

    snapshot = evaluator.get_observability_snapshot()
    return to_json_ready(
        ConditionTestResult(
            condition_uuid=condition.uuid,
            matched=matched,
            duration_ms=duration_ms,
            trace=snapshot["trace"],
            execution_path=snapshot["execution_path"],
            operator=condition.operator,
            condition_type=condition.conditionType,
        )
    )


@conditions_api.post(
    "/test/batch",
    tags=[condition_tag],
    responses={200: BatchConditionTestResponse, 400: ErrorResponse},
)
def test_conditions_batch(body: BatchConditionTestInput):
    started = datetime.utcnow()
    results: List[ConditionTestResult] = []
    matched = 0
    failed = 0

    for test in body.tests:
        condition = Condition.objects(uuid=test.condition_uuid).first()
        if not condition:
            failed += 1
            results.append(
                ConditionTestResult(
                    condition_uuid=test.condition_uuid,
                    matched=False,
                    duration_ms=0,
                    trace=[{"error": "Condition not found"}],
                    execution_path=[],
                )
            )
            continue

        evaluator = ConditionEvaluator(
            context=test.context, enable_tracing=test.enable_tracing
        )
        run_start = datetime.utcnow()
        try:
            run_matched = evaluator.evaluate(condition)
        except ConditionEvaluationError as exc:
            failed += 1
            results.append(
                ConditionTestResult(
                    condition_uuid=condition.uuid,
                    matched=False,
                    duration_ms=(datetime.utcnow() - run_start).total_seconds() * 1000,
                    trace=[{"error": str(exc)}],
                    execution_path=[],
                    operator=condition.operator,
                    condition_type=condition.conditionType,
                )
            )
            continue

        run_duration = (datetime.utcnow() - run_start).total_seconds() * 1000
        if run_matched:
            matched += 1
        record_evaluation_stat(
            condition, run_matched, run_duration, endpoint="batch_test"
        )
        snap = evaluator.get_observability_snapshot()
        results.append(
            ConditionTestResult(
                condition_uuid=condition.uuid,
                matched=run_matched,
                duration_ms=run_duration,
                trace=snap["trace"],
                execution_path=snap["execution_path"],
                operator=condition.operator,
                condition_type=condition.conditionType,
            )
        )

    completed = datetime.utcnow()
    return to_json_ready(
        BatchConditionTestResponse(
            total=len(body.tests),
            matched=matched,
            failed=failed,
            results=results,
            started_at=started,
            completed_at=completed,
        )
    )


@conditions_api.get("/cache/metrics", tags=[condition_tag])
def cache_metrics():
    ttl = get_global_ttl_cache()
    hist = get_global_historical_cache()
    neg = get_global_negative_cache()

    response: Dict[str, Any] = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "regex_cache": get_regex_cache_stats(),
        "ttl_cache": ttl.get_stats().to_dict() if ttl else None,
        "historical_cache": hist.get_stats().to_dict() if hist else None,
        "negative_cache": neg.get_stats().to_dict() if neg else None,
        "historical_hot_keys": hist.get_hot_keys() if hist else {},
    }

    total_mem = 0
    for key in ("ttl_cache", "historical_cache", "negative_cache"):
        if response.get(key):
            total_mem += int(response[key].get("memory_bytes", 0))
    response["total_memory_bytes"] = total_mem
    return to_json_ready(response)


@conditions_api.post(
    "/cache/invalidate/<condition_uuid>",
    tags=[condition_tag],
    responses={200: MessageResponse},
)
def invalidate_cache(path: ConditionPath):
    manager = get_global_invalidation_manager()
    if not manager:
        return _error("Cache manager not initialized", 500)
    stats = manager.invalidate_condition(path.condition_uuid)
    return to_json_ready(
        {
            "message": "cache_invalidated",
            "condition_uuid": path.condition_uuid,
            "stats": stats,
        }
    )


@conditions_api.get(
    "/usage/<condition_uuid>",
    tags=[condition_tag],
    responses={200: MessageResponse, 404: ErrorResponse},
)
def get_usage(path: ConditionPath):
    condition, err = _condition_or_error(path.condition_uuid)
    if err:
        return err
    return to_json_ready(discover_usage(condition.uuid))


@conditions_api.post(
    "/impact/<condition_uuid>",
    tags=[condition_tag],
    responses={200: MessageResponse, 404: ErrorResponse},
)
def get_impact(path: ConditionPath, body: ConditionImpactInput):
    condition, err = _condition_or_error(path.condition_uuid)
    if err:
        return err
    sample_contexts = body.sample_contexts or []
    return to_json_ready(
        impact_analysis(condition.uuid, sample_contexts=sample_contexts)
    )


@conditions_api.get("/monitoring/graph", tags=[condition_tag])
def monitoring_graph():
    return to_json_ready({"graph": get_monitoring_snapshot().get("graph", [])})


@conditions_api.get("/monitoring/heatmap", tags=[condition_tag])
def monitoring_heatmap():
    return to_json_ready({"heatmap": get_monitoring_snapshot().get("heatmap", {})})


@conditions_api.get("/monitoring/unused", tags=[condition_tag])
def monitoring_unused():
    return to_json_ready({"unused": get_monitoring_snapshot().get("unused", [])})


@conditions_api.get("/monitoring/most-used", tags=[condition_tag])
def monitoring_most_used():
    return to_json_ready({"most_used": get_monitoring_snapshot().get("most_used", [])})


@conditions_api.get("/monitoring/evaluation-stats", tags=[condition_tag])
def monitoring_evaluation_stats():
    return to_json_ready(
        {"evaluation_stats": get_monitoring_snapshot().get("evaluation_stats", [])}
    )


@conditions_api.post(
    "/presets",
    tags=[condition_tag],
    responses={200: MessageResponse, 400: ErrorResponse},
)
def upsert_preset(body: PresetUpsertInput):
    try:
        preset = create_or_update_preset(
            preset_uuid=body.uuid,
            name=body.name,
            condition_uuid=body.condition_uuid,
            description=body.description,
            tags=body.tags,
            references=body.references,
            auto_update=body.auto_update,
            actor_user_uuid=body.actor_user_uuid,
            changelog=body.changelog,
        )
    except ConditionManagementError as exc:
        return _error(str(exc))

    return to_json_ready(
        {
            "uuid": preset.uuid,
            "name": preset.name,
            "condition_uuid": preset.condition_uuid,
            "current_version": preset.current_version,
            "references": list(preset.references or []),
            "auto_update": preset.auto_update,
        }
    )


@conditions_api.get("/presets", tags=[condition_tag])
def list_presets():
    return to_json_ready(export_presets())


@conditions_api.post("/presets/import", tags=[condition_tag])
def import_preset_payload(body: ImportPresetsInput):
    return to_json_ready(
        import_presets(body.model_dump(), actor_user_uuid=body.actor_user_uuid)
    )


@conditions_api.get("/presets/export", tags=[condition_tag])
def export_preset_payload():
    return to_json_ready(export_presets())


@conditions_api.post(
    "/<condition_uuid>/approval/transition",
    tags=[condition_tag],
    responses={200: MessageResponse, 400: ErrorResponse, 404: ErrorResponse},
)
def approval_transition(path: ConditionPath, body: ApprovalTransitionInput):
    condition, err = _condition_or_error(path.condition_uuid)
    if err:
        return err
    try:
        result = transition_approval_state(
            condition,
            body.target_state,
            actor_user_uuid=body.actor_user_uuid,
            note=body.note,
        )
    except ConditionManagementError as exc:
        return _error(str(exc))
    return to_json_ready(result)


@conditions_api.post(
    "/<condition_uuid>/approval/rollback",
    tags=[condition_tag],
    responses={200: MessageResponse, 400: ErrorResponse, 404: ErrorResponse},
)
def approval_rollback(path: ConditionPath, body: ActorUserInput):
    condition, err = _condition_or_error(path.condition_uuid)
    if err:
        return err
    try:
        result = rollback_approval_state(
            condition, actor_user_uuid=body.actor_user_uuid
        )
    except ConditionManagementError as exc:
        return _error(str(exc))
    return to_json_ready(result)


@conditions_api.get(
    "/<condition_uuid>/versions",
    tags=[condition_tag],
    responses={200: MessageResponse, 404: ErrorResponse},
)
def get_condition_versions(path: ConditionPath):
    condition, err = _condition_or_error(path.condition_uuid)
    if err:
        return err
    versions = list_condition_versions(condition.uuid)
    return to_json_ready(
        {
            "condition_uuid": condition.uuid,
            "versions": [
                {
                    "version": v.version,
                    "snapshot": v.snapshot,
                    "diff": v.diff,
                    "changelog": v.changelog,
                    "action": v.action,
                    "actor_user_uuid": v.actor_user_uuid,
                    "created_at": v.created_at.isoformat() + "Z",
                }
                for v in versions
            ],
        }
    )


@conditions_api.post(
    "/<condition_uuid>/versions/record",
    tags=[condition_tag],
    responses={200: MessageResponse, 404: ErrorResponse},
)
def record_version(path: ConditionPath, body: VersionRecordInput):
    condition, err = _condition_or_error(path.condition_uuid)
    if err:
        return err
    entry = record_condition_version(
        condition,
        actor_user_uuid=body.actor_user_uuid,
        action=body.action,
        changelog=body.changelog,
    )
    sync_auto_update_presets(condition)
    return to_json_ready({"condition_uuid": condition.uuid, "version": entry.version})


@conditions_api.post(
    "/<condition_uuid>/versions/restore",
    tags=[condition_tag],
    responses={200: MessageResponse, 400: ErrorResponse, 404: ErrorResponse},
)
def restore_version(path: ConditionPath, body: VersionRestoreInput):
    _, err = _condition_or_error(path.condition_uuid)
    if err:
        return err
    try:
        condition = restore_condition_version(
            path.condition_uuid, body.version, actor_user_uuid=body.actor_user_uuid
        )
    except ConditionManagementError as exc:
        return _error(str(exc))
    return to_json_ready(
        {
            "message": "version_restored",
            "condition": to_json_ready(to_condition_output(condition)),
        }
    )


@conditions_api.post(
    "/bulk/create",
    tags=[condition_tag],
    responses={200: MessageResponse, 400: ErrorResponse},
)
def bulk_create_conditions(body: BulkCreateConditionInput):
    created = []
    errors = []
    for item in body.items:
        try:
            condition = Condition(**item)
            condition.save()
            record_condition_version(condition, action="create")
            created.append(condition.uuid)
        except Exception as exc:
            errors.append(str(exc))
    return to_json_ready({"created": created, "errors": errors})


@conditions_api.patch(
    "/bulk/update",
    tags=[condition_tag],
    responses={200: MessageResponse, 400: ErrorResponse},
)
def bulk_update_conditions(body: BulkUpdateConditionInput):
    updated = []
    errors = []
    for item in body.items:
        condition = Condition.objects(uuid=item.get("uuid")).first()
        if not condition:
            errors.append(f"Condition not found: {item.get('uuid')}")
            continue
        try:
            for key, value in item.items():
                if key == "uuid":
                    continue
                setattr(condition, key, value)
            condition.save()
            record_condition_version(condition, action="update")
            sync_auto_update_presets(condition)
            updated.append(condition.uuid)
        except Exception as exc:
            errors.append(str(exc))
    return to_json_ready({"updated": updated, "errors": errors})


@conditions_api.delete(
    "/bulk/delete",
    tags=[condition_tag],
    responses={200: MessageResponse, 400: ErrorResponse},
)
def bulk_delete_conditions(body: BulkDeleteConditionInput):
    deleted = []
    skipped = []
    for condition_uuid in body.condition_uuids:
        usage = discover_usage(condition_uuid)
        if not usage["can_delete"]:
            skipped.append(
                {"condition_uuid": condition_uuid, "reason": "condition is in use"}
            )
            continue
        condition = Condition.objects(uuid=condition_uuid).first()
        if condition:
            condition.delete()
            deleted.append(condition_uuid)
    return to_json_ready({"deleted": deleted, "skipped": skipped})


@conditions_api.post(
    "/bulk/validate", tags=[condition_tag], responses={200: MessageResponse}
)
def bulk_validate_conditions(body: BulkValidateConditionInput):
    valid = []
    invalid = []
    for item in body.items:
        try:
            condition = Condition(**item)
            condition.validate()
            valid.append(item.get("uuid"))
        except Exception as exc:
            invalid.append({"uuid": item.get("uuid"), "error": str(exc)})
    return to_json_ready({"valid": valid, "invalid": invalid})


@conditions_api.post(
    "/bulk/test", tags=[condition_tag], responses={200: MessageResponse}
)
def bulk_test_conditions(body: BulkTestInput):
    tests = body.tests or []
    payload = BatchConditionTestInput(tests=tests)
    return test_conditions_batch(payload)


@conditions_api.post(
    "/bulk/import", tags=[condition_tag], responses={200: MessageResponse}
)
def bulk_import_conditions(body: BulkImportConditionsInput):
    return bulk_create_conditions(BulkCreateConditionInput(items=body.items or []))


@conditions_api.get(
    "/bulk/export", tags=[condition_tag], responses={200: MessageResponse}
)
def bulk_export_conditions():
    data = [
        to_json_ready(to_condition_output(condition)) for condition in Condition.objects
    ]
    return to_json_ready({"items": data, "count": len(data)})


@conditions_api.post(
    "/async/evaluate",
    tags=[condition_tag],
    responses={200: MessageResponse, 400: ErrorResponse, 404: ErrorResponse},
)
def async_evaluate_condition(body: AsyncEvaluationInput):
    try:
        job = enqueue_async_evaluation(
            body.condition_uuid,
            body.context,
            timeout_ms=body.timeout_ms,
            retries=body.retries,
            fallback_result=body.fallback_result,
        )
    except ConditionManagementError as exc:
        return _error(str(exc), 404)
    return to_json_ready({"job_id": job.job_id, "status": job.status})


@conditions_api.get(
    "/async/<job_id>",
    tags=[condition_tag],
    responses={200: MessageResponse, 404: ErrorResponse},
)
def async_evaluate_status(path: AsyncJobPath):
    try:
        return to_json_ready(get_async_job_status(path.job_id))
    except ConditionManagementError as exc:
        return _error(str(exc), 404)
