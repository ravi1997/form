from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import EmailStr, Field

from app.schemas.common import SchemaModel
from app.schemas.user import UserOutput


class RegisterRequest(SchemaModel):
    name: str = Field(min_length=1)
    email: EmailStr
    password: str = Field(min_length=8)
    designation: Optional[str] = None
    phone: Optional[str] = None
    device_name: Optional[str] = None


class LoginRequest(SchemaModel):
    email: EmailStr
    password: str = Field(min_length=1)
    device_name: Optional[str] = None


class RefreshTokenRequest(SchemaModel):
    refresh_token: str = Field(min_length=1)


class LogoutRequest(SchemaModel):
    refresh_token: str = Field(min_length=1)


class AuthorizationHeader(SchemaModel):
    Authorization: str = Field(min_length=10)


class TokenPairResponse(SchemaModel):
    access_token: str
    refresh_token: str
    session_uuid: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int
    user: UserOutput


class AccessTokenResponse(SchemaModel):
    access_token: str
    refresh_token: str
    session_uuid: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int


class ErrorResponse(SchemaModel):
    message: str
    limit_scope: Optional[Literal["ip", "user"]] = None


class LogoutResponse(SchemaModel):
    message: Literal["logged_out"] = "logged_out"


class SessionInfo(SchemaModel):
    session_uuid: str
    device_name: Optional[str] = None
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime
    last_seen_at: datetime
    is_current: bool = False


class SessionListResponse(SchemaModel):
    sessions: List[SessionInfo]


class RevokeSessionRequest(SchemaModel):
    session_uuid: str = Field(min_length=1)


class RevokeSessionResponse(SchemaModel):
    message: Literal["session_revoked"] = "session_revoked"


class LogoutAllSessionsRequest(SchemaModel):
    keep_current: bool = False


class LogoutAllSessionsResponse(SchemaModel):
    message: Literal["sessions_revoked"] = "sessions_revoked"
    revoked_count: int


class AdminUserPath(SchemaModel):
    user_uuid: str = Field(min_length=1)


class AdminRevokeSessionRequest(SchemaModel):
    session_uuid: str = Field(min_length=1)


class AdminRevokeSessionResponse(SchemaModel):
    message: Literal["admin_session_revoked"] = "admin_session_revoked"


class AdminRevokeAllSessionsResponse(SchemaModel):
    message: Literal["admin_sessions_revoked"] = "admin_sessions_revoked"
    revoked_count: int


class AdminConfigHealthResponse(SchemaModel):
    env_name: str
    debug: bool
    jwt_algorithm: str
    jwt_active_kid: str
    jwt_additional_key_ids: List[str]
    jwt_access_token_expires_minutes: int
    jwt_refresh_token_expires_days: int
    auth_rate_limit_login_max: int
    auth_rate_limit_login_window_seconds: int
    auth_rate_limit_refresh_max: int
    auth_rate_limit_refresh_window_seconds: int
    auth_rate_limit_logout_max: int
    auth_rate_limit_logout_window_seconds: int
    enable_audit_logs: bool
    request_id_header: str


class AdminAuditLogQuery(SchemaModel):
    actor_user_uuid: Optional[str] = None
    target_user_uuid: Optional[str] = None
    session_uuid: Optional[str] = None
    action: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    cursor: Optional[str] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class AdminAuditLogSearchQuery(SchemaModel):
    user_uuid: Optional[str] = None
    action: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    cursor: Optional[str] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class AdminAuditLogEntry(SchemaModel):
    actor_user_uuid: str
    target_user_uuid: str
    session_uuid: Optional[str] = None
    action: str
    reason: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime


class AdminAuditLogListResponse(SchemaModel):
    items: List[AdminAuditLogEntry]
    page: int
    page_size: int
    total_items: Optional[int] = None
    total_pages: Optional[int] = None
    next_cursor: Optional[str] = None
