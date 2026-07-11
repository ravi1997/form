from __future__ import annotations

from typing import Optional

from mongoengine.errors import ValidationError

from app.api.resources_support import _error
from app.api.resources_context import _get_form_for_project, _get_project_or_error
from app.models.form import FormResponse, ResponseItem
from app.models.user import User
from app.schemas.form_response import FormResponseCreateInput
from app.schemas.mappers import to_form_response_output, to_json_ready


def create_form_response(
    *,
    project_uuid: str,
    form_uuid: str,
    body: FormResponseCreateInput,
    submitted_by: Optional[User],
    public_only: bool = False,
):
    project, project_err = _get_project_or_error(project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, form_uuid)
    if form_err:
        return form_err
    if public_only and not getattr(form, "is_public", False):
        return _error("Public submission is disabled for this form", 403)
    if body.form_uuid != form_uuid:
        return _error("form_uuid does not match request path", 400)
    if body.project_uuid and body.project_uuid != project_uuid:
        return _error("project_uuid does not match request path", 400)
    if not form.versions:
        return _error("Form has no versions", 400)
    if body.form_version_uuid not in {version.uuid for version in form.versions or []}:
        return _error("form_version_uuid does not match a known form version", 400)

    try:
        response_items = [ResponseItem(**item.model_dump()) for item in body.responses]
        response = FormResponse(
            uuid=body.uuid,
            form=form,
            form_uuid=form.uuid,
            form_version_uuid=body.form_version_uuid,
            project=project,
            project_uuid=project.uuid,
            organization_uuid=body.organization_uuid,
            submitted_by=submitted_by,
            submitted_by_uuid=getattr(submitted_by, "uuid", None),
            status="submitted",
            responses=response_items,
            response_map=body.response_map,
            score=body.score,
            validation_errors=body.validation_errors,
            reviewed_by=[],
            approved_by=[],
            metadata=body.metadata,
        ).save()
    except (ValidationError, ValueError) as exc:
        return _error(str(exc))

    return to_json_ready(to_form_response_output(response)), 201
