from __future__ import annotations

import csv
import io
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.models.form import Form, FormResponse, Question, ResponseAuditLog
from app.models.user import User
from app.services.condition_evaluator import ConditionEvaluator


def get_response_analytics(form_uuid: str) -> Dict[str, Any]:
    """Calculate summary statistics and answer frequency aggregates for form responses."""
    responses = FormResponse.objects(form_uuid=form_uuid, status__ne="deleted")
    total_count = responses.count()
    if total_count == 0:
        return {
            "total_responses": 0,
            "status_distribution": {},
            "average_score": 0.0,
            "question_aggregates": {},
        }

    status_distribution: Dict[str, int] = {}
    total_score = 0.0
    scored_responses = 0

    # Aggregate answer frequencies for choice/select questions
    # Format: {question_uuid: {choice_value: count}}
    question_aggregates: Dict[str, Dict[str, int]] = {}

    for resp in responses:
        status_distribution[resp.status] = status_distribution.get(resp.status, 0) + 1
        if resp.score is not None:
            total_score += resp.score
            scored_responses += 1

        for item in resp.responses:
            q_uuid = item.question_uuid
            val = str(item.value) if item.value is not None else ""
            if val:
                if q_uuid not in question_aggregates:
                    question_aggregates[q_uuid] = {}
                question_aggregates[q_uuid][val] = (
                    question_aggregates[q_uuid].get(val, 0) + 1
                )

    return {
        "total_responses": total_count,
        "status_distribution": status_distribution,
        "average_score": (total_score / scored_responses)
        if scored_responses > 0
        else 0.0,
        "question_aggregates": question_aggregates,
    }


def export_responses_to_csv(form_uuid: str) -> str:
    """Generate a CSV string of all form responses for export."""
    responses = FormResponse.objects(form_uuid=form_uuid, status__ne="deleted")
    if not responses:
        return ""

    # Gather all unique question UUIDs across all responses to use as header columns
    question_uuids = set()
    for resp in responses:
        for item in resp.responses:
            if item.question_uuid:
                question_uuids.add(item.question_uuid)
    headers = sorted(list(question_uuids))

    output = io.StringIO()
    writer = csv.writer(output)

    # Header Row
    writer.writerow(
        ["response_uuid", "status", "submitted_by", "submitted_at", "score"] + headers
    )

    for resp in responses:
        # Map values by question_uuid
        values_map = {item.question_uuid: item.value for item in resp.responses}
        row = [
            resp.uuid,
            resp.status,
            resp.submitted_by_uuid or "anonymous",
            resp.submitted_at.isoformat() if resp.submitted_at else "",
            resp.score if resp.score is not None else "",
        ]
        for q_uuid in headers:
            row.append(str(values_map.get(q_uuid, "")))
        writer.writerow(row)

    return output.getvalue()


def check_field_level_permission(
    user: Optional[User], question_uuid: str, action_type: str = "write"
) -> bool:
    """Check if the user is authorized to edit/read a specific question based on its metadata allowed_roles."""
    question = Question.objects(uuid=question_uuid).first()
    if not question:
        return True

    metadata = dict(question.metadata or {})
    allowed_roles: List[str] = metadata.get("allowed_roles", [])
    if not allowed_roles:
        return True  # No constraints defined, anyone can access

    if not user:
        return False  # Anonymous access restricted

    if user.is_super_admin:
        return True

    # User roles map is usually structured as: user.roles[org_id] = [role1, role2]
    user_roles_set = set()
    for roles_list in (user.roles or {}).values():
        for r in roles_list:
            user_roles_set.add(r)

    # Check if user has any of the allowed roles
    return any(role in user_roles_set for role in allowed_roles)


def validate_response_conditions(
    form: Form, responses_list: List[Any], response_map: Dict[str, Any]
) -> List[str]:
    """Validate submitted values against the form's custom validation rules/conditions on the backend."""
    errors: List[str] = []

    # Resolve all questions in the form versions to evaluate validation conditions
    # Create an in-memory evaluator mapping the submitted inputs
    evaluator = ConditionEvaluator(context=response_map)

    # Basic backend constraint validation
    for item in responses_list:
        question = Question.objects(uuid=item.question_uuid).first()
        if not question:
            continue

        # Check conditions
        for cond_ref in question.validation_conditions or []:
            from app.models.form import Condition

            condition = Condition.objects(uuid=str(cond_ref)).first()
            if condition:
                try:
                    is_valid = evaluator.evaluate(condition)
                    if not is_valid:
                        msg = (
                            question.validation_condition_messages.get(str(cond_ref))
                            or f"Validation failed for question {question.uuid}"
                        )
                        errors.append(msg)
                except Exception as exc:
                    errors.append(f"Condition evaluation error: {str(exc)}")

    return errors


def write_response_audit_log(
    response_uuid: str,
    actor_user_uuid: Optional[str],
    action: str,
    changes: Dict[str, Any],
) -> ResponseAuditLog:
    """Create a detailed audit trace log entry for a FormResponse operation."""
    audit = ResponseAuditLog(
        uuid=str(uuid4()),
        response_uuid=response_uuid,
        actor_user_uuid=actor_user_uuid,
        action=action,
        changes=changes,
    )
    audit.save()
    return audit


def trigger_async_actions(response_id: str, event_type: str) -> None:
    """Trigger celery asynchronous tasks/actions (e.g. webhooks, notifications) when response events occur."""
    from app.celery.tasks import trigger_response_webhook_task

    trigger_response_webhook_task.apply_async(args=[response_id, event_type])
