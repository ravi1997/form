from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import Field, model_validator

from app.schemas.common import SchemaModel

Role = Literal["admin", "editor", "viewer", "reviewer", "approver", "submitter"]
UserStatus = Literal[
    "active", "inactive", "deleted", "suspended", "locked", "unverified"
]
AuthProvider = Literal["local", "sso"]


class UserBase(SchemaModel):
    name: str
    designation: Optional[str] = None
    email: str
    phone: Optional[str] = None
    organizations: List[str] = Field(default_factory=list)
    roles: Dict[str, List[Role]] = Field(default_factory=dict)
    status: UserStatus = "active"
    auth_provider: AuthProvider = "local"
    is_email_verified: bool = False
    is_phone_verified: bool = False
    is_organisation_admin: bool = False
    is_super_admin: bool = False
    is_mfa_enabled: bool = False
    must_change_password: bool = False

    @model_validator(mode="after")
    def validate_admin_flag_against_roles(self) -> "UserBase":
        if self.is_organisation_admin and self.roles:
            has_admin_role = any(
                "admin" in org_roles for org_roles in self.roles.values()
            )
            if not has_admin_role:
                raise ValueError(
                    "is_organisation_admin cannot be true when no organization has admin role"
                )
        return self


class UserCreateInput(UserBase):
    uuid: str
    password_hash: Optional[str] = None

    @model_validator(mode="after")
    def validate_local_auth_password(self) -> "UserCreateInput":
        if self.auth_provider == "local" and not self.password_hash:
            raise ValueError("password_hash is required for local auth users")
        return self


class UserUpdateInput(SchemaModel):
    name: Optional[str] = None
    designation: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    organizations: Optional[List[str]] = None
    roles: Optional[Dict[str, List[Role]]] = None
    status: Optional[UserStatus] = None
    auth_provider: Optional[AuthProvider] = None
    # password_hash and otp_secret are intentionally excluded — callers must use
    # the dedicated /auth/change-password and /auth/otp endpoints instead.
    password_reset_token: Optional[str] = None
    password_reset_token_expiry: Optional[datetime] = None
    password_reset_token_created_at: Optional[datetime] = None
    otp_secret_created_at: Optional[datetime] = None
    is_email_verified: Optional[bool] = None
    is_phone_verified: Optional[bool] = None
    is_organisation_admin: Optional[bool] = None
    is_super_admin: Optional[bool] = None
    is_mfa_enabled: Optional[bool] = None
    must_change_password: Optional[bool] = None
    verified_at: Optional[datetime] = None
    verified_by: Optional[str] = None
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None
    last_login_at: Optional[datetime] = None
    last_logout_at: Optional[datetime] = None
    last_password_change_at: Optional[datetime] = None
    must_change_password: Optional[bool] = None


class UserRef(SchemaModel):
    uuid: str
    name: str
    email: str


class UserOutput(UserBase):
    uuid: str
    created_at: datetime
    updated_at: datetime
    verified_at: Optional[datetime] = None
    verified_by: Optional[str] = None
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None
    last_login_at: Optional[datetime] = None
    last_logout_at: Optional[datetime] = None
    last_password_change_at: Optional[datetime] = None
    must_change_password: bool


class VerifyUserInput(SchemaModel):
    organization_uuid: str
    roles: List[Role]
