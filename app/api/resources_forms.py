"""Form CRUD, version, workflow, and UI config endpoints."""

from __future__ import annotations

from typing import Any, Dict

from flask import g
from mongoengine.errors import NotUniqueError, ValidationError

from app.models.form import (
    Condition,
    Form,
    Section,
    FormResponse,
    FormResponseStatusEvent,
    ResponseItem,
)
from app.models.ui_template import LayoutTemplate, ThemeTemplate
from app.models.user import User
from app.schemas.form import FormCreateInput, FormOutput, FormUpdateInput
from app.schemas.form_response import (
    FormResponseCreateInput,
    FormResponseOutput,
    FormResponseUpdateInput,
)
from app.schemas.mappers import (
    to_form_output,
    to_json_ready,
    to_version_output,
    to_form_response_output,
)
from app.schemas.ui_template import EffectiveUiConfigOutput
from app.schemas.version import VersionCreateInput, VersionOutput, VersionUpdateInput
from app.api.resources_schemas import (
    ErrorResponse,
    FormListResponse,
    FormPath,
    FormVersionPath,
    ListQuery,
    MessageResponse,
    ProjectPath,
    FormResponseSubmissionPath,
    WorkflowActionRequest,
    WorkflowActionResponse,
    FormResponseListResponse,
    AssignReviewersRequest,
    AssignApproversRequest,
    ResponseActionExecutionPath,
)
from app.api.resources_support import _error, resources_api, resources_tag, version_tag
from app.api.resources_context import (
    _append_version,
    _apply_form_update,
    _get_form_for_project,
    _get_project_or_error,
    _resolve_refs,
    _update_version,
    _version_from_create,
)
from app.api.resources_utils import (
    apply_form_workflow_action as _apply_form_workflow_action,
    deep_merge as _deep_merge,
    paginate_items as _paginate_items,
    paginate_queryset as _paginate_queryset,
)
from app.services.form_response_service import create_form_response


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
            theme_template_uuid=body.theme_template_uuid,
            theme_revision_uuid=body.theme_revision_uuid,
            layout_template_uuid=body.layout_template_uuid,
            layout_revision_uuid=body.layout_revision_uuid,
            ui_overrides=body.ui_overrides,
            is_public=body.is_public,
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
        forms = [
            form for form in forms if getattr(form, "status", None) == query.status
        ]
    try:
        items, page, page_size, total_items, total_pages, next_cursor = _paginate_items(
            forms, query
        )
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


@resources_api.get(
    "/projects/<project_uuid>/forms/<form_uuid>/ui/effective",
    tags=[resources_tag],
    responses={200: EffectiveUiConfigOutput, 404: ErrorResponse},
)
def get_effective_ui_config(path: FormPath):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err

    theme_config: Dict[str, Any] = {}
    if form.theme_template_uuid and form.theme_revision_uuid:
        theme_template = ThemeTemplate.objects(uuid=form.theme_template_uuid).first()
        if theme_template:
            for revision in theme_template.revisions or []:
                if revision.uuid == form.theme_revision_uuid:
                    theme_config = dict(revision.config or {})
                    break

    layout_config: Dict[str, Any] = {}
    if form.layout_template_uuid and form.layout_revision_uuid:
        layout_template = LayoutTemplate.objects(uuid=form.layout_template_uuid).first()
        if layout_template:
            for revision in layout_template.revisions or []:
                if revision.uuid == form.layout_revision_uuid:
                    layout_config = dict(revision.config or {})
                    break

    ui_overrides = dict(form.ui_overrides or {})
    effective = _deep_merge(
        {"theme": theme_config, "layout": layout_config}, ui_overrides
    )
    return to_json_ready(
        EffectiveUiConfigOutput(
            theme_template_uuid=form.theme_template_uuid,
            theme_revision_uuid=form.theme_revision_uuid,
            layout_template_uuid=form.layout_template_uuid,
            layout_revision_uuid=form.layout_revision_uuid,
            theme_config=theme_config,
            layout_config=layout_config,
            ui_overrides=ui_overrides,
            effective_ui_config=effective,
        )
    )


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


@resources_api.post(
    "/projects/<project_uuid>/forms/<form_uuid>/responses",
    tags=[resources_tag],
    responses={201: FormResponseOutput, 400: ErrorResponse, 404: ErrorResponse},
)
def submit_form_response(
    path: FormResponseSubmissionPath, body: FormResponseCreateInput
):
    return create_form_response(
        project_uuid=path.project_uuid,
        form_uuid=path.form_uuid,
        body=body,
        submitted_by=getattr(g, "resources_user", None),
    )


@resources_api.post(
    "/public/projects/<project_uuid>/forms/<form_uuid>/responses",
    tags=[resources_tag],
    responses={
        201: FormResponseOutput,
        400: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
    },
)
def submit_public_form_response(
    path: FormResponseSubmissionPath, body: FormResponseCreateInput
):
    return create_form_response(
        project_uuid=path.project_uuid,
        form_uuid=path.form_uuid,
        body=body,
        submitted_by=None,
        public_only=True,
    )


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


def _workflow_action(path: FormPath, body: WorkflowActionRequest, action: str):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    from app.api.resources_utils import security_event as _security_event

    actor_user_uuid = str(getattr(g.resources_user, "uuid", "unknown"))
    try:
        message = _apply_form_workflow_action(
            form=form,
            action=action,
            actor_user_uuid=actor_user_uuid,
            note=body.note,
        )
    except ValueError as exc:
        _security_event(
            event=f"resources_workflow_{action}",
            outcome="rejected",
            reason=str(exc),
            details={"project_uuid": project.uuid, "form_uuid": form.uuid},
        )
        return _error(str(exc), 409)
    from app.api.resources_utils import security_event as _security_event2

    _security_event2(
        event=f"resources_workflow_{action}",
        outcome="success",
        details={
            "project_uuid": project.uuid,
            "form_uuid": form.uuid,
            "message": message,
        },
    )
    return to_json_ready(
        WorkflowActionResponse(
            message=message,
            action=action,
            actor_user_uuid=actor_user_uuid,
            form_uuid=form.uuid,
            project_uuid=project.uuid,
        )
    )


@resources_api.post(
    "/projects/<project_uuid>/forms/<form_uuid>/workflow/submit",
    tags=[resources_tag],
    responses={
        200: WorkflowActionResponse,
        400: ErrorResponse,
        404: ErrorResponse,
        409: ErrorResponse,
    },
)
def submit_form_workflow(path: FormPath, body: WorkflowActionRequest):
    return _workflow_action(path, body, "submit")


@resources_api.post(
    "/projects/<project_uuid>/forms/<form_uuid>/workflow/review",
    tags=[resources_tag],
    responses={
        200: WorkflowActionResponse,
        400: ErrorResponse,
        404: ErrorResponse,
        409: ErrorResponse,
    },
)
def review_form_workflow(path: FormPath, body: WorkflowActionRequest):
    return _workflow_action(path, body, "review")


@resources_api.post(
    "/projects/<project_uuid>/forms/<form_uuid>/workflow/approve",
    tags=[resources_tag],
    responses={
        200: WorkflowActionResponse,
        400: ErrorResponse,
        404: ErrorResponse,
        409: ErrorResponse,
    },
)
def approve_form_workflow(path: FormPath, body: WorkflowActionRequest):
    return _workflow_action(path, body, "approve")


@resources_api.get(
    "/projects/<project_uuid>/forms/<form_uuid>/responses",
    tags=[resources_tag],
    responses={200: FormResponseListResponse, 404: ErrorResponse},
)
def list_form_responses(path: FormResponseSubmissionPath, query: ListQuery):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    responses = FormResponse.objects(form_uuid=form.uuid, status__ne="deleted")
    items, page, page_size, total_items, total_pages, next_cursor = _paginate_queryset(
        responses, query
    )
    return to_json_ready(
        FormResponseListResponse(
            items=[to_form_response_output(item) for item in items],
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
            next_cursor=next_cursor,
        )
    )


@resources_api.get(
    "/projects/<project_uuid>/forms/<form_uuid>/responses/<response_uuid>",
    tags=[resources_tag],
    responses={200: FormResponseOutput, 404: ErrorResponse},
)
def get_form_response(path: ResponseActionExecutionPath):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    response = FormResponse.objects(
        uuid=path.response_uuid, form_uuid=form.uuid, status__ne="deleted"
    ).first()
    if not response:
        return _error("Form response not found", 404)
    return to_json_ready(to_form_response_output(response))


@resources_api.delete(
    "/projects/<project_uuid>/forms/<form_uuid>/responses/<response_uuid>",
    tags=[resources_tag],
    responses={200: MessageResponse, 404: ErrorResponse},
)
def delete_form_response(path: ResponseActionExecutionPath):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    response = FormResponse.objects(
        uuid=path.response_uuid, form_uuid=form.uuid, status__ne="deleted"
    ).first()
    if not response:
        return _error("Form response not found", 404)

    from datetime import datetime, timezone
    from app.services.response_management import (
        write_response_audit_log,
        trigger_async_actions,
    )

    actor_uuid = getattr(g.resources_user, "uuid", None)
    old_status = response.status

    response.status = "deleted"
    response.deleted_at = datetime.now(timezone.utc)
    response.deleted_by = getattr(g, "resources_user", None)

    event = FormResponseStatusEvent(
        transition_from=old_status,
        transition_to="deleted",
        changed_at=response.deleted_at,
        reason="deleted_by_user",
    )
    response.status_history = list(response.status_history or [])
    response.status_history.append(event)
    response.save()

    # Log Audit
    write_response_audit_log(
        response_uuid=response.uuid,
        actor_user_uuid=actor_uuid,
        action="delete",
        changes={"status": {"old": old_status, "new": "deleted"}},
    )

    # Trigger Async Tasks
    trigger_async_actions(response.uuid, "deleted")

    return to_json_ready(MessageResponse(message="Response deleted successfully"))


@resources_api.patch(
    "/projects/<project_uuid>/forms/<form_uuid>/responses/<response_uuid>",
    tags=[resources_tag],
    responses={200: FormResponseOutput, 400: ErrorResponse, 404: ErrorResponse},
)
def update_form_response(
    path: ResponseActionExecutionPath, body: FormResponseUpdateInput
):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    response = FormResponse.objects(
        uuid=path.response_uuid, form_uuid=form.uuid, status__ne="deleted"
    ).first()
    if not response:
        return _error("Form response not found", 404)

    from app.services.response_management import (
        check_field_level_permission,
        validate_response_conditions,
        write_response_audit_log,
        trigger_async_actions,
    )

    user = getattr(g, "resources_user", None)
    actor_uuid = getattr(user, "uuid", None)

    # 1. Field-level role constraint check
    if body.responses is not None:
        for item in body.responses:
            if not check_field_level_permission(user, item.question_uuid, "write"):
                return _error(f"Unauthorized to update field {item.question_uuid}", 403)

    # 2. Backend condition validation
    if body.responses is not None:
        val_errors = validate_response_conditions(
            form, body.responses, body.response_map or response.response_map or {}
        )
        if val_errors:
            return _error(f"Validation failed: {', '.join(val_errors)}", 400)

    try:
        old_status = response.status
        changes = {}

        if body.responses is not None:
            response.responses = [
                ResponseItem(**item.model_dump()) for item in body.responses
            ]
            changes["responses"] = "updated"
        if body.response_map is not None:
            response.response_map = body.response_map
        if body.score is not None:
            response.score = body.score
        if body.validation_errors is not None:
            response.validation_errors = body.validation_errors
        if body.metadata is not None:
            merged = dict(response.metadata or {})
            merged.update(body.metadata)
            response.metadata = merged
            changes["metadata"] = body.metadata
        if body.status is not None and body.status != response.status:
            from datetime import datetime, timezone

            response.status = body.status
            event = FormResponseStatusEvent(
                transition_from=old_status,
                transition_to=body.status,
                changed_at=datetime.now(timezone.utc),
                reason="updated_by_user",
            )
            response.status_history = list(response.status_history or [])
            response.status_history.append(event)
            changes["status"] = {"old": old_status, "new": body.status}

        response.save()

        # 3. Log Audit
        write_response_audit_log(
            response_uuid=response.uuid,
            actor_user_uuid=actor_uuid,
            action="update",
            changes=changes,
        )

        # 4. Trigger Async Tasks
        trigger_async_actions(response.uuid, "updated")

    except (ValidationError, ValueError) as exc:
        return _error(str(exc), 400)

    return to_json_ready(to_form_response_output(response))


@resources_api.post(
    "/projects/<project_uuid>/forms/<form_uuid>/responses/<response_uuid>/review",
    tags=[resources_tag],
    responses={200: FormResponseOutput, 400: ErrorResponse, 404: ErrorResponse},
)
def review_form_response(
    path: ResponseActionExecutionPath, body: WorkflowActionRequest
):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    response = FormResponse.objects(
        uuid=path.response_uuid, form_uuid=form.uuid, status__ne="deleted"
    ).first()
    if not response:
        return _error("Form response not found", 404)

    from datetime import datetime, timezone
    from app.services.response_management import (
        write_response_audit_log,
        trigger_async_actions,
    )

    user = getattr(g, "resources_user", None)
    actor_uuid = getattr(user, "uuid", None)
    old_status = response.status

    response.status = "in_review"
    response.reviewed_at = datetime.now(timezone.utc)
    if user and user not in response.reviewed_by:
        response.reviewed_by = list(response.reviewed_by or [])
        response.reviewed_by.append(user)

    event = FormResponseStatusEvent(
        transition_from=old_status,
        transition_to="in_review",
        changed_at=response.reviewed_at,
        reason=body.note or "reviewed_by_user",
    )
    response.status_history = list(response.status_history or [])
    response.status_history.append(event)
    response.save()

    # Log Audit
    write_response_audit_log(
        response_uuid=response.uuid,
        actor_user_uuid=actor_uuid,
        action="review",
        changes={"status": {"old": old_status, "new": "in_review"}, "note": body.note},
    )

    # Trigger Async Tasks
    trigger_async_actions(response.uuid, "reviewed")

    return to_json_ready(to_form_response_output(response))


@resources_api.post(
    "/projects/<project_uuid>/forms/<form_uuid>/responses/<response_uuid>/approve",
    tags=[resources_tag],
    responses={200: FormResponseOutput, 400: ErrorResponse, 404: ErrorResponse},
)
def approve_form_response(
    path: ResponseActionExecutionPath, body: WorkflowActionRequest
):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    response = FormResponse.objects(
        uuid=path.response_uuid, form_uuid=form.uuid, status__ne="deleted"
    ).first()
    if not response:
        return _error("Form response not found", 404)

    from datetime import datetime, timezone
    from app.services.response_management import (
        write_response_audit_log,
        trigger_async_actions,
    )

    user = getattr(g, "resources_user", None)
    actor_uuid = getattr(user, "uuid", None)
    old_status = response.status

    response.status = "approved"
    response.approved_at = datetime.now(timezone.utc)
    if user and user not in response.approved_by:
        response.approved_by = list(response.approved_by or [])
        response.approved_by.append(user)

    event = FormResponseStatusEvent(
        transition_from=old_status,
        transition_to="approved",
        changed_at=response.approved_at,
        reason=body.note or "approved_by_user",
    )
    response.status_history = list(response.status_history or [])
    response.status_history.append(event)
    response.save()

    # Log Audit
    write_response_audit_log(
        response_uuid=response.uuid,
        actor_user_uuid=actor_uuid,
        action="approve",
        changes={"status": {"old": old_status, "new": "approved"}, "note": body.note},
    )

    # Trigger Async Tasks
    trigger_async_actions(response.uuid, "approved")

    return to_json_ready(to_form_response_output(response))


@resources_api.post(
    "/projects/<project_uuid>/forms/<form_uuid>/responses/<response_uuid>/reject",
    tags=[resources_tag],
    responses={200: FormResponseOutput, 400: ErrorResponse, 404: ErrorResponse},
)
def reject_form_response(
    path: ResponseActionExecutionPath, body: WorkflowActionRequest
):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    response = FormResponse.objects(
        uuid=path.response_uuid, form_uuid=form.uuid, status__ne="deleted"
    ).first()
    if not response:
        return _error("Form response not found", 404)

    from datetime import datetime, timezone
    from app.services.response_management import (
        write_response_audit_log,
        trigger_async_actions,
    )

    actor_uuid = getattr(g.resources_user, "uuid", None)
    old_status = response.status

    response.status = "rejected"
    event = FormResponseStatusEvent(
        transition_from=old_status,
        transition_to="rejected",
        changed_at=datetime.now(timezone.utc),
        reason=body.note or "rejected_by_user",
    )
    response.status_history = list(response.status_history or [])
    response.status_history.append(event)
    response.save()

    # Log Audit
    write_response_audit_log(
        response_uuid=response.uuid,
        actor_user_uuid=actor_uuid,
        action="reject",
        changes={"status": {"old": old_status, "new": "rejected"}, "note": body.note},
    )

    # Trigger Async Tasks
    trigger_async_actions(response.uuid, "rejected")

    return to_json_ready(to_form_response_output(response))


@resources_api.put(
    "/projects/<project_uuid>/forms/<form_uuid>/responses/<response_uuid>/reviewers",
    tags=[resources_tag],
    responses={200: FormResponseOutput, 400: ErrorResponse, 404: ErrorResponse},
)
def assign_form_response_reviewers(
    path: ResponseActionExecutionPath, body: AssignReviewersRequest
):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    response = FormResponse.objects(
        uuid=path.response_uuid, form_uuid=form.uuid, status__ne="deleted"
    ).first()
    if not response:
        return _error("Form response not found", 404)

    users = []
    for uuid in body.reviewer_uuids:
        user = User.objects(uuid=uuid).first()
        if not user:
            return _error(f"User with UUID {uuid} not found", 404)
        users.append(user)

    response.reviewed_by = users
    response.save()
    return to_json_ready(to_form_response_output(response))


@resources_api.put(
    "/projects/<project_uuid>/forms/<form_uuid>/responses/<response_uuid>/approvers",
    tags=[resources_tag],
    responses={200: FormResponseOutput, 400: ErrorResponse, 404: ErrorResponse},
)
def assign_form_response_approvers(
    path: ResponseActionExecutionPath, body: AssignApproversRequest
):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    response = FormResponse.objects(
        uuid=path.response_uuid, form_uuid=form.uuid, status__ne="deleted"
    ).first()
    if not response:
        return _error("Form response not found", 404)

    users = []
    for uuid in body.approver_uuids:
        user = User.objects(uuid=uuid).first()
        if not user:
            return _error(f"User with UUID {uuid} not found", 404)
        users.append(user)

    response.approved_by = users
    response.save()
    return to_json_ready(to_form_response_output(response))


@resources_api.get(
    "/projects/<project_uuid>/forms/<form_uuid>/responses/export",
    tags=[resources_tag],
)
def export_form_responses(path: FormResponseSubmissionPath):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err

    from flask import Response
    from app.services.response_management import export_responses_to_csv

    csv_data = export_responses_to_csv(form.uuid)
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={
            "Content-disposition": f"attachment; filename=responses-{form.uuid}.csv"
        },
    )


@resources_api.get(
    "/projects/<project_uuid>/forms/<form_uuid>/responses/analytics",
    tags=[resources_tag],
)
def get_form_responses_analytics(path: FormResponseSubmissionPath):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err

    from app.services.response_management import get_response_analytics

    analytics = get_response_analytics(form.uuid)
    return to_json_ready(analytics)
