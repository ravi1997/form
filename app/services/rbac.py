from __future__ import annotations

from typing import Set, Tuple

from app.models.user import User
from app.services.auth import AuthError, decode_token


def resolve_access_identity_from_header(raw_authorization: str) -> dict:
    raw = raw_authorization.strip()
    if not raw.startswith("Bearer "):
        raise AuthError("Authorization header must use Bearer token")
    token = raw.replace("Bearer ", "", 1).strip()
    return decode_token(token, expected_type="access")


def get_user_by_uuid(user_uuid: str) -> User:
    user = User.objects(uuid=user_uuid).first()
    if not user:
        raise AuthError("User not found")
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


def require_admin_by_payload(payload: dict) -> Tuple[dict, User]:
    user = get_user_by_uuid(payload["sub"])
    if not has_elevated_admin_privileges(user):
        raise AuthError("Admin privileges required")
    return payload, user


def require_global_admin_by_payload(payload: dict) -> Tuple[dict, User]:
    user = get_user_by_uuid(payload["sub"])
    if not has_global_admin_privileges(user):
        raise AuthError("Global admin privileges required")
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
