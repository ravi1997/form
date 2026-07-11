from __future__ import annotations

import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from uuid import uuid4
from datetime import datetime

from flask import request
from werkzeug.security import check_password_hash, generate_password_hash

from app.models.user import User
from app.api.auth_support import (
    _audit_log,
    _bad_request,
    _decode_audit_cursor,
    _encode_audit_cursor,
    _extract_bearer,
    _resolve_access_identity,
    _security_event,
    _unauthorized,
    auth_api,
    auth_tag,
)
from app.schemas.auth import (
    AccessTokenResponse,
    AuthorizationHeader,
    ChangePasswordRequest,
    ChangePasswordResponse,
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
    SessionListQuery,
    SessionListResponse,
    TokenPairResponse,
)
from app.schemas.mappers import to_json_ready, to_user_output
from app.schemas.user import UserOutput
from app.services.auth import (
    AuthError,
    access_token_ttl_seconds,
    create_user_session,
    decode_token,
    revoke_access_token,
    is_refresh_token_revoked,
    list_active_sessions,
    rotate_refresh_token,
    revoke_all_sessions,
    revoke_refresh_token,
    revoke_session,
    touch_session,
)
from app.services.rbac import (
    enforce_must_change_password,
    get_user_by_uuid,
    validate_account_status,
)
from app.middleware.rate_limit import rate_limit
from app.api import auth_admin_routes as _auth_admin_routes  # noqa: F401
from app.utils import client_ip, utcnow


def _encode_composite_cursor(*, timestamp, tie_breaker: str) -> str:
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


@auth_api.post(
    "/register",
    tags=[auth_tag],
    responses={201: UserOutput, 400: ErrorResponse},
)
def register(body: RegisterRequest):
    email = str(body.email).strip().lower()
    if User.objects(email=email).first():
        _security_event(
            event="register",
            outcome="rejected",
            endpoint="/api/v1/auth/register",
            reason="email_exists",
            details={"email": email},
        )
        return _bad_request("Email already registered")

    now = utcnow()
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
        status="unverified",
        must_change_password=False,
        last_password_change_at=now,
    )
    user.save()

    _security_event(
        event="register",
        outcome="success",
        endpoint="/api/v1/auth/register",
        actor_user_uuid=user.uuid,
        reason="verification_required",
        details={"email": email},
    )
    return to_json_ready(to_user_output(user)), 201


@rate_limit
@auth_api.post(
    "/login",
    tags=[auth_tag],
    responses={200: TokenPairResponse, 401: ErrorResponse, 429: ErrorResponse},
)
def login(body: LoginRequest):
    email = str(body.email).strip().lower()
    user = User.objects(email=email).first()
    if not user or not user.password_hash:
        _security_event(
            event="login",
            outcome="failed",
            endpoint="/api/v1/auth/login",
            reason="invalid_credentials",
            details={"email": email},
        )
        return _unauthorized("Invalid email or password")

    if not check_password_hash(user.password_hash, body.password):
        _security_event(
            event="login",
            outcome="failed",
            endpoint="/api/v1/auth/login",
            actor_user_uuid=user.uuid,
            reason="invalid_credentials",
            details={"email": email},
        )
        return _unauthorized("Invalid email or password")

    try:
        validate_account_status(user)
        enforce_must_change_password(user)
    except AuthError as exc:
        _security_event(
            event="login",
            outcome="failed",
            endpoint="/api/v1/auth/login",
            actor_user_uuid=user.uuid,
            reason=str(exc),
            details={"email": email},
        )
        return _unauthorized(str(exc))

    user.last_login_at = utcnow()
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
    _security_event(
        event="login",
        outcome="success",
        endpoint="/api/v1/auth/login",
        actor_user_uuid=user.uuid,
        details={"session_uuid": str(session["session_uuid"]), "email": email},
    )
    return to_json_ready(payload)


@auth_api.post(
    "/change-password",
    tags=[auth_tag],
    responses={200: ChangePasswordResponse, 401: ErrorResponse, 400: ErrorResponse},
)
def change_password(header: AuthorizationHeader, body: ChangePasswordRequest):
    try:
        token = _extract_bearer(header)
        payload = decode_token(token, expected_type="access")
        user = get_user_by_uuid(payload["sub"], allow_access=True)
    except AuthError as exc:
        return _unauthorized(str(exc))

    if not check_password_hash(user.password_hash, body.current_password):
        _security_event(
            event="change_password",
            outcome="failed",
            endpoint="/api/v1/auth/change-password",
            actor_user_uuid=user.uuid,
            reason="invalid_current_password",
        )
        return _unauthorized("Invalid current password")

    user.password_hash = generate_password_hash(body.new_password)
    user.must_change_password = False
    user.last_password_change_at = utcnow()
    user.save()

    touch_session(session_uuid=payload["sid"], user_uuid=payload["sub"])
    _security_event(
        event="change_password",
        outcome="success",
        endpoint="/api/v1/auth/change-password",
        actor_user_uuid=user.uuid,
    )
    return to_json_ready(ChangePasswordResponse())


@rate_limit
@auth_api.post(
    "/refresh",
    tags=[auth_tag],
    responses={200: AccessTokenResponse, 401: ErrorResponse, 429: ErrorResponse},
)
def refresh_token(body: RefreshTokenRequest):
    try:
        payload = decode_token(body.refresh_token, expected_type="refresh")
    except AuthError as exc:
        _security_event(
            event="refresh",
            outcome="failed",
            endpoint="/api/v1/auth/refresh",
            reason=str(exc),
        )
        return _unauthorized(str(exc))

    if is_refresh_token_revoked(body.refresh_token, payload=payload):
        _security_event(
            event="refresh",
            outcome="failed",
            endpoint="/api/v1/auth/refresh",
            actor_user_uuid=payload.get("sub"),
            reason="refresh_token_revoked",
        )
        return _unauthorized("Refresh token has been revoked")

    user = User.objects(uuid=payload["sub"]).first()
    if not user:
        _security_event(
            event="refresh",
            outcome="failed",
            endpoint="/api/v1/auth/refresh",
            actor_user_uuid=payload.get("sub"),
            reason="user_not_found",
        )
        return _unauthorized("User not found")
    try:
        validate_account_status(user)
    except AuthError as exc:
        _security_event(
            event="refresh",
            outcome="failed",
            endpoint="/api/v1/auth/refresh",
            actor_user_uuid=user.uuid,
            reason=str(exc),
        )
        return _unauthorized(str(exc))

    try:
        rotated = rotate_refresh_token(body.refresh_token)
    except AuthError as exc:
        _security_event(
            event="refresh",
            outcome="failed",
            endpoint="/api/v1/auth/refresh",
            actor_user_uuid=payload.get("sub"),
            reason=str(exc),
        )
        return _unauthorized(str(exc))

    response = AccessTokenResponse(
        access_token=str(rotated["access_token"]),
        refresh_token=str(rotated["refresh_token"]),
        session_uuid=str(rotated["session_uuid"]),
        expires_in=access_token_ttl_seconds(),
    )
    _security_event(
        event="refresh",
        outcome="success",
        endpoint="/api/v1/auth/refresh",
        actor_user_uuid=payload.get("sub"),
        details={"session_uuid": str(rotated["session_uuid"])},
    )
    return to_json_ready(response)


@rate_limit
@auth_api.post(
    "/logout",
    tags=[auth_tag],
    responses={200: LogoutResponse, 401: ErrorResponse, 429: ErrorResponse},
)
def logout(body: LogoutRequest):
    try:
        access_payload = decode_token(body.access_token, expected_type="access")
        payload = decode_token(body.refresh_token, expected_type="refresh")
        get_user_by_uuid(payload["sub"])
        if access_payload["sub"] != payload["sub"] or access_payload["sid"] != payload["sid"]:
            raise AuthError("Access token does not match refresh token")
        revoke_access_token(body.access_token, reason="logout")
        revoke_refresh_token(body.refresh_token, reason="logout")
    except AuthError as exc:
        _security_event(
            event="logout",
            outcome="failed",
            endpoint="/api/v1/auth/logout",
            reason=str(exc),
        )
        return _unauthorized(str(exc))

    _audit_log(
        actor_user_uuid=payload["sub"],
        target_user_uuid=payload["sub"],
        session_uuid=payload["sid"],
        action="logout",
        reason="logout",
        ip_address=client_ip(),
        user_agent=request.headers.get("User-Agent"),
        metadata={"endpoint": "/api/v1/auth/logout"},
    )

    _security_event(
        event="logout",
        outcome="success",
        endpoint="/api/v1/auth/logout",
        actor_user_uuid=payload["sub"],
        details={"session_uuid": payload["sid"]},
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

    try:
        user = get_user_by_uuid(payload["sub"])
    except AuthError as exc:
        return _unauthorized(str(exc))

    touch_session(session_uuid=payload["sid"], user_uuid=payload["sub"])

    return to_json_ready(to_user_output(user))


@auth_api.get(
    "/sessions",
    tags=[auth_tag],
    responses={200: SessionListResponse, 401: ErrorResponse},
)
def sessions(header: AuthorizationHeader, query: SessionListQuery):
    try:
        payload = _resolve_access_identity(header)
        get_user_by_uuid(payload["sub"])
    except AuthError as exc:
        return _unauthorized(str(exc))

    touch_session(session_uuid=payload["sid"], user_uuid=payload["sub"])

    all_items = list_active_sessions(user_uuid=payload["sub"])
    all_items = sorted(
        all_items,
        key=lambda session: (session.last_seen_at, session.session_uuid),
        reverse=True,
    )
    page_size = query.page_size
    page = query.page

    if query.cursor:
        cursor_created_at_raw, cursor_session_uuid = _decode_composite_cursor(
            query.cursor
        )
        filtered = [
            s
            for s in all_items
            if (
                s.last_seen_at < cursor_created_at_raw
                or (
                    cursor_session_uuid is not None
                    and s.last_seen_at == cursor_created_at_raw
                    and s.session_uuid < cursor_session_uuid
                )
            )
        ]
        selected = filtered[:page_size]
        total_items = None
        total_pages = None
    else:
        total_items = len(all_items)
        total_pages = (total_items + page_size - 1) // page_size if total_items else 0
        start = (page - 1) * page_size
        selected = all_items[start : start + page_size]

    items = []
    for session in selected:
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

    next_cursor = None
    if len(selected) == page_size:
        next_cursor = _encode_composite_cursor(
            timestamp=selected[-1].last_seen_at,
            tie_breaker=selected[-1].session_uuid,
        )

    return to_json_ready(
        SessionListResponse(
            sessions=items,
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
            next_cursor=next_cursor,
        )
    )


@auth_api.post(
    "/sessions/revoke",
    tags=[auth_tag],
    responses={200: RevokeSessionResponse, 401: ErrorResponse, 400: ErrorResponse},
)
def revoke_session_endpoint(header: AuthorizationHeader, body: RevokeSessionRequest):
    try:
        payload = _resolve_access_identity(header)
        get_user_by_uuid(payload["sub"])
    except AuthError as exc:
        return _unauthorized(str(exc))

    if body.session_uuid == payload["sid"]:
        _security_event(
            event="session_revoke",
            outcome="rejected",
            endpoint="/api/v1/auth/sessions/revoke",
            actor_user_uuid=payload["sub"],
            reason="current_session_disallowed",
        )
        return _bad_request("Use /api/v1/auth/logout for current session")

    revoked = revoke_session(
        session_uuid=body.session_uuid,
        user_uuid=payload["sub"],
        reason="session_revoke",
    )
    if not revoked:
        _security_event(
            event="session_revoke",
            outcome="failed",
            endpoint="/api/v1/auth/sessions/revoke",
            actor_user_uuid=payload["sub"],
            target_user_uuid=payload["sub"],
            reason="session_not_found",
            details={"session_uuid": body.session_uuid},
        )
        return _bad_request("Session not found or already inactive")

    _audit_log(
        actor_user_uuid=payload["sub"],
        target_user_uuid=payload["sub"],
        session_uuid=body.session_uuid,
        action="session_revoke",
        reason="session_revoke",
        ip_address=client_ip(),
        user_agent=request.headers.get("User-Agent"),
        metadata={"endpoint": "/api/v1/auth/sessions/revoke"},
    )

    _security_event(
        event="session_revoke",
        outcome="success",
        endpoint="/api/v1/auth/sessions/revoke",
        actor_user_uuid=payload["sub"],
        target_user_uuid=payload["sub"],
        details={"session_uuid": body.session_uuid},
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
        get_user_by_uuid(payload["sub"])
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
        ip_address=client_ip(),
        user_agent=request.headers.get("User-Agent"),
        metadata={
            "endpoint": "/api/v1/auth/logout-all",
            "revoked_count": revoked_count,
            "keep_current": body.keep_current,
        },
    )

    _security_event(
        event="logout_all",
        outcome="success",
        endpoint="/api/v1/auth/logout-all",
        actor_user_uuid=payload["sub"],
        target_user_uuid=payload["sub"],
        details={"revoked_count": revoked_count, "keep_current": body.keep_current},
    )

    if body.keep_current:
        touch_session(session_uuid=payload["sid"], user_uuid=payload["sub"])

    response = LogoutAllSessionsResponse(revoked_count=revoked_count)
    return to_json_ready(response)
