"""Section CRUD and version endpoints."""

from __future__ import annotations

from mongoengine.errors import NotUniqueError, ValidationError

from app.models.form import Condition, Section
from app.models.user import User
from app.schemas.mappers import to_json_ready, to_section_output, to_version_output
from app.schemas.section import SectionCreateInput, SectionOutput, SectionUpdateInput
from app.schemas.version import VersionCreateInput, VersionOutput, VersionUpdateInput
from app.api.resources_schemas import (
    ErrorResponse,
    FormPath,
    ListQuery,
    MessageResponse,
    SectionListResponse,
    SectionPath,
    SectionVersionPath,
    VersionLinkQuery,
)
from app.api.resources_support import _error, resources_api, resources_tag, version_tag
from app.api.resources_context import (
    _append_version,
    _apply_section_update,
    _form_section_uuids,
    _get_form_for_project,
    _get_project_or_error,
    _get_section_for_form,
    _resolve_refs,
    _resolve_version_key,
    _update_version,
    _version_from_create,
)
from app.api.resources_utils import paginate_queryset as _paginate_queryset


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
        version_key = _resolve_version_key(
            form.versions or [], form.sections or {}, query.version_uuid
        )
        section = Section(
            uuid=body.uuid,
            versions=[_version_from_create(v) for v in body.versions],
            questions=body.questions,
            add_button=body.add_button,
            is_repeatable=body.is_repeatable,
            repeatable_condition=(
                Condition.objects(uuid=body.repeatable_condition).first()
                if body.repeatable_condition
                else None
            ),
            check_repeat_on=body.check_repeat_on,
            min_repeatable_count=body.min_repeatable_count,
            max_repeatable_count=body.max_repeatable_count,
            title=body.title,
            description=body.description,
            isDeleted=body.isDeleted,
            deletedBy=(
                User.objects(uuid=body.deletedBy).first() if body.deletedBy else None
            ),
            deletedAt=body.deletedAt,
            deleted_at=body.deleted_at,
            deleted_by=(
                User.objects(uuid=body.deleted_by).first() if body.deleted_by else None
            ),
            visibility_condition=(
                Condition.objects(uuid=body.visibility_condition).first()
                if body.visibility_condition
                else None
            ),
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
    try:
        items, page, page_size, total_items, total_pages, next_cursor = (
            _paginate_queryset(qs, query)
        )
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
        form.sections[key] = [v for v in (values or []) if v != section.uuid]
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
