"""Tests for RBAC privilege boundaries."""

import pytest

from app.services.auth import AuthError
import app.services.rbac as rbac


class _DummyUser:
    def __init__(
        self,
        *,
        is_super_admin=False,
        is_organisation_admin=False,
        roles=None,
        organizations=None,
    ):
        self.is_super_admin = is_super_admin
        self.is_organisation_admin = is_organisation_admin
        self.roles = roles or {}
        self.organizations = organizations or []


class _DummyOrg:
    def __init__(self, org_id, uuid=None):
        self.id = org_id
        self.uuid = uuid


def test_has_global_admin_privileges_requires_super_admin():
    user = _DummyUser(
        is_super_admin=False, is_organisation_admin=True, roles={"org-1": ["admin"]}
    )
    assert rbac.has_global_admin_privileges(user) is False

    super_user = _DummyUser(is_super_admin=True)
    assert rbac.has_global_admin_privileges(super_user) is True


def test_has_elevated_admin_privileges_accepts_org_admin():
    org_admin = _DummyUser(is_organisation_admin=True)
    assert rbac.has_elevated_admin_privileges(org_admin) is True


def test_require_global_admin_by_payload_rejects_org_admin(monkeypatch):
    monkeypatch.setattr(
        rbac,
        "get_user_by_uuid",
        lambda _uuid: _DummyUser(is_super_admin=False, is_organisation_admin=True),
    )

    with pytest.raises(AuthError, match="Global admin privileges required"):
        rbac.require_global_admin_by_payload({"sub": "user-1"})


def test_require_admin_for_user_payload_allows_scoped_org_admin(monkeypatch):
    admin_user = _DummyUser(
        is_super_admin=False,
        is_organisation_admin=True,
        roles={"org-1": ["admin"]},
        organizations=[_DummyOrg("org-1")],
    )
    target_user = _DummyUser(organizations=[_DummyOrg("org-1")])

    def _lookup(user_uuid):
        if user_uuid == "admin-user":
            return admin_user
        return target_user

    monkeypatch.setattr(rbac, "get_user_by_uuid", _lookup)

    payload, resolved_admin, resolved_target = rbac.require_admin_for_user_payload(
        {"sub": "admin-user"},
        "target-user",
    )

    assert payload["sub"] == "admin-user"
    assert resolved_admin is admin_user
    assert resolved_target is target_user
