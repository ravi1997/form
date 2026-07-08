from __future__ import annotations

from typing import Optional

from flask import current_app, request
from mongoengine.queryset.visitor import Q

from app.models.auth import SessionAuditLog
from app.config import BaseConfig
from app.api.auth_support import (
    _audit_log,
    _bad_request,
    _client_ip,
    _decode_audit_cursor,
    _encode_audit_cursor,
    _require_admin,
    _require_admin_for_user,
    _security_event,
    _unauthorized,
    auth_api,
    auth_tag,
)
from app.schemas.auth import (
    AdminAuditLogEntry,
    AdminAuditLogListResponse,
    AdminAuditLogQuery,
    AdminAuditLogSearchQuery,
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
    list_active_sessions,
    revoke_all_sessions,
    revoke_session,
    touch_session,
)


def _build_session_list_response(
    all_items: list,
    page: int,
    page_size: int,
    cursor: Optional[str],
    current_session_uuid: Optional[str],
) -> SessionListResponse:
    total_items: Optional[int] = None
    total_pages: Optional[int] = None
    next_cursor: Optional[str] = None

    if cursor:
        cursor_created_at = _decode_audit_cursor(cursor)
        filtered = [s for s in all_items if s.last_seen_at < cursor_created_at]
        selected = filtered[:page_size]
    else:
        total_items = len(all_items)
        total_pages = (total_items + page_size - 1) // page_size if total_items else 0
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
            is_current=bool(current_session_uuid and session.session_uuid == current_session_uuid),
        )
        for session in selected
    ]

    if len(selected) == page_size:
        next_cursor = _encode_audit_cursor(selected[-1].last_seen_at)

    return SessionListResponse(
        sessions=items,
        page=page,
        page_size=page_size,
        total_items=total_items,
        total_pages=total_pages,
        next_cursor=next_cursor,
    )


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
        payload, _admin_user, _target_user = _require_admin_for_user(header, path.user_uuid)
    except AuthError as exc:
        return _unauthorized(str(exc))

    touch_session(session_uuid=payload["sid"], user_uuid=payload["sub"])
    all_items = list_active_sessions(user_uuid=path.user_uuid)
    response = _build_session_list_response(
        all_items=all_items,
        page=query.page,
        page_size=query.page_size,
        cursor=query.cursor,
        current_session_uuid=None,
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
        payload, _admin_user, _target_user = _require_admin_for_user(header, path.user_uuid)
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
        ip_address=_client_ip(),
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
        payload, _admin_user, _target_user = _require_admin_for_user(header, path.user_uuid)
    except AuthError as exc:
        return _unauthorized(str(exc))

    revoked_count = revoke_all_sessions(user_uuid=path.user_uuid, reason="admin_revoke_all")
    _audit_log(
        actor_user_uuid=payload["sub"],
        target_user_uuid=path.user_uuid,
        session_uuid=None,
        action="admin_sessions_revoke_all",
        reason="admin_revoke_all",
        ip_address=_client_ip(),
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
        api_version=BaseConfig.get_str(current_app.config, "API_VERSION", BaseConfig.API_VERSION),
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
        jwt_additional_key_ids=sorted(list((current_app.config.get("JWT_ADDITIONAL_KEYS") or {}).keys())),
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
        cursor_created_at = _decode_audit_cursor(query.cursor)
        filters["created_at__lt"] = cursor_created_at
        queryset = SessionAuditLog.objects(**filters).order_by("-created_at")
        entries = list(queryset.limit(query.page_size + 1))
    else:
        queryset = SessionAuditLog.objects(**filters).order_by("-created_at")
        total_items = queryset.count()
        total_pages = (total_items + query.page_size - 1) // query.page_size if total_items else 0
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
        base_filter &= Q(actor_user_uuid=query.user_uuid) | Q(target_user_uuid=query.user_uuid)

    total_items: Optional[int] = None
    total_pages: Optional[int] = None
    if query.cursor:
        cursor_created_at = _decode_audit_cursor(query.cursor)
        base_filter &= Q(created_at__lt=cursor_created_at)
        queryset = SessionAuditLog.objects(base_filter).order_by("-created_at")
        entries = list(queryset.limit(query.page_size + 1))
    else:
        queryset = SessionAuditLog.objects(base_filter).order_by("-created_at")
        total_items = queryset.count()
        total_pages = (total_items + query.page_size - 1) // query.page_size if total_items else 0
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
