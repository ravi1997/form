from __future__ import annotations

import copy
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.models.form import Condition, FormResponse, Question
from app.services.condition_evaluator import (
    ConditionEvaluationContext,
    ConditionEvaluator,
)
from app.services.condition_management_core import ConditionManagementError


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
    start = datetime.now(timezone.utc)
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
        "analysis_time_ms": (datetime.now(timezone.utc) - start).total_seconds() * 1000,
    }


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
