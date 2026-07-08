# Testing Guide

## Overview

The test suite uses **pytest** with **mongomock** as the MongoDB backend — no real MongoDB instance is required to run tests.

```
tests/
├── conftest.py                          # App fixture, DB setup/teardown
├── test_api_auth.py                     # Auth endpoint integration tests
├── test_integration.py                  # Cross-domain integration tests
├── test_config.py                       # Configuration loading/validation
├── test_models_form_state.py            # Form workflow state machine
├── test_models_organization.py          # Organization model
├── test_models_user.py                  # User model + tracking fields
├── test_services_auth.py                # JWT create/decode/rotate/revoke
├── test_services_rbac.py                # RBAC access checks
├── test_security_validation.py          # Security-specific scenarios
├── test_condition_evaluator.py          # Condition evaluation engine
├── test_condition_advanced_evaluator.py # Temporal/arithmetic/set conditions
├── test_condition_cache.py              # TTL/historical/negative caches
├── test_condition_management.py         # Condition lifecycle management
├── test_resources_api.py               # Resources CRUD smoke tests
├── test_rate_limit_service.py          # Redis-backed rate limiting behavior
├── test_condition_performance.py        # Evaluation performance benchmark
├── test_conditions_api.py               # Condition API endpoints
├── test_question_actions.py             # Question action triggers
├── test_safe_dsl.py                     # Sandboxed arithmetic DSL
├── test_logger_service.py               # Structured logger service
├── test_rotating_logger.py              # Rotating file logger
├── test_runtime_logging_audit.py        # Full-request logging lifecycle audit
└── test_ui_templates.py                 # UI template endpoints
```

---

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=term --cov-report=html

# Run a specific file
pytest tests/test_api_auth.py -v

# Run by marker
pytest -m unit
pytest -m integration
pytest -m security

# Run in parallel (requires pytest-xdist)
pytest -n auto

# Show only failures
pytest --tb=short -q
```

---

## Test Markers

Defined in `pytest.ini`:

| Marker        | Usage                                              |
|--------------|----------------------------------------------------|
| `unit`        | Tests for individual components in isolation      |
| `integration` | Tests for component interactions                  |
| `security`    | Security-focused scenarios                        |
| `api`         | HTTP endpoint tests via `client` fixture          |
| `model`       | MongoEngine document model tests                  |
| `service`     | Service layer logic tests                         |
| `performance` | Performance and load tests                        |
| `edge_case`   | Boundary conditions and edge cases                |
| `slow`        | Long-running tests (excluded from quick runs)     |

---

## Fixtures

### `app` (session scope)

Creates a Flask application configured for testing with:
- `TESTING=True`
- MongoDB via mongomock
- A fixed `JWT_SECRET_KEY`
- Rate limit and audit settings suitable for test isolation

```python
def test_something(app):
    with app.app_context():
        ...
```

### `client`

A `FlaskClient` for making HTTP requests in tests:

```python
def test_login(client):
    resp = client.post("/api/v1/auth/login", json={...})
    assert resp.status_code == 200
```

### `cleanup_db` (autouse)

Drops and re-creates the test database before and after **every test function**. All MongoEngine documents are wiped between tests.

### `app_context`

Wraps `app.app_context()` for tests that need direct model access without HTTP:

```python
def test_user_model(app_context):
    from app.models.user import User
    user = User(...)
    user.save()
    assert User.objects.count() == 1
```

---

## Writing Tests

### Happy path + error path

Every new endpoint should have at minimum:

```python
def test_create_widget_success(client, access_token):
    resp = client.post(
        "/api/v1/widgets",
        json={"name": "foo"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 201
    assert resp.get_json()["name"] == "foo"


def test_create_widget_missing_name(client, access_token):
    resp = client.post(
        "/api/v1/widgets",
        json={},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 422
```

### Testing authentication

```python
from werkzeug.security import generate_password_hash
from app.models.user import User
from app.services.auth import create_user_session

def test_protected_endpoint(client, app):
    with app.app_context():
        user = User(
            uuid="test-uuid",
            email="test@example.com",
            password_hash=generate_password_hash("password"),
            auth_provider="local",
            name="Test User",
        ).save()
        session = create_user_session(user_uuid=user.uuid, email=user.email)

    resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {session['access_token']}"},
    )
    assert resp.status_code == 200
```

### Testing RBAC

See `tests/test_services_rbac.py` for examples. Create users with specific roles and organisations, then verify endpoint access is granted or denied correctly.

---

## Coverage

Target coverage is tracked but not enforced at a hard threshold in CI. Focus on meaningful test cases over line coverage metrics.

View the HTML coverage report after running:

```bash
pytest --cov=app --cov-report=html
open htmlcov/index.html
```

---

## Runtime Logging Audit

`tests/test_runtime_logging_audit.py` is a special integration test that:

1. Iterates every registered `/api/v1/` route.
2. Makes both an unauthenticated and an authenticated request to each.
3. Parses the rotating log files.
4. Asserts that for every request the logs contain the required lifecycle events:
   - `request_received`, `API Started`, `response_sent`, `API Completed`
   - `authentication` stage, `authorization` stage
   - `validation stage`, `database stage`, `external API stage`
   - `business decision`
   - `audit` event (for mutations: POST, PUT, PATCH, DELETE)

This test enforces the observability contract — any route that doesn't produce these log events will cause a CI failure.
