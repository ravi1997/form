from __future__ import annotations

import base64
from datetime import datetime
import logging
import time
from typing import Any, Dict, List, Literal, Optional, Type

from flask import current_app, g, request
from mongoengine.errors import NotUniqueError, ValidationError

from app.models.form import Choice, Form, FormWorkflowEvent, Project, Question, Section, Version
from app.models.form import Condition
from app.models.user import Organization, User
from app.schemas.common import SchemaModel
from app.schemas.choice import ChoiceCreateInput, ChoiceOutput, ChoiceUpdateInput
from app.schemas.form import FormCreateInput, FormOutput, FormUpdateInput
from app.schemas.mappers import (
    to_choice_output,
    to_form_output,
    to_json_ready,
    to_project_output,
    to_question_output,
    to_section_output,
    to_version_output,
)
from app.schemas.project import ProjectCreateInput, ProjectOutput, ProjectUpdateInput
from app.schemas.question import QuestionCreateInput, QuestionOutput, QuestionUpdateInput
from app.schemas.section import SectionCreateInput, SectionOutput, SectionUpdateInput
from app.schemas.version import VersionCreateInput, VersionOutput, VersionUpdateInput
from app.services.auth import AuthError
from app.services.rbac import (
    get_user_by_uuid,
    has_global_admin_privileges,
    resolve_access_identity_from_header,
)
from app.services.security import check_and_increment_rate_limit

try:
    from flask_openapi3 import APIBlueprint, Tag
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "flask-openapi3 is required for OpenAPI integration. Install with: pip install flask-openapi3"
    ) from exc


resources_tag = Tag(name="Resources", description="Project/Form/Section/Question resource APIs")
version_tag = Tag(name="Versions", description="Version append/update APIs")
resources_api = APIBlueprint("resources", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)


class MessageResponse(SchemaModel):
    message: str


class ErrorResponse(SchemaModel):
    message: str


class UUIDPath(SchemaModel):
    uuid: str


class VersionPath(SchemaModel):
    uuid: str
    version_uuid: str


class ProjectPath(SchemaModel):
    project_uuid: str


class FormPath(SchemaModel):
    project_uuid: str
    form_uuid: str


class SectionPath(SchemaModel):
    project_uuid: str
    form_uuid: str
    section_uuid: str


class QuestionPath(SchemaModel):
    project_uuid: str
    form_uuid: str
    section_uuid: str
    question_uuid: str


class FormVersionPath(SchemaModel):
    project_uuid: str
    form_uuid: str
    version_uuid: str


class SectionVersionPath(SchemaModel):
    project_uuid: str
    form_uuid: str
    section_uuid: str
    version_uuid: str


class QuestionVersionPath(SchemaModel):
    project_uuid: str
    form_uuid: str
    section_uuid: str
    question_uuid: str
    version_uuid: str


class ChoicePath(SchemaModel):
    project_uuid: str
    form_uuid: str
    section_uuid: str
    question_uuid: str
    choice_uuid: str


class VersionLinkQuery(SchemaModel):
    version_uuid: Optional[str] = None


class ListQuery(SchemaModel):
    status: Optional[str] = None
    cursor: Optional[str] = None
    page: int = 1
    page_size: int = 20
    limit: Optional[int] = None
    offset: Optional[int] = None


class ProjectListResponse(SchemaModel):
    items: List[ProjectOutput]
    page: int
    page_size: int
    total_items: Optional[int] = None
    total_pages: Optional[int] = None
    next_cursor: Optional[str] = None


class FormListResponse(SchemaModel):
    items: List[FormOutput]
    page: int
    page_size: int
    total_items: Optional[int] = None
    total_pages: Optional[int] = None
    next_cursor: Optional[str] = None


class SectionListResponse(SchemaModel):
    items: List[SectionOutput]
    page: int
    page_size: int
    total_items: Optional[int] = None
    total_pages: Optional[int] = None
    next_cursor: Optional[str] = None


class QuestionListResponse(SchemaModel):
    items: List[QuestionOutput]
    page: int
    page_size: int
    total_items: Optional[int] = None
    total_pages: Optional[int] = None
    next_cursor: Optional[str] = None


class ChoiceListResponse(SchemaModel):
    items: List[ChoiceOutput]
    page: int
    page_size: int
    total_items: int
    total_pages: int
    next_cursor: Optional[str] = None


class WorkflowActionRequest(SchemaModel):
    note: Optional[str] = None


class WorkflowActionResponse(SchemaModel):
    message: str
    action: Literal["submit", "review", "approve"]
    actor_user_uuid: str
    form_uuid: str
    project_uuid: str


_PROJECT_UUID_ENDPOINTS = {
    "resources.get_project",
    "resources.update_project",
    "resources.delete_project",
    "resources.create_project_version",
    "resources.update_project_version",
}

_ENDPOINT_PERMISSION = {
    "resources.create_project": "global_admin",
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


def _client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _security_event(
    *,
    event: str,
    outcome: str,
    reason: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
):
    actor = getattr(g, "resources_user", None)
    actor_user_uuid = str(getattr(actor, "uuid", "")) or None

    payload = {
        "event": event,
        "outcome": outcome,
        "endpoint": request.endpoint,
        "path": request.path,
        "method": request.method,
        "ip": _client_ip(),
        "actor_user_uuid": actor_user_uuid,
        "reason": reason,
        "details": details or {},
        "request_id": getattr(g, "request_id", None),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    logger.info("resources_security_event=%s", payload)


def _resources_rate_limit() -> Optional[tuple]:
    max_requests = int(current_app.config.get("RESOURCE_RATE_LIMIT_MAX", 300))
    window_seconds = int(current_app.config.get("RESOURCE_RATE_LIMIT_WINDOW_SECONDS", 60))
    result = check_and_increment_rate_limit(
        scope="resources_api",
        key=f"ip:{_client_ip()}",
        max_requests=max_requests,
        window_seconds=window_seconds,
    )
    if bool(result.get("limited")):
        _security_event(
            event="resources_rate_limit",
            outcome="throttled",
            reason="rate_limit_exceeded",
            details={"retry_after": int(result["retry_after"])},
        )
        payload = to_json_ready(
            ErrorResponse(
                message="Too many resource API requests. Please try again later."
            )
        )
        return payload, 429, {"Retry-After": str(int(result["retry_after"]))}
    return None


def _encode_cursor(dt: datetime) -> str:
    return base64.urlsafe_b64encode(dt.isoformat().encode("utf-8")).decode("utf-8")


def _decode_cursor(cursor: str) -> datetime:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        return datetime.fromisoformat(raw)
    except Exception as exc:
        raise ValueError("Invalid cursor") from exc


def _encode_index_cursor(index: int) -> str:
    return base64.urlsafe_b64encode(str(index).encode("utf-8")).decode("utf-8")


def _decode_index_cursor(cursor: str) -> int:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        index = int(raw)
    except Exception as exc:
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


def _can_read_project(user: User, project: Project) -> bool:
    if has_global_admin_privileges(user):
        return True

    user_uuid = str(user.uuid)
    if user_uuid in _project_user_uuids(project, "admins"):
        return True
    if user_uuid in _project_user_uuids(project, "members"):
        return True
    if user_uuid in _project_user_uuids(project, "viewers"):
        return True

    role_set = _project_role_set(user, project)
    return bool({"admin", "editor", "viewer", "reviewer", "approver", "submitter"} & role_set)


def _can_write_project(user: User, project: Project) -> bool:
    if has_global_admin_privileges(user):
        return True

    user_uuid = str(user.uuid)
    if user_uuid in _project_user_uuids(project, "admins"):
        return True
    if user_uuid in _project_user_uuids(project, "members"):
        return True

    role_set = _project_role_set(user, project)
    return bool({"admin", "editor"} & role_set)


def _can_admin_project(user: User, project: Project) -> bool:
    if has_global_admin_privileges(user):
        return True

    user_uuid = str(user.uuid)
    if user_uuid in _project_user_uuids(project, "admins"):
        return True

    role_set = _project_role_set(user, project)
    return "admin" in role_set


def _can_submit_project(user: User, project: Project) -> bool:
    if _can_write_project(user, project):
        return True

    role_set = _project_role_set(user, project)
    return "submitter" in role_set


def _can_review_project(user: User, project: Project) -> bool:
    if _can_write_project(user, project):
        return True

    role_set = _project_role_set(user, project)
    return "reviewer" in role_set


def _can_approve_project(user: User, project: Project) -> bool:
    if _can_admin_project(user, project):
        return True

    role_set = _project_role_set(user, project)
    return "approver" in role_set


def _validate_project_membership_role_alignment(project: Project) -> None:
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
            raise ValueError("Project organizations are required when membership lists are set")
        return

    rules = {
        "admins": {"admin"},
        "members": {"admin", "editor"},
        "viewers": {"admin", "editor", "viewer"},
    }

    for attr, required_roles in rules.items():
        for user in getattr(project, attr, None) or []:
            matched = False
            for org_key, roles in (user.roles or {}).items():
                if str(org_key) in org_keys and required_roles.intersection(set(roles or [])):
                    matched = True
                    break
            if not matched:
                raise ValueError(
                    f"User {getattr(user, 'uuid', '<unknown>')} in {attr} is not aligned with project organization roles"
                )


def _paginate_items(items: List[Any], query: ListQuery, sort_field: str = "updated_at"):
    ordered = sorted(items, key=lambda item: getattr(item, sort_field, datetime.min), reverse=True)

    if query.cursor:
        cursor_dt = _decode_cursor(query.cursor)
        filtered = [item for item in ordered if getattr(item, sort_field, datetime.min) < cursor_dt]
        selected = filtered[: query.page_size]
        next_cursor = (
            _encode_cursor(getattr(selected[-1], sort_field, datetime.min))
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
        _encode_cursor(getattr(selected[-1], sort_field, datetime.min))
        if len(selected) == page_size
        else None
    )
    return selected, page, page_size, total_items, total_pages, next_cursor


def _apply_form_workflow_action(form: Form, action: str, actor_user_uuid: str, note: Optional[str]) -> str:
    strict_review = bool(
        current_app.config.get(
            "WORKFLOW_STRICT_REVIEW_BEFORE_APPROVE",
            True,
        )
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
        elif current_state == "submitted" or (not strict_review and current_state in {"draft", "rejected"}):
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
        elif current_state in {"submitted", "in_review"} or (not strict_review and current_state in {"draft", "rejected"}):
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


def _extract_project_uuid_from_request() -> Optional[str]:
    view_args = request.view_args or {}
    if "project_uuid" in view_args:
        return str(view_args["project_uuid"])

    if request.endpoint in _PROJECT_UUID_ENDPOINTS and "uuid" in view_args:
        return str(view_args["uuid"])

    return None


def _authorize_resources_route() -> Optional[tuple]:
    required = _ENDPOINT_PERMISSION.get(request.endpoint, "authenticated")
    payload = getattr(g, "resources_user_payload", None)
    user = getattr(g, "resources_user", None)
    if payload is None or user is None:
        return _error("Unauthorized", 401)

    if required == "authenticated":
        return None

    if required == "global_admin":
        if has_global_admin_privileges(user):
            return None
        _security_event(
            event="resources_rbac",
            outcome="forbidden",
            reason="global_admin_required",
            details={"required": required},
        )
        return _error("Admin privileges required", 403)

    project_uuid = _extract_project_uuid_from_request()
    if not project_uuid:
        return _error("Project context required", 400)

    project = Project.objects(uuid=project_uuid).first()
    if not project:
        return _error("Project not found", 404)
    g.resources_project = project

    if required == "project_read" and _can_read_project(user, project):
        return None
    if required == "project_write" and _can_write_project(user, project):
        return None
    if required == "project_admin" and _can_admin_project(user, project):
        return None
    if required == "project_submit" and _can_submit_project(user, project):
        return None
    if required == "project_review" and _can_review_project(user, project):
        return None
    if required == "project_approve" and _can_approve_project(user, project):
        return None

    _security_event(
        event="resources_rbac",
        outcome="forbidden",
        reason="rbac_denied",
        details={
            "required": required,
            "project_uuid": project_uuid,
        },
    )
    return _error("Forbidden", 403)


@resources_api.before_request
def _before_resources_request():
    g.resources_request_started_at = time.perf_counter()
    g.resources_request_id = getattr(g, "request_id", None)

    throttle = _resources_rate_limit()
    if throttle:
        logger.warning(
            "resources_api_throttled method=%s path=%s ip=%s request_id=%s",
            request.method,
            request.path,
            _client_ip(),
            g.resources_request_id,
        )
        return throttle

    try:
        raw_authorization = request.headers.get("Authorization", "")
        payload = resolve_access_identity_from_header(raw_authorization)
        user = get_user_by_uuid(payload["sub"])
        g.resources_user_payload = payload
        g.resources_user = user
    except AuthError as exc:
        _security_event(
            event="resources_auth",
            outcome="failed",
            reason=str(exc),
        )
        return _error(str(exc), 401)

    authz = _authorize_resources_route()
    if authz:
        return authz


@resources_api.after_request
def _after_resources_request(response):
    started_at = getattr(g, "resources_request_started_at", None)
    duration_ms = None
    if started_at is not None:
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)

    logger.info(
        "resources_api_request method=%s path=%s status=%s ip=%s duration_ms=%s request_id=%s",
        request.method,
        request.path,
        response.status_code,
        _client_ip(),
        duration_ms,
        getattr(g, "resources_request_id", None),
    )
    return response


def _error(message: str, status: int = 400):
    return to_json_ready(ErrorResponse(message=message)), status


def _resolve_refs(model: Type[Any], uuids: List[str], label: str) -> List[Any]:
    resolved = []
    for value in uuids or []:
        doc = model.objects(uuid=value).first()
        if not doc:
            raise ValueError(f"{label} uuid not found: {value}")
        resolved.append(doc)
    return resolved


def _resolve_user(user_uuid: Optional[str]) -> Optional[User]:
    if not user_uuid:
        return None
    return User.objects(uuid=user_uuid).first()


def _version_from_create(version: VersionCreateInput) -> Version:
    return Version(
        uuid=version.uuid,
        major=version.major,
        minor=version.minor,
        patch=version.patch,
        status=version.status,
        created=datetime.utcnow(),
        created_by=_resolve_user(version.created_by),
    )


def _apply_version_update(version: Version, body: VersionUpdateInput) -> None:
    if body.major is not None:
        version.major = body.major
    if body.minor is not None:
        version.minor = body.minor
    if body.patch is not None:
        version.patch = body.patch
    if body.status is not None:
        version.status = body.status
    if body.updated_by is not None:
        version.updated_by = _resolve_user(body.updated_by)
    version.updated = datetime.utcnow()


def _apply_project_update(project: Project, body: ProjectUpdateInput) -> None:
    data = body.model_dump(exclude_none=True)

    if "name" in data:
        project.name = data["name"]
    if "admins" in data:
        project.admins = _resolve_refs(User, data["admins"], "admin")
    if "members" in data:
        project.members = _resolve_refs(User, data["members"], "member")
    if "viewers" in data:
        project.viewers = _resolve_refs(User, data["viewers"], "viewer")
    if "forms" in data:
        project.forms = _resolve_refs(Form, data["forms"], "form")
    if "organizations" in data:
        project.organizations = _resolve_refs(Organization, data["organizations"], "organization")
    if "tags" in data:
        project.tags = data["tags"]
    if "status" in data:
        project.status = data["status"]


def _apply_form_update(form: Form, body: FormUpdateInput) -> None:
    data = body.model_dump(exclude_none=True)

    if "sections" in data:
        form.sections = data["sections"]
    if "editors" in data:
        form.editors = _resolve_refs(User, data["editors"], "editor")
    if "viewers" in data:
        form.viewers = _resolve_refs(User, data["viewers"], "viewer")
    if "reviewers" in data:
        form.reviewers = _resolve_refs(User, data["reviewers"], "reviewer")
    if "approvers" in data:
        form.approvers = _resolve_refs(User, data["approvers"], "approver")
    if "submitters" in data:
        form.submitters = _resolve_refs(User, data["submitters"], "submitter")
    if "requires_reviewer" in data:
        form.requires_reviewer = data["requires_reviewer"]
    if "requires_approver" in data:
        form.requires_approver = data["requires_approver"]
    if "min_reviewers_required" in data:
        form.min_reviewers_required = data["min_reviewers_required"]
    if "min_approvers_required" in data:
        form.min_approvers_required = data["min_approvers_required"]
    if "validation_conditions" in data:
        form.validation_conditions = _resolve_refs(
            Condition, data["validation_conditions"], "validation_condition"
        )
    if "validation_condition_messages" in data:
        form.validation_condition_messages = data["validation_condition_messages"]
    if "child_sections" in data:
        form.child_sections = _resolve_refs(Section, data["child_sections"], "section")
    if "tags" in data:
        form.tags = data["tags"]
    if "icon" in data:
        form.icon = data["icon"]
    if "status" in data:
        form.status = data["status"]


def _apply_section_update(section: Section, body: SectionUpdateInput) -> None:
    data = body.model_dump(exclude_none=True)

    for key in (
        "questions",
        "add_button",
        "is_repeatable",
        "check_repeat_on",
        "min_repeatable_count",
        "max_repeatable_count",
        "title",
        "description",
        "isDeleted",
        "deletedAt",
        "deleted_at",
        "tags",
        "icon",
        "status",
        "validation_condition_messages",
    ):
        if key in data:
            setattr(section, key, data[key])

    if "repeatable_condition" in data:
        section.repeatable_condition = Condition.objects(uuid=data["repeatable_condition"]).first()
    if "visibility_condition" in data:
        section.visibility_condition = Condition.objects(uuid=data["visibility_condition"]).first()
    if "validation_conditions" in data:
        section.validation_conditions = _resolve_refs(
            Condition, data["validation_conditions"], "validation_condition"
        )
    if "deletedBy" in data:
        section.deletedBy = User.objects(uuid=data["deletedBy"]).first()
    if "deleted_by" in data:
        section.deleted_by = User.objects(uuid=data["deleted_by"]).first()


def _apply_question_update(question: Question, body: QuestionUpdateInput) -> None:
    data = body.model_dump(exclude_none=True)

    for key in (
        "type",
        "label",
        "placeholder",
        "description",
        "default_value",
        "help_text",
        "tooltip",
        "add_button",
        "is_repeatable",
        "check_repeat_on",
        "min_repeatable_count",
        "max_repeatable_count",
        "isAction",
        "actionButtonType",
        "actionType",
        "actionLabel",
        "tags",
        "hideButton",
        "actionIcon",
        "status",
        "validation_condition_messages",
    ):
        if key in data:
            setattr(question, key, data[key])

    if "validation_conditions" in data:
        question.validation_conditions = _resolve_refs(
            Condition, data["validation_conditions"], "validation_condition"
        )
    if "visibility_conditions" in data:
        question.visibility_conditions = _resolve_refs(
            Condition, data["visibility_conditions"], "visibility_condition"
        )
    if "repeatable_condition" in data:
        question.repeatable_condition = Condition.objects(uuid=data["repeatable_condition"]).first()
    if "choices" in data:
        choices = []
        for choice in body.choices or []:
            choices.append(
                {
                    "uuid": choice.uuid,
                    "label": choice.label,
                    "value": choice.value,
                    "visibility_condition": Condition.objects(
                        uuid=choice.visibility_condition
                    ).first()
                    if choice.visibility_condition
                    else None,
                }
            )
        question.choices = choices


def _list_docs(model: Type[Any], query: ListQuery):
    qs = model.objects
    if query.status:
        qs = qs(status=query.status)
    return list(qs.skip(query.offset).limit(query.limit))


def _project_form_uuids(project: Project) -> set[str]:
    return {str(getattr(form, "uuid", "")) for form in (project.forms or []) if getattr(form, "uuid", None)}


def _form_section_uuids(form: Form) -> set[str]:
    uuids: set[str] = set()
    for section_ids in (form.sections or {}).values():
        for section_uuid in section_ids or []:
            uuids.add(str(section_uuid))
    return uuids


def _section_question_uuids(section: Section) -> set[str]:
    uuids: set[str] = set()
    for question_ids in (section.questions or {}).values():
        for question_uuid in question_ids or []:
            uuids.add(str(question_uuid))
    return uuids


def _resolve_version_key(versions: list[Any], versioned_map: Dict[str, list[str]], requested: Optional[str]) -> str:
    available = [str(v.uuid) for v in (versions or []) if getattr(v, "uuid", None)]

    if requested:
        if requested not in available:
            raise ValueError(f"Unknown version_uuid: {requested}")
        return requested

    if len(available) == 1:
        return available[0]

    existing_keys = list((versioned_map or {}).keys())
    if len(existing_keys) == 1:
        return str(existing_keys[0])

    raise ValueError("version_uuid is required when multiple versions exist")


def _get_project_or_error(project_uuid: str):
    project = Project.objects(uuid=project_uuid).first()
    if not project:
        return None, _error("Project not found", 404)
    return project, None


def _get_form_for_project(project: Project, form_uuid: str):
    if form_uuid not in _project_form_uuids(project):
        return None, _error("Form not found under project", 404)
    form = Form.objects(uuid=form_uuid).first()
    if not form:
        return None, _error("Form not found", 404)
    return form, None


def _get_section_for_form(form: Form, section_uuid: str):
    if section_uuid not in _form_section_uuids(form):
        return None, _error("Section not found under form", 404)
    section = Section.objects(uuid=section_uuid).first()
    if not section:
        return None, _error("Section not found", 404)
    return section, None


def _get_question_for_section(section: Section, question_uuid: str):
    if question_uuid not in _section_question_uuids(section):
        return None, _error("Question not found under section", 404)
    question = Question.objects(uuid=question_uuid).first()
    if not question:
        return None, _error("Question not found", 404)
    return question, None


def _get_choice_for_question(question: Question, choice_uuid: str):
    for index, choice in enumerate(question.choices or []):
        if str(choice.uuid) == choice_uuid:
            return choice, index, None
    return None, None, _error("Choice not found", 404)


def _append_version(doc: Any, body: VersionCreateInput):
    if any(v.uuid == body.uuid for v in (doc.versions or [])):
        raise ValueError("Version uuid already exists")
    doc.versions.append(_version_from_create(body))


def _update_version(doc: Any, version_uuid: str, body: VersionUpdateInput) -> Version:
    for version in doc.versions or []:
        if version.uuid == version_uuid:
            _apply_version_update(version, body)
            return version
    raise ValueError("Version not found")


@resources_api.post("/projects", tags=[resources_tag], responses={201: ProjectOutput, 400: ErrorResponse})
def create_project(body: ProjectCreateInput):
    try:
        project = Project(
            uuid=body.uuid,
            name=body.name,
            versions=[_version_from_create(v) for v in body.versions],
            admins=_resolve_refs(User, body.admins, "admin"),
            members=_resolve_refs(User, body.members, "member"),
            viewers=_resolve_refs(User, body.viewers, "viewer"),
            forms=_resolve_refs(Form, body.forms, "form"),
            organizations=_resolve_refs(Organization, body.organizations, "organization"),
            tags=body.tags,
            status=body.status,
        )
        _validate_project_membership_role_alignment(project)
        project.save()
    except (ValidationError, ValueError, NotUniqueError) as exc:
        return _error(str(exc))
    return to_json_ready(to_project_output(project)), 201


@resources_api.get("/projects", tags=[resources_tag], responses={200: ProjectListResponse})
def list_projects(query: ListQuery):
    user = getattr(g, "resources_user", None)
    qs = Project.objects
    if query.status:
        qs = qs(status=query.status)

    visible_items = [project for project in list(qs) if _can_read_project(user, project)]
    try:
        items, page, page_size, total_items, total_pages, next_cursor = _paginate_items(
            visible_items,
            query,
        )
    except ValueError as exc:
        return _error(str(exc), 400)
    return to_json_ready(
        ProjectListResponse(
            items=[to_project_output(item) for item in items],
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
            next_cursor=next_cursor,
        )
    )


@resources_api.get("/projects/<uuid>", tags=[resources_tag], responses={200: ProjectOutput, 404: ErrorResponse})
def get_project(path: UUIDPath):
    item = Project.objects(uuid=path.uuid).first()
    if not item:
        return _error("Project not found", 404)
    return to_json_ready(to_project_output(item))


@resources_api.patch("/projects/<uuid>", tags=[resources_tag], responses={200: ProjectOutput, 400: ErrorResponse, 404: ErrorResponse})
def update_project(path: UUIDPath, body: ProjectUpdateInput):
    item = Project.objects(uuid=path.uuid).first()
    if not item:
        return _error("Project not found", 404)
    try:
        _apply_project_update(item, body)
        _validate_project_membership_role_alignment(item)
        item.save()
    except (ValidationError, ValueError, NotUniqueError) as exc:
        return _error(str(exc))
    return to_json_ready(to_project_output(item))


@resources_api.delete("/projects/<uuid>", tags=[resources_tag], responses={200: MessageResponse, 404: ErrorResponse})
def delete_project(path: UUIDPath):
    item = Project.objects(uuid=path.uuid).first()
    if not item:
        return _error("Project not found", 404)
    item.status = "deleted"
    item.save()
    return to_json_ready(MessageResponse(message="project_deleted"))


@resources_api.post(
    "/projects/<uuid>/versions",
    tags=[version_tag],
    responses={201: VersionOutput, 400: ErrorResponse, 404: ErrorResponse},
)
def create_project_version(path: UUIDPath, body: VersionCreateInput):
    item = Project.objects(uuid=path.uuid).first()
    if not item:
        return _error("Project not found", 404)
    try:
        _append_version(item, body)
        item.save()
    except (ValidationError, ValueError) as exc:
        return _error(str(exc))
    return to_json_ready(to_version_output(item.versions[-1])), 201


@resources_api.patch(
    "/projects/<uuid>/versions/<version_uuid>",
    tags=[version_tag],
    responses={200: VersionOutput, 400: ErrorResponse, 404: ErrorResponse},
)
def update_project_version(path: VersionPath, body: VersionUpdateInput):
    item = Project.objects(uuid=path.uuid).first()
    if not item:
        return _error("Project not found", 404)
    try:
        updated = _update_version(item, path.version_uuid, body)
        item.save()
    except (ValidationError, ValueError) as exc:
        if str(exc) == "Version not found":
            return _error(str(exc), 404)
        return _error(str(exc))
    return to_json_ready(to_version_output(updated))


@resources_api.post(
    "/projects/<project_uuid>/forms",
    tags=[resources_tag],
    responses={201: FormOutput, 400: ErrorResponse, 404: ErrorResponse},
)
def create_form(path: ProjectPath, body: FormCreateInput):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err

    try:
        form = Form(
            uuid=body.uuid,
            versions=[_version_from_create(v) for v in body.versions],
            sections=body.sections,
            editors=_resolve_refs(User, body.editors, "editor"),
            viewers=_resolve_refs(User, body.viewers, "viewer"),
            reviewers=_resolve_refs(User, body.reviewers, "reviewer"),
            approvers=_resolve_refs(User, body.approvers, "approver"),
            submitters=_resolve_refs(User, body.submitters, "submitter"),
            requires_reviewer=body.requires_reviewer,
            requires_approver=body.requires_approver,
            min_reviewers_required=body.min_reviewers_required,
            min_approvers_required=body.min_approvers_required,
            validation_conditions=_resolve_refs(
                Condition, body.validation_conditions, "validation_condition"
            ),
            validation_condition_messages=body.validation_condition_messages,
            child_sections=_resolve_refs(Section, body.child_sections, "section"),
            tags=body.tags,
            icon=body.icon,
            status=body.status,
        ).save()

        project.forms = list(project.forms or [])
        project.forms.append(form)
        project.save()
    except (ValidationError, ValueError, NotUniqueError) as exc:
        return _error(str(exc))
    return to_json_ready(to_form_output(form)), 201


@resources_api.get(
    "/projects/<project_uuid>/forms",
    tags=[resources_tag],
    responses={200: FormListResponse, 404: ErrorResponse},
)
def list_forms(path: ProjectPath, query: ListQuery):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err

    forms = [form for form in (project.forms or []) if getattr(form, "uuid", None)]
    if query.status:
        forms = [form for form in forms if getattr(form, "status", None) == query.status]
    try:
        items, page, page_size, total_items, total_pages, next_cursor = _paginate_items(forms, query)
    except ValueError as exc:
        return _error(str(exc), 400)
    return to_json_ready(
        FormListResponse(
            items=[to_form_output(item) for item in items],
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
            next_cursor=next_cursor,
        )
    )


@resources_api.get(
    "/projects/<project_uuid>/forms/<form_uuid>",
    tags=[resources_tag],
    responses={200: FormOutput, 404: ErrorResponse},
)
def get_form(path: FormPath):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    return to_json_ready(to_form_output(form))


@resources_api.patch(
    "/projects/<project_uuid>/forms/<form_uuid>",
    tags=[resources_tag],
    responses={200: FormOutput, 400: ErrorResponse, 404: ErrorResponse},
)
def update_form(path: FormPath, body: FormUpdateInput):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err

    try:
        _apply_form_update(form, body)
        form.save()
    except (ValidationError, ValueError, NotUniqueError) as exc:
        return _error(str(exc))
    return to_json_ready(to_form_output(form))


@resources_api.delete(
    "/projects/<project_uuid>/forms/<form_uuid>",
    tags=[resources_tag],
    responses={200: MessageResponse, 404: ErrorResponse},
)
def delete_form(path: FormPath):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err

    form.status = "deleted"
    form.save()
    return to_json_ready(MessageResponse(message="form_deleted"))


@resources_api.post(
    "/projects/<project_uuid>/forms/<form_uuid>/versions",
    tags=[version_tag],
    responses={201: VersionOutput, 400: ErrorResponse, 404: ErrorResponse},
)
def create_form_version(path: FormPath, body: VersionCreateInput):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err

    try:
        _append_version(form, body)
        form.save()
    except (ValidationError, ValueError) as exc:
        return _error(str(exc))
    return to_json_ready(to_version_output(form.versions[-1])), 201


@resources_api.patch(
    "/projects/<project_uuid>/forms/<form_uuid>/versions/<version_uuid>",
    tags=[version_tag],
    responses={200: VersionOutput, 400: ErrorResponse, 404: ErrorResponse},
)
def update_form_version(path: FormVersionPath, body: VersionUpdateInput):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err

    try:
        updated = _update_version(form, path.version_uuid, body)
        form.save()
    except (ValidationError, ValueError) as exc:
        if str(exc) == "Version not found":
            return _error(str(exc), 404)
        return _error(str(exc))
    return to_json_ready(to_version_output(updated))


@resources_api.post(
    "/projects/<project_uuid>/forms/<form_uuid>/workflow/submit",
    tags=[resources_tag],
    responses={200: WorkflowActionResponse, 400: ErrorResponse, 404: ErrorResponse, 409: ErrorResponse},
)
def submit_form_workflow(path: FormPath, body: WorkflowActionRequest):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err

    actor_user_uuid = str(getattr(g.resources_user, "uuid", "unknown"))
    try:
        message = _apply_form_workflow_action(
            form=form,
            action="submit",
            actor_user_uuid=actor_user_uuid,
            note=body.note,
        )
    except ValueError as exc:
        _security_event(
            event="resources_workflow_submit",
            outcome="rejected",
            reason=str(exc),
            details={"project_uuid": project.uuid, "form_uuid": form.uuid},
        )
        return _error(str(exc), 409)

    payload = WorkflowActionResponse(
        message=message,
        action="submit",
        actor_user_uuid=actor_user_uuid,
        form_uuid=form.uuid,
        project_uuid=project.uuid,
    )
    _security_event(
        event="resources_workflow_submit",
        outcome="success",
        details={"project_uuid": project.uuid, "form_uuid": form.uuid, "message": message},
    )
    return to_json_ready(payload)


@resources_api.post(
    "/projects/<project_uuid>/forms/<form_uuid>/workflow/review",
    tags=[resources_tag],
    responses={200: WorkflowActionResponse, 400: ErrorResponse, 404: ErrorResponse, 409: ErrorResponse},
)
def review_form_workflow(path: FormPath, body: WorkflowActionRequest):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err

    actor_user_uuid = str(getattr(g.resources_user, "uuid", "unknown"))
    try:
        message = _apply_form_workflow_action(
            form=form,
            action="review",
            actor_user_uuid=actor_user_uuid,
            note=body.note,
        )
    except ValueError as exc:
        _security_event(
            event="resources_workflow_review",
            outcome="rejected",
            reason=str(exc),
            details={"project_uuid": project.uuid, "form_uuid": form.uuid},
        )
        return _error(str(exc), 409)

    payload = WorkflowActionResponse(
        message=message,
        action="review",
        actor_user_uuid=actor_user_uuid,
        form_uuid=form.uuid,
        project_uuid=project.uuid,
    )
    _security_event(
        event="resources_workflow_review",
        outcome="success",
        details={"project_uuid": project.uuid, "form_uuid": form.uuid, "message": message},
    )
    return to_json_ready(payload)


@resources_api.post(
    "/projects/<project_uuid>/forms/<form_uuid>/workflow/approve",
    tags=[resources_tag],
    responses={200: WorkflowActionResponse, 400: ErrorResponse, 404: ErrorResponse, 409: ErrorResponse},
)
def approve_form_workflow(path: FormPath, body: WorkflowActionRequest):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err

    actor_user_uuid = str(getattr(g.resources_user, "uuid", "unknown"))
    try:
        message = _apply_form_workflow_action(
            form=form,
            action="approve",
            actor_user_uuid=actor_user_uuid,
            note=body.note,
        )
    except ValueError as exc:
        _security_event(
            event="resources_workflow_approve",
            outcome="rejected",
            reason=str(exc),
            details={"project_uuid": project.uuid, "form_uuid": form.uuid},
        )
        return _error(str(exc), 409)

    payload = WorkflowActionResponse(
        message=message,
        action="approve",
        actor_user_uuid=actor_user_uuid,
        form_uuid=form.uuid,
        project_uuid=project.uuid,
    )
    _security_event(
        event="resources_workflow_approve",
        outcome="success",
        details={"project_uuid": project.uuid, "form_uuid": form.uuid, "message": message},
    )
    return to_json_ready(payload)


@resources_api.post(
    "/projects/<project_uuid>/forms/<form_uuid>/sections",
    tags=[resources_tag],
    responses={201: SectionOutput, 400: ErrorResponse, 404: ErrorResponse},
)
def create_section(path: FormPath, query: VersionLinkQuery, body: SectionCreateInput):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err

    try:
        version_key = _resolve_version_key(form.versions or [], form.sections or {}, query.version_uuid)

        section = Section(
            uuid=body.uuid,
            versions=[_version_from_create(v) for v in body.versions],
            questions=body.questions,
            add_button=body.add_button,
            is_repeatable=body.is_repeatable,
            repeatable_condition=Condition.objects(uuid=body.repeatable_condition).first()
            if body.repeatable_condition
            else None,
            check_repeat_on=body.check_repeat_on,
            min_repeatable_count=body.min_repeatable_count,
            max_repeatable_count=body.max_repeatable_count,
            title=body.title,
            description=body.description,
            isDeleted=body.isDeleted,
            deletedBy=User.objects(uuid=body.deletedBy).first() if body.deletedBy else None,
            deletedAt=body.deletedAt,
            deleted_at=body.deleted_at,
            deleted_by=User.objects(uuid=body.deleted_by).first() if body.deleted_by else None,
            visibility_condition=Condition.objects(uuid=body.visibility_condition).first()
            if body.visibility_condition
            else None,
            validation_conditions=_resolve_refs(
                Condition, body.validation_conditions, "validation_condition"
            ),
            validation_condition_messages=body.validation_condition_messages,
            tags=body.tags,
            icon=body.icon,
            status=body.status,
        ).save()

        form.sections = dict(form.sections or {})
        form.sections[version_key] = list(form.sections.get(version_key, []))
        if section.uuid not in form.sections[version_key]:
            form.sections[version_key].append(section.uuid)
        form.save()
    except (ValidationError, ValueError, NotUniqueError) as exc:
        return _error(str(exc))
    return to_json_ready(to_section_output(section)), 201


@resources_api.get(
    "/projects/<project_uuid>/forms/<form_uuid>/sections",
    tags=[resources_tag],
    responses={200: SectionListResponse, 404: ErrorResponse},
)
def list_sections(path: FormPath, query: ListQuery):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err

    uuids = list(_form_section_uuids(form))
    qs = Section.objects(uuid__in=uuids)
    if query.status:
        qs = qs(status=query.status)
    items = list(qs)
    try:
        items, page, page_size, total_items, total_pages, next_cursor = _paginate_items(items, query)
    except ValueError as exc:
        return _error(str(exc), 400)
    return to_json_ready(
        SectionListResponse(
            items=[to_section_output(item) for item in items],
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
            next_cursor=next_cursor,
        )
    )


@resources_api.get(
    "/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>",
    tags=[resources_tag],
    responses={200: SectionOutput, 404: ErrorResponse},
)
def get_section(path: SectionPath):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    section, section_err = _get_section_for_form(form, path.section_uuid)
    if section_err:
        return section_err
    return to_json_ready(to_section_output(section))


@resources_api.patch(
    "/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>",
    tags=[resources_tag],
    responses={200: SectionOutput, 400: ErrorResponse, 404: ErrorResponse},
)
def update_section(path: SectionPath, body: SectionUpdateInput):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    section, section_err = _get_section_for_form(form, path.section_uuid)
    if section_err:
        return section_err

    try:
        _apply_section_update(section, body)
        section.save()
    except (ValidationError, ValueError, NotUniqueError) as exc:
        return _error(str(exc))
    return to_json_ready(to_section_output(section))


@resources_api.delete(
    "/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>",
    tags=[resources_tag],
    responses={200: MessageResponse, 404: ErrorResponse},
)
def delete_section(path: SectionPath):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    section, section_err = _get_section_for_form(form, path.section_uuid)
    if section_err:
        return section_err

    section.status = "deleted"
    section.save()

    form.sections = dict(form.sections or {})
    for key, values in form.sections.items():
        form.sections[key] = [value for value in (values or []) if value != section.uuid]
    form.save()

    return to_json_ready(MessageResponse(message="section_deleted"))


@resources_api.post(
    "/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/versions",
    tags=[version_tag],
    responses={201: VersionOutput, 400: ErrorResponse, 404: ErrorResponse},
)
def create_section_version(path: SectionPath, body: VersionCreateInput):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    section, section_err = _get_section_for_form(form, path.section_uuid)
    if section_err:
        return section_err

    try:
        _append_version(section, body)
        section.save()
    except (ValidationError, ValueError) as exc:
        return _error(str(exc))
    return to_json_ready(to_version_output(section.versions[-1])), 201


@resources_api.patch(
    "/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/versions/<version_uuid>",
    tags=[version_tag],
    responses={200: VersionOutput, 400: ErrorResponse, 404: ErrorResponse},
)
def update_section_version(path: SectionVersionPath, body: VersionUpdateInput):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    section, section_err = _get_section_for_form(form, path.section_uuid)
    if section_err:
        return section_err

    try:
        updated = _update_version(section, path.version_uuid, body)
        section.save()
    except (ValidationError, ValueError) as exc:
        if str(exc) == "Version not found":
            return _error(str(exc), 404)
        return _error(str(exc))
    return to_json_ready(to_version_output(updated))


@resources_api.post(
    "/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions",
    tags=[resources_tag],
    responses={201: QuestionOutput, 400: ErrorResponse, 404: ErrorResponse},
)
def create_question(path: SectionPath, query: VersionLinkQuery, body: QuestionCreateInput):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    section, section_err = _get_section_for_form(form, path.section_uuid)
    if section_err:
        return section_err

    try:
        version_key = _resolve_version_key(
            section.versions or [],
            section.questions or {},
            query.version_uuid,
        )

        choices = []
        for choice in body.choices:
            choices.append(
                Choice(
                    uuid=choice.uuid,
                    label=choice.label,
                    value=choice.value,
                    visibility_condition=Condition.objects(
                        uuid=choice.visibility_condition
                    ).first()
                    if choice.visibility_condition
                    else None,
                )
            )

        question = Question(
            uuid=body.uuid,
            versions=[_version_from_create(v) for v in body.versions],
            type=body.type,
            label=body.label,
            placeholder=body.placeholder,
            description=body.description,
            default_value=body.default_value,
            help_text=body.help_text,
            tooltip=body.tooltip,
            validation_conditions=_resolve_refs(
                Condition, body.validation_conditions, "validation_condition"
            ),
            validation_condition_messages=body.validation_condition_messages,
            visibility_conditions=_resolve_refs(
                Condition, body.visibility_conditions, "visibility_condition"
            ),
            add_button=body.add_button,
            is_repeatable=body.is_repeatable,
            repeatable_condition=Condition.objects(uuid=body.repeatable_condition).first()
            if body.repeatable_condition
            else None,
            check_repeat_on=body.check_repeat_on,
            min_repeatable_count=body.min_repeatable_count,
            max_repeatable_count=body.max_repeatable_count,
            isAction=body.isAction,
            actionButtonType=body.actionButtonType,
            actionType=body.actionType,
            actionLabel=body.actionLabel,
            tags=body.tags,
            choices=choices,
            hideButton=body.hideButton,
            actionIcon=body.actionIcon,
            status=body.status,
        ).save()

        section.questions = dict(section.questions or {})
        section.questions[version_key] = list(section.questions.get(version_key, []))
        if question.uuid not in section.questions[version_key]:
            section.questions[version_key].append(question.uuid)
        section.save()
    except (ValidationError, ValueError, NotUniqueError) as exc:
        return _error(str(exc))
    return to_json_ready(to_question_output(question)), 201


@resources_api.get(
    "/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions",
    tags=[resources_tag],
    responses={200: QuestionListResponse, 404: ErrorResponse},
)
def list_questions(path: SectionPath, query: ListQuery):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    section, section_err = _get_section_for_form(form, path.section_uuid)
    if section_err:
        return section_err

    uuids = list(_section_question_uuids(section))
    qs = Question.objects(uuid__in=uuids)
    if query.status:
        qs = qs(status=query.status)
    items = list(qs)
    try:
        items, page, page_size, total_items, total_pages, next_cursor = _paginate_items(items, query)
    except ValueError as exc:
        return _error(str(exc), 400)
    return to_json_ready(
        QuestionListResponse(
            items=[to_question_output(item) for item in items],
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
            next_cursor=next_cursor,
        )
    )


@resources_api.get(
    "/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions/<question_uuid>",
    tags=[resources_tag],
    responses={200: QuestionOutput, 404: ErrorResponse},
)
def get_question(path: QuestionPath):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    section, section_err = _get_section_for_form(form, path.section_uuid)
    if section_err:
        return section_err
    question, question_err = _get_question_for_section(section, path.question_uuid)
    if question_err:
        return question_err
    return to_json_ready(to_question_output(question))


@resources_api.patch(
    "/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions/<question_uuid>",
    tags=[resources_tag],
    responses={200: QuestionOutput, 400: ErrorResponse, 404: ErrorResponse},
)
def update_question(path: QuestionPath, body: QuestionUpdateInput):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    section, section_err = _get_section_for_form(form, path.section_uuid)
    if section_err:
        return section_err
    question, question_err = _get_question_for_section(section, path.question_uuid)
    if question_err:
        return question_err

    try:
        _apply_question_update(question, body)
        question.save()
    except (ValidationError, ValueError, NotUniqueError) as exc:
        return _error(str(exc))
    return to_json_ready(to_question_output(question))


@resources_api.delete(
    "/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions/<question_uuid>",
    tags=[resources_tag],
    responses={200: MessageResponse, 404: ErrorResponse},
)
def delete_question(path: QuestionPath):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    section, section_err = _get_section_for_form(form, path.section_uuid)
    if section_err:
        return section_err
    question, question_err = _get_question_for_section(section, path.question_uuid)
    if question_err:
        return question_err

    question.status = "deleted"
    question.save()

    section.questions = dict(section.questions or {})
    for key, values in section.questions.items():
        section.questions[key] = [value for value in (values or []) if value != question.uuid]
    section.save()

    return to_json_ready(MessageResponse(message="question_deleted"))


@resources_api.post(
    "/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions/<question_uuid>/versions",
    tags=[version_tag],
    responses={201: VersionOutput, 400: ErrorResponse, 404: ErrorResponse},
)
def create_question_version(path: QuestionPath, body: VersionCreateInput):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    section, section_err = _get_section_for_form(form, path.section_uuid)
    if section_err:
        return section_err
    question, question_err = _get_question_for_section(section, path.question_uuid)
    if question_err:
        return question_err

    try:
        _append_version(question, body)
        question.save()
    except (ValidationError, ValueError) as exc:
        return _error(str(exc))
    return to_json_ready(to_version_output(question.versions[-1])), 201


@resources_api.patch(
    "/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions/<question_uuid>/versions/<version_uuid>",
    tags=[version_tag],
    responses={200: VersionOutput, 400: ErrorResponse, 404: ErrorResponse},
)
def update_question_version(path: QuestionVersionPath, body: VersionUpdateInput):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    section, section_err = _get_section_for_form(form, path.section_uuid)
    if section_err:
        return section_err
    question, question_err = _get_question_for_section(section, path.question_uuid)
    if question_err:
        return question_err

    try:
        updated = _update_version(question, path.version_uuid, body)
        question.save()
    except (ValidationError, ValueError) as exc:
        if str(exc) == "Version not found":
            return _error(str(exc), 404)
        return _error(str(exc))
    return to_json_ready(to_version_output(updated))


@resources_api.post(
    "/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions/<question_uuid>/choices",
    tags=[resources_tag],
    responses={201: ChoiceOutput, 400: ErrorResponse, 404: ErrorResponse},
)
def create_choice(path: QuestionPath, body: ChoiceCreateInput):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    section, section_err = _get_section_for_form(form, path.section_uuid)
    if section_err:
        return section_err
    question, question_err = _get_question_for_section(section, path.question_uuid)
    if question_err:
        return question_err

    if any(str(choice.uuid) == body.uuid for choice in (question.choices or [])):
        return _error("Choice uuid already exists")

    choice = Choice(
        uuid=body.uuid,
        label=body.label,
        value=body.value,
        visibility_condition=Condition.objects(uuid=body.visibility_condition).first()
        if body.visibility_condition
        else None,
    )
    question.choices = list(question.choices or [])
    question.choices.append(choice)

    try:
        question.save()
    except (ValidationError, ValueError, NotUniqueError) as exc:
        return _error(str(exc))

    return to_json_ready(to_choice_output(choice)), 201


@resources_api.get(
    "/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions/<question_uuid>/choices",
    tags=[resources_tag],
    responses={200: ChoiceListResponse, 404: ErrorResponse},
)
def list_choices(path: QuestionPath, query: ListQuery):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    section, section_err = _get_section_for_form(form, path.section_uuid)
    if section_err:
        return section_err
    question, question_err = _get_question_for_section(section, path.question_uuid)
    if question_err:
        return question_err

    all_items = list(question.choices or [])
    total_items = len(all_items)

    next_cursor = None
    if query.cursor:
        try:
            start = _decode_index_cursor(query.cursor)
        except ValueError as exc:
            return _error(str(exc), 400)
        page = max(query.page, 1)
        page_size = max(query.page_size, 1)
        items = all_items[start : start + page_size]
        if start + page_size < total_items:
            next_cursor = _encode_index_cursor(start + page_size)
    elif query.offset is not None or query.limit is not None:
        page_size = query.limit or 50
        offset = query.offset or 0
        page = (offset // max(page_size, 1)) + 1
        items = all_items[offset : offset + page_size]
    else:
        page = max(query.page, 1)
        page_size = max(query.page_size, 1)
        start = (page - 1) * page_size
        items = all_items[start : start + page_size]
        if start + page_size < total_items:
            next_cursor = _encode_index_cursor(start + page_size)

    total_pages = (total_items + page_size - 1) // page_size if total_items else 0
    return to_json_ready(
        ChoiceListResponse(
            items=[to_choice_output(choice) for choice in items],
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
            next_cursor=next_cursor,
        )
    )


@resources_api.get(
    "/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions/<question_uuid>/choices/<choice_uuid>",
    tags=[resources_tag],
    responses={200: ChoiceOutput, 404: ErrorResponse},
)
def get_choice(path: ChoicePath):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    section, section_err = _get_section_for_form(form, path.section_uuid)
    if section_err:
        return section_err
    question, question_err = _get_question_for_section(section, path.question_uuid)
    if question_err:
        return question_err
    choice, _, choice_err = _get_choice_for_question(question, path.choice_uuid)
    if choice_err:
        return choice_err

    return to_json_ready(to_choice_output(choice))


@resources_api.patch(
    "/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions/<question_uuid>/choices/<choice_uuid>",
    tags=[resources_tag],
    responses={200: ChoiceOutput, 400: ErrorResponse, 404: ErrorResponse},
)
def update_choice(path: ChoicePath, body: ChoiceUpdateInput):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    section, section_err = _get_section_for_form(form, path.section_uuid)
    if section_err:
        return section_err
    question, question_err = _get_question_for_section(section, path.question_uuid)
    if question_err:
        return question_err
    choice, _, choice_err = _get_choice_for_question(question, path.choice_uuid)
    if choice_err:
        return choice_err

    if body.label is not None:
        choice.label = body.label
    if body.value is not None:
        choice.value = body.value
    if body.visibility_condition is not None:
        choice.visibility_condition = Condition.objects(uuid=body.visibility_condition).first()

    try:
        question.save()
    except (ValidationError, ValueError, NotUniqueError) as exc:
        return _error(str(exc))

    return to_json_ready(to_choice_output(choice))


@resources_api.delete(
    "/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions/<question_uuid>/choices/<choice_uuid>",
    tags=[resources_tag],
    responses={200: MessageResponse, 404: ErrorResponse},
)
def delete_choice(path: ChoicePath):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    section, section_err = _get_section_for_form(form, path.section_uuid)
    if section_err:
        return section_err
    question, question_err = _get_question_for_section(section, path.question_uuid)
    if question_err:
        return question_err
    _, index, choice_err = _get_choice_for_question(question, path.choice_uuid)
    if choice_err:
        return choice_err

    question.choices.pop(index)
    question.save()
    return to_json_ready(MessageResponse(message="choice_deleted"))
