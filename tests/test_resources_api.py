"""API-level regression tests for hierarchical resources CRUD."""

from __future__ import annotations

import json

from mongomock import MongoClient
from werkzeug.security import generate_password_hash

from app import create_openapi_app
from app.models.user import User, Organization


def _auth_header(client, email: str, password: str) -> dict[str, str]:
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


def _create_super_admin_user() -> User:
    user = User(
        uuid="resources-admin-0001",
        name="Resources Admin",
        email="resources-admin@example.com",
        password_hash=generate_password_hash("StrongPass123!"),
        auth_provider="local",
        is_super_admin=True,
    )
    user.save()
    return user


def _create_regular_user() -> User:
    user = User(
        uuid="resources-user-0001",
        name="Resources User",
        email="resources-user@example.com",
        password_hash=generate_password_hash("StrongPass123!"),
        auth_provider="local",
    )
    user.save()
    return user


def _create_organization(uuid: str, name: str, admins: list[User] | None = None) -> Organization:
    organization = Organization(
        uuid=uuid,
        name=name,
        admins=list(admins or []),
        status="active",
    )
    organization.save()
    return organization


def _create_project_payload(org_uuids: list[str]) -> dict:
    return {
        "uuid": "project-crud-0001",
        "name": "Project CRUD",
        "versions": [{"uuid": "project-v1", "major": 1, "minor": 0, "patch": 0}],
        "admins": [],
        "members": [],
        "viewers": [],
        "forms": [],
        "organizations": org_uuids,
        "tags": [],
        "status": "active",
    }


def test_project_creation_requires_access_to_every_organization(client, app_context):
    admin = _create_super_admin_user()
    user = _create_regular_user()
    admin_headers = _auth_header(client, "resources-admin@example.com", "StrongPass123!")
    user_headers = _auth_header(client, "resources-user@example.com", "StrongPass123!")

    org_a = _create_organization("org-auth-0001", "Org A", admins=[admin])
    org_b = _create_organization("org-auth-0002", "Org B", admins=[admin])

    admin.roles = {
        str(org_a.id): ["admin"],
        str(org_b.id): ["admin"],
    }
    admin.organizations = [org_a, org_b]
    admin.save()

    user.roles = {str(org_a.id): ["admin"]}
    user.organizations = [org_a]
    user.save()

    ok_payload = _create_project_payload([org_a.uuid, org_b.uuid])
    ok_response = client.post(
        "/api/v1/projects",
        data=json.dumps(ok_payload),
        content_type="application/json",
        headers=admin_headers,
    )
    assert ok_response.status_code == 201

    fail_payload = _create_project_payload([org_a.uuid, org_b.uuid])
    fail_payload["uuid"] = "project-crud-0002"
    fail_response = client.post(
        "/api/v1/projects",
        data=json.dumps(fail_payload),
        content_type="application/json",
        headers=user_headers,
    )
    assert fail_response.status_code == 403


def test_project_creation_rejects_mixed_authorization(client, app_context):
    _create_super_admin_user()
    user = _create_regular_user()
    user_headers = _auth_header(client, "resources-user@example.com", "StrongPass123!")

    org_a = _create_organization("org-auth-1001", "Org A")
    org_b = _create_organization("org-auth-1002", "Org B")
    user.roles = {str(org_a.id): ["admin"]}
    user.organizations = [org_a]
    user.save()

    mixed_payload = _create_project_payload([org_a.uuid, org_b.uuid])
    mixed_payload["uuid"] = "project-crud-1001"
    response = client.post(
        "/api/v1/projects",
        data=json.dumps(mixed_payload),
        content_type="application/json",
        headers=user_headers,
    )
    assert response.status_code == 403


def test_project_and_form_crud_lifecycle(client, app_context):
    _create_super_admin_user()
    headers = _auth_header(client, "resources-admin@example.com", "StrongPass123!")

    project_payload = {
        "uuid": "project-crud-0001",
        "name": "Project CRUD",
        "versions": [{"uuid": "project-v1", "major": 1, "minor": 0, "patch": 0}],
        "admins": [],
        "members": [],
        "viewers": [],
        "forms": [],
        "organizations": [],
        "tags": [],
        "status": "active",
    }
    create_project = client.post(
        "/api/v1/projects",
        data=json.dumps(project_payload),
        content_type="application/json",
        headers=headers,
    )
    assert create_project.status_code == 201

    duplicate_project = client.post(
        "/api/v1/projects",
        data=json.dumps(project_payload),
        content_type="application/json",
        headers=headers,
    )
    assert duplicate_project.status_code >= 400

    get_project = client.get("/api/v1/projects/project-crud-0001", headers=headers)
    assert get_project.status_code == 200
    assert get_project.get_json()["uuid"] == "project-crud-0001"

    update_project = client.patch(
        "/api/v1/projects/project-crud-0001",
        data=json.dumps({"name": "Project CRUD Updated"}),
        content_type="application/json",
        headers=headers,
    )
    assert update_project.status_code == 200
    assert update_project.get_json()["name"] == "Project CRUD Updated"

    form_payload = {
        "uuid": "form-crud-0001",
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
        "is_public": False,
        "status": "active",
    }
    create_form = client.post(
        "/api/v1/projects/project-crud-0001/forms",
        data=json.dumps(form_payload),
        content_type="application/json",
        headers=headers,
    )
    assert create_form.status_code == 201

    get_form = client.get(
        "/api/v1/projects/project-crud-0001/forms/form-crud-0001",
        headers=headers,
    )
    assert get_form.status_code == 200
    assert get_form.get_json()["uuid"] == "form-crud-0001"

    update_form = client.patch(
        "/api/v1/projects/project-crud-0001/forms/form-crud-0001",
        data=json.dumps({"tags": ["updated"]}),
        content_type="application/json",
        headers=headers,
    )
    assert update_form.status_code == 200
    assert "updated" in update_form.get_json()["tags"]

    delete_form = client.delete(
        "/api/v1/projects/project-crud-0001/forms/form-crud-0001",
        headers=headers,
    )
    assert delete_form.status_code == 200
    assert delete_form.get_json()["message"] == "form_deleted"

    deleted_form = client.get(
        "/api/v1/projects/project-crud-0001/forms/form-crud-0001",
        headers=headers,
    )
    assert deleted_form.status_code == 200
    assert deleted_form.get_json()["status"] == "deleted"

    delete_project = client.delete(
        "/api/v1/projects/project-crud-0001",
        headers=headers,
    )
    assert delete_project.status_code == 200
    assert delete_project.get_json()["message"] == "project_deleted"


def test_deleted_project_lifecycle_rejects_reads_and_writes(client, app_context):
    _create_super_admin_user()
    headers = _auth_header(client, "resources-admin@example.com", "StrongPass123!")

    project_payload = _create_project_payload([])
    project_payload["uuid"] = "project-deleted-0001"
    create_response = client.post(
        "/api/v1/projects",
        data=json.dumps(project_payload),
        content_type="application/json",
        headers=headers,
    )
    assert create_response.status_code == 201

    delete_response = client.delete("/api/v1/projects/project-deleted-0001", headers=headers)
    assert delete_response.status_code == 200

    read_response = client.get("/api/v1/projects/project-deleted-0001", headers=headers)
    assert read_response.status_code == 404

    update_response = client.patch(
        "/api/v1/projects/project-deleted-0001",
        data=json.dumps({"name": "should fail"}),
        content_type="application/json",
        headers=headers,
    )
    assert update_response.status_code == 404

    version_response = client.post(
        "/api/v1/projects/project-deleted-0001/versions",
        data=json.dumps({"uuid": "project-deleted-v2", "major": 2, "minor": 0, "patch": 0}),
        content_type="application/json",
        headers=headers,
    )
    assert version_response.status_code == 404


def test_section_question_choice_lifecycle_and_anonymous_access(client, app_context):
    _create_super_admin_user()
    headers = _auth_header(client, "resources-admin@example.com", "StrongPass123!")

    anonymous = client.get("/api/v1/projects")
    assert anonymous.status_code == 401

    project_payload = {
        "uuid": "project-nested-0001",
        "name": "Project Nested",
        "versions": [{"uuid": "project-v1-nested", "major": 1, "minor": 0, "patch": 0}],
        "admins": [],
        "members": [],
        "viewers": [],
        "forms": [],
        "organizations": [],
        "tags": [],
        "status": "active",
    }
    assert (
        client.post(
            "/api/v1/projects",
            data=json.dumps(project_payload),
            content_type="application/json",
            headers=headers,
        ).status_code
        == 201
    )

    form_payload = {
        "uuid": "form-nested-0001",
        "versions": [{"uuid": "form-v1-nested", "major": 1, "minor": 0, "patch": 0}],
        "sections": {"form-v1-nested": []},
        "editors": [],
        "viewers": [],
        "reviewers": [],
        "approvers": [],
        "submitters": [],
        "validation_conditions": [],
        "validation_condition_messages": {},
        "child_sections": [],
        "tags": [],
        "is_public": False,
        "status": "active",
    }
    assert (
        client.post(
            "/api/v1/projects/project-nested-0001/forms",
            data=json.dumps(form_payload),
            content_type="application/json",
            headers=headers,
        ).status_code
        == 201
    )

    duplicate_form = client.post(
        "/api/v1/projects/project-nested-0001/forms",
        data=json.dumps(form_payload),
        content_type="application/json",
        headers=headers,
    )
    assert duplicate_form.status_code >= 400

    _create_regular_user()
    unauthorized_headers = _auth_header(
        client, "resources-user@example.com", "StrongPass123!"
    )
    assert (
        client.get(
            "/api/v1/projects/project-nested-0001",
            headers=unauthorized_headers,
        ).status_code
        == 403
    )

    section_payload = {
        "uuid": "section-nested-0001",
        "versions": [{"uuid": "section-v1-nested", "major": 1, "minor": 0, "patch": 0}],
        "questions": {},
        "add_button": True,
        "is_repeatable": False,
        "validation_conditions": [],
        "validation_condition_messages": {},
        "tags": [],
        "status": "active",
    }
    create_section = client.post(
        "/api/v1/projects/project-nested-0001/forms/form-nested-0001/sections?version_uuid=form-v1-nested",
        data=json.dumps(section_payload),
        content_type="application/json",
        headers=headers,
    )
    assert create_section.status_code == 201

    invalid_section = client.post(
        "/api/v1/projects/project-nested-0001/forms/form-nested-0001/sections?version_uuid=missing-version",
        data=json.dumps(section_payload),
        content_type="application/json",
        headers=headers,
    )
    assert invalid_section.status_code == 400

    get_section = client.get(
        "/api/v1/projects/project-nested-0001/forms/form-nested-0001/sections/section-nested-0001",
        headers=headers,
    )
    assert get_section.status_code == 200

    update_section = client.patch(
        "/api/v1/projects/project-nested-0001/forms/form-nested-0001/sections/section-nested-0001",
        data=json.dumps({"title": "Updated section"}),
        content_type="application/json",
        headers=headers,
    )
    assert update_section.status_code == 200

    question_payload = {
        "uuid": "question-nested-0001",
        "versions": [
            {"uuid": "question-v1-nested", "major": 1, "minor": 0, "patch": 0}
        ],
        "type": "text",
        "label": "Question",
        "choices": [],
        "validation_conditions": [],
        "validation_condition_messages": {},
        "visibility_conditions": [],
        "actions": [],
        "tags": [],
        "status": "active",
    }
    create_question = client.post(
        "/api/v1/projects/project-nested-0001/forms/form-nested-0001/sections/section-nested-0001/questions?version_uuid=section-v1-nested",
        data=json.dumps(question_payload),
        content_type="application/json",
        headers=headers,
    )
    assert create_question.status_code == 201

    duplicate_section = client.post(
        "/api/v1/projects/project-nested-0001/forms/form-nested-0001/sections?version_uuid=form-v1-nested",
        data=json.dumps(section_payload),
        content_type="application/json",
        headers=headers,
    )
    assert duplicate_section.status_code >= 400

    duplicate_question = client.post(
        "/api/v1/projects/project-nested-0001/forms/form-nested-0001/sections/section-nested-0001/questions?version_uuid=section-v1-nested",
        data=json.dumps(question_payload),
        content_type="application/json",
        headers=headers,
    )
    assert duplicate_question.status_code >= 400

    get_question = client.get(
        "/api/v1/projects/project-nested-0001/forms/form-nested-0001/sections/section-nested-0001/questions/question-nested-0001",
        headers=headers,
    )
    assert get_question.status_code == 200

    update_question = client.patch(
        "/api/v1/projects/project-nested-0001/forms/form-nested-0001/sections/section-nested-0001/questions/question-nested-0001",
        data=json.dumps({"label": "Updated question"}),
        content_type="application/json",
        headers=headers,
    )
    assert update_question.status_code == 200

    choice_payload = {"uuid": "choice-nested-0001", "label": "Choice", "value": "A"}
    create_choice = client.post(
        "/api/v1/projects/project-nested-0001/forms/form-nested-0001/sections/section-nested-0001/questions/question-nested-0001/choices",
        data=json.dumps(choice_payload),
        content_type="application/json",
        headers=headers,
    )
    assert create_choice.status_code == 201

    duplicate_choice = client.post(
        "/api/v1/projects/project-nested-0001/forms/form-nested-0001/sections/section-nested-0001/questions/question-nested-0001/choices",
        data=json.dumps(choice_payload),
        content_type="application/json",
        headers=headers,
    )
    assert duplicate_choice.status_code >= 400

    get_choice = client.get(
        "/api/v1/projects/project-nested-0001/forms/form-nested-0001/sections/section-nested-0001/questions/question-nested-0001/choices/choice-nested-0001",
        headers=headers,
    )
    assert get_choice.status_code == 200

    update_choice = client.patch(
        "/api/v1/projects/project-nested-0001/forms/form-nested-0001/sections/section-nested-0001/questions/question-nested-0001/choices/choice-nested-0001",
        data=json.dumps({"label": "Updated choice"}),
        content_type="application/json",
        headers=headers,
    )
    assert update_choice.status_code == 200

    missing_question_choice = client.post(
        "/api/v1/projects/project-nested-0001/forms/form-nested-0001/sections/section-nested-0001/questions/question-missing/choices",
        data=json.dumps(choice_payload),
        content_type="application/json",
        headers=headers,
    )
    assert missing_question_choice.status_code == 404

    assert (
        client.delete(
            "/api/v1/projects/project-nested-0001/forms/form-nested-0001/sections/section-nested-0001/questions/question-nested-0001/choices/choice-nested-0001",
            headers=headers,
        ).status_code
        == 200
    )
    assert (
        client.delete(
            "/api/v1/projects/project-nested-0001/forms/form-nested-0001/sections/section-nested-0001/questions/question-nested-0001",
            headers=headers,
        ).status_code
        == 200
    )
    assert (
        client.delete(
            "/api/v1/projects/project-nested-0001/forms/form-nested-0001/sections/section-nested-0001",
            headers=headers,
        ).status_code
        == 200
    )

    repeat_delete_section = client.delete(
        "/api/v1/projects/project-nested-0001/forms/form-nested-0001/sections/section-nested-0001",
        headers=headers,
    )
    assert repeat_delete_section.status_code == 404

    deleted_question = client.get(
        "/api/v1/projects/project-nested-0001/forms/form-nested-0001/sections/section-nested-0001/questions/question-nested-0001",
        headers=headers,
    )
    assert deleted_question.status_code == 404

    deleted_choice = client.get(
        "/api/v1/projects/project-nested-0001/forms/form-nested-0001/sections/section-nested-0001/questions/question-nested-0001/choices/choice-nested-0001",
        headers=headers,
    )
    assert deleted_choice.status_code == 404


def test_form_submission_routes_require_public_flag_for_anonymous_access(
    client, app_context
):
    _create_super_admin_user()
    headers = _auth_header(client, "resources-admin@example.com", "StrongPass123!")

    project_payload = {
        "uuid": "project-submit-0001",
        "name": "Project Submit",
        "versions": [{"uuid": "project-v1-submit", "major": 1, "minor": 0, "patch": 0}],
        "admins": [],
        "members": [],
        "viewers": [],
        "forms": [],
        "organizations": [],
        "tags": [],
        "status": "active",
    }
    assert (
        client.post(
            "/api/v1/projects",
            data=json.dumps(project_payload),
            content_type="application/json",
            headers=headers,
        ).status_code
        == 201
    )

    private_form_payload = {
        "uuid": "form-submit-private-0001",
        "versions": [
            {"uuid": "form-v1-submit-private", "major": 1, "minor": 0, "patch": 0}
        ],
        "sections": {"form-v1-submit-private": []},
        "editors": [],
        "viewers": [],
        "reviewers": [],
        "approvers": [],
        "submitters": [],
        "validation_conditions": [],
        "validation_condition_messages": {},
        "child_sections": [],
        "tags": [],
        "is_public": False,
        "status": "active",
    }
    assert (
        client.post(
            "/api/v1/projects/project-submit-0001/forms",
            data=json.dumps(private_form_payload),
            content_type="application/json",
            headers=headers,
        ).status_code
        == 201
    )

    private_submission_payload = {
        "uuid": "response-private-0001",
        "form": "form-submit-private-0001",
        "form_uuid": "form-submit-private-0001",
        "form_version_uuid": "form-v1-submit-private",
        "project": "project-submit-0001",
        "project_uuid": "project-submit-0001",
        "responses": [],
        "response_map": {},
        "metadata": {},
    }
    private_public_submit = client.post(
        "/api/v1/public/projects/project-submit-0001/forms/form-submit-private-0001/responses",
        data=json.dumps(private_submission_payload),
        content_type="application/json",
    )
    assert private_public_submit.status_code == 403

    public_form_payload = {
        "uuid": "form-submit-public-0001",
        "versions": [
            {"uuid": "form-v1-submit-public", "major": 1, "minor": 0, "patch": 0}
        ],
        "sections": {"form-v1-submit-public": []},
        "editors": [],
        "viewers": [],
        "reviewers": [],
        "approvers": [],
        "submitters": [],
        "validation_conditions": [],
        "validation_condition_messages": {},
        "child_sections": [],
        "tags": [],
        "is_public": True,
        "status": "active",
    }
    assert (
        client.post(
            "/api/v1/projects/project-submit-0001/forms",
            data=json.dumps(public_form_payload),
            content_type="application/json",
            headers=headers,
        ).status_code
        == 201
    )

    public_submission_payload = {
        "uuid": "response-public-0001",
        "form": "form-submit-public-0001",
        "form_uuid": "form-submit-public-0001",
        "form_version_uuid": "form-v1-submit-public",
        "project": "project-submit-0001",
        "project_uuid": "project-submit-0001",
        "responses": [],
        "response_map": {},
        "metadata": {},
    }
    public_submit = client.post(
        "/api/v1/public/projects/project-submit-0001/forms/form-submit-public-0001/responses",
        data=json.dumps(public_submission_payload),
        content_type="application/json",
    )
    assert public_submit.status_code == 201
    public_payload = public_submit.get_json()
    assert public_payload["uuid"] == "response-public-0001"
    assert public_payload["form_uuid"] == "form-submit-public-0001"
    assert public_payload["project_uuid"] == "project-submit-0001"
    assert public_payload["status"] == "submitted"

    authenticated_submit = client.post(
        "/api/v1/projects/project-submit-0001/forms/form-submit-public-0001/responses",
        data=json.dumps(
            {**public_submission_payload, "uuid": "response-auth-0001"}
        ),
        content_type="application/json",
        headers=headers,
    )
    assert authenticated_submit.status_code == 201


def test_openapi_includes_form_submission_routes_and_public_flag():
    app = create_openapi_app(
        {
            "TESTING": True,
            "MONGODB_SETTINGS": {
                "db": "test_form_db",
                "host": "mongodb://localhost/test_form_db",
                "mongo_client_class": MongoClient,
                "connect": False,
                "uuidRepresentation": "standard",
            },
            "JWT_SECRET_KEY": "test-secret-key-do-not-use-in-production",
            "JWT_ALGORITHM": "HS256",
            "JWT_ACCESS_TOKEN_EXPIRES_MINUTES": 30,
            "JWT_REFRESH_TOKEN_EXPIRES_DAYS": 7,
            "AUTH_RATE_LIMIT_LOGIN_MAX": 10,
            "AUTH_RATE_LIMIT_LOGIN_WINDOW_SECONDS": 60,
            "AUTH_RATE_LIMIT_REFRESH_MAX": 20,
            "AUTH_RATE_LIMIT_REFRESH_WINDOW_SECONDS": 60,
            "AUTH_RATE_LIMIT_LOGOUT_MAX": 20,
            "AUTH_RATE_LIMIT_LOGOUT_WINDOW_SECONDS": 60,
            "ENABLE_AUDIT_LOGS": False,
            "CELERY_TASK_ALWAYS_EAGER": True,
            "CELERY_TASK_EAGER_PROPAGATES": True,
            "CELERY_BROKER_URL": "memory://",
            "CELERY_RESULT_BACKEND": "cache+memory://",
        }
    )
    client = app.test_client()

    spec = client.get("/openapi/openapi.json")
    assert spec.status_code == 200
    payload = spec.get_json()

    assert "/api/v1/projects/{project_uuid}/forms/{form_uuid}/responses" in payload[
        "paths"
    ]
    assert "/api/v1/public/projects/{project_uuid}/forms/{form_uuid}/responses" in payload[
        "paths"
    ]
    assert (
        "is_public"
        in payload["components"]["schemas"]["FormOutput"]["properties"]
    )
    assert (
        "is_public"
        in payload["components"]["schemas"]["FormCreateInput"]["properties"]
    )
    assert (
        "is_public"
        in payload["components"]["schemas"]["FormUpdateInput"]["properties"]
    )
