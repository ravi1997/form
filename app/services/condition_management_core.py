from __future__ import annotations

from typing import Any, Dict

from app.models.form import Condition

APPROVAL_TRANSITIONS = {
    "draft": {"review", "archived"},
    "review": {"published", "draft", "archived"},
    "published": {"deprecated", "archived"},
    "deprecated": {"published", "archived"},
    "archived": set(),
}


class ConditionManagementError(ValueError):
    pass


def serialize_condition(condition: Condition) -> Dict[str, Any]:
    return {
        "uuid": condition.uuid,
        "conditionType": condition.conditionType,
        "expression": condition.expression,
        "targetField": condition.targetField,
        "sourceSectionUuid": condition.sourceSectionUuid,
        "operator": condition.operator,
        "operands": list(condition.operands or []),
        "isNegated": bool(condition.isNegated),
        "subConditions": [str(getattr(c, "id", c)) for c in (condition.subConditions or [])],
        "logicalJoinType": condition.logicalJoinType,
        "isActive": bool(condition.isActive),
        "errorMessage": condition.errorMessage,
        "description": condition.description,
        "priority": int(condition.priority or 0),
        "stopEvaluationIfTrue": bool(condition.stopEvaluationIfTrue),
        "metadata": dict(condition.metadata or {}),
        "status": condition.status,
        "updated_at": condition.updated_at.isoformat() if condition.updated_at else None,
    }


def diff_dict(old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    diff: Dict[str, Any] = {}
    keys = set(old.keys()).union(new.keys())
    for key in keys:
        if old.get(key) != new.get(key):
            diff[key] = {"from": old.get(key), "to": new.get(key)}
    return diff
