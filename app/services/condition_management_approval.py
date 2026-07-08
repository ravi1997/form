from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from app.models.condition_management import (
    APPROVAL_STATE_CHOICES,
    ConditionApprovalAudit,
)
from app.models.form import Condition
from app.services.condition_management_core import (
    APPROVAL_TRANSITIONS,
    ConditionManagementError,
)


def ensure_publishable(condition: Condition) -> List[str]:
    errors: List[str] = []
    if not condition.isActive:
        errors.append("Condition must be active before publishing")
    if condition.conditionType in {"comparison", "temporal", "set"} and not condition.operator:
        errors.append("Operator is required")
    if condition.conditionType in {"comparison", "temporal", "set"} and not condition.targetField:
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
