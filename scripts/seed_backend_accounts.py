#!/usr/bin/env python
"""
Seed the backend with a known organization and role-based user accounts.

This script is idempotent:
- it creates the organization if missing
- it creates each account if missing
- it updates existing records to match the configured seed values

Usage:
    python scripts/seed_backend_accounts.py
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from werkzeug.security import generate_password_hash

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_openapi_app  # noqa: E402
from app.models.user import Organization, User  # noqa: E402
from app.services.org_keys import resolve_org_role_key  # noqa: E402
from app.utils import utcnow  # noqa: E402


@dataclass(frozen=True)
class SeedOrganization:
    uuid: str
    name: str


@dataclass(frozen=True)
class SeedUser:
    uuid: str
    name: str
    email: str
    password: str
    role: str
    is_super_admin: bool = False
    is_organisation_admin: bool = False


DEFAULT_SEED_ORGANIZATION = SeedOrganization(
    uuid="org-role-seed-0001",
    name="Role Seed Org",
)

DEFAULT_SEED_USERS: tuple[SeedUser, ...] = (
    SeedUser(
        uuid="usr-role-admin-0001",
        name="Role Admin",
        email="role-admin@example.com",
        password="Password123!",
        role="admin",
        is_organisation_admin=True,
    ),
    SeedUser(
        uuid="usr-role-editor-0001",
        name="Role Editor",
        email="role-editor@example.com",
        password="Password123!",
        role="editor",
    ),
    SeedUser(
        uuid="usr-role-viewer-0001",
        name="Role Viewer",
        email="role-viewer@example.com",
        password="Password123!",
        role="viewer",
    ),
    SeedUser(
        uuid="usr-role-reviewer-0001",
        name="Role Reviewer",
        email="role-reviewer@example.com",
        password="Password123!",
        role="reviewer",
    ),
    SeedUser(
        uuid="usr-role-approver-0001",
        name="Role Approver",
        email="role-approver@example.com",
        password="Password123!",
        role="approver",
    ),
    SeedUser(
        uuid="usr-role-submitter-0001",
        name="Role Submitter",
        email="role-submitter@example.com",
        password="Password123!",
        role="submitter",
    ),
)


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise KeyError(name)
    return value


def _read_seed_organization() -> SeedOrganization:
    try:
        return SeedOrganization(
            uuid=_required_env("SEED_ORGANIZATION_UUID"),
            name=_required_env("SEED_ORGANIZATION_NAME"),
        )
    except KeyError:
        return DEFAULT_SEED_ORGANIZATION


def _read_seed_users() -> tuple[SeedUser, ...]:
    try:
        return (
            SeedUser(
                uuid=_required_env("SEED_ADMIN_UUID"),
                name=_required_env("SEED_ADMIN_NAME"),
                email=_required_env("SEED_ADMIN_EMAIL"),
                password=_required_env("SEED_ADMIN_PASSWORD"),
                role="admin",
                is_organisation_admin=True,
            ),
            SeedUser(
                uuid=_required_env("SEED_EDITOR_UUID"),
                name=_required_env("SEED_EDITOR_NAME"),
                email=_required_env("SEED_EDITOR_EMAIL"),
                password=_required_env("SEED_EDITOR_PASSWORD"),
                role="editor",
            ),
            SeedUser(
                uuid=_required_env("SEED_VIEWER_UUID"),
                name=_required_env("SEED_VIEWER_NAME"),
                email=_required_env("SEED_VIEWER_EMAIL"),
                password=_required_env("SEED_VIEWER_PASSWORD"),
                role="viewer",
            ),
            SeedUser(
                uuid=_required_env("SEED_REVIEWER_UUID"),
                name=_required_env("SEED_REVIEWER_NAME"),
                email=_required_env("SEED_REVIEWER_EMAIL"),
                password=_required_env("SEED_REVIEWER_PASSWORD"),
                role="reviewer",
            ),
            SeedUser(
                uuid=_required_env("SEED_APPROVER_UUID"),
                name=_required_env("SEED_APPROVER_NAME"),
                email=_required_env("SEED_APPROVER_EMAIL"),
                password=_required_env("SEED_APPROVER_PASSWORD"),
                role="approver",
            ),
            SeedUser(
                uuid=_required_env("SEED_SUBMITTER_UUID"),
                name=_required_env("SEED_SUBMITTER_NAME"),
                email=_required_env("SEED_SUBMITTER_EMAIL"),
                password=_required_env("SEED_SUBMITTER_PASSWORD"),
                role="submitter",
            ),
        )
    except KeyError:
        return DEFAULT_SEED_USERS


def _ensure_organization(seed: SeedOrganization) -> Organization:
    organization = Organization.objects(uuid=seed.uuid).first()
    if organization is None:
        organization = Organization(
            uuid=seed.uuid,
            name=seed.name,
            status="active",
        )
    else:
        organization.name = seed.name
        organization.status = "active"
    organization.save()
    return organization


def _ensure_user(seed: SeedUser, organization: Organization) -> User:
    now = utcnow()
    role_key = resolve_org_role_key(organization)
    user = User.objects(email=seed.email).first()
    roles = {role_key: [seed.role]}
    organizations = [organization]

    if user is None:
        user = User(
            uuid=seed.uuid,
            name=seed.name,
            email=seed.email,
            auth_provider="local",
            password_hash=generate_password_hash(seed.password),
            created_at=now,
            updated_at=now,
            is_super_admin=seed.is_super_admin,
            is_organisation_admin=seed.is_organisation_admin,
            is_email_verified=True,
            status="active",
            organizations=organizations,
            roles=roles,
        )
    else:
        user.uuid = seed.uuid
        user.name = seed.name
        user.email = seed.email
        user.auth_provider = "local"
        user.password_hash = generate_password_hash(seed.password)
        user.updated_at = now
        user.is_super_admin = seed.is_super_admin
        user.is_organisation_admin = seed.is_organisation_admin
        user.is_email_verified = True
        user.status = "active"
        user.organizations = organizations
        user.roles = roles

    user.save()
    return user


def seed_backend_accounts() -> list[User]:
    organization = _ensure_organization(_read_seed_organization())
    seeded = []
    for seed in _read_seed_users():
        seeded.append(_ensure_user(seed, organization))
    return seeded


if __name__ == "__main__":
    app = create_openapi_app({"TESTING": True})
    with app.app_context():
        organization = _ensure_organization(_read_seed_organization())
        print(f"✓ {organization.uuid} {organization.name}")
        accounts = seed_backend_accounts()
        for account in accounts:
            print(f"✓ {account.email}")
