"""API-level tests for organization CRUD endpoints."""

from __future__ import annotations

import json
from werkzeug.security import generate_password_hash
from app.models.user import User, Organization


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


def _create_super_admin_user() -> User:
    user = User(
        uuid="orgs-admin-0001",
        name="Orgs Admin",
        email="orgs-admin@example.com",
        password_hash=generate_password_hash("StrongPass123!"),
        auth_provider="local",
        is_super_admin=True,
    )
    user.save()
    return user


def _create_regular_user() -> User:
    user = User(
        uuid="orgs-user-0001",
        name="Orgs User",
        email="orgs-user@example.com",
        password_hash=generate_password_hash("StrongPass123!"),
        auth_provider="local",
    )
    user.save()
    return user


def test_organization_crud_lifecycle(client, app_context):
    admin = _create_super_admin_user()
    regular = _create_regular_user()
    admin_headers = _auth_header(client, "orgs-admin@example.com", "StrongPass123!")
    user_headers = _auth_header(client, "orgs-user@example.com", "StrongPass123!")

    # 1. Create Organization (Super Admin)
    org_payload = {
        "uuid": "org-test-0001",
        "name": "Test Organization",
        "admins": [regular.uuid],
        "status": "active"
    }

    # Non-admin should not be allowed to create
    res = client.post(
        "/api/v1/organizations",
        data=json.dumps(org_payload),
        headers=user_headers,
        content_type="application/json"
    )
    assert res.status_code == 403

    # Admin should be allowed
    res = client.post(
        "/api/v1/organizations",
        data=json.dumps(org_payload),
        headers=admin_headers,
        content_type="application/json"
    )
    assert res.status_code == 201
    created_org = res.get_json()
    assert created_org["uuid"] == "org-test-0001"
    assert created_org["name"] == "Test Organization"
    assert created_org["admins"] == [regular.uuid]

    # 2. Get Organization
    # Regular user cannot get (403)
    res = client.get("/api/v1/organizations/org-test-0001", headers=user_headers)
    assert res.status_code == 403

    # Superadmin can get (200)
    res = client.get("/api/v1/organizations/org-test-0001", headers=admin_headers)
    assert res.status_code == 200
    got_org = res.get_json()
    assert got_org["name"] == "Test Organization"

    # 3. List Organizations
    # Non-authenticated user (anonymous) can list
    res = client.get("/api/v1/organizations")
    assert res.status_code == 200
    list_orgs = res.get_json()
    assert len(list_orgs["items"]) >= 1
    assert any(item["uuid"] == "org-test-0001" for item in list_orgs["items"])

    # 4. Update Organization
    update_payload = {
        "name": "Updated Organization Name",
        "admins": []
    }

    # Non-admin should not be allowed to update
    res = client.patch(
        "/api/v1/organizations/org-test-0001",
        data=json.dumps(update_payload),
        headers=user_headers,
        content_type="application/json"
    )
    assert res.status_code == 403

    # Admin should be allowed
    res = client.patch(
        "/api/v1/organizations/org-test-0001",
        data=json.dumps(update_payload),
        headers=admin_headers,
        content_type="application/json"
    )
    assert res.status_code == 200
    updated_org = res.get_json()
    assert updated_org["name"] == "Updated Organization Name"
    assert updated_org["admins"] == []

    # 4.5. Admin Management
    # List admins - initially forbidden for non-admin of organization
    res = client.get("/api/v1/organizations/org-test-0001/admins", headers=user_headers)
    assert res.status_code == 403

    # But allowed for superadmin
    res = client.get("/api/v1/organizations/org-test-0001/admins", headers=admin_headers)
    assert res.status_code == 200
    assert len(res.get_json()["admins"]) == 0

    # Add admin
    # Non-admin should not be allowed
    res = client.post(
        "/api/v1/organizations/org-test-0001/admins",
        data=json.dumps({"user_uuid": regular.uuid}),
        headers=user_headers,
        content_type="application/json"
    )
    assert res.status_code == 403

    # Admin should be allowed
    res = client.post(
        "/api/v1/organizations/org-test-0001/admins",
        data=json.dumps({"user_uuid": regular.uuid}),
        headers=admin_headers,
        content_type="application/json"
    )
    assert res.status_code == 200
    assert len(res.get_json()["admins"]) == 1
    assert res.get_json()["admins"][0]["uuid"] == regular.uuid

    # Check updated user model values
    regular.reload()
    assert regular.is_organisation_admin is True
    org_id_key = str(Organization.objects(uuid="org-test-0001").first().id)
    assert org_id_key in regular.roles
    assert "admin" in regular.roles[org_id_key]

    # Under new rules, even organization admins cannot list admins (only superadmin / global_admin can)
    res = client.get("/api/v1/organizations/org-test-0001/admins", headers=user_headers)
    assert res.status_code == 403

    # Remove admin
    # Non-admin should not be allowed
    res = client.delete(
        f"/api/v1/organizations/org-test-0001/admins/{regular.uuid}",
        headers=user_headers
    )
    assert res.status_code == 403

    # Admin should be allowed
    res = client.delete(
        f"/api/v1/organizations/org-test-0001/admins/{regular.uuid}",
        headers=admin_headers
    )
    assert res.status_code == 200
    assert len(res.get_json()["admins"]) == 0

    regular.reload()
    assert regular.is_organisation_admin is False

    # 5. Delete Organization
    # Non-admin should not be allowed to delete
    res = client.delete("/api/v1/organizations/org-test-0001", headers=user_headers)
    assert res.status_code == 403

    # Admin should be allowed
    res = client.delete("/api/v1/organizations/org-test-0001", headers=admin_headers)
    assert res.status_code == 200
    assert res.get_json()["message"] == "organization_deleted"

    # Verify status changed to deleted
    res = client.get("/api/v1/organizations/org-test-0001", headers=admin_headers)
    assert res.status_code == 200
    deleted_org = res.get_json()
    assert deleted_org["status"] == "deleted"
