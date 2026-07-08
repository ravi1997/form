from __future__ import annotations

import copy
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from threading import Lock, Thread
from typing import Any, Dict, List, Optional

from app.models.condition_management import (
    APPROVAL_STATE_CHOICES,
    ConditionApprovalAudit,
    ConditionAsyncJob,
    ConditionEvaluationStat,
    ConditionPreset,
    ConditionPresetVersion,
    ConditionVersion,
)
from app.models.form import Condition, FormResponse, Question
from app.services.condition_evaluator import (
    ConditionEvaluationContext,
    ConditionEvaluationError,
    ConditionEvaluator,
)

APPROVAL_TRANSITIONS = {
    "draft": {"review", "archived"},
    "review": {"published", "draft", "archived"},
    "published": {"deprecated", "archived"},
    "deprecated": {"published", "archived"},
    "archived": set(),
}


class ConditionManagementError(ValueError):
    pass


class InMemoryConditionQueue:
    """Queue abstraction for async evaluation."""

    def __init__(self):
        self._lock = Lock()

    def enqueue(self, func, *args, **kwargs) -> None:
        thread = Thread(target=func, args=args, kwargs=kwargs, daemon=True)
        thread.start()


_default_queue = InMemoryConditionQueue()


def _serialize_condition(condition: Condition) -> Dict[str, Any]:
    return {
        "uuid": condition.uuid,
        "conditionType": condition.conditionType,
        "expression": condition.expression,
        "targetField": condition.targetField,
        "sourceSectionUuid": condition.sourceSectionUuid,
        "operator": condition.operator,
        "operands": list(condition.operands or []),
        "isNegated": bool(condition.isNegated),
        "subConditions": [
            str(getattr(c, "id", c)) for c in (condition.subConditions or [])
        ],
        "logicalJoinType": condition.logicalJoinType,
        "isActive": bool(condition.isActive),
        "errorMessage": condition.errorMessage,
        "description": condition.description,
        "priority": int(condition.priority or 0),
        "stopEvaluationIfTrue": bool(condition.stopEvaluationIfTrue),
        "metadata": dict(condition.metadata or {}),
        "status": condition.status,
        "updated_at": condition.updated_at.isoformat()
        if condition.updated_at
        else None,
    }


def _diff_dict(old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    diff: Dict[str, Any] = {}
    keys = set(old.keys()).union(new.keys())
    for key in keys:
        if old.get(key) != new.get(key):
            diff[key] = {"from": old.get(key), "to": new.get(key)}
    return diff


def record_condition_version(
    condition: Condition,
    actor_user_uuid: Optional[str] = None,
    action: str = "update",
    changelog: str = "",
) -> ConditionVersion:
    latest = (
        ConditionVersion.objects(condition_uuid=condition.uuid)
        .order_by("-version")
        .first()
    )
    new_version = (latest.version + 1) if latest else 1
    snapshot = _serialize_condition(condition)
    prev_snapshot = latest.snapshot if latest else {}
    entry = ConditionVersion(
        condition_uuid=condition.uuid,
        version=new_version,
        snapshot=snapshot,
        diff=_diff_dict(prev_snapshot, snapshot),
        changelog=changelog,
        action=action,
        actor_user_uuid=actor_user_uuid,
    )
    entry.save()
    return entry


def list_condition_versions(condition_uuid: str) -> List[ConditionVersion]:
    return list(
        ConditionVersion.objects(condition_uuid=condition_uuid).order_by("version")
    )


def restore_condition_version(
    condition_uuid: str, version: int, actor_user_uuid: Optional[str] = None
) -> Condition:
    item = Condition.objects(uuid=condition_uuid).first()
    if not item:
        raise ConditionManagementError("Condition not found")
    version_entry = ConditionVersion.objects(
        condition_uuid=condition_uuid, version=version
    ).first()
    if not version_entry:
        raise ConditionManagementError("Version not found")

    data = copy.deepcopy(version_entry.snapshot)
    for key in ["uuid", "updated_at"]:
        data.pop(key, None)

    for key, value in data.items():
        if key == "subConditions":
            continue
        setattr(item, key, value)

    item.save()
    record_condition_version(
        item,
        actor_user_uuid=actor_user_uuid,
        action="restore",
        changelog=f"restored to version {version}",
    )
    return item


def ensure_publishable(condition: Condition) -> List[str]:
    errors: List[str] = []
    if not condition.isActive:
        errors.append("Condition must be active before publishing")
    if (
        condition.conditionType in {"comparison", "temporal", "set"}
        and not condition.operator
    ):
        errors.append("Operator is required")
    if (
        condition.conditionType in {"comparison", "temporal", "set"}
        and not condition.targetField
    ):
        errors.append("targetField is required")
    if condition.conditionType == "custom" and not condition.expression:
        errors.append("Expression is required")
    if condition.conditionType == "logical" and not condition.subConditions:
        errors.append("Logical condition requires subConditions")
    return errors


def transition_approval_state(
    condition: Condition,
    target_state: str,
    actor_user_uuid: Optional[str] = None,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    if target_state not in APPROVAL_STATE_CHOICES:
        raise ConditionManagementError(f"Invalid state: {target_state}")

    current_state = (condition.metadata or {}).get("approval_state", "draft")
    allowed = APPROVAL_TRANSITIONS.get(current_state, set())
    if target_state not in allowed:
        raise ConditionManagementError(
            f"Transition not allowed: {current_state} -> {target_state}"
        )

    validation_errors: List[str] = []
    if target_state == "published":
        validation_errors = ensure_publishable(condition)
        if validation_errors:
            raise ConditionManagementError("; ".join(validation_errors))

    metadata = dict(condition.metadata or {})
    metadata["approval_state"] = target_state
    metadata["approval_updated_at"] = datetime.utcnow().isoformat() + "Z"
    if target_state == "published":
        metadata["published_at"] = datetime.utcnow().isoformat() + "Z"

    condition.metadata = metadata
    condition.save()

    ConditionApprovalAudit(
        condition_uuid=condition.uuid,
        from_state=current_state,
        to_state=target_state,
        actor_user_uuid=actor_user_uuid,
        note=note,
        validation_errors=validation_errors,
    ).save()

    return {
        "condition_uuid": condition.uuid,
        "from_state": current_state,
        "to_state": target_state,
        "validation_errors": validation_errors,
    }


def rollback_approval_state(
    condition: Condition, actor_user_uuid: Optional[str] = None
) -> Dict[str, Any]:
    latest = (
        ConditionApprovalAudit.objects(condition_uuid=condition.uuid)
        .order_by("-created_at")
        .first()
    )
    if not latest:
        raise ConditionManagementError("No approval history available")
    previous_state = latest.from_state or "draft"
    metadata = dict(condition.metadata or {})
    current_state = metadata.get("approval_state", "draft")
    metadata["approval_state"] = previous_state
    metadata["approval_updated_at"] = datetime.utcnow().isoformat() + "Z"
    condition.metadata = metadata
    condition.save()

    ConditionApprovalAudit(
        condition_uuid=condition.uuid,
        from_state=current_state,
        to_state=previous_state,
        actor_user_uuid=actor_user_uuid,
        note="rollback",
    ).save()

    return {
        "condition_uuid": condition.uuid,
        "from_state": current_state,
        "to_state": previous_state,
    }


def create_or_update_preset(
    *,
    preset_uuid: str,
    name: str,
    condition_uuid: str,
    description: Optional[str] = None,
    tags: Optional[List[str]] = None,
    references: Optional[List[str]] = None,
    auto_update: bool = False,
    actor_user_uuid: Optional[str] = None,
    changelog: str = "manual update",
) -> ConditionPreset:
    condition = Condition.objects(uuid=condition_uuid).first()
    if not condition:
        raise ConditionManagementError("Condition not found")

    snapshot = _serialize_condition(condition)
    preset = ConditionPreset.objects(uuid=preset_uuid).first()
    if not preset:
        preset = ConditionPreset(
            uuid=preset_uuid,
            name=name,
            condition_uuid=condition_uuid,
            condition_snapshot=snapshot,
            description=description,
            tags=tags or [],
            references=references or [],
            auto_update=auto_update,
            created_by=actor_user_uuid,
            updated_by=actor_user_uuid,
        )
    else:
        preset.name = name
        preset.description = description or preset.description
        preset.tags = tags or preset.tags
        preset.references = references or preset.references
        preset.auto_update = auto_update
        preset.condition_uuid = condition_uuid
        preset.condition_snapshot = snapshot
        preset.updated_by = actor_user_uuid
        preset.current_version += 1
        preset.versions.append(
            ConditionPresetVersion(
                version=preset.current_version,
                condition_snapshot=snapshot,
                changelog=changelog,
            )
        )

    preset.save()
    return preset


def export_presets() -> Dict[str, Any]:
    presets = []
    for preset in ConditionPreset.objects:
        presets.append(
            {
                "uuid": preset.uuid,
                "name": preset.name,
                "description": preset.description,
                "condition_uuid": preset.condition_uuid,
                "condition_snapshot": preset.condition_snapshot,
                "current_version": preset.current_version,
                "versions": [
                    {
                        "version": v.version,
                        "condition_snapshot": v.condition_snapshot,
                        "changelog": v.changelog,
                        "created_at": v.created_at.isoformat()
                        if v.created_at
                        else None,
                    }
                    for v in (preset.versions or [])
                ],
                "references": list(preset.references or []),
                "auto_update": bool(preset.auto_update),
                "status": preset.status,
            }
        )
    return {"presets": presets, "exported_at": datetime.utcnow().isoformat() + "Z"}


def import_presets(
    payload: Dict[str, Any], actor_user_uuid: Optional[str] = None
) -> Dict[str, Any]:
    created = 0
    updated = 0
    failed: List[str] = []

    for preset in payload.get("presets", []):
        try:
            preset_uuid = preset["uuid"]
            name = preset["name"]
            condition_uuid = preset["condition_uuid"]
            create_or_update_preset(
                preset_uuid=preset_uuid,
                name=name,
                condition_uuid=condition_uuid,
                description=preset.get("description"),
                tags=preset.get("tags") or [],
                references=preset.get("references") or [],
                auto_update=bool(preset.get("auto_update", False)),
                actor_user_uuid=actor_user_uuid,
                changelog="import",
            )
            if ConditionPreset.objects(uuid=preset_uuid).count() == 1:
                updated += 1
            else:
                created += 1
        except Exception as exc:
            failed.append(str(exc))

    return {
        "created": created,
        "updated": updated,
        "failed": failed,
    }


def sync_auto_update_presets(condition: Condition) -> int:
    count = 0
    for preset in ConditionPreset.objects(
        condition_uuid=condition.uuid, auto_update=True
    ):
        preset.current_version += 1
        snapshot = _serialize_condition(condition)
        preset.condition_snapshot = snapshot
        preset.versions.append(
            ConditionPresetVersion(
                version=preset.current_version,
                condition_snapshot=snapshot,
                changelog="auto update",
            )
        )
        preset.save()
        count += 1
    return count


def discover_usage(condition_uuid: str) -> Dict[str, Any]:
    used_by_questions = Question.objects(
        validation_conditions=Condition.objects(uuid=condition_uuid).first()
    )
    explicit_graph = defaultdict(list)
    reverse_graph = defaultdict(list)

    for condition in Condition.objects:
        deps = []
        for sub in condition.subConditions or []:
            ref = sub.fetch() if hasattr(sub, "fetch") else sub
            if ref and ref.uuid:
                deps.append(ref.uuid)
                reverse_graph[ref.uuid].append(condition.uuid)
        explicit_graph[condition.uuid] = deps

    return {
        "condition_uuid": condition_uuid,
        "question_count": used_by_questions.count(),
        "questions": [q.uuid for q in used_by_questions],
        "depends_on": explicit_graph.get(condition_uuid, []),
        "reverse_dependencies": reverse_graph.get(condition_uuid, []),
        "can_delete": used_by_questions.count() == 0
        and len(reverse_graph.get(condition_uuid, [])) == 0,
        "is_orphan": used_by_questions.count() == 0
        and len(explicit_graph.get(condition_uuid, [])) == 0,
    }


def impact_analysis(
    condition_uuid: str, sample_contexts: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    condition = Condition.objects(uuid=condition_uuid).first()
    if not condition:
        raise ConditionManagementError("Condition not found")

    contexts = sample_contexts or [{"value": "sample", "status": "draft", "score": 1}]
    start = datetime.utcnow()
    evaluator = ConditionEvaluator(enable_tracing=False)

    current_matches = 0
    for ctx in contexts:
        evaluator.context = ctx
        if evaluator.evaluate(condition):
            current_matches += 1

    return {
        "condition_uuid": condition_uuid,
        "sample_size": len(contexts),
        "current_match_count": current_matches,
        "current_match_rate": current_matches / len(contexts) if contexts else 0,
        "affected_conditions": [condition_uuid]
        + discover_usage(condition_uuid)["reverse_dependencies"],
        "analysis_time_ms": (datetime.utcnow() - start).total_seconds() * 1000,
    }


def record_evaluation_stat(
    condition: Condition, matched: bool, duration_ms: float, endpoint: str = ""
) -> None:
    ConditionEvaluationStat(
        condition_uuid=condition.uuid,
        endpoint=endpoint,
        matched=matched,
        duration_ms=duration_ms,
        operator=condition.operator,
        condition_type=condition.conditionType,
    ).save()


def get_monitoring_snapshot(window_days: int = 30) -> Dict[str, Any]:
    since = datetime.utcnow() - timedelta(days=window_days)
    rows = ConditionEvaluationStat.objects(created_at__gte=since)

    usage: Counter[str] = Counter()
    matched: Counter[str] = Counter()
    durations: Dict[str, List[float]] = defaultdict(list)
    heatmap: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for row in rows:
        usage[row.condition_uuid] += 1
        if row.matched:
            matched[row.condition_uuid] += 1
        durations[row.condition_uuid].append(row.duration_ms)
        day_key = row.created_at.strftime("%Y-%m-%d")
        heatmap[day_key][row.condition_uuid] += 1

    all_condition_uuids = [c.uuid for c in Condition.objects]
    unused = [cid for cid in all_condition_uuids if usage[cid] == 0]
    most_used = usage.most_common(10)

    evaluation_stats = []
    for condition_uuid, count in usage.items():
        avg = sum(durations[condition_uuid]) / len(durations[condition_uuid])
        evaluation_stats.append(
            {
                "condition_uuid": condition_uuid,
                "total_evaluations": count,
                "matched": matched[condition_uuid],
                "match_rate": matched[condition_uuid] / count if count else 0,
                "avg_duration_ms": round(avg, 3),
            }
        )

    graph = []
    for condition in Condition.objects:
        for sub in condition.subConditions or []:
            ref = sub.fetch() if hasattr(sub, "fetch") else sub
            if ref and ref.uuid:
                graph.append({"from": condition.uuid, "to": ref.uuid})

    return {
        "graph": graph,
        "heatmap": {day: dict(values) for day, values in heatmap.items()},
        "unused": unused,
        "most_used": [
            {"condition_uuid": cid, "count": count} for cid, count in most_used
        ],
        "evaluation_stats": evaluation_stats,
    }


def _run_async_job(job_id: str, retry_count: int = 0) -> None:
    job = ConditionAsyncJob.objects(job_id=job_id).first()
    if not job:
        return
    condition = Condition.objects(uuid=job.condition_uuid).first()
    if not condition:
        job.status = "failed"
        job.error = "Condition not found"
        job.save()
        return

    evaluator = ConditionEvaluator(
        context=job.context,
        enable_tracing=True,
        timeout_ms=job.timeout_ms,
    )
    job.status = "running"
    job.started_at = datetime.utcnow()
    job.save()

    try:
        result = evaluator.evaluate(condition)
        snapshot = evaluator.get_observability_snapshot()
        job.result = bool(result)
        job.trace = snapshot["trace"]
        job.status = "success"
        job.completed_at = datetime.utcnow()
        job.save()
    except ConditionEvaluationError as exc:
        job.error = str(exc)
        if "timeout" in str(exc).lower() and retry_count < job.retries:
            _run_async_job(job_id, retry_count + 1)
            return
        job.status = "timeout" if "timeout" in str(exc).lower() else "failed"
        job.result = bool(job.fallback_result)
        job.completed_at = datetime.utcnow()
        job.save()


def enqueue_async_evaluation(
    condition_uuid: str,
    context: Dict[str, Any],
    *,
    timeout_ms: int = 1000,
    retries: int = 0,
    fallback_result: bool = False,
    queue: Optional[InMemoryConditionQueue] = None,
) -> ConditionAsyncJob:
    condition = Condition.objects(uuid=condition_uuid).first()
    if not condition:
        raise ConditionManagementError("Condition not found")

    job = ConditionAsyncJob(
        job_id=str(uuid.uuid4()),
        condition_uuid=condition_uuid,
        context=context,
        timeout_ms=timeout_ms,
        retries=retries,
        fallback_result=fallback_result,
        status="queued",
    )
    job.save()

    (queue or _default_queue).enqueue(_run_async_job, job.job_id)
    return job


def get_async_job_status(job_id: str) -> Dict[str, Any]:
    job = ConditionAsyncJob.objects(job_id=job_id).first()
    if not job:
        raise ConditionManagementError("Job not found")

    return {
        "job_id": job.job_id,
        "condition_uuid": job.condition_uuid,
        "status": job.status,
        "result": job.result,
        "error": job.error,
        "trace": list(job.trace or []),
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


def operator_metadata() -> Dict[str, Dict[str, Any]]:
    return dict(ConditionEvaluator.OPERATOR_METADATA)


def condition_presets() -> List[Dict[str, Any]]:
    return [
        {
            "uuid": preset.uuid,
            "name": preset.name,
            "description": preset.description,
            "condition_uuid": preset.condition_uuid,
            "current_version": preset.current_version,
            "status": preset.status,
            "tags": list(preset.tags or []),
        }
        for preset in ConditionPreset.objects
    ]


def build_dependency_graph() -> Dict[str, List[str]]:
    graph = defaultdict(list)
    for condition in Condition.objects:
        deps = []
        for sub in condition.subConditions or []:
            ref = sub.fetch() if hasattr(sub, "fetch") else sub
            if ref and ref.uuid:
                deps.append(ref.uuid)
        graph[condition.uuid] = sorted(set(deps))
    return dict(graph)


def reverse_dependency_graph(
    graph: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, List[str]]:
    base = graph or build_dependency_graph()
    reverse = defaultdict(list)
    for condition_uuid, deps in base.items():
        for dep in deps:
            reverse[dep].append(condition_uuid)
    for key in base:
        reverse.setdefault(key, [])
    return {key: sorted(set(values)) for key, values in reverse.items()}


def detect_circular_references(
    graph: Optional[Dict[str, List[str]]] = None,
) -> List[List[str]]:
    base = graph or build_dependency_graph()
    visited = set()
    stack = set()
    path: List[str] = []
    cycles: List[List[str]] = []

    def dfs(node: str) -> None:
        visited.add(node)
        stack.add(node)
        path.append(node)
        for child in base.get(node, []):
            if child not in visited:
                dfs(child)
            elif child in stack:
                start = path.index(child)
                cycles.append(path[start:] + [child])
        stack.remove(node)
        path.pop()

    for node in base.keys():
        if node not in visited:
            dfs(node)
    return cycles


def calculate_complexity_score(
    condition: Condition, graph: Optional[Dict[str, List[str]]] = None
) -> Dict[str, Any]:
    base_score = ConditionEvaluator().complexity_score(condition)
    deps = (
        graph.get(condition.uuid, [])
        if graph
        else build_dependency_graph().get(condition.uuid, [])
    )
    score = base_score + len(deps)
    level = "low"
    if score >= 12:
        level = "high"
    elif score >= 7:
        level = "medium"
    return {"score": score, "level": level, "dependency_count": len(deps)}


def collect_condition_usage(condition_uuid: str) -> Dict[str, Any]:
    return discover_usage(condition_uuid)


def validate_safe_delete(condition_uuid: str) -> Dict[str, Any]:
    usage = discover_usage(condition_uuid)
    return {
        "condition_uuid": condition_uuid,
        "safe_to_delete": usage["can_delete"],
        "blockers": {
            "question_count": usage["question_count"],
            "reverse_dependencies": usage["reverse_dependencies"],
        },
        "usage": usage,
    }


def create_condition_version_snapshot(
    condition: Condition,
    actor_user_uuid: Optional[str] = None,
    reason: str = "update",
) -> Dict[str, Any]:
    version = record_condition_version(
        condition,
        actor_user_uuid=actor_user_uuid,
        action="update",
        changelog=reason,
    )
    return {
        "condition_uuid": version.condition_uuid,
        "version": version.version,
        "changelog": version.changelog,
        "created_at": version.created_at.isoformat() if version.created_at else None,
    }


def get_condition_versions(condition: Condition) -> List[Dict[str, Any]]:
    return [
        {
            "version": v.version,
            "snapshot": v.snapshot,
            "diff": v.diff,
            "changelog": v.changelog,
            "action": v.action,
            "actor_user_uuid": v.actor_user_uuid,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        }
        for v in list_condition_versions(condition.uuid)
    ]


def rollback_condition_to_version(
    condition: Condition,
    version_id: str,
    actor_user_uuid: Optional[str] = None,
) -> Condition:
    try:
        version_number = int(str(version_id).replace("v", ""))
    except ValueError as exc:
        raise ConditionManagementError("Invalid version id") from exc
    return restore_condition_version(
        condition.uuid,
        version_number,
        actor_user_uuid=actor_user_uuid,
    )


def diff_condition_versions(
    condition: Condition, left_version: str, right_version: str
) -> Dict[str, Any]:
    try:
        left = int(str(left_version).replace("v", ""))
        right = int(str(right_version).replace("v", ""))
    except ValueError as exc:
        raise ConditionManagementError("Invalid version id") from exc

    left_entry = ConditionVersion.objects(
        condition_uuid=condition.uuid, version=left
    ).first()
    right_entry = ConditionVersion.objects(
        condition_uuid=condition.uuid, version=right
    ).first()
    if not left_entry or not right_entry:
        raise ConditionManagementError("Version not found")
    return {
        "condition_uuid": condition.uuid,
        "from_version": left_version,
        "to_version": right_version,
        "diff": _diff_dict(left_entry.snapshot, right_entry.snapshot),
    }


def export_conditions() -> List[Dict[str, Any]]:
    return [_serialize_condition(c) for c in Condition.objects]


def import_conditions(
    items: List[Dict[str, Any]], overwrite: bool = False
) -> Dict[str, Any]:
    created = 0
    updated = 0
    skipped = 0
    errors: List[Dict[str, Any]] = []
    for raw in items:
        try:
            condition_uuid = raw["uuid"]
            existing = Condition.objects(uuid=condition_uuid).first()
            if existing and not overwrite:
                skipped += 1
                continue
            target = existing or Condition(uuid=condition_uuid)
            for field in (
                "conditionType",
                "expression",
                "targetField",
                "sourceSectionUuid",
                "operator",
                "operands",
                "isNegated",
                "logicalJoinType",
                "isActive",
                "errorMessage",
                "description",
                "priority",
                "stopEvaluationIfTrue",
                "metadata",
                "status",
            ):
                if field in raw:
                    setattr(target, field, raw[field])
            if "subConditions" in raw:
                refs = []
                for sub_uuid in raw["subConditions"] or []:
                    sub_condition = Condition.objects(uuid=sub_uuid).first()
                    if sub_condition:
                        refs.append(sub_condition)
                target.subConditions = refs
            target.save()
            if existing:
                updated += 1
            else:
                created += 1
        except Exception as exc:
            errors.append({"uuid": raw.get("uuid"), "error": str(exc)})
    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
    }


def analyze_condition_impact(
    condition: Condition,
    new_condition_params: Optional[Dict[str, Any]] = None,
    sample_size: int = 100,
) -> Dict[str, Any]:
    contexts: List[Dict[str, Any]] = []
    for response in FormResponse.objects.order_by("-created_at")[: max(1, sample_size)]:
        contexts.append(
            ConditionEvaluationContext.merged(
                form_response={
                    "status": response.status,
                    "metadata": response.metadata or {},
                    "responses": response.response_map or {},
                }
            )
        )
    if not contexts:
        contexts = [{"status": "draft", "score": 0, "value": None}]

    current = impact_analysis(condition.uuid, sample_contexts=contexts)
    projected = None
    if new_condition_params:
        projected_condition = copy.copy(condition)
        for key, value in new_condition_params.items():
            setattr(projected_condition, key, value)
        evaluator = ConditionEvaluator(enable_tracing=False)
        projected_hits = 0
        for ctx in contexts:
            evaluator.context = ctx
            if evaluator.evaluate(projected_condition):
                projected_hits += 1
        projected = projected_hits / len(contexts)

    return {
        "condition_uuid": condition.uuid,
        "current_match_count": current["current_match_count"],
        "current_match_rate": current["current_match_rate"],
        "projected_match_count": int(projected * len(contexts))
        if projected is not None
        else None,
        "projected_match_rate": projected,
        "affected_actions": current["affected_conditions"],
        "affected_questions": current.get("questions", []),
        "sample_size": current["sample_size"],
        "analysis_time_ms": current["analysis_time_ms"],
    }


def evaluate_condition_async(
    condition: Condition,
    context: Dict[str, Any],
    timeout_seconds: float = 2.0,
) -> Dict[str, Any]:
    timeout_ms = max(1, int(timeout_seconds * 1000))
    job = enqueue_async_evaluation(
        condition.uuid,
        context,
        timeout_ms=timeout_ms,
        retries=0,
        fallback_result=False,
    )
    deadline = datetime.utcnow() + timedelta(milliseconds=timeout_ms)
    while datetime.utcnow() < deadline:
        payload = get_async_job_status(job.job_id)
        if payload["status"] in {"success", "failed", "timeout"}:
            return {
                "job_id": payload["job_id"],
                "status": payload["status"],
                "result": payload["result"],
                "trace": payload["trace"],
                "timed_out": payload["status"] == "timeout",
                "error": payload["error"],
            }
        time.sleep(0.02)
    return {
        "job_id": job.job_id,
        "status": "timeout",
        "result": None,
        "trace": [],
        "timed_out": True,
        "error": f"Evaluation timed out after {timeout_seconds}s",
    }


def monitoring_dashboard_snapshot() -> Dict[str, Any]:
    snapshot = get_monitoring_snapshot()
    graph = build_dependency_graph()
    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "total_conditions": Condition.objects.count(),
        "active_conditions": Condition.objects(isActive=True).count(),
        "circular_references": detect_circular_references(graph),
        "dependency_graph": graph,
        "monitoring": snapshot,
    }
