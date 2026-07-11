"""API-level tests for admin user management and verification lifecycle."""

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
        uuid="usrmgr-admin-0001",
        name="Usrmgr Admin",
        email="usrmgr-admin@example.com",
        password_hash=generate_password_hash("StrongPass123!"),
        auth_provider="local",
        is_super_admin=True,
    )
    user.save()
    return user


def test_user_verification_lifecycle(client, app_context):
    app_context.config['PROPAGATE_EXCEPTIONS'] = True
    admin = _create_super_admin_user()
    admin_headers = _auth_header(client, "usrmgr-admin@example.com", "StrongPass123!")

    # 1. Register a new user (Self registration)
    reg_payload = {
        "email": "selfuser@example.com",
        "name": "Self User",
        "password": "SecurePass123!",
    }
    res = client.post(
        "/api/v1/auth/register",
        data=json.dumps(reg_payload),
        content_type="application/json"
    )
    assert res.status_code == 201
    
    # 2. Verify self-registered user has status "unverified"
    user_db = User.objects(email="selfuser@example.com").first()
    assert user_db is not None
    assert user_db.status == "unverified"

    # 3. Attempting to log in as unverified user should fail
    login_payload = {
        "email": "selfuser@example.com",
        "password": "SecurePass123!"
    }
    res = client.post(
        "/api/v1/auth/login",
        data=json.dumps(login_payload),
        content_type="application/json"
    )
    assert res.status_code == 401
    assert "unverified" in res.get_json()["message"]

    # 4. Superadmin creates an organization admin - verified by default
    org = Organization(uuid="org-usrmgr-0001", name="Usrmgr Org").save()
    
    new_org_admin_payload = {
        "uuid": "new-org-admin-0001",
        "name": "New Org Admin",
        "email": "neworgadmin@example.com",
        "password_hash": generate_password_hash("Password123!"),
        "organizations": [org.uuid],
        "roles": {org.uuid: ["admin"]},
        "is_organisation_admin": True,
        "auth_provider": "local"
    }
    res = client.post(
        "/api/v1/auth/admin/users",
        data=json.dumps(new_org_admin_payload),
        headers=admin_headers,
        content_type="application/json"
    )
    assert res.status_code == 201
    created_org_admin = res.get_json()
    assert created_org_admin["status"] == "active"
    assert created_org_admin["is_email_verified"] is True

    # Verify self-registered user has no roles
    assert user_db.roles == {}

    # Associate user with the organization so the org admin can list them
    user_db.organizations = [org]
    user_db.save()

    # Log in as the new organization admin to verify the self-registered user
    org_admin_headers = _auth_header(client, "neworgadmin@example.com", "Password123!")

    # Org admin lists users (should see the self-registered user who belongs to the same org)
    res = client.get("/api/v1/auth/admin/users", headers=org_admin_headers)
    assert res.status_code == 200
    user_list = res.get_json()
    assert any(u["email"] == "selfuser@example.com" for u in user_list["items"])

    # Org admin verifies the user and assigns roles
    verify_payload = {
        "organization_uuid": org.uuid,
        "roles": ["editor"]
    }
    res = client.post(
        f"/api/v1/auth/admin/users/{user_db.uuid}/verify",
        data=json.dumps(verify_payload),
        headers=org_admin_headers,
        content_type="application/json"
    )
    assert res.status_code == 200
    res_data = res.get_json()
    assert res_data["status"] == "active"
    assert "editor" in res_data["roles"][org.uuid]

    # 6. Now the verified user can successfully log in!
    res = client.post(
        "/api/v1/auth/login",
        data=json.dumps(login_payload),
        content_type="application/json"
    )
    assert res.status_code == 200
    assert "access_token" in res.get_json()


def test_must_change_password_blocks_admin_routes(client, app_context):
    admin = _create_super_admin_user()
    admin_headers = _auth_header(client, "usrmgr-admin@example.com", "StrongPass123!")

    target = User(
        uuid="usrmgr-target-0001",
        name="Target User",
        email="target@example.com",
        password_hash=generate_password_hash("TargetPass123!"),
        auth_provider="local",
        must_change_password=True,
    )
    target.save()

    response = client.get(
        f"/api/v1/auth/admin/users/{target.uuid}", headers=admin_headers
    )
    assert response.status_code == 401
    assert "password change required" in response.get_json()["message"].lower()


def test_admin_bulk_must_change_password_route(client, app_context):
    admin = _create_super_admin_user()
    admin_headers = _auth_header(client, "usrmgr-admin@example.com", "StrongPass123!")

    user1 = User(
        uuid="usrmgr-bulk-0001",
        name="Bulk One",
        email="bulk1@example.com",
        password_hash=generate_password_hash("BulkPass123!"),
        auth_provider="local",
    )
    user1.save()
    user2 = User(
        uuid="usrmgr-bulk-0002",
        name="Bulk Two",
        email="bulk2@example.com",
        password_hash=generate_password_hash("BulkPass123!"),
        auth_provider="local",
    )
    user2.save()

    response = client.post(
        "/api/v1/auth/admin/users/bulk/must-change-password",
        headers=admin_headers,
        data=json.dumps(
            {"user_uuids": [user1.uuid, user2.uuid], "must_change_password": True}
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert User.objects.get(uuid=user1.uuid).must_change_password is True
    assert User.objects.get(uuid=user2.uuid).must_change_password is True
