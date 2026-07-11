from __future__ import annotations

import base64
import binascii
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from flask import current_app, g, request

from app.api.resources_schemas import ActionExecutionOutput, ErrorResponse, ListQuery
from app.models.form import (
    ActionDefinition,
    ActionExecution,
    ActionStep,
    Condition,
    Form,
    FormWorkflowEvent,
    Project,
    Question,
)
from app.models.user import User
from app.schemas.mappers import to_json_ready
from app.services import get_rotating_logger
from app.services.rate_limit import get_rate_limit_service
from app.utils import client_ip

logger = get_rotating_logger()

PROJECT_UUID_ENDPOINTS = {
    "resources.get_project",
    "resources.update_project",
    "resources.delete_project",
    "resources.create_project_version",
    "resources.update_project_version",
}

ENDPOINT_PERMISSION = {
    "resources.create_organization": "global_admin",
    "resources.list_organizations": "authenticated",
    "resources.get_organization": "global_admin",
    "resources.update_organization": "global_admin",
    "resources.delete_organization": "global_admin",
    "resources.get_organization_admins": "global_admin",
    "resources.add_organization_admin": "global_admin",
    "resources.remove_organization_admin": "global_admin",
    "resources.create_organization_invitation": "authenticated",
    "resources.accept_organization_invitation": "authenticated",
    "resources.create_project": "authenticated",
    "resources.list_projects": "authenticated",
    "resources.get_project": "project_read",
    "resources.update_project": "project_admin",
    "resources.delete_project": "project_admin",
    "resources.create_project_version": "project_admin",
    "resources.update_project_version": "project_admin",
    "resources.create_form": "project_write",
    "resources.list_forms": "project_read",
    "resources.get_form": "project_read",
    "resources.update_form": "project_write",
    "resources.delete_form": "project_admin",
    "resources.create_form_version": "project_write",
    "resources.update_form_version": "project_write",
    "resources.submit_form_response": "project_submit",
    "resources.submit_public_form_response": "anonymous",
    "resources.create_section": "project_write",
    "resources.list_sections": "project_read",
    "resources.get_section": "project_read",
    "resources.update_section": "project_write",
    "resources.delete_section": "project_admin",
    "resources.create_section_version": "project_write",
    "resources.update_section_version": "project_write",
    "resources.create_question": "project_write",
    "resources.list_questions": "project_read",
    "resources.get_question": "project_read",
    "resources.update_question": "project_write",
    "resources.delete_question": "project_admin",
    "resources.create_question_version": "project_write",
    "resources.update_question_version": "project_write",
    "resources.create_choice": "project_write",
    "resources.list_choices": "project_read",
    "resources.get_choice": "project_read",
    "resources.update_choice": "project_write",
    "resources.delete_choice": "project_admin",
    "resources.submit_form_workflow": "project_submit",
    "resources.review_form_workflow": "project_review",
    "resources.approve_form_workflow": "project_approve",
}

def security_event(
    *,
    event: str,
    outcome: str,
    reason: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    actor = getattr(g, "resources_user", None)
    actor_user_uuid = str(getattr(actor, "uuid", "")) or None

    payload = {
        "event": event,
        "outcome": outcome,
        "endpoint": request.endpoint,
        "path": request.path,
        "method": request.method,
        "ip": client_ip(),
        "actor_user_uuid": actor_user_uuid,
        "reason": reason,
        "details": details or {},
        "request_id": getattr(g, "request_id", None),
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
    }
    logger.log_app_event("resources_security_event", context=payload)


def resources_rate_limit() -> Optional[tuple]:
    service = get_rate_limit_service()
    allowed, metadata = service.check_rate_limit(
        route_pattern="/api/v1/resources",
        http_method=request.method,
        user_uuid=getattr(g, "user_id", None),
        organization_uuid=getattr(g, "organization_id", None),
        identifier=client_ip(),
    )
    if allowed:
        return None

    retry_after = max(
        0,
        int(
            (metadata.get("reset_time", 0) or 0)
            - datetime.now(timezone.utc).timestamp()
        ),
    )
    security_event(
        event="resources_rate_limit",
        outcome="throttled",
        reason="rate_limit_exceeded",
        details={"rule_id": metadata.get("rule_id"), "retry_after": retry_after},
    )
    payload = to_json_ready(
        ErrorResponse(message="Too many resource API requests. Please try again later.")
    )
    return payload, 429, {"Retry-After": str(retry_after)}


def encode_cursor(dt: datetime) -> str:
    return base64.urlsafe_b64encode(dt.isoformat().encode("utf-8")).decode("utf-8")


def decode_cursor(cursor: str) -> datetime:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        return datetime.fromisoformat(raw)
    except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
        raise ValueError("Invalid cursor") from exc


def encode_index_cursor(index: int) -> str:
    return base64.urlsafe_b64encode(str(index).encode("utf-8")).decode("utf-8")


def decode_index_cursor(cursor: str) -> int:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        index = int(raw)
    except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
        raise ValueError("Invalid cursor") from exc
    if index < 0:
        raise ValueError("Invalid cursor")
    return index


def _project_org_scope_keys(project: Project) -> set[str]:
    keys: set[str] = set()
    for org in project.organizations or []:
        org_id = getattr(org, "id", None)
        if org_id is not None:
            keys.add(str(org_id))
        org_uuid = getattr(org, "uuid", None)
        if org_uuid:
            keys.add(str(org_uuid))
    return keys


def _project_user_uuids(project: Project, attr: str) -> set[str]:
    values = getattr(project, attr, None) or []
    uuids: set[str] = set()
    for value in values:
        uuid = getattr(value, "uuid", None)
        if uuid:
            uuids.add(str(uuid))
    return uuids


def _project_role_set(user: User, project: Project) -> set[str]:
    roles: set[str] = set()
    project_org_keys = _project_org_scope_keys(project)
    for org_key, org_roles in (user.roles or {}).items():
        if str(org_key) in project_org_keys:
            roles.update(org_roles or [])
    return roles


def _can_read_project(user: User, project: Project, has_global_admin) -> bool:
    if has_global_admin(user):
        return True
    user_uuid = str(user.uuid)
    if user_uuid in _project_user_uuids(project, "admins"):
        return True
    if user_uuid in _project_user_uuids(project, "members"):
        return True
    if user_uuid in _project_user_uuids(project, "viewers"):
        return True
    role_set = _project_role_set(user, project)
    return bool(
        {"admin", "editor", "viewer", "reviewer", "approver", "submitter"} & role_set
    )


def _can_write_project(user: User, project: Project, has_global_admin) -> bool:
    if has_global_admin(user):
        return True
    user_uuid = str(user.uuid)
    if user_uuid in _project_user_uuids(project, "admins"):
        return True
    if user_uuid in _project_user_uuids(project, "members"):
        return True
    role_set = _project_role_set(user, project)
    return bool({"admin", "editor"} & role_set)


def _can_admin_project(user: User, project: Project, has_global_admin) -> bool:
    if has_global_admin(user):
        return True
    user_uuid = str(user.uuid)
    if user_uuid in _project_user_uuids(project, "admins"):
        return True
    role_set = _project_role_set(user, project)
    return "admin" in role_set


def _can_submit_project(user: User, project: Project, has_global_admin) -> bool:
    if _can_write_project(user, project, has_global_admin):
        return True
    role_set = _project_role_set(user, project)
    return "submitter" in role_set


def _can_review_project(user: User, project: Project, has_global_admin) -> bool:
    if _can_write_project(user, project, has_global_admin):
        return True
    role_set = _project_role_set(user, project)
    return "reviewer" in role_set


def _can_approve_project(user: User, project: Project, has_global_admin) -> bool:
    if _can_admin_project(user, project, has_global_admin):
        return True
    role_set = _project_role_set(user, project)
    return "approver" in role_set


def validate_project_membership_role_alignment(project: Project) -> None:
    if not bool(
        current_app.config.get(
            "RESOURCE_RBAC_REQUIRE_ORG_ROLE_ALIGNMENT",
            True,
        )
    ):
        return

    org_keys = _project_org_scope_keys(project)
    if not org_keys:
        if project.admins or project.members or project.viewers:
            raise ValueError(
                "Project organizations are required when membership lists are set"
            )
        return

    rules = {
        "admins": {"admin", "editor"},
        "members": {"admin", "editor"},
        "viewers": {"admin", "editor", "viewer"},
    }

    for attr, required_roles in rules.items():
        for user in getattr(project, attr, None) or []:
            matched = False
            for org_key, roles in (user.roles or {}).items():
                if str(org_key) in org_keys and required_roles.intersection(
                    set(roles or [])
                ):
                    matched = True
                    break
            if not matched:
                raise ValueError(
                    f"User {getattr(user, 'uuid', '<unknown>')} in {attr} is not aligned with project organization roles"
                )


def paginate_items(items: list[Any], query: ListQuery, sort_field: str = "updated_at"):
    ordered = sorted(
        items, key=lambda item: getattr(item, sort_field, datetime.min), reverse=True
    )

    if query.cursor:
        cursor_dt = decode_cursor(query.cursor)
        filtered = [
            item
            for item in ordered
            if getattr(item, sort_field, datetime.min) < cursor_dt
        ]
        selected = filtered[: query.page_size]
        next_cursor = (
            encode_cursor(getattr(selected[-1], sort_field, datetime.min))
            if len(selected) == query.page_size
            else None
        )
        return selected, query.page, query.page_size, None, None, next_cursor

    if query.offset is not None or query.limit is not None:
        limit = query.limit or 50
        offset = query.offset or 0
        selected = ordered[offset : offset + limit]
        page = (offset // max(limit, 1)) + 1
        page_size = limit
        total_items = len(ordered)
        total_pages = (total_items + page_size - 1) // page_size if total_items else 0
        return selected, page, page_size, total_items, total_pages, None

    page = max(query.page, 1)
    page_size = max(query.page_size, 1)
    start = (page - 1) * page_size
    selected = ordered[start : start + page_size]
    total_items = len(ordered)
    total_pages = (total_items + page_size - 1) // page_size if total_items else 0
    next_cursor = (
        encode_cursor(getattr(selected[-1], sort_field, datetime.min))
        if len(selected) == page_size
        else None
    )
    return selected, page, page_size, total_items, total_pages, next_cursor


def paginate_queryset(qs: Any, query: ListQuery, sort_field: str = "updated_at"):
    ordered = qs.order_by(f"-{sort_field}")

    if query.cursor:
        cursor_dt = decode_cursor(query.cursor)
        filtered = ordered.filter(**{f"{sort_field}__lt": cursor_dt})
        selected = list(filtered.limit(query.page_size))
        next_cursor = (
            encode_cursor(getattr(selected[-1], sort_field, datetime.min))
            if len(selected) == query.page_size
            else None
        )
        return selected, query.page, query.page_size, None, None, next_cursor

    if query.offset is not None or query.limit is not None:
        limit = query.limit or 50
        offset = query.offset or 0
        selected = list(ordered.skip(offset).limit(limit))
        page = (offset // max(limit, 1)) + 1
        page_size = limit
        total_items = ordered.count()
        total_pages = (total_items + page_size - 1) // page_size if total_items else 0
        return selected, page, page_size, total_items, total_pages, None

    page = max(query.page, 1)
    page_size = max(query.page_size, 1)
    skip = (page - 1) * page_size
    selected = list(ordered.skip(skip).limit(page_size))
    total_items = ordered.count()
    total_pages = (total_items + page_size - 1) // page_size if total_items else 0
    next_cursor = (
        encode_cursor(getattr(selected[-1], sort_field, datetime.min))
        if len(selected) == page_size
        else None
    )
    return selected, page, page_size, total_items, total_pages, next_cursor


def paginate_queryset_with_predicate(
    qs: Any,
    query: ListQuery,
    predicate,
    sort_field: str = "updated_at",
):
    """Paginate an ordered queryset while applying an in-Python filter lazily."""

    ordered = qs.order_by(f"-{sort_field}")

    def _visible_items():
        for item in ordered:
            if predicate(item):
                yield item

    if query.cursor:
        cursor_dt = decode_cursor(query.cursor)
        selected = []
        for item in _visible_items():
            if getattr(item, sort_field, datetime.min) >= cursor_dt:
                continue
            selected.append(item)
            if len(selected) == query.page_size:
                break
        next_cursor = (
            encode_cursor(getattr(selected[-1], sort_field, datetime.min))
            if len(selected) == query.page_size
            else None
        )
        return selected, query.page, query.page_size, None, None, next_cursor

    if query.offset is not None or query.limit is not None:
        limit = query.limit or 50
        offset = query.offset or 0
        visible = list(_visible_items())
        selected = visible[offset : offset + limit]
        page = (offset // max(limit, 1)) + 1
        page_size = limit
        total_items = len(visible)
        total_pages = (total_items + page_size - 1) // page_size if total_items else 0
        return selected, page, page_size, total_items, total_pages, None

    page = max(query.page, 1)
    page_size = max(query.page_size, 1)
    start = (page - 1) * page_size
    visible = list(_visible_items())
    selected = visible[start : start + page_size]
    total_items = len(visible)
    total_pages = (total_items + page_size - 1) // page_size if total_items else 0
    next_cursor = (
        encode_cursor(getattr(selected[-1], sort_field, datetime.min))
        if len(selected) == page_size
        else None
    )
    return selected, page, page_size, total_items, total_pages, next_cursor


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def build_action_definitions(action_inputs: list[Any]) -> list[ActionDefinition]:
    actions: list[ActionDefinition] = []
    for action in action_inputs:
        steps = [
            ActionStep(
                id=step.id,
                target=step.target,
                type=step.type,
                config=step.config or {},
                on_error=step.on_error,
            )
            for step in (action.steps or [])
        ]
        actions.append(
            ActionDefinition(
                id=action.id,
                label=action.label,
                icon=action.icon,
                button_variant=action.button_variant,
                trigger=action.trigger,
                confirmation_message=action.confirmation_message,
                schema_version=action.schema_version,
                audit_policy=action.audit_policy,
                allowed_roles=action.allowed_roles or [],
                visibility_condition=(
                    Condition.objects(uuid=action.visibility_condition).first()
                    if action.visibility_condition
                    else None
                ),
                enabled_condition=(
                    Condition.objects(uuid=action.enabled_condition).first()
                    if action.enabled_condition
                    else None
                ),
                metadata=action.metadata or {},
                steps=steps,
            )
        )
    return actions


def resolve_action_definition(
    question: Question, action_id: str
) -> Optional[ActionDefinition]:
    for action in question.actions or []:
        if action.id == action_id:
            return action
    return None


def to_action_execution_output(execution: ActionExecution) -> ActionExecutionOutput:
    return ActionExecutionOutput(
        uuid=execution.uuid,
        project_uuid=execution.project_uuid,
        form_uuid=execution.form_uuid,
        section_uuid=execution.section_uuid,
        question_uuid=execution.question_uuid,
        action_id=execution.action_id,
        response_uuid=execution.response_uuid,
        actor_user_uuid=execution.actor_user_uuid,
        idempotency_key=execution.idempotency_key,
        status=execution.status,
        frontend_steps=execution.frontend_steps or [],
        step_results=execution.step_results or [],
        request_context=execution.request_context or {},
        client_state=execution.client_state or {},
        output=execution.output or {},
        error=execution.error,
        created_at=execution.created_at,
        updated_at=execution.updated_at,
        completed_at=execution.completed_at,
        request_id=execution.request_id,
    )


def apply_form_workflow_action(
    form: Form, action: str, actor_user_uuid: str, note: Optional[str]
) -> str:
    strict_review = bool(
        current_app.config.get("WORKFLOW_STRICT_REVIEW_BEFORE_APPROVE", True)
    )
    current_state = (form.workflow_state or "draft").strip()
    target_state = current_state
    outcome = "success"
    message = f"{action}_accepted"

    if action == "submit":
        if current_state in {"submitted", "in_review", "approved"}:
            outcome = "idempotent"
            message = "submit_already_processed"
        elif current_state in {"draft", "rejected"}:
            target_state = "submitted"
        else:
            outcome = "rejected"
            message = "submit_invalid_state"

    if action == "review":
        if not form.requires_reviewer:
            outcome = "rejected"
            message = "reviewer_workflow_not_enabled"
        elif current_state == "in_review":
            outcome = "idempotent"
            message = "review_already_processed"
        elif current_state == "approved":
            outcome = "idempotent"
            message = "review_already_processed"
        elif current_state == "submitted" or (
            not strict_review and current_state in {"draft", "rejected"}
        ):
            target_state = "in_review"
        else:
            outcome = "rejected"
            message = "review_invalid_state"

    if action == "approve":
        if not form.requires_approver:
            outcome = "rejected"
            message = "approver_workflow_not_enabled"
        elif current_state == "approved":
            outcome = "idempotent"
            message = "approve_already_processed"
        elif strict_review and form.requires_reviewer and current_state != "in_review":
            outcome = "rejected"
            message = "approve_requires_review"
        elif current_state in {"submitted", "in_review"} or (
            not strict_review and current_state in {"draft", "rejected"}
        ):
            target_state = "approved"
        else:
            outcome = "rejected"
            message = "approve_invalid_state"

    event = FormWorkflowEvent(
        action=action,
        actor_user_uuid=actor_user_uuid,
        note=note,
        transition_from=current_state,
        transition_to=target_state,
        outcome=outcome,
        request_id=getattr(g, "request_id", None),
    )
    form.workflow_history = list(form.workflow_history or [])
    form.workflow_history.append(event)
    if outcome == "success":
        form.workflow_state = target_state
    form.save()
    if outcome == "rejected":
        raise ValueError(message)
    return message


def extract_project_uuid_from_request() -> Optional[str]:
    view_args = request.view_args or {}
    if "project_uuid" in view_args:
        return str(view_args["project_uuid"])
    if request.endpoint in PROJECT_UUID_ENDPOINTS and "uuid" in view_args:
        return str(view_args["uuid"])
    return None


def authorize_resources_route(has_global_admin_privileges) -> Optional[tuple]:
    required = ENDPOINT_PERMISSION.get(request.endpoint, "authenticated")
    if required == "anonymous":
        return None

    payload = getattr(g, "resources_user_payload", None)
    user = getattr(g, "resources_user", None)
    if payload is None or user is None:
        return to_json_ready(ErrorResponse(message="Unauthorized")), 401

    if required == "authenticated":
        return None

    if required == "global_admin":
        if has_global_admin_privileges(user):
            return None
        security_event(
            event="resources_rbac",
            outcome="forbidden",
            reason="global_admin_required",
            details={"required": required},
        )
        return to_json_ready(ErrorResponse(message="Admin privileges required")), 403

    project_uuid = extract_project_uuid_from_request()
    if not project_uuid:
        return to_json_ready(ErrorResponse(message="Project context required")), 400

    project = Project.objects(uuid=project_uuid).first()
    if not project:
        return to_json_ready(ErrorResponse(message="Project not found")), 404
    g.resources_project = project

    if required == "project_read" and _can_read_project(
        user, project, has_global_admin_privileges
    ):
        return None
    if required == "project_write" and _can_write_project(
        user, project, has_global_admin_privileges
    ):
        return None
    if required == "project_admin" and _can_admin_project(
        user, project, has_global_admin_privileges
    ):
        return None
    if required == "project_submit" and _can_submit_project(
        user, project, has_global_admin_privileges
    ):
        return None
    if required == "project_review" and _can_review_project(
        user, project, has_global_admin_privileges
    ):
        return None
    if required == "project_approve" and _can_approve_project(
        user, project, has_global_admin_privileges
    ):
        return None

    security_event(
        event="resources_rbac",
        outcome="forbidden",
        reason="rbac_denied",
        details={"required": required, "project_uuid": project_uuid},
    )
    return to_json_ready(ErrorResponse(message="Forbidden")), 403


def before_resources_request_logging() -> None:
    g.resources_request_started_at = time.perf_counter()
    g.resources_request_id = getattr(g, "request_id", None)
    logger.log_app_event(
        "API Started",
        context={
            "route": f"{request.method} {request.path}",
            "endpoint": request.endpoint,
            "request_id": g.resources_request_id,
            "user_id": getattr(g, "user_id", None),
        },
    )


def after_resources_request_logging(response):
    started_at = getattr(g, "resources_request_started_at", None)
    duration_ms = None
    if started_at is not None:
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)

    logger.log_app_event(
        "resources_api_request",
        context={
            "method": request.method,
            "path": request.path,
            "status": response.status_code,
            "ip": client_ip(),
            "duration_ms": duration_ms,
            "request_id": getattr(g, "resources_request_id", None),
        },
    )
    return response
