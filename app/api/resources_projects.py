"""Project CRUD and version endpoints."""

from __future__ import annotations

from flask import g
from mongoengine.errors import NotUniqueError, ValidationError

from app.models.form import Form, Project
from app.models.user import Organization, User
from app.schemas.mappers import to_json_ready, to_project_output, to_version_output
from app.schemas.project import ProjectCreateInput, ProjectOutput, ProjectUpdateInput
from app.schemas.version import VersionCreateInput, VersionOutput, VersionUpdateInput
from app.services.org_keys import resolve_org_role_keys
from app.services.rbac import has_global_admin_privileges
from app.api.resources_schemas import (
    ErrorResponse,
    ListQuery,
    MessageResponse,
    ProjectListResponse,
    UUIDPath,
    VersionPath,
)
from app.api.resources_support import _error, resources_api, resources_tag, version_tag
from app.api.resources_context import (
    _append_version,
    _apply_project_update,
    _resolve_refs,
    _update_version,
    _version_from_create,
)
from app.api.resources_utils import (
    _can_read_project,
    paginate_queryset_with_predicate as _paginate_queryset_with_predicate,
    validate_project_membership_role_alignment as _validate_project_membership_role_alignment,
)


def _creator_can_manage_all_organizations(creator: User, organizations: list[str]) -> bool:
    if creator.is_super_admin:
        return True
    if not organizations:
        return False

    for org_uuid in organizations:
        org = Organization.objects(uuid=org_uuid).first()
        if not org:
            return False
        org_role_keys = resolve_org_role_keys(org)
        has_permission = any(
            role in {"admin", "editor"}
            for org_key in org_role_keys
            for role in (creator.roles or {}).get(org_key, [])
        )
        if not has_permission:
            return False
    return True


def ensure_project_active(project: Project):
    if getattr(project, "status", None) == "deleted":
        return _error("Project not found", 404)
    return None


@resources_api.post(
    "/projects",
    tags=[resources_tag],
    responses={201: ProjectOutput, 400: ErrorResponse, 403: ErrorResponse},
)
def create_project(body: ProjectCreateInput):
    creator = getattr(g, "resources_user", None)
    if not creator:
        return _error("Unauthorized", 401)

    if not _creator_can_manage_all_organizations(creator, list(body.organizations or [])):
        return _error(
            "Forbidden: You must be an administrator or editor of every organization on the project",
            403,
        )

    try:
        admins_list = _resolve_refs(User, body.admins, "admin")
        # Automatically add the creator to project admins list if the project is organization-scoped
        if body.organizations and not creator.is_super_admin:
            if creator not in admins_list:
                admins_list.append(creator)

        project = Project(
            uuid=body.uuid,
            name=body.name,
            versions=[_version_from_create(v) for v in body.versions],
            admins=admins_list,
            members=_resolve_refs(User, body.members, "member"),
            viewers=_resolve_refs(User, body.viewers, "viewer"),
            forms=_resolve_refs(Form, body.forms, "form"),
            organizations=_resolve_refs(
                Organization, body.organizations, "organization"
            ),
            tags=body.tags,
            status=body.status,
        )
        _validate_project_membership_role_alignment(project)
        project.save()
    except (ValidationError, ValueError, NotUniqueError) as exc:
        return _error(str(exc))
    return to_json_ready(to_project_output(project)), 201


@resources_api.get(
    "/projects",
    tags=[resources_tag],
    responses={200: ProjectListResponse},
)
def list_projects(query: ListQuery):
    user = getattr(g, "resources_user", None)
    qs = Project.objects
    if query.status:
        qs = qs(status=query.status)
    try:
        items, page, page_size, total_items, total_pages, next_cursor = (
            _paginate_queryset_with_predicate(
                qs,
                query,
                lambda project: _can_read_project(
                    user, project, has_global_admin_privileges
                ),
            )
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


@resources_api.get(
    "/projects/<uuid>",
    tags=[resources_tag],
    responses={200: ProjectOutput, 404: ErrorResponse},
)
def get_project(path: UUIDPath):
    item = Project.objects(uuid=path.uuid).first()
    if not item:
        return _error("Project not found", 404)
    inactive_err = ensure_project_active(item)
    if inactive_err:
        return inactive_err
    return to_json_ready(to_project_output(item))


@resources_api.patch(
    "/projects/<uuid>",
    tags=[resources_tag],
    responses={200: ProjectOutput, 400: ErrorResponse, 404: ErrorResponse},
)
def update_project(path: UUIDPath, body: ProjectUpdateInput):
    item = Project.objects(uuid=path.uuid).first()
    if not item:
        return _error("Project not found", 404)
    inactive_err = ensure_project_active(item)
    if inactive_err:
        return inactive_err
    try:
        _apply_project_update(item, body)
        _validate_project_membership_role_alignment(item)
        item.save()
    except (ValidationError, ValueError, NotUniqueError) as exc:
        return _error(str(exc))
    return to_json_ready(to_project_output(item))


@resources_api.delete(
    "/projects/<uuid>",
    tags=[resources_tag],
    responses={200: MessageResponse, 404: ErrorResponse},
)
def delete_project(path: UUIDPath):
    item = Project.objects(uuid=path.uuid).first()
    if not item:
        return _error("Project not found", 404)
    inactive_err = ensure_project_active(item)
    if inactive_err:
        return inactive_err
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
    inactive_err = ensure_project_active(item)
    if inactive_err:
        return inactive_err
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
    inactive_err = ensure_project_active(item)
    if inactive_err:
        return inactive_err
    try:
        updated = _update_version(item, path.version_uuid, body)
        item.save()
    except (ValidationError, ValueError) as exc:
        if str(exc) == "Version not found":
            return _error(str(exc), 404)
        return _error(str(exc))
    return to_json_ready(to_version_output(updated))
