"""RBAC (Role-Based Access Control) service.

Provides identity resolution (JWT → User), privilege checks, and admin scope
validation.  All check helpers raise ``AuthError`` on failure rather than
returning a boolean, so callers can propagate errors uniformly.

Role hierarchy (highest to lowest):
  is_super_admin > is_organisation_admin (with admin role) > per-org roles
"""

from __future__ import annotations

from typing import Set, Tuple

from app.models.user import User
from app.services.auth import AuthError, decode_token
from app.services import get_rotating_logger
from app.services.password_policy import should_force_password_change
from app.services.org_keys import resolve_org_role_key, resolve_org_role_keys

logger = get_rotating_logger()

_DISABLED_ACCOUNT_STATUSES = {
    "inactive",
    "suspended",
    "locked",
    "deleted",
    "unverified",
}


def resolve_access_identity_from_header(raw_authorization: str) -> dict:
    logger.log_debug(
        "authentication_started",
        context={"has_authorization_header": bool(raw_authorization)},
    )
    raw = raw_authorization.strip()
    if not raw.startswith("Bearer "):
        logger.log_app_event(
            "authentication_failed",
            level="WARNING",
            context={"reason": "invalid_authorization_scheme"},
        )
        raise AuthError("Authorization header must use Bearer token")
    token = raw.replace("Bearer ", "", 1).strip()
    payload = decode_token(token, expected_type="access")
    get_user_by_uuid(payload["sub"])
    logger.log_debug(
        "authentication_successful",
        context={"user_uuid": payload.get("sub"), "session_uuid": payload.get("sid")},
    )
    return payload


def validate_account_status(user: User) -> None:
    status = getattr(user, "status", None)
    if status in _DISABLED_ACCOUNT_STATUSES:
        raise AuthError(f"User account is {status}")


def enforce_must_change_password(user: User, allow_access: bool = False) -> None:
    validate_account_status(user)
    if should_force_password_change(user):
        user.must_change_password = True
        user.save()
    if not allow_access and bool(getattr(user, "must_change_password", False)):
        raise AuthError("Password change required")


def get_user_by_uuid(user_uuid: str, *, allow_access: bool = False) -> User:
    logger.log_debug(
        "db_query_started",
        context={"model": "User", "operation": "get_by_uuid", "user_uuid": user_uuid},
    )
    user = User.objects(uuid=user_uuid).first()
    if not user:
        logger.log_app_event(
            "db_query_result_not_found",
            level="WARNING",
            context={
                "model": "User",
                "operation": "get_by_uuid",
                "user_uuid": user_uuid,
            },
        )
        raise AuthError("User not found")
    enforce_must_change_password(user, allow_access=allow_access)
    logger.log_debug(
        "db_query_succeeded",
        context={"model": "User", "operation": "get_by_uuid", "user_uuid": user_uuid},
    )
    return user


def has_global_admin_privileges(user: User) -> bool:
    return bool(user.is_super_admin)


def has_org_admin_privileges(user: User) -> bool:
    has_admin_role = any("admin" in roles for roles in (user.roles or {}).values())
    return bool(user.is_organisation_admin) or has_admin_role


def has_elevated_admin_privileges(user: User) -> bool:
    return has_global_admin_privileges(user) or has_org_admin_privileges(user)


def user_org_scope_keys(user: User) -> Set[str]:
    keys: Set[str] = set()
    for org in user.organizations or []:
        org_id = getattr(org, "id", None)
        if org_id is not None:
            keys.add(str(org_id))

        org_uuid = getattr(org, "uuid", None)
        if org_uuid:
            keys.add(str(org_uuid))
    return keys


def admin_org_scope_keys(user: User) -> Set[str]:
    keys: Set[str] = set()
    for org_key, roles in (user.roles or {}).items():
        if "admin" in (roles or []):
            keys.add(str(org_key))
    return keys


def admin_org_ids_for_user(user: User) -> Set[str]:
    return {
        key
        for org in user.organizations or []
        for key in resolve_org_role_keys(org)
        if "admin" in (user.roles or {}).get(key, [])
    }


def shares_org_scope(admin_user: User, target_user: User) -> bool:
    if bool(admin_user.is_super_admin):
        return True
    admin_org_ids = admin_org_ids_for_user(admin_user)
    target_org_ids = user_org_scope_keys(target_user)
    return bool(admin_org_ids and target_org_ids and admin_org_ids & target_org_ids)


def can_admin_access_user(admin_user: User, target_user: User) -> bool:
    if bool(admin_user.is_super_admin):
        return True
    return shares_org_scope(admin_user, target_user)


def require_admin_by_payload(payload: dict) -> Tuple[dict, User]:
    logger.log_debug(
        "authorization_check_started",
        context={"required_role": "admin", "user_uuid": payload.get("sub")},
    )
    user = get_user_by_uuid(payload["sub"])
    if not has_elevated_admin_privileges(user):
        logger.log_app_event(
            "authorization_denied",
            level="WARNING",
            context={"required_role": "admin", "user_uuid": payload.get("sub")},
        )
        raise AuthError("Admin privileges required")
    logger.log_debug(
        "authorization_passed",
        context={"required_role": "admin", "user_uuid": payload.get("sub")},
    )
    return payload, user


def require_global_admin_by_payload(payload: dict) -> Tuple[dict, User]:
    logger.log_debug(
        "authorization_check_started",
        context={"required_role": "global_admin", "user_uuid": payload.get("sub")},
    )
    user = get_user_by_uuid(payload["sub"])
    if not has_global_admin_privileges(user):
        logger.log_app_event(
            "authorization_denied",
            level="WARNING",
            context={"required_role": "global_admin", "user_uuid": payload.get("sub")},
        )
        raise AuthError("Global admin privileges required")
    logger.log_debug(
        "authorization_passed",
        context={"required_role": "global_admin", "user_uuid": payload.get("sub")},
    )
    return payload, user


def require_admin_for_user_payload(payload: dict, target_user_uuid: str):
    payload, admin_user = require_admin_by_payload(payload)
    target_user = get_user_by_uuid(target_user_uuid)

    if bool(admin_user.is_super_admin):
        return payload, admin_user, target_user

    admin_scope = admin_org_scope_keys(admin_user)
    target_scope = user_org_scope_keys(target_user)
    if not admin_scope or not target_scope or not (admin_scope & target_scope):
        raise AuthError("Admin scope does not include target user organizations")

    return payload, admin_user, target_user
