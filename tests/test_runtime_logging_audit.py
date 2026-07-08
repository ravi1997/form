from __future__ import annotations

import importlib
import inspect
import json
import os
import tempfile
import uuid
from typing import Any, get_args, get_origin

import pytest
from mongomock import MongoClient
from werkzeug.security import generate_password_hash

from app import create_openapi_app
from app.models.form import Choice, Condition, Form, Project, Question, Section, Version
from app.models.rate_limit import RateLimitConfig
from app.models.user import Organization, User


PUBLIC_PREFIXES = (
    "/api/v1/health",
    "/api/v1/schemas/echo-form",
    "/api/v1/auth/register",
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
)


def _parse_line(raw: str) -> dict[str, Any] | None:
    index = raw.find("{")
    if index == -1:
        return None
    payload = raw[index:].strip()
    try:
        return json.loads(payload)
    except Exception:
        return None


def _collect_events(log_dir: str) -> dict[str, list[dict[str, Any]]]:
    by_request_id: dict[str, list[dict[str, Any]]] = {}
    for filename in (
        "requests.log",
        "responses.log",
        "app.log",
        "debug.log",
        "errors.log",
    ):
        path = os.path.join(log_dir, filename)
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                payload = _parse_line(line)
                if not payload:
                    continue
                request_id = payload.get("request_id")
                if request_id:
                    by_request_id.setdefault(str(request_id), []).append(payload)
    return by_request_id


def _val_for_type(tp: Any, name: str = "field") -> Any:
    origin = get_origin(tp)
    args = get_args(tp)
    if origin is None:
        if tp is str:
            if "email" in name:
                return "admin@example.com"
            if "password" in name:
                return "StrongPass123!"
            if "uuid" in name:
                return f"{name}-{uuid.uuid4().hex[:8]}"
            return f"{name}-value"
        if tp is int:
            return 1
        if tp is float:
            return 1.0
        if tp is bool:
            return True
        if tp is list:
            return []
        if tp is dict:
            return {}
        return None

    if origin in (list,):
        inner = args[0] if args else str
        return [_val_for_type(inner, name)]
    if origin in (dict,):
        return {}
    if str(origin).endswith("Literal"):
        return args[0]
    if origin is __import__("typing").Union:
        non_none = [a for a in args if a is not type(None)]
        return _val_for_type(non_none[0], name) if non_none else None
    return None


def _payload_for_model(
    model_name: str, model: Any, refresh_token: str | None, session_uuid: str | None
) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for field_name, field in model.model_fields.items():
        if field.default is not ... and field.default is not None:
            continue
        if field.default_factory is not None:
            continue
        value = _val_for_type(field.annotation, field_name)
        if value is None:
            value = f"{field_name}-value"
        data[field_name] = value

    overrides: dict[str, dict[str, Any]] = {
        "RegisterRequest": {
            "email": f"user-{uuid.uuid4().hex[:6]}@example.com",
            "name": "Audit User",
            "password": "StrongPass123!",
        },
        "LoginRequest": {"email": "admin@example.com", "password": "StrongPass123!"},
        "RevokeSessionRequest": {
            "session_uuid": session_uuid or "session-001",
            "reason": "audit",
        },
        "AdminRevokeSessionRequest": {
            "session_uuid": session_uuid or "session-001",
            "reason": "audit",
        },
        "LogoutAllSessionsRequest": {"reason": "audit"},
        "ProjectCreateInput": {
            "uuid": f"project-{uuid.uuid4().hex[:6]}",
            "name": "Project Created",
        },
        "FormCreateInput": {"uuid": f"form-{uuid.uuid4().hex[:6]}"},
        "SectionCreateInput": {"uuid": f"section-{uuid.uuid4().hex[:6]}"},
        "QuestionCreateInput": {
            "uuid": f"question-{uuid.uuid4().hex[:6]}",
            "type": "text",
            "label": "Q",
        },
        "ChoiceCreateInput": {
            "uuid": f"choice-{uuid.uuid4().hex[:6]}",
            "label": "C",
            "value": "c",
        },
        "ConditionCreateInput": {
            "uuid": f"cond-{uuid.uuid4().hex[:6]}",
            "conditionType": "regex",
            "expression": ".*",
            "targetField": "field_a",
        },
        "VersionCreateInput": {
            "uuid": f"ver-{uuid.uuid4().hex[:6]}",
            "major": 1,
            "minor": 0,
            "patch": 0,
            "status": "draft",
        },
        "WorkflowActionRequest": {"note": "ok"},
        "RateLimitCreateRequest": {
            "rule_id": f"rule-{uuid.uuid4().hex[:6]}",
            "scope": "global",
            "max_requests": 10,
            "window_size": 60,
            "unit": "second",
            "route_pattern": "/api/v1/sample",
            "is_active": True,
            "priority": 1,
        },
        "RateLimitUpdateRequest": {"max_requests": 20},
        "ConditionImpactInput": {"sample_contexts": [{"field_a": "x"}]},
        "ActorUserInput": {"actor_user_uuid": "user-admin-001"},
        "VersionRecordInput": {
            "actor_user_uuid": "user-admin-001",
            "action": "update",
            "changelog": "audit",
        },
    }
    data.update(overrides.get(model_name, {}))

    if model_name == "RefreshTokenRequest":
        data = {"refresh_token": refresh_token or "invalid-token"}
    if model_name == "LogoutRequest":
        data = {"refresh_token": refresh_token or "invalid-token"}
    return data


def _ensure_seed_state() -> None:
    org = Organization.objects(uuid="org-001").first()
    if not org:
        org = Organization(uuid="org-001", name="Org 001").save()

    admin = User.objects(uuid="user-admin-001").first()
    if not admin:
        admin = User(
            uuid="user-admin-001",
            name="Admin User",
            email="admin@example.com",
            password_hash=generate_password_hash("StrongPass123!"),
            auth_provider="local",
            is_super_admin=True,
            is_organisation_admin=True,
            organizations=[org],
            roles={str(org.id): ["admin"]},
        ).save()

    condition = Condition.objects(uuid="cond-001").first()
    if not condition:
        Condition(
            uuid="cond-001",
            conditionType="regex",
            expression=".*",
            targetField="field_a",
            status="active",
        ).save()

    question = Question.objects(uuid="question-001").first()
    if not question:
        Question(
            uuid="question-001",
            type="text",
            label="Question 1",
            choices=[Choice(uuid="choice-001", label="Choice 1", value="choice-1")],
        ).save()

    section = Section.objects(uuid="section-001").first()
    if not section:
        Section(
            uuid="section-001",
            versions=[
                Version(
                    uuid="ver-section-001", major=1, minor=0, patch=0, status="draft"
                )
            ],
            questions={"ver-section-001": ["question-001"]},
            status="active",
        ).save()

    form = Form.objects(uuid="form-001").first()
    if not form:
        form = Form(
            uuid="form-001",
            versions=[
                Version(uuid="ver-form-001", major=1, minor=0, patch=0, status="draft")
            ],
            sections={"ver-form-001": ["section-001"]},
            status="active",
        ).save()

    project = Project.objects(uuid="project-001").first()
    if not project:
        Project(
            uuid="project-001",
            name="Project 1",
            forms=[form],
            organizations=[org],
            admins=[admin],
            members=[admin],
            viewers=[admin],
            versions=[
                Version(
                    uuid="ver-project-001", major=1, minor=0, patch=0, status="draft"
                )
            ],
            status="active",
        ).save()

    if not RateLimitConfig.objects(rule_id="rule-001").first():
        RateLimitConfig(
            rule_id="rule-001",
            scope="global",
            max_requests=100,
            window_size=60,
            unit="second",
            route_pattern="/api/v1/test",
            is_active=True,
            priority=1,
        ).save()


@pytest.fixture
def runtime_audit_env():
    with tempfile.TemporaryDirectory(prefix="runtime-audit-test-") as log_dir:
        app = create_openapi_app(
            {
                "TESTING": True,
                "LOG_DIR": log_dir,
                "JWT_SECRET_KEY": "test-secret-key-do-not-use-in-production",
                "MONGODB_SETTINGS": {
                    "db": "runtime_audit_test_db",
                    "host": "mongodb://localhost/runtime_audit_test_db",
                    "mongo_client_class": MongoClient,
                    "connect": False,
                },
                "ENABLE_AUDIT_LOGS": True,
            }
        )
        client = app.test_client()
        with app.app_context():
            _ensure_seed_state()
        yield app, client, log_dir


def test_runtime_logging_lifecycle_for_all_v1_routes(runtime_audit_env):
    app, client, log_dir = runtime_audit_env

    seed = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "StrongPass123!"},
        headers={"X-Request-Id": "seed-login"},
    )
    seed_json = seed.get_json(silent=True) or {}
    access_token = seed_json.get("access_token") or seed_json.get("accessToken")
    refresh_token = seed_json.get("refresh_token") or seed_json.get("refreshToken")
    session_uuid = seed_json.get("session_uuid") or seed_json.get("sessionUuid")

    state = {
        "uuid": "project-001",
        "project_uuid": "project-001",
        "form_uuid": "form-001",
        "section_uuid": "section-001",
        "question_uuid": "question-001",
        "choice_uuid": "choice-001",
        "condition_uuid": "cond-001",
        "version_uuid": "ver-project-001",
        "user_uuid": "user-admin-001",
        "rule_id": "rule-001",
        "job_id": "job-001",
    }

    executed_requests: dict[str, dict[str, Any]] = {}
    route_count = 0

    for rule in sorted(app.url_map.iter_rules(), key=lambda item: item.rule):
        if not rule.rule.startswith("/api/v1/"):
            continue

        methods = sorted(
            method
            for method in rule.methods
            if method in {"GET", "POST", "PATCH", "PUT", "DELETE"}
        )
        if not methods:
            continue

        for method in methods:
            route_count += 1
            with app.app_context():
                _ensure_seed_state()

            path = rule.rule
            for key, value in state.items():
                path = path.replace(f"<{key}>", value)
            if "<" in path and ">" in path:
                segments = []
                for segment in path.split("/"):
                    if segment.startswith("<") and segment.endswith(">"):
                        token = segment[1:-1]
                        if ":" in token:
                            _, token = token.split(":", 1)
                        segments.append(state.get(token, f"{token}-value"))
                    else:
                        segments.append(segment)
                path = "/".join(segments)

            payload = None
            endpoint = rule.endpoint
            module_name, _, function_name = endpoint.rpartition(".")
            if module_name:
                try:
                    api_module = importlib.import_module(
                        f"app.api.{module_name.split('.')[-1]}"
                    )
                    function = getattr(api_module, function_name, None)
                except Exception:
                    function = None
                if function is not None:
                    signature = inspect.signature(function)
                    body_parameter = signature.parameters.get("body")
                    if body_parameter is not None and hasattr(
                        body_parameter.annotation, "model_fields"
                    ):
                        model = body_parameter.annotation
                        payload = _payload_for_model(
                            model.__name__, model, refresh_token, session_uuid
                        )

            fail_request_id = f"fail-{uuid.uuid4().hex[:10]}"
            ok_request_id = f"ok-{uuid.uuid4().hex[:10]}"
            executed_requests[fail_request_id] = {"method": method, "path": path}
            executed_requests[ok_request_id] = {"method": method, "path": path}

            fail_headers = {"X-Request-Id": fail_request_id}
            ok_headers = {"X-Request-Id": ok_request_id}
            if access_token and not any(
                path.startswith(prefix) for prefix in PUBLIC_PREFIXES
            ):
                ok_headers["Authorization"] = f"Bearer {access_token}"

            client.open(
                path,
                method=method,
                headers=fail_headers,
                json=payload if payload is not None else None,
            )
            client.open(
                path,
                method=method,
                headers=ok_headers,
                json=payload if payload is not None else None,
            )

    by_request_id = _collect_events(log_dir)
    assert route_count > 0
    assert executed_requests, "No requests executed during runtime audit test"

    missing = []
    for request_id, meta in executed_requests.items():
        entries = by_request_id.get(request_id, [])
        if not entries:
            missing.append(f"{request_id}: no log entries")
            continue

        events = [str(entry.get("event", "")).lower() for entry in entries]
        messages = [str(entry.get("message", "")).lower() for entry in entries]
        combined = " | ".join(events + messages)

        if "request_received" not in combined:
            missing.append(f"{request_id}: missing request_received")
        if "api started" not in combined:
            missing.append(f"{request_id}: missing API Started")
        if "response_sent" not in combined:
            missing.append(f"{request_id}: missing response_sent")
        if "api completed" not in combined:
            missing.append(f"{request_id}: missing API Completed")
        if "authentication" not in combined:
            missing.append(f"{request_id}: missing authentication stage log")
        if "authorization" not in combined:
            missing.append(f"{request_id}: missing authorization stage log")
        if "validation stage" not in combined:
            missing.append(f"{request_id}: missing validation stage log")
        if "database stage" not in combined:
            missing.append(f"{request_id}: missing database stage log")
        if "external api stage" not in combined:
            missing.append(f"{request_id}: missing external API stage log")
        if "business decision" not in combined:
            missing.append(f"{request_id}: missing business decision stage log")
        if (
            meta["method"] in {"POST", "PUT", "PATCH", "DELETE"}
            and "audit" not in combined
        ):
            missing.append(f"{request_id}: missing audit stage log")

        request_ids = {
            entry.get("request_id") for entry in entries if entry.get("request_id")
        }
        correlation_ids = {
            entry.get("correlation_id")
            for entry in entries
            if entry.get("correlation_id")
        }
        if len(request_ids) > 1:
            missing.append(
                f"{request_id}: request_id mismatch in logs -> {sorted(request_ids)}"
            )
        if len(correlation_ids) > 1:
            missing.append(
                f"{request_id}: correlation_id mismatch in logs -> {sorted(correlation_ids)}"
            )
        if correlation_ids and request_ids and correlation_ids != request_ids:
            missing.append(f"{request_id}: correlation_id does not match request_id")

    assert not missing, "Runtime logging lifecycle gaps:\\n" + "\\n".join(missing)
