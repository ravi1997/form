"""API-level regression tests for hierarchical resources CRUD."""

from __future__ import annotations

import json

from werkzeug.security import generate_password_hash

from app.models.user import User


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

    delete_project = client.delete(
        "/api/v1/projects/project-crud-0001",
        headers=headers,
    )
    assert delete_project.status_code == 200
    assert delete_project.get_json()["message"] == "project_deleted"


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
