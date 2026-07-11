"""Integration tests for organization invitation and acceptance flow."""

from __future__ import annotations

import json
from uuid import uuid4
from werkzeug.security import generate_password_hash
from app.models.user import User, Organization, Invitation


def _auth_header(client, email: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        data=json.dumps({"email": email, "password": password}),
        content_type="application/json",
    )
    assert response.status_code == 200
    payload = response.get_json()
    token = payload.get("access_token")
    assert token
    return {"Authorization": f"Bearer {token}"}


def _create_user(uuid: str, name: str, email: str, is_super_admin: bool = False) -> User:
    user = User(
        uuid=uuid,
        name=name,
        email=email,
        password_hash=generate_password_hash("Password123!"),
        auth_provider="local",
        is_super_admin=is_super_admin,
    )
    user.save()
    return user


def test_invitation_lifecycle(client, app_context):
    # Setup users
    superadmin = _create_user("inv-super-0001", "Super Admin", "inv-super@example.com", is_super_admin=True)
    org_admin = _create_user("inv-orgadmin-0001", "Org Admin", "inv-orgadmin@example.com")
    invited_user = _create_user("inv-invited-0001", "Invited User", "invited@example.com")
    intruder_user = _create_user("inv-intruder-0001", "Intruder User", "intruder@example.com")

    # Get auth headers
    super_headers = _auth_header(client, "inv-super@example.com", "Password123!")
    orgadmin_headers = _auth_header(client, "inv-orgadmin@example.com", "Password123!")
    invited_headers = _auth_header(client, "invited@example.com", "Password123!")
    intruder_headers = _auth_header(client, "intruder@example.com", "Password123!")

    # Create Organization
    org = Organization(uuid="org-inv-0001", name="Invitation Org")
    org.admins = [org_admin]
    org.save()

    # Assign organization and role to org_admin so they can manage it
    org_admin.organizations = [org]
    org_admin.roles = {str(org.id): ["admin"]}
    org_admin.is_organisation_admin = True
    org_admin.save()

    # 1. Non-admin user tries to create invitation -> 403
    res = client.post(
        "/api/v1/organizations/org-inv-0001/invitations",
        data=json.dumps({"email": "invited@example.com", "role": "editor"}),
        headers=intruder_headers,
        content_type="application/json"
    )
    assert res.status_code == 403

    # 2. Org admin tries to invite someone as admin -> 403 (restricted to superadmin only)
    res = client.post(
        "/api/v1/organizations/org-inv-0001/invitations",
        data=json.dumps({"email": "invited@example.com", "role": "admin"}),
        headers=orgadmin_headers,
        content_type="application/json"
    )
    assert res.status_code == 403

    # 3. Org admin invites someone as editor -> 201
    res = client.post(
        "/api/v1/organizations/org-inv-0001/invitations",
        data=json.dumps({"email": "invited@example.com", "role": "editor"}),
        headers=orgadmin_headers,
        content_type="application/json"
    )
    assert res.status_code == 201
    invitation = res.get_json()
    assert invitation["status"] == "pending"
    assert invitation["role"] == "editor"
    assert "invitation_link" in invitation

    inv_uuid = invitation["uuid"]

    # 4. Intruder tries to accept the invitation -> 403
    res = client.post(
        f"/api/v1/invitations/{inv_uuid}/accept",
        headers=intruder_headers
    )
    assert res.status_code == 403

    # 5. Invited user accepts the invitation -> 200
    res = client.post(
        f"/api/v1/invitations/{inv_uuid}/accept",
        headers=invited_headers
    )
    assert res.status_code == 200
    assert res.get_json()["message"] == "invitation_accepted"

    # Verify db status of invited_user
    invited_user.reload()
    assert org in invited_user.organizations
    assert "editor" in invited_user.roles[str(org.id)]

    # 6. Trying to accept again -> 400
    res = client.post(
        f"/api/v1/invitations/{inv_uuid}/accept",
        headers=invited_headers
    )
    assert res.status_code == 400


def test_invitation_link_uses_public_base_url_when_configured(client, app_context):
    app_context.config["PUBLIC_BASE_URL"] = "https://public.example.com"
    superadmin = _create_user("inv-base-0001", "Super Admin", "base-admin@example.com", is_super_admin=True)
    org = Organization(uuid="org-base-0001", name="Base URL Org")
    org.admins = [superadmin]
    org.save()
    superadmin.organizations = [org]
    superadmin.roles = {str(org.id): ["admin"]}
    superadmin.save()
    headers = _auth_header(client, "base-admin@example.com", "Password123!")

    res = client.post(
        "/api/v1/organizations/org-base-0001/invitations",
        data=json.dumps({"email": "invited@example.com", "role": "editor"}),
        headers=headers,
        content_type="application/json",
    )
    assert res.status_code == 201
    assert res.get_json()["invitation_link"].startswith("https://public.example.com/")


def test_invitation_link_falls_back_to_request_context(client, app_context):
    superadmin = _create_user("inv-base-0002", "Super Admin", "request-admin@example.com", is_super_admin=True)
    org = Organization(uuid="org-base-0002", name="Request URL Org")
    org.admins = [superadmin]
    org.save()
    superadmin.organizations = [org]
    superadmin.roles = {str(org.id): ["admin"]}
    superadmin.save()
    headers = _auth_header(client, "request-admin@example.com", "Password123!")

    res = client.post(
        "/api/v1/organizations/org-base-0002/invitations",
        data=json.dumps({"email": "invited@example.com", "role": "editor"}),
        headers=headers,
        content_type="application/json",
    )
    assert res.status_code == 201
    assert res.get_json()["invitation_link"].startswith("http://localhost")
