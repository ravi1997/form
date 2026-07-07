import pytest
from mongoengine.errors import ValidationError

from app.models.form import Form, FormResponse, Version


def _reset_form_collections():
    Form.drop_collection()
    FormResponse.drop_collection()


@pytest.fixture(autouse=True)
def _clean_form_state_collections(app_context):
    _reset_form_collections()
    yield
    _reset_form_collections()


def test_form_rejects_invalid_workflow_transition(app_context):
    form = Form(
        uuid="form-state-0001",
        versions=[Version(uuid="v1")],
        sections={"v1": []},
    )
    form.save()

    form.workflow_state = "approved"
    with pytest.raises(ValidationError):
        form.save()


def test_form_allows_valid_workflow_transition(app_context):
    form = Form(
        uuid="form-state-0002",
        versions=[Version(uuid="v1")],
        sections={"v1": []},
    )
    form.save()

    form.workflow_state = "submitted"
    form.save()

    saved = Form.objects.get(uuid="form-state-0002")
    assert saved.workflow_state == "submitted"


def test_response_rejects_invalid_status_transition(app_context):
    form = Form(
        uuid="form-response-state-0001",
        versions=[Version(uuid="v1")],
        sections={"v1": []},
    )
    form.save()

    response = FormResponse(
        uuid="response-state-0001",
        form=form,
        form_uuid=form.uuid,
        form_version_uuid="v1",
        status="draft",
    )
    response.save()

    response.status = "approved"
    with pytest.raises(ValidationError):
        response.save()


def test_response_status_history_and_timestamps_are_maintained(app_context):
    form = Form(
        uuid="form-response-state-0002",
        versions=[Version(uuid="v1")],
        sections={"v1": []},
    )
    form.save()

    response = FormResponse(
        uuid="response-state-0002",
        form=form,
        form_uuid=form.uuid,
        form_version_uuid="v1",
        status="draft",
    )
    response.save()

    assert len(response.status_history) == 1
    assert response.status_history[0].transition_from is None
    assert response.status_history[0].transition_to == "draft"
    assert response.reviewed_at is None
    assert response.approved_at is None

    response.status = "submitted"
    response.save()
    assert response.submitted_at is not None
    assert response.reviewed_at is None
    assert response.approved_at is None
    assert response.status_history[-1].transition_from == "draft"
    assert response.status_history[-1].transition_to == "submitted"

    response.status = "in_review"
    response.save()
    assert response.reviewed_at is not None
    assert response.approved_at is None
    assert response.status_history[-1].transition_from == "submitted"
    assert response.status_history[-1].transition_to == "in_review"

    response.status = "approved"
    response.save()
    assert response.approved_at is not None
    assert response.status_history[-1].transition_from == "in_review"
    assert response.status_history[-1].transition_to == "approved"
