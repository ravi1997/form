from __future__ import annotations

from flask import g
from mongoengine.connection import get_db

from app.api.resources_schemas import (
    ErrorResponse,
    GlobalSearchQuery,
    GlobalSearchResponse,
    GlobalSearchResult,
)
from app.api.resources_support import _error, resources_api, resources_tag
from app.api.resources_utils import _can_read_project
from app.models.condition_management import ConditionEvaluationStat
from app.models.form import Condition, Form, FormResponse, Project
from app.models.user import Organization, User
from app.schemas.mappers import to_json_ready
from app.services.rbac import can_admin_access_user, has_global_admin_privileges


def _contains(value: object, query: str) -> bool:
    return query in str(value or "").lower()


def _append_result(
    results: list[GlobalSearchResult], result: GlobalSearchResult, limit: int
) -> None:
    if len(results) < limit:
        results.append(result)


def _visible_org_uuids(user: User | None) -> set[str]:
    if not user or user.is_super_admin:
        return set()
    return {
        str(org.uuid)
        for org in (user.organizations or [])
        if getattr(org, "uuid", None)
    }


def _document_value(document: object, key: str, default: object = None) -> object:
    if isinstance(document, dict):
        return document.get(key, default)
    return getattr(document, key, default)


def _document_matches(document: object, query: str, keys: tuple[str, ...]) -> bool:
    return any(_contains(_document_value(document, key), query) for key in keys)


def _raw_collection_documents(collection_name: str) -> list[dict]:
    db = get_db()
    if collection_name not in db.list_collection_names():
        return []
    return list(db[collection_name].find({}))


def _raw_collection_search(
    *,
    collection_name: str,
    kind: str,
    search_term: str,
    results: list[GlobalSearchResult],
    limit: int,
    user: User | None,
    title_keys: tuple[str, ...] = ("name", "title", "uuid"),
    subtitle_prefix: str | None = None,
    route_prefix: str | None = None,
    organization_keys: tuple[str, ...] = ("organization_uuid", "organization_id"),
    metadata_keys: tuple[str, ...] = (),
) -> None:
    visible_org_uuids = _visible_org_uuids(user)
    for document in _raw_collection_documents(collection_name):
        if len(results) >= limit:
            return
        if user and not user.is_super_admin:
            doc_org = next(
                (
                    str(_document_value(document, key))
                    for key in organization_keys
                    if _document_value(document, key)
                ),
                None,
            )
            if doc_org and doc_org not in visible_org_uuids:
                continue
        if not _document_matches(document, search_term, title_keys + metadata_keys):
            continue
        uuid = str(
            _document_value(document, "uuid") or _document_value(document, "_id") or ""
        )
        title = next(
            (
                str(_document_value(document, key))
                for key in title_keys
                if _document_value(document, key)
            ),
            uuid or kind.title(),
        )
        subtitle_value = _document_value(document, "status") or _document_value(
            document, "state"
        )
        subtitle = (
            f"{subtitle_prefix} · {subtitle_value}"
            if subtitle_prefix and subtitle_value
            else subtitle_prefix
        )
        route = f"{route_prefix}/{uuid}" if route_prefix and uuid else None
        metadata = {
            key: _document_value(document, key)
            for key in metadata_keys
            if _document_value(document, key) is not None
        }
        _append_result(
            results,
            GlobalSearchResult(
                kind=kind,
                uuid=uuid,
                title=title,
                subtitle=subtitle,
                organization_uuid=next(
                    (
                        str(_document_value(document, key))
                        for key in organization_keys
                        if _document_value(document, key)
                    ),
                    None,
                ),
                route=route,
                metadata=metadata,
            ),
            limit,
        )


@resources_api.get(
    "/search",
    tags=[resources_tag],
    responses={200: GlobalSearchResponse, 400: ErrorResponse},
)
def global_search(query: GlobalSearchQuery):
    user = getattr(g, "resources_user", None)
    search_term = query.q.strip().lower()
    if not search_term:
        return _error("Search query is required", 400)

    limit = max(1, min(int(query.limit or 20), 100))
    results: list[GlobalSearchResult] = []

    def add_project_result(project: Project) -> None:
        if user and not _can_read_project(user, project, has_global_admin_privileges):
            return
        _append_result(
            results,
            GlobalSearchResult(
                kind="project",
                uuid=str(project.uuid),
                title=str(project.name),
                subtitle=f"Project · {getattr(project, 'status', 'active')}",
                route=f"/api/v1/projects/{project.uuid}",
                metadata={"tags": list(project.tags or [])},
            ),
            limit,
        )

    for project in Project.objects(status__ne="deleted").order_by("name"):
        if _contains(project.name, search_term) or _contains(project.uuid, search_term):
            add_project_result(project)
        if len(results) >= limit:
            break

    if len(results) < limit:
        for form in Form.objects(status__ne="deleted").order_by("uuid"):
            project = (
                getattr(form, "project", None) or Project.objects(forms=form).first()
            )
            if (
                project
                and user
                and not _can_read_project(user, project, has_global_admin_privileges)
            ):
                continue
            if not (
                _contains(form.uuid, search_term)
                or _contains(form.workflow_state, search_term)
                or any(_contains(tag, search_term) for tag in (form.tags or []))
            ):
                continue
            _append_result(
                results,
                GlobalSearchResult(
                    kind="form",
                    uuid=str(form.uuid),
                    title=str(form.uuid),
                    subtitle=f"Form · {getattr(form, 'workflow_state', 'draft')}",
                    project_uuid=getattr(project, "uuid", None),
                    route=(
                        f"/api/v1/projects/{project.uuid}/forms/{form.uuid}"
                        if project
                        else f"/api/v1/forms/{form.uuid}"
                    ),
                    metadata={
                        "tags": list(form.tags or []),
                        "is_public": bool(getattr(form, "is_public", False)),
                    },
                ),
                limit,
            )

    if len(results) < limit:
        for organization in Organization.objects(status__ne="deleted").order_by("name"):
            if user and not user.is_super_admin:
                visible_org_uuids = {
                    str(org.uuid)
                    for org in (user.organizations or [])
                    if getattr(org, "uuid", None)
                }
                if str(organization.uuid) not in visible_org_uuids:
                    continue
            if not (
                _contains(organization.name, search_term)
                or _contains(organization.uuid, search_term)
            ):
                continue
            _append_result(
                results,
                GlobalSearchResult(
                    kind="organization",
                    uuid=str(organization.uuid),
                    title=str(organization.name),
                    subtitle=f"Organization · {getattr(organization, 'status', 'active')}",
                    organization_uuid=str(organization.uuid),
                    route=f"/api/v1/organizations/{organization.uuid}",
                ),
                limit,
            )

    if len(results) < limit and user:
        if user.is_super_admin or user.is_organisation_admin:
            user_qs = User.objects.order_by("name")
        else:
            user_qs = []

        for target_user in user_qs:
            if (
                not _contains(target_user.name, search_term)
                and not _contains(target_user.email, search_term)
                and not _contains(target_user.uuid, search_term)
            ):
                continue
            if user.is_super_admin:
                permitted = True
            elif user.is_organisation_admin:
                permitted = can_admin_access_user(user, target_user)
            else:
                permitted = False
            if not permitted:
                continue
            _append_result(
                results,
                GlobalSearchResult(
                    kind="user",
                    uuid=str(target_user.uuid),
                    title=str(target_user.name),
                    subtitle=str(target_user.email),
                    metadata={
                        "status": getattr(target_user, "status", "active"),
                        "roles": list((target_user.roles or {}).keys()),
                    },
                ),
                limit,
            )

    if len(results) < limit:
        for response in FormResponse.objects(status__ne="deleted").order_by(
            "-created_at"
        ):
            if user and not user.is_super_admin:
                if user.is_organisation_admin:
                    visible_org_uuids = {
                        str(org.uuid)
                        for org in (user.organizations or [])
                        if getattr(org, "uuid", None)
                    }
                    if (
                        response.organization_uuid
                        and response.organization_uuid not in visible_org_uuids
                    ):
                        continue
                else:
                    visible_org_uuids = {
                        str(org.uuid)
                        for org in (user.organizations or [])
                        if getattr(org, "uuid", None)
                    }
                    if (
                        response.organization_uuid
                        and response.organization_uuid not in visible_org_uuids
                    ):
                        continue
            if not (
                _contains(response.uuid, search_term)
                or _contains(response.status, search_term)
                or _contains(response.form_uuid, search_term)
            ):
                continue
            _append_result(
                results,
                GlobalSearchResult(
                    kind="response",
                    uuid=str(response.uuid),
                    title=str(response.uuid),
                    subtitle=f"Response · {response.status}",
                    organization_uuid=getattr(response, "organization_uuid", None),
                    project_uuid=getattr(response, "project_uuid", None),
                    form_uuid=getattr(response, "form_uuid", None),
                    route=(
                        f"/api/v1/projects/{response.project_uuid}/forms/{response.form_uuid}/responses/{response.uuid}"
                        if getattr(response, "project_uuid", None)
                        and getattr(response, "form_uuid", None)
                        else f"/api/v1/responses/{response.uuid}"
                    ),
                ),
                limit,
            )

    if len(results) < limit:
        for condition in Condition.objects(status__ne="deleted").order_by("uuid"):
            if not (
                _contains(condition.uuid, search_term)
                or _contains(condition.conditionType, search_term)
                or _contains(condition.operator, search_term)
                or _contains(condition.expression, search_term)
                or _contains(condition.description, search_term)
                or _contains(condition.approval_state, search_term)
            ):
                continue
            _append_result(
                results,
                GlobalSearchResult(
                    kind="analysis",
                    uuid=str(condition.uuid),
                    title=str(condition.uuid),
                    subtitle=f"Analysis · {getattr(condition, 'approval_state', 'draft')}",
                    route=f"/api/v1/conditions/{condition.uuid}",
                    metadata={
                        "condition_type": getattr(condition, "conditionType", None),
                        "operator": getattr(condition, "operator", None),
                    },
                ),
                limit,
            )

    if len(results) < limit:
        for stat in ConditionEvaluationStat.objects.order_by("-created_at"):
            if not (
                _contains(stat.condition_uuid, search_term)
                or _contains(stat.endpoint, search_term)
                or _contains(stat.operator, search_term)
                or _contains(stat.condition_type, search_term)
            ):
                continue
            _append_result(
                results,
                GlobalSearchResult(
                    kind="analytics",
                    uuid=f"{stat.condition_uuid}:{getattr(stat, 'created_at', '')}",
                    title=str(stat.condition_uuid),
                    subtitle=f"Analytics · {'matched' if stat.matched else 'unmatched'}",
                    route=f"/api/v1/conditions/{stat.condition_uuid}/monitoring",
                    metadata={
                        "matched": bool(stat.matched),
                        "duration_ms": float(stat.duration_ms or 0),
                        "endpoint": stat.endpoint,
                    },
                ),
                limit,
            )

    if len(results) < limit:
        _raw_collection_search(
            collection_name="dashboards",
            kind="dashboard",
            search_term=search_term,
            results=results,
            limit=limit,
            user=user,
            subtitle_prefix="Dashboard",
            route_prefix="/api/v1/dashboards",
            metadata_keys=("tags", "status"),
        )

    if len(results) < limit:
        _raw_collection_search(
            collection_name="analysis_definitions",
            kind="analytics",
            search_term=search_term,
            results=results,
            limit=limit,
            user=user,
            subtitle_prefix="Analytics",
            route_prefix="/api/v1/analytics",
            metadata_keys=("tags", "status"),
        )

    if len(results) < limit:
        _raw_collection_search(
            collection_name="audit_logs",
            kind="audit",
            search_term=search_term,
            results=results,
            limit=limit,
            user=user,
            subtitle_prefix="Audit",
            route_prefix="/api/v1/auth/admin/audit-logs",
            organization_keys=("organization_uuid", "organization_id"),
            metadata_keys=(
                "action",
                "resource_type",
                "resource_uuid",
                "message",
                "status",
            ),
        )

    if len(results) < limit:
        _raw_collection_search(
            collection_name="session_audit_logs",
            kind="activity",
            search_term=search_term,
            results=results,
            limit=limit,
            user=user,
            subtitle_prefix="Activity",
            route_prefix="/api/v1/auth/admin/audit-logs",
            metadata_keys=("action", "reason", "session_uuid"),
        )

    return to_json_ready(GlobalSearchResponse(items=results))
