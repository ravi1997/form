"""Integration tests for the global search endpoint."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from werkzeug.security import generate_password_hash

from app.models.auth import SessionAuditLog
from app.models.condition_management import ConditionEvaluationStat
from app.models.form import Condition, Form, FormResponse, Project, Version
from app.models.user import Organization, User
from mongoengine.connection import get_db


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


def _create_user(uuid: str, name: str, email: str, **kwargs) -> User:
    user = User(
        uuid=uuid,
        name=name,
        email=email,
        password_hash=generate_password_hash("Password123!"),
        auth_provider="local",
        status="active",
        is_email_verified=True,
        **kwargs,
    )
    user.save()
    return user


def _create_project_bundle(
    org: Organization, owner: User
) -> tuple[Project, Form, FormResponse, Condition]:
    project = Project(
        uuid="proj-search-0001",
        name="Search Project",
        admins=[owner],
        members=[owner],
        viewers=[owner],
        organizations=[org],
        tags=["alpha", "searchable"],
    ).save()

    version = Version(uuid="form-search-v1", major=1, minor=0, patch=0)
    form = Form(
        uuid="form-search-0001",
        versions=[version],
        viewers=[owner],
        editors=[owner],
        tags=["searchable"],
        workflow_state="submitted",
    ).save()
    project.forms = [form]
    project.save()

    response = FormResponse(
        uuid="resp-search-0001",
        project=project,
        form=form,
        form_version_uuid=version.uuid,
        organization_uuid=org.uuid,
        status="submitted",
    ).save()

    condition = Condition(
        uuid="cond-search-0001",
        conditionType="comparison",
        targetField="score",
        operator="greater_than",
        operands=[10],
        description="Search condition",
    ).save()

    return project, form, response, condition


def test_global_search_includes_core_and_operational_results(client, app_context):
    org = Organization(uuid="org-search-0001", name="Search Org").save()
    admin = _create_user(
        "search-admin-0001",
        "Search Admin",
        "search-admin@example.com",
        is_super_admin=True,
    )
    admin_headers = _auth_header(client, "search-admin@example.com", "Password123!")

    _create_project_bundle(org, admin)
    ConditionEvaluationStat(
        condition_uuid="cond-search-0001",
        endpoint="/api/v1/conditions/monitoring/graph",
        matched=True,
        duration_ms=12.5,
        operator="greater_than",
        condition_type="comparison",
    ).save()
    SessionAuditLog(
        actor_user_uuid=admin.uuid,
        target_user_uuid=admin.uuid,
        session_uuid="sess-search-0001",
        action="login",
        reason="search test",
        metadata={"message": "Search audit entry"},
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    ).save()
    get_db()["dashboards"].insert_one(
        {
            "uuid": "dash-search-0001",
            "name": "Search Dashboard",
            "status": "active",
            "organization_uuid": org.uuid,
            "tags": ["searchable"],
        }
    )
    get_db()["analysis_definitions"].insert_one(
        {
            "uuid": "analysis-search-0001",
            "name": "Search Analysis",
            "status": "active",
            "organization_uuid": org.uuid,
            "tags": ["searchable"],
        }
    )
    get_db()["audit_logs"].insert_one(
        {
            "uuid": "audit-search-0001",
            "message": "Search audit trail",
            "status": "active",
            "organization_uuid": org.uuid,
            "action": "update",
            "resource_type": "project",
            "resource_uuid": "proj-search-0001",
        }
    )

    response = client.get("/api/v1/search?q=search", headers=admin_headers)
    assert response.status_code == 200
    payload = response.get_json()
    kinds = {item["kind"] for item in payload["items"]}

    assert "project" in kinds
    assert "form" in kinds
    assert "response" in kinds
    assert "analysis" in kinds
    assert "analytics" in kinds
    assert "dashboard" in kinds
    assert "audit" in kinds
    assert "activity" in kinds

    routes = {item["route"] for item in payload["items"] if item.get("route")}
    assert "/api/v1/projects/proj-search-0001" in routes
    assert "/api/v1/projects/proj-search-0001/forms/form-search-0001" in routes


def test_global_search_user_visibility_is_role_filtered(client, app_context):
    org = Organization(uuid="org-search-0002", name="Search Org 2").save()
    other_org = Organization(uuid="org-search-0003", name="Other Org").save()

    _create_user(
        "search-super-0001",
        "Search Super",
        "search-super@example.com",
        is_super_admin=True,
    )
    admin_user = _create_user(
        "search-admin-org-0001",
        "Org Admin",
        "org-admin@example.com",
        is_organisation_admin=True,
    )
    admin_user.organizations = [org]
    admin_user.roles = {org.uuid: ["admin"]}
    admin_user.save()

    viewer_user = _create_user(
        "search-viewer-0001",
        "Org Viewer",
        "org-viewer@example.com",
    )
    viewer_user.organizations = [org]
    viewer_user.roles = {org.uuid: ["viewer"]}
    viewer_user.save()

    other_user = _create_user(
        "search-other-0001",
        "Other Org User",
        "other-org@example.com",
    )
    other_user.organizations = [other_org]
    other_user.roles = {other_org.uuid: ["viewer"]}
    other_user.save()

    super_headers = _auth_header(client, "search-super@example.com", "Password123!")
    admin_headers = _auth_header(client, "org-admin@example.com", "Password123!")
    viewer_headers = _auth_header(client, "org-viewer@example.com", "Password123!")

    super_res = client.get("/api/v1/search?q=org", headers=super_headers)
    admin_res = client.get("/api/v1/search?q=org", headers=admin_headers)
    viewer_res = client.get("/api/v1/search?q=org", headers=viewer_headers)

    assert super_res.status_code == 200
    assert admin_res.status_code == 200
    assert viewer_res.status_code == 200

    super_items = super_res.get_json()["items"]
    admin_items = admin_res.get_json()["items"]
    viewer_items = viewer_res.get_json()["items"]

    assert any(
        item["kind"] == "user" and item["uuid"] == admin_user.uuid
        for item in super_items
    )
    assert any(
        item["kind"] == "user" and item["uuid"] == other_user.uuid
        for item in super_items
    )
    assert any(
        item["kind"] == "user" and item["uuid"] == admin_user.uuid
        for item in admin_items
    )
    assert all(
        item["uuid"] != other_user.uuid
        for item in admin_items
        if item["kind"] == "user"
    )
    assert all(item["kind"] != "user" for item in viewer_items)
