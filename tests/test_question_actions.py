import json

import pytest
from mongoengine.errors import ValidationError
from werkzeug.security import generate_password_hash

from app.models.form import (
    ActionDefinition,
    ActionStep,
    Form,
    FormResponse,
    Project,
    Question,
    Section,
    Version,
)
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


@pytest.fixture
def super_admin_user(app_context):
    user = User(
        uuid="question-action-admin-0001",
        name="Question Action Admin",
        email="question-action-admin@example.com",
        password_hash=generate_password_hash("StrongPass123!"),
        auth_provider="local",
        is_super_admin=True,
    )
    user.save()
    return user


def test_question_rejects_duplicate_action_ids(app_context):
    question = Question(
        uuid="question-action-model-0001",
        versions=[Version(uuid="v1")],
        type="button",
        label="Action Question",
        actions=[
            ActionDefinition(
                id="duplicate",
                label="Primary",
                steps=[
                    ActionStep(id="step-1", target="frontend", type="ui.open_modal")
                ],
            ),
            ActionDefinition(
                id="duplicate",
                label="Secondary",
                steps=[
                    ActionStep(
                        id="step-2",
                        target="backend",
                        type="response.status.set",
                        config={"status": "submitted"},
                    )
                ],
            ),
        ],
    )

    with pytest.raises(ValidationError):
        question.save()


def test_hybrid_question_action_trigger_and_idempotency(
    client, app_context, super_admin_user
):
    headers = _auth_header(
        client,
        "question-action-admin@example.com",
        "StrongPass123!",
    )

    project_payload = {
        "uuid": "project-action-0001",
        "name": "Project Action",
        "versions": [{"uuid": "proj-v1", "major": 1, "minor": 0, "patch": 0}],
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
        "uuid": "form-action-0001",
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
    assert (
        client.post(
            "/api/v1/projects/project-action-0001/forms",
            data=json.dumps(form_payload),
            content_type="application/json",
            headers=headers,
        ).status_code
        == 201
    )

    section_payload = {
        "uuid": "section-action-0001",
        "versions": [{"uuid": "section-v1", "major": 1, "minor": 0, "patch": 0}],
        "questions": {"section-v1": []},
        "title": "Action Section",
        "validation_conditions": [],
        "validation_condition_messages": {},
        "tags": [],
        "status": "active",
    }
    assert (
        client.post(
            "/api/v1/projects/project-action-0001/forms/form-action-0001/sections?version_uuid=form-v1",
            data=json.dumps(section_payload),
            content_type="application/json",
            headers=headers,
        ).status_code
        == 201
    )

    question_payload = {
        "uuid": "question-action-0001",
        "versions": [{"uuid": "question-v1", "major": 1, "minor": 0, "patch": 0}],
        "type": "button",
        "label": "Submit Response",
        "validation_conditions": [],
        "validation_condition_messages": {},
        "visibility_conditions": [],
        "tags": [],
        "choices": [],
        "status": "active",
        "actions": [
            {
                "id": "submit-response",
                "label": "Submit Response",
                "button_variant": "primary",
                "icon": "send",
                "trigger": "click",
                "confirmation_message": "Submit now?",
                "steps": [
                    {
                        "id": "step-ui-toast",
                        "target": "frontend",
                        "type": "ui.toast",
                        "config": {"message": "Submitting"},
                    },
                    {
                        "id": "step-status",
                        "target": "backend",
                        "type": "response.status.set",
                        "config": {"status": "submitted"},
                    },
                    {
                        "id": "step-metadata",
                        "target": "backend",
                        "type": "response.metadata.merge",
                        "config": {"patch": {"source": "question-action"}},
                    },
                    {
                        "id": "step-ui-nav",
                        "target": "frontend",
                        "type": "ui.navigate",
                        "config": {"to": "/submitted"},
                    },
                ],
            }
        ],
    }
    create_question = client.post(
        "/api/v1/projects/project-action-0001/forms/form-action-0001/sections/section-action-0001/questions?version_uuid=section-v1",
        data=json.dumps(question_payload),
        content_type="application/json",
        headers=headers,
    )
    assert create_question.status_code == 201
    created_question = create_question.get_json()
    assert created_question["actions"][0]["id"] == "submit-response"
    assert created_question["actions"][0]["label"] == "Submit Response"
    assert created_question["actions"][0]["steps"][0]["type"] == "ui.toast"

    form = Form.objects.get(uuid="form-action-0001")
    response = FormResponse(
        uuid="response-action-0001",
        form=form,
        form_uuid=form.uuid,
        form_version_uuid="form-v1",
        submitted_by=super_admin_user,
        submitted_by_uuid=super_admin_user.uuid,
        status="draft",
    )
    response.save()

    trigger_payload = {
        "response_uuid": "response-action-0001",
        "confirmed": True,
        "idempotency_key": "idem-action-001",
        "context": {"note": "submit response"},
        "client_state": {"screen": "builder"},
    }
    trigger_response = client.post(
        "/api/v1/projects/project-action-0001/forms/form-action-0001/sections/section-action-0001/questions/question-action-0001/actions/submit-response/trigger",
        data=json.dumps(trigger_payload),
        content_type="application/json",
        headers=headers,
    )
    assert trigger_response.status_code == 200
    trigger_data = trigger_response.get_json()
    assert trigger_data["idempotent"] is False
    assert trigger_data["execution"]["status"] == "success"
    assert len(trigger_data["frontend_steps"]) == 2
    assert (
        trigger_data["execution"]["step_results"][0]["output"]["deferred_to_frontend"]
        is True
    )

    updated_response = FormResponse.objects.get(uuid="response-action-0001")
    assert updated_response.status == "submitted"
    assert updated_response.metadata["source"] == "question-action"

    second_trigger = client.post(
        "/api/v1/projects/project-action-0001/forms/form-action-0001/sections/section-action-0001/questions/question-action-0001/actions/submit-response/trigger",
        data=json.dumps(trigger_payload),
        content_type="application/json",
        headers=headers,
    )
    assert second_trigger.status_code == 200
    second_data = second_trigger.get_json()
    assert second_data["idempotent"] is True

    execution_list = client.get(
        "/api/v1/projects/project-action-0001/forms/form-action-0001/responses/response-action-0001/action-executions",
        headers=headers,
    )
    assert execution_list.status_code == 200
    execution_payload = execution_list.get_json()
    assert execution_payload["total_items"] == 1
    assert execution_payload["items"][0]["action_id"] == "submit-response"


def test_legacy_action_fields_are_exposed_as_actions(
    client, app_context, super_admin_user
):
    headers = _auth_header(
        client,
        "question-action-admin@example.com",
        "StrongPass123!",
    )

    form = Form(
        uuid="form-legacy-action-0001",
        versions=[Version(uuid="v1")],
        sections={"v1": []},
    )
    form.save()
    section = Section(
        uuid="section-legacy-action-0001",
        versions=[Version(uuid="section-v1")],
        questions={"section-v1": ["question-legacy-action-0001"]},
    )
    section.save()
    question = Question(
        uuid="question-legacy-action-0001",
        versions=[Version(uuid="question-v1")],
        type="button",
        label="Legacy Action",
        isAction=True,
        actionType="ui.open_modal",
        actionLabel="Open",
        actionButtonType="secondary",
        actionIcon="bolt",
    )
    question.save()
    form.sections = {"v1": [section.uuid]}
    form.save()
    project = Project(
        uuid="project-legacy-action-0001",
        name="Legacy Project",
        versions=[Version(uuid="proj-v1")],
        forms=[form],
    )
    project.save()

    response = client.get(
        "/api/v1/projects/project-legacy-action-0001/forms/form-legacy-action-0001/sections/section-legacy-action-0001/questions/question-legacy-action-0001",
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["actions"] == []


def test_action_visibility_condition_rejected_when_false(
    client, app_context, super_admin_user
):
    """Action trigger should be rejected with 409 when visibility_condition is false."""
    from app.models.form import Condition

    headers = _auth_header(
        client,
        "question-action-admin@example.com",
        "StrongPass123!",
    )

    # Create visibility condition: only visible when status is "in_review"
    vis_condition = Condition(
        uuid="vis-cond-001",
        conditionType="comparison",
        targetField="status",
        operator="equals",
        operands=["in_review"],
        isActive=True,
    )
    vis_condition.save()

    form = Form(
        uuid="form-vis-cond-0001", versions=[Version(uuid="v1")], sections={"v1": []}
    )
    form.save()
    section = Section(
        uuid="section-vis-cond-0001",
        versions=[Version(uuid="section-v1")],
        questions={"section-v1": ["question-vis-cond-0001"]},
    )
    section.save()
    question = Question(
        uuid="question-vis-cond-0001",
        versions=[Version(uuid="question-v1")],
        type="button",
        label="Conditional Action",
        actions=[
            ActionDefinition(
                id="conditional-action",
                label="Submit",
                visibility_condition=vis_condition,
                steps=[
                    ActionStep(
                        id="step-1",
                        target="backend",
                        type="response.status.set",
                        config={"status": "submitted"},
                    ),
                ],
            )
        ],
    )
    question.save()
    form.sections = {"v1": [section.uuid]}
    form.save()
    project = Project(
        uuid="project-vis-cond-0001",
        name="Visibility Condition Project",
        versions=[Version(uuid="proj-v1")],
        forms=[form],
    )
    project.save()

    response = FormResponse(
        uuid="response-vis-cond-0001",
        form=form,
        form_uuid="form-vis-cond-0001",
        form_version_uuid="v1",
        submitted_by=super_admin_user,
        submitted_by_uuid=super_admin_user.uuid,
        status="draft",  # Not "in_review", so visibility condition is false
    )
    response.save()

    trigger_payload = {
        "response_uuid": "response-vis-cond-0001",
        "response_snapshot": {"status": "draft"},
    }
    trigger_response = client.post(
        "/api/v1/projects/project-vis-cond-0001/forms/form-vis-cond-0001/sections/section-vis-cond-0001/questions/question-vis-cond-0001/actions/conditional-action/trigger",
        data=json.dumps(trigger_payload),
        content_type="application/json",
        headers=headers,
    )
    assert trigger_response.status_code == 409
    error_data = trigger_response.get_json()
    assert "not visible" in error_data["message"].lower()


def test_action_enabled_condition_rejected_when_false(
    client, app_context, super_admin_user
):
    """Action trigger should be rejected with 409 when enabled_condition is false."""
    from app.models.form import Condition

    headers = _auth_header(
        client,
        "question-action-admin@example.com",
        "StrongPass123!",
    )

    # Create enabled condition: only enabled when score > 70
    enabled_condition = Condition(
        uuid="en-cond-001",
        conditionType="comparison",
        targetField="score",
        operator="greater_than",
        operands=["70"],
        isActive=True,
    )
    enabled_condition.save()

    form = Form(
        uuid="form-en-cond-0001", versions=[Version(uuid="v1")], sections={"v1": []}
    )
    form.save()
    section = Section(
        uuid="section-en-cond-0001",
        versions=[Version(uuid="section-v1")],
        questions={"section-v1": ["question-en-cond-0001"]},
    )
    section.save()
    question = Question(
        uuid="question-en-cond-0001",
        versions=[Version(uuid="question-v1")],
        type="button",
        label="Enabled Conditional Action",
        actions=[
            ActionDefinition(
                id="enabled-action",
                label="Approve",
                enabled_condition=enabled_condition,
                steps=[
                    ActionStep(
                        id="step-1",
                        target="backend",
                        type="response.status.set",
                        config={"status": "approved"},
                    ),
                ],
            )
        ],
    )
    question.save()
    form.sections = {"v1": [section.uuid]}
    form.save()
    project = Project(
        uuid="project-en-cond-0001",
        name="Enabled Condition Project",
        versions=[Version(uuid="proj-v1")],
        forms=[form],
    )
    project.save()

    response = FormResponse(
        uuid="response-en-cond-0001",
        form=form,
        form_uuid="form-en-cond-0001",
        form_version_uuid="v1",
        submitted_by=super_admin_user,
        submitted_by_uuid=super_admin_user.uuid,
        status="in_review",
        metadata={"score": 50},  # Score is 50, less than 70, so condition is false
    )
    response.save()

    trigger_payload = {
        "response_uuid": "response-en-cond-0001",
        "response_snapshot": {"score": 50},
    }
    trigger_response = client.post(
        "/api/v1/projects/project-en-cond-0001/forms/form-en-cond-0001/sections/section-en-cond-0001/questions/question-en-cond-0001/actions/enabled-action/trigger",
        data=json.dumps(trigger_payload),
        content_type="application/json",
        headers=headers,
    )
    assert trigger_response.status_code == 409
    error_data = trigger_response.get_json()
    assert "disabled" in error_data["message"].lower()


def test_action_allowed_when_conditions_are_true(client, app_context, super_admin_user):
    """Action trigger should succeed when both visibility and enabled conditions are true."""
    from app.models.form import Condition

    headers = _auth_header(
        client,
        "question-action-admin@example.com",
        "StrongPass123!",
    )

    # Create conditions
    vis_condition = Condition(
        uuid="vis-cond-allow-001",
        conditionType="comparison",
        targetField="status",
        operator="equals",
        operands=["in_review"],
        isActive=True,
    )
    vis_condition.save()

    enabled_condition = Condition(
        uuid="en-cond-allow-001",
        conditionType="comparison",
        targetField="score",
        operator="greater_than",
        operands=["70"],
        isActive=True,
    )
    enabled_condition.save()

    form = Form(
        uuid="form-allow-cond-0001", versions=[Version(uuid="v1")], sections={"v1": []}
    )
    form.save()
    section = Section(
        uuid="section-allow-cond-0001",
        versions=[Version(uuid="section-v1")],
        questions={"section-v1": ["question-allow-cond-0001"]},
    )
    section.save()
    question = Question(
        uuid="question-allow-cond-0001",
        versions=[Version(uuid="question-v1")],
        type="button",
        label="Action with Both Conditions",
        actions=[
            ActionDefinition(
                id="allow-action",
                label="Approve",
                visibility_condition=vis_condition,
                enabled_condition=enabled_condition,
                steps=[
                    ActionStep(
                        id="step-1",
                        target="backend",
                        type="response.status.set",
                        config={"status": "approved"},
                    ),
                ],
            )
        ],
    )
    question.save()
    form.sections = {"v1": [section.uuid]}
    form.save()
    project = Project(
        uuid="project-allow-cond-0001",
        name="Allow Condition Project",
        versions=[Version(uuid="proj-v1")],
        forms=[form],
    )
    project.save()

    response = FormResponse(
        uuid="response-allow-cond-0001",
        form=form,
        form_uuid="form-allow-cond-0001",
        form_version_uuid="v1",
        submitted_by=super_admin_user,
        submitted_by_uuid=super_admin_user.uuid,
        status="in_review",  # Status is "in_review", so visibility condition is true
        metadata={
            "score": 85
        },  # Score is 85, greater than 70, so enabled condition is true
    )
    response.save()

    trigger_payload = {
        "response_uuid": "response-allow-cond-0001",
        "response_snapshot": {"status": "in_review", "score": 85},
    }
    trigger_response = client.post(
        "/api/v1/projects/project-allow-cond-0001/forms/form-allow-cond-0001/sections/section-allow-cond-0001/questions/question-allow-cond-0001/actions/allow-action/trigger",
        data=json.dumps(trigger_payload),
        content_type="application/json",
        headers=headers,
    )
    assert trigger_response.status_code == 200
    trigger_data = trigger_response.get_json()
    assert trigger_data["execution"]["status"] == "success"

    updated_response = FormResponse.objects.get(uuid="response-allow-cond-0001")
    assert updated_response.status == "approved"
