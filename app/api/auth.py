from __future__ import annotations

import base64
from datetime import datetime
from typing import Optional
from uuid import uuid4

from flask import current_app, request
from mongoengine.queryset.visitor import Q
from werkzeug.security import check_password_hash, generate_password_hash

from app.models.user import User
from app.models.auth import SessionAuditLog
from app.config import BaseConfig
from app.schemas.auth import (
    AccessTokenResponse,
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
    LoginRequest,
    LogoutAllSessionsRequest,
    LogoutAllSessionsResponse,
    LogoutRequest,
    LogoutResponse,
    RevokeSessionRequest,
    RevokeSessionResponse,
    RefreshTokenRequest,
    RegisterRequest,
    SessionInfo,
    SessionListResponse,
    TokenPairResponse,
)
from app.schemas.mappers import to_json_ready, to_user_output
from app.schemas.user import UserOutput
from app.services.auth import (
    AuthError,
    access_token_ttl_seconds,
    create_access_token,
    create_user_session,
    decode_token,
    is_refresh_token_revoked,
    list_active_sessions,
    rotate_refresh_token,
    revoke_all_sessions,
    revoke_refresh_token,
    revoke_session,
    touch_session,
)
from app.services.security import check_and_increment_rate_limit, log_session_audit_event

try:
    from flask_openapi3 import APIBlueprint, Tag
except ImportError as exc:  # pragma: no cover - evaluated only when package is missing
    raise RuntimeError(
        "flask-openapi3 is required for OpenAPI integration. Install with: pip install flask-openapi3"
    ) from exc


auth_tag = Tag(name="Auth", description="JWT authentication")
auth_api = APIBlueprint("auth", __name__, url_prefix="/api/auth")


def _unauthorized(message: str):
    return to_json_ready(ErrorResponse(message=message)), 401


def _bad_request(message: str):
    return to_json_ready(ErrorResponse(message=message)), 400


def _too_many_requests(message: str, retry_after: int):
    response, status = to_json_ready(ErrorResponse(message=message)), 429
    return response, status, {"Retry-After": str(retry_after)}


def _client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _is_audit_enabled() -> bool:
    return BaseConfig.get_bool(
        current_app.config,
        "ENABLE_AUDIT_LOGS",
        BaseConfig.ENABLE_AUDIT_LOGS,
    )


def _audit_log(**kwargs):
    if _is_audit_enabled():
        log_session_audit_event(**kwargs)


def _encode_audit_cursor(created_at: datetime) -> str:
    return base64.urlsafe_b64encode(created_at.isoformat().encode("utf-8")).decode("utf-8")


def _decode_audit_cursor(cursor: str) -> datetime:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        return datetime.fromisoformat(raw)
    except Exception as exc:
        raise AuthError("Invalid cursor") from exc


def _enforce_rate_limit(scope: str, key: str):
    max_key = f"AUTH_RATE_LIMIT_{scope.upper()}_MAX"
    window_key = f"AUTH_RATE_LIMIT_{scope.upper()}_WINDOW_SECONDS"
    defaults = {
        "login": (
            BaseConfig.AUTH_RATE_LIMIT_LOGIN_MAX,
            BaseConfig.AUTH_RATE_LIMIT_LOGIN_WINDOW_SECONDS,
        ),
        "refresh": (
            BaseConfig.AUTH_RATE_LIMIT_REFRESH_MAX,
            BaseConfig.AUTH_RATE_LIMIT_REFRESH_WINDOW_SECONDS,
        ),
        "logout": (
            BaseConfig.AUTH_RATE_LIMIT_LOGOUT_MAX,
            BaseConfig.AUTH_RATE_LIMIT_LOGOUT_WINDOW_SECONDS,
        ),
    }
    default_max, default_window = defaults.get(scope, (10, 60))

    max_requests = int(current_app.config.get(max_key, default_max))
    window_seconds = int(current_app.config.get(window_key, default_window))

    result = check_and_increment_rate_limit(
        scope=scope,
        key=key,
        max_requests=max_requests,
        window_seconds=window_seconds,
    )
    if bool(result["limited"]):
        return _too_many_requests(
            message="Too many requests for this endpoint. Please try again later.",
            retry_after=int(result["retry_after"]),
        )
    return None


def _enforce_dual_rate_limit(scope: str, user_key: Optional[str]):
    ip_limit = _enforce_rate_limit(scope=scope, key=f"ip:{_client_ip()}")
    if ip_limit:
        return ip_limit

    if user_key:
        user_limit = _enforce_rate_limit(scope=scope, key=f"user:{user_key}")
        if user_limit:
            return user_limit

    return None


def _enforce_user_rate_limit(scope: str, user_key: Optional[str]):
    if not user_key:
        return None
    return _enforce_rate_limit(scope=scope, key=f"user:{user_key}")


def _extract_bearer(header: AuthorizationHeader):
    raw = header.Authorization.strip()
    if not raw.startswith("Bearer "):
        raise AuthError("Authorization header must use Bearer token")
    return raw.replace("Bearer ", "", 1).strip()


def _resolve_access_identity(header: AuthorizationHeader):
    token = _extract_bearer(header)
    return decode_token(token, expected_type="access")


def _require_admin(header: AuthorizationHeader):
    payload = _resolve_access_identity(header)
    user = User.objects(uuid=payload["sub"]).first()
    if not user:
        raise AuthError("User not found")

    has_admin_role = any("admin" in roles for roles in (user.roles or {}).values())
    if not (bool(user.is_super_admin) or bool(user.is_organisation_admin) or has_admin_role):
        raise AuthError("Admin privileges required")

    return payload, user


def _user_org_scope_keys(user: User):
    keys = set()

    for org in user.organizations or []:
        org_id = getattr(org, "id", None)
        if org_id is not None:
            keys.add(str(org_id))

        org_uuid = getattr(org, "uuid", None)
        if org_uuid:
            keys.add(str(org_uuid))

    return keys


def _admin_org_scope_keys(user: User):
    keys = set()

    for org_key, roles in (user.roles or {}).items():
        if "admin" in (roles or []):
            keys.add(str(org_key))

    return keys


def _require_admin_for_user(header: AuthorizationHeader, target_user_uuid: str):
    payload, admin_user = _require_admin(header)
    target_user = User.objects(uuid=target_user_uuid).first()
    if not target_user:
        raise AuthError("Target user not found")

    # Global admins keep unrestricted visibility and revocation access.
    if bool(admin_user.is_super_admin):
        return payload, admin_user, target_user

    admin_scope = _admin_org_scope_keys(admin_user)
    target_scope = _user_org_scope_keys(target_user)
    if not admin_scope or not target_scope or not (admin_scope & target_scope):
        raise AuthError("Admin scope does not include target user organizations")

    return payload, admin_user, target_user


@auth_api.post(
    "/register",
    tags=[auth_tag],
    responses={201: TokenPairResponse, 400: ErrorResponse},
)
def register(body: RegisterRequest):
    email = str(body.email).strip().lower()
    if User.objects(email=email).first():
        return _bad_request("Email already registered")

    now = datetime.utcnow()
    user = User(
        uuid=str(uuid4()),
        name=body.name,
        email=email,
        phone=body.phone,
        designation=body.designation,
        auth_provider="local",
        password_hash=generate_password_hash(body.password),
        created_at=now,
        updated_at=now,
    )
    user.save()

    session = create_user_session(
        user_uuid=user.uuid,
        email=user.email,
        user_agent=request.headers.get("User-Agent"),
        ip_address=request.remote_addr,
        device_name=body.device_name,
    )
    payload = TokenPairResponse(
        access_token=str(session["access_token"]),
        refresh_token=str(session["refresh_token"]),
        session_uuid=str(session["session_uuid"]),
        expires_in=access_token_ttl_seconds(),
        user=to_user_output(user),
    )
    return to_json_ready(payload), 201


@auth_api.post(
    "/login",
    tags=[auth_tag],
    responses={200: TokenPairResponse, 401: ErrorResponse, 429: ErrorResponse},
)
def login(body: LoginRequest):
    rate_limit = _enforce_dual_rate_limit(
        scope="login",
        user_key=str(body.email).strip().lower(),
    )
    if rate_limit:
        return rate_limit

    email = str(body.email).strip().lower()
    user = User.objects(email=email).first()
    if not user or not user.password_hash:
        return _unauthorized("Invalid email or password")

    if not check_password_hash(user.password_hash, body.password):
        return _unauthorized("Invalid email or password")

    user.last_login_at = datetime.utcnow()
    user.save()

    session = create_user_session(
        user_uuid=user.uuid,
        email=user.email,
        user_agent=request.headers.get("User-Agent"),
        ip_address=request.remote_addr,
        device_name=body.device_name,
    )
    payload = TokenPairResponse(
        access_token=str(session["access_token"]),
        refresh_token=str(session["refresh_token"]),
        session_uuid=str(session["session_uuid"]),
        expires_in=access_token_ttl_seconds(),
        user=to_user_output(user),
    )
    return to_json_ready(payload)


@auth_api.post(
    "/refresh",
    tags=[auth_tag],
    responses={200: AccessTokenResponse, 401: ErrorResponse, 429: ErrorResponse},
)
def refresh_token(body: RefreshTokenRequest):
    rate_limit = _enforce_dual_rate_limit(scope="refresh", user_key=None)
    if rate_limit:
        return rate_limit

    try:
        payload = decode_token(body.refresh_token, expected_type="refresh")
    except AuthError as exc:
        return _unauthorized(str(exc))

    user_limit = _enforce_user_rate_limit(scope="refresh", user_key=payload.get("sub"))
    if user_limit:
        return user_limit

    if is_refresh_token_revoked(body.refresh_token, payload=payload):
        return _unauthorized("Refresh token has been revoked")

    user = User.objects(uuid=payload["sub"]).first()
    if not user:
        return _unauthorized("User not found")

    try:
        rotated = rotate_refresh_token(body.refresh_token)
    except AuthError as exc:
        return _unauthorized(str(exc))

    response = AccessTokenResponse(
        access_token=str(rotated["access_token"]),
        refresh_token=str(rotated["refresh_token"]),
        session_uuid=str(rotated["session_uuid"]),
        expires_in=access_token_ttl_seconds(),
    )
    return to_json_ready(response)


@auth_api.post(
    "/logout",
    tags=[auth_tag],
    responses={200: LogoutResponse, 401: ErrorResponse, 429: ErrorResponse},
)
def logout(body: LogoutRequest):
    rate_limit = _enforce_dual_rate_limit(scope="logout", user_key=None)
    if rate_limit:
        return rate_limit

    try:
        payload = decode_token(body.refresh_token, expected_type="refresh")
        user_limit = _enforce_user_rate_limit(scope="logout", user_key=payload.get("sub"))
        if user_limit:
            return user_limit
        revoke_refresh_token(body.refresh_token, reason="logout")
    except AuthError as exc:
        return _unauthorized(str(exc))

    _audit_log(
        actor_user_uuid=payload["sub"],
        target_user_uuid=payload["sub"],
        session_uuid=payload["sid"],
        action="logout",
        reason="logout",
        ip_address=_client_ip(),
        user_agent=request.headers.get("User-Agent"),
        metadata={"endpoint": "/api/auth/logout"},
    )

    return to_json_ready(LogoutResponse())


@auth_api.get(
    "/me",
    tags=[auth_tag],
    responses={200: UserOutput, 401: ErrorResponse},
)
def me(header: AuthorizationHeader):
    try:
        token = _extract_bearer(header)
    except AuthError as exc:
        return _unauthorized(str(exc))

    try:
        payload = decode_token(token, expected_type="access")
    except AuthError as exc:
        return _unauthorized(str(exc))

    user = User.objects(uuid=payload["sub"]).first()
    if not user:
        return _unauthorized("User not found")

    touch_session(session_uuid=payload["sid"], user_uuid=payload["sub"])

    return to_json_ready(to_user_output(user))


@auth_api.get(
    "/sessions",
    tags=[auth_tag],
    responses={200: SessionListResponse, 401: ErrorResponse},
)
def sessions(header: AuthorizationHeader):
    try:
        payload = _resolve_access_identity(header)
    except AuthError as exc:
        return _unauthorized(str(exc))

    touch_session(session_uuid=payload["sid"], user_uuid=payload["sub"])

    items = []
    for session in list_active_sessions(user_uuid=payload["sub"]):
        items.append(
            SessionInfo(
                session_uuid=session.session_uuid,
                device_name=session.device_name,
                user_agent=session.user_agent,
                ip_address=session.ip_address,
                created_at=session.created_at,
                last_seen_at=session.last_seen_at,
                is_current=session.session_uuid == payload["sid"],
            )
        )

    return to_json_ready(SessionListResponse(sessions=items))


@auth_api.post(
    "/sessions/revoke",
    tags=[auth_tag],
    responses={200: RevokeSessionResponse, 401: ErrorResponse, 400: ErrorResponse},
)
def revoke_session_endpoint(header: AuthorizationHeader, body: RevokeSessionRequest):
    try:
        payload = _resolve_access_identity(header)
    except AuthError as exc:
        return _unauthorized(str(exc))

    if body.session_uuid == payload["sid"]:
        return _bad_request("Use /api/auth/logout for current session")

    revoked = revoke_session(
        session_uuid=body.session_uuid,
        user_uuid=payload["sub"],
        reason="session_revoke",
    )
    if not revoked:
        return _bad_request("Session not found or already inactive")

    _audit_log(
        actor_user_uuid=payload["sub"],
        target_user_uuid=payload["sub"],
        session_uuid=body.session_uuid,
        action="session_revoke",
        reason="session_revoke",
        ip_address=_client_ip(),
        user_agent=request.headers.get("User-Agent"),
        metadata={"endpoint": "/api/auth/sessions/revoke"},
    )

    touch_session(session_uuid=payload["sid"], user_uuid=payload["sub"])
    return to_json_ready(RevokeSessionResponse())


@auth_api.post(
    "/logout-all",
    tags=[auth_tag],
    responses={200: LogoutAllSessionsResponse, 401: ErrorResponse},
)
def logout_all(header: AuthorizationHeader, body: LogoutAllSessionsRequest):
    try:
        payload = _resolve_access_identity(header)
    except AuthError as exc:
        return _unauthorized(str(exc))

    revoked_count = revoke_all_sessions(
        user_uuid=payload["sub"],
        reason="logout_all",
        except_session_uuid=payload["sid"] if body.keep_current else None,
    )

    _audit_log(
        actor_user_uuid=payload["sub"],
        target_user_uuid=payload["sub"],
        session_uuid=None,
        action="logout_all",
        reason="logout_all",
        ip_address=_client_ip(),
        user_agent=request.headers.get("User-Agent"),
        metadata={
            "endpoint": "/api/auth/logout-all",
            "revoked_count": revoked_count,
            "keep_current": body.keep_current,
        },
    )

    if body.keep_current:
        touch_session(session_uuid=payload["sid"], user_uuid=payload["sub"])

    response = LogoutAllSessionsResponse(revoked_count=revoked_count)
    return to_json_ready(response)


@auth_api.get(
    "/admin/users/<user_uuid>/sessions",
    tags=[auth_tag],
    responses={200: SessionListResponse, 401: ErrorResponse},
)
def admin_list_user_sessions(header: AuthorizationHeader, path: AdminUserPath):
    try:
        payload, _admin_user, _target_user = _require_admin_for_user(header, path.user_uuid)
    except AuthError as exc:
        return _unauthorized(str(exc))

    touch_session(session_uuid=payload["sid"], user_uuid=payload["sub"])

    items = []
    for session in list_active_sessions(user_uuid=path.user_uuid):
        items.append(
            SessionInfo(
                session_uuid=session.session_uuid,
                device_name=session.device_name,
                user_agent=session.user_agent,
                ip_address=session.ip_address,
                created_at=session.created_at,
                last_seen_at=session.last_seen_at,
                is_current=False,
            )
        )

    return to_json_ready(SessionListResponse(sessions=items))


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
        return _bad_request("Session not found or already inactive")

    _audit_log(
        actor_user_uuid=payload["sub"],
        target_user_uuid=path.user_uuid,
        session_uuid=body.session_uuid,
        action="admin_session_revoke",
        reason="admin_revoke",
        ip_address=_client_ip(),
        user_agent=request.headers.get("User-Agent"),
        metadata={"endpoint": "/api/auth/admin/users/<user_uuid>/sessions/revoke"},
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

    revoked_count = revoke_all_sessions(
        user_uuid=path.user_uuid,
        reason="admin_revoke_all",
    )

    _audit_log(
        actor_user_uuid=payload["sub"],
        target_user_uuid=path.user_uuid,
        session_uuid=None,
        action="admin_sessions_revoke_all",
        reason="admin_revoke_all",
        ip_address=_client_ip(),
        user_agent=request.headers.get("User-Agent"),
        metadata={
            "endpoint": "/api/auth/admin/users/<user_uuid>/sessions/revoke-all",
            "revoked_count": revoked_count,
        },
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
        env_name=BaseConfig.get_str(current_app.config, "ENV_NAME", "development"),
        debug=BaseConfig.get_bool(current_app.config, "DEBUG", False),
        jwt_algorithm=BaseConfig.get_str(
            current_app.config,
            "JWT_ALGORITHM",
            BaseConfig.JWT_ALGORITHM,
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
        enable_audit_logs=BaseConfig.get_bool(
            current_app.config,
            "ENABLE_AUDIT_LOGS",
            BaseConfig.ENABLE_AUDIT_LOGS,
        ),
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

    page = query.page
    page_size = query.page_size
    total_items: Optional[int] = None
    total_pages: Optional[int] = None
    next_cursor: Optional[str] = None

    if query.cursor:
        cursor_created_at = _decode_audit_cursor(query.cursor)
        filters["created_at__lt"] = cursor_created_at
        queryset = SessionAuditLog.objects(**filters).order_by("-created_at")
        entries = list(queryset.limit(page_size + 1))
    else:
        queryset = SessionAuditLog.objects(**filters).order_by("-created_at")
        total_items = queryset.count()
        total_pages = (total_items + page_size - 1) // page_size if total_items else 0
        skip = (page - 1) * page_size
        entries = list(queryset.skip(skip).limit(page_size + 1))

    items = []
    page_entries = entries[:page_size]
    for entry in page_entries:
        items.append(
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
        )

    if len(entries) > page_size and page_entries:
        next_cursor = _encode_audit_cursor(page_entries[-1].created_at)

    response = AdminAuditLogListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total_items=total_items,
        total_pages=total_pages,
        next_cursor=next_cursor,
    )
    return to_json_ready(response)


@auth_api.get(
    "/admin/audit-logs/search",
    tags=[auth_tag],
    responses={200: AdminAuditLogListResponse, 401: ErrorResponse},
)
def admin_audit_logs_search(header: AuthorizationHeader, query: AdminAuditLogSearchQuery):
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

    page = query.page
    page_size = query.page_size
    total_items: Optional[int] = None
    total_pages: Optional[int] = None
    next_cursor: Optional[str] = None

    if query.cursor:
        cursor_created_at = _decode_audit_cursor(query.cursor)
        base_filter &= Q(created_at__lt=cursor_created_at)
        queryset = SessionAuditLog.objects(base_filter).order_by("-created_at")
        entries = list(queryset.limit(page_size + 1))
    else:
        queryset = SessionAuditLog.objects(base_filter).order_by("-created_at")
        total_items = queryset.count()
        total_pages = (total_items + page_size - 1) // page_size if total_items else 0
        skip = (page - 1) * page_size
        entries = list(queryset.skip(skip).limit(page_size + 1))

    items = []
    page_entries = entries[:page_size]
    for entry in page_entries:
        items.append(
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
        )

    if len(entries) > page_size and page_entries:
        next_cursor = _encode_audit_cursor(page_entries[-1].created_at)

    response = AdminAuditLogListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total_items=total_items,
        total_pages=total_pages,
        next_cursor=next_cursor,
    )
    return to_json_ready(response)
