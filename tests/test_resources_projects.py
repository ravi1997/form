"""Integration tests for project creation and role management permissions."""

from __future__ import annotations

import json
from werkzeug.security import generate_password_hash
from app.models.user import User, Organization
from app.models.form import Project


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


def _create_user(uuid: str, name: str, email: str) -> User:
    user = User(
        uuid=uuid,
        name=name,
        email=email,
        password_hash=generate_password_hash("Password123!"),
        auth_provider="local",
        status="active",
        is_email_verified=True,
    )
    user.save()
    return user


def test_project_creator_and_role_assignment(client, app_context):
    # Setup users
    org_admin = _create_user("p-admin-0001", "Org Admin", "padmin@example.com")
    org_editor = _create_user("p-editor-0001", "Org Editor", "peditor@example.com")
    org_viewer = _create_user("p-viewer-0001", "Org Viewer", "pviewer@example.com")
    org_viewer2 = _create_user("p-viewer-0002", "Org Viewer 2", "pviewer2@example.com")
    intruder = _create_user("p-intruder-0001", "Intruder", "pintruder@example.com")

    # Save Organization
    org = Organization(uuid="org-proj-0001", name="Proj Org").save()

    # Configure Org Admin
    org_admin.organizations = [org]
    org_admin.roles = {str(org.id): ["admin"]}
    org_admin.is_organisation_admin = True
    org_admin.save()
    org.admins = [org_admin]
    org.save()

    # Configure Org Editor
    org_editor.organizations = [org]
    org_editor.roles = {str(org.id): ["editor"]}
    org_editor.save()

    # Configure Org Viewer
    org_viewer.organizations = [org]
    org_viewer.roles = {str(org.id): ["viewer"]}
    org_viewer.save()

    # Configure Org Viewer 2
    org_viewer2.organizations = [org]
    org_viewer2.roles = {str(org.id): ["viewer"]}
    org_viewer2.save()

    # Get headers
    admin_headers = _auth_header(client, "padmin@example.com", "Password123!")
    editor_headers = _auth_header(client, "peditor@example.com", "Password123!")
    viewer_headers = _auth_header(client, "pviewer@example.com", "Password123!")
    intruder_headers = _auth_header(client, "pintruder@example.com", "Password123!")

    # 1. Editor creates a project -> 201 (success)
    proj_payload = {
        "uuid": "proj-test-0001",
        "name": "Editor Created Project",
        "versions": [{"uuid": "p-v1", "major": 1, "minor": 0, "patch": 0}],
        "admins": [],
        "members": [],
        "viewers": [],
        "forms": [],
        "organizations": [org.uuid],
        "tags": [],
        "status": "active"
    }
    res = client.post(
        "/api/v1/projects",
        data=json.dumps(proj_payload),
        headers=editor_headers,
        content_type="application/json"
    )
    assert res.status_code == 201
    created_proj = res.get_json()
    # Creator must be automatically added to project admins
    assert org_editor.uuid in created_proj["admins"]

    # 2. Org Viewer tries to create a project -> 403 (Forbidden)
    proj_payload2 = {
        "uuid": "proj-test-0002",
        "name": "Viewer Created Project",
        "versions": [{"uuid": "p-v2", "major": 1, "minor": 0, "patch": 0}],
        "admins": [],
        "members": [],
        "viewers": [],
        "forms": [],
        "organizations": [org.uuid],
        "tags": [],
        "status": "active"
    }
    res = client.post(
        "/api/v1/projects",
        data=json.dumps(proj_payload2),
        headers=viewer_headers,
        content_type="application/json"
    )
    assert res.status_code == 403

    # 3. Editor (now project admin) updates the project users -> 200 (Success)
    res = client.patch(
        "/api/v1/projects/proj-test-0001",
        data=json.dumps({
            "members": [org_admin.uuid]
        }),
        headers=editor_headers,
        content_type="application/json"
    )
    assert res.status_code == 200
    updated_proj = res.get_json()
    assert org_admin.uuid in updated_proj["members"]

    # 4. Org Admin (who is not in project.admins) manages roles for the project -> 200 (Success)
    res = client.patch(
        "/api/v1/projects/proj-test-0001",
        data=json.dumps({
            "viewers": [org_viewer.uuid]
        }),
        headers=admin_headers,
        content_type="application/json"
    )
    assert res.status_code == 200
    updated_proj = res.get_json()
    assert org_viewer.uuid in updated_proj["viewers"]

    # 5. Non-admin, non-project-admin tries to update the project -> 403
    res = client.patch(
        "/api/v1/projects/proj-test-0001",
        data=json.dumps({
            "name": "Hacked Name"
        }),
        headers=viewer_headers,
        content_type="application/json"
    )
    assert res.status_code == 403
