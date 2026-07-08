import json

from werkzeug.security import generate_password_hash

from app.models.user import User


def _auth_header(client, email: str, password: str) -> dict:
    response = client.post(
        "/api/v1/auth/login",
        data=json.dumps({"email": email, "password": password}),
        content_type="application/json",
    )
    assert response.status_code == 200
    payload = response.get_json()
    token = payload.get("access_token") or payload.get("accessToken")
    assert token
    return {"Authorization": f"Bearer {token}"}


def _create_super_admin_user():
    user = User(
        uuid="ui-template-admin-0001",
        name="UI Template Admin",
        email="ui-template-admin@example.com",
        password_hash=generate_password_hash("StrongPass123!"),
        auth_provider="local",
        is_super_admin=True,
    )
    user.save()
    return user


def test_theme_and_layout_template_binding_and_effective_ui(client, app_context):
    _create_super_admin_user()
    headers = _auth_header(client, "ui-template-admin@example.com", "StrongPass123!")

    theme_payload = {
        "uuid": "theme-template-001",
        "name": "Ocean Theme",
        "scope_type": "global",
        "visibility": "public",
        "admins": [],
        "editors": [],
        "viewers": [],
        "status": "draft",
        "initial_revision": {
            "uuid": "theme-revision-001",
            "schema_version": 1,
            "config": {"palette": {"primary": "#0055AA"}},
            "status": "draft",
        },
    }
    theme_create = client.post(
        "/api/v1/ui/theme-templates",
        data=json.dumps(theme_payload),
        content_type="application/json",
        headers=headers,
    )
    assert theme_create.status_code == 201

    theme_publish = client.post(
        "/api/v1/ui/theme-templates/theme-template-001/revisions/theme-revision-001/publish",
        headers=headers,
    )
    assert theme_publish.status_code == 200

    layout_payload = {
        "uuid": "layout-template-001",
        "name": "Single Column",
        "scope_type": "global",
        "visibility": "public",
        "admins": [],
        "editors": [],
        "viewers": [],
        "status": "draft",
        "initial_revision": {
            "uuid": "layout-revision-001",
            "schema_version": 1,
            "config": {"grid": {"columns": 1}},
            "status": "draft",
        },
    }
    layout_create = client.post(
        "/api/v1/ui/layout-templates",
        data=json.dumps(layout_payload),
        content_type="application/json",
        headers=headers,
    )
    assert layout_create.status_code == 201

    layout_publish = client.post(
        "/api/v1/ui/layout-templates/layout-template-001/revisions/layout-revision-001/publish",
        headers=headers,
    )
    assert layout_publish.status_code == 200

    project_payload = {
        "uuid": "project-ui-0001",
        "name": "UI Project",
        "versions": [{"uuid": "proj-v1", "major": 1, "minor": 0, "patch": 0}],
        "admins": [],
        "members": [],
        "viewers": [],
        "forms": [],
        "organizations": [],
        "tags": [],
        "status": "active",
    }
    project_response = client.post(
        "/api/v1/projects",
        data=json.dumps(project_payload),
        content_type="application/json",
        headers=headers,
    )
    assert project_response.status_code == 201

    form_payload = {
        "uuid": "form-ui-0001",
        "versions": [{"uuid": "form-v1", "major": 1, "minor": 0, "patch": 0}],
        "sections": {"form-v1": []},
        "editors": [],
        "viewers": [],
        "reviewers": [],
        "approvers": [],
        "submitters": [],
        "validation_conditions": [],
        "validation_condition_messages": {},
        "child_sections": [],
        "tags": [],
        "status": "active",
        "theme_template_uuid": "theme-template-001",
        "theme_revision_uuid": "theme-revision-001",
        "layout_template_uuid": "layout-template-001",
        "layout_revision_uuid": "layout-revision-001",
        "ui_overrides": {"theme": {"palette": {"accent": "#FFD700"}}},
    }
    form_response = client.post(
        "/api/v1/projects/project-ui-0001/forms",
        data=json.dumps(form_payload),
        content_type="application/json",
        headers=headers,
    )
    assert form_response.status_code == 201

    effective_ui = client.get(
        "/api/v1/projects/project-ui-0001/forms/form-ui-0001/ui/effective",
        headers=headers,
    )
    assert effective_ui.status_code == 200
    effective_payload = effective_ui.get_json()
    assert effective_payload["theme_template_uuid"] == "theme-template-001"
    assert effective_payload["layout_template_uuid"] == "layout-template-001"
    assert effective_payload["theme_config"]["palette"]["primary"] == "#0055AA"
    assert effective_payload["layout_config"]["grid"]["columns"] == 1
    assert (
        effective_payload["effective_ui_config"]["theme"]["palette"]["accent"]
        == "#FFD700"
    )


def test_template_publish_requires_template_admin(client, app_context):
    super_admin = User(
        uuid="ui-template-super-0001",
        name="Super Admin",
        email="ui-template-super@example.com",
        password_hash=generate_password_hash("StrongPass123!"),
        auth_provider="local",
        is_super_admin=True,
    )
    super_admin.save()
    regular_user = User(
        uuid="ui-template-user-0001",
        name="Regular User",
        email="ui-template-user@example.com",
        password_hash=generate_password_hash("StrongPass123!"),
        auth_provider="local",
    )
    regular_user.save()

    admin_headers = _auth_header(
        client, "ui-template-super@example.com", "StrongPass123!"
    )
    user_headers = _auth_header(
        client, "ui-template-user@example.com", "StrongPass123!"
    )

    create_response = client.post(
        "/api/v1/ui/theme-templates",
        data=json.dumps(
            {
                "uuid": "theme-template-002",
                "name": "Private Theme",
                "scope_type": "global",
                "visibility": "private",
                "admins": ["ui-template-super-0001"],
                "editors": [],
                "viewers": [],
                "status": "draft",
                "initial_revision": {
                    "uuid": "theme-revision-002",
                    "schema_version": 1,
                    "config": {"palette": {"primary": "#111111"}},
                    "status": "draft",
                },
            }
        ),
        content_type="application/json",
        headers=admin_headers,
    )
    assert create_response.status_code == 201

    forbidden_publish = client.post(
        "/api/v1/ui/theme-templates/theme-template-002/revisions/theme-revision-002/publish",
        headers=user_headers,
    )
    assert forbidden_publish.status_code == 403
