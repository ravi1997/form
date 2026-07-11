from __future__ import annotations

import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import Optional
from datetime import datetime

from flask import current_app, request
from mongoengine.queryset.visitor import Q

from app.models.auth import SessionAuditLog, UserSession
from app.config import BaseConfig
from app.api.auth_support import (
    _audit_log,
    _bad_request,
    _decode_audit_cursor,
    _encode_audit_cursor,
    _require_admin,
    _require_admin_for_user,
    _security_event,
    _unauthorized,
    _resolve_access_identity,
    auth_api,
    auth_tag,
)
from werkzeug.security import generate_password_hash
from app.models.user import User, Organization
from app.utils import utcnow
from app.schemas.user import UserCreateInput, UserUpdateInput, UserOutput, VerifyUserInput
from app.api.resources_schemas import UserListResponse, MessageResponse
from app.utils import client_ip
from app.schemas.auth import (
    AdminAuditLogEntry,
    AdminAuditLogListResponse,
    AdminAuditLogQuery,
    AdminAuditLogSearchQuery,
    AdminBulkMustChangePasswordRequest,
    AdminBulkMustChangePasswordResponse,
    AdminConfigHealthResponse,
    AdminRevokeAllSessionsResponse,
    AdminRevokeSessionRequest,
    AdminRevokeSessionResponse,
    AdminUserPath,
    AuthorizationHeader,
    ErrorResponse,
    SessionInfo,
    SessionListQuery,
    SessionListResponse,
)
from app.schemas.mappers import to_json_ready
from app.services.auth import (
    AuthError,
    revoke_all_sessions,
    revoke_session,
    touch_session,
)
from app.services.org_keys import resolve_org_role_key
from app.services.rbac import admin_org_ids_for_user, can_admin_access_user


def _encode_composite_cursor(*, timestamp: datetime, tie_breaker: str) -> str:
    payload = json.dumps(
        {"timestamp": timestamp.isoformat(), "tie_breaker": tie_breaker},
        separators=(",", ":"),
    ).encode("utf-8")
    return urlsafe_b64encode(payload).decode("utf-8")


def _decode_composite_cursor(cursor: str) -> tuple[datetime, str | None]:
    raw = urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return datetime.fromisoformat(raw), None
    return datetime.fromisoformat(payload["timestamp"]), payload.get("tie_breaker")


def _build_session_list_response(
    all_items: list,
    page: int,
    page_size: int,
    cursor: Optional[str],
    current_session_uuid: Optional[str],
    total_items: Optional[int] = None,
    total_pages: Optional[int] = None,
) -> SessionListResponse:
    next_cursor: Optional[str] = None

    if cursor:
        cursor_created_at, cursor_session_uuid = _decode_composite_cursor(cursor)
        filtered = [
            s
            for s in all_items
            if (
                s.last_seen_at < cursor_created_at
                or (
                    cursor_session_uuid is not None
                    and s.last_seen_at == cursor_created_at
                    and s.session_uuid < cursor_session_uuid
                )
            )
        ]
        selected = filtered[:page_size]
    else:
        total_items = len(all_items) if total_items is None else total_items
        total_pages = (
            (total_items + page_size - 1) // page_size if total_pages is None and total_items else total_pages
        )
        start = (page - 1) * page_size
        selected = all_items[start : start + page_size]

    items = [
        SessionInfo(
            session_uuid=session.session_uuid,
            device_name=session.device_name,
            user_agent=session.user_agent,
            ip_address=session.ip_address,
            created_at=session.created_at,
            last_seen_at=session.last_seen_at,
            is_current=bool(
                current_session_uuid and session.session_uuid == current_session_uuid
            ),
        )
        for session in selected
    ]

    if len(selected) == page_size:
        next_cursor = _encode_composite_cursor(
            timestamp=selected[-1].last_seen_at,
            tie_breaker=selected[-1].session_uuid,
        )

    return SessionListResponse(
        sessions=items,
        page=page,
        page_size=page_size,
        total_items=total_items,
        total_pages=total_pages,
        next_cursor=next_cursor,
    )


def _fetch_session_page(
    user_uuid: str,
    page: int,
    page_size: int,
    cursor: Optional[str],
):
    queryset = UserSession.objects(user_uuid=user_uuid, is_active=True).order_by(
        "-last_seen_at"
    )
    if cursor:
        cursor_created_at = _decode_audit_cursor(cursor)
        entries = list(
            queryset.filter(last_seen_at__lt=cursor_created_at).limit(page_size + 1)
        )
        total_items = None
        total_pages = None
    else:
        total_items = queryset.count()
        total_pages = (total_items + page_size - 1) // page_size if total_items else 0
        skip = (page - 1) * page_size
        entries = list(queryset.skip(skip).limit(page_size + 1))
    return entries, total_items, total_pages


def _build_audit_log_response(
    entries: list,
    page: int,
    page_size: int,
    total_items: Optional[int],
    total_pages: Optional[int],
) -> AdminAuditLogListResponse:
    page_entries = entries[:page_size]
    items = [
        AdminAuditLogEntry(
            actor_user_uuid=entry.actor_user_uuid,
            target_user_uuid=entry.target_user_uuid,
            session_uuid=entry.session_uuid,
            action=entry.action,
            reason=entry.reason,
            ip_address=entry.ip_address,
            user_agent=entry.user_agent,
            metadata=dict(entry.metadata or {}),
            created_at=entry.created_at,
        )
        for entry in page_entries
    ]

    next_cursor = None
    if len(entries) > page_size and page_entries:
        next_cursor = _encode_audit_cursor(page_entries[-1].created_at)

    return AdminAuditLogListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total_items=total_items,
        total_pages=total_pages,
        next_cursor=next_cursor,
    )


def _resolve_users_by_uuid(user_uuids: list[str]) -> dict[str, User]:
    requested = [user_uuid for user_uuid in user_uuids if user_uuid]
    if not requested:
        return {}
    return {user.uuid: user for user in User.objects(uuid__in=requested)}


def _resolve_orgs_by_uuid(org_uuids: list[str]) -> dict[str, Organization]:
    requested = [org_uuid for org_uuid in org_uuids if org_uuid]
    if not requested:
        return {}
    return {org.uuid: org for org in Organization.objects(uuid__in=requested)}


@auth_api.get(
    "/admin/users/<user_uuid>/sessions",
    tags=[auth_tag],
    responses={200: SessionListResponse, 401: ErrorResponse},
)
def admin_list_user_sessions(
    header: AuthorizationHeader,
    path: AdminUserPath,
    query: SessionListQuery,
):
    try:
        payload, _admin_user, _target_user = _require_admin_for_user(
            header, path.user_uuid
        )
    except AuthError as exc:
        return _unauthorized(str(exc))

    touch_session(session_uuid=payload["sid"], user_uuid=payload["sub"])
    entries, total_items, total_pages = _fetch_session_page(
        user_uuid=path.user_uuid,
        page=query.page,
        page_size=query.page_size,
        cursor=query.cursor,
    )
    response = _build_session_list_response(
        all_items=entries,
        page=query.page,
        page_size=query.page_size,
        cursor=query.cursor,
        current_session_uuid=payload["sid"],
        total_items=total_items,
        total_pages=total_pages,
    )
    return to_json_ready(response)


@auth_api.post(
    "/admin/users/<user_uuid>/sessions/revoke",
    tags=[auth_tag],
    responses={200: AdminRevokeSessionResponse, 401: ErrorResponse, 400: ErrorResponse},
)
def admin_revoke_user_session(
    header: AuthorizationHeader,
    path: AdminUserPath,
    body: AdminRevokeSessionRequest,
):
    try:
        payload, _admin_user, _target_user = _require_admin_for_user(
            header, path.user_uuid
        )
    except AuthError as exc:
        return _unauthorized(str(exc))

    revoked = revoke_session(
        session_uuid=body.session_uuid,
        user_uuid=path.user_uuid,
        reason="admin_revoke",
    )
    if not revoked:
        _security_event(
            event="admin_session_revoke",
            outcome="failed",
            endpoint="/api/v1/auth/admin/users/<user_uuid>/sessions/revoke",
            actor_user_uuid=payload["sub"],
            target_user_uuid=path.user_uuid,
            reason="session_not_found",
            details={"session_uuid": body.session_uuid},
        )
        return _bad_request("Session not found or already inactive")

    _audit_log(
        actor_user_uuid=payload["sub"],
        target_user_uuid=path.user_uuid,
        session_uuid=body.session_uuid,
        action="admin_session_revoke",
        reason="admin_revoke",
        ip_address=client_ip(),
        user_agent=request.headers.get("User-Agent"),
        metadata={"endpoint": "/api/v1/auth/admin/users/<user_uuid>/sessions/revoke"},
    )
    _security_event(
        event="admin_session_revoke",
        outcome="success",
        endpoint="/api/v1/auth/admin/users/<user_uuid>/sessions/revoke",
        actor_user_uuid=payload["sub"],
        target_user_uuid=path.user_uuid,
        details={"session_uuid": body.session_uuid},
    )

    touch_session(session_uuid=payload["sid"], user_uuid=payload["sub"])
    return to_json_ready(AdminRevokeSessionResponse())


@auth_api.post(
    "/admin/users/<user_uuid>/sessions/revoke-all",
    tags=[auth_tag],
    responses={200: AdminRevokeAllSessionsResponse, 401: ErrorResponse},
)
def admin_revoke_all_user_sessions(header: AuthorizationHeader, path: AdminUserPath):
    try:
        payload, _admin_user, _target_user = _require_admin_for_user(
            header, path.user_uuid
        )
    except AuthError as exc:
        return _unauthorized(str(exc))

    revoked_count = revoke_all_sessions(
        user_uuid=path.user_uuid, reason="admin_revoke_all"
    )
    _audit_log(
        actor_user_uuid=payload["sub"],
        target_user_uuid=path.user_uuid,
        session_uuid=None,
        action="admin_sessions_revoke_all",
        reason="admin_revoke_all",
        ip_address=client_ip(),
        user_agent=request.headers.get("User-Agent"),
        metadata={
            "endpoint": "/api/v1/auth/admin/users/<user_uuid>/sessions/revoke-all",
            "revoked_count": revoked_count,
        },
    )
    _security_event(
        event="admin_sessions_revoke_all",
        outcome="success",
        endpoint="/api/v1/auth/admin/users/<user_uuid>/sessions/revoke-all",
        actor_user_uuid=payload["sub"],
        target_user_uuid=path.user_uuid,
        details={"revoked_count": revoked_count},
    )

    touch_session(session_uuid=payload["sid"], user_uuid=payload["sub"])
    return to_json_ready(AdminRevokeAllSessionsResponse(revoked_count=revoked_count))


@auth_api.get(
    "/admin/config/health",
    tags=[auth_tag],
    responses={200: AdminConfigHealthResponse, 401: ErrorResponse},
)
def admin_config_health(header: AuthorizationHeader):
    try:
        payload, _admin_user = _require_admin(header)
    except AuthError as exc:
        return _unauthorized(str(exc))

    touch_session(session_uuid=payload["sid"], user_uuid=payload["sub"])

    response = AdminConfigHealthResponse(
        api_version=BaseConfig.get_str(
            current_app.config, "API_VERSION", BaseConfig.API_VERSION
        ),
        env_name=BaseConfig.get_str(current_app.config, "ENV_NAME", "development"),
        debug=BaseConfig.get_bool(current_app.config, "DEBUG", False),
        jwt_algorithm=BaseConfig.get_str(
            current_app.config,
            "JWT_ALGORITHM",
            BaseConfig.JWT_ALGORITHM,
        ),
        jwt_active_kid=BaseConfig.get_str(
            current_app.config,
            "JWT_ACTIVE_KID",
            BaseConfig.JWT_ACTIVE_KID,
        ),
        jwt_additional_key_ids=sorted(
            list((current_app.config.get("JWT_ADDITIONAL_KEYS") or {}).keys())
        ),
        jwt_access_token_expires_minutes=BaseConfig.get_int(
            current_app.config,
            "JWT_ACCESS_TOKEN_EXPIRES_MINUTES",
            BaseConfig.JWT_ACCESS_TOKEN_EXPIRES_MINUTES,
        ),
        jwt_refresh_token_expires_days=BaseConfig.get_int(
            current_app.config,
            "JWT_REFRESH_TOKEN_EXPIRES_DAYS",
            BaseConfig.JWT_REFRESH_TOKEN_EXPIRES_DAYS,
        ),
        auth_rate_limit_login_max=BaseConfig.get_int(
            current_app.config,
            "AUTH_RATE_LIMIT_LOGIN_MAX",
            BaseConfig.AUTH_RATE_LIMIT_LOGIN_MAX,
        ),
        auth_rate_limit_login_window_seconds=BaseConfig.get_int(
            current_app.config,
            "AUTH_RATE_LIMIT_LOGIN_WINDOW_SECONDS",
            BaseConfig.AUTH_RATE_LIMIT_LOGIN_WINDOW_SECONDS,
        ),
        auth_rate_limit_refresh_max=BaseConfig.get_int(
            current_app.config,
            "AUTH_RATE_LIMIT_REFRESH_MAX",
            BaseConfig.AUTH_RATE_LIMIT_REFRESH_MAX,
        ),
        auth_rate_limit_refresh_window_seconds=BaseConfig.get_int(
            current_app.config,
            "AUTH_RATE_LIMIT_REFRESH_WINDOW_SECONDS",
            BaseConfig.AUTH_RATE_LIMIT_REFRESH_WINDOW_SECONDS,
        ),
        auth_rate_limit_logout_max=BaseConfig.get_int(
            current_app.config,
            "AUTH_RATE_LIMIT_LOGOUT_MAX",
            BaseConfig.AUTH_RATE_LIMIT_LOGOUT_MAX,
        ),
        auth_rate_limit_logout_window_seconds=BaseConfig.get_int(
            current_app.config,
            "AUTH_RATE_LIMIT_LOGOUT_WINDOW_SECONDS",
            BaseConfig.AUTH_RATE_LIMIT_LOGOUT_WINDOW_SECONDS,
        ),
        resource_rate_limit_max=BaseConfig.get_int(
            current_app.config,
            "RESOURCE_RATE_LIMIT_MAX",
            BaseConfig.RESOURCE_RATE_LIMIT_MAX,
        ),
        resource_rate_limit_window_seconds=BaseConfig.get_int(
            current_app.config,
            "RESOURCE_RATE_LIMIT_WINDOW_SECONDS",
            BaseConfig.RESOURCE_RATE_LIMIT_WINDOW_SECONDS,
        ),
        resource_rbac_require_org_role_alignment=BaseConfig.get_bool(
            current_app.config,
            "RESOURCE_RBAC_REQUIRE_ORG_ROLE_ALIGNMENT",
            BaseConfig.RESOURCE_RBAC_REQUIRE_ORG_ROLE_ALIGNMENT,
        ),
        workflow_strict_review_before_approve=BaseConfig.get_bool(
            current_app.config,
            "WORKFLOW_STRICT_REVIEW_BEFORE_APPROVE",
            BaseConfig.WORKFLOW_STRICT_REVIEW_BEFORE_APPROVE,
        ),
        enable_audit_logs=BaseConfig.get_bool(
            current_app.config,
            "ENABLE_AUDIT_LOGS",
            BaseConfig.ENABLE_AUDIT_LOGS,
        ),
        audit_log_retention_days=BaseConfig.get_int(
            current_app.config,
            "AUDIT_LOG_RETENTION_DAYS",
            BaseConfig.AUDIT_LOG_RETENTION_DAYS,
        ),
        request_id_header=BaseConfig.get_str(
            current_app.config,
            "REQUEST_ID_HEADER",
            BaseConfig.REQUEST_ID_HEADER,
        ),
    )

    _security_event(
        event="admin_config_health",
        outcome="success",
        endpoint="/api/v1/auth/admin/config/health",
        actor_user_uuid=payload["sub"],
    )
    return to_json_ready(response)


@auth_api.get(
    "/admin/audit-logs",
    tags=[auth_tag],
    responses={200: AdminAuditLogListResponse, 401: ErrorResponse},
)
def admin_audit_logs(header: AuthorizationHeader, query: AdminAuditLogQuery):
    try:
        payload, _admin_user = _require_admin(header)
    except AuthError as exc:
        return _unauthorized(str(exc))

    touch_session(session_uuid=payload["sid"], user_uuid=payload["sub"])

    filters = {}
    if query.actor_user_uuid:
        filters["actor_user_uuid"] = query.actor_user_uuid
    if query.target_user_uuid:
        filters["target_user_uuid"] = query.target_user_uuid
    if query.session_uuid:
        filters["session_uuid"] = query.session_uuid
    if query.action:
        filters["action"] = query.action
    if query.start_at:
        filters["created_at__gte"] = query.start_at
    if query.end_at:
        filters["created_at__lte"] = query.end_at

    total_items: Optional[int] = None
    total_pages: Optional[int] = None
    if query.cursor:
        cursor_created_at, cursor_session_uuid = _decode_composite_cursor(query.cursor)
        queryset = SessionAuditLog.objects(**filters).order_by("-created_at", "-session_uuid")
        if cursor_session_uuid is None:
            queryset = queryset.filter(created_at__lt=cursor_created_at)
        else:
            queryset = queryset.filter(
                Q(created_at__lt=cursor_created_at)
                | Q(created_at=cursor_created_at, session_uuid__lt=cursor_session_uuid)
            )
        entries = list(queryset.limit(query.page_size + 1))
    else:
        queryset = SessionAuditLog.objects(**filters).order_by("-created_at", "-session_uuid")
        total_items = queryset.count()
        total_pages = (
            (total_items + query.page_size - 1) // query.page_size if total_items else 0
        )
        skip = (query.page - 1) * query.page_size
        entries = list(queryset.skip(skip).limit(query.page_size + 1))

    response = _build_audit_log_response(
        entries=entries,
        page=query.page,
        page_size=query.page_size,
        total_items=total_items,
        total_pages=total_pages,
    )
    _security_event(
        event="admin_audit_logs",
        outcome="success",
        endpoint="/api/v1/auth/admin/audit-logs",
        actor_user_uuid=payload["sub"],
        details={
            "page": query.page,
            "page_size": query.page_size,
            "used_cursor": bool(query.cursor),
            "returned_items": len(response.items),
        },
    )
    return to_json_ready(response)


@auth_api.get(
    "/admin/audit-logs/search",
    tags=[auth_tag],
    responses={200: AdminAuditLogListResponse, 401: ErrorResponse},
)
def admin_audit_logs_search(
    header: AuthorizationHeader, query: AdminAuditLogSearchQuery
):
    try:
        payload, _admin_user = _require_admin(header)
    except AuthError as exc:
        return _unauthorized(str(exc))

    touch_session(session_uuid=payload["sid"], user_uuid=payload["sub"])

    base_filter = Q()
    if query.action:
        base_filter &= Q(action=query.action)
    if query.start_at:
        base_filter &= Q(created_at__gte=query.start_at)
    if query.end_at:
        base_filter &= Q(created_at__lte=query.end_at)
    if query.user_uuid:
        base_filter &= Q(actor_user_uuid=query.user_uuid) | Q(
            target_user_uuid=query.user_uuid
        )

    total_items: Optional[int] = None
    total_pages: Optional[int] = None
    if query.cursor:
        cursor_created_at, cursor_session_uuid = _decode_composite_cursor(query.cursor)
        if cursor_session_uuid is None:
            queryset = SessionAuditLog.objects(
                base_filter & Q(created_at__lt=cursor_created_at)
            ).order_by("-created_at", "-session_uuid")
        else:
            queryset = SessionAuditLog.objects(
                base_filter
                & (
                    Q(created_at__lt=cursor_created_at)
                    | Q(created_at=cursor_created_at, session_uuid__lt=cursor_session_uuid)
                )
            ).order_by("-created_at", "-session_uuid")
        entries = list(queryset.limit(query.page_size + 1))
    else:
        queryset = SessionAuditLog.objects(base_filter).order_by("-created_at", "-session_uuid")
        total_items = queryset.count()
        total_pages = (
            (total_items + query.page_size - 1) // query.page_size if total_items else 0
        )
        skip = (query.page - 1) * query.page_size
        entries = list(queryset.skip(skip).limit(query.page_size + 1))

    response = _build_audit_log_response(
        entries=entries,
        page=query.page,
        page_size=query.page_size,
        total_items=total_items,
        total_pages=total_pages,
    )
    _security_event(
        event="admin_audit_logs_search",
        outcome="success",
        endpoint="/api/v1/auth/admin/audit-logs/search",
        actor_user_uuid=payload["sub"],
        details={
            "page": query.page,
            "page_size": query.page_size,
            "used_cursor": bool(query.cursor),
            "returned_items": len(response.items),
            "has_user_filter": bool(query.user_uuid),
            "has_action_filter": bool(query.action),
            "has_date_filter": bool(query.start_at or query.end_at),
        },
    )
    return to_json_ready(response)


def _resolve_and_require_elevated_admin(header: AuthorizationHeader):
    from app.services.rbac import require_admin_by_payload
    payload = _resolve_access_identity(header)
    return require_admin_by_payload(payload)


@auth_api.get(
    "/admin/users",
    tags=[auth_tag],
    responses={200: UserListResponse, 401: ErrorResponse, 403: ErrorResponse},
)
def admin_list_users(header: AuthorizationHeader, query: SessionListQuery):
    try:
        payload, admin_user = _resolve_and_require_elevated_admin(header)
    except AuthError as exc:
        return _unauthorized(str(exc))

    touch_session(session_uuid=payload["sid"], user_uuid=payload["sub"])

    if admin_user.is_super_admin:
        qs = User.objects
    else:
        # Organization admin can see only users of organizations they manage
        admin_org_ids = admin_org_ids_for_user(admin_user)
        # Resolve to database Organization references to filter
        resolved_orgs = list(Organization.objects(id__in=admin_org_ids))
        qs = User.objects(organizations__in=list(resolved_orgs))

    total_items = qs.count()
    total_pages = (total_items + query.page_size - 1) // query.page_size if total_items else 0
    skip = (query.page - 1) * query.page_size
    items = list(qs.skip(skip).limit(query.page_size))

    from app.schemas.mappers import to_user_output
    response = UserListResponse(
        items=[to_user_output(item) for item in items],
        page=query.page,
        page_size=query.page_size,
        total_items=total_items,
        total_pages=total_pages,
    )
    return to_json_ready(response)


@auth_api.post(
    "/admin/users",
    tags=[auth_tag],
    responses={201: UserOutput, 400: ErrorResponse, 401: ErrorResponse, 403: ErrorResponse},
)
def admin_create_user(header: AuthorizationHeader, body: UserCreateInput):
    try:
        payload, admin_user = _resolve_and_require_elevated_admin(header)
    except AuthError as exc:
        return _unauthorized(str(exc))

    touch_session(session_uuid=payload["sid"], user_uuid=payload["sub"])

    if not admin_user.is_super_admin:
        admin_org_ids = admin_org_ids_for_user(admin_user)
        org_lookup = _resolve_orgs_by_uuid(body.organizations)
        for org_uuid in body.organizations:
            org = org_lookup.get(org_uuid)
            if not org or resolve_org_role_key(org) not in admin_org_ids:
                return _unauthorized(f"You cannot create users in organization: {org_uuid}")

    # Determine status: org admin created by super admin -> verified/active by default
    status = "unverified"
    is_email_verified = False
    if admin_user.is_super_admin and (body.is_organisation_admin or any("admin" in roles for roles in body.roles.values())):
        status = "active"
        is_email_verified = True

    try:
        org_lookup = _resolve_orgs_by_uuid(body.organizations or [])
        resolved_orgs = []
        for org_uuid in body.organizations or []:
            org = org_lookup.get(org_uuid)
            if not org:
                return _bad_request(f"Organization not found: {org_uuid}")
            resolved_orgs.append(org)

        mapped_roles = {}
        role_org_lookup = _resolve_orgs_by_uuid(list(body.roles.keys()))
        for k, v in body.roles.items():
            org = role_org_lookup.get(k) or Organization.objects(id=k).first()
            if org:
                mapped_roles[resolve_org_role_key(org)] = v
            else:
                mapped_roles[k] = v

        user = User(
            uuid=body.uuid,
            name=body.name,
            designation=body.designation,
            email=body.email.strip().lower(),
            phone=body.phone,
            organizations=resolved_orgs,
            roles=mapped_roles,
            status=status,
            auth_provider=body.auth_provider,
            password_hash=body.password_hash or generate_password_hash("TempPass123!"),
            is_email_verified=is_email_verified,
            is_organisation_admin=body.is_organisation_admin,
            is_super_admin=body.is_super_admin,
            must_change_password=bool(body.must_change_password),
            last_password_change_at=utcnow(),
        )
        user.save()
    except Exception as exc:
        current_app.logger.exception("Failed to create user")
        return _bad_request(str(exc))

    from app.schemas.mappers import to_user_output
    return to_json_ready(to_user_output(user)), 201


@auth_api.get(
    "/admin/users/<user_uuid>",
    tags=[auth_tag],
    responses={200: UserOutput, 401: ErrorResponse, 403: ErrorResponse, 404: ErrorResponse},
)
def admin_get_user(header: AuthorizationHeader, path: AdminUserPath):
    try:
        payload, admin_user = _resolve_and_require_elevated_admin(header)
    except AuthError as exc:
        return _unauthorized(str(exc))

    touch_session(session_uuid=payload["sid"], user_uuid=payload["sub"])

    target_user = _resolve_users_by_uuid([path.user_uuid]).get(path.user_uuid)
    if not target_user:
        return _bad_request("User not found")

    if not can_admin_access_user(admin_user, target_user):
        return _unauthorized("You are not authorized to view this user")

    from app.schemas.mappers import to_user_output
    return to_json_ready(to_user_output(target_user))


@auth_api.patch(
    "/admin/users/<user_uuid>",
    tags=[auth_tag],
    responses={200: UserOutput, 400: ErrorResponse, 401: ErrorResponse, 403: ErrorResponse, 404: ErrorResponse},
)
def admin_update_user(header: AuthorizationHeader, path: AdminUserPath, body: UserUpdateInput):
    try:
        payload, admin_user = _resolve_and_require_elevated_admin(header)
    except AuthError as exc:
        return _unauthorized(str(exc))

    touch_session(session_uuid=payload["sid"], user_uuid=payload["sub"])

    target_user = _resolve_users_by_uuid([path.user_uuid]).get(path.user_uuid)
    if not target_user:
        return _bad_request("User not found")

    if not can_admin_access_user(admin_user, target_user):
        return _unauthorized("You are not authorized to update this user")

    try:
        if body.name is not None:
            target_user.name = body.name
        if body.designation is not None:
            target_user.designation = body.designation
        if body.email is not None:
            target_user.email = body.email.strip().lower()
        if body.phone is not None:
            target_user.phone = body.phone
        if body.organizations is not None:
            resolved_orgs = []
            for org_uuid in body.organizations:
                org = Organization.objects(uuid=org_uuid).first()
                if not org:
                    return _bad_request(f"Organization not found: {org_uuid}")
                resolved_orgs.append(org)
            target_user.organizations = resolved_orgs
        if body.roles is not None:
            mapped_roles = {}
            for k, v in body.roles.items():
                org = Organization.objects(uuid=k).first() or Organization.objects(id=k).first()
                if org:
                    mapped_roles[resolve_org_role_key(org)] = v
                else:
                    mapped_roles[k] = v
            target_user.roles = mapped_roles
        if body.status is not None:
            target_user.status = body.status
        if body.auth_provider is not None:
            target_user.auth_provider = body.auth_provider
        if body.is_email_verified is not None:
            target_user.is_email_verified = body.is_email_verified
        if body.is_phone_verified is not None:
            target_user.is_phone_verified = body.is_phone_verified
        if body.is_organisation_admin is not None:
            target_user.is_organisation_admin = body.is_organisation_admin
        if body.is_super_admin is not None:
            target_user.is_super_admin = body.is_super_admin
        if body.is_mfa_enabled is not None:
            target_user.is_mfa_enabled = body.is_mfa_enabled
        if body.must_change_password is not None:
            target_user.must_change_password = body.must_change_password
        if body.verified_at is not None:
            target_user.verified_at = body.verified_at
        if body.verified_by is not None:
            target_user.verified_by = body.verified_by
        if body.deleted_at is not None:
            target_user.deleted_at = body.deleted_at
        if body.deleted_by is not None:
            target_user.deleted_by = body.deleted_by

        target_user.save()
    except (ValidationError, NotUniqueError, ValueError) as exc:
        return _bad_request(str(exc))

    from app.schemas.mappers import to_user_output
    return to_json_ready(to_user_output(target_user))


@auth_api.post(
    "/admin/users/bulk/must-change-password",
    tags=[auth_tag],
    responses={
        200: AdminBulkMustChangePasswordResponse,
        400: ErrorResponse,
        401: ErrorResponse,
        403: ErrorResponse,
    },
)
def admin_bulk_set_must_change_password(
    header: AuthorizationHeader, body: AdminBulkMustChangePasswordRequest
):
    try:
        payload, admin_user = _resolve_and_require_elevated_admin(header)
    except AuthError as exc:
        return _unauthorized(str(exc))

    touch_session(session_uuid=payload["sid"], user_uuid=payload["sub"])

    if body.must_change_password is not True:
        return _bad_request("This bulk route only supports enabling must_change_password")

    updated_count = 0
    for user_uuid in body.user_uuids:
        target_user = _resolve_users_by_uuid([user_uuid]).get(user_uuid)
        if not target_user:
            return _bad_request(f"User not found: {user_uuid}")
        if not admin_user.is_super_admin:
            if not can_admin_access_user(admin_user, target_user):
                return _unauthorized(
                    f"You are not authorized to update this user: {user_uuid}"
                )
        if not bool(getattr(target_user, "must_change_password", False)):
            target_user.must_change_password = True
            target_user.save()
            updated_count += 1

    return to_json_ready(
        AdminBulkMustChangePasswordResponse(updated_count=updated_count)
    )


@auth_api.delete(
    "/admin/users/<user_uuid>",
    tags=[auth_tag],
    responses={200: MessageResponse, 401: ErrorResponse, 403: ErrorResponse, 404: ErrorResponse},
)
def admin_delete_user(header: AuthorizationHeader, path: AdminUserPath):
    try:
        payload, admin_user = _resolve_and_require_elevated_admin(header)
    except AuthError as exc:
        return _unauthorized(str(exc))

    touch_session(session_uuid=payload["sid"], user_uuid=payload["sub"])

    target_user = _resolve_users_by_uuid([path.user_uuid]).get(path.user_uuid)
    if not target_user:
        return _bad_request("User not found")

    if not can_admin_access_user(admin_user, target_user):
        return _unauthorized("You are not authorized to delete this user")

    target_user.status = "deleted"
    target_user.deleted_at = utcnow()
    target_user.deleted_by = str(admin_user.uuid)
    target_user.save()

    return to_json_ready(MessageResponse(message="user_deleted"))


@auth_api.post(
    "/admin/users/<user_uuid>/verify",
    tags=[auth_tag],
    responses={200: UserOutput, 400: ErrorResponse, 401: ErrorResponse, 403: ErrorResponse, 404: ErrorResponse},
)
def admin_verify_user(header: AuthorizationHeader, path: AdminUserPath, body: VerifyUserInput):
    try:
        payload, admin_user = _resolve_and_require_elevated_admin(header)
    except AuthError as exc:
        return _unauthorized(str(exc))

    touch_session(session_uuid=payload["sid"], user_uuid=payload["sub"])

    target_user = _resolve_users_by_uuid([path.user_uuid]).get(path.user_uuid)
    if not target_user:
        return _bad_request("User not found")

    # Resolve target organization
    org = Organization.objects(uuid=body.organization_uuid).first()
    if not org:
        return _bad_request("Organization not found")

    # Check permission: caller must be superadmin or admin of the target organization
    if not admin_user.is_super_admin and resolve_org_role_key(org) not in admin_org_ids_for_user(admin_user):
        return _unauthorized("You are not authorized to verify users for this organization")

    # Enforce: only superadmins can assign "admin" role
    if "admin" in body.roles and not admin_user.is_super_admin:
        return _unauthorized("Only superadmins can manage organization administrators")

    # Associate with organization
    if org not in target_user.organizations:
        target_user.organizations.append(org)

    # Set roles
    if not target_user.roles:
        target_user.roles = {}
    target_user.roles[resolve_org_role_key(org)] = body.roles

    # Adjust flag and organization admin membership if admin role is assigned
    if "admin" in body.roles:
        target_user.is_organisation_admin = True
        if target_user not in org.admins:
            org.admins.append(target_user)
            org.save()

    target_user.status = "active"
    target_user.is_email_verified = True
    target_user.verified_at = utcnow()
    target_user.verified_by = str(admin_user.uuid)
    target_user.save()

    from app.schemas.mappers import to_user_output
    return to_json_ready(to_user_output(target_user))
